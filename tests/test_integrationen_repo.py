"""Persistenz der Marktplatz-Abrechnungen: Posten, Befunde, Status."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from accounti.db import init_db, session_factory
from accounti.db.repo_integrationen import (
    abrechnung_vorhanden,
    ergaenze_befunde,
    lade_abrechnung,
    lade_abrechnungen,
    setze_abrechnungsstatus,
    setze_bank_transaktion,
    speichere_abrechnung,
    vorhandene_referenzen,
)
from accounti.models.integrationen import (
    Abrechnung,
    AbrechnungStatus,
    Befund,
    Gebuehrenart,
    Marktplatzposten,
    Postenart,
    Schweregrad,
)


@pytest.fixture
def session(tmp_path):
    engine, make = session_factory(f"sqlite:///{tmp_path / 'r.db'}")
    init_db(engine)
    with make() as s:
        yield s


def _abrechnung():
    return Abrechnung(
        marktplatz="paypal",
        nummer="PayPal 2026-08-01 bis 2026-08-31",
        von=date(2026, 8, 1),
        bis=date(2026, 8, 31),
        auszahlung=None,
        kurs=Decimal("1.083400"),
        anfangssaldo=Decimal("100.00"),
        endsaldo=Decimal("112.36"),
        dateiname="pp.csv",
        beleg_id=uuid4(),
        posten=[
            Marktplatzposten(
                nr=2,
                art=Postenart.ERLOES,
                datum=date(2026, 8, 2),
                betrag=Decimal("119.00"),
                bestimmungsland="DE",
                bestellnummer="1AB",
                referenz="1AB",
                gegenpartei="Kunde Eins",
            ),
            Marktplatzposten(
                nr=2,
                art=Postenart.GEBUEHR,
                datum=date(2026, 8, 2),
                betrag=Decimal("-3.18"),
                gebuehrenart=Gebuehrenart.ZAHLUNG,
                referenz="1AB",
            ),
        ],
        befunde=[Befund(code="x", schweregrad=Schweregrad.HINWEIS, text="Hinweis")],
    )


def test_speichern_und_laden(session):
    a = _abrechnung()
    speichere_abrechnung(session, a)
    (geladen,) = lade_abrechnungen(session)
    assert geladen == a
    assert lade_abrechnung(session, a.nummer).id == a.id
    assert lade_abrechnung(session, str(a.id)[:8]).id == a.id
    assert abrechnung_vorhanden(session, "paypal", a.nummer)
    assert not abrechnung_vorhanden(session, "amazon", a.nummer)
    assert vorhandene_referenzen(session, "paypal") == {"1AB"}
    with pytest.raises(ValueError, match="Keine Abrechnung"):
        lade_abrechnung(session, "gibtsnicht")


def test_befunde_nicht_doppelt(session):
    a = _abrechnung()
    speichere_abrechnung(session, a)
    neu = Befund(code="y", schweregrad=Schweregrad.FEHLER, text="Abweichung")
    assert ergaenze_befunde(session, a.id, [neu, a.befunde[0]]) == 1
    assert ergaenze_befunde(session, a.id, [neu]) == 0
    assert [b.code for b in lade_abrechnungen(session)[0].befunde] == ["x", "y"]


def test_bank_und_status(session):
    a = _abrechnung()
    speichere_abrechnung(session, a)
    tx = uuid4()
    setze_bank_transaktion(session, a.posten[0].id, tx)
    setze_abrechnungsstatus(session, a.id, AbrechnungStatus.ABGEGLICHEN)
    (geladen,) = lade_abrechnungen(session)
    assert geladen.posten[0].bank_transaktion_id == tx
    assert geladen.status is AbrechnungStatus.ABGEGLICHEN
