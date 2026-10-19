from datetime import date, timedelta
from decimal import Decimal

from accounti.belege.dubletten import pruefe_dublette
from accounti.models import Beleg, Eingangsergebnis


def _beleg(**kw):
    daten = {
        "datei_hash": "a" * 64,
        "dateiname": "r.pdf",
        "kanal": "upload",
        "herkunft": "x",
        "aufbewahren_bis": date(2036, 12, 31),
    }
    daten.update(kw)
    return Beleg(**daten)


VORHANDEN = _beleg(
    datei_hash="a" * 64,
    lieferant_name="Bürobedarf Müller GmbH",
    lieferant_ust_id="DE123456789",
    belegnummer="RE-2026-0042",
    belegdatum=date(2026, 3, 5),
    brutto=Decimal("173.50"),
)


def test_stufe1_gleicher_hash():
    befund = pruefe_dublette(_beleg(datei_hash="a" * 64), [VORHANDEN])
    assert befund.ergebnis is Eingangsergebnis.DUBLETTE
    assert befund.beleg_id == VORHANDEN.id
    assert "Datei" in befund.grund


def test_stufe2_lieferant_und_belegnummer():
    kandidat = _beleg(
        datei_hash="b" * 64,
        lieferant_name="BÜROBEDARF MÜLLER GMBH ",
        belegnummer="re-2026-0042",
    )
    befund = pruefe_dublette(kandidat, [VORHANDEN])
    assert befund.ergebnis is Eingangsergebnis.DUBLETTE
    assert befund.beleg_id == VORHANDEN.id


def test_stufe2_ust_id_schlaegt_namen():
    kandidat = _beleg(
        datei_hash="b" * 64,
        lieferant_name="Müller Büro",
        lieferant_ust_id="DE 123 456 789",
        belegnummer="RE-2026-0042",
    )
    assert pruefe_dublette(kandidat, [VORHANDEN]).ergebnis is Eingangsergebnis.DUBLETTE


def test_stufe3_betrag_und_datum_im_fenster_ist_verdacht():
    kandidat = _beleg(
        datei_hash="b" * 64,
        lieferant_ust_id="DE123456789",
        belegnummer="RE-2026-0099",
        belegdatum=date(2026, 3, 5) + timedelta(days=3),
        brutto=Decimal("173.50"),
    )
    befund = pruefe_dublette(kandidat, [VORHANDEN])
    assert befund.ergebnis is Eingangsergebnis.VERDACHT
    assert befund.beleg_id == VORHANDEN.id


def test_stufe3_ausserhalb_des_fensters_ist_neu():
    kandidat = _beleg(
        datei_hash="b" * 64,
        lieferant_ust_id="DE123456789",
        belegdatum=date(2026, 3, 5) + timedelta(days=4),
        brutto=Decimal("173.50"),
    )
    assert pruefe_dublette(kandidat, [VORHANDEN]).ergebnis is Eingangsergebnis.NEU


def test_fehlende_felder_loesen_keine_stufe_aus():
    kandidat = _beleg(datei_hash="b" * 64)
    befund = pruefe_dublette(kandidat, [_beleg(datei_hash="c" * 64)])
    assert befund.ergebnis is Eingangsergebnis.NEU
    assert befund.beleg_id is None


def test_anderer_lieferant_ist_neu():
    kandidat = _beleg(
        datei_hash="b" * 64,
        lieferant_name="Andere Firma AG",
        belegnummer="RE-2026-0042",
        belegdatum=date(2026, 3, 5),
        brutto=Decimal("173.50"),
    )
    assert pruefe_dublette(kandidat, [VORHANDEN]).ergebnis is Eingangsergebnis.NEU
