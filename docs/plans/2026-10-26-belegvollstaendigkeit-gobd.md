# Belegvollständigkeit & Ordnungsmäßigkeit (Baustein 7) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** accounti sagt jederzeit, was der Buchhaltung fehlt und was daran nicht stimmt
(`accounti pruefen`), fordert fehlende Belege als Aufgabe an, die von selbst verstummt, sobald
der Beleg da ist (`accounti nachfordern`), und lässt Gebuchtes nicht mehr heimlich ändern: Jede
buchungsrelevante Änderung steht in einem hash-verketteten, nur anfügbaren Journal
(`accounti journal pruefen` findet Manipulationen), eine freigegebene Buchung wird nur noch per
Storno mit Neubuchung korrigiert, ein festgeschriebener Monat nimmt keine Buchung mehr an, und
die Verfahrensdokumentation entsteht aus dem tatsächlich eingerichteten Stand.

**Spec:** [`docs/specs/2026-08-10-belegvollstaendigkeit-gobd.md`](../specs/2026-08-10-belegvollstaendigkeit-gobd.md),
Abschnitte 4.1–4.7 · Akzeptanzkriterien 1–7 · **Baut auf:** Baustein 1 (Buchungssätze, `classify`,
Supervisor-Befehle), 2 (Belege, Archiv), 3 (E-Rechnung: Parser, `validierung`), 4 (Kontakte,
offene Posten, USt-IdNr.-Protokoll), 5 (`bank/abgleichslauf.offen_in_der_bank`, Bankkonten),
6 (Zahlungsläufe), 8 (`accounti.aufgaben`), 9 (`steuer/kennziffern`), 11 (`export/kontoauszuege`),
12 (Jahressperre, Abschlussprotokoll, Kontenrahmen)

```
 Belege · Umsätze · Buchungen · offene Posten · Kontoauszüge
        │
        ▼  accounti pruefen --period 2026-08         (liest nur)
 [1] PRÜFREGELN (Registry, Schwellen aus pruefung.regeln) ──▶ Befunde
     Vollständigkeit  umsatz_ohne_beleg · beleg_ohne_zahlung · nummernkreis_luecke ·
                      kontoauszug_luecke
     Richtigkeit      pflichtangaben (§ 14 Abs. 4 UStG / § 33 UStDV) · rechenprobe ·
                      steuerschluessel_konto · steuersatz_land · adressat · ig_erwerb_ustid ·
                      dublette
     Zeitgerechtheit  beleg_unbearbeitet · buchung_verspaetet · buchung_in_gesperrter_periode
     Ordnung          buchung_ohne_beleg · op_alter · periode_nicht_festgeschrieben
        │
        ▼  accounti nachfordern --period 2026-08
 [2] NACHFORDERUNG: Prüflauf „beleg_fehlt“ (ersetzt den eingebauten, Baustein 8) aus der Regel
     umsatz_ohne_beleg → Aufgabe mit Umsatz, Betrag, Gegenpartei, Zuständigkeit; Beleg da →
     hinfällig. Anfrage an den Lieferanten: Entwurf aus Vorlage, Versand nur auf Befehl.
        │
 [3] JOURNAL  journal (nur anfügen, SHA-256-Kette, SQLite-Trigger) ◀── ORM-Ereignisse
     (Session before_flush/after_flush) auf buchungssaetze, belege, beleg_eingaenge,
     zahlungslaeufe, abschluesse, periodenabschluesse + explizit: Export, Verfahrensdoku
        │
 [4] STORNO STATT ÄNDERUNG  freigegeben (auto/geprueft/korrigiert/exportiert) → nur Storno
     (Gegenbuchung, storno_von ↔ storniert_durch) + Neubuchung; ORM verweigert alles andere
        │
 [5] PERIODEN  periode schliessen 2026-08 → Monatssperre neben der Jahressperre (Baustein 12),
     gemeinsame Fehlerklasse, Öffnen nur mit Grund, Abschlussprotokoll + Journal
        │
 [6] VERFAHRENSDOKU  accounti verfahrensdoku --ausgabe … (Markdown, optional PDF), Hash im Journal
```

