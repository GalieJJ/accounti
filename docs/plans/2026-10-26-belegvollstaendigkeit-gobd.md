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
     zahlungslaeufe, zahlungslauf_protokoll, abschlussprotokoll + explizit: Export,
     Verfahrensdoku; Abgleich der Sperrtabellen in journal pruefen
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
| Storno-Form | Gegenbuchung: Soll und Haben getauscht, Beträge und Steuerschlüssel unverändert positiv, Status `geprueft`, `storno_von` = Original; das Original bekommt `storniert_durch` und behält seinen Status. Neubuchung = Original mit den Korrekturen, Status `korrigiert`. Ein Datensatz `buchungskorrekturen` verbindet Original, Storno, Neubuchung, Grund, Person. Im DATEV-Export tragen Original und Storno in Belegfeld 2 `ST` + die ersten acht Zeichen der Original-ID | Konvention des Projekts („Gutschrift: Seiten tauschen, Beträge positiv“): Salden, Kennziffern (Vorzeichen über die Sachkontoseite), OSS und DATEV-Export (Konto = Soll, Kennzeichen S) kehren sich so ohne Änderung um — die BWA nicht: `bwa/berechnung.py` (derzeit von keinem Befehl genutzt) summiert beide Seiten positiv (Grenze). Original und Storno heben sich auf, beide bleiben sichtbar und sind aufeinander rückbeziehbar (Spec 4.4, GoBD Rz. 64) |
| Storno-Grenzfall | Haben beide Seiten dieselbe Natur (beide Geld-/Personenkonto oder beide Sachkonto) **und** einen Steuerschlüssel, lehnt der Storno ab (`StornoError`) | `abschluss/salden.py` legt die Steuer dann nach dem Schlüssel auf die Soll-Seite — die getauschte Buchung höbe die Steuer nicht auf, sondern verdoppelte sie |
| Storno-Datum | Datum des Originals, wenn dessen Monat und Jahr offen sind; sonst muss `--datum` einen offenen Tag nennen (beide Buchungen bekommen ihn). Liegt der Tag in einem anderen Monat und hat die Buchung einen Steuerschlüssel, warnt accounti: Die Umsatzsteuer ändert sich im Zeitraum des Stornos, der Originalzeitraum braucht gegebenenfalls eine berichtigte Voranmeldung | Korrektur nach Festschreibung in der laufenden Periode; keine stille Wahl |
| Sperre freigegebener Buchungen | `before_flush`: liest den gespeicherten Stand **aus der Datenbank** (nie aus der Attribut-Historie, die nach `commit` leer ist) und prüft damit Jahres- und Monatssperre (gespeichertes und neues Datum) und die Storno-Regel — auch im gesperrten Zeitraum; erlaubt bei freigegebenen Buchungen nur `auto → geprueft` (mit `geprueft_von`), `auto/geprueft/korrigiert → exportiert` und das einmalige Setzen von `storniert_durch`, das auf eine Stornobuchung mit `storno_von` zeigen muss; Löschen nie. Der Primärschlüssel erfasster Zeilen ändert sich nie. `datum` und `storniert_durch` haben zusätzlich `active_history`, damit auch die Mapper-Sperre das alte Datum kennt. Massen-`INSERT`/`UPDATE`/`DELETE` über die Sitzung (ORM und Core-DML) auf `buchungssaetze`, `journal`, `buchungskorrekturen` werden abgelehnt (`do_orm_execute`), die alten `bulk_*`-Wege sperrt die Sitzungsklasse `AccountiSitzung` aus `session_factory`; `repo_bank.loesche_buchung` löscht über `session.delete` | Akzeptanz 6 in der Datenbankschicht statt nur im Befehl; der bisherige Massen-Delete umging auch die Jahressperre |
| Unique | `storno_von` und `storniert_durch` eindeutig | eine Buchung wird höchstens einmal storniert — auch bei zwei Prozessen |
| `korrigiere` | Vorschlag: direkt (Status `korrigiert`, Journal „korrigiert“ und „freigegeben“). Freigegeben: Storno + Neubuchung. In beiden Fällen bleiben Transaktion, **Beleg, Belegposition, Belegnummer, Datum, Text und Betrag der Buchung** erhalten; mit `--steuer` werden Netto/Steuer aus dem **Brutto der Buchung** neu gerechnet, nicht aus dem Umsatz. **Ändert sich das Sachkonto** (die Seite, die kein Geld-/Personenkonto ist) einer Buchung mit Schlüssel, muss `--steuer` (bestätigen oder ändern) oder `--ohne-steuer` angegeben werden; bleibt das Sachkonto (nur das Geldkonto wechselt), bleibt der Schlüssel. Eine Kombination, die die Regel `steuerschluessel_konto` als Fehler einstuft, wird abgelehnt. `--steuer` mit anderem Schlüssel bei Buchungen mit Beleg (Belegbuchung, Split, Ausgleich, Skonto) abgelehnt; `--ohne-steuer` dort nicht für ausgewiesene Umsatzsteuer (Schlüssel 2, 3) und nur mit `--grund` (steht im Journal) — ausgewiesene Umsatzsteuer wird geschuldet, bis die Rechnung berichtigt ist (§ 14c Abs. 1 UStG), die Berichtigung ist ein neuer Beleg. Ein DATEV-Automatikkonto ohne Schlüssel lehnt `korrigiere` ab (DATEV rechnete trotzdem Steuer heraus). Geprüft wird mit der Kontenrahmen-Datei der Konfiguration (`pruefung.kontenrahmen_datei`). `--lernen` lernt den Schlüssel der Neubuchung (bei neuem Sachkonto ausdrücklich angegeben, sonst der des unveränderten Sachkontos). Storno- und stornierte Buchungen werden nicht korrigiert | behebt: `zu_buchungssatz(tx)` setzte den ganzen Umsatzbetrag ein und verlor `beleg_id` (Belegbuchung, Ausgleich, Skonto, Split); ein still mitgenommener Schlüssel ergab Vorsteuer auf Versicherung (4360), Privatentnahme (1800) oder Umsatzsteuer auf eine Auszahlung (1200 an 1361) |
| Person | Ohne Benutzer: `--von`, sonst `ACCOUNTI_BENUTZER`, sonst Anmeldename (wie `zahlung/freigabe.py`). Mit Benutzern (Baustein 10a): `befehle.handelnde_person` prüft Recht und Einmalcode und setzt den Benutzer geprüft in `journal_kontext` (`geprueft=True`), `geprueft_von` und das Protokoll; API-Token stehen geprüft als „API-Token <Name>“ im Journal; jede andere Person steht als „… (ungeprüft)“ im Journal, sobald die Datenbank zu einer Benutzerverwaltung gehört (Merker oder eigene Benutzer) | Freitext beweist nichts, der zweite Faktor schon — und das Journal unterscheidet beides |
| Rechte (Verzahnung 10a, Liste `models.auth.FREIGABEWEGE`) | `BUCHEN` (buchhalter): `korrigiere`, `buchung storniere`, `kasse buchen|anfangsbestand|storno`, `abschluss eroeffnung`, `bank bestaetigen|ablehnen`, `nachfordern anfrage --senden`. `BUCHUNG_FREIGEBEN` (buchhalter, freigeber): `bestaetige`, `opos bestaetigen|ablehnen`, `abschluss bestaetigen|ablehnen`, `periode schliessen`, `abschluss vortrag`, `export datev`, `datev belege`. `STEUER_FREIGEBEN` (freigeber): `periode oeffnen`, `abschluss oeffnen`. `VERWALTEN` (verwalter): `journal uebernehmen`. `review` zeigt nur an (kein Recht) | Erfassen und Korrigieren (auch mit sofort freigegebener Buchung) ist Buchen — jede Rolle mit `BUCHEN` hat auch `BUCHUNG_FREIGEBEN` (Test `test_buchen_umfasst_die_freigabe`), eine zweite Prüfung verlangte einen zweiten Einmalcode. Einen Vorschlag zur freigegebenen Buchung machen (Status geprueft) ist Freigeben; Beleg und Umsatz zuordnen (noch keine Buchung) ist Buchen. Festschreiben und Vortrag schützen nur — Freigabe; der Export ist die Übergabe an den Steuerberater und setzt den Vermerk „exportiert“ — Freigabe (`LAEUFE_STARTEN` hat nur der buchhalter, ein freigeber soll übergeben können). Die Festschreibung aufheben ist Funktionstrennung (GoBD Rz. 100–102) und zieht meist eine berichtigte Voranmeldung nach sich — nur, wer Steuermeldungen freigibt. Die Bestandsübernahme ist ein Schritt des Betriebs beim Upgrade, kein Buchhaltungsvorgang — verwalten, und nur, solange das Journal außer Übernahmen leer ist. Senden an Lieferanten ist Buchhaltungsarbeit — buchen |
| Journal-Einhängung | Session-Ereignisse, eingehängt von `session_factory`/`init_db` (`accounti.db.registriere_ereignisse`), nicht durch einen Import: `before_flush` liest den gespeicherten Stand geänderter/gelöschter Zeilen, `after_flush` liest den neuen Stand immer aus der Datenbank und hängt je Vorgang einen Eintrag an (über die Verbindung, in derselben Transaktion — ein Rollback nimmt beides zurück). Tabellen: `buchungssaetze`, `belege`, `beleg_eingaenge` (nur Dubletten = „verworfen“), `zahlungslaeufe` (Anlage), `zahlungslauf_protokoll` (Statuswechsel), `abschlussprotokoll` (Jahres- und Monatsabschlüsse) — die Sperrtabellen `abschluesse`/`periodenabschluesse` selbst gleicht `journal pruefen` ab. Explizit: Export, Verfahrensdoku, Bestandsübernahme, Anfrage an Lieferanten. Fehlt die Tabelle `journal` (alte Datenbank), wird nicht protokolliert und `journal pruefen` meldet es. Sperren werden je Flush einmal gelesen. **Vor dem Lesen** holt jeder Flush und jedes `schreibe` die Schreibsperre der Transaktion (`journal.schreibsperre`: SQLite ein UPDATE ohne Treffer = RESERVED-Sperre, PostgreSQL die Advisory-Sperre der Nummernvergabe) — Prüfung, Nummernvergabe und Schreiben sind atomar gegenüber anderen accounti-Schreibern; die Mapper-Sperre überspringt nur Zeilen, die `before_flush` unter dieser Sperre geprüft hat | zentral statt in jedem Befehl; jeder Weg über eine Sitzung aus `session_factory` ist erfasst (Grenzen: rohes SQL, Sitzungen an `session_factory` vorbei) |
| Vorgänge | `buchung_angelegt`, `storno_gebucht`, `buchung_korrigiert`, `buchung_freigegeben`, `buchung_exportiert`, `buchung_storniert`, `buchung_geaendert`, `buchung_verworfen`, `beleg_importiert`, `beleg_verworfen`, `beleg_geaendert`, `zahlungslauf_<status>`, `jahr_abgeschlossen`/`jahr_geoeffnet`, `periode_geschlossen`/`periode_geoeffnet`, `export`, `verfahrensdoku_erstellt`, `bestand_uebernommen`, `sperre_uebernommen`, `beleg_angefordert`. Löschen und Neuanlegen derselben ID in einem Flush ist eine Änderung | Spec 4.3 vollständig plus Perioden |
| Journal-Eintrag | laufende Nummer, Zeitpunkt, Person, Vorgang, Objekt (Typ, ID), Vorher/Nachher als kanonisches JSON (alle Spalten, Beträge mit Spaltenskala; `zahlungslaeufe` ohne die erzeugte Datei `datei` und ohne `version`), Grund, Bezug, Vorgänger-Hash, Hash = SHA-256 über alles außer dem Hash | Muster `kontakte/ustid.py`; vorher/nachher aus der Datenbank, damit der spätere Abgleich exakt vergleicht |
| Unveränderbarkeit des Journals | ORM-Ereignis verweigert Ändern/Löschen (`UnveraenderbarError`); unter SQLite zusätzlich `BEFORE UPDATE/DELETE`-Trigger per `after_create`; Postgres: `pg_advisory_xact_lock` beim Anfügen (Nummernvergabe), sonst Kette + Abgleich | wie `ustid_pruefungen`, `abschlussprotokoll` |
| `journal pruefen` | Kette (Lücken, Vorgänger-Hash, Hash), optional Anker `--kopf NR:HASH`, **Verlauf je Objekt** (der Vorher-Stand eines Eintrags ist der letzte Nachher-Stand; Einträge eines Flushs mit gleichem Paar zählen als ein Übergang), **Abgleich mit dem Bestand**: jede Buchung und jeder Beleg muss dem letzten Nachher-Stand im Journal entsprechen; Buchung ohne Eintrag, verschwundene Buchung, an accounti vorbei geänderte Felder, Stornovermerk ohne zurückzeigende Stornobuchung werden gemeldet. Journal und Bestand werden aus einem Stand gelesen (`journal.lesestand`: SQLite eine Lesetransaktion, PostgreSQL die Schreibsperre), Felder, die in alten Einträgen fehlen (neue Spalte), zählen als `None`. Ausgabe nennt den Kopf (Nr., Hash) zum Notieren | eine abgeschnittene Kette (letzte Einträge gelöscht) fällt nur über den Bestand auf; eine an accounti vorbei geänderte und danach regulär weiterbearbeitete Zeile („gewaschen“) nur über den Verlauf |
| Bestand vor dem Journal | `journal uebernehmen` trägt Buchungen und Belege ohne Eintrag einmal als `bestand_uebernommen` ein, gesperrte Jahre und Monate ohne Sperrvorgang im Journal als `sperre_uebernommen` | ältere Datenbanken: sonst meldete `journal pruefen` jedes vor dem Journal abgeschlossene Jahr als „an accounti vorbei gesperrt“ |
| Perioden | Tabelle `periodenabschluesse` (Monat, gesperrt, Zeitpunkte, Personen, Grund). ORM-Ereignis auf `buchungssaetze` wie die Jahressperre; `PeriodeGesperrtError(JahrGesperrtError)` — alle vorhandenen Fänger der Jahressperre (Kasse, Anlagen, `opos verbuchen`, Abschluss) behandeln die Monatssperre mit. Die Jahressperre bleibt, wie sie ist (Saldovortrag), und erlaubt jetzt wie die Monatssperre das Setzen von `storniert_durch`. `offene_transaktionen` überspringt gesperrte Monate. EB-Buchungen des Saldovortrags und des ersten Eröffnungssaldos am 01.01. nimmt die Monatssperre an (`tabellen_pruefung.eroeffnungsbuchungen(session, kontenrahmen, gewinnermittlung)`: nur angelegt, nur mit gemeldeter ID und nur in der Form einer EB-Buchung — am 01.01., ohne Steuer, kein Storno, Belegnummer `EB-JJJJ`, genau eine Seite ein Saldenvortragskonto des Kontenrahmens, die andere ein Bestandskonto; Rahmen lassen sich schachteln; die Jahressperre gilt weiter) — sie tragen die Schlussbilanz vor und ändern weder Verkehrszahlen noch UStVA des Januars, auf einem späteren Tag stimmten die Januarsalden nicht. Eine Eingangsrechnung zu einem festgeschriebenen Monat bucht `opos verbuchen --buchungsdatum eingang|offen|JJJJ-MM-TT` in einen offenen Zeitraum (Vorsteuer, wenn die Rechnung vorliegt: § 15 Abs. 1 Nr. 1 UStG) — die Option wirkt nur auf Belege, deren Monat gesperrt ist, `offen` beginnt beim späteren von Beleg- und Eingangsdatum, bei Bilanzierung — und solange `abschluss.gewinnermittlung` nicht ausdrücklich angegeben ist — nie über den Geschäftsjahreswechsel (§ 252 Abs. 1 Nr. 5 HGB, GoBD Rz. 51: dann Dezember bzw. das Jahr öffnen, Vorsteuer 1548); offener Posten und Fälligkeit bleiben beim Belegdatum. `periode schliessen` holt die Schreibsperre vor seinen Prüfungen. Schließen verlangt: keine Vorschläge im Monat; ungebuchte Umsätze nur mit `--trotzdem`. Öffnen nur mit Grund und nur, wenn das Jahr offen ist. Jede Aktion: Abschlussprotokoll (`protokolliere`, Hash-Kette aus Baustein 12) und Journal | „baue nichts doppelt“: dieselbe Fehlerklasse, dasselbe Protokoll, ein gemeinsames Abfrage-API (`pruefung.perioden.sperre_am`) |
| Prüfregel | Klasse mit `name`, `kategorie`, `schwere`, `beschreibung`, `Parameter` (Pydantic-Modell mit Standardwerten) und `pruefe(kontext) -> list[Befund]`; Registry `PRUEFREGELN`, `registriere_pruefregel`; ändert nie Daten (Test: Datenbank vor/nach identisch) | Spec 4.1, Architektur „Neue Prüfregel hinzufügen“ |
| Befund | Regel, Kategorie, Schwere (`hinweis`, `warnung`, `fehler`), Objekt (Typ, ID), Datum, Betrag, Gegenpartei, Begründung, Abhilfe | Akzeptanz 1 verlangt Betrag, Datum, Gegenpartei |
| Konfiguration | Abschnitt `pruefung` mit Lader `lade_pruefung`: `abgeschaltet`, `schwere` (je Regel), `regeln.<name>` (Schwellen, nur Abweichungen), `belegfrei` (Muster mit Begründung), `kleinbetrag_grenze` (250), `eigene_namen`, `kontenrahmen_datei`, `archiv`, `nachforderung` (Vorlage). Unbekannte Regel → `KonfigurationError` beim Lauf | Spec 4.1: Schwellen ohne Code ändern |
| Pflichtangaben-Quelle | E-Rechnung (XML/ZUGFeRD aus dem Archiv) → Rechnungsmodell; PDF mit Textebene/Text → Regex (Steuernummer, USt-IdNr., Anschrift, eigener Name); Scan ohne Text → nur mit `--ocr`, sonst Hinweis „nicht prüfbar“; ohne Archiv → nur gespeicherte Felder, Steuernummer gilt dann als „nicht erkannt“ (Warnung statt Fehler) | Beleg speichert keine Steuernummer und keinen Empfänger; `models/__init__.py` darf nur die Storno-Felder bekommen |
| Kleinbetrag | Brutto ≤ `kleinbetrag_grenze` (250 €): nur § 33 UStDV (keine Steuernummer, kein Empfänger, keine Nummer) — nicht bei § 13b, § 6a, § 3c (§ 33 Satz 3 UStDV), erkannt an Schlüssel 91/94 bzw. 18/19, OSS-Erlöskonto, E-Rechnungs-Kategorie AE/K oder Hinweis im Text. Dann § 14 Abs. 4 plus die Angaben für den Sonderfall: USt-IdNr. beider Seiten, Hinweis „Steuerschuldnerschaft des Leistungsempfängers“ bzw. auf die steuerfreie ig. Lieferung — bei inländischem Leistenden nach § 14a UStG, bei ausländischem nach dem Recht seines Staats (Art. 226 Nr. 3, 4, 11, 11a MwStSystRL) — als Warnung, weil der Vorsteuerabzug nach § 15 Abs. 1 Nr. 3/4 UStG nicht an der Rechnung hängt | § 33 UStDV seit 01.01.2017; § 14a UStG |
| Steuerschlüssel ./. Konto | Sachkontoseite = die Seite, die kein Geld-/Personenkonto ist (`kennziffern.Kontenplan`). Fehler: Vorsteuerschlüssel auf Erlöskonto, USt-Schlüssel auf Aufwandskonto, Schlüssel auf Konto mit fester Steuerfunktion (8125 …), **DATEV-Automatikkonto** (AV/AM laut der mitgelieferten `accounti/pruefung/skr03.yaml` bzw. `pruefung.kontenrahmen_datei`, abgeglichen mit dem DATEV-Kontenrahmen SKR 03 2026, Art.-Nr. 11174: 3300 = 7 % VSt, 3400 = 19 % VSt, 8300/8400 …) mit anderem Schlüssel. Fehler auch: Schlüssel auf einer Buchung nur zwischen Geld- und Personenkonten. Fehler auch: Automatikkonto mit Steuerbetrag, aber ohne Schlüssel (accounti meldet die Steuer nicht, DATEV rechnet sie). Warnung: unbekannter Schlüssel, Automatikkonto ohne Steuer (DATEV rechnete selbst; der Export setzt BU 40). Hinweis: Vorsteuer auf einem Konto ohne DATEV-Vorsteuerfunktion (`vorsteuer: false`: Löhne, Versicherungen, AfA). Andere Konten der Datei (z.B. 4900, 4930) tragen nur einen üblichen Schlüssel ohne Befund. SKR04 ohne Automatikdatei: nur Bereichsregeln. Die Abhilfe ist ein ausführbarer `korrigiere`-Aufruf (mit Beleg auf einem Automatikkonto: Platzhalter `<Konto>` für ein Konto ohne Automatik) | Akzeptanz 3; nutzt Steuerautomatik, Kennziffern-Bereiche und Kontenrahmen; Fehler nur, wo die Automatik gesichert ist |
| Nachforderung | `accounti.pruefung.aufgaben_anbindung` ersetzt den eingebauten Prüflauf `beleg_fehlt` (wie in Architektur/Bauplan vorgesehen): Anlässe des eingebauten Laufs **geschnitten** mit den Befunden der Regel `umsatz_ohne_beleg` (Schwellen, `belegfrei`-Muster); belegfrei nach Regel → Grund „belegfrei nach Regel …“. Merkmale `befund`, `schwere` zusätzlich | nur ein Erzeuger je Art (Baustein 8); ohne `belegfrei`-Regeln verhält sich der Lauf wie bisher (bestehende Tests) |
| Anfrage an Lieferanten | `nachfordern anfrage TX` zeigt den Entwurf aus der Vorlage (`pruefung.nachforderung`); `--senden` verschickt **diese eine** Anfrage über den SMTP-Zugang aus `versand`, Kommentar an der Aufgabe, Journal `beleg_angefordert`. Kein Lauf verschickt etwas | Spec 4.2: Nachrichten an Dritte sind Entscheidung des Betriebs |
| Verfahrensdoku | aus dem Systemzustand: Mandant, Kontenrahmen, Gewinnermittlung, Belegkanäle (Postfächer, Webhook, Connectoren — ohne Geheimnisse), OCR/LLM (Modell, opt-in), Bankkonten mit Provider/Zustand, Kontierungsregeln, Auto-Schwelle, Freigabe/Storno, Vier-Augen, Rollen, Zuständigkeit, Prüfregeln mit Schwellen, Perioden, Aufbewahrung, Journal-Kopf, Protokolle; gegliedert nach GoBD Rz. 151 ff.; Stand-Datum; Hash und Historie über das Journal (Rz. 154); PDF mit fpdf2 (Liberation Sans aus `erechnung/schriften`) | Akzeptanz 7 |
| Export | `export datev` und `datev belege` setzen nach dem Schreiben die exportierten **freigegebenen** Buchungen auf `exportiert` (blockweise geladen, ein Flush, Sperren je Monat einmal gelesen) und schreiben einen Journal-Eintrag `export` (Datei, SHA-256, Anzahl). Eine Buchung ohne Schlüssel auf einem DATEV-Automatikkonto (aus der Kontenrahmen-Datei) trägt BU 40 „Aufhebung der Automatik“ | Spec 4.3 „exportiert“; vorher setzte niemand den Status |
| Migration | `ddc9a184ddb4` auf `a684d10751de`: Tabellen `journal`, `buchungskorrekturen`, `periodenabschluesse`; `storniert_durch`/`storno_von` per `batch_alter_table` mit benannten Unique-Indizes (`ix_buchungssaetze_…`, auch im Modell: `unique=True, index=True`); SQLite-Trigger von Hand (`after_create` greift in Migrationen nicht). Schon von `init_db` angelegte Tabellen, Spalten, Indizes und Trigger übernimmt sie | Upgrade-Weg: Migration, dann `journal uebernehmen`; ein Befehl des neuen Codes vor der Migration darf das Upgrade nicht blockieren |

