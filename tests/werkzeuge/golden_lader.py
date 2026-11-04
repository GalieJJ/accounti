"""Golden-Daten der Lader (Plan 10c P4, D20) — Schutz für den Umbau auf den
Abschnittsleser.

Jeder Lader aus ``GOLDEN_LADER`` läuft auf jeder Konfiguration aus ``KONFIGURATIONEN``;
``serialisiere`` macht aus dem Ergebnis JSON (Modell → ``model_dump(mode="json",
by_alias=True)``, Dataclass → Felder, Datum → ISO-Text, Fehler → Klasse und Meldung),
Pfade der Konfiguration werden zu ``<pfad>``/``<ordner>``. Die Daten unter
``tests/daten/lader_golden/<konfig>.json`` sind **einmal auf dem Code vor P4**
erzeugt und eingecheckt; ``tests/test_lader_golden.py`` vergleicht damit.

Neu erzeugen nur, wenn ``main`` Lader oder Konfiguration ändert — dann aus ``main``
ohne P4 in einem eigenen Worktree, und der Unterschied steht im PR (Plan, Schritt 0)::

    PYTHONPATH=src python -m tests.werkzeuge.golden_lader
"""

from __future__ import annotations

import dataclasses
import enum
import json
import os
import re
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from accounti.abschluss.konfiguration import (
    gewinnermittlung_angegeben,
    lade_abschluss,
    lade_kasse,
    lade_wirtschaftsjahr_beginn,
)
from accounti.anlagen.konfiguration import lade_anlagen
from accounti.api.einstellungen import lade_server
from accounti.aufgaben.einstellungen import lade_aufgaben_einstellungen
from accounti.auth.einstellungen import lade_auth
from accounti.bank.einstellungen import lade_bank_einstellungen
from accounti.belege.kanaele.einstellungen import lade_belegkanaele
from accounti.betrieb.gesellschaften import lade_gesellschaften
from accounti.elster.konfiguration import (
    lade_elster,
    lade_elster_konten,
    lade_mandant,
    lade_oss,
)
from accounti.erechnung.versand import lade_versand
from accounti.export.datev_stammdaten import lade_datev_mandant, sachkontenlaenge
from accounti.integrationen.einstellungen import (
    lade_integrationen,
    lade_kontext,
    lade_steuerangaben,
)
from accounti.konfiguration import (
    lade_buchhaltung,
    lade_eigene_firma,
    lade_firma,
    lade_ustid_pruefung,
)
from accounti.mahnwesen.konfiguration import lade_mahnwesen
from accounti.pruefung.einstellungen import lade_pruefung
from accounti.zahlung.konfiguration import lade_zahlung

WURZEL = Path(__file__).resolve().parents[2]
DATEN = WURZEL / "tests" / "daten" / "lader_golden"
KONFIGURATIONEN = {
    "beispiel": WURZEL / "config" / "accounti.example.yaml",
    "skr04_abweichend": DATEN / "skr04_abweichend.yaml",
    "leer": DATEN / "leer.yaml",
    "einzelwerte": DATEN / "einzelwerte.yaml",
}
# Stichtag für den DATEV-Kopf (Wirtschaftsjahr, in dem er liegt)
STICHTAG = date(2026, 3, 31)

# Jeder Lader, der die Konfiguration der Gesellschaft liest, mit seiner Signatur
# (``lade_oss`` und ``gewinnermittlung_angegeben`` bekommen in Schritt 6 den
# Zeitraum). ``pruefung.storno.lade_korrekturumgebung`` fehlt: Sie setzt sich aus
# lade_abschluss, lade_buchhaltung, lade_pruefung und lade_elster_konten zusammen und
# trüge sonst die mitgelieferte Kontenzuordnung (Daten, keine Konfiguration) mit.
GOLDEN_LADER: dict[str, Callable[[Path], Any]] = {
    "lade_firma": lade_firma,
    "lade_buchhaltung": lade_buchhaltung,
    "lade_ustid_pruefung": lade_ustid_pruefung,
    "lade_eigene_firma": lade_eigene_firma,
    "lade_abschluss": lade_abschluss,
    "lade_kasse": lade_kasse,
    "lade_wirtschaftsjahr_beginn": lade_wirtschaftsjahr_beginn,
    "gewinnermittlung_angegeben": gewinnermittlung_angegeben,
    "lade_anlagen": lade_anlagen,
    "lade_server": lade_server,
    "lade_aufgaben_einstellungen": lade_aufgaben_einstellungen,
    "lade_auth": lade_auth,
    "lade_bank_einstellungen": lade_bank_einstellungen,
    "lade_belegkanaele": lade_belegkanaele,
    "lade_gesellschaften": lade_gesellschaften,
    "lade_elster": lade_elster,
    "lade_elster_konten": lade_elster_konten,
    "lade_oss": lade_oss,
    "lade_mandant": lade_mandant,
    "lade_versand": lade_versand,
    "sachkontenlaenge": sachkontenlaenge,
    "lade_datev_mandant": lambda pfad: lade_datev_mandant(pfad, STICHTAG),
    "lade_integrationen": lade_integrationen,
    "lade_steuerangaben": lade_steuerangaben,
    "lade_kontext": lade_kontext,
    "lade_mahnwesen": lade_mahnwesen,
    "lade_pruefung": lade_pruefung,
    "lade_zahlung": lade_zahlung,
}

