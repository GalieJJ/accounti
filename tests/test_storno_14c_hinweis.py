"""Storno ohne Neubuchung einer Belegbuchung mit ausgewiesener Umsatzsteuer
(Gesamttest 10b-1, Runde 5: g4w N2).

Das Storno bleibt erlaubt (eine Doppelbuchung ist so richtig aufzuheben, der Grund ist
Pflicht und steht im Journal). Hat der Beleg danach keine wirksame Buchung mehr, fehlt
seine Umsatzsteuer in der Voranmeldung — geschuldet wird sie, bis die Rechnung
berichtigt ist (§ 14c Abs. 1 UStG). Bisher meldete das niemand: Storno mit rc 0, UStVA
Kz 83 = 0, ``pruefen`` ohne Befund. Jetzt warnt das Storno (CLI und Browser), und die
Prüfregel ``beleg_ust_ohne_buchung`` meldet den Beleg, solange es so bleibt.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.konfiguration import Buchhaltung
from accounti.models import Belegart, Belegposition, Belegrichtung, BuchungStatus
from accounti.models.pruefung import Schwere
from accounti.pruefung.einstellungen import PruefEinstellungen
from accounti.pruefung.regeln import Kontext, fuehre_regeln_aus, zeitraum
from accounti.pruefung.storno import korrigiere, storniere
from tests.api_hilfe import csrf, formularwert
from tests.auth_hilfe import billige_hashes
from tests.pruefen_hilfe import pdf, queuewelt
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    beleg,
    buchung,
    db_url,
    kurz,
    make_session_fixture,
)

runner = CliRunner()
D = Decimal
REGEL = "beleg_ust_ohne_buchung"


def _ausgang(schluessel: int = 3):  # noqa: ANN202
    steuer = "95.00" if schluessel == 3 else "35.00"
    ar = beleg(
        belegart=Belegart.AUSGANGSRECHNUNG,
        richtung=Belegrichtung.AUSGANG,
        nummer="AR-1",
        tag=date(2026, 10, 1),
        netto="500.00",
        steuer=steuer,
        brutto=str(D("500.00") + D(steuer)),
        lieferant="Kunde K GmbH",
    )
    b = buchung(
        status=BuchungStatus.GEPRUEFT,
        soll="10001",
        haben="8400" if schluessel == 3 else "8300",
        netto="500.00",
        steuer=steuer,
        schluessel=schluessel,
        tag=date(2026, 10, 1),
        beleg_id=ar.id,
    )
    return ar, b


def _hinweis(warnungen: list[str]) -> list[str]:
    return [w for w in warnungen if "§ 14c" in w]


def _pruefe(make_session, period: str | None = "2026-10"):  # noqa: ANN001, ANN202
    von, bis = zeitraum(period)
    with make_session() as s:
        k = Kontext(
            s, PruefEinstellungen(), Buchhaltung(), date(2026, 10, 20), von, bis
        )
        return fuehre_regeln_aus(k, [REGEL]).befunde


# --- Storno: Warnung ----------------------------------------------------------------


@pytest.mark.parametrize("schluessel", [3, 2])
def test_storno_der_einzigen_buchung_warnt(make_session, schluessel):
    ar, b = _ausgang(schluessel)
    anlegen(make_session, ar, b)
    with make_session() as s:
        k = storniere(s, str(b.id), grund="Rechnung storniert", von="erika")
        s.commit()
    (hinweis,) = _hinweis(k.warnungen)
    assert "AR-1" in hinweis and "keine wirksame Buchung" in hinweis
    assert "Gutschrift/Rechnungskorrektur" in hinweis


def test_storno_einer_doppelbuchung_warnt_nicht(make_session):
    ar, b = _ausgang()
    doppel = b.model_copy(update={"id": uuid4()})
    anlegen(make_session, ar, b, doppel)
    with make_session() as s:
        k = storniere(s, str(doppel.id), grund="doppelt", von="erika")
        s.commit()
    assert _hinweis(k.warnungen) == []
    assert _pruefe(make_session) == []


def test_korrektur_mit_neubuchung_warnt_nicht(make_session):
    ar, b = _ausgang()
    anlegen(make_session, ar, b)
    with make_session() as s:
        k = korrigiere(s, str(b.id), "10002", "8400", von="erika")
        s.commit()
    assert _hinweis(k.warnungen) == []
    assert _pruefe(make_session) == []


def test_storno_eingangsrechnung_mit_vorsteuer_warnt_nicht(make_session):
    """Vorsteuer muss niemand ziehen — § 14c betrifft die ausgewiesene Steuer."""
    er = beleg(tag=date(2026, 10, 2))
    b = buchung(
        status=BuchungStatus.GEPRUEFT,
        soll="4900",
        haben="70001",
        tag=date(2026, 10, 2),
        beleg_id=er.id,
    )
    anlegen(make_session, er, b)
    with make_session() as s:
        k = storniere(s, str(b.id), grund="doppelt erfasst", von="erika")
        s.commit()
    assert _hinweis(k.warnungen) == []
    assert _pruefe(make_session) == []


# --- Prüfregel ----------------------------------------------------------------------


def test_pruefregel_meldet_beleg_ohne_wirksame_buchung(make_session):
    ar, b = _ausgang()
    anlegen(make_session, ar, b)
    assert _pruefe(make_session) == []  # gebucht: kein Befund
    with make_session() as s:
        storniere(s, str(b.id), grund="Rechnung storniert", von="erika")
        s.commit()
    (befund,) = _pruefe(make_session)
    assert (befund.regel, befund.schwere, befund.objekt_typ) == (
        REGEL,
        Schwere.WARNUNG,
        "beleg",
    )
    assert befund.objekt_id == str(ar.id)
    assert "AR-1" in befund.text and "§ 14c" in befund.text
    assert befund.betrag == D("95.00")
    assert _pruefe(make_session, "2026-09") == []  # im Zeitraum des Stornos


# --- CLI und Browser ------------------------------------------------------------------


def test_cli_buchung_storniere_warnt(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    from accounti.db import init_db, session_factory

    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    ar, b = _ausgang()
    anlegen(fabrik, ar, b)
    r = runner.invoke(
        app,
        ["buchung", "storniere", kurz(b.id), "--grund", "storniert", "--db", url],
        env={"COLUMNS": "300"},
    )
    engine.dispose()
    text = " ".join(r.output.split())
    assert r.exit_code == 0, r.output
    assert "Storniert:" in text and "§ 14c" in text and "keine wirksame Buchung" in text


@pytest.fixture
def qw(tmp_path, monkeypatch):
    billige_hashes(monkeypatch)
    return queuewelt(tmp_path)


def test_browser_stornieren_warnt(qw):
    bid = uuid4()
    ar = qw.beleg(
        pdf("Rechnung AR-1 Netto 500,00 USt 19 % 95,00"),
        id=bid,
        belegart=Belegart.AUSGANGSRECHNUNG,
        richtung=Belegrichtung.AUSGANG,
        belegnummer="AR-1",
        belegdatum=date(2026, 10, 1),
        lieferant_name="Kunde K GmbH",
        netto=D("500.00"),
        steuer=D("95.00"),
        brutto=D("595.00"),
        positionen=[
            Belegposition(
                beleg_id=bid, bezeichnung="Ware", netto=D("500.00"), steuersatz=D("19")
            )
        ],
    )
    b = qw.buchung(
        beleg_id=ar.id,
        soll="10001",
        haben="8400",
        betrag_netto=D("500.00"),
        steuer_schluessel=3,
        steuer_betrag=D("95.00"),
        status=BuchungStatus.GEPRUEFT,
        confidence=1.0,
    )
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/buchungen/{b.id}").text
    daten = {
        "csrf": csrf(client),
        "stand": formularwert(seite, "stand"),
        "grund": "Rechnung storniert",
        "einmalcode": qw.web.personen["jan"].codes[-1],
    }
    r = client.post(f"/buchungen/{b.id}/stornieren", data=daten)
    assert r.status_code == 200, r.status_code
    assert "§ 14c" in r.text and "keine wirksame Buchung" in r.text


# --- Runde 6 (g5w NEU-3, NEU-4): ausgewiesene USt je Satz -----------------------------
#
# Gezählt wird nur die ausgewiesene Umsatzsteuer: je Steuersatz die wirksam gebuchte
# Steuer (Schlüssel 2, 3, Rechnungsseite) gegen die des Belegs. Eine Zahlung mit
# derselben beleg_id (opos/ausgleich) oder eine Buchung zu einem anderen Satz deckt
# sie nicht (NEU-3); eine wegfallende Minderung (Gutschrift) fehlt nicht, und eine
# Dublette derselben Rechnung, die wirksam gebucht ist, deckt sie (NEU-4).


def _rechnung(nummer="AR-1", positionen=None, hash_="a", **kw):  # noqa: ANN001, ANN202
    positionen = positionen or [("Ware", "500.00", "19", "95.00")]
    netto = sum(D(p[1]) for p in positionen)
    steuer = sum(D(p[3]) for p in positionen)
    return beleg(
        belegart=Belegart.AUSGANGSRECHNUNG,
        richtung=Belegrichtung.AUSGANG,
        nummer=nummer,
        tag=date(2026, 10, 1),
        netto=str(netto),
        steuer=str(steuer),
        brutto=str(netto + steuer),
        lieferant="Kunde K GmbH",
        positionen=positionen,
        datei_hash=hash_ * 64,
        **kw,
    )


def _erloes(bel, haben="8400", netto="500.00", steuer="95.00", schluessel=3, **kw):  # noqa: ANN001, ANN202
    werte = {"soll": "10001", "haben": haben}
    werte.update(kw)
    return buchung(
        status=BuchungStatus.GEPRUEFT,
        netto=netto,
        steuer=steuer,
        schluessel=schluessel,
        tag=date(2026, 10, 1),
        beleg_id=bel.id,
        **werte,
    )


def test_bezahlte_rechnung_storno_warnt(make_session):
    """NEU-3 T1: die Zahlungsbuchung „1200 an 10001“ mit derselben beleg_id zählte als
    wirksame Buchung — Storno der Erlösbuchung ohne Warnung, Prüfregel stumm."""
    from tests.pruefung_hilfe import umsatz

    ar = _rechnung()
    b = _erloes(ar)
    tx = umsatz(betrag="595.00", tag=date(2026, 10, 10), zweck="AR-1")
    zahlung = buchung(
        tx, status=BuchungStatus.GEPRUEFT, soll="1200", haben="10001",
        netto="595.00", steuer=None, schluessel=None, beleg_id=ar.id,
    )  # fmt: skip
    anlegen(make_session, ar, b, tx, zahlung)
    with make_session() as s:
        k = storniere(s, str(b.id), grund="Test", von="erika")
        s.commit()
    (hinweis,) = _hinweis(k.warnungen)
    assert "AR-1" in hinweis and "95,00 €" in hinweis
    (befund,) = _pruefe(make_session)
    assert befund.objekt_id == str(ar.id) and befund.betrag == D("95.00")


def test_zwei_steuersaetze_storno_einer_buchung_warnt(make_session):
    """NEU-3 T2: Beleg mit 19 % und 7 %, nur die 19-%-Buchung storniert — die 7-%-
    Buchung zählte als wirksame Buchung des Belegs."""
    ar = _rechnung(
        "AR-2",
        [("Ware 19", "500.00", "19", "95.00"), ("Buch 7", "100.00", "7", "7.00")],
    )
    b19 = _erloes(ar)
    b7 = _erloes(ar, haben="8300", netto="100.00", steuer="7.00", schluessel=2)
    anlegen(make_session, ar, b19, b7)
    with make_session() as s:
        k = storniere(s, str(b19.id), grund="Test", von="erika")
        s.commit()
    (hinweis,) = _hinweis(k.warnungen)
    assert "95,00 €" in hinweis and "19 %" in hinweis and "7,00" not in hinweis
    (befund,) = _pruefe(make_session)
    assert befund.betrag == D("95.00") and "19 %" in befund.text
    # die 7-%-Buchung storniert: jetzt fehlt beides
    with make_session() as s:
        k = storniere(s, str(b7.id), grund="Test", von="erika")
        s.commit()
    (hinweis,) = _hinweis(k.warnungen)
    assert "95,00 €" in hinweis and "7,00 €" in hinweis
    (befund,) = _pruefe(make_session)
    assert befund.betrag == D("102.00")


def test_teilweise_gebucht_nennt_den_rest(make_session):
    """Zwei 19-%-Buchungen (zwei Erlöskonten), eine storniert: 60 € fehlen."""
    ar = _rechnung(
        "AR-5",
        [("Ware", "300.00", "19", "57.00"), ("Dienst", "200.00", "19", "38.00")],
    )
    a = _erloes(ar, netto="300.00", steuer="57.00")
    b = _erloes(ar, haben="8401", netto="200.00", steuer="38.00")
    anlegen(make_session, ar, a, b)
    with make_session() as s:
        k = storniere(s, str(b.id), grund="Test", von="erika")
        s.commit()
    (hinweis,) = _hinweis(k.warnungen)
    assert "38,00 €" in hinweis and "57,00 €" in hinweis  # fehlt, noch gebucht


def test_dublette_storno_der_doppelbuchung_warnt_nicht(make_session):
    """NEU-4 T3: zweiter Belegdatensatz derselben Rechnung (Lieferant, Nummer,
    Betrag gleich), beide gebucht; die Doppelbuchung des zweiten storniert — die
    Steuer steht über den ersten in der Voranmeldung."""
    a = _rechnung("AR-3", hash_="a")
    kopie = _rechnung("AR-3", hash_="b")
    ba, bk = _erloes(a), _erloes(kopie)
    anlegen(make_session, a, kopie, ba, bk)
    with make_session() as s:
        k = storniere(s, str(bk.id), grund="doppelt", von="erika")
        s.commit()
    assert _hinweis(k.warnungen) == []
    assert _pruefe(make_session) == []
    # beide storniert: ein Befund für die Rechnung, nicht zwei
    with make_session() as s:
        k = storniere(s, str(ba.id), grund="Rechnung storniert", von="erika")
        s.commit()
    assert len(_hinweis(k.warnungen)) == 1
    assert len(_pruefe(make_session)) == 1


def test_andere_rechnung_gleicher_nummer_deckt_nicht(make_session):
    """Gleiche Nummer, anderer Betrag (berichtigte Rechnung): keine Kopie."""
    a = _rechnung("AR-6", hash_="a")
    andere = _rechnung("AR-6", [("Ware", "400.00", "19", "76.00")], hash_="b")
    ba, bo = _erloes(a), _erloes(andere, netto="400.00", steuer="76.00")
    anlegen(make_session, a, andere, ba, bo)
    with make_session() as s:
        k = storniere(s, str(ba.id), grund="Test", von="erika")
        s.commit()
    (hinweis,) = _hinweis(k.warnungen)
    assert "95,00 €" in hinweis


def test_storno_einer_gutschrift_fehlt_nicht(make_session):
    """NEU-4 T4: Gutschrift GS-4 (Belegsteuer −95) storniert — die Steuer steigt, sie
    fehlt nicht; die Regel meldete „die -95,00 € Umsatzsteuer fehlt“."""
    r = _rechnung("AR-4")
    gs = beleg(
        belegart=Belegart.AUSGANGSRECHNUNG,
        richtung=Belegrichtung.AUSGANG,
        nummer="GS-4",
        tag=date(2026, 10, 1),
        netto="-500.00",
        steuer="-95.00",
        brutto="-595.00",
        lieferant="Kunde K GmbH",
        positionen=[("Gutschrift", "-500.00", "19", "-95.00")],
        datei_hash="c" * 64,
    )
    br = _erloes(r)
    bg = _erloes(gs, soll="8400", haben="10001")
    anlegen(make_session, r, gs, br, bg)
    with make_session() as s:
        k = storniere(s, str(bg.id), grund="Gutschrift zurückgenommen", von="erika")
        s.commit()
    assert _hinweis(k.warnungen) == []
    assert _pruefe(make_session) == []


def test_skonto_ist_keine_luecke(make_session):
    """Eine Minderung (Skonto mit Schlüssel 3) desselben Belegs mindert die Steuer nach
    § 17 — sie ist keine fehlende Rechnungssteuer: Korrektur der Erlösbuchung (Storno
    und Neubuchung) mit Skonto auf dem Beleg meldet nichts."""
    ar = _rechnung()
    b = _erloes(ar)
    skonto = _erloes(ar, soll="8736", haben="10001", netto="10.00", steuer="1.90")
    anlegen(make_session, ar, b, skonto)
    with make_session() as s:
        korrigiere(s, str(b.id), "10002", "8400", von="erika")
        s.commit()
    assert _pruefe(make_session) == []


def test_zahlungsstorno_verschiebt_die_meldung_nicht(make_session):
    """g6w N3 (T15, Runde 7): Rechnung im Oktober storniert, die Zahlung mit derselben
    beleg_id im Dezember — die Meldung blieb nicht im Oktober (wo die Umsatzsteuer
    fehlt), sondern wanderte in den Monat des Zahlungsstornos. Den Zeitraum bestimmt
    nur das Storno einer Buchung mit ausgewiesener Umsatzsteuer."""
    from tests.pruefung_hilfe import umsatz

    ar = _rechnung(nummer="AR-15")
    b = _erloes(ar)
    tx = umsatz(betrag="595.00", tag=date(2026, 10, 10), zweck="AR-15")
    zahlung = buchung(
        tx, status=BuchungStatus.GEPRUEFT, soll="1200", haben="10001",
        netto="595.00", steuer=None, schluessel=None, beleg_id=ar.id,
        tag=date(2026, 10, 10),
    )  # fmt: skip
    anlegen(make_session, ar, b, tx, zahlung)
    with make_session() as s:
        storniere(s, str(b.id), grund="Test", von="erika", datum=date(2026, 10, 20))
        storniere(s, str(zahlung.id), grund="umgeordnet", datum=date(2026, 12, 2))
        s.commit()
    (befund,) = _pruefe(make_session, "2026-10")
    assert befund.objekt_id == str(ar.id) and befund.datum == date(2026, 10, 20)
    assert _pruefe(make_session, "2026-12") == []
    assert len(_pruefe(make_session, None)) == 1


# --- Paket G (gf3-obergrenze GF3-1): Beleg ohne Steuerzeile ---------------------------
#
# Nennt keine Position einen Satz und gibt es keine eindeutige Belegsteuer — so legt die
# Erkennung einen Beleg ohne Steuerzeile an (eine Position „Gesamtbetrag“ ohne Satz,
# belege/erkennung.py) —, weist der Beleg die Steuer seiner Rechnungsbuchungen aus. Der
# Rückfall nahm die vorzeichenbehaftete Steuer der nach Datum letzten Buchung mit
# Schlüssel 2/3, auch einer (stornierten) Erlösschmälerung: ausgewiesen ≤ 0, keine
# Warnung, kein Befund, die 95 € fehlten still (o2_wege.py, o3_rueckfall.py,
# o4_rueckfall_cli.py, o5_rueckfall_ar.py).

OHNE_STEUERZEILE = {
    "Q": (Belegart.QUITTUNG, Belegrichtung.EINGANG, "1000"),
    "S": (Belegart.SONSTIGES, Belegrichtung.EINGANG, "1200"),
    "AR": (Belegart.AUSGANGSRECHNUNG, Belegrichtung.AUSGANG, "10001"),
}
T1, T2 = date(2026, 10, 1), date(2026, 10, 2)


def _ohne_steuerzeile(art, brutto="595.00", **kw):  # noqa: ANN001, ANN003, ANN202
    belegart, richtung, _ = OHNE_STEUERZEILE[art]
    werte: dict[str, str | None] = {"netto": None, "steuer": None}
    werte.update(kw)
    return beleg(
        belegart=belegart,
        richtung=richtung,
        nummer=f"OS-{art}",
        tag=T1,
        brutto=brutto,
        lieferant="Partner GmbH",
        positionen=[("Gesamtbetrag", brutto, None, None)],
        **werte,
    )


def _am(bel, soll, haben, steuer, netto="500.00", schluessel=3, tag=T1):  # noqa: ANN001, ANN202
    return buchung(
        status=BuchungStatus.GEPRUEFT,
        soll=soll,
        haben=haben,
        netto=netto,
        steuer=steuer,
        schluessel=schluessel,
        tag=tag,
        beleg_id=bel.id,
    )


# (Sollkonto der zweiten Buchung, ihr Tag, wird sie vor dem Erlös storniert?)
MINDERUNGEN = {
    "minderung_storniert": ("8700", T2, True),
    "minderung_wirksam": ("8700", T2, False),
    "minderung_selber_tag": ("8700", T1, False),
    "erstattung_8400_soll": ("8400", T2, False),
}


@pytest.mark.parametrize("fall", list(MINDERUNGEN))
@pytest.mark.parametrize("art", list(OHNE_STEUERZEILE))
def test_minderung_ohne_steuerzeile_hebt_die_steuer_des_belegs_nicht_auf(
    make_session, art, fall
):
    """GF3-1 (o2 W1b, o3 W1e/W1f/W1g, o5): Beleg ohne Steuerzeile, Erlös B1 „Geld an
    8400, Schlüssel 3, 500/95“ (01.10.), daneben B2 „8700 an Geld, Schlüssel 3,
    10/1,90“ bzw. eine Erstattung „8400 an Geld“ — B2 storniert oder wirksam, später
    oder am selben Tag. Nach dem Storno von B1 fehlen die 95 € des Belegs: Warnung und
    Befund 95 € wie ohne B2. Eine Minderung ist keine Rechnungsbuchung."""
    konto, tag, zuerst = MINDERUNGEN[fall]
    geld = OHNE_STEUERZEILE[art][2]
    bel = _ohne_steuerzeile(art)
    b1 = _am(bel, geld, "8400", "95.00")
    b2 = _am(bel, konto, geld, "1.90", netto="10.00", tag=tag)
    anlegen(make_session, bel, b1, b2)
    assert _pruefe(make_session, None) == []
    if zuerst:
        with make_session() as s:
            k = storniere(s, str(b2.id), grund="falsch erfasst", von="erika")
            s.commit()
        assert _hinweis(k.warnungen) == []
    with make_session() as s:
        k = storniere(s, str(b1.id), grund="doppelt erfasst", von="erika")
        s.commit()
    (hinweis,) = _hinweis(k.warnungen)
    assert f"OS-{art} weist 95,00 € Umsatzsteuer zu 19 %" in hinweis, hinweis
    (befund,) = _pruefe(make_session, None)
    assert befund.objekt_id == str(bel.id) and befund.betrag == D("95.00"), befund.text


@pytest.mark.parametrize("art", ["Q", "AR"])
def test_ohne_steuerzeile_mit_zwei_saetzen_zaehlt_den_erloes_je_satz(make_session, art):
    """GF3-1 (o3 W1i): Belegsteuer 130 bei Erlösen zu 19 % und 7 % (die Belegsteuer ist
    nicht eindeutig einem Satz zuzuordnen), dazu eine spätere Minderung zu 19 % — das
    Storno des 19-%-Erlöses meldet 95 € zu 19 %, nicht nichts."""
    geld = OHNE_STEUERZEILE[art][2]
    bel = _ohne_steuerzeile(art, brutto="1130.00", netto="1000.00", steuer="130.00")
    v19 = _am(bel, geld, "8400", "95.00")
    v7 = _am(bel, geld, "8300", "35.00", schluessel=2)
    m = _am(bel, "8700", geld, "1.90", netto="10.00", tag=T2)
    anlegen(make_session, bel, v19, v7, m)
    with make_session() as s:
        k = storniere(s, str(v19.id), grund="doppelt erfasst", von="erika")
        s.commit()
    (hinweis,) = _hinweis(k.warnungen)
    assert "weist 95,00 € Umsatzsteuer zu 19 %" in hinweis, hinweis
    (befund,) = _pruefe(make_session, None)
    assert befund.betrag == D("95.00"), befund.text


@pytest.mark.parametrize("art", ["Q", "S"])
def test_ohne_steuerzeile_nach_umbuchung_ohne_steuer_meldet_die_luecke(
    make_session, art
):
    """GF3-1 (o3 W1k, GF-1b-Weg): Minderung storniert, dann der Erlös über „→ 2700
    --steuer 3“ und „--ohne-steuer --grund“ berichtigt — die Prüfregel meldet 95 €."""
    geld = OHNE_STEUERZEILE[art][2]
    bel = _ohne_steuerzeile(art)
    b1 = _am(bel, geld, "8400", "95.00")
    b2 = _am(bel, "8700", geld, "1.90", netto="10.00", tag=T2)
    anlegen(make_session, bel, b1, b2)
    with make_session() as s:
        storniere(s, str(b2.id), grund="falsch erfasst", von="erika")
        k = korrigiere(s, str(b1.id), geld, "2700", steuer=3, von="erika")
        assert k.neu is not None
        korrigiere(
            s, str(k.neu.id), geld, "2700", ohne_steuer=True, grund="kein", von="erika"
        )
        s.commit()
    (befund,) = _pruefe(make_session, None)
    assert befund.betrag == D("95.00"), befund.text


def test_rechnungsbuchungen_einer_ausgangsrechnung_ohne_steuerzeile(make_session):
    """GF3-1 auf einer Ausgangsrechnung (eindeutige Belegart, keine Obergrenze) mit
    mehreren Rechnungsbuchungen: B1 „10001 an 8400“ korrigiert auf „10002 an 8400“
    (Storno und Neubuchung, 01.10.), Skonto „8736 an 10002, Schlüssel 3“ (02.10.)
    storniert, dann die Neubuchung storniert — es fehlen 95 €. Eine Doppelbuchung
    desselben Erlöses zählt nicht doppelt: ihr Storno warnt nicht."""
    bel = _ohne_steuerzeile("AR")
    b1 = _am(bel, "10001", "8400", "95.00")
    doppel = b1.model_copy(update={"id": uuid4()})
    anlegen(make_session, bel, b1, doppel)
    with make_session() as s:
        k = storniere(s, str(doppel.id), grund="doppelt", von="erika")
        s.commit()
    assert _hinweis(k.warnungen) == []
    with make_session() as s:
        k = korrigiere(s, str(b1.id), "10002", "8400", von="erika")
        s.commit()
    neu = k.neu
    assert neu is not None and _hinweis(k.warnungen) == []
    skonto = _am(bel, "8736", "10002", "1.90", netto="10.00", tag=T2)
    anlegen(make_session, skonto)
    with make_session() as s:
        k = storniere(s, str(skonto.id), grund="kein Skonto", von="erika")
        s.commit()
    assert _hinweis(k.warnungen) == [] and _pruefe(make_session, None) == []
    with make_session() as s:
        k = storniere(s, str(neu.id), grund="Rechnung storniert", von="erika")
        s.commit()
    (hinweis,) = _hinweis(k.warnungen)
    assert "OS-AR weist 95,00 € Umsatzsteuer zu 19 %" in hinweis, hinweis
    (befund,) = _pruefe(make_session, None)
    assert befund.betrag == D("95.00"), befund.text


@pytest.mark.parametrize("art", ["Q", "S"])
def test_cli_storno_der_minderung_dann_des_erloeses_ohne_steuerzeile(
    tmp_path, monkeypatch, art
):
    """GF3-1 über die echte CLI (o4_rueckfall_cli.py W1e): ``buchung storniere`` der
    Minderung B2, dann des Erlöses B1 — die Ausgabe warnt mit 95,00 €, ``accounti
    pruefen --regel beleg_ust_ohne_buchung`` meldet 95,00 € (vorher: keine Warnung,
    „keine Befunde“)."""
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    from accounti.db import init_db, session_factory

    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    geld = OHNE_STEUERZEILE[art][2]
    bel = _ohne_steuerzeile(art)
    b1 = _am(bel, geld, "8400", "95.00")
    b2 = _am(bel, "8700", geld, "1.90", netto="10.00", tag=T2)
    anlegen(fabrik, bel, b1, b2)
    engine.dispose()

    def cli(*argumente: str) -> str:
        r = runner.invoke(app, [*argumente, "--db", url], env={"COLUMNS": "250"})
        assert r.exit_code == 0, r.output
        return " ".join(r.output.split())

    text = cli("buchung", "storniere", kurz(b2.id), "--grund", "falsch erfasst",
               "--datum", "2026-10-02")  # fmt: skip
    assert "Storniert:" in text and "§ 14c" not in text, text
    text = cli("buchung", "storniere", kurz(b1.id), "--grund", "doppelt erfasst",
               "--datum", "2026-10-03")  # fmt: skip
    assert f"OS-{art} weist 95,00 € Umsatzsteuer" in text, text
    text = cli("pruefen", "--regel", REGEL)
    assert "1 Befunde" in text and "│ 95,00 │" in text, text
