# Marktplatz-Fixtures

Anonymisierte, von Hand nachgebaute Berichte — **keine echten Daten**. Aufbau, Spalten und
Zahlenformate folgen der öffentlichen Dokumentation der Anbieter (Stand Oktober 2026, Quellen im
Plan `docs/plans/2026-10-25-integrationen-export.md`); Namen, Orte, Bestell- und
Transaktionsnummern sind erfunden.

| Datei | Format | Inhalt |
|-------|--------|--------|
| `amazon_abrechnung_v2.txt` | Amazon Flat File V2 (tab-getrennt, Beträge `95,00`) | Abrechnung 11223344556, 01.–15.08.2026: Bestellungen DE/FR/IT/AT/CH, Rabatt, Erstattung mit Provisionsrückvergütung, FBA-, Lager-, Grundgebühr, Werbung, Reserve (Vorperiode frei, neu einbehalten), Ersatz für beschädigte Ware; Auszahlung 209,85 € |
| `amazon_bestellungen.txt` | Amazon-Bestellbericht (`ship-country`) | Bestimmungsland je Bestellung |
| `ebay_transaktionsbericht.csv` | eBay-Transaktionsbericht (Semikolon) | zwei Auszahlungen (139,35 € und 44,69 €) mit Bestellungen DE/FR/AT/IT, Rückerstattung, Shop-Abo, Versandetikett, Einbehalt; eine noch nicht ausgezahlte Bestellung |
| `ebay_transaktionsbericht_gbp.csv` | eBay-Transaktionsbericht (Semikolon), Auszahlung in GBP | Auszahlung 6009990001 (51,68 GBP): Bestellung nach Großbritannien mit Provisionen und internationaler Gebühr — prüft den Weg über `--kurs` |
| `paypal_aktivitaeten.csv` | PayPal-Aktivitäten (41 Spalten) | Guthaben 100,00 → 112,36 €: Verkäufe DE/FR, USD-Verkauf mit Währungsumrechnung, Rückzahlung, Einkauf, Abbuchung aufs Bankkonto, Bankgutschrift, eine ausstehende Zahlung |
| `paypal_sonderfaelle.csv` | PayPal-Aktivitäten (41 Spalten) | Guthaben 100,00 → 96,82 €: Checkout-Verkauf, Einbehaltung für offene Konfliktlösung und ihre Freigabe, Rückbuchung (Chargeback), Allgemeine Zahlung eines Kunden auf eine Ausgangsrechnung, Einkauf und Rückzahlung des Lieferanten, Rückzahlung an den Kunden zu seiner Allgemeinen Zahlung (keine Erlösminderung) |
| `shopify_auszahlung.csv` | Shopify-Payments-Transaktionen | Auszahlung 87654321098 (125,39 €): Verkäufe DE/NL/ES, Erstattung, Korrektur; eine noch nicht ausgezahlte Zahlung |
| `shopify_auszahlung_gbp.csv` | Shopify-Payments-Transaktionen in GBP | Auszahlung 87654321555 (52,95 GBP): Verkäufe GB/NL, Reserve (Einbehalt) — prüft `--kurs` und Einbehalt |
| `shopify_bestellungen.csv` | Shopify-Bestellexport (`Shipping Country`) | Bestimmungsland je Bestellung |
