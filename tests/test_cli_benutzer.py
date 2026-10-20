"""CLI ``accounti benutzer`` und ``accounti token`` (Spec 4.7)."""

from datetime import datetime

import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from accounti.auth import totp
from accounti.cli import app
from accounti.db import session_factory
from accounti.db.repo_auth import lade_api_tokens, lade_benutzer, rollen_von
from tests.auth_hilfe import billige_hashes, setze_schluessel

runner = CliRunner()
GEHEIMNIS = b"0123456789abcdefghij"
PW = "ein langer geheimer Satz"


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def schluessel(monkeypatch):
    return setze_schluessel(monkeypatch)


@pytest.fixture
def db(tmp_path, monkeypatch, schluessel):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "chef")
    monkeypatch.setattr(totp, "neues_geheimnis", lambda: GEHEIMNIS)
    return f"sqlite:///{tmp_path / 'a.db'}"


def run(db, *args, input=None):
    return runner.invoke(app, [*args, "--db", db], input=input, env={"COLUMNS": "250"})


def code(versatz: int = 0) -> str:
    return totp.code(GEHEIMNIS, datetime.now().timestamp() + 30 * versatz)


def lade(db, fn, *args):
    engine, fabrik = session_factory(db)
    with fabrik() as s:
        ergebnis = fn(s, *args)
    engine.dispose()
    return ergebnis


def chef_mit_2fa(db):
    r = run(
        db, "benutzer", "anlegen", "chef", "--rolle", "verwalter", input=f"{PW}\n{PW}\n"
    )
    assert r.exit_code == 0, r.output
    # Einrichtung mit dem Code des aktuellen Schritts, danach code(1)
    r = run(db, "benutzer", "2fa", "chef", input=code() + "\n")
    assert r.exit_code == 0, r.output
    return r


def wiederherstellungscodes(ausgabe: str) -> list[str]:
    zeilen = [z.strip() for z in ausgabe.splitlines()]
    return [z for z in zeilen if len(z) == 11 and z[5] == "-"]


def frische_codes(monkeypatch, db):
    """Jeder Befehl braucht einen eigenen Einmalcode — hier die zehn
    Wiederherstellungscodes des Verwalters, jeder genau einmal."""
    codes = iter(wiederherstellungscodes(chef_mit_2fa(db).output))
    return lambda: monkeypatch.setenv("ACCOUNTI_EINMALCODE", next(codes))


def test_erster_benutzer_muss_verwalter_sein(db):
    r = run(
        db, "benutzer", "anlegen", "jan", "--rolle", "buchhalter", input=f"{PW}\n{PW}\n"
    )
    assert r.exit_code == 1
    assert "verwalter" in r.output


def test_anlegen_passwortregeln_und_unbekannte_rolle(db):
    r = run(db, "benutzer", "anlegen", "chef", "--rolle", "chef")
    assert r.exit_code == 1 and "Unbekannte Rolle" in r.output
    r = run(
        db, "benutzer", "anlegen", "chef", "--rolle", "verwalter", input="kurz\nkurz\n"
    )
    assert r.exit_code == 1 and "mindestens 12" in r.output
    r = run(db, "benutzer", "anlegen", "Chef Mann", "--rolle", "verwalter")
    assert r.exit_code == 1 and "Ungültiger Benutzername" in r.output


def test_einrichten_2fa_und_wiederherstellungscodes(db):
    r = chef_mit_2fa(db)
    assert "otpauth://totp/accounti:chef?secret=" in r.output
    assert totp.base32(GEHEIMNIS)[:4] in r.output
    assert len(set(wiederherstellungscodes(r.output))) == 10
    b = lade(db, lade_benutzer, "chef")
    assert b.totp_aktiv
    # weder Passwort noch Geheimnis im Klartext in der Datenbank
    engine, fabrik = session_factory(db)
    with fabrik() as s:
        alles = " ".join(str(z) for z in s.execute(text("SELECT * FROM auth_benutzer")))
    engine.dispose()
    assert PW not in alles and totp.base32(GEHEIMNIS) not in alles


def test_falscher_code_bei_der_einrichtung(db):
    run(
        db, "benutzer", "anlegen", "chef", "--rolle", "verwalter", input=f"{PW}\n{PW}\n"
    )
    r = run(db, "benutzer", "2fa", "chef", input="000000\n")
    assert r.exit_code == 1 and "passt nicht" in r.output
    assert not lade(db, lade_benutzer, "chef").totp_aktiv


