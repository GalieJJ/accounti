"""Gemeinsame Bausteine der Marktplatz-Importer (Baustein 11).

Ein Marktplatz-Importer liest einen Bericht (Abrechnung, Transaktionsbericht,
Aktivitäten) und liefert `Abrechnung`-Objekte mit ihren Posten. Er kennt nur sein
Format — Konten, Steuer und Abgleich passieren in ``accounti.integrationen``.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections.abc import Iterable
from datetime import date
from decimal import Decimal, InvalidOperation

from accounti.models.integrationen import Abrechnung, Laenderangabe
from accounti.steuer.eu_steuersaetze import EU_STEUERSAETZE


class MarktplatzFormatError(ValueError):
    """Die Datei ist kein lesbarer Bericht dieses Marktplatzes."""


class MarktplatzImporter:
    """Basisklasse: ``lies`` macht aus einer Datei eine oder mehrere Abrechnungen."""

    name: str = "base"
    beschreibung: str = ""

    def lies(
        self,
        inhalt: bytes,
        dateiname: str,
        laender: dict[str, Laenderangabe] | None = None,
    ) -> list[Abrechnung]:
        raise NotImplementedError


# Registry: Marktplatzname -> Importer (füllen die Module amazon, ebay, paypal, shopify)
MARKTPLATZ_IMPORTER: dict[str, MarktplatzImporter] = {}


def registriere(importer: MarktplatzImporter) -> MarktplatzImporter:
    MARKTPLATZ_IMPORTER[importer.name] = importer
    return importer


# ---------------------------------------------------------------------------
# Text, Beträge, Daten
# ---------------------------------------------------------------------------


def dekodiere(inhalt: bytes) -> str:
    """UTF-8 (mit oder ohne BOM), sonst Windows-1252."""
    try:
        return inhalt.decode("utf-8-sig")
    except UnicodeDecodeError:
        return inhalt.decode("cp1252", errors="replace")


_MINUS = str.maketrans({"−": "-", "–": "-", " ": " ", " ": " "})


def erkenne_dezimal(werte: Iterable[str]) -> str:
    """Dezimaltrennzeichen einer Datei: ``,`` (Vorgabe) oder ``.``."""
    for wert in werte:
        w = wert.strip()
        if re.search(r",\d{1,2}$", w):
            return ","
        if re.search(r"\.\d{1,2}$", w):
            return "."
    return ","


def lies_betrag(text: str, dezimal: str = ",") -> Decimal:
    """Betrag mit Vorzeichen; Tausenderpunkte, Währungszeichen, Klammern egal."""
    roh = (text or "").translate(_MINUS).strip()
    if not roh:
        return Decimal("0")
    negativ = roh.startswith("(") and roh.endswith(")")
    roh = re.sub(r"[^\d,.\-]", "", roh)
    if roh.startswith("-"):
        negativ, roh = True, roh[1:]
    tausender = "." if dezimal == "," else ","
    roh = roh.replace(tausender, "").replace(dezimal, ".")
    if not re.fullmatch(r"\d+(\.\d+)?", roh):
        msg = f"Betrag {text!r} ist nicht lesbar"
        raise MarktplatzFormatError(msg)
    try:
        wert = Decimal(roh)
    except InvalidOperation as fehler:  # pragma: no cover — vom Muster abgefangen
        raise MarktplatzFormatError(f"Betrag {text!r} ist nicht lesbar") from fehler
    return -wert if negativ else wert


_MONATE = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "mär": 3,
    "maer": 3,
    "apr": 4,
    "may": 5,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "okt": 10,
    "nov": 11,
    "dec": 12,
    "dez": 12,
}


def lies_datum(text: str) -> date:
    """Datum aus den gängigen Berichtsformaten; Uhrzeit und Zeitzone fallen weg."""
    roh = (text or "").strip()
    if m := re.match(r"(\d{4})-(\d{2})-(\d{2})", roh):
        return date(int(m[1]), int(m[2]), int(m[3]))
    if m := re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})\b", roh):
        jahr = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
        return date(jahr, int(m[2]), int(m[1]))
    if m := re.match(r"(\d{1,2})\.?\s*([A-Za-zäÄ]{3})[a-zä]*\.?\s+(\d{4})", roh):
        monat = _MONATE.get(m[2].lower())
        if monat:
            return date(int(m[3]), monat, int(m[1]))
    if m := re.match(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", roh):
        monat = _MONATE.get(m[1].lower())
        if monat:
            return date(int(m[3]), monat, int(m[2]))
    msg = f"Datum {text!r} ist nicht lesbar"
    raise MarktplatzFormatError(msg)


# ---------------------------------------------------------------------------
# Länder
# ---------------------------------------------------------------------------


def _schluessel(text: str) -> str:
    zerlegt = unicodedata.normalize("NFKD", text.casefold())
    return re.sub(r"[^a-z]", "", zerlegt.encode("ascii", "ignore").decode())


_LAENDER: dict[str, str] = {}
for _code, _info in EU_STEUERSAETZE.items():
    _LAENDER[_schluessel(_info.land_name)] = _code
    _LAENDER[_schluessel(_info.land_name_en)] = _code
_LAENDER.update(
    {
        _schluessel(name): code
        for name, code in [
            ("Schweiz", "CH"),
            ("Switzerland", "CH"),
            ("Liechtenstein", "LI"),
            ("Norwegen", "NO"),
            ("Norway", "NO"),
            ("Island", "IS"),
            ("Iceland", "IS"),
            ("Großbritannien", "GB"),
            ("Great Britain", "GB"),
            ("UK", "GB"),
            ("England", "GB"),
            ("Vereinigte Staaten", "US"),
            ("Vereinigte Staaten von Amerika", "US"),
            ("United States", "US"),
            ("United States of America", "US"),
            ("USA", "US"),
            ("Kanada", "CA"),
            ("Canada", "CA"),
            ("Türkei", "TR"),
            ("Turkey", "TR"),
            ("Australien", "AU"),
            ("Australia", "AU"),
            ("Japan", "JP"),
            ("Tschechische Republik", "CZ"),
            ("Czechia", "CZ"),
            ("Holland", "NL"),
        ]
    }
)


def land_iso(text: str | None) -> str | None:
    """ISO-3166-Code aus Code oder Ländernamen (deutsch/englisch); unbekannt → None."""
    roh = (text or "").strip()
    if not roh:
        return None
    if re.fullmatch(r"[A-Za-z]{2}", roh):
        code = roh.upper()
        return "GR" if code == "EL" else code
    return _LAENDER.get(_schluessel(roh))


# ---------------------------------------------------------------------------
# Tabellen
# ---------------------------------------------------------------------------

Zeile = tuple[int, dict[str, str]]


def _trenner(zeile: str) -> str:
    return max(["\t", ";", ","], key=zeile.count)


def lies_tabelle(text: str, pflicht: set[str]) -> tuple[list[str], list[Zeile]]:
    """Sucht die Kopfzeile (enthält alle ``pflicht``-Spalten) und liest die Zeilen.

    Liefert die Kopfzeile und je Datenzeile (Zeilennummer in der Datei, Werte nach
    Spaltenname). Vorspann vor der Kopfzeile und Leerzeilen werden übergangen.
    """
    zeilen = text.splitlines()
    for index, zeile in enumerate(zeilen):
        if not zeile.strip():
            continue
        trenner = _trenner(zeile)
        kopf = [k.strip() for k in next(csv.reader([zeile], delimiter=trenner))]
        if not pflicht <= set(kopf):
            continue
        rest = "\n".join(zeilen[index + 1 :])
        daten: list[Zeile] = []
        for nr, werte in enumerate(
            csv.reader(io.StringIO(rest), delimiter=trenner), start=index + 2
        ):
            if not any(w.strip() for w in werte):
                continue
            werte += [""] * (len(kopf) - len(werte))
            daten.append((nr, {k: werte[i].strip() for i, k in enumerate(kopf)}))
        return kopf, daten
    fehlend = ", ".join(sorted(pflicht))
    msg = f"Kopfzeile mit den Spalten {fehlend} nicht gefunden"
    raise MarktplatzFormatError(msg)


def spalte(kopf: list[str], *namen: str) -> str | None:
    """Der erste vorhandene Spaltenname (Berichte benennen Spalten unterschiedlich)."""
    vorhanden = {k.casefold(): k for k in kopf}
    for name in namen:
        if name.casefold() in vorhanden:
            return vorhanden[name.casefold()]
    return None


# Länderdatei: Bestellnummer → Bestimmungsland, Abgangsland, USt-IdNr. des Käufers
_BESTELLNUMMER = (
    "amazon-order-id",
    "order-id",
    "TRANSACTION_EVENT_ID",
    "Name",
    "Order",
    "Bestellnummer",
)
_BESTIMMUNG = (
    "ship-country",
    "SALE_ARRIVAL_COUNTRY",
    "ARRIVAL_COUNTRY",
    "Shipping Country",
    "Versandziel - Land",
    "Billing Country",
)
_ABGANG = ("SALE_DEPART_COUNTRY", "DEPARTURE_COUNTRY", "ship-from-country")
_UST_ID = ("BUYER_VAT_NUMBER", "buyer-vat-number", "buyer-tax-registration")
_VERSAND = ("fulfillment-channel",)  # Amazon (FBA) oder Merchant
_GESCHAEFT = ("is-business-order",)


def _ja_nein(text: str, ja: set[str], nein: set[str]) -> bool | None:
    wert = text.strip().casefold()
    return True if wert in ja else False if wert in nein else None


def lies_laenderdatei(inhalt: bytes) -> dict[str, Laenderangabe]:
    """Liest einen Zusatzbericht mit Bestellnummer und Lieferland.

    Unterstützt den Amazon-USt-Transaktionsbericht (``TRANSACTION_EVENT_ID``,
    ``SALE_ARRIVAL_COUNTRY``, ``SALE_DEPART_COUNTRY``, ``BUYER_VAT_NUMBER`` —
    empfohlen, weil er das Abgangsland kennt), den Amazon-Bestellbericht
    (``amazon-order-id``, ``ship-country``, ``fulfillment-channel``,
    ``is-business-order`` — ohne Abgangsland und USt-IdNr.) und den
    Shopify-Bestellexport (``Name``, ``Shipping Country``).
    """
    text = dekodiere(inhalt)
    erste = next((z for z in text.splitlines() if z.strip()), "")
    kopf = [k.strip() for k in next(csv.reader([erste], delimiter=_trenner(erste)))]
    nummer = spalte(kopf, *_BESTELLNUMMER)
    bestimmung = spalte(kopf, *_BESTIMMUNG)
    if nummer is None or bestimmung is None:
        msg = (
            "Länderdatei: Spalten für Bestellnummer und Lieferland fehlen "
            "(z.B. amazon-order-id/ship-country oder Name/Shipping Country)"
        )
        raise MarktplatzFormatError(msg)
    kopf, zeilen = lies_tabelle(text, {nummer, bestimmung})
    abgang = spalte(kopf, *_ABGANG)
    ust_id = spalte(kopf, *_UST_ID)
    versand = spalte(kopf, *_VERSAND)
    geschaeft = spalte(kopf, *_GESCHAEFT)
    ergebnis: dict[str, Laenderangabe] = {}
    for _nr, werte in zeilen:
        schluessel = werte[nummer].strip()
        if not schluessel or schluessel in ergebnis:
            continue  # eine Bestellung mit mehreren Artikeln steht mehrfach drin
        ergebnis[schluessel] = Laenderangabe(
            bestellnummer=schluessel,
            bestimmungsland=land_iso(werte[bestimmung]),
            abgangsland=land_iso(werte[abgang]) if abgang else None,
            kaeufer_ust_id=(werte[ust_id].replace(" ", "") or None) if ust_id else None,
            versand_durch_marktplatz=(
                _ja_nein(werte[versand], {"amazon", "afn"}, {"merchant", "mfn"})
                if versand
                else None
            ),
            geschaeftskunde=(
                _ja_nein(werte[geschaeft], {"true", "ja", "1"}, {"false", "nein", "0"})
                if geschaeft
                else None
            ),
        )
    return ergebnis


# Importer registrieren (füllt MARKTPLATZ_IMPORTER)
from accounti.importers import amazon, ebay, paypal, shopify  # noqa: E402, F401
