# accounti — Architektur

## Überblick

accounti ist als Pipeline aufgebaut: Daten fließen in eine Richtung von Import über Klassifikation und Buchung bis zum Export. Jede Stufe kann unabhängig getestet und erweitert werden.

```
Belege ──┐
         ├── Abgleich → Klassifikation → Buchung → Export/BWA/Steuer/Abschluss
Umsätze ─┘                    ↑                        │
                              └── Lernschleife ────────┘
```

Der Belegstrang und der Umsatzstrang laufen im Abgleich zusammen — bewusst **vor** der
Klassifikation, damit die Kontierung den Beleg bereits kennt.

Welche Module in welcher Reihenfolge entstehen, steht im [Bauplan](bauplan.md).

## Designprinzipien

1. **Regelwerk vor KI**: Deterministische Regeln sind schneller, billiger und nachvollziehbar. Das LLM kommt nur zum Einsatz, wenn keine Regel greift.

2. **Nachvollziehbarkeit**: Jede Buchung speichert ihre Herkunft — ob per Regel oder LLM, mit welcher Confidence, und welche Begründung die KI gegeben hat.

3. **Supervisor hat das letzte Wort**: Nichts wird exportiert ohne menschliche Freigabe (zumindest in den ersten Versionen). Automatische Buchungen sind opt-in.

4. **DATEV-Kompatibilität**: Der Export muss 1:1 in DATEV importierbar sein. Kein "fast richtig".

5. **Erweiterbar**: Neue Bankformate, ERP-Quellen und Kontenrahmen sollen ohne Kernänderungen hinzufügbar sein.

6. **Unveränderbarkeit**: Was freigegeben oder exportiert wurde, wird nicht mehr überschrieben. Korrekturen sind Stornos mit Neubuchung; beide bleiben sichtbar und verweisen aufeinander. Das Journal ist fortlaufend und append-only. Vor der Freigabe darf ein Vorschlag frei korrigiert werden — die Grenze ist die Freigabe, und sie steht im Journal.

7. **Belegbezug**: Jede Buchung zeigt auf ihren Beleg oder trägt eine Begründung, warum sie belegfrei ist. Eine Zahlung ohne Beleg ist kein Randfall, sondern ein Befund.

Prinzip 6 und 7 ergeben sich aus den GoBD und sind der Grund, warum die Prüfmechanik ein eigener Baustein ist und nicht nebenbei entsteht.

## Module

### `importers/`

Importer wandeln Rohdaten einer Quelle in `Transaktion`-Objekte um — sie kennen nur ihr Format, keine Buchhaltungslogik.

Bank-CSVs laufen **konfigurationsgetrieben** über `profil.py`: Ein `BankProfil` beschreibt Trennzeichen, Encoding, Datums-/Betragsformat und die Spalten-Zuordnung; der generische `ProfilImporter` parst damit jede unterstützte Bank — ohne bankspezifischen Code.

- `profil.py` — `BankProfil` + `ProfilImporter`, eingebaute Profile (sparkasse, ing, dkb, volksbank, commerzbank), Auto-Erkennung (`erkenne_profil`) und Laden eigener Profile aus `config/banken.yaml`.
- `sparkasse.py` — dünner Wrapper um das Sparkasse-Profil (Rückwärtskompatibilität).
- Registry `BANK_IMPORTERS` (Bankname → einsatzbereiter Importer); `import bank --format auto` erkennt die Bank an den Spaltenüberschriften.

Marktplätze (Baustein 11) haben eigene Importer, die eine *Abrechnung* mit Posten liefern statt
Transaktionen — `marktplatz.py` (gemeinsame Parser, Länderdatei, Registry
`MARKTPLATZ_IMPORTER`), `amazon.py`, `ebay.py`, `paypal.py`, `shopify.py`. Geplant: `jtl.py`.

Kontoauszüge in Bankformaten:

- `mt940.py` — SWIFT MT940 nach DK-Belegung (`:61:`, `:86:` mit ?00/?20–?29/?30–?34/?60–?63,
  SEPA-Schlüssel), Saldenprobe je Auszug. *(vorhanden)*
- `camt.py` — camt.052/053/054 (.02 und .08), nur gebuchte Einträge, Bankreferenz, Storno
  (`RvslInd`), DTD/Entities im Parser abgelehnt (auch UTF-16), Saldenprobe. *(vorhanden)*
- `kontoauszug.py` — gemeinsames `Auszug`-Modell, Formaterkennung am Inhalt, Kontozuordnung
  (IBAN oder BLZ/Kontonummer; ein Konto ohne IBAN nimmt keine Auszüge eines Bankkontos an),
  `AuszugImporter` mit Kontoprüfung für `import bank --konto`.
  Registry-Einträge `mt940` und `camt`; `--format auto` erkennt sie vor den CSV-Profilen.
  *(vorhanden)*

### `belege/` *(vorhanden — [Baustein 2](specs/2026-08-10-belegerfassung.md))*

Bringt Belege ins System und macht Daten daraus. Kanäle folgen demselben Registry-Muster wie die Bank-Importer: `ordner`, `email`, `upload`, `webhook`, `connector` — jeder liefert nur Rohdatei plus Herkunft, keiner kennt Buchhaltungslogik.

- `erkennung.py` — E-Rechnung, PDF mit Textebene oder Scan? Strukturierte Daten schlagen immer OCR — außer bei ZUGFeRD MINIMUM/BASIC WL (keine Rechnung nach § 14 Abs. 4 UStG): Der Beleg geht zur Prüfung, die Steuersätze kommen aus der PDF-Ansicht, wenn deren Steuerzeilen zu den XML-Summen passen. Klassifiziert die Belegart (Eingangs-/Ausgangsrechnung, Quittung, Kontoauszug, …). Als Steuerangabe zählt auch ein Hinweis statt des Steuerausweises. `BelegErkenner` verbindet Format, Text, Regelwerk und LLM und ist der `erkenner` der Pipeline. *(vorhanden; E-Rechnungen werden bis Baustein 3 nur erkannt)*
- `extraktion.py` — Regelwerk: Belegnummer, Daten, Lieferant, USt-IdNr., IBAN (mit Prüfziffer), Zahlungsziel, Skonto („ohne Abzug“ = 0 %), Steuerzeilen (auch 0 %, mit Vorzeichen), Summen, Rechenprobe (auch Vorzeichen einheitlich). Hinweistexte (§ 13b, ig. Lieferung, § 19, § 4 UStG) werden das `steuerkennzeichen` des Belegs (UNTDID 5305: AE, K, E); ein Korrekturbeleg mit positiven Beträgen wird negiert. Belegnummer ist die eigene Nummer, nicht der Bezug („zur Rechnung Nr. …“). Steht vor dem Korrekturtitel eine Zeile wie ein Rechnungstitel, ist der Titel mehrdeutig (Beträge wie gedruckt, zur Prüfung). Belegtexte sind Fremddaten: Leerraum und Länge werden vor allen Mustern begrenzt (`begrenze_text`: 20 Leerzeichen, eine Leerzeile, 100.000 Zeichen — sonst Anfang und Ende, zur Prüfung; auch im Prüflauf), die Muster sind linear (Titel: atomare Gruppen, possessive Wiederholung; sonst Ansatz nur am Anfang einer Folge, begrenzte Länge). *(vorhanden)*
- `freigabe.py` — `belege freigeben`: Beleg aus der Prüfung → erfasst, mit Belegart, Steuerfall, Belegnummer oder umgekehrtem Vorzeichen (`--vorzeichen umkehren`); bei Dublettenverdacht, Rechenprobe, Vorzeichen und mehrdeutigem Titel nur mit Grund; verbuchte Belege nie. Journal `beleg_freigegeben` nur aus diesem Weg (`pruefung.ereignisse.belegfreigabe`), das automatische Neulesen steht als `beleg_geaendert`. *(vorhanden)*
- `ocr/` — steckbar über `OCR_ENGINES`; `tesseract` lokal als Default, damit die Zusage „Daten bleiben auf deinem Server" hält. Fehlt Tesseract, geht der Beleg mit Hinweis in die Prüfung. *(vorhanden)*
- `llm.py` — zweite Stufe, nur mit `--llm`. Der Belegtext geht maskiert hinaus (IBAN, USt-IdNr., E-Mail, Telefon, Lieferant, Belegnummer); das LLM füllt nur Lücken, das Regelwerk gewinnt. *(vorhanden)*
- `positionen.py` — Positionssplit. Eine Rechnung kann mehrere Konten betreffen; eine Kreditkartenabrechnung ist eine Datei mit vielen Umsätzen. *(vorhanden: eine Position je Steuersatz, Kreditkartenumsätze einzeln)*
- `dubletten.py` — Datei-Hash, dann Lieferant + Rechnungsnummer (bei anderem Bruttobetrag nur Verdacht — Gutschrift oder berichtigte Rechnung), dann Betrag + Datum im engen Fenster. *(vorhanden)*
- `archiv.py` — Originaldatei unverändert, content-adressiert, mit Aufbewahrungsfrist. Kein Löschpfad. *(vorhanden)*
- `kanaele/` — `BELEG_KANAELE`-Registry: `ordner`, `upload`, `email`, `webhook`, `connector`. Alle liefern nur Rohdatei plus Herkunft; `pruefung.py` prüft für E-Mail, Webhook, Connector und Ordner Typ am Inhalt (PDF, XML ohne DTD, JPEG, PNG, TIFF) und Größe (abgelehnte Dateien im Ordner nach `abgelehnt/`); der Handimport `belege import` (`upload`) prüft nicht — die Datei wählt der Anwender. `email.py` holt Anhänge per IMAP (UID-Befehle, `BODY.PEEK[]`, Ordner nur lesend, TLS mit Zertifikatsprüfung), Absender als Hinweis; `gedaechtnis.py` merkt verarbeitete Nachrichten in `kanal_nachrichten` (Ordner + UIDVALIDITY + UID, Message-ID) erst, wenn alle Anhänge aufgenommen sind; gelesen markiert oder verschoben wird eine Nachricht nur, wenn nichts abgelehnt wurde. `connector.py` ist Basisklasse und Registry `BELEG_CONNECTOREN` für Belegportale, `json_http.py` der generische JSON/HTTP-Connector. Geheimnisse nur als `${VAR}` oder im Tresor (`zugaenge.py`, AES-GCM wie `bank/tresor.py`). Konfiguration: Abschnitt `belegkanaele` (`einstellungen.py`). *(vorhanden)*
- `webhook/` — FastAPI-Endpunkt `POST /belege` für Fremdsysteme und Messenger-Weiterleitungen: Bearer-Token (gespeichert nur als SHA-256), Rohdaten/multipart/JSON, Größe und Typ werden geprüft, bevor etwas gespeichert wird; Aufnahmen je Prozess serialisiert. Start mit `accounti kanaele webhook starten`, TLS über einen Reverse-Proxy. *(vorhanden)*
- `pipeline.py` — `nimm_auf`: archivieren, Dubletten prüfen, optionalen Erkenner aufrufen, `Beleg` und Eingangsprotokoll speichern. Ein Fehler im Erkenner schickt den Beleg in die Prüfung, statt die Pipeline abzubrechen. *(vorhanden)*

