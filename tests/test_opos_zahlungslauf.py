"""Ende zu Ende: Beleg → Posten → Banktransaktion → Ausgleich (Akzeptanz 2–5)."""

from datetime import date
from decimal import Decimal

import pytest

from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_buchungen,
    lade_posten,
    lade_zuordnungen,
    speichere_beleg,
    speichere_buchung,
    speichere_transaktion,
)
from accounti.models import (
    Belegposition,
    Buchungssatz,
    BuchungStatus,
    PostenStatus,
    Transaktion,
    TransaktionQuelle,
    ZuordnungStatus,
)
from accounti.opos.zahlungslauf import (
    ZahlungslaufError,
    bestaetige,
    lehne_ab,
    offene_transaktionen,
    zuordne_zahlungen,
)
from tests.test_opos_verbuchung import EINSTELLUNGEN, _verbuche, eingangsrechnung


@pytest.fixture
def make_session(tmp_path):
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    return make_session


def _rechnungen(make_session, *belege):
    with make_session() as s:
        for b in belege or (eingangsrechnung(),):
            speichere_beleg(s, b)
        s.commit()
    _verbuche(make_session)


def _zahlung(make_session, betrag, zweck, datum=date(2026, 3, 10), name=None):
    t = Transaktion(
        datum=datum,
        betrag=Decimal(betrag),
        verwendungszweck=zweck,
        gegenkonto_name=name,
        quelle=TransaktionQuelle.BANK,
        rohtext=zweck,
    )
    with make_session() as s:
        speichere_transaktion(s, t)
        s.commit()
    return t


def _lauf(make_session):
    with make_session() as s:
        lauf = zuordne_zahlungen(s, EINSTELLUNGEN)
        s.commit()
    return lauf


def _rechnung(nummer, brutto, hash_):
    b = eingangsrechnung(
        datei_hash=hash_ * 64,
        belegnummer=nummer,
        netto=Decimal(brutto),
        steuer=Decimal("0"),
        brutto=Decimal(brutto),
        skonto_prozent=None,
        skonto_tage=None,
        zahlungsziel=None,
    )
    b.positionen = [
        Belegposition(
            beleg_id=b.id,
            bezeichnung="x",
            netto=Decimal(brutto),
            steuersatz=Decimal("0"),
            steuer_betrag=Decimal("0"),
        )
    ]
    return b


def test_passende_zahlung_gleicht_automatisch_aus(make_session):
    """Akzeptanz 2."""
    _rechnungen(make_session)
    t = _zahlung(make_session, "-172.50", "RE-2026-0042")
    lauf = _lauf(make_session)
    assert [tx.id for tx, _ in lauf.gebucht] == [t.id]
    with make_session() as s:
        (p,) = lade_posten(s)
        (z,) = lade_zuordnungen(s)
    assert p.status is PostenStatus.AUSGEGLICHEN
    assert (z.transaktion_id, z.posten_id, z.status) == (
        t.id,
        p.id,
        ZuordnungStatus.GEBUCHT,
    )


def test_skonto_gleicht_vollstaendig_aus_mit_vorsteuerkorrektur(make_session):
    """Akzeptanz 3."""
    _rechnungen(make_session)
    t = _zahlung(make_session, "-169.05", "RE-2026-0042 abzgl. Skonto")
    _lauf(make_session)
    with make_session() as s:
        (p,) = lade_posten(s)
        skonto = [
            b
            for b in lade_buchungen(s)
            if b.transaktion_id == t.id and b.haben_konto != "1200"
        ]
    assert p.status is PostenStatus.AUSGEGLICHEN
    assert sorted((b.haben_konto, b.betrag_netto, b.steuer_betrag) for b in skonto) == [
        ("3731", Decimal("1.00"), Decimal("0.07")),
        ("3736", Decimal("2.00"), Decimal("0.38")),
    ]


def test_teilzahlung_und_zweite_zahlung(make_session):
    """Akzeptanz 4."""
    _rechnungen(make_session)
    _zahlung(make_session, "-100.00", "RE-2026-0042 Teilzahlung")
    _lauf(make_session)
    with make_session() as s:
        (p,) = lade_posten(s)
    assert (p.restbetrag, p.status) == (Decimal("72.50"), PostenStatus.TEILBEZAHLT)
    _zahlung(make_session, "-72.50", "RE-2026-0042 Rest", datum=date(2026, 4, 1))
    _lauf(make_session)
    with make_session() as s:
        (p,) = lade_posten(s)
    assert (p.restbetrag, p.status) == (Decimal("0.00"), PostenStatus.AUSGEGLICHEN)


