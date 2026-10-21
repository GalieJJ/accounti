"""``accounti lerne`` und ``accounti regeln …`` — gelernte Regeln in der Datenbank
(Baustein 10b, Paket 1)."""

from __future__ import annotations

import os
import stat
from datetime import date

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repo_kontierung import lade_kontierungsregeln
from accounti.db.repository import lade_buchungen
from tests.pruefung_hilfe import anlegen, db_url, umsatz

runner = CliRunner()


@pytest.fixture(autouse=True)
def _umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def url(tmp_path):
    u = db_url(tmp_path)
    engine, _ = session_factory(u)
    init_db(engine)
    engine.dispose()
    return u


def run(*args):  # noqa: ANN002, ANN201
    return runner.invoke(app, [str(a) for a in args], env={"COLUMNS": "250"})


def regeln(url):  # noqa: ANN001, ANN201
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        r = lade_kontierungsregeln(s)
    engine.dispose()
    return r


def test_lerne_schreibt_in_die_datenbank(url, tmp_path):
    """Auch bei schreibgeschützter Regeldatei (Container: config/ nur lesbar)."""
    (tmp_path / "config").mkdir()
    datei = tmp_path / "config" / "regeln.yaml"
    datei.write_text("# eigene Regeln\n[]\n", encoding="utf-8")
    os.chmod(datei, stat.S_IRUSR)
    os.chmod(tmp_path / "config", stat.S_IRUSR | stat.S_IXUSR)
    try:
        r = run(
            "lerne", "--muster", r"telekom|t-mobile", "--soll", "4920", "--haben",
            "1200", "--steuer", "9", "--name", "telekom", "--richtung", "ausgabe",
            "--db", url,
        )  # fmt: skip
    finally:
        os.chmod(tmp_path / "config", stat.S_IRWXU)
        os.chmod(datei, stat.S_IRUSR | stat.S_IWUSR)
    assert r.exit_code == 0, r.output
    (regel,) = regeln(url)
    assert (regel.name, regel.muster, regel.ist_text) == (
        "telekom",
        "telekom|t-mobile",
        False,
    )
    assert regel.richtung is not None and regel.richtung.value == "ausgabe"
    assert datei.read_text(encoding="utf-8") == "# eigene Regeln\n[]\n"
    r = run("lerne", "--muster", "(kaputt", "--soll", "4920", "--haben", "1200",
            "--name", "x", "--db", url)  # fmt: skip
    assert r.exit_code == 1 and "regulärer Ausdruck" in r.output


def test_regeln_liste_und_deaktivieren(url):
    assert (
        run("regeln", "liste", "--db", url).output.strip() == "Keine gelernten Regeln."
    )
    run("lerne", "--muster", "aral", "--soll", "4530", "--haben", "1200",
        "--name", "tanken", "--db", url)  # fmt: skip
    r = run("regeln", "liste", "--db", url)
    assert r.exit_code == 0 and "tanken" in r.output and "aktiv" in r.output
    r = run("regeln", "deaktivieren", "tanken", "--grund", "Privatwagen", "--db", url)
    assert r.exit_code == 0, r.output
    assert "tanken" not in run("regeln", "liste", "--db", url).output
    alle = run("regeln", "liste", "--alle", "--db", url).output
    assert "Privatwagen" in alle
    r = run("regeln", "deaktivieren", "tanken", "--grund", "nochmal", "--db", url)
    assert r.exit_code == 1 and "schon deaktiviert" in r.output
    r = run("regeln", "deaktivieren", "gibtsnicht", "--grund", "x", "--db", url)
    assert r.exit_code == 1 and "nicht gefunden" in r.output


def test_regeln_uebernehmen_probe_und_echt(url, tmp_path):
    (tmp_path / "config").mkdir()
    datei = tmp_path / "config" / "regeln.yaml"
    inhalt = (
        "- name: miete\n  muster: miete\n  soll_konto: '4210'\n  haben_konto: '1200'\n"
        "- name: gelernt_stadtwerke\n  muster: Stadtwerke\n  feld: beide\n"
        "  soll_konto: '4240'\n  haben_konto: '1200'\n  steuer_schluessel: 9\n"
    )
    datei.write_text(inhalt, encoding="utf-8")
    r = run("regeln", "uebernehmen", "--probe", "--db", url)
    assert r.exit_code == 0 and "würde übernehmen" in r.output
    assert regeln(url) == []
    r = run("regeln", "uebernehmen", "--db", url)
    assert r.exit_code == 0 and "1 Regeln übernommen" in r.output
    assert [x.name for x in regeln(url)] == ["gelernt_stadtwerke"]
    r = run("regeln", "uebernehmen", "--db", url)
    assert "übersprungen" in r.output and len(regeln(url)) == 1
    assert datei.read_text(encoding="utf-8") == inhalt


def test_gelernte_regel_greift_beim_naechsten_classify(url, tmp_path):
    """Durchlauf in der CLI: Vorschlag → Korrektur mit --lernen → classify bucht den
    nächsten Umsatz derselben Gegenpartei nach der Regel (vor einer eigenen Regel,
    die falsch trifft)."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "regeln.yaml").write_text(
        "- name: buero_falsch\n  muster: 'b(ü|ue)ro'\n  feld: beide\n"
        "  soll_konto: '4980'\n  haben_konto: '1200'\n  steuer_schluessel: 9\n",
        encoding="utf-8",
    )
    engine, fabrik = session_factory(url)
    erster = umsatz("-59.50", date(2026, 10, 1), "RE 4711", "Bürobedarf Müller GmbH")
    anlegen(fabrik, erster)
    assert run("classify", "--no-llm", "--db", url).exit_code == 0
    with fabrik() as s:
        (b,) = lade_buchungen(s)
    assert b.soll_konto == "4980"
    from tests.pruefung_hilfe import kurz

    r = run("korrigiere", kurz(b.id), "--soll", "4930", "--haben", "1200",
            "--steuer", "9", "--lernen", "--db", url)  # fmt: skip
    assert r.exit_code == 0, r.output
    zweiter = umsatz("-12.00", date(2026, 10, 9), "RE 4790", "Bürobedarf Müller GmbH")
    erstattung = umsatz(
        "8.00", date(2026, 10, 9), "Gutschrift", "Bürobedarf Müller GmbH"
    )
    anlegen(fabrik, zweiter, erstattung)
    assert run("classify", "--no-llm", "--db", url).exit_code == 0
    with fabrik() as s:
        neu = {x.transaktion_id: x for x in lade_buchungen(s)}
    engine.dispose()
    assert neu[zweiter.id].soll_konto == "4930" and neu[zweiter.id].confidence == 1.0
    # die Erstattung trifft die (Ausgabe-)Regel nicht, nur die falsche eigene Regel
    assert neu[erstattung.id].soll_konto == "4980"