### `erechnung/` *(teilweise — [Baustein 3](specs/2026-08-10-erechnung.md))*

Liest und schreibt strukturierte Rechnungen. Alle Formate werden auf ein gemeinsames Zwischenmodell nach EN 16931 abgebildet; die restliche Anwendung kennt nur dieses Modell, nie ein konkretes Format.

- `modell.py` — Zwischenmodell `Rechnung` mit BT-Nummern als Kommentar; Profilerkennung aus BT-24 (MINIMUM, BASIC WL, BASIC, EN 16931, EXTENDED, XRechnung). *(vorhanden)*
- `parser/` — XRechnung (UBL Invoice/CreditNote, CII), ZUGFeRD/Factur-X (das XML holt `belege/erkennung.py` aus dem PDF). DTDs und Entities werden abgelehnt. *(vorhanden)*
- `validierung.py` — fachliche Prüfungen mit Befunden nach Schweregrad statt „gültig/ungültig": Auswahl der EN-16931-Geschäftsregeln (Pflichtangaben, Rechenregeln BR-CO-10…16, Steuerkategorien S/AE/E/Z/K/G/O), XRechnung BR-DE-3/4/15, § 14 UStG, Steuersatz zum Land über `steuer/`. Bewusst strenger als XRechnung: Ohne USt-IdNr. oder Steuernummer des Verkäufers gibt es keinen Vorsteuerabzug, also einen Fehler. Die formale Prüfung gegen XSD und Schematron folgt. *(vorhanden)*
- `abbildung.py` — Zwischenmodell → `Beleg`: jede Zeile und jeder Nachlass/Zuschlag eine Position; die Steuer je Satz entspricht exakt der Aufschlüsselung der Rechnung. Gutschriften (Typ 381) mit negativen Beträgen. *(vorhanden)*
- `erzeuger/aufbau.py` — Entwurf + Firmendaten → Zwischenmodell. Geschäftsvorfall, Satz und Steuerbetrag liefert `steuer/UStBerechner`; hier wird nur auf die EN-16931-Kategorien abgebildet (S, AE mit Reverse-Charge-Hinweis, K mit Lieferanschrift, G). Dienstleistungen ins Drittland (Kategorie O) sind noch nicht unterstützt. *(vorhanden)*
- `erzeuger/cii.py` — Zwischenmodell → XRechnung 3.0 in CII-Syntax, Elementreihenfolge nach Schema. Round-Trip: der eigene Parser liest exakt das Modell zurück. *(vorhanden)*
- `kosit.py` — formale Prüfung mit dem KoSIT-Validator (Java) und der XRechnung-Konfiguration; installiert per `scripts/pruefwerkzeuge_installieren.sh` nach `.kosit/` (oder `ACCOUNTI_KOSIT_DIR`). *(vorhanden)*
- `erzeuger/zugferd.py` — ZUGFeRD-PDF (Profil XRECHNUNG): lesbare Rechnung nach DIN 5008 als PDF/A-3b mit fpdf2, Liberation Sans eingebettet (`schriften/`, SIL OFL), XRechnung als Anhang `xrechnung.xml` (AFRelationship *Alternative*), XMP mit Factur-X-Erweiterung. *(vorhanden)*
- `mustang.py` — formale Prüfung des PDF mit Mustang (veraPDF für PDF/A-3b plus Prüfung des eingebetteten XML). Prüfwerkzeuge liegen in `.pruefwerkzeuge/` (oder `ACCOUNTI_PRUEFWERKZEUGE`). *(vorhanden)*
- `ausstellung.py` — vergibt die Nummer (`nummernkreise`, Hochzählen per `UPDATE` in der Transaktion), erzeugt XRechnung und ZUGFeRD-PDF, prüft fachlich und formal (KoSIT, Mustang), archiviert beide und legt den Beleg der Ausgangsrechnung an. Scheitert eine Prüfung, wird zurückgerollt und die Nummer bleibt frei. Ausgestellte Rechnungen sind unveränderlich. *(vorhanden)*
- `versand.py` — versendet die archivierte Datei (nie neu erzeugt) per SMTP; Versandweg als Schnittstelle, damit Peppol später andocken kann; jeder Versuch steht in `versandprotokolle`. Zugangsdaten aus dem Abschnitt `versand`, Passwort per `${UMGEBUNGSVARIABLE}`. *(vorhanden)*
- `erzeuger/` — Ausgangsrechnungen. Die Steuer kommt vollständig aus `steuer/`; es gibt keine zweite Steuerlogik im Rechnungsschreiber.

### `bank/` *(vorhanden — [Baustein 5](specs/2026-08-10-bankanbindung-live.md))*

Holt Kontoumsätze selbst ab und führt sie mit Belegen zusammen.

- `provider.py` — Registry wie bei den Importern: `fints` (Direktverbindung, Default), `psd2` (Aggregator, opt-in), `datei` (der bestehende Dateiimport hinter derselben Schnittstelle, `datei.py`). Damit bleibt accounti ohne jede Bankverbindung vollständig nutzbar. Verlangt die Bank eine Freigabe, meldet der Provider das als Zustand am Konto. *(vorhanden: Schnittstelle, `datei`, `fints`; `psd2` folgt)*
- `tresor.py` — Zugangsdaten mit AES-GCM verschlüsselt, Schlüssel aus `ACCOUNTI_SCHLUESSEL`, das Chiffrat an das Konto gebunden. *(vorhanden)*
- `dubletten.py` — Dublettenschlüssel aus Konto, Datum, Betrag, Verwendungszweck, Gegenpartei und laufender Nummer gleicher Umsätze; gilt für Abruf und `import bank`. *(vorhanden)*
- `lauf.py` — Abruf aller Konten (ab Stand minus 14 Tage) und der geplante Lauf: abrufen → offene Posten zuordnen → abgleichen → kontieren; idempotent. Umsätze tragen das Sachkonto ihres Bankkontos. *(vorhanden)*
- `abgleich.py` — Beleg ↔ Umsatz, dreistufig: Referenz, exakter Treffer, unscharfer Vorschlag. Bewusst streng — ein falscher Abgleich begründet eine falsche Vorsteuer und ist teurer als ein fehlender. Abgeglichen werden Quittungen und sonstige Belege; Rechnungen laufen über offene Posten. Automatisch nur, was auf beiden Seiten eindeutig ist; zwei gleiche Belege werden zwei Vorschläge. *(vorhanden)*
- `abgleichslauf.py` — Tabelle `belegabgleiche` (vorgeschlagen/bestätigt/abgelehnt), Bestätigen verwirft konkurrierende Vorschläge, Bericht „Umsätze ohne Beleg / Belege ohne Umsatz“. *(vorhanden)*
- Bankkonten (`Bankkonto` in `models/`, Tabelle `bankkonten`) — IBAN, Sachkonto, Provider, Einstellungen, verschlüsselter Zugang, Abrufstand, Zustand; Zugangsdaten nie in Logs, nie im LLM-Prompt. *(vorhanden)*
- `fints.py` — Provider `fints` über python-fints (FinTS 3.0, PIN/TAN). Produkt-ID der
  Installation (Konto-Einstellung → `ACCOUNTI_FINTS_PRODUKT_ID` → `bank.fints.produkt_id`), Konto
  über die IBAN aus HKSPA, Umsätze als camt.052 (HKCAZ) oder MT940 (HKKAZ, roh) durch die eigenen
  Parser; das Format bleibt nach dem ersten Abruf fest (Wechsel nur ausdrücklich, ohne
  Überlappung), nur https. PIN abgelehnt → `ZugangAbgelehntError`, Zustand `zugang_abgelehnt`. Die Sitzung (Kundensystem-ID, BPD/UPD, TAN-Verfahren) liegt verschlüsselt im Zugang,
  sonst verlöre die Bank die 180-Tage-Ausnahme. Freigaben: ohne Rückfrage `FreigabeNoetigError`
  (Zustand `freigabe_noetig`), mit Rückfrage TAN-Eingabe bzw. Statusabfrage für die App.
  `richte_fints_ein` wählt TAN-Verfahren und -Medium. *(vorhanden)*
