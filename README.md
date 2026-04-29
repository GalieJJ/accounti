<p align="center">
  <img src="docs/logo-placeholder.svg" alt="accounti" width="120" />
</p>

<h1 align="center">accounti</h1>

<p align="center">
  <strong>KI-gestützte Buchhaltungsautomatisierung für deutsche Unternehmen</strong><br>
  Open Source · SKR03/SKR04 · DATEV-Export · BWA · Self-Hosted
</p>

<p align="center">
  <a href="#features">Features</a> ·
  <a href="#quickstart">Quickstart</a> ·
  <a href="#architektur">Architektur</a> ·
  <a href="#roadmap">Roadmap</a> ·
  <a href="CONTRIBUTING.md">Mitmachen</a> ·
  <a href="LICENSE">Lizenz</a>
</p>

---

## Was ist accounti?

**accounti** automatisiert die laufende Buchhaltung für kleine und mittlere Unternehmen in Deutschland. Es ersetzt nicht den Steuerberater — es ersetzt die manuelle Arbeit *zwischen* Belegeingang und Steuerberater.

Du importierst Transaktionsdaten (Bankkonto, ERP, Marktplätze), accounti klassifiziert und kontiert automatisch nach SKR03/SKR04, erzeugt Buchungssätze, erstellt eine BWA und exportiert alles DATEV-konform. Du supervisierst nur noch.

### Das Problem

- Belege manuell kontieren kostet Stunden pro Woche
- DATEV-Exporte aus ERP-Systemen sind teuer (z.B. JERA ~50€/Monat) oder fehleranfällig
- BWA gibt es erst Wochen später vom Steuerberater
- Bestehende Tools sind Closed Source, teuer, oder für den US-Markt gebaut

### Die Lösung

```
Bankdaten / ERP / Marktplätze
        │
        ▼
   ┌─────────┐
   │ accounti │  ← KI-gestützte Kontierung
   └─────────┘
        │
   ┌────┼────┐
   ▼    ▼    ▼
 DATEV  BWA  Dashboard
```

---

## Features

| Status | Feature | Beschreibung |
|--------|---------|-------------|
| 🔲 | **Multi-Import** | CSV/MT940/CAMT von Banken, JTL-Wawi, Shopify, Amazon, eBay |
| 🔲 | **KI-Kontierung** | Automatische SKR03/SKR04-Zuordnung per LLM + Regelwerk |
| 🔲 | **Buchungssätze** | Soll/Haben mit Steuer, Kostenstelle, Belegnummer |
| 🔲 | **BWA** | Betriebswirtschaftliche Auswertung nach DATEV-Schema |
| 🔲 | **DATEV-Export** | ASCII-konformer Export (Buchungsstapel + Stammdaten) |
| 🔲 | **Supervisionsansicht** | Web-UI zum Prüfen, Korrigieren, Freigeben |
| 🔲 | **Lernschleife** | Korrekturen fließen als Training zurück |
| 🔲 | **Multi-Mandant** | Mehrere Firmen, Wirtschaftsjahre, Kontenrahmen |
| 🔲 | **Umsatzsteuer** | Automatische USt/VSt-Berechnung, Steuerautomatik, ELSTER-Kennziffern |
| 🔲 | **OSS-Verfahren** | EU-weite MwSt (27 Länder), Schwellenwertprüfung, Quartalsmeldung |
| 🔲 | **USt-Voranmeldung** | Kennziffern für ELSTER, Zahllast-Berechnung |
| 🔲 | **Multi-Marketplace** | Amazon (DE/FR/IT/ES/NL/UK/SE/PL), eBay, PayPal — korrekte Steuersätze je Land |

---

## Quickstart

> ⚠️ **accounti ist in aktiver Entwicklung.** Die folgenden Schritte beschreiben das Zielbild.

### Voraussetzungen

- Python 3.11+
- PostgreSQL 15+
- Ein LLM-Zugang (Anthropic API, OpenAI, oder lokales Modell via Ollama)

### Installation

```bash
git clone https://github.com/DEIN-USER/accounti.git
cd accounti
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Konfiguration
cp config/accounti.example.yaml config/accounti.yaml
# → API-Keys und Datenbankverbindung eintragen

# Datenbank initialisieren
accounti db init

# Starten
accounti serve
```

### Erster Import

