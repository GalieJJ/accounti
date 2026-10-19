from datetime import date

import pytest

from accounti.erechnung import lies
from accounti.erechnung.erzeuger.cii import schreibe_cii
from accounti.erechnung.validierung import Schwere, pruefe
from tests.test_erechnung_aufbau import _bau, entwurf, kunde, pos

FAELLE = {
    "inland": entwurf(
        kunde(leitweg_id="04011000-12345-67"),
        pos("Bilderrahmen Eiche", "250.00", "4"),
        pos("Ausstellungskatalog", "25.00", ermaessigt=True),
        bestellnummer="PO-77",
        notiz="Vielen Dank für Ihren Auftrag.",
        skonto_prozent=__import__("decimal").Decimal("2"),
        skonto_tage=7,
    ),
    "reverse_charge": entwurf(
        kunde(land="AT", ust_id="ATU12345678"),
        pos("Hängung", "90.00", "8", einheit="HUR", sonstige_leistung=True),
    ),
    "ig_lieferung": entwurf(
        kunde(land="FR", ust_id="FR12345678901"), pos("Rahmen", "100")
    ),
    "ausfuhr": entwurf(kunde(land="CH", ust_id=None), pos("Rahmen", "100")),
}


@pytest.mark.parametrize("fall", FAELLE, ids=str)
def test_round_trip_ergibt_identisches_zwischenmodell(fall):
    r = _bau(FAELLE[fall])
    xml = schreibe_cii(r)
    assert xml.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')
    assert lies(xml) == r


@pytest.mark.parametrize("fall", FAELLE, ids=str)
def test_erzeugte_rechnung_besteht_die_eigene_pruefung(fall):
    r = lies(schreibe_cii(_bau(FAELLE[fall])))
    assert [str(b) for b in pruefe(r) if b.schwere is Schwere.FEHLER] == []


def test_skonto_im_xrechnung_format():
    xml = schreibe_cii(_bau(FAELLE["inland"])).decode()
    assert "#SKONTO#TAGE=7#PROZENT=2.00#\n" in xml


def test_betraege_mit_zwei_nachkommastellen():
    xml = schreibe_cii(_bau(FAELLE["inland"])).decode()
    assert "<ram:GrandTotalAmount>1216.75</ram:GrandTotalAmount>" in xml
    assert "<ram:RateApplicablePercent>19</ram:RateApplicablePercent>" in xml
    assert '<udt:DateTimeString format="102">20260310</udt:DateTimeString>' in xml


def test_sonderzeichen_werden_escaped():
    e = FAELLE["inland"].model_copy(update={"notiz": "Rahmen & Leisten <Eiche>"})
    r = lies(schreibe_cii(_bau(e)))
    assert "Rahmen & Leisten <Eiche>" in r.notizen
    assert r.datum == date(2026, 3, 10)