- `einstellungen.py` — Abschnitt `bank` (`fints`, `kreditkarte`) mit Standardwerten. *(vorhanden)*
- `kreditkarte.py` — Kreditkarte = eigenes Bankkonto mit eigenem Sachkonto plus Tabelle
  `kreditkarten` (Girokonto, Muster, Endziffern, Abrechnungstag). Umsätze per Provider oder aus
  der PDF-Abrechnung (Positionssplit aus `belege/`, Provider `abrechnung`); Abrechnungen
  (`kreditkartenabrechnungen`, `kreditkartenumsaetze`) mit Summe der Einzelumsätze; die
  Sammelbelastung auf dem Girokonto wird centgenau dagegen geprüft — Abweichung = Befund und
  Buchung zur Prüfung, nie ein Rundungsposten; solche Zuordnungen sind vorläufig und werden bei
  jedem Lauf neu bewertet (exakter Treffer gewinnt auch über Läufe), spät gelieferte
  Kartenumsätze werden nachgetragen, alte PDF-Abrechnungen mit schon gebuchter Belastung nicht
  von selbst übernommen; „mehrdeutig“ entscheidet ein Mensch (`trenne_belastung`). Gebucht wird
  „Kreditkarte an Bank“ (PDF-Karten) bzw. über Geldtransit (Karten mit Abruf; der Ausgleich nur
  gegen eine gleich hohe, bestätigte Belastung automatisch). Läuft in `bank lauf` vor den offenen
  Posten.
  *(vorhanden)*
- `abrechnung.py` — Provider `abrechnung` für Konten, deren Umsätze aus übernommenen
  Abrechnungen kommen (PDF-Kreditkarten); liefert beim Abruf nichts. *(vorhanden)*
- `dubletten.py` — … mit Bankreferenz (camt `AcctSvcrRef`, MT940 `//Referenz`) besteht der
  Schlüssel aus Konto, Datum, Betrag und Referenz (ohne laufende Nummer und Zweck); ohne sie zählt
  die laufende Nummer je Auszug bzw. Datei (`Abruf.abschnitte`, Folgeseiten gehören dazu).
  *(vorhanden)*
- `lauf.py` — … Konten auf `freigabe_noetig` oder `zugang_abgelehnt` ruft ein Abruf ohne
  Rückfrage nicht ab. *(vorhanden)*
- `provider.py` — … Rückfrage für Freigaben (`BankProvider(freigabe=…)`, `Freigabeanfrage`);
  geänderte Zugänge (Sitzung, Tokens) gibt der Provider in `Abruf.zugang` bzw.
  `FreigabeNoetigError.zugang` zurück, `rufe_ab` verschlüsselt sie neu. *(vorhanden)*

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

### `klassifikation/`

Die Klassifikations-Engine entscheidet, welches Konto zu einer Transaktion gehört.

**Dreistufiger Ansatz:**

```
Transaktion
    │
    ▼
┌──────────┐  Match?   ┌─────────┐
│ Regelwerk │──── Ja ──▶│ Buchung │  (Confidence = 1.0)
└──────────┘            └─────────┘
    │ Nein
    ▼
┌──────────┐  Conf > 0.85   ┌─────────┐
│   LLM    │───── Ja ──────▶│ Buchung │  (Confidence = LLM-Score)
└──────────┘                 └─────────┘
    │ Conf < 0.85
    ▼
┌──────────────┐
│ Zur Prüfung  │  → Supervisor-Queue
└──────────────┘
```

### `buchung/`

Erzeugt vollständige Buchungssätze (Soll/Haben) aus Klassifikationsergebnissen. Berücksichtigt Steuerautomatik, Belegverknüpfung, Kostenstellen.

`kontierung.py` ist der Kontierungslauf (`classify`): Ein Umsatz mit bestätigtem Beleg wird über `mit_beleg.py` aus dem Beleg gebucht — je Steuersatz ein Buchungssatz, Vorsteuer aus dem Beleg, Sachkonto aus Kontakt oder Regelwerk auf die Belegdaten; der Buchungssatz trägt Transaktion und Beleg. Alle anderen Umsätze gehen wie bisher durch Regelwerk und LLM. *(vorhanden)*

Zweiter Pfad über Personenkonten (`opos/verbuchung.py`): Liegt ein erfasster Beleg vor, wird gegen Kreditor bzw. Debitor gebucht und ein offener Posten erzeugt; der Buchungssatz trägt dann `beleg_id` statt `transaktion_id`. Der bestehende Pfad (Bankbuchung ohne Beleg) bleibt — für Gebühren, Zinsen und Ähnliches ist er weiterhin richtig. *(vorhanden)*

### `kontakte/` *(vorhanden — [Baustein 4](specs/2026-08-10-kreditoren-debitoren-opos.md))*

Debitoren- und Kreditorenstammdaten mit Personenkontonummern aus den Nummernkreisen des Kontenrahmens (Abschnitt `buchhaltung`, Standard 10000–69999 / 70000–99999). `erkennung.py` findet Kontakte über IBAN, dann USt-IdNr., dann den normalisierten Namen (Rechtsform, Satzzeichen, Umlaut-Schreibweisen egal) — greift nichts, geht die Neuanlage zur Prüfung, statt still zu passieren. Ein Treffer darf dem Beleg nicht widersprechen: Eine andere USt-IdNr. ist ein anderes Unternehmen (auch bei gleicher IBAN oder gleichem Namen), ein anderes Land schließt einen Namenstreffer aus, Kunden aus eigenen Rechnungen brauchen dazu gleiche PLZ oder E-Mail; gleiche IBAN mit anderem Namen ist ein Treffer mit Widerspruch (Buchung zur Prüfung). `land_aus_kennung` leitet das Land aus USt-IdNr. bzw. IBAN ab. `dienst.py` legt an, vergibt das Personenkonto der Rolle und ergänzt fehlende Angaben, ohne vorhandene zu überschreiben. *(vorhanden)*

`ustid.py` führt die qualifizierte Bestätigungsabfrage beim BZSt durch (eVatR-REST-API `POST https://api.evatr.vies.bzst.de/app/v1/abfrage`; die XML-RPC-Schnittstelle ist seit 30.11.2025 abgeschaltet) und protokolliert sie revisionssicher: Tabelle `ustid_pruefungen` mit Rohanfrage und Rohantwort, laufender Nummer und SHA-256-Hash-Kette; Änderungen und Löschungen scheitern am ORM, unter SQLite zusätzlich an Triggern; `pruefe_protokoll()` findet Lücken und veränderte Einträge. Bestätigt ist eine Nummer erst mit `evatr-0000` aus einer qualifizierten Abfrage, bei der Name und Ort nicht abweichen; es zählt die jüngste aussagekräftige Antwort innerhalb von `ustid_pruefung.max_alter_tage`. Erst damit steht die in `steuer/umsatzsteuer.py` implementierte Regel „EU + B2B mit USt-ID → 0 %" auf einer belastbaren Grundlage: `erechnung/ausstellung.py` stellt K und AE ohne Bestätigung nicht aus, `opos/verbuchung.py` bucht solche Erlöse nur zur Prüfung. *(vorhanden)*

### `opos/` *(vorhanden — [Baustein 4](specs/2026-08-10-kreditoren-debitoren-opos.md))*

