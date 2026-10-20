"""AfA-Lauf: Soll bis Monat minus schon gebucht — monatlich, jährlich, idempotent."""

from datetime import date
from decimal import Decimal

import pytest

from accounti.anlagen.konfiguration import lade_anlagen
from accounti.anlagen.lauf import afa_lauf, freigeben
from accounti.db.repo_anlagen import aktualisiere_anlage, lade_afa_vorgaenge
from accounti.db.repository import lade_buchungen
from accounti.models import BuchungStatus
from accounti.models.anlagen import AfaArt
from tests.abschluss_hilfe import anlegen, datenbank

D = Decimal


@pytest.fixture
def make_session(tmp_path):
    yield from datenbank(tmp_path)


@pytest.fixture
def einst(tmp_path):
    return lade_anlagen(tmp_path / "keine.yaml")


def lauf(make_session, einst, jahr, bis_monat=12):
    with make_session() as s:
        ergebnis = afa_lauf(s, jahr, einst, bis_monat=bis_monat)
        s.commit()
    return ergebnis


def buchungen(make_session):
    with make_session() as s:
        return sorted(lade_buchungen(s), key=lambda b: (b.datum, b.soll_konto))


def test_monatslauf_und_jahreslauf_ergeben_die_jahres_afa(make_session, einst):
    anlegen(make_session, 3600, date(2026, 9, 15), nd=3)
    erster = lauf(make_session, einst, 2026, bis_monat=10)
    assert erster.summe == D("200.00")  # September und Oktober
    zweiter = lauf(make_session, einst, 2026)
    assert zweiter.summe == D("200.00")
    assert lauf(make_session, einst, 2026).buchungen == []  # idempotent
    b = buchungen(make_session)
    assert [(x.datum, x.soll_konto, x.haben_konto, x.betrag_netto) for x in b] == [
        (date(2026, 10, 31), "4830", "0420", D("200.00")),
        (date(2026, 12, 31), "4830", "0420", D("200.00")),
    ]
    assert all(x.status is BuchungStatus.ZUR_PRUEFUNG for x in b)
    assert all("AfA 2026" in x.buchungstext for x in b)
    with make_session() as s:
        vorgaenge = lade_afa_vorgaenge(s, 2026)
    assert sum(v.betrag for v in vorgaenge) == D("400.00")
    assert all("linear" in v.begruendung for v in vorgaenge)
    assert "Gut 3600" in vorgaenge[0].begruendung


def test_eine_buchung_je_konto_paar(make_session, einst):
    anlegen(make_session, 1300, date(2026, 1, 1), nd=13)
    anlegen(make_session, 2600, date(2026, 1, 1), nd=13)
    anlegen(make_session, 700, date(2026, 3, 1), AfaArt.GWG)
    ergebnis = lauf(make_session, einst, 2026)
    assert len(ergebnis.positionen) == 3
    paare = {(b.soll_konto, b.haben_konto): b.betrag_netto for b in ergebnis.buchungen}
    assert paare == {("4830", "0420"): D("300.00"), ("4855", "0480"): D("700.00")}


def test_sammelposten_erst_zum_jahresende(make_session, einst):
    anlegen(make_session, 600, date(2026, 2, 1), AfaArt.SAMMELPOSTEN)
    anlegen(make_session, 900, date(2026, 6, 1), AfaArt.SAMMELPOSTEN)
    assert lauf(make_session, einst, 2026, bis_monat=11).buchungen == []
    ergebnis = lauf(make_session, einst, 2026)
    assert [
        (b.soll_konto, b.haben_konto, b.betrag_netto) for b in ergebnis.buchungen
    ] == [("4862", "0485", D("300.00"))]
    assert ergebnis.positionen[0].objekt == "sammelposten:0485:2026"
    assert lauf(make_session, einst, 2027).summe == D("300.00")


def test_korrektur_nach_spaeterem_abgang(make_session, einst):
    g = anlegen(make_session, 3600, date(2026, 9, 15), nd=3)
    lauf(make_session, einst, 2026)
    assert lauf(make_session, einst, 2027).summe == D("1200.00")
    with make_session() as s:
        aktualisiere_anlage(s, g.model_copy(update={"abgang_datum": date(2027, 5, 20)}))
        s.commit()
    korrektur = lauf(make_session, einst, 2027)
    assert korrektur.summe == D("-700.00")  # nur Januar bis Mai
    b = korrektur.buchungen[0]
    assert (b.soll_konto, b.haben_konto, b.betrag_netto) == (
        "0420",
        "4830",
        D("700.00"),
    )
    assert "Korrektur" in b.buchungstext


def test_fruehere_jahre_werden_nicht_nachgeholt(make_session, einst):
    anlegen(make_session, 3600, date(2024, 1, 10), nd=6)
    ergebnis = lauf(make_session, einst, 2026)
    assert ergebnis.summe == D("600.00")


def test_nicht_abnutzbar_und_kfz(make_session, einst):
    anlegen(make_session, 50000, date(2026, 1, 1), AfaArt.KEINE, konto="0065")
    anlegen(make_session, 36000, date(2026, 1, 1), nd=6, konto="0320")
    ergebnis = lauf(make_session, einst, 2026)
    assert [
        (b.soll_konto, b.haben_konto, b.betrag_netto) for b in ergebnis.buchungen
    ] == [("4832", "0320", D("6000.00"))]


def test_freigeben(make_session, einst):
    anlegen(make_session, 1300, date(2026, 1, 1), nd=13)
    lauf(make_session, einst, 2026)
    with make_session() as s:
        assert freigeben(s, 2026, "pruefer") == 1
        s.commit()
    (b,) = buchungen(make_session)
    assert (b.status, b.geprueft_von) == (BuchungStatus.GEPRUEFT, "pruefer")
    with make_session() as s:
        assert freigeben(s, 2026, "pruefer") == 0
