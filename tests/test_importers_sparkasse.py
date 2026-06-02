from decimal import Decimal
from pathlib import Path

from accounti.importers.sparkasse import SparkasseImporter
from accounti.models import TransaktionQuelle

BEISPIEL = Path(__file__).resolve().parents[1] / "examples" / "beispiel_sparkasse.csv"


def test_importiert_alle_zeilen():
    txs = SparkasseImporter().importiere(BEISPIEL)
    assert len(txs) == 8


def test_parst_betrag_und_datum_deutsch():
    txs = SparkasseImporter().importiere(BEISPIEL)
    erste = txs[0]
    assert erste.betrag == Decimal("1250.00")        # "1.250,00"
    assert erste.datum.isoformat() == "2026-04-15"    # "15.04.26"
    assert erste.quelle is TransaktionQuelle.BANK


def test_negativer_betrag():
    txs = SparkasseImporter().importiere(BEISPIEL)
    aws = next(t for t in txs if "AWS" in t.verwendungszweck)
    assert aws.betrag == Decimal("-89.50")


def test_gegenkonto_name_gesetzt():
    txs = SparkasseImporter().importiere(BEISPIEL)
    assert txs[0].gegenkonto_name == "Amazon Payments Europe S.C.A."