Offene Posten mit Fälligkeit, Skontofrist und Restbetrag. `verbuchung.py` macht aus einem erfassten Beleg die Buchungen je Steuersatz (Eingang: Sachkonto aus Kontakt-Vorschlag, Regelwerk oder Standard zur Prüfung, Steuerfall AE → Schlüssel 94, K → 19 zur Prüfung; Ausgang: Erlöskonto nach Steuerkategorie der E-Rechnung) und den Posten; jeder Beleg genau einmal, jeder in eigenem Savepoint. Eine Position ohne Satz wird brutto gebucht (`buchung/steuergruppe.py`, gemeinsam mit `buchung/mit_beleg.py`), eine Gutschrift mit getauschten Seiten; bei Bilanzierung und Eingang im Folgejahr geht die Vorsteuer auf 1548 (SKR04 1434) und wird zum ersten offenen Tag des Eingangsmonats umgebucht — nur der Abzug: eine Gutschrift mindert die Vorsteuer zum Belegdatum (§ 17 Abs. 1 S. 8 UStG), später gebucht zur Prüfung. `abstimmung.py` vergleicht den Saldo jedes Personenkontos mit der Summe seiner offenen Posten (Prüfregel `personenkonto_op`, Abschlussprüfung `personenkonten`). `auswertung.py` liefert OPOS-Liste, Fälligkeitsstaffel und Summen je Kontakt. *(vorhanden)*

`zuordnung.py` ordnet Banktransaktionen dreistufig zu — Referenz (Belegnummer im Verwendungszweck), exakt (einziger Posten des Kontakts über den Betrag), unscharf (Skonto ohne Referenz, Sammelzahlung als Teilmengensumme, Teilbetrag, Betrag ohne Kontakt). Automatisch gebucht wird nur Eindeutiges; der Rest wird Vorschlag. `ausgleich.py` bucht Zahlung und Skonto — das Skonto anteilig nach den Bruttoanteilen der Rechnung auf ihre Steuersätze verteilt, Netto und Steuer je Anteil aus `steuer/`, also immer mit Vorsteuer- bzw. Umsatzsteuerkorrektur. `zahlungslauf.py` verbindet beides, reserviert vorgeschlagene Posten und speichert jede Zuordnung in `zahlungszuordnungen`; `classify` kontiert nur noch Transaktionen ohne Buchung und ohne Zuordnung. *(vorhanden)* `zuordnung.py` ordnet Zahlungen dreistufig zu (Referenz, exakt, unscharf), `ausgleich.py` bucht den Ausgleich — bei gezogenem Skonto immer **mit** anteiliger Steuerkorrektur, nie als reine Betragsdifferenz.

### `zahlung/` und `mahnwesen/` *(vorhanden — [Baustein 6](specs/2026-08-10-zahlungsverkehr-mahnwesen.md))*

`zahlung/vorschlag.py` erzeugt aus offenen Verbindlichkeiten die Vorschlagsliste zum Stichtag:
Skontoposten, sobald ihre Skontofrist in den Planungshorizont (`zahlung.vorlauf_tage`) fällt, vor
fälligen Posten, mit Grund je Position; Gutschriften, gesperrte Kontakte und Posten aktiver Läufe
werden mit Grund ausgeschlossen. `zahlung/freigabe.py` führt den Zahlungslauf als Zustandsautomaten
(Entwurf → freigegeben → eingereicht → ausgeführt, Storno aus den ersten drei) mit Protokoll
(`zahlungslauf_protokoll`, nur anfügen), optionalem Vier-Augen-Prinzip und Freigabe-Hash; die
Zahlungen frieren Empfänger, IBAN, Betrag und Verwendungszweck ein und sind nach der Freigabe am
ORM gesperrt; ein eindeutiger Index auf `zahlungen.sperre` lässt einen Posten nie in zwei aktive
Läufe. `zahlung/pruefung.py` prüft blockierend — eine IBAN, die vom Stammsatz oder von der Rechnung
abweicht, stoppt den Lauf, bis der Stammsatz geändert oder die Abweichung mit Grund geklärt ist;
ebenso ein Posten, dem `opos zuordnen` schon einen Bankumsatz vorschlägt, und Empfänger außerhalb
des EWR (dort verlangt SEPA den BIC).
`zahlung/sepa.py` schreibt `pain.001.001.09` nach DK-TVS GBIC_5 (DFÜ-Abkommen Anlage 3), speichert
die Datei im Lauf und gibt sie nur noch byte-gleich aus. Ausgeglichen wird nie hier, sondern über
den Bankumsatz (`opos zuordnen`); `zahlung abgleichen` setzt danach „ausgeführt“. Die Einreichung
über den Bank-Provider fehlt noch — der Dateiweg funktioniert ohne jede Bankverbindung.

`mahnwesen/` liest Stufen aus dem Abschnitt `mahnwesen` (Karenz, Mindestbetrag, Stufenabstand,
Gebühr und Zinsen je Stufe), ermittelt je überfälligem Posten die nächste Stufe (keine wird
übersprungen, die nächste erst nach Ablauf der Frist der letzten), stuft Kunden als Unternehmer
oder Verbraucher ein (Kontakt → Ausgangsrechnung → USt-IdNr. → Standard Verbraucher), bestimmt
den Verzugsbeginn nach § 286 BGB (erste versendete Mahnung, vereinbartes Zahlungsziel,
30-Tage-Regel) und rechnet ab da Verzugszinsen nach § 288 BGB taggenau (act/365)
mit der Basiszinssatz-Tabelle aus `mahnwesen/basiszins.py` — jeder Satz mit Gültigkeitszeitraum,
Teilzahlungen aus den Zahlungszuordnungen zeitanteilig, die 40-€-Pauschale mit Anrechnung der
Mahngebühren; Gebühren verlangt eine Mahnung nur für Mahnungen im Verzug. Mahnungen sind Entwürfe, bis sie versendet werden (PDF mit fpdf2, Text oder E-Mail
über den Versandweg aus `erechnung/versand.py`); dann zählt die Mahnstufe am offenen Posten hoch,
das PDF liegt im Belegarchiv, und die versendeten Mahnungen sind die Historie.

### `pruefung/` *(vorhanden — [Baustein 7](specs/2026-08-10-belegvollstaendigkeit-gobd.md))*

Die Mechanik hinter den Prinzipien 6 und 7.

- `regeln/` — Registry `PRUEFREGELN` (`registriere_pruefregel`): Regel = `name`, `kategorie`,
  `schwere`, `beschreibung`, Pydantic-`Parameter` (Schwellen) und `pruefe(kontext, p)`;
  liest nur. `vollstaendigkeit.py` (Umsatz ohne Beleg über `offen_in_der_bank`, Rechnung ohne
  Zahlung, Nummernkreise, Kontoauszüge über `export/kontoauszuege.pruefe_auszuege` und
  Kontoauszugssalden), `richtigkeit.py` (Pflichtangaben, Rechenprobe, Steuerschlüssel ./.
  Sachkonto über die mitgelieferte `pruefung/skr03.yaml` — DATEV-Automatikkonten — und
  `steuer/kennziffern`, Steuersatz zum Land, Adressat, ig. Erwerb gegen das
  USt-IdNr.-Protokoll, Dubletten), `zeitgerechtheit.py`, `ordnung.py`. *(vorhanden)*
- `belegangaben.py` — liest Pflichtangaben aus dem archivierten Original (E-Rechnung,
  Textebene, OCR auf Wunsch). *(vorhanden)*
- `einstellungen.py` — Abschnitt `pruefung` (`lade_pruefung`). *(vorhanden)*
- `nachforderung.py` + `aufgaben_anbindung.py` — ersetzt den Prüflauf `beleg_fehlt` aus
  Baustein 8 durch den mit Schwellen und `belegfrei`-Mustern; Anfrage an den Lieferanten als
  Entwurf, Versand nur auf Befehl. *(vorhanden)*
- `journal.py` + `ereignisse.py` — Journal (`journal`, nur anfügen, SHA-256-Kette,
  SQLite-Trigger); Sitzungsereignisse `before_flush`/`after_flush` schreiben je Vorgang einen
  Eintrag (Buchungen, Belege, verworfene Dubletten, Zahlungslauf- und Abschlussprotokoll),
  `do_orm_execute` sperrt Massenänderungen; jede schreibende Transaktion hält ab dem ersten
  Flush mit Journal- oder Sperrbezug die Schreibsperre (`schreibsperre`). `pruefe_journal`
  prüft Kette, Anker, Übernahmen, Verlauf je Objekt und den Bestand (Buchungen, Belege,
  Sperren) aus einem Stand (`lesestand`: PostgreSQL-Schnappschuss, SQLite-Lesetransaktion).
  Person und Grund aus `person.journal_kontext` — mit Benutzern setzt ihn die Rechteprüfung
  der CLI (`befehle.handelnde_person`, geprüft), für API-Token die REST-API; jede andere
  Person kennzeichnet `fuege_an` als „(ungeprüft)“, sobald die Datenbank zu einer
  Benutzerverwaltung gehört. *(vorhanden)*