```bash
# Banktransaktionen importieren
accounti import bank ./meine-umsaetze.csv --format sparkasse

# KI-Kontierung starten
accounti classify --period 2026-04

# BWA generieren
accounti bwa --period 2026-04

# DATEV-Export
accounti export datev --period 2026-04 --berater 23426 --mandant 40005
```

---

## Architektur

```
accounti/
├── src/
│   ├── importers/        # Datenquellen: Bank-CSV, MT940, CAMT, JTL, Amazon...
│   ├── klassifikation/   # KI-Engine: LLM + Regelwerk + Lernschleife
│   ├── buchung/          # Buchungssatz-Erzeugung (Soll/Haben/Steuer)
│   ├── steuer/           # USt-Berechnung, OSS-Verfahren, EU-Steuersätze
│   ├── export/           # DATEV-ASCII, CSV, JSON
│   ├── bwa/              # BWA-Berechnung nach DATEV-Schema
│   └── api/              # REST-API + Web-UI für Supervision
├── config/               # Kontenrahmen (SKR03/04), Steuerschlüssel, Regeln
├── tests/
├── docs/
└── examples/             # Beispiel-Imports und Konfigurationen
```

### Pipeline

```
┌──────────┐    ┌───────────────┐    ┌──────────┐    ┌────────┐    ┌────────┐
│  Import  │───▶│ Klassifikation│───▶│ Buchung  │───▶│ Export │───▶│  BWA   │
│          │    │               │    │          │    │        │    │        │
│ Bank-CSV │    │ 1. Regelwerk  │    │ Soll/Hab │    │ DATEV  │    │ Schema │
│ MT940    │    │ 2. LLM-Match  │    │ MwSt     │    │ CSV    │    │ GuV    │
│ JTL-Wawi │    │ 3. Supervisor │    │ KSt      │    │ JSON   │    │ Bilanz │
│ Amazon   │    │    Feedback   │    │ BelegNr  │    │        │    │        │
└──────────┘    └───────────────┘    └──────────┘    └────────┘    └────────┘
                       ▲                                               │
                       └──── Lernschleife (Korrekturen → Regeln) ──────┘
```

### Klassifikations-Strategie

accounti nutzt einen **dreistufigen Ansatz**:

1. **Regelwerk** (deterministisch): Feste Zuordnungen für bekannte Geschäftsvorfälle. "Amazon Payments" → Erlöse 8400, "AWS" → EDV-Kosten 4970. Schnell, zuverlässig, kein API-Call nötig.

2. **LLM-Klassifikation** (probabilistisch): Für unbekannte Transaktionen. Das LLM bekommt den Kontenrahmen + Kontext und schlägt Konto + Steuerschlüssel vor. Confidence-Score bestimmt, ob automatisch gebucht oder zur Prüfung vorgelegt wird.

3. **Supervisor-Feedback**: Korrekturen durch den Menschen werden als neue Regeln gespeichert. Das System lernt mit jeder Korrektur und braucht das LLM immer seltener.

### Datenmodell (Kern)

```
Transaction          Buchungssatz           Konto
─────────────        ─────────────          ──────
id                   id                     nummer (z.B. "8400")
datum                transaction_id ───┐    name
betrag               soll_konto ───────┤    typ (Aktiv/Passiv/Erlös/Aufwand)
verwendungszweck     haben_konto ──────┘    kontenrahmen (SKR03/SKR04)
quelle (bank/erp)    betrag_netto
rohtext              steuer_schluessel
status               steuer_betrag
confidence           beleg_nummer
                     kostenstelle
                     status (auto/geprüft)
```

---

## Kontenrahmen & Steuer

accounti liefert SKR03 und SKR04 als YAML-Dateien mit:

- Kontonummern und Bezeichnungen
- Kontotypen (Bilanz/GuV)
- BWA-Zuordnung (BWA-Zeile je Konto)
- Steuerautomatik (Vorsteuer/Umsatzsteuer)
- Steuerschlüssel nach DATEV-Standard

```yaml
# config/skr03.yaml (Auszug)
konten:
  "8400":
    name: "Erlöse 19% USt"
    typ: erloes
    bwa_zeile: 1
    steuer:
      schluessel: 3    # USt 19%
      automatik: true
  "4970":
    name: "Nebenkosten des Geldverkehrs"
    typ: aufwand
    bwa_zeile: 14
    steuer:
      schluessel: 9    # VSt 19%
      automatik: true
```

