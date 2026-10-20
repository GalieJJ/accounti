"""CLI ``accounti marktplatz``: import, liste, zeigen, abgleichen."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import speichere_transaktion
from accounti.models import Transaktion, TransaktionQuelle

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "marktplatz"
runner = CliRunner()


def _text(r):
    return " ".join(r.output.split())


def _basis(tmp_path):
    return [
        "--db",
        f"sqlite:///{tmp_path / 'm.db'}",
        "--config",
        str(tmp_path / "accounti.yaml"),
    ]


def _import(tmp_path, *extra):
    return runner.invoke(
        app,
        [
            "marktplatz",
            "import",
            "amazon",
            str(FIXTURES / "amazon_abrechnung_v2.txt"),
            "--laender",
            str(FIXTURES / "amazon_bestellungen.txt"),
            "--archiv",
            str(tmp_path / "archiv"),
            *_basis(tmp_path),
            *extra,
        ],
    )


def _bankumsatz(tmp_path, betrag):
    engine, make = session_factory(f"sqlite:///{tmp_path / 'm.db'}")
    init_db(engine)
    with make() as s:
        speichere_transaktion(
            s,
            Transaktion(
                datum=date(2026, 8, 18),
                betrag=Decimal(betrag),
                verwendungszweck="AMAZON PAYMENTS EUROPE S.C.A.",
                quelle=TransaktionQuelle.BANK,
                rohtext="",
            ),
        )
        s.commit()


def test_import_liste_zeigen(tmp_path):
    r = _import(tmp_path)
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "Amazon 11223344556" in text
    assert "Auszahlung 209,85 € offen" in text
    r = runner.invoke(app, ["marktplatz", "liste", *_basis(tmp_path)[:2]])
    assert r.exit_code == 0, r.output
    assert "11223344556" in r.output and "gebucht" in r.output
    r = runner.invoke(
        app, ["marktplatz", "zeigen", "11223344556", *_basis(tmp_path)[:2]]
    )
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "erloes 438,29" in text
    assert "gebuehr -133,44" in text


def test_import_mit_bank_und_zweimal(tmp_path):
    _bankumsatz(tmp_path, "209.85")
    r = _import(tmp_path)
    assert r.exit_code == 0, r.output
    assert "abgeglichen mit dem Bankumsatz vom 18.08.2026" in _text(r)
    r = _import(tmp_path)
    assert r.exit_code == 0, r.output
    assert "schon importiert" in _text(r)


def test_abgleichen_spaeter_mit_abweichung(tmp_path):
    assert _import(tmp_path).exit_code == 0
    _bankumsatz(tmp_path, "209.00")
    r = runner.invoke(app, ["marktplatz", "abgleichen", *_basis(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "auszahlung_abweichung" in _text(r)


def test_unbekannter_marktplatz_und_kaputte_datei(tmp_path):
    datei = tmp_path / "x.csv"
    datei.write_text("a;b\n1;2\n", encoding="utf-8")
    r = runner.invoke(
        app, ["marktplatz", "import", "otto", str(datei), *_basis(tmp_path)]
    )
    assert r.exit_code == 1
    assert "otto" in r.output
    r = runner.invoke(
        app, ["marktplatz", "import", "amazon", str(datei), *_basis(tmp_path)]
    )
    assert r.exit_code == 1
    assert "Kopfzeile" in r.output
