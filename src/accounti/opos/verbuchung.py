"""Beleg → Buchung auf ein Personenkonto + offener Posten.

Eingang:  Aufwand an Kreditor (Vorsteuer per BU-Schlüssel)
Ausgang:  Debitor an Erlös   (Erlöskonto nach Steuerkategorie der E-Rechnung)

Beträge und Steuer kommen aus dem Beleg — gerechnet wird hier nichts neu.

Eingangsrechnungen werden auf das Belegdatum gebucht. Eine Eingangsrechnung, die erst
nach der Festschreibung ihres Monats eintrifft, bucht ``buchungsdatum`` auf das
Eingangsdatum (``eingang``), den ersten offenen Tag ab dem späteren von Beleg- und
Eingangsdatum (``offen``) oder einen festen Tag — nur Belege, deren Zeitraum gesperrt
ist; die Vorsteuer gehört nach § 15 Abs. 1 Nr. 1 UStG ohnehin in den Zeitraum, in dem
die Rechnung vorliegt. Bei Bilanzierung nie über den Geschäftsjahreswechsel.

Ausgangsrechnungen werden zum umsatzsteuerlichen Zeitpunkt gebucht
(``steuer/leistungszeitpunkt.py``): zum Leistungsdatum, wenn die Leistung in einem
früheren Monat lag (§ 13 Abs. 1 Nr. 1 Buchst. a UStG), eine innergemeinschaftliche
Lieferung im Rechnungsmonat, spätestens am Ende des Folgemonats (§ 13 Abs. 1 Nr. 6
UStG), eine Gutschrift/Korrektur zu ihrem Datum (§ 17 Abs. 1 Satz 7 UStG). Ist dieser
Monat festgeschrieben, wird nicht still später gebucht: Der Monat ist zu öffnen und die
Voranmeldung zu berichtigen. Ist die Voranmeldung des Zeitraums schon übermittelt, der
Monat aber offen, weist die Verbuchung auf die Berichtigung hin (§ 153 Abs. 1 AO). Eine
Gutschrift mit Bezug (BT-25) wird mit der noch offenen Rechnung desselben Kunden
verrechnet.

Offener Posten, Fälligkeit und Skonto bleiben beim Belegdatum.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy.orm import Session

from accounti.belege.archiv import BelegArchiv
from accounti.belege.erkennung import erkenne_format
from accounti.belege.kanaele import RohBeleg
from accounti.buchung.mit_beleg import sachkonto_fuer_beleg
from accounti.db.repo_abschluss import ist_gesperrt
from accounti.db.repository import (
    lade_belege,
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
from accounti.kontakte.erkennung import finde_kontakt
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
from accounti.steuer.leistungszeitpunkt import steuertag
from accounti.steuer.umsatzsteuer import OSS_ERLOES_KONTEN_SKR03
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
class _Gruppe:
    konto: str
    schluessel: int | None
    pruefen: bool
    tag: date
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
        # ohne Positionen: eine Gruppe über die Belegsummen
        konto = sachkonto if eingang else _ERLOES_UNBEKANNT
        g = _Gruppe(konto, None, True, tag_fuer(None))
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
            konto, schluessel = _ERLOES_STEUERFREI[kategorie], None
            # K/AE nur mit bestätigter USt-IdNr. des Käufers automatisch
            pruefen = kategorie in USTID_KATEGORIEN and not ustid_bestaetigt
        elif satz in _ERLOES_STEUERPFLICHTIG and kategorie in ("S", None):
            konto, schluessel = _ERLOES_STEUERPFLICHTIG[satz], _UST_SCHLUESSEL[satz]
            pruefen = False
        elif kategorie == "S" and satz:
            # anderer Satz als 19/7 %: OSS (Satz des Bestimmungslands)
            konto = OSS_ERLOES_KONTEN_SKR03.get(land, "8320")
            schluessel, pruefen = None, True
        else:
            konto, schluessel, pruefen = _ERLOES_UNBEKANNT, None, True
        tag = tag_fuer(kategorie)
        g = gruppen.setdefault(
            (konto, schluessel, tag), _Gruppe(konto, schluessel, pruefen, tag)
        )
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
        gebucht_am, hinweis_datum = _buchungstag(
            session, beleg, belegdatum, buchungsdatum, anlass, gewinnermittlung
        )
        hinweise += [hinweis_datum] if hinweis_datum else []
        _pruefe_sperre(session, anlass, gebucht_am, belegdatum, eingang=True)
        tag_fuer = _fester_tag(gebucht_am)
    else:
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
            _pruefe_sperre(session, anlass, tag, belegdatum, eingang=False)
            berichtigung = _abgegebene_voranmeldung(session, tag)
            if berichtigung and berichtigung not in hinweise:
                hinweise.append(berichtigung)

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
    text = f"{treffer.kontakt.name} {beleg.belegnummer or ''}".strip()[:60]

    ustid_bestaetigt = True
    if rechnung is not None and any(
        kategorie in USTID_KATEGORIEN for kategorie in _kategorien(beleg, rechnung)
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
    for g in _gruppen(
        beleg,
        eingang,
        sachkonto,
        sachkonto_pruefen,
        rechnung,
        treffer.kontakt.land,
        tag_fuer,
        ustid_bestaetigt,
    ):
        soll, haben = (g.konto, personenkonto) if eingang else (personenkonto, g.konto)
        if g.netto < 0:  # Gutschrift: Seiten tauschen, Beträge positiv
            soll, haben = haben, soll
        buchung = Buchungssatz(
            beleg_id=beleg.id,
            datum=g.tag,
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
    if not eingang and rechnung is not None and rechnung.vorgaenger_nummer:
        posten = _mit_rechnung_verrechnen(
            session, posten, rechnung.vorgaenger_nummer, belegdatum, hinweise
        )
    return Verbuchung(beleg, treffer, posten, buchungen, hinweise)


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
    session: Session, anlass: str, tag: date, belegdatum: date, *, eingang: bool
) -> None:
    """Abgeschlossenes Jahr oder festgeschriebener Monat am Buchungstag → Fehler."""
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
        ausweg = (
            " — eine Eingangsrechnung mit --buchungsdatum eingang, offen oder "
            "JJJJ-MM-TT in einen offenen Zeitraum desselben Geschäftsjahres buchen"
            if eingang
            else f" — die Umsatzsteuer gehört in den Voranmeldungszeitraum {tag:%m/%Y} "
            "(§ 13 Abs. 1 UStG), nicht still in einen späteren: Monat mit Grund öffnen "
            f"(accounti periode oeffnen {tag:%Y-%m} --grund …), verbuchen und die "
            f"Voranmeldung {tag:%m/%Y} berichtigen"
        )
        raise type(fehler)(f"{anlass}: gebucht am {tag:%d.%m.%Y}: {fehler}{ausweg}")


def _abgegebene_voranmeldung(session: Session, tag: date) -> str | None:
    """Ist die Voranmeldung des Zeitraums schon übermittelt (Monat oder Quartal), fehlt
    die Umsatzsteuer dieser Buchung darin — sie ist zu berichtigen (§ 153 Abs. 1 AO,
    berichtigte Anmeldung mit Kz 10). Festgeschriebene Monate lehnt ``_pruefe_sperre``
    vorher ab."""
    for zeitraum in (
        Zeitraum.monat_von(tag),
        Zeitraum(tag.year, quartal=(tag.month - 1) // 3 + 1),
    ):
        if abgegeben(session, Meldeart.USTVA, str(zeitraum)):
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
        return belegdatum, None
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
        raise VerbuchungError(
            f"{anlass}: Buchungsdatum {tag:%d.%m.%Y} liegt im Geschäftsjahr "
            f"{tag.year}, die Rechnung vom {belegdatum:%d.%m.%Y} gehört mit Aufwand "
            f"und Verbindlichkeit ins Geschäftsjahr {belegdatum.year} (§ 252 Abs. 1 "
            f"Nr. 5 HGB, GoBD Rz. 51) — {oeffnen} und zum Belegdatum buchen; die "
            "Vorsteuer ist erst im Folgejahr abziehbar (§ 15 Abs. 1 Nr. 1 UStG) und "
            "gehört dann auf 1548 „Vorsteuer im Folgejahr abziehbar“ (SKR03) — das "
            f"bucht accounti nicht selbst{ohne_angabe}"
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
