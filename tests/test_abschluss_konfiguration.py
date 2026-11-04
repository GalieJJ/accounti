"""Abschnitte ``abschluss`` und ``kasse`` — Standards je Kontenrahmen."""

import pytest

from accounti.abschluss.konfiguration import lade_abschluss, lade_kasse
from accounti.konfiguration import KonfigurationError


def test_ohne_datei(tmp_path):
    a = lade_abschluss(tmp_path / "fehlt.yaml")
    # Periodenwert (Baustein 10c P4): gefragt wird mit dem Wirtschaftsjahr
    gewinnermittlung = a.gewinnermittlung_fuer(2026)
    assert (gewinnermittlung, a.ergebnis_konto, a.arap_konto, a.prap_konto) == (
        "euer",
        "0880",
        "0980",
        "0990",
    )
    # Geldtransit, Durchlaufende Posten, Sonstige Verrechnungskonten (Interimskonten)
    assert a.verrechnungskonten == ["1360", "1590", "1792"]
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
    gewinnermittlung = a.gewinnermittlung_fuer(2026)
    assert (a.kontenrahmen, gewinnermittlung, a.ergebnis_konto, a.arap_konto) == (
        "SKR04",
        "bilanz",
        "2010",
        "1900",
    )
    assert a.rap_verzicht_bis_gwg
    assert a.verrechnungskonten == ["1460", "1370", "3630"]
    assert a.lade_kontenrahmen().name == "SKR04"
    assert lade_kasse(datei).konto == "1610"


def test_ungueltige_gewinnermittlung(tmp_path):
    datei = tmp_path / "a.yaml"
    datei.write_text("abschluss:\n  gewinnermittlung: gewuerfelt\n", encoding="utf-8")
    with pytest.raises(KonfigurationError, match="abschluss"):
        lade_abschluss(datei)


def test_gewinnermittlung_angegeben_mit_zuordnung(tmp_path):
    """M6: Eine Zuordnung je Wirtschaftsjahr — ``gewinnermittlung_angegeben`` fragt mit
    dem WJ (bisher bei einer Zuordnung ``None``)."""
    from accounti.abschluss.konfiguration import gewinnermittlung_angegeben

    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(
        "abschluss:\n  gewinnermittlung: {2026: euer, 2027: bilanz}\n", "utf-8"
    )
    assert gewinnermittlung_angegeben(pfad, 2025) == "euer"
    assert gewinnermittlung_angegeben(pfad, 2026) == "euer"
    assert gewinnermittlung_angegeben(pfad, 2027) == "bilanz"
    einst = lade_abschluss(pfad)
    assert einst.gewinnermittlung_fuer(2026) == "euer"
    assert einst.gewinnermittlung_fuer(2030) == "bilanz"
    pfad.write_text("abschluss:\n  rap_verzicht_bis_gwg: true\n", "utf-8")
    assert gewinnermittlung_angegeben(pfad, 2027) is None
    assert lade_abschluss(pfad).gewinnermittlung_fuer(2027) == "euer"
