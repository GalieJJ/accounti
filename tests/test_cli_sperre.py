"""Nachprüfung Runde 2 (R2-M1 = NEU-M1): Die Kontosperre darf keine Waffe sein.

- Aus dem Netz (Browser-Anmeldung) lässt sich ein Konto sperren — auch bis zum
  Entsperren —, aber nie die Server-Shell: CLI-Versuche zählen getrennt, und mit
  gültigem zweitem Faktor entsperrt sich jeder dort selbst.
- Eine präparierte Konfiguration (``--config``/``ACCOUNTI_KONFIG``) setzt keine
  Sperrwerte: die CLI zählt immer mit den Standardwerten.
- Gesperrte Verwalter zählen weiter als Verwalter — die Einrichtungsphase lässt
  sich nicht aus dem Netz auslösen.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from accounti.auth.dienst import pruefe_anmeldung
from accounti.auth.fehler import AnmeldungError
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repo_auth import DAUERHAFT, lade_benutzer
from accounti.models.auth import Rolle
from tests import test_cli_zahlung as zahlung
from tests.auth_hilfe import (
    PASSWORT,
    SCHLUESSEL,
    billige_hashes,
    einstellungen,
    lege_person_an,
    setze_schluessel,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def _umgebung(monkeypatch, tmp_path):
    billige_hashes(monkeypatch)
    setze_schluessel(monkeypatch)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in (
        "ACCOUNTI_DB",
        "ACCOUNTI_GESELLSCHAFT",
        "ACCOUNTI_EINMALCODE",
        "ACCOUNTI_SYSTEM_DB",
        "ACCOUNTI_BENUTZER",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def welt(tmp_path):
    """Zahlungslauf 1 (von eva angelegt, ohne Benutzer), dann chef (Verwalter und
    Freigeber) und eva (Buchhalterin) — chef ist der einzige Verwalter."""
    url, config = zahlung._umgebung(tmp_path)
    r = runner.invoke(
        app, ["zahlung", "anlegen", "--db", url, "--config", config, "--von", "eva"]
    )
    assert r.exit_code == 0, r.output
    engine, fabrik = session_factory(url)
    init_db(engine)
    jetzt = datetime.now()
    with fabrik() as s:
        personen = {
            "chef": lege_person_an(
                s, "chef", Rolle.VERWALTER, Rolle.FREIGEBER, jetzt=jetzt
            ),
            "eva": lege_person_an(s, "eva", Rolle.BUCHHALTER, jetzt=jetzt),
        }
    engine.dispose()
    return url, config, fabrik, personen


def netzflut(fabrik, name: str, runden: int = 20) -> None:
    """Fehlversuche über die Browser-Anmeldung (nur den Namen kennt der Angreifer),
    je fünf und dann die Sperre abwarten — bis zur Obergrenze von 100."""
    # die letzte Runde endet gerade eben — ihre Sperre läuft noch
    t = datetime.now() - timedelta(minutes=16 * (runden - 1) + 1)
    with fabrik() as s:
        for _ in range(runden):
            for _ in range(5):
                with pytest.raises(AnmeldungError):
                    pruefe_anmeldung(
                        s, name, "geraten geraten", "000000", SCHLUESSEL,
                        einstellungen(), jetzt=t,
                    )  # fmt: skip
            t += timedelta(minutes=16)


def lade(fabrik, name):
    with fabrik() as s:
        return lade_benutzer(s, name)


def test_netzflut_sperrt_die_server_shell_nicht(welt, monkeypatch):
    url, config, fabrik, p = welt
    netzflut(fabrik, "chef")
    chef = lade(fabrik, "chef")
    assert chef.fehlversuche == 100 and chef.gesperrt_bis == DAUERHAFT
    # im Browser kommt chef nicht mehr hinein …
    with fabrik() as s, pytest.raises(AnmeldungError):
        pruefe_anmeldung(
            s, "chef", PASSWORT, p["chef"].codes[0], SCHLUESSEL, einstellungen()
        )
    # … auf der Server-Shell gibt er mit seinem Code frei und entsperrt sich selbst
    basis = ["--db", url, "--config", config]
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].codes.pop())
    r = runner.invoke(app, ["zahlung", "freigeben", "1", *basis, "--von", "chef"])
    assert r.exit_code == 0, r.output
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "chef")
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].codes.pop())
    r = runner.invoke(app, ["benutzer", "entsperren", "chef", *basis])
    assert r.exit_code == 0, r.output
    chef = lade(fabrik, "chef")
    assert chef.fehlversuche == 0 and chef.gesperrt_bis is None
    with fabrik() as s:
        assert pruefe_anmeldung(
            s, "chef", PASSWORT, p["chef"].codes.pop(), SCHLUESSEL, einstellungen()
        )


def test_jeder_entsperrt_sich_selbst_mit_dem_zweiten_faktor(welt, monkeypatch):
    url, config, fabrik, p = welt
    netzflut(fabrik, "eva", runden=1)
    assert lade(fabrik, "eva").gesperrt(datetime.now())
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "eva")
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", "000000")
    r = runner.invoke(app, ["benutzer", "entsperren", "eva", "--db", url])
    assert r.exit_code == 1  # ohne gültigen Code nicht
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = runner.invoke(app, ["benutzer", "entsperren", "eva", "--db", url])
    assert r.exit_code == 0, r.output
    assert not lade(fabrik, "eva").gesperrt(datetime.now())


def test_selbst_entsperren_aktiviert_kein_gesperrtes_konto(welt, monkeypatch):
    """``benutzer sperren`` (Verwalter) hebt nur ein Verwalter auf."""
    from accounti.auth.dienst import setze_aktiv

    url, _, fabrik, p = welt
    with fabrik() as s:
        setze_aktiv(s, lade_benutzer(s, "eva"), False, None, "chef")
        s.commit()
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "eva")
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = runner.invoke(app, ["benutzer", "entsperren", "eva", "--db", url])
    assert r.exit_code == 1, r.output
    assert not lade(fabrik, "eva").aktiv


def test_gesperrter_verwalter_oeffnet_keine_einrichtungsphase(welt, monkeypatch):
    url, _, fabrik, _ = welt
    netzflut(fabrik, "chef")
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "fremd")
    pw = "ein langer geheimer Satz"
    r = runner.invoke(
        app,
        ["benutzer", "anlegen", "fremd", "--rolle", "verwalter", "--db", url],
        input=f"{pw}\n{pw}\n",
    )
    assert r.exit_code == 1, r.output
    assert lade(fabrik, "fremd") is None


@pytest.mark.parametrize(
    "auth",
    [
        "fehlversuche_obergrenze: 1\n  sperre_nach_fehlversuchen: 1",
        "sperre_nach_fehlversuchen: 1\n  sperre_minuten: 1440",
        "sperre_nach_fehlversuchen: 1\n  sperre_minuten: 1000000000",
    ],
)
def test_praeparierte_konfiguration_setzt_keine_sperrwerte(welt, monkeypatch, auth):
    """Ein Aufruf mit eigener Datei und falschem Code sperrte chef bisher dauerhaft."""
    url, config, fabrik, p = welt
    boese = Path(config).with_name("boese.yaml")
    boese.write_text(
        Path(config).read_text(encoding="utf-8") + f"\nauth:\n  {auth}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", "000000")
    r = runner.invoke(
        app,
        ["zahlung", "freigeben", "1", "--db", url, "--config", str(boese)]
        + ["--von", "chef"],
    )
    assert r.exit_code == 1
    chef = lade(fabrik, "chef")
    assert not chef.gesperrt(datetime.now())
    assert not chef.cli_gesperrt(datetime.now())
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].codes.pop())
    r = runner.invoke(
        app,
        ["zahlung", "freigeben", "1", "--db", url, "--config", config]
        + ["--von", "chef"],
    )
    assert r.exit_code == 0, r.output


def test_sperre_minuten_hat_eine_obergrenze():
    from pydantic import ValidationError

    from accounti.auth.einstellungen import AuthEinstellungen

    with pytest.raises(ValidationError):
        AuthEinstellungen(sperre_minuten=1_000_000_000)
    assert AuthEinstellungen(sperre_minuten=24 * 60).sperre_minuten == 1440


def test_selbst_entsperren_eines_stillgelegten_kontos_meldet_das_ehrlich(
    welt, monkeypatch
):
    """Runde 3 (N-R3-1): chef legt sich als einziger Verwalter selbst still — in der
    Einrichtungsphase meldete ``entsperren chef`` durch chef „entsperrt“ (Exit 0),
    das Konto blieb aber stillgelegt."""
    from accounti.auth.dienst import setze_aktiv

    url, _, fabrik, _ = welt
    with fabrik() as s:
        setze_aktiv(s, lade_benutzer(s, "chef"), False, None, "chef")
        s.commit()
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "chef")
    r = runner.invoke(app, ["benutzer", "entsperren", "chef", "--db", url])
    assert r.exit_code == 1, r.output
    assert "stillgelegt" in r.output and "entsperrt." not in r.output
    assert not lade(fabrik, "chef").aktiv


def test_verwalter_hebt_auch_die_cli_sperre_auf(welt, monkeypatch):
    """Runde 3 (N-R3-6): 100 falsche Codes auf der Shell sperren chefs CLI bis zum
    Entsperren — ein anderer Verwalter hebt beide Sperren auf."""
    from sqlalchemy import update

    from accounti.db.tabellen_auth import BenutzerRow

    url, config, fabrik, p = welt
    with fabrik() as s:
        anna = lege_person_an(s, "anna", Rolle.VERWALTER, jetzt=datetime.now())
        s.execute(
            update(BenutzerRow)
            .where(BenutzerRow.name == "chef")
            .values(
                cli_fehlversuche=100,
                cli_gesperrt_bis=DAUERHAFT,
                fehlversuche=100,
                gesperrt_bis=DAUERHAFT,
            )
        )
        s.commit()
    assert lade(fabrik, "chef").cli_gesperrt(datetime.now())
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "anna")
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", anna.codes.pop())
    r = runner.invoke(app, ["benutzer", "entsperren", "chef", "--db", url])
    assert r.exit_code == 0, r.output
    chef = lade(fabrik, "chef")
    assert (chef.cli_fehlversuche, chef.cli_gesperrt_bis) == (0, None)
    assert (chef.fehlversuche, chef.gesperrt_bis) == (0, None)
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].codes.pop())
    r = runner.invoke(
        app,
        ["zahlung", "freigeben", "1", "--db", url, "--config", config]
        + ["--von", "chef"],
    )
    assert r.exit_code == 0, r.output
