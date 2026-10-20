"""Importlauf: Bericht archivieren, buchen, Auszahlung gegen die Bank abgleichen."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import init_db, session_factory
from accounti.db.repo_integrationen import lade_abrechnungen
from accounti.db.repository import (
    lade_belege,
    lade_buchungen,
    lade_transaktionen,
    speichere_buchung,
    speichere_transaktion,
)
from accounti.importers.marktplatz import lies_laenderdatei
from accounti.integrationen.auszahlung import gleiche_auszahlungen_ab
from accounti.integrationen.einstellungen import lade_integrationen
from accounti.integrationen.lauf import IntegrationError, Kontext, importiere
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Belegart,
    Buchungssatz,
    BuchungStatus,
    Transaktion,
    TransaktionQuelle,
)
from accounti.models.integrationen import AbrechnungStatus, Postenart
from accounti.opos.zahlungslauf import offene_transaktionen

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "marktplatz"
D = Decimal


@pytest.fixture
def umgebung(tmp_path):
    engine, make = session_factory(f"sqlite:///{tmp_path / 'm.db'}")
    init_db(engine)
    kontext = Kontext(
        einstellungen=lade_integrationen(tmp_path / "keine.yaml"),
        buchhaltung=Buchhaltung(),
        oss_registriert=True,
    )
    with make() as s:
        yield s, BelegArchiv(tmp_path / "archiv"), kontext


def bank(session, datum, betrag, zweck, name="", quelle=TransaktionQuelle.BANK):
    tx = Transaktion(
        datum=datum,
        betrag=D(betrag),
        verwendungszweck=zweck,
        gegenkonto_name=name,
        quelle=quelle,
        rohtext=zweck,
    )
    speichere_transaktion(session, tx)
    session.flush()
    return tx


def amazon(session, archiv, kontext, inhalt=None):
    roh = inhalt or (FIXTURES / "amazon_abrechnung_v2.txt").read_bytes()
    laender = lies_laenderdatei((FIXTURES / "amazon_bestellungen.txt").read_bytes())
    return importiere(
        session, archiv, kontext, "amazon", roh, "abrechnung.txt", laender=laender
    )


def saldo(buchungen, konto):
    summe = D("0")
    for b in buchungen:
        betrag = b.betrag_netto + (
            b.steuer_betrag
            if b.steuer_schluessel is not None and b.steuer_betrag
            else 0
        )
        summe += betrag if b.soll_konto == konto else 0
        summe -= betrag if b.haben_konto == konto else 0
    return summe


def test_import_archiviert_bucht_und_gleicht_ab(umgebung):
    s, archiv, kontext = umgebung
    eingang = bank(
        s, date(2026, 8, 18), "209.85", "AMAZON PAYMENTS EUROPE S.C.A. 11223344556"
    )
    (ergebnis,) = amazon(s, archiv, kontext)
    assert ergebnis.neu
    (beleg,) = lade_belege(s)
    assert (beleg.belegart, beleg.kanal) == (Belegart.SONSTIGES, "marktplatz")
    assert beleg.brutto is None  # kein Vorschlag im Bankabgleich
    assert archiv.enthaelt(beleg.datei_hash)
    buchungen = lade_buchungen(s)
    assert {b.beleg_id for b in buchungen} == {beleg.id}
    # Auszahlung: Bank an Verrechnungskonto, am Bankumsatz — Verrechnungskonto glatt
    (auszahlung,) = [b for b in buchungen if b.transaktion_id == eingang.id]
    assert (auszahlung.soll_konto, auszahlung.haben_konto) == ("1200", "1361")
    assert saldo(buchungen, "1361") == 0
    assert eingang.id not in {t.id for t in offene_transaktionen(s, True)}
    (abrechnung,) = lade_abrechnungen(s)
    assert abrechnung.status is AbrechnungStatus.ABGEGLICHEN


def test_akzeptanz_2_auszahlung_weicht_von_der_bank_ab(umgebung):
    s, archiv, kontext = umgebung
    bank(s, date(2026, 8, 18), "209.80", "AMAZON PAYMENTS EUROPE S.C.A. 11223344556")
    (ergebnis,) = amazon(s, archiv, kontext)
    assert [a.befund.code for a in ergebnis.abgleich if a.befund] == [
        "auszahlung_abweichung"
    ]
    (abrechnung,) = lade_abrechnungen(s)
    assert abrechnung.status is AbrechnungStatus.ABWEICHUNG
    befund = next(b for b in abrechnung.befunde if b.code == "auszahlung_abweichung")
    assert "209,80" in befund.text and "209,85" in befund.text
    # nichts geglättet: keine Bankbuchung, keine Differenzbuchung
    buchungen = lade_buchungen(s)
    assert not [b for b in buchungen if b.transaktion_id is not None]
    assert saldo(buchungen, "1361") == D("209.85")


def test_zweiter_import_bucht_nichts_doppelt(umgebung):
    s, archiv, kontext = umgebung
    amazon(s, archiv, kontext)
    anzahl = len(lade_buchungen(s))
    (ergebnis,) = amazon(s, archiv, kontext)
    assert not ergebnis.neu
    assert len(lade_buchungen(s)) == anzahl
    assert len(lade_abrechnungen(s)) == 1


def test_abgleich_spaeter(umgebung):
    s, archiv, kontext = umgebung
    (ergebnis,) = amazon(s, archiv, kontext)
    assert ergebnis.abrechnung.status is AbrechnungStatus.GEBUCHT
    eingang = bank(s, date(2026, 8, 19), "209.85", "Gutschrift", "AMAZON EU SARL")
    (abgleich,) = gleiche_auszahlungen_ab(s, kontext)
    assert abgleich.transaktion is not None and abgleich.transaktion.id == eingang.id
    assert lade_abrechnungen(s)[0].status is AbrechnungStatus.ABGEGLICHEN
    assert gleiche_auszahlungen_ab(s, kontext) == []  # nichts mehr offen


def test_gleicher_betrag_zweimal_wird_nicht_geraten(umgebung):
    s, archiv, kontext = umgebung
    bank(s, date(2026, 8, 18), "209.85", "AMAZON PAYMENTS 1")
    bank(s, date(2026, 8, 19), "209.85", "AMAZON PAYMENTS 2")
    (ergebnis,) = amazon(s, archiv, kontext)
    assert [a.befund.code for a in ergebnis.abgleich if a.befund] == [
        "auszahlung_mehrdeutig"
    ]


def test_auszahlung_schon_per_regel_gebucht(umgebung):
    s, archiv, kontext = umgebung
    tx = bank(s, date(2026, 8, 18), "209.85", "AMAZON PAYMENTS EUROPE 11223344556")
    speichere_buchung(
        s,
        Buchungssatz(
            transaktion_id=tx.id,
            datum=tx.datum,
            soll_konto="1200",
            haben_konto="8400",
            betrag_netto=D("176.34"),
            steuer_schluessel=3,
            steuer_betrag=D("33.51"),
            buchungstext="Amazon-Auszahlung",
            status=BuchungStatus.AUTO_GEBUCHT,
        ),
    )
    (ergebnis,) = amazon(s, archiv, kontext)
    (befund,) = [a.befund for a in ergebnis.abgleich if a.befund]
    assert befund.code == "auszahlung_anderweitig_gebucht"
    assert "korrigiere" in befund.text


def test_fehlende_laenderdatei_erloese_zur_pruefung(umgebung):
    s, archiv, kontext = umgebung
    roh = (FIXTURES / "amazon_abrechnung_v2.txt").read_bytes()
    (ergebnis,) = importiere(s, archiv, kontext, "amazon", roh, "a.txt")
    assert any(b.code == "land_fehlt" for b in ergebnis.abrechnung.befunde)
    erloese = [b for b in lade_buchungen(s) if b.haben_konto == "8200"]
    assert len(erloese) == 7
    assert {b.status for b in erloese} == {BuchungStatus.ZUR_PRUEFUNG}


def test_unbekannter_marktplatz(umgebung):
    s, archiv, kontext = umgebung
    with pytest.raises(IntegrationError, match="otto"):
        importiere(s, archiv, kontext, "otto", b"x", "x.csv")


# --- PayPal als Konto ------------------------------------------------------------


def paypal(session, archiv, kontext, inhalt=None, name="pp.csv"):
    roh = inhalt or (FIXTURES / "paypal_aktivitaeten.csv").read_bytes()
    return importiere(session, archiv, kontext, "paypal", roh, name)


def test_paypal_wird_gefuehrt_wie_ein_bankkonto(umgebung):
    s, archiv, kontext = umgebung
    abbuchung = bank(s, date(2026, 8, 13), "150.00", "PAYPAL EUROPE ABBUCHUNG")
    aufladung = bank(s, date(2026, 8, 19), "-50.00", "PAYPAL EUROPE GUTHABEN")
    (ergebnis,) = paypal(s, archiv, kontext)
    assert ergebnis.umsaetze == 7  # saldenwirksame EUR-Zeilen
    pp = [t for t in lade_transaktionen(s) if t.quelle is TransaktionQuelle.PAYPAL]
    assert {t.sachkonto for t in pp} == {"1210"}
    assert sum((t.betrag for t in pp), D("0")) == D("12.36")
    # der Einkauf bleibt für opos/classify, alles andere ist gebucht
    pp_ids = {t.id for t in pp}
    offen = [t for t in offene_transaktionen(s, True) if t.id in pp_ids]
    assert [t.betrag for t in offen] == [D("-45.00")]
    buchungen = lade_buchungen(s)
    assert saldo(buchungen, "1360") == 0  # Geldtransit glatt
    assert {abbuchung.id, aufladung.id} <= {b.transaktion_id for b in buchungen}
    assert lade_abrechnungen(s)[0].status is AbrechnungStatus.ABGEGLICHEN


def test_paypal_ueberlappender_export(umgebung):
    s, archiv, kontext = umgebung
    paypal(s, archiv, kontext)
    anzahl = len(lade_buchungen(s))
    roh = (FIXTURES / "paypal_aktivitaeten.csv").read_bytes().decode("utf-8-sig")
    neu = roh.replace("20.08.2026", "21.08.2026")  # anderer Export, gleiche Zeilen
    neu += (
        '"22.08.2026","10:00:00","Europe/Berlin","Kunde Fuenf","Website-Zahlung",'
        '"Abgeschlossen","EUR","10,00","-0,60","9,40","","","XNEU0000000000001"'
        + ',""' * 16
        + ',"121,76"'
        + ',""' * 11
        + "\r\n"
    )
    (ergebnis,) = paypal(s, archiv, kontext, neu.encode("utf-8"), "pp2.csv")
    assert ergebnis.neu
    assert ergebnis.umsaetze == 1
    neue = [p for p in ergebnis.abrechnung.posten if p.art is Postenart.ERLOES]
    assert [p.referenz for p in neue] == ["XNEU0000000000001"]
    assert len(lade_buchungen(s)) == anzahl + 2  # Erlös und Gebühr
