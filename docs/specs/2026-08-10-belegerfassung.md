# Spec: Belegerfassung & Dokumentenmanagement

- **Status:** Entwurf (2026-08-10)
- **Baustein:** 2 von 12 (siehe [Bauplan](../bauplan.md))
- **Ziel-Branch:** `feat/belegerfassung`

## 1. Kontext

Baustein 1 kontiert Banktransaktionen. Eine Banktransaktion ist aber nur die halbe Wahrheit: Sie
sagt, dass 89,50 € an einen Zahlungsdienstleister geflossen sind — nicht, wofür. Die Rechnung
dazu liegt als PDF im Postfach.

Ohne Beleg fehlt der Kontierung der Kontext (Positionen, Steuersätze, Leistungsdatum), dem
Vorsteuerabzug die Grundlage und der Buchführung die Ordnungsmäßigkeit. Dieser Baustein baut den
zweiten Strang der Pipeline: **Belege kommen ins System, werden gelesen und strukturiert.**

Der Abgleich Beleg ↔ Banktransaktion gehört nicht hierher, sondern in Baustein 5.

## 2. Ziel

> Ein Beleg landet über einen beliebigen Kanal im System und wird zu einem strukturierten
> `Beleg`-Objekt mit Positionen, Beträgen, Steuersätzen und Belegdatum — ohne dass jemand etwas
> abtippt.

## 3. Pipeline

```
Kanäle                    Verarbeitung                     Ergebnis
──────                    ────────────                     ────────
Watch-Ordner   ┐
E-Mail-Postfach├─▶ [1] Intake ──▶ [2] Dublettenprüfung ──▶ verworfen / neu
Messenger      │       Rohdatei          (Hash, RgNr,
Upload (UI/CLI)│       + Metadaten        Betrag+Datum)
Connector-API  ┘                              │
                                              ▼
                                       [3] Erkennung
                                       ├─ E-Rechnung? ──▶ Baustein 3 (Parser)
                                       ├─ PDF/Bild?  ───▶ OCR + Extraktion
                                       └─ Kreditkarten-
                                          abrechnung? ──▶ Positionsaufteilung
                                              │
                                              ▼
                                       [4] Belegart
                                       (Eingangsrechnung, Ausgangsrechnung,
                                        Quittung, Kontoauszug, Vertrag, sonstiges)
                                              │
                                              ▼
                                       [5] Beleg + Belegpositionen
                                              │
                                              ▼
                                       [6] Archiv (unveränderbar, 10 Jahre)
```

## 4. Komponenten & Arbeitspakete

### 4.1 `belege/kanaele/` — Intake *(neu)*

Kanäle folgen demselben Muster wie die Bank-Importer in Baustein 1: eine Basisklasse plus
Registry (`BELEG_KANAELE`), damit neue Kanäle ohne Kernänderung dazukommen — analog zu
`BANK_IMPORTERS` in `importers/__init__.py`.

| Kanal | Beschreibung |
|-------|--------------|
| `ordner` | Überwachtes Verzeichnis; Datei rein = Beleg rein. Der einfachste Kanal, deshalb zuerst |
| `email` | IMAP-Postfach, Anhänge werden gezogen; Absender wird als Hinweis auf den Kreditor gespeichert |
| `upload` | CLI (`accounti belege import`) und später Web-UI |
| `webhook` | HTTP-Endpunkt für Messenger-Weiterleitungen und Fremdsysteme, tokengeschützt |
| `connector` | Abholung aus Belegportalen und Rechnungssammeldiensten über deren API |

Jeder Kanal liefert nur Rohdatei + Herkunftsmetadaten. **Kein Kanal kennt Buchhaltungslogik.**

### 4.2 `belege/erkennung.py` — Format- und Belegarterkennung *(neu)*

- Erkennt zuerst, ob eine strukturierte E-Rechnung vorliegt (PDF/A-3 mit eingebettetem XML oder
  reines XML) → weiter an Baustein 3. Strukturierte Daten schlagen OCR immer.
- Sonst: PDF mit Textebene → Textextraktion; Scan/Foto → OCR.
- Belegart wird klassifiziert (Eingangsrechnung, Ausgangsrechnung, Quittung, Kontoauszug,
  Vertrag, sonstiges). Regelwerk zuerst, LLM als zweite Stufe — dasselbe dreistufige Prinzip wie
  bei der Kontierung, inklusive Confidence und Begründung.

### 4.3 `belege/ocr/` — Texterkennung *(neu)*

Steckbares Interface mit mindestens einer lokalen Implementierung als Default. Grund: Die
Architektur sagt „Self-Hosted: Deine Daten bleiben auf deinem Server" zu — ein Cloud-OCR-Dienst
als Zwangsvoraussetzung würde das brechen. Cloud-OCR bleibt eine bewusst zu aktivierende Option
für Anwender, die bessere Erkennungsraten über Datensparsamkeit stellen.

Extrahiert werden: Rechnungsnummer, Belegdatum, Leistungsdatum, Lieferant (Name, Anschrift,
USt-IdNr.), Netto/Steuer/Brutto je Steuersatz, Zahlungsziel, Skonto, IBAN, Positionen.