- `storno.py` — Freigabe, Korrektur (Vorschlag direkt, freigegeben per Storno mit
  Neubuchung), Storno als Gegenbuchung, Export-Vermerk; die Sperre freigegebener Buchungen
  sitzt in `ereignisse.py`. *(vorhanden)*
- `perioden.py` — Monatsabschluss (`periodenabschluesse`) neben der Jahressperre aus
  Baustein 12: gemeinsame Fehlerklasse (`PeriodeGesperrtError` ist ein `JahrGesperrtError`),
  gemeinsames Abschlussprotokoll, `sperre_am`. *(vorhanden)*
- `verfahrensdoku.py` — Verfahrensdokumentation aus Konfiguration, Datenbank, Systemdatenbank
  (Benutzer, Rollen, Freigabewege) und Code-Standards (GoBD Rz. 151 ff.), Markdown/PDF,
  Fassung im Journal. *(vorhanden)*

Befehle: `accounti pruefen`, `nachfordern`, `journal`, `buchung`, `periode`,
`verfahrensdoku`; `korrigiere`, `bestaetige`, `review` aus `cli.py` nutzen `storno.py`.
Tabellen in `db/tabellen_pruefung.py`, Migration `ddc9a184ddb4`.

### `aufgaben/` *(vorhanden — [Baustein 8](specs/2026-08-10-aufgaben-rueckfragen.md))*

Alles, was ein Mensch entscheiden muss, an einem Ort. Eine `Aufgabe` (`models/aufgaben.py`)
zeigt auf `Objekt(typ, id)` — Buchung, Beleg, Transaktion, offener Posten, Kontakt, Bankkonto
oder einen Typ, den ein anderer Baustein mitbringt (z.B. `frist`). Art und Objekttyp sind
freie Bezeichner; `objekte.py` beschreibt und löst die bekannten Typen auf
(`registriere_objekttyp`).

- `erzeugung.py` — die Schnittstelle für andere Bausteine: `melde_aufgabe` ist idempotent über
  den Schlüssel `art|objekt_typ|objekt_id` (eindeutiger Index, auch bei parallelen Läufen);
  ein zweiter Aufruf aktualisiert; ein Versionszähler verhindert, dass ein Lauf die Änderung
  eines Menschen überschreibt. `schliesse_wenn_erledigt` setzt `hinfaellig` (System),
  `erledige` setzt `erledigt` (Mensch) — erledigt bleibt erledigt, hinfällig öffnet sich wieder,
  wenn der Anlass zurückkehrt. Kommentare und Rückfragen hängen an Aufgabe und/oder Objekt;
  der Verlauf ist nur anfügbar. *(vorhanden)*
- `prueflaeufe.py` — Registry `PRUEFLAEUFE`: `kontierung_pruefen`, `beleg_fehlt` (über
  `bank/abgleichslauf.offen_in_der_bank`), `beleg_pruefen`, `kontakt_pruefen`, `bank_freigabe`.
  Prüfläufe lesen nur; `gleiche_ab` meldet die Anlässe und schließt Aufgaben ohne Anlass im
  geprüften Umfang. *(vorhanden)*
- `zustaendigkeit.py` — Regeln `wenn → an | rolle` aus `aufgaben.zustaendigkeit`; ohne Treffer
  unzugewiesen = gemeinsame Liste. *(vorhanden)*
- `erinnerung.py` — Stufen in Tagen nach Fälligkeit (Standard 0/3/7, je Art), die letzte
  eskaliert. *(vorhanden)*
- `benachrichtigung.py` — Tagesübersicht je Empfänger statt Einzelmeldungen, Kanal-Registry
  `KANAELE`: `email` (SMTP aus `versand`, `Auto-Submitted` nach RFC 3834), `webhook` (JSON mit
  `text`); Protokoll `aufgaben_benachrichtigungen`, höchstens eine Übersicht je Empfänger, Kanal
  und Tag, als gemeldet gilt nur Zugestelltes; der Webhook-Text ist gegen fremdes Markup
  entschärft. *(vorhanden)*
- `anbindung.py` — lädt `accounti.<baustein>.aufgaben_anbindung` aller Bausteine, bevor
  Prüfläufe, Objekttypen oder Kanäle gelesen werden. *(vorhanden)*

Intern gedacht: kein Portal für externe Nutzer.

### `steuer/`

Vollständiges Umsatzsteuer-Modul mit vier Komponenten:

- **`eu_steuersaetze.py`** — Datenbank aller 27 EU-Steuersätze + UK. Normal, ermäßigt, super-ermäßigt, Währung, OSS-Fähigkeit. Erweiterbar per YAML-Override.

- **`umsatzsteuer.py`** — Kern-Engine für USt/VSt-Berechnung:
  - Geschäftsvorfall-Bestimmung (Inland / EU-OSS / EU-B2B-RC / Drittland)
  - Netto ↔ Brutto-Umrechnung mit korrektem Steuersatz
  - Steuerkonten-Zuordnung (USt 1776/1771, VSt 1576/1571, OSS 1777xx)
  - DATEV BU-Schlüssel und ELSTER-Kennziffern
  - SKR03 OSS-Erlöskonten (8320-8339 pro Land)

- **`oss.py`** — One-Stop-Shop-Engine:
  - €10.000-Schwellenwertprüfung
  - Quartalsmeldung mit Aufschlüsselung nach Land und Steuersatz
  - Abgabefristen-Berechnung
  - CSV-Export der Meldung

- **`voranmeldung.py`** — USt-Voranmeldung:
  - Alle ELSTER-Kennziffern (Kz 81, 86, 41, 43, 66, 89...)
  - Zahllast-Berechnung (USt − VSt)
  - OSS-Umsätze als Info-Zeile (nicht Teil der VA)
  - Text-Zusammenfassung für Review

```
Transaktion
    │
    ▼
┌──────────────────────┐
│ Geschäftsvorfall?    │
│                      │
│ Käufer DE? ─────────▶ Inland (19%/7%)
│ Käufer EU + B2C? ───▶ OSS (Steuersatz Bestimmungsland)
│ Käufer EU + B2B? ───▶ ig. Lieferung (0%, Reverse Charge)
│ Käufer Drittland? ──▶ Ausfuhr (0%)
└──────────────────────┘
    │
    ▼
  Buchungssatz mit korrekter Steuer
  + Steuerkonto + DATEV-Schlüssel
  + ELSTER-Kennziffer
```

### `elster/` *(teilweise — [Baustein 9](specs/2026-08-10-steuermeldungen-elster.md))*

Die Rechenlogik liegt in `steuer/`; hier kommen Datensatz, Abgabe und Nachweis dazu.

- `konfiguration.py` — Abschnitt `elster` (`lade_elster`), alles optional. *(vorhanden)*
- `steuernummer.py` — Steuernummer des Landes → 13-stelliges ELSTER-Format, Finanzamtsnummer. *(vorhanden)*
- `datensatz.py` — ELSTER-XML (TransferHeader/NutzdatenHeader v11, Nutzdaten `ustva/v2026`, Kz09 = Hersteller-ID) für Voranmeldung und Dauerfristverlängerung; interne Prüfung inkl. nachgerechneter Kz 83. *(vorhanden)*
- `uebermittlung.py` — Schnittstelle `Uebermittler` (`pruefe`, `sende`), `AttrappenUebermittler`, Auswahl: ERiC nur mit Bibliothek, Zertifikat und PIN-Datei. *(vorhanden)*
- `eric.py` — ERiC über ctypes (Mt-API: Instanz, Zertifikat, `EricMtBearbeiteVorgang` mit EBV-8 zum Prüfen und EBV-6 zum Senden, Transferticket und PDF; Plugins aus `plugins2`). *(vorhanden, nicht gegen ELSTER erprobt)*
- `pin.py` — Zertifikats-PIN mit dem Tresor aus `bank/` verschlüsselt in einer Datei außerhalb der Datenbank. *(vorhanden)*
- `freigabe.py` — Freigabe durch einen Menschen, gebunden an den Hash der Formularwerte, einmal verwendbar. *(vorhanden)*
- `protokoll.py` — Tabelle `steuermeldung_protokolle`: Datensatz, Ticket, Zeitpunkt, Ergebnis, Prüfbericht, Serverantwort; nur anfügen, Hash-Kette, SQLite-Trigger, Datensatz und PDF im Belegarchiv; `pruefe_protokoll()` findet Lücken, Änderungen und veränderte Archivdateien. Eine berichtigte Anmeldung tritt daneben. *(vorhanden)*
- `zahllast.py` — Zahllast als Eigenbeleg, Buchung 1780 (SKR04 3820) an Kreditor „Finanzamt“ und offener Posten zur Abgabefrist, Erstattung als Forderung; Berichtigung bucht die Differenz und verrechnet sie mit dem offenen Posten; Sondervorauszahlung auf 1781/3830; `buche_fehlende` holt gescheiterte Buchungen nach. *(vorhanden)*
- `ustva.py` — Ablauf vorbereiten → freigeben → übermitteln (Testmodus, Testfall, echt; Testmodus beim ersten Lauf, Attrappe nie echt). *(vorhanden)*

