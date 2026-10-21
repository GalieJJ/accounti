"""Freigaben in der CLI an Rollen gebunden (Akzeptanz 3) — ohne Benutzer wie bisher."""

from datetime import datetime

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import session_factory
from accounti.models.auth import Rolle
from tests import test_cli_ustva as ustva
from tests import test_cli_zahlung as zahlung
from tests.auth_hilfe import (
    billige_hashes,
    lege_person_an,
    setze_schluessel,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def schluessel(monkeypatch):
    return setze_schluessel(monkeypatch)


@pytest.fixture(autouse=True)
def umgebung_sauber(tmp_path, monkeypatch, schluessel):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)


def personen(url):
    engine, fabrik = session_factory(url)
    jetzt = datetime.now()
    with fabrik() as s:
        p = {
            "jan": lege_person_an(s, "jan", Rolle.BETRACHTER, jetzt=jetzt),
            "eva": lege_person_an(s, "eva", Rolle.BUCHHALTER, jetzt=jetzt),
            "chef": lege_person_an(s, "chef", Rolle.FREIGEBER, jetzt=jetzt),
        }
    engine.dispose()
    return p


def zahlungslauf(tmp_path):
    url, config = zahlung._umgebung(tmp_path)
    basis = ["--db", url, "--config", config]
    r = runner.invoke(app, ["zahlung", "anlegen", *basis, "--von", "eva"])
    assert r.exit_code == 0, r.output
    return url, basis


def test_akzeptanz_3_zahlungslauf_nur_durch_freigeber(tmp_path, monkeypatch):
    url, basis = zahlungslauf(tmp_path)
    p = personen(url)
    for wer in ("jan", "eva"):  # betrachter, buchhalter
        r = runner.invoke(app, ["zahlung", "freigeben", "1", *basis, "--von", wer])
        assert r.exit_code == 1, r.output
        assert f"{wer} darf" in r.output and "Zahlungsläufe freigeben" in r.output
    r = runner.invoke(app, ["zahlung", "zeigen", "1", *basis])
    assert "entwurf" in r.output.lower()
    # der Freigeber mit Einmalcode
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].code(datetime.now()))
    r = runner.invoke(app, ["zahlung", "freigeben", "1", *basis, "--von", "chef"])
    assert r.exit_code == 0, r.output
    assert "Lauf 1 freigegeben" in r.output


def test_freigeber_ohne_richtigen_code_scheitert(tmp_path):
    url, basis = zahlungslauf(tmp_path)
    personen(url)
    r = runner.invoke(
        app, ["zahlung", "freigeben", "1", *basis, "--von", "chef"], input="000000\n"
    )
    assert r.exit_code == 1
    assert "Einmalcode falsch" in r.output


def test_einmalcode_wird_abgefragt(tmp_path):
    url, basis = zahlungslauf(tmp_path)
    p = personen(url)
    r = runner.invoke(
        app,
        ["zahlung", "freigeben", "1", *basis, "--von", "chef"],
        input=p["chef"].code(datetime.now()) + "\n",
    )
    assert r.exit_code == 0, r.output
    assert "Einmalcode für chef" in r.output


def test_akzeptanz_3_ustva_nur_durch_freigeber(tmp_path, monkeypatch):
    url, konfig = ustva.umgebung(tmp_path)
    p = personen(url)
    basis = ["--period", "2026-08", "--db", url, "--config", konfig]
    for wer in ("jan", "eva"):
        r = runner.invoke(app, ["ustva", "freigeben", *basis, "--von", wer])
        assert r.exit_code == 1, r.output
        assert "Steuermeldungen freigeben" in r.output
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].code(datetime.now()))
    r = runner.invoke(app, ["ustva", "freigeben", *basis, "--von", "chef"])
    assert r.exit_code == 0, r.output
    assert "Freigegeben von chef" in ustva.text(r)


def test_dauerfrist_freigabe_nur_durch_freigeber(tmp_path):
    url, konfig = ustva.umgebung(tmp_path)
    personen(url)
    r = runner.invoke(
        app,
        ["ustva", "dauerfrist", "--jahr", "2026", "--summe-vorjahr", "11000"]
        + ["--svz-vorjahr", "0", "--freigeben", "--von", "eva"]
        + ["--db", url, "--config", konfig],
    )
    assert r.exit_code == 1, r.output
    assert "eva darf" in r.output


def test_ohne_benutzer_wie_bisher(tmp_path):
    _, basis = zahlungslauf(tmp_path)
    r = runner.invoke(app, ["zahlung", "freigeben", "1", *basis, "--von", "jan"])
    assert r.exit_code == 0, r.output


