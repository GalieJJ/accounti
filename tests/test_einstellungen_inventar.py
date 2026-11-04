"""Inventar der Einstellungen (Baustein 10c P4, Schritt 2; Spec Anhang A).

Strukturtests: Jeder Abschnitt der Vorlage ist bekannt; die Markierung
``Betriebsfeld[...]`` an den Modellfeldern und ``BETRIEBSFELDER`` stimmen überein, und
jedes Feld, das nach Pfad aussieht, ist markiert oder mit Grund ausgenommen (D7, N11);
jedes Geheimnis hat genau eine Verbrauchsstelle (D8).
"""

from __future__ import annotations

import importlib
import re
import typing
from collections.abc import Iterator
from pathlib import Path, PurePath
from typing import Any

import yaml
from pydantic import BaseModel

from accounti.einstellungen.inventar import (
    ABSCHNITTE,
    BETRIEB,
    BETRIEBSABSCHNITTE,
    BETRIEBSFELDER,
    GEHEIMFELDER,
    KEIN_BETRIEBSFELD,
    LADER,
    MODELL,
    PERIODENFELDER,
    UMZUG,
)

WURZEL = Path(__file__).resolve().parents[1]
PFADNAME = re.compile(r"datei|pfad|archiv|zuordnung|schema|rechtsstand|ordner")


def _objekt(punktname: str, trenner: str = ".") -> Any:
    modul, _, name = punktname.rpartition(trenner)
    return getattr(importlib.import_module(modul), name)


def _modelle(typ: Any) -> Iterator[tuple[str, type[BaseModel]]]:
    """Untermodelle in einem Feldtyp mit dem Pfadzusatz (``[]`` für Listen)."""
    herkunft = typing.get_origin(typ)
    if herkunft is None:
        if isinstance(typ, type) and issubclass(typ, BaseModel):
            yield "", typ
        return
    argumente = typing.get_args(typ)
    if herkunft is typing.Annotated:
        yield from _modelle(argumente[0])
        return
    for i, argument in enumerate(argumente):
        if herkunft is dict and i == 0:
            continue
        zusatz = "[]" if herkunft in (list, tuple, set, frozenset) else ""
        zusatz = "[]" if herkunft is dict else zusatz
        for weiter, modell in _modelle(argument):
            yield zusatz + weiter, modell


def _ist_pfadtyp(typ: Any) -> bool:
    if isinstance(typ, type) and issubclass(typ, PurePath):
        return True
    return any(_ist_pfadtyp(a) for a in typing.get_args(typ))


def _felder(praefix: str, modell: type[BaseModel]) -> Iterator[tuple[str, Any, bool]]:
    """(Pfad mit Datei-Schlüsseln, Typ, markiert) je Feld, Untermodelle eingeschlossen —
    unter einem markierten Feld nicht weiter (es deckt den Teilbaum)."""
    for name, feld in modell.model_fields.items():
        pfad = f"{praefix}.{feld.alias or name}"
        markiert = feld.json_schema_extra == BETRIEB
        yield pfad, feld.annotation, markiert
        if markiert:
            continue
        for zusatz, unter in _modelle(feld.annotation):
            yield from _felder(pfad + zusatz, unter)


def _alle_felder() -> list[tuple[str, Any, bool]]:
    from accounti.belege.kanaele.connector import BELEG_CONNECTOREN

    felder = []
    for abschnitt, punktname in MODELL.items():
        if abschnitt in BETRIEBSABSCHNITTE:
            continue  # ganz Betrieb — ohne Markierung je Feld
        felder += list(_felder(abschnitt, _objekt(punktname)))
    for typ, klasse in BELEG_CONNECTOREN.items():
        felder += list(
            _felder(f"belegkanaele.connectoren[{typ}]", klasse.Einstellungen)
        )
    return felder


def test_jeder_abschnitt_der_vorlage_ist_bekannt():
    vorlage = yaml.safe_load(
        (WURZEL / "config" / "accounti.example.yaml").read_text(encoding="utf-8")
    )
    unbekannt = set(vorlage) - set(ABSCHNITTE)
    assert unbekannt == set()
    assert {"database", "server", "auth", "gesellschaften", "einstellungen"} == (
        BETRIEBSABSCHNITTE
    )
    assert ABSCHNITTE["einrichtung"].ziel == "nur_db"
    assert ABSCHNITTE["mandant"].unvollstaendig_erlaubt == {"missing", "pflicht_fehlt"}


def test_betriebsfelder_markiert_und_gelistet():
    felder = _alle_felder()
    markiert = {pfad for pfad, _, m in felder if m}
    assert markiert == BETRIEBSFELDER
    verdaechtig = {
        pfad
        for pfad, typ, m in felder
        if not m
        and (PFADNAME.search(pfad.rsplit(".", 1)[-1]) or _ist_pfadtyp(typ))
        and not any(pfad.startswith(f"{b}.") for b in BETRIEBSFELDER)
    }
    assert verdaechtig == set(KEIN_BETRIEBSFELD)
    assert all(grund.strip() for grund in KEIN_BETRIEBSFELD.values())


def test_betriebsfelder_liegen_in_datenbank_abschnitten():
    for pfad in BETRIEBSFELDER:
        assert ABSCHNITTE[pfad.split(".")[0]].ziel == "db", pfad


def test_geheimfelder_haben_eine_verbrauchsstelle():
    assert set(GEHEIMFELDER) == {
        "versand.smtp.passwort",
        "llm.api_key",
        "aufgaben.benachrichtigung.webhook.url",
        "elster.pin",
    }
    stellen = [g.verbrauch for g in GEHEIMFELDER.values()]
    assert len(set(stellen)) == len(stellen)  # je Geheimnis eine eigene Stelle
    for name, geheim in GEHEIMFELDER.items():
        assert callable(_objekt(geheim.verbrauch, ":")), name
    pruefe = GEHEIMFELDER["aufgaben.benachrichtigung.webhook.url"].pruefe
    assert pruefe("https://chat.example/hook") is None
    assert pruefe("chat.example/hook") is not None
    assert GEHEIMFELDER["llm.api_key"].pruefe("  ") is not None


def test_modelle_und_lader_sind_aufloesbar():
    for abschnitt, punktname in MODELL.items():
        assert issubclass(_objekt(punktname), BaseModel), abschnitt
    for lader, abschnitte in LADER.items():
        assert callable(_objekt(lader)), lader
        assert abschnitte <= set(ABSCHNITTE), lader
    for pfad in (*PERIODENFELDER, *UMZUG, *UMZUG.values()):
        assert pfad.split(".")[0] in ABSCHNITTE, pfad
