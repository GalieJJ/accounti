"""Anlagenabgang: AfA bis zum Abgangsmonat, Restbuchwert, Erlös, Ergebnis."""

from datetime import date
from decimal import Decimal

import pytest

from accounti.anlagen.abgang import AbgangError, buche_abgang
from accounti.anlagen.konfiguration import lade_anlagen
from accounti.anlagen.lauf import afa_lauf
from accounti.db.repo_anlagen import lade_anlage
from accounti.models import BuchungStatus
from accounti.models.anlagen import AbgangArt, AfaArt
from tests.abschluss_hilfe import anlegen, datenbank

D = Decimal


@pytest.fixture
def make_session(tmp_path):
    yield from datenbank(tmp_path)


@pytest.fixture
def einst(tmp_path):
    return lade_anlagen(tmp_path / "keine.yaml")


def _paare(buchungen):
    return [
        (
            b.soll_konto,
            b.haben_konto,
            b.betrag_netto,
            b.steuer_schluessel,
            b.steuer_betrag,
        )
        for b in buchungen
    ]


def _vorbereiten(make_session, einst, bis_jahr=2027):
    g = anlegen(make_session, 3600, date(2026, 9, 15), nd=3)
    with make_session() as s:
        for jahr in range(2026, bis_jahr + 1):
            afa_lauf(s, jahr, einst)
        s.commit()
    return g


def _abgang(make_session, einst, nr, **kw):
    with make_session() as s:
        ergebnis = buche_abgang(s, str(nr), einstellungen=einst, **kw)
        s.commit()
    return ergebnis


def test_verkauf_mit_buchgewinn(make_session, einst):
    g = _vorbereiten(make_session, einst)
    e = _abgang(
        make_session,
        einst,
        g.nr,
        datum=date(2028, 5, 20),
        erloes=D("2000"),
        gegenkonto="1200",
    )
    assert e.afa.summe == D("500.00")  # Januar bis Mai 2028
    assert e.restbuchwert == D("1500.00")
    assert e.ergebnis == D("500.00")
    assert _paare(e.buchungen) == [
        ("2315", "0420", D("1500.00"), None, None),
        ("1200", "8820", D("2000"), 3, D("380.00")),
    ]
    assert all(b.status is BuchungStatus.ZUR_PRUEFUNG for b in e.buchungen)
    with make_session() as s:
        gespeichert = lade_anlage(s, str(g.nr))
    assert gespeichert.abgang_datum == date(2028, 5, 20)
    assert gespeichert.abgang_art is AbgangArt.VERKAUF
    assert gespeichert.abgang_erloes == D("2000")


def test_verkauf_mit_buchverlust_und_ohne_ust(make_session, einst):
    g = _vorbereiten(make_session, einst)
    e = _abgang(
        make_session,
        einst,
        g.nr,
        datum=date(2028, 5, 20),
        erloes=D("1000"),
        gegenkonto="1200",
        mit_ust=False,
    )
    assert e.ergebnis == D("-500.00")
    assert _paare(e.buchungen) == [
        ("2310", "0420", D("1500.00"), None, None),
        ("1200", "8800", D("1000"), None, None),
    ]


def test_verschrottung(make_session, einst):
    g = _vorbereiten(make_session, einst)
    e = _abgang(
        make_session, einst, g.nr, datum=date(2028, 5, 20), art=AbgangArt.VERSCHROTTUNG
    )
    assert e.ergebnis == D("-1500.00")
    assert _paare(e.buchungen) == [("2310", "0420", D("1500.00"), None, None)]


def test_abgang_nach_gebuchter_jahres_afa_korrigiert(make_session, einst):
    g = _vorbereiten(make_session, einst)  # 2027 voll gebucht
    e = _abgang(make_session, einst, g.nr, datum=date(2027, 5, 31))
    assert e.afa.summe == D("-700.00")
    assert e.restbuchwert == D("2700.00")  # 3.600 − 400 − 500


def test_sammelposten_wird_nicht_gemindert(make_session, einst):
    g = anlegen(make_session, 600, date(2026, 2, 1), AfaArt.SAMMELPOSTEN)
    e = _abgang(
        make_session,
        einst,
        g.nr,
        datum=date(2027, 3, 1),
        erloes=D("100"),
        gegenkonto="1000",
    )
    assert e.restbuchwert == 0
    assert _paare(e.buchungen) == [("1000", "8820", D("100"), 3, D("19.00"))]
    assert any("Sammelposten" in h for h in e.hinweise)


def test_sammelposten_abgang_im_anschaffungsjahr(make_session, einst):
    g = anlegen(make_session, 600, date(2026, 2, 1), AfaArt.SAMMELPOSTEN)
    e = _abgang(make_session, einst, g.nr, datum=date(2026, 8, 1))
    assert e.restbuchwert == D("600")
    assert _paare(e.buchungen) == [("2310", "0485", D("600"), None, None)]


def test_fehler(make_session, einst):
    g = _vorbereiten(make_session, einst)
    with pytest.raises(AbgangError, match="vor der Anschaffung"):
        _abgang(make_session, einst, g.nr, datum=date(2025, 1, 1))
    with pytest.raises(AbgangError, match="Gegenkonto"):
        _abgang(make_session, einst, g.nr, datum=date(2028, 1, 1), erloes=D("5"))
    _abgang(make_session, einst, g.nr, datum=date(2028, 1, 31))
    with pytest.raises(AbgangError, match="schon"):
        _abgang(make_session, einst, g.nr, datum=date(2028, 2, 1))
