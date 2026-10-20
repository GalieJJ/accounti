"""Zahllast als offener Posten gegenüber dem Finanzamt.

Nach einer erfolgreichen echten Abgabe wird die Vorauszahlung (Kz 83) gebucht und als
offener Posten beim Kreditor „Finanzamt“ geführt — fällig zur Abgabefrist (§ 18 Abs. 1
Satz 4 UStG: Vorauszahlung am 10. Tag nach Ablauf des Zeitraums). So taucht sie in
OPOS-Liste und Fälligkeitsstaffel auf, und die Zahlung oder die Lastschrift des
Finanzamts gleicht sie über den Kontoumsatz aus (``opos zuordnen``).

- Beleg: Eigenbeleg mit dem übermittelten Datensatz aus dem Archiv.
- Buchung: Umsatzsteuer-Vorauszahlungen (SKR03 1780, SKR04 3820) an Kreditor; die
  Sondervorauszahlung auf 1781 bzw. 3830. Eine Erstattung bucht umgekehrt und ist ein
  negativer Posten.
- Berichtigung: gebucht wird nur die Differenz zur zuletzt abgegebenen Anmeldung.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from accounti.db.repo_elster import lade_uebermittlungen
from accounti.db.repository import (
    lade_belege,
    speichere_beleg,
    speichere_buchung,
    speichere_posten,
)
from accounti.elster.konfiguration import ElsterEinstellungen
from accounti.elster.steuernummer import finanzamtsnummer
from accounti.konfiguration import Buchhaltung
from accounti.kontakte.dienst import Partnerdaten, kontakt_fuer
from accounti.models import (
    Beleg,
    Belegart,
    Belegrichtung,
    BelegStatus,
    Buchungssatz,
    BuchungStatus,
    Kontakt,
    OffenerPosten,
    PostenRichtung,
)
from accounti.models.elster import Meldeart, Modus, Uebermittlung
from accounti.steuer.fristen import sondervorauszahlung_frist, ustva_frist
from accounti.steuer.zeitraum import Zeitraum

KANAL = "elster"
KONTEN = {
    # Kontenrahmen: (Umsatzsteuer-Vorauszahlungen, Umsatzsteuer-Vorauszahlung 1/11)
    "SKR03": ("1780", "1781"),
    "SKR04": ("3820", "3830"),
}


@dataclass(frozen=True)
class Zahllastbuchung:
    kontakt: Kontakt
    beleg: Beleg
    buchung: Buchungssatz
    posten: OffenerPosten
    betrag: Decimal
    art: Meldeart = Meldeart.USTVA


def finanzamt(
    session: Session,
    buchhaltung: Buchhaltung,
    einstellungen: ElsterEinstellungen,
    steuernummer: str,
) -> Kontakt:
    """Der Kreditor „Finanzamt“ — gefunden über IBAN oder Name, sonst angelegt."""
    name = einstellungen.finanzamt.name or f"Finanzamt {finanzamtsnummer(steuernummer)}"
    treffer = kontakt_fuer(
        session,
        buchhaltung,
        "kreditor",
        Partnerdaten(name=name, iban=einstellungen.finanzamt.iban),
        neu_pruefen=False,
        anlass="Umsatzsteuer-Voranmeldung",
    )
    return treffer.kontakt


def _konto(
    buchhaltung: Buchhaltung, einstellungen: ElsterEinstellungen, art: Meldeart
) -> str:
    standard = KONTEN.get(buchhaltung.kontenrahmen.upper(), KONTEN["SKR03"])
    if art is Meldeart.DAUERFRIST:
        return einstellungen.konto_sondervorauszahlung or standard[1]
    return einstellungen.konto_vorauszahlung or standard[0]


def _faellig(u: Uebermittlung, einstellungen: ElsterEinstellungen) -> date:
    if u.art is Meldeart.DAUERFRIST:
        return sondervorauszahlung_frist(
            int(u.zeitraum), einstellungen.bundesland
        ).faellig_am
    return ustva_frist(
        Zeitraum.lies(u.zeitraum),
        einstellungen.dauerfristverlaengerung,
        einstellungen.bundesland,
    ).faellig_am


def buche_zahllast(
    session: Session,
    u: Uebermittlung,
    *,
    buchhaltung: Buchhaltung,
    einstellungen: ElsterEinstellungen,
    steuernummer: str,
) -> Zahllastbuchung | None:
    """Bucht Zahllast oder Sondervorauszahlung einer erfolgreichen Abgabe — einmal."""
    if u.modus is not Modus.ECHT or not u.erfolgreich or u.betrag is None:
        return None
    herkunft = f"Übermittlungsprotokoll Nr. {u.nr}"
    if any(b.kanal == KANAL and b.herkunft == herkunft for b in lade_belege(session)):
        return None  # schon gebucht
    frueher = [
        x
        for x in lade_uebermittlungen(session, u.art, u.zeitraum, Modus.ECHT)
        if x.erfolgreich and x.nr < u.nr and x.betrag is not None
    ]
    bisher = frueher[-1].betrag if frueher and frueher[-1].betrag is not None else 0
    betrag = u.betrag - bisher
    if betrag == 0:
        return None

    kontakt = finanzamt(session, buchhaltung, einstellungen, steuernummer)
    kreditor = kontakt.kreditor_konto
    assert kreditor is not None  # kontakt_fuer vergibt das Personenkonto
    name = "UStVA" if u.art is Meldeart.USTVA else "Sondervorauszahlung"
    belegnummer = f"{name} {u.zeitraum}"
    if u.berichtigt or frueher:
        belegnummer += f" berichtigt (Nr. {u.nr})"
    belegdatum = u.zeitpunkt.date()
    faellig = _faellig(u, einstellungen)
    beleg = Beleg(
        belegart=Belegart.SONSTIGES,
        richtung=Belegrichtung.EINGANG,
        belegnummer=belegnummer,
        belegdatum=belegdatum,
        kontakt_id=kontakt.id,
        lieferant_name=kontakt.name,
        netto=betrag,
        steuer=Decimal("0"),
        brutto=betrag,
        zahlungsziel=faellig,
        datei_hash=u.datensatz_hash,
        dateiname=f"{u.art.value.lower()}-{u.zeitraum}-{u.nr}.xml",
        kanal=KANAL,
        herkunft=herkunft,
        aufbewahren_bis=u.aufbewahren_bis,
        status=BelegStatus.ERFASST,
        confidence=1.0,
    )
    speichere_beleg(session, beleg)
    sachkonto = _konto(buchhaltung, einstellungen, u.art)
    soll, haben = (sachkonto, kreditor) if betrag > 0 else (kreditor, sachkonto)
    buchung = Buchungssatz(
        beleg_id=beleg.id,
        datum=belegdatum,
        soll_konto=soll,
        haben_konto=haben,
        betrag_netto=abs(betrag),
        buchungstext=f"{belegnummer} {kontakt.name}"[:60],
        beleg_nummer=belegnummer[:36],
        status=BuchungStatus.AUTO_GEBUCHT,
        confidence=1.0,
    )
    speichere_buchung(session, buchung)
    posten = OffenerPosten(
        kontakt_id=kontakt.id,
        beleg_id=beleg.id,
        richtung=PostenRichtung.VERBINDLICHKEIT,
        belegnummer=belegnummer,
        belegdatum=belegdatum,
        betrag=betrag,
        restbetrag=betrag,
        faellig_am=faellig,
    )
    speichere_posten(session, posten)
    return Zahllastbuchung(kontakt, beleg, buchung, posten, betrag, u.art)
