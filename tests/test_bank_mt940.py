from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from accounti.importers import BANK_IMPORTERS
from accounti.importers.kontoauszug import KontoauszugError
from accounti.importers.mt940 import lies_mt940
from accounti.models import TransaktionQuelle

DATEN = Path(__file__).parent / "daten" / "bank"


def _text(*zeilen: str) -> str:
    return "\r\n".join(zeilen) + "\r\n"


def _auszug(*umsatz: str, anfang="C260310EUR100,00", ende="C260310EUR100,00"):
    return _text(
        ":20:STARTUMSE",
        ":25:12030000/0000202051",
        ":28C:1",
        f":60F:{anfang}",
        *umsatz,
        f":62F:{ende}",
        "-",
    )


def test_beispielauszug_vollstaendig():
    auszuege = lies_mt940((DATEN / "auszug.sta").read_bytes().decode("cp1252"))
    assert len(auszuege) == 2
    eins, zwei = auszuege
    assert eins.konto == "12030000/0000202051"
    assert (eins.anfangssaldo, eins.endsaldo) == (
        Decimal("1000.00"),
        Decimal("2120.50"),
    )
    assert eins.endsaldo_datum == date(2026, 3, 13)
    assert eins.waehrung == "EUR"
    assert [str(t.betrag) for t in eins.umsaetze] == [
        "-59.50",
        "1190.00",
        "-5.00",
        "-5.00",
    ]
    karte, gutschrift, parken, _ = eins.umsaetze
    assert karte.datum == date(2026, 3, 12)
    assert karte.quelle is TransaktionQuelle.BANK
    assert karte.quelle_referenz == "2603120000001"
    assert karte.gegenkonto_name == "SHELL STATION KIEL"
    assert karte.gegenkonto_iban == "DE89370400440532013000"
    assert karte.verwendungszweck == (
        "2026-03-12T10.15 Debitk.1 2028-12 EREF: 70012345678901234567"
    )
    assert ":61:2603120312DR59,50" in karte.rohtext
    assert "?32SHELL STATION KIEL" in karte.rohtext
    # SVWZ über mehrere Unterfelder, EREF davor
    assert gutschrift.verwendungszweck == (
        "Rechnung RE-2026-0042 vom 01.03.2026 EREF: RE-2026-0042"
    )
    assert gutschrift.gegenkonto_name == "Muster Handels GmbH"
    # ohne Bankreferenz (nur NONREF) keine Referenz; Name über ?32 und ?33
    assert parken.quelle_referenz is None
    assert parken.gegenkonto_name == "APCOA PARKING Deutschland GmbH"
    assert parken.gegenkonto_iban is None
    # Rückbuchung einer Belastung (RD) ist eine Gutschrift; ?20/?21 ohne Schlüssel
    rueck, entgelt = zwei.umsaetze
    assert rueck.betrag == Decimal("59.50")
    assert entgelt.verwendungszweck == "Entgeltabrechnung siehe Anlage"
    assert entgelt.datum == date(2026, 3, 31)


def test_registriert_als_importer(tmp_path):
    datei = tmp_path / "a.sta"
    datei.write_bytes((DATEN / "auszug.sta").read_bytes())
    transaktionen = BANK_IMPORTERS["mt940"].importiere(datei)
    assert len(transaktionen) == 6


@pytest.mark.parametrize(
    ("zeile", "betrag"),
    [
        (":61:2603120312CR10,00NMSCNONREF", "10.00"),
        (":61:2603120312DR10,00NMSCNONREF", "-10.00"),
        (":61:2603120312D10,5NMSCNONREF", "-10.5"),
        (":61:2603120312RC10,00NRTINONREF", "-10.00"),  # Storno einer Gutschrift
        (":61:2603120312RD10,00NRTINONREF", "10.00"),  # Storno einer Belastung
        (":61:260312C10,NMSCNONREF", "10"),  # ohne Buchungsdatum, ohne Cent
    ],
)
def test_soll_haben_und_storno(zeile, betrag):
    wert = Decimal(betrag)
    anfang = "C260310EUR100,00"
    ende = f"C260312EUR{(Decimal('100') + wert):.2f}".replace(".", ",")
    (auszug,) = lies_mt940(_auszug(zeile, ":86:Test", anfang=anfang, ende=ende))
    assert auszug.umsaetze[0].betrag == wert


@pytest.mark.parametrize(
    ("zeile", "datum"),
    [
        (":61:2612311231D1,00NMSCNONREF", date(2026, 12, 31)),
        # Valuta Dezember, gebucht Januar — und umgekehrt
        (":61:2612310102D1,00NMSCNONREF", date(2027, 1, 2)),
        (":61:2701021231D1,00NMSCNONREF", date(2026, 12, 31)),
        (":61:270102D1,00NMSCNONREF", date(2027, 1, 2)),  # nur Valuta
    ],
)
def test_buchungsdatum_ueber_den_jahreswechsel(zeile, datum):
    text = _auszug(zeile, ":86:x", anfang="C261230EUR10,00", ende="C270102EUR9,00")
    (auszug,) = lies_mt940(text)
    assert auszug.umsaetze[0].datum == datum


def test_referenzen_und_zusatzzeile():
    text = _auszug(
        ":61:2603120312DR1,00NTRFKREF4711//BANKREF0815",
        "/OCMT/EUR1,00/",
        ":86:Miete",
        ":61:2603120312DR1,00NTRFNONREF//NONREF",
        ":86:Miete",
        ende="C260312EUR98,00",
    )
    (auszug,) = lies_mt940(text)
    assert [t.quelle_referenz for t in auszug.umsaetze] == ["BANKREF0815", None]