Ergänzungen in `steuer/`:

- **`voranmeldung.py`** — Vordruck 2026: alle Kennziffern mit Zeile und Art, Bemessungsgrundlagen in vollen Euro, Steuer zu 81/86/89/93 wie ELSTER, Kz 83.
- **`kennziffern.py`** — Ermittlung aus Buchungssätzen: DATEV-Schlüssel und Kennzifferkonten (SKR03/SKR04), Vorzeichen über die Sachkontoseite bzw. die Zugangsseite der Kennziffer, Erlösschmälerungen über den Beleg, Umbuchung „Vorsteuer im Folgejahr“ als Kz 66, ZM-USt-IdNr. aus der Ausgangsrechnung, Warnungen (§ 13b ohne Leistenden, Aufwand ohne Schlüssel gegen EU-Kreditor mit USt-IdNr. „§ 13b prüfen“, Steuerkonto ohne Kennziffer).
- **`plausibilitaet.py`** — Befunde mit Schweregrad vor der Abgabe; Fehler sperren die Freigabe. `beleg_nach_zeitraum`: Vorsteuer aus einer Rechnung, die erst nach Ende des Zeitraums erfasst wurde (Warnung).
- **`zeitraum.py`**, **`feiertage.py`**, **`fristen.py`** — Meldezeiträume, Feiertage je Land, Fristen nach § 108 Abs. 3 AO.
- **`zusammenfassende_meldung.py`** — ZM je USt-IdNr. (L/D/S) mit CSV für den Portal-Import.

### `anlagen/` und `abschluss/` *(teilweise — [Baustein 12](specs/2026-08-10-anlagen-jahresabschluss.md))*

`anlagen/` führt Anlagegüter (`Anlagegut` in `models/anlagen.py`, Tabellen `anlagegueter`,
`afa_vorgaenge`) und schreibt die AfA fort.

- `rechtsstand.py` + `rechtsstand.yaml` — Grenzbeträge mit Gültigkeitszeitraum und Quelle: GWG,
  Verzeichnis, Sammelposten (2008/2009 Pflicht), degressive Fenster (Faktor, Höchstsatz),
  E-Fahrzeug-Staffel, digitale Wirtschaftsgüter, RAP-Verzicht, AfA-Tabelle. Maßgeblich ist der
  Anschaffungstag. Eigene Datei per `anlagen.rechtsstand`. *(vorhanden)*
- `afa.py` — AfA-Plan, rein: linear monatsgenau über die Kumulierte (keine Rundungsdrift),
  degressiv vom Restbuchwert mit Wechsel zur linearen AfA, GWG, Sammelposten (1/5 der Summe zum
  Jahresende), digital, E-Fahrzeug; Prüfung der Wahlrechte (einheitlicher Sammelposten). *(vorhanden)*
- `lauf.py` — AfA-Lauf: je Anlagegut Soll bis Monat minus schon gebucht, eine Buchung je
  AfA-/Anlagekonto, Begründung im Vorgang, Status „zur Prüfung“. *(vorhanden)*
- `abgang.py` — AfA bis Abgangsmonat, Restbuchwert auf 2310/2315, Erlös auf 8801/8820 mit USt aus
  `steuer/`. `spiegel.py` — Anlagenspiegel aus dem Plan. *(vorhanden)*

`abschluss/` arbeitet auf freigegebenen Buchungen.

- `kontenrahmen.py` + `kontenrahmen_skr03.yaml`/`…_skr04.yaml` — Kontoarten, Geld- und
  Steuerkonten, EÜR-Kennzahl je Kontenbereich. *(vorhanden)*
- `salden.py` — Kontobewegungen mit Steueraufteilung (Nettoseite, Steuerkonto, Bruttoseite;
  § 13b und ig. Erwerb mit Steuerpaar `steuerpaare`, z. B. SKR03 1577/1787),
  EB-Werte, Summen- und Saldenliste. *(vorhanden)*
- `kassenbuch.py` — Kassenbuch (Tabelle `kassenbuch`, nur anfügen): laufende Nummer, Bestand nie
  negativ, auch nicht rückwirkend; jeder Vorgang wird Transaktion des Kassenkontos. *(vorhanden)*
- `pruefungen.py` — benannte Abschlussprüfungen mit Befunden (Fehler/Warnung/Hinweis): u. a.
  Bank-Saldenabstimmung gegen `kontoauszugssalden`, Kassenbuch, AfA, offene Vorschläge. *(vorhanden)*
- `abgrenzung.py` — ARAP/PRAP-Vorschläge aus dem Leistungszeitraum, Auflösung je Folgejahr gleich
  mit (Tabelle `abgrenzungen`). *(vorhanden)*
- `euer.py` + `euer_vordrucke.yaml` — EÜR nach Kennzahlen, Zeilen je Vordruckjahr. *(vorhanden)*
- `vortrag.py` — Eröffnungssalden, Saldovortrag (EB gegen 9000/9008/9009), Jahressperre
  (`abschluesse`, ORM-Ereignis auf `buchungssaetze` in `db/tabellen_abschluss.py`; die CLI lädt es
  über `befehle/abschluss.py` beim Start). `protokoll.py` — Protokoll `abschlussprotokoll` (nur
  anfügen, Hash-Kette, bei jeder Abschlussprüfung nachgerechnet). *(vorhanden)*
- Bilanz/GuV, Rückstellungen und Übermittlung *(geplant)*.

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

### `bwa/`

Berechnet die BWA aus Buchungssätzen. Standard: DATEV BWA-Form 01. Unterstützt:
- Monatsauswertung
- Kumuliert (Jahresanfang bis Stichtag)
- Vorjahresvergleich

### `auth/` *(vorhanden — [Baustein 10](specs/2026-08-10-web-ui-auth-betrieb.md))*

Benutzer, Rollen, Sitzungen, zweiter Faktor, API-Token — alles in der **Systemdatenbank**
(ohne Registry: die Datenbank der Gesellschaft). Modelle `models/auth.py`, Tabellen
`db/tabellen_auth.py` (`auth_benutzer`, `auth_rollen`, `auth_wiederherstellungscodes`,
`auth_sitzungen`, `api_tokens`, `auth_ereignisse` — nur anfügen, SQLite-Trigger —,
`auth_merker`), Repository `db/repo_auth.py`.

- `passwort.py` — `hashlib.scrypt` (N = 2^17, r = 8, p = 1), Parameter im Hash, Neuberechnung
  bei der Anmeldung; Regeln nach NIST 800-63B-4 (Länge, Sperrliste, keine Zusammensetzung).
- `totp.py` — RFC 6238 mit `hmac` (Prüfwerte aus Anhang B), Toleranz ±1 Schritt, otpauth-URI;
  jeder Schritt wird nur einmal angenommen (`UPDATE … WHERE letzter < schritt`).
- `wiederherstellung.py` — zehn Codes je Benutzer, als HMAC mit einem Pepper aus dem Tresor
  gespeichert (ein Nachschlagen, gleiche Arbeit je Versuch), je einer genau einmal.
- `dienst.py` — anlegen, 2FA bestätigen (Geheimnis im Tresor, an den Benutzer gebunden),
  `pruefe_anmeldung` (Passwort **und** zweiter Faktor, sonst `AnmeldungError` ohne Grund;
  jeder Weg kostet eine Passwort-Prüfung), Sperre (jeder Versuch vor der Prüfung atomar
  gezählt, Obergrenze in Folge; Browser und Server-Shell getrennt), Sitzungen (256-Bit-Token, nur SHA-256 gespeichert,
  Leerlauf, Höchstdauer; Passwortwechsel, `benutzer sperren`, Rollenänderung und neuer
  zweiter Faktor beenden sie — Fehlversuche anderer nicht), Rollen je Gesellschaft.
- `token.py` — API-Token `accounti_api_…` mit Gesellschaft, Rechten (`TokenRecht`), Ablauf;
  nur SHA-256. Kein Token kann freigeben.
- `cli.py` — Rechte in der CLI: ohne Benutzer keine Prüfung; sonst Person mit Recht in der
  Gesellschaft der benutzten Datenbank und Einmalcode (in der CLI immer). Bindung jeder
  Gesellschafts-Datenbank an ihre Systemdatenbank (Merker `auth_merker`, fail-closed).
  Verwaltung mit Einrichtungsphase, fremde Konten nur durch Verwalter aller ihrer
  Gesellschaften. Eingebunden in `zahlung anlegen|freigeben|iban-klaeren|entfernen|sperre|stornieren`,
  `ustva freigeben`, `ustva dauerfrist`, `anlagen freigeben` und — über
  `befehle.handelnde_person`, das zugleich die geprüfte Person im Journal setzt — in die
  Befehle von Baustein 7 (vollständige Liste je Recht: `models.auth.FREIGABEWEGE`).
  Sperrwerte gelten in der CLI immer mit den Standardwerten, nie aus `--config`.
