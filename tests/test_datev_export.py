"""Tests für den DATEV-Export."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from accounti.export.datev import DATEVConfig, DATEVExporter
from accounti.models import Buchungssatz, BuchungStatus


def _beispiel_buchung(**kwargs) -> Buchungssatz:
    defaults = dict(
        transaktion_id=uuid4(),
        datum=date(2026, 4, 15),
        soll_konto="4970",
        haben_konto="1200",
        betrag_netto=Decimal("29.99"),
        steuer_schluessel=None,
        buchungstext="AWS Hosting April",
        status=BuchungStatus.GEPRUEFT,
        confidence=1.0,
    )
    defaults.update(kwargs)
    return Buchungssatz(**defaults)


class TestDATEVExporter:
    def test_export_erzeugt_datei(self, tmp_path: Path) -> None:
        config = DATEVConfig(
            berater_nummer="23426",
            mandanten_nummer="40005",
            datum_von=date(2026, 4, 1),
            datum_bis=date(2026, 4, 30),
        )
        exporter = DATEVExporter(config)
        buchungen = [_beispiel_buchung()]

        datei = exporter.exportiere(buchungen, tmp_path)

        assert datei.exists()
        assert datei.suffix == ".csv"
        assert "EXTF" in datei.read_text(encoding="cp1252")

    def test_export_enthaelt_header(self, tmp_path: Path) -> None:
        config = DATEVConfig(
            berater_nummer="99999",
            mandanten_nummer="00001",
        )
        exporter = DATEVExporter(config)
        buchungen = [_beispiel_buchung()]

        datei = exporter.exportiere(buchungen, tmp_path)
        inhalt = datei.read_text(encoding="cp1252")

        assert "99999" in inhalt
        assert "00001" in inhalt
        assert "accounti" in inhalt

    def test_export_mit_mehreren_buchungen(self, tmp_path: Path) -> None:
        config = DATEVConfig(
            berater_nummer="23426",
            mandanten_nummer="40005",
        )
        exporter = DATEVExporter(config)
        buchungen = [
            _beispiel_buchung(buchungstext="Buchung 1"),
            _beispiel_buchung(buchungstext="Buchung 2"),
            _beispiel_buchung(buchungstext="Buchung 3"),
        ]

        datei = exporter.exportiere(buchungen, tmp_path)
        zeilen = datei.read_text(encoding="cp1252").strip().split("\n")

        # Header + Spaltenüberschriften + 3 Datenzeilen = 5
        assert len(zeilen) == 5
