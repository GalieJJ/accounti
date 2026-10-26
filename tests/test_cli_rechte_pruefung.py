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


def test_betrachter_darf_nicht_freigeben_korrigieren_stornieren_festschreiben(
    welt, monkeypatch
):
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
        # Schlussprüfung M-3: auch Erfassen, Bestätigen, Export und Versand
        ["kasse", "anfangsbestand", "--betrag", "100", "--datum", "2026-03-01"],
        ["kasse", "buchen", "--betrag", "-24.90", "--text", "Porto", "--datum"]
        + ["2026-03-02", "--konto", "4910"],
        ["abschluss", "eroeffnung", "--jahr", "2026", "--konto", "1200"]
        + ["--saldo", "5000"],
        ["abschluss", "bestaetigen", "1"],
        ["abschluss", "ablehnen", "1"],
        ["opos", "bestaetigen", "abc"],
        ["opos", "ablehnen", "abc"],
        ["bank", "bestaetigen", "abc"],
        ["bank", "ablehnen", "abc"],
        ["nachfordern", "anfrage", "abc", "--senden"],
        # Gesamttest Abschluss B8: Anlagen und Saldo laut Kontoauszug sind Buchen
        ["anlagen", "anlegen", "--bezeichnung", "Pkw", "--datum", "2026-01-15"]
        + ["--kosten", "30000", "--typ", "pkw"],
        ["anlagen", "afa", "--jahr", "2026"],
        ["anlagen", "abgang", "1", "--datum", "2026-06-30", "--art", "verschrottung"],
        ["abschluss", "saldo", "--konto", "DE12500105170648489890"]
        + ["--stichtag", "2026-12-31", "--saldo", "100"],
        # Nachprüfung M1: derselbe AfA-Lauf und die Abgrenzungen über abschluss buchen
        ["abschluss", "buchen", "--jahr", "2026"],
    ]
    for befehl in befehle:
        r = _run(url, config, *befehl, "--von", "jan")
        assert r.exit_code == 1, (befehl, r.output)
        assert "jan darf" in r.output, (befehl, r.output)
    # Export ohne --von: die Person aus ACCOUNTI_BENUTZER
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "jan")
    for befehl in (
        ["export", "datev", "--berater", "1", "--mandant", "2"],
        ["datev", "belege", "--period", "2026-08", "--ausgabe", "b.zip"]
        + ["--berater", "1", "--mandant", "2"],
        # Abschluss B8: Kontoauszüge schreiben fest — Buchungen freigeben
        ["datev", "kontoauszuege", "--period", "2026-08", "--anfangssaldo", "0"],
        # Nachprüfung M1: --von ist dort der Leistungszeitraum
        ["abschluss", "abgrenzen", kurz(b.id), "--von", "2026-11-01"]
        + ["--bis", "2027-10-31"],
    ):
        r = _run(url, config, *befehl)
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


