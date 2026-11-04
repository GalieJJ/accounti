"""Keine Rückfälle auf ``config/accounti.yaml`` unter einer Registry (Baustein 10c P4a,
Prüfung sicher-1/verhalten-1).

Aufbau wie in docs/betrieb.md: Gesellschaft a hat kein ``konfiguration:`` und nutzt die
globale ``config/accounti.yaml`` (Arbeitsordner, wie im Docker-Abbild), b eine eigene
Datei. Für ``-g b`` steht die globale Datei damit unter den Konfigurationen anderer
Gesellschaften (D5) — ein Lader, der ohne Pfad auf den Standard zurückfällt, scheiterte
dort mit ``EinstellungsquelleFehlt``. ``bank lauf``, ``bank abrufen``, ``fints
freigeben`` und ``aufgaben lauf|pruefen`` lesen deshalb die Einstellungen der gewählten
Gesellschaft und reichen sie durch (FinTS-Provider, Prüflauf ``beleg_fehlt``); im Web
gilt dasselbe für ``POST /api/v1/laeufe/bank`` mit einem FinTS-Konto.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_bankkonten,
    speichere_bankkonto,
    speichere_transaktion,
)
from accounti.models import Bankkonto, Transaktion, TransaktionQuelle
from accounti.models.auth import TokenRecht
from tests.api_hilfe import webwelt
from tests.auth_hilfe import billige_hashes

runner = CliRunner()
FINTS_IBAN = "DE12500105170648489890"


@pytest.fixture(autouse=True)
def _umgebung(monkeypatch):
    for name in (
        "ACCOUNTI_KONFIG",
        "ACCOUNTI_DB",
        "ACCOUNTI_GESELLSCHAFT",
        "ACCOUNTI_SYSTEM_DB",
        "ACCOUNTI_FINTS_PRODUKT_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    billige_hashes(monkeypatch)


def _url(pfad: Path) -> str:
    return f"sqlite:///{pfad.as_posix()}"


def _registry(wurzel: Path, b_yaml: str) -> dict[str, str]:
    """Registry in ``wurzel/config/accounti.yaml``: a ohne ``konfiguration:`` (die
    globale Datei), b mit ``b.yaml``. Liefert die Datenbanken."""
    (wurzel / "config").mkdir()
    db = {k: _url(wurzel / f"{k}.db") for k in ("a", "b", "system")}
    for url in db.values():
        engine, _ = session_factory(url)
        init_db(engine)
        engine.dispose()
    (wurzel / "b.yaml").write_text(b_yaml, encoding="utf-8")
    (wurzel / "config" / "accounti.yaml").write_text(
        "mandant:\n  name: Alpha GmbH\n"
        "pruefung:\n  regeln:\n    umsatz_ohne_beleg:\n      ab_betrag: 0\n"
        "gesellschaften:\n"
        f"  systemdatenbank: '{db['system']}'\n"
        "  eintraege:\n"
        "    a:\n      name: Alpha GmbH\n"
        f"      datenbank: '{db['a']}'\n"
        f"      archiv: '{(wurzel / 'archiv-a').as_posix()}'\n"
        "    b:\n      name: Beta KG\n"
        f"      datenbank: '{db['b']}'\n"
        f"      archiv: '{(wurzel / 'archiv-b').as_posix()}'\n"
        f"      konfiguration: '{(wurzel / 'b.yaml').as_posix()}'\n"
        f"      regeln: '{(wurzel / 'b-regeln.yaml').as_posix()}'\n",
        encoding="utf-8",
    )
    return db


B_YAML = (
    "mandant:\n  name: Beta KG\n"
    "bank:\n  fints:\n    produkt_id: BETA-PRODUKT\n"
    "pruefung:\n  regeln:\n    umsatz_ohne_beleg:\n      ab_betrag: 1000\n"
    # aufgaben lauf: ein Kanal ist Pflicht — gesendet wird nichts (keine Aufgabe, SMTP
    # gesperrt)
    "versand:\n  absender: Beta KG <b@beta.invalid>\n  smtp:\n    host: smtp.invalid\n"
)


def _fints_konto(url: str) -> None:
    """Ein FinTS-Konto ohne Zugang: der Abruf scheitert am Konto, nicht am Lauf."""
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        speichere_bankkonto(
            s,
            Bankkonto(
                iban=FINTS_IBAN,
                bezeichnung="Giro",
                provider="fints",
                einstellungen={"blz": "50010517", "server": "https://fints.example/"},
            ),
        )
        s.commit()
    engine.dispose()


def _umsatz(url: str, betrag: str = "-50.00") -> None:
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        speichere_transaktion(
            s,
            Transaktion(
                datum=date(2026, 3, 2),
                betrag=Decimal(betrag),
                verwendungszweck="Tankstelle",
                gegenkonto_name="SHELL",
                quelle=TransaktionQuelle.BANK,
                rohtext="",
            ),
        )
        s.commit()
    engine.dispose()


def _aufruf(*argumente: str) -> str:
    r = runner.invoke(app, list(argumente), env={"COLUMNS": "250"})
    ausgabe = " ".join(r.output.split())
    assert r.exit_code == 0, ausgabe
    assert "anderen Gesellschaft" not in ausgabe, ausgabe
    return ausgabe


class _KeinSmtp:
    def __init__(self, *_: object, **__: object) -> None:
        raise AssertionError("kein Versand im Test")


@pytest.fixture
def registry(tmp_path, monkeypatch):
    import smtplib

    monkeypatch.setattr(smtplib, "SMTP", _KeinSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _KeinSmtp)
    monkeypatch.chdir(tmp_path)  # config/accounti.yaml ist die globale Datei
    return _registry(tmp_path, B_YAML)


def test_bank_lauf_ohne_konto(registry):
    """Vor dem Fix: Exit 1 schon ohne Bankkonto (``lade_bank_einstellungen()``)."""
    assert "Keine Bankkonten" in _aufruf("-g", "b", "bank", "lauf", "--no-llm")
    assert "Keine Bankkonten" in _aufruf("-g", "a", "bank", "lauf", "--no-llm")


def test_bank_lauf_mit_fints_konto_nimmt_die_einstellungen_von_b(registry):
    """Das Konto meldet seinen Fehler wie vor P4a, der Lauf geht weiter — und der
    Provider sieht die Produkt-ID aus b.yaml (die globale Datei hat keine)."""
    _fints_konto(registry["b"])
    ausgabe = _aufruf("-g", "b", "bank", "lauf", "--no-llm")
    assert FINTS_IBAN in ausgabe and "FinTS-Zugang unvollständig" in ausgabe
    assert "Produkt-ID fehlt" not in ausgabe
    assert "Kontierung:" in ausgabe


def test_bank_abrufen_und_fints_freigeben(registry):
    _fints_konto(registry["b"])
    for befehl in (("bank", "abrufen"), ("fints", "freigeben")):
        ausgabe = _aufruf("-g", "b", *befehl)
        assert "FinTS-Zugang unvollständig" in ausgabe, (befehl, ausgabe)
        assert "Produkt-ID fehlt" not in ausgabe, (befehl, ausgabe)


def test_ohne_registry_bleibt_die_globale_datei(tmp_path, monkeypatch):
    """Ohne Registry nimmt ``bank lauf`` wie bisher die Datei aus ``--config``."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "accounti.yaml").write_text(
        "bank:\n  fints:\n    produkt_id: GLOBAL-PRODUKT\n", encoding="utf-8"
    )
    url = _url(tmp_path / "accounti.db")
    engine, _ = session_factory(url)
    init_db(engine)
    engine.dispose()
    _fints_konto(url)
    ausgabe = _aufruf("bank", "lauf", "--no-llm")
    assert "FinTS-Zugang unvollständig" in ausgabe, ausgabe
    ohne = tmp_path / "ohne.yaml"
    ohne.write_text("mandant:\n  name: Ohne\n", encoding="utf-8")
    ausgabe = _aufruf("bank", "lauf", "--no-llm", "--config", str(ohne))
    assert "Produkt-ID fehlt" in ausgabe, ausgabe
    ausgabe = _aufruf("bank", "abrufen", "--config", str(ohne))
    assert "Produkt-ID fehlt" in ausgabe, ausgabe


