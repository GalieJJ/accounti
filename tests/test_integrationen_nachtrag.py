"""Eine Auszahlung über mehrere Berichte, wiederholte Exporte, Sammelabgleich.

Eine schon bekannte Abrechnung wird nicht pauschal übersprungen: Posten, die der neue
Bericht zusätzlich enthält, werden nachgebucht, Summenprobe und Bankabgleich laufen
über die ganze Abrechnung neu. Befunde, die sich dadurch erledigen, bleiben sichtbar,
bestimmen aber den Status nicht mehr.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import init_db, session_factory
from accounti.db.repo_integrationen import lade_abrechnungen
from accounti.db.repository import (
    lade_buchungen,
    lade_transaktionen,
    speichere_transaktion,
)
from accounti.integrationen.auszahlung import gleiche_auszahlungen_ab
from accounti.integrationen.einstellungen import lade_integrationen
from accounti.integrationen.lauf import Kontext, importiere
from accounti.konfiguration import Buchhaltung
from accounti.models import BuchungStatus, Transaktion, TransaktionQuelle
from accounti.models.integrationen import AbrechnungStatus, Postenart, Schweregrad
from tests.marktplatz_hilfe import FIXTURES, ebay_bericht, paypal_bericht

D = Decimal


@pytest.fixture
def umgebung(tmp_path):
    engine, make = session_factory(f"sqlite:///{tmp_path / 'n.db'}")
    init_db(engine)
    pfad = tmp_path / "c.yaml"
    pfad.write_text(
        "integrationen:\n  marktplaetze:\n    ebay:\n      ust_gebuehren: ohne\n",
        encoding="utf-8",
    )
    kontext = Kontext(
        einstellungen=lade_integrationen(pfad),
        buchhaltung=Buchhaltung(),
        oss_registriert=True,
    )
    with make() as s:
        yield s, BelegArchiv(tmp_path / "archiv"), kontext


def bank(session, datum, betrag, zweck):
    tx = Transaktion(
        datum=datum,
        betrag=D(betrag),
        verwendungszweck=zweck,
        quelle=TransaktionQuelle.BANK,
        rohtext=zweck,
    )
    speichere_transaktion(session, tx)
    session.flush()
    return tx


def saldo(buchungen, konto):
    summe = D("0")
    for b in buchungen:
        betrag = b.betrag_netto + (b.steuer_betrag if b.steuer_schluessel else 0)
        summe += betrag if b.soll_konto == konto else 0
        summe -= betrag if b.haben_konto == konto else 0
    return summe


AUGUST = ebay_bericht(
    ("30.08.2026", "Bestellung", "12-1", "Deutschland", "100,00", "P1", ""),
)
SEPTEMBER = ebay_bericht(
    ("01.09.2026", "Bestellung", "12-2", "Deutschland", "50,00", "P1", ""),
    ("02.09.2026", "Auszahlung", "", "", "-150,00", "P1", "02.09.2026"),
)


def test_auszahlung_ueber_zwei_berichte(umgebung):
    s, archiv, kontext = umgebung
    eingang = bank(s, date(2026, 9, 3), "150.00", "EBAY AUSZAHLUNG P1")
    (erst,) = importiere(s, archiv, kontext, "ebay", AUGUST, "aug.csv")
    assert erst.neu and erst.buchungen == 1
    # die Auszahlungszeile kommt erst mit dem nächsten Bericht: kein erfundener
    # Auszahlungsbetrag, also auch kein falscher Abweichungsbefund
    a = erst.abrechnung
    assert not [p for p in a.posten if p.art is Postenart.AUSZAHLUNG]
    assert a.status is AbrechnungStatus.GEBUCHT
    assert [b.code for b in a.befunde] == ["auszahlung_folgt"]

    (zweit,) = importiere(s, archiv, kontext, "ebay", SEPTEMBER, "sep.csv")
    assert not zweit.neu
    assert (zweit.nachgetragen, zweit.buchungen) == (2, 1)
    (abrechnung,) = lade_abrechnungen(s)
    assert abrechnung.status is AbrechnungStatus.ABGEGLICHEN
    assert abrechnung.auszahlung == D("150.00")
    buchungen = lade_buchungen(s)
    assert {b.beleg_nummer for b in buchungen if b.haben_konto == "8400"} == {
        "12-1",
        "12-2",
    }
    assert eingang.id in {b.transaktion_id for b in buchungen}
    assert saldo(buchungen, "1362") == 0
    assert any(b.code == "nachtrag" for b in abrechnung.befunde)


def test_auszahlung_ueber_zwei_berichte_umgekehrte_reihenfolge(umgebung):
    s, archiv, kontext = umgebung
    bank(s, date(2026, 9, 3), "150.00", "EBAY AUSZAHLUNG P1")
    (erst,) = importiere(s, archiv, kontext, "ebay", SEPTEMBER, "sep.csv")
    # 50 € Posten, 150 € Auszahlung: solange der August fehlt, ist das ein Fehler
    assert erst.abrechnung.status is AbrechnungStatus.ABWEICHUNG
    (zweit,) = importiere(s, archiv, kontext, "ebay", AUGUST, "aug.csv")
    assert (zweit.nachgetragen, zweit.buchungen) == (1, 1)
    (abrechnung,) = lade_abrechnungen(s)
    # die Summenprobe stimmt jetzt; der alte Befund ist erledigt, nicht gelöscht
    (alt,) = [b for b in abrechnung.befunde if b.code == "summe_abweichung"]
    assert alt.erledigt
    assert abrechnung.status is AbrechnungStatus.ABGEGLICHEN
    assert saldo(lade_buchungen(s), "1362") == 0


def test_gleicher_bericht_nochmals_bucht_nichts(umgebung):
    s, archiv, kontext = umgebung
    importiere(s, archiv, kontext, "ebay", SEPTEMBER, "sep.csv")
    anzahl = len(lade_buchungen(s))
    neu_gespeichert = SEPTEMBER.replace(b"\r\n", b"\n")  # andere Datei, gleiche Posten
    (ergebnis,) = importiere(s, archiv, kontext, "ebay", neu_gespeichert, "s2.csv")
    assert (ergebnis.neu, ergebnis.nachgetragen) == (False, 0)
    assert len(lade_buchungen(s)) == anzahl


NUR_P1 = (
    ("10.08.2026", "Bestellung", "12-1", "Deutschland", "100,00", "P1", ""),
    ("12.08.2026", "Auszahlung", "", "", "-100,00", "P1", "12.08.2026"),
)


def test_gleicher_bericht_mit_anderem_beschreibungstext_bucht_nichts(umgebung):
    """eBay lässt die Spalten konfigurieren: derselbe Bericht mit anderem
    Freitext ist keine neue Bestellung und keine zweite Auszahlung."""
    s, archiv, kontext = umgebung
    bank(s, date(2026, 8, 13), "100.00", "EBAY AUSZAHLUNG P1")
    (erst,) = importiere(s, archiv, kontext, "ebay", ebay_bericht(*NUR_P1), "e.csv")
    assert erst.abrechnung.status is AbrechnungStatus.ABGEGLICHEN
    anzahl = len(lade_buchungen(s))
    anders = ebay_bericht(*NUR_P1, beschreibung="Verkauf")
    (zweit,) = importiere(s, archiv, kontext, "ebay", anders, "e2.csv")
    assert (zweit.neu, zweit.nachgetragen, zweit.buchungen) == (False, 0, 0)
    assert len(lade_buchungen(s)) == anzahl
    (abrechnung,) = lade_abrechnungen(s)
    assert abrechnung.auszahlung == D("100.00")
    assert abrechnung.status is AbrechnungStatus.ABGEGLICHEN


def test_zweite_auszahlungszeile_ist_widerspruch(umgebung):
    """Eine Auszahlungsnummer hat genau eine Auszahlungszeile. Bringt ein Bericht
    eine andere, wird nichts nachgetragen und nichts summiert."""
    s, archiv, kontext = umgebung
    bank(s, date(2026, 8, 13), "100.00", "EBAY AUSZAHLUNG P1")
    importiere(s, archiv, kontext, "ebay", ebay_bericht(*NUR_P1), "e.csv")
    anzahl = len(lade_buchungen(s))
    widerspruch = ebay_bericht(
        ("10.08.2026", "Bestellung", "12-1", "Deutschland", "100,00", "P1", ""),
        ("11.08.2026", "Bestellung", "12-9", "Deutschland", "20,00", "P1", ""),
        ("12.08.2026", "Auszahlung", "", "", "-120,00", "P1", "12.08.2026"),
    )
    (ergebnis,) = importiere(s, archiv, kontext, "ebay", widerspruch, "e2.csv")
    assert (ergebnis.neu, ergebnis.nachgetragen, ergebnis.buchungen) == (False, 0, 0)
    assert ergebnis.widerspruch is not None
    assert len(lade_buchungen(s)) == anzahl
    (abrechnung,) = lade_abrechnungen(s)
    assert abrechnung.auszahlung == D("100.00")
    assert len([p for p in abrechnung.posten if p.art is Postenart.AUSZAHLUNG]) == 1
    (befund,) = [b for b in abrechnung.befunde if b.code == "auszahlung_doppelt"]
    assert befund.schweregrad is Schweregrad.FEHLER
    assert "e2.csv" in befund.text and "120,00" in befund.text
    assert abrechnung.status is AbrechnungStatus.ABWEICHUNG


def test_auseinanderlaufender_posten_bei_bekannter_auszahlungszeile(umgebung):
    """Ein Posten, den der Fingerabdruck nicht wiedererkennt (hier: ohne
    Bestellnummer), ist neu — die bekannte Auszahlungszeile hält die Summe fest,
    die Summenprobe meldet die Doppelung und der Nachtrag geht zur Prüfung."""
    s, archiv, kontext = umgebung
    importiere(s, archiv, kontext, "ebay", ebay_bericht(*NUR_P1), "e.csv")
    ohne_nummer = ebay_bericht(
        ("10.08.2026", "Bestellung", "", "Deutschland", "100,00", "P1", ""),
        NUR_P1[1],
    )
    (ergebnis,) = importiere(s, archiv, kontext, "ebay", ohne_nummer, "e2.csv")
    assert ergebnis.nachgetragen == 1 and ergebnis.widerspruch is None
    (abrechnung,) = lade_abrechnungen(s)
    assert abrechnung.auszahlung == D("100.00")
    assert abrechnung.status is AbrechnungStatus.ABWEICHUNG
    assert any(b.code == "summe_abweichung" for b in abrechnung.offene_befunde)
    (neu,) = [b for b in lade_buchungen(s) if b.beleg_nummer == "P1"]
    assert neu.status is BuchungStatus.ZUR_PRUEFUNG


def test_nachtrag_uebernimmt_die_befunde_seiner_posten(umgebung):
    s, archiv, kontext = umgebung
    importiere(s, archiv, kontext, "ebay", AUGUST, "aug.csv")
    september = ebay_bericht(
        ("01.09.2026", "Bestellung", "12-2", "Deutschland", "50,00", "P1", ""),
        ("01.09.2026", "Korrektur", "", "", "5,00", "P1", ""),
        ("02.09.2026", "Auszahlung", "", "", "-155,00", "P1", "02.09.2026"),
    )
    (ergebnis,) = importiere(s, archiv, kontext, "ebay", september, "sep.csv")
    assert ergebnis.nachgetragen == 3
    (abrechnung,) = lade_abrechnungen(s)
    (befund,) = [b for b in abrechnung.befunde if b.code == "unbekannter_posten"]
    assert "Korrektur" in befund.text


def test_nachtrag_nach_bankabgleich_ist_fehler(umgebung):
    """Ist die (aus den Posten gebildete) Auszahlung schon gegen die Bank
    abgeglichen, passt ein zusätzlicher Posten nicht mehr dazu."""
    s, archiv, kontext = umgebung
    roh = (FIXTURES / "shopify_auszahlung.csv").read_text(encoding="utf-8")
    bank(s, date(2026, 8, 22), "125.39", "SHOPIFY PAYOUT")
    (erst,) = importiere(s, archiv, kontext, "shopify", roh.encode(), "s.csv")
    assert erst.abrechnung.status is AbrechnungStatus.ABGEGLICHEN
    mehr = roh + (
        "2026-08-20 18:00:00 +0200,charge,#1005,visa,online,paid,2026-08-21,"
        "87654321098,2026-08-21,10.00,0.50,9.50,c1005,card,10.00,EUR,EUR\n"
    )
    (zweit,) = importiere(s, archiv, kontext, "shopify", mehr.encode(), "s2.csv")
    assert zweit.nachgetragen == 2  # Verkauf und Gebühr
    (abrechnung,) = lade_abrechnungen(s)
    assert abrechnung.status is AbrechnungStatus.ABWEICHUNG
    (befund,) = [
        b for b in abrechnung.befunde if b.code == "summe_abweichung" and not b.erledigt
    ]
    assert "125,39" in befund.text and "134,89" in befund.text
    neue = [b for b in lade_buchungen(s) if b.beleg_nummer == "#1005"]
    assert neue and {b.status for b in neue} == {BuchungStatus.ZUR_PRUEFUNG}


def test_paypal_export_mit_gleichem_zeitraum(umgebung):
    """Zweimal 01.–31.08. exportiert (am 31.08. und nach Monatsende): gleiche
    Nummer, aber eine Zeile mehr — sie wird übernommen."""
    s, archiv, kontext = umgebung

    def zeile(datum, code, guthaben, brutto="10,00"):
        return {
            "Datum": datum,
            "Uhrzeit": "10:00:00",
            "Name": "Kunde",
            "Typ": "Website-Zahlung",
            "Brutto": brutto,
            "Netto": brutto,
            "Transaktionscode": code,
            "Guthaben": guthaben,
            "Land": "Deutschland",
        }

    frueh = paypal_bericht(
        zeile("02.08.2026", "AAA0000000000001", "10,00"),
        zeile("20.08.2026", "AAA0000000000002", "20,00"),
    )
    spaet = paypal_bericht(
        zeile("02.08.2026", "AAA0000000000001", "10,00"),
        zeile("20.08.2026", "AAA0000000000003", "30,00", "10,00"),
        zeile("20.08.2026", "AAA0000000000002", "20,00"),
    )
    (erst,) = importiere(s, archiv, kontext, "paypal", frueh, "pp1.csv")
    (zweit,) = importiere(s, archiv, kontext, "paypal", spaet, "pp2.csv")
    assert erst.abrechnung.nummer == "PayPal 2026-08-02 bis 2026-08-20"
    assert zweit.neu and zweit.umsaetze == 1
    assert zweit.abrechnung.nummer == "PayPal 2026-08-02 bis 2026-08-20 (2)"
    pp = [t for t in lade_transaktionen(s) if t.quelle is TransaktionQuelle.PAYPAL]
    assert len(pp) == 3


# --- Sammelabgleich -------------------------------------------------------------


ZWEI_AUSZAHLUNGEN = ebay_bericht(
    ("10.08.2026", "Bestellung", "12-1", "Deutschland", "100,00", "P1", ""),
    ("12.08.2026", "Auszahlung", "", "", "-100,00", "P1", "12.08.2026"),
    ("13.08.2026", "Bestellung", "12-2", "Deutschland", "50,00", "P2", ""),
    ("14.08.2026", "Auszahlung", "", "", "-50,00", "P2", "14.08.2026"),
)


def test_sammelabgleich_ohne_fehlalarm(umgebung):
    """Der Umsatz, den P1 eben bekommen hat, ist für P2 keine Abweichung."""
    s, archiv, kontext = umgebung
    importiere(s, archiv, kontext, "ebay", ZWEI_AUSZAHLUNGEN, "e.csv")
    bank(s, date(2026, 8, 13), "100.00", "EBAY AUSZAHLUNG P1")
    ergebnisse = gleiche_auszahlungen_ab(s, kontext)
    assert [e.befund for e in ergebnisse] == [None, None]
    status = {a.nummer: a.status for a in lade_abrechnungen(s)}
    assert status == {
        "P1": AbrechnungStatus.ABGEGLICHEN,
        "P2": AbrechnungStatus.GEBUCHT,
    }
    eingang = bank(s, date(2026, 8, 15), "50.00", "EBAY AUSZAHLUNG P2")
    (ergebnis,) = gleiche_auszahlungen_ab(s, kontext)
    assert ergebnis.transaktion is not None and ergebnis.transaktion.id == eingang.id
    (p2,) = [a for a in lade_abrechnungen(s) if a.nummer == "P2"]
    assert p2.status is AbrechnungStatus.ABGEGLICHEN
    (buchung,) = [b for b in lade_buchungen(s) if b.transaktion_id == eingang.id]
    assert buchung.status is BuchungStatus.AUTO_GEBUCHT


def test_sammelabgleich_unabhaengig_von_der_reihenfolge(umgebung):
    s, archiv, kontext = umgebung
    importiere(s, archiv, kontext, "ebay", ZWEI_AUSZAHLUNGEN, "e.csv")
    bank(s, date(2026, 8, 13), "100.00", "EBAY AUSZAHLUNG P1")
    rueckwaerts = list(reversed(lade_abrechnungen(s)))
    ergebnisse = gleiche_auszahlungen_ab(s, kontext, rueckwaerts)
    assert [e.befund for e in ergebnisse] == [None, None]


def test_abweichung_erledigt_sich_mit_dem_passenden_umsatz(umgebung):
    """Ein Abweichungsbefund hält den Status nicht fest, wenn danach der exakt
    passende Bankumsatz kommt."""
    s, archiv, kontext = umgebung
    bank(s, date(2026, 8, 13), "99.00", "EBAY AUSZAHLUNG P1")
    kontext = replace(kontext)
    nur_p1 = ebay_bericht(
        ("10.08.2026", "Bestellung", "12-1", "Deutschland", "100,00", "P1", ""),
        ("12.08.2026", "Auszahlung", "", "", "-100,00", "P1", "12.08.2026"),
    )
    (erst,) = importiere(s, archiv, kontext, "ebay", nur_p1, "e.csv")
    assert erst.abrechnung.status is AbrechnungStatus.ABWEICHUNG
    bank(s, date(2026, 8, 14), "100.00", "EBAY AUSZAHLUNG P1")
    gleiche_auszahlungen_ab(s, kontext)
    (a,) = lade_abrechnungen(s)
    assert a.status is AbrechnungStatus.ABGEGLICHEN
    (befund,) = [b for b in a.befunde if b.code == "auszahlung_abweichung"]
    assert befund.erledigt
