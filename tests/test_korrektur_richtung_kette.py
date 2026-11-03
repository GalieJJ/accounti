"""Richtungssperre über die ganze Korrekturkette, neu entstehende Kennziffern und
Fehlschlüssel auf Eingangsbelegen (Gesamttest 10b-1, Runde 7: g6w N1, N2, N5).

N1: Die Regeln (a), (b) und (e) verglichen nur mit der unmittelbar vorigen Buchung.
Ein Zwischenschritt mit unbestimmter Sachseite („10001 an 1590“, zwei Gegenkonten;
„4931 an 4932“, zwei Sachkonten ohne Erlös) löschte jedes Gedächtnis der Richtung —
die nächste Korrektur durfte die Seiten tauschen („10001 an 8125 → 10001 an 1590 →
8125 an 1200“ buchte Kz 41 −500). Jetzt gilt jeder Stand der Kette (Neubuchung →
Original über ``buchungskorrekturen``, direkt korrigierte Vorschläge über das
Journal), und bestimmt keiner die Seite, die des Belegs.

N2: (d) sah nur Kennziffern, die vorher und nachher gebucht werden — „10001 an 8125 →
8120 an 8125“ buchte Kz 43 −500.

N5: „4930 an 1200, Schlüssel 3“ auf einer Eingangsrechnung hing fest: keine Freigabe,
keine Korrektur auf Schlüssel 9, kein „ohne Steuer“, kein Storno.
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
from accounti.db.repository import lade_buchungen
from accounti.elster.konfiguration import ElsterEinstellungen
from accounti.konfiguration import Buchhaltung
from accounti.models import Belegart, Belegposition, Belegrichtung, BuchungStatus
from accounti.pruefung.storno import (
    StornoError,
    korrigiere,
    steuer_optionen,
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
KETTE = "die Richtung gilt für die ganze Korrekturkette"


def _welt(
    soll: str,
    haben: str,
    schluessel: int | None = None,
    steuer: str | None = None,
    *,
    status: BuchungStatus = G,
    ausgang: bool = False,
    satz: str | None = None,
    netto: str = "500.00",
):  # noqa: ANN202
    satz = satz if satz is not None else ("19" if steuer else "0")
    bel = beleg(
        belegart=Belegart.AUSGANGSRECHNUNG if ausgang else Belegart.EINGANGSRECHNUNG,
        richtung=Belegrichtung.AUSGANG if ausgang else Belegrichtung.EINGANG,
        nummer="B-1",
        tag=date(2026, 10, 1),
        netto=netto,
        steuer=steuer or "0.00",
        brutto=str(D(netto) + D(steuer or "0")),
        lieferant="Partner GmbH",
        positionen=[("Leistung", netto, satz, steuer or "0.00")],
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


def _wirksam(make_session, beleg_id) -> Any:  # noqa: ANN001
    with make_session() as s:
        (x,) = [
            b
            for b in lade_buchungen(s)
            if b.beleg_id == beleg_id
            and b.storno_von is None
            and b.storniert_durch is None
        ]
    return x


def _schritt(make_session, beleg_id, soll: str, haben: str, **optionen: Any) -> Any:  # noqa: ANN001
    akt = _wirksam(make_session, beleg_id)
    with make_session() as s:
        k = korrigiere(
            s, str(akt.id), soll, haben, von="erika", grund="Test", **optionen
        )
        s.commit()
    return k


# (id, SKR04?, Ausgang?, Status, Start-Soll, Start-Haben, Zwischenschritte, letzter
# Schritt, Optionen) — die Fälle aus kette.py (g6w-richtung)
UMGEHUNG: list[tuple[str, bool, bool, BuchungStatus, str, str, list, tuple, dict]] = [
    ("U01_igl_ueber_1590", False, True, G, "10001", "8125",
     [("10001", "1590")], ("8125", "1200"), {}),
    ("U01v_igl_vorschlag", False, True, P, "10001", "8125",
     [("10001", "1590")], ("8125", "1200"), {}),
    ("U02_igl_ueber_aufwand", False, True, G, "10001", "8125",
     [("4931", "4932")], ("8125", "10001"), {}),
    ("U03_aufwand_wird_ertrag", False, False, G, "4930", "70001",
     [("4931", "4932")], ("70001", "4930"), {}),
    ("U06_bu9_ohne_dann_94", False, False, G, "4930", "70001",
     [("4931", "4932")], ("70001", "4925"), {"steuer": 94}),
    ("U07b_vst_folgejahr", False, False, G, "1576", "1548",
     [("1590", "1360")], ("1548", "1576"), {}),
    ("U08_ezt_62", False, False, G, "1588", "70001",
     [("1590", "70002")], ("70001", "1588"), {"elster": True}),
    ("U09_ueber_privat", False, True, G, "10001", "8125",
     [("1800", "1890")], ("8125", "10001"), {}),
    ("U14_skr04_igl", True, True, G, "10001", "4125",
     [("10001", "70001")], ("4125", "10002"), {}),
    ("U15_ausfuhr_vorschlag", False, True, P, "10001", "8120",
     [("10001", "70001")], ("8120", "10002"), {}),
    ("U15b_ausfuhr_dritter_schritt", False, True, P, "10001", "8120",
     [("10001", "70001"), ("10002", "70001")], ("8120", "10001"), {}),
]  # fmt: skip


@pytest.mark.parametrize(
    ("skr04", "ausgang", "status", "soll", "haben", "zwischen", "letzter", "optionen"),
    [f[1:] for f in UMGEHUNG],
    ids=[f[0] for f in UMGEHUNG],
)
def test_zwei_korrekturen_tauschen_die_seiten_nicht(
    make_session, skr04, ausgang, status, soll, haben, zwischen, letzter, optionen
):
    """N1: Nach einem Zwischenschritt mit unbestimmter Seite tauscht die nächste
    Korrektur die Seiten nicht — die Meldung nennt den früheren Stand."""
    bel, b = _welt(soll, haben, status=status, ausgang=ausgang)
    anlegen(make_session, bel, b)
    umgebung: dict[str, Any] = {}
    if skr04:
        umgebung = {"buchhaltung": SKR04, "kontenrahmen": lade_kontenrahmen("SKR04")}
    if optionen.pop("elster", False):
        umgebung["elster"] = ElsterEinstellungen(kennziffern_konten={"1588": 62})
    for s_, h_ in zwischen:
        _schritt(make_session, bel.id, s_, h_, **umgebung)
    vorher = _wirksam(make_session, bel.id)
    with pytest.raises(StornoError) as fehler:
        _schritt(make_session, bel.id, *letzter, **umgebung, **optionen)
    meldung = fehler.value.meldung
    assert BERICHTIGUNG in meldung, meldung
    assert KETTE in meldung, meldung
    nachher = _wirksam(make_session, bel.id)
    assert (nachher.id, nachher.soll_konto, nachher.haben_konto) == (
        vorher.id,
        vorher.soll_konto,
        vorher.haben_konto,
    )


def test_cli_zwei_schritte_ig_lieferung(tmp_path, monkeypatch):
    """U01 über die CLI: S1 geht, S2 endet mit rc 1 und nennt den früheren Stand."""
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    from accounti.db import init_db, session_factory

    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    bel, b = _welt("10001", "8125", ausgang=True)
    anlegen(fabrik, bel, b)

    def cli(*args: str) -> tuple[int, str]:
        r = runner.invoke(app, [*args, "--db", url], env={"COLUMNS": "300"})
        return r.exit_code, " ".join(r.output.split())

    rc, text = cli(
        "korrigiere", kurz(b.id), "--soll", "10001", "--haben", "1590", "--grund", "x"
    )
    assert rc == 0, text
    neu = _wirksam(fabrik, bel.id)
    rc, text = cli(
        "korrigiere", kurz(neu.id), "--soll", "8125", "--haben", "1200", "--grund", "x"
    )
    assert rc == 1, text
    assert "8125 aus dem Haben ins Soll" in text and "„10001 an 8125“" in text
    assert f"accounti buchung storniere {kurz(neu.id)}" in text
    engine.dispose()


# (id, Ausgang?, Start, Schritte) — legitime Ketten derselben Seite
LEGITIM: list[tuple[str, bool, tuple, list]] = [
    ("aufwand_konto_dann_anlage", False, ("4930", "70001", 9, "95.00"),
     [("4940", "70002", {"steuer": 9}), ("0420", "70002", {"steuer": 9})]),
    ("privat_und_zurueck", False, ("4360", "1200", None, None),
     [("1800", "1200", {}), ("4360", "1200", {})]),
    ("debitor_dann_bank", True, ("10001", "8400", 3, "95.00"),
     [("10002", "8400", {}), ("1200", "8400", {})]),
    ("ueber_unbestimmt_zurueck", True, ("10001", "8125", None, None),
     [("10001", "1590", {}), ("10002", "8125", {})]),
    ("aufwand_ueber_zwei_sachkonten", False, ("4930", "70001", None, None),
     [("4931", "4932", {}), ("4930", "70002", {})]),
    ("igl_8125_8120_8125", True, ("10001", "8125", None, None),
     [("10001", "8120", {}), ("10001", "8125", {})]),
    ("lieferantengutschrift", False, ("70001", "4930", 9, "95.00"),
     [("70002", "4940", {"steuer": 9}), ("1200", "4940", {"steuer": 9})]),
]  # fmt: skip


@pytest.mark.parametrize("status", [G, P], ids=["freigegeben", "vorschlag"])
@pytest.mark.parametrize(
    ("ausgang", "start", "schritte"),
    [f[1:] for f in LEGITIM],
    ids=[f[0] for f in LEGITIM],
)
def test_ketten_derselben_seite_bleiben_erlaubt(
    make_session, status, ausgang, start, schritte
):
    soll, haben, schluessel, steuer = start
    bel, b = _welt(soll, haben, schluessel, steuer, status=status, ausgang=ausgang)
    anlegen(make_session, bel, b)
    for s_, h_, optionen in schritte:
        k = _schritt(make_session, bel.id, s_, h_, **optionen)
        assert k.neu is not None
        assert (k.neu.soll_konto, k.neu.haben_konto) == (s_, h_)


def test_ohne_bestimmte_seite_gilt_die_des_belegs(make_session):
    """Bestimmt kein Stand die Seite („4931 an 4932“ als erster Vorschlag), misst die
    Korrektur an der Rechnung: Aufwand der Eingangsrechnung im Soll."""
    bel, b = _welt("4931", "4932", status=P)
    anlegen(make_session, bel, b)
    with make_session() as s, pytest.raises(StornoError) as fehler:
        korrigiere(s, str(b.id), "70001", "4930", von="erika")
    assert "die Eingangsrechnung bucht ihr Erfolgskonto" in fehler.value.meldung
    assert "Erfolgskonto 4930 im Haben" in fehler.value.meldung
    with make_session() as s:
        k = korrigiere(s, str(b.id), "4930", "70001", von="erika")
        s.commit()
    assert k.neu is not None and k.neu.soll_konto == "4930"


def test_beleg_mit_negativem_betrag_dreht_die_seite(make_session):
    """Eine Gutschrift (negativer Beleg) bucht ihren Aufwand im Haben."""
    bel, b = _welt("4931", "4932", status=P, netto="-500.00")
    anlegen(make_session, bel, b)
    with make_session() as s:
        k = korrigiere(s, str(b.id), "70001", "4930", von="erika")
        s.commit()
    assert k.neu is not None and k.neu.haben_konto == "4930"


# --- N2: neu entstehende Kennziffer mit dem Vorzeichen einer Gutschrift -------------


def test_neue_kennziffer_negativ_gesperrt(make_session):
    """U12: „10001 an 8125 → 8120 an 8125“ buchte Kz 41 +500 und Kz 43 −500."""
    bel, b = _welt("10001", "8125", ausgang=True)
    anlegen(make_session, bel, b)
    with make_session() as s, pytest.raises(StornoError) as fehler:
        korrigiere(s, str(b.id), "8120", "8125", von="erika", grund="x")
    meldung = fehler.value.meldung
    assert "Kz 43 mit -500,00 €" in meldung and "Gutschrift" in meldung
    assert BERICHTIGUNG in meldung


@pytest.mark.parametrize("status", [G, P], ids=["freigegeben", "vorschlag"])
@pytest.mark.parametrize(
    ("ausgang", "start", "neu", "optionen", "satz"),
    [
        # 8400 → 8300 (Satz laut Beleg 7 %, Schlüssel 2): Kz 81 → 86
        (True, ("10001", "8400", 3, "35.00"), ("10001", "8300"), {"steuer": 2}, "7"),
        # 8120 → 8125 (steuerfrei → ig. Lieferung): Kz 43 → 41
        (True, ("10001", "8120", None, None), ("10001", "8125"), {}, "0"),
        # Vorsteuer 19 % → 7 % laut Beleg: Kz 66 bleibt positiv
        (False, ("4930", "70001", 9, "35.00"), ("4930", "70001"), {"steuer": 8}, "7"),
        # § 13b: Kz 66 → 84/85/67, alle positiv
        (False, ("4930", "70001", 9, "95.00"), ("4925", "70001"), {"steuer": 94}, "19"),
    ],
    ids=["8400_8300", "8120_8125", "vorsteuer_19_7", "paragraf_13b"],
)
def test_neue_kennziffer_positiv_erlaubt(
    make_session, status, ausgang, start, neu, optionen, satz
):
    soll, haben, schluessel, steuer = start
    bel, b = _welt(
        soll, haben, schluessel, steuer, status=status, ausgang=ausgang, satz=satz
    )
    anlegen(make_session, bel, b)
    with make_session() as s:
        k = korrigiere(s, str(b.id), *neu, von="erika", grund="x", **optionen)
        s.commit()
    assert k.neu is not None and (k.neu.soll_konto, k.neu.haben_konto) == neu


def test_neue_negative_kennziffer_bei_gutschrift_erlaubt(make_session):
    """Bucht schon ein Stand eine Kennziffer negativ (Gutschrift), darf eine andere
    negative entstehen: „8400 an 10001, Schlüssel 3“ (Kz 81 −) → 8300, Schlüssel 2."""
    bel, b = _welt("8400", "10001", 3, "35.00", ausgang=True, satz="7")
    anlegen(make_session, bel, b)
    with make_session() as s:
        k = korrigiere(s, str(b.id), "8300", "10001", von="erika", steuer=2)
        s.commit()
    assert k.neu is not None and k.neu.steuer_schluessel == 2


# --- N5: Fehlschlüssel auf dem Eingangsbeleg -----------------------------------------


def test_ust_schluessel_auf_eingangsbeleg_ist_fehlschluessel(make_session):
    """V1 (fest6.py): Korrektur auf den Vorsteuerschlüssel des Belegs geht, auch ohne
    Grund; § 14c gilt nicht (kein Ausgangsbeleg)."""
    bel, b = _welt("4930", "1200", 3, "95.00", status=P)
    anlegen(make_session, bel, b)
    optionen = steuer_optionen(b, bel)
    assert optionen.laut_beleg == 9 and 9 in optionen.schluessel
    assert optionen.ohne_steuer and "Fehlschlüssel" in (optionen.hinweis or "")
    with make_session() as s:
        k = korrigiere(s, str(b.id), "4930", "1200", von="erika", steuer=9)
        s.commit()
    assert k.neu is not None
    assert (k.neu.steuer_schluessel, k.neu.betrag_netto, k.neu.steuer_betrag) == (
        9,
        D("500.00"),
        D("95.00"),
    )


def test_ust_schluessel_auf_eingangsbeleg_ohne_steuer_mit_grund(make_session):
    bel, b = _welt("4930", "1200", 3, "95.00", status=P)
    anlegen(make_session, bel, b)
    with make_session() as s:
        k = korrigiere(
            s, str(b.id), "4930", "1200", von="erika", ohne_steuer=True, grund="x"
        )
        s.commit()
    assert k.neu is not None and k.neu.steuer_schluessel is None


@pytest.mark.parametrize(
    ("ausgang", "satz", "start", "falsch"),
    [
        (False, "19", 3, 8),  # Eingang 19 %: 8 (7 %) widerspricht dem Beleg
        (False, "19", 9, 8),
        (True, "19", 3, 2),  # Ausgang 19 %: 2 (7 %) widerspricht, § 14c
        (True, "19", 3, 9),
    ],
    ids=["eingang_3_8", "eingang_9_8", "ausgang_3_2", "ausgang_3_9"],
)
def test_schluessel_gegen_den_beleg_bleibt_gesperrt(
    make_session, ausgang, satz, start, falsch
):
    soll, haben = ("10001", "8400") if ausgang else ("4930", "1200")
    bel, b = _welt(soll, haben, start, "95.00", status=P, ausgang=ausgang, satz=satz)
    anlegen(make_session, bel, b)
    with make_session() as s, pytest.raises(StornoError) as fehler:
        korrigiere(s, str(b.id), soll, haben, von="erika", steuer=falsch, grund="x")
    assert fehler.value.feld == "steuer"


def test_ausgangsbeleg_behaelt_paragraf_14c(make_session):
    bel, b = _welt("10001", "8400", 3, "95.00", status=P, ausgang=True)
    anlegen(make_session, bel, b)
    optionen = steuer_optionen(b, bel)
    assert not optionen.ohne_steuer and "§ 14c" in (optionen.hinweis or "")
    with make_session() as s, pytest.raises(StornoError) as fehler:
        korrigiere(
            s, str(b.id), "10001", "8400", von="erika", ohne_steuer=True, grund="x"
        )
    assert "§ 14c" in fehler.value.meldung


def test_ausgangsbeleg_7_prozent_schluessel_laut_beleg(make_session):
    """Schlüssel 3 auf einer Rechnung, die 7 % ausweist: der Schlüssel des Belegs (2)
    widerspricht § 14c nicht — die ausgewiesene Steuer ist die zu 7 %."""
    bel, b = _welt("10001", "8300", 3, "35.00", status=P, ausgang=True, satz="7")
    anlegen(make_session, bel, b)
    with make_session() as s:
        k = korrigiere(s, str(b.id), "10001", "8300", von="erika", steuer=2)
        s.commit()
    assert k.neu is not None and k.neu.steuer_schluessel == 2


# Typische Fehlvorschläge: mindestens ein Weg führt zur richtigen Buchung (CLI).
# (id, Ausgang?, Satz, Vorschlag (Soll, Haben, Schlüssel, Steuer), Ziel (Soll, Haben,
# Schlüssel), Weg: "korrektur" oder "storno" (freigeben und mit Grund stornieren))
FEHLVORSCHLAEGE: list[tuple[str, bool, str, tuple, tuple, str]] = [
    ("schluessel_3_statt_9", False, "19", ("4930", "1200", 3, "95.00"),
     ("4930", "1200", 9), "korrektur"),
    ("schluessel_2_statt_8", False, "7", ("4930", "1200", 2, "35.00"),
     ("4930", "1200", 8), "korrektur"),
    ("schluessel_9_statt_3", True, "19", ("1200", "8400", 9, "95.00"),
     ("1200", "8400", 3), "korrektur"),
    ("automatikkonto_ohne_schluessel", False, "19", ("3400", "1200", None, None),
     ("3400", "1200", 9), "korrektur"),
    ("falsches_aufwandskonto", False, "19", ("4900", "1200", 9, "95.00"),
     ("4930", "1200", 9), "korrektur"),
    ("falsches_erloeskonto", True, "19", ("10001", "8401", 3, "95.00"),
     ("10001", "8400", 3), "korrektur"),
    ("privat_statt_aufwand", False, "0", ("4360", "1200", None, None),
     ("1800", "1200", None), "korrektur"),
    ("falsche_richtung_eingang", False, "19", ("70001", "4930", 9, "95.00"),
     ("4930", "70001", 9), "storno"),
    ("falsche_richtung_ausgang", True, "19", ("8400", "10001", 3, "95.00"),
     ("10001", "8400", 3), "storno"),
]  # fmt: skip


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


@pytest.mark.parametrize(
    ("ausgang", "satz", "vorschlag", "ziel", "weg"),
    [f[1:] for f in FEHLVORSCHLAEGE],
    ids=[f[0] for f in FEHLVORSCHLAEGE],
)
def test_kein_fehlvorschlag_haengt_fest(cli_db, ausgang, satz, vorschlag, ziel, weg):
    """Kein Vorschlag, bei dem Korrektur, Freigabe und Storno alle gesperrt sind
    (g6w N5): falscher Schlüssel und falsches Konto werden korrigiert, die falsche
    Richtung wird freigegeben und mit Grund storniert (Grenze 3)."""
    url, fabrik = cli_db
    soll, haben, schluessel, steuer = vorschlag
    bel, b = _welt(
        soll, haben, schluessel, steuer, status=P, ausgang=ausgang, satz=satz
    )
    objekte: list[Any] = [bel]
    if "1200" in (soll, haben):  # Bankumsatz: 1200 auf der Seite seines Vorzeichens
        tx = umsatz(betrag="-595.00" if haben == "1200" else "595.00")
        b = b.model_copy(update={"transaktion_id": tx.id})
        objekte.append(tx)
    anlegen(fabrik, *objekte, b)

    def cli(*args: str) -> tuple[int, str]:
        r = runner.invoke(app, [*args, "--db", url], env={"COLUMNS": "300"})
        return r.exit_code, " ".join(r.output.split())

    z_soll, z_haben, z_schluessel = ziel
    # ändert sich das Sachkonto, wird der Schlüssel ausdrücklich bestätigt
    steuer_arg = ["--steuer", str(z_schluessel)] if z_schluessel else []
    if z_schluessel is None and schluessel is not None:
        steuer_arg = ["--ohne-steuer"]
    rc, text = cli(
        "korrigiere", kurz(b.id), "--soll", z_soll, "--haben", z_haben, *steuer_arg,
        "--grund", "Fehlvorschlag",
    )  # fmt: skip
    if weg == "korrektur":
        assert rc == 0, text
        with fabrik() as s:
            (neu,) = [x for x in lade_buchungen(s) if x.storniert_durch is None]
        assert (neu.soll_konto, neu.haben_konto, neu.steuer_schluessel) == ziel
        return
    assert rc == 1 and "freigeben" in text, text
    rc, text = cli("bestaetige", kurz(b.id))
    assert rc == 0, text
    rc, text = cli("buchung", "storniere", kurz(b.id), "--grund", "falsche Richtung")
    assert rc == 0, text
    with fabrik() as s:
        assert not [
            x
            for x in lade_buchungen(s)
            if x.storno_von is None and not x.storniert_durch
        ]


# --- Browser ------------------------------------------------------------------------


@pytest.fixture
def qw(tmp_path, monkeypatch):
    billige_hashes(monkeypatch)
    return queuewelt(tmp_path)


def test_web_queue_dann_buchungen_tauscht_nicht(qw):
    """Web (test_g6w_web.py): Queue 10001 an 8125 → 10001 an 1590 gibt 303,
    /buchungen → 8125 an 1200 jetzt 422 statt 200."""
    bid = uuid4()
    bel = qw.beleg(
        pdf("Rechnung AR-41 Partner SARL 500,00"),
        id=bid,
        belegnummer="AR-41",
        belegart=Belegart.AUSGANGSRECHNUNG,
        belegdatum=date(2026, 10, 1),
        lieferant_name="Partner SARL",
        netto=D("500.00"),
        steuer=D("0.00"),
        brutto=D("500.00"),
        positionen=[
            Belegposition(
                beleg_id=bid, bezeichnung="Ware", netto=D("500.00"), steuersatz=D("0")
            )
        ],
    )
    b = qw.buchung(
        beleg_id=bel.id,
        soll="10001",
        haben="8125",
        betrag_netto=D("500.00"),
        steuer_schluessel=None,
        steuer_betrag=None,
        status=P,
        confidence=0.5,
    )
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    r = client.post(
        f"/pruefen/{b.id}/korrigieren",
        data={
            "csrf": csrf(client),
            "stand": formularwert(seite, "stand"),
            "soll": "10001",
            "haben": "1590",
            "steuer": "",
            "grund": "Test",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.status_code
    seite = client.get(f"/buchungen/{b.id}").text
    r = client.post(
        f"/buchungen/{b.id}/korrigieren",
        data={
            "csrf": csrf(client),
            "stand": formularwert(seite, "stand"),
            "soll": "8125",
            "haben": "1200",
            "steuer": "",
            "grund": "Test",
            "einmalcode": qw.web.personen["jan"].codes[-1],
        },
    )
    assert r.status_code == 422, r.status_code
    assert "8125 aus dem Haben ins Soll" in r.text
    wirksam = qw.sql(
        "SELECT soll_konto, haben_konto FROM buchungssaetze "
        "WHERE storno_von IS NULL AND storniert_durch IS NULL"
    )
    assert wirksam == [("10001", "1590")]


def test_schluessel_aus_steuer_und_netto_verlangt_grund(make_session):
    """Nennt keine Position den Satz (ZUGFeRD MINIMUM), leitet ihn ``laut_beleg`` aus
    Steuer und Netto ab — wählbar, aber nur mit Grund (Gesamttest B05)."""
    bel, b = _welt("4930", "1200", None, None, status=P)
    bel = bel.model_copy(
        update={
            "steuer": D("95.00"),
            "brutto": D("595.00"),
            "positionen": [
                p.model_copy(update={"steuersatz": None, "steuer_betrag": None})
                for p in bel.positionen
            ],
        }
    )
    anlegen(make_session, bel, b)
    assert steuer_optionen(b, bel).laut_beleg == 9
    with make_session() as s, pytest.raises(StornoError, match="Grund"):
        korrigiere(s, str(b.id), "4930", "1200", von="erika", steuer=9)
    with make_session() as s:
        k = korrigiere(
            s, str(b.id), "4930", "1200", von="erika", steuer=9, grund="PDF 19 %"
        )
        s.commit()
    assert k.neu is not None and k.neu.steuer_schluessel == 9
