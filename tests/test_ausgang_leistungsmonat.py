"""Ausgangsrechnung umsatzsteuerlich im Monat der Leistung (Gesamttest Ausgang B2, B12).

Die Steuer entsteht mit Ablauf des Voranmeldungszeitraums, in dem die Leistung
ausgeführt wurde (§ 13 Abs. 1 Nr. 1 Buchst. a Satz 1 UStG) — unabhängig vom
Rechnungsdatum. Eine innergemeinschaftliche Lieferung gehört in den Monat der
Rechnung, spätestens den Folgemonat der Lieferung (§ 13 Abs. 1 Nr. 6, § 18b Satz 2
UStG); eine Minderung (Gutschrift) in den Monat, in dem sie eintritt (§ 17 Abs. 1
Satz 7 UStG).
"""

import json
from datetime import date, datetime
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from accounti.belege.archiv import BelegArchiv
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_ausgangsrechnungen,
    lade_buchungen,
    lade_posten,
    speichere_ausgangsrechnung,
)
from accounti.elster.protokoll import neuer_eintrag, protokolliere
from accounti.erechnung.ausstellung import AusstellungError, stelle_aus
from accounti.konfiguration import Buchhaltung
from accounti.models import AusgangsrechnungStatus
from accounti.models.elster import Meldeart, Modus
from accounti.opos.verbuchung import verbuche_belege
from accounti.pruefung.perioden import schliesse
from tests.test_cli_ustva import KONFIG
from tests.test_erechnung_aufbau import FIRMA, entwurf, kunde, pos
from tests.test_ustid_protokoll import bestaetige

D = Decimal
runner = CliRunner()


@pytest.fixture
def umgebung(tmp_path):
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    return make_session, BelegArchiv(tmp_path / "archiv")


def _stelle_aus(make_session, archiv, e, datum):
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        stelle_aus(s, archiv, str(e.id)[:8], FIRMA, datum)
        s.commit()


def _verbuche(make_session, archiv):
    with make_session() as s:
        lauf = verbuche_belege(
            s, Buchhaltung(), archiv=archiv, gewinnermittlung="bilanz"
        )
        s.commit()
    return lauf


def _tage(make_session):
    with make_session() as s:
        return sorted({b.datum for b in lade_buchungen(s)})


def test_inland_bucht_zum_leistungsdatum(umgebung):
    make_session, archiv = umgebung
    e = entwurf(kunde(), pos("Montage", "1000", sonstige_leistung=True))
    e = e.model_copy(update={"leistungsdatum": date(2026, 8, 25)})
    _stelle_aus(make_session, archiv, e, date(2026, 9, 3))
    (v,) = _verbuche(make_session, archiv).verbucht
    assert _tage(make_session) == [date(2026, 8, 25)]
    assert any("§ 13 Abs. 1 Nr. 1" in h for h in v.hinweise), v.hinweise
    # Fälligkeit und Mahnwesen bleiben beim Rechnungsdatum
    assert v.posten.belegdatum == date(2026, 9, 3)


def _uebermittelt(make_session, zeitraum, modus=Modus.ECHT):
    with make_session() as s:
        protokolliere(
            s,
            neuer_eintrag(
                None,
                art=Meldeart.USTVA,
                zeitraum=zeitraum,
                modus=modus,
                weg="eric",
                datensatz="<Elster/>",
                erfolgreich=True,
                ergebnis="ok",
                pruefbericht="",
            ),
        )
        s.commit()


@pytest.mark.parametrize("zeitraum", ["2026-08", "2026-Q3"])
def test_uebermittelte_voranmeldung_verlangt_eine_berichtigung(umgebung, zeitraum):
    # Nachprüfung N8: Die Voranmeldung August (bzw. III. Quartal) ist schon abgegeben,
    # der Monat aber nicht festgeschrieben — die Umsatzsteuer der Rechnung fehlt darin
    # (§ 153 Abs. 1 AO, berichtigte Anmeldung)
    make_session, archiv = umgebung
    _uebermittelt(make_session, zeitraum)
    e = entwurf(kunde(), pos("Montage", "1000", sonstige_leistung=True))
    e = e.model_copy(update={"leistungsdatum": date(2026, 8, 25)})
    _stelle_aus(make_session, archiv, e, date(2026, 9, 3))
    (v,) = _verbuche(make_session, archiv).verbucht
    (hinweis,) = [h for h in v.hinweise if "berichtig" in h]
    assert zeitraum in hinweis and "§ 153" in hinweis, hinweis
    assert f"accounti ustva freigeben --period {zeitraum}" in hinweis


