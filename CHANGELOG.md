# Changelog

Alle wesentlichen Änderungen an accounti werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [Unreleased]

### Hinzugefügt
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
