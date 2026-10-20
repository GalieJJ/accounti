"""Importlauf: Bericht lesen → archivieren → buchen → Auszahlung abgleichen.

Ein Lauf ist idempotent: Derselbe Bericht wird am Datei-Hash und an der
Abrechnungsnummer erkannt und nicht zweimal gebucht; PayPal-Zeilen eines überlappenden
Exports erkennt der Transaktionscode. Buchung und Abgleich passieren im selben Lauf,
damit ``classify`` die Auszahlung nicht vorher per Regel als Erlös bucht.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.belege.archiv import BelegArchiv
from accounti.belege.kanaele import RohBeleg
from accounti.belege.pipeline import Erkenner, nimm_auf
from accounti.db.repo_integrationen import (
    abrechnung_vorhanden,
    aktualisiere_abrechnung,
    lade_abrechnung_nach_nummer,
    lade_abrechnungen,
    speichere_abrechnung,
    transaktionen_zu_schluesseln,
    vorhandene_referenzen,
)
from accounti.db.repository import speichere_buchung, speichere_transaktion
from accounti.importers.marktplatz import MARKTPLATZ_IMPORTER
from accounti.integrationen.auszahlung import (
    ABGLEICHSBEFUNDE,
    Abgleich,
    gleiche_auszahlungen_ab,
    status_von,
)
from accounti.integrationen.buchung import (
    ANZEIGE,
    Buchungskontext,
    buche_abrechnung,
    ergaenze_auszahlung,
    setze_auszahlung_eur,
    summenprobe,
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
    Befund,
    Laenderangabe,
    Marktplatzposten,
    Postenart,
    Schweregrad,
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
    nachgetragen: int = 0  # Posten, die eine bekannte Abrechnung dazubekam
    buchungen: int = 0
    umsaetze: int = 0
    abgleich: list[Abgleich] = field(default_factory=list)


def _erkenner(markt: str, abrechnungen: list[Abrechnung]) -> Erkenner:
    nummern = ", ".join(a.nummer for a in abrechnungen)
    bis = max(a.bis for a in abrechnungen)

    def erkenne(roh: RohBeleg, beleg: Beleg) -> Beleg:
        # Ein zweiter Bericht derselben Abrechnung (anderer Inhalt) ist ein eigener
        # Beleg, keine Dublette: der Inhalts-Hash macht die Belegnummer eindeutig
        kurz = hashlib.sha256(roh.inhalt).hexdigest()[:8]
        nummer = f"{ANZEIGE.get(markt, markt)} {nummern}"[:90]
        return beleg.model_copy(
            update={
                "belegart": Belegart.SONSTIGES,
                "status": BelegStatus.ERFASST,
                "belegnummer": f"{nummer} #{kurz}",
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


def _fingerabdruck(p: Marktplatzposten) -> tuple[object, ...]:
    """Was einen Posten ausmacht — ohne Zeilennummer, die je Bericht anders ist."""
    return (
        p.art,
        p.datum,
        p.betrag,
        p.waehrung,
        p.bestellnummer,
        p.gebuehrenart,
        p.beschreibung,
        p.artikel,
        p.referenz,
    )


def neue_posten(
    vorhanden: list[Marktplatzposten], bericht: list[Marktplatzposten]
) -> list[Marktplatzposten]:
    """Posten des Berichts, die die Abrechnung noch nicht hat (als Multimenge).

    Der aus der Summe gebildete Auszahlungsposten (``nr`` 0) zählt nicht mit.
    """
    bekannt = Counter(_fingerabdruck(p) for p in vorhanden if p.nr != 0)
    ergebnis = []
    for p in bericht:
        f = _fingerabdruck(p)
        if bekannt[f]:
            bekannt[f] -= 1
        elif p.nr != 0:
            ergebnis.append(p)
    return ergebnis


def _buchungskontext(session: Session, kontext: Kontext) -> Buchungskontext:
    return Buchungskontext(
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


def _freie_nummer(session: Session, markt: str, nummer: str) -> str:
    """PayPal: zweiter Export desselben Zeitraums → ``… (2)``."""
    if not abrechnung_vorhanden(session, markt, nummer):
        return nummer
    n = 2
    while abrechnung_vorhanden(session, markt, f"{nummer} ({n})"):
        n += 1
    return f"{nummer} ({n})"


def _nachtrag(
    session: Session,
    kontext: Kontext,
    alt: Abrechnung,
    bericht: Abrechnung,
    beleg_id: UUID | None,
    auszahlung: Decimal | None,
) -> Importergebnis:
    """Ergänzt eine bekannte Abrechnung um die Posten, die sie noch nicht hat.

    Eine Auszahlung kann über zwei Berichte verteilt sein (eBay, Shopify mit
    Monatsberichten), und der Hinweis „nach der Auszahlung erneut importieren“ führt
    zu genau diesem Fall. Neue Posten werden gebucht (mit dem Beleg des neuen
    Berichts), ein aus der Summe gebildeter, noch nicht abgeglichener
    Auszahlungsposten wird ersetzt, Summenprobe und Bankabgleich laufen über die
    ganze Abrechnung. Ist die gebildete Auszahlung schon gegen die Bank abgeglichen,
    gilt ihr Betrag als bestätigt — passen neue Posten nicht dazu, ist das ein
    Fehler-Befund.
    """
    neue = neue_posten(alt.posten, bericht.posten)
    if not neue:
        return Importergebnis(alt, neu=False)
    a = alt.model_copy(deep=True)
    gebildet = [p for p in a.posten if p.art is Postenart.AUSZAHLUNG and p.nr == 0]
    ersetzt = {p.id for p in gebildet if p.bank_transaktion_id is None}
    bestaetigt = [p for p in gebildet if p.bank_transaktion_id is not None]
    a.posten = [p for p in a.posten if p.id not in ersetzt] + neue
    a.von, a.bis = min(a.von, bericht.von), max(a.bis, bericht.bis)
    a.auszahlungsdatum = a.auszahlungsdatum or bericht.auszahlungsdatum
    zeilen = [p for p in a.posten if p.art is Postenart.AUSZAHLUNG and p.nr != 0]
    if zeilen:
        a.auszahlung = -sum((p.betrag for p in zeilen), NULL)
    elif a.auszahlung is None and auszahlung is not None:
        a.auszahlung = auszahlung
    elif a.auszahlung is None and bestaetigt:
        a.auszahlung = -sum((p.betrag for p in bestaetigt), NULL)
    a.vollstaendig = bool(zeilen) or (alt.vollstaendig and bericht.vollstaendig)
    ergaenze_auszahlung(a)
    probe = summenprobe(a)

    # überholte Befunde erledigen: alte Summenprobe, „Auszahlung folgt“, Abgleich
    # des ersetzten Auszahlungspostens
    probe_texte = {(b.code, b.text) for b in probe}
    for b in a.offene_befunde:
        if (
            (b.code == "summe_abweichung" and (b.code, b.text) not in probe_texte)
            or (b.code == "auszahlung_folgt" and a.vollstaendig)
            or (ersetzt and b.code in ABGLEICHSBEFUNDE and b.posten_nr == 0)
        ):
            b.erledigt = True
    offen_texte = {(b.code, b.text) for b in a.offene_befunde}
    a.befunde.extend(b for b in probe if (b.code, b.text) not in offen_texte)
    a.befunde.append(
        Befund(
            code="nachtrag",
            schweregrad=Schweregrad.HINWEIS,
            text=f"{len(neue)} Posten aus {bericht.dateiname} nachgetragen",
        )
    )

    teil = a.model_copy(
        update={
            "posten": neue,
            "befunde": list(a.offene_befunde),
            "beleg_id": beleg_id,
            "auszahlung": None,
        }
    )
    gebucht = buche_abrechnung(teil, _buchungskontext(session, kontext))
    a.befunde.extend(gebucht.befunde)
    setze_auszahlung_eur(a)
    a.status = status_von(a)
    aktualisiere_abrechnung(session, a)
    for buchung in gebucht.buchungen:
        speichere_buchung(session, buchung)
    session.flush()
    abgleich = gleiche_auszahlungen_ab(session, kontext, [a])
    return Importergebnis(
        a,
        neu=False,
        nachgetragen=len(neue),
        buchungen=len(gebucht.buchungen),
        abgleich=abgleich,
    )


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
    """Liest einen Marktplatzbericht, bucht neue Abrechnungen und Nachträge zu
    bekannten, und gleicht ab."""
    importer = MARKTPLATZ_IMPORTER.get(markt)
    if importer is None:
        bekannt = ", ".join(sorted(MARKTPLATZ_IMPORTER))
        raise IntegrationError(f"Marktplatz '{markt}' unbekannt (bekannt: {bekannt})")
    abrechnungen = importer.lies(inhalt, dateiname, laender)
    if auszahlung is not None and len(abrechnungen) != 1:
        msg = "--auszahlung geht nur bei einer Auszahlung je Datei"
        raise IntegrationError(msg)
    vorhandene: dict[str, Abrechnung] = {}
    if markt != "paypal":  # PayPal: Zeilen über den Transaktionscode, nicht die Nummer
        for a in abrechnungen:
            alt = lade_abrechnung_nach_nummer(session, markt, a.nummer)
            if alt is not None:
                vorhandene[a.nummer] = alt
    _pruefe_kurs(abrechnungen, vorhandene, kurs)

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
        if eingang.ergebnis is Eingangsergebnis.DUBLETTE:
            ergebnisse.append(Importergebnis(a, neu=False))
            continue
        if a.nummer in vorhandene:
            ergebnisse.append(
                _nachtrag(
                    session, kontext, vorhandene[a.nummer], a, beleg_id, auszahlung
                )
            )
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
            if not a.posten:
                ergebnisse.append(Importergebnis(a, neu=False))
                continue
            a.nummer = _freie_nummer(session, markt, a.nummer)
            umsaetze, neue_umsaetze = _paypal_umsaetze(
                session, a, konten.verrechnungskonto
            )
        ergaenze_auszahlung(a)
        gebucht = buche_abrechnung(a, _buchungskontext(session, kontext), umsaetze)
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


def _pruefe_kurs(
    abrechnungen: list[Abrechnung],
    vorhandene: dict[str, Abrechnung],
    kurs: Decimal | None,
) -> None:
    """Vor dem Archivieren: Fremdwährung braucht einen Kurs, Nachträge denselben.

    Eine gespeicherte Abrechnung ohne Kurs ließe sich nicht mehr buchen.
    """
    ohne_kurs = []
    for a in abrechnungen:
        if a.waehrung == "EUR":
            continue
        alt = vorhandene.get(a.nummer)
        if alt is None and kurs is None:
            ohne_kurs.append(a)
        elif alt is not None and kurs is not None and alt.kurs != kurs:
            msg = (
                f"Abrechnung {a.nummer} ist mit dem Kurs {alt.kurs} gebucht — "
                f"Nachträge nicht mit {kurs}"
            )
            raise IntegrationError(msg)
    if ohne_kurs:
        nummern = ", ".join(f"{a.nummer} ({a.waehrung})" for a in ohne_kurs)
        msg = (
            f"Abrechnung {nummern} in Fremdwährung: ohne Kurs (--kurs, Einheiten je "
            "1 EUR) wird nichts importiert"
        )
        raise IntegrationError(msg)