def test_oeffnen_nur_wer_steuermeldungen_freigibt(welt, monkeypatch):
    """Schlussprüfung M-1: Die Festschreibung aufheben darf nicht, wer bucht
    (Funktionstrennung, GoBD Rz. 100–102) — nur die Rolle freigeber. Ist die
    Voranmeldung des Zeitraums schon freigegeben oder abgegeben, sagt accounti, dass
    eine berichtigte nötig wird."""
    from accounti.db.repo_elster import speichere_freigabe, speichere_uebermittlung
    from accounti.models.elster import Freigabe, Meldeart, Modus, Uebermittlung

    url, config, b, p = welt
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    assert _run(url, config, "bestaetige", kurz(b.id), "--von", "eva").exit_code == 0
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = _run(
        url, config, "periode", "schliessen", "2026-08", "--trotzdem", "--von", "eva"
    )
    assert r.exit_code == 0, r.output
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        speichere_freigabe(
            s,
            Freigabe(
                art=Meldeart.USTVA,
                zeitraum="2026-08",
                inhalt_hash="0" * 64,
                werte="{}",
                freigegeben_von="chef",
            ),
        )
        speichere_uebermittlung(
            s,
            Uebermittlung(
                nr=1,
                art=Meldeart.USTVA,
                zeitraum="2026-Q3",
                modus=Modus.ECHT,
                weg="attrappe",
                datensatz="<x/>",
                datensatz_hash="1" * 64,
                erfolgreich=True,
                ergebnis="ok",
                pruefbericht="",
                aufbewahren_bis=date(2036, 12, 31),
                vorgaenger_hash="0" * 64,
                hash="2" * 64,
            ),
        )
        s.commit()
    engine.dispose()
    oeffnen = ["periode", "oeffnen", "2026-08", "--grund", "Rechnung nachgereicht"]
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = _run(url, config, *oeffnen, "--von", "eva")
    assert r.exit_code == 1 and "eva darf" in r.output
    assert "Steuermeldungen freigeben" in r.output
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].codes.pop())
    r = _run(url, config, *oeffnen, "--von", "chef")
    assert r.exit_code == 0, r.output
    text = " ".join(r.output.split())
    assert "III. Quartal 2026 ist schon abgegeben" in text
    assert "berichtigte Voranmeldung" in text


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
        c = lege_person_an(s, "chef", Rolle.FREIGEBER, jetzt=datetime.now())
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
    oeffnen = ["abschluss", "oeffnen", "--jahr", "2026", "--grund", "Nachbuchung"]
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p.codes.pop())
    r = runner.invoke(app, [*oeffnen, "--von", "eva", *basis])
    assert r.exit_code == 1 and "eva darf" in r.output  # M-1: nur freigeber
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", c.codes.pop())
    r = runner.invoke(app, [*oeffnen, "--von", "chef", *basis])
    assert r.exit_code == 0, r.output
    eintraege = _journal(url, "vorgang", "person")
    assert ("jahr_abgeschlossen", "eva") in eintraege
    assert ("jahr_geoeffnet", "chef") in eintraege
    angelegt = [person for v, person in eintraege if v == "buchung_angelegt"]
    assert angelegt[-1] == "eva"  # die EB-Buchung des Vortrags


def test_laufsperre_vor_dem_einmalcode(welt, monkeypatch):
    """Schlussprüfung T-N3: Läuft ein Buchungslauf, endet periode schliessen, bevor
    der Einmalcode geprüft (und verbraucht) ist — derselbe Code gilt danach noch."""
    from accounti.betrieb.laufsperre import laufsperre

    url, config, b, p = welt
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    assert _run(url, config, "bestaetige", kurz(b.id), "--von", "eva").exit_code == 0
    code = p["eva"].codes.pop()
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", code)
    befehl = ["periode", "schliessen", "2026-08", "--trotzdem", "--von", "eva"]
    with laufsperre(url, "bank"):
        r = _run(url, config, *befehl)
    assert r.exit_code == 1 and "läuft schon" in r.output
    r = _run(url, config, *befehl)  # derselbe Wiederherstellungscode
    assert r.exit_code == 0, r.output


def test_eb_in_festgeschriebenen_januar_nicht_durch_betrachter(welt, monkeypatch):
    """Schlussprüfung M-3/T-M1: ``abschluss eroeffnung`` nutzt die EB-Ausnahme der
    Monatssperre — ohne Rolle und Einmalcode käme jeder in einen festgeschriebenen
    Januar."""
    url, config, _, p = welt
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].codes.pop())
    r = _run(
        url, config, "periode", "schliessen", "2026-01", "--trotzdem", "--von", "chef"
    )
    assert r.exit_code == 0, r.output
    vorher = _journal(url, "nr")
    eb = ["abschluss", "eroeffnung", "--jahr", "2026", "--konto", "1210"]
    r = _run(url, config, *eb, "--saldo", "777", "--von", "jan")
    assert r.exit_code == 1 and "jan darf" in r.output
    r = _run(url, config, *eb, "--saldo", "777", "--von", "chef")  # bucht nicht
    assert r.exit_code == 1 and "chef darf" in r.output
    assert _journal(url, "nr") == vorher
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = _run(url, config, *eb, "--saldo", "777", "--von", "eva")
    assert r.exit_code == 0, r.output
    assert ("buchung_angelegt", "eva") in _journal(url, "vorgang", "person")


