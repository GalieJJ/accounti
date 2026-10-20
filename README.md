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
| 🟨 | **Belegeingang** | Überwachter Ordner und Upload vorhanden; E-Mail-Weiterleitung, Webhook, Beleg-Connectoren folgen |
| ✅ | **Belegerkennung** | PDF-Textebene, OCR mit lokaler Engine (Tesseract), Belegart per Regelwerk + optionalem LLM, Dublettenerkennung, Rechenprobe |
| ✅ | **Positionssplit** | Eine Rechnung auf mehrere Konten aufteilen; Kreditkartenabrechnung in Einzelumsätze zerlegen |
| ✅ | **E-Rechnung Eingang** | XRechnung (UBL/CII) und ZUGFeRD/Factur-X ohne OCR übernehmen, fachlich validieren (EN-16931-Regeln, § 14 UStG), `accounti rechnung pruefen` |
| ✅ | **E-Rechnung Ausgang** | Rechnungen schreiben und als XRechnung + ZUGFeRD-PDF (PDF/A-3b) ausstellen: lückenlose Nummernkreise, Steuer aus `steuer/` (Inland, Reverse-Charge, ig. Lieferung, Ausfuhr, OSS), formale Prüfung mit KoSIT und Mustang/veraPDF, Versand per E-Mail mit Protokoll |

**Buchen & Zahlen**

| Status | Feature | Beschreibung |
|--------|---------|-------------|
| ✅ | **Bank-Import** | CSV mehrerer Banken, konfigurationsgetriebene Profile mit Auto-Erkennung |
| 🟨 | **Live-Bankanbindung** | Bankkonten mit verschlüsselten Zugängen, Provider-Schnittstelle, Datei-Provider (Ordner mit Kontoauszügen), Dublettenschutz, geplanter Lauf `bank lauf`; FinTS und Kreditkarten folgen |
| ✅ | **Belegabgleich** | Quittungen und sonstige Belege ↔ Kontoumsatz (Referenz → exakt → Vorschlag), bevor kontiert wird; `classify` bucht abgeglichene Umsätze aus dem Beleg mit dessen Vorsteuer |
| ✅ | **KI-Kontierung** | SKR03/SKR04-Zuordnung per Regelwerk + LLM, mit Confidence und Begründung |
| ✅ | **Buchungssätze** | Soll/Haben mit Steuer, Kostenstelle, Belegnummer |
| ✅ | **Kreditoren & Debitoren** | Personenkonten (SKR03/04-Kreise), Stammdaten, Erkennung aus Belegen (IBAN → USt-IdNr. → Name), Neuanlage zur Prüfung, qualifizierte USt-IdNr.-Bestätigung beim BZSt (eVatR-REST-API) mit revisionssicherem Protokoll |
| ✅ | **Offene Posten** | Beleg → Buchung auf Personenkonto + offener Posten, OPOS-Liste, Fälligkeitsstaffel, Zahlungszuordnung (Referenz → exakt → Vorschlag), Teil- und Sammelzahlung, Skonto mit Vorsteuer-/Umsatzsteuerkorrektur |
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
| ✅ | **Aufgaben & Rückfragen** | Aufgaben mit Bezug auf Buchung, Beleg, Umsatz, Kontakt oder Bankkonto; Prüfläufe (unsichere Kontierung, Beleg fehlt, Beleg/Kontakt zur Prüfung, Bankfreigabe) idempotent und mit Selbstabschluss; Zuständigkeit an Person oder Rolle, sonst gemeinsame Liste; Rückfragen am Beleg; gebündelte Tagesübersicht per E-Mail oder Webhook |
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

Legende: ✅ vorhanden · 🟨 teilweise · 🔲 geplant

---

## Quickstart

> ⚠️ **accounti ist in aktiver Entwicklung.** Die folgenden Schritte beschreiben das Zielbild.

### Voraussetzungen

- Python 3.11+
- PostgreSQL 15+
- Ein LLM-Zugang (Anthropic API, OpenAI, oder lokales Modell via Ollama)
- Optional für die formale Prüfung von E-Rechnungen: Java 21 und die Prüfwerkzeuge KoSIT
  (XRechnung) und Mustang/veraPDF (ZUGFeRD, PDF/A-3) — `scripts/pruefwerkzeuge_installieren.sh`,
  feste Versionen mit Prüfsumme. Ohne sie stellt `accounti rechnung ausstellen` nur mit
  ausdrücklichem `--ohne-formale-pruefung` aus.
- Optional für gescannte Belege und Fotos: Tesseract mit deutschen Sprachdaten
  (`apt install tesseract-ocr tesseract-ocr-deu`). Ohne Tesseract landen Scans mit Hinweis in der Prüfung.

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

