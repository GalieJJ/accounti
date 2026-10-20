"""CLI `accounti mahnwesen …` — vom Lauf bis zum versendeten Mahnschreiben."""

from datetime import date

from pypdf import PdfReader
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_einen_posten
from accounti.models import PostenRichtung
from tests.zahlung_hilfe import debitor, posten, speichere

runner = CliRunner()

KONFIG = """\
mandant:
  name: Galerie Muster GmbH
  anschrift: {strasse: Beispielweg 3, plz: "24103", ort: Kiel}
  ust_id: DE999999999
  email: rechnung@galerie-muster.example
  kontakt: {name: Jan Muster, telefon: "0431 123456", email: jan@galerie-muster.example}
  bank: {iban: DE89370400440532013000}
"""


def _umgebung(tmp_path):
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    engine, fabrik = session_factory(url)
    init_db(engine)
    k = debitor(ust_id="DE888888888")
    p = posten(
        k,
        "2026-0042",
        "1190.00",
        faellig=date(2026, 6, 15),
        belegdatum=date(2026, 6, 1),
        richtung=PostenRichtung.FORDERUNG,
    )
    speichere(fabrik, [k], [p])
    engine.dispose()
    config = tmp_path / "accounti.yaml"
    config.write_text(KONFIG, encoding="utf-8")
    basis = ["--db", url, "--config", str(config)]
    return basis, url, p


def _run(*args):
    return runner.invoke(app, list(args))


def _mahnstufe(url, p):
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        stufe = lade_einen_posten(s, p.id).mahnstufe
    engine.dispose()
    return stufe


def test_mahnstufen_bis_zum_versendeten_schreiben(tmp_path):
    basis, url, p = _umgebung(tmp_path)
    archiv = ["--archiv", str(tmp_path / "archiv")]

    r = _run("mahnwesen", "lauf", "--stichtag", "2026-06-20", *basis)
    assert r.exit_code == 0, r.output
    assert "Mahnung 1" in r.output and "Zahlungserinnerung" in r.output
    assert "2026-0042" in r.output and "1.190,00" in r.output

    r = _run("mahnwesen", "zeigen", "1", *basis)
    assert r.exit_code == 0, r.output
    assert "Zahlungserinnerung — Rechnung 2026-0042 vom 01.06.2026" in r.output

    pdf = tmp_path / "mahnung-1.pdf"
    r = _run("mahnwesen", "versenden", "1", "--pdf", str(pdf), *archiv, *basis)
    assert r.exit_code == 0, r.output
    assert "versendet" in r.output and "Mahnstufe 1" in r.output
    assert "Zahlungserinnerung" in PdfReader(pdf).pages[0].extract_text()
    assert _mahnstufe(url, p) == 1

    r = _run("mahnwesen", "lauf", "--stichtag", "2026-06-29", *basis)
    assert r.exit_code == 0, r.output
    assert "1. Mahnung" in r.output and "1.234,69" in r.output
    assert "Unternehmer" in r.output
    text = tmp_path / "mahnung-2.txt"
    r = _run("mahnwesen", "versenden", "2", "--text", str(text), *archiv, *basis)
    assert r.exit_code == 0, r.output
    assert "Gesamtbetrag" in text.read_text(encoding="utf-8")
    assert _mahnstufe(url, p) == 2

    r = _run("mahnwesen", "historie", "10001", *basis)
    assert r.exit_code == 0, r.output
    assert "Zahlungserinnerung" in r.output and "1. Mahnung" in r.output
    assert r.output.count("versendet") >= 2

    r = _run("mahnwesen", "liste", *basis)
    assert r.exit_code == 0 and "1.234,69" in r.output


def test_sperre_einstufung_verwerfen_und_fehler(tmp_path):
    basis, url, p = _umgebung(tmp_path)
    r = _run("mahnwesen", "sperre", "10001", "--grund", "Ratenzahlung", *basis)
    assert r.exit_code == 0 and "Mahnsperre" in r.output
    r = _run("mahnwesen", "lauf", "--stichtag", "2026-06-20", *basis)
    assert "Mahnsperre: Ratenzahlung" in r.output
    assert _run("mahnwesen", "sperre", "10001", "--aufheben", *basis).exit_code == 0

    r = _run("mahnwesen", "kunde", "10001", "--verbraucher", *basis)
    assert r.exit_code == 0 and "Verbraucher" in r.output
    r = _run("mahnwesen", "lauf", "--stichtag", "2026-06-20", *basis)
    assert "Verbraucher" in r.output

    r = _run("mahnwesen", "versenden", "1", *basis)
    assert r.exit_code == 1 and "Mindestens --pdf" in r.output
    r = _run("mahnwesen", "verwerfen", "1", *basis)
    assert r.exit_code == 0 and "verworfen" in r.output
    r = _run("mahnwesen", "verwerfen", "1", *basis)
    assert r.exit_code == 1 and "nur Entwürfe" in r.output
    r = _run("mahnwesen", "zeigen", "99", *basis)
    assert r.exit_code == 1 and "Keine Mahnung 99" in r.output

    ohne = tmp_path / "ohne.yaml"
    ohne.write_text("buchhaltung: {}\n", encoding="utf-8")
    _run(
        "mahnwesen",
        "lauf",
        "--stichtag",
        "2026-06-21",
        "--db",
        url,
        "--config",
        str(ohne),
    )
    r = _run("mahnwesen", "zeigen", "2", "--db", url, "--config", str(ohne))
    assert r.exit_code == 1 and "mandant" in r.output


def test_basiszinssaetze_anzeigen(tmp_path):
    basis, _, _ = _umgebung(tmp_path)
    r = _run("mahnwesen", "basiszins", *basis)
    assert r.exit_code == 0, r.output
    assert "01.07.2026" in r.output and "31.12.2026" in r.output
    assert "1,52 %" in r.output and "bundesbank.de" in r.output
