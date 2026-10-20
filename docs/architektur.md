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

Geplant (eigene Importer, kein Bank-CSV): `mt940.py`, `camt.py` (XML), `jtl.py`, `amazon.py`, `ebay.py`, `paypal.py`.

### `belege/` *(vorhanden — [Baustein 2](specs/2026-08-10-belegerfassung.md))*

Bringt Belege ins System und macht Daten daraus. Kanäle folgen demselben Registry-Muster wie die Bank-Importer: `ordner`, `email`, `upload`, `webhook`, `connector` — jeder liefert nur Rohdatei plus Herkunft, keiner kennt Buchhaltungslogik.

- `erkennung.py` — E-Rechnung, PDF mit Textebene oder Scan? Strukturierte Daten schlagen immer OCR. Klassifiziert die Belegart (Eingangs-/Ausgangsrechnung, Quittung, Kontoauszug, …). `BelegErkenner` verbindet Format, Text, Regelwerk und LLM und ist der `erkenner` der Pipeline. *(vorhanden; E-Rechnungen werden bis Baustein 3 nur erkannt)*
- `extraktion.py` — Regelwerk: Belegnummer, Daten, Lieferant, USt-IdNr., IBAN (mit Prüfziffer), Zahlungsziel, Skonto, Steuerzeilen, Summen, Rechenprobe. *(vorhanden)*
- `ocr/` — steckbar über `OCR_ENGINES`; `tesseract` lokal als Default, damit die Zusage „Daten bleiben auf deinem Server" hält. Fehlt Tesseract, geht der Beleg mit Hinweis in die Prüfung. *(vorhanden)*
- `llm.py` — zweite Stufe, nur mit `--llm`. Der Belegtext geht maskiert hinaus (IBAN, USt-IdNr., E-Mail, Telefon, Lieferant, Belegnummer); das LLM füllt nur Lücken, das Regelwerk gewinnt. *(vorhanden)*
- `positionen.py` — Positionssplit. Eine Rechnung kann mehrere Konten betreffen; eine Kreditkartenabrechnung ist eine Datei mit vielen Umsätzen. *(vorhanden: eine Position je Steuersatz, Kreditkartenumsätze einzeln)*
- `dubletten.py` — Datei-Hash, dann Lieferant + Rechnungsnummer, dann Betrag + Datum im engen Fenster. *(vorhanden)*
- `archiv.py` — Originaldatei unverändert, content-adressiert, mit Aufbewahrungsfrist. Kein Löschpfad. *(vorhanden)*
- `kanaele/` — `BELEG_KANAELE`-Registry: `ordner`, `upload`, `email`, `webhook`, `connector`. Alle liefern nur Rohdatei plus Herkunft; `pruefung.py` prüft für alle Typ am Inhalt (PDF, XML ohne DTD, JPEG, PNG, TIFF) und Größe. `email.py` holt Anhänge per IMAP (UID-Befehle, `BODY.PEEK[]`, Ordner nur lesend, TLS mit Zertifikatsprüfung), Absender als Hinweis; `gedaechtnis.py` merkt verarbeitete Nachrichten in `kanal_nachrichten` (Ordner + UIDVALIDITY + UID, Message-ID) erst, wenn alle Anhänge aufgenommen sind; gelesen markiert oder verschoben wird eine Nachricht nur, wenn nichts abgelehnt wurde. `connector.py` ist Basisklasse und Registry `BELEG_CONNECTOREN` für Belegportale, `json_http.py` der generische JSON/HTTP-Connector. Geheimnisse nur als `${VAR}` oder im Tresor (`zugaenge.py`, AES-GCM wie `bank/tresor.py`). Konfiguration: Abschnitt `belegkanaele` (`einstellungen.py`). *(vorhanden)*
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

### `bank/` *(teilweise — [Baustein 5](specs/2026-08-10-bankanbindung-live.md))*

Holt Kontoumsätze selbst ab und führt sie mit Belegen zusammen.

