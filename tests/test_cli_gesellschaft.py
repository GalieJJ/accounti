"""Mehrere Gesellschaften in der CLI (Spec 4.4, Akzeptanz 5)."""

import re

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from accounti.betrieb.kontext import aktueller_kontext, standardwerte_fuer
from accounti.cli import app
from tests.gesellschaft_hilfe import zwei_gesellschaften

runner = CliRunner()


@pytest.fixture
def umgebung(tmp_path, monkeypatch):
    u = zwei_gesellschaften(tmp_path)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_ARCHIV", "ACCOUNTI_GESELLSCHAFT"):
        monkeypatch.delenv(name, raising=False)
    return u


def run(*args, **kw):
    return runner.invoke(app, list(args), **kw)


ANSICHTEN = [
    (["kontakte", "liste"], "Alpha", "Beta"),
    (["opos", "liste", "--stichtag", "2026-12-01"], "A-RE-1", "B-RE-7"),
    (["opos", "staffel", "--stichtag", "2026-12-01"], "111,00", "777,00"),
    (["zahlung", "vorschlag", "--stichtag", "2026-12-01"], "A-RE-1", "B-RE-7"),
    (["belege", "liste"], "A-RE-1", "B-RE-7"),
]


@pytest.mark.parametrize(("befehl", "marke_a", "marke_b"), ANSICHTEN)
def test_akzeptanz_5_wechsel_aendert_die_ansichten(umgebung, befehl, marke_a, marke_b):
    a = run("--gesellschaft", "a", *befehl)
    assert a.exit_code == 0, a.output
    b = run("-g", "b", *befehl)
    assert b.exit_code == 0, b.output
    assert marke_a in a.output and marke_b not in a.output
    assert marke_b in b.output and marke_a not in b.output


def test_umgebungsvariable_waehlt_die_gesellschaft(umgebung, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_GESELLSCHAFT", "b")
    r = run("kontakte", "liste")
    assert r.exit_code == 0, r.output
    assert "Beta" in r.output and "Alpha" not in r.output


def test_ausdrueckliche_option_gewinnt(umgebung):
    r = run("-g", "a", "kontakte", "liste", "--db", umgebung.db["b"])
    assert r.exit_code == 0, r.output
    assert "Beta" in r.output and "Alpha" not in r.output


def test_jeder_befehl_bekommt_datenbank_archiv_und_konfiguration(umgebung):
    """Alle Ansichten: jeder Befehl mit --db/--archiv/--config, auch in Untergruppen."""
    werte = {"db": "DB-A", "archiv": "ARCHIV-A", "config": "KONFIG-A"}
    karte = standardwerte_fuer(get_command(app), werte)
    gefunden = 0

    def pruefe(befehl, unter, pfad):
        nonlocal gefunden
        for name, kind in befehl.commands.items():
            if getattr(kind, "commands", None):
                pruefe(kind, (unter or {}).get(name), [*pfad, name])
                continue
            for p in kind.params:
                if p.name in werte:
                    gefunden += 1
                    assert unter[name][p.name] == werte[p.name], [*pfad, name]

    pruefe(get_command(app), karte, [])
    assert gefunden > 150  # 127 Befehle mit --db, dazu --archiv und --config


def test_hilfe_zeigt_die_datenbank_der_gesellschaft(umgebung):
    """Stichprobe über drei Ebenen: Typer liest den Standard aus der default_map."""
    for befehl in (
        ["zahlung", "freigeben"],
        ["kanaele", "webhook", "starten"],
        ["classify"],
    ):
        r = run("-g", "b", *befehl, "--help", env={"COLUMNS": "300"})
        assert r.exit_code == 0, r.output
        text = re.sub(r"\s+", "", r.output)
        assert re.sub(r"\s+", "", umgebung.db["b"]) in text, befehl


def test_ohne_registry_und_umgebung_wie_bisher(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_ARCHIV", "ACCOUNTI_GESELLSCHAFT"):
        monkeypatch.delenv(name, raising=False)
    r = run("kontakte", "liste", "--help", env={"COLUMNS": "300"})
    assert "sqlite:///accounti.db" in r.output
    r = run("-g", "a", "kontakte", "liste")
    assert r.exit_code == 2
    assert "Keine Gesellschaften eingerichtet" in r.output


def test_acc_db_aus_der_umgebung(tmp_path, monkeypatch):
    u = zwei_gesellschaften(tmp_path)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    monkeypatch.setenv("ACCOUNTI_DB", u.db["a"])
    r = run("kontakte", "liste")
    assert r.exit_code == 0, r.output
    assert "Alpha" in r.output


def test_unbekannte_gesellschaft(umgebung):
    r = run("-g", "c", "kontakte", "liste")
    assert r.exit_code == 2
    assert "a, b" in r.output


def test_mehrere_ohne_standard_verlangen_die_option(umgebung):
    r = run("kontakte", "liste")
    assert r.exit_code == 2
    assert "--gesellschaft angeben" in r.output
    # die Liste der Gesellschaften geht auch ohne
    r = run("gesellschaft", "liste")
    assert r.exit_code == 0, r.output


def test_standard_aus_der_registry(tmp_path, monkeypatch):
    u = zwei_gesellschaften(tmp_path, standard="b")
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    monkeypatch.delenv("ACCOUNTI_GESELLSCHAFT", raising=False)
    r = run("kontakte", "liste")
    assert r.exit_code == 0, r.output
    assert "Beta" in r.output


def test_kontext_endet_mit_dem_befehl(umgebung):
    run("-g", "a", "kontakte", "liste")
    assert aktueller_kontext().gesellschaft is None


def test_gesellschaft_liste_und_zeigen_ohne_passwort(umgebung, monkeypatch):
    text = umgebung.registry.read_text(encoding="utf-8").replace(
        f"datenbank: '{umgebung.db['b']}'",
        "datenbank: 'postgresql+psycopg://accounti:${PG_TEST_PW}@db/b'",
    )
    umgebung.registry.write_text(text, encoding="utf-8")
    monkeypatch.setenv("PG_TEST_PW", "streng-geheim")
    r = run("gesellschaft", "liste")
    assert r.exit_code == 0, r.output
    assert "Alpha Papier GmbH" in r.output and "Beta Rahmen KG" in r.output
    r = run("gesellschaft", "zeigen", "b")
    assert r.exit_code == 0, r.output
    assert "streng-geheim" not in r.output
    assert "accounti:***@db/b" in r.output
    assert "SKR04" in r.output  # eigener Kontenrahmen
    assert "2026-07-01" in r.output  # eigenes Wirtschaftsjahr
