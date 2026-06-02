from datetime import date
from decimal import Decimal

import pytest

from accounti.db import init_db, session_factory
from accounti.db.repository import (
    aktualisiere_buchung,
    finde_buchung,
    lade_buchungen,
    lade_pruefliste,
    setze_status,
    speichere_buchung,
    speichere_transaktion,
)
from accounti.models import (
    Buchungssatz,
    BuchungStatus,
    Transaktion,
    TransaktionQuelle,
)


def _setup():
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    return make_session


def _tx(**kw) -> Transaktion:
    base = dict(
        datum=date(2026, 4, 15),
        betrag=Decimal("-119.00"),
        verwendungszweck="TEST",
        quelle=TransaktionQuelle.BANK,
        rohtext="x",
    )
    base.update(kw)
    return Transaktion(**base)


def _b(tx: Transaktion, status: BuchungStatus, **kw) -> Buchungssatz:
    base = dict(
        transaktion_id=tx.id,
        datum=tx.datum,
        soll_konto="4930",
        haben_konto="1200",
        betrag_netto=Decimal("100.00"),
        steuer_schluessel=9,
        steuer_betrag=Decimal("19.00"),
        buchungstext="TEST",
        status=status,
        confidence=0.5,
    )
    base.update(kw)
    return Buchungssatz(**base)


def test_lade_buchungen_status_filter():
    ms = _setup()
    tx = _tx()
    with ms() as s:
        speichere_transaktion(s, tx)
        speichere_buchung(s, _b(tx, BuchungStatus.AUTO_GEBUCHT))
        speichere_buchung(s, _b(tx, BuchungStatus.ZUR_PRUEFUNG))
        s.commit()
    with ms() as s:
        auto = lade_buchungen(s, status={BuchungStatus.AUTO_GEBUCHT})
        assert len(auto) == 1
        assert len(lade_buchungen(s)) == 2


def test_pruefliste_joins_transaktion():
    ms = _setup()
    tx = _tx(verwendungszweck="STADTWERKE STROM")
    with ms() as s:
        speichere_transaktion(s, tx)
        speichere_buchung(s, _b(tx, BuchungStatus.ZUR_PRUEFUNG))
        speichere_buchung(s, _b(tx, BuchungStatus.AUTO_GEBUCHT))
        s.commit()
    with ms() as s:
        liste = lade_pruefliste(s)
        assert len(liste) == 1
        buchung, transaktion = liste[0]
        assert buchung.status is BuchungStatus.ZUR_PRUEFUNG
        assert transaktion is not None
        assert transaktion.verwendungszweck == "STADTWERKE STROM"


def test_setze_status_bestaetigt():
    ms = _setup()
    tx = _tx()
    b = _b(tx, BuchungStatus.ZUR_PRUEFUNG)
    with ms() as s:
        speichere_transaktion(s, tx)
        speichere_buchung(s, b)
        s.commit()
    prefix = str(b.id)[:8]
    with ms() as s:
        aktualisiert = setze_status(
            s, prefix, BuchungStatus.GEPRUEFT, geprueft_von="jan"
        )
        s.commit()
        assert aktualisiert.status is BuchungStatus.GEPRUEFT
        assert aktualisiert.geprueft_von == "jan"
    with ms() as s:
        assert finde_buchung(s, prefix).status is BuchungStatus.GEPRUEFT


def test_finde_buchung_unbekannt_raises():
    ms = _setup()
    with ms() as s, pytest.raises(ValueError):
        finde_buchung(s, "deadbeef")


def test_aktualisiere_buchung_ueberschreibt():
    ms = _setup()
    tx = _tx()
    b = _b(tx, BuchungStatus.ZUR_PRUEFUNG, soll_konto="4900")
    with ms() as s:
        speichere_transaktion(s, tx)
        speichere_buchung(s, b)
        s.commit()
    prefix = str(b.id)[:8]
    neu = _b(tx, BuchungStatus.KORRIGIERT, soll_konto="4930", buchungstext="korrigiert")
    neu = neu.model_copy(update={"id": b.id})
    with ms() as s:
        aktualisiere_buchung(s, prefix, neu)
        s.commit()
    with ms() as s:
        geladen = finde_buchung(s, prefix)
        assert geladen.soll_konto == "4930"
        assert geladen.buchungstext == "korrigiert"
        assert geladen.status is BuchungStatus.KORRIGIERT