---

## Umsatzsteuer & OSS-Verfahren

accounti berechnet Umsatzsteuer automatisch — für Inland, EU und Drittland:

### Dreistufige Vorfallbestimmung

```
Wo sitzt der Käufer?
        │
        ▼
   ┌─ Inland (DE) ──────────────▶ 19% / 7% USt
   │
   ├─ EU-Land ─┬─ B2B + USt-ID ─▶ 0% (ig. Lieferung / Reverse Charge)
   │            │
   │            └─ B2C ──────────▶ OSS: Steuersatz des Bestimmungslands
   │                               (FR 20%, IT 22%, ES 21%, SE 25%...)
   │
   └─ Drittland (UK, CH, US...) ─▶ 0% (Ausfuhr)
```

### EU-Steuersätze (alle 27 Mitgliedsstaaten)

accounti enthält eine vollständige Datenbank aller EU-Steuersätze (Normal, ermäßigt, super-ermäßigt) inklusive UK (post-Brexit). Auszug:

| Land | Normal | Ermäßigt | Währung |
|------|--------|----------|---------|
| 🇩🇪 DE | 19% | 7% | EUR |
| 🇫🇷 FR | 20% | 5,5% | EUR |
| 🇮🇹 IT | 22% | 10% | EUR |
| 🇪🇸 ES | 21% | 10% | EUR |
| 🇳🇱 NL | 21% | 9% | EUR |
| 🇸🇪 SE | 25% | 12% | SEK |
| 🇵🇱 PL | 23% | 8% | PLN |
| 🇬🇧 UK | 20% | 5% | GBP |

### OSS-Verfahren (One-Stop-Shop)

Seit Juli 2021 müssen B2C-Fernverkäufe in andere EU-Länder über €10.000 p.a. mit dem Steuersatz des Bestimmungslands versteuert werden. accounti:

- Trackt die **€10.000-Schwelle** über alle EU-B2C-Verkäufe
- Berechnet den **korrekten Steuersatz** je Bestimmungsland
- Bucht auf **separate OSS-Erlöskonten** (SKR03: 8320-8339)
- Erstellt die **Quartalsmeldung** mit Aufschlüsselung nach Land und Steuersatz
- Kennt die **Abgabefristen** (letzter Tag des Folgemonats)
- Markiert OSS-Umsätze korrekt als **nicht Teil der USt-Voranmeldung**

### USt-Voranmeldung

accounti berechnet alle ELSTER-Kennziffern:

| Kz | Beschreibung |
|----|-------------|
| 81 | Steuerpflichtige Umsätze 19% |
| 86 | Steuerpflichtige Umsätze 7% |
| 41 | Innergemeinschaftliche Lieferungen |
| 43 | Ausfuhrlieferungen |
| 66 | Abziehbare Vorsteuer |
| ... | Zahllast = USt − VSt |

---

## DATEV-Export

accounti erzeugt DATEV-konforme ASCII-Dateien nach dem Format "Buchungsstapel" (Header-Version 700+):

- **EXTF Buchungsstapel**: Alle Buchungssätze eines Zeitraums
- **EXTF Debitoren/Kreditoren**: Stammdaten
- Berater-Nr., Mandanten-Nr., Wirtschaftsjahr, Sachkonten-Länge — alles konfigurierbar

---

## BWA (Betriebswirtschaftliche Auswertung)

Die BWA wird aus den Buchungssätzen berechnet, nicht aus Rohdaten. Das Standardformat orientiert sich am DATEV-BWA-Schema (BWA-Form 01):

| Zeile | Bezeichnung | Konten (SKR03) |
|-------|-------------|----------------|
| 1 | Umsatzerlöse | 8000-8099, 8300-8499 |
| 2 | Bestandsveränderungen | 8900-8989 |
| 3 | Aktivierte Eigenleistungen | 8990-8999 |
| ... | ... | ... |
| 14 | Sonstige betriebliche Aufwendungen | 4900-4999 |
| ... | ... | ... |
| Rohergebnis | Zeile 1-8 | |
| Betriebsergebnis | Rohergebnis - Personalkosten - Abschreibungen - sonst. Aufwand | |

---

## Roadmap

