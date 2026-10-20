from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from accounti.importers import BANK_IMPORTERS
from accounti.importers.camt import lies_camt
from accounti.importers.kontoauszug import KontoauszugError

DATEN = Path(__file__).parent / "daten" / "bank"


def _doc(*eintraege: str, ns="camt.053.001.08", bal="") -> bytes:
    return (
        f'<?xml version="1.0"?><Document xmlns="urn:iso:std:iso:20022:tech:xsd:{ns}">'
        "<BkToCstmrStmt><Stmt><Acct><Id><IBAN>DE02120300000000202051</IBAN></Id></Acct>"
        f"{bal}{''.join(eintraege)}</Stmt></BkToCstmrStmt></Document>"
    ).encode()


def _ntry(betrag="1.00", ind="DBIT", sts="<Sts><Cd>BOOK</Cd></Sts>", rest=""):
    return (
        f'<Ntry><Amt Ccy="EUR">{betrag}</Amt><CdtDbtInd>{ind}</CdtDbtInd>{sts}'
        f"<BookgDt><Dt>2026-03-12</Dt></BookgDt>{rest}</Ntry>"
    )


def test_camt053_v08():
    (auszug,) = lies_camt((DATEN / "camt053_v08.xml").read_bytes())
    assert auszug.konto == "DE02120300000000202051"
    assert (auszug.anfangssaldo, auszug.endsaldo) == (
        Decimal("1000.00"),
        Decimal("2120.50"),
    )
    assert auszug.endsaldo_datum == date(2026, 3, 13)
    karte, gutschrift, parken1, parken2 = auszug.umsaetze
    assert [str(t.betrag) for t in auszug.umsaetze] == [
        "-59.50",
        "1190.00",
        "-5.00",
        "-5.00",
    ]
    assert karte.datum == date(2026, 3, 12)
    assert karte.quelle_referenz == "2026031200001"
    assert karte.gegenkonto_name == "SHELL STATION KIEL"
    assert karte.gegenkonto_iban == "DE89370400440532013000"
    assert karte.verwendungszweck == (
        "2026-03-12T10.15 Debitk.1 2028-12 EREF: 70012345678901234567"
    )
    assert "AcctSvcrRef" in karte.rohtext
    # Gutschrift: Gegenpartei ist der Zahler (Dbtr), nicht man selbst (Cdtr)
    assert gutschrift.gegenkonto_name == "Muster Handels GmbH"
    assert gutschrift.gegenkonto_iban == "DE12500105170648489890"
    assert gutschrift.verwendungszweck == (
        "Rechnung RE-2026-0042 vom 01.03.2026 EREF: RE-2026-0042"
    )
    # Buchungsdatum als Zeitpunkt; NOTPROVIDED ist keine Referenz
    assert parken1.datum == date(2026, 3, 13)
    assert parken1.verwendungszweck == "PARKHAUS ALTSTADT"
    assert (parken1.quelle_referenz, parken2.quelle_referenz) == (
        "2026031300003",
        "2026031300004",
    )


def test_camt053_v02_sammler_storno_strukturierte_referenz():
    (auszug,) = lies_camt((DATEN / "camt053_v02.xml").read_bytes())
    assert auszug.konto == "DE44500105175407324931"
    assert (auszug.anfangssaldo, auszug.endsaldo) == (
        Decimal("500.00"),
        Decimal("-960.01"),
    )
    sammler, rueck, verein = auszug.umsaetze
    assert sammler.betrag == Decimal("-1500.00")
    assert sammler.verwendungszweck == (
        "Abschlag Maerz EREF: LOHN-03-1; Abschlag Maerz EREF: LOHN-03-2"
    )
    assert sammler.gegenkonto_name is None  # zwei Empfänger: keiner wird geraten
    assert sammler.gegenkonto_iban is None
    assert rueck.betrag == Decimal("49.99")
    assert rueck.gegenkonto_name == "Telefon AG"  # Gutschrift ohne Dbtr → Cdtr
    assert rueck.verwendungszweck == "Ruecklastschrift Kundennr 4711"
    assert verein.verwendungszweck == "RF18539007547034"
    assert verein.quelle_referenz is None


def test_camt052_nur_gebuchte_eintraege():
    (auszug,) = lies_camt((DATEN / "camt052_v08.xml").read_bytes())
    (tx,) = auszug.umsaetze
    assert (tx.betrag, tx.gegenkonto_name) == (
        Decimal("-25.00"),
        "Buchhandlung am Markt",
    )
    assert auszug.anfangssaldo is None and auszug.endsaldo is None


