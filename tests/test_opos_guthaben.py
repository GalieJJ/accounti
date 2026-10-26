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
from accounti.opos.zuordnung import Anteil, Stufe, ordne_zu
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
