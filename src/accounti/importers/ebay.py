"""eBay-Transaktionsbericht → eine Abrechnung je Auszahlung.

Format: Transaktionsbericht aus dem Verkäufer-Cockpit Pro (Zahlungen › Berichte), CSV.
eBay lässt die Spalten konfigurieren und hat sie mehrfach umbenannt; deshalb werden
Spalten über mehrere bekannte Namen gesucht. Je Zeile: ``Typ``, Bestellnummer,
Versandziel-Land, Transaktionsbetrag (inkl. Kosten) = Bruttozahlung des Käufers, die
Provisionsspalten und der Nettobetrag nach Gebühren. Jede Zeile gehört über
„Auszahlung Nr.“ zu einer Auszahlung; die Zeile vom Typ „Auszahlung“ ist die
Überweisung selbst. Zeilen ohne Auszahlung (noch nicht ausgezahlt) bleiben draußen.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from accounti.importers.marktplatz import (
    MarktplatzFormatError,
    MarktplatzImporter,
    Zeile,
    dekodiere,
    erkenne_dezimal,
    land_iso,
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

# logischer Name -> bekannte Spaltennamen (deutsch, ältere Fassung, englisch)
_SPALTEN: dict[str, tuple[str, ...]] = {
    "datum": (
        "Datum der Transaktionserstellung",
        "Transaktionsdatum",
        "Transaction creation date",
    ),
    "typ": ("Typ", "Type"),
    "bestellung": ("Bestellnummer", "Bestellnr.", "Order number"),
    "land": ("Versandziel - Land", "Versand an Land", "Ship to country"),
    "netto": ("Betrag abzügl. Kosten", "Nettobetrag", "Net amount"),
    "brutto": (
        "Transaktionsbetrag (inkl. Kosten)",
        "Transaktionsbetrag",
        "Gross transaction amount",
    ),
    "auszahlung": ("Auszahlung Nr.", "Auszahlungsnr.", "Payout ID"),
    "auszahlungsdatum": ("Auszahlungsdatum", "Payout date"),
    "waehrung": ("Auszahlungswährung", "Transaktionswährung", "Payout currency"),
    "beschreibung": ("Beschreibung", "Description", "Angebotstitel", "Item title"),
    "kaeufer": ("Name des Käufers", "Buyer name"),
}
_GEBUEHREN = (
    "Fixer Anteil der Verkaufsprovision",
    "Variabler Anteil der Verkaufsprovision",
    "Gebühr für sehr hohe Quote an „nicht wie beschriebenen Artikeln“",
    "Gebühr für unterdurchschnittlichen Servicestatus",
    "Internationale Gebühr",
    "Final Value Fee - fixed",
    "Final Value Fee - variable",
    'Very high "item not as described" fee',
    "Below standard performance fee",
    "International fee",
)

NULL = Decimal("0")


def _typ(text: str, beschreibung: str) -> tuple[Postenart, Gebuehrenart | None]:
    t, b = text.casefold(), beschreibung.casefold()
    if t in {"bestellung", "order"}:
        return Postenart.ERLOES, None
    if t in {"rückerstattung", "rueckerstattung", "refund"}:
        return Postenart.ERSTATTUNG, None
    if t in {"auszahlung", "payout"}:
        return Postenart.AUSZAHLUNG, None
    if "versandetikett" in t or "shipping label" in t:
        return Postenart.GEBUEHR, Gebuehrenart.VERSAND
    if "gebühr" in t or "fee" in t:
        if "anzeige" in b or "promoted" in b or "werbung" in b:
            return Postenart.WERBUNG, None
        return Postenart.GEBUEHR, Gebuehrenart.SONSTIGE
    if "einbehalt" in t or "hold" in t:
        return Postenart.EINBEHALT, None
    return Postenart.SONSTIGES, None


@dataclass
class _Zeile:
    nr: int
    werte: dict[str, str]  # logischer Name -> Wert
    gebuehren: dict[str, str]  # Spaltenname -> Wert
    datum: date


class EbayImporter(MarktplatzImporter):
    name = "ebay"
    beschreibung = "eBay-Transaktionsbericht (CSV aus dem Verkäufer-Cockpit Pro)"

    def lies(
        self,
        inhalt: bytes,
        dateiname: str,
        laender: dict[str, Laenderangabe] | None = None,
    ) -> list[Abrechnung]:
        kopf, zeilen = self._tabelle(dekodiere(inhalt))
        spalten = {n: spalte(kopf, *namen) for n, namen in _SPALTEN.items()}
        fehlend = [n for n in ("datum", "typ", "netto", "auszahlung") if not spalten[n]]
        if fehlend:
            msg = f"eBay-Transaktionsbericht: Spalten fehlen ({', '.join(fehlend)})"
            raise MarktplatzFormatError(msg)
        gebuehren = [g for g in (spalte(kopf, n) for n in _GEBUEHREN) if g]

        gruppen: dict[str, list[_Zeile]] = defaultdict(list)
        offen = 0
        for nr, w in zeilen:
            werte = {n: (w.get(s, "") if s else "") for n, s in spalten.items()}
            if not werte["auszahlung"]:
                offen += 1
                continue
            gruppen[werte["auszahlung"]].append(
                _Zeile(
                    nr,
                    werte,
                    {g: w.get(g, "") for g in gebuehren},
                    lies_datum(werte["datum"]),
                )
            )
        if not gruppen:
            raise MarktplatzFormatError("keine ausgezahlten Transaktionen im Bericht")
        dezimal = erkenne_dezimal(z.werte["netto"] for g in gruppen.values() for z in g)

        abrechnungen = []
        for nummer, gruppe in gruppen.items():
            erste = gruppe[0].werte
            abrechnung = Abrechnung(
                marktplatz=self.name,
                nummer=nummer,
                von=min(z.datum for z in gruppe),
                bis=max(z.datum for z in gruppe),
                auszahlungsdatum=(
                    lies_datum(erste["auszahlungsdatum"])
                    if erste["auszahlungsdatum"]
                    else None
                ),
                waehrung=erste["waehrung"] or "EUR",
                dateiname=dateiname,
            )
            for zeile in gruppe:
                self._zeile(abrechnung, zeile, dezimal)
            if any(p.art is Postenart.AUSZAHLUNG for p in abrechnung.posten):
                abrechnung.auszahlung = -abrechnung.summe(Postenart.AUSZAHLUNG)
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

    @staticmethod
    def _tabelle(text: str) -> tuple[list[str], list[Zeile]]:
        for typ in _SPALTEN["typ"]:
            for netto in _SPALTEN["netto"]:
                try:
                    return lies_tabelle(text, {typ, netto})
                except MarktplatzFormatError:
                    continue
        raise MarktplatzFormatError("Kopfzeile des eBay-Transaktionsberichts fehlt")

    def _zeile(self, abrechnung: Abrechnung, zeile: _Zeile, dezimal: str) -> None:
        w, nr = zeile.werte, zeile.nr
        art, gebuehrenart = _typ(w["typ"], w["beschreibung"])
        netto = lies_betrag(w["netto"], dezimal)
        bestellung = w["bestellung"] or None
        text = f"{w['typ']}: {w['beschreibung']}".strip(": ")

        def posten(
            art: Postenart,
            betrag: Decimal,
            beschreibung: str,
            gebuehrenart: Gebuehrenart | None = None,
            land: str | None = None,
        ) -> Marktplatzposten:
            return Marktplatzposten(
                nr=nr,
                art=art,
                datum=zeile.datum,
                betrag=betrag,
                waehrung=abrechnung.waehrung,
                beschreibung=beschreibung,
                gebuehrenart=gebuehrenart,
                bestellnummer=bestellung,
                bestimmungsland=land,
                auszahlungs_nr=abrechnung.nummer,
                gegenpartei=w["kaeufer"] or None,
            )

        def befund(code: str, schwere: Schweregrad, text: str) -> None:
            abrechnung.befunde.append(
                Befund(code=code, schweregrad=schwere, text=text, posten_nr=nr)
            )

        if art not in (Postenart.ERLOES, Postenart.ERSTATTUNG):
            abrechnung.posten.append(posten(art, netto, text, gebuehrenart))
            if art is Postenart.SONSTIGES:
                befund(
                    "unbekannter_posten",
                    Schweregrad.WARNUNG,
                    f"Zeile {nr}: Typ {w['typ']!r} ist nicht zugeordnet — zur Prüfung",
                )
            return

        brutto = lies_betrag(w["brutto"], dezimal) if w["brutto"] else netto
        land = land_iso(w["land"])
        abrechnung.posten.append(posten(art, brutto, text, land=land))
        if w["land"] and land is None:
            befund(
                "land_unbekannt",
                Schweregrad.WARNUNG,
                f"Zeile {nr}: Land {w['land']!r} unbekannt",
            )
        summe = NULL
        for spaltenname, roh in zeile.gebuehren.items():
            betrag = lies_betrag(roh, dezimal)
            if betrag:
                summe += betrag
                abrechnung.posten.append(
                    posten(Postenart.GEBUEHR, betrag, spaltenname, Gebuehrenart.VERKAUF)
                )
        if brutto + summe != netto:
            befund(
                "zeile_rechnet_nicht",
                Schweregrad.FEHLER,
                f"Zeile {nr} ({bestellung}): Brutto {brutto} + Gebühren {summe} "
                f"≠ Netto {netto}",
            )


registriere(EbayImporter())
