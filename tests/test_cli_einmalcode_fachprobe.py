"""Einmalcode erst nach der Fachprobe (gw-storno N3, besteht auf main).

Mit eingerichteten Benutzern verbrauchte die CLI den Einmalcode — auch einen
Wiederherstellungscode —, bevor die Fachlogik prüfte: ein Storno-Datum vor der
Buchung, eine Umbuchung als Regel, ein kaputtes Muster endeten mit Exit 1, der Code
war trotzdem weg. Jetzt läuft die Aktion zuerst zur Probe (zurückgerollt), wie im
Browser (Technik-M3); nur eine Aktion, die gelingt, verbraucht den Code.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repo_kontierung import lade_kontierungsregeln
from accounti.models import BuchungStatus
from accounti.models.auth import Rolle
from tests.auth_hilfe import billige_hashes, lege_person_an, setze_schluessel
from tests.pruefung_hilfe import anlegen, buchung, db_url, kurz, umsatz

runner = CliRunner()


@pytest.fixture(autouse=True)
def _umgebung(tmp_path, monkeypatch):
    billige_hashes(monkeypatch)
    setze_schluessel(monkeypatch)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def welt(tmp_path):
    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    with fabrik() as s:
        jan = lege_person_an(s, "jan", Rolle.BUCHHALTER, jetzt=datetime.now())
    engine.dispose()
    return url, jan


def _run(monkeypatch, code: str, *args: str):  # noqa: ANN202
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", code)
    return runner.invoke(app, [*args, "--von", "jan"], env={"COLUMNS": "250"})


def test_storno_mit_falschem_datum_verbraucht_den_code_nicht(welt, monkeypatch):
    url, jan = welt
    engine, fabrik = session_factory(url)
    tx = umsatz("-119.00", date(2026, 10, 5))
    b = buchung(tx, status=BuchungStatus.GEPRUEFT)
    anlegen(fabrik, tx, b)
    engine.dispose()
    code = jan.codes[0]  # Wiederherstellungscode: nur einmal gültig
    befehl = ["buchung", "storniere", kurz(b.id), "--grund", "doppelt", "--db", url]
    r = _run(monkeypatch, code, *befehl, "--datum", "2026-10-04")
    assert r.exit_code == 1 and "vor der Buchung" in r.output, r.output
    r = _run(monkeypatch, code, *befehl, "--datum", "2026-10-06")
    assert r.exit_code == 0 and "Storniert" in r.output, r.output
    r = _run(monkeypatch, code, *befehl, "--datum", "2026-10-06")
    assert r.exit_code == 1  # jetzt verbraucht (bzw. schon storniert)


def test_korrigiere_lernen_aus_umbuchung_verbraucht_den_code_nicht(welt, monkeypatch):
    url, jan = welt
    engine, fabrik = session_factory(url)
    tx = umsatz(
        "-300.00", date(2026, 10, 2), "Übertrag", "Probe GmbH", sachkonto="1210"
    )
    b = buchung(tx, soll="4900", haben="1210", schluessel=None, steuer=None)
    anlegen(fabrik, tx, b)
    code = jan.codes[1]
    befehl = ["korrigiere", kurz(b.id), "--soll", "1200", "--haben", "1210"]
    befehl += ["--grund", "Umbuchung", "--db", url]
    r = _run(monkeypatch, code, *befehl, "--lernen")
    assert r.exit_code == 1 and "Geldkonten" in r.output, r.output
    r = _run(monkeypatch, code, *befehl)
    assert r.exit_code == 0 and "Korrigiert" in r.output, r.output
    with fabrik() as s:
        assert lade_kontierungsregeln(s) == []
    engine.dispose()


def test_lerne_mit_kaputtem_muster_verbraucht_den_code_nicht(welt, monkeypatch):
    url, jan = welt
    code = jan.codes[2]
    basis = ["lerne", "--soll", "4920", "--haben", "1200", "--name", "telekom"]
    r = _run(monkeypatch, code, *basis, "--muster", "(kaputt", "--db", url)
    assert r.exit_code == 1 and "regulärer Ausdruck" in r.output, r.output
    r = _run(monkeypatch, code, *basis, "--muster", "telekom", "--db", url)
    assert r.exit_code == 0 and "gespeichert" in r.output, r.output


def test_ohne_recht_zuerst_die_rechtemeldung(welt, monkeypatch, tmp_path):
    """Die Probe läuft erst nach der Rechteprüfung — wer nicht buchen darf, sieht
    „darf nicht“, nicht den Fachfehler."""
    url, _ = welt
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        lege_person_an(s, "leo", Rolle.BETRACHTER, jetzt=datetime.now())
    engine.dispose()
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", "000000")
    r = runner.invoke(
        app,
        ["lerne", "--muster", "(kaputt", "--soll", "4920", "--haben", "1200",
         "--name", "x", "--db", url, "--von", "leo"],
    )  # fmt: skip
    assert r.exit_code == 1 and "darf" in r.output and "regulär" not in r.output


def test_bestaetige_mit_pruefregelfehler_verbraucht_den_code_nicht(welt, monkeypatch):
    """Gleiche Klasse: bestaetige prüft steuerschluessel_konto erst nach dem Code."""
    url, jan = welt
    engine, fabrik = session_factory(url)
    tx = umsatz("-119.00", date(2026, 10, 5), "Privat", "Max Mustermann")
    falsch = buchung(tx, soll="1800", haben="1200", schluessel=9)  # Privat + Vorsteuer
    richtig = buchung(tx, soll="4930", haben="1200", schluessel=9)
    anlegen(fabrik, tx, falsch, richtig)
    engine.dispose()
    code = jan.codes[3]
    r = _run(monkeypatch, code, "bestaetige", kurz(falsch.id), "--db", url)
    assert r.exit_code == 1, r.output
    r = _run(monkeypatch, code, "bestaetige", kurz(richtig.id), "--db", url)
    assert r.exit_code == 0 and "Freigegeben" in r.output, r.output
