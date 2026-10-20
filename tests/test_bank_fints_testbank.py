"""Der echte python-fints-Client gegen die lokale Testbank (127.0.0.1).

Hier läuft kein Ersatz für python-fints: Dialog, Kundensystem-ID, TAN-Ablauf,
Aufsetzpunkt und Sitzungsdaten kommen aus der Bibliothek selbst. Damit fällt auf,
wenn sich ihr Verhalten (auch die intern genutzten Methoden) ändert.
"""

import base64
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from accounti.bank.einstellungen import FinTSEinstellungen
from accounti.bank.fints import SITZUNG, FinTSProvider, richte_fints_ein
from accounti.bank.provider import FreigabeNoetigError, ProviderError
from accounti.models import Bankkonto
from tests.fints_testbank import BLZ, IBAN, FinTSTestbank

DATEN = Path(__file__).parent / "daten" / "bank"
PRODUKT_ID = "ACCOUNTITEST0815"
ZUGANG = {"benutzerkennung": "kunde-4711", "pin": "1234"}


def _mt940_in_zwei_teilen() -> list[str]:
    text = (DATEN / "auszug.sta").read_bytes().decode("cp1252")
    mitte = text.index(":20:", 10)  # zweiter Auszug beginnt hier
    return [text[:mitte], text[mitte:]]


@pytest.fixture
def testbank():
    bank = FinTSTestbank(
        mt940_teile=_mt940_in_zwei_teilen(),
        camt_dokumente=[(DATEN / "camt052_v08.xml").read_bytes()],
    )
    bank.starte()
    yield bank
    bank.stoppe()


def _konto(testbank, **einstellungen):
    return Bankkonto(
        iban=IBAN,
        bezeichnung="Giro Testbank",
        provider="fints",
        einstellungen={"blz": BLZ, "server": testbank.url, **einstellungen},
    )


def _provider(freigabe=None):
    return FinTSProvider(
        freigabe, einstellungen=FinTSEinstellungen(produkt_id=PRODUKT_ID)
    )


def test_mt940_mit_freigabe_und_gesicherter_sitzung(testbank):
    tans = []

    def frage(anfrage):
        tans.append(anfrage.text)
        return "123456"

    konto = _konto(testbank, format="mt940")
    abruf = _provider(frage).abrufen(konto, ZUGANG, date(2026, 3, 1))
    assert len(abruf.transaktionen) == 6
    assert abruf.transaktionen[0].quelle_referenz == "2603120000001"
    assert (abruf.saldo, abruf.saldo_datum) == (Decimal("2167.10"), date(2026, 3, 31))
    assert tans == ["Bitte TAN aus der SMS eingeben"]
    assert testbank.tans == ["123456"]
    # Produkt-ID der Installation bei jeder Dialoginitialisierung
    assert testbank.produkt_ids and set(testbank.produkt_ids) == {PRODUKT_ID}
    assert set(testbank.produkt_versionen) == {"0.1"}
    # zwei Teile über den Aufsetzpunkt, ab dem gewünschten Datum
    assert [z[2] for z in testbank.zeitraeume] == [None, "1"]
    assert testbank.zeitraeume[0][0] == date(2026, 3, 1)
    assert len(testbank.systeme) == 1

    # zweiter Abruf ohne Rückfrage: gleiche Kundensystem-ID, die Bank kennt die SCA
    nachrichten = len(testbank.eingang)
    zweiter = _provider().abrufen(konto, abruf.zugang, date(2026, 3, 1))
    assert len(zweiter.transaktionen) == 6
    assert len(testbank.systeme) == 1
    assert testbank.tans == ["123456"]
    assert not any("HKSYN" in n for n in testbank.eingang[nachrichten:])


def test_camt_wenn_die_bank_es_anbietet(testbank):
    testbank.camt, testbank.sca_bei_init = True, False
    abruf = _provider().abrufen(_konto(testbank), ZUGANG, None)
    (tx,) = abruf.transaktionen
    assert (tx.betrag, tx.quelle_referenz) == (Decimal("-25.00"), "2026031900011")
    assert any("HKCAZ" in n for n in testbank.eingang)
    assert not any("HKKAZ" in n for n in testbank.eingang)


def test_ohne_rueckfrage_wird_die_freigabe_zum_zustand(testbank):
    with pytest.raises(FreigabeNoetigError, match="fints freigeben") as fehler:
        _provider().abrufen(_konto(testbank), ZUGANG, None)
    sitzung = base64.b64decode(fehler.value.zugang[SITZUNG])
    assert sitzung.startswith(b"python-fints_DATABLOB")
    assert testbank.zeitraeume == []


def test_falsche_pin(testbank):
    with pytest.raises(ProviderError, match="PIN"):
        _provider(lambda a: "123456").abrufen(
            _konto(testbank), {**ZUGANG, "pin": "9999"}, None
        )


def test_einrichtung_gegen_die_testbank(testbank):
    konto, zugang = richte_fints_ein(
        _konto(testbank),
        ZUGANG,
        waehle_verfahren=lambda v: v[0].kennung,
        waehle_medium=lambda m: m[0],
        freigabe=lambda a: "123456",
        einstellungen=FinTSEinstellungen(produkt_id=PRODUKT_ID),
    )
    assert konto.einstellungen["tan_verfahren"] == "942"
    assert testbank.freigegeben == {testbank.systeme[0]}
    abruf = _provider().abrufen(konto, zugang, None)  # danach ohne Eingabe
    assert len(abruf.transaktionen) == 6
