"""Journal-Ereignisse über alle buchungsrelevanten Vorgänge (Spec 4.3)."""

import json
from datetime import date, timedelta

import pytest
from typer.testing import CliRunner

from accounti.abschluss.protokoll import protokolliere
from accounti.belege.archiv import BelegArchiv
from accounti.belege.kanaele import RohBeleg
from accounti.belege.pipeline import nimm_auf
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repo_bank import loesche_buchung
from accounti.db.repository import aktualisiere_beleg, lade_belege
from accounti.models import BuchungStatus
from accounti.pruefung.ereignisse import BuchungFestgeschriebenError
from accounti.pruefung.journal import lade_journal, pruefe_journal
from tests.pruefung_hilfe import anlegen, buchung, make_session_fixture  # noqa: F401
from tests.zahlung_hilfe import beleg_zu, kreditor, posten, speichere


def _vorgaenge(make_session):
    with make_session() as s:
        return [(e.vorgang, e.objekt_typ) for e in lade_journal(s)]


def test_beleg_importiert_und_dublette_verworfen(make_session, tmp_path):
    archiv = BelegArchiv(tmp_path / "archiv")
    roh = RohBeleg(
        dateiname="r.pdf", inhalt=b"%PDF Rechnung", kanal="upload", herkunft="/r.pdf"
    )
    with make_session() as s:
        nimm_auf(s, archiv, roh)
        nimm_auf(s, archiv, roh)  # dieselbe Datei noch einmal
        s.commit()
        (beleg,) = lade_belege(s)
        eintraege = lade_journal(s)
    assert [(e.vorgang, e.objekt_typ) for e in eintraege] == [
        ("beleg_importiert", "beleg"),
        ("beleg_verworfen", "beleg_eingang"),
    ]
    assert eintraege[0].objekt_id == str(beleg.id)
    assert json.loads(eintraege[0].nachher)["dateiname"] == "r.pdf"
    assert eintraege[1].bezug == str(beleg.id)
    with make_session() as s:
        aktualisiere_beleg(s, beleg.model_copy(update={"belegnummer": "RE-1"}))
        s.commit()
        letzter = lade_journal(s)[-1]
        assert pruefe_journal(s).in_ordnung
    assert letzter.vorgang == "beleg_geaendert"
    assert json.loads(letzter.vorher)["belegnummer"] is None
    assert json.loads(letzter.nachher)["belegnummer"] == "RE-1"


def test_vorlaeufige_buchung_verworfen_freigegebene_nicht(make_session):
    vorlaeufig = buchung(status=BuchungStatus.ZUR_PRUEFUNG)
    fest = buchung(status=BuchungStatus.AUTO_GEBUCHT)
    anlegen(make_session, vorlaeufig, fest)
    with make_session() as s:
        loesche_buchung(s, vorlaeufig.id)  # Kreditkartenabgleich löst die Zuordnung
        s.commit()
        with pytest.raises(BuchungFestgeschriebenError):
            loesche_buchung(s, fest.id)
        s.rollback()
        assert pruefe_journal(s).in_ordnung
    assert _vorgaenge(make_session)[-1] == ("buchung_verworfen", "buchung")


def test_jahresabschluss_und_oeffnen_aus_dem_abschlussprotokoll(make_session):
    with make_session() as s:
        protokolliere(s, 2025, "abgeschlossen", "erika", None, {"ergebnis": "1"})
        protokolliere(s, 2025, "geoeffnet", "jan", "Nachbuchung Steuerberater")
        protokolliere(s, 2025, "eroeffnung", "jan")  # kein eigener Vorgang
        s.commit()
        eintraege = lade_journal(s)
    assert [(e.vorgang, e.objekt_id, e.person, e.grund) for e in eintraege] == [
        ("jahr_abgeschlossen", "2025", "erika", None),
        ("jahr_geoeffnet", "2025", "jan", "Nachbuchung Steuerberater"),
    ]


def test_zahlungslauf_freigegeben_mit_person(tmp_path):
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    engine, fabrik = session_factory(url)
    init_db(engine)
    heute = date.today()
    m = kreditor()
    p = posten(m, "RE-2026-0200", "1190.00", faellig=heute - timedelta(days=1))
    speichere(fabrik, [m], [p], [beleg_zu(p, m.iban)])
    config = tmp_path / "accounti.yaml"
    config.write_text(
        "mandant:\n  name: Galerie Muster GmbH\n"
        "  bank: {iban: DE12500105170648489890, bic: COBADEFFXXX}\n",
        encoding="utf-8",
    )
    basis = ["--db", url, "--config", str(config)]
    runner = CliRunner()
    assert (
        runner.invoke(app, ["zahlung", "anlegen", *basis, "--von", "erika"]).exit_code
        == 0
    )
    r = runner.invoke(app, ["zahlung", "freigeben", "1", *basis, "--von", "jan"])
    assert r.exit_code == 0, r.output
    with fabrik() as s:
        eintraege = [e for e in lade_journal(s) if e.objekt_typ == "zahlungslauf"]
    assert [(e.vorgang, e.person) for e in eintraege] == [
        ("zahlungslauf_angelegt", "erika"),
        ("zahlungslauf_freigegeben", "jan"),
    ]
    engine.dispose()
