"""Kennziffern der Voranmeldung aus Buchungssätzen ermitteln.

Ein Buchungssatz trägt seine Steuer wie bei DATEV über den Steuerschlüssel
(BU-Schlüssel) oder über ein Konto mit fester Funktion (z. B. 8125 „Steuerfreie
innergemeinschaftliche Lieferungen“). Daraus folgt die Kennziffer; das Vorzeichen folgt
aus der Seite, auf der das Sachkonto steht — Personen-, Geld-, Transit- und
Privatkonten sind Gegenkonten:

- Umsatzsteuerschlüssel und Erlöskonten: Sachkonto im Haben = Umsatz, im Soll =
  Minderung (Gutschrift, Skonto).
- Vorsteuer-, Erwerbs- und § 13b-Schlüssel: Sachkonto im Soll = Bezug, im Haben =
  Minderung.
- Stehen beide Seiten (oder keine) auf Gegenkonten, entscheidet das Erlöskonto: bei
  Umsatzsteuerschlüsseln ist es das Sachkonto, bei Vorsteuerschlüsseln die Gegenseite.
- Konten mit fester Funktion buchen ihren Zugang auf der Seite ihrer Kennziffer:
  Umsätze (Abschnitte A, B, E) und Umsatzsteuer im Haben, Erwerbe und § 13b-Bezüge
  (Abschnitte C, D) und Vorsteuer im Soll.

Ein Erlöskonto ohne Schlüssel und ohne feste Funktion hat keine Kennziffer — es sei
denn, die Buchung mindert eine Rechnung desselben Belegs: Erlöskonto im Soll (Skonto,
Gutschrift) oder ein Erlösschmälerungskonto (SKR03 87xx, SKR04 47xx, auch dessen
Storno im Haben), gegen ein Gegenkonto. Hat die Rechnung genau eine Kennziffer und
läuft sie über ein Konto mit fester Funktion (steuerfrei, z. B. Kz 41), folgt die
Minderung ihr. Eine steuerpflichtige Rechnung (Schlüssel 3 → Kz 81) mindert nur eine
Buchung mit Schlüssel, sonst fehlt die Korrektur der Umsatzsteuer; bei mehreren
Kennziffern ist offen, welche gemindert wird. Ein Erlös im Haben ohne Schlüssel mindert
nichts. Alles andere landet in ``ohne_kennziffer`` und sperrt die Freigabe.
Buchungen auf Steuerkonten ohne Kennziffer (z. B. Einfuhrumsatzsteuer) sind eine
Warnung, ebenso Aufwand ohne Schlüssel gegen einen Kreditor im übrigen
Gemeinschaftsgebiet mit USt-IdNr.: Dort ist meist § 13b (Schlüssel 94, Kz 46/47) oder
ein ig. Erwerb (Schlüssel 19, Kz 89) anzumelden.

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
from accounti.steuer.voranmeldung import KENNZIFFERN_2026, Art, UStVoranmeldung
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

Bereiche = tuple[tuple[int, int], ...]

# Konten, auf denen ein Umsatz im Sinne des UStG gebucht wird: ohne Steuerschlüssel oder
# Funktion fehlt er in der Voranmeldung. Umsatzerlöse, unentgeltliche Wertabgaben und
# Erlösschmälerungen, dazu die Erlöskonten unter den sonstigen Erträgen, die DATEV als
# Automatikkonten mit Umsatzsteuer führt (Kontenrahmen 2026), samt ihren Geschwistern
# ohne Steuersatz: Sachbezüge, Anlagenverkäufe, Vermietung, sonstige Erlöse mit USt
# oder steuerfrei nach § 4 UStG. Nicht dazu gehören Bestandsveränderungen, aktivierte
# Eigenleistungen, Währungsumrechnung, Restbuchwerte, Erträge aus Auflösungen und
# Zuschreibungen, Versicherungsentschädigungen und erstattete Vorsteuer — sie sind nicht
# steuerbar — sowie die Sammelkonten der sonstigen Erträge ohne Steuerautomatik (SKR03
# 2700–2749, SKR04 4830, 4832, 4839): ein steuerpflichtiger Ertrag dort braucht seinen
# Schlüssel, ohne ihn fällt er nicht auf. Außerhalb liegen damit SKR03 8960–8999 und
# SKR04 4800–4832, 4837–4840, 4843, 4846–4847, 4855–4859, 4870–4939, 4950–4999.
STEUERRELEVANT: dict[str, Bereiche] = {
    # 8000–8959 Erlöse bis Wertabgaben (mit 859x/86xx Sachbezüge und sonstige Erlöse,
    # 88xx Anlagenverkäufe); 2750–2752 Grundstückserträge, Vermietung
    "SKR03": ((2750, 2752), (8000, 8959)),
    "SKR04": (
        (4000, 4799),  # Umsatzerlöse, Wertabgaben, Erlösschmälerungen
        (4833, 4836),  # andere Nebenerlöse, sonstige Erträge regelmäßig 16 %/19 %
        (4841, 4842),  # sonstige Erträge steuerfrei § 4 Nr. 8 ff., Nr. 2 bis 7
        (4844, 4845),  # Anlagenverkäufe § 4 Nr. 1a, 19 % (Buchgewinn)
        (4848, 4852),  # Anlagenverkäufe § 4 Nr. 1b, ohne Satz, immateriell, Finanz
        (4860, 4869),  # Grundstückserträge, Vermietung, Umlaufvermögen § 4 Abs. 3
        (4940, 4949),  # Sachbezüge (z. B. 4947 Kfz-Gestellung 19 %)
        (6884, 6892),  # Anlagenverkäufe bei Buchverlust
    ),
}
# Erlösschmälerungen: mindern die Rechnung desselben Belegs, in beide Richtungen
ERLOESSCHMAELERUNG: dict[str, Bereiche] = {
    "SKR03": ((8700, 8799),),
    "SKR04": ((4700, 4799),),
}
# Geld-, Transit-, Forderungs-, Verbindlichkeits- und Privatkonten: reine Gegenkonten
_GEGENKONTEN: dict[str, Bereiche] = {
    # 1000–1499 Kasse, Bank, Geldtransit 1360, Forderungen; 1590 durchlaufende Posten;
    # 1600–1699 Verbindlichkeiten; 1800–1899 Privat
    "SKR03": ((1000, 1499), (1590, 1590), (1600, 1699), (1800, 1899)),
    # 1200–1299 Forderungen; 1370 durchlaufende Posten; 1460 Geldtransit; 1600–1899
    # Kasse, Bank; 2100–2199 Privat; 3300–3399 Verbindlichkeiten
    "SKR04": (
        (1200, 1299),
        (1370, 1370),
        (1460, 1460),
        (1600, 1899),
        (2100, 2199),
        (3300, 3399),
    ),
}
# Vorsteuer- und Umsatzsteuerkonten, deren Buchung ohne Kennziffer auffallen soll —
# ohne Vorauszahlungen, Sondervorauszahlung und USt laufendes Jahr/Vorjahr
STEUERKONTEN: dict[str, Bereiche] = {
    "SKR03": ((1570, 1588), (1770, 1779), (1782, 1788)),
    "SKR04": ((1400, 1433), (3800, 3819), (3832, 3837)),
}
# Saldenvortrags- und statistische Konten (SKR03/SKR04 9000–9999)
_VORTRAG: Bereiche = ((9000, 9999),)
# Nicht steuerbare Umsätze, die bei einem EU-Unternehmer meist eine EU-Leistung sind
_NICHT_STEUERBAR_EU: dict[str, tuple[frozenset[str], str]] = {
    "SKR03": (frozenset({"8338", "8339"}), "8336"),
    "SKR04": (frozenset({"4338", "4339"}), "4336"),
}

EU_ARTEN = {41: "L", 42: "D", 21: "S"}  # Art der Leistung in der ZM

# Vorsteuerfelder: ein Zugang steht im Soll
_VORSTEUER_KZ = frozenset({66, 61, 62, 67, 63, 59, 64})
# berechnet (83) oder aus der Sondervorauszahlung (39) — nie über ein Konto
_NICHT_ZUORDENBAR = frozenset({83, 39})


def zuordenbar(kz: int) -> bool:
    """Kann ``elster.kennziffern_konten`` ein Konto auf diese Kennziffer legen?"""
    k = KENNZIFFERN_2026.get(kz)
    return k is not None and k.art is not Art.MERKER and kz not in _NICHT_ZUORDENBAR


def zugangsseite(kz: int) -> Seite:
    """Seite, auf der ein Konto mit dieser Kennziffer seinen Zugang bucht.

    Umsätze (Abschnitte A, B, E), Umsatzsteuer und Kz 37 im Haben; Erwerbe und
    § 13b-Bezüge (C, D), Vorsteuer und Kz 50 (Minderung der Bemessungsgrundlage) im
    Soll.
    """
    k = KENNZIFFERN_2026[kz]
    if k.art is Art.BMG:
        return "soll" if k.abschnitt in ("C", "D") or kz == 50 else "haben"
    return "soll" if kz in _VORSTEUER_KZ else "haben"


def _im_bereich(konto: str, bereiche: Bereiche) -> bool:
    return konto.isdigit() and any(von <= int(konto) <= bis for von, bis in bereiche)


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
        return _im_bereich(konto, _GEGENKONTEN.get(self.kontenrahmen, ()))

    def ist_steuerrelevant(self, konto: str) -> bool:
        bereiche = (
            self.steuerrelevant
            if self.steuerrelevant is not None
            else STEUERRELEVANT.get(self.kontenrahmen, ())
        )
        return _im_bereich(konto, bereiche)

    def ist_erloesschmaelerung(self, konto: str) -> bool:
        return _im_bereich(konto, ERLOESSCHMAELERUNG.get(self.kontenrahmen, ()))

    def ist_erloeskonto(self, konto: str) -> bool:
        return self.ist_steuerrelevant(konto) or self.ist_erloesschmaelerung(konto)

    def ist_steuerkonto(self, konto: str) -> bool:
        return _im_bereich(konto, STEUERKONTEN.get(self.kontenrahmen, ()))


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
class Belegpartner:
    """Abnehmer laut Rechnung (USt-IdNr., Land) — geht dem Kontakt vor."""

    name: str
    ust_id: str | None
    land: str | None


@dataclass(frozen=True)
class EuUmsatz:
    """Steuerfreier Umsatz an einen EU-Unternehmer — für ZM und USt-IdNr.-Prüfung."""

    buchung: Buchungssatz
    kz: int
    art: str  # L, D, S
    betrag: Decimal  # vorzeichenrichtig
    kontakt: Kontakt | None
    # aus der Rechnung, sonst aus dem Kontakt: § 18a Abs. 7 Nr. 1 UStG meldet je
    # USt-IdNr., unter der geliefert wurde
    ust_id: str | None = None
    name: str | None = None


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
    warnungen: list[str] = field(default_factory=list)


def _andere(seite: Seite) -> Seite:
    return "haben" if seite == "soll" else "soll"


def _sachseite(
    b: Buchungssatz, plan: Kontenplan, normal: Seite, umsatzsteuer: bool
) -> Seite:
    """Seite des Sachkontos: gegenüber dem Gegenkonto — sonst entscheidet das
    Erlöskonto (Umsatzsteuer: das Erlöskonto selbst, Vorsteuer: die Gegenseite)."""
    soll_gegen = plan.ist_gegenkonto(b.soll_konto)
    haben_gegen = plan.ist_gegenkonto(b.haben_konto)
    if soll_gegen != haben_gegen:
        return "soll" if haben_gegen else "haben"
    soll_erloes = plan.ist_erloeskonto(b.soll_konto)
    if soll_erloes != plan.ist_erloeskonto(b.haben_konto):
        erloes: Seite = "soll" if soll_erloes else "haben"
        return erloes if umsatzsteuer else _andere(erloes)
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
        beleg_partner: Mapping[UUID, Belegpartner] | None = None,
    ) -> None:
        self.alle = alle
        self.beleg_partner = beleg_partner or {}
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
        seite = _sachseite(b, self.plan, r.seite, schluessel in _USTEUER_SCHLUESSEL)
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
                self.e.warnungen.append(
                    f"{_kurz(b)}: Leistender unbekannt (kein Personenkonto, kein "
                    "Kontakt am Beleg) — § 13b als „andere Leistung“ (Kz 84/85) "
                    "gemeldet; ist es eine sonstige Leistung eines EU-Unternehmers, "
                    "gehört sie in Kz 46/47"
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

    def _rechnungs_kz(self, b: Buchungssatz) -> tuple[set[int], set[int]]:
        """Umsatz-Kennziffern der Rechnungsbuchungen desselben Belegs (ohne
        Zahlungen): über Konten mit fester Funktion und über Umsatzsteuerschlüssel.

        Ein Storno-Paar (Original und Stornobuchung, Baustein 7) hebt sich auf und
        bestimmt die Kennziffer nicht — die Neubuchung gilt."""
        rechnung = [
            andere
            for andere in self.alle
            if andere.beleg_id == b.beleg_id
            and andere.id != b.id
            and andere.transaktion_id is None
            and andere.storniert_durch is None
            and andere.storno_von is None
        ]
        ueber_konto = {
            kz
            for andere in rechnung
            for konto in (andere.soll_konto, andere.haben_konto)
            if (kz := self.funktion.get(konto)) is not None
            and KENNZIFFERN_2026[kz].art is Art.BMG
            and zugangsseite(kz) == "haben"
        }
        ueber_schluessel = {
            kz
            for andere in rechnung
            if andere.steuer_schluessel in _USTEUER_SCHLUESSEL
            and (kz := STEUERSCHLUESSEL[andere.steuer_schluessel].bmg) is not None
        }
        return ueber_konto, ueber_schluessel

    def _rest_eines_aufgeteilten_ausgleichs(
        self, b: Buchungssatz, ueber_konto: set[int], ueber_schluessel: set[int]
    ) -> bool:
        """Ist ``b`` der schlüssellose Teil einer nach Steuersätzen aufgeteilten
        Minderung (Skonto aus dem Ausgleich) einer Rechnung mit genau einer
        steuerfreien Kennziffer?"""
        if b.transaktion_id is None or len(ueber_konto) != 1 or not ueber_schluessel:
            return False
        if ueber_konto & ueber_schluessel:
            return False
        mit_schluessel = {
            kz
            for andere in self.alle
            if andere.id != b.id
            and andere.transaktion_id == b.transaktion_id
            and andere.beleg_id == b.beleg_id
            and andere.steuer_schluessel in _USTEUER_SCHLUESSEL
            and (kz := STEUERSCHLUESSEL[andere.steuer_schluessel].bmg) is not None
        }
        return ueber_schluessel <= mit_schluessel

    def _minderung(self, b: Buchungssatz, konto: str, seite: Seite) -> Beitrag | str:
        """Erlöskonto ohne Schlüssel: Minderung der Rechnung desselben Belegs — oder
        der Grund, warum die Buchung keine Kennziffer hat."""
        ohne = f"Erlöskonto {konto} ohne Steuerschlüssel und ohne Kennziffer"
        if seite == "haben" and not self.plan.ist_erloesschmaelerung(konto):
            return ohne  # ein Erlös im Haben mindert nichts
        if not b.beleg_id:
            return ohne
        gegen = _gegenkonto(b, seite)
        if not self.plan.ist_gegenkonto(gegen):
            return (
                f"{ohne} — gegen {gegen} (kein Personen- oder Geldkonto) mindert es "
                "keine Rechnung"
            )
        ueber_konto, ueber_schluessel = self._rechnungs_kz(b)
        kandidaten = ueber_konto | ueber_schluessel
        if not kandidaten:
            return ohne
        if len(kandidaten) > 1 and self._rest_eines_aufgeteilten_ausgleichs(
            b, ueber_konto, ueber_schluessel
        ):
            # opos/ausgleich hat die Minderung nach Steuersätzen aufgeteilt: der
            # steuerpflichtige Teil steht mit Schlüssel in derselben Transaktion,
            # dieser Rest ohne Schlüssel gehört zur einzigen steuerfreien Kennziffer
            kandidaten = set(ueber_konto)
        if len(kandidaten) > 1:
            liste = ", ".join(str(kz) for kz in sorted(kandidaten))
            return f"Erlöskonto {konto}: Rechnung mit mehreren Kennziffern ({liste})"
        (kz,) = kandidaten
        if kz not in ueber_konto:
            return (
                f"Erlöskonto {konto} mindert eine steuerpflichtige Rechnung (Kz {kz}) "
                "ohne Steuerschlüssel — die Umsatzsteuer wird nicht berichtigt"
            )
        return Beitrag(kz, b.betrag_netto if seite == "haben" else -b.betrag_netto)

    def _steuerkonto(self, b: Buchungssatz, konto: str) -> None:
        self.e.warnungen.append(
            f"{_kurz(b)}: Steuerkonto {konto} ohne Kennziffer — z. B. "
            "Einfuhrumsatzsteuer (Kz 62) oder Nachsteuer (Kz 65) über "
            "elster.kennziffern_konten zuordnen, sonst fehlt der Betrag"
        )

    def _eu_pruefen(self, b: Buchungssatz, konto: str, kontakt: Kontakt | None) -> None:
        konten, richtig = _NICHT_STEUERBAR_EU.get(
            self.plan.kontenrahmen, (frozenset(), "")
        )
        if (
            konto not in konten
            or kontakt is None
            or not kontakt.ust_id
            or kontakt.land.upper() == "DE"
            or not ist_eu_land(kontakt.land)
        ):
            return
        self.e.warnungen.append(
            f"{_kurz(b)}: Konto {konto} (Kz 45, nicht steuerbar) an {kontakt.name} "
            f"({kontakt.land}, USt-IdNr. {kontakt.ust_id}) — eine EU-Leistung an einen "
            f"Unternehmer (§ 3a Abs. 2 UStG) gehört auf {richtig} (Kz 21) und in die "
            "Zusammenfassende Meldung"
        )

    def _bezug_ohne_schluessel(self, b: Buchungssatz) -> None:
        """Aufwand ohne Schlüssel von einem EU-Unternehmer: § 13b bzw. ig. Erwerb?

        Der Leistungsempfänger schuldet die Steuer (§ 13b Abs. 1, 5 bzw. § 1a, § 13a
        Abs. 1 Nr. 2 UStG) — ohne Schlüssel fehlt sie in der Anmeldung."""
        soll, haben = b.soll_konto, b.haben_konto
        plan = self.plan
        if (
            plan.ist_gegenkonto(soll)
            or plan.ist_steuerkonto(soll)
            or plan.ist_erloeskonto(soll)
            or _im_bereich(soll, _VORTRAG)
            or _im_bereich(haben, _VORTRAG)
            or not plan.ist_gegenkonto(haben)
            or haben in self.debitoren
        ):
            return
        kontakt = self._kontakt(haben, b.beleg_id)
        if (
            kontakt is None
            or not kontakt.ust_id
            or kontakt.land.upper() == "DE"
            or not ist_eu_land(kontakt.land)
        ):
            return
        self.e.warnungen.append(
            f"{_kurz(b)}: Bezug von {kontakt.name} ({kontakt.land}, USt-IdNr. "
            f"{kontakt.ust_id}) ohne Steuerschlüssel — § 13b prüfen: sonstige Leistung "
            "eines EU-Unternehmers → Schlüssel 94/91 (Kz 46/47, 67), Lieferung → ig. "
            "Erwerb, Schlüssel 19/18 (Kz 89, 61): accounti korrigiere … --steuer 94"
        )

    def konto(self, b: Buchungssatz) -> None:
        """Buchung ohne Steuerschlüssel: jede Seite für sich."""
        beitraege: list[tuple[Beitrag, Seite]] = []
        regeln: list[str] = []
        gruende: list[str] = []
        seiten: tuple[tuple[Seite, str], ...] = (
            ("soll", b.soll_konto),
            ("haben", b.haben_konto),
        )
        for seite, konto in seiten:
            if konto in self.funktion:
                kz = self.funktion[konto]
                vz = 1 if seite == zugangsseite(kz) else -1
                beitraege.append((Beitrag(kz, vz * b.betrag_netto), seite))
                regeln.append(f"Konto {konto}")
            elif self.plan.ist_erloeskonto(konto):
                ergebnis = self._minderung(b, konto, seite)
                if isinstance(ergebnis, str):
                    gruende.append(ergebnis)
                    continue
                beitraege.append((ergebnis, seite))
                regeln.append(f"Konto {konto} mindert die Rechnung (Kz {ergebnis.kz})")
            elif self.plan.ist_steuerkonto(konto):
                self._steuerkonto(b, konto)
        if gruende:
            self.e.ohne_kennziffer.append((b, "; ".join(gruende)))
            return
        if not beitraege:
            self._bezug_ohne_schluessel(b)
            return  # Zahlung, Umbuchung, Aufwand ohne Vorsteuer
        self._buche(b, "; ".join(regeln), [beitrag for beitrag, _ in beitraege])
        for beitrag, seite in beitraege:
            konto = b.soll_konto if seite == "soll" else b.haben_konto
            kontakt = self._kontakt(_gegenkonto(b, seite), b.beleg_id)
            if beitrag.kz in EU_ARTEN:
                art = EU_ARTEN[beitrag.kz]
                partner = self.beleg_partner.get(b.beleg_id) if b.beleg_id else None
                ust_id = (
                    partner.ust_id
                    if partner is not None
                    else (kontakt.ust_id if kontakt else None)
                )
                name = partner.name if partner else (kontakt.name if kontakt else None)
                self.e.eu.append(
                    EuUmsatz(b, beitrag.kz, art, beitrag.betrag, kontakt, ust_id, name)
                )
            elif beitrag.betrag > 0:
                self._eu_pruefen(b, konto, kontakt)

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
    beleg_partner: Mapping[UUID, Belegpartner] | None = None,
) -> Ermittlung:
    """Voranmeldung eines Zeitraums aus den endgültigen Buchungen.

    ``buchungen`` dürfen alle Buchungen sein; gezählt wird nur der Zeitraum. Ältere
    Buchungen dienen dazu, Minderungen einer Rechnung (Skonto) zuzuordnen.
    ``beleg_kontakte``: Beleg → Kontakt aus den offenen Posten, für Erlöse ohne
    Personenkonto. ``beleg_partner``: Beleg → Abnehmer laut Rechnung (USt-IdNr. für
    die ZM, auch wenn der Kontakt eine andere trägt).
    """
    alle = list(buchungen)
    ermittler = _Ermittler(
        alle, zeitraum, plan, kontakte, beleg_kontakte or {}, beleg_partner
    )
    for b in sorted(alle, key=lambda x: (x.datum, x.soll_konto, x.haben_konto)):
        if not zeitraum.enthaelt(b.datum):
            continue
        if b.status not in ENDGUELTIG:
            ermittler.e.offen.append(b)
            continue
        ermittler(b)
    return ermittler.e
