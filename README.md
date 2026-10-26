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
| ✅ | **Belegeingang** | Überwachter Ordner, Upload, IMAP-Postfach (Anhänge, Absender als Hinweis, verarbeitete Nachrichten gemerkt), tokengeschützter Webhook für Fremdsysteme und Messenger-Weiterleitungen, Connectoren für Belegportale (generisch per JSON/HTTP-Konfiguration); Typ- und Größenprüfung am Inhalt, Dublettenschutz über alle Kanäle |
| ✅ | **Belegerkennung** | PDF-Textebene, OCR mit lokaler Engine (Tesseract), Belegart per Regelwerk + optionalem LLM, Dublettenerkennung, Rechenprobe |
| ✅ | **Positionssplit** | Eine Rechnung auf mehrere Konten aufteilen; Kreditkartenabrechnung in Einzelumsätze zerlegen |
| ✅ | **E-Rechnung Eingang** | XRechnung (UBL/CII) und ZUGFeRD/Factur-X ohne OCR übernehmen, fachlich validieren (EN-16931-Regeln, § 14 UStG), `accounti rechnung pruefen` |
| ✅ | **E-Rechnung Ausgang** | Rechnungen schreiben und als XRechnung + ZUGFeRD-PDF (PDF/A-3b) ausstellen: lückenlose Nummernkreise, Steuer aus `steuer/` (Inland, Reverse-Charge, ig. Lieferung, Ausfuhr, OSS), formale Prüfung mit KoSIT und Mustang/veraPDF, Versand per E-Mail mit Protokoll |

**Buchen & Zahlen**

| Status | Feature | Beschreibung |
|--------|---------|-------------|
| ✅ | **Bank-Import** | CSV mehrerer Banken, konfigurationsgetriebene Profile mit Auto-Erkennung |
| ✅ | **Live-Bankanbindung** | Bankkonten mit verschlüsselten Zugängen, FinTS-Direktabruf (python-fints, eigene Produkt-ID, TAN/App-Freigabe als Zustand oder interaktiv), Datei-Provider, MT940 und CAMT (camt.052/053/054) mit Bankreferenz im Dublettenschutz, Kreditkarten als eigene Konten mit Abgleich der Sammelbelastung, geplanter Lauf `bank lauf`; PSD2 folgt |
| ✅ | **Belegabgleich** | Quittungen und sonstige Belege ↔ Kontoumsatz (Referenz → exakt → Vorschlag), bevor kontiert wird; `classify` bucht abgeglichene Umsätze aus dem Beleg mit dessen Vorsteuer |
| ✅ | **KI-Kontierung** | SKR03/SKR04-Zuordnung per Regelwerk + LLM, mit Confidence und Begründung |
| ✅ | **Buchungssätze** | Soll/Haben mit Steuer, Kostenstelle, Belegnummer |
| ✅ | **Kreditoren & Debitoren** | Personenkonten (SKR03/04-Kreise), Stammdaten, Erkennung aus Belegen (IBAN → USt-IdNr. → Name), Neuanlage zur Prüfung, qualifizierte USt-IdNr.-Bestätigung beim BZSt (eVatR-REST-API) mit revisionssicherem Protokoll |
| ✅ | **Offene Posten** | Beleg → Buchung auf Personenkonto + offener Posten, OPOS-Liste, Fälligkeitsstaffel, Zahlungszuordnung (Referenz → exakt → Vorschlag), Teil- und Sammelzahlung, Skonto mit Vorsteuer-/Umsatzsteuerkorrektur |
| ✅ | **Zahlungsverkehr** | Zahlungsvorschlag mit Skonto zuerst und Grund je Position, Zahlungslauf mit blockierender Prüfung (IBAN ≠ Stammsatz oder Rechnung stoppt), Freigabe (optional Vier-Augen) und Storno mit Protokoll, SEPA-Sammelüberweisung `pain.001.001.09` (DK GBIC_5) als Datei |
| ✅ | **Mahnwesen** | Konfigurierbare Stufen, Verzugszinsen nach § 288 BGB mit datiertem Basiszinssatz, 40-€-Pauschale im B2B, Mahnschreiben als PDF/Text/E-Mail, Mahnstufe am offenen Posten |
| ✅ | **Lernschleife** | Korrekturen werden zu Regeln — das System fragt mit der Zeit seltener |

**Prüfen & Zusammenarbeiten**

