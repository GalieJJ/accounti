"""Steuer je Bestimmungsland: OSS-Erlöskonten, Quartalsmeldung, Sonderfälle.

Sollwerte von Hand gerechnet (Amazon-Fixture, Q3 2026, OSS-registriert):

    FR  Bestellung 2   60,00 brutto → 50,00 netto + 10,00 USt (20 %)
        Bestellung 6   36,00 brutto → 30,00 netto +  6,00 USt
        Erstattung 2  −60,00 brutto → −50,00 netto − 10,00 USt
        Summe                          30,00          6,00
    IT  Bestellung 3   61,00 brutto → 50,00 netto + 11,00 USt (22 %)
    AT  Bestellung 4   50,40 brutto → 42,00 netto +  8,40 USt (20 %)
    Gesamt                            122,00         25,40
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from accounti.belege.archiv import BelegArchiv
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_buchungen
from accounti.importers.marktplatz import MARKTPLATZ_IMPORTER, lies_laenderdatei
from accounti.integrationen.buchung import (
    Buchungskontext,
    buche_abrechnung,
    ergaenze_auszahlung,
)
from accounti.integrationen.einstellungen import (
    Kontext,
    lade_integrationen,
)
from accounti.integrationen.lauf import importiere
from accounti.integrationen.oss import oss_meldung
from accounti.models import Buchungssatz, BuchungStatus
from accounti.models.integrationen import Laenderangabe
from accounti.steuer.oss import OSSEngine

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "marktplatz"
D = Decimal


def amazon(laender=None):
    roh = (FIXTURES / "amazon_abrechnung_v2.txt").read_bytes()
    angaben = lies_laenderdatei((FIXTURES / "amazon_bestellungen.txt").read_bytes())
    angaben.update(laender or {})
    (a,) = MARKTPLATZ_IMPORTER["amazon"].lies(roh, "a.txt", angaben)
    ergaenze_auszahlung(a)
    return a


def buche(a, tmp_path, oss=True, **kw):
    einstellungen = kw.pop("einstellungen", lade_integrationen(tmp_path / "x.yaml"))
    return buche_abrechnung(
        a, Buchungskontext(einstellungen=einstellungen, oss_registriert=oss, **kw)
    )


def mit_beleg(ergebnis, nummer):
    return [b for b in ergebnis.buchungen if b.beleg_nummer == nummer]


def test_akzeptanz_3_drei_eu_laender_auf_oss_konten_und_in_der_meldung(tmp_path):
    engine, make = session_factory(f"sqlite:///{tmp_path / 'o.db'}")
    init_db(engine)
    kontext = Kontext(
        einstellungen=lade_integrationen(tmp_path / "x.yaml"), oss_registriert=True
    )
    roh = (FIXTURES / "amazon_abrechnung_v2.txt").read_bytes()
    angaben = lies_laenderdatei((FIXTURES / "amazon_bestellungen.txt").read_bytes())
    with make() as s:
        importiere(
            s, BelegArchiv(tmp_path / "a"), kontext, "amazon", roh, "a.txt", angaben
        )
        buchungen = lade_buchungen(s)
        meldung = oss_meldung(s, 2026, 3)

    def netto(konto, seite):
        return sum(
            (b.betrag_netto for b in buchungen if getattr(b, seite) == konto), D("0")
        )

    # richtige OSS-Erlöskonten (steuer.umsatzsteuer.OSS_ERLOES_KONTEN_SKR03)
    assert netto("8320", "haben_konto") - netto("8320", "soll_konto") == D("30.00")
    assert netto("8321", "haben_konto") == D("50.00")
    assert netto("8326", "haben_konto") == D("42.00")
    # Umsatzsteuer der Bestimmungsländer auf den OSS-Steuerkonten
    assert netto("177722", "haben_konto") == D("11.00")  # IT 22 %
    assert netto("177720", "haben_konto") - netto("177720", "soll_konto") == D(
        "14.40"
    )  # FR 6,00 + AT 8,40
    # deutsche Bestellungen bleiben Inland, CH ist Ausfuhr
    assert netto("8400", "haben_konto") == D("104.12") + D("22.68")
    assert netto("8120", "haben_konto") == D("80.00")

    laender = {land.land_code: land for land in meldung.laender}
    assert set(laender) == {"FR", "IT", "AT"}
    assert (
        laender["FR"].bemessungsgrundlage_gesamt,
        laender["FR"].steuer_gesamt,
    ) == (D("30.00"), D("6.00"))
    assert (laender["IT"].bemessungsgrundlage_gesamt, laender["IT"].steuer_gesamt) == (
        D("50.00"),
        D("11.00"),
    )
    assert (laender["AT"].bemessungsgrundlage_gesamt, laender["AT"].steuer_gesamt) == (
        D("42.00"),
        D("8.40"),
    )
    assert (meldung.bemessungsgrundlage_gesamt, meldung.steuer_gesamt) == (
        D("122.00"),
        D("25.40"),
    )
    assert meldung.abgabefrist == date(2026, 10, 31)
    assert meldung.als_csv_zeilen()[-1] == "GESAMT;;122.00;25.40;5"


def test_erstattung_mindert_die_oss_meldung():
    """Fix in steuer/oss.py: Erlösminderung (OSS-Konto im Soll) zählt negativ."""
    erloes = Buchungssatz(
        datum=date(2026, 8, 4),
        soll_konto="1361",
        haben_konto="8320",
        betrag_netto=D("50.00"),
        buchungstext="Erlös FR",
    )
    erstattung = erloes.model_copy(
        update={"soll_konto": "8320", "haben_konto": "1361", "datum": date(2026, 8, 12)}
    )
    meldung = OSSEngine().erstelle_meldung([erloes, erstattung], 2026, 3)
    (fr,) = meldung.laender
    assert (fr.bemessungsgrundlage_gesamt, fr.steuer_gesamt) == (D("0.00"), D("0.00"))
    schwelle, summe = OSSEngine().pruefe_schwelle([erloes, erstattung], 2026)
    assert (schwelle, summe) == (False, D("0.00"))


def test_ohne_oss_registrierung_inland_mit_deutscher_steuer(tmp_path):
    e = buche(amazon(), tmp_path, oss=False)
    (fr,) = mit_beleg(e, "302-1000002-0000002")[:1]
    assert (fr.haben_konto, fr.steuer_schluessel) == ("8400", 3)
    assert fr.betrag_netto == D("50.42")  # 60,00 / 1,19
    assert not [b for b in e.buchungen if b.haben_konto.startswith("832")]


def test_lieferschwelle_ueberschritten(tmp_path):
    e = buche(amazon(), tmp_path, oss=False, eu_b2c_bisher={2026: D("9990.00")})
    (befund,) = [b for b in e.befunde if b.code == "lieferschwelle"]
    assert "10.000" in befund.text
    # FR-Bestellung 2 (50,42 netto) überschreitet die Schwelle — sie und alle
    # späteren EU-Fernverkäufe gehen zur Prüfung, Inlandsverkäufe nicht
    (fr,) = mit_beleg(e, "302-1000002-0000002")[:1]
    assert fr.status is BuchungStatus.ZUR_PRUEFUNG
    (de,) = mit_beleg(e, "302-1000005-0000005")
    assert de.status is BuchungStatus.AUTO_GEBUCHT


def test_b2b_mit_ust_id_ist_ig_lieferung_zur_pruefung(tmp_path):
    a = amazon(
        {
            "302-1000003-0000003": Laenderangabe(
                bestellnummer="302-1000003-0000003",
                bestimmungsland="IT",
                kaeufer_ust_id="IT01234567897",
            )
        }
    )
    e = buche(a, tmp_path)
    (it,) = mit_beleg(e, "302-1000003-0000003")
    assert (it.haben_konto, it.betrag_netto, it.steuer_betrag) == (
        "8125",
        D("61.00"),
        None,
    )
    assert it.status is BuchungStatus.ZUR_PRUEFUNG
    assert any(b.code == "ig_lieferung" for b in e.befunde)


def test_abgangsland_ausland_zur_pruefung(tmp_path):
    a = amazon(
        {
            "302-1000001-0000001": Laenderangabe(
                bestellnummer="302-1000001-0000001",
                bestimmungsland="DE",
                abgangsland="PL",
            )
        }
    )
    e = buche(a, tmp_path)
    (de,) = mit_beleg(e, "302-1000001-0000001")
    assert de.status is BuchungStatus.ZUR_PRUEFUNG
    assert any(b.code == "abgangsland" and "(PL)" in b.text for b in e.befunde)


def test_ermaessigter_satz(tmp_path):
    pfad = tmp_path / "c.yaml"
    pfad.write_text("integrationen:\n  ermaessigte_artikel: [ART-100, ART-200]\n")
    e = buche(amazon(), tmp_path, einstellungen=lade_integrationen(pfad))
    (de,) = mit_beleg(e, "302-1000001-0000001")
    assert (de.haben_konto, de.steuer_schluessel) == ("8300", 2)
    assert de.betrag_netto == D("115.79")  # 123,90 / 1,07
    fr = mit_beleg(e, "302-1000002-0000002")
    assert fr[0].betrag_netto == D("56.87")  # 60,00 / 1,055 (FR 5,5 %)
    assert {b.status for b in fr} == {BuchungStatus.ZUR_PRUEFUNG}
    assert any(b.code == "oss_ermaessigt" for b in e.befunde)


def test_land_ohne_oss_konto(tmp_path):
    a = amazon(
        {
            "302-1000003-0000003": Laenderangabe(
                bestellnummer="302-1000003-0000003", bestimmungsland="IE"
            )
        }
    )
    e = buche(a, tmp_path)
    ie = mit_beleg(e, "302-1000003-0000003")
    assert ie[0].haben_konto == "8200"
    assert ie[0].betrag_netto == D("49.59")  # 61,00 / 1,23 (IE 23 %)
    assert any(b.code == "oss_konto_fehlt" and "IE" in b.text for b in e.befunde)


def test_drittland_ausfuhr_zur_pruefung(tmp_path):
    e = buche(amazon(), tmp_path)
    (ch,) = mit_beleg(e, "302-1000007-0000007")
    assert (ch.haben_konto, ch.status) == ("8120", BuchungStatus.ZUR_PRUEFUNG)
    assert any(b.code == "ausfuhr" for b in e.befunde)


@pytest.fixture
def cli_db(tmp_path):
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text("mandant:\n  name: Test GmbH\n  oss: true\n", encoding="utf-8")
    basis = ["--db", f"sqlite:///{tmp_path / 'c.db'}", "--config", str(konfig)]
    r = CliRunner().invoke(
        app,
        [
            "marktplatz",
            "import",
            "amazon",
            str(FIXTURES / "amazon_abrechnung_v2.txt"),
            "--laender",
            str(FIXTURES / "amazon_bestellungen.txt"),
            "--archiv",
            str(tmp_path / "archiv"),
            *basis,
        ],
    )
    assert r.exit_code == 0, r.output
    return basis


def test_cli_oss_quartal(cli_db, tmp_path):
    csv = tmp_path / "oss.csv"
    r = CliRunner().invoke(
        app,
        ["marktplatz", "oss", "--quartal", "2026-Q3", "--csv", str(csv), *cli_db[:2]],
    )
    assert r.exit_code == 0, r.output
    text = " ".join(r.output.split())
    assert "2026-Q3" in text and "31.10.2026" in text
    assert "FR" in text and "30,00" in text and "6,00" in text
    assert "GESAMT;;122.00;25.40;5" in csv.read_text(encoding="utf-8")


def test_cli_oss_quartal_falsch(cli_db):
    r = CliRunner().invoke(
        app, ["marktplatz", "oss", "--quartal", "2026-5", *cli_db[:2]]
    )
    assert r.exit_code == 1
