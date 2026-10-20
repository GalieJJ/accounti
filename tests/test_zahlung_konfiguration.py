from decimal import Decimal

import pytest

from accounti.konfiguration import KonfigurationError
from accounti.zahlung.konfiguration import lade_zahlung


def test_ohne_datei_und_abschnitt_gelten_standards(tmp_path):
    e = lade_zahlung(tmp_path / "fehlt.yaml")
    assert e.vorlauf_tage == 3
    assert e.skonto_ziehen is True
    assert e.vier_augen is False
    assert e.einzelbuchung is True
    assert e.hoechstbetrag_zahlung is None
    assert e.auftraggeber.iban is None

    leer = tmp_path / "leer.yaml"
    leer.write_text("buchhaltung: {}\n", encoding="utf-8")
    assert lade_zahlung(leer).vorlauf_tage == 3


def test_auftraggeber_aus_mandant(tmp_path):
    pfad = tmp_path / "a.yaml"
    pfad.write_text(
        "mandant:\n"
        "  name: Galerie Muster GmbH\n"
        "  bank: {iban: 'DE89 3704 0044 0532 0130 00', bic: COBADEFFXXX}\n"
        "zahlung:\n"
        "  vorlauf_tage: 5\n"
        "  vier_augen: true\n"
        "  hoechstbetrag_zahlung: 25000\n",
        encoding="utf-8",
    )
    e = lade_zahlung(pfad)
    assert e.vorlauf_tage == 5 and e.vier_augen is True
    assert e.hoechstbetrag_zahlung == Decimal("25000")
    assert e.auftraggeber.name == "Galerie Muster GmbH"
    assert e.auftraggeber.iban == "DE89370400440532013000"
    assert e.auftraggeber.bic == "COBADEFFXXX"


def test_eigener_auftraggeber_geht_vor(tmp_path):
    pfad = tmp_path / "a.yaml"
    pfad.write_text(
        "mandant: {name: Firma, bank: {iban: DE89370400440532013000}}\n"
        "zahlung:\n"
        "  auftraggeber: {name: Zweitfirma, iban: DE02120300000000202051}\n",
        encoding="utf-8",
    )
    e = lade_zahlung(pfad)
    assert e.auftraggeber.name == "Zweitfirma"
    assert e.auftraggeber.iban == "DE02120300000000202051"
    assert e.auftraggeber.bic is None


def test_ungueltige_werte_mit_klarer_meldung(tmp_path):
    pfad = tmp_path / "a.yaml"
    pfad.write_text("zahlung: {vorlauf_tage: -1}\n", encoding="utf-8")
    with pytest.raises(KonfigurationError, match="zahlung.*vorlauf_tage"):
        lade_zahlung(pfad)
    pfad.write_text(
        "zahlung: {auftraggeber: {iban: DE00123456780000000000}}\n", encoding="utf-8"
    )
    with pytest.raises(KonfigurationError, match="Prüfziffer"):
        lade_zahlung(pfad)
