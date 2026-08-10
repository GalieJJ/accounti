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
  <a href="docs/bauplan.md">Bauplan</a> ·
  <a href="#roadmap">Roadmap</a> ·
  <a href="CONTRIBUTING.md">Mitmachen</a> ·
  <a href="LICENSE">Lizenz</a>
</p>

---

## Was ist accounti?

**accounti** macht die laufende Buchhaltung kleiner und mittlerer Unternehmen in Deutschland im eigenen Haus möglich — von der Belegerfassung über die Kontierung und den Zahlungsverkehr bis zur Steuermeldung und zum Jahresabschluss.

Belege kommen über E-Mail, Ordner oder als E-Rechnung herein, Kontoumsätze holt accounti selbst von der Bank. Beides wird zusammengeführt, nach SKR03/SKR04 kontiert, zu Buchungssätzen verarbeitet und als BWA ausgewertet. Was unsicher ist, legt dir accounti zur Prüfung vor — den Rest erledigt es.

### Das Problem

- Belege manuell kontieren kostet Stunden pro Woche
- DATEV-Exporte aus ERP-Systemen sind teuer (z.B. JERA ~50€/Monat) oder fehleranfällig
- BWA gibt es erst Wochen später vom Steuerberater
- Bestehende Tools sind Closed Source, teuer, oder für den US-Markt gebaut

### Die Lösung

```
  Belege                          Kontoumsätze
  E-Mail · Ordner · Upload        Bank (FinTS/PSD2) · Kreditkarte
  E-Rechnung · Connector          ERP · Marktplätze
        │                                │
        └──────────────┬─────────────────┘
                       ▼
                 ┌──────────┐
                 │ accounti │  ← Abgleich, KI-Kontierung, Prüfung
                 └──────────┘
                       │
      ┌────────┬───────┼────────┬─────────┐
      ▼        ▼       ▼        ▼         ▼
   Zahlung   OPOS     BWA    Steuer-   DATEV
   Mahnung          Abschluss meldung
```

---

## Features

Was gebaut wird, steht im [Bauplan](docs/bauplan.md) — zwölf Bausteine, jeder mit eigenem Spec.

**Belege & Rechnungen**

| Status | Feature | Beschreibung |
|--------|---------|-------------|
| 🔲 | **Belegeingang** | E-Mail-Weiterleitung, überwachter Ordner, Upload, Webhook, Beleg-Connectoren |
| 🔲 | **Belegerkennung** | OCR mit lokaler Engine als Default, automatische Belegsortierung, Dublettenerkennung |
| 🔲 | **Positionssplit** | Eine Rechnung auf mehrere Konten aufteilen; Kreditkartenabrechnung in Einzelumsätze zerlegen |
| 🔲 | **E-Rechnung Eingang** | XRechnung, ZUGFeRD/Factur-X lesen und validieren — ohne OCR |
| 🔲 | **E-Rechnung Ausgang** | Rechnungen schreiben und als konforme E-Rechnung versenden |

**Buchen & Zahlen**

| Status | Feature | Beschreibung |
|--------|---------|-------------|
| ✅ | **Bank-Import** | CSV mehrerer Banken, konfigurationsgetriebene Profile mit Auto-Erkennung |
| 🔲 | **Live-Bankanbindung** | FinTS/HBCI direkt, PSD2-Aggregator optional, Kreditkarten |
| 🔲 | **Belegabgleich** | Beleg ↔ Kontoumsatz automatisch zusammenführen, bevor kontiert wird |
| ✅ | **KI-Kontierung** | SKR03/SKR04-Zuordnung per Regelwerk + LLM, mit Confidence und Begründung |
| ✅ | **Buchungssätze** | Soll/Haben mit Steuer, Kostenstelle, Belegnummer |
| 🔲 | **Kreditoren & Debitoren** | Personenkonten, Stammdaten, USt-IdNr.-Prüfung mit Protokoll |
| 🔲 | **Offene Posten** | OPOS-Liste, Fälligkeitsstaffel, automatische Zahlungszuordnung, Teilzahlung, Skonto |
| 🔲 | **Zahlungsverkehr** | Zahlungsvorschlag nach Skontofrist, SEPA-Sammelüberweisung, Freigabe-Workflow |
| 🔲 | **Mahnwesen** | Mehrstufig, mit Verzugszinsen und Mahngebühren |
| ✅ | **Lernschleife** | Korrekturen werden zu Regeln — das System fragt mit der Zeit seltener |

