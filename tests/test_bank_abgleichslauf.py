from datetime import date
from decimal import Decimal

import pytest

from accounti.bank.abgleichslauf import (
    AbgleichError,
    bestaetige_abgleich,
    gleiche_belege_ab,
    lehne_abgleich_ab,
    offen_in_der_bank,
)
from accounti.buchung.kontierung import kontiere_umsaetze
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_abgleiche,
    lade_buchungen,
    speichere_beleg,
    speichere_buchung,
    speichere_transaktion,
)
from accounti.klassifikation.engine import KlassifikationsEngine, RegelwerkEngine
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    AbgleichStatus,
    Belegart,
    Belegposition,
    BelegStatus,
    Buchungssatz,
    BuchungStatus,
)
from accounti.opos.zahlungslauf import offene_transaktionen
from tests.test_bank_abgleich import quittung, umsatz
from tests.test_buchung_mit_beleg import TANKEN

EINSTELLUNGEN = Buchhaltung()


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'b.db'}")
    init_db(engine)
    yield factory
    engine.dispose()


def _anlegen(make_session, transaktionen=(), belege=()):
    with make_session() as s:
        for tx in transaktionen:
            speichere_transaktion(s, tx)
        for b in belege:
            speichere_beleg(s, b)
        s.commit()


def _lauf(make_session, **kw):
    with make_session() as s:
        ergebnis = gleiche_belege_ab(s, **kw)
        s.commit()
    return ergebnis


def _abgleiche(make_session, status=None):
    with make_session() as s:
        return lade_abgleiche(s, status=status)


def test_eindeutiges_wird_bestaetigt_und_nicht_wiederholt(make_session):
    tx, b = umsatz(), quittung()
    _anlegen(make_session, [tx], [b])
    ergebnis = _lauf(make_session)
    assert len(ergebnis.automatisch) == 1
    (a,) = _abgleiche(make_session)
    assert (a.transaktion_id, a.beleg_id, a.status) == (
        tx.id,
        b.id,
        AbgleichStatus.BESTAETIGT,
    )
    assert a.stufe == "exakt" and a.differenz == 0
    nochmal = _lauf(make_session)
    assert (nochmal.automatisch, nochmal.vorschlaege) == ([], [])
    assert len(_abgleiche(make_session)) == 1


def test_nur_quittungen_und_sonstige_erfasste_belege(make_session):
    rechnung = quittung(belegart=Belegart.EINGANGSRECHNUNG)
    in_pruefung = quittung(status=BelegStatus.ZUR_PRUEFUNG)
    _anlegen(make_session, [umsatz()], [rechnung, in_pruefung])
    ergebnis = _lauf(make_session)
    assert ergebnis.automatisch == [] and ergebnis.ohne_treffer == 1


def test_gebuchte_umsaetze_bleiben_unberuehrt(make_session):
    tx, b = umsatz(), quittung()
    _anlegen(make_session, [tx], [b])
    with make_session() as s:
        speichere_buchung(
            s,
            Buchungssatz(
                transaktion_id=tx.id,
                datum=tx.datum,
                soll_konto="4530",
                haben_konto="1200",
                betrag_netto=Decimal("59.50"),
                buchungstext="schon kontiert",
            ),
        )
        s.commit()
    assert _lauf(make_session).automatisch == []


def test_bestaetigen_verwirft_die_konkurrenz(make_session):
    t1, t2, b1, b2 = umsatz(), umsatz(), quittung(), quittung()
    _anlegen(make_session, [t1, t2], [b1, b2])
    ergebnis = _lauf(make_session)
    assert len(ergebnis.vorschlaege) == 4
    (gewaehlt,) = [
        a
        for a in _abgleiche(make_session)
        if (a.transaktion_id, a.beleg_id) == (t1.id, b1.id)
    ]
    with make_session() as s:
        bestaetige_abgleich(s, str(gewaehlt.id)[:8])
        s.commit()
    status = {
        (a.transaktion_id, a.beleg_id): a.status for a in _abgleiche(make_session)
    }
    assert status == {
        (t1.id, b1.id): AbgleichStatus.BESTAETIGT,
        (t1.id, b2.id): AbgleichStatus.ABGELEHNT,
        (t2.id, b1.id): AbgleichStatus.ABGELEHNT,
        (t2.id, b2.id): AbgleichStatus.VORGESCHLAGEN,
    }


def test_ablehnen_und_nicht_wieder_vorschlagen(make_session):
    tx = umsatz(gegenkonto_name="SumUp", verwendungszweck="SUMUP *KIOSK")
    _anlegen(make_session, [tx], [quittung()])
    (vorschlag,) = _lauf(make_session).vorschlaege
    (a,) = _abgleiche(make_session)
    with make_session() as s:
        lehne_abgleich_ab(s, str(a.id)[:8])
        s.commit()
    assert _abgleiche(make_session)[0].status is AbgleichStatus.ABGELEHNT
    nochmal = _lauf(make_session)
    assert nochmal.vorschlaege == [] and nochmal.ohne_treffer == 1
    assert vorschlag.beleg.id == a.beleg_id


