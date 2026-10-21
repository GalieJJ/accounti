"""CLI ``accounti nachfordern`` (Spec 4.2, Akzeptanz 4)."""

from datetime import date

from typer.testing import CliRunner

from accounti.bank.abgleichslauf import gleiche_belege_ab
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.erechnung.versand import SmtpVersand
from accounti.models import Belegart
from tests.pruefung_hilfe import anlegen, beleg, db_url, kurz, umsatz

runner = CliRunner()


def _run(*args):
    return runner.invoke(app, [str(a) for a in args], env={"COLUMNS": "250"})


def _umgebung(tmp_path, extra=""):
    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    config = tmp_path / "accounti.yaml"
    config.write_text("mandant:\n  name: Galerie Muster GmbH\n" + extra, "utf-8")
    return url, fabrik, str(config), engine


def test_akzeptanz_4_cli(tmp_path):
    url, fabrik, config, engine = _umgebung(tmp_path)
    tx = umsatz("-59.50", tag=date(2026, 8, 12), name="Shell Kiel")
    anlegen(fabrik, tx)
    basis = ["--db", url, "--config", config]
    r = _run("nachfordern", "--period", "2026-08", *basis)
    assert r.exit_code == 0, r.output
    assert "1 neu" in r.output and "Shell Kiel" in r.output
    r = _run("nachfordern", "--period", "2026-08", *basis)
    assert "0 neu" in r.output and "1 offen" in r.output  # idempotent
    r = _run("aufgaben", "liste", *basis)
    assert "Beleg fehlt" in r.output

    anlegen(
        fabrik,
        beleg(
            belegart=Belegart.QUITTUNG,
            nummer=None,
            lieferant="Shell Kiel",
            netto=None,
            steuer=None,
            brutto="59.50",
            positionen=[],
            tag=date(2026, 8, 12),
        ),
    )
    with fabrik() as s:
        gleiche_belege_ab(s)
        s.commit()
    r = _run("nachfordern", *basis)
    assert r.exit_code == 0, r.output
    assert "1 hinfällig" in r.output and "0 offen" in r.output
    engine.dispose()


def test_anfrage_entwurf_und_senden(tmp_path, monkeypatch):
    url, fabrik, config, engine = _umgebung(
        tmp_path,
        'versand:\n  absender: "Galerie <buchhaltung@galerie.example>"\n'
        "  smtp: {host: localhost, port: 2525, verschluesselung: keine}\n",
    )
    tx = umsatz("-59.50", tag=date(2026, 8, 12), name="Shell Kiel")
    anlegen(fabrik, tx)
    basis = ["--db", url, "--config", config]
    r = _run("nachfordern", "anfrage", kurz(tx.id), *basis)
    assert r.exit_code == 0, r.output
    assert "12.08.2026" in r.output and "nichts gesendet" in r.output
    r = _run("nachfordern", "anfrage", kurz(tx.id), *basis, "--senden")
    assert r.exit_code == 1 and "Kein Empfänger" in r.output

    gesendet = []
    monkeypatch.setattr(SmtpVersand, "sende", lambda self, n: gesendet.append(n))
    r = _run(
        "nachfordern",
        "anfrage",
        kurz(tx.id),
        *basis,
        "--an",
        "beleg@shell.example",
        "--senden",
        "--von",
        "jan",
    )
    assert r.exit_code == 0, r.output
    assert "gesendet" in r.output
    (nachricht,) = gesendet
    assert nachricht["To"] == "beleg@shell.example"
    assert "buchhaltung@galerie.example" in nachricht.get_content()
    r = _run("journal", "--vorgang", "beleg_angefordert", "--db", url)
    assert "jan" in r.output
    engine.dispose()


def test_senden_ohne_versand_und_unbekannter_umsatz(tmp_path):
    url, _, config, engine = _umgebung(tmp_path)
    basis = ["--db", url, "--config", config]
    r = _run("nachfordern", "anfrage", "ffffffff", *basis)
    assert r.exit_code == 1 and "nicht gefunden" in r.output
    r = _run("nachfordern", "anfrage", "ffffffff", *basis, "--senden")
    assert r.exit_code == 1 and "versand" in r.output
    assert "Traceback" not in r.output
    engine.dispose()
