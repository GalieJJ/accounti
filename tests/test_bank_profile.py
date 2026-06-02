from decimal import Decimal
from pathlib import Path

from accounti.importers import BANK_IMPORTERS
from accounti.importers.sparkasse import SparkasseImporter

BEISPIEL = Path(__file__).resolve().parents[1] / "examples" / "beispiel_sparkasse.csv"


def test_eingebaute_profile_registriert():
    for name in ("sparkasse", "ing", "dkb", "volksbank", "commerzbank"):
        assert name in BANK_IMPORTERS


def test_sparkasse_unveraendert():
    txs = SparkasseImporter().importiere(BEISPIEL)
    assert len(txs) == 8
    assert txs[0].gegenkonto_name == "Amazon Payments Europe S.C.A."
    assert txs[1].betrag == Decimal("-89.50")


def test_sparkasse_via_registry():
    txs = BANK_IMPORTERS["sparkasse"].importiere(BEISPIEL)
    assert len(txs) == 8


def test_ing_profil(tmp_path: Path):
    csv = tmp_path / "ing.csv"
    csv.write_text(
        "Buchung;Valuta;Auftraggeber/Empfänger;Buchungstext;"
        "Verwendungszweck;Betrag;Währung\n"
        "05.04.2026;05.04.2026;Stadtwerke;Lastschrift;Strom April;-75,00;EUR\n",
        encoding="utf-8",
    )
    txs = BANK_IMPORTERS["ing"].importiere(csv)
    assert len(txs) == 1
    assert txs[0].betrag == Decimal("-75.00")
    assert txs[0].gegenkonto_name == "Stadtwerke"
    assert txs[0].verwendungszweck == "Strom April"


def test_dkb_profil(tmp_path: Path):
    csv = tmp_path / "dkb.csv"
    csv.write_text(
        "Buchungstag;Wertstellung;Buchungstext;Auftraggeber / Begünstigter;"
        "Verwendungszweck;Betrag (EUR)\n"
        "10.04.2026;10.04.2026;Lastschrift;Finanzamt;USt-VZ;-432,10\n",
        encoding="utf-8",
    )
    txs = BANK_IMPORTERS["dkb"].importiere(csv)
    assert len(txs) == 1
    assert txs[0].betrag == Decimal("-432.10")
    assert txs[0].gegenkonto_name == "Finanzamt"
