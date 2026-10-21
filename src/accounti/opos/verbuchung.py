"""Beleg → Buchung auf ein Personenkonto + offener Posten.

Eingang:  Aufwand an Kreditor (Vorsteuer per BU-Schlüssel)
Ausgang:  Debitor an Erlös   (Erlöskonto nach Steuerkategorie der E-Rechnung)

Beträge und Steuer kommen aus dem Beleg — gerechnet wird hier nichts neu.

Gebucht wird auf das Belegdatum. Eine Eingangsrechnung, die erst nach der
Festschreibung ihres Monats eintrifft, bucht ``buchungsdatum`` auf das Eingangsdatum
(``eingang``), den ersten offenen Tag ab dem späteren von Beleg- und Eingangsdatum
(``offen``) oder einen festen Tag — nur Belege, deren Zeitraum gesperrt ist; die
Vorsteuer gehört nach § 15 Abs. 1 Nr. 1 UStG ohnehin in den Zeitraum, in dem die
Rechnung vorliegt. Bei Bilanzierung nie über den Geschäftsjahreswechsel. Offener
Posten, Fälligkeit und Skonto bleiben beim Belegdatum.
"""

from __future__ import annotations

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
    speichere_buchung,
    speichere_posten,
    verbuchte_beleg_ids,
)
from accounti.db.tabellen_abschluss import JahrGesperrtError
from accounti.db.tabellen_pruefung import erster_offener_tag, sperrfehler
from accounti.erechnung import ERechnungError, lies
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
    "AE": "8336",  # sonstige Leistung im EU-Ausland, Steuerschuld beim Empfänger
    "K": "8125",  # steuerfreie innergemeinschaftliche Lieferung
    "G": "8120",  # steuerfreie Ausfuhr
    "E": "8100",  # steuerfreie Umsätze § 4 Nr. 8 ff.
}
_ERLOES_UNBEKANNT = "8200"


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
    ustid_bestaetigt: bool = True,
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
    ustid_max_alter_tage: int = 30,
    buchungsdatum: Buchungsdatum = "beleg",
    gewinnermittlung: str = "bilanz",
) -> Verbuchung:
    eingang = beleg.belegart is Belegart.EINGANGSRECHNUNG
    rechnung = _rechnung_aus_archiv(beleg, archiv)
    anlass = f"Beleg {beleg.belegnummer or beleg.dateiname}"
    belegdatum = beleg.belegdatum or beleg.eingegangen_am.date()
    gebucht_am, hinweis_datum = _buchungstag(
        session,
        beleg,
        belegdatum,
        buchungsdatum if eingang else "beleg",
        anlass,
        gewinnermittlung,
    )
    if ist_gesperrt(session, gebucht_am.year) and gebucht_am == belegdatum:
        jahr = belegdatum.year
        msg = (
            f"{anlass}: Belegdatum {belegdatum:%d.%m.%Y} liegt im abgeschlossenen "
            f"Geschäftsjahr {jahr} — verbuchen erst nach accounti abschluss oeffnen "
            f"--jahr {jahr}"
            + (
                " (bei Einnahmenüberschussrechnung auch auf einen offenen Tag: "
                "--buchungsdatum offen)"
                if eingang
                else ""
            )
        )
        raise JahrGesperrtError(msg)
    if (fehler := sperrfehler(session.connection(), gebucht_am)) is not None:
        ausweg = (
            " — eine Eingangsrechnung mit --buchungsdatum eingang, offen oder "
            "JJJJ-MM-TT in einen offenen Zeitraum desselben Geschäftsjahres buchen"
            if eingang
            else " — eine Ausgangsrechnung gehört in den Zeitraum ihrer Leistung"
        )
        raise type(fehler)(
            f"{anlass}: gebucht am {gebucht_am:%d.%m.%Y}: {fehler}{ausweg}"
        )

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

    hinweise = [hinweis_datum] if hinweis_datum else []
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
        ustid_bestaetigt,
    ):
        soll, haben = (g.konto, personenkonto) if eingang else (personenkonto, g.konto)
        if g.netto < 0:  # Gutschrift: Seiten tauschen, Beträge positiv
            soll, haben = haben, soll
        buchung = Buchungssatz(
            beleg_id=beleg.id,
            datum=gebucht_am,
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
    return Verbuchung(beleg, treffer, posten, buchungen, hinweise)


def _buchungstag(
    session: Session,
    beleg: Beleg,
    belegdatum: date,
    buchungsdatum: Buchungsdatum,
    anlass: str,
    gewinnermittlung: str = "bilanz",
) -> tuple[date, str | None]:
    """(Buchungsdatum, Hinweis) — Belegdatum, Eingang, erster offener Tag oder fest.

    Ein anderes Datum als das Belegdatum gilt nur für Belege, deren Zeitraum gesperrt
    ist — der Rest eines Laufs bleibt beim Belegdatum. „Eingang“ ist der Zeitpunkt, zu
    dem accounti den Beleg erfasst hat (``eingegangen_am``, z.B. der Import). Bei
    Bilanzierung bleibt die Buchung im Geschäftsjahr des Belegs (§ 252 Abs. 1 Nr. 5
    HGB, GoBD Rz. 51)."""
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
    if tag.year != belegdatum.year and gewinnermittlung == "bilanz":
        raise VerbuchungError(
            f"{anlass}: Buchungsdatum {tag:%d.%m.%Y} liegt im Geschäftsjahr "
            f"{tag.year}, die Rechnung vom {belegdatum:%d.%m.%Y} gehört mit Aufwand "
            f"und Verbindlichkeit ins Geschäftsjahr {belegdatum.year} (§ 252 Abs. 1 "
            f"Nr. 5 HGB, GoBD Rz. 51) — den Monat mit Grund öffnen (accounti periode "
            f"oeffnen {belegdatum:%Y-%m} --grund …) und zum Belegdatum buchen; die "
            "Vorsteuer ist erst im Folgejahr abziehbar (§ 15 Abs. 1 Nr. 1 UStG) und "
            "gehört dann auf 1548 „Vorsteuer im Folgejahr abziehbar“ (SKR03) — das "
            "bucht accounti nicht selbst"
        )
    hinweis = (
        f"gebucht am {tag:%d.%m.%Y} statt zum Belegdatum {belegdatum:%d.%m.%Y} "
        f"(Eingang {eingegangen:%d.%m.%Y}) — die Vorsteuer zählt in diesem "
        "Voranmeldungszeitraum (§ 15 Abs. 1 Nr. 1 UStG: Rechnung liegt vor)"
    )
    if sperrfehler(session.connection(), eingegangen) is not None and tag > eingegangen:
        hinweis += (
            "; der Eingang liegt in einem festgeschriebenen Zeitraum — dessen "
            "Voranmeldung ist gegebenenfalls zu berichtigen"
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
    gewinnermittlung: str = "bilanz",
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
