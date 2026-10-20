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

## Recherche (Stand 20.10.2026)

| Thema | Ergebnis | Quelle (abgerufen 20.10.2026) |
|-------|----------|-------------------------------|
| DATEV-Format, Kopfzeile | 31 Felder; Textfelder 1, 4, 8, 9, 10, 17, 18, 22, 27, 31 in Anführungszeichen; Versionsnummer 700; Feld 27 Sachkontenrahmen (`"03"`); Feld 19 Buchungstyp 1 = Finanzbuchführung | DATEV Developer Portal, „DATEV-Format“, Musterdaten (`Musterdaten_DATEV_Format_0_7f9322b9cc.zip`: `EXTF_DebKred_Stamm.csv` vom 27.03.2024, `EXTF_Buchungsstapel.csv` vom 18.06.2025) |
| Debitoren/Kreditoren | Kategorie 16, Formatname `Debitoren/Kreditoren`, Formatversion 5, **254 Felder**; Spaltenüberschriften wörtlich aus der Musterdatei; Textfelder immer quotiert (auch leer `""`), Zahl/Datum/Betrag/Konto unquotiert; Personenkonto = Sachkontenlänge + 1 Stellen; Adressattyp 0 = keine Angabe, 1 = natürliche Person, 2 = Unternehmen; EU-UStID **ohne** Länderpräfix (Länderkennzeichen im Feld EU-Land); Datumsfelder `TTMMJJJJ`; Windows-1252 | Musterdatei wie oben; Feldbeschreibung `Format_Debitoren_Kreditoren.xml` (Version 5, Stand 21.10.2025) aus dem DATEV-Format-Prüfprogramm 2.2.3.0 (`Datev_Format_Pruefprogramm_2_2_3_0_76439824cb.zip`) |
| Buchungsstapel | Kategorie 21, Formatversion 13, **125 Spalten**; Feld 20 „Beleglink“ (Text, 210); BU-Schlüssel ist ein Textfeld (`"9"`); Belegdatum `TTMM` | Musterdatei + `Format_Buchungsstapel.xml` (Version 13) aus dem Prüfprogramm |
| Beleglink | Inhalt `BEDI "<GUID>"`, im CSV als Textfeld mit verdoppelten Anführungszeichen; die GUID ist die `guid` des Dokuments in der `document.xml`; Belegpaket per DATEV Belegtransfer (ZIP nicht entpacken), Buchungsstapel getrennt über die Stapelverarbeitung — Reihenfolge egal | Stotax-Hilfe „Export von Buchungen mit Belegen … (EXTF)“ (Spalte 20 „Beleglink“); Capitol-Schnittstellendoku (Beispiel `BEDI "CB6A…"`, „DATEV XML-Schnittstelle online v5.0“); AHA Consulting „Keine Buchung ohne Beleg“ (2025). DATEV-Dok. 1005516 „Buchungsdaten mit integriertem Beleglink…“ ist nur nach Anmeldung lesbar |
| Belegpaket | `document.xml` mit Namespace `http://xml.datev.de/bedi/tps/document/v06.0`, `version="6.0"`, `<document guid type processID>`, `<extension xsi:type="File" name="…"/>`, optional `<repository>`; GUID-Muster `8-4-4-4-12` Hex; `processID` 1 = buchungsrelevant (Posteingang, Gefahr der Doppelbuchung), 2 = archivierungsrelevant (Ordner, festgeschrieben); `type` 1 = Rechnungseingang, 2 = Rechnungsausgang, ohne = „ohne Belegtyp“; Dateinamen nur ASCII; je Paket ≤ 4999 Dokumente, ≤ 465 MB (empfohlen ~100 MB), je Datei ≤ 20 MB; keine verschachtelten ZIPs; leere Elemente/Attribute werden abgelehnt | DATEV Developer Portal „DATEV XML-Schnittstelle online“ (XSD-Paket `XSD_3c866dbe96.zip`, `Document_v060.xsd` vom 17.11.2022, Musterdaten `accounts_Receivable_Ledger_Ausgangsrechnungen`) |
| Kontoauszüge | DATEV Kanzlei-Rechnungswesen importiert Kontoumsätze weiter aus **MT940**-Dateien (auch nach Nov. 2025); ein manueller camt.053-Import ist dort nicht geplant | DATEV-Dok. 1036444 (Stand 03.12.2025, laut Suchtreffer; Volltext nicht abrufbar); datev.de „Kontoumsätze bereitstellen – neues Format“ (DK hat MT940 im Nov. 2025 aus dem Regelwerk genommen) |
| MT940 | `:20:` Referenz ≤16x · `:25:` BLZ/Konto-Nr. oder IBAN ≤35x · `:28C:` Auszugsnummer ≤5n `/` Blattnummer · `:60F:`/`:62F:` C/D + JJMMTT + Währung + Betrag mit Komma · `:61:` Valuta JJMMTT, Buchung MMTT, C/D, Betrag, `N` + Buchungsschlüssel (3c), Referenz (`NONREF`) · `:86:` ≤ 6×65 Zeichen, GVC mit erster Stelle 9 = unstrukturierte Belegung · Zeilen mit CRLF, Nachricht endet mit `-`; SWIFT-Zeichensatz | DK, DFÜ-Abkommen Anlage 3 „Spezifikation der Datenformate“ V3.3, Teil 5 „Kontoauszugsinformationen MT940/MT942“ und Teil 6 „Geschäftsvorfallcodes“ (Stand 17.11.2019, Fassung der Postbank) |
| Amazon | Flat-File-V2-Abrechnungsbericht (`GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2`), Tab-getrennt, 24 Spalten (`settlement-id` … `promotion-id`); Beträge im lokalen Format (`95,00` in der EU); bleibt verfügbar, während der XML- und der alte Flat-File-Bericht am 11.11.2026 entfallen; das Bestimmungsland steht **nicht** im Abrechnungsbericht | Amazon SP-API „Settlement reports attributes“ (updatedAt 14.10.2026), Changelog „Deprecation of two payment settlement report types“ |
| eBay | Transaktionsbericht (Verkäufer-Cockpit Pro › Zahlungen › Berichte), CSV mit u. a. „Datum der Transaktionserstellung“, „Typ“, „Bestellnummer“, „Versandziel - Land“, „Betrag abzügl. Kosten“/„Nettobetrag“, „Auszahlung Nr.“, Provisionsspalten, „Transaktionsbetrag (inkl. Kosten)“, „Transaktionswährung“, „Wechselkurs“; Spalten sind konfigurierbar | eBay-Hilfe 4847 „Abgleichen Ihrer eBay-Verkaufstransaktionen“; Taxpool-Forum „Probleme beim Import von Ebay Payment Dateien“; netzhandwerker.de (11.09.2026) |
| PayPal | Aktivitäten-CSV mit 41 Spalten „Datum, Uhrzeit, Zeitzone, Name, Typ, Status, Währung, Brutto, Gebühr, Netto, …, Zugehöriger Transaktionscode, …, Guthaben, …, Land, …, Auswirkung auf Guthaben“ | StarMoney-Forum (Kopfzeile wörtlich); PayPal-Hilfe „Kontoauszüge und Berichte herunterladen“ |
| Shopify | Auszahlungs-Transaktionen-CSV: Transaction Date, Type, Order, Card Brand, Card Source, Payout Status, Payout Date, Available On, Amount, Fee, Net | Shopify Help Center „View payout details“ |
| OSS | Lieferschwelle 10 000 € (Vorjahr **und** laufendes Jahr, § 3c Abs. 4 UStG; Verzicht bindet zwei Jahre); Erklärung innerhalb eines Monats nach Ablauf des Quartals (§ 18j Abs. 4 UStG i. V. m. § 16 Abs. 1d) | gesetze-im-internet.de, §§ 3c, 18j UStG |

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
| Doppelter Import | Abrechnung eindeutig über (Marktplatz, Nummer); dieselbe Datei erkennt zusätzlich das Belegarchiv (Datei-Hash); PayPal-Zeilen über den Transaktionscode (Dublettenschlüssel) | ein zweiter Import bucht nichts doppelt |
| Beleg | Der Bericht wird über `belege/pipeline.nimm_auf` unverändert archiviert und als Beleg (Art „sonstiges“, ohne Betrag, Kanal `marktplatz`) erfasst; jede Buchung der Abrechnung trägt diese `beleg_id` | Prinzip 7 (Belegbezug); ohne Betrag schlägt der Bankabgleich den Bericht nicht als Quittung vor |
| Buchungsweg | Alles gegen ein Verrechnungskonto je Marktplatz (SKR03-Vorgabe 1361 Amazon, 1362 eBay, 1363 Shopify; anzulegen); Auszahlung „Bank an Verrechnungskonto“ mit `transaktion_id` des Bankumsatzes | Spec 5: Auszahlung ist nur Differenz und Abgleichspunkt; `classify` lässt den Umsatz dann in Ruhe |
| Erlöse | je Bestellung eine Buchung (Bruttosumme aller Preisbestandteile inkl. Versand, Geschenkverpackung und Rabatt), Netto/Steuer über `UStBerechner` aus Bestimmungsland und Satz; Belegfeld = Bestellnummer | Einzelaufzeichnung; OSS-Meldung zählt je Bestellung |
| Gebühren | je Abrechnung und Gebührenart eine Summenbuchung (Verkaufs-, Versand-/Fulfillment-, Lager-, Werbe-, sonstige Gebühr) auf konfigurierbare Konten (SKR03: 4760, 4780, 4780, 4610, 4760; PayPal/Shopify 4970); ohne Steuerschlüssel, BU-Schlüssel je Marktplatz konfigurierbar | Gebühren sind netto im Bericht; § 13b-Behandlung hängt vom Vertragspartner ab (siehe Grenzen) |
| Erstattungen | eigene Buchung je Bestellung auf dasselbe Erlöskonto (Soll), Steuer negativ; zurückerstattete Provision als Gebühr mit umgekehrtem Vorzeichen | Erlöse und Erstattungen erscheinen getrennt (Akzeptanz 1); OSS-Meldung saldiert richtig |
| Einbehalte | Reservebewegungen „Verrechnungskonto ↔ Einbehaltskonto“ (SKR03-Vorgabe 1500) | jeder Bestandteil gebucht; Einbehalt bleibt sichtbar |
| Unbekanntes | unbekannte Posten, Ersatzleistungen (z. B. FBA-Erstattung) und Korrekturen werden gebucht, aber **zur Prüfung** mit Befund | nichts verschwindet, der Mensch entscheidet |
| Summenprobe | Summe aller Posten = gemeldete Auszahlung, exakt auf den Cent; sonst Befund `summe_abweichung`, Buchungen der Abrechnung zur Prüfung, **keine** Differenzbuchung | Spec 5 „Differenzen“, Akzeptanz 2 |
| Auszahlungsabgleich | Bankumsatz ohne Buchung/Zuordnung, Betrag exakt gleich, Datum Auszahlungsdatum −2/+`auszahlung_toleranz_tage` (10), eindeutig; Stichwort im Verwendungszweck bevorzugt. Gleicher Betrag mehrfach → Befund, kein Raten; anderer Betrag mit Abrechnungsnummer im Verwendungszweck → Befund `auszahlung_abweichung`; schon anderweitig gebuchter Umsatz → Befund mit Korrekturhinweis | Akzeptanz 2: Abweichung melden statt glätten |
| PayPal | jede saldenwirksame EUR-Zeile wird ein Umsatz (`Transaktion`, Quelle `paypal`) auf dem PayPal-Konto (SKR03-Vorgabe 1210, Dublettenschlüssel = Transaktionscode); Verkäufe, Gebühren, Erstattungen, Abbuchungen/Einzahlungen bucht das Modul mit `transaktion_id`, alles andere (Einkäufe) läuft durch `opos zuordnen`/`classify` | Spec: „eigenes Konto mit Saldo, nicht bloß Zahlungsweg“ |
| PayPal-Saldo | Guthabenkette je Währung: vorheriges Guthaben + Netto = Guthaben; Bruch → Befund `saldensprung` | fehlende Zeilen fallen auf |
| PayPal-Fremdwährung | Erlös in EUR zum effektiven PayPal-Kurs der zugehörigen Währungsumrechnung (EUR-Zeile = Netto, Brutto anteilig); ohne Umrechnung bleibt der Posten zur Prüfung | EUR-Saldo bleibt exakt, keine erfundenen Kurse |
| Fremdwährung sonst | Abrechnung in Fremdwährung nur mit `--kurs` (Einheiten je 1 EUR, wie EZB/DATEV); jeder Posten einzeln umgerechnet, Auszahlung = Summe; Bankeingang anderer Höhe → Befund | kein stiller Kursverlust |
| Bestimmungsland | Amazon: aus einer Länderdatei (`--laender`: Bestellbericht mit `ship-country` oder Amazon-USt-Transaktionsbericht mit `SALE_ARRIVAL_COUNTRY`/`SALE_DEPART_COUNTRY`/`BUYER_VAT_NUMBER`); eBay/PayPal aus der Datei; Shopify aus dem Bestellexport (`Shipping Country`). Ländernamen deutsch/englisch über `steuer.EU_STEUERSAETZE`. Fehlt es: Erlöskonto 8200, zur Prüfung, Befund — **nie** aus dem Marktplatznamen geraten | Spec 5: Pflichtfeld; Amazon.fr liefert auch nach DE |
| Steuer je Bestellung | `UStBerechner.bestimme_vorfall` mit `mandant.oss`: Inland → 8400/BU 3 (7 %: 8300/BU 2); EU-B2C mit OSS → OSS-Erlöskonto + OSS-USt-Konto aus `steuer.umsatzsteuer` (zwei Buchungen, keine Steuerautomatik); EU-B2B mit USt-IdNr. → 8125 zur Prüfung; Drittland → 8120 zur Prüfung (Ausfuhrnachweis); Abgangsland ≠ DE → zur Prüfung | Steuerlogik nur über `accounti.steuer` |
| Lieferschwelle | ohne OSS-Registrierung: EU-B2C-Netto des Jahres aus allen Marktplatz-Abrechnungen; ab Überschreiten von 10 000 € (`steuer.oss.OSS_SCHWELLE_EUR`) gehen EU-B2C-Erlöse zur Prüfung, Befund `lieferschwelle` | ab dem überschreitenden Umsatz gilt der Satz des Bestimmungslands |
| Ermäßigter Satz | Artikel-SKUs mit ermäßigtem Satz über `integrationen.ermaessigte_artikel`; ermäßigte OSS-Verkäufe gehen zur Prüfung | die OSS-Engine rechnet nur den Normalsatz |
| OSS-Meldung | `OSSEngine.erstelle_meldung` auf den Buchungen; Fix in `steuer/oss.py`: OSS-Erlöskonto im Soll (Erstattung) mindert Bemessungsgrundlage und Steuer, statt sie zu erhöhen | bisher zählte `abs()` Erstattungen doppelt |
| EXTF-Grundbausteine | eigener Kopfzeilen- und Feldschreiber (`export/datev_format.py`): 31 Kopffelder, Feldtyp bestimmt Quotierung, `""` verdoppelt, CRLF, Windows-1252; Zeichen außerhalb Windows-1252 → `DatevFormatError` statt stiller Ersetzung | der vorhandene Buchungsstapel-Export (`export/datev.py`) bleibt unverändert |
| Stammdaten | alle Kontakte mit Personenkonto; Kontakt mit beiden Rollen = zwei Sätze mit gegenseitigem „Verknüpftes OPOS-Konto“; `--period` beschränkt auf Personenkonten mit Buchungen im Zeitraum; Kontakte „zur Prüfung“ werden mitgegeben und gezählt; „Nummer Fremdsystem“ = Kontakt-ID (15 Zeichen) | Buchungen und Stammdaten passen zusammen |
| Belegexport | Belegpaket (ZIP) + Buchungsstapel mit Beleglink für denselben Zeitraum und dieselben freigegebenen Buchungen wie `export datev`; GUID = Beleg-ID (deterministisch); Dateiname = GUID ohne Bindestriche + Endung; `processID="2"`, Ablage `accounti / Belege JJJJ / MM`; Beleg über `beleg_id` oder über einen bestätigten Belegabgleich der Transaktion | Beleg hängt beim Empfänger am Buchungssatz (Akzeptanz 5); keine Doppelbuchung aus dem Posteingang |
| Belegformate | PDF, JPG/JPEG, PNG, TIF/TIFF, XML; andere Formate, fehlende Archivdateien und Dateien > 20 MB → Befund, Buchung ohne Link; > 4999 Belege oder > 465 MB → `BelegexportError` | DATEV-Grenzen |
| Kontoauszüge | je Finanzkonto (Sachkonto der Transaktion, sonst `buchhaltung.bank_konto`) ein Auszug je Kalendermonat, Nummer je Jahr ab 1 lückenlos, auch für Monate ohne Umsatz; Auszüge werden beim Erstellen festgeschrieben (Tabelle `kontoauszuege`, Zuordnung `kontoauszug_umsaetze`); später eingehende Umsätze eines abgeschlossenen Monats kommen in den nächsten offenen Auszug mit Befund `nachtrag` | Spec 4.6, Akzeptanz 6; ein ausgegebener Auszug ändert sich nicht |
| Saldenverlauf | Anfangssaldo des ersten Auszugs per `--anfangssaldo` (Pflicht beim ersten Mal), danach Endsaldo des Vorgängers; optional `--kontrollsaldo` (Saldo laut Bank) → Befund bei Abweichung; `pruefe_auszuege` findet Lücken und Saldensprünge | schlüssiger Verlauf statt behaupteter |
| MT940 | ein File je Export mit einer Nachricht je Auszug; `:25:` BLZ/Konto aus deutscher IBAN, sonst IBAN bzw. konfigurierte Kontobezeichnung (PayPal); `:61:` mit `NMSC`, Referenz `NONREF`; `:86:` unstrukturiert (GVC 999) mit Verwendungszweck, Name, IBAN; Text in den SWIFT-Zeichensatz umgesetzt (Ä → AE …) | DATEV liest MT940; ursprüngliche GVCs kennt accounti nicht |
| CLI | Befehlsgruppen `accounti marktplatz` (`befehle/integrationen.py`: `import`, `liste`, `zeigen`, `abgleichen`, `oss`) und `accounti datev` (`befehle/export.py`: `stammdaten`, `belege`, `kontoauszuege`); `cli.py` bleibt unverändert | Gerüst aus #19 |
| Konfiguration | Abschnitt `integrationen` in `config/accounti.yaml`, Lader `integrationen.einstellungen.lade_integrationen` mit Standardwerten; OSS-Registrierung aus `mandant.oss` (nachsichtig gelesen) | alles läuft auch ohne den Abschnitt |

