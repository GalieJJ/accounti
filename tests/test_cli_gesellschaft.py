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

    def pruefe(befehl, karte_hier, pfad):
        """Eigene Parameter (auch einer Gruppe mit Callback, Befund Betrieb B1) und
        rekursiv die Unterbefehle."""
        nonlocal gefunden
        for p in befehl.params:
            if p.name in werte:
                gefunden += 1
                assert karte_hier[p.name] == werte[p.name], pfad
        for name, kind in getattr(befehl, "commands", {}).items():
            pruefe(kind, (karte_hier or {}).get(name), [*pfad, name])

    pruefe(get_command(app), karte, [])
    assert gefunden > 150  # 127 Befehle mit --db, dazu --archiv und --config


GRUPPEN_MIT_CALLBACK = (["ustva"], ["pruefen"], ["journal"], ["nachfordern"])


def test_gruppen_mit_callback_nutzen_die_gesellschaft(umgebung, monkeypatch):
    """Befund Betrieb B1: ``ustva``, ``pruefen``, ``journal`` (Liste) und
    ``nachfordern`` liefen still gegen ``accounti.db`` im Arbeitsverzeichnis."""
    leer = umgebung.wurzel / "arbeit"
    leer.mkdir()
    monkeypatch.chdir(leer)
    for befehl in GRUPPEN_MIT_CALLBACK:
        r = run("-g", "a", *befehl, env={"COLUMNS": "300"})
        assert "Mehrere Gesellschaften" not in r.output, (befehl, r.output)
        assert not (leer / "accounti.db").exists(), befehl
    # ohne Registry, nur ACCOUNTI_DB (Docker-Abbild)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(leer / "fehlt.yaml"))
    monkeypatch.setenv("ACCOUNTI_DB", umgebung.db["a"])
    for befehl in GRUPPEN_MIT_CALLBACK:
        run(*befehl)
        assert not (leer / "accounti.db").exists(), befehl


def test_hilfe_zeigt_die_datenbank_der_gesellschaft(umgebung):
    """Stichprobe über drei Ebenen: Typer liest den Standard aus der default_map."""
    for befehl in (
        ["zahlung", "freigeben"],
        ["kanaele", "webhook", "starten"],
        ["classify"],
        *GRUPPEN_MIT_CALLBACK,
    ):
        r = run("-g", "b", *befehl, "--help", env={"COLUMNS": "300"})
        assert r.exit_code == 0, r.output
        text = re.sub(r"\s+", "", r.output)
        assert re.sub(r"\s+", "", umgebung.db["b"]) in text, befehl


@pytest.mark.parametrize(
    "befehl",
    [
        ["abschluss", "--help"],
        ["kasse", "buchen", "--help"],
        ["ustva", "--help"],
        ["ustva", "pruefen", "--help"],
        ["kontakte", "liste", "--help"],
    ],
)
def test_hilfe_ohne_gesellschaft(umgebung, befehl):
    """Befund Betrieb B11: Die Hilfe braucht keine Gesellschaft."""
    r = run(*befehl, env={"COLUMNS": "300"})
    assert r.exit_code == 0, r.output
    assert "Usage" in r.output and "--gesellschaft angeben" not in r.output


def test_hilfe_als_wert_ist_keine_hilfe(umgebung, monkeypatch):
    """``--help`` als Wert einer Option ist keine Hilfe — der Befehl liefe sonst ohne
    Gesellschaft gegen die Standarddatenbank."""
    leer = umgebung.wurzel / "arbeit"
    leer.mkdir()
    monkeypatch.chdir(leer)
    r = run("kasse", "buchen", "--text", "--help", "--betrag", "1")
    assert r.exit_code == 2, r.output
    assert "--gesellschaft angeben" in r.output
    assert not (leer / "accounti.db").exists()


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


def test_kaputte_konfiguration_blockiert_befehle_ohne_konfigurationsbedarf_nicht(
    tmp_path, monkeypatch
):
    """Befund B-M8: ``version`` und Befehle mit ``--db`` laufen weiter; wer eine
    Gesellschaft braucht oder Rechte prüft, bekommt den Fehler."""
    kaputt = tmp_path / "accounti.yaml"
    kaputt.write_text("mandant:\n  name: [kaputt\n", encoding="utf-8")
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(kaputt))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_ARCHIV", "ACCOUNTI_GESELLSCHAFT"):
        monkeypatch.delenv(name, raising=False)
    r = run("version")
    assert r.exit_code == 0, r.output
    db = f"sqlite:///{tmp_path / 'x.db'}"
    r = run("opos", "liste", "--db", db)
    assert r.exit_code == 0, r.output
    assert "kein gültiges YAML" in r.output  # als Warnung
    r = run("-g", "a", "opos", "liste")
    assert r.exit_code == 2 and "kein gültiges YAML" in r.output
    r = run("zahlung", "freigeben", "1", "--db", db, "--von", "x")
    assert r.exit_code == 1 and "kein gültiges YAML" in r.output


def test_regeln_je_gesellschaft_auch_in_der_cli(umgebung, monkeypatch):
    """Befund B-M4: ``classify``/``bank lauf`` und ``lerne`` nutzen die Regeldatei
    der Gesellschaft, nicht config/regeln.yaml."""
    from datetime import date
    from decimal import Decimal

    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_buchungen, speichere_transaktion
    from accounti.models import Transaktion, TransaktionQuelle

    monkeypatch.chdir(umgebung.wurzel)
    regel = (
        "- name: Galerie Rahmen\n  muster: RAHMENWERK\n  feld: beide\n"
        "  soll_konto: '{konto}'\n  haben_konto: '1200'\n  steuer_schluessel: 9\n"
        "  buchungstext: Rahmen\n"
    )
    (umgebung.wurzel / "a-regeln.yaml").write_text(
        regel.format(konto="3400"), encoding="utf-8"
    )
    (umgebung.wurzel / "b-regeln.yaml").write_text(
        regel.format(konto="5400"), encoding="utf-8"
    )
    for k in ("a", "b"):
        engine, fabrik = session_factory(umgebung.db[k])
        init_db(engine)
        with fabrik() as s:
            speichere_transaktion(
                s,
                Transaktion(
                    datum=date(2026, 10, 1),
                    quelle=TransaktionQuelle.BANK,
                    betrag=Decimal("-119.00"),
                    verwendungszweck="RAHMENWERK Lieferung 77",
                    gegenkonto_name="Rahmenwerk GmbH",
                    rohtext="RAHMENWERK",
                ),
            )
            s.commit()
        engine.dispose()
    for k, konto in (("a", "3400"), ("b", "5400")):
        r = run("-g", k, "classify", "--no-llm")
        assert r.exit_code == 0, r.output
        engine, fabrik = session_factory(umgebung.db[k])
        with fabrik() as s:
            assert [b.soll_konto for b in lade_buchungen(s)] == [konto], k
        engine.dispose()
    r = run(
        "-g", "b", "lerne", "--muster", "FARBE", "--soll", "5400", "--haben", "1200",
        "--name", "Farbe",
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    assert "FARBE" in (umgebung.wurzel / "b-regeln.yaml").read_text(encoding="utf-8")
    assert "FARBE" not in (umgebung.wurzel / "a-regeln.yaml").read_text(
        encoding="utf-8"
    )
    assert not (umgebung.wurzel / "config" / "regeln.yaml").exists()
