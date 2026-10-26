"""Befunde der gegnerischen Prüfung (Baustein 10a): Freigaben in der CLI an die
tatsächlich benutzte Datenbank, Konfiguration und Systemdatenbank gebunden.

- A-H2: Rechte werden in der Gesellschaft geprüft, deren Datenbank benutzt wird.
- B-H1: ``auth``-Werte aus frei wählbarem ``--config`` schwächen nichts ab; eine leere
  oder falsche Systemdatenbank schaltet die Prüfung nicht ab (Merker in der
  Gesellschafts-Datenbank, fail-closed).
- A-M6/B-M5: wer einen Benutzer verwaltet, ist Verwalter überall, wo dieser Rollen hat.
"""

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from accounti.auth import totp
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.models.auth import Rolle, TokenRecht
from tests import test_cli_zahlung as zahlung
from tests.auth_hilfe import (
    PASSWORT,
    billige_hashes,
    lege_person_an,
    setze_schluessel,
)
from tests.gesellschaft_hilfe import zahlungslauf, zwei_gesellschaften

runner = CliRunner()


@pytest.fixture(autouse=True)
def _umgebung(monkeypatch, tmp_path):
    billige_hashes(monkeypatch)
    setze_schluessel(monkeypatch)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in (
        "ACCOUNTI_DB",
        "ACCOUNTI_ARCHIV",
        "ACCOUNTI_GESELLSCHAFT",
        "ACCOUNTI_EINMALCODE",
        "ACCOUNTI_SYSTEM_DB",
        "ACCOUNTI_BENUTZER",
    ):
        monkeypatch.delenv(name, raising=False)


def run(*args, input=None):
    return runner.invoke(app, list(args), input=input, env={"COLUMNS": "250"})


def personen_in(url: str, *eintraege: tuple[str, str, Rolle]) -> dict:
    engine, fabrik = session_factory(url)
    init_db(engine)
    jetzt = datetime.now()
    with fabrik() as s:
        p = {
            name: lege_person_an(s, name, rolle, gesellschaft=g, jetzt=jetzt)
            for name, g, rolle in eintraege
        }
    engine.dispose()
    return p


def lauf_status(db: str) -> str:
    from accounti.db.repo_zahlung import lade_lauf

    engine, fabrik = session_factory(db)
    with fabrik() as s:
        status = lade_lauf(s, 1).status.value
    engine.dispose()
    return status


# ---------------------------------------------------------------------------
# A-H2: Gesellschaft der Rechteprüfung = Gesellschaft der Datenbank
# ---------------------------------------------------------------------------


@pytest.fixture
def registry(tmp_path, monkeypatch):
    u = zwei_gesellschaften(tmp_path)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    monkeypatch.setenv("ACCOUNTI_GESELLSCHAFT", "a")
    zahlungslauf(u, "a")
    monkeypatch.delenv("ACCOUNTI_GESELLSCHAFT")
    return u


def test_freigeber_von_b_gibt_den_lauf_von_a_nicht_frei(registry, monkeypatch):
    u = registry
    p = personen_in(
        u.system, ("chef", "a", Rolle.VERWALTER), ("bob", "b", Rolle.FREIGEBER)
    )
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["bob"].code(datetime.now()))
    r = run(
        "-g", "b", "zahlung", "freigeben", "1", "--db", u.db["a"],
        "--config", str(u.config["a"]), "--von", "bob",
    )  # fmt: skip
    assert r.exit_code == 1, r.output
    assert "Gesellschaft b" in r.output
    assert lauf_status(u.db["a"]) == "entwurf"
    # nur --db abweichend genügt auch nicht
    r = run("-g", "b", "zahlung", "freigeben", "1", "--db", u.db["a"], "--von", "bob")
    assert r.exit_code == 1 and lauf_status(u.db["a"]) == "entwurf"
    # in a selbst hat bob keine Rolle
    r = run("-g", "a", "zahlung", "freigeben", "1", "--von", "bob")
    assert r.exit_code == 1 and "bob darf in der Gesellschaft a nicht" in r.output


def test_fremde_registry_mit_vertauschter_datenbank_wird_abgewiesen(
    registry, monkeypatch, tmp_path
):
    """Eigene ``ACCOUNTI_KONFIG``: „b“ zeigt auf die Datenbank von a."""
    u = registry
    p = personen_in(
        u.system, ("chef", "a", Rolle.VERWALTER), ("bob", "b", Rolle.FREIGEBER)
    )
    # eine echte Prüfung in a merkt sich in a.db, wem die Datenbank gehört
    r = run("-g", "a", "zahlung", "freigeben", "1", "--von", "bob")
    assert r.exit_code == 1
    falsch = tmp_path / "falsch.yaml"
    falsch.write_text(
        u.registry.read_text(encoding="utf-8")
        .replace(u.db["b"], "__A__")
        .replace(u.db["a"], u.db["b"])
        .replace("__A__", u.db["a"])
        .replace(str(u.config["b"].as_posix()), "__CB__")
        .replace(str(u.config["a"].as_posix()), str(u.config["b"].as_posix()))
        .replace("__CB__", str(u.config["a"].as_posix())),
        encoding="utf-8",
    )
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(falsch))
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["bob"].code(datetime.now()))
    r = run("-g", "b", "zahlung", "freigeben", "1", "--von", "bob")
    assert r.exit_code == 1, r.output
    assert "gehört zur Gesellschaft a" in r.output
    assert lauf_status(u.db["a"]) == "entwurf"


