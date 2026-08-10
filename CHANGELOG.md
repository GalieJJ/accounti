# Changelog

Alle wesentlichen Änderungen an accounti werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [Unreleased]

### Hinzugefügt
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
