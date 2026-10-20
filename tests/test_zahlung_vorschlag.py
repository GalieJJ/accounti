"""Zahlungsvorschlag: Skontofristen vor Nettofälligkeiten, Grund je Position."""

from datetime import date
from decimal import Decimal

import pytest

from accounti.models import PostenRichtung
from accounti.models.zahlung import LaufStatus, Zahlungssperre
from accounti.zahlung.konfiguration import ZahlungEinstellungen
from accounti.zahlung.vorschlag import erstelle_vorschlag, lade_vorschlag
from tests.zahlung_hilfe import (
    STICHTAG,
    debitor,
    kreditor,
    neue_db,
    posten,
    speichere,
)

E = ZahlungEinstellungen()


@pytest.fixture
def mueller():
    return kreditor()


def _vorschlag(alle, kontakte, **kw):
    return erstelle_vorschlag(
        alle, {k.id: k for k in kontakte}, STICHTAG, kw.pop("einstellungen", E), **kw
    )


def test_skontoposten_zuerst_mit_grund(mueller):
    """Akzeptanz 1: Skontofrist morgen schlägt Nettofälligkeit heute."""
    heute_faellig = posten(
        mueller,
        "RE-100",
        "500.00",
        faellig=date(2026, 10, 20),
        belegdatum=date(2026, 9, 20),
    )
    skonto_morgen = posten(
        mueller,
        "RE-200",
        "1190.00",
        faellig=date(2026, 11, 15),
        skonto_bis=date(2026, 10, 21),
        skonto_prozent="2",
    )
    skonto_spaeter = posten(
        mueller,
        "RE-300",
        "300.00",
        faellig=date(2026, 11, 30),
        skonto_bis=date(2026, 11, 5),
        skonto_prozent="3",
    )
    v = _vorschlag([heute_faellig, skonto_morgen, skonto_spaeter], [mueller])

    assert [p.posten.belegnummer for p in v.positionen] == ["RE-200", "RE-100"]
    skonto, netto = v.positionen
    assert skonto.art == "skonto"
    assert skonto.betrag == Decimal("1166.20") and skonto.skonto == Decimal("23.80")
    assert "Skontofrist endet morgen (21.10.2026)" in skonto.grund
    assert "2 % = 23,80 € sparen" in skonto.grund
    assert "netto fällig erst am 15.11.2026" in skonto.grund
    assert netto.art == "faellig"
    assert netto.betrag == Decimal("500.00") and netto.skonto == 0
    assert netto.grund == "heute fällig (20.10.2026)"
    assert v.summe == Decimal("1666.20") and v.skonto_summe == Decimal("23.80")
    # Skonto in 16 Tagen: noch nicht zahlen, aber auch kein Ausschluss
    assert v.ausgeschlossen == []


def test_skontofrist_heute_und_in_drei_tagen(mueller):
    heute = posten(mueller, "RE-1", skonto_bis=date(2026, 10, 20), skonto_prozent="2")
    drei = posten(mueller, "RE-2", skonto_bis=date(2026, 10, 23), skonto_prozent="3")
    vier = posten(mueller, "RE-3", skonto_bis=date(2026, 10, 24), skonto_prozent="3")
    v = _vorschlag([drei, vier, heute], [mueller])
    assert [p.posten.belegnummer for p in v.positionen] == ["RE-1", "RE-2"]
    assert v.positionen[0].grund.startswith("Skontofrist endet heute (20.10.2026)")
    assert v.positionen[1].grund.startswith("Skontofrist endet in 3 Tagen (23.10.2026)")


def test_skonto_verfallen_zahlt_netto_bei_faelligkeit(mueller):
    p = posten(
        mueller,
        faellig=date(2026, 10, 22),
        skonto_bis=date(2026, 10, 19),
        skonto_prozent="2",
    )
    (pos,) = _vorschlag([p], [mueller]).positionen
    assert pos.betrag == Decimal("1190.00") and pos.skonto == 0
    assert (
        pos.grund == "fällig am 22.10.2026 (in 2 Tagen); Skonto verfallen am 19.10.2026"
    )


def test_ueberfaellige_posten_vor_faelligen(mueller):
    alt = posten(mueller, "RE-ALT", faellig=date(2026, 10, 5))
    neu = posten(mueller, "RE-NEU", faellig=date(2026, 10, 21))
    v = _vorschlag([neu, alt], [mueller])
    assert [p.posten.belegnummer for p in v.positionen] == ["RE-ALT", "RE-NEU"]
    assert v.positionen[0].art == "ueberfaellig"
    assert v.positionen[0].grund == "seit 15 Tagen überfällig (fällig am 05.10.2026)"
    assert v.positionen[1].grund == "fällig am 21.10.2026 (morgen)"