- `einstellungen.py` — Abschnitt `auth`.

Rollen → Rechte (`ROLLEN_RECHTE`): `betrachter` lesen · `buchhalter` lesen, buchen, Belege
einliefern, Läufe starten, Buchungen freigeben · `freigeber` lesen, Buchungen, Zahlungsläufe,
Steuermeldungen freigeben · `verwalter` lesen, verwalten. Additiv, nicht hierarchisch.

### `api/` *(Gerüst und REST-API vorhanden — [Baustein 10](specs/2026-08-10-web-ui-auth-betrieb.md))*

FastAPI-Anwendung aus `app.erstelle_app(Dienste)`: Systemdatenbank, Gesellschaften und ihre
Datenbanken (`dienste.py`), Sicherheitskopfzeilen und Zugriffsprotokoll ohne Personenbezug
(`sicherheit.py`), `/gesund`, `/statisch`. Gestartet mit `accounti serve` (`server.py`).

- `sitzung.py` — Dependencies `angemeldet`, `erfordert(Recht.X)`, `gesellschaft_db`; CSRF-Token
  aus dem Sitzungstoken, Pflicht bei jeder nicht lesenden Anfrage (Feld `csrf` oder Kopf
  `X-CSRF-Token`). Die aktive Gesellschaft steht in der Sitzung; Mitgliedschaft und Rechte
  werden je Anfrage neu gelesen.
- `seiten/` — HTML-Router-Registry (jedes Modul mit `router`, optional `NAVIGATION`):
  `anmeldung.py` (Passwort + Einmalcode, Double-Submit gegen Login-CSRF), `start.py`,
  `gesellschaft.py` (Wechsel), `freigaben.py` (Zahlungslauf, USt-VA mit frischem Einmalcode).
- `rest/` — REST-Registry unter `/api/v1`, nur mit API-Token (`erfordert_recht`, `TokenDb`):
  `ich`, `offene-posten`, `buchungen`, `belege` (über `belege.pipeline`, Kanal `api`),
  `laeufe/bank`, `laeufe/aufgaben`.
- `vorlagen/` + `vorlagen.py` (Jinja2, Autoescape, `basis.html`), `statisch/` (CSS), `formular.py`
  (urlencoded ohne `python-multipart`), `registry.py`, `einstellungen.py` (Abschnitt `server`).

Die Oberfläche ruft dieselben Funktionen wie die CLI. Geplant auf diesem Gerüst: die
Supervisions-Queue (links Beleg, rechts Vorschlag mit Confidence und Begründung, Korrektur in
einem Schritt, Angebot einer Regel), Auswertungen, DE/EN.

### `betrieb/` *(vorhanden — [Baustein 10](specs/2026-08-10-web-ui-auth-betrieb.md), [Betrieb](betrieb.md))*

- `gesellschaften.py` — Registry `gesellschaften`: je Kürzel Name, Datenbank, Archiv,
  Konfiguration, Regeln; Systemdatenbank; `${VAR}` erst bei Bedarf ersetzt.
- `kontext.py`, `cli.py` — Kontext je CLI-Aufruf: `--gesellschaft`/`ACCOUNTI_GESELLSCHAFT` bzw.
  `ACCOUNTI_DB`/`ARCHIV`/`KONFIG` setzen über `Context.default_map` die Standards von `--db`,
  `--archiv`, `--config` **aller** Befehle (Callback in `cli.py`).
- `verschluesselung.py`, `sicherung.py` — Sicherung als Tar-Strom (Tabellen als JSON-Zeilen,
  typgetreu; Archivdateien; Manifest mit SHA-256), AES-256-GCM in Stücken (STREAM, HKDF je
  Sicherung); Wiederherstellung nur in eine leere Umgebung, alles oder nichts.
- `aufbewahrung.py` — Fristen nach § 147 AO (BEG IV) und § 14b UStG, Bericht ohne Löschen;
  Journal, Buchungskorrekturen und Monatsabschlüsse als Bücher, ein spät festgeschriebener
  Monat als letzte Eintragung seines Wirtschaftsjahres.
- `planer.py` — geplanter Lauf (`bank lauf`, `aufgaben lauf` je Gesellschaft als Prozesse).
- `laufsperre.py` — je Gesellschaft und Art höchstens ein Lauf, über Prozesse hinweg
  (PostgreSQL-Advisory-Lock, SQLite-Dateisperre). Art `bank`: `bank lauf` und seine Schritte,
  `opos verbuchen`, `periode schliessen`; Art `aufgaben`: `aufgaben lauf`, `nachfordern`.
- `protokoll.py` — Schwärzung (IBAN, E-Mail, Token, Passwörter in URLs) an jedem Handler.

## Datenmodell

Der Kern steht in `models/` und ist umgesetzt: `Transaktion`, `Konto`, `Buchungssatz`,
`Klassifikationsergebnis`, `Regel`. Die geplanten Bausteine erweitern ihn um:

| Entität | Kernfelder | Bezug |
|---------|-----------|-------|
| `Beleg` | Belegart, Richtung, Belegnummer, Beleg-/Leistungsdatum, Netto/Steuer/Brutto, Zahlungsziel, Skonto, Datei-Hash, Kanal, Status | → `Kontakt` |
| `Belegposition` | Bezeichnung, Menge, Netto, Steuersatz, Steuerbetrag, Kontovorschlag | → `Beleg`; `Buchungssatz.beleg_position_id` |
| `AbgeholteNachricht` | Kanal, Quelle, Schlüssel (UIDVALIDITY/UID, Dokument-ID), Message-ID, Absender, Betreff, Dateien (Hash), Hinweis | → `Beleg` über den Datei-Hash |
| `Kontakt` | Name, Anschrift, Land, USt-IdNr., IBAN, Zahlungsbedingungen, Personenkonto | → `Beleg`, `OffenerPosten` |
| `OffenerPosten` | Richtung, Betrag, Restbetrag, Fälligkeit, Skontofrist, Status, Mahnstufe | → `Kontakt`, `Beleg` |
| `UstIdPruefung` | Nr., Zeitpunkt, USt-IdNr., Art, Anfrage/Antwort roh, BZSt-Status und -ID, Ergebnisse A–D, Vorgänger-Hash, Hash | → `Kontakt` (nur anfügen) |
| `Belegabgleich` | Stufe, Status (vorgeschlagen → bestätigt/abgelehnt), Confidence, Begründung, Differenz | → `Transaktion`, `Beleg` |
| `Zahlungslauf` | Nr., Status (Entwurf → freigegeben → eingereicht → ausgeführt / storniert), Ausführungstag, Auftraggeber, Freigabe-Hash, SEPA-Datei | → `Zahlung`, Protokoll |
| `Zahlung` | Lauf, Posten, Empfänger, IBAN, Betrag, Skonto, Verwendungszweck, EndToEndId | → `OffenerPosten`, `Kontakt` |
| `Mahnung` | Nr., Stufe, Datum, Rest, Verzugsbeginn mit Grund, Zinsen mit Abschnitten, Pauschale, Gebühren, Frist, B2B/B2C mit Grund, Status, Versandtag und -weg, Datei-Hash | → `OffenerPosten`, `Kontakt` |
| `Aufgabe` | Art, Titel, Objektbezug, Zuständigkeit, Fälligkeit, Status, Idempotenzschlüssel | → beliebiges Objekt |
| `Kommentar` | Art (Kommentar, Rückfrage, Ereignis), Autor, Text, Zeitpunkt, Anhang-Beleg | → `Aufgabe` und/oder beliebiges Objekt (nur anfügen) |
| `Anlagegut` | Anschaffungsdatum und -kosten, Nutzungsdauer, AfA-Art, Restbuchwert, Abgang | → `Beleg`, `Buchungssatz` |
| `Journaleintrag` | Laufende Nummer, Zeitpunkt, Person, Vorgang, Objekt, Vorher/Nachher (JSON), Grund, Bezug, Hash des Vorgängers, Hash | → Buchung, Beleg, Zahlungslauf, Periode, Geschäftsjahr, Export (nur anfügen) |
| `Buchungskorrektur` | Original, Storno, Neubuchung, Datum, Grund, Person | → `Buchungssatz` (nur anfügen) |
| `Periodenabschluss` | Monat, gesperrt, geschlossen/geöffnet (Zeit, Person), Grund | → Buchungen des Monats |
| `Befund` | Regel, Kategorie, Schwere, Objekt, Datum, Betrag, Gegenpartei, Begründung, Abhilfe | nicht gespeichert |

`Buchungssatz` hat zwei Ergänzungen: `beleg_position_id` für den Belegbezug (Prinzip 7) und
`storniert_durch` / `storno_von` (je eindeutig) für Korrekturen nach Freigabe (Prinzip 6).

