"""Kleine Marktplatzberichte für Tests (nach dem Aufbau der Fixtures)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "marktplatz"

EBAY_KOPF = (
    '"Datum der Transaktionserstellung";"Typ";"Bestellnummer";"Versandziel - Land";'
    '"Betrag abzügl. Kosten";"Auszahlungswährung";"Auszahlungsdatum";'
    '"Auszahlung Nr.";"Transaktionsbetrag (inkl. Kosten)";"Beschreibung"'
)


def ebay_bericht(*zeilen: tuple[str, str, str, str, str, str, str]) -> bytes:
    """(Datum, Typ, Bestellnummer, Land, Betrag, Auszahlung Nr., Auszahlungsdatum)."""
    text = [EBAY_KOPF]
    for datum, typ, bestellung, land, betrag, nummer, auszahlungsdatum in zeilen:
        werte = [
            datum,
            typ,
            bestellung,
            land,
            betrag,
            "EUR",
            auszahlungsdatum,
            nummer,
            betrag if typ == "Bestellung" else "",
            "",
        ]
        text.append(";".join(f'"{w}"' for w in werte))
    return ("\r\n".join(text) + "\r\n").encode("utf-8")


def paypal_bericht(*zeilen: dict[str, str]) -> bytes:
    """PayPal-Aktivitäten mit der Kopfzeile der Fixture; je Zeile Spalte → Wert."""
    quelle = (FIXTURES / "paypal_aktivitaeten.csv").read_text(encoding="utf-8-sig")
    kopf = next(csv.reader(io.StringIO(quelle.splitlines()[0])))
    aus = io.StringIO()
    schreiber = csv.writer(aus, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    schreiber.writerow(kopf)
    for werte in zeilen:
        vorgabe = {
            "Zeitzone": "Europe/Berlin",
            "Status": "Abgeschlossen",
            "Währung": "EUR",
            "Gebühr": "0,00",
        }
        vorgabe.update(werte)
        schreiber.writerow([vorgabe.get(k, "") for k in kopf])
    return aus.getvalue().encode("utf-8")
