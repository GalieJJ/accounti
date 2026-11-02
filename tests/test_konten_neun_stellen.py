"""Neunstellige Personenkonten (Gesamttest 10b-1, Runde 5: g4w N5).

DATEV-Personenkonten sind eine Stelle länger als die Sachkontenlänge (4–8): bei
Sachkontenlänge 8 also 9 Stellen (``kontoart``). Mit ``buchhaltung.debitoren_von:
100000000`` bucht ``opos verbuchen`` „100000000 an 8400“ — korrigieren ließ sich das
nicht („keine Kontonummer (4–8 Ziffern)“), die Kasse lehnte das Gegenkonto ab, und
der Kontenrahmen hielt das Konto für ein Sachkonto („beide Seiten dieselbe Natur“).
"""

from __future__ import annotations

from datetime import date

import pytest
from typer.testing import CliRunner

from accounti.abschluss.kontenrahmen import lade_kontenrahmen
from accounti.buchung.konten import KontoError, pruefe_kontonummer
from accounti.cli import app
from accounti.db.repository import lade_buchungen
from accounti.export.datev_format import kontoart
from accounti.models import BuchungStatus
from tests.pruefung_hilfe import anlegen, beleg, buchung, db_url, kurz

runner = CliRunner()
NEUN = "700000001"
KONFIG = (
    "mandant:\n  name: Muster GmbH\n  sachkonten_laenge: 8\n"
    "buchhaltung:\n  kontenrahmen: SKR03\n  debitoren_von: 100000000\n"
    "  debitoren_bis: 699999999\n  kreditoren_von: 700000000\n"
    "  kreditoren_bis: 999999999\n"
)


@pytest.mark.parametrize("konto", ["1200", "10001", "177720", "12345678", NEUN])
def test_kontonummer_bis_neun_ziffern(konto):
    assert pruefe_kontonummer(konto) == konto


@pytest.mark.parametrize("konto", ["420", "1000000000"])
def test_kontonummer_ausserhalb(konto):
    with pytest.raises(KontoError, match=r"\(4–9 Ziffern\)"):
        pruefe_kontonummer(konto)


@pytest.mark.parametrize("rahmen", ["SKR03", "SKR04"])
def test_kontenrahmen_kennt_neunstellige_personenkonten(rahmen):
    kr = lade_kontenrahmen(rahmen)
    assert kr.ist_personenkonto(NEUN) and kr.ist_personenkonto("100000000")
    assert kr.ist_geldkonto(NEUN)  # Gegenkonto: die Steuer hebt sich beim Storno auf
    assert not kr.ist_personenkonto("177720")  # Unterkonto (6 Stellen)
    assert not kr.ist_personenkonto("12345678")


def test_datev_kontoart_bei_sachkontenlaenge_8():
    assert kontoart(NEUN, 8) == "personenkonto"
    assert kontoart(NEUN, 4) is None


@pytest.fixture
def welt(tmp_path, monkeypatch):
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(KONFIG, encoding="utf-8")
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(konfig))
    from accounti.db import init_db, session_factory

    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    yield tmp_path, url, fabrik, str(konfig)
    engine.dispose()


@pytest.mark.parametrize("status", [BuchungStatus.GEPRUEFT, BuchungStatus.ZUR_PRUEFUNG])
def test_korrigiere_mit_neunstelligem_kreditor(welt, status):
    _, url, fabrik, konfig = welt
    er = beleg(tag=date(2026, 10, 2))
    b = buchung(
        status=status, soll="4900", haben=NEUN, tag=date(2026, 10, 2), beleg_id=er.id
    )
    anlegen(fabrik, er, b)
    r = runner.invoke(
        app,
        ["korrigiere", kurz(b.id), "--soll", "4930", "--haben", NEUN, "--steuer", "9",
         "--db", url, "--config", konfig],
        env={"COLUMNS": "250"},
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    with fabrik() as s:
        wirksam = [x for x in lade_buchungen(s) if not x.storno_von]
    assert ("4930", NEUN) in [(x.soll_konto, x.haben_konto) for x in wirksam]


def test_kasse_bucht_gegen_neunstelliges_personenkonto(welt):
    _, url, fabrik, konfig = welt
    c = ["--db", url, "--config", konfig]
    r = runner.invoke(
        app, ["kasse", "anfangsbestand", "--betrag", "100", "--datum", "2026-10-01", *c]
    )
    assert r.exit_code == 0, r.output
    r = runner.invoke(
        app,
        ["kasse", "buchen", "--betrag", "-11.90", "--text", "Lieferant bar",
         "--datum", "2026-10-02", "--konto", NEUN, *c],
        env={"COLUMNS": "250"},
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    with fabrik() as s:
        assert [(x.soll_konto, x.haben_konto) for x in lade_buchungen(s)] == [
            (NEUN, "1000")
        ]


def test_export_datev_mit_sachkontenlaenge_der_konfiguration(welt):
    """Der Buchungsstapel nannte immer Sachkontenlänge 4 — ein 9-stelliges
    Personenkonto passte dann nicht (DATEV lehnt den Stapel ab); ``datev belege``
    nahm schon ``mandant.sachkonten_laenge``."""
    tmp_path, url, fabrik, konfig = welt
    anlegen(
        fabrik,
        buchung(
            status=BuchungStatus.GEPRUEFT, soll="4900", haben=NEUN,
            tag=date(2026, 10, 2),
        ),
        buchung(
            status=BuchungStatus.GEPRUEFT, soll="4900", haben="1234567890",
            tag=date(2026, 10, 3), steuer=None, schluessel=None,
        ),
    )  # fmt: skip
    ausgabe = tmp_path / "ex"
    r = runner.invoke(
        app,
        ["export", "datev", "--berater", "1", "--mandant", "2", "--output",
         str(ausgabe), "--db", url, "--config", konfig],
        env={"COLUMNS": "250"},
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    (datei,) = ausgabe.glob("EXTF_*.csv")
    kopf = datei.read_text(encoding="cp1252").splitlines()[0].split(";")
    assert kopf[13] == "8"  # Feld 14: Sachkontenlänge
    text = " ".join(r.output.split())
    assert "1234567890" in text and "Sachkontenlänge 8" in text
    assert NEUN not in text
