"""CLI ``accounti datev``: stammdaten, belege (kontoauszuege in test_kontoauszuege)."""

import zipfile

import pytest
from typer.testing import CliRunner

from accounti.belege.archiv import BelegArchiv
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import speichere_kontakt
from accounti.models import Belegart, Kontakt
from tests.test_datev_belege import PDF, _beleg, _buchung

runner = CliRunner()


def _text(r):
    return " ".join(r.output.split())


@pytest.fixture
def umgebung(tmp_path):
    url = f"sqlite:///{tmp_path / 'd.db'}"
    engine, make = session_factory(url)
    init_db(engine)
    archiv = tmp_path / "archiv"
    with make() as s:
        speichere_kontakt(s, Kontakt(name="Kunde A GmbH", debitor_konto="10001"))
        speichere_kontakt(s, Kontakt(name="Lieferant B KG", kreditor_konto="70001"))
        speichere_kontakt(s, Kontakt(name="Lieferant C AG", kreditor_konto="70002"))
        beleg = _beleg(
            s, BelegArchiv(archiv), "r.pdf", PDF, Belegart.EINGANGSRECHNUNG, "R-1"
        )
        _buchung(s, "R-1", beleg_id=beleg.id)  # 4930 an 70001 im August
        s.commit()
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        "datev:\n  berater_nummer: '29098'\n  mandanten_nummer: '00042'\n"
        "  wirtschaftsjahr_beginn: '2026-01-01'\n",
        encoding="utf-8",
    )
    return tmp_path, ["--db", url, "--config", str(konfig)], archiv


def test_stammdaten(umgebung):
    tmp_path, basis, _ = umgebung
    r = runner.invoke(
        app, ["datev", "stammdaten", "--ausgabe", str(tmp_path / "aus"), *basis]
    )
    assert r.exit_code == 0, r.output
    assert "3 Personenkonten" in _text(r)
    (datei,) = (tmp_path / "aus").glob("EXTF_DebKred_Stamm_*.csv")
    kopf = datei.read_bytes().decode("cp1252").split("\r\n")[0].split(";")
    assert kopf[10:12] == ["29098", "42"]  # aus der Konfiguration


def test_stammdaten_nur_konten_mit_buchungen_im_zeitraum(umgebung):
    tmp_path, basis, _ = umgebung
    r = runner.invoke(
        app,
        [
            "datev",
            "stammdaten",
            "--period",
            "2026-08",
            "--ausgabe",
            str(tmp_path / "aus"),
            *basis,
        ],
    )
    assert r.exit_code == 0, r.output
    assert "1 Personenkonten" in _text(r)


def test_stammdaten_ohne_beraternummer(tmp_path):
    r = runner.invoke(
        app,
        [
            "datev",
            "stammdaten",
            "--db",
            f"sqlite:///{tmp_path / 'x.db'}",
            "--config",
            str(tmp_path / "fehlt.yaml"),
        ],
    )
    assert r.exit_code == 1
    assert "Beraternummer" in _text(r)


def test_belege(umgebung):
    tmp_path, basis, archiv = umgebung
    ziel = tmp_path / "aus" / "belege-08.zip"
    r = runner.invoke(
        app,
        [
            "datev",
            "belege",
            "--period",
            "2026-08",
            "--ausgabe",
            str(ziel),
            "--archiv",
            str(archiv),
            "--berater",
            "1234",
            "--mandant",
            "7",
            *basis,
        ],
    )
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "1 Belege" in text and "1 von 1 Buchungen verknüpft" in text
    with zipfile.ZipFile(ziel) as z:
        assert "document.xml" in z.namelist()
        assert b"<consultantNumber>1234</consultantNumber>" in z.read("document.xml")
    assert (
        tmp_path / "aus" / "EXTF_Buchungsstapel_20260801_20260831_Beleglink.csv"
    ).exists()


def test_belege_falscher_zeitraum(umgebung):
    tmp_path, basis, archiv = umgebung
    r = runner.invoke(
        app,
        [
            "datev",
            "belege",
            "--period",
            "08/2026",
            "--ausgabe",
            str(tmp_path / "z.zip"),
            *basis,
        ],
    )
    assert r.exit_code == 1
    assert "JJJJ-MM" in _text(r)