### Phase 1 — Fundament (v0.1)
- [ ] Datenmodell + PostgreSQL-Schema
- [ ] SKR03/SKR04 als YAML-Konfiguration
- [ ] CSV-Import (Sparkasse, Volksbank, Commerzbank)
- [ ] Regelwerk-Engine für bekannte Buchungen
- [ ] Umsatzsteuer-Berechnung (Inland 19%/7%)
- [ ] DATEV-ASCII-Export (Buchungsstapel)
- [ ] CLI-Interface

### Phase 2 — KI-Kontierung + Steuer (v0.2)
- [ ] LLM-Integration (Anthropic Claude, OpenAI, Ollama)
- [ ] Confidence-Scoring und Schwellenwerte
- [ ] Lernschleife: Korrekturen → neue Regeln
- [ ] MT940/CAMT-Import
- [ ] BWA-Berechnung
- [ ] OSS-Verfahren: EU-Steuersätze, Schwellenwertprüfung
- [ ] OSS-Quartalsmeldung mit Aufschlüsselung nach Land
- [ ] USt-Voranmeldung (ELSTER-Kennziffern)

### Phase 3 — ERP- & Marketplace-Integration (v0.3)
- [ ] JTL-Wawi Import (Rechnungen, Zahlungen, Stornos)
- [ ] Amazon Settlement Reports (DE/FR/IT/ES/NL/UK/SE/PL)
- [ ] eBay Managed Payments Import
- [ ] Bestimmungsland-Erkennung aus Marketplace-Daten
- [ ] Multi-Mandanten-Fähigkeit
- [ ] DATEV Debitoren/Kreditoren-Export

### Phase 4 — Supervision-UI (v0.4)
- [ ] Web-Dashboard (FastAPI + React/HTMX)
- [ ] Buchungsvorschau mit Korrekturmöglichkeit
- [ ] BWA-Ansicht mit Vorjahresvergleich
- [ ] Beleg-Upload und Zuordnung

### Phase 5 — Produktion (v1.0)
- [ ] Automatischer Monatsabschluss-Workflow
- [ ] E-Mail-Import für Belege
- [ ] API für Drittsysteme
- [ ] Docker-Setup für einfaches Deployment
- [ ] Umfassende Dokumentation + Tutorials

---

## Technologie-Stack

| Komponente | Technologie | Begründung |
|-----------|-------------|------------|
| Sprache | Python 3.11+ | Ecosystem, LLM-Libraries, Community |
| Datenbank | PostgreSQL | ACID, JSON-Spalten, bewährt |
| ORM | SQLAlchemy 2.0 | Standard, async-fähig |
| API | FastAPI | Async, OpenAPI-Docs, modern |
| CLI | Typer | Click-basiert, einfach |
| LLM | LiteLLM | Abstrahiert Anthropic/OpenAI/Ollama |
| Frontend | HTMX + Jinja2 | Leichtgewichtig, kein Build-Step |
| Testing | pytest | Standard |

---

## Mitmachen

Wir freuen uns über Beiträge! Lies [CONTRIBUTING.md](CONTRIBUTING.md) für Details.

Besonders gesucht:
- 🏦 **Bank-Formate**: Wer kennt das CSV-Format seiner Bank und kann einen Parser schreiben?
- 📊 **Steuerberater/Buchhalter**: Fachliche Validierung der Kontierungslogik
- 🔌 **ERP-Nutzer**: JTL-Wawi, Shopify, WooCommerce — wer kann Importdaten bereitstellen?
- 🤖 **LLM-Prompt-Engineering**: Kontierungsprompts optimieren

---

## Lizenz

[MIT](LICENSE) — accounti ist freie Software. Verwende es, verändere es, verkaufe Dienste damit. Gib der Community etwas zurück, wenn du kannst.

---

## Disclaimer

accounti ist ein Werkzeug zur Automatisierung der Vorkontierung und Datenaufbereitung. Es ersetzt **keine steuerliche Beratung** und ist **kein zertifiziertes Buchhaltungsprogramm**. Die erzeugten DATEV-Exporte sollten immer von einem Steuerberater geprüft werden. Verwendung auf eigenes Risiko.

---

<p align="center">
  <sub>Made with ☕ in Hamburg — weil Buchhaltung kein Luxusgut sein sollte.</sub>
</p>