def test_nach_der_einrichtung_nur_verwalter_mit_code(db, monkeypatch):
    chef_mit_2fa(db)
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "eva")
    r = run(db, "benutzer", "anlegen", "eva", "--rolle", "verwalter", input="x\n")
    assert r.exit_code == 1, r.output
    assert "eva ist kein aktiver Benutzer" in r.output
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "chef")
    r = run(db, "benutzer", "anlegen", "eva", "--rolle", "buchhalter", input="000000\n")
    assert r.exit_code == 1 and "Einmalcode falsch" in r.output
    r = run(
        db,
        "benutzer",
        "anlegen",
        "eva",
        "--rolle",
        "buchhalter",
        "--anzeigename",
        "Eva Muster",
        input=f"{code(1)}\n{PW}\n{PW}\n",
    )
    assert r.exit_code == 0, r.output
    assert "eva angelegt" in r.output


def test_liste_rolle_sperren_entsperren(db, monkeypatch):
    frisch = frische_codes(monkeypatch, db)
    frisch()
    r = run(
        db, "benutzer", "anlegen", "eva", "--rolle", "buchhalter", input=f"{PW}\n{PW}\n"
    )
    assert r.exit_code == 0, r.output
    frisch()
    r = run(db, "benutzer", "rolle", "eva", "--rolle", "freigeber")
    assert r.exit_code == 0, r.output
    eva = lade(db, lade_benutzer, "eva")
    assert {z.rolle.value for z in lade(db, rollen_von, eva.id)} == {
        "buchhalter",
        "freigeber",
    }
    frisch()
    r = run(db, "benutzer", "rolle", "eva", "--rolle", "freigeber", "--entfernen")
    assert r.exit_code == 0, r.output
    frisch()
    r = run(db, "benutzer", "sperren", "eva")
    assert r.exit_code == 0
    assert not lade(db, lade_benutzer, "eva").aktiv
    frisch()
    r = run(db, "benutzer", "liste")
    assert r.exit_code == 0, r.output
    assert (
        "eva" in r.output
        and "gesperrt" in r.output
        and "standard: buchhalter" in r.output
    )
    frisch()
    r = run(db, "benutzer", "entsperren", "eva")
    assert r.exit_code == 0
    assert lade(db, lade_benutzer, "eva").aktiv
    frisch()
    r = run(db, "benutzer", "protokoll")
    assert r.exit_code == 0, r.output
    assert "rolle_hinzugefuegt" in r.output and "benutzer_deaktiviert" in r.output


def test_passwort_selbst_aendern(db, monkeypatch):
    chef_mit_2fa(db)
    alt = lade(db, lade_benutzer, "chef").passwort_hash
    neu = "ein ganz anderer langer Satz"
    r = run(db, "benutzer", "passwort", "chef", input=f"{code(1)}\n{neu}\n{neu}\n")
    assert r.exit_code == 0, r.output
    assert lade(db, lade_benutzer, "chef").passwort_hash != alt


def test_token_anlegen_liste_widerrufen(db, monkeypatch):
    frisch = frische_codes(monkeypatch, db)
    frisch()
    r = run(
        db,
        "token",
        "anlegen",
        "erp",
        "--recht",
        "opos:lesen",
        "--recht",
        "belege:schreiben",
    )
    assert r.exit_code == 0, r.output
    klartext = next(
        z.strip()
        for z in r.output.splitlines()
        if "accounti_api_" in z and "Bearer" not in z
    )
    t = lade(db, lade_api_tokens)[0]
    assert klartext not in t.token_hash
    assert [x.value for x in t.rechte] == ["belege:schreiben", "opos:lesen"]
    assert t.angelegt_von == "chef"
    frisch()
    r = run(db, "token", "anlegen", "x", "--recht", "zahlung:freigeben")
    assert r.exit_code == 1 and "Unbekanntes Recht" in r.output
    frisch()
    r = run(db, "token", "liste")
    assert "erp" in r.output and klartext not in r.output
    frisch()
    r = run(db, "token", "widerrufen", "erp")
    assert r.exit_code == 0
    assert lade(db, lade_api_tokens)[0].widerrufen_am is not None


def test_token_bei_mehreren_gesellschaften_nur_mit_auswahl(
    tmp_path, monkeypatch, schluessel
):
    from tests.gesellschaft_hilfe import zwei_gesellschaften

    u = zwei_gesellschaften(tmp_path)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    monkeypatch.delenv("ACCOUNTI_GESELLSCHAFT", raising=False)
    r = runner.invoke(app, ["token", "anlegen", "erp", "--recht", "opos:lesen"])
    assert r.exit_code == 1 and "--gesellschaft angeben" in r.output
    r = runner.invoke(
        app, ["-g", "b", "token", "anlegen", "erp", "--recht", "opos:lesen"]
    )
    assert r.exit_code == 0, r.output
    # gespeichert in der Systemdatenbank, nicht in der Datenbank der Gesellschaft
    t = lade(u.system, lade_api_tokens)
    assert [(x.name, x.gesellschaft) for x in t] == [("erp", "b")]
    assert lade(u.db["b"], lade_api_tokens) == []
