"""Abrechnung → Buchungen: alle Bestandteile einzeln, Summenprobe ohne Glätten."""

from decimal import Decimal
from pathlib import Path

import pytest

from accounti.importers.marktplatz import MARKTPLATZ_IMPORTER, lies_laenderdatei
from accounti.integrationen.buchung import (
    Buchungskontext,
    buche_abrechnung,
    ergaenze_auszahlung,
    summenprobe,
)
from accounti.integrationen.einstellungen import lade_integrationen
from accounti.models import BuchungStatus
from accounti.models.integrationen import Postenart, Schweregrad

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "marktplatz"
D = Decimal


def lies(markt, datei, laender=None, inhalt=None):
    roh = inhalt if inhalt is not None else (FIXTURES / datei).read_bytes()
    angaben = lies_laenderdatei((FIXTURES / laender).read_bytes()) if laender else None
    return MARKTPLATZ_IMPORTER[markt].lies(roh, datei, angaben)


def kontext(tmp_path, oss=True, **kw):
    return Buchungskontext(
        einstellungen=lade_integrationen(tmp_path / "keine.yaml"),
        oss_registriert=oss,
        **kw,
    )


def saldo(buchungen, konto):
    """Soll minus Haben auf einem Konto (Bruttobetrag der Buchung)."""
    summe = D("0")
    for b in buchungen:
        betrag = b.betrag_netto + (
            b.steuer_betrag
            if b.steuer_schluessel is not None and b.steuer_betrag
            else 0
        )
        if b.soll_konto == konto:
            summe += betrag
        if b.haben_konto == konto:
            summe -= betrag
    return summe


@pytest.fixture
def amazon():
    (a,) = lies("amazon", "amazon_abrechnung_v2.txt", "amazon_bestellungen.txt")
    ergaenze_auszahlung(a)
    return a


def test_auszahlung_wird_posten(amazon):
    (auszahlung,) = [p for p in amazon.posten if p.art is Postenart.AUSZAHLUNG]
    assert auszahlung.betrag == D("-209.85")
    assert auszahlung.datum.isoformat() == "2026-08-17"
    assert amazon.summe() == 0


def test_akzeptanz_1_abrechnungszeitraum_vollstaendig_gebucht(amazon, tmp_path):
    ergebnis = buche_abrechnung(amazon, kontext(tmp_path))
    b = ergebnis.buchungen
    # Vollständig: nach allen Bestandteilen steht auf dem Verrechnungskonto genau
    # die Auszahlung — sie gleicht der Bankabgleich aus.
    assert saldo(b, "1361") == D("209.85")
    # Erlöse je Bestellung, getrennt von Gebühren und Erstattungen
    erloese = [
        x for x in b if x.haben_konto in {"8400", "8320", "8321", "8326", "8120"}
    ]
    assert {x.beleg_nummer for x in erloese} == {
        f"302-100000{i}-000000{i}" for i in range(1, 8)
    }
    erstattungen = [x for x in b if x.soll_konto == "8320"]
    assert len(erstattungen) == 1
    assert erstattungen[0].betrag_netto == D("50.00")
    assert "Erstattung" in erstattungen[0].buchungstext
    # Gebühren je Art (brutto mit Vorsteuer), rückvergütete Provision eigens gebucht
    assert saldo(b, "4760") == D("58.55") + D("9.00") - D("9.00") + D("39.00")
    assert saldo(b, "4780") == D("23.55") + D("12.34")
    assert saldo(b, "4610") == D("25.00")
    rueck = [x for x in b if x.haben_konto == "4760"]
    assert [(x.betrag_netto, x.steuer_betrag) for x in rueck] == [
        (D("7.56"), D("1.44"))
    ]
    # Einbehalte und Ersatzleistung
    assert saldo(b, "1500") == D("25.00")
    (ersatz,) = [x for x in b if x.haben_konto == "2700"]
    assert ersatz.status is BuchungStatus.ZUR_PRUEFUNG
    # Inland 19 %: Steuer über den BU-Schlüssel
    (de,) = [x for x in b if x.beleg_nummer == "302-1000001-0000001"]
    assert (
        de.haben_konto,
        de.betrag_netto,
        de.steuer_betrag,
        de.steuer_schluessel,
    ) == (
        "8400",
        D("104.12"),
        D("19.78"),
        3,
    )
    assert not [f for f in ergebnis.befunde if f.schweregrad is Schweregrad.FEHLER]