| Status | Feature | Beschreibung |
|--------|---------|-------------|
| ✅ | **Belegvollständigkeit** | Prüfregeln mit Schweregrad und Schwellen aus der Konfiguration: Umsatz ohne Beleg (mit Betrag, Datum, Gegenpartei), Rechnung ohne Zahlung nach Zahlungsziel, Lücken in Nummernkreisen und Kontoauszügen; begründet belegfreie Umsätze per Muster |
| ✅ | **Ordnungsmäßigkeit** | Pflichtangaben nach § 14 Abs. 4 UStG aus dem Original (Kleinbetragsrechnung § 33 UStDV bis 250 €), Rechenprobe, Steuerschlüssel ./. Sachkonto (DATEV-Automatikkonten), Steuersatz zum Land, Adressat, Vorsteuer aus ig. Erwerb ohne USt-IdNr., Dubletten, Zeitgerechtheit, Festschreibung — `accounti pruefen` |
| ✅ | **Belegnachforderung** | Fehlende Belege werden Aufgaben mit Umsatz, Betrag und Gegenpartei, erinnern und verstummen, sobald der Beleg abgeglichen ist; Anfrage an den Lieferanten als Entwurf, gesendet nur auf Befehl |
| ✅ | **Unveränderbares Journal** | Jede Buchung, Freigabe, Korrektur, jedes Storno, jeder Export, Beleg und Zahlungslauf hash-verkettet im Journal (`journal pruefen` findet Manipulationen, auch am Bestand vorbei); freigegebene Buchungen nur per Storno mit Neubuchung; Monate festschreiben; mit Benutzern nur mit Rolle und Einmalcode, im Journal steht der Benutzer; Verfahrensdokumentation aus dem eingerichteten System |
| ✅ | **Aufgaben & Rückfragen** | Aufgaben mit Bezug auf Buchung, Beleg, Umsatz, Kontakt oder Bankkonto; Prüfläufe (unsichere Kontierung, Beleg fehlt, Beleg/Kontakt zur Prüfung, Bankfreigabe) idempotent und mit Selbstabschluss; Zuständigkeit an Person oder Rolle, sonst gemeinsame Liste; Rückfragen am Beleg; gebündelte Tagesübersicht per E-Mail oder Webhook |
| 🔲 | **Supervisionsansicht** | Web-UI: Beleg links, Vorschlag rechts, Korrektur in einem Schritt |

**Steuer & Abschluss**

| Status | Feature | Beschreibung |
|--------|---------|-------------|
| ✅ | **Umsatzsteuer** | USt/VSt-Berechnung, Steuerautomatik, Geschäftsvorfall-Bestimmung |
| ✅ | **OSS-Verfahren** | EU-weite MwSt (27 Länder), Schwellenwertprüfung, Quartalsmeldung |
| ✅ | **USt-Voranmeldung** | Kennziffern nach Vordruck 2026 aus den Buchungen (Steuerschlüssel + Automatikkonten), volle Euro wie ELSTER, Plausibilisierung (ohne Steuerschlüssel, unbestätigte USt-IdNr., Verprobung, Vormonatsvergleich), Freigabe durch den Menschen |
| 🟨 | **Elektronische Übermittlung** | ELSTER-Datensatz UStVA/Dauerfristverlängerung, Testmodus ohne Abgabe, ERiC-Anbindung über ctypes (mit eigener Hersteller-ID und Zertifikat), unveränderbares Protokoll, Zahllast als offener Posten beim Finanzamt; Zusammenfassende Meldung als Portaldatei |
| ✅ | **Fristenkalender** | UStVA, Dauerfristverlängerung, Sondervorauszahlung, ZM, OSS — verschoben nach § 108 Abs. 3 AO mit Feiertagen des Bundeslands |
| ✅ | **BWA** | Betriebswirtschaftliche Auswertung nach DATEV-Schema |
| ✅ | **Anlagenbuchhaltung** | Anlagegüter mit AfA linear (monatsgenau), degressiv (2020–2022, 2024, 07/2025–2027 mit Wechsel zur linearen AfA), GWG, Sammelposten, digitale Wirtschaftsgüter, E-Fahrzeuge — Grenzbeträge mit Gültigkeitszeitraum, AfA-Tabelle, AfA-Lauf je Monat oder Jahr, Abgang mit Ergebnis, Anlagenspiegel |
| 🟨 | **Jahresabschluss** | Kassenbuch ohne negativen Bestand, Bank-Saldenabstimmung als Abschlusssperre, Abschlussprüfungen, Summen- und Saldenliste, ARAP/PRAP-Vorschläge mit Auflösung, Einnahmenüberschussrechnung nach Anlage EÜR 2025/2026, Saldovortrag mit Jahressperre; Bilanz/GuV, Rückstellungen und Übermittlung folgen |

**Anbinden & Übergeben**

