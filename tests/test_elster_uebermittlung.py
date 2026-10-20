"""Übermittler-Schnittstelle: Attrappe und Auswahl des Übermittlers."""

import pytest

from accounti.bank.tresor import neuer_schluessel
from accounti.elster.eric import EricUebermittler
from accounti.elster.konfiguration import ElsterEinstellungen
from accounti.elster.pin import speichere_pin
from accounti.elster.uebermittlung import AttrappenUebermittler, waehle_uebermittler


def test_attrappe_prueft_und_sendet_ohne_netz():
    a = AttrappenUebermittler()
    p = a.pruefe("<Elster/>", "UStVA_2026")
    assert p.erfolgreich and p.ticket is None
    s = a.sende("<Elster/>", "UStVA_2026")
    assert s.erfolgreich and s.ticket == "attrappe-0001"
    assert "Attrappe" in s.server_antwort
    assert a.geprueft == ["<Elster/>"] and a.gesendet == ["<Elster/>"]
    assert a.weg == "attrappe"


def test_attrappe_kann_scheitern():
    a = AttrappenUebermittler(fehler="Zertifikat abgelaufen")
    s = a.sende("<Elster/>", "UStVA_2026")
    assert not s.erfolgreich and s.fehler == "Zertifikat abgelaufen"


def test_ohne_eric_kein_uebermittler():
    u, grund = waehle_uebermittler(ElsterEinstellungen())
    assert u is None
    assert "elster.eric.bibliothek" in grund


def test_attrappe_nur_auf_ausdruecklichen_wunsch():
    u, grund = waehle_uebermittler(ElsterEinstellungen(uebermittler="attrappe"))
    assert isinstance(u, AttrappenUebermittler)
    assert "nichts wird abgegeben" in grund


def _eric(tmp_path, **kw):
    for name in ("libericapi.so", "elster.pfx"):
        (tmp_path / name).write_bytes(b"x")
    werte = {
        "bibliothek": str(tmp_path / "libericapi.so"),
        "zertifikat": str(tmp_path / "elster.pfx"),
        "pin_datei": str(tmp_path / "pin.enc"),
        **kw,
    }
    return ElsterEinstellungen.model_validate({"eric": werte})


def test_eric_nur_mit_bibliothek_zertifikat_und_pin(tmp_path, monkeypatch):
    schluessel = neuer_schluessel()
    monkeypatch.setenv("ACCOUNTI_SCHLUESSEL", schluessel)
    einst = _eric(tmp_path)
    u, grund = waehle_uebermittler(einst)
    assert u is None and "PIN" in grund  # PIN-Datei fehlt noch
    speichere_pin(tmp_path / "pin.enc", "123456", schluessel)
    u, grund = waehle_uebermittler(einst)
    assert isinstance(u, EricUebermittler)
    assert u.weg == "eric"
    assert "ERiC" in grund


@pytest.mark.parametrize("feld", ["bibliothek", "zertifikat"])
def test_eric_mit_fehlender_datei(tmp_path, monkeypatch, feld):
    monkeypatch.setenv("ACCOUNTI_SCHLUESSEL", neuer_schluessel())
    u, grund = waehle_uebermittler(_eric(tmp_path, **{feld: str(tmp_path / "weg")}))
    assert u is None and "nicht gefunden" in grund


def test_eric_ohne_schluessel(tmp_path, monkeypatch):
    schluessel = neuer_schluessel()
    speichere_pin(tmp_path / "pin.enc", "123456", schluessel)
    monkeypatch.delenv("ACCOUNTI_SCHLUESSEL", raising=False)
    u, grund = waehle_uebermittler(_eric(tmp_path))
    assert u is None and "ACCOUNTI_SCHLUESSEL" in grund
