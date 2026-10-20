import base64

import pytest
from typer.testing import CliRunner

from accounti.bank.provider import BANK_PROVIDER
from accounti.bank.tresor import neuer_schluessel
from accounti.cli import app
from tests.test_bank_lauf import Attrappe
from tests.test_cli_opos import KOPF

runner = CliRunner()
ZEILEN = [
    "DE12;13.03.26;13.03.26;KARTENZAHLUNG;PARKHAUS ALTSTADT;APCOA;;;-5,00;EUR;gebucht",
    "DE12;13.03.26;13.03.26;KARTENZAHLUNG;PARKHAUS ALTSTADT;APCOA;;;-5,00;EUR;gebucht",
    "DE12;15.03.26;15.03.26;ENTGELT;Kontoführung März;Sparkasse;;;-5,90;EUR;gebucht",
]


def _text(ergebnis):
    return " ".join(ergebnis.output.split())


def _run(*args, **kw):
    return runner.invoke(app, list(args), **kw)


@pytest.fixture
def umgebung(tmp_path):
    url = f"sqlite:///{(tmp_path / 'k.db').as_posix()}"
    auszuege = tmp_path / "auszuege"
    auszuege.mkdir()
    (auszuege / "maerz.csv").write_text("\n".join([KOPF, *ZEILEN]) + "\n", "utf-8")
    return url, auszuege


def _verbinde_datei(url, auszuege):
    return _run(
        "bank",
        "verbinde",
        "--provider",
        "datei",
        "--iban",
        "DE12 3456 7890 1234 5678 90",
        "--bezeichnung",
        "Giro Sparkasse",
        "--feld",
        f"ordner={auszuege}",
        "--db",
        url,
    )


def test_schluessel():
    r = _run("bank", "schluessel")
    assert r.exit_code == 0, r.output
    zeile = next(z for z in r.output.splitlines() if "ACCOUNTI_SCHLUESSEL=" in z)
    wert = zeile.split("ACCOUNTI_SCHLUESSEL=")[1].strip()
    assert len(base64.urlsafe_b64decode(wert)) == 32


def test_datei_konto_einrichten_abrufen_und_nichts_doppelt(umgebung):
    url, auszuege = umgebung
    r = _verbinde_datei(url, auszuege)
    assert r.exit_code == 0, r.output
    assert "DE12345678901234567890" in _text(r)

    r = _run("bank", "abrufen", "--db", url)
    assert r.exit_code == 0, r.output
    assert "3 neu" in _text(r)
    r = _run("bank", "abrufen", "--db", url)
    assert "0 neu" in _text(r) and "3 schon vorhanden" in _text(r)

    r = _run("bank", "konten", "--db", url)
    assert r.exit_code == 0, r.output
    assert all(w in _text(r) for w in ("Giro", "Sparkasse", "15.03.2026"))
    assert "bereit" in _text(r)


def test_konto_doppelt_einrichten(umgebung):
    url, auszuege = umgebung
    _verbinde_datei(url, auszuege)
    r = _verbinde_datei(url, auszuege)
    assert r.exit_code == 1
    assert "schon eingerichtet" in _text(r)


def test_unbekannte_einstellung_und_provider(umgebung):
    url, _ = umgebung
    r = _run(
        "bank", "verbinde", "--provider", "datei", "--iban", "DE1", "--bezeichnung",
        "x", "--feld", "pin=1", "--db", url,
    )  # fmt: skip
    assert r.exit_code == 1 and "pin" in _text(r)
    r = _run(
        "bank", "verbinde", "--provider", "gibtsnicht", "--iban", "DE1",
        "--bezeichnung", "x", "--db", url,
    )  # fmt: skip
    assert r.exit_code == 1 and "datei" in _text(r)


@pytest.fixture
def attrappe():
    BANK_PROVIDER["attrappe"] = Attrappe
    Attrappe.antworten, Attrappe.gesehen = {}, []
    yield
    del BANK_PROVIDER["attrappe"]


def test_geheime_felder_werden_verschluesselt(
    umgebung, attrappe, monkeypatch, tmp_path
):
    url, _ = umgebung
    monkeypatch.setenv("ACCOUNTI_SCHLUESSEL", neuer_schluessel())
    r = _run(
        "bank", "verbinde", "--provider", "attrappe", "--iban", "DE99",
        "--bezeichnung", "Testbank", "--feld", "bank=Test", "--db", url,
        input="ganz-geheime-pin\n",
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    assert "ganz-geheime-pin" not in r.output
    assert b"ganz-geheime-pin" not in (tmp_path / "k.db").read_bytes()

    from accounti.bank.provider import Abruf

    Attrappe.antworten["DE99"] = Abruf([])
    assert _run("bank", "abrufen", "--db", url).exit_code == 0
    assert Attrappe.gesehen == [("DE99", {"pin": "ganz-geheime-pin"}, None)]


def test_geheime_felder_ohne_schluessel(umgebung, attrappe, monkeypatch):
    url, _ = umgebung
    monkeypatch.delenv("ACCOUNTI_SCHLUESSEL", raising=False)
    r = _run(
        "bank", "verbinde", "--provider", "attrappe", "--iban", "DE99",
        "--bezeichnung", "Testbank", "--db", url, input="x\n",
    )  # fmt: skip
    assert r.exit_code == 1
    assert "ACCOUNTI_SCHLUESSEL" in _text(r)


def test_import_bank_zweimal_ergibt_keine_dubletten(umgebung):
    url, auszuege = umgebung
    datei = str(auszuege / "maerz.csv")
    r = _run("import", "bank", datei, "--db", url, "--format", "sparkasse")
    assert "3 Transaktionen importiert" in _text(r)
    r = _run("import", "bank", datei, "--db", url, "--format", "sparkasse")
    assert r.exit_code == 0, r.output
    assert "0 Transaktionen importiert" in _text(r) and "3 Dubletten" in _text(r)


def test_import_bank_einem_konto_zuordnen(umgebung):
    url, auszuege = umgebung
    _verbinde_datei(url, auszuege)
    datei = str(auszuege / "maerz.csv")
    r = _run("import", "bank", datei, "--db", url, "--konto", "DE12345678901234567890")
    assert "3 Transaktionen importiert" in _text(r)
    # derselbe Umsatz über den Provider: schon da
    assert "0 neu" in _text(_run("bank", "abrufen", "--db", url))
    r = _run("import", "bank", datei, "--db", url, "--konto", "DE00")
    assert r.exit_code == 1 and "Kein Bankkonto" in _text(r)


def test_bank_lauf(umgebung, tmp_path):
    url, auszuege = umgebung
    _verbinde_datei(url, auszuege)
    r = _run(
        "bank", "lauf", "--db", url, "--no-llm", "--config", str(tmp_path / "x.yaml")
    )
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "3 neu" in text
    assert "kontiert" in text and "abgeglichen" in text and "ausgeglichen" in text
    zweiter = _text(
        _run("bank", "lauf", "--db", url, "--no-llm", "--config", str(tmp_path / "x"))
    )
    assert "0 neu" in zweiter and "0 kontiert" in zweiter
