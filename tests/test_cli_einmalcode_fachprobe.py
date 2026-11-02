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


def test_korrigiere_lernen_soll_gleich_haben_verbraucht_den_code_nicht(
    welt, monkeypatch
):
    """Runde 3: Aus einer Umbuchung wird mit ``--lernen`` eine Korrektur ohne Regel
    (gw2-merge B2) — der Fachfehler der Probe ist jetzt „Soll = Haben“."""
    url, jan = welt
    engine, fabrik = session_factory(url)
    tx = umsatz(
        "-300.00", date(2026, 10, 2), "Übertrag", "Probe GmbH", sachkonto="1210"
    )
    b = buchung(tx, soll="4900", haben="1210", schluessel=None, steuer=None)
    anlegen(fabrik, tx, b)
    code = jan.codes[1]
    befehl = ["korrigiere", kurz(b.id), "--grund", "Umbuchung", "--db", url]
    r = _run(monkeypatch, code, *befehl, "--soll", "1210", "--haben", "1210")
    assert r.exit_code == 1 and "dasselbe Konto" in r.output, r.output
    r = _run(
        monkeypatch, code, *befehl, "--soll", "1200", "--haben", "1210", "--lernen"
    )
    assert r.exit_code == 0 and "Korrigiert" in r.output, r.output
    assert "Keine Regel gelernt" in r.output
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


# --- Gesamttest 10b-1, Runde 3 (gw2-betrieb B-1/B-2) ----------------------------------


def test_regeln_deaktivieren_mit_tippfehler_verbraucht_den_code_nicht(
    welt, monkeypatch
):
    """Ein unbekannter Name oder eine schon deaktivierte Regel kostete einen
    Wiederherstellungscode."""
    url, jan = welt
    code = jan.codes[4]
    r = _run(
        monkeypatch, code, "lerne", "--muster", "strom", "--soll", "4240", "--haben",
        "1200", "--name", "strom", "--db", url,
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    code = jan.codes[5]
    befehl = ["regeln", "deaktivieren", "--grund", "falsch", "--db", url]
    r = _run(monkeypatch, code, *befehl[:2], "gibtsnicht", *befehl[2:])
    assert r.exit_code == 1 and "nicht gefunden" in r.output, r.output
    r = _run(monkeypatch, code, *befehl[:2], "strom", *befehl[2:])
    assert r.exit_code == 0 and "deaktiviert" in r.output, r.output
    code = jan.codes[6]
    r = _run(monkeypatch, code, *befehl[:2], "strom", *befehl[2:])
    assert r.exit_code == 1 and "schon deaktiviert" in r.output, r.output
    r = _run(
        monkeypatch, code, "lerne", "--muster", "gas", "--soll", "4240", "--haben",
        "1200", "--name", "gas", "--db", url,
    )  # fmt: skip
    assert r.exit_code == 0, r.output  # derselbe Code gilt noch


def test_regeln_uebernehmen_mit_kaputter_datei_meldung_und_code_bleibt(
    welt, monkeypatch, tmp_path
):
    url, jan = welt
    (tmp_path / "config").mkdir()
    datei = tmp_path / "config" / "regeln.yaml"
    datei.write_text("- name: gelernt_x\n  haben: [1200\n", encoding="utf-8")
    code = jan.codes[7]
    r = _run(monkeypatch, code, "regeln", "uebernehmen", "--db", url)
    assert r.exit_code == 1 and "kein gültiges YAML" in r.output, r.output
    assert "Traceback" not in r.output
    r = runner.invoke(app, ["regeln", "uebernehmen", "--probe", "--db", url])
    assert r.exit_code == 1 and "kein gültiges YAML" in r.output, r.output
    datei.write_text(
        "- name: gelernt_telekom\n  muster: telekom\n  soll_konto: '4920'\n"
        "  haben_konto: '1200'\n",
        encoding="utf-8",
    )
    r = _run(monkeypatch, code, "regeln", "uebernehmen", "--db", url)
    assert r.exit_code == 0 and "1 Regeln übernommen" in r.output, r.output


def test_kasse_und_periode_fachfehler_verbrauchen_den_code_nicht(welt, monkeypatch):
    """Runde 3: Gegenkonto = Kassenkonto (Soll = Haben) und ein Monat mit offenen
    Vorschlägen kosteten den Code."""
    url, jan = welt
    engine, fabrik = session_factory(url)
    tx = umsatz("-119.00", date(2026, 9, 5))
    anlegen(fabrik, tx, buchung(tx))  # Vorschlag im September
    engine.dispose()
    code = jan.codes[8]
    kasse = ["kasse", "buchen", "--text", "Porto", "--datum", "2026-10-02"]
    r = _run(monkeypatch, code, *kasse, "--betrag", "-5", "--konto", "1000",
             "--db", url)  # fmt: skip
    assert r.exit_code == 1 and "Kassenkonto" in r.output, r.output
    r = _run(monkeypatch, code, "periode", "schliessen", "2026-09", "--db", url)
    assert r.exit_code == 1 and "noch nicht freigegeben" in r.output, r.output
    r = _run(monkeypatch, code, *kasse, "--betrag", "50", "--konto", "1200",
             "--db", url)  # fmt: skip
    assert r.exit_code == 0 and "Bestand" in r.output, r.output
