"""CLI ``accounti pruefen`` (Spec 4.7) — Akzeptanz 1–3 über die Kommandozeile."""

from datetime import date

from typer.testing import CliRunner

from accounti.belege.archiv import BelegArchiv
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.pruefung.journal import lade_journal
from tests.pruefung_hilfe import anlegen, beleg, buchung, db_url, umsatz
from tests.test_pruefung_regeln import RECHNUNGSTEXT

runner = CliRunner()


def _run(*args):
    return runner.invoke(app, [str(a) for a in args], env={"COLUMNS": "250"})


def _umgebung(tmp_path, monkeypatch, config_text=""):
    monkeypatch.chdir(tmp_path)  # config/skr03.yaml relativ zum Arbeitsverzeichnis
    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    config = tmp_path / "accounti.yaml"
    config.write_text(
        "mandant:\n  name: Galerie Muster GmbH\n  ust_id: DE999999999\n" + config_text,
        encoding="utf-8",
    )
    return url, fabrik, str(config), engine


def test_akzeptanz_1_cli_zahlung_ohne_beleg(tmp_path, monkeypatch):
    url, fabrik, config, engine = _umgebung(tmp_path, monkeypatch)
    anlegen(fabrik, umsatz("-119.00", tag=date(2026, 8, 12)))
    with fabrik() as s:
        vorher = len(lade_journal(s))
    r = _run(
        "pruefen",
        "--period",
        "2026-08",
        "--regel",
        "umsatz_ohne_beleg",
        "--db",
        url,
        "--config",
        config,
        "--stichtag",
        "2026-10-20",
    )
    assert r.exit_code == 0, r.output  # nur eine Warnung
    assert "Zahlung ohne Beleg" in r.output
    assert "12.08.2026" in r.output and "-119,00" in r.output
    assert "Stadtwerke Hamburg" in r.output
    assert "1 Warnungen" in r.output
    with fabrik() as s:
        assert len(lade_journal(s)) == vorher  # Prüfregeln ändern nichts
    engine.dispose()


def test_akzeptanz_2_und_3_cli_fehler_mit_exit_1(tmp_path, monkeypatch):
    url, fabrik, config, engine = _umgebung(tmp_path, monkeypatch)
    archiv = BelegArchiv(tmp_path / "archiv")
    datei_hash = archiv.ablegen(RECHNUNGSTEXT.format(zusatz="").encode(), ".txt")
    anlegen(
        fabrik,
        beleg(
            datei_hash=datei_hash,
            netto="500.00",
            steuer="95.00",
            brutto="595.00",
            positionen=[("Papier", "500.00", "19", "95.00")],
        ),
        buchung(soll="1200", haben="8400", schluessel=9),
    )
    r = _run(
        "pruefen",
        "--db",
        url,
        "--config",
        config,
        "--archiv",
        tmp_path / "archiv",
        "--regel",
        "pflichtangaben",
        "--regel",
        "steuerschluessel_konto",
    )
    assert r.exit_code == 1, r.output
    assert "unvollständig nach § 14 Abs. 4 UStG" in r.output
    assert "Steuernummer oder USt-IdNr." in r.output
    assert "passt nicht zum Sachkonto" in r.output and "Erlöskonto 8400" in r.output
    engine.dispose()


def test_ohne_befunde_und_regelliste(tmp_path, monkeypatch):
    url, _, config, engine = _umgebung(
        tmp_path,
        monkeypatch,
        "pruefung:\n  abgeschaltet: [op_alter]\n"
        "  regeln:\n    umsatz_ohne_beleg: {ab_betrag: 5}\n",
    )
    r = _run("pruefen", "--db", url, "--config", config)
    assert r.exit_code == 0, r.output
    assert "keine Befunde" in r.output
    r = _run("pruefen", "regeln", "--config", config)
    assert r.exit_code == 0, r.output
    assert "op_alter (aus)" in r.output and "ab_betrag=5" in r.output
    engine.dispose()


def test_falsche_angaben_ohne_traceback(tmp_path, monkeypatch):
    url, _, config, engine = _umgebung(
        tmp_path, monkeypatch, "pruefung:\n  abgeschaltet: [gibt_es_nicht]\n"
    )
    for args in (
        ["pruefen", "--db", url, "--config", config],
        ["pruefen", "--db", url, "--period", "08-2026"],
        ["pruefen", "--db", url, "--regel", "nix"],
    ):
        r = _run(*args)
        assert r.exit_code == 1, r.output
        assert "Traceback" not in r.output
    engine.dispose()