def test_sammelzahlung_wird_vorgeschlagen_und_nach_bestaetigung_aufgeteilt(
    make_session,
):
    """Akzeptanz 5."""
    _rechnungen(
        make_session,
        _rechnung("RE-1001", "100.00", "1"),
        _rechnung("RE-1002", "200.00", "2"),
        _rechnung("RE-1003", "300.00", "3"),
    )
    t = _zahlung(make_session, "-600.00", "Sammelzahlung RE-1001 RE-1002 RE-1003")
    lauf = _lauf(make_session)
    assert lauf.gebucht == []
    ((tx, vorschlag),) = lauf.vorgeschlagen
    assert tx.id == t.id and len(vorschlag.anteile) == 3
    with make_session() as s:
        assert {p.status for p in lade_posten(s)} == {PostenStatus.OFFEN}
        assert not [b for b in lade_buchungen(s) if b.transaktion_id == t.id]
        buchungen = bestaetige(s, str(t.id)[:8], EINSTELLUNGEN)
        s.commit()
        posten = {p.belegnummer: p for p in lade_posten(s)}
        zuordnungen = lade_zuordnungen(s)
    assert sorted(b.betrag_netto for b in buchungen) == [
        Decimal("100.00"),
        Decimal("200.00"),
        Decimal("300.00"),
    ]
    assert all(b.status is BuchungStatus.GEPRUEFT for b in buchungen)
    assert {p.status for p in posten.values()} == {PostenStatus.AUSGEGLICHEN}
    assert {z.status for z in zuordnungen} == {ZuordnungStatus.GEBUCHT}


def test_vorgeschlagene_posten_werden_nicht_doppelt_vergeben(make_session):
    _rechnungen(
        make_session,
        _rechnung("RE-1001", "100.00", "1"),
        _rechnung("RE-1002", "200.00", "2"),
    )
    _zahlung(make_session, "-300.00", "RE-1001 RE-1002")
    _lauf(make_session)  # Vorschlag reserviert beide Posten
    _zahlung(make_session, "-100.00", "RE-1001")
    lauf = _lauf(make_session)
    assert lauf.gebucht == [] and lauf.vorgeschlagen == []


def test_ablehnen_gibt_die_transaktion_frei(make_session):
    _rechnungen(
        make_session,
        _rechnung("RE-1001", "100.00", "1"),
        _rechnung("RE-1002", "200.00", "2"),
    )
    t = _zahlung(make_session, "-300.00", "RE-1001 RE-1002")
    _lauf(make_session)
    with make_session() as s:
        assert t.id not in {tx.id for tx in offene_transaktionen(s)}
        lehne_ab(s, str(t.id)[:8])
        s.commit()
        assert {z.status for z in lade_zuordnungen(s)} == {ZuordnungStatus.ABGELEHNT}
        # frei für die Kontierung, aber nicht erneut vorgeschlagen
        assert t.id in {tx.id for tx in offene_transaktionen(s, fuer_kontierung=True)}
    assert _lauf(make_session).vorgeschlagen == []


def test_bereits_kontierte_transaktion_wird_nicht_zugeordnet(make_session):
    _rechnungen(make_session)
    t = _zahlung(make_session, "-172.50", "RE-2026-0042")
    with make_session() as s:
        speichere_buchung(
            s,
            Buchungssatz(
                transaktion_id=t.id,
                datum=t.datum,
                soll_konto="4930",
                haben_konto="1200",
                betrag_netto=Decimal("172.50"),
                buchungstext="schon kontiert",
            ),
        )
        s.commit()
    lauf = _lauf(make_session)
    assert lauf.gebucht == [] and lauf.vorgeschlagen == []


def test_bestaetigen_unbekannt_oder_ohne_vorschlag(make_session):
    with make_session() as s, pytest.raises(ZahlungslaufError, match="Kein Vorschlag"):
        bestaetige(s, "deadbeef", EINSTELLUNGEN)


def test_zeitraum_filter(make_session):
    _rechnungen(make_session)
    _zahlung(make_session, "-172.50", "RE-2026-0042", datum=date(2026, 4, 2))
    with make_session() as s:
        assert zuordne_zahlungen(s, EINSTELLUNGEN, zeitraum="2026-03").gebucht == []
        assert len(zuordne_zahlungen(s, EINSTELLUNGEN, zeitraum="2026-04").gebucht) == 1
