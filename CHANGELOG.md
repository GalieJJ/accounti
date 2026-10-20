# Changelog

Alle wesentlichen Änderungen an accounti werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [Unreleased]

### Hinzugefügt
- **Live-Bankanbindung, Paket 2 – Provider, Konten, Abruf** (Baustein 5): Bankkonten mit
  Sachkonto und Provider (`accounti bank verbinde|konten`); Zugangsdaten werden mit AES-GCM
  verschlüsselt (Schlüssel aus `ACCOUNTI_SCHLUESSEL`, `accounti bank schluessel`), nie im
  Klartext gespeichert; Provider-Schnittstelle mit Registry und Datei-Provider (Ordner mit
  Kontoauszügen); `accounti bank abrufen` holt neue Umsätze aller Konten ab dem letzten Stand,
  eine Freigabe der Bank wird als Zustand gemeldet; `accounti bank lauf` für Cron: abrufen →
  offene Posten zuordnen → Belege abgleichen → kontieren. Neue Abhängigkeit `cryptography`
  (Apache-2.0/BSD)
- **Live-Bankanbindung & Belegabgleich, Paket 1 – Belegabgleich** (Baustein 5): `accounti bank
  abgleich` führt Bankumsätze mit Quittungen und sonstigen Belegen zusammen, bevor kontiert
  wird — Referenz (Belegnummer im Verwendungszweck), exakt (Betrag, 0–7 Tage, Gegenpartei über
  IBAN oder Namen) und unscharf als Vorschlag (Betrag ohne Namenstreffer, Rundungsdifferenz,
  Trinkgeld); automatisch nur, was auf beiden Seiten eindeutig ist, zwei gleiche Belege werden
  zwei Vorschläge; Gutschriften werden erkannt, Rücklastschriften gemeldet statt abgeglichen;
  `bank vorschlaege|bestaetigen|ablehnen|offen`. `classify` bucht abgeglichene Umsätze aus dem
  Beleg: je Steuersatz, Vorsteuer aus dem Beleg, Sachkonto aus Kontakt oder Regelwerk auf die
  Belegdaten; Trinkgeld/Differenz ohne Steuer zur Prüfung; Ausgabe „davon n mit Beleg“
- **Kreditoren, Debitoren & offene Posten, Paket 3 – USt-IdNr.-Prüfung** (Baustein 4 damit
  fertig): qualifizierte Bestätigungsabfrage beim BZSt über die eVatR-REST-API
  (`accounti kontakte pruefe-ustid`, `--einfach`); jede Abfrage — auch eine gescheiterte —
  steht mit Rohantwort in einem Protokoll, das nur wachsen kann (Hash-Kette, ORM-Sperre,
  SQLite-Trigger, Aufbewahrungsfrist); `accounti kontakte ustid-protokoll` zeigt, prüft und
  exportiert es (`--csv`); `kontakte zeigen` nennt die letzte Prüfung; neuer, optionaler
  Abschnitt `ustid_pruefung` (`max_alter_tage`, `timeout_sekunden`, `url` bzw.
  `ACCOUNTI_EVATR_URL`); Echtabfrage mit den Testwerten des BZSt als Test
  (`ACCOUNTI_EVATR_LIVE=1`)
- **Kreditoren, Debitoren & offene Posten, Paket 2 – Zahlungen** (Baustein 4): `accounti opos
  zuordnen` ordnet Banktransaktionen offenen Posten zu — Referenz (Belegnummer im
  Verwendungszweck), exakt (einziger Posten des Kontakts), unscharf als Vorschlag (Skonto ohne
  Referenz, Sammelzahlung, Teilbetrag, unbekannter Kontakt); Eindeutiges wird sofort
  ausgeglichen: vollständig, Teilzahlung oder Skonto mit anteiliger Vorsteuer- bzw.
  Umsatzsteuerkorrektur (Skontokonten 3736/3731/3730 und 8736/8731/8730, konfigurierbar);
  Überzahlung bleibt als Guthaben auf dem Personenkonto; `opos vorschlaege|bestaetigen|ablehnen`;
  vorgeschlagene Posten sind für andere Zahlungen reserviert
- **Kreditoren, Debitoren & offene Posten, Paket 1** (Baustein 4): Kontakte mit Personenkonten
  (Kreise konfigurierbar im neuen, optionalen Abschnitt `buchhaltung`), Kontakterkennung aus
  Belegen über IBAN → USt-IdNr. → normalisierten Namen, automatische Neuanlage zur Prüfung;
  `accounti opos verbuchen` bucht erfasste Rechnungen gegen Kreditor bzw. Debitor (Sachkonto aus
  Kontakt-Vorschlag oder Regelwerk, Erlöskonto nach Steuerkategorie) und legt offene Posten mit
  Fälligkeit und Skontofrist an; OPOS-Liste und Fälligkeitsstaffel; CLI `kontakte
  liste|zeigen|bestaetigen|bearbeiten`, `opos verbuchen|liste|staffel`; `korrigiere --lernen`
  merkt sich bei Belegbuchungen das Sachkonto am Kontakt; ein Beleg der eigenen Firma (Name oder
  USt-IdNr. aus `mandant`) wird nie als Kreditor gebucht
