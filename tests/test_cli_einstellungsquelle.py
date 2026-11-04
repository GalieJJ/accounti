"""Bindung der Einstellungen in der CLI (Baustein 10c P4, Schritt 3; D3, D5, M1, M2).

Jeder Befehl liest die Einstellungen aus **seiner** Datenbank: Der Callback legt einen
Stand an, jeder Parameter ``db`` (jeder Ebene) bindet ihn beim Parsen und nimmt sofort
den Schnappschuss. Ohne ``--db`` gilt beim ersten Lesen der Standard der Gesellschaft
bzw. ``ACCOUNTI_DB``, sonst ``befehle.STANDARD_DB``. Die Lader sind die Piloten aus
Schritt 2 (``lade_buchhaltung``, ``lade_elster``).
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
import typer
import typer.main
from sqlalchemy.engine import make_url
from typer.testing import CliRunner

from accounti.befehle import DB_OPTION, KONFIG_OPTION, STANDARD_DB
from accounti.betrieb.cli import Wurzelgruppe, richte_kontext_ein
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repo_einstellungen import fuege_version_an
from accounti.elster.konfiguration import lade_elster
from accounti.konfiguration import lade_buchhaltung
from tests.gesellschaft_hilfe import zwei_gesellschaften

runner = CliRunner()


@pytest.fixture(autouse=True)
def _umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_SYSTEM_DB"):
        monkeypatch.delenv(name, raising=False)


def _db(pfad: Path) -> str:
    url = f"sqlite:///{pfad}"
    engine, _ = session_factory(url)
    init_db(engine)
    engine.dispose()
    return url


def version(url: str, abschnitt: str, daten: dict) -> None:
    engine, fabrik = session_factory(url)
    try:
        with fabrik() as s:
            fuege_version_an(
                s, abschnitt, daten, person="erika", grund="Probe", quelle="cli"
            )
            s.commit()
    finally:
        engine.dispose()


def _konfig(tmp_path: Path, text: str, name: str = "c.yaml") -> str:
    pfad = tmp_path / name
    pfad.write_text(text, encoding="utf-8")
    return str(pfad)


ELSTER = "elster:\n  bundesland: BY\n  voranmeldungszeitraum: monat\n"


def _fristen(*argumente: str, env: dict[str, str] | None = None) -> str:
    r = runner.invoke(
        app,
        ["fristen", "--jahr", "2027", *argumente],
        env={"COLUMNS": "200", **(env or {})},
    )
    assert r.exit_code == 0, r.output
    return r.output


def _probe(befehl):  # noqa: ANN001, ANN202 - eigener Baum mit dem echten Callback
    probe = typer.Typer(cls=Wurzelgruppe)

    @probe.callback()
    def wurzel(
        ctx: typer.Context,
        gesellschaft: str | None = typer.Option(None, "--gesellschaft", "-g"),
    ) -> None:
        richte_kontext_ein(ctx, gesellschaft)

    probe.command("probe")(befehl)
    probe.command("anders")(lambda: None)
    return probe


def test_db_option_bindet_die_quelle(tmp_path):
    url = _db(tmp_path / "x.db")
    konfig = _konfig(tmp_path, ELSTER)
    assert "2027-01" in _fristen("--db", url, "--config", konfig)
    version(url, "elster", {"bundesland": "BY", "voranmeldungszeitraum": "quartal"})
    ausgabe = _fristen("--db", url, "--config", konfig)
    assert "2027-Q1" in ausgabe and "2027-01" not in ausgabe
    leer = _db(tmp_path / "leer.db")
    assert "2027-01" in _fristen("--db", leer, "--config", konfig)


def test_config_anderer_datei_datenbank_gilt(tmp_path):
    """E5: Die Datenbank des Befehls gilt auch bei einer anderen ``--config``."""
    url = _db(tmp_path / "x.db")
    version(url, "elster", {"voranmeldungszeitraum": "quartal"})
    andere = _konfig(tmp_path, ELSTER, "andere.yaml")
    assert "2027-Q1" in _fristen("--db", url, "--config", andere)


def test_befehl_ohne_db_nimmt_standardwert(tmp_path):
    """Ohne ``--db`` die Datenbank aus ``ACCOUNTI_DB`` — auch für einen Befehl, der
    gar keinen Parameter ``db`` hat (Ersatz beim ersten Lesen)."""
    url = _db(tmp_path / "x.db")
    version(url, "buchhaltung", {"kontenrahmen": "SKR04"})
    konfig = _konfig(tmp_path, "buchhaltung:\n  kontenrahmen: SKR03\n")

    def befehl(config: str = KONFIG_OPTION) -> None:
        typer.echo(lade_buchhaltung(config).kontenrahmen)

    r = runner.invoke(
        _probe(befehl), ["probe", "--config", konfig], env={"ACCOUNTI_DB": url}
    )
    assert r.exit_code == 0, r.output
    assert r.output.strip() == "SKR04"
    version(url, "elster", {"voranmeldungszeitraum": "quartal"})
    elster = _konfig(tmp_path, ELSTER, "e.yaml")
    assert "2027-Q1" in _fristen("--config", elster, env={"ACCOUNTI_DB": url})


def test_ohne_db_und_gesellschaft_standard_db(tmp_path, monkeypatch):
    """M1: Ohne ``--db`` und Gesellschaft nehmen alle Befehle ``./accounti.db`` — so
    sehen ``fristen`` und ``ustva`` denselben Voranmeldungszeitraum."""
    assert STANDARD_DB == "sqlite:///accounti.db"
    assert DB_OPTION.default == STANDARD_DB
    monkeypatch.chdir(tmp_path)
    url = _db(tmp_path / "accounti.db")
    version(url, "elster", {"bundesland": "BY", "voranmeldungszeitraum": "quartal"})
    konfig = _konfig(tmp_path, ELSTER)
    assert "2027-Q1" in _fristen("--config", konfig)
    r = runner.invoke(
        app,
        ["ustva", "--period", "2026-Q3", "--json", "--config", konfig],
        env={"COLUMNS": "250"},
    )
    assert "kein Voranmeldungszeitraum" not in r.output, r.output
    r = runner.invoke(
        app,
        ["ustva", "--period", "2026-08", "--json", "--config", konfig],
        env={"COLUMNS": "250"},
    )
    assert "kein Voranmeldungszeitraum" in " ".join(r.output.split()), r.output


def test_jeder_befehl_mit_config_hat_db():
    """M1: Jeder Befehl mit ``--config`` hat ``--db`` (Standard ``STANDARD_DB``) —
    sonst läse er die Einstellungen einer anderen Datenbank als ihre Nachbarn."""
    ausnahmen: dict[str, str] = {}  # Befehl → Grund; leer
    fehlt: list[str] = []
    falscher_standard: list[str] = []

    def lauf(befehl: object, pfad: list[str]) -> None:
        parameter = {p.name: p for p in getattr(befehl, "params", []) or []}
        name = " ".join(pfad)
        if "config" in parameter and "db" not in parameter and name not in ausnahmen:
            fehlt.append(name)
        if "db" in parameter and parameter["db"].default != STANDARD_DB:
            falscher_standard.append(name)
        for kind_name, kind in (getattr(befehl, "commands", {}) or {}).items():
            lauf(kind, [*pfad, kind_name])

    lauf(typer.main.get_command(app), ["accounti"])
    assert fehlt == []
    assert falscher_standard == []


def test_gesellschaft_bindet_ihre_datenbank(tmp_path, monkeypatch):
    """AK78: ``-g b`` liest die Einstellungen aus der Datenbank von b."""
    u = zwei_gesellschaften(tmp_path)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    version(u.db["b"], "elster", {"voranmeldungszeitraum": "quartal"})
    assert "2027-Q1" in _fristen(env={"ACCOUNTI_GESELLSCHAFT": "b"})
    ausgabe = _fristen(env={"ACCOUNTI_GESELLSCHAFT": "a"})
    assert "2027-01" in ausgabe and "2027-Q1" not in ausgabe


def test_gesellschaft_liste_zeigt_kontenrahmen_je_datenbank(tmp_path, monkeypatch):
    """M2: SKR04 nur als Version in b → ``liste`` und ``zeigen b`` zeigen SKR04, a
    bleibt SKR03; das Wirtschaftsjahr kommt ebenso aus der Datenbank von b."""
    u = zwei_gesellschaften(tmp_path)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    u.config["b"].write_text(
        "mandant:\n  name: Beta Rahmen KG\nbuchhaltung:\n  kontenrahmen: SKR03\n",
        encoding="utf-8",
    )
    version(u.db["b"], "buchhaltung", {"kontenrahmen": "SKR04"})
    version(u.db["b"], "datev", {"wirtschaftsjahr_beginn": "2025-10-01"})
    r = runner.invoke(app, ["gesellschaft", "liste"], env={"COLUMNS": "250"})
    assert r.exit_code == 0, r.output
    zeilen = {z.split("│")[1].strip(): z for z in r.output.splitlines() if "│" in z}
    assert "SKR03" in zeilen["a"] and "SKR04" in zeilen["b"]
    r = runner.invoke(app, ["gesellschaft", "zeigen", "b"], env={"COLUMNS": "250"})
    assert r.exit_code == 0, r.output
    assert "SKR04" in r.output and "2025-10-01" in r.output
    r = runner.invoke(app, ["gesellschaft", "zeigen", "a"], env={"COLUMNS": "250"})
    assert "SKR03" in r.output and "2026-01-01" in r.output


def test_fremder_registry_pfad_fail_closed(tmp_path, monkeypatch):
    """M2/D5: gebunden an a, der Lader liest die Konfiguration von b → abgewiesen
    (sonst sähe b die Datenbank-Werte von a); eine Datei außerhalb der Registry geht."""
    u = zwei_gesellschaften(tmp_path)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    r = runner.invoke(
        app,
        ["-g", "a", "fristen", "--jahr", "2027", "--config", str(u.config["b"])],
        env={"COLUMNS": "250"},
    )
    ausgabe = " ".join(r.output.split())
    assert r.exit_code == 1, r.output
    assert "anderen Gesellschaft" in ausgabe, ausgabe
    sonst = _konfig(tmp_path, ELSTER, "sonst.yaml")
    r = runner.invoke(app, ["-g", "a", "fristen", "--jahr", "2027", "--config", sonst])
    assert r.exit_code == 0, r.output


def test_schnappschuss_vor_dem_rumpf(tmp_path):
    """D3 (b): Der Schnappschuss entsteht beim Parsen — hält der Befehl danach die
    Schreibsperre seiner SQLite-Datei, liest der Lader trotzdem ohne Warten."""
    url = _db(tmp_path / "x.db")
    version(url, "buchhaltung", {"kontenrahmen": "SKR04"})
    konfig = _konfig(tmp_path, "buchhaltung:\n  kontenrahmen: SKR03\n")

    def befehl(db: str = DB_OPTION, config: str = KONFIG_OPTION) -> None:
        sperre = sqlite3.connect(str(make_url(db).database), timeout=0)
        try:
            sperre.execute("BEGIN EXCLUSIVE")
            beginn = time.monotonic()
            rahmen = lade_buchhaltung(config).kontenrahmen
            typer.echo(f"{rahmen} {time.monotonic() - beginn:.3f}")
        finally:
            sperre.rollback()
            sperre.close()

    r = runner.invoke(_probe(befehl), ["probe", "--db", url, "--config", konfig])
    assert r.exit_code == 0, r.output
    rahmen, dauer = r.output.split()
    assert rahmen == "SKR04" and float(dauer) < 1


def test_zwei_lader_ein_stand(tmp_path):
    """A54: Zwei Lader in einem Befehl sehen denselben Stand — auch wenn dazwischen
    eine neue Version entsteht."""
    url = _db(tmp_path / "x.db")
    version(url, "buchhaltung", {"kontenrahmen": "SKR04", "bank_konto": "1800"})
    konfig = _konfig(tmp_path, "")

    def befehl(db: str = DB_OPTION, config: str = KONFIG_OPTION) -> None:
        vorher = lade_buchhaltung(config).bank_konto
        version(db, "buchhaltung", {"kontenrahmen": "SKR03", "bank_konto": "1210"})
        nachher = lade_buchhaltung(config).bank_konto
        oss = lade_elster(config).konten_ohne_kennziffer  # SKR04: 3817
        typer.echo(f"{vorher} {nachher} {'3817' in oss}")

    r = runner.invoke(_probe(befehl), ["probe", "--db", url, "--config", konfig])
    assert r.exit_code == 0, r.output
    assert r.output.split() == ["1800", "1800", "True"]
    r = runner.invoke(_probe(befehl), ["probe", "--db", url, "--config", konfig])
    assert r.output.split()[0] == "1210"  # der nächste Befehl sieht die neue Version


def test_gruppe_mit_eigener_db_und_unterbefehl(tmp_path):
    """``ustva --db … pruefen --db …``: Gruppe und Unterbefehl binden je ihre
    Datenbank; es gilt die des Unterbefehls — dieselbe, die sein Rumpf liest."""
    gruppe = _db(tmp_path / "gruppe.db")
    unter = _db(tmp_path / "unter.db")
    version(unter, "elster", {"bundesland": "BY", "voranmeldungszeitraum": "quartal"})
    konfig = _konfig(tmp_path, ELSTER)
    befehl = ["ustva", "--db", gruppe, "--config", konfig, "pruefen"]
    r = runner.invoke(
        app,
        [*befehl, "--period", "2026-Q3", "--db", unter, "--config", konfig],
        env={"COLUMNS": "250"},
    )
    assert "kein Voranmeldungszeitraum" not in " ".join(r.output.split()), r.output
    r = runner.invoke(
        app,
        [*befehl, "--period", "2026-Q3", "--db", gruppe, "--config", konfig],
        env={"COLUMNS": "250"},
    )
    assert "kein Voranmeldungszeitraum" in " ".join(r.output.split()), r.output


def test_unlesbare_datenbank_meldung_statt_traceback(tmp_path):
    kaputt = tmp_path / "kaputt.db"
    kaputt.write_bytes(b"keine Datenbank" * 200)
    konfig = _konfig(tmp_path, ELSTER)
    r = runner.invoke(
        app,
        [
            "fristen",
            "--jahr",
            "2027",
            "--db",
            f"sqlite:///{kaputt}",
            "--config",
            konfig,
        ],
        env={"COLUMNS": "250"},
    )
    assert r.exit_code == 1, r.output
    assert isinstance(r.exception, SystemExit)
    assert "nicht lesen" in " ".join(r.output.split())


def test_neue_db_option_an_den_vier_befehlen(tmp_path):
    """M1: ``pruefen regeln``, ``kanaele connectoren`` und ``elster pin`` haben
    ``--db`` (``fristen`` zeigen die Tests oben)."""
    url = _db(tmp_path / "x.db")
    version(url, "pruefung", {"abgeschaltet": ["dublette"]})
    konfig = _konfig(tmp_path, "")
    r = runner.invoke(
        app,
        ["pruefen", "regeln", "--db", url, "--config", konfig],
        env={"COLUMNS": "250"},
    )
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["kanaele", "connectoren", "--db", url, "--config", konfig])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["elster", "pin", "--help"])
    assert "--db" in r.output
