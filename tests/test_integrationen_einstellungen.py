"""Abschnitt ``integrationen`` der Konfiguration — mit Standardwerten."""

import pytest

from accounti.integrationen.einstellungen import (
    lade_integrationen,
    lade_steuerangaben,
)
from accounti.konfiguration import KonfigurationError


def test_ohne_datei_gelten_standards(tmp_path):
    e = lade_integrationen(tmp_path / "fehlt.yaml")
    assert e.marktplatz("amazon").verrechnungskonto == "1361"
    assert e.marktplatz("ebay").verrechnungskonto == "1362"
    assert e.marktplatz("shopify").verrechnungskonto == "1363"
    assert e.marktplatz("paypal").verrechnungskonto == "1210"
    assert e.marktplatz("amazon").konto_fuer_gebuehr("verkauf") == "4760"
    assert e.marktplatz("paypal").konto_fuer_gebuehr("zahlung") == "4970"
    assert e.geldtransit_konto == "1360"
    assert e.auszahlung_toleranz_tage == 10
    assert e.ermaessigte_artikel == []


def test_ohne_abschnitt(tmp_path):
    pfad = tmp_path / "a.yaml"
    pfad.write_text("mandant:\n  name: X\n", encoding="utf-8")
    assert lade_integrationen(pfad).marktplatz("ebay").verrechnungskonto == "1362"


def test_teilweise_ueberschreiben(tmp_path):
    pfad = tmp_path / "a.yaml"
    pfad.write_text(
        "integrationen:\n"
        "  ermaessigte_artikel: [BUCH-1]\n"
        "  marktplaetze:\n"
        "    amazon:\n"
        "      verrechnungskonto: '1370'\n"
        "      bank_stichworte: [AMAZON, AMZN]\n",
        encoding="utf-8",
    )
    e = lade_integrationen(pfad)
    amazon = e.marktplatz("amazon")
    assert amazon.verrechnungskonto == "1370"
    assert amazon.bank_stichworte == ["AMAZON", "AMZN"]
    assert amazon.einbehalt_konto == "1500"  # Rest bleibt Standard
    assert e.marktplatz("ebay").verrechnungskonto == "1362"
    assert e.ermaessigte_artikel == ["BUCH-1"]


def test_unbekannter_marktplatz(tmp_path):
    with pytest.raises(KeyError):
        lade_integrationen(tmp_path / "x.yaml").marktplatz("otto")


def test_ungueltig(tmp_path):
    pfad = tmp_path / "a.yaml"
    pfad.write_text("integrationen:\n  auszahlung_toleranz_tage: -3\n", "utf-8")
    with pytest.raises(KonfigurationError, match="integrationen"):
        lade_integrationen(pfad)


def test_steuerangaben(tmp_path):
    pfad = tmp_path / "a.yaml"
    assert lade_steuerangaben(pfad) == (False, "DE")
    pfad.write_text(
        "mandant:\n  name: X\n  oss: true\n  anschrift:\n    land: DE\n", "utf-8"
    )
    assert lade_steuerangaben(pfad) == (True, "DE")
