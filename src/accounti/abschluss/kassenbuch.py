"""Kassenbuch — Bargeschäfte mit laufender Nummer, Tagessaldo und Kassensturz.

Ein negativer Kassenbestand ist rechnerisch unmöglich und wird deshalb abgelehnt, nicht
gewarnt (Spec 4.4). Geprüft wird der ganze Bestandsverlauf ab dem Buchungstag, denn
auch ein rückdatierter Eintrag kann einen späteren Tag ins Minus ziehen.

Einträge sind unveränderbar (Tabelle ``kassenbuch``, nur anfügen); korrigiert wird per
Storno. Jeder Vorgang wird eine Transaktion mit dem Kassenkonto als Sachkonto — dann
kontiert ``classify`` ihn, und ``opos zuordnen`` / ``bank abgleich`` sehen ihn. Mit
Gegenkonto entsteht sofort ein geprüfter Buchungssatz; die Steuer kommt aus
``accounti.steuer``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from accounti.abschluss.konfiguration import KassenEinstellungen
from accounti.anzeige import betrag_de
from accounti.db.repo_abschluss import pruefe_jahr_offen
from accounti.db.repo_kasse import (
    lade_kassenbuch,
    naechste_kassennummer,
    speichere_kassenvorgang,
)
from accounti.db.repository import (
    lade_buchungen,
    speichere_buchung,
    speichere_transaktion,
)
from accounti.models import Buchungssatz, BuchungStatus, Transaktion, TransaktionQuelle
from accounti.models.kasse import Kassenart, Kassenvorgang
from accounti.steuer.umsatzsteuer import DATEV_BU_SCHLUESSEL, UStBerechner

NULL = Decimal("0")


class KassenbuchError(ValueError):
    """Der Kassenvorgang ist so nicht möglich."""


class KasseNegativError(KassenbuchError):
    """Der Vorgang würde den Kassenbestand negativ machen — abgelehnt."""


def verlauf(vorgaenge: Iterable[Kassenvorgang]) -> list[tuple[Kassenvorgang, Decimal]]:
    """Vorgänge nach Datum und Nummer, je mit dem Bestand danach."""
    bestand = NULL
    ergebnis = []
    for v in sorted(vorgaenge, key=lambda v: (v.datum, v.nr)):
        bestand += v.betrag
        ergebnis.append((v, bestand))
    return ergebnis


def bestand(vorgaenge: Iterable[Kassenvorgang], bis: date | None = None) -> Decimal:
    return sum((v.betrag for v in vorgaenge if bis is None or v.datum <= bis), NULL)


def _pruefe_verlauf(vorgaenge: list[Kassenvorgang]) -> None:
    for v, stand in verlauf(vorgaenge):
        if stand < 0:
            msg = (
                f"Kassenbestand würde am {v.datum:%d.%m.%Y} auf "
                f"−{betrag_de(-stand)} € fallen — abgelehnt"
            )
            raise KasseNegativError(msg)


@dataclass(frozen=True)
class Tagessaldo:
    datum: date
    einnahmen: Decimal
    ausgaben: Decimal
    bestand: Decimal


def tagessalden(
    vorgaenge: Iterable[Kassenvorgang], von: date, bis: date
) -> list[Tagessaldo]:
    tage: dict[date, list[Decimal]] = {}
    for v, stand in verlauf(vorgaenge):
        if not von <= v.datum <= bis:
            continue
        t = tage.setdefault(v.datum, [NULL, NULL, NULL])
        if v.betrag >= 0:
            t[0] += v.betrag
        else:
            t[1] -= v.betrag
        t[2] = stand
    return [Tagessaldo(d, e, a, b) for d, (e, a, b) in sorted(tage.items())]


def anfangsbestand(
    session: Session,
    betrag: Decimal,
    datum: date,
    einstellungen: KassenEinstellungen,  # noqa: ARG001 — einheitliche Signatur
    von: str | None = None,
) -> Kassenvorgang:
    """Erster Eintrag eines leeren Kassenbuchs. Gebucht wird er nicht — der EB-Wert des
    Kassenkontos kommt aus Eröffnungssalden oder Saldovortrag."""
    pruefe_jahr_offen(session, datum.year)
    if lade_kassenbuch(session):
        raise KassenbuchError("Anfangsbestand nur in einem leeren Kassenbuch")
    if betrag < 0:
        raise KasseNegativError("Ein negativer Anfangsbestand ist unmöglich")
    v = Kassenvorgang(
        nr=naechste_kassennummer(session),
        datum=datum,
        betrag=betrag,
        art=Kassenart.ANFANGSBESTAND,
        text="Anfangsbestand",
        erfasst_von=von,
    )
    speichere_kassenvorgang(session, v)
    return v


def _buchung(
    tx: Transaktion,
    kassenkonto: str,
    gegenkonto: str,
    steuersatz: Decimal | None,
    text: str,
    belegnummer: str | None,
    von: str | None,
) -> Buchungssatz:
    brutto = abs(tx.betrag)
    netto, steuer, schluessel = brutto, None, None
    einnahme = tx.betrag > 0
    if steuersatz:
        berechner = UStBerechner()
        if einnahme:
            netto = berechner.brutto_zu_netto(brutto, steuersatz)
            steuer = brutto - netto
            schluessel = DATEV_BU_SCHLUESSEL.get(f"ust_{int(steuersatz)}")
        else:
            vst = berechner.berechne_vst(brutto, steuersatz)
            netto, steuer, schluessel = (
                vst.netto,
                vst.steuerbetrag,
                vst.datev_schluessel,
            )
        if schluessel is None:
            raise KassenbuchError(f"Steuersatz {steuersatz} % ist nicht hinterlegt")
    soll, haben = (kassenkonto, gegenkonto) if einnahme else (gegenkonto, kassenkonto)
    return Buchungssatz(
        transaktion_id=tx.id,
        datum=tx.datum,
        soll_konto=soll,
        haben_konto=haben,
        betrag_netto=netto,
        steuer_schluessel=schluessel,
        steuer_betrag=steuer,
        buchungstext=text[:60],
        beleg_nummer=(belegnummer or "")[:36] or None,
        status=BuchungStatus.GEPRUEFT,
        confidence=1.0,
        geprueft_von=von or "kassenbuch",
    )


def _speichere(
    session: Session,
    v: Kassenvorgang,
    einstellungen: KassenEinstellungen,
    buchung_umkehren: Buchungssatz | None = None,
) -> Kassenvorgang:
    pruefe_jahr_offen(session, v.datum.year)
    _pruefe_verlauf([*lade_kassenbuch(session), v])
    tx = Transaktion(
        datum=v.datum,
        betrag=v.betrag,
        verwendungszweck=v.text,
        quelle=TransaktionQuelle.MANUELL,
        rohtext=f"Kassenbuch Nr. {v.nr}: {v.text}",
        sachkonto=einstellungen.konto,
    )
    speichere_transaktion(session, tx)
    buchung: Buchungssatz | None = None
    if buchung_umkehren is not None:
        buchung = buchung_umkehren.model_copy(
            update={
                "id": uuid4(),
                "transaktion_id": tx.id,
                "datum": v.datum,
                "soll_konto": buchung_umkehren.haben_konto,
                "haben_konto": buchung_umkehren.soll_konto,
                "buchungstext": v.text[:60],
                "status": BuchungStatus.GEPRUEFT,
                "geprueft_von": v.erfasst_von or "kassenbuch",
            }
        )
    elif v.gegenkonto:
        buchung = _buchung(
            tx,
            einstellungen.konto,
            v.gegenkonto,
            v.steuersatz,
            v.text,
            v.belegnummer,
            v.erfasst_von,
        )
    if buchung is not None:
        speichere_buchung(session, buchung)
    v = v.model_copy(
        update={
            "transaktion_id": tx.id,
            "buchung_id": buchung.id if buchung else None,
        }
    )
    speichere_kassenvorgang(session, v)
    return v


def buche_kasse(
    session: Session,
    betrag: Decimal,
    text: str,
    einstellungen: KassenEinstellungen,
    datum: date | None = None,
    belegnummer: str | None = None,
    gegenkonto: str | None = None,
    steuersatz: Decimal | None = None,
    von: str | None = None,
) -> Kassenvorgang:
    """Einnahme (positiv) oder Ausgabe (negativ) — abgelehnt, wenn die Kasse ins Minus
    fiele."""
    if betrag == 0:
        raise KassenbuchError("Ein Kassenvorgang über 0 € ist keiner")
    if not text.strip():
        raise KassenbuchError("Buchungstext fehlt")
    v = Kassenvorgang(
        nr=naechste_kassennummer(session),
        datum=datum or date.today(),
        betrag=betrag,
        art=Kassenart.EINNAHME if betrag > 0 else Kassenart.AUSGABE,
        text=text.strip(),
        belegnummer=belegnummer,
        gegenkonto=gegenkonto,
        steuersatz=steuersatz,
        erfasst_von=von,
    )
    return _speichere(session, v, einstellungen)


def storniere(
    session: Session,
    nr: int,
    grund: str,
    einstellungen: KassenEinstellungen,
    datum: date | None = None,
    von: str | None = None,
) -> Kassenvorgang:
    """Gegeneintrag zu Nr. ``nr``; eine Buchung des Originals wird umgekehrt."""
    buch = lade_kassenbuch(session)
    original = next((v for v in buch if v.nr == nr), None)
    if original is None:
        raise KassenbuchError(f"Kassenvorgang Nr. {nr} gibt es nicht")
    if original.art in (Kassenart.STORNO, Kassenart.ANFANGSBESTAND):
        raise KassenbuchError(
            f"Nr. {nr} ({original.art.value}) kann nicht storniert werden"
        )
    if any(v.storno_von == nr for v in buch):
        raise KassenbuchError(f"Nr. {nr} ist schon storniert")
    umkehren = None
    if original.buchung_id is not None:
        umkehren = next(
            (b for b in lade_buchungen(session) if b.id == original.buchung_id), None
        )
    v = Kassenvorgang(
        nr=naechste_kassennummer(session),
        datum=datum or date.today(),
        betrag=-original.betrag,
        art=Kassenart.STORNO,
        text=f"Storno Nr. {nr}: {grund}",
        belegnummer=original.belegnummer,
        gegenkonto=original.gegenkonto,
        storno_von=nr,
        erfasst_von=von,
    )
    return _speichere(session, v, einstellungen, umkehren)
