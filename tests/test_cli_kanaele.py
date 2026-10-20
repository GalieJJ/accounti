import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from accounti.bank.tresor import neuer_schluessel
from accounti.cli import app
from accounti.db import session_factory
from accounti.db.repo_kanaele import lade_kanal_zugang
from tests.http_attrappe import HttpAttrappe, datei_antwort, json_antwort
from tests.imap_attrappe import ImapAttrappe, Postfach
from tests.pdf_hilfe import pdf_mit_text
from tests.test_kanaele_email import mail

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "belege"
RECHNUNG = (FIXTURES / "rechnung_zwei_steuersaetze.txt").read_text(encoding="utf-8")

runner = CliRunner()


@pytest.fixture(autouse=True)
def _breite_konsole(monkeypatch):
    """Rich bricht sonst bei 80 Zeichen um — Meldungen bleiben am Stück."""
    monkeypatch.setenv("COLUMNS", "250")


def _db(tmp_path):
    return f"sqlite:///{(tmp_path / 'a.db').as_posix()}"


def _args(tmp_path):
    return ["--db", _db(tmp_path), "--archiv", str(tmp_path / "archiv")]


def _konfig(tmp_path, port, passwort_zeile='passwort: "${ACCOUNTI_TEST_IMAP}"'):
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(
        f"""
belegkanaele:
  email:
    - name: rechnungen
      host: 127.0.0.1
      port: {port}
      verschluesselung: keine
      benutzer: belege@firma.example
      {passwort_zeile}
""",
        encoding="utf-8",
    )
    return str(pfad)


@pytest.fixture
def postfach():
    pf = Postfach()
    pf.lege_ab(mail(("Rechnung.pdf", pdf_mit_text(RECHNUNG), "application/pdf")))
    pf.lege_ab(mail(("vertrag.zip", b"PK\x03\x04", "application/zip"),
                    message_id="<zip@x>", betreff="Vertrag"))  # fmt: skip
    return pf


def _abholen(tmp_path, konfig, *weitere):
    return runner.invoke(
        app,
        [
            "belege",
            "abholen",
            "--kanal",
            "email",
            "--config",
            konfig,
            *weitere,
            *_args(tmp_path),
        ],
    )


def test_belege_kanaele_listet_email():
    r = runner.invoke(app, ["belege", "kanaele"])
    assert r.exit_code == 0
    assert "email" in r.output


def test_pdf_per_email_wird_erfasst(tmp_path, postfach, monkeypatch):
    """Akzeptanz 1 über den E-Mail-Kanal, Ende-zu-Ende über die CLI."""
    monkeypatch.setenv("ACCOUNTI_TEST_IMAP", "geheim")
    with ImapAttrappe(postfach) as server:
        konfig = _konfig(tmp_path, server.port)
        r = _abholen(tmp_path, konfig)
        assert r.exit_code == 0, r.output
        assert "E-Mail rechnungen" in r.output
        assert "1 neu" in r.output
        assert "Hinweis" in r.output
        assert "vertrag.zip" in r.output
        zweit = _abholen(tmp_path, konfig)
    assert zweit.exit_code == 0, zweit.output
    assert "0 neu" in zweit.output
    liste = runner.invoke(app, ["belege", "liste", "--db", _db(tmp_path)])
    assert "172.50" in liste.output
    assert "erfasst" in liste.output
    nachrichten = runner.invoke(
        app, ["kanaele", "nachrichten", "--db", _db(tmp_path), "--kanal", "email"]
    )
    assert nachrichten.exit_code == 0, nachrichten.output
    assert "rechnung@mueller.example" in nachrichten.output
    assert "Bürobedarf Müller GmbH" in nachrichten.output


def test_ohne_postfach_unbekannte_quelle_und_webhook(tmp_path):
    leer = tmp_path / "leer.yaml"
    leer.write_text("mandant:\n  name: X\n", encoding="utf-8")
    r = _abholen(tmp_path, str(leer))
    assert r.exit_code == 1
    assert "Kein Postfach" in r.output
    r = _abholen(tmp_path, _konfig(tmp_path, 1), "--quelle", "anders")
    assert r.exit_code == 1
    assert "nicht konfiguriert" in r.output
    r = runner.invoke(
        app, ["belege", "abholen", "--kanal", "webhook", *_args(tmp_path)]
    )
    assert r.exit_code == 1
    assert "kanaele webhook starten" in r.output
    neu = tmp_path / "neu"
    neu.mkdir()
    r = runner.invoke(app, ["belege", "abholen", "--kanal", "fax", *_args(neu)])
    assert r.exit_code == 1
    assert "ordner, email, connector" in r.output
    assert not (neu / "a.db").exists()  # keine Datenbank für einen Tippfehler


