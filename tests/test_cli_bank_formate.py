"""MT940 und CAMT über die Kommandozeile — Akzeptanz 2 und 6 für die neuen Formate."""

from pathlib import Path

from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_transaktionen

runner = CliRunner()
DATEN = Path(__file__).parent / "daten" / "bank"


def _text(ergebnis):
    return " ".join(ergebnis.output.split())


def test_import_bank_mt940_zweimal_ohne_dubletten(tmp_path):
    url = f"sqlite:///{(tmp_path / 'f.db').as_posix()}"
    datei = tmp_path / "maerz.sta"
    datei.write_bytes((DATEN / "auszug.sta").read_bytes())
    r = runner.invoke(app, ["import", "bank", str(datei), "--db", url])
    assert r.exit_code == 0, r.output
    assert "6 Transaktionen importiert" in _text(r)
    r = runner.invoke(app, ["import", "bank", str(datei), "--db", url])
    assert "0 Transaktionen importiert, 6 Dubletten übersprungen" in _text(r)


def test_import_bank_camt_mit_festem_format(tmp_path):
    url = f"sqlite:///{(tmp_path / 'f.db').as_posix()}"
    datei = tmp_path / "auszug.xml"
    datei.write_bytes((DATEN / "camt053_v08.xml").read_bytes())
    r = runner.invoke(
        app, ["import", "bank", str(datei), "--format", "camt", "--db", url]
    )
    assert r.exit_code == 0, r.output
    engine, make_session = session_factory(url)
    init_db(engine)
    with make_session() as s:
        betraege = sorted(str(t.betrag) for t in lade_transaktionen(s))
    engine.dispose()
    # zwei gleiche Parkgebühren mit verschiedener Bankreferenz bleiben zwei
    assert betraege == ["-5.00", "-5.00", "-59.50", "1190.00"]


def test_formate_werden_aufgelistet():
    r = runner.invoke(app, ["import", "banken"])
    assert r.exit_code == 0, r.output
    assert "mt940" in r.output and "camt" in r.output


def _konto_anlegen(url, iban):
    r = runner.invoke(
        app,
        [
            "bank",
            "verbinde",
            "--provider",
            "datei",
            "--iban",
            iban,
            "--bezeichnung",
            "Konto",
            "--feld",
            "ordner=.",
            "--db",
            url,
        ],
    )
    assert r.exit_code == 0, r.output


def test_import_bank_mit_konto_nimmt_nur_dessen_auszuege(tmp_path):
    """Ein Export mehrerer Konten oder eine falsche Datei: fremde Umsätze bekämen
    sonst das Sachkonto des genannten Kontos."""
    url = f"sqlite:///{(tmp_path / 'f.db').as_posix()}"
    _konto_anlegen(url, "DE44500105175407324931")
    falsch = tmp_path / "giro.xml"
    falsch.write_bytes((DATEN / "camt053_v08.xml").read_bytes())
    r = runner.invoke(
        app,
        [
            "import",
            "bank",
            str(falsch),
            "--konto",
            "DE44500105175407324931",
            "--db",
            url,
        ],
    )
    assert r.exit_code == 1
    assert "DE02120300000000202051" in _text(r) and "Traceback" not in r.output

    beide = tmp_path / "beide.xml"
    v08 = (DATEN / "camt053_v08.xml").read_text(encoding="utf-8")
    v02 = (DATEN / "camt053_v02.xml").read_text(encoding="utf-8")
    stmt_v02 = v02[v02.index("<Stmt>") : v02.index("</Stmt>") + len("</Stmt>")]
    beide.write_text(v08.replace("</Stmt>", "</Stmt>" + stmt_v02, 1), encoding="utf-8")
    r = runner.invoke(
        app,
        [
            "import",
            "bank",
            str(beide),
            "--konto",
            "DE44500105175407324931",
            "--db",
            url,
        ],
    )
    assert r.exit_code == 0, r.output
    assert "3 Transaktionen importiert" in _text(r)
    r = runner.invoke(app, ["import", "bank", str(beide), "--db", url])
    assert r.exit_code == 1
    assert "mehrerer Konten" in _text(r) and "--konto" in _text(r)


def test_import_bank_mit_kaputtem_saldo_ohne_traceback(tmp_path):
    url = f"sqlite:///{(tmp_path / 'f.db').as_posix()}"
    kaputt = tmp_path / "kaputt.sta"
    kaputt.write_bytes(
        (DATEN / "auszug.sta").read_bytes().replace(b"2167,10", b"2167,11")
    )
    r = runner.invoke(app, ["import", "bank", str(kaputt), "--db", url])
    assert r.exit_code == 1
    assert "Saldo" in _text(r) and "geht nicht auf" in _text(r)
    assert r.exception is None or isinstance(r.exception, SystemExit)