**Prüfen & Zusammenarbeiten**

| Status | Feature | Beschreibung |
|--------|---------|-------------|
| 🔲 | **Belegvollständigkeit** | Umsatz ohne Beleg, Beleg ohne Umsatz, Lücken in Nummernkreisen |
| 🔲 | **Ordnungsmäßigkeit** | § 14 UStG-Pflichtangaben, Rechenprobe, Steuerschlüssel ./. Konto, Adressat |
| 🔲 | **Belegnachforderung** | Fehlende Belege werden selbstständig angefordert und erinnert |
| 🔲 | **Unveränderbares Journal** | Hashverkettet, Storno statt Änderung, Verfahrensdokumentation generiert |
| 🔲 | **Aufgaben & Rückfragen** | Kommentare am Beleg statt E-Mail, Zuständigkeiten, Fristen, Erinnerungen |
| 🔲 | **Supervisionsansicht** | Web-UI: Beleg links, Vorschlag rechts, Korrektur in einem Schritt |

**Steuer & Abschluss**

| Status | Feature | Beschreibung |
|--------|---------|-------------|
| ✅ | **Umsatzsteuer** | USt/VSt-Berechnung, Steuerautomatik, Geschäftsvorfall-Bestimmung |
| ✅ | **OSS-Verfahren** | EU-weite MwSt (27 Länder), Schwellenwertprüfung, Quartalsmeldung |
| ✅ | **USt-Voranmeldung** | ELSTER-Kennziffern, Zahllast-Berechnung |
| 🔲 | **Elektronische Übermittlung** | Voranmeldung, Dauerfristverlängerung, Zusammenfassende Meldung — mit Protokoll |
| 🔲 | **Fristenkalender** | Abgabefristen berechnet, inkl. Wochenend- und Feiertagsverschiebung |
| ✅ | **BWA** | Betriebswirtschaftliche Auswertung nach DATEV-Schema |
| 🔲 | **Anlagenbuchhaltung** | AfA linear, GWG, Sammelposten, Anlagenspiegel, Abgänge |
| 🔲 | **Jahresabschluss** | Abgrenzungen, Rückstellungen, Kassenbuch, EÜR oder Bilanz mit GuV, Saldovortrag |

**Anbinden & Übergeben**

| Status | Feature | Beschreibung |
|--------|---------|-------------|
| ✅ | **DATEV-Buchungsstapel** | ASCII-konformer EXTF-Export, gegen echte Dateien geprüft |
| 🔲 | **DATEV vollständig** | Debitoren/Kreditoren-Stammdaten, Belegbilder, Kontoauszüge |
| 🔲 | **Marktplätze & ERP** | JTL-Wawi, Amazon (DE/FR/IT/ES/NL/UK/SE/PL), eBay, Shopify, PayPal — mit Bestimmungsland |
| 🔲 | **Prüfungsdaten** | Datenüberlassung für die Betriebsprüfung |
| 🔲 | **REST-API** | Belege einliefern, Buchungen und OPOS abfragen, Läufe anstoßen |
| 🔲 | **Mehrere Gesellschaften** | Eigene Firmen mit eigenem Wirtschaftsjahr und Kontenrahmen |
| 🔲 | **Benutzer & Rollen** | Anmeldung mit 2FA, Rollen, Vier-Augen-Freigabe, DE/EN |

Legende: ✅ vorhanden · 🔲 geplant

---

## Quickstart

> ⚠️ **accounti ist in aktiver Entwicklung.** Die folgenden Schritte beschreiben das Zielbild.

### Voraussetzungen

- Python 3.11+
- PostgreSQL 15+
- Ein LLM-Zugang (Anthropic API, OpenAI, oder lokales Modell via Ollama)

### Installation

