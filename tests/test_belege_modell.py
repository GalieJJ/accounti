from datetime import date
from decimal import Decimal
from uuid import uuid4

from accounti.models import (
    Beleg,
    Belegart,
    Belegposition,
    Belegrichtung,
    BelegStatus,
    Buchungssatz,
)


def test_beleg_defaults():
    b = Beleg(
        datei_hash="a" * 64,
        dateiname="rechnung.pdf",
        kanal="upload",
        herkunft="/tmp/rechnung.pdf",
        aufbewahren_bis=date(2036, 12, 31),
    )
    assert b.status is BelegStatus.EINGEGANGEN
    assert b.belegart is Belegart.UNBEKANNT
    assert b.richtung is Belegrichtung.EINGANG
    assert b.positionen == []
    assert b.pruef_grund is None


def test_belegposition_traegt_beleg_id():
    beleg_id = uuid4()
    p = Belegposition(
        beleg_id=beleg_id,
        bezeichnung="Büromaterial",
        netto=Decimal("100.00"),
        steuersatz=Decimal("19"),
        steuer_betrag=Decimal("19.00"),
    )
    assert p.beleg_id == beleg_id
    assert p.menge == Decimal("1")


def test_buchungssatz_beleg_position_optional():
    b = Buchungssatz(
        transaktion_id=uuid4(),
        datum=date(2026, 4, 1),
        soll_konto="4930",
        haben_konto="1200",
        betrag_netto=Decimal("10"),
        buchungstext="x",
    )
    assert b.beleg_position_id is None