## Aufgaben

### Paket 1 — Journal & Storno

- [x] **Modelle** (`models/pruefung.py`, `models/__init__.py`): `Journaleintrag`, `Buchungskorrektur`, `Periodenabschluss`, `Befund`, `Schwere`, `Kategorie`; `Buchungssatz.storniert_durch`, `storno_von`.
- [x] **Tabellen** (`db/tabellen_pruefung.py`, `db/tabellen.py`): `journal`, `buchungskorrekturen` (nur anfügen, ORM + SQLite-Trigger per `after_create`), Spalten am Buchungssatz (eindeutig); Repository (`db/repo_pruefung.py`, Mapping in `db/repository.py`, `lade_belegbuchungen` ohne Storno-Paare).
- [x] **Journal** (`pruefung/journal.py`): kanonischer Schnappschuss, Hash, Anfügen mit Kette, `pruefe_journal` (Kette, Anker, Bestand, Sperren), `uebernehme_bestand` (`tests/test_pruefung_journal.py`).
- [x] **Ereignisse** (`pruefung/ereignisse.py`): Vorgänge aus ORM-Änderungen (Buchungen, Belege, Dubletten, Zahlungslauf-Protokoll, Abschlussprotokoll), Sperre freigegebener Buchungen, Massen-Änderungen abgelehnt; `repo_bank.loesche_buchung` löscht über die Sitzung (`tests/test_pruefung_ereignisse.py`).
- [x] **Storno** (`pruefung/storno.py`): `storniere`, `korrigiere` (Vorschlag direkt / freigegeben per Storno), `freigeben`, `markiere_exportiert`; je ein Test mit Bank-, Beleg-, Ausgleichs-, Skonto- und Splitbuchung (`tests/test_pruefung_storno.py`).
- [x] **CLI:** `korrigiere`, `bestaetige`, `review` umgebaut; `export datev`/`datev belege` vermerken „exportiert“; `buchung storniere|zeige`; `journal [--von --bis --objekt --vorgang]`, `journal zeige NR`, `journal pruefen [--kopf]`, `journal uebernehmen` (`tests/test_cli_journal_storno.py`).
- [x] **Akzeptanz 5 und 6** als Tests.

