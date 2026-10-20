"""Zwischenmodell → UN/CEFACT CII (XRechnung 3.0, zugleich die Syntax von ZUGFeRD).

Die Reihenfolge der Elemente folgt dem CII-Schema (D16B) — das KoSIT-Prüftool prüft
auch die Struktur, nicht nur die Inhalte.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal

from accounti.erechnung.modell import Anschrift, Partei, Rechnung
from accounti.erechnung.parser.cii import NS

PEPPOL_PROZESS = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
CENT = Decimal("0.01")

for _praefix, _uri in NS.items():
    ET.register_namespace(_praefix, _uri)


def _q(name: str) -> str:
    praefix, _, lokal = name.partition(":")
    return f"{{{NS[praefix]}}}{lokal}"


def _el(
    eltern: ET.Element, name: str, text: str | None = None, **attribute: str
) -> ET.Element:
    element = ET.SubElement(eltern, _q(name), attribute)
    if text is not None:
        element.text = text
    return element


def _betrag(wert: Decimal) -> str:
    return f"{wert.quantize(CENT):f}"


def _zahl(wert: Decimal) -> str:
    return f"{wert.normalize():f}"


def _datum(eltern: ET.Element, name: str, wert: date) -> None:
    _el(_el(eltern, name), "udt:DateTimeString", f"{wert:%Y%m%d}", format="102")


def _anschrift(adresse: ET.Element, a: Anschrift) -> None:
    for feld, wert in (
        ("ram:PostcodeCode", a.plz),
        ("ram:LineOne", a.strasse),
        ("ram:CityName", a.ort),
        ("ram:CountryID", a.land),
    ):
        if wert:
            _el(adresse, feld, wert)


def _partei(eltern: ET.Element, name: str, p: Partei) -> None:
    partei = _el(eltern, name)
    if p.name:
        _el(partei, "ram:Name", p.name)
    if p.kontakt_name or p.kontakt_telefon or p.kontakt_email:
        kontakt = _el(partei, "ram:DefinedTradeContact")
        if p.kontakt_name:
            _el(kontakt, "ram:PersonName", p.kontakt_name)
        if p.kontakt_telefon:
            telefon = _el(kontakt, "ram:TelephoneUniversalCommunication")
            _el(telefon, "ram:CompleteNumber", p.kontakt_telefon)
        if p.kontakt_email:
            email = _el(kontakt, "ram:EmailURIUniversalCommunication")
            _el(email, "ram:URIID", p.kontakt_email)
    _anschrift(_el(partei, "ram:PostalTradeAddress"), p.anschrift)
    if p.email:
        _el(
            _el(partei, "ram:URIUniversalCommunication"),
            "ram:URIID",
            p.email,
            schemeID="EM",
        )
    for kennung, schema in ((p.ust_id, "VA"), (p.steuernummer, "FC")):
        if kennung:
            _el(
                _el(partei, "ram:SpecifiedTaxRegistration"),
                "ram:ID",
                kennung,
                schemeID=schema,
            )


def _steuer(
    eltern: ET.Element,
    kategorie: str | None,
    satz: Decimal | None,
    *,
    basis: Decimal | None = None,
    betrag: Decimal | None = None,
    grund: str | None = None,
    code: str | None = None,
    name: str = "ram:ApplicableTradeTax",
) -> None:
    steuer = _el(eltern, name)
    if betrag is not None:
        _el(steuer, "ram:CalculatedAmount", _betrag(betrag))
    _el(steuer, "ram:TypeCode", "VAT")
    if grund:
        _el(steuer, "ram:ExemptionReason", grund)
    if basis is not None:
        _el(steuer, "ram:BasisAmount", _betrag(basis))
    if kategorie:
        _el(steuer, "ram:CategoryCode", kategorie)
    if code:
        _el(steuer, "ram:ExemptionReasonCode", code)
    if satz is not None:  # Kategorie O trägt keinen Satz
        _el(steuer, "ram:RateApplicablePercent", _zahl(satz))


def schreibe_cii(r: Rechnung) -> bytes:
    """Serialisiert eine Rechnung als CII-XML (UTF-8, mit XML-Deklaration)."""
    wurzel = ET.Element(_q("rsm:CrossIndustryInvoice"))

    kontext = _el(wurzel, "rsm:ExchangedDocumentContext")
    _el(
        _el(kontext, "ram:BusinessProcessSpecifiedDocumentContextParameter"),
        "ram:ID",
        PEPPOL_PROZESS,
    )
    _el(
        _el(kontext, "ram:GuidelineSpecifiedDocumentContextParameter"),
        "ram:ID",
        r.spezifikation,
    )

    kopf = _el(wurzel, "rsm:ExchangedDocument")
    _el(kopf, "ram:ID", r.nummer)
    _el(kopf, "ram:TypeCode", r.typ)
    if r.datum:
        _datum(kopf, "ram:IssueDateTime", r.datum)
    for notiz in r.notizen:
        _el(_el(kopf, "ram:IncludedNote"), "ram:Content", notiz)

    handel = _el(wurzel, "rsm:SupplyChainTradeTransaction")
    for z in r.zeilen:
        zeile = _el(handel, "ram:IncludedSupplyChainTradeLineItem")
        _el(_el(zeile, "ram:AssociatedDocumentLineDocument"), "ram:LineID", z.id)
        _el(_el(zeile, "ram:SpecifiedTradeProduct"), "ram:Name", z.bezeichnung)
        if z.einzelpreis is not None:
            preis = _el(
                _el(zeile, "ram:SpecifiedLineTradeAgreement"),
                "ram:NetPriceProductTradePrice",
            )
            _el(preis, "ram:ChargeAmount", _zahl(z.einzelpreis))
        if z.menge is not None:
            lieferung = _el(zeile, "ram:SpecifiedLineTradeDelivery")
            _el(
                lieferung,
                "ram:BilledQuantity",
                _zahl(z.menge),
                unitCode=z.einheit or "C62",
            )
        abrechnung = _el(zeile, "ram:SpecifiedLineTradeSettlement")
        _steuer(abrechnung, z.steuerkategorie, z.steuersatz)
        if z.netto is not None:
            summe = _el(abrechnung, "ram:SpecifiedTradeSettlementLineMonetarySummation")
            _el(summe, "ram:LineTotalAmount", _betrag(z.netto))

    vereinbarung = _el(handel, "ram:ApplicableHeaderTradeAgreement")
    if r.kaeufer_referenz:
        _el(vereinbarung, "ram:BuyerReference", r.kaeufer_referenz)
    _partei(vereinbarung, "ram:SellerTradeParty", r.verkaeufer)
    _partei(vereinbarung, "ram:BuyerTradeParty", r.kaeufer)
    if r.bestellnummer:
        bestellung = _el(vereinbarung, "ram:BuyerOrderReferencedDocument")
        _el(bestellung, "ram:IssuerAssignedID", r.bestellnummer)

    lieferung = _el(handel, "ram:ApplicableHeaderTradeDelivery")
    if r.lieferanschrift is not None:
        empfaenger = _el(lieferung, "ram:ShipToTradeParty")
        _anschrift(_el(empfaenger, "ram:PostalTradeAddress"), r.lieferanschrift)
    if r.leistungsdatum:
        ereignis = _el(lieferung, "ram:ActualDeliverySupplyChainEvent")
        _datum(ereignis, "ram:OccurrenceDateTime", r.leistungsdatum)

    abrechnung = _el(handel, "ram:ApplicableHeaderTradeSettlement")
    _el(abrechnung, "ram:InvoiceCurrencyCode", r.waehrung)
    if r.zahlungsart:
        zahlung = _el(abrechnung, "ram:SpecifiedTradeSettlementPaymentMeans")
        _el(zahlung, "ram:TypeCode", r.zahlungsart)
        if r.iban:
            konto = _el(zahlung, "ram:PayeePartyCreditorFinancialAccount")
            _el(konto, "ram:IBANID", r.iban)
    for st in r.steuern:
        _steuer(
            abrechnung,
            st.kategorie,
            st.satz,
            basis=st.basis,
            betrag=st.betrag,
            grund=st.befreiungsgrund,
            code=st.befreiungsgrund_code,
        )
    if r.leistungszeitraum_von or r.leistungszeitraum_bis:
        zeitraum = _el(abrechnung, "ram:BillingSpecifiedPeriod")
        if r.leistungszeitraum_von:
            _datum(zeitraum, "ram:StartDateTime", r.leistungszeitraum_von)
        if r.leistungszeitraum_bis:
            _datum(zeitraum, "ram:EndDateTime", r.leistungszeitraum_bis)
    for za in r.zu_abschlaege:
        posten = _el(abrechnung, "ram:SpecifiedTradeAllowanceCharge")
        _el(
            _el(posten, "ram:ChargeIndicator"),
            "udt:Indicator",
            "true" if za.zuschlag else "false",
        )
        if za.betrag is not None:
            _el(posten, "ram:ActualAmount", _betrag(za.betrag))
        if za.grund:
            _el(posten, "ram:Reason", za.grund)
        _steuer(posten, za.steuerkategorie, za.steuersatz, name="ram:CategoryTradeTax")
    if r.zahlungsbedingungen or r.faellig:
        bedingungen = _el(abrechnung, "ram:SpecifiedTradePaymentTerms")
        if r.zahlungsbedingungen:
            text = r.zahlungsbedingungen
            if "#SKONTO#" in text and not text.endswith("\n"):
                text += "\n"  # BR-DE-18: jede Skonto-Angabe endet mit Zeilenumbruch
            _el(bedingungen, "ram:Description", text)
        if r.faellig:
            _datum(bedingungen, "ram:DueDateDateTime", r.faellig)

    s = r.summen
    summe = _el(abrechnung, "ram:SpecifiedTradeSettlementHeaderMonetarySummation")
    for feld, wert in (
        ("ram:LineTotalAmount", s.positionen_netto),
        ("ram:ChargeTotalAmount", s.zuschlaege),
        ("ram:AllowanceTotalAmount", s.abschlaege),
        ("ram:TaxBasisTotalAmount", s.netto),
    ):
        if wert is not None:
            _el(summe, feld, _betrag(wert))
    if s.steuer is not None:
        _el(
            summe,
            "ram:TaxTotalAmount",
            _betrag(s.steuer),
            currencyID=r.waehrung or "EUR",
        )
    for feld, wert in (
        ("ram:RoundingAmount", s.rundung),
        ("ram:GrandTotalAmount", s.brutto),
        ("ram:TotalPrepaidAmount", s.vorauszahlung),
        ("ram:DuePayableAmount", s.zahlbetrag),
    ):
        if wert is not None:
            _el(summe, feld, _betrag(wert))

    ET.indent(wurzel, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        wurzel, encoding="unicode"
    ).encode("utf-8")
