from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from accounti.bank.provider import BANK_PROVIDER, ProviderError
from accounti.models import Bankkonto
from tests.test_cli_opos import KOPF

DATEN = Path(__file__).parent / "daten" / "bank"

ZEILEN = [
    "DE12;13.03.26;13.03.26;KARTENZAHLUNG;PARKHAUS ALTSTADT;APCOA;;;-5,00;EUR;gebucht",
    "DE12;13.03.26;13.03.26;KARTENZAHLUNG;PARKHAUS ALTSTADT;APCOA;;;-5,00;EUR;gebucht",
    "DE12;15.03.26;15.03.26;ENTGELT;Kontoführung März;Sparkasse;;;-5,90;EUR;gebucht",
]


def _konto(ordner, **einstellungen):
    return Bankkonto(
        iban="DE12",
        bezeichnung="Giro",
        provider="datei",
        einstellungen={"ordner": str(ordner), **einstellungen},
    )


def test_datei_provider_ist_registriert():
    provider = BANK_PROVIDER["datei"]
    assert provider.felder == ("ordner", "format")
    assert provider.geheime_felder == ()


def test_liest_alle_kontoauszuege_eines_ordners(tmp_path):
    (tmp_path / "maerz-1.csv").write_text(
        "\n".join([KOPF, *ZEILEN[:2]]) + "\n", encoding="utf-8"
    )
    (tmp_path / "maerz-2.CSV").write_text(
        "\n".join([KOPF, ZEILEN[2]]) + "\n", encoding="utf-8"
    )
    (tmp_path / "notiz.txt").write_text("kein Kontoauszug", encoding="utf-8")
    abruf = BANK_PROVIDER["datei"]().abrufen(_konto(tmp_path), {}, None)
    assert [str(t.betrag) for t in abruf.transaktionen] == ["-5.00", "-5.00", "-5.90"]
    assert abruf.transaktionen[0].gegenkonto_name == "APCOA"


def test_festes_format(tmp_path):
    (tmp_path / "a.csv").write_text("\n".join([KOPF, ZEILEN[0]]) + "\n", "utf-8")
    abruf = BANK_PROVIDER["datei"]().abrufen(
        _konto(tmp_path, format="sparkasse"), {}, None
    )
    assert len(abruf.transaktionen) == 1


@pytest.mark.parametrize(
    ("einstellungen", "grund"),
    [({"ordner": "/gibt/es/nicht"}, "Ordner"), ({}, "Ordner")],
)
def test_fehlender_ordner(einstellungen, grund):
    konto = Bankkonto(iban="DE12", bezeichnung="x", einstellungen=einstellungen)
    with pytest.raises(ProviderError, match=grund):
        BANK_PROVIDER["datei"]().abrufen(konto, {}, None)


def test_unlesbare_datei_nennt_den_namen(tmp_path):
    (tmp_path / "kaputt.csv").write_text("irgendwas;ohne;kopf\n1;2;3\n", "utf-8")
    with pytest.raises(ProviderError, match="kaputt.csv"):
        BANK_PROVIDER["datei"]().abrufen(_konto(tmp_path), {}, None)


def test_liest_mt940_und_camt_und_meldet_den_saldo(tmp_path):
    (tmp_path / "maerz.sta").write_bytes((DATEN / "auszug.sta").read_bytes())
    (tmp_path / "notiz.txt").write_text("kein Kontoauszug", encoding="utf-8")
    (tmp_path / "rechnung.xml").write_text("<Invoice/>", encoding="utf-8")
    konto = Bankkonto(
        iban="DE02120300000000202051",
        bezeichnung="Giro",
        einstellungen={"ordner": str(tmp_path)},
    )
    abruf = BANK_PROVIDER["datei"]().abrufen(konto, {}, None)
    assert len(abruf.transaktionen) == 6
    assert abruf.transaktionen[0].quelle_referenz == "2603120000001"
    assert (abruf.saldo, abruf.saldo_datum) == (Decimal("2167.10"), date(2026, 3, 31))


def test_auszuege_fremder_konten_werden_uebersprungen(tmp_path):
    (tmp_path / "a.xml").write_bytes((DATEN / "camt053_v08.xml").read_bytes())
    (tmp_path / "b.xml").write_bytes((DATEN / "camt053_v02.xml").read_bytes())
    konto = Bankkonto(
        iban="DE44500105175407324931",
        bezeichnung="Zweitkonto",
        einstellungen={"ordner": str(tmp_path)},
    )
    abruf = BANK_PROVIDER["datei"]().abrufen(konto, {}, None)
    assert [str(t.betrag) for t in abruf.transaktionen] == [
        "-1500.00",
        "49.99",
        "-10.00",
    ]


def test_kaputter_kontoauszug_nennt_den_namen(tmp_path):
    (tmp_path / "kaputt.sta").write_text(
        ":20:X\n:25:1/2\n:60F:C260310EUR1,00\n:61:kaputt\n:62F:C260310EUR1,00\n-\n",
        encoding="utf-8",
    )
    with pytest.raises(ProviderError, match="kaputt.sta"):
        BANK_PROVIDER["datei"]().abrufen(_konto(tmp_path), {}, None)