### Paket 2 — Perioden

- [x] **Tabelle und Sperre** (`periodenabschluesse`, Ereignis auf `buchungssaetze`, `PeriodeGesperrtError`), Stornovermerk in gesperrten Zeiträumen erlaubt (auch Jahressperre, `tabellen_abschluss.nur_stornovermerk`).
- [x] **`pruefung/perioden.py`:** `schliesse`, `oeffne`, `sperre_am`, `lade_perioden`; Abschlussprotokoll + Journal; Sammelläufe (`offene_transaktionen`) (`tests/test_pruefung_perioden.py`).
- [x] **CLI:** `periode schliessen|oeffnen|liste` (`tests/test_cli_periode.py`).

### Paket 3 — Prüfregeln

- [x] **Registry, Kontext, Befund, Konfiguration** (`pruefung/regeln/__init__.py`, `pruefung/einstellungen.py`).
- [x] **Pflichtangaben-Quelle** (`pruefung/belegangaben.py`): E-Rechnung, Textebene, OCR auf Wunsch, sonst gespeicherte Felder.
- [x] **Vollständigkeit** (`regeln/vollstaendigkeit.py`), **Richtigkeit** (`regeln/richtigkeit.py`), **Zeitgerechtheit** (`regeln/zeitgerechtheit.py`), **Ordnung** (`regeln/ordnung.py`) — je Regel auslösend und nicht auslösend, Regeln ändern nichts (`tests/test_pruefung_regeln.py`).
- [x] **CLI** `accounti pruefen [--period] [--regel] [--stichtag] [--archiv] [--ocr]`, Exit 1 bei Fehler-Befunden; `pruefen regeln` (`tests/test_cli_pruefen.py`).

