"""Freigaben in der CLI an Rollen gebunden (Akzeptanz 3) — ohne Benutzer wie bisher."""

from datetime import datetime

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import session_factory
from accounti.models.auth import Rolle
from tests import test_cli_ustva as ustva
from tests import test_cli_zahlung as zahlung
from tests.auth_hilfe import (
    billige_hashes,
    lege_person_an,
    setze_schluessel,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def schluessel(monkeypatch):
    return setze_schluessel(monkeypatch)


@pytest.fixture(autouse=True)
def umgebung_sauber(tmp_path, monkeypatch, schluessel):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)


def personen(url):
    engine, fabrik = session_factory(url)
    jetzt = datetime.now()
    with fabrik() as s:
        p = {
            "jan": lege_person_an(s, "jan", Rolle.BETRACHTER, jetzt=jetzt),
            "eva": lege_person_an(s, "eva", Rolle.BUCHHALTER, jetzt=jetzt),
            "chef": lege_person_an(s, "chef", Rolle.FREIGEBER, jetzt=jetzt),
        }
    engine.dispose()
    return p


def zahlungslauf(tmp_path):
    url, config = zahlung._umgebung(tmp_path)
    basis = ["--db", url, "--config", config]
    r = runner.invoke(app, ["zahlung", "anlegen", *basis, "--von", "eva"])
    assert r.exit_code == 0, r.output
    return url, basis


def test_akzeptanz_3_zahlungslauf_nur_durch_freigeber(tmp_path, monkeypatch):
    url, basis = zahlungslauf(tmp_path)
    p = personen(url)
    for wer in ("jan", "eva"):  # betrachter, buchhalter
        r = runner.invoke(app, ["zahlung", "freigeben", "1", *basis, "--von", wer])
        assert r.exit_code == 1, r.output
        assert f"{wer} darf" in r.output and "Zahlungsläufe freigeben" in r.output
    r = runner.invoke(app, ["zahlung", "zeigen", "1", *basis])
    assert "entwurf" in r.output.lower()
    # der Freigeber mit Einmalcode
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].code(datetime.now()))
    r = runner.invoke(app, ["zahlung", "freigeben", "1", *basis, "--von", "chef"])
    assert r.exit_code == 0, r.output
    assert "Lauf 1 freigegeben" in r.output


def test_freigeber_ohne_richtigen_code_scheitert(tmp_path):
    url, basis = zahlungslauf(tmp_path)
    personen(url)
    r = runner.invoke(
        app, ["zahlung", "freigeben", "1", *basis, "--von", "chef"], input="000000\n"
    )
    assert r.exit_code == 1
    assert "Einmalcode falsch" in r.output


def test_einmalcode_wird_abgefragt(tmp_path):
    url, basis = zahlungslauf(tmp_path)
    p = personen(url)
    r = runner.invoke(
        app,
        ["zahlung", "freigeben", "1", *basis, "--von", "chef"],
        input=p["chef"].code(datetime.now()) + "\n",
    )
    assert r.exit_code == 0, r.output
    assert "Einmalcode für chef" in r.output


def test_akzeptanz_3_ustva_nur_durch_freigeber(tmp_path, monkeypatch):
    url, konfig = ustva.umgebung(tmp_path)
    p = personen(url)
    basis = ["--period", "2026-08", "--db", url, "--config", konfig]
    for wer in ("jan", "eva"):
        r = runner.invoke(app, ["ustva", "freigeben", *basis, "--von", wer])
        assert r.exit_code == 1, r.output
        assert "Steuermeldungen freigeben" in r.output
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].code(datetime.now()))
    r = runner.invoke(app, ["ustva", "freigeben", *basis, "--von", "chef"])
    assert r.exit_code == 0, r.output
    assert "Freigegeben von chef" in ustva.text(r)


def test_dauerfrist_freigabe_nur_durch_freigeber(tmp_path):
    url, konfig = ustva.umgebung(tmp_path)
    personen(url)
    r = runner.invoke(
        app,
        ["ustva", "dauerfrist", "--jahr", "2026", "--summe-vorjahr", "11000"]
        + ["--svz-vorjahr", "0", "--freigeben", "--von", "eva"]
        + ["--db", url, "--config", konfig],
    )
    assert r.exit_code == 1, r.output
    assert "eva darf" in r.output


def test_ohne_benutzer_wie_bisher(tmp_path):
    _, basis = zahlungslauf(tmp_path)
    r = runner.invoke(app, ["zahlung", "freigeben", "1", *basis, "--von", "jan"])
    assert r.exit_code == 0, r.output
