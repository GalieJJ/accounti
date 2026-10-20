"""CLI `accounti zahlung …` — ohne jede Bankverbindung bis zur Datei (Akzeptanz 7)."""

import xml.etree.ElementTree as ET
from datetime import date, timedelta

from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from tests.zahlung_hilfe import IBAN_BETRUG, beleg_zu, kreditor, posten, speichere

runner = CliRunner()
HEUTE = date.today()
NS = {"p": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"}


def _umgebung(tmp_path, beleg_iban=None):
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    engine, fabrik = session_factory(url)
    init_db(engine)
    m = kreditor()
    s = kreditor("Schulz KG", "70002", iban="DE02120300000000202051")
    skonto = posten(
        m,
        "RE-2026-0200",
        "1190.00",
        faellig=HEUTE + timedelta(days=25),
        belegdatum=HEUTE - timedelta(days=5),
        skonto_bis=HEUTE + timedelta(days=1),
        skonto_prozent="2",
    )
    faellig = posten(s, "SK-77", "250.00", faellig=HEUTE - timedelta(days=2))
    belege = [beleg_zu(skonto, beleg_iban or m.iban), beleg_zu(faellig, s.iban)]
    speichere(fabrik, [m, s], [skonto, faellig], belege)
    engine.dispose()
    config = tmp_path / "accounti.yaml"
    config.write_text(
        "mandant:\n"
        "  name: Galerie Muster GmbH\n"
        "  bank: {iban: DE12500105170648489890, bic: COBADEFFXXX}\n",
        encoding="utf-8",
    )
    return url, str(config)


def _run(*args):
    return runner.invoke(app, list(args))


def test_von_vorschlag_bis_zur_sepa_datei(tmp_path):
    url, config = _umgebung(tmp_path)
    basis = ["--db", url, "--config", config]

    r = _run("zahlung", "vorschlag", *basis)
    assert r.exit_code == 0, r.output
    assert r.output.index("RE-2026-0200") < r.output.index("SK-77")
    assert "Skontofrist endet morgen" in r.output
    assert "seit 2 Tagen überfällig" in r.output
    assert "1.416,20" in r.output and "23,80" in r.output

    r = _run("zahlung", "anlegen", *basis, "--von", "erika")
    assert r.exit_code == 0, r.output
    assert "Zahlungslauf 1 angelegt" in r.output

    r = _run("zahlung", "pruefen", "1", *basis)
    assert r.exit_code == 0, r.output
    assert "keine Befunde" in r.output

    r = _run("zahlung", "freigeben", "1", *basis, "--von", "jan")
    assert r.exit_code == 0, r.output
    assert "freigegeben" in r.output

    datei = tmp_path / "ueberweisung.xml"
    r = _run("zahlung", "sepa", "1", "--datei", str(datei), *basis, "--von", "jan")
    assert r.exit_code == 0, r.output
    assert "pain.001.001.09" in r.output and "Onlinebanking" in r.output
    wurzel = ET.parse(datei).getroot()
    assert wurzel.findtext(".//p:GrpHdr/p:NbOfTxs", namespaces=NS) == "2"
    assert wurzel.findtext(".//p:GrpHdr/p:CtrlSum", namespaces=NS) == "1416.20"
    assert wurzel.findtext(".//p:DbtrAgt//p:BICFI", namespaces=NS) == "COBADEFFXXX"

    # zweiter Aufruf: dieselbe Datei, kein neuer Auftrag
    zweite = tmp_path / "nochmal.xml"
    r = _run("zahlung", "sepa", "1", "--datei", str(zweite), *basis)
    assert r.exit_code == 0, r.output
    assert "unverändert" in r.output
    assert zweite.read_bytes() == datei.read_bytes()

    r = _run("zahlung", "liste", *basis)
    assert "eingereicht" in r.output and "1.416,20" in r.output
    r = _run("zahlung", "zeigen", "1", *basis)
    assert r.exit_code == 0, r.output
    for erwartet in ("eingereicht", "jan", "erika", "RE-2026-0200", "Protokoll"):
        assert erwartet in r.output

    # der Posten steht nicht noch einmal im Vorschlag
    r = _run("zahlung", "vorschlag", *basis)
    assert "bereits in Zahlungslauf 1 (eingereicht)" in r.output

    r = _run("zahlung", "abgleichen", *basis)
    assert r.exit_code == 0, r.output
    assert "noch keiner ausgeführt" in r.output


def test_abweichende_iban_blockiert_mit_klarer_meldung(tmp_path):
    url, config = _umgebung(tmp_path, beleg_iban=IBAN_BETRUG)
    basis = ["--db", url, "--config", config]
    assert _run("zahlung", "anlegen", *basis).exit_code == 0

    r = _run("zahlung", "pruefen", "1", *basis)
    assert r.exit_code == 1
    assert "gesperrt" in r.output and "IBAN-Abweichung" in r.output
    assert "DE75 5121 0800 1245 1261 99" in r.output
    r = _run("zahlung", "freigeben", "1", *basis)
    assert r.exit_code == 1 and "IBAN-Abweichung" in r.output
    r = _run("zahlung", "sepa", "1", "--datei", str(tmp_path / "x.xml"), *basis)
    assert r.exit_code == 1 and "erst freigeben" in r.output
    assert not (tmp_path / "x.xml").exists()

    r = _run("zahlung", "iban-klaeren", "1", "1", "--grund", "Rückruf 20.10.", *basis)
    assert r.exit_code == 0, r.output
    assert _run("zahlung", "freigeben", "1", *basis).exit_code == 0


def test_entfernen_storno_und_sperre(tmp_path):
    url, config = _umgebung(tmp_path)
    basis = ["--db", url, "--config", config]
    assert _run("zahlung", "anlegen", *basis).exit_code == 0
    r = _run("zahlung", "entfernen", "1", "2", *basis)
    assert r.exit_code == 0 and "SK-77" in r.output
    assert _run("zahlung", "freigeben", "1", *basis).exit_code == 0
    r = _run("zahlung", "entfernen", "1", "1", *basis)
    assert r.exit_code == 1 and "nur stornieren" in r.output

    r = _run("zahlung", "stornieren", "1", *basis)
    assert r.exit_code != 0
    r = _run("zahlung", "stornieren", "1", "--grund", "falscher Termin", *basis)
    assert r.exit_code == 0 and "storniert" in r.output

    r = _run("zahlung", "sperre", "70002", "--grund", "Reklamation", *basis)
    assert r.exit_code == 0 and "Schulz KG" in r.output
    r = _run("zahlung", "vorschlag", *basis)
    assert "Zahlungssperre: Reklamation" in r.output
    r = _run("zahlung", "sperre", "70002", "--aufheben", *basis)
    assert r.exit_code == 0 and "aufgehoben" in r.output
    r = _run("zahlung", "sperre", "99999", "--grund", "x", *basis)
    assert r.exit_code == 1 and "Kein Kontakt" in r.output


def test_ohne_auftraggeber_klare_meldung(tmp_path):
    url, _ = _umgebung(tmp_path)
    r = _run("zahlung", "anlegen", "--db", url, "--config", str(tmp_path / "x.yaml"))
    assert r.exit_code == 1
    assert "Auftraggeber fehlt" in r.output
