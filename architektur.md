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

Jede Datenquelle hat einen eigenen Importer, der Rohdaten in `Transaktion`-Objekte umwandelt. Ein Importer kennt nur sein Format — keine Buchhaltungslogik.

Geplante Importer:
- `bank.py` — Bank-CSV (Sparkasse, Volksbank, ING, N26, ...)
- `mt940.py` — SWIFT MT940 (universelles Bankformat)
- `camt.py` — CAMT.053 (XML, moderneres Bankformat)
- `jtl.py` — JTL-Wawi Export (Rechnungen, Zahlungen)
- `amazon.py` — Amazon Settlement Reports
- `ebay.py` — eBay Managed Payments
- `paypal.py` — PayPal-Transaktionsberichte

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

```python
# src/accounti/importers/bank.py

class MeineBankImporter(BankImporter):
    name = "meinebank"
    encoding = "utf-8"
    delimiter = ";"

    def parse_zeile(self, zeile, raw):
        # Implementierung hier
        ...

# In BANK_IMPORTERS registrieren:
BANK_IMPORTERS["meinebank"] = MeineBankImporter
```

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
