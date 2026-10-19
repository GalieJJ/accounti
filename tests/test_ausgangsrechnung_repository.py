from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from accounti.db import init_db, session_factory
from accounti.db.repository import (
    fuege_position_hinzu,
    lade_ausgangsrechnung,
    lade_ausgangsrechnungen,
    markiere_ausgestellt,
    speichere_ausgangsrechnung,
)
from accounti.models import (
    AusgangsPosition,
    Ausgangsrechnung,
    AusgangsrechnungStatus,
    Rechnungsempfaenger,
)


def _session():
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    return make_session


def _entwurf():
    return Ausgangsrechnung(
        kunde=Rechnungsempfaenger(
            name="Atelier Kundin GmbH",
            strasse="Kundenstraße 8",
            plz="10115",
            ort="Berlin",
            ust_id="DE888888888",
            email="rechnung@atelier-kundin.example",
        ),
        leistungsdatum=date(2026, 3, 9),
        bestellnummer="PO-77",
    )


def test_positionsnetto():
    p = AusgangsPosition(
        bezeichnung="Rahmen", menge=Decimal("3"), einzelpreis=Decimal("33.333")
    )
    assert p.netto == Decimal("100.00")


def test_entwurf_mit_positionen_roundtrip():
    make_session = _session()
    r = _entwurf()
    with make_session() as s:
        speichere_ausgangsrechnung(s, r)
        fuege_position_hinzu(
            s,
            str(r.id)[:8],
            AusgangsPosition(
                bezeichnung="Beratung",
                menge=Decimal("2"),
                einheit="HUR",
                einzelpreis=Decimal("90"),
                sonstige_leistung=True,
            ),
        )
        fuege_position_hinzu(
            s,
            str(r.id)[:8],
            AusgangsPosition(
                bezeichnung="Katalog", einzelpreis=Decimal("25"), ermaessigt=True
            ),
        )
        s.commit()
    with make_session() as s:
        geladen = lade_ausgangsrechnung(s, str(r.id)[:8])
        (einzige,) = lade_ausgangsrechnungen(s)
    assert einzige.id == r.id
    assert geladen.status is AusgangsrechnungStatus.ENTWURF
    assert geladen.nummer is None
    assert geladen.kunde.ust_id == "DE888888888"
    assert geladen.bestellnummer == "PO-77"
    assert [
        (p.bezeichnung, p.einheit, p.sonstige_leistung, p.ermaessigt)
        for p in geladen.positionen
    ] == [
        ("Beratung", "HUR", True, False),
        ("Katalog", "C62", False, True),
    ]
    assert geladen.positionen[0].netto == Decimal("180.00")


def test_ausgestellte_rechnung_ist_unveraenderlich():
    make_session = _session()
    r = _entwurf()
    with make_session() as s:
        speichere_ausgangsrechnung(s, r)
        markiere_ausgestellt(
            s,
            r.id,
            nummer="2026-0001",
            rechnungsdatum=date(2026, 3, 10),
            zahlungsziel=date(2026, 3, 24),
            beleg_id=uuid4(),
            datei_hash="a" * 64,
        )
        s.commit()
        with pytest.raises(ValueError, match="ausgestellt"):
            fuege_position_hinzu(
                s,
                "2026-0001",
                AusgangsPosition(bezeichnung="x", einzelpreis=Decimal("1")),
            )
        geladen = lade_ausgangsrechnung(s, "2026-0001")
    assert geladen.status is AusgangsrechnungStatus.AUSGESTELLT
    assert geladen.rechnungsdatum == date(2026, 3, 10)


def test_unbekannte_rechnung():
    make_session = _session()
    with make_session() as s, pytest.raises(ValueError, match="Keine Rechnung"):
        lade_ausgangsrechnung(s, "abc")
