# Integrationen & Export (ohne REST-API) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Marktplatz- und Zahlungsdienstleister-Abrechnungen (Amazon, eBay, PayPal, Shopify) kommen
vollständig und mit Bestimmungsland ins System: Erlöse, Gebühren, Erstattungen und Einbehalte werden
einzeln gebucht, die Auszahlung ist nur der Abgleichspunkt gegen die Bank, eine Abweichung ist ein
Befund. EU-Privatkundenverkäufe landen über `accounti.steuer` auf den OSS-Erlöskonten und in der
Quartalsmeldung. Die DATEV-Übergabe wird um Debitoren/Kreditoren, Belegbilder mit Beleglink am
Buchungssatz und lückenlos nummerierte Kontoauszüge mit schlüssigem Saldenverlauf ergänzt.

**Spec:** [`docs/specs/2026-08-10-integrationen-export.md`](../specs/2026-08-10-integrationen-export.md),
Abschnitte 4.2–4.6, 4.10 · Akzeptanzkriterien 1–6 · Akzeptanzkriterium 7 (REST-API) kommt mit
Baustein 10 · **Baut auf:** Baustein 2 (Belegarchiv), 4 (Kontakte), 5 (Bankkonten), `steuer/`

```
Marktplatzbericht ──▶ importers/<markt>.py ──▶ Abrechnung + Posten (Bestimmungsland je Bestellung)
 (+ Länderdatei)          nur Format                 │
                                                     ▼
              integrationen/lauf.py: Datei als Beleg archivieren · Summenprobe (Befund)
                                                     │
                     integrationen/buchung.py ──▶ Buchungssätze gegen das Verrechnungskonto
                     (Steuer: accounti.steuer)        Erlös je Bestellung (Inland/OSS/…),
                                                      Gebühren, Erstattungen, Einbehalte
                                                     │
                     integrationen/auszahlung.py ──▶ Auszahlung ↔ Bankumsatz (exakt, sonst Befund)
                                                     │
              steuer/oss.py ◀── OSS-Erlöskonten ─────┘   PayPal: jede Zeile ist ein Umsatz auf dem
                                                         PayPal-Konto (wie ein Bankkonto)
DATEV-Übergabe:
  kontakte ──▶ export/datev_stammdaten.py ──▶ EXTF Debitoren/Kreditoren (Kategorie 16, Version 5)
  Buchungen + Belegarchiv ──▶ export/datev_belege.py ──▶ Belegpaket (ZIP, document.xml v6.0)
                                                    └─▶ EXTF Buchungsstapel (Version 13) mit Beleglink
  Transaktionen je Finanzkonto ──▶ export/kontoauszuege.py ──▶ MT940 + Saldenverlauf (CSV)
```

## Recherche (Stand 20.10.2026, ergänzt nach der Prüfung)

| Thema | Ergebnis | Quelle (abgerufen 20.10.2026) |
|-------|----------|-------------------------------|
| DATEV-Format, Kopfzeile | 31 Felder; Textfelder 1, 4, 8, 9, 10, 17, 18, 22, 27, 31 in Anführungszeichen; Versionsnummer 700; Feld 27 Sachkontenrahmen (`"03"`); Feld 19 Buchungstyp 1 = Finanzbuchführung | DATEV Developer Portal, „DATEV-Format“, Musterdaten (`Musterdaten_DATEV_Format_0_7f9322b9cc.zip`: `EXTF_DebKred_Stamm.csv` vom 27.03.2024, `EXTF_Buchungsstapel.csv` vom 18.06.2025) |
| Debitoren/Kreditoren | Kategorie 16, Formatname `Debitoren/Kreditoren`, Formatversion 5, **254 Felder**; Spaltenüberschriften wörtlich aus der Musterdatei; Textfelder immer quotiert (auch leer `""`), Zahl/Datum/Betrag/Konto unquotiert; Personenkonto = Sachkontenlänge + 1 Stellen; Adressattyp 0 = keine Angabe, 1 = natürliche Person, 2 = Unternehmen; EU-UStID **ohne** Länderpräfix (Länderkennzeichen im Feld EU-Land); Datumsfelder `TTMMJJJJ`; Windows-1252 | Musterdatei wie oben; Feldbeschreibung `Format_Debitoren_Kreditoren.xml` (Version 5, Stand 21.10.2025) aus dem DATEV-Format-Prüfprogramm 2.2.3.0 (`Datev_Format_Pruefprogramm_2_2_3_0_76439824cb.zip`) |
| Buchungsstapel | Kategorie 21, Formatversion 13, **125 Spalten**; Feld 20 „Beleglink“ (Text, 210); BU-Schlüssel ist ein Textfeld (`"9"`); Belegdatum `TTMM` | Musterdatei + `Format_Buchungsstapel.xml` (Version 13) aus dem Prüfprogramm |
| Beleglink | Inhalt `BEDI "<GUID>"`, im CSV als Textfeld mit verdoppelten Anführungszeichen; die GUID ist die `guid` des Dokuments in der `document.xml`; Belegpaket per DATEV Belegtransfer (ZIP nicht entpacken), Buchungsstapel getrennt über die Stapelverarbeitung — Reihenfolge egal | Stotax-Hilfe „Export von Buchungen mit Belegen … (EXTF)“ (Spalte 20 „Beleglink“); Capitol-Schnittstellendoku (Beispiel `BEDI "CB6A…"`, „DATEV XML-Schnittstelle online v5.0“); AHA Consulting „Keine Buchung ohne Beleg“ (2025). DATEV-Dok. 1005516 „Buchungsdaten mit integriertem Beleglink…“ ist nur nach Anmeldung lesbar |
| Belegpaket | `document.xml` mit Namespace `http://xml.datev.de/bedi/tps/document/v06.0`, `version="6.0"`, `<document guid type processID>`, `<extension xsi:type="File" name="…"/>`, optional `<repository>`; GUID-Muster `8-4-4-4-12` Hex; `processID` 1 = buchungsrelevant (Posteingang, Gefahr der Doppelbuchung), 2 = archivierungsrelevant (Ordner, festgeschrieben); `type` 1 = Rechnungseingang, 2 = Rechnungsausgang, ohne = „ohne Belegtyp“; Dateinamen nur ASCII; je Paket ≤ 4999 Dokumente, ≤ 465 MB (empfohlen ~100 MB), je Datei ≤ 20 MB; keine verschachtelten ZIPs; leere Elemente/Attribute werden abgelehnt | DATEV Developer Portal „DATEV XML-Schnittstelle online“ (XSD-Paket `XSD_3c866dbe96.zip`, `Document_v060.xsd` vom 17.11.2022, Musterdaten `accounts_Receivable_Ledger_Ausgangsrechnungen`) |
| Kontoauszüge | DATEV Kanzlei-Rechnungswesen importiert Kontoumsätze weiter aus **MT940**-Dateien (auch nach Nov. 2025); ein manueller camt.053-Import ist dort nicht geplant | DATEV-Dok. 1036444 (Stand 03.12.2025, laut Suchtreffer; Volltext nicht abrufbar); datev.de „Kontoumsätze bereitstellen – neues Format“ (DK hat MT940 im Nov. 2025 aus dem Regelwerk genommen) |
| Belegfeld 1 | Muster `^(["][\w$&%*+\-\/]{0,36}["])$`: nur Buchstaben, Ziffern und `$ & % * + - /`; „Andere Zeichen sind unzulässig (insbesondere Leerzeichen, Umlaute, Punkt, Komma, Semikolon und Doppelpunkt)“; Schlüssel für den OPOS-Ausgleich | DATEV Developer Portal, „DATEV-Format“ › Formatbeschreibung Buchungsstapel, Feld 11 (Seiteninhalt als JSON abgerufen 20.10.2026) |
| BU-Schlüssel | Formatbeschreibung des Prüfprogramms: Text, Länge 4; das Muster im Developer Portal verlangt `"\d{4}"` — die Quellen widersprechen sich, die DATEV-Musterdatei schreibt ihn leer | `Format_Buchungsstapel.xml` (Prüfprogramm 2.2.3.0); Developer Portal wie oben |
| document.xml | `<content>` braucht **mindestens ein** `<document>` (minOccurs 1, maxOccurs 4999); `<description>` 1–40 Zeichen ohne weiteres Muster; Ablage `<repository>` mit `level` 1 = Kategorie, 2 = Ordner, 3 = Register, fehlende Ebenen legt Belege online an | `Document_v060.xsd`, `Document_types_v060.xsd` (Typ `p10052`) aus dem XSD-Paket wie oben |
| MT940 | `:20:` Referenz ≤16x · `:25:` BLZ/Konto-Nr. oder IBAN ≤35x · `:28C:` Auszugsnummer ≤5n `/` Blattnummer · `:60F:`/`:62F:` C/D + JJMMTT + Währung + Betrag mit Komma · `:61:` Valuta JJMMTT, Buchung MMTT, C/D, Betrag, `N` + Buchungsschlüssel (3c), Referenz (`NONREF`) · `:86:` ≤ 6×65 Zeichen, GVC mit erster Stelle 9 = unstrukturierte Belegung · Zeilen mit CRLF, Nachricht endet mit `-`; SWIFT-Zeichensatz | DK, DFÜ-Abkommen Anlage 3 „Spezifikation der Datenformate“ V3.3, Teil 5 „Kontoauszugsinformationen MT940/MT942“ und Teil 6 „Geschäftsvorfallcodes“ (Stand 17.11.2019, Fassung der Postbank) |
| Amazon | Flat-File-V2-Abrechnungsbericht (`GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2`), Tab-getrennt, 24 Spalten (`settlement-id` … `promotion-id`); Beträge im lokalen Format (`95,00` in der EU); bleibt verfügbar, während der XML- und der alte Flat-File-Bericht am 11.11.2026 entfallen; das Bestimmungsland steht **nicht** im Abrechnungsbericht | Amazon SP-API „Settlement reports attributes“ (updatedAt 14.10.2026), Changelog „Deprecation of two payment settlement report types“ |
| eBay | Transaktionsbericht (Verkäufer-Cockpit Pro › Zahlungen › Berichte), CSV mit u. a. „Datum der Transaktionserstellung“, „Typ“, „Bestellnummer“, „Versandziel - Land“, „Betrag abzügl. Kosten“/„Nettobetrag“, „Auszahlung Nr.“, Provisionsspalten, „Transaktionsbetrag (inkl. Kosten)“, „Transaktionswährung“, „Wechselkurs“; Spalten sind konfigurierbar | eBay-Hilfe 4847 „Abgleichen Ihrer eBay-Verkaufstransaktionen“; Taxpool-Forum „Probleme beim Import von Ebay Payment Dateien“; netzhandwerker.de (11.09.2026) |
| PayPal | Aktivitäten-CSV mit 41 Spalten „Datum, Uhrzeit, Zeitzone, Name, Typ, Status, Währung, Brutto, Gebühr, Netto, …, Zugehöriger Transaktionscode, …, Guthaben, …, Land, …, Auswirkung auf Guthaben“ | StarMoney-Forum (Kopfzeile wörtlich); PayPal-Hilfe „Kontoauszüge und Berichte herunterladen“ |
| Shopify | Auszahlungs-Transaktionen-CSV: Transaction Date, Type, Order, Card Brand, Card Source, Payout Status, Payout Date, Available On, Amount, Fee, Net | Shopify Help Center „View payout details“ |
| OSS | Lieferschwelle 10 000 € (Vorjahr **und** laufendes Jahr, § 3c Abs. 4 UStG; Verzicht bindet zwei Jahre); Erklärung innerhalb eines Monats nach Ablauf des Quartals (§ 18j Abs. 4 UStG i. V. m. § 16 Abs. 1d) | gesetze-im-internet.de, §§ 3c, 18j UStG |
| OSS-Korrekturen | Das BZSt-Online-Portal nimmt keine negativen Beträge an; Minderungen für frühere Quartale (z. B. Erstattungen) werden in einer späteren Meldung als Korrektur des ursprünglichen Meldezeitraums angegeben (Land, Jahr, Quartal, ursprünglicher und berichtigter Steuerbetrag) | Art. 61 MwSt-DVO (VO (EU) 282/2011); Lexware-Hilfe 548730 (Befund der Prüfer, nicht selbst abgerufen) |
| Amazon-Gebühren | Seit 01.08.2024 stellt die Amazon EU S.à r.l. über ihre deutsche Niederlassung deutschen Händlern die meisten Verkaufs- und Fulfillment-Gebühren mit 19 % deutscher USt in Rechnung, statt § 13b; die USt wird von der Auszahlung einbehalten und ist Vorsteuer (Beleg: monatliche Gebührenrechnung). Werbegebühren rechnet nicht die AEU ab; Werbung auf ausländischen Marktplätzen kann § 13b sein | steuerberaten.de Blog 555 „Umstellung der Amazon-Abrechnungen“; whk-controlling.de „Amazon Vorsteuerabzug 2024“; Händlerbund „Amazon ändert Abrechnungspraxis“ (abgerufen 20.10.2026). Ob die Beträge im Abrechnungsbericht brutto stehen, sagt keine Quelle ausdrücklich — aus „von der Auszahlung einbehalten“ abgeleitet |
| eBay-Gebühren | eBay berechnet gewerblichen Verkäufern aus Deutschland seit 01.05.2018 deutsche USt auf die Gebühren; mit hinterlegter USt-IdNr. laut eBay netto — hängt also vom Konto ab | eBay-Hilfe 4837 „Umsatzsteuer auf eBay-Gebühren für Verkäufer und Nutzer aus Deutschland“ (Suchtreffer, 20.10.2026) |
| PayPal-Gebühren | Zahlungsabwicklung ist eine steuerfreie Finanzdienstleistung (§ 4 Nr. 8 UStG) | UStG |
| Amazon-Länderdateien | Der Bestellbericht (`amazon-order-id`, `ship-country`, `fulfillment-channel`, `is-business-order`) kennt weder Abgangsland noch USt-IdNr. des Käufers; der USt-Transaktionsbericht hat `SALE_DEPART_COUNTRY`, `SALE_ARRIVAL_COUNTRY`, `BUYER_VAT_NUMBER` | Amazon Seller Central, Berichtsbeschreibungen (wie oben) |

