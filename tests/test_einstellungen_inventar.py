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


def _lader(punktname: str) -> Any:
    """Auch eine Methode (``modul.Klasse.methode``)."""
    teile = punktname.split(".")
    for i in range(len(teile) - 1, 0, -1):
        try:
            ziel: Any = importlib.import_module(".".join(teile[:i]))
        except ModuleNotFoundError:
            continue
        for teil in teile[i:]:
            ziel = getattr(ziel, teil)
        return ziel
    raise AssertionError(punktname)


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


def _nimmt_feldnamen(modell: type[BaseModel]) -> bool:
    konfig = modell.model_config
    return bool(konfig.get("populate_by_name") or konfig.get("validate_by_name"))


def _betriebswege(
    praefixe: list[tuple[str, str]], modell: type[BaseModel]
) -> Iterator[tuple[str, str]]:
    """(Pfad mit Datei-Schlüsseln, Pfad, unter dem das Modell den Wert auch nimmt) je
    markiertem Feld — mit dem Feldnamen statt des Alias, wo ein Modell beides annimmt
    (``populate_by_name``), auch auf dem Weg dorthin."""
    for name, feld in modell.model_fields.items():
        datei = feld.alias or name
        schluessel = [datei]
        if feld.alias and feld.alias != name and _nimmt_feldnamen(modell):
            schluessel.append(name)
        wege = [(f"{a}.{datei}", f"{w}.{s}") for a, w in praefixe for s in schluessel]
        if feld.json_schema_extra == BETRIEB:
            yield from wege
            continue
        for zusatz, unter in _modelle(feld.annotation):
            yield from _betriebswege([(a + zusatz, w + zusatz) for a, w in wege], unter)


def _ohne_namensschutz(
    abschnitt: str,
    modell: type[BaseModel],
    namen: dict[str, str],
    betriebsfelder: frozenset[str] = BETRIEBSFELDER,
) -> set[str]:
    """Wege, unter denen das Modell ein Betriebsfeld annimmt, die der Leser aber nicht
    aus einer Version entfernt (weder ``betriebsfelder`` noch ``namen``)."""
    geschuetzt = betriebsfelder | set(namen.values())
    return {
        weg
        for _, weg in _betriebswege([(abschnitt, abschnitt)], modell)
        if weg not in geschuetzt
    }


def test_betriebsfeld_auch_unter_dem_feldnamen_geschuetzt():
    """Prüfung sicher-2: Ein markiertes Feld mit Alias in einem Modell mit
    ``populate_by_name`` nimmt auch den Feldnamen — der steht dann in
    ``BETRIEBSFELD_NAMEN`` (der Leser entfernt beide aus einer Version), sonst schlägt
    der Test an."""
    from pydantic import ConfigDict, Field

    from accounti.einstellungen.inventar import BETRIEBSFELD_NAMEN, Betriebsfeld

    class Probe(BaseModel):
        model_config = ConfigDict(populate_by_name=True)
        datei: Betriebsfeld[str | None] = Field(default=None, alias="pfad")

    class OhneNamen(BaseModel):
        datei: Betriebsfeld[str | None] = Field(default=None, alias="pfad")

    markiert = frozenset({"probe.pfad"})
    assert _ohne_namensschutz("probe", Probe, {}, markiert) == {"probe.datei"}
    namen = {"probe.pfad": "probe.datei"}
    assert _ohne_namensschutz("probe", Probe, namen, markiert) == set()
    assert _ohne_namensschutz("probe", OhneNamen, {}, markiert) == set()
    alle: set[tuple[str, str]] = set()
    for abschnitt, punktname in MODELL.items():
        if abschnitt in BETRIEBSABSCHNITTE:
            continue
        modell = _objekt(punktname)
        assert _ohne_namensschutz(abschnitt, modell, BETRIEBSFELD_NAMEN) == set()
        alle |= set(_betriebswege([(abschnitt, abschnitt)], modell))
    # jeder Eintrag ist ein Weg eines Betriebsfelds (keiner veraltet)
    assert set(BETRIEBSFELD_NAMEN.items()) <= alle
    assert all(datei in BETRIEBSFELDER for datei in BETRIEBSFELD_NAMEN)
    assert BETRIEBSFELD_NAMEN == {"anlagen.rechtsstand": "anlagen.rechtsstand_datei"}


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
        assert callable(_lader(lader)), lader
        assert abschnitte <= set(ABSCHNITTE), lader
    for pfad in (*PERIODENFELDER, *UMZUG, *UMZUG.values()):
        assert pfad.split(".")[0] in ABSCHNITTE, pfad


