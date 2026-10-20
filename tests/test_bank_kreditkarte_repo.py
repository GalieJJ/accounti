from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from accounti.db import init_db, session_factory
from accounti.db.repo_bank import (
    abgerechnete_transaktion_ids,
    aktualisiere_abrechnung,
    lade_abrechnungen,
    lade_kreditkarte,
    lade_kreditkarten,
    lade_transaktionen_nach_schluessel,
    speichere_abrechnung,
    speichere_kreditkarte,
)
from accounti.db.repository import speichere_bankkonto, speichere_transaktion
from accounti.models import Bankkonto, Transaktion, TransaktionQuelle
from accounti.models.bank import (
    AbrechnungStatus,
    Kreditkarte,
    Kreditkartenabrechnung,
)


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'k.db'}")
    init_db(engine)
    yield factory
    engine.dispose()


def _konten(s):
    giro = Bankkonto(iban="DE02120300000000202051", bezeichnung="Giro")
    karte = Bankkonto(
        iban="VISA1234", bezeichnung="Visa", sachkonto="1730", provider="abrechnung"
    )
    speichere_bankkonto(s, giro)
    speichere_bankkonto(s, karte)
    return giro, karte


def test_karte_speichern_und_laden(make_session):
    with make_session() as s:
        giro, konto = _konten(s)
        karte = Kreditkarte(
            bankkonto_id=konto.id,
            girokonto_id=giro.id,
            endziffern="1234",
            abrechnungstag=20,
        )
        speichere_kreditkarte(s, karte)
        s.commit()
        assert lade_kreditkarten(s) == [karte]
        assert lade_kreditkarte(s, "visa 1234") == karte
        assert lade_kreditkarte(s, str(karte.id)[:8]) == karte
        with pytest.raises(ValueError, match="Keine Kreditkarte"):
            lade_kreditkarte(s, "DE02120300000000202051")
        with pytest.raises(ValueError, match="schon"):
            speichere_kreditkarte(s, karte.model_copy(update={"id": uuid4()}))


def test_abrechnung_mit_umsaetzen(make_session):
    with make_session() as s:
        giro, konto = _konten(s)
        karte = Kreditkarte(bankkonto_id=konto.id, girokonto_id=giro.id)
        speichere_kreditkarte(s, karte)
        tx = Transaktion(
            datum=date(2026, 3, 2),
            betrag=Decimal("-23.99"),
            verwendungszweck="AMAZON",
            quelle=TransaktionQuelle.BANK,
            rohtext="",
            dublettenschluessel="a" * 64,
        )
        speichere_transaktion(s, tx)
        a = Kreditkartenabrechnung(
            kreditkarte_id=karte.id,
            stichtag=date(2026, 3, 31),
            summe=Decimal("-23.99"),
            anzahl=1,
        )
        speichere_abrechnung(s, a, [tx.id])
        s.commit()
        assert lade_abrechnungen(s) == [a]
        assert lade_abrechnungen(s, kreditkarte_id=uuid4()) == []
        assert abgerechnete_transaktion_ids(s) == {tx.id}
        gefunden = lade_transaktionen_nach_schluessel(s, ["a" * 64, "b" * 64])
        assert {k: t.id for k, t in gefunden.items()} == {"a" * 64: tx.id}
        neu = a.model_copy(
            update={
                "status": AbrechnungStatus.ABWEICHUNG,
                "belastung_id": uuid4(),
                "belastung_betrag": Decimal("-24.00"),
                "befund": "Differenz -0,01 €",
            }
        )
        aktualisiere_abrechnung(s, neu)
        s.commit()
        (gespeichert,) = lade_abrechnungen(s, status={AbrechnungStatus.ABWEICHUNG})
        assert gespeichert == neu
        assert gespeichert.differenz == Decimal("-0.01")
