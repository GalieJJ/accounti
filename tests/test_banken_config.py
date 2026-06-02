from decimal import Decimal
from pathlib import Path

from accounti.importers.profil import (
    ProfilImporter,
    lade_banken_profile,
)


def test_fehlende_datei_leeres_dict(tmp_path: Path):
    assert lade_banken_profile(tmp_path / "nope.yaml") == {}


def test_laedt_und_parst_eigenes_profil(tmp_path: Path):
    cfg = tmp_path / "banken.yaml"
    cfg.write_text(
        "- name: meinebank\n"
        "  delimiter: ','\n"
        "  datum_spalte: Date\n"
        "  datum_format: '%Y-%m-%d'\n"
        "  betrag_spalte: Amount\n"
        "  dezimal: '.'\n"
        "  verwendungszweck_spalte: Memo\n"
        "  erkennungs_spalten: [Date, Amount, Memo]\n",
        encoding="utf-8",
    )
    profile = lade_banken_profile(cfg)
    assert "meinebank" in profile
    assert profile["meinebank"].erkennungs_spalten == ("Date", "Amount", "Memo")

    data = tmp_path / "x.csv"
    data.write_text("Date,Amount,Memo\n2026-04-01,-12.50,Test\n", encoding="utf-8")
    txs = ProfilImporter(profile["meinebank"]).importiere(data)
    assert txs[0].betrag == Decimal("-12.50")
    assert txs[0].verwendungszweck == "Test"