### Paket 4 — Nachforderung

- [x] **Prüflauf** (`pruefung/nachforderung.py`, `pruefung/aufgaben_anbindung.py`), Anfrage aus Vorlage, Versand nur auf Befehl (`tests/test_pruefung_nachforderung.py`); `test_aufgaben_anbindung.py` erwartet jetzt die Anbindung von Baustein 7.
- [x] **CLI** `accounti nachfordern [--period] [--stichtag]`, `nachfordern anfrage UMSATZ [--an] [--senden]` (`tests/test_cli_nachfordern.py`).

### Paket 5 — Verfahrensdokumentation & Abschluss

- [x] **Generator** (`pruefung/verfahrensdoku.py`), Markdown + PDF, Fassung im Journal (`tests/test_pruefung_verfahrensdoku.py`).
- [x] **CLI** `accounti verfahrensdoku --ausgabe … [--pdf …] [--archiv …]`.
- [x] **Selbstprüfung:** übernommener Bestand gilt nicht als verspätet/nach Abschluss angelegt (`test_bestand_von_vor_dem_journal_ist_nicht_verspaetet`); festgeschriebene Kontoauszüge über `pruefe_auszuege` (`test_festgeschriebener_kontoauszug_mit_fehlendem_umsatz`); zwei Tests mit zufälligem Hash-/ID-Zeichen deterministisch gemacht.
- [x] **Abschluss:** `pytest`, `ruff` (ohne Cache), `mypy` grün; Checkboxen abgehakt; Doku-Bausteine vollständig.

### Befunde der Prüfung (technisch und fachlich), je mit Regressionstest

- [x] **Sperre und Journal** (`tests/test_pruefung_umgehungen.py`): Sperre und Storno-Regel aus dem gespeicherten Stand auch bei abgelaufenen Attributen (A1), kein Wechsel des Primärschlüssels (A2), `session.new` einmal je Flush, Leistungstest 5.000 Buchungen (A3), Massen- und `bulk_*`-Wege gesperrt (A8), Löschen + Neuanlegen derselben ID, Stornovermerk nur mit Stornobuchung, Ereignisse aus `session_factory` ohne zirkulären Import (A5). `markiere_exportiert` in einem Flush (A4: `export datev` mit 5.000 Buchungen 17,9 s → 2,2 s, main 1,0 s). `journal uebernehmen` übernimmt Sperren (A6, `test_pruefung_journal.py::test_sperren_von_vor_dem_journal_uebernehmen`). Reines Storno macht den Umsatz wieder offen (A7/B-M3, `test_pruefung_storno.py::test_reines_storno_macht_den_umsatz_wieder_offen`).
- [x] **Steuerschlüssel** (`test_pruefung_storno.py`, `test_cli_supervisor.py`, `test_integrationen_lauf.py`): `korrigiere` verlangt bei neuem Sachkonto `--steuer`/`--ohne-steuer`, lehnt Fehler-Kombinationen ab, `--lernen` nur ausdrücklich (B-H1); `--ohne-steuer` bei Beleg mit Grund (B-M2); SKR03-Stammdaten nach DATEV, Ende-zu-Ende mit `rechnung_zwei_steuersaetze.txt` (B-H2, `test_cli_pruefen.py`).
- [x] **Perioden** (`test_abschluss_vortrag.py`, `test_pruefung_perioden.py`, `test_cli_opos.py`): Saldovortrag in einen festgeschriebenen Januar, `opos verbuchen --buchungsdatum` (B-H3).
- [x] **Kasse und Folgeläufe** (`test_kassenbuch.py`, `test_abschluss_abgrenzung.py`, `test_anlagen_dienst.py`, `test_steuer_kennziffern.py`): `kasse storno` nach `korrigiere` (B-M1), Storno-Paare in Abgrenzung, Anlagen-Vorschlägen und Rechnungs-Kennziffer (B-M4).
- [x] **Prüfregeln** (`test_pruefung_regeln.py`): Marktplatz-Dubletten (B-M5), DE-USt-IdNr. ausländischer Lieferanten (B-M6), § 33 UStDV nicht bei § 13b/§ 6a/§ 3c, § 14a (B-M7), gültige Abhilfe.
- [x] **Export und Doku:** Belegfeld 2 an Storno-Paaren (`test_datev_export.py`, `test_datev_belege.py`), Warnung bei Storno-Datum in anderem Monat, Verfahrensdoku nennt alle `auto`-Wege (`test_pruefung_verfahrensdoku.py`).

### Befunde der Nachprüfung (Runde 3), je mit Regressionstest

- [x] **Gewinnermittlung** (`test_cli_opos.py::test_buchungsdatum_im_folgejahr_braucht_die_gewinnermittlung`): ohne `abschluss.gewinnermittlung` kein Buchungsdatum im Folgejahr (M-1); bei abgeschlossenem Jahr rät die Meldung zu `abschluss oeffnen` (N-11, `test_pruefung_perioden.py`).
- [x] **`journal pruefen` aus einem Stand** (M-2, `test_pruefung_nebenlaeufigkeit.py::test_journal_pruefen_liest_einen_gemeinsamen_stand`); busy timeout 30 s (N-5); `periode schliessen` sperrt vor den Prüfungen (N-4, `::test_periode_schliessen_wartet_und_prueft_danach`).
- [x] **DATEV-Export auf Automatikkonten** (M-4, `test_pruefung_regeln.py::test_datev_export_hebt_die_automatik_auf`, `test_cli_datev.py::test_export_und_belege_mit_automatikkonten`): passender Schlüssel leer, ohne Steuer BU 40, abweichender gemeldet; Kontenrahmen-Datei im Paket, kaputte Datei = Meldung (N-8, `::test_export_mit_kaputter_kontenrahmen_datei`).
- [x] Sammelläufe als Grenze (M-3, Laufsperre aus Baustein 10a); Alias in Core-DML (N-1), EB-Rahmen `eq=False`, Kontenrahmen statt Kontenliste, Bestandskonto, kein EB-Storno (N-2, N-3, `test_abschluss_vortrag.py`), neue Spalte ohne Dauerbefund (N-6), Storno mit ungetauschten Konten (N-7), `--ohne-steuer` bei § 13b/ig. Erwerb (N-9), ausführbare Abhilfe (N-10), Verfahrensdoku bei EÜR (N-12), Steuerbetrag ohne Schlüssel auf Automatikkonto (N-13).

### Verzahnung mit Baustein 10a, je mit Regressionstest

- [x] **Rollen in der CLI** (`tests/test_cli_rechte_pruefung.py`): `befehle.handelnde_person`
  in `bestaetige`, `periode schliessen|oeffnen`, `abschluss vortrag|oeffnen`, `journal
  uebernehmen` (Buchungen freigeben) und `korrigiere`, `buchung storniere`, `kasse storno`
  (buchen); Betrachter und — beim Buchen — Freigeber werden abgewiesen, ein Freitext ist kein
  Benutzer, falscher Einmalcode scheitert; im Journal, in `geprueft_von`, in
  `buchungskorrekturen` und im Abschlussprotokoll steht der Benutzer, auch an den
  EB-Buchungen des Vortrags; Rollenmatrix: buchen schließt Freigeben ein
  (`::test_buchen_umfasst_die_freigabe`). REST: „API-Token <Name>“ im Journal
  (`test_api_rest.py::test_im_journal_steht_das_token`).
- [x] **Laufsperre** (`test_betrieb_laufsperre.py::test_sammellaeufe_aus_baustein_7_halten_die_laufsperre`):
  `opos verbuchen`, `periode schliessen` (Art `bank`), `nachfordern` (Art `aufgaben`);
  `journal uebernehmen` sperrt vor dem Lesen
  (`test_pruefung_nebenlaeufigkeit.py::test_journal_uebernehmen_zweimal_gleichzeitig`).
- [x] **Aufbewahrung** (`test_betrieb_aufbewahrung.py`): Journal, Buchungskorrekturen,
  Monatsabschlüsse als Bücher; spät festgeschriebener Monat verschiebt den Fristbeginn;
  wieder geöffneter Monat läuft nicht ab.
- [x] **Sicherung** (`test_betrieb_sicherung.py::test_journal_und_korrekturen_im_rundlauf`,
  auch `…_postgresql`): Rundlauf mit Journal, Korrekturen und Monatssperre, Trigger und
  Sperren wirken danach, `journal pruefen --kopf` in Ordnung; Sicherung einer Datenbank vor der
  Migration mit dem neuen Code (nur vorhandene Spalten).
