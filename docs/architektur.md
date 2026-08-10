# accounti — Architektur

## Überblick

accounti ist als Pipeline aufgebaut: Daten fließen in eine Richtung von Import über Klassifikation und Buchung bis zum Export. Jede Stufe kann unabhängig getestet und erweitert werden.

```
Belege ──┐
         ├── Abgleich → Klassifikation → Buchung → Export/BWA/Steuer/Abschluss
Umsätze ─┘                    ↑                        │
                              └── Lernschleife ────────┘
```

Der Belegstrang und der Umsatzstrang laufen im Abgleich zusammen — bewusst **vor** der
Klassifikation, damit die Kontierung den Beleg bereits kennt.

Welche Module in welcher Reihenfolge entstehen, steht im [Bauplan](bauplan.md).

## Designprinzipien

1. **Regelwerk vor KI**: Deterministische Regeln sind schneller, billiger und nachvollziehbar. Das LLM kommt nur zum Einsatz, wenn keine Regel greift.

2. **Nachvollziehbarkeit**: Jede Buchung speichert ihre Herkunft — ob per Regel oder LLM, mit welcher Confidence, und welche Begründung die KI gegeben hat.

3. **Supervisor hat das letzte Wort**: Nichts wird exportiert ohne menschliche Freigabe (zumindest in den ersten Versionen). Automatische Buchungen sind opt-in.

4. **DATEV-Kompatibilität**: Der Export muss 1:1 in DATEV importierbar sein. Kein "fast richtig".

5. **Erweiterbar**: Neue Bankformate, ERP-Quellen und Kontenrahmen sollen ohne Kernänderungen hinzufügbar sein.

6. **Unveränderbarkeit**: Was freigegeben oder exportiert wurde, wird nicht mehr überschrieben. Korrekturen sind Stornos mit Neubuchung; beide bleiben sichtbar und verweisen aufeinander. Das Journal ist fortlaufend und append-only. Vor der Freigabe darf ein Vorschlag frei korrigiert werden — die Grenze ist die Freigabe, und sie steht im Journal.

7. **Belegbezug**: Jede Buchung zeigt auf ihren Beleg oder trägt eine Begründung, warum sie belegfrei ist. Eine Zahlung ohne Beleg ist kein Randfall, sondern ein Befund.

Prinzip 6 und 7 ergeben sich aus den GoBD und sind der Grund, warum die Prüfmechanik ein eigener Baustein ist und nicht nebenbei entsteht.

## Module

### `importers/`

Importer wandeln Rohdaten einer Quelle in `Transaktion`-Objekte um — sie kennen nur ihr Format, keine Buchhaltungslogik.

Bank-CSVs laufen **konfigurationsgetrieben** über `profil.py`: Ein `BankProfil` beschreibt Trennzeichen, Encoding, Datums-/Betragsformat und die Spalten-Zuordnung; der generische `ProfilImporter` parst damit jede unterstützte Bank — ohne bankspezifischen Code.

- `profil.py` — `BankProfil` + `ProfilImporter`, eingebaute Profile (sparkasse, ing, dkb, volksbank, commerzbank), Auto-Erkennung (`erkenne_profil`) und Laden eigener Profile aus `config/banken.yaml`.
- `sparkasse.py` — dünner Wrapper um das Sparkasse-Profil (Rückwärtskompatibilität).
- Registry `BANK_IMPORTERS` (Bankname → einsatzbereiter Importer); `import bank --format auto` erkennt die Bank an den Spaltenüberschriften.

Geplant (eigene Importer, kein Bank-CSV): `mt940.py`, `camt.py` (XML), `jtl.py`, `amazon.py`, `ebay.py`, `paypal.py`.

### `belege/` *(geplant — [Baustein 2](specs/2026-08-10-belegerfassung.md))*

Bringt Belege ins System und macht Daten daraus. Kanäle folgen demselben Registry-Muster wie die Bank-Importer: `ordner`, `email`, `upload`, `webhook`, `connector` — jeder liefert nur Rohdatei plus Herkunft, keiner kennt Buchhaltungslogik.

- `erkennung.py` — E-Rechnung, PDF mit Textebene oder Scan? Strukturierte Daten schlagen immer OCR. Klassifiziert die Belegart (Eingangs-/Ausgangsrechnung, Quittung, Kontoauszug, …).
- `ocr/` — steckbar; lokale Engine als Default, damit die Zusage „Daten bleiben auf deinem Server" hält.
- `positionen.py` — Positionssplit. Eine Rechnung kann mehrere Konten betreffen; eine Kreditkartenabrechnung ist eine Datei mit vielen Umsätzen.
- `dubletten.py` — Datei-Hash, dann Lieferant + Rechnungsnummer, dann Betrag + Datum im engen Fenster.
- `archiv.py` — Originaldatei unverändert, content-adressiert, mit Aufbewahrungsfrist. Kein Löschpfad.

