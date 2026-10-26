"""Beleg → Buchung auf ein Personenkonto + offener Posten.

Eingang:  Aufwand an Kreditor (Vorsteuer per BU-Schlüssel)
Ausgang:  Debitor an Erlös   (Erlöskonto nach Steuerkategorie der E-Rechnung)

Beträge und Steuer kommen aus dem Beleg — gerechnet wird hier nur, was der Beleg
nicht nennen darf: die Steuer bei § 13b UStG und beim ig. Erwerb (Steuerfall AE bzw. K,
Schlüssel 94 bzw. 19 zur Prüfung, ``buchung/steuergruppe.py``). Eine Steuer ohne Satz
geht brutto und zur Prüfung auf das Konto, nie netto gegen einen Brutto-Posten.

Gebucht wird auf das Belegdatum. Eine Eingangsrechnung, die erst nach der
Festschreibung ihres Monats eintrifft, bucht ``buchungsdatum`` auf das Eingangsdatum
(``eingang``), den ersten offenen Tag ab dem späteren von Beleg- und Eingangsdatum
(``offen``) oder einen festen Tag — nur Belege, deren Zeitraum gesperrt ist; die
Vorsteuer gehört nach § 15 Abs. 1 Nr. 1 UStG ohnehin in den Zeitraum, in dem die
Rechnung vorliegt. Bei Bilanzierung nie über den Geschäftsjahreswechsel. Offener
Posten, Fälligkeit und Skonto bleiben beim Belegdatum.

Geht die Rechnung erst im Folgejahr ein (Bilanz: Aufwand und Verbindlichkeit bleiben im
alten Jahr), bucht accounti die Vorsteuer auf „Vorsteuer im Folgejahr abziehbar“
(SKR03 1548, SKR04 1434) und zum ersten offenen Tag des Eingangsmonats auf das
Vorsteuerkonto um — erst dort zählt sie in der Voranmeldung (§ 15 Abs. 1 S. 1 Nr. 1
UStG, Abschn. 15.2 Abs. 2 S. 7 UStAE: Leistung und Rechnung müssen vorliegen).
"""

from __future__ import annotations

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
    Gruppe,
)
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
from accounti.kontakte.erkennung import finde_kontakt, land_aus_kennung
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
from accounti.steuer.eu_steuersaetze import ist_eu_land
from accounti.steuer.kennziffern import VORSTEUER_FOLGEJAHR
from accounti.steuer.umsatzsteuer import OSS_ERLOES_KONTEN_SKR03, OSS_UST_KONTEN_SKR03

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
) -> list[Gruppe]:
    gruppen: dict[tuple[str, int | None], Gruppe] = {}
    positionen = beleg.positionen or []
    kategorien = _kategorien(beleg, rechnung)
    if not positionen:
        # ohne Positionen: eine Gruppe über die Belegsummen (ohne Satz: brutto)
        g = Gruppe(sachkonto if eingang else _ERLOES_UNBEKANNT, None, True)
        if beleg.netto is not None:
            g.addiere(beleg.netto, beleg.steuer or NULL)
        else:
            g.addiere(beleg.brutto or NULL, NULL)
        return [g]

    def gruppe(konto: str, schluessel: int | None, pruefen: bool) -> Gruppe:
        g = gruppen.setdefault((konto, schluessel), Gruppe(konto, schluessel, pruefen))
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
            gruppe(OSS_ERLOES_KONTEN_SKR03.get(land, "8320"), None, True).addiere(
                p.netto, NULL
            )
            gruppe(OSS_UST_KONTEN_SKR03.get(land, "1779"), None, True).addiere(
                steuer, NULL
            )
            continue
        else:
            konto, schluessel, pruefen = _ERLOES_UNBEKANNT, None, True
        gruppe(konto, schluessel, pruefen).addiere(p.netto, steuer)
    for g in gruppen.values():
        g.berechne_selbst()
    return list(gruppen.values())


def _steuerhinweise(gruppen: list[Gruppe], anlass: str, land: str) -> list[str]:
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
        # ein gleichnamiger Kunde ist derselbe nur bei gleicher PLZ oder E-Mail
        treffer = kontakt_fuer(
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

    hinweise = [hinweis_datum] if hinweis_datum else []
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
        ustid_bestaetigt,
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
        pruefen = g.pruefen or widerspruch
        status = BuchungStatus.ZUR_PRUEFUNG if pruefen else BuchungStatus.AUTO_GEBUCHT

        def buche(
            soll: str,
            haben: str,
            betrag: Decimal,
            schluessel: int | None = None,
            steuer: Decimal | None = None,
            datum: date = gebucht_am,
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

        if folgejahr is not None and g.schluessel in (8, 9) and g.steuer:
            konto_folgejahr, umbuchung_am, kr = folgejahr
            vorsteuer = kr.steuerkonto(g.schluessel) or konto_folgejahr
            steuer = abs(g.steuer)
            buche(soll, haben, abs(g.netto))
            # Vorsteuer: im alten Jahr nur als „im Folgejahr abziehbar“ …
            if gedreht:
                buche(personenkonto, konto_folgejahr, steuer)
                buche(konto_folgejahr, vorsteuer, steuer, datum=umbuchung_am)
            else:
                buche(konto_folgejahr, personenkonto, steuer)
                # … und abziehbar im Zeitraum, in dem die Rechnung vorliegt
                buche(vorsteuer, konto_folgejahr, steuer, datum=umbuchung_am)
            hinweise.append(
                f"{anlass}: Rechnung vom {belegdatum:%d.%m.%Y} erst am "
                f"{beleg.eingegangen_am:%d.%m.%Y} erfasst — Vorsteuer "
                f"{betrag_de(steuer)} € auf "
                f"{konto_folgejahr} „Vorsteuer im Folgejahr abziehbar“ und zum "
                f"{umbuchung_am:%d.%m.%Y} auf {vorsteuer} umgebucht: abziehbar in "
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
    return Verbuchung(beleg, treffer, posten, buchungen, hinweise)


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
        f"{eingegangen:%m/%Y} (§ 15 Abs. 1 Nr. 1 UStG, kein Wahlrecht)"
    )


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
        raise VerbuchungError(
            f"{anlass}: Buchungsdatum {tag:%d.%m.%Y} liegt im Geschäftsjahr "
            f"{tag.year}, die Rechnung vom {belegdatum:%d.%m.%Y} gehört mit Aufwand "
            f"und Verbindlichkeit ins Geschäftsjahr {belegdatum.year} (§ 252 Abs. 1 "
            f"Nr. 5 HGB, GoBD Rz. 51) — {oeffnen} und zum Belegdatum buchen; die "
            "Vorsteuer ist erst im Folgejahr abziehbar (§ 15 Abs. 1 Nr. 1 UStG): "
            "accounti bucht sie dann auf 1548 „Vorsteuer im Folgejahr abziehbar“ "
            "(SKR04 1434) und zum ersten offenen Tag des Eingangsmonats auf das "
            f"Vorsteuerkonto um{ohne_angabe}"
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
