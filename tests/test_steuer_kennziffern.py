"""Kennziffern aus Buchungssätzen: Steuerschlüssel, Kennzifferkonten, Vorzeichen."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from accounti.models import Buchungssatz, BuchungStatus, Kontakt
from accounti.steuer.kennziffern import Kontenplan, ermittle
from accounti.steuer.zeitraum import Zeitraum

D = Decimal

AUGUST = Zeitraum.lies("2026-08")
TAG = date(2026, 8, 14)

KUNDE_DE = Kontakt(name="Kunde DE", debitor_konto="10001")
KUNDE_AT = Kontakt(
    name="Rahmen Wien", land="AT", ust_id="ATU12345678", debitor_konto="10002"
)
LIEFERANT_AT = Kontakt(name="Agentur Wien", land="AT", kreditor_konto="70002")
LIEFERANT_DE = Kontakt(name="Bau GmbH", kreditor_konto="70001")
KONTAKTE = [KUNDE_DE, KUNDE_AT, LIEFERANT_AT, LIEFERANT_DE]


def b(soll, haben, netto, schluessel=None, steuer=None, **kw):
    return Buchungssatz(
        datum=kw.pop("datum", TAG),
        soll_konto=soll,
        haben_konto=haben,
        betrag_netto=D(netto),
        steuer_schluessel=schluessel,
        steuer_betrag=D(steuer) if steuer is not None else None,
        buchungstext="Test",
        status=kw.pop("status", BuchungStatus.AUTO_GEBUCHT),
        **kw,
    )


def test_konstellationen_skr03():
    rechnung_ig = uuid4()
    buchungen = [
        b("10001", "8400", "1000.50", 3, "190.10"),  # Inland 19 %
        b("1200", "8300", "100.00", 2, "7.00"),  # Inland 7 % über die Bank
        b("8400", "10001", "50.00", 3, "9.50"),  # Gutschrift
        b("8736", "10001", "10.00", 3, "1.90"),  # gewährtes Skonto
        b("4930", "70001", "100.00", 9, "19.00"),  # Vorsteuer
        b("70001", "3736", "5.00", 9, "0.95"),  # erhaltenes Skonto
        b("10002", "8125", "5000.00", beleg_id=rechnung_ig),  # ig. Lieferung
        b("8730", "10002", "20.00", beleg_id=rechnung_ig),  # Skonto darauf
        b("10002", "8336", "300.00"),  # EU-Leistung, Empfänger schuldet
        b("10001", "8120", "700.00"),  # Ausfuhr
        b("1200", "8320", "200.00"),  # OSS Frankreich
        b("4900", "70002", "1000.00", 94, "190.00"),  # § 13b Abs. 1 (EU)
        b("4900", "70001", "400.00", 94, "76.00"),  # § 13b Abs. 2 (Inland)
        b("3425", "70002", "500.00", 19, "95.00"),  # ig. Erwerb 19 %
        b("1200", "10001", "1190.60"),  # Zahlung: keine Kennziffer
        b("1780", "70009", "500.00"),  # Zahllast: keine Kennziffer
        b("10001", "8400", "999.00", 3, "189.81", datum=date(2026, 9, 1)),  # außerhalb
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    va = e.voranmeldung
    assert va.werte == {
        81: D("940.50"),  # 1000,50 − 50 − 10
        86: D("100.00"),
        66: D("18.05"),  # 19,00 − 0,95
        41: D("4980.00"),  # 5000 − 20 Skonto
        21: D("300.00"),
        43: D("700.00"),
        45: D("200.00"),
        46: D("1000.00"),
        47: D("190.00"),
        84: D("400.00"),
        85: D("76.00"),
        67: D("266.00"),
        89: D("500.00"),
        61: D("95.00"),
    }
    assert e.ohne_kennziffer == [] and e.offen == []
    assert e.gebuchte_umsatzsteuer == D("185.70")  # 190,10 + 7 − 9,50 − 1,90
    eu = sorted((u.art, u.betrag, u.kontakt.name if u.kontakt else None) for u in e.eu)
    assert eu == [
        ("L", D("-20.00"), "Rahmen Wien"),
        ("L", D("5000.00"), "Rahmen Wien"),
        ("S", D("300.00"), "Rahmen Wien"),
    ]


def test_offene_buchungen_zaehlen_nicht():
    buchungen = [
        b("10001", "8400", "100", 3, "19", status=BuchungStatus.ZUR_PRUEFUNG),
        b("10001", "8400", "200", 3, "38", status=BuchungStatus.GEPRUEFT),
        b("10001", "8400", "300", 3, "57", status=BuchungStatus.EXPORTIERT),
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {81: D("500")}
    assert [x.betrag_netto for x in e.offen] == [D("100")]


def test_erloes_ohne_steuerschluessel_hat_keine_kennziffer():
    buchungen = [
        b("10001", "8200", "100"),  # Erlöse ohne Schlüssel
        b("10001", "8400", "100", 5, "16"),  # Schlüssel ohne Kennziffer
        b("4900", "1200", "50"),  # Aufwand ohne Vorsteuer: kein Befund
    ]
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    assert e.voranmeldung.werte == {}
    gruende = [grund for _, grund in e.ohne_kennziffer]
    assert "8200 ohne Steuerschlüssel" in gruende[0]
    assert "Steuerschlüssel 5" in gruende[1]


def test_eigene_kennzifferkonten_und_steuerrelevante_bereiche():
    plan = Kontenplan(
        kennziffern_konten={"8150": 43}, steuerrelevant=((8000, 8999), (2700, 2749))
    )
    buchungen = [b("10001", "8150", "100"), b("1200", "2700", "10")]
    e = ermittle(buchungen, AUGUST, plan, KONTAKTE)
    assert e.voranmeldung.werte == {43: D("100")}
    assert [x.haben_konto for x, _ in e.ohne_kennziffer] == ["2700"]


def test_skr04():
    plan = Kontenplan(kontenrahmen="SKR04")
    buchungen = [
        b("10001", "4400", "100", 3, "19"),
        b("10002", "4125", "50"),
        b("6300", "70001", "10", 9, "1.90"),
        b("1800", "4200", "5"),  # SKR04-Erlöskonto ohne Schlüssel
    ]
    e = ermittle(buchungen, AUGUST, plan, KONTAKTE)
    assert e.voranmeldung.werte == {81: D("100"), 41: D("50"), 66: D("1.90")}
    assert [x.haben_konto for x, _ in e.ohne_kennziffer] == ["4200"]


def test_abnehmer_ueber_offenen_posten_des_belegs():
    beleg = uuid4()
    e = ermittle(
        [b("1200", "8125", "100", beleg_id=beleg)],
        AUGUST,
        Kontenplan(),
        KONTAKTE,
        beleg_kontakte={beleg: KUNDE_AT.id},
    )
    assert e.eu[0].kontakt == KUNDE_AT


def test_quartal():
    q3 = Zeitraum.lies("2026-Q3")
    buchungen = [
        b("10001", "8400", "100", 3, "19", datum=date(2026, 7, 1)),
        b("10001", "8400", "100", 3, "19", datum=date(2026, 9, 30)),
        b("10001", "8400", "100", 3, "19", datum=date(2026, 10, 1)),
    ]
    assert ermittle(buchungen, q3, Kontenplan()).voranmeldung.werte == {81: D("200")}
