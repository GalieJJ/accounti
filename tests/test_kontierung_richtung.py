"""Zahlungsrichtung beim Kontieren und Standardregeln je Kontenrahmen.

Gesamttest: Eingang B07 = Abschluss B4 = Steuer B1 (Gutschrift wie Ausgabe gebucht),
Betrieb B3 (SKR03-Standardregeln in SKR04), Steuer B2 (classify bucht
Marktplatz-Auszahlungen vor dem Abgleich als Erlös bzw. Aufwand).
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from accounti.buchung.mapper import zu_buchungssatz
from accounti.klassifikation.engine import (
    STANDARD_REGELN,
    KlassifikationsEngine,
    Regel,
    RegelwerkEngine,
    standard_regeln,
)
from accounti.klassifikation.regeln_loader import lade_regeln
from accounti.konfiguration import KonfigurationError
from accounti.models import (
    BuchungStatus,
    Klassifikationsergebnis,
    Transaktion,
    TransaktionQuelle,
)
from accounti.steuer.kennziffern import Kontenplan, ermittle
from accounti.steuer.zeitraum import Zeitraum

D = Decimal
REGELN = Path(__file__).resolve().parents[1] / "config" / "regeln.yaml"
FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "marktplatz"
PRUEFUNG = BuchungStatus.ZUR_PRUEFUNG
AUTO = BuchungStatus.AUTO_GEBUCHT


def tx(betrag: str, zweck: str, name: str | None = None, **kw) -> Transaktion:
    return Transaktion(
        datum=kw.pop("datum", date(2026, 4, 15)),
        betrag=D(betrag),
        verwendungszweck=zweck,
        gegenkonto_name=name,
        quelle=kw.pop("quelle", TransaktionQuelle.BANK),
        rohtext=zweck,
        **kw,
    )


def kontiere(engine: KlassifikationsEngine, t: Transaktion, bank: str = "1200"):
    ergebnis = engine.klassifiziere(t)
    assert ergebnis is not None, t.verwendungszweck
    return zu_buchungssatz(t, ergebnis, bank_konto=bank)


def ergebnis(soll, haben, schluessel=9, confidence=1.0, quelle="llm", **kw):
    return Klassifikationsergebnis(
        transaktion_id=uuid4(),
        soll_konto=soll,
        haben_konto=haben,
        steuer_schluessel=schluessel,
        buchungstext="Test",
        confidence=confidence,
        begruendung="Test",
        quelle=quelle,
        **kw,
    )


# --- Eingang B07 / Steuer B1: Gutschrift auf eine Ausgaberegel --------------------


def test_gutschrift_auf_ausgaberegel_mindert_die_vorsteuer_zur_pruefung():
    """Telekom −119/+119 (Repro b07): die Gutschrift ist keine zweite Ausgabe.

    § 17 Abs. 1 S. 2 UStG: Minderung des Entgelts → Vorsteuer berichtigen."""
    engine = KlassifikationsEngine(RegelwerkEngine(lade_regeln(REGELN)))
    last = kontiere(engine, tx("-119.00", "TELEKOM MOBILFUNK APRIL", "Telekom AG"))
    gut = kontiere(engine, tx("119.00", "TELEKOM GUTSCHRIFT KULANZ", "Telekom AG"))
    assert (last.soll_konto, last.haben_konto, last.status) == ("4920", "1200", AUTO)
    assert (
        gut.soll_konto,
        gut.haben_konto,
        gut.steuer_schluessel,
        gut.betrag_netto,
        gut.steuer_betrag,
        gut.status,
    ) == ("1200", "4920", 9, D("100.00"), D("19.00"), PRUEFUNG)
    # nach der Freigabe heben sich die Vorsteuerbeträge auf
    frei = [last, gut.model_copy(update={"status": BuchungStatus.GEPRUEFT})]
    werte = ermittle(frei, Zeitraum.lies("2026-04"), Kontenplan()).voranmeldung.werte
    assert werte.get(66, D("0")) == 0


def test_erstattung_und_untermiete_aus_standardregeln_nicht_als_aufwand():
    """Repro abschluss/r_regel_richtung: nur Standardregeln, Zahlungseingänge."""
    engine = KlassifikationsEngine(RegelwerkEngine(standard_regeln("SKR03")))
    miete = kontiere(engine, tx("500.00", "UNTERMIETE MAERZ", "Mieter Meier"))
    erst = kontiere(engine, tx("80.00", "BEITRAGSERSTATTUNG VERSICHERUNG", "Allianz"))
    assert (miete.soll_konto, miete.haben_konto, miete.steuer_schluessel) == (
        "1200",
        "4210",
        None,
    )
    assert (erst.soll_konto, erst.haben_konto, erst.steuer_schluessel) == (
        "1200",
        "4360",
        None,
    )
    assert miete.status is PRUEFUNG and erst.status is PRUEFUNG


def test_regel_der_passenden_richtung_hat_vorrang():
    regeln = RegelwerkEngine(
        [
            Regel("miete", "miete", "4210", "1200", richtung="ausgabe"),
            Regel("untermiete", "untermiete", "1200", "8200", richtung="einnahme"),
        ]
    )
    erg = regeln.klassifiziere(tx("500.00", "UNTERMIETE MAERZ"))
    assert erg is not None
    assert (erg.soll_konto, erg.haben_konto, erg.pruefen) == ("1200", "8200", False)
    # Regelwerk allein kennt nur Treffer der passenden Richtung …
    assert RegelwerkEngine(regeln.regeln[:1]).klassifiziere(tx("5.00", "MIETE")) is None
    # … die Gegenrichtung schlägt erst der Orchestrator vor, gedreht und zur Prüfung
    gegen = RegelwerkEngine(regeln.regeln[:1]).gegenrichtung(tx("5.00", "MIETE"))
    assert gegen is not None
    assert (gegen.soll_konto, gegen.haben_konto, gegen.pruefen) == (
        "1200",
        "4210",
        True,
    )
    assert "Ausgabe" in gegen.begruendung


def test_gegenrichtung_erst_nach_dem_llm():
    class Llm:
        def __init__(self, antwort):
            self.antwort = antwort
            self.gefragt = 0

        def klassifiziere(self, t):
            self.gefragt += 1
            return self.antwort

    regeln = RegelwerkEngine(
        [Regel("tk", "telekom", "4920", "1200", 9, richtung="ausgabe")]
    )
    gut = tx("119.00", "TELEKOM GUTSCHRIFT")
    llm = Llm(ergebnis("1200", "4920", confidence=0.97))
    erg = KlassifikationsEngine(regeln, llm).klassifiziere(gut)  # type: ignore[arg-type]
    assert llm.gefragt == 1 and erg is llm.antwort
    leer = Llm(None)
    erg = KlassifikationsEngine(regeln, leer).klassifiziere(gut)  # type: ignore[arg-type]
    assert leer.gefragt == 1 and erg is not None and erg.pruefen
    assert (erg.soll_konto, erg.haben_konto) == ("1200", "4920")


# --- Mapper-Schranke: auch LLM- und gelernte Regeln -------------------------------


@pytest.mark.parametrize("quelle", ["llm", "regelwerk"])
def test_mapper_dreht_eine_verkehrte_richtung_und_legt_vor(quelle):
    erstattung = tx("23.99", "AMAZON MKTPLACE ERSTATTUNG")
    b = zu_buchungssatz(erstattung, ergebnis("4930", "1200", quelle=quelle))
    assert (b.soll_konto, b.haben_konto, b.betrag_netto, b.steuer_betrag) == (
        "1200",
        "4930",
        D("20.16"),
        D("3.83"),
    )
    assert b.status is PRUEFUNG and b.confidence <= 0.5
    abbuchung = tx("-59.50", "RUECKBUCHUNG KUNDE")
    b = zu_buchungssatz(abbuchung, ergebnis("1200", "8400", 3, quelle=quelle))
    assert (b.soll_konto, b.haben_konto, b.status) == ("8400", "1200", PRUEFUNG)


def test_mapper_kennt_das_bankkonto_des_umsatzes():
    karte = tx("23.99", "AMAZON ERSTATTUNG", sachkonto="1730")
    b = zu_buchungssatz(karte, ergebnis("4930", "1730"), bank_konto="1200")
    assert (b.soll_konto, b.haben_konto, b.status) == ("1730", "4930", PRUEFUNG)
    giro = tx("-23.99", "AMAZON MKTPLACE", sachkonto="1730")
    b = zu_buchungssatz(giro, ergebnis("4930", "1200"), bank_konto="1200")
    assert (b.soll_konto, b.haben_konto, b.status) == ("4930", "1200", AUTO)


def test_mapper_ohne_bankkonto_auf_einer_seite_zur_pruefung():
    """SKR03-Regel (Bank 1200) in einer SKR04-Gesellschaft (Bank 1800)."""
    b = zu_buchungssatz(
        tx("-119.00", "TELEKOM"), ergebnis("4920", "1200"), bank_konto="1800"
    )
    assert (b.soll_konto, b.haben_konto, b.status) == ("4920", "1200", PRUEFUNG)


def test_mapper_pruefen_aus_der_regel():
    b = zu_buchungssatz(
        tx("-1200.00", "MIETE"), ergebnis("4210", "1200", None, pruefen=True)
    )
    assert b.status is PRUEFUNG


def test_gelernte_regel_ohne_richtung_gutschrift_gedreht():
    """Repro b08: `accounti lerne` legt Regeln ohne Richtung an."""
    gelernt = RegelwerkEngine([Regel("amazon", "AMAZON MKTPLACE", "4930", "1200", 9)])
    engine = KlassifikationsEngine(gelernt)
    b = kontiere(engine, tx("23.99", "AMAZON MKTPLACE GUTSCHRIFT"))
    assert (b.soll_konto, b.haben_konto, b.status) == ("1200", "4930", PRUEFUNG)


# --- Regelfelder richtung, pruefen, confidence ------------------------------------


def test_regelfelder_werden_geprueft():
    assert Regel("x", "x", "4900", "1200", richtung="beide").richtung is None
    with pytest.raises(ValueError, match="richtung"):
        Regel("x", "x", "4900", "1200", richtung="rein")
    with pytest.raises(ValueError, match="confidence"):
        Regel("x", "x", "4900", "1200", confidence=1.5)


def test_loader_liest_richtung_pruefen_confidence(tmp_path):
    datei = tmp_path / "regeln.yaml"
    datei.write_text(
        "- name: miete\n  muster: miete\n  soll_konto: '4210'\n  haben_konto: '1200'\n"
        "  steuer_schluessel: null\n  richtung: ausgabe\n  pruefen: true\n"
        "- name: strom\n  muster: strom\n  soll_konto: '4240'\n  haben_konto: '1200'\n"
        "  confidence: 0.9\n",
        encoding="utf-8",
    )
    miete, strom = lade_regeln(datei)
    assert (miete.richtung, miete.pruefen, miete.confidence) == ("ausgabe", True, 1.0)
    assert (strom.richtung, strom.pruefen, strom.confidence) == (None, False, 0.9)
    erg = RegelwerkEngine([strom]).klassifiziere(tx("-50", "STROM"))
    assert erg is not None and erg.confidence == 0.9


def test_loader_falsche_richtung_ist_ein_konfigurationsfehler(tmp_path):
    datei = tmp_path / "regeln.yaml"
    datei.write_text(
        "- name: kaputt\n  muster: x\n  soll_konto: '4900'\n  haben_konto: '1200'\n"
        "  richtung: rueckwaerts\n",
        encoding="utf-8",
    )
    with pytest.raises(KonfigurationError, match="kaputt"):
        lade_regeln(datei)


def test_mitgelieferte_regeln_haben_eine_richtung():
    for regel in [*lade_regeln(REGELN), *standard_regeln("SKR03")]:
        assert regel.richtung in ("ausgabe", "einnahme"), regel.name
        bank = "haben" if regel.richtung == "ausgabe" else "soll"
        assert getattr(regel, f"{bank}_konto") == "1200", regel.name


# --- Betrieb B3: Standardregeln je Kontenrahmen ------------------------------------


def test_standardregeln_skr04():
    engine = RegelwerkEngine(standard_regeln("SKR04", "1800"))
    aws = engine.klassifiziere(
        tx("-89.50", "AWS EMEA HOSTING 08/25", "Amazon Web Services EMEA SARL")
    )
    miete = engine.klassifiziere(tx("-1200.00", "MIETE BUERO 08/25", "Vermieter"))
    vers = engine.klassifiziere(tx("-320.00", "HAFTPFLICHTVERSICHERUNG", "Allianz"))
    assert aws is not None and miete is not None and vers is not None
    # § 13b UStG: AWS EMEA SARL (LU) — keine Vorsteuer „aus Rechnung“, Mensch prüft
    assert (aws.soll_konto, aws.haben_konto, aws.steuer_schluessel, aws.pruefen) == (
        "6300",
        "1800",
        None,
        True,
    )
    # § 4 Nr. 12 UStG: Miete steuerfrei, Vorsteuer nur bei Option (§ 9 UStG)
    assert (miete.soll_konto, miete.steuer_schluessel, miete.pruefen) == (
        "6310",
        None,
        True,
    )
    assert (vers.soll_konto, vers.haben_konto) == ("6400", "1800")
    konten = {
        k for r in standard_regeln("SKR04") for k in (r.soll_konto, r.haben_konto)
    }
    assert konten.isdisjoint({"1200", "8400", "4210", "4360", "4970", "1360"})


def test_standardregeln_skr03_ohne_vorsteuer_auf_miete_und_aws():
    regeln = {r.name: r for r in standard_regeln("SKR03")}
    assert regeln["miete"].steuer_schluessel is None and regeln["miete"].pruefen
    assert regeln["aws_hosting"].steuer_schluessel is None
    assert regeln["aws_hosting"].pruefen
    # Marktplatz-Auszahlung: Geldtransit ohne Umsatzsteuer, nicht Erlös
    assert (regeln["amazon_auszahlung"].haben_konto,) == ("1360",)
    assert regeln["amazon_auszahlung"].steuer_schluessel is None
    assert [r.name for r in STANDARD_REGELN] == [r.name for r in standard_regeln()]


def test_standardregeln_unbekannter_kontenrahmen_keine():
    assert standard_regeln("SKR99") == []
    assert [r.soll_konto for r in standard_regeln("skr04")][0] == "1800"
