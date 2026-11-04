# Einstellungen: Fachkern und CLI (Baustein 10c, Paket P4) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken. Ablageort beim Zusammenführen:
> `docs/plans/2026-10-26-oberflaeche-p4-einstellungen-kern.md` (mit dem ersten PR, danach
> fortgeschrieben). **Drei PRs nacheinander** (D28), je Squash-Merge gegen `main`:
> `feat/oberflaeche-p4a-einstellungen-lesen` (Schritte 0–6), `feat/oberflaeche-p4b-einstellungen-schreiben`
> (Schritte 7–10, 12, 13, 16) und `feat/oberflaeche-p4c-steuer-vier-augen` (Schritte 11, 14, 15);
> Schritt 17 läuft je PR für dessen Teil. Ein PR zweigt erst ab, wenn der vorige auf `main` ist.
>
> **Fassung 3** (26.10.2026): Befunde der gegnerischen Prüfung von Fassung 1 und der Gegenprüfung
> von Fassung 2 (Kennung „G-…“) eingearbeitet (Abschnitt „Prüfbefunde und Umgang“ am Ende).
> Grundlage: Spec 10c (`spec-10c-oberflaeche-einrichtung.md`, Stand „entschieden“, Ablage beim
> Merge `docs/specs/2026-10-26-oberflaeche-einrichtung.md`) und Skizzen (`spec-10c-skizzen.md`, vor
> allem 6b und 7). Code gelesen auf `main` 87c6c8d (= 18faeaa + #32, Paket A gemergt) und in den
> Worktrees `gt-abschluss` (Paket F, 410cc64), `gt-steuer-datev` (Paket E, 243754f), `gt-belege`
> (2d1aec2), `gt-debitoren` (2f62e17) und `web-oberflaeche` (10b-1, 43031a7). Seit Fassung 2 hat
> keiner dieser Stände Lader, Konfigurationsmodule, Migrationen oder `yaml.safe_load`-Stellen
> außerhalb der Positivliste geändert, die Vorlage nur in einem Kommentar (nachgeprüft per
> `git diff`). **Abzweigen erst, wenn 10b-1 und alle
> `fix/gesamttest-*`-Branches auf `main` sind** (Spec Abschnitt 9, R2). Vor Schritt 0 die im
> Abschnitt „Was P4 vorfindet“ genannten Signaturen auf `main` neu lesen; weicht etwas ab, gilt
> `main`, und dieser Plan wird an der Stelle nachgezogen.
>
> **Vor Schritt 7 (P4b) vom Nutzer zu entscheiden:** D6 (Standards nicht einfrieren, Abweichung
> vom Wortlaut von F1; Ausgleich über Journaleinträge der Standards, keine Spalte). Siehe „Offene
> Punkte“ 5. **D26 ist entschieden** (26.10.2026, wie vorgeschlagen): Ziel-Host-Felder sind K2;
> die Ergänzung von Anhang A der Spec steht als Doku-Baustein „Spec 10c, Anhang A“ und wird mit
> P4b eingetragen.

**Ziel:** Einstellungen leben ab der ersten Änderung in der Datenbank der Gesellschaft: nur
anfügend versioniert, mit Person, Grund, Quelle, Hash-Kette und Journal. Die YAML bleibt Startwert
und kann Abschnitte festlegen; Betriebswerte kommen immer aus Datei oder Umgebung. Ein zentraler
Abschnittsleser ersetzt jedes `yaml.safe_load` der Konfiguration. Alle Lader behalten ihren
Modelltyp und ihre Signatur (Ausnahme: `lade_oss(pfad, zeitraum)` und
`gewinnermittlung_angegeben(pfad, wj)` bekommen den Zeitraum als Pflichtparameter, D14), sehen
aber je Befehl bzw. Anfrage genau einen Stand der Datenbank.
Wer eine Kontrolle abschwächen will, stellt einen Antrag, den eine zweite Person bestätigt.
Periodenwerte verhindern, dass eine Änderung auf abgeschlossene Zeiträume zurückwirkt.
Geheimnisse stehen nur als Chiffrat in der Datenbank. Die CLI kann alles, was P5 später im Browser
anbietet: zeigen, setzen, Verlauf, prüfen, Datei-Stand übernehmen, exportieren, Geheimnisse und
Anträge. Dazu kommt das Vier-Augen-Prinzip für Steuermeldungen (`elster.vier_augen`). P4 hat
**keine neuen Seiten**. Bestehende Web-Wege binden den Stand der aktiven Gesellschaft, damit
Datenbank-Werte dort wirken.

**Spec:** Abschnitte 1.3, 4 (Leitlinien 1, 6, 7), 5 (E1–E6), 6.4 und 6.10 (A113–A119) · Anforderungen
**A39–A54, A122, A124, A125** · Akzeptanz **AK24 (CLI-Teil), AK25, AK26 (Fachkern), AK27
(Fachkern + CLI), AK28 (Fachkern), AK30 (CLI-Teil), AK31–AK35, AK76–AK81 (AK81 ohne Seite),
AK100** · Anhang A (Inventar, Stufen, Perioden) · **Baut auf:** 10a (Kontext, Registry, Rechte in
der CLI, Tresor, Sicherung, Aufbewahrung), 7 (Journal, Schreibsperre, Sperren,
Verfahrensdoku), 9 (`elster.freigabe`, Protokoll), 10b-1 (Web-Gerüst, `angemeldet`, i18n),
Paket A (`lade_buchhaltung` mit einer Kontenrahmen-Quelle, `db upgrade`, `SCHEMA_STAND`),
Paket F (`abschluss.konfiguration.wirtschaftsjahr`), Paket E (`lade_abschluss` mit
Marktplatzkonten) · **Nicht hier:** alle Seiten unter `/einstellungen`, Verwaltungsmodus,
Benachrichtigung (P5); Benutzer und Einladung (P6); Assistent und `einrichtung.stand` (P7);
„wartet auf eine zweite Person“ in Übersicht, Fristenliste und `/freigaben`-Karten (P2).

```
 CLI (Typer)                                         Web (FastAPI, 10a/10b-1)
   Callback richte_kontext_ein ─ neuer Stand           Middleware Einstellungsstand ─ neuer Stand je Anfrage
   --db-Parameter (jede Ebene) ─ binde + Schnappschuss angemeldet / api_zugang ─ binde Gesellschaft + Schnappschuss
        │                                                   │
        ▼                                                   ▼
 einstellungen/leser.py   ContextVar _STAND ─▶ Stand(Quelle, Schnappschuss, Dateien)
   lies_abschnitt(pfad, name)  Vorrang E2: Umgebung (${VAR}) › Festlegung › Datenbank › Datei › Standard
   Betriebsabschnitte/-felder immer aus der Datei · ${…} nur aus der Datei · Geheimnisse nie im Modell
   fehlende Datei = {} · mit_quelle(…, stichtag) · ueberlagert({abschnitt: daten}) · pruefmodus · parse_text
        │  (alle Lader: lade_firma, lade_buchhaltung, lade_elster, … — Signatur und Modell unverändert)
        ▼
 einstellungen/dienst.py   speichere · setze_feld · setze_periodenwert · uebernehme_aus_datei
   pruefung.py (Modelle über die Lader + Querprüfungen) · perioden.py (Periodenwerte, Sperren)
   stufen.py (K1/K2/K3, Anhang A) · Anträge · Geheimnisse · verlauf.py · export.py
        │
        ▼
 db/tabellen_einstellungen.py  einstellungen (nur anfügen, Hash-Kette je Abschnitt, Trigger SQLite + PostgreSQL)
                               einstellungsantraege (Status nur aus „offen“) · geheimnisse (AES-GCM, Tresor)
 pruefung/journal.py (7)       einstellung_geaendert · einstellung_beantragt · antrag_bestaetigt · geheimnis_ersetzt …
                               journal pruefen: Teilstände je Feld (D27)
 elster/freigabe.py (9)        offene_freigabe(…, vier_augen) — zwei Personen, eine Abgabe verbraucht beide
```

---

## Umsetzung P4a — Stand und Abweichungen von `main`

Abgezweigt am 04.11.2026 als `feat/oberflaeche-p4a-einstellungen-lesen` von `main`
117275e (10b-1, alle Gesamttest-Pakete, 10c P1 = #40 gemergt). Wo `main` vom Plan abweicht,
gilt `main`; die Stellen stehen hier und an den Schritten.

- **Kopf der Migrationen:** `alembic heads` zeigt genau `1dd2f6b7c6c8` (P1, Vorlieben an
  `auth_benutzer`) = `db.SCHEMA_STAND`. P4a kettet sich daran (Offener Punkt 8).
- **YAML-Lesestellen:** Auf `main` liest die Konfiguration fast überall über
  `konfiguration.lies_yaml` (eine Stelle, Meldung bei kaputtem YAML) bzw.
  `betrieb/gesellschaften.lies_yaml`. Direkt `yaml.safe_load` steht noch an 12 Stellen in
  10 Dateien (Plan: 30 in 25): `konfiguration.py` (`lies_yaml`, `lade_eigene_firma`),
  `elster/konfiguration.py` (`lade_oss`, `lade_mandant`), `befehle/gesellschaft.py`
  (`_wirtschaftsjahr`), `betrieb/gesellschaften.py` (`lies_yaml`) und die Daten-Dateien
  der Positivliste. Schritt 4 baut damit vor allem die Aufrufer von `lies_yaml` um; dass
  `lies_yaml` danach entfällt, prüft `test_kein_lies_yaml_mehr`.
- **Signaturen** wie im Plan: `lade_buchhaltung(pfad)`, `lade_abschluss(pfad)`
  (mittelbar `buchhaltung`, `integrationen`, `datev`), `lade_wirtschaftsjahr_beginn(pfad)
  -> date | None`, `Dienste` (Engines je URL, `pruefe_schema`, `PFLICHTSPALTEN`),
  `angemeldet`/`api_zugang` (async), `richte_kontext_ein(ctx, gesellschaft)`. P1 ist
  gemergt: `angemeldet` und `vielleicht_angemeldet` teilen den Kern `_lade` (Offener
  Punkt 7).
- **Kopf-Tests (G-M1, Offener Punkt 8):** P1 hat die Regel schon eingeführt
  (`tests/test_migration_regeln.py`: kein relatives Downgrade, kein `get_current_head()`,
  keine Aussage über „(head)“ außer der Zählung). `git grep` auf dem Abzweigpunkt findet
  keinen kopfabhängigen Test mehr; die P1-Tests (`test_migration_web.py`,
  `test_db_upgrade.py`, `test_api_schema.py`) führen `VORLIEBEN` fest und lesen `VOR` aus
  dem `ScriptDirectory`. Umzustellen war nichts; nachgeprüft mit P4a als Kopf (Schritt 1).

---

## Kontext und Abgrenzung

### Stand der Grundlage (gelesen am 26.10.2026)

- **`main` 87c6c8d** (#32 = Paket A auf 18faeaa). Die Konfiguration wird auf `main` an **30
  Stellen in 25 Dateien** mit `yaml.safe_load` gelesen, 10b-1 verschiebt eine Stelle aus `cli.py`
  nach `klassifikation/lernen.py` und bringt `i18n/__init__.py` mit (31 in 26). Jeder Lader liest
  die Datei bei jedem Aufruf neu. Fehlertexte nennen den Abschnittspfad.
- **Paket A (#32, auf `main`)** ändert `konfiguration.py`:
  - `_fehlertext(fehler, abschnitt, herkunft)` nennt jetzt den richtigen Abschnitt.
  - `KONTENRAHMEN = ("SKR03", "SKR04")` mit einem Validator in `Buchhaltung` (Tippfehler sind
    Fehler).
  - `lade_buchhaltung` übernimmt `mandant.kontenrahmen`, wenn `buchhaltung.kontenrahmen` fehlt,
    und bricht ab, wenn beide sich widersprechen.
  - `export/datev_stammdaten` liest den Kontenrahmen nur noch über `lade_buchhaltung`.
  - Die Beispielkonfiguration führt `kontenrahmen` unter `buchhaltung` (N1 ist dort behoben).
  - Neu sind `db.SCHEMA_STAND`, `db.stemple`, `db/upgrade.py` (`accounti db upgrade` leitet den
    Stand ohne Versionsvermerk aus Tabellen und Spalten ab) und die Migration `6d38d11fc348`.
  - `betrieb/cli.Wurzelgruppe` und `richte_kontext_ein` setzen den Kontext und die `default_map`
    jedes Befehls.
- **Paket F (`gt-abschluss`)** bringt `abschluss/konfiguration.py`:
  `Wirtschaftsjahr`, `wirtschaftsjahr(jahr, beginn)`, `wirtschaftsjahr_zum(tag, beginn)`,
  `lade_wirtschaftsjahr_beginn(pfad)` (liest noch „JJJJ-MM-TT“) und
  `AbschlussEinstellungen.wirtschaftsjahr_beginn`. Die Konvention lautet: `--jahr` ist das
  Kalenderjahr des WJ-Endes. Dazu kommt die Migration `2f7c7043043e`.
- **Paket E (`gt-steuer-datev`)**: `lade_abschluss` liest zusätzlich `lade_integrationen`
  (`marktplatz_konten`). Neu sind OSS-Konten je Land, EU-Steuersätze mit Gültigkeit und
  Kursdifferenzkonten (Beispielkonfiguration).
- **`gt-belege`, `gt-debitoren`**: je eine Migration (`46371a6681c2`, `a14acef69fae`). Dazu kommt
  der Validator `Rechnungseinstellungen.nummernformat` (`gt-debitoren`).
- **10b-1 (`web-oberflaeche`)** bringt:
  - die Migrationen `d5a849692843` und `e7153706b43a`
  - `api/dienste.Dienste` (Engines je Gesellschaft, `pruefe_schema`, `PFLICHTSPALTEN`)
  - `api/sitzung.angemeldet` (async), `gesellschaft_db` (synchroner Generator), `api/rest.api_zugang`
    (async)
  - Änderungen an `seiten/freigaben.py` (die Seite gibt es seit 10a, c019c2a; USt-VA-Freigabe im
    Browser über `gib_frei(s, v, a.benutzer.name)`)
  - `i18n` mit dem Vollständigkeitstest
- **Alembic:** Sechs Branch-Migrationen: `6d38d11fc348` (A), `2f7c7043043e` (F), `46371a6681c2`
  (belege), `a14acef69fae` (debitoren) und `d5a849692843` (10b-1) hängen an `ddc9a184ddb4`,
  `e7153706b43a` (10b-1) hängt an `d5a849692843`; Paket E bringt keine. Auf `main` ist
  `6d38d11fc348` jetzt Kopf (`SCHEMA_STAND`). Beim Mergen setzt jede später gemergte Kette ihre
  unterste `down_revision` auf den neuen Kopf. P4a nimmt den Kopf, den `alembic heads` beim
  Abzweigen zeigt, und zieht `SCHEMA_STAND` nach. Migrationstests, die am Kopf hängen
  (`downgrade -1`, „`<rev>` (head)“, `get_current_head()`), brechen dabei; Schritt 1 stellt sie um
  (G-M1). `main` macht es in `tests/test_migration_belegvollstaendigkeit.py:145` schon so
  („head ist inzwischen eine spätere Migration“).

### Was P4 vorfindet (nach dem Merge der Gesamttest-Branches)

| Baustein | Was P4 nutzt | Wo |
|----------|--------------|----|
| Kontext (10a, Paket A) | `aktueller_kontext()`, `Kontext.standardwerte["db"]`, `richte_kontext_ein(ctx, g)`, `standardwerte_fuer` (Baumlauf über alle Befehle) | `betrieb/kontext.py`, `betrieb/cli.py` |
| Rechte in der CLI (10a) | `befehlsrecht_oder_ende(db, config, recht, person)`, `pruefe_befehlsrecht`, `frage_einmalcode` (`ACCOUNTI_EINMALCODE`), `benutzer_eingerichtet(db)`, `aktueller_benutzername()` | `auth/cli.py` |
| Person (7) | `aktuelle_person(von)`, `journal_kontext(person=…)`, `geprueft_als` | `pruefung/person.py` |
| Vier-Augen Zahlung (6) | `person_fuer_freigabe`, `betriebssystem_benutzer()` (Anmeldename über die UID, nicht über die Umgebung) | `zahlung/freigabe.py` |
| Journal (7) | `schreibe(session, vorgang, objekt_typ, objekt_id, vorher=, nachher=, grund=, bezug=, person=)`, `schreibsperre(verbindung)`, `kanonisch` (ohne `default=`, nur JSON-Typen), `_pruefe_verlauf` (Vorher gegen letzten Nachher-Stand über die Vereinigung der Schlüssel) | `pruefung/journal.py` |
| Schutz (7) | `db.GESCHUETZT`, ORM-Sperre `before_update`/`before_delete`, `do_orm_execute`, SQLite-Trigger über `after_create` (PostgreSQL bisher nur ORM und Hash-Kette) | `db/__init__.py`, `db/tabellen_pruefung.py`, `pruefung/ereignisse.py` |
| Tresor (5) | `verschluessele(daten, schluessel, bezug)`, `entschluessele`, `lade_schluessel()` (`ACCOUNTI_SCHLUESSEL`) | `bank/tresor.py` |
| ELSTER (9) | `freigabe.speichere`/`gib_frei`/`offene_freigabe`/`inhalt_hash`, `ustva.uebermittle(…, modus, …)`, `dauerfrist.gib_dauerfrist_frei`/`uebermittle_dauerfrist`, `uebermittlung.waehle_uebermittler` (PIN-Datei) | `elster/` |
| Sperren (7, 12) | `repo_elster.lade_freigaben`/`lade_uebermittlungen`, `repo_abschluss.lade_gesperrte_jahre`, `pruefung.perioden.lade_perioden` | `db/`, `pruefung/` |
| Sicherung (10a) | sichert **alle** Tabellen aus `Base.metadata`, stellt nur in eine leere Umgebung wieder her, prüft die Gesellschaft im Manifest | `betrieb/sicherung.py` |
| Aufbewahrung (10a) | `BESTAND` (Tabelle, Spalte, Bezeichnung, Unterlage), `FRISTEN` | `betrieb/aufbewahrung.py` |
| Verfahrensdoku (7) | `_Doku.lade(lader, name)`, `_Doku.roh()` (ganze Datei), `erzeuge(s, config, *, db_url, archiv, stand: date \| None, system_db, gesellschaft)` | `pruefung/verfahrensdoku.py` |
| Lader-Wächter | fast jeder Lader endet bei fehlender Datei an `pfad.is_file()` (Standards bzw. „Vorlage kopieren“), bevor er etwas liest | `konfiguration.py`, `elster/`, `erechnung/versand.py`, `aufgaben/`, `belege/kanaele/`, `abschluss/`, `integrationen/`, `mahnwesen/`, `bank/`, `pruefung/`, `anlagen/`, `zahlung/` |

### Abgrenzung

- **P4 liefert keine Seiten.** Einziger sichtbarer Web-Unterschied ist die Meldung „erste Freigabe
  – eine zweite Person muss freigeben“ bei der USt-VA-Freigabe in `/freigaben`, wenn
  `elster.vier_augen` an ist. Sie läuft über die vorhandene `meldung.html`, der Text steht in
  `i18n/en.yaml`.
- **P5** baut auf der Schnittstelle unten auf: Formulare, Verwaltungsmodus
  (`Bestaetigung(k2=True, verfahren="verwaltungsmodus")`), Anträge im Browser, Herkunft und
  Abweichung auf der Seite, Verlauf, Benachrichtigung (`Ergebnis.meldepflichtig`),
  Experten-Ansicht (`leser.parse_text`), Docker-Probe im Browser (AK24-Rest) und der 409 mit
  Gegenüberstellung (AK28, AK83).
- **P2** zeigt „wartet auf eine zweite Person“ und „1 von 2 Freigaben“. Die Daten dafür liefert
  `elster.freigabe.stand_der_freigaben` aus Schritt 11.
- **P7** nutzt `dienst.speichere(…, quelle="assistent")` mit `vollstaendig=false` und den
  Datenbank-Abschnitt `einrichtung`. Die Fachfunktion `einrichtung.stand` gehört zu P7.

### Berührungspunkte mit P1 (läuft parallel)

P1 ändert Vorlagen, CSS, Navigation, `auth_benutzer` (Vorlieben-Spalten) und Teile von `api/`.
P4 berührt in `api/` nur wenig:

- `app.py`: eine Middleware, registriert **vor** `app.add_middleware(Sicherheit)`
  (`web-oberflaeche` `app.py:71`; in Starlette liegt die zuletzt hinzugefügte außen). So gilt die
  Absprache aus dem P1-Plan (R-P1-4, Offener Punkt 4): Sicherheit außen mit der 500-Seite,
  `Einstellungsstand` innen (G-N1).
- `sitzung.angemeldet` und `rest.api_zugang`: je ein Aufruf `binde_gesellschaft`
- `dienste.py`: `quelle(kuerzel)`, Name ohne Registry beim Start (D21)
- `seiten/freigaben.py`: Vier-Augen-Meldung (erst P4c)

Gemeinsam sind die Alembic-Kette, `.github/workflows/ci.yaml` (P4a ergänzt einen
PostgreSQL-Dienst) und `docs/betrieb.md`. Das später gemergte Paket setzt
`down_revision` und `SCHEMA_STAND` auf den neuen Kopf (A118, AK61) und stellt die Kopf-Tests des
zuerst gemergten auf feste Revisionen um. Beide hängen ihre eigenen Migrationstests an die
eigene Revision, nicht an den Kopf (G-M1, Offener Punkt 8). Konflikte in `sitzung.py` löst P4 durch
einen Aufruf am Ende von `angemeldet`, ohne die Struktur zu ändern. Ist P1 vorher auf `main`,
sitzt die Bindung im gemeinsamen Kern von `angemeldet` und `vielleicht_angemeldet` (P1-Plan
R-P1-4), damit sie auch für Hilfe und 404 gilt (G-N1).

---

## Entscheidungen

Die Spec legt E1–E6 fest (B, B, B, B, B, B). Hier steht, wie P4 sie technisch umsetzt, und jede
Stelle, an der der Plan von der Spec abweicht oder sie präzisiert.

1. **D1 — Ein Paket `accounti/einstellungen/`, Lader bleiben, wo sie sind.**
   - `leser.py` (lesen, ohne Importe aus Fachmodulen, keine Zyklen)
   - `inventar.py` (Daten: Abschnitte, Betriebs-, Geheim-, Perioden- und Kontofelder,
     meldepflichtige Felder)
   - `stufen.py` (Anhang A als Daten)
   - `perioden.py`, `pruefung.py`, `dienst.py`, `verlauf.py`, `export.py`

   Dazu kommen `db/tabellen_einstellungen.py`, `db/repo_einstellungen.py`,
   `models/einstellungen.py` und `befehle/einstellungen.py` (wird automatisch eingehängt).
   *Grund:* Das Muster der Bausteine bleibt (Spec E5 B). Die Lader in den Fachmodulen behalten
   ihre Signatur (`lade_x(pfad)`; Ausnahmen mit Zeitraum: `lade_oss`, `gewinnermittlung_angegeben`,
   D14). Nur ihr Inneres liest über `lies_abschnitt`.
2. **D2 — Der Abschnittsleser liefert Rohdaten.** `lies_abschnitt(pfad, name) -> dict` gibt den
   wirksamen Abschnitt als Zuordnung zurück. Die Lader validieren wie bisher mit ihrem Modell, mit
   ihren Querbezügen (`lade_zahlung` nimmt den Auftraggeber aus `mandant`) und ihren
   Fehlertexten. *Grund:* Es gibt kein zweites Modell je Abschnitt und keine Doppelung der
   Lader-Logik. Der Modelltyp bleibt gleich (A41).
3. **D3 — Bindung in der CLI über die `--db`-Parameter, Schnappschuss sofort.**
   `richte_kontext_ein` legt einen neuen `Stand` in die Kontextvariable. Danach hängt es an
   **jeden** Click-Parameter `db` im Befehlsbaum einen Callback (Baumlauf wie
   `standardwerte_fuer`, bestehende Callbacks werden verkettet). Der Callback bindet die
   Datenbank und nimmt **sofort** den Schnappschuss, also beim Parsen und vor dem Rumpf des
   Befehls. Ein Befehl ohne `--db` nutzt beim ersten Lesen `kontext.standardwerte["db"]`
   (Gesellschaft bzw. `ACCOUNTI_DB`), sonst `befehle.STANDARD_DB` (`sqlite:///accounti.db`, der
   Standard von `DB_OPTION`), also dieselbe Datenbank, die jeder andere Befehl ohne Angabe nimmt.
   „Nur die Datei“ gilt in der CLI nicht mehr. Die vier Befehle mit `--config`, aber ohne `--db`
   (`fristen`, `pruefen regeln`, `kanaele connectoren`, `elster pin`) bekommen `db: str =
   DB_OPTION`. Ein Strukturtest verlangt das für jeden Befehl mit `config`; die Ausnahmeliste ist
   leer und braucht je Eintrag einen Grund.
   *Gründe:*
   - (a) Die Spec verlangt die Datenbank des Befehls, nicht die der Datei (E5).
   - (b) Ein später, fauler Schnappschuss über eine zweite Verbindung stünde unter SQLite hinter
     der eigenen Schreibsperre des Befehls (EXCLUSIVE nach einem Cache-Überlauf) und wartete
     30 s auf sich selbst.
   - (c) A54: ein Stand je Befehl.
   - (d) Ohne Ersatzwert zeigte `fristen` „monatlich“ aus der Datei, während `ustva` aus
     `accounti.db` „quartal“ liest.

   Der Spec-Satz „die CLI setzt sie im Callback“ ist so umgesetzt: Der Callback legt den Stand an,
   die Parameter binden ihn.
4. **D4 — Bindung im Web über Middleware und `angemeldet` statt `gesellschaft_db`.** Eine reine
   ASGI-Middleware `Einstellungsstand` legt je HTTP-Anfrage einen neuen, ungebundenen `Stand` an
   und setzt ihn am Ende zurück. Die async-Dependencies `angemeldet` (Sitzung) und `api_zugang`
   (Token) binden ihn an die Gesellschaft: `Dienste.quelle(kuerzel)`, Konfigurationspfad, im
   Threadpool mit sofortigem Schnappschuss. *Gründe:* `gesellschaft_db` ist ein synchroner
   Generator. FastAPI führt ihn in einem kopierten Kontext im Threadpool aus, ein dort gesetztes
   `ContextVar` sähe der Endpunkt nicht. Gebunden wird ein **veränderliches** Stand-Objekt, das
   in allen Kopien dasselbe ist. Viele Routen lesen Lader außerhalb der Sitzung (z. B.
   `lade_zahlung(a.gesellschaft.konfiguration)`). Abweichung von A47 im Wortlaut, nicht in der
   Wirkung.
5. **D5 — Ungebundener Stand im Web: fail-closed.** Liest Code in einer Web-Anfrage einen
   Abschnitt mit Datenbank-Ziel, ohne dass der Stand gebunden ist, oder mit einem anderen
   Konfigurationspfad als dem der gebundenen Gesellschaft, folgt `EinstellungsquelleFehlt` (500,
   im Test sichtbar). Betriebsabschnitte (`server`, `auth`, `gesellschaften`, `einstellungen`)
   gehen immer. In der CLI gilt E5 wörtlich: Die Datenbank des Befehls gilt auch bei abweichendem
   `--config`. **Ausnahme in der CLI:** Gehört der gelesene Pfad (aufgelöst) zum
   `konfiguration`-Eintrag einer **anderen** Gesellschaft der Registry als der gebundenen und nicht
   zugleich zu ihr, folgt ebenfalls `EinstellungsquelleFehlt`. Wer über Gesellschaften hinweg liest
   (`gesellschaft liste|zeigen`, `dienste_aus_kontext`), tut das je Gesellschaft unter
   `mit_quelle(DatenbankQuelle(g.datenbank), g.konfiguration)`. Sonst zeigte `gesellschaft liste`
   für b den Kontenrahmen aus der Datenbank von a. Außerhalb von CLI und Web (Unit-Tests,
   Werkzeuge) gibt es keinen Stand. Dann gilt nur die Datei, wie heute.
6. **D6 — Die erste Version ist der Roh-Abschnitt der Datei plus Änderung, nicht `model_dump()`.**
   **Abweichung vom Wortlaut von E2/F1** („Datei bzw. Standard plus Änderung“), **Freigabe durch
   den Nutzer nötig vor Schritt 7** (Offener Punkt 5).
   „Vollständig“ (E2) heißt hier: Alles, was die Datei für den Abschnitt angibt, steht in der
   Version. Die Datei wird danach für diesen Abschnitt nicht mehr gelesen, außer Betriebs- und
   Platzhalterfeldern. Es gibt also keine stille Mischung aus Datei und Datenbank. Standards des
   Modells werden **nicht** eingefroren.
   *Gründe:* Einfrieren über die Lader-Ergebnisse schriebe abgeleitete Werte als scheinbar
   gepflegte fest: `zahlung.auftraggeber` aus `mandant` (eine spätere Änderung der Firmen-IBAN käme
   im Zahlungsverkehr nicht mehr an), die Kontenrahmen-Standards von `abschluss` und `kasse`, die
   OSS-Konten, die `lade_elster` in `kennziffern_konten` einmischt. Einfrieren über das Modell allein
   scheitert dort, wo der Lader vor der Validierung ergänzt (`abschluss.ergebnis_konto` ist ohne
   Kontenrahmen-Standard Pflicht), und Optionen mit `None` überdeckten die Ersatzwerte der Lader
   (`setdefault`).
   *Ausgleich für die Nachvollziehbarkeit* (GoBD, A51; Gegenprüfung G-M4). Die accounti-Version
   taugt dafür nicht: Sie ist immer `0.1.0-dev` (`src/accounti/__init__.py:3`, so genannt in
   `pruefung/verfahrensdoku.py:173, 736`). Darum hält die Datenbank die Standards selbst fest:
   - `pruefung.standards()` liefert je Abschnitt die Ergebnisse der Lader aus `inventar.LADER` auf
     einem leeren Stand (ohne Datei, ohne Datenbank, wie Golden „leer“), einmal mit SKR03 und
     einmal mit `buchhaltung.kontenrahmen: SKR04`. Die Werte stehen in Normalform (D9), Fehler als
     Klasse und Text ohne Pfad (Serialisierung wie D20).
   - Weicht das vom zuletzt festgehaltenen Stand ab, schreibt `dienst.halte_standards_fest` je
     betroffenen Abschnitt einen Journaleintrag `einstellung_standards` (objekt_typ
     `einstellungsstandard`, objekt_id = Abschnitt, nur die geänderten Pfade alt → neu, Person
     „accounti“, Grund „Programmstand“; Teilstände nach D27). Das geschieht in `db upgrade` (dem
     dokumentierten Schritt jedes Updates) und in `speichere` vor der ersten Version der
     Transaktion. Hat die Datenbank keine Version und bekommt sie keine, wird nichts geschrieben.
   - `serve` beim Start und `pruefen` schreiben nicht, sie warnen nur, wenn die Standards vom
     letzten Eintrag abweichen („nach dem Update `accounti db upgrade` ausführen“).
   - Der Anhang der Verfahrensdokumentation (Schritt 15) führt diese Einträge wie Änderungen der
     Einstellungen. So ist der wirksame Wert zum Stichtag aus Version und Standard-Eintrag
     bestimmbar, auch nach einem Update **zwischen** zwei Versionen.

   Der Vorschlag der Gegenprüfung, je Version einen `standard_hash` (oder eine Build-Kennung) zu
   speichern, ist nicht gewählt. Ein Hash je Version zeigt nur den Stand beim Schreiben. Ein Update
   zwischen zwei Versionen bliebe unsichtbar, aus demselben Grund wie bei M8. Außerdem nennt er
   keine Werte. Da keine Spalte nötig ist, bleibt die Entscheidung zu D6 „vor Schritt 7“. Dazu
   bleiben der Golden-Test „leer“ (D20) als Wächter und die Regel, jede Standard-Änderung im
   CHANGELOG unter „Geändert“ mit altem und neuem Wert zu nennen (`docs/architektur.md`,
   Erweiterungspunkte). Bei F1 wörtlich bleibt der Eintrag für abgeleitete und später
   hinzukommende Felder nötig.
   *Alternative, falls der Nutzer bei F1 wörtlich bleibt:* Die erste Version friert die eigenen
   Felder des Abschnitts ein (`Modell.model_validate(roh).model_dump(mode="json", by_alias=True,
   exclude_none=True)`, ohne Betriebs-, Platzhalter- und Geheimfelder). Ausgenommen sind die
   Felder in `inventar.ABGELEITET` (Kontenrahmen-Standards von `abschluss` und `kasse`,
   `zahlung.auftraggeber` aus `mandant`, OSS-Anteil von `elster`), mit einem Test je Eintrag. Aufwand
   etwa ein Tag mehr in Schritt 7.
7. **D7 — Betriebs- und Platzhalterfelder werden beim Lesen aus der Datei übernommen, beim
   Schreiben abgewiesen.**
   - **Betriebsabschnitte:** `database`, `server`, `auth`, `gesellschaften`, `einstellungen`.
   - **`BETRIEBSFELDER`** nach A42, ergänzt um alle Pfadfelder:
     - `elster.eric.*`, `pruefung.archiv`, `pruefung.kontenrahmen_datei`
     - `belegkanaele.webhook.host|port`, `belegkanaele.email[name].ca_datei`
     - `ustid_pruefung.url`, `bank.fints.produkt_id`
     - `abschluss.kontenzuordnung`, `anlagen.rechtsstand`, später `bwa.schema`

   Quelle der Wahrheit ist eine **Markierung am Feld**: `Field(json_schema_extra={"accounti":
   "betrieb"})` über den Typ `Betriebsfeld[...]` in `einstellungen/inventar.py`. Der Strukturtest
   verlangt: Jedes markierte Feld steht in `BETRIEBSFELDER` und umgekehrt. Als Netz gilt
   zusätzlich: Ein Feld vom Typ `Path` oder mit einem Namen wie
   `datei|pfad|archiv|zuordnung|schema|rechtsstand|ordner` trägt die Markierung oder steht mit
   Grund in `KEIN_BETRIEBSFELD` (etwa `belegkanaele.email[].ordner|ziel_ordner`: IMAP-Ordner,
   kein Dateipfad; die „Ordnerpfade“ aus Anhang A sind im Modell nur diese).
   *Grund:* Ein im Browser gesetzter Pfad ließe den Server beliebige Dateien lesen.
   **Platzhalterfelder:** Steht in der Datei an einem Blatt `${VAR}`, bleibt das Blatt auch bei
   Datenbank-Version der Platzhalter, den der Lader wie heute auflöst. Das ist E2 Stufe 1
   „Umgebung schlägt alles“ (AK76), feldweise. Listen von Zuordnungen (`belegkanaele.email`,
   `belegkanaele.connectoren`) werden über `name` zugeordnet.
   **`${…}` nur aus der Datei** (Schutz der Umgebung, Prüfbefund H1): Die Lader setzen
   Umgebungsvariablen überall im Abschnitt ein (`_ersetze_variablen` in `lade_versand` und
   `lade_aufgaben_einstellungen`, `loese_auf` für Postfach-Passwörter und Connector-Kopfzeilen).
   Ein `${ACCOUNTI_SCHLUESSEL}` in `versand.betreff`, in `smtp.passwort` mit eigenem `smtp.host`
   oder in `connectoren[].kopfzeilen` gäbe sonst Tresor-Schlüssel und Datenbank-Passwörter an
   jeden, der Einstellungen ändern darf. Darum:
   - **Schreiben:** Jedes Blatt (auch Listenelement und Schlüssel einer Zuordnung) der neuen Daten,
     das `${` enthält, ergibt `PlatzhalterError`, außer es ist **gleich** dem Blatt der Datei an
     demselben Pfad (so bleibt `uebernehmen --aus-datei` mit `${SMTP_PASS}` möglich). Das gilt für
     alle Felder, auch für Geheimfelder (D8). Solche gleichen Platzhalterblätter werden **nicht
     gespeichert**, ebenso keine Betriebsfelder (G-N3). Beides legt der Leser ohnehin aus der Datei
     darüber. Eine in der Datei umbenannte Variable (`${SMTP_PASS}` → `${SMTP_PASSWORT}`) ließe
     sonst einen veralteten Platzhalter in der Version zurück, und `pruefen` wäre rot.
   - **Lesen:** Der Leser löst nichts auf, gibt aber auch kein `${` aus der Datenbank weiter. Ein
     Blatt der Version mit `${` (nur über rohes SQL möglich) wird durch das Blatt der Datei
     ersetzt, wenn die Datei an demselben Pfad einen Platzhalter hat. Sonst entfällt es (der Lader
     nimmt den Standard bzw. meldet das Pflichtfeld), und `pruefen` meldet einen Fehler
     („Platzhalter in der Datenbank an versand.smtp.passwort wird nicht aufgelöst“). Betriebsfelder
     einer Version entfallen vor dem Überlagern. Fehlen sie in der Datei, gilt der Standard, nicht
     die Version (A42).
8. **D8 — Geheimnisse kommen nie aus der Datenbank in ein Modell.** Geheimfelder sind
   `versand.smtp.passwort`, `llm.api_key`, `aufgaben.benachrichtigung.webhook.url` und
   `elster.pin`, das kein Konfigurationsfeld ist. Gelesen werden sie nur über
   `einstellungen.geheimnis(name)` an den **vier Verbrauchsstellen**:
   - SMTP-Anmeldung in `erechnung/versand`
   - `klassifikation/llm`
   - Webhook-Kanal in `aufgaben/benachrichtigung`
   - `elster/uebermittlung.waehle_uebermittler`

   Vorrang: Wert im Modell (aus Datei-`${VAR}` aufgelöst) → Geheimnis der Datenbank. Die
   PIN-Datei geht vor `elster.pin` (E4). Modelle, Anzeigen, Journal-Diffs und Export sehen damit
   nie einen entschlüsselten Wert. Ein Geheimfeld in neuen Daten muss fehlen oder **derselbe
   Platzhalter wie in der Datei** sein (D7, „`${…}` nur aus der Datei“); ein eigener `${VAR}` ist
   `PlatzhalterError`. Klartext wird abgewiesen, auch beim ersten Übernehmen aus einer Datei, die
   Klartext enthält. Der Fehler verweist auf `${VAR}` in der Datei oder `einstellungen geheimnis
   setzen`. *Grund:* Leitlinie 7.
   Ein Modell mit eingespritztem Klartext gelangte über `model_dump` früher oder später in eine
   Seite oder ein Log.
9. **D9 — Normalform, Hash-Kette, `datei_hash`.** `daten` wird als kanonisches JSON gespeichert.
   Vorher wandelt `einstellungen.normalform(wert)` alles in JSON-Typen: Datum als ISO-Text,
   `Decimal` als Text, Schlüssel als Text, Tupel als Listen. `journal.kanonisch` hat kein
   `default=` und bekommt nur so normierte Daten. Diese Form gilt auch für Hash, Vergleich und
   Journal-Diff. **Hash:** `hash = sha256(kanonisch(zeile))` über alle Spalten **außer `id` und
   `hash`**. `erstellt_am` geht als `Einstellungsversion.model_dump(mode="json")["erstellt_am"]`
   ein (naiv, Ortszeit wie das Journal, ein Wert je Schreibvorgang, wie `journal.schreibe`), damit
   SQLite und PostgreSQL denselben Text liefern. `daten` und `fehlend` gehen als ihr gespeicherter
   Text ein. Die Kette läuft je Abschnitt (GENESIS bei Version 1). Anträge tragen `inhalt_hash`
   (sha256 über die kanonischen `aenderungen`), der bei `antraege` angezeigt und bei der
   Bestätigung neu gerechnet wird (Abweichung → `AntragError`, Prüfbefund N14). **Zusätzlich** gibt es
   `datei_hash`: den Hash des normalisierten Datei-Abschnitts beim Schreiben (`null` ohne Datei).
   Er ist **nicht** der Cache-Schlüssel des Lesers (der ist der Hash der ganzen Datei, Schritt 2).
   Ein geänderter Kommentar oder ein anderer Abschnitt ändert ihn nicht (G-N2). Damit unterscheidet `pruefen` „weicht ab, aber die Datei ist unverändert Startwert“ (Hinweis)
   von „Datei **nach** der letzten Version geändert“ (Warnung, R1: „Ich habe die YAML geändert,
   nichts passiert“). Nur Letzteres meldet `serve` beim Start ausdrücklich. Dazu kommt
   `antrag_id` (nullable) als Bezug. Beides ergänzt die Spalten aus A39.
10. **D10 — PostgreSQL-Trigger neu, allgemein, nur für `einstellungen`.** `db/schutz.py` erzeugt
    für SQLite `BEFORE UPDATE`/`DELETE … RAISE(ABORT)`. Für PostgreSQL erzeugt es die Funktion
    `accounti_nur_anfuegen()` (plpgsql, `RAISE EXCEPTION '% ist unveränderbar'`) mit Triggern
    `BEFORE UPDATE OR DELETE … FOR EACH ROW` und `BEFORE TRUNCATE … FOR EACH STATEMENT`. Die
    Trigger entstehen über `after_create` (der Weg über `init_db`) und in der Migration.
    *Grund:* AK25 verlangt PostgreSQL ausdrücklich. Bisher schützt PostgreSQL das Journal nur über
    ORM und Hash-Kette. Journal und Korrekturen nachzurüsten ist ein eigener Schritt (Grenzen).
11. **D11 — Anträge umfassen die ganze Änderung.** Ist ein Abschnitt einer Änderung K3, wird die
    **gesamte** Änderung (alle Abschnitte, je mit Basisversion) ein Antrag, und es wird nichts
    gespeichert. Das folgt „alles oder nichts“ wie A45.
    - Ein Antrag läuft nach 7 Tagen ab.
    - Bestätigt wird er nur, wenn alle Basisversionen noch aktuell sind, sonst ist der Status
      „veraltet“.
    - Erst die Bestätigung schreibt die Versionen (`quelle="antrag"`, `antrag_id`).
    - `einstellungsantraege` ist veränderlich, aber nur aus `offen` heraus und nur in Status und
      Entscheidungsfeldern (ORM-Sperre). Jede Statusänderung steht im Journal.
12. **D12 — Rechte in der CLI wie 10a.**
    - **Schreibende Befehle:** `setzen`, `uebernehmen`, `geheimnis setzen|entfernen` brauchen
      mit eingerichteten Benutzern `VERWALTEN` und den Einmalcode. In der CLI gibt es keinen
      Verwaltungsmodus, also immer einen Code (E6: „K2 verlangt den Code immer“).
    - **`antraege bestaetigen`** braucht das Recht der Kontrolle (`ZAHLUNG_FREIGEBEN` bzw.
      `STEUER_FREIGEBEN`) mit eigenem Code. Die Person muss eine andere sein als die
      antragstellende.
    - **`antraege ablehnen`** (Prüfbefund N7): Die antragstellende Person zieht mit `VERWALTEN`
      und Code zurück; jede andere Person braucht das Recht der Kontrolle des Antrags und ihren
      Code. Das Recht wird vor der Code-Abfrage aus dem Antrag bestimmt.
    - **Lesende Befehle** (`zeigen`, `verlauf`, `pruefen`, `export`, `antraege`) prüfen wie alle
      Lesebefehle der CLI nicht (10a: Wer die CLI aufrufen kann, kann die Datenbank lesen).
    - **Ohne Benutzer** läuft alles wie bisher. Person ist dann `aktuelle_person()`, bei K3 der
      Anmeldename über `betriebssystem_benutzer()` (wie `zahlung.vier_augen`, D13).
13. **D13 — Person bei K3 ohne Benutzer ist der Anmeldename.** Antragsteller und Bestätiger werden
    über die UID bestimmt, `ACCOUNTI_BENUTZER` und `--von` zählen nicht. *Grund:* Die Kontrolle,
    die K3 schützt (`zahlung.vier_augen`), zählt ohne Benutzer genauso.
14. **D14 — Periodenwerte als „ab Zeitraum → Wert“.**
    - **Format:** `{2026: monat, 2027: quartal}`, für OSS mit Quartalsschlüsseln `"2027-Q1"`.
    - **Auswertung:** Es gilt der Eintrag mit dem größten Schlüssel ≤ Zeitraum. Der früheste
      Eintrag gilt auch für alle früheren Zeiträume. Ein Einzelwert gilt immer (A124).
    - **Umwandeln:** Ein Einzelwert `alt` mit Änderung „ab Z: neu“ wird zu `{Z−1: alt, Z: neu}`.
      So bleiben alle früheren Zeiträume beim alten Wert.
    - **CLI:** `einstellungen setzen elster.voranmeldungszeitraum quartal --ab 2027`. `--ab`
      ergänzt A49, weil eine Zuordnung sonst nur über `--datei` ginge.
    - **Lesen:** Lader-Modelle bekommen `…_fuer(zeitraum)`. Jeder Verbraucher fragt mit seinem
      Zeitraum, es gibt keinen Zugriff auf den Rohwert mehr.
    - **Prüfbar über mypy** (Prüfbefund M6): Das Rohfeld heißt im Modell anders als in der Datei,
      z. B. `voranmeldungszeitraum_roh: Periodisch[...] = Field(alias="voranmeldungszeitraum")`
      mit `populate_by_name=True`. Jeder alte Zugriff `einst.voranmeldungszeitraum` scheitert dann
      an `mypy` (pydantic definiert `__getattr__` nur außerhalb von `TYPE_CHECKING`), auch ein
      Vergleich wie `!= "bilanz"`, den der Union-Typ allein nicht fände. Funktionen, die heute
      einen Rohwert liefern, bekommen einen Pflichtparameter: `lade_oss(pfad, zeitraum) -> bool`
      (heute `bool(dict)`, also `True` für jede Zuordnung), `gewinnermittlung_angegeben(pfad, wj)`.
      Ausgaben, die geschrieben werden (Golden, Export, Verlauf), nutzen `by_alias=True`. Ein
      AST-Test erlaubt Zugriffe auf `*_roh` nur in `einstellungen/perioden.py` und im Modul des
      Modells.
15. **D15 — Sperren gelten für wirksame Werte.** Die Sperrprüfung vergleicht die Ergebnisse der
    echten Lader vor und nach der Änderung (Überlagerung) je Zeitraum, nicht die Pfade. Damit
    fällt auch ein Kontenrahmenwechsel über `mandant.kontenrahmen` (Fallback aus Paket A) unter
    die Sperre „nach der ersten Buchung“.
16. **D16 — Validierung über die echten Lader.** `pruefung.validiere(abschnitte)` führt unter
    `ueberlagert({…})` jeden Lader aus, der den Abschnitt liest, **auch mittelbar**
    (`inventar.LADER`: `lade_elster` liest seit Paket E auch `integrationen` und `buchhaltung`,
    `lade_zahlung` auch `mandant`, `lade_abschluss` auch `buchhaltung`, `integrationen`, `datev`).
    Es gelten also dieselben Modelle, Querbezüge und Fehlertexte wie beim Lesen (A44).
    **Zurechnung** (Prüfbefund M3):
    - Die Lader laufen zweimal, ohne und mit Änderung, beide unter `leser.pruefmodus()`. Im
      Prüfmodus wirft ein fehlender `${VAR}` keinen Fehler, der Platzhalter bleibt als Text
      stehen (gilt für `_ersetze_variablen` und `loese_auf`, die dafür `leser.im_pruefmodus()`
      fragen). So scheitert `einstellungen setzen versand.betreff …` nicht in einer CLI ohne
      SMTP-Variable (`docker compose run`).
    - Fehler an einem Platzhalterblatt der Datei zählen nie („nicht prüfbar ohne
      Umgebungsvariable“, Hinweis).
    - In einem **geänderten** Abschnitt zählen alle übrigen Fehler; die Version muss gültig sein.
    - In einem **nicht geänderten** Abschnitt zählen nur Fehler, die erst mit der Änderung
      entstehen (Vergleich nach Lader und Fehlertext). Schon vorhandene Fehler werden Hinweise
      („zahlung: … — besteht schon, betrifft diese Änderung nicht“). So blockiert eine kaputte
      `zahlung` nicht das Speichern von `mandant`, eine Änderung an `mandant`, die den
      Auftraggeber in `zahlung` ungültig macht, aber schon.

    **Unbekannte Felder** (Prüfbefund M4): `Firma`, `Buchhaltung`, `ElsterEinstellungen` und
    andere Modelle haben kein `extra="forbid"` und nähmen `mandant.rechnung.zahlungziel_tage`
    still hin. `pruefung.unbekannte_felder(abschnitt, daten)` läuft über `inventar.MODELL`
    (Abschnitt → Modell; bei `belegkanaele.connectoren[]` das Modell des Connector-Typs) und
    meldet jeden Schlüssel, den das Modell nicht kennt. Zuordnungen mit freien Schlüsseln
    (`dict[str, …]`, etwa `skonto_erhalten`, `sondervorauszahlung`) sind offen. Beim Schreiben ist
    ein unbekanntes Feld **in der Änderung selbst** (Wert von `setzen`, Inhalt von `--datei`,
    später das Formular) ein Fehler mit Pfad und Vorschlag (`difflib`, „meinten Sie
    rechnung.zahlungsziel_tage?“). Unbekannte Felder der **Basis** (Roh-Abschnitt der Datei, D6)
    und beim Übernehmen aus der Datei werden nicht übernommen und als Hinweis genannt (G-M2).
    Sonst scheiterte `setzen mandant.rechnung.zahlungsziel_tage` an einem Feld, das niemand
    angefasst hat. `pruefen` warnt über unbekannte Felder der Datei. Heute nur nebenbei gelesene
    Felder werden Modellfelder: `mandant.sachkonten_laenge: int = 4` (liest `datev_stammdaten`).
    Nachgeprüft: Sonst liest kein Lader einen Schlüssel von `mandant` am Modell `Firma` vorbei
    (`lade_mandant`, `lade_steuerangaben`, `lade_eigene_firma`, `lade_zahlung`, `_Doku` lesen nur
    Felder von `Firma`). Die eine Ausnahme ist der Umzug:

    **Umzug** (G-M2): `inventar.UMZUG = {"mandant.kontenrahmen": "buchhaltung.kontenrahmen"}`.
    `Firma` kennt `kontenrahmen` nicht. Ältere Dateien führen ihn aber noch unter `mandant`, und
    `lade_buchhaltung` liest ihn dort als Rückfall (`konfiguration.py:198–206` auf `main`). Ließe
    die erste `mandant`-Version das Feld still fallen, wechselte der Kontenrahmen ohne Buchungen
    von SKR04 auf SKR03; mit Buchungen käme `GesperrtError` beim Ändern des Zahlungsziels. Darum:
    Der Umzug greift nur, wenn `mandant.kontenrahmen` gesetzt ist und `buchhaltung.kontenrahmen`
    im wirksamen Abschnitt fehlt. Ein bloßer Standard wird nicht eingefroren (D6).
    - Die erste Version von `buchhaltung` nimmt den Wert in dieselbe Version auf.
    - Die erste Version von `mandant` lässt das Feld fallen und schreibt in derselben Transaktion
      eine eigene Version von `buchhaltung` mit dem Wert (Journal, Hinweis „mandant.kontenrahmen
      nach buchhaltung.kontenrahmen übernommen“).
    - Der wirksame Wert bleibt gleich, also greift weder eine Sperre (D15) noch eine Stufe.
    - Ist `buchhaltung` festgelegt, bricht `speichere` mit `FestgelegtError` ab und nennt
      `buchhaltung.kontenrahmen` in der Datei als Weg.

    **Unvollständig** (Prüfbefund M5): Was als „fehlt noch“ zählt, legt je Abschnitt
    `AbschnittInfo.unvollstaendig_erlaubt` fest, und zwar über Fehlerarten: `missing` und die neue
    Art `pflicht_fehlt`. `Firma._pflichten` wirft dafür `PydanticCustomError("pflicht_fehlt",
    "USt-IdNr. oder Steuernummer fehlt (§ 14 Abs. 4 Nr. 2 UStG)", {"felder": ["ust_id",
    "steuernummer"]})`. Der Text bleibt gleich, auch in `_fehlertext`. Solche Fehler werden zu
    `fehlend` (`["mandant.ust_id oder mandant.steuernummer"]`), die Version zu
    `vollstaendig=false`. Alle anderen Fehler bleiben Fehler. Zunächst gilt das nur für
    `mandant`; P7 ergänzt weitere Abschnitte.

    Danach folgen die **Querprüfungen** (A44):
    - **Konto bekannt** (Prüfbefund M10): Die `arten`-Spannen von SKR03 und SKR04 decken
      0000–9999 lückenlos ab, „Nummer in einer Spanne“ prüft also nichts. P4 prüft darum die
      Form: nur Ziffern; ein Sachkontenfeld verlangt genau die Sachkontenlänge
      (`mandant.sachkonten_laenge`, Standard 4; längere Nummern liest `Kontenrahmen._nummer` über
      die ersten vier Ziffern). 0000 ist unbekannt. Ein Personenkonto (Sachkontenlänge + 1 Stellen,
      also 5 bzw. 7; die Vorlage erlaubt `sachkonten_laenge` 4 oder 6) in einem Sachkontenfeld ist der Fehler
      „Personenkonto statt Sachkonto“. Ob ein Konto im Rahmen wirklich vorkommt, lässt sich erst
      mit den Bezeichnungslisten aus P3 prüfen (A36, mindestens 300 Konten je Rahmen). Das steht
      in den Grenzen, und AK77 ist für „unbekanntes Konto“ in P4 nur in dieser Form belegt.
    - **Kontoart je Feld** (`inventar.KONTOFELDER`): Sachkonto eines Bankkontos ist ein
      Bankkonto des Rahmens (`ist_bankkonto` bzw. eingerichtet über `mit_eingerichteten_konten`).
      Skontokonten und `standard_aufwand` sind Erfolgskonten (`art(...) is ERFOLG`). Ein Konto
      des anderen Rahmens fällt so auf, soweit seine Art dort abweicht: 3736 (SKR03 „Skonto
      erhalten“) ist unter SKR04 ein Bestandskonto. 8736 ist in beiden Rahmen ein Erfolgskonto und
      bleibt bis P3 unerkannt (Grenzen).
    - eine ausdrückliche `zahlung.auftraggeber.iban` gehört zu einem eigenen Bankkonto

    Querprüfungen sind beim Schreiben Fehler, aber **nur für gesetzte Werte** (neue Daten, Version
    oder Datei). Ein unpassender Standard wird Warnung: `Buchhaltung.skonto_erhalten` ist auch
    unter SKR04 mit SKR03-Konten vorbelegt (3736 dort ein Bestandskonto). Ein Fehler würde sonst
    jedes Speichern von `buchhaltung` unter SKR04 blockieren. In `pruefen` gelten Querprüfungen für
    Datei-Werte als Warnung („würde beim Speichern abgewiesen“), damit ein Update bestehende
    Installationen nicht rot macht.
17. **D17 — `WERT` als YAML-Skalar mit Vorrang für Text.** Erwartet das Modell an dieser Stelle
    `str`, gilt der Text wörtlich (`1200`, `0880`, `DE…` bleiben Text, `no` bleibt „no“). Sonst gilt
    der YAML-Wert. Listen und Zuordnungen gehen nur über `--datei` (A49).
18. **D18 — Der Abschnitt `llm` wirkt ab P4.** Neu sind das Modell `LlmEinstellungen` und
    `lade_llm`. Verdrahtet werden `auto_buchen_schwelle` (über `KlassifikationsEngine` in
    `zu_buchungssatz(auto_schwelle=…)`) und Anbieter/Modell (`LLMEngine(model=…)`), `api_key` über
    D8. *Grund:* Heute gilt immer 0,95, und der Abschnitt ist toter Text. K3 für „Schwelle senken“
    (E6, AK100) schützte dann nichts. Die Beispielkonfiguration hat 0,95, der Golden-Test bleibt
    grün. Abweichende Werte in bestehenden Dateien **wirken ab jetzt**. Das steht im CHANGELOG und
    in `pruefen` als einmaliger Hinweis („llm.auto_buchen_schwelle 0,80 wirkt seit Baustein 10c“),
    solange keine Datenbank-Version besteht. `import` bekommt nur Modell und Lader (A44), die
    Wirkung bleibt wie heute: keine (Grenzen).
19. **D19 — Vier-Augen für Steuermeldungen ohne Migration.** `offene_freigabe(…, vier_augen=True)`
    verlangt zwei unverbrauchte Freigaben mit gleichem `inhalt_hash` von zwei verschiedenen
    Personen. Eine erfolgreiche Echt-Abgabe verbraucht **alle** Freigaben desselben Inhalts bis
    zur genutzten (Zeitpunkt ≤). Die Tabelle braucht so keine zweite `freigabe_id` (A125: „keine
    Migration“). **Die Verbrauchsregel gilt unabhängig vom Schalter** (Prüfbefund N15): Hinge sie
    an `vier_augen`, machte ein späteres Ausschalten die erste Freigabe eines schon abgegebenen
    Paars wieder „offen“, und dieselben Werte ließen sich ohne neue Freigabe noch einmal abgeben.
    Ohne Schalter ändert sich für den üblichen Ablauf nichts (eine Freigabe, eine Abgabe, AK100
    „wie bisher“). Neu ist nur, dass eine ältere, doppelte Freigabe derselben Werte mit verbraucht
    wird. Heute erlaubte sie eine zweite identische Abgabe ohne neue Freigabe. Das steht im
    CHANGELOG unter „Geändert“.
20. **D20 — Golden-Test vor dem Umbau.** Schritt 0 erzeugt aus dem **unveränderten** Code die
    Modelle aller Lader für vier Konfigurationen als JSON:
    - Beispielkonfiguration
    - SKR04 mit abweichendem WJ
    - leer
    - Einzelwerte

    Der Test ist grün, bevor ein Lader angefasst wird (Schutztest). Erlaubte Unterschiede stehen
    im Test: neue Felder mit Standard sowie `wirtschaftsjahr_beginn` nur nach Tag und Monat
    verglichen. Die Lader liefern verschiedene Typen (`lade_oss` bool, `lade_mandant` dict,
    `lade_eigene_firma` `Partnerdaten`, `lade_wirtschaftsjahr_beginn` Datum, `lade_firma` auf
    „leer“ einen Fehler). Darum serialisiert ein eigener Serialisierer `golden_lader.serialisiere`
    (Prüfbefund N13): Modell → `model_dump(mode="json", by_alias=True)`, Dataclass →
    `asdict`, Datum → ISO-Text, Fehler → `{"fehler": <Klasse>, "text": <Meldung ohne Pfad>}`,
    sonst der Wert. Der Golden-Test „leer“ bleibt nach P4 als Wächter über alle Standards (D6).
21. **D21 — Name der Gesellschaft ohne Registry beim Start aus ihrer Datenbank.** Mit Registry
    kommen die Namen aus den Einträgen der Registry (`gesellschaften[].name`, Betriebsabschnitt);
    `lade_eigene_firma` liest dort nur `ocr_erkenner(g)`, und das geschieht in einer gebundenen
    Anfrage. Ohne Registry liest `einzelne_gesellschaft` den Namen unter
    `mit_quelle(DatenbankQuelle(db), config)`. Damit folgt ein im Browser (P5) geänderter
    `mandant.name` nach dem Neustart. Ohne Datei oder Datenbank bleibt es beim Kürzel. Mit
    Registry bleibt der Name der Registry das Etikett des Betreibers. `pruefen` gibt einen Hinweis,
    wenn er vom `mandant.name` abweicht.
22. **D22 — Tresor-Bezug `<kuerzel>:<name>`** wie A48. Ohne Registry ist das Kürzel `standard`.
    Wer später auf eine Registry mit anderem Kürzel umzieht, setzt die Geheimnisse neu (Grenzen,
    Meldung von `pruefen`).
23. **D23 — „Datei weicht ab“ wird normalisiert verglichen.** Verglichen werden die
    Modell-Ausgaben, wo es ein Modell gibt (sonst die Normalform D9), ohne Betriebs-, Platzhalter-
    und Geheimfelder. Ein Abschnitt, der in der Datei fehlt, ist keine Abweichung. `serve` meldet
    beim Start nur Anzahl und Abschnittsnamen, nie Werte (A116). Weil der Vergleich die Modelle
    braucht, liegen `herkunft` und `abweichend` in `einstellungen/pruefung.py`, nicht im Leser
    (D1: der Leser importiert keine Fachmodule, Prüfbefund N4). Der Leser liefert nur
    `herkunft_roh` (Art, Version, Zeit, Person, `datei_hash`).
24. **D24 — Downgrade bricht mit Daten ab.** Die Migration lässt sich nur zurücknehmen, solange
    `einstellungen`, `einstellungsantraege` und `geheimnisse` leer sind. Sonst nennt die Meldung
    `accounti sicherung erstellen` als Weg, die Versionen sind Organisationsunterlagen (§ 147 AO).
    P4c ergänzt `einstellungen export`. Den Befehl gibt es erst ab P4c, die Migration kommt mit
    P4a (G-N5).
25. **D25 — Eine fehlende Datei ist ein leerer Startwert** (Prüfbefund H3). Heute endet fast jeder
    Lader an `pfad.is_file()`, bevor er etwas liest (`lade_firma` „Vorlage kopieren“,
    `lade_buchhaltung` Standards, ebenso `lade_elster`, `lade_versand`,
    `lade_aufgaben_einstellungen`, `lade_belegkanaele`, `abschluss._abschnitt`,
    `integrationen._abschnitt` …). Damit gälten bei fehlender Datei die Datenbank-Versionen nicht.
    Das widerspräche E5 (gilt auch bei anderem `--config`) und A71.3 („weder Datei- noch
    Datenbankwerte“) und verhinderte die Einrichtung im Container ohne Datei (P7). Darum:
    - `lies_abschnitt` liest eine fehlende Datei als `{}` (Festlegung, Platzhalter und
      Betriebsfelder gibt es dann nicht).
    - Die Wächter fallen aus allen Ladern weg, die Datenbank-Abschnitte lesen.
    - Meldungen wie „`<pfad>` fehlt — Vorlage … kopieren“ kommen nur noch, wenn
      `leser.quelle_vorhanden(pfad, name)` falsch ist, also weder Datei noch Version (bzw.
      Überlagerung) besteht. Der Wortlaut bleibt.
    - Betriebslader (`lade_auth`, `lade_server`, `lade_gesellschaften`) behalten ihr Verhalten.
26. **D26 — K2 für Felder, die bestimmen, wohin ein Zugang geht** (Prüfbefund H4). **Entschieden
    am 26.10.2026 wie vorgeschlagen** (Orchestrator; Offener Punkt 6). Das ist eine **Ergänzung von
    Anhang A der Spec**: Text im Doku-Baustein „Spec 10c, Anhang A“, eingetragen mit P4b. Anhang A
    macht nur Passwörter zu K2. Wer aber Host oder Verschlüsselung ändern darf, lenkt einen
    gespeicherten Zugang (Tresor, Geheimnis, `${VAR}`) an einen eigenen Server, ohne das Geheimnis
    je zu sehen:
    - IMAP: Passwort aus Tresor oder `${VAR}`, Host aus `belegkanaele.email[].host`
    - SMTP: `versand.smtp.passwort` bzw. Geheimnis, Host aus `versand.smtp.host`
    - Connector: `{zugang}` in den Kopfzeilen geht an `basis_url`
    - `llm.provider`/`llm.model` wirken ab D18 und bestimmen, wohin `llm.api_key` und die
      Bankumsätze gehen

    **K2 sind** (Feldnamen am Code geprüft: `erechnung/versand.py:62–66`,
    `belege/kanaele/einstellungen.py:63–66`, `belege/kanaele/json_http.py:108–113`):
    `versand.smtp.host|port|verschluesselung`, `belegkanaele.email[].host|port|verschluesselung`,
    `belegkanaele.connectoren[].basis_url|erlaubte_hosts|kopfzeilen`, `llm.provider|model`.
    `benutzer` bleibt K1, weil er nicht ändert, wohin das Geheimnis geht. `verschluesselung` kommt
    über den Vorschlag der Prüfung hinaus hinzu: `keine` schickte das Passwort im Klartext. In der
    CLI wirkt K2 nicht anders als K1 (D12: immer Code); die Stufe zählt ab P5 im Browser
    (Einmalcode bzw. Verwaltungsmodus).
    **Nicht übernommen** ist die Alternative der Gegenprüfung (G-N4), die Zielfelder eines Elements
    mit Zugang aus `${VAR}` wie Betriebsfelder zu behandeln. Sie widerspräche der Entscheidung (K2
    für alle Ziel-Host-Felder). Der Rest wird benannt: Im Verwaltungsmodus kann eine Person mit
    `VERWALTEN` und Einmalcode (bzw. im Verwaltungsmodus ab P5) einen Zugang des Betreibers aus
    `${VAR}` an einen eigenen Host lenken. Wer das
    ausschließen will, legt die Abschnitte in der Datei fest (`einstellungen.festgelegt: [versand,
    belegkanaele, llm]`). Das steht in den Grenzen und in `docs/betrieb.md`.
27. **D27 — Journalprüfung mit Teilständen** (Prüfbefund H2). `einstellung_geaendert` trägt nach
    A40 nur die geänderten Felder, als flache Punkt-Pfade (`{"rechnung.zahlungsziel_tage": 14}`),
    mit `objekt_id` = Abschnitt. `pruefung/journal._pruefe_verlauf` vergleicht heute den
    Vorher-Stand mit dem letzten Nachher-Stand über die Vereinigung der Schlüssel. Ab der zweiten
    Änderung an einem anderen Feld meldete `accounti journal pruefen` dann „an accounti vorbei
    geändert“. Für die Objekttypen in `journal.TEILSTAENDE = {"einstellung",
    "einstellungsantrag", "einstellungsstandard"}` (der letzte für D6) wird der Stand je Schlüssel fortgeschrieben (Nachher in den bisherigen
    Stand gemischt), und verglichen werden nur die Schlüssel des Vorher-Stands, die der bisherige
    Stand kennt. Eine echte Änderung an accounti vorbei fällt weiter auf, wenn ein späterer
    Eintrag dasselbe Feld mit anderem Vorher trägt. Die Hash-Kette je Abschnitt (D9) deckt den
    Rest.
28. **D28 — Drei PRs statt eines** (Prüfbefund M12). 18 Schritte über fast alle Module neben dem
    parallel laufenden P1 sind als ein PR schwer zu prüfen und zu mergen. Jeder Zwischenstand auf
    `main` muss sicher sein, also kommt das Schreiben erst mit allem, was es absichert:
    - **P4a Lesen** (Schritte 0–6): Golden-Test, alle drei Tabellen samt Migration und
      PostgreSQL-CI, Leser, Bindung in CLI und Web, Umbau aller Lader, neue Felder und Modelle
      (`llm` wirkt), Periodenwerte lesen. Ohne Schreibweg ist das Verhalten gleich (Golden). R2:
      Der Leser ist früh auf `main`, P5 und P7 bauen darauf. P1 liest keine YAML (P1-Plan B4,
      G-N9).
    - **P4b Schreiben** (Schritte 7–10, 12, 13, 16): Dienst, Validierung, Journal samt Prüfung
      (D27), Sperren, Stufen und Anträge, Geheimnisse, CLI, `pruefen`, Sicherung und
      Aufbewahrung. Sperren und Periodenwerte müssen vor dem ersten Schreibweg da sein, sonst
      wirkte `setzen elster.voranmeldungszeitraum` rückwirkend, und der Kontenrahmen ließe sich
      nach Buchungen wechseln. Darum weicht die Aufteilung vom Vorschlag der Prüfung ab, der
      Periodenwerte und Sperren erst in P4c sah.
    - **P4c Steuer-Vier-Augen, Export, Stichtag** (Schritte 11, 14, 15): `elster.vier_augen`
      (Feld, Stufen, Wirkung) kommt erst hier. So lässt sich der Schalter nicht vorher setzen, ohne
      dass er wirkt.

    Die Doku-Bausteine verteilen sich entsprechend (Abschnitt „Doku-Bausteine“, je Block
    vermerkt). Jeder PR durchläuft die gegnerische Prüfung.

---

## Schnittstelle (Fachfunktionen für CLI, P5 und P7)

```python
# einstellungen/leser.py — lesen; kein Import aus Fachmodulen
def lies_abschnitt(pfad: str | Path, name: str) -> dict[str, Any]   # wirksam nach E2 (ohne DB-Geheimnisse, ohne ${…} aus der DB);
                                                                     # fehlende Datei = {} (D25)
def quelle_vorhanden(pfad: str | Path, name: str) -> bool           # Datei-Abschnitt oder Version/Überlagerung vorhanden (D25)
def lies_datei(pfad: str | Path) -> dict[str, Any]                  # ganze Datei, Inhalts-Hash-Cache, Kopie (Registry, Export)
def geheimnis(name: str) -> str | None                              # nur Verbrauchsstellen (D8); Tresor-Bezug <kuerzel>:<name>
def herkunft_roh(pfad: str | Path, name: str) -> HerkunftRoh        # art: datenbank|datei|standard|festgelegt|betrieb,
                                                                     # version, erstellt_am, person, datei_hash (D23)
@contextmanager pruefmodus() -> Iterator[None] ; def im_pruefmodus() -> bool   # fehlender ${VAR} wirft nicht (D16)
def parse_text(text: str, *, grenze: int = 64 * 1024) -> Any        # safe_load, ohne Anker/Aliase, Zeile/Spalte im Fehler
@contextmanager neuer_stand(*, web: bool = False) -> Iterator[Stand]
@contextmanager mit_quelle(quelle: Quelle | None, konfiguration: Path | None = None,
                           stichtag: datetime | None = None) -> Iterator[Stand]
@contextmanager ueberlagert(abschnitte: Mapping[str, dict[str, Any]]) -> Iterator[None]
class DatenbankQuelle:  # url oder engine; legt keine SQLite-Datei an; ohne Tabelle: leer
    def schnappschuss(self, stichtag: datetime | None = None) -> Schnappschuss
class Stand:
    def binde(self, quelle: Quelle, konfiguration: Path | None = None, *, streng: bool = False,
              kuerzel: str | None = None) -> None   # nimmt sofort den Schnappschuss (D3, D4)

# einstellungen/dienst.py — in der Sitzung des Aufrufers (flush, nie commit); Aufrufer committet
@dataclass(frozen=True)
class Bestaetigung:
    k2: bool
    verfahren: Literal["einmalcode", "verwaltungsmodus", "ohne_benutzer"]
@dataclass(frozen=True)
class Aenderung:
    abschnitt: str
    daten: dict[str, Any]
    erwartete_version: int   # 0 = noch keine
def speichere(s, pfad, aenderungen, *, person, grund, quelle, bestaetigung,
              berechtigte: Callable[[Recht], int | None], jetzt=None) -> Ergebnis
    # Ergebnis(versionen, antrag, meldepflichtig: list[str], hinweise: list[str])
def setze_feld(s, pfad, ziel: str, wert: Any, **kw) -> Ergebnis              # "mandant.rechnung.zahlungsziel_tage"
def setze_periodenwert(s, pfad, ziel: str, ab: str, wert: Any, **kw) -> Ergebnis
def setze_abschnitt(s, pfad, abschnitt: str, daten: dict, **kw) -> Ergebnis  # --datei / Experten-Ansicht (P5)
def uebernehme_aus_datei(s, pfad, abschnitte: list[str] | None, **kw) -> Ergebnis
def bestaetige_antrag(s, pfad, antrag_id, *, person, jetzt=None) -> Ergebnis
def lehne_antrag_ab(s, antrag_id, *, person, grund, jetzt=None) -> Antrag
def halte_standards_fest(s, *, jetzt=None) -> list[str]   # D6: Journal einstellung_standards, geänderte Abschnitte
def setze_geheimnis(s, kuerzel, name, wert, *, person, schluessel, jetzt=None) -> GeheimnisInfo
def entferne_geheimnis(s, name, *, person, grund, jetzt=None) -> None
def wirksam(pfad, abschnitt) -> dict[str, Any]          # für Anzeigen: Geheimfelder als Markierung
# Fehler (alle KonfigurationError, mit .feld und .meldung ohne CLI-Optionen):
# KonfliktError(abschnitt, erwartet, aktuell, von, am) · FestgelegtError · BetriebsfeldError
# PlatzhalterError · GeheimnisImKlartextError · GesperrtError(feld, zeitraum, grund)
# BestaetigungNoetig(stufe) · ValidierungError(fehler: list[Feldfehler]) · AntragError

# einstellungen/pruefung.py · stufen.py · perioden.py · verlauf.py · export.py
def validiere(s, pfad, abschnitte: Mapping[str, dict]) -> Pruefergebnis   # fehler, hinweise, fehlend, vollstaendig je Abschnitt (D16)
def unbekannte_felder(abschnitt: str, daten: dict) -> list[Feldfehler]     # gegen inventar.MODELL (D16, M4)
def herkunft(pfad, name) -> Herkunft                                       # herkunft_roh + abweichend, datei_geaendert (D23)
def abweichungen(pfad) -> list[str]                                         # Abschnittsnamen für die Startmeldung von serve (Schritt 13)
def standards() -> dict[str, Any]                                           # Lader auf leerem Stand, SKR03 und SKR04, Normalform (D6)
def pruefe_alles(s, pfad, *, berechtigte=None) -> list[Befund]             # stufe fehler|warnung|hinweis, abschnitt, text
def stufe(abschnitt, alt_wirksam, neu_wirksam, kontrollen) -> Bewertung    # K1|K2|K3, felder, kontrolle, recht
def wert_fuer(feldwert, zeitraum) -> Any ; def setze_ab(feldwert, ab, wert) -> Any
def pruefe_sperren(s, pfad, alt, neu) -> list[GesperrtError]
def verlauf(s, abschnitt=None, *, bis: datetime | None = None) -> list[Versionsdiff]   # Feld, alt → neu, ohne Geheimnisse
def exportiere(s, pfad) -> str

# elster/freigabe.py (9, ergänzt)
def gib_frei(session, v, von, jetzt=None, *, vier_augen: bool = False) -> Freigabe
def offene_freigabe(session, art, zeitraum, daten, *, vier_augen: bool = False) -> Freigabe
def stand_der_freigaben(session, art, zeitraum, daten) -> FreigabeStand   # personen, fehlt_zweite (für P2)

# pruefung/verfahrensdoku.py (7, ergänzt): erzeuge(s, config, *, db_url, archiv, stand, …) — `stand` ist der Stichtag (N2)
# pruefung/journal.py (7, ergänzt): TEILSTAENDE = {"einstellung", "einstellungsantrag", "einstellungsstandard"} (D27, D6)
```

---

## Aufgaben

> **PR P4a „Lesen“: Schritte 0–6** (D28). Danach Schritt 17 für P4a (Doku, Prüfläufe,
> gegnerische Prüfung), Merge, dann P4b.

### Schritt 0 — Abzweigen, Grundlage prüfen, Golden-Test · P4a

- [x] **Abzweigen und lesen**: `main` mit 10b-1 und allen `fix/gesamttest-*`; `alembic heads`
  zeigt genau einen Kopf (notieren: `<kopf>`), `db.SCHEMA_STAND == <kopf>`. Die Signaturen aus
  „Was P4 vorfindet“ gegenlesen (vor allem `lade_buchhaltung`, `lade_abschluss`,
  `lade_wirtschaftsjahr_beginn`, `Dienste`, `angemeldet`, `api_zugang`, `richte_kontext_ein`).
- [x] **Golden-Daten erzeugen** (D20): `tests/werkzeuge/golden_lader.py` ruft für jede
  Konfiguration in `tests/daten/lader_golden/` (`beispiel` = `config/accounti.example.yaml`,
  `skr04_abweichend.yaml`, `leer.yaml`, `einzelwerte.yaml`) jeden Lader aus
  `GOLDEN_LADER` auf und schreibt `serialisiere(ergebnis)` (D20: Modelle, bool, dict,
  `Partnerdaten`, Datum, Fehler) nach `tests/daten/lader_golden/<konfig>.json`. Das geschieht
  **einmal auf dem unveränderten Code**. Die JSON-Dateien werden eingecheckt. *Test*
  `tests/test_lader_golden.py::test_lader_wie_vor_10c[<konfig>-<lader>]`, mit `ERLAUBT`: neue
  Felder mit Standard, `wirtschaftsjahr_beginn` nur nach (Monat, Tag), umbenannte Rohfelder über
  ihren Alias (D14). Dazu `::test_serialisierer_kennt_jeden_rueckgabetyp`. Grün auf dem alten
  Code, Commit „Golden-Test der Lader (Schutz für P4)“. Ändert ein Commit auf `main` nach dem
  Abzweigen Lader oder Konfiguration, werden die Golden-Daten beim Rebase aus `main` ohne P4 neu
  erzeugt (eigener Worktree), und der Unterschied steht im PR (G-N8).
  *Umgesetzt:* Kopf `1dd2f6b7c6c8` = `SCHEMA_STAND` (siehe „Umsetzung P4a“). `GOLDEN_LADER`
  umfasst 28 Lader (alle öffentlichen Lader der Gesellschaftskonfiguration samt
  `gewinnermittlung_angegeben`, `sachkontenlaenge`, `lade_datev_mandant` zum 31.03.2026);
  `lade_korrekturumgebung` fehlt mit Grund (nur zusammengesetzt). Fest belegte Umgebung
  (`feste_umgebung`), Pfade als `<pfad>`/`<ordner>`. `ERLAUBT` zusätzlich: eine
  Fehlermeldung darf ergänzt werden (gleiche Klasse, alter Text enthalten; für den Verweis
  „Einstellungen › Firma & Steuern“ aus Schritt 4). Neue Felder trägt `NEUE_FELDER` je
  Lader mit Standard ein (Schritt 5).

### Schritt 1 — Tabellen, Schutz, Migration · P4a

- [x] **Tabellen und Modelle** (`db/tabellen_einstellungen.py`, `models/einstellungen.py`,
  `db/repo_einstellungen.py`):
  - **`einstellungen`:** `id` Integer PK, `abschnitt` String(40) indiziert, `version` Integer,
    `UniqueConstraint(abschnitt, version)`, `daten` Text (kanonisches JSON), `schema_version`
    Integer, `vollstaendig` Boolean, `fehlend` Text (JSON-Liste), `person` String(100), `grund`
    String(500), `quelle` String(20) (`browser|cli|assistent|datei_uebernahme|antrag`),
    `antrag_id` Integer nullable, `datei_hash` String(64) nullable, `erstellt_am` DateTime,
    `hash` String(64) unique, `vorgaenger_hash` String(64). Hash nach D9 (ohne `id`, `hash`).
  - **`einstellungsantraege`:** `id`, `aenderungen` (JSON: Abschnitt, Basisversion, Daten),
    `inhalt_hash` String(64) (D9), `grund`, `antragsteller`, `erstellt_am`, `gueltig_bis`, `kontrolle`
    (`zahlung.vier_augen|elster.vier_augen`), `recht`, `felder` (JSON), `status`
    (`offen|bestaetigt|abgelehnt|abgelaufen|veraltet`), `entschieden_von`, `entschieden_am`,
    `entscheidungsgrund`, `versionen` (JSON).
  - **`geheimnisse`:** `id`, `name` String(100) unique, `chiffrat` Text, `gesetzt_am`,
    `gesetzt_von`.
  - **Repository:** `neueste_versionen(s) -> dict[str, int]`, `lade_version(s, abschnitt,
    version)`, `lade_versionen(s, abschnitt=None, bis=None)`, `fuege_version_an(s, …)`
    (berechnet Hash und Vorgänger, unter `journal.schreibsperre`), `lade_antraege`,
    `lade_geheimnisse` (nur Name, gesetzt_am/von), `lade_chiffrate(s)`.

  *Tests zuerst* in `tests/test_einstellungen_tabellen.py`:
  - `::test_version_nur_anfuegen_orm` (`UnveraenderbarError` bei Ändern und Löschen)
  - `::test_version_nur_anfuegen_rohes_sql_sqlite` (Trigger)
  - `::test_massenaenderung_gesperrt` (`session.execute(update(...))`, `bulk_*`; `db.GESCHUETZT`)
  - `::test_versionen_je_abschnitt_fortlaufend`
  - `::test_doppelte_version_scheitert` (Unique)
  - `::test_hash_kette_je_abschnitt`
  - `::test_hash_gleich_unter_sqlite_und_postgresql` (`@mit_postgresql`: dieselbe Zeile ergibt
    denselben Hash; `erstellt_am` mit Mikrosekunden, `Decimal` und Datum in `daten`)
  - `::test_hash_ohne_id` (gleiche Zeile mit anderer `id` → gleicher Hash)
  - `::test_antrag_status_nur_aus_offen`
  - `::test_antrag_nicht_loeschbar`
  - `::test_geheimnis_name_eindeutig`

  Rot; Umsetzung; grün.
- [x] **Schutz für SQLite und PostgreSQL** (`db/schutz.py`: `nur_anfuegen_sql(tabelle, text,
  dialekt) -> list[str]`, PG-Funktion `accounti_nur_anfuegen()`; `after_create` an
  `einstellungen`). *Tests* `tests/test_einstellungen_tabellen.py::test_trigger_postgresql`
  (`@mit_postgresql`: `UPDATE`, `DELETE`, `TRUNCATE` scheitern mit „ist unveränderbar“, `INSERT`
  geht) und `::test_trigger_nach_init_db_postgresql` (Weg über `create_all`). Lokal mit
  `ACCOUNTI_TEST_PG` (postgres:16 im Wegwerf-Container).
- [x] **PostgreSQL in der CI** (Prüfbefund M11; AK25 sonst nur von Hand belegt):
  `.github/workflows/ci.yaml` bekommt einen Job `postgresql` (Python 3.12) mit
  `services: postgres` (Abbild `postgres:16.<n>`, genau gepinnt; beim Abzweigen die neueste
  Unterversion nehmen, die mindestens zwei Wochen alt ist), `POSTGRES_PASSWORD` nur für die CI,
  Healthcheck `pg_isready`, und `ACCOUNTI_TEST_PG=postgresql+psycopg://postgres:…@127.0.0.1:5432/postgres`.
  Schritte: Checkout, Python, `pip install -e ".[dev,fints]"` wie im Job `test`, dann `pytest`
  ganz, damit auch die bestehenden `@mit_postgresql`-Tests aus 7, 10a und den Gesamttest-Paketen
  laufen. **Ausdrücklich ohne** Tesseract, Prüfwerkzeuge und `ACCOUNTI_PRUEFWERKZEUGE_PFLICHT`
  (G-N6). Diese Tests überspringen dort (`skipif` auf `tesseract` bzw. auf den Prüfer ohne
  Pflicht-Variable, `tests/test_belege_ocr.py:49`, `tests/test_erechnung_kosit_pruefer.py:20`) und
  laufen im Job `test`, ebenso ruff, mypy und Coverage. Ein Kommentar im Job sagt das. `psycopg`
  ist schon Abhängigkeit, eine Python-Abhängigkeit kommt nicht hinzu. Scheitert ein bestehender PostgreSQL-Test, wird er in einem eigenen Commit
  behoben oder mit Befund im PR genannt, nicht still übersprungen. Ohne den Dienst (lokal)
  überspringen die Tests wie bisher.
- [x] **Migration** `alembic/versions/<rev>_add_einstellungen.py` mit `down_revision = "<kopf>"`
  nach dem Muster `ddc9a184ddb4`:
  - vorhandene Tabellen übernehmen (`init_db` kann sie schon angelegt haben)
  - Trigger je Dialekt mit `IF NOT EXISTS` bzw. `CREATE OR REPLACE`
  - Downgrade bricht mit Zeilen ab (D24, Meldung nach G-N5)
  - `db.SCHEMA_STAND = "<rev>"`

  *Tests* `tests/test_migration_einstellungen.py`. Alle hängen an der eigenen Konstante
  `REV = "<rev>"` und an `VOR = ScriptDirectory.from_config(…).get_revision(REV).down_revision`,
  nie an `downgrade -1`, `get_current_head()` oder „`<rev>` (head)“ (G-M1). So bleiben sie grün,
  wenn P1 oder ein späterer Branch sich daran kettet:
  - `::test_ein_kopf` (genau ein Kopf, Kopf == `db.SCHEMA_STAND`, `REV` steht in der Kette
    `… → VOR → REV`)
  - `::test_upgrade_auf_bestand` (Datenbank auf `VOR` mit Buchungen → `db upgrade` → Tabellen und
    Trigger da)
  - `::test_migration_uebernimmt_was_init_db_anlegte`
  - `::test_downgrade_leer_und_wieder_hinauf` (Downgrade auf `VOR`)
  - `::test_downgrade_mit_versionen_bricht_ab` (Downgrade auf `VOR`; Meldung nennt
    `accounti sicherung erstellen`)
  - `::test_db_upgrade_leitet_stand_ab` (Paket A: Datenbank ohne Vermerk mit den neuen Tabellen →
    abgeleiteter Stand stimmt)

  Dazu `tests/test_db_upgrade.py` (Paket A) mit `SCHEMA_STAND` grün. Alembic als Unterprozess mit
  `ACCOUNTI_DB` wie `tests/test_migration_belegvollstaendigkeit.py`.
- [x] **Kopfabhängige Migrationstests umstellen** (G-M1, **Pflicht vor dem Migrations-Commit**).
  Auf dem Abzweigpunkt `git grep -n -E '"downgrade", *"-1"|get_current_head|\(head\)' tests/`
  ausführen. Jeden Treffer, der eine bestimmte Migration meint, auf feste Revisionen umstellen:
  Upgrade bis zur eigenen Revision des Tests, Downgrade auf deren `down_revision`. Prüfungen wie
  `count("(head)") == 1` bleiben. Stand 26.10.2026:
  - `tests/test_db_upgrade.py:201, 227, 280, 289` (Paket A, `6d38d11fc348`). 227 und 280 erwarten
    „Downgrade abgebrochen … erp“ und würden mit P4 als Kopf rot, 201 und 289 prüften still die
    falsche Migration.
  - `gt-abschluss` `tests/test_migration_anlagen_buchung.py:35` (`downgrade -1` vor
    `buchung_id`).
  - `web-oberflaeche` `tests/test_migration_web.py:89, 92` (`SPRACHE` als Kopf) und `:134, 137`
    (zweimal `downgrade -1`).

  Was ein Branch bis zum Abzweigen schon umgestellt hat, entfällt. Die Liste steht im PR. Ist P1
  vorher gemergt, gehören dessen Tests dazu (`KOPF = get_current_head()` im P1-Plan, Schritt 3
  „Vorlieben am Benutzer“; Offener Punkt 8).

  *Umgesetzt (Schritt 1):*
  - Revision `83dfa5750c7f` (`REV`) an `1dd2f6b7c6c8` (P1), `SCHEMA_STAND = "83dfa5750c7f"`.
  - Kopf-Tests: Auf dem Abzweigpunkt findet der `git grep` nur erlaubte Zählungen
    (`count("(head)") == 1`) und den Wächter `tests/test_migration_regeln.py`, den P1
    mitgebracht hat. Alle oben genannten Stellen sind auf `main` schon umgestellt, auch die
    P1-Tests (`VORLIEBEN` fest, `VOR` aus dem `ScriptDirectory`). Umzustellen war nichts;
    mit `REV` als Kopf grün: `test_db_upgrade.py`, `test_migration_web.py`,
    `test_api_schema.py`, `test_migration_{belegvollstaendigkeit,steuerkennzeichen,
    verrechnungen,anlagen_buchung,regeln}.py` (SQLite und PostgreSQL).
  - **Abweichung:** Auch `einstellungsantraege` steht in `db.GESCHUETZT`. Sonst ginge ein
    Massen-`UPDATE` über die Sitzung an der ORM-Sperre „nur aus offen“ vorbei.
  - Trigger-Text „Die Einstellungsversion ist unveränderbar“ (SQLite `RAISE(ABORT)`,
    PostgreSQL `RAISE EXCEPTION '% ist unveränderbar', TG_ARGV[0]`). Trigger unter
    PostgreSQL: `einstellungen_nur_anfuegen` (UPDATE/DELETE je Zeile),
    `einstellungen_nicht_leeren` (TRUNCATE). Die Migration nimmt die Anweisungen aus
    `db/schutz.py`; das Downgrade entfernt die Funktion nur, wenn kein Trigger sie mehr
    nutzt.
  - Zusätzlich im Repository: `pruefe_kette(s)` (Lücke, falscher Vorgänger, veränderte
    Zeile je Abschnitt) und `zeilenhash`/`versionshash`; `normalform` liegt in
    `einstellungen/leser.py` (ohne Fachimporte), `einstellungen.normalform` reicht sie weiter.
  - CI-Job `postgresql` mit `postgres:16.15` (veröffentlicht am 13.08.2026; 16.16 gibt es
    am 04.11.2026 noch nicht), `ACCOUNTI_TEST_PG` auf den Dienst, `pytest` ganz.

### Schritt 2 — Abschnittsleser und Inventar · P4a

- [x] **Inventar als Daten** (`einstellungen/inventar.py`):
  - `ABSCHNITTE` (Name → `AbschnittInfo(ziel: "db"|"datei"|"nur_db", schema_version,
    unvollstaendig_erlaubt)`) für die Abschnitte aus Anhang A und `einrichtung`
  - `BETRIEBSABSCHNITTE`, `BETRIEBSFELDER`, Markierung `Betriebsfeld[...]`, `KEIN_BETRIEBSFELD`
    mit Grund (D7)
  - `GEHEIMFELDER` (D8, mit Prüffunktion je Name, z. B. URL-Form)
  - `PERIODENFELDER` (Feld → `"jahr"|"quartal"|"wirtschaftsjahr"`)
  - `KONTOFELDER` (Pfadmuster → `"sachkonto"|"bankkonto"|"erfolgskonto"`)
  - `MELDEPFLICHTIG` (A60 für P5)
  - `MODELL` (Abschnitt → Modell als Punktname, erst in `pruefung.py` aufgelöst; D16, M4)
  - `UMZUG` (`{"mandant.kontenrahmen": "buchhaltung.kontenrahmen"}`; D16, G-M2)
  - `LADER` (Lader → gelesene Abschnitte, **auch mittelbar**; wird in Schritt 4 gefüllt)

  *Tests* `tests/test_einstellungen_inventar.py`:
  - `::test_jeder_abschnitt_der_vorlage_ist_bekannt` (jeder Abschnitt von
    `config/accounti.example.yaml` steht in `ABSCHNITTE` oder `BETRIEBSABSCHNITTE`)
  - `::test_betriebsfelder_markiert_und_gelistet` (Strukturtest über alle Lader-Modelle und die
    Modelle der Connector-Typen: Markierung ⇔ `BETRIEBSFELDER`; Feld vom Typ `Path` oder mit
    Pfadnamen ohne Markierung nur mit Grund in `KEIN_BETRIEBSFELD`; D7, N11)
  - `::test_geheimfelder_haben_eine_verbrauchsstelle` (Liste gegen die vier Stellen)
- [x] **Leser** (`einstellungen/leser.py`):
  - **Datei-Cache** (Prüfbefund M7): Die Datei wird bei jedem ersten Lesen in einem Stand als
    Bytes gelesen (klein, eine Systemabfrage). Gecacht wird nur das Parsen, Schlüssel ist der
    SHA-256 des Inhalts → geparste Datei; Rückgabe als tiefe Kopie. Eine gleich lange Änderung
    im selben Zeitstempel-Takt (SKR03 → SKR04 im Test) kann so nicht alt bleiben. Dieser Hash der
    ganzen Datei ist nur der Cache-Schlüssel. `datei_hash` (D9) ist der Hash des normalisierten
    Abschnitts, sonst warnten `pruefen` und `serve` bei jeder Änderung an einem Kommentar oder
    einem anderen Abschnitt (G-N2). Ein Stand **heftet** jede Datei beim ersten Lesen an, damit A54
    auch bei einer Dateiänderung mitten im Befehl gilt. Fehlt die Datei, heftet der Stand `{}`
    an (D25).
  - **`DatenbankQuelle.schnappschuss`:** eine Abfrage je Abschnitt nach der neuesten Version bis
    zum Stichtag, mit `version` **und** `hash` der Zeile. Zeilen werden nur dort nachgeladen, wo
    sich der Zeilen-`hash` gegenüber dem Prozess-Cache (Schlüssel `datenbank_schluessel(url)`,
    Abschnitt, `hash`) geändert hat. Mit (url, Abschnitt, Version) als Schlüssel lieferte ein
    laufendes `serve` alte Inhalte, wenn unter derselben URL eine Datenbank neu angelegt wird,
    etwa bei einer Wiederherstellung (G-N7).
    Dazu kommen die Chiffrate der Geheimnisse (nur Name und Chiffrat, für `geheimnis()` ohne
    zweite Verbindung). Alles geschieht in **einer kurzen Lesetransaktion**
    (`with engine.connect() as c:`), danach ist die Verbindung geschlossen; der Schnappschuss
    liegt im Speicher (Prüfbefund N10). Eine offene SQLite-Lesetransaktion blockierte sonst das
    Commit des Befehls. Der Prozess-Cache ist durch ein `threading.Lock` geschützt (Web:
    Anfragen im Threadpool).
  - **Datenbank fehlt oder ist leer:** SQLite-Datei fehlt → leerer Schnappschuss, **ohne** die
    Datei anzulegen. Tabelle fehlt (Schema vor P4) → leer. Datenbank nicht erreichbar → der Stand
    merkt sich den Fehler, und das erste Lesen eines Datenbank-Abschnitts scheitert mit
    `EinstellungenNichtLesbar`, statt still die Datei zu nehmen (fail-closed).
  - **Vorrang in `lies_abschnitt`:**
    1. Betriebsabschnitt → Datei.
    2. `einstellungen.quelle: datei` oder `name in einstellungen.festgelegt` → Datei.
    3. Version im Schnappschuss → Daten. Dann Blätter mit `${` aus der Datenbank durch das
       Platzhalterblatt der Datei an demselben Pfad ersetzen oder entfernen (D7, „`${…}` nur aus
       der Datei“), Betriebsfelder der Version entfernen, danach Betriebsfelder und
       Platzhalterblätter aus der Datei darüberlegen (G-N3). Postfächer und Connectoren werden
       über ihren `name` zugeordnet.
    4. Datei-Abschnitt (fehlende Datei: `{}`, D25).
    5. `{}` (der Lader nimmt die Standards).
  - **`nur_db`-Abschnitte** (`einrichtung`) lesen nie die Datei.
  - **`ueberlagert`** legt einen abgeleiteten Schnappschuss an, in dem die genannten Abschnitte
    wie Versionen wirken, also auch mit Betriebs- und Platzhalterfeldern und denselben Regeln für
    `${`.
  - **`pruefmodus`** (D16): Kontextvariable; `im_pruefmodus()` fragen `_ersetze_variablen`
    (`erechnung/versand.py`, auch von `aufgaben` genutzt) und `loese_auf`
    (`belege/kanaele/einstellungen.py`). Ein fehlender `${VAR}` bleibt dann als Text stehen.
  - **`parse_text`:** `yaml.safe_load` mit Grenze 64 KB. `AnchorToken`/`AliasToken` aus
    `yaml.scan` werden abgewiesen. Der Fehler nennt Zeile und Spalte.
  - **Pilot-Lader** (Prüfbefund M9, damit die Tests in Schritt 3 echte Lader haben):
    `lade_buchhaltung` (mit Fallback `mandant.kontenrahmen` aus Paket A) und `lade_elster` lesen
    schon hier über `lies_abschnitt`, ohne `is_file`-Wächter (D25). Der Golden-Test bleibt grün.

  *Tests zuerst* in `tests/test_einstellungen_leser.py` (AK76, A41, A42, A54):
  - `::test_ohne_stand_nur_datei` (E5)
  - `::test_datenbank_schlaegt_datei`
  - `::test_ohne_beides_gilt_der_standard`
  - `::test_festgelegter_abschnitt_nimmt_die_datei_trotz_version`
  - `::test_quelle_datei_fuer_alle`
  - `::test_umgebung_schlaegt_alles` (`versand.absender: ${VERSAND_ABSENDER}` in der Datei, Version mit
    anderem Absender → `lies_abschnitt` liefert den Platzhalter der Datei; den aufgelösten Wert
    über `lade_versand` prüft Schritt 4)
  - `::test_platzhalter_aus_der_datenbank_wird_nicht_weitergegeben` (Version mit `betreff: "x
    ${HOME}"` → Blatt entfällt; Version mit `smtp.passwort: ${SMTP_PASS}` und gleichem Blatt in
    der Datei → Blatt der Datei; H1)
  - `::test_fehlende_datei_ist_leer_versionen_gelten` (Pfad existiert nicht, Version von
    `buchhaltung` → `lade_buchhaltung` liefert den Datenbank-Wert; `quelle_vorhanden` ohne beides
    falsch; D25)
  - `::test_pilot_lader_lesen_ueber_den_leser` (`lade_buchhaltung`, `lade_elster` unter
    `mit_quelle` mit Version)
  - `::test_pruefmodus_fehlende_variable_bleibt_text`
  - `::test_betriebsfeld_kommt_aus_der_datei` (`elster.eric.bibliothek`, `pruefung.archiv`, Postfach
    `ca_datei` je Name)
  - `::test_betriebsabschnitt_nie_aus_der_datenbank`
  - `::test_nur_db_abschnitt_ignoriert_die_datei`
  - `::test_schnappschuss_bleibt_in_der_anfrage` (zwei Lesevorgänge, dazwischen neue Version → beide
    alt)
  - `::test_datei_aenderung_im_stand_unsichtbar`
  - `::test_cache_liest_neu_nach_gleich_langer_aenderung` (SKR03 → SKR04, `os.utime` auf den alten
    Zeitstempel → neuer Stand sieht SKR04; M7)
  - `::test_datei_hash_nur_ueber_den_abschnitt` (Kommentar bzw. anderer Abschnitt geändert →
    `herkunft_roh(…).datei_hash` gleich; G-N2)
  - `::test_cache_erkennt_neu_angelegte_datenbank` (SQLite-Datei mit Version 1 lesen, Datei löschen,
    unter derselben URL neu anlegen, Version 1 mit anderem Inhalt → neuer Stand sieht den neuen
    Inhalt; G-N7)
  - `::test_betriebsfeld_der_version_gilt_nie` (rohe Version mit `pruefung.archiv`, Datei ohne →
    Standard; G-N3, A42)
  - `::test_rueckgabe_ist_eine_kopie`
  - `::test_schnappschuss_haelt_keine_verbindung` (nach `binde` hält eine zweite Sitzung `BEGIN
    EXCLUSIVE` und committet ohne Warten; N10)
  - `::test_prozess_cache_unter_threads` (acht Threads lesen gleichzeitig, ein Ergebnis)
  - `::test_stichtag_nimmt_die_damals_gueltige_version`
  - `::test_ueberlagert_wirkt_nur_im_block`
  - `::test_keine_neue_sqlite_datei`
  - `::test_ohne_tabelle_wie_datei`
  - `::test_nicht_erreichbar_fail_closed`
  - `::test_parse_text_grenze_anker_zeile_spalte`

  *Umgesetzt (Schritt 2), Abweichungen und Ergänzungen:*
  - **`KonfigurationError` liegt jetzt in `einstellungen/leser.py`**; `konfiguration.py`
    führt ihn weiter (`from … import KonfigurationError as KonfigurationError`, dieselbe
    Klasse). Der Leser meldet kaputtes YAML, fremde Kodierung, eine unlesbare Datei und
    einen Abschnitt, der keine Zuordnung ist, als `KonfigurationError` (Texte wie
    `konfiguration.lies_yaml`), darf aber `konfiguration.py` nicht importieren (D1, kein
    Zyklus: `konfiguration` importiert den Leser).
  - `EinstellungsquelleFehlt` und `EinstellungenNichtLesbar` sind `RuntimeError`, keine
    `KonfigurationError`: Routen und Befehle fangen `KonfigurationError` und zeigten sonst
    eine Meldung statt der 500 (D5). Die Meldungen nennen keinen Pfad und keine URL.
  - **Abschnitt keine Zuordnung** (`kasse: 5`): `lies_abschnitt` bricht mit „Abschnitt
    'kasse' muss eine Zuordnung sein“ ab (bisher je Lader verschieden: übergangen,
    Pydantic-Fehler oder dieselbe Meldung). `mandant: null` gilt als fehlend.
  - **Fehlende Datei** (D25) wirkt schon bei den Piloten: `lade_elster` auf einen
    fehlenden Pfad liefert jetzt dasselbe wie auf eine leere Datei (mit den OSS-Konten aus
    den Standards von `integrationen`); `tests/test_elster_konfiguration.py::
    test_ohne_datei_und_ohne_abschnitt_gelten_standards` ist darauf angepasst.
  - **Anker, Aliase und 64 KB** prüft nur `parse_text` (Eingaben über CLI und später den
    Browser). Die Datei des Betreibers liest `lies_datei` wie bisher mit `yaml.safe_load`;
    sonst bräche ein Update bestehende Dateien mit Ankern. Die Größe der Normalform beim
    Übernehmen aus der Datei prüft P4b (Offener Punkt 9).
  - `herkunft_roh` liefert zusätzlich `version_datei_hash` (der `datei_hash` der Version),
    damit `pruefung.herkunft` „Datei nach der letzten Version geändert“ ohne zweite
    Abfrage erkennt; `datei_hash` ist der Hash des Datei-Abschnitts jetzt.
  - Neu im Leser: `abschnitt_hash(daten)` (D9), `binde_gesellschaft` (Schritt 3),
    `aktueller_stand`/`setze_stand`/`ruecksetzen` (Middleware), `Stand.ersatz` und
    `Stand.fremde_pfade` (D3, D5). `neuer_stand(web=…, ersatz=…, fremde_pfade=…)`.
    `mit_quelle(…, konfiguration)` bindet streng (nur diese Datei).
  - Der Schnappschuss liest per SQL ohne die Tabellenmodule (eine Abfrage für die neueste
    Version je Abschnitt, Zeilen nur bei unbekanntem Hash, dazu die Chiffrate) und hält
    die Verbindung nur für diese Lesetransaktion (URL: eigene Engine ohne Pool).
  - Markiert mit `Betriebsfeld[...]`: `ElsterEinstellungen.eric`,
    `PruefEinstellungen.archiv|kontenrahmen_datei`, `WebhookEinstellungen.host|port`,
    `EmailPostfach.ca_datei`, `UstIdEinstellungen.url`, `FinTSEinstellungen.produkt_id`,
    `AbschlussEinstellungen.kontenzuordnung`, `AnlagenEinstellungen.rechtsstand_datei`
    (Alias `rechtsstand`). `KEIN_BETRIEBSFELD`: `belegkanaele.dateitypen`,
    `email[].ordner|ziel_ordner`, `webhook.max_dateien` und die URL-Pfade des
    JSON-Connectors (`liste.pfad`, `datei`, `datei.pfad`, `felder.dateiname`).
  - `MODELL` führt nur vorhandene Modelle; `datev`, `import`, `llm`, `einrichtung` trägt
    Schritt 5 nach, `bwa` 10b-2. `LADER` enthält die beiden Piloten.
  - Der Datei-Abschnitt `einstellungen` (`quelle`, `festgelegt`) wird im Leser schon
    geprüft (Wert von `quelle`, unbekannte Abschnitte in `festgelegt` mit Pfad); das
    Modell `EinstellungsQuelle` aus Schritt 5 kann diese Prüfung übernehmen.
  - Zusätzliche Tests: `::test_festlegung_mit_unbekanntem_abschnitt_ist_ein_fehler`,
    `::test_pilot_lader_fallback_mandant_kontenrahmen`,
    `::test_web_ungebunden_und_fremder_pfad_fail_closed`,
    `::test_cli_fremder_registry_pfad_fail_closed`, `::test_ersatzquelle_beim_ersten_lesen`,
    `::test_kaputtes_yaml_und_fremde_kodierung_sind_konfigurationsfehler`,
    `::test_datei_cache_ohne_wiederholtes_parsen`; im Inventar
    `::test_betriebsfelder_liegen_in_datenbank_abschnitten`,
    `::test_modelle_und_lader_sind_aufloesbar`.

### Schritt 3 — Bindung in CLI und Web · P4a

- [x] **CLI** (`betrieb/cli.py`):
  - `richte_kontext_ein` legt `neuer_stand()` an (Rücksetzen über `ctx.call_on_close`).
  - `binde_datenbank_parameter(ctx.command)` verkettet Callbacks an jedem Parameter `db` aller
    Ebenen, idempotent markiert (D3).
  - Ohne Bindung bis zum ersten Lesen gilt `kontext.standardwerte.get("db") or STANDARD_DB`
    (D3). `befehle.STANDARD_DB` ist neu, `DB_OPTION` nutzt ihn.
  - Der Stand kennt das Kürzel der gebundenen Gesellschaft und die Konfigurationspfade der
    Registry für die Ausnahme in D5 (fremder Registry-Pfad → `EinstellungsquelleFehlt`).
  - `fristen`, `pruefen regeln`, `kanaele connectoren`, `elster pin` bekommen `db: str =
    DB_OPTION` (M1).
  - `gesellschaft liste|zeigen`: Kontenrahmen und Wirtschaftsjahr je Gesellschaft unter
    `mit_quelle(DatenbankQuelle(g.datenbank), g.konfiguration)` (M2).

  *Tests* `tests/test_cli_einstellungsquelle.py` (Lader aus den Piloten in Schritt 2):
  - `::test_db_option_bindet_die_quelle`
  - `::test_gesellschaft_bindet_ihre_datenbank` (`-g b` → `buchhaltung.kontenrahmen` aus b, AK78)
  - `::test_config_anderer_datei_datenbank_gilt` (E5)
  - `::test_befehl_ohne_db_nimmt_standardwert`
  - `::test_ohne_db_und_gesellschaft_standard_db` (Version in `./accounti.db` im Arbeitsordner →
    `fristen --jahr 2027` und `ustva …` sehen denselben Voranmeldungszeitraum; M1)
  - `::test_jeder_befehl_mit_config_hat_db` (Strukturtest über den Typer-Baum; Ausnahmeliste
    leer; M1)
  - `::test_gesellschaft_liste_zeigt_kontenrahmen_je_datenbank` (SKR04 nur als Version in b → `liste`
    und `zeigen b` zeigen SKR04, a bleibt SKR03; M2)
  - `::test_fremder_registry_pfad_fail_closed` (gebunden an a, Lader liest
    `b.konfiguration` → `EinstellungsquelleFehlt`; M2)
  - `::test_schnappschuss_vor_dem_rumpf` (Testbefehl hält `BEGIN EXCLUSIVE` auf seiner SQLite-Sitzung
    und ruft dann `lade_buchhaltung` → kein Warten, < 1 s)
  - `::test_zwei_lader_ein_stand` (A54)
  - `::test_gruppe_mit_eigener_db_und_unterbefehl` (`ustva --db … pruefen`)

  *Umgesetzt (Schritt 3, CLI):*
  - `richte_kontext_ein` ruft `richte_stand_ein`: `ctx.with_resource(neuer_stand(ersatz=…,
    fremde_pfade=…))`, Kürzel am Stand, dann `binde_datenbank_parameter(ctx.command)`
    (Callback je Parameter `db`, vorhandener Callback läuft vorher, Marke am Parameter;
    nicht bei `resilient_parsing`). Typer baut den Click-Baum je Aufruf neu, die Marke
    wirkt also je Aufruf.
  - **Gruppe und Unterbefehl:** Beide binden; es gilt der zuletzt geparste Parameter, also
    der des Unterbefehls — dieselbe Datenbank, die sein Rumpf liest (`ustva --db X
    pruefen` liest die Daten aus der Standarddatenbank des Unterbefehls; das ist das
    bisherige Verhalten der Gruppen-Optionen). Der Test prüft genau diese Übereinstimmung.
  - `EinstellungenNichtLesbar` und `EinstellungsquelleFehlt` fängt `Wurzelgruppe.invoke`:
    Meldung, Exit 1 statt Traceback (Test `::test_unlesbare_datenbank_meldung_statt_traceback`).
  - `gesellschaft liste|zeigen` lesen je Gesellschaft unter `mit_quelle(DatenbankQuelle(
    g.datenbank), g.konfiguration)`; `_wirtschaftsjahr` liest über `lies_abschnitt`
    (`inventar.LADER`), ohne Datei jetzt „Kalenderjahr“ statt „—“ (D25). **Abweichung:**
    Ist die Datenbank einer Gesellschaft nicht erreichbar, zeigt `zeigen` alle übrigen
    Angaben, bei Kontenrahmen und Wirtschaftsjahr „— (Datenbank nicht lesbar)“, und endet
    mit der Meldung und Exit 1; `liste` zeigt die Meldung in der Zeile.
    `tests/test_cli_gesellschaft.py::test_gesellschaft_liste_und_zeigen_ohne_passwort`
    ist darauf umgestellt (bisher die Werte der Datei bei unerreichbarer Datenbank).
  - Eine ungültige URL (`--db kein-url`) wirft beim Binden nicht; der Schnappschuss merkt
    den Fehler (sonst endete `db upgrade --db kein-url` mit einem Traceback).
  - Zusätzlich: `::test_neue_db_option_an_den_vier_befehlen`.
- [x] **Web**:
  - `api/einstellungsstand.py`: reine ASGI-Middleware, in `erstelle_app` registriert, und zwar
    **vor** `app.add_middleware(Sicherheit)`. In Starlette liegt die zuletzt hinzugefügte
    Middleware außen. So bleibt Sicherheit mit der 500-Seite außen, wie mit P1 vereinbart (G-N1).
  - `Dienste.quelle(kuerzel) -> DatenbankQuelle` auf der vorhandenen Engine.
  - `leser.binde_gesellschaft(stand, dienste, g)` am Ende von `angemeldet` und in `api_zugang`,
    über `run_in_threadpool`, Modus streng (D5). Ist P1 vorher auf `main`, sitzt der Aufruf im
    gemeinsamen Kern von `angemeldet` und `vielleicht_angemeldet` (G-N1, Offener Punkt 7).
  - Name ohne Registry beim Start (D21) folgt in Schritt 4, die Startmeldung zu Abweichungen in
    Schritt 13 (G-M3). Beide brauchen Teile, die erst dort entstehen.

  *Tests* `tests/test_api_einstellungsstand.py`:
  - `::test_datenbank_wert_wirkt_in_freigaben` (`elster.voranmeldungszeitraum: quartal` als Version →
    `/freigaben/ustva` mit `2026-Q3` ist kein Fehler)
  - `::test_schnappschuss_je_anfrage` (Testroute: Lader, neue Version, Lader → gleich; nächste
    Anfrage → neu)
  - `::test_gesellschaften_getrennt` (Sitzung in a, Version nur in b)
  - `::test_rest_token_bindet_seine_gesellschaft` (`POST /api/v1/laeufe/bank` mit
    `buchhaltung.bank_konto` aus der Version; Pilot `lade_buchhaltung`)
  - `::test_ungebunden_fail_closed` (Testroute ohne Anmeldung liest `lade_elster` → 500,
    `EinstellungsquelleFehlt`)
  - `::test_anderer_pfad_fail_closed`
  - `::test_betriebsabschnitte_ohne_bindung`
  - `::test_sicherheit_ist_die_aeusserste_middleware` (`app.user_middleware[0].cls is Sicherheit`;
    `EinstellungsquelleFehlt` in einer Testroute ergibt die 500-Seite der Sicherheits-Middleware
    mit ihren Kopfzeilen; G-N1)

  Die Rechte-Matrix und der CSP-Test aus 10a/10b bleiben unverändert grün (keine neue Route).

  *Umgesetzt (Schritt 3, Web):* P1 ist gemergt — die Bindung sitzt im gemeinsamen Kern
  `sitzung._lade_gebunden` (ein Sprung in den Threadpool: Sitzung lesen, dann
  `binde_gesellschaft`), den `angemeldet` und `vielleicht_angemeldet` nutzen;
  `merke_benutzersprache` bindet nicht. `api_zugang` bindet nach der Tokenprüfung.
  `Dienste.quelle(kuerzel)` hält je URL eine `DatenbankQuelle` auf der vorhandenen Engine
  (`schliesse` leert sie mit). `test_rest_token_bindet_seine_gesellschaft` fängt
  `bank.lauf.bank_lauf` ab und prüft die übergebene `Buchhaltung` je Token (a: Datei, b:
  Version) und den Stand einer Token-Route. Zusätzlich
  `::test_dienste_quelle_nutzt_die_engine_der_gesellschaft`,
  `::test_rechte_haengen_nicht_an_der_bindung`; `::test_gesellschaften_getrennt` wechselt
  per `POST /gesellschaft` von a nach b.

### Schritt 4 — Lader-Umbau · P4a

- [ ] **Jeder Lader liest über `lies_abschnitt`** (gleiche Signatur, gleicher Modelltyp, gleiche
  Fehlertexte). Der `is_file`-Wächter fällt dabei weg (D25). Wo er eine Meldung trug („Vorlage
  kopieren“), steht sie hinter `not quelle_vorhanden(pfad, name)`:

  | Datei | Lader | Abschnitte | Umbau |
  |-------|-------|------------|-------|
  | `konfiguration.py` | `lade_firma`, `lade_buchhaltung` (Pilot aus Schritt 2), `lade_ustid_pruefung` (`ACCOUNTI_EVATR_URL` bleibt), `lade_eigene_firma` | mandant, buchhaltung, ustid_pruefung | 4 Stellen; `lade_firma` nennt bei Fehlern zusätzlich „Einstellungen › Firma & Steuern“ (AK77) |
  | `abschluss/konfiguration.py` | `_abschnitt` → `lade_abschluss` (liest mittelbar buchhaltung, integrationen, datev), `gewinnermittlung_angegeben`, `lade_kasse`, `lade_wirtschaftsjahr_beginn` (Paket F) | abschluss, kasse, datev | `_abschnitt` wird zu `lies_abschnitt` |
  | `aufgaben/einstellungen.py` | `lade_aufgaben_einstellungen` | aufgaben | — |
  | `erechnung/versand.py` | `lade_versand` | versand | — |
  | `mahnwesen/konfiguration.py` | `lade_mahnwesen` | mahnwesen | — |
  | `pruefung/einstellungen.py` | `lade_pruefung` | pruefung | — |
  | `belege/kanaele/einstellungen.py` | `lade_belegkanaele` | belegkanaele | — |
  | `anlagen/konfiguration.py` | `lade_anlagen` | anlagen | — |
  | `elster/konfiguration.py` | `lade_elster` (Pilot; mittelbar integrationen, buchhaltung über `_mit_oss_konten`), `lade_oss`, `lade_mandant` | elster, mandant | 3 Stellen |
  | `integrationen/einstellungen.py` | `_abschnitt` → `lade_integrationen`, `lade_steuerangaben` | integrationen, mandant | — |
  | `bank/einstellungen.py` | `lade_bank_einstellungen` | bank | — |
  | `zahlung/konfiguration.py` | `lade_zahlung` (Auftraggeber aus `mandant`) | zahlung, mandant | — |
  | `export/datev_stammdaten.py` | `lade_datev_mandant` | datev, mandant | über `lade_datev` (Schritt 5) |
  | `auth/einstellungen.py`, `api/einstellungen.py` | `lade_auth`, `lade_server` | auth, server | Betriebsabschnitte |
  | `betrieb/gesellschaften.py` | `lies_yaml` → `leser.lies_datei` | gesellschaften | `lies_yaml` entfällt |
  | `befehle/gesellschaft.py` | `_wirtschaftsjahr`, `lade_buchhaltung` in `liste`/`zeigen` | datev, buchhaltung | beides je Gesellschaft unter `mit_quelle(DatenbankQuelle(g.datenbank), g.konfiguration)` (schon Schritt 3, M2) |
  | `befehle/betrieb.py` | `_wirtschaftsjahr_beginn` (über `lies_yaml`) | datev | `lade_wirtschaftsjahr_beginn` |
  | `pruefung/verfahrensdoku.py` | `_Doku.roh()` (genutzt nur für `mandant` und `belegkanaele`, Z. 129, 207, 732) | mandant, belegkanaele | `_Doku.abschnitt(name)` über `lies_abschnitt`, in `LADER` eingetragen; `roh()` entfällt (G-M3: kein `wirksam_alle` nötig, `wirksam` liegt erst in P4b) |
  | `api/dienste.py` | `einzelne_gesellschaft` (Name über `lade_eigene_firma`) | mandant | ohne Registry unter `mit_quelle(DatenbankQuelle(db), config)` (D21, aus Schritt 3 hierher, G-M3); mit Registry bleibt der Name der Registry |

  **Positivliste** (Daten-Dateien, keine Konfiguration):
  - `einstellungen/leser.py`
  - `abschluss/kontenrahmen.py`, `abschluss/euer.py`
  - `anlagen/rechtsstand.py`
  - `pruefung/regeln/richtigkeit.py`
  - `importers/profil.py` (`config/banken.yaml`)
  - `klassifikation/regeln_loader.py`, `klassifikation/lernen.py` (Regeldatei)
  - `i18n/__init__.py`

  Jeder Eintrag hat einen Grund im Test.
  *Tests zuerst*:
  - `tests/test_lader_umbau.py::test_safe_load_nur_in_der_positivliste` (AST über `src/`: Aufrufe
    `yaml.safe_load|load|full_load|unsafe_load` und Importe `from yaml import …load`)
  - `::test_kein_lies_yaml_mehr`
  - `::test_jeder_lader_ist_registriert` (AST: jede Funktion, die `lies_abschnitt` aufruft, steht in
    `inventar.LADER`)
  - `::test_lader_lesen_was_registriert_ist[<lader>]` (jeder Lader läuft unter einem
    aufzeichnenden Stand; die gelesenen Abschnitte, auch mittelbar, sind genau die in `LADER`
    eingetragenen, N1)
  - `::test_kein_is_file_waechter_mehr` (AST: kein `is_file()` in Ladern aus `LADER`, die einen
    Datenbank-Abschnitt lesen; `lade_auth`, `lade_server`, `lade_gesellschaften` ausgenommen; D25)
  - `::test_ohne_datei_gelten_versionen[<lader>]` (Pfad existiert nicht, Versionen von `mandant`
    und `buchhaltung` → `lade_firma` und `lade_buchhaltung` liefern die Datenbank-Werte; ohne
    Version: die bisherige Meldung bzw. die Standards; H3)
  - `::test_datenbankwert_wirkt[<lader>]` (parametrisiert über `LADER`: je Lader ein Feld, eine
    Version, erwarteter Wert unter `mit_quelle`)
  - `::test_umgebung_schlaegt_alles_im_lader` (`versand.absender: ${VERSAND_ABSENDER}` in der
    Datei, Version mit anderem Absender → `lade_versand` liefert den Umgebungswert; AK76)
  - `::test_platzhalter_der_datenbank_wird_nie_aufgeloest` (Version mit `versand.betreff: "x
    ${HOME}"` per Repository eingefügt → `lade_versand().betreff` ist der Standard, kein Inhalt
    von `HOME`; ebenso `belegkanaele.connectoren[].kopfzeilen`; H1)
  - `::test_cli_wirkt_mit_datenbankwert` (`fristen --jahr 2027` → Quartalsfristen aus der Version;
    `rechnung neu` → Zahlungsziel aus der Version)
  - `::test_andere_gesellschaft_eigene_werte` (AK78)
  - `tests/test_api_einstellungsstand.py::test_name_ohne_registry_beim_start_aus_der_datenbank`
    (mit Registry: Name der Registry; aus Schritt 3 hierher, G-M3)
  - `tests/test_pruefung_verfahrensdoku.py::test_doku_liest_mandant_aus_der_datenbank`
    (Version von `mandant` mit anderem Namen → Kopf und Abschnitt 1 nennen ihn; G-M3)

  Der Golden-Test aus Schritt 0 bleibt **ohne Änderung** grün. Rot; Umbau Lader für Lader; grün.

### Schritt 5 — Neue und geänderte Felder, fehlende Modelle (A44, A124) · P4a

- [ ] **`mandant`**: `rechtsform: Literal["einzelunternehmen", "ek", "gbr", "ohg", "kg", "gmbh",
  "ug", "gmbh_co_kg", "ag", "eg", "partg", "sonstige"] | None`, `kennfarbe: int | None` (1–6). Beides
  steht in `Firma` und wird nachsichtig in `lade_eigene_firma` gelesen (P5 macht `kennfarbe`
  wählbar; P1 leitet die Farbe aus dem Kürzel ab und liest keine YAML, P1-Plan B4). Dazu `sachkonten_laenge: int = 4` (heute nur von `datev_stammdaten` roh gelesen;
  D16, M4) und `_pflichten` mit der Fehlerart `pflicht_fehlt` (D16, M5; Text unverändert).
- [ ] **`datev`**: Modell `DatevEinstellungen` (`berater_nummer: str | None`, `mandanten_nummer:
  str | None`, je nur Ziffern; eine Zahl aus der YAML wird wie heute über `str()` zu Text, damit
  `berater_nummer: 12345` gültig bleibt, Prüfbefund N9; führende Nullen gehen dabei wie heute
  verloren, die Vorlage schreibt Text), `wirtschaftsjahr_beginn: TagMonat | None`) und
  `lade_datev(pfad)`.
  - `TagMonat` liest `"MM-TT"`, `"TT.MM."`, ein Datum mit Jahr (das Jahr zählt nicht, N2) und das
    YAML-Datum.
  - Geschrieben wird `"MM-TT"`.
  - `als_datum()` liefert `date(2000, m, t)` (Schaltjahr für den 29.02., wie
    `_beginn_im_jahr` in Paket F).
  - Umgestellt werden `lade_wirtschaftsjahr_beginn`, `lade_datev_mandant`,
    `befehle/gesellschaft`, `befehle/betrieb`, `export/datev_stammdaten.wirtschaftsjahr_beginn`.

  *Tests* `tests/test_konfiguration.py::test_wirtschaftsjahr_tag_monat[2026-01-01|"07-01"|"01.07."|date]`,
  `::test_wirtschaftsjahr_ungueltig_nennt_pfad`, `::test_rechtsform_und_kennfarbe`,
  `::test_kennfarbe_ausserhalb_1_bis_6`, `::test_datev_nummern_als_zahl_und_text` (N9),
  `::test_pflichten_fehlerart_pflicht_fehlt_text_gleich` (M5).
- [ ] **`llm`** (D18): `LlmEinstellungen(provider, model, api_key: str | None, auto_buchen_schwelle
  = 0.95, pruefung_schwelle = 0.70)` mit `pruefung_schwelle ≤ auto_buchen_schwelle`,
  `lade_llm(pfad)`.
  - **`${VAR}` nur in `api_key` und nachsichtig** (G-M5): Fehlt die Variable (die Vorlage hat
    `api_key: "${ANTHROPIC_API_KEY}"`, `config/accounti.example.yaml:74`), ist `api_key=None`.
    Ab P4b folgt dann D8 (Geheimnis), und ohne Geheimnis liest litellm den Schlüssel wie heute selbst
    aus der Umgebung. Kein `_ersetze_variablen` über den Abschnitt, das bei fehlender Variable
    abbräche (`erechnung/versand.py:89–94`). Die Schwellen sind so immer lesbar: `bank lauf
    --no-llm`, `classify` ohne LLM und `verfahrensdoku` laufen ohne die Variable wie heute
    (`LLMEngine() if llm else None`, `cli.py:2261, 2329`).
  - Verdrahtet in `cli.classify`, `cli.bank_lauf` und `api/rest/laeufe`:
    `KlassifikationsEngine(auto_buchen_schwelle=…)`, `kontiere_umsaetze` reicht sie an
    `zu_buchungssatz(auto_schwelle=…)` durch, und `LLMEngine(model=f"{provider}/{model}",
    api_key=…)`.
  - `pruefung/verfahrensdoku.py` nimmt die Schwelle aus `lade_llm` statt aus dem
    Signatur-Standard.

  *Tests* `tests/test_llm_einstellungen.py::test_standard_wie_bisher`,
  `::test_schwelle_wirkt_auf_den_status` (Confidence 0,9 mit Schwelle 0,85 → auto,
  mit 0,95 → zur Prüfung), `::test_pruefschwelle_ueber_auto_ist_fehler`,
  `::test_verfahrensdoku_nennt_die_wirksame_schwelle`, `::test_ohne_api_key_variable_laeuft_no_llm`
  (Vorlage, `ANTHROPIC_API_KEY` nicht gesetzt → `lade_llm().api_key is None`, `bank lauf --no-llm`
  und `verfahrensdoku` mit Exit 0; G-M5).
- [ ] **`import`**: `ImportEinstellungen(standard_bank: str | None, duplikat_check: bool = True)`,
  `lade_import`. Die Wirkung bleibt unverändert (Grenzen).
- [ ] **Datei-Abschnitt `einstellungen`**: `EinstellungsQuelle(quelle: Literal["datenbank",
  "datei"] = "datenbank", festgelegt: list[str] = [])`. Unbekannte Abschnittsnamen sind ein
  Fehler mit Pfad.
- [ ] **Datenbank-Abschnitt `einrichtung`**: `EinrichtungEinstellungen(ausgeblendet: list[str] =
  [])`, nur Datenbank (für P7).
- [ ] **`elster.vier_augen: bool = False`** kommt erst mit P4c in Schritt 11 (Feld, Stufen,
  Wirkung zusammen; D28).

  *Tests* `tests/test_einstellungen_inventar.py::test_neue_felder_abwaertskompatibel` (jede
  Golden-Konfiguration ergibt dieselben Werte, die neuen Felder ihren Standard; AK80).

### Schritt 6 — Periodenwerte (E3, A46 Teil 1) · P4a

- [ ] **`einstellungen/perioden.py`**: `wert_fuer(feldwert, zeitraum)`, `setze_ab(feldwert, ab,
  wert)` (D14), `schluessel_fuer(art, zeitraum)` (Jahr, `"JJJJ-Qn"`, WJ nach Paket F).
  Pydantic-Typen sind `Periodisch[T] = T | dict[int, T]` bzw. mit Quartalsschlüsseln, je mit
  Validator (Schlüsselform, mindestens ein Eintrag).
- [ ] **Rohfelder umbenennen** (D14, M6): `voranmeldungszeitraum_roh`, `dauerfrist_roh`,
  `oss_roh`, `gewinnermittlung_roh`, je mit `alias` auf den Dateinamen und
  `populate_by_name=True`. Zuerst umbenennen, `mypy src/` laufen lassen: Die Fehlerliste ist die
  vollständige Liste der Verbraucher. Sie wird mit der Liste unten abgeglichen und im PR
  genannt.
- [ ] **Felder und Verbraucher** (jeder fragt mit seinem Zeitraum):
  - `elster.voranmeldungszeitraum` und `elster.dauerfristverlaengerung` → `ElsterEinstellungen.
    voranmeldungszeitraum_fuer(jahr)`, `dauerfrist_fuer(jahr)`. Verbraucher: `elster/ustva.py`
    (Zeitraumprüfung, Dezember mit Dauerfrist), `elster/dauerfrist.py`, `elster/zahllast.py`,
    `befehle/fristen.py`, `steuer/fristen` (Aufrufer), `pruefung/verfahrensdoku.py`.
  - `mandant.oss` → `Firma.oss_am(datum)`, `lade_oss(pfad, zeitraum)` (Pflichtparameter; heute
    `bool(dict)`, also `True` für jede Zuordnung), `integrationen.Kontext.oss_am(datum)`.
    Verbraucher: `erechnung/erzeuger/aufbau.py` (Rechnungsdatum), `befehle/ustva.py`,
    `befehle/fristen.py`, `api/seiten/freigaben.py`, `integrationen/buchung.py`.
  - `abschluss.gewinnermittlung` → `AbschlussEinstellungen.gewinnermittlung_fuer(wj)` und
    `gewinnermittlung_angegeben(pfad, wj)` (Paket F; heute Rohwert, bei einer Zuordnung `None`).
    Verbraucher: `abschluss/euer.py`, `vortrag.py`, `abgrenzung.py`, `pruefungen.py`,
    `befehle/abschluss.py`, `db/tabellen_pruefung.py` (aus dem Buchungsdatum über
    `wirtschaftsjahr_zum`), `opos/verbuchung.py`, `cli.py` (`gewinnermittlung_angegeben`, um
    Z. 1455), `pruefung/verfahrensdoku.py` (Z. 165 und 556: Wirtschaftsjahr des Stichtags).

  *Tests zuerst* in `tests/test_einstellungen_perioden.py`:
  - `::test_einzelwert_gilt_immer`
  - `::test_ab_zeitraum_groesster_schluessel`
  - `::test_fruehester_eintrag_gilt_auch_davor`
  - `::test_umwandlung_einzelwert`
  - `::test_quartalsschluessel_oss`
  - `::test_wirtschaftsjahr_schluessel_abweichendes_wj`
  - `::test_ungueltiger_schluessel_nennt_pfad`
  - `::test_kein_zugriff_auf_rohfelder` (AST: `*_roh` nur in `perioden.py` und im Modul des
    Modells, M6)

  Dazu `tests/test_elster_ustva.py::test_dezember_2026_monat_trotz_quartal_2027` (AK31, dritter
  Punkt), `tests/test_steuer_fristen.py::test_kalender_je_jahr_mit_periodenwert`,
  `tests/test_erechnung_aufbau.py::test_oss_ab_quartal_nach_rechnungsdatum`,
  `tests/test_elster_konfiguration.py::test_lade_oss_mit_zuordnung_je_zeitraum` (`{2026-Q1:
  false, 2027-Q1: true}` → 2026 falsch, 2027 wahr; M6),
  `tests/test_abschluss_euer.py::test_gewinnermittlung_je_wirtschaftsjahr` und
  `tests/test_abschluss_konfiguration.py::test_gewinnermittlung_angegeben_mit_zuordnung` (M6).
  Golden bleibt grün (Einzelwerte).

> **PR P4b „Schreiben“: Schritte 7–10, 12, 13, 16** (D28), abzweigen nach dem Merge von P4a.
> Vorher entscheidet der Nutzer D6 (Offener Punkt 5). D26 ist entschieden (Offener Punkt 6).

### Schritt 7 — Schreiben: Versionen, Journal, Gleichzeitigkeit, Validierung · P4b

- [ ] **`einstellungen/pruefung.py`**: `validiere` über die Lader unter Überlagerung, zweimal
  (ohne und mit Änderung) im Prüfmodus, mit der Zurechnung aus D16; `unbekannte_felder` (D16,
  M4); `querpruefungen(s, pfad, wirksam, gesetzt)` nur für gesetzte Werte (D16). Neu ist
  `Kontenrahmen.form_fehler(konto, sachkonten_laenge) -> str | None` (Form statt „in einer
  Spanne“, M10), dazu `mit_eingerichteten_konten` für Bankkonto-Sachkonten. `fehlend` kommt aus
  den Fehlerarten `missing` und `pflicht_fehlt` bei `unvollstaendig_erlaubt` (M5).
- [ ] **`einstellungen/dienst.py::speichere`**:
  1. Unter `journal.schreibsperre` die aktuelle Version **frisch** lesen (nicht aus dem
     Schnappschuss). Weicht sie von `erwartete_version` ab → `KonfliktError` mit Person und
     Zeitpunkt der aktuellen Version (A45). Es wird nichts geschrieben.
  2. Für jeden Abschnitt, der in der Datei festgelegt ist, folgt `FestgelegtError`
     (E2, AK26).
  3. Bei geänderten Betriebsfeldern folgt `BetriebsfeldError` mit „vom Betreiber in `<Datei>`
     festgelegt“. **Jedes** Blatt der neuen Daten mit `${`, das nicht gleich dem Blatt der Datei
     ist, ergibt `PlatzhalterError` (D7, H1), Klartext in Geheimfeldern
     `GeheimnisImKlartextError` (D8). Unbekannte Felder **der Änderung** ergeben
     `ValidierungError` mit Vorschlag (D16, M4).
  4. Basis ist die wirksame Version, sonst der Roh-Abschnitt der Datei (D6). Unbekannte Felder
     der Basis entfallen mit Hinweis, `inventar.UMZUG` bringt `mandant.kontenrahmen` nach
     `buchhaltung.kontenrahmen` (D16, G-M2; A53, N1). Gleiche Platzhalterblätter und
     Betriebsfelder werden vor dem Speichern entfernt (D7, G-N3). Daten, die mit dem aktuellen
     Stand gleich sind, ergeben keine Version.
  5. `validiere` → `ValidierungError`, `pruefe_sperren` (Schritt 8) → `GesperrtError`, `stufe`
     (Schritt 9) → `BestaetigungNoetig` bzw. Antrag.
  6. Zuerst `halte_standards_fest` (D6, G-M4), dann je geänderten Abschnitt eine Version (Hash,
     Vorgänger, `datei_hash`, `vollstaendig`, `fehlend`).
  7. Journal: `schreibe(s, "einstellung_geaendert", "einstellung", abschnitt, vorher=<nur
     geänderte Felder als Punkt-Pfade>, nachher=<…>, grund=, bezug=f"einstellung:{abschnitt}:v{n}",
     person=)`. Das geschieht in derselben Transaktion (A40). Werte in Normalform (D9).
- [ ] **`pruefung/journal.py`** (D27, H2): `TEILSTAENDE` und `_pruefe_verlauf` mit
  fortgeschriebenem Stand je Schlüssel für diese Objekttypen. *Tests zuerst* in
  `tests/test_pruefung_journal.py`:
  - `::test_einstellung_zwei_felder_nacheinander_kein_befund` (v2 ändert
    `rechnung.zahlungsziel_tage`, v3 `name` → `accounti journal pruefen` ohne Befund)
  - `::test_einstellung_falsches_vorher_ist_befund` (v3 nennt für `rechnung.zahlungsziel_tage`
    ein anderes Vorher als v2 Nachher → Befund „verlauf“)
  - `::test_andere_objekttypen_unveraendert` (bestehende Verlaufstests bleiben grün)
- [ ] **Standards festhalten** (D6, G-M4; gehört zum Vorschlag D6): `pruefung.standards()` und
  `dienst.halte_standards_fest(s)` mit dem Journal `einstellung_standards`. Aufrufe in `speichere`
  (Punkt 6 oben) und in `accounti db upgrade` nach der Migration, je Gesellschaftsdatenbank. Die
  Serialisierung `golden_lader.serialisiere` (D20) zieht dafür nach `einstellungen/pruefung.py`,
  das Werkzeug importiert sie von dort. *Tests zuerst* in `tests/test_einstellungen_standards.py`:
  - `::test_erste_version_haelt_standards_fest` (Journal `einstellung_standards` je Abschnitt vor
    der ersten Version)
  - `::test_geaenderter_standard_nur_geaenderte_pfade` (Standard per `monkeypatch` geändert →
    `db upgrade` schreibt nur diesen Pfad alt → neu; zweiter Lauf schreibt nichts)
  - `::test_ohne_versionen_kein_eintrag`
  - `::test_journal_pruefen_mit_standard_eintraegen` (D27: kein Verlaufsbefund)
  - `::test_standards_unabhaengig_von_datei_und_datenbank` (andere Datei, andere Versionen →
    gleiche Standards)

  Dazu `setze_feld` (Pfad in Punktschreibweise, Listenindizes nicht erlaubt), `setze_abschnitt`,
  `uebernehme_aus_datei` (nur Abschnitte, die in der Datei stehen; Pflicht-Grund; `quelle =
  "datei_uebernahme"`) und `mandant.kontenrahmen` setzen → Fehler „gehört nach
  buchhaltung.kontenrahmen“.
  *Tests zuerst* in `tests/test_einstellungen_dienst.py`:
  - `::test_erste_version_ist_der_ganze_abschnitt` (AK76)
  - `::test_standards_werden_nicht_eingefroren` (D6; entscheidet der Nutzer für F1 wörtlich, wird
    daraus `::test_erste_version_friert_eigene_standards_ein` und
    `::test_abgeleitete_werte_nicht_eingefroren[auftraggeber|abschluss_konten|oss_konten]`)
  - `::test_version_und_journal_mit_person_vorher_nachher` (AK24 Fachkern:
    `mandant.rechnung.zahlungsziel_tage` 14 → 21; `lade_firma` unter neuem Stand → 21)
  - `::test_veraltete_version_konflikt_nichts_gespeichert` (AK28 Fachkern)
  - `::test_mehrere_abschnitte_eine_transaktion` (A45: `mandant` und `elster`, einer veraltet →
    keiner)
  - `::test_festgelegt_abgewiesen` (AK26)
  - `::test_betriebsfeld_abgewiesen_und_aus_datei` (AK26)
  - `::test_platzhalter_feld_abgewiesen`
  - `::test_eigener_platzhalter_abgewiesen` (H1: `setze_feld versand.betreff 'x ${HOME}'`,
    `setze_abschnitt versand` mit `smtp.passwort: ${ACCOUNTI_SCHLUESSEL}` und eigenem `smtp.host`,
    `belegkanaele.connectoren[].kopfzeilen` mit `${…}` → je `PlatzhalterError`; `uebernehmen`
    mit `${SMTP_PASS}` wie in der Datei → erlaubt, das Blatt steht nicht in der Version)
  - `::test_platzhalter_und_betriebsfelder_werden_nicht_gespeichert` (Datei mit
    `smtp.passwort: ${SMTP_PASS}` und `pruefung.archiv`, `uebernehmen` → beides fehlt in `daten`;
    danach Variable in der Datei umbenannt → `lade_versand` nimmt die neue; den Teil zu `pruefen`
    prüft Schritt 13; G-N3)
  - `::test_geheimnis_im_klartext_abgewiesen_auch_bei_uebernahme`
  - `::test_unbekanntes_feld_abgewiesen_mit_vorschlag` (`mandant.rechnung.zahlungziel_tage` →
    Fehler, Vorschlag `zahlungsziel_tage`; beim Übernehmen nur Hinweis; M4)
  - `::test_unbekanntes_konto_fehler_mit_pfad` (Form: `12A0`, `123`, `0000`; Personenkonto `10001`
    in `buchhaltung.bank_konto`; M10)
  - `::test_bankkonto_sachkonto_ohne_kontoart_bank`
  - `::test_skontokonto_aus_anderem_rahmen` (3736 unter SKR04)
  - `::test_auftraggeber_iban_ohne_bankkonto` (vier Fehler mit Abschnittspfad, AK77)
  - `::test_unpassender_standard_nur_warnung` (SKR04 ohne eigene Skontokonten: `buchhaltung`
    speicherbar, Warnung zu `skonto_erhalten`)
  - `::test_unvollstaendiger_mandant_speicherbar_rechnung_scheitert_mit_verweis` (AK77; ohne
    Steuernummer **und** ohne USt-IdNr. → `vollstaendig=false`, `fehlend` nennt beide; M5)
  - `::test_fremder_fehler_blockiert_nicht` (`zahlung` in der Datei ungültig, `mandant` ändern →
    Version, Hinweis zu `zahlung`; M3)
  - `::test_neuer_fehler_im_anderen_abschnitt_blockiert` (`mandant.bank.bic` auf `"FALSCH"`:
    `Firma` prüft die BIC nicht, `lade_zahlung` übernimmt sie in den Auftraggeber und scheitert
    neu → Fehler, keine Version; M3)
  - `::test_ohne_umgebungsvariable_speicherbar` (`versand.smtp.passwort: ${SMTP_PASS}` in der
    Datei, Variable nicht gesetzt, `versand.betreff` ändern → Version; M3)
  - `::test_gleiche_daten_keine_version`
  - `::test_uebernahme_bringt_kontenrahmen_nach_buchhaltung` (A53)
  - `::test_erste_mandant_version_zieht_kontenrahmen_um` (Datei mit `mandant.kontenrahmen: SKR04`,
    ohne `buchhaltung.kontenrahmen`, eine Buchung vorhanden; `setze_feld
    mandant.rechnung.zahlungsziel_tage 21` → zwei Versionen (`mandant` ohne `kontenrahmen`,
    `buchhaltung` mit SKR04), je ein Journaleintrag, Hinweis, keine `GesperrtError`;
    `lade_buchhaltung().kontenrahmen == "SKR04"`; G-M2)
  - `::test_erste_buchhaltung_version_nimmt_kontenrahmen_mit` (gleiche Datei, `setze_feld
    buchhaltung.bank_konto …` → Version enthält `kontenrahmen: SKR04`; G-M2)
  - `::test_umzug_bei_festgelegter_buchhaltung_fehler` (`festgelegt: [buchhaltung]` →
    `FestgelegtError` mit Verweis auf `buchhaltung.kontenrahmen` in der Datei, keine Version; G-M2)
  - `::test_unbekanntes_feld_der_datei_blockiert_nicht` (Datei-`mandant` mit `altes_feld: 1`,
    `setze_feld mandant.rechnung.zahlungsziel_tage 21` → Version ohne `altes_feld`, Hinweis; G-M2)
  - `::test_mandant_kontenrahmen_setzen_abgewiesen`
  - `::test_journal_ohne_geheimnisse`
  - `::test_rollback_nimmt_version_und_journal_zurueck`

### Schritt 8 — Sperren (A46 Teil 2) · P4b

- [ ] **`perioden.pruefe_sperren(s, pfad, alt, neu)`** über die wirksamen Lader-Ergebnisse vor und
  nach der Änderung (D15). Gesperrt sind:
  - `buchhaltung.kontenrahmen` (auch über den Fallback) und `datev.wirtschaftsjahr_beginn`, sobald
    es eine Buchung gibt (`exists(buchungssaetze)`)
  - `elster.voranmeldungszeitraum` und `dauerfristverlaengerung` für ein Jahr mit Freigabe oder
    erfolgreicher Echt-Übermittlung einer USt-VA bzw. eines Dauerfristantrags dieses Jahres oder
    mit Jahresabschluss bzw. Jahressperre
  - `mandant.oss` für ein Quartal mit festgeschriebenem Monat (Baustein 7), übermittelter USt-VA
    eines Monats darin oder Jahressperre
  - `abschluss.gewinnermittlung` für ein Wirtschaftsjahr mit Abschluss bzw. Jahressperre

  Die Meldung nennt Feld, Zeitraum und Grund („gesperrt – USt-VA Januar bis August 2026
  übermittelt“, Skizze 7).
  *Tests zuerst* in `tests/test_einstellungen_sperren.py`:
  - `::test_voranmeldungszeitraum_2026_gesperrt_nach_uebermittlung` (AK31, erster Punkt; Attrappe
    im Echtmodus über einen Test-Übermittler)
  - `::test_ab_2027_noch_aenderbar`
  - `::test_kontenrahmen_gesperrt_nach_erster_buchung` (AK31, zweiter Punkt)
  - `::test_kontenrahmen_ueber_mandant_fallback_gesperrt`
  - `::test_wirtschaftsjahr_gesperrt_nach_erster_buchung`
  - `::test_oss_quartal_mit_festgeschriebenem_monat`
  - `::test_gewinnermittlung_wj_mit_abschluss`
  - `::test_sperre_gilt_in_der_cli` (über `setzen`)

### Schritt 9 — Bestätigungsstufen und Anträge (E6, A39 Anträge) · P4b

- [ ] **`einstellungen/stufen.py`**: Anhang A als Daten. K2-Felder je Abschnitt, K3-Lockerungen mit
  Kontrolle und Recht. Vergleicher:
  - `aus` (an → aus)
  - `an` (aus → an)
  - `senken`, `anheben_oder_entfernen` (Zahl kleiner bzw. größer oder `None`)
  - `erweitern` (Liste wird Obermenge bzw. eine nicht leere Liste wird leer)

  `stufe(...)` liefert die höchste Stufe aller geänderten Felder. **K3 gilt nur, solange die
  Kontrolle im alten wirksamen Stand an ist.** Dazu die K2-Einträge aus D26 (Ziel-Host-Felder,
  entschieden). Die K3-Regeln, die an `elster.vier_augen` hängen (Schwelle senken,
  Prüfregeln abschalten), stehen schon hier in den Daten; sie greifen erst, wenn P4c das Feld
  bringt (bis dahin ist die Kontrolle nie an).
- [ ] **K2:** `speichere` mit `bestaetigung.k2 is False` und K2-Feld → `BestaetigungNoetig(K2)`.
  **K3:** Antrag nach D11 (Journal `einstellung_beantragt`, objekt_typ `einstellungsantrag`).
  `bestaetige_antrag`:
  - prüft Status `offen`, Ablauf (7 Tage → `abgelaufen`) und Basisversionen (→ `veraltet`)
  - rechnet `inhalt_hash` neu und vergleicht (D9, N14); die CLI zeigt vor der Code-Abfrage die
    Änderung (Feld alt → neu) und die ersten 12 Zeichen des Hashs
  - prüft, dass die Person nicht die antragstellende ist
  - prüft erneut Validierung und Sperren, schreibt dann die Versionen (`quelle="antrag"`,
    `antrag_id`)
  - Journal `einstellungsantrag_bestaetigt` mit beiden Personen

  `lehne_antrag_ab`: Die antragstellende Person zieht zurück, oder eine Person mit dem Recht der
  Kontrolle lehnt ab (D12, N7). Auch `uebernehme_aus_datei` und `setze_abschnitt` laufen durch
  `stufe`: Ein Datei-Stand mit `zahlung.vier_augen: false`, während die Datenbank `true` hat, wird
  ein Antrag (N8).
- [ ] **Kein Aussperren** (A125) gehört zu `elster.vier_augen` und kommt mit P4c (Schritt 11):
  `elster.vier_augen` aus → an mit eingerichteten Benutzern nur, wenn
  `berechtigte(Recht.STEUER_FREIGEBEN) ≥ 2` (aktive Benutzer mit dem Recht in der Gesellschaft,
  aus der Systemdatenbank). Sonst Feldfehler mit dem Text aus A125. `berechtigte` gibt `None`
  zurück, wenn keine Benutzer eingerichtet sind; dann ist Einschalten erlaubt (Anmeldename, wie
  `zahlung.vier_augen`). Die Schnittstelle `berechtigte` legt P4b schon an.

  *Tests zuerst*:
  - `tests/test_einstellungen_stufen.py::test_stufen_wie_anhang_a` (tabellengetrieben: jedes Feld aus
    Anhang A → K2 bzw. K3, alles andere K1)
  - `::test_k3_nur_solange_kontrolle_an`
  - `::test_hoechste_stufe_gewinnt`
  - `::test_ziel_host_ist_k2` (D26, tabellengetrieben: `versand.smtp.host|port|verschluesselung`,
    `belegkanaele.email[].host|port|verschluesselung`,
    `belegkanaele.connectoren[].basis_url|erlaubte_hosts|kopfzeilen`, `llm.provider|model` → K2;
    `smtp.benutzer`, `email[].benutzer` → K1)
  - `tests/test_einstellungen_antraege.py`:
    - `::test_k2_ohne_bestaetigung_scheitert`
    - `::test_zahlung_vier_augen_aus_wird_antrag` (AK30 Fachkern: keine Version, Antrag offen)
    - `::test_uebernahme_aus_datei_mit_lockerung_wird_antrag` (Datei `zahlung.vier_augen: false`,
      Datenbank `true` → Antrag, keine Version; N8)
    - `::test_bestaetigung_durch_zweite_person_mit_zahlung_freigeben`
    - `::test_selbe_person_kann_nicht_bestaetigen`
    - `::test_antrag_inhalt_geaendert_wird_abgewiesen` (rohes `UPDATE` an `aenderungen` vorbei an
      der ORM-Sperre → `inhalt_hash` passt nicht → `AntragError`; N14)
    - `::test_ablehnen_antragsteller_oder_recht_der_kontrolle` (Antragsteller mit `VERWALTEN`
      zieht zurück; Dritter ohne `ZAHLUNG_FREIGEBEN` scheitert, mit kann ablehnen; N7)
    - `::test_antrag_laeuft_nach_7_tagen_ab`
    - `::test_veralteter_antrag_wird_abgewiesen`
    - `::test_ganze_aenderung_wird_ein_antrag` (D11)
    - `::test_freigeber_erweitern_hoechstbetrag_anheben_ersteller_an`
    - `::test_journal_fuer_antrag_bestaetigung_ablehnung`

  Die Tests zu `elster.vier_augen` (Schwelle senken, Prüfregeln erweitern, ausschalten,
  einschalten) stehen in Schritt 11 (P4c).

### Schritt 10 — Geheimnisse (E4, A48) · P4b

- [ ] **`setze_geheimnis`/`entferne_geheimnis`**: Chiffrat mit `verschluessele({"wert": …},
  schluessel, f"{kuerzel}:{name}")`. Erlaubte Namen stehen in `GEHEIMFELDER` mit Prüffunktion
  (URL-Form für den Webhook). Ohne `ACCOUNTI_SCHLUESSEL` folgt eine `TresorError`-Meldung für den
  Betreiber. Das Journal schreibt nur „Geheimnis `<name>` ersetzt/entfernt“, ohne Wert und ohne
  Chiffrat.
- [ ] **`leser.geheimnis(name)`** entschlüsselt aus dem Schnappschuss (D8). Verbrauchsstellen:
  - `VersandDienst` mit `passwort = smtp.passwort or geheimnis("versand.smtp.passwort")`
  - `LLMEngine` mit `api_key = llm.api_key or geheimnis("llm.api_key")`
  - Webhook-Kanal mit `url = webhook.url or geheimnis("aufgaben.benachrichtigung.webhook.url")`
    (dafür wird `WebhookEinstellungen.url` optional, die Meldung „…webhook.url fehlt“ bleibt)
  - `waehle_uebermittler`: PIN-Datei, sonst `geheimnis("elster.pin")`. Heute verlangt die
    Schleife über `("bibliothek", "zertifikat", "pin_datei")` die PIN-Datei (Prüfbefund N5).
    Künftig ist `pin_datei` keine Pflicht mehr. Ist sie gesetzt, gilt sie wie heute (fehlt die
    Datei, ist das ein Fehler, kein stiller Wechsel zum Geheimnis). Sonst gilt das Geheimnis.
    Fehlt beides: „ERiC nicht eingerichtet: elster.eric.pin_datei oder Geheimnis elster.pin
    fehlt“.

  *Tests zuerst* in `tests/test_einstellungen_geheimnisse.py` (AK32):
  - `::test_nur_chiffrat_in_der_datenbank` (Rohabfrage findet den Klartext nicht)
  - `::test_journal_ohne_wert`
  - `::test_protokoll_ohne_wert` (caplog über alle Wege)
  - `::test_zeigen_und_export_ohne_wert`
  - `::test_umgebungsvariable_geht_vor`
  - `::test_pin_datei_geht_vor`
  - `::test_ohne_pin_datei_mit_geheimnis_gibt_es_einen_uebermittler` (N5; ohne beides: Meldung
    nennt beide Wege)
  - `::test_versand_nutzt_geheimnis` (SMTP-Attrappe)
  - `::test_llm_nutzt_geheimnis`
  - `::test_webhook_url_als_geheimnis`
  - `::test_ohne_schluessel_meldung`
  - `::test_bezug_bindet_an_gesellschaft` (Chiffrat aus a in b eingespielt → `TresorError`)

### Schritt 11 — Vier-Augen für Steuermeldungen (A125) · P4c

> **PR P4c: Schritte 11, 14, 15** (D28), abzweigen nach dem Merge von P4b.

- [ ] **Feld und Einschalten:** `elster.vier_augen: bool = False` (A125), K2 beim Einschalten,
  K3 beim Ausschalten (Daten aus Schritt 9). Dazu „Kein Aussperren“ aus Schritt 9:
  `berechtigte(Recht.STEUER_FREIGEBEN) ≥ 2`, sonst Feldfehler mit dem Text aus A125.
- [ ] **`elster/freigabe.py`**:
  - `gib_frei(…, vier_augen)` und `speichere(…, vier_augen)` weisen eine zweite Freigabe
    derselben Person für denselben Hash ab („hat bereits freigegeben — eine zweite Person muss
    freigeben“).
  - `offene_freigabe(…, vier_augen)` verlangt zwei Personen (D19), sonst `FreigabeError("eine
    zweite Person muss freigeben")`.
  - Der Verbrauch über alle Freigaben gleichen Inhalts bis zur genutzten folgt D19, **auch ohne
    Schalter** (N15).
  - `stand_der_freigaben(...)` liefert die Daten für P2.
  - `freigegeben_von` der Übermittlung: „A und B“ (≤ 100 Zeichen).
- [ ] **Aufrufer**:
  - `elster/ustva.uebermittle(…, vier_augen=…)` und `elster/dauerfrist.gib_dauerfrist_frei`,
    `uebermittle_dauerfrist` (ebenso).
  - `befehle/ustva.py` (`freigeben`, `uebermitteln`, `dauerfrist --freigeben|--uebermitteln`):
    Person mit Benutzern ist der per Einmalcode bestätigte Benutzer, ohne Benutzer
    `betriebssystem_benutzer()`. Ein abweichendes `--von` ist mit `elster.vier_augen` ein Fehler
    wie bei `zahlung` (D13).
  - Nach der ersten Freigabe lautet die Ausgabe „Erste Freigabe von X — das Vier-Augen-Prinzip
    verlangt eine zweite Person“.
  - `api/seiten/freigaben._ustva_freigeben` übergibt `vier_augen` und zeigt die Meldung (Text in
    `i18n/en.yaml`).
  - `pruefung/verfahrensdoku.py` ergänzt die Zeile „Steuermeldungen: Vier-Augen-Prinzip ja/nein“
    neben der Zeile für Zahlungsläufe.

  *Tests zuerst* in `tests/test_elster_vier_augen.py` (AK100):
  - `::test_ohne_schalter_eine_freigabe_wie_bisher` (Golden)
  - `::test_erste_freigabe_abgabe_verweigert` (Test-Übermittler im Echtmodus → „eine zweite Person
    muss freigeben“)
  - `::test_selbe_person_nicht_zweimal`
  - `::test_von_zaehlt_nicht_als_person` (ohne Benutzer: `--von bob` als Anmeldename `alice` →
    Fehler; mit Benutzern zählt nur der per Code bestätigte)
  - `::test_zweite_person_dann_abgabe`
  - `::test_geaenderte_buchung_entwertet_erste_freigabe`
  - `::test_eine_abgabe_verbraucht_beide`
  - `::test_ausschalten_belebt_keine_alte_freigabe` (Paar abgegeben, Schalter per Antrag aus →
    keine erneute Abgabe ohne neue Freigabe; N15)
  - `::test_ohne_schalter_doppelte_freigabe_mit_verbraucht` (zwei Freigaben derselben Werte, eine
    Abgabe → keine zweite Abgabe ohne neue Freigabe; N15)
  - `::test_dauerfrist_freigeben_und_uebermitteln_ebenso`
  - `::test_web_meldung_erste_freigabe`
  - `::test_verfahrensdoku_nennt_den_schalter`

  Aus Schritt 9 hierher (`tests/test_einstellungen_antraege.py`, AK100):
  - `::test_auto_buchen_schwelle_senken_bei_elster_vier_augen`
  - `::test_pruefung_abgeschaltet_erweitern_bei_elster_vier_augen`
  - `::test_elster_vier_augen_aus_braucht_steuer_freigeben`
  - `::test_einschalten_mit_einem_berechtigten_fehler_mit_hinweis`
  - `::test_einschalten_ohne_benutzer_erlaubt`

  `tests/test_i18n_katalog.py` bleibt grün.

### Schritt 12 — CLI `accounti einstellungen` (A49) · P4b

- [ ] **`befehle/einstellungen.py`** (`NAME = "einstellungen"`; jede Option `--db` und `--config`
  wie `DB_OPTION`/`KONFIG_OPTION`):

  ```bash
  accounti einstellungen zeigen [ABSCHNITT] [--herkunft] [--json]
  accounti einstellungen setzen ZIEL [WERT] [--ab ZEITRAUM] [--datei TEIL.yaml] --grund "…"
  accounti einstellungen verlauf ABSCHNITT [--json]
  accounti einstellungen pruefen [--json]
  accounti einstellungen uebernehmen --aus-datei [ABSCHNITT …] --grund "…"
  accounti einstellungen export [--ziel DATEI]
  accounti einstellungen geheimnis setzen NAME            # Wert nur über stdin
  accounti einstellungen geheimnis entfernen NAME --grund "…"
  accounti einstellungen geheimnis liste
  accounti einstellungen antraege [--alle]
  accounti einstellungen antraege bestaetigen ID
  accounti einstellungen antraege ablehnen ID --grund "…"
  ```

  - **`setzen`:** `ZIEL` mit Punkt ist ein Feld (`WERT` als Skalar, D17). `ZIEL` ohne Punkt mit
    `--datei` ist ein ganzer Abschnitt (`parse_text`, Grenze 64 KB). `--ab` gilt für
    Periodenfelder. `--grund` ist Pflicht.
  - **Person und Rechte** nach D12: `befehlsrecht_oder_ende(db, config, Recht.VERWALTEN,
    aktuelle_person())` → `Bestaetigung(k2=True, verfahren="einmalcode")`, ohne Benutzer
    `verfahren="ohne_benutzer"`. `berechtigte` zählt über `systemsitzung`.
  - **Ergebnis:**
    - Version: „mandant: Version 5 gespeichert“.
    - Antrag: „Antrag 3 angelegt — bestätigen: accounti einstellungen antraege bestaetigen 3
      (eine zweite Person mit Recht „Zahlungen freigeben“)“, Exit 0, `--json` mit `antrag`.
    - Fachfehler: Meldung, Exit 1.
  - **`zeigen`:** YAML des wirksamen Abschnitts. Geheimfelder erscheinen als „«gesetzt am
    21.10.2026 von jan»“, „«aus Umgebungsvariable SMTP_PASS (gesetzt)»“ oder „«nicht
    gesetzt»“. Mit `--herkunft` steht über jedem Abschnitt eine Zeile wie in Skizze 7.
  - **`geheimnis setzen`:** Ist stdin kein Terminal, wird stdin gelesen (genau ein abschließender
    Zeilenumbruch fällt weg). Sonst folgt eine verdeckte Eingabe mit Wiederholung. Es gibt
    **keine** Option für den Wert.
  - **`pruefen`:** kommt mit Schritt 13 (braucht `pruefe_alles`, Prüfbefund M9). Befunde nach
    Stufe. Exit 1 bei mindestens einem Fehler (Validierung, gebrochene Hash-Kette, Version ohne
    Journaleintrag, Platzhalter in der Datenbank), Exit 0 bei Warnungen und Hinweisen.
  - **`export`:** kommt mit Schritt 14 (P4c).
  - **`antraege`:** zeigt je Antrag die Änderung (Feld alt → neu) und den Anfang von
    `inhalt_hash`. `bestaetigen` zeigt beides vor der Code-Abfrage (N14). `ablehnen` bestimmt das
    Recht aus Antrag und Person (D12, N7).

  *Tests zuerst* in `tests/test_cli_einstellungen.py`:
  - `::test_setzen_mit_grund_neue_version` (AK24 CLI-Teil: danach `zeigen` und `lade_firma` mit
    21; Journal mit Person)
  - `::test_setzen_ohne_grund_fehler`
  - `::test_k2_ohne_code_scheitert` (Benutzer eingerichtet, falscher bzw. fehlender
    `ACCOUNTI_EINMALCODE` → Exit 1, keine Version; AK79)
  - `::test_k3_erzeugt_antrag_statt_version` (AK79, AK30 CLI-Teil)
  - `::test_antrag_bestaetigen_zweite_person` (andere `ACCOUNTI_BENUTZER` + Code mit Rolle
    `freigeber`)
  - `::test_antrag_selbst_bestaetigen_abgewiesen`
  - `::test_festgelegt_abgewiesen` (AK79)
  - `::test_wert_als_skalar_text_vorrang` (`buchhaltung.bank_konto 1200` bleibt `"1200"`)
  - `::test_liste_nur_ueber_datei`
  - `::test_ab_fuer_periodenwert`
  - `::test_datei_mit_anker_abgewiesen`
  - `::test_geheimnis_nur_von_stdin` (Befehl hat außer `NAME`, `--db`, `--config` keinen Parameter;
    Wert aus stdin, nicht in der Ausgabe)
  - `::test_eigener_platzhalter_abgewiesen` (`setzen versand.betreff 'x ${HOME}'` → Exit 1, keine
    Version; H1)
  - `::test_antrag_ablehnen_rechte` (N7)
  - `::test_uebernehmen_mit_grund`
  - `::test_ohne_benutzer_wie_bisher`
  - `::test_mit_gesellschaft_eigene_datenbank`
  - `::test_verlauf_alt_neu_ohne_geheimnis`
  - `::test_hilfe_ohne_gesellschaft` (Paket A: Hilfe ohne `-g`)

### Schritt 13 — Herkunft, Abweichung, `pruefen` (A43 Fachkern, A53, A122) · P4b

- [ ] **`pruefung.herkunft`** (D9, D23; auf `leser.herkunft_roh`) und **`pruefung.pruefe_alles`**,
  dazu der CLI-Befehl `einstellungen pruefen` (aus Schritt 12 hierher, M9). Die Befunde sind:
  - Validierungsfehler je wirksamem Abschnitt (Datei-Werte nach D16 als Warnung)
  - gebrochene Hash-Kette bzw. Lücke in den Versionen (Fehler)
  - Version ohne Journaleintrag (Fehler, über `bezug`)
  - Blatt mit `${` in einer Version an einem Pfad, an dem die Datei keinen Platzhalter hat
    (Fehler, D7/H1). Hat die Datei dort einen, auch mit anderem Namen, gilt er, und es gibt
    keinen Befund (G-N3). accounti selbst speichert keine Platzhalter.
  - Standards weichen vom letzten Eintrag `einstellung_standards` ab (Warnung „nach dem Update
    `accounti db upgrade` ausführen“, D6, G-M4)
  - unbekanntes Feld in der Datei (Warnung, D16/M4)
  - unpassender Standard, z. B. SKR03-Skontokonten unter SKR04 (Warnung, D16)
  - Name der Registry ≠ `mandant.name` (Hinweis, D21)
  - `vollstaendig=false` mit fehlenden Feldern (Warnung)
  - Datei ≠ Datenbank (Hinweis) bzw. Datei nach der letzten Version geändert (Warnung)
  - `kontenrahmen` nur unter `mandant` (Warnung, N1, A53)
  - `mandant.steuernummer` ≠ `elster.steuernummer` (Warnung, A122)
  - unbekannter Abschnitt in der Datei (Warnung)
  - Festlegung mit vorhandenen Datenbank-Versionen („Versionen werden nicht verwendet“, Hinweis)
  - Geheimnis lässt sich nicht entschlüsseln (Warnung, D22)
  - Empfehlung „Vier-Augen für Steuermeldungen einschalten?“, wenn mindestens zwei Benutzer
    `STEUER_FREIGEBEN` haben und der Schalter aus ist (Hinweis, A125; kommt mit dem Feld in P4c)
  - `llm`-Werte, die erst ab P4 wirken (Hinweis, D18)

  Dazu `pruefung.abweichungen(pfad)` für `serve` und der Aufruf in `api/server.py` (aus Schritt 3
  hierher, G-M3): nach `pruefe_schema` je Gesellschaft eine Warnzeile ohne Werte (A43, D23), dazu
  die Warnung zu geänderten Standards (D6).
  *Tests zuerst* in `tests/test_einstellungen_pruefung.py` (`::test_empfehlung_vier_augen` erst
  in P4c):
  - `::test_platzhalter_in_version_ist_fehler` (H1; rohes `INSERT` mit `${HOME}` an einem Pfad ohne
    Platzhalter der Datei → Fehler)
  - `::test_umbenannte_variable_kein_fehler` (Version ohne Platzhalter, Datei von `${SMTP_PASS}` auf
    `${SMTP_PASSWORT}` umgestellt → kein Befund, Exit 0; G-N3)
  - `::test_standards_nach_update_warnung` (D6, G-M4)
  - `tests/test_api_einstellungsstand.py::test_serve_meldet_abweichung_ohne_werte` (caplog:
    Abschnittsname ja, IBAN nein; aus Schritt 3 hierher, G-M3)
  - `tests/test_cli_einstellungen.py::test_pruefen_exit_code` (gebrochene Kette → 1; nur
    Abweichung → 0; aus Schritt 12 hierher, M9)
  - `::test_abweichung_sichtbar_und_uebernehmen_erzeugt_version` (AK27 Fachkern + CLI)
  - `::test_datei_nach_version_geaendert_ist_warnung`
  - `::test_fehlender_abschnitt_keine_abweichung`
  - `::test_kette_gebrochen_fehler` (rohes `INSERT` mit falschem Hash; unter SQLite vorbei am
    `UPDATE`-Trigger)
  - `::test_version_ohne_journal_fehler`
  - `::test_kontenrahmen_nur_unter_mandant_warnt` (AK80)
  - `::test_zwei_steuernummern_warnung` (AK81 P4-Teil)
  - `::test_vollstaendig_false_nennt_felder`
  - `::test_empfehlung_vier_augen`
  - `::test_herkunft_jeder_art`

### Schritt 14 — Export und Rundlauf (A50) · P4c

- [ ] **`einstellungen/export.py`**: vollständige YAML aller wirksamen Abschnitte in der
  Reihenfolge der Beispielkonfiguration. Unbekannte Datei-Abschnitte werden übernommen, die
  Betriebsabschnitte aus der Datei ebenfalls, damit die Ausgabe eine vollständige Datei ist.
  - Je Abschnitt steht ein Kommentar mit der Herkunft („# elster: Datenbank, Version 4 vom
    21.10.2026, jan“).
  - Geheimfelder: der `${VAR}` der Datei, sonst `${ACCOUNTI_GEHEIMNIS_<NAME>}` mit Kommentar
    „Wert als Umgebungsvariable bereitstellen“.
  - `elster.pin` steht als Kommentar mit dem Weg über `elster pin`.
  - Datenbank-Adressen aus `database` und `gesellschaften[].datenbank` gehen durch
    `ohne_passwort` (Passwort als `***`, Kommentar „Passwort ergänzen oder `${VAR}`“); ein `${…}`
    der Datei bleibt stehen (Prüfbefund N12).
  - Ein Kopfkommentar erklärt `einstellungen: {quelle: datei}`.
  - Geschrieben wird mit `--ziel` als neue Datei (keine Überschreibung ohne `--ueberschreiben`),
    sonst auf stdout.

  *Tests zuerst* in `tests/test_einstellungen_export.py`:
  - `::test_rundlauf_gleiche_wirksame_werte` (AK33: Versionen in drei Abschnitten, Export,
    `einstellungen: {quelle: datei}` ergänzt, gleiche Lader-Ergebnisse; Geheimnisse mit gesetzter
    Umgebungsvariable gleich)
  - `::test_geheimnis_als_platzhalter` (AK32)
  - `::test_datenbank_passwort_geschwaerzt` (`database: postgresql+psycopg://u:geheim@h/db` →
    `geheim` steht nicht im Export; N12)
  - `::test_export_ist_gueltiges_yaml_ohne_anker`
  - `::test_herkunft_als_kommentar`
  - `::test_ziel_wird_nicht_ueberschrieben`

### Schritt 15 — Verfahrensdokumentation zum Stichtag (A51) · P4c

- [ ] **`accounti verfahrensdoku --stichtag JJJJ-MM-TT`** (Standard heute): Die Option füllt den
  vorhandenen Parameter `stand: date` von `erzeuge` (Prüfbefund N2; kein neuer Parameter).
  `erzeuge` arbeitet unter `mit_quelle(DatenbankQuelle(db_url oder session.get_bind()),
  stichtag=Ende des Tages von stand)`, damit der Stichtag auch ohne `db_url` greift.
  - Neu ist der Anhang „Änderungen der Einstellungen“ aus `verlauf(s, bis=stichtag)`: Datum,
    Abschnitt, Feld, alt → neu (ohne Geheimnisse), Person, Grund, Quelle, Antrag. Die Einträge
    `einstellung_standards` bis zum Stichtag stehen darin als „Standard (Programmstand)“ (D6,
    G-M4).
  - Die Zeile „Einstellungen: Quelle je Abschnitt“ nennt Datei bzw. Datenbank vN.
  - Vor der ersten Version steht ein Hinweis, dass die Datei keinen eigenen Verlauf hat (Grenzen).
  - Liegt der Stichtag vor heute, sagt der Kopf: „Einstellungen zum Stichtag; Benutzer, Rollen
    und Mengenangaben nach heutigem Stand der Datenbank“. Das Dokument mischt sonst unbemerkt
    zwei Stände.
  - Die Fassung (SHA-256) im Journal enthält den Stichtag.

  *Tests zuerst* in `tests/test_pruefung_verfahrensdoku.py`:
  - `::test_stichtag_vor_aenderung_alter_wert`
  - `::test_stichtag_nach_aenderung_neuer_wert`
  - `::test_anhang_aenderungen_ohne_geheimnisse` (AK34, beide mit Anhang)
  - `::test_anhang_nennt_standardaenderung` (Standard-Eintrag vor dem Stichtag erscheint, danach
    nicht; D6, G-M4)
  - `::test_quelle_je_abschnitt`
  - `::test_stichtag_ohne_db_url_aus_der_sitzung` (N2)
  - `::test_kopf_kennzeichnet_gemischten_stand` (N2)
  - `::test_vier_augen_zeilen` (AK100)

### Schritt 16 — Sicherung und Aufbewahrung (A52) · P4b

- [ ] **Sicherung**: Die neuen Tabellen laufen über `Base.metadata` automatisch mit, es gibt keine
  Ausnahmeliste. **Aufbewahrung**: `Unterlage.ORGANISATION` (10 Jahre, `_NR1`) und `BESTAND` um
  `einstellungen` (`erstellt_am`) und `einstellungsantraege` (`erstellt_am`) ergänzt. Die Zeile
  sagt „wird nicht ausgesondert (Verlauf der Verfahrensdokumentation)“ statt eines Datums.
  `geheimnisse` sind keine Unterlage und erscheinen nicht im Bericht.
  *Tests zuerst*:
  - `tests/test_betrieb_sicherung.py::test_einstellungen_antraege_geheimnisse_im_rundlauf` (AK35:
    Wiederherstellung in eine leere Umgebung, Hash-Kette gültig, `geheimnis()` mit demselben
    Schlüssel entschlüsselbar, mit anderem Schlüssel `TresorError`)
  - `::test_..._postgresql` (`@mit_postgresql`; Trigger blockieren das Einspielen nicht)
  - `tests/test_betrieb_aufbewahrung.py::test_einstellungsversionen_als_organisationsunterlagen`

### Schritt 17 — Abschluss · je PR

- [ ] **Beispielkonfiguration und Doku** nach „Doku-Bausteine“ (README, CHANGELOG, Bauplan,
  Architektur, Betrieb, `config/accounti.example.yaml`), je PR der dort vermerkte Teil (D28).
  `i18n/en.yaml` bekommt die neuen Web-Texte (Schritt 11, P4c).
- [ ] **Protokoll ohne Personenbezug** (A116, P4b; P4c ergänzt die Vier-Augen-Wege):
  `tests/test_betrieb_protokoll.py::test_einstellungen_ohne_werte_im_protokoll`. Über `setzen`,
  `uebernehmen`, `geheimnis setzen`, Antrag, `serve`-Start mit Abweichung und Fehlerwege prüft
  er, dass IBAN, Steuernummer, USt-IdNr., E-Mail, Namen und Geheimnis nicht in der
  Protokollausgabe stehen.
- [ ] **Gleichlauf** (A113, Vorgriff P5; P4b): `tests/test_einstellungen_gleichlauf.py::test_cli_und_dienst_gleicher_zustand`.
  `setzen` per CLI und `dienst.setze_feld` mit denselben Daten ergeben dieselben Daten,
  denselben Hash ohne Zeit und Person und denselben Journal-Vorgang.
- [ ] **Prüfläufe**: `ruff check`, `ruff format --check`, `mypy src/`, `pytest` (ohne
  `last`-Marker); PostgreSQL läuft ab P4a im CI-Job `postgresql` mit (Schritt 1, M11).
- [ ] **Handprobe Docker (CLI-Teil von AK24, P4b)**: `docker compose run --rm app einstellungen setzen
  mandant.rechnung.zahlungsziel_tage 21 --grund "Probe"` mit `config/:ro` und `read_only: true`,
  dann `docker compose restart app` und `docker compose run --rm app einstellungen zeigen mandant`
  → 21 (Protokoll im PR). Dazu einmal ohne `config/accounti.yaml` im Container (nur
  Datenbank-Versionen von `mandant` und `buchhaltung`): `einstellungen zeigen mandant` zeigt die
  Datenbank-Werte (D25). Die Browser-Probe folgt in P5.
- [ ] **Gegnerische Prüfung** (Technik und Fachlich) je PR wie in 10a/10b; Befunde im Plan
  nachtragen.

---

## Dateien

| Datei | Art | Inhalt |
|-------|-----|--------|
| `src/accounti/einstellungen/__init__.py` | neu | öffentliche API (`lies_abschnitt`, `herkunft`, `geheimnis`, `mit_quelle`, …) |
| `src/accounti/einstellungen/leser.py` | neu | Datei-Cache (Inhalts-Hash), Stand, Kontextvariable, `DatenbankQuelle`, Schnappschuss, Vorrang, `${…}` nur aus der Datei, fehlende Datei, Überlagerung, Prüfmodus, `herkunft_roh`, `parse_text` |
| `src/accounti/einstellungen/inventar.py` | neu | Abschnitte, Betriebsfelder samt Markierung, Geheim-, Perioden-, Konto-, Meldefelder, `MODELL`, `LADER` (mittelbar) |
| `src/accounti/einstellungen/perioden.py` | neu | Periodenwerte, Sperren |
| `src/accounti/einstellungen/stufen.py` | neu | K1/K2/K3 nach Anhang A, Ziel-Host-Felder (D26) |
| `src/accounti/einstellungen/pruefung.py` | neu | Validierung über Lader mit Zurechnung, unbekannte Felder, Querprüfungen, `herkunft`, `pruefe_alles`, `abweichungen` |
| `src/accounti/einstellungen/dienst.py` | neu | Schreiben, Anträge, Geheimnisse |
| `src/accounti/einstellungen/verlauf.py` | neu | Versionsdiffs |
| `src/accounti/einstellungen/export.py` | neu | YAML-Export |
| `src/accounti/db/tabellen_einstellungen.py`, `db/repo_einstellungen.py`, `db/schutz.py` | neu | Tabellen, Repository, Trigger SQLite/PG |
| `src/accounti/models/einstellungen.py` | neu | Version, Antrag, GeheimnisInfo, Herkunft, Befund, Ergebnis |
| `src/accounti/befehle/einstellungen.py` | neu | CLI |
| `src/accounti/api/einstellungsstand.py` | neu | ASGI-Middleware |
| `alembic/versions/<rev>_add_einstellungen.py` | neu | Migration |
| `.github/workflows/ci.yaml` | geändert | Job `postgresql` mit `services: postgres` (P4a, M11) |
| `src/accounti/db/__init__.py` | geändert | `GESCHUETZT` + `einstellungen`, `SCHEMA_STAND` |
| `src/accounti/pruefung/journal.py` | geändert | `TEILSTAENDE`, `_pruefe_verlauf` mit fortgeschriebenem Stand (D27) |
| `src/accounti/cli.py` (`db upgrade`, Z. 2789) | geändert | `halte_standards_fest` nach der Migration (D6, P4b) |
| `src/accounti/betrieb/cli.py`, `betrieb/kontext.py`, `befehle/__init__.py` | geändert | Stand im Callback, `binde_datenbank_parameter`, `STANDARD_DB` |
| `src/accounti/befehle/{fristen,pruefen,kanaele,elster}.py` | geändert | `--db` (D3, M1) |
| `src/accounti/api/app.py`, `api/sitzung.py`, `api/rest/__init__.py`, `api/dienste.py`, `api/server.py`, `api/seiten/freigaben.py` | geändert | Bindung, Name ohne Registry beim Start, Startmeldung, Vier-Augen-Meldung |
| `src/accounti/konfiguration.py` | geändert | Lader über `lies_abschnitt` ohne `is_file`, `rechtsform`, `kennfarbe`, `sachkonten_laenge`, `pflicht_fehlt`, `oss_am`, Verweis in Fehlern |
| `src/accounti/abschluss/konfiguration.py`, `abschluss/kontenrahmen.py` (`form_fehler`) | geändert | Leser, `TagMonat`, `gewinnermittlung_fuer`, `gewinnermittlung_angegeben(pfad, wj)` |
| `src/accounti/elster/konfiguration.py`, `elster/freigabe.py`, `elster/ustva.py`, `elster/dauerfrist.py`, `elster/zahllast.py`, `elster/uebermittlung.py` | geändert | Leser, Periodenwerte, `vier_augen`, PIN aus Geheimnis |
| `src/accounti/{aufgaben,belege/kanaele,pruefung,anlagen,bank,zahlung,mahnwesen,integrationen}/…einstellungen\|konfiguration.py`, `erechnung/versand.py`, `export/datev_stammdaten.py`, `auth/einstellungen.py`, `api/einstellungen.py`, `betrieb/gesellschaften.py` | geändert | Leser; `_ersetze_variablen` und `loese_auf` fragen den Prüfmodus |
| `src/accounti/klassifikation/{llm,engine}.py`, `buchung/kontierung.py`, `cli.py` (`classify`, `bank lauf`, `rechnung`), `api/rest/laeufe.py` | geändert | `lade_llm`, Schwelle, Modell, `api_key` |
| `src/accounti/befehle/{ustva,fristen,gesellschaft,betrieb,verfahrensdoku,abschluss}.py`, `steuer/fristen.py`, `erechnung/erzeuger/aufbau.py`, `integrationen/buchung.py`, `opos/verbuchung.py`, `abschluss/{euer,vortrag,abgrenzung,pruefungen}.py`, `db/tabellen_pruefung.py`, `cli.py` (`gewinnermittlung_angegeben`) | geändert | Periodenwerte, Vier-Augen, WJ-Beginn, Gesellschaften je eigener Datenbank |
| `src/accounti/pruefung/verfahrensdoku.py`, `betrieb/aufbewahrung.py` | geändert | Stichtag, Anhang, Organisationsunterlagen |
| `src/accounti/i18n/en.yaml` | geändert | Web-Texte Vier-Augen |
| `config/accounti.example.yaml`, `README.md`, `CHANGELOG.md`, `docs/{bauplan,architektur,betrieb}.md` | geändert | Doku-Bausteine |
| `tests/…` | neu/geändert | siehe Aufgaben; Golden-Daten in `tests/daten/lader_golden/` |

---

## Anforderungen und Akzeptanz → Schritt → Test

| Anf. | Inhalt | Schritt | Test |
|------|--------|---------|------|
| A39 | Tabelle `einstellungen`, nur anfügend, Hash-Kette, Anträge | 1, 9 | `test_einstellungen_tabellen.py::*`, `test_migration_einstellungen.py::*`, `test_einstellungen_antraege.py::*` |
| A40 | Journal `einstellung_geaendert` mit geänderten Feldern; `journal pruefen` bleibt ohne Fehlbefund (D27) | 7 | `test_einstellungen_dienst.py::test_version_und_journal_mit_person_vorher_nachher`, `::test_journal_ohne_geheimnisse`, `test_pruefung_journal.py::test_einstellung_zwei_felder_nacheinander_kein_befund`, `::test_einstellung_falsches_vorher_ist_befund` |
| A41 | Wirksamer Wert nach E2, gleicher Modelltyp, auch ohne Datei (D25) | 2, 4 | `test_einstellungen_leser.py::test_datenbank_schlaegt_datei` …, `::test_fehlende_datei_ist_leer_versionen_gelten`, `test_lader_umbau.py::test_ohne_datei_gelten_versionen[*]`, `test_lader_golden.py` |
| A42 | Betriebswerte nur aus Datei/Umgebung | 2, 7 | `test_einstellungen_leser.py::test_betriebsfeld_kommt_aus_der_datei`, `::test_betriebsabschnitt_nie_aus_der_datenbank`, `test_einstellungen_dienst.py::test_betriebsfeld_abgewiesen_und_aus_datei`, `test_einstellungen_inventar.py::test_betriebsfelder_markiert_und_gelistet` |
| A42 (Umgebung) | `${…}` nur aus der Datei, nie aus der Datenbank aufgelöst (D7, H1) | 2, 4, 7, 13 | `test_einstellungen_leser.py::test_platzhalter_aus_der_datenbank_wird_nicht_weitergegeben`, `test_lader_umbau.py::test_platzhalter_der_datenbank_wird_nie_aufgeloest`, `test_einstellungen_dienst.py::test_eigener_platzhalter_abgewiesen`, `test_einstellungen_pruefung.py::test_platzhalter_in_version_ist_fehler` |
| A43 | Herkunft, Abweichung, Datei-Stand übernehmen, Meldung beim Start (Fachkern) | 13 | `test_einstellungen_pruefung.py::test_abweichung_sichtbar_und_uebernehmen_erzeugt_version`, `::test_herkunft_jeder_art`, `test_api_einstellungsstand.py::test_serve_meldet_abweichung_ohne_werte` |
| A44 | Validierung, fehlende Modelle, `MM-TT`, Querprüfungen, Unvollständiges, unbekannte Felder, Zurechnung | 5, 7 | `test_einstellungen_dienst.py::test_unbekanntes_konto_*` … `::test_unvollstaendiger_mandant_*`, `::test_unbekanntes_feld_abgewiesen_mit_vorschlag`, `::test_fremder_fehler_blockiert_nicht`, `::test_neuer_fehler_im_anderen_abschnitt_blockiert`, `::test_ohne_umgebungsvariable_speicherbar`, `test_konfiguration.py::test_wirtschaftsjahr_tag_monat`, `::test_pflichten_fehlerart_pflicht_fehlt_text_gleich`, `test_llm_einstellungen.py::*` |
| A45 | Gleichzeitigkeit über Versionen, alle Abschnitte in einer Transaktion | 7 | `test_einstellungen_dienst.py::test_veraltete_version_konflikt_nichts_gespeichert`, `::test_mehrere_abschnitte_eine_transaktion` |
| A46 | Periodenwerte und Sperren | 6, 8 | `test_einstellungen_perioden.py::*` (mit `::test_kein_zugriff_auf_rohfelder`), `test_einstellungen_sperren.py::*`, `test_elster_ustva.py::test_dezember_2026_monat_trotz_quartal_2027`, `test_elster_konfiguration.py::test_lade_oss_mit_zuordnung_je_zeitraum`, `test_abschluss_konfiguration.py::test_gewinnermittlung_angegeben_mit_zuordnung` |
| A47 | Abschnittsleser, Kontextvariable, AST-Test, Datenbank des Befehls | 2, 3, 4 | `test_lader_umbau.py::test_safe_load_nur_in_der_positivliste`, `::test_datenbankwert_wirkt[*]`, `::test_lader_lesen_was_registriert_ist[*]`, `test_cli_einstellungsquelle.py::*` (mit `::test_jeder_befehl_mit_config_hat_db`, `::test_gesellschaft_liste_zeigt_kontenrahmen_je_datenbank`, `::test_fremder_registry_pfad_fail_closed`), `test_api_einstellungsstand.py::*` |
| A48 | Geheimnisse | 10 | `test_einstellungen_geheimnisse.py::*` |
| A49 | CLI | 12 | `test_cli_einstellungen.py::*` |
| A50 | Export als Rückweg | 14 | `test_einstellungen_export.py::*` |
| A51 | Verfahrensdoku zum Stichtag mit Änderungsanhang; Standards bestimmbar (D6) | 7, 15 | `test_pruefung_verfahrensdoku.py::test_stichtag_*`, `::test_anhang_aenderungen_ohne_geheimnisse`, `::test_anhang_nennt_standardaenderung`, `test_einstellungen_standards.py::*` |
| A52 | Sicherung, Aufbewahrung, Hinweis zum Schlüssel | 16, 17 | `test_betrieb_sicherung.py::test_einstellungen_antraege_geheimnisse_im_rundlauf`, `test_betrieb_aufbewahrung.py::test_einstellungsversionen_als_organisationsunterlagen`, Doku `betrieb.md` |
| A53 | Übergang ohne automatische Übernahme, N1 | 0, 7, 13 | `test_lader_golden.py`, `test_einstellungen_dienst.py::test_uebernahme_bringt_kontenrahmen_nach_buchhaltung`, `test_einstellungen_pruefung.py::test_kontenrahmen_nur_unter_mandant_warnt` |
| A54 | Ein Stand je Anfrage bzw. Befehl | 2, 3 | `test_einstellungen_leser.py::test_schnappschuss_bleibt_in_der_anfrage`, `test_cli_einstellungsquelle.py::test_zwei_lader_ein_stand`, `test_api_einstellungsstand.py::test_schnappschuss_je_anfrage` |
| A122 | Eine Steuernummer | 13 | `test_einstellungen_pruefung.py::test_zwei_steuernummern_warnung` (Seite: P5) |
| A124 | Neue und geänderte Felder, abwärtskompatibel | 5, 6 | `test_einstellungen_inventar.py::test_neue_felder_abwaertskompatibel`, `test_konfiguration.py::test_rechtsform_und_kennfarbe`, `test_einstellungen_perioden.py::test_einzelwert_gilt_immer` |
| A125 | Vier-Augen für Steuermeldungen | 11, 15 (P4c) | `test_elster_vier_augen.py::*`, `test_einstellungen_antraege.py::test_elster_vier_augen_aus_*`, `::test_einschalten_*` |
| A113 | Gleichlauf | 17 | `test_einstellungen_gleichlauf.py` |
| A116 | Protokoll ohne Personenbezug | 17 | `test_betrieb_protokoll.py::test_einstellungen_ohne_werte_im_protokoll` |
| A117 | Abhängigkeiten | — | keine neue |
| A118 | Migration, ein Kopf, `SCHEMA_STAND`; Tests an der eigenen Revision (G-M1) | 1 | `test_migration_einstellungen.py::*`, `test_db_upgrade.py`, umgestellte Kopf-Tests (Liste im PR) |
| A119 | Zweisprachigkeit | 11 | `test_i18n_katalog.py` |

| AK | Prüft | Test |
|----|-------|------|
| AK24 (CLI-Teil) | Version + Journal + `zeigen` + `lade_firma` | `test_cli_einstellungen.py::test_setzen_mit_grund_neue_version`; Handprobe Docker (Schritt 17) |
| AK25 | `UPDATE`/`DELETE` scheitern, ORM + Trigger, SQLite + PG | `test_einstellungen_tabellen.py::test_version_nur_anfuegen_orm`, `::test_version_nur_anfuegen_rohes_sql_sqlite`, `::test_trigger_postgresql`, `::test_trigger_nach_init_db_postgresql` (PostgreSQL im CI-Job `postgresql`, M11) |
| AK26 (Fachkern) | festgelegt abgewiesen, Betriebsfelder aus der Datei | `test_einstellungen_dienst.py::test_festgelegt_abgewiesen`, `::test_betriebsfeld_abgewiesen_und_aus_datei` |
| AK27 (Fachkern, CLI) | Abweichung sichtbar, Übernahme mit Grund | `test_einstellungen_pruefung.py::test_abweichung_sichtbar_und_uebernehmen_erzeugt_version`, `test_cli_einstellungen.py::test_uebernehmen_mit_grund` |
| AK28 (Fachkern) | veraltete Version, nichts gespeichert | `test_einstellungen_dienst.py::test_veraltete_version_konflikt_nichts_gespeichert` |
| AK30 (CLI-Teil) | Antrag, zweite Person, nicht selbst | `test_cli_einstellungen.py::test_k3_erzeugt_antrag_statt_version`, `::test_antrag_bestaetigen_zweite_person`, `::test_antrag_selbst_bestaetigen_abgewiesen` |
| AK31 | Sperren, Periodenwert Dezember | `test_einstellungen_sperren.py::test_voranmeldungszeitraum_2026_gesperrt_nach_uebermittlung`, `::test_kontenrahmen_gesperrt_nach_erster_buchung`, `test_elster_ustva.py::test_dezember_2026_monat_trotz_quartal_2027` |
| AK32 | Geheimnis nie im Klartext, Platzhalter im Export | `test_einstellungen_geheimnisse.py::*`, `test_einstellungen_export.py::test_geheimnis_als_platzhalter` |
| AK33 | Rundlauf | `test_einstellungen_export.py::test_rundlauf_gleiche_wirksame_werte` |
| AK34 | Verfahrensdoku zum Stichtag | `test_pruefung_verfahrensdoku.py::test_stichtag_vor_aenderung_alter_wert`, `::test_stichtag_nach_aenderung_neuer_wert` |
| AK35 | Sicherung und Wiederherstellung | `test_betrieb_sicherung.py::test_einstellungen_antraege_geheimnisse_im_rundlauf` |
| AK76 | Vorrang-Matrix, erste Version vollständig, Stand je Anfrage | `test_einstellungen_leser.py::test_umgebung_schlaegt_alles`, `::test_festgelegter_abschnitt_nimmt_die_datei_trotz_version`, `::test_datenbank_schlaegt_datei`, `::test_ohne_beides_gilt_der_standard`, `test_einstellungen_dienst.py::test_erste_version_ist_der_ganze_abschnitt`, `test_api_einstellungsstand.py::test_schnappschuss_je_anfrage` |
| AK77 | Querprüfungen, unvollständiger `mandant` | `test_einstellungen_dienst.py::test_unbekanntes_konto_fehler_mit_pfad`, `::test_bankkonto_sachkonto_ohne_kontoart_bank`, `::test_skontokonto_aus_anderem_rahmen`, `::test_auftraggeber_iban_ohne_bankkonto`, `::test_unvollstaendiger_mandant_speicherbar_rechnung_scheitert_mit_verweis`. **Grenze:** „unbekanntes Konto“ heißt in P4 falsche Form oder Personenkonto statt Sachkonto, nicht „kommt im Rahmen nicht vor“ (die `arten`-Spannen decken 0000–9999 ab; Existenz erst mit den Listen aus P3, A36). „Skontokonto aus dem anderen Rahmen“ wird erkannt, wenn die Kontoart abweicht (3736 unter SKR04), nicht bei 8736 (M10) |
| AK78 | AST-Test, je Lader, CLI und Web, andere Gesellschaft | `test_lader_umbau.py::*`, `test_cli_einstellungsquelle.py::test_gesellschaft_bindet_ihre_datenbank`, `::test_gesellschaft_liste_zeigt_kontenrahmen_je_datenbank`, `test_api_einstellungsstand.py::test_datenbank_wert_wirkt_in_freigaben` |
| AK79 | CLI: Grund, K2, K3, festgelegt, stdin, `pruefen` mit Exit-Code | `test_cli_einstellungen.py::*` |
| AK80 | Golden, Einzelwerte, WJ mit Jahr, N1-Warnung, Vorlage | `test_lader_golden.py`, `test_einstellungen_inventar.py::test_neue_felder_abwaertskompatibel`, `test_einstellungen_pruefung.py::test_kontenrahmen_nur_unter_mandant_warnt` |
| AK81 (P4-Teil) | Warnung bei zwei Steuernummern | `test_einstellungen_pruefung.py::test_zwei_steuernummern_warnung` (das eine Feld auf der Firma-Seite: P5) |
| AK100 | Vier-Augen Steuermeldungen komplett (P4c) | `test_elster_vier_augen.py::*` (mit `::test_ausschalten_belebt_keine_alte_freigabe`), `test_einstellungen_antraege.py::test_auto_buchen_schwelle_senken_bei_elster_vier_augen`, `::test_elster_vier_augen_aus_braucht_steuer_freigeben`, `::test_einschalten_mit_einem_berechtigten_fehler_mit_hinweis`, `test_pruefung_verfahrensdoku.py::test_vier_augen_zeilen` |

---

## Sicherheit

- **Nur anfügen, nachweisbar.** Die Versionen sind auf drei Ebenen gegen Änderung geschützt
  (D10): ORM-Sperre, `GESCHUETZT` gegen Massenwege und Trigger unter SQLite **und** PostgreSQL.
  Die Hash-Kette je Abschnitt und der Journal-Bezug je Version machen auch Wege an accounti
  vorbei sichtbar (rohes `INSERT`, Kette neu gerechnet, aber ohne Journaleintrag →
  `einstellungen pruefen` meldet einen Fehler).
- **Geheimnisse:**
  - AES-GCM mit `ACCOUNTI_SCHLUESSEL`, an `<kuerzel>:<name>` gebunden (D22). Ein Chiffrat lässt
    sich keiner anderen Gesellschaft unterschieben.
  - Kein Modell, kein Diff, kein Journal, kein Export, kein `zeigen` und kein Log trägt den
    Klartext (D8). Gelesen wird er nur an den vier Verbrauchsstellen.
  - Der Wert kommt nur über stdin, nie als Argument (Prozessliste, Shell-Verlauf).
  - Ohne Schlüssel sind die Felder gesperrt, mit Hinweis.
- **Pfade nur vom Betreiber.** Alle Pfadfelder sind Betriebsfelder (D7, Markierung und
  Strukturtest). Weder CLI noch später der Browser können den Server über eine Einstellung eine
  beliebige Datei lesen lassen (Kontenzuordnung, Rechtsstand, Zertifikat, Archiv).
- **Umgebung nur vom Betreiber** (D7, H1). Ein `${…}` aus der Datenbank wird nie aufgelöst,
  ein eigener `${…}` in neuen Daten wird abgewiesen. Wer Einstellungen ändern darf, kann so weder
  `ACCOUNTI_SCHLUESSEL` noch Datenbank-Passwörter über Betreff, Kopfzeilen oder ein
  SMTP-Passwortfeld an sich leiten.
- **Zugänge bleiben bei ihrem Ziel** (D26, entschieden; Ergänzung von Anhang A). Host, Port und
  Verschlüsselung von SMTP und IMAP, `basis_url`, `erlaubte_hosts` und `kopfzeilen` eines
  Connectors sowie `llm.provider`/`model` sind K2. Eine Sitzung ohne Code kann einen gespeicherten
  Zugang nicht an einen eigenen Server lenken (wirksam ab P5 im Browser). Mit Code bzw. im
  Verwaltungsmodus geht das, auch für einen Zugang des Betreibers aus `${VAR}`. Wer das
  ausschließen will, legt den Abschnitt in der Datei fest (G-N4, Grenzen).
- **YAML.** Nur `yaml.safe_load`, zentral in `parse_text`/`lies_datei`, mit 64 KB, ohne Anker und
  Aliase (keine Vervielfachung beim Speichern als JSON). Der AST-Test verhindert neue Umgehungen.
- **Kontrollen lassen sich nicht von der kontrollierten Person abschwächen** (E6).
  - K3 wird ein Antrag, bestätigt von einer zweiten Person mit dem Recht der Kontrolle und
    eigenem Code. Ohne Benutzer zählt der Anmeldename über die UID (D13).
  - Anträge laufen ab und verfallen, wenn sich der Stand inzwischen geändert hat.
  - Einschalten von `elster.vier_augen` ohne zweite berechtigte Person ist ausgeschlossen (kein
    Aussperren vor einer Frist, R13).
- **Rechte in der CLI** wie 10a (D12). Schreiben braucht mit Benutzern `VERWALTEN` und immer den
  Einmalcode, auch wenn `auth.einmalcode_bestaetigung: false` gesetzt ist (`streng`). Mit
  Registry müssen `--db` und `--config` zur Gesellschaft gehören (`_pruefe_registry`). Wer ohne
  Registry die CLI mit eigener `--config` samt `einstellungen.quelle: datei` aufruft, handelt als
  Betreiber. Das ist gegenüber heute keine Erweiterung, denn bisher wirkte jede `--config`
  vollständig (Grenzen).
- **Web fail-closed** (D5). Ohne gebundenen Stand oder mit fremdem Pfad liest keine Anfrage
  Datenbank-Abschnitte. Damit kann keine Route still Werte aus der Datei statt aus der Datenbank
  nehmen oder die Werte einer anderen Gesellschaft zeigen. Die Bindung hängt an derselben
  Gesellschaft wie die Rechteprüfung (`angemeldet` bzw. Token). In der CLI gilt dasselbe für den
  Pfad einer anderen Gesellschaft der Registry (D5, M2).
- **Datenbank nicht erreichbar** heißt Abbruch, nicht still die Datei (Schritt 2). **Datei
  fehlt** heißt nicht „Datenbank ignorieren“ (D25).
- **Protokoll** (A116): Die Startmeldung nennt nur Anzahl und Abschnittsnamen. Fehlertexte nennen
  Feldpfade, keine Werte, außer dort, wo der Lader es schon heute tut (IBAN-Prüfziffer nennt die
  IBAN: Das bleibt so in der CLI-Ausgabe, landet aber nicht im Anwendungsprotokoll, Test
  Schritt 17).
- **CSP, CSRF, WCAG:** Es gibt keine neuen Seiten, Routen, Vorlagen, Skripte oder Stile. Die eine
  geänderte Meldung nutzt die vorhandene `meldung.html`. Der Vorlagen-Test (kein `style=`, kein
  Inline-Skript), die Rechte-Matrix, der CSRF-Test und der i18n-Vollständigkeitstest aus 10a/10b
  bleiben grün und decken das ab. Prüfbare Barrierefreiheit (axe-core, Fokus, Kontrast) beginnt
  mit den Seiten in P1 und P5.
- **Abhängigkeiten:** keine neue Python-Abhängigkeit (A117). Gebraucht werden nur
  Standardbibliothek, `pyyaml`, `pydantic`, `sqlalchemy`, `psycopg` und `cryptography`, alle schon
  in `pyproject.toml`. Ihre Versionsgrenzen bleiben unverändert: `sqlalchemy>=2.0`,
  `pydantic>=2.5` und `pyyaml>=6.0` haben keine Obergrenze, nur `cryptography` ist begrenzt
  (`>=50.0.2,<51`). Neu in der CI ist das Abbild `postgres:16.<n>` (PostgreSQL License), genau
  gepinnt und beim Abzweigen mindestens zwei Wochen alt (Schritt 1). Kein CDN.

---

## Migration

- **Eine Migration** `<rev>_add_einstellungen` in der gemeinsamen Kette, mit P4a für alle drei
  Tabellen (P4b und P4c bringen keine), `down_revision` = Kopf beim Abzweigen (nach 10b-1 und den
  Gesamttest-Branches). Wird P1 vorher gemergt, setzt P4a `down_revision` auf dessen Kopf (A118,
  AK61) und stellt dessen Kopf-Tests um. `SCHEMA_STAND` in `db/__init__.py` wird nachgezogen
  (`tests/test_db_upgrade.py`). Migrationstests hängen an der eigenen Revision, nie am Kopf (G-M1,
  Schritt 1).
- **Inhalt:** die Tabellen `einstellungen` (mit Unique `abschnitt, version`, Index `abschnitt`),
  `einstellungsantraege` und `geheimnisse` (Unique `name`). Trigger für `einstellungen` unter
  SQLite (`CREATE TRIGGER IF NOT EXISTS`) und PostgreSQL (`CREATE OR REPLACE FUNCTION
  accounti_nur_anfuegen()`, `DROP TRIGGER IF EXISTS` + `CREATE TRIGGER`). Vorhandene Tabellen aus
  `init_db` werden übernommen, ergänzt wird nur, was fehlt (Muster `ddc9a184ddb4`).
- **Gesellschafts- und Systemdatenbank** teilen die Kette. Die Systemdatenbank bekommt die
  Tabellen leer mit. Ohne Registry ist sie zugleich Gesellschaftsdatenbank.
- **`accounti db upgrade`** (Paket A) erkennt den Schritt an den neuen Tabellen. Hat `init_db` sie
  vorher angelegt, zählt der Schritt als offen, und die Migration verträgt das (Test Schritt 1).
- **Downgrade** nur mit leeren Tabellen (D24). Die Meldung nennt `accounti sicherung erstellen`,
  ab P4c auch `einstellungen export` (G-N5).
- **Keine Datenmigration.** Bestehende Installationen bleiben unverändert, bis jemand speichert
  (A53). `elster.vier_augen` braucht keine Migration (A125, D19).
- **Reihenfolge beim Update:** Sicherung → `db upgrade` → Start. Läuft ein Befehl des neuen
  Abbilds vorher, legt `init_db` die Tabellen samt Triggern selbst an. Das ist unkritisch.

---

## Grenzen

- **Keine Seiten** (P5): Formulare, Verwaltungsmodus, Anträge im Browser, Benachrichtigung bei
  Bank- und Freigabeänderungen (A60; der Fachkern liefert `Ergebnis.meldepflichtig`), Verlauf mit
  Vergleich, Docker-Probe im Browser.
- **Die Datei hat keinen Verlauf.** Die Verfahrensdokumentation zu einem Stichtag vor der ersten
  Datenbank-Version zeigt den heutigen Datei-Stand, mit Hinweis. Wer GoBD-genau dokumentieren
  will, übernimmt die Datei einmal (`einstellungen uebernehmen --aus-datei --grund
  "Ausgangsstand"`).
- **Langlaufende Prozesse außer `serve`** lesen den Stand beim Start, vor allem
  `kanaele webhook starten`. Nach einer Änderung muss der Prozess neu starten. `betrieb lauf`
  startet je Schritt einen eigenen Prozess und ist nicht betroffen.
- **Die CLI mit eigener `--config`** ohne Registry kann über `einstellungen.quelle: datei`
  Datenbank-Werte übergehen. Wie bisher ist der Aufrufer der CLI Betreiber. Mit Registry und
  Benutzern verhindert `_pruefe_registry` das.
- **PostgreSQL-Trigger nur für `einstellungen`.** Journal, Korrekturen und USt-IdNr.-Protokoll
  bleiben unter PostgreSQL bei ORM-Sperre und Hash-Kette. `db/schutz.py` erlaubt das Nachrüsten
  als eigenen Schritt.
- **`llm.auto_buchen_schwelle` wirkt jetzt** (D18). Wer in der Datei bisher wirkungslos einen
  anderen Wert als 0,95 stehen hatte, bekommt ihn ab dem Update. `pruefen` weist darauf hin.
  **`import.standard_bank`/`duplikat_check`** haben ein Modell, aber weiter keine Wirkung (die
  Erkennung ist automatisch, Dubletten prüft accounti immer).
- **Periodenwerte** gibt es nur für die vier Felder aus A46. `sondervorauszahlung` bleibt „je
  Jahr“. Die OSS-Sperre je Quartal stützt sich auf Monatsabschluss, Jahressperre und übermittelte
  USt-VA. Ein eigenes OSS-Meldeprotokoll gibt es nicht (Abgabe im BZSt-Portal).
- **„Konto bekannt“** prüft in P4 nur die Form (Ziffern, Sachkontenlänge, kein Personenkonto in
  einem Sachkontenfeld) und die Kontoart je Feld. Die `arten`-Spannen von SKR03 und SKR04 decken
  0000–9999 lückenlos ab, „liegt in einer Spanne“ wäre keine Prüfung. Ob ein Konto im Rahmen
  vorkommt, lässt sich erst mit den Bezeichnungslisten aus P3 prüfen (N4, A36). Dann kommt dort
  eine Warnung für Konten, die weder in der Liste noch eingerichtet noch bebucht sind. Ein
  Skontokonto des anderen Rahmens mit gleicher Kontoart (8736) bleibt bis dahin unerkannt.
- **Standards werden nicht eingefroren** (D6, sofern der Nutzer zustimmt). Ändert ein späteres
  Update einen Standard, wirkt der neue Wert auch für Abschnitte mit Datenbank-Version. Der
  Golden-Test „leer“ macht jede solche Änderung sichtbar; sie steht dann im CHANGELOG und, ab
  `db upgrade`, als Eintrag `einstellung_standards` im Journal (G-M4). Befehle des neuen Abbilds,
  die vor `db upgrade` laufen, rechnen schon mit dem neuen Standard. Der Eintrag folgt mit
  `db upgrade` bzw. der nächsten Änderung, `serve` und `pruefen` warnen bis dahin.
- **Ziel-Host-Felder sind K2, keine Betriebsfelder** (D26, G-N4). Wer `VERWALTEN` und den Code
  hat (ab P5: den Verwaltungsmodus), kann auch einen Zugang des Betreibers aus `${VAR}` an einen
  eigenen Host lenken. Wer das ausschließen will, legt `versand`, `belegkanaele` bzw. `llm` in
  der Datei fest.
- **Unpassende Standards** wie die SKR03-Skontokonten unter SKR04 meldet P4 als Warnung, ändert
  sie aber nicht (eigener Befund außerhalb von P4).
- **Mit Registry** bleibt der Name einer Gesellschaft der Name aus der Registry, auch wenn
  `mandant.name` in der Datenbank anders lautet (D21; `pruefen` weist darauf hin).
- **Geheimnisse und Kürzel:** Ein Umzug in eine Registry mit anderem Kürzel macht die Chiffrate
  unlesbar (D22). Dann die Geheimnisse neu setzen. `pruefen` meldet das.
- **`zahlung.vier_augen` einschalten** prüft nicht, ob es zwei Freigabe-Berechtigte gibt. Das
  bleibt wie vor 10c (A125 verlangt die Prüfung nur für Steuermeldungen).
- **Ohne zweite Person** ist ein K3-Antrag nicht bestätigbar. Ausweg ist die Festlegung des
  Abschnitts in der Datei durch den Betreiber (R11, gewollt).
- **Gleichzeitige Prozesse:** Der Datei-Cache ist je Prozess. Zwei Prozesse sehen eine geänderte
  Datei nach ihrem nächsten Stand. Datenbank-Versionen sind über die Unique-Bedingung und die
  Schreibsperre gegen doppelte Versionsnummern geschützt.

---

## Offene Punkte (vor bzw. bei der Umsetzung)

1. Beim Abzweigen `alembic heads` und `SCHEMA_STAND` lesen und die Kette eintragen (Schritt 0).
2. Prüfen, ob 10b-1 bzw. P1 neue Lader mitbringen (etwa `lade_korrekturumgebung`, Vorlieben) und
   ob sie in `inventar.LADER` gehören. Der AST-Test findet sie ohnehin.
3. Nach dem Merge von Paket E die Verbraucher von `mandant.oss` in `integrationen/` neu zählen
   (OSS-Konten je Land), bevor Schritt 6 beginnt.
4. Die Liste der Rechtsformen mit P7 (Assistent, Vorschläge nach Rechtsform, A74) abgleichen.
   Werte dürfen nur hinzukommen, nicht wegfallen.
5. **Entscheidung des Nutzers zu D6** (vor Schritt 7): Standards nicht einfrieren (Vorschlag,
   Ausgleich über Journaleinträge `einstellung_standards`, Golden-Test und CHANGELOG; G-M4) oder
   F1 wörtlich (eigene Standards einfrieren, außer `inventar.ABGELEITET`, etwa ein Tag mehr). Die
   Spec sagt „Datei bzw. Standard plus Änderung“. Der Ausgleich braucht keine Spalte, die
   Migration von P4a hängt also nicht an der Entscheidung. Den von der Gegenprüfung genannten
   `standard_hash` je Version empfiehlt der Plan nicht (D6).
6. **D26 entschieden** (26.10.2026, wie vorgeschlagen): Ziel-Host-Felder sind K2. Mit P4b wird
   Anhang A der Spec um den Doku-Baustein „Spec 10c, Anhang A“ ergänzt (**Spec-Ergänzung**).
7. Beim Abzweigen **von P4a**, P4b und P4c prüfen, ob P1 inzwischen gemergt ist und Berührungspunkte
   (`api/app.py` Reihenfolge der Middlewares, `api/sitzung.py` mit `vielleicht_angemeldet`,
   `seiten/freigaben.py`, `docs/betrieb.md`, Alembic-Kette) neu zu lesen sind (G-N1).
8. **Mit P1 dieselbe Regel für Migrationstests vereinbaren** (G-M1): Der P1-Plan (Schritt 3,
   `KOPF = skripte.get_current_head()`, `VOR = get_revision(KOPF).down_revision`) bricht, sobald
   P4a nach P1 gemergt wird. Dann ist `VOR` die P1-Revision, und
   `test_start_ohne_vorlieben_bricht_mit_hinweis_ab` wird rot. Beide hängen ihre Tests an die
   eigene Revision (`REV`, `VOR = get_revision(REV).down_revision`). Wer als Zweiter merged,
   kettet sich an, setzt `SCHEMA_STAND` auf seine Revision und stellt die Kopf-Tests des Ersten
   um. Das geht als Hinweis an P1, den P1-Plan ändert dieser Plan nicht.
9. **(P4b, aus P4a)** Beim Übernehmen aus der Datei und bei `setze_abschnitt` die Größe
   der Normalform begrenzen (64 KB wie `parse_text`): `lies_datei` weist Anker und Aliase
   in der Datei des Betreibers nicht ab (Schritt 2, Abweichung).

---

## Doku-Bausteine

Fertige Texte zum Einarbeiten beim Zusammenführen. Grundlage ist der Stand **nach** dem Merge von
10b-1 und den Gesamttest-Branches (Paket A trägt `db upgrade`, `SCHEMA_STAND` und den
Kontenrahmen unter `buchhaltung` schon in Doku und Vorlage). Wo P1 vorher gemergt ist, bleiben
dessen Texte, P4 ergänzt nur.

**Verteilung auf die PRs** (D28):

| PR | Teile |
|----|-------|
| P4a | CHANGELOG „Geändert“: `llm` wirkt, `datev.wirtschaftsjahr_beginn` als Tag und Monat, `--db` an `fristen`, `pruefen regeln`, `kanaele connectoren`, `elster pin`, Standard-Datenbank für Befehle ohne `--db`; „Hinzugefügt“: neue Felder und Modelle, Periodenwerte. `docs/architektur.md`: `leser.py`, `inventar.py`, `perioden.py`, Erweiterungspunkt. `docs/betrieb.md`: Upgrade-Block (Migration, `llm`, WJ), Periodenwerte. Vorlage: `einstellungen`, `rechtsform`, `kennfarbe`, `oss`, `datev`, `voranmeldungszeitraum`, `gewinnermittlung`, `llm` |
| P4b | README (Feature-Zeile, Abschnitt „Einstellungen“), CHANGELOG „Einstellungen in der Datenbank“, Journalprüfung, `docs/architektur.md` (`dienst.py`, `stufen.py`, `pruefung.py`, `verlauf.py`, Datenmodell, Sicherheit), `docs/betrieb.md` (Abschnitt „Einstellungen: Datei und Datenbank“ ohne Vier-Augen für Steuermeldungen und ohne Export, Sicherung, Aufbewahrung), `docs/bauplan.md`, Spec 10c Anhang A (D26) |
| P4c | README-Zeile USt-Voranmeldung, CHANGELOG „Vier-Augen-Prinzip für Steuermeldungen“ und Verbrauchsregel (D19), `export.py`, `verfahrensdoku --stichtag`, `docs/betrieb.md` (Vier-Augen, Export), Vorlage `elster.vier_augen`, `docs/bauplan.md` „P4 fertig“ |

Die Blöcke unten zeigen den **Endstand nach P4c** (G-N9). P4b kürzt beim Einarbeiten:
- README: ohne die Zeile `einstellungen export`.
- CHANGELOG „Einstellungen in der Datenbank“: ohne `export` in der Befehlsliste und ohne den Satz
  zu `verfahrensdoku --stichtag`.
- Den Eintrag „Vier-Augen-Prinzip für Steuermeldungen“ und die `ustva`-Zeile unter „Geändert“
  ohne die Verbrauchsregel lässt P4b ganz weg.
- `docs/betrieb.md` ohne „Vier-Augen für Steuermeldungen“, ohne `elster.vier_augen` im Absatz
  „Bestätigung“ und ohne die Sätze zu `export`.

P4c ergänzt genau diese Teile. Ebenso lässt P4a im Upgrade-Block von `docs/betrieb.md` den Satz
zu `accounti einstellungen pruefen` und den zu `db upgrade` nach späteren Updates weg; den
Befehl und die Standard-Einträge gibt es erst ab P4b (beim Einarbeiten von G-N5 gefunden). Der
Baustein „Spec 10c, Anhang A“ gehört zu P4b.

### README.md

**Ergänzt** die Feature-Tabelle im Block „Belegvollständigkeit & Ordnungsmäßigkeit“ nach der
Zeile **Unveränderbares Journal** um:

```markdown
| ✅ | **Einstellungen mit Verlauf** | Einstellungen je Gesellschaft in der Datenbank — nur anfügend versioniert mit Person, Grund und Journal, Verfahrensdokumentation zu jedem Stichtag; Werte, die vom Zeitraum abhängen (Voranmeldungszeitraum, Dauerfrist, OSS, Gewinnermittlung), wirken nie zurück; Lockerungen von Kontrollen nur auf Antrag mit zweiter Person; Geheimnisse verschlüsselt; die YAML bleibt Startwert, Festlegung und Rückweg (`accounti einstellungen`) |
```

**Ersetzt** in der Zeile **USt-Voranmeldung** den Schluss „…, Freigabe durch den Menschen“ durch
„…, Freigabe durch den Menschen (wählbar mit zwei Personen: `elster.vier_augen`)“.

**Fügt** nach dem Abschnitt „### Betrieb, Benutzer und mehrere Gesellschaften“ ein:

````markdown
### Einstellungen

Ab der ersten Änderung gilt für einen Abschnitt der Stand aus der Datenbank der Gesellschaft —
die YAML bleibt Startwert. Jede Änderung ist eine neue Version mit Person und Grund; nichts wird
überschrieben.

```bash
accounti einstellungen zeigen elster --herkunft          # wirksamer Wert und woher er kommt
accounti einstellungen setzen mandant.rechnung.zahlungsziel_tage 21 --grund "neue AGB"
accounti einstellungen setzen elster.voranmeldungszeitraum quartal --ab 2027 \
  --grund "Bescheid vom 12.10.2026"                     # 2026 bleibt monatlich
accounti einstellungen verlauf elster                    # Versionen: Feld alt → neu, Person, Grund
accounti einstellungen pruefen                           # Validierung, Verlauf, Datei ≠ Datenbank
printf '%s' "$SMTP_PASS" | accounti einstellungen geheimnis setzen versand.smtp.passwort
accounti einstellungen export --ziel accounti-stand.yaml # Rückweg zur Datei
```

Mit eingerichteten Benutzern braucht jede Änderung die Rolle `verwalter` und den Einmalcode.
Wer bei aktivem Vier-Augen-Prinzip eine Kontrolle abschwächt (z. B. `zahlung.vier_augen` aus),
stellt einen Antrag; wirksam wird er erst, wenn eine zweite Person mit Freigaberecht ihn mit
`accounti einstellungen antraege bestaetigen ID` bestätigt. Details:
[docs/betrieb.md](docs/betrieb.md#einstellungen-datei-und-datenbank).
````

### CHANGELOG.md

**Unter `## [Unreleased]` → `### Hinzugefügt`** oben einfügen:

```markdown
- **Einstellungen in der Datenbank** (Baustein 10c, Paket P4): Je Gesellschaft liegen die
  Abschnitte der Konfiguration ab der ersten Änderung als nur anfügende Versionen in der
  Datenbank (`einstellungen`: Person, Grund, Quelle, Hash-Kette je Abschnitt, SQLite- und
  PostgreSQL-Trigger gegen Ändern und Löschen, Journal `einstellung_geaendert` mit den
  geänderten Feldern). Vorrang: Umgebung (`${VAR}`) vor Festlegung in der Datei
  (`einstellungen.quelle: datei` bzw. `einstellungen.festgelegt: [...]`) vor Datenbank vor Datei
  vor Standard; Betriebswerte (`database`, `server`, `auth`, `gesellschaften`, alle Pfade,
  `elster.eric`, Webhook-Adresse, eVatR-URL, FinTS-Produkt-ID) kommen immer aus Datei oder
  Umgebung. Ein zentraler Abschnittsleser ersetzt jedes `yaml.safe_load` der Konfiguration;
  innerhalb eines Befehls bzw. einer Anfrage gilt ein Stand, und es gelten die Einstellungen der
  Datenbank, mit der der Befehl arbeitet. Validierung mit denselben Modellen wie beim Lesen und
  Querprüfungen (Konten im Kontenrahmen, Bankkonto-Sachkonto, Skontokonten, Auftraggeber-IBAN);
  Gleichzeitigkeit über Versionsnummern; Bestätigungsstufen nach Spec 10c Anhang A — Lockerungen
  von Kontrollen werden bei aktivem Vier-Augen-Prinzip ein Antrag (`einstellungsantraege`, 7 Tage
  gültig), den eine zweite Person mit Freigaberecht bestätigt. Werte, die vom Zeitraum abhängen
  (`elster.voranmeldungszeitraum`, `elster.dauerfristverlaengerung`, `mandant.oss`,
  `abschluss.gewinnermittlung`), als „ab Zeitraum → Wert“; gesperrt, sobald der Zeitraum
  freigegeben, übermittelt oder abgeschlossen ist, Kontenrahmen und Wirtschaftsjahresbeginn
  nach der ersten Buchung. Geheimnisse (`versand.smtp.passwort`, `llm.api_key`, Webhook-Adresse
  der Benachrichtigung, ELSTER-PIN) verschlüsselt in `geheimnisse` (AES-GCM,
  `ACCOUNTI_SCHLUESSEL`), nie im Klartext in Datenbank, Journal, Log oder Export.
  `accounti einstellungen zeigen|setzen|verlauf|pruefen|uebernehmen|export|geheimnis|antraege`;
  `accounti verfahrensdoku --stichtag` mit Anhang „Änderungen der Einstellungen“. Einstellungen,
  Anträge und Geheimnisse laufen in Sicherung und Wiederherstellung mit und stehen als
  Organisationsunterlagen (10 Jahre) im Aufbewahrungsbericht.
- **Vier-Augen-Prinzip für Steuermeldungen** (`elster.vier_augen`, Standard aus): USt-VA und
  Dauerfristantrag brauchen dann zwei Freigaben derselben Werte von zwei verschiedenen Personen
  mit Recht `steuer_freigeben`; einschalten nur mit zwei solchen Personen, ausschalten nur auf
  Antrag. Ohne Schalter genügt eine Freigabe wie bisher.
- Neue Felder: `mandant.rechtsform`, `mandant.kennfarbe` (1–6); Modelle für `llm`, `import`,
  `datev`.
```

**Unter `### Geändert`** einfügen:

```markdown
- `llm.auto_buchen_schwelle`, `llm.provider` und `llm.model` wirken jetzt (bisher galt immer
  0,95 und das Standardmodell). Wer einen anderen Wert in der Konfiguration stehen hat, bekommt
  ihn ab diesem Update — `accounti einstellungen pruefen` weist darauf hin.
- `datev.wirtschaftsjahr_beginn` wird als Tag und Monat gelesen und geschrieben (`"07-01"`); ein
  Datum mit Jahr bleibt gültig, das Jahr zählt nicht.
- `accounti ustva freigeben`/`uebermitteln` und `ustva dauerfrist --freigeben|--uebermitteln`
  achten auf `elster.vier_augen`; `--von` zählt dann nicht als Person. Eine erfolgreiche Abgabe
  verbraucht alle Freigaben derselben Werte bis zur genutzten — auch ohne Schalter; eine ältere,
  doppelte Freigabe erlaubt keine zweite Abgabe mehr.
- `accounti fristen`, `pruefen regeln`, `kanaele connectoren` und `elster pin` haben `--db`;
  ohne Angabe gilt wie bei allen Befehlen `sqlite:///accounti.db` bzw. die Gesellschaft.
- Fehlt die Konfigurationsdatei, gelten die Einstellungen der Datenbank (bisher: Standards bzw.
  „Vorlage kopieren“).
- `accounti journal pruefen` vergleicht Einstellungsänderungen feldweise (nur geänderte Felder
  stehen im Journal).
```

### docs/bauplan.md

**Ergänzt** nach dem Absatz zu Baustein 10 (bzw. nach dem Absatz zu 10c, falls P1 ihn schon
angelegt hat):

```markdown
**Baustein 10c — Oberfläche und Einrichtung** ([Spec](specs/2026-10-26-oberflaeche-einrichtung.md))
entsteht in sieben Paketen in vier Wellen. **Paket P4 (Einstellungen: Fachkern + CLI) ist
fertig** ([Plan](plans/2026-10-26-oberflaeche-p4-einstellungen-kern.md)): Einstellungen je
Gesellschaft in der Datenbank, nur anfügend versioniert mit Journal und Hash-Kette; die YAML
bleibt Startwert und kann Abschnitte festlegen; Betriebswerte nur aus Datei und Umgebung; ein
Abschnittsleser für alle Lader mit einem Stand je Befehl bzw. Anfrage; Periodenwerte mit
Sperren; Lockerungen von Kontrollen nur auf Antrag mit zweiter Person; Geheimnisse im Tresor;
`accounti einstellungen`; Verfahrensdokumentation zum Stichtag; Vier-Augen-Prinzip für
Steuermeldungen. Die Seiten dazu folgen mit P5, Benutzer mit P6, der Assistent mit P7.
```

### docs/architektur.md

**Fügt** nach dem Abschnitt `### betrieb/` ein:

```markdown
### `einstellungen/` *(vorhanden — [Baustein 10c](specs/2026-10-26-oberflaeche-einrichtung.md), Paket P4)*

Wo Einstellungen leben und wie sie gelesen werden.

- **`leser.py`** — `lies_abschnitt(pfad, name)` ist der einzige Weg an einen Abschnitt der
  Konfiguration; jeder Lader (`lade_firma`, `lade_elster`, …) ruft ihn und validiert wie bisher
  mit seinem Modell. Vorrang je Abschnitt: Umgebung (`${VAR}`-Blätter der Datei) → Festlegung
  in der Datei (`einstellungen.quelle`/`festgelegt`) → neueste Version in der Datenbank → Datei
  → Standard. Betriebsabschnitte und -felder (`inventar.BETRIEBSFELDER`, alle Pfade) kommen immer
  aus der Datei. Ein `Stand` je CLI-Befehl bzw. Web-Anfrage (Kontextvariable) hält einen
  Schnappschuss der Versionen und die gelesenen Dateien fest; die CLI bindet ihn an die
  Datenbank aus `--db` bzw. der Gesellschaft (ohne beides `sqlite:///accounti.db`), das Web an
  die Gesellschaft der Sitzung oder des Tokens (`api/einstellungsstand.py`). Ohne Stand
  (Unit-Tests, Werkzeuge): nur die Datei. Eine fehlende Datei ist ein leerer Startwert. Ein
  Web-Stand ohne Bindung und ein Pfad einer anderen Gesellschaft lesen keine
  Datenbank-Abschnitte (fail-closed). `${…}` kommt nur aus der Datei. `geheimnis(name)`
  entschlüsselt Geheimnisse nur an den Stellen, die sie brauchen.
- **`dienst.py`** — Schreiben in der Sitzung des Aufrufers: `speichere` (Versionsprüfung unter
  der Schreibsperre, Validierung über die echten Lader, Querprüfungen, Sperren, Stufe K1/K2/K3,
  Version + Journal), `setze_feld`, `setze_periodenwert`, `uebernehme_aus_datei`, Anträge,
  Geheimnisse. CLI (`befehle/einstellungen.py`) und Einstellungsseiten (P5) rufen dieselben
  Funktionen.
- **`inventar.py`, `stufen.py`, `perioden.py`** — Daten: Abschnitte, Betriebs-, Geheim-,
  Perioden- und Kontofelder; Bestätigungsstufen nach Spec 10c Anhang A; Periodenwerte „ab
  Zeitraum → Wert“ und ihre Sperren.
- **`pruefung.py`, `verlauf.py`, `export.py`** — `einstellungen pruefen` (Validierung,
  Hash-Kette, Journalbezug, Datei ≠ Datenbank), Diffs je Version (Journal, Verfahrensdoku,
  Verlauf), YAML-Export als Rückweg.
```

**Ergänzt** im Abschnitt „## Datenmodell“ die Liste der Tabellen der Gesellschaftsdatenbank um:

```markdown
- `einstellungen` — Versionen je Abschnitt (nur anfügen; ORM, `GESCHUETZT`, Trigger unter
  SQLite und PostgreSQL; Hash-Kette je Abschnitt), `einstellungsantraege` (Lockerungen mit
  zweiter Person; Status nur aus „offen“), `geheimnisse` (AES-GCM, Bezug `<gesellschaft>:<name>`).
```

**Ergänzt** im Abschnitt „## Sicherheit“:

```markdown
- Einstellungen: Pfade und Betriebswerte nur aus Datei oder Umgebung; Geheimnisse nur als
  Chiffrat und nie in Modellen, Diffs, Journal, Log oder Export; Lockerungen von Kontrollen nur
  mit zweiter Person; `yaml.safe_load` nur an einer Stelle (AST-Test).
```

**Fügt** unter „## Erweiterungspunkte“ ein:

````markdown
### Neuen Konfigurationsabschnitt anschließen

1. Modell und Lader im Fachmodul wie bisher (`lade_x(pfad=STANDARD_PFAD) -> XEinstellungen`),
   gelesen **nur** über `einstellungen.lies_abschnitt(pfad, "x")` — `yaml.safe_load` außerhalb
   der Positivliste lässt `tests/test_lader_umbau.py` scheitern.
2. In `einstellungen/inventar.py` eintragen: `ABSCHNITTE["x"]`, der Lader in `LADER`, Pfadfelder
   in `BETRIEBSFELDER`, Geheimnisse in `GEHEIMFELDER` (mit Verbrauchsstelle über
   `einstellungen.geheimnis`), Konten in `KONTOFELDER`; steuer- oder sicherheitsrelevante Felder
   in `stufen.py`.
3. Ein Feld, das vom Zeitraum abhängt, als `Periodisch[...]` mit `…_fuer(zeitraum)` und Eintrag in
   `PERIODENFELDER` samt Sperrregel; das Rohfeld heißt `<name>_roh` mit Alias.
4. Ein Pfadfeld als `Betriebsfeld[...]` (Strukturtest). `${…}` nur in der Datei — der Leser gibt
   keinen Platzhalter aus der Datenbank weiter.
5. Golden-Daten ergänzen (`tests/werkzeuge/golden_lader.py`). **Einen Standard ändern** heißt:
   Golden-Daten bewusst neu erzeugen und die Änderung mit altem und neuem Wert im CHANGELOG unter
   „Geändert“ nennen — Standards sind in Datenbank-Versionen nicht eingefroren; `db upgrade`
   hält die Änderung je Installation als Journaleintrag `einstellung_standards` fest.
````

### docs/betrieb.md

**Fügt** nach dem Abschnitt „## Mehrere Gesellschaften“ ein:

````markdown
## Einstellungen: Datei und Datenbank

Die Konfigurationsdatei ist der **Startwert**. Sobald ein Abschnitt (z. B. `mandant`, `elster`,
`zahlung`) einmal über `accounti einstellungen` (oder später im Browser) geändert wird, gilt für
ihn der Stand aus der Datenbank der Gesellschaft. Die Datei wird für diesen Abschnitt dann nicht
mehr gelesen — mit drei Ausnahmen:

- **Betriebswerte** kommen immer aus der Datei: die Abschnitte `database`, `server`, `auth`,
  `gesellschaften`, `einstellungen` sowie `elster.eric.*`, `pruefung.archiv`,
  `pruefung.kontenrahmen_datei`, `abschluss.kontenzuordnung`, `anlagen.rechtsstand`,
  `belegkanaele.webhook.host`/`port`, `belegkanaele.email[].ca_datei`, `ustid_pruefung.url` und
  `bank.fints.produkt_id`. Sie lassen sich nicht über `einstellungen setzen` ändern.
- **Umgebungsvariablen** gehen vor: Steht in der Datei `${VAR}`, gilt die Variable, auch wenn
  der Abschnitt in der Datenbank gepflegt ist (dazu `ACCOUNTI_EVATR_URL`). Platzhalter gibt es
  nur in der Datei: `einstellungen setzen` weist einen eigenen `${…}` ab, und aus der Datenbank
  wird nie eine Umgebungsvariable eingesetzt.
- **Festlegung:** Wer Konfiguration als Code führt, legt Abschnitte in der Datei fest — sie sind
  dann nur noch dort änderbar:

  ```yaml
  einstellungen:
    quelle: datei                 # alle Abschnitte aus der Datei (Datenbank-Versionen ruhen)
    # festgelegt: [elster, zahlung]   # oder nur diese
  ```

Ohne Datenbank-Version ändert sich nach dem Update nichts. Fehlt die Datei ganz (etwa im
Container nach der Einrichtung im Browser), gelten die Werte der Datenbank. `accounti einstellungen pruefen`
zeigt je Abschnitt die Herkunft und meldet, wenn die Datei vom Stand der Datenbank abweicht
(„es gilt die Datenbank“) — als Warnung, wenn die Datei **nach** der letzten Version geändert
wurde; `accounti serve` meldet das beim Start. Den Datei-Stand übernimmt
`accounti einstellungen uebernehmen --aus-datei [ABSCHNITT] --grund "…"`; den Stand der
Datenbank als Datei liefert `accounti einstellungen export --ziel DATEI` (Geheimnisse als
`${…}`). Zusammen mit `einstellungen.quelle: datei` ergibt der Export dieselben Werte.

**Verlauf.** Jede Änderung ist eine neue Version mit Person, Zeitpunkt, Quelle und Grund; nichts
wird überschrieben oder gelöscht (Organisationsunterlagen, § 147 Abs. 1 Nr. 1 AO, 10 Jahre).
`accounti verfahrensdoku --stichtag JJJJ-MM-TT` dokumentiert den damals gültigen Stand samt
Änderungsanhang. Werte, die vom Zeitraum abhängen, tragen ein „ab“:

```yaml
elster:
  voranmeldungszeitraum: { 2026: monat, 2027: quartal }   # Einzelwert gilt für alle Jahre
mandant:
  oss: { 2026-Q1: false, 2027-Q1: true }
```

Ein Zeitraum mit freigegebener oder übermittelter Meldung, festgeschriebenem Monat oder
abgeschlossenem Jahr ist gesperrt; Kontenrahmen und Beginn des Wirtschaftsjahres nach der ersten
Buchung.

**Bestätigung.** Mit eingerichteten Benutzern braucht jede Änderung in der CLI die Rolle
`verwalter` und den Einmalcode (`ACCOUNTI_EINMALCODE` für Skripte). Wer bei aktivem
`zahlung.vier_augen` bzw. `elster.vier_augen` eine Kontrolle abschwächt (Vier-Augen aus,
Freigeberliste erweitern, Höchstbetrag anheben, KI-Schwelle senken, Prüfregeln abschalten),
stellt einen Antrag; eine zweite Person mit `zahlung_freigeben` bzw. `steuer_freigeben`
bestätigt ihn mit ihrem Code (`accounti einstellungen antraege bestaetigen ID`) innerhalb von
7 Tagen. Gibt es keine zweite Person, bleibt nur die Festlegung in der Datei.

Felder, die bestimmen, wohin ein Zugang geht — Host, Port und Verschlüsselung von SMTP
(`versand.smtp`) und Postfächern (`belegkanaele.email[]`), `basis_url`, `erlaubte_hosts` und
`kopfzeilen` eines Connectors, `llm.provider` und `llm.model` —, brauchen im Browser den Code bzw.
den Verwaltungsmodus. Wer Zugänge über `${VAR}` bereitstellt und ihr Ziel allein bestimmen will,
legt die Abschnitte fest (`einstellungen.festgelegt: [versand, belegkanaele, llm]`).

**Vier-Augen für Steuermeldungen** (`elster.vier_augen`, Standard aus): USt-VA und
Dauerfristantrag brauchen dann zwei Freigaben derselben Werte von zwei Personen mit
`steuer_freigeben`. Einschalten geht nur, wenn es zwei solche aktive Benutzer gibt — sonst
bliebe jede Meldung vor der Frist hängen.

**Geheimnisse.** SMTP-Passwort, LLM-API-Schlüssel, die Webhook-Adresse der Benachrichtigung und
die ELSTER-PIN lassen sich verschlüsselt in der Datenbank ablegen:

```bash
printf '%s' "$SMTP_PASS" | accounti -g muster einstellungen geheimnis setzen versand.smtp.passwort
accounti -g muster einstellungen geheimnis liste       # nur Name, gesetzt am, von
```

Der Wert kommt nur über stdin. Ein `${VAR}` in der Datei und die PIN-Datei
(`elster.eric.pin_datei`) gehen vor. Ein Klartext-Passwort in der Datei verhindert, dass der
Abschnitt in die Datenbank übernommen wird — vorher auf `${VAR}` oder ein Geheimnis umstellen.

**Container.** `config/` bleibt schreibgeschützt (`:ro`, `read_only: true`); Einstellungen
ändern sich trotzdem — sie liegen in der Datenbank:

```bash
docker compose run --rm app einstellungen setzen mandant.rechnung.zahlungsziel_tage 21 --grund "neue AGB"
```
````

**Ergänzt** im Abschnitt „## Sicherung und Wiederherstellung“ nach dem ersten Absatz:

```markdown
Einstellungsversionen, Anträge und Geheimnisse sind Tabellen der Gesellschaftsdatenbank und
laufen mit. Geheimnisse liegen nur als Chiffrat in der Sicherung: Wiederherstellen lassen sie
sich nur mit **demselben** `ACCOUNTI_SCHLUESSEL` und in eine Gesellschaft mit demselben Kürzel
(sonst `einstellungen geheimnis setzen` neu). Die Konfigurationsdatei selbst ist nicht in der
Sicherung — wer sie mitsichern will, legt `accounti einstellungen export` daneben.
```

**Ergänzt** im Abschnitt „## Upgrades“ nach dem Block „Update auf Baustein 7“:

```markdown
**Update auf Baustein 10c, Paket P4** (Migration `<rev>`: Tabellen `einstellungen`,
`einstellungsantraege`, `geheimnisse`; Trigger gegen Ändern und Löschen der Versionen unter
SQLite und PostgreSQL): `db upgrade` wie oben, sonst nichts — bis zur ersten Änderung gelten die
Werte der Datei wie bisher. Zwei Dinge wirken ab diesem Stand neu: `llm.auto_buchen_schwelle`,
`llm.provider` und `llm.model` (bisher ohne Wirkung, immer 0,95) und `datev.wirtschaftsjahr_beginn`
als Tag und Monat (ein Datum mit Jahr bleibt gültig). `accounti einstellungen pruefen` einmal
ausführen: Es meldet ungültige oder unvollständige Abschnitte und einen Kontenrahmen, der nur
unter `mandant` steht. Das Downgrade geht nur, solange noch keine Einstellung in der Datenbank
gespeichert ist. Nach jedem späteren Update `accounti db upgrade` ausführen, auch ohne neue
Migration: Es hält geänderte Standards der Einstellungen im Journal fest (Verfahrensdokumentation).
```

**Ergänzt** im Abschnitt „## Aufbewahrung und Löschkonzept“ in der Aufzählung:

```markdown
- Einstellungsversionen und Änderungsanträge sind Organisationsunterlagen (§ 147 Abs. 1 Nr. 1,
  Abs. 3 AO, 10 Jahre); accounti sondert sie nie aus — sie tragen den Verlauf der
  Verfahrensdokumentation.
```

### Spec 10c, Anhang A (Ergänzung, P4b; **Spec-Ergänzung**, D26)

**Ergänzt** in Anhang A der Spec (`docs/specs/2026-10-26-oberflaeche-einrichtung.md`) bei den
K2-Feldern, mit Datum und Verweis auf diesen Plan:

```markdown
- **Ziel eines Zugangs** (Ergänzung 26.10.2026, P4 D26): `versand.smtp.host`, `.port`,
  `.verschluesselung`; `belegkanaele.email[].host`, `.port`, `.verschluesselung`;
  `belegkanaele.connectoren[].basis_url`, `.erlaubte_hosts`, `.kopfzeilen`; `llm.provider`,
  `llm.model`. Grund: Wer sie ändert, lenkt einen gespeicherten Zugang (Tresor, Geheimnis,
  `${VAR}`) oder die Bankumsätze an einen anderen Server, ohne das Geheimnis zu sehen;
  `verschluesselung: keine` schickte das Passwort im Klartext. `benutzer` bleibt K1.
```

### config/accounti.example.yaml

**Ergänzt** am Anfang nach `database:`:

```yaml
# Einstellungen (optional): Ab der ersten Änderung über "accounti einstellungen" (bzw. im
# Browser) gilt je Abschnitt der Stand aus der Datenbank; diese Datei ist dann Startwert.
# einstellungen:
#   quelle: datei                # alle Abschnitte nur aus dieser Datei
#   festgelegt: [elster, zahlung]  # oder nur diese Abschnitte
```

**Ergänzt** in `mandant:` nach `name:`:

```yaml
  rechtsform: gmbh             # einzelunternehmen, ek, gbr, ohg, kg, gmbh, ug, gmbh_co_kg, ag, eg, partg, sonstige
  # kennfarbe: 1               # 1–6: Farbe der Gesellschaft in der Oberfläche (sonst aus dem Kürzel)
```

**Ersetzt** in `mandant:` die Zeile `oss: false …` durch:

```yaml
  oss: false                   # OSS-registriert? Dann zahlen EU-Privatkunden ihren Landessatz;
                               # ab einem Quartal: { 2026-Q1: false, 2027-Q1: true }
```

**Ersetzt** in `datev:` die Zeile(n) zu `wirtschaftsjahr_beginn` durch:

```yaml
  wirtschaftsjahr_beginn: "01-01"   # MM-TT; abweichendes WJ (§ 4a EStG) z.B. "07-01":
                                    # abschluss --jahr 2026 = 01.07.2025–30.06.2026 (Jahr des
                                    # WJ-Endes); ein Datum mit Jahr wird weiter gelesen
```

**Ergänzt** in `elster:` nach `dauerfristverlaengerung:`:

```yaml
  # voranmeldungszeitraum und dauerfristverlaengerung ab einem Jahr:
  #   voranmeldungszeitraum: { 2026: monat, 2027: quartal }
  vier_augen: false                # true: USt-VA und Dauerfristantrag brauchen zwei Personen
                                   # mit steuer_freigeben (einschalten nur mit zwei solchen)
```

**Ergänzt** in `abschluss:` beim Kommentar zu `gewinnermittlung`:

```yaml
                                 # ab einem Wirtschaftsjahr: { 2026: euer, 2027: bilanz }
```

**Ersetzt** in `llm:` den Kommentar über `auto_buchen_schwelle` durch:

```yaml
  # Ab welcher Confidence automatisch buchen (0.0-1.0)? Wirkt ab Baustein 10c; bei
  # elster.vier_augen ist Senken nur mit zweiter Person möglich
```

---

## Prüfbefunde und Umgang

Gegnerische Prüfung von Fassung 1 auf `main` 18faeaa (Urteil: „umsetzbar: nein“; nach H1–H4 mit
H4 als Entscheidung des Nutzers und M1–M6: ja). Jeder Befund ist am Code nachgeprüft, bevor er
übernommen wurde. Die Fundstellen stehen in der Spalte „Nachgeprüft“. Eine Spalte „Umgang“
nennt, wo der Befund in Fassung 2 steht, und begründet jede Abweichung vom Vorschlag. Die
Gegenprüfung von Fassung 2 steht darunter (Kennung „G-…“, eingearbeitet in Fassung 3). Wo sie
einen Umgang aus der ersten Runde ändert, ist das in der Zeile vermerkt.

### Hoch

| Nr. | Nachgeprüft | Umgang |
|-----|-------------|--------|
| H1 `${VAR}` aus Datenbank-Werten löst jede Umgebungsvariable auf | **bestätigt:** `erechnung/versand._ersetze_variablen` über den ganzen Abschnitt (auch von `aufgaben` genutzt), `belege/kanaele/einstellungen.loese_auf` für Postfach-Passwort (`aufbau.passwort_fuer`) und Connector-Kopfzeilen und -Parameter (`json_http._aufloesen`); D8 erlaubte `${VAR}` in Geheimfeldern neuer Daten | **übernommen.** D7 „`${…}` nur aus der Datei“: Schreiben weist jedes `${` ab, das nicht gleich dem Blatt der Datei ist (auch Geheimfelder, D8 angepasst). Der Leser gibt keinen Platzhalter aus der Datenbank weiter (ersetzt durch das gleiche Datei-Blatt oder entfernt), `pruefen` meldet einen Fehler. Tests in Schritt 2, 4, 7, 12, 13; Sicherheit, Doku |
| H2 `journal pruefen` meldet ab der zweiten Änderung falsche Verlaufsbefunde | **bestätigt:** `pruefung/journal._pruefe_verlauf` mit `_unterschiede` über `set(alt) \| set(neu)`; A40 schreibt nur geänderte Felder unter `objekt_id` = Abschnitt | **übernommen** als D27: `TEILSTAENDE`, Stand je Schlüssel fortgeschrieben, verglichen nur die Schlüssel des Vorher-Stands. Das prüft strenger als „nur gemeinsame Schlüssel“: Ein falsches Vorher für ein früher geändertes Feld fällt weiter auf. Tests in Schritt 7 |
| H3 Fehlende Datei: Lader ignorieren die Datenbank | **bestätigt:** `is_file()`-Wächter in `konfiguration.py` (119, 165, 192, 214), `elster/konfiguration.py` (178, 192, 203), `erechnung/versand.py` 103, `aufgaben/einstellungen.py` 185, `belege/kanaele/einstellungen.py` 209, `abschluss/konfiguration.py`, `integrationen/einstellungen.py`, `mahnwesen`, `bank`, `pruefung`, `anlagen`, `zahlung`, `export/datev_stammdaten`, `pruefung/verfahrensdoku._Doku.roh` | **übernommen** als D25: fehlende Datei = `{}`, Wächter entfallen, Meldung nur ohne Datei und ohne Version (`quelle_vorhanden`). Pilot-Lader schon in Schritt 2; AST-Test, Lader-Tests, Handprobe im Container ohne Datei |
| H4 Wechsel des Ziel-Hosts gibt gespeicherte Zugänge preis | **bestätigt:** IMAP-Host aus `EmailPostfach.host`, Passwort aus Tresor bzw. `${VAR}`; SMTP ebenso; `{zugang}` geht an `basis_url`; `llm.provider`/`model` wirken ab D18; Anhang A macht nur Passwörter zu K2 | **übernommen als Vorschlag, entschieden am 26.10.2026 wie vorgeschlagen** (D26, Offener Punkt 6; Spec-Ergänzung Anhang A; Rest siehe G-N4). Abweichungen vom Vorschlag: `verschluesselung` (SMTP und IMAP) kommt hinzu, weil `keine` das Passwort im Klartext schickte. `benutzer` bleibt K1, weil er das Ziel des Geheimnisses nicht ändert. In der CLI wirkt K2 wie K1 (immer Code); die Stufe zählt ab P5 |

### Mittel

| Nr. | Nachgeprüft | Umgang |
|-----|-------------|--------|
| M1 Befehle ohne `--db` lesen nur die Datei | **bestätigt:** AST über `cli.py` und `befehle/` findet genau `fristen`, `pruefen regeln`, `kanaele connectoren`, `elster pin` mit `config` ohne `db`; `kontext.standardwerte["db"]` nur mit Registry oder `ACCOUNTI_DB` | **übernommen, beide Vorschläge:** Ersatzwert `STANDARD_DB` (= Standard von `DB_OPTION`) und `--db` an den vier Befehlen, Strukturtest mit leerer Ausnahmeliste (D3, Schritt 3) |
| M2 `gesellschaft liste/zeigen` lesen b unter dem Stand von a | **bestätigt:** `befehle/gesellschaft.py` ruft `lade_buchhaltung(g.konfiguration)` je Eintrag (gt-betrieb Z. 67, 88) | **übernommen:** `mit_quelle` je Gesellschaft und fail-closed in der CLI für den Pfad einer anderen Gesellschaft der Registry (D5, Schritt 3, Tests mit SKR04 nur in b) |
| M3 Validierung über alle Lader hat Nebenwirkungen | **bestätigt:** `_ersetze_variablen` wirft bei fehlender Variable; D16 lief jeden Lader, der den Abschnitt liest, ohne Zurechnung | **übernommen, verfeinert:** Prüfmodus ohne Auflösung, Fehler an Platzhalterblättern zählen nicht. Abweichung vom Vorschlag „übrige Fehler werden Hinweise“: In nicht geänderten Abschnitten zählen Fehler, die **erst durch die Änderung** entstehen, weiter als Fehler (Vergleich ohne/mit Änderung). Sonst ließe sich über `mandant.bank.bic` ein ungültiger Auftraggeber in `zahlung` speichern (`Firma` prüft die BIC nicht, `Auftraggeber` schon). Schon vorhandene Fehler werden Hinweise (D16, Tests in Schritt 7) |
| M4 Unbekannte Feldpfade still angenommen | **bestätigt:** `extra="forbid"` nur in `abschluss/kontenrahmen.py`, `belege/kanaele/*`, `pruefung/einstellungen.py`; `Firma`, `Buchhaltung`, `ElsterEinstellungen` ohne | **übernommen:** `unbekannte_felder` über `inventar.MODELL` mit Vorschlag, beim Übernehmen nur Hinweis. Beim Nachprüfen gefunden: `datev_stammdaten` liest `mandant.sachkonten_laenge` am Modell vorbei; das Feld wird Modellfeld (D16, Schritt 5, 7) |
| M5 Unvollständiger `mandant` ohne Steuernummer und USt-IdNr. nicht speicherbar | **bestätigt:** `Firma._pflichten` wirft `ValueError` (Fehlerart `value_error`) | **übernommen:** Fehlerart `pflicht_fehlt` (`PydanticCustomError`, Text unverändert), `unvollstaendig_erlaubt` je Abschnitt über Fehlerarten (D16, Schritt 5, 7) |
| M6 Periodenwerte noch roh gelesen | **bestätigt:** `gewinnermittlung_angegeben` (gt-abschluss) mit Verbrauchern `cli.py` 1455 und `pruefung/verfahrensdoku.py` 165, 556 fehlte; `lade_oss` liefert `bool(dict)`; `mypy` (strict, ohne pydantic-Plugin) fände `!= "bilanz"` nicht | **übernommen:** Rohfelder `*_roh` mit Alias, damit `mypy` jeden alten Zugriff findet; `lade_oss(pfad, zeitraum)` und `gewinnermittlung_angegeben(pfad, wj)` mit Pflichtparameter; AST-Test gegen Rohzugriffe (D14, Schritt 6) |
| M7 Datei-Cache über (realpath, mtime_ns, size) kann veralten | **bestätigt** (Zeitstempel-Takt, gleiche Länge) | **übernommen** mit Inhalts-Hash als Schlüssel (Datei klein lesen, nur Parsen cachen). Dass der Hash zugleich `datei_hash` sei, ist durch G-N2 berichtigt: `datei_hash` gilt dem normalisierten Abschnitt (D9). `st_ino`/`st_ctime_ns` nicht gewählt, weil auch das bei schnellem Neuschreiben am Ort nicht sicher wäre (Schritt 2) |
| M8 D6 weicht von E2 (F1) ab | **bestätigt:** Spec E2 „Datei bzw. Standard plus Änderung“ | **berechtigt, als Entscheidung des Nutzers vorgelegt** (D6, Offener Punkt 5). Die Begründung gegen das Einfrieren steht jetzt in D6: Rückfallwerte (`zahlung.auftraggeber`, `buchhaltung.kontenrahmen`), Kontenrahmen-Standards von `abschluss`/`kasse` und OSS-Konten von `elster`. Die Alternative für F1 wörtlich ist beschrieben. **Zurückgewiesen** ist der Teilvorschlag „je Version die accounti-Version festhalten“: `__version__` ist `0.1.0-dev` und wird nicht je Update erhöht, und ein Update zwischen zwei Versionen bliebe unsichtbar. Als Ausgleich bleibt der Golden-Test „leer“ dauerhaft Wächter über alle Standards, und jede Standard-Änderung steht im CHANGELOG. **Durch G-M4 ergänzt:** Der Ausgleich nannte noch die accounti-Version. Jetzt hält die Datenbank die Standards als Journaleinträge `einstellung_standards` fest (D6) |
| M9 TDD-Reihenfolge stimmt nicht | **bestätigt:** Schritt-3-Tests brauchen umgebaute Lader; `test_umgebung_schlaegt_alles` brauchte `lade_versand`; `test_pruefen_exit_code` brauchte `pruefe_alles` | **übernommen:** Pilot-Lader `lade_buchhaltung`, `lade_elster` in Schritt 2; `test_umgebung_schlaegt_alles` prüft in Schritt 2 den Leser, der Lader-Teil steht in Schritt 4; `pruefen` samt Exit-Code-Test in Schritt 13 |
| M10 „unbekanntes Konto“ mit Spannen nicht prüfbar | **bestätigt** per Skript: `arten` von SKR03 (21 Spannen) und SKR04 (20) decken 0000–9999 ohne Lücke ab; `namen` hat nur 45 bzw. 26 Einträge | **übernommen:** „unbekannt“ = Form (Ziffern, Sachkontenlänge, 0000) und Personenkonto statt Sachkonto; Kontoart je Feld. Grenze in D16, Grenzen und AK-Zuordnung (AK77) ehrlich benannt. Beim Nachprüfen gefunden: 8736 (SKR03 „Skonto gewährt“) ist auch unter SKR04 ein Erfolgskonto und bleibt unerkannt; SKR03-Skontostandards unter SKR04 hätten jedes Speichern von `buchhaltung` blockiert, darum gelten Querprüfungen nur für gesetzte Werte, Standards ergeben eine Warnung |
| M11 CI ohne PostgreSQL | **bestätigt:** `.github/workflows/ci.yaml` ohne Dienst, `tests/pg_hilfe.py` überspringt ohne `ACCOUNTI_TEST_PG` | **übernommen:** Job `postgresql` mit `services: postgres:16.<n>` (genau gepinnt, mindestens zwei Wochen alt), ganze Suite, bestehende PG-Tests laufen mit (Schritt 1) |
| M12 Ein PR mit 18 Schritten | **berechtigt** | **übernommen, anderer Schnitt** (D28): P4a Lesen (0–6, mit Periodenwerten), P4b Schreiben (7–10, 12, 13, 16, mit Sperren), P4c Steuer-Vier-Augen, Export, Stichtag (11, 14, 15). Abweichung vom Vorschlag: Periodenwerte und Sperren nicht erst in P4c. Sonst gäbe es auf `main` einen Schreibweg, der den Voranmeldungszeitraum rückwirkend ändert oder den Kontenrahmen nach Buchungen wechselt. `elster.vier_augen` kommt geschlossen in P4c, damit der Schalter nie gesetzt, aber wirkungslos ist |

### Niedrig

| Nr. | Nachgeprüft | Umgang |
|-----|-------------|--------|
| N1 Falsche Annahmen | **bestätigt:** nur `cryptography` begrenzt; `e7153706b43a` hängt an `d5a849692843`, Paket E ohne Migration; `seiten/freigaben.py` seit c019c2a; mit Registry Namen aus der Registry; `lade_elster` liest über `_mit_oss_konten` auch `integrationen`, `buchhaltung`; Worktrees inzwischen gt-debitoren 82120b5, web-oberflaeche 1d3cf59 | **übernommen:** Stand der Grundlage, Kopf, Sicherheit (Abhängigkeiten), D21, `LADER` mittelbar mit dynamischem Test (`test_lader_lesen_was_registriert_ist`) |
| N2 `erzeuge` hat schon `stand` | **bestätigt** (`pruefung/verfahrensdoku.py`, `stand: date \| None`) | **übernommen:** `--stichtag` füllt `stand`, Quelle aus `session.get_bind()`, Kopf kennzeichnet den gemischten Stand (Schritt 15) |
| N3 `fristen 2027` | **bestätigt** (`--jahr` ist Option) | **übernommen** (`fristen --jahr 2027`) |
| N4 Importzyklus `leser.herkunft` | **bestätigt** (D1 gegen D23) | **übernommen:** `herkunft` nach `pruefung.py`, im Leser nur `herkunft_roh` (D23) |
| N5 `waehle_uebermittler` verlangt `pin_datei` | **bestätigt** (Schleife über `bibliothek`, `zertifikat`, `pin_datei`) | **übernommen:** `pin_datei` keine Pflicht mehr, gesetzte PIN-Datei geht vor, Test ohne PIN-Datei mit Geheimnis (Schritt 10) |
| N6 Hash-Definition | **bestätigt** (`journal.kanonisch` ohne `default=`) | **übernommen:** ohne `id` und `hash`, Normalform vorher, `erstellt_am` wie das Journal über `model_dump(mode="json")`, Test SQLite = PostgreSQL (D9, Schritt 1) |
| N7 Rechte für `antraege ablehnen` widersprüchlich | **bestätigt** (D12 gegen Schritt 9) | **übernommen:** Antragsteller mit `VERWALTEN`, sonst Recht der Kontrolle (D12, Tests) |
| N8 `uebernehmen` mit Lockerung | **bestätigt** als Testlücke (`stufe` vergleicht schon alt/neu wirksam) | **übernommen:** Test `test_uebernahme_aus_datei_mit_lockerung_wird_antrag` |
| N9 `berater_nummer` als Zahl | **bestätigt** (`str(datev.get(...))`, Vorlage mit Text) | **übernommen:** Text mit Ziffernprüfung, Zahl wird wie heute zu Text (Schritt 5) |
| N10 Schnappschuss-Verbindung schließen, Sperre im Prozess-Cache | **berechtigt** | **übernommen:** eine kurze Lesetransaktion, Schnappschuss im Speicher, `threading.Lock`, zwei Tests (Schritt 2) |
| N11 Namens-Regex anfällig | **berechtigt** | **übernommen mit Ergänzung:** Markierung `Betriebsfeld[...]` ist die Quelle der Wahrheit; Regex und Typ `Path` bleiben als Netz mit begründeten Ausnahmen, weil eine vergessene Markierung sonst unbemerkt bliebe (D7) |
| N12 Export mit Passwort in der URL | **berechtigt** (`ohne_passwort` vorhanden) | **übernommen** (Schritt 14, Test) |
| N13 Golden-Test braucht eigenen Serialisierer | **bestätigt** (bool, dict, `Partnerdaten`, Datum; `lade_firma` auf „leer“ wirft) | **übernommen** inklusive Fehler als Ergebnis (D20, Schritt 0) |
| N14 Antragsinhalt hashen | **berechtigt** | **übernommen:** `inhalt_hash`, Anzeige und Neuberechnung bei der Bestätigung (D9, Schritt 9, 12) |
| N15 D19-Verbrauch nur mit `vier_augen`? | **berechtigt** (Klarstellung fehlte) | **entschieden: gilt immer**, mit Begründung in D19 (sonst belebte das Ausschalten alte Freigaben). Der übliche Ablauf ohne Schalter bleibt wie bisher. Neu ist nur, dass eine doppelte ältere Freigabe mit verbraucht wird; das steht im CHANGELOG. Zwei Tests |

### Gegenprüfung von Fassung 2 (eingearbeitet in Fassung 3)

Urteil der Gegenprüfung: „umsetzbar: ja“, mit der Bedingung, M1, M3, M4 und M5 vor bzw. in P4a
und M2 vor Schritt 7 nachzutragen. Kein Hoch-Befund. Nachgeprüft auf `main` 87c6c8d (Paket A
inzwischen gemergt) und in den Branches. Die Bestätigungen der Gegenprüfung (H1–H3, M1–M7,
M9–M12 eingearbeitet; Zurückweisungen zu M3, M12, H4, M7, N11 und der Grund zu M8 berechtigt)
stehen nicht noch einmal hier. Die Zeilennummern beziehen sich auf den genannten Stand.

**Entscheidung D26** (zu H4, G-N4): entschieden am 26.10.2026 wie vorgeschlagen (Orchestrator).
Host, Port und Verschlüsselung bei SMTP und IMAP, `basis_url`, `erlaubte_hosts` und `kopfzeilen`
der Connectoren sowie `llm.provider`/`llm.model` sind K2 (Einmalcode). Die Ergänzung von Anhang A
der Spec ist als Doku-Baustein „Spec 10c, Anhang A“ markiert und kommt mit P4b. Eingetragen in
Kopf, D26, Schritt 9, Sicherheit, Grenzen, Offener Punkt 6 und `docs/betrieb.md`.

| Nr. | Nachgeprüft | Umgang |
|-----|-------------|--------|
| G-M1 Kopfabhängige Migrationstests brechen, sobald P4a Kopf wird | **bestätigt:** `main` `tests/test_db_upgrade.py:201, 227, 280, 289` (`downgrade -1`; 227 und 280 erwarten „Downgrade abgebrochen … erp“), `fix/gesamttest-abschluss` `tests/test_migration_anlagen_buchung.py:35`, `feat/web-oberflaeche` `tests/test_migration_web.py:89, 92` (`SPRACHE` als Kopf) und `:134, 137`; P1-Plan Schritt 3 mit `KOPF = get_current_head()`. `main` stellt `test_migration_belegvollstaendigkeit.py:145` schon auf `VOR` um | **übernommen:** Tests an `REV`/`VOR` (Schritt 1), Kopftest nur „ein Kopf, == `SCHEMA_STAND`, `REV` in der Kette“. Neu ist die Pflichtaufgabe „Kopfabhängige Migrationstests umstellen“ mit `git grep` vor dem Migrations-Commit und der Liste im PR. Regel mit P1 als Offener Punkt 8; den P1-Plan ändert dieser Plan nicht. Ergänzt in Kontext (Alembic), Berührungspunkte, Migration und A118 |
| G-M2 Unbekannte Felder der Datei-Basis blockieren oder verfälschen (`mandant.kontenrahmen`) | **bestätigt:** `Firma` (`konfiguration.py:61–76`) kennt `kontenrahmen` nicht, `lade_buchhaltung` liest ihn als Rückfall (`:198–206`). Die Vorlage auf `main` 87c6c8d führt ihn nicht mehr unter `mandant`, das Prüfskript meldet dort nur `mandant.sachkonten_laenge`. Bestandsdateien können ihn aber noch dort haben; dafür gibt es den Rückfall. Zusätzlich geprüft: `lade_mandant`, `lade_steuerangaben`, `lade_eigene_firma`, `lade_zahlung` und `_Doku` lesen nur Felder von `Firma` | **übernommen:** Fehler nur für unbekannte Felder der Änderung, Felder der Basis entfallen mit Hinweis (D16, Schritt 7). `inventar.UMZUG` wie vorgeschlagen. Ergänzt wurde: Die erste `buchhaltung`-Version nimmt den Wert gleich mit, bei festgelegter `buchhaltung` kommt `FestgelegtError` mit Weg. Vier Tests in Schritt 7 |
| G-M3 P4a nutzt Teile aus P4b | **bestätigt:** `pruefung.abweichungen` entsteht erst in Schritt 13. `einzelne_gesellschaft` liest den Namen über `lade_eigene_firma` (`web-oberflaeche` `api/dienste.py:149`), umgebaut erst in Schritt 4. `_Doku.roh()` wird nur für `mandant` und `belegkanaele` genutzt (`verfahrensdoku.py:129, 207, 732`) | **übernommen:** Startmeldung samt Test nach Schritt 13, Name samt Test nach Schritt 4. **Abweichung:** kein `wirksam_alle`. `_Doku.abschnitt(name)` liest über `lies_abschnitt` (Schritt 4); `lies_abschnitt` gibt ohnehin keine Datenbank-Geheimnisse aus (D8), ein neuer Leser-Aufruf ist unnötig |
| G-M4 Ausgleich in D6 widerspricht der Zurückweisung von M8 | **bestätigt:** `__version__ = "0.1.0-dev"` (`src/accounti/__init__.py:3`), genutzt in `verfahrensdoku.py:173, 736`; kein Build-Argument im `Dockerfile` | **übernommen, andere Lösung:** Journaleinträge `einstellung_standards` je Abschnitt (nur geänderte Pfade) aus `db upgrade` und `speichere`; `serve` und `pruefen` warnen; Anhang der Verfahrensdoku (D6, Schritte 7, 13, 15). **Nicht gewählt:** `standard_hash` je Version bzw. Build-Kennung. Beides zeigt nur den Stand beim Schreiben, ein Update zwischen zwei Versionen bliebe unsichtbar (der Grund aus M8). Werte nennt beides nicht. Keine Spalte, darum hängt die Migration von P4a nicht an D6 |
| G-M5 `lade_llm` bricht ohne `${ANTHROPIC_API_KEY}` | **bestätigt:** Vorlage `config/accounti.example.yaml:74`, `cli.py:2261, 2329` (`LLMEngine() if llm else None`), `_ersetze_variablen` wirft (`erechnung/versand.py:89–94`); `LLMEngine` hat heute kein `api_key` (`klassifikation/llm.py:34–40`) | **übernommen:** `${VAR}` nur in `api_key`, nachsichtig (`None`), Schwellen immer lesbar, Test `test_ohne_api_key_variable_laeuft_no_llm` (Schritt 5) |
| G-N1 Absprache mit P1 zur Middleware | **bestätigt:** P1-Plan R-P1-4 und Offener Punkt 4, `web-oberflaeche` `api/app.py:71` `add_middleware(Sicherheit)`; Starlette fügt vorn ein, die zuletzt hinzugefügte liegt außen | **übernommen:** Registrierung vor `Sicherheit`, Test `test_sicherheit_ist_die_aeusserste_middleware`, Bindung im gemeinsamen Kern mit `vielleicht_angemeldet`, falls P1 vorher gemergt ist; Offener Punkt 7 gilt auch für P4a (Berührungspunkte, Schritt 3) |
| G-N2 `datei_hash` widersprüchlich | **bestätigt** (Schritt 2 gegen D9) | **übernommen:** D9 gilt, der Hash der ganzen Datei ist nur Cache-Schlüssel; Test `test_datei_hash_nur_ueber_den_abschnitt` |
| G-N3 Platzhalter in Versionen machen `pruefen` rot | **bestätigt** am Plan: Der Leser legt Platzhalterblätter ohnehin aus der Datei darüber, gespeicherte sind wirkungslos | **übernommen:** gleiche Platzhalterblätter werden nicht gespeichert; Fehler nur für `${` ohne Platzhalter der Datei an demselben Pfad (D7, Schritte 2, 7, 13). **Beim Einarbeiten ergänzt:** Betriebsfelder werden ebenso nicht gespeichert, und der Leser entfernt sie aus einer Version vor dem Überlagern. Sonst gälte bei fehlendem Datei-Blatt der Datenbank-Wert (A42). Test `test_betriebsfeld_der_version_gilt_nie` |
| G-N4 K2 lenkt im Verwaltungsmodus trotzdem ein `${VAR}`-Geheimnis um | **berechtigt** als Restrisiko | **nicht übernommen** (Alternative zur Entscheidung D26, die wie vorgeschlagen gefallen ist). Benannt in D26, Sicherheit, Grenzen und `docs/betrieb.md`, mit der Festlegung des Abschnitts in der Datei als Weg |
| G-N5 D24 verweist zu früh auf `einstellungen export` | **bestätigt:** `export` erst P4c; `accounti sicherung erstellen` gibt es (`befehle/sicherung.py:133`) | **übernommen:** Meldung nennt `sicherung erstellen`, P4c ergänzt `export` (D24, Schritt 1, Migration). Beim Einarbeiten gefunden: Der Upgrade-Block für P4a nannte `einstellungen pruefen` (erst P4b); er wird beim Aufteilen gekürzt (Doku-Bausteine) |
| G-N6 PostgreSQL-Job ungenau | **bestätigt:** `ci.yaml` installiert Tesseract und Prüfwerkzeuge und setzt `ACCOUNTI_PRUEFWERKZEUGE_PFLICHT=1`. Die Tests überspringen ohne beides (`test_belege_ocr.py:49`, `test_erechnung_kosit_pruefer.py:20`) | **übernommen** als „ausdrücklich ohne“: der Job installiert `.[dev,fints]` und läuft ohne Tesseract, Prüfwerkzeuge und Pflicht-Variable; ruff, mypy und Coverage nur im Job `test` (Schritt 1) |
| G-N7 Prozess-Cache veraltet bei neu angelegter Datenbank | **berechtigt** (etwa Wiederherstellung unter derselben URL bei laufendem `serve`) | **übernommen:** Schlüssel mit Zeilen-`hash` aus derselben Abfrage; Test `test_cache_erkennt_neu_angelegte_datenbank` (Schritt 2) |
| G-N8 Stände der Worktrees veraltet | **bestätigt und überholt:** `main` steht inzwischen auf 87c6c8d (#32, Paket A), `gt-betrieb` gibt es nicht mehr. `gt-debitoren` 2f62e17, `gt-steuer-datev` 243754f, `gt-belege` 2d1aec2, `web-oberflaeche` 43031a7. `git diff` seit den Ständen von Fassung 2: keine Änderung an Ladern, Konfigurationsmodulen, Migrationen; `safe_load` weiter 30 Stellen in 25 Dateien | **übernommen:** Kopf und „Stand der Grundlage“ nachgezogen; Golden-Daten beim Rebase aus `main` ohne P4 neu erzeugen, falls Lader sich ändern (Schritt 0) |
| G-N9 Kleinigkeiten | **bestätigt:** Fristen zu D26 widersprüchlich; `lade_oss(pfad, zeitraum)` gegen „Signatur unverändert“; Vorlage `mandant.sachkonten_laenge` „4 oder 6“ (Z. 11); Doku-Blöcke für P4b mit Export und Vier-Augen; P1-Plan B4: P1 liest keine YAML und leitet die Kennfarbe aus dem Kürzel ab | **übernommen:** D26 entschieden (Frist entfällt); Ausnahme in Ziel und D1 benannt; „Personenkonto = Sachkontenlänge + 1“ (D16); Kürzungsliste für P4b und P4a bei den Doku-Bausteinen; D28 und Schritt 5 berichtigt (P5 und P7 bauen auf dem Leser, nicht P1) |

### Zurückgewiesen

Kein Befund ist ganz zurückgewiesen. Teilweise nicht übernommen, jeweils oben begründet:
- M8: accounti-Version je Version festhalten
- M3: alle Fehler anderer Abschnitte zu Hinweisen machen
- M12: Periodenwerte und Sperren erst in P4c
- H4: `benutzer` als K2
- M7: `st_ino`/`st_ctime_ns` als Schlüssel
- G-M3: `wirksam_alle` im Leser (unnötig, `_Doku.abschnitt` über `lies_abschnitt`)
- G-M4: `standard_hash` je Version bzw. Build-Kennung (ersetzt durch Journaleinträge der Standards)
- G-N4: Ziel-Host-Felder bei `${VAR}`-Zugang als Betriebsfelder (D26 ist anders entschieden; Restrisiko benannt)
