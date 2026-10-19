"""Regressionstest gegen offizielle Beispiele der KoSIT-Testsuite."""

from pathlib import Path

import pytest

from accounti.erechnung import lies
from accounti.erechnung.validierung import Schwere, pruefe

KOSIT = Path(__file__).resolve().parents[1] / "examples" / "erechnung" / "kosit"


@pytest.mark.parametrize("datei", sorted(KOSIT.glob("*.xml")), ids=lambda p: p.name)
def test_offizielle_beispiele_ohne_fehler(datei):
    r = lies(datei.read_bytes())
    fehler = [str(b) for b in pruefe(r) if b.schwere is Schwere.FEHLER]
    assert fehler == []
    assert r.nummer
    assert r.summen.zahlbetrag is not None


def test_ubl_und_cii_der_testsuite_ergeben_dasselbe_modell():
    import dataclasses

    ubl = lies((KOSIT / "01.01a-INVOICE_ubl.xml").read_bytes())
    cii = lies((KOSIT / "01.01a-INVOICE_uncefact.xml").read_bytes())
    assert (ubl.nummer, ubl.summen, len(ubl.zeilen), ubl.steuern) == (
        cii.nummer,
        cii.summen,
        len(cii.zeilen),
        cii.steuern,
    )
    assert dataclasses.asdict(ubl.verkaeufer)["ust_id"] == cii.verkaeufer.ust_id