## Schnitt in Pakete

1. **Paket 1 — Marktplatz-Abrechnungen:** gemeinsames Modell, vier Importer mit Fixtures, Summenprobe,
   Buchung gegen Verrechnungskonten, Auszahlungsabgleich, PayPal als Konto, CLI `accounti marktplatz`.
2. **Paket 2 — OSS:** Erlöse je Bestimmungsland über `accounti.steuer` (Inland, OSS, ig. Lieferung,
   Ausfuhr), Schwellenprüfung, Quartalsmeldung aus den Buchungen; Vorzeichenfehler der OSS-Engine bei
   Erstattungen beheben.
3. **Paket 3 — DATEV-Stammdaten und Belege:** EXTF-Grundbausteine, Debitoren/Kreditoren (Golden-Test),
   Belegpaket mit `document.xml` und Buchungsstapel mit Beleglink.
4. **Paket 4 — Kontoauszüge:** lückenlos nummerierte Monatsauszüge je Finanzkonto, festgeschrieben in
   der Datenbank, MT940 und Saldenverlauf, Prüfung der Kette.

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Code-Ort | Formate in `importers/{marktplatz,amazon,ebay,paypal,shopify}.py`; Buchung, Abgleich, Lauf, OSS und Einstellungen im neuen Paket `integrationen/`; Exporte in `export/{datev_format,datev_stammdaten,datev_belege,kontoauszuege}.py` | Importer kennen nur ihr Format (Architektur); Buchhaltungslogik bleibt außerhalb |
| Einheit „Abrechnung“ | Amazon: eine Abrechnung = ein `settlement-id`; eBay: eine je „Auszahlung Nr.“; Shopify: eine je Payout (ID oder Datum); PayPal: Zeitraum der Datei | jede Abrechnung hat genau einen Abgleichspunkt gegen die Bank (PayPal: das Guthaben) |
| Doppelter Import, Nachträge | Abrechnung eindeutig über (Marktplatz, Nummer); dieselbe Datei erkennt das Belegarchiv (Datei-Hash). Ein anderer Bericht zu einer bekannten Abrechnung wird **nicht** übersprungen: Posten werden als Multimenge über ihren Inhalt (Art, Datum, Betrag, Währung, Bestellnummer, Gebührenart, Artikel, Referenz — ohne Zeilennummer und ohne Freitext, denn Beschreibung, Typbezeichnung und Gebührenspalte hängen von Sprache und Spaltenauswahl des Exports ab) verglichen, fehlende nachgebucht, Befunde des Berichts zu diesen Posten übernommen; ein aus der Summe gebildeter, noch nicht abgeglichener Auszahlungsposten wird ersetzt, Summenprobe und Abgleich laufen über die ganze Abrechnung; ist er schon abgeglichen, gilt sein Betrag als bestätigt (abweichende Posten → `summe_abweichung`). Eine Auszahlungsnummer hat genau eine Auszahlungszeile: Bringt ein Bericht eine weitere (oder zwei auf einmal), widerspricht er der Abrechnung — Fehler-Befund `auszahlung_doppelt`, **nichts** wird nachgetragen oder summiert (eine summierte zweite Zeile ließe doppelt gebuchte Posten die Summenprobe bestehen); zwei Auszahlungszeilen in einem neuen Bericht → derselbe Befund, alles zur Prüfung. eBay ohne Auszahlungszeile im Bericht: kein Auszahlungsposten, Hinweis `auszahlung_folgt`. PayPal: Zeilen immer über den Transaktionscode, ein zweiter Export desselben Zeitraums heißt `… (2)`. Jeder Bericht ist ein eigener Beleg (Inhalts-Hash in der Belegnummer, sonst hielte die Belegdublettenprüfung „Lieferant + Belegnummer“ ihn für eine Dublette) | eine Auszahlung verteilt sich über Monatsberichte; der Hinweis „nach der Auszahlung erneut importieren“ führt genau dahin; ein zweiter Import bucht nichts doppelt |
| Beleg | Der Bericht wird über `belege/pipeline.nimm_auf` unverändert archiviert und als Beleg (Art „sonstiges“, ohne Betrag, Kanal `marktplatz`) erfasst; jede Buchung der Abrechnung trägt diese `beleg_id` | Prinzip 7 (Belegbezug); ohne Betrag schlägt der Bankabgleich den Bericht nicht als Quittung vor |
| Buchungsweg | Alles gegen ein Verrechnungskonto je Marktplatz (SKR03-Vorgabe 1361 Amazon, 1362 eBay, 1363 Shopify; anzulegen); Auszahlung „Bank an Verrechnungskonto“ mit `transaktion_id` des Bankumsatzes | Spec 5: Auszahlung ist nur Differenz und Abgleichspunkt; `classify` lässt den Umsatz dann in Ruhe |
| Erlöse | je Bestellung eine Buchung (Bruttosumme aller Preisbestandteile inkl. Versand, Geschenkverpackung und Rabatt), Netto/Steuer über `UStBerechner` aus Bestimmungsland und Satz; Belegfeld = Bestellnummer | Einzelaufzeichnung; OSS-Meldung zählt je Bestellung |
| Gebühren | je Abrechnung und Gebührenart eine Summenbuchung (Verkaufs-, Versand-/Fulfillment-, Lager-, Werbe-, sonstige Gebühr) auf konfigurierbare Konten (SKR03: 4760, 4780, 4780, 4610, 4760; PayPal/Shopify 4970). Umsatzsteuer je Marktplatz über `ust_gebuehren` und getrennt `ust_werbung`: `vorsteuer` (Betrag im Bericht brutto mit deutscher USt → netto + Vorsteuer, BU 9), `13b` (netto mit `bu_gebuehren`/`bu_werbung`), `ohne` (steuerfrei). Vorgabe: Amazon-Gebühren `vorsteuer`, PayPal `ohne`; nicht eingestellt (Amazon-Werbung, eBay, Shopify) → ohne Vorsteuer zur Prüfung, ein Befund `ust_gebuehren_offen` je Abrechnung | Amazon rechnet seit 01.08.2024 mit deutscher USt ab (Recherche); bei eBay hängt es am Konto, bei Werbung am Marktplatz — raten wäre falsch |
| Erstattungen | eigene Buchung je Bestellung auf dasselbe Erlöskonto (Soll), Steuer negativ; zurückerstattete Provision als Gebühr mit umgekehrtem Vorzeichen | Erlöse und Erstattungen erscheinen getrennt (Akzeptanz 1); OSS-Meldung saldiert richtig |
| Einbehalte | Reservebewegungen „Verrechnungskonto ↔ Einbehaltskonto“ (SKR03-Vorgabe 1500) | jeder Bestandteil gebucht; Einbehalt bleibt sichtbar |
| Unbekanntes | unbekannte Posten, Ersatzleistungen (z. B. FBA-Erstattung) und Korrekturen werden gebucht, aber **zur Prüfung** mit Befund | nichts verschwindet, der Mensch entscheidet |
| Summenprobe | Summe aller Posten = gemeldete Auszahlung, exakt auf den Cent; sonst Befund `summe_abweichung`, Buchungen der Abrechnung zur Prüfung, **keine** Differenzbuchung | Spec 5 „Differenzen“, Akzeptanz 2 |
| Auszahlungsabgleich | Bankumsatz ohne Buchung/Zuordnung, Betrag exakt gleich, Datum Auszahlungsdatum −2/+`auszahlung_toleranz_tage` (10), eindeutig; Stichwort im Verwendungszweck bevorzugt. Zwei Durchgänge: erst alle eindeutigen exakten Treffer (wiederholt), dann Befunde für den Rest — gleicher Betrag mehrfach → Befund, kein Raten; anderer Betrag mit Stichwort/Abrechnungsnummer → `auszahlung_abweichung`; schon anderweitig gebuchter Umsatz → Befund mit Korrekturhinweis; ein im selben Lauf zugeordneter Umsatz zählt für keinen Befund. Befunde lassen sich erledigen (bleiben sichtbar): ein späterer exakter Treffer erledigt die Abgleichsbefunde seines Postens; der Status richtet sich nur nach offenen Befunden | Akzeptanz 2: Abweichung melden statt glätten; Fehlalarme sind so schädlich wie übersehene Fehler |
| PayPal | jede saldenwirksame EUR-Zeile wird ein Umsatz (`Transaktion`, Quelle `paypal`) auf dem PayPal-Konto (SKR03-Vorgabe 1210, Dublettenschlüssel = Transaktionscode); das Modul bucht mit `transaktion_id`: Verkäufe (nur eingehende Checkout-Zahlungen: Website-, Express-Checkout-, Handy-, Warenkorb-, eBay-Zahlung), deren Gebühren, Erstattungen (nur negative Rückzahlungen, deren zugehöriger Transaktionscode ein Checkout-Verkauf ist — aus derselben Datei oder einem früheren Export), Einbehaltungen und ihre Freigaben (Einbehaltskonto), Abbuchungen/Einzahlungen; Rückbuchungen, Zahlungsrückbuchungen und Chargebacks gehen auf das Klärungskonto zur Prüfung (Befund `rueckbuchung`, § 17 UStG). Alles andere — Einkäufe, „Allgemeine Zahlung“ eines Kunden (z. B. auf eine Ausgangsrechnung), Rückzahlungen an uns, Rückzahlungen an Kunden zu einer Zahlung, die kein Verkauf war (Hinweis `rueckzahlung_ohne_verkauf`), oder zu einer nicht importierten Zahlung (dieselbe Befundart als Warnung mit Verweis auf § 17 UStG) — bleibt für `opos zuordnen`/`classify` (Hinweis `eingehende_zahlung`) | Spec: „eigenes Konto mit Saldo, nicht bloß Zahlungsweg“; eine Zahlung auf eine schon gebuchte Forderung darf kein zweiter Erlös werden — und ihre Rückzahlung keine Erlösminderung |
| PayPal-Saldo | Guthabenkette je Währung: vorheriges Guthaben + Netto = Guthaben; Bruch → Befund `saldensprung` | fehlende Zeilen fallen auf |
| PayPal-Fremdwährung | Erlös in EUR zum effektiven PayPal-Kurs der zugehörigen Währungsumrechnung (EUR-Zeile = Netto, Brutto anteilig); ohne Umrechnung bleibt der Posten zur Prüfung | EUR-Saldo bleibt exakt, keine erfundenen Kurse |
| Fremdwährung sonst | Abrechnung in Fremdwährung nur mit `--kurs` (Einheiten je 1 EUR, wie EZB/DATEV); ohne Kurs bricht der Import **vor** dem Archivieren ab (`IntegrationError`); jeder Posten einzeln umgerechnet, Auszahlung = Summe; Bankeingang anderer Höhe → Befund; Nachträge nehmen den gespeicherten Kurs | kein stiller Kursverlust; eine gespeicherte, ungebuchte Abrechnung ließe sich nicht mehr buchen |
| Bestimmungsland | Amazon: aus einer Länderdatei (`--laender`: Bestellbericht mit `ship-country` oder Amazon-USt-Transaktionsbericht mit `SALE_ARRIVAL_COUNTRY`/`SALE_DEPART_COUNTRY`/`BUYER_VAT_NUMBER`); eBay/PayPal aus der Datei; Shopify aus dem Bestellexport (`Shipping Country`). Ländernamen deutsch/englisch über `steuer.EU_STEUERSAETZE`. Fehlt es: Erlöskonto 8200, zur Prüfung, Befund — **nie** aus dem Marktplatznamen geraten. Aus dem Bestellbericht zusätzlich `fulfillment-channel` (sonst `fulfillment-id` AFN der Abrechnung) und `is-business-order`: Versand aus einem Marktplatzlager ohne bekanntes Abgangsland → zur Prüfung, Befund `abgangsland_fehlt` (außer `marktplaetze.<name>.lager_nur_inland`); Geschäftskunde im EU-Ausland ohne USt-IdNr. → zur Prüfung, Befund `geschaeftskunde_ohne_ust_id` | Spec 5: Pflichtfeld; Amazon.fr liefert auch nach DE; Pan-EU/CEE-Lager machen den Verkauf im Lagerland steuerbar |
| Steuer je Bestellung | `UStBerechner.bestimme_vorfall` mit `mandant.oss`: Inland → 8400/BU 3 (7 %: 8300/BU 2); EU-B2C mit OSS → OSS-Erlöskonto + OSS-USt-Konto aus `steuer.umsatzsteuer` (zwei Buchungen, keine Steuerautomatik); EU-B2B mit USt-IdNr. → 8125 zur Prüfung; Drittland → 8120 zur Prüfung (Ausfuhrnachweis); Abgangsland ≠ DE → zur Prüfung | Steuerlogik nur über `accounti.steuer` |
| Lieferschwelle | ohne OSS-Registrierung: EU-B2C-Netto je Kalenderjahr — jeder Posten in seinem Jahr, nicht im Jahr der Abrechnung — aus allen Marktplatz-Abrechnungen plus `integrationen.eu_fernverkaeufe_sonstige` (Jahr → Betrag, z. B. Vorjahr vor accounti); liegt das **Vorjahr** über 10 000 € (`steuer.oss.OSS_SCHWELLE_EUR`), gehen alle EU-B2C-Erlöse ab 1. Januar zur Prüfung, sonst ab dem Umsatz, der das laufende Jahr überschreitet; Befund `lieferschwelle` | § 3c Abs. 4 UStG: Vorjahr **und** laufendes Jahr; `OSSEngine.pruefe_schwelle` zählt nur OSS-Erlöskonten und ist ohne Registrierung leer |
| Ermäßigter Satz | Artikel-SKUs mit ermäßigtem Satz über `integrationen.ermaessigte_artikel`; ermäßigte OSS-Verkäufe auf eigene Erlöskonten je Land (`integrationen.oss_erloes_ermaessigt`), die die OSS-Engine als ermäßigten Satz meldet; ohne Konto: Klärungskonto 8200, zur Prüfung, **nicht** in der Meldung (Befund `oss_ermaessigt`) | der Satz steckt nur im Erlöskonto; mit dem Normalsatz gemeldet wäre die Steuer zu hoch und nach der Prüfung nicht mehr korrigierbar |
| OSS-Meldung | `OSSEngine.erstelle_meldung` auf den Buchungen bis Quartalsende; Änderungen in `steuer/oss.py`: OSS-Erlöskonto im Soll (Erstattung) mindert, statt zu erhöhen; eine Erstattung, deren Erlös (gleiche Belegnummer = Bestellnummer) in einem früheren Quartal liegt, wird `OSSKorrektur` dieses Quartals; Steuer je Land und Satz einmal aus der Summe der Bemessungsgrundlagen gerundet; die CSV lässt keine Zeile mehr weg (auch negative), die Länderzeilen ergeben GESAMT, Korrekturen stehen in einem eigenen Abschnitt. `accounti marktplatz oss` gleicht gebuchte gegen gemeldete OSS-Steuer je Steuerkonto ab (`integrationen.oss.steuerabgleich`) und warnt bei negativen Länderzeilen | das BZSt nimmt keine negativen Beträge an; gebuchte (Brutto − Netto je Bestellung) und gemeldete Steuer weichen centweise ab |
| EXTF-Grundbausteine | eigener Kopfzeilen- und Feldschreiber (`export/datev_format.py`): 31 Kopffelder, Feldtyp bestimmt Quotierung, `""` verdoppelt, CRLF, Windows-1252; Zeichen außerhalb Windows-1252 → `DatevFormatError` statt stiller Ersetzung | der vorhandene Buchungsstapel-Export (`export/datev.py`) bleibt unverändert |
| Stammdaten | alle Kontakte mit Personenkonto; Kontakt mit beiden Rollen = zwei Sätze mit gegenseitigem „Verknüpftes OPOS-Konto“; `--period` beschränkt auf Personenkonten mit Buchungen im Zeitraum; Kontakte „zur Prüfung“ werden mitgegeben und gezählt; „Nummer Fremdsystem“ = Kontakt-ID (15 Zeichen) | Buchungen und Stammdaten passen zusammen |
| Belegexport | Belegpaket (ZIP) + Buchungsstapel mit Beleglink für denselben Zeitraum und dieselben freigegebenen Buchungen wie `export datev`; GUID = Beleg-ID (deterministisch); Dateiname = GUID ohne Bindestriche + Endung; `processID="2"`, Ablage `accounti / Belege JJJJ / MM`; Beleg über `beleg_id` oder über einen bestätigten Belegabgleich der Transaktion | Beleg hängt beim Empfänger am Buchungssatz (Akzeptanz 5); keine Doppelbuchung aus dem Posteingang |
| Belegformate | PDF, JPG/JPEG, PNG, TIF/TIFF, XML; andere Formate, fehlende Archivdateien und Dateien > 20 MB → Befund, Buchung ohne Link; > 4999 Belege oder > 465 MB → `BelegexportError` | DATEV-Grenzen |
| Kontoauszüge | je Finanzkonto (Sachkonto der Transaktion, sonst `buchhaltung.bank_konto`) ein Auszug je Kalendermonat, Nummer je Jahr ab 1 lückenlos, auch für Monate ohne Umsatz; Auszüge werden beim Erstellen festgeschrieben (Tabelle `kontoauszuege`, Zuordnung `kontoauszug_umsaetze`) und über eine Hash-Kette verbunden; später eingehende Umsätze eines abgeschlossenen Monats kommen in den nächsten neuen Auszug mit Befund `nachtrag`; der laufende Monat wird nicht festgeschrieben | Spec 4.6, Akzeptanz 6; ein ausgegebener Auszug ändert sich nicht |
| Erster Auszug | beginnt mit dem Monat von `--period` oder einem früheren `--ab JJJJ-MM` (nur beim ersten Mal); Umsätze davor gehören in den Anfangssaldo und werden einmal als `vor_beginn` gemeldet; Fremdwährungsumsätze kommen in keinen EUR-Auszug (`fremdwaehrung`) | ein Anfangssaldo braucht einen Stichtag |
| Saldenverlauf | Anfangssaldo des ersten Auszugs per `--anfangssaldo` (Pflicht beim ersten Mal), danach fest der Endsaldo des Vorgängers; `--kontrollsaldo` (Saldo laut Bank zum Monatsende) — weicht er ab, wird **nichts** festgeschrieben; ist der Monat schon festgeschrieben, wird er gegen den Endsaldo dieses Auszugs geprüft; `pruefe_auszuege` rechnet Nummern, Zeiträume, Salden, Summen und Hash-Kette nach (der Hash deckt je Umsatz auch Verwendungszweck, Name und IBAN ab, also alles aus `:86:`); hat die Prüfung Befunde, schreibt `datev kontoauszuege` keine Dateien | schlüssiger Verlauf statt behaupteter; ein falscher Auszug ließe sich nicht mehr ändern |
| Belegfeld 1 | im Buchungsstapel mit Beleglink auf DATEVs Zeichenvorrat gekürzt (`datev_format.belegfeld1`), je Export ein Befund mit Beispielen | DATEV lehnt andere Zeichen ab; der OPOS-Ausgleich hängt an dem Feld |
| Leeres Belegpaket | ohne verknüpfbaren Beleg kein ZIP (nur der Buchungsstapel) | die XSD verlangt mindestens ein Dokument |
| Wirtschaftsjahr im Kopf | aus `datev.wirtschaftsjahr_beginn` nur Tag und Monat; Beginn des Wirtschaftsjahrs, in dem der Exportzeitraum liegt (abweichendes WJ nach § 4a EStG) | sonst stünde im Kopf ein falsches Jahr |
| MT940 | ein File je Export mit einer Nachricht je Auszug; `:25:` BLZ/Konto aus deutscher IBAN, sonst IBAN bzw. konfigurierte Kontobezeichnung (PayPal); `:61:` mit `NMSC`, Referenz `NONREF`; `:86:` unstrukturiert (GVC 999) mit Verwendungszweck, Name, IBAN; Text in den SWIFT-Zeichensatz umgesetzt (Ä → AE …) | DATEV liest MT940; ursprüngliche GVCs kennt accounti nicht |
| CLI | Befehlsgruppen `accounti marktplatz` (`befehle/integrationen.py`: `import`, `liste`, `zeigen`, `abgleichen`, `oss`) und `accounti datev` (`befehle/export.py`: `stammdaten`, `belege`, `kontoauszuege`); `cli.py` bleibt unverändert — die in Spec 4.10 skizzierten Namen `accounti import amazon` / `accounti export stammdaten` hätten `cli.py` gebraucht | Gerüst aus #19 |
| Konfiguration | Abschnitt `integrationen` in `config/accounti.yaml`, Lader `integrationen.einstellungen.lade_integrationen` mit Standardwerten; OSS-Registrierung aus `mandant.oss` (nachsichtig gelesen) | alles läuft auch ohne den Abschnitt |

