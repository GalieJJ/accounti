"""CLI ``accounti sicherung`` und ``accounti betrieb aufbewahrung``."""

import pytest
from typer.testing import CliRunner

from accounti.bank.tresor import neuer_schluessel
from accounti.cli import app
from tests.gesellschaft_hilfe import zwei_gesellschaften
from tests.test_betrieb_sicherung import befuelle, url

runner = CliRunner()


@pytest.fixture
def umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_ARCHIV", "ACCOUNTI_GESELLSCHAFT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ACCOUNTI_SICHERUNG_SCHLUESSEL", neuer_schluessel())
    return tmp_path


def test_sichern_pruefen_wiederherstellen(umgebung):
    db, archiv = befuelle(umgebung)
    ordner = umgebung / "sicherungen"  # gibt es noch nicht: „/“ am Ende = Ordner
    r = runner.invoke(
        app,
        [
            "sicherung",
            "erstellen",
            "--ziel",
            f"{ordner}/",
            "--db",
            db,
            "--archiv",
            str(archiv),
        ],
    )
    assert r.exit_code == 0, r.output
    assert "3 Buchungen" in r.output and "4 Belege" in r.output
    (datei,) = ordner.glob("accounti-standard-*.sicherung")
    r = runner.invoke(app, ["sicherung", "pruefen", str(datei)])
    assert r.exit_code == 0, r.output
    assert "vollständig und unverändert" in r.output
    neu = url(umgebung / "neu.db")
    r = runner.invoke(
        app,
        ["sicherung", "wiederherstellen", str(datei), "--db", neu]
        + ["--archiv", str(umgebung / "neu-archiv")],
    )
    assert r.exit_code == 0, r.output
    assert "Wiederhergestellt" in r.output
    # die Ansichten zeigen dasselbe
    vorher = runner.invoke(app, ["opos", "liste", "--db", db]).output
    nachher = runner.invoke(app, ["opos", "liste", "--db", neu]).output
    assert vorher == nachher and "RE-1" in nachher
    # ein zweites Mal geht nicht: Ziel nicht mehr leer
    r = runner.invoke(
        app,
        ["sicherung", "wiederherstellen", str(datei), "--db", neu]
        + ["--archiv", str(umgebung / "x")],
    )
    assert r.exit_code == 1 and "nicht leer" in r.output


def test_ohne_schluessel_wird_nichts_geschrieben(umgebung, monkeypatch):
    db, archiv = befuelle(umgebung)
    monkeypatch.delenv("ACCOUNTI_SICHERUNG_SCHLUESSEL")
    monkeypatch.delenv("ACCOUNTI_SCHLUESSEL", raising=False)
    ziel = umgebung / "s.sicherung"
    r = runner.invoke(
        app,
        [
            "sicherung",
            "erstellen",
            "--ziel",
            str(ziel),
            "--db",
            db,
            "--archiv",
            str(archiv),
        ],
    )
    assert r.exit_code == 1 and "fehlt" in r.output
    assert not ziel.exists()


def _beleg_im_archiv(db: str, archiv) -> None:
    """Ein echter Beleg im Archiv der Gesellschaft (die Posten der Testumgebung
    verweisen auf Dateien, die es nicht gibt)."""
    from accounti.belege.archiv import BelegArchiv
    from accounti.belege.kanaele import RohBeleg
    from accounti.belege.pipeline import nimm_auf
    from accounti.db import init_db, session_factory
    from tests.pdf_hilfe import pdf_mit_text

    engine, fabrik = session_factory(db)
    init_db(engine)
    with fabrik() as s:
        nimm_auf(
            s,
            BelegArchiv(archiv),
            RohBeleg(
                dateiname="b.pdf",
                inhalt=pdf_mit_text("Rechnung B"),
                kanal="ordner",
                herkunft="test",
            ),
        )
        s.commit()
    engine.dispose()


def test_mit_gesellschaft(umgebung, monkeypatch):
    u = zwei_gesellschaften(umgebung)
    _beleg_im_archiv(u.db["b"], u.archiv["b"])
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    ziel = umgebung / "b.sicherung"
    r = runner.invoke(app, ["-g", "b", "sicherung", "erstellen", "--ziel", str(ziel)])
    assert r.exit_code == 0, r.output
    assert "1 Belege ohne Datei im Archiv" in r.output
    r = runner.invoke(app, ["sicherung", "pruefen", str(ziel)])
    assert "2 Belege" in r.output and "1 Archivdateien" in r.output


def test_falscher_archivpfad_bricht_ab(umgebung):
    """Befund B-M1: Cron aus einem anderen Arbeitsverzeichnis — Archiv fehlt."""
    db, _ = befuelle(umgebung)
    r = runner.invoke(
        app, ["sicherung", "erstellen", "--ziel", str(umgebung / "s"), "--db", db]
    )
    assert r.exit_code == 1
    assert "fehlt oder ist leer" in r.output and "4 Belege verweisen" in r.output
    assert not (umgebung / "s").exists()


