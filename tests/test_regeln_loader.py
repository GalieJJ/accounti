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
