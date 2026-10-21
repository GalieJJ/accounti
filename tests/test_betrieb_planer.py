"""Geplanter Lauf: bank lauf und aufgaben lauf je Gesellschaft."""

import logging
import subprocess
import threading
from pathlib import Path

import accounti
from accounti.betrieb.gesellschaften import Gesellschaften, lade_gesellschaften
from accounti.betrieb.kontext import Kontext
from accounti.betrieb.planer import einmal, schleife, schritte
from tests.gesellschaft_hilfe import zwei_gesellschaften


def kontext_ohne_registry():
    return Kontext("fehlt.yaml", Gesellschaften())


def test_schritte_ohne_und_mit_registry(tmp_path):
    assert schritte(kontext_ohne_registry()) == [["bank", "lauf"], ["aufgaben", "lauf"]]
    u = zwei_gesellschaften(tmp_path)
    k = Kontext(str(u.registry), lade_gesellschaften(u.registry))
    assert schritte(k) == [
        ["--gesellschaft", "a", "bank", "lauf"],
        ["--gesellschaft", "a", "aufgaben", "lauf"],
        ["--gesellschaft", "b", "bank", "lauf"],
        ["--gesellschaft", "b", "aufgaben", "lauf"],
    ]


def test_ein_fehler_haelt_die_anderen_nicht_auf(caplog):
    aufrufe = []

    def ausfuehren(argumente):
        aufrufe.append(list(argumente))
        code = 1 if argumente[0] == "bank" else 0
        return subprocess.CompletedProcess(
            argumente, code, "IBAN DE89370400440532013000", ""
        )

    with caplog.at_level(logging.DEBUG, logger="accounti.lauf"):
        ergebnisse = einmal(kontext_ohne_registry(), ausfuehren)
    assert [e.code for e in ergebnisse] == [1, 0]
    assert len(aufrufe) == 2
    assert "bank lauf → 1" in caplog.text
    assert "370400440532013000" not in caplog.text  # Ausgabe nur geschwärzt


def test_schleife_endet_auf_signal():
    halt = threading.Event()
    runden = []

    def ausfuehren(argumente):
        runden.append(argumente)
        if len(runden) >= 4:
            halt.set()
        return subprocess.CompletedProcess(argumente, 0, "", "")

    assert schleife(kontext_ohne_registry(), 0.0001, ausfuehren, halt) == 2


def test_echter_einmaliger_lauf(tmp_path, monkeypatch):
    """Ein echter Prozess je Schritt gegen eine leere Datenbank."""
    konfig = tmp_path / "accounti.yaml"
    # ohne Benachrichtigungskanal endet `aufgaben lauf` mit 1 (Baustein 8)
    konfig.write_text(
        "aufgaben:\n  benachrichtigung:\n    kanaele: [webhook]\n"
        "    webhook: {url: 'http://127.0.0.1:9/nie'}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(konfig))
    monkeypatch.setenv("ACCOUNTI_DB", f"sqlite:///{tmp_path / 'a.db'}")
    # der Kindprozess soll diesen Quelltext laden, nicht ein installiertes accounti
    monkeypatch.setenv("PYTHONPATH", str(Path(accounti.__file__).parents[1]))
    monkeypatch.chdir(tmp_path)
    ergebnisse = einmal(kontext_ohne_registry())
    assert [e.code for e in ergebnisse] == [0, 0], ergebnisse
    assert (tmp_path / "a.db").exists()