def test_systemdatenbank_sichern_ohne_gesellschaft(umgebung, monkeypatch):
    """Befund B-M9: ``--system`` ohne ``standard``, eindeutige Namen, eigene Art."""
    u = zwei_gesellschaften(umgebung, standard="a")
    _beleg_im_archiv(u.db["a"], u.archiv["a"])
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    from datetime import datetime

    from accounti.db import init_db, session_factory
    from accounti.models.auth import Rolle
    from tests.auth_hilfe import billige_hashes, lege_person_an

    billige_hashes(monkeypatch)
    engine, fabrik = session_factory(u.system)
    init_db(engine)
    with fabrik() as s:
        lege_person_an(
            s, "chef", Rolle.VERWALTER, gesellschaft="a", jetzt=datetime.now()
        )
    engine.dispose()
    ordner = f"{umgebung}/s/"
    for _ in range(2):  # zweimal in derselben Sekunde
        r = runner.invoke(app, ["sicherung", "erstellen", "--system", "--ziel", ordner])
        assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["sicherung", "erstellen", "--ziel", ordner])
    assert r.exit_code == 0, r.output
    namen = sorted(p.name for p in (umgebung / "s").iterdir())
    assert len([n for n in namen if n.startswith("accounti-system-")]) == 2
    assert len([n for n in namen if n.startswith("accounti-a-")]) == 1
    system = sorted((umgebung / "s").glob("accounti-system-*"))[0]
    # ohne standard bei mehreren Gesellschaften: --system braucht keine Wahl
    (umgebung / "zwei").mkdir()
    u2 = zwei_gesellschaften(umgebung / "zwei")
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u2.registry))
    r = runner.invoke(
        app, ["sicherung", "erstellen", "--system", "--ziel", f"{umgebung}/t/"]
    )
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["sicherung", "pruefen", str(system)])
    assert r.exit_code == 0 and "Systemdatenbank" in r.output
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    r = runner.invoke(
        app,
        ["sicherung", "wiederherstellen", str(system), "--ohne-archiv"]
        + ["--db", url(umgebung / "x.db")],
    )
    assert r.exit_code == 1 and "--system" in r.output
    leer = url(umgebung / "leer-system.db")
    monkeypatch.setenv("ACCOUNTI_SYSTEM_DB", leer)
    r = runner.invoke(app, ["sicherung", "wiederherstellen", str(system), "--system"])
    assert r.exit_code == 0, r.output
    from tests.api_hilfe import zaehle

    assert zaehle(leer, "SELECT count(*) FROM auth_benutzer") == 1


def test_wiederherstellen_in_die_falsche_gesellschaft(umgebung, monkeypatch):
    """Befund B-N3: ``-g b`` mit einer Sicherung von a bricht ab."""
    u = zwei_gesellschaften(umgebung)
    _beleg_im_archiv(u.db["a"], u.archiv["a"])
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    ziel = umgebung / "a.sicherung"
    r = runner.invoke(app, ["-g", "a", "sicherung", "erstellen", "--ziel", str(ziel)])
    assert r.exit_code == 0, r.output
    neu = ["--db", url(umgebung / "neu.db"), "--archiv", str(umgebung / "neu")]
    zurueck = ["-g", "b", "sicherung", "wiederherstellen", str(ziel), *neu]
    r = runner.invoke(app, zurueck)
    assert r.exit_code == 1 and "Gesellschaft a" in r.output
    r = runner.invoke(
        app,
        [*zurueck, "--fremde-gesellschaft"],
    )
    assert r.exit_code == 0, r.output


def test_schluessel(umgebung):
    r = runner.invoke(app, ["sicherung", "schluessel"])
    assert r.exit_code == 0
    assert len(r.output.splitlines()[0].strip()) == 44


def test_aufbewahrung(umgebung):
    db, _ = befuelle(umgebung)
    r = runner.invoke(
        app,
        ["betrieb", "aufbewahrung", "--db", db, "--stichtag", "2026-10-20"],
        env={"COLUMNS": "200"},
    )
    assert r.exit_code == 0, r.output
    assert "Buchungen" in r.output and "10 Jahre" in r.output
    assert "8 Jahre" in r.output and "Nichts wird automatisch gelöscht" in r.output


def test_aufbewahrung_mit_wirtschaftsjahr_aus_der_konfiguration(umgebung):
    """Befund A-N4/B-M6: Bücher je Wirtschaftsjahr (datev.wirtschaftsjahr_beginn)."""
    from datetime import date
    from decimal import Decimal

    from accounti.db import init_db, session_factory
    from accounti.db.repository import speichere_buchung
    from accounti.models import Buchungssatz

    db = url(umgebung / "wj.db")
    engine, fabrik = session_factory(db)
    init_db(engine)
    with fabrik() as s:
        speichere_buchung(
            s,
            Buchungssatz(
                datum=date(2015, 8, 1),  # WJ 2015/16 bei Beginn 1. Juli
                soll_konto="4930",
                haben_konto="1200",
                betrag_netto=Decimal("1.00"),
                buchungstext="x",
            ),
        )
        s.commit()
    engine.dispose()
    config = umgebung / "wj.yaml"
    config.write_text("datev:\n  wirtschaftsjahr_beginn: '2026-07-01'\n", "utf-8")
    befehl = ["betrieb", "aufbewahrung", "--db", db, "--stichtag", "2027-06-01"]
    mit = runner.invoke(app, [*befehl, "--config", str(config)], env={"COLUMNS": "200"})
    ohne = runner.invoke(app, befehl, env={"COLUMNS": "200"})
    assert mit.exit_code == 0 and ohne.exit_code == 0, mit.output + ohne.output
    zeile = next(z for z in mit.output.splitlines() if "Buchungen" in z)
    assert zeile.split("│")[-3].strip() == "0"  # bis 31.12.2027 aufzubewahren
    zeile = next(z for z in ohne.output.splitlines() if "Buchungen" in z)
    assert zeile.split("│")[-3].strip() == "1"  # Kalenderjahr 2015 → bis 2026
