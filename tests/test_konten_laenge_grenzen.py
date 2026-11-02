"""Grenzen der Kontenlängen (Gesamttest 10b-1, Runde 6: g5w-konten N2, N3).

N2: ``export datev`` übernahm ``mandant.sachkonten_laenge`` ohne Bereichsprüfung — 0,
true, 3, 9 und -1 standen im Kopf (Feld 14) mit rc 0, obwohl die Meldung „4 bis 8“
nennt; bei Länge 6 oder 8 liefen 5-stellige Personenkonten ohne Warnung durch, während
``datev stammdaten`` dieselbe Einstellung ablehnte. DATEV erlaubt 4 bis 8, ein
Personenkonto ist eine Stelle länger.

N3: Die Personenkontenbereiche (``buchhaltung.debitoren_von`` …) hatten keine
Obergrenze — 10-stellige Debitoren wurden gebucht, ließen sich aber weder korrigieren
noch in der Kasse gegenbuchen (Kontonummern 4–9 Ziffern). DATEV-Personenkonten haben
höchstens 9 Stellen.
"""

from __future__ import annotations

from datetime import date

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.export.datev import DATEVConfig, DATEVExporter
from accounti.export.datev_stammdaten import sachkontenlaenge
from accounti.konfiguration import Buchhaltung, KonfigurationError, lade_buchhaltung
from accounti.models import BuchungStatus
from tests.pruefung_hilfe import anlegen, buchung, db_url

runner = CliRunner()


def _konfig(tmp_path, text: str):  # noqa: ANN001, ANN202
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(text, encoding="utf-8")
    return pfad


# --- N2: Sachkontenlänge ------------------------------------------------------------


@pytest.mark.parametrize(
    ("wert", "erwartet"),
    [("4", 4), ("5", 5), ("6", 6), ("7", 7), ("8", 8), ("'8 '", 8), ("'6'", 6)],
)
def test_sachkontenlaenge_4_bis_8(tmp_path, wert, erwartet):
    pfad = _konfig(tmp_path, f"mandant:\n  sachkonten_laenge: {wert}\n")
    assert sachkontenlaenge(pfad) == erwartet


@pytest.mark.parametrize("wert", ["0", "3", "9", "-1", "true", "4.0", "abc", "[8]"])
def test_sachkontenlaenge_ausserhalb_ist_konfigurationsfehler(tmp_path, wert):
    pfad = _konfig(tmp_path, f"mandant:\n  sachkonten_laenge: {wert}\n")
    with pytest.raises(KonfigurationError, match="4 bis 8"):
        sachkontenlaenge(pfad)


@pytest.mark.parametrize(
    "text", ["", "mandant:\n  name: X\n", "mandant:\n  sachkonten_laenge:\n"]
)
def test_sachkontenlaenge_ohne_angabe_4(tmp_path, text):
    assert sachkontenlaenge(_konfig(tmp_path, text)) == 4


def test_kaputte_konfiguration_ist_konfigurationsfehler(tmp_path):
    """export_kaputt.py: kaputtes YAML endete in einem ParserError mit Traceback."""
    with pytest.raises(KonfigurationError):
        sachkontenlaenge(_konfig(tmp_path, "mandant: [unclosed\n"))


def _buchungen():  # noqa: ANN202
    return [
        buchung(status=BuchungStatus.GEPRUEFT, soll="10000", haben="8400",
                tag=date(2026, 10, 1), schluessel=3),
        buchung(status=BuchungStatus.GEPRUEFT, soll="4900", haben="70001",
                tag=date(2026, 10, 2)),
        buchung(status=BuchungStatus.GEPRUEFT, soll="4900", haben="70001",
                tag=date(2026, 10, 3)),
    ]  # fmt: skip


@pytest.mark.parametrize("laenge", [6, 8])
def test_export_warnt_vor_unpassenden_personenkonten(tmp_path, laenge):
    exporter = DATEVExporter(
        DATEVConfig(berater_nummer="1", mandanten_nummer="2", sachkonten_laenge=laenge)
    )
    exporter.exportiere(_buchungen(), tmp_path)
    personen = [w for w in exporter.warnungen if "Personenkonto" in w]
    assert len(personen) == 2  # je Konto einmal, nicht je Buchung
    assert all(f"erwartet {laenge + 1} Stellen" in w for w in personen)
    assert any("10000" in w for w in personen) and any("70001" in w for w in personen)