def test_unbekannter_vorschlag(make_session):
    with make_session() as s, pytest.raises(AbgleichError, match="Kein Vorschlag"):
        bestaetige_abgleich(s, "deadbeef")


def test_offener_vorschlag_haelt_zuordnung_und_kontierung_fern(make_session):
    tx = umsatz(gegenkonto_name="SumUp", verwendungszweck="SUMUP *KIOSK")
    _anlegen(make_session, [tx], [quittung()])
    _lauf(make_session)
    with make_session() as s:
        assert offene_transaktionen(s) == []
        assert offene_transaktionen(s, fuer_kontierung=True) == []


def test_bestaetigter_abgleich_geht_in_die_kontierung_nicht_in_die_zuordnung(
    make_session,
):
    _anlegen(make_session, [umsatz()], [quittung()])
    _lauf(make_session)
    with make_session() as s:
        assert offene_transaktionen(s) == []
        assert len(offene_transaktionen(s, fuer_kontierung=True)) == 1


def test_zeitraum(make_session):
    _anlegen(make_session, [umsatz()], [quittung()])
    assert _lauf(make_session, zeitraum="2026-04").ohne_treffer == 0
    assert len(_lauf(make_session, zeitraum="2026-03").automatisch) == 1


# --- Akzeptanz 3: mit Beleg kontiert die Regel, was ohne Beleg offen bleibt ---------


def _kontiere(make_session):
    engine = KlassifikationsEngine(regelwerk=RegelwerkEngine([TANKEN]))
    with make_session() as s:
        lauf = kontiere_umsaetze(s, engine, EINSTELLUNGEN)
        s.commit()
    return lauf


def test_beleg_hebt_die_regel_trefferquote(make_session):
    """Akzeptanz 3."""
    tx = umsatz(
        betrag="-70.20",
        gegenkonto_name="SumUp Payments",
        verwendungszweck="SUMUP *SHELL STATION 4711",
    )
    b = quittung(brutto="70.20")
    b = b.model_copy(
        update={
            "positionen": [
                Belegposition(
                    beleg_id=b.id,
                    bezeichnung="Super E10",
                    netto=Decimal("50.00"),
                    steuersatz=Decimal("19"),
                    steuer_betrag=Decimal("9.50"),
                ),
                Belegposition(
                    beleg_id=b.id,
                    bezeichnung="Snack",
                    netto=Decimal("10.00"),
                    steuersatz=Decimal("7"),
                    steuer_betrag=Decimal("0.70"),
                ),
            ]
        }
    )
    _anlegen(make_session, [tx], [b])

    ohne = _kontiere(make_session)  # ohne Abgleich: die Regel greift nicht
    assert (ohne.kontiert, ohne.mit_beleg, ohne.offen) == (0, 0, 1)

    assert len(_lauf(make_session).automatisch) == 1
    mit = _kontiere(make_session)
    assert (mit.kontiert, mit.mit_beleg, mit.offen) == (1, 1, 0)
    with make_session() as s:
        buchungen = sorted(lade_buchungen(s), key=lambda x: -x.betrag_netto)
    assert [
        (x.soll_konto, x.betrag_netto, x.steuer_schluessel, x.steuer_betrag)
        for x in buchungen
    ] == [
        ("4530", Decimal("50.00"), 9, Decimal("9.50")),
        ("4530", Decimal("10.00"), 8, Decimal("0.70")),
    ]
    assert all(x.beleg_id == b.id and x.transaktion_id == tx.id for x in buchungen)
    assert all(x.status is BuchungStatus.AUTO_GEBUCHT for x in buchungen)

    # zweiter Lauf: nichts doppelt, und der Beleg ist verbraucht
    assert _kontiere(make_session).kontiert == 0
    assert _lauf(make_session).automatisch == []


def test_ohne_beleg_kontiert_wie_bisher(make_session):
    tx = umsatz(gegenkonto_name="SHELL DEUTSCHLAND", tag=0)
    _anlegen(make_session, [tx])
    lauf = _kontiere(make_session)
    assert (lauf.kontiert, lauf.mit_beleg, lauf.offen) == (1, 0, 0)
    with make_session() as s:
        (x,) = lade_buchungen(s)
    assert x.beleg_id is None and x.soll_konto == "4530"


# --- Bericht -------------------------------------------------------------------------


def test_offen_in_der_bank(make_session):
    gefunden, ohne_beleg = umsatz(), umsatz(betrag="-12.00", tag=2)
    belegt, ohne_umsatz = quittung(), quittung(brutto="5.00", lieferant_name="Parken")
    rechnung = quittung(belegart=Belegart.EINGANGSRECHNUNG, brutto="99.00")
    _anlegen(make_session, [gefunden, ohne_beleg], [belegt, ohne_umsatz, rechnung])
    _lauf(make_session)
    with make_session() as s:
        bericht = offen_in_der_bank(s)
    assert [t.id for t in bericht.umsaetze_ohne_beleg] == [ohne_beleg.id]
    assert [b.id for b in bericht.belege_ohne_umsatz] == [ohne_umsatz.id]
    assert date(2026, 3, 14) == bericht.umsaetze_ohne_beleg[0].datum
