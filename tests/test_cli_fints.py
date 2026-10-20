"""`accounti fints …` und Akzeptanzkriterium 1 mit der Attrappe der Bank."""

import pytest
from typer.testing import CliRunner

from accounti.bank import fints as fints_modul
from accounti.bank.tresor import neuer_schluessel
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_bankkonten
from accounti.models import KontoZustand
from tests.fints_attrappe import IBAN, AttrappenBank

runner = CliRunner()
SERVER = "https://fints.example.invalid/fints30"


def _text(ergebnis):
    return " ".join(ergebnis.output.split())


@pytest.fixture
def umgebung(tmp_path, monkeypatch):
    bank = AttrappenBank()
    monkeypatch.setattr(fints_modul, "erzeuge_client", bank.fabrik)
    monkeypatch.setenv("ACCOUNTI_SCHLUESSEL", neuer_schluessel())
    monkeypatch.setenv("ACCOUNTI_FINTS_PRODUKT_ID", "TESTPRODUKT0815")
    monkeypatch.chdir(tmp_path)  # keine config/accounti.yaml aus dem Projekt
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "accounti.yaml").write_text(
        "bank:\n  fints:\n    freigabe_intervall_sekunden: 0\n", encoding="utf-8"
    )
    return bank, f"sqlite:///{(tmp_path / 'f.db').as_posix()}"


def _run(*args, eingabe=None):
    return runner.invoke(app, list(args), input=eingabe)


def _konten(url):
    engine, make_session = session_factory(url)
    init_db(engine)
    with make_session() as s:
        konten = lade_bankkonten(s)
    engine.dispose()
    return konten


def _einrichten(url, eingabe):
    return _run(
        "fints",
        "einrichten",
        "--iban",
        "DE02 1203 0000 0000 2020 51",
        "--bezeichnung",
        "Giro Testbank",
        "--blz",
        "12030000",
        "--server",
        SERVER,
        "--db",
        url,
        eingabe=eingabe,
    )


def test_akzeptanz_1_abruf_ohne_weitere_eingabe_ausser_der_freigabe(umgebung, tmp_path):
    """Einmal einrichten (PIN, TAN-Verfahren, erste Freigabe) — danach holt
    `bank abrufen` ohne Eingabe; verlangt die Bank wieder eine Freigabe, wird das
    zum Zustand, und `fints freigeben` fragt nach der TAN."""
    bank, url = umgebung
    # Benutzerkennung, PIN, Wahl des TAN-Verfahrens (2 = mobileTAN), TAN
    r = _einrichten(url, "kunde-4711\n1234\n2\n123456\n")
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "Eingerichtet" in text and IBAN in text
    assert "mobileTAN" in text and "Bitte TAN eingeben" in text
    (konto,) = _konten(url)
    assert (konto.provider, konto.einstellungen["tan_verfahren"]) == ("fints", "942")
    assert "produkt_id" not in konto.einstellungen  # die ID bleibt in der Umgebung

    for erwartet in ("1 neu, 0 schon vorhanden", "0 neu, 1 schon vorhanden"):
        r = _run("bank", "abrufen", "--db", url)  # keine Eingabe vorhanden
        assert r.exit_code == 0, r.output
        assert erwartet in _text(r)
    assert bank.systeme == 1 and bank.tans == ["123456"]

    bank.freigegeben.clear()  # 180 Tage vorbei: die Bank will wieder eine SCA
    r = _run("bank", "abrufen", "--db", url)
    assert r.exit_code == 0, r.output
    assert "freigabe_noetig" in _text(r)
    assert "accounti fints freigeben" in _text(r)
    (konto,) = _konten(url)
    assert konto.zustand is KontoZustand.FREIGABE_NOETIG

    r = _run("fints", "freigeben", "--db", url, eingabe="123456\n")
    assert r.exit_code == 0, r.output
    assert "0 neu, 1 schon vorhanden" in _text(r)
    (konto,) = _konten(url)
    assert konto.zustand is KontoZustand.BEREIT
    r = _run("bank", "abrufen", "--db", url)
    assert "0 neu, 1 schon vorhanden" in _text(r)

    roh = (tmp_path / "f.db").read_bytes()
    assert b"kunde-4711" not in roh and b"TESTPRODUKT0815" not in roh


def test_einrichten_mit_app_freigabe(umgebung):
    bank, url = umgebung
    bank.sca_bei_init, bank.app_bestaetigt_nach = "app", 1
    bank.verfahren = {"921": "pushTAN 2.0"}
    r = _einrichten(url, "kunde-4711\n1234\n")
    assert r.exit_code == 0, r.output
    assert "App" in _text(r)
    (konto,) = _konten(url)
    assert konto.einstellungen["tan_verfahren"] == "921"