## Aufgaben

### Paket 1 — Marktplatz-Abrechnungen

- [x] **Modelle** (`models/integrationen.py`): `Postenart`, `Marktplatzposten`, `Abrechnung`, `Befund`, `Laenderangabe`; Tabellen `marktplatz_abrechnungen`, `marktplatz_posten`, `marktplatz_befunde`; Repository (`tests/test_integrationen_repo.py`).
- [x] **Gemeinsame Parser** (`importers/marktplatz.py`): Beträge deutsch/englisch, Datumsformate, Ländernamen → ISO, Kopfzeile suchen, Länderdatei (`tests/test_marktplatz_parser.py`).
- [x] **Fixtures** (`examples/marktplatz/`): anonymisiert, nach den recherchierten Formaten nachgebaut — Amazon-Abrechnung V2 + Bestellbericht, eBay-Transaktionsbericht, PayPal-Aktivitäten (mit USD-Umrechnung), Shopify-Auszahlung + Bestellexport. Abdeckung (nach Runde 1 ergänzt, siehe unten): Erstattung und Gebühr je Marktplatz; Einbehalt bei Amazon (Reserve), eBay (Einbehalt), PayPal (`paypal_sonderfaelle.csv`: Einbehaltung und Freigabe, Rückbuchung) und Shopify (`shopify_auszahlung_gbp.csv`: Reserve); Währungsumrechnung bei PayPal (USD-Verkauf), eBay (`ebay_transaktionsbericht_gbp.csv`) und Shopify (GBP) über `--kurs`, bei Amazon nur durch Ersetzen von EUR durch GBP im Test.
- [x] **Importer** Amazon, eBay, PayPal, Shopify (`tests/test_marktplatz_importer.py`).
- [x] **Einstellungen** (`integrationen/einstellungen.py`, `tests/test_integrationen_einstellungen.py`).
- [x] **Buchung und Summenprobe** (`integrationen/buchung.py`): Akzeptanz 1 und 2 (`tests/test_integrationen_buchung.py`).
- [x] **Lauf und Auszahlungsabgleich** (`integrationen/lauf.py`, `integrationen/auszahlung.py`): Archiv, Dubletten, PayPal-Umsätze, Bankabgleich, Abweichungen als Befund (`tests/test_integrationen_lauf.py`).
- [x] **CLI** `accounti marktplatz import|liste|zeigen|abgleichen` (`tests/test_cli_marktplatz.py`).

