from datetime import date
from decimal import Decimal

from accounti.export.datev import DATEVConfig, DATEVExporter
from accounti.models import Buchungssatz


def _buchung() -> Buchungssatz:
    return Buchungssatz(
        transaktion_id="00000000-0000-0000-0000-000000000000",
        datum=date(2026, 4, 15),
        soll_konto="4930",
        haben_konto="1200",
        betrag_netto=Decimal("100.00"),
        steuer_schluessel=9,
        steuer_betrag=Decimal("19.00"),
        buchungstext="Büromaterial",
    )


def _datenzeile(tmp_path) -> str:
    cfg = DATEVConfig(berater_nummer="23426", mandanten_nummer="40005")
    datei = DATEVExporter(cfg).exportiere([_buchung()], tmp_path)
    return datei.read_text(encoding="cp1252").splitlines()[2]


def test_betrag_nicht_gequotet(tmp_path):
    zeile = _datenzeile(tmp_path)
    assert zeile.startswith("119,00;")  # nicht "\"119,00\""


def test_konten_nicht_gequotet(tmp_path):
    felder = _datenzeile(tmp_path).split(";")
    assert felder[6] == "4930"  # Konto, ohne Quotes
    assert felder[7] == "1200"  # Gegenkonto, ohne Quotes


def test_text_gequotet(tmp_path):
    assert '"Büromaterial"' in _datenzeile(tmp_path)


def test_wkz_umsatz_leer(tmp_path):
    felder = _datenzeile(tmp_path).split(";")
    assert felder[2] == ""  # WKZ Umsatz leer