# Umgebung beim Erzeugen und Vergleichen: Platzhalter der Konfigurationen fest belegt,
# Variablen, die Lader sonst einmischen, entfernt
UMGEBUNG = {
    "ACCOUNTI_SMTP_PASSWORT": "golden-smtp-passwort",
    "ACCOUNTI_IMAP_PASSWORT": "golden-imap-passwort",
    "ACCOUNTI_FINTS_PRODUKT_ID": "GOLDENPRODUKT",
    "ANTHROPIC_API_KEY": "golden-llm-schluessel",
}
OHNE = ("ACCOUNTI_EVATR_URL", "ACCOUNTI_AUFGABEN_WEBHOOK", "ACCOUNTI_SYSTEM_DB")
_PYDANTIC_HINWEIS = re.compile(r"\n?\s*For further information visit \S+")


@contextmanager
def feste_umgebung() -> Iterator[None]:
    """``UMGEBUNG`` gesetzt, ``OHNE`` entfernt — danach wie vorher."""
    namen = (*UMGEBUNG, *OHNE)
    alt = {name: os.environ.get(name) for name in namen}
    try:
        for name in OHNE:
            os.environ.pop(name, None)
        os.environ.update(UMGEBUNG)
        yield
    finally:
        for name, wert in alt.items():
            if wert is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = wert


def serialisiere(wert: Any) -> Any:
    """Ergebnis eines Laders als JSON-Wert; ein unbekannter Typ ist ein
    ``TypeError`` (``test_serialisierer_kennt_jeden_rueckgabetyp``)."""
    if isinstance(wert, BaseException):
        text = _PYDANTIC_HINWEIS.sub("", str(wert))
        return {"fehler": type(wert).__name__, "text": text}
    if isinstance(wert, BaseModel):
        return serialisiere(wert.model_dump(mode="json", by_alias=True))
    if dataclasses.is_dataclass(wert) and not isinstance(wert, type):
        return {
            f.name: serialisiere(getattr(wert, f.name))
            for f in dataclasses.fields(wert)
        }
    if wert is None or isinstance(wert, bool | int | float | str):
        return wert
    if isinstance(wert, datetime | date):
        return wert.isoformat()
    if isinstance(wert, Decimal):
        return str(wert)
    if isinstance(wert, enum.Enum):
        return serialisiere(wert.value)
    if isinstance(wert, Path):
        return str(wert)
    if isinstance(wert, dict):
        return {str(k): serialisiere(v) for k, v in wert.items()}
    if isinstance(wert, list | tuple):
        return [serialisiere(v) for v in wert]
    if isinstance(wert, set | frozenset):
        return sorted(serialisiere(v) for v in wert)
    msg = f"kein Golden-Wert für {type(wert).__name__}"
    raise TypeError(msg)


def ohne_pfad(wert: Any, pfad: Path) -> Any:
    """Pfad und Ordner der Konfiguration als ``<pfad>``/``<ordner>``."""
    if isinstance(wert, str):
        return wert.replace(str(pfad), "<pfad>").replace(str(pfad.parent), "<ordner>")
    if isinstance(wert, dict):
        return {k: ohne_pfad(v, pfad) for k, v in wert.items()}
    if isinstance(wert, list):
        return [ohne_pfad(v, pfad) for v in wert]
    return wert


def roh(lader: str, pfad: Path) -> Any:
    """Ergebnis oder Fehler eines Laders — ohne Serialisierung."""
    try:
        return GOLDEN_LADER[lader](pfad)
    except Exception as fehler:  # noqa: BLE001 — der Fehler ist das Ergebnis
        return fehler


def lauf(lader: str, pfad: Path) -> Any:
    """Ein Lader auf einer Konfiguration, serialisiert (in ``feste_umgebung``)."""
    return ohne_pfad(serialisiere(roh(lader, pfad)), pfad)


def erzeuge(konfig: str) -> dict[str, Any]:
    pfad = KONFIGURATIONEN[konfig]
    with feste_umgebung():
        return {name: lauf(name, pfad) for name in sorted(GOLDEN_LADER)}


def golden_datei(konfig: str) -> Path:
    return DATEN / f"{konfig}.json"


def main() -> None:
    for konfig in KONFIGURATIONEN:
        text = json.dumps(erzeuge(konfig), ensure_ascii=False, indent=2, sort_keys=True)
        golden_datei(konfig).write_text(text + "\n", encoding="utf-8")
        sys.stdout.write(f"{golden_datei(konfig).relative_to(WURZEL)}\n")


if __name__ == "__main__":
    main()
