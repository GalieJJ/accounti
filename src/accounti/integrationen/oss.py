"""OSS-Quartalsmeldung aus den gebuchten Marktplatz-Erlösen, gerechnet von steuer.oss.

Die Marktplatz-Buchung legt EU-Fernverkäufe an Privatkunden je Bestimmungsland auf die
OSS-Erlöskonten aus ``steuer.umsatzsteuer.OSS_ERLOES_KONTEN_SKR03`` (ermäßigte Sätze auf
die Konten aus ``integrationen.oss_erloes_ermaessigt``); die Meldung bildet
``steuer.oss.OSSEngine`` aus diesen Buchungen. Hier wird nur zusammengestellt und die
gemeldete Steuer gegen die gebuchte abgeglichen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from accounti.db.repository import lade_buchungen
from accounti.integrationen.einstellungen import Integrationen
from accounti.models import Buchungssatz, BuchungStatus
from accounti.steuer.eu_steuersaetze import EU_STEUERSAETZE
from accounti.steuer.oss import OSSEngine, OSSMeldung
from accounti.steuer.umsatzsteuer import OSS_ERLOES_KONTEN_SKR03, UStBerechner

NULL = Decimal("0.00")


def _erloeskonten(einstellungen: Integrationen | None) -> set[str]:
    konten = set(OSS_ERLOES_KONTEN_SKR03.values())
    if einstellungen is not None:
        konten |= set(einstellungen.oss_erloes_ermaessigt.values())
    return konten


def _zeitraum(jahr: int, quartal: int) -> tuple[date, date]:
    if quartal not in (1, 2, 3, 4):
        raise ValueError(f"Quartal {quartal} gibt es nicht")
    von = date(jahr, (quartal - 1) * 3 + 1, 1)
    bis = date(jahr + 1, 1, 1) if quartal == 4 else date(jahr, quartal * 3 + 1, 1)
    return von, bis


def oss_buchungen(
    session: Session,
    jahr: int,
    quartal: int,
    einstellungen: Integrationen | None = None,
) -> list[Buchungssatz]:
    """Buchungen eines Quartals auf OSS-Erlöskonten (Erlöse und Erstattungen)."""
    konten = _erloeskonten(einstellungen)
    von, bis = _zeitraum(jahr, quartal)
    return [
        b
        for b in lade_buchungen(session)
        if von <= b.datum < bis and (b.haben_konto in konten or b.soll_konto in konten)
    ]


def oss_meldung(
    session: Session,
    jahr: int,
    quartal: int,
    firmen_land: str = "DE",
    einstellungen: Integrationen | None = None,
) -> OSSMeldung:
    """Meldung des Quartals; frühere Buchungen ordnen Erstattungen ihrem Quartal zu."""
    konten = _erloeskonten(einstellungen)
    _von, bis = _zeitraum(jahr, quartal)
    buchungen = [
        b
        for b in lade_buchungen(session)
        if b.datum < bis and (b.haben_konto in konten or b.soll_konto in konten)
    ]
    return OSSEngine(firmen_land).erstelle_meldung(
        buchungen,
        jahr,
        quartal,
        erloes_konten_ermaessigt=(
            einstellungen.oss_erloes_ermaessigt if einstellungen else None
        ),
    )


def ungepruefte(buchungen: list[Buchungssatz]) -> int:
    """Wie viele der Buchungen noch zur Prüfung liegen (Meldung dann vorläufig)."""
    return sum(1 for b in buchungen if b.status is BuchungStatus.ZUR_PRUEFUNG)


@dataclass
class Steuerdifferenz:
    """Gebuchte OSS-Umsatzsteuer eines Steuerkontos ≠ gemeldete Steuer."""

    konto: str
    gebucht: Decimal
    gemeldet: Decimal

    @property
    def differenz(self) -> Decimal:
        return self.gebucht - self.gemeldet


def _steuerkonto(land: str, firmen_land: str) -> str:
    berechner = UStBerechner(firmen_land=firmen_land)
    return berechner.berechne_ust(Decimal("1"), land).steuer_konto


def steuerabgleich(
    session: Session, meldung: OSSMeldung, firmen_land: str = "DE"
) -> list[Steuerdifferenz]:
    """Gebuchte OSS-Steuer des Quartals gegen die gemeldete, je OSS-Steuerkonto.

    Gebucht wird je Bestellung Brutto − Netto, gemeldet je Land und Satz die Steuer
    auf die Summe der Bemessungsgrundlagen; dazu kommen Korrekturen früherer
    Quartale. Eine Differenz entsteht durch Rundung — oder durch OSS-Steuer, deren
    Erlös nicht auf einem OSS-Erlöskonto liegt (z.B. ermäßigter Satz ohne Konto).
    """
    land_konto = {
        land: _steuerkonto(land, firmen_land)
        for land in EU_STEUERSAETZE
        if land != firmen_land
    }
    gemeldet: dict[str, Decimal] = {konto: NULL for konto in land_konto.values()}
    for land in meldung.laender:
        gemeldet[land_konto[land.land_code]] += land.steuer_gesamt
    for k in meldung.korrekturen:
        gemeldet[land_konto[k.land_code]] += k.steuer
    gebucht: dict[str, Decimal] = {konto: NULL for konto in gemeldet}
    von, bis = meldung.meldezeitraum_von, meldung.meldezeitraum_bis
    for b in lade_buchungen(session):
        if not von <= b.datum <= bis:
            continue
        if b.haben_konto in gebucht:
            gebucht[b.haben_konto] += b.betrag_netto
        if b.soll_konto in gebucht:
            gebucht[b.soll_konto] -= b.betrag_netto
    return [
        Steuerdifferenz(konto, gebucht[konto], gemeldet[konto])
        for konto in sorted(gemeldet)
        if gebucht[konto] != gemeldet[konto]
    ]