def test_verbindungsfehler_und_fehlende_variable_enden_mit_exit_1(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("ACCOUNTI_TEST_IMAP", raising=False)
    with ImapAttrappe(Postfach()) as server:
        port = server.port
    r = _abholen(tmp_path, _konfig(tmp_path, port))
    assert r.exit_code == 1
    assert "ACCOUNTI_TEST_IMAP" in r.output
    monkeypatch.setenv("ACCOUNTI_TEST_IMAP", "geheim")
    r = _abholen(tmp_path, _konfig(tmp_path, port))
    assert r.exit_code == 1
    assert "Verbindung" in r.output


def test_passwort_im_klartext_wird_abgelehnt(tmp_path):
    r = _abholen(tmp_path, _konfig(tmp_path, 1, 'passwort: "geheim"'))
    assert r.exit_code == 1
    assert "Klartext" in r.output


def test_zugang_im_tresor_und_abholen_damit(tmp_path, postfach, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_SCHLUESSEL", neuer_schluessel())
    with ImapAttrappe(postfach) as server:
        konfig = _konfig(tmp_path, server.port, passwort_zeile="")
        ohne = _abholen(tmp_path, konfig)
        assert ohne.exit_code == 1
        assert "kanaele zugang email rechnungen" in ohne.output
        r = runner.invoke(
            app,
            [
                "kanaele",
                "zugang",
                "email",
                "rechnungen",
                "--config",
                konfig,
                "--db",
                _db(tmp_path),
            ],
            input="geheim\n",
        )
        assert r.exit_code == 0, r.output
        assert "verschlüsselt" in r.output
        assert "geheim" not in r.output.replace("Passwort:", "")
        mit = _abholen(tmp_path, konfig, "--ohne-erkennung")
    assert mit.exit_code == 0, mit.output
    assert "1 neu" in mit.output
    _, make_session = session_factory(_db(tmp_path))
    with make_session() as s:
        z = lade_kanal_zugang(s, "email", "rechnungen")
    assert z is not None
    assert "geheim" not in z.chiffrat


def test_zugang_fuer_unbekanntes_postfach_oder_ohne_schluessel(tmp_path, monkeypatch):
    konfig = _konfig(tmp_path, 1)
    monkeypatch.setenv("ACCOUNTI_SCHLUESSEL", neuer_schluessel())
    r = runner.invoke(
        app,
        ["kanaele", "zugang", "email", "anders", "--config", konfig],
        input="x\n",
    )
    assert r.exit_code == 1
    assert "nicht konfiguriert" in r.output
    monkeypatch.delenv("ACCOUNTI_SCHLUESSEL")
    r = runner.invoke(
        app,
        ["kanaele", "zugang", "email", "rechnungen", "--config", konfig],
        input="x\n",
    )
    assert r.exit_code == 1
    assert "ACCOUNTI_SCHLUESSEL" in r.output
    r = runner.invoke(app, ["kanaele", "zugang", "fax", "x", "--config", konfig])
    assert r.exit_code == 1


def test_nachrichten_ohne_eintraege(tmp_path):
    r = runner.invoke(app, ["kanaele", "nachrichten", "--db", _db(tmp_path)])
    assert r.exit_code == 0
    assert "Keine" in r.output


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


def test_webhook_token_tokens_widerrufen(tmp_path):
    db = ["--db", _db(tmp_path)]
    r = runner.invoke(app, ["kanaele", "webhook", "token", "n8n", *db])
    assert r.exit_code == 0, r.output
    (token,) = re.findall(r"accounti_wh_[A-Za-z0-9_-]+", r.output)
    doppelt = runner.invoke(app, ["kanaele", "webhook", "token", "n8n", *db])
    assert doppelt.exit_code == 1
    liste = runner.invoke(app, ["kanaele", "webhook", "tokens", *db])
    assert "n8n" in liste.output
    assert "aktiv" in liste.output
    assert token not in liste.output
    r = runner.invoke(app, ["kanaele", "webhook", "widerrufen", "n8n", *db])
    assert r.exit_code == 0
    liste = runner.invoke(app, ["kanaele", "webhook", "tokens", *db])
    assert "widerrufen" in liste.output
    r = runner.invoke(app, ["kanaele", "webhook", "widerrufen", "gibtsnicht", *db])
    assert r.exit_code == 1


def test_webhook_starten_uebergibt_app_an_uvicorn(tmp_path, monkeypatch):
    import uvicorn
    from fastapi.testclient import TestClient

    gestartet = {}
    monkeypatch.setattr(
        uvicorn, "run", lambda app, **kw: gestartet.update(app=app, **kw)
    )
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text("belegkanaele:\n  webhook:\n    port: 9123\n", encoding="utf-8")
    db = ["--db", _db(tmp_path)]
    r = runner.invoke(
        app,
        [
            "kanaele",
            "webhook",
            "starten",
            "--config",
            str(konfig),
            "--archiv",
            str(tmp_path / "archiv"),
            "--ohne-erkennung",
            *db,
        ],
    )
    assert r.exit_code == 0, r.output
    assert "kein aktives Token" in r.output
    assert (gestartet["host"], gestartet["port"]) == ("127.0.0.1", 9123)
    neu = runner.invoke(app, ["kanaele", "webhook", "token", "erp", *db])
    (token,) = re.findall(r"accounti_wh_[A-Za-z0-9_-]+", neu.output)
    antwort = TestClient(gestartet["app"]).post(
        "/belege",
        content=pdf_mit_text(RECHNUNG),
        headers={"Authorization": f"Bearer {token}", "X-Dateiname": "r.pdf"},
    )
    assert antwort.status_code == 200, antwort.text
    liste = runner.invoke(app, ["belege", "liste", "--db", _db(tmp_path)])
    assert "r.pdf" in liste.output
    r = runner.invoke(
        app,
        [
            "kanaele",
            "webhook",
            "starten",
            "--port",
            "9999",
            "--config",
            str(tmp_path / "fehlt.yaml"),
            *db,
        ],
    )
    assert r.exit_code == 0, r.output
    assert gestartet["port"] == 9999


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


def _connector_konfig(tmp_path, url, kopf='Authorization: "Bearer {zugang}"'):
    pfad = tmp_path / "connector.yaml"
    pfad.write_text(
        f"""
belegkanaele:
  connectoren:
    - name: portal
      typ: json
      basis_url: {url}/api
      kopfzeilen:
        {kopf}
      liste:
        pfad: /dokumente
        eintraege: records
      felder:
        id: id
        dateiname: name
        absender: lieferant
      datei:
        pfad: /dokumente/{{id}}/datei
""",
        encoding="utf-8",
    )
    return str(pfad)


def _abholen_connector(tmp_path, konfig):
    return runner.invoke(
        app,
        [
            "belege",
            "abholen",
            "--kanal",
            "connector",
            "--config",
            konfig,
            *_args(tmp_path),
        ],
    )


def test_connector_ende_zu_ende(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_SCHLUESSEL", neuer_schluessel())
    routen = {
        "/api/dokumente": lambda a: json_antwort(
            {"records": [{"id": 42, "name": "re-42.pdf", "lieferant": "Müller"}]}
        ),
        "/api/dokumente/42/datei": lambda a: datei_antwort(pdf_mit_text(RECHNUNG)),
    }
    with HttpAttrappe(routen) as server:
        konfig = _connector_konfig(tmp_path, server.url)
        pruefen = runner.invoke(app, ["kanaele", "connectoren", "--config", konfig])
        assert pruefen.exit_code == 0, pruefen.output
        assert "json" in pruefen.output
        assert "portal (json): in Ordnung" in pruefen.output
        ohne = _abholen_connector(tmp_path, konfig)
        assert ohne.exit_code == 1
        assert "kanaele zugang connector portal" in ohne.output
        r = runner.invoke(
            app,
            [
                "kanaele",
                "zugang",
                "connector",
                "portal",
                "--config",
                konfig,
                "--db",
                _db(tmp_path),
            ],
            input="portal-token\n",
        )
        assert r.exit_code == 0, r.output
        r = _abholen_connector(tmp_path, konfig)
        assert r.exit_code == 0, r.output
        assert "Connector portal (json)" in r.output
        assert "1 neu" in r.output
        assert server.anfragen[-1].kopfzeilen["authorization"] == "Bearer portal-token"
        zweit = _abholen_connector(tmp_path, konfig)
        assert "0 neu" in zweit.output
    liste = runner.invoke(app, ["belege", "liste", "--db", _db(tmp_path)])
    assert "re-42.pdf" in liste.output
    assert "172.50" in liste.output
    nachrichten = runner.invoke(
        app, ["kanaele", "nachrichten", "--kanal", "connector", "--db", _db(tmp_path)]
    )
    assert "Müller" in nachrichten.output


def test_connectoren_meldet_fehlerhafte_konfiguration(tmp_path):
    konfig = _connector_konfig(tmp_path, "http://portal.example", 'X-API-KEY: "abc"')
    r = runner.invoke(app, ["kanaele", "connectoren", "--config", konfig])
    assert r.exit_code == 1
    assert "https" in r.output
    assert _abholen_connector(tmp_path, konfig).exit_code == 1
    leer = tmp_path / "leer.yaml"
    leer.write_text("", encoding="utf-8")
    r = runner.invoke(app, ["kanaele", "connectoren", "--config", str(leer)])
    assert r.exit_code == 0
    assert "Kein Connector" in r.output
    r = _abholen_connector(tmp_path, str(leer))
    assert r.exit_code == 1
    assert "Kein Connector" in r.output
