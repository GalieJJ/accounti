"""Importlauf: Bericht archivieren, buchen, Auszahlung gegen die Bank abgleichen."""

import hashlib
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
from accounti.models.integrationen import AbrechnungStatus, Postenart, Schweregrad
from accounti.opos.zahlungslauf import offene_transaktionen
from tests.marktplatz_hilfe import paypal_bericht

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
    # dem Hinweis folgen: die Auszahlung ist eine Geldbewegung ohne Umsatzsteuer
    import re

    from accounti.pruefung.storno import korrigiere

    treffer = re.search(
        r"korrigiere (\w+) --soll (\d+) --haben (\d+) --ohne-steuer", befund.text
    )
    assert treffer is not None, befund.text
    ident, soll, haben = treffer.groups()
    k = korrigiere(s, ident, soll, haben, ohne_steuer=True, von="erika")
    assert k.neu is not None and k.neu.steuer_schluessel is None
    assert k.neu.betrag_netto == D("209.85")


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


# --- PayPal: Einbehalt, Rückbuchung, eingehende Zahlungen ---------------------------


def test_paypal_sonderfaelle(umgebung):
    s, archiv, kontext = umgebung
    roh = (FIXTURES / "paypal_sonderfaelle.csv").read_bytes()
    (ergebnis,) = paypal(s, archiv, kontext, roh, "sonder.csv")
    assert ergebnis.umsaetze == 8
    nach_schluessel = {t.dublettenschluessel: t for t in lade_transaktionen(s)}
    pp = {
        code: nach_schluessel[hashlib.sha256(f"paypal|{code}".encode()).hexdigest()]
        for code in (f"5{x}{x}0000000000000{i}" for i, x in enumerate("ABCDEFGH", 1))
    }
    buchungen = lade_buchungen(s)

    def zu(code):
        return [b for b in buchungen if b.transaktion_id == pp[code].id]

    # Verkauf über den Checkout: Erlös
    verkauf = {(b.soll_konto, b.haben_konto) for b in zu("5AA00000000000001")}
    assert ("1210", "8400") in verkauf
    # Einbehalt für den Konflikt und seine Freigabe: Einbehaltskonto, glatt
    (einbehalt,) = zu("5BB00000000000002")
    (frei,) = zu("5CC00000000000003")
    assert (einbehalt.soll_konto, einbehalt.haben_konto) == ("1500", "1210")
    assert (frei.soll_konto, frei.haben_konto) == ("1210", "1500")
    assert saldo(buchungen, "1500") == 0
    # Rückbuchung (Chargeback): kein Einbehalt, sondern Klärung zur Prüfung
    (rueck,) = zu("5DD00000000000004")
    assert (rueck.soll_konto, rueck.haben_konto) == ("1590", "1210")
    assert rueck.status is BuchungStatus.ZUR_PRUEFUNG
    befunde = {b.code: b for b in ergebnis.abrechnung.befunde}
    assert "§ 17 UStG" in befunde["rueckbuchung"].text
    # eingehende Zahlung ohne Checkout (Ausgangsrechnung) und Erstattung an uns:
    # kein Erlös, offen für opos zuordnen/classify
    for code in ("5EE00000000000005", "5GG00000000000007", "5FF00000000000006"):
        assert zu(code) == []
    offen = {t.id for t in offene_transaktionen(s, True)}
    assert {pp[c].id for c in ("5EE00000000000005", "5GG00000000000007")} <= offen
    hinweise = [
        b.text for b in ergebnis.abrechnung.befunde if b.code == "eingehende_zahlung"
    ]
    assert len(hinweise) == 2 and any("RE-2026-100" in h for h in hinweise)
    assert [b.betrag_netto for b in buchungen if b.haben_konto == "8400"] == [
        D("100.00")
    ]
    # Rückzahlung der Allgemeinen Zahlung: kein Verkauf, also keine Erlösminderung —
    # sie bleibt wie die Zahlung selbst offen für opos zuordnen/classify
    assert zu("5HH00000000000008") == []
    assert pp["5HH00000000000008"].id in offen
    assert not [b for b in buchungen if b.soll_konto == "8400"]
    (rueckzahlung,) = [
        b for b in ergebnis.abrechnung.befunde if b.code == "rueckzahlung_ohne_verkauf"
    ]
    assert rueckzahlung.schweregrad is Schweregrad.HINWEIS
    assert "5EE00000000000005" in rueckzahlung.text


def _pp_zeile(datum, code, typ, brutto, guthaben, zugehoerig=""):
    return {
        "Datum": datum,
        "Uhrzeit": "10:00:00",
        "Name": "Kunde",
        "Typ": typ,
        "Brutto": brutto,
        "Netto": brutto,
        "Transaktionscode": code,
        "Zugehöriger Transaktionscode": zugehoerig,
        "Guthaben": guthaben,
        "Land": "Deutschland",
    }


