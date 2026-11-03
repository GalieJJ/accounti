"""Kaputtes YAML in der Konfiguration: eine Meldung statt eines Tracebacks, für jeden
Lader (Gesamttest 10b-1, Runde 7: g6w B-3).

Runde 6 machte das für ``lade_buchhaltung`` und ``sachkontenlaenge`` (export datev).
``datev stammdaten`` und ``datev belege`` endeten weiter mit einem ParserError aus
``lade_datev_mandant``, ``pruefen`` und ``verfahrensdoku`` ebenso (Grenze 7:
``lade_pruefung``, ``lade_elster``). Jetzt lesen die Lader die Datei über
``konfiguration.lies_yaml`` — dieselbe Meldung wie export datev, rc 1.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.konfiguration import KonfigurationError
from tests.pruefung_hilfe import db_url

runner = CliRunner()
KAPUTT = 'mandant:\n  name: "Galerie Muster GmbH"\nbuchhaltung_extra: [a, b\n'
MELDUNG = "kein gültiges YAML"


def _lader() -> list[tuple[str, Callable[[Path], Any]]]:
    from accounti.abschluss.konfiguration import lade_abschluss
    from accounti.anlagen.konfiguration import lade_anlagen
    from accounti.api.einstellungen import lade_server
    from accounti.aufgaben.einstellungen import lade_aufgaben_einstellungen
    from accounti.bank.einstellungen import lade_bank_einstellungen
    from accounti.belege.kanaele.einstellungen import lade_belegkanaele
    from accounti.elster.konfiguration import lade_elster, lade_elster_konten
    from accounti.erechnung.versand import lade_versand
    from accounti.export.datev_stammdaten import lade_datev_mandant, sachkontenlaenge
    from accounti.integrationen.einstellungen import lade_integrationen
    from accounti.konfiguration import lade_buchhaltung, lade_firma, lade_ustid_pruefung
    from accounti.mahnwesen.konfiguration import lade_mahnwesen
    from accounti.pruefung.einstellungen import lade_pruefung
    from accounti.zahlung.konfiguration import lade_zahlung

    return [
        ("lade_buchhaltung", lade_buchhaltung),
        ("lade_firma", lade_firma),
        ("lade_ustid_pruefung", lade_ustid_pruefung),
        ("sachkontenlaenge", sachkontenlaenge),
        (
            "lade_datev_mandant",
            lambda p: lade_datev_mandant(p, date(2026, 10, 1), "1", "2"),
        ),
        ("lade_pruefung", lade_pruefung),
        ("lade_elster", lade_elster),
        ("lade_elster_konten", lade_elster_konten),
        ("lade_abschluss", lade_abschluss),
        ("lade_anlagen", lade_anlagen),
        ("lade_server", lade_server),
        ("lade_aufgaben_einstellungen", lade_aufgaben_einstellungen),
        ("lade_bank_einstellungen", lade_bank_einstellungen),
        ("lade_belegkanaele", lade_belegkanaele),
        ("lade_versand", lade_versand),
        ("lade_integrationen", lade_integrationen),
        ("lade_mahnwesen", lade_mahnwesen),
        ("lade_zahlung", lade_zahlung),
    ]


@pytest.mark.parametrize("nr", range(len(_lader())), ids=[n for n, _ in _lader()])
def test_lader_melden_kaputtes_yaml(tmp_path, nr):
    _, lader = _lader()[nr]
    datei = tmp_path / "accounti.yaml"
    datei.write_text(KAPUTT, encoding="utf-8")
    with pytest.raises(KonfigurationError) as fehler:
        lader(datei)
    assert str(fehler.value).startswith(f"{datei}: {MELDUNG} (")


@pytest.fixture
def welt(tmp_path, monkeypatch):
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(KAPUTT, encoding="utf-8")
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(konfig))
    monkeypatch.chdir(tmp_path)
    from accounti.db import init_db, session_factory

    url = db_url(tmp_path)
    engine, _ = session_factory(url)
    init_db(engine)
    yield tmp_path, url, konfig
    engine.dispose()


@pytest.mark.parametrize(
    "befehl",
    [
        ["datev", "stammdaten", "--berater", "1", "--mandant", "2"],
        ["datev", "belege", "--period", "2026-10", "--berater", "1", "--mandant", "2"],
        ["export", "datev", "--berater", "1", "--mandant", "2", "--alle"],
        ["pruefen"],
        ["verfahrensdoku"],
    ],
    ids=[
        "datev_stammdaten",
        "datev_belege",
        "export_datev",
        "pruefen",
        "verfahrensdoku",
    ],
)
def test_befehle_melden_kaputtes_yaml(welt, befehl):
    ordner, url, konfig = welt
    zusatz = {
        "stammdaten": ["--ausgabe", str(ordner / "st")],
        "belege": [
            "--archiv",
            str(ordner / "archiv"),
            "--ausgabe",
            str(ordner / "b.zip"),
        ],  # fmt: skip
        "export": ["--output", str(ordner / "ex")],
        "verfahrensdoku": ["--ausgabe", str(ordner / "vd.md")],
    }
    extra = next((v for k, v in zusatz.items() if k in befehl), [])
    r = runner.invoke(
        app, [*befehl, *extra, "--config", str(konfig), "--db", url],
        env={"COLUMNS": "300"},
    )  # fmt: skip
    text = " ".join(r.output.split())
    assert r.exit_code == 1, text
    assert r.exception is None or isinstance(r.exception, SystemExit), repr(r.exception)
    assert MELDUNG in text, text
    assert not (ordner / "vd.md").exists()