### `erechnung/` *(geplant — [Baustein 3](specs/2026-08-10-erechnung.md))*

Liest und schreibt strukturierte Rechnungen. Alle Formate werden auf ein gemeinsames Zwischenmodell nach EN 16931 abgebildet; die restliche Anwendung kennt nur dieses Modell, nie ein konkretes Format.

- `parser/` — XRechnung (UBL, CII), ZUGFeRD/Factur-X (XML aus PDF/A-3).
- `validierung.py` — Schema, Schematron, fachliche Prüfungen. Befunde mit Schweregrad statt „gültig/ungültig".
- `erzeuger/` — Ausgangsrechnungen. Die Steuer kommt vollständig aus `steuer/`; es gibt keine zweite Steuerlogik im Rechnungsschreiber.

### `bank/` *(geplant — [Baustein 5](specs/2026-08-10-bankanbindung-live.md))*

Holt Kontoumsätze selbst ab und führt sie mit Belegen zusammen.

- `provider.py` — Registry wie bei den Importern: `fints` (Direktverbindung, Default), `psd2` (Aggregator, opt-in), `datei` (der bestehende Dateiimport hinter derselben Schnittstelle). Damit bleibt accounti ohne jede Bankverbindung vollständig nutzbar.
- `abgleich.py` — Beleg ↔ Umsatz, dreistufig: Referenz, exakter Treffer, unscharfer Vorschlag. Bewusst streng — ein falscher Abgleich begründet eine falsche Vorsteuer und ist teurer als ein fehlender.
- `konten.py` — Bankkonten und Zugänge; Zugangsdaten verschlüsselt, nie in Logs, nie im LLM-Prompt.

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

Geplant: ein zweiter Pfad über Personenkonten. Liegt ein Beleg mit Kontakt vor, wird gegen Debitor bzw. Kreditor gebucht und ein offener Posten erzeugt. Der bestehende Pfad (Bankbuchung ohne Beleg) bleibt — für Gebühren, Zinsen und Ähnliches ist er weiterhin richtig.

### `kontakte/` *(geplant — [Baustein 4](specs/2026-08-10-kreditoren-debitoren-opos.md))*

Debitoren- und Kreditorenstammdaten mit Personenkontonummern aus den Nummernkreisen des Kontenrahmens. Erkennung aus Belegdaten über IBAN, dann USt-IdNr., dann Name — greift nichts, geht die Neuanlage zur Prüfung, statt still zu passieren.

`ustid.py` führt die qualifizierte Bestätigungsabfrage durch und protokolliert sie revisionssicher. Erst damit steht die in `steuer/umsatzsteuer.py` implementierte Regel „EU + B2B mit USt-ID → 0 %" auf einer belastbaren Grundlage.

### `opos/` *(geplant — [Baustein 4](specs/2026-08-10-kreditoren-debitoren-opos.md))*

Offene Posten mit Fälligkeit, Skontofrist und Restbetrag; Fälligkeitsstaffel. `zuordnung.py` ordnet Zahlungen dreistufig zu (Referenz, exakt, unscharf), `ausgleich.py` bucht den Ausgleich — bei gezogenem Skonto immer **mit** anteiliger Steuerkorrektur, nie als reine Betragsdifferenz.

### `zahlung/` und `mahnwesen/` *(geplant — [Baustein 6](specs/2026-08-10-zahlungsverkehr-mahnwesen.md))*

`zahlung/` erzeugt die Vorschlagsliste (Skontofristen vor Nettofälligkeiten), prüft blockierend — eine vom Stammsatz abweichende IBAN stoppt den Lauf —, verwaltet die Freigabe als Zustandsautomaten und schreibt SEPA-Sammelüberweisungen. Einreichung über den Bank-Provider oder als Datei; der Dateiweg bleibt immer verfügbar.

`mahnwesen/` führt Mahnstufen aus `config/mahnwesen.yaml`, berechnet Verzugszinsen mit datiertem Basiszinssatz und zählt die Stufe am offenen Posten hoch.

### `pruefung/` *(geplant — [Baustein 7](specs/2026-08-10-belegvollstaendigkeit-gobd.md))*

Die Mechanik hinter den Prinzipien 6 und 7. Benannte Prüfregeln mit Schweregrad liefern Befunde und ändern nie Daten: Umsatz ohne Beleg, Beleg ohne Zahlung, Lücken in Nummernkreisen, § 14 UStG-Pflichtangaben, Rechenprobe, Steuerschlüssel ./. Sachkonto, Zeitgerechtheit.

`journal.py` führt das hashverkettete, append-only Journal. `perioden.py` schließt Zeiträume ab. `verfahrensdoku.py` generiert die Verfahrensdokumentation aus dem tatsächlichen Systemzustand statt aus einem Textbaustein, der nach der ersten Konfigurationsänderung nicht mehr stimmt.

