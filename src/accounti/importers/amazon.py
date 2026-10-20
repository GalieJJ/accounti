"""Amazon-Abrechnungsbericht (Flat File V2) → eine Abrechnung je Settlement-ID.

Format: ``GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2`` aus Seller Central bzw. der
SP-API, tab-getrennt, 24 Spalten. Die erste Datenzeile ist die Kopfzeile der
Abrechnung (Zeitraum, Auszahlungsdatum, ``total-amount``), danach je Bestandteil eine
Zeile mit ``transaction-type``, ``amount-type``, ``amount-description`` und ``amount``.
Beträge stehen im lokalen Format (in der EU ``95,00``).

Das Bestimmungsland steht **nicht** im Abrechnungsbericht; es kommt aus einer
Länderdatei (Bestellbericht oder USt-Transaktionsbericht), siehe
``importers.marktplatz.lies_laenderdatei``.
"""

from __future__ import annotations

from accounti.importers.marktplatz import (
    MarktplatzFormatError,
    MarktplatzImporter,
    dekodiere,
    erkenne_dezimal,
    lies_betrag,
    lies_datum,
    lies_tabelle,
    registriere,
)
from accounti.models.integrationen import (
    Abrechnung,
    Befund,
    Gebuehrenart,
    Laenderangabe,
    Marktplatzposten,
    Postenart,
    Schweregrad,
)

PFLICHT = {
    "settlement-id",
    "settlement-start-date",
    "settlement-end-date",
    "deposit-date",
    "total-amount",
    "currency",
    "transaction-type",
    "order-id",
    "amount-type",
    "amount-description",
    "amount",
    "posted-date",
}

_ERSTATTUNG = {"refund", "chargeback refund", "a-to-z guarantee claim"}


def _art(
    transaktion: str, typ: str, beschreibung: str
) -> tuple[Postenart, Gebuehrenart | None]:
    t, a, b = transaktion.casefold(), typ.casefold(), beschreibung.casefold()
    if a in {"itemprice", "promotion"}:
        return (Postenart.ERSTATTUNG if t in _ERSTATTUNG else Postenart.ERLOES), None
    if "withheldtax" in a or "marketplacefacilitator" in b:
        return Postenart.SONSTIGES, None  # Steuer, die Amazon selbst abführt
    if "advertising" in a or "advertising" in b:
        return Postenart.WERBUNG, None
    if "reserve" in b:
        return Postenart.EINBEHALT, None
    if "reimbursement" in a or "reimbursement" in b:
        return Postenart.ERSATZ, None
    if a == "itemfees" or t == "servicefee" or "fee" in b:
        if "storage" in b:
            return Postenart.GEBUEHR, Gebuehrenart.LAGER
        if "fba" in b or "shipping" in b or "fulfil" in b:
            return Postenart.GEBUEHR, Gebuehrenart.VERSAND
        if "subscription" in b or t == "servicefee":
            return Postenart.GEBUEHR, Gebuehrenart.SONSTIGE
        return Postenart.GEBUEHR, Gebuehrenart.VERKAUF
    return Postenart.SONSTIGES, None


class AmazonImporter(MarktplatzImporter):
    name = "amazon"
    beschreibung = "Amazon-Abrechnungsbericht (Flat File V2, tab-getrennt)"

    def lies(
        self,
        inhalt: bytes,
        dateiname: str,
        laender: dict[str, Laenderangabe] | None = None,
    ) -> list[Abrechnung]:
        _kopf, zeilen = lies_tabelle(dekodiere(inhalt), PFLICHT)
        if not zeilen:
            raise MarktplatzFormatError("Abrechnungsbericht ohne Zeilen")
        dezimal = erkenne_dezimal(w["amount"] or w["total-amount"] for _, w in zeilen)
        kopfzeile = next((w for _, w in zeilen if w["total-amount"]), None)
        if kopfzeile is None:
            raise MarktplatzFormatError("Kopfzeile der Abrechnung (total-amount) fehlt")
        laender = laender or {}
        abrechnung = Abrechnung(
            marktplatz=self.name,
            nummer=kopfzeile["settlement-id"],
            von=lies_datum(kopfzeile["settlement-start-date"]),
            bis=lies_datum(kopfzeile["settlement-end-date"]),
            auszahlungsdatum=lies_datum(kopfzeile["deposit-date"]),
            waehrung=kopfzeile["currency"] or "EUR",
            auszahlung=lies_betrag(kopfzeile["total-amount"], dezimal),
            dateiname=dateiname,
        )
        for nr, w in zeilen:
            if w is kopfzeile or not (w["amount-type"] or w["transaction-type"]):
                continue
            if w["settlement-id"] != abrechnung.nummer:
                msg = f"Zeile {nr}: andere Settlement-ID {w['settlement-id']!r}"
                raise MarktplatzFormatError(msg)
            art, gebuehrenart = _art(
                w["transaction-type"], w["amount-type"], w["amount-description"]
            )
            bestellung = w["order-id"] or None
            angabe = laender.get(bestellung or "")
            posten = Marktplatzposten(
                nr=nr,
                art=art,
                datum=lies_datum(w["posted-date"] or w.get("posted-date-time", "")),
                betrag=lies_betrag(w["amount"], dezimal),
                waehrung=abrechnung.waehrung,
                beschreibung=f"{w['amount-type']}/{w['amount-description']}",
                gebuehrenart=gebuehrenart,
                bestellnummer=bestellung,
                artikel=w.get("sku") or None,
                bestimmungsland=angabe.bestimmungsland if angabe else None,
                abgangsland=angabe.abgangsland if angabe else None,
                kaeufer_ust_id=angabe.kaeufer_ust_id if angabe else None,
                auszahlungs_nr=abrechnung.nummer,
            )
            abrechnung.posten.append(posten)
            if art is Postenart.SONSTIGES:
                abrechnung.befunde.append(
                    Befund(
                        code="unbekannter_posten",
                        schweregrad=Schweregrad.WARNUNG,
                        text=(
                            f"Zeile {nr}: {w['transaction-type']} / "
                            f"{posten.beschreibung} ist nicht zugeordnet — "
                            "zur Prüfung gebucht"
                        ),
                        posten_nr=nr,
                    )
                )
        return [abrechnung]


registriere(AmazonImporter())
