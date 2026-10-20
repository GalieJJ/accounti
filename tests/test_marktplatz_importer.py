"""Marktplatz-Importer: Amazon, eBay, PayPal, Shopify gegen anonymisierte Fixtures."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from accounti.importers.marktplatz import (
    MARKTPLATZ_IMPORTER,
    MarktplatzFormatError,
    lies_laenderdatei,
)
from accounti.models.integrationen import Gebuehrenart, Postenart

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "marktplatz"
D = Decimal


def _lies(markt, datei, laender=None):
    inhalt = (FIXTURES / datei).read_bytes()
    angaben = lies_laenderdatei((FIXTURES / laender).read_bytes()) if laender else None
    return MARKTPLATZ_IMPORTER[markt].lies(inhalt, datei, angaben)


def _summe(abrechnung, art):
    return sum((p.betrag for p in abrechnung.posten if p.art is art), D("0"))


def test_registry():
    assert {"amazon", "ebay", "paypal", "shopify"} <= set(MARKTPLATZ_IMPORTER)


# --- Amazon ---------------------------------------------------------------------


@pytest.fixture
def amazon():
    (abrechnung,) = _lies(
        "amazon", "amazon_abrechnung_v2.txt", "amazon_bestellungen.txt"
    )
    return abrechnung


def test_amazon_kopf(amazon):
    assert amazon.marktplatz == "amazon"
    assert amazon.nummer == "11223344556"
    assert (amazon.von, amazon.bis) == (date(2026, 8, 1), date(2026, 8, 15))
    assert amazon.auszahlungsdatum == date(2026, 8, 17)
    assert amazon.auszahlung == D("209.85")
    assert amazon.waehrung == "EUR"


def test_amazon_summe_der_posten_ist_auszahlung(amazon):
    assert amazon.summe() == D("209.85")


def test_amazon_bestandteile(amazon):
    assert _summe(amazon, Postenart.ERLOES) == D("438.29")
    assert _summe(amazon, Postenart.ERSTATTUNG) == D("-60.00")
    assert _summe(amazon, Postenart.GEBUEHR) == D("-133.44")
    assert _summe(amazon, Postenart.WERBUNG) == D("-25.00")
    assert _summe(amazon, Postenart.EINBEHALT) == D("-25.00")
    assert _summe(amazon, Postenart.ERSATZ) == D("15.00")


def test_amazon_gebuehrenarten(amazon):
    arten = {p.beschreibung: p.gebuehrenart for p in amazon.posten if p.gebuehrenart}
    assert arten["ItemFees/Commission"] is Gebuehrenart.VERKAUF
    assert arten["ItemFees/FBAPerUnitFulfillmentFee"] is Gebuehrenart.VERSAND
    assert arten["other-transaction/Storage Fee"] is Gebuehrenart.LAGER
    assert arten["other-transaction/Subscription Fee"] is Gebuehrenart.SONSTIGE


def test_amazon_bestimmungsland_aus_laenderdatei(amazon):
    laender = {
        p.bestellnummer: p.bestimmungsland
        for p in amazon.posten
        if p.art is Postenart.ERLOES
    }
    assert laender["302-1000002-0000002"] == "FR"
    assert laender["302-1000007-0000007"] == "CH"
    rabatt = next(p for p in amazon.posten if p.beschreibung == "Promotion/Principal")
    assert (rabatt.art, rabatt.betrag) == (Postenart.ERLOES, D("-3.00"))


def test_amazon_ohne_laenderdatei_kein_land():
    (abrechnung,) = _lies("amazon", "amazon_abrechnung_v2.txt")
    assert all(p.bestimmungsland is None for p in abrechnung.posten)


def test_amazon_falsche_datei():
    with pytest.raises(MarktplatzFormatError):
        MARKTPLATZ_IMPORTER["amazon"].lies(b"a\tb\n1\t2\n", "x.txt")


# --- eBay -----------------------------------------------------------------------


@pytest.fixture
def ebay():
    return _lies("ebay", "ebay_transaktionsbericht.csv")


def test_ebay_eine_abrechnung_je_auszahlung(ebay):
    assert [a.nummer for a in ebay] == ["6001234567", "6001234999"]
    erste, zweite = ebay
    assert erste.auszahlung == D("139.35")
    assert erste.auszahlungsdatum == date(2026, 8, 12)
    assert zweite.auszahlung == D("44.69")


def test_ebay_summenprobe(ebay):
    for abrechnung in ebay:
        assert abrechnung.summe() == D("0")  # Auszahlung als negativer Posten
        auszahlung = -abrechnung.summe(Postenart.AUSZAHLUNG)
        assert auszahlung == abrechnung.auszahlung


def test_ebay_bestandteile(ebay):
    erste = ebay[0]
    assert _summe(erste, Postenart.ERLOES) == D("237.90")
    assert _summe(erste, Postenart.ERSTATTUNG) == D("-24.90")
    assert _summe(erste, Postenart.GEBUEHR) == D("-73.65")
    laender = {
        p.bestellnummer: p.bestimmungsland
        for p in erste.posten
        if p.art is Postenart.ERLOES
    }
    assert laender["12-22222-22222"] == "FR"
    assert laender["12-44444-44444"] == "AT"
    etikett = next(p for p in erste.posten if "Versandetikett" in p.beschreibung)
    assert etikett.gebuehrenart is Gebuehrenart.VERSAND
    assert _summe(ebay[1], Postenart.EINBEHALT) == D("-20.00")


def test_ebay_noch_nicht_ausgezahlt_ist_hinweis(ebay):
    texte = [b.text for a in ebay for b in a.befunde]
    assert any("noch nicht ausgezahlt" in t for t in texte)
    assert not any(p.bestellnummer == "12-66666-66666" for a in ebay for p in a.posten)


def test_ebay_zeile_rechnet_nicht():
    inhalt = (FIXTURES / "ebay_transaktionsbericht.csv").read_bytes()
    kaputt = inhalt.replace(b"52,56", b"52,66")
    (erste, _zweite) = MARKTPLATZ_IMPORTER["ebay"].lies(kaputt, "x.csv")
    assert any(b.code == "zeile_rechnet_nicht" for b in erste.befunde)


# --- PayPal ---------------------------------------------------------------------


@pytest.fixture
def paypal():
    (abrechnung,) = _lies("paypal", "paypal_aktivitaeten.csv")
    return abrechnung


def test_paypal_konto_mit_guthaben(paypal):
    assert paypal.marktplatz == "paypal"
    assert (paypal.von, paypal.bis) == (date(2026, 8, 2), date(2026, 8, 20))
    assert paypal.anfangssaldo == D("100.00")
    assert paypal.endsaldo == D("112.36")
    eur = [p for p in paypal.posten if p.art is not Postenart.UMRECHNUNG]
    assert sum((p.betrag for p in eur), D("0")) == D("12.36")
    assert not [b for b in paypal.befunde if b.code == "saldensprung"]


def test_paypal_bestandteile(paypal):
    verkauf = [p for p in paypal.posten if p.referenz == "1AB23456CD7890123"]
    assert {(p.art, p.betrag) for p in verkauf} == {
        (Postenart.ERLOES, D("119.00")),
        (Postenart.GEBUEHR, D("-3.18")),
    }
    assert _summe(paypal, Postenart.ERSTATTUNG) == D("-119.00")
    assert _summe(paypal, Postenart.AUSZAHLUNG) == D("-150.00")
    assert _summe(paypal, Postenart.EINZAHLUNG) == D("50.00")
    assert _summe(paypal, Postenart.ZAHLUNG) == D("-45.00")
    fr = next(p for p in paypal.posten if p.referenz == "2BC34567DE8901234")
    assert fr.bestimmungsland == "FR"


def test_paypal_fremdwaehrung_zum_effektiven_kurs(paypal):
    usd = [p for p in paypal.posten if p.referenz == "5EF67890AB1234567"]
    assert {(p.art, p.betrag, p.waehrung) for p in usd} == {
        (Postenart.ERLOES, D("91.49"), "EUR"),
        (Postenart.GEBUEHR, D("-3.64"), "EUR"),
    }
    assert next(p for p in usd if p.art is Postenart.ERLOES).bestimmungsland == "US"
    assert all(
        p.waehrung == "USD" for p in paypal.posten if p.art is Postenart.UMRECHNUNG
    )


def test_paypal_ausstehendes_bleibt_draussen(paypal):
    assert not any(p.referenz == "9CD01234EF5678901" for p in paypal.posten)


def test_paypal_saldensprung_wird_befund():
    inhalt = (FIXTURES / "paypal_aktivitaeten.csv").read_bytes().decode("utf-8-sig")
    ohne = "\r\n".join(z for z in inhalt.split("\r\n") if "7AB89012CD3456789" not in z)
    (abrechnung,) = MARKTPLATZ_IMPORTER["paypal"].lies(ohne.encode(), "pp.csv")
    assert any(b.code == "saldensprung" for b in abrechnung.befunde)


# --- Shopify --------------------------------------------------------------------


@pytest.fixture
def shopify():
    (abrechnung,) = _lies(
        "shopify", "shopify_auszahlung.csv", "shopify_bestellungen.csv"
    )
    return abrechnung


def test_shopify_auszahlung(shopify):
    assert shopify.nummer == "87654321098"
    assert shopify.auszahlungsdatum == date(2026, 8, 21)
    assert shopify.auszahlung is None  # steht nicht in der Datei
    assert shopify.summe() == D("125.39")


def test_shopify_bestandteile(shopify):
    assert _summe(shopify, Postenart.ERLOES) == D("204.70")
    assert _summe(shopify, Postenart.GEBUEHR) == D("-4.81")
    assert _summe(shopify, Postenart.ERSTATTUNG) == D("-59.50")
    assert _summe(shopify, Postenart.SONSTIGES) == D("-15.00")
    assert all(
        p.gebuehrenart is Gebuehrenart.ZAHLUNG
        for p in shopify.posten
        if p.art is Postenart.GEBUEHR
    )
    laender = {
        p.bestellnummer: p.bestimmungsland
        for p in shopify.posten
        if p.art is Postenart.ERLOES
    }
    assert laender["#1002"] == "NL"
    assert any("noch nicht ausgezahlt" in b.text for b in shopify.befunde)


@pytest.mark.parametrize(
    ("typ", "brutto", "art"),
    [
        ("Website-Zahlung", "119.00", Postenart.ERLOES),
        ("Express-Checkout-Zahlung", "20.00", Postenart.ERLOES),
        ("Handyzahlung", "20.00", Postenart.ERLOES),
        ("Website Payment", "20.00", Postenart.ERLOES),
        ("Allgemeine Zahlung", "238.00", Postenart.ZAHLUNG),
        ("Allgemeine Zahlung", "-45.00", Postenart.ZAHLUNG),
        ("General Payment", "50.00", Postenart.ZAHLUNG),
        ("Rückzahlung", "-119.00", Postenart.ERSTATTUNG),
        ("Rückzahlung", "45.00", Postenart.ZAHLUNG),
        ("Payment Refund", "45.00", Postenart.ZAHLUNG),
        ("Einbehaltung für offene Konfliktlösung", "-119.00", Postenart.EINBEHALT),
        (
            "Rückbuchung einer Einbehaltung für offene Konfliktlösung",
            "119.00",
            Postenart.EINBEHALT,
        ),
        ("Reversal of General Account Hold", "10.00", Postenart.EINBEHALT),
        ("Rückbuchung", "-119.00", Postenart.SONSTIGES),
        ("Payment Reversal", "-10.00", Postenart.SONSTIGES),
        ("Chargeback", "-10.00", Postenart.SONSTIGES),
    ],
)
def test_paypal_typen(typ, brutto, art):
    from accounti.importers.paypal import _art, _Zeile

    zeile = _Zeile(
        nr=2,
        datum=date(2026, 9, 1),
        zeit="",
        name="",
        typ=typ,
        waehrung="EUR",
        brutto=D(brutto),
        gebuehr=D("0"),
        netto=D(brutto),
        code="X",
        zugehoerig="",
        guthaben=None,
        land=None,
        text=typ,
    )
    assert _art(zeile)[0] is art
