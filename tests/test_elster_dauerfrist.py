"""Dauerfristverlängerung und Sondervorauszahlung (§§ 46–48 UStDV, USt 5 E 2026)."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from accounti.belege.archiv import BelegArchiv
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repo_elster import lade_uebermittlungen
from accounti.db.repository import lade_posten
from accounti.elster.datensatz import lies_kennzahlen
from accounti.elster.dauerfrist import (
    DauerfristError,
    berechne_svz,
    gib_dauerfrist_frei,
    uebermittle_dauerfrist,
)
from accounti.elster.konfiguration import ElsterEinstellungen
from accounti.elster.protokoll import neuer_eintrag, protokolliere
from accounti.elster.uebermittlung import AttrappenUebermittler, UebermittlungError
from accounti.elster.ustva import bereite_vor
from accounti.konfiguration import Buchhaltung
from accounti.models.elster import Meldeart, Modus
from accounti.steuer.voranmeldung import sondervorauszahlung
from accounti.steuer.zeitraum import Zeitraum
from tests.test_cli_ustva import KONFIG, text
from tests.test_elster_ustva import KONTEXT

D = Decimal
runner = CliRunner()
MONATLICH = ElsterEinstellungen(dauerfristverlaengerung=True)


def test_ein_elftel_wie_im_beispiel_der_anleitung():
    # USt 5 E 2026: 39.000 € Vorauszahlungen + 5.000 € Sondervorauszahlung → 4.000 €
    assert sondervorauszahlung(D("39000"), D("5000")) == D("4000.00")
    assert sondervorauszahlung(D("1000"), D("0")) == D("90.91")
    assert sondervorauszahlung(D("-500"), D("0")) == D("0.00")  # Überschuss → 0


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'd.db'}")
    init_db(engine)
    yield factory
    engine.dispose()


def vorjahr(s, monate=range(1, 13), betrag="3250.00", svz=None):
    """Abgegebene Voranmeldungen 2025 im Protokoll (12 × 3.250 € = 39.000 €)."""
    for m in monate:
        protokolliere(
            s,
            neuer_eintrag(
                None, art=Meldeart.USTVA, zeitraum=f"2025-{m:02d}", modus=Modus.ECHT,
                weg="attrappe", datensatz=f"<x m='{m}'/>", erfolgreich=True,
                ergebnis="übermittelt", pruefbericht="{}", betrag=D(betrag),
            ),
        )  # fmt: skip
    if svz is not None:
        protokolliere(
            s,
            neuer_eintrag(
                None, art=Meldeart.DAUERFRIST, zeitraum="2025", modus=Modus.ECHT,
                weg="attrappe", datensatz="<x/>", erfolgreich=True,
                ergebnis="übermittelt", pruefbericht="{}", betrag=D(svz),
            ),
        )  # fmt: skip
    s.commit()


def test_summe_aus_dem_protokoll(make_session):
    with make_session() as s:
        vorjahr(s, svz="5000.00")
        svz = berechne_svz(s, 2026, MONATLICH)
    assert (svz.summe_vorjahr, svz.svz_vorjahr, svz.betrag) == (
        D("39000.00"),
        D("5000.00"),
        D("4000.00"),
    )


def test_fehlende_monate_brauchen_eine_angabe(make_session):
    with make_session() as s:
        vorjahr(s, monate=range(1, 12))
        with pytest.raises(DauerfristError, match="2025-12"):
            berechne_svz(s, 2026, MONATLICH)
        svz = berechne_svz(s, 2026, MONATLICH, summe_vorjahr=D("44000"))
    assert svz.betrag == D("4000.00")


def test_quartalszahler_ohne_sondervorauszahlung(make_session):
    quartal = ElsterEinstellungen(voranmeldungszeitraum="quartal")
    with make_session() as s:
        assert berechne_svz(s, 2026, quartal).betrag is None


def test_freigeben_uebermitteln_und_posten(make_session, tmp_path):
    archiv = BelegArchiv(tmp_path / "archiv")
    einst = MONATLICH.model_copy(update={"bundesland": "BY"})
    with make_session() as s:
        vorjahr(s, svz="5000.00")
        svz = berechne_svz(s, 2026, einst)
        with pytest.raises(UebermittlungError, match="nicht freigegeben"):
            uebermittle_dauerfrist(
                s, svz, modus=Modus.ECHT, kontext=KONTEXT,
                uebermittler=AttrappenUebermittler(), archiv=archiv,
            )  # fmt: skip
        gib_dauerfrist_frei(s, svz, "Erika Muster")
        s.commit()
        u = uebermittle_dauerfrist(
            s, svz, modus=Modus.ECHT, kontext=KONTEXT,
            uebermittler=AttrappenUebermittler(), archiv=archiv,
            jetzt=datetime(2026, 2, 2, 9, 0),
        )  # fmt: skip
        s.commit()
    werte = lies_kennzahlen(u.datensatz)
    assert werte["Kz38"] == "4000.00" and werte["Jahr"] == "2026"
    assert "<Dauerfristverlaengerung>" in u.datensatz
    assert u.art is Meldeart.DAUERFRIST and u.betrag == D("4000.00")


def test_kz_39_im_dezember(make_session):
    with make_session() as s:
        protokolliere(
            s,
            neuer_eintrag(
                None, art=Meldeart.DAUERFRIST, zeitraum="2026", modus=Modus.ECHT,
                weg="attrappe", datensatz="<x/>", erfolgreich=True,
                ergebnis="übermittelt", pruefbericht="{}", betrag=D("4000.00"),
            ),
        )  # fmt: skip
        s.commit()
        dezember = bereite_vor(
            s, Zeitraum.lies("2026-12"), buchhaltung=Buchhaltung(),
            einstellungen=MONATLICH,
        )  # fmt: skip
        november = bereite_vor(
            s, Zeitraum.lies("2026-11"), buchhaltung=Buchhaltung(),
            einstellungen=MONATLICH,
        )  # fmt: skip
        ohne_dfv = bereite_vor(
            s, Zeitraum.lies("2026-12"), buchhaltung=Buchhaltung(),
            einstellungen=ElsterEinstellungen(),
        )  # fmt: skip
    assert dezember.voranmeldung.formularwerte()[39] == D("4000.00")
    assert dezember.voranmeldung.kz83 == D("-4000.00")
    assert 39 not in november.voranmeldung.formularwerte()
    assert 39 not in ohne_dfv.voranmeldung.formularwerte()


def test_cli_dauerfrist(tmp_path):
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        KONFIG
        + "  dauerfristverlaengerung: true\n  uebermittler: attrappe\n"
        + "  hersteller_id: '12345'\n",
        encoding="utf-8",
    )
    url = f"sqlite:///{tmp_path / 'c.db'}"
    basis = [
        "ustva",
        "dauerfrist",
        "--jahr",
        "2026",
        "--db",
        url,
        "--config",
        str(konfig),
    ]
    archiv = ["--archiv", str(tmp_path / "archiv")]
    zeige = runner.invoke(
        app, [*basis, "--summe-vorjahr", "39000", "--svz-vorjahr", "5000"]
    )
    assert zeige.exit_code == 0, zeige.output
    assert "4.000,00" in text(zeige) and "10.02.2026" in text(zeige)
    ohne = runner.invoke(app, basis)
    assert ohne.exit_code == 2 and "--summe-vorjahr" in text(ohne)
    werte = ["--summe-vorjahr", "39000", "--svz-vorjahr", "5000"]
    frei = runner.invoke(app, [*basis, *werte, "--freigeben", "--von", "Erika Muster"])
    assert frei.exit_code == 0, frei.output
    ab = runner.invoke(app, [*basis, *werte, "--uebermitteln", *archiv])
    assert ab.exit_code == 0, ab.output
    assert "Sondervorauszahlung 4.000,00 € als offener Posten" in text(ab)
    engine, make_session = session_factory(url)
    with make_session() as s:
        (posten,) = lade_posten(s)
        (u,) = lade_uebermittlungen(s)
    engine.dispose()
    assert posten.faellig_am == date(2026, 2, 10) and posten.betrag == D("4000.00")
    assert u.art is Meldeart.DAUERFRIST