@pytest.mark.parametrize("befehl", [("aufgaben", "pruefen"), ("aufgaben", "lauf")])
def test_aufgaben_nehmen_die_pruefeinstellungen_von_b(registry, befehl):
    """``beleg_fehlt`` mit ``pruefung`` aus b.yaml (ab 1000 €): der Umsatz über 50 €
    ist keine Aufgabe; mit der globalen Datei (ab 0 €) wäre er eine."""
    _umsatz(registry["b"])
    ausgabe = _aufruf("-g", "b", *befehl)
    assert "beleg_fehlt: 0 neu" in ausgabe, ausgabe
    _umsatz(registry["a"])
    ausgabe = _aufruf("-g", "a", "aufgaben", "pruefen")
    assert "beleg_fehlt: 1 neu" in ausgabe, ausgabe


def test_rest_banklauf_mit_fints_konto_unter_registry(tmp_path, monkeypatch, caplog):
    """Web (streng gebunden): kein 500 — der Provider bekommt die FinTS-Einstellungen
    der Gesellschaft, statt ``config/accounti.yaml`` des Arbeitsordners zu lesen."""
    monkeypatch.chdir(tmp_path)
    w = webwelt(tmp_path)
    w.umgebung.config["a"].write_text(
        w.umgebung.config["a"].read_text(encoding="utf-8")
        + "bank:\n  fints:\n    produkt_id: ALPHA-PRODUKT\n",
        encoding="utf-8",
    )
    _fints_konto(w.umgebung.db["a"])
    token = w.token("a", TokenRecht.LAEUFE_STARTEN)
    with caplog.at_level(logging.ERROR, logger="accounti"):
        r = w.client().post(
            "/api/v1/laeufe/bank", headers={"Authorization": f"Bearer {token}"}
        )
    assert r.status_code == 200, r.text
    (konto,) = r.json()["konten"]
    assert (konto["iban"], konto["zustand"]) == (FINTS_IBAN, "fehler")
    assert "EinstellungsquelleFehlt" not in caplog.text
    engine, fabrik = session_factory(w.umgebung.db["a"])
    with fabrik() as s:
        (gespeichert,) = lade_bankkonten(s)
    engine.dispose()
    # die Produkt-ID aus a.yaml kam an: es fehlt nur noch der Zugang
    assert "FinTS-Zugang unvollständig" in (gespeichert.meldung or "")
