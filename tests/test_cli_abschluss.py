"""CLI ``accounti abschluss …``."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from tests.abschluss_hilfe import buche

runner = CliRunner()
D = Decimal
IBAN = "DE02120300000000202051"


def _text(ergebnis):
    return " ".join(ergebnis.output.split())


@pytest.fixture
def umgebung(tmp_path):
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    engine, factory = session_factory(url)
    init_db(engine)
    config = str(tmp_path / "accounti.yaml")

    def run(gruppe, *args, mit_config=True):
        extra = ["--db", url] + (["--config", config] if mit_config else [])
        return runner.invoke(app, [gruppe, *args, *extra])

    yield run, factory
    engine.dispose()


def _bank_und_buchungen(run, factory: sessionmaker):
    r = run(
        "bank",
        "verbinde",
        "--iban",
        IBAN,
        "--bezeichnung",
        "Giro",
        mit_config=False,
    )
    assert r.exit_code == 0, r.output
    buche(factory, date(2026, 1, 1), "1200", "9000", "5000", "EB", beleg_nummer="EB")
    buche(factory, date(2026, 1, 1), "9000", "0880", "5000", "EB", beleg_nummer="EB")
    buche(
        factory,
        date(2026, 5, 1),
        "1200",
        "8400",
        "1000",
        steuer_schluessel=3,
        steuer_betrag=D("190"),
    )


def test_saldo_pruefen_susa(umgebung, tmp_path):
    run, factory = umgebung
    _bank_und_buchungen(run, factory)

    r = run("abschluss", "pruefen", "--jahr", "2026")
    assert r.exit_code == 1
    assert "fehlt" in _text(r) and "gesperrt" in _text(r)

    r = run(
        "abschluss",
        "saldo",
        "--konto",
        IBAN,
        "--stichtag",
        "31.12.2026",
        "--saldo",
        "6.000,00",
    )
    assert r.exit_code == 0, r.output
    r = run("abschluss", "pruefen", "--jahr", "2026")
    assert r.exit_code == 1 and "Differenz 190,00" in _text(r)

    run(
        "abschluss",
        "saldo",
        "--konto",
        IBAN,
        "--stichtag",
        "2026-12-31",
        "--saldo",
        "6190",
    )
    r = run("abschluss", "pruefen", "--jahr", "2026")
    assert r.exit_code == 0, r.output
    assert "keine Fehler" in _text(r)

    datei = tmp_path / "susa.csv"
    r = run("abschluss", "susa", "--jahr", "2026", "--csv", str(datei))
    assert r.exit_code == 0, r.output
    assert "6.190,00" in _text(r) and "Ergebnis" in _text(r)
    zeilen = datei.read_text(encoding="utf-8").splitlines()
    assert zeilen[0].startswith("Konto;Bezeichnung")
    assert any(z.startswith("1776;") and z.endswith(";-190,00") for z in zeilen)


def test_saldo_fuer_unbekanntes_konto(umgebung):
    run, _ = umgebung
    r = run(
        "abschluss",
        "saldo",
        "--konto",
        "DE00",
        "--stichtag",
        "2026-12-31",
        "--saldo",
        "1",
    )
    assert r.exit_code == 1 and "Kein Bankkonto" in _text(r)


def test_eroeffnung_euer_vortrag_oeffnen(umgebung, tmp_path):
    """Eröffnung → EÜR → Vortrag (erst gesperrt, dann gebucht) → Sperre → Öffnen."""
    run, factory = umgebung
    r = run(
        "bank", "verbinde", "--iban", IBAN, "--bezeichnung", "Giro", mit_config=False
    )
    assert r.exit_code == 0, r.output
    for konto, saldo in (("1200", "5000"), ("0880", "-5000")):
        r = run(
            "abschluss",
            "eroeffnung",
            "--jahr",
            "2026",
            "--konto",
            konto,
            "--saldo",
            saldo,
            "--von",
            "E. Muster",
        )
        assert r.exit_code == 0, r.output
        assert "Eröffnungssaldo" in _text(r)
    r = run(
        "abschluss", "eroeffnung", "--jahr", "2026", "--konto", "4930", "--saldo", "1"
    )
    assert r.exit_code == 1 and "kein Bestandskonto" in _text(r)
    buche(
        factory,
        date(2026, 5, 1),
        "1200",
        "8400",
        "1000",
        steuer_schluessel=3,
        steuer_betrag=D("190"),
    )

    datei = tmp_path / "euer.csv"
    r = run("abschluss", "euer", "--jahr", "2026", "--csv", str(datei))
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "Umsatzsteuerpflichtige Betriebseinnahmen" in text and "1.000,00" in text
    assert "Vereinnahmte Umsatzsteuer" in text and "190,00" in text
    assert "1.190,00" in text and "Summen- und Saldenliste" in text
    assert "15;112;Umsatzsteuerpflichtige Betriebseinnahmen;1000,00" in datei.read_text(
        encoding="utf-8"
    )

    r = run("abschluss", "vortrag", "--jahr", "2026", "--von", "E. Muster")
    assert r.exit_code == 1
    assert "FEHLER bank" in _text(r) and "nicht möglich" in _text(r)

    run(
        "abschluss",
        "saldo",
        "--konto",
        IBAN,
        "--stichtag",
        "2026-12-31",
        "--saldo",
        "6190",
    )
    r = run("abschluss", "vortrag", "--jahr", "2026", "--von", "E. Muster")
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "1200 an 9000 6.190,00" in text and "9000 an 0880 6.190,00" in text
    assert "01.01.2027" in text and "gesperrt" in text and "1.190,00" in text

    # gesperrtes Jahr: Kasse, AfA und Eröffnung lehnen sauber ab
    r = run(
        "kasse", "buchen", "--betrag", "5", "--text", "Einlage", "--datum", "2026-12-31"
    )
    assert r.exit_code == 1 and "abgeschlossen" in _text(r)
    r = run("anlagen", "afa", "--jahr", "2026")
    assert r.exit_code == 1 and "abgeschlossen" in _text(r)
    r = run("abschluss", "buchen", "--jahr", "2026")
    assert r.exit_code == 1 and "abgeschlossen" in _text(r)
    r = run("abschluss", "vortrag", "--jahr", "2026", "--von", "E. Muster")
    assert r.exit_code == 1 and "schon abgeschlossen" in _text(r)

    r = run(
        "abschluss", "oeffnen", "--jahr", "2026", "--von", "E. Muster", "--grund", " "
    )
    assert r.exit_code == 1 and "Grund" in _text(r)
    r = run(
        "abschluss",
        "oeffnen",
        "--jahr",
        "2026",
        "--von",
        "E. Muster",
        "--grund",
        "Nachbuchung Beleg 4711",
    )
    assert r.exit_code == 0, r.output
    assert "geöffnet" in _text(r)
    r = run("abschluss", "vortrag", "--jahr", "2026", "--von", "E. Muster")
    assert r.exit_code == 0, r.output
    assert "unverändert" in _text(r)


def test_buchen_und_abgrenzungen(umgebung, tmp_path):
    """Bilanzierer: AfA und Abgrenzungsvorschläge, bestätigen, ablehnen, manuell."""
    from tests.abschluss_hilfe import anlegen

    run, factory = umgebung
    (tmp_path / "accounti.yaml").write_text(
        "abschluss:\n  gewinnermittlung: bilanz\n", encoding="utf-8"
    )
    buche(
        factory,
        date(2026, 12, 15),
        "4360",
        "1200",
        "1200",
        "Betriebshaftpflicht 01.01.2027 - 31.12.2027",
    )
    anlegen(factory, 3000, date(2026, 9, 10), nd=3)

    r = run("abschluss", "buchen", "--jahr", "2026")
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "333,33" in text  # AfA 3.000 × 4/36
    assert "ARAP" in text and "1.200,00" in text and "Nr. 1" in text

    r = run("abschluss", "abgrenzungen", "--jahr", "2026")
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "ARAP" in text and "0980" in text and "vorgeschlagen" in text

    r = run("abschluss", "bestaetigen", "1", "--von", "Prüferin")
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "0980 an 4360 1.200,00" in text and "31.12.2026" in text
    assert "4360 an 0980 1.200,00" in text and "01.01.2027" in text
    r = run("abschluss", "bestaetigen", "1")
    assert r.exit_code == 1 and "schon bestaetigt" in _text(r)

    miete = buche(factory, date(2026, 11, 2), "4210", "1200", "600", "Miete")
    r = run(
        "abschluss",
        "abgrenzen",
        str(miete.id)[:8],
        "--von",
        "2026-11-01",
        "--bis",
        "2027-04-30",
    )
    assert r.exit_code == 0, r.output
    assert "Nr. 2" in _text(r) and "400,00" in _text(r)  # 600 × 4/6
    r = run("abschluss", "ablehnen", "2", "--von", "Prüferin")
    assert r.exit_code == 0, r.output
    assert "abgelehnt" in _text(r)
    r = run(
        "abschluss", "abgrenzen", "zzzz", "--von", "2026-11-01", "--bis", "2027-04-30"
    )
    assert r.exit_code == 1

    r = run("abschluss", "buchen", "--jahr", "2026")
    assert r.exit_code == 0, r.output
    assert "keine neuen" in _text(r)

    r = run("abschluss", "euer", "--jahr", "2026")
    assert r.exit_code == 1 and "keine EÜR" in _text(r)