### Belege und E-Rechnungen

```bash
# Belege aus dem Watch-Ordner holen und lesen (PDF, Scan, XRechnung, ZUGFeRD)
accounti belege abholen --kanal ordner --ordner ./eingang/belege
accounti belege liste --status pruefung

# Eingehende E-Rechnung prüfen, ohne zu importieren — fachlich und mit dem KoSIT-Prüftool
accounti rechnung pruefen ./eingang/rechnung.xml --kosit

# Ausgangsrechnung schreiben und als XRechnung ausstellen (Firmendaten: config/accounti.yaml)
scripts/pruefwerkzeuge_installieren.sh
accounti rechnung neu --name "Kunde GmbH" --plz 10115 --ort Berlin \
  --ust-id DE123456789 --email rechnung@kunde.example
accounti rechnung position <ID> --text "Beratung" --preis 120 --menge 8 --einheit HUR --leistung
accounti rechnung zeigen <ID>
accounti rechnung ausstellen <ID>     # Nummer, XRechnung + ZUGFeRD-PDF, Prüfung → rechnungen/
accounti rechnung senden RE-2026-0001 # per E-Mail (Abschnitt 'versand'), mit Versandprotokoll
```

### Offene Posten

```bash
# Erfasste Rechnungen auf Kreditor/Debitor buchen und offene Posten anlegen
accounti opos verbuchen
accounti kontakte liste --status pruefung     # automatisch angelegte Lieferanten prüfen
accounti kontakte bestaetigen 70000
accounti kontakte bearbeiten 70000 --sachkonto 4930 --zahlungsziel 30
accounti opos liste --richtung eingang --faellig
accounti opos staffel

# Bankzahlungen den Posten zuordnen — vor 'classify', damit nichts doppelt gebucht wird
accounti import bank ./umsaetze.csv
accounti opos zuordnen                         # Eindeutiges wird sofort ausgeglichen
accounti opos vorschlaege                      # Sammel-, Teil-, Skontozahlungen ohne Referenz
accounti opos bestaetigen <ID>                 # oder: accounti opos ablehnen <ID>
accounti bank abgleich                         # Quittungen & Co. ↔ Umsätze
accounti bank vorschlaege                      # mehrdeutig, Rundung, Trinkgeld
accounti bank bestaetigen <ID>                 # oder: accounti bank ablehnen <ID>
accounti classify                              # kontiert aus dem Beleg, sonst Regelwerk/LLM
accounti bank offen                            # Umsätze ohne Beleg, Belege ohne Umsatz
```

### Bankkonten und geplanter Lauf

```bash
accounti bank schluessel                       # Schlüssel für verschlüsselte Bankzugänge
export ACCOUNTI_SCHLUESSEL=…                   # gehört in die Umgebung, nicht ins Projekt
accounti bank verbinde --provider datei --iban DE12… --bezeichnung "Giro" \
  --sachkonto 1200 --feld ordner=./eingang/kontoauszuege
accounti bank konten                           # Konten, Abrufstand, Zustand
accounti bank abrufen                          # neue Umsätze aller Konten, ohne Dubletten
accounti bank lauf                             # abrufen → zuordnen → abgleichen → kontieren (Cron)
```

Auch `accounti import bank` überspringt jetzt Umsätze, die schon da sind; mit `--konto IBAN`
landen sie beim eingerichteten Konto und dessen Sachkonto.

### USt-IdNr.-Prüfung

Steuerfreie innergemeinschaftliche Lieferungen und Reverse Charge gibt es nur mit einer
**qualifizierten Bestätigung des BZSt** (§ 18e UStG). accounti fragt über die eVatR-REST-API an
und hält jede Abfrage mit der Rohantwort in einem Protokoll fest, das nur wachsen kann
(Hash-Kette, unter SQLite zusätzlich per Trigger gesperrt).

```bash
accounti kontakte pruefe-ustid 10001          # qualifiziert: Name, Straße, PLZ, Ort
accounti kontakte pruefe-ustid 10001 --einfach
accounti kontakte ustid-protokoll             # Protokoll + Prüfung auf Unverändertheit
accounti kontakte ustid-protokoll ATU12345678 --csv ustid.csv
```

`accounti rechnung ausstellen` fragt bei Kategorie K oder AE selbst an, wenn keine
Bestätigung aus den letzten 30 Tagen vorliegt (`ustid_pruefung.max_alter_tage`). Ist die
Nummer ungültig oder stimmen Name/Ort nicht, wird die Rechnung nicht ausgestellt, und
`opos verbuchen` legt solche Erlöse zur Prüfung vor.

