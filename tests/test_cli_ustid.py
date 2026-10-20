import csv
import sqlite3

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_ustid_pruefungen, speichere_kontakt
from accounti.models import Kontakt
from tests.test_cli_rechnung import _basis, _position
from tests.test_ustid_client import EvatrAttrappe

runner = CliRunner()
UST_ID = "ATU12345678"
ALLES_A = {"ergFirmenname": "A", "ergStrasse": "A", "ergPlz": "A", "ergOrt": "A"}
GUELTIG = {"id": "b1", "anfrageZeitpunkt": "2026-10-20T10:00:00+02:00"}


@pytest.fixture
def evatr(monkeypatch):
    attrappe = EvatrAttrappe()
    attrappe.thread.start()
    monkeypatch.setenv("ACCOUNTI_EVATR_URL", attrappe.url)
    yield attrappe
    attrappe.server.shutdown()
    attrappe.server.server_close()


def _kunde(url, ust_id=UST_ID, land="AT"):
    engine, make_session = session_factory(url)
    init_db(engine)
    with make_session() as s:
        speichere_kontakt(
            s,
            Kontakt(
                name="Rahmenwerk Wien GmbH",
                strasse="Ring 1",
                plz="1010",
                ort="Wien",
                land=land,
                ust_id=ust_id,
                debitor_konto="10001",
            ),
        )
        s.commit()
    engine.dispose()


def _protokoll(url):
    engine, make_session = session_factory(url)
    with make_session() as s:
        eintraege = lade_ustid_pruefungen(s)
    engine.dispose()
    return eintraege


def _pruefe(url, konfig, *extra):
    return runner.invoke(
        app,
        ["kontakte", "pruefe-ustid", "10001", "--db", url, "--config", konfig]
        + list(extra),
    )


def test_qualifizierte_pruefung_eines_kontakts(tmp_path, evatr):
    url, konfig = _basis(tmp_path)
    _kunde(url)
    evatr.antworte(200, {**GUELTIG, "status": "evatr-0000", **ALLES_A})
    r = _pruefe(url, konfig)
    assert r.exit_code == 0, r.output
    assert "ATU12345678" in r.output
    assert "qualifiziert bestätigt" in r.output
    assert "Name stimmt" in r.output
    assert "Protokoll Nr. 1" in r.output
    (anfrage,) = evatr.anfragen
    assert anfrage["body"] == {
        "anfragendeUstid": "DE999999999",
        "angefragteUstid": UST_ID,
        "firmenname": "Rahmenwerk Wien GmbH",
        "strasse": "Ring 1",
        "plz": "1010",
        "ort": "Wien",
    }
    (p,) = _protokoll(url)
    assert p.kontakt_id is not None and p.status == "evatr-0000"

    zeigen = runner.invoke(app, ["kontakte", "zeigen", "10001", "--db", url])
    assert zeigen.exit_code == 0, zeigen.output
    assert "qualifiziert bestätigt" in zeigen.output


def test_ungueltige_nummer(tmp_path, evatr):
    url, konfig = _basis(tmp_path)
    _kunde(url)
    evatr.antworte(404, {**GUELTIG, "status": "evatr-2001"})
    r = _pruefe(url, konfig)
    assert r.exit_code == 1
    assert "nicht vergeben" in r.output
    assert len(_protokoll(url)) == 1


def test_einfache_pruefung(tmp_path, evatr):
    url, konfig = _basis(tmp_path)
    _kunde(url)
    evatr.antworte(200, {**GUELTIG, "status": "evatr-0000"})
    r = _pruefe(url, konfig, "--einfach")
    assert r.exit_code == 0, r.output
    assert "nur einfach bestätigt" in r.output
    assert set(evatr.anfragen[0]["body"]) == {"anfragendeUstid", "angefragteUstid"}


def test_bzst_nicht_erreichbar(tmp_path, evatr):
    url, konfig = _basis(tmp_path)
    _kunde(url)
    evatr.antworte(503, {**GUELTIG, "status": "evatr-1001"})
    r = _pruefe(url, konfig)
    assert r.exit_code == 1
    assert "zurzeit nicht möglich" in r.output
    assert _protokoll(url)[0].http_status == 503


def test_inlaendische_nummer_wird_nicht_angefragt(tmp_path, evatr):
    url, konfig = _basis(tmp_path)
    _kunde(url, ust_id="DE888888888", land="DE")
    r = _pruefe(url, konfig)
    assert r.exit_code == 1
    assert "inländische" in r.output
    assert evatr.anfragen == [] and _protokoll(url) == []


def test_ohne_eigene_ust_id(tmp_path, evatr):
    url, _ = _basis(tmp_path)
    _kunde(url)
    leer = tmp_path / "leer.yaml"
    leer.write_text("buchhaltung: {}\n", encoding="utf-8")
    r = _pruefe(url, str(leer))
    assert r.exit_code == 1
    assert "mandant.ust_id" in r.output
    assert evatr.anfragen == []