def test_akzeptanz_1_buchungen_tragen_den_beleg(amazon, tmp_path):
    from uuid import uuid4

    amazon.beleg_id = uuid4()
    ergebnis = buche_abrechnung(amazon, kontext(tmp_path))
    assert {x.beleg_id for x in ergebnis.buchungen} == {amazon.beleg_id}


def test_akzeptanz_2_summenprobe_stimmt(amazon):
    assert summenprobe(amazon) == []


def test_akzeptanz_2_abweichung_wird_gemeldet_nicht_geglaettet(tmp_path):
    roh = (FIXTURES / "amazon_abrechnung_v2.txt").read_bytes()
    kaputt = roh.replace(b"\t209,85\t", b"\t209,86\t")
    (a,) = lies("amazon", "x", "amazon_bestellungen.txt", inhalt=kaputt)
    ergaenze_auszahlung(a)
    (befund,) = summenprobe(a)
    assert befund.code == "summe_abweichung"
    assert befund.schweregrad is Schweregrad.FEHLER
    assert "209,85" in befund.text and "209,86" in befund.text and "0,01" in befund.text
    ergebnis = buche_abrechnung(a, kontext(tmp_path))
    assert any(f.code == "summe_abweichung" for f in ergebnis.befunde)
    assert {x.status for x in ergebnis.buchungen} == {BuchungStatus.ZUR_PRUEFUNG}
    # nichts wird geglättet: kein Cent-Ausgleich, das Verrechnungskonto zeigt die
    # Einzelposten, die Auszahlung (209,86) bleibt um 0,01 daneben
    assert not [x for x in ergebnis.buchungen if x.betrag_netto == D("0.01")]
    assert saldo(ergebnis.buchungen, "1361") == D("209.85")


def test_ebay_buchung(tmp_path):
    erste, zweite = lies("ebay", "ebay_transaktionsbericht.csv")
    for a in (erste, zweite):
        ergaenze_auszahlung(a)
        assert summenprobe(a) == []
    b = buche_abrechnung(erste, kontext(tmp_path)).buchungen
    assert saldo(b, "1362") == D("139.35")
    b2 = buche_abrechnung(zweite, kontext(tmp_path)).buchungen
    assert saldo(b2, "1362") == D("44.69")
    assert saldo(b2, "1500") == D("20.00")  # Einbehalt wegen Zahlungsstreitfall


def test_shopify_buchung(tmp_path):
    (a,) = lies("shopify", "shopify_auszahlung.csv", "shopify_bestellungen.csv")
    ergaenze_auszahlung(a)
    (auszahlung,) = [p for p in a.posten if p.art is Postenart.AUSZAHLUNG]
    assert auszahlung.betrag == D("-125.39")  # Summe der Posten
    ergebnis = buche_abrechnung(a, kontext(tmp_path))
    assert saldo(ergebnis.buchungen, "1363") == D("125.39")
    assert saldo(ergebnis.buchungen, "4970") == D("4.81")
    (klaerung,) = [x for x in ergebnis.buchungen if x.soll_konto == "1590"]
    assert klaerung.status is BuchungStatus.ZUR_PRUEFUNG