### Paket 2 — OSS

- [x] **Steuer je Bestellung** über `UStBerechner`: Inland, OSS, ig. Lieferung, Drittland, fehlendes Land, Abgangsland, ermäßigter Satz, Lieferschwelle (`tests/test_integrationen_oss.py`).
- [x] **OSS-Engine:** Erstattung auf OSS-Erlöskonto mindert die Meldung (`steuer/oss.py`).
- [x] **Akzeptanz 3:** drei EU-Länder auf den richtigen OSS-Erlöskonten und in der Quartalsmeldung, gegen handgerechnete Sollwerte; CLI `accounti marktplatz oss --quartal`.

### Paket 3 — DATEV-Stammdaten und Belege

- [x] **EXTF-Grundbausteine** (`export/datev_format.py`, `tests/test_datev_format.py`).
- [x] **Stammdaten** (`export/datev_stammdaten.py`): Akzeptanz 4 als Golden-Test (`examples/datev/EXTF_Debitoren_Kreditoren_golden.csv`, `tests/test_datev_stammdaten.py`).
- [x] **Belegpaket und Buchungsstapel mit Beleglink** (`export/datev_belege.py`): Akzeptanz 5 mit Empfänger-Simulation (`tests/test_datev_belege.py`).
- [x] **CLI** `accounti datev stammdaten|belege` (`tests/test_cli_datev.py`).
- [x] **Nacharbeit:** Belegfeld 1 im DATEV-Zeichenvorrat, kein leeres Belegpaket, Wirtschaftsjahresbeginn aus dem Exportzeitraum; `document.xml` gegen die DATEV-XSD geprüft (`test_document_xml_gegen_datev_xsd`, mit `ACCOUNTI_DATEV_XSD` und Java).