def test_gutschrift_in_uebermitteltem_zeitraum_ohne_berichtigungspflicht(umgebung):
    # Gegenprüfung N8: die Gutschrift mindert die Steuer — keine Pflicht nach § 153
    # Abs. 1 AO (keine Steuerverkürzung); eine berichtigte Voranmeldung ist möglich
    make_session, archiv = umgebung
    e = entwurf(kunde(), pos("Ware", "500")).model_copy(
        update={"leistungsdatum": date(2026, 8, 3)}
    )
    _stelle_aus(make_session, archiv, e, date(2026, 8, 3))
    _uebermittelt(make_session, "2026-09")
    g = entwurf(
        kunde(), pos("Minderung", "100"), rechnungstyp="381", korrektur_zu="2026-0001"
    )
    _stelle_aus(make_session, archiv, g, date(2026, 9, 3))
    lauf = _verbuche(make_session, archiv)
    (gutschrift,) = [v for v in lauf.verbucht if v.beleg.belegnummer == "2026-0002"]
    (hinweis,) = [h for h in gutschrift.hinweise if "übermittelt" in h]
    assert "2026-09" in hinweis and "keine Pflicht" in hinweis, hinweis
    assert "§ 153 Abs. 1 AO" in hinweis and "kann" in hinweis, hinweis
    # eine Rechnungskorrektur, die die Steuer erhöht, bleibt berichtigungspflichtig
    k = entwurf(
        kunde(), pos("Fracht", "20"), rechnungstyp="384", korrektur_zu="2026-0001"
    )
    _stelle_aus(make_session, archiv, k, date(2026, 9, 4))
    (korrektur,) = _verbuche(make_session, archiv).verbucht
    (hinweis,) = [h for h in korrektur.hinweise if "übermittelt" in h]
    assert "berichtigte Voranmeldung abgeben" in hinweis, hinweis


def test_ohne_echte_abgabe_kein_berichtigungshinweis(umgebung):
    make_session, archiv = umgebung
    _uebermittelt(make_session, "2026-08", modus=Modus.TESTFALL)
    _uebermittelt(make_session, "2026-09")  # Rechnungsmonat, Leistung im August
    e = entwurf(kunde(), pos("Montage", "1000", sonstige_leistung=True))
    e = e.model_copy(update={"leistungsdatum": date(2026, 8, 25)})
    _stelle_aus(make_session, archiv, e, date(2026, 9, 3))
    (v,) = _verbuche(make_session, archiv).verbucht
    assert not [h for h in v.hinweise if "berichtig" in h], v.hinweise


def test_leistung_im_rechnungsmonat_bleibt_beim_rechnungsdatum(umgebung):
    make_session, archiv = umgebung
    e = entwurf(kunde(), pos("Ware", "100")).model_copy(
        update={"leistungsdatum": date(2026, 9, 1)}
    )
    _stelle_aus(make_session, archiv, e, date(2026, 9, 3))
    (v,) = _verbuche(make_session, archiv).verbucht
    assert _tage(make_session) == [date(2026, 9, 3)] and v.hinweise == []


def test_leistung_nach_dem_rechnungsdatum_mit_hinweis(umgebung):
    make_session, archiv = umgebung
    e = entwurf(kunde(), pos("Ware", "100")).model_copy(
        update={"leistungsdatum": date(2026, 10, 5)}
    )
    _stelle_aus(make_session, archiv, e, date(2026, 9, 3))
    (v,) = _verbuche(make_session, archiv).verbucht
    assert _tage(make_session) == [date(2026, 9, 3)]
    assert any("Anzahlung" in h for h in v.hinweise), v.hinweise


@pytest.mark.parametrize(
    ("rechnungsdatum", "gebucht"),
    [
        (date(2026, 9, 3), date(2026, 9, 3)),  # Rechnungsmonat
        (date(2026, 10, 15), date(2026, 9, 30)),  # spätestens Ende des Folgemonats
    ],
)
def test_ig_lieferung_im_rechnungsmonat_hoechstens_folgemonat(
    umgebung, rechnungsdatum, gebucht
):
    make_session, archiv = umgebung
    with make_session() as s:
        bestaetige(s, ust_id="FR40303265045", jetzt=datetime(2026, 9, 1, 9))
        s.commit()
    e = entwurf(kunde(land="FR", ust_id="FR40303265045"), pos("Ware", "1000"))
    e = e.model_copy(update={"leistungsdatum": date(2026, 8, 25)})
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        stelle_aus(
            s, archiv, str(e.id)[:8], FIRMA, rechnungsdatum, ustid_max_alter_tage=60
        )
        s.commit()
    with make_session() as s:
        lauf = verbuche_belege(s, Buchhaltung(), archiv=archiv, ustid_max_alter_tage=60)
        s.commit()
    assert lauf.fehler == []
    assert _tage(make_session) == [gebucht]


