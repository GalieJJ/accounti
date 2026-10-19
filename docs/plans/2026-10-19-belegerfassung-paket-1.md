# Belegerfassung, Paket 1 — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Ein Beleg kommt über Watch-Ordner oder CLI-Upload ins System, wird unverändert und
content-adressiert archiviert, gegen den Bestand auf Dubletten geprüft und als `Beleg` gespeichert.
Jeder Eingang — auch eine verworfene Dublette — steht im Eingangsprotokoll.

**Spec:** [`docs/specs/2026-08-10-belegerfassung.md`](../specs/2026-08-10-belegerfassung.md)

**Architektur:** `Kanal → RohBeleg → Archiv → Dublettenprüfung → Beleg + BelegEingang`.
Kanäle kennen nur Datei und Herkunft (Registry `BELEG_KANAELE`, analog `BANK_IMPORTERS`). Die
Erkennung (Paket 2) hängt sich als optionaler `erkenner` in die Pipeline; schlägt sie fehl, geht der
Beleg mit Begründung in „zur Prüfung", die Pipeline läuft weiter.

---

## Schnitt: was Paket 1 umfasst

| Spec-Abschnitt | Paket 1 | Später |
|----------------|---------|--------|
| 4.1 Kanäle | `ordner`, `upload` | `email` (Paket 3), `webhook`, `connector` (mit Baustein 10/11) |
| 4.2 Erkennung | Schnittstelle `erkenner` in der Pipeline | Format-/Belegarterkennung (Paket 2) |
| 4.3 OCR | — | Paket 2 |
| 4.4 Positionssplit | Datenmodell `Belegposition` | Split-Logik, Kreditkartenabrechnung (Paket 2) |
| 4.5 Dubletten | alle drei Stufen | — |
| 4.6 Archiv | vollständig | — |
| 4.7 Datenmodell | `Beleg`, `Belegposition`, `Buchungssatz.beleg_position_id` | `Kontakt` (Baustein 4) |
| 4.8 CLI | `kanaele`, `import`, `abholen --kanal ordner`, `liste` | `abholen --kanal email` |

Bis `Kontakt` aus Baustein 4 existiert, trägt `Beleg` zusätzlich `lieferant_name` und
`lieferant_ust_id` als Freitext — die Dublettenstufen 2 und 3 brauchen einen Lieferanten.

## Dateistruktur

| Pfad | Verantwortung |
|------|---------------|
| `src/accounti/models/__init__.py` | Enums `Belegart`, `Belegrichtung`, `BelegStatus`, `Eingangsergebnis`; Modelle `Beleg`, `Belegposition`, `BelegEingang`; `Buchungssatz.beleg_position_id` |
| `src/accounti/db/tabellen.py` | `BelegRow`, `BelegpositionRow`, `BelegEingangRow`; Spalte `beleg_position_id` |
| `alembic/versions/…_add_belege.py` | Migration der neuen Tabellen und Spalte |
| `src/accounti/db/repository.py` | `speichere_beleg`, `lade_belege`, `speichere_eingang`, `lade_eingaenge` |
| `src/accounti/belege/kanaele/__init__.py` | `RohBeleg`, `BelegKanal`, `BELEG_KANAELE` |
| `src/accounti/belege/kanaele/ordner.py` | Watch-Ordner; verarbeitete Dateien wandern nach `verarbeitet/` |
| `src/accounti/belege/kanaele/upload.py` | Einzeldateien von der CLI |
| `src/accounti/belege/archiv.py` | `BelegArchiv` (SHA-256, schreibgeschützt, kein Löschpfad), `aufbewahrungsende` |
| `src/accounti/belege/dubletten.py` | `pruefe_dublette` — drei Stufen, reine Funktion |
| `src/accounti/belege/pipeline.py` | `nimm_auf` — verbindet Archiv, Dubletten, Erkenner, Persistenz |
| `src/accounti/cli.py` | Befehlsgruppe `belege` |

---

## Aufgabe 1: Datenmodell

**Tests:** `tests/test_belege_modell.py`

- [x] Test: `Beleg` mit Defaults anlegen (Status `eingegangen`, Belegart `unbekannt`, Richtung `eingang`, leere Positionen).
- [x] Test: `Buchungssatz` akzeptiert `beleg_position_id`, Default `None`.
- [x] Enums und Modelle in `models/__init__.py` ergänzen. Status: `eingegangen` (archiviert, noch nicht gelesen), `pruefung` (Mensch muss ran, `pruef_grund` gesetzt), `erfasst` (strukturiert).

