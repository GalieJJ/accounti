"""Ablauf der Umsatzsteuer-Voranmeldung: vorbereiten → freigeben → übermitteln.

Vorbereiten heißt: Kennziffern aus den Buchungen ermitteln (``steuer.kennziffern``)
und plausibilisieren (``steuer.plausibilitaet``) — mit den Daten aus der Datenbank
(Kontakte, offene Posten, USt-IdNr.-Protokoll) und der Konfiguration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from accounti import __version__
from accounti.belege.archiv import BelegArchiv
from accounti.db.repo_elster import lade_uebermittlungen
from accounti.db.repository import (
    lade_bankkonten,
    lade_buchungen,
    lade_kontakte,
    lade_posten,
)
from accounti.elster.datensatz import (
    TEST_HERSTELLER_ID,
    TESTMERKER,
    Absender,
    Kopf,
    datenart_version,
    pruefe_datensatz,
    ustva_xml,
)
from accounti.elster.freigabe import FreigabeError, offene_freigabe, ustva_inhalt
from accounti.elster.konfiguration import (
    ElsterEinstellungen,
    KonfigurationError,
    bereiche,
    lade_mandant,
)
from accounti.elster.protokoll import neuer_eintrag, protokolliere
from accounti.elster.steuernummer import SteuernummerError, elster_steuernummer
from accounti.elster.uebermittlung import Ergebnis, Uebermittler, UebermittlungError
from accounti.konfiguration import Buchhaltung
from accounti.kontakte.ustid import Bewertung, aktuelle_bestaetigung
from accounti.models import Buchungssatz, Kontakt
from accounti.models.elster import Meldeart, Modus, Uebermittlung
from accounti.steuer.kennziffern import Ermittlung, Kontenplan, ermittle
from accounti.steuer.plausibilitaet import (
    Befund,
    Schwellen,
    Schweregrad,
    freigabe_gesperrt,
    plausibilisiere,
)
from accounti.steuer.voranmeldung import UStVoranmeldung
from accounti.steuer.zeitraum import Zeitraum


def kontenplan(
    buchhaltung: Buchhaltung,
    einstellungen: ElsterEinstellungen,
    bank_sachkonten: set[str] | None = None,
) -> Kontenplan:
    return Kontenplan(
        kontenrahmen=buchhaltung.kontenrahmen.upper(),
        debitoren=(buchhaltung.debitoren_von, buchhaltung.debitoren_bis),
        kreditoren=(buchhaltung.kreditoren_von, buchhaltung.kreditoren_bis),
        geldkonten=frozenset({buchhaltung.bank_konto, *(bank_sachkonten or set())}),
        steuerrelevant=bereiche(einstellungen.steuerrelevante_konten),
        kennziffern_konten=dict(einstellungen.kennziffern_konten),
    )


@dataclass
class Vorbereitung:
    zeitraum: Zeitraum
    ermittlung: Ermittlung
    befunde: list[Befund]

    @property
    def voranmeldung(self) -> UStVoranmeldung:
        return self.ermittlung.voranmeldung

    @property
    def gesperrt(self) -> bool:
        return freigabe_gesperrt(self.befunde)

    @property
    def fehler(self) -> list[Befund]:
        return [b for b in self.befunde if b.schweregrad is Schweregrad.FEHLER]


def _zeitraum_befunde(zeitraum: Zeitraum, einst: ElsterEinstellungen) -> list[Befund]:
    if zeitraum.art == einst.voranmeldungszeitraum:
        return []
    text = (
        f"{zeitraum} ist kein Voranmeldungszeitraum: elster.voranmeldungszeitraum ist "
        f"„{einst.voranmeldungszeitraum}“"
    )
    return [Befund("zeitraum", Schweregrad.FEHLER, text)]


class _Daten:
    """Einmal geladen, mehrfach ermittelt (Zeitraum, Vorperiode, Vorjahr)."""

    def __init__(
        self,
        session: Session,
        buchhaltung: Buchhaltung,
        einstellungen: ElsterEinstellungen,
    ) -> None:
        self.buchungen: list[Buchungssatz] = lade_buchungen(session)
        self.kontakte: list[Kontakt] = lade_kontakte(session)
        self.beleg_kontakte = {p.beleg_id: p.kontakt_id for p in lade_posten(session)}
        bank = {k.sachkonto for k in lade_bankkonten(session)}
        self.plan = kontenplan(buchhaltung, einstellungen, bank)

    def ermittle(self, zeitraum: Zeitraum) -> Ermittlung:
        return ermittle(
            self.buchungen, zeitraum, self.plan, self.kontakte, self.beleg_kontakte
        )

    def vergleich(self, zeitraum: Zeitraum) -> UStVoranmeldung | None:
        e = self.ermittle(zeitraum)
        return e.voranmeldung if e.zugeordnet else None


def bereite_vor(
    session: Session,
    zeitraum: Zeitraum,
    *,
    buchhaltung: Buchhaltung,
    einstellungen: ElsterEinstellungen,
    ustid_max_alter_tage: int = 30,
    oss_aktiv: bool = False,
) -> Vorbereitung:
    """Kennziffern und Befunde eines Voranmeldungszeitraums.

    Wurde der Zeitraum schon einmal erfolgreich abgegeben, ist die neue Anmeldung eine
    berichtigte (Kz 10) — sie tritt neben die alte.
    """
    daten = _Daten(session, buchhaltung, einstellungen)
    e = daten.ermittle(zeitraum)
    e.voranmeldung.berichtigt = abgegeben(session, Meldeart.USTVA, str(zeitraum))

    def bestaetigung(ust_id: str | None, stichtag: date) -> Bewertung:
        return aktuelle_bestaetigung(session, ust_id, stichtag, ustid_max_alter_tage)

    befunde = _zeitraum_befunde(zeitraum, einstellungen) + plausibilisiere(
        e,
        bestaetigung=bestaetigung,
        plan=daten.plan,
        kontakte=daten.kontakte,
        vorperiode=daten.vergleich(zeitraum.vorperiode()),
        vorjahr=daten.vergleich(zeitraum.vorjahr()),
        oss_aktiv=oss_aktiv,
        schwellen=Schwellen(
            abweichung_prozent=einstellungen.abweichung_prozent,
            abweichung_mindestens=einstellungen.abweichung_mindestens,
        ),
    )
    rang = {Schweregrad.FEHLER: 0, Schweregrad.WARNUNG: 1, Schweregrad.HINWEIS: 2}
    return Vorbereitung(zeitraum, e, sorted(befunde, key=lambda b: rang[b.schweregrad]))


def abgegeben(session: Session, art: Meldeart, zeitraum: str) -> bool:
    """Gibt es für den Zeitraum schon eine erfolgreiche echte Abgabe?"""
    return any(
        u.erfolgreich for u in lade_uebermittlungen(session, art, zeitraum, Modus.ECHT)
    )


@dataclass(frozen=True)
class Kontext:
    """Was der Datensatz über Absender und Software wissen muss."""

    steuernummer: str  # 13-stellig, ELSTER-Format
    absender: Absender
    hersteller_id: str | None  # eigene; ohne sie nur der Testmodus
    produkt_name: str = "accounti"
    produkt_version: str = __version__


def _kopf(kontext: Kontext, modus: Modus) -> Kopf:
    if modus is not Modus.PRUEFUNG and not kontext.hersteller_id:
        msg = (
            "Eigene Hersteller-ID fehlt (elster.hersteller_id) — ELSTER nimmt ohne sie "
            "weder Test- noch Echtfälle an"
        )
        raise UebermittlungError(msg)
    return Kopf(
        hersteller_id=kontext.hersteller_id or TEST_HERSTELLER_ID,
        produkt_name=kontext.produkt_name,
        produkt_version=kontext.produkt_version,
        testmerker=None if modus is Modus.ECHT else TESTMERKER,
    )


def _bericht(
    intern: list[Befund], plausi: list[Befund], ergebnis: Ergebnis | None
) -> str:
    def liste(befunde: list[Befund]) -> list[str]:
        return [f"{b.schweregrad.value}: {b.text}" for b in befunde]

    return json.dumps(
        {
            "intern": liste(intern),
            "plausibilisierung": liste(plausi),
            "eric": ergebnis.pruefbericht if ergebnis else None,
            "hinweise": list(ergebnis.hinweise) if ergebnis else [],
        },
        ensure_ascii=False,
        indent=1,
    )


def fuehre_aus(
    session: Session,
    *,
    art: Meldeart,
    zeitraum: str,
    xml: str,
    jahr: int,
    modus: Modus,
    uebermittler: Uebermittler | None,
    archiv: BelegArchiv | None,
    plausi: list[Befund],
    betrag: Decimal | None,
    berichtigt: bool,
    freigabe_id: UUID | None = None,
    freigegeben_von: str | None = None,
    jetzt: datetime | None = None,
) -> Uebermittlung:
    """Interne Prüfung, dann prüfen (Testmodus) oder senden — und protokollieren."""
    intern = pruefe_datensatz(xml, testfall=modus is not Modus.ECHT)
    fehler_intern = [b for b in intern if b.schweregrad is Schweregrad.FEHLER]
    ergebnis: Ergebnis | None = None
    weg = uebermittler.weg if uebermittler is not None else "intern"
    if fehler_intern:
        erfolgreich = False
        text = "interne Prüfung: " + "; ".join(b.text for b in fehler_intern)
        weg = "intern"
    elif modus is Modus.PRUEFUNG:
        if uebermittler is not None:
            ergebnis = uebermittler.pruefe(xml, datenart_version(jahr))
        erfolgreich = ergebnis is None or ergebnis.erfolgreich
        text = "Datensatz geprüft — nichts abgegeben"
    else:
        assert uebermittler is not None
        ergebnis = uebermittler.sende(xml, datenart_version(jahr))
        erfolgreich = ergebnis.erfolgreich
        text = (
            "Testfall übermittelt — ELSTER löscht ihn sofort"
            if modus is Modus.TESTFALL
            else "übermittelt"
        )
    if ergebnis is not None and not ergebnis.erfolgreich:
        text = f"gescheitert: {ergebnis.fehler}"
    eintrag = neuer_eintrag(
        archiv,
        art=art,
        zeitraum=zeitraum,
        modus=modus,
        weg=weg,
        datensatz=xml,
        erfolgreich=erfolgreich,
        ergebnis=text,
        pruefbericht=_bericht(intern, plausi, ergebnis),
        zeitpunkt=jetzt,
        berichtigt=berichtigt,
        freigabe_id=freigabe_id,
        freigegeben_von=freigegeben_von,
        ticket=ergebnis.ticket if ergebnis else None,
        server_antwort=ergebnis.server_antwort if ergebnis else None,
        pdf=ergebnis.pdf if ergebnis else None,
        betrag=betrag,
    )
    return protokolliere(session, eintrag)


def uebermittle(
    session: Session,
    v: Vorbereitung,
    *,
    modus: Modus,
    kontext: Kontext,
    uebermittler: Uebermittler | None,
    archiv: BelegArchiv | None,
    jetzt: datetime | None = None,
) -> Uebermittlung:
    """Voranmeldung prüfen (Testmodus), als Testfall senden oder abgeben.

    Abgegeben wird nur mit einer passenden, unverbrauchten Freigabe. Jeder Lauf landet
    im Protokoll; der Aufrufer schreibt sofort fest.
    """
    freigabe = None
    if modus is not Modus.PRUEFUNG and uebermittler is None:
        raise UebermittlungError("Kein Übermittler: ERiC ist nicht eingerichtet")
    if modus is Modus.ECHT:
        try:
            freigabe = offene_freigabe(
                session, Meldeart.USTVA, str(v.zeitraum), ustva_inhalt(v)
            )
        except FreigabeError as fehler:
            raise UebermittlungError(str(fehler)) from fehler
    kopf = _kopf(kontext, modus)
    xml = ustva_xml(
        v.voranmeldung,
        v.zeitraum,
        kontext.steuernummer,
        kontext.absender,
        kopf,
        (jetzt or datetime.now()).date(),
    )
    return fuehre_aus(
        session,
        art=Meldeart.USTVA,
        zeitraum=str(v.zeitraum),
        xml=xml,
        jahr=v.zeitraum.jahr,
        modus=modus,
        uebermittler=uebermittler,
        archiv=archiv,
        plausi=v.befunde,
        betrag=v.voranmeldung.kz83,
        berichtigt=v.voranmeldung.berichtigt,
        freigabe_id=freigabe.id if freigabe else None,
        freigegeben_von=freigabe.freigegeben_von if freigabe else None,
        jetzt=jetzt,
    )


def kontext_aus(pfad: str | Path, einstellungen: ElsterEinstellungen) -> Kontext:
    """Absender und Steuernummer aus den Abschnitten ``mandant`` und ``elster``."""
    mandant = lade_mandant(pfad)
    fehlt = [f for f in ("name", "strasse", "plz", "ort") if f not in mandant]
    if fehlt:
        felder = ", ".join(
            f"mandant.{f}" if f == "name" else f"mandant.anschrift.{f}" for f in fehlt
        )
        raise KonfigurationError(f"{pfad}: für den Datensatz fehlt {felder}")
    nummer = einstellungen.steuernummer or mandant.get("steuernummer")
    if not nummer:
        msg = f"{pfad}: Steuernummer fehlt (elster.steuernummer, mandant.steuernummer)"
        raise KonfigurationError(msg)
    try:
        steuernummer = elster_steuernummer(nummer, einstellungen.bundesland)
    except SteuernummerError as fehler:
        raise KonfigurationError(f"{pfad}: {fehler}") from fehler
    absender = Absender(
        mandant["name"], mandant["strasse"], mandant["plz"], mandant["ort"]
    )
    return Kontext(
        steuernummer=steuernummer,
        absender=absender,
        hersteller_id=einstellungen.hersteller_id,
        produkt_name=einstellungen.produkt_name,
    )
