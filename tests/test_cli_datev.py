"""CLI ``accounti datev``: stammdaten, belege, kontoauszuege."""

import zipfile
from datetime import date
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from accounti.belege.archiv import BelegArchiv
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repo_export import lade_kontoauszuege
from accounti.db.repository import (
    speichere_bankkonto,
    speichere_kontakt,
    speichere_transaktion,
)
from accounti.models import (
    Bankkonto,
    Belegart,
    Kontakt,
    Transaktion,
    TransaktionQuelle,
)
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


# ---------------------------------------------------------------------------
# kontoauszuege
# ---------------------------------------------------------------------------


@pytest.fixture
def bank(tmp_path):
    url = f"sqlite:///{tmp_path / 'k.db'}"
    engine, make = session_factory(url)
    init_db(engine)
    with make() as s:
        speichere_bankkonto(
            s, Bankkonto(iban="DE89370400440532013000", bezeichnung="Giro")
        )
        for tag, betrag, konto in [
            (date(2025, 7, 3), "1190.00", "1200"),
            (date(2025, 7, 15), "-59.50", "1200"),
            (date(2025, 8, 5), "250.00", "1200"),
            (date(2025, 7, 9), "49.90", "1210"),
        ]:
            speichere_transaktion(
                s,
                Transaktion(
                    datum=tag,
                    betrag=Decimal(betrag),
                    verwendungszweck="Umsatz",
                    quelle=TransaktionQuelle.BANK,
                    rohtext="",
                    sachkonto=konto,
                ),
            )
        s.commit()
    aus = tmp_path / "aus"
    return make, aus, ["--db", url, "--config", str(tmp_path / "fehlt.yaml")]


def _auszug(basis, aus, *args):
    return runner.invoke(
        app, ["datev", "kontoauszuege", "--ausgabe", str(aus), *args, *basis]
    )


def test_kontoauszuege(bank):
    make, aus, basis = bank
    r = _auszug(basis, aus, "--period", "2025-07", "--anfangssaldo", "1.000,00")
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "Auszug 1/2025" in text and "2.130,50" in text
    mt = (aus / "MT940_1200_202507.sta").read_bytes().decode("ascii")
    assert ":25:37040044/532013000" in mt and ":28C:1/1" in mt
    r = _auszug(basis, aus, "--period", "2025-09", "--kontrollsaldo", "2380,50")
    assert r.exit_code == 0, r.output
    mt = (aus / "MT940_1200_202508-202509.sta").read_bytes().decode("ascii")
    assert ":28C:2/1" in mt and ":28C:3/1" in mt
    csv = (aus / "Saldenverlauf_1200_2025.csv").read_bytes().decode("cp1252")
    assert len(csv.strip().split("\r\n")) == 4  # Kopf + Juli, August, September
    assert "keine Befunde" in _text(r)
    with make() as s:
        assert [a.nummer for a in lade_kontoauszuege(s, "1200")] == [1, 2, 3]


def test_kontoauszuege_paypal(bank):
    _, aus, basis = bank
    r = _auszug(
        basis, aus, "--konto", "1210", "--period", "2025-07", "--anfangssaldo", "0"
    )
    assert r.exit_code == 0, r.output
    mt = (aus / "MT940_1210_202507.sta").read_bytes().decode("ascii")
    assert ":25:PPLXLULL/PAYPAL" in mt and "1190,00" not in mt  # nur PayPal
    assert ":61:2507090709C49,90NMSCNONREF" in mt
    assert ":62F:C250731EUR49,90" in mt


def test_kontoauszuege_ohne_anfangssaldo(bank):
    make, aus, basis = bank
    r = _auszug(basis, aus, "--period", "2025-07")
    assert r.exit_code == 1
    assert "--anfangssaldo" in _text(r)


def test_kontoauszuege_kontrollsaldo_falsch(bank):
    make, aus, basis = bank
    r = _auszug(
        basis,
        aus,
        "--period",
        "2025-07",
        "--anfangssaldo",
        "1000",
        "--kontrollsaldo",
        "2000",
    )
    assert r.exit_code == 1
    assert "Nichts festgeschrieben" in _text(r)
    with make() as s:
        assert lade_kontoauszuege(s) == []


def test_kontoauszuege_bei_kaputter_kette_keine_dateien(bank):
    """Hat die Prüfung der Auszugskette Befunde, wird kein MT940 geschrieben."""
    from sqlalchemy import update

    from accounti.db.tabellen import TransaktionRow

    make, aus, basis = bank
    r = _auszug(basis, aus, "--period", "2025-07", "--anfangssaldo", "1000")
    assert r.exit_code == 0, r.output
    mt = aus / "MT940_1200_202507.sta"
    mt.unlink()
    with make() as s:
        s.execute(
            update(TransaktionRow)
            .where(TransaktionRow.betrag == Decimal("-59.50"))
            .values(betrag=Decimal("-60.00"))
        )
        s.commit()
    r = _auszug(basis, aus, "--period", "2025-07")
    assert r.exit_code == 1
    text = _text(r)
    assert "Prüfung der Auszugskette" in text and "keine Dateien" in text
    assert not mt.exists()


def test_kontoauszuege_ohne_bankkonto(bank):
    _, aus, basis = bank
    r = _auszug(
        basis, aus, "--konto", "1230", "--period", "2025-07", "--anfangssaldo", "0"
    )
    assert r.exit_code == 1
    assert "--kontobezeichnung" in _text(r)
    r = _auszug(
        basis,
        aus,
        "--konto",
        "1230",
        "--period",
        "2025-07",
        "--anfangssaldo",
        "0",
        "--kontobezeichnung",
        "DE02120300000000202051",
    )
    assert r.exit_code == 0, r.output