| Status | Feature | Beschreibung |
|--------|---------|-------------|
| ✅ | **DATEV-Buchungsstapel** | ASCII-konformer EXTF-Export, gegen echte Dateien geprüft |
| ✅ | **DATEV vollständig** | Debitoren/Kreditoren (EXTF, Golden-Test), Belegpaket mit `document.xml` und Buchungsstapel mit Beleglink — Belege hängen beim Empfänger am Buchungssatz —, Kontoauszüge lückenlos nummeriert als MT940 mit Saldenverlauf |
| 🟨 | **Marktplätze & ERP** | Amazon (Abrechnungsbericht V2), eBay, Shopify, PayPal (als eigenes Konto) — Erlöse, Gebühren, Erstattungen, Einbehalte einzeln gebucht, Summenprobe, Auszahlungsabgleich, Bestimmungsland → OSS; JTL-Wawi folgt |
| 🔲 | **Prüfungsdaten** | Datenüberlassung für die Betriebsprüfung |
| ✅ | **REST-API** | `/api/v1` mit API-Token und Rechten (`opos:lesen`, `buchungen:lesen`, `belege:schreiben`, `laeufe:starten`): offene Posten und Buchungen abfragen, Belege einliefern (Pipeline wie der Webhook), `bank lauf` und `aufgaben lauf` anstoßen; Token nur als Hash gespeichert, ohne Recht 403 |
| ✅ | **Mehrere Gesellschaften** | Je eigene Gesellschaft eine Datenbank, ein Belegarchiv und eine Konfiguration (Kontenrahmen, Wirtschaftsjahr, Nummernkreise, Bankkonten); `accounti --gesellschaft K …` für alle Befehle, Wechsel im Browser |
| 🟨 | **Benutzer & Rollen** | Anmeldung mit Passwort (scrypt) und zweitem Faktor (TOTP, Wiederherstellungscodes), Sperre nach Fehlversuchen (Browser und Server-Shell getrennt gezählt), Rollen betrachter/buchhalter/freigeber/verwalter je Gesellschaft, Freigaben nur mit Rolle und Einmalcode (Browser und CLI) — auch Buchungsfreigabe, Korrektur, Storno und Festschreibung —, Vier-Augen-Freigabe; DE/EN folgt |
| ✅ | **Betrieb** | `docker compose up` mit PostgreSQL und geplantem Lauf, Geheimnisse nur aus der Umgebung, verschlüsselte Sicherung von Datenbank und Belegarchiv mit Wiederherstellung, Aufbewahrungsfristen nach § 147 AO, Protokoll ohne Personenbezug — [Betrieb](docs/betrieb.md) |

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

# Ersten Benutzer (Verwalter) anlegen und zweiten Faktor einrichten
accounti bank schluessel            # die ausgegebene Zeile „export ACCOUNTI_SCHLUESSEL=…“ ausführen
accounti benutzer anlegen chef --rolle verwalter --rolle freigeber
accounti benutzer 2fa chef

# Web-Oberfläche und REST-API (TLS über einen Reverse-Proxy, siehe docs/betrieb.md)
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
# Original geprüft: freigeben (Rechnung ohne Steuerausweis mit ihrem Steuerfall)
accounti belege freigeben 3fa2c1 --steuer 13b --grund "Hinweis § 13b UStG auf Seite 2"
accounti belege freigeben 7c41d0 --vorzeichen umkehren --grund "Rechnung, keine Korrektur"
accounti belege erkennen --id 3fa2c1           # erfasst, aber falsch gelesen: neu lesen

# Belege aus dem Postfach holen (Abschnitt belegkanaele.email; Passwort per ${VAR} oder Tresor)
accounti kanaele zugang email rechnungen         # Passwort verschlüsselt ablegen (ACCOUNTI_SCHLUESSEL)
accounti belege abholen --kanal email            # alle Postfächer, oder --quelle rechnungen
accounti kanaele nachrichten --kanal email       # verarbeitete Nachrichten mit Absender

# Webhook für Fremdsysteme und Messenger-Weiterleitungen (n8n, Make, Zapier, curl)
accounti kanaele webhook token n8n               # Token wird nur jetzt angezeigt
accounti kanaele webhook starten                 # 127.0.0.1:8410 — TLS über einen Reverse-Proxy
curl -H "Authorization: Bearer $TOKEN" -F datei=@rechnung.pdf -F absender="Telegram Erika" \
  http://127.0.0.1:8410/belege

# Belegportal über seine API (Abschnitt belegkanaele.connectoren)
accounti kanaele connectoren                     # Typen und Prüfung der Konfiguration
accounti kanaele zugang connector getmyinvoices  # API-Schlüssel verschlüsselt ablegen
accounti belege abholen --kanal connector

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
accounti kontakte bearbeiten 70001 --land AT --plz 5020 --ort Salzburg
accounti opos liste --richtung eingang --faellig
accounti opos staffel