- [x] **Migration** `ddc9a184ddb4` (`tests/test_migration_belegvollstaendigkeit.py`): Bestand
  auf `a684d10751de` → Upgrade → `journal uebernehmen` → `journal pruefen` in Ordnung;
  `alembic check` ohne Abweichung, Downgrade und erneutes Upgrade; schon von `init_db`
  angelegte Tabellen; Sicherung vor der Migration zurückgespielt und migriert. Zusätzlich
  lokal gegen PostgreSQL 16 (Upgrade mit Bestand, Übernahme, Downgrade, `check`,
  `init_db` vor der Migration, PG-Tests der Sicherung).

### Befunde der Abschlussprüfung, je mit Regressionstest

- [x] **M-A** „(ungeprüft)“ auch für die Person eines Vorgangs; 10a-Befehle (`zahlung`,
  `anlagen freigeben`, `ustva`) und die Freigaben im Browser setzen den geprüften
  Benutzer; `zahlung sepa` (Zahlungsfreigabe) und `zahlung abgleichen` (buchen)
  gebunden (`test_cli_rechte_pruefung.py::test_zahlung_einreichen_nicht_unter_fremdem_namen`,
  `::test_eigene_person_eines_vorgangs_wird_auch_gekennzeichnet`,
  `test_api_rechte_matrix.py::test_freigabe_im_browser_steht_geprueft_im_journal`).
- [x] **N-A** Sperrreihenfolge unter PostgreSQL
  (`test_pruefung_nebenlaeufigkeit.py::test_kein_deadlock_durch_sperrreihenfolge_postgresql`);
  **N-D** keine Read-only-Transaktion nach der Prüfung
  (`::test_nach_der_pruefung_schreibt_die_sitzung_wieder_postgresql`).
- [x] **N-B** Buchungstag vor dem Eingang: „zu früh“
  (`test_pruefung_perioden.py::test_fester_tag_vor_dem_eingang_warnt_zu_frueh`).
- [x] **N-C** Verfahrensdoku: gebunden, aber Systemdatenbank nicht lesbar; keine leere
  SQLite-Datei; nur Benutzer der aktiven Gesellschaft
  (`test_pruefung_verfahrensdoku.py::test_benutzer_bei_falscher_systemdatenbank_und_je_gesellschaft`).
- [x] **N-E** `opos bestaetigen` setzt `geprueft_von`; Entscheidungen über den
  Belegabgleich stehen im Journal (`abgleich_bestaetigt|abgelehnt`; der Abgleich selbst
  speichert keine Person) (`test_cli_opos.py::test_vorschlag_anzeigen_und_bestaetigen`,
  `test_bank_abgleichslauf.py::test_entscheidung_ueber_den_abgleich_steht_im_journal`).
- [x] **N-F** Testlücken U3, U4, U6, F1, F2
  (`test_pruefung_journal.py::test_neue_person_im_kontext_ist_ungeprueft`,
  `::test_gebundene_datenbank_kennzeichnet_ohne_eigene_benutzer`, `test_api_rest.py`
  gegen eine gebundene Datenbank, `test_bank_lauf.py::test_mit_freigabe_wird_je_konto_gesichert`
  über den Kontostand statt der Umsätze, `::test_cli_sichert_je_konto`).
- [x] **N-G** Upgrade mit `docker compose stop app lauf`; der Befund „ohne Eintrag“
  empfiehlt `journal uebernehmen` nur, solange es geht
  (`test_pruefung_journal.py::test_befundtext_empfiehlt_uebernahme_nur_wenn_moeglich`);
  Vorher/Nachher, das kein JSON-Objekt ist, wird gemeldet statt abzustürzen
  (`::test_journal_mit_nicht_objekt_stuerzt_nicht_ab`); `anlagen freigeben` ohne
  Benutzer ohne „supervisor“.

### Befunde der Schlussprüfung, je mit Regressionstest

- [x] **M-1** Öffnen nur mit `STEUER_FREIGEBEN` (freigeber), Hinweis auf freigegebene bzw.
  abgegebene Voranmeldungen (`test_cli_rechte_pruefung.py::test_oeffnen_nur_wer_steuermeldungen_freigibt`,
  `::test_abschluss_vortrag_und_oeffnen_mit_benutzer`).
- [x] **M-2** `journal uebernehmen` nur mit `VERWALTEN` und nur vor dem ersten regulären
  Eintrag; `journal pruefen` meldet spätere Übernahmen
  (`test_pruefung_journal.py::test_uebernahme_nur_auf_dem_upgrade_weg`).
- [x] **M-3/T-M1** `kasse buchen|anfangsbestand`, `abschluss eroeffnung|bestaetigen|ablehnen`,
  `opos bestaetigen|ablehnen`, `bank bestaetigen|ablehnen`, `export datev`, `datev belege`,
  `nachfordern anfrage --senden` gebunden; „(ungeprüft)“ im Journal
  (`test_cli_rechte_pruefung.py::test_betrachter_darf_nicht_…`,
  `::test_eb_in_festgeschriebenen_januar_nicht_durch_betrachter`,
  `::test_ungepruefte_person_im_journal_gekennzeichnet`).
- [x] **M-4** Verfahrensdoku mit Benutzern, Rollen, Rechten, Einmalcode, Freigabewegen,
  Datensicherung, `betrieb lauf`, Laufsperre; **N-3** Gewinnermittlung ohne Angabe, EB-Form
  vollständig (`test_pruefung_verfahrensdoku.py::test_akzeptanz_7_…`).
- [x] **M-5** `--ohne-steuer` bei 18/19/91/94: eigene Meldung, Warnung, keine Abhilfe
  „Vorsteuer entfernen“, Brutto ohne selbst berechnete Steuer
  (`test_pruefung_storno.py::test_ohne_steuer_bei_13b_und_ig_erwerb_eigener_hinweis`,
  `test_pruefung_regeln.py::test_abhilfe_bei_13b_schlaegt_nicht_vorsteuer_entfernen_vor`).
- [x] **T-M2** Schreibsperre nur bei Journal- oder Sperrbezug, `fints freigeben` je Konto
  festgeschrieben (`test_pruefung_nebenlaeufigkeit.py::test_flush_ohne_journalbezug_holt_keine_schreibsperre`,
  `::test_anmeldung_wartet_nicht_auf_eine_buchung_postgresql`,
  `test_bank_lauf.py::test_mit_freigabe_wird_je_konto_gesichert`).
- [x] **T-N1/T-N2** Lesestand ohne fremden Commit, unter PostgreSQL Schnappschuss
  (`::test_journal_pruefen_schreibt_offene_aenderungen_nicht_fest`,
  `::test_journal_pruefen_haelt_schreiber_nicht_an_postgresql`); **T-N3** Laufsperre vor
  dem Einmalcode (`test_cli_rechte_pruefung.py::test_laufsperre_vor_dem_einmalcode`);
  **T-N4** gleichzeitiges Storno als Meldung
  (`test_pruefung_storno.py::test_gleichzeitiges_storno_meldet_klar`); **T-N5**
  (`test_api_rest.py::test_lauf_ueber_rest_steht_unter_dem_token_im_journal`).
- [x] **N-1** Vorsteuer-Zeitraum bei festem Buchungsdatum
  (`test_pruefung_perioden.py::test_fester_tag_lange_nach_dem_eingang_warnt_zur_vorsteuer`);
  **N-2** als Grenze (Kalenderjahr); **N-4**
  (`test_pruefung_nachforderung.py::test_beleg_ueber_die_buchung_zugeordnet`); **N-5**
  (`test_pruefung_regeln.py::test_datev_export_warnt_bei_steuer_ohne_schluessel_auf_automatikkonto`);
  **N-6** CHANGELOG, Anfrage-Text ohne `antwort_an`, `--von` ohne „supervisor“.

### Befunde der Nachprüfung (Runde 2), je mit Regressionstest

- [x] **Nebenläufigkeit** (`tests/test_pruefung_nebenlaeufigkeit.py`): Schreibsperre vor dem Lesen in `before_flush` und `fuege_an`; Export gegen Storno, Freigabe gegen Änderung, Festschreibung gegen Verschiebung, Journalnummer (N1, N3); die Abkürzung über den Vorher-Stand ist entfernt (M1). Zusätzlich lokal gegen PostgreSQL 16 und unter Last (4 Prozesse × 250 Vorgänge: Journal in Ordnung).
- [x] **Verlauf** in `journal pruefen` (M2, `test_pruefung_journal.py::test_gewaschene_aenderung_faellt_am_verlauf_auf`, `::test_verlauf_ohne_fehlalarm_bei_mehreren_vorgaengen_je_flush`); Stornovermerk ohne zurückzeigendes Storno (N5, `test_pruefung_umgehungen.py::test_haengender_stornovermerk_faellt_auf`), Storno muss freigegeben sein und spiegeln (`::test_stornovermerk_nur_auf_ein_spiegelbildliches_freigegebenes_storno`).
- [x] Core-DML mit anders geschriebenem Tabellennamen (N2), EB-Ausnahme nur für die Form einer EB-Buchung und verschachtelt (N4, `test_abschluss_vortrag.py`), Datumsformat im Hinweis (N6 = N-N1).
- [x] **Buchungsdatum** (`test_pruefung_perioden.py`): nicht über den Jahreswechsel bei Bilanz (N-M1), nur Belege aus gesperrten Monaten, `offen` ab dem späteren von Beleg und Eingang (N-N8, N-N7).
- [x] **Steuer** (`test_pruefung_storno.py`, `test_pruefung_regeln.py`, `test_cli_supervisor.py`): `--ohne-steuer` nicht für ausgewiesene USt (N-M2); Automatikkonto ohne Schlüssel — Warnung, `korrigiere` lehnt ab, Abhilfe ohne `--ohne-steuer`, DATEV-Export BU 40 (N-M3); `--lernen` lernt den Schlüssel der Neubuchung (N-N5); Kontenrahmen-Datei der Konfiguration (N-N6).
- [x] **Texte und Doku:** Verfahrensdoku beschreibt die EB-Ausnahme (N-M4), Steuersatz ohne „2E+1 %“ (N-N2), eigene USt-IdNr. verdeckt den Lieferanten nicht (N-N3), Art. 226 MwStSystRL bei ausländischen Leistenden (N-N4), Hinweise mit `--steuer`/`--ohne-steuer` (N-N10), Doku-Bausteine (N-N9), Grenze „Beleg nach reinem Storno“ (N-N11).

