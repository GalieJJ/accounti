"""``accounti serve`` — Dienste aus Optionen oder Registry, Uvicorn-Optionen."""

import pytest
from typer.testing import CliRunner

from accounti.api import server
from accounti.api.dienste import Dienste
from accounti.cli import app
from tests.gesellschaft_hilfe import zwei_gesellschaften

runner = CliRunner()


@pytest.fixture
def gestartet(monkeypatch):
    aufrufe: list[tuple[Dienste, str, int]] = []
    monkeypatch.setattr(server, "starte", lambda d, h, p: aufrufe.append((d, h, p)))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_SYSTEM_DB"):
        monkeypatch.delenv(name, raising=False)
    return aufrufe


def test_eine_gesellschaft_aus_den_optionen(tmp_path, monkeypatch, gestartet):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    monkeypatch.delenv("ACCOUNTI_SCHLUESSEL", raising=False)
    config = tmp_path / "accounti.yaml"
    config.write_text(
        "mandant: {name: Galerie Muster GmbH}\nserver: {port: 8455}\n", encoding="utf-8"
    )
    db = f"sqlite:///{tmp_path / 'a.db'}"
    r = runner.invoke(
        app,
        [
            "serve",
            "--db",
            db,
            "--archiv",
            str(tmp_path / "archiv"),
            "--config",
            str(config),
        ],
    )
    assert r.exit_code == 0, r.output
    assert "Noch keine Benutzer" in r.output
    assert "ACCOUNTI_SCHLUESSEL fehlt" in r.output
    dienste, host, port = gestartet[0]
    assert (host, port) == ("127.0.0.1", 8455)
    assert list(dienste.gesellschaften) == ["standard"]
    g = dienste.gesellschaften["standard"]
    assert g.name == "Galerie Muster GmbH" and g.datenbank == db
    assert dienste.systemdatenbank == db


def test_registry_mit_allen_gesellschaften(tmp_path, monkeypatch, gestartet):
    u = zwei_gesellschaften(tmp_path)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    r = runner.invoke(app, ["serve", "--host", "0.0.0.0", "--port", "9000"])
    assert r.exit_code == 0, r.output
    dienste, host, port = gestartet[0]
    assert (host, port) == ("0.0.0.0", 9000)
    assert sorted(dienste.gesellschaften) == ["a", "b"]
    assert dienste.systemdatenbank == u.system


def test_uvicorn_ohne_zugriffsprotokoll_und_nur_vertraute_proxies():
    dienste = Dienste("sqlite://", {})
    optionen = server.uvicorn_optionen(dienste, "127.0.0.1", 8400)
    assert optionen["access_log"] is False
    assert optionen["proxy_headers"] is True
    assert optionen["forwarded_allow_ips"] == "127.0.0.1"
    assert optionen["server_header"] is False
