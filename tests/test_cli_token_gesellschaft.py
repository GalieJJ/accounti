"""Token-Namen und Anmeldeprotokoll je Gesellschaft (Gesamttest Betrieb B9).

Token-Namen waren über alle Gesellschaften eindeutig (Index nur auf ``name``): b konnte
kein Token „erp“ anlegen, solange a eines hatte, und es dort auch nicht widerrufen.
``benutzer protokoll`` zeigte einem Verwalter von b die Ereignisse von a.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repo_auth import lade_api_tokens, lade_ereignisse
from accounti.models.auth import Rolle
from tests.auth_hilfe import billige_hashes, lege_person_an, setze_schluessel
from tests.gesellschaft_hilfe import zwei_gesellschaften

runner = CliRunner()


@pytest.fixture(autouse=True)
def _umgebung(monkeypatch, tmp_path):
    billige_hashes(monkeypatch)
    setze_schluessel(monkeypatch)
    for name in (
        "ACCOUNTI_DB",
        "ACCOUNTI_ARCHIV",
        "ACCOUNTI_GESELLSCHAFT",
        "ACCOUNTI_EINMALCODE",
        "ACCOUNTI_SYSTEM_DB",
        "ACCOUNTI_BENUTZER",
    ):
        monkeypatch.delenv(name, raising=False)


def run(*args):
    return runner.invoke(app, list(args), env={"COLUMNS": "250"})


@pytest.fixture
def welt(tmp_path, monkeypatch):
    """chef verwaltet a und b, sven nur b (beide mit zweitem Faktor)."""
    u = zwei_gesellschaften(tmp_path)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    engine, fabrik = session_factory(u.system)
    init_db(engine)
    jetzt = datetime.now()
    with fabrik() as s:
        p = {
            "chef": lege_person_an(s, "chef", Rolle.VERWALTER, gesellschaft="a"),
            "sven": lege_person_an(s, "sven", Rolle.VERWALTER, gesellschaft="b"),
        }
        from accounti.auth.dienst import fuege_rolle_hinzu

        fuege_rolle_hinzu(s, p["chef"].benutzer, "b", Rolle.VERWALTER, jetzt, "t")
        s.commit()
    engine.dispose()
    codes = {n: list(x.codes) for n, x in p.items()}

    def als(name: str) -> None:
        monkeypatch.setenv("ACCOUNTI_BENUTZER", name)
        monkeypatch.setenv("ACCOUNTI_EINMALCODE", codes[name].pop())

    def lade(fn, *args, **kw):
        engine, fabrik = session_factory(u.system)
        with fabrik() as s:
            ergebnis = fn(s, *args, **kw)
        engine.dispose()
        return ergebnis

    return u, als, lade


def test_gleicher_tokenname_in_zwei_gesellschaften(welt):
    u, als, lade = welt
    for g in ("a", "b"):
        als("chef")
        r = run("-g", g, "token", "anlegen", "erp", "--recht", "opos:lesen")
        assert r.exit_code == 0, (g, r.output)
    assert sorted((t.gesellschaft, t.name) for t in lade(lade_api_tokens)) == [
        ("a", "erp"),
        ("b", "erp"),
    ]
    # in derselben Gesellschaft bleibt der Name eindeutig
    als("chef")
    r = run("-g", "b", "token", "anlegen", "erp", "--recht", "opos:lesen")
    assert r.exit_code == 1 and "schon ein aktives Token" in r.output
    # widerrufen wirkt nur in der gewählten Gesellschaft
    als("sven")
    r = run("-g", "b", "token", "widerrufen", "erp")
    assert r.exit_code == 0, r.output
    stand = {t.gesellschaft: t.widerrufen_am for t in lade(lade_api_tokens)}
    assert stand["b"] is not None and stand["a"] is None
    als("sven")
    r = run("-g", "b", "token", "widerrufen", "erp")
    assert r.exit_code == 1 and "kein aktives Token" in r.output


def test_index_je_gesellschaft_und_name(welt):
    u, _, _ = welt
    engine, _ = session_factory(u.system)
    zeile = (
        "INSERT INTO api_tokens (id, name, token_hash, gesellschaft, rechte, "
        "angelegt_von, angelegt_am) VALUES (:id, 'erp', :h, :g, '[]', 'x', "
        "'2026-10-01 00:00:00')"
    )
    with engine.begin() as v:
        v.execute(text(zeile), {"id": "1", "h": "h1", "g": "a"})
        v.execute(text(zeile), {"id": "2", "h": "h2", "g": "b"})
    with pytest.raises(IntegrityError), engine.begin() as v:
        v.execute(text(zeile), {"id": "3", "h": "h3", "g": "b"})
    engine.dispose()


def test_protokoll_zeigt_nur_die_eigenen_gesellschaften(welt):
    u, als, lade = welt
    als("chef")
    r = run("-g", "a", "token", "anlegen", "nur-a", "--recht", "opos:lesen")
    assert r.exit_code == 0, r.output
    als("sven")
    r = run("-g", "b", "benutzer", "protokoll", "--anzahl", "500")
    assert r.exit_code == 0, r.output
    assert "nur-a" not in r.output
    assert "token_angelegt" not in r.output
    als("chef")
    r = run("-g", "a", "benutzer", "protokoll", "--anzahl", "500")
    assert "nur-a" in r.output
    # Ereignisse ohne Gesellschaft (z.B. Anlegen eines Benutzers) bleiben sichtbar
    a = lade(lade_ereignisse, gesellschaften={"b"})
    assert all(e.gesellschaft in (None, "b") for e in a)
    assert any(e.gesellschaft is None for e in a)


def test_protokoll_ohne_gesellschaft_nur_ueber_benutzer_der_sicht(welt):
    """Nachprüfung N6: Ereignisse ohne Gesellschaft (Sperren, Codes, Passwort) über
    einen Benutzer, der nur in a Rollen hat, sah auch der Verwalter von b."""
    u, als, lade = welt
    engine, fabrik = session_factory(u.system)
    with fabrik() as s:
        lege_person_an(s, "eva", Rolle.BUCHHALTER, gesellschaft="a")
    engine.dispose()
    for befehl in ("sperren", "entsperren"):
        als("chef")
        r = run("-g", "a", "benutzer", befehl, "eva")
        assert r.exit_code == 0, r.output
    als("sven")
    r = run("-g", "b", "benutzer", "protokoll", "--anzahl", "500")
    assert r.exit_code == 0, r.output
    assert "eva" not in r.output
    assert "benutzer_angelegt" in r.output  # sven selbst, ohne Gesellschaft
    als("chef")
    r = run("-g", "a", "benutzer", "protokoll", "--anzahl", "500")
    assert "benutzer_deaktiviert" in r.output and "eva" in r.output


def test_protokoll_hilfe_ohne_befundnummer():
    """Nachprüfung N7: Die Hilfe zeigte „(Befund Betrieb B9)“ mitten im Satz."""
    r = run("benutzer", "protokoll", "--help")
    assert r.exit_code == 0, r.output
    assert "Befund" not in r.output and "Anmeldungen, Fehlversuche" in r.output
