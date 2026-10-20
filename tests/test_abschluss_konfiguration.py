"""Abschnitte ``abschluss`` und ``kasse`` — Standards je Kontenrahmen."""

import pytest

from accounti.abschluss.konfiguration import lade_abschluss, lade_kasse
from accounti.konfiguration import KonfigurationError


def test_ohne_datei(tmp_path):
    a = lade_abschluss(tmp_path / "fehlt.yaml")
    assert (a.gewinnermittlung, a.ergebnis_konto, a.arap_konto, a.prap_konto) == (
        "euer",
        "0880",
        "0980",
        "0990",
    )
    assert a.verrechnungskonten == ["1360", "1590"]
    assert a.kreditoren == (70000, 99999)
    assert a.lade_kontenrahmen().name == "SKR03"
    assert lade_kasse(tmp_path / "fehlt.yaml").konto == "1000"


def test_skr04_und_eigene_werte(tmp_path):
    datei = tmp_path / "a.yaml"
    datei.write_text(
        "buchhaltung:\n  kontenrahmen: SKR04\n  kreditoren_von: 70000\n"
        "abschluss:\n  gewinnermittlung: bilanz\n  rap_verzicht_bis_gwg: true\n"
        "kasse:\n  konto: '1610'\n",
        encoding="utf-8",
    )
    a = lade_abschluss(datei)
    assert (a.kontenrahmen, a.gewinnermittlung, a.ergebnis_konto, a.arap_konto) == (
        "SKR04",
        "bilanz",
        "2010",
        "1900",
    )
    assert a.rap_verzicht_bis_gwg
    assert a.lade_kontenrahmen().name == "SKR04"
    assert lade_kasse(datei).konto == "1610"


def test_ungueltige_gewinnermittlung(tmp_path):
    datei = tmp_path / "a.yaml"
    datei.write_text("abschluss:\n  gewinnermittlung: gewuerfelt\n", encoding="utf-8")
    with pytest.raises(KonfigurationError, match="abschluss"):
        lade_abschluss(datei)
