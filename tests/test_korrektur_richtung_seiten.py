"""Richtungssperre einer Belegbuchung: nur was die Richtung wirklich umdreht
(Gesamttest 10b-1, Runde 6: g5w NEU-1, NEU-2).

Runde 5 verglich ``kennziffern.sachseite`` vor und nach der Korrektur. Bestimmen die
Konten die Sachseite nicht (zwei Gegenkonten, z. B. „1800 an 1200“, oder zwei
Sachkonten ohne Erlös, „4120 an 1740“), setzt die Voranmeldung die Seite des
Schlüssels ein — ohne Schlüssel „Haben“. Die Sperre las darin einen Seitenwechsel:
Privatanteil, Spende, Wertpapier, Geldtransit, Lohn- und sonstige Verbindlichkeit
waren nicht mehr korrigierbar, ein Vorschlag hing fest (NEU-1). Umgekehrt ging ein
echter Tausch zweier Konten ohne Gegenkonto durch (NEU-2: „1576 an 1548“ getauscht,
Kz 66 kehrte still um).

Gesperrt ist jetzt, was die Seiten vertauscht:
(a) ein Konto wechselt die Seite (neues Soll = altes Haben oder umgekehrt),
(b) die Sachseite ist vorher und nachher aus den Konten bestimmt und eine andere,
(e) ein Erfolgskonto (Aufwand, Ertrag) steht vorher und nachher allein auf einer
    Seite, nachher auf der anderen — aus einem Aufwand würde ein Ertrag,
(d) eine Kennziffer der Voranmeldung kehrt ihr Vorzeichen um.
Eine nur per Rückfall bestimmte Sachseite sperrt nicht (c).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from accounti.abschluss.kontenrahmen import lade_kontenrahmen
from accounti.cli import app
from accounti.db.repository import lade_buchungen, speichere_abgleich
from accounti.elster.konfiguration import ElsterEinstellungen
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    AbgleichStatus,
    Belegabgleich,
    Belegart,
    Belegposition,
    Belegrichtung,
    BuchungStatus,
)
from accounti.pruefung.storno import (
    StornoError,
    freigeben,
    korrigiere,
    storniere,
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
    umsatz,
)

runner = CliRunner()
D = Decimal
G, P = BuchungStatus.GEPRUEFT, BuchungStatus.ZUR_PRUEFUNG
BERICHTIGUNG = "Berichtigung als eigener Beleg (Gutschrift/Rechnungskorrektur)"
SKR04 = Buchhaltung(kontenrahmen="SKR04", bank_konto="1800")


def _welt(
    soll: str,
    haben: str,
    schluessel: int | None = None,
    steuer: str | None = None,
    *,
    status: BuchungStatus = G,
    ausgang: bool = False,
):  # noqa: ANN202
    netto = "500.00"
    bel = beleg(
        belegart=Belegart.AUSGANGSRECHNUNG if ausgang else Belegart.EINGANGSRECHNUNG,
        richtung=Belegrichtung.AUSGANG if ausgang else Belegrichtung.EINGANG,
        nummer="B-1",
        tag=date(2026, 10, 1),
        netto=netto,
        steuer=steuer or "0.00",
        brutto=str(D(netto) + D(steuer or "0")),
        lieferant="Partner GmbH",
        positionen=[("Leistung", netto, "19" if steuer else "0", steuer or "0.00")],
    )
    b = buchung(
        status=status,
        soll=soll,
        haben=haben,
        netto=netto,
        steuer=steuer,
        schluessel=schluessel,
        tag=date(2026, 10, 1),
        beleg_id=bel.id,
    )
    return bel, b


# (id, Soll, Haben, Schlüssel, Steuer, neues Soll, neues Haben, Optionen)
ERLAUBT: list[tuple[str, str, str, int | None, str | None, str, str, dict]] = [
    ("privatanteil", "4360", "1200", None, None, "1800", "1200", {"grund": "privat"}),
    ("privat_zu_aufwand", "1800", "1200", None, None, "4360", "1200", {}),
    ("wertpapier_1348_zu_0525", "1348", "1200", None, None, "0525", "1200", {}),
    ("aufwand_zu_wertpapier_1348", "4930", "1200", None, None, "1348", "1200", {}),
    ("geldtransit_zu_aufwand", "1360", "1200", None, None, "4970", "1200", {}),
    ("kreditor_zu_lohnverbindlichkeit", "4120", "70001", None, None, "4120",
     "1740", {}),
    ("kreditor_zu_sonstiger_verbindlichkeit", "4360", "70001", None, None, "4360",
     "1700", {}),
    ("verbindlichkeit_privat", "4360", "1700", None, None, "1800", "1700", {}),
    ("privatspende", "4900", "1200", None, None, "1840", "1200", {}),
    ("automatikkonto_privat", "3400", "1200", None, None, "1800", "1200", {}),
    ("miete_zu_kaution", "4210", "70001", None, None, "1525", "70001", {}),
    ("vorsteuer_privat", "4930", "1200", 9, "95.00", "1800", "1200",
     {"ohne_steuer": True, "grund": "privat"}),
    ("vorsteuer_gutschrift_privat", "1200", "4930", 9, "95.00", "1200", "1800",
     {"ohne_steuer": True, "grund": "privat"}),
    ("anderes_aufwandskonto", "4930", "70001", 9, "95.00", "4940", "70002",
     {"steuer": 9}),
    ("ust_konto_im_soll", "10001", "8400", 3, "95.00", "1776", "8400", {"steuer": 3}),
]  # fmt: skip


@pytest.mark.parametrize("status", [G, P], ids=["freigegeben", "vorschlag"])
@pytest.mark.parametrize(
    ("soll", "haben", "schluessel", "steuer", "neu_soll", "neu_haben", "optionen"),
    [f[1:] for f in ERLAUBT],
    ids=[f[0] for f in ERLAUBT],
)
def test_korrektur_derselben_seite_erlaubt(
    make_session, status, soll, haben, schluessel, steuer, neu_soll, neu_haben, optionen
):
    """NEU-1: Aufwand, Privat oder Anlage bleibt im Soll, Bank bzw. Verbindlichkeit
    im Haben — nichts dreht sich."""
    ausgang = haben == "8400"
    bel, b = _welt(soll, haben, schluessel, steuer, status=status, ausgang=ausgang)
    anlegen(make_session, bel, b)
    with make_session() as s:
        k = korrigiere(s, str(b.id), neu_soll, neu_haben, von="erika", **optionen)
        s.commit()
    assert k.neu is not None
    assert (k.neu.soll_konto, k.neu.haben_konto) == (neu_soll, neu_haben)


@pytest.mark.parametrize("status", [G, P], ids=["freigegeben", "vorschlag"])
@pytest.mark.parametrize(
    ("soll", "haben", "neu_soll", "neu_haben"),
    [("6400", "1800", "2100", "1800"), ("6020", "70001", "6020", "3720")],
    ids=["privat_2100", "lohnverbindlichkeit_3720"],
)
def test_skr04_korrektur_derselben_seite_erlaubt(
    make_session, status, soll, haben, neu_soll, neu_haben
):
    bel, b = _welt(soll, haben, status=status)
    anlegen(make_session, bel, b)
    with make_session() as s:
        k = korrigiere(
            s,
            str(b.id),
            neu_soll,
            neu_haben,
            grund="x",
            von="erika",
            buchhaltung=SKR04,
            kontenrahmen=lade_kontenrahmen("SKR04"),
        )
        s.commit()
    assert k.neu is not None and k.neu.soll_konto == neu_soll


# (id, Soll, Haben, Schlüssel, Steuer, neues Soll, neues Haben, Optionen, in der
# Meldung)
GESPERRT: list[tuple[str, str, str, int | None, str | None, str, str, dict, list]] = [
    # (a) ein Konto wechselt die Seite
    ("vorsteuer_umbuchung_getauscht", "1576", "1548", None, None, "1548", "1576", {},
     ["1576 aus dem Soll ins Haben", "1548 aus dem Haben ins Soll"]),
    ("ig_lieferung_8125_gegen_8120", "10001", "8125", None, None, "8125", "8120", {},
     ["8125 aus dem Haben ins Soll"]),
    ("8125_gegen_bank", "10001", "8125", None, None, "8125", "1200", {},
     ["8125 aus dem Haben ins Soll"]),
    ("aufwand_bu9_ins_haben", "4930", "70001", 9, "95.00", "1700", "4930",
     {"steuer": 9}, ["4930 aus dem Soll ins Haben", "§ 17"]),
    ("aufwand_bu94_ins_haben", "4925", "70001", 94, "95.00", "1700", "4925",
     {"steuer": 94}, ["4925 aus dem Soll ins Haben"]),
    ("rechnung_getauscht", "10001", "8400", 3, "95.00", "8400", "10001", {},
     ["8400 aus dem Haben ins Soll", "10001 aus dem Soll ins Haben", "§ 14c"]),
    ("zahlung_getauscht", "1200", "10001", None, None, "10001", "1200", {},
     ["1200 aus dem Soll ins Haben", "10001 aus dem Haben ins Soll"]),
    ("aufwand_ohne_steuer_getauscht", "4900", "70001", None, None, "70001", "4900",
     {}, ["4900 aus dem Soll ins Haben"]),
    # (b) Sachseite vorher und nachher bestimmt, andere Seite
    ("andere_konten_sachseite_gedreht", "10001", "8400", 3, "95.00", "8401", "10002",
     {"steuer": 3}, ["Sachkonto 8400 steht im Haben", "Sachkonto 8401 im Soll"]),
    # (e) das Erfolgskonto wechselt die Seite, ohne dass ein Konto wandert
    ("erfolgskonto_ins_haben", "4930", "70001", 9, "95.00", "1700", "4931",
     {"steuer": 9}, ["Erfolgskonto 4930 steht im Soll", "Erfolgskonto 4931 im Haben"]),
    ("erfolgskonto_ohne_steuer_ins_haben", "4360", "1700", None, None, "1701", "4361",
     {}, ["Erfolgskonto 4360 steht im Soll", "Erfolgskonto 4361 im Haben"]),
]  # fmt: skip


@pytest.mark.parametrize("status", [G, P], ids=["freigegeben", "vorschlag"])
@pytest.mark.parametrize(
    ("soll", "haben", "schluessel", "steuer", "neu_soll", "neu_haben", "optionen",
     "erwartet"),
    [f[1:] for f in GESPERRT],
    ids=[f[0] for f in GESPERRT],
)  # fmt: skip
def test_vertauschte_seiten_gesperrt(
    make_session,
    status,
    soll,
    haben,
    schluessel,
    steuer,
    neu_soll,
    neu_haben,
    optionen,
    erwartet,
):
    """NEU-2 und g4w N1: die Meldung nennt die tatsächlich vertauschten Konten."""
    ausgang = "8400" in (soll, haben) or "8125" in (soll, haben)
    bel, b = _welt(soll, haben, schluessel, steuer, status=status, ausgang=ausgang)
    anlegen(make_session, bel, b)
    with make_session() as s:
        with pytest.raises(StornoError) as fehler:
            korrigiere(s, str(b.id), neu_soll, neu_haben, von="erika", **optionen)
        s.rollback()
        (geblieben,) = lade_buchungen(s)
    meldung = fehler.value.meldung
    for text in erwartet:
        assert text in meldung, meldung
    assert BERICHTIGUNG in meldung and fehler.value.feld == "soll"
    # keine Behauptung über das Bank- oder Personenkonto als „Sachkonto“
    assert "stellte das Sachkonto ins" not in meldung
    assert (geblieben.soll_konto, geblieben.haben_konto, geblieben.status) == (
        soll,
        haben,
        status,
    )


def test_kennziffer_kehrt_um_gesperrt(make_session):
    """(d): Kein Konto wandert, die Sachseite bestimmen die Konten nicht — aber die
    Voranmeldung kehrte Kz 62 um (eigene Funktionskonten der Konfiguration)."""
    elster = ElsterEinstellungen(kennziffern_konten={"1588": 62, "1589": 62})
    bel, b = _welt("1588", "1700")
    anlegen(make_session, bel, b)
    with make_session() as s, pytest.raises(StornoError) as fehler:
        korrigiere(s, str(b.id), "1701", "1589", von="erika", elster=elster)
    assert "Kz 62" in fehler.value.meldung and BERICHTIGUNG in fehler.value.meldung
    # ohne die Zuordnung hat die Buchung keine Kennziffer: erlaubt
    with make_session() as s:
        assert korrigiere(s, str(b.id), "1701", "1589", von="erika").neu is not None


def test_kennziffer_ohne_vorzeichenwechsel_erlaubt(make_session):
    elster = ElsterEinstellungen(kennziffern_konten={"1588": 62, "1589": 62})
    bel, b = _welt("1588", "1700")
    anlegen(make_session, bel, b)
    with make_session() as s:
        k = korrigiere(s, str(b.id), "1589", "1701", von="erika", elster=elster)
    assert k.neu is not None


def test_altfall_soll_gleich_haben_bleibt_korrigierbar(make_session):
    """Ein Vorschlag „4900 an 4900“ (Altfall): kein Konto „wandert“ — beide Seiten
    sind frei korrigierbar, sonst hinge er fest (Freigabe gesperrt)."""
    bel, b = _welt("4900", "4900", status=P)
    zweite = b.model_copy(update={"id": uuid4()})
    anlegen(make_session, bel, b, zweite)
    for x, neu in ((b, ("4900", "1200")), (zweite, ("1200", "4900"))):
        with make_session() as s:
            k = korrigiere(s, str(x.id), *neu, von="erika")
            s.commit()
        assert k.neu is not None and (k.neu.soll_konto, k.neu.haben_konto) == neu


@pytest.mark.parametrize(
    ("soll", "haben", "schluessel", "steuer", "neu_soll", "neu_haben", "optionen"),
    [f[1:8] for f in GESPERRT],
    ids=[f[0] for f in GESPERRT],
)
def test_gesperrter_vorschlag_haengt_nicht_fest(
    make_session, soll, haben, schluessel, steuer, neu_soll, neu_haben, optionen
):
    """Ist die Richtung gesperrt, nennt die Meldung beim Vorschlag den Weg, der geht:
    freigeben, dann mit Grund stornieren (nicht „stornieren“ allein — das lehnt ein
    Vorschlag ab)."""
    ausgang = "8400" in (soll, haben) or "8125" in (soll, haben)
    bel, b = _welt(soll, haben, schluessel, steuer, status=P, ausgang=ausgang)
    anlegen(make_session, bel, b)
    with make_session() as s:
        with pytest.raises(StornoError) as fehler:
            korrigiere(s, str(b.id), neu_soll, neu_haben, von="erika", **optionen)
        s.rollback()
        assert "freigeben" in fehler.value.meldung
        _, geaendert = freigeben(s, str(b.id), von="erika")
        k = storniere(s, str(b.id), grund="falscher Beleg", von="erika")
        s.commit()
    assert geaendert and k.storno is not None


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


def _cli(*args: str) -> tuple[int, str]:
    r = runner.invoke(app, list(args), env={"COLUMNS": "300"})
    return r.exit_code, " ".join(r.output.split())


def test_cli_privatanteil_mit_beleg(cli_db):
    url, fabrik = cli_db
    bel, b = _welt("4360", "1200")
    anlegen(fabrik, bel, b)
    rc, text = _cli(
        "korrigiere", kurz(b.id), "--soll", "1800", "--haben", "1200", "--grund",
        "private Versicherung", "--db", url,
    )  # fmt: skip
    assert rc == 0, text
    with fabrik() as s:
        assert len(lade_buchungen(s)) == 3  # Original, Storno, Neubuchung


def test_cli_tausch_nennt_die_konten(cli_db):
    url, fabrik = cli_db
    bel, b = _welt("10001", "8125", ausgang=True)
    anlegen(fabrik, bel, b)
    rc, text = _cli(
        "korrigiere", kurz(b.id), "--soll", "8125", "--haben", "8120", "--db", url
    )
    assert rc == 1, text
    assert "8125 aus dem Haben ins Soll" in text and BERICHTIGUNG in text
    assert f"accounti buchung storniere {kurz(b.id)}" in text


def test_cli_vorschlag_tausch_nennt_freigabe_und_storno(cli_db):
    url, fabrik = cli_db
    bel, b = _welt("1576", "1548", status=P)
    anlegen(fabrik, bel, b)
    rc, text = _cli(
        "korrigiere", kurz(b.id), "--soll", "1548", "--haben", "1576", "--db", url
    )
    assert rc == 1, text
    assert f"accounti bestaetige {kurz(b.id)}" in text
    assert f"accounti buchung storniere {kurz(b.id)}" in text


def test_cli_automatikkonto_vorschlag_haengt_nicht_fest(cli_db):
    """fest.py: Vorschlag „3400 an 1200“ ohne Schlüssel — die Freigabe sperrt das
    Automatikkonto, die Korrektur auf 1800 (privat) geht wieder."""
    url, fabrik = cli_db
    bel = beleg(
        netto="500.00",
        steuer="0.00",
        brutto="500.00",
        lieferant="Privatkauf GmbH",
        positionen=[("x", "500.00", "0", "0.00")],
        tag=date(2026, 10, 1),
    )
    tx = umsatz(betrag="-500.00", tag=date(2026, 10, 2), zweck="Privatkauf")
    b = buchung(
        tx, status=P, soll="3400", haben="1200", netto="500.00", steuer=None,
        schluessel=None, beleg_id=bel.id,
    )  # fmt: skip
    anlegen(fabrik, bel, tx, b)
    rc, text = _cli("bestaetige", kurz(b.id), "--db", url)
    assert rc == 1 and "Automatikkonto" in text, text
    rc, text = _cli(
        "korrigiere", kurz(b.id), "--soll", "1800", "--haben", "1200", "--grund",
        "privat", "--db", url,
    )  # fmt: skip
    assert rc == 0, text
    with fabrik() as s:
        (neu,) = lade_buchungen(s)
    assert (neu.soll_konto, neu.haben_konto, neu.beleg_id) == ("1800", "1200", bel.id)


def test_cli_bestaetigter_abgleich_korrektur_statt_schleife(cli_db):
    """schleife.py: Umsatz, Beleg ohne Vorsteuer und bestätigter Belegabgleich —
    classify bucht „4900 an 1200“ mit Beleg; die Korrektur auf 1840 (Privatspende)
    geht, statt dass nur Freigabe und Storno blieben (und classify neu buchte)."""
    url, fabrik = cli_db
    bel = beleg(
        nummer="SP-2026-17",
        netto="500.00",
        steuer="0.00",
        brutto="500.00",
        lieferant="Kinderhilfe e.V.",
        positionen=[("Spende", "500.00", "0", "0.00")],
        tag=date(2026, 10, 1),
    )
    tx = umsatz(
        betrag="-500.00",
        tag=date(2026, 10, 2),
        zweck="SPENDE SP-2026-17",
        name="Kinderhilfe e.V.",
    )
    anlegen(fabrik, bel, tx)
    with fabrik() as s:
        speichere_abgleich(
            s,
            Belegabgleich(
                transaktion_id=tx.id,
                beleg_id=bel.id,
                stufe="referenz",
                status=AbgleichStatus.BESTAETIGT,
                confidence=1.0,
                begruendung="Test",
            ),
        )
        s.commit()
    rc, text = _cli("classify", "--no-llm", "--db", url)
    assert rc == 0, text
    with fabrik() as s:
        (b,) = lade_buchungen(s)
    assert (b.soll_konto, b.haben_konto, b.beleg_id) == ("4900", "1200", bel.id)
    rc, text = _cli(
        "korrigiere", kurz(b.id), "--soll", "1840", "--haben", "1200", "--grund",
        "Privatspende", "--db", url,
    )  # fmt: skip
    assert rc == 0, text
    rc, text = _cli("classify", "--no-llm", "--db", url)
    with fabrik() as s:
        alle = lade_buchungen(s)
    assert [(x.soll_konto, x.haben_konto) for x in alle] == [("1840", "1200")]


# --- Browser ------------------------------------------------------------------------


@pytest.fixture
def qw(tmp_path, monkeypatch):
    billige_hashes(monkeypatch)
    return queuewelt(tmp_path)


def _versicherung(qw, status: BuchungStatus, soll: str = "4360", haben: str = "1200"):  # noqa: ANN001, ANN202
    bid = uuid4()
    bel = qw.beleg(
        pdf("Beitragsrechnung POL-4711 Versicherung AG 500,00"),
        id=bid,
        belegnummer="POL-4711",
        belegdatum=date(2026, 10, 1),
        lieferant_name="Versicherung AG",
        netto=D("500.00"),
        steuer=D("0.00"),
        brutto=D("500.00"),
        positionen=[
            Belegposition(
                beleg_id=bid, bezeichnung="Beitrag", netto=D("500.00"),
                steuersatz=D("0"),
            )
        ],
    )  # fmt: skip
    return qw.buchung(
        beleg_id=bel.id,
        soll=soll,
        haben=haben,
        betrag_netto=D("500.00"),
        steuer_schluessel=None,
        steuer_betrag=None,
        status=status,
        confidence=0.5,
    )


def _queue_korrektur(qw, b, soll: str, haben: str) -> Any:  # noqa: ANN001
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    daten = {
        "csrf": csrf(client),
        "stand": formularwert(seite, "stand"),
        "soll": soll,
        "haben": haben,
        "steuer": "",
        "grund": "private Versicherung",
    }
    return client.post(
        f"/pruefen/{b.id}/korrigieren", data=daten, follow_redirects=False
    )


def test_queue_vorschlag_privatanteil(qw):
    b = _versicherung(qw, P)
    r = _queue_korrektur(qw, b, "1800", "1200")
    assert r.status_code in (200, 303), r.text[:500]
    assert qw.sql("SELECT soll_konto, haben_konto FROM buchungssaetze") == [
        ("1800", "1200")
    ]


def test_queue_vorschlag_tausch_422_mit_konten(qw):
    b = _versicherung(qw, P, soll="1576", haben="1548")
    r = _queue_korrektur(qw, b, "1548", "1576")
    assert r.status_code == 422, r.status_code
    assert "1576 aus dem Soll ins Haben" in r.text and "freigeben" in r.text
    assert qw.sql("SELECT soll_konto, haben_konto, status FROM buchungssaetze") == [
        ("1576", "1548", P.value)
    ]


def test_buchungen_freigegeben_privatanteil(qw):
    b = _versicherung(qw, G)
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/buchungen/{b.id}").text
    daten = {
        "csrf": csrf(client),
        "stand": formularwert(seite, "stand"),
        "soll": "1800",
        "haben": "1200",
        "steuer": "",
        "grund": "private Versicherung",
        "einmalcode": qw.web.personen["jan"].codes[-1],
    }
    r = client.post(f"/buchungen/{b.id}/korrigieren", data=daten)
    assert r.status_code == 200, r.status_code
    assert sorted(qw.sql("SELECT soll_konto, haben_konto FROM buchungssaetze")) == [
        ("1200", "4360"),
        ("1800", "1200"),
        ("4360", "1200"),
    ]