def test_neue_felder_abwaertskompatibel():
    """AK80/A124: Jede Golden-Konfiguration ergibt mit den neuen Modellen (datev, llm,
    import, einrichtung, einstellungen) die Werte der Datei bzw. die Standards; die
    neuen Felder von mandant haben ihren Standard (den Rest prüft
    ``tests/test_lader_golden.py``)."""
    from accounti.abschluss.konfiguration import TagMonat, lade_datev
    from accounti.einstellungen.einrichtung import (
        EinrichtungEinstellungen,
        lade_einrichtung,
    )
    from accounti.importers.einstellungen import ImportEinstellungen, lade_import
    from accounti.klassifikation.einstellungen import LlmEinstellungen, lade_llm
    from accounti.konfiguration import lade_firma
    from tests.werkzeuge.golden_lader import KONFIGURATIONEN, feste_umgebung

    erwartet_datev = {
        "beispiel": ("12345", "00001", TagMonat(1, 1)),
        "skr04_abweichend": ("54321", "00042", TagMonat(7, 1)),
        "leer": (None, None, None),
        "einzelwerte": ("1234567", "99", TagMonat(4, 1)),
    }
    with feste_umgebung():
        for konfig, pfad in KONFIGURATIONEN.items():
            datev = lade_datev(pfad)
            assert (
                datev.berater_nummer,
                datev.mandanten_nummer,
                datev.wirtschaftsjahr_beginn,
            ) == erwartet_datev[konfig], konfig
            llm = lade_llm(pfad)
            assert llm.auto_buchen_schwelle == 0.95, konfig
            assert llm.model_copy(update={"api_key": None}) == LlmEinstellungen()
            erwartet_import = (
                ImportEinstellungen(standard_bank="sparkasse")
                if konfig == "beispiel"
                else ImportEinstellungen()
            )
            assert lade_import(pfad) == erwartet_import, konfig
            assert lade_einrichtung(pfad) == EinrichtungEinstellungen()
            if konfig != "leer":
                firma = lade_firma(pfad)
                assert (firma.rechtsform, firma.kennfarbe) == (None, None)
                assert firma.sachkonten_laenge == 4


def test_einstellungsquelle_und_einrichtung():
    """Datei-Abschnitt ``einstellungen`` (E2) und Datenbank-Abschnitt ``einrichtung``
    (nur Datenbank, P7) haben ihr Modell."""
    import pytest
    from pydantic import ValidationError

    from accounti.einstellungen.einrichtung import EinrichtungEinstellungen
    from accounti.einstellungen.leser import EinstellungsQuelle

    assert EinstellungsQuelle() == EinstellungsQuelle(quelle="datenbank", festgelegt=[])
    assert EinstellungsQuelle(festgelegt=["elster"]).festgelegt == ["elster"]
    with pytest.raises(ValidationError, match="unbekannter Abschnitt"):
        EinstellungsQuelle(festgelegt=["elstr"])
    with pytest.raises(ValidationError, match="unbekannter Abschnitt"):
        EinstellungsQuelle(festgelegt=["server"])  # Betrieb: ohnehin nur die Datei
    with pytest.raises(ValidationError):
        EinstellungsQuelle(quelle="beides")  # type: ignore[arg-type]
    assert EinrichtungEinstellungen(ausgeblendet=["bank"]).ausgeblendet == ["bank"]
    assert ABSCHNITTE["einrichtung"].ziel == "nur_db"
    for abschnitt in ("datev", "llm", "import", "einrichtung", "einstellungen"):
        assert abschnitt in MODELL, abschnitt