def test_vier_augen_wer_anlegt_gibt_nicht_frei(tmp_path, monkeypatch):
    """Befund B-M10: ``zahlung anlegen`` braucht das Recht buchen (mit Einmalcode,
    der Ersteller ist der angemeldete Benutzer), und wer anlegt, gibt nicht frei."""
    from accounti.auth.dienst import fuege_rolle_hinzu
    from accounti.db.repo_auth import lade_benutzer

    url, config = zahlung._umgebung(tmp_path)
    basis = ["--db", url, "--config", config]
    p = personen(url)
    for wer in ("jan", "chef"):  # betrachter, freigeber: kein Recht buchen
        r = runner.invoke(app, ["zahlung", "anlegen", *basis, "--von", wer])
        assert r.exit_code == 1, r.output
        assert f"{wer} darf" in r.output and "buchen" in r.output
    r = runner.invoke(
        app, ["zahlung", "anlegen", *basis, "--von", "eva"], input="000000\n"
    )
    assert r.exit_code == 1 and "Einmalcode falsch" in r.output
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = runner.invoke(app, ["zahlung", "anlegen", *basis, "--von", "eva"])
    assert r.exit_code == 0, r.output
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        fuege_rolle_hinzu(
            s, lade_benutzer(s, "eva"), "standard", Rolle.FREIGEBER, None, "t"
        )
        s.commit()
    engine.dispose()
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = runner.invoke(app, ["zahlung", "freigeben", "1", *basis, "--von", "eva"])
    assert r.exit_code == 1, r.output
    assert "angelegt" in r.output
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["chef"].codes.pop())
    r = runner.invoke(app, ["zahlung", "freigeben", "1", *basis, "--von", "chef"])
    assert r.exit_code == 0, r.output


def test_ersteller_darf_freigeben_wenn_bewusst_eingestellt(tmp_path, monkeypatch):
    """Kleine Firma: ``zahlung.ersteller_darf_freigeben: true`` hebt sie auf."""
    from pathlib import Path

    from accounti.auth.dienst import fuege_rolle_hinzu
    from accounti.db.repo_auth import lade_benutzer

    url, config = zahlung._umgebung(tmp_path)
    Path(config).write_text(
        Path(config).read_text(encoding="utf-8")
        + "zahlung:\n  ersteller_darf_freigeben: true\n",
        encoding="utf-8",
    )
    basis = ["--db", url, "--config", config]
    p = personen(url)
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        fuege_rolle_hinzu(
            s, lade_benutzer(s, "eva"), "standard", Rolle.FREIGEBER, None, "t"
        )
        s.commit()
    engine.dispose()
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    assert (
        runner.invoke(app, ["zahlung", "anlegen", *basis, "--von", "eva"]).exit_code
        == 0
    )
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = runner.invoke(app, ["zahlung", "freigeben", "1", *basis, "--von", "eva"])
    assert r.exit_code == 0, r.output


def test_anlagen_freigeben_nur_mit_rolle(tmp_path, monkeypatch):
    """Befund B-M12: die AfA-Freigabe ist eine Buchungsfreigabe — Rolle und
    Einmalcode, freigebende Person ist der Benutzer, nicht ``--von``-Freitext."""
    url = f"sqlite:///{(tmp_path / 'anlagen.db').as_posix()}"
    config = str(tmp_path / "anlagen.yaml")
    basis = ["--db", url, "--config", config]

    def anlagen(*args, **kw):
        return runner.invoke(app, ["anlagen", *args, *basis], **kw)

    r = anlagen(
        "anlegen", "--bezeichnung", "Schreibtisch", "--datum", "15.09.2026",
        "--kosten", "3.600,00", "--nutzungsdauer", "3", "--konto", "0420",
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    assert anlagen("afa", "--jahr", "2026").exit_code == 0
    p = personen(url)
    r = anlagen("freigeben", "--jahr", "2026", "--von", "jan")
    assert r.exit_code == 1 and "jan darf" in r.output
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "eva")
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", p["eva"].codes.pop())
    r = anlagen("freigeben", "--jahr", "2026")
    assert r.exit_code == 0, r.output
    assert "1 AfA-Buchung freigegeben" in " ".join(r.output.split())
    engine, fabrik = session_factory(url)
    from sqlalchemy import text

    with fabrik() as s:
        geprueft = set(
            s.execute(
                text(
                    "SELECT geprueft_von FROM buchungssaetze "
                    "WHERE geprueft_von IS NOT NULL"
                )
            ).scalars()
        )
    engine.dispose()
    assert geprueft == {"eva"}
