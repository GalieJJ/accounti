"""Konfigurationsgetriebener Bank-Importer.

Ein BankProfil beschreibt das CSV-Format einer Bank (Trennzeichen, Encoding,
Datums-/Betragsformat, Spalten-Zuordnung). Der ProfilImporter parst damit jede
unterstützte Bank-CSV in Transaktion-Objekte — ohne bankspezifischen Code.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import yaml

from accounti.importers import BANK_IMPORTERS, BankImporter
from accounti.models import Transaktion, TransaktionQuelle


@dataclass
class BankProfil:
    """Beschreibt das CSV-Format einer Bank."""

    name: str
    delimiter: str = ";"
    encoding: str = "auto"  # "auto" probiert utf-8-sig, dann cp1252
    datum_spalte: str = "Buchungstag"
    datum_format: str = "%d.%m.%y"
    verwendungszweck_spalte: str = "Verwendungszweck"
    gegenkonto_spalte: str | None = None
    gegenkonto_iban_spalte: str | None = None
    waehrung_spalte: str | None = None
    betrag_modus: str = "signed"  # "signed" | "soll_haben"
    betrag_spalte: str = "Betrag"
    dezimal: str = ","  # Dezimaltrennzeichen
    soll_spalte: str | None = None  # nur im Modus "soll_haben"
    haben_spalte: str | None = None
    # Spalten, an denen die Bank im Auto-Modus erkannt wird:
    erkennungs_spalten: tuple[str, ...] = ()


def parse_betrag(roh: str, dezimal: str = ",") -> Decimal:
    """Parst einen Betrag unabhängig vom Tausender-/Dezimalstil."""
    roh = roh.strip()
    if not roh:
        return Decimal("0")
    if dezimal == ",":
        roh = roh.replace(".", "").replace(",", ".")
    else:
        roh = roh.replace(",", "")
    return Decimal(roh)


def parse_datum(roh: str, fmt: str) -> date:
    return datetime.strptime(roh.strip(), fmt).date()


def _lies_text(pfad: Path, encoding: str) -> str:
    if encoding != "auto":
        return pfad.read_text(encoding=encoding)
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return pfad.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return pfad.read_text(encoding="latin-1")


class ProfilImporter(BankImporter):
    """Importiert eine Bank-CSV anhand eines BankProfils."""

    def __init__(self, profil: BankProfil) -> None:
        self.profil = profil
        self.name = profil.name

    def _betrag(self, row: dict[str, str]) -> Decimal:
        p = self.profil
        if p.betrag_modus == "soll_haben":
            soll = parse_betrag(row.get(p.soll_spalte or "", ""), p.dezimal)
            haben = parse_betrag(row.get(p.haben_spalte or "", ""), p.dezimal)
            return haben - soll
        return parse_betrag(row.get(p.betrag_spalte, ""), p.dezimal)

    def importiere(self, pfad: str | Path) -> list[Transaktion]:
        p = self.profil
        text = _lies_text(Path(pfad), p.encoding)
        reader = csv.DictReader(text.splitlines(), delimiter=p.delimiter)
        transaktionen: list[Transaktion] = []
        for row in reader:
            if not (row.get(p.datum_spalte) or "").strip():
                continue
            gegenkonto = None
            if p.gegenkonto_spalte:
                gegenkonto = (row.get(p.gegenkonto_spalte) or "").strip() or None
            iban = None
            if p.gegenkonto_iban_spalte:
                iban = (row.get(p.gegenkonto_iban_spalte) or "").strip() or None
            waehrung = "EUR"
            if p.waehrung_spalte:
                waehrung = (row.get(p.waehrung_spalte) or "EUR").strip() or "EUR"
            transaktionen.append(
                Transaktion(
                    datum=parse_datum(row[p.datum_spalte], p.datum_format),
                    betrag=self._betrag(row),
                    waehrung=waehrung,
                    verwendungszweck=(row.get(p.verwendungszweck_spalte) or "").strip(),
                    gegenkonto_name=gegenkonto,
                    gegenkonto_iban=iban,
                    quelle=TransaktionQuelle.BANK,
                    quelle_referenz=None,
                    rohtext=p.delimiter.join(row.values()),
                )
            )
        return transaktionen


# ---------------------------------------------------------------------------
# Eingebaute Bank-Profile (Startwerte — ggf. an echte Exporte anpassen via
# config/banken.yaml). encoding="auto" deckt utf-8 und cp1252 ab.
# ---------------------------------------------------------------------------

EINGEBAUTE_PROFILE: dict[str, BankProfil] = {
    "sparkasse": BankProfil(
        name="sparkasse",
        datum_spalte="Buchungstag",
        datum_format="%d.%m.%y",
        betrag_spalte="Betrag",
        verwendungszweck_spalte="Verwendungszweck",
        gegenkonto_spalte="Begünstigter/Zahlungspflichtiger",
        gegenkonto_iban_spalte="Kontonummer",
        waehrung_spalte="Währung",
        erkennungs_spalten=("Auftragskonto", "Begünstigter/Zahlungspflichtiger"),
    ),
    "ing": BankProfil(
        name="ing",
        datum_spalte="Buchung",
        datum_format="%d.%m.%Y",
        betrag_spalte="Betrag",
        verwendungszweck_spalte="Verwendungszweck",
        gegenkonto_spalte="Auftraggeber/Empfänger",
        waehrung_spalte="Währung",
        erkennungs_spalten=("Buchung", "Auftraggeber/Empfänger"),
    ),
    "dkb": BankProfil(
        name="dkb",
        datum_spalte="Buchungstag",
        datum_format="%d.%m.%Y",
        betrag_spalte="Betrag (EUR)",
        verwendungszweck_spalte="Verwendungszweck",
        gegenkonto_spalte="Auftraggeber / Begünstigter",
        erkennungs_spalten=("Auftraggeber / Begünstigter", "Betrag (EUR)"),
    ),
    "volksbank": BankProfil(
        name="volksbank",
        datum_spalte="Buchungstag",
        datum_format="%d.%m.%Y",
        betrag_spalte="Betrag",
        verwendungszweck_spalte="Verwendungszweck",
        gegenkonto_spalte="Name Zahlungsbeteiligter",
        waehrung_spalte="Waehrung",
        erkennungs_spalten=("Buchungstag", "Name Zahlungsbeteiligter"),
    ),
    "commerzbank": BankProfil(
        name="commerzbank",
        datum_spalte="Buchungstag",
        datum_format="%d.%m.%Y",
        betrag_spalte="Betrag",
        verwendungszweck_spalte="Buchungstext",
        waehrung_spalte="Währung",
        erkennungs_spalten=("Buchungstag", "Umsatzart", "Buchungstext"),
    ),
}


def registriere_profile(profile: dict[str, BankProfil]) -> None:
    """Registriert Profile als einsatzbereite Importer in BANK_IMPORTERS."""
    for name, profil in profile.items():
        BANK_IMPORTERS[name] = ProfilImporter(profil)


def lade_banken_profile(pfad: str | Path) -> dict[str, BankProfil]:
    """Lädt eigene Bank-Profile aus einer YAML-Datei (Liste von Profilen)."""
    pfad = Path(pfad)
    if not pfad.exists():
        return {}
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or []
    profile: dict[str, BankProfil] = {}
    for eintrag in daten:
        if "erkennungs_spalten" in eintrag:
            eintrag = {
                **eintrag,
                "erkennungs_spalten": tuple(eintrag["erkennungs_spalten"]),
            }
        profile[eintrag["name"]] = BankProfil(**eintrag)
    return profile


registriere_profile(EINGEBAUTE_PROFILE)