def test_export_mit_laenge_4_ohne_warnung(tmp_path):
    exporter = DATEVExporter(DATEVConfig(berater_nummer="1", mandanten_nummer="2"))
    exporter.exportiere(_buchungen(), tmp_path)
    assert exporter.warnungen == []


def test_export_personenkonten_aus_den_bereichen_der_buchhaltung(tmp_path):
    """Neunstellige Bereiche (Sachkontenlänge 8): 100000000 passt, 10000 nicht."""
    exporter = DATEVExporter(
        DATEVConfig(
            berater_nummer="1",
            mandanten_nummer="2",
            sachkonten_laenge=8,
            personenkonten=((100000000, 699999999), (700000000, 999999999)),
        )
    )
    exporter.exportiere(
        [buchung(status=BuchungStatus.GEPRUEFT, soll="100000000", haben="8400",
                 tag=date(2026, 10, 1), schluessel=3)],
        tmp_path,
    )  # fmt: skip
    assert exporter.warnungen == []


@pytest.fixture
def cli_welt(tmp_path, monkeypatch):
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    from accounti.db import init_db, session_factory

    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    anlegen(fabrik, *_buchungen())
    yield tmp_path, url
    engine.dispose()


def _export(tmp_path, url, konfig):  # noqa: ANN001, ANN202
    r = runner.invoke(
        app,
        ["export", "datev", "--berater", "1", "--mandant", "2", "--output",
         str(tmp_path / "ex"), "--db", url, "--config", str(konfig)],
        env={"COLUMNS": "300", "ACCOUNTI_KONFIG": str(konfig)},
    )  # fmt: skip
    return r.exit_code, " ".join(r.output.split())


@pytest.mark.parametrize("wert", ["9", "0", "true"])
def test_cli_export_lehnt_laenge_ausserhalb_ab(cli_welt, wert):
    tmp_path, url = cli_welt
    konfig = _konfig(tmp_path, f"mandant:\n  sachkonten_laenge: {wert}\n")
    rc, text = _export(tmp_path, url, konfig)
    assert rc == 1 and "4 bis 8" in text, text
    assert not (tmp_path / "ex").exists() or not list((tmp_path / "ex").iterdir())


def test_cli_export_warnt_bei_laenge_6(cli_welt):
    tmp_path, url = cli_welt
    konfig = _konfig(tmp_path, "mandant:\n  sachkonten_laenge: 6\n")
    rc, text = _export(tmp_path, url, konfig)
    assert rc == 0, text
    assert "Personenkonto 10000" in text and "erwartet 7 Stellen" in text


# --- N3: Personenkontenbereiche -----------------------------------------------------


@pytest.mark.parametrize(
    "feld", ["debitoren_von", "debitoren_bis", "kreditoren_von", "kreditoren_bis"]
)
def test_personenkontenbereich_hoechstens_neun_stellen(tmp_path, feld):
    pfad = _konfig(tmp_path, f"buchhaltung:\n  {feld}: 1000000000\n")
    with pytest.raises(KonfigurationError, match=f"{feld}.*9 Stellen"):
        lade_buchhaltung(pfad)


def test_neunstellige_bereiche_erlaubt():
    b = Buchhaltung(
        debitoren_von=100000000,
        debitoren_bis=699999999,
        kreditoren_von=700000000,
        kreditoren_bis=999999999,
    )
    assert b.kreditoren_bis == 999999999


def test_cli_export_kaputtes_yaml_meldung_statt_traceback(cli_welt):
    """export_kaputt.py: „mandant: [unclosed“ endete in export datev mit ParserError
    (aus lade_buchhaltung, vor der Sachkontenlänge)."""
    tmp_path, url = cli_welt
    konfig = _konfig(tmp_path, "mandant: [unclosed\n")
    rc, text = _export(tmp_path, url, konfig)
    assert rc == 1 and "kein gültiges YAML" in text, text
    assert "Traceback" not in text


def test_lade_buchhaltung_kaputtes_yaml(tmp_path):
    with pytest.raises(KonfigurationError, match="kein gültiges YAML"):
        lade_buchhaltung(_konfig(tmp_path, "buchhaltung: [unclosed\n"))