def test_paypal_rueckzahlung_zu_verkauf_aus_frueherem_export(umgebung):
    """Der Verkauf steht im Augustexport, die Rückzahlung im September."""
    s, archiv, kontext = umgebung
    august = paypal_bericht(
        _pp_zeile(
            "20.08.2026", "VK00000000000001", "Website-Zahlung", "119,00", "119,00"
        )
    )
    september = paypal_bericht(
        _pp_zeile(
            "03.09.2026",
            "RZ00000000000001",
            "Rückzahlung",
            "-119,00",
            "0,00",
            "VK00000000000001",
        )
    )
    paypal(s, archiv, kontext, august, "aug.csv")
    (ergebnis,) = paypal(s, archiv, kontext, september, "sep.csv")
    assert [p.art for p in ergebnis.abrechnung.posten] == [Postenart.ERSTATTUNG]
    (minderung,) = [b for b in lade_buchungen(s) if b.soll_konto == "8400"]
    assert (minderung.betrag_netto, minderung.steuer_betrag) == (
        D("100.00"),
        D("19.00"),
    )
    assert minderung.status is BuchungStatus.AUTO_GEBUCHT


def test_paypal_rueckzahlung_ohne_bekannte_zahlung(umgebung):
    """Die zugehörige Zahlung ist nicht importiert: nicht raten, sondern Warnung."""
    s, archiv, kontext = umgebung
    roh = paypal_bericht(
        _pp_zeile("01.09.2026", "EZ00000000000001", "Bankgutschrift", "50,00", "50,00"),
        _pp_zeile(
            "03.09.2026",
            "RZ00000000000002",
            "Rückzahlung",
            "-30,00",
            "20,00",
            "ALT0000000000001",
        ),
    )
    (ergebnis,) = paypal(s, archiv, kontext, roh, "sep.csv")
    (posten,) = [p for p in ergebnis.abrechnung.posten if p.referenz.startswith("RZ")]
    assert (posten.art, posten.betrag) == (Postenart.ZAHLUNG, D("-30.00"))
    assert not [b for b in lade_buchungen(s) if b.soll_konto == "8400"]
    (befund,) = [
        b for b in ergebnis.abrechnung.befunde if b.code == "rueckzahlung_ohne_verkauf"
    ]
    assert befund.schweregrad is Schweregrad.WARNUNG
    assert "§ 17 UStG" in befund.text and "ALT0000000000001" in befund.text


# --- Fremdwährung und Einbehalt je Marktplatz ---------------------------------------


def test_fremdwaehrung_ohne_kurs_wird_gar_nicht_erst_importiert(umgebung):
    """Sonst wäre die Abrechnung gespeichert und ließe sich nie mehr buchen."""
    s, archiv, kontext = umgebung
    roh = (FIXTURES / "ebay_transaktionsbericht_gbp.csv").read_bytes()
    with pytest.raises(IntegrationError, match="GBP.*--kurs"):
        importiere(s, archiv, kontext, "ebay", roh, "gbp.csv")
    assert lade_abrechnungen(s) == []
    assert lade_belege(s) == []
    eingang = bank(s, date(2026, 9, 11), "60.80", "EBAY 6009990001")
    (ergebnis,) = importiere(s, archiv, kontext, "ebay", roh, "gbp.csv", kurs=D("0.85"))
    assert ergebnis.neu and ergebnis.buchungen == 2  # Erlös, Verkaufsgebühren
    buchungen = lade_buchungen(s)
    # 60,00 GBP / 0,85 = 70,59 EUR brutto; Gebühren einzeln umgerechnet
    (erloes,) = [b for b in buchungen if b.haben_konto == "8120"]
    assert erloes.betrag_netto == D("70.59")
    assert eingang.id in {b.transaktion_id for b in buchungen}
    assert saldo(buchungen, "1362") == 0
    assert lade_abrechnungen(s)[0].status is AbrechnungStatus.ABGEGLICHEN


def test_shopify_reserve_in_fremdwaehrung(umgebung):
    s, archiv, kontext = umgebung
    roh = (FIXTURES / "shopify_auszahlung_gbp.csv").read_bytes()
    laender = lies_laenderdatei((FIXTURES / "shopify_bestellungen.csv").read_bytes())
    bank(s, date(2026, 9, 5), "62.30", "SHOPIFY PAYOUT")
    (ergebnis,) = importiere(
        s, archiv, kontext, "shopify", roh, "s.csv", laender=laender, kurs=D("0.85")
    )
    buchungen = lade_buchungen(s)
    # Reserve 10,00 GBP / 0,85 → 11,76 EUR auf dem Einbehaltskonto
    assert saldo(buchungen, "1500") == D("11.76")
    (nl,) = [b for b in buchungen if b.haben_konto == "8323"]
    assert nl.betrag_netto == D("24.31")  # 25,00 GBP = 29,41 EUR / 1,21
    assert saldo(buchungen, "1363") == 0
    assert lade_abrechnungen(s)[0].status is AbrechnungStatus.ABGEGLICHEN
