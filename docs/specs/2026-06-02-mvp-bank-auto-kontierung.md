# Spec: MVP „Bank-Auto-Kontierung"

- **Status:** Entwurf, vom Maintainer genehmigt (2026-06-02)
- **Baustein:** 1 von 5 der Produktvision (siehe unten)
- **Ziel-Branch:** `mvp/bank-auto-kontierung`

## 1. Kontext & Produktvision

accounti ist eine **Open-Source-Software für deutsche KMU**, die die Buchhaltung auf ein Minimum
reduziert und damit den Steuerberater-Aufwand senkt. Es ersetzt nicht den Steuerberater, sondern
die manuelle Arbeit *zwischen Belegeingang und Steuerberater*.

Die Gesamtvision zerfällt in eigenständige Bausteine (je eigenes Spec → Plan → Build):

| # | Baustein | Dieses Spec |
|---|----------|-------------|
| **1** | **Bankauszug → Auto-Kontierung (Regeln + KI) → DATEV/CSV** | ✅ |
| 2 | Beleg-OCR → Kontierung → Abgleich mit Bank | — |
| 3 | USt/OSS-Auswertung & Meldungen | — |
| 4 | Supervision-Web-UI | — |
| 5 | Integrationen (Bank, Marktplätze, DATEV) | — |

Dieses Spec beschreibt **ausschließlich Baustein 1**.

## 2. Ziel des MVP

> Ein Bankauszug (CSV) geht hinein, kontierte Buchungssätze kommen heraus — automatisch,
> mit KI für unbekannte Buchungen, DATEV-konform.

Eine in sich nützliche, vorzeigbare Scheibe, die das Kernversprechen beweist. Heute laufen bereits
~62 % davon (Regel-Engine + Export existieren); dieses MVP schließt die Lücken und verdrahtet alles.

## 3. Pipeline

```
CSV (Bankauszug)
   │  [1] Importer       Sparkasse-CSV → Transaktion-Objekte
   ▼
Transaktionen
   │  [2] Klassifikation
   │      Stufe A: YAML-Regelwerk   (deterministisch, confidence = 1.0)
   │      Stufe B: LLM via LiteLLM  (Claude default / Ollama optional)
   ▼
Klassifikationsergebnisse (+ confidence, + Begründung, + Quelle)
   │  [3] Buchung        Ergebnis → Buchungssatz (Netto/Steuer-Split via steuer/)
   │  [4] Persistenz     SQLite (SQLAlchemy + Alembic), Postgres-ready
   ▼
   [5] Review-Report     Auto vs. „zur Prüfung" (Confidence-Schwelle)
   │  [6] Export         DATEV-EXTF (konform!) + generisches CSV
   ▼
   [7] Feedback          Korrektur → neue YAML-Regel (Lernschleife)
```

Entspricht der bestehenden `docs/architektur.md` (Regelwerk vor KI, Nachvollziehbarkeit,
Supervisor hat das letzte Wort, DATEV-Kompatibilität 1:1).

## 4. Komponenten & Arbeitspakete

### 4.1 `importers/` — Bank-Importer *(neu)*
- `BankImporter`-Basisklasse + `BANK_IMPORTERS`-Registry (wie in `architektur.md` skizziert).
- `SparkasseImporter`: parst das Sparkassen-CSV-Format
  (Spalten: `Auftragskonto;Buchungstag;Valutadatum;Buchungstext;Verwendungszweck;`
  `Begünstigter/Zahlungspflichtiger;Kontonummer;BLZ;Betrag;Währung;Info`).
- Robustes Parsing: deutsches Datum `TT.MM.JJ`, deutscher Betrag `1.250,00` / `-89,50`,
  Encoding-Erkennung (utf-8 / cp1252), leere Zeilen, Header-Varianten.
- Mappt auf `Transaktion` (Feld `quelle = BANK`, `rohtext` = Originalzeile).
- Weitere Banken später über Spalten-Mapping — **nicht** im MVP.

### 4.2 `klassifikation/` — Regeln + echte LLM-Stufe *(erweitern)*
- Regeln aus `config/regeln.yaml` laden (Format wie in `architektur.md` dokumentiert),
  Fallback auf `STANDARD_REGELN`.
- **`LLMEngine` echt implementieren** (ersetzt `NotImplementedError`):
  - LiteLLM-Aufruf, Default-Modell `anthropic/claude-*`, konfigurierbar (inkl. `ollama/...`).
  - **Structured Output** (Konto, Gegenkonto, Steuerschlüssel, Confidence, Begründung).
  - **Datenschutz (Pflicht, lt. `architektur.md` §Sicherheit):** Prompt enthält *keine*
    echten Kontodaten — IBAN/Namen/Belegnummern werden vor dem Versand anonymisiert/maskiert.
  - Confidence-Schwelle: ≥ `auto_buchen_schwelle` → auto; darunter → „zur Prüfung".
  - Fehlertoleranz: LLM nicht erreichbar / kein Key → Transaktion bleibt „zur Prüfung",
    Pipeline bricht nicht ab.