```bash
git clone https://github.com/GalieJJ/accounti.git
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
│   ├── belege/           # Belegeingang, OCR, Positionen, Dubletten, Archiv
│   ├── erechnung/        # XRechnung/ZUGFeRD lesen und erzeugen
│   ├── bank/             # Live-Anbindung (FinTS/PSD2), Belegabgleich
│   ├── klassifikation/   # KI-Engine: LLM + Regelwerk + Lernschleife
│   ├── buchung/          # Buchungssatz-Erzeugung (Soll/Haben/Steuer)
│   ├── kontakte/         # Debitoren/Kreditoren, USt-IdNr.-Prüfung
│   ├── opos/             # Offene Posten, Zahlungszuordnung, Ausgleich
│   ├── zahlung/          # Zahlungsvorschlag, SEPA, Freigabe
│   ├── mahnwesen/        # Mahnstufen, Verzugszinsen
│   ├── pruefung/         # Vollständigkeit, Ordnungsmäßigkeit, Journal
│   ├── aufgaben/         # Aufgaben, Rückfragen, Erinnerungen
│   ├── steuer/           # USt-Berechnung, OSS-Verfahren, EU-Steuersätze
│   ├── elster/           # Elektronische Übermittlung + Protokoll
│   ├── anlagen/          # Anlagegüter, AfA, Anlagenspiegel
│   ├── abschluss/        # Abgrenzung, Kassenbuch, EÜR/Bilanz, Vortrag
│   ├── export/           # DATEV-ASCII, Stammdaten, Belege, CSV, JSON
│   ├── bwa/              # BWA-Berechnung nach DATEV-Schema
│   ├── auth/             # Benutzer, Rollen, 2FA
│   └── api/              # REST-API + Web-UI für Supervision
├── config/               # Kontenrahmen (SKR03/04), Steuerschlüssel, Regeln
├── tests/
├── docs/                 # Bauplan, Architektur, Specs, Pläne
└── examples/             # Beispiel-Imports und Konfigurationen
```

