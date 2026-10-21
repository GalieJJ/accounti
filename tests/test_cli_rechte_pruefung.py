"""Rollen in den Befehlen von Baustein 7 (Verzahnung mit Baustein 10a).

Ohne eingerichtete Benutzer bleibt alles wie bisher (die übrigen Tests laufen so).
Mit Benutzern braucht Freigeben, Korrigieren, Stornieren und Festschreiben das
passende Recht und den Einmalcode — und im Journal steht der angemeldete Benutzer,
nicht ein frei gewählter Text aus ``--von``.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.models import BuchungStatus
from accounti.models.auth import ROLLEN_RECHTE, Recht, Rolle
from tests.auth_hilfe import billige_hashes, lege_person_an, setze_schluessel
from tests.pruefung_hilfe import anlegen, buchung, db_url, kurz, umsatz

runner = CliRunner()


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture(autouse=True)
def umgebung_sauber(tmp_path, monkeypatch):
    setze_schluessel(monkeypatch)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in (
        "ACCOUNTI_DB",
        "ACCOUNTI_GESELLSCHAFT",
        "ACCOUNTI_EINMALCODE",
        "ACCOUNTI_BENUTZER",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def welt(tmp_path):
    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    tx = umsatz()
    b = buchung(tx, status=BuchungStatus.ZUR_PRUEFUNG)
    anlegen(fabrik, tx, b)
    jetzt = datetime.now()
    with fabrik() as s:
        p = {
            "jan": lege_person_an(s, "jan", Rolle.BETRACHTER, jetzt=jetzt),
            "eva": lege_person_an(s, "eva", Rolle.BUCHHALTER, jetzt=jetzt),
            "chef": lege_person_an(s, "chef", Rolle.FREIGEBER, jetzt=jetzt),
        }
    engine.dispose()
    config = str(tmp_path / "accounti.yaml")
    return url, config, b, p


def _run(url, config, *args):
    return runner.invoke(
        app,
        [str(a) for a in args] + ["--db", url, "--config", config],
        env={"COLUMNS": "250"},
    )


def _journal(url, *spalten):
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        zeilen = s.execute(
            text(f"SELECT {', '.join(spalten)} FROM journal ORDER BY nr")
        ).all()
    engine.dispose()
    return [tuple(z) for z in zeilen]


def test_buchen_umfasst_die_freigabe():
    """``korrigiere``, ``storniere`` und ``kasse storno`` prüfen nur das Recht
    *buchen* (ein Einmalcode je Befehl), legen aber freigegebene Buchungen an
    (Neubuchung „korrigiert“, Storno „geprueft“). Das trägt nur, solange jede
    Rolle mit *buchen* auch Buchungen freigeben darf."""
    for rolle, rechte in ROLLEN_RECHTE.items():
        if Recht.BUCHEN in rechte:
            assert Recht.BUCHUNG_FREIGEBEN in rechte, rolle


def test_betrachter_darf_nicht_freigeben_korrigieren_stornieren_festschreiben(welt):
    url, config, b, _ = welt
    vorher = _journal(url, "nr", "hash")
    befehle = [
        ["bestaetige", kurz(b.id)],
        ["korrigiere", kurz(b.id), "--soll", "4930", "--haben", "1200"]
        + ["--steuer", "9"],
        ["buchung", "storniere", kurz(b.id), "--grund", "doppelt"],
        ["kasse", "storno", "1", "--grund", "falsch"],
        ["periode", "schliessen", "2026-08", "--trotzdem"],
        ["periode", "oeffnen", "2026-08", "--grund", "Nachtrag"],
        ["abschluss", "vortrag", "--jahr", "2025"],
        ["abschluss", "oeffnen", "--jahr", "2025", "--grund", "Nachtrag"],
        ["journal", "uebernehmen"],
    ]
    for befehl in befehle:
        r = _run(url, config, *befehl, "--von", "jan")
        assert r.exit_code == 1, (befehl, r.output)
        assert "jan darf" in r.output, (befehl, r.output)
    assert _journal(url, "nr", "hash") == vorher


def test_freigeber_bucht_nicht_buchhalter_schon(welt):
    """Korrigieren und Stornieren ist Buchen — die Rolle freigeber hat das nicht."""
    url, config, b, _ = welt
    for befehl in (
        ["korrigiere", kurz(b.id), "--soll", "4930", "--haben", "1200"]
        + ["--steuer", "9"],
        ["buchung", "storniere", kurz(b.id), "--grund", "doppelt"],
        ["kasse", "storno", "1", "--grund", "falsch"],
    ):
        r = _run(url, config, *befehl, "--von", "chef")
        assert r.exit_code == 1, (befehl, r.output)
        assert "chef darf" in r.output and "buchen" in r.output


def test_journal_nennt_den_angemeldeten_benutzer(welt, monkeypatch):
    url, config, b, p = welt
    # ein frei gewählter Name ist kein Benutzer
    r = _run(url, config, "bestaetige", kurz(b.id), "--von", "supervisor")
    assert r.exit_code == 1 and "supervisor ist kein aktiver Benutzer" in r.output
    # falscher Einmalcode: nichts freigegeben
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", "000000")
    r = _run(url, config, "bestaetige", kurz(b.id), "--von", "eva")
    assert r.exit_code == 1 and "Einmalcode falsch" in r.output

    # ohne --von: ACCOUNTI_BENUTZER, mit Einmalcode — der Benutzer gibt frei
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "chef")
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].codes.pop())
    r = _run(url, config, "bestaetige", kurz(b.id))
    assert r.exit_code == 0, r.output
    assert "Freigegeben" in r.output

    monkeypatch.setenv("ACCOUNTI_BENUTZER", "eva")
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = _run(
        url, config, "korrigiere", kurz(b.id), "--soll", "4930", "--haben", "1200",
        "--steuer", "9", "--grund", "Bürobedarf",
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    assert "Storniert" in r.output and "Neubuchung" in r.output

    eintraege = _journal(url, "vorgang", "person")
    assert ("buchung_freigegeben", "chef") in eintraege
    nach_korrektur = eintraege[eintraege.index(("buchung_freigegeben", "chef")) + 1 :]
    assert {v for v, _ in nach_korrektur} >= {
        "storno_gebucht",
        "buchung_storniert",
        "buchung_angelegt",
    }
    assert {person for _, person in nach_korrektur} == {"eva"}
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        pruefer = set(
            s.execute(
                text(
                    "SELECT geprueft_von FROM buchungssaetze "
                    "WHERE geprueft_von IS NOT NULL"
                )
            ).scalars()
        )
        korrektur = s.execute(text("SELECT person FROM buchungskorrekturen")).scalar()
    engine.dispose()
    assert pruefer == {"chef", "eva"} and korrektur == "eva"


def test_storno_und_periode_mit_benutzer_im_journal(welt, monkeypatch):
    url, config, b, p = welt
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    assert _run(url, config, "bestaetige", kurz(b.id), "--von", "eva").exit_code == 0
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = _run(
        url, config, "buchung", "storniere", kurz(b.id), "--grund", "doppelt",
        "--von", "eva",
    )  # fmt: skip
    assert r.exit_code == 0, r.output

    # festschreiben: buchhalter darf (Buchungen freigeben), öffnen auch der freigeber
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = _run(
        url, config, "periode", "schliessen", "2026-08", "--trotzdem", "--von", "eva"
    )
    assert r.exit_code == 0, r.output
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", "000000")
    r = _run(
        url, config, "periode", "oeffnen", "2026-08", "--grund", "Rechnung fehlt",
        "--von", "chef",
    )  # fmt: skip
    assert r.exit_code == 1 and "Einmalcode falsch" in r.output
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].codes.pop())
    r = _run(
        url, config, "periode", "oeffnen", "2026-08", "--grund", "Rechnung fehlt",
        "--von", "chef",
    )  # fmt: skip
    assert r.exit_code == 0, r.output

    eintraege = _journal(url, "vorgang", "person")
    assert ("storno_gebucht", "eva") in eintraege
    assert ("buchung_storniert", "eva") in eintraege
    assert ("periode_geschlossen", "eva") in eintraege
    assert ("periode_geoeffnet", "chef") in eintraege


def test_kasse_storno_mit_benutzer_im_journal(tmp_path, monkeypatch):
    url = db_url(tmp_path)
    config = str(tmp_path / "accounti.yaml")
    kasse = ["--db", url, "--config", config]
    assert (
        runner.invoke(
            app,
            ["kasse", "anfangsbestand", "--betrag", "100", "--datum", "2026-03-01"]
            + kasse,
        ).exit_code
        == 0
    )
    r = runner.invoke(
        app,
        ["kasse", "buchen", "--betrag", "-24.90", "--text", "Porto"]
        + ["--datum", "2026-03-02", "--konto", "4910", *kasse],
    )
    assert r.exit_code == 0, r.output
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        p = lege_person_an(s, "eva", Rolle.BUCHHALTER, jetzt=datetime.now())
    engine.dispose()
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p.codes.pop())
    r = runner.invoke(
        app,
        ["kasse", "storno", "2", "--grund", "falsch", "--datum", "2026-03-04"]
        + ["--von", "eva", *kasse],
    )
    assert r.exit_code == 0, r.output
    eintraege = _journal(url, "vorgang", "person")
    assert ("storno_gebucht", "eva") in eintraege or ("buchung_angelegt", "eva") in (
        eintraege
    )
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        erfasst = s.execute(
            text("SELECT erfasst_von FROM kassenbuch WHERE storno_von = 2")
        ).scalar()
    engine.dispose()
    assert erfasst == "eva"


def test_abschluss_vortrag_und_oeffnen_mit_benutzer(tmp_path, monkeypatch):
    """Jahressperre setzen und aufheben: Buchungen freigeben, mit Einmalcode; im
    Protokoll und im Journal (auch an den EB-Buchungen) steht der Benutzer."""
    url = db_url(tmp_path)
    config = str(tmp_path / "accounti.yaml")
    engine, fabrik = session_factory(url)
    init_db(engine)
    with fabrik() as s:
        p = lege_person_an(s, "eva", Rolle.BUCHHALTER, jetzt=datetime.now())
        j = lege_person_an(s, "jan", Rolle.BETRACHTER, jetzt=datetime.now())
    from tests.abschluss_hilfe import buche

    buche(fabrik, date(2026, 1, 1), "1590", "9000", "500", "EB", beleg_nummer="EB")
    buche(fabrik, date(2026, 1, 1), "9000", "0880", "500", "EB", beleg_nummer="EB")
    engine.dispose()
    basis = ["--db", url, "--config", config]
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", j.codes.pop())
    r = runner.invoke(
        app, ["abschluss", "vortrag", "--jahr", "2026", "--von", "jan", *basis]
    )
    assert r.exit_code == 1 and "jan darf" in r.output
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p.codes.pop())
    r = runner.invoke(
        app, ["abschluss", "vortrag", "--jahr", "2026", "--von", "eva", *basis]
    )
    assert r.exit_code == 0, r.output
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p.codes.pop())
    r = runner.invoke(
        app,
        ["abschluss", "oeffnen", "--jahr", "2026", "--grund", "Nachbuchung"]
        + ["--von", "eva", *basis],
    )
    assert r.exit_code == 0, r.output
    eintraege = _journal(url, "vorgang", "person")
    assert ("jahr_abgeschlossen", "eva") in eintraege
    assert ("jahr_geoeffnet", "eva") in eintraege
    angelegt = [person for v, person in eintraege if v == "buchung_angelegt"]
    assert angelegt[-1] == "eva"  # die EB-Buchung des Vortrags
