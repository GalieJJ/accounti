"""CLI: korrigiere/bestaetige/review mit Storno, buchung, journal (Akz. 5 und 6)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from typer.testing import CliRunner

from accounti.buchung.mit_beleg import kontiere_mit_beleg
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    finde_buchung,
    lade_buchungen,
    speichere_buchung,
    speichere_transaktion,
)
from accounti.konfiguration import Buchhaltung
from accounti.models import BuchungStatus
from accounti.opos.ausgleich import gleiche_aus
from accounti.opos.zuordnung import Anteil
from tests.pruefung_hilfe import anlegen, buchung, db_url, kurz, umsatz
from tests.test_buchung_mit_beleg import REGELN, mit_positionen
from tests.zahlung_hilfe import beleg_zu, kreditor, posten, speichere

runner = CliRunner()


def _run(*args):
    return runner.invoke(app, [str(a) for a in args], env={"COLUMNS": "250"})


def _fabrik(tmp_path):
    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    return url, fabrik


def _buchungen(fabrik):
    with fabrik() as s:
        return {b.id: b for b in lade_buchungen(s)}


def test_akzeptanz_6_freigegeben_nur_per_storno_beide_sichtbar(tmp_path):
    url, fabrik = _fabrik(tmp_path)
    tx = umsatz()
    b = buchung(tx, status=BuchungStatus.ZUR_PRUEFUNG)
    anlegen(fabrik, tx, b)

    r = _run("bestaetige", kurz(b.id), "--db", url, "--von", "erika")
    assert r.exit_code == 0, r.output
    assert "Freigegeben" in r.output
    r = _run("bestaetige", kurz(b.id), "--db", url)
    assert "Schon freigegeben" in r.output

    r = _run(
        "korrigiere",
        kurz(b.id),
        "--soll",
        "4930",
        "--haben",
        "1200",
        "--db",
        url,
        "--von",
        "jan",
        "--grund",
        "Bürobedarf statt Sonstiges",
    )
    assert r.exit_code == 0, r.output
    assert "Storniert" in r.output and "Neubuchung" in r.output
    alle = _buchungen(fabrik)
    assert len(alle) == 3
    original = alle[b.id]
    storno = alle[original.storniert_durch]
    neu = next(x for x in alle.values() if x.status is BuchungStatus.KORRIGIERT)
    assert storno.storno_von == b.id and original.soll_konto == "4900"
    assert neu.soll_konto == "4930" and neu.betrag_netto == Decimal("100.00")

    r = _run("review", "--db", url)
    assert "storniert" in r.output
    r = _run("buchung", "zeige", kurz(b.id), "--db", url)
    assert r.exit_code == 0, r.output
    assert f"storniert durch {kurz(storno.id)}" in r.output
    assert "Bürobedarf statt Sonstiges" in r.output
    assert "buchung_freigegeben" in r.output and "buchung_storniert" in r.output

    # alle drei gehen in den Export
    r = _run(
        "export",
        "datev",
        "--db",
        url,
        "--berater",
        "1",
        "--mandant",
        "2",
        "--output",
        tmp_path / "export",
    )
    assert r.exit_code == 0, r.output
    assert "3 Buchungen" in r.output and "3 als exportiert vermerkt" in r.output
    # und danach: exportiert, weiter nur per Storno
    r = _run(
        "korrigiere", kurz(neu.id), "--soll", "4940", "--haben", "1200", "--db", url
    )
    assert r.exit_code == 0, r.output
    assert "Storniert" in r.output
    r = _run("journal", "--vorgang", "export", "--db", url)
    assert "export" in r.output


def test_korrigiere_meldet_fehler_ohne_traceback(tmp_path):
    url, fabrik = _fabrik(tmp_path)
    b = buchung(beleg_id=kreditor().id, status=BuchungStatus.GEPRUEFT)
    anlegen(fabrik, b)
    r = _run(
        "korrigiere",
        kurz(b.id),
        "--soll",
        "4930",
        "--haben",
        "1200",
        "--steuer",
        "8",
        "--db",
        url,
    )
    assert r.exit_code == 1
    assert "Beleg" in r.output and "Traceback" not in r.output
    r = _run("korrigiere", "ffffffff", "--soll", "1", "--haben", "2", "--db", url)
    assert r.exit_code == 1 and "Keine Buchung" in r.output


# --- Der behobene Fehler über die CLI -----------------------------------------------


def _ausgleich(fabrik, skonto="0"):
    m = kreditor()
    p = posten(m, betrag="1190.00", skonto_prozent="2" if skonto != "0" else None)
    speichere(fabrik, [m], [p], [beleg_zu(p)])
    rechnung = buchung(
        None,
        soll="4930",
        haben="70001",
        netto="1000.00",
        steuer="190.00",
        beleg_id=p.beleg_id,
        status=BuchungStatus.GEPRUEFT,
    )
    anlegen(fabrik, rechnung)
    tx = umsatz("-2000.00", tag=date(2026, 10, 20))
    with fabrik() as s:
        speichere_transaktion(s, tx)
        buchungen = gleiche_aus(
            s,
            tx,
            [Anteil(p, Decimal("1190.00") - Decimal(skonto), Decimal(skonto))],
            Buchhaltung(),
        )
        s.commit()
    return tx, p, buchungen


def _neubuchung(fabrik, original_id):
    alle = _buchungen(fabrik)
    storno = alle[alle[original_id].storniert_durch]
    neu = next(
        x
        for x in alle.values()
        if x.status is BuchungStatus.KORRIGIERT and x.storno_von is None
    )
    return neu, storno


def test_cli_ausgleichsbuchung(tmp_path):
    url, fabrik = _fabrik(tmp_path)
    tx, p, (zahlung,) = _ausgleich(fabrik)
    r = _run(
        "korrigiere",
        kurz(zahlung.id),
        "--soll",
        "70001",
        "--haben",
        "1210",
        "--db",
        url,
    )
    assert r.exit_code == 0, r.output
    neu, storno = _neubuchung(fabrik, zahlung.id)
    for x in (neu, storno):
        assert x.betrag_netto == Decimal("1190.00")
        assert (x.transaktion_id, x.beleg_id) == (tx.id, p.beleg_id)


def test_cli_skontobuchung(tmp_path):
    url, fabrik = _fabrik(tmp_path)
    tx, p, buchungen = _ausgleich(fabrik, skonto="23.80")
    skonto = next(b for b in buchungen if b.steuer_schluessel)
    r = _run(
        "korrigiere",
        kurz(skonto.id),
        "--soll",
        skonto.soll_konto,
        "--haben",
        "3730",
        "--db",
        url,
    )
    assert r.exit_code == 0, r.output
    neu, _ = _neubuchung(fabrik, skonto.id)
    assert (neu.betrag_netto, neu.steuer_betrag, neu.beleg_id) == (
        Decimal("20.00"),
        Decimal("3.80"),
        p.beleg_id,
    )


def test_cli_splitbuchung(tmp_path):
    url, fabrik = _fabrik(tmp_path)
    b = mit_positionen(
        ("Super E10", "50.00", "19", "9.50"),
        ("Snack", "10.00", "7", "0.70"),
        brutto="70.20",
    )
    tx = umsatz("-70.20")
    teile = kontiere_mit_beleg(tx, b, Buchhaltung(), REGELN)
    with fabrik() as s:
        speichere_transaktion(s, tx)
        for t in teile:
            speichere_buchung(s, t)
        s.commit()
    r = _run(
        "korrigiere",
        kurz(teile[1].id),
        "--soll",
        "4650",
        "--haben",
        "1200",
        "--db",
        url,
    )
    assert r.exit_code == 0, r.output
    neu, _ = _neubuchung(fabrik, teile[1].id)
    assert (neu.betrag_netto, neu.steuer_betrag, neu.steuer_schluessel) == (
        Decimal("10.00"),
        Decimal("0.70"),
        8,
    )
    assert (neu.transaktion_id, neu.beleg_id) == (tx.id, b.id)


def test_cli_belegbuchung(tmp_path):
    url, fabrik = _fabrik(tmp_path)
    m = kreditor()
    p = posten(m)
    speichere(fabrik, [m], [p])
    rechnung = buchung(
        None,
        soll="4930",
        haben="70001",
        netto="1000.00",
        steuer="190.00",
        beleg_id=p.beleg_id,
        status=BuchungStatus.ZUR_PRUEFUNG,
    )
    anlegen(fabrik, rechnung)
    r = _run(
        "korrigiere",
        kurz(rechnung.id),
        "--soll",
        "4900",
        "--haben",
        "70001",
        "--db",
        url,
    )
    assert r.exit_code == 0, r.output
    assert "Korrigiert" in r.output  # Vorschlag: direkt
    with fabrik() as s:
        neu = finde_buchung(s, kurz(rechnung.id))
    assert (neu.soll_konto, neu.beleg_id, neu.betrag_netto) == (
        "4900",
        p.beleg_id,
        Decimal("1000.00"),
    )


def test_buchung_storniere(tmp_path):
    url, fabrik = _fabrik(tmp_path)
    b = buchung(status=BuchungStatus.AUTO_GEBUCHT)
    anlegen(fabrik, b)
    r = _run("buchung", "storniere", kurz(b.id), "--db", url, "--grund", "doppelt")
    assert r.exit_code == 0, r.output
    assert "Storniert" in r.output
    r = _run("buchung", "storniere", kurz(b.id), "--db", url, "--grund", "doppelt")
    assert r.exit_code == 1 and "schon storniert" in r.output


# --- Journal (Akzeptanz 5) ------------------------------------------------------------


def test_akzeptanz_5_manipulierter_eintrag_wird_gefunden(tmp_path):
    url, fabrik = _fabrik(tmp_path)
    b = buchung()
    anlegen(fabrik, b)
    assert _run("bestaetige", kurz(b.id), "--db", url, "--von", "jan").exit_code == 0
    r = _run("journal", "pruefen", "--db", url)
    assert r.exit_code == 0, r.output
    assert "in Ordnung" in r.output and "2 Einträge" in r.output
    r = _run("journal", "--db", url)
    assert "buchung_freigegeben" in r.output and "jan" in r.output
    r = _run("journal", "zeige", "2", "--db", url)
    assert "pruefung" in r.output and "geprueft" in r.output

    with fabrik() as s:
        s.execute(text("DROP TRIGGER journal_kein_update"))
        s.execute(text("UPDATE journal SET person = 'erika' WHERE nr = 2"))
        s.commit()
    r = _run("journal", "pruefen", "--db", url)
    assert r.exit_code == 1
    assert "Eintrag 2 wurde verändert" in r.output


def test_journal_uebernehmen(tmp_path):
    url, fabrik = _fabrik(tmp_path)
    anlegen(fabrik, buchung())
    with fabrik() as s:
        s.execute(text("DROP TRIGGER journal_kein_delete"))
        s.execute(text("DELETE FROM journal"))
        s.commit()
    assert _run("journal", "pruefen", "--db", url).exit_code == 1
    r = _run("journal", "uebernehmen", "--db", url, "--von", "jan")
    assert "1 Objekte" in r.output
    assert _run("journal", "pruefen", "--db", url).exit_code == 0
