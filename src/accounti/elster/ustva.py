"""Ablauf der Umsatzsteuer-Voranmeldung: vorbereiten → freigeben → übermitteln.

Vorbereiten heißt: Kennziffern aus den Buchungen ermitteln (``steuer.kennziffern``)
und plausibilisieren (``steuer.plausibilitaet``) — mit den Daten aus der Datenbank
(Kontakte, offene Posten, USt-IdNr.-Protokoll) und der Konfiguration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from accounti.db.repository import (
    lade_bankkonten,
    lade_buchungen,
    lade_kontakte,
    lade_posten,
)
from accounti.elster.konfiguration import ElsterEinstellungen, bereiche
from accounti.konfiguration import Buchhaltung
from accounti.kontakte.ustid import Bewertung, aktuelle_bestaetigung
from accounti.models import Buchungssatz, Kontakt
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
    """Kennziffern und Befunde eines Voranmeldungszeitraums."""
    daten = _Daten(session, buchhaltung, einstellungen)
    e = daten.ermittle(zeitraum)

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