## Aufgabe 2: Persistenz

**Tests:** `tests/test_belege_repository.py`

- [x] Test: Roundtrip `Beleg` mit zwei Positionen (Decimal-Beträge bleiben exakt).
- [x] Test: Roundtrip `BelegEingang`, Filter nach Status in `lade_belege`.
- [x] Test: `Buchungssatz.beleg_position_id` übersteht den Roundtrip.
- [x] Tabellen, Repository-Funktionen, Alembic-Migration. Migration gegen frische SQLite-DB mit `alembic upgrade head` prüfen, danach `alembic check` (kein Drift).

## Aufgabe 3: Archiv

**Tests:** `tests/test_belege_archiv.py`

- [x] Test: Ablegen liefert SHA-256, Datei liegt unter `<wurzel>/<h[:2]>/<h[2:4]>/<h><endung>` mit identischen Bytes.
- [x] Test: Zweites Ablegen derselben Bytes ist idempotent und überschreibt nicht.
- [x] Test: Abgelegte Datei ist schreibgeschützt; das Archiv hat keine Löschmethode.
- [x] Test: `aufbewahrungsende(date(2026, 3, 5)) == date(2036, 12, 31)` (§ 147 Abs. 4 AO: Frist beginnt mit Schluss des Kalenderjahres).

## Aufgabe 4: Dublettenprüfung

**Tests:** `tests/test_belege_dubletten.py` — je Stufe ein eigener Fall

- [x] Stufe 1: gleicher `datei_hash` → `dublette`.
- [x] Stufe 2: gleicher Lieferant (normalisiert, USt-IdNr. bevorzugt) + gleiche Belegnummer, anderer Hash → `dublette`.
- [x] Stufe 3: gleicher Lieferant + gleicher Bruttobetrag + Belegdatum ±3 Tage → `verdacht`.
- [x] Gegenprobe: fehlende Felder lösen Stufe 2/3 nicht aus; anderer Lieferant → `neu`.

## Aufgabe 5: Kanäle

**Tests:** `tests/test_belege_kanaele.py`

- [x] Test: `BELEG_KANAELE` enthält `ordner` und `upload`, jeder mit Beschreibung.
- [x] Test: `OrdnerKanal` liefert alle regulären Dateien (keine versteckten, keine Unterordner) als `RohBeleg` mit Kanal und Herkunft.
- [x] Test: Nach `bestaetige()` liegt die Datei in `verarbeitet/` und wird beim nächsten Abholen nicht mehr geliefert.
- [x] Test: `UploadKanal` liefert genau die übergebenen Dateien und fasst sie nicht an.

## Aufgabe 6: Pipeline

**Tests:** `tests/test_belege_pipeline.py`

- [x] Test: Neuer Beleg → archiviert, `Beleg` gespeichert, Eingang `neu`.
- [x] Test (Akzeptanz 3): dieselbe Datei über `ordner` und `upload` → genau ein `Beleg`, zweiter Eingang `dublette` mit Verweis auf den ersten.
- [x] Test: Verdacht → `Beleg` gespeichert mit Status `pruefung` und Begründung.
- [x] Test (Akzeptanz 5): Erkenner wirft eine Ausnahme → Beleg im Status `pruefung` mit Begründung, keine Ausnahme nach außen.
- [x] Test (Akzeptanz 6): Originaldatei ist nach dem Import unverändert im Archiv.

## Aufgabe 7: CLI

**Tests:** `tests/test_cli_belege.py`

- [x] `accounti belege kanaele` listet Kanäle.
- [x] `accounti belege import <datei>…` meldet neu/Dublette je Datei.
- [x] `accounti belege abholen --kanal ordner --ordner <pfad>` leert den Ordner einmal.
- [x] `accounti belege liste [--status …]` zeigt eine Tabelle.

## Abschluss

- [x] `pytest`, `ruff check`, `ruff format --check`, `mypy src/` grün.
- [x] End-to-end von Hand: PDF in Watch-Ordner → `belege abholen` → `belege liste` zeigt den Beleg; dieselbe Datei per `belege import` → als Dublette gemeldet.
- [x] README-Featureliste, Bauplan-Status (🟨 für Baustein 2) und CHANGELOG nachziehen.