- `provider.py` — Registry wie bei den Importern: `fints` (Direktverbindung, Default), `psd2` (Aggregator, opt-in), `datei` (der bestehende Dateiimport hinter derselben Schnittstelle, `datei.py`). Damit bleibt accounti ohne jede Bankverbindung vollständig nutzbar. Verlangt die Bank eine Freigabe, meldet der Provider das als Zustand am Konto. *(vorhanden: Schnittstelle und `datei`)*
- `tresor.py` — Zugangsdaten mit AES-GCM verschlüsselt, Schlüssel aus `ACCOUNTI_SCHLUESSEL`, das Chiffrat an das Konto gebunden. *(vorhanden)*
- `dubletten.py` — Dublettenschlüssel aus Konto, Datum, Betrag, Verwendungszweck, Gegenpartei und laufender Nummer gleicher Umsätze; gilt für Abruf und `import bank`. *(vorhanden)*
- `lauf.py` — Abruf aller Konten (ab Stand minus 14 Tage) und der geplante Lauf: abrufen → offene Posten zuordnen → abgleichen → kontieren; idempotent. Umsätze tragen das Sachkonto ihres Bankkontos. *(vorhanden)*
- `abgleich.py` — Beleg ↔ Umsatz, dreistufig: Referenz, exakter Treffer, unscharfer Vorschlag. Bewusst streng — ein falscher Abgleich begründet eine falsche Vorsteuer und ist teurer als ein fehlender. Abgeglichen werden Quittungen und sonstige Belege; Rechnungen laufen über offene Posten. Automatisch nur, was auf beiden Seiten eindeutig ist; zwei gleiche Belege werden zwei Vorschläge. *(vorhanden)*
- `abgleichslauf.py` — Tabelle `belegabgleiche` (vorgeschlagen/bestätigt/abgelehnt), Bestätigen verwirft konkurrierende Vorschläge, Bericht „Umsätze ohne Beleg / Belege ohne Umsatz“. *(vorhanden)*
- Bankkonten (`Bankkonto` in `models/`, Tabelle `bankkonten`) — IBAN, Sachkonto, Provider, Einstellungen, verschlüsselter Zugang, Abrufstand, Zustand; Zugangsdaten nie in Logs, nie im LLM-Prompt. *(vorhanden)*

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

Debitoren- und Kreditorenstammdaten mit Personenkontonummern aus den Nummernkreisen des Kontenrahmens (Abschnitt `buchhaltung`, Standard 10000–69999 / 70000–99999). `erkennung.py` findet Kontakte über IBAN, dann USt-IdNr., dann den normalisierten Namen (Rechtsform, Satzzeichen, Umlaut-Schreibweisen egal) — greift nichts, geht die Neuanlage zur Prüfung, statt still zu passieren. `dienst.py` legt an, vergibt das Personenkonto der Rolle und ergänzt fehlende Angaben, ohne vorhandene zu überschreiben. *(vorhanden)*

`ustid.py` führt die qualifizierte Bestätigungsabfrage beim BZSt durch (eVatR-REST-API `POST https://api.evatr.vies.bzst.de/app/v1/abfrage`; die XML-RPC-Schnittstelle ist seit 30.11.2025 abgeschaltet) und protokolliert sie revisionssicher: Tabelle `ustid_pruefungen` mit Rohanfrage und Rohantwort, laufender Nummer und SHA-256-Hash-Kette; Änderungen und Löschungen scheitern am ORM, unter SQLite zusätzlich an Triggern; `pruefe_protokoll()` findet Lücken und veränderte Einträge. Bestätigt ist eine Nummer erst mit `evatr-0000` aus einer qualifizierten Abfrage, bei der Name und Ort nicht abweichen; es zählt die jüngste aussagekräftige Antwort innerhalb von `ustid_pruefung.max_alter_tage`. Erst damit steht die in `steuer/umsatzsteuer.py` implementierte Regel „EU + B2B mit USt-ID → 0 %" auf einer belastbaren Grundlage: `erechnung/ausstellung.py` stellt K und AE ohne Bestätigung nicht aus, `opos/verbuchung.py` bucht solche Erlöse nur zur Prüfung. *(vorhanden)*

### `opos/` *(vorhanden — [Baustein 4](specs/2026-08-10-kreditoren-debitoren-opos.md))*

Offene Posten mit Fälligkeit, Skontofrist und Restbetrag. `verbuchung.py` macht aus einem erfassten Beleg die Buchungen je Steuersatz (Eingang: Sachkonto aus Kontakt-Vorschlag, Regelwerk oder Standard zur Prüfung; Ausgang: Erlöskonto nach Steuerkategorie der E-Rechnung) und den Posten; jeder Beleg genau einmal, jeder in eigenem Savepoint. `auswertung.py` liefert OPOS-Liste, Fälligkeitsstaffel und Summen je Kontakt. *(vorhanden)*

