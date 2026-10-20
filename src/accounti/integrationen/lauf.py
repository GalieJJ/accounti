"""Importlauf: Bericht lesen → archivieren → buchen → Auszahlung abgleichen.

Ein Lauf ist idempotent: Derselbe Bericht wird am Datei-Hash und an der
Abrechnungsnummer erkannt und nicht zweimal gebucht; PayPal-Zeilen eines überlappenden
Exports erkennt der Transaktionscode. Buchung und Abgleich passieren im selben Lauf,
damit ``classify`` die Auszahlung nicht vorher per Regel als Erlös bucht.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.belege.archiv import BelegArchiv
from accounti.belege.kanaele import RohBeleg
from accounti.belege.pipeline import Erkenner, nimm_auf
from accounti.db.repo_integrationen import (
    abrechnung_vorhanden,
    lade_abrechnungen,
    speichere_abrechnung,
    transaktionen_zu_schluesseln,
    vorhandene_referenzen,
)
from accounti.db.repository import speichere_buchung, speichere_transaktion
from accounti.importers.marktplatz import MARKTPLATZ_IMPORTER
from accounti.integrationen.auszahlung import (
    Abgleich,
    gleiche_auszahlungen_ab,
    status_von,
)
from accounti.integrationen.buchung import (
    ANZEIGE,
    Buchungskontext,
    buche_abrechnung,
    ergaenze_auszahlung,
)
from accounti.integrationen.einstellungen import Kontext
from accounti.models import (
    Beleg,
    Belegart,
    BelegStatus,
    Eingangsergebnis,
    Transaktion,
    TransaktionQuelle,
)
from accounti.models.integrationen import (
    Abrechnung,
    Laenderangabe,
    Marktplatzposten,
    Postenart,
)
from accounti.steuer.eu_steuersaetze import EU_STEUERSAETZE, ist_eu_land
from accounti.steuer.umsatzsteuer import UStBerechner

__all__ = ["IntegrationError", "Importergebnis", "Kontext", "importiere"]

NULL = Decimal("0")


class IntegrationError(RuntimeError):
    """Der Import ist so nicht möglich (unbekannter Marktplatz, Widersprüche)."""


@dataclass
class Importergebnis:
    abrechnung: Abrechnung
    neu: bool
    buchungen: int = 0
    umsaetze: int = 0
    abgleich: list[Abgleich] = field(default_factory=list)


def _erkenner(markt: str, abrechnungen: list[Abrechnung]) -> Erkenner:
    nummern = ", ".join(a.nummer for a in abrechnungen)
    bis = max(a.bis for a in abrechnungen)

    def erkenne(_roh: RohBeleg, beleg: Beleg) -> Beleg:
        return beleg.model_copy(
            update={
                "belegart": Belegart.SONSTIGES,
                "status": BelegStatus.ERFASST,
                "belegnummer": f"{ANZEIGE.get(markt, markt)} {nummern}"[:100],
                "belegdatum": bis,
                "lieferant_name": ANZEIGE.get(markt, markt),
                "confidence": 1.0,
            }
        )

    return erkenne


def eu_fernverkaeufe(
    session: Session, firmen_land: str, sonstige: dict[int, Decimal] | None = None
) -> dict[int, Decimal]:
    """EU-Fernverkäufe an Privatkunden (netto zum Inlandssatz) je Kalenderjahr.

    Grundlage der Lieferschwelle (§ 3c Abs. 4 UStG), solange keine OSS-Registrierung
    besteht — dann werden diese Erlöse mit dem Inlandssatz gebucht. Gezählt wird jeder
    Posten in seinem Jahr (nicht im Jahr der Abrechnung), dazu ``sonstige``
    (``integrationen.eu_fernverkaeufe_sonstige``).
    """
    berechner = UStBerechner(firmen_land=firmen_land)
    satz = EU_STEUERSAETZE[firmen_land].normal
    summen: dict[int, Decimal] = defaultdict(lambda: NULL)
    for jahr, betrag in (sonstige or {}).items():
        summen[jahr] += betrag
    for a in lade_abrechnungen(session):
        for p in a.posten:
            land = p.bestimmungsland
            if (
                p.art in (Postenart.ERLOES, Postenart.ERSTATTUNG)
                and land
                and land != firmen_land
                and ist_eu_land(land)
                and not p.kaeufer_ust_id
            ):
                betrag = p.betrag
                if a.waehrung != "EUR" and a.kurs:
                    betrag = betrag / a.kurs
                netto = berechner.brutto_zu_netto(abs(betrag), satz)
                summen[p.datum.year] += netto if betrag > 0 else -netto
    return dict(summen)


def _paypal_umsaetze(
    session: Session, a: Abrechnung, konto: str
) -> tuple[dict[str, UUID], int]:
    """Jede saldenwirksame EUR-Zeile wird ein Umsatz auf dem PayPal-Konto."""
    gruppen: dict[str, list[Marktplatzposten]] = defaultdict(list)
    for p in a.posten:
        if p.referenz and p.waehrung == "EUR" and p.art is not Postenart.UMRECHNUNG:
            gruppen[p.referenz].append(p)
    schluessel = {
        r: hashlib.sha256(f"paypal|{r}".encode()).hexdigest() for r in gruppen
    }
    vorhanden = transaktionen_zu_schluesseln(session, set(schluessel.values()))
    ids: dict[str, UUID] = {}
    neu = 0
    for referenz, posten in gruppen.items():
        if schluessel[referenz] in vorhanden:
            ids[referenz] = vorhanden[schluessel[referenz]]
            continue
        erster = posten[0]
        tx = Transaktion(
            datum=erster.datum,
            betrag=sum((p.betrag for p in posten), NULL),
            verwendungszweck=erster.beschreibung[:500] or f"PayPal {referenz}",
            gegenkonto_name=erster.gegenpartei,
            quelle=TransaktionQuelle.PAYPAL,
            quelle_referenz=referenz,
            rohtext=f"PayPal {referenz}: {erster.beschreibung}"[:2000],
            sachkonto=konto,
            dublettenschluessel=schluessel[referenz],
        )
        speichere_transaktion(session, tx)
        ids[referenz] = tx.id
        neu += 1
    session.flush()
    return ids, neu


def importiere(
    session: Session,
    archiv: BelegArchiv,
    kontext: Kontext,
    markt: str,
    inhalt: bytes,
    dateiname: str,
    laender: dict[str, Laenderangabe] | None = None,
    kurs: Decimal | None = None,
    auszahlung: Decimal | None = None,
) -> list[Importergebnis]:
    """Liest einen Marktplatzbericht, bucht jede neue Abrechnung und gleicht ab."""
    importer = MARKTPLATZ_IMPORTER.get(markt)
    if importer is None:
        bekannt = ", ".join(sorted(MARKTPLATZ_IMPORTER))
        raise IntegrationError(f"Marktplatz '{markt}' unbekannt (bekannt: {bekannt})")
    abrechnungen = importer.lies(inhalt, dateiname, laender)
    if auszahlung is not None and len(abrechnungen) != 1:
        msg = "--auszahlung geht nur bei einer Auszahlung je Datei"
        raise IntegrationError(msg)
    ohne_kurs = [
        a
        for a in abrechnungen
        if a.waehrung != "EUR"
        and kurs is None
        and not abrechnung_vorhanden(session, markt, a.nummer)
    ]
    if ohne_kurs:
        # vor dem Archivieren abbrechen: eine gespeicherte Abrechnung ohne Kurs
        # ließe sich nicht mehr buchen
        nummern = ", ".join(f"{a.nummer} ({a.waehrung})" for a in ohne_kurs)
        msg = (
            f"Abrechnung {nummern} in Fremdwährung: ohne Kurs (--kurs, Einheiten je "
            "1 EUR) wird nichts importiert"
        )
        raise IntegrationError(msg)

    eingang = nimm_auf(
        session,
        archiv,
        RohBeleg(
            dateiname=dateiname,
            inhalt=inhalt,
            kanal="marktplatz",
            herkunft=f"marktplatz:{markt}",
        ),
        erkenner=_erkenner(markt, abrechnungen),
    )
    beleg_id = eingang.beleg_id
    konten = kontext.einstellungen.marktplatz(markt)
    ergebnisse = []
    for a in abrechnungen:
        if eingang.ergebnis is Eingangsergebnis.DUBLETTE or abrechnung_vorhanden(
            session, markt, a.nummer
        ):
            ergebnisse.append(Importergebnis(a, neu=False))
            continue
        a.beleg_id = beleg_id
        a.kurs = kurs
        if auszahlung is not None and a.auszahlung is None:
            a.auszahlung = auszahlung
        umsaetze: dict[str, UUID] = {}
        neue_umsaetze = 0
        if markt == "paypal":
            schon_da = vorhandene_referenzen(session, "paypal")
            a.posten = [p for p in a.posten if p.referenz not in schon_da]
            umsaetze, neue_umsaetze = _paypal_umsaetze(
                session, a, konten.verrechnungskonto
            )
        ergaenze_auszahlung(a)
        buchungskontext = Buchungskontext(
            einstellungen=kontext.einstellungen,
            oss_registriert=kontext.oss_registriert,
            firmen_land=kontext.firmen_land,
            eu_b2c_bisher=(
                {}
                if kontext.oss_registriert
                else eu_fernverkaeufe(
                    session,
                    kontext.firmen_land,
                    kontext.einstellungen.eu_fernverkaeufe_sonstige,
                )
            ),
        )
        gebucht = buche_abrechnung(a, buchungskontext, umsaetze)
        a.befunde.extend(gebucht.befunde)
        a.status = status_von(a)
        speichere_abrechnung(session, a)
        for b in gebucht.buchungen:
            speichere_buchung(session, b)
        session.flush()
        abgleich = gleiche_auszahlungen_ab(session, kontext, [a])
        ergebnisse.append(
            Importergebnis(
                a,
                neu=True,
                buchungen=len(gebucht.buchungen),
                umsaetze=neue_umsaetze,
                abgleich=abgleich,
            )
        )
    return ergebnisse