### 4.4 `belege/positionen.py` — Positionssplit *(neu)*

Eine Rechnung kann mehrere Konten betreffen: Ein Beleg über Büromaterial und Fachliteratur gehört
auf zwei Aufwandskonten. Deshalb ist `Belegposition` ein eigenes Objekt und die Kontierung arbeitet
auf Positionen, nicht auf Belegen.

Sonderfall Kreditkartenabrechnung: eine PDF-Datei, viele Einzelumsätze. Sie wird in Positionen
zerlegt, die sich anschließend wie einzelne Transaktionen kontieren lassen.

### 4.5 `belege/dubletten.py` — Dublettenerkennung *(neu)*

Belege kommen doppelt — per Mail und nochmal aus dem Portal. Dreistufig:
1. Byte-Hash der Datei (identische Datei),
2. Lieferant + Rechnungsnummer (identischer Beleg, andere Datei),
3. Lieferant + Betrag + Datum in engem Fenster (Verdacht, geht zur Prüfung statt automatisch weg).

### 4.6 `belege/archiv.py` — Belegablage *(neu)*

Originaldatei wird unverändert abgelegt, adressiert über ihren Hash, mit Aufbewahrungsfrist.
Löschen ist nicht vorgesehen, nur Markieren. Das Archiv ist die Grundlage für den
DATEV-Belegexport in Baustein 11 und für die Vollständigkeitsprüfung in Baustein 7.

### 4.7 Datenmodell *(neu in `models/`)*

```
Beleg                          Belegposition
─────                          ─────────────
id                             id
belegart                       beleg_id
richtung (eingang/ausgang)     bezeichnung
belegnummer                    menge
belegdatum                     netto
leistungsdatum                 steuersatz
kontakt_id  ─────────┐         steuer_betrag
netto / steuer / brutto        konto_vorschlag
waehrung             │         confidence
zahlungsziel         │
skonto_prozent/-tage │
datei_hash           │
kanal / eingegangen_am
status               └──▶ Kontakt (Baustein 4)
confidence
```

`Buchungssatz` bekommt eine optionale `beleg_position_id`, damit jede Buchung auf ihren Beleg
zeigt (Leitplanke „Belegbezug", siehe [Bauplan](../bauplan.md#fachliche-leitplanken)).

### 4.8 CLI

```bash
accounti belege kanaele                     # verfügbare Kanäle auflisten
accounti belege import ./rechnung.pdf       # Einzelbeleg
accounti belege abholen --kanal email       # Kanal einmal leeren
accounti belege liste --status offen        # Übersicht
```

## 5. Tech-Entscheidungen (fix)

| Thema | Entscheidung |
|-------|--------------|
| Kanäle | Registry + Basisklasse, analog `BANK_IMPORTERS` |
| OCR | Steckbar; lokale Engine als Default, Cloud opt-in |
| Reihenfolge | Strukturierte Daten (E-Rechnung) schlagen immer OCR |
| Ablage | Content-adressiert über Hash, Originaldatei unverändert |
| Extraktion | Regelwerk zuerst, LLM als zweite Stufe, Confidence wie bei der Kontierung |
| Datenschutz | Belegtexte im LLM-Prompt maskiert (IBAN, Namen, Belegnummern) |

## 6. Teststrategie

- Kanal-Tests gegen temporäre Verzeichnisse und ein gemocktes IMAP-Postfach.
- OCR gemockt; die Extraktionslogik wird gegen feste Textfixtures getestet, nicht gegen Bilder.
- Fixture-Sammlung anonymisierter Belege in `examples/belege/` — deutsche Zahlen- und
  Datumsformate, mehrere Steuersätze auf einem Beleg, fehlende Pflichtangaben.
- Dublettenerkennung mit allen drei Stufen als eigene Testfälle.
- Bestehende Tests bleiben grün; `ruff` und `mypy --strict` sauber.

## 7. Akzeptanzkriterien

1. Eine PDF-Rechnung im Watch-Ordner wird ohne Zutun zu einem `Beleg` mit korrekten Beträgen,
   Belegdatum und Lieferant.
2. Eine Rechnung mit zwei Steuersätzen erzeugt zwei `Belegposition`-Objekte mit je korrektem
   Netto- und Steuerbetrag.
3. Derselbe Beleg über zwei Kanäle erzeugt genau einen Datensatz; der zweite Eingang wird als
   Dublette protokolliert.
4. Eine Kreditkartenabrechnung mit zwölf Umsätzen ergibt zwölf Positionen.
5. Ein unlesbarer Scan landet mit Begründung im Status „zur Prüfung" — die Pipeline bricht nicht ab.
6. Die Originaldatei ist nach dem Import unverändert im Archiv auffindbar.

## 8. Ausdrücklich NICHT in diesem Baustein

Abgleich Beleg ↔ Banktransaktion (Baustein 5) · Erzeugen von Ausgangsrechnungen (Baustein 3) ·
offene Posten (Baustein 4) · Vollständigkeitsprüfung „welcher Beleg fehlt" (Baustein 7) ·
Web-Oberfläche zum Sichten der Belege (Baustein 10).
