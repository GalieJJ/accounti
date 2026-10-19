# Belegerfassung, Paket 2 — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Aus einem archivierten Rohbeleg wird ein strukturierter `Beleg` mit Belegart, Lieferant,
Belegnummer, Datum, Beträgen je Steuersatz und Positionen — ohne Abtippen. Was nicht sicher erkannt
wird, geht mit Begründung in die Prüfung.

**Spec:** [`docs/specs/2026-08-10-belegerfassung.md`](../specs/2026-08-10-belegerfassung.md),
Abschnitte 4.2–4.4 · **Baut auf:** [Paket 1](2026-10-19-belegerfassung-paket-1.md)

**Architektur:** Der `BelegErkenner` ist der `erkenner` aus Paket 1 und läuft in drei Schritten:

```
RohBeleg ─▶ [1] Format          ─▶ [2] Text                 ─▶ [3] Extraktion
            E-Rechnung (XML,        PDF-Textebene (pypdf)       Regelwerk: Felder, Steuerzeilen,
            ZUGFeRD-Anhang),        oder OCR (steckbar,         Belegart, Kreditkartenumsätze
            PDF, Bild               Tesseract lokal)            └─ LLM (opt-in, maskiert) füllt Lücken
```

---

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| PDF-Text | `pypdf` als neue Abhängigkeit | reines Python, typisiert, kann auch eingebettete Dateien (ZUGFeRD) lesen |
| OCR | Registry `OCR_ENGINES`; `tesseract` über die CLI (`tesseract stdin stdout -l deu`) | lokal, keine Python-Abhängigkeit; fehlt das Programm, geht der Beleg mit Hinweis in die Prüfung |
| Gescannte PDFs | eingebettete Seitenbilder (pypdf) an die OCR | ohne Poppler/Ghostscript auskommen |
| E-Rechnung | nur erkennen (CII/UBL im XML oder als PDF-Anhang); Übernahme folgt mit Baustein 3 | „strukturierte Daten schlagen OCR" — bis der Parser steht, nicht aus dem Sichtbild raten |
| Positionen (Regelwerk) | eine `Belegposition` je Steuersatz | Einzelpositionen per Regex sind zu unzuverlässig; die LLM-Stufe darf echte Positionen liefern |
| Kreditkartenabrechnung | jede Umsatzzeile → eine Position, Belegart `kontoauszug` | Akzeptanzkriterium 4 |
| LLM-Stufe | **Standard: aus** (`--llm` schaltet ein); Text maskiert (IBAN, USt-IdNr., E-Mail, Telefon, Lieferant, Belegnummer, lange Ziffernfolgen) | Belege enthalten viel mehr personenbezogene Daten als ein Verwendungszweck |
| Zusammenführung | Regelwerk gewinnt, LLM füllt nur leere Felder | deterministisch vor probabilistisch |
| Status | `erfasst` nur bei Belegart, Lieferant, Datum, Brutto und bestandener Rechenprobe; sonst `pruefung` mit Liste der Lücken | der Mensch entscheidet |

## Dateistruktur

| Pfad | Verantwortung |
|------|---------------|
| `src/accounti/belege/zahlen.py` | deutsche Beträge und Datumsangaben parsen |
| `src/accounti/belege/ocr/__init__.py` | `OCREngine`, `OCR_ENGINES`, `OCRNichtVerfuegbarError` |
| `src/accounti/belege/ocr/tesseract.py` | `TesseractEngine` |
| `src/accounti/belege/erkennung.py` | `erkenne_format`, `hole_text`, `erkenne_belegart`, `BelegErkenner` |
| `src/accounti/belege/extraktion.py` | `extrahiere` → `Extrakt` (Felder, Steuerzeilen, Summen, Rechenprobe) |
| `src/accounti/belege/positionen.py` | Positionen je Steuersatz; Kreditkartenabrechnung zerlegen |
| `src/accounti/belege/llm.py` | `LLMBelegEngine`, `maskiere_beleg` |
| `src/accounti/belege/pipeline.py` | `erkenne_erneut` für bereits archivierte Belege |
| `src/accounti/db/repository.py` | `aktualisiere_beleg` |
| `src/accounti/cli.py` | `--erkennen/--ohne-erkennung`, `--llm`, `--eigene-ust-id`; neuer Befehl `belege erkennen` |
| `examples/belege/*.txt` | anonymisierte Textfixtures |
| `tests/pdf_hilfe.py` | erzeugt minimale PDFs mit Textebene für Tests |

---

## Aufgabe 1: Zahlen und Daten

**Tests:** `tests/test_belege_zahlen.py`

