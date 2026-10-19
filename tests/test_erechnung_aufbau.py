from datetime import date
from decimal import Decimal

import pytest

from accounti.erechnung.erzeuger.aufbau import NichtUnterstuetztError, baue_rechnung
from accounti.erechnung.validierung import Schwere, pruefe
from accounti.konfiguration import Firma
from accounti.models import AusgangsPosition, Ausgangsrechnung, Rechnungsempfaenger

FIRMA = Firma.model_validate(
    {
        "name": "Galerie Muster GmbH",
        "kuerzel": "GM",
        "anschrift": {"strasse": "Beispielweg 3", "plz": "24103", "ort": "Kiel"},
        "ust_id": "DE999999999",
        "email": "rechnung@galerie-muster.example",
        "kontakt": {
            "name": "Jan Muster",
            "telefon": "0431 123456",
            "email": "buchhaltung@galerie-muster.example",
        },
        "bank": {"iban": "DE89370400440532013000", "bic": "COBADEFFXXX"},
    }
)


def kunde(land="DE", ust_id="DE888888888", privat=False, **kw):
    return Rechnungsempfaenger(
        name="Atelier Kundin GmbH",
        strasse="Kundenstraße 8",
        plz="10115",
        ort="Berlin",
        land=land,
        ust_id=ust_id,
        email="rechnung@atelier-kundin.example",
        privat=privat,
        **kw,
    )


def pos(text, preis, menge="1", **kw):
    return AusgangsPosition(
        bezeichnung=text, einzelpreis=Decimal(preis), menge=Decimal(menge), **kw
    )


def entwurf(k, *positionen, **kw):
    return Ausgangsrechnung(
        kunde=k, positionen=list(positionen), leistungsdatum=date(2026, 3, 9), **kw
    )


def _bau(e, **kw):
    return baue_rechnung(e, FIRMA, "2026-0001", date(2026, 3, 10), **kw)


def test_inland_mit_zwei_steuersaetzen():
    r = _bau(
        entwurf(
            kunde(),
            pos("Bilderrahmen Eiche", "250.00", "4"),
            pos("Ausstellungskatalog", "25.00", ermaessigt=True),
        )
    )
    assert r.nummer == "2026-0001"
    assert r.datum == date(2026, 3, 10)
    assert r.faellig == date(2026, 3, 24)
    assert r.profil.value == "xrechnung"
    assert [(z.steuerkategorie, z.steuersatz, z.netto) for z in r.zeilen] == [
        ("S", Decimal("19"), Decimal("1000.00")),
        ("S", Decimal("7"), Decimal("25.00")),
    ]
    assert [(s.kategorie, s.satz, s.basis, s.betrag) for s in r.steuern] == [
        ("S", Decimal("19"), Decimal("1000.00"), Decimal("190.00")),
        ("S", Decimal("7"), Decimal("25.00"), Decimal("1.75")),
    ]
    assert (r.summen.netto, r.summen.steuer, r.summen.brutto, r.summen.zahlbetrag) == (
        Decimal("1025.00"),
        Decimal("191.75"),
        Decimal("1216.75"),
        Decimal("1216.75"),
    )
    assert r.verkaeufer.name == "Galerie Muster GmbH"
    assert r.verkaeufer.kontakt_telefon == "0431 123456"
    assert r.iban == "DE89370400440532013000"
    assert [b for b in pruefe(r) if b.schwere is Schwere.FEHLER] == []


def test_steuer_je_satz_auf_die_summe():
    r = _bau(entwurf(kunde(), *[pos(f"Karte {i}", "0.33") for i in range(3)]))
    # 3 × 0,33 = 0,99 → 19 % = 0,19 (je Position gerundet wären es 3 × 0,06 = 0,18)
    assert r.steuern[0].betrag == Decimal("0.19")


