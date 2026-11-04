"""``accounti serve`` prüft das Schema der Systemdatenbank (Baustein 10b): Ohne die
Migration ``…_add_benutzer_sprache`` scheiterte sonst jede Anmeldung."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from accounti.api import server
from accounti.cli import app
from tests.test_migration_web import KONTIERUNG, VOR, alembic, ok

runner = CliRunner()


@pytest.fixture
def gestartet(tmp_path, monkeypatch):
    aufrufe: list[object] = []
    monkeypatch.setattr(server, "starte", lambda d, h, p: aufrufe.append(d))
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_SYSTEM_DB"):
        monkeypatch.delenv(name, raising=False)
    return aufrufe


def _serve(tmp_path, db: str):  # noqa: ANN001, ANN202
    return runner.invoke(
        app,
        ["serve", "--db", db, "--archiv", str(tmp_path / "archiv"), "--config"]
        + [str(tmp_path / "accounti.yaml")],
    )


def test_start_ohne_migration_bricht_mit_hinweis_ab(tmp_path, gestartet):
    datei = tmp_path / "geheim-pfad.db"
    ok(alembic(datei, "upgrade", KONTIERUNG))  # Stand vor der Sprachspalte
    r = _serve(tmp_path, f"sqlite:///{datei}")
    assert r.exit_code == 2, r.output
    assert "auth_benutzer.sprache" in r.output and "accounti db upgrade" in r.output
    meldung = " ".join(r.output.split())
    assert "alembic upgrade head" in meldung
    # jede fehlende Spalte, auch die Vorlieben (Baustein 10c P1)
    assert "auth_benutzer.darstellung" in meldung
    assert "geheim-pfad" not in r.output and "sqlite" not in r.output
    assert gestartet == []
    # der Hinweis führt zum Ziel: nach accounti db upgrade startet serve
    r = runner.invoke(app, ["db", "upgrade", "--db", f"sqlite:///{datei}"])
    assert r.exit_code == 0, r.output
    r = _serve(tmp_path, f"sqlite:///{datei}")
    assert r.exit_code == 0, r.output
    assert len(gestartet) == 1


def test_start_ohne_vorlieben_bricht_mit_hinweis_ab(tmp_path, gestartet):
    """Baustein 10c P1: Stand vor den Vorlieben → Exit 2; die Meldung nennt jede
    fehlende Spalte, ``accounti db upgrade`` und ``alembic upgrade head`` als Gleichwert
    für Datenbanken mit Vermerk (AK61), aber keine URL."""
    datei = tmp_path / "geheim-pfad.db"
    ok(alembic(datei, "upgrade", VOR))
    r = _serve(tmp_path, f"sqlite:///{datei}")
    assert r.exit_code == 2, r.output
    meldung = " ".join(r.output.split())
    for spalte in ("darstellung", "fachansicht", "betraege_verbergen", "tastenkuerzel"):
        assert f"auth_benutzer.{spalte}" in meldung, spalte
    assert "auth_benutzer.sprache" not in meldung
    assert "accounti db upgrade" in meldung and "alembic upgrade head" in meldung
    assert "geheim-pfad" not in r.output and "sqlite" not in r.output
    assert gestartet == []


def test_frische_datenbank_startet(tmp_path, gestartet):
    r = _serve(tmp_path, f"sqlite:///{tmp_path / 'neu.db'}")
    assert r.exit_code == 0, r.output
    assert len(gestartet) == 1