- [x] `1.234,56` · `1234,56` · `-23,99` · `23,99-` · `1.234,56 €` · `EUR 12,00` → `Decimal`.
- [x] `05.03.2026` · `5.3.26` · `5. März 2026` · `2026-03-05` → `date`; ungültige Daten → `None`.

## Aufgabe 2: Extraktion

**Tests:** `tests/test_belege_extraktion.py`, Fixtures `examples/belege/`

- [x] Rechnungsnummer, Rechnungsdatum, Leistungsdatum, Lieferant (Zeile mit Rechtsform, sonst erste Zeile), USt-IdNr., IBAN (mit Prüfziffer).
- [x] Zahlungsziel (`zahlbar bis …` und `innerhalb von N Tagen`), Skonto (Prozent + Tage).
- [x] Steuerzeilen: zwei Steuersätze auf einem Beleg → zwei Zeilen mit Netto und Steuer.
- [x] Summen und Rechenprobe; fehlende Summe aus den Steuerzeilen ableiten; „inkl. MwSt." (Quittung).
- [x] Unvollständige Rechnung → fehlende Felder bleiben `None`, Rechenprobe `None`.

## Aufgabe 3: Positionen

**Tests:** `tests/test_belege_positionen.py`

- [x] (Akzeptanz 2) Zwei Steuersätze → zwei `Belegposition` mit je korrektem Netto und Steuer.
- [x] (Akzeptanz 4) Kreditkartenabrechnung mit zwölf Umsätzen → zwölf Positionen; Vorzeichen wie bei `Transaktion` (Belastung negativ, Gutschrift positiv); Summen- und Saldozeilen ignoriert.

## Aufgabe 4: Belegart

**Tests:** `tests/test_belege_erkennung.py`

- [x] Rechnung, Quittung, Kontoauszug, Kreditkartenabrechnung, Vertrag, sonstiges — je ein Fixture.
- [x] Rechnung mit eigener USt-IdNr. als Absender → `ausgangsrechnung`, Richtung `ausgang`.

## Aufgabe 5: Format und Text

**Tests:** `tests/test_belege_erkennung.py`, `tests/test_belege_ocr.py`

- [x] Format: XML mit `CrossIndustryInvoice`/`Invoice` → E-Rechnung; PDF mit `factur-x.xml`-Anhang → ZUGFeRD; PDF mit Text → PDF-Text; PDF ohne Text → Scan; `.jpg`/`.png`/`.tif` → Bild.
- [x] `hole_text` liest die Textebene; Scan und Bild gehen an die OCR-Engine (gemockt).
- [x] `TesseractEngine`: ruft das Programm mit `-l deu` auf; fehlt es → `OCRNichtVerfuegbarError` mit Installationshinweis. Echter Lauf nur, wenn `tesseract` installiert ist (`skipif`).

## Aufgabe 6: LLM-Stufe

**Tests:** `tests/test_belege_llm.py`

- [x] `maskiere_beleg` entfernt IBAN, USt-IdNr., E-Mail, Telefon, bekannten Lieferanten und Belegnummer.
- [x] Antwort-JSON wird zu Feldern und Positionen; Fehler → `None`.
- [x] Regelwerk gewinnt: LLM füllt nur Felder, die das Regelwerk leer gelassen hat.

## Aufgabe 7: BelegErkenner und Pipeline

**Tests:** `tests/test_belege_erkenner.py`

- [x] (Akzeptanz 1) PDF-Rechnung mit Textebene → `Beleg` mit Beträgen, Belegdatum, Lieferant; Status `erfasst`.
- [x] Unvollständige Rechnung → `pruefung`, Grund nennt die fehlenden Felder.
- [x] E-Rechnung → `eingangsrechnung`, `pruefung` mit Hinweis auf Baustein 3.
- [x] (Akzeptanz 5) OCR nicht verfügbar → `pruefung` mit Hinweis, Pipeline läuft weiter.
- [x] `erkenne_erneut` liest das Original aus dem Archiv, ersetzt Felder und Positionen (`aktualisiere_beleg`).

## Aufgabe 8: CLI

**Tests:** `tests/test_cli_belege.py`

- [x] `belege abholen`/`import` erkennen standardmäßig; `--ohne-erkennung` schaltet ab.
- [x] (Akzeptanz 1, end-to-end) PDF im Watch-Ordner → `belege liste` zeigt Brutto und Status `erfasst`.
- [x] `belege erkennen` verarbeitet Belege im Status `eingegangen` und `pruefung` erneut.

## Abschluss

- [x] `pytest`, `ruff check`, `ruff format --check`, `mypy src/` grün.
- [x] `pypdf` in `pyproject.toml`; Tesseract als optionale Systemabhängigkeit im README.
- [x] README, Bauplan, Architektur, CHANGELOG nachziehen.
