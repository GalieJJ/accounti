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


def _giro(ordner):
    return Bankkonto(
        iban="DE02120300000000202051",
        bezeichnung="Giro",
        einstellungen={"ordner": str(ordner)},
    )


def _speichern(transaktionen, konto):
    from accounti.bank.lauf import speichere_neue
    from accounti.db import init_db, session_factory
    from accounti.db.repository import lade_transaktionen

    engine, make_session = session_factory("sqlite://")
    init_db(engine)
    with make_session() as s:
        ergebnis = speichere_neue(s, transaktionen, konto.iban, konto)
        summe = sum(t.betrag for t in lade_transaktionen(s))
    engine.dispose()
    return ergebnis, summe


@pytest.mark.parametrize("datei", ["camt053_v08.xml", "auszug.sta"])
def test_doppelt_heruntergeladener_auszug_kommt_einmal(tmp_path, datei):
    """Wie nach einem erneuten Download: „auszug.xml“ und „auszug (1).xml“."""
    endung = Path(datei).suffix
    (tmp_path / f"auszug{endung}").write_bytes((DATEN / datei).read_bytes())
    (tmp_path / f"auszug (1){endung}").write_bytes((DATEN / datei).read_bytes())
    abruf = BANK_PROVIDER["datei"]().abrufen(_giro(tmp_path), {}, None)
    (neu, _), _ = _speichern(abruf.transaktionen, _giro(tmp_path))
    assert neu == (4 if endung == ".xml" else 6)  # MT940 hier ohne Bankreferenz


def test_ueberlappende_auszuege_mit_bankreferenz(tmp_path):
    """camt.052 (Tagesreport) neben camt.053 (Auszug) desselben Tages: dieselben
    Buchungen mit derselben AcctSvcrRef kommen einmal."""
    import re

    voll = (DATEN / "camt053_v08.xml").read_text(encoding="utf-8")
    (tmp_path / "monat.xml").write_text(voll, encoding="utf-8")
    # Tagesreport vom 13.03.: ohne Salden, ohne den Umsatz vom 12.03., ohne RmtInf
    tag = re.sub(r"<Bal>.*?</Bal>", "", voll, flags=re.S)
    tag = re.sub(r"<Ntry>.*?</Ntry>", "", tag, count=1, flags=re.S)
    tag = re.sub(r"<RmtInf>.*?</RmtInf>", "", tag, flags=re.S)
    tag = tag.replace("BkToCstmrStmt", "BkToCstmrAcctRpt").replace("Stmt>", "Rpt>")
    (tmp_path / "tag.xml").write_text(tag, encoding="utf-8")
    abruf = BANK_PROVIDER["datei"]().abrufen(_giro(tmp_path), {}, None)
    (neu, _), summe = _speichern(abruf.transaktionen, _giro(tmp_path))
    assert (neu, summe) == (4, Decimal("1120.50"))


CAMT053_SAMMLER = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08">
<BkToCstmrStmt><Stmt><Id>S1</Id>
<Acct><Id><IBAN>DE02120300000000202051</IBAN></Id></Acct>
<Ntry><Amt Ccy="EUR">300.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
<BookgDt><Dt>2026-03-12</Dt></BookgDt><AcctSvcrRef>2026031200007</AcctSvcrRef>
<AddtlNtryInf>SAMMLER-UEBERWEISUNG 3 POSTEN</AddtlNtryInf></Ntry>
</Stmt></BkToCstmrStmt></Document>"""

CAMT054_AUFLOESUNG = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.054.001.08">
<BkToCstmrDbtCdtNtfctn><Ntfctn><Id>N1</Id>
<Acct><Id><IBAN>DE02120300000000202051</IBAN></Id></Acct>
<Ntry><Amt Ccy="EUR">300.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
<BookgDt><Dt>2026-03-12</Dt></BookgDt><AcctSvcrRef>2026031200007</AcctSvcrRef>
<NtryDtls>{}</NtryDtls></Ntry>
</Ntfctn></BkToCstmrDbtCdtNtfctn></Document>""".format(
    "".join(
        f"<TxDtls><Amt Ccy='EUR'>100.00</Amt><RltdPties><Cdtr><Nm>Lieferant {i}</Nm>"
        f"</Cdtr></RltdPties><RmtInf><Ustrd>RE {i}</Ustrd></RmtInf></TxDtls>"
        for i in (1, 2, 3)
    )
)


def test_camt054_neben_camt053_bucht_den_sammler_nicht_doppelt(tmp_path):
    (tmp_path / "auszug.xml").write_text(CAMT053_SAMMLER, encoding="utf-8")
    (tmp_path / "avis.xml").write_text(CAMT054_AUFLOESUNG, encoding="utf-8")
    abruf = BANK_PROVIDER["datei"]().abrufen(_giro(tmp_path), {}, None)
    assert len(abruf.transaktionen) == 2  # beide Dateien gelesen
    (neu, doppelt), summe = _speichern(abruf.transaktionen, _giro(tmp_path))
    assert (neu, doppelt, summe) == (1, 1, Decimal("-300.00"))


def test_kartenkonto_ohne_iban_ueberspringt_auszuege_mit_iban(tmp_path):
    (tmp_path / "giro.xml").write_bytes((DATEN / "camt053_v08.xml").read_bytes())
    karte = Bankkonto(
        iban="DKBVISA9", bezeichnung="Visa", einstellungen={"ordner": str(tmp_path)}
    )
    assert BANK_PROVIDER["datei"]().abrufen(karte, {}, None).transaktionen == []