### Paket 4 — Kontoauszüge

- [x] **Modell und Tabellen** `kontoauszuege`, `kontoauszug_umsaetze` (`models/export.py`, `db/tabellen_export.py`, `db/repo_export.py`; `tests/test_kontoauszuege.py::test_repository`).
- [x] **Auszüge erstellen und prüfen** (`export/kontoauszuege.py`): Akzeptanz 6 (`tests/test_kontoauszuege.py`).
- [x] **MT940 und Saldenverlauf** (`tests/test_kontoauszuege.py`), CLI `accounti datev kontoauszuege` (`tests/test_cli_datev.py`).
- [x] **Abschluss:** `pytest`, `ruff` (ohne Cache), `mypy` grün; Doku-Bausteine unten.

### Nacharbeit nach der Prüfung (Runde 1)

- [x] Lieferschwelle mit Vorjahr, Jahr je Posten, `eu_fernverkaeufe_sonstige` (`tests/test_integrationen_lieferschwelle.py`).
- [x] Umsatzsteuer der Gebühren und der Werbung je Marktplatz, Amazon mit Vorsteuer (`tests/test_integrationen_buchung.py::test_amazon_gebuehren_mit_deutscher_vorsteuer` u. a.).
- [x] OSS: Korrekturen früherer Quartale, keine still weggelassenen Zeilen, ermäßigte Sätze, Steuer je Land, Steuerabgleich in der CLI (`tests/test_integrationen_oss.py`).
- [x] PayPal: nur Checkout-Zahlungen als Erlös, Rückbuchungen zur Prüfung, Einbehalt/Freigabe (`tests/test_integrationen_lauf.py::test_paypal_sonderfaelle`, `tests/test_marktplatz_importer.py::test_paypal_typen`).
- [x] Fremdwährung ohne Kurs bricht vor dem Archivieren ab; eBay- und Shopify-Fremdwährung, Shopify-Reserve (`tests/test_integrationen_lauf.py`).
- [x] Amazon: Versand aus Marktplatzlager ohne Abgangsland, Geschäftskunden ohne USt-IdNr. (`tests/test_integrationen_oss.py`, `tests/test_marktplatz_parser.py`).
- [x] Nachträge zu bekannten Abrechnungen, PayPal-Export mit gleichem Zeitraum, Sammelabgleich in zwei Durchgängen, erledigte Befunde (`tests/test_integrationen_nachtrag.py`, `tests/test_cli_marktplatz.py`).
- [x] Kontoauszüge: Kontrollsaldo für festgeschriebene Monate, keine Dateien bei kaputter Kette, Texte in der Hash-Kette (`tests/test_kontoauszuege.py`, `tests/test_cli_datev.py`).

### Nacharbeit nach der Prüfung (Runde 2)

- [x] PayPal: Rückzahlung an den Kunden ist nur zu einem Checkout-Verkauf eine Erlösminderung; zu einer „Allgemeinen Zahlung“ oder Überzahlung bleibt sie für opos/classify, zu einer nicht importierten Zahlung mit Warnung (`tests/test_integrationen_lauf.py::test_paypal_sonderfaelle`, `::test_paypal_rueckzahlung_zu_verkauf_aus_frueherem_export`, `::test_paypal_rueckzahlung_ohne_bekannte_zahlung`, `tests/test_marktplatz_importer.py::test_paypal_rueckzahlung_nur_zu_einem_verkauf_ist_erstattung`; Fixture `paypal_sonderfaelle.csv` um die Rückzahlung ergänzt).
- [x] Nachträge: Fingerabdruck ohne Freitext; zweite Auszahlungszeile zu einer bekannten Auszahlung ist ein Widerspruch, es wird nichts nachgetragen; Befunde des Nachtragsberichts zu seinen Posten bleiben erhalten (`tests/test_integrationen_nachtrag.py::test_gleicher_bericht_mit_anderem_beschreibungstext_bucht_nichts`, `::test_zweite_auszahlungszeile_ist_widerspruch`, `::test_auseinanderlaufender_posten_bei_bekannter_auszahlungszeile`, `::test_nachtrag_uebernimmt_die_befunde_seiner_posten`, `tests/test_marktplatz_importer.py::test_ebay_zwei_auszahlungszeilen_sind_ein_fehler`, `tests/test_cli_marktplatz.py::test_import_meldet_widerspruechliche_auszahlungszeile`).

## Akzeptanzkriterien → Tests