def test_gesperrter_leistungsmonat_verlangt_oeffnen_und_berichtigung(umgebung):
    make_session, archiv = umgebung
    with make_session() as s:
        schliesse(s, "2026-08", "erika", trotzdem=True)
        s.commit()
    e = entwurf(kunde(), pos("Abbau", "500", sonstige_leistung=True))
    e = e.model_copy(update={"leistungsdatum": date(2026, 8, 28)})
    _stelle_aus(make_session, archiv, e, date(2026, 9, 4))
    lauf = _verbuche(make_session, archiv)
    assert lauf.verbucht == []
    ((_, grund),) = lauf.fehler
    assert "08/2026" in grund and "berichtig" in grund and "periode oeffnen" in grund
    with make_session() as s:
        assert lade_buchungen(s) == [] and lade_posten(s) == []


# --- B12: ausstellen prüft Sperre und Zukunft ---------------------------------------


def test_ausstellen_in_festgeschriebenen_monat_wird_abgewiesen(umgebung):
    make_session, archiv = umgebung
    with make_session() as s:
        schliesse(s, "2026-03", "erika", trotzdem=True)
        s.commit()
    e = entwurf(kunde(), pos("Ware", "100"))
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        s.commit()
    with make_session() as s, pytest.raises(AusstellungError, match="festgeschrieben"):
        stelle_aus(s, archiv, str(e.id)[:8], FIRMA, date(2026, 3, 15))
    with make_session() as s:
        ergebnis = stelle_aus(s, archiv, str(e.id)[:8], FIRMA, date(2026, 4, 1))
        s.commit()
    assert ergebnis.rechnung.nummer == "2026-0001"  # die Nummer blieb frei


def test_ausstellen_mit_datum_in_der_zukunft_wird_abgewiesen(umgebung):
    make_session, archiv = umgebung
    e = entwurf(kunde(), pos("Ware", "100"))
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        s.commit()
    heute = datetime(2026, 10, 22, 12, 0).astimezone()
    with make_session() as s, pytest.raises(AusstellungError, match="Zukunft"):
        stelle_aus(s, archiv, str(e.id)[:8], FIRMA, date(2027, 3, 1), erstellt_am=heute)
    with make_session() as s:
        (r,) = lade_ausgangsrechnungen(s)
    assert r.status is AusgangsrechnungStatus.ENTWURF


def test_ausstellen_mit_gesperrtem_leistungsmonat_gibt_einen_hinweis(umgebung):
    make_session, archiv = umgebung
    with make_session() as s:
        schliesse(s, "2026-08", "erika", trotzdem=True)
        s.commit()
    e = entwurf(kunde(), pos("Abbau", "500")).model_copy(
        update={"leistungsdatum": date(2026, 8, 28)}
    )
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        ergebnis = stelle_aus(s, archiv, str(e.id)[:8], FIRMA, date(2026, 9, 4))
        s.commit()
    assert any("08/2026" in h for h in ergebnis.hinweise), ergebnis.hinweise


# --- Ende zu Ende: Kennziffern im Leistungsmonat (Probe des Testers) ---------------


def test_ustva_meldet_die_leistung_im_august(tmp_path):
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(KONFIG, encoding="utf-8")
    url = f"sqlite:///{tmp_path / 'a.db'}"
    archiv = str(tmp_path / "archiv")
    r = runner.invoke(
        app,
        [
            "rechnung", "neu", "--db", url, "--name", "Firma B2B GmbH", "--strasse",
            "Kehrwieder 1", "--plz", "20457", "--ort", "Hamburg", "--email",
            "ap@b2b.example", "--ust-id", "DE129273398", "--leistungsdatum",
            "2026-08-25",
        ],
    )  # fmt: skip
    rid = r.output.split("Entwurf ")[1].split()[0]
    runner.invoke(
        app,
        [
            "rechnung", "position", rid, "--db", url, "--text", "Montage", "--preis",
            "1000", "--leistung",
        ],
    )  # fmt: skip
    r = runner.invoke(
        app,
        [
            "rechnung", "ausstellen", rid, "--db", url, "--archiv", archiv,
            "--config", str(konfig), "--ausgabe", str(tmp_path / "out"), "--datum",
            "2026-09-03", "--ohne-formale-pruefung",
        ],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    r = runner.invoke(
        app,
        ["opos", "verbuchen", "--db", url, "--archiv", archiv, "--config", str(konfig)],
    )
    assert r.exit_code == 0, r.output
    kz = {}
    for monat in ("2026-08", "2026-09"):
        r = runner.invoke(
            app,
            [
                "ustva",
                "--period",
                monat,
                "--json",
                "--db",
                url,
                "--config",
                str(konfig),
            ],
        )
        assert r.exit_code == 0, r.output
        kz[monat] = json.loads(r.output)["kennziffern"]
    assert kz["2026-08"].get("81") == "1000"
    assert "81" not in kz["2026-09"]
