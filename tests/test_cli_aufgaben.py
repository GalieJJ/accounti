"""CLI ``accounti aufgaben`` — Liste, Zuweisung, Rückfragen, Prüfläufe, Übersicht."""

from datetime import date

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    speichere_beleg,
    speichere_buchung,
    speichere_transaktion,
)
from tests.aufgaben_hilfe import SmtpTestserver, buchung
from tests.test_bank_abgleich import quittung, umsatz

runner = CliRunner()


def _text(ergebnis):
    return " ".join(ergebnis.output.split())


@pytest.fixture
def umgebung(tmp_path, monkeypatch):
    """DB mit einem Umsatz ohne Beleg und einer unsicheren Buchung; leere Config."""
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "jan")
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    engine, factory = session_factory(url)
    init_db(engine)
    tx = umsatz()
    with factory() as s:
        speichere_transaktion(s, tx)
        speichere_buchung(s, buchung(datum=date(2026, 3, 13)))
        s.commit()
    engine.dispose()
    config = tmp_path / "accounti.yaml"
    config.write_text("aufgaben: {}\n", encoding="utf-8")
    return url, str(config), factory


def _run(umgebung, *args):
    url, config, _ = umgebung
    return runner.invoke(app, ["aufgaben", *args, "--db", url, "--config", config])


def _pruefen(umgebung, *args):
    return _run(umgebung, "pruefen", "--stichtag", "2026-03-31", *args)


def test_pruefen_ist_idempotent(umgebung):
    r = _pruefen(umgebung)
    assert r.exit_code == 0, r.output
    assert "kontierung_pruefen: 1 neu" in _text(r)
    assert "beleg_fehlt: 1 neu" in _text(r)
    r = _pruefen(umgebung)
    assert r.exit_code == 0, r.output
    assert "kontierung_pruefen: 0 neu, 1 unverändert" in _text(r)
    assert "beleg_fehlt: 0 neu, 1 unverändert" in _text(r)


def test_unzugewiesen_in_der_gemeinsamen_liste(umgebung):
    """Akzeptanz 6."""
    _pruefen(umgebung, "--lauf", "beleg_fehlt")
    r = _run(umgebung, "liste")
    assert r.exit_code == 0, r.output
    assert "Beleg fehlt" in _text(r) and "gemeinsam" in _text(r)
    r = _run(umgebung, "liste", "--unzugewiesen")
    assert "Beleg fehlt" in _text(r)
    r = _run(umgebung, "liste", "--zustaendig", "ich")
    assert "Keine Aufgaben für jan" in _text(r)
    assert "1 Aufgabe in der gemeinsamen Liste" in _text(r)
    assert "accounti aufgaben liste --unzugewiesen" in _text(r)


def test_zuweisen_kommentieren_zeigen_erledigen(umgebung):
    _pruefen(umgebung, "--lauf", "beleg_fehlt")
    r = _run(umgebung, "zuweisen", "1", "--an", "jan")
    assert r.exit_code == 0, r.output
    assert "#1 zugewiesen an jan" in _text(r)
    r = _run(umgebung, "liste", "--zustaendig", "ich")
    assert "Beleg fehlt" in _text(r)
    r = _run(umgebung, "kommentieren", "1", "--text", "Beim Lieferanten angefragt")
    assert r.exit_code == 0, r.output
    r = _run(umgebung, "status", "1", "wartet")
    assert r.exit_code == 0, r.output
    r = _run(umgebung, "zeige", "1")
    assert r.exit_code == 0, r.output
    t = _text(r)
    assert "Aufgabe #1" in t and "beleg_fehlt" in t and "wartet" in t
    assert "Umsatz 13.03.2026 -59,50 €" in t  # Bezugsobjekt
    assert "Beim Lieferanten angefragt" in t and "zugewiesen an jan" in t
    r = _run(umgebung, "erledigen", "1", "--text", "Beleg liegt vor")
    assert r.exit_code == 0, r.output
    assert "#1 erledigt" in _text(r)
    assert "Beleg fehlt" not in _text(_run(umgebung, "liste"))
    r = _run(umgebung, "liste", "--alle")
    assert "erledigt" in _text(r)
    r = _run(umgebung, "zuweisen", "1", "--frei")
    assert r.exit_code == 1 and "erledigt" in _text(r)


