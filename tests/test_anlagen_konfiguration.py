"""Abschnitt ``anlagen`` — Standards je Kontenrahmen, alles läuft auch ohne."""

from datetime import date
from decimal import Decimal

import pytest

from accounti.anlagen.konfiguration import lade_anlagen
from accounti.konfiguration import KonfigurationError
from accounti.models.anlagen import AfaArt, Anlagegut


def _gut(art, konto="0420", **kw):
    return Anlagegut(
        bezeichnung="X",
        konto=konto,
        anschaffungsdatum=date(2026, 1, 1),
        anschaffungskosten=Decimal("700"),
        nutzungsdauer=5,
        afa_art=art,
        **kw,
    )


def test_ohne_datei_skr03(tmp_path):
    e = lade_anlagen(tmp_path / "fehlt.yaml")
    assert e.kontenrahmen == "SKR03"
    assert e.konten.afa == "4830"
    assert e.afa_konto(_gut(AfaArt.LINEAR)) == "4830"
    assert e.afa_konto(_gut(AfaArt.GWG)) == "4855"
    assert e.afa_konto(_gut(AfaArt.SAMMELPOSTEN, konto="0485")) == "4862"
    assert e.afa_konto(_gut(AfaArt.LINEAR, konto="0320")) == "4832"
    assert e.afa_konto(_gut(AfaArt.E_FAHRZEUG, konto="0320")) == "4832"
    assert e.afa_konto(_gut(AfaArt.DIGITAL, konto="0027", immateriell=True)) == "4822"
    assert e.afa_konto(_gut(AfaArt.LINEAR, afa_konto="4840")) == "4840"
    assert e.ist_anlagekonto("0420") and not e.ist_anlagekonto("4930")
    assert e.rechtsstand().grenzen_am(date(2026, 1, 1)).gwg == 800


def test_skr04_standards(tmp_path):
    datei = tmp_path / "a.yaml"
    datei.write_text("buchhaltung:\n  kontenrahmen: SKR04\n", encoding="utf-8")
    e = lade_anlagen(datei)
    assert (e.konten.afa, e.konten.gwg_afa, e.konten.sammelposten_afa) == (
        "6220",
        "6260",
        "6264",
    )
    assert (e.konten.abgang_buchverlust, e.konten.abgang_buchgewinn) == ("6895", "4855")
    assert e.afa_konto(_gut(AfaArt.LINEAR, konto="0520")) == "6222"


def test_eigene_werte_und_rechtsstand(tmp_path):
    rs = tmp_path / "rs.yaml"
    rs.write_text(
        "grenzen:\n  - von: 2026-01-01\n    gwg: 1000\n    quelle: test\n",
        encoding="utf-8",
    )
    datei = tmp_path / "a.yaml"
    datei.write_text(
        f"anlagen:\n  rechtsstand: {rs}\n  konten:\n    afa: '4831'\n"
        "  kfz_konten: ['0300']\n",
        encoding="utf-8",
    )
    e = lade_anlagen(datei)
    assert e.konten.afa == "4831"
    assert e.konten.gwg_afa == "4855"  # Rest bleibt Standard
    assert e.kfz_konten == ["0300"]
    assert e.rechtsstand().grenzen_am(date(2026, 6, 1)).gwg == 1000


def test_fehlerhafter_abschnitt(tmp_path):
    datei = tmp_path / "a.yaml"
    datei.write_text("anlagen:\n  konten: [1, 2]\n", encoding="utf-8")
    with pytest.raises(KonfigurationError, match="anlagen"):
        lade_anlagen(datei)
