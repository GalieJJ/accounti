import dataclasses
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from accounti.erechnung import ERechnungError, Profil, lies

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "erechnung"


def _lies(name):
    return lies((FIXTURES / name).read_bytes())


def test_cii_kopf_und_parteien():
    r = _lies("xrechnung_cii.xml")
    assert r.syntax == "CII"
    assert r.profil is Profil.XRECHNUNG
    assert r.nummer == "RE-2026-0042"
    assert r.datum == date(2026, 3, 5)
    assert r.typ == "380"
    assert r.waehrung == "EUR"
    assert r.faellig == date(2026, 3, 19)
    assert r.leistungsdatum == date(2026, 3, 3)
    assert r.kaeufer_referenz == "04011000-12345-67"
    assert r.bestellnummer == "B-2026-117"
    assert r.notizen == ["Vielen Dank für Ihren Auftrag."]
    v = r.verkaeufer
    assert v.name == "Bürobedarf Müller GmbH"
    assert v.ust_id == "DE123456789"
    assert (
        v.anschrift.strasse,
        v.anschrift.plz,
        v.anschrift.ort,
        v.anschrift.land,
    ) == (
        "Hauptstraße 12",
        "20095",
        "Hamburg",
        "DE",
    )
    assert v.email == "info@buero-mueller.example"
    assert v.kontakt_name == "Erika Muster"
    assert r.kaeufer.name == "Galerie Muster GmbH"
    assert r.kaeufer.ust_id == "DE999999999"


def test_cii_zeilen_steuern_summen_zahlung():
    r = _lies("xrechnung_cii.xml")
    assert [
        (z.id, z.bezeichnung, z.menge, z.einheit, z.einzelpreis, z.netto)
        for z in r.zeilen
    ] == [
        (
            "1",
            "Kopierpapier A4, 500 Blatt",
            Decimal("10"),
            "C62",
            Decimal("8.50"),
            Decimal("85.00"),
        ),
        ("2", "Ordner breit", Decimal("10"), "C62", Decimal("1.50"), Decimal("15.00")),
        (
            "3",
            "Fachbuch Steuerrecht",
            Decimal("1"),
            "C62",
            Decimal("50.00"),
            Decimal("50.00"),
        ),
    ]
    assert [(z.steuerkategorie, z.steuersatz) for z in r.zeilen] == [
        ("S", Decimal("19")),
        ("S", Decimal("19")),
        ("S", Decimal("7")),
    ]
    assert [(s.kategorie, s.satz, s.basis, s.betrag) for s in r.steuern] == [
        ("S", Decimal("19"), Decimal("100.00"), Decimal("19.00")),
        ("S", Decimal("7"), Decimal("50.00"), Decimal("3.50")),
    ]
    s = r.summen
    assert (s.positionen_netto, s.netto, s.steuer, s.brutto, s.zahlbetrag) == (
        Decimal("150.00"),
        Decimal("150.00"),
        Decimal("22.50"),
        Decimal("172.50"),
        Decimal("172.50"),
    )
    assert r.iban == "DE89370400440532013000"
    assert r.zahlungsart == "58"
    assert r.skonto == (Decimal("2.00"), 7)


def test_ubl_ergibt_dasselbe_zwischenmodell_wie_cii():
    cii = _lies("xrechnung_cii.xml")
    ubl = _lies("xrechnung_ubl.xml")
    assert ubl.syntax == "UBL"
    assert dataclasses.replace(ubl, syntax="CII") == cii


def test_nachlass_und_zuschlag_auf_belegebene():
    r = _lies("mit_nachlass_cii.xml")
    assert [(z.zuschlag, z.betrag, z.grund, z.steuersatz) for z in r.zu_abschlaege] == [
        (False, Decimal("10.00"), "Treuerabatt", Decimal("19")),
        (True, Decimal("5.90"), "Versand", Decimal("19")),
    ]
    assert r.summen.abschlaege == Decimal("10.00")
    assert r.summen.zuschlaege == Decimal("5.90")
    assert r.summen.netto == Decimal("145.90")


def test_reverse_charge_ubl_mit_zeitraum_und_befreiungsgrund():
    r = _lies("reverse_charge_ohne_ust_id_ubl.xml")
    assert r.profil is Profil.EN16931
    assert r.verkaeufer.anschrift.land == "AT"
    assert r.kaeufer.ust_id is None
    assert (r.leistungszeitraum_von, r.leistungszeitraum_bis) == (
        date(2026, 3, 9),
        date(2026, 3, 10),
    )
    (st,) = r.steuern
    assert (st.kategorie, st.satz, st.befreiungsgrund) == (
        "AE",
        Decimal("0"),
        "Steuerschuldnerschaft des Leistungsempfängers",
    )


def test_minimum_profil_hat_keine_zeilen():
    r = _lies("minimum_cii.xml")
    assert r.profil is Profil.MINIMUM
    assert r.profil.reduziert
    assert r.zeilen == []
    assert r.summen.brutto == Decimal("1190.00")
    assert r.summen.positionen_netto is None


def test_ubl_gutschrift():
    xml = (FIXTURES / "xrechnung_ubl.xml").read_text(encoding="utf-8")
    xml = (
        xml.replace("ubl:schema:xsd:Invoice-2", "ubl:schema:xsd:CreditNote-2")
        .replace("ubl:Invoice", "ubl:CreditNote")
        .replace("InvoiceTypeCode>380", "CreditNoteTypeCode>381")
        .replace("</cbc:InvoiceTypeCode>", "</cbc:CreditNoteTypeCode>")
        .replace("cac:InvoiceLine", "cac:CreditNoteLine")
        .replace("cbc:InvoicedQuantity", "cbc:CreditedQuantity")
    )
    r = lies(xml.encode())
    assert r.typ == "381"
    assert len(r.zeilen) == 3
    assert r.zeilen[0].menge == Decimal("10")


def test_doctype_wird_abgelehnt():
    xml = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><Invoice/>'
    with pytest.raises(ERechnungError, match="DTD"):
        lies(xml)


@pytest.mark.parametrize("xml", [b"<Rechnung/>", b"<Invoice", b""])
def test_unbekanntes_oder_kaputtes_xml(xml):
    with pytest.raises(ERechnungError):
        lies(xml)


def test_ubl_steuernummer_unter_beliebigem_nicht_vat_schema():
    xml = (FIXTURES / "xrechnung_ubl.xml").read_text(encoding="utf-8")
    xml = xml.replace(
        "<cbc:CompanyID>DE123456789</cbc:CompanyID>\n        <cac:TaxScheme>\n"
        "          <cbc:ID>VAT</cbc:ID>",
        "<cbc:CompanyID>12/345/67890</cbc:CompanyID>\n        <cac:TaxScheme>\n"
        "          <cbc:ID>???</cbc:ID>",
    )
    r = lies(xml.encode())
    assert r.verkaeufer.ust_id is None
    assert r.verkaeufer.steuernummer == "12/345/67890"


def test_befreiungsgrund_als_code():
    r = _lies("reverse_charge_ohne_ust_id_ubl.xml")
    assert r.steuern[0].befreiungsgrund_code == "VATEX-EU-AE"
