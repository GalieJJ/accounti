"""Saldovortrag ins neue Jahr, Jahressperre und Abschlussprotokoll (Spec 4.8).

Schlusssalden: Bestandskonten mit ihrem Saldo; Erfolgs- und Privatkonten (bei EÜR auch
die Steuerkonten) gehen auf das Kapitalkonto. Daraus werden Eröffnungsbuchungen am
01.01. des Folgejahres gegen die Saldenvortragskonten (9000, Debitoren 9008,
Kreditoren 9009). Gebucht wird nur der Unterschied zu schon vorhandenen EB-Werten —
ein erneuter Vortrag nach dem Wiederöffnen korrigiert, statt etwas zu löschen.

Ein Fehler-Befund der Abschlussprüfung verhindert den Vortrag. Danach ist das Jahr
gesperrt (``JahrGesperrtError`` bei jeder Buchung); geöffnet wird es nur mit Grund,
und jede Aktion steht im Abschlussprotokoll (``protokoll.py``: nur anfügen,
Hash-Kette).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from accounti.abschluss.konfiguration import AbschlussEinstellungen
from accounti.abschluss.kontenrahmen import Kontenart, Kontenrahmen
from accounti.abschluss.protokoll import hash_von, protokolliere
from accounti.abschluss.pruefungen import (
    Abschlusskontext,
    Befund,
    Schwere,
    blockiert,
    pruefe_abschluss,
)
from accounti.abschluss.salden import summen_und_salden
from accounti.anzeige import betrag_de
from accounti.db.repo_abschluss import (
    ist_gesperrt,
    lade_jahresabschluss,
    pruefe_jahr_offen,
    setze_jahresabschluss,
)
from accounti.db.repository import speichere_buchung
from accounti.models import Buchungssatz, BuchungStatus
from accounti.models.abschluss import Jahresabschluss

NULL = Decimal("0")


class AbschlussError(ValueError):
    """Abschluss, Vortrag oder Öffnen ist so nicht möglich."""


class AbschlussGesperrtError(AbschlussError):
    """Fehler-Befunde der Abschlussprüfung verhindern den Vortrag."""

    def __init__(self, befunde: list[Befund]) -> None:
        self.befunde = befunde
        fehler = [b for b in befunde if b.schwere is Schwere.FEHLER]
        text = "; ".join(f"{b.pruefung}: {b.text}" for b in fehler)
        super().__init__(f"Abschluss gesperrt — {text}")


@dataclass
class Vortrag:
    jahr: int
    schlusssalden: dict[str, Decimal]
    ergebnis: Decimal
    buchungen: list[Buchungssatz] = field(default_factory=list)
    befunde: list[Befund] = field(default_factory=list)


def eroeffnungssalden(
    session: Session, jahr: int, kr: Kontenrahmen
) -> dict[str, Decimal]:
    """EB-Werte des Jahres je Konto (ohne die Saldenvortragskonten selbst)."""
    susa = summen_und_salden(session, jahr, kr, "bilanz")
    return {
        z.konto: z.eb
        for z in susa.zeilen
        if z.eb != 0 and not kr.ist_saldenvortrag(z.konto)
    }


def schlusssalden(
    session: Session, jahr: int, einst: AbschlussEinstellungen, kr: Kontenrahmen
) -> dict[str, Decimal]:
    """Bestandskonten zum 31.12. nach Abschluss der Erfolgs- und Privatkonten."""
    susa = summen_und_salden(session, jahr, kr, einst.gewinnermittlung)
    salden: dict[str, Decimal] = {}
    kapital = NULL
    for z in susa.zeilen:
        if kr.ist_saldenvortrag(z.konto) or z.art is Kontenart.VORTRAG:
            continue
        if z.art in (Kontenart.ERFOLG, Kontenart.PRIVAT):
            kapital += z.saldo
        elif z.saldo:
            salden[z.konto] = z.saldo
    gesamt = salden.get(einst.ergebnis_konto, NULL) + kapital
    salden.pop(einst.ergebnis_konto, None)
    if gesamt:
        salden[einst.ergebnis_konto] = gesamt
    return salden


def _eb_buchung(
    konto: str,
    differenz: Decimal,
    datum: date,
    einst: AbschlussEinstellungen,
    kr: Kontenrahmen,
    text: str,
    von: str,
) -> Buchungssatz:
    gegen = kr.vortragskonto(konto, einst.debitoren, einst.kreditoren)
    soll, haben = (konto, gegen) if differenz > 0 else (gegen, konto)
    return Buchungssatz(
        datum=datum,
        soll_konto=soll,
        haben_konto=haben,
        betrag_netto=abs(differenz),
        buchungstext=f"{text} {konto}"[:60],
        beleg_nummer=f"EB-{datum.year}",
        status=BuchungStatus.GEPRUEFT,
        confidence=1.0,
        geprueft_von=von,
    )


def erfasse_eroeffnung(
    session: Session,
    jahr: int,
    konto: str,
    saldo: Decimal,
    von: str,
    einst: AbschlussEinstellungen,
) -> Buchungssatz | None:
    """Eröffnungssaldo eines Bestandskontos im ersten Jahr (Soll positiv).

    Setzt den EB-Wert: Ein zweiter Aufruf bucht nur den Unterschied.
    """
    pruefe_jahr_offen(session, jahr)
    if lade_jahresabschluss(session, jahr - 1) is not None:
        msg = f"Die EB-Werte {jahr} kommen aus dem Saldovortrag {jahr - 1}"
        raise AbschlussError(msg)
    kr = einst.lade_kontenrahmen()
    art = kr.art(konto, einst.gewinnermittlung)
    if kr.ist_saldenvortrag(konto) or art in (Kontenart.ERFOLG, Kontenart.VORTRAG):
        raise AbschlussError(f"Konto {konto} ist kein Bestandskonto")
    differenz = saldo - eroeffnungssalden(session, jahr, kr).get(konto, NULL)
    if differenz == 0:
        return None
    b = _eb_buchung(
        konto, differenz, date(jahr, 1, 1), einst, kr, "Eröffnungssaldo", von
    )
    speichere_buchung(session, b)
    protokolliere(
        session, jahr, "eroeffnung", von, None, {"konto": konto, "saldo": saldo}
    )
    session.flush()
    return b


def trage_vor(session: Session, k: Abschlusskontext, von: str) -> Vortrag:
    """Prüfen, EB-Buchungen ins Folgejahr, Jahr sperren, protokollieren."""
    jahr, einst, kr = k.jahr, k.einstellungen, k.kontenrahmen
    if ist_gesperrt(session, jahr):
        raise AbschlussError(f"Geschäftsjahr {jahr} ist schon abgeschlossen")
    if ist_gesperrt(session, jahr + 1):
        raise AbschlussError(f"Das Folgejahr {jahr + 1} ist gesperrt")
    befunde = pruefe_abschluss(k)
    if blockiert(befunde):
        raise AbschlussGesperrtError(befunde)
    ziel = schlusssalden(session, jahr, einst, kr)
    vorhanden = eroeffnungssalden(session, jahr + 1, kr)
    ergebnis = k.susa.ergebnis
    vortrag = Vortrag(jahr, ziel, ergebnis, befunde=befunde)
    for konto in sorted(set(ziel) | set(vorhanden), key=lambda x: (len(x), x)):
        differenz = ziel.get(konto, NULL) - vorhanden.get(konto, NULL)
        if differenz == 0:
            continue
        b = _eb_buchung(
            konto,
            differenz,
            date(jahr + 1, 1, 1),
            einst,
            kr,
            f"Saldovortrag {jahr}",
            von,
        )
        speichere_buchung(session, b)
        vortrag.buchungen.append(b)
    session.flush()
    setze_jahresabschluss(
        session,
        Jahresabschluss(
            jahr=jahr,
            gesperrt=True,
            gewinnermittlung=einst.gewinnermittlung,
            ergebnis=ergebnis,
            abgeschlossen_am=datetime.now(),
            von=von,
        ),
    )
    protokolliere(
        session,
        jahr,
        "abgeschlossen",
        von,
        None,
        {
            "ergebnis": betrag_de(ergebnis),
            "gewinnermittlung": einst.gewinnermittlung,
            "schlusssalden": hash_von({k: str(v) for k, v in ziel.items()}),
            "eb_buchungen": len(vortrag.buchungen),
            "korrektur": bool(vorhanden),
        },
    )
    return vortrag


def oeffne(session: Session, jahr: int, von: str, grund: str) -> None:
    """Hebt die Sperre auf — nur mit Grund und nur, wenn das Folgejahr offen ist."""
    if not grund.strip():
        raise AbschlussError("Grund für das Öffnen fehlt")
    abschluss = lade_jahresabschluss(session, jahr)
    if abschluss is None or not abschluss.gesperrt:
        raise AbschlussError(f"Geschäftsjahr {jahr} ist nicht abgeschlossen")
    if ist_gesperrt(session, jahr + 1):
        raise AbschlussError(f"Erst {jahr + 1} öffnen — es baut auf {jahr} auf")
    setze_jahresabschluss(session, abschluss.model_copy(update={"gesperrt": False}))
    protokolliere(session, jahr, "geoeffnet", von, grund.strip())
