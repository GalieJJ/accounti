"""Abschnitte ``abschluss`` und ``kasse`` in ``config/accounti.yaml`` — optional.

Ohne Abschnitt gelten die Standards des Kontenrahmens aus ``buchhaltung.kontenrahmen``.

Das Wirtschaftsjahr kommt aus ``datev.wirtschaftsjahr_beginn`` (nur Tag und Monat;
ohne Angabe das Kalenderjahr). ``wirtschaftsjahr(jahr, beginn)`` ist der eine Helfer,
mit dem alle Abschlussmodule rechnen. Konvention: ``--jahr`` bezeichnet das
Wirtschaftsjahr über das Kalenderjahr seines **Endes** — 2026 ist bei Beginn 1. Juli
das Wirtschaftsjahr 01.07.2025–30.06.2026 (so gilt der Gewinn bei Gewerbetreibenden
als bezogen, § 4a Abs. 2 Nr. 2 EStG). Ein abweichendes Wirtschaftsjahr haben Land- und
Forstwirte (§ 4a Abs. 1 Satz 2 Nr. 1 EStG, auch mit EÜR) und im Handelsregister
eingetragene Gewerbetreibende (Nr. 2); es umfasst zwölf Monate (§ 8b EStDV,
Rumpfwirtschaftsjahre unterstützt accounti nicht).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    Field,
    GetCoreSchemaHandler,
    ValidationError,
    field_validator,
)
from pydantic_core import core_schema

from accounti.abschluss.kontenrahmen import (
    Gewinnermittlung,
    Kontenrahmen,
    lade_kontenrahmen,
)
from accounti.einstellungen.inventar import Betriebsfeld
from accounti.einstellungen.leser import lies_abschnitt
from accounti.einstellungen.perioden import (
    Periodenmodell,
    WirtschaftsjahrGewinnermittlung,
    pruefe,
    wert_fuer,
)
from accounti.konfiguration import (
    STANDARD_PFAD,
    KonfigurationError,
    _fehlertext,
    lade_buchhaltung,
)

_STANDARDS: dict[str, dict[str, Any]] = {
    "SKR03": {
        "ergebnis_konto": "0880",  # Variables Kapital
        "arap_konto": "0980",
        "prap_konto": "0990",
        # Geldtransit, Durchlaufende Posten, Sonstige Verrechnungskonten (Interim)
        "verrechnungskonten": ["1360", "1590", "1792"],
    },
    "SKR04": {
        "ergebnis_konto": "2010",
        "arap_konto": "1900",
        "prap_konto": "3900",
        "verrechnungskonten": ["1460", "1370", "3630"],
    },
}
_KASSE = {"SKR03": "1000", "SKR04": "1600"}


@dataclass(frozen=True)
class Wirtschaftsjahr:
    """Ein Wirtschaftsjahr, benannt nach dem Kalenderjahr seines Endes."""

    jahr: int
    von: date
    bis: date

    @property
    def abweichend(self) -> bool:
        """Weicht vom Kalenderjahr ab (§ 4a EStG)?"""
        return (self.von.month, self.von.day) != (1, 1)

    @property
    def bezeichnung(self) -> str:
        """„2026“ bzw. „2025/2026“."""
        if not self.abweichend:
            return str(self.jahr)
        return f"{self.von.year}/{self.bis.year}"

    @property
    def zeitraum(self) -> str:
        return f"{self.von:%d.%m.%Y}–{self.bis:%d.%m.%Y}"

    def enthaelt(self, tag: date) -> bool:
        return self.von <= tag <= self.bis

    @property
    def kalenderjahre(self) -> list[tuple[int, int]]:
        """(Kalenderjahr, letzter Monat im Wirtschaftsjahr) je berührtem Kalenderjahr —
        für Läufe, die im Kalenderjahr rechnen (AfA-Lauf)."""
        if self.von.year == self.bis.year:
            return [(self.bis.year, self.bis.month)]
        return [(self.von.year, 12), (self.bis.year, self.bis.month)]


def _beginn_im_jahr(jahr: int, beginn: date | None) -> date:
    monat, tag = (beginn.month, beginn.day) if beginn else (1, 1)
    return date(jahr, monat, min(tag, 28) if monat == 2 else tag)


def wirtschaftsjahr(jahr: int, beginn: date | None = None) -> Wirtschaftsjahr:
    """Das Wirtschaftsjahr, das im Kalenderjahr ``jahr`` endet.

    ``beginn``: irgendein Beginn aus der Konfiguration, maßgeblich sind Tag und Monat
    (wie ``export/datev_stammdaten.wirtschaftsjahr_beginn``); ohne: Kalenderjahr."""
    start = _beginn_im_jahr(jahr, beginn)
    if (start.month, start.day) == (1, 1):
        return Wirtschaftsjahr(jahr, start, date(jahr, 12, 31))
    von = _beginn_im_jahr(jahr - 1, beginn)
    return Wirtschaftsjahr(jahr, von, start - timedelta(days=1))


def wirtschaftsjahr_zum(tag: date, beginn: date | None = None) -> Wirtschaftsjahr:
    """Das Wirtschaftsjahr, in dem ``tag`` liegt."""
    wj = wirtschaftsjahr(tag.year, beginn)
    return wj if tag <= wj.bis else wirtschaftsjahr(tag.year + 1, beginn)


_TAG_MONAT = re.compile(r"^(\d{2})-(\d{2})$")
_TT_MM = re.compile(r"^(\d{1,2})\.(\d{1,2})\.?$")
_FORMAT = 'Tag und Monat als MM-TT (z. B. "07-01"), TT.MM. oder JJJJ-MM-TT'


@dataclass(frozen=True, order=True)
class TagMonat:
    """Tag und Monat ohne Jahr (Beginn des Wirtschaftsjahres, Baustein 10c P4).

    Gelesen werden „MM-TT“, „TT.MM.“, ein Datum mit Jahr (das Jahr zählt nicht, N2) und
    das YAML-Datum; geschrieben wird „MM-TT“."""

    monat: int
    tag: int

    def __post_init__(self) -> None:
        self.als_datum()  # 31.02. o. Ä. ist ein ValueError

    def als_datum(self) -> date:
        """Ein Datum mit diesem Tag und Monat — im Schaltjahr 2000 (der 29.02. gilt,
        ``wirtschaftsjahr`` nimmt in anderen Jahren den 28.)."""
        return date(2000, self.monat, self.tag)

    def __str__(self) -> str:
        return f"{self.monat:02d}-{self.tag:02d}"

    @property
    def deutsch(self) -> str:
        return f"{self.tag:02d}.{self.monat:02d}."

    @classmethod
    def lies(cls, wert: object) -> TagMonat:
        if isinstance(wert, TagMonat):
            return wert
        if isinstance(wert, date):  # auch datetime
            return cls(wert.month, wert.day)
        if isinstance(wert, str):
            text = wert.strip()
            try:
                if treffer := _TAG_MONAT.match(text):
                    return cls(int(treffer[1]), int(treffer[2]))
                if treffer := _TT_MM.match(text):
                    return cls(int(treffer[2]), int(treffer[1]))
                tag = date.fromisoformat(text)
            except ValueError:
                pass
            else:
                return cls(tag.month, tag.day)
        raise ValueError(f"{wert!r}: {_FORMAT}")

    @classmethod
    def __get_pydantic_core_schema__(
        cls, quelle: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls.lies,
            serialization=core_schema.plain_serializer_function_ser_schema(
                str, when_used="json"
            ),
        )


def _datev_nummer(wert: object) -> str | None:
    """Beraternummer bzw. Mandantennummer: nur Ziffern; eine Zahl aus der YAML wird wie
    bisher Text (N9: führende Nullen gehen dabei verloren, die Vorlage schreibt
    Text)."""
    if isinstance(wert, bool) or not isinstance(wert, int | str | None):
        raise ValueError(f"{wert!r}: nur Ziffern")
    text = str(wert).strip() if wert is not None else ""
    if text and not text.isdigit():
        raise ValueError(f"{wert!r}: nur Ziffern")
    return text or None


class DatevEinstellungen(BaseModel):
    """Abschnitt ``datev`` (Baustein 10c P4, A44)."""

    berater_nummer: str | None = None
    mandanten_nummer: str | None = None
    wirtschaftsjahr_beginn: TagMonat | None = Field(
        default=None, description="nur Tag und Monat (abweichendes WJ, § 4a EStG)"
    )

    _nummern = field_validator("berater_nummer", "mandanten_nummer", mode="before")(
        _datev_nummer
    )


def _datev_fehler(pfad: Path, fehler: ValidationError) -> KonfigurationError:
    return KonfigurationError(f"{pfad}: {_fehlertext(fehler, 'datev')}")


def lade_datev(pfad: str | Path = STANDARD_PFAD) -> DatevEinstellungen:
    """Abschnitt ``datev``: Berater- und Mandantennummer, Beginn des
    Wirtschaftsjahres."""
    pfad = Path(pfad)
    try:
        return DatevEinstellungen.model_validate(lies_abschnitt(pfad, "datev"))
    except ValidationError as fehler:
        raise _datev_fehler(pfad, fehler) from fehler


def lade_wirtschaftsjahr_beginn(pfad: str | Path = STANDARD_PFAD) -> date | None:
    """``datev.wirtschaftsjahr_beginn`` (Tag und Monat, als Datum im Jahr 2000) — ohne:
    Kalenderjahr. Liest nur dieses Feld: eine fehlerhafte Beraternummer hält den
    Abschluss nicht auf (die prüft ``lade_datev`` beim DATEV-Export)."""
    pfad = Path(pfad)
    wert = lies_abschnitt(pfad, "datev").get("wirtschaftsjahr_beginn")
    try:
        datev = DatevEinstellungen.model_validate({"wirtschaftsjahr_beginn": wert})
    except ValidationError as fehler:
        raise _datev_fehler(pfad, fehler) from fehler
    beginn = datev.wirtschaftsjahr_beginn
    return beginn.als_datum() if beginn is not None else None


class AbschlussEinstellungen(Periodenmodell):
    # Periodenwert je Wirtschaftsjahr (Baustein 10c P4, D14): gelesen nur über
    # gewinnermittlung_fuer(wj)
    kontenrahmen: str = "SKR03"
    gewinnermittlung_roh: WirtschaftsjahrGewinnermittlung = Field(
        default="euer", alias="gewinnermittlung"
    )
    ergebnis_konto: str
    arap_konto: str
    prap_konto: str
    rap_verzicht_bis_gwg: bool = Field(
        default=False, description="§ 5 Abs. 5 Satz 2 EStG, einheitlich"
    )
    verrechnungskonten: list[str] = Field(default_factory=list)
    # Verrechnungskonten der Marktplätze (integrationen.marktplaetze, ohne PayPal —
    # dessen Konto ist ein Geldkonto): sollen zum Stichtag ausgeglichen sein, bis auf
    # Auszahlungen, die erst im neuen Jahr kommen
    marktplatz_konten: list[str] = Field(default_factory=list)
    kontenzuordnung: Betriebsfeld[str | None] = None
    debitoren: tuple[int, int] = (10000, 69999)
    kreditoren: tuple[int, int] = (70000, 99999)
    bank_konto: str = "1200"
    wirtschaftsjahr_beginn: date | None = Field(
        default=None, description="aus datev.wirtschaftsjahr_beginn (Tag und Monat)"
    )

    def lade_kontenrahmen(self) -> Kontenrahmen:
        return lade_kontenrahmen(self.kontenrahmen, self.kontenzuordnung)

    def gewinnermittlung_fuer(self, wj: int) -> Gewinnermittlung:
        """Gewinnermittlung im Wirtschaftsjahr ``wj`` (Kalenderjahr seines Endes)."""
        return wert_fuer(self.gewinnermittlung_roh, wj)

    def wirtschaftsjahr(self, jahr: int) -> Wirtschaftsjahr:
        """Das Wirtschaftsjahr ``jahr`` (Kalenderjahr seines Endes)."""
        return wirtschaftsjahr(jahr, self.wirtschaftsjahr_beginn)

    def wirtschaftsjahr_zum(self, tag: date) -> Wirtschaftsjahr:
        return wirtschaftsjahr_zum(tag, self.wirtschaftsjahr_beginn)

    @property
    def abweichendes_wirtschaftsjahr(self) -> bool:
        return self.wirtschaftsjahr(2000).abweichend


_GEWINNERMITTLUNG = pruefe("wirtschaftsjahr", Gewinnermittlung)


class KassenEinstellungen(BaseModel):
    konto: str


def lade_abschluss(pfad: str | Path = STANDARD_PFAD) -> AbschlussEinstellungen:
    from accounti.integrationen.einstellungen import lade_integrationen

    pfad = Path(pfad)
    buchhaltung = lade_buchhaltung(pfad)
    kontenrahmen = buchhaltung.kontenrahmen.upper()
    marktplaetze = lade_integrationen(pfad).marktplaetze
    werte = {
        **_STANDARDS.get(kontenrahmen, _STANDARDS["SKR03"]),
        **lies_abschnitt(pfad, "abschluss"),
        "marktplatz_konten": sorted(
            {
                k.verrechnungskonto
                for name, k in marktplaetze.items()
                if name != "paypal"
            }
        ),
        "kontenrahmen": kontenrahmen,
        "debitoren": (buchhaltung.debitoren_von, buchhaltung.debitoren_bis),
        "kreditoren": (buchhaltung.kreditoren_von, buchhaltung.kreditoren_bis),
        "bank_konto": buchhaltung.bank_konto,
        "wirtschaftsjahr_beginn": lade_wirtschaftsjahr_beginn(pfad),
    }
    try:
        return AbschlussEinstellungen.model_validate(werte)
    except ValidationError as fehler:
        msg = f"{pfad}: Abschnitt 'abschluss': {fehler}"
        raise KonfigurationError(msg) from fehler


def gewinnermittlung_angegeben(pfad: str | Path, wj: int) -> str | None:
    """``abschluss.gewinnermittlung`` im Wirtschaftsjahr ``wj`` (Kalenderjahr seines
    Endes), wenn sie ausdrücklich in der Konfiguration steht (``bilanz`` oder ``euer``,
    auch als Periodenwert) — sonst ``None`` (der Standard ``euer`` gilt dann nur dort,
    wo er nichts riskiert). Nachsichtig: einen ungültigen Wert meldet
    ``lade_abschluss``."""
    wert = lies_abschnitt(Path(pfad), "abschluss").get("gewinnermittlung")
    if wert is None:
        return None
    try:
        geprueft = _GEWINNERMITTLUNG(wert)
    except ValueError:
        return None
    return str(wert_fuer(geprueft, wj))


def lade_kasse(pfad: str | Path = STANDARD_PFAD) -> KassenEinstellungen:
    pfad = Path(pfad)
    kontenrahmen = lade_buchhaltung(pfad).kontenrahmen.upper()
    werte = {"konto": _KASSE.get(kontenrahmen, "1000"), **lies_abschnitt(pfad, "kasse")}
    try:
        return KassenEinstellungen.model_validate(werte)
    except ValidationError as fehler:
        raise KonfigurationError(f"{pfad}: Abschnitt 'kasse': {fehler}") from fehler
