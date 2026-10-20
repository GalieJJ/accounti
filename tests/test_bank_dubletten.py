from datetime import date
from decimal import Decimal

from accounti.bank.dubletten import mit_schluessel
from accounti.models import Transaktion, TransaktionQuelle


def tx(betrag="-5.00", tag=12, zweck="PARKHAUS ALTSTADT", **kw):
    return Transaktion(
        datum=date(2026, 3, tag),
        betrag=Decimal(betrag),
        verwendungszweck=zweck,
        gegenkonto_name=kw.pop("name", "APCOA"),
        quelle=TransaktionQuelle.BANK,
        rohtext="",
        **kw,
    )


def _schluessel(umsaetze, konto="DE12"):
    return [t.dublettenschluessel for t in mit_schluessel(umsaetze, konto)]


def test_gleiche_umsaetze_am_selben_tag_bleiben_zwei():
    a, b = _schluessel([tx(), tx()])
    assert a and b and a != b


def test_derselbe_abruf_zweimal_ergibt_dieselben_schluessel():
    assert _schluessel([tx(), tx(), tx(betrag="-7")]) == _schluessel(
        [tx(), tx(), tx(betrag="-7")]
    )


def test_ueberlappung_mit_zusaetzlichem_gleichen_umsatz():
    erster = _schluessel([tx()])
    zweiter = _schluessel([tx(tag=11), tx(), tx()])
    assert erster[0] in zweiter
    assert len(set(zweiter)) == 3


def test_schreibweise_im_verwendungszweck_egal():
    assert _schluessel([tx(zweck="Parkhaus  Altstadt ")]) == _schluessel(
        [tx(zweck="PARKHAUS ALTSTADT")]
    )


def test_konto_gehoert_zum_schluessel():
    assert _schluessel([tx()], "DE12") != _schluessel([tx()], "DE34")


def test_unterscheidende_merkmale():
    basis = _schluessel([tx()])
    assert _schluessel([tx(tag=13)]) != basis
    assert _schluessel([tx(betrag="-5.01")]) != basis
    assert _schluessel([tx(name="Q-Park")]) != basis
    assert _schluessel([tx(gegenkonto_iban="DE02120300000000202051")]) != basis


def test_original_bleibt_unveraendert():
    original = tx()
    (neu,) = mit_schluessel([original], "DE12")
    assert original.dublettenschluessel is None and neu.dublettenschluessel


def test_ohne_bankreferenz_bleibt_der_schluessel_wie_bisher():
    import hashlib

    basis = "DE12|2026-03-12|-5|parkhaus altstadt||apcoa"
    erwartet = hashlib.sha256(f"{basis}|1".encode()).hexdigest()
    assert _schluessel([tx()]) == [erwartet]
    assert _schluessel([tx(quelle_referenz="NONREF")]) == [erwartet]
    assert _schluessel([tx(quelle_referenz=" notprovided ")]) == [erwartet]


def test_bankreferenz_unterscheidet_gleich_aussehende_umsaetze():
    a, b = tx(quelle_referenz="2026031300003"), tx(quelle_referenz="2026031300004")
    hin = _schluessel([a, b])
    zurueck = _schluessel([b, a])
    assert len(set(hin)) == 2
    assert set(hin) == set(zurueck)  # Reihenfolge des Abrufs egal
    # nur einer der beiden kommt im nächsten Abruf noch einmal: keine neue Dublette
    assert _schluessel([b]) == [hin[1]]
    assert _schluessel([tx()]) not in ([hin[0]], [hin[1]])