# Bankzahlungen den Posten zuordnen — vor 'classify', damit nichts doppelt gebucht wird
accounti import bank ./umsaetze.csv
accounti opos zuordnen                         # Eindeutiges wird sofort ausgeglichen
accounti opos vorschlaege                      # Sammel-, Teil-, Skontozahlungen ohne Referenz
accounti opos bestaetigen <ID>                 # oder: accounti opos ablehnen <ID>
accounti opos bestaetigen <ID> --skonto RW-8890=53,55   # Skonto auf diesen Posten anerkennen
accounti bank abgleich                         # Quittungen & Co. ↔ Umsätze
accounti bank vorschlaege                      # mehrdeutig, Rundung, Trinkgeld
accounti bank bestaetigen <ID>                 # oder: accounti bank ablehnen <ID>
accounti classify                              # kontiert aus dem Beleg, sonst Regelwerk/LLM
accounti bank offen                            # Umsätze ohne Beleg, Belege ohne Umsatz
```

Eine Rechnung ohne Umsatzsteuer erkennt accounti am Hinweistext statt am Steuerausweis
(§ 13b „Steuerschuldnerschaft des Leistungsempfängers“, ig. Lieferung, § 19, § 4 UStG).
`opos verbuchen` schlägt bei § 13b Schlüssel 94 und bei einer ig. Lieferung an uns
Schlüssel 19 vor — immer zur Prüfung; die Steuer berechnet accounti aus dem Netto, Kz 46/47
gilt für Kreditoren aus dem übrigen EU-Gebiet (Land aus USt-IdNr. oder IBAN, sonst
`kontakte bearbeiten --land`). Gutschriften des Lieferanten mindern Aufwand und Vorsteuer
im Zeitraum ihres Belegdatums (§ 17 Abs. 1 S. 8 UStG); einen Korrekturbeleg mit positiven
Beträgen (Titel „Rechnungskorrektur“, „Gutschrift“, „Stornorechnung“, „Credit Note“)
negiert accounti und legt ihn zur Prüfung — ist es doch eine Rechnung: `belege freigeben
… --vorzeichen umkehren`. Kommt eine Rechnung bei Bilanzierung erst im Folgejahr an,
steht die Vorsteuer zunächst auf „Vorsteuer im Folgejahr abziehbar“ (SKR03 1548, SKR04
1434) und wird im Eingangsmonat umgebucht (§ 15 Abs. 1 Nr. 1 UStG). Als Eingang gilt die
Erfassung in accounti.

### Zahlungsverkehr

```bash
accounti zahlung vorschlag --stichtag 2026-10-21      # Skonto zuerst, Grund je Position
accounti zahlung anlegen --stichtag 2026-10-21        # Entwurf = Lauf 1
accounti zahlung entfernen 1 3                         # Position 3 nicht zahlen (nur im Entwurf)
accounti zahlung pruefen 1                             # blockierend: IBAN, Betrag, Sperre, Dubletten
accounti zahlung freigeben 1                           # mit zahlung.vier_augen: zweite Person (eigene Anmeldung)
accounti zahlung sepa 1 --datei ueberweisung.xml      # pain.001.001.09 → im Onlinebanking hochladen
accounti opos zuordnen                                 # Kontoumsätze gleichen die Posten aus
accounti zahlung abgleichen                            # Lauf → ausgeführt
accounti zahlung stornieren 1 --grund "doppelt"       # freigegebene Läufe: nur Storno, mit Protokoll
accounti zahlung sperre 70003 --grund "Reklamation"   # Kreditor vom Zahlungsverkehr ausnehmen
```

Weicht die IBAN der Rechnung vom Stammsatz ab, stoppt der Lauf — so funktionieren gefälschte
Rechnungen. Überweisungen gehen nur an Empfänger im EWR (für die Schweiz oder das Vereinigte
Königreich verlangt SEPA den BIC). Mit `zahlung.vier_augen` gibt frei, wer am Rechner angemeldet
ist — das ist so stark wie diese Anmeldung, nicht mehr. Nach einem Rückruf beim Lieferanten auf bekanntem Weg: Stammsatz ändern
(`accounti kontakte bearbeiten 70003 --iban …`) oder mit `accounti zahlung iban-klaeren 1 2
--grund "…"` festhalten, dass an die Stammsatz-IBAN gezahlt wird.

### Mahnwesen

```bash
accounti mahnwesen lauf --stichtag 2026-10-21          # Mahnentwürfe mit Zinsen, Pauschale, Gebühren
accounti mahnwesen zeigen 7                            # Mahnschreiben als Text
accounti mahnwesen versenden 7 --pdf mahnung-7.pdf     # oder --text, --email; Mahnstufe am Posten +1
accounti mahnwesen versenden 8 --text m.txt --am 2026-10-20   # Brief ging gestern zur Post
accounti mahnwesen kunde 10001 --unternehmer           # B2B: 9 Prozentpunkte + 40 € Pauschale
accounti mahnwesen sperre 10002 --grund "Ratenzahlung" # Kunde vom Mahnlauf ausnehmen
accounti mahnwesen basiszins                           # Basiszinssätze mit Gültigkeitszeitraum
accounti mahnwesen historie 10001                      # versendete Mahnungen eines Kunden
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

### FinTS und Kreditkarten

FinTS ist ein Zusatzpaket: `pip install "accounti[fints]"` (bzw. `pip install -e ".[fints]"` im
Quellordner).

