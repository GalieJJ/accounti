"""Importlauf: Bericht lesen → archivieren → buchen → Auszahlung abgleichen.

Ein Lauf ist idempotent: Derselbe Bericht wird am Datei-Hash und an der
Abrechnungsnummer erkannt und nicht zweimal gebucht; PayPal-Zeilen eines überlappenden
Exports erkennt der Transaktionscode. Buchung und Abgleich passieren im selben Lauf,
damit ``classify`` die Auszahlung nicht vorher per Regel als Erlös bucht.

Liegen zu buchende Posten in einem abgeschlossenen Zeitraum (Jahr oder
festgeschriebener Monat), wird vor dem Ablegen abgebrochen — oder mit
``buchungsdatum`` (``offen`` oder ein Tag) in einen offenen Zeitraum desselben
Geschäftsjahrs gebucht, das Belegdatum bleibt. Scheitert der Lauf nach dem Ablegen,
wird die eben abgelegte Datei wieder entfernt (die Datenbank rollt zurück, kein Beleg
verweist auf sie).
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import Connection
from sqlalchemy.orm import Session

from accounti.belege.archiv import BelegArchiv
from accounti.belege.kanaele import RohBeleg
from accounti.belege.pipeline import Erkenner, nimm_auf
from accounti.db.repo_integrationen import (
    abrechnung_vorhanden,
    aktualisiere_abrechnung,
    erloes_codes,
    lade_abrechnung_nach_nummer,
    lade_abrechnungen,
    speichere_abrechnung,
    transaktionen_zu_schluesseln,
    vorhandene_referenzen,
)
from accounti.db.repository import speichere_buchung, speichere_transaktion
from accounti.db.tabellen_abschluss import jahressperre
from accounti.db.tabellen_pruefung import erster_offener_tag, sperrfehler
from accounti.importers.marktplatz import MARKTPLATZ_IMPORTER
from accounti.importers.paypal import FruehereUmsaetze, PaypalImporter
from accounti.integrationen.auszahlung import (
    ABGLEICHSBEFUNDE,
    Abgleich,
    gleiche_auszahlungen_ab,
    status_von,
)
from accounti.integrationen.buchung import (
    ANZEIGE,
    Buchungsergebnis,
    Buchungskontext,
    buche_abrechnung,
    ergaenze_auszahlung,
    eur_text,
    setze_auszahlung_eur,
    summenprobe,
)
from accounti.integrationen.einstellungen import Kontext
from accounti.models import (
    Beleg,
    Belegart,
    BelegStatus,
    Buchungssatz,
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
from accounti.steuer.eu_steuersaetze import ist_eu_land, steuersatz_fuer_land
from accounti.steuer.umsatzsteuer import UStBerechner

__all__ = ["IntegrationError", "Importergebnis", "Kontext", "importiere"]

NULL = Decimal("0")
# Buchungsdatum für Posten in abgeschlossenen Zeiträumen: erster offener Tag oder fest
Buchungsdatum = Literal["offen"] | date


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
    # Bericht widerspricht der bekannten Abrechnung: nichts nachgetragen
    widerspruch: Befund | None = None


def _grund(session: Session, gebucht: Buchungsergebnis, b: Buchungssatz) -> None:
    """Herkunft der Marktplatz-Buchung (Baustein 10b)."""
    from accounti.db.repo_kontierung import speichere_kontierungsgrund

    speichere_kontierungsgrund(
        session,
        b.id,
        quelle="marktplatz",
        begruendung=gebucht.gruende.get(b.id, b.buchungstext),
    )


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
                satz = steuersatz_fuer_land(firmen_land, p.datum).normal
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
    """Was einen Posten ausmacht — ohne Zeilennummer, die je Bericht anders ist.

    Ohne Freitext: Beschreibung, Typbezeichnung und Gebührenspalte hängen von
    Sprache und Spaltenauswahl des Exports ab (eBay lässt die Spalten konfigurieren).
    Gleiche Posten einer Bestellung zählt ``neue_posten`` als Multimenge.
    """
    return (
        p.art,
        p.datum,
        p.betrag,
        p.waehrung,
        p.bestellnummer,
        p.gebuehrenart,
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
        oss_am=kontext.oss_am,
        firmen_land=kontext.firmen_land,
        # Lieferschwelle: wer erst ab einem Quartal OSS-registriert ist, zählt die
        # Fernverkäufe davor (Periodenwert, Baustein 10c P4)
        eu_b2c_bisher=(
            {}
            if kontext.oss_immer
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
    buchungsdatum: Buchungsdatum | None = None,
    berichtsnummern: frozenset[tuple[str, str]] = frozenset(),
) -> Importergebnis:
    """Ergänzt eine bekannte Abrechnung um die Posten, die sie noch nicht hat.

    Eine Auszahlung kann über zwei Berichte verteilt sein (eBay, Shopify mit
    Monatsberichten), und der Hinweis „nach der Auszahlung erneut importieren“ führt
    zu genau diesem Fall. Neue Posten werden gebucht (mit dem Beleg des neuen
    Berichts), ein aus der Summe gebildeter, noch nicht abgeglichener
    Auszahlungsposten wird ersetzt, Summenprobe und Bankabgleich laufen über die
    ganze Abrechnung. Ist die gebildete Auszahlung schon gegen die Bank abgeglichen,
    gilt ihr Betrag als bestätigt — passen neue Posten nicht dazu, ist das ein
    Fehler-Befund. Bringt der Bericht eine weitere Auszahlungszeile, widerspricht
    er der Abrechnung: dann wird nichts nachgetragen (``auszahlung_doppelt``).
    """
    neue = neue_posten(alt.posten, bericht.posten)
    if not neue:
        return Importergebnis(alt, neu=False)
    widerspruch = _zweite_auszahlungszeile(alt, neue, bericht.dateiname)
    if widerspruch is not None:
        a = alt.model_copy(deep=True)
        a.befunde.append(widerspruch)
        a.status = status_von(a)
        aktualisiere_abrechnung(session, a)
        session.flush()
        return Importergebnis(a, neu=False, widerspruch=widerspruch)
    a = alt.model_copy(deep=True)
    # Befunde des Berichts zu den neuen Posten (z.B. Zeile rechnet nicht) gelten mit
    nummern = {p.nr for p in neue}
    a.befunde.extend(b for b in bericht.befunde if b.posten_nr in nummern)
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
    a.befunde.extend(_verschiebe(session, gebucht.buchungen, buchungsdatum))
    setze_auszahlung_eur(a)
    a.status = status_von(a)
    aktualisiere_abrechnung(session, a)
    for buchung in gebucht.buchungen:
        speichere_buchung(session, buchung)
        _grund(session, gebucht, buchung)
    session.flush()
    abgleich = gleiche_auszahlungen_ab(session, kontext, [a], berichtsnummern)
    return Importergebnis(
        a,
        neu=False,
        nachgetragen=len(neue),
        buchungen=len(gebucht.buchungen),
        abgleich=abgleich,
    )


def _zweite_auszahlungszeile(
    alt: Abrechnung, neue: list[Marktplatzposten], dateiname: str
) -> Befund | None:
    """Eine Auszahlungsnummer hat genau eine Auszahlungszeile.

    Bringt ein Bericht eine weitere (anderer Betrag oder anderes Datum), ist das ein
    Widerspruch — summiert ergäbe sie eine erfundene Auszahlung, gegen die doppelt
    nachgebuchte Posten die Summenprobe bestehen. Dann wird nichts nachgetragen.
    """
    bekannt = [p for p in alt.posten if p.art is Postenart.AUSZAHLUNG and p.nr != 0]
    zeilen = [p for p in neue if p.art is Postenart.AUSZAHLUNG]
    if not zeilen or (not bekannt and len(zeilen) == 1):
        return None

    def beschreibe(p: Marktplatzposten) -> str:
        return f"{eur_text(-p.betrag)} {p.waehrung} am {p.datum:%d.%m.%Y}"

    vorher = ", ".join(beschreibe(p) for p in bekannt) or "keine"
    return Befund(
        code="auszahlung_doppelt",
        schweregrad=Schweregrad.FEHLER,
        text=(
            f"{dateiname} enthält eine weitere Auszahlungszeile zu {alt.nummer} "
            f"({', '.join(beschreibe(p) for p in zeilen)}; bekannt: {vorher}) — "
            f"widerspricht der Abrechnung, aus {dateiname} wurde nichts "
            "nachgetragen; Bericht und Auszahlung prüfen"
        ),
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
    buchungsdatum: Buchungsdatum | None = None,
) -> list[Importergebnis]:
    """Liest einen Marktplatzbericht, bucht neue Abrechnungen und Nachträge zu
    bekannten, und gleicht ab. ``buchungsdatum``: Posten in abgeschlossenen
    Zeiträumen dorthin buchen (sonst Abbruch vor dem Ablegen)."""
    importer = MARKTPLATZ_IMPORTER.get(markt)
    if importer is None:
        bekannt = ", ".join(sorted(MARKTPLATZ_IMPORTER))
        raise IntegrationError(f"Marktplatz '{markt}' unbekannt (bekannt: {bekannt})")
    if isinstance(importer, PaypalImporter):
        # Rückzahlungen: ist die zugehörige Zahlung ein früher importierter Verkauf?
        frueher = FruehereUmsaetze(
            verkaeufe=frozenset(erloes_codes(session, markt)),
            alle=frozenset(vorhandene_referenzen(session, markt)),
        )
        abrechnungen = importer.lies(inhalt, dateiname, laender, frueher=frueher)
    else:
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
    _pruefe_sperre(session, markt, abrechnungen, vorhandene, buchungsdatum)

    datei_hash = hashlib.sha256(inhalt).hexdigest()
    schon_im_archiv = archiv.enthaelt(datei_hash)
    try:
        return _importiere(
            session,
            archiv,
            kontext,
            markt,
            inhalt,
            dateiname,
            abrechnungen,
            vorhandene,
            kurs,
            auszahlung,
            buchungsdatum,
        )
    except BaseException:
        if not schon_im_archiv:
            _verwirf_abgelegte(archiv, datei_hash)
        raise


def _importiere(
    session: Session,
    archiv: BelegArchiv,
    kontext: Kontext,
    markt: str,
    inhalt: bytes,
    dateiname: str,
    abrechnungen: list[Abrechnung],
    vorhandene: dict[str, Abrechnung],
    kurs: Decimal | None,
    auszahlung: Decimal | None,
    buchungsdatum: Buchungsdatum | None,
) -> list[Importergebnis]:
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
    # die Nummern aller Abrechnungen des Berichts zählen beim Abgleich schon, bevor
    # sie gespeichert sind: ein Umsatz mit einer davon gehört nicht zur ersten
    # (Nachprüfung 3 E, M2 — ein Transaktionsbericht mit mehreren Auszahlungen)
    berichtsnummern = frozenset((x.marktplatz, x.nummer) for x in abrechnungen)
    ergebnisse = []
    for a in abrechnungen:
        if eingang.ergebnis is Eingangsergebnis.DUBLETTE:
            ergebnisse.append(Importergebnis(a, neu=False))
            continue
        if a.nummer in vorhandene:
            ergebnisse.append(
                _nachtrag(
                    session,
                    kontext,
                    vorhandene[a.nummer],
                    a,
                    beleg_id,
                    auszahlung,
                    buchungsdatum,
                    berichtsnummern,
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
        if not any(w.strip() for w in konten.bank_stichworte):
            a.befunde.append(_ohne_stichworte(markt))
        a.befunde.extend(_verschiebe(session, gebucht.buchungen, buchungsdatum))
        a.status = status_von(a)
        speichere_abrechnung(session, a)
        for b in gebucht.buchungen:
            speichere_buchung(session, b)
            _grund(session, gebucht, b)
        session.flush()
        ergebnisse.append(
            Importergebnis(
                a,
                neu=True,
                buchungen=len(gebucht.buchungen),
                umsaetze=neue_umsaetze,
            )
        )
    # erst abgleichen, wenn alle Abrechnungen des Berichts gespeichert sind: sonst
    # nähme die erste einen Umsatz, der genauso der einzige Kandidat der zweiten ist
    # (Regel 5, Nachprüfung 5 E)
    neue = [e for e in ergebnisse if e.neu]
    if neue:
        abgleich = gleiche_auszahlungen_ab(
            session, kontext, [e.abrechnung for e in neue], berichtsnummern
        )
        for e in neue:
            e.abgleich = [x for x in abgleich if x.abrechnung.id == e.abrechnung.id]
    return ergebnisse


def _ohne_stichworte(markt: str) -> Befund:
    """WARNUNG: ohne ``bank_stichworte`` erkennt der Abgleich eine Auszahlung, deren
    Verwendungszweck die Nummer nicht nennt, in Fremdwährung gar nicht (in Euro nur
    am exakten Betrag) — und die Kontierung lässt sie nicht offen, sondern bucht sie
    nach den Regeln, der Erlös stünde doppelt (Nachprüfung 5 E, Grenze)."""
    return Befund(
        code="bank_stichworte_leer",
        schweregrad=Schweregrad.WARNUNG,
        text=(
            f"integrationen.marktplaetze.{markt}.bank_stichworte ist leer — eine "
            "Auszahlung ohne die Nummer im Verwendungszweck erkennt der Abgleich in "
            "Fremdwährung nicht, und die Kontierung bucht sie nach den Regeln (Erlös "
            "doppelt). Ein Stichwort des Bankeingangs eintragen; leer nur ohne "
            "Marktplatz-Import"
        ),
    )


def _zu_buchende_tage(
    session: Session,
    markt: str,
    abrechnungen: list[Abrechnung],
    vorhandene: dict[str, Abrechnung],
) -> set[date]:
    """Tage, an denen der Import buchen wird: die neuen Posten (Nachtrag: nur die
    fehlenden, PayPal: nur unbekannte Transaktionscodes; die Auszahlung bucht erst der
    Bankabgleich) und das Ende des Zeitraums (Sammelgebühren)."""
    paypal = markt == "paypal"
    schon_da = vorhandene_referenzen(session, "paypal") if paypal else set()
    tage: set[date] = set()
    for a in abrechnungen:
        alt = vorhandene.get(a.nummer)
        posten = neue_posten(alt.posten, a.posten) if alt is not None else a.posten
        posten = [
            p
            for p in posten
            if (paypal or p.art is not Postenart.AUSZAHLUNG)
            and not (paypal and p.referenz in schon_da)
        ]
        if posten:
            tage |= {p.datum for p in posten} | {a.bis}
    return tage


def _pruefe_sperre(
    session: Session,
    markt: str,
    abrechnungen: list[Abrechnung],
    vorhandene: dict[str, Abrechnung],
    buchungsdatum: Buchungsdatum | None,
) -> None:
    """Vor dem Ablegen: Posten in einem abgeschlossenen Zeitraum brechen ab — mit
    klarer Meldung statt eines Fehlers beim Schreiben (und einer verwaisten Datei);
    mit ``buchungsdatum`` muss jeder dieser Posten ein Ziel im selben Geschäftsjahr
    haben (``_zieltag``)."""
    verbindung = session.connection()
    if isinstance(buchungsdatum, date):
        fehler = sperrfehler(verbindung, buchungsdatum)
        if fehler is not None:
            msg = f"--buchungsdatum {buchungsdatum:%d.%m.%Y}: {fehler}"
            raise IntegrationError(msg)
    gesperrt: dict[str, str] = {}
    for tag in sorted(_zu_buchende_tage(session, markt, abrechnungen, vorhandene)):
        fehler = sperrfehler(verbindung, tag)
        if fehler is None:
            continue
        if buchungsdatum is not None:
            _zieltag(verbindung, tag, buchungsdatum)
        gesperrt.setdefault(f"{tag:%Y-%m}", str(fehler))
    if not gesperrt or buchungsdatum is not None:
        return
    monate = ", ".join(gesperrt)
    msg = (
        f"Der Bericht hat Posten in einem abgeschlossenen Zeitraum ({monate}: "
        f"{next(iter(gesperrt.values()))}) — nichts importiert. Entweder den "
        "Zeitraum öffnen (accounti periode oeffnen JJJJ-MM --grund …) oder mit "
        "--buchungsdatum offen (bzw. JJJJ-MM-TT) in einen offenen Zeitraum buchen; "
        "umsatzsteuerlich gehören die Umsätze trotzdem in ihren Monat (berichtigte "
        "Voranmeldung, § 18 Abs. 1 UStG)"
    )
    raise IntegrationError(msg)


def _verschiebe(
    session: Session,
    buchungen: list[Buchungssatz],
    buchungsdatum: Buchungsdatum | None,
) -> list[Befund]:
    """Buchungen in abgeschlossenen Zeiträumen auf das Buchungsdatum legen (wie
    ``opos verbuchen --buchungsdatum``); das Belegdatum bleibt am Beleg. Ein Befund
    sagt, dass accounti die Umsätze damit im Buchungsmonat zählt, obwohl sie
    umsatzsteuerlich in den Monat der Leistung gehören."""
    if buchungsdatum is None:
        return []
    verbindung = session.connection()
    monate: set[str] = set()
    tage: set[date] = set()
    for i, b in enumerate(buchungen):
        if sperrfehler(verbindung, b.datum) is None:
            continue
        tag = _zieltag(verbindung, b.datum, buchungsdatum)
        monate.add(f"{b.datum:%Y-%m}")
        tage.add(tag)
        buchungen[i] = b.model_copy(update={"datum": tag})
    if not monate:
        return []
    liste = ", ".join(sorted(monate))
    text = (
        f"Posten aus abgeschlossenem Zeitraum ({liste}) am "
        f"{', '.join(f'{t:%d.%m.%Y}' for t in sorted(tage))} gebucht (Belegdatum "
        "unverändert) — accounti zählt sie damit in der Voranmeldung (und "
        "OSS-Meldung) des Buchungsmonats; umsatzsteuerlich gehören sie in den Monat "
        "der Leistung (§ 13 Abs. 1 Nr. 1 Buchst. a, § 18 Abs. 1 UStG). Wer die "
        f"abgegebene Voranmeldung für {liste} zusätzlich von Hand berichtigt "
        "(§ 153 Abs. 1 AO), meldet sie doppelt — richtig ist dann: den Monat öffnen "
        f"(accounti periode oeffnen {min(monate)} --grund …), ohne --buchungsdatum "
        "importieren und die berichtigte Voranmeldung aus accounti abgeben"
    )
    return [Befund(code="buchungsdatum", schweregrad=Schweregrad.WARNUNG, text=text)]


def _zieltag(verbindung: Connection, tag: date, buchungsdatum: Buchungsdatum) -> date:
    """Buchungsdatum für einen Posten vom ``tag`` in einem abgeschlossenen Zeitraum —
    nie davor und, wie bei ``opos verbuchen``, nie in einem anderen Geschäftsjahr:
    der Erlös gehört ins Geschäftsjahr der Leistung (§ 252 Abs. 1 Nr. 5 HGB, GoBD
    Rz. 51)."""
    if buchungsdatum == "offen":
        ziel = erster_offener_tag(verbindung, tag)
    else:
        ziel = buchungsdatum
    if ziel < tag:
        msg = (
            f"--buchungsdatum {ziel:%d.%m.%Y} liegt vor dem Posten vom {tag:%d.%m.%Y}"
            " — nichts importiert"
        )
        raise IntegrationError(msg)
    if ziel.year != tag.year:
        oeffnen = (
            f"das Geschäftsjahr öffnen (accounti abschluss oeffnen --jahr {tag.year})"
            if jahressperre(verbindung, tag.year) is not None
            else f"den Monat öffnen (accounti periode oeffnen {tag:%Y-%m} --grund …)"
        )
        msg = (
            f"Der Posten vom {tag:%d.%m.%Y} gehört ins Geschäftsjahr {tag.year}; "
            f"gebucht am {ziel:%d.%m.%Y} stünde er im Geschäftsjahr {ziel.year} "
            "(§ 252 Abs. 1 Nr. 5 HGB, GoBD Rz. 51) — nichts importiert. "
            f"{oeffnen[0].upper()}{oeffnen[1:]} und ohne --buchungsdatum importieren"
        )
        raise IntegrationError(msg)
    return ziel


def _verwirf_abgelegte(archiv: BelegArchiv, datei_hash: str) -> None:
    """Die eben in diesem Lauf abgelegte Datei wieder entfernen — die Datenbank rollt
    zurück, kein Beleg verweist auf sie. Archivierte Belege löscht accounti nie."""
    if archiv.enthaelt(datei_hash):
        archiv.pfad(datei_hash).unlink(missing_ok=True)


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
