"""Stufenermittlung: Karenz, Mindestbetrag, Stufenabstand, keine Stufe auslassen."""

from datetime import date
from decimal import Decimal

from accounti.mahnwesen.konfiguration import MahnEinstellungen
from accounti.mahnwesen.stufen import ermittle
from accounti.models import PostenRichtung
from accounti.models.mahnwesen import MahnKontakt
from tests.zahlung_hilfe import debitor, kreditor, posten

E = MahnEinstellungen()
KUNDE = debitor()
FAELLIG = date(2026, 9, 1)


def _forderung(**kw):
    werte = {
        "faellig": FAELLIG,
        "belegdatum": date(2026, 8, 18),
        "richtung": PostenRichtung.FORDERUNG,
    }
    werte.update(kw)
    return posten(KUNDE, "2026-0042", "1190.00", **werte)


def _stufe(p, stichtag, **kw):
    faellig, ausnahmen = ermittle([p], {KUNDE.id: KUNDE}, stichtag, E, **kw)
    return [(f.stufe_nr, f.stufe.name, f.tage) for f in faellig], [
        a.grund for a in ausnahmen
    ]


def test_ein_posten_durchlaeuft_die_stufen_der_reihe_nach():
    p = _forderung()
    assert _stufe(p, date(2026, 9, 4)) == ([], [])  # 3 Tage: Karenz
    assert _stufe(p, date(2026, 9, 6)) == ([(1, "Zahlungserinnerung", 5)], [])
    p1 = p.model_copy(update={"mahnstufe": 1})
    letzte = {p.id: date(2026, 9, 6)}
    assert _stufe(p1, date(2026, 9, 14), letzte_mahnung=letzte) == ([], [])  # 13 Tage
    assert _stufe(p1, date(2026, 9, 15), letzte_mahnung=letzte) == (
        [(2, "1. Mahnung", 14)],
        [],
    )
    p2 = p.model_copy(update={"mahnstufe": 2})
    assert _stufe(p2, date(2026, 9, 29), letzte_mahnung={p.id: date(2026, 9, 15)}) == (
        [(3, "2. Mahnung", 28)],
        [],
    )
    p3 = p.model_copy(update={"mahnstufe": 3})
    assert _stufe(p3, date(2026, 12, 1), letzte_mahnung={p.id: date(2026, 9, 29)}) == (
        [],
        [
            "letzte Stufe (2. Mahnung) erreicht — weiter nur außerhalb von accounti "
            "(gerichtliches Mahnverfahren, Inkasso)"
        ],
    )


def test_keine_stufe_wird_uebersprungen():
    # 60 Tage überfällig, nie gemahnt: zuerst die Zahlungserinnerung
    assert _stufe(_forderung(), date(2026, 10, 31))[0] == [
        (1, "Zahlungserinnerung", 60)
    ]


def test_stufenabstand_seit_der_letzten_mahnung():
    p = _forderung(mahnstufe=1)
    letzte = {p.id: date(2026, 9, 12)}
    assert _stufe(p, date(2026, 9, 15), letzte_mahnung=letzte) == ([], [])
    assert _stufe(p, date(2026, 9, 19), letzte_mahnung=letzte)[0] == [
        (2, "1. Mahnung", 18)
    ]


def test_naechste_stufe_erst_nach_ablauf_der_frist():
    """Stufenabstand erreicht, aber die Frist der letzten Mahnung läuft noch."""
    p = _forderung(mahnstufe=1)
    letzte = {p.id: date(2026, 9, 6)}
    frist = {p.id: date(2026, 9, 16)}
    kw = {"letzte_mahnung": letzte, "frist_bis": frist}
    assert _stufe(p, date(2026, 9, 15), **kw) == ([], [])
    assert _stufe(p, date(2026, 9, 16), **kw) == ([], [])
    assert _stufe(p, date(2026, 9, 17), **kw)[0] == [(2, "1. Mahnung", 16)]


def test_karenz_gilt_auch_fuer_fruehe_stufen():
    e = MahnEinstellungen(karenztage=10)
    faellig, _ = ermittle([_forderung()], {KUNDE.id: KUNDE}, date(2026, 9, 8), e)
    assert faellig == []
    faellig, _ = ermittle([_forderung()], {KUNDE.id: KUNDE}, date(2026, 9, 12), e)
    assert [f.stufe_nr for f in faellig] == [1]


def test_ausnahmen_mit_grund():
    stichtag = date(2026, 10, 1)
    klein = _forderung(rest="5.00")
    assert _stufe(klein, stichtag)[1] == [
        "Rest 5,00 € unter dem Mindestbetrag von 10,00 €"
    ]
    p = _forderung()
    sperre = {
        KUNDE.id: MahnKontakt(
            kontakt_id=KUNDE.id, mahnsperre=True, sperrgrund="Ratenzahlung vereinbart"
        )
    }
    assert _stufe(p, stichtag, mahnkontakte=sperre)[1] == [
        "Mahnsperre: Ratenzahlung vereinbart"
    ]
    assert _stufe(p, stichtag, offene_entwuerfe={p.id: 3})[1] == [
        "Mahnung 3 ist noch ein Entwurf — erst versenden oder verwerfen"
    ]
    assert _stufe(p, stichtag, zahlung_vorgeschlagen={p.id})[1] == [
        "Zahlung vorgeschlagen — erst 'accounti opos bestaetigen' oder "
        "'accounti opos ablehnen'"
    ]


def test_nur_offene_forderungen():
    lieferant = kreditor()
    verbindlichkeit = posten(lieferant, faellig=FAELLIG)
    bezahlt = _forderung(rest="0.00")
    gutschrift = posten(
        KUNDE, "GS-1", "-50.00", faellig=FAELLIG, richtung=PostenRichtung.FORDERUNG
    )
    faellig, ausnahmen = ermittle(
        [verbindlichkeit, bezahlt, gutschrift],
        {KUNDE.id: KUNDE, lieferant.id: lieferant},
        date(2026, 10, 1),
        E,
    )
    assert faellig == [] and ausnahmen == []
    assert Decimal(bezahlt.restbetrag) == 0
