"""Nur Steuerschlüssel, die accounti kennt (Gesamttest 10b-1, Runde 4: g3w-web N5).

``korrigiere --steuer -1/0/-9/4 --grund …`` buchte Storno und Neubuchung mit diesem
Schlüssel und ohne Steuerbetrag — die Vorsteuer entfiel, erst die Voranmeldung
sperrte („Steuerschlüssel -1 hat keine Kennziffer“). Der Browser lehnte dieselbe
Eingabe ab („Unbekannter Steuerschlüssel“). Jetzt lehnt die Fachfunktion ab
(``storno._steuer``), für CLI, Browser und REST gleich; ebenso ``lerne --steuer``.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db.repo_kontierung import lade_kontierungsregeln
from accounti.db.repository import lade_buchungen
from accounti.models import BuchungStatus
from accounti.pruefung.storno import StornoError, korrigiere
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    buchung,
    db_url,
    kurz,
    make_session_fixture,
    umsatz,
)

runner = CliRunner()
UNBEKANNT = [-1, 0, -9, 4, 40, 1, 99]


@pytest.mark.parametrize("schluessel", UNBEKANNT)
@pytest.mark.parametrize("status", [BuchungStatus.GEPRUEFT, BuchungStatus.ZUR_PRUEFUNG])
def test_korrigiere_lehnt_unbekannten_schluessel_ab(make_session, schluessel, status):
    tx = umsatz("-59.50")
    b = buchung(tx, soll="4980", haben="1200", status=status)
    anlegen(make_session, tx, b)
    with make_session() as s:
        with pytest.raises(StornoError, match="Unbekannter Steuerschlüssel") as f:
            korrigiere(
                s, str(b.id), "4980", "1200", steuer=schluessel, grund="Probe",
                von="erika",
            )  # fmt: skip
        assert f.value.feld == "steuer"
        s.rollback()
        assert [x.steuer_schluessel for x in lade_buchungen(s)] == [9]


@pytest.fixture
def cli_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    from accounti.db import init_db, session_factory

    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    yield url, fabrik
    engine.dispose()


@pytest.mark.parametrize("schluessel", ["-1", "0", "-9", "4"])
def test_cli_korrigiere_unbekannter_schluessel_exit_1(cli_db, schluessel):
    url, fabrik = cli_db
    tx = umsatz("-59.50")
    b = buchung(tx, soll="4980", haben="1200", status=BuchungStatus.GEPRUEFT)
    anlegen(fabrik, tx, b)
    r = runner.invoke(
        app,
        ["korrigiere", kurz(b.id), "--soll", "4980", "--haben", "1200",
         "--steuer", schluessel, "--grund", "Probe", "--db", url],
        env={"COLUMNS": "250"},
    )  # fmt: skip
    assert r.exit_code == 1 and "Unbekannter Steuerschlüssel" in r.output, r.output
    with fabrik() as s:
        assert [x.steuer_schluessel for x in lade_buchungen(s)] == [9]


@pytest.mark.parametrize("schluessel", ["-1", "0", "4"])
def test_cli_lerne_unbekannter_schluessel_exit_1(cli_db, schluessel):
    url, fabrik = cli_db
    r = runner.invoke(
        app,
        ["lerne", "--muster", "telekom", "--soll", "4920", "--haben", "1200",
         "--name", "telekom", "--steuer", schluessel, "--db", url],
        env={"COLUMNS": "250"},
    )  # fmt: skip
    assert r.exit_code == 1 and "Unbekannter Steuerschlüssel" in r.output, r.output
    with fabrik() as s:
        assert lade_kontierungsregeln(s) == []