def test_paypal_buchung_je_umsatz(tmp_path):
    from uuid import uuid4

    (a,) = lies("paypal", "paypal_aktivitaeten.csv")
    umsaetze = {p.referenz: uuid4() for p in a.posten if p.referenz}
    ergebnis = buche_abrechnung(a, kontext(tmp_path), umsaetze)
    b = ergebnis.buchungen
    # jede Buchung hängt an ihrem PayPal-Umsatz
    assert all(x.transaktion_id is not None for x in b)
    # PayPal-Konto bewegt sich um die gebuchten Umsätze; der Einkauf (−45,00) läuft
    # durch die normale Kontierung
    assert saldo(b, "1210") == D("12.36") + D("45.00")
    # Abbuchung und Bankgutschrift über Geldtransit
    assert saldo(b, "1360") == D("150.00") - D("50.00")
    verkauf = [x for x in b if x.transaktion_id == umsaetze["1AB23456CD7890123"]]
    assert {(x.soll_konto, x.haben_konto) for x in verkauf} == {
        ("1210", "8400"),
        ("4970", "1210"),
    }


def test_fremdwaehrung_ohne_kurs_bucht_nicht(tmp_path):
    roh = (FIXTURES / "amazon_abrechnung_v2.txt").read_bytes()
    (a,) = lies("amazon", "x", inhalt=roh.replace(b"\tEUR\t", b"\tGBP\t"))
    ergaenze_auszahlung(a)
    ergebnis = buche_abrechnung(a, kontext(tmp_path))
    assert ergebnis.buchungen == []
    assert [f.code for f in ergebnis.befunde] == ["fremdwaehrung_ohne_kurs"]


def test_fremdwaehrung_mit_kurs(tmp_path):
    roh = (FIXTURES / "amazon_abrechnung_v2.txt").read_bytes()
    gbp = roh.replace(b"\tEUR\t", b"\tGBP\t")
    (a,) = lies("amazon", "x", "amazon_bestellungen.txt", gbp)
    a.kurs = D("0.85")  # 0,85 GBP je EUR
    ergaenze_auszahlung(a)
    ergebnis = buche_abrechnung(a, kontext(tmp_path))
    (de,) = [x for x in ergebnis.buchungen if x.beleg_nummer == "302-1000001-0000001"]
    # 123,90 GBP / 0,85 = 145,76 EUR brutto
    assert de.betrag_netto + de.steuer_betrag == D("145.76")
    (auszahlung,) = [p for p in a.posten if p.art is Postenart.AUSZAHLUNG]
    assert auszahlung.betrag_eur is not None
    assert saldo(ergebnis.buchungen, "1361") == -auszahlung.betrag_eur


# --- Umsatzsteuer auf Gebühren ----------------------------------------------------


def gebuehr(buchungen, konto, text):
    (b,) = [
        x
        for x in buchungen
        if konto in (x.soll_konto, x.haben_konto) and text in x.buchungstext
    ]
    return b


def test_amazon_gebuehren_mit_deutscher_vorsteuer(amazon, tmp_path):
    """Seit 01.08.2024 berechnet Amazon EU S.à r.l. (Niederlassung Deutschland) die
    Verkaufs- und Versandgebühren mit 19 % deutscher USt — Vorsteuer, kein § 13b."""
    ergebnis = buche_abrechnung(amazon, kontext(tmp_path))
    b = ergebnis.buchungen
    verkauf = gebuehr(b, "4760", "Gebühren verkauf")
    # 67,55 brutto (Provisionen inkl. Rückerstattungsgebühr) = 56,76 + 10,79 VSt
    assert (verkauf.soll_konto, verkauf.haben_konto) == ("4760", "1361")
    assert (verkauf.betrag_netto, verkauf.steuer_betrag) == (D("56.76"), D("10.79"))
    assert verkauf.steuer_schluessel == 9
    assert verkauf.status is BuchungStatus.AUTO_GEBUCHT
    # zurückerstattete Provision mindert die Vorsteuer
    rueck = gebuehr(b, "4760", "Gebührenerstattung")
    assert (rueck.soll_konto, rueck.haben_konto) == ("1361", "4760")
    assert (rueck.betrag_netto, rueck.steuer_betrag, rueck.steuer_schluessel) == (
        D("7.56"),
        D("1.44"),
        9,
    )
    # Lager und Abo ebenfalls mit Vorsteuer
    lager = gebuehr(b, "4780", "Gebühren lager")
    assert (lager.betrag_netto, lager.steuer_betrag) == (D("10.37"), D("1.97"))
    # das Verrechnungskonto bewegt sich weiter um den Bruttobetrag
    assert saldo(b, "1361") == D("209.85")