## Akzeptanzkriterien → Tests

| # | Kriterium | Tests |
|---|-----------|-------|
| 1 | Zahlung ohne Beleg erscheint als Befund mit Betrag, Datum, Gegenpartei | `test_pruefung_regeln.py::test_akzeptanz_1_zahlung_ohne_beleg_mit_betrag_datum_gegenpartei`, `::test_umsatz_mit_beleg_ist_kein_befund`, `::test_umsatz_ohne_beleg_schwellen_belegfrei_und_zeitraum`, `test_cli_pruefen.py::test_akzeptanz_1_cli_zahlung_ohne_beleg` |
| 2 | Rechnung ohne Steuernummer → unvollständig nach § 14 UStG | `test_pruefung_regeln.py::test_akzeptanz_2_rechnung_ohne_steuernummer_unvollstaendig`, `::test_erechnung_ohne_ustid_und_steuernummer`, nicht auslösend: `::test_rechnung_mit_steuernummer_ist_vollstaendig`, `::test_kleinbetragsrechnung_braucht_keine_steuernummer`, `::test_erechnung_mit_ustid_ist_vollstaendig`; `test_cli_pruefen.py::test_akzeptanz_2_und_3_cli_fehler_mit_exit_1` |
| 3 | Steuerschlüssel passt nicht zum Sachkonto → erkannt | `test_pruefung_regeln.py::test_akzeptanz_3_steuerschluessel_passt_nicht_zum_sachkonto`, `::test_passende_steuerschluessel_sind_kein_befund`, `::test_skr04_ohne_automatikdatei`; nicht auslösend auf richtigen Daten: `::test_keine_automatikkonten_laut_datev`, `test_cli_pruefen.py::test_eigene_belegverbuchung_mit_zwei_steuersaetzen_ohne_fehler`; `test_cli_pruefen.py::test_akzeptanz_2_und_3_cli_fehler_mit_exit_1` |
| 4 | Befund → Aufgabe, die verstummt, sobald der Beleg eintrifft | `test_pruefung_nachforderung.py::test_akzeptanz_4_aufgabe_verstummt_wenn_der_beleg_eintrifft`, `::test_belegfrei_nach_regel_schliesst_mit_grund`, `test_cli_nachfordern.py::test_akzeptanz_4_cli` |
| 5 | Manipulierter Journaleintrag → `journal pruefen` findet ihn | `test_pruefung_journal.py::test_veraenderter_eintrag_wird_gefunden`, `::test_neu_berechneter_hash_bricht_die_kette`, `::test_entfernter_eintrag_wird_gefunden`, `::test_abgeschnittenes_ende_faellt_am_bestand_auf`, `::test_buchung_an_accounti_vorbei_geaendert`; `test_cli_journal_storno.py::test_akzeptanz_5_manipulierter_eintrag_wird_gefunden` |
| 6 | Freigegebene Buchung nur per Storno korrigierbar, beide sichtbar | `test_pruefung_storno.py::test_freigegebene_buchung_nur_per_storno_beide_sichtbar`, `::test_freigegebene_buchung_nicht_loeschbar`, keine Umgehung über abgelaufene Attribute, Primärschlüssel oder Massenwege: `test_pruefung_umgehungen.py`, `test_cli_journal_storno.py::test_akzeptanz_6_freigegeben_nur_per_storno_beide_sichtbar`; behobener Fehler je Buchungsart: `test_pruefung_storno.py::test_belegbuchung_behaelt_beleg_und_betrag`, `::test_ausgleichsbuchung_behaelt_anteil_und_beleg`, `::test_skontobuchung_behaelt_betrag_steuer_und_beleg`, `::test_splitbuchung_behaelt_ihren_anteil`, `test_cli_journal_storno.py::test_cli_belegbuchung`, `::test_cli_ausgleichsbuchung`, `::test_cli_skontobuchung`, `::test_cli_splitbuchung` |
| 7 | Verfahrensdoku beschreibt den eingerichteten Stand | `test_pruefung_verfahrensdoku.py::test_akzeptanz_7_beschreibt_den_eingerichteten_stand`, `::test_fassungen_im_journal_und_historie`, `::test_cli` |

## Grenzen

- **Rohes SQL und Sitzungen an `session_factory` vorbei.** Journal-Ereignisse,
  Storno-Regel und Monats-/Jahressperre hängen am ORM (Sitzungs- und Mapper-Ereignisse,
  eingehängt von `session_factory`/`init_db`). Wer direkt auf die Datenbank schreibt
  (Core-`execute` auf der Verbindung, rohes SQL per `text()`), umgeht sie — ORM- und
  Core-DML über die Sitzung (`session.execute(insert/update/delete(…))`) auf Buchungen,
  Journal und Korrekturen lehnt accounti ab; die alten `bulk_*`-Wege
  sperrt nur die Sitzungsklasse aus `session_factory` (`AccountiSitzung`) — eine selbst
  gebaute `Session(engine)` könnte sie noch nutzen. Unter SQLite verhindern Trigger nur
  Änderungen an `journal` und `buchungskorrekturen`. Aufgedeckt wird
  das von `journal pruefen` — für Buchungen, Belege und die Sperrtabellen über den
  Bestandsabgleich, und über den Verlauf auch dann, wenn ein späterer regulärer Vorgang
  (Export-Vermerk, Storno, Freigabe) die Zeile wieder ins Journal gebracht hat. Nicht
  auffallen kann eine Änderung, die vor dem nächsten Vorgang wieder zurückgesetzt wurde. Umsätze, Kontakte, offene Posten, Zuordnungen, Abgleiche,
  Belegpositionen und Aufgaben stehen nicht im Journal (Stammdatenänderungen werden nicht
  historisiert). Wird das Ende des Journals **und** die zugehörige Buchung gelöscht, fällt das
  nur mit dem notierten Kopf auf (`journal pruefen --kopf NR:HASH`). Unter Postgres gibt es
  keine Trigger. Die Tests laufen gegen SQLite; die Wettlauf-Fälle (Export gegen Storno,
  Freigabe gegen Änderung, Festschreibung gegen Verschiebung, Journalnummer) sind zusätzlich
  lokal gegen PostgreSQL 16 geprüft (nicht in der CI).
- **Nebenläufigkeit:** Jede schreibende accounti-Transaktion hält ab dem ersten Flush mit
  Journal- oder Sperrbezug (Buchungen, Belege, Zahlungsläufe, Abschlussprotokoll, Journal,
  Korrekturen, Sperren) bzw. `schreibe` (`periode schliessen`: vor seinen Prüfungen) die
  Schreibsperre bis zum Commit; Flushes ohne diesen Bezug (neue Umsätze, Anmeldungen,
  Sitzungen) holen sie nicht. Unter PostgreSQL holt sie außerdem jeder Flush, der
  bestehende Zeilen ändert oder löscht (außer Anmeldedaten) — so ist die
  Advisory-Sperre immer die erste Sperre einer Transaktion, die sie braucht, und zwei
  accounti-Schreiber können sich nicht gegenseitig blockieren (Deadlock). Rest: zwei
  gleichzeitige Einfügungen desselben eindeutigen Werts (z.B. derselbe Umsatz aus zwei
  Importen) warten aufeinander außerhalb dieser Reihenfolge — PostgreSQL bricht dann
  einen der beiden mit `DeadlockDetected` ab, die Daten bleiben konsistent. `fints
  freigeben` und `bank lauf` schreiben den Abruf je Konto fest (keine offene
  Transaktion während der TAN-Abfrage bzw. des Netzabrufs); die Buchungen danach
  beginnen eine eigene Transaktion.
  Ein zweiter Schreiber wartet (SQLite: busy timeout, von `session_factory` auf 30 s
  gesetzt, danach „database is locked“; PostgreSQL: ohne Frist) und prüft dann gegen den
  neuen Stand: Ein einzelner Vorgang, der dem inzwischen geschriebenen Stand widerspricht,
  wird abgelehnt (zweites Storno derselben Buchung: Unique; Freigabe einer inzwischen
  freigegebenen Buchung: Storno-Regel), nicht zusammengeführt. **Sammelläufe sind dagegen
  nicht durch die Schreibsperre geschützt** (zwei gleichzeitige lesen dieselben offenen
  Umsätze bzw. Belege, bevor einer schreibt) — das übernimmt die Laufsperre aus Baustein 10a
  (`betrieb.laufsperre`, je Datenbank und Art höchstens ein Lauf, über Prozesse hinweg; ein
  zweiter endet mit Exit 1 bzw. HTTP 409 statt zu warten): Art `bank` für `bank lauf` und
  seine Schritte (`bank abrufen`, `fints freigeben`, `kreditkarte abgleich`, `opos
  zuordnen`, `bank abgleich`, `classify`), `opos verbuchen` (bucht dieselben Belege) und
  `periode schliessen` (nicht festschreiben, während ein Lauf in den Monat bucht); Art
  `aufgaben` für `aufgaben lauf` und `nachfordern` (derselbe Prüflauf `beleg_fehlt`).
  `journal uebernehmen` holt die Schreibsperre, bevor es liest. Nicht gesperrt sind
  `aufgaben pruefen` (Baustein 8) und Läufe an der CLI vorbei. Unter PostgreSQL
  serialisiert die Sperre alle schreibenden Transaktionen mit Journalbezug (Durchsatz statt
  Parallelität). Lange Befehle halten die Sperre bis zu ihrem Commit. `journal pruefen`
  liest Journal und Bestand aus einem Stand: unter PostgreSQL aus einem Schnappschuss
  (`REPEATABLE READ READ ONLY`, hält niemanden auf), unter SQLite in einer Lesetransaktion
  — Schreiber warten mit ihrem Commit, solange die Prüfung liest (gemessen: 22.200
  Einträge 2,0 s; hochgerechnet auf zehn Jahre, rund 250.000 Einträge, 20–25 s und etwa
  1 GB Speicher — nahe am busy timeout von 30 s; die Prüfung lädt das ganze Journal).
  Ein zweites Storno derselben Buchung scheitert am Unique-Index und wird als Meldung
  „inzwischen storniert“ abgelehnt. Rohes SQL nimmt die Sperre nicht.
