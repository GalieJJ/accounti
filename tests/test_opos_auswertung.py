from datetime import date
from decimal import Decimal
from uuid import uuid4

from accounti.models import OffenerPosten, PostenRichtung, PostenStatus
from accounti.opos.auswertung import (
    STAFFELN,
    faelligkeitsstaffel,
    offene_posten,
    summen_je_kontakt,
    ueberfaellig_tage,
)

STICHTAG = date(2026, 6, 30)
A, B = uuid4(), uuid4()


def op(
    faellig,
    betrag,
    rest=None,
    kontakt=A,
    status=PostenStatus.OFFEN,
    richtung=PostenRichtung.VERBINDLICHKEIT,
):
    return OffenerPosten(
        kontakt_id=kontakt,
        beleg_id=uuid4(),
        richtung=richtung,
        belegdatum=date(2026, 1, 1),
        betrag=Decimal(betrag),
        restbetrag=Decimal(rest if rest is not None else betrag),
        faellig_am=faellig,
        status=status,
    )


POSTEN = [
    op(date(2026, 7, 15), "100.00"),  # nicht fällig
    op(date(2026, 6, 30), "200.00"),  # heute fällig → nicht überfällig
    op(date(2026, 6, 29), "10.00"),  # 1 Tag
    op(date(2026, 5, 31), "20.00", kontakt=B),  # 30 Tage
    op(date(2026, 5, 30), "30.00"),  # 31 Tage
    op(date(2026, 5, 1), "40.00", "15.00", status=PostenStatus.TEILBEZAHLT),  # 60
    op(date(2026, 4, 30), "50.00"),  # 61 Tage
    op(date(2026, 4, 1), "60.00", kontakt=B),  # 90 Tage
    op(date(2026, 3, 31), "70.00"),  # 91 Tage
    op(date(2026, 1, 31), "999.00", "0.00", status=PostenStatus.AUSGEGLICHEN),
    op(date(2026, 5, 1), "500.00", richtung=PostenRichtung.FORDERUNG),
]


def test_ueberfaellige_tage():
    assert [ueberfaellig_tage(p, STICHTAG) for p in POSTEN[:9]] == [
        -15,
        0,
        1,
        30,
        31,
        60,
        61,
        90,
        91,
    ]


def test_faelligkeitsstaffel_gegen_handgerechnete_sollwerte():
    """Akzeptanz 6."""
    verbindlichkeiten = [
        p for p in POSTEN if p.richtung is PostenRichtung.VERBINDLICHKEIT
    ]
    assert faelligkeitsstaffel(verbindlichkeiten, STICHTAG) == {
        "nicht fällig": Decimal("300.00"),
        "1–30 Tage": Decimal("30.00"),
        "31–60 Tage": Decimal("45.00"),
        "61–90 Tage": Decimal("110.00"),
        "über 90 Tage": Decimal("70.00"),
    }
    assert list(faelligkeitsstaffel([], STICHTAG)) == list(STAFFELN)


def test_offene_posten_filter():
    assert len(offene_posten(POSTEN)) == 10
    faellig = offene_posten(
        POSTEN, faellig_bis=STICHTAG, richtung=PostenRichtung.VERBINDLICHKEIT
    )
    assert len(faellig) == 8
    assert all(p.faellig_am <= STICHTAG for p in faellig)


def test_summen_je_kontakt():
    summen = summen_je_kontakt(
        offene_posten(POSTEN, richtung=PostenRichtung.VERBINDLICHKEIT)
    )
    assert summen == {A: Decimal("475.00"), B: Decimal("80.00")}