def test_ungepruefte_person_im_journal_gekennzeichnet(welt, tmp_path, monkeypatch):
    """Schlussprüfung M-3: Mit eingerichteten Benutzern steht eine Person, die keine
    Rechteprüfung bestätigt hat (Import, Läufe), als „(ungeprüft)“ im Journal —
    ``ACCOUNTI_BENUTZER=chef`` ist von chef mit Einmalcode zu unterscheiden."""
    from tests.pdf_hilfe import pdf_mit_text

    url, config, b, p = welt
    ordner = tmp_path / "eingang"
    ordner.mkdir()
    (ordner / "re.pdf").write_bytes(pdf_mit_text("Rechnung RE-9 über 119,00 EUR"))
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "chef")
    r = runner.invoke(
        app,
        ["belege", "import", str(ordner / "re.pdf"), "--db", url]
        + ["--archiv", str(tmp_path / "archiv")],
    )
    assert r.exit_code == 0, r.output
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].codes.pop())
    assert _run(url, config, "bestaetige", kurz(b.id)).exit_code == 0
    eintraege = _journal(url, "vorgang", "person")
    assert ("beleg_importiert", "chef (ungeprüft)") in eintraege
    assert ("buchung_freigegeben", "chef") in eintraege


def test_journal_uebernehmen_nur_als_verwalter(welt, monkeypatch):
    """Schlussprüfung M-2: Die Bestandsübernahme ist ein Schritt des Betriebs beim
    Upgrade — verwalten, nicht Buchungen freigeben."""
    url, config, _, p = welt
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        s.execute(text("DROP TRIGGER journal_kein_delete"))
        s.execute(text("DELETE FROM journal"))
        s.commit()
        admin = lege_person_an(s, "admin", Rolle.VERWALTER, jetzt=datetime.now())
    engine.dispose()
    for wer in ("eva", "chef"):
        monkeypatch.setenv("ACCOUNTI_EINMALCODE", p[wer].codes.pop())
        r = _run(url, config, "journal", "uebernehmen", "--von", wer)
        assert r.exit_code == 1 and f"{wer} darf" in r.output
        assert "verwalten" in r.output
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", admin.codes.pop())
    r = _run(url, config, "journal", "uebernehmen", "--von", "admin")
    assert r.exit_code == 0, r.output
    assert ("bestand_uebernommen", "admin") in _journal(url, "vorgang", "person")


def test_zahlung_einreichen_nicht_unter_fremdem_namen(tmp_path, monkeypatch):
    """Abschlussprüfung M-A: mallory (kein Benutzer, kein Einmalcode) reicht mit
    ``--von chef`` keinen Zahlungslauf ein und gleicht keinen ab — beide Befehle
    sind gebunden; im Journal stehen die 10a-Freigaben unter dem geprüften
    Benutzer (ohne „(ungeprüft)“), das echte Einreichen unter chef."""
    from tests import test_cli_zahlung as zahlung

    url, config = zahlung._umgebung(tmp_path)
    basis = ["--db", url, "--config", config]
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        p = {
            "eva": lege_person_an(s, "eva", Rolle.BUCHHALTER, jetzt=datetime.now()),
            "chef": lege_person_an(s, "chef", Rolle.FREIGEBER, jetzt=datetime.now()),
        }
    engine.dispose()

    def run(*args):  # type: ignore[no-untyped-def]
        return runner.invoke(app, [*args, *basis], env={"COLUMNS": "250"})

    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    assert run("zahlung", "anlegen", "--von", "eva").exit_code == 0
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].codes.pop())
    assert run("zahlung", "freigeben", "1", "--von", "chef").exit_code == 0
    monkeypatch.delenv("ACCOUNTI_EINMALCODE")
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "mallory")
    datei = tmp_path / "x.xml"
    r = run("zahlung", "sepa", "1", "--datei", str(datei), "--von", "chef")
    assert r.exit_code == 1 and not datei.exists()  # Einmalcode fehlt
    r = run("zahlung", "sepa", "1", "--datei", str(datei))
    assert r.exit_code == 1 and "mallory ist kein aktiver Benutzer" in r.output
    r = run("zahlung", "abgleichen", "--von", "chef")
    assert r.exit_code == 1 and "chef darf" in r.output  # freigeber bucht nicht
    vorgaenge = [v for v, _ in _journal(url, "vorgang", "person")]
    assert "zahlungslauf_eingereicht" not in vorgaenge

    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].codes.pop())
    r = run("zahlung", "sepa", "1", "--datei", str(datei), "--von", "chef")
    assert r.exit_code == 0, r.output
    eintraege = _journal(url, "vorgang", "person")
    assert ("zahlungslauf_eingereicht", "chef") in eintraege
    assert ("zahlungslauf_angelegt", "eva") in eintraege
    assert not [x for x in eintraege if "(ungeprüft)" in x[1]], eintraege


