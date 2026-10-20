"""EXTF-Grundbausteine: Kopfzeile, Feldwerte, Quotierung, Zeichensatz."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from accounti.export.datev_felder import BUCHUNGSSTAPEL, DEBITOREN_KREDITOREN, Feld
from accounti.export.datev_format import (
    DatevFormatError,
    Kopf,
    belegfeld1,
    feldnummer,
    feldwert,
    kontoart,
    kopfzeile,
    schreibe_extf,
)

ERZEUGT = datetime(2026, 9, 1, 8, 30, 15, 123000)


def _kopf(**kw):
    werte = {
        "kategorie": 16,
        "formatname": "Debitoren/Kreditoren",
        "formatversion": 5,
        "berater": 29098,
        "mandant": 55003,
        "wj_beginn": date(2026, 1, 1),
        "skr": "03",
        "erzeugt_am": ERZEUGT,
    }
    werte.update(kw)
    return Kopf(**werte)


def test_kopfzeile_wie_datev_musterdatei():
    # DATEV-Musterdatei EXTF_DebKred_Stamm.csv, nur Zeitstempel, Nummern und WJ eigene
    assert kopfzeile(_kopf()) == (
        '"EXTF";700;16;"Debitoren/Kreditoren";5;20260901083015123;;"RE";"";"";'
        '29098;55003;20260101;4;;;"";"";;;;"";;"";;;"03";;;"";"accounti"'
    )


def test_kopfzeile_buchungsstapel():
    zeile = kopfzeile(
        _kopf(
            kategorie=21,
            formatname="Buchungsstapel",
            formatversion=13,
            datum_von=date(2026, 8, 1),
            datum_bis=date(2026, 8, 31),
            bezeichnung="Belege 2026-08",
            buchungstyp=1,
            rechnungslegungszweck=0,
            festschreibung=0,
            waehrung="EUR",
        )
    )
    felder = zeile.split(";")
    assert len(felder) == 31
    assert felder[14:22] == [
        "20260801",
        "20260831",
        '"Belege 2026-08"',
        '""',
        "1",
        "0",
        "0",
        '"EUR"',
    ]


def test_bezeichnung_zu_lang():
    with pytest.raises(DatevFormatError, match="Bezeichnung"):
        kopfzeile(_kopf(bezeichnung="x" * 31))


@pytest.mark.parametrize(
    ("feld", "wert", "erwartet"),
    [
        (Feld("Name", "T", 50), 'Galerie "Nord"', '"Galerie ""Nord"""'),
        (Feld("Name", "T", 50), None, '""'),
        (Feld("Name", "T", 50), "Zeile1\r\nZeile2\tx", '"Zeile1  Zeile2 x"'),
        (Feld("Skonto", "Z", 2, 2), Decimal("2"), "2,00"),
        (Feld("Tage", "Z", 3), 30, "30"),
        (Feld("Tage", "Z", 3), None, ""),
        (Feld("Umsatz", "B", 10, 2), Decimal("1234.5"), "1234,50"),
        (Feld("Datum", "D", 8), date(2026, 8, 4), "04082026"),
        (Feld("Konto", "K", 9), "10001", "10001"),
    ],
)
def test_feldwert(feld, wert, erwartet):
    assert feldwert(feld, wert) == erwartet


def test_belegdatum_ttmm():
    assert feldwert(Feld("Belegdatum", "D", 8), date(2026, 8, 4), "%d%m") == "0408"


def test_text_zu_lang_und_falscher_zeichensatz():
    with pytest.raises(DatevFormatError, match="Kurz"):
        feldwert(Feld("Kurz", "T", 3), "abcd")
    with pytest.raises(DatevFormatError, match="Windows-1252"):
        schreibe_extf(_kopf(), DEBITOREN_KREDITOREN, [{1: "10000", 2: "Łódź"}])


def test_zahl_zu_lang():
    with pytest.raises(DatevFormatError, match="Tage"):
        feldwert(Feld("Tage", "Z", 2), 120)


def test_schreiben():
    inhalt = schreibe_extf(_kopf(), DEBITOREN_KREDITOREN, [{1: "10000", 2: "Müller"}])
    text = inhalt.decode("cp1252")
    assert text.endswith("\r\n")
    zeilen = text.split("\r\n")
    assert zeilen[1].split(";")[:3] == [
        "Konto",
        "Name (Adressattyp Unternehmen)",
        "Unternehmensgegenstand",
    ]
    werte = zeilen[2].split(";")
    assert len(werte) == 254
    assert werte[:3] == ["10000", '"Müller"', '""']


def test_feldnummer():
    assert feldnummer(BUCHUNGSSTAPEL, "Beleglink") == 20
    assert feldnummer(DEBITOREN_KREDITOREN, "Verknüpftes OPOS-Konto") == 232
    with pytest.raises(KeyError):
        feldnummer(DEBITOREN_KREDITOREN, "Leerfeld")  # nicht eindeutig


def test_kontoart():
    assert kontoart("8400", 4) == "sachkonto"
    assert kontoart("10001", 4) == "personenkonto"
    assert kontoart("177720", 4) is None  # passt nicht zur Sachkontenlänge
    assert kontoart("177720", 6) == "sachkonto"
    assert kontoart("12a", 4) is None


@pytest.mark.parametrize(
    ("roh", "erwartet"),
    [
        ("Rg32029/2024", "Rg32029/2024"),
        ("302-1234567-1234567", "302-1234567-1234567"),
        ("R.2026 0815", "R20260815"),  # Punkt und Leerzeichen sind unzulässig
        ("Müller;1:2,3", "Mller123"),
        ("$&%*+-/_", "$&%*+-/_"),
        ("x" * 40, "x" * 36),
        (None, ""),
    ],
)
def test_belegfeld1_nur_datev_zeichen(roh, erwartet):
    # DATEV-Format, Buchungsstapel Feld 11: ^(["][\w$&%*+\-\/]{0,36}["])$
    assert belegfeld1(roh) == erwartet