def test_camt054_und_rueckfall_auf_zusatzinfo():
    xml = (
        b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.054.001.08">'
        b"<BkToCstmrDbtCdtNtfctn><Ntfctn><Acct><Id><IBAN>DE02120300000000202051"
        b"</IBAN></Id></Acct>"
        + _ntry("7.50", rest="<AddtlNtryInf>ENTGELT</AddtlNtryInf>").encode()
        + b"</Ntfctn></BkToCstmrDbtCdtNtfctn></Document>"
    )
    (auszug,) = lies_camt(xml)
    assert auszug.umsaetze[0].verwendungszweck == "ENTGELT"
    assert auszug.umsaetze[0].betrag == Decimal("-7.50")


def test_ohne_status_gilt_gebucht_info_nicht():
    (auszug,) = lies_camt(
        _doc(_ntry(sts=""), _ntry(sts="<Sts><Cd>INFO</Cd></Sts>"), _ntry(sts=""))
    )
    assert len(auszug.umsaetze) == 2


def test_waehrung_aus_dem_betrag():
    (auszug,) = lies_camt(_doc(_ntry().replace("EUR", "CHF")))
    assert auszug.umsaetze[0].waehrung == "CHF"


def test_saldenprobe():
    bal = (
        "<Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp><Amt Ccy='EUR'>10.00</Amt>"
        "<CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-03-12</Dt></Dt></Bal>"
        "<Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy='EUR'>8.00</Amt>"
        "<CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-03-12</Dt></Dt></Bal>"
    )
    with pytest.raises(KontoauszugError, match="Saldo"):
        lies_camt(_doc(_ntry("1.00"), bal=bal))
    (auszug,) = lies_camt(_doc(_ntry("1.00"), _ntry("1.00"), bal=bal))
    assert auszug.endsaldo == Decimal("8.00")


@pytest.mark.parametrize(
    "xml",
    [
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><Document/>',
        b'<!DOCTYPE Document SYSTEM "file:///etc/passwd"><Document/>',
        b"<Document><kaputt></Document>",
        b"<Document><Andere/></Document>",
        _doc(_ntry("abc")),
        _doc(_ntry(ind="XXXX")),
        _doc(_ntry().replace("<BookgDt><Dt>2026-03-12</Dt></BookgDt>", "")),
    ],
)
def test_unsicheres_oder_unlesbares_wird_abgelehnt(xml):
    with pytest.raises(KontoauszugError):
        lies_camt(xml)


def test_registriert_als_importer(tmp_path):
    datei = tmp_path / "a.xml"
    datei.write_bytes((DATEN / "camt053_v08.xml").read_bytes())
    assert len(BANK_IMPORTERS["camt"].importiere(datei)) == 4


def test_ruecklastschrift_mit_beiden_parteien_nennt_den_glaeubiger():
    """Storno (RvslInd): die Rücklastschrift trägt die Parteien der Lastschrift —
    Dbtr ist man selbst, die Gegenpartei ist der Gläubiger (Cdtr)."""
    parteien = (
        "<NtryDtls><TxDtls><RltdPties>"
        "<Dbtr><Pty><Nm>Meine Firma GmbH</Nm></Pty></Dbtr>"
        "<DbtrAcct><Id><IBAN>DE02120300000000202051</IBAN></Id></DbtrAcct>"
        "<Cdtr><Pty><Nm>Telefon AG</Nm></Pty></Cdtr>"
        "<CdtrAcct><Id><IBAN>DE89370400440532013000</IBAN></Id></CdtrAcct>"
        "</RltdPties></TxDtls></NtryDtls>"
    )
    storno = _ntry("49.99", ind="CRDT", rest=parteien).replace(
        "<Sts>", "<RvslInd>true</RvslInd><Sts>"
    )
    gutschrift = _ntry("49.99", ind="CRDT", rest=parteien)
    rueck, normal = lies_camt(_doc(storno, gutschrift))[0].umsaetze
    assert (rueck.gegenkonto_name, rueck.gegenkonto_iban) == (
        "Telefon AG",
        "DE89370400440532013000",
    )
    assert normal.gegenkonto_name == "Meine Firma GmbH"  # Gutschrift: der Zahler


@pytest.mark.parametrize(
    ("kodierung", "bom"), [("utf-16", b""), ("utf-16-be", b"\xfe\xff")]
)
def test_dtd_auch_in_utf16_abgelehnt(kodierung, bom):
    """Der Byte-Vergleich fände „<!DOCTYPE“ in UTF-16 nicht — geprüft wird im
    XML-Parser selbst."""
    rumpf = _doc(_ntry(rest="<AddtlNtryInf>&b;</AddtlNtryInf>")).decode()
    text = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<!DOCTYPE d [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;">]>'
        + rumpf.split("?>", 1)[1]
    )
    with pytest.raises(KontoauszugError, match="DTD"):
        lies_camt(bom + text.encode(kodierung))
