from datetime import date
from decimal import Decimal
from uuid import uuid4

from accounti.models import (
    Kontakt,
    OffenerPosten,
    PostenRichtung,
    PostenStatus,
    Transaktion,
    TransaktionQuelle,
)
from accounti.opos.zuordnung import Stufe, ordne_zu

MUELLER = Kontakt(
    name="Bürobedarf Müller GmbH", kreditor_konto="70000", iban="DE89370400440532013000"
)
DRUCK = Kontakt(name="Druckerei Beispiel GmbH", kreditor_konto="70001")
KUNDIN = Kontakt(name="Atelier Kundin GmbH", debitor_konto="10000")
KONTAKTE = [MUELLER, DRUCK, KUNDIN]


def op(
    nummer,
    betrag,
    kontakt=MUELLER,
    rest=None,
    faellig=date(2026, 3, 19),
    skonto=None,
    skonto_bis=None,
    richtung=PostenRichtung.VERBINDLICHKEIT,
):
    return OffenerPosten(
        kontakt_id=kontakt.id,
        beleg_id=uuid4(),
        richtung=richtung,
        belegnummer=nummer,
        belegdatum=date(2026, 3, 5),
        betrag=Decimal(betrag),
        restbetrag=Decimal(rest if rest is not None else betrag),
        faellig_am=faellig,
        skonto_betrag=Decimal(skonto) if skonto else None,
        skonto_bis=skonto_bis,
        skonto_prozent=Decimal("2") if skonto else None,
        status=PostenStatus.TEILBEZAHLT if rest is not None else PostenStatus.OFFEN,
    )


def tx(betrag, zweck="", name=None, iban=None, datum=date(2026, 3, 10)):
    return Transaktion(
        datum=datum,
        betrag=Decimal(betrag),
        verwendungszweck=zweck,
        gegenkonto_name=name,
        gegenkonto_iban=iban,
        quelle=TransaktionQuelle.BANK,
        rohtext="x",
    )


RE42 = op("RE-2026-0042", "172.50", skonto="3.45", skonto_bis=date(2026, 3, 12))
RE51 = op("RE-2026-0051", "59.50")
DR9 = op("MIN-2026-9", "1190.00", kontakt=DRUCK)
POSTEN = [RE42, RE51, DR9]


def _anteile(v):
    return [(a.posten.belegnummer, a.betrag, a.skonto) for a in v.anteile]


def test_referenz_voll():
    v = ordne_zu(tx("-172.50", "Rechnung RE-2026-0042 Kd 100234"), POSTEN, KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.REFERENZ, True)
    assert _anteile(v) == [("RE-2026-0042", Decimal("172.50"), Decimal("0"))]


def test_referenz_mit_anderer_schreibweise():
    v = ordne_zu(tx("-172.50", "RE 2026 0042"), POSTEN, KONTAKTE)
    assert v.stufe is Stufe.REFERENZ


def test_referenz_mit_skonto_in_der_frist():
    """Akzeptanz 3 — die Zuordnung erkennt den Skontoabzug."""
    v = ordne_zu(
        tx("-169.05", "RE-2026-0042 abzgl. 2% Skonto", datum=date(2026, 3, 14)),
        POSTEN,
        KONTAKTE,
    )
    assert (v.stufe, v.automatisch) == (Stufe.SKONTO, True)
    assert _anteile(v) == [("RE-2026-0042", Decimal("169.05"), Decimal("3.45"))]


def test_skonto_mit_rundungsdifferenz():
    v = ordne_zu(tx("-169.06", "RE-2026-0042"), POSTEN, KONTAKTE)
    assert v.stufe is Stufe.SKONTO
    assert _anteile(v) == [("RE-2026-0042", Decimal("169.06"), Decimal("3.44"))]


def test_skonto_nach_der_frist_ist_teilzahlung():
    v = ordne_zu(
        tx("-169.05", "RE-2026-0042", datum=date(2026, 3, 20)), POSTEN, KONTAKTE
    )
    assert (v.stufe, v.automatisch) == (Stufe.TEIL, True)
    assert _anteile(v) == [("RE-2026-0042", Decimal("169.05"), Decimal("0"))]


def test_referenz_teilzahlung_und_rest():
    """Akzeptanz 4 — Teilzahlung, später der Rest."""
    v = ordne_zu(tx("-100.00", "RE-2026-0042 Teilzahlung"), POSTEN, KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.TEIL, True)
    rest = op("RE-2026-0042", "172.50", rest="72.50")
    v = ordne_zu(tx("-72.50", "RE-2026-0042 Rest"), [rest], KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.REFERENZ, True)
    assert _anteile(v) == [("RE-2026-0042", Decimal("72.50"), Decimal("0"))]


