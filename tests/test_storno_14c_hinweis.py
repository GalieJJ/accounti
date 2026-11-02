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
