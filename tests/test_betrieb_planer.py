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


def test_fehlermeldung_eines_schritts_steht_im_protokoll(caplog):
    """g4w N6 (Runde 5): Im geplanten Lauf stand nur „bank lauf → 1 (5 s)“ — der
    Grund (z. B. ein Fehler in der Regeldatei) nur auf DEBUG. Jetzt die letzten
    Zeilen der Ausgabe auf WARNING, geschwärzt; ein erfolgreicher Schritt bleibt
    ohne Ausgabe."""
    meldung = (
        "config/regeln.yaml: Regel telekom: unbekannter Schlüssel kommentar — "
        "erlaubt sind name, muster"
    )

    def ausfuehren(argumente):
        if argumente[0] == "bank":
            return subprocess.CompletedProcess(
                argumente, 1, "Abruf DE89370400440532013000 …\n" + meldung + "\n", ""
            )
        return subprocess.CompletedProcess(argumente, 0, "alles gut\n", "")

    with caplog.at_level(logging.INFO, logger="accounti.lauf"):
        einmal(kontext_ohne_registry(), ausfuehren)
    warnungen = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    (zeile,) = warnungen
    assert zeile.startswith("bank lauf → 1") and meldung in zeile
    assert "370400440532013000" not in caplog.text  # geschwärzt
    assert "alles gut" not in caplog.text


def test_zugangsdaten_der_webhook_adresse_nicht_in_der_warnung(caplog):
    """g5w-konten N1 (Runde 6): Rich bricht die Meldung nach 80 Zeichen hart um — der
    Grund verband die Zeilen erst danach, das URL-Muster verlangte „:geheim@“ ohne
    Leerraum. 63 von 97 Zeichen eines Tokens standen auf WARNING."""
    token = "github_pat_11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyzABCDEF0123456789"
    ausgabe = (
        "gemeinsam: webhook fehlgeschlagen — KanalError: Webhook https://accounti:"
        f"{token[:50]}\n{token[50:]}@hooks.example.invalid/… nicht zustellbar\n"
    )

    def ausfuehren(argumente):
        return subprocess.CompletedProcess(argumente, 1, ausgabe, "")

    with caplog.at_level(logging.INFO, logger="accounti.lauf"):
        einmal(kontext_ohne_registry(), ausfuehren)
    for teil in (token[:20], token[20:40], token[40:60], token[60:]):
        assert teil not in caplog.text, teil
    assert "nicht zustellbar" in caplog.text


def test_zeitlimit_steht_im_protokoll(caplog):
    def ausfuehren(argumente):
        raise subprocess.TimeoutExpired(argumente, 3600)

    with caplog.at_level(logging.INFO, logger="accounti.lauf"):
        einmal(kontext_ohne_registry(), ausfuehren)
    assert "Zeitlimit" in caplog.text


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


def test_rahmen_und_ueberbreite_zeilen_nicht_im_protokoll(caplog):
    """g6w B-1 (Runde 7): Mit COLUMNS=10000 wurde ein Rich-Traceback 10 000 Zeichen
    breit — das DEBUG-Protokoll 64-mal so groß, die WARNUNG voller Rahmenzeichen. Jetzt
    ohne Rahmen, jede Zeile begrenzt; der Grund steht vollständig und geschwärzt in der
    WARNUNG."""
    rahmen = "╭" + "─" * 9990 + "╮"
    ausgabe = "\n".join(
        [
            rahmen,
            "│ /pfad/datei.py:12 in lauf" + " " * 9960 + "│",
            "╰" + "─" * 9990 + "╯",
            "OperationalError: unable to open database file (DE89370400440532013000)",
        ]
    )

    def ausfuehren(argumente):
        return subprocess.CompletedProcess(argumente, 1, "", ausgabe)

    with caplog.at_level(logging.DEBUG, logger="accounti.lauf"):
        einmal(kontext_ohne_registry(), ausfuehren)
    warnungen = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnungen) == 2  # bank lauf, aufgaben lauf
    for warnung in warnungen:
        assert "unable to open database file" in warnung and "[IBAN]" in warnung
    assert not set("─│╭╮╰╯") & set(caplog.text)
    assert max(len(r.getMessage()) for r in caplog.records) <= 1000
    assert len(caplog.text) < 6000


def test_schritt_ohne_rich_traceback(monkeypatch):
    """Der Schritt läuft mit dem Traceback von Python (Typer: TYPER_STANDARD_TRACEBACK,
    ältere Fassungen _TYPER_STANDARD_TRACEBACK) — ohne Rahmen in Terminalbreite."""
    from accounti.betrieb import planer

    gesehen = {}

    def run(befehl, **kw):
        gesehen.update(kw["env"])
        return subprocess.CompletedProcess(befehl, 0, "", "")

    monkeypatch.setattr(planer.subprocess, "run", run)
    planer._starte(["bank", "lauf"])
    assert gesehen["TYPER_STANDARD_TRACEBACK"] == "1"
    assert gesehen["_TYPER_STANDARD_TRACEBACK"] == "1"
    assert gesehen["COLUMNS"] == planer.AUSGABE_BREITE


def test_echter_traceback_eines_schritts(tmp_path, monkeypatch, caplog):
    """planer_db_fehlt.py: Datenbankdatei in einem fehlenden Ordner — der Grund steht
    in der WARNUNG, ohne Rahmen; DEBUG bleibt klein."""
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text('mandant:\n  name: "Galerie Muster GmbH"\n', encoding="utf-8")
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(konfig))
    monkeypatch.setenv("ACCOUNTI_DB", f"sqlite:///{tmp_path / 'fehlt' / 'a.db'}")
    monkeypatch.setenv("PYTHONPATH", str(Path(accounti.__file__).parents[1]))
    monkeypatch.delenv("COLUMNS", raising=False)
    monkeypatch.chdir(tmp_path)
    from accounti.betrieb import planer

    monkeypatch.setattr(planer, "BEFEHLE", [["bank", "lauf"]])
    with caplog.at_level(logging.DEBUG, logger="accounti.lauf"):
        (ergebnis,) = einmal(kontext_ohne_registry())
    assert ergebnis.code != 0
    (warnung,) = [
        r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
    ]
    assert "unable to open database file" in warnung, warnung
    assert "─" not in caplog.text and "│" not in caplog.text
    assert len(caplog.text) < 60_000