### 4.3 `buchung/` — Mapper *(neu, Modul ist leer)*
- `Klassifikationsergebnis → Buchungssatz`.
- Netto/Steuer-Split über vorhandenes `steuer/umsatzsteuer.py` (Brutto→Netto + Steuerbetrag),
  Steuerschlüssel setzen, `status` aus Confidence ableiten.

### 4.4 `db/` — Persistenz *(neu)*
- SQLAlchemy-Modelle für `transaktionen`, `buchungssaetze`, `regeln`, `export_log`.
- Alembic-Migration (initial). SQLite-Default (`accounti.db`), Verbindungs-String konfigurierbar.
- **Postgres-ready:** keine SQLite-spezifischen Typen; Decimal/Date/UUID portabel halten.
- Pydantic-Modelle (`models/`) bleiben die Domänenobjekte; SQLAlchemy-Modelle sind die Persistenz —
  klare Trennung, Mapping in einer Schicht.

### 4.5 `export/datev.py` — Konformität *(fixen)*
Abgleich gegen echte `EXTF_Buchungsstapel_*`-Dateien ergab Lücken:
- **`QUOTE_ALL` → DATEV-Quoting:** Beträge & Kontonummern **ohne** Anführungszeichen,
  nur Textfelder gequotet (DATEV: `197,06;"S";"";;;"";1200;6999999;...`).
- **WKZ Umsatz** pro Zeile **leer** (Währung steht im Header), nicht `"EUR"`.
- Sachkontenlänge konfigurierbar (Default 4, real oft 6).
- Header-Felder gegen Echt-Datei verifizieren (Versions-/Format-Felder).

### 4.6 `cli.py` — echte Verdrahtung *(Stubs ersetzen)*
```bash
accounti db init                              # SQLite anlegen / migrieren
accounti import bank auszug.csv               # → Transaktionen gespeichert
accounti classify --period 2026-04            # Regeln + LLM, Confidence-Report
accounti review  --period 2026-04             # unsichere prüfen/korrigieren (lernt)
accounti export datev --period 2026-04 \
        --berater 23426 --mandant 40005       # konformer Buchungsstapel
```

## 5. Tech-Entscheidungen (fix)

| Thema | Entscheidung |
|-------|--------------|
| KI | LiteLLM, Default `anthropic/claude-*`, Option Ollama; Key via `.env` |
| Datenschutz | Cloud als Default, lokal als Option; **PII-Maskierung in LLM-Prompts** |
| Persistenz | SQLAlchemy + Alembic, SQLite-Default, Postgres-ready |
| Bank | Sparkasse zuerst, Importer steckbar |
| Output | DATEV-EXTF (konform, gegen Echt-Dateien getestet) + CSV |
| Interface | CLI |

## 6. Teststrategie

- **Unit-Tests** pro Stufe: Importer (Datum/Betrag/Encoding-Kanten), Regeln, Mapper, Export.
- **Golden-Tests:** Export gegen anonymisierte, von echten `EXTF_Buchungsstapel_*`-Dateien
  abgeleitete Fixtures (Format-Konformität 1:1).
- **LLM gemockt** für deterministische Tests; optionaler Live-Smoke-Test hinter Marker.
- Bestehende 53 Tests bleiben grün; `ruff` + `mypy --strict` sauber.

## 7. Akzeptanzkriterien (Definition of Done)

1. `accounti import bank examples/beispiel_sparkasse.csv` lädt 8 Transaktionen in die DB.
2. `accounti classify` kontiert per Regel **und** LLM; die heute 3 offenen Buchungen
   (Telekom, Büromaterial, eBay) erhalten einen Vorschlag **oder** landen begründet „zur Prüfung".
3. `accounti export datev` erzeugt eine Datei, die **strukturell 1:1** einer echten
   DATEV-EXTF-Datei entspricht (Golden-Test grün).
4. Eine Korrektur im `review` wird als neue Regel gespeichert und beim nächsten Lauf angewandt.
5. Ohne LLM-Key läuft die Pipeline regelbasiert sauber durch.

## 8. Ausdrücklich NICHT im MVP

Beleg-OCR · Web-UI/`api/` · Marktplatz-Import (Amazon/PayPal/eBay) · direkte DATEV-Cloud-Anbindung ·
Multi-Mandant · Postgres-Betrieb · MT940/CAMT · BWA-Ausbau. Alles spätere Bausteine.
