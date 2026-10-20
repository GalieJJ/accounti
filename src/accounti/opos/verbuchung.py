"""Beleg → Buchung auf ein Personenkonto + offener Posten.

Eingang:  Aufwand an Kreditor (Vorsteuer per BU-Schlüssel)
Ausgang:  Debitor an Erlös   (Erlöskonto nach Steuerkategorie der E-Rechnung)

Beträge und Steuer kommen aus dem Beleg — gerechnet wird hier nichts neu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from accounti.belege.archiv import BelegArchiv
from accounti.belege.erkennung import erkenne_format
from accounti.belege.kanaele import RohBeleg
from accounti.db.repository import (
    lade_belege,
    speichere_buchung,
    speichere_posten,
    verbuchte_beleg_ids,
)
from accounti.erechnung import ERechnungError, lies
from accounti.erechnung.modell import Rechnung
from accounti.klassifikation.engine import RegelwerkEngine
from accounti.konfiguration import Buchhaltung
from accounti.kontakte.dienst import KontaktTreffer, Partnerdaten, kontakt_fuer
from accounti.kontakte.erkennung import finde_kontakt
from accounti.models import (
    Beleg,
    Belegart,
    BelegStatus,
    Buchungssatz,
    BuchungStatus,
    Kontakt,
    KontaktStatus,
    OffenerPosten,
    PostenRichtung,
    Transaktion,
    TransaktionQuelle,
)
from accounti.steuer.umsatzsteuer import OSS_ERLOES_KONTEN_SKR03

NULL = Decimal("0")
CENT = Decimal("0.01")

# Vorsteuer-BU-Schlüssel (Eingang) und Umsatzsteuer-BU-Schlüssel (Ausgang), SKR03
_VST_SCHLUESSEL = {Decimal("19"): 9, Decimal("7"): 8}
_UST_SCHLUESSEL = {Decimal("19"): 3, Decimal("7"): 2}
# Erlöskonten (SKR03) je EN-16931-Steuerkategorie
_ERLOES_STEUERPFLICHTIG = {Decimal("19"): "8400", Decimal("7"): "8300"}
_ERLOES_STEUERFREI = {
    "AE": "8338",  # sonstige Leistung im EU-Ausland, Steuerschuld beim Empfänger
    "K": "8125",  # steuerfreie innergemeinschaftliche Lieferung
    "G": "8120",  # steuerfreie Ausfuhr
    "E": "8100",  # steuerfreie Umsätze § 4 Nr. 8 ff.
}
_ERLOES_UNBEKANNT = "8200"


class VerbuchungError(RuntimeError):
    """Der Beleg kann so nicht verbucht werden."""


@dataclass
class Verbuchung:
    beleg: Beleg
    treffer: KontaktTreffer
    posten: OffenerPosten
    buchungen: list[Buchungssatz] = field(default_factory=list)

    @property
    def kontakt_neu(self) -> bool:
        return self.treffer.neu

    @property
    def merkmal(self) -> str | None:
        return self.treffer.merkmal


@dataclass
class _Gruppe:
    konto: str
    schluessel: int | None
    pruefen: bool
    netto: Decimal = NULL
    steuer: Decimal = NULL


def _satz(wert: Decimal | None) -> Decimal | None:
    return wert.normalize() if wert is not None else None


def _rechnung_aus_archiv(beleg: Beleg, archiv: BelegArchiv | None) -> Rechnung | None:
    """Die E-Rechnung hinter dem Beleg — für Käuferdaten und Steuerkategorien."""
    if archiv is None or not archiv.enthaelt(beleg.datei_hash):
        return None
    roh = RohBeleg(
        dateiname=beleg.dateiname,
        inhalt=archiv.lese(beleg.datei_hash),
        kanal=beleg.kanal,
        herkunft=beleg.herkunft,
    )
    xml = erkenne_format(roh).xml
    if xml is None:
        return None
    try:
        return lies(xml)
    except ERechnungError:
        return None


def _kategorien(beleg: Beleg, rechnung: Rechnung | None) -> list[str | None]:
    """Steuerkategorie je Belegposition (gleiche Reihenfolge wie in der Abbildung)."""
    if rechnung is None:
        return [None] * len(beleg.positionen)
    kategorien = [z.steuerkategorie for z in rechnung.zeilen] + [
        za.steuerkategorie for za in rechnung.zu_abschlaege
    ]
    if len(kategorien) != len(beleg.positionen):
        return [None] * len(beleg.positionen)
    return kategorien


def _sachkonto_eingang(
    beleg: Beleg,
    treffer: KontaktTreffer,
    einstellungen: Buchhaltung,
    regelwerk: RegelwerkEngine | None,
) -> tuple[str, bool]:
    """(Sachkonto, zur Prüfung?) — Kontakt-Vorschlag, Regelwerk, Standard."""
    kontakt = treffer.kontakt
    if kontakt.sachkonto:
        return kontakt.sachkonto, kontakt.status is not KontaktStatus.GEPRUEFT
    if regelwerk is not None:
        text = " ".join(
            filter(
                None, [beleg.belegnummer, *(p.bezeichnung for p in beleg.positionen)]
            )
        )
        pseudo = Transaktion(
            datum=beleg.belegdatum or beleg.eingegangen_am.date(),
            betrag=-(beleg.brutto or NULL),
            verwendungszweck=text or kontakt.name,
            gegenkonto_name=beleg.lieferant_name or kontakt.name,
            quelle=TransaktionQuelle.MANUELL,
            rohtext=f"Beleg {beleg.id}",
        )
        ergebnis = regelwerk.klassifiziere(pseudo)
        # nur Ausgaberegeln (… an Bank) taugen als Aufwandskonto
        if ergebnis is not None and ergebnis.haben_konto == einstellungen.bank_konto:
            return ergebnis.soll_konto, kontakt.status is not KontaktStatus.GEPRUEFT
    return einstellungen.standard_aufwand, True


def _gruppen(
    beleg: Beleg,
    eingang: bool,
    sachkonto: str,
    sachkonto_pruefen: bool,
    rechnung: Rechnung | None,
    land: str,
) -> list[_Gruppe]:
    gruppen: dict[tuple[str, int | None], _Gruppe] = {}
    positionen = beleg.positionen or []
    kategorien = _kategorien(beleg, rechnung)
    if not positionen:
        # ohne Positionen: eine Gruppe über die Belegsummen
        konto = sachkonto if eingang else _ERLOES_UNBEKANNT
        g = _Gruppe(konto, None, True)
        g.netto = beleg.netto if beleg.netto is not None else (beleg.brutto or NULL)
        g.steuer = beleg.steuer or NULL
        return [g]
    for p, kategorie in zip(positionen, kategorien, strict=True):
        satz = _satz(p.steuersatz)
        if eingang:
            schluessel = _VST_SCHLUESSEL.get(satz) if satz is not None else None
            konto = sachkonto
            # 0 % oder unbekannter Satz: § 13b, steuerfrei oder unklar → Mensch
            pruefen = sachkonto_pruefen or schluessel is None or kategorie == "AE"
        elif kategorie in _ERLOES_STEUERFREI:
            konto, schluessel, pruefen = _ERLOES_STEUERFREI[kategorie], None, False
        elif satz in _ERLOES_STEUERPFLICHTIG and kategorie in ("S", None):
            konto, schluessel = _ERLOES_STEUERPFLICHTIG[satz], _UST_SCHLUESSEL[satz]
            pruefen = False
        elif kategorie == "S" and satz:
            # anderer Satz als 19/7 %: OSS (Satz des Bestimmungslands)
            konto = OSS_ERLOES_KONTEN_SKR03.get(land, "8320")
            schluessel, pruefen = None, True
        else:
            konto, schluessel, pruefen = _ERLOES_UNBEKANNT, None, True
        g = gruppen.setdefault((konto, schluessel), _Gruppe(konto, schluessel, pruefen))
        g.pruefen = g.pruefen or pruefen
        g.netto += p.netto
        g.steuer += p.steuer_betrag or NULL
    return list(gruppen.values())


def _faelligkeit(
    beleg: Beleg, treffer: KontaktTreffer, einstellungen: Buchhaltung, belegdatum: date
) -> tuple[date, date | None, Decimal | None, Decimal | None]:
    """(fällig, Skonto bis, Skonto %, Skontobetrag): Beleg vor Kontakt vor Standard."""
    k = treffer.kontakt
    if beleg.zahlungsziel is not None:
        faellig = beleg.zahlungsziel
    else:
        tage = k.zahlungsziel_tage
        if tage is None:
            tage = einstellungen.standard_zahlungsziel_tage
        faellig = belegdatum + timedelta(days=tage)
    prozent = (
        beleg.skonto_prozent if beleg.skonto_prozent is not None else k.skonto_prozent
    )
    skonto_tage = beleg.skonto_tage if beleg.skonto_tage is not None else k.skonto_tage
    if prozent is None or skonto_tage is None:
        return faellig, None, None, None
    brutto = beleg.brutto or NULL
    betrag = (brutto * prozent / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    return faellig, belegdatum + timedelta(days=skonto_tage), prozent, betrag


def verbuche_beleg(
    session: Session,
    beleg: Beleg,
    einstellungen: Buchhaltung,
    archiv: BelegArchiv | None = None,
    regelwerk: RegelwerkEngine | None = None,
    eigene_firma: Partnerdaten | None = None,
) -> Verbuchung:
    eingang = beleg.belegart is Belegart.EINGANGSRECHNUNG
    rechnung = _rechnung_aus_archiv(beleg, archiv)
    anlass = f"Beleg {beleg.belegnummer or beleg.dateiname}"

    if eingang:
        if not beleg.lieferant_name:
            msg = f"{anlass}: kein Lieferant erkannt"
            raise VerbuchungError(msg)
        partner = Partnerdaten(
            name=beleg.lieferant_name, ust_id=beleg.lieferant_ust_id, iban=beleg.iban
        )
        if eigene_firma is not None:
            selbst = Kontakt(
                name=eigene_firma.name,
                ust_id=eigene_firma.ust_id,
                iban=eigene_firma.iban,
            )
            _, merkmal = finde_kontakt(
                [selbst], iban=partner.iban, ust_id=partner.ust_id, name=partner.name
            )
            if merkmal is not None:
                msg = (
                    f"{anlass}: Aussteller ist die eigene Firma (erkannt über "
                    f"{merkmal}) — als Ausgangsrechnung erfassen, z.B. mit "
                    "belege import --eigene-ust-id"
                )
                raise VerbuchungError(msg)
        treffer = kontakt_fuer(
            session, einstellungen, "kreditor", partner, neu_pruefen=True, anlass=anlass
        )
        personenkonto = treffer.kontakt.kreditor_konto
    else:
        k = rechnung.kaeufer if rechnung is not None else None
        if k is None or not k.name:
            msg = f"{anlass}: Käufer nicht lesbar (keine E-Rechnung im Archiv)"
            raise VerbuchungError(msg)
        partner = Partnerdaten(
            name=k.name,
            ust_id=k.ust_id,
            strasse=k.anschrift.strasse,
            plz=k.anschrift.plz,
            ort=k.anschrift.ort,
            land=k.anschrift.land,
            email=k.email,
        )
        # Kunden einer eigenen Ausgangsrechnung sind bekannt — keine Prüfung nötig.
        treffer = kontakt_fuer(
            session, einstellungen, "debitor", partner, neu_pruefen=False, anlass=anlass
        )
        personenkonto = treffer.kontakt.debitor_konto
    if personenkonto is None:  # pragma: no cover — kontakt_fuer vergibt immer eins
        raise VerbuchungError(f"{anlass}: kein Personenkonto")

    sachkonto, sachkonto_pruefen = (
        _sachkonto_eingang(beleg, treffer, einstellungen, regelwerk)
        if eingang
        else ("", False)
    )
    belegdatum = beleg.belegdatum or beleg.eingegangen_am.date()
    text = f"{treffer.kontakt.name} {beleg.belegnummer or ''}".strip()[:60]

    buchungen = []
    for g in _gruppen(
        beleg, eingang, sachkonto, sachkonto_pruefen, rechnung, treffer.kontakt.land
    ):
        soll, haben = (g.konto, personenkonto) if eingang else (personenkonto, g.konto)
        if g.netto < 0:  # Gutschrift: Seiten tauschen, Beträge positiv
            soll, haben = haben, soll
        buchung = Buchungssatz(
            beleg_id=beleg.id,
            datum=belegdatum,
            soll_konto=soll,
            haben_konto=haben,
            betrag_netto=abs(g.netto),
            steuer_schluessel=g.schluessel,
            steuer_betrag=abs(g.steuer) if g.schluessel is not None else None,
            buchungstext=text,
            beleg_nummer=(beleg.belegnummer or "")[:36] or None,
            status=BuchungStatus.ZUR_PRUEFUNG
            if g.pruefen
            else BuchungStatus.AUTO_GEBUCHT,
            confidence=0.5 if g.pruefen else 1.0,
        )
        speichere_buchung(session, buchung)
        buchungen.append(buchung)

    faellig, skonto_bis, skonto_prozent, skonto_betrag = _faelligkeit(
        beleg, treffer, einstellungen, belegdatum
    )
    brutto = beleg.brutto
    if brutto is None:
        brutto = sum(
            (p.netto + (p.steuer_betrag or NULL) for p in beleg.positionen), NULL
        )
    posten = OffenerPosten(
        kontakt_id=treffer.kontakt.id,
        beleg_id=beleg.id,
        richtung=PostenRichtung.VERBINDLICHKEIT
        if eingang
        else PostenRichtung.FORDERUNG,
        belegnummer=beleg.belegnummer,
        belegdatum=belegdatum,
        betrag=brutto,
        restbetrag=brutto,
        faellig_am=faellig,
        skonto_bis=skonto_bis,
        skonto_prozent=skonto_prozent,
        skonto_betrag=skonto_betrag,
    )
    speichere_posten(session, posten)
    return Verbuchung(beleg, treffer, posten, buchungen)


@dataclass
class Verbuchungslauf:
    verbucht: list[Verbuchung] = field(default_factory=list)
    fehler: list[tuple[Beleg, str]] = field(default_factory=list)


def verbuche_belege(
    session: Session,
    einstellungen: Buchhaltung,
    archiv: BelegArchiv | None = None,
    regelwerk: RegelwerkEngine | None = None,
    eigene_firma: Partnerdaten | None = None,
) -> Verbuchungslauf:
    """Verbucht alle erfassten, noch nicht verbuchten Rechnungen.

    Jeder Beleg läuft in einem eigenen Savepoint: Scheitert einer, bleiben die
    anderen verbucht und der Fehler steht im Ergebnis.
    """
    bereits = verbuchte_beleg_ids(session)
    lauf = Verbuchungslauf()
    for beleg in lade_belege(session, status={BelegStatus.ERFASST}):
        if beleg.id in bereits or beleg.belegart not in (
            Belegart.EINGANGSRECHNUNG,
            Belegart.AUSGANGSRECHNUNG,
        ):
            continue
        try:
            with session.begin_nested():
                verbuchung = verbuche_beleg(
                    session, beleg, einstellungen, archiv, regelwerk, eigene_firma
                )
            lauf.verbucht.append(verbuchung)
        except (VerbuchungError, ValueError) as fehler:
            lauf.fehler.append((beleg, str(fehler)))
    return lauf
