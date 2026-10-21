"""Aktive Gesellschaft — für die CLI ein Kontext je Aufruf.

``accounti --gesellschaft K …`` (oder ``ACCOUNTI_GESELLSCHAFT``) wählt eine
Gesellschaft aus der Registry. Der Typer-Callback in ``cli.py`` setzt damit über
``Context.default_map`` die Standardwerte von ``--db``, ``--archiv`` und ``--config``
**jedes** Befehls — die Optionen heißen in allen Befehlen gleich. Ausdrücklich
angegebene Optionen gewinnen. Ohne Gesellschaft gelten ``ACCOUNTI_DB``,
``ACCOUNTI_ARCHIV`` und ``ACCOUNTI_KONFIG``, sonst die bisherigen Standards.

Ist die globale Konfiguration kaputt (YAML-Syntax, Registry), laufen Befehle ohne
Gesellschaft weiter (``version``, ``--db``-Befehle); der Fehler steht im Kontext und
bricht ab, wo eine Gesellschaft oder eine Rechteprüfung gebraucht wird.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from accounti.betrieb.gesellschaften import (
    Gesellschaft,
    Gesellschaften,
    lade_gesellschaften,
)
from accounti.konfiguration import STANDARD_PFAD, KonfigurationError
from accounti.models.auth import STANDARD_GESELLSCHAFT

UMGEBUNG_GESELLSCHAFT = "ACCOUNTI_GESELLSCHAFT"
UMGEBUNG_DB = "ACCOUNTI_DB"
UMGEBUNG_ARCHIV = "ACCOUNTI_ARCHIV"
UMGEBUNG_KONFIG = "ACCOUNTI_KONFIG"
UMGEBUNG_SYSTEM_DB = "ACCOUNTI_SYSTEM_DB"

# Befehlsgruppen, die ohne gewählte Gesellschaft starten dürfen; wer darin doch eine
# braucht, ruft ``gesellschaft_noetig()`` (z.B. ``sicherung erstellen``)
OHNE_GESELLSCHAFT = frozenset(
    {"gesellschaft", "version", "serve", "benutzer", "token", "betrieb", "sicherung"}
)

_PARAMETER = {"db": "datenbank", "archiv": "archiv", "config": "konfiguration"}
STANDARD_REGELN = "config/regeln.yaml"


@dataclass(frozen=True)
class Kontext:
    globale_konfiguration: str
    registry: Gesellschaften
    gesellschaft: Gesellschaft | None = None
    standardwerte: dict[str, str] = field(default_factory=dict)
    # die globale Konfiguration ließ sich nicht lesen — Registry unbekannt
    fehler: str | None = None

    @property
    def kuerzel(self) -> str:
        return self.gesellschaft.kuerzel if self.gesellschaft else STANDARD_GESELLSCHAFT

    def pruefe(self) -> Kontext:
        """``KonfigurationError``, wenn die Registry unbekannt ist (fail-closed)."""
        if self.fehler is not None:
            raise KonfigurationError(self.fehler)
        return self

    @property
    def regeln(self) -> str:
        """Regeldatei der aktiven Gesellschaft, ohne Registry ``config/regeln.yaml``."""
        if self.gesellschaft is not None:
            return self.gesellschaft.regeln
        return STANDARD_REGELN

    def systemdatenbank(self, db: str) -> str:
        """Wo Benutzer und Token liegen; ohne Registry: die Datenbank ``db``."""
        if os.environ.get(UMGEBUNG_SYSTEM_DB):
            return os.environ[UMGEBUNG_SYSTEM_DB]
        if self.registry.eintraege:
            system = self.registry.system()
            if system:
                return system
        return db


_AKTUELL: ContextVar[Kontext | None] = ContextVar("accounti_kontext", default=None)


def globale_konfiguration() -> str:
    return os.environ.get(UMGEBUNG_KONFIG) or str(STANDARD_PFAD)


def aktueller_kontext() -> Kontext:
    """Kontext des laufenden Aufrufs — außerhalb der CLI aus der Umgebung."""
    kontext = _AKTUELL.get()
    if kontext is None:
        pfad = globale_konfiguration()
        kontext = Kontext(pfad, Gesellschaften(quelle=pfad))
    return kontext


def regeln_datei() -> str:
    """Regeldatei für ``classify``, ``bank lauf``, ``lerne`` … im aktuellen Aufruf."""
    return aktueller_kontext().regeln


def gesellschaft_noetig() -> Kontext:
    """Bei mehreren Gesellschaften ohne Wahl ein ``KonfigurationError``."""
    kontext = aktueller_kontext().pruefe()
    if kontext.gesellschaft is None and kontext.registry.mehrere:
        msg = "Mehrere Gesellschaften eingerichtet — --gesellschaft angeben"
        raise KonfigurationError(msg)
    return kontext


def setze_kontext(kontext: Kontext | None) -> Any:
    return _AKTUELL.set(kontext)


def ruecksetzen(token: Any) -> None:
    _AKTUELL.reset(token)


def _umgebungswerte() -> dict[str, str]:
    werte: dict[str, str] = {}
    for parameter, variable in (
        ("db", UMGEBUNG_DB),
        ("archiv", UMGEBUNG_ARCHIV),
        ("config", UMGEBUNG_KONFIG),
    ):
        if os.environ.get(variable):
            werte[parameter] = os.environ[variable]
    return werte


def kontext_ohne_registry(fehler: str) -> Kontext:
    """Die Registry ließ sich nicht lesen: nur Umgebung, Fehler gemerkt."""
    pfad = globale_konfiguration()
    return Kontext(pfad, Gesellschaften(quelle=pfad), None, _umgebungswerte(), fehler)


def bestimme_kontext(gesellschaft: str | None) -> Kontext:
    """Kontext aus Option/Umgebung und Registry — wirft ``KonfigurationError``."""
    pfad = globale_konfiguration()
    registry = lade_gesellschaften(pfad)
    werte = _umgebungswerte()
    kuerzel = gesellschaft or registry.standard
    if kuerzel is None:
        return Kontext(pfad, registry, None, werte)
    if not registry.eintraege:
        msg = (
            f"Keine Gesellschaften eingerichtet — Abschnitt 'gesellschaften' in {pfad} "
            f"(oder {UMGEBUNG_KONFIG})"
        )
        raise KonfigurationError(msg)
    g = registry.finde(kuerzel)
    for parameter, attribut in _PARAMETER.items():
        werte[parameter] = getattr(g, attribut)
    return Kontext(pfad, registry, g, werte)


def standardwerte_fuer(befehl: Any, werte: Mapping[str, str]) -> dict[str, Any]:
    """``default_map`` für eine Befehlsgruppe: an jedem Befehl, der einen der
    Parameter hat, dessen Wert — über alle Ebenen der Gruppen."""
    karte: dict[str, Any] = {}
    unter: Mapping[str, Any] = getattr(befehl, "commands", {}) or {}
    for name, kind in unter.items():
        if getattr(kind, "commands", None):
            tiefer = standardwerte_fuer(kind, werte)
            if tiefer:
                karte[name] = tiefer
            continue
        eigene = {
            p.name: werte[p.name]
            for p in getattr(kind, "params", [])
            if p.name in werte
        }
        if eigene:
            karte[name] = eigene
    return karte


def ohne_passwort(adresse: str) -> str:
    """Datenbankadresse für Anzeigen: das Passwort wird zu ``***``."""
    return re.sub(r"(://[^:/@]+:)[^@]*@", r"\1***@", adresse)