- **Beleg:** IBAN des Ausstellers wird übernommen (Extraktion und E-Rechnung)

- **E-Rechnung, Paket 3 – ZUGFeRD und Versand** (Baustein 3 damit fertig): Jede ausgestellte
  Rechnung gibt es zusätzlich als ZUGFeRD-PDF (Profil XRECHNUNG, PDF/A-3b) mit lesbarem Layout
  nach DIN 5008 und der XRechnung als Anhang; formale Prüfung mit Mustang/veraPDF; XML und PDF
  werden archiviert. Versand per E-Mail (`accounti rechnung senden`, SMTP mit STARTTLS/SSL,
  Passwort aus Umgebungsvariable), gesendet wird immer die archivierte Datei; jeder Versuch steht
  im Versandprotokoll; `--eml` schreibt die Nachricht nur in eine Datei. Neue Abhängigkeit
  `fpdf2` (LGPL-3.0), Schrift Liberation Sans (SIL OFL) mitgeliefert
- **Prüfwerkzeuge:** `scripts/pruefwerkzeuge_installieren.sh` installiert KoSIT und Mustang mit
  festen Versionen und SHA-256 nach `.pruefwerkzeuge/` (ersetzt `scripts/kosit_installieren.sh`
  und `.kosit/`); `--ohne-formale-pruefung` (alt: `--ohne-kosit`)
- **E-Rechnung, Paket 2 – Ausgang** (Baustein 3): Ausgangsrechnungen als Entwurf schreiben und
  als XRechnung 3.0 (CII) ausstellen; lückenlose Nummernkreise je Gesellschaft und Jahr, auch bei
  parallelen Zugriffen; Steuer ausschließlich über `steuer/` (Inland, Reverse-Charge bei
  EU-B2B-Dienstleistungen, innergemeinschaftliche Lieferung, Ausfuhr, OSS); vor dem Ausstellen
  fachliche Prüfung und formale Prüfung mit dem KoSIT-Prüftool, bei Fehlern Rollback ohne
  verbrauchte Nummer; ausgestellte Rechnung wird archiviert und als Beleg geführt; CLI
  `accounti rechnung neu|position|zeigen|liste|ausstellen` und `rechnung pruefen --kosit`;
  Firmendaten im Abschnitt `mandant` von `config/accounti.yaml`; `scripts/pruefwerkzeuge_installieren.sh`
- **Steuer:** `UStBerechner` unterscheidet Lieferung und sonstige Leistung — EU-B2B-Dienstleistung
  mit USt-IdNr. ist Reverse Charge (`EU_B2B_REVERSE_CHARGE`, USt-VA Kz 21)
- **E-Rechnung Eingang:** Lieferanschrift (BG-15) wird gelesen; neue Regeln BR-IC-12 und
  BR-DE-10/11; OSS-Sätze des Bestimmungslands gelten als plausibel
- **E-Rechnung, Paket 1 – Eingang** (Baustein 3): Zwischenmodell nach EN 16931; Parser für
  XRechnung (UBL Invoice/CreditNote, CII) und ZUGFeRD/Factur-X mit Profilerkennung; fachliche
  Validierung mit Befunden nach Schweregrad (EN-16931-Geschäftsregeln, BR-DE-3/4/15, § 14 UStG,
  Steuersatz zum Land); E-Rechnungen werden in der Beleg-Pipeline ohne OCR übernommen, Fehler
  gehen mit Regel und Befund zur Prüfung; neuer Befehl `accounti rechnung pruefen`; Fixtures
  unter `examples/erechnung/` inklusive einer Auswahl der offiziellen KoSIT-Testsuite
- **Belegerfassung, Paket 2** (Baustein 2): `BelegErkenner` liest Belege beim Eingang —
  PDF-Textebene über `pypdf` (neue Abhängigkeit), OCR steckbar mit lokaler Tesseract-Engine,
  Erkennung von XRechnung/ZUGFeRD (Übernahme folgt mit Baustein 3), Regelwerk-Extraktion mit
  Rechenprobe, Belegart-Regeln, Positionen je Steuersatz, Zerlegung von
  Kreditkartenabrechnungen, optionale maskierte LLM-Stufe (`--llm`); unvollständige Belege gehen
  mit Begründung in die Prüfung; neuer Befehl `accounti belege erkennen`; Textfixtures unter
  `examples/belege/`
- **Belegerfassung, Paket 1** (Baustein 2): Datenmodell `Beleg`, `Belegposition` und
  Eingangsprotokoll `BelegEingang`; Kanäle `ordner` und `upload` über die Registry
  `BELEG_KANAELE`; content-adressiertes, schreibgeschütztes Belegarchiv mit Aufbewahrungsfrist;
  dreistufige Dublettenerkennung; CLI `accounti belege kanaele|import|abholen|liste`;
  `Buchungssatz.beleg_position_id`; Alembic-Migration `add belege`
