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
