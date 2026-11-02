"""Lädt Kontierungsregeln aus der Regeldatei der Gesellschaft (``config/regeln.yaml``).

accounti schreibt die Datei nicht (mehr): gelernte Regeln liegen in der Datenbank
(``klassifikation.lernen``) und haben Vorrang, die Datei pflegt der Betreiber.

Felder je Regel: ``name``, ``muster``, ``soll_konto``, ``haben_konto``, optional
``steuer_schluessel``, ``buchungstext``, ``feld`` (verwendungszweck,
gegenkonto_name, gegenkonto_iban, beide), ``richtung`` (ausgabe, einnahme, beide),
``pruefen`` (Treffer immer zur Prüfung) und ``confidence`` (0–1, Standard 1).

Jeder Wert wird geprüft (Gesamttest 10b-1, Runde 3): Konten sind 4 bis 8 Ziffern —
eine Zahl mit führender Null (``0420``) bleibt Text (YAML 1.1 läse sie sonst als
Oktalzahl: 272), ein leeres Konto ist ein Fehler (sonst „None“); das Muster ist ein
nicht leerer Text (ein leeres Muster träfe jeden Umsatz), der Steuerschlüssel eine Zahl.
Ein Fehler ist ein ``KonfigurationError`` mit Datei und Regelname.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from accounti.buchung.konten import KontoError, pruefe_kontonummer
from accounti.klassifikation.engine import Regel
from accounti.konfiguration import KonfigurationError

# Textfelder des Umsatzes, auf die ein Muster passen kann (``gegenkonto_iban``: vor
# Gesamttest 10b-1 N-2 wirksam, gw2-merge B1)
FELDER = ("verwendungszweck", "gegenkonto_name", "gegenkonto_iban", "beide")
_FUEHRENDE_NULL = re.compile(r"[-+]?0[0-9_]+")


class _Lader(yaml.SafeLoader):
    """SafeLoader ohne Oktalzahlen: ``0420`` bleibt der Text „0420“."""


def _ganzzahl(lader: yaml.SafeLoader, knoten: yaml.ScalarNode) -> object:
    if _FUEHRENDE_NULL.fullmatch(knoten.value):
        return knoten.value
    return yaml.SafeLoader.construct_yaml_int(lader, knoten)


_Lader.add_constructor("tag:yaml.org,2002:int", _ganzzahl)


def lies_regeldatei(pfad: str | Path) -> list[Any]:
    """Die Einträge der Datei (keine Datei: keine). ``KonfigurationError``, wenn sie
    nicht lesbar ist (Verzeichnis, nicht UTF-8), kein YAML oder keine Liste."""
    pfad = Path(pfad)
    if not pfad.exists():
        return []
    try:
        text = pfad.read_text(encoding="utf-8")
    except UnicodeDecodeError as fehler:
        msg = f"{pfad}: keine UTF-8-Datei ({fehler.reason} an Stelle {fehler.start})"
        raise KonfigurationError(msg) from fehler
    except OSError as fehler:
        raise KonfigurationError(f"{pfad}: nicht lesbar — {fehler}") from fehler
    try:
        daten = yaml.load(text, Loader=_Lader) or []  # noqa: S506 — SafeLoader
    except yaml.YAMLError as fehler:
        raise KonfigurationError(f"{pfad}: kein gültiges YAML — {fehler}") from fehler
    if not isinstance(daten, list):
        msg = f"{pfad}: keine Liste von Regeln (- name: …, muster: …)"
        raise KonfigurationError(msg)
    return daten


def _text(eintrag: dict[str, Any], feld: str, name: str) -> str | None:
    wert = eintrag.get(feld)
    if wert is None or isinstance(wert, str):
        return wert or None
    if isinstance(wert, (int, float)) and not isinstance(wert, bool):
        return str(wert)
    raise ValueError(f"Regel {name}: {feld} {wert!r} — ein Text erwartet")


def _confidence(eintrag: dict[str, Any], name: str) -> float:
    wert = eintrag.get("confidence", 1.0)
    try:
        if isinstance(wert, bool) or not isinstance(wert, (int, float, str)):
            raise ValueError
        return float(wert)
    except ValueError:
        msg = f"Regel {name}: confidence {wert!r} — eine Zahl von 0 bis 1"
        raise ValueError(msg) from None


def _konto(eintrag: dict[str, Any], feld: str, name: str) -> str:
    if feld not in eintrag:
        raise KeyError(feld)
    wert = "" if eintrag[feld] is None else eintrag[feld]
    if isinstance(wert, bool) or not isinstance(wert, (int, str)):
        raise ValueError(f"Regel {name}: {feld} {wert!r} ist keine Kontonummer")
    try:
        return pruefe_kontonummer(str(wert), f"Regel {name}: {feld}")
    except KontoError as fehler:
        hinweis = (
            " — Kontonummern in Anführungszeichen schreiben ('0420')"
            if isinstance(wert, int)
            else ""
        )
        raise ValueError(f"{fehler}{hinweis}") from fehler


def _schluessel(eintrag: dict[str, Any], name: str) -> int | None:
    wert = eintrag.get("steuer_schluessel")
    if wert is None:
        return None
    if isinstance(wert, str) and wert.strip().isascii() and wert.strip().isdigit():
        return int(wert.strip())
    if isinstance(wert, bool) or not isinstance(wert, int):
        msg = f"Regel {name}: steuer_schluessel {wert!r} — eine Zahl (z. B. 9)"
        raise ValueError(msg)
    return wert


def pruefe_eintrag(eintrag: Any, pfad: str | Path) -> Regel:
    """Ein Eintrag der Regeldatei als ``Regel`` — sonst ``KonfigurationError`` mit
    Datei und Regelname (auch für ``regeln uebernehmen``)."""
    if not isinstance(eintrag, dict):
        raise KonfigurationError(f"{pfad}: Regel {eintrag!r} ist keine Zuordnung")
    name = str(eintrag.get("name") or "?")
    try:
        if not eintrag.get("name"):
            raise KeyError("name")
        if "muster" not in eintrag:
            raise KeyError("muster")
        muster = eintrag["muster"]
        if not isinstance(muster, str) or not muster.strip():
            raise ValueError(
                f"Regel {name}: muster {muster!r} — ein nicht leerer Text (ein leeres "
                "Muster träfe jeden Umsatz)"
            )
        pruefen = eintrag.get("pruefen", False)
        if not isinstance(pruefen, bool):
            raise ValueError(f"Regel {name}: pruefen {pruefen!r} — true oder false")
        feld = eintrag.get("feld", "verwendungszweck")
        if feld not in FELDER:
            raise ValueError(f"Regel {name}: feld {feld!r} — {', '.join(FELDER)}")
        return Regel(
            name=name,
            muster=muster,
            soll_konto=_konto(eintrag, "soll_konto", name),
            haben_konto=_konto(eintrag, "haben_konto", name),
            steuer_schluessel=_schluessel(eintrag, name),
            buchungstext=_text(eintrag, "buchungstext", name),
            feld=feld,
            richtung=eintrag.get("richtung"),
            pruefen=pruefen,
            confidence=_confidence(eintrag, name),
        )
    except KeyError as fehler:
        msg = f"{pfad}: Regel {name}: Feld {fehler.args[0]} fehlt"
        raise KonfigurationError(msg) from fehler
    except re.error as fehler:
        msg = (
            f"{pfad}: Regel {name}: Muster ist kein gültiger regulärer Ausdruck: "
            f"{fehler}"
        )
        raise KonfigurationError(msg) from fehler
    except (TypeError, ValueError) as fehler:
        raise KonfigurationError(f"{pfad}: {fehler}") from fehler


def lade_regeln(pfad: str | Path) -> list[Regel]:
    """Regeln der Datei (keine Datei: keine Regeln). Eine fehlerhafte Datei — nicht
    lesbar, kein YAML, keine Liste, ein ungültiger Wert (``pruefe_eintrag``) — meldet
    ``KonfigurationError`` mit Datei und Regelname: CLI und Oberfläche zeigen dann
    eine Meldung statt eines Tracebacks bzw. 500 (Gesamttest 10b-1 nach dem Merge,
    gw-regeln N-2; Runde 3)."""
    return [pruefe_eintrag(eintrag, pfad) for eintrag in lies_regeldatei(pfad)]