def test_eu_dienstleistung_ist_reverse_charge():
    """Akzeptanz 5."""
    r = _bau(
        entwurf(
            kunde(land="AT", ust_id="ATU12345678"),
            pos(
                "Hängung der Ausstellung",
                "90.00",
                "8",
                einheit="HUR",
                sonstige_leistung=True,
            ),
        )
    )
    (st,) = r.steuern
    assert (st.kategorie, st.satz, st.betrag) == ("AE", Decimal("0"), Decimal("0.00"))
    assert st.befreiungsgrund_code == "VATEX-EU-AE"
    assert "Steuerschuldnerschaft des Leistungsempfängers" in st.befreiungsgrund
    assert any("Reverse Charge" in n for n in r.notizen)
    assert r.summen.brutto == Decimal("720.00")
    assert [b for b in pruefe(r) if b.schwere is Schwere.FEHLER] == []


def test_eu_ware_ist_innergemeinschaftliche_lieferung():
    r = _bau(entwurf(kunde(land="FR", ust_id="FR12345678901"), pos("Rahmen", "100")))
    (st,) = r.steuern
    assert (st.kategorie, st.befreiungsgrund_code) == ("K", "VATEX-EU-IC")
    assert (r.lieferanschrift.ort, r.lieferanschrift.plz, r.lieferanschrift.land) == (
        "Berlin",
        "10115",
        "FR",
    )
    assert [b for b in pruefe(r) if b.schwere is Schwere.FEHLER] == []


def test_drittland_ware_ist_ausfuhr():
    r = _bau(entwurf(kunde(land="CH", ust_id=None), pos("Rahmen", "100")))
    (st,) = r.steuern
    assert (st.kategorie, st.befreiungsgrund_code) == ("G", "VATEX-EU-G")
    assert [b for b in pruefe(r) if b.schwere is Schwere.FEHLER] == []


def test_eu_privatkunde_mit_oss():
    firma = FIRMA.model_copy(update={"oss": True})
    r = baue_rechnung(
        entwurf(kunde(land="FR", ust_id=None, privat=True), pos("Rahmen", "100")),
        firma,
        "2026-0002",
        date(2026, 3, 10),
    )
    (st,) = r.steuern
    assert (st.kategorie, st.satz, st.betrag) == ("S", Decimal("20"), Decimal("20.00"))
    assert [b for b in pruefe(r) if b.schwere is Schwere.FEHLER] == []
    assert "SATZ-LAND" not in {b.regel for b in pruefe(r)}


def test_eu_privatkunde_ohne_oss_zahlt_deutsche_steuer():
    r = _bau(entwurf(kunde(land="FR", ust_id=None, privat=True), pos("Rahmen", "100")))
    assert r.steuern[0].satz == Decimal("19")


def test_skonto_und_kaeuferreferenz():
    r = _bau(
        entwurf(
            kunde(leitweg_id="04011000-12345-67"),
            pos("Rahmen", "100"),
            skonto_prozent=Decimal("2"),
            skonto_tage=7,
            bestellnummer="PO-77",
            notiz="Vielen Dank!",
        )
    )
    assert r.skonto == (Decimal("2.00"), 7)
    assert r.kaeufer_referenz == "04011000-12345-67"
    assert r.bestellnummer == "PO-77"
    assert "Vielen Dank!" in r.notizen


def test_kaeuferreferenz_faellt_auf_bestellnummer_zurueck():
    r = _bau(entwurf(kunde(), pos("Rahmen", "100"), bestellnummer="PO-77"))
    assert r.kaeufer_referenz == "PO-77"


@pytest.mark.parametrize(
    ("aenderung", "meldung"),
    [
        ({"email": None}, "E-Mail"),
        ({"ort": None}, "Ort"),
        ({"plz": None}, "PLZ"),
    ],
)
def test_pflichtangaben_des_kunden(aenderung, meldung):
    k = kunde().model_copy(update=aenderung)
    with pytest.raises(ValueError, match=meldung):
        _bau(entwurf(k, pos("Rahmen", "100")))


def test_ohne_positionen():
    with pytest.raises(ValueError, match="Position"):
        _bau(entwurf(kunde()))


def test_dienstleistung_ins_drittland_noch_nicht_unterstuetzt():
    with pytest.raises(NichtUnterstuetztError, match="Drittland"):
        _bau(
            entwurf(
                kunde(land="CH", ust_id=None),
                pos("Beratung", "100", sonstige_leistung=True),
            )
        )
