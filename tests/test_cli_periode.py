"""CLI ``accounti periode`` (Spec 4.5) — und die Sperre in anderen Befehlen."""

from datetime import date

from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.models import BuchungStatus
from tests.pruefung_hilfe import anlegen, buchung, db_url, kurz, umsatz

runner = CliRunner()


def _run(*args):
    return runner.invoke(app, [str(a) for a in args], env={"COLUMNS": "200"})


def test_schliessen_oeffnen_liste(tmp_path):
    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    vorschlag = buchung(tag=date(2026, 8, 3))
    anlegen(fabrik, vorschlag, umsatz(tag=date(2026, 8, 20)))

    r = _run("periode", "schliessen", "2026-08", "--db", url)
    assert r.exit_code == 1 and "Vorschlag" in r.output
    assert _run("bestaetige", kurz(vorschlag.id), "--db", url).exit_code == 0
    r = _run("periode", "schliessen", "2026-08", "--db", url)
    assert r.exit_code == 1 and "ungebucht" in r.output
    r = _run(
        "periode", "schliessen", "2026-08", "--db", url, "--trotzdem", "--von", "erika"
    )
    assert r.exit_code == 0, r.output
    assert "festgeschrieben" in r.output

    # korrigieren im gesperrten Monat nur per Storno mit Datum im offenen Monat
    r = _run(
        "korrigiere",
        kurz(vorschlag.id),
        "--soll",
        "4930",
        "--haben",
        "1200",
        "--steuer",
        "9",
        "--db",
        url,
    )
    assert r.exit_code == 1 and "--datum" in r.output
    r = _run(
        "korrigiere",
        kurz(vorschlag.id),
        "--soll",
        "4930",
        "--haben",
        "1200",
        "--steuer",
        "9",
        "--db",
        url,
        "--datum",
        "2026-09-01",
    )
    assert r.exit_code == 0, r.output

    r = _run("periode", "liste", "--db", url)
    assert (
        "2026-08" in r.output and "festgeschrieben" in r.output and "erika" in r.output
    )
    r = _run("periode", "oeffnen", "2026-08", "--db", url)
    assert r.exit_code != 0  # --grund fehlt
    r = _run(
        "periode",
        "oeffnen",
        "2026-08",
        "--db",
        url,
        "--grund",
        "Nachtrag",
        "--von",
        "jan",
    )
    assert r.exit_code == 0, r.output
    r = _run("periode", "liste", "--db", url)
    assert "offen" in r.output and "Nachtrag" in r.output
    r = _run("journal", "--vorgang", "periode_geoeffnet", "--db", url)
    assert "jan" in r.output and "Nachtrag" in r.output
    assert _run("journal", "pruefen", "--db", url).exit_code == 0
    engine.dispose()


def test_falsches_format(tmp_path):
    r = _run("periode", "schliessen", "08-2026", "--db", db_url(tmp_path))
    assert r.exit_code == 1 and "JJJJ-MM" in r.output


def test_freigeben_im_gesperrten_monat_ohne_traceback(tmp_path):
    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    auto = buchung(status=BuchungStatus.AUTO_GEBUCHT, tag=date(2026, 7, 3))
    anlegen(fabrik, auto)
    assert _run("periode", "schliessen", "2026-07", "--db", url).exit_code == 0
    r = _run("bestaetige", kurz(auto.id), "--db", url)
    assert r.exit_code == 1 and "festgeschrieben" in r.output
    assert "Traceback" not in r.output
    engine.dispose()