---

## Recherche (Stand 20.10.2026)

| Thema | Ergebnis | Quelle |
|-------|----------|--------|
| GoBD, Fassung | BMF-Schreiben vom 28.11.2019 (BStBl I S. 1269), geändert am 11.03.2024 (IV D 2 - S 0316/21/10001 :002, u. a. „Finanzbehörde“ statt „Finanzverwaltung“, Rz. 11) und am 14.07.2025 (IV D 2 - S 0316/00128/005/088, 2. Änderung wegen E-Rechnung: Rz. 76 bildhafte Kopie der Ausgangsrechnung entbehrlich, Rz. 118/119 bei E-Rechnungen genügt der strukturierte Teil, Rz. 121 Zahlungsnachweise, Rz. 185 neu: Anwendung ab 14.07.2025). Keine weitere Änderung gefunden. Die Randziffern zu Unveränderbarkeit, Belegen, Zeitgerechtheit und Verfahrensdokumentation sind durch die Änderungen nicht berührt | Änderungsschreiben 2024 als PDF vom BMF ([bundesfinanzministerium.de](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Weitere_Steuerthemen/Abgabenordnung/AO-Anwendungserlass/2024-03-11-aenderung-gobd.pdf?__blob=publicationFile&v=1)); 2. Änderung nach [KPMG](https://kpmg.com/de/de/themen/2025/07/bmf-gobd-zweite-aenderung.html), [IWW](https://www.iww.de/bbp/bilanzierung/bmf-schreiben-zweite-aenderung-der-gobd-aufgrund-gesetzlicher-anpassungen-n168278), [umwelt-online (Änderungstext)](https://umwelt-online.de/recht/allgemei/steuer/11032024.htm). Das Gesamt-PDF 2019 war am 20.10.2026 unter den bekannten BMF-Adressen nicht abrufbar (HTTP 404) |
| Unveränderbarkeit (Rz. 58, 59, 107–110) | Eine Buchung darf nicht so verändert werden, dass der ursprüngliche Inhalt nicht mehr feststellbar ist (Rz. 58, § 146 Abs. 4 AO); Veränderungen und Löschungen sind zu protokollieren (Rz. 59); einmal in den Verarbeitungsprozess eingeführte Informationen (Beleg, Grundaufzeichnung, Buchung) dürfen nicht ohne Kenntlichmachung überschrieben, gelöscht oder geändert werden (Rz. 107, 108); Mittel u. a. Sperren, Festschreibung, Protokollierung, Historisierung (Rz. 110) | [PSP, „Was bedeutet Unveränderbarkeit“](https://www.psp.eu/assets/pdfs/beitrag_expertenerlaeuterungen_gobd_unveraenderbarkeit_final.pdf) (zitiert die Rz. wörtlich), [§ 146 AO](https://www.gesetze-im-internet.de/ao_1977/__146.html) |
| Storno (Rz. 64) | Neufassung 2019: Korrektur- bzw. Stornobuchungen müssen auf die ursprüngliche Buchung rückbeziehbar sein | [Rödl & Partner zur Neufassung 2019](https://www.roedl.com/insights/2019-neufassung-bmf-buchfuehrung-details-aenderungen/) |
| Zeitgerechtheit (Rz. 47, 48, 50, 52) | unbare Vorfälle innerhalb von zehn Tagen erfassen ist unbedenklich (Rz. 47), Kasse täglich (Rz. 48), periodenweise Buchung bis Ablauf des Folgemonats, wenn vorher zeitnah grundaufgezeichnet (Rz. 50, 52) | Rödl & Partner (wie oben); Baustein 8 nutzt dieselben zehn Tage |
| Festschreibung | Die GoBD nennen keinen festen Tag; Praxis: spätestens mit der Umsatzsteuer-Voranmeldung bzw. bis Ablauf des Folgemonats (Rz. 50/52) | [DStV zum Entwurf 2018](https://dstv.de/download/2018-s14-entwurf-bmf-schreiben-neufassung-gobd), [NWB-Expertenblog](https://www.nwb-experten-blog.de/?p=7559) |
| Verfahrensdokumentation (Rz. 151–155) | Inhalt, Aufbau, Ablauf und Ergebnisse des Verfahrens vollständig ersichtlich; gegliedert in allgemeine Beschreibung, Anwender-, technische System- und Betriebsdokumentation; Änderungen versioniert und historisch nachvollziehbar (Rz. 154) | [PSP, „Verfahrensdokumentation“](https://www.psp.eu/assets/pdfs/beitrag_expertenerlaeuterungen_gobd_verfahrensdokumentation_final_.pdf), Rödl & Partner (Rz. 154) |
| § 14 Abs. 4 UStG | Pflichtangaben Nr. 1 Name/Anschrift Leistender und Empfänger, Nr. 2 Steuernummer oder USt-IdNr. des Leistenden, Nr. 3 Ausstellungsdatum, Nr. 4 fortlaufende Nummer, Nr. 5 Menge und Art, Nr. 6 Zeitpunkt der Leistung, Nr. 7 Entgelt nach Steuersätzen, Nr. 8 Steuersatz und Steuerbetrag bzw. Hinweis auf Befreiung, Nr. 9 Aufbewahrungshinweis (§ 14b), Nr. 10 „Gutschrift“ | [gesetze-im-internet.de, § 14 UStG](https://www.gesetze-im-internet.de/ustg_1980/__14.html) (abgerufen 20.10.2026) |
| § 33 UStDV (Kleinbetragsrechnung) | Gesamtbetrag bis **250 Euro**: vollständiger Name und Anschrift des Leistenden, Ausstellungsdatum, Menge und Art, Entgelt und Steuer in einer Summe, Steuersatz (bzw. Hinweis auf Befreiung); gilt nicht für §§ 3c, 6a, 13b UStG | [gesetze-im-internet.de, § 33 UStDV](https://www.gesetze-im-internet.de/ustdv_1980/__33.html) (abgerufen 20.10.2026) |
| § 14a Abs. 3 UStG, § 15 Abs. 1 UStG | Rechnung über eine ig. Lieferung trägt die USt-IdNr. des Lieferers und des Empfängers; Vorsteuer aus Rechnung setzt eine Rechnung nach §§ 14, 14a voraus (Nr. 1), die Erwerbsteuer ist nach Nr. 3 abziehbar | [§ 14a UStG](https://www.gesetze-im-internet.de/ustg_1980/__14a.html), [§ 15 UStG](https://www.gesetze-im-internet.de/ustg_1980/__15.html) |
| § 146 AO | Abs. 1: einzeln, vollständig, richtig, zeitgerecht, geordnet; Kasse täglich. Abs. 4: Veränderungsverbot | [§ 146 AO](https://www.gesetze-im-internet.de/ao_1977/__146.html) |

## Schnitt in Pakete

| Paket | Inhalt | Akzeptanz |
|-------|--------|-----------|
| **1 Journal & Storno** | Journal (Modell, Tabelle, Trigger, ORM-Ereignisse, Kette, Abgleich mit dem Bestand), `storniert_durch`/`storno_von`, Sperre freigegebener Buchungen, `korrigiere` neu (Fehler behoben), `bestaetige` als Freigabe, `buchung storniere|zeige`, Export setzt „exportiert“, `journal`, `journal pruefen|zeige|uebernehmen` | 5, 6 |
| **2 Perioden** | Monatssperre neben der Jahressperre, `periode schliessen|oeffnen|liste`, Sammelläufe überspringen gesperrte Monate | — |
| **3 Prüfregeln** | Registry, Konfiguration `pruefung`, Pflichtangaben aus dem Archiv, 17 Regeln, `accounti pruefen` | 1, 2, 3 |
| **4 Nachforderung** | Prüflauf `beleg_fehlt` aus der Regel, `accounti nachfordern`, Anfrage aus Vorlage | 4 |
| **5 Verfahrensdoku** | Generator (Markdown, PDF), Journal-Eintrag mit Hash, `accounti verfahrensdoku` | 7 |

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Ort | `src/accounti/pruefung/` (Regeln unter `pruefung/regeln/`), Tabellen `db/tabellen_pruefung.py`, Repository `db/repo_pruefung.py`, Modelle `models/pruefung.py`, Befehlsgruppen `befehle/{pruefen,nachfordern,journal,periode,verfahrensdoku,buchung}.py` | Dateiregeln; jede Befehlsgruppe ein Modul mit `NAME` und `befehl` |
| Freigegeben | wie im ganzen Projekt (`export`, `salden`, `kennziffern`): `auto`, `geprueft`, `korrigiert`, `exportiert`; Vorschlag: `entwurf`, `pruefung` | Spec 4.4: „ein Vorschlag ist noch keine Buchung“; eine automatisch gebuchte Buchung geht schon in Export, UStVA und Abschluss ein |
| Storno-Form | Gegenbuchung: Soll und Haben getauscht, Beträge und Steuerschlüssel unverändert positiv, Status `geprueft`, `storno_von` = Original; das Original bekommt `storniert_durch` und behält seinen Status. Neubuchung = Original mit den Korrekturen, Status `korrigiert`. Ein Datensatz `buchungskorrekturen` verbindet Original, Storno, Neubuchung, Grund, Person | Konvention des Projekts („Gutschrift: Seiten tauschen, Beträge positiv“): Salden, Kennziffern (Vorzeichen über die Sachkontoseite), OSS, BWA und DATEV-Export (Konto = Soll, Kennzeichen S) kehren sich so ohne Änderung um. Original und Storno heben sich auf, beide bleiben sichtbar (Spec 4.4, GoBD Rz. 64) |
| Storno-Grenzfall | Haben beide Seiten dieselbe Natur (beide Geld-/Personenkonto oder beide Sachkonto) **und** einen Steuerschlüssel, lehnt der Storno ab (`StornoError`) | `abschluss/salden.py` legt die Steuer dann nach dem Schlüssel auf die Soll-Seite — die getauschte Buchung höbe die Steuer nicht auf, sondern verdoppelte sie |
| Storno-Datum | Datum des Originals, wenn dessen Monat und Jahr offen sind; sonst muss `--datum` einen offenen Tag nennen (beide Buchungen bekommen ihn) | Korrektur nach Festschreibung in der laufenden Periode; keine stille Wahl |
| Sperre freigegebener Buchungen | `before_flush`: liest den gespeicherten Stand; erlaubt bei freigegebenen Buchungen nur `auto → geprueft` (mit `geprueft_von`), `auto/geprueft/korrigiert → exportiert` und das einmalige Setzen von `storniert_durch`; Löschen nie. Massen-`UPDATE`/`DELETE` über das ORM auf `buchungssaetze` werden abgelehnt (`do_orm_execute`), `repo_bank.loesche_buchung` löscht deshalb über `session.delete` | Akzeptanz 6 in der Datenbankschicht statt nur im Befehl; der bisherige Massen-Delete umging auch die Jahressperre |
| Unique | `storno_von` und `storniert_durch` eindeutig | eine Buchung wird höchstens einmal storniert — auch bei zwei Prozessen |
| `korrigiere` | Vorschlag: direkt (Status `korrigiert`, Journal „korrigiert“ und „freigegeben“). Freigegeben: Storno + Neubuchung. In beiden Fällen bleiben Transaktion, **Beleg, Belegposition, Belegnummer, Datum, Text und Betrag der Buchung** erhalten; mit `--steuer` werden Netto/Steuer aus dem **Brutto der Buchung** neu gerechnet, nicht aus dem Umsatz. `--steuer` bei Buchungen mit Beleg (Belegbuchung, Split, Ausgleich, Skonto) abgelehnt; ohne `--steuer` bleibt der Schlüssel (früher fiel er weg); `--ohne-steuer` entfernt ihn. Storno- und stornierte Buchungen werden nicht korrigiert | behebt: `zu_buchungssatz(tx)` setzte den ganzen Umsatzbetrag ein und verlor `beleg_id` (Belegbuchung, Ausgleich, Skonto, Split) |
| Person | `--von`, sonst `ACCOUNTI_BENUTZER`, sonst Anmeldename (wie `zahlung/freigabe.py`); im Journal aus dem Kontext (`journal_kontext`), bei Freigaben `geprueft_von` | Benutzer bringt Baustein 10; bis dahin Zeichenkette |
| Journal-Einhängung | Session-Ereignisse: `before_flush` liest den gespeicherten Stand geänderter/gelöschter Zeilen, `after_flush` liest den neuen Stand aus der Datenbank und hängt je Vorgang einen Eintrag an (über die Verbindung, in derselben Transaktion — ein Rollback nimmt beides zurück). Tabellen: `buchungssaetze`, `belege`, `beleg_eingaenge` (nur Dubletten = „verworfen“), `zahlungslaeufe`, `abschluesse`, `periodenabschluesse`. Explizit: Export, Verfahrensdoku, Bestandsübernahme, Anfrage an Lieferanten. Fehlt die Tabelle `journal` (alte Datenbank), wird nicht protokolliert und `journal pruefen` meldet es | zentral statt in jedem Befehl; jeder Weg über das ORM ist erfasst |
| Vorgänge | `buchung_angelegt`, `storno_gebucht`, `buchung_korrigiert`, `buchung_freigegeben`, `buchung_exportiert`, `buchung_storniert`, `buchung_geaendert`, `buchung_verworfen`, `beleg_importiert`, `beleg_verworfen`, `beleg_geaendert`, `zahlungslauf_<status>`, `jahr_abgeschlossen`/`jahr_geoeffnet`, `periode_geschlossen`/`periode_geoeffnet`, `export`, `verfahrensdoku_erstellt`, `bestand_uebernommen`, `beleg_angefordert` | Spec 4.3 vollständig plus Perioden |
| Journal-Eintrag | laufende Nummer, Zeitpunkt, Person, Vorgang, Objekt (Typ, ID), Vorher/Nachher als kanonisches JSON (alle Spalten, Beträge mit Spaltenskala, `zahlungslaeufe.datei` nur als Hash), Grund, Bezug, Vorgänger-Hash, Hash = SHA-256 über alles außer dem Hash | Muster `kontakte/ustid.py`; vorher/nachher aus der Datenbank, damit der spätere Abgleich exakt vergleicht |
| Unveränderbarkeit des Journals | ORM-Ereignis verweigert Ändern/Löschen (`UnveraenderbarError`); unter SQLite zusätzlich `BEFORE UPDATE/DELETE`-Trigger per `after_create`; Postgres: `pg_advisory_xact_lock` beim Anfügen (Nummernvergabe), sonst Kette + Abgleich | wie `ustid_pruefungen`, `abschlussprotokoll` |
| `journal pruefen` | Kette (Lücken, Vorgänger-Hash, Hash), optional Anker `--kopf NR:HASH`, **Abgleich mit dem Bestand**: jede Buchung und jeder Beleg muss dem letzten Nachher-Stand im Journal entsprechen; Buchung ohne Eintrag, verschwundene Buchung, an accounti vorbei geänderte Felder werden gemeldet. Ausgabe nennt den Kopf (Nr., Hash) zum Notieren | eine abgeschnittene Kette (letzte Einträge gelöscht) fällt nur so auf |
| Bestand vor dem Journal | `journal uebernehmen` trägt Buchungen und Belege ohne Eintrag einmal als `bestand_uebernommen` ein | ältere Datenbanken |
| Perioden | Tabelle `periodenabschluesse` (Monat, gesperrt, Zeitpunkte, Personen, Grund). ORM-Ereignis auf `buchungssaetze` wie die Jahressperre; `PeriodeGesperrtError(JahrGesperrtError)` — alle vorhandenen Fänger der Jahressperre (Kasse, Anlagen, `opos verbuchen`, Abschluss) behandeln die Monatssperre mit. Die Jahressperre bleibt, wie sie ist (Saldovortrag), und erlaubt jetzt wie die Monatssperre das Setzen von `storniert_durch`. `offene_transaktionen` überspringt gesperrte Monate. Schließen verlangt: keine Vorschläge im Monat; ungebuchte Umsätze nur mit `--trotzdem`. Öffnen nur mit Grund und nur, wenn das Jahr offen ist. Jede Aktion: Abschlussprotokoll (`protokolliere`, Hash-Kette aus Baustein 12) und Journal | „baue nichts doppelt“: dieselbe Fehlerklasse, dasselbe Protokoll, ein gemeinsames Abfrage-API (`pruefung.perioden.sperre_am`) |
| Prüfregel | Klasse mit `name`, `kategorie`, `schwere`, `beschreibung`, `Parameter` (Pydantic-Modell mit Standardwerten) und `pruefe(kontext) -> list[Befund]`; Registry `PRUEFREGELN`, `registriere_pruefregel`; ändert nie Daten (Test: Datenbank vor/nach identisch) | Spec 4.1, Architektur „Neue Prüfregel hinzufügen“ |
| Befund | Regel, Kategorie, Schwere (`hinweis`, `warnung`, `fehler`), Objekt (Typ, ID), Datum, Betrag, Gegenpartei, Begründung, Abhilfe | Akzeptanz 1 verlangt Betrag, Datum, Gegenpartei |
| Konfiguration | Abschnitt `pruefung` mit Lader `lade_pruefung`: `abgeschaltet`, `schwere` (je Regel), `regeln.<name>` (Schwellen, nur Abweichungen), `belegfrei` (Muster mit Begründung), `kleinbetrag_grenze` (250), `eigene_namen`, `kontenrahmen_datei`, `archiv`, `nachforderung` (Vorlage). Unbekannte Regel → `KonfigurationError` beim Lauf | Spec 4.1: Schwellen ohne Code ändern |
| Pflichtangaben-Quelle | E-Rechnung (XML/ZUGFeRD aus dem Archiv) → Rechnungsmodell; PDF mit Textebene/Text → Regex (Steuernummer, USt-IdNr., Anschrift, eigener Name); Scan ohne Text → nur mit `--ocr`, sonst Hinweis „nicht prüfbar“; ohne Archiv → nur gespeicherte Felder, Steuernummer gilt dann als „nicht erkannt“ (Warnung statt Fehler) | Beleg speichert keine Steuernummer und keinen Empfänger; `models/__init__.py` darf nur die Storno-Felder bekommen |
| Kleinbetrag | Brutto ≤ `kleinbetrag_grenze` (250 €): nur § 33 UStDV (keine Steuernummer, kein Empfänger, keine Nummer) | § 33 UStDV seit 01.01.2017 |
| Steuerschlüssel ./. Konto | Sachkontoseite = die Seite, die kein Geld-/Personenkonto ist (`kennziffern.Kontenplan`). Fehler: Vorsteuerschlüssel auf Erlöskonto, USt-Schlüssel auf Aufwandskonto, Schlüssel auf Konto mit fester Steuerfunktion (8125 …), Automatikkonto aus `config/skr03.yaml` mit anderem Schlüssel. Warnung: Automatikkonto ohne Schlüssel, Schlüssel auf Konto ohne Vorsteuerabzug laut Kontenrahmen (Gehälter, Versicherungen …). SKR04 ohne Automatikdatei: nur Bereichsregeln | Akzeptanz 3; nutzt Steuerautomatik, Kennziffern-Bereiche und Kontenrahmen |
| Nachforderung | `accounti.pruefung.aufgaben_anbindung` ersetzt den eingebauten Prüflauf `beleg_fehlt` (wie in Architektur/Bauplan vorgesehen): Anlässe des eingebauten Laufs **geschnitten** mit den Befunden der Regel `umsatz_ohne_beleg` (Schwellen, `belegfrei`-Muster); belegfrei nach Regel → Grund „belegfrei nach Regel …“. Merkmale `befund`, `schwere` zusätzlich | nur ein Erzeuger je Art (Baustein 8); ohne `belegfrei`-Regeln verhält sich der Lauf wie bisher (bestehende Tests) |
| Anfrage an Lieferanten | `nachfordern anfrage TX` zeigt den Entwurf aus der Vorlage (`pruefung.nachforderung`); `--senden` verschickt **diese eine** Anfrage über den SMTP-Zugang aus `versand`, Kommentar an der Aufgabe, Journal `beleg_angefordert`. Kein Lauf verschickt etwas | Spec 4.2: Nachrichten an Dritte sind Entscheidung des Betriebs |
| Verfahrensdoku | aus dem Systemzustand: Mandant, Kontenrahmen, Gewinnermittlung, Belegkanäle (Postfächer, Webhook, Connectoren — ohne Geheimnisse), OCR/LLM (Modell, opt-in), Bankkonten mit Provider/Zustand, Kontierungsregeln, Auto-Schwelle, Freigabe/Storno, Vier-Augen, Rollen, Zuständigkeit, Prüfregeln mit Schwellen, Perioden, Aufbewahrung, Journal-Kopf, Protokolle; gegliedert nach GoBD Rz. 151 ff.; Stand-Datum; Hash und Historie über das Journal (Rz. 154); PDF mit fpdf2 (Liberation Sans aus `erechnung/schriften`) | Akzeptanz 7 |
| Export | `export datev` und `datev belege` setzen nach dem Schreiben die exportierten **freigegebenen** Buchungen auf `exportiert` und schreiben einen Journal-Eintrag `export` (Datei, SHA-256, Anzahl) | Spec 4.3 „exportiert“; vorher setzte niemand den Status |
| Keine Migration | Tabellen und Spalten entstehen mit `init_db`; Alembic beim Zusammenführen | Dateiregeln |

## Aufgaben

### Paket 1 — Journal & Storno

- [ ] **Modelle** (`models/pruefung.py`, `models/__init__.py`): `Journaleintrag`, `Buchungskorrektur`; `Buchungssatz.storniert_durch`, `storno_von`.
- [ ] **Tabellen** (`db/tabellen_pruefung.py`, `db/tabellen.py`): `journal`, `buchungskorrekturen` (nur anfügen, ORM + SQLite-Trigger), Spalten am Buchungssatz (eindeutig); Repository (`db/repo_pruefung.py`, Mapping in `db/repository.py`).
- [ ] **Journal** (`pruefung/journal.py`): kanonischer Schnappschuss, Hash, Anfügen mit Kette, `pruefe_journal` (Kette, Anker, Bestand), `uebernehme_bestand` (`tests/test_pruefung_journal.py`).
- [ ] **Ereignisse** (`pruefung/ereignisse.py`): Vorgänge aus ORM-Änderungen, Sperre freigegebener Buchungen, Massen-Änderungen abgelehnt (`tests/test_pruefung_ereignisse.py`).
- [ ] **Storno** (`pruefung/storno.py`): `storniere`, `korrigiere` (Vorschlag direkt / freigegeben per Storno), `freigeben`, `markiere_exportiert`; je ein Test mit Bank-, Beleg-, Ausgleichs-, Skonto- und Splitbuchung (`tests/test_pruefung_storno.py`).
- [ ] **CLI:** `korrigiere`, `bestaetige`, `review` umgebaut; `export datev`/`datev belege` markieren; `buchung storniere|zeige`; `journal [--von --bis --objekt --vorgang]`, `journal zeige NR`, `journal pruefen [--kopf]`, `journal uebernehmen` (`tests/test_cli_journal_storno.py`).
- [ ] **Akzeptanz 5 und 6** als Tests.

### Paket 2 — Perioden

- [ ] **Tabelle und Sperre** (`periodenabschluesse`, Ereignis auf `buchungssaetze`, `PeriodeGesperrtError`), Storno-Vermerk in gesperrten Zeiträumen erlaubt (auch Jahressperre).
- [ ] **`pruefung/perioden.py`:** `schliesse`, `oeffne`, `sperre_am`, `lade_perioden`; Protokoll + Journal; Sammelläufe (`offene_transaktionen`) (`tests/test_pruefung_perioden.py`).
- [ ] **CLI:** `periode schliessen|oeffnen|liste` (`tests/test_cli_periode.py`).

### Paket 3 — Prüfregeln

- [ ] **Registry, Kontext, Befund, Konfiguration** (`pruefung/regeln/__init__.py`, `pruefung/einstellungen.py`) (`tests/test_pruefung_regeln_basis.py`).
- [ ] **Pflichtangaben-Quelle** (`pruefung/belegangaben.py`) (`tests/test_pruefung_belegangaben.py`).
- [ ] **Vollständigkeit** — je Regel auslösend und nicht auslösend (`tests/test_pruefung_vollstaendigkeit.py`).
- [ ] **Richtigkeit** (`tests/test_pruefung_richtigkeit.py`).
- [ ] **Zeitgerechtheit und Ordnung** (`tests/test_pruefung_zeit_ordnung.py`).
- [ ] **CLI** `accounti pruefen [--period] [--regel] [--stichtag] [--archiv] [--ocr]`, Exit 1 bei Fehler-Befunden (`tests/test_cli_pruefen.py`).

### Paket 4 — Nachforderung

- [ ] **Prüflauf** (`pruefung/nachforderung.py`, `pruefung/aufgaben_anbindung.py`), Anfrage aus Vorlage, Versand nur auf Befehl (`tests/test_pruefung_nachforderung.py`); `test_aufgaben_anbindung.py` erwartet jetzt die Anbindung von Baustein 7.
- [ ] **CLI** `accounti nachfordern [--period]`, `nachfordern anfrage TX [--an] [--senden]` (`tests/test_cli_nachfordern.py`).

### Paket 5 — Verfahrensdokumentation & Abschluss

- [ ] **Generator** (`pruefung/verfahrensdoku.py`), Markdown + PDF, Journal-Eintrag (`tests/test_pruefung_verfahrensdoku.py`).
- [ ] **CLI** `accounti verfahrensdoku --ausgabe … [--pdf …]`.
- [ ] **Abschluss:** `pytest`, `ruff` (ohne Cache), `mypy` grün; Checkboxen abgehakt; Doku-Bausteine vollständig; gegnerische Selbstprüfung.

## Akzeptanzkriterien → Tests

| # | Kriterium | Tests |
|---|-----------|-------|
| 1 | Zahlung ohne Beleg erscheint als Befund mit Betrag, Datum, Gegenpartei | (wird ergänzt) |
| 2 | Rechnung ohne Steuernummer → unvollständig nach § 14 UStG | (wird ergänzt) |
| 3 | Steuerschlüssel passt nicht zum Sachkonto → erkannt | (wird ergänzt) |
| 4 | Befund → Aufgabe, die verstummt, sobald der Beleg eintrifft | (wird ergänzt) |
| 5 | Manipulierter Journaleintrag → `journal pruefen` findet ihn | (wird ergänzt) |
| 6 | Freigegebene Buchung nur per Storno korrigierbar, beide sichtbar | (wird ergänzt) |
| 7 | Verfahrensdoku beschreibt den eingerichteten Stand | (wird ergänzt) |

## Grenzen

(wird mit der Umsetzung gefüllt)

## Doku-Bausteine

(wird mit der Umsetzung gefüllt)