## Aufgaben

### Paket 1 — Marktplatz-Abrechnungen

- [ ] **Modelle** (`models/integrationen.py`): `Postenart`, `Marktplatzposten`, `Abrechnung`, `Befund`, `Laenderangabe`; Tabellen `marktplatz_abrechnungen`, `marktplatz_posten`, `marktplatz_befunde`; Repository (`tests/test_integrationen_repo.py`).
- [ ] **Gemeinsame Parser** (`importers/marktplatz.py`): Beträge deutsch/englisch, Datumsformate, Ländernamen → ISO, Kopfzeile suchen, Länderdatei (`tests/test_marktplatz_parser.py`).
- [ ] **Fixtures** (`examples/marktplatz/`): anonymisiert, nach den recherchierten Formaten nachgebaut — Amazon-Abrechnung V2 + Bestellbericht, eBay-Transaktionsbericht, PayPal-Aktivitäten (mit USD-Umrechnung), Shopify-Auszahlung + Bestellexport, je mit Erstattung, Gebühr, Einbehalt.
- [ ] **Importer** Amazon, eBay, PayPal, Shopify (`tests/test_marktplatz_importer.py`).
- [ ] **Einstellungen** (`integrationen/einstellungen.py`, `tests/test_integrationen_einstellungen.py`).
- [ ] **Buchung und Summenprobe** (`integrationen/buchung.py`): Akzeptanz 1 und 2 (`tests/test_integrationen_buchung.py`).
- [ ] **Lauf und Auszahlungsabgleich** (`integrationen/lauf.py`, `integrationen/auszahlung.py`): Archiv, Dubletten, PayPal-Umsätze, Bankabgleich, Abweichungen als Befund (`tests/test_integrationen_lauf.py`).
- [ ] **CLI** `accounti marktplatz import|liste|zeigen|abgleichen` (`tests/test_cli_marktplatz.py`).

