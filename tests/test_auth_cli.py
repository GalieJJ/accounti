"""Rechte in der CLI: ohne Benutzer wie bisher, mit Benutzern Rolle + Einmalcode."""

from datetime import datetime

import pytest

from accounti.auth.cli import (
    befehlsrecht_oder_ende,
    pruefe_befehlsrecht,
    pruefe_verwaltung,
)
from accounti.auth.fehler import AnmeldungError, RechteError
from accounti.db import init_db, session_factory
from accounti.db.repo_auth import lade_ereignisse
from accounti.models.auth import Recht, Rolle
from tests.auth_hilfe import (
    billige_hashes,
    lege_person_an,
    setze_schluessel,
)


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def schluessel(monkeypatch):
    return setze_schluessel(monkeypatch)


@pytest.fixture
def db(tmp_path, monkeypatch, schluessel):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    monkeypatch.delenv("ACCOUNTI_SYSTEM_DB", raising=False)
    monkeypatch.delenv("ACCOUNTI_EINMALCODE", raising=False)
    url = f"sqlite:///{tmp_path / 'a.db'}"
    engine, fabrik = session_factory(url)
    init_db(engine)
    yield url, fabrik, tmp_path / "accounti.yaml"
    engine.dispose()


def personen(fabrik):
    jetzt = datetime.now()
    with fabrik() as s:
        return {
            "jan": lege_person_an(s, "jan", Rolle.BETRACHTER, jetzt=jetzt),
            "eva": lege_person_an(s, "eva", Rolle.BUCHHALTER, jetzt=jetzt),
            "chef": lege_person_an(s, "chef", Rolle.FREIGEBER, jetzt=jetzt),
            "root": lege_person_an(s, "root", Rolle.VERWALTER, jetzt=jetzt),
        }


def test_ohne_benutzer_keine_pruefung(db):
    url, _, config = db
    assert pruefe_befehlsrecht(url, str(config), Recht.ZAHLUNG_FREIGEBEN, "wer") is None


def test_akzeptanz_3_rollen_in_der_cli(db):
    url, fabrik, config = db
    p = personen(fabrik)
    nie = lambda person: pytest.fail("ohne Recht wird kein Code abgefragt")  # noqa: E731
    with pytest.raises(RechteError, match="jan darf .*Zahlungsläufe freigeben"):
        pruefe_befehlsrecht(url, str(config), Recht.ZAHLUNG_FREIGEBEN, "jan", nie)
    with pytest.raises(RechteError, match="Steuermeldungen freigeben"):
        pruefe_befehlsrecht(url, str(config), Recht.STEUER_FREIGEBEN, "jan", nie)
    with pytest.raises(RechteError, match="eva darf .*Zahlungsläufe freigeben"):
        pruefe_befehlsrecht(url, str(config), Recht.ZAHLUNG_FREIGEBEN, "eva", nie)
    with pytest.raises(RechteError, match="kein aktiver Benutzer"):
        pruefe_befehlsrecht(url, str(config), Recht.ZAHLUNG_FREIGEBEN, "fremd", nie)
    b = pruefe_befehlsrecht(
        url,
        str(config),
        Recht.ZAHLUNG_FREIGEBEN,
        "chef",
        lambda person: p[person].code(datetime.now()),
    )
    assert b.name == "chef"
    with fabrik() as s:
        arten = [(e.art, e.benutzer, e.ok) for e in lade_ereignisse(s)]
    assert ("recht_verweigert", "eva", False) in arten
    assert ("recht_genutzt", "chef", True) in arten


def test_falscher_einmalcode(db):
    url, fabrik, config = db
    personen(fabrik)
    with pytest.raises(AnmeldungError):
        pruefe_befehlsrecht(
            url, str(config), Recht.ZAHLUNG_FREIGEBEN, "chef", lambda _: "000000"
        )


def test_wiederherstellungscode_in_der_cli(db, monkeypatch):
    url, fabrik, config = db
    p = personen(fabrik)
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].codes[0])
    assert pruefe_befehlsrecht(url, str(config), Recht.STEUER_FREIGEBEN, "chef")
    with pytest.raises(AnmeldungError):
        pruefe_befehlsrecht(url, str(config), Recht.STEUER_FREIGEBEN, "chef")


def test_ohne_einmalcode_wenn_abgeschaltet(db):
    url, fabrik, config = db
    personen(fabrik)
    config.write_text("auth:\n  einmalcode_bestaetigung: false\n", encoding="utf-8")
    nie = lambda person: pytest.fail("abgeschaltet")  # noqa: E731
    assert pruefe_befehlsrecht(url, str(config), Recht.ZAHLUNG_FREIGEBEN, "chef", nie)
    with pytest.raises(RechteError):
        pruefe_befehlsrecht(url, str(config), Recht.ZAHLUNG_FREIGEBEN, "eva", nie)


def test_ende_mit_meldung(db, capsys):
    import typer

    url, fabrik, config = db
    personen(fabrik)
    with pytest.raises(typer.Exit):
        befehlsrecht_oder_ende(url, str(config), Recht.ZAHLUNG_FREIGEBEN, "eva")
    assert "eva darf" in capsys.readouterr().err


def test_verwaltung_einrichtungsphase_und_danach(db, monkeypatch):
    url, fabrik, config = db
    jetzt = datetime.now()
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "irgendwer")
    # kein Benutzer: frei
    assert pruefe_verwaltung(url, str(config)) == "irgendwer"
    with fabrik() as s:
        lege_person_an(s, "root", Rolle.VERWALTER, mit_2fa=False, jetzt=jetzt)
    # Verwalter ohne zweiten Faktor: noch Einrichtungsphase
    assert pruefe_verwaltung(url, str(config)) == "irgendwer"
    with fabrik() as s:
        chef = lege_person_an(s, "chef", Rolle.VERWALTER, jetzt=jetzt)
        eva = lege_person_an(s, "eva", Rolle.BUCHHALTER, jetzt=jetzt)
    with pytest.raises(RechteError):
        pruefe_verwaltung(url, str(config))
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "eva")
    with pytest.raises(RechteError):
        pruefe_verwaltung(url, str(config), frage=lambda _: eva.code(jetzt))
    # sich selbst darf man verwalten (mit dem eigenen Code)
    assert (
        pruefe_verwaltung(
            url, str(config), selbst="eva", frage=lambda _: eva.code(datetime.now())
        )
        == "eva"
    )
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "chef")
    assert (
        pruefe_verwaltung(url, str(config), frage=lambda _: chef.code(datetime.now()))
        == "chef"
    )
