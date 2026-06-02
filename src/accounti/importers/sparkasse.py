"""Sparkasse-CSV-Importer (CSV-CAMT-Format)."""
from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from accounti.importers import BANK_IMPORTERS, BankImporter
from accounti.models import Transaktion, TransaktionQuelle


def _lies_text(pfad: Path) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return pfad.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return pfad.read_text(encoding="latin-1")


def parse_betrag(roh: str) -> Decimal:
    """Deutsches Zahlenformat: '1.250,00' / '-89,50' -> Decimal."""
    return Decimal(roh.strip().replace(".", "").replace(",", "."))


def parse_datum(roh: str) -> date:
    """Deutsches Datum 'TT.MM.JJ' -> date."""
    return datetime.strptime(roh.strip(), "%d.%m.%y").date()


class SparkasseImporter(BankImporter):
    name = "sparkasse"

    def importiere(self, pfad: Path) -> list[Transaktion]:
        text = _lies_text(Path(pfad))
        reader = csv.DictReader(text.splitlines(), delimiter=";")
        transaktionen: list[Transaktion] = []
        for row in reader:
            if not row.get("Buchungstag"):
                continue
            transaktionen.append(
                Transaktion(
                    datum=parse_datum(row["Buchungstag"]),
                    betrag=parse_betrag(row["Betrag"]),
                    waehrung=(row.get("Währung") or "EUR").strip(),
                    verwendungszweck=(row.get("Verwendungszweck") or "").strip(),
                    gegenkonto_name=(row.get("Begünstigter/Zahlungspflichtiger") or "").strip()
                    or None,
                    gegenkonto_iban=(row.get("Kontonummer") or "").strip() or None,
                    quelle=TransaktionQuelle.BANK,
                    quelle_referenz=None,
                    rohtext=";".join(row.values()),
                )
            )
        return transaktionen


BANK_IMPORTERS[SparkasseImporter.name] = SparkasseImporter
