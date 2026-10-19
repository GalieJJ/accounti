from datetime import date
from decimal import Decimal
from uuid import uuid4

from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_belege,
    lade_buchungen,
    lade_eingaenge,
    speichere_beleg,
    speichere_buchung,
    speichere_eingang,
)
from accounti.models import (
    Beleg,
    BelegEingang,
    Belegposition,
    BelegStatus,
    Buchungssatz,
    Eingangsergebnis,
)


def _session():
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    return make_session


def _beleg(**kw):
    daten = {
        "datei_hash": "a" * 64,
        "dateiname": "rechnung.pdf",
        "kanal": "upload",
        "herkunft": "/tmp/rechnung.pdf",
        "aufbewahren_bis": date(2036, 12, 31),
    }
    daten.update(kw)
    return Beleg(**daten)


def test_roundtrip_beleg_mit_positionen():
    make_session = _session()
    beleg = _beleg(
        belegnummer="RE-2026-0042",
        belegdatum=date(2026, 3, 5),
        lieferant_name="Bürobedarf Müller GmbH",
        netto=Decimal("150.00"),
        steuer=Decimal("23.50"),
        brutto=Decimal("173.50"),
    )
    beleg.positionen = [
        Belegposition(
            beleg_id=beleg.id,
            bezeichnung="Papier",
            netto=Decimal("100.00"),
            steuersatz=Decimal("19"),
            steuer_betrag=Decimal("19.00"),
        ),
        Belegposition(
            beleg_id=beleg.id,
            bezeichnung="Fachbuch",
            netto=Decimal("50.00"),
            steuersatz=Decimal("7"),
            steuer_betrag=Decimal("3.50"),
        ),
    ]
    with make_session() as s:
        speichere_beleg(s, beleg)
        s.commit()
    with make_session() as s:
        (geladen,) = lade_belege(s)
    assert geladen.id == beleg.id
    assert geladen.belegnummer == "RE-2026-0042"
    assert geladen.brutto == Decimal("173.50")
    assert [p.bezeichnung for p in geladen.positionen] == ["Papier", "Fachbuch"]
    assert geladen.positionen[1].steuer_betrag == Decimal("3.50")


def test_lade_belege_filtert_status():
    make_session = _session()
    with make_session() as s:
        speichere_beleg(s, _beleg(datei_hash="a" * 64))
        speichere_beleg(
            s,
            _beleg(
                datei_hash="b" * 64,
                status=BelegStatus.ZUR_PRUEFUNG,
                pruef_grund="unlesbar",
            ),
        )
        s.commit()
    with make_session() as s:
        pruefung = lade_belege(s, status={BelegStatus.ZUR_PRUEFUNG})
    assert len(pruefung) == 1
    assert pruefung[0].pruef_grund == "unlesbar"


def test_roundtrip_eingang():
    make_session = _session()
    eingang = BelegEingang(
        kanal="ordner",
        dateiname="rechnung.pdf",
        herkunft="/eingang/rechnung.pdf",
        datei_hash="a" * 64,
        ergebnis=Eingangsergebnis.DUBLETTE,
        beleg_id=uuid4(),
        hinweis="identische Datei",
    )
    with make_session() as s:
        speichere_eingang(s, eingang)
        s.commit()
    with make_session() as s:
        (geladen,) = lade_eingaenge(s)
    assert geladen.ergebnis is Eingangsergebnis.DUBLETTE
    assert geladen.beleg_id == eingang.beleg_id
    assert geladen.hinweis == "identische Datei"


def test_buchung_behaelt_beleg_position_id():
    make_session = _session()
    pos_id = uuid4()
    b = Buchungssatz(
        transaktion_id=uuid4(),
        datum=date(2026, 4, 1),
        soll_konto="4930",
        haben_konto="1200",
        betrag_netto=Decimal("10"),
        buchungstext="x",
        beleg_position_id=pos_id,
    )
    with make_session() as s:
        speichere_buchung(s, b)
        s.commit()
    with make_session() as s:
        (geladen,) = lade_buchungen(s)
    assert geladen.beleg_position_id == pos_id