- **Personen:** Ohne eingerichtete Benutzer sind sie Zeichenketten (`--von`,
  `ACCOUNTI_BENUTZER`, Anmeldename) — wer die CLI bedient, kann jeden Namen angeben. Mit
  Benutzern (Baustein 10a) brauchen alle Befehle aus `FREIGABEWEGE` (Erfassen, Freigeben,
  Korrigieren, Stornieren, Festschreiben, Öffnen, Vortrag, Export, Versand,
  Bestandsübernahme) Rolle und Einmalcode, und im Journal steht der Benutzer. Nicht
  gebunden sind Lesebefehle und maschinelle Läufe und Importe (`classify`, `opos
  verbuchen`, `opos zuordnen`, `bank abgleich`, `bank lauf`, `aufgaben lauf`, `import`,
  `belege import`, `verfahrensdoku`, `abschluss buchen` und `anlagen afa` mit Vorschlägen):
  dort steht die Person als „… (ungeprüft)“ im Journal, sobald die Datenbank zu einer
  Benutzerverwaltung gehört (Merker der Bindung oder eigene Benutzer; je Verbindung eine
  Minute gemerkt). Eine nicht gebundene Gesellschafts-Datenbank (noch keine Rechteprüfung,
  keine Rollenvergabe dort) kennzeichnet noch nicht. Die Prüfung gilt in der CLI auf dem
  Server; wer die Datenbankdatei schreiben kann, umgeht sie (Grenze aus 10a). Zeitstempel
  sind lokale Zeit ohne Zeitzone, ohne qualifizierten Zeitstempel.
- **Bestehende Datenbanken** brauchen die Migration `ddc9a184ddb4` (neue Spalten
  `storniert_durch`, `storno_von`, neue Tabellen, Trigger); ohne Tabelle `journal` wird nicht
  protokolliert, und `journal pruefen` meldet das. Bestand von vor dem Journal einmal mit
  `accounti journal uebernehmen` eintragen — nur, solange das Journal außer Übernahmen leer
  ist, also gleich nach der Migration und bevor accounti selbst schreibt; danach lehnt
  accounti ab, und `journal pruefen` meldet jede Übernahme nach dem ersten regulären Eintrag
  (geprüft: Datenbank mit Buchungen, Belegen und abgeschlossenem Jahr auf `a684d10751de`,
  Migration, Übernahme — `journal pruefen` in Ordnung). Wer vergisst und schon gebucht
  hat, behält die Befunde „ohne Eintrag“ für den Altbestand (bewusst: sie sind von an
  accounti vorbei angelegten Buchungen nicht zu unterscheiden). Die Sicherung aus 10a liest eine Datenbank vor der Migration mit dem neuen Code
  (nur vorhandene Spalten) und bringt Journal und Korrekturen samt Triggern zurück.
- **Aufbewahrung:** Journal, Buchungskorrekturen und Monatsabschlüsse zählen als Bücher (10
  Jahre); ein spät festgeschriebener Monat verschiebt den Fristbeginn seines
  Wirtschaftsjahres, ein wieder geöffneter Monat eines offenen Jahres läuft nicht ab. Den
  Zeitpunkt einzelner Buchungen aus dem Journal wertet der Bericht nicht aus.
- **Storno als Gegenbuchung**, nicht als DATEV-Generalumkehr (GU-Kennzeichen). Haben beide
  Seiten dieselbe Natur und einen Steuerschlüssel, lehnt accounti das Storno ab. Storno und
  Korrektur ändern keine offenen Posten, Zahlungszuordnungen, Belegabgleiche,
  Kreditkartenabrechnungen, AfA-Vorgänge oder Abgrenzungen — eine falsche Zahlungszuordnung
  bleibt bestehen, eine schon vorgeschlagene Abgrenzung des Originals ebenso (neue Läufe für
  Abgrenzung und Anlagen übergehen Storno-Paare). Ein anderer Schlüssel per `--steuer` ist bei
  Buchungen mit Beleg gesperrt (die Steuer kommt aus dem Beleg bzw. dem Ausgleich) — außer
  § 13b und ig. Erwerb (94/91/19/18) und Belegen ohne Steuersatz, jeweils mit Grund
  (Gesamttest Paket C);
  `--ohne-steuer` entfernt dort Vorsteuer, ig. Erwerb und § 13b (Eingangsrechnung, z.B. ein
  falsch erkannter § 13b-Fall) nur mit Grund. Bei § 13b und ig. Erwerb (18, 19, 91, 94)
  entfernt es Steuerschuld **und** Vorsteuer — richtig nur, wenn gar kein solcher Fall
  vorliegt (Grund dann Pflicht, auch ohne Beleg, und eine Warnung); „kein
  Vorsteuerabzug“ bei einem echten § 13b-Fall bildet accounti nicht ab (die Steuerschuld
  bliebe, § 13b Abs. 5 UStG; der Vorsteuerabzug hängt nicht an der Rechnung, § 15 Abs. 1
  Nr. 3/4 UStG) — das klärt der Steuerberater. Das Brutto einer korrigierten Buchung
  enthält bei diesen Schlüsseln die selbst berechnete Steuer nicht; ausgewiesene Umsatzsteuer einer
  Ausgangsrechnung (Schlüssel 2, 3; § 14c UStG) bleibt — die Berichtigung ist ein neuer
  Beleg. Nach einem reinen Storno einer Belegbuchung lässt sich
  der Beleg nicht erneut mit `opos verbuchen` buchen (der offene Posten bleibt bestehen);
  der Weg ist `korrigiere` statt `storniere`. Eine freigegebene Buchung mit
  Steuerschlüssel zwischen zwei Geld-/Personenkonten lässt sich nicht stornieren (die
  Gegenbuchung höbe die Steuer nicht auf) — die Prüfregel verweist dann auf den
  Steuerberater. `kasse storno` kehrt die gültige Buchung um (nach `korrigiere` die
  Neubuchung); ist die Buchung eines Kassenvorgangs rein storniert, lehnt es ab.
- **Storno mit `--datum` in einem anderen Monat** verschiebt die Umsatzsteuer-Wirkung in
  den Zeitraum des Stornos; accounti warnt, berichtigt aber keine schon abgegebene
  Voranmeldung des Originalzeitraums (das bleibt Entscheidung des Betriebs).
- **DATEV:** Storno als Gegenbuchung, nicht als Generalumkehr; DATEV verknüpft Original
  und Storno nicht selbst — Belegfeld 2 trägt an beiden `ST` + 8 Zeichen der Original-ID
  (nur ein sichtbarer Bezug). Auf DATEV-Automatikkonten (AV/AM) gilt die
  Steuerschlüssel-Tabelle (DATEV Dok.-Nr. 0907049, Kap. 3: Steuerschlüssel nur auf Konten
  ohne Automatik): Entspricht der Schlüssel der Automatik, bleibt das BU-Feld leer (DATEV
  rechnet selbst), ohne Steuer steht BU 40 (Aufhebung der Automatik); ein abweichender
  Schlüssel bleibt stehen und wird vor dem Export gemeldet (DATEV nähme ihn nicht an —
  `pruefen` meldet ihn als Fehler). Die Automatikkonten kommen aus derselben
  Kontenrahmen-Datei wie die Prüfregel (mitgeliefert, nicht vom Arbeitsverzeichnis
  abhängig); eine fehlende oder kaputte Datei bricht den Export ab, bevor etwas als
  exportiert vermerkt ist. Ein Storno in einem schon exportierten Monat geht nur über
  einen erneuten Export des Zeitraums, das Original wird dabei noch einmal übertragen.
