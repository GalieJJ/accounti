"""§ 14c Abs. 1 UStG bei der Korrektur einer Belegbuchung (Gesamttest 10b-1, Runde 4:
g3w-merge M1, g3w-web).

Weist eine Rechnung Umsatzsteuer aus (Schlüssel 3 bzw. 2), wird sie geschuldet, bis die
Rechnung berichtigt ist; die Berichtigung wirkt erst in dem Zeitraum, in dem sie
erfolgt (§ 14c Abs. 1 Satz 2 i. V. m. § 17 Abs. 1 UStG). main (Paket C) sperrte deshalb
jede Schlüsseländerung einer solchen Belegbuchung. Nach dem Zusammenführen sperrte
``storno._steuer`` nur noch „ohne Steuer“: ``korrigiere --steuer 94 --grund …`` (auch
19/91/18, bei einem Beleg ohne Positionssatz jeder Schlüssel) nahm die 95 € still aus
der Voranmeldung — in CLI, Browser und REST gleich, weil alle Wege dieselbe
Fachfunktion rufen.

Die Ausnahme von Paket C bleibt: Eine Belegbuchung, deren Beleg keine Umsatzsteuer
ausweist (Eingangsrechnung mit Vorsteuer oder ohne Steuer), nimmt § 13b bzw. ig. Erwerb
(94/91/19/18) mit Grund an — diese Steuer steht nie auf dem Beleg (§ 14a Abs. 5 UStG).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db.repository import lade_buchungen
from accounti.models import Belegart, Belegrichtung, BuchungStatus
from accounti.pruefung.storno import (
    SELBST_BERECHNET,
    StornoError,
    _steuer,
    korrigiere,
)
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
# ausgewiesene Umsatzsteuer: (Schlüssel, Steuer auf 500 €, Satz)
AUSGEWIESEN = [(3, "95.00", "19"), (2, "35.00", "7")]


def _ausgangsbeleg(mit_satz: bool, steuer: str = "95.00", satz: str = "19"):  # noqa: ANN202
    return beleg(
        belegart=Belegart.AUSGANGSRECHNUNG,
        richtung=Belegrichtung.AUSGANG,
        nummer="AR-1",
        tag=date(2026, 10, 1),
        netto="500.00",
        steuer=steuer,
        brutto=str(D("500.00") + D(steuer)),
        lieferant="Kunde K GmbH",
        positionen=[("Ware", "500.00", satz if mit_satz else None, None)],
    )


def _belegbuchung(beleg_id, schluessel: int = 3, steuer: str = "95.00"):  # noqa: ANN001, ANN202
    return buchung(
        status=BuchungStatus.GEPRUEFT,
        soll="10001",
        haben="8400" if schluessel == 3 else "8300",
        netto="500.00",
        steuer=steuer,
        schluessel=schluessel,
        tag=date(2026, 10, 1),
        beleg_id=beleg_id,
    )


# --- Fachfunktion -------------------------------------------------------------------


@pytest.mark.parametrize(("alt", "steuer", "satz"), AUSGEWIESEN)
@pytest.mark.parametrize("mit_satz", [True, False], ids=["mit_satz", "ohne_satz"])
@pytest.mark.parametrize("neu", [94, 91, 19, 18, 9, 8, "anders"])
@pytest.mark.parametrize("grund", [None, "doch § 13b"], ids=["ohne_grund", "mit_grund"])
def test_steuer_lehnt_jede_aenderung_ausgewiesener_ust_ab(
    alt, steuer, satz, mit_satz, neu, grund
):
    """Direkter Aufruf von ``_steuer`` — auch mit Grund (der alte Test
    ``test_steuer_optionen_wie_korrigiere`` prüfte nur ohne Grund, dort scheiterte 94
    schon an der Grund-Pflicht)."""
    schluessel = (5 - alt) if neu == "anders" else neu  # 3 → 2, 2 → 3
    b = _belegbuchung(uuid4(), alt, steuer)
    with pytest.raises(StornoError) as fehler:
        _steuer(b, schluessel, False, grund, beleg_mit_satz=mit_satz)
    assert fehler.value.feld == "steuer"
    if schluessel in SELBST_BERECHNET or not mit_satz:
        # an der Beleg-Ausnahme von Paket C vorbei: hier greift § 14c
        assert "§ 14c" in str(fehler.value) and "§ 14c" in fehler.value.meldung


@pytest.mark.parametrize(("alt", "steuer", "satz"), AUSGEWIESEN)
@pytest.mark.parametrize("mit_satz", [True, False], ids=["mit_satz", "ohne_satz"])
def test_ohne_steuer_bleibt_gesperrt(alt, steuer, satz, mit_satz):
    b = _belegbuchung(uuid4(), alt, steuer)
    with pytest.raises(StornoError, match="§ 14c"):
        _steuer(b, None, True, "doch ig. Lieferung", beleg_mit_satz=mit_satz)


@pytest.mark.parametrize("mit_satz", [True, False], ids=["mit_satz", "ohne_satz"])
@pytest.mark.parametrize("neu", [94, 19, 2, 9])
def test_korrigiere_mit_beleg_aus_der_datenbank(make_session, mit_satz, neu):
    """Mit dem Beleg in der Datenbank (``_beleg_mit_satz`` liest seine Positionen):
    nichts wird gebucht, die Buchung bleibt freigegeben mit Schlüssel 3."""
    ar = _ausgangsbeleg(mit_satz)
    b = _belegbuchung(ar.id)
    anlegen(make_session, ar, b)
    with make_session() as s:
        with pytest.raises(StornoError) as fehler:
            korrigiere(
                s, str(b.id), "10001", "2700", steuer=neu, grund="doch § 13b",
                von="erika",
            )  # fmt: skip
        s.rollback()
        if neu in SELBST_BERECHNET or not mit_satz:
            assert "§ 14c" in str(fehler.value)
        (geblieben,) = lade_buchungen(s)
    assert (geblieben.steuer_schluessel, geblieben.storniert_durch) == (3, None)


# --- Paket C: Belege ohne ausgewiesene Umsatzsteuer --------------------------------


@pytest.mark.parametrize("neu", sorted(SELBST_BERECHNET))
@pytest.mark.parametrize(
    ("alt", "steuer", "positionen"),
    [
        (9, "19.00", None),  # Eingangsrechnung mit Vorsteuer (Satz auf dem Beleg)
        (None, None, [("Leistung", "100.00", None, None)]),  # ohne Steuer, ohne Satz
        (None, None, [("Leistung", "100.00", "0", "0.00")]),  # 0 % auf dem Beleg
    ],
    ids=["vorsteuer", "ohne_steuer_ohne_satz", "null_prozent"],
)
def test_eingangsbeleg_nimmt_13b_und_ig_erwerb_mit_grund(
    make_session, neu, alt, steuer, positionen
):
    eingang = beleg(
        netto="100.00",
        steuer=steuer or "0.00",
        brutto="119.00" if steuer else "100.00",
        positionen=positionen,
    )
    b = buchung(
        status=BuchungStatus.GEPRUEFT,
        soll="4900",
        haben="70001",
        steuer=steuer,
        schluessel=alt,
        beleg_id=eingang.id,
    )
    anlegen(make_session, eingang, b)
    with make_session() as s:
        k = korrigiere(
            s, str(b.id), "4900", "70001", steuer=neu, grund="Reverse Charge",
            von="erika",
        )  # fmt: skip
        s.commit()
    assert k.neu is not None and k.neu.steuer_schluessel == neu


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


@pytest.mark.parametrize("mit_satz", [True, False], ids=["mit_satz", "ohne_satz"])
@pytest.mark.parametrize(
    "zusatz", [[], ["--grund", "doch § 13b"]], ids=["ohne_grund", "mit_grund"]
)
@pytest.mark.parametrize("neu", ["94", "19"])
def test_cli_korrigiere_steuer_94_auf_ausgangsrechnung_exit_1(
    cli_db, mit_satz, zusatz, neu
):
    url, fabrik = cli_db
    ar = _ausgangsbeleg(mit_satz)
    b = _belegbuchung(ar.id)
    anlegen(fabrik, ar, b)
    r = runner.invoke(
        app,
        ["korrigiere", kurz(b.id), "--soll", "10001", "--haben", "2700",
         "--steuer", neu, *zusatz, "--db", url],
        env={"COLUMNS": "250"},
    )  # fmt: skip
    assert r.exit_code == 1 and "§ 14c" in r.output, r.output
    with fabrik() as s:
        assert [x.steuer_schluessel for x in lade_buchungen(s)] == [3]


# --- Browser ------------------------------------------------------------------------


@pytest.fixture
def qw(tmp_path, monkeypatch):
    billige_hashes(monkeypatch)
    return queuewelt(tmp_path)


@pytest.mark.parametrize("mit_satz", [True, False], ids=["mit_satz", "ohne_satz"])
@pytest.mark.parametrize("neu", ["94", "19", "2"])
def test_browser_korrektur_steuer_auf_ausgangsrechnung_422(qw, mit_satz, neu):
    """g3w-web: Das Formular bietet nur den bisherigen Schlüssel an, ein von Hand
    gebauter POST mit Grund und Einmalcode buchte trotzdem um."""
    from accounti.models import Belegposition

    bid = uuid4()
    satz = D("19") if mit_satz else None
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
                beleg_id=bid, bezeichnung="Ware", netto=D("500.00"), steuersatz=satz
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
    code = qw.web.personen["jan"].codes[-1]
    seite = client.get(f"/buchungen/{b.id}").text
    daten = {
        "csrf": csrf(client),
        "stand": formularwert(seite, "stand"),
        "soll": "10001",
        "haben": "2700",
        "steuer": neu,
        "grund": "doch § 13b",
        "einmalcode": code,
    }
    r = client.post(f"/buchungen/{b.id}/korrigieren", data=daten)
    assert r.status_code == 422, r.status_code
    if neu in ("94", "19") or not mit_satz:
        assert "§ 14c" in r.text
    assert qw.sql("SELECT steuer_schluessel FROM buchungssaetze") == [(3,)]
    # der Fachfehler verbraucht den Code nicht: dieselbe Buchung lässt sich mit ihm
    # stornieren
    r = client.post(f"/buchungen/{b.id}/stornieren", data={**daten, "grund": "doppelt"})
    assert r.status_code == 200, r.status_code