def test_unstrukturierter_verwendungszweck_ueber_mehrere_zeilen():
    text = _auszug(
        ":61:2603120312DR1,00NTRFNONREF",
        ":86:Miete Maerz",
        "Buero Hafenstrasse",
        ende="C260312EUR99,00",
    )
    (auszug,) = lies_mt940(text)
    assert auszug.umsaetze[0].verwendungszweck == "Miete Maerz Buero Hafenstrasse"


def test_ohne_svwz_zaehlt_der_ganze_text_und_buchungstext_als_rueckfall():
    text = _auszug(
        ":61:2603120312DR1,00NTRFNONREF",
        ":86:177?00ONLINE-UEBERWEISUNG?20Kaution Lager?21Halle 3?32Vermieter KG",
        ":61:2603120312DR1,00NCHGNONREF",
        ":86:805?00ABSCHLUSS?32Sparkasse",
        ende="C260312EUR98,00",
    )
    (auszug,) = lies_mt940(text)
    eins, zwei = auszug.umsaetze
    assert eins.verwendungszweck == "Kaution LagerHalle 3"
    assert zwei.verwendungszweck == "ABSCHLUSS"


def test_anderes_trennzeichen_und_zeilen_mit_at():
    text = (
        ":20:X@@:25:DE02120300000000202051@@:28C:1@@:60F:C260310EUR10,00@@"
        ":61:2603120312DR1,00NMSCNONREF@@:86:106/00KARTE/20SVWZ+Kaffee/32BAECKER"
        "@@:62F:C260312EUR9,00@@-@@"
    )
    (auszug,) = lies_mt940(text)
    (tx,) = auszug.umsaetze
    assert (tx.verwendungszweck, tx.gegenkonto_name) == ("Kaffee", "BAECKER")
    assert auszug.konto == "DE02120300000000202051"


def test_swift_kopf_und_zwischensalden():
    text = (
        "{1:F01COBADEFFAXXX0000000000}{2:I940COBADEFFXXXXN}{4:\r\n"
        ":20:X\r\n:25:12030000/202051\r\n:28C:1/1\r\n:60F:C260310EUR10,00\r\n"
        ":61:2603110311DR1,00NMSCNONREF\r\n:86:a\r\n:62M:C260311EUR9,00\r\n-}"
        "{1:F01COBADEFFAXXX0000000000}{2:I940COBADEFFXXXXN}{4:\r\n"
        ":20:X\r\n:25:12030000/202051\r\n:28C:1/2\r\n:60M:C260311EUR9,00\r\n"
        ":61:2603120312CR2,00NMSCNONREF\r\n:86:b\r\n:62F:C260312EUR11,00\r\n-}"
    )
    eins, zwei = lies_mt940(text)
    assert [t.betrag for t in eins.umsaetze + zwei.umsaetze] == [
        Decimal("-1.00"),
        Decimal("2.00"),
    ]
    assert zwei.endsaldo == Decimal("11.00")


def test_negativer_saldo():
    text = _auszug(
        ":61:2603120312DR150,00NMSCNONREF",
        ":86:x",
        anfang="D260310EUR10,00",
        ende="D260312EUR160,00",
    )
    (auszug,) = lies_mt940(text)
    assert (auszug.anfangssaldo, auszug.endsaldo) == (
        Decimal("-10.00"),
        Decimal("-160.00"),
    )


def test_auszugsinformation_nach_dem_endsaldo_gehoert_zu_keinem_umsatz():
    text = _text(
        ":20:X",
        ":25:12030000/202051",
        ":60F:C260310EUR10,00",
        ":61:2603120312DR1,00NMSCNONREF",
        ":62F:C260312EUR9,00",
        ":86:Ihr Dispositionskredit wurde angepasst",
        "-",
    )
    (auszug,) = lies_mt940(text)
    assert auszug.umsaetze[0].verwendungszweck == ""


def test_saldenprobe_findet_eine_fehlende_zeile():
    text = _auszug(":61:2603120312DR1,00NMSCNONREF", ":86:x", ende="C260312EUR98,00")
    with pytest.raises(KontoauszugError, match="Saldo"):
        lies_mt940(text)


@pytest.mark.parametrize(
    "text",
    [
        _auszug(":61:kaputt", ":86:x"),
        ":20:X\r\n:25:1/2\r\n:60F:C2603EUR1\r\n-",
        "kein Kontoauszug",
    ],
)
def test_unlesbares_wird_abgelehnt(text):
    with pytest.raises(KontoauszugError):
        lies_mt940(text)


def test_lange_texte_werden_gekuerzt():
    zweck = "?20" + "?21".join(["A" * 27] * 10)
    text = _auszug(
        ":61:2603120312DR1,00NMSCNONREF",
        f":86:166?00X{zweck}?32{'N' * 27}?33{'M' * 27}",
        ende="C260312EUR99,00",
    )
    (auszug,) = lies_mt940(text)
    tx = auszug.umsaetze[0]
    assert len(tx.verwendungszweck) <= 500
    assert len(tx.rohtext) <= 2000


def test_folgeseite_mit_zwischensaldo_wird_erkannt():
    seite_1 = _auszug().replace(":62F:", ":62M:")
    seite_2 = _auszug().replace(":60F:", ":60M:")
    erste, zweite = lies_mt940(seite_1 + seite_2)
    assert (erste.fortsetzung, zweite.fortsetzung) == (False, True)
