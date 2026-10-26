from datetime import date
from decimal import Decimal

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_buchungen, lade_posten, speichere_beleg
from accounti.models import (
    Belegposition,
    BuchungStatus,
    PostenStatus,
    Transaktion,
    TransaktionQuelle,
)
from accounti.opos.ausgleich import gleiche_aus
from accounti.opos.zuordnung import Anteil
from tests.test_erechnung_aufbau import entwurf, kunde, pos
from tests.test_opos_verbuchung import (
    EINSTELLUNGEN,
    _ausgangsrechnung,
    _verbuche,
    eingangsrechnung,
)


@pytest.fixture
def umgebung(tmp_path):
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    return make_session, BelegArchiv(tmp_path / "archiv")


def tx(betrag, datum=date(2026, 3, 10), zweck="Zahlung"):
    return Transaktion(
        datum=datum,
        betrag=Decimal(betrag),
        verwendungszweck=zweck,
        quelle=TransaktionQuelle.BANK,
        rohtext="x",
    )


def _mit_posten(make_session, beleg=None):
    with make_session() as s:
        speichere_beleg(s, beleg or eingangsrechnung())
        s.commit()
    _verbuche(make_session)
    with make_session() as s:
        (posten,) = lade_posten(s)
    return posten


def _zahlungs_und_skontobuchungen(make_session, transaktion):
    with make_session() as s:
        return sorted(
            [b for b in lade_buchungen(s) if b.transaktion_id == transaktion.id],
            key=lambda b: (b.haben_konto, b.soll_konto),
        )


def _zeile(b):
    return (
        b.soll_konto,
        b.haben_konto,
        b.betrag_netto,
        b.steuer_schluessel,
        b.steuer_betrag,
    )


def test_skonto_mit_vorsteuerkorrektur_19_und_7(umgebung):
    """Akzeptanz 3 — gegen handgerechnete Sollwerte."""
    make_session, _ = umgebung
    posten = _mit_posten(make_session)
    zahlung = tx("-169.05")
    with make_session() as s:
        gleiche_aus(
            s,
            zahlung,
            [Anteil(posten, Decimal("169.05"), Decimal("3.45"))],
            EINSTELLUNGEN,
        )
        s.commit()
        (p,) = lade_posten(s)
    assert [
        _zeile(b) for b in _zahlungs_und_skontobuchungen(make_session, zahlung)
    ] == [
        ("70000", "1200", Decimal("169.05"), None, None),
        ("70000", "3731", Decimal("1.00"), 8, Decimal("0.07")),
        ("70000", "3736", Decimal("2.00"), 9, Decimal("0.38")),
    ]
    assert (p.restbetrag, p.status) == (Decimal("0.00"), PostenStatus.AUSGEGLICHEN)


def test_zahlungsbuchung_traegt_beleg_und_transaktion(umgebung):
    make_session, _ = umgebung
    posten = _mit_posten(make_session)
    zahlung = tx("-172.50")
    with make_session() as s:
        gleiche_aus(s, zahlung, [Anteil(posten, Decimal("172.50"))], EINSTELLUNGEN)
        s.commit()
    (b,) = _zahlungs_und_skontobuchungen(make_session, zahlung)
    assert (b.beleg_id, b.beleg_nummer, b.datum) == (
        posten.beleg_id,
        "RE-2026-0042",
        date(2026, 3, 10),
    )
    assert b.status is BuchungStatus.AUTO_GEBUCHT
    assert "Bürobedarf Müller" in b.buchungstext


def test_teilzahlung_und_rest(umgebung):
    """Akzeptanz 4."""
    make_session, _ = umgebung
    posten = _mit_posten(make_session)
    with make_session() as s:
        gleiche_aus(
            s, tx("-100.00"), [Anteil(posten, Decimal("100.00"))], EINSTELLUNGEN
        )
        s.commit()
        (p,) = lade_posten(s)
    assert (p.restbetrag, p.status) == (Decimal("72.50"), PostenStatus.TEILBEZAHLT)
    with make_session() as s:
        gleiche_aus(s, tx("-72.50"), [Anteil(p, Decimal("72.50"))], EINSTELLUNGEN)
        s.commit()
        (p,) = lade_posten(s)
    assert (p.restbetrag, p.status) == (Decimal("0.00"), PostenStatus.AUSGEGLICHEN)