def test_einrichten_scheitert_ohne_konto_speichern(umgebung):
    bank, url = umgebung
    r = _einrichten(url, "kunde-4711\nfalsch\n2\n")
    assert r.exit_code == 1
    assert "PIN" in _text(r) and "falsch" not in _text(r).replace("falsch?", "")
    assert _konten(url) == []


def test_einrichten_ohne_produkt_id(umgebung, monkeypatch):
    _, url = umgebung
    monkeypatch.delenv("ACCOUNTI_FINTS_PRODUKT_ID")
    r = _einrichten(url, "kunde-4711\n1234\n2\n123456\n")
    assert r.exit_code == 1
    assert "Produkt-ID" in _text(r)
    assert _konten(url) == []


def test_einrichten_mit_produkt_id_am_konto(umgebung, monkeypatch):
    bank, url = umgebung
    monkeypatch.delenv("ACCOUNTI_FINTS_PRODUKT_ID")
    bank.verfahren = {"921": "pushTAN 2.0"}
    bank.sca_bei_init = None
    r = _run(
        "fints",
        "einrichten",
        "--iban",
        IBAN,
        "--bezeichnung",
        "Giro",
        "--blz",
        "12030000",
        "--server",
        SERVER,
        "--produkt-id",
        "AMKONTO1",
        "--format",
        "mt940",
        "--sachkonto",
        "1210",
        "--db",
        url,
        eingabe="kunde-4711\n1234\n",
    )
    assert r.exit_code == 0, r.output
    (konto,) = _konten(url)
    assert konto.einstellungen["produkt_id"] == "AMKONTO1"
    assert (konto.einstellungen["format"], konto.sachkonto) == ("mt940", "1210")
    assert bank.clients[-1]["produkt_id"] == "AMKONTO1"


def test_bank_verbinde_mit_fints_und_freigeben(umgebung):
    """Auch der allgemeine Weg über `bank verbinde` funktioniert."""
    bank, url = umgebung
    r = _run(
        "bank",
        "verbinde",
        "--provider",
        "fints",
        "--iban",
        IBAN,
        "--bezeichnung",
        "Giro",
        "--feld",
        "blz=12030000",
        "--feld",
        f"server={SERVER}",
        "--db",
        url,
        eingabe="kunde-4711\n1234\n",
    )
    assert r.exit_code == 0, r.output
    r = _run("bank", "abrufen", "--db", url)
    assert "freigabe_noetig" in _text(r)
    r = _run("fints", "freigeben", "--konto", IBAN, "--db", url, eingabe="\n")
    assert "abgebrochen" in _text(r)
    r = _run("fints", "freigeben", "--konto", IBAN, "--db", url, eingabe="123456\n")
    assert "1 neu" in _text(r)


def test_freigeben_ohne_fints_konten(umgebung):
    _, url = umgebung
    r = _run("fints", "freigeben", "--db", url)
    assert r.exit_code == 0
    assert "Keine FinTS-Konten" in _text(r)
    r = _run("fints", "freigeben", "--konto", "DE00", "--db", url)
    assert r.exit_code == 1


def test_akzeptanz_6_dateiimport_wenn_fints_ausfaellt(umgebung, tmp_path):
    """Fällt die Bank aus, bleibt der Dateiimport nutzbar — und was die Bank danach
    liefert, kommt nicht doppelt (Akzeptanz 2: gleicher Auszug, gleiche Schlüssel)."""
    from fints.exceptions import FinTSConnectionError

    from tests.fints_attrappe import DATEN

    bank, url = umgebung
    bank.sca_bei_init = None
    bank.verfahren = {"921": "pushTAN 2.0"}
    r = _run(
        "fints",
        "einrichten",
        "--iban",
        IBAN,
        "--bezeichnung",
        "Giro",
        "--blz",
        "12030000",
        "--server",
        SERVER,
        "--format",
        "mt940",
        "--db",
        url,
        eingabe="kunde-4711\n1234\n",
    )
    assert r.exit_code == 0, r.output
    bank.verbindung_weg = FinTSConnectionError("Bad status code 503")
    r = _run("bank", "abrufen", "--db", url)
    assert "fehler" in _text(r) and "nicht erreichbar" in _text(r)

    datei = tmp_path / "auszug.sta"
    datei.write_bytes((DATEN / "auszug.sta").read_bytes())
    r = _run("import", "bank", str(datei), "--konto", IBAN, "--db", url)
    assert r.exit_code == 0, r.output
    assert "6 Transaktionen importiert" in _text(r)

    bank.verbindung_weg = None
    r = _run("bank", "abrufen", "--db", url)
    assert "0 neu, 6 schon vorhanden" in _text(r)
