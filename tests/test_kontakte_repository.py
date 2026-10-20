from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from accounti.db import init_db, session_factory
from accounti.db.repository import (
    aktualisiere_kontakt,
    lade_buchungen,
    lade_kontakt,
    lade_kontakte,
    lade_posten,
    speichere_buchung,
    speichere_kontakt,
    speichere_posten,
    verbuchte_beleg_ids,
)
from accounti.models import (
    Buchungssatz,
    Kontakt,
    KontaktStatus,
    OffenerPosten,
    PostenRichtung,
    PostenStatus,
)


@pytest.fixture
def make_session():
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    return make_session


def test_kontakt_roundtrip_und_suche(make_session):
    k = Kontakt(
        name="Bürobedarf Müller GmbH",
        kreditor_konto="70001",
        iban="DE89370400440532013000",
        zahlungsziel_tage=30,
        skonto_prozent=Decimal("2"),
        skonto_tage=10,
        sachkonto="4930",
        status=KontaktStatus.ZUR_PRUEFUNG,
        pruef_grund="neu angelegt",
    )
    with make_session() as s:
        speichere_kontakt(s, k)
        s.commit()
    with make_session() as s:
        (geladen,) = lade_kontakte(s)
        assert lade_kontakt(s, "70001").id == k.id
        assert lade_kontakt(s, str(k.id)[:8]).id == k.id
        geaendert = aktualisiere_kontakt(
            s,
            k.model_copy(
                update={"status": KontaktStatus.GEPRUEFT, "sachkonto": "4910"}
            ),
        )
        s.commit()
    assert geladen.skonto_prozent == Decimal("2")
    assert geladen.status is KontaktStatus.ZUR_PRUEFUNG
    assert geaendert.sachkonto == "4910"


def test_unbekannter_kontakt(make_session):
    with make_session() as s, pytest.raises(ValueError, match="Kein Kontakt"):
        lade_kontakt(s, "79999")


def test_posten_roundtrip(make_session):
    beleg_id = uuid4()
    p = OffenerPosten(
        kontakt_id=uuid4(),
        beleg_id=beleg_id,
        richtung=PostenRichtung.VERBINDLICHKEIT,
        belegnummer="RE-1",
        belegdatum=date(2026, 3, 5),
        betrag=Decimal("172.50"),
        faellig_am=date(2026, 3, 19),
        skonto_bis=date(2026, 3, 12),
        skonto_prozent=Decimal("2"),
        skonto_betrag=Decimal("3.45"),
    )
    assert p.restbetrag == Decimal("172.50")
    with make_session() as s:
        speichere_posten(s, p)
        s.commit()
    with make_session() as s:
        (geladen,) = lade_posten(s)
        assert lade_posten(s, richtung=PostenRichtung.FORDERUNG) == []
        assert lade_posten(s, status={PostenStatus.OFFEN})[0].id == p.id
        assert verbuchte_beleg_ids(s) == {beleg_id}
    assert geladen.skonto_betrag == Decimal("3.45")
    assert geladen.status is PostenStatus.OFFEN


def test_buchung_ohne_transaktion(make_session):
    beleg_id = uuid4()
    b = Buchungssatz(
        beleg_id=beleg_id,
        datum=date(2026, 3, 5),
        soll_konto="4930",
        haben_konto="70001",
        betrag_netto=Decimal("100"),
        buchungstext="Bürobedarf",
        beleg_nummer="RE-2026-0042",
    )
    with make_session() as s:
        speichere_buchung(s, b)
        s.commit()
    with make_session() as s:
        (geladen,) = lade_buchungen(s)
    assert geladen.transaktion_id is None
    assert geladen.beleg_id == beleg_id
    assert geladen.beleg_nummer == "RE-2026-0042"  # DATEV Belegfeld 1
