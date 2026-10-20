"""CLI ``accounti abschluss …``."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from tests.abschluss_hilfe import buche

runner = CliRunner()
D = Decimal
IBAN = "DE02120300000000202051"


def _text(ergebnis):
    return " ".join(ergebnis.output.split())


@pytest.fixture
def umgebung(tmp_path):
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    engine, factory = session_factory(url)
    init_db(engine)
    config = str(tmp_path / "accounti.yaml")

    def run(gruppe, *args, mit_config=True):
        extra = ["--db", url] + (["--config", config] if mit_config else [])
        return runner.invoke(app, [gruppe, *args, *extra])

    yield run, factory
    engine.dispose()


def _bank_und_buchungen(run, factory: sessionmaker):
    r = run(
        "bank",
        "verbinde",
        "--iban",
        IBAN,
        "--bezeichnung",
        "Giro",
        mit_config=False,
    )
    assert r.exit_code == 0, r.output
    buche(factory, date(2026, 1, 1), "1200", "9000", "5000", "EB", beleg_nummer="EB")
    buche(factory, date(2026, 1, 1), "9000", "0880", "5000", "EB", beleg_nummer="EB")
    buche(
        factory,
        date(2026, 5, 1),
        "1200",
        "8400",
        "1000",
        steuer_schluessel=3,
        steuer_betrag=D("190"),
    )


def test_saldo_pruefen_susa(umgebung, tmp_path):
    run, factory = umgebung
    _bank_und_buchungen(run, factory)

    r = run("abschluss", "pruefen", "--jahr", "2026")
    assert r.exit_code == 1
    assert "fehlt" in _text(r) and "gesperrt" in _text(r)

    r = run(
        "abschluss",
        "saldo",
        "--konto",
        IBAN,
        "--stichtag",
        "31.12.2026",
        "--saldo",
        "6.000,00",
    )
    assert r.exit_code == 0, r.output
    r = run("abschluss", "pruefen", "--jahr", "2026")
    assert r.exit_code == 1 and "Differenz 190,00" in _text(r)

    run(
        "abschluss",
        "saldo",
        "--konto",
        IBAN,
        "--stichtag",
        "2026-12-31",
        "--saldo",
        "6190",
    )
    r = run("abschluss", "pruefen", "--jahr", "2026")
    assert r.exit_code == 0, r.output
    assert "keine Fehler" in _text(r)

    datei = tmp_path / "susa.csv"
    r = run("abschluss", "susa", "--jahr", "2026", "--csv", str(datei))
    assert r.exit_code == 0, r.output
    assert "6.190,00" in _text(r) and "Ergebnis" in _text(r)
    zeilen = datei.read_text(encoding="utf-8").splitlines()
    assert zeilen[0].startswith("Konto;Bezeichnung")
    assert any(z.startswith("1776;") and z.endswith(";-190,00") for z in zeilen)


def test_saldo_fuer_unbekanntes_konto(umgebung):
    run, _ = umgebung
    r = run(
        "abschluss",
        "saldo",
        "--konto",
        "DE00",
        "--stichtag",
        "2026-12-31",
        "--saldo",
        "1",
    )
    assert r.exit_code == 1 and "Kein Bankkonto" in _text(r)