| Nr. | Kriterium | Test |
|-----|-----------|------|
| 1 | Abrechnungszeitraum vollständig gebucht, Erlöse/Gebühren/Erstattungen getrennt | `test_integrationen_buchung.py::test_akzeptanz_1_abrechnungszeitraum_vollstaendig_gebucht`, `::test_akzeptanz_1_buchungen_tragen_den_beleg`; je Marktplatz `::test_ebay_buchung`, `::test_shopify_buchung`, `::test_paypal_buchung_je_umsatz`; über zwei Berichte `test_integrationen_nachtrag.py::test_auszahlung_ueber_zwei_berichte*`; Fremdwährung `test_integrationen_lauf.py::test_fremdwaehrung_ohne_kurs_wird_gar_nicht_erst_importiert` |
| 2 | Summe der Einzelposten = Auszahlung, Abweichung gemeldet statt geglättet | `test_integrationen_buchung.py::test_akzeptanz_2_summenprobe_stimmt`, `::test_akzeptanz_2_abweichung_wird_gemeldet_nicht_geglaettet`; `test_integrationen_lauf.py::test_akzeptanz_2_auszahlung_weicht_von_der_bank_ab`; `test_integrationen_nachtrag.py::test_nachtrag_nach_bankabgleich_ist_fehler`, `::test_sammelabgleich_ohne_fehlalarm` |
| 3 | Drei EU-Länder auf den richtigen OSS-Erlöskonten und in der Quartalsmeldung | `test_integrationen_oss.py::test_akzeptanz_3_drei_eu_laender_auf_oss_konten_und_in_der_meldung` (FR, IT, AT gegen handgerechnete Sollwerte); Korrekturen und ermäßigte Sätze `::test_erstattung_aus_vorquartal_ist_korrektur_des_ursprungsquartals`, `::test_ermaessigter_oss_verkauf_mit_konto_in_der_meldung` |
| 4 | Stammdatenexport in DATEV importierbar (Golden-Test) | `test_datev_stammdaten.py::test_akzeptanz_4_golden`, `::test_golden_ist_datev_format` |
| 5 | Exportierte Belege hängen beim Empfänger am Buchungssatz | `test_datev_belege.py::test_akzeptanz_5_belege_haengen_am_buchungssatz` (Empfänger-Simulation), `::test_document_xml_nach_datev_vorgaben`, `::test_buchungsstapel_mit_beleglink` |
| 6 | Kontoauszugsexport lückenlos nummeriert, Saldenverlauf schlüssig | `test_kontoauszuege.py::test_akzeptanz_6_lueckenlos_nummeriert_und_saldenverlauf_schluessig` (mit MT940-Empfänger-Simulation), `::test_pruefung_findet_*` |
| 7 | REST-API | nicht in diesem Auftrag — kommt mit Baustein 10 |

## Grenzen

**Nicht in diesem Auftrag**
- Akzeptanzkriterium 7 (REST-API, Spec 4.8) kommt mit Baustein 10. Ebenfalls nicht umgesetzt: JTL-Wawi
  (Spec 4.1), Prüfungsdatenüberlassung (4.7) und Beleg-Connectoren (4.9).
- Die Befehle heißen anders als in Spec 4.10 skizziert (`accounti marktplatz import amazon …` statt
  `accounti import amazon …`, `accounti datev stammdaten|belege|kontoauszuege` statt
  `accounti export …`), weil `cli.py` unverändert bleiben sollte. Aliase wären beim Zusammenführen
  eine kleine Änderung an `cli.py`.
- Keine Alembic-Migration für die neuen Tabellen `marktplatz_abrechnungen`, `marktplatz_posten`,
  `marktplatz_befunde`, `kontoauszuege`, `kontoauszug_umsaetze` — entsteht beim Zusammenführen.

**Marktplätze**
- Die Fixtures sind von Hand nach der öffentlichen Dokumentation nachgebaut, nicht aus echten
  Exporten. Gegen echte Berichte ist nichts geprüft; eBay benennt Spalten um und lässt sie
  konfigurieren — der Importer kennt mehrere Namen, ein neuer Name ist ein Formatfehler, kein
  stiller Fehlimport.
- Amazon liefert das Bestimmungsland nur mit Länderdatei (`--laender`); ohne sie gehen alle Erlöse
  auf 8200 zur Prüfung. Das Abgangsland kennt nur der USt-Transaktionsbericht; mit dem
  Bestellbericht geht jeder FBA-Verkauf mit Befund `abgangsland_fehlt` zur Prüfung, bis
  `lager_nur_inland` eingestellt ist — diese Einstellung ist eine Zusicherung des Händlers
  (kein Pan-EU/CEE), accounti prüft sie nicht. Die Amazon-Marktplätze UK (nach dem Brexit
  Drittland) und die Lagerbewegungen zwischen Ländern (innergemeinschaftliches Verbringen)
  behandelt das Modul nicht eigens: Abgangsland ≠ DE geht zur Prüfung. Den
  USt-Transaktionsbericht kennt der Importer nur aus der Spaltenbeschreibung, eine Fixture
  dafür gibt es nicht.
- Umsatzsteuer der Gebühren: Für Amazon wird angenommen, dass die Gebühren im
  Abrechnungsbericht **brutto** mit 19 % deutscher USt stehen (Amazon behält die USt von der
  Auszahlung ein). Das ist aus den Quellen abgeleitet, nicht an einer echten Abrechnung mit der
  zugehörigen Gebührenrechnung bestätigt; bucht Amazon die Steuer in eigenen Zeilen aus,
  landen diese als unbekannte Posten auf dem Klärungskonto. Die Vorsteuer wird aus dem
  Abrechnungsbericht gebucht, Beleg ist aber die monatliche Gebührenrechnung — der Abgleich
  beider fehlt. Für Amazon-Werbung, eBay und Shopify ist nichts voreingestellt; bis
  `ust_gebuehren`/`ust_werbung` eingestellt sind, gehen deren Gebühren ohne Vorsteuer zur
  Prüfung.
- Ersatzleistungen, unbekannte Posten und Korrekturen werden gebucht, aber zur Prüfung vorgelegt;
  ihre steuerliche Behandlung entscheidet der Mensch.
- PayPal: geführt wird nur das EUR-Guthaben; Fremdwährungsguthaben erscheinen nicht als Konto.
  Erlös ist nur, was eine Checkout-Zahlungsart trägt (Typnamen aus der Dokumentation, nicht aus
  echten Exporten); eine „Allgemeine Zahlung“ eines Kunden wird nicht gegen offene Posten
  geprüft, sondern bleibt für `opos zuordnen`/`classify`. Rückbuchungen (Chargebacks) bucht
  accounti nicht als Erlösminderung, sondern auf das Klärungskonto — ob Forderung oder
  Erlösminderung mit USt-Berichtigung, entscheidet der Mensch. Eine Rückzahlung an den Kunden
  mindert den Erlös nur, wenn ihr „Zugehöriger Transaktionscode“ ein importierter
  Checkout-Verkauf ist; fehlt der Code im Export oder wurde der Verkauf vor dem ersten
  PayPal-Import gebucht, bleibt sie mit Warnung unverbucht — kontieren muss dann der Mensch
  (Erlösminderung mit § 17 UStG oder Rückzahlung zu einem offenen Posten). Teilrückzahlungen
  werden nicht gegen den Verkaufsbetrag geprüft.
- Nachträge: Posten werden über ihren Inhalt ohne Freitext verglichen. Stabile Zeilen-IDs
  (eBay „Transaktionsnummer“/„Referenznummer“) nimmt der Fingerabdruck bewusst nicht: die
  Spalten sind wählbar, ein Bericht mit und einer ohne sie ergäbe wieder Doppelungen. Was
  trotzdem auseinanderläuft, gilt als neuer Posten: ein vom Marktplatz geänderter Betrag oder
  Datum, eine im zweiten Export fehlende Spalte „Bestellnummer“, eine Werbegebühr, die ohne
  Beschreibungsspalte als Gebühr erkannt wird. Steht die Auszahlungszeile schon in der
  Abrechnung, meldet die Summenprobe die Doppelung (Fehler, Nachtrag zur Prüfung), gelöscht wird
  nichts; steht sie noch aus (eBay-Monatsbericht ohne Auszahlungszeile), werden solche Posten
  zunächst normal gebucht und erst mit der Auszahlungszeile von der Summenprobe erkannt. Eine
  zweite Auszahlungszeile (`auszahlung_doppelt`) hält die Abrechnung auf „Abweichung“; einen
  Befehl, Befunde von Hand zu erledigen, gibt es nicht — der Bericht bleibt archiviert, ein
  erneuter Import derselben Datei ist eine Dublette. Zeilennummern in Befunden beziehen sich auf
  den Bericht, aus dem der Posten kam. Wurde eine aus der Summe gebildete Auszahlung schon
  abgeglichen, bleibt ein späterer Nachtrag ein Fehler-Befund, bis der Mensch klärt.
- eBay: Ob eBay bei Transaktionen in einer anderen Währung als der Auszahlungswährung Brutto
  und Gebühren in Transaktions- oder Auszahlungswährung ausweist, ist nicht geprüft; geht die
  Zeile nicht auf, meldet die Zeilenprobe einen Fehler. Die GBP-Fixtures prüfen nur den Weg über
  `--kurs` bei einer Auszahlung in Fremdwährung.
  Shopify: der Auszahlungsbetrag steht nicht in der Transaktionsdatei, er wird aus den Posten
  gebildet (oder mit `--auszahlung` vorgegeben).

**OSS**
- Ermäßigte Steuersätze nur über die SKU-Liste `integrationen.ermaessigte_artikel` und je Land
  nur der erste ermäßigte Satz aus `steuer.eu_steuersaetze` (FR 5,5 %, nicht 10 % oder 2,1 %).
  Ohne `oss_erloes_ermaessigt` fehlen ermäßigte OSS-Verkäufe in der Meldung; die CLI zeigt die
  Differenz der gebuchten OSS-Steuer, umbuchen muss der Mensch.