`zuordnung.py` ordnet Banktransaktionen dreistufig zu — Referenz (Belegnummer im Verwendungszweck), exakt (einziger Posten des Kontakts über den Betrag), unscharf (Skonto ohne Referenz, Sammelzahlung als Teilmengensumme, Teilbetrag, Betrag ohne Kontakt). Automatisch gebucht wird nur Eindeutiges; der Rest wird Vorschlag. `ausgleich.py` bucht Zahlung und Skonto — das Skonto anteilig nach den Bruttoanteilen der Rechnung auf ihre Steuersätze verteilt, Netto und Steuer je Anteil aus `steuer/`, also immer mit Vorsteuer- bzw. Umsatzsteuerkorrektur. `zahlungslauf.py` verbindet beides, reserviert vorgeschlagene Posten und speichert jede Zuordnung in `zahlungszuordnungen`; `classify` kontiert nur noch Transaktionen ohne Buchung und ohne Zuordnung. *(vorhanden)* `zuordnung.py` ordnet Zahlungen dreistufig zu (Referenz, exakt, unscharf), `ausgleich.py` bucht den Ausgleich — bei gezogenem Skonto immer **mit** anteiliger Steuerkorrektur, nie als reine Betragsdifferenz.

### `zahlung/` und `mahnwesen/` *(geplant — [Baustein 6](specs/2026-08-10-zahlungsverkehr-mahnwesen.md))*

`zahlung/` erzeugt die Vorschlagsliste (Skontofristen vor Nettofälligkeiten), prüft blockierend — eine vom Stammsatz abweichende IBAN stoppt den Lauf —, verwaltet die Freigabe als Zustandsautomaten und schreibt SEPA-Sammelüberweisungen. Einreichung über den Bank-Provider oder als Datei; der Dateiweg bleibt immer verfügbar.

`mahnwesen/` führt Mahnstufen aus `config/mahnwesen.yaml`, berechnet Verzugszinsen mit datiertem Basiszinssatz und zählt die Stufe am offenen Posten hoch.

### `pruefung/` *(geplant — [Baustein 7](specs/2026-08-10-belegvollstaendigkeit-gobd.md))*

Die Mechanik hinter den Prinzipien 6 und 7. Benannte Prüfregeln mit Schweregrad liefern Befunde und ändern nie Daten: Umsatz ohne Beleg, Beleg ohne Zahlung, Lücken in Nummernkreisen, § 14 UStG-Pflichtangaben, Rechenprobe, Steuerschlüssel ./. Sachkonto, Zeitgerechtheit.

`journal.py` führt das hashverkettete, append-only Journal. `perioden.py` schließt Zeiträume ab. `verfahrensdoku.py` generiert die Verfahrensdokumentation aus dem tatsächlichen Systemzustand statt aus einem Textbaustein, der nach der ersten Konfigurationsänderung nicht mehr stimmt.

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

### `elster/` *(geplant — [Baustein 9](specs/2026-08-10-steuermeldungen-elster.md))*

Die Rechenlogik der Meldungen liegt in `steuer/` und ist fertig; hier kommt der letzte Schritt dazu: Plausibilisierung vor der Abgabe, Übermittlung von Voranmeldung, Dauerfristverlängerung und Zusammenfassender Meldung, sowie das unveränderbare Protokoll aus Datensatz, Ticket, Zeitpunkt und Prüfbericht.

Ein Testmodus erzeugt und prüft, ohne abzugeben. Die Freigabe durch einen Menschen ist nicht abkürzbar — eine Steuererklärung wird abgegeben, nicht ausgelöst.

### `anlagen/` und `abschluss/` *(geplant — [Baustein 12](specs/2026-08-10-anlagen-jahresabschluss.md))*

`anlagen/` führt Anlagegüter und schreibt die AfA fort (linear zeitanteilig, GWG, Sammelposten), erstellt den Anlagenspiegel und rechnet Abgänge. Grenzbeträge sind Konfiguration **mit Gültigkeitszeitraum**, damit alte Jahre mit den damals gültigen Werten rechenbar bleiben.

`abschluss/` bildet Abgrenzungen und Rückstellungen als Vorschläge — Bewertungen werden bestätigt, nicht gesetzt —, führt das Kassenbuch (negativer Bestand wird abgelehnt, nicht gewarnt), erstellt EÜR oder Bilanz mit GuV und trägt die Salden ins neue Jahr vor.

