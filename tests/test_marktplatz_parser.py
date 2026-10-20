"""Gemeinsame Bausteine der Marktplatz-Importer: Beträge, Daten, Länder, Tabellen."""

from datetime import date
from decimal import Decimal

import pytest

from accounti.importers.marktplatz import (
    MarktplatzFormatError,
    dekodiere,
    erkenne_dezimal,
    land_iso,
    lies_betrag,
    lies_datum,
    lies_laenderdatei,
    lies_tabelle,
)


@pytest.mark.parametrize(
    ("text", "dezimal", "erwartet"),
    [
        ("119,00", ",", "119.00"),
        ("-1.234,56", ",", "-1234.56"),
        ("1,234.56", ".", "1234.56"),
        ("-12.5", ".", "-12.5"),
        ("€ 3,10", ",", "3.10"),
        ("1 234,00", ",", "1234.00"),
        ("−7,00", ",", "-7.00"),  # typografisches Minus
        ("(4,50)", ",", "-4.50"),
        ("0", ",", "0"),
    ],
)
def test_betrag(text, dezimal, erwartet):
    assert lies_betrag(text, dezimal) == Decimal(erwartet)


def test_betrag_ohne_zahl_ist_formatfehler():
    with pytest.raises(MarktplatzFormatError):
        lies_betrag("abc", ",")


def test_leerer_betrag_ist_null():
    assert lies_betrag("", ",") == Decimal("0")


def test_dezimal_erkennen():
    assert erkenne_dezimal(["119,00", "-3,50"]) == ","
    assert erkenne_dezimal(["119.00", "1,234.50"]) == "."
    assert erkenne_dezimal(["", "12"]) == ","  # Vorgabe: deutsch


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("01.08.2026", date(2026, 8, 1)),
        ("01.08.2026 08:00:00 UTC", date(2026, 8, 1)),
        ("2026-08-01", date(2026, 8, 1)),
        ("2026-08-01 11:26:40 -0400", date(2026, 8, 1)),
        ("2026-08-01T11:26:40+00:00", date(2026, 8, 1)),
        ("Aug 1, 2026", date(2026, 8, 1)),
        ("1. Aug. 2026", date(2026, 8, 1)),
        ("01.08.26", date(2026, 8, 1)),
    ],
)
def test_datum(text, erwartet):
    assert lies_datum(text) == erwartet


def test_datum_unlesbar():
    with pytest.raises(MarktplatzFormatError):
        lies_datum("irgendwann")


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("DE", "DE"),
        ("fr", "FR"),
        ("Deutschland", "DE"),
        ("Frankreich", "FR"),
        ("Italy", "IT"),
        ("Österreich", "AT"),
        ("Schweiz", "CH"),
        ("United States", "US"),
        ("Vereinigtes Königreich", "GB"),
        ("Griechenland", "GR"),
        ("", None),
        ("Atlantis", None),
    ],
)
def test_land(text, erwartet):
    assert land_iso(text) == erwartet


def test_dekodieren():
    assert dekodiere("Grüße".encode("utf-8-sig")) == "Grüße"
    assert dekodiere("Grüße".encode("cp1252")) == "Grüße"


def test_tabelle_sucht_kopfzeile():
    text = (
        'Transaktionsbericht\n"Zeitraum";"08/2026"\n\nTyp;Bestellnummer;Betrag\nA;1;2\n'
    )
    kopf, zeilen = lies_tabelle(text, pflicht={"Typ", "Bestellnummer"})
    assert kopf == ["Typ", "Bestellnummer", "Betrag"]
    assert zeilen == [(5, {"Typ": "A", "Bestellnummer": "1", "Betrag": "2"})]


def test_tabelle_ohne_kopfzeile():
    with pytest.raises(MarktplatzFormatError, match="Kopfzeile"):
        lies_tabelle("a;b\n1;2\n", pflicht={"Typ"})


def test_tabelle_tab_getrennt():
    kopf, zeilen = lies_tabelle("x\ty\n1\t2\n", pflicht={"x"})
    assert zeilen[0][1] == {"x": "1", "y": "2"}


def test_laenderdatei_amazon_bestellbericht():
    text = (
        "amazon-order-id\tpurchase-date\tship-country\n"
        "302-1\t2026-08-01\tFR\n"
        "302-2\t2026-08-01\tDE\n"
    )
    laender = lies_laenderdatei(text.encode())
    assert laender["302-1"].bestimmungsland == "FR"
    assert laender["302-2"].bestimmungsland == "DE"


def test_laenderdatei_ust_transaktionsbericht():
    text = (
        "TRANSACTION_EVENT_ID,SALE_DEPART_COUNTRY,SALE_ARRIVAL_COUNTRY,"
        "BUYER_VAT_NUMBER\n"
        "302-9,PL,DE,\n"
        "302-8,DE,AT,ATU12345678\n"
    )
    laender = lies_laenderdatei(text.encode())
    assert laender["302-9"].abgangsland == "PL"
    assert laender["302-8"].kaeufer_ust_id == "ATU12345678"


def test_laenderdatei_shopify():
    text = "Name,Email,Shipping Country,Billing Country\n#1001,x@y.example,IT,DE\n"
    assert lies_laenderdatei(text.encode())["#1001"].bestimmungsland == "IT"


def test_laenderdatei_ohne_passende_spalten():
    with pytest.raises(MarktplatzFormatError):
        lies_laenderdatei(b"a,b\n1,2\n")


def test_laenderdatei_bestellbericht_versandweg_und_geschaeftskunde():
    from pathlib import Path

    fixtures = Path(__file__).resolve().parents[1] / "examples" / "marktplatz"
    roh = (fixtures / "amazon_bestellungen.txt").read_bytes()
    roh = roh.replace(
        b"\tFR\t\tfalse\t\t\r\n302-1000003", b"\tFR\t\ttrue\t\t\r\n302-1000003", 1
    )
    angaben = lies_laenderdatei(roh)
    erste = angaben["302-1000001-0000001"]
    # der Bestellbericht kennt das Abgangsland nicht, aber den Versand durch Amazon
    assert (erste.abgangsland, erste.versand_durch_marktplatz) == (None, True)
    assert erste.geschaeftskunde is False
    assert angaben["302-1000002-0000002"].geschaeftskunde is True
