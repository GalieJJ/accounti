"""Gutschriften, Guthaben, Verrechnung und Handzuordnung (Gesamttest Ausgang B3–B6).

Ein offener Posten mit negativem Rest ist ein Guthaben des Kunden (Gutschrift,
Rechnungskorrektur, Überzahlung) bzw. bei Kreditoren ein Guthaben beim Lieferanten.
Er gleicht sich durch Verrechnung mit gegenläufigen Posten desselben Kontakts aus oder
durch eine Erstattung über die Bank (Zahlung in Gegenrichtung).
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_buchungen,
    lade_einen_posten,
    lade_zuordnungen,
    speichere_transaktion,
)
from accounti.konfiguration import Buchhaltung
from accounti.mahnwesen.konfiguration import MahnEinstellungen
from accounti.mahnwesen.lauf import mahnlauf
from accounti.models import (
    Kontakt,
    OffenerPosten,
    PostenRichtung,
    PostenStatus,
    Transaktion,
    TransaktionQuelle,
    ZuordnungStatus,
)
from accounti.opos.ausgleich import gleiche_aus
from accounti.opos.verrechnung import VerrechnungError, lade_verrechnungen, verrechne
from accounti.opos.zahlungslauf import (
    ZahlungslaufError,
    ordne_von_hand,
    zuordne_zahlungen,
)
from accounti.opos.zuordnung import Anteil, Stufe, ordne_zu, verteile
from accounti.pruefung.journal import pruefe_journal
from tests.pg_hilfe import mit_postgresql
from tests.pruefung_hilfe import make_session_fixture  # noqa: F401 - Fixture
from tests.zahlung_hilfe import beleg_zu, debitor, kreditor, neue_db, speichere

D = Decimal
F = PostenRichtung.FORDERUNG
V = PostenRichtung.VERBINDLICHKEIT
EINSTELLUNGEN = Buchhaltung()

KUNDE = Kontakt(name="Kunde AG", debitor_konto="10000")
X = Kontakt(name="Kunde X GmbH", debitor_konto="10001")
Y = Kontakt(name="Kunde Y AG", debitor_konto="10002")
LIEFERANT = Kontakt(name="Druckerei Beispiel GmbH", kreditor_konto="70001")
KONTAKTE = [KUNDE, X, Y, LIEFERANT]


def op(nummer, betrag, kontakt=KUNDE, rest=None, richtung=F, faellig=date(2026, 4, 1)):
    betrag = D(betrag)
    return OffenerPosten(
        kontakt_id=kontakt.id,
        beleg_id=uuid4(),
        richtung=richtung,
        belegnummer=nummer,
        belegdatum=date(2026, 3, 2),
        betrag=betrag,
        restbetrag=D(rest) if rest is not None else betrag,
        faellig_am=faellig,
        status=PostenStatus.TEILBEZAHLT if rest is not None else PostenStatus.OFFEN,
    )


def tx(betrag, zweck="", name=None, datum=date(2026, 3, 20)):
    return Transaktion(
        datum=datum,
        betrag=D(betrag),
        verwendungszweck=zweck,
        gegenkonto_name=name,
        quelle=TransaktionQuelle.BANK,
        rohtext=zweck,
    )


def _anteile(v):
    return [(a.posten.belegnummer, a.betrag, a.skonto) for a in v.anteile]


# --- Zuordnung: Saldierung, Erstattung, Guthaben (B3, B4, B6) ----------------------

RECHNUNG = op("2026-0001", "595.00")
GUTSCHRIFT = op("2026-0002", "-119.00")


def test_saldozahlung_mit_beiden_nummern_wird_saldiert():
    v = ordne_zu(
        tx("476.00", "RE 2026-0001 ABZGL KORREKTUR 2026-0002", "Kunde AG"),
        [RECHNUNG, GUTSCHRIFT],
        KONTAKTE,
    )
    assert v is not None and v.stufe is Stufe.SAMMEL
    assert sorted(_anteile(v)) == [
        ("2026-0001", D("595.00"), D("0")),
        ("2026-0002", D("-119.00"), D("0")),
    ]
    assert "Gutschrift" in v.begruendung or "Guthaben" in v.begruendung


def test_erstattung_trifft_den_negativen_posten():
    v = ordne_zu(
        tx("-119.00", "ERSTATTUNG GUTSCHRIFT 2026-0002", "Kunde AG"),
        [GUTSCHRIFT, op("2026-0003", "200.00")],
        KONTAKTE,
    )
    assert (v.stufe, v.automatisch) == (Stufe.REFERENZ, True)
    assert _anteile(v) == [("2026-0002", D("-119.00"), D("0"))]


def test_erstattung_ohne_nummer_beim_erkannten_kunden():
    v = ordne_zu(tx("-119.00", "Rueckzahlung", "Kunde AG"), [GUTSCHRIFT], KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.EXAKT, True)
    assert _anteile(v) == [("2026-0002", D("-119.00"), D("0"))]


def test_erstattung_eines_lieferanten_trifft_seine_gutschrift():
    gutschrift = op("GS-2026-77", "-50.00", kontakt=LIEFERANT, richtung=V)
    v = ordne_zu(tx("50.00", "Gutschrift GS-2026-77"), [gutschrift], KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.REFERENZ, True)
    assert _anteile(v) == [("GS-2026-77", D("-50.00"), D("0"))]


def test_zahlung_abzueglich_guthaben_wird_vorgeschlagen():
    guthaben = op("2026-0001", "1190.00", rest="-50.00")  # Überzahlung
    neu = op("2026-0002", "1190.00", faellig=date(2026, 6, 1))
    v = ordne_zu(
        tx("1140.00", "INV 2026-0002 LESS CREDIT 50", "Kunde AG"),
        [guthaben, neu],
        KONTAKTE,
    )
    assert (v.stufe, v.automatisch) == (Stufe.SAMMEL, False)
    assert sorted(_anteile(v)) == [
        ("2026-0001", D("-50.00"), D("0")),
        ("2026-0002", D("1190.00"), D("0")),
    ]


def test_zahlung_abzueglich_guthaben_ohne_nummer():
    guthaben = op("2026-0001", "1190.00", rest="-50.00")
    neu = op("2026-0002", "1190.00", faellig=date(2026, 6, 1))
    v = ordne_zu(tx("1140.00", "Zahlung", "Kunde AG"), [guthaben, neu], KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.SAMMEL, False)
    assert sorted(a[0] for a in _anteile(v)) == ["2026-0001", "2026-0002"]


def test_ueberzahlung_ohne_referenz_beim_erkannten_kunden_wird_vorgeschlagen():
    v = ordne_zu(
        tx("1200.00", "IHRE LIEFERUNG SEPTEMBER", "Kunde AG"),
        [op("2026-0001", "1190.00")],
        KONTAKTE,
    )
    assert (v.stufe, v.automatisch) == (Stufe.UEBERZAHLUNG, False)
    assert _anteile(v) == [("2026-0001", D("1200.00"), D("0"))]
    assert "10.00" in v.begruendung or "10,00" in v.begruendung


def test_gutschrift_allein_ist_kein_kandidat_fuer_einen_zahlungseingang():
    assert ordne_zu(tx("119.00", "2026-0002"), [GUTSCHRIFT], KONTAKTE) is None


BEIDE = Kontakt(
    name="Rahmen und Kunst KG", debitor_konto="10005", kreditor_konto="70005"
)


def test_verbindlichkeit_desselben_kontakts_ist_kein_guthaben_fuer_einen_eingang():
    # Nachprüfung N1: Forderung 1.000 und Verbindlichkeit 300 desselben Kontakts — ein
    # Eingang über 700 ist keine „Zahlung mit Guthaben“ (zwei Personenkonten)
    forderung = op("2026-0001", "1000.00", kontakt=BEIDE)
    verbindlichkeit = op("ER-4711", "300.00", kontakt=BEIDE, richtung=V)
    for zweck in ("Zahlung", "RE 2026-0001 abzgl. ER-4711"):
        v = ordne_zu(
            tx("700.00", zweck, BEIDE.name),
            [forderung, verbindlichkeit],
            [*KONTAKTE, BEIDE],
        )
        assert v is not None, zweck
        assert [a.posten.belegnummer for a in v.anteile] == ["2026-0001"], zweck
        assert "Guthaben" not in v.begruendung, zweck
    # ein echtes Guthaben (Forderung mit negativem Rest) zählt weiter
    guthaben = op("2026-0002", "1000.00", kontakt=BEIDE, rest="-300.00")
    v = ordne_zu(
        tx("700.00", "Zahlung", BEIDE.name),
        [forderung, guthaben, verbindlichkeit],
        [*KONTAKTE, BEIDE],
    )
    assert sorted(a.posten.belegnummer for a in v.anteile) == ["2026-0001", "2026-0002"]


# --- Referenz: Wortgrenzen und Zahler (B5) -----------------------------------------


def test_referenz_nur_an_wortgrenzen():
    posten = [op("2026-0315", "476.00", kontakt=Y)]
    for zweck in ("Kd 120260315 Lieferung", "RE 2026-03150", "IBAN DE20260315001"):
        v = ordne_zu(tx("476.00", zweck), posten, KONTAKTE)
        assert v is None or v.stufe is not Stufe.REFERENZ, zweck
    for zweck in ("RE 2026-0315", "Rechnung2026-0315 danke", "RG.NR.2026/0315"):
        v = ordne_zu(tx("476.00", zweck), posten, KONTAKTE)
        assert v is not None and v.stufe is Stufe.REFERENZ, zweck


def test_referenz_auf_den_posten_eines_anderen_kunden_bucht_nicht_automatisch():
    x = op("2026-0001", "476.00", kontakt=X)
    y = op("2026-0315", "1190.00", kontakt=Y)
    v = ordne_zu(
        tx("476.00", "EREF+20260315-0042 IHRE LIEFERUNG", "Kunde X GmbH"),
        [x, y],
        KONTAKTE,
    )
    assert v is not None and not v.automatisch
    assert _anteile(v) == [("2026-0001", D("476.00"), D("0"))]


def test_fremde_referenz_ohne_eigenen_posten_bleibt_ein_schwacher_vorschlag():
    y = op("2026-0315", "1190.00", kontakt=Y)
    v = ordne_zu(tx("400.00", "RE 2026-0315", "Kunde X GmbH"), [y], KONTAKTE)
    assert v is not None and not v.automatisch and v.confidence <= 0.6
    assert "Kunde Y" in v.begruendung or "anderen" in v.begruendung


def test_datum_im_zweck_ist_ohne_erkannten_zahler_keine_sichere_referenz():
    # Probe des Testers ohne erkannten Zahler: „20260315“ ist hier ein Datum (EREF),
    # die Rechnung 2026-0315 von Kunde Y wird nur vorgeschlagen, nicht gebucht
    x = op("2026-0001", "476.00", kontakt=X)
    y = op("2026-0315", "1190.00", kontakt=Y)
    for zweck in ("EREF+20260315-0042 IHRE LIEFERUNG", "SVWZ+ LIEFERUNG 20260315"):
        v = ordne_zu(tx("476.00", zweck, "Unbekannt"), [x, y], KONTAKTE)
        assert v is not None and not v.automatisch, zweck
        assert v.confidence <= 0.6 and "Datum" in v.begruendung, zweck
    # mit Trennzeichen oder Buchstaben davor bleibt es eine Referenz wie bisher
    for zweck in ("RE 2026-0315", "RE2026-0315", "2026/0315"):
        v = ordne_zu(tx("400.00", zweck, "Unbekannt"), [x, y], KONTAKTE)
        assert (v.stufe, v.automatisch) == (Stufe.TEIL, True), zweck
    # keine Datumsform (Monat 13): Referenz wie bisher
    z = op("2026-1315", "1190.00", kontakt=Y)
    v = ordne_zu(tx("400.00", "EREF+20261315", "Unbekannt"), [z], KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.TEIL, True)


def test_iso_datum_mit_trennzeichen_ist_ohne_erkannten_zahler_keine_referenz():
    # Nachprüfung M1: „2026-03-15“ ergibt zusammengesetzt „20260315“ = 2026-0315 — die
    # Wortfolge ist anders gegliedert als die Nummer (4-2-2 statt 4-4), also ein Datum
    x = op("2026-0001", "476.00", kontakt=X)
    y = op("2026-0315", "1190.00", kontakt=Y)
    for zweck in (
        "Lieferung vom 2026-03-15",
        "Zahlung 2026/03/15 Bild",
        "EREF+2026-03-15-0042",
        "Lieferung 2026 03 15",
        "Lieferung 202603-15",
    ):
        v = ordne_zu(tx("476.00", zweck, "Hans Meier"), [x, y], KONTAKTE)
        assert v is not None and not v.automatisch, zweck
        assert v.confidence <= 0.6 and "Datum" in v.begruendung, zweck
        # der eindeutige Betrag geht der Datumsreferenz vor
        assert _anteile(v) == [("2026-0001", D("476.00"), D("0"))], zweck
    v = ordne_zu(
        tx("400.00", "Lieferung vom 2026-03-15", "Hans Meier"), [x, y], KONTAKTE
    )
    assert v is not None and not v.automatisch and v.confidence <= 0.6
    # gleich gegliedert wie die Nummer: weiter eine Referenz
    v = ordne_zu(tx("400.00", "RE 2026 0315", "Hans Meier"), [x, y], KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.TEIL, True)


def test_nummer_ohne_trennzeichen_ist_ohne_erkannten_zahler_mehrdeutig():
    # Format {jahr}{nummer:04d}: „20260315“ ist als Nummer und als Datum gleich
    # geschrieben — ohne erkannten Zahler nie automatisch (vorher: „RE 20260315“ buchte
    # automatisch, „EREF+20260315-0042“ ebenso auf den fremden Kunden)
    ohne = op("20260315", "1190.00", kontakt=Y)
    for zweck in ("RE 20260315", "EREF+20260315-0042", "Lieferung vom 2026-03-15"):
        v = ordne_zu(tx("400.00", zweck, "Unbekannt"), [ohne], KONTAKTE)
        assert v is not None and not v.automatisch, zweck
        assert v.confidence <= 0.6 and "Datum" in v.begruendung, zweck
    keins = op("20261315", "1190.00", kontakt=Y)  # Monat 13: kein Datum
    v = ordne_zu(tx("400.00", "RE 20261315", "Unbekannt"), [keins], KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.TEIL, True)
    # mit Buchstaben in der Nummer selbst ist sie kein Datum
    re = op("RE20260315", "1190.00", kontakt=Y)
    v = ordne_zu(tx("400.00", "RE20260315", "Unbekannt"), [re], KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.TEIL, True)


def test_datum_bei_nummer_mit_praefix_ist_ohne_erkannten_zahler_keine_referenz():
    # Gegenprüfung: Format RE-{jahr}-{nummer:04d} — „RE 2026-03-15“ ergibt
    # zusammengesetzt RE-2026-0315; geprüft werden nur die Ziffernwörter (4-2-2 statt
    # 4-4 = ein Datum), das Präfix allein macht es nicht zur Referenz
    x = op("RE-2026-0001", "476.00", kontakt=X)
    y = op("RE-2026-0315", "1190.00", kontakt=Y)
    for zweck in (
        "RE 2026-03-15",
        "Re. 2026-03-15",
        "RE-2026-03-15",
        "Rechnung RE 2026/03/15",
    ):
        v = ordne_zu(tx("476.00", zweck, "Hans Meier"), [x, y], KONTAKTE)
        assert v is not None and not v.automatisch, zweck
        assert v.confidence <= 0.6 and "Datum" in v.begruendung, zweck
        assert _anteile(v) == [("RE-2026-0001", D("476.00"), D("0"))], zweck
    # gleich gegliedert wie die Nummer: weiter eine Referenz
    for zweck in ("RE 2026 0315", "RE-2026-0315", "Rechnung RE2026-0315"):
        v = ordne_zu(tx("400.00", zweck, "Hans Meier"), [x, y], KONTAKTE)
        assert (v.stufe, v.automatisch) == (Stufe.TEIL, True), zweck


def test_echte_referenz_geht_einer_nummer_nur_als_datum_vor():
    # Gegenprüfung: neben einer echten Referenz zählt ein nur als Datum genannter
    # Posten nicht mit — weder als zweite Rechnung noch als Gutschrift
    x = op("2026-0001", "476.00", kontakt=X)
    y = op("2026-0315", "1190.00", kontakt=Y)
    zweck = "RE 2026-0001 vom 2026-03-15"
    for zahler in ("Hans Meier", "Kunde X GmbH"):
        v = ordne_zu(tx("476.00", zweck, zahler), [x, y], KONTAKTE)
        assert (v.stufe, v.automatisch) == (Stufe.REFERENZ, True), zahler
        assert _anteile(v) == [("2026-0001", D("476.00"), D("0"))], zahler
    rechnung = op("2026-0001", "595.00")
    gutschrift = op("2026-0315", "-119.00")
    for zahler in ("Hans Meier", "Kunde AG"):
        v = ordne_zu(tx("595.00", zweck, zahler), [rechnung, gutschrift], KONTAKTE)
        assert (v.stufe, v.automatisch) == (Stufe.REFERENZ, True), zahler
        assert _anteile(v) == [("2026-0001", D("595.00"), D("0"))], zahler


def test_eigener_posten_nur_als_datum_hebt_den_widerspruch_nicht_auf():
    # Gegenprüfung: Zahler X, der Zweck nennt 2026-0500 von Kunde Y und X' eigene
    # 2026-0315 nur als Datum — wie ohne das Datum höchstens ein Vorschlag (0,7)
    eigen = op("2026-0315", "476.00", kontakt=X)
    fremd = op("2026-0500", "800.00", kontakt=Y)
    for zweck in ("RE 2026-0500 vom 2026-03-15", "RE 2026-0500"):
        v = ordne_zu(tx("476.00", zweck, "Kunde X GmbH"), [eigen, fremd], KONTAKTE)
        assert v is not None and not v.automatisch, zweck
        assert v.confidence <= 0.7 and "anderen Kontakts" in v.begruendung, zweck


def test_datum_im_zweck_trifft_beim_zahler_nicht_den_falschen_eigenen_posten():
    # Erkannter Zahler mit zwei eigenen Posten: das Datum „2026-03-15“ ist keine
    # Referenz auf seine 2026-0315 — der eindeutige Betrag entscheidet
    a = op("2026-0001", "476.00", kontakt=X)
    b = op("2026-0315", "1190.00", kontakt=X)
    zweck = "Lieferung vom 2026-03-15"
    v = ordne_zu(tx("476.00", zweck, "Kunde X GmbH"), [a, b], KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.EXAKT, True)
    assert _anteile(v) == [("2026-0001", D("476.00"), D("0"))]
    # Betrag passt zu keinem Posten: der genannte Posten nur als Vorschlag
    v = ordne_zu(tx("400.00", zweck, "Kunde X GmbH"), [a, b], KONTAKTE)
    assert not v.automatisch and v.confidence <= 0.6 and "Datum" in v.begruendung
    assert _anteile(v) == [("2026-0315", D("400.00"), D("0"))]
    # eine echte Referenz bleibt automatisch
    v = ordne_zu(tx("400.00", "RE 2026-0315", "Kunde X GmbH"), [a, b], KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.TEIL, True)


def test_referenz_ohne_erkannten_zahler_bleibt_automatisch():
    y = op("2026-0315", "1190.00", kontakt=Y)
    v = ordne_zu(tx("400.00", "RE 2026-0315", "Unbekannt"), [y], KONTAKTE)
    assert (v.stufe, v.automatisch) == (Stufe.TEIL, True)


# --- Ausgleich: Guthaben bleibt als Posten (B4) ------------------------------------


@pytest.fixture
def fabrik():
    return neue_db()


def _speichere_tx(fabrik, t):
    with fabrik() as s:
        speichere_transaktion(s, t)
        s.commit()
    return t


def _kunde_mit_posten(fabrik, *posten_):
    k = debitor(name="Kunde AG", konto="10000")
    posten_ = [p.model_copy(update={"kontakt_id": k.id}) for p in posten_]
    speichere(fabrik, [k], posten_)
    return k, posten_


def test_ueberzahlung_bleibt_als_guthaben_am_posten(fabrik):
    _, (p,) = _kunde_mit_posten(fabrik, op("2026-0001", "1190.00"))
    t = _speichere_tx(fabrik, tx("1240.00", "INV 2026-0001"))
    with fabrik() as s:
        gleiche_aus(s, t, [Anteil(p, D("1240.00"))], EINSTELLUNGEN)
        s.commit()
        neu = lade_einen_posten(s, p.id)
        (b,) = [b for b in lade_buchungen(s) if b.transaktion_id == t.id]
    assert (neu.restbetrag, neu.status) == (D("-50.00"), PostenStatus.TEILBEZAHLT)
    assert (b.soll_konto, b.haben_konto, b.betrag_netto) == (
        "1200",
        "10000",
        D("1240.00"),
    )


def test_negativer_anteil_bucht_die_erstattung_umgekehrt(fabrik):
    _, (p,) = _kunde_mit_posten(fabrik, op("2026-0002", "-119.00"))
    t = _speichere_tx(fabrik, tx("-119.00", "ERSTATTUNG 2026-0002"))
    with fabrik() as s:
        gleiche_aus(s, t, [Anteil(p, D("-119.00"))], EINSTELLUNGEN)
        s.commit()
        neu = lade_einen_posten(s, p.id)
        (b,) = [b for b in lade_buchungen(s) if b.transaktion_id == t.id]
    assert (neu.restbetrag, neu.status) == (D("0.00"), PostenStatus.AUSGEGLICHEN)
    assert (b.soll_konto, b.haben_konto, b.betrag_netto) == (
        "10000",
        "1200",
        D("119.00"),
    )


def test_saldozahlung_gleicht_rechnung_und_gutschrift_aus(fabrik):
    _, (r, g) = _kunde_mit_posten(
        fabrik, op("2026-0001", "595.00"), op("2026-0002", "-119.00")
    )
    t = _speichere_tx(
        fabrik, tx("476.00", "RE 2026-0001 ABZGL KORREKTUR 2026-0002", "Kunde AG")
    )
    with fabrik() as s:
        lauf = zuordne_zahlungen(s, EINSTELLUNGEN)
        s.commit()
    assert len(lauf.vorgeschlagen) == 1
    from accounti.opos.zahlungslauf import bestaetige

    with fabrik() as s:
        buchungen = bestaetige(s, str(t.id)[:8], EINSTELLUNGEN, "Prüferin")
        s.commit()
        assert {lade_einen_posten(s, x.id).status for x in (r, g)} == {
            PostenStatus.AUSGEGLICHEN
        }
    bank = sum(
        (b.betrag_netto if b.soll_konto == "1200" else -b.betrag_netto)
        for b in buchungen
    )
    assert bank == D("476.00")


def test_saldozahlung_bucht_den_gutschriftanteil_als_verrechnung(fabrik):
    # Nachprüfung N3: der Gutschriftanteil einer Saldozahlung ist keine Erstattung —
    # es fließt kein Geld an den Kunden zurück
    _, (r, g, gut) = _kunde_mit_posten(
        fabrik,
        op("2026-0001", "595.00"),
        op("2026-0002", "-119.00"),
        op("2026-0004", "-50.00"),
    )
    t = _speichere_tx(fabrik, tx("476.00", "RE 2026-0001 ABZGL 2026-0002", "Kunde AG"))
    with fabrik() as s:
        buchungen = gleiche_aus(
            s, t, [Anteil(r, D("595.00")), Anteil(g, D("-119.00"))], EINSTELLUNGEN
        )
        s.commit()
    texte = {b.beleg_nummer: b.buchungstext for b in buchungen}
    assert texte["2026-0001"].startswith("Zahlung 2026-0001")
    assert texte["2026-0002"].startswith("Verrechnung 2026-0002")
    # eine echte Erstattung (Geld geht an den Kunden) heißt weiter so
    e = _speichere_tx(fabrik, tx("-50.00", "ERSTATTUNG"))
    with fabrik() as s:
        (b,) = gleiche_aus(s, e, [Anteil(gut, D("-50.00"))], EINSTELLUNGEN)
        s.commit()
    assert b.buchungstext.startswith("Erstattung 2026-0004")


def test_kunde_mit_guthaben_wird_nicht_gemahnt(fabrik):
    _kunde_mit_posten(
        fabrik,
        op("2026-0001", "1190.00", rest="-50.00", faellig=date(2026, 3, 1)),
        op("2026-0002", "1190.00", faellig=date(2026, 4, 1)),
    )
    with fabrik() as s:
        lauf = mahnlauf(s, date(2026, 6, 15), MahnEinstellungen())
    assert lauf.mahnungen == []
    assert any("Guthaben" in a.grund for a in lauf.ausnahmen)


# --- Verrechnung (B3) ----------------------------------------------------------------


def test_verrechnen_gleicht_gutschrift_gegen_rechnung_aus_ohne_buchung(fabrik):
    _, (r, g) = _kunde_mit_posten(
        fabrik, op("2026-0001", "595.00"), op("2026-0002", "-119.00")
    )
    with fabrik() as s:
        ergebnis = verrechne(
            s, ["2026-0002", "2026-0001"], date(2026, 3, 6), person="Prüferin"
        )
        s.commit()
        rechnung, gutschrift = lade_einen_posten(s, r.id), lade_einen_posten(s, g.id)
        (v,) = lade_verrechnungen(s)
        assert lade_buchungen(s) == []
    assert [(x.betrag, x.posten_id, x.gegen_posten_id) for x in ergebnis] == [
        (D("119.00"), r.id, g.id)
    ]
    assert (rechnung.restbetrag, rechnung.status) == (
        D("476.00"),
        PostenStatus.TEILBEZAHLT,
    )
    assert (gutschrift.restbetrag, gutschrift.status) == (
        D("0.00"),
        PostenStatus.AUSGEGLICHEN,
    )
    assert (v.datum, v.person) == (date(2026, 3, 6), "Prüferin")


def _verrechnet(fabrik):
    _kunde_mit_posten(fabrik, op("2026-0001", "595.00"), op("2026-0002", "-119.00"))
    with fabrik() as s:
        verrechne(s, ["2026-0002", "2026-0001"], date(2026, 3, 6), person="Prüferin")
        s.commit()


def test_verrechnungen_sind_auch_fuer_rohes_sql_unveraenderbar(fabrik):
    # Nachprüfung N6: wie Journal und USt-IdNr.-Protokoll ein SQLite-Trigger
    _verrechnet(fabrik)
    with fabrik() as s:
        for sql in ("UPDATE verrechnungen SET betrag = 1", "DELETE FROM verrechnungen"):
            with pytest.raises(DatabaseError, match="unveränderbar"):
                s.execute(text(sql))
            s.rollback()


@pytest.mark.parametrize(
    ("sql", "art"),
    [
        ("UPDATE verrechnungen SET betrag = 1", "abweichung"),
        ("DELETE FROM verrechnungen", "fehlt"),
    ],
)
def test_journal_pruefen_gleicht_verrechnungen_mit_dem_bestand_ab(fabrik, sql, art):
    # Nachprüfung N6: an accounti vorbei (Trigger entfernt bzw. PostgreSQL)
    _verrechnet(fabrik)
    with fabrik() as s:
        assert pruefe_journal(s).in_ordnung
    with fabrik() as s:
        for aktion in ("update", "delete"):
            s.execute(text(f"DROP TRIGGER IF EXISTS verrechnungen_kein_{aktion}"))
        s.execute(text(sql))
        s.commit()
    with fabrik() as s:
        p = pruefe_journal(s)
    assert [(b.art, b.text.split()[0]) for b in p.befunde] == [(art, "verrechnung")]


@mit_postgresql
def test_journal_pruefen_findet_geaenderte_verrechnung_auf_postgresql(pg_datenbank):
    # PostgreSQL hat keinen Trigger — dort trägt der Bestandsabgleich (N6)
    engine, fabrik = session_factory(pg_datenbank())
    init_db(engine)
    _verrechnet(fabrik)
    with fabrik() as s:
        assert pruefe_journal(s).in_ordnung
        s.execute(text("UPDATE verrechnungen SET betrag = 1"))
        s.commit()
    with fabrik() as s:
        p = pruefe_journal(s)
    engine.dispose()
    assert [(b.art, b.text.split()[0]) for b in p.befunde] == [
        ("abweichung", "verrechnung")
    ]


def test_verrechnen_verlangt_gegenlaeufige_posten_desselben_kontakts(fabrik):
    k, (r,) = _kunde_mit_posten(fabrik, op("2026-0001", "595.00"))
    andere = debitor(name="Andere GmbH", konto="10009")
    fremd = op("2026-0009", "-50.00", kontakt=andere)
    speichere(fabrik, [andere], [fremd])
    with fabrik() as s, pytest.raises(VerrechnungError, match="Kontakt"):
        verrechne(s, ["2026-0001", "2026-0009"], date(2026, 3, 6))
    zweite = op("2026-0003", "100.00", kontakt=k)
    speichere(fabrik, [], [zweite], [beleg_zu(zweite)])
    with fabrik() as s, pytest.raises(VerrechnungError, match="gegenläufig"):
        verrechne(s, ["2026-0001", "2026-0003"], date(2026, 3, 6))


def test_verrechnen_nicht_vor_belegdatum_oder_der_zahlung_des_guthabens(fabrik):
    # Nachprüfung N2: Guthaben aus der Überzahlung vom 20.03., Folgerechnung vom 05.03.
    # bzw. 10.06. — eine Verrechnung davor passte nicht zur Stichtagsliste
    k, _ = _kunde_mit_posten(fabrik, op("2026-0001", "1190.00"))
    t = _speichere_tx(fabrik, tx("1200.00", "INV 2026-0001", "Kunde AG"))
    with fabrik() as s:
        ordne_von_hand(s, str(t.id)[:8], ["2026-0001"], EINSTELLUNGEN, "Prüferin")
        s.commit()
    frueh = op("2026-0002", "500.00", kontakt=k).model_copy(
        update={"belegdatum": date(2026, 3, 5)}
    )
    spaet = op("2026-0003", "500.00", kontakt=k).model_copy(
        update={"belegdatum": date(2026, 6, 10)}
    )
    speichere(fabrik, [], [frueh, spaet], [beleg_zu(frueh), beleg_zu(spaet)])
    for nummer, tag, grund in (
        ("2026-0002", date(2026, 3, 10), "Zahlung, aus der das Guthaben 2026-0001"),
        ("2026-0003", date(2026, 4, 1), "Belegdatum von 2026-0003"),
    ):
        with fabrik() as s, pytest.raises(VerrechnungError, match=grund):
            verrechne(s, ["2026-0001", nummer], tag)
    with fabrik() as s:
        (v,) = verrechne(s, ["2026-0001", "2026-0002"], date(2026, 3, 20))
        s.commit()
    assert (v.betrag, v.datum) == (D("10.00"), date(2026, 3, 20))


# --- Handzuordnung (B6) --------------------------------------------------------------


def test_handzuordnung_bucht_mit_pruefvermerk_und_guthaben(fabrik):
    _, (p,) = _kunde_mit_posten(fabrik, op("2026-0001", "1190.00"))
    t = _speichere_tx(fabrik, tx("1200.00", "IHRE LIEFERUNG SEPTEMBER", "Kunde AG"))
    with fabrik() as s:
        ergebnis = ordne_von_hand(
            s, str(t.id)[:8], ["2026-0001"], EINSTELLUNGEN, "Prüferin"
        )
        s.commit()
        neu = lade_einen_posten(s, p.id)
        (z,) = lade_zuordnungen(s)
    assert [(a.betrag, a.posten.id) for a in ergebnis.anteile] == [(D("1200.00"), p.id)]
    assert {b.geprueft_von for b in ergebnis.buchungen} == {"Prüferin"}
    assert (neu.restbetrag, neu.status) == (D("-10.00"), PostenStatus.TEILBEZAHLT)
    assert (z.stufe, z.status) == ("hand", ZuordnungStatus.GEBUCHT)
    with fabrik() as s, pytest.raises(ZahlungslaufError, match="nicht offen"):
        ordne_von_hand(s, str(t.id)[:8], ["2026-0001"], EINSTELLUNGEN, "Prüferin")


def test_handzuordnung_verteilt_und_nimmt_gutschriften_ganz(fabrik):
    _, (r, g) = _kunde_mit_posten(
        fabrik, op("2026-0001", "595.00"), op("2026-0002", "-119.00")
    )
    t = _speichere_tx(fabrik, tx("400.00", "Teilzahlung"))
    with fabrik() as s:
        ordne_von_hand(
            s, str(t.id)[:8], ["2026-0001", "2026-0002"], EINSTELLUNGEN, "Prüferin"
        )
        s.commit()
        assert lade_einen_posten(s, r.id).restbetrag == D("76.00")
        assert lade_einen_posten(s, g.id).status is PostenStatus.AUSGEGLICHEN


def test_handzuordnung_bei_offenem_vorschlag_erst_ablehnen(fabrik):
    _kunde_mit_posten(fabrik, op("2026-0001", "1190.00"))
    t = _speichere_tx(fabrik, tx("600.00", "Abschlag", "Kunde AG"))
    with fabrik() as s:
        assert len(zuordne_zahlungen(s, EINSTELLUNGEN).vorgeschlagen) == 1
        s.commit()
    with fabrik() as s, pytest.raises(ZahlungslaufError, match="ablehnen"):
        ordne_von_hand(s, str(t.id)[:8], ["2026-0001"], EINSTELLUNGEN, "Prüferin")


def test_handzuordnung_verrechnet_nicht_ueber_zwei_personenkonten(fabrik):
    # Nachprüfung N1: Forderung gegen Verbindlichkeit bzw. Gutschrift eines anderen
    # Kunden — das wäre eine Aufrechnung über zwei Personenkonten
    k = debitor(name=BEIDE.name, konto="10005", kreditor_konto="70005")
    andere = debitor(name="Andere GmbH", konto="10009")
    posten_ = [
        op("2026-0001", "1000.00", kontakt=k),
        op("ER-4711", "300.00", kontakt=k, richtung=V),
        op("2026-0009", "-50.00", kontakt=andere),
    ]
    speichere(fabrik, [k, andere], posten_)
    t = _speichere_tx(fabrik, tx("700.00", "Zahlung"))
    for zweite in ("ER-4711", "2026-0009"):
        with fabrik() as s, pytest.raises(ZahlungslaufError, match="Personenkonten"):
            ordne_von_hand(
                s, str(t.id)[:8], ["2026-0001", zweite], EINSTELLUNGEN, "Prüferin"
            )
    with fabrik() as s:
        assert lade_zuordnungen(s) == []


def test_handzuordnung_rechnet_ein_guthaben_nur_gegen_posten_desselben_kontakts():
    # Gegenprüfung (Rest N1): Rechnung von Y, Rechnung und Gutschrift von X — das
    # Guthaben von X tilgt nur die Rechnung von X, nie die von Y (keine Aufrechnung
    # über zwei Personenkonten); die Zahlung verteilt sich dann wie angegeben
    rechnung_y = op("2026-0001", "595.00", kontakt=Y)
    rechnung_x = op("2026-0002", "595.00", kontakt=X)
    gutschrift_x = op("2026-0003", "-119.00", kontakt=X)
    anteile = verteile(tx("476.00", "Zahlung"), [rechnung_y, rechnung_x, gutschrift_x])
    assert sorted((a.posten.belegnummer, a.betrag) for a in anteile) == [
        ("2026-0001", D("476.00")),
        ("2026-0002", D("119.00")),
        ("2026-0003", D("-119.00")),
    ]
    assert sum(a.betrag for a in anteile) == D("476.00")
    # übersteigt das Guthaben die eigenen Rechnungen, bleibt der Rest stehen
    klein_x = op("2026-0004", "100.00", kontakt=X)
    anteile = verteile(tx("495.00", "Zahlung"), [klein_x, gutschrift_x, rechnung_y])
    assert sorted((a.posten.belegnummer, a.betrag) for a in anteile) == [
        ("2026-0001", D("495.00")),
        ("2026-0003", D("-100.00")),
        ("2026-0004", D("100.00")),
    ]


def test_handzuordnung_richtung_muss_passen(fabrik):
    k = kreditor()
    p = op("RE-77", "100.00", kontakt=k, richtung=V)
    speichere(fabrik, [k], [p])
    t = _speichere_tx(fabrik, tx("100.00", "Eingang"))
    with fabrik() as s, pytest.raises(ZahlungslaufError, match="tilgt"):
        ordne_von_hand(s, str(t.id)[:8], ["RE-77"], EINSTELLUNGEN, "Prüferin")


def test_guthaben_aus_ueberzahlung_ist_kein_fehler_der_postenliste(make_session):
    from accounti.db.repository import speichere_posten
    from accounti.models.pruefung import Schwere
    from tests.pruefung_hilfe import anlegen
    from tests.pruefung_hilfe import kontakt as pruef_kontakt
    from tests.test_pruefung_regeln import pruefe

    k = pruef_kontakt()
    guthaben = op("2026-0001", "1190.00", kontakt=k, rest="-50.00")
    kaputt = op("2026-0002", "100.00", kontakt=k, rest="150.00")
    anlegen(make_session, k)
    with make_session() as s:
        for p in (guthaben, kaputt):
            speichere_posten(s, p.model_copy(update={"belegdatum": date(2026, 9, 1)}))
        s.commit()
    befunde = {b.objekt_id: b for b in pruefe(make_session, "op_alter")}
    assert befunde[str(kaputt.id)].schwere is Schwere.FEHLER
    assert befunde[str(guthaben.id)].schwere is Schwere.HINWEIS
    assert "Guthaben" in befunde[str(guthaben.id)].text


def test_verrechnetes_guthaben_ist_kein_befund_der_abstimmung(make_session, tmp_path):
    """Nachprüfung Merge M-1: Ein Guthaben aus einer Überzahlung, per ``opos
    verrechnen`` gegen eine neue Rechnung verrechnet — Personenkonto und offene Posten
    stimmen überein (28,50 €), zu jedem Stichtag."""
    from accounti.abschluss.pruefungen import kontext, pruefe_abschluss
    from accounti.db.repository import speichere_posten
    from accounti.models import BuchungStatus
    from tests.pruefung_hilfe import anlegen, buchung
    from tests.test_pruefung_regeln import pruefe

    k = debitor(name="Kunde AG", konto="10000")
    r1, r2 = (
        op("2026-0001", "119.00", kontakt=k),
        op("2026-0002", "59.50", kontakt=k).model_copy(
            update={"belegdatum": date(2026, 3, 20)}
        ),
    )

    def rechnung(p, netto, steuer):
        return buchung(
            soll="10000", haben="8400", netto=netto, steuer=steuer, schluessel=3,
            beleg_id=p.beleg_id, tag=p.belegdatum, status=BuchungStatus.AUTO_GEBUCHT,
        )  # fmt: skip

    anlegen(make_session, k, rechnung(r1, "100.00", "19.00"))
    with make_session() as s:
        speichere_posten(s, r1)
        s.commit()
    t = tx("150.00", "Zahlung", "Kunde AG", datum=date(2026, 3, 10))
    with make_session() as s:
        speichere_transaktion(s, t)
        ordne_von_hand(s, str(t.id)[:8], ["2026-0001"], EINSTELLUNGEN, "Prüferin")
        s.commit()
    anlegen(make_session, rechnung(r2, "50.00", "9.50"))
    with make_session() as s:
        speichere_posten(s, r2)
        verrechne(s, ["2026-0001", "2026-0002"], date(2026, 3, 20), grund="Test")
        s.commit()
        assert [lade_einen_posten(s, p.id).restbetrag for p in (r1, r2)] == [
            D("0.00"),
            D("28.50"),
        ]
    for stichtag in (date(2026, 3, 15), date(2026, 3, 31)):
        assert pruefe(make_session, "personenkonto_op", stichtag=stichtag) == []
    with make_session() as s:
        assert (
            pruefe_abschluss(
                kontext(s, 2026, tmp_path / "accounti.yaml"), nur=["personenkonten"]
            )
            == []
        )