# ---------------------------------------------------------------------------
# B-H1: frei wählbare Konfiguration und Systemdatenbank
# ---------------------------------------------------------------------------


@pytest.fixture
def einzeln(tmp_path):
    url, config = zahlung._umgebung(tmp_path)
    basis = ["--db", url, "--config", config]
    r = run("zahlung", "anlegen", *basis, "--von", "eva")
    assert r.exit_code == 0, r.output
    p = personen_in(
        url,
        ("eva", "standard", Rolle.BUCHHALTER),
        ("chef", "standard", Rolle.FREIGEBER),
    )
    return url, Path(config), p


def test_eigene_konfiguration_schaltet_den_einmalcode_nicht_ab(einzeln, tmp_path):
    url, config, _ = einzeln
    eigene = tmp_path / "eigene.yaml"
    eigene.write_text(
        config.read_text(encoding="utf-8")
        + "\nauth:\n  einmalcode_bestaetigung: false\n"
        + "  sperre_nach_fehlversuchen: 100\n",
        encoding="utf-8",
    )
    r = run(
        "zahlung", "freigeben", "1", "--db", url, "--config", str(eigene),
        "--von", "chef", input="000000\n",
    )  # fmt: skip
    assert r.exit_code == 1, r.output
    assert "Einmalcode für chef" in r.output and "Einmalcode falsch" in r.output
    assert lauf_status(url) == "entwurf"


def test_leere_systemdatenbank_schaltet_die_pruefung_nicht_ab(
    einzeln, tmp_path, monkeypatch
):
    url, config, _ = einzeln
    # Benutzer liegen in der Datenbank selbst (ohne Registry) — eine andere,
    # leere Systemdatenbank darf nicht „keine Benutzer“ bedeuten
    monkeypatch.setenv("ACCOUNTI_SYSTEM_DB", f"sqlite:///{tmp_path / 'leer.db'}")
    r = run("zahlung", "freigeben", "1", "--db", url, "--config", str(config))
    assert r.exit_code == 1, r.output
    assert "Systemdatenbank" in r.output
    assert lauf_status(url) == "entwurf"


def test_merker_nach_einer_pruefung_haelt_auch_ohne_eigene_benutzer(
    registry, monkeypatch, tmp_path
):
    """Mit Registry liegen die Benutzer nicht in a.db — der Merker hält fest, zu
    welcher Systemdatenbank a gehört (auch bei Tippfehler in ACCOUNTI_SYSTEM_DB)."""
    u = registry
    p = personen_in(u.system, ("chef", "a", Rolle.FREIGEBER))
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", "000000")
    r = run("-g", "a", "zahlung", "freigeben", "1", "--von", "chef")
    assert r.exit_code == 1  # falscher Code — der Merker steht trotzdem
    monkeypatch.setenv("ACCOUNTI_SYSTEM_DB", f"sqlite:///{tmp_path / 'tippfehler.db'}")
    r = run("-g", "a", "zahlung", "freigeben", "1", "--von", "eva")
    assert r.exit_code == 1, r.output
    assert "Systemdatenbank" in r.output
    assert lauf_status(u.db["a"]) == "entwurf"
    monkeypatch.delenv("ACCOUNTI_SYSTEM_DB")
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].code(datetime.now()))
    r = run("-g", "a", "zahlung", "freigeben", "1", "--von", "chef")
    assert r.exit_code == 0, r.output


