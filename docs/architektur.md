# accounti — Architektur

## Überblick

accounti ist als Pipeline aufgebaut: Daten fließen in eine Richtung von Import über Klassifikation und Buchung bis zum Export. Jede Stufe kann unabhängig getestet und erweitert werden.

```
Import → Klassifikation → Buchung → Export/BWA
                ↑                        │
                └── Lernschleife ────────┘
```

## Designprinzipien

1. **Regelwerk vor KI**: Deterministische Regeln sind schneller, billiger und nachvollziehbar. Das LLM kommt nur zum Einsatz, wenn keine Regel greift.

2. **Nachvollziehbarkeit**: Jede Buchung speichert ihre Herkunft — ob per Regel oder LLM, mit welcher Confidence, und welche Begründung die KI gegeben hat.

3. **Supervisor hat das letzte Wort**: Nichts wird exportiert ohne menschliche Freigabe (zumindest in den ersten Versionen). Automatische Buchungen sind opt-in.

4. **DATEV-Kompatibilität**: Der Export muss 1:1 in DATEV importierbar sein. Kein "fast richtig".

5. **Erweiterbar**: Neue Bankformate, ERP-Quellen und Kontenrahmen sollen ohne Kernänderungen hinzufügbar sein.

## Module

### `importers/`

Importer wandeln Rohdaten einer Quelle in `Transaktion`-Objekte um — sie kennen nur ihr Format, keine Buchhaltungslogik.

Bank-CSVs laufen **konfigurationsgetrieben** über `profil.py`: Ein `BankProfil` beschreibt Trennzeichen, Encoding, Datums-/Betragsformat und die Spalten-Zuordnung; der generische `ProfilImporter` parst damit jede unterstützte Bank — ohne bankspezifischen Code.

- `profil.py` — `BankProfil` + `ProfilImporter`, eingebaute Profile (sparkasse, ing, dkb, volksbank, commerzbank), Auto-Erkennung (`erkenne_profil`) und Laden eigener Profile aus `config/banken.yaml`.
- `sparkasse.py` — dünner Wrapper um das Sparkasse-Profil (Rückwärtskompatibilität).
- Registry `BANK_IMPORTERS` (Bankname → einsatzbereiter Importer); `import bank --format auto` erkennt die Bank an den Spaltenüberschriften.

Geplant (eigene Importer, kein Bank-CSV): `mt940.py`, `camt.py` (XML), `jtl.py`, `amazon.py`, `ebay.py`, `paypal.py`.

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

### `export/`

**DATEV-Export** (Priorität):
- EXTF-Format Version 700
- Buchungsstapel + Debitoren/Kreditoren
- cp1252-Encoding (DATEV-Standard)

Weitere Exportformate:
- CSV (generisch)
- JSON (für API-Konsumenten)

### `bwa/`

Berechnet die BWA aus Buchungssätzen. Standard: DATEV BWA-Form 01. Unterstützt:
- Monatsauswertung
- Kumuliert (Jahresanfang bis Stichtag)
- Vorjahresvergleich

### `api/`

REST-API (FastAPI) für:
- Supervision: Buchungen prüfen, korrigieren, freigeben
- BWA-Abfrage
- Import-Trigger
- Statusübersicht

Web-UI: Minimalistisch mit HTMX + Jinja2 (kein SPA-Build-Step).

## Datenfluss

```
                    ┌─────────────────────────┐
                    │      PostgreSQL          │
                    │                          │
  Import ─────────▶ │  transaktionen           │
                    │  buchungssaetze          │
  Klassifikation ──▶│  regeln                  │
                    │  konten                   │
  BWA ◀──────────── │  bwa_berichte            │
                    │  export_log              │
  DATEV ◀────────── │                          │
                    └─────────────────────────┘
```

## Sicherheit

- API-Keys werden nie in der Datenbank gespeichert
- LLM-Prompts enthalten keine echten Kontodaten — nur anonymisierte Muster
- DATEV-Exports werden lokal erzeugt, nie über externe APIs
- Self-Hosted: Deine Daten bleiben auf deinem Server

## Erweiterungspunkte

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
