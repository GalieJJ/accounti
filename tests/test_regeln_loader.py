from pathlib import Path

import pytest

from accounti.klassifikation.regeln_loader import lade_regeln
from accounti.konfiguration import KonfigurationError
from accounti.models import Transaktion, TransaktionQuelle


def _tx(zweck: str) -> Transaktion:
    return Transaktion(
        datum="2026-04-10",
        betrag="-39.99",
        verwendungszweck=zweck,
        quelle=TransaktionQuelle.BANK,
        rohtext=zweck,
    )


def test_laedt_regeln_aus_yaml(tmp_path: Path):
    yaml_datei = tmp_path / "regeln.yaml"
    yaml_datei.write_text(
        "- name: telekom\n"
        "  muster: 'TELEKOM'\n"
        "  feld: verwendungszweck\n"
        "  soll_konto: '4920'\n"
        "  haben_konto: '1200'\n"
        "  steuer_schluessel: 9\n"
        "  buchungstext: 'Telefon/Internet'\n",
        encoding="utf-8",
    )
    regeln = lade_regeln(yaml_datei)
    assert len(regeln) == 1
    assert regeln[0].passt(_tx("TELEKOM MOBILFUNK APRIL")) is True


def test_fehlende_datei_gibt_leere_liste(tmp_path: Path):
    assert lade_regeln(tmp_path / "gibtsnicht.yaml") == []


# --- Gesamttest 10b-1 nach dem Merge, gw-regeln N-2 ----------------------------------


@pytest.mark.parametrize(
    ("inhalt", "erwartet"),
    [
        (
            "- name: telekom\n  muster: '(telekom'\n  soll_konto: '4920'\n"
            "  haben_konto: '1200'\n",
            "Regel telekom: Muster ist kein gültiger regulärer Ausdruck",
        ),
        (
            "- name: telekom\n  muster: telekom\n  feld: betrag\n"
            "  soll_konto: '4920'\n  haben_konto: '1200'\n",
            "Regel telekom: feld 'betrag'",
        ),
        ("- name: [kaputt\n", "kein gültiges YAML"),
        ("name: telekom\n", "keine Liste"),
    ],
    ids=["regex", "feld", "yaml", "keine_liste"],
)
def test_fehlerhafte_regeldatei_meldet_konfigurationsfehler(tmp_path, inhalt, erwartet):
    """Bisher gab ``re.error`` bzw. ein falsches ``feld`` im Web 500 und in der CLI
    einen Traceback — jetzt ``KonfigurationError`` mit Datei und Regelname."""
    datei = tmp_path / "regeln.yaml"
    datei.write_text(inhalt, encoding="utf-8")
    with pytest.raises(KonfigurationError, match=erwartet) as info:
        lade_regeln(datei)
    assert str(datei) in str(info.value)


def test_classify_mit_kaputtem_muster_meldung_statt_traceback(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from accounti.cli import app

    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "regeln.yaml").write_text(
        "- name: telekom\n  muster: '(telekom'\n  soll_konto: '4920'\n"
        "  haben_konto: '1200'\n",
        encoding="utf-8",
    )
    url = f"sqlite:///{tmp_path / 'a.db'}"
    r = CliRunner().invoke(app, ["classify", "--no-llm", "--db", url])
    assert r.exit_code == 1 and "Regel telekom" in r.output
    assert r.exception is None or isinstance(r.exception, SystemExit)


def test_rest_lauf_mit_kaputter_regeldatei_409_statt_500(tmp_path, monkeypatch):
    """Der REST-Lauf lädt die Regeldatei der Gesellschaft — fehlerhaft: 409 mit
    Meldung (wie die Oberfläche), nicht 500 „Interner Fehler“."""
    from accounti.models.auth import TokenRecht
    from tests.api_hilfe import webwelt
    from tests.auth_hilfe import billige_hashes

    billige_hashes(monkeypatch)
    welt = webwelt(tmp_path)
    welt.umgebung.wurzel.joinpath("a-regeln.yaml").write_text(
        "- name: kaputt\n  muster: müller\n  feld: betrag\n  soll_konto: '4920'\n"
        "  haben_konto: '1200'\n",
        encoding="utf-8",
    )
    token = welt.token("a", TokenRecht.LAEUFE_STARTEN)
    r = welt.client().post(
        "/api/v1/laeufe/bank", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 409, r.text
    assert "Regel kaputt" in r.text


@pytest.mark.parametrize("art", ["latin1", "verzeichnis", "konto_leer"])
def test_rest_lauf_mit_unlesbarer_regeldatei_409_statt_500(tmp_path, monkeypatch, art):
    """Runde 3 (gw2-web B3, gegen:regeln:3): Latin-1, Verzeichnis und ein leeres
    Konto gaben 500 bzw. buchten auf „None“ — jetzt 409 mit Datei und Grund."""
    from accounti.models.auth import TokenRecht
    from tests.api_hilfe import webwelt
    from tests.auth_hilfe import billige_hashes

    billige_hashes(monkeypatch)
    welt = webwelt(tmp_path)
    datei = welt.umgebung.wurzel.joinpath("a-regeln.yaml")
    eintrag = "- name: buero\n  muster: Bürobedarf\n  haben_konto: '1200'\n"
    if art == "latin1":
        datei.write_bytes((eintrag + "  soll_konto: '4930'\n").encode("latin-1"))
    elif art == "verzeichnis":
        datei.mkdir()
    else:
        datei.write_text(eintrag + "  soll_konto:\n", encoding="utf-8")
    token = welt.token("a", TokenRecht.LAEUFE_STARTEN)
    r = welt.client().post(
        "/api/v1/laeufe/bank", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 409, r.text
    assert {"latin1": "UTF-8", "verzeichnis": "nicht lesbar"}.get(
        art, "Regel buero"
    ) in r.text