- **BWA:** `bwa/berechnung.py` (von keinem Befehl genutzt) summiert Soll und Haben beide
  positiv — ein Storno kehrt sich dort nicht um. Wer die BWA anschließt, muss das zuerst
  ändern.
- **Verhaltensänderungen:** automatisch gebuchte Buchungen (`auto`) gelten wie im ganzen
  Projekt als freigegeben — ihre Korrektur ist jetzt ein Storno; `korrigiere` mit neuem
  Sachkonto verlangt bei Buchungen mit Schlüssel `--steuer` oder `--ohne-steuer` (früher fiel
  der Schlüssel still weg), bei gleichem Sachkonto bleibt er; `bestaetige` und
  `korrigiere` nehmen ohne `--von` `ACCOUNTI_BENUTZER` bzw. den Anmeldenamen (früher
  „supervisor“). Der DATEV-Export exportiert weiterhin alle freigegebenen Buchungen,
  auch bereits exportierte — „exportiert“ ist ein Vermerk, kein Filter; Buchungen in
  gesperrten Zeiträumen werden nicht vermerkt (die Sperre nimmt keinen Statuswechsel an),
  stehen aber im Journaleintrag des Exports.
- **Perioden:** Monate, keine Quartale; beliebige Reihenfolge; die Festschreibung ist
  accounti-intern (im EXTF-Kopf bleibt „Festschreibung“ 0). Kassenbuch, AfA-Lauf, Abgang und
  Abgrenzung prüfen vorab nur das Jahr — die Monatssperre greift dort erst beim Schreiben
  (gleiche Fehlerklasse, Meldung ohne Traceback, wo die Jahressperre gefangen wird).
  EB-Buchungen am 01.01. nimmt die Monatssperre an (Saldovortrag, Eröffnungssaldo); erkannt
  werden sie an der ID, die `abschluss/vortrag.py` meldet, und an ihrer Form (ohne Steuer,
  `EB-JJJJ`, eine Seite Saldenvortragskonto), in der Prüfregel an Belegnummer `EB-…` und
  01.01. Die Verfahrensdokumentation beschreibt die Ausnahme. `opos verbuchen
  --buchungsdatum` gilt nur für Eingangsrechnungen (Ausgangsrechnungen gehören in den
  Zeitraum ihrer Leistung) und nur für Belege, deren Monat gesperrt ist; „Eingang“ ist der
  Zeitpunkt, zu dem accounti den Beleg erfasst hat (`eingegangen_am`, oft der Import), nicht
  ein Eingangsstempel. Bei Bilanzierung lehnt accounti ein Buchungsdatum im nächsten
  Geschäftsjahr ab; die Vorsteuer einer erst im Folgejahr erfassten Rechnung bucht es auf
  1548 und zum Eingangsmonat um (Gesamttest Paket C, `docs/plans/2026-10-26-gesamttest-belege.md`); bei
  Einnahmenüberschussrechnung bucht es mit Hinweis. Bei `offen` mit Eingang in einem
  festgeschriebenen Monat weist accounti auf die Berichtigung der dortigen Voranmeldung
  hin, korrigiert sie aber nicht; liegt ein fester Tag nach einem offenen Eingangsmonat,
  warnt es, dass die Vorsteuer in den Eingangsmonat gehört (kein Wahlrecht). Der Schutz
  beim Jahreswechsel und die Jahressperre rechnen wie der ganze Abschluss mit dem
  Kalenderjahr — ein abweichendes Wirtschaftsjahr (`datev.wirtschaftsjahr_beginn`)
  berücksichtigen sie nicht. Weitere Buchungswege (Kasse, Kreditkarte,
  Marktplatz) haben noch kein eigenes Buchungsdatum.
  `ustva` berücksichtigt Befunde und Perioden noch nicht (Plausibilisierung aus Baustein 9
  unverändert).
- **Pflichtangaben** werden aus PDFs per Muster gelesen: Anschrift = „PLZ Ort“ irgendwo im
  Text, Steuernummer ohne Prüfziffer, Empfänger nur als „eigener Name oder eigene USt-IdNr.
  im Text“, Menge/Art nur bei E-Rechnungen; Nr. 9 (§ 14b-Hinweis) und Nr. 10 („Gutschrift“)
  werden nicht geprüft. Scans nur mit `--ocr` (Tesseract), sonst Hinweis. Standardmäßig nur
  Eingangsrechnungen (`regeln.pflichtangaben.belegarten`). § 13b, § 6a und § 3c erkennt die
  Regel an Steuerschlüssel, OSS-Erlöskonto, E-Rechnungs-Kategorie oder Hinweistext; die
  Angaben nach § 14a (USt-IdNr. beider Seiten, Hinweise) sind Warnungen und ohne Original
  nur teilweise prüfbar; das Land des Leistenden kommt aus Kontakt oder USt-IdNr., die
  eigene USt-IdNr. auf der Rechnung zählt dafür nicht.
- **Steuerschlüssel ./. Sachkonto:** Steuerautomatik nur aus der Kontenrahmen-Datei — der
  mitgelieferten `accounti/pruefung/skr03.yaml` (Starterset mit 42 Konten, am 21.10.2026
  gegen den DATEV-Kontenrahmen SKR 03 „Gültig für 2026“, Art.-Nr. 11174, abgeglichen) oder
  einer eigenen unter `pruefung.kontenrahmen_datei` (relativ zum Arbeitsverzeichnis);
  Automatikkonten außerhalb der Datei (z.B. 3010–3019, 3060–3069, 8721) kennt die Regel
  nicht. Für SKR04 gibt es keine Automatikdatei, nur Bereichsregeln (Erlös-, Aufwands-,
  Funktions-, Geld- und Personenkonten). Schlüsselbedeutung nach `steuer/kennziffern.py` (2,
  3, 8, 9, 18, 19, 91, 94). „Konto ohne Vorsteuer“ (`vorsteuer: false`) ist nur ein
  Hinweis; Privatkonten (1800 …) gelten wie in `kennziffern` als Gegenkonto, ein Schlüssel
  zwischen ihnen und Geldkonten ist ein Fehler.
- **Weitere Regeln:** Steuersätze aus `steuer/eu_steuersaetze.py` (Stand 2026), Drittland ohne
  Prüfung; bei Eingangsrechnungen zählt das Land der USt-IdNr. auf der Rechnung vor dem des
  Kontakts; ig. Erwerb nur gegen das vorhandene BZSt-Protokoll (der Prüflauf fragt nie beim
  BZSt an); Dubletten heuristisch (Kontakt + Brutto + Fenster; Buchungen je Beleg mit
  Bestellnummer/Belegposition); Nummernkreise nur für
  Ausgangsrechnungen (Präfix-Heuristik, Lücken nur zwischen kleinster und größter Nummer)
  und das Kassenbuch. Kontoauszugslücken: festgeschriebene accounti-Auszüge
  (`export/kontoauszuege`), Saldoverlauf nur mit erfassten Kontoauszugssalden
  (`abschluss saldo`), „Monat ohne Umsatz“ als Hinweis — die Auszugsnummern der Bank aus
  MT940/CAMT werden nicht gespeichert und sind nicht prüfbar. „Verspätet gebucht“ braucht den
  Journal-Zeitpunkt (Bestand von vor dem Journal: unbekannt, kein Befund).
- **Nachforderung:** `accounti aufgaben pruefen` (Baustein 8) liest den Abschnitt `pruefung`
  aus `config/accounti.yaml` im Arbeitsverzeichnis, nicht aus `--config`
  (`accounti nachfordern` nutzt `--config`). Ohne Abschnitt `pruefung` verhält sich
  `beleg_fehlt` wie der eingebaute Lauf. Erinnerung und Eskalation kommen aus Baustein 8.
  Die Anfrage hat keinen Anhang, Empfänger nur über die E-Mail des Kontakts (IBAN/Name) oder
  `--an`; der Versand ist nur gegen eine Attrappe getestet, es wurde keine E-Mail verschickt.
  Aufgaben entstehen nur für „Umsatz ohne Beleg“, nicht für andere Befunde.
- **Leistung:** Jede Buchungsänderung schreibt einen Journaleintrag mit Vorher/Nachher.
  Gemessen (SQLite, 5.000 Buchungen): `export datev` über die CLI 2,2 s (main 1,0 s; vor der
  Prüfung 17,9 s), 8.000 Buchungen in einem Flush 1,7 s (main 3,4 s), 40.000 in 9,0 s (main
  16,9 s).
- **Verfahrensdokumentation:** beschreibt, was Konfiguration, Datenbank und Code-Standards
  hergeben; Datensicherung, Organisation und Zeitpläne bleiben Platzhalter. Das LLM-Modell
  stammt aus dem Code-Standard — der Konfigurationsabschnitt `llm` wird von accounti nicht
  ausgewertet. Die PDF-Fassung ist schlicht (keine Tabellenlayouts, kein PDF/A, keine
  Signatur); frühere Fassungen werden nicht archiviert, nur ihr Hash steht im Journal.

## Doku-Bausteine

In README, CHANGELOG, Bauplan und Architektur eingearbeitet.
