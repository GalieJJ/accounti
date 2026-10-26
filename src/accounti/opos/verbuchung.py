"""Beleg → Buchung auf ein Personenkonto + offener Posten.

Eingang:  Aufwand an Kreditor (Vorsteuer per BU-Schlüssel)
Ausgang:  Debitor an Erlös   (Erlöskonto nach Steuerkategorie der E-Rechnung)

Beträge und Steuer kommen aus dem Beleg — gerechnet wird hier nur, was der Beleg
nicht nennen darf: die Steuer bei § 13b UStG und beim ig. Erwerb (Steuerfall AE bzw. K,
Schlüssel 94 bzw. 19 zur Prüfung, ``buchung/steuergruppe.py``). Eine Steuer ohne Satz
geht brutto und zur Prüfung auf das Konto, nie netto gegen einen Brutto-Posten.

Eingangsrechnungen werden auf das Belegdatum gebucht. Eine Eingangsrechnung, die erst
nach der Festschreibung ihres Monats eintrifft, bucht ``buchungsdatum`` auf das
Eingangsdatum (``eingang``), den ersten offenen Tag ab dem späteren von Beleg- und
Eingangsdatum (``offen``) oder einen festen Tag — nur Belege, deren Zeitraum gesperrt
ist; die Vorsteuer gehört nach § 15 Abs. 1 Nr. 1 UStG ohnehin in den Zeitraum, in dem
die Rechnung vorliegt. Bei Bilanzierung nie über den Geschäftsjahreswechsel.

Geht die Rechnung erst im Folgejahr ein (Bilanz: Aufwand und Verbindlichkeit bleiben im
alten Jahr), bucht accounti die Vorsteuer auf „Vorsteuer im Folgejahr abziehbar“
(SKR03 1548, SKR04 1434) und zum ersten offenen Tag des Eingangsmonats auf das
Vorsteuerkonto um — erst dort zählt sie in der Voranmeldung (§ 15 Abs. 1 S. 1 Nr. 1
UStG, Abschn. 15.2 Abs. 2 S. 7 UStAE: Leistung und Rechnung müssen vorliegen).

Das gilt nur für den Abzug. Eine Gutschrift des Lieferanten (negative Vorsteuer)
mindert die Vorsteuer im Zeitraum, in dem sich die Bemessungsgrundlage geändert hat —
unabhängig davon, wann der Beleg eingeht (§ 17 Abs. 1 S. 8 UStG, Abschn. 17.1 UStAE).
accounti nimmt dafür das Belegdatum der Gutschrift: kein 1548-Weg, kein § 15-Hinweis;
gebucht in einem späteren Zeitraum (gesperrter Monat), geht sie zur Prüfung.

Ausgangsrechnungen werden zum umsatzsteuerlichen Zeitpunkt gebucht
(``steuer/leistungszeitpunkt.py``): zum Leistungsdatum, wenn die Leistung in einem
früheren Monat lag (§ 13 Abs. 1 Nr. 1 Buchst. a UStG), eine innergemeinschaftliche
Lieferung im Rechnungsmonat, spätestens am Ende des Folgemonats (§ 13 Abs. 1 Nr. 6
UStG), eine Gutschrift/Korrektur zu ihrem Datum (§ 17 Abs. 1 Satz 7 UStG). Ist dieser
Monat festgeschrieben, wird nicht still später gebucht: Der Monat ist zu öffnen und die
Voranmeldung zu berichtigen. Ist die Voranmeldung des Zeitraums schon übermittelt, der
Monat aber offen, weist die Verbuchung auf die Berichtigung hin (§ 153 Abs. 1 AO) — bei
einer Minderung (Gutschrift, Korrektur nach unten) als Möglichkeit, nicht als Pflicht,
denn sie verkürzt keine Steuer. Eine Gutschrift mit Bezug (BT-25) wird mit der noch
offenen Rechnung desselben Kunden verrechnet.

Offener Posten, Fälligkeit und Skonto bleiben beim Belegdatum.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy.orm import Session

from accounti.abschluss.kontenrahmen import Kontenrahmen, lade_kontenrahmen
from accounti.anzeige import betrag_de
from accounti.belege.archiv import BelegArchiv
from accounti.belege.erkennung import erkenne_format
from accounti.belege.kanaele import RohBeleg
from accounti.buchung.mit_beleg import sachkonto_fuer_beleg
from accounti.buchung.steuergruppe import (
    SCHLUESSEL_FUER_STEUERFALL,
    SELBST_BERECHNET,
    Gruppe,
)
from accounti.db.repo_abschluss import ist_gesperrt
from accounti.db.repository import (
    lade_belege,
    lade_kontakte,
    lade_posten,
    speichere_buchung,
    speichere_posten,
    verbuchte_beleg_ids,
)
from accounti.db.tabellen_abschluss import JahrGesperrtError
from accounti.db.tabellen_pruefung import erster_offener_tag, sperrfehler
from accounti.elster.ustva import abgegeben
from accounti.erechnung import ERechnungError, lies
from accounti.erechnung.abbildung import GUTSCHRIFT_TYPEN
from accounti.erechnung.modell import Rechnung
from accounti.klassifikation.engine import RegelwerkEngine
from accounti.konfiguration import Buchhaltung
from accounti.kontakte.dienst import KontaktTreffer, Partnerdaten, kontakt_fuer
from accounti.kontakte.erkennung import finde_kontakt, land_aus_kennung, suche_kontakt
from accounti.kontakte.ustid import USTID_KATEGORIEN, aktuelle_bestaetigung
from accounti.models import (
    Beleg,
    Belegart,
    BelegStatus,
    Buchungssatz,
    BuchungStatus,
    Kontakt,
    OffenerPosten,
    PostenRichtung,
    PostenStatus,
)
from accounti.models.elster import Meldeart
from accounti.opos.verrechnung import VerrechnungError, verrechne_posten
from accounti.steuer.eu_steuersaetze import ist_eu_land
from accounti.steuer.kennziffern import VORSTEUER_FOLGEJAHR
from accounti.steuer.leistungszeitpunkt import steuertag
from accounti.steuer.umsatzsteuer import OSS_ERLOES_KONTEN_SKR03, OSS_UST_KONTEN_SKR03
from accounti.steuer.zeitraum import Zeitraum

NULL = Decimal("0")
CENT = Decimal("0.01")

# Vorsteuer-BU-Schlüssel (Eingang) und Umsatzsteuer-BU-Schlüssel (Ausgang), SKR03
_VST_SCHLUESSEL = {Decimal("19"): 9, Decimal("7"): 8}
_UST_SCHLUESSEL = {Decimal("19"): 3, Decimal("7"): 2}
# Erlöskonten (SKR03) je EN-16931-Steuerkategorie
_ERLOES_STEUERPFLICHTIG = {Decimal("19"): "8400", Decimal("7"): "8300"}
_ERLOES_STEUERFREI = {
    "AE": "8336",  # sonstige Leistung im EU-Ausland, Steuerschuld beim Empfänger
    "K": "8125",  # steuerfreie innergemeinschaftliche Lieferung
    "G": "8120",  # steuerfreie Ausfuhr
    "E": "8100",  # steuerfreie Umsätze § 4 Nr. 8 ff.
}
_ERLOES_UNBEKANNT = "8200"
# Belegtypen, die eine Rechnung mindern oder berichtigen (§ 17 UStG: Monat der Änderung)
_KORREKTUR_TYPEN = GUTSCHRIFT_TYPEN | {"384"}


class VerbuchungError(RuntimeError):
    """Der Beleg kann so nicht verbucht werden."""


# Buchungsdatum einer Eingangsrechnung: Belegdatum, Eingang, erster offener Tag, fest
Buchungsdatum = Literal["beleg", "eingang", "offen"] | date


@dataclass
class Verbuchung:
    beleg: Beleg
    treffer: KontaktTreffer
    posten: OffenerPosten
    buchungen: list[Buchungssatz] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)

    @property
    def kontakt_neu(self) -> bool:
        return self.treffer.neu

    @property
    def merkmal(self) -> str | None:
        return self.treffer.merkmal


@dataclass
class _Gruppe(Gruppe):
    """Gruppe mit Buchungstag — im Eingang der Buchungstag des Belegs, im Ausgang
    der umsatzsteuerliche Zeitpunkt je Steuerkategorie
    (``steuer/leistungszeitpunkt.py``)."""

    tag: date = field(kw_only=True)


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
    s = sachkonto_fuer_beleg(beleg, treffer.kontakt, einstellungen, regelwerk)
    return s.konto, s.pruefen


def _gruppen(
    beleg: Beleg,
    eingang: bool,
    sachkonto: str,
    sachkonto_pruefen: bool,
    rechnung: Rechnung | None,
    land: str,
    tag_fuer: Callable[[str | None], date],
    ustid_bestaetigt: bool = True,
) -> list[_Gruppe]:
    """Buchungen je Konto, Steuerschlüssel und Buchungstag (``tag_fuer`` je
    Steuerkategorie)."""
    gruppen: dict[tuple[str, int | None, date], _Gruppe] = {}
    positionen = beleg.positionen or []
    kategorien = _kategorien(beleg, rechnung)
    if not positionen:
        # ohne Positionen: eine Gruppe über die Belegsummen (ohne Satz: brutto)
        konto = sachkonto if eingang else _ERLOES_UNBEKANNT
        g = _Gruppe(konto, None, True, tag=tag_fuer(None))
        if beleg.netto is not None:
            g.addiere(beleg.netto, beleg.steuer or NULL)
        else:
            g.addiere(beleg.brutto or NULL, NULL)
        return [g]

    def gruppe(
        konto: str, schluessel: int | None, pruefen: bool, kategorie: str | None
    ) -> _Gruppe:
        tag = tag_fuer(kategorie)
        g = gruppen.setdefault(
            (konto, schluessel, tag), _Gruppe(konto, schluessel, pruefen, tag=tag)
        )
        g.pruefen = g.pruefen or pruefen
        return g

    schluessel: int | None
    for p, kategorie in zip(positionen, kategorien, strict=True):
        satz = _satz(p.steuersatz)
        steuer = p.steuer_betrag or NULL
        if eingang:
            # Steuerfall ohne Steuerausweis: Kategorie der E-Rechnung bzw. Hinweis
            fall = kategorie or (beleg.steuerkennzeichen if not satz else None)
            konto = sachkonto
            if fall in SCHLUESSEL_FUER_STEUERFALL and not satz:
                # § 13b bzw. ig. Erwerb: die Steuer schuldet der Empfänger — 19 %
                # vorgeschlagen, der Mensch prüft (7 %: 91 bzw. 18)
                schluessel, pruefen = SCHLUESSEL_FUER_STEUERFALL[fall], True
            else:
                schluessel = _VST_SCHLUESSEL.get(satz) if satz is not None else None
                # 0 % oder unbekannter Satz: steuerfrei, § 19 oder unklar → Mensch
                pruefen = sachkonto_pruefen or schluessel is None
        elif kategorie in _ERLOES_STEUERFREI:
            konto, schluessel = _ERLOES_STEUERFREI[kategorie], None
            # K/AE nur mit bestätigter USt-IdNr. des Käufers automatisch
            pruefen = kategorie in USTID_KATEGORIEN and not ustid_bestaetigt
        elif satz in _ERLOES_STEUERPFLICHTIG and kategorie in ("S", None):
            konto, schluessel = _ERLOES_STEUERPFLICHTIG[satz], _UST_SCHLUESSEL[satz]
            pruefen = False
        elif kategorie == "S" and satz:
            # anderer Satz als 19/7 %: OSS (Satz des Bestimmungslands) — Erlös netto,
            # die ausländische Steuer auf das OSS-Steuerkonto des Landes
            erloes = OSS_ERLOES_KONTEN_SKR03.get(land, "8320")
            gruppe(erloes, None, True, kategorie).addiere(p.netto, NULL)
            ust = OSS_UST_KONTEN_SKR03.get(land, "1779")
            gruppe(ust, None, True, kategorie).addiere(steuer, NULL)
            continue
        else:
            konto, schluessel, pruefen = _ERLOES_UNBEKANNT, None, True
        gruppe(konto, schluessel, pruefen, kategorie).addiere(p.netto, steuer)
    for g in gruppen.values():
        g.berechne_selbst()
    return list(gruppen.values())


def _steuerhinweise(gruppen: list[_Gruppe], anlass: str, land: str) -> list[str]:
    """Was der Mensch bei 0-%-Positionen einer Eingangsrechnung prüfen muss."""
    hinweise = []
    schluessel = {g.schluessel for g in gruppen}
    if schluessel & {94, 91}:
        kz = "46/47" if land.upper() != "DE" and ist_eu_land(land) else "84/85"
        hinweise.append(
            f"{anlass}: Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG) — "
            f"Schlüssel 94 (19 %) vorgeschlagen und zur Prüfung, Kz {kz} (Kreditor-"
            f"Land {land.upper()}); bei 7 %: accounti korrigiere … --steuer 91"
        )
    if schluessel & {19, 18}:
        hinweise.append(
            f"{anlass}: steuerfreie ig. Lieferung an uns = ig. Erwerb (§ 1a UStG) — "
            "Schlüssel 19 (19 %) vorgeschlagen und zur Prüfung; bei 7 %: --steuer 18"
        )
    return hinweise


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
    # Der Beleg geht vor: „ohne Abzug“ (0 %) schlägt das Skonto des Kontakts
    prozent = (
        beleg.skonto_prozent if beleg.skonto_prozent is not None else k.skonto_prozent
    )
    skonto_tage = beleg.skonto_tage if beleg.skonto_tage is not None else k.skonto_tage
    if not prozent or skonto_tage is None:
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
    ustid_max_alter_tage: int = 30,
    buchungsdatum: Buchungsdatum = "beleg",
    gewinnermittlung: str | None = None,
) -> Verbuchung:
    eingang = beleg.belegart is Belegart.EINGANGSRECHNUNG
    rechnung = _rechnung_aus_archiv(beleg, archiv)
    anlass = f"Beleg {beleg.belegnummer or beleg.dateiname}"
    belegdatum = beleg.belegdatum or beleg.eingegangen_am.date()
    hinweise: list[str] = []
    if eingang:
        gutschrift = _gutschrift_eingang(beleg, rechnung)
        gebucht_am, hinweis_datum = _buchungstag(
            session,
            beleg,
            belegdatum,
            buchungsdatum,
            anlass,
            gewinnermittlung,
            gutschrift=gutschrift,
        )
        hinweise += [hinweis_datum] if hinweis_datum else []
        _pruefe_sperre(
            session,
            beleg,
            anlass,
            gebucht_am,
            belegdatum,
            gewinnermittlung,
            eingang=True,
            gutschrift=gutschrift,
        )
        tag_fuer = _fester_tag(gebucht_am)
    else:
        # Buchungstag je Steuerkategorie (tag_fuer); Abzug und Minderung der
        # Vorsteuer, 1548-Weg und § 15-Hinweis betreffen nur den Eingang
        gebucht_am, hinweis_datum = belegdatum, None
        korrektur = (rechnung is not None and rechnung.typ in _KORREKTUR_TYPEN) or (
            beleg.brutto is not None and beleg.brutto < 0
        )
        tag_fuer = _steuertag_fuer(belegdatum, beleg.leistungsdatum, korrektur)
        kategorien = set(_kategorien(beleg, rechnung)) or {None}
        for kategorie in sorted(kategorien, key=str):
            tag, hinweis = steuertag(
                belegdatum, beleg.leistungsdatum, kategorie, korrektur
            )
            if hinweis and hinweis not in hinweise:
                hinweise.append(hinweis)
            _pruefe_sperre(
                session, beleg, anlass, tag, belegdatum, gewinnermittlung, eingang=False
            )
            berichtigung = _abgegebene_voranmeldung(
                session, tag, minderung=beleg.brutto is not None and beleg.brutto < 0
            )
            if berichtigung and berichtigung not in hinweise:
                hinweise.append(berichtigung)

    if eingang:
        if not beleg.lieferant_name:
            msg = f"{anlass}: kein Lieferant erkannt"
            raise VerbuchungError(msg)
        partner = Partnerdaten(
            name=beleg.lieferant_name,
            ust_id=beleg.lieferant_ust_id,
            iban=beleg.iban,
            land=land_aus_kennung(beleg.lieferant_ust_id, beleg.iban),
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
        # Kunden einer eigenen Ausgangsrechnung sind bekannt — keine Prüfung nötig;
        # ein gleichnamiger Kunde ist derselbe nur bei gleicher PLZ oder E-Mail,
        # eine Gutschrift mit Bezug (BT-25) gehört zum Kunden ihrer Rechnung
        bezug = (
            _kunde_der_bezugsrechnung(
                session, rechnung.vorgaenger_nummer, partner, anlass, hinweise
            )
            if rechnung is not None and rechnung.vorgaenger_nummer
            else None
        )
        treffer = bezug or kontakt_fuer(
            session,
            einstellungen,
            "debitor",
            partner,
            neu_pruefen=False,
            anlass=anlass,
            mit_anschrift=True,
        )
        personenkonto = treffer.kontakt.debitor_konto
    if personenkonto is None:  # pragma: no cover — kontakt_fuer vergibt immer eins
        raise VerbuchungError(f"{anlass}: kein Personenkonto")

    sachkonto, sachkonto_pruefen = (
        _sachkonto_eingang(beleg, treffer, einstellungen, regelwerk)
        if eingang
        else ("", False)
    )
    text = f"{treffer.kontakt.name} {beleg.belegnummer or ''}".strip()[:60]

    # Kontakt widerspricht dem Beleg (z. B. gleiche IBAN, anderer Name): zur Prüfung
    widerspruch = treffer.widerspruch is not None and not treffer.neu
    if treffer.widerspruch is not None:
        folge = "neuer Kontakt zur Prüfung" if treffer.neu else "Buchung zur Prüfung"
        hinweise.append(f"{anlass}: {treffer.widerspruch} — {folge}")
    ustid_bestaetigt = True
    # nur bei eigenen Rechnungen: K/AE im Eingang hängen an der USt-IdNr. des
    # Lieferanten, nicht an unserer (die Bestätigung braucht der Lieferant)
    if (
        not eingang
        and rechnung is not None
        and any(
            kategorie in USTID_KATEGORIEN for kategorie in _kategorien(beleg, rechnung)
        )
    ):
        ust_id = rechnung.kaeufer.ust_id
        lage = aktuelle_bestaetigung(session, ust_id, belegdatum, ustid_max_alter_tage)
        ustid_bestaetigt = lage.bestaetigt
        if not lage.bestaetigt:
            hinweise.append(
                f"USt-IdNr. {ust_id or '—'} nicht bestätigt: {lage.grund} — "
                "steuerfreie Erlöse zur Prüfung "
                f"(accounti kontakte pruefe-ustid {personenkonto})"
            )

    buchungen = []
    land = treffer.kontakt.land
    if not eingang and rechnung is not None:
        # OSS: Bestimmungsland aus der Rechnung (Lieferanschrift, sonst Käufer), nicht
        # aus dem Kontakt — gleichnamige Kunden dürfen sich nicht vermischen
        lieferung = rechnung.lieferanschrift
        land = (
            (lieferung.land if lieferung is not None else None)
            or rechnung.kaeufer.anschrift.land
            or land
        )
    gruppen = _gruppen(
        beleg,
        eingang,
        sachkonto,
        sachkonto_pruefen,
        rechnung,
        land,
        tag_fuer,
        ustid_bestaetigt,
    )
    vorsteuer = [g.steuer for g in gruppen if g.schluessel in (8, 9) and g.steuer]
    abzug = any(s > 0 for s in vorsteuer)
    # Gutschrift: negative Vorsteuer — oder bei § 13b/ig. Erwerb ein negatives Netto
    # (keine ausgewiesene Steuer, § 17 Abs. 1 S. 5 UStG)
    minderung = any(s < 0 for s in vorsteuer) or any(
        _mindert_selbst_berechnet(g) for g in gruppen
    )
    if hinweis_datum and not abzug and (gebucht_am == belegdatum or minderung):
        # der § 15-Hinweis gilt nur für den Abzug von Vorsteuer aus der Rechnung —
        # § 13b/ig. Erwerb hängen nicht an ihr (§ 15 Abs. 1 S. 1 Nr. 3, 4 UStG), eine
        # Gutschrift mindert im Zeitraum der Änderung (§ 17 Abs. 1 S. 8 UStG)
        hinweise.remove(hinweis_datum)
    minderung_spaet = minderung and (gebucht_am.year, gebucht_am.month) != (
        belegdatum.year,
        belegdatum.month,
    )
    if minderung:
        hinweise += _hinweis_minderung(
            belegdatum,
            beleg.eingegangen_am.date(),
            gebucht_am,
            anlass,
            gutschrift or "vorsteuer",
        )
    if eingang:
        hinweise += _steuerhinweise(gruppen, anlass, land)
    folgejahr = _vorsteuer_folgejahr(
        session, einstellungen, beleg, gebucht_am, eingang, gewinnermittlung
    )
    for g in gruppen:
        soll, haben = (g.konto, personenkonto) if eingang else (personenkonto, g.konto)
        gedreht = g.netto < 0  # Gutschrift: Seiten tauschen, Beträge positiv
        if gedreht:
            soll, haben = haben, soll
        # Minderung außerhalb ihres Zeitraums gebucht: die Voranmeldung stimmt so nicht
        spaet = minderung_spaet and (
            (g.schluessel in (8, 9) and g.steuer < 0) or _mindert_selbst_berechnet(g)
        )
        pruefen = g.pruefen or widerspruch or spaet
        status = BuchungStatus.ZUR_PRUEFUNG if pruefen else BuchungStatus.AUTO_GEBUCHT

        def buche(
            soll: str,
            haben: str,
            betrag: Decimal,
            schluessel: int | None = None,
            steuer: Decimal | None = None,
            datum: date = g.tag,
            status: BuchungStatus = status,
            pruefen: bool = pruefen,
        ) -> None:
            buchung = Buchungssatz(
                beleg_id=beleg.id,
                datum=datum,
                soll_konto=soll,
                haben_konto=haben,
                betrag_netto=betrag,
                steuer_schluessel=schluessel,
                steuer_betrag=steuer,
                buchungstext=text,
                beleg_nummer=(beleg.belegnummer or "")[:36] or None,
                status=status,
                confidence=0.5 if pruefen else 1.0,
            )
            speichere_buchung(session, buchung)
            buchungen.append(buchung)

        # nur der Abzug wartet auf die Rechnung — eine Minderung (Gutschrift) gehört
        # in den Zeitraum der Änderung (§ 17 Abs. 1 S. 8 UStG), also kein 1548-Weg
        if folgejahr is not None and g.schluessel in (8, 9) and g.steuer > 0:
            konto_folgejahr, umbuchung_am, kr = folgejahr
            vorsteuerkonto = kr.steuerkonto(g.schluessel) or konto_folgejahr
            steuer = g.steuer
            buche(soll, haben, abs(g.netto))
            # Vorsteuer: im alten Jahr nur als „im Folgejahr abziehbar“ …
            buche(konto_folgejahr, personenkonto, steuer)
            # … und abziehbar im Zeitraum, in dem die Rechnung vorliegt
            buche(vorsteuerkonto, konto_folgejahr, steuer, datum=umbuchung_am)
            hinweise.append(
                f"{anlass}: Rechnung vom {belegdatum:%d.%m.%Y} erst am "
                f"{beleg.eingegangen_am:%d.%m.%Y} erfasst — Vorsteuer "
                f"{betrag_de(steuer)} € auf "
                f"{konto_folgejahr} „Vorsteuer im Folgejahr abziehbar“ und zum "
                f"{umbuchung_am:%d.%m.%Y} auf {vorsteuerkonto} umgebucht: abziehbar in "
                f"{umbuchung_am:%m/%Y} (§ 15 Abs. 1 Nr. 1 UStG); lag die Rechnung "
                "schon im alten Jahr vor (Eingang = Erfassung in accounti), die "
                "Buchungen korrigieren"
            )
            continue
        buche(
            soll,
            haben,
            abs(g.netto),
            g.schluessel,
            abs(g.steuer) if g.schluessel is not None else None,
        )

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
    if not eingang and rechnung is not None and rechnung.vorgaenger_nummer:
        posten = _mit_rechnung_verrechnen(
            session, posten, rechnung.vorgaenger_nummer, belegdatum, hinweise
        )
    return Verbuchung(beleg, treffer, posten, buchungen, hinweise)


# Was eine Lieferanten-Gutschrift mindert — ausgewiesene Vorsteuer oder bei § 13b und
# ig. Erwerb Steuer und Vorsteuer, die der Empfänger selbst berechnet: (Akkusativ,
# Genitiv, Verb) für die Meldungen
_SELBST = "(§ 13b bzw. ig. Erwerb, § 17 Abs. 1 S. 5 UStG)"
_MINDERT = {
    "vorsteuer": ("die Vorsteuer", "der Vorsteuer", "mindert"),
    "selbst": (
        f"Steuer und Vorsteuer {_SELBST}",
        f"von Steuer und Vorsteuer {_SELBST}",
        "mindern",
    ),
}


def _gutschrift_eingang(
    beleg: Beleg, rechnung: Rechnung | None
) -> Literal["vorsteuer", "selbst"] | None:
    """Mindert die Eingangsrechnung Steuer, ist sie eine Gutschrift des Lieferanten:
    negative Vorsteuer (``vorsteuer``) oder eine negative Position ohne Steuerausweis
    mit Steuerfall § 13b bzw. ig. Erwerb (``selbst`` — dort steht keine Steuer im
    Beleg, Nachprüfung Merge N-3)."""
    if beleg.steuer is not None and beleg.steuer < 0:
        return "vorsteuer"
    for p, kategorie in zip(
        beleg.positionen, _kategorien(beleg, rechnung), strict=True
    ):
        fall = kategorie or beleg.steuerkennzeichen
        if (
            p.netto < 0
            and not _satz(p.steuersatz)
            and fall in SCHLUESSEL_FUER_STEUERFALL
        ):
            return "selbst"
    return None


def _mindert_selbst_berechnet(g: Gruppe) -> bool:
    return g.schluessel in SELBST_BERECHNET and g.netto < 0


def _vorsteuer_folgejahr(
    session: Session,
    einstellungen: Buchhaltung,
    beleg: Beleg,
    gebucht_am: date,
    eingang: bool,
    gewinnermittlung: str | None,
) -> tuple[str, date, Kontenrahmen] | None:
    """(Konto „Vorsteuer im Folgejahr“, Tag der Umbuchung, Kontenrahmen), wenn eine
    Eingangsrechnung bei Bilanzierung erst im Folgejahr eingegangen ist — sonst None.

    Ohne Angabe der Gewinnermittlung gilt wie beim Buchungstag die Bilanzierung."""
    eingegangen = beleg.eingegangen_am.date()
    if not eingang or gewinnermittlung == "euer" or eingegangen.year <= gebucht_am.year:
        return None
    kr = lade_kontenrahmen(einstellungen.kontenrahmen)
    konto, _ = VORSTEUER_FOLGEJAHR.get(kr.name, VORSTEUER_FOLGEJAHR["SKR03"])
    tag = erster_offener_tag(session.connection(), eingegangen.replace(day=1))
    return konto, tag, kr


def _hinweis_minderung(
    belegdatum: date,
    eingegangen: date,
    gebucht_am: date,
    anlass: str,
    gutschrift: Literal["vorsteuer", "selbst"] = "vorsteuer",
) -> list[str]:
    """Gutschrift: Die Vorsteuer mindert sich im Zeitraum der Änderung der
    Bemessungsgrundlage (§ 17 Abs. 1 S. 8 UStG) — hier das Belegdatum —, nicht im
    Zeitraum des Eingangs (Abschn. 17.1 UStAE; § 15 Abs. 1 Nr. 1 gilt nur für den
    Abzug)."""
    zeitraum = f"{belegdatum:%m/%Y}"
    was, wessen, mindert = _MINDERT[gutschrift]
    if (gebucht_am.year, gebucht_am.month) != (belegdatum.year, belegdatum.month):
        return [
            f"{anlass}: Gutschrift vom {belegdatum:%d.%m.%Y} am {gebucht_am:%d.%m.%Y} "
            f"gebucht — die Minderung {wessen} gehört in den Zeitraum der "
            f"Änderung ({zeitraum}), nicht in einen späteren (§ 17 Abs. 1 S. 8 UStG): "
            f"die Voranmeldung {zeitraum} ist zu berichtigen und diese Buchung zu "
            f"stornieren und zum Belegdatum neu zu buchen — bleibt sie stehen, zählt "
            f"die Minderung doppelt ({zeitraum} und {gebucht_am:%m/%Y}); Buchung zur "
            "Prüfung"
        ]
    if (eingegangen.year, eingegangen.month) > (belegdatum.year, belegdatum.month):
        return [
            f"{anlass}: Gutschrift vom {belegdatum:%d.%m.%Y}, erfasst am "
            f"{eingegangen:%d.%m.%Y} — {was} {mindert} sich im Zeitraum der "
            f"Änderung ({zeitraum}), nicht im Eingangszeitraum (§ 17 Abs. 1 S. 8 UStG, "
            f"Abschn. 17.1 UStAE); ist die Voranmeldung {zeitraum} schon abgegeben, "
            "ist sie zu berichtigen"
        ]
    return []


def _hinweis_eingang_spaeter(
    belegdatum: date, eingegangen: date, anlass: str, gewinnermittlung: str | None
) -> str | None:
    """Zum Belegdatum gebucht, aber in einem späteren Monat erfasst: Die Vorsteuer
    zählt im Monat des Belegdatums — abziehbar ist sie erst, wenn die Rechnung
    vorliegt (§ 15 Abs. 1 Nr. 1 UStG). Folgejahr bei Bilanz: 1548, eigener Hinweis."""
    if (eingegangen.year, eingegangen.month) <= (belegdatum.year, belegdatum.month):
        return None
    if eingegangen.year > belegdatum.year and gewinnermittlung != "euer":
        return None
    return (
        f"{anlass}: zum Belegdatum {belegdatum:%d.%m.%Y} gebucht, erfasst am "
        f"{eingegangen:%d.%m.%Y} — die Vorsteuer zählt in {belegdatum:%m/%Y}; lag "
        f"die Rechnung erst nach Ende dieses Zeitraums vor, gehört sie in "
        f"{eingegangen:%m/%Y} (§ 15 Abs. 1 Nr. 1 UStG, kein Wahlrecht). accounti "
        "verschiebt sie nicht von sich aus (Eingang = Erfassung in accounti; "
        "--buchungsdatum gilt nur für festgeschriebene Monate); die Voranmeldung "
        f"{belegdatum:%m/%Y} meldet sie als Befund beleg_nach_zeitraum"
    )


def _spaetere_wege(
    session: Session,
    beleg: Beleg,
    belegdatum: date,
    gewinnermittlung: str | None,
) -> str:
    """Die Werte für ``--buchungsdatum``, mit denen ``_buchungstag`` einen gesperrten
    Beleg später bucht — bei Bilanzierung nur im Geschäftsjahr des Belegs (Nachprüfung
    C, N-2; Runde 4: „eingang“ und „offen“ gehen vom Eingang aus und lagen im
    Folgejahr, die Meldung bot sie trotzdem an). Leer, wenn keiner geht."""
    verbindung = session.connection()
    eingegangen = beleg.eingegangen_am.date()

    def geht(tag: date) -> bool:
        im_jahr = gewinnermittlung == "euer" or tag.year == belegdatum.year
        return tag >= belegdatum and im_jahr and sperrfehler(verbindung, tag) is None

    wege = [
        weg
        for weg, tag in (
            ("eingang", eingegangen),
            ("offen", erster_offener_tag(verbindung, max(belegdatum, eingegangen))),
            ("JJJJ-MM-TT", erster_offener_tag(verbindung, belegdatum)),
        )
        if geht(tag)
    ]
    if len(wege) < 2:
        return "".join(wege)
    return ", ".join(wege[:-1]) + " oder " + wege[-1]


def _kunde_der_bezugsrechnung(
    session: Session,
    nummer: str,
    partner: Partnerdaten,
    anlass: str,
    hinweise: list[str],
) -> KontaktTreffer | None:
    """Gutschrift/Korrektur mit Bezug (BT-25): der Debitor der Rechnung ``nummer``,
    wenn der Käufer dort derselbe ist (Name, keine andere USt-IdNr., kein anderes
    Land). Sonst teilte eine neue Anschrift — ein umgezogener Privatkunde ohne E-Mail —
    den Kunden in zwei Debitoren, und die Verrechnung fiele still aus (Nachprüfung
    Merge N-1). Eine abweichende Anschrift wird gemeldet, nicht übernommen."""
    kunden = {
        p.kontakt_id
        for p in lade_posten(session, richtung=PostenRichtung.FORDERUNG)
        if p.belegnummer == nummer
    }
    if len(kunden) != 1:
        return None
    kontakt = {k.id: k for k in lade_kontakte(session)}.get(kunden.pop())
    if kontakt is None or kontakt.debitor_konto is None:
        return None
    gefunden = suche_kontakt(
        [kontakt], ust_id=partner.ust_id, name=partner.name, land=partner.land
    )
    if gefunden.kontakt is None:
        return None
    if partner.plz and kontakt.plz and partner.plz.strip() != kontakt.plz.strip():
        hinweise.append(
            f"{anlass}: Kunde über den Bezug auf Rechnung {nummer} erkannt (Debitor "
            f"{kontakt.debitor_konto}) — die Anschrift der Gutschrift/Korrektur "
            f"({partner.plz} {partner.ort or ''}) weicht vom Kontakt ab "
            f"({kontakt.plz} {kontakt.ort or ''}): Anschrift im Kontakt prüfen "
            f"(accounti kontakte zeigen {kontakt.debitor_konto})"
        )
    return KontaktTreffer(kontakt, neu=False, merkmal=f"Bezug auf {nummer} (BT-25)")


def _mit_rechnung_verrechnen(
    session: Session,
    gutschrift: OffenerPosten,
    nummer: str,
    tag: date,
    hinweise: list[str],
) -> OffenerPosten:
    """Gutschrift/Korrektur mit Bezug (BT-25) gegen die noch offene Rechnung desselben
    Kunden verrechnen — beide stehen auf demselben Debitor (keine Buchung)."""
    if gutschrift.restbetrag >= 0:
        return gutschrift
    offen = [
        p
        for p in lade_posten(
            session,
            richtung=PostenRichtung.FORDERUNG,
            status={PostenStatus.OFFEN, PostenStatus.TEILBEZAHLT},
        )
        if p.belegnummer == nummer
        and p.kontakt_id == gutschrift.kontakt_id
        and p.restbetrag > 0
    ]
    if len(offen) != 1:
        kontakte = {k.id: k for k in lade_kontakte(session)}
        fremd = sorted(
            {
                kontakte[p.kontakt_id].debitor_konto or kontakte[p.kontakt_id].name
                for p in lade_posten(session, richtung=PostenRichtung.FORDERUNG)
                if p.belegnummer == nummer
                and p.kontakt_id != gutschrift.kontakt_id
                and p.kontakt_id in kontakte
            }
        )
        eigen = kontakte.get(gutschrift.kontakt_id)
        if not offen and fremd and eigen is not None:
            hinweise.append(
                f"nicht mit Rechnung {nummer} verrechnet: sie steht auf Debitor "
                f"{', '.join(fremd)}, die Gutschrift auf {eigen.debitor_konto} "
                "(anderer Kunde) — Bezug prüfen"
            )
        return gutschrift
    (rechnung,) = offen
    try:
        (v, *_) = verrechne_posten(
            session,
            [gutschrift, rechnung],
            tag,
            grund=f"{gutschrift.belegnummer} bezieht sich auf {nummer} (BT-25)",
        )
    except VerrechnungError as fehler:
        hinweise.append(f"nicht mit Rechnung {nummer} verrechnet: {fehler}")
        return gutschrift
    rest = rechnung.restbetrag - v.betrag
    hinweise.append(
        f"mit Rechnung {nummer} verrechnet: {v.betrag:.2f} € (Rest {nummer} "
        f"{rest:.2f} €) — accounti opos liste"
    )
    neuer_rest = gutschrift.restbetrag + v.betrag
    return gutschrift.model_copy(
        update={
            "restbetrag": neuer_rest,
            "status": PostenStatus.AUSGEGLICHEN
            if neuer_rest == 0
            else PostenStatus.TEILBEZAHLT,
        }
    )


def _fester_tag(tag: date) -> Callable[[str | None], date]:
    return lambda _: tag


def _steuertag_fuer(
    belegdatum: date, leistungsdatum: date | None, korrektur: bool
) -> Callable[[str | None], date]:
    """Buchungstag je Steuerkategorie einer Ausgangsrechnung (leistungszeitpunkt)."""
    return lambda kategorie: steuertag(
        belegdatum, leistungsdatum, kategorie, korrektur
    )[0]


def _pruefe_sperre(
    session: Session,
    beleg: Beleg,
    anlass: str,
    tag: date,
    belegdatum: date,
    gewinnermittlung: str | None,
    *,
    eingang: bool,
    gutschrift: Literal["vorsteuer", "selbst"] | None = None,
) -> None:
    """Abgeschlossenes Jahr oder festgeschriebener Monat am Buchungstag → Fehler
    (``gutschrift``: was eine Lieferanten-Gutschrift mindert, siehe
    ``_gutschrift_eingang``)."""
    if ist_gesperrt(session, tag.year) and (tag == belegdatum or not eingang):
        art = "Belegdatum" if tag == belegdatum else "Leistungsdatum"
        msg = (
            f"{anlass}: {art} {tag:%d.%m.%Y} liegt im abgeschlossenen "
            f"Geschäftsjahr {tag.year} — verbuchen erst nach accounti abschluss "
            f"oeffnen --jahr {tag.year}"
            + (
                " (bei Einnahmenüberschussrechnung auch auf einen offenen Tag: "
                "--buchungsdatum offen)"
                if eingang
                else ""
            )
        )
        raise JahrGesperrtError(msg)
    if (fehler := sperrfehler(session.connection(), tag)) is not None:
        if eingang and gutschrift is not None:
            wege = _spaetere_wege(session, beleg, belegdatum, gewinnermittlung)
            ausweg = (
                f" — eine Gutschrift mindert {_MINDERT[gutschrift][0]} im Zeitraum "
                f"der Änderung ({belegdatum:%m/%Y}, § 17 Abs. 1 S. 8 UStG): den Monat "
                f"mit Grund öffnen (accounti periode oeffnen {belegdatum:%Y-%m} "
                "--grund …) und zum Belegdatum buchen"
                + (
                    f"; mit --buchungsdatum {wege} später gebucht, geht sie zur Prüfung"
                    if wege
                    else ""
                )
            )
        elif eingang:
            ausweg = (
                " — eine Eingangsrechnung mit --buchungsdatum eingang, offen oder "
                "JJJJ-MM-TT in einen offenen Zeitraum desselben Geschäftsjahres buchen"
            )
        else:
            ausweg = (
                f" — die Umsatzsteuer gehört in den Voranmeldungszeitraum {tag:%m/%Y} "
                "(§ 13 Abs. 1 UStG), nicht still in einen späteren: Monat mit Grund "
                f"öffnen (accounti periode oeffnen {tag:%Y-%m} --grund …), verbuchen "
                f"und die Voranmeldung {tag:%m/%Y} berichtigen"
            )
        raise type(fehler)(f"{anlass}: gebucht am {tag:%d.%m.%Y}: {fehler}{ausweg}")


def _abgegebene_voranmeldung(
    session: Session, tag: date, *, minderung: bool = False
) -> str | None:
    """Ist die Voranmeldung des Zeitraums schon übermittelt (Monat oder Quartal), fehlt
    die Umsatzsteuer dieser Buchung darin — sie ist zu berichtigen (§ 153 Abs. 1 AO,
    berichtigte Anmeldung mit Kz 10). Eine ``minderung`` (Gutschrift, Korrektur nach
    unten) verkürzt keine Steuer: keine Pflicht nach § 153 Abs. 1 AO, die berichtigte
    Anmeldung ist nur möglich (§ 164 Abs. 2, § 168 AO) — sonst erfasst sie die
    Jahreserklärung. Festgeschriebene Monate lehnt ``_pruefe_sperre`` vorher ab."""
    for zeitraum in (
        Zeitraum.monat_von(tag),
        Zeitraum(tag.year, quartal=(tag.month - 1) // 3 + 1),
    ):
        if not abgegeben(session, Meldeart.USTVA, str(zeitraum)):
            continue
        if minderung:
            return (
                f"Die Voranmeldung {zeitraum} ist schon übermittelt — die Minderung "
                f"dieser Gutschrift/Korrektur (gebucht am {tag:%d.%m.%Y}) fehlt darin: "
                "eine berichtigte Voranmeldung kann sie geltend machen (accounti ustva "
                f"freigeben --period {zeitraum}, dann uebermitteln), sonst erfasst sie "
                "die Jahreserklärung — keine Pflicht nach § 153 Abs. 1 AO, die Steuer "
                "sinkt"
            )
        return (
            f"Die Voranmeldung {zeitraum} ist schon übermittelt — die Umsatzsteuer "
            f"dieser Rechnung (gebucht am {tag:%d.%m.%Y}) fehlt darin: berichtigte "
            f"Voranmeldung abgeben (accounti ustva freigeben --period {zeitraum}, "
            "dann uebermitteln; § 153 Abs. 1 AO)"
        )
    return None


def _buchungstag(
    session: Session,
    beleg: Beleg,
    belegdatum: date,
    buchungsdatum: Buchungsdatum,
    anlass: str,
    gewinnermittlung: str | None = None,
    *,
    gutschrift: Literal["vorsteuer", "selbst"] | None = None,
) -> tuple[date, str | None]:
    """(Buchungsdatum, Hinweis) — Belegdatum, Eingang, erster offener Tag oder fest.

    Ein anderes Datum als das Belegdatum gilt nur für Belege, deren Zeitraum gesperrt
    ist — der Rest eines Laufs bleibt beim Belegdatum. „Eingang“ ist der Zeitpunkt, zu
    dem accounti den Beleg erfasst hat (``eingegangen_am``, z.B. der Import). Bei
    Bilanzierung bleibt die Buchung im Geschäftsjahr des Belegs (§ 252 Abs. 1 Nr. 5
    HGB, GoBD Rz. 51) — ebenso, wenn die Gewinnermittlung nicht angegeben ist
    (``None``); nur ausdrücklich ``euer`` bucht über den Jahreswechsel."""
    eingegangen = beleg.eingegangen_am.date()
    if (
        buchungsdatum == "beleg"
        or sperrfehler(session.connection(), belegdatum) is None
    ):
        if beleg.belegart is not Belegart.EINGANGSRECHNUNG:
            return belegdatum, None
        return belegdatum, _hinweis_eingang_spaeter(
            belegdatum, eingegangen, anlass, gewinnermittlung
        )
    if buchungsdatum == "eingang":
        tag = eingegangen
    elif buchungsdatum == "offen":
        tag = erster_offener_tag(session.connection(), max(belegdatum, eingegangen))
    else:
        assert isinstance(buchungsdatum, date)
        tag = buchungsdatum
    if tag < belegdatum:
        raise VerbuchungError(
            f"{anlass}: Buchungsdatum {tag:%d.%m.%Y} liegt vor dem Belegdatum "
            f"{belegdatum:%d.%m.%Y}"
        )
    if tag == belegdatum:
        return tag, None
    if tag.year != belegdatum.year and gewinnermittlung != "euer":
        if ist_gesperrt(session, belegdatum.year):
            oeffnen = (
                f"das Geschäftsjahr mit Grund öffnen (accounti abschluss oeffnen "
                f"--jahr {belegdatum.year})"
            )
        else:
            oeffnen = (
                f"den Monat mit Grund öffnen (accounti periode oeffnen "
                f"{belegdatum:%Y-%m} --grund …)"
            )
        ohne_angabe = (
            " — die Gewinnermittlung ist nicht angegeben (abschluss.gewinnermittlung: "
            "bilanz oder euer in der Konfiguration); ohne Angabe gilt der Schutz der "
            "Bilanzierung"
            if gewinnermittlung is None
            else ""
        )
        if gutschrift is not None:
            # Gutschrift: kein 1548-Weg, die Minderung gehört in den Zeitraum der
            # Änderung (§ 17 Abs. 1 S. 8 UStG; Nachprüfung C, N-2)
            art = "die Gutschrift"
            vorsteuer = (
                f"{_MINDERT[gutschrift][0]} {_MINDERT[gutschrift][2]} sich im Zeitraum "
                f"der Änderung ({belegdatum:%m/%Y}, § 17 Abs. 1 S. 8 UStG)"
            )
        else:
            art = "die Rechnung"
            vorsteuer = (
                "die Vorsteuer ist erst im Folgejahr abziehbar (§ 15 Abs. 1 Nr. 1 "
                "UStG): accounti bucht sie dann auf 1548 „Vorsteuer im Folgejahr "
                "abziehbar“ (SKR04 1434) und zum ersten offenen Tag des Eingangsmonats "
                "auf das Vorsteuerkonto um"
            )
        raise VerbuchungError(
            f"{anlass}: Buchungsdatum {tag:%d.%m.%Y} liegt im Geschäftsjahr "
            f"{tag.year}, {art} vom {belegdatum:%d.%m.%Y} gehört mit Aufwand "
            f"und Verbindlichkeit ins Geschäftsjahr {belegdatum.year} (§ 252 Abs. 1 "
            f"Nr. 5 HGB, GoBD Rz. 51) — {oeffnen} und zum Belegdatum buchen; "
            f"{vorsteuer}{ohne_angabe}"
        )
    # Vorsteuer: im Zeitraum, in dem Leistung und Rechnung vorliegen — ohne Wahlrecht
    # (§ 15 Abs. 1 Nr. 1 UStG); maßgeblich ist hier das spätere von Beleg und Eingang
    massgeblich = max(belegdatum, eingegangen)
    gebucht = (
        f"gebucht am {tag:%d.%m.%Y} statt zum Belegdatum {belegdatum:%d.%m.%Y} "
        f"(Eingang {eingegangen:%d.%m.%Y})"
    )
    if (tag.year, tag.month) == (massgeblich.year, massgeblich.month):
        hinweis = (
            f"{gebucht} — die Vorsteuer zählt in diesem Voranmeldungszeitraum "
            "(§ 15 Abs. 1 Nr. 1 UStG: Rechnung liegt vor)"
        )
    elif tag < massgeblich:
        hinweis = (
            f"{gebucht} — Achtung: die Vorsteuer zählt erst ab dem Zeitraum, in dem "
            f"die Rechnung vorliegt ({massgeblich:%m/%Y}); gebucht am "
            f"{tag:%d.%m.%Y} zählt sie zu früh (§ 15 Abs. 1 Nr. 1 UStG) — zum ersten "
            "offenen Tag ab Eingang buchen: --buchungsdatum offen"
        )
    elif sperrfehler(session.connection(), massgeblich) is not None:
        hinweis = (
            f"{gebucht} — die Vorsteuer gehört in den Zeitraum, in dem die Rechnung "
            f"vorlag ({massgeblich:%m/%Y}), der ist festgeschrieben: dessen "
            "Voranmeldung ist gegebenenfalls zu berichtigen (§ 15 Abs. 1 Nr. 1 UStG, "
            "kein Wahlrecht beim Zeitpunkt)"
        )
    else:
        hinweis = (
            f"{gebucht} — Achtung: die Vorsteuer gehört in den Voranmeldungszeitraum "
            f"{massgeblich:%m/%Y}, in dem die Rechnung vorlag (offen); gebucht am "
            f"{tag:%d.%m.%Y} zählt sie erst später (§ 15 Abs. 1 Nr. 1 UStG, kein "
            "Wahlrecht) — zum ersten offenen Tag buchen: --buchungsdatum offen"
        )
    if tag.year != belegdatum.year:  # Einnahmenüberschussrechnung
        hinweis += (
            f"; gebucht im Geschäftsjahr {tag.year} statt {belegdatum.year} — bei der "
            "Einnahmenüberschussrechnung zählt der Abfluss (§ 11 EStG)"
        )
    return tag, hinweis


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
    ustid_max_alter_tage: int = 30,
    buchungsdatum: Buchungsdatum = "beleg",
    gewinnermittlung: str | None = None,
) -> Verbuchungslauf:
    """Verbucht alle erfassten, noch nicht verbuchten Rechnungen.

    Jeder Beleg läuft in einem eigenen Savepoint: Scheitert einer, bleiben die
    anderen verbucht und der Fehler steht im Ergebnis — auch eine Rechnung, deren
    Belegdatum in einem abgeschlossenen Geschäftsjahr liegt (Baustein 12).
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
                    session,
                    beleg,
                    einstellungen,
                    archiv,
                    regelwerk,
                    eigene_firma,
                    ustid_max_alter_tage,
                    buchungsdatum,
                    gewinnermittlung,
                )
            lauf.verbucht.append(verbuchung)
        except (VerbuchungError, JahrGesperrtError, ValueError) as fehler:
            lauf.fehler.append((beleg, str(fehler)))
    return lauf
