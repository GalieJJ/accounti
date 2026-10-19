"""OASIS UBL 2.1 — XRechnung (UBL), Peppol BIS; Invoice und CreditNote."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from accounti.erechnung.modell import (
    Anschrift,
    Partei,
    Rechnung,
    Rechnungszeile,
    Steueraufschluesselung,
    Summen,
    ZuAbschlag,
)
from accounti.erechnung.parser._xml import Leser, lokaler_name

NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


def _partei(p: Leser) -> Partei:
    ust_id = steuernummer = None
    for schema in p.alle("cac:PartyTaxScheme"):
        art = schema.text("cac:TaxScheme/cbc:ID")
        # BT-31 steht unter dem Schema VAT, die Steuernummer (BT-32) unter jedem
        # anderen Schema.
        if art == "VAT":
            ust_id = schema.text("cbc:CompanyID")
        else:
            steuernummer = schema.text("cbc:CompanyID")
    adresse = p.knoten("cac:PostalAddress")
    kontakt = p.knoten("cac:Contact")
    return Partei(
        name=p.text("cac:PartyLegalEntity/cbc:RegistrationName")
        or p.text("cac:PartyName/cbc:Name"),
        ust_id=ust_id,
        steuernummer=steuernummer,
        anschrift=Anschrift(
            strasse=adresse.text("cbc:StreetName"),
            plz=adresse.text("cbc:PostalZone"),
            ort=adresse.text("cbc:CityName"),
            land=adresse.text("cac:Country/cbc:IdentificationCode"),
        ),
        email=p.text("cbc:EndpointID"),
        kontakt_name=kontakt.text("cbc:Name"),
        kontakt_telefon=kontakt.text("cbc:Telephone"),
        kontakt_email=kontakt.text("cbc:ElectronicMail"),
    )


def _zeile(z: Leser, menge_tag: str) -> Rechnungszeile:
    kategorie = z.knoten("cac:Item/cac:ClassifiedTaxCategory")
    return Rechnungszeile(
        id=z.text("cbc:ID"),
        bezeichnung=z.text("cac:Item/cbc:Name"),
        menge=z.dezimal(f"cbc:{menge_tag}"),
        einheit=z.attr(f"cbc:{menge_tag}", "unitCode"),
        einzelpreis=z.dezimal("cac:Price/cbc:PriceAmount"),
        netto=z.dezimal("cbc:LineExtensionAmount"),
        steuerkategorie=kategorie.text("cbc:ID"),
        steuersatz=kategorie.dezimal("cbc:Percent"),
    )


def lies_ubl(wurzel: ET.Element) -> Rechnung:
    doc = Leser(wurzel, NS)
    gutschrift = lokaler_name(wurzel) == "CreditNote"
    zeilen_tag, menge_tag, typ_tag = (
        ("CreditNoteLine", "CreditedQuantity", "CreditNoteTypeCode")
        if gutschrift
        else ("InvoiceLine", "InvoicedQuantity", "InvoiceTypeCode")
    )
    zahlung = doc.knoten("cac:PaymentMeans")
    summe = doc.knoten("cac:LegalMonetaryTotal")
    zeitraum = doc.knoten("cac:InvoicePeriod")
    # Die Steueraufschlüsselung steht im TaxTotal in Rechnungswährung (mit Subtotals).
    steuer_gesamt = next(
        (t for t in doc.alle("cac:TaxTotal") if t.alle("cac:TaxSubtotal")),
        doc.knoten("cac:TaxTotal"),
    )

    return Rechnung(
        syntax="UBL",
        spezifikation=doc.text("cbc:CustomizationID"),
        nummer=doc.text("cbc:ID"),
        datum=doc.datum("cbc:IssueDate"),
        typ=doc.text(f"cbc:{typ_tag}"),
        waehrung=doc.text("cbc:DocumentCurrencyCode"),
        faellig=doc.datum("cbc:DueDate")
        or doc.datum("cac:PaymentMeans/cbc:PaymentDueDate"),
        kaeufer_referenz=doc.text("cbc:BuyerReference"),
        bestellnummer=doc.text("cac:OrderReference/cbc:ID"),
        notizen=[t for n in doc.alle("cbc:Note") if (t := n.text())],
        leistungsdatum=doc.datum("cac:Delivery/cbc:ActualDeliveryDate"),
        leistungszeitraum_von=zeitraum.datum("cbc:StartDate"),
        leistungszeitraum_bis=zeitraum.datum("cbc:EndDate"),
        verkaeufer=_partei(doc.knoten("cac:AccountingSupplierParty/cac:Party")),
        kaeufer=_partei(doc.knoten("cac:AccountingCustomerParty/cac:Party")),
        zahlungsart=zahlung.text("cbc:PaymentMeansCode"),
        iban=zahlung.text("cac:PayeeFinancialAccount/cbc:ID"),
        zahlungsbedingungen=doc.text("cac:PaymentTerms/cbc:Note"),
        zeilen=[_zeile(z, menge_tag) for z in doc.alle(f"cac:{zeilen_tag}")],
        zu_abschlaege=[
            ZuAbschlag(
                zuschlag=(za.text("cbc:ChargeIndicator") or "").lower() == "true",
                betrag=za.dezimal("cbc:Amount"),
                grund=za.text("cbc:AllowanceChargeReason"),
                steuerkategorie=za.text("cac:TaxCategory/cbc:ID"),
                steuersatz=za.dezimal("cac:TaxCategory/cbc:Percent"),
            )
            for za in doc.alle("cac:AllowanceCharge")
        ],
        steuern=[
            Steueraufschluesselung(
                kategorie=s.text("cac:TaxCategory/cbc:ID"),
                satz=s.dezimal("cac:TaxCategory/cbc:Percent"),
                basis=s.dezimal("cbc:TaxableAmount"),
                betrag=s.dezimal("cbc:TaxAmount"),
                befreiungsgrund=s.text("cac:TaxCategory/cbc:TaxExemptionReason"),
                befreiungsgrund_code=s.text(
                    "cac:TaxCategory/cbc:TaxExemptionReasonCode"
                ),
            )
            for s in steuer_gesamt.alle("cac:TaxSubtotal")
        ],
        summen=Summen(
            positionen_netto=summe.dezimal("cbc:LineExtensionAmount"),
            abschlaege=summe.dezimal("cbc:AllowanceTotalAmount"),
            zuschlaege=summe.dezimal("cbc:ChargeTotalAmount"),
            netto=summe.dezimal("cbc:TaxExclusiveAmount"),
            steuer=steuer_gesamt.dezimal("cbc:TaxAmount"),
            brutto=summe.dezimal("cbc:TaxInclusiveAmount"),
            vorauszahlung=summe.dezimal("cbc:PrepaidAmount"),
            rundung=summe.dezimal("cbc:PayableRoundingAmount"),
            zahlbetrag=summe.dezimal("cbc:PayableAmount"),
        ),
    )