- Die Lieferschwelle zählt EU-B2C-Erlöse aus Marktplatz-Abrechnungen und den eingestellten Wert
  `eu_fernverkaeufe_sonstige`; Ausgangsrechnungen aus Baustein 3 zählen nur, wenn sie dort
  eingetragen werden. Fehlt der Vorjahreswert, kann accounti ein überschrittenes Vorjahr nicht
  erkennen.
- OSS-Korrekturen: Eine Erstattung wird ihrem Ursprungsquartal nur zugeordnet, wenn der Erlös
  mit derselben Belegnummer auf demselben OSS-Erlöskonto gebucht ist; sonst mindert sie das
  laufende Quartal (die CLI warnt bei negativen Länderzeilen). Ausgewiesen wird die Änderung,
  nicht der „ursprüngliche und berichtigte Steuerbetrag“ des Portals — die ursprünglich
  gemeldete Steuer kennt accounti nicht. Die CSV ist eine Prüfliste, nicht das Upload-Format
  des BZSt.
- Gebuchte OSS-Steuer (Brutto − Netto je Bestellung) und gemeldete (je Land und Satz aus der
  Summe) können centweise auseinanderliegen; die CLI zeigt die Differenz je Steuerkonto, eine
  Ausgleichsbuchung gibt es nicht.
- OSS-Erlöskonten gibt es in `steuer/umsatzsteuer.py` nur für acht Länder (FR, IT, ES, NL, SE, PL,
  AT, BE); andere Länder gehen mit Befund `oss_konto_fehlt` zur Prüfung. Die OSS-Steuerkonten dort
  sind sechsstellig (`1777xx`) und teilen sich teils ein Konto (FR/AT `177720`) — sie passen nicht
  zur Sachkontenlänge 4 und werden im DATEV-Export als Befund gemeldet. `steuer/` ist gemeinsamer
  Code und wurde hier nur im Vorzeichenfehler der OSS-Engine geändert.

**DATEV**
- Kein Import in ein echtes DATEV-Programm. Die Golden-Datei ist von accounti erzeugt und gegen die
  DATEV-Musterdatei (Kopf, Überschriften, Quotierung je Spalte) und die Formatbeschreibung des
  Prüfprogramms abgeglichen; das DATEV-Format-Prüfprogramm (Windows) lief nicht. Die
  Musterdatei liegt nicht im Repository: `test_golden_ist_datev_format` vergleicht die
  Überschriften mit accountis eigener Feldliste — wird die Golden-Datei neu erzeugt, fällt eine
  Abweichung vom DATEV-Format im Repository nicht auf (die Prüfer haben alle 254 Überschriften
  gegen die Musterdatei nachgeprüft).
- Stammdaten: alle Kontakte als Unternehmen (Adressattyp 2), weil Kontakte keine natürlichen Personen
  kennzeichnen; Bankverbindung nur als IBAN, keine Zahlungsbedingungs-Nummer.
- Belege: `document.xml` ist gegen die DATEV-XSD validiert (Test läuft nur mit `ACCOUNTI_DATEV_XSD`
  und Java, die XSD liegt nicht im Repository); dass DATEV Unternehmen online den Beleg wirklich am
  Buchungssatz zeigt, ist nur simuliert. Marktplatzberichte (`.txt`, `.csv`) nimmt Belege online
  nicht an — diese Buchungen gehen ohne Beleglink und mit Befund; eine PDF-Wandlung fehlt.
- Der Buchungsstapel mit Beleglink füllt keine OSS-Felder („EU-Land u. UStID (Bestimmung)“,
  „EU-Steuersatz (Bestimmung)“); OSS-Erlös und OSS-Steuer gehen als zwei Buchungen ohne BU-Schlüssel.
  Inlandserlöse tragen BU 3 auf dem Automatikkonto 8400 — das ist die Projektkonvention
  (`config/regeln.yaml`), ob DATEV das ohne Hinweis annimmt, ist nicht geprüft.
- Der Zeitraum eines Belegexports liegt in einem Kalenderjahr (Kopf und Belegdatum `TTMM`).

**Kontoauszüge**
- Der MT940-Import in DATEV ist nicht echt geprüft, nur gegen die DK-Spezifikation und eine
  Empfänger-Simulation. `:86:` ist unstrukturiert (GVC 999), Buchungsschlüssel immer `NMSC` —
  die ursprünglichen Geschäftsvorfallcodes der Bank kennt accounti nicht. Kein camt.053.
- Es sind accounti-Auszüge aus den importierten Umsätzen, keine Auszüge der Bank: Ihre
  Vollständigkeit hängt am Import. `--kontrollsaldo` deckt fehlende Umsätze auf.
- Umsätze vor dem ersten Auszug werden nur beim ersten Lauf gemeldet; ein später importierter
  Fremdwährungsumsatz für einen abgeschlossenen Monat wird nicht gemeldet.
- Nachträge behalten ihr Datum; im MT940 liegt ihr Buchungsdatum dann vor dem Auszugszeitraum.
- Die Festschreibung ist eine Hash-Kette in der eigenen Datenbank: Sie macht unbemerkte Änderungen
  sichtbar, schützt aber nicht vor jemandem mit Schreibzugriff, der die Kette neu berechnet.
  Auszüge, die vor dieser Runde festgeschrieben wurden, hätten einen Hash ohne Texte — es gibt
  noch keine, weil der Baustein nicht zusammengeführt ist.
- Mehrere Bankkonten auf demselben Sachkonto werden abgelehnt (ein Auszug je Finanzkonto).
  Die Reihenfolge am selben Tag ist die Ladereihenfolge der Datenbank, weil `transaktionen` den
  Importzeitpunkt nicht speichert; einmal festgeschrieben, steht sie fest.

## Doku-Bausteine

### README — Feature-Tabelle „Anbinden & Übergeben“ (ersetzt die beiden Zeilen)

```markdown
| ✅ | **DATEV vollständig** | Debitoren/Kreditoren (EXTF, Golden-Test), Belegpaket mit `document.xml` und Buchungsstapel mit Beleglink — Belege hängen beim Empfänger am Buchungssatz —, Kontoauszüge lückenlos nummeriert als MT940 mit Saldenverlauf |
| 🟨 | **Marktplätze & ERP** | Amazon (Abrechnungsbericht V2), eBay, Shopify, PayPal (als eigenes Konto) — Erlöse, Gebühren, Erstattungen, Einbehalte einzeln gebucht, Summenprobe, Auszahlungsabgleich, Bestimmungsland → OSS; JTL-Wawi folgt |
```

### README — Nutzungsblock (neuer Abschnitt nach „USt-IdNr.-Prüfung“)

````markdown
### Marktplätze und DATEV-Übergabe

```bash
accounti marktplatz import amazon ./abrechnung.txt --laender ./ust_transaktionen.csv
accounti marktplatz import paypal ./aktivitaeten.csv     # PayPal ist ein eigenes Konto (1210)
accounti marktplatz import shopify ./auszahlung.csv --laender ./bestellungen.csv
accounti marktplatz liste                                # Status und Befunde je Abrechnung
accounti marktplatz abgleichen                           # Auszahlungen ↔ Bankumsätze
accounti marktplatz oss --quartal 2026-Q3                # OSS-Quartalsmeldung

accounti datev stammdaten --ausgabe ./export             # Debitoren/Kreditoren
accounti datev belege --period 2026-08 --ausgabe ./export/belege-08.zip
accounti datev kontoauszuege --period 2026-08 --anfangssaldo 1.234,56   # erstes Mal
accounti datev kontoauszuege --period 2026-09 --kontrollsaldo 2.345,67
```

Jede Abrechnung wird als Beleg archiviert und Bestandteil für Bestandteil gegen ein
Verrechnungskonto gebucht; die Auszahlung ist nur der Abgleichspunkt gegen die Bank. Stimmt die
Summe der Posten nicht mit der Auszahlung, ist das ein Befund — nichts wird geglättet. Ein
weiterer Bericht zu einer bekannten Abrechnung (Monatsberichte, erneuter Export) bucht nur die
Posten nach, die noch fehlen; bringt er eine zweite Auszahlungszeile, wird nichts nachgetragen.
Eine PayPal-Rückzahlung mindert den Erlös nur, wenn ihre Zahlung ein Checkout-Verkauf war.
Als Länderdatei für Amazon den USt-Transaktionsbericht nehmen: Nur
er kennt das Abgangsland (FBA-Lager) und die USt-IdNr. des Käufers; mit dem Bestellbericht gehen
FBA-Verkäufe zur Prüfung, bis `lager_nur_inland` eingestellt ist. Fremdwährung braucht `--kurs`.
`datev belege` schreibt Belegpaket (für DATEV Belegtransfer, nicht entpacken) und Buchungsstapel
mit Beleglink; beide zusammen importieren. Kontoauszüge werden beim Erstellen festgeschrieben.
````

### CHANGELOG