def test_ueberzahlung_bucht_den_vollen_betrag_und_laesst_das_guthaben_offen(umgebung):
    """Das Guthaben (27,50 beim Kreditor) bleibt als negativer Rest ein offener Posten
    — sonst wichen Personenkonto und Postenliste voneinander ab (Gesamttest B4)."""
    make_session, _ = umgebung
    posten = _mit_posten(make_session)
    zahlung = tx("-200.00")
    with make_session() as s:
        gleiche_aus(s, zahlung, [Anteil(posten, Decimal("200.00"))], EINSTELLUNGEN)
        s.commit()
        (p,) = lade_posten(s)
    (b,) = _zahlungs_und_skontobuchungen(make_session, zahlung)
    assert b.betrag_netto == Decimal("200.00")
    assert (p.restbetrag, p.status) == (Decimal("-27.50"), PostenStatus.TEILBEZAHLT)


def test_skonto_bei_steuerfreier_rechnung(umgebung):
    make_session, _ = umgebung
    beleg = eingangsrechnung(
        netto=Decimal("100.00"),
        steuer=Decimal("0.00"),
        brutto=Decimal("100.00"),
        skonto_prozent=Decimal("3"),
    )
    beleg.positionen = [
        Belegposition(
            beleg_id=beleg.id,
            bezeichnung="Buch",
            netto=Decimal("100.00"),
            steuersatz=Decimal("0"),
            steuer_betrag=Decimal("0.00"),
        )
    ]
    posten = _mit_posten(make_session, beleg)
    zahlung = tx("-97.00")
    with make_session() as s:
        gleiche_aus(
            s,
            zahlung,
            [Anteil(posten, Decimal("97.00"), Decimal("3.00"))],
            EINSTELLUNGEN,
        )
        s.commit()
    assert [
        _zeile(b) for b in _zahlungs_und_skontobuchungen(make_session, zahlung)
    ] == [
        ("70000", "1200", Decimal("97.00"), None, None),
        ("70000", "3730", Decimal("3.00"), None, None),
    ]


def test_ausgang_skonto_mit_umsatzsteuerkorrektur(umgebung):
    make_session, archiv = umgebung
    _ausgangsrechnung(
        make_session,
        archiv,
        entwurf(
            kunde(),
            pos("Bilderrahmen", "250", "4"),
            pos("Katalog", "25", ermaessigt=True),
            skonto_prozent=Decimal("2"),
            skonto_tage=7,
        ),
    )
    _verbuche(make_session, archiv=archiv)
    with make_session() as s:
        (posten,) = lade_posten(s)
    assert (posten.betrag, posten.skonto_betrag) == (
        Decimal("1216.75"),
        Decimal("24.34"),
    )
    zahlung = tx("1192.41", datum=date(2026, 3, 15))
    with make_session() as s:
        gleiche_aus(
            s,
            zahlung,
            [Anteil(posten, Decimal("1192.41"), Decimal("24.34"))],
            EINSTELLUNGEN,
        )
        s.commit()
        (p,) = lade_posten(s)
    assert [
        _zeile(b) for b in _zahlungs_und_skontobuchungen(make_session, zahlung)
    ] == [
        ("1200", "10000", Decimal("1192.41"), None, None),
        ("8731", "10000", Decimal("0.50"), 2, Decimal("0.04")),
        ("8736", "10000", Decimal("20.00"), 3, Decimal("3.80")),
    ]
    assert p.status is PostenStatus.AUSGEGLICHEN


def test_bereits_ausgeglichener_posten_wird_nicht_nochmal_ausgeglichen(umgebung):
    make_session, _ = umgebung
    posten = _mit_posten(make_session)
    with make_session() as s:
        gleiche_aus(
            s, tx("-172.50"), [Anteil(posten, Decimal("172.50"))], EINSTELLUNGEN
        )
        s.commit()
    with make_session() as s, pytest.raises(ValueError, match="ausgeglichen"):
        gleiche_aus(
            s, tx("-172.50"), [Anteil(posten, Decimal("172.50"))], EINSTELLUNGEN
        )