def test_rueckfrage_am_beleg_und_wiederfinden(umgebung):
    """Akzeptanz 4 über die Kommandozeile."""
    _, _, factory = umgebung
    b = quittung(dateiname="bewirtung.jpg")
    with factory() as s:
        speichere_beleg(s, b)
        s.commit()
    kurz = str(b.id)[:8]
    r = _run(umgebung, "rueckfrage", kurz, "--text", "Wer war beim Essen dabei?")
    assert r.exit_code == 0, r.output
    assert "Rückfrage am Beleg" in _text(r)
    r = _run(umgebung, "objekt", "beleg", kurz)
    assert r.exit_code == 0, r.output
    t = _text(r)
    assert "bewirtung.jpg" in t and "Wer war beim Essen dabei?" in t
    assert "Rückfrage" in t and "jan" in t
    r = _run(
        umgebung, "rueckfrage", kurz, "--text", "Bitte bis Freitag", "--an", "erika"
    )
    assert "#1" in _text(r) and "erika" in _text(r)
    r = _run(umgebung, "kommentieren", "--beleg", kurz, "--text", "Teilnehmerliste da")
    assert r.exit_code == 0, r.output
    t = _text(_run(umgebung, "objekt", "beleg", kurz))
    assert "Teilnehmerliste da" in t and "#1" in t


def test_beleg_trifft_ein_cli(umgebung):
    """Akzeptanz 3 mit vorhandenen Befehlen: bank abgleich, dann aufgaben pruefen."""
    url, _, factory = umgebung
    _pruefen(umgebung, "--lauf", "beleg_fehlt")
    with factory() as s:
        speichere_beleg(s, quittung())
        s.commit()
    r = runner.invoke(app, ["bank", "abgleich", "--db", url])
    assert r.exit_code == 0 and "1 abgeglichen" in _text(r)
    r = _pruefen(umgebung, "--lauf", "beleg_fehlt")
    assert "1 hinfällig" in _text(r)
    r = _run(umgebung, "zeige", "1")
    assert "hinfaellig" in _text(r) and "Beleg zugeordnet" in _text(r)


def test_fehler(umgebung):
    r = _run(umgebung, "zeige", "99")
    assert r.exit_code == 1 and "Keine Aufgabe" in _text(r)
    r = _run(umgebung, "status", "99", "fertig")
    assert r.exit_code == 1 and "offen, in_arbeit, wartet" in _text(r)
    r = _pruefen(umgebung, "--zeitraum", "März")
    assert r.exit_code == 1 and "JJJJ-MM" in _text(r)
    r = _run(umgebung, "kommentieren", "--text", "ohne Ziel")
    assert r.exit_code == 1


def test_erinnern_vorschau_und_versand(umgebung, tmp_path):
    url, _, _ = umgebung
    _pruefen(umgebung)
    server = SmtpTestserver().starte()
    try:
        config = tmp_path / "mit_versand.yaml"
        config.write_text(
            f"""
versand:
  absender: "Firma <rechnung@firma.example>"
  smtp: {{host: 127.0.0.1, port: {server.port}, verschluesselung: keine}}
aufgaben:
  benachrichtigung:
    empfaenger: {{gemeinsam: buchhaltung@firma.example}}
""",
            encoding="utf-8",
        )

        def erinnern(*args):
            return runner.invoke(
                app,
                ["aufgaben", "erinnern", "--stichtag", "2026-03-31", *args]
                + ["--db", url, "--config", str(config)],
            )

        r = erinnern("--vorschau")
        assert r.exit_code == 0, r.output
        assert "Gemeinsame Liste — Tagesübersicht vom 31.03.2026" in _text(r)
        assert server.nachrichten == []
        r = erinnern()
        assert r.exit_code == 0, r.output
        assert "gemeinsam: email an buchhaltung@firma.example — 2 Aufgaben" in _text(r)
        assert len(server.nachrichten) == 1
        r = erinnern()
        assert "heute schon zugestellt" in _text(r) or "Nichts zu melden" in _text(r)
        assert len(server.nachrichten) == 1
    finally:
        server.stoppe()


def test_erinnern_ohne_versand_konfiguration(umgebung):
    _pruefen(umgebung)
    r = _run(umgebung, "erinnern", "--stichtag", "2026-03-31")
    assert r.exit_code == 1
    assert "versand" in _text(r)


def test_lauf_fuer_cron(umgebung, tmp_path):
    url, _, _ = umgebung
    server = SmtpTestserver().starte()
    try:
        config = tmp_path / "lauf.yaml"
        config.write_text(
            f"""
versand:
  absender: "Firma <rechnung@firma.example>"
  smtp: {{host: 127.0.0.1, port: {server.port}, verschluesselung: keine}}
aufgaben:
  benachrichtigung:
    empfaenger: {{gemeinsam: buchhaltung@firma.example}}
""",
            encoding="utf-8",
        )
        r = runner.invoke(
            app,
            ["aufgaben", "lauf", "--stichtag", "2026-03-31"]
            + ["--db", url, "--config", str(config)],
        )
        assert r.exit_code == 0, r.output
        assert "beleg_fehlt: 1 neu" in _text(r)
        assert len(server.nachrichten) == 1
    finally:
        server.stoppe()
