from pathlib import Path

from accounti.klassifikation.regeln_loader import lade_regeln
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
