"""Die Richtung einer Belegbuchung kommt aus dem Beleg (Gesamttest 10b-1, Runde 5:
g4w N1).

Eine Rechnung bucht ihr Sachkonto auf der einen Seite, eine Gutschrift bzw.
Rechnungskorrektur auf der anderen. Tauschte eine Korrektur Soll und Haben einer
Belegbuchung (``korrigiere <id> --soll 8400 --haben 10001`` auf „10001 an 8400,
Schlüssel 3“), las die Voranmeldung die Sachseite im Soll und kehrte das Vorzeichen um
(``steuer/kennziffern.py``): Kz 81 −500, Kz 83 −95 („Erstattung“), Freigabe möglich —
ohne Grund, im Browser über das normale Formular. Ausgewiesene Umsatzsteuer wird aber
geschuldet, bis die Rechnung berichtigt ist (§ 14c Abs. 1 UStG); die Berichtigung ist
ein eigener Beleg und wirkt in ihrem Zeitraum (§ 17 Abs. 1 UStG). Ebenso mindert eine
Eingangsrechnung die Vorsteuer erst mit der Gutschrift bzw. Rechnungskorrektur des
Lieferanten (§ 17 Abs. 1 Satz 2 UStG).

Konten derselben Richtung bleiben korrigierbar (anderes Personenkonto, anderes
Sachkonto auf derselben Seite); Buchungen ohne Beleg ebenso wie bisher.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db.repository import lade_buchungen
from accounti.models import Belegart, Belegposition, Belegrichtung, BuchungStatus
from accounti.pruefung.storno import StornoError, korrigiere
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
BERICHTIGUNG = "Berichtigung als eigener Beleg (Gutschrift/Rechnungskorrektur)"


def _ausgang(schluessel: int = 3):  # noqa: ANN202
    steuer, satz, erloes = ("95.00", "19", "8400") if schluessel == 3 else (
        "35.00", "7", "8300"
    )  # fmt: skip
    ar = beleg(
        belegart=Belegart.AUSGANGSRECHNUNG,
        richtung=Belegrichtung.AUSGANG,
        nummer="AR-1",
        tag=date(2026, 10, 1),
        netto="500.00",
        steuer=steuer,
        brutto=str(D("500.00") + D(steuer)),
        lieferant="Kunde K GmbH",
        positionen=[("Ware", "500.00", satz, steuer)],
    )
    b = buchung(
        status=BuchungStatus.GEPRUEFT,
        soll="10001",
        haben=erloes,
        netto="500.00",
        steuer=steuer,
        schluessel=schluessel,
        tag=date(2026, 10, 1),
        beleg_id=ar.id,
    )
    return ar, b


def _eingang(schluessel: int | None = 9):  # noqa: ANN202
    steuer = {9: "19.00", 8: "7.00", None: None}[schluessel]
    satz = {9: "19", 8: "7", None: None}[schluessel]
    er = beleg(
        netto="100.00",
        steuer=steuer or "0.00",
        brutto=str(D("100.00") + D(steuer or "0")),
        positionen=[("Leistung", "100.00", satz, steuer)],
    )
    b = buchung(
        status=BuchungStatus.GEPRUEFT,
        soll="4900",
        haben="70001",
        steuer=steuer,
        schluessel=schluessel,
        tag=date(2026, 10, 2),
        beleg_id=er.id,
    )
    return er, b


# --- Fachfunktion -------------------------------------------------------------------


@pytest.mark.parametrize("schluessel", [3, 2])
@pytest.mark.parametrize("status", [BuchungStatus.GEPRUEFT, BuchungStatus.ZUR_PRUEFUNG])
@pytest.mark.parametrize(
    "zusatz",
    [{}, {"grund": "doch Gutschrift"}, {"steuer": None}],
    ids=["ohne_grund", "mit_grund", "steuer_unveraendert"],
)
def test_seitentausch_ausgewiesener_ust_abgelehnt(
    make_session, schluessel, status, zusatz
):
    ar, b = _ausgang(schluessel)
    b = b.model_copy(update={"status": status})
    anlegen(make_session, ar, b)
    with make_session() as s:
        with pytest.raises(StornoError) as fehler:
            korrigiere(s, str(b.id), b.haben_konto, "10001", von="erika", **zusatz)
        s.rollback()
        (geblieben,) = lade_buchungen(s)
    assert "§ 14c" in fehler.value.meldung and "§ 17" in fehler.value.meldung
    assert BERICHTIGUNG in fehler.value.meldung and BERICHTIGUNG in str(fehler.value)
    assert fehler.value.feld == "soll"
    assert (geblieben.soll_konto, geblieben.haben_konto, geblieben.status) == (
        "10001",
        b.haben_konto,
        status,
    )


@pytest.mark.parametrize(
    ("soll", "haben", "steuer"),
    [
        ("8400", "1200", 3),  # anderes Gegenkonto, Seiten getauscht
        ("8400", "4900", 3),  # Sachkonto gegen Sachkonto: das Erlöskonto im Soll
        ("8401", "10001", 3),  # anderes Erlöskonto, Seiten getauscht
    ],
)
def test_seitentausch_auch_mit_anderen_konten(make_session, soll, haben, steuer):
    """Auch mit bestätigtem Schlüssel: Maßgeblich ist die Seite, auf der die
    Voranmeldung das Sachkonto liest — nicht, ob genau die alten Konten getauscht
    werden."""
    ar, b = _ausgang()
    anlegen(make_session, ar, b)
    with make_session() as s, pytest.raises(StornoError, match="§ 14c"):
        korrigiere(s, str(b.id), soll, haben, steuer=steuer, von="erika")


@pytest.mark.parametrize("schluessel", [9, 8])
def test_seitentausch_eingangsrechnung_mit_vorsteuer_abgelehnt(
    make_session, schluessel
):
    """Vorsteuer: die Gutschrift des Lieferanten mindert sie (§ 17 Abs. 1 Satz 2
    UStG), nicht das Umdrehen der Rechnung."""
    er, b = _eingang(schluessel)
    anlegen(make_session, er, b)
    with make_session() as s, pytest.raises(StornoError) as fehler:
        korrigiere(s, str(b.id), "70001", "4900", grund="Gutschrift", von="erika")
    assert "§ 17" in fehler.value.meldung and BERICHTIGUNG in fehler.value.meldung
    assert "§ 14c" not in fehler.value.meldung


def test_seitentausch_belegbuchung_ohne_steuer_abgelehnt(make_session):
    """Auch ohne Steuer bestimmt der Beleg die Richtung (Aufwand bleibt Aufwand)."""
    er, b = _eingang(None)
    anlegen(make_session, er, b)
    with make_session() as s, pytest.raises(StornoError) as fehler:
        korrigiere(s, str(b.id), "70001", "4900", von="erika")
    assert BERICHTIGUNG in fehler.value.meldung


@pytest.mark.parametrize(
    ("soll", "haben", "steuer"),
    [
        ("10002", "8400", None),  # anderes Personenkonto
        ("1400", "8400", None),  # Sammelkonto statt Personenkonto
        ("10001", "8401", 3),  # anderes Erlöskonto auf derselben Seite
    ],
)
def test_konten_derselben_richtung_bleiben_korrigierbar(
    make_session, soll, haben, steuer
):
    ar, b = _ausgang()
    anlegen(make_session, ar, b)
    with make_session() as s:
        k = korrigiere(s, str(b.id), soll, haben, steuer=steuer, von="erika")
        s.commit()
    assert k.neu is not None
    assert (k.neu.soll_konto, k.neu.haben_konto, k.neu.steuer_schluessel) == (
        soll,
        haben,
        3,
    )


def test_eingangsrechnung_anderes_sachkonto_bleibt_korrigierbar(make_session):
    er, b = _eingang(9)
    anlegen(make_session, er, b)
    with make_session() as s:
        k = korrigiere(s, str(b.id), "4930", "70002", steuer=9, von="erika")
        s.commit()
    assert k.neu is not None and (k.neu.soll_konto, k.neu.haben_konto) == (
        "4930",
        "70002",
    )


def test_buchung_ohne_beleg_darf_die_seiten_tauschen(make_session):
    """Ohne Beleg gibt es keine Richtung aus einem Beleg — wie bisher."""
    b = buchung(
        status=BuchungStatus.GEPRUEFT, soll="4900", haben="70001", tag=date(2026, 10, 2)
    )
    anlegen(make_session, b)
    with make_session() as s:
        k = korrigiere(s, str(b.id), "70001", "4900", von="erika")
        s.commit()
    assert k.neu is not None and k.neu.soll_konto == "70001"


# --- CLI ----------------------------------------------------------------------------


@pytest.fixture
def cli_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    from accounti.db import init_db, session_factory

    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    yield url, fabrik
    engine.dispose()


@pytest.mark.parametrize("zusatz", [[], ["--grund", "doch Gutschrift"]])
def test_cli_korrigiere_seitentausch_exit_1(cli_db, zusatz):
    url, fabrik = cli_db
    ar, b = _ausgang()
    anlegen(fabrik, ar, b)
    r = runner.invoke(
        app,
        ["korrigiere", kurz(b.id), "--soll", "8400", "--haben", "10001", *zusatz,
         "--db", url],
        env={"COLUMNS": "300"},
    )  # fmt: skip
    text = " ".join(r.output.split())
    assert r.exit_code == 1, r.output
    assert "§ 14c" in text and BERICHTIGUNG in text
    with fabrik() as s:
        assert [(x.soll_konto, x.haben_konto) for x in lade_buchungen(s)] == [
            ("10001", "8400")
        ]


def test_cli_korrigiere_anderes_personenkonto(cli_db):
    url, fabrik = cli_db
    ar, b = _ausgang()
    anlegen(fabrik, ar, b)
    r = runner.invoke(
        app,
        ["korrigiere", kurz(b.id), "--soll", "10002", "--haben", "8400", "--db", url],
        env={"COLUMNS": "300"},
    )
    assert r.exit_code == 0, r.output
    with fabrik() as s:
        assert len(lade_buchungen(s)) == 3  # Original, Storno, Neubuchung


# --- Browser ------------------------------------------------------------------------


@pytest.fixture
def qw(tmp_path, monkeypatch):
    billige_hashes(monkeypatch)
    return queuewelt(tmp_path)


def _browser_ar(qw, status: BuchungStatus):  # noqa: ANN001, ANN202
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
    return qw.buchung(
        beleg_id=ar.id,
        soll="10001",
        haben="8400",
        betrag_netto=D("500.00"),
        steuer_schluessel=3,
        steuer_betrag=D("95.00"),
        status=status,
        confidence=1.0,
    )


def test_browser_buchungen_seitentausch_422(qw):
    """Das normale Formular (Steuer unverändert, ohne Grund) — kein von Hand gebauter
    POST; der Fachfehler verbraucht den Einmalcode nicht."""
    b = _browser_ar(qw, BuchungStatus.GEPRUEFT)
    client = qw.web.angemeldet("jan")
    code = qw.web.personen["jan"].codes[-1]
    seite = client.get(f"/buchungen/{b.id}").text
    daten = {
        "csrf": csrf(client),
        "stand": formularwert(seite, "stand"),
        "soll": "8400",
        "haben": "10001",
        "steuer": "",
        "grund": "",
        "einmalcode": code,
    }
    r = client.post(f"/buchungen/{b.id}/korrigieren", data=daten)
    assert r.status_code == 422, r.status_code
    assert "§ 14c" in r.text and "Gutschrift/Rechnungskorrektur" in r.text
    assert qw.sql("SELECT soll_konto, haben_konto FROM buchungssaetze") == [
        ("10001", "8400")
    ]
    # derselbe Code korrigiert danach das Personenkonto
    seite = client.get(f"/buchungen/{b.id}").text
    daten = {**daten, "stand": formularwert(seite, "stand"), "soll": "10002",
             "haben": "8400"}  # fmt: skip
    r = client.post(f"/buchungen/{b.id}/korrigieren", data=daten)
    assert r.status_code == 200, r.status_code


def test_queue_vorschlag_seitentausch_422(qw):
    b = _browser_ar(qw, BuchungStatus.ZUR_PRUEFUNG)
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    daten = {
        "csrf": csrf(client),
        "stand": formularwert(seite, "stand"),
        "soll": "8400",
        "haben": "10001",
        "steuer": "",
    }
    r = client.post(f"/pruefen/{b.id}/korrigieren", data=daten, follow_redirects=False)
    assert r.status_code == 422, r.status_code
    assert "§ 14c" in r.text
    assert qw.sql("SELECT soll_konto, haben_konto, status FROM buchungssaetze") == [
        ("10001", "8400", BuchungStatus.ZUR_PRUEFUNG.value)
    ]