### `aufgaben/` *(geplant — [Baustein 8](specs/2026-08-10-aufgaben-rueckfragen.md))*

Alles, was ein Mensch entscheiden muss, an einem Ort: unsichere Buchung, unlesbarer Beleg, fehlender Beleg, ausstehende Freigabe. Erzeugung ist idempotent über (Art, Objekt), sonst entstünde bei jedem Prüflauf dieselbe Aufgabe neu. Entfällt der Anlass, schließt sich die Aufgabe selbst — Listen, die nur wachsen, werden ignoriert.

Kommentare hängen an einer Aufgabe **oder** direkt am Beleg. Intern gedacht: kein Portal für externe Nutzer.

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

### `elster/` *(geplant — [Baustein 9](specs/2026-08-10-steuermeldungen-elster.md))*

Die Rechenlogik der Meldungen liegt in `steuer/` und ist fertig; hier kommt der letzte Schritt dazu: Plausibilisierung vor der Abgabe, Übermittlung von Voranmeldung, Dauerfristverlängerung und Zusammenfassender Meldung, sowie das unveränderbare Protokoll aus Datensatz, Ticket, Zeitpunkt und Prüfbericht.

Ein Testmodus erzeugt und prüft, ohne abzugeben. Die Freigabe durch einen Menschen ist nicht abkürzbar — eine Steuererklärung wird abgegeben, nicht ausgelöst.

### `anlagen/` und `abschluss/` *(geplant — [Baustein 12](specs/2026-08-10-anlagen-jahresabschluss.md))*

`anlagen/` führt Anlagegüter und schreibt die AfA fort (linear zeitanteilig, GWG, Sammelposten), erstellt den Anlagenspiegel und rechnet Abgänge. Grenzbeträge sind Konfiguration **mit Gültigkeitszeitraum**, damit alte Jahre mit den damals gültigen Werten rechenbar bleiben.

`abschluss/` bildet Abgrenzungen und Rückstellungen als Vorschläge — Bewertungen werden bestätigt, nicht gesetzt —, führt das Kassenbuch (negativer Bestand wird abgelehnt, nicht gewarnt), erstellt EÜR oder Bilanz mit GuV und trägt die Salden ins neue Jahr vor.

### `export/`

**DATEV-Export** (Priorität):
- EXTF-Format Version 700
- Buchungsstapel + Debitoren/Kreditoren
- cp1252-Encoding (DATEV-Standard)

Weitere Exportformate:
- CSV (generisch)
- JSON (für API-Konsumenten)

Geplant ([Baustein 11](specs/2026-08-10-integrationen-export.md)): Debitoren-/Kreditoren-Stammdaten, Belegbilder mit Verknüpfung zum Buchungssatz, Kontoauszüge, Prüfungsdatenüberlassung.

### `bwa/`

Berechnet die BWA aus Buchungssätzen. Standard: DATEV BWA-Form 01. Unterstützt:
- Monatsauswertung
- Kumuliert (Jahresanfang bis Stichtag)
- Vorjahresvergleich

### `auth/` *(geplant — [Baustein 10](specs/2026-08-10-web-ui-auth-betrieb.md))*

Benutzer, Rollen, Sitzungen, Zwei-Faktor-Authentifizierung. Rollen `betrachter` / `buchhalter` / `freigeber` / `verwalter`; die Trennung von Buchen und Freigeben ist die Voraussetzung dafür, dass das Vier-Augen-Prinzip überhaupt greifen kann. Ab hier trägt jeder Journaleintrag einen echten Benutzer statt einer freien Zeichenkette.

### `api/`

REST-API (FastAPI) für:
- Supervision: Buchungen prüfen, korrigieren, freigeben
- BWA-Abfrage
- Import-Trigger
- Statusübersicht

Web-UI: Minimalistisch mit HTMX + Jinja2 (kein SPA-Build-Step).

Kernansicht ist die Supervisions-Queue: links die Belegvorschau, rechts der Buchungsvorschlag mit Confidence und Begründung, Korrektur in einem Schritt — und das Angebot, aus der Korrektur eine Regel zu machen. Die Oberfläche ruft dieselben Funktionen auf wie die CLI; Logik, die nur im Browser existiert, gibt es nicht.

## Datenmodell

Der Kern steht in `models/` und ist umgesetzt: `Transaktion`, `Konto`, `Buchungssatz`,
`Klassifikationsergebnis`, `Regel`. Die geplanten Bausteine erweitern ihn um:

