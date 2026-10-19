"""UN/CEFACT Cross Industry Invoice — XRechnung (CII), ZUGFeRD 2.x, Factur-X."""

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
from accounti.erechnung.parser._xml import Leser

NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": (
        "urn:un:unece:uncefact:data:standard:"
        "ReusableAggregateBusinessInformationEntity:100"
    ),
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}
_DATUM = "udt:DateTimeString"


def _partei(p: Leser) -> Partei:
    adresse = p.knoten("ram:PostalTradeAddress")
    kontakt = p.knoten("ram:DefinedTradeContact")
    ust_id = steuernummer = None
    for reg in p.alle("ram:SpecifiedTaxRegistration/ram:ID"):
        schema = reg.element.get("schemeID") if reg.element is not None else None
        if schema == "VA":
            ust_id = reg.text()
        elif schema == "FC":
            steuernummer = reg.text()
    return Partei(
        name=p.text("ram:Name"),
        ust_id=ust_id,
        steuernummer=steuernummer,
        anschrift=Anschrift(
            strasse=adresse.text("ram:LineOne"),
            plz=adresse.text("ram:PostcodeCode"),
            ort=adresse.text("ram:CityName"),
            land=adresse.text("ram:CountryID"),
        ),
        email=p.text("ram:URIUniversalCommunication/ram:URIID"),
        kontakt_name=kontakt.text("ram:PersonName"),
        kontakt_telefon=kontakt.text(
            "ram:TelephoneUniversalCommunication/ram:CompleteNumber"
        ),
        kontakt_email=kontakt.text("ram:EmailURIUniversalCommunication/ram:URIID"),
    )


def _zeile(z: Leser) -> Rechnungszeile:
    steuer = z.knoten("ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax")
    return Rechnungszeile(
        id=z.text("ram:AssociatedDocumentLineDocument/ram:LineID"),
        bezeichnung=z.text("ram:SpecifiedTradeProduct/ram:Name"),
        menge=z.dezimal("ram:SpecifiedLineTradeDelivery/ram:BilledQuantity"),
        einheit=z.attr("ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", "unitCode"),
        einzelpreis=z.dezimal(
            "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount"
        ),
        netto=z.dezimal(
            "ram:SpecifiedLineTradeSettlement/"
            "ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount"
        ),
        steuerkategorie=steuer.text("ram:CategoryCode"),
        steuersatz=steuer.dezimal("ram:RateApplicablePercent"),
    )


def lies_cii(wurzel: ET.Element) -> Rechnung:
    doc = Leser(wurzel, NS)
    kopf = doc.knoten("rsm:ExchangedDocument")
    handel = doc.knoten("rsm:SupplyChainTradeTransaction")
    vereinbarung = handel.knoten("ram:ApplicableHeaderTradeAgreement")
    lieferung = handel.knoten("ram:ApplicableHeaderTradeDelivery")
    abrechnung = handel.knoten("ram:ApplicableHeaderTradeSettlement")
    zahlung = abrechnung.knoten("ram:SpecifiedTradeSettlementPaymentMeans")
    bedingungen = abrechnung.knoten("ram:SpecifiedTradePaymentTerms")
    summe = abrechnung.knoten("ram:SpecifiedTradeSettlementHeaderMonetarySummation")
    zeitraum = abrechnung.knoten("ram:BillingSpecifiedPeriod")

    return Rechnung(
        syntax="CII",
        spezifikation=doc.text(
            "rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID"
        ),
        nummer=kopf.text("ram:ID"),
        datum=kopf.datum(f"ram:IssueDateTime/{_DATUM}"),
        typ=kopf.text("ram:TypeCode"),
        waehrung=abrechnung.text("ram:InvoiceCurrencyCode"),
        faellig=bedingungen.datum(f"ram:DueDateDateTime/{_DATUM}"),
        kaeufer_referenz=vereinbarung.text("ram:BuyerReference"),
        bestellnummer=vereinbarung.text(
            "ram:BuyerOrderReferencedDocument/ram:IssuerAssignedID"
        ),
        notizen=[
            t for n in kopf.alle("ram:IncludedNote") if (t := n.text("ram:Content"))
        ],
        leistungsdatum=lieferung.datum(
            f"ram:ActualDeliverySupplyChainEvent/ram:OccurrenceDateTime/{_DATUM}"
        ),
        leistungszeitraum_von=zeitraum.datum(f"ram:StartDateTime/{_DATUM}"),
        leistungszeitraum_bis=zeitraum.datum(f"ram:EndDateTime/{_DATUM}"),
        verkaeufer=_partei(vereinbarung.knoten("ram:SellerTradeParty")),
        kaeufer=_partei(vereinbarung.knoten("ram:BuyerTradeParty")),
        zahlungsart=zahlung.text("ram:TypeCode"),
        iban=zahlung.text("ram:PayeePartyCreditorFinancialAccount/ram:IBANID"),
        zahlungsbedingungen=bedingungen.text("ram:Description"),
        zeilen=[_zeile(z) for z in handel.alle("ram:IncludedSupplyChainTradeLineItem")],
        zu_abschlaege=[
            ZuAbschlag(
                zuschlag=(za.text("ram:ChargeIndicator/udt:Indicator") or "").lower()
                == "true",
                betrag=za.dezimal("ram:ActualAmount"),
                grund=za.text("ram:Reason"),
                steuerkategorie=za.text("ram:CategoryTradeTax/ram:CategoryCode"),
                steuersatz=za.dezimal("ram:CategoryTradeTax/ram:RateApplicablePercent"),
            )
            for za in abrechnung.alle("ram:SpecifiedTradeAllowanceCharge")
        ],
        steuern=[
            Steueraufschluesselung(
                kategorie=s.text("ram:CategoryCode"),
                satz=s.dezimal("ram:RateApplicablePercent"),
                basis=s.dezimal("ram:BasisAmount"),
                betrag=s.dezimal("ram:CalculatedAmount"),
                befreiungsgrund=s.text("ram:ExemptionReason"),
                befreiungsgrund_code=s.text("ram:ExemptionReasonCode"),
            )
            for s in abrechnung.alle("ram:ApplicableTradeTax")
        ],
        summen=Summen(
            positionen_netto=summe.dezimal("ram:LineTotalAmount"),
            abschlaege=summe.dezimal("ram:AllowanceTotalAmount"),
            zuschlaege=summe.dezimal("ram:ChargeTotalAmount"),
            netto=summe.dezimal("ram:TaxBasisTotalAmount"),
            steuer=summe.dezimal("ram:TaxTotalAmount"),
            brutto=summe.dezimal("ram:GrandTotalAmount"),
            vorauszahlung=summe.dezimal("ram:TotalPrepaidAmount"),
            rundung=summe.dezimal("ram:RoundingAmount"),
            zahlbetrag=summe.dezimal("ram:DuePayableAmount"),
        ),
    )