def test_protokoll_anzeigen_exportieren_und_pruefen(tmp_path, evatr):
    url, konfig = _basis(tmp_path)
    _kunde(url)
    evatr.antworte(200, {**GUELTIG, "status": "evatr-0000", **ALLES_A})
    evatr.antworte(404, {**GUELTIG, "status": "evatr-2001"})
    _pruefe(url, konfig)
    _pruefe(url, konfig)
    ziel = tmp_path / "protokoll.csv"
    r = runner.invoke(
        app,
        [
            "kontakte",
            "ustid-protokoll",
            "atu 123 456 78",
            "--db",
            url,
            "--csv",
            str(ziel),
        ],
    )
    assert r.exit_code == 0, r.output
    assert "evatr-0000" in r.output and "evatr-2001" in r.output
    assert "2 Einträge" in r.output and "unverändert" in r.output
    with ziel.open(encoding="utf-8", newline="") as datei:
        zeilen = list(csv.DictReader(datei, delimiter=";"))
    assert [z["status"] for z in zeilen] == ["evatr-0000", "evatr-2001"]
    assert zeilen[1]["vorgaenger_hash"] == zeilen[0]["hash"]

    db = sqlite3.connect(tmp_path / "a.db")
    db.execute("DROP TRIGGER ustid_pruefungen_kein_update")
    db.execute("UPDATE ustid_pruefungen SET status = 'evatr-0000' WHERE nr = 2")
    db.commit()
    db.close()
    r = runner.invoke(app, ["kontakte", "ustid-protokoll", "--db", url])
    assert r.exit_code == 1
    assert "Eintrag 2: Inhalt verändert" in r.output


# --- rechnung ausstellen fragt selbst an ------------------------------------------


def _eu_entwurf(url):
    r = runner.invoke(
        app,
        [
            "rechnung",
            "neu",
            "--db",
            url,
            "--name",
            "Rahmenwerk Wien GmbH",
            "--strasse",
            "Ring 1",
            "--plz",
            "1010",
            "--ort",
            "Wien",
            "--land",
            "AT",
            "--ust-id",
            UST_ID,
            "--email",
            "office@rahmenwerk.example",
        ],
    )
    assert r.exit_code == 0, r.output
    rid = r.output.split("Entwurf ")[1].split()[0]
    _position(url, rid, "--text", "Rahmen", "--preis", "100")
    return rid


def _ausstellen(tmp_path, url, konfig, rid):
    return runner.invoke(
        app,
        [
            "rechnung",
            "ausstellen",
            rid,
            "--db",
            url,
            "--config",
            konfig,
            "--archiv",
            str(tmp_path / "archiv"),
            "--ausgabe",
            str(tmp_path / "rechnungen"),
            "--datum",
            "2026-10-20",
            "--ohne-formale-pruefung",
        ],
    )


def test_ausstellen_fragt_beim_bzst_an(tmp_path, evatr):
    url, konfig = _basis(tmp_path)
    evatr.antworte(200, {**GUELTIG, "status": "evatr-0000", **ALLES_A})
    r = _ausstellen(tmp_path, url, konfig, _eu_entwurf(url))
    assert r.exit_code == 0, r.output
    assert "qualifiziert bestätigt" in r.output
    assert "2026-0001" in r.output
    assert evatr.anfragen[0]["body"]["firmenname"] == "Rahmenwerk Wien GmbH"

    # zweite Rechnung an denselben Kunden: Bestätigung ist aktuell, keine neue Abfrage
    r = _ausstellen(tmp_path, url, konfig, _eu_entwurf(url))
    assert r.exit_code == 0, r.output
    assert "2026-0002" in r.output
    assert len(evatr.anfragen) == 1


def test_ausstellen_mit_ungueltiger_nummer(tmp_path, evatr):
    url, konfig = _basis(tmp_path)
    evatr.antworte(404, {**GUELTIG, "status": "evatr-2001"})
    r = _ausstellen(tmp_path, url, konfig, _eu_entwurf(url))
    assert r.exit_code == 1
    assert "Nicht ausgestellt" in r.output
    assert "nicht vergeben" in r.output
    assert "innergemeinschaftliche Lieferung" in r.output.replace("\n", " ")
    # der Nachweis bleibt, obwohl die Ausstellung zurückgerollt wurde
    (p,) = _protokoll(url)
    assert p.status == "evatr-2001"
    liste = runner.invoke(app, ["rechnung", "liste", "--db", url])
    assert "entwurf" in liste.output


def test_verbuchen_meldet_ungueltig_gewordene_nummer(tmp_path, evatr):
    url, konfig = _basis(tmp_path)
    _kunde(url)
    evatr.antworte(200, {**GUELTIG, "status": "evatr-0000", **ALLES_A})
    assert _ausstellen(tmp_path, url, konfig, _eu_entwurf(url)).exit_code == 0
    abgelaufen = {"gueltigAb": "2020-01-01", "gueltigBis": "2026-10-19"}
    evatr.antworte(200, {**GUELTIG, "status": "evatr-2006", **abgelaufen})
    assert _pruefe(url, konfig).exit_code == 1
    r = runner.invoke(
        app,
        [
            "opos",
            "verbuchen",
            "--db",
            url,
            "--config",
            konfig,
            "--archiv",
            str(tmp_path / "archiv"),
        ],
    )
    assert r.exit_code == 0, r.output
    assert "1 zur Prüfung" in r.output
    assert "nicht bestätigt" in r.output and "19.10.2026" in r.output
