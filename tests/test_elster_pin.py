import stat

import pytest

from accounti.bank.tresor import TresorError, neuer_schluessel
from accounti.elster.pin import PinError, lade_pin, speichere_pin


def test_pin_verschluesselt_in_eigener_datei(tmp_path):
    schluessel = neuer_schluessel()
    datei = tmp_path / "geheim" / "elster-pin.enc"
    speichere_pin(datei, "123456", schluessel)
    assert stat.S_IMODE(datei.stat().st_mode) == 0o600
    inhalt = datei.read_text(encoding="utf-8")
    assert "123456" not in inhalt and inhalt.startswith("v1:")
    assert lade_pin(datei, schluessel) == "123456"


def test_falscher_schluessel(tmp_path):
    datei = tmp_path / "pin.enc"
    speichere_pin(datei, "123456", neuer_schluessel())
    with pytest.raises(TresorError):
        lade_pin(datei, neuer_schluessel())


def test_fehlende_datei_und_leere_pin(tmp_path):
    with pytest.raises(PinError, match="accounti elster pin"):
        lade_pin(tmp_path / "fehlt.enc", neuer_schluessel())
    with pytest.raises(PinError):
        speichere_pin(tmp_path / "x.enc", "", neuer_schluessel())