### `export/`

**DATEV-Export** (Priorität):
- EXTF-Format Version 700
- Buchungsstapel + Debitoren/Kreditoren
- cp1252-Encoding (DATEV-Standard)

Weitere Exportformate:
- CSV (generisch)
- JSON (für API-Konsumenten)

Geplant ([Baustein 11](specs/2026-08-10-integrationen-export.md)): Debitoren-/Kreditoren-Stammdaten, Belegbilder mit Verknüpfung zum Buchungssatz, Kontoauszüge, Prüfungsdatenüberlassung.

### `bwa/`

Berechnet die BWA aus Buchungssätzen. Standard: DATEV BWA-Form 01. Unterstützt:
- Monatsauswertung
- Kumuliert (Jahresanfang bis Stichtag)
- Vorjahresvergleich

### `auth/` *(geplant — [Baustein 10](specs/2026-08-10-web-ui-auth-betrieb.md))*

Benutzer, Rollen, Sitzungen, Zwei-Faktor-Authentifizierung. Rollen `betrachter` / `buchhalter` / `freigeber` / `verwalter`; die Trennung von Buchen und Freigeben ist die Voraussetzung dafür, dass das Vier-Augen-Prinzip überhaupt greifen kann. Ab hier trägt jeder Journaleintrag einen echten Benutzer statt einer freien Zeichenkette.

### `api/`

REST-API (FastAPI) für:
- Supervision: Buchungen prüfen, korrigieren, freigeben
- BWA-Abfrage
- Import-Trigger
- Statusübersicht

Web-UI: Minimalistisch mit HTMX + Jinja2 (kein SPA-Build-Step).

Kernansicht ist die Supervisions-Queue: links die Belegvorschau, rechts der Buchungsvorschlag mit Confidence und Begründung, Korrektur in einem Schritt — und das Angebot, aus der Korrektur eine Regel zu machen. Die Oberfläche ruft dieselben Funktionen auf wie die CLI; Logik, die nur im Browser existiert, gibt es nicht.

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
| `Zahlung` | Lauf, Betrag, Ausführungsdatum, Status (Entwurf → freigegeben → eingereicht → ausgeführt) | → `OffenerPosten` |
| `Aufgabe` | Art, Titel, Objektbezug, Zuständigkeit, Fälligkeit, Status, Idempotenzschlüssel | → beliebiges Objekt |
| `Kommentar` | Art (Kommentar, Rückfrage, Ereignis), Autor, Text, Zeitpunkt, Anhang-Beleg | → `Aufgabe` und/oder beliebiges Objekt (nur anfügen) |
| `Anlagegut` | Anschaffungsdatum und -kosten, Nutzungsdauer, AfA-Art, Restbuchwert, Abgang | → `Beleg`, `Buchungssatz` |
| `Journaleintrag` | Laufende Nummer, Zeitpunkt, Benutzer, Vorgang, Vorher/Nachher, Hash des Vorgängers | → alles Buchungsrelevante |

`Buchungssatz` bekommt zwei Ergänzungen: `beleg_position_id` für den Belegbezug (Prinzip 7) und
`storniert_durch` / `storno_von` für Korrekturen nach Freigabe (Prinzip 6).

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
  Prüfung ────────▶ │  befunde · journal           │
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

Ein Provider erbt von `BankProvider` aus `bank/provider.py`, nennt seine Einstellungen (`felder`)
und Zugangsdaten (`geheime_felder`, landen verschlüsselt im Tresor), liefert mit `abrufen(konto,
zugang, ab)` Umsätze und optional den Saldo und trägt sich mit `registriere` in `BANK_PROVIDER`
ein; eine Freigabe der Bank meldet er als `FreigabeNoetigError`. Alles dahinter
(Normalisierung, Dublettenschutz, Abgleich, Kontierung) ist providerunabhängig.

Weil der bestehende Dateiimport selbst als Provider eingehängt ist, bleibt accounti auch dann
vollständig nutzbar, wenn kein einziger Live-Provider eingerichtet ist.

### Neue Prüfregel hinzufügen *(geplant)*

Prüfregeln aus `pruefung/regeln/` sind benannt, tragen einen Schweregrad und liefern Befunde —
sie ändern nie Daten. Schwellenwerte (ab welchem Betrag ein fehlender Beleg auffällt, wie viele
Tage Zeitgerechtheit bedeutet) gehören in die Konfiguration, nicht in den Code.

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
