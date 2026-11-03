"""Fehlende oder kaputte ``pruefung.kontenrahmen_datei`` (Gesamttest 10b-1, Runde 5:
g4w N3): ``kasse buchen --konto …`` und ``korrigiere`` endeten mit einem Traceback
(``KonfigurationError`` aus der Prüfregel ``steuerschluessel_konto``) — jetzt eine
Meldung mit Exit 1, vor dem Einmalcode und ohne Buchung."""

from __future__ import annotations

from datetime import date

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db.repository import lade_buchungen
from accounti.models import BuchungStatus
from tests.pruefung_hilfe import anlegen, buchung, db_url, kurz, umsatz

runner = CliRunner()


@pytest.fixture(params=["fehlt", "kaputt"])
def welt(request, tmp_path, monkeypatch):
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    datei = tmp_path / "kontenrahmen.yaml"
    if request.param == "kaputt":
        datei.write_text("konten: [1, 2\n", encoding="utf-8")
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        "buchhaltung:\n  kontenrahmen: SKR03\n"
        f"pruefung:\n  kontenrahmen_datei: {datei}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(konfig))
    from accounti.db import init_db, session_factory

    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    yield url, fabrik, str(konfig)
    engine.dispose()


def _ohne_traceback(r) -> str:  # noqa: ANN001
    text = " ".join(r.output.split())
    assert r.exit_code == 1, r.output
    assert r.exception is None or isinstance(r.exception, SystemExit), r.exception
    assert "Kontenrahmen-Datei" in text and "Traceback" not in text
    return text


@pytest.mark.parametrize("steuer", [[], ["--steuer", "19"]])
def test_kasse_buchen_mit_konto_meldet_die_datei(welt, steuer):
    url, fabrik, konfig = welt
    c = ["--db", url, "--config", konfig]
    r = runner.invoke(
        app, ["kasse", "anfangsbestand", "--betrag", "100", "--datum", "2026-10-01", *c]
    )
    assert r.exit_code == 0, r.output
    r = runner.invoke(
        app,
        ["kasse", "buchen", "--betrag", "-10.70", "--text", "Porto", "--datum",
         "2026-10-02", "--konto", "4980", *steuer, *c],
        env={"COLUMNS": "250"},
    )  # fmt: skip
    _ohne_traceback(r)
    with fabrik() as s:
        assert lade_buchungen(s) == []


def test_korrigiere_meldet_die_datei(welt):
    url, fabrik, konfig = welt
    tx = umsatz("-119.00", date(2026, 10, 5))
    b = buchung(tx, status=BuchungStatus.ZUR_PRUEFUNG)
    anlegen(fabrik, tx, b)
    r = runner.invoke(
        app,
        ["korrigiere", kurz(b.id), "--soll", "4930", "--haben", "1200", "--steuer",
         "9", "--db", url, "--config", konfig],
        env={"COLUMNS": "250"},
    )  # fmt: skip
    _ohne_traceback(r)
    with fabrik() as s:
        assert [x.soll_konto for x in lade_buchungen(s)] == ["4900"]