| Entität | Kernfelder | Bezug |
|---------|-----------|-------|
| `Beleg` | Belegart, Richtung, Belegnummer, Beleg-/Leistungsdatum, Netto/Steuer/Brutto, Zahlungsziel, Skonto, Datei-Hash, Kanal, Status | → `Kontakt` |
| `Belegposition` | Bezeichnung, Menge, Netto, Steuersatz, Steuerbetrag, Kontovorschlag | → `Beleg`; `Buchungssatz.beleg_position_id` |
| `Kontakt` | Name, Anschrift, Land, USt-IdNr., IBAN, Zahlungsbedingungen, Personenkonto | → `Beleg`, `OffenerPosten` |
| `OffenerPosten` | Richtung, Betrag, Restbetrag, Fälligkeit, Skontofrist, Status, Mahnstufe | → `Kontakt`, `Beleg` |
| `Zahlung` | Lauf, Betrag, Ausführungsdatum, Status (Entwurf → freigegeben → eingereicht → ausgeführt) | → `OffenerPosten` |
| `Aufgabe` | Art, Titel, Objektbezug, Zuständigkeit, Fälligkeit, Status, Idempotenzschlüssel | → beliebiges Objekt |
| `Anlagegut` | Anschaffungsdatum und -kosten, Nutzungsdauer, AfA-Art, Restbuchwert, Abgang | → `Beleg`, `Buchungssatz` |
| `Journaleintrag` | Laufende Nummer, Zeitpunkt, Benutzer, Vorgang, Vorher/Nachher, Hash des Vorgängers | → alles Buchungsrelevante |

`Buchungssatz` bekommt zwei Ergänzungen: `beleg_position_id` für den Belegbezug (Prinzip 7) und
`storniert_durch` / `storno_von` für Korrekturen nach Freigabe (Prinzip 6).

## Datenfluss

```
                    ┌──────────────────────────────┐
                    │         PostgreSQL           │
  Belege ─────────▶ │  belege · belegpositionen    │
                    │  kontakte                    │
  Import ─────────▶ │  transaktionen               │
  Bank live ──────▶ │  bankkonten                  │
                    │  buchungssaetze              │
  Klassifikation ──▶│  regeln · konten             │
                    │  offene_posten · zahlungen   │
  Prüfung ────────▶ │  befunde · journal           │
                    │  aufgaben                    │
  Steuer ─────────▶ │  meldungen · protokolle      │
  Abschluss ──────▶ │  anlagegueter · abschluesse  │
  BWA ◀──────────── │  bwa_berichte                │
  DATEV ◀────────── │  export_log                  │
                    └──────────────────────────────┘
```

## Sicherheit

- API-Keys werden nie in der Datenbank gespeichert
- Bankzugänge und Übermittlungszertifikate liegen verschlüsselt, mit Schlüssel aus der Umgebung — nie im Klartext, nie in Logs
- LLM-Prompts enthalten keine echten Kontodaten — nur anonymisierte Muster
- DATEV-Exports werden lokal erzeugt, nie über externe APIs
- Self-Hosted: Deine Daten bleiben auf deinem Server. Deshalb ist auch die OCR-Engine standardmäßig lokal und Cloud-Verarbeitung opt-in
- Belege, Buchungen, Journale und Übermittlungsprotokolle unterliegen der zehnjährigen Aufbewahrungsfrist; das Löschkonzept kennt sie, statt sie zu ignorieren

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

### Neuen Beleg-Kanal hinzufügen *(geplant)*

Ein Kanal implementiert die Basisklasse aus `belege/kanaele/` und trägt sich in die Registry
`BELEG_KANAELE` ein — dasselbe Muster wie `BANK_IMPORTERS`. Er liefert Rohdatei plus
Herkunftsmetadaten, sonst nichts: Erkennung, OCR, Dublettenprüfung und Archivierung passieren
dahinter und sind für alle Kanäle identisch.

Wer nur ein anderes Postfach oder Verzeichnis anbinden will, braucht keinen neuen Kanal, sondern
nur einen Eintrag in `config/belege.yaml`.

### Neuen Bank-Provider hinzufügen *(geplant)*

Ein Provider implementiert die Schnittstelle aus `bank/provider.py`: Konten auflisten, Umsätze ab
einem Zeitpunkt abrufen, Saldo melden — und optional Zahlungen einreichen. Alles dahinter
(Normalisierung, Dublettenschutz, Abgleich, Kontierung) ist providerunabhängig.

Weil der bestehende Dateiimport selbst als Provider eingehängt ist, bleibt accounti auch dann
vollständig nutzbar, wenn kein einziger Live-Provider eingerichtet ist.

### Neue Prüfregel hinzufügen *(geplant)*

Prüfregeln aus `pruefung/regeln/` sind benannt, tragen einen Schweregrad und liefern Befunde —
sie ändern nie Daten. Schwellenwerte (ab welchem Betrag ein fehlender Beleg auffällt, wie viele
Tage Zeitgerechtheit bedeutet) gehören in die Konfiguration, nicht in den Code.

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
