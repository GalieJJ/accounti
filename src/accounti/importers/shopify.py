"""Shopify-Payments-Auszahlung (Transaktionen-CSV) → eine Abrechnung je Auszahlung.

Format laut Shopify-Hilfe („View payout details“, Export der Transaktionen einer
Auszahlung bzw. aller Transaktionen): ``Transaction Date, Type, Order, Card Brand,
Card Source, Payout Status, Payout Date, Available On, Amount, Fee, Net`` — je nach
Export zusätzlich ``Payout ID``, ``Currency``, ``Presentment Amount``. ``Net`` ist
``Amount`` minus ``Fee``; die Gebühr steht positiv in der Datei.

Den Auszahlungsbetrag selbst enthält die Datei nicht; er ist die Summe der Posten und
wird gegen den Bankumsatz geprüft (oder mit ``--auszahlung`` aus der Auszahlungsliste
vorgegeben). Das Bestimmungsland kommt aus dem Bestellexport (``Shipping Country``).
"""

from __future__ import annotations

from collections import defaultdict

from accounti.importers.marktplatz import (
    MarktplatzFormatError,
    MarktplatzImporter,
    Zeile,
    dekodiere,
    erkenne_dezimal,
    lies_betrag,
    lies_datum,
    lies_tabelle,
    registriere,
    spalte,
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

PFLICHT = {"Transaction Date", "Type", "Amount", "Fee", "Net"}


def _art(typ: str) -> Postenart:
    t = typ.casefold()
    if t in {"charge", "sale"}:
        return Postenart.ERLOES
    if t == "refund":
        return Postenart.ERSTATTUNG
    if t in {"reserve", "reserved_funds"}:
        return Postenart.EINBEHALT
    if t == "payout":
        return Postenart.AUSZAHLUNG
    return Postenart.SONSTIGES  # adjustment, dispute, chargeback, …


class ShopifyImporter(MarktplatzImporter):
    name = "shopify"
    beschreibung = "Shopify-Payments-Auszahlung (Transaktionen als CSV)"

    def lies(
        self,
        inhalt: bytes,
        dateiname: str,
        laender: dict[str, Laenderangabe] | None = None,
    ) -> list[Abrechnung]:
        kopf, zeilen = lies_tabelle(dekodiere(inhalt), PFLICHT)
        s_id = spalte(kopf, "Payout ID")
        s_datum = spalte(kopf, "Payout Date")
        s_status = spalte(kopf, "Payout Status")
        s_waehrung = spalte(kopf, "Currency")
        s_order = spalte(kopf, "Order")
        if s_id is None and s_datum is None:
            raise MarktplatzFormatError("Shopify-Export ohne Payout ID und Payout Date")
        dezimal = erkenne_dezimal(w["Amount"] for _, w in zeilen)
        laender = laender or {}

        gruppen: dict[str, list[Zeile]] = defaultdict(list)
        offen = 0
        for nr, w in zeilen:
            schluessel = (w.get(s_id, "") if s_id else "") or (
                w.get(s_datum, "") if s_datum else ""
            )
            status = w.get(s_status, "").casefold() if s_status else "paid"
            if not schluessel or status in {"pending", "scheduled", "failed"}:
                offen += 1
                continue
            gruppen[schluessel].append((nr, w))
        if not gruppen:
            raise MarktplatzFormatError("keine ausgezahlten Transaktionen im Export")

        abrechnungen = []
        for nummer, gruppe in gruppen.items():
            erste = gruppe[0][1]
            daten = [lies_datum(w["Transaction Date"]) for _, w in gruppe]
            abrechnung = Abrechnung(
                marktplatz=self.name,
                nummer=nummer,
                von=min(daten),
                bis=max(daten),
                auszahlungsdatum=(
                    lies_datum(erste[s_datum]) if s_datum and erste[s_datum] else None
                ),
                waehrung=(erste.get(s_waehrung, "") if s_waehrung else "") or "EUR",
                dateiname=dateiname,
            )
            for (nr, w), datum in zip(gruppe, daten, strict=True):
                art = _art(w["Type"])
                bestellung = (w.get(s_order, "") if s_order else "") or None
                angabe = laender.get(bestellung or "")
                betrag = lies_betrag(w["Amount"], dezimal)
                gebuehr = lies_betrag(w["Fee"], dezimal)
                netto = lies_betrag(w["Net"], dezimal)
                abrechnung.posten.append(
                    Marktplatzposten(
                        nr=nr,
                        art=art,
                        datum=datum,
                        betrag=betrag,
                        waehrung=abrechnung.waehrung,
                        beschreibung=f"{w['Type']} {bestellung or ''}".strip(),
                        bestellnummer=bestellung,
                        bestimmungsland=angabe.bestimmungsland if angabe else None,
                        kaeufer_ust_id=angabe.kaeufer_ust_id if angabe else None,
                        auszahlungs_nr=nummer,
                    )
                )
                if gebuehr:
                    abrechnung.posten.append(
                        Marktplatzposten(
                            nr=nr,
                            art=Postenart.GEBUEHR,
                            datum=datum,
                            betrag=-gebuehr,
                            waehrung=abrechnung.waehrung,
                            beschreibung=(
                                f"Gebühr {w['Type']} {bestellung or ''}".strip()
                            ),
                            gebuehrenart=Gebuehrenart.ZAHLUNG,
                            bestellnummer=bestellung,
                            auszahlungs_nr=nummer,
                        )
                    )
                if betrag - gebuehr != netto:
                    abrechnung.befunde.append(
                        Befund(
                            code="zeile_rechnet_nicht",
                            schweregrad=Schweregrad.FEHLER,
                            text=f"Zeile {nr}: Amount − Fee ≠ Net",
                            posten_nr=nr,
                        )
                    )
                if art is Postenart.SONSTIGES:
                    abrechnung.befunde.append(
                        Befund(
                            code="unbekannter_posten",
                            schweregrad=Schweregrad.WARNUNG,
                            text=(
                                f"Zeile {nr}: Typ {w['Type']!r} ist nicht zugeordnet "
                                "— zur Prüfung"
                            ),
                            posten_nr=nr,
                        )
                    )
            abrechnungen.append(abrechnung)
        if offen:
            abrechnungen[-1].befunde.append(
                Befund(
                    code="nicht_ausgezahlt",
                    schweregrad=Schweregrad.HINWEIS,
                    text=(
                        f"{offen} Zeile(n) noch nicht ausgezahlt — nicht übernommen; "
                        "nach der Auszahlung erneut importieren"
                    ),
                )
            )
        return abrechnungen


registriere(ShopifyImporter())