- Projektstruktur und Datenmodell
- CLI-Grundgerüst (Import, Classify, BWA, Export, Serve)
- Sparkasse CSV-Importer
- Regelwerk-Engine mit Standard-Kontierungsregeln (SKR03)
- DATEV-ASCII-Export (Buchungsstapel EXTF Format 700)
- BWA-Berechnung nach DATEV-Schema Form 01
- SKR03-Kontenrahmen als YAML-Konfiguration
- **Umsatzsteuer-Modul**: Netto/Brutto-Berechnung, Steuerautomatik
- **EU-Steuersätze**: Vollständige DB aller 27 EU-Staaten + UK
- **OSS-Verfahren**: Schwellenwertprüfung, Quartalsmeldung, Länderzuordnung
- **USt-Voranmeldung**: ELSTER-Kennziffern, Zahllast-Berechnung
- **Geschäftsvorfall-Engine**: Inland, EU B2C (OSS), EU B2B (Reverse Charge), Drittland
- Tests für Klassifikation, DATEV-Export, USt, OSS und EU-Steuersätze
- CI-Pipeline (GitHub Actions)

### Geändert
- **Umsätze mehrerer Bankkonten** werden gegen das Sachkonto ihres Kontos gebucht (Kontierung,
  Ausgleich offener Posten, Kontierung mit Beleg) statt pauschal gegen `buchhaltung.bank_konto`
- **`classify`** kontiert über den neuen Kontierungslauf: abgeglichene Umsätze aus dem Beleg,
  Umsätze mit offenem Beleg-Vorschlag bleiben liegen; neue Option `--config`; `opos zuordnen`
  lässt Umsätze mit Beleg-Abgleich in Ruhe
- **Steuerfreie EU-Rechnungen nur mit bestätigter USt-IdNr.:** `rechnung ausstellen` fragt bei
  Kategorie K (innergemeinschaftliche Lieferung) und AE (Reverse Charge) beim BZSt an, wenn
  keine aktuelle Bestätigung vorliegt, und stellt bei ungültiger Nummer oder abweichendem
  Namen/Ort nicht aus (die Nummer bleibt frei); `opos verbuchen` bucht solche Erlöse ohne
  Bestätigung nur zur Prüfung und nennt den Grund
- **CI:** `actions/checkout` und `actions/setup-python` auf v7 (Node 24); Tesseract mit deutschen
  Sprachdaten wird installiert, damit die echten OCR-Tests laufen
- **Belegerkennung:** OCR-Text wird normalisiert (`19 $`, `7°/o` → `%`); hinter einem Betrags-Label
  zählt der erste Betrag; Brutto wird auch in Zeilen mit Netto-Angabe gefunden. Neues Fixture
  `examples/belege/quittung_tankstelle_scan.jpg` für einen echten OCR-Durchlauf
- **Bauplan von 5 auf 12 Bausteine erweitert** — neue Übersicht in [`docs/bauplan.md`](docs/bauplan.md),
  je ein Spec unter `docs/specs/` für die Bausteine 2 bis 12. Neu aufgenommen: Belegerfassung mit
  OCR, E-Rechnung (Eingang und Ausgang), Kreditoren/Debitoren mit offenen Posten,
  Live-Bankanbindung mit Belegabgleich, Zahlungsverkehr und Mahnwesen, Belegvollständigkeits- und
  Ordnungsmäßigkeitsprüfung mit unveränderbarem Journal, Aufgaben und Rückfragen, elektronische
  Übermittlung der Steuermeldungen, Benutzer/Rollen/2FA, vollständige DATEV-Übergabe sowie
  Anlagenbuchhaltung und Jahresabschluss.
- README: Feature-Übersicht nach Bereichen gegliedert und um den Ist-Stand ergänzt; Roadmap folgt
  jetzt den Bausteinen; Positionierung präzisiert (Buchhaltung im eigenen Haus, keine
  Mandantenbetreuung für Dritte).
- `docs/architektur.md`: neue Module beschrieben, Designprinzipien um Unveränderbarkeit und
  Belegbezug erweitert, Datenmodell und Erweiterungspunkte ergänzt.

### Behoben
- **`import bank`** hat dieselbe Datei beim zweiten Import doppelt eingelesen; Umsätze tragen
  jetzt einen Dublettenschlüssel und werden nur einmal gespeichert
- Ein zweiter `accounti classify`-Lauf hat alle Transaktionen erneut gebucht; jetzt werden nur
  Transaktionen ohne Buchung und ohne Zahlungszuordnung kontiert
- Die Belegnummer eines Buchungssatzes wurde nicht gespeichert — der DATEV-Export ließ
  „Belegfeld 1" deshalb leer