FinTS braucht eine **Produkt-ID**, die jede Installation selbst bei der Deutschen Kreditwirtschaft
registriert (https://www.fints.org/de/hersteller/produktregistrierung, 10–15 Werktage). Sie gehört
in die Umgebung oder in `config/accounti.yaml`, nie ins Repo.

```bash
export ACCOUNTI_FINTS_PRODUKT_ID=…             # oder bank.fints.produkt_id
accounti fints einrichten --iban DE12… --bezeichnung "Giro Sparkasse" \
  --blz 12345678 --server https://fints.example-bank.de/fints30
                                               # Benutzerkennung, PIN, TAN-Verfahren, erste Freigabe
accounti bank abrufen                          # danach ohne Eingabe (Cron); verlangt die Bank
                                               # wieder eine Freigabe, steht das Konto auf
                                               # freigabe_noetig:
accounti fints freigeben                       # TAN eingeben oder in der App bestätigen
accounti fints zugang --konto DE12…            # neue PIN: der Cron versucht es nach einer
                                               # Ablehnung nicht weiter (Sperrgefahr)
accounti fints format --konto DE12… camt       # Format nur ausdrücklich wechseln

accounti import bank auszug.sta                # MT940 und CAMT werden am Inhalt erkannt
accounti import bank camt053.xml --konto DE12…

accounti kreditkarte einrichten --kennung VISA1234 --bezeichnung "Visa Firma" \
  --sachkonto 1730 --girokonto DE12… --endziffern 1234
                                               # eigenes Sachkonto der Karte (SKR03 1730 /
                                               # SKR04 3610 „Kreditkartenabrechnung“, mit der
                                               # Steuerberatung abstimmen), keine Kartennummer
accounti kreditkarte einrichten --konto AMEX01 --girokonto DE12… --abrechnungstag 20
                                               # Karte mit Abruf (z.B. Datei-Provider): Ausgleich
                                               # über Geldtransit 1360/1460
accounti belege import abrechnung-maerz.pdf    # PDF-Abrechnung wird in Umsätze zerlegt …
accounti kreditkarte uebernehmen <BELEG-ID>    # … und landet am Kartenkonto
accounti kreditkarte abgleich                  # Sammelbelastung ./. Summe der Einzelumsätze
accounti kreditkarte liste                     # Karten, Abrechnungen, Befunde
accounti kreditkarte loesen <ABRECHNUNG>       # falsche vorläufige Zuordnung lösen
accounti kreditkarte loesen <ABRECHNUNG> --belastung <UMSATZ>
                                               # „mehrdeutig“: diese Belastung gehört nicht
                                               # zu dieser Abrechnung
```

Stimmt die Sammelbelastung auf dem Girokonto nicht centgenau mit der Summe der Einzelumsätze
überein, bucht accounti sie zur Prüfung und nennt die Differenz als Befund — es gibt keinen
Rundungsposten. Diese Zuordnung bleibt vorläufig: Kommt später die centgenaue Belastung, löst
accounti sie selbst. Passen mehrere Belastungen ungefähr (etwa eine Jahresgebühr und die
Abrechnung), ordnet accounti nichts zu und meldet „mehrdeutig“ mit dem Befehl, der eine davon
abtrennt. `accounti bank lauf` erledigt den Kartenabgleich vor dem Kontieren und
nennt sein Ergebnis; ist genau eine Karte mit PDF-Abrechnung eingerichtet, übernimmt er erfasste
Abrechnungen auch von selbst — nicht aber Abrechnungen, deren Sammelbelastung schon anders
gebucht ist (sonst stünde der Aufwand doppelt da). Die Einzelumsätze kontiert `classify` gegen
das Sachkonto der Karte.

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

### Umsatzsteuer-Voranmeldung und ELSTER

```bash
accounti ustva --period 2026-08                 # Kennziffern (Vordruck 2026) + Plausibilisierung
accounti ustva pruefen --period 2026-08         # nur die Befunde; Fehler sperren die Freigabe
accounti ustva freigeben --period 2026-08 --von "Erika Muster"
accounti ustva uebermitteln --period 2026-08 --test --ausgabe ustva.xml   # prüfen, nichts geht raus
accounti ustva uebermitteln --period 2026-08    # abgeben (ERiC), Protokoll, Zahllast als offener Posten
accounti ustva dauerfrist --jahr 2027           # Dauerfristverlängerung + Sondervorauszahlung (1/11)
accounti zm --period 2026-Q3 --csv zm.csv       # Zusammenfassende Meldung für den Portal-Import
accounti fristen --jahr 2026 --bundesland BY    # Fristenkalender mit Wochenend- und Feiertagsverschiebung
accounti elster pin                             # Zertifikats-PIN verschlüsselt ablegen
accounti elster protokoll                       # Übermittlungsprotokoll + Prüfung auf Unverändertheit
accounti elster zahllast                        # fehlende Zahllast-Buchungen zu Abgaben nachholen
```

Abgegeben wird nur, was ein Mensch freigegeben hat — die Freigabe hängt an den Formularwerten;
ändern sich danach Buchungen, passt sie nicht mehr, und ein neuer Fehler-Befund sperrt die Abgabe
auch mit Freigabe. Der erste Lauf eines Betriebs ist immer der Testmodus: Ohne erfolgreichen
Prüflauf über ERiC wird nur geprüft, erst der nächste Aufruf gibt ab. Ohne ERiC (Registrierung beim
Bayerischen Landesamt für Steuern, eigene Hersteller-ID, Zertifikat) bleibt der Testmodus: Der
Datensatz wird erzeugt und geprüft, aber nicht abgegeben; die Attrappe (`elster.uebermittler:
attrappe`) prüft und testet nur, sie gibt nie ab.

### Marktplätze und DATEV-Übergabe

```bash
accounti marktplatz import amazon ./abrechnung.txt --laender ./ust_transaktionen.csv
accounti marktplatz import paypal ./aktivitaeten.csv     # PayPal ist ein eigenes Konto (1210)
accounti marktplatz import shopify ./auszahlung.csv --laender ./bestellungen.csv
accounti marktplatz liste                                # Status und Befunde je Abrechnung
accounti marktplatz abgleichen                           # Auszahlungen ↔ Bankumsätze
accounti marktplatz oss --quartal 2026-Q3                # OSS-Quartalsmeldung

accounti datev stammdaten --ausgabe ./export             # Debitoren/Kreditoren
accounti datev belege --period 2026-08 --ausgabe ./export/belege-08.zip
accounti datev kontoauszuege --period 2026-08 --anfangssaldo 1.234,56   # erstes Mal
accounti datev kontoauszuege --period 2026-09 --kontrollsaldo 2.345,67
```

Jede Abrechnung wird als Beleg archiviert und Bestandteil für Bestandteil gegen ein
Verrechnungskonto gebucht; die Auszahlung ist nur der Abgleichspunkt gegen die Bank. Stimmt die
Summe der Posten nicht mit der Auszahlung, ist das ein Befund — nichts wird geglättet. Ein
weiterer Bericht zu einer bekannten Abrechnung (Monatsberichte, erneuter Export) bucht nur die
Posten nach, die noch fehlen; bringt er eine zweite Auszahlungszeile, wird nichts nachgetragen.
Eine PayPal-Rückzahlung mindert den Erlös nur, wenn ihre Zahlung ein Checkout-Verkauf war.
Als Länderdatei für Amazon den USt-Transaktionsbericht nehmen: Nur
er kennt das Abgangsland (FBA-Lager) und die USt-IdNr. des Käufers; mit dem Bestellbericht gehen
FBA-Verkäufe zur Prüfung, bis `lager_nur_inland` eingestellt ist. Fremdwährung braucht `--kurs`.
`datev belege` schreibt Belegpaket (für DATEV Belegtransfer, nicht entpacken) und Buchungsstapel
mit Beleglink; beide zusammen importieren. Kontoauszüge werden beim Erstellen festgeschrieben.

### Anlagen und Jahresabschluss

```bash
# Anlagegut aus einem Beleg anlegen — Nutzungsdauer aus der AfA-Tabelle, immer änderbar
accounti anlagen tabelle                       # hinterlegte Nutzungsdauern mit Fundstelle
accounti anlagen anlegen --beleg RE-4711 --typ notebook
accounti anlagen anlegen --bezeichnung "Transporter" --datum 2026-09-15 \
  --kosten 36000 --typ lkw --art degressiv     # 3-fach, höchstens 30 % (07/2025–2027)
accounti anlagen plan 1                        # AfA-Plan bis zum Ende
accounti anlagen afa --jahr 2026 --bis-monat 9 # monatlich oder am Jahresende — idempotent
accounti anlagen freigeben --jahr 2026         # AfA-Vorschläge freigeben
accounti anlagen abgang 1 --datum 2026-11-30 --erloes 500 --gegenkonto 1200
accounti anlagen spiegel --jahr 2026 --csv anlagenspiegel.csv

# Kassenbuch — ein Eintrag, der den Bestand negativ machen würde, wird abgelehnt
accounti kasse anfangsbestand --betrag 300 --datum 2026-01-01
accounti kasse buchen --betrag -24.90 --text "Porto" --konto 4910
accounti kasse liste --jahr 2026               # laufende Nummer, Tagessaldo, Bestand
accounti kasse bestand --gezaehlt 275.10       # Kassensturz

# Jahresabschluss
accounti abschluss eroeffnung --jahr 2026 --konto 1200 --saldo 5000   # nur im ersten Jahr
accounti abschluss saldo --konto DE12… --stichtag 2026-12-31 --saldo 12345,67
accounti abschluss buchen --jahr 2026          # AfA + Abgrenzungsvorschläge
accounti abschluss abgrenzungen --jahr 2026    # bestaetigen <Nr> | ablehnen <Nr>
accounti abschluss abgrenzen 3f2a9c1e --von 2026-11-01 --bis 2027-10-31   # Zeitraum nicht im Text
accounti abschluss pruefen --jahr 2026         # Fehler blockieren den Vortrag
accounti abschluss susa --jahr 2026
accounti abschluss euer --jahr 2026            # Anlage EÜR nach Zeilen und Kennzahlen
accounti abschluss vortrag --jahr 2026 --von "E. Muster"   # EB 01.01.2027, 2026 gesperrt
accounti abschluss oeffnen --jahr 2026 --grund "Nachbuchung Beleg 4711" --von "E. Muster"
```

Grenzbeträge (GWG, Sammelposten, degressive Fenster) gelten **ab dem Anschaffungstag** — ein Zugang
aus 2015 rechnet mit 410 €, einer aus 2026 mit 800 €. Abschlussbuchungen sind immer Vorschläge zur
Freigabe; gezählt wird in Salden und Auswertungen nur, was freigegeben ist.

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

### Prüfung, Journal und Festschreibung

accounti sagt, was der Buchhaltung fehlt und was daran nicht stimmt — die Prüfregeln lesen
nur. Was freigegeben ist, ändert sich nur noch per Storno; jede Änderung steht im Journal.

```bash
accounti pruefen --period 2026-08              # alle Regeln; Exit 1 bei Fehler-Befunden
accounti pruefen --regel umsatz_ohne_beleg --period 2026-08
accounti pruefen --archiv archiv/belege        # Pflichtangaben aus dem Original (--ocr für Scans)
accounti pruefen regeln                        # Regeln, Schweregrade, Schwellen
accounti nachfordern --period 2026-08          # Aufgaben „Beleg fehlt“; schließen sich selbst
accounti nachfordern anfrage 3fa2c1 --an beleg@lieferant.example   # Entwurf; senden mit --senden

accounti korrigiere 3fa2c1 --soll 4930 --haben 1200 --steuer 9   # freigegeben: Storno + Neubuchung
accounti buchung zeige 3fa2c1                  # Original, Storno, Neubuchung, Journal
accounti buchung storniere 3fa2c1 --grund "doppelt erfasst"
accounti journal --von 2026-08-01 --bis 2026-08-31
accounti journal pruefen                       # Verkettung, Verlauf, Bestand; Kopf zum Notieren
accounti periode schliessen 2026-08            # keine Buchung mehr im August
accounti periode oeffnen 2026-08 --grund "Rechnung nachgereicht"
accounti opos verbuchen --buchungsdatum eingang   # Rechnung zu einem festgeschriebenen Monat
accounti verfahrensdoku --ausgabe verfahrensdoku.md --pdf verfahrensdoku.pdf
accounti journal uebernehmen                   # einmal nach dem Update einer älteren Datenbank
```

Ab der Freigabe (auch automatisch gebuchte Buchungen) ist eine Korrektur eine Stornobuchung
mit Neubuchung; beide bleiben sichtbar und verweisen aufeinander. Ändert sich das Sachkonto,
gehört `--steuer` oder `--ohne-steuer` dazu. Einen festgeschriebenen Monat öffnet nur, wer
einen Grund angibt — protokolliert wie der Jahresabschluss. Nur die EB-Werte des
Saldovortrags am 01.01. nimmt ein festgeschriebener Januar noch an; eine Eingangsrechnung zu
einem festgeschriebenen Monat bucht `opos verbuchen --buchungsdatum` in einen offenen Monat —
bei Bilanzierung (und ohne ausdrückliche `abschluss.gewinnermittlung`) nicht über den
Geschäftsjahreswechsel.

Mit eingerichteten Benutzern gilt jeweils mit Einmalcode:

| Recht (Rollen) | Befehle |
|----------------|---------|
| buchen (`buchhalter`) | `korrigiere`, `buchung storniere`, `kasse buchen\|anfangsbestand\|storno`, `abschluss eroeffnung`, `bank bestaetigen\|ablehnen`, `nachfordern anfrage --senden`, `zahlung anlegen\|abgleichen`, `belege freigeben` … |
| Buchungen freigeben (`buchhalter`, `freigeber`) | `bestaetige`, `opos bestaetigen\|ablehnen`, `abschluss bestaetigen\|ablehnen`, `periode schliessen`, `abschluss vortrag`, `export datev`, `datev belege` |
| Zahlungsläufe freigeben (`freigeber`) | `zahlung freigeben\|stornieren\|sepa` |
| Steuermeldungen freigeben (`freigeber`) | `ustva freigeben`, `periode oeffnen`, `abschluss oeffnen` — wer bucht, hebt keine Festschreibung auf |
| verwalten (`verwalter`) | `journal uebernehmen` |

Im Journal steht dann der Benutzer, nicht ein Freitext aus `--von`; wer keine
Rechteprüfung durchlaufen hat (Läufe wie `classify`, Importe), steht dort als „… (ungeprüft)“.
Beim Öffnen nennt accounti schon freigegebene oder abgegebene Voranmeldungen des
Zeitraums. `opos verbuchen` und `periode schliessen` laufen nie neben `bank lauf`, `classify`
oder einem anderen Buchungslauf derselben Datenbank (Laufsperre, sonst Exit 1),
`nachfordern` nicht neben `aufgaben lauf`.

Eine bestehende Datenbank bekommt Journal und Storno-Spalten mit `alembic upgrade head`
(Migration `ddc9a184ddb4`); gleich danach — bevor accounti selbst schreibt — einmal
`accounti journal uebernehmen`, sonst meldet `journal pruefen` den älteren Bestand als
„ohne Eintrag“. Später lehnt `journal uebernehmen` ab: Was dann ohne Eintrag ist, entstand an
accounti vorbei ([Upgrades](docs/betrieb.md#upgrades)).

### Betrieb, Benutzer und mehrere Gesellschaften

```bash
docker compose up -d --build                       # App, PostgreSQL, geplanter Lauf (docs/betrieb.md)
accounti benutzer anlegen eva --rolle buchhalter   # Rollen: betrachter, buchhalter, freigeber, verwalter
accounti benutzer 2fa eva                          # TOTP-App + zehn Wiederherstellungscodes
accounti benutzer liste | rolle | passwort | sperren | entsperren | protokoll
accounti token anlegen erp --recht opos:lesen --recht belege:schreiben
accounti gesellschaft liste                        # Registry `gesellschaften`
accounti --gesellschaft tochter opos liste         # setzt --db/--archiv/--config aller Befehle
accounti sicherung erstellen --ziel /sicherungen/  # Datenbank + Belegarchiv, verschlüsselt
accounti sicherung wiederherstellen DATEI --db sqlite:////tmp/probe/x.db --archiv /tmp/probe/belege
accounti betrieb aufbewahrung                      # was frühestens ausgesondert werden dürfte
accounti betrieb lauf --intervall-minuten 60       # bank lauf + aufgaben lauf je Gesellschaft
```

Mit eingerichteten Benutzern verlangen `zahlung freigeben` und `ustva freigeben` die Rolle
`freigeber` und den Einmalcode der handelnden Person, Buchungsfreigabe, Korrektur, Storno und
Festschreibung die Rollen aus dem Abschnitt oben; ohne Benutzer bleibt alles wie bisher.

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
├── config/               # Beispielkonfiguration, eigene Kontierungsregeln
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

accounti liefert für SKR03 eine Kontendatei im Paket (Starterset, gegen den
DATEV-Kontenrahmen 2026 abgeglichen; für SKR04 gelten nur Kontenbereiche) mit:

- Kontonummern und Bezeichnungen
- Kontotypen (Bilanz/GuV)
- BWA-Zuordnung (BWA-Zeile je Konto)
- Steuerautomatik (Vorsteuer/Umsatzsteuer)
- Steuerschlüssel nach DATEV-Standard

```yaml
# accounti/pruefung/skr03.yaml (Auszug; mitgeliefert, eigene Datei: pruefung.kontenrahmen_datei)
konten:
  "8400":
    name: "Erlöse 19 % USt"
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
      schluessel: null
      automatik: false
```

`automatik: true` tragen nur DATEV-Automatikkonten (AV/AM). Im DATEV-Export bleibt auf ihnen
der passende Steuerschlüssel weg, ohne Steuer steht BU 40. Kontoarten, EÜR-Kennzahlen und
Saldenvortragskonten für den Jahresabschluss stehen getrennt davon in
`accounti/abschluss/kontenrahmen_skr03.yaml` bzw. `…_skr04.yaml`.

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
- Meldet OSS-Umsätze in der USt-Voranmeldung **nur als Nettoumsatz in Kz 45** (Anleitung 2026, Zeile 36) — die Steuer läuft über die OSS-Meldung

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
- [x] Live-Bankanbindung: FinTS/HBCI, Kreditkarten (PSD2 optional folgt)
- [x] FinTS-Provider und Kreditkarten (FinTS braucht eine Produktregistrierung)
- [x] Belegabgleich vor der Kontierung
- [x] Bankkonten, Provider-Schnittstelle, Datei-Provider, Dublettenschutz, geplanter Lauf
- [ ] FinTS-Provider und Kreditkarten (FinTS braucht eine Produktregistrierung)

### v0.4 — Zahlung & Prüfung *(Bausteine 6, 7)*
- [x] Zahlungsvorschlag nach Skontofrist, SEPA-Sammelüberweisung, Freigabe
- [x] Mehrstufiges Mahnwesen mit Verzugszinsen
- [x] Prüfregeln für Vollständigkeit, Richtigkeit, Zeitgerechtheit, Ordnung
- [x] Belegnachforderung, unveränderbares Journal, Periodenabschluss
- [x] Generierte Verfahrensdokumentation

### v0.5 — Oberfläche & Betrieb *(Bausteine 8, 10)*
- [x] Aufgaben, Rückfragen am Beleg, Zuständigkeiten, Erinnerungen
- [ ] Web-UI: Supervisions-Queue mit Belegansicht, BWA mit Vorjahresvergleich
- [x] Benutzer, Rollen, 2FA, Vier-Augen-Freigabe, mehrere Gesellschaften, REST-API
- [x] Docker-Setup, verschlüsselte Sicherungen, Löschkonzept
- [ ] DE/EN in der Oberfläche

### v0.6 — Integrationen *(Baustein 11)*
- [ ] JTL-Wawi, Amazon (DE/FR/IT/ES/NL/UK/SE/PL), eBay, Shopify, PayPal
- [ ] Bestimmungsland-Erkennung für OSS
- [x] DATEV vollständig: Stammdaten, Belegbilder, Kontoauszüge
- [ ] REST-API, Prüfungsdatenüberlassung
- [ ] MT940/CAMT-Import

### v1.0 — Meldungen & Abschluss *(Bausteine 9, 12)*
- [ ] Elektronische Übermittlung: Voranmeldung, Dauerfristverlängerung, ZM
- [x] Plausibilisierung vor Abgabe, Übermittlungsprotokolle, Fristenkalender
- [x] Anlagenbuchhaltung: AfA, GWG, Sammelposten, Anlagenspiegel
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