def test_ueberzahlung_ist_vorschlag():
    v = ordne_zu(tx("-200.00", "RE-2026-0042"), POSTEN, KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.UEBERZAHLUNG, False)
    assert _anteile(v) == [("RE-2026-0042", Decimal("200.00"), Decimal("0"))]


def test_exakt_ueber_iban_ohne_referenz():
    v = ordne_zu(
        tx("-59.50", "Ihre Rechnung", iban="DE89 3704 0044 0532 0130 00"),
        POSTEN,
        KONTAKTE,
    )
    assert (v.stufe, v.automatisch) == (Stufe.EXAKT, True)
    assert v.kontakt.id == MUELLER.id
    assert _anteile(v) == [("RE-2026-0051", Decimal("59.50"), Decimal("0"))]


def test_exakt_ueber_namen():
    v = ordne_zu(tx("-1190.00", "Druck", name="DRUCKEREI BEISPIEL"), POSTEN, KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.EXAKT, True)


def test_skonto_ohne_referenz_ist_vorschlag():
    v = ordne_zu(tx("-169.05", "Zahlung", name="Bürobedarf Müller"), POSTEN, KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.SKONTO, False)
    assert _anteile(v) == [("RE-2026-0042", Decimal("169.05"), Decimal("3.45"))]


def test_sammelzahlung_mit_referenzen_ist_vorschlag():
    """Akzeptanz 5 — drei Rechnungen, eine Zahlung."""
    drei = [op("RE-1001", "100.00"), op("RE-1002", "200.00"), op("RE-1003", "300.00")]
    v = ordne_zu(tx("-600.00", "RE-1001 RE-1002 RE-1003"), drei, KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.SAMMEL, False)
    assert sorted(_anteile(v)) == [
        ("RE-1001", Decimal("100.00"), Decimal("0")),
        ("RE-1002", Decimal("200.00"), Decimal("0")),
        ("RE-1003", Decimal("300.00"), Decimal("0")),
    ]


def test_sammelzahlung_ohne_referenzen_ueber_summe():
    posten = [
        op("RE-1001", "100.00"),
        op("RE-1002", "200.00"),
        op("RE-1003", "300.00"),
        op("RE-1004", "45.00"),
    ]
    v = ordne_zu(
        tx("-345.00", "Sammelüberweisung", name="Bürobedarf Müller GmbH"),
        posten,
        KONTAKTE,
    )
    assert (v.stufe, v.automatisch) == (Stufe.SAMMEL, False)
    assert sorted(a[0] for a in _anteile(v)) == ["RE-1003", "RE-1004"]


def test_sammelzahlung_mit_skonto_je_posten():
    posten = [
        op("RE-1001", "100.00", skonto="2.00", skonto_bis=date(2026, 3, 15)),
        op("RE-1002", "200.00", skonto="4.00", skonto_bis=date(2026, 3, 15)),
    ]
    v = ordne_zu(tx("-294.00", "RE-1001, RE-1002"), posten, KONTAKTE)
    assert v.stufe is Stufe.SAMMEL
    assert sorted(_anteile(v)) == [
        ("RE-1001", Decimal("98.00"), Decimal("2.00")),
        ("RE-1002", Decimal("196.00"), Decimal("4.00")),
    ]


def test_teilbetrag_ohne_referenz_ist_vorschlag():
    v = ordne_zu(
        tx("-50.00", "Abschlag", name="Druckerei Beispiel GmbH"), POSTEN, KONTAKTE
    )
    assert (v.stufe, v.automatisch) == (Stufe.TEIL, False)
    assert v.confidence < 0.7


def test_unbekannter_kontakt_mit_eindeutigem_betrag():
    v = ordne_zu(tx("-1190.00", "Überweisung", name="Jemand Anders"), POSTEN, KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.UNSCHARF, False)


def test_kein_treffer():
    assert (
        ordne_zu(tx("-12.34", "Bankgebühren", name="Sparkasse"), POSTEN, KONTAKTE)
        is None
    )


def test_richtung_einnahme_trifft_nur_forderungen():
    forderung = op(
        "2026-0001", "1216.75", kontakt=KUNDIN, richtung=PostenRichtung.FORDERUNG
    )
    assert ordne_zu(tx("-1216.75", "2026-0001"), [forderung], KONTAKTE) is None
    v = ordne_zu(tx("1216.75", "Rechnung 2026-0001"), [forderung], KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.REFERENZ, True)


def test_zu_kurze_belegnummer_ist_keine_referenz():
    kurz = op("4711", "75.83")
    v = ordne_zu(tx("-75.83", "Tankstelle Karte 4711 0042"), [kurz], KONTAKTE)
    assert v is None or v.stufe is not Stufe.REFERENZ
