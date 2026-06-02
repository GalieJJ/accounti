from decimal import Decimal
from pathlib import Path

from accounti.importers.profil import BankProfil, ProfilImporter, parse_betrag
from accounti.models import TransaktionQuelle

BEISPIEL = Path(__file__).resolve().parents[1] / "examples" / "beispiel_sparkasse.csv"


def test_parse_betrag_deutsch():
    assert parse_betrag("1.250,00", ",") == Decimal("1250.00")
    assert parse_betrag("-89,50", ",") == Decimal("-89.50")


def test_parse_betrag_englisch():
    assert parse_betrag("1,250.00", ".") == Decimal("1250.00")
    assert parse_betrag("-89.50", ".") == Decimal("-89.50")


def test_signed_profil_parst_beispiel():
    profil = BankProfil(
        name="test",
        datum_spalte="Buchungstag",
        datum_format="%d.%m.%y",
        betrag_spalte="Betrag",
        verwendungszweck_spalte="Verwendungszweck",
        gegenkonto_spalte="Begünstigter/Zahlungspflichtiger",
    )
    txs = ProfilImporter(profil).importiere(BEISPIEL)
    assert len(txs) == 8
    assert txs[0].betrag == Decimal("1250.00")
    assert txs[0].quelle is TransaktionQuelle.BANK
    assert txs[1].betrag == Decimal("-89.50")


def test_soll_haben_modus(tmp_path: Path):
    csv = tmp_path / "vr.csv"
    csv.write_text(
        "Datum;Zweck;Soll;Haben\n"
        "01.04.2026;Rechnung Mueller;100,00;\n"
        "02.04.2026;Zahlungseingang;;250,00\n",
        encoding="utf-8",
    )
    profil = BankProfil(
        name="vr",
        delimiter=";",
        datum_spalte="Datum",
        datum_format="%d.%m.%Y",
        verwendungszweck_spalte="Zweck",
        betrag_modus="soll_haben",
        soll_spalte="Soll",
        haben_spalte="Haben",
    )
    txs = ProfilImporter(profil).importiere(csv)
    assert txs[0].betrag == Decimal("-100.00")  # Soll = Abgang
    assert txs[1].betrag == Decimal("250.00")  # Haben = Eingang