Module ohne Häkchen in der [Feature-Übersicht](#features) sind geplant — der
[Bauplan](docs/bauplan.md) sagt, in welcher Reihenfolge sie entstehen.

### Pipeline

```
┌──────────┐
│  Belege  │──┐
│          │  │   ┌──────────┐    ┌───────────────┐    ┌──────────┐    ┌────────┐
│ E-Mail   │  ├──▶│ Abgleich │───▶│ Klassifikation│───▶│ Buchung  │───▶│ Export │
│ Ordner   │  │   │          │    │               │    │          │    │        │
│ E-Rechn. │  │   │ Beleg ↔  │    │ 1. Regelwerk  │    │ Soll/Hab │    │ DATEV  │
└──────────┘  │   │  Umsatz  │    │ 2. LLM-Match  │    │ MwSt     │    │ CSV    │
              │   └──────────┘    │ 3. Supervisor │    │ KSt      │    │ JSON   │
┌──────────┐  │                   │    Feedback   │    │ BelegNr  │    └────────┘
│  Umsätze │  │                   └───────────────┘    └──────────┘
│          │──┘                          ▲                   │
│ Bank live│                             │                   ▼
│ Bank-CSV │                             │        ┌──────────────────────┐
│ JTL/Amaz.│                             │        │  OPOS · Zahlung      │
└──────────┘                             │        │  Mahnwesen · Prüfung │
                                         │        │  BWA · Steuermeldung │
                                         │        │  Abschluss           │
                                         │        └──────────┬───────────┘
                                         │                   │
                                         └── Lernschleife ───┘
                                            (Korrekturen → Regeln)
```

Der **Abgleich vor der Klassifikation** ist Absicht: Eine Transaktion, deren Beleg bekannt ist,
kennt Positionen, Steuersätze und Lieferant — die Kontierung muss dann nichts mehr aus einem
Verwendungszweck erraten.

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

Die Roadmap folgt den zwölf Bausteinen aus dem [Bauplan](docs/bauplan.md). Jeder Baustein hat ein
eigenes Spec unter [`docs/specs/`](docs/specs/) und ist für sich nützlich — wer nur Bankauszüge
kontieren will, braucht nur v0.1.

### v0.1 — Fundament ✅
- [x] Datenmodell + Persistenz (SQLite, Postgres-ready)
- [x] SKR03 als YAML-Konfiguration
- [x] Bank-CSV-Import über konfigurierbare Profile mit Auto-Erkennung
- [x] Regelwerk-Engine + LLM-Kontierung mit Confidence
- [x] Supervisor-Loop: prüfen, korrigieren, freigeben — Korrektur wird zur Regel
- [x] Umsatzsteuer, OSS-Verfahren, USt-Voranmeldung (Kennziffern)
- [x] DATEV-ASCII-Export (Buchungsstapel), BWA-Berechnung
- [x] CLI-Interface
- [ ] SKR04 als YAML-Konfiguration

### v0.2 — Beleg & E-Rechnung *(Bausteine 2, 3)*
- [ ] Belegeingang: Ordner, E-Mail, Upload, Webhook, Connector
- [ ] OCR und Belegartklassifikation, Positionssplit, Dublettenerkennung
- [ ] Belegarchiv mit Aufbewahrungsfrist
- [ ] E-Rechnung lesen: XRechnung (UBL/CII), ZUGFeRD/Factur-X, mit Validierung
- [ ] E-Rechnung schreiben und versenden

### v0.3 — Personenkonten & Bank *(Bausteine 4, 5)*
- [ ] Debitoren/Kreditoren-Stammdaten, USt-IdNr.-Prüfung mit Protokoll
- [ ] Offene Posten, Fälligkeitsstaffel, Zahlungszuordnung, Skonto, Teilzahlung
- [ ] Live-Bankanbindung: FinTS/HBCI, PSD2 optional, Kreditkarten
- [ ] Belegabgleich vor der Kontierung, geplanter Abruf

### v0.4 — Zahlung & Prüfung *(Bausteine 6, 7)*
- [ ] Zahlungsvorschlag nach Skontofrist, SEPA-Sammelüberweisung, Freigabe
- [ ] Mehrstufiges Mahnwesen mit Verzugszinsen
- [ ] Prüfregeln für Vollständigkeit, Richtigkeit, Zeitgerechtheit, Ordnung
- [ ] Belegnachforderung, unveränderbares Journal, Periodenabschluss
- [ ] Generierte Verfahrensdokumentation

### v0.5 — Oberfläche & Betrieb *(Bausteine 8, 10)*
- [ ] Aufgaben, Rückfragen am Beleg, Zuständigkeiten, Erinnerungen
- [ ] Web-UI: Supervisions-Queue mit Belegansicht, BWA mit Vorjahresvergleich
- [ ] Benutzer, Rollen, 2FA, Vier-Augen-Freigabe, DE/EN
- [ ] Docker-Setup, verschlüsselte Sicherungen, Löschkonzept

### v0.6 — Integrationen *(Baustein 11)*
- [ ] JTL-Wawi, Amazon (DE/FR/IT/ES/NL/UK/SE/PL), eBay, Shopify, PayPal
- [ ] Bestimmungsland-Erkennung für OSS
- [ ] DATEV vollständig: Stammdaten, Belegbilder, Kontoauszüge
- [ ] REST-API, Prüfungsdatenüberlassung
- [ ] MT940/CAMT-Import

### v1.0 — Meldungen & Abschluss *(Bausteine 9, 12)*
- [ ] Elektronische Übermittlung: Voranmeldung, Dauerfristverlängerung, ZM
- [ ] Plausibilisierung vor Abgabe, Übermittlungsprotokolle, Fristenkalender
- [ ] Anlagenbuchhaltung: AfA, GWG, Sammelposten, Anlagenspiegel
- [ ] Abgrenzungen, Rückstellungen, Kassenbuch
- [ ] Jahresabschluss: EÜR oder Bilanz mit GuV, Saldovortrag
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
- 📊 **Steuerberater/Buchhalter**: Fachliche Validierung der Kontierungslogik und der Prüfregeln
- 🧾 **E-Rechnung**: Anonymisierte XRechnungen und ZUGFeRD-Dateien für die Format-Fixtures
- 🔌 **ERP-Nutzer**: JTL-Wawi, Shopify, WooCommerce — wer kann Importdaten bereitstellen?
- 🤖 **LLM-Prompt-Engineering**: Kontierungsprompts optimieren

---

## Lizenz

[MIT](LICENSE) — accounti ist freie Software. Verwende es, verändere es, verkaufe Dienste damit. Gib der Community etwas zurück, wenn du kannst.

---

## Disclaimer

accounti ist ein Werkzeug zur Buchführung und Datenaufbereitung, kein Berater. Es leistet **keine steuerliche Beratung** und ist **kein zertifiziertes Buchhaltungsprogramm**. Wer es einsetzt, trägt die fachliche Verantwortung für die eigene Buchführung und für alles, was daraus an Meldungen entsteht — accounti rechnet und meldet, die Erklärung gibt ein Mensch ab.

accounti ist für die **eigene** Buchhaltung gebaut. Die geschäftsmäßige Hilfeleistung in Steuersachen für Dritte ist in Deutschland reglementiert; wer accounti für fremde Unternehmen einsetzen will, muss selbst klären, ob er das darf. Verwendung auf eigenes Risiko.

---

<p align="center">
  <sub>Made with ☕ in Hamburg — weil Buchhaltung kein Luxusgut sein sollte.</sub>
</p>