## Datenfluss

```
                    ┌──────────────────────────────┐
                    │         PostgreSQL           │
  Belege ─────────▶ │  belege · belegpositionen    │
                    │  kontakte                    │
  Import ─────────▶ │  transaktionen               │
  Bank live ──────▶ │  bankkonten                  │
                    │  buchungssaetze              │
  Klassifikation ──▶│  regeln · konten             │
                    │  offene_posten · zahlungen   │
  Prüfung ────────▶ │  journal · korrekturen       │
                    │  aufgaben                    │
  Steuer ─────────▶ │  meldungen · protokolle      │
  Abschluss ──────▶ │  anlagegueter · abschluesse  │
  BWA ◀──────────── │  bwa_berichte                │
  DATEV ◀────────── │  export_log                  │
                    └──────────────────────────────┘
```

## Sicherheit

- API-Keys werden nie in der Datenbank gespeichert
- Bankzugänge und Übermittlungszertifikate liegen verschlüsselt, mit Schlüssel aus der Umgebung — nie im Klartext, nie in Logs
- LLM-Prompts enthalten keine echten Kontodaten — nur anonymisierte Muster
- DATEV-Exports werden lokal erzeugt, nie über externe APIs
- Self-Hosted: Deine Daten bleiben auf deinem Server. Deshalb ist auch die OCR-Engine standardmäßig lokal und Cloud-Verarbeitung opt-in
- Belege, Buchungen, Journale und Übermittlungsprotokolle unterliegen der zehnjährigen Aufbewahrungsfrist; das Löschkonzept kennt sie, statt sie zu ignorieren
- Anmeldung nur mit zweitem Faktor; Passwörter mit scrypt, Sitzungs- und API-Token nur als
  SHA-256, TOTP-Geheimnisse im Tresor; Freigaben mit Rolle und frischem Einmalcode
- Protokolle ohne IP-Adressen, Abfrageparameter, Namen, Token und Passwörter; Sicherungen
  verschlüsselt mit einem Schlüssel aus der Umgebung, getrennt aufzubewahren

## Erweiterungspunkte

### Neuen Baustein anschließen

Bausteine bringen ihren Code in eigene Module mit, damit sie unabhängig voneinander entstehen
können und keiner `cli.py`, `models/__init__.py` oder `db/tabellen.py` umbauen muss:

| Was | Wohin | Eingebunden durch |
|-----|-------|-------------------|
| Domänenmodelle | `src/accounti/models/<bereich>.py` | Import im Baustein |
| Tabellen | `src/accounti/db/tabellen_<bereich>.py` (Basis `accounti.db.Base`) | `registriere_tabellen()` — für `init_db` und Alembic |
| Repository-Funktionen | `src/accounti/db/repo_<bereich>.py` | Import im Baustein |
| CLI-Befehlsgruppe | `src/accounti/befehle/<bereich>.py` mit `NAME` und `befehl = typer.Typer(...)` | `haenge_befehle_ein()` in `cli.py` |
| Konfiguration | eigener Abschnitt in `config/accounti.yaml`, eigener Lader im Baustein | — |
| HTML-Seiten der Oberfläche | `src/accounti/api/seiten/<bereich>.py` mit `router` (optional `NAVIGATION`) | `routermodule()` in `api/app.py` |
| REST-Endpunkte | `src/accounti/api/rest/<bereich>.py` mit `router` | `routermodule()` in `api/app.py`, Präfix `/api/v1` |

Migrationen entstehen beim Zusammenführen mit `alembic revision --autogenerate`.

### Neues Bankformat hinzufügen

Kein Code nötig — ein Profil in `config/banken.yaml` genügt:

```yaml
# config/banken.yaml
- name: meinebank
  delimiter: ";"
  encoding: auto
  datum_spalte: Buchungstag
  datum_format: "%d.%m.%Y"
  betrag_spalte: Betrag
  dezimal: ","
  verwendungszweck_spalte: Verwendungszweck
  gegenkonto_spalte: Empfänger
  erkennungs_spalten: [Buchungstag, Empfänger]   # für --format auto
```

Danach: `accounti import bank auszug.csv --format meinebank` (oder `--format auto`).
Für Betragsspalten mit getrennten Soll/Haben-Feldern: `betrag_modus: soll_haben`
plus `soll_spalte`/`haben_spalte`.

### Neuen Beleg-Kanal hinzufügen

Ein Kanal implementiert die Basisklasse aus `belege/kanaele/` und trägt sich in die Registry
`BELEG_KANAELE` ein — dasselbe Muster wie `BANK_IMPORTERS`. Er liefert Rohdatei plus
Herkunftsmetadaten, sonst nichts: Erkennung, OCR, Dublettenprüfung und Archivierung passieren
dahinter und sind für alle Kanäle identisch.

Wer nur ein anderes Postfach oder Verzeichnis anbinden will, braucht keinen neuen Kanal, sondern
nur einen Eintrag im Abschnitt `belegkanaele` der `config/accounti.yaml`.

Ein Belegportal braucht meist keinen neuen Kanal, sondern nur einen Eintrag unter
`belegkanaele.connectoren` mit `typ: json`. Reicht das nicht (OAuth, POST-Abfragen, eigene
Formate), implementiert ein Connector `BelegConnector` (`dokumente()`, `lade()`, eigenes
Einstellungsmodell) und trägt sich mit `registriere_connector` in `BELEG_CONNECTOREN` ein —
Dateiprüfung, Gedächtnis, Dublettenprüfung und Archiv bleiben dieselben.

### Neuen Bank-Provider hinzufügen

Ein Provider implementiert die Schnittstelle aus `bank/provider.py`: `felder` (Einstellungen),
`geheime_felder` (landen im Tresor) und `abrufen(konto, zugang, ab)` — Umsätze ab einem Stand,
optional Saldo. Verlangt die Bank eine Freigabe, fragt er über die mitgegebene Rückfrage nach
oder meldet `FreigabeNoetigError`; ändern sich Zugangsdaten (Sitzung, Tokens), gibt er sie in
`Abruf.zugang` zurück. Alles dahinter (Normalisierung, Dublettenschutz, Abgleich, Kontierung) ist
providerunabhängig. Vorbild: `bank/fints.py`.

Weil der bestehende Dateiimport selbst als Provider eingehängt ist, bleibt accounti auch dann
vollständig nutzbar, wenn kein einziger Live-Provider eingerichtet ist.

### Neue Prüfregel hinzufügen

Prüfregeln aus `pruefung/regeln/` sind benannt, tragen einen Schweregrad und liefern Befunde —
sie ändern nie Daten. Schwellenwerte (ab welchem Betrag ein fehlender Beleg auffällt, wie viele
Tage Zeitgerechtheit bedeutet) gehören in die Konfiguration, nicht in den Code.

Eine Klasse mit `name`, `kategorie`, `schwere`, `beschreibung`, einem Pydantic-Modell
`Parameter` (Schwellen mit Standardwerten) und `pruefe(kontext, parameter) -> list[Befund]`,
eingetragen mit `registriere_pruefregel`. Der `Kontext` bringt Sitzung, Zeitraum, Stichtag,
Einstellungen und einmal geladene Bestände mit; Schwellen setzt der Betrieb unter
`pruefung.regeln.<name>`, den Schweregrad unter `pruefung.schwere.<name>`.

### Aufgaben aus einem anderen Baustein melden

Direkt: `melde_aufgabe(session, art, Objekt(typ, id), titel=…, erzeugt_von=…)` und
`schliesse_wenn_erledigt(…)`, sobald der Anlass entfällt — mit einer eigenen Art. Als
Prüflauf: eine Klasse mit `name`, `beschreibung`, `grund_entfallen` und `finde(session,
einstellungen, stichtag, zeitraum) -> Pruefergebnis`, eingetragen mit `registriere_prueflauf`
in einem Modul `accounti.<baustein>.aufgaben_anbindung` — das Modul wird von selbst geladen,
der Lauf läuft mit `accounti aufgaben pruefen` und schließt Entfallenes selbst. Jeder
Prüflauf besitzt genau eine Aufgabenart, auch Aufgaben, die andere mit dieser Art angelegt
haben; wer die Regeln eines eingebauten Laufs ändern will, registriert einen Lauf gleichen
Namens. Eigene Objekttypen (`registriere_objekttyp`) und Benachrichtigungskanäle
(`adresse()` und `sende()`, eingetragen in `KANAELE`, in der Konfiguration unter
`benachrichtigung.kanaele` genannt) gehören in dasselbe Modul.

### Neue Kontierungsregel hinzufügen

```yaml
# config/regeln.yaml (geplant)
- name: "mein_lieferant"
  muster: "Firma XY GmbH"
  feld: "gegenkonto_name"
  soll_konto: "3300"
  haben_konto: "1200"
  steuer_schluessel: 9
  buchungstext: "Wareneinkauf Firma XY"
```
