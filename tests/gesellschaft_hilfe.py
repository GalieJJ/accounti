"""Zwei eigene Gesellschaften mit getrennten Daten — für CLI-, Web- und API-Tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from accounti.db import init_db, session_factory
from tests.zahlung_hilfe import kreditor, posten, speichere


@dataclass
class Umgebung:
    wurzel: Path
    registry: Path
    system: str
    db: dict[str, str]
    archiv: dict[str, Path]
    config: dict[str, Path]


def _url(pfad: Path) -> str:
    return f"sqlite:///{pfad.as_posix()}"


def zwei_gesellschaften(tmp_path: Path, standard: str | None = None) -> Umgebung:
    """A: Kreditor „Alpha Papier GmbH“ (SKR03), B: „Beta Rahmen KG“ (SKR04)."""
    db = {k: _url(tmp_path / f"{k}.db") for k in ("a", "b")}
    archiv = {k: tmp_path / f"archiv-{k}" for k in ("a", "b")}
    config = {k: tmp_path / f"{k}.yaml" for k in ("a", "b")}
    daten = {
        "a": ("Alpha Papier GmbH", "70001", "A-RE-1", "111.00", "SKR03"),
        "b": ("Beta Rahmen KG", "70009", "B-RE-7", "777.00", "SKR04"),
    }
    for k, (name, konto, nummer, betrag, rahmen) in daten.items():
        engine, fabrik = session_factory(db[k])
        init_db(engine)
        kontakt = kreditor(name, konto)
        speichere(
            fabrik,
            [kontakt],
            [posten(kontakt, nummer, betrag, faellig=date(2026, 11, 1))],
        )
        engine.dispose()
        config[k].write_text(
            f"mandant:\n  name: {name}\n  kontenrahmen: {rahmen}\n"
            f"buchhaltung:\n  kontenrahmen: {rahmen}\n"
            f"datev:\n  wirtschaftsjahr_beginn: '2026-0{1 if k == 'a' else 7}-01'\n"
            f"zahlung:\n  auftraggeber:\n    name: {name}\n"
            "    iban: DE12500105170648489890\n    bic: COBADEFFXXX\n",
            encoding="utf-8",
        )
    system = _url(tmp_path / "system.db")
    registry = tmp_path / "accounti.yaml"
    registry.write_text(
        "gesellschaften:\n"
        f"  systemdatenbank: '{system}'\n"
        + (f"  standard: {standard}\n" if standard else "")
        + "  eintraege:\n"
        + "".join(
            f"    {k}:\n"
            f"      name: {daten[k][0]}\n"
            f"      datenbank: '{db[k]}'\n"
            f"      archiv: '{archiv[k].as_posix()}'\n"
            f"      konfiguration: '{config[k].as_posix()}'\n"
            f"      regeln: '{(tmp_path / f'{k}-regeln.yaml').as_posix()}'\n"
            for k in ("a", "b")
        ),
        encoding="utf-8",
    )
    return Umgebung(tmp_path, registry, system, db, archiv, config)


def zahlungslauf(u: Umgebung, kuerzel: str) -> None:
    """Zahlungslauf 1 im Entwurf über den Posten der Gesellschaft (wie per CLI)."""
    from typer.testing import CliRunner

    from accounti.cli import app

    befehl = ["zahlung", "anlegen", "--db", u.db[kuerzel]]
    befehl += ["--config", str(u.config[kuerzel]), "--stichtag", "2026-12-01"]
    r = CliRunner().invoke(app, [*befehl, "--von", "eva"])
    assert r.exit_code == 0, r.output