### Aufgaben und Rückfragen

Alles, was ein Mensch entscheiden muss, steht an einem Ort. Prüfläufe werten vorhandene Daten
aus — eine zweite Ausführung verdoppelt nichts, und eine Aufgabe ohne Anlass schließt sich
selbst als `hinfaellig` (z.B. sobald der fehlende Beleg abgeglichen ist).

```bash
accounti aufgaben pruefen                      # unsichere Kontierung, Beleg fehlt, Beleg/Kontakt zur Prüfung, Bankfreigabe
accounti aufgaben liste                        # offene Aufgaben; unzugewiesen = gemeinsame Liste
accounti aufgaben liste --zustaendig ich       # eigene und die der eigenen Rollen
accounti aufgaben zeige 42                     # mit Bezugsobjekt und Verlauf
accounti aufgaben zuweisen 42 --an jan         # oder --rolle buchhaltung, --frei
accounti aufgaben kommentieren 42 --text "Beim Lieferanten angefragt"
accounti aufgaben erledigen 42 --text "Kontoführungsgebühr, belegfrei"
accounti aufgaben rueckfrage 3fa2c1 --text "Wer war beim Essen dabei?" --an erika
accounti aufgaben objekt beleg 3fa2c1          # Rückfragen, Kommentare, Aufgaben am Beleg
accounti aufgaben erinnern --vorschau          # Tagesübersicht ansehen, nichts senden
accounti aufgaben erinnern                     # je Empfänger eine Übersicht (E-Mail über 'versand')
accounti aufgaben lauf                         # Cron: prüfen + erinnern, z.B. nach 'accounti bank lauf'
```

Erledigt bleibt erledigt: Wer eine Aufgabe mit Begründung schließt, bekommt sie vom nächsten
Prüflauf nicht wieder. „Beleg fehlt“ lässt sich nur mit Begründung (`--text`) erledigen. Erinnerungen kommen am Fälligkeitstag, nach drei und nach sieben Tagen
(einstellbar je Art, die letzte Stufe eskaliert auf Wunsch) — gebündelt, nicht als Einzelmail.

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
   ├─ EU-Land ─┬─ B2B + USt-ID ─▶ 0% (ig. Lieferung / Reverse Charge),
   │            │                  nur mit qualifizierter BZSt-Bestätigung
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
- [x] Belegeingang: Ordner, Upload
- [ ] Belegeingang: E-Mail, Webhook, Connector
- [x] Dublettenerkennung, Eingangsprotokoll
- [x] OCR und Belegartklassifikation, Positionssplit
- [x] Belegarchiv mit Aufbewahrungsfrist
- [x] E-Rechnung lesen: XRechnung (UBL/CII), ZUGFeRD/Factur-X, mit fachlicher Validierung
- [x] E-Rechnung: formale Prüfung gegen XSD/Schematron (KoSIT-Prüftool)
- [x] E-Rechnung schreiben: XRechnung mit lückenlosen Nummernkreisen
- [x] E-Rechnung: ZUGFeRD-PDF (PDF/A-3b) und Versand per E-Mail

### v0.3 — Personenkonten & Bank *(Bausteine 4, 5)*
- [x] Debitoren/Kreditoren-Stammdaten mit Personenkonten und Kontakterkennung
- [x] USt-IdNr.-Prüfung mit Protokoll
- [x] Offene Posten aus Belegen, OPOS-Liste, Fälligkeitsstaffel
- [x] Zahlungszuordnung, Skonto mit Steuerkorrektur, Teil- und Sammelzahlung
- [ ] Live-Bankanbindung: FinTS/HBCI, PSD2 optional, Kreditkarten
- [x] Belegabgleich vor der Kontierung
- [x] Bankkonten, Provider-Schnittstelle, Datei-Provider, Dublettenschutz, geplanter Lauf
- [ ] FinTS-Provider und Kreditkarten (FinTS braucht eine Produktregistrierung)

### v0.4 — Zahlung & Prüfung *(Bausteine 6, 7)*
- [ ] Zahlungsvorschlag nach Skontofrist, SEPA-Sammelüberweisung, Freigabe
- [ ] Mehrstufiges Mahnwesen mit Verzugszinsen
- [ ] Prüfregeln für Vollständigkeit, Richtigkeit, Zeitgerechtheit, Ordnung
- [ ] Belegnachforderung, unveränderbares Journal, Periodenabschluss
- [ ] Generierte Verfahrensdokumentation

### v0.5 — Oberfläche & Betrieb *(Bausteine 8, 10)*
- [x] Aufgaben, Rückfragen am Beleg, Zuständigkeiten, Erinnerungen
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
