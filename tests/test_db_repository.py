from datetime import date
from decimal import Decimal

from accounti.db import init_db, session_factory
from accounti.db.repository import lade_transaktionen, speichere_transaktion
from accounti.models import Transaktion, TransaktionQuelle


def test_roundtrip_transaktion():
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    tx = Transaktion(
        datum=date(2026, 4, 15),
        betrag=Decimal("-89.50"),
        verwendungszweck="AWS",
        quelle=TransaktionQuelle.BANK,
        rohtext="x",
    )
    with make_session() as s:
        speichere_transaktion(s, tx)
        s.commit()
    with make_session() as s:
        geladen = lade_transaktionen(s)
    assert len(geladen) == 1
    assert geladen[0].betrag == Decimal("-89.50")
    assert geladen[0].verwendungszweck == "AWS"
    assert geladen[0].quelle is TransaktionQuelle.BANK