```markdown
### Hinzugefügt
- **Integrationen & Export, Pakete 1–4** (Baustein 11 ohne REST-API): Marktplatz-Importer für
  Amazon (Abrechnungsbericht Flat File V2 mit Länderdatei), eBay (Transaktionsbericht), PayPal
  (Aktivitäten, als eigenes Konto mit Guthabenkette und Fremdwährungsumrechnung) und Shopify
  (Auszahlungstransaktionen mit Bestellexport); jede Abrechnung wird archiviert, Erlöse je
  Bestellung, Gebühren je Art, Erstattungen und Einbehalte werden einzeln gegen ein
  Verrechnungskonto gebucht, die Summenprobe meldet Abweichungen als Befund, die Auszahlung wird
  exakt gegen den Bankumsatz abgeglichen (`accounti marktplatz import|liste|zeigen|abgleichen`);
  Steuer je Bestimmungsland über `accounti.steuer` (Inland, OSS, ig. Lieferung, Ausfuhr,
  Lieferschwelle aus Vorjahr und laufendem Jahr), Umsatzsteuer der Marktplatzgebühren
  (Amazon mit Vorsteuer), OSS-Quartalsmeldung mit Korrekturen früherer Quartale und ermäßigten
  Sätzen (`accounti marktplatz oss`); Nachträge zu bekannten Abrechnungen; DATEV-Debitoren/Kreditoren
  (EXTF Kategorie 16, Version 5), Belegpaket mit `document.xml` (Version 6.0) und Buchungsstapel
  mit Beleglink (`accounti datev stammdaten|belege`); Kontoauszüge je Finanzkonto, lückenlos
  nummeriert, festgeschrieben mit Hash-Kette, als MT940 mit Saldenverlauf
  (`accounti datev kontoauszuege`). Neuer, optionaler Konfigurationsabschnitt `integrationen`

### Geändert
- DATEV-Exporte mit Beleglink schreiben Belegfeld 1 nur noch mit den von DATEV zugelassenen
  Zeichen (Befund bei Kürzung)

### Behoben
- OSS-Meldung und Schwellenprüfung (`steuer/oss.py`) zählten Erstattungen auf OSS-Erlöskonten
  als Umsatz statt als Minderung
- OSS-Meldung (`steuer/oss.py`): Erstattungen früherer Quartale werden als Korrektur des
  Ursprungsquartals ausgewiesen, die CSV lässt negative Zeilen nicht mehr weg, ermäßigte Sätze
  über eigene Erlöskonten, Steuer je Land und Satz aus der Summe der Bemessungsgrundlagen
```

### docs/bauplan.md (ersetzt den Absatz „Baustein 11 ist teilweise fertig …“)

```markdown
**Baustein 11 ist teilweise fertig,** weil Marktplatz-Abrechnungen (Amazon, eBay, PayPal,
Shopify) mit Summenprobe, Auszahlungsabgleich und OSS-Zuordnung sowie die vollständige
DATEV-Übergabe — Stammdaten, Belege mit Beleglink, lückenlos nummerierte Kontoauszüge — stehen
([Plan](plans/2026-10-25-integrationen-export.md)). Was fehlt, sind die REST-API (mit Baustein 10),
JTL-Wawi, die Prüfungsdatenüberlassung und die Beleg-Connectoren.
```

### docs/architektur.md

Im Abschnitt `importers/` den Satz „Geplant (eigene Importer …)“ ersetzen durch:

```markdown
Marktplätze (Baustein 11) haben eigene Importer, die eine *Abrechnung* mit Posten liefern statt
Transaktionen — `marktplatz.py` (gemeinsame Parser, Länderdatei, Registry
`MARKTPLATZ_IMPORTER`), `amazon.py`, `ebay.py`, `paypal.py`, `shopify.py`. Geplant: `mt940.py`,
`camt.py` (XML), `jtl.py`.
```

Neuer Abschnitt nach `bank/`:

```markdown
### `integrationen/` *(teilweise — [Baustein 11](specs/2026-08-10-integrationen-export.md))*

Bucht Marktplatz-Abrechnungen. Eine Abrechnung hat genau einen Abgleichspunkt gegen die Bank
(Amazon: Settlement-ID, eBay/Shopify: Auszahlung, PayPal: Zeitraum der Datei — PayPal ist ein
eigenes Konto mit Guthaben).

- `lauf.py` — Bericht archivieren (Beleg, Kanal `marktplatz`), Dubletten über Datei-Hash,
  Nachträge zu bekannten Abrechnungen (Marktplatz, Nummer) über den Inhalt der Posten,
  PayPal-Zeilen als Umsätze auf dem PayPal-Konto, Lieferschwelle je Kalenderjahr, Buchen,
  Abgleichen.
- `buchung.py` — Summenprobe (Abweichung = Befund, keine Differenzbuchung); Erlös je Bestellung,
  Gebühren je Art, Erstattungen, Einbehalte gegen das Verrechnungskonto; Steuer je
  Bestimmungsland über `steuer.umsatzsteuer`; Lieferschwelle.
- `auszahlung.py` — Auszahlung ↔ Bankumsatz exakt (erst alle eindeutigen Treffer, dann
  Befunde), sonst Befund; Buchung „Bank an Verrechnungskonto“ mit `transaktion_id`.
- `oss.py` — Quartalsmeldung aus den gebuchten OSS-Erlösen über `steuer.oss`, Abgleich der
  gebuchten mit der gemeldeten OSS-Steuer.
- `einstellungen.py` — Abschnitt `integrationen` mit Standardwerten (SKR03).
- Tabellen `marktplatz_abrechnungen`, `marktplatz_posten`, `marktplatz_befunde`.
```

Abschnitt `export/` ersetzen durch:

```markdown
### `export/`

**DATEV-Export** (Priorität), Format EXTF Version 700, Windows-1252:
- `datev.py` — Buchungsstapel (`accounti export datev`).
- `datev_format.py`, `datev_felder.py` — Kopfzeile, Feldtypen und Feldlisten wörtlich aus DATEVs
  Musterdateien und Formatbeschreibung; was nicht passt, ist ein `DatevFormatError`.
- `datev_stammdaten.py` — Debitoren/Kreditoren (Kategorie 16, Version 5) aus `kontakte/`.
- `datev_belege.py` — Belegpaket (ZIP mit `document.xml` nach `Document_v060.xsd`) und
  Buchungsstapel mit Beleglink `BEDI "<GUID>"`: der Beleg hängt beim Empfänger am Buchungssatz.
- `kontoauszuege.py` — Monatsauszüge je Finanzkonto, lückenlos nummeriert, festgeschrieben
  (Tabellen `kontoauszuege`, `kontoauszug_umsaetze`, Hash-Kette), als MT940 und Saldenverlauf;
  `pruefe_auszuege` für Baustein 7.

Befehle: `accounti datev stammdaten|belege|kontoauszuege`.

Weitere Exportformate:
- CSV (generisch)
- JSON (für API-Konsumenten)

Geplant ([Baustein 11](specs/2026-08-10-integrationen-export.md)): Prüfungsdatenüberlassung.
```

### config/accounti.example.yaml (neuer Abschnitt nach `datev:`)

```yaml
# Marktplätze & Zahlungsdienstleister (optional — ohne Abschnitt gelten diese Werte, SKR03)
integrationen:
  erloes_inland: { "19": "8400", "7": "8300" }
  bu_inland: { "19": 3, "7": 2 }
  erloes_ig_lieferung: "8125"   # B2B mit USt-IdNr. (zur Prüfung)
  erloes_ausfuhr: "8120"        # Drittland (zur Prüfung: Ausfuhrnachweis)
  erloes_unbekannt: "8200"      # Bestimmungsland fehlt (zur Prüfung)
  geldtransit_konto: "1360"
  auszahlung_toleranz_tage: 10  # Bankeingang bis so viele Tage nach dem Auszahlungsdatum
  ermaessigte_artikel: []       # SKUs mit ermäßigtem Satz
  oss_erloes_ermaessigt: {}     # Land → Erlöskonto für ermäßigte OSS-Umsätze, z.B. { FR: "8330" } (anlegen)
  eu_fernverkaeufe_sonstige: {} # Jahr → EU-Fernverkäufe netto außerhalb der Marktplätze, z.B. { 2025: 12000 }
  paypal_kontobezeichnung: "PPLXLULL/PAYPAL"   # Feld :25: im MT940 des PayPal-Kontos
  marktplaetze:                 # nur Abweichungen angeben; Konten 1361–1363/1210 anlegen
    amazon:
      verrechnungskonto: "1361"
      bank_stichworte: ["AMAZON"]
      ust_gebuehren: vorsteuer  # vorsteuer | 13b (mit bu_gebuehren) | ohne — Amazon seit 08/2024 mit deutscher USt
      ust_werbung: null         # Werbung getrennt einstellen (nicht eingestellt → zur Prüfung)
      lager_nur_inland: false   # true: FBA nur aus deutschen Lagern (kein Pan-EU/CEE)
    ebay:    { verrechnungskonto: "1362", ust_gebuehren: null }   # mit dem Berater klären
    shopify: { verrechnungskonto: "1363", verkaufsgebuehr: "4970", ust_gebuehren: null }
    paypal:  { verrechnungskonto: "1210", verkaufsgebuehr: "4970", ust_gebuehren: ohne }
```