def test_teilzahlung_ohne_skonto(mueller):
    p = posten(
        mueller,
        betrag="1190.00",
        rest="190.00",
        faellig=date(2026, 10, 21),
        skonto_bis=date(2026, 10, 25),
        skonto_prozent="2",
    )
    (pos,) = _vorschlag([p], [mueller]).positionen
    assert pos.betrag == Decimal("190.00") and pos.skonto == 0
    assert "Restbetrag nach Teilzahlung" in pos.grund


def test_gesperrter_kontakt_wird_mit_grund_ausgeschlossen(mueller):
    p = posten(mueller, faellig=date(2026, 10, 1))
    sperre = Zahlungssperre(
        kontakt_id=mueller.id, grund="Reklamation offen", gesetzt_von="erika"
    )
    v = _vorschlag([p], [mueller], sperren={mueller.id: sperre})
    assert v.positionen == []
    (aus,) = v.ausgeschlossen
    assert aus.grund == "Zahlungssperre: Reklamation offen (erika)"


def test_posten_im_lauf_und_gutschrift_ausgeschlossen(mueller):
    im_lauf = posten(mueller, "RE-1", faellig=date(2026, 10, 1))
    gutschrift = posten(mueller, "GS-1", "-50.00", faellig=date(2026, 10, 1))
    v = _vorschlag(
        [im_lauf, gutschrift],
        [mueller],
        in_laeufen={im_lauf.id: (3, LaufStatus.FREIGEGEBEN)},
    )
    assert v.positionen == []
    assert [a.grund for a in v.ausgeschlossen] == [
        "bereits in Zahlungslauf 3 (freigegeben)",
        "Gutschrift über -50,00 € — wird verrechnet, nicht überwiesen",
    ]


def test_betrags_und_kontaktfilter(mueller):
    schulz = kreditor("Schulz KG", "70002", iban="DE02120300000000202051")
    klein = posten(mueller, "K", "5.00", faellig=date(2026, 10, 1))
    gross = posten(mueller, "G", "90000.00", faellig=date(2026, 10, 1))
    mittel = posten(schulz, "M", "200.00", faellig=date(2026, 10, 1))
    e = ZahlungEinstellungen(
        mindestbetrag=Decimal("10"), hoechstbetrag=Decimal("50000")
    )
    v = _vorschlag([klein, gross, mittel], [mueller, schulz], einstellungen=e)
    assert [p.posten.belegnummer for p in v.positionen] == ["M"]
    assert [a.grund for a in v.ausgeschlossen] == [
        "unter dem Mindestbetrag von 10,00 €",
        "über dem Höchstbetrag von 50.000,00 €",
    ]
    nur_mueller = _vorschlag(
        [klein, mittel], [mueller, schulz], kontakt_ids={mueller.id}
    )
    assert [p.posten.belegnummer for p in nur_mueller.positionen] == ["K"]


def test_ohne_skonto_wird_erst_bei_faelligkeit_gezahlt(mueller):
    p = posten(
        mueller,
        faellig=date(2026, 11, 15),
        skonto_bis=date(2026, 10, 21),
        skonto_prozent="2",
    )
    e = ZahlungEinstellungen(skonto_ziehen=False)
    assert _vorschlag([p], [mueller], einstellungen=e).positionen == []
    spaeter = erstelle_vorschlag([p], {mueller.id: mueller}, date(2026, 11, 14), e)
    assert spaeter.positionen[0].betrag == Decimal("1190.00")


def test_planungshorizont_einstellbar(mueller):
    p = posten(mueller, faellig=date(2026, 10, 27))
    assert _vorschlag([p], [mueller]).positionen == []
    weit = ZahlungEinstellungen(vorlauf_tage=7)
    assert len(_vorschlag([p], [mueller], einstellungen=weit).positionen) == 1


def test_forderungen_und_ausgeglichene_werden_ignoriert(mueller):
    kunde = debitor()
    forderung = posten(
        kunde, faellig=date(2026, 10, 1), richtung=PostenRichtung.FORDERUNG
    )
    bezahlt = posten(mueller, rest="0.00", faellig=date(2026, 10, 1))
    v = _vorschlag([forderung, bezahlt], [mueller, kunde])
    assert v.positionen == [] and v.ausgeschlossen == []


def test_vorschlag_aus_der_datenbank():
    fabrik = neue_db()
    m = kreditor()
    p = posten(m, faellig=date(2026, 10, 19))
    speichere(fabrik, [m], [p])
    with fabrik() as s:
        v = lade_vorschlag(s, STICHTAG, E)
    assert [x.posten.id for x in v.positionen] == [p.id]
    assert v.positionen[0].kontakt.name == "Bürobedarf Müller GmbH"