def test_benutzer_anlegen_bindet_die_gesellschaften(registry, monkeypatch, tmp_path):
    """Schon der erste Verwalter bindet die Datenbanken der Registry."""
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "chef")
    pw = "ein langer geheimer Satz"
    r = run(
        "-g", "a", "benutzer", "anlegen", "chef", "--rolle", "verwalter",
        "--rolle", "freigeber", input=f"{pw}\n{pw}\n",
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    leer = f"sqlite:///{tmp_path / 'leer.db'}"
    monkeypatch.setenv("ACCOUNTI_SYSTEM_DB", leer)
    for k in ("a", "b"):
        r = run("-g", k, "zahlung", "freigeben", "1", "--von", "irgendwer")
        assert r.exit_code == 1, (k, r.output)
        assert "Systemdatenbank" in r.output
    # in der leeren Systemdatenbank lässt sich zwar jemand anlegen, die
    # Gesellschaft aber nicht an sie binden
    r = run(
        "-g", "a", "benutzer", "anlegen", "fremd", "--rolle", "verwalter",
        "--rolle", "freigeber", input=f"{pw}\n{pw}\n",
    )  # fmt: skip
    assert r.exit_code == 1, r.output
    assert "Systemdatenbank" in r.output


def test_ohne_benutzer_bleibt_alles_wie_bisher(tmp_path):
    url, config = zahlung._umgebung(tmp_path)
    basis = ["--db", url, "--config", config]
    assert run("zahlung", "anlegen", *basis, "--von", "eva").exit_code == 0
    r = run("zahlung", "freigeben", "1", *basis, "--von", "jan")
    assert r.exit_code == 0, r.output


# ---------------------------------------------------------------------------
# A-M6/B-M5: Verwaltung über Gesellschaftsgrenzen
# ---------------------------------------------------------------------------


@pytest.fixture
def verwalter(registry, monkeypatch):
    u = registry
    p = personen_in(
        u.system,
        ("chef", "a", Rolle.VERWALTER),
        ("tina", "b", Rolle.VERWALTER),
        ("eva", "b", Rolle.BUCHHALTER),
    )
    engine, fabrik = session_factory(u.system)
    from accounti.auth.dienst import fuege_rolle_hinzu

    with fabrik() as s:
        fuege_rolle_hinzu(s, p["chef"].benutzer, "a", Rolle.FREIGEBER, None, "t")
        fuege_rolle_hinzu(s, p["chef"].benutzer, "b", Rolle.VERWALTER, None, "t")
        s.commit()
    engine.dispose()
    codes = {name: list(person.codes) for name, person in p.items()}

    def als(name: str) -> None:
        monkeypatch.setenv("ACCOUNTI_BENUTZER", name)
        monkeypatch.setenv("ACCOUNTI_EINMALCODE", codes[name].pop())

    return u, p, als


@pytest.mark.parametrize(
    "befehl",
    [
        ["benutzer", "2fa", "chef"],
        ["benutzer", "codes", "chef"],
        ["benutzer", "passwort", "chef"],
        ["benutzer", "sperren", "chef"],
        ["benutzer", "entsperren", "chef"],
        ["benutzer", "rolle", "chef", "--rolle", "betrachter"],
    ],
)
def test_verwalter_von_b_uebernimmt_kein_konto_mit_rollen_in_a(verwalter, befehl):
    u, p, als = verwalter
    als("tina")
    neu = "voellig neues Passwort 42"
    r = run("-g", "b", *befehl, input=f"{neu}\n{neu}\n000000\n")
    assert r.exit_code == 1, r.output
    assert "Verwalter in a" in r.output
    engine, fabrik = session_factory(u.system)
    from accounti.auth import passwort as pw
    from accounti.db.repo_auth import lade_benutzer

    with fabrik() as s:
        chef = lade_benutzer(s, "chef")
    engine.dispose()
    assert chef.aktiv and pw.pruefe_passwort(PASSWORT, chef.passwort_hash)


def test_verwalter_beider_gesellschaften_darf(verwalter):
    _, p, als = verwalter
    als("chef")
    r = run("-g", "b", "benutzer", "rolle", "eva", "--rolle", "betrachter")
    assert r.exit_code == 0, r.output
    als("tina")  # eva hat nur Rollen in b
    r = run("-g", "b", "benutzer", "sperren", "eva")
    assert r.exit_code == 0, r.output


def test_token_nur_in_der_eigenen_gesellschaft(verwalter):
    from accounti.auth.token import lege_api_token_an

    u, _, als = verwalter
    engine, fabrik = session_factory(u.system)
    with fabrik() as s:
        lege_api_token_an(s, "erp-a", "a", [TokenRecht.OPOS_LESEN], "chef")
        lege_api_token_an(s, "erp-b", "b", [TokenRecht.OPOS_LESEN], "tina")
        s.commit()
    engine.dispose()
    als("tina")
    r = run("-g", "b", "token", "liste")
    assert r.exit_code == 0, r.output
    assert "erp-b" in r.output and "erp-a" not in r.output
    als("tina")
    r = run("-g", "b", "token", "widerrufen", "erp-a")
    assert r.exit_code == 1, r.output
    # Namen gelten je Gesellschaft (Gesamttest Betrieb B9): in b gibt es kein
    # „erp-a“ — die Meldung verrät nicht mehr, dass a eines hat
    assert "kein aktives Token 'erp-a' in b" in r.output
    assert "Gesellschaft a" not in r.output
    als("tina")
    r = run("-g", "b", "token", "widerrufen", "erp-b")
    assert r.exit_code == 0, r.output


# ---------------------------------------------------------------------------
# Verwaltung mit Gesellschaft, die es nicht gibt / Selbstverwaltung bleibt
# ---------------------------------------------------------------------------


def test_eigenes_konto_bleibt_selbst_verwaltbar(verwalter, monkeypatch):
    _, p, als = verwalter
    als("eva")
    geheim = b"\x02" * 20
    monkeypatch.setattr(totp, "neues_geheimnis", lambda: geheim)
    r = run(
        "-g", "b", "benutzer", "2fa", "eva",
        input=totp.code(geheim, datetime.now().timestamp()) + "\n",
    )  # fmt: skip
    assert r.exit_code == 0, r.output
