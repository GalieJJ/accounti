"""Kennziffern der Voranmeldung aus Buchungssätzen ermitteln.

Ein Buchungssatz trägt seine Steuer wie bei DATEV über den Steuerschlüssel
(BU-Schlüssel) oder über ein Konto mit fester Funktion (z. B. 8125 „Steuerfreie
innergemeinschaftliche Lieferungen“). Daraus folgt die Kennziffer; das Vorzeichen folgt
aus der Seite, auf der das Sachkonto steht — Personen- und Geldkonten sind Gegenkonten:

- Umsatzsteuerschlüssel und Erlöskonten: Sachkonto im Haben = Umsatz, im Soll =
  Minderung (Gutschrift, Skonto).
- Vorsteuer-, Erwerbs- und § 13b-Schlüssel: Sachkonto im Soll = Bezug, im Haben =
  Minderung.

Ein Erlöskonto ohne Schlüssel und ohne feste Funktion hat keine Kennziffer — es sei
denn, die Buchung mindert eine Rechnung desselben Belegs (Skonto auf eine steuerfreie
Rechnung), dann folgt sie deren Kennziffer. Alles andere landet in
``ohne_kennziffer`` und sperrt die Freigabe.

DATEV-Schlüssel: 2/3 USt 7/19 %, 8/9 VSt 7/19 %, 18/19 ig. Erwerb 7/19 %,
91/94 § 13b 7/19 %.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

from accounti.models import Buchungssatz, BuchungStatus, Kontakt
from accounti.steuer.eu_steuersaetze import ist_eu_land
from accounti.steuer.umsatzsteuer import OSS_ERLOES_KONTEN_SKR03
from accounti.steuer.voranmeldung import UStVoranmeldung
from accounti.steuer.zeitraum import Zeitraum

NULL = Decimal("0.00")
CENT = Decimal("0.01")

ENDGUELTIG = frozenset(
    {
        BuchungStatus.AUTO_GEBUCHT,
        BuchungStatus.GEPRUEFT,
        BuchungStatus.KORRIGIERT,
        BuchungStatus.EXPORTIERT,
    }
)

Seite = Literal["soll", "haben"]


@dataclass(frozen=True)
class SchluesselRegel:
    bezeichnung: str
    seite: Seite  # Seite des Sachkontos im Normalfall
    satz: Decimal
    bmg: int | None = None  # Kennziffer der Bemessungsgrundlage
    steuer: int | None = None  # Steuerfeld (Umsatzsteuer), sonst berechnet ELSTER
    vorsteuer: int | None = None  # Vorsteuerfeld
    eu_bmg: int | None = None  # § 13b Abs. 1: Leistender im übrigen Gemeinschaftsgebiet
    eu_steuer: int | None = None


STEUERSCHLUESSEL: dict[int, SchluesselRegel] = {
    3: SchluesselRegel("USt 19 %", "haben", Decimal("19"), bmg=81),
    2: SchluesselRegel("USt 7 %", "haben", Decimal("7"), bmg=86),
    9: SchluesselRegel("VSt 19 %", "soll", Decimal("19"), vorsteuer=66),
    8: SchluesselRegel("VSt 7 %", "soll", Decimal("7"), vorsteuer=66),
    19: SchluesselRegel("ig. Erwerb 19 %", "soll", Decimal("19"), bmg=89, vorsteuer=61),
    18: SchluesselRegel("ig. Erwerb 7 %", "soll", Decimal("7"), bmg=93, vorsteuer=61),
    94: SchluesselRegel(
        "§ 13b 19 %",
        "soll",
        Decimal("19"),
        bmg=84,
        steuer=85,
        vorsteuer=67,
        eu_bmg=46,
        eu_steuer=47,
    ),
    91: SchluesselRegel(
        "§ 13b 7 %",
        "soll",
        Decimal("7"),
        bmg=84,
        steuer=85,
        vorsteuer=67,
        eu_bmg=46,
        eu_steuer=47,
    ),
}
_USTEUER_SCHLUESSEL = frozenset({2, 3})

# Konten mit fester Funktion (Bemessungsgrundlage ohne Steuer), DATEV SKR03/SKR04
KENNZIFFERN_KONTEN: dict[str, dict[str, int]] = {
    "SKR03": {
        "8125": 41,  # steuerfreie ig. Lieferungen § 4 Nr. 1b UStG
        "8130": 42,  # Lieferungen des ersten Abnehmers, ig. Dreiecksgeschäft
        "8120": 43,  # steuerfreie Umsätze § 4 Nr. 1a UStG (Ausfuhr)
        "8100": 48,  # steuerfreie Umsätze § 4 Nr. 8 ff. UStG
        "8336": 21,  # EU-Leistung, Steuerschuld beim Leistungsempfänger
        "8337": 60,  # Leistungen, für die der Empfänger nach § 13b schuldet
        "8338": 45,  # Drittland steuerbar, im Inland nicht steuerbar
        "8339": 45,  # anderes EU-Land steuerbar, im Inland nicht steuerbar
        # OSS-Fernverkäufe: Nettoumsatz in Kz 45 (USt 1 E 2026, Zeile 36)
        **dict.fromkeys(OSS_ERLOES_KONTEN_SKR03.values(), 45),
    },
    "SKR04": {
        "4125": 41,
        "4130": 42,
        "4120": 43,
        "4100": 48,
        "4336": 21,
        "4337": 60,
        "4338": 45,
        "4339": 45,
    },
}

# Erlöskonten: ohne Steuerschlüssel oder Funktion fehlt der Umsatz in der Voranmeldung
STEUERRELEVANT: dict[str, tuple[tuple[int, int], ...]] = {
    "SKR03": ((8000, 8999),),
    "SKR04": ((4000, 4999),),
}
# Geld-, Forderungs- und Verbindlichkeits-Sammelkonten: reine Gegenkonten
_GEGENKONTEN: dict[str, tuple[tuple[int, int], ...]] = {
    "SKR03": ((1000, 1499), (1600, 1699)),
    "SKR04": ((1200, 1299), (1600, 1899), (3300, 3399)),
}

EU_ARTEN = {41: "L", 42: "D", 21: "S"}  # Art der Leistung in der ZM


@dataclass(frozen=True)
class Kontenplan:
    """Was die Ermittlung über die Konten wissen muss."""

    kontenrahmen: str = "SKR03"
    debitoren: tuple[int, int] = (10000, 69999)
    kreditoren: tuple[int, int] = (70000, 99999)
    geldkonten: frozenset[str] = (
        frozenset()
    )  # zusätzlich, z. B. eingerichtete Bankkonten
    steuerrelevant: tuple[tuple[int, int], ...] | None = None  # None: je Kontenrahmen
    kennziffern_konten: Mapping[str, int] = field(default_factory=dict)  # Ergänzungen

    @property
    def funktionskonten(self) -> dict[str, int]:
        return {
            **KENNZIFFERN_KONTEN.get(self.kontenrahmen, {}),
            **self.kennziffern_konten,
        }

    @staticmethod
    def _zahl(konto: str) -> int | None:
        return int(konto) if konto.isdigit() else None

    def ist_personenkonto(self, konto: str) -> bool:
        nr = self._zahl(konto)
        return nr is not None and any(
            von <= nr <= bis for von, bis in (self.debitoren, self.kreditoren)
        )

    def ist_gegenkonto(self, konto: str) -> bool:
        if konto in self.geldkonten or self.ist_personenkonto(konto):
            return True
        nr = self._zahl(konto)
        bereiche = _GEGENKONTEN.get(self.kontenrahmen, ())
        return nr is not None and any(von <= nr <= bis for von, bis in bereiche)

    def ist_steuerrelevant(self, konto: str) -> bool:
        nr = self._zahl(konto)
        bereiche = (
            self.steuerrelevant
            if self.steuerrelevant is not None
            else STEUERRELEVANT.get(self.kontenrahmen, ())
        )
        return nr is not None and any(von <= nr <= bis for von, bis in bereiche)


@dataclass(frozen=True)
class Beitrag:
    kz: int
    betrag: Decimal


@dataclass(frozen=True)
class Zuordnung:
    buchung: Buchungssatz
    beitraege: tuple[Beitrag, ...]
    regel: str


@dataclass(frozen=True)
class EuUmsatz:
    """Steuerfreier Umsatz an einen EU-Unternehmer — für ZM und USt-IdNr.-Prüfung."""

    buchung: Buchungssatz
    kz: int
    art: str  # L, D, S
    betrag: Decimal  # vorzeichenrichtig
    kontakt: Kontakt | None


@dataclass
class Ermittlung:
    zeitraum: Zeitraum
    voranmeldung: UStVoranmeldung
    zugeordnet: list[Zuordnung] = field(default_factory=list)
    ohne_kennziffer: list[tuple[Buchungssatz, str]] = field(default_factory=list)
    offen: list[Buchungssatz] = field(default_factory=list)
    eu: list[EuUmsatz] = field(default_factory=list)
    gebuchte_umsatzsteuer: Decimal = NULL
    hinweise: list[str] = field(default_factory=list)


def _sachseite(b: Buchungssatz, plan: Kontenplan, normal: Seite) -> Seite:
    soll_gegen = plan.ist_gegenkonto(b.soll_konto)
    haben_gegen = plan.ist_gegenkonto(b.haben_konto)
    if haben_gegen and not soll_gegen:
        return "soll"
    if soll_gegen and not haben_gegen:
        return "haben"
    return normal


def _gegenkonto(b: Buchungssatz, sachseite: Seite) -> str:
    return b.haben_konto if sachseite == "soll" else b.soll_konto


def _kurz(b: Buchungssatz) -> str:
    return f"{b.datum:%d.%m.%Y} {b.soll_konto} an {b.haben_konto} {b.betrag_netto}"


class _Ermittler:
    def __init__(
        self,
        alle: Sequence[Buchungssatz],
        zeitraum: Zeitraum,
        plan: Kontenplan,
        kontakte: Sequence[Kontakt],
        beleg_kontakte: Mapping[UUID, UUID],
    ) -> None:
        self.alle = alle
        self.plan = plan
        self.funktion = plan.funktionskonten
        self.debitoren = {k.debitor_konto: k for k in kontakte if k.debitor_konto}
        self.kreditoren = {k.kreditor_konto: k for k in kontakte if k.kreditor_konto}
        self.nach_id = {k.id: k for k in kontakte}
        self.beleg_kontakte = beleg_kontakte
        self.e = Ermittlung(zeitraum, UStVoranmeldung(zeitraum=str(zeitraum)))

    def _kontakt(self, konto: str, beleg_id: UUID | None) -> Kontakt | None:
        kontakt = self.debitoren.get(konto) or self.kreditoren.get(konto)
        if kontakt is None and beleg_id is not None:
            kontakt_id = self.beleg_kontakte.get(beleg_id)
            kontakt = self.nach_id.get(kontakt_id) if kontakt_id else None
        return kontakt

    def _buche(self, b: Buchungssatz, regel: str, beitraege: list[Beitrag]) -> None:
        for beitrag in beitraege:
            self.e.voranmeldung.addiere(beitrag.kz, beitrag.betrag)
        self.e.zugeordnet.append(Zuordnung(b, tuple(beitraege), regel))

    def _steuer(self, b: Buchungssatz, satz: Decimal) -> Decimal:
        if b.steuer_betrag is not None:
            return b.steuer_betrag
        berechnet = (b.betrag_netto * satz / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        self.e.hinweise.append(
            f"{_kurz(b)}: Steuerbetrag fehlt — {berechnet} aus dem Satz berechnet"
        )
        return berechnet

    def schluessel(self, b: Buchungssatz, schluessel: int) -> None:
        r = STEUERSCHLUESSEL[schluessel]
        seite = _sachseite(b, self.plan, r.seite)
        vz = 1 if seite == r.seite else -1
        netto = vz * b.betrag_netto
        steuer = vz * self._steuer(b, r.satz)
        beitraege = []
        if schluessel in _USTEUER_SCHLUESSEL:
            self.e.gebuchte_umsatzsteuer += steuer
        bmg, steuer_kz = r.bmg, r.steuer
        if r.eu_bmg is not None:
            kreditor = self._kontakt(_gegenkonto(b, seite), b.beleg_id)
            if kreditor is None:
                self.e.hinweise.append(
                    f"{_kurz(b)}: Leistender unbekannt — § 13b als „andere Leistung“ "
                    "(Kz 84/85) gemeldet"
                )
            elif kreditor.land.upper() != "DE" and ist_eu_land(kreditor.land):
                bmg, steuer_kz = r.eu_bmg, r.eu_steuer
        if bmg is not None:
            beitraege.append(Beitrag(bmg, netto))
        if steuer_kz is not None:
            beitraege.append(Beitrag(steuer_kz, steuer))
        if r.vorsteuer is not None:
            beitraege.append(Beitrag(r.vorsteuer, steuer))
        self._buche(b, f"Steuerschlüssel {schluessel} ({r.bezeichnung})", beitraege)

    def _rechnungs_kz(self, b: Buchungssatz) -> set[int]:
        """Kennziffern der Rechnungsbuchungen desselben Belegs (ohne Zahlungen)."""
        return {
            self.funktion[konto]
            for andere in self.alle
            if andere.beleg_id == b.beleg_id
            and andere.id != b.id
            and andere.transaktion_id is None
            for konto in (andere.soll_konto, andere.haben_konto)
            if konto in self.funktion
        }

    def konto(self, b: Buchungssatz) -> None:
        if b.haben_konto in self.funktion or b.soll_konto in self.funktion:
            haben = b.haben_konto in self.funktion
            konto = b.haben_konto if haben else b.soll_konto
            kz, regel = self.funktion[konto], f"Konto {konto}"
        else:
            relevant = next(
                (
                    k
                    for k in (b.haben_konto, b.soll_konto)
                    if self.plan.ist_steuerrelevant(k)
                ),
                None,
            )
            if relevant is None:
                return  # Zahlung, Umbuchung, Aufwand ohne Vorsteuer
            haben = relevant == b.haben_konto
            kandidaten = self._rechnungs_kz(b) if b.beleg_id else set()
            if len(kandidaten) != 1:
                grund = (
                    f"Erlöskonto {relevant} ohne Steuerschlüssel und ohne Kennziffer"
                    if not kandidaten
                    else f"Erlöskonto {relevant}: Rechnung mit mehreren Kennziffern"
                )
                self.e.ohne_kennziffer.append((b, grund))
                return
            (kz,) = kandidaten
            regel = f"Konto {relevant} mindert die Rechnung (Kz {kz})"
        betrag = b.betrag_netto if haben else -b.betrag_netto
        self._buche(b, regel, [Beitrag(kz, betrag)])
        if kz in EU_ARTEN:
            seite: Seite = "haben" if haben else "soll"
            kontakt = self._kontakt(_gegenkonto(b, seite), b.beleg_id)
            self.e.eu.append(EuUmsatz(b, kz, EU_ARTEN[kz], betrag, kontakt))

    def __call__(self, b: Buchungssatz) -> None:
        schluessel = b.steuer_schluessel
        if schluessel in STEUERSCHLUESSEL:
            self.schluessel(b, schluessel)
        elif schluessel in (None, 1):
            self.konto(b)
        else:
            self.e.ohne_kennziffer.append(
                (b, f"Steuerschlüssel {schluessel} hat keine Kennziffer in accounti")
            )


def ermittle(
    buchungen: Iterable[Buchungssatz],
    zeitraum: Zeitraum,
    plan: Kontenplan,
    kontakte: Sequence[Kontakt] = (),
    beleg_kontakte: Mapping[UUID, UUID] | None = None,
) -> Ermittlung:
    """Voranmeldung eines Zeitraums aus den endgültigen Buchungen.

    ``buchungen`` dürfen alle Buchungen sein; gezählt wird nur der Zeitraum. Ältere
    Buchungen dienen dazu, Minderungen einer Rechnung (Skonto) zuzuordnen.
    ``beleg_kontakte``: Beleg → Kontakt aus den offenen Posten, für Erlöse ohne
    Personenkonto.
    """
    alle = list(buchungen)
    ermittler = _Ermittler(alle, zeitraum, plan, kontakte, beleg_kontakte or {})
    for b in sorted(alle, key=lambda x: (x.datum, x.soll_konto, x.haben_konto)):
        if not zeitraum.enthaelt(b.datum):
            continue
        if b.status not in ENDGUELTIG:
            ermittler.e.offen.append(b)
            continue
        ermittler(b)
    return ermittler.e
