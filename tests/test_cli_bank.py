from datetime import date
from decimal import Decimal

from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_abgleiche, lade_buchungen, speichere_beleg
from accounti.models import AbgleichStatus, Belegposition
from tests.test_bank_abgleich import quittung
from tests.test_cli_opos import _bankdatei

runner = CliRunner()


def _run(*args):
    return runner.invoke(app, list(args))


def _text(ergebnis):
    """Ausgabe ohne die Zeilenumbrüche der 80-Spalten-Konsole."""
    return " ".join(ergebnis.output.split())


def _belege(url, *belege):
    engine, make_session = session_factory(url)
    init_db(engine)
    with make_session() as s:
        for b in belege:
            speichere_beleg(s, b)
        s.commit()
    engine.dispose()


def _db(url, funktion):
    engine, make_session = session_factory(url)
    with make_session() as s:
        ergebnis = funktion(s)
    engine.dispose()
    return ergebnis


def test_abgleich_vorschlag_kontierung_und_bericht(tmp_path):
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    papier = quittung(
        brutto="23.80",
        lieferant_name="Schreibwaren Petersen",
        belegnummer="B-7781",
    )
    papier = papier.model_copy(
        update={
            "positionen": [
                Belegposition(
                    beleg_id=papier.id,
                    bezeichnung="Druckerpapier",
                    netto=Decimal("20.00"),
                    steuersatz=Decimal("19"),
                    steuer_betrag=Decimal("3.80"),
                )
            ]
        }
    )
    parken_1 = quittung(
        brutto="5.00", lieferant_name="Parkhaus Altstadt", belegdatum=date(2026, 3, 14)
    )
    parken_2 = quittung(
        brutto="5.00", lieferant_name="Parkhaus Altstadt", belegdatum=date(2026, 3, 14)
    )
    blumen = quittung(brutto="30.00", lieferant_name="Blumen Meier")
    _belege(url, papier, parken_1, parken_2, blumen)
    csv = _bankdatei(
        tmp_path,
        "DE12;13.03.26;13.03.26;KARTENZAHLUNG;SUMUP *PETERSEN KIEL;SumUp Payments;;;"
        "-23,80;EUR;gebucht",
        "DE12;14.03.26;14.03.26;KARTENZAHLUNG;PARKHAUS ALTSTADT;APCOA;;;-5,00;EUR;"
        "gebucht",
        "DE12;15.03.26;15.03.26;ENTGELT;Kontoführung März;Sparkasse;;;-5,90;EUR;"
        "gebucht",
    )
    assert (
        _run("import", "bank", csv, "--db", url, "--format", "sparkasse").exit_code == 0
    )

    r = _run("bank", "abgleich", "--db", url)
    assert r.exit_code == 0, r.output
    assert "Schreibwaren Petersen" in _text(r)
    assert "1 abgeglichen" in _text(r) and "2 Vorschläge" in _text(r)
    assert "1 ohne passenden Beleg" in _text(r)

    r = _run("bank", "vorschlaege", "--db", url)
    assert r.exit_code == 0, r.output
    vorschlaege = _db(
        url, lambda s: lade_abgleiche(s, status={AbgleichStatus.VORGESCHLAGEN})
    )
    assert len(vorschlaege) == 2
    assert all(str(a.id)[:8] in r.output for a in vorschlaege)
    gewaehlt = next(a for a in vorschlaege if a.beleg_id == parken_1.id)
    r = _run("bank", "bestaetigen", str(gewaehlt.id)[:8], "--db", url)
    assert r.exit_code == 0, r.output
    assert "Bestätigt" in _text(r)
    assert "Keine offenen Vorschläge" in _text(_run("bank", "vorschlaege", "--db", url))

    r = _run("classify", "--db", url, "--no-llm")
    assert r.exit_code == 0, r.output
    assert "davon 2 mit Beleg" in _text(r)
    buchungen = _db(url, lade_buchungen)
    (papierbuchung,) = [b for b in buchungen if b.beleg_id == papier.id]
    assert (papierbuchung.soll_konto, papierbuchung.steuer_schluessel) == ("4930", 9)
    assert papierbuchung.steuer_betrag == Decimal("3.80")
    assert any(b.beleg_id == parken_1.id for b in buchungen)

    r = _run("bank", "offen", "--db", url)
    assert r.exit_code == 0, r.output
    assert "Kontoführung" in _text(r)
    assert "Blumen Meier" in _text(r)
    assert _text(r).count("Parkhaus Altstadt") == 1  # die zweite Quittung bleibt offen
    assert "PETERSEN" not in _text(r)


def test_bestaetigen_ohne_vorschlag(tmp_path):
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    r = _run("bank", "bestaetigen", "deadbeef", "--db", url)
    assert r.exit_code == 1
    assert "Kein Vorschlag" in _text(r)


def test_ablehnen(tmp_path):
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    _belege(url, quittung(brutto="5.00", lieferant_name="Kiosk"))
    csv = _bankdatei(
        tmp_path,
        "DE12;13.03.26;13.03.26;KARTENZAHLUNG;SUMUP 4711;SumUp;;;-5,00;EUR;gebucht",
    )
    _run("import", "bank", csv, "--db", url, "--format", "sparkasse")
    assert "1 Vorschlag," in _text(_run("bank", "abgleich", "--db", url))
    (a,) = _db(url, lade_abgleiche)
    r = _run("bank", "ablehnen", str(a.id)[:8], "--db", url)
    assert r.exit_code == 0, r.output
    assert "Abgelehnt" in _text(r)
    assert "0 Vorschläge" in _text(_run("bank", "abgleich", "--db", url))