### Paket 2 — OSS

- [ ] **Steuer je Bestellung** über `UStBerechner`: Inland, OSS, ig. Lieferung, Drittland, fehlendes Land, Abgangsland, ermäßigter Satz, Lieferschwelle (`tests/test_integrationen_oss.py`).
- [ ] **OSS-Engine:** Erstattung auf OSS-Erlöskonto mindert die Meldung (`steuer/oss.py`).
- [ ] **Akzeptanz 3:** drei EU-Länder auf den richtigen OSS-Erlöskonten und in der Quartalsmeldung, gegen handgerechnete Sollwerte; CLI `accounti marktplatz oss --quartal`.

### Paket 3 — DATEV-Stammdaten und Belege

- [ ] **EXTF-Grundbausteine** (`export/datev_format.py`, `tests/test_datev_format.py`).
- [ ] **Stammdaten** (`export/datev_stammdaten.py`): Akzeptanz 4 als Golden-Test (`examples/datev/EXTF_Debitoren_Kreditoren_golden.csv`, `tests/test_datev_stammdaten.py`).
- [ ] **Belegpaket und Buchungsstapel mit Beleglink** (`export/datev_belege.py`): Akzeptanz 5 mit Empfänger-Simulation (`tests/test_datev_belege.py`).
- [ ] **CLI** `accounti datev stammdaten|belege` (`tests/test_cli_datev.py`).

### Paket 4 — Kontoauszüge

- [ ] **Modell und Tabellen** `kontoauszuege`, `kontoauszug_umsaetze` (`models/export.py`, `db/tabellen_export.py`, `db/repo_export.py`).
- [ ] **Auszüge erstellen und prüfen** (`export/kontoauszuege.py`): Akzeptanz 6 (`tests/test_kontoauszuege.py`).
- [ ] **MT940 und Saldenverlauf**, CLI `accounti datev kontoauszuege` (`tests/test_cli_datev.py`).
- [ ] **Abschluss:** `pytest`, `ruff` (ohne Cache), `mypy` grün; Doku-Bausteine unten.

## Grenzen

*(wird beim Bauen ergänzt)*

## Doku-Bausteine

*(wird am Ende ausgefüllt)*