def test_eigene_person_eines_vorgangs_wird_auch_gekennzeichnet(welt):
    """M-A (1): Ein Vorgang mit eigener Person (Protokoll, geprueft_von) außerhalb
    einer Rechteprüfung steht ebenfalls als „(ungeprüft)“ im Journal."""
    from accounti.pruefung.journal import schreibe
    from accounti.pruefung.person import journal_kontext

    url, _, _, _ = welt
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        schreibe(s, "export", "export", "frei", nachher={"n": 1}, person="chef")
        with journal_kontext(person="chef", geprueft=True):
            schreibe(s, "export", "export", "geprueft", nachher={"n": 2}, person="chef")
        s.commit()
    engine.dispose()
    eintraege = _journal(url, "objekt_id", "person")
    assert ("frei", "chef (ungeprüft)") in eintraege
    assert ("geprueft", "chef") in eintraege


def test_anlagen_mit_benutzer_im_journal(welt, monkeypatch):
    """Gesamttest Abschluss B8: Der Betrachter schied einen Pkw unwiderruflich aus;
    jetzt bucht nur, wer buchen darf — und im Journal steht der Benutzer."""
    from accounti.db.repo_auth import lade_ereignisse

    url, config, _, p = welt
    anlegen = ["anlagen", "anlegen", "--bezeichnung", "Notebook"]
    anlegen += ["--datum", "2026-02-10", "--kosten", "1500", "--typ", "notebook"]
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = _run(url, config, *anlegen, "--von", "eva")
    assert r.exit_code == 0, r.output
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = _run(url, config, "anlagen", "afa", "--jahr", "2026", "--von", "eva")
    assert r.exit_code == 0, r.output
    assert ("buchung_angelegt", "eva") in _journal(url, "vorgang", "person")
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        genutzt = [
            (e.benutzer, e.hinweis)
            for e in lade_ereignisse(s)
            if e.art == "recht_genutzt"
        ]
    engine.dispose()
    assert genutzt.count(("eva", Recht.BUCHEN.value)) == 2
    vorher = _journal(url, "nr", "hash")
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "jan")
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["jan"].codes.pop())
    r = _run(url, config, "anlagen", "abgang", "1", "--datum", "2026-06-30")
    assert r.exit_code == 1 and "jan darf" in r.output, r.output
    assert _journal(url, "nr", "hash") == vorher


def test_abschluss_buchen_und_abgrenzen_mit_benutzer(welt, monkeypatch):
    """Nachprüfung M1: ``abschluss buchen`` ruft denselben AfA-Lauf wie ``anlagen
    afa`` — ein Betrachter legte so eine AfA-Buchung an („… (ungeprüft)“ im Journal).
    Jetzt buchen mit Einmalcode, im Journal steht der geprüfte Benutzer."""
    url, config, b, p = welt
    anlegen = ["anlagen", "anlegen", "--bezeichnung", "Notebook"]
    anlegen += ["--datum", "2026-02-10", "--kosten", "1500", "--typ", "notebook"]
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    assert _run(url, config, *anlegen, "--von", "eva").exit_code == 0
    vorher = _journal(url, "nr", "hash")
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["jan"].codes.pop())
    r = _run(url, config, "abschluss", "buchen", "--jahr", "2026", "--von", "jan")
    assert r.exit_code == 1 and "jan darf" in r.output, r.output
    assert _journal(url, "nr", "hash") == vorher
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = _run(url, config, "abschluss", "buchen", "--jahr", "2026", "--von", "eva")
    assert r.exit_code == 0, r.output
    assert "AfA 2026" in r.output
    neu = _journal(url, "vorgang", "person")[len(vorher) :]
    assert ("buchung_angelegt", "eva") in neu, neu  # nicht „eva (ungeprüft)“
    # abgrenzen: die Person aus ACCOUNTI_BENUTZER (--von ist der Zeitraum)
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "jan")
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["jan"].codes.pop())
    abgrenzen = ["abschluss", "abgrenzen", kurz(b.id), "--von", "2026-11-01"]
    r = _run(url, config, *abgrenzen, "--bis", "2027-10-31")
    assert r.exit_code == 1 and "jan darf" in r.output, r.output