def test_werbung_ohne_eingestellte_steuer_zur_pruefung(amazon, tmp_path):
    ergebnis = buche_abrechnung(amazon, kontext(tmp_path))
    werbung = gebuehr(ergebnis.buchungen, "4610", "Werbung")
    assert werbung.steuer_schluessel is None
    assert werbung.status is BuchungStatus.ZUR_PRUEFUNG
    (befund,) = [f for f in ergebnis.befunde if f.code == "ust_gebuehren_offen"]
    assert "Werbung" in befund.text and "ust_werbung" in befund.text


def test_ebay_gebuehren_ohne_einstellung_befund_je_abrechnung(tmp_path):
    erste, _ = lies("ebay", "ebay_transaktionsbericht.csv")
    ergaenze_auszahlung(erste)
    ergebnis = buche_abrechnung(erste, kontext(tmp_path))
    befunde = [f for f in ergebnis.befunde if f.code == "ust_gebuehren_offen"]
    assert len(befunde) == 1
    assert "ust_gebuehren" in befunde[0].text
    gebuehren = [x for x in ergebnis.buchungen if "Gebühr" in x.buchungstext]
    assert gebuehren
    assert {x.status for x in gebuehren} == {BuchungStatus.ZUR_PRUEFUNG}
    assert {x.steuer_schluessel for x in gebuehren} == {None}


def test_paypal_gebuehren_steuerfrei_ohne_befund(tmp_path):
    (a,) = lies("paypal", "paypal_aktivitaeten.csv")
    ergebnis = buche_abrechnung(a, kontext(tmp_path))
    assert not [f for f in ergebnis.befunde if f.code == "ust_gebuehren_offen"]
    gebuehren = [x for x in ergebnis.buchungen if x.soll_konto == "4970"]
    assert {(x.steuer_schluessel, x.status) for x in gebuehren} == {
        (None, BuchungStatus.AUTO_GEBUCHT)
    }


def test_gebuehren_13b_mit_eingestelltem_schluessel(amazon, tmp_path):
    pfad = tmp_path / "c.yaml"
    pfad.write_text(
        "integrationen:\n  marktplaetze:\n    amazon:\n      ust_gebuehren: 13b\n"
        "      bu_gebuehren: 94\n      ust_werbung: ohne\n",
        encoding="utf-8",
    )
    k = Buchungskontext(einstellungen=lade_integrationen(pfad), oss_registriert=True)
    ergebnis = buche_abrechnung(amazon, k)
    verkauf = gebuehr(ergebnis.buchungen, "4760", "Gebühren verkauf")
    assert (verkauf.betrag_netto, verkauf.steuer_schluessel) == (D("67.55"), 94)
    assert verkauf.steuer_betrag is None
    werbung = gebuehr(ergebnis.buchungen, "4610", "Werbung")
    assert werbung.status is BuchungStatus.AUTO_GEBUCHT
    assert not [f for f in ergebnis.befunde if f.code == "ust_gebuehren_offen"]


def test_gebuehren_13b_ohne_schluessel_zur_pruefung(amazon, tmp_path):
    pfad = tmp_path / "c.yaml"
    pfad.write_text(
        "integrationen:\n  marktplaetze:\n    amazon:\n      ust_gebuehren: 13b\n",
        encoding="utf-8",
    )
    k = Buchungskontext(einstellungen=lade_integrationen(pfad), oss_registriert=True)
    ergebnis = buche_abrechnung(amazon, k)
    verkauf = gebuehr(ergebnis.buchungen, "4760", "Gebühren verkauf")
    assert verkauf.status is BuchungStatus.ZUR_PRUEFUNG
    assert any(f.code == "ust_gebuehren_offen" for f in ergebnis.befunde)
