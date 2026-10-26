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
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from accounti.abschluss.konfiguration import KassenEinstellungen
from accounti.abschluss.salden import FREIGEGEBEN
from accounti.anzeige import betrag_de
from accounti.db.repo_abschluss import pruefe_jahr_offen
from accounti.db.repo_kasse import (
    lade_kassenbuch,
    naechste_kassennummer,
    speichere_kassenvorgang,
)
from accounti.db.repo_pruefung import (
    lade_korrekturen,
    setze_storniert_durch,
    speichere_korrektur,
)
from accounti.db.repository import (
    lade_buchungen,
    speichere_buchung,
    speichere_transaktion,
)
from accounti.models import Buchungssatz, BuchungStatus, Transaktion, TransaktionQuelle
from accounti.models.kasse import Kassenart, Kassenvorgang
from accounti.models.pruefung import Buchungskorrektur
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
    umkehren: list[Buchungssatz] | None = None,
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
    buchungen: list[Buchungssatz] = []
    if umkehren:
        # die Gegenbuchung ist ein Storno der gültigen Buchung (Baustein 7): Vermerke
        # des Originals nicht mitkopieren, sondern auf das Original verweisen
        for original in umkehren:
            storno = original.model_copy(
                update={
                    "id": uuid4(),
                    "transaktion_id": tx.id,
                    "datum": v.datum,
                    "soll_konto": original.haben_konto,
                    "haben_konto": original.soll_konto,
                    "buchungstext": v.text[:60],
                    "status": BuchungStatus.GEPRUEFT,
                    "geprueft_von": v.erfasst_von or "kassenbuch",
                    "storniert_durch": None,
                    "storno_von": original.id,
                }
            )
            speichere_buchung(session, storno)
            session.flush()
            setze_storniert_durch(session, original.id, storno.id)
            speichere_korrektur(
                session,
                Buchungskorrektur(
                    original_id=original.id,
                    storno_id=storno.id,
                    datum=v.datum,
                    grund=v.text,
                    person=v.erfasst_von or "kassenbuch",
                ),
            )
            buchungen.append(storno)
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
        speichere_buchung(session, buchung)
        buchungen.append(buchung)
    v = v.model_copy(
        update={
            "transaktion_id": tx.id,
            "buchung_id": buchungen[0].id if buchungen else None,
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


def _gueltige_buchung(
    session: Session, buchung_id: UUID, nr: int
) -> Buchungssatz | None:
    """Die Buchung, die für den Kassenvorgang gerade gilt: nach ``korrigiere`` die
    Neubuchung (Kette über die Buchungskorrekturen), sonst das Original."""
    alle = {b.id: b for b in lade_buchungen(session)}
    neubuchung = {k.original_id: k.neubuchung_id for k in lade_korrekturen(session)}
    b = alle.get(buchung_id)
    gesehen: set[UUID] = set()
    while b is not None and b.storniert_durch is not None and b.id not in gesehen:
        gesehen.add(b.id)
        nachfolger = neubuchung.get(b.id)
        if nachfolger is None:
            raise KassenbuchError(
                f"Die Buchung {str(b.id)[:8]} zu Nr. {nr} ist storniert, ohne "
                "Neubuchung — es gibt keine gültige Buchung, die sich umkehren "
                "ließe; den Umsatz erst neu buchen (accounti classify), dann "
                "stornieren"
            )
        b = alle.get(nachfolger)
    return b


def _buchungen_zum_umsatz(
    session: Session, transaktion_id: UUID, nr: int
) -> list[Buchungssatz]:
    """Die gültigen Buchungen am Umsatz eines Kassenvorgangs ohne eigene Buchung —
    angelegt von ``classify`` (Regelwerk, Belegabgleich, auch Splitbuchungen); nach
    ``korrigiere`` die Neubuchung (sie behält den Umsatz). Das Kassenbuch ist nur
    anfügbar, ``buchung_id`` lässt sich dort nicht nachtragen — der Weg zur Buchung
    führt deshalb über ``transaktion_id`` (Befund B5)."""
    am_umsatz = [
        b
        for b in lade_buchungen(session)
        if b.transaktion_id == transaktion_id and b.storno_von is None
    ]
    gueltig = [b for b in am_umsatz if b.storniert_durch is None]
    if am_umsatz and not gueltig:
        raise KassenbuchError(
            f"Die Buchung zu Nr. {nr} ist storniert, ohne Neubuchung — es gibt keine "
            "gültige Buchung, die sich umkehren ließe; den Umsatz erst neu buchen "
            "(accounti classify), dann stornieren"
        )
    vorschlaege = [b for b in gueltig if b.status not in FREIGEGEBEN]
    if vorschlaege:
        kurz = ", ".join(str(b.id)[:8] for b in vorschlaege)
        raise KassenbuchError(
            f"Die Buchung {kurz} zu Nr. {nr} ist noch ein Vorschlag — erst freigeben "
            "(accounti bestaetige) oder direkt korrigieren (accounti korrigiere), "
            "dann stornieren"
        )
    return sorted(gueltig, key=lambda b: (b.datum, str(b.id)))


def storniere(
    session: Session,
    nr: int,
    grund: str,
    einstellungen: KassenEinstellungen,
    datum: date | None = None,
    von: str | None = None,
) -> Kassenvorgang:
    """Gegeneintrag zu Nr. ``nr``; die gültige Buchung des Originals wird umgekehrt —
    die eigene (mit Gegenkonto erfasst) oder die von ``classify`` am Umsatz.

    Das Storno liegt nie vor dem Original: Der Gegeneintrag machte den Kassenbestand
    dazwischen falsch (Kassensturzfähigkeit, § 146 Abs. 1 AO), und die Umsatzsteuer
    würde vor dem Umsatz berichtigt. Ebenso nie vor der Buchung, die es umkehrt (nach
    ``korrigiere --datum`` kann die Neubuchung später liegen). Ohne ``datum`` gilt
    heute, frühestens der Tag des Originals bzw. dieser Buchung."""
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
    umkehren: list[Buchungssatz] = []
    if original.buchung_id is not None:
        gueltig = _gueltige_buchung(session, original.buchung_id, nr)
        umkehren = [gueltig] if gueltig is not None else []
    elif original.transaktion_id is not None:
        umkehren = _buchungen_zum_umsatz(session, original.transaktion_id, nr)
    # auch nicht vor der Buchung, die es umkehrt (nach korrigiere --datum später)
    frueheste = max([original.datum, *(b.datum for b in umkehren)])
    tag = datum or max(date.today(), frueheste)
    if tag < original.datum:
        raise KassenbuchError(
            f"Storno am {tag:%d.%m.%Y} läge vor Nr. {nr} vom "
            f"{original.datum:%d.%m.%Y} — ein Storno frühestens am Tag des Originals"
        )
    if tag < frueheste:
        raise KassenbuchError(
            f"Storno am {tag:%d.%m.%Y} läge vor der Buchung vom "
            f"{frueheste:%d.%m.%Y}, die es umkehrt (Neubuchung zu Nr. {nr}) — ein "
            "Storno frühestens an deren Tag"
        )
    v = Kassenvorgang(
        nr=naechste_kassennummer(session),
        datum=tag,
        betrag=-original.betrag,
        art=Kassenart.STORNO,
        text=f"Storno Nr. {nr}: {grund}",
        belegnummer=original.belegnummer,
        gegenkonto=original.gegenkonto,
        storno_von=nr,
        erfasst_von=von,
    )
    return _speichere(session, v, einstellungen, umkehren)
