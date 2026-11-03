# Design-System & Gerüst (Baustein 10c, Paket P1) — Umsetzungsplan

> **Für agentische Umsetzer:** Schritte der Reihe nach, jeder testgetrieben (Test zuerst, rot
> sehen, implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken. Ablageort beim
> Zusammenführen: `docs/plans/2026-10-28-oberflaeche-p1-design.md`. Branch
> `feat/oberflaeche-p1-design`, ein PR mit Squash-Merge gegen `main`.
>
> **Fassung 4** (26.10.2026, abends): an die Design-Leinwand angeglichen, die der Nutzer
> freigegeben hat („Die Richtung passt. Setz das Design so in Baustein 10c um.“). **Neu** ist der
> Abschnitt **„Design-Leinwand“** (L0–L10, vor „Entscheidungen“) mit folgendem Inhalt:
> - Token mit nachgerechneten Kontrasten: neu `--fehler-text`, `--schatten` und `--schleier`, die
>   Kennfarben aus der Leinwand plus eine sechste;
> - eine Schriftskala mit 12/13/20/40 px, Abstände mit Zwischen- und Feinstufen, Radien von 2 bis
>   12 px;
> - Maße und Zustände jeder Komponente, die Layouts und die Symbole (36 statt 37);
> - die Abweichungen Leinwand ↔ Spec mit ihrer Lösung und eine Zuordnung Zeichenfläche →
>   Vorlage/Makro/Klasse/Paket;
> - `/muster` als Nachbildung der Zeichenfläche „Bausteine“ (hell und dunkel nebeneinander) sowie
>   einen Bildvergleich mit Maßprobe.
>
> **Geändert** sind die Entscheidungen „Gerüst“ und „Design-System“, die Abweichungen, die
> Seitenstruktur (`/muster`, Symbole) und die Schnittstelle (Komponenten, Monogramm,
> `NavEintrag.betont`). Außerdem die Schritte 0, 1, 2, 4, 5, 7, 8, 12 und 14, die Dateien, die
> Spec-Tabelle, Grenzen, Risiken, Übergabe, offene Punkte, Doku-Bausteine und ein Nachtrag zur
> Grundlage. **Unverändert** bleiben Fachlogik, Migration, Zähler, Lesezugriff, Fehlerwege, Hilfe,
> Vorlieben, Testregeln und Prüfbefehle. Eine Übersicht steht am Ende unter „Angleichung an die
> Leinwand (Fassung 3 → 4)“. Maßgeblich für das Aussehen ist die Leinwand. Wo sie der Spec
> widerspricht, gilt die Spec (L7).
>
> **Fassung 3** (26.10.2026), nach der zweiten gegnerischen Prüfung überarbeitet (Abschnitt
> „Prüfbefunde und Umgang“ am Ende, zweite Tabelle). Fassung 2 folgte der ersten Prüfung,
> Fassung 1 der Spec 10c (Status „entschieden“, F1–F5 beantwortet) und den Skizzen. Gelesen:
> `main` **87c6c8d** (#32 = Paket A, baumgleich mit 606ef21; davor #31 18faeaa), Worktree
> `web-oberflaeche` **43031a7** (10b-1, drei Commits nach 1d3cf59, noch nicht auf `main`) und
> die Gesamttest-Branches C 2d1aec2, D 2f62e17, E 243754f, F 410cc64 (Migrationen,
> `db/__init__.py`, `db/upgrade.py`, die Auth-Dateien, ihre Berührungen mit `api/` und die
> Migrationstests). **Abzweigen erst, wenn 10b-1 auf `main` ist**; Paket A ist es seit #32
> (Begründung unter „Stand der Grundlage“). Dann die Annahmen unter „Stand der Grundlage“ gegen
> `main` prüfen. Zeilenangaben beziehen sich auf 43031a7 bzw. 87c6c8d; die drei Commits nach
> 1d3cf59 berühren von den zitierten Dateien nur `buchung/pruefschlange.py`,
> `pruefen/_regelvorschau.html` und `i18n/en.yaml`, die übrigen Zeilen gelten unverändert.

**Ziel:** Nach diesem Paket sieht jede Seite von accounti gleich aus und funktioniert gleich: ein
ruhiges, eigenes Design nach der freigegebenen Design-Leinwand (Abschnitt „Design-Leinwand“) mit
Token für hell und dunkel (am Benutzer wählbar: automatisch, hell, dunkel), Systemschrift, CSS
ohne Framework und ohne Build-Schritt, Symbole als lokales SVG-Sprite. Breite Bildschirme bekommen
links eine Seitenleiste mit Zählern, schmale eine untere Leiste mit höchstens fünf Zielen und eine
Seite „Mehr“ – alles ohne Skript. Die aktive Gesellschaft steht mit Kennfarbe und Kürzel
(Monogramm) auf jeder Seite, gewechselt wird auf einer eigenen Seite. Es gibt Hilfe je
Bereich, Fehlerseiten im Design, „Mein Konto“ mit den Anzeige-Vorlieben (Sprache, Darstellung,
Fachansicht, Beträge verbergen, Tastenkürzel) und eine Musterseite mit allen Komponenten. Die
Seiten aus 10a und 10b-1 ziehen ohne fachliche Änderung ins neue Design um; dabei verschwinden
die Befunde I1 und I8–I12 (waagrechtes Scrollen, überladene Kopfleiste, heller Dunkelmodus,
Codefeld ohne Label, zu schmale Label-Spalte, Hauptaktion nicht erkennbar). Ab diesem Paket gelten
die Querschnittsregeln A102–A119 als Tests für jedes weitere Paket: Kontrast, Fokus, Zielgrößen,
Umbruch, Formulare, CSP, Rechte, CSRF, htmx-Formen, Protokoll, Abhängigkeiten, Zweisprachigkeit.
Neue Fachlogik entsteht nicht.

**Spec:** [`docs/specs/2026-10-26-oberflaeche-einrichtung.md`](../specs/2026-10-26-oberflaeche-einrichtung.md)
(legt Schritt 0 ab), Abschnitte 6.1, 6.8, 6.9, 6.10, Entscheidungen E14–E16, E19, E20,
Paketschnitt Abschnitt 9 · **Anforderungen** A1–A9, A87 (Teil Vorlieben), A89–A101, A121;
Querschnitt A102–A119 · **Akzeptanz** AK1–AK8, AK44–AK61, AK43 für die Abläufe dieses Pakets ·
Skizzen 1, 2 und 8 (Gerüst), 3–5, 7 und 9 nur als Ausblick ·
**Design-Leinwand** (freigegeben 26.10.2026; Schritt 0 legt sie unter
`docs/design/2026-10-26-leinwand/` ab): alle zehn Zeichenflächen, maßgeblich für das Aussehen
(Abschnitt „Design-Leinwand“) ·
**Baut auf:** 10a (Gerüst, Anmeldung, Rollen, Gesellschaften, CSP, CSRF, Einmalcode,
Router-Registry), 10b-1 (i18n, htmx 2.0.11 mit Fehlerwegen, Prüfschlange, Belegvorschau,
Rechte-Matrix mit `MIT_EINMALCODE`, Vorlagen-Scan) ·
**Nicht hier:** Übersicht „Heute zu tun“ (P2), neue Bedienung der Prüfschlange und Belege-Minimum
(P3), Einstellungen (P4, P5), Benutzerverwaltung und der Sicherheitsteil von „Mein Konto“ (P6),
Assistent (P7), Auswertungen (10b-2).

```
 Browser (Jinja2 serverseitig · htmx 2.0.11 · accounti.js + pruefen.js · kein Build-Schritt)
    │  <html lang data-theme="auto|hell|dunkel">  <meta name="color-scheme">  CSP aus 10a unverändert
    ▼
 statisch/  accounti.css  ── @layer token, basis, layout, komponenten, seiten, hilfen, druck
            │               Token hell/dunkel = Leinwand (Kontrast- und Leinwandtest lesen sie aus der Datei),
            │               auch als .thema-hell/.thema-dunkel für /muster
            symbole.svg   ── Lucide 1.55.0, 36 Symbole, <use href="…?v=…#name">  · LIZENZ-lucide.txt
            accounti.js   ── Fehlerhinweis, aria-busy, Fokus nach Austausch, Benutzermenü schließen
            pruefen.js    ── Tasten der Prüfseite, abschaltbar über <body data-tastenkuerzel>
    ▼
 vorlagen/  basis.html (Gerüst) · schlicht.html (Anmeldung, 500) · _komponenten.html (Makros)
            konto.html · menue.html · gesellschaften.html · hilfe/ · muster.html · fehler.html · _fehler.html
    ▼
 api/  vorlagen.seite() (async: Gerüst-Kontext; Zähler im Threadpool über den Lesezugriff, nur für
       ganze Seiten mit Status < 400; neue Seiten mit HX-Request als Inhaltsfragment)
       geruest.py ── Geruest, Bereiche je Rolle, untere Leiste, aktiver Bereich, Brotkrumen, Kennfarbe, Hilfethema
       lesezugriff.py ─ Zähler-Engines je Gesellschaft: ohne init_db, nur lesend, kurze Zeitlimits, eigener Pool
       registry.py ─ Navigationspunkt(titel, pfad, bereich, symbol, recht | eines von, zaehler, kurztitel)
       seiten/ konto.py (/konto, /konto/vorlieben, 308 vom alten Sprachpfad) · menue.py · hilfe.py
               muster.py (+ /muster/beispiel) · gesellschaft.py (+ GET) · bestehende Seiten im neuen Design
       sitzung.py ─ vielleicht_angemeldet (Hilfe, 404) · verweigert(a, *rechte): 403 mit Recht und Rollen
       sicherheit.py ─ 500 als schlichte Designseite ohne Einzelheiten
    ▼
 auth/dienst.setze_vorlieben ─▶ auth_benutzer.darstellung · fachansicht · betraege_verbergen · tastenkuerzel
                                 (gezieltes UPDATE; Migration <rev>_add_benutzer_vorlieben, jede Datenbank,
                                  db.SCHEMA_STAND = <rev>, Betrieb über `accounti db upgrade`)
 buchung/pruefschlange.anzahl_offen · db/repo_zahlung.anzahl_laeufe  ─▶ Zähler in der Navigation

 Werkzeuge (nicht ausgeliefert): scripts/symbole.py (Sprite aus lucide-static) ·
 scripts/browserprobe/ (Node: Playwright 1.64.0 + axe-core 4.14.0; leinwand.mjs = Referenzbilder,
 probe.mjs --vergleich = Bildvergleich und Maßprobe) · tests/browserprobe_welt.py
 Referenz (nicht ausgeliefert): docs/design/2026-10-26-leinwand/ (canvas.json + 10 Zeichenflächen)
```

---

## Kontext und Abgrenzung

### Stand der Grundlage (gelesen am 26.10.2026)

| Stand | Commit | Für P1 maßgeblich |
|-------|--------|-------------------|
| `main` | **87c6c8d** (#32, Paket A „Gesamttest Betrieb“, baumgleich mit 606ef21) auf 18faeaa (#31) | #31 bringt keine Migration und berührt in `api/` nur `rest/laeufe.py`; #32 bringt `6d38d11fc348_token_je_gesellschaft` auf `ddc9a184ddb4`. Alembic-Kopf und `SCHEMA_STAND` **`6d38d11fc348`** |
| 10b-1 | **43031a7** auf `feat/web-oberflaeche` (593216c + acht Nachbesserungen, zuletzt „Runde 3: Doku, Plan und Grenzen“) | zweigt von ec32890 ab, wird vor P1 ohne inhaltliche Änderung auf `main` gebracht (E19); dabei kettet es `d5a849692843_add_kontierung` → `e7153706b43a_add_benutzer_sprache` auf `6d38d11fc348` neu und muss die kopfrelativen Tests aus Paket A umstellen (B10). Die Nachbesserungen seit 593216c ändern für P1: `seiten/pruefen.py` (403-Prüfungen jetzt um :593/:650), `seiten/buchungen.py`, `pruefen/_aktionen.html` (neu `e.freigabe_gesperrt`: Freigeben fehlt dann, dazu ein Prüfregel-Hinweis), `pruefen/liste.html`, `pruefen/regeln.html`, `pruefen.css` (52 Zeilen), `models/auth.py` (Kommentare und `FREIGABEWEGE`), `i18n/en.yaml`, `tests/test_i18n_katalog.py` (Katalogwerte ohne fremde Tags); seit 1d3cf59 außerdem `buchung/pruefschlange.py` (+119 Zeilen: `Bankkontowechsel`, Regel aus Umsätzen ohne Namen nur mit Bestätigung – P1 ergänzt dort nur `anzahl_offen`), `pruefen/_regelvorschau.html` (neue msgid „Weitere Treffer, Gegenpartei nicht erkennbar:“, weiter mit `class="hinweis"`) und `en.yaml` (+1) |
| Gesamttest-Branches | `fix/gesamttest-abschluss` (Paket F) 410cc64, `-belege` (C) 2d1aec2, `-debitoren` (D) 2f62e17, `-steuer-datev` (E) 243754f; Paket A ist gemergt | C, D und F bringen je eine Migration, **alle noch mit `down_revision = 'ddc9a184ddb4'`** (F `2f7c7043043e`, C `46371a6681c2`, D `a14acef69fae`); beim Zusammenführen wird jede neu gekettet. Kopfrelativ ist darunter `tests/test_migration_anlagen_buchung.py:35` (F, `downgrade -1`); C und D gehen auf ausdrückliche Revisionen (D: `REVISION`/`_vorher()`, `test_migration_verrechnungen.py:20–28`) |
| Paket A im Einzelnen | 87c6c8d | `db.SCHEMA_STAND = "6d38d11fc348"` (`db/__init__.py:125–128`, Kommentar „beim Zusammenführen neuer Migrationen hier nachziehen“); `init_db` stempelt **neue** Datenbanken mit `SCHEMA_STAND` (`stemple`, :142–169); `sicherung wiederherstellen` behält den Vermerk des Ziels (`betrieb/sicherung.py`); `accounti db upgrade` (`db/upgrade.py`: ohne Vermerk den Stand aus den Merkmalen der Migrationen ableiten, stempeln, `upgrade head`; legt keine SQLite-Datei neu an); `alembic/env.py` nimmt eine übergebene Verbindung. Tests: `tests/test_db_upgrade.py:61–67` verlangt `get_heads() == [SCHEMA_STAND]`, `:70–82` den Vermerk nach `db init`; `tests/test_migration_belegvollstaendigkeit.py:191–198` den Vermerk nach einer Wiederherstellung. **Kopfrelativ:** `test_db_upgrade.py:201` und `:227` (SQLite) sowie `:280` und `:289` (nur mit PostgreSQL) gehen mit `downgrade -1` vom Kopf aus; `:227` und `:280` erwarten, dass dieser Schritt abgewiesen wird. Geändert sind außerdem `db/repo_auth.py`, `db/tabellen_auth.py` (Token je Gesellschaft), `models/auth.py`, `auth/dienst.py` – dieselben Dateien, die P1 für die Vorlieben anfasst |
| Alembic-Kette für P1 | — | `down_revision` = der **eine** Kopf, den `alembic heads` beim Abzweigen zeigt (im Plan **`K`**; mit 10b-1 auf `main` voraussichtlich `e7153706b43a`, wenn bis dahin keiner der Branches C, D, F gemergt ist). Im selben Commit `db.SCHEMA_STAND = "<rev>"`. Die Tests führen die **eigene** Revision als Konstante `VORLIEBEN = "<rev>"` (sie ändert sich beim Neuketten nicht) und lesen `VOR = get_revision(VORLIEBEN).down_revision` aus dem `ScriptDirectory`; nichts im Test hängt am Kopf (B10). Vor dem Merge `alembic heads` erneut lesen; ist P4 oder ein Gesamttest-Branch vorher gemergt, auf dessen Kopf setzen und `SCHEMA_STAND` mitziehen (A118) |

**Warum P1 auf Paket A wartet:** Spec 9 verlangt für P1 nur 10b-1 auf `main`. Nach der
vereinbarten Reihenfolge (Gesamttest-Pakete zuerst, dann 10b-1 rebasen) ist Paket A dann ohnehin
gemergt – seit #32 (87c6c8d) ist es das. P1 setzt es voraus: `SCHEMA_STAND`, `db upgrade` und die
Vermerk-Logik bestimmen Migration, Tests und `docs/betrieb.md`, und A ändert dieselben
Auth-Dateien. C, D, E und F müssen nicht vorher gemergt sein. Wer nach dem Abzweigen von P1
merged, kettet neu (A118); P1 liest vor dem eigenen Merge `alembic heads` neu. Als Schutz wirkt
außerdem die Zeile `SCHEMA_STAND = …`: P1 und jedes andere Paket mit Migration ändern sie, der
Git-Konflikt zwingt das später gemergte zum Rebase.

Gelesen wurde der Quelltext der Stände ohne Lauf gegen eine Datenbank. Die Spec maß die
Vorschau von 10b-1 am 26.10.2026 (Anhang C der Spec, `messwerte.json`).

**Nachtrag Fassung 4** (26.10.2026 abends, nur gelesen, nichts geändert):
- `main` steht auf **339a30a**: #33 (Paket F) und #34 (Paket D) sind gemergt,
  `SCHEMA_STAND = "a14acef69fae"`. `tests/test_db_upgrade.py` geht dort schon auf ausdrückliche
  Revisionen (`VOR_TOKEN`, :277); unter `tests/` gibt es kein `downgrade -1` mehr.
- 10b-1 (`feat/web-oberflaeche`) hat `main` in **2de9a1b** zusammengeführt. Es kettet
  `d5a849692843_add_kontierung` auf `a14acef69fae` und `e7153706b43a` darüber; `SCHEMA_STAND`
  ist dort `e7153706b43a`.
- 10b-1 ist **noch nicht auf `main`**. Im Worktree liegen ungesicherte Änderungen, u. a. an
  `buchung/pruefschlange.py` und `api/rest/laeufe.py`.
- `test_migration_web.py:92–95` setzt auf 2de9a1b weiter `SPRACHE` als Kopf voraus; die
  Umstellung in Schritt 3 bleibt.
- Zwischen 43031a7 und 2de9a1b haben sich unter `api/` nur `seiten/pruefen.py` (ab :695,
  Regelvorschau) und `pruefen/_regelvorschau.html` (eine msgid) geändert. Die übrigen Zeilenangaben
  dieses Plans gelten weiter.

Für P1 folgt daraus nichts Neues: `K` liest Schritt 0 aus `alembic heads`, voraussichtlich
`e7153706b43a`. Schritt 3 prüft, welche kopfrelativen Tests dann noch übrig sind; der Wächtertest
bleibt.

### Was 10a und 10b-1 für P1 liefern

- **Registry** (`api/registry.py:21`): `Navigationspunkt(titel, pfad, recht=Recht.LESEN,
  reihenfolge=100)`; `navigation(module)` sortiert; `app.state.navigation` (Tests ersetzen sie,
  `tests/test_api_app.py:55`). Einträge heute: Übersicht `/` (0), Prüfen `/pruefen` (10),
  Freigaben `/freigaben` (50, **`Recht.LESEN`**, `seiten/freigaben.py:44`).
- **Rendern** (`api/vorlagen.py:117`): `seite(request, vorlage, werte, status)` ist **synchron**,
  setzt `navigation` (gefiltert nach `a.darf`), `sprache`, `htmx_konfig`, `hx_kopf`, `pfad`; **19**
  Aufrufe in `app.py` (3) und `seiten/*.py` (16), zwei davon in synchronen Hilfsfunktionen
  (`anmeldung._formular`, `pruefen._antwort`), die mit `async seite()` selbst `async` werden.
  Fragmente (`pruefen/_arbeitsflaeche.html`) laufen durch dieselbe Funktion. Die GET-Seiten aus
  10a/10b liefern auch mit `HX-Request` die ganze Seite (nur die Arbeitsfläche hat zwei Formen,
  `api/htmx.ist_htmx`). Filter `betrag`, `euro`, `datum`, `prozent`, `monat`, `uebersetzt`, `iban`.
  Die Vorlagen importieren ihre Makros auf **oberster Ebene** (`{% import "_makros.html" as m
  with context %}` in `buchungen/buchung.html:2`, `pruefen/liste.html:2`, `pruefen/regeln.html:2`);
  `_` ist ein Jinja-Global (`install_gettext_callables`), die Umgebung nutzt `StrictUndefined`.
- **Datenbanken je Gesellschaft** (`api/dienste.py:61–67`): `_fabrik(url)` legt Engine und
  `init_db` (also `create_all`) **unter der globalen Sperre** `_sperre` an und merkt sich keinen
  Fehlschlag. SQLite wartet bis zu 30 s auf eine Sperre (`db/__init__.py:93`), PostgreSQL hat
  kein `connect_timeout`. Eine fehlende SQLite-Datei in einem vorhandenen Ordner legt
  `create_all` still neu an.
- **Gerüst** (`vorlagen/basis.html`): Kopfleiste mit Navigation, Auswahlliste der Gesellschaft mit
  Knopf, Sprachauswahl mit Knopf „Übernehmen“ (`POST /einstellungen/sprache`, :38), Benutzername,
  Abmelden; im Inhalt zusätzlich „Gesellschaft: **…**“ (:59); `<title>{% block titel %}… ·
  accounti`; Fehlerhinweis `#netzhinweis` für htmx.
- **Stile:** `statisch/accounti.css` (62 Zeilen, Dunkelmodus nur über `prefers-color-scheme`,
  **kein `color-scheme`** → Befund I9; `[hidden] { display: none !important }` in :55, auf das
  `pruefen.js` baut), `statisch/pruefen.css` (52 Zeilen; Label-Spalte `9rem`, :19 → I11; Umbruch
  bei `60rem`; **ohne `@layer`**, mit denselben Klassennamen wie die künftigen Komponenten –
  `.reiter` :3–4, `.knopf` :5, `.hinweis` :24, `.haken` :31–32, `.unsichtbar` :41 – und den alten Token `--gedaempft`,
  `--hintergrund`; eingebunden über `{% block kopf %}` von fünf Vorlagen). Kein Sprite, keine
  Komponenten außer
  `vorlagen/_makros.html` (`konto`, `schluessel`, `meldung_text`, `fehlerkasten`, `feldfehler`).
- **Formulare mit mehreren Codefeldern:** `/buchungen/{id}` hat zwei Formulare und nutzt dafür
  `grund-k`/`grund-s`, `datum-k`/`datum-s`, `code-k`/`code-s` (`buchungen/buchung.html:65–83`);
  `/freigaben` hat ein Codefeld je Lauf und eines für die USt-VA (`freigaben.html:23, 62`). Die
  Anmeldung ist **ein** Formular mit Benutzer, Passwort, Code und verstecktem `weiter`
  (`anmelden.html:6–15`).
- **Skript** `statisch/pruefen.js` (168 Zeilen): Tasten `j k f e r z b ?`, Fehlerhinweis für
  `htmx:responseError`/`sendError`; Abschaltung der Tasten in **`localStorage`** (:15–33);
  Strg+Enter in einem Feld löst `button.hauptknopf` des Formulars aus (:98, Knopf „Korrigieren“
  in `pruefen/_korrektur.html:51`; geprüft in `test_api_statisch.py:184` und
  `test_api_pruefen.py:341`).
- **htmx** 2.0.11 lokal mit Prüfsumme und Konfiguration (`HTMX_KONFIG`, `vorlagen.py:85`):
  `allowEval:false`, `selfRequestsOnly:true`, `responseHandling` tauscht 409/422 ein. Bleibt
  unverändert (A115).
- **Fehlerwege** (`api/app.py`): `nicht_angemeldet` (:85, mit `HX-Redirect`), `http_fehler` (:104)
  rendert `meldung.html` **ohne `h1`**, `ungueltig` (:122) 422, `beschaeftigt` (:133) 503. Eine
  unbehandelte Ausnahme beantwortet die Middleware mit `PlainTextResponse("Interner Fehler", 500)`
  (`api/sicherheit.py:102`).
- **403 der Rolle** (`api/sitzung.py:142–155`): „Ihre Rolle in %(gesellschaft)s erlaubt das nicht“ –
  **ohne** das fehlende Recht. A9/AK48 verlangen, dass 403 die fehlende Rolle nennt.
- **Sprache am Benutzer:** Spalte `auth_benutzer.sprache` (`db/tabellen_auth.py:58`),
  `auth/dienst.setze_sprache` (:147), `api/seiten/sprache.py`, Schemaprüfung beim Start über
  `PFLICHTSPALTEN = {"auth_benutzer": ("sprache",)}` (`api/dienste.py:40`), Abbruch von `serve`
  mit Exit 2 (`tests/test_api_schema.py:34`). Die Meldung nennt nur die erste fehlende Spalte und
  als Weg `alembic upgrade head` (`dienste.py:80–101`, Test :39) – bei einer Datenbank ohne
  Versionsvermerk führt genau das zu „table … already exists“ (Befund Betrieb B2, den Paket A mit
  `accounti db upgrade` löst).
- **Sitzung lesen schreibt:** `sitzung._lade` → `auth.dienst.pruefe_sitzung` beendet abgelaufene
  Sitzungen und markiert die Sitzung höchstens alle 60 s als aktiv (`auth/dienst.py:618–621`),
  über `Dienste.system()` (`_fabrik`, SQLite wartet bis zu 30 s auf eine Sperre).
- **Tests als Gerüst für die Querschnittsregeln:** Rechte-Matrix `SEITEN` und `MIT_EINMALCODE`
  (`tests/test_api_rechte_matrix.py`), CSRF über alle POST der Registry (`tests/test_api_csrf.py`),
  Vorlagen-Scan gegen Inline-Code (`tests/test_api_statisch.py:138`), Katalogtests
  (`tests/test_i18n_katalog.py`: Vorlagen per `extract_translations`, `_`/`N_`/`Text` unter `api/`
  per AST), Protokolltest (`tests/test_betrieb_protokoll.py`), Akzeptanz-5-Test
  (`tests/test_api_gesellschaften.py:36`), Testwelten `tests/api_hilfe.webwelt` (**zwei**
  Gesellschaften, `api_hilfe.py:145`) und `tests/pruefen_hilfe.queuewelt` (jan buchhalter, fritz
  freigeber, leo betrachter, vera verwalter). Die Testhelfer `formularwert` und `freigabe_hash`
  (`tests/api_hilfe.py:105–108`, `:131–140`) suchen `name="…" value="…"` direkt hintereinander.
- **Benutzer schreiben:** `repo_auth.speichere_benutzer` schreibt **alle** Felder aus
  `_BENUTZER_FELDER` zurück (`db/repo_auth.py:70–73`); `setze_sprache` ändert dagegen gezielt
  nur `sprache` (`auth/dienst.py:147–157`).

### Befunde im Quelltext, die den Plan bestimmen

| # | Befund (Beleg) | Folge für P1 |
|---|----------------|--------------|
| B1 | `seite()` ist synchron und kennt keine Datenbank; die Zähler der Navigation (A2, A3, A4) brauchen die Datenbank der Gesellschaft. Datenbankzugriffe laufen in 10a/10b immer im Threadpool | `seite()` wird `async` und holt die Zähler in einem Thread (eigener Pool des Lesezugriffs), **nur** für ganze Seiten (Entscheidung „Zähler“) |
| B2 | `Navigationspunkt.recht` ist ein einzelnes Recht; „Freigaben“ braucht künftig `ZAHLUNG_FREIGEBEN` **oder** `STEUER_FREIGEBEN` (A2) | `recht: Recht \| frozenset[Recht]` („eines genügt“), dazu `bereich`, `symbol`, `zaehler`, `kurztitel` |
| B3 | Die einzige Seite des Bereichs „Belege“ ist `/belege/{beleg_id}` (mit Parameter); Bereiche ohne eigene Seite fallen nach A2 weg | vor P3 erscheinen nur Übersicht, Prüfen, Freigaben; AK6/AK44 werden mit einer Test-Registry (Stub-Seiten für Belege, Steuern, Auswertungen, Einstellungen) in den Zahlen der Spec geprüft |
| B4 | `Firma` (`konfiguration.py:61`) verlangt einen vollständigen `mandant`; `mandant.kennfarbe` gibt es erst mit P4 (A124), die Wahl erst mit P5 | P1 leitet die Kennfarbe aus dem Kürzel ab (stabil, ohne Dopplung); die gewählte Farbe kommt mit P5 über den Abschnittsleser dazu. P1 liest keine YAML selbst (sonst stünde ein neues `yaml.safe_load` gegen den AST-Test von P4) |
| B5 | Tastenkürzel-Abschaltung in `localStorage` (`pruefen.js:15–33`), AK45 verbietet das | Wert am Benutzer, Skript liest `document.body.dataset.tastenkuerzel` |
| B6 | Anmeldung: ein Feld „Einmalcode aus der App oder Wiederherstellungscode“ mit `inputmode="text"` (`anmelden.html:13–14`); Freigaben: Codefeld nur mit Platzhalter und `aria-label` (`freigaben.html:23`, :62 → I10) | ein Codefeld-Baustein: `inputmode="numeric"`, sichtbares Label, Link „Wiederherstellungscode verwenden“ auf dieselbe Seite mit `?code=wiederherstellung` (Textfeld, ohne JS) – auf Anmeldung, `/freigaben`, `/buchungen/{id}` (A109). Der Link trägt `weiter` mit und steht beim Label, vor dem Feld (B17) |
| B7 | `/freigaben` schachtelt die Zahlungstabelle in eine Zeile der Lauftabelle (`freigaben.html:28–44`) – als Karte unter 40rem nicht sinnvoll umzubrechen | P1 ordnet nur das Markup: je Lauf ein Abschnitt mit Angaben, Zahlungstabelle (Komponente) und Formular. Karten mit `<details>` und Zeitraum-Auswahl bleiben P2 (A126) |
| B8 | 500 ist Klartext ohne Design, `meldung.html` hat kein `h1` | eigene Vorlagen `fehler.html` (mit Gerüst) und `fehler_500.html` (schlicht, ohne Datenbank) |
| B9 | Tests prüfen Markup, das P1 entfernt: „Gesellschaft: <strong>…</strong>“ (`test_api_gesellschaften.py:58`, `test_akzeptanz_web.py:338`, `test_api_sprache.py:33, 37, 122–123`), „Approvals“ in der Navigation für jan, der buchhalter ist und kein Freigaberecht hat (`test_api_sprache.py:34`), `r.text == "Interner Fehler"` (`test_api_htmx.py:136`), Freigaben für den betrachter in der Navigation (`test_api_app.py:69`), der Haken der Tastenhilfe (`test_api_statisch.py:174` liest `pruefen.js`; `test_api_pruefen.py:326` verlangt `id="tasten-aus"`), Katalogeintrag „Gesellschaft: <strong>…“ als Beispiel (`test_i18n.py:62`) | **umgestellt**, nicht gelöscht: dieselbe Absicht an der neuen Stelle (Kopfleiste, `<title>`, Fehlerseite, Formular statt Haken). Die Liste steht im PR (AK49), abgeglichen per `pytest --collect-only` zwischen `main` und Branch (Schritt 15) |
| B10 | Migrationstests gehen vom **Kopf** aus: 10b-1 mit `downgrade -1` und der Sprachspalte (`test_migration_web.py:130–144`), `test_ein_kopf_nach_ddc9a184ddb4` erwartet `e7153706b43a` als Kopf (:88–92); Paket A mit `downgrade -1` in `test_db_upgrade.py:201`, `:227`, `:280`, `:289` (`:227`/`:280` erwarten die Abweisung dieses Schritts – mit einer Migration darüber werden sie rot, nachgestellt mit einer leeren Migration auf 87c6c8d: `:227` scheitert; `:280`/`:289` laufen nur mit PostgreSQL, die CI hat keinen solchen Dienst); F in `test_migration_anlagen_buchung.py:35`. Paket A verlangt `get_heads() == [SCHEMA_STAND]` (`test_db_upgrade.py:61–67`) und prüft den Vermerk nach `db init` und nach einer Wiederherstellung | **Kein Migrationstest hängt am Kopf** (Muster Paket D, `test_migration_verrechnungen.py:20–28`): die eigene Revision als Konstante (`VORLIEBEN = "<rev>"`), der Vorgänger als `get_revision(VORLIEBEN).down_revision` (`VOR`), Downgrades auf ausdrückliche Revisionen, „genau ein Kopf“ **nur** über den Test aus Paket A, Vermerke gegen `SCHEMA_STAND`. Die kopfrelativen Tests anderer Pakete, die beim Abzweigen auf `main` stehen, stellt P1 im Migrations-Commit auf dasselbe Muster um (umgestellt, AK49); ein Wächtertest hält die Regel für alle Pakete (Schritt 3). `SCHEMA_STAND = "<rev>"` im Migrations-Commit |
| B11 | Playwright und axe-core sind nicht im Projekt; die Spec-Probe lief mit einem fremden `node_modules` (`/opt/noro-craft/…/playwright@1.59.1`). AK60 erlaubt in `pyproject.toml` keine neue Abhängigkeit | Browserprobe als eigenes Node-Werkzeug unter `scripts/browserprobe/` mit festen Versionen und Lockdatei, nicht in `pyproject.toml`, nicht im Abbild (Entscheidung „Browserprobe“) |
| B12 | Die Spec verlangt für A6 „mit htmx genügt die Auswahl“. Optionsfelder wechseln mit den Pfeiltasten die Auswahl; ein Absenden bei `change` lüde die Seite schon beim ersten Pfeil neu (Tastatur- und Screenreader-Nutzer kommen nicht zur dritten Option) und wäre ein Kontextwechsel bei Eingabe (WCAG 3.2.2, Stufe A) | **Abweichung:** immer mit Absendeknopf, auch mit htmx (Entscheidung „Vorlieben“); im PR und in der Spec vermerken |
| B13 | A4 zählt für die schmale Kopfleiste nur Kennfarbe/Kürzel, Seitentitel und Benutzersymbol auf; A8 und AK47 verlangen den Hilfe-Link „auf jeder Seite an derselben Stelle der Kopfleiste“ (WCAG 3.2.6) | **Ergänzung:** Hilfe-Symbol (44 × 44, `aria-label`) auch in der schmalen Kopfleiste, vor dem Benutzersymbol; passt in 56 px Höhe und 320 px Breite |
| B14 | `/gesellschaft` liest Zähler aus **allen** Gesellschafts-Datenbanken. Über `Dienste._fabrik` hielte jede Verbindung die globale Sperre (`dienste.py:61–67`); eine hängende PostgreSQL-Verbindung blockierte alle Anfragen, eine fehlende SQLite-Datei entstünde neu | eigener **Lesezugriff** (`api/lesezugriff.py`) für alle Zähler: Engine ohne `init_db`, nur lesend, SQLite nur bei vorhandener Datei (`mode=ro`, `timeout` 2 s), PostgreSQL mit `connect_timeout` 3 s und `statement_timeout` 2 s, Engine-Aufbau außerhalb jeder globalen Sperre, Gesamtfrist je Gesellschaft (Entscheidung „Zähler“) |
| B15 | Die Fehlerwege rendern über `seite()` (`app.py:104–157`); mit Zählern fragte gerade die 503-Seite die gesperrte Datenbank | `seite(…, zaehler=False)` für 403, 404, 409, 413, 422 und 503; Zähler nur für ganze Seiten mit Status < 400 |
| B16 | Zwei Formulare auf einer Seite brauchen eigene IDs (`grund-k`/`grund-s`, `code-k`/`code-s`), `/freigaben` hat mehrere Codefelder; `StornoError.feld` heißt `grund`, das Feld aber `grund-k` | `feld`, `codefeld`, `optionen` und `haken` bekommen einen Parameter `id` (Standard: der Name); `fehlerliste(fehler, ids)` bildet Feldname → id ab; Test „IDs je Seite eindeutig“ über alle Seiten |
| B17 | Der Link „Wiederherstellungscode verwenden“ lädt die Seite neu; ohne Durchreichen ginge `weiter` verloren, Benutzer und Passwort sind weg | Link mit `weiter`, sichtbar beim Code-Label vor der Eingabe; der Verlust der Eingaben steht unter Grenzen (WCAG 3.3.7, Ausnahme für sicherheitsrelevante Angaben) |
| B18 | `speichere_benutzer` schreibt alle Felder zurück; ein vorher geladener `Benutzer` überschriebe beim Speichern frisch gesetzte Vorlieben | Vorlieben **nur** über `setze_vorlieben` (gezieltes `UPDATE` wie heute `setze_sprache`); `speichere_benutzer` schreibt sie und `sprache` bei bestehenden Zeilen nicht (nur beim Anlegen) |
| B19 | Ein Block allein (`Template.blocks["inhalt"]`) läuft ohne den Code auf oberster Ebene der Vorlage: Importe und `{% set %}` dort fehlen, `super()` findet keinen Elternblock – mit `StrictUndefined` ein `UndefinedError` (nachgestellt mit Jinja 3.1.6: `'k' is undefined`, `there is no parent block called 'inhalt'`); die Bestandsvorlagen importieren oben (siehe „Rendern“) | Regel für jede Vorlage mit `teil`: auf oberster Ebene nur `extends` und Blöcke, Importe **im** Block `inhalt`, kein `super()` darin; `seite(…, teil=…)` prüft das selbst (Entscheidung „Zwei Formen“) |
| B20 | `pruefen.css` hat keine Ebene; Regeln ohne Ebene schlagen jede `@layer`-Regel, und `.knopf`, `.reiter`, `.hinweis`, `.haken` heißen wie die Komponenten; die Datei nutzt `--gedaempft` und `--hintergrund`, die es ab Schritt 1 nicht mehr gibt | in Schritt 1 die alten Regeln (aus `accounti.css` und `pruefen.css`) in eine Übergangsebene `bestand` **vor** `komponenten`, Token umgeschrieben; Schritt 12 leert sie Seite für Seite (Entscheidung „Eine CSS-Datei“) |
| B21 | Strg+Enter sucht `button.hauptknopf` (`pruefen.js:98`); Schritt 12 rendert Knöpfe über `knopf()`, „Korrigieren“ ist dort sekundär | Kennzeichen unabhängig von der Optik: `data-hauptknopf` über `attribute`, Skript sucht `button[data-hauptknopf]` (Schritt 9) |
| B22 | Der Starthinweis nennt `alembic upgrade head` (`dienste.py:80–101`), das bei Datenbanken ohne Vermerk scheitert (Befund Betrieb B2) | die Meldung nennt `accounti db upgrade` und alle fehlenden Spalten, `alembic upgrade head` bleibt als Gleichwert für Datenbanken mit Vermerk genannt (AK61) |
| B23 | `vielleicht_angemeldet` liest **und schreibt** die Systemdatenbank (`pruefe_sitzung`, siehe „Sitzung lesen schreibt“); im 404-Handler würde ein „database is locked“ zur 500 | bei Datenbankfehlern gilt die Anfrage als nicht angemeldet (schlichtes Layout), Protokoll nur die Art (Entscheidung „Fehlerseiten“) |
| B24 | Das Registry-Kürzel einer Gesellschaft ist ein Kennwort mit bis zu 30 Zeichen (`a–z`, `0–9`, `_`, `-`; `models/auth.pruefe_gesellschaft`, Beispiele `muster`, `tochter`, in den Tests `a`/`b`). Die Leinwand zeigt dagegen ein Monogramm aus zwei Großbuchstaben („GD“, „KU“) in einem Quadrat von 28 px – ein Kennwort passt dort nicht hinein (Fassung 4) | **Monogramm** aus dem Namen, in der Registry eindeutig (`geruest.monogramme`, Schnittstelle). Das Registry-Kürzel bleibt Schlüssel und steht in `data-gesellschaft` (L7 Nr. 18) |

### Abgrenzung

| Thema | P1 (dieser Plan) | später |
|-------|------------------|--------|
| Token, Komponenten, Musterseite, Symbole | **neu**, nach der Leinwand (L1–L6, L9) | alle Pakete nutzen sie; neue Komponenten nur mit Eintrag auf `/muster` (AK51) |
| Zeichenflächen der Leinwand | Gerüst, Komponenten, Layouts, `/menue` vollständig, `/muster`; Optik der Bestandsseiten (L8) | Übersicht-Karten mit Daten P2, Prüfschlange neu P3, Einstellungen P5, Assistent P7 (L8) |
| Navigation, Kopfleiste, untere Leiste, `/menue`, `/gesellschaft`, Hilfe, Fehlerseiten | **neu** | P2 trägt Steuern (`/steuern/fristen`) und ggf. Aufgaben ein, P3 Belege, P5 Einstellungen, 10b-2 Auswertungen – je mit Hilfeseite |
| Zähler der Navigation | Prüfen (offene Vorschläge), Freigaben (Zahlungsläufe im Entwurf) | P2: USt-VA im Freigaben-Zähler (A126); P3: Belege zur Prüfung |
| Mein Konto | Vorlieben (`/konto`, `POST /konto/vorlieben`) | P6: Passwort, Faktor, Codes, Sitzungen (A87) |
| Fachansicht, Beträge verbergen | gespeichert und im Gerüst verfügbar (`geruest.fachansicht`, `geruest.betraege_verbergen`) | Wirkung: P3 (A27), P2 (A18) |
| Kennfarbe und Monogramm | Farbe aus dem Kürzel abgeleitet, Werte aus der Leinwand (L1), Klassen `marke-1` … `marke-6`; Monogramm aus dem Namen (B24) | Wahl `mandant.kennfarbe`: Feld P4 (A124), Formular und Verdrahtung P5; ein wählbares Monogramm kann P5 ergänzen |
| Bestehende Seiten | neues Gerüst, Komponenten, Token; I1, I8–I12 behoben; **keine** neue Bedienung | P3: Prüfschlange neu (I2–I5), P2: Freigaben-Karten (A126) |
| Migration | `auth_benutzer`: vier Vorlieben-Spalten | P4 `einstellungen` …, P5 `verwaltung_bis` …, P6, P7 (A118) |

---

## Recherche (Stand 26.10.2026)

| Thema | Ergebnis | Quelle |
|-------|----------|--------|
| **Lucide-Symbole** | Paket `lucide-static`; `latest` = 1.61.0 (21.10.2026), 1.56.0–1.61.0 sind jünger als zwei Wochen. Gewählt **1.55.0**, veröffentlicht **2026-10-10T07:06:58Z** (16 Tage). Lizenz **ISC**; die `LICENSE` im Paket nennt zusätzlich die von Feather abgeleiteten Symbole unter **MIT** („Copyright (c) 2013-present Cole Bemis“), mit den **alten Feather-Namen**. Von den 36 gewählten (Fassung 4, L6) fallen darunter `arrow-down`, `arrow-right`, `arrow-up`, `calendar`, `check`, `chevron-down/-left/-right`, `download`, `external-link`, `info`, `lock`, `log-out`, `monitor`, `moon`, `search`, `upload`, `x` sowie unter neuem Namen `triangle-alert` (alt `alert-triangle`), `circle-help` (`help-circle`), `circle-x` (`x-circle`) und `circle-alert` (`alert-circle`); `square-check-big`, `menu` und `shield-check` stehen nicht in der Liste (am 26.10.2026 an `package/LICENSE` geprüft). Tarball `lucide-static-1.55.0.tgz`: npm-Integrität `sha512-h18lunTFsIJWnY0FMRPjXeO9KcAtNi7fDqtqgWHOFbssfgUWsctn/pA7bpiyrd4g1DuBOJ24CsRnPfkYblwm/A==` (nachgerechnet, stimmt), `shasum` `12e5674d15cb258ca10e5ec8ff039ed602886d44`, SHA-256 `809e2e759aeecd05ef3abc231395a0ccb6a58169823cbd26a425960b4d282797`, 2 141 Symbole unter `package/icons/`. Probe-Sprite aus den 36 gewählten Symbolen (Wurzelattribute in CSS, Formen unverändert): **6 443 Bytes** (Fassung 3: 37 Symbole, 6 829 Bytes) | npm-Registry (`registry.npmjs.org/lucide-static/1.55.0`, per WebFetch und `curl` gelesen), Tarball in eigenem Ordner geladen und nachgerechnet, nicht ausgeführt |
| **axe-core** (nur Entwicklung) | `latest` = **4.14.0**, veröffentlicht **2026-10-05T17:43:36Z** (21 Tage). Lizenz **MPL-2.0** (Datei-Copyleft; unverändert benutzt, nicht ausgeliefert). Integrität `sha512-9WTZxEjsZ7b13TH8JPmbV2z8CHbl80/2hm3XPEG4JgNdQLK81IBRXmSxHfMAOkSqQeRxT/0dwNDz2GOm3zzpcQ==` (stimmt), `shasum` `a9819d3932a8198fbe935d8cbd8afcdfecbcf31d`; `package/axe.min.js` 652 140 Bytes, SHA-256 `20c09fe157a8a34a30e241aaa1fcdade657734f08ab379ecfbeb7d45cc46e878`; keine Abhängigkeiten | npm-Registry (WebFetch, `curl`), Tarball nachgerechnet |
| **Playwright** (nur Entwicklung) | `latest` = 1.64.1 (14.10.2026, 12 Tage – zu jung). Gewählt **1.64.0**, veröffentlicht **2026-10-07T20:42:55Z** (19 Tage), **Apache-2.0**, Integrität `sha512-kVzTnYFYEyQ9RGzBjNCd2+yEqWmVbxl3AHPynv3qQ6JTjv4a+kwRcnqQwIpuP3NnrnIrE/Q6wWAIAvMfIE2/Yg==` (stimmt); einzige Abhängigkeit `playwright-core` 1.64.0 (2026-10-07T20:44:22Z, Apache-2.0, `sha512-T9r+MZkTECl2+oUcZ26YgZzTrYidTsIhYYkJix+6iDOymOb1FB2RLLSOxRGnZGv5DStt+aduIVbt+E8WygXYpg==`). `playwright-core@1.64.0/browsers.json` verlangt **Chromium-Revision 1248** (Chrome for Testing 156.0.8078.4) samt Headless-Shell 1248 und Firefox 1555. Auf dem Server liegen nur die Chromium-Builds **1217/1223** unter `~/.cache/ms-playwright` (je rund 370 MB plus 260 MB Headless-Shell entpackt), **kein Firefox**. Für 1.64.0 muss `npx playwright install chromium` die Browser also **auch auf dem Server** von Microsofts CDN laden; das sichert die Lockdatei nicht ab und geschieht nur nach Freigabe durch den Nutzer. **Rückfall:** `playwright` 1.59.1 (2026-04-01T17:58:48Z, Apache-2.0, `sha512-C8oWjPR3F81yljW9o5OxcWzfh6avkVwDD2VYdwIGqTkl+OGFISgypqzfu7dOe4QNLL2aqcWBmI3PMtLIK233lw==`; `playwright-core` 1.59.1 `sha512-HBV/RJg81z5BiiZ9yPzIiClYV/QMsDCKUyogwH9p3MCP6IYjUFu/MActgYAvK0oWyV9NlwM3GLBjADyWgydVyg==`) nutzt Chromium 1217, das schon da ist (1223 gehört zu einer Vorabversion von 1.60.0, keine Wahl). Node 24.14.1, npm 11.11.0 | npm-Registry (WebFetch, `curl`, für 1.59.1 am 26.10.2026 per `curl` gelesen), `browsers.json` aus dem geprüften Tarball, lokaler Rechner |
| **htmx** | unverändert `latest` = 2.0.11 (2026-09-22), `next` = 4.0.0 (Versionssprung, nicht verwenden) | npm-Registry |
| **Browserunterstützung** | `@layer` (Chrome 99, Firefox 97, Safari 15.4), `:focus-visible` (Chrome 86, Firefox 85, Safari 15.4), `color-scheme`-Eigenschaft und `<meta name="color-scheme">` (alle aktuellen), `env(safe-area-inset-*)` mit `viewport-fit=cover`, `scroll-padding` beim Fokussieren (Chromium, Firefox, Safari), `content: attr(x) / ""` (Alternativtext für erzeugten Inhalt: Chrome 77, Firefox 128, Safari 17.4; ältere lesen den Text doppelt vor). `light-dark()` erst ab Safari 17.5 – **nicht** genutzt, weil ältere Geräte dann gar keine Farben hätten. Für die Leinwand (Fassung 4): `:has()` (Chrome 105, Safari 15.4, Firefox 121) für Optionskarte und Wahlpillen, ohne es bleibt die Auswahl am Optionsfeld sichtbar; `overflow: clip` (Chrome 90, Firefox 81, Safari 16) für Tabellenrahmen, davor `hidden` als Rückfall; `<progress>` färbbar über `::-webkit-progress-bar`/`-value` und `::-moz-progress-bar`; `accent-color` (Chrome 93, Firefox 92, Safari 15.4) | MDN Browser Compat Data (Stand der Recherche-Session), Entscheidung „Token“ |
| **WCAG 2.2** | 2.4.11 Fokus nicht verdeckt, 2.5.7 Ziehen, 2.5.8 Zielgröße 24 × 24, 3.2.6 konsistente Hilfe, 3.3.7 keine doppelte Eingabe, 3.3.8 zugängliche Anmeldung (Einfügen, kein Abtippen); 3.2.2 Bei Eingabe (Stufe A) – Grund für B12; 1.4.10 Reflow nimmt Datentabellen aus, P1 bricht sie trotzdem zu Karten um (AK1 verlangt kein waagrechtes Scrollen) | Spec 13.4, W3C |
| **Kontraste** | Token der Spec nachgerechnet (WCAG-Leuchtdichte): alle Paare der Tabelle A89 erreichen die angegebenen Werte; zusätzlich geprüft: `--linie-stark` auf `--flaeche-2` 3,41 / 3,36, `--fokus` auf `--flaeche-2` 4,04 / 8,62 und auf `--akzent-flaeche` 4,00 / 7,82, `--text-2` auf `--akzent-flaeche` 5,65 / 6,16, Text auf allen Statusflächen ≥ 12,4, Nebentext dort ≥ 5,6, Akzent (Links) dort ≥ 6,4. **`--fokus` neben `--akzent` nur 1,61 / 1,11** – deshalb liegt der Fokusring immer mit 2 px Abstand auf der Fläche, nie direkt am primären Knopf. Fassung 4: neue Token, Kennfarben der Leinwand, gewählte Zeile, Hover und `kbd` nachgerechnet, Werte in L1 | Skript im Scratchpad (`lw-skript/kontrast.py`), Werte im Test festgehalten |
| **Design-Leinwand** | zehn Zeichenflächen gelesen; Token in allen gleich (27 Token, 54 Werte); gerendert mit `playwright-core` 1.59.1 und Chromium 1217 aus dem npx-Cache (`~/.npm/_npx/e41f203b7505f1fb`), hell und dunkel, 20 Bilder, kein waagrechtes Scrollen. Python-Playwright ist im venv **nicht** vorhanden (`/opt/accounti/.venv`, geprüft) | L0, L10 |

---

## Design-Leinwand (Fassung 4)

Dieser Abschnitt übersetzt die freigegebene Leinwand in Token, Maße, Komponenten und Layouts. Er
ist für das **Aussehen** maßgeblich. Wo er einer Anforderung der Spec widerspricht, gilt die Spec;
L7 sagt dann, wie das Aussehen trotzdem erreicht wird. Die übrigen Abschnitte verweisen mit
„L0“ … „L10“ hierher.

### L0 Quelle, Freigabe, Lesart

- **Leinwand** „accounti Oberfläche“ (Claude Design, `canvas.json` v3, zehn Zeichenflächen).
  Freigabe des Nutzers am 26.10.2026: „Die Richtung passt. Setz das Design so in Baustein 10c
  um.“ Beim Planen gelesen aus dem Scratchpad (`…/design-accounti/project/`). Im Repository legt
  Schritt 0 sie unter `docs/design/2026-10-26-leinwand/` ab, damit P2–P7 dieselbe Vorlage haben.
- **Format:** `<x-dc>` mit Stilen in `<helmet><style>`: Token als CSS-Variablen auf `.a`, dunkel
  auf `.a.dunkel`. Alles andere steht als Inline-`style=` im Markup; dazu Platzhalter `{{…}}`,
  `sc-if`/`sc-for` und Klicklogik in `DCLogic`. **Maßgeblich** sind Aussehen, Abstände, Farben,
  Komponenten und Texte – nicht Markup, Inline-Stile oder Skriptlogik.
- **Gelesen** wurden alle zehn Zeichenflächen vollständig. Die Token sind in allen Flächen gleich:
  27 Token mit je einem hellen und dunklen Wert (54 Werte); ein Skript fand keinen Widerspruch. Außerhalb der Tokenblöcke steht kein
  Farbliteral. **Gerendert** wurde am 26.10.2026 mit `playwright-core` 1.59.1 und Chromium 1217 aus dem
  npx-Cache: je Zeichenfläche hell und dunkel in ihrer Breite (1440 bzw. 390 px), ohne
  `support.js` (`{{theme}}` per `sed` ersetzt). Ergebnis: 20 Bilder, `scrollWidth` überall gleich
  der Fensterbreite. Die Bilder zeigen außerdem zwei Mängel (Beträge und Status-Pillen brechen in
  schmalen Karten um); sie stehen in L7.

| Zeichenfläche | Größe | Inhalt | wer baut |
|---|---|---|---|
| `Main` | 1440 × 1040 | Übersicht Desktop: Kopfleiste, Seitenleiste mit Zählern, „Heute zu tun“ (sechs Karten), „Erledigt“, andere Gesellschaften, Kennzahlen | Gerüst, Karte, Raster **P1**; Inhalte **P2** |
| `Pruefen-Liste` | 1440 × 1120 | Reiter, Gruppen mit Sammelfreigabe, Tabelle mit Auswahl, Sammelleiste | Reiter, Tabelle, Komponente Sammelleiste **P1**; Gruppen, Auswahl, Zeilenaktionen **P3** |
| `Pruefen-Arbeitsflaeche` (klickbar) | 1440 × 940 | Prüfschlangen-Leiste; Beleg und Vorschlag; drei Schritte (Vorschlag → „Welches Konto passt?“ → „Künftig immer so?“ → Erledigt) | zweispaltiges Layout und Optik der Bestandsseite **P1**; Abläufe und Fokusleiste **P3** |
| `Handy-Uebersicht` | 390 × 844 | schmale Kopfleiste, Karten untereinander, untere Leiste | Kopf, untere Leiste **P1**; Karten **P2** |
| `Handy-Pruefen` (klickbar) | 390 × 844 | Prüfschlangen-Leiste, Reiter Vorschlag/Beleg, Aktionsleiste | Komponente Aktionsleiste **P1**; Seite **P3** |
| `Handy-Freigaben` | 390 × 844 | je Freigabe eine Karte mit Betrag, Aufklapper, Codefeld | Karten-Optik der Bestandsseite **P1**; Aufklapper und USt-VA-Werte **P2** (A126) |
| `Handy-Mehr` | 390 × 844 | `/menue`: Bereiche, Gesellschaft, Mein Konto | **P1** vollständig |
| `Assistent-Steuern` | 1440 × 1200 | schlichter Kopf, Schrittliste mit Fortschritt, Formular mit Optionskarten, Wahlpillen, Prüfhinweisen am Feld | Komponenten **P1**; Seite **P7** |
| `Einstellungen-Firma` | 1440 × 1320 | Brotkrumen, Unternavigation, Abschnittskarten, Wahl der Kennfarbe, Jahrestabelle | Layout und Komponenten **P1**; Seite **P5** |
| `Bausteine` | 1440 × 1480 | Farben, Schrift, Knöpfe, Status, Sicherheit, Felder, Hinweise, Tabelle, leerer Zustand – hell und dunkel nebeneinander | `/muster` **P1** (L9) |

### L1 Farb-Token

Werte aus der Leinwand. Die Kontraste sind nach WCAG 2.2 nachgerechnet (Skript im Scratchpad
`lw-skript/kontrast.py`); der Test in Schritt 1 rechnet sie aus `accounti.css` erneut. Die Token
der Spec (A89) stimmen mit der Leinwand **wörtlich** überein. Neu sind `--fehler-text`, `--schatten`
und `--schleier`; bei den Kennfarben ändern sich die Werte.

| Token | hell | dunkel | Zweck | Kontrast hell / dunkel | Stand |
|---|---|---|---|---|---|
| `--grund` | `#f5f4f1` | `#121417` | Seitenhintergrund, Seitenleiste | — | Spec |
| `--flaeche` | `#ffffff` | `#1a1d21` | Kopfleiste, Karten, Tabellen, Felder, untere Leiste | — | Spec |
| `--flaeche-2` | `#efede8` | `#22262b` | Tabellenkopf, neutraler Zähler, deaktivierter Knopf, Fortschrittsspur | — | Spec |
| `--text` | `#1b1f24` | `#e8eaed` | Text | 16,56 / 14,03 auf Fläche; 14,15 / 12,62 auf Fläche 2; 14,02 / 11,46 auf Akzentfläche; ≥ 13,93 / 12,41 auf den Statusflächen | Spec |
| `--text-2` | `#555d66` | `#a7aeb6` | Nebentext, Etiketten, inaktive Reiter und Ziele | 6,68 / 7,55 Fläche; 6,07 / 8,24 Grund; 5,71 / 6,79 Fläche 2; 5,65 / 6,16 Akzentfläche; ≥ 5,62 / 6,68 auf den Statusflächen | Spec |
| `--linie` | `#d6d3cc` | `#33383f` | Trennlinien, Rahmen von Karten und Tabellen, leere Sicherheitskästchen – nur Schmuck | 1,49 / 1,43, trägt nie Bedeutung | Spec |
| `--linie-stark` | `#7a8088` | `#6f7781` | Feldränder, sekundäre Knöpfe, Optionskarten, gestrichelter Leerrahmen, Summenlinie, obere Kante von Sammel- und Aktionsleiste | 3,98 / 3,73 Fläche; 3,62 / 4,07 Grund; 3,41 / 3,36 Fläche 2; 3,37 / 3,05 Akzentfläche | Spec |
| `--akzent` | `#1a5a73` | `#7dc3db` | Primärknopf, Links, aktiver Eintrag, Reiter-Strich, Auswahlrand, Fortschritt (Petrol) | 7,63 / 8,62 Fläche; 6,93 / 9,40 Grund; 6,52 / 7,75 Fläche 2; 6,46 / 7,04 Akzentfläche | Spec |
| `--akzent-text` | `#ffffff` | `#0e1a1f` | Text auf Akzent, auch im betonten Zähler | 7,63 / 9,02 | Spec |
| `--akzent-flaeche` | `#e3eef2` | `#183039` | aktiver Eintrag, gewählte Zeile und Option, Avatar | siehe Zeilen davor | Spec |
| `--fokus` | `#b35c00` | `#ffb366` | Fokusring (Bernstein) | 4,72 / 9,58 Fläche; 4,29 / 10,45 Grund; neben `--akzent` nur 1,61 / 1,11, neben `--fehler` 1,51 / 1,16 → der Ring liegt immer mit 2 px Abstand auf der Fläche | Spec |
| `--ok` / `--ok-flaeche` | `#1d6b3a` / `#e5f2e9` | `#7fd19b` / `#16291d` | Erfolg | 5,66 / 8,40 auf eigener Fläche; 6,53 / 9,26 auf Fläche; 5,53 / 7,56 auf Akzentfläche | Spec |
| `--warn` / `--warn-flaeche` | `#8a5a00` / `#fbf0d9` | `#f0c46a` / `#2e2614` | Warnung, Fristen | 5,24 / 9,13; 5,93 / 10,32; 5,02 / 8,42 | Spec |
| `--fehler` / `--fehler-flaeche` | `#a8241f` / `#fbe7e5` | `#ff9a92` / `#341a19` | Fehler, überfällig, Gefahr-Knopf | 6,01 / 7,87; 7,15 / 8,29; 6,05 / 6,77 | Spec |
| `--info` / `--info-flaeche` | `#1f5fa8` / `#e6eef9` | `#8db8f0` / `#172436` | Hinweis | 5,51 / 7,64; 6,44 / 8,25 | Spec |
| **`--fehler-text`** | `#ffffff` | `#2a0d0b` | Text auf dem Gefahr-Knopf („Stornieren“) | 7,15 / 8,86 auf `--fehler`; die Knopffläche `--fehler` gegen Fläche 7,15 / 8,29, Grund 6,50 / 9,04, Fläche 2 6,11 / 7,46 | **neu** (Leinwand) |
| **`--schatten`** | `0 1px 2px rgba(27,31,36,.05), 0 4px 12px rgba(27,31,36,.04)` | `none` | der eine Schatten (Karten, freistehende Tabellen, Benutzermenü); dunkel nur die Linie (A91) | — | **neu** (Leinwand) |
| **`--schleier`** | `rgb(0 0 0 / .08)` | `rgb(255 255 255 / .08)` | Hover über Knöpfen, Navigations- und Listeneinträgen (`background-image: linear-gradient(var(--schleier), var(--schleier))`) | Text darauf: primär 8,45 / 9,57; gefährlich 7,99 / 9,38; sekundär 13,89 / 11,16; still auf Fläche 6,40 / 6,85, auf Grund 5,78 / 7,63; aktiver Eintrag 5,41 / 5,49 | **neu** (P1; die Leinwand zeigt Hover nur an Links) |
| **`--marke-1` … `--marke-6`** | siehe Kennfarben | | Kennfarbe der Gesellschaft (A5) | siehe Kennfarben | **Werte neu** (Leinwand) |
| `--beleg-hintergrund` | `#ffffff` | `#ffffff` | Rahmen der Belegvorschau | — | Fassung 3 |

**Kennfarben.** Die Leinwand nennt sie `--marke-gd` und `--marke-ku` und bietet in „Einstellungen“
fünf zur Wahl. Die Klassen bleiben `marke-1` … `marke-6` (A5). Das Kürzel steht in `--flaeche` auf
der Kennfarbe.

| Klasse | Farbe | hell | dunkel | gegen Fläche / Grund / Fläche 2 (≥ 3) – hell; dunkel | Kürzel darauf (≥ 4,5) hell / dunkel | Herkunft |
|---|---|---|---|---|---|---|
| `marke-1` | Violett | `#7b3fa0` | `#c79ae6` | 6,86 / 6,24 / 5,86; 7,40 / 8,08 / 6,66 | 6,86 / 7,40 | Leinwand (`--marke-gd`) |
| `marke-2` | Blau | `#1f6fa8` | `#8db8f0` | 5,39 / 4,90 / 4,61; 8,25 / 9,00 / 7,42 | 5,39 / 8,25 | Leinwand |
| `marke-3` | Grün | `#2f7d5b` | `#7fd1ad` | 4,99 / 4,54 / 4,27; 9,36 / 10,21 / 8,42 | 4,99 / 9,36 | Leinwand (`--marke-ku`) |
| `marke-4` | Orange | `#a8551f` | `#f0a46a` | 5,27 / 4,79 / 4,51; 8,23 / 8,98 / 7,41 | 5,27 / 8,23 | Leinwand |
| `marke-5` | Rot | `#a8244f` | `#f08fb0` | 6,93 / 6,30 / 5,92; 7,46 / 8,14 / 6,71 | 6,93 / 7,46 | Leinwand |
| `marke-6` | Oliv | `#5f6b1f` | `#b5c25a` | 5,82 / 5,29 / 4,97; 8,72 / 9,51 / 7,85 | 5,82 / 8,72 | Fassung 3 (die Leinwand zeigt fünf, A5 verlangt sechs) |

Die Kennfarben liegen nahe an den Statusfarben: dunkel ist `marke-2` gleich `--info`, `marke-3`
fast gleich `--ok` und `marke-4` fast gleich `--fehler` (Kontrast untereinander 1,00–1,01). Das ist
hingenommen. Die Kennfarbe steht nie allein (Kürzel als Text, auf breiten Bildschirmen der Name
daneben), und Status trägt immer Wort und Symbol (1.4.1). Fassung 3 hatte eigene, von den
Statusfarben abgesetzte Werte; freigegeben ist aber die Leinwand.

**Nicht übernommen** wegen des Kontrasts: `kbd` mit `opacity: .75` (Leinwand, Arbeitsfläche) ergibt
im stillen Knopf hell 4,15 : 1 und verfehlt AK4 (≥ 4,5). P1 setzt `kbd` ohne Deckkraft (L4).

### L2 Typografie

Systemschrift wie in der Spec (`system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans",
sans-serif`), Grundgröße 16 px, Zeilenhöhe 1,5, Überschriften 1,25, Gewichte **400 und 600**. Die
Leinwand nutzt mehr Stufen als A90. P1 übernimmt die tragenden als Token und rundet die
Zwischengrößen der Handy-Flächen.

| Token | rem / px | Gewicht | Einsatz (Leinwand) | gegenüber A90 |
|---|---|---|---|---|
| `--gr-1` | 0,75 / 12 | 400, aktiv 600 | Beschriftung der unteren Leiste, `kbd`, Kürzel der Marke (Leinwand 10–11 px, 700) | **neu** |
| `--gr-2` | 0,8125 / 13 | 600 | Etikett (Versalien, Laufweite 0,06em), Status-Pille, Zähler, Initialen im Avatar, Abzeichen „Hinweis“/„Experte“ | **neu** |
| `--gr-3` | 0,875 / 14 | 400/600 | Nebentext, Hilfe- und Fehlertext am Feld, Tabellenkopf, kleiner Knopf, Brotkrumen | Spec |
| `--gr-4` | 1 / 16 | 400/600 | Fließtext, Felder, Knöpfe, Navigation (Handy 15 → 16; 16 px verhindert zugleich, dass iOS beim Tippen in Felder zoomt) | Spec |
| `--gr-5` | 1,125 / 18 | 600 | Kartentitel, Seitentitel im schmalen Kopf, Beträge der Muster-Zeile (Handy-Kartentitel 17 → 18) | Spec |
| `--gr-6` | 1,25 / 20 | 600 | Wortmarke „accounti“ (19 → 20), Titel der Einstellungs-Karten, Schrittfrage, vorgeschlagenes Konto (Handy 19 → 20), Beträge in Freigabe-Karten, Codefeld | **neu** |
| `--gr-7` | 1,375 / 22 | 600 | Abschnitt, Name der Gegenpartei auf der Arbeitsfläche, Begrüßung auf dem Handy | Spec |
| `--gr-8` | 1,75 / 28 | 600 | Seitentitel `h1`, Betrag auf der Arbeitsfläche (Handy 26–28 → 28) | Spec |
| `--gr-9` | 2,5 / 40 | 600, Zeilenhöhe 1 | Kennzahl in einer Karte (Übersicht) | **neu** |

- Laufweite: `h1` und Wortmarke −0,01em, Kennzahl −0,02em, Etikett +0,06em mit `text-transform:
  uppercase`.
- `font-variant-numeric: tabular-nums` auf `body`, wie in der Leinwand. Das deckt A90 für Beträge,
  Daten und Kontonummern ab; `.zahl` regelt nur noch die Ausrichtung.
- `strong`, `b`, `th`, `h1`–`h6`, `summary` und `legend` stehen auf 600 (Fassung 3); das Kürzel der
  Marke auf 600 statt 700.

### L3 Abstände, Radien, Maße

**Abstände.** Layout-Abstände liegen auf dem 4-px-Raster der Spec und laufen über Token: der
Innenabstand von Kopf, Leisten, Inhalt und Karten sowie der Abstand zwischen Blöcken, Karten und
Feldern. Abstände **innerhalb** einer Komponente (Symbol ↔ Text, Label ↔ Feld, Pille, Zähler,
`kbd`) nutzen die Feinstufen der Leinwand.

| Token | rem / px | Einsatz |
|---|---|---|
| `--a-1` … `--a-8` | 0,25 / 0,5 / 0,75 / 1 / 1,5 / 2 / 3 / 4 rem = 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 px | Spec |
| `--a-45` | 1,25 / 20 | **neu**: Karten, Seitenleiste |
| `--a-55` | 1,75 / 28 | **neu**: Abstand der Abschnitte, Themenrahmen |
| `--a-65` | 2,5 / 40 | **neu**: Inhalt seitlich |
| `--fein-1`, `--fein-3`, `--fein-5` | 0,125 / 0,375 / 0,625 rem = 2 / 6 / 10 px | **neu**, nur in `@layer komponenten` |

**Rundung:** Layout-Werte der Leinwand außerhalb des 4-px-Rasters (6, 10, 14, 18, 22, 26 px)
gehen auf das nächste Vielfache von 4, bei Gleichstand nach oben (14 → 16, 18 → 20, 22 → 24,
26 → 28). Die Abweichung beträgt höchstens 2 px. Die Leinwand ist dort ohnehin uneinheitlich: Der
Hinweis hat 10/14, 12/14 und 14/16 px Innenabstand; P1 nimmt einheitlich 12/16.

**Radien:**

| Token | Wert | Einsatz | Stand |
|---|---|---|---|
| `--radius-xs` | 2 px | Sicherheitskästchen | **neu** |
| `--radius-s` | 4 px | `kbd`, kleine Marke | **neu** |
| `--radius` | 6 px | Knöpfe, Felder, Marke, Farbfelder | Spec |
| `--radius-m` | 8 px | Hinweis, Navigationseintrag, Optionskarte, Gesellschafts-Chip, Tabelle in einer Karte | **neu** |
| `--radius-karte` | 10 px | Karte, Tabelle, leerer Zustand, Aufklapper als Karte | Spec |
| `--radius-l` | 12 px | Themenrahmen der Musterseite, Feld des Benutzermenüs | **neu** |
| `--radius-rund` | 999px | Pille, Zähler, Wahlpille, Fortschritt, Avatar | **neu** |

**Maße** (Höhen und Breiten sind keine Abstände; sie folgen der Leinwand):

| Maß | Wert | Token |
|---|---|---|
| Kopfleiste (breit und schmal) | 56 px | `--kopfhoehe: 3.5rem` |
| Untere Leiste | 64 px + `env(safe-area-inset-bottom)` | `--leistenhoehe: 4rem` |
| Seitenleiste | Basis 232 px | `--seitenleiste: 14.5rem` |
| Inhalt breit | höchstens 72rem (Leinwand 1120–1180 px; A3: ≤ 90rem) | `--inhalt-max` |
| Formular (Assistent) / Inhalt der Einstellungen | 47,5rem (760) / 51,25rem (820) | `--formular-max`, `--einstellungen-max` |
| Knopf normal / klein / groß | min. 44 / 36 / 48 px hoch | — |
| Feld | min. 44 px, Codefeld 48 px | — |
| Navigationseintrag | 44 px; Unternavigation der Einstellungen und Bedienelemente im Kopf 40 px (unter `pointer: coarse` 44 px, A106) | — |
| Listenzeile („Mehr“, Gesellschaften) | 48 px | — |
| Symbol | 18 px (Navigation, Hinweis), 22 px (untere Leiste), 16 px (Chevron, Meldung am Feld), 14 px (Pille), 28 px (leerer Zustand), 40 px (fehlender Beleg) | Klassen `symbol-14` … `symbol-40` |
| Marke | 28 px (Kopf), 24 px (Listen) | — |
| Avatar | 32 px (Leinwand 30/32) | — |
| Kontrollkästchen, Optionsfeld | 18 px sichtbar, Klickfläche ≥ 24 px (L7 Nr. 20) | — |

### L4 Komponenten

Makros in `vorlagen/_komponenten.html`, Stile in `@layer komponenten`, Maße nach L2/L3. Die
Zustände folgen A92 (normal, hover, fokus, aktiv, deaktiviert, lädt, fehler – soweit sinnvoll). In
Klammern steht die Zeichenfläche, aus der ein Maß stammt.

| Komponente · Makro · Klasse | Aussehen und Maße | Zustände | Abweichung / Ergänzung |
|---|---|---|---|
| **Kopfleiste breit** · `basis.html` · `.kopfleiste` | 56 px, Innenabstand 0 24, Abstand 16, `--flaeche`, Linie unten. Wortmarke `--gr-6`/600/−0,01em in `--text`. Gesellschafts-Chip: 40 px, Rahmen `--linie`, `--radius-m`, Innenabstand 0 12 0 8, Marke 28 + Name 600 + `chevron-down` 16. Rechts „Hilfe“ (`circle-help` 18 + Text, `--text-2`, Abstand 6) und das Benutzermenü (Avatar 32 + Name + `chevron-down`) (Main) | Hover Schleier, Fokus | Der Chip ist ein **Link** auf `/gesellschaft`, bei nur einer Gesellschaft ein `span` ohne Chevron. Die Leinwand zeigt einen `button` zum Aufklappen; A5 verlangt den Wechsel über die Seite |
| **Kopfleiste schmal** · `.kopfleiste` unter 64rem | 56 px, Innenabstand 0 16 plus Safe Area, Abstand 12: Marke 28, Seitentitel `--gr-5`/600 (füllt), Hilfe-Symbol 44 × 44, Avatar 32 in 44 × 44 (Link `/menue#konto`) (Handy-Uebersicht) | Fokus | **Hilfe-Symbol ergänzt** (B13, A8/AK47; fehlt in der Leinwand). Titel `aria-hidden`, das `h1` im Inhalt bleibt (Fassung 3) |
| **Seitenleiste** · `seitenleiste(geruest)` · `.seitenleiste` | Basis 232 px, Innenabstand 20 12, Linie rechts, Hintergrund `--grund`. Einträge 44 px, Innenabstand 0 12, `--radius-m`, Symbol 18 + Text mit Abstand 12, Einträge 4 px auseinander (Leinwand 2). Trenner 1 px `--linie` mit Rand 12, danach „Einstellungen“ (Main) | aktiv: `--akzent-flaeche`, `--akzent`, 600, `aria-current="page"`; Hover Schleier; Fokus | klebt unter dem Kopf (Fassung 3) |
| **Zähler** · `zaehler(anzahl, beschriftung, betont=False)` · `.zaehler`, `.zaehler-betont` | rechts im Eintrag (`margin-left: auto`), mindestens 28 breit, 22 hoch, Innenabstand 0 8, `--radius-rund`, `--gr-2`/600. Neutral `--flaeche-2`/`--text-2`; betont `--akzent`/`--akzent-text` (Prüfen) (Main) | — | `beschriftung` versteckt („offen“) für Screenreader (Fassung 3) |
| **Untere Leiste** · `untere_leiste(geruest)` · `.untere-leiste` | 64 px plus Safe Area, `--flaeche`, Linie oben; bis zu fünf gleich breite Ziele (`grid-auto-flow: column`), je Symbol 22 über der Beschriftung `--gr-1`, Abstand 2. **Der Zähler steht in der Beschriftung** („Prüfen 12“); bei 320 px gilt `kurztitel` (Handy-Uebersicht) | aktiv: `--akzent`, 600, `aria-current="page"`; sonst `--text-2` | — |
| **Marke** · `marke(marke, klein, href)` (`marke`: `geruest.Marke`) · `.marke`, `.marke-n`, `.marke-klein` | Quadrat 28 (klein 24), `--radius` (klein `--radius-s`), Hintergrund Kennfarbe, Kürzel zentriert in `--flaeche`, `--gr-1`/600 | — | Text ist das **Monogramm** (L7 Nr. 18), Gewicht 600 statt 700. Der Name steht daneben oder als versteckter Text; **kein `aria-label` auf einem `span`** (axe `aria-prohibited-attr`) |
| **Avatar und Benutzermenü** · `avatar(initialen)` · `.avatar`, `.benutzermenue` | Avatar 32, rund, `--akzent-flaeche`/`--akzent`, Initialen `--gr-2`/600. Auslöser (`summary`) 40 px, Innenabstand 0 8 0 4, `--radius-m`: Avatar + Name + Chevron (Main) | offen: Feld in `--flaeche` mit Linie, `--radius-l`, `--schatten`, mindestens 16rem breit, Einträge 44 px | Das Feld fehlt in der Leinwand und ist aus den Token abgeleitet; `<details>` (A6) |
| **Knopf / Linkknopf** · `knopf(…)`, `linkknopf(…)` · `.knopf`, `.knopf-primaer` / `-sekundaer` / `-still` / `-gefaehrlich`, `.knopf-klein` / `-gross`, `.knopf-breit` | mindestens 44 px, Innenabstand 0 20, `--radius`, 600. Primär `--akzent`/`--akzent-text`; sekundär `--flaeche` mit 1 px `--linie-stark` und `--text`; still transparent in `--akzent`, Innenabstand 0 12; gefährlich `--fehler`/`--fehler-text`. Klein 36 px, Innenabstand 0 16 (Leinwand 14), `--gr-3`; groß 48 px, Innenabstand 0 24 (Leinwand 22 und 28); breit 100 % (Handy, Arbeitsfläche). Mit `kbd` Abstand 12 (Bausteine, Arbeitsfläche) | deaktiviert: `--flaeche-2`/`--text-2`, `cursor: not-allowed`, `disabled`; lädt: `aria-busy="true"`, Symbol `loader-circle` 14 vor „Speichert …“, ohne Drehung (A100); Fokus 3 px `--fokus` mit Abstand 2; Hover Schleier | Größe als `groesse="klein"\|"normal"\|"gross"` statt `klein` (Fassung 3) |
| **Karte** · `karte(titel, anzahl, status, hauptaktion, kennzahl, ebene)` (Aufruf) · `.karte`, `.karte-kopf`, `.karte-liste`, `.kennzahl` | Spalte, Abstand 12, Innenabstand 20 24 (Leinwand 20/22; Handy 16), `--flaeche`, 1 px `--linie`, `--radius-karte`, `--schatten`. Titelzeile: `h2`/`h3` in `--gr-5`/600/1,25, Anzahl dahinter in `--text-2`/400, rechts die Status-Pille, `flex-wrap`. Liste: Zeilen mit Linie oben, Innenabstand 12 0 (Leinwand 10); Hauptzeile 600, Nebenzeile `--gr-3`/`--text-2`, rechts Betrag (600) oder Info. Fuß unten (`margin-top: auto`): Link (600) oder Knopf, auf dem Handy volle Breite und 48 px hoch. Kennzahl: `--gr-9` mit Satz in `--text-2` (Main) | — | Die Status-Pille rechts **bricht nicht um** (L7 Nr. 21) |
| **Status-Pille** · `status(art, wort)` · `.status`, `.status-ok` / `-info` / `-warn` / `-fehler` | `inline-flex`, Abstand 6, Innenabstand 2 10, `--radius-rund`, `--<art>-flaeche`/`--<art>`, `--gr-2`/600, Symbol 14 mit Strich 2,4: ok `check`, info `info`, warn und fehler `triangle-alert` (Bausteine) | — | `white-space: nowrap`; nie ohne Symbol (L7 Nr. 11) |
| **Sicherheitsanzeige** · `sicherheit(stufe, zusatz, klein)` · `.sicherheit` | drei Kästchen 10 × 10 (in Tabellen 8 × 8), `--radius-xs`, Abstand 2. Niedrig: 1 × `--fehler`; mittel: 2 × `--warn`; hoch: 3 × `--ok`; die übrigen `--linie`. Daneben mit Abstand 8 „Sicherheit: mittel“ in `--gr-3`/`--text-2`, auf Wunsch „· KI“ (Bausteine, Pruefen-Liste) | — | Kästchen `aria-hidden`; die Bedeutung trägt das Wort |
| **Reiter** · `reiter(beschriftung, eintraege, aktiv, geteilt=False)` · `.reiter` | Zeile mit Linie unten, Abstand 4. Eintrag 44 px, Innenabstand 0 16 (Leinwand 14), Text und Anzahl in `--text-2`/400 (Pruefen-Liste) | aktiv: 3 px `--akzent` unten über der Linie (`margin-bottom: -1px`), `--text`, 600, `aria-current="page"`; inaktiv `--text-2` | `nav` mit Links statt `role="tablist"` (L7 Nr. 3). `geteilt=True`: zwei gleich breite Spalten auf `--flaeche` (Handy-Pruefen, für P3) |
| **Optionskarte** · `optionskarte(name, wert, titel, nebentext, grund, gewaehlt, taste, id)` · `.optionskarte` | `label`, Abstand 12, Innenabstand 12 16, 1 px `--linie-stark`, `--radius-m`, `--flaeche`. Optionsfeld 18 (`accent-color: var(--akzent)`), Titel 600, Nebentext `--gr-3`/`--text-2`, rechts auf Wunsch `kbd`. Mehrere im Raster `auto-fit, minmax(16rem, 1fr)` (Assistent, Arbeitsfläche) | gewählt: 2 px `--akzent` und `--akzent-flaeche` über `:has(input:checked)`, der Innenabstand dabei 1 px kleiner (nichts springt); Fokus: Ring am Optionsfeld; deaktiviert `--flaeche-2` | ohne Skript (L7 Nr. 2) |
| **Segment (Wahlpillen)** · `segment(name, legende, optionen, gewaehlt)` · `.segment` | Optionsfelder als Pillen: 44 px, Innenabstand 0 16 (Leinwand 14), 1 px `--linie-stark`, `--radius-rund`, Abstand 8, `flex-wrap` (Assistent) | gewählt: 2 px `--akzent`, `--akzent-flaeche`, 600 | dient auch für Sprache und Darstellung im Benutzermenü und auf `/konto` |
| **Feld** · `feld(…, fehler, warnung, bestaetigt, pflicht, breite, id)`, `auswahl(…)`, `textfeld(…)` · `.feld`, `.eingabe` | Label oben 600, dahinter „(Pflicht)“ 400 in `--text-2`, Abstand 6. Eingabe 44 px, Innenabstand 0 12, 1 px `--linie-stark`, `--radius`, `--flaeche`, Schrift geerbt; Hilfetext `--gr-3`/`--text-2` (Bausteine, Einstellungen). Breiten: `breite-schmal` 8rem (PLZ), `breite-mittel` 14rem (Code, Rechtsform), `breite-breit` 22rem (USt-IdNr.), sonst volle Breite | **Fehler:** 2 px `--fehler` (Innenabstand 11 px), darunter `circle-x` 14 + „Fehler: …“ in `--gr-3`/600/`--fehler`, `aria-invalid`, `aria-describedby`. **Warnung** (Assistent): 2 px `--warn`, `triangle-alert` + „Achtung:“ (600) + Text in `--warn`, **ohne** `aria-invalid`. **Bestätigt:** `check` 16 + Text in `--ok`, Zusatz in `--text-2`. Deaktiviert `--flaeche-2` | `warnung` und `bestaetigt` sind neu (P7 nutzt sie). Die Leinwand setzt bei der Warnung `aria-invalid` – das ist falsch, eine Warnung ist kein Fehler |
| **Codefeld** · `codefeld(variante, wechsel_href, fehler, id)` | wie ein Feld, 48 px, `--gr-6`, Laufweite 0,2em, `breite-mittel`; Label „Code aus Ihrer Authenticator-App“ (Handy-Freigaben) | wie Feld | Link „Wiederherstellungscode verwenden“ beim Label (Fassung 3) |
| **Hinweis** · `hinweis(art, titel, neu)` (Aufruf) · `.hinweis`, `.hinweis-<art>` | Zeile, Abstand 10, Innenabstand 12 16, `--radius-m`, `--<art>-flaeche`; Symbol 18 in `--<art>`, oben bündig; **Wort 600 in `--<art>`** („Hinweis:“, „Erledigt:“, „Achtung:“, „Fehler:“), Text in `--text` | `role` nur mit `neu` | Symbol **und** farbiges Wort. „Bausteine“ zeigt nur das farbige Wort, die Seiten Symbol und Wort in Textfarbe; A95 verlangt das Symbol (L7 Nr. 10) |
| **Leerer Zustand** · `leer(satz, nebensatz, aktion_text, aktion_href, symbol="check")` · `.leer` | Spalte zentriert, Abstand 6, Innenabstand 24, 1 px **gestrichelt** `--linie-stark`, `--radius-karte`; Symbol 28 (`check` in `--ok`), Satz 600, Nebensatz `--gr-3`/`--text-2` („Nichts zu prüfen.“ / „Nächster Bankabruf: heute 14:00.“) (Bausteine). Variante fehlender Beleg: `file-text` 40 in `--text-2`, `--flaeche`, Innenabstand 32 (Arbeitsfläche) | — | **Link zur nächsten Aktion** darunter (AK54; fehlt in der Leinwand) |
| **Tabelle** · `tabelle(beschriftung, spalten, kompakt, sichtbar, in_karte)`, `zeile(gewaehlt)`, `zelle(label, zahl)`, `spaltenkopf(spalte)` · `.tabelle`, `.tabelle-rahmen` | Rahmen 1 px `--linie`, `--radius-karte` (in einer Karte `--radius-m`), `--flaeche`; freistehend mit `--schatten`. Kopf auf `--flaeche-2` in `--gr-3`/600/`--text-2`, Zellen 8 16. Körperzellen 12 16 (Leinwand 12–14), erste und letzte Spalte außen 20 (Leinwand 18), oben bündig, Zeilen mit Linie oben, Zahlen rechtsbündig. Zweizeilige Zelle: Hauptzeile 600, Nebenzeile `--gr-3`/`--text-2`. **Summenzeile** (`tfoot`): 2 px `--linie-stark` oben, 600 (Bausteine, Pruefen-Liste) | gewählte Zeile `--akzent-flaeche` (`zeile(gewaehlt=True)`, Klasse `zeile-gewaehlt`); der Kopf klebt unter der Kopfleiste | Rahmen mit `overflow: clip` statt `hidden`, **ohne** `min-width` (L7 Nr. 14, 15); unter 40rem Karten (Fassung 3) |
| **Angaben** · `angaben(klein)`, `angabe(label)` · `.angaben` | `dl` als Raster: Label in `--text-2`, Wert ohne Rand; Abstand 4 16 (Arbeitsfläche, `klein`: `--gr-3`) bzw. 12 20 (Einstellungen, Leinwand 10/20); Label-Spalte `fit-content(14rem)` (Leinwand fest 6,5–14rem) | — | Fassung 3 (I11) |
| **Aufklapper** · `aufklapper(titel, art="linie"\|"karte", offen)` (Aufruf) · `.aufklapper` | `details`/`summary` mit 600. „linie“: Linie oben, darüber 12 Abstand, `summary` 32 px, Markierung des Browsers (Arbeitsfläche, Handy-Freigaben). „karte“: wie eine Karte ohne Schatten, Innenabstand 0 24, `summary` 56 px, rechts `chevron-down` und „aufklappen“ bzw. „zuklappen“ in `--gr-3`/`--text-2` (Main) | offen: Chevron gedreht über `details[open]` (ohne Übergang), das Wort wechselt per CSS | **neu** (nicht in A92, auf der Leinwand fünfmal) |
| **Sammelleiste** · `sammelleiste()` (Aufruf) · `.sammelleiste` | klebt unten im Inhalt (`position: sticky; bottom: 0`), `--flaeche`, 1 px `--linie-stark` oben, Innenabstand 16 40 (Leinwand 14), `flex-wrap`, Abstand 12 24. Links „2 ausgewählt“ (600) und „· zusammen …“ in `--text-2`, rechts ein stiller und ein primärer Knopf (Pruefen-Liste) | — | **neu**. Unter 64rem steht sie über der unteren Leiste (`bottom: calc(var(--leistenhoehe) + env(safe-area-inset-bottom))`); `scroll-padding-block-end` wächst um ihre Höhe (2.4.11) |
| **Aktionsleiste** · `aktionsleiste()` (Aufruf) | ersetzt unter 64rem die untere Leiste: `--flaeche`, 1 px `--linie-stark` oben, Innenabstand 12 16 16 plus Safe Area; primärer Knopf 48 in voller Breite, darunter zwei sekundäre (48) in zwei Spalten, Abstand 8 (Handy-Pruefen) | — | Fassung 3 |
| **Schritte** · `schritte(schritte, aktuell)` · `.schritte`, `.fortschritt` | „Schritt 3 von 7“ in `--gr-3`/`--text-2`; Fortschritt 6 px hoch, `--radius-rund`, Spur `--flaeche-2`, Füllung `--akzent`. Liste mit 40-px-Einträgen, Symbol 18 + Text mit Abstand 10. Erledigt: `check` in `--ok`, Text `--text-2`. Aktuell: `--akzent-flaeche`, `--akzent`, 600, Ring 18 mit 5 px Rand. Offen: Kreis 18 mit 2 px `--linie-stark`. „Fertig“ ohne Symbol in `--text-2` (Assistent) | `aria-current="step"` | Fortschritt als `<progress value max>` – so entsteht die Breite ohne `style=` (L7 Nr. 1); `aria-hidden`, weil der Text die Zahl trägt |
| **Betrag** · `betrag(wert, richtung, groesse)` · `.betrag`, `.betrag-richtung` | Vorzeichen „+“ bzw. „−“ (U+2212) mit schmalem festem Leerzeichen, Euro mit festem Leerzeichen; darunter die Richtung als Wort („Einnahme“/„Ausgabe“) in `--gr-3`/`--text-2`. Summen ohne Vorzeichen (Bausteine: „+ 780,25 €“, „− 1.204,90 €“, „11.111,11 €“) | — | `white-space: nowrap` (L7 Nr. 21) |
| **Tastenkürzel** · `<kbd>` | Schrift geerbt, `--gr-1`, Innenabstand 0 6, 1 px `--linie`, `--radius-s`, `--text-2`, ohne Hintergrund (Pruefen-Liste); im primären Knopf Farbe und Rand `currentColor` | — | **ohne** `opacity` (L1) |
| **Etikett und Seitenkopf** · `.etikett`, `.seitenkopf` | Etikett: `--gr-2`/600, Versalien, 0,06em, `--text-2` – für Abschnittsüberschriften und `legend`. Seitenkopf: `h1` und darunter eine Zeile in `--text-2` (Abstand 4), rechts z. B. das Datum, `flex-wrap`, an der Grundlinie ausgerichtet (Main) | — | — |
| **Unternavigation** (Einstellungen) · `.unternavigation` | Einträge 40 px, Innenabstand 0 12, `--radius`; Abzeichen rechts: „Hinweis“ in `--gr-2`/600/`--warn` mit `triangle-alert` 14, „Experte“ in `--gr-2`/`--text-2` (Einstellungen-Firma) | aktiv: `--flaeche`, 1 px `--linie`, 600, `aria-current="true"` – anders als in der Seitenleiste | Teil von `layout-einstellungen` |
| **Gruppenliste** („Mehr“, `/gesellschaft`) · `.gruppenliste` | Etikett über einer Karte ohne Schatten; Zeilen 48 px, Innenabstand 0 16 (Leinwand 14), Linie zwischen den Zeilen; rechts Zähler in `--text-2` und `chevron-right` 18. Gesellschaft: kleine Marke und Name; die aktive mit Name 600 und „aktiv“ in `--gr-3`/`--text-2`. „Abmelden“ als stiller Knopf in der Liste (Handy-Mehr) | Hover Schleier | Wechsel und Abmelden sind POST-Formulare (Fassung 3) |
| nicht auf der Leinwand: **Brotkrumen**, **Seitenblättern**, **Fehlerliste**, **Ladeanzeige**, **Bestätigung** | aus den Token und den Mustern oben abgeleitet. Brotkrumen in `--gr-3`/`--text-2` mit Trenner „›“ (`aria-hidden`) wie in Einstellungen-Firma; Fehlerliste wie ein Hinweis „Fehler“; Seitenblättern als kleine sekundäre Knöpfe, die aktuelle Seite auf `--akzent-flaeche` | wie Fassung 3 | — |

### L5 Layouts

| Layout · Klasse | Leinwand | Umsetzung P1 |
|---|---|---|
| **Gerüst** · `basis.html` | Kopf 56; darunter Seitenleiste (`flex: 1 1 232px`) und Inhalt (`flex: 999 1 560px; min-width: 0`) in einer Zeile mit `flex-wrap` (Main) | dasselbe Flex-Paar. **Ab 64rem** ist die Seitenleiste sichtbar und klebt, **darunter** `display: none` mit unterer Leiste (A3/A4, statt dass die Seitenleiste über den Inhalt umbricht) |
| **Inhalt** · `main` | Innenabstand 32 40 48, Breite höchstens 1120–1180 px, Abschnitte 28 bzw. 24 auseinander; Handy 16 mit Abstand 12 | `padding: var(--a-6) var(--a-65) var(--a-7)`, `max-width: var(--inhalt-max)`; unter 64rem `var(--a-4)`; Fließtext ≤ 75ch (Fassung 3) |
| **karten** · `.layout-karten` | `repeat(auto-fit, minmax(18rem, 1fr))`, Abstand 16 (Main) | `minmax(min(18rem, 100%), 1fr)` – 320 px ohne Überlauf (Fassung 3) |
| **zweispaltig** · `.layout-zweispaltig` | Beleg `flex: 1 1 420px`, Vorschlag `flex: 1 1 440px; max-width: 620px`, Abstand 24, `flex-wrap`, oben bündig (Arbeitsfläche) | so übernommen: zwei Spalten, sobald beide Platz haben (bei 1440 px mit Seitenleiste), sonst untereinander. Auslegung von A91 „ab 64rem“ (L7 Nr. 16) |
| **einstellungen** · `.layout-einstellungen` | Brotkrumen und `h1`; Unternavigation `flex: 1 1 220px; max-width: 260px`, Inhalt `flex: 999 1 520px; max-width: 820px`, Abstand 32; Abschnittskarten mit Innenabstand 24 28 (Leinwand 26) und 20 auseinander (Leinwand 18) (Einstellungen-Firma) | so übernommen; unter 64rem steht die Unternavigation als Liste oben (A91) |
| **formular** · `.layout-formular` | eine Spalte bis 760 px, Abstand 28, Aktionen am Ende mit Linie oben (Assistent) | für P7 und lange Formulare; P1 nutzt es auf `/konto` |
| **schlicht** · `schlicht.html` | Kopf 56 mit „accounti einrichten“, kleiner Marke und Name in `--text-2`, Hilfe rechts; keine Seitenleiste (Assistent) | Anmeldung, 500, später der Assistent: Kopf mit Wortmarke und Hilfe (Fassung 3); Inhalt als Karte, höchstens 26rem, zentriert |

### L6 Symbole

Die Leinwand zeichnet Lucide-Formen nach, teils vereinfacht. Das Sprite nimmt die **Originalformen**
aus `lucide-static` 1.55.0 (Fassung 3); die Auswahl folgt der Leinwand.

| Stelle | Leinwand (Form) | Lucide | gegenüber Fassung 3 |
|---|---|---|---|
| Übersicht | Haus | `house` | — |
| Prüfen | Quadrat mit Haken | `square-check-big` | statt `list-checks` |
| Belege | Blatt mit Zeilen | `file-text` | — (Pruefen-Liste zeigt das Blatt ohne Zeilen; Main gilt) |
| Steuern | Kalender | `calendar` | statt `calculator` |
| Auswertungen | Säulen | `chart-column` | — |
| Freigaben | Schild mit Haken | `shield-check` | statt `stamp` |
| Einstellungen | Zahnrad | `settings` | — (Pruefen-Liste zeigt eine Sonne; Main gilt) |
| Mehr | drei Linien | `menu` | statt `ellipsis` |
| Hilfe | Kreis mit Fragezeichen | `circle-help` | — |
| erledigt, freigegeben, „Format passt“, leerer Zustand | Haken | `check` | statt `circle-check` |
| vorbereitet, Hinweis | Kreis mit i | `info` | — |
| Achtung, überfällig | Dreieck | `triangle-alert` | — |
| Fehler am Feld | Kreis mit x | `circle-x` | — |
| Beleg fehlt, Angabe fehlt | Kreis mit Ausrufezeichen | `circle-alert` | **neu** |
| gesperrt | Schloss | `lock` | **neu** |
| Vorschlag („Vorschlag: monatlich“) | Pfeil nach rechts | `arrow-right` | **neu** |
| Gesellschaft wechseln, Benutzermenü, Aufklapper, Zeilen in „Mehr“, Rückweg | Chevron | `chevron-down`, `chevron-right`, `chevron-left` | — |
| PDF öffnen | Pfeil aus Kasten | `external-link` | — |
| lädt | Ring mit Lücke | `loader-circle` (steht still, A100) | — |

Aus Fassung 3 bleiben ohne Vorbild auf der Leinwand: `landmark`, `receipt` (Bereiche ohne Seite in
10c), `log-out`, `search`, `upload`, `download`, `calendar-clock`, `sun`, `moon`, `monitor`,
`arrow-up-down`, `arrow-up`, `arrow-down`, `x`, `keyboard`. **Entfallen:** `gauge` (Sicherheit
sind Kästchen), `circle-user` (Avatar mit Initialen), `building-2` (Marke), `circle-check`
(Haken), `ellipsis`, `list-checks`, `calculator`, `stamp`.

**Ergebnis: 36 Symbole.** Ein Probe-Sprite aus dem geprüften Tarball hat 6 443 Bytes (Budget 15 360).
Von Feather abgeleitet (MIT-Teil der Lizenz) sind 22 davon: unter gleichem Namen `arrow-down`,
`arrow-right`, `arrow-up`, `calendar`, `check`, `chevron-down`, `chevron-left`, `chevron-right`,
`download`, `external-link`, `info`, `lock`, `log-out`, `monitor`, `moon`, `search`, `upload`,
`x`; unter neuem Namen `triangle-alert` ← `alert-triangle`, `circle-help` ← `help-circle`,
`circle-x` ← `x-circle`, `circle-alert` ← `alert-circle`. Geprüft an `package/LICENSE`:
`square-check-big`, `menu` und `shield-check` stehen dort nicht und fallen unter ISC. Strichstärke 2
wie Lucide; kleine Symbole in Pillen und Meldungen am Feld zeichnet die Leinwand mit 2,4, P1 über
`.symbol-kraeftig`.

### L7 Leinwand ↔ Spec: Abweichungen und Lösung

| Nr. | Leinwand | Spec / Plan | Lösung in P1 (das Aussehen bleibt) | später |
|---|---|---|---|---|
| 1 | Alles über `style=`, auch berechnete Werte (Auswahlrand, Reiter-Strich, Fortschritt 43 %) | A98 CSP: kein `style=` | jede Regel als Klasse in `statisch/accounti.css`. Zustände über Attribute und Selektoren (`aria-current`, `:has(input:checked)`, `details[open]`, `[disabled]`, `[aria-busy]`), Kennfarbe über `marke-n`, Fortschritt als `<progress>` | alle Pakete |
| 2 | Klicklogik in `DCLogic` (Arbeitsfläche, Handy-Reiter) | A99: ohne JS bedienbar | Der Server rendert jeden Zustand. Optionskarte und Segment zeigen die Auswahl ohne Skript (`:has`), gewählt wird per Absenden | P3, P7 |
| 3 | Reiter als `role="tablist"`/`role="tab"` auf Links und Knöpfen | ARIA-Reiter verlangen Pfeiltasten-Logik per Skript (A105) | `nav` mit Links und `aria-current="page"`, Optik gleich | P3: Handy-Reiter als zwei Abschnitte mit Sprunglinks oder Umschaltung durch den Server |
| 4 | Kürzel in Gewicht 700 | A90: 400 und 600 | 600 | — |
| 5 | Schriftgrößen 10, 11, 12, 13, 15, 17, 19, 20, 26, 40 px | A90: 14/16/18/22/28 | Skala um 12, 13, 20 und 40 px erweitert, Zwischengrößen gerundet (L2) | Nachtrag in der Spec |
| 6 | Abstände in 2-px-Schritten (6, 10, 14, 18, 22, 26) | A91: 4-px-Raster | Layout gerundet; Feinstufen 2/6/10 nur in Komponenten; Zwischenstufen 20/28/40 (L3) | Nachtrag in der Spec |
| 7 | Radien 2, 3, 4, 5, 8, 11, 12 px | A91: 6 und 10 px | Radius-Token 2/4/6/8/10/12/rund (L3) | Nachtrag in der Spec |
| 8 | Fokusring 3 px mit 2 px Abstand | A104: „2-px-Ring“; AK55: „≥ 2 px“ | **3 px** wie die Leinwand; A104 als Mindestmaß gelesen, AK55 erfüllt | Auslegung im PR |
| 9 | `kbd` mit `opacity: .75` | AK4: `kbd` ≥ 4,5 : 1 | ohne Deckkraft (im stillen Knopf sonst 4,15 : 1) | — |
| 10 | Hinweis in „Bausteine“ ohne Symbol | A95: Symbol, Wort, Text | Symbol, farbiges Wort und Text – vereint beide Varianten der Leinwand | — |
| 11 | Status ohne Symbol: Etikett „überfällig“ in der Fristenliste, „seit 25.10.“ nur rot, „geändert“ nur gelb | A89: Farbe trägt nie allein Bedeutung | `status()` hat immer Symbol und Wort; Farbe allein gibt es nicht | P2 (Fristen), P5 (Spalte „Stand“) |
| 12 | schmaler Kopf ohne Hilfe | A8/AK47: Hilfe-Link auf jeder Seite an derselben Stelle | Hilfe-Symbol 44 × 44 vor dem Avatar (B13) | — |
| 13 | `aria-label` auf einem `span` (Marke im Handy-Kopf) | AK2: axe 0 Verstöße (`aria-prohibited-attr`) | Marke mit sichtbarem Monogramm, der Name als `.unsichtbar`-Text; bei mehreren Gesellschaften ein Link auf `/gesellschaft` | — |
| 14 | Prüftabelle mit `min-width: 760px` in `overflow-x: auto` | AK1, A93: unter 40rem Karten, kein waagrechtes Scrollen | kein `min-width`; zweizeilige Zellen brechen um, unter 40rem Karten; nur `kompakt` (Auswertungen) im `.tabelle-rahmen` | 10b-2 |
| 15 | Tabellenrahmen mit `overflow: hidden` | A93: der Kopf klebt beim Scrollen | `overflow: clip` (kein Scroll-Container, `sticky` wirkt; Safari ab 16, davor `hidden` als Rückfall) | — |
| 16 | zweispaltig über eine Flex-Basis (420/440 px) | A91: „zweispaltig ab 64rem“ | Flex-Basis übernommen; zwei Spalten, wo Platz ist – Auslegung | — |
| 17 | fünf Kennfarben, dazu eigene Namen je Gesellschaft | A5: sechs, Klassen `marke-1` … `marke-6` | fünf aus der Leinwand und Oliv aus Fassung 3 (L1) | P5 zeigt sechs in der Wahl |
| 18 | Kürzel als Monogramm („GD“, „KU“) | Registry-Kürzel haben bis zu 30 Zeichen (`muster`, `tochter`; `models/auth.pruefe_gesellschaft`) | **Monogramm** aus dem Namen, in der Registry eindeutig (Regel unter „Schnittstelle“); das Registry-Kürzel bleibt in `data-gesellschaft` | P5 kann eine Wahl ergänzen |
| 19 | Arbeitsfläche ohne Gerüst: eigene Prüfschlangen-Leiste, keine Seitenleiste, keine Marke, keine Hilfe – auf dem Handy ebenso | A5 (Marke auf jeder Seite), A8/AK47 (Hilfe), A4 (die Aktionsleiste ersetzt nur die **untere** Leiste) | P1 lässt die Arbeitsfläche im Gerüst und gibt ihrer Positionszeile die Optik der Prüfschlangen-Leiste | **P3 entscheidet** über einen Fokusmodus; Marke und Hilfe müssen bleiben |
| 20 | Kontrollkästchen 18 px ohne Label in Tabellen | A106/AK55: Ziel ≥ 24 × 24 (44 bei `pointer: coarse`) | sichtbar 18 px; das umschließende `label` (`.haken-ziel`) ist mindestens 24 × 24 bzw. 44 × 44 | P3 |
| 21 | Beträge („3.212,40 €“) und Pillen („1 überfällig“) brechen in Karten bei 1440 px um (Bild von Main) | A90: lesbare Beträge | `.betrag` und `.status` mit `white-space: nowrap` und festen Leerzeichen; die Titelzeile der Karte bricht als Ganzes um | — |
| 22 | Hover nur für Links | A92: Zustand „hover“ | Token `--schleier` (L1) | — |
| 23 | Wörter nach Anhang B („Später klären“, „Sicherheit: mittel“, „Passt – freigeben“, Datum „05.04.26“) | A121: Bestandsseiten ohne fachliche Änderung; I2–I5 erst in P3 | P1 übernimmt die Optik, nicht die Wörter der neuen Bedienung | P3 |
| 24 | Bedienelemente im Kopf 40 px hoch, `summary` 32 px | A106: ≥ 24, bei `pointer: coarse` 44 | 40/32 bei feinem Zeiger, 44 unter `pointer: coarse` | — |
| 25 | `summary` mit `display: flex` (die Markierung verschwindet nur in Chromium) | einheitliches Aussehen | Variante „karte“ setzt `list-style: none` und `::-webkit-details-marker { display: none }` und zeichnet einen eigenen Chevron | — |

**Budget.** Die Komponenten der Leinwand sind reicher als in Fassung 3 (Aufklapper, Sammelleiste,
Wahlpillen, Fortschritt, zwei Themenklassen). Geschätzt 28–32 KB ohne `bestand`; das Ziel bleibt
≤ 30 KB nach Schritt 12 (R-P1-3), die Grenze 40 KB.

### L8 Zuordnung Zeichenfläche → Vorlage, Makro, CSS-Klasse, Paket

| Zeichenfläche · Element | Vorlage / Makro / Klasse | baut |
|---|---|---|
| **Main** · Kopfleiste | `basis.html` · `.kopfleiste`, `marke()`, `.benutzermenue` | P1 |
| Main · Seitenleiste mit Zählern | `seitenleiste(geruest)` · `.seitenleiste`, `zaehler(betont)` | P1 |
| Main · Seitenkopf („Guten Morgen, Jan“, Datum) | `.seitenkopf` | Muster P1; Text P2 |
| Main · „Heute zu tun“ (Etikett und sechs Karten) | `.etikett`, `.layout-karten`, `karte(…)`, `status()`, `.karte-liste`, `.kennzahl` | Komponenten P1. P1 setzt die **vier Zahlen** der Bestands-Übersicht als Kennzahl-Karten (`start.html`); die sechs Karten mit Daten baut **P2** |
| Main · „Erledigt“, „In anderen Gesellschaften“ | `marke(klein=True)`, `gesellschaften_mit_zaehlern` | P2 |
| Main · „Kennzahlen Oktober“ | `aufklapper(art="karte")` | Komponente P1; Inhalt 10b-2/P2 |
| **Pruefen-Liste** · Reiter | `reiter()` · `.reiter` (Bestand: „Offen“, „Zurückgestellt“, „Gelernte Regeln“) | Optik P1; Wörter P3 |
| Pruefen-Liste · „Gleichartige Vorschläge“ | `karte` mit Zeilen und `knopf` | P3 |
| Pruefen-Liste · „Einzeln prüfen“ und „Durcharbeiten j“ | `tabelle()`, `linkknopf(art="sekundaer", taste="j")`, `betrag()`, `sicherheit()` | Tabelle mit den Bestandsspalten P1; Auswahl, Zeilenaktionen, Sicherheit statt Prozent **P3** |
| Pruefen-Liste · Sammelleiste | `sammelleiste()` | Komponente P1; Einsatz P3 |
| **Pruefen-Arbeitsflaeche** · Prüfschlangen-Leiste | `pruefen/_arbeitsflaeche.html` · `.queue-kopf` in der Optik der Leiste, innerhalb des Gerüsts | Optik P1; Fokusmodus P3 |
| Arbeitsfläche · Beleg-Spalte | `.layout-zweispaltig`, `leer(symbol="file-text")`, Vorschau-Rahmen mit `--beleg-hintergrund` | P1 |
| Arbeitsfläche · Vorschlag-Karte (Name, Betrag 28, Herkunft) | `.karte`, `betrag(groesse="gross")`, `angaben(klein=True)` | Optik P1 mit Bestandsinhalt; Texte nach Anhang B P3 |
| Arbeitsfläche · „Achtung: Kein Beleg …“ | `hinweis("warn")` – in P1 für die Bestandshinweise (Prüfregel, Sperre, zurückgestellt) | P1 |
| Arbeitsfläche · Aktionen („Passt – freigeben f“, „Anderes Konto … e“, „Später klären … z“) | `knopf(groesse="gross", breit=True, taste=…)` – in P1 für Freigeben (f), Korrigieren und Zurückstellen | Optik P1; drei Schritte, `optionskarte` mit Tasten 1–3 und „Künftig immer so?“ **P3** |
| **Handy-Uebersicht** · Kopf schmal, untere Leiste | `basis.html` · `.kopfleiste` unter 64rem, `untere_leiste()` | P1 |
| Handy-Uebersicht · Karten | `karte` mit Handy-Maßen, Hauptaktion `knopf(breit=True, groesse="gross")` | P2 |
| **Handy-Pruefen** · Leiste, Reiter, Aktionsleiste | `aktionsleiste()`, `reiter(geteilt=True)` | Komponenten P1; Seite P3 |
| **Handy-Freigaben** · Karte je Freigabe | `freigaben.html`: je Lauf eine `karte` mit Betrag rechts (`--gr-6`), `angaben`, Zahlungstabelle, `codefeld`, primärer Knopf (unter 40rem in voller Breite) | Gliederung P1 mit den Bestandstexten; `aufklapper` „Zahlungen ansehen (4)“ und die USt-VA-Karte mit Werten und Frist **P2** (A126) |
| **Handy-Mehr** | `menue.html` · `.gruppenliste`, `marke(klein=True)`, `.etikett`, POST-Formulare | **P1** vollständig |
| **Assistent-Steuern** | `schlicht.html` (Kopf), `schritte()`, `.layout-formular`, `hinweis("info")`, `optionskarte`, `segment`, `feld(bestaetigt=…, warnung=…)`, `haken` | Komponenten P1; Seite **P7** |
| **Einstellungen-Firma** | `.layout-einstellungen`, `.unternavigation`, `brotkrumen`, Abschnittskarten, `feld`, `auswahl`, Wahl der Kennfarbe (`marke-n` als Optionsfelder), `tabelle(in_karte=True)`, `hinweis("warn")`, `codefeld`, `angaben` | Layout und Komponenten P1 (auf `/muster`); Seite **P5**, Daten P4 |
| **Bausteine** | `muster.html` (L9) | **P1** |
| nicht auf der Leinwand: Anmeldung, `/konto`, `/gesellschaft`, `/hilfe`, Fehlerseiten, Buchung, Beleg | aus denselben Komponenten: Anmeldung `schlicht.html` mit Karte; `/konto` `.layout-formular` mit `segment`/`optionen`; `/gesellschaft` `.gruppenliste`; Hilfe einspaltig; Fehlerseiten `hinweis` mit Link; Buchung und Beleg `angaben`, `tabelle`, `knopf("gefaehrlich")` | P1 |

### L9 Musterseite als Nachbildung der Zeichenfläche „Bausteine“

- **Ohne Parameter** (`/muster`) beginnt die Seite wie die Zeichenfläche: `h1` „Bausteine“,
  darunter der Einleitungssatz („Ruhig, hell und dunkel, Systemschrift, Beträge in gleich breiten
  Ziffern. Farbe trägt nie allein Bedeutung: Status hat immer Wort und Symbol. Der Fokusring ist
  bernsteinfarben und unterscheidet sich von Akzent und Fehler.“) in `--text-2`, höchstens 900 px
  breit. Darunter folgt ein Raster `repeat(auto-fit, minmax(min(30rem, 100%), 1fr))` mit Abstand 24
  und **zwei Themenrahmen nebeneinander**: `<section class="thema thema-hell">` „Hell“ und
  `<section class="thema thema-dunkel">` „Dunkel“. Jeder Rahmen hat ein `h2` in `--gr-7`,
  Innenabstand 28, 1 px `--linie`, `--radius-l`; seine Abschnitte stehen 28 auseinander. Bei
  390 px stehen die Rahmen untereinander.
- **Themenklassen:** Die Tokenblöcke gelten auch für `.thema-hell` und `.thema-dunkel`
  (`:root, .thema-hell { … }`, `:root[data-theme="dunkel"], .thema-dunkel { … }`, jeweils mit
  `color-scheme`; am Rahmen `background: var(--grund)` und `color: var(--text)`). So zeigt eine
  Seite beide Modi ohne `style=`, und native Bedienelemente folgen dem `color-scheme` des Rahmens.
  Nur `/muster` nutzt die Klassen.
- **Abschnitte je Rahmen** in der Reihenfolge der Zeichenfläche, je mit `h3` als Etikett:
  1. **Farben** – zwölf Felder im Raster mit vier Spalten (Abstand 12), je 40 px hoch mit
     `--radius`; Grund und Fläche mit Linie. Grund, Fläche, Fläche 2, Linie, Text, Nebentext, Akzent
     (Petrol), Fokus (Bernstein), Erfolg, Warnung, Fehler, Hinweis. **P1 ergänzt** eine Zeile mit
     den Kennfarben `marke-1` … `marke-6` samt Monogramm.
  2. **Schrift** – Seitentitel 28, Abschnitt 22, Kartentitel 18, Fließtext 16 („Kontobezeichnung vor
     Nummer, „19 % Vorsteuer“ vor „Schlüssel 9“.“), Nebentext 14, Beträge `+ 780,25 €`,
     `− 1.204,90 €`, `11.111,11 €` (18/600). **Ergänzt:** 20, 13 (Etikett), 12 und 40 (Kennzahl).
  3. **Knöpfe** – erste Zeile Primär, Sekundär, Still, Stornieren (gefährlich); zweite Zeile Klein,
     „Mit Fokus“ (Klasse `zeige-fokus`, nur auf `/muster`: zeichnet den Ring ohne echten Fokus),
     Deaktiviert, „Speichert …“ (`aria-busy`). **Ergänzt:** groß, breit, mit Symbol, mit `kbd`,
     Linkknopf.
  4. **Status und Sicherheit** – Pillen „freigegeben“ (ok), „vorbereitet“ (info), „zur Prüfung“
     (warn), „überfällig“ (fehler); Sicherheit niedrig, mittel, hoch.
  5. **Felder** – zwei Spalten: IBAN mit Hilfetext; PLZ mit Fehler („Fehler: Die PLZ hat 5
     Ziffern.“, `breite-schmal`). **Ergänzt:** Warnung, bestätigt, Pflicht, Auswahl, Textfeld,
     Codefeld (beide Varianten), Optionen, Haken, Fehlerliste.
  6. **Hinweise** – Hinweis („accounti berät nicht steuerlich.“), Erledigt („6 Buchungen
     freigegeben.“), Achtung („Letzte Sicherung vor 9 Tagen.“), Fehler („Code falsch oder schon
     benutzt.“).
  7. **Tabelle und leerer Zustand** – Konto/Betrag: Telefon (4920) 239,94 €, Bürobedarf (4930)
     412,37 €, Summe 652,31 €; leer „Nichts zu prüfen.“ / „Nächster Bankabruf: heute 14:00.“, dazu
     der Link.
  8. **Ergänzt (P1, nicht auf der Zeichenfläche):** Karte (mit Pille, mit Kennzahl), Reiter,
     Optionskarte, Segment, Aufklapper (beide Arten), Angaben, Betrag mit Richtung, `kbd`, Zähler,
     Marke, Avatar, Brotkrumen, Seitenblättern, Schritte mit Fortschritt, Bestätigung,
     Ladeanzeige, Ausschnitte von Seitenleiste, unterer Leiste, Aktionsleiste und Sammelleiste (in
     `.muster-rahmen`, dort weder fest noch klebend), die vier Layouts als kleine Skizzen.
- **Außerhalb der Rahmen** steht einmal: der Umschalter „beide | hell | dunkel | automatisch“ als
  Links und der Abschnitt „Austausch“ (`/muster/beispiel`, Fassung 3).
- **`?theme=hell|dunkel|auto`** zeigt einen einzigen Rahmen ohne Themenklasse; die Seite selbst
  trägt `data-theme` und `color-scheme` der Wahl. So prüft die Browserprobe axe und Bilder je Modus
  mit dem echten Gerüst. Andere Werte werden ignoriert (Fassung 3).
- **IDs** bekommen je Rahmen eine Vorsilbe (`hell-iban`, `dunkel-iban`), damit sie trotz zweier
  Rahmen auf der Seite eindeutig bleiben (`test_ids_je_seite_eindeutig`).
- Beispieldaten und Texte wie auf der Zeichenfläche: erfunden, keine Daten der Gesellschaft (A101).
  Die Texte stehen als Konstanten in `seiten/muster.py` und laufen durch `_()` (`en.yaml`).

### L10 Bildvergleich und Maßprobe

1. **Referenzbilder der Leinwand** (Schritt 5): `node scripts/browserprobe/leinwand.mjs --quelle
   docs/design/2026-10-26-leinwand --ziel scripts/browserprobe/ergebnisse/leinwand` legt je
   Zeichenfläche eine helle und eine dunkle Kopie im Ergebnisordner an (`{{theme}}` → leer bzw.
   `dunkel`; in „Bausteine“ `{{th.klasse}}`/`{{th.titel}}` → hell bzw. dunkel; `support.js` fehlt
   und wird nicht gebraucht). Es öffnet sie in der Breite der Zeichenfläche (1440 bzw. 390 px) und
   speichert ganzseitige Bilder. `sc-if`-Zweige erscheinen untereinander (die Arbeitsfläche zeigt
   alle vier Zustände); als Referenz genügt das. Beim Planen erprobt: 20 Bilder, `scrollWidth`
   gleich der Fensterbreite.
2. **Bilder der Umsetzung** (Schritt 14, `probe.mjs --vergleich`): `/muster` ohne Parameter bei
   1440 px (beide Rahmen), `/muster?theme=hell` und `?theme=dunkel` bei 390 px; `/` und
   `/pruefen` bei 1440 und 390 px, hell und dunkel; dazu `/pruefen/{id}`, `/freigaben` und
   `/menue` bei 390 px sowie `/pruefen/{id}` bei 1440 px.
3. **Gegenüberstellung** `ergebnisse/<datum>-vergleich.html`: eine lokale Datei mit den Bildern
   nebeneinander (Leinwand | Umsetzung) und je Paar einem Satz, was P1 abdeckt und was P2/P3
   bringen. Kein Pixelvergleich als Abbruchgrund (Spec 8): Die Inhalte unterscheiden sich, solange
   P2 und P3 fehlen.
4. **Maßprobe** (bricht ab, Teil von Schritt 14) aus berechneten Stilen gegen L1–L4: alle Token hell
   und dunkel (`getComputedStyle(document.documentElement).getPropertyValue(…)`) gleich der Tabelle
   L1; Kopfleiste 56 px; untere Leiste 64 px (ohne Safe Area); Seitenleiste 232 ± 1 px; Karte mit
   Radius 10, Rahmen 1 px, Innenabstand 20/24; Knopf ≥ 44 px mit Radius 6; Reiter-Strich 3 px in
   `--akzent`; gewählte Optionskarte 2 px; Feldrand 1 px, im Fehler 2 px in `--fehler`; Fokusring
   3 px mit 2 px Abstand; Pille mit `white-space: nowrap`, 13 px, 600; Etikett in Versalien; Betrag
   ohne Umbruch. Auf `/muster` gelten dieselben Werte in beiden Rahmen.
5. **Handprüfung des Nutzers:** die Gegenüberstellung öffnen und je Paar bestätigen („wie die
   Leinwand“ oder Abweichung mit Bild); das Protokoll steht im PR. **Python-Playwright** gibt es im
   venv nicht (`/opt/accounti/.venv` ohne `playwright`, am 26.10.2026 geprüft) und soll es wegen
   AK60 auch nicht geben; die Bilder macht die Node-Probe aus Fassung 3. Fehlen die Browser (kein
   Download freigegeben, Offener Punkt 6), bleibt der Vergleich eine Handprüfung: die Leinwand im
   Design-Werkzeug neben der laufenden Anwendung bei 1440 und 390 px.

---


## Entscheidungen

### Gerüst und Navigation

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Bereiche | `Bereich` (Enum, Reihenfolge = A1): `uebersicht`, `pruefen`, `belege`, `bank`, `rechnungen`, `steuern`, `auswertungen`, `freigaben`; abgesetzt `einstellungen`. Jeder `Navigationspunkt` gehört zu einem Bereich; je Bereich zeigt die Navigation **einen** Eintrag (den mit der kleinsten `reihenfolge`, den die Rolle öffnen darf), mit Symbol, Titel und Zähler. Ein Bereich ohne registrierte Seite oder ohne Recht entfällt (A2) | Reihenfolge und Abgrenzung aus der Spec an einer Stelle; spätere Pakete tragen nur einen `Navigationspunkt` ein |
| Rechte je Punkt | `recht: Recht \| frozenset[Recht]` – ein `frozenset` heißt „eines genügt“. Freigaben: `frozenset({ZAHLUNG_FREIGEBEN, STEUER_FREIGEBEN})`; die **Route** `/freigaben` bleibt `LESEN` (A2) | sichtbar nur für Freigabe-Berechtigte, erreichbar für alle (Lesen der offenen Läufe) |
| Breite Bildschirme (≥ 64rem) | Seitenleiste links (`position: sticky`, volle Höhe), Kopfleiste oben: „accounti“, Gesellschaft (Marke mit Kennfarbe und Monogramm, Name; Link auf `/gesellschaft` nur bei mehr als einer Gesellschaft), rechts „Hilfe“ und Benutzermenü. Inhalt höchstens `--inhalt-max` (72rem, Leinwand; A3: ≤ 90rem), Fließtext (`p`, `li`, `dd` im Inhalt) höchstens 75ch (A3). **Aussehen** wie Zeichenfläche „Main“: Kopf 56 px, Gesellschafts-Chip, Seitenleiste 232 px mit Zählern, aktiver Eintrag auf `--akzent-flaeche` (L4, L5) | Skizze 1, Leinwand „Main“ |
| Reihenfolge im Kopf | fest, DOM-Reihenfolge = Fokusreihenfolge = sichtbare Reihenfolge: Sprunglink → „accounti“ → Gesellschaft (Link nur bei mehreren) → Hilfe → Benutzermenü bzw. -symbol. Im schlichten Kopf fehlen Gesellschaft und Benutzermenü, Hilfe steht trotzdem hinter „accounti“. Damit ist die Stelle des Hilfe-Links für einen angemeldeten Benutzer auf allen Seiten dieselbe (gleicher Index unter den fokussierbaren Elementen), zwischen angemeldeten und schlichten Seiten dieselbe **relative** Reihenfolge (WCAG 3.2.6 „same relative order“) – Auslegung von AK47 | Hilfe vor die Gesellschaft zu ziehen, trennte Fokus- und Lesereihenfolge (WCAG 1.3.2, 2.4.3); die Gesellschaft immer als Link zählen ließe die Anmeldeseite trotzdem abweichen |
| Schmale Bildschirme (< 64rem) | Kopfleiste 56 px (`--kopfhoehe: 3.5rem`) mit `padding` aus `env(safe-area-inset-top)`, `-left` und `-right` (wegen `viewport-fit=cover`): Marke (28 px, Kennfarbe + Monogramm, Name als `.unsichtbar`-Text), Seitentitel (aus dem Block `titel`, `aria-hidden="true"`, `--gr-5`), Hilfe-Symbol (44 × 44), Benutzersymbol mit Initialen (Avatar 32 px in 44 × 44, Link `/menue#konto`) – Aussehen wie „Handy-Uebersicht“, ergänzt um die Hilfe (L4). Das `h1` im Inhalt ist dort visuell versteckt (bleibt für Screenreader), damit der Titel nicht doppelt Platz kostet (Skizze 2, 5a); das `h1` selbst bleibt ohne Klasse, das Verstecken regelt `.mit-kopftitel main h1` (im schlichten Layout ohne Kopftitel bleibt es sichtbar; `test_api_sprache.py:44` prüft `<h1>Anmelden</h1>` wörtlich). Untere Leiste fest (64 px plus Safe Area, Symbol 22 über der Beschriftung, Zähler in der Beschriftung: „Prüfen 12“), Ziele in der Reihenfolge Übersicht, Prüfen, Belege, Freigaben, Mehr – nur vorhandene und erlaubte; „Mehr“ ist immer da (A4) | Skizzen 2, 8; B13; Leinwand „Handy-Uebersicht“ |
| Kopf- und Leistenhöhe bei wenig Höhe | unter `max-height: 30rem` (Querformat, 200 % Zoom auf kleinen Geräten) sind Kopfleiste und untere Leiste **nicht** fest, sondern stehen im Fluss | sonst belegten beide fast die Hälfte der sichtbaren Höhe (WCAG 1.4.10/2.4.11) |
| Kurztitel | `Navigationspunkt.kurztitel` (optional) für die untere Leiste; die Browserprobe misst bei 320 px, dass kein Titel abgeschnitten ist | fünf Ziele à 64 px; „Übersicht“ und „Freigaben“ sind knapp |
| Aktiver Bereich | der Navigationspunkt mit dem längsten Pfadpräfix der Anfrage (`/` nur exakt); trägt `aria-current="page"` in Seitenleiste, unterer Leiste und `/menue` | ein Merkmal, drei Darstellungen |
| Brotkrumen | `nav aria-label="{{ _('Brotkrumen') }}"` mit `<ol>`, letzter Eintrag `aria-current="page"`. Automatisch für jede Seite unterhalb eines Bereichs (Pfad beginnt mit dem Pfad des Bereichs + `/`): „Bereich › Seitentitel“; Seiten können eine eigene Kette übergeben (`brotkrumen=[…]`) (A7) | AK46 prüft die Regel über alle GET-Routen, ohne dass jede Seite sie selbst denken muss |
| Titel | `<title>{Seite} · {Gesellschaft} · accounti</title>`, ohne Anmeldung `{Seite} · accounti` (A5) | AK7 |
| Zähler | `Navigationspunkt.zaehler: Callable[[Session], int] \| None`. `seite()` ist `async` und ruft die Zähler der sichtbaren Punkte **in einem** Thread-Aufruf mit **einer** Sitzung der aktiven Gesellschaft – nur für ganze Seiten mit Status < 400 (nicht für Fragmente, nicht mit `HX-Request` ohne Verlaufsabruf, nicht auf Fehlerseiten: `seite(…, zaehler=False)`, B15). Die Sitzung kommt aus dem **Lesezugriff** (`api/lesezugriff.Lesezugriff`, in `app.state`, geschlossen in der `lebenszeit` von `app.py`): eigene Engine je Gesellschaft ohne `init_db`, nur lesend; SQLite nur, wenn die Datei existiert, als `file:…?mode=ro` mit `timeout` 2 s; PostgreSQL mit `connect_timeout=3` und `options=-c statement_timeout=2000 -c default_transaction_read_only=on`; die Engine entsteht außerhalb jeder globalen Sperre (Doppelprüfung beim Eintragen in den Cache). Die Zähler laufen in einem **eigenen** `concurrent.futures.ThreadPoolExecutor` des Lesezugriffs (`max_workers=8`, Namensvorsilbe `zaehler`, `shutdown(wait=False, cancel_futures=True)` in `schliesse()`), aufgerufen mit `loop.run_in_executor`; eine Gesamtfrist von 3 s (`asyncio.wait_for` darum) begrenzt die Wartezeit der Seite. Bei Ablauf kehrt `wait_for` sofort zurück, der Thread läuft im Pool zu Ende (begrenzt durch die Zeitlimits der Verbindung) – das ist Verhalten der Standardbibliothek, nicht von anyio oder Starlette abhängig, und hängende Zähler belegen keine Plätze des gemeinsamen Threadpools der Anfragen (nicht `run_in_threadpool`: dessen Abbruch hängt an anyio, das kein eigener Eintrag in `pyproject.toml` ist; `abandon_on_cancel` gibt es erst ab anyio 4.1, Starlette erlaubt ab 3.6.2). Ein Fehler oder eine Zeitüberschreitung lässt nur den Zähler weg und protokolliert die Art (`FEHLER`), nie die Seite. Zähler: `pruefschlange.anzahl_offen(s)` (ein `COUNT` auf `status = pruefung` ohne die zurückgestellten), `repo_zahlung.anzahl_laeufe(s, [ENTWURF])` (ein `COUNT`). `buchungssaetze.status` hat keinen Index: Schritt 6 misst den Zähler bei 50 000 Buchungen (Ziel < 50 ms auf SQLite); reicht das nicht, kommt `ix_buchungssaetze_status` in **dieselbe** Migration (A118: eine Migration je Datenbankart) | keine Datenbank im Event-Loop (Muster aus 10a/10b); Zähler dürfen eine Seite weder lange aufhalten noch eine Datenbank anlegen (B14, B15); `mypy --strict` findet jeden vergessenen `await` (Rückgabetyp `Coroutine` statt `HTMLResponse`) |
| `/menue` | gewöhnliche Seite ohne Skript: Bereiche (mit Zählern), Gesellschaften (je ein POST-Formular mit CSRF zum Wechseln, aktive markiert), Abschnitt `id="konto"` mit Mein Konto, Hilfe, Abmelden (POST). Jeder Eintrag ≥ 44 px hoch (A4, Skizze 8). Aussehen wie „Handy-Mehr“: drei Gruppen mit Etikett („Bereiche“, „Gesellschaft“, „Mein Konto · Name“), je eine `.gruppenliste` mit 48-px-Zeilen, Zähler und `chevron-right` (L4) | kein Hamburger-Menü, keine Fokusfalle (E14) |
| `/gesellschaft` (GET) | Liste der Gesellschaften, in denen der Benutzer eine Rolle hat: Marke (Kennfarbe, Monogramm), Name, „n zu prüfen“ (mit `LESEN`), „n Freigaben“ (nur mit Freigaberecht dort), aktive markiert, Wechsel per POST mit CSRF (bestehende Route). Die Zahlen laufen je Gesellschaft im Pool des **Lesezugriffs** (nicht über `Dienste.datenbank`, also ohne `init_db` und ohne die globale Sperre), parallel mit `asyncio.gather` und je Gesellschaft der Gesamtfrist aus „Zähler“. Ist eine nicht erreichbar, hängt sie, fehlt ihre SQLite-Datei oder läuft die Frist ab, steht dort „nicht erreichbar“, und es entsteht keine Datei (A5) | P2 nutzt dieselbe Funktion für „In anderen Gesellschaften“ (A17) und erbt die Fristen |
| Benutzermenü | ab 64rem `<details class="benutzermenue">` (Zusammenfassung: Avatar, Anzeigename, `chevron-down` wie „Main“) mit Mein Konto, einem Formular Sprache + Darstellung (`segment`-Wahlpillen, Knopf „Übernehmen“), Hilfe, Abmelden; das aufgeklappte Feld zeichnet die Leinwand nicht, es folgt L4. `accounti.js` schließt es bei `Esc` und Klick daneben; ohne JS schließt die Zusammenfassung (A6) | Aufklapper ohne ARIA-Menümuster (kein `role="menu"`, keine Fokusfalle) |
| Sprunglink, Statusbereich, Druckkopf | erster fokussierbarer Link „Zum Inhalt springen“ (`#inhalt`, `main tabindex="-1"`); ein globaler Bereich `<div id="status" role="status" aria-live="polite" class="unsichtbar">` für htmx-Ansagen (A110), der schon beim Laden der Seite im DOM steht. **P1 schreibt hinein:** Die Antworten der Arbeitsfläche (Freigeben, Korrigieren, Zurückstellen, auch 409/422) tragen ein `<div hx-swap-oob="innerHTML:#status">` mit dem Ergebnistext; die sichtbare Meldung im Fragment verliert ihr `role="status"` (sonst doppelte Ansage). Ein versteckter Druckkopf mit Gesellschaft, Seitentitel, Datum (`dienste.uhr()`) und Benutzer (A97) | A104, A105, A110; ein neu eingefügtes `role="status"` sagen Screenreader oft nicht an, ein bestehender Live-Bereich mit neuem Inhalt schon |
| Schlichtes Layout | `schlicht.html` (Kopf mit „accounti“ und Hilfe, ohne Navigation; Aussehen wie der Kopf von „Assistent-Steuern“, L5) für Anmeldung, 500 und später den Assistenten (P7) | Hilfe an derselben Stelle auch dort (AK47) |
| Zwei Formen der neuen Seiten | Jede **neue** GET-Route liefert mit `HX-Request` (kein Verlaufsabruf) ein Fragment, ohne die ganze Seite (AK58): `seite(…, teil="inhalt")` rendert dann nur den Block `inhalt` der Vorlage (`Template.blocks`, ohne Gerüst und ohne Zähler). Weil ein Block allein den Code auf oberster Ebene nicht ausführt (B19), gilt für jede solche Vorlage: **auf oberster Ebene nur `{% extends %}` und Blöcke**; `{% import "_komponenten.html" as k with context %}` und jedes `{% set %}` stehen **innerhalb** des Blocks `inhalt` (und in jedem anderen Block, der sie braucht), kein `super()` in `inhalt`. `seite()` prüft das bei jedem Aufruf mit `teil` – auch ohne `HX-Request` – einmal je Vorlage (AST über `UMGEBUNG.parse`, Ergebnis zwischengespeichert) und wirft sonst `RuntimeError`; damit scheitert schon der erste Test, der die Seite ganz rendert. Gilt für `/konto`, `/menue`, `/gesellschaft`, `/hilfe`, `/hilfe/{thema}`, `/muster`; `/muster/beispiel` ist ein eigenes kleines Fragment. Die GET-Seiten aus 10a/10b bleiben, wie sie sind (`HTMX_FORMEN`: `ganze_seite`, Grund „Bestand“; ihre Importe dürfen oben bleiben) | AK58 wörtlich, ohne Abweichung; kostet eine Verzweigung in `seite()`, eine Prüfung und zwei Tests; eigene Teilvorlagen je Seite (wie `_arbeitsflaeche.html`) gingen auch, verdoppelten aber die Dateien jeder neuen Seite |

### Design-System

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Eine CSS-Datei | **nur** `statisch/accounti.css` (Ebenen `@layer token, basis, layout, komponenten, seiten, hilfen, druck`). `pruefen.css` entfällt, seine Regeln werden Komponenten bzw. stehen unter `seiten`. Auch 10b-2 und P2–P7 schreiben in diese Datei; das Budget 40 KB gilt für alles (A99). **Übergang bis Ende Schritt 12:** die alten Regeln der bestehenden Seiten – die aus `accounti.css` und der ganze Inhalt von `pruefen.css` (als `@layer bestand { … }`) – stehen in einer Ebene `bestand` **vor** `komponenten` (`@layer token, basis, layout, bestand, komponenten, seiten, hilfen, druck`), auf die neuen Token umgeschrieben (`--gedaempft` → `--text-2`, `--hintergrund` → `--grund` bzw. `--flaeche-2`, `#fff` → `var(--beleg-hintergrund)`). Jeder Seiten-Commit in Schritt 12 löscht die Regeln seiner Seite aus `bestand`; am Ende entfallen `pruefen.css` und die Ebene | ein Budget, eine Prüfung; keine Reihenfolgeprobleme zwischen Dateien. Regeln ohne Ebene schlügen jede Komponente, in `seiten` schlügen sie sie ebenfalls (spätere Ebene gewinnt) – nur vor `komponenten` gewinnen bei gleichen Klassennamen (`.knopf`, `.reiter`, `.hinweis`, `.haken`) die neuen Komponenten (B20) |
| Token | Farben **wie die Leinwand** (L1) – das ist wörtlich die Tabelle aus A89 (`--grund`, `--flaeche`, `--flaeche-2`, `--text`, `--text-2`, `--linie`, `--linie-stark`, `--akzent`, `--akzent-text`, `--akzent-flaeche`, `--fokus`, `--ok`/`--ok-flaeche`, `--warn`/…, `--fehler`/…, `--info`/…), dazu aus der Leinwand `--fehler-text`, `--schatten` und die Kennfarben `--marke-1` … `--marke-6` (fünf aus der Leinwand, Oliv aus Fassung 3), von P1 `--schleier` (Hover) und `--beleg-hintergrund: #ffffff` (beide Modi, für den PDF-Rahmen). Maß-Token nach L2/L3: `--gr-1` … `--gr-9`, `--a-1` … `--a-8` mit `--a-45`, `--a-55`, `--a-65`, `--fein-1/-3/-5`, `--radius-xs` … `--radius-rund`, `--kopfhoehe`, `--leistenhoehe`, `--seitenleiste`, `--inhalt-max`, `--formular-max`, `--einstellungen-max` | die Spec hat die Farbwerte nachgerechnet, Fassung 4 die neuen (L1); ein Token ohne Wert in beiden Modi fällt im Test auf; `test_token_wie_leinwand` hält die Farben an der Leinwand fest |
| Hell/dunkel | `:root, .thema-hell { color-scheme: light; …hell… }`; `:root[data-theme="dunkel"], .thema-dunkel { color-scheme: dark; …dunkel… }`; `:root[data-theme="auto"] { color-scheme: light dark }` und `@media (prefers-color-scheme: dark) { :root[data-theme="auto"] { …dunkel… } }`. Der Dunkel-Block steht **zweimal**, ein Test verlangt beide gleich. Die Klassen `.thema-hell`/`.thema-dunkel` braucht nur `/muster`, um beide Modi nebeneinander zu zeigen (L9); sie setzen dazu `background: var(--grund)` und `color: var(--text)`. Dazu `<meta name="color-scheme">` mit `light dark`, `light` bzw. `dark` passend zur Wahl, damit vor dem Laden der Datei nichts aufblitzt (E16, A89) | ohne `light-dark()` (Safari < 17.5); ohne Skript, ohne Flackern; Themenrahmen ohne `style=` |
| Formularelemente | `input`, `select`, `textarea`, `button` bekommen Hintergrund, Text- und Randfarbe aus Token (`--flaeche`, `--text`, `--linie-stark`), Schrift geerbt; `accent-color: var(--akzent)` für Kontrollkästchen und Optionsfelder (18 px wie die Leinwand). `kbd` wie in der Leinwand ohne Hintergrund in `--text-2` mit Rand `--linie`, im primären Knopf in `currentColor` – **ohne** `opacity` (L1, L4). Kontrast der Schrift: auf Fläche 6,68 / 7,55, auf Fläche 2 5,71 / 6,79, im primären Knopf 7,63 / 9,02 | I9 und AK4 – `color-scheme` allein färbt nicht alle Bedienelemente; mit `opacity: .75` fiele `kbd` im stillen Knopf auf 4,15 : 1 |
| Schrift | `system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", sans-serif`; Größen aus der Skala L2 (`--gr-1` … `--gr-9`: 12/13/14/16/18/20/22/28/40 px – die Spec-Stufen 14/16/18/22/28 plus 12, 13, 20, 40 aus der Leinwand); Zeilenhöhe 1,5 (Überschriften 1,25, Kennzahl 1); Gewichte nur 400 und 600 – auch `strong`, `b`, `th`, `h1`–`h6`, `summary`, `legend` werden auf 600 gesetzt (sonst 700 aus dem Browser), das Kürzel der Marke ebenfalls (Leinwand 700); `font-variant-numeric: tabular-nums` auf `body` wie in der Leinwand, `.zahl` regelt nur noch die Ausrichtung (A90, E15) | AK50; L2 |
| Raster und Layouts | 4-px-Raster über `--a-n` mit den Zwischenstufen 20/28/40 px; Feinstufen 2/6/10 px nur in `@layer komponenten`; Werte der Leinwand außerhalb des Rasters nach der Rundungsregel aus L3. Radien nur über die Radius-Token (L3). Breakpoints **nur** 40rem, 64rem, 90rem (dazu `max-height: 30rem`); Layoutklassen `.layout-einspaltig`, `.layout-zweispaltig` (Flex-Basis 420/440 px wie die Leinwand: zwei Spalten, sobald beide Platz haben, sonst untereinander), `.layout-karten` (`repeat(auto-fit, minmax(min(18rem, 100%), 1fr))`, Abstand 16 – das `min()` hält 320 px ohne Überlauf), `.layout-einstellungen` (Unternavigation 220–260 px links, Inhalt bis 820 px; darunter die Unternavigation als Liste oben), `.layout-formular` (bis 760 px). Ein Schatten (`--schatten`) nur für Karten, freistehende Tabellen und das Benutzermenü im hellen Modus; dunkel mit Linie (A91, L5) | Spec A91, Leinwand; `minmax(18rem, 1fr)` allein liefe bei 320 px mit 16 px Rand über |
| Fokus | `:focus-visible { outline: 3px solid var(--fokus); outline-offset: 2px }` für alle Bedienelemente – 3 px wie die Leinwand; A104 („2-px-Ring“) gilt als Mindestmaß, AK55 verlangt ≥ 2 px (Auslegung, L7 Nr. 8). `html { scroll-padding-block-start: calc(var(--kopfhoehe) + var(--a-2)) }`, unter 64rem zusätzlich `scroll-padding-block-end` in Höhe der unteren Leiste plus `env(safe-area-inset-bottom)`; Seiten mit Sammelleiste (`.mit-sammelleiste`) zusätzlich ihre Höhe (A104). Zellen und Karten haben ≥ 8 px Innenabstand, damit `overflow: clip` den Ring (3 + 2 px) nicht abschneidet | 2.4.11; Ring nie direkt am Akzent oder am Gefahr-Knopf (L1) |
| Zielgrößen | Klickziele mindestens 24 × 24 px, bei `@media (pointer: coarse)` 44 × 44 px; Kontrollkästchen und Optionsfelder sind sichtbar 18 px (Leinwand), ihre Klickfläche ist das umschließende `label` (`.haken-ziel`, mindestens 24 × 24 bzw. 44 × 44). Kopf-Bedienelemente 40 px und `summary` 32 px gelten nur bei feinem Zeiger. Links in Tabellenzellen und Listen als Block mit Innenabstand; ausgenommen Links im Fließtext (A106) | AK55; L7 Nr. 20, 24 |
| Bewegung | `transition` nur für `color`, `background-color`, `border-color`, `outline-color`, `opacity`, Dauer ≤ 150 ms (`120ms`); `@media (prefers-reduced-motion: reduce)` setzt `transition-duration` und `animation-duration` auf 0 s. Die Ladeanzeige dreht sich **nicht** (Text „Wird geladen …“ mit Symbol, eingeblendet über Deckkraft) (A100) | keine Animation außerhalb der erlaubten Eigenschaften |
| Tabellen | Komponente `tabelle` (Aufruf-Makro) in der Optik der Leinwand (L4: Rahmen 1 px `--linie` mit `--radius-karte` und `overflow: clip`, freistehend mit `--schatten`, kein `min-width`): `caption` Pflicht (auf Wunsch `.unsichtbar`), Kopf auf `--flaeche-2`, `position: sticky` unter der Kopfleiste, Linien statt Zebra, Zahlen rechtsbündig, Summenzeile `tfoot` mit 2 px `--linie-stark` abgesetzt, gewählte Zeile auf `--akzent-flaeche`; Sortierung über Links mit `aria-sort`; Dichte `normal` (Zeile ≥ 44 px) und `kompakt`. **Unter 40rem** werden Zeilen Karten: `thead` visuell versteckt (nicht `display: none`), `td::before { content: attr(data-label); content: attr(data-label) / "" }`, und `table`, `thead`/`tbody`, `tr`, `th`, `td` tragen ausdrücklich `role="table"`, `"rowgroup"`, `"row"`, `"columnheader"`, `"cell"`. Breite Tabellen (`kompakt`) stehen in `.tabelle-rahmen` mit `tabindex="0"`, `role="region"` und `aria-label` = Caption (axe `scrollable-region-focusable`) (A93, A111) | I1 behoben; Semantik bleibt beim Umbruch erhalten |
| Beschreibungsliste | Komponente `angaben`: Label-Spalte `fit-content(14rem)`, Wert `minmax(0, 1fr)`, `overflow-wrap: anywhere`; unter 40rem Label über dem Wert (A92) | behebt I11 („Verwendungszweck“ läuft nicht mehr in den Wert) |
| Komponenten | Makros in `vorlagen/_komponenten.html` (Liste unter „Schnittstelle“); Attribute, die Seiten mitgeben (htmx, `data-taste`), gehen als Zuordnung an das Makro. Das Makro lässt nur Namen aus einer **Positivliste** zu (Start: `hx-` + `get\|post\|target\|swap\|select\|push-url\|disabled-elt\|indicator\|vals\|confirm`, `data-` + `[a-z-]+`, `aria-` + `[a-z]+`, dazu `form`, `formaction`, `formnovalidate`, `autofocus`; erweitert wird nur mit Test), sonst scheitert das Rendern; die Werte escapt `xmlattr`. Die Schlüsselprüfung von `xmlattr` selbst gibt es erst ab Jinja 3.1.3/3.1.4, `pyproject.toml` erlaubt `jinja2>=3.1` – die Positivliste hängt nicht an der Version. Formularfelder (`feld`, `codefeld`, `optionen`, `haken`) haben einen Parameter `id` (Standard: der Name), aus dem `for`, `<id>-hilfe` und `<id>-fehler` entstehen (B16). Wo ein Makro `name` und `value` schreibt, steht `name="…" value="…"` direkt hintereinander (die Testhelfer `formularwert` und `freigabe_hash` suchen genau das). `_makros.html` behält nur fachliche Bausteine (`konto`, `schluessel`, `meldung_text`); `fehlerkasten`/`feldfehler` werden durch `fehlerliste`/`feld` ersetzt (A92). **Aussehen, Maße und Zustände jeder Komponente: L4.** Neu gegenüber Fassung 3 sind `aufklapper`, `sammelleiste`, `marke` und `avatar` sowie `feld(warnung, bestaetigt)`, `karte(kennzahl)`, `zaehler(betont)`, `knopf(groesse, breit, laedt)`, `reiter(geteilt)`, `tabelle(in_karte)` und `zeile(gewaehlt)`. Bis Schritt 12 stehen die alten Regeln in `bestand`. Neue Klassen meiden deshalb deren übrige Namen (`.fehler`, `.meldung`, `.flaeche`, `.daten`, `.aktionen`, `.seiten`, `.klein`, `.liste`): Der Fehlerkasten heißt `.hinweis-fehler`, Seitenblättern `.seitenblaettern`, der kleine Knopf `.knopf-klein`. Bei den vier gleichnamigen Klassen (`.knopf`, `.reiter`, `.hinweis`, `.haken`, B20) gewinnt die Komponente nur bei den Eigenschaften, die sie selbst setzt. Sie setzt deshalb jede Eigenschaft, die die alte Regel setzt, ausdrücklich, z. B. `.hinweis { border: 0 }` gegen den alten linken Balken – sonst sähe `/muster` bis Schritt 12 anders aus als die Leinwand (die Maßprobe in Schritt 5 fängt das). `.unsichtbar` steht in `@layer hilfen` (nach `bestand`) | AK51 vergleicht Makronamen und Musterseite; fachliche Bausteine gehören nicht auf `/muster` |
| Symbole | Sprite `statisch/symbole.svg` aus **lucide-static 1.55.0**, 36 Symbole nach der Leinwand (L6, Liste unter „Schnittstelle“); Größen über `.symbol-14`, `-16`, `-18`, `-22`, `-28`, `-40`, kräftiger Strich (2,4) in Pillen und Meldungen am Feld über `.symbol-kraeftig`; je `<symbol id viewBox="0 0 24 24">` nur mit den Formen; Strich, Füllung und Linienenden setzt `.symbol` in CSS (`fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round`) – sie erben in die `<use>`-Instanz. Einbindung `<svg class="symbol" aria-hidden="true" focusable="false"><use href="/statisch/symbole.svg?v={{ version }}#name"></use></svg>`, mit Beschriftung `role="img" aria-label`. Erzeugt von `scripts/symbole.py` (liest den entpackten Tarball, prüft Version und SHA-512, schreibt Sprite und Lizenz); `LIZENZ-lucide.txt` = vollständige `LICENSE` (ISC **und** MIT-Teil) mit Kopf (Version, Integrität, Symbolliste und einer Zuordnung neuer → alter Name für die Symbole, die der MIT-Teil unter Feather-Namen führt: `triangle-alert` ← `alert-triangle`, `circle-help` ← `help-circle`, `circle-x` ← `x-circle`, `circle-alert` ← `alert-circle`) (A96, E15) | Lizenz verlangt den Hinweis für beide Teile; die vollständige `LICENSE` genügt rechtlich, die Zuordnung macht sie nachvollziehbar; gleiche Herkunft wie das Sprite; kein npm-Paket zur Laufzeit |
| Kennfarbe | `kennfarben(kuerzel_alle, gewaehlt={}) -> dict[str, int]`, **immer** mit allen Gesellschaften der Registry (`dienste.gesellschaften`), nie nur mit denen des Benutzers – so sieht jeder Benutzer dieselbe Gesellschaft in derselben Farbe. Gewählte zuerst, dann in alphabetischer Reihenfolge der Kürzel `1 + (erste 4 Byte von SHA-256(kuerzel)) % 6`, bei Belegung die nächste freie (zyklisch); ab sieben Gesellschaften wiederholen sich Farben. Kommt eine Gesellschaft hinzu oder fällt weg, kann eine Gesellschaft, deren Farbe durch Ausweichen entstand, eine andere Farbe bekommen (Grenze; mit der Wahl in P5 ist die Farbe fest). Wirkung nur über `class="marke-n"`, nie `style=` (A5). **Werte aus der Leinwand** (L1; je ≥ 4,27 : 1 zu Fläche, Grund und Fläche 2, Kürzel darauf ≥ 4,99 : 1): hell `#7b3fa0`, `#1f6fa8`, `#2f7d5b`, `#a8551f`, `#a8244f` und Oliv `#5f6b1f` aus Fassung 3; dunkel `#c79ae6`, `#8db8f0`, `#7fd1ad`, `#f0a46a`, `#f08fb0`, `#b5c25a`. **Monogramm** (B24): `monogramme(namen_alle) -> dict[str, str]`, ebenfalls immer über die ganze Registry, Regel unter „Schnittstelle“ | stabil je Kürzel, solange die Registry gleich bleibt, bei bis zu sechs Gesellschaften ohne Dopplung; ein reiner Hash wäre auch bei Änderungen der Registry stabil, doppelte Farben schon bei zwei Gesellschaften (1 : 6) nähmen der Kennfarbe aber ihren Zweck. Die Leinwand-Farben liegen nah an den Statusfarben (L1) – hingenommen, weil das Monogramm immer als Text dasteht (1.4.1) und Status immer Wort und Symbol trägt |
| Druck | `@layer druck` in `@media print`: Navigation, Leisten, Knöpfe, Formulare aus; Schwarz auf Weiß; `.druckkopf` sichtbar; `tr { break-inside: avoid }`, `thead { display: table-header-group }` (Karten-Umbruch gilt im Druck nicht) (A97) | AK8 |

### Vorlieben am Benutzer

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Spalten | `auth_benutzer.darstellung` (`auto`/`hell`/`dunkel`, Standard `auto`), `fachansicht` (Standard aus), `betraege_verbergen` (aus), `tastenkuerzel` (an); alle `NOT NULL` mit Server-Standard, damit bestehende Zeilen gültig sind; `sprache` bleibt (A87, A118) | E16 B; P2/P3 lesen dieselben Felder |
| Fachfunktion | `auth.dienst.setze_vorlieben(s, benutzer_id, Vorlieben(sprache=…, darstellung=…, …))` – **nur** die gesetzten Felder ändern sich (`UNVERAENDERT` als Platzhalter), als gezieltes `UPDATE` der Zeile wie heute `setze_sprache`, nie über `speichere_benutzer` (B18); ersetzt `setze_sprache` (entfällt, Aufrufer und Tests umgestellt) (A88). `_BENUTZER_FELDER` liest die Vorlieben, `speichere_benutzer` schreibt sie und `sprache` nur beim Anlegen | ein Weg; Teilformulare (Benutzermenü, Tastenhilfe, 308) ändern nichts anderes; kein verlorenes Update, wenn parallel eine Anmeldung `letzte_anmeldung_am` schreibt |
| Protokoll | Vorlieben schreiben **kein** Ereignis in `auth_ereignisse` und nichts ins Journal: reine Anzeige-Vorlieben fallen unter die Ausnahme in A113 und sind keine buchführungsrelevanten Daten im Sinn der GoBD (wie die Sprachwahl in 10b) | A113, A116 |
| Formular | `/konto` mit einer Formulargruppe je Vorliebe als **Optionsfelder** (auch an/aus: zwei Optionen, kein Kontrollkästchen) und einem Knopf „Speichern“. Ein fehlendes Feld heißt „unverändert“ – mit Kontrollkästchen hieße ein fehlendes Feld „aus“, und Teilformulare würden andere Werte zurücksetzen | Teil-Aktualisierung ohne Sonderfelder |
| htmx | `POST /konto/vorlieben` mit `HX-Request` antwortet `200` mit `HX-Refresh: true` (Sprache und Darstellung betreffen `<html>`), ohne `HX-Request` mit 303 auf `weiter` (`sicheres_ziel`). **Kein Absenden bei Auswahl** (B12) | WCAG 3.2.2; Pfeiltasten in Optionsgruppen |
| Alter Pfad | `POST /einstellungen/sprache` antwortet **308** auf `/konto/vorlieben` (Methode und Körper bleiben: `csrf`, `sprache`, `weiter`), entfällt ein Release später (A87) | Lesezeichen und offene Seiten alter Fassung |
| Ohne Anmeldung | `data-theme="auto"`, Sprache nach `Accept-Language` | E16 |
| Tastenkürzel | `<body data-tastenkuerzel="an">` bzw. `"aus"`; `pruefen.js` liest nur dieses Attribut, kein `localStorage`; die Tastenhilfe bietet statt des Hakens ein kleines Formular „Tastenkürzel ausschalten“ (`POST /konto/vorlieben`, `tastenkuerzel=aus`, `weiter` = aktuelle Seite) (A87, AK45) | geht mit auf andere Geräte; WCAG 2.1.4 bleibt erfüllt |
| CLI | kein CLI-Befehl für Vorlieben – Ausnahme nach A113 (reine Anzeige-Vorlieben, wie die Sprachwahl in 10b) | Spec |

### Barrierefreiheit, Formulare, Fehler

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Codefeld | Komponente `codefeld(variante, wechsel_href, fehler, id="einmalcode")`: **ein** Feld `name="einmalcode"`, `autocomplete="one-time-code"`, `inputmode="numeric"`, sichtbares Label „Code aus Ihrer Authenticator-App“ (Anhang B), Einfügen erlaubt, kein `pattern`, kein `maxlength` (Leerzeichen toleriert der Server schon). Der Link „Wiederherstellungscode verwenden“ steht **beim Label, vor dem Feld** (sichtbar, bevor jemand tippt) und führt auf dieselbe Seite mit `?code=wiederherstellung` **und dem bisherigen `weiter`** (auf `/anmelden` `?weiter=…&code=wiederherstellung`, über `sicheres_ziel`): dann `inputmode="text"`, `autocapitalize="off"`, `spellcheck="false"`, Label „Wiederherstellungscode“, Rückweg „Code aus der App verwenden“. Der Server nimmt in beiden Fällen beides an (wie heute). Der Neuaufruf verwirft Eingaben im Formular (Benutzer, Passwort; auf `/buchungen/{id}` Grund und Datum) – Grenze, B17 (A109) | 3.3.8; Wiederherstellungscodes enthalten Buchstaben (`auth/wiederherstellung.ALPHABET`), die Zifferntastatur kann sie nicht; ohne JS gibt es keinen Wechsel ohne Neuaufruf, und ein GET-Absenden des Formulars brächte das Passwort in die URL |
| Formularfeld | Label über dem Feld, Hilfetext darunter (`id="<id>-hilfe"`), Fehler darunter mit Symbol und Wort „Fehler:“ (`id="<id>-fehler"`), `aria-describedby` auf beide, `aria-invalid="true"`; `id` als Parameter (Standard: Name), damit zwei Formulare einer Seite (`grund-k`/`grund-s`) und mehrere Codefelder (`einmalcode-lauf-3`) eindeutig bleiben (B16); Breitenklassen `breite-schmal`, `breite-mittel`, `breite-breit`; vollständige `autocomplete`-Werte (A94) | AK53 |
| Fehlerliste | `fehlerliste(fehler, ids={})`: `role="alert"`, Überschrift „Bitte prüfen“, je Fehler ein Link `#<id>` – `ids` bildet den Feldnamen der Fachfunktion (`StornoError.feld`, z. B. `grund`) auf die id im Formular ab (`grund-k`), ohne Eintrag gilt der Name; mit `data-fokus` (accounti.js setzt den Fokus nach Laden bzw. Austausch). Eingaben bleiben erhalten, außer Passwörtern und Codes (A108) | 3.3.1, 3.3.3 |
| Hinweise | `hinweis(art, neu=False)`: Symbol, Wort („Hinweis“, „Erledigt“, „Achtung“, „Fehler“) und Text; `role="status"` bzw. `role="alert"` **nur** mit `neu=True` (A95) | dauerhafte Hinweise werden nicht bei jedem Laden angesagt |
| Leere Zustände | `leer(satz, aktion_text, aktion_href)` – jede Liste der bestehenden Seiten bekommt einen Satz und einen **Link** zur nächsten Aktion (AK54). Hat die nächste Aktion noch keine Seite, führt der Link auf den Abschnitt der Hilfe, der den Weg beschreibt, z. B. „Kein Zahlungslauf wartet auf Freigabe.“ → „So entsteht ein Zahlungslauf“ (`/hilfe/freigaben#zahlungslauf`, dort `accounti zahlung vorschlag`). `leer` setzt **kein** `role` – das dauerhafte `role="status"` aus `pruefen/liste.html:40` entfällt (A95) | AK54; ein Leerzustand ist keine neue Meldung |
| 403 | Hilfsfunktion `verweigert(a, *rechte) -> HTTPException`; `detail` ist eine `Verweigerung(text, rechte, rollen)`: `text` ist der **bisherige** Satz „Ihre Rolle in %(gesellschaft)s erlaubt das nicht“ als eigene msgid (bleibt wörtlich, auch auf Englisch; `test_i18n.py:66–68` prüft Gleichheit, `test_api_sprache.py:47` Teilstring), `rechte` die fehlenden `Recht`-Werte, `rollen` die Rollen, die eines davon enthalten. `fehler.html` rendert daraus strukturiert „Nötig: <Recht> …“ (Name aus `RECHT_TEXT`, übersetzt) und „Enthalten in den Rollen <span lang="de">buchhalter</span> …“ (Rollenkennungen mit `lang="de"` auch in der englischen Oberfläche, A112). `str(Verweigerung)` ist der Satz (JSON der API, Protokoll). `erfordert()` und die zwei zusammengesetzten Prüfungen in `seiten/pruefen.py` (um :593 und :650) nutzen sie (A9) | AK48 „403 nennt die fehlende Rolle“; eine neue Gesamt-msgid ließe die alte verwaisen (`test_keine_verwaisten_eintraege`), in einem escapten `Text` ginge `lang="de"` nicht |
| Fehlerseiten | `fehler.html` im Gerüst mit `h1` je Status (403 „Keine Berechtigung“, 404 „Nicht gefunden“, 409 „Inzwischen geändert“, 413 „Zu groß“, 422 „Angaben prüfen“, 503 „Gerade beschäftigt“, sonst „Fehler“), der Meldung und einem Link zurück (übergebenes `zurueck`, sonst Start des aktiven Bereichs, sonst `/`). Alle Fehlerwege rendern mit `zaehler=False` (B15). Ein 404 ohne Route versucht `vielleicht_angemeldet`, damit das Gerüst mit Navigation erscheint; das liest die Systemdatenbank und schreibt dabei womöglich (Sitzung beenden bzw. höchstens alle 60 s als aktiv markieren, B23). Scheitert das an der Datenbank (`SQLAlchemyError`, etwa „database is locked“ nach der Wartezeit), gibt `vielleicht_angemeldet` `None` zurück: Die 404 bzw. die Hilfe erscheint im schlichten Layout, das Protokoll nennt nur die Art – nie wird daraus eine 500. Mit `HX-Request` liefern 403/404/409/413/422/503 das Fragment `_fehler.html` (Hinweis-Komponente, `role="alert"`); 409/422 tauscht htmx ein, die übrigen zeigt der Fehlerhinweis (A9, A115) | AK48, AK58 |
| 500 | Die Middleware rendert `fehler_500.html` (erbt `schlicht.html`) direkt mit der Jinja-Umgebung: Sprache nur aus `Accept-Language`, **keine** Datenbank, kein Benutzer, kein Ausnahmetext, kein Traceback; Link „Zur Startseite“ und Hilfe. `/api/` bleibt JSON (A9) | wer bei 500 noch die Datenbank fragt, scheitert womöglich ein zweites Mal |
| Fokus nach Austausch | `accounti.js`: nach `htmx:afterSettle` erhält das erste Element mit `data-fokus` im neuen Inhalt den Fokus (Überschrift mit `tabindex="-1"` bzw. nächste Zeile); während einer Anfrage trägt das Ziel `aria-busy="true"` (A104, A110) | P3 nutzt beides; P1 liefert den Mechanismus und den Test der Musterseite |

### Hilfe

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Seiten | `/hilfe` (Übersicht, Begriffe aus Anhang B) und `/hilfe/{thema}` für jedes Thema aus `Hilfethema` = alle Bereiche + `anmeldung` + `konto`. Der Pfadparameter ist ein `str`, die Route bildet ihn selbst auf `Hilfethema` ab: unbekannt → 404, bekannt ohne Eintrag in `HILFE` → ebenfalls 404 (nie 422 aus der Validierung, nie 500). Inhalt als Daten in `api/hilfe_inhalt.py` (Kurzanleitung als Liste von `N_()`-Texten, Begriffe, Tastenkürzel), gerendert von **einer** Vorlage. P1 schreibt Hilfe für Übersicht, Prüfen, Freigaben, Anmeldung und Konto. Ein Test verlangt für jeden Bereich der **echten** Registry einen Eintrag; gegen die Test-Registry prüft ein zweiter Test nur, dass `fehlende_hilfe(punkte)` die Bereiche ohne Eintrag (Belege, Steuern, Auswertungen, Einstellungen) meldet – spätere Pakete schreiben ihre Hilfe mit (A8) | 3.2.6; i18n-Test sammelt die Texte über `N_()`; FastAPI beantwortet einen ungültigen Enum-Pfadparameter mit 422 |
| Zugang | ohne Anmeldung erreichbar (Rechte-Matrix `OFFEN`): statischer Inhalt ohne Daten der Gesellschaft; angemeldet mit Gerüst und Navigation (`vielleicht_angemeldet`) | der Hilfe-Link der Anmeldeseite muss funktionieren |
| Hilfe-Link | in Kopfleiste und schlichtem Kopf immer an derselben Stelle der festen Kopf-Reihenfolge (nach „accounti“ und Gesellschaft, vor dem Benutzermenü bzw. -symbol; Entscheidung „Reihenfolge im Kopf“); Ziel: `/hilfe/<aktiver Bereich>`, auf der Anmeldung `/hilfe/anmeldung`, sonst `/hilfe` | AK47 in der Auslegung „gleicher Index je angemeldetem Benutzer, gleiche relative Reihenfolge überall“ |
| Tastenkürzel | eine Quelle `api/hilfe_inhalt.TASTEN_PRUEFEN` für Tastenhilfe der Arbeitsfläche, Hilfeseite und den Test gegen `pruefen.js` | kein Auseinanderlaufen (P3 ändert die Bedeutungen an einer Stelle) |
| Externe Links | keine; Rechtsbezüge als Text (§-Angaben) | AK47 |

### Werkzeuge

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Browserprobe | Node-Werkzeug `scripts/browserprobe/` mit `package.json` (devDependencies **genau** `playwright` 1.64.0, `axe-core` 4.14.0), `package-lock.json` (Integritätswerte wie unter Recherche), `.npmrc` mit `ignore-scripts=true`; Start `npm ci` und `npx playwright install chromium firefox`. Die Browser selbst kommen von Microsofts CDN und sind durch die Lockdatei **nicht** abgesichert – das steht in `README.md` der Probe, in `CONTRIBUTING.md` und `THIRD-PARTY.md`. Auf dem Server braucht 1.64.0 einen Chromium-Download (Revision 1248, Recherche); er geschieht erst nach Freigabe durch den Nutzer (vor dem ersten Lauf in Schritt 5). Ohne Freigabe gilt der Rückfall `playwright` 1.59.1 mit dem vorhandenen Chromium 1217 (Werte unter Recherche). `probe.mjs` liest `probe.json` aus `python -m tests.browserprobe_welt` (Wegwerf-Bestand mit beiden Testgesellschaften, je Rolle ein Benutzer mit TOTP-Geheimnis, Prüfschlange mit PDF-Beleg, Zahlungslauf; startet `accounti`-App mit uvicorn auf 127.0.0.1), meldet sich je Rolle an und misst die Kriterien aus Schritt 14. axe läuft in einem eigenen Kontext mit `bypassCSP: true` (die eingespielte `axe.min.js` und das Textabstands-Stylesheet aus WCAG 1.4.12 wären sonst durch die CSP gesperrt); die CSP-Prüfung (AK5, Konsole) läuft in einem Kontext **ohne** Umgehung. Ergebnis: `ergebnisse/<datum>-<browser>.json` und Bildschirmfotos (in `.gitignore`); Zusammenfassung in den PR | AK1, AK2, AK4, AK6, AK44 … brauchen einen echten Browser; die Probe wird für P2–P7 wiederverwendet. Python-Playwright verstieße gegen AK60 (neue Abhängigkeit in `pyproject.toml`); nichts davon landet im Abbild (`Dockerfile` kopiert `src/`, `alembic/` und `alembic.ini`, aber nicht `scripts/` und `tests/`) |
| Firefox | läuft beim Nutzer (`node probe.mjs --browser firefox`); auf dem Server nur Chromium (Recherche) | wie 10b |
| Sprite-Erzeuger | `scripts/symbole.py PFAD-ZUM-ENTPACKTEN-PAKET [--tarball DATEI]` – prüft `package.json` (`version` = 1.55.0) und, mit `--tarball`, die SHA-512; schreibt `symbole.svg` und `LIZENZ-lucide.txt`. Nur für Entwickler, im Repository nachvollziehbar | Herkunft des Sprites reproduzierbar, wie `scripts/pruefwerkzeuge_installieren.sh` |
| Rückverfolgung | `tests/test_spec_rueckverfolgung.py` liest die abgelegte Spec: jede Anforderung A1–A126 steht in Anhang D und in mindestens einem Kriterium; jedes Kriterium nennt nur vorhandene Anforderungen (Spec, Anhang D: „Prüfskript im Plan von P1“). Bereichsangaben in den Klammern hinter Kriterien (`A1–A4`, `A24–A28`, `A58–A60`, `A104–A106`, `A113–A115`; Halbgeviertstrich oder Bindestrich) löst der Test in alle Nummern auf – A2 und A3 stehen nur so in AK44 | die Spec bleibt beim Nachtragen stimmig |

### Abweichungen von der Spec (im PR nennen, Spec nachtragen)

1. **A6:** Sprache und Darstellung im Benutzermenü werden auch mit htmx mit dem Knopf
   „Übernehmen“ gespeichert, nicht schon bei der Auswahl (B12, WCAG 3.2.2).
2. **A4:** Die schmale Kopfleiste trägt zusätzlich das Hilfe-Symbol (B13, A8/AK47); die Leinwand
   zeichnet es nicht (L7 Nr. 12).
3. **A99/A92:** Die Stile aller Bereiche stehen in `accounti.css`; je Bereich eigene Dateien wie in
   10b gibt es nicht mehr (Budget gilt für alles).
4. **A96:** 36 statt „etwa 25“ Symbole (Auswahl nach der Leinwand, L6); Budget 15 KB eingehalten
   (Probe 6,4 KB).
5. **A90 (Fassung 4):** Die Schriftskala hat neben 14/16/18/22/28 px auch 12, 13, 20 und 40 px
   (Leinwand, L2).
6. **A91 (Fassung 4):** Zum 4-px-Raster kommen die Zwischenstufen 20/28/40 px und, nur innerhalb
   von Komponenten, die Feinstufen 2/6/10 px. Neben den Radien 6 und 10 px gibt es 2, 4, 8 und
   12 px sowie „rund“ (L3).
7. **A5/A89 (Fassung 4):** Die Kennfarben übernehmen die fünf Werte der Leinwand plus Oliv. Das
   „Kürzel“ auf der Marke ist ein Monogramm aus dem Namen; das Registry-Kürzel ist dafür zu lang
   (B24, L7 Nr. 17/18).
8. **A92 (Fassung 4):** Es gibt zusätzlich die Komponenten Aufklapper, Sammelleiste, Marke und
   Avatar; `feld` kennt außerdem „Warnung“ und „bestätigt“ (L4).

**Auslegungen** (keine Abweichung, im PR benennen):

- **A104 (Fassung 4)** „2-px-Ring“: Gelesen als Mindestmaß; P1 zeichnet 3 px wie die Leinwand,
  AK55 verlangt „≥ 2 px“ (L7 Nr. 8).
- **A91 (Fassung 4)** „zweispaltig ab 64rem“: Zwei Spalten entstehen, sobald beide Platz haben
  (Flex-Basis der Leinwand). Bei 1440 px mit Seitenleiste sind es immer zwei (L5).

- **AK47** „derselben Stelle der Fokusreihenfolge“: gleicher Index unter den fokussierbaren
  Elementen für alle Seiten eines angemeldeten Benutzers im Gerüst (einschließlich der
  Fehlerseiten 403, 404, 409, 413, 422, 503); zwischen diesen und den schlichten Seiten
  (Anmeldung, 500 – auch für Angemeldete –, Fehlerseiten ohne Anmeldung oder bei gesperrter
  Systemdatenbank) dieselbe relative Reihenfolge nach WCAG 3.2.6. Die schlichten Seiten haben
  keine Gesellschaft und kein Benutzermenü im Kopf.
- **A117** „BSD/MIT/Apache/ISC-Lizenz“ gilt für Abhängigkeiten in `pyproject.toml` und
  Ausgeliefertes. axe-core (MPL-2.0) ist ein Entwicklungswerkzeug der Browserprobe: nicht in
  `pyproject.toml`, nicht im Abbild, unverändert benutzt (die Datei-Copyleft-Pflicht der MPL greift
  nur bei Änderungen an ihren Dateien). Playwright ist Apache-2.0, Lucide ISC/MIT.
- **AK61** „Hinweis auf `alembic upgrade head`“: Die Meldung nennt `accounti db upgrade` (Paket A)
  als Weg und `alembic upgrade head` als Gleichwert für Datenbanken mit Versionsvermerk – ohne
  Vermerk scheitert `alembic upgrade head` (Befund Betrieb B2). Nachtrag in der Spec.
- **AK55** „eine Einstellungsseite“: Einstellungsseiten gibt es erst mit P5; P1 misst `/konto`,
  das Formularmuster der Einstellungen. P5 misst seine Seiten selbst.
- **AK54** „Link zur nächsten Aktion“: Hat die nächste Aktion noch keine Seite (Zahlungsvorschlag,
  Bankabruf), zeigt der Link auf den Abschnitt der Hilfe, der den Weg beschreibt.

---

## Seitenstruktur

| Methode, Pfad | Recht | Einmalcode | htmx-Form | Fachfunktion / Gleichlauf |
|---------------|-------|------------|-----------|---------------------------|
| GET `/konto` | angemeldet | — | Fragment (Block `inhalt`); ohne htmx ganze Seite | Anzeige der Vorlieben (`lade_benutzer_id`) |
| POST `/konto/vorlieben` | angemeldet | nein | `200` ohne Körper mit `HX-Refresh: true`; ohne htmx 303 | `auth.dienst.setze_vorlieben` – Ausnahme A113 (Anzeige-Vorliebe, keine CLI) |
| POST `/einstellungen/sprache` | angemeldet | nein | 308 auf `/konto/vorlieben` | wie oben (entfällt ein Release später) |
| GET `/menue` | angemeldet | — | Fragment; ohne htmx ganze Seite | Navigation des Gerüsts |
| GET `/gesellschaft` | angemeldet | — | Fragment; ohne htmx ganze Seite | `geruest.gesellschaften_mit_zaehlern` (lesend, Lesezugriff) |
| POST `/gesellschaft` | angemeldet | nein | 303 (Bestand 10a) | `auth.dienst.wechsle_gesellschaft` – Ausnahme A113 (Sitzungszustand; CLI: `--gesellschaft`) |
| GET `/hilfe` | **offen** | — | Fragment; ohne htmx ganze Seite | — |
| GET `/hilfe/{thema}` | **offen** | — | Fragment; ohne htmx ganze Seite; `thema` als `str`, unbekannt oder ohne Eintrag 404 | — |
| GET `/muster` | `LESEN` | — | Fragment; ohne htmx ganze Seite. Ohne `?theme=` hell und dunkel nebeneinander wie die Zeichenfläche „Bausteine“ (L9); `?theme=` als `str`, nur `hell`, `dunkel`, `auto` wirken (ein Rahmen, `data-theme` der Seite), alles andere wird ignoriert | — (erfundene Beispieldaten) |
| GET `/muster/beispiel` | `LESEN` | — | Fragment (Abschnitt „Austausch“ mit `data-fokus`); ohne htmx 303 auf `/muster#austausch` | — (Beispiel für Fokus nach Austausch und `aria-busy`, A104/A110) |
| GET `/anmelden?code=` | offen (Bestand) | — | ganze Seite (Bestand) | `code` als `str`, nur `wiederherstellung` wirkt |
| GET `/freigaben?code=` | `LESEN` (Bestand) | — | ganze Seite (Bestand) | `code` als `str`, nur `wiederherstellung` wirkt – dann alle Codefelder der Seite als Textfeld |
| GET `/buchungen/{id}?code=` | `LESEN` (Bestand) | — | ganze Seite (Bestand) | wie oben, für beide Formulare (Korrektur, Storno) |

Bestehende Routen bleiben, wie sie sind (Rechte-Matrix unverändert bis auf die neuen Zeilen).
Jede neue Route kommt **im selben Schritt**, in dem sie entsteht, in `SEITEN` der Rechte-Matrix,
in `GLEICHLAUF` (POST) und in `HTMX_FORMEN`; ihre Texte im selben Schritt in `i18n/en.yaml`.
Navigation (`N_()`-Titel, Bereich, Symbol, Zähler):

| Punkt | Pfad | Bereich | Symbol | Recht | Zähler | Reihenfolge |
|-------|------|---------|--------|-------|--------|-------------|
| Übersicht | `/` | `uebersicht` | `house` | `LESEN` | — | 0 |
| Prüfen | `/pruefen` | `pruefen` | `square-check-big` | `LESEN` | `pruefschlange.anzahl_offen`, **betont** (Akzent wie in „Main“) | 10 |
| Freigaben | `/freigaben` | `freigaben` | `shield-check` | eines von `ZAHLUNG_FREIGEBEN`, `STEUER_FREIGEBEN` | `repo_zahlung.anzahl_laeufe(s, [ENTWURF])`, neutral | 50 |

Spätere Bereiche nehmen die Symbole aus L6: Belege `file-text`, Steuern `calendar`, Auswertungen
`chart-column`, Einstellungen `settings`, „Mehr“ `menu`.

## Schnittstelle

```python
# api/registry.py
class Bereich(str, enum.Enum):          # Reihenfolge = A1; EINSTELLUNGEN abgesetzt
    UEBERSICHT = "uebersicht"; PRUEFEN = "pruefen"; BELEGE = "belege"; BANK = "bank"
    RECHNUNGEN = "rechnungen"; STEUERN = "steuern"; AUSWERTUNGEN = "auswertungen"
    FREIGABEN = "freigaben"; EINSTELLUNGEN = "einstellungen"
UNTEN = (Bereich.UEBERSICHT, Bereich.PRUEFEN, Bereich.BELEGE, Bereich.FREIGABEN)  # + „Mehr“

@dataclass(frozen=True)
class Navigationspunkt:
    titel: str
    pfad: str
    bereich: Bereich
    symbol: str                                   # Name im Sprite, geprüft
    recht: Recht | frozenset[Recht] = Recht.LESEN  # frozenset: eines genügt
    reihenfolge: int = 100
    zaehler: Callable[[Session], int] | None = None
    zaehler_betont: bool = False                  # Akzent-Zähler (Prüfen), sonst neutral (L4)
    kurztitel: str | None = None                  # untere Leiste
    def erlaubt(self, rechte: frozenset[Recht]) -> bool: ...

# api/geruest.py — alles, was basis.html braucht, an einer Stelle
@dataclass(frozen=True)
class NavEintrag:                        # Ansicht für die Makros (Schritt 4), aus der Registry (Schritt 6)
    titel: str; kurztitel: str; pfad: str; symbol: str; zaehler: int | None; betont: bool; aktiv: bool
@dataclass(frozen=True)
class Marke:                             # Kennfarbe + Monogramm einer Gesellschaft (A5, B24)
    kuerzel: str; name: str; farbe: int; monogramm: str
@dataclass(frozen=True)
class Geruest:                           # Datentyp ab Schritt 4, befüllt ab Schritt 6/7
    bereiche: tuple[NavEintrag, ...]; einstellungen: NavEintrag | None; unten: tuple[NavEintrag, ...]
    brotkrumen: tuple[tuple[str, str | None], ...]; hilfe_pfad: str; marke: Marke | None
    marken: dict[str, Marke]; darstellung: str; color_scheme: str; tastenkuerzel: bool
    fachansicht: bool; betraege_verbergen: bool; druck_datum: date | None
g = await geruest(request, a, vorlage, zaehler=True)
kennfarben(sorted(dienste.gesellschaften), gewaehlt={}) -> {"a": 3, "b": 5}   # immer alle der Registry
monogramme({k: g.name for k, g in dienste.gesellschaften.items()}) -> {"a": "GD", "b": "KU"}
    # immer alle der Registry, in alphabetischer Reihenfolge der Kürzel vergeben; Wörter des Namens =
    # Folgen aus Buchstaben/Ziffern (re "[^\W_]+"); 1. Wahl: Anfangsbuchstaben der ersten zwei Wörter
    # („Galerie Demo GmbH“ → GD, „Kunsthandel UG“ → KU); ein Wort → seine ersten zwei Zeichen; schon
    # vergeben → die ersten zwei Zeichen des Registry-Kürzels; auch vergeben → erstes Zeichen + Ziffer
    # 2…9. Immer zwei Zeichen, groß (str.upper, Umlaute bleiben)
marken(dienste.gesellschaften, gewaehlt={}) -> dict[str, Marke]       # beides zusammen, für Kopf, /menue, /gesellschaft
aktiver_punkt(punkte, pfad) -> Navigationspunkt | None
fehlende_hilfe(punkte) -> list[Bereich]                  # Bereiche mit Seite, aber ohne HILFE-Eintrag
zeilen = await gesellschaften_mit_zaehlern(request, a)   # [GesellschaftsZeile(g, marke, pruefen,
                                                         #   freigaben, erreichbar, aktiv)]

# api/lesezugriff.py — Zähler aller Gesellschaften, nie über Dienste._fabrik
class Lesezugriff:                       # app.state.lesezugriff; schliesse() in der lebenszeit
    def sitzung(self, url: str) -> ContextManager[Session]   # ohne init_db, nur lesend, kurze Fristen;
                                                             # LeseFehler, wenn die SQLite-Datei fehlt
    _pool: ThreadPoolExecutor                                # max_workers=8, eigener Pool der Zähler
async def zaehle(lesezugriff, url, funktionen, frist=3.0) -> dict[str, int] | None  # None: nicht erreichbar
    # asyncio.wait_for(loop.run_in_executor(lesezugriff._pool, …), frist) — kein run_in_threadpool

# api/vorlagen.py
async def seite(request, vorlage, werte=None, status=200, *,
                zaehler=True, teil=None) -> HTMLResponse
    # Zähler nur für ganze Seiten mit status < 400 und zaehler=True;
    # teil="inhalt": mit HX-Request (ohne Verlaufsabruf) nur dieser Block der Vorlage;
    # mit teil prüft seite() einmal je Vorlage: oben nur extends und Blöcke (RuntimeError sonst)
def fehlerseite_500(accept_language: str | None) -> HTMLResponse            # ohne Datenbank
symbol_url(name) -> str          # Jinja-Global; ValueError bei unbekanntem Namen

# api/sitzung.py
async def vielleicht_angemeldet(request) -> Angemeldet | None   # Hilfe, 404; derselbe Kern wie angemeldet;
                                                                # SQLAlchemyError → None (Protokoll: Art)
def verweigert(a: Angemeldet, *rechte: Recht) -> HTTPException  # 403, detail=Verweigerung(text, rechte, rollen)

# auth/dienst.py
@dataclass(frozen=True)
class Vorlieben:      # UNVERAENDERT = Feld nicht gesendet
    sprache: Literal["de", "en"] | None | _Unveraendert = UNVERAENDERT     # None = automatisch
    darstellung: Literal["auto", "hell", "dunkel"] | _Unveraendert = UNVERAENDERT
    fachansicht: bool | _Unveraendert = UNVERAENDERT
    betraege_verbergen: bool | _Unveraendert = UNVERAENDERT
    tastenkuerzel: bool | _Unveraendert = UNVERAENDERT
setze_vorlieben(s, benutzer_id, Vorlieben(darstellung="dunkel"))   # nur gesetzte Felder, gezieltes
                                                                    # UPDATE, kein Ereignis; AuthError
vorlieben_aus_formular(felder) -> Vorlieben                         # api/seiten/konto.py, 422 bei Unsinn

# Zähler
pruefschlange.anzahl_offen(s) -> int            # COUNT status=pruefung ohne zurückgestellte
repo_zahlung.anzahl_laeufe(s, [LaufStatus.ENTWURF]) -> int

# api/hilfe_inhalt.py
class Hilfethema(str, enum.Enum): ...           # alle Bereiche + ANMELDUNG + KONTO
HILFE: dict[Hilfethema, Hilfe]                  # titel, anleitung: tuple[str, ...], begriffe, tasten
BEGRIFFE: tuple[Begriff, ...]                   # Anhang B: klare Sprache, Fachbegriff, Erklärung (N_)
TASTEN_PRUEFEN: tuple[tuple[str, str], ...]     # ("j", N_("nächster Eintrag")), …
```

**Komponenten** (`vorlagen/_komponenten.html`, importiert `with context` – in Vorlagen mit
`teil` **innerhalb** des Blocks `inhalt`, in `basis.html` und den Bestandsvorlagen oben; jede
steht auf `/muster`):

| Gruppe | Makros |
|--------|--------|
| Bedienung | `knopf(text, art="primaer"\|"sekundaer"\|"still"\|"gefaehrlich", symbol, groesse="normal"\|"klein"\|"gross", breit, typ, name, wert, taste, deaktiviert, laedt, attribute)`, `linkknopf(text, href, art, symbol, groesse, breit, taste, attribute)`, `optionskarte(name, wert, titel, nebentext, grund, gewaehlt, taste, id)`, `segment(name, legende, optionen, gewaehlt)`, `reiter(beschriftung, eintraege, aktiv, geteilt=False)` |
| Inhalte | `karte(titel, anzahl, status, hauptaktion, kennzahl, ebene=2)` (Aufruf; `status` = `(art, wort)`, `hauptaktion` = `(text, href, art)` mit `art` = `link`\|`primaer`\|`sekundaer`), `zaehler(anzahl, beschriftung, betont=False)`, `status(art, wort)`, `sicherheit(stufe, zusatz, klein)`, `symbol(name, beschriftung, groesse=18, kraeftig=False)`, `marke(marke, klein=False, href=None)`, `avatar(initialen)`, `aufklapper(titel, art="linie"\|"karte", offen=False)` (Aufruf) |
| Daten | `tabelle(beschriftung, spalten, kompakt, sichtbar, in_karte=False)` (Aufruf), `zeile(gewaehlt=False)` (Aufruf), `zelle(label, zahl)` (Aufruf), `spaltenkopf(spalte)`, `angaben(klein=False)` (Aufruf), `angabe(label)` (Aufruf), `betrag(wert, richtung, groesse)` |
| Formular | `feld(name, beschriftung, wert, typ, hilfe, fehler, warnung, bestaetigt, pflicht, autocomplete, inputmode, breite, attribute, id)`, `auswahl(…, id)`, `textfeld(…, id)`, `optionen(name, legende, optionen, gewaehlt, fehler, id)`, `haken(name, beschriftung, gewaehlt, id)`, `codefeld(variante, wechsel_href, fehler, id)`, `feldgruppe(legende)` (Aufruf), `fehlerliste(fehler, ids)` |
| Rückmeldung | `hinweis(art, titel, neu)` (Aufruf), `leer(satz, nebensatz, aktion_text, aktion_href, symbol="check")`, `ladeanzeige(text)` |
| Abläufe | `schritte(schritte, aktuell)` (mit `<progress>`), `bestaetigung(titel, knopf, abbrechen_href)` (Aufruf) |
| Navigation | `seitenleiste(geruest)`, `untere_leiste(geruest)`, `aktionsleiste()` (Aufruf; ersetzt unter 64rem die untere Leiste, für P3 und P7), `sammelleiste()` (Aufruf; klebt unten im Inhalt, für P3), `brotkrumen(teile)`, `seitenblaettern(seite, seiten, url)` |

Aussehen, Maße und Zustände: L4. CSS-Muster ohne eigenes Makro (Klassen, auf `/muster` gezeigt):
`.etikett`, `.seitenkopf`, `.karte-liste`, `.gruppenliste`, `.unternavigation`, `.layout-*`,
`.haken-ziel`, `.zeige-fokus` (nur `/muster`), `.thema-hell`/`.thema-dunkel` (nur `/muster`).

**Symbole** (36, `lucide-static` 1.55.0, Auswahl nach der Leinwand, L6): `house` Übersicht ·
`square-check-big` Prüfen · `file-text` Belege · `landmark` Bank & Zahlungen · `receipt`
Rechnungen & Kontakte · `calendar` Steuern · `chart-column` Auswertungen · `shield-check`
Freigaben · `settings` Einstellungen · `menu` Mehr · `circle-help` Hilfe · `log-out` Abmelden ·
`check` erledigt · `triangle-alert` Achtung · `circle-x` Fehler · `info` Hinweis · `circle-alert`
fehlt · `lock` gesperrt · `arrow-right` Vorschlag · `chevron-down`, `chevron-right`,
`chevron-left` · `external-link` · `search` · `upload` · `download` · `calendar-clock` Frist ·
`sun`, `moon`, `monitor` Darstellung · `arrow-up-down`, `arrow-up`, `arrow-down` Sortierung ·
`loader-circle` lädt · `x` · `keyboard` Tastenkürzel.

---

## Aufgaben

> **Schutztests** sind als „(Schutz)“ markiert: von Anfang an grün, sie sichern Bestehendes ab.
> **Umgestellt** heißt: ein Test aus 10a/10b prüft dieselbe Absicht an der neuen Stelle; er wird
> nicht gelöscht und steht in der Liste im PR (AK49). Testnamen sind Vorschläge; maßgeblich ist,
> dass jede Zeile der Tabelle „Spec und Akzeptanz → Schritt → Test“ einen roten Test zuerst hat.
>
> **Regeln für jeden Schritt:**
> - Rot sehen gilt für den neuen Test. **Am Ende jedes Schritts ist die Gesamtsuite grün**
>   (`pytest`, `ruff check --no-cache`, `ruff format --no-cache --check`, `mypy --strict`).
> - Wer eine Route anlegt, trägt sie im selben Schritt in `SEITEN` (`tests/test_api_rechte_matrix.py`,
>   der Test verlangt `vorhanden == set(SEITEN) | set(REST)`), in `GLEICHLAUF` (nur POST) und in
>   `HTMX_FORMEN` (`tests/test_api_vollstaendigkeit.py`) ein. Wer einen Text anlegt oder entfernt,
>   pflegt `i18n/en.yaml` im selben Schritt (`test_i18n_katalog.py` prüft „vollständig“ und
>   „verwaist“). Wer Markup ändert, das ein Test aus 10a/10b prüft, stellt diesen Test im selben
>   Schritt um.
> - Ein Commit je Komponente (Schritt 4), je Gerüstteil (Schritt 7) und je Seite (Schritt 12).

### Schritt 0 — Abzweigen, Spec ablegen, Rückverfolgung, Vollständigkeitslisten

- [ ] **Grundlage prüfen:** 10b-1 und Paket A sind auf `main` (sonst nicht abzweigen). `alembic
  heads` zeigt genau einen Kopf; den Wert als **`K`** notieren (`down_revision` der Migration in
  Schritt 3). `db.SCHEMA_STAND == K` (`test_db_upgrade.py::test_schema_stand_ist_der_kopf_der_migrationen`
  grün). Notieren, welche der Pakete C–F schon gemergt sind. Die unter „Stand der Grundlage“
  genannten Zeilen und Signaturen stimmen (sonst hier nachtragen, wie der Abgleich im 10b-Plan).
  Die Testliste von `main` sichern (`pytest --collect-only -q` in eine Datei im Scratchpad, für
  den Abgleich in Schritt 15).
- [ ] **Kopfannahmen auflisten:** `git grep -nE '"downgrade", *"-[0-9]+"|\(head\)|get_current_head' tests`
  und jede andere Stelle, die eine bestimmte Revision als Kopf oder „eine Migration unter dem
  Kopf“ voraussetzt (Stand 87c6c8d: `test_db_upgrade.py:201`, `:227`, `:280`, `:289`; nach
  10b-1 dazu `test_migration_web.py`; ist F gemergt, `test_migration_anlagen_buchung.py:35`). Hat
  der Rebase von 10b-1 eine davon schon auf ausdrückliche Revisionen umgestellt, bleibt sie
  Schutztest; die übrigen stellt Schritt 3 um. Liste im Plan unter „Umsetzung“ festhalten.
- [ ] **Spec und Skizzen ablegen** unter `docs/specs/2026-10-26-oberflaeche-einrichtung.md` und
  `docs/specs/2026-10-26-oberflaeche-skizzen.md` (Pfadangaben auf den Scratchpad in Anhang C durch
  „liegt beim Autor der Spec“ ersetzen, Bildschirmfotos nicht einchecken). Hat P4 sie schon
  abgelegt, nichts tun.
- [ ] **Leinwand ablegen** (Fassung 4) unter `docs/design/2026-10-26-leinwand/`: `canvas.json` und
  die zehn `.dc.html` unverändert. Dazu ein `README.md` mit dem Zitat der Freigabe und dem Datum,
  der Lesart aus L0, der Tabelle L8 als Kurzfassung („wer baut was“) und dem Hinweis: Entwurfsformat
  mit Inline-Stilen, nicht als Vorlage kopieren, Maße und Token stehen im Plan P1. Liegt der Ordner
  schon da (P4), nichts doppelt ablegen. Prüft ein Test `docs/` auf Links oder Inline-Stile, nimmt er
  den Ordner aus. *Test* `tests/test_spec_rueckverfolgung.py::test_leinwand_abgelegt`: die zehn
  Dateien aus `canvas.json` → `order` sind da, und die Tokenblöcke (`.a{…}`, `.a.dunkel{…}`) aller
  Zeichenflächen sind widerspruchsfrei (dieselbe Variable hat überall denselben Wert).
- [ ] **Rückverfolgung** (`tests/test_spec_rueckverfolgung.py`): *Tests*
  `::test_jede_anforderung_in_anhang_d`, `::test_jede_anforderung_in_einem_kriterium`,
  `::test_kriterien_nennen_nur_vorhandene_anforderungen`, `::test_paket_in_anhang_d_wie_im_abschnitt_6`,
  `::test_bereichsangaben_werden_aufgeloest` („(A1–A4)“ ergibt A1, A2, A3, A4; Halbgeviert- und
  Bindestrich; ohne Auflösung fehlten A2 und A3). Rot, solange die Spec fehlt; grün nach dem
  Ablegen (die Spec ist am 26.10.2026 abgeglichen).
- [ ] **Vollständigkeitslisten** (`tests/test_api_vollstaendigkeit.py`, neu, mit dem Bestand):
  `GLEICHLAUF` = jeder POST-Endpunkt → Name des Gleichlauftests **oder** eine ausdrücklich
  benannte Ausnahme nach A113 (`/einstellungen/sprache`, `/gesellschaft`, `/anmelden`,
  `/abmelden`; die POST-Endpunkte aus 10a/10b mit ihrem vorhandenen Test, z. B.
  `test_akzeptanz_web.py::test_akzeptanz_1_…` für `/pruefen/{id}/freigeben`, sonst als `BESTAND`
  mit Verweis auf Plan 10a bzw. 10b); `HTMX_FORMEN` = jede Route → `fragment` | `neu_laden` |
  `weiterleitung` | `ganze_seite` (mit Grund; die GET-Seiten aus 10a/10b `ganze_seite`, Grund
  „Bestand“). *Tests* `::test_jeder_post_hat_gleichlauf_oder_ausnahme`,
  `::test_jede_route_hat_eine_htmx_form`, `::test_jeder_gleichlauftest_existiert` (jeder genannte
  Test lässt sich auflösen). Ab hier trägt jeder Schritt seine Routen nach; das Verhalten prüft
  `::test_htmx_formen_wirken` in Schritt 13.

### Schritt 1 — Token und Grundstile

- [ ] **Kontrasthilfe** (`tests/design_hilfe.py`): Leuchtdichte und Kontrast nach WCAG 2.2,
  Leser für die Tokenblöcke aus `accounti.css` (hell aus `:root, .thema-hell`, dunkel aus
  `:root[data-theme="dunkel"], .thema-dunkel` und aus dem `@media (prefers-color-scheme: dark)`-Block),
  Mischung einer Farbe mit Alpha über einer Fläche (für `--schleier`), Leser für die Tokenblöcke der
  Leinwand (`docs/design/2026-10-26-leinwand/*.dc.html`, `.a{…}` und `.a.dunkel{…}`).
- [ ] **`statisch/accounti.css` neu** (Ebenen; Token hell/dunkel **wie die Leinwand** nach L1, also
  die Werte aus A89 plus `--fehler-text`, `--schatten`, `--schleier`, Kennfarben und
  `--beleg-hintergrund`, die Tokenblöcke auch für `.thema-hell`/`.thema-dunkel`; Maß-Token nach
  L2/L3 (`--gr-*`, `--a-*`, `--fein-*`, `--radius-*`, `--kopfhoehe`, `--leistenhoehe`,
  `--seitenleiste`, `--inhalt-max`, `--formular-max`, `--einstellungen-max`); `color-scheme` je Wahl,
  Grundstile für Text (`tabular-nums` auf `body`), Überschriften (600), Links (`--akzent`,
  `text-underline-offset: 3px`, Hover 2 px dick), `input`/`select`/`textarea`/`button`/`kbd` aus
  Token, `accent-color`, Fokusring 3 px, `scroll-padding`, Zielgrößen, Übergänge und
  `prefers-reduced-motion`, `.unsichtbar` (in `hilfen`), `.symbol`, `[hidden] { display: none
  !important }` (heute `accounti.css:55`; `pruefen.js` schaltet `hidden` um, eine spätere
  `display`-Regel darf das nicht aufheben); Breakpoints 40/64/90rem). Die Regeln der bestehenden
  Seiten stehen bis Schritt 12 in der Übergangsebene `@layer bestand` **vor** `komponenten`
  (Entscheidung „Eine CSS-Datei“, B20): die aus `accounti.css` dort, und **`pruefen.css` wird im
  selben Commit ganz in `@layer bestand { … }` gefasst**; beide auf die neuen Token umgeschrieben
  (`--gedaempft` → `--text-2`, `--hintergrund` → `--grund` bzw. `--flaeche-2`, `#fff` →
  `var(--beleg-hintergrund)`): *Tests* `tests/test_design_token.py::test_kontrast_hell`,
  `::test_kontrast_dunkel` (je eine Paarliste: Text und Nebentext auf Grund, Fläche, Fläche-2,
  Akzentfläche und Statusflächen ≥ 4,5; Akzent als Text ≥ 4,5; `--akzent-text` auf `--akzent`
  ≥ 4,5; Status auf eigener Fläche ≥ 4,5; `--linie-stark`, `--fokus` und `--marke-1` … `-6` auf
  Grund, Fläche, Fläche-2 ≥ 3; **Fassung 4:** `--fehler-text` auf `--fehler` ≥ 4,5 und `--fehler`
  auf Fläche und Grund ≥ 3; das Kürzel (`--flaeche`) auf `--marke-1` … `-6` ≥ 4,5;
  `--ok`/`--warn`/`--fehler` und `--text-2` auf `--akzent-flaeche` ≥ 4,5 für die gewählte Zeile;
  Text der Knopfarten und des aktiven Eintrags über `--schleier` ≥ 4,5; Erwartungswerte wie L1),
  `::test_token_wie_leinwand` (Fassung 4: jedes Farb-Token der Leinwand hat in `accounti.css`
  denselben Wert, hell und dunkel; `--marke-gd` → `--marke-1`, `--marke-ku` → `--marke-3`,
  `--marke-2`/`-4`/`-5` gleichnamig; die Leinwand kennt `--schleier`, `--marke-6` und
  `--beleg-hintergrund` nicht – die stehen in einer Liste mit Grund),
  `::test_themenklassen_in_den_tokenbloecken` (`.thema-hell` im hellen, `.thema-dunkel` im ersten
  dunklen Block, je mit `color-scheme`; der Block unter `@media` ohne Klasse),
  `::test_schriftgroessen_nur_aus_der_skala` (jedes `font-size` ist `var(--gr-n)`, `inherit` oder
  `1em`; die Skala hat genau die neun Stufen aus L2),
  `::test_abstaende_und_radien_aus_token` (in `layout`, `komponenten`, `seiten`: `padding`,
  `margin`, `gap`, `inset` und `border-radius` nur aus `var(--a-…)`, `var(--fein-…)`,
  `var(--radius…)`, `0`, `auto`, `env(safe-area-inset-…)` oder `calc()` darüber; in `calc()` und
  allein ist nur ±1 px als Randausgleich erlaubt (Feld im Fehler, gewählte Optionskarte und
  Wahlpille, Reiter-Strich); `--fein-…` nur in `komponenten`),
  `::test_dunkel_zweimal_gleich`, `::test_color_scheme_je_wahl`,
  `::test_jedes_token_in_beiden_modi`, `::test_farben_nur_ueber_token` (außerhalb der
  Tokenblöcke und `@media print` nur `var(--…)`, `transparent`, `currentColor`, `inherit`),
  `::test_formularelemente_aus_token` (AK4 statisch), `::test_nur_gewichte_400_und_600`,
  `::test_uebergaenge_kurz_nur_farbe_und_deckkraft`, `::test_reduzierte_bewegung_ohne_uebergang`,
  `::test_fokusring_3px_mit_2px_abstand` (Fassung 4, vorher `…_2px_…`; 3 px wie die Leinwand,
  Auslegung A104), `::test_nur_drei_breakpoints`,
  `::test_hidden_versteckt_immer` (`[hidden]` mit `!important` in `@layer basis`),
  `::test_css_budget` (≤ 40 960 Bytes, AK50), `::test_jede_regel_in_einer_ebene` (in
  `accounti.css` und, solange es sie gibt, `pruefen.css` steht keine Regel außerhalb von
  `@layer`; `pruefen.css` nur in `bestand`), `::test_jeder_tokenverweis_definiert` (jedes
  `var(--…)` beider Dateien hat einen Wert in beiden Modi – fängt `--gedaempft` und
  `--hintergrund`); `::test_farben_nur_ueber_token` liest `pruefen.css` mit.
- [ ] **`basis.html`: Theme an `<html>`** (vorerst `data-theme="auto"` fest, Schritt 3 macht es
  wählbar) und `<meta name="color-scheme">`, `viewport-fit=cover`: *Test*
  `tests/test_api_geruest.py::test_html_traegt_theme_und_color_scheme`.

### Schritt 2 — Symbole

- [ ] **Erzeuger** `scripts/symbole.py` (Liste `SYMBOLE` wie unter „Schnittstelle“; prüft Version
  und SHA-512 des Tarballs, liest `package/icons/<name>.svg`, übernimmt nur die Formen, schreibt
  `statisch/symbole.svg` mit Kopfkommentar und `statisch/LIZENZ-lucide.txt` = Kopf (Version,
  Integrität, Symbolliste, Zuordnung neuer → alter Name für `triangle-alert`, `circle-help`,
  `circle-x`, `circle-alert`) + vollständige `package/LICENSE`); die Liste hat 36 Namen nach L6: *Test*
  `tests/test_symbole.py::test_erzeuger_wandelt_symbol` (zwei Beispieldateien im `tmp_path`:
  Wurzelattribute weg, Formen gleich, `viewBox` gesetzt).
- [ ] **Sprite und Lizenz einchecken** (Erzeuger einmal gegen den geprüften Tarball laufen lassen;
  Tarball in eigenem leeren Ordner, Skript nicht darin): *Tests* `::test_sprite_budget_und_ids`
  (≤ 15 360 Bytes, Ids = `SYMBOLE`), `::test_lizenz_isc_und_mit_beigelegt` („ISC License“,
  „Cole Bemis“, „1.55.0“, Integrität, die vier Namenszuordnungen; `THIRD-PARTY.md` nennt Lucide),
  `::test_sprite_ohne_skript_und_verweise`, `::test_symbole_wie_leinwand` (Fassung 4: die Namen der
  Tabelle L6 – Navigation, Status, Hinweis, Feldmeldung, gesperrt, Vorschlag – stehen im Sprite;
  `list-checks`, `calculator`, `stamp`, `ellipsis`, `gauge`, `circle-user`, `building-2`,
  `circle-check` nicht mehr).
- [ ] **`symbol`-Makro und `symbol_url`** (`api/symbole.py`: Ids einmal aus dem Sprite gelesen;
  Größe über `groesse` → Klasse `symbol-14` … `symbol-40`, `kraeftig` → `symbol-kraeftig`):
  *Tests* `::test_symbol_dekorativ_aria_hidden`, `::test_symbol_mit_beschriftung_role_img`,
  `::test_symbol_groesse_und_strich_als_klasse` (kein `width`/`height`/`style` am Element),
  `::test_unbekanntes_symbol_scheitert`, `::test_symbol_url_mit_versionsanhang`; **umgestellt**
  `tests/test_api_statisch.py::test_eigene_dateien_mit_versionsanhang`: ein Verweis mit Fragment
  (`/statisch/symbole.svg?v=…#name` in `<use href>`) zählt als versioniert, wenn der Teil vor `#`
  auf `?v=…` endet. Heute verlangt der Test `endswith("?v=…")` (:165–171) und schlüge mit dem
  ersten Symbol auf einer Seite fehl.

### Schritt 3 — Vorlieben am Benutzer

- [ ] **Modell, Tabelle, Repository** (`models/auth.Benutzer`: `darstellung: Literal["auto",
  "hell", "dunkel"] = "auto"`, `fachansicht: bool = False`, `betraege_verbergen: bool = False`,
  `tastenkuerzel: bool = True`; `db/tabellen_auth.BenutzerRow` mit `default` **und**
  `server_default`; `db/repo_auth._BENUTZER_FELDER` liest sie, `speichere_benutzer` schreibt sie
  und `sprache` nur beim Anlegen, B18): *Tests*
  `tests/test_auth_vorlieben.py::test_standard_fuer_neue_benutzer`,
  `::test_bestehender_benutzer_liest_standard` (Zeile ohne Angaben → Standardwerte),
  `::test_speichern_ueberschreibt_vorlieben_nicht` (Benutzer laden, Vorlieben mit
  `setze_vorlieben` ändern, den vorher geladenen `Benutzer` mit neuem `letzte_anmeldung_am`
  speichern → Vorlieben bleiben).
- [ ] **`setze_vorlieben`** (ersetzt `setze_sprache`; `Vorlieben` mit `UNVERAENDERT`; gezieltes
  `UPDATE`, kein Ereignis): *Tests* `::test_nur_gesetzte_felder_aendern_sich`,
  `::test_sprache_none_heisst_automatisch`, `::test_ungueltige_darstellung_auth_error`,
  `::test_unbekannter_benutzer_auth_error`, `::test_kein_auth_ereignis` (Zahl der Zeilen in
  `auth_ereignisse` unverändert); umgestellt alle Aufrufer von `setze_sprache` (nur
  `seiten/sprache.py`, entfällt in Schritt 9) und ihre Tests.
- [ ] **Migration** `alembic/versions/<rev>_add_benutzer_vorlieben.py` (`down_revision = K` aus
  Schritt 0; je Spalte nur, wenn sie fehlt; `batch_alter_table`; `server_default` `'auto'`,
  `sa.false()`, `sa.false()`, `sa.true()`; Downgrade entfernt die vier Spalten) und **im selben
  Commit `db.SCHEMA_STAND = "<rev>"`** (Paket A, `db/__init__.py`): *Tests*
  `tests/test_migration_web.py::test_upgrade_ergaenzt_vorlieben_in_bestehender_tabelle` (System-
  und Gesellschaftsdatenbank, Benutzer bleibt, Standardwerte gesetzt, `alembic check` leer),
  `::test_migration_ist_wiederholbar` (Spalten schon da → kein Fehler). **Kein Test hängt am
  Kopf** (B10, Muster Paket D `test_migration_verrechnungen.py:20–28`): die eigene Revision
  steht als Konstante `VORLIEBEN = "<rev>"` im Test (sie ändert sich beim Neuketten nicht), der
  Vorgänger kommt als `VOR = _vorher(VORLIEBEN)` (`get_revision(VORLIEBEN).down_revision`) aus
  dem `ScriptDirectory`; `get_current_head()`, `downgrade -1` und „`<rev>` ist Kopf“ kommen nicht
  vor. Merged danach P4 (oder C, D, F, P5–P7) mit einer Migration auf `<rev>`, bleiben die Tests
  gültig; eine feste `e7153706b43a` als Vorgänger nähme dagegen bei einer Kette
  `… → e7153706b43a → 2f7c7043043e → <rev>` auch fremde Migrationen zurück. Upgrades gehen auf
  `VOR` bzw. `VORLIEBEN` oder `head`, Vermerke werden gegen `SCHEMA_STAND` geprüft, „genau ein
  Kopf“ nur über `test_schema_stand_ist_der_kopf_der_migrationen` (Paket A). Umgestellt
  `::test_ein_kopf_nach_ddc9a184ddb4` (ohne Kopfannahme: unter den Vorfahren von `VORLIEBEN`
  stehen Baustein 7, Kontierung und Sprache in dieser Reihenfolge; die Kopfzahl prüft Paket A),
  `::test_downgrade_und_wieder_hinauf` (Downgrade auf ausdrückliche Revisionen – `VOR`, dann
  `_vorher(SPRACHE)` und `_vorher(KONTIERUNG)` – statt `-1`), `::test_postgresql_rundlauf` (über
  `ACCOUNTI_TEST_PG`, hinauf auf `head` und zurück auf `VOR`). Schutz aus Paket A:
  `tests/test_db_upgrade.py::test_schema_stand_ist_der_kopf_der_migrationen`,
  `::test_db_init_stempelt_und_alembic_upgrade_laeuft`,
  `tests/test_migration_belegvollstaendigkeit.py` (Vermerk nach einer Wiederherstellung).
- [ ] **Kopfrelative Tests anderer Pakete** (im selben Commit wie die Migration; Liste aus
  Schritt 0; umgestellt, in die Liste für AK49): Paket A `tests/test_db_upgrade.py` – Konstante
  `TOKEN = "6d38d11fc348"`, `_vorher(TOKEN)`; `test_migration_token_je_gesellschaft` (:201)
  geht auf `_vorher(TOKEN)` statt `-1`, `test_downgrade_token_index_bricht_vor_dem_loeschen_ab`
  (:227) geht **auf `TOKEN`** hinauf statt auf `head` und erwartet nach dem abgewiesenen
  Downgrade den Vermerk `TOKEN` (vom Kopf aus nähme `downgrade _vorher(TOKEN)` erst die späteren
  Migrationen zurück), ebenso der PostgreSQL-Test (:280, :289: erst `downgrade TOKEN`, dann der
  abgewiesene Schritt, Vermerk `TOKEN`). Ist F gemergt: `test_migration_anlagen_buchung.py:35`
  auf `_vorher("2f7c7043043e")`. Was der Rebase von 10b-1 schon umgestellt hat, bleibt Schutz.
  *Test* (Wächter, gilt ab hier für jedes Paket)
  `tests/test_migration_regeln.py::test_kein_migrationstest_haengt_am_kopf` (in `tests/` kein
  relatives Downgrade `"downgrade", "-N"`, kein `get_current_head`, keine Aussage über
  `(head)` außer der Zählung `count("(head)") == 1`); rot gesehen gegen den Stand aus Schritt 0.
- [ ] **Schemaprüfung** (`api/dienste.PFLICHTSPALTEN["auth_benutzer"]` um die vier Spalten; die
  Meldung nennt **jede** fehlende Spalte, damit der Test aus 10b mit `auth_benutzer.sprache` gilt,
  und als Weg `accounti db upgrade` (Paket A) mit `alembic upgrade head` als Gleichwert für
  Datenbanken mit Versionsvermerk, B22; neue msgid in `en.yaml`, die alte entfällt):
  *Tests* `tests/test_api_schema.py::test_start_ohne_vorlieben_bricht_mit_hinweis_ab` (Upgrade
  bis `VOR`, `serve` → Exit 2, Meldung nennt `auth_benutzer.darstellung`,
  `accounti db upgrade` und `alembic upgrade head`, keine URL),
  `::test_start_ohne_migration_bricht_mit_hinweis_ab` (Schutz: `auth_benutzer.sprache` und
  `alembic upgrade head` stehen weiter in der Meldung).
- [ ] **Sicherung** (generisch, kein Code): *Test*
  `tests/test_betrieb_sicherung.py::test_rundlauf_mit_vorlieben` (Werte gleich; eine Sicherung
  von vor der Migration lässt sich einspielen: das Ziel legt `init_db` nach dem neuen Code an und
  vermerkt `SCHEMA_STAND`, die Zeilen bekommen die Standardwerte).
- [ ] **`accounti db upgrade`** (Paket A): *Test*
  `tests/test_db_upgrade.py::test_stand_ohne_vermerk_mit_sprache_ohne_vorlieben` (Bestand per
  `alembic upgrade VOR`, dann `alembic_version` gelöscht; `db upgrade` leitet `VOR` ab, stempelt,
  ergänzt die vier Spalten, nennt den abgeleiteten Stand und vermerkt `SCHEMA_STAND`).

### Schritt 4 — Komponenten und Musterseite

- [ ] **Datentyp `Geruest`** (`api/geruest.py`: `Geruest`, `NavEintrag` und `Marke` wie unter
  „Schnittstelle“, noch ohne Befüllung aus der Registry; die Navigationsmakros arbeiten nur mit
  `NavEintrag`). Geprüft über `::test_navigationsmakros_mit_beispielgeruest`.
- [ ] **`vorlagen/_komponenten.html`** mit allen Makros der Tabelle „Komponenten“ und ihren
  Stilen unter `@layer komponenten`. Aussehen, Maße und Zustände nach **L4**, ein Commit je
  Komponente; nach jeder Komponente den Abschnitt auf `/muster` neben die Zeichenfläche
  „Bausteine“ legen, sobald Schritt 5 die Bilder liefert. *Tests* `tests/test_komponenten.py` – je
  Makro gerendert über eine kleine Vorlage: `::test_knopf_arten_groessen_zustaende`
  (`deaktiviert` → `disabled`, `aria-disabled` nie zusätzlich; `groesse` klein/normal/groß und
  `breit` als Klassen; `laedt` → `aria-busy="true"` mit `loader-circle`),
  `::test_attribute_nur_aus_positivliste` (`hx-post`, `data-taste`,
  `aria-controls` gehen durch, Werte escaped; `onclick`, `style`, `href`, ein Name mit Leerzeichen
  oder `>` → Fehler beim Rendern),
  `::test_name_direkt_vor_value` (`knopf` mit `name`/`wert` und versteckte Felder schreiben
  `name="…" value="…"` direkt hintereinander, wie `formularwert` und `freigabe_hash` es suchen),
  `::test_tabelle_caption_pflicht_und_rollen` (`role`-Attribute, `data-label`, `scope="col"`),
  `::test_spaltenkopf_aria_sort`, `::test_angaben_als_dl`,
  `::test_betrag_vorzeichen_und_richtung_als_text` (Fassung 4: „−“ ist U+2212, zwischen
  Vorzeichen und Zahl und vor „€“ feste Leerzeichen, Richtung als Wort, Klasse `betrag`),
  `::test_status_und_sicherheit_wort_und_symbol` (Fassung 4: je Art das Symbol aus L4 – ok `check`,
  info `info`, warn/fehler `triangle-alert`; Sicherheit mit drei Kästchen `aria-hidden` und Wort),
  `::test_feld_label_hilfe_fehler_aria` (mit `id`
  ungleich Name: `for`, `<id>-hilfe`, `<id>-fehler`, `aria-describedby`),
  `::test_feld_warnung_ohne_aria_invalid_und_bestaetigt` (Fassung 4: Warnung mit
  `triangle-alert`, „Achtung:“ und `aria-describedby`, aber **ohne** `aria-invalid`; bestätigt mit
  `check`), `::test_optionen_als_fieldset_mit_legend`,
  `::test_optionskarte_und_segment_ohne_skript` (Fassung 4: Optionsfeld im `label`, `checked`
  vom Server, kein `on…`, keine `style`), `::test_codefeld_ein_feld_numerisch_und_variante`
  (eigene `id`; Link beim Label vor dem Feld, mit `weiter`), `::test_fehlerliste_alert_mit_links`
  (Zuordnung Feldname → id: `grund` → `#grund-k`), `::test_hinweis_rolle_nur_wenn_neu`,
  `::test_hinweis_mit_symbol_und_wort` (Fassung 4), `::test_leer_mit_satz_nebensatz_und_link_ohne_rolle`
  (Fassung 4, vorher `::test_leer_mit_satz_und_link_ohne_rolle`),
  `::test_karte_titel_anzahl_status_hauptaktion_kennzahl` (Fassung 4: Überschrift der gewählten
  Ebene, Anzahl in eigenem Element, Pille rechts, Hauptaktion als Link oder Knopf, `kennzahl` mit
  Klasse `kennzahl`), `::test_aufklapper_details_summary` (Fassung 4: beide Arten,
  `offen` → `open`), `::test_sammelleiste_und_aktionsleiste` (Fassung 4: `role="region"` mit
  `aria-label`, Inhalt aus dem Aufruf), `::test_marke_monogramm_ohne_aria_label_auf_span`
  (Fassung 4: Klasse `marke-n`, Monogramm als Text, Name sichtbar oder `.unsichtbar`, mit `href`
  ein Link), `::test_zaehler_betont_und_beschriftung` (Fassung 4),
  `::test_schritte_mit_progress_und_aria_current_step` (Fassung 4, vorher
  `::test_schritte_aria_current_step`: `<progress value max aria-hidden>`, Text „Schritt n von m“),
  `::test_tabelle_in_karte_und_gewaehlte_zeile` (Fassung 4),
  `::test_brotkrumen_und_seitenblaettern`, `::test_navigationsmakros_mit_beispielgeruest`
  (Seitenleiste mit betontem Zähler, untere Leiste mit Zähler in der Beschriftung und Aktionsleiste
  bekommen hier ein `Geruest` aus Konstanten; Schritt 7 verdrahtet sie im Gerüst).
- [ ] **Zwei Formen in `seite()`** (Parameter `teil`; mit `HX-Request` ohne Verlaufsabruf nur der
  Block; Prüfung „oben nur `extends` und Blöcke“ je Vorlage, B19): *Tests*
  `tests/test_api_muster.py::test_fragment_mit_hx_request` (`/muster` mit
  `HX-Request`: nur Block `inhalt`, kein `<html`, keine Navigation, Makros aus `_komponenten.html`
  gerendert; mit `HX-History-Restore-Request` die ganze Seite; ohne die ganze Seite),
  `tests/test_api_vorlagen.py::test_teil_verlangt_nur_bloecke_auf_oberster_ebene` (Vorlagen aus
  einem `DictLoader`: Import bzw. `{% set %}` auf oberster Ebene → `RuntimeError` schon beim Rendern
  der ganzen Seite; Import im Block → Fragment rendert; `super()` im Block `inhalt` → Fehler).
  `muster.html` importiert `_komponenten.html` im Block `inhalt`.
- [ ] **Musterseite** `api/seiten/muster.py` + `vorlagen/muster.html` als **Nachbildung der
  Zeichenfläche „Bausteine“** nach L9 (`GET /muster` und `GET /muster/beispiel`, `LESEN`, kein
  Navigationspunkt; erfundene Daten und die Texte der Zeichenfläche als Konstanten im Modul; ohne
  Parameter zwei Themenrahmen `thema-hell`/`thema-dunkel` nebeneinander mit den sieben Abschnitten
  der Zeichenfläche und den Ergänzungen aus L9; je Komponente die Zustände normal, deaktiviert,
  lädt (Rahmen mit Klasse `htmx-request`), Fehler, aktiv (`aria-current`/`aria-selected`), Fokus
  (`zeige-fokus`); Umschalter „beide | hell | dunkel | automatisch“ als Links mit `?theme=`;
  Abschnitt „Austausch“ mit einem Knopf, der `/muster/beispiel` per `hx-get` lädt; im selben
  Schritt beide Routen in `SEITEN`, `HTMX_FORMEN` (`fragment`) und ihre Texte in `en.yaml`):
  *Tests*
  `tests/test_api_muster.py::test_jedes_makro_auf_der_musterseite` (Makronamen aus
  `_komponenten.html` per Regex gegen Aufrufe in `muster.html`, AK51), `::test_zustaende_gezeigt`,
  `::test_ohne_parameter_hell_und_dunkel_nebeneinander` (Fassung 4: zwei Rahmen mit den Klassen
  `thema-hell` und `thema-dunkel`; in jedem die Etiketten „Farben“, „Schrift“, „Knöpfe“, „Status und
  Sicherheit“, „Felder“, „Hinweise“, „Tabelle und leerer Zustand“ in dieser Reihenfolge und die
  Beispieltexte der Zeichenfläche, z. B. „Fehler: Die PLZ hat 5 Ziffern.“, „Summe“ mit „652,31 €“),
  `::test_theme_parameter_zeigt_einen_rahmen` (Fassung 4: `?theme=dunkel` → `<html
  data-theme="dunkel">` und `color-scheme` `dark`, genau ein Rahmen ohne Themenklasse),
  `::test_ids_eindeutig_trotz_zwei_rahmen` (Fassung 4: Vorsilbe `hell-`/`dunkel-`, jedes `for` und
  `aria-describedby` trifft eine `id`),
  `::test_theme_parameter_nur_bekannte_werte` (`?theme=xyz` → 200, ignoriert, nicht gespiegelt,
  kein 422), `::test_verlangt_anmeldung_und_steht_nicht_in_der_navigation`,
  `::test_keine_daten_der_gesellschaft` (Name, Kürzel und Buchungen der Testgesellschaft kommen
  im Inhalt nicht vor), `::test_beispielfragment_mit_data_fokus` (mit `HX-Request` ein Fragment
  mit genau einem `data-fokus`-Element; ohne 303 auf `/muster#austausch`).

### Schritt 5 — Browserprobe als Werkzeug

- [ ] **Welt** `tests/browserprobe_welt.py` (`python -m tests.browserprobe_welt --port 8473
  --ziel DIR`): baut mit `tests.pruefen_hilfe.queuewelt` einen Bestand (zwei Gesellschaften,
  Benutzer `jan` buchhalter, `fritz` freigeber, `leo` betrachter, `vera` verwalter, ein Benutzer mit
  allen Rollen; Prüfschlange mit PDF-, Bild- und E-Rechnungsbeleg; ein Zahlungslauf), schreibt
  `probe.json` (Basis-URL, je Benutzer Passwort und TOTP-Geheimnis, Liste aller GET-Seiten mit
  Beispiel-IDs je Rolle) und startet die App mit uvicorn auf 127.0.0.1. Nur im Wegwerf-Ordner:
  *Test* `tests/test_browserprobe_welt.py::test_welt_listet_jede_get_route` (jede GET-Route der
  Registry kommt mit Beispielwerten vor und liefert 200 bzw. die erwartete 403).
- [ ] **Browser auf dem Server:** Vor dem ersten Lauf die Freigabe des Nutzers für den Download
  von Chromium 1248 samt Headless-Shell (Playwright 1.64.0, von Microsofts CDN) einholen. Ohne
  Freigabe `package.json` und Lockdatei auf `playwright` 1.59.1 setzen (Chromium 1217 liegt schon
  da; Werte unter Recherche) und das im PR vermerken.
- [ ] **Probe** `scripts/browserprobe/` (`package.json`, `package-lock.json`, `.npmrc`,
  `probe.mjs`, `README.md` mit der Bezugsquelle der Browser): Anmeldung je Rolle (TOTP mit
  `node:crypto` wie in der Spec-Probe), Messungen als Funktionen je Kriterium, Ausgabe JSON +
  Bildschirmfotos. Grundmessungen sofort: `scrollWidth` (AK1), axe-core 4.14.0 mit `runOnly:
  wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` (AK2), Konsole ohne CSP-Meldung (AK5). Weitere
  Messungen kommen mit den Schritten, die sie betreffen; die vollständige Liste steht in
  Schritt 14. `.gitignore`: `scripts/browserprobe/node_modules/`, `scripts/browserprobe/ergebnisse/`.
- [ ] **Referenzbilder der Leinwand** (Fassung 4, L10 Punkt 1): `scripts/browserprobe/leinwand.mjs`
  (`--quelle docs/design/2026-10-26-leinwand --ziel scripts/browserprobe/ergebnisse/leinwand`).
  Es kopiert jede Zeichenfläche hell und dunkel in den Ergebnisordner und ersetzt dabei die
  Platzhalter, sonst nichts; das Original bleibt unverändert. Dann öffnet es jede Kopie in der Breite
  der Zeichenfläche aus `canvas.json` und speichert ein ganzseitiges Bild. Ohne Netz, ohne
  `support.js`. Beim Planen mit `playwright-core` 1.59.1 und Chromium 1217 erprobt (20 Bilder,
  kein waagrechtes Scrollen); die Kopien entstehen nur im Ergebnisordner (`.gitignore`).
- [ ] **Erster Lauf gegen `/muster`** in Chromium, hell und dunkel, 1440/390/320: 0 Verstöße,
  kein waagrechtes Scrollen, Fokus nach dem Austausch über `/muster/beispiel` auf dem
  `data-fokus`-Element. **Fassung 4:** dazu die Maßprobe aus L10 Punkt 4 auf `/muster` (beide
  Rahmen) und das Bild von `/muster` bei 1440 px neben `Bausteine-hell.png`/`-dunkel.png` –
  Abweichungen sind Fehler der Komponenten aus Schritt 4 oder stehen in L7. Ergebnis im Plan unter
  „Umsetzung“ festhalten.

### Schritt 6 — Registry, Bereiche, Lesezugriff, Zähler

- [ ] **Registry** (`Bereich`, `Navigationspunkt` neu, `navigation()` sortiert nach Bereich und
  Reihenfolge; Punkte in `seiten/start.py`, `seiten/pruefen.py`, `seiten/freigaben.py` mit Bereich,
  Symbol, Zähler; Freigaben mit `frozenset({ZAHLUNG_FREIGEBEN, STEUER_FREIGEBEN})`): *Tests*
  `tests/test_api_navigation.py::test_bereiche_je_rolle_in_reihenfolge` (AK44: alle vier Rollen
  gegen eine Test-Registry mit Stub-Seiten für Belege, Steuern, Auswertungen und Einstellungen –
  genau die erlaubten Bereiche in der Reihenfolge aus A1), `::test_einstellungen_abgesetzt_nur_mit_verwalten`,
  `::test_freigaben_nur_mit_freigaberecht_seite_aber_lesbar`, `::test_bereich_ohne_seite_entfaellt`,
  `::test_symbol_muss_im_sprite_stehen`; umgestellt `tests/test_api_app.py::test_navigation_nur_mit_recht`
  (Absicht: ein Punkt ohne Recht fehlt; Freigaben ist für den betrachter jetzt der Beispielfall)
  und `::test_registry_findet_router_module`.
- [ ] **Zähler** (`buchung/pruefschlange.anzahl_offen`, `db/repo_zahlung.anzahl_laeufe`):
  *Tests* `tests/test_pruefschlange.py::test_anzahl_offen_gleich_der_liste` (mit zurückgestellten
  Einträgen), `tests/test_zahlung_freigabe.py::test_anzahl_laeufe_je_status` (dort stehen die
  Tests zu `lade_laeufe`). **Messung** (kein Test): `anzahl_offen` bei 50 000 Buchungen in SQLite;
  über 50 ms kommt `ix_buchungssaetze_status` in die Migration aus Schritt 3. Ergebnis unter
  „Umsetzung“.
- [ ] **Lesezugriff** (`api/lesezugriff.py`, `app.state.lesezugriff`, geschlossen in der
  `lebenszeit` von `app.py`; Entscheidung „Zähler“): *Tests*
  `tests/test_api_lesezugriff.py::test_sqlite_nur_lesend` (Schreibversuch scheitert),
  `::test_fehlende_sqlite_datei_wird_nicht_angelegt`, `::test_legt_keine_tabelle_an` (kein
  `init_db`), `::test_frist_bei_haengender_verbindung` (eine Zählerfunktion blockiert länger als
  die Frist → `None` nach höchstens Frist plus Toleranz; eine zweite Anfrage an eine andere
  Gesellschaft läuft währenddessen durch; die Zählerfunktion lief in einem Thread des eigenen
  Pools – Threadname mit Vorsilbe `zaehler` –, nicht in `run_in_threadpool`),
  `::test_schliessen_wartet_nicht_auf_haengende_zaehler`, `::test_postgresql_mit_zeitlimits`
  (`@mit_postgresql`: `connect_timeout` und `statement_timeout` wirken, Schreiben scheitert).
- [ ] **`seite()` asynchron** (alle 19 Aufrufe mit `await`; `anmeldung._formular` und
  `pruefen._antwort` werden `async`; Gerüst-Kontext aus `api/geruest.py`; Zähler über den
  Lesezugriff in einem Aufruf seines Pools, nur für ganze Seiten mit Status < 400; die Fehlerwege in
  `app.py` rufen `seite(…, zaehler=False)`): *Tests*
  `tests/test_api_navigation.py::test_zaehler_im_geruest` (ganze Seite: `geruest.bereiche` tragen
  die Zahlen; sichtbar werden sie mit den Leisten in Schritt 7), `::test_zaehler_nicht_fuer_fragmente`
  (Arbeitsfläche mit `HX-Request` → Zählerfunktion nicht aufgerufen),
  `::test_zaehler_fehler_laesst_nur_den_zaehler_weg` (Ausnahme und `OperationalError` „database
  is locked“; Protokoll nur mit der Art), `::test_keine_zaehler_auf_fehlerseiten` (503 über einen
  erzwungenen „database is locked“, 404 und 422: Zählerfunktion nicht aufgerufen); `mypy --strict`
  grün (fehlende `await` fallen dort auf).

### Schritt 7 — Gerüst

- [ ] **`basis.html` neu** (Sprunglink; Kopf in der festen Reihenfolge Sprunglink → „accounti“ →
  Gesellschaft → Hilfe → Benutzermenü; Kopfleiste breit/schmal, schmal mit
  `env(safe-area-inset-top/-left/-right)`; Seitenleiste und untere Leiste (mit
  `env(safe-area-inset-bottom)`) über die Navigationsmakros, die untere Leiste im überschreibbaren
  Block `untere_leiste` – P3 und P7 setzen dort die `aktionsleiste` ein, der Rückweg steht dann
  oben; `main#inhalt tabindex="-1"`; Brotkrumen; Statusbereich `#status`; `#netzhinweis`;
  Druckkopf; `<title>`-Muster; `data-theme`, `data-tastenkuerzel` aus den Vorlieben; die Zeile
  „Gesellschaft: …“ entfällt) und **`schlicht.html`**. **Aussehen** nach L4/L5 (Fassung 4): Kopf
  56 px mit Wortmarke, Gesellschafts-Chip (Marke 28 + Name + Chevron, Link nur bei mehreren
  Gesellschaften), Hilfe mit Symbol und Text, Benutzermenü mit Avatar; schmal Marke, Titel,
  Hilfe-Symbol, Avatar; Seitenleiste 232 px mit betontem und neutralem Zähler; untere Leiste 64 px
  mit dem Zähler in der Beschriftung; `schlicht.html` wie der Kopf von „Assistent-Steuern“. Die Marke
  kommt aus `geruest.marken()` (Monogramm und Farbe; die Regeln prüft Schritt 8). *Tests*
  `tests/test_api_geruest.py::test_titel_seite_gesellschaft_accounti` (DE und EN; ohne Anmeldung
  „Anmelden · accounti“), `::test_kennfarbe_und_kuerzel_auf_jeder_seite` (Klasse `marke-n`,
  Monogramm als Text, der Name sichtbar oder als `.unsichtbar`-Text, kein `aria-label` an einem
  `span` (L7 Nr. 13), `data-gesellschaft` mit dem Registry-Kürzel; alle GET-Seiten ohne Parameter
  und die Fachseiten),
  `::test_keine_zeile_gesellschaft_im_inhalt`, `::test_genau_ein_h1` (AK46: alle GET-Routen
  einschließlich Seiten mit Parametern, Fehlerseiten, Anmeldung, Hilfe, Muster),
  `::test_brotkrumen_unterhalb_eines_bereichs` (AK46: `/pruefen/{id}`, `/pruefen/regeln`;
  übersetztes `aria-label`, letzter Eintrag `aria-current="page"`), `::test_sprunglink_ist_erstes_ziel`,
  `::test_hilfe_link_gleiche_stelle` (AK47 in der Auslegung unter „Abweichungen“: in `webwelt`
  mit zwei Gesellschaften für jeden Benutzer derselbe Index des Hilfe-Links unter den
  fokussierbaren Elementen des Kopfs auf allen seinen Seiten im Gerüst einschließlich der
  Fehlerseiten 403/404/409/422/503; auf allen Seiten, auch Anmeldung und 500, die relative
  Reihenfolge Sprunglink < „accounti“ < [Gesellschaft] < Hilfe < [Benutzermenü bzw. -symbol] –
  die schlichte 500 nimmt der Index-Vergleich ausdrücklich aus, sie kommt mit Schritt 11 nur in
  den Vergleich der Reihenfolge),
  `::test_benutzermenue_breit_und_symbol_schmal` (Mein Konto, Sprache, Darstellung, Hilfe,
  Abmelden; Symbol verlinkt `/menue#konto`), `::test_untere_leiste_ziele` (AK6: buchhalter vier,
  freigeber fünf Ziele mit Test-Registry inkl. Belege; nie mehr als fünf; „Mehr“ zuletzt;
  `aria-current`), `::test_zaehler_in_seitenleiste_und_unterer_leiste` (aus Schritt 6 hierher,
  die Leisten entstehen erst jetzt; Fassung 4: in der Seitenleiste als `zaehler` mit
  `zaehler-betont` für Prüfen, in der unteren Leiste in der Beschriftung),
  `::test_safe_area_im_kopf_und_in_der_leiste` (statisch in `accounti.css`),
  `::test_masse_des_geruests` (Fassung 4, statisch in `accounti.css`: `--kopfhoehe: 3.5rem`,
  `--leistenhoehe: 4rem`, `--seitenleiste: 14.5rem`; die Seitenleiste ist ab 64rem sichtbar und
  darunter `display: none`, die untere Leiste umgekehrt), `::test_druckkopf`, `::test_statusbereich_role_status` (`#status` steht beim
  Laden leer im DOM), `::test_data_theme_aus_der_wahl` (auto/hell/dunkel → `data-theme`, Meta
  `color-scheme`).
- [ ] **Umstellungen** (Absicht bleibt): `tests/test_api_gesellschaften.py::test_akzeptanz_5_wechsel_aendert_alle_ansichten`
  (statt „Gesellschaft: <strong>…</strong>“: `data-gesellschaft="b"` in der Kopfleiste und
  `<title>… · Beta Rahmen KG · accounti</title>`; „Beta Rahmen KG“ vor dem Wechsel auf
  `/gesellschaft` statt im Wechsler des Kopfes), `tests/test_akzeptanz_web.py` (:338, ebenso),
  `tests/test_api_sprache.py::test_html_lang_und_navigation_englisch` (Titel statt Zeile;
  „Approvals“ fehlt für jan, der buchhalter ist – die Absicht „Navigation englisch“ prüft der
  Test mit „Overview“ und „Review“ für jan und „Approvals“ für einen freigeber),
  `::test_jede_seite_in_beiden_sprachen` (Titel statt Zeile), `tests/test_i18n.py::test_platzhalter_werden_escaped`
  (anderer Katalogeintrag mit Platzhalter und Markup, weil „Gesellschaft: <strong>…“ verwaist; der
  Teil mit „Ihre Rolle in %(gesellschaft)s erlaubt das nicht“ bleibt unverändert).

### Schritt 8 — `/menue`, `/gesellschaft`, Kennfarbe

- [ ] **Kennfarbe** (`geruest.kennfarben`, Eingabe immer `dienste.gesellschaften`): *Tests*
  `tests/test_api_geruest.py::test_kennfarbe_stabil_je_kuerzel`, `::test_kennfarben_ohne_dopplung_bis_sechs`,
  `::test_gewaehlte_farbe_geht_vor` (Schnittstelle für P5), `::test_kennfarbe_gleich_fuer_alle_benutzer`
  (zwei Benutzer mit Rollen in verschiedenen Gesellschaften sehen für die gemeinsame Gesellschaft
  dieselbe `marke-n`).
- [ ] **Monogramm** (Fassung 4, B24; `geruest.monogramme` und `geruest.marken`, Eingabe immer
  `dienste.gesellschaften`): *Tests* `tests/test_api_geruest.py::test_monogramm_aus_dem_namen`
  („Galerie Demo GmbH“ → `GD`, „Kunsthandel UG“ → `KU`, „Beta Rahmen KG“ → `BR`, ein Wort →
  die ersten zwei Zeichen, Umlaute bleiben), `::test_monogramm_eindeutig_je_registry` (zwei Namen
  mit gleichen Anfangsbuchstaben → das spätere Kürzel weicht auf sein Registry-Kürzel aus, danach
  auf Buchstabe + Ziffer; immer zwei Zeichen), `::test_monogramm_gleich_fuer_alle_benutzer`.
- [ ] **`/menue`** (`api/seiten/menue.py`, `vorlagen/menue.html`; im selben Schritt `SEITEN`,
  `HTMX_FORMEN` (`fragment`), `en.yaml`). Aussehen wie „Handy-Mehr“ (L4 „Gruppenliste“, L8): drei
  Gruppen mit Etikett, Zeilen 48 px, Zähler und `chevron-right`, die aktive Gesellschaft mit „aktiv“,
  die anderen als Formular-Knopf mit „n zu prüfen“, „Abmelden“ als stiller Knopf in der Liste.
  *Tests*
  `tests/test_api_navigation.py::test_menue_ohne_js` (AK6: alle erlaubten Bereiche mit Zählern,
  Gesellschaften als POST-Formulare mit CSRF, Abschnitt `id="konto"` mit Mein Konto, Hilfe,
  Abmelden), `::test_menue_einstellungen_und_freigaben_nur_mit_recht`, `::test_menue_fragment_mit_hx_request`,
  `::test_menue_gruppen_wie_leinwand` (Fassung 4: Etiketten „Bereiche“, „Gesellschaft“, „Mein Konto“
  in dieser Reihenfolge, je eine `.gruppenliste`, Marke mit Monogramm je Gesellschaft).
- [ ] **`GET /gesellschaft`** (`seiten/gesellschaft.py`, `vorlagen/gesellschaften.html` als
  `.gruppenliste` mit Marke, Name, Zählern und „aktiv“ (L8),
  `geruest.gesellschaften_mit_zaehlern` über den Lesezugriff; im selben Schritt `SEITEN`,
  `HTMX_FORMEN`, `en.yaml`): *Tests*
  `tests/test_api_gesellschaften.py::test_gesellschaftsseite_nur_mit_rolle`,
  `::test_zaehler_je_gesellschaft`, `::test_freigaben_zahl_nur_mit_freigaberecht`,
  `::test_nicht_erreichbare_gesellschaft_bricht_die_seite_nicht` (Ausnahme im Zähler),
  `::test_haengende_gesellschaft_haelt_die_seite_nicht_auf` (Zähler einer Gesellschaft blockiert →
  Seite nach höchstens der Frist mit „nicht erreichbar“),
  `::test_fehlende_datenbankdatei_wird_nicht_angelegt` (SQLite-Pfad einer Gesellschaft ohne Datei
  → „nicht erreichbar“, danach keine Datei), `::test_gesellschaft_fragment_mit_hx_request`;
  `::test_wechsel_per_post` (Schutz, bestehender Weg).

### Schritt 9 — Mein Konto, Sprachwahl-Umzug, Tastenkürzel, `accounti.js`

- [ ] **`/konto` und `POST /konto/vorlieben`** (`api/seiten/konto.py`, `vorlagen/konto.html`;
  `seiten/sprache.py` entfällt, der alte Pfad steht in `konto.py`; im selben Schritt `SEITEN`
  für `/konto` und `/konto/vorlieben`, `GLEICHLAUF` (Ausnahme A113 für `/konto/vorlieben`),
  `HTMX_FORMEN`, `en.yaml`): *Tests*
  `tests/test_api_konto.py::test_konto_fuer_jede_rolle`, `::test_vorlieben_ohne_js_303_und_wirkung`
  (AK45: Darstellung dunkel → nächste Seite `data-theme="dunkel"`, auch nach neuer Anmeldung),
  `::test_teilformular_aendert_nur_gesendete_felder`, `::test_ungueltige_wahl_422_mit_fehlerliste`,
  `::test_mit_htmx_hx_refresh`, `::test_weiter_nur_relativ`, `::test_alter_sprachpfad_308_und_wirkt`
  (AK45), `::test_tastenkuerzel_als_data_attribut`, `::test_konto_fragment_mit_hx_request`;
  umgestellt `tests/test_api_sprache.py::test_sprache_wechseln_braucht_csrf`,
  `::test_sprache_bleibt_nach_neuer_anmeldung`, `::test_automatisch_folgt_wieder_dem_browser`
  (über `/konto/vorlieben`).
- [ ] **`statisch/accounti.js` neu** (aus `pruefen.js` übernommen: Fehlerhinweis; neu: `aria-busy`
  am Ziel während einer htmx-Anfrage, Fokus auf `[data-fokus]` nach Laden und `htmx:afterSettle`,
  Benutzermenü bei `Esc`/Klick daneben schließen) und **`pruefen.js` ohne `localStorage`** (liest
  `document.body.dataset.tastenkuerzel`; Tastenhilfe: Formular „Tastenkürzel ausschalten“ statt
  Haken): *Tests* `tests/test_api_statisch.py::test_skripte_ohne_speicher` (kein `localStorage`,
  `sessionStorage`, `indexedDB`, `document.cookie`), `::test_eigenes_skript_ohne_eval_und_innerhtml`
  (Schutz, gilt jetzt für beide), `::test_skripte_budget` (zusammen ≤ 20 480 Bytes, AK50);
  umgestellt `::test_tasten_in_markup_und_skript_gleich` (Tasten aus `TASTEN_PRUEFEN`, Tastenhilfe
  ohne Haken `tasten-aus`) und `tests/test_api_pruefen.py::test_tastenbelegung_im_markup` (:326:
  statt `id="tasten-aus"` das Formular mit `tastenkuerzel=aus`).
- [ ] **Strg+Enter unabhängig von der Optik** (B21): `pruefen.js` sucht
  `button[data-hauptknopf]` statt `button.hauptknopf` (Rückfall weiter der erste Absendeknopf);
  „Korrigieren“ in `pruefen/_korrektur.html:51` trägt `data-hauptknopf` (ab Schritt 12 über
  `knopf(…, attribute={"data-hauptknopf": "ja"})`, unabhängig davon, ob der Knopf primär oder
  sekundär ist): umgestellt `test_api_statisch.py::test_tasten_in_markup_und_skript_gleich`
  (:184, Selektor `button[data-hauptknopf]`) und
  `test_api_pruefen.py::test_korrigieren_ist_der_standardknopf` (:341, `data-hauptknopf` im
  ersten Absendeknopf statt `class="hauptknopf"`).

### Schritt 10 — Hilfe

- [ ] **`api/hilfe_inhalt.py`, `api/seiten/hilfe.py`, `vorlagen/hilfe/index.html`,
  `vorlagen/hilfe/thema.html`** (Kurzanleitung, Begriffe, Tastenkürzel; `vielleicht_angemeldet`;
  `thema` als `str`; im selben Schritt `SEITEN` (`OFFEN`), `HTMX_FORMEN`, `en.yaml`): *Tests*
  `tests/test_api_hilfe.py::test_jeder_bereich_hat_eine_hilfeseite` (AK47: jeder Bereich der
  **echten** Registry hat einen Eintrag; `/hilfe/<bereich>` 200), `::test_fehlende_hilfe_wird_gemeldet`
  (Test-Registry mit Stub-Seiten: `fehlende_hilfe` nennt Belege, Steuern, Auswertungen,
  Einstellungen), `::test_ohne_anmeldung_ohne_daten_der_gesellschaft`, `::test_angemeldet_mit_geruest`,
  `::test_keine_links_auf_fremde_hosts` (AK47), `::test_begriffe_aus_anhang_b` (jeder Begriff aus
  Anhang B auf `/hilfe`, AK57), `::test_tasten_aus_einer_quelle`, `::test_unbekanntes_thema_404`
  (`/hilfe/xyz` und ein bekanntes Thema ohne Eintrag wie `/hilfe/belege`: 404, nie 422 oder 500),
  `::test_abschnitt_zahlungslauf` (`/hilfe/freigaben#zahlungslauf` für den leeren Zustand),
  `::test_hilfe_fragment_mit_hx_request`, `::test_hilfe_bei_gesperrter_systemdatenbank_schlicht`
  (`sitzung._lade` wirft `OperationalError` „database is locked“ → 200 im schlichten Layout,
  Protokoll nur die Art; B23).

### Schritt 11 — Fehler- und Statusseiten

- [ ] **403 mit Recht und Rollen** (`sitzung.verweigert`, `Verweigerung`; `seiten/pruefen.py` um
  :593 und :650 nutzen `verweigert`; `fehler.html` rendert Rechte und Rollen strukturiert): *Tests*
  `tests/test_api_fehlerseiten.py::test_403_nennt_recht_und_rollen` (DE und EN; Rollenkennungen in
  `<span lang="de">`), `::test_403_api_json_mit_dem_satz`; `tests/test_i18n.py::test_platzhalter_werden_escaped`
  und `tests/test_api_sprache.py::test_fehlerseite_uebersetzt` (Schutz: der erste Satz bleibt
  eigene msgid, wörtlich).
- [ ] **`fehler.html`, `_fehler.html`, `http_fehler`/`ungueltig`/`beschaeftigt` auf die neuen
  Vorlagen (alle mit `zaehler=False`); 404 mit `vielleicht_angemeldet`**: *Tests*
  `::test_404_im_design_mit_weg_zurueck` (angemeldet mit Navigation, abgemeldet schlicht),
  `::test_404_bei_gesperrter_systemdatenbank_schlicht` (angemeldet, `sitzung._lade` wirft
  `OperationalError` „database is locked“ → 404 im schlichten Layout, keine 500; B23),
  `::test_409_im_design` (veralteter Freigabe-Hash), `::test_htmx_fehler_als_fragment` (409, 422,
  503 mit `HX-Request`: kein `<html`, `role="alert"`, AK58), `::test_api_fehler_bleiben_json` (Schutz).
- [ ] **500 schlicht** (`api/sicherheit.py` ruft `vorlagen.fehlerseite_500`; die Middleware bleibt
  die äußerste – auch vor der Middleware aus P4): *Tests*
  `::test_500_ohne_einzelheiten` (Test-Route wirft `RuntimeError("geheim-4711")`: Status 500,
  `h1` „Interner Fehler“, Link zurück, weder „geheim-4711“ noch „Traceback“ noch „RuntimeError“ in
  der Antwort; im Protokoll nur die Art), `::test_500_fragt_keine_datenbank`,
  `::test_sicherheit_ist_die_aeusserste_middleware` (`erstelle_app(…).user_middleware[0].cls is
  Sicherheit` – in Starlette ist die zuletzt mit `add_middleware` eingetragene die äußerste; eine
  später eingetragene Middleware, etwa `Einstellungsstand` aus P4, macht den Test rot),
  `::test_ausnahme_in_innerer_middleware_gibt_designseite` (eine Test-Middleware, die wirft, vor der
  ersten Anfrage innen eingehängt: 500 als schlichte Designseite ohne Einzelheiten); umgestellt
  `tests/test_api_htmx.py::test_andere_operationalerror_bleiben_500` (Status 500 und Designseite
  statt Klartext; „no such table“ weder in Antwort noch Protokoll).

### Schritt 12 — Bestehende Seiten ins neue Design (A121)

Reihenfolge: Anmeldung → Übersicht → Freigaben → Prüfen (Liste, Arbeitsfläche, Regeln) →
Buchung → Beleg, je Seite ein Commit; jeder Seiten-Commit löscht die Regeln seiner Seite aus
`@layer bestand` (in `accounti.css` bzw. `pruefen.css`, B20). Nach jeder Seite die Browserprobe für
diese Seite (R8); was dann noch in `bestand` steht, gehört zu Seiten, die noch nicht umgestellt
sind, und verliert bei gleichen Klassennamen gegen die Komponenten.
**Keine** neue Bedienung: dieselben Felder, Knöpfe, Tasten und Routen; nur Gerüst, Komponenten,
Token und Markup-Ordnung.

**Fassung 4 – Optik nach der Leinwand:** Jede Seite übernimmt die Optik der Zeichenfläche, die ihr
in L8 zugeordnet ist, aber **mit ihren bisherigen Inhalten und Wörtern**. Die Wörter nach
Anhang B, die Gruppen, die Auswahl und die drei Schritte der Arbeitsfläche bringt P3 (L7 Nr. 23).
Hat eine Seite eine Zeichenfläche (Übersicht, Prüfen, Arbeitsfläche, Freigaben), kommt ihr Bild aus
der Probe nach jedem Seiten-Commit in die Gegenüberstellung aus L10.

- [ ] **Querschnittstests zuerst** (`tests/test_api_bestand_design.py`, parametrisiert über die
  Liste `UMGESTELLT` der schon umgestellten Seiten, anfangs leer; jede Seite kommt mit ihrem
  Commit hinein und macht die Tests für sich erst rot, dann grün):
  `::test_codefelder_mit_sichtbarem_label_und_ein_feld` (AK49 I10, AK53),
  `::test_hauptaktion_ist_primaerknopf` (AK49 I12: Anmelden; Freigeben auf der Arbeitsfläche – ist
  es wegen `e.freigabe_gesperrt` ausgeblendet, ist Korrigieren der primäre Knopf; Freigeben auf
  `/freigaben`; Korrigieren auf `/buchungen/{id}`),
  `::test_jedes_sichtbare_feld_mit_label_for` (AK53; kein Feld nur mit Platzhalter oder
  `aria-label`), `::test_jede_tabelle_mit_caption_und_rollen` (AK52),
  `::test_beschreibungslisten_sind_komponente` (I11 statisch), `::test_ids_je_seite_eindeutig`
  (jede `id` einer Seite einmal; jedes `for`, `aria-describedby`, `aria-controls` und jeder Link
  `#…` der Fehlerliste zeigt auf eine vorhandene `id`; Seiten mit zwei Formularen und mehreren
  Codefeldern eingeschlossen), `::test_422_mit_fehlerliste_und_aria` (AK53: Korrektur ohne
  Steuerangabe auf der Arbeitsfläche → 422, `role="alert"`, Link `#steuer`, `aria-invalid`,
  `aria-describedby`, Eingaben außer Codes erhalten; auf `/buchungen/{id}` Storno ohne Grund →
  Link `#grund-s`), `::test_jede_liste_mit_leerem_zustand` (AK54 mit leerer Datenbank: Satz und
  Link, kein `role`), `::test_code_parameter_je_seite` (jede umgestellte Seite mit Codefeld –
  Anmeldung, `/freigaben`, `/buchungen/{id}`: `?code=wiederherstellung` schaltet **alle**
  Codefelder der Seite auf die Textvariante mit Label „Wiederherstellungscode“ und Rückweg;
  `?code=xyz` → 200 mit Standardfeldern, Wert nicht gespiegelt, kein 422).
- [ ] **Anmeldung** (`schlicht.html` mit dem Kopf aus L5, Karte höchstens 26rem zentriert, `feld`
  für Benutzer/Passwort, `codefeld` mit Variante `?code=wiederherstellung` und durchgereichtem
  `weiter`, Knopf primär, `breit`): *Tests*
  `tests/test_api_anmeldung.py::test_codefeld_numerisch_mit_wiederherstellungsweg`,
  `::test_anmeldung_mit_wiederherstellungscode_ohne_js` (Variante, dann Anmeldung mit einem der
  Codes), `::test_wiederherstellungsweg_behaelt_weiter` (`/anmelden?weiter=/pruefen` → der Link
  trägt `weiter=%2Fpruefen`; Anmeldung über die Variante landet auf `/pruefen`; ein fremdes
  `weiter` wird über `sicheres_ziel` zu `/`), `::test_code_parameter_unbekannt_ignoriert`
  (`?code=xyz` → 200 mit Standardfeld, kein 422; für `/freigaben` und `/buchungen/{id}` prüft das
  `test_code_parameter_je_seite`), alle Anmeldetests aus 10a (Schutz).
- [ ] **Übersicht** (`start.html` in der Optik von „Main“: `.seitenkopf` mit `h1` „Übersicht“,
  darunter das Etikett und die vier Zahlen als **Kennzahl-Karten** (`karte(kennzahl=…)`, Zahl in
  `--gr-9`, Satz in `--text-2`, wie die Karte „Prüfen“ der Leinwand) im Layout `karten`; Tabelle
  der fälligen Posten als `tabelle` mit `betrag`; leerer Zustand. Keine neue Zahl – P2 baut die
  Übersicht mit den sechs Karten der Leinwand neu): *Test* `tests/test_api_app.py::test_uebersicht_im_design`
  (vier Karten mit Klasse `kennzahl`, Zahl und Beschriftung in `.layout-karten`, dieselben Zahlen
  wie bisher; Tabelle mit `caption`; mit leerer Datenbank Leerzustand mit Link).
- [ ] **Freigaben** (in der Optik von „Handy-Freigaben“: je Lauf eine `karte` mit Titel, rechts der
  Betrag in `--gr-6`, `angaben`, Zahlungstabelle als `tabelle(in_karte=True)` (Karten unter
  40rem), Formular mit `codefeld(id="einmalcode-lauf-<nr>")` und primärem Knopf (unter 40rem
  `breit`); die Texte bleiben die von 10b-1, `aufklapper` und Werte der USt-VA bringt P2;
  USt-VA-Formular mit `feld` „Zeitraum“ und Hilfetext „Monat (2026-09) oder Quartal (2026-Q3)“
  statt Platzhalter, `codefeld(id="einmalcode-ustva")`; `?code=` als `str`-Parameter der Route,
  nur `wiederherstellung` wirkt; leere Zustände mit Link auf
  `/hilfe/freigaben#zahlungslauf`): `tests/test_api_rechte_matrix.py::test_ustva_freigabe_im_browser`
  und `::test_vier_augen_im_browser` (Schutz; `freigabe_hash` findet `name="freigabe_hash"
  value="…"` weiter).
- [ ] **Prüfen** (Liste in der Optik von „Pruefen-Liste“: `reiter` mit 3-px-Strich und Anzahl,
  „Durcharbeiten“ als `linkknopf(art="sekundaer", taste="j")` rechts neben dem Etikett, `tabelle`
  mit Kopf auf `--flaeche-2`, Betrag rechtsbündig über `betrag()`, Karten unter 40rem,
  `seitenblaettern`, `leer` ohne das dauerhafte `role="status"` aus `liste.html:40`; die Spalten
  bleiben die von 10b-1. Arbeitsfläche in der Optik von „Pruefen-Arbeitsflaeche“, aber im Gerüst
  (L7 Nr. 19): Positionszeile `.queue-kopf` wie die Prüfschlangen-Leiste („‹ Zur Liste“, „3 von
  12“, „Voriger k“, „Nächster j“), `layout-zweispaltig` (Beleg-Spalte mit Etikett, Vorschlag als
  Karte mit Name in `--gr-7` und Betrag in `--gr-8`), Vorschlag als `angaben(klein=True)`,
  Hinweise als `hinweis`, Freigeben als `knopf("primaer", groesse="gross", breit=True, taste="f")`
  (bei `e.freigabe_gesperrt` Korrigieren), Korrigieren und Zurückstellen als `feldgruppe` mit
  `feld`, Knöpfe sekundär,
  „Korrigieren“ mit `attribute={"data-hauptknopf": "ja"}` (Strg+Enter, Schritt 9);
  `fehlerkasten` → `fehlerliste` mit Link auf das Feld aus `StornoError.feld`, `feldfehler` setzt
  zusätzlich `aria-describedby`; Ergebnistext der htmx-Aktionen per `hx-swap-oob="innerHTML:#status"`,
  die sichtbare Meldung ohne `role`; Regeln: `tabelle`, Grund-Feld mit sichtbarem Label statt nur
  `.unsichtbar`; Tastenhilfe aus `TASTEN_PRUEFEN`): *Test*
  `tests/test_api_pruefen.py::test_ergebnis_im_statusbereich` (Fragment nach Freigeben,
  Korrigieren, Zurückstellen und nach einem 409 enthält ein `hx-swap-oob`-Element für `#status`
  mit dem Ergebnistext). Die Tests aus 10b-1 bleiben grün; Markup-Tests werden auf Rollen und
  Texte umgestellt (Liste im PR).
- [ ] **Buchung und Beleg** (`angaben`, Journal als `tabelle`, Korrektur mit
  `codefeld(id="einmalcode-k")` und primärem Knopf, Storno mit `codefeld(id="einmalcode-s")` und
  `knopf("gefaehrlich")` für „Stornieren“, `fehlerliste(…, ids={"grund": "grund-k", …})` je
  Formular; `?code=` wie bei `/freigaben`; Belegvorschau-Rahmen mit `--beleg-hintergrund`): *Tests*
  `tests/test_api_buchungen.py::test_buchung_im_design` (Journal mit `caption`; zwei Codefelder
  mit eigenem Label; „Stornieren“ als gefährlicher Knopf; Fehlerliste eines Stornos verlinkt
  `#grund-s`), `tests/test_api_belege.py::test_beleg_im_design` (`angaben` als `dl`, Rahmen der
  Vorschau mit der Klasse für `--beleg-hintergrund`).
- [ ] **`pruefen.css` entfernen**, alle `{% block kopf %}`-Verweise darauf löschen, die leere
  Ebene `bestand` aus der Ebenenfolge streichen: *Tests*
  `tests/test_api_statisch.py::test_nur_eine_css_datei`,
  `tests/test_design_token.py::test_ebenenfolge_wie_entschieden` (genau `token, basis, layout,
  komponenten, seiten, hilfen, druck`, kein `bestand`).
- [ ] **Querschnitt vollständig**: *Test* `tests/test_api_bestand_design.py::test_alle_seiten_im_querschnitt`
  (`UMGESTELLT` = alle GET-Seiten der Registry plus die Fachseiten aus `fachseiten_html`).

### Schritt 13 — Querschnittstests (gelten ab hier für jedes Paket)

- [ ] **Rechte-Matrix** (die neuen Zeilen sind seit den Schritten 4, 8, 9, 10 drin):
  `::test_jede_rolle_gegen_jeden_endpunkt`, `::test_jeder_endpunkt_steht_in_der_matrix` (Schutz);
  `tests/test_api_csrf.py::test_jeder_post_ohne_csrf_403_und_nichts_geaendert` (Schutz, nimmt
  `/konto/vorlieben` von selbst mit).
- [ ] **Vollständigkeit** (die Listen stehen seit Schritt 0 und sind in jedem Schritt nachgetragen):
  *Test* `tests/test_api_vollstaendigkeit.py::test_htmx_formen_wirken` (je Route mit und ohne
  `HX-Request` aufgerufen: Fragment ohne `<html`, `HX-Refresh`, 303 bzw. ganze Seite; jede neue
  GET-Route liefert mit `HX-Request` ein Fragment, AK58).
- [ ] **Protokoll** (`tests/test_betrieb_protokoll.py::test_geruest_ohne_personenbezug`): Marker im
  Anzeigenamen, im Namen der Gesellschaft, in einem 404-Pfad und in einer 500-Ausnahme; nach
  Vorlieben, `/gesellschaft`, `/menue`, `/hilfe`, `/muster`, 404 und 500 steht keiner in der
  Protokollausgabe (AK59).
- [ ] **Abhängigkeiten und Fremdhosts** (`tests/test_abhaengigkeiten.py`):
  `::test_pyproject_ohne_neue_abhaengigkeit` (die **Paketnamen** in `dependencies` und
  `optional-dependencies` wie auf `main`; geänderte Versionsgrenzen bestehender Pakete sind
  erlaubt und stehen im PR; P6 trägt dort `segno` nach, AK60),
  `::test_keine_url_auf_fremde_hosts` (Vorlagen, CSS, eigene Skripte; erlaubt nur der
  SVG-Namensraum im Sprite, AK50), `::test_lizenzen_beigelegt` (htmx, Lucide),
  `::test_browserprobe_versionen_fest` (`package.json` mit genauen Versionen, Lockdatei mit
  Integrität, `ignore-scripts`).
- [ ] **Zweisprachigkeit** (`tests/test_i18n_katalog.py`): sammelt zusätzlich die Werte von
  `RECHT_TEXT` und die `N_()`-Texte aus `api/hilfe_inhalt.py` (liegt unter `api/`, also schon
  erfasst); `::test_begriffe_aus_anhang_b_im_katalog` (feste Liste der Spalte „Standardansicht“
  aus Anhang B, AK57); `tests/test_api_geruest.py::test_lang_je_sprache_auf_jeder_seite` (AK57).
- [ ] **Vorlagen-Scan** (`tests/test_api_statisch.py::test_keine_inline_skripte_stile_oder_ereignisattribute`):
  nimmt die neuen Seiten und `fehler_500.html` mit (Schutz, erweitert; AK5). Der
  Versionsanhang-Test ist seit Schritt 2 umgestellt.

### Schritt 14 — Browserprobe aller Seiten, Handprüfung

- [ ] **Probe in Chromium** auf dem Server (Browser aus Schritt 5; Firefox beim Nutzer) über jede
  Seite aus `probe.json`, je Rolle, hell und dunkel, bei 1440, 390 und 320 px. Messungen:
  - AK1: `document.documentElement.scrollWidth` ≤ Fensterbreite bei 320 und 390 px.
  - AK2: axe-core 0 Verstöße (A und AA) bei 1440 und 390 px, hell und dunkel.
  - AK4: im Dunkelmodus berechneter Hintergrund von `input`, `select`, `textarea`, `button` nicht
    `rgb(255, 255, 255)`; `kbd` ≥ 4,5 : 1 (aus berechneten Farben; `kbd` ist durchsichtig, als
    Hintergrund zählt der erste nicht durchsichtige Vorfahr, z. B. der primäre Knopf; die Deckkraft
    muss 1 sein).
  - AK5: keine CSP-Meldung in der Konsole (Kontext ohne `bypassCSP`), auch nach einem
    htmx-Austausch auf der Arbeitsfläche.
  - AK6/AK44: berechnetes `display` von Seitenleiste und unterer Leiste bei 1440 und 390 px,
    Höhe der Kopfleiste ≤ 56 px unter 64rem, ≤ 5 Ziele, Inhaltsbreite ≤ 90rem; kein
    abgeschnittener Titel in der unteren Leiste bei 320 px.
  - AK7: `<title>` und Kennfarbe nach dem Wechsel über `/gesellschaft`.
  - AK8: Emulation `print` einer Liste (`/pruefen`, `/freigaben`): keine Navigation, keine Knöpfe,
    Druckkopf sichtbar.
  - AK45: Darstellung „dunkel“ gespeichert → neuer Kontext nach Anmeldung `data-theme="dunkel"`,
    berechnetes `color-scheme` `dark`; „auto“ folgt `emulateMedia({colorScheme})`; mit
    „Tastenkürzel aus“ löst `f` auf der Arbeitsfläche keine Anfrage aus.
  - AK49: Bounding-Boxen von Label und Wert jeder `dl.angaben` überlappen nicht (I11); Codefeld mit
    sichtbarem `<label>` (I10); Hauptaktion mit Klasse `knopf-primaer` (I12).
  - AK50: Beträge mit `font-variant-numeric: tabular-nums`; mit `prefers-reduced-motion: reduce`
    jede `transition-duration` 0 s; jedes `svg.symbol` ohne sichtbaren Text mit `aria-label`, alle
    übrigen `aria-hidden`; berechnete `font-weight` nur 400 oder 600.
  - AK52: bei 390 px tragen Tabellen in Kartenform die Rollen, der ARIA-Schnappschuss
    (`page.accessibility`/`ariaSnapshot`) zeigt Zeilen und Zellen.
  - AK53: Einfügen in jedes Codefeld (Zwischenablage mit Rechten, `Strg+V`) ergibt den Wert;
    „Wiederherstellungscode verwenden“ ohne JS (Kontext mit `javaScriptEnabled: false`), das Ziel
    `weiter` bleibt.
  - AK55 (Auslegung: `/konto` statt einer Einstellungsseite): Tab durch `/pruefen`, die
    Arbeitsfläche und `/konto` bei 390 und 1440 px: das fokussierte Element liegt nie vollständig
    unter Kopfleiste oder unterer Leiste, Fokusring ≥ 2 px, erster Tab-Stopp „Zum Inhalt
    springen“, nach endlich vielen Tabs wieder am Seitenanfang; alle Klickziele ≥ 24 × 24 px, mit
    `hasTouch`/`isMobile` (pointer: coarse) ≥ 44 × 44 px, ausgenommen Links im Fließtext.
    Kontrollkästchen und Optionsfelder misst die Probe an ihrem umschließenden `label`
    (`.haken-ziel`, `.optionskarte`, `.segment label`), nicht am sichtbaren 18-px-Kästchen (L7 Nr. 20).
    Fokusring 3 px (L7 Nr. 8).
  - AK56: Fenster 640 × 400 CSS-px (entspricht 1280 px bei 200 % Zoom) und das
    Textabstands-Stylesheet aus WCAG 1.4.12: `scrollWidth` ≤ Fensterbreite, kein Element mit
    `overflow: hidden` mit `scrollHeight` > `clientHeight`.
  - AK54: nach einer Freigabe per htmx steht der Ergebnistext im globalen Bereich `#status`
    (`role="status"`), während der Anfrage trägt das Ziel `aria-busy="true"` (gemessen mit
    verzögerter Antwort über `page.route`).
  - A104: nach dem Austausch über `/muster/beispiel` ist `document.activeElement` das
    `data-fokus`-Element.
- [ ] **Bildvergleich und Maßprobe gegen die Leinwand** (Fassung 4, L10;
  `node scripts/browserprobe/probe.mjs --welt /tmp/accounti-probe/probe.json --browser chromium
  --vergleich scripts/browserprobe/ergebnisse/leinwand`):
  - Bilder von `/muster` (ohne Parameter bei 1440 px, `?theme=hell` und `?theme=dunkel` bei
    390 px), von `/` und `/pruefen` bei 1440 und 390 px, hell und dunkel, dazu `/pruefen/{id}`,
    `/freigaben` und `/menue` bei 390 px und `/pruefen/{id}` bei 1440 px.
  - Gegenüberstellung `ergebnisse/<datum>-vergleich.html` mit den Referenzbildern aus Schritt 5;
    je Paar ein Satz, was P1 abdeckt und was P2/P3 bringen. Kein Pixelvergleich als Abbruchgrund
    (Spec 8).
  - **Maßprobe** aus berechneten Stilen (bricht ab): Token hell und dunkel gleich L1, Kopfleiste
    56 px, untere Leiste 64 px, Seitenleiste 232 ± 1 px, Karte (Radius 10, Rahmen 1 px,
    Innenabstand 20/24), Knopf (≥ 44 px, Radius 6), Reiter-Strich 3 px `--akzent`, gewählte
    Optionskarte 2 px, Feldrand 1 bzw. 2 px, Fokusring 3/2 px, Pille ohne Umbruch (13 px, 600),
    Etikett in Versalien, Betrag ohne Umbruch – auf `/muster` in beiden Rahmen, auf den Kernseiten
    für die dort vorhandenen Komponenten.
  - Die Bilder (Gegenüberstellung) gehören als Referenz in den PR.
- [ ] **Handprüfung der Optik durch den Nutzer** (Fassung 4): die Gegenüberstellung öffnen und je
  Paar bestätigen „wie die Leinwand“ oder die Abweichung mit Bild nennen; Protokoll im PR.
  Python-Playwright gibt es im venv nicht und kommt wegen AK60 auch nicht hinein; die Bilder
  liefert die Node-Probe. Fehlen auf einem Rechner die Browser, vergleicht der Nutzer die
  Leinwand im Design-Werkzeug mit der laufenden Anwendung bei 1440 und 390 px von Hand.
- [ ] **Handprüfung (AK43)** für die Abläufe von P1 (Anmeldung, Navigation und „Mehr“,
  Gesellschaft wechseln, Mein Konto, Hilfe, Prüfen und Freigaben im neuen Design): nur Tastatur
  (auf dem Server per Playwright mit sichtbaren Fotos, beim Nutzer im Browser), NVDA + Firefox und
  VoiceOver auf iOS **beim Nutzer**; Protokoll im PR. Was offen bleibt, steht im PR als offen.

### Schritt 15 — Abschluss

- [ ] **Migration gegen jede Datenbank:** SQLite im Test, PostgreSQL über `ACCOUNTI_TEST_PG` mit
  der **ganzen Suite** (nicht nur `test_postgresql_rundlauf`: die CI hat keinen PostgreSQL-Dienst,
  `test_db_upgrade.py` hat eigene PostgreSQL-Fälle) und von Hand (System- und
  Gesellschaftsdatenbank: `accounti db upgrade`, `accounti check`, Downgrade auf `VOR`, wieder
  `db upgrade`); `alembic heads` genau ein Kopf und `SCHEMA_STAND` gleich diesem Kopf (AK61). Vor
  dem Merge den Kopf von `main` erneut lesen; wurde P4 oder ein Gesamttest-Branch vorher gemergt,
  `down_revision` und `SCHEMA_STAND` anpassen und dessen Migrationstests mit
  `git grep` wie in Schritt 0 auf Kopfannahmen prüfen (der Wächtertest aus Schritt 3 meldet sie).
  Die eigenen Tests bleiben unverändert: `VORLIEBEN` ist fest, `VOR` liest der Test als dessen
  `down_revision`, und keiner hängt am Kopf – auch nicht, wenn P4 oder ein anderes Paket **nach**
  P1 auf `<rev>` kettet.
- [ ] **Sicherung** (Rundlauf aus Schritt 3) gegen SQLite und PostgreSQL.
- [ ] **Docker-Probe:** `docker compose build`, `.env` in die Shell laden, `accounti db upgrade`
  für Systemdatenbank und jede Gesellschaft nach `docs/betrieb.md` (dabei eine Datenbank ohne
  Versionsvermerk), `docker compose up -d`, Anmeldung, Darstellung wechseln, Neustart, Wahl
  bleibt; `config/:ro` unverändert.
- [ ] **Testliste abgleichen (AK49):** `pytest --collect-only -q` des Branches gegen die Liste von
  `main` aus Schritt 0: jede Test-ID von `main` gibt es noch, oder sie steht mit neuem Namen in
  der Liste der umgestellten Tests im PR.
- [ ] **Gegnerische Prüfung** (zweite Person bzw. Prüfagent gegen diesen Plan und die Spec),
  `pytest`, `ruff` (ohne Cache), `mypy --strict` grün; Checkboxen abgehakt; Liste der
  umgestellten Tests und das Handprotokoll im PR; Abweichungen und Auslegungen im PR und als
  Nachtrag in der Spec (Abschnitt 12, „Nachträge aus P1“).
- [ ] **Doku-Bausteine** eingearbeitet (README, CHANGELOG, Bauplan, Architektur, Betrieb,
  THIRD-PARTY, CONTRIBUTING).

---

## Dateien

**Neu:** `src/accounti/api/geruest.py`, `api/lesezugriff.py`, `api/symbole.py`, `api/hilfe_inhalt.py` ·
`src/accounti/api/seiten/konto.py`, `seiten/menue.py`, `seiten/hilfe.py`, `seiten/muster.py` ·
`src/accounti/api/vorlagen/_komponenten.html`, `schlicht.html`, `fehler.html`, `_fehler.html`,
`fehler_500.html`, `konto.html`, `menue.html`, `gesellschaften.html`, `muster.html`,
`hilfe/index.html`, `hilfe/thema.html` · `src/accounti/api/statisch/symbole.svg`,
`LIZENZ-lucide.txt`, `accounti.js` · `alembic/versions/<rev>_add_benutzer_vorlieben.py` ·
`scripts/symbole.py` · `scripts/browserprobe/package.json`, `package-lock.json`, `.npmrc`,
`probe.mjs` (mit `--vergleich`), `leinwand.mjs`, `README.md` · `docs/specs/2026-10-26-oberflaeche-einrichtung.md`,
`docs/specs/2026-10-26-oberflaeche-skizzen.md` · `docs/design/2026-10-26-leinwand/` (`canvas.json`,
`Main.dc.html`, `Pruefen-Liste.dc.html`, `Pruefen-Arbeitsflaeche.dc.html`, `Handy-Uebersicht.dc.html`,
`Handy-Pruefen.dc.html`, `Handy-Freigaben.dc.html`, `Handy-Mehr.dc.html`, `Assistent-Steuern.dc.html`,
`Einstellungen-Firma.dc.html`, `Bausteine.dc.html`, `README.md`) · Tests: `tests/design_hilfe.py`,
`test_design_token.py`, `test_symbole.py`, `test_auth_vorlieben.py`, `test_komponenten.py`,
`test_api_muster.py`, `test_api_navigation.py`, `test_api_geruest.py`, `test_api_konto.py`,
`test_api_hilfe.py`, `test_api_fehlerseiten.py`, `test_api_bestand_design.py`,
`test_api_lesezugriff.py`, `test_api_vollstaendigkeit.py`, `test_api_vorlagen.py`,
`test_migration_regeln.py`, `test_abhaengigkeiten.py`, `test_spec_rueckverfolgung.py`,
`browserprobe_welt.py`, `test_browserprobe_welt.py`.

**Geändert:** `src/accounti/api/registry.py` (Bereich, Navigationspunkt), `api/vorlagen.py`
(`async seite` mit `zaehler` und `teil`, Gerüst-Kontext, `symbol_url`, `fehlerseite_500`),
`api/app.py` (Fehlerseiten mit `zaehler=False`, htmx-Fragmente, 404 mit Gerüst, Lesezugriff in
der `lebenszeit`), `api/sicherheit.py` (500 als Designseite), `api/sitzung.py`
(`vielleicht_angemeldet`, `verweigert`, `Verweigerung`), `api/dienste.py` (nur `PFLICHTSPALTEN`
und die Meldung von `pruefe_schema`; `_fabrik` bleibt unverändert), `db/__init__.py` (`SCHEMA_STAND`), `api/seiten/*.py`
(`await seite`, Navigationspunkte; `freigaben.py` Recht der Navigation; `pruefen.py` `verweigert`;
`gesellschaft.py` + GET; `anmeldung.py` Codefeld-Variante) · `api/vorlagen/basis.html` (neu
geschrieben), `anmelden.html`, `start.html`, `freigaben.html`, `meldung.html`, `_makros.html`,
`pruefen/*.html`, `buchungen/buchung.html`, `belege/beleg.html`, `belege/_vorschau.html` ·
`api/statisch/accounti.css` (neu geschrieben), `pruefen.js` (ohne Fehlerhinweis und
`localStorage`, Strg+Enter über `data-hauptknopf`), bis Schritt 12 `pruefen.css` (in
`@layer bestand`) · `models/auth.py` (Vorlieben), `db/tabellen_auth.py`, `db/repo_auth.py`,
`auth/dienst.py` (`setze_vorlieben`, `Vorlieben`; `setze_sprache` entfällt) ·
`buchung/pruefschlange.py` (`anzahl_offen`), `db/repo_zahlung.py` (`anzahl_laeufe`) ·
`i18n/en.yaml` · Tests (umgestellt, siehe B9, B10, B21 und die Schritte; `tests/test_db_upgrade.py`
um den Fall ohne Vermerk und die kopfrelativen Fälle auf `TOKEN`/`_vorher`, ist F gemergt auch
`test_migration_anlagen_buchung.py`) · `THIRD-PARTY.md`, `.gitignore`, `CONTRIBUTING.md`, `README.md`,
`CHANGELOG.md`, `docs/bauplan.md`, `docs/architektur.md`, `docs/betrieb.md`.

**Entfällt:** `src/accounti/api/statisch/pruefen.css`, `src/accounti/api/seiten/sprache.py` (Route
in `konto.py`).

---

## Spec und Akzeptanz → Schritt → Test

| Spec | Punkt | Schritt | Test |
|------|-------|---------|------|
| **A1** | Ziel-Gliederung, Einstellungen abgesetzt, Freigaben eigener Punkt | 6 | `test_api_navigation.py::test_bereiche_je_rolle_in_reihenfolge`, `::test_einstellungen_abgesetzt_nur_mit_verwalten` |
| **A2** | Registry mit Bereich, Symbol, Zähler; Bereich nur mit Seite und Recht; `aria-current`; Freigaben mit Freigaberecht, `/freigaben` mit `LESEN` | 6, 7 | `::test_bereich_ohne_seite_entfaellt`, `::test_freigaben_nur_mit_freigaberecht_seite_aber_lesbar`, `::test_zaehler_in_seitenleiste_und_unterer_leiste`, `::test_symbol_muss_im_sprite_stehen`, `test_api_geruest.py::test_untere_leiste_ziele` (`aria-current`) |
| **A3** | Seitenleiste ≥ 64rem, Kopfleiste mit Gesellschaft, Hilfe, Benutzermenü; 90rem/75ch | 7, 14 | `test_api_geruest.py::test_benutzermenue_breit_und_symbol_schmal`, `::test_kennfarbe_und_kuerzel_auf_jeder_seite`; Browserprobe AK44 |
| **A4** | Kopfleiste ≤ 56 px, untere Leiste ≤ 5 Ziele, `/menue`, `safe-area`, Fokus nicht verdeckt | 7, 8, 14 | `::test_untere_leiste_ziele`, `::test_safe_area_im_kopf_und_in_der_leiste`, `test_api_navigation.py::test_menue_ohne_js`; Browserprobe AK6, AK55 |
| **A5** | Kennfarbe und Kürzel auf jeder Seite, Titel, `/gesellschaft`, keine Doppelzeile, Kennfarbe per Klasse | 7, 8 | `test_api_geruest.py::test_titel_seite_gesellschaft_accounti`, `::test_keine_zeile_gesellschaft_im_inhalt`, `::test_kennfarbe_stabil_je_kuerzel`, `::test_kennfarben_ohne_dopplung_bis_sechs`, `::test_kennfarbe_gleich_fuer_alle_benutzer`, `::test_kennfarbe_und_kuerzel_auf_jeder_seite`, `::test_monogramm_aus_dem_namen`, `::test_monogramm_eindeutig_je_registry`, `::test_monogramm_gleich_fuer_alle_benutzer` (Fassung 4), `test_api_gesellschaften.py::test_gesellschaftsseite_nur_mit_rolle`, `::test_zaehler_je_gesellschaft`, `::test_haengende_gesellschaft_haelt_die_seite_nicht_auf`, `::test_fehlende_datenbankdatei_wird_nicht_angelegt`, `test_api_lesezugriff.py` (alle); umgestellt `::test_akzeptanz_5_wechsel_aendert_alle_ansichten` |
| **A6** | Benutzermenü (Mein Konto, Sprache, Darstellung, Hilfe, Abmelden); `<details>` breit, `/menue#konto` schmal; POST 303 | 7, 9 | `::test_benutzermenue_breit_und_symbol_schmal`, `test_api_konto.py::test_vorlieben_ohne_js_303_und_wirkung` (Abweichung „Auswahl genügt“: B12) |
| **A7** | genau ein `h1`, Brotkrumen | 7 | `test_api_geruest.py::test_genau_ein_h1`, `::test_brotkrumen_unterhalb_eines_bereichs` |
| **A8** | Hilfe je Bereich, Link an derselben Stelle, keine externen Links | 10, 7 | `test_api_hilfe.py::test_jeder_bereich_hat_eine_hilfeseite`, `::test_fehlende_hilfe_wird_gemeldet`, `::test_unbekanntes_thema_404`, `::test_keine_links_auf_fremde_hosts`, `::test_begriffe_aus_anhang_b`, `test_api_geruest.py::test_hilfe_link_gleiche_stelle` |
| **A9** | 403/404/409/500 im Design mit Weg zurück; 403 nennt Rolle; 500 ohne Einzelheiten | 11 | `test_api_fehlerseiten.py::test_403_nennt_recht_und_rollen`, `::test_403_api_json_mit_dem_satz`, `::test_404_im_design_mit_weg_zurueck`, `::test_404_bei_gesperrter_systemdatenbank_schlicht`, `::test_409_im_design`, `::test_500_ohne_einzelheiten`, `::test_500_fragt_keine_datenbank`, `::test_sicherheit_ist_die_aeusserste_middleware`, `::test_ausnahme_in_innerer_middleware_gibt_designseite` |
| **A87** (P1-Teil) | `/konto`, `POST /konto/vorlieben`: Sprache, Darstellung, Fachansicht, Beträge verbergen, Tastenkürzel; Skript liest `data-`Attribut; 308 vom alten Pfad | 3, 9 | `test_auth_vorlieben.py::test_nur_gesetzte_felder_aendern_sich`, `::test_speichern_ueberschreibt_vorlieben_nicht`, `test_api_konto.py::test_teilformular_aendert_nur_gesendete_felder`, `::test_alter_sprachpfad_308_und_wirkt`, `::test_tastenkuerzel_als_data_attribut`, `test_api_statisch.py::test_skripte_ohne_speicher` |
| **A88** (P1-Teil) | `setze_vorlieben` ersetzt `setze_sprache` | 3 | `test_auth_vorlieben.py` (alle) |
| **A89** | Farb-Token hell/dunkel/auto, `color-scheme` (Werte = Leinwand, L1) | 0, 1 | `test_design_token.py::test_kontrast_hell`, `::test_kontrast_dunkel`, `::test_token_wie_leinwand`, `::test_themenklassen_in_den_tokenbloecken`, `test_spec_rueckverfolgung.py::test_leinwand_abgelegt`, `test_design_token.py::test_dunkel_zweimal_gleich`, `::test_color_scheme_je_wahl`, `::test_jedes_token_in_beiden_modi`, `::test_farben_nur_ueber_token`, `::test_jeder_tokenverweis_definiert` |
| **A90** | Systemschrift, Größen (Skala L2), `tabular-nums`, Gewichte 400/600 | 1, 4, 14 | `::test_nur_gewichte_400_und_600`, `::test_schriftgroessen_nur_aus_der_skala`, `test_komponenten.py::test_betrag_vorzeichen_und_richtung_als_text`; Browserprobe AK50 und Maßprobe (L10) |
| **A91** | 4-px-Raster (mit Zwischen- und Feinstufen, L3), Radien, ein Schatten, Breakpoints, vier Layouts | 1, 4, 7, 14 | `::test_nur_drei_breakpoints`, `::test_abstaende_und_radien_aus_token`, `test_api_geruest.py::test_masse_des_geruests`, `test_api_muster.py::test_zustaende_gezeigt` (Layouts auf `/muster`); Maßprobe (L10) |
| **A92** | Komponenten als Makros mit Zuständen (Aussehen L4) | 4, 5, 14 | `test_komponenten.py` (alle), `test_api_muster.py::test_jedes_makro_auf_der_musterseite`; Maßprobe und Bildvergleich (L10) |
| **A93** | Tabellen: ruhig, fixierter Kopf, `aria-sort`, Dichten, Karten unter 40rem, `caption` | 4, 12, 14 | `test_komponenten.py::test_tabelle_caption_pflicht_und_rollen`, `::test_spaltenkopf_aria_sort`, `test_api_bestand_design.py::test_jede_tabelle_mit_caption_und_rollen`; Browserprobe AK52 |
| **A94** | Formulare: Label oben, Hilfe/Fehler mit `aria-describedby`, Breiten, `autocomplete`, kein Platzhalter als Label | 4, 12 | `test_komponenten.py::test_feld_label_hilfe_fehler_aria`, `test_api_bestand_design.py::test_jedes_sichtbare_feld_mit_label_for` |
| **A95** | Hinweise mit Symbol und Wort, Rollen nur für neue Meldungen, leere Zustände | 4, 12 | `test_komponenten.py::test_hinweis_rolle_nur_wenn_neu`, `::test_hinweis_mit_symbol_und_wort`, `::test_leer_mit_satz_nebensatz_und_link_ohne_rolle`, `test_api_bestand_design.py::test_jede_liste_mit_leerem_zustand` |
| **A96** | Sprite aus Lucide-Teilmenge (36 nach L6), Lizenz, `aria-hidden`/`aria-label` | 2, 14 | `test_symbole.py` (alle, auch `::test_symbole_wie_leinwand`); Browserprobe AK50 |
| **A97** | Druck | 1, 7, 14 | `test_api_geruest.py::test_druckkopf`; Browserprobe AK8 |
| **A98** | CSP: kein `style=`, kein Inline-Skript, keine `on…`, `?v=` | 2, 13, 14 | `test_api_statisch.py::test_keine_inline_skripte_stile_oder_ereignisattribute` (erweitert), `::test_eigene_dateien_mit_versionsanhang`; Browserprobe AK5 |
| **A99** | kein CDN, Budgets, ohne JS bedienbar | 1, 2, 9, 13 | `test_design_token.py::test_css_budget`, `test_symbole.py::test_sprite_budget_und_ids`, `test_api_statisch.py::test_skripte_budget`, `test_abhaengigkeiten.py::test_keine_url_auf_fremde_hosts`, `test_api_vollstaendigkeit.py::test_htmx_formen_wirken` (ohne `HX-Request`) |
| **A100** | Übergänge ≤ 150 ms, nur Farbe/Deckkraft, `prefers-reduced-motion` | 1, 14 | `::test_uebergaenge_kurz_nur_farbe_und_deckkraft`, `::test_reduzierte_bewegung_ohne_uebergang`; Browserprobe AK50 |
| **A101** | Musterseite, angemeldet, `LESEN`, nicht in der Navigation, erfundene Daten, `?theme=`; Nachbildung der Zeichenfläche „Bausteine“ (L9) | 4, 5, 14 | `test_api_muster.py` (alle, auch `::test_ohne_parameter_hell_und_dunkel_nebeneinander`, `::test_theme_parameter_zeigt_einen_rahmen`, `::test_ids_eindeutig_trotz_zwei_rahmen`); Browserprobe AK2 auf `/muster`; Bildvergleich mit `Bausteine` (L10) |
| **A102** | Ziel WCAG 2.2 AA | 14 | Browserprobe AK2; Handprotokoll AK43 |
| **A103** | Kontrasttest aus den Token | 1 | `test_design_token.py::test_kontrast_hell`, `::test_kontrast_dunkel` |
| **A104** | Fokusring 2 px mit Abstand (Auslegung: 3 px wie die Leinwand), nicht verdeckt, Fokus nach Austausch | 1, 4, 9, 14 | `::test_fokusring_3px_mit_2px_abstand`, `test_api_muster.py::test_beispielfragment_mit_data_fokus`; Browserprobe AK55 und Fokus nach dem Austausch über `/muster/beispiel` |
| **A105** | Tastatur ohne Falle, Sprunglink zuerst, Kürzel abschaltbar | 7, 9, 14 | `test_api_geruest.py::test_sprunglink_ist_erstes_ziel`, `test_api_konto.py::test_tastenkuerzel_als_data_attribut`, `test_api_statisch.py::test_tasten_in_markup_und_skript_gleich` (umgestellt, Strg+Enter über `data-hauptknopf`); Browserprobe AK45, AK55; AK43 |
| **A106** | Ziele 24/44 px, kein Ziehen | 1, 14 | Browserprobe AK55 |
| **A107** | 320 px ohne waagrechtes Scrollen, 200 % Zoom, Textabstände | 1, 12, 14 | Browserprobe AK1, AK56 |
| **A108** | Fehlerliste oben, Fehler am Feld, Eingaben bleiben | 4, 12 | `test_komponenten.py::test_fehlerliste_alert_mit_links` (Zuordnung Feldname → id), `test_api_bestand_design.py::test_422_mit_fehlerliste_und_aria`, `::test_ids_je_seite_eindeutig`, `test_api_konto.py::test_ungueltige_wahl_422_mit_fehlerliste` |
| **A109** | Anmeldung: Passwortmanager, Einfügen, ein Codefeld numerisch, Wiederherstellungscode ohne JS; ebenso alle Codefelder | 4, 12, 14 | `test_komponenten.py::test_codefeld_ein_feld_numerisch_und_variante`, `test_api_anmeldung.py::test_codefeld_numerisch_mit_wiederherstellungsweg`, `::test_anmeldung_mit_wiederherstellungscode_ohne_js`, `::test_wiederherstellungsweg_behaelt_weiter`, `test_api_bestand_design.py::test_code_parameter_je_seite`, `test_api_bestand_design.py::test_codefelder_mit_sichtbarem_label_und_ein_feld`; Browserprobe AK53 |
| **A110** | Statusbereich, `aria-busy` | 7, 9, 12, 14 | `test_api_geruest.py::test_statusbereich_role_status`, `test_api_pruefen.py::test_ergebnis_im_statusbereich`; Browserprobe AK54 |
| **A111** | Tabellen als Karten mit ausdrücklichen Rollen | 4, 12, 14 | `test_komponenten.py::test_tabelle_caption_pflicht_und_rollen`; Browserprobe AK52 |
| **A112** | `lang`, axe-core in der Browserprobe, Handdurchlauf | 5, 13, 14 | `test_api_geruest.py::test_lang_je_sprache_auf_jeder_seite`; Browserprobe AK2; AK43 |
| **A113** | Gleichlauf oder benannte Ausnahme | 0, 9, 13 | `test_api_vollstaendigkeit.py::test_jeder_post_hat_gleichlauf_oder_ausnahme` |
| **A114** | Rechte-Matrix, CSRF, Einmalcode | 4, 8, 9, 10, 13 | `test_api_rechte_matrix.py::test_jeder_endpunkt_steht_in_der_matrix`, `::test_jede_rolle_gegen_jeden_endpunkt`, `test_api_csrf.py::test_jeder_post_ohne_csrf_403_und_nichts_geaendert` |
| **A115** | htmx-Konfiguration unverändert, eine Route – zwei Formen, Fehlerfragmente | 0, 4, 8–11, 13 | `test_api_statisch.py::test_htmx_konfiguration` (Schutz), `test_api_muster.py::test_fragment_mit_hx_request`, `test_api_vorlagen.py::test_teil_verlangt_nur_bloecke_auf_oberster_ebene`, `test_api_vollstaendigkeit.py::test_jede_route_hat_eine_htmx_form`, `::test_htmx_formen_wirken`, `test_api_fehlerseiten.py::test_htmx_fehler_als_fragment` |
| **A116** | Protokoll ohne Personenbezug | 13 | `test_betrieb_protokoll.py::test_geruest_ohne_personenbezug` |
| **A117** | keine neue Python-Abhängigkeit in P1; Symbole als Dateien mit Lizenz | 2, 13 | `test_abhaengigkeiten.py::test_pyproject_ohne_neue_abhaengigkeit`, `::test_lizenzen_beigelegt`, `::test_browserprobe_versionen_fest` |
| **A118** | eine Migration, beide Datenbankarten, ein Kopf, Schemaprüfung | 3, 15 | `test_migration_web.py::test_upgrade_ergaenzt_vorlieben_in_bestehender_tabelle`, `::test_ein_kopf_nach_ddc9a184ddb4` (umgestellt, ohne Kopfannahme), `::test_postgresql_rundlauf`, `test_migration_regeln.py::test_kein_migrationstest_haengt_am_kopf`, `test_api_schema.py::test_start_ohne_vorlieben_bricht_mit_hinweis_ab`, `test_db_upgrade.py::test_schema_stand_ist_der_kopf_der_migrationen` (Schutz), `::test_stand_ohne_vermerk_mit_sprache_ohne_vorlieben` |
| **A119** | alle neuen Texte übersetzt, Begriffe aus Anhang B | 13 | `test_i18n_katalog.py::test_jeder_text_hat_eine_uebersetzung` (Schutz, wird rot bei jedem neuen Text), `::test_begriffe_aus_anhang_b_im_katalog` |
| **A121** | bestehende Seiten im neuen Design, I1/I8–I12 behoben, Tests umgestellt statt gelöscht | 1, 12, 7, 14 | `test_api_bestand_design.py` (alle), `test_design_token.py::test_jede_regel_in_einer_ebene`, `::test_ebenenfolge_wie_entschieden`, umgestellte Tests (B9), Browserprobe AK1, AK4, AK49 |
| **AK1** | 320/390 px ohne waagrechtes Scrollen, jede Seite, jede Rolle | 14 | Browserprobe |
| **AK2** | axe 0 Verstöße A/AA, hell/dunkel, 1440/390 | 14 | Browserprobe |
| **AK3** | Token-Kontrasttest | 1 | `test_design_token.py::test_kontrast_hell`, `::test_kontrast_dunkel` (mit den Paaren aus L1) |
| **AK4** | Dunkelmodus: Bedienelemente nicht weiß, `kbd` ≥ 4,5 | 1, 14 | `::test_formularelemente_aus_token`; Browserprobe |
| **AK5** | Vorlagen-Test ohne Inline-Code, keine CSP-Meldung | 13, 14 | `test_api_statisch.py::test_keine_inline_skripte_stile_oder_ereignisattribute`; Browserprobe |
| **AK6** | untere Leiste ≤ 5, `aria-current`, Freigaben nur mit Recht, Kopf ≤ 56 px, `/menue` ohne JS | 7, 8, 14 | `test_api_geruest.py::test_untere_leiste_ziele`, `test_api_navigation.py::test_menue_ohne_js`; Browserprobe |
| **AK7** | Wechsel über `/gesellschaft`, Akzeptanz 5, `marke-n`, Titelmuster | 7, 8 | `test_api_gesellschaften.py::test_akzeptanz_5_wechsel_aendert_alle_ansichten` (umgestellt), `test_api_geruest.py::test_titel_seite_gesellschaft_accounti`, `::test_kennfarbe_und_kuerzel_auf_jeder_seite` |
| **AK8** | Druck ohne Navigation und Knöpfe | 14 | Browserprobe (`emulateMedia({media: "print"})`) |
| **AK43** | Handdurchlauf Tastatur, NVDA + Firefox, VoiceOver iOS | 14 | Handprotokoll im PR (NVDA und VoiceOver beim Nutzer) |
| **AK44** | Registry je Rolle, Reihenfolge, Einstellungen/Freigaben nur mit Recht; Seitenleiste/untere Leiste je Breite; ≤ 90rem | 6, 14 | `test_api_navigation.py::test_bereiche_je_rolle_in_reihenfolge`; Browserprobe |
| **AK45** | Darstellung in neuem Kontext, auto folgt Emulation, Vorlieben ohne JS, 308, Tastenkürzel aus, kein `localStorage` | 9, 14 | `test_api_konto.py::test_vorlieben_ohne_js_303_und_wirkung`, `::test_alter_sprachpfad_308_und_wirkt`, `test_api_statisch.py::test_skripte_ohne_speicher`; Browserprobe |
| **AK46** | ein `h1`, Brotkrumen mit übersetztem `aria-label` | 7 | `test_api_geruest.py::test_genau_ein_h1`, `::test_brotkrumen_unterhalb_eines_bereichs` |
| **AK47** | Hilfe-Link gleiche Stelle (Auslegung: gleicher Index je Benutzer auf den Seiten im Gerüst, gleiche relative Reihenfolge überall, auch auf der schlichten 500), `/hilfe/<bereich>` 200 ohne fremde Hosts | 7, 10 | `test_api_geruest.py::test_hilfe_link_gleiche_stelle`, `test_api_hilfe.py::test_jeder_bereich_hat_eine_hilfeseite`, `::test_keine_links_auf_fremde_hosts` |
| **AK48** | 403/404/409/500 im Design, 403 mit Rolle, 500 ohne Einzelheiten | 11 | `test_api_fehlerseiten.py` (alle) |
| **AK49** | alte Tests grün, umgestellte im PR; Label am Codefeld, Angaben überlappen nicht, Hauptaktion primär | 12, 14, 15 | ganze Testsuite; Abgleich `pytest --collect-only` zwischen `main` und Branch (Schritt 15); `test_api_bestand_design.py::test_codefelder_mit_sichtbarem_label_und_ein_feld`, `::test_hauptaktion_ist_primaerknopf`; Browserprobe (Bounding-Boxen) |
| **AK50** | Budgets, keine Fremdhosts, Gewichte, Lizenz; `tabular-nums`, reduzierte Bewegung, Symbol-Beschriftung | 1, 2, 9, 13, 14 | `test_design_token.py::test_css_budget`, `test_api_statisch.py::test_skripte_budget`, `test_symbole.py::test_sprite_budget_und_ids`, `test_abhaengigkeiten.py::test_keine_url_auf_fremde_hosts`, `test_design_token.py::test_nur_gewichte_400_und_600`, `test_symbole.py::test_lizenz_isc_und_mit_beigelegt`; Browserprobe |
| **AK51** | jedes Makro auf `/muster` in seinen Zuständen; `/muster` mit Anmeldung, axe-frei | 4, 14 | `test_api_muster.py::test_jedes_makro_auf_der_musterseite`, `::test_zustaende_gezeigt`, `::test_verlangt_anmeldung_und_steht_nicht_in_der_navigation`, `::test_ohne_parameter_hell_und_dunkel_nebeneinander`; Browserprobe AK2 |
| **AK52** | `caption`, `aria-sort`, Rollen in Kartenform, ARIA-Schnappschuss | 4, 12, 14 | `test_komponenten.py::test_tabelle_caption_pflicht_und_rollen`, `::test_spaltenkopf_aria_sort`, `test_api_bestand_design.py::test_jede_tabelle_mit_caption_und_rollen`; Browserprobe |
| **AK53** | Label für jedes Feld, 422 mit Fehlerliste und ARIA, Eingaben bleiben, Codefeld einzeln, Einfügen, Wiederherstellungscode ohne JS | 4, 9, 12, 14 | `test_api_bestand_design.py::test_jedes_sichtbare_feld_mit_label_for`, `::test_422_mit_fehlerliste_und_aria`, `::test_codefelder_mit_sichtbarem_label_und_ein_feld`, `::test_ids_je_seite_eindeutig`, `test_api_anmeldung.py::test_anmeldung_mit_wiederherstellungscode_ohne_js`, `::test_wiederherstellungsweg_behaelt_weiter`; Browserprobe |
| **AK54** | leere Zustände mit Link; Statusbereich nach htmx-Freigabe, `aria-busy` | 12, 14 | `test_api_bestand_design.py::test_jede_liste_mit_leerem_zustand`, `test_api_pruefen.py::test_ergebnis_im_statusbereich`; Browserprobe |
| **AK55** | Fokus nicht verdeckt, Ring ≥ 2 px, Sprunglink zuerst, keine Falle, Ziele 24/44 px (Auslegung: `/konto` statt einer Einstellungsseite) | 1, 7, 14 | `test_design_token.py::test_fokusring_3px_mit_2px_abstand`, `test_api_geruest.py::test_sprunglink_ist_erstes_ziel`; Browserprobe (Ziele am `label`, L7 Nr. 20) |
| **AK56** | 200 % Zoom, Textabstände, nichts abgeschnitten | 14 | Browserprobe |
| **AK57** | `lang` je Sprache, Katalog vollständig, Begriffe Anhang B | 10, 13 | `test_api_geruest.py::test_lang_je_sprache_auf_jeder_seite`, `test_i18n_katalog.py::test_jeder_text_hat_eine_uebersetzung`, `::test_begriffe_aus_anhang_b_im_katalog` |
| **AK58** | Matrix vollständig, CSRF, `MIT_EINMALCODE`, Gleichlauf-Liste, htmx-Formen (neue Routen als Fragment), Fehlerfragmente | 0, 4, 8–11, 13 | `test_api_rechte_matrix.py`, `test_api_csrf.py`, `test_api_vollstaendigkeit.py` (alle), `test_api_muster.py::test_fragment_mit_hx_request` und die `…_fragment_mit_hx_request`-Tests der Schritte 8–10, `test_api_fehlerseiten.py::test_htmx_fehler_als_fragment` |
| **AK59** | Protokolltest über alle neuen Wege | 13 | `test_betrieb_protokoll.py::test_geruest_ohne_personenbezug` |
| **AK60** | `pyproject.toml` ohne neue Abhängigkeit (P1) | 13 | `test_abhaengigkeiten.py::test_pyproject_ohne_neue_abhaengigkeit` |
| **AK61** | Migration SQLite/PostgreSQL hinauf und hinunter, `serve` bricht ab (Hinweis `accounti db upgrade`, Gleichwert `alembic upgrade head`; Auslegung), ein Kopf | 3, 15 | `test_migration_web.py` (umgestellt und neu), `test_api_schema.py::test_start_ohne_vorlieben_bricht_mit_hinweis_ab`, `test_db_upgrade.py` (Schutz, neu und umgestellt), `test_migration_regeln.py::test_kein_migrationstest_haengt_am_kopf`; ganze Suite mit `ACCOUNTI_TEST_PG` (Schritt 15) |
| Anhang D | Prüfskript „jede Anforderung in einem Kriterium“ | 0 | `test_spec_rueckverfolgung.py` (alle) |
| **Leinwand** (Fassung 4) | Aussehen wie die freigegebene Design-Leinwand; Abweichungen nur nach L7 | 0, 1, 2, 4, 5, 7, 12, 14 | `test_spec_rueckverfolgung.py::test_leinwand_abgelegt`, `test_design_token.py::test_token_wie_leinwand`, `test_symbole.py::test_symbole_wie_leinwand`, `test_api_muster.py::test_ohne_parameter_hell_und_dunkel_nebeneinander`, `test_api_navigation.py::test_menue_gruppen_wie_leinwand`; Maßprobe und Bildvergleich (L10); Handprüfung der Optik durch den Nutzer |

---

## Sicherheit

**CSP bleibt wörtlich.** Kein neues `style=`, kein Inline-Skript, keine `on…`-Attribute, kein
`javascript:`, kein `<style>`; die Kennfarbe wirkt über Klassen. Das Sprite ist eine Datei der
eigenen Herkunft (`default-src 'self'` deckt `<use href>`), ohne Skript, ohne Verweise. Der
Vorlagen-Scan nimmt jede neue Vorlage und die gerenderten neuen Seiten mit; die Browserprobe
prüft die Konsole ohne `bypassCSP`. htmx-Konfiguration unverändert.

**Rechte.** Jede neue Route steht in der Rechte-Matrix; der Vollständigkeitstest scheitert an
einer fehlenden. `/muster` braucht `LESEN` und zeigt nur Konstanten aus dem Modul. `/hilfe` ist
ohne Anmeldung erreichbar und enthält keine Daten der Gesellschaft (Test). `/gesellschaft` und
`/menue` zeigen nur Gesellschaften mit Rolle; Zähler einer Gesellschaft nur mit dem Recht des
Zählers dort (Freigaben nur mit Freigaberecht). Zähler lesen über den Lesezugriff: nur lesend,
ohne `init_db`, mit Fristen – eine fehlende oder hängende Datenbank einer Gesellschaft hält
weder die Seite noch andere Benutzer auf und wird nicht angelegt. Der Wechsel bleibt der POST aus 10a mit CSRF und
Rollenprüfung. Navigation ist nie die Rechteprüfung: `/freigaben` bleibt für `LESEN` lesbar,
die Freigabe-POSTs verlangen weiter Rolle und frischen Einmalcode.

**CSRF.** `POST /konto/vorlieben` läuft durch `angemeldet()` wie jeder POST; der 308 vom alten
Pfad schickt Methode und Körper samt Token weiter, geprüft wird am Ziel erneut. `weiter` geht
durch `sicheres_ziel` (nur relative Pfade dieser Anwendung).

**Eingaben.** Vorlieben nur aus festen Wertelisten (422 sonst); `?theme=` auf `/muster` und
`?code=` auf den Seiten mit Codefeld kommen als `str` an und wirken nur mit bekannten Werten,
sonst werden sie ignoriert (keine Spiegelung in die Seite, kein 422 aus der Validierung);
`/hilfe/{thema}` kommt als `str` und wird auf das Enum abgebildet (404 sonst). Attribute aus
Seiten an Komponenten müssen in der Positivliste der Makros stehen, ihre Werte escapt
`xmlattr`; Symbolnamen laufen durch `symbol_url` (unbekannt → Fehler, nie in den Pfad
gespiegelt). Der Link „Wiederherstellungscode verwenden“ reicht `weiter` nur über
`sicheres_ziel` durch. Autoescape und `StrictUndefined` bleiben.

**Fehlerseiten.** Scheitert auf 404 oder Hilfe das Erkennen der Sitzung an der Datenbank, gilt
die Anfrage als nicht angemeldet (schlichtes Layout, keine Daten). 500 enthält weder Ausnahmetext
noch Traceback und fragt keine Datenbank; die Sicherheits-Middleware bleibt die äußerste (Test). Das
Protokoll nennt nur die Art (wie 10a). 403 nennt Recht und Rollen – das sind öffentliche
Bezeichnungen aus der Doku, keine Angaben über andere Personen.

**Protokoll.** Neue Routen haben nur feste Pfade bzw. das Thema als Pfadparameter; das
Zugriffsprotokoll schreibt weiterhin die Routenvorlage. Zählerfehler und Zeitüberschreitungen
schreiben nur die Art. Vorlieben schreiben kein Ereignis in `auth_ereignisse` (Ausnahme A113). Test mit
Markern in Anzeigename, Gesellschaftsname, 404-Pfad und 500-Ausnahme.

**Werkzeuge.** `scripts/browserprobe/` und `scripts/symbole.py` gehören nicht zum Abbild
(`Dockerfile` kopiert `src/`, `alembic/` und `alembic.ini`, nicht `scripts/`), `npm ci` mit
`ignore-scripts=true` und Lockdatei mit Integritätswerten; die Browser von Microsofts CDN sichert
die Lockdatei nicht ab (Download auf dem Server nur nach Freigabe, Schritt 5); Tarballs werden vor dem Entpacken geprüft und in eigenen leeren Ordnern
entpackt. `probe.json` mit Testpasswörtern und TOTP-Geheimnissen entsteht nur im Wegwerf-Ordner
der Welt und steht in `.gitignore`.

---

## Migration

- **Datei:** `alembic/versions/<rev>_add_benutzer_vorlieben.py`, `down_revision = K` = der eine
  Kopf von `main` beim Abzweigen (10b-1 und Paket A sind dann gemergt; voraussichtlich
  `e7153706b43a`, maßgeblich ist `alembic heads`). Im selben Commit `db.SCHEMA_STAND = "<rev>"`:
  `init_db` stempelt neue Datenbanken damit, `sicherung wiederherstellen` vermerkt ihn im Ziel,
  `test_db_upgrade.py` verlangt `get_heads() == [SCHEMA_STAND]`. Vor dem Merge neu lesen; wurde
  P4 oder ein Gesamttest-Branch vorher gemergt, `down_revision` auf dessen Kopf setzen und
  `SCHEMA_STAND` mitziehen (der Konflikt in der Zeile `SCHEMA_STAND = …` erzwingt das ohnehin).
  Die Tests führen nur die eigene Revision fest (`VORLIEBEN`), lesen `VOR` als deren
  `down_revision` und setzen keinen bestimmten Kopf voraus – sie bleiben gültig, wenn P1 neu
  gekettet wird **und** wenn spätere Pakete auf `<rev>` ketten; „genau ein Kopf“ prüft allein
  `test_schema_stand_ist_der_kopf_der_migrationen`. Nach dem Merge zeigt `alembic heads` genau
  einen Kopf (A118, AK61).
- **Inhalt:** `auth_benutzer` bekommt `darstellung VARCHAR(6) NOT NULL DEFAULT 'auto'`,
  `fachansicht BOOLEAN NOT NULL DEFAULT false`, `betraege_verbergen BOOLEAN NOT NULL DEFAULT
  false`, `tastenkuerzel BOOLEAN NOT NULL DEFAULT true` – jede nur, wenn sie fehlt
  (wiederholbar, wie `e7153706b43a`); SQLite über `batch_alter_table`. Downgrade entfernt die
  vier Spalten.
- **Wo:** `auth_benutzer` liegt wegen der gemeinsamen Metadaten in **jeder** Datenbank – die
  Migration läuft gegen die Systemdatenbank **und** jede Gesellschaftsdatenbank, die
  Systemdatenbank zuerst (ohne die Spalten startet `serve` nicht). `docs/betrieb.md` nennt
  `accounti db upgrade` (Paket A): mit Vermerk gleich `alembic upgrade head`, ohne Vermerk leitet
  es den Stand aus dem Schema ab (Test in Schritt 3).
- **Start:** `Dienste.pruefe_schema()` verlangt die vier Spalten (`PFLICHTSPALTEN`); fehlen sie,
  bricht `serve` mit Exit 2 ab, ohne URL; die Meldung nennt alle fehlenden Spalten und
  `accounti db upgrade` (bei Datenbanken mit Vermerk gleich `alembic upgrade head`, das sie
  ebenfalls nennt; B22).
- **Bestand:** bestehende Benutzer erhalten die Standardwerte (automatisch, aus, aus, an) –
  Verhalten unverändert, nur die Tastenkürzel-Abschaltung aus `localStorage` geht verloren
  (einmal unter „Mein Konto“ neu setzen; steht im CHANGELOG).
- **Sicherung:** generisch über die Metadaten; eine Sicherung von vor der Migration lässt sich
  einspielen: das Ziel legt `init_db` nach dem neuen Code an und vermerkt `<rev>` (Paket A), die
  Standardwerte füllen die Spalten.
- **Index:** nur falls die Messung in Schritt 6 es verlangt, legt dieselbe Migration
  `ix_buchungssaetze_status` an (je Spalte bzw. Index nur, wenn er fehlt).

---

## Grenzen

**Gerüst und Navigation**
- Vor P3 hat „Belege“ keine eigene Seite und erscheint nicht; die untere Leiste hat als
  buchhalter drei Ziele (Übersicht, Prüfen, Mehr), als freigeber vier. „Steuern“ kommt mit P2,
  „Auswertungen“ mit 10b-2, „Einstellungen“ mit P5.
- Der Zähler „Freigaben“ zählt in P1 nur Zahlungsläufe im Entwurf; USt-VA kommen mit P2 (A126).
  Der Zähler „Prüfen“ zählt offene Vorschläge ohne zurückgestellte, nicht die Belege zur Prüfung.
- Die Kennfarbe ist bis P5 aus dem Kürzel abgeleitet; ab sieben Gesellschaften wiederholen sich
  Farben (das Kürzel unterscheidet weiter). Kommt eine Gesellschaft in die Registry oder fällt
  sie weg, kann eine Gesellschaft, deren Farbe durch Ausweichen entstand, umgefärbt werden; alle
  Benutzer sehen aber stets dieselbe Farbe. Fest wird sie mit der Wahl in P5.
- Die Zähler fehlen, solange die Datenbank nicht innerhalb der Frist antwortet (3 s); auf
  Fehlerseiten gibt es keine Zähler. Ein hängender Zähler belegt bis zum Zeitlimit seiner
  Verbindung einen der acht Plätze im Pool des Lesezugriffs; sind alle belegt, fehlen die Zähler
  auch anderer Seiten bis zur Frist.
- Ist die Systemdatenbank gesperrt, erscheinen 404 und Hilfe ohne Navigation (wie ohne
  Anmeldung); die übrigen Seiten antworten wie bisher mit 503.
- Das Benutzermenü schließt ohne JavaScript nur über seine Zusammenfassung.
- Browser ohne `@layer` (Safari vor 15.4) zeigen die Seiten ohne Stile; bedienbar bleiben sie.
- Fachansicht und „Beträge verbergen“ sind gespeichert, wirken aber erst mit P3 bzw. P2.
- Kein CLI-Befehl für die Vorlieben (Ausnahme A113). Die Darstellung gilt erst nach der
  Anmeldung; davor „automatisch“.
- `POST /einstellungen/sprache` bleibt ein Release als 308 erhalten.

**Design und Barrierefreiheit**
- Hover, Fokus und Aktiv-Zustände zeigt `/muster` statisch nicht; die Browserprobe prüft sie
  mit `hover()`/`focus()` und Bildschirmfotos.
- Die Tabellen der bestehenden Seiten werden unter 40rem zu Karten; breite Tabellen späterer
  Auswertungen scrollen in ihrem Rahmen (erlaubt nach WCAG 1.4.10 für Datentabellen).
- Ältere Browser lesen das `data-label` der Kartenansicht doppelt vor (Alternativtext für
  erzeugten Inhalt fehlt dort).
- Automatisch geprüft sind axe-Regeln, Messungen der Probe und die Servertests; NVDA, VoiceOver
  und die Firefox-Probe macht der Nutzer (keine Windows-/iOS-Umgebung und kein Firefox auf dem
  Server). Ohne dieses Protokoll ist AK43 offen.
- Die englischen Texte hat niemand mit englischer Muttersprache durchgesehen (wie 10b).
- „Wiederherstellungscode verwenden“ lädt die Seite neu (ohne JS geht es nicht anders): Benutzer
  und Passwort bzw. auf `/buchungen/{id}` Grund und Datum sind danach neu einzugeben; das Ziel
  `weiter` bleibt. Für Passwort und Code greift die Ausnahme in WCAG 3.3.7 (sicherheitsrelevante
  Angaben); der Passwortmanager füllt die Anmeldung erneut. Der Link steht vor dem Feld, damit
  die Wahl vor dem Tippen fällt.

**Treue zur Leinwand (Fassung 4)**
- Die Optik folgt der Leinwand bis auf die Abweichungen in L7. Layout-Abstände liegen bis zu 2 px
  neben der Leinwand (Rundung auf das 4-px-Raster, L3), die Zwischengrößen der Handy-Schrift sind
  gerundet (15/17/19/26 → 16/18/20/28 px, L2), der Fokusring ist 3 px.
- Die Kennfarben der Leinwand liegen nahe an den Statusfarben (dunkel ist `marke-2` gleich
  `--info`). Unterscheidbar bleiben sie durch das Monogramm und durch Wort und Symbol des Status.
  Die sechste Farbe (Oliv) stammt nicht aus der Leinwand.
- Das Monogramm entsteht aus dem Namen. Bei ähnlichen Namen weicht es auf das Registry-Kürzel oder
  auf Buchstabe + Ziffer aus und kann dann fremd wirken; eine Wahl kann P5 bringen. Kommt eine
  Gesellschaft hinzu, kann sich das Monogramm einer anderen ändern (wie bei der Kennfarbe).
- `:has()` fehlt in Firefox vor 121: Optionskarte und Wahlpille zeigen die Auswahl dort nur am
  Optionsfeld, nicht am Rahmen. `overflow: clip` fehlt in Safari vor 16: Dort klebt der
  Tabellenkopf nicht.
- Die Referenzbilder der Leinwand zeigen bei `sc-if` alle Zustände untereinander (Arbeitsfläche,
  Handy-Prüfen); verglichen wird der jeweils passende Abschnitt.
- Die Leinwand zeichnet das aufgeklappte Benutzermenü, Brotkrumen außerhalb der Einstellungen,
  Seitenblättern, Fehlerliste, Fehlerseiten, Anmeldung, `/konto`, `/gesellschaft` und die Hilfe
  nicht. Ihr Aussehen ist aus Token und Mustern abgeleitet (L4, L8); der Nutzer sieht es zuerst
  im Bildvergleich.

**Bestehende Seiten**
- Neues Aussehen, alte Bedienung: Die Arbeitsfläche zeigt bis P3 weiter Soll, Haben,
  Steuerschlüssel, Regel-Haken und Rückfrage gleichzeitig (I2–I5 bleiben bis P3, R10). Sie bleibt
  im Gerüst; den Fokusmodus der Leinwand ohne Seitenleiste entscheidet P3 (L7 Nr. 19).
- Die Wörter der Leinwand nach Anhang B („Später klären“, „Sicherheit: mittel“, „Passt –
  freigeben“) kommen erst mit P3; bis dahin tragen die Bestandsseiten ihre Wörter aus 10b-1 in der
  neuen Optik.
- `/freigaben` ist bis P2 nach Läufen gegliedert; Zeitraum der USt-VA weiter als Text, Werte
  erst nach der Freigabe sichtbar (A126 in P2).
- Die Übersicht zeigt bis P2 die vier Zahlen aus 10a/10b als Kennzahl-Karten; die sechs Karten
  der Leinwand („Heute zu tun“) baut P2.

**Werkzeuge**
- Die Browserprobe ist kein Teil von `pytest` und läuft nicht in der CI; sie braucht Node und
  einmal `npx playwright install` (lädt Browser von Microsofts CDN, nicht durch die Lockdatei
  abgesichert). Auf dem Server braucht Playwright 1.64.0 dafür einen Download nach Freigabe;
  sonst läuft die Probe mit 1.59.1 und dem vorhandenen Chromium 1217. Ergebnisse liegen im PR.
- Das Sprite wird nur mit `scripts/symbole.py` aus dem geprüften Tarball neu erzeugt; ein
  Wechsel der Lucide-Version ist eine bewusste Änderung mit neuer Prüfsumme.

---

## Risiken und Gegenmittel

| # | Risiko | Gegenmittel |
|---|--------|-------------|
| R-P1-1 | `async seite()` ändert alle 19 Aufrufe (zwei in synchronen Hilfsfunktionen, die mit `async` werden); ein vergessenes `await` liefert eine Coroutine statt einer Antwort | `mypy --strict` (Rückgabetyp), die Seitentests über alle GET-Routen, Umstellung in einem eigenen Schritt (6) vor dem Gerüst |
| R-P1-2 | Das Paket wird groß (Spec R8): Gerüst, Komponenten und alle bestehenden Seiten | Musterseite und Browserprobe zuerst (Schritte 4, 5), dann Seite für Seite (Schritt 12) mit Probe je Seite; keine neue Bedienung (R10 der Spec) |
| R-P1-3 | CSS-Budget 40 KB reicht für P2–P7 und 10b-2 nicht; die Komponenten der Leinwand sind reicher als in Fassung 3 (Aufklapper, Sammelleiste, Wahlpillen, Fortschritt, Themenklassen; geschätzt 28–32 KB) | eine Datei mit Ebenen, Komponenten statt Seitenregeln, Budgettest ab P1; Maße über Token statt Einzelwerten; Messung im PR (Ziel für P1: ≤ 30 KB ohne `bestand`, damit Raum bleibt); reicht es nicht, zuerst Seitenregeln in Komponenten zusammenlegen, nicht die Leinwand vereinfachen |
| R-P1-4 | Zusammenstöße mit parallelen Branches. **P4** (laut `plan-10c-p4-einstellungen.md:144–153`): Alembic-Kette und `SCHEMA_STAND`, `docs/betrieb.md`, `app.py` (ASGI-Middleware `Einstellungsstand`), `sitzung.angemeldet` (Aufruf `binde_gesellschaft` am Ende), `api/rest.api_zugang`, `dienste.py` (`quelle(kuerzel)`, Namen beim Start), `seiten/freigaben.py` (Vier-Augen-Meldung über `meldung.html`). **Paket A** (vor P1 gemergt): `db/__init__.py`, `db/repo_auth.py`, `db/tabellen_auth.py`, `models/auth.py`, `auth/dienst.py`, `alembic/env.py`, `betrieb/sicherung.py`. **10b-2** (Vorlagen) | `down_revision` und `SCHEMA_STAND` beim Merge neu lesen (A118), Test „genau ein Kopf“; P1 baut auf A auf, statt parallel dieselben Auth-Dateien zu ändern; in `dienste.py` nur `PFLICHTSPALTEN`, der Lesezugriff liegt in eigenem Modul; `vielleicht_angemeldet` nutzt denselben Kern wie `angemeldet`, damit P4s Bindung auch für Hilfe und 404 gilt; die Sicherheits-Middleware mit der 500-Seite bleibt die äußerste (P4s Middleware innen, damit ihre Fehler die schlichte 500-Seite bekommen; `test_sicherheit_ist_die_aeusserste_middleware` wird rot, wenn P4 sie nach `Sicherheit` einträgt – in Starlette wird die zuletzt eingetragene die äußerste); Migrationstests ohne Kopfannahme auf beiden Seiten (Wächtertest); `seiten/freigaben.py`: wer zuerst merged, der andere zieht die Meldung bzw. das neue Markup nach (P4s Meldung läuft dann über `meldung.html` mit der Komponente `hinweis`); 10b-2 beginnt erst nach P1 (Spec 9) |
| R-P1-5 | Zähler auf jeder Seite kosten Zeit oder brechen bei gesperrter Datenbank | zwei `COUNT` in einem Aufruf im eigenen Pool des Lesezugriffs (nur lesend, kurze Fristen, keine globale Sperre, Frist ohne Abhängigkeit von anyio), nur für ganze Seiten mit Status < 400, nie auf Fehlerseiten; Fehler und Zeitüberschreitung lassen nur den Zähler weg (Tests); Messung bei 50 000 Buchungen, notfalls Index |
| R-P1-6 | Die Browserprobe braucht Node, Playwright-Browser von Microsoft und Firefox beim Nutzer; ohne sie sind AK1, AK2, AK4 … nicht belegt. Für 1.64.0 fehlt auf dem Server das passende Chromium (1248) | feste Versionen mit Lockdatei, Anleitung und Bezugsquelle der Browser in `CONTRIBUTING.md` und `THIRD-PARTY.md`; Download auf dem Server nach Freigabe, sonst Rückfall 1.59.1 (Chromium 1217 vorhanden); Firefox-Lauf und Handprotokoll beim Nutzer als offener Punkt im PR |
| R-P1-7 | Abweichungen von der Spec (B12, B13) stoßen beim Nutzer auf Widerspruch | im PR mit Begründung (WCAG 3.2.2, 3.2.6) vorlegen; beide lassen sich ohne Umbau ändern (Knopf ausblenden, Symbol entfernen) |
| R-P1-8 | Das visuell versteckte `h1` auf dem Handy und der doppelte Titel in der Kopfleiste verwirren Screenreader | Kopftitel `aria-hidden`, `h1` bleibt im Baum; Probe mit VoiceOver (AK43) |
| R-P1-9 | Lucide-Lizenz falsch wiedergegeben (MIT-Teil für Feather-Symbole übersehen) | vollständige `LICENSE` beilegen, Test auf ISC- und MIT-Teil, `THIRD-PARTY.md` |
| R-P1-10 | Alte Browser ohne `@layer` zeigen keine Stile | dokumentierte Grenze; Seiten bleiben ohne Stile bedienbar (semantisches HTML, keine Logik in CSS) |
| R-P1-11 | P3 schreibt die Prüfseiten neu – Arbeit aus Schritt 12 geht verloren | in P1 nur mechanisch umstellen (Komponenten, Klassen, Codefeld, Fehlerliste), keine neue Struktur der Arbeitsfläche; die Optik der Leinwand liegt in den Komponenten, die P3 weiterverwendet |
| R-P1-12 | Umsetzung und Leinwand laufen auseinander: Werte werden aus dem Inline-Markup der Leinwand abgeschrieben statt aus L1–L4, spätere Pakete erfinden eigene Maße | Leinwand im Repository (Schritt 0), Token-Test gegen die Leinwand (`test_token_wie_leinwand`), Skala-, Abstands- und Radius-Tests, Maßprobe und Bildvergleich (L10) in jedem Paket mit Oberfläche; Abweichungen nur mit Eintrag in L7 bzw. in der Spec |
| R-P1-13 | Der Nutzer erwartet nach der Freigabe die Leinwand vollständig, P1 liefert aber nur Gerüst, Komponenten und die Optik der Bestandsseiten | L8 im PR und im README der Leinwand: was P1 zeigt und was P2/P3/P5/P7 bringen; die Gegenüberstellung sagt es je Bildpaar |

---

## Übergabe an die Folgepakete

| Paket | nutzt aus P1 | muss selbst |
|-------|--------------|-------------|
| P2 | `karte` (mit `status`, `anzahl`, `kennzahl`, `hauptaktion`), `.karte-liste`, `.seitenkopf`, `.etikett`, `layout-karten`, `zaehler`, `status`, `leer`, `aufklapper(art="karte")`, `marke(klein=True)`, `betrag`, Statusbereich, `gesellschaften_mit_zaehlern` mit Lesezugriff und Fristen (A17), `seite(…, teil="inhalt")`, `geruest.betraege_verbergen` (A18), Navigationspunkt „Steuern“ (`calendar`) | Hilfeseiten für Steuern (und ggf. Aufgaben); USt-VA in den Freigaben-Zähler; Freigaben-Karten (A126). **Leinwand:** Zeichenflächen „Main“ und „Handy-Uebersicht“ (sechs Karten „Heute zu tun“, „Erledigt“, andere Gesellschaften, Kennzahlen) und „Handy-Freigaben“ (Aufklapper, USt-VA-Karte); Status in der Fristenliste mit Symbol statt farbigem Etikett, „seit 25.10.“ mit Wort (L7 Nr. 11) |
| P3 | `optionskarte`, `reiter` (auch `geteilt`), `tabelle` (Karten, `zeile(gewaehlt)`), `sicherheit`, `betrag`, `sammelleiste`, `.haken-ziel`, Aktionsleiste über den Block `untere_leiste`, `data-fokus`, `aria-busy`, Ansagen per `hx-swap-oob` in `#status` (auf der Arbeitsfläche schon verdrahtet), `TASTEN_PRUEFEN`, `geruest.fachansicht` | Bereich „Belege“ mit Seite und Hilfe (`file-text`); Belege-Zähler; neue Tastenbedeutungen an einer Stelle. **Leinwand:** „Pruefen-Liste“ (Gruppen, Auswahl, Zeilenaktionen, Sammelleiste), „Pruefen-Arbeitsflaeche“ (drei Schritte, Tasten 1–3, „Künftig immer so?“), „Handy-Pruefen“ (geteilte Reiter, Aktionsleiste), Wörter nach Anhang B; **entscheidet den Fokusmodus** – Marke und Hilfe müssen bleiben (L7 Nr. 19); Handy-Reiter ohne `role="tab"` (L7 Nr. 3) |
| P5 | `layout-einstellungen`, `.unternavigation`, `brotkrumen`, `feld`, `auswahl`, `optionen`, `fehlerliste`, `tabelle(in_karte=True)`, `hinweis`, `codefeld`, `kennfarben(…, gewaehlt=…)`, `marken()` | Bereich „Einstellungen“ mit Seite und Hilfe (`settings`); Kennfarbe aus `mandant.kennfarbe` verdrahten. **Leinwand:** „Einstellungen-Firma“; die Wahl der Kennfarbe zeigt **sechs** Felder (`marke-1` … `-6`), versteckte Optionsfelder brauchen einen Fokusring am Feld (`label:has(:focus-visible)`); Spalte „Stand“ mit Symbol statt nur Farbe (L7 Nr. 11); auf Wunsch ein wählbares Monogramm (L7 Nr. 18) |
| P6 | Mein Konto (`/konto`), `codefeld`, `hinweis` | Sicherheitsteil von „Mein Konto“; `segno` in `test_pyproject_ohne_neue_abhaengigkeit` nachtragen |
| P7 | `schlicht.html`, `schritte` (mit `<progress>`), `.layout-formular`, `optionskarte`, `segment`, `feld(warnung=…, bestaetigt=…)`, `hinweis("info")`, Aktionsleiste | Hilfe für den Assistenten an derselben Stelle (AK47). **Leinwand:** „Assistent-Steuern“ (Kopf „accounti einrichten“ mit Marke, Schrittliste, Wahlpillen für die Umsatzsteuer, Prüfhinweise am Feld ohne `aria-invalid` bei Warnungen) |
| 10b-2 | alle Komponenten, `tabelle(kompakt=True)` im `.tabelle-rahmen`, Bereich „Auswertungen“ | Hilfeseite, Stile in `accounti.css` im Budget |
| alle | Browserprobe mit Bildvergleich und Maßprobe gegen die Leinwand (`leinwand.mjs`, `probe.mjs --vergleich`), Vollständigkeitslisten (`GLEICHLAUF`, `HTMX_FORMEN`), Rechte-Matrix, Kontrast-, Leinwand-, Skala-, Abstands- und Budgettests, Rückverfolgungstest, Wächtertest für Migrationstests, Prüfung der Vorlagen mit `teil`; L1–L8 als Quelle für das Aussehen | jede neue Route, jeder neue Text und jede neue Komponente in die jeweilige Liste bzw. auf `/muster`; Vorlagen mit `teil` importieren im Block `inhalt`; Migrationstests mit eigener Revision als Konstante und `_vorher()`, nie `downgrade -1` oder „ist Kopf“ |

---

## Offene Punkte (vor bzw. bei der Umsetzung)

1. **Alembic-Kopf und `SCHEMA_STAND`** beim Abzweigen und vor dem Merge lesen (Schritt 0,
   Schritt 15); die drei offenen Gesamttest-Migrationen (C, D, F) hängen an `ddc9a184ddb4` und
   werden beim Merge selbst neu gekettet. P1 setzt seine eigene `down_revision` und
   `SCHEMA_STAND` **und** stellt kopfrelative Tests um, die beim Abzweigen bzw. vor dem Merge auf
   `main` stehen (Schritt 3; sicher betroffen: Paket A, `test_db_upgrade.py`, sofern der Rebase von
   10b-1 sie nicht schon umgestellt hat; F, falls vor P1 gemergt).
2. **Voraussetzung Paket A:** erledigt – Paket A ist mit #32 auf `main` (87c6c8d). Offen bleibt
   nur 10b-1.
3. **`Dienste._fabrik`** hält beim Verbinden und bei `init_db` die globale Sperre und merkt sich
   keinen Fehlschlag (`dienste.py:61–67`). P1 umgeht das für alle Zähler mit dem Lesezugriff,
   ändert `_fabrik` aber nicht (Bestand aus 10a, betrifft jede Anfrage an die aktive
   Gesellschaft, P4 ändert dieselbe Datei). Vorschlag: eigene kleine Korrektur (Verbinden
   außerhalb der Sperre, `connect_timeout` für PostgreSQL), abgestimmt mit P4.
4. **Spec ablegen** – mit P4 abstimmen, wer zuerst merged; der andere übernimmt die Dateien.
   Ebenso die Reihenfolge der Middlewares (Sicherheit außen, P4s `Einstellungsstand` innen): der
   P4-Plan nennt sie nicht (`plan-10c-p4-einstellungen.md:160`, `:881`); dort nachtragen, dass
   `Einstellungsstand` **vor** `Sicherheit` eingetragen wird. P1 sichert das mit
   `test_sicherheit_ist_die_aeusserste_middleware`. Ebenso im P4-Plan nachtragen: dessen
   `test_ein_kopf` (`:734`, Kette `… → <kopf> → <rev>`) ohne Kopfannahme – eigene Revision als
   Konstante, `_vorher()`, „genau ein Kopf“ nur über `test_schema_stand_ist_der_kopf_der_migrationen`;
   sonst wird er rot, sobald P1 nach P4 auf dessen Revision kettet.
5. **Abweichungen** B12 (Absenden bei Auswahl) und B13 (Hilfe in der schmalen Kopfleiste) sowie
   die Auslegungen zu AK47, AK54 und AK55 dem Nutzer mit dem PR vorlegen und in der Spec
   nachtragen.
6. **Chromium-Download auf dem Server** (Playwright 1.64.0, Revision 1248) vor Schritt 5 vom
   Nutzer freigeben lassen; sonst Rückfall 1.59.1.
7. **Firefox-Probe, NVDA, VoiceOver** beim Nutzer (Schritt 14); bis dahin ist AK43 offen.
8. **Lucide-Version** beim Umsetzen nicht wechseln, außer mit Grund; eine neuere Version muss
   ebenfalls mindestens zwei Wochen alt sein und wird mit neuer Prüfsumme eingetragen.
9. **Sechste Kennfarbe** (Fassung 4): Die Leinwand zeigt fünf, A5 verlangt sechs; der Plan nimmt
   Oliv (`#5f6b1f` / `#b5c25a`, Kontraste in L1). Ist der Nutzer dagegen, ändert sich nur ein
   Tokenpaar. Nicht blockierend.
10. **Fokusmodus der Arbeitsfläche** (Fassung 4, für P3): Die Leinwand zeigt die Arbeitsfläche ohne
    Seitenleiste, Marke und Hilfe. Die Spec verlangt Marke und Hilfe auf jeder Seite (A5,
    A8/AK47), und die Aktionsleiste ersetzt nur die untere Leiste (A4). P1 lässt die Seite im
    Gerüst; ob P3 einen Fokusmodus mit schmalem Kopf (Marke, Position, Hilfe) baut, entscheidet
    der Nutzer mit P3 (L7 Nr. 19).
11. **Spec-Nachträge aus der Leinwand** (Fassung 4) mit dem PR in Abschnitt 12 der Spec eintragen:
    Schriftskala (A90), Zwischen- und Feinstufen der Abstände sowie Radien (A91), Kennfarben-Werte
    und Monogramm (A5/A89), zusätzliche Komponenten (A92), Fokusring 3 px als Auslegung (A104).
    Das sind Folgen der Freigabe, keine neuen Fragen.

---

## Doku-Bausteine

Fertige Texte zum Einarbeiten mit dem PR. Grundlage ist der Stand **nach** dem Merge von 10b-1
und Paket A (README, CHANGELOG, Bauplan, Architektur und Betrieb tragen dann die Texte aus
43031a7 und 87c6c8d; der Upgrade-Abschnitt in `docs/betrieb.md` nennt `accounti db upgrade`).
Beim Einarbeiten gegen den dann aktuellen Stand der Dateien abgleichen (Schritt 0).

### README.md

**Neue Zeile** in der Feature-Tabelle direkt nach `| ✅ | **Deutsch/Englisch** | … |`:

```markdown
| ✅ | **Oberfläche** | Eigenes ruhiges Design ohne fremde Server: hell, dunkel oder automatisch je Benutzer, Systemschrift, Symbole lokal; links eine Seitenleiste mit Zählern, auf dem Handy eine untere Leiste und die Seite „Mehr“; die aktive Gesellschaft mit Kennfarbe und Kürzel im Kopf; Hilfe je Bereich; „Mein Konto“ mit Sprache, Darstellung und Tastenkürzeln; Ziel WCAG 2.2 AA (Kontrast, Fokus, Tastatur, ohne JavaScript bedienbar) |
```

**Ersetzt** im Abschnitt „### Prüfen im Browser“ den Satzteil
`` `b` Beleg öffnen, `?` Hilfe (dort auch abschaltbar). `` durch:

```markdown
`b` Beleg öffnen, `?` Hilfe; abschalten lassen sich die Kürzel unter „Mein Konto“ (gilt auf jedem Gerät).
```

**Neuer Absatz** am Ende von „### Prüfen im Browser“:

```markdown
Die Oberfläche folgt einem Design-System mit Token für hell und dunkel; Vorlage ist eine
Design-Leinwand (`docs/design/2026-10-26-leinwand/`). Alle Bausteine stehen auf der Musterseite
`/muster` (angemeldet), hell und dunkel nebeneinander. Hilfe gibt es je Bereich unter `/hilfe`, auch ohne
Anmeldung. Auf dem Handy führt „Mehr“ (`/menue`) zu allen Bereichen, zum Wechsel der
Gesellschaft und zu „Mein Konto“.
```

**Ergänzt** in „### v0.5 — Oberfläche & Betrieb“ nach `- [x] DE/EN in der Oberfläche`:

```markdown
- [x] Design-System und Seitengerüst: hell/dunkel je Benutzer, Handy-Navigation, Hilfe je Bereich, Fehlerseiten (Baustein 10c, Paket 1)
- [ ] Übersicht „Heute zu tun“, neue Prüfschlange, Einstellungen und Einrichtung im Browser (Baustein 10c, Pakete 2–7)
```

### CHANGELOG.md

**Unter `## [Unreleased]` → `### Hinzugefügt`** oben einfügen:

```markdown
- **Oberfläche: Design-System und Seitengerüst** (Baustein 10c, Paket 1): eigene Token für hell
  und dunkel mit nachgerechneten Kontrasten (Test), Systemschrift, CSS ohne Framework in einer
  Datei (`accounti.css`, ≤ 40 KB), Symbole als lokales SVG-Sprite (Lucide 1.55.0, 36 Symbole,
  ISC/MIT), Komponenten als Jinja-Makros mit Musterseite `/muster` (hell und dunkel
  nebeneinander); Aussehen nach der freigegebenen Design-Leinwand (`docs/design/`). Neues Gerüst: ab 64rem Seitenleiste
  mit Zählern, darunter eine feste untere Leiste mit höchstens fünf Zielen und die Seite „Mehr“
  (`/menue`) – ohne Skript; Kopfleiste mit Kennfarbe und Kürzel der Gesellschaft, Hilfe und
  Benutzermenü; Titel „Seite · Gesellschaft · accounti“; Brotkrumen; „Zum Inhalt springen“;
  Druckansicht mit Kopf. `/gesellschaft` listet die eigenen Gesellschaften mit offenen
  Prüfungen und Freigaben und wechselt per Formular. „Mein Konto“ (`/konto`): Sprache,
  Darstellung (automatisch/hell/dunkel), Fachansicht, Beträge verbergen und Tastenkürzel am
  Benutzer, ohne JavaScript speicherbar. Hilfe je Bereich (`/hilfe`, auch ohne Anmeldung) mit
  Kurzanleitung, Begriffen und Tastenkürzeln. Fehlerseiten für 403 (nennt das fehlende Recht
  und die Rollen), 404, 409, 422, 503 und 500 (ohne technische Einzelheiten) im Design; mit
  htmx als Fragment. Browserprobe als Entwicklungswerkzeug (`scripts/browserprobe/`,
  Playwright 1.64.0 und axe-core 4.14.0, nicht ausgeliefert). Migration
  `<rev>_add_benutzer_vorlieben` (`auth_benutzer`).
```

**Unter `### Geändert`** oben einfügen:

```markdown
- **Oberfläche:** Alle Seiten aus 10a und 10b (Anmeldung, Übersicht, Freigaben, Prüfen,
  Buchung, Beleg) im neuen Design, fachlich unverändert. Die Sprachwahl zieht von der
  Kopfleiste nach „Mein Konto“ (`POST /konto/vorlieben`); `POST /einstellungen/sprache`
  antwortet ein Release lang mit 308. „Freigaben“ steht in der Navigation nur noch mit dem
  Recht, Zahlungsläufe oder Steuermeldungen freizugeben (die Seite bleibt für alle lesbar). Das
  Codefeld bei Anmeldung, Freigaben und Storno öffnet auf dem Handy die Zifferntastatur;
  „Wiederherstellungscode verwenden“ schaltet auf ein Textfeld um (ohne JavaScript). Die
  Abschaltung der Tastenkürzel liegt am Benutzer statt im Browser (`localStorage`) – wer sie
  abgeschaltet hatte, schaltet sie einmal unter „Mein Konto“ wieder ab. `pruefen.css` entfällt.
```

**Unter `### Behoben`** oben einfügen:

```markdown
- **Oberfläche:** Die Prüfliste scrollt auf dem Handy nicht mehr waagrecht (Tabellen werden
  unter 40rem zu Karten); im Dunkelmodus bleiben Felder und Knöpfe nicht mehr weiß
  (`color-scheme`), `<kbd>` ist lesbar; das Einmalcode-Feld hat ein sichtbares Label; Label und
  Wert in Angabenlisten überlappen nicht mehr; die Hauptaktion ist als primärer Knopf
  erkennbar; die Kopfleiste ist auf dem Handy höchstens 56 px hoch.
```

### docs/bauplan.md

**Ergänzt** im Absatz „**Baustein 10 ist teilweise fertig** …“ nach dem Satz, der mit „Dazu aus
10b, Teil 1:“ beginnt (vor „Offen (10b, Teil 2): …“):

```markdown
Dazu aus 10c, Paket 1 ([Spec 10c](specs/2026-10-26-oberflaeche-einrichtung.md),
[Plan](plans/2026-10-28-oberflaeche-p1-design.md)): ein eigenes Design-System (Token hell und
dunkel, Komponenten, Musterseite, Symbole) und ein neues Seitengerüst mit Seitenleiste, unterer
Leiste für das Handy, Gesellschaft mit Kennfarbe, Hilfe je Bereich, Fehlerseiten und „Mein Konto“
mit den Anzeige-Vorlieben; die bestehenden Seiten sind umgestellt. Offen aus 10c: Übersicht
„Heute zu tun“ (P2), neue Bedienung der Prüfschlange (P3), Einstellungen im Browser (P4, P5),
Benutzerverwaltung (P6) und der Einrichtungsassistent (P7).
```

### docs/architektur.md

**Ersetzt** im Abschnitt „### `api/`“ die Punkte
„`vorlagen/` + `vorlagen.py` (Jinja2, Autoescape, `basis.html`), `statisch/` (CSS), …“,
„`seiten/sprache.py` — Sprache am Benutzer.“ und
„`statisch/` — `accounti.css` und je Bereich ein Stylesheet, …“ durch:

```markdown
- `registry.py` — Router-Registry; `Navigationspunkt(titel, pfad, bereich, symbol, recht,
  reihenfolge, zaehler, kurztitel)`. Die Bereiche (`Bereich`) stehen in fester Reihenfolge; ein
  Bereich erscheint nur mit registrierter Seite und Recht (`recht` als `frozenset`: eines
  genügt). `geruest.py` baut daraus Seitenleiste, untere Leiste, aktiven Bereich, Brotkrumen,
  Hilfe-Link und Kennfarbe der Gesellschaft (`kennfarben` über alle Gesellschaften der
  Registry, stabil je Kürzel, für alle Benutzer gleich).
- `vorlagen.py` — `async seite()` rendert mit dem Gerüst-Kontext; Zähler der Navigation laufen im
  eigenen Threadpool von `lesezugriff.py` (eigene Engines ohne `init_db`, nur lesend, kurze Fristen),
  nur für ganze Seiten ohne Fehlerstatus. Neue Seiten liefern mit `HX-Request` nur ihren Block
  `inhalt` (`seite(…, teil="inhalt")`). `vorlagen/basis.html` (Gerüst), `schlicht.html`
  (Anmeldung, 500), `_komponenten.html` (alle Bausteine des Design-Systems als Makros, jede auf
  `/muster`), `_makros.html` (fachliche Bausteine: Konto, Steuerschlüssel).
- `statisch/` — **eine** Stildatei `accounti.css` (Ebenen `token`, `basis`, `layout`,
  `komponenten`, `seiten`, `hilfen`, `druck`; Token hell/dunkel, ein Test rechnet die Kontraste
  aus der Datei; ein zweiter Test hält die Farben an der Design-Leinwand in
  `docs/design/2026-10-26-leinwand/` fest; die Klassen `.thema-hell`/`.thema-dunkel` zeigen beide
  Modi nebeneinander auf `/muster`), `symbole.svg` (Lucide-Teilmenge, Lizenz daneben), `htmx-2.0.11.min.js` (ohne
  `eval`, Prüfsumme im Test), `accounti.js` (Fehlerhinweis, `aria-busy`, Fokus nach Austausch),
  `pruefen.js` (Tasten, abschaltbar über `<body data-tastenkuerzel>`). Keine Inline-Skripte und
  -Stile, eigene Dateien mit Versionsanhang, Budgets im Test (CSS 40 KB, Skripte 20 KB, Symbole
  15 KB).
- `seiten/konto.py` (Mein Konto, Vorlieben am Benutzer über `auth.dienst.setze_vorlieben`),
  `menue.py` („Mehr“), `gesellschaft.py` (Liste mit Zählern, Wechsel), `hilfe.py` (Hilfe je
  Bereich aus `hilfe_inhalt.py`, ohne Anmeldung), `muster.py` (Musterseite mit erfundenen Daten).
- Fehlerseiten: `fehler.html` im Gerüst (403 nennt Recht und Rollen über `sitzung.verweigert`),
  mit htmx das Fragment `_fehler.html`; 500 rendert die Middleware schlicht ohne Datenbank und
  ohne Einzelheiten.
```

**Neuer Abschnitt** unter „## Erweiterungspunkte“ vor „### Neue Kontierungsregel hinzufügen“:

```markdown
### Neue Seite anschließen

Ein Modul in `accounti/api/seiten/` mit `router` und, wenn die Seite ein Bereich ist, einem
`Navigationspunkt` (Bereich, Symbol aus `symbole.svg`, Recht, optional Zähler; Zähler lesen nur
und laufen über den Lesezugriff). Die Seite rendert mit `await seite(..., teil="inhalt")`
(mit `HX-Request` nur der Inhalt, ohne die ganze Seite). Weil dann nur der Block `inhalt` läuft,
steht in ihrer Vorlage auf oberster Ebene nur `{% extends %}` und Blöcke: `{% import
"_komponenten.html" as k with context %}` und `{% set %}` gehören **in** den Block, `super()` nicht
hinein – `seite()` prüft das und bricht sonst ab. Sie nutzt die Komponenten aus `_komponenten.html` und schreibt Stile nur als
Token-Verweise in `accounti.css` (Budget). Pflicht für jede neue Route: Eintrag in der
Rechte-Matrix (`tests/test_api_rechte_matrix.py`), in `GLEICHLAUF` (POST: Test von CLI und Browser
oder benannte Ausnahme) und `HTMX_FORMEN` (`tests/test_api_vollstaendigkeit.py`), alle Texte in
`i18n/en.yaml`, für einen neuen Bereich eine Hilfeseite in `api/hilfe_inhalt.py`, eine neue
Komponente auch auf `/muster` – jeweils im selben Commit wie die Route bzw. der Text, damit die
Suite grün bleibt. Vor dem PR die Browserprobe (`scripts/browserprobe/`) über die neuen Seiten
laufen lassen.
```

### docs/betrieb.md

**Neuer Absatz** in „## Benutzer, Rollen, Anmeldung“ nach dem Punkt „**Sitzungen:** …“:

```markdown
- **Mein Konto:** Jeder Benutzer wählt unter `/konto` Sprache, Darstellung (automatisch, hell,
  dunkel), Fachansicht, ob die Übersicht Beträge verbirgt und ob Tastenkürzel gelten. Die Werte
  liegen in der Systemdatenbank am Benutzer und gelten auf jedem Gerät; ohne Anmeldung gilt
  „automatisch“. Die Hilfe (`/hilfe`) ist ohne Anmeldung erreichbar und enthält keine Daten.
```

**Neuer Absatz** in „## Upgrades“ nach „**Update auf Baustein 10b** …“:

````markdown
**Update auf Baustein 10c, Paket 1** (Migration `<rev>_add_benutzer_vorlieben` auf `<kopf>`:
`auth_benutzer.darstellung`, `fachansicht`, `betraege_verbergen`, `tastenkuerzel`): Vorher wie
oben stoppen und sichern. Wie bei 10b liegt `auth_benutzer` in **jeder** Datenbank – die
Systemdatenbank zuerst migrieren (ohne die Spalten startet `serve` nicht), danach jede
Gesellschaftsdatenbank. Die URLs stehen in `.env` und werden auf dem Host eingesetzt, deshalb
zuerst die `.env` in die Shell laden:

```bash
set -a; . ./.env; set +a
docker compose run --rm app -g muster db upgrade --db "$ACCOUNTI_SYSTEM_DB"   # Systemdatenbank zuerst
docker compose run --rm app -g muster db upgrade
docker compose run --rm app -g tochter db upgrade
```

`db upgrade` leitet bei Datenbanken ohne Versionsvermerk den Stand aus dem Schema ab (siehe
oben); mit Vermerk ist es gleich `alembic upgrade head`.

Bestehende Benutzer bekommen „automatisch“, Fachansicht aus, Beträge sichtbar, Tastenkürzel an.
Wer die Tastenkürzel im Browser abgeschaltet hatte, schaltet sie einmal unter „Mein Konto“ ab.
Der Reverse-Proxy braucht keine Änderung; alle Dateien (Stile, Symbole, Skripte) liefert
accounti selbst unter `/statisch` aus, nichts kommt von fremden Servern.
````

*(`<rev>` und `<kopf>` beim Merge eintragen; die Gesellschaftskürzel folgen dem Beispiel des
Abschnitts „Update auf Baustein 10b“.)*

### THIRD-PARTY.md

**Neue Zeile** in der Tabelle nach htmx:

```markdown
| Lucide 1.55.0 (`lucide-static`, Lucide Contributors; von Feather abgeleitete Symbole © Cole Bemis) — 36 Symbole der Oberfläche | `src/accounti/api/statisch/symbole.svg` (erzeugt mit `scripts/symbole.py` aus dem Tarball mit npm-Integrität `sha512-h18lunTF…m/A==`) | ISC; die von Feather abgeleiteten Symbole MIT | `src/accounti/api/statisch/LIZENZ-lucide.txt` |
```

**Neuer Absatz** unter der Tabelle:

```markdown
Nur für die Entwicklung (nicht ausgeliefert, nicht im Abbild): Playwright 1.64.0 (Apache-2.0)
und axe-core 4.14.0 (MPL-2.0) in `scripts/browserprobe/`, installiert mit `npm ci` aus der
Lockdatei. Die Browser (Chromium, Firefox) lädt `npx playwright install` von Microsofts
Playwright-CDN; sie stehen nicht in der Lockdatei und gelten unter den Lizenzen ihrer Hersteller.
```

### CONTRIBUTING.md

**Neuer Abschnitt** nach „## Development Setup“:

````markdown
## Oberfläche prüfen (Browserprobe)

```bash
cd scripts/browserprobe && npm ci && npx playwright install chromium firefox && cd ../..
python -m tests.browserprobe_welt --port 8473 --ziel /tmp/accounti-probe &   # Wegwerf-Bestand
node scripts/browserprobe/probe.mjs --welt /tmp/accounti-probe/probe.json --browser chromium
node scripts/browserprobe/probe.mjs --welt /tmp/accounti-probe/probe.json --browser firefox
node scripts/browserprobe/leinwand.mjs --quelle docs/design/2026-10-26-leinwand --ziel scripts/browserprobe/ergebnisse/leinwand
node scripts/browserprobe/probe.mjs --welt /tmp/accounti-probe/probe.json --browser chromium --vergleich scripts/browserprobe/ergebnisse/leinwand
```

`npx playwright install` lädt die Browser von Microsofts Playwright-CDN (Chromium-Revision aus
`playwright-core/browsers.json`, nicht durch die Lockdatei abgesichert). Die Probe misst je
Rolle, hell und dunkel, bei 1440, 390 und 320 px: waagrechtes Scrollen,
axe-core (WCAG 2.2 A/AA), CSP-Meldungen, Fokus, Zielgrößen, Zoom und Textabstände, Druck.
`leinwand.mjs` macht Referenzbilder aus der Design-Leinwand; `--vergleich` legt die Bilder der
Anwendung daneben (`ergebnisse/<datum>-vergleich.html`) und prüft Token und Maße gegen den Plan.
Das Ergebnis (`scripts/browserprobe/ergebnisse/`) gehört zusammengefasst in den PR. Neue Seiten
brauchen Rechte-Matrix, `GLEICHLAUF`/`HTMX_FORMEN`, Übersetzungen und bei einem neuen Bereich eine
Hilfeseite (siehe `docs/architektur.md`, „Neue Seite anschließen“).

Migrationstests hängen nie am Kopf der Kette, weil parallele Branches neu ketten: die eigene
Revision als Konstante, den Vorgänger über `ScriptDirectory.get_revision(REVISION).down_revision`,
Downgrades auf ausdrückliche Revisionen (kein `downgrade -1`), Vermerke gegen
`accounti.db.SCHEMA_STAND`. „Genau ein Kopf“ prüft nur
`tests/test_db_upgrade.py::test_schema_stand_ist_der_kopf_der_migrationen`; der Test
`tests/test_migration_regeln.py` weist die üblichen Kopfannahmen ab.
````

---

## Prüfbefunde und Umgang

### Erste Prüfung (Fassung 1 → 2)

Gegnerische Prüfung vom 26.10.2026 gegen `main` 18faeaa, `feat/web-oberflaeche` 964b2b0, die
Gesamttest-Branches, Spec und Skizzen. Jeden Befund habe ich vor der Übernahme selbst am Code
nachgeprüft: 10b-1 auf 1d3cf59, ein Commit nach 964b2b0, der nur `pruefschlange.py` und das README
ändert; Paket A auf 0ed330f; dazu der P4-Plan. „Angenommen“ heißt: eingearbeitet. Bei
„teilweise“ steht der zurückgewiesene Teil mit Grund dabei. Die Prüfung bestätigte außerdem die
Annahmen über den Code, die Abhängigkeiten (Versionen, Daten, Lizenzen, Prüfsummen), die
Kontraste und die Abweichungen B12/B13; daraus folgt nichts zu ändern.

| Befund | Nachprüfung | Entscheidung | Eingearbeitet in |
|--------|-------------|--------------|------------------|
| **H1** Migrationskette, `SCHEMA_STAND` | bestätigt: `SCHEMA_STAND = "6d38d11fc348"` (`db/__init__.py:125–128`), `init_db` stempelt neue Datenbanken, `test_db_upgrade.py:62–67` und `:70–82`, `test_migration_belegvollstaendigkeit.py:191–198`; alle vier Gesamttest-Migrationen hängen an `ddc9a184ddb4` | **teilweise.** Angenommen: `SCHEMA_STAND` im Migrations-Commit, Schutztests aus Paket A, `VOR` aus dem `ScriptDirectory`, `db upgrade`-Test ohne Bedingung, `betrieb.md` fest auf `accounti db upgrade`, Paket A als Voraussetzung. **Zurückgewiesen:** die feste Basis „nach 10b-1, A und F“ und die Kette `… → 6d38d11fc348 → 2f7c7043043e → P1`. Grund: Auch C und D bringen Migrationen (`46371a6681c2`, `a14acef69fae`), und welche vor P1 gemergt sind, entscheidet die Merge-Reihenfolge. P1 nimmt deshalb den Kopf `K`, den `alembic heads` beim Abzweigen zeigt. Auf A wartet P1 wegen `SCHEMA_STAND`, `db upgrade` und der gemeinsamen Auth-Dateien, auf F nicht | Kopf; Stand der Grundlage (Zeilen Paket A und Alembic-Kette, Absatz „Warum P1 auf Paket A wartet“); B10; Schritte 0, 3, 15; Migration; Offene Punkte 1–2; Doku `betrieb.md` |
| **M1** TDD-Reihenfolge, rote Suite | bestätigt: `test_api_rechte_matrix.py:140–144`, `test_i18n_katalog.py:70/75`, `test_api_statisch.py:165–171`; `Geruest` entstand erst in Schritt 6; der Zählertest lief vor den Leisten; für Übersicht, Buchung und Beleg gab es keinen roten Test | angenommen | Regeln am Anfang von „Aufgaben“; Schritt 0 (Vollständigkeitslisten mit dem Bestand); Schritt 2 (Versionsanhang); Schritt 4 (`Geruest`); Zählertest von 6 nach 7; Schritte 4, 8–10 (Matrix, Listen und `en.yaml` im selben Schritt); Schritt 12 (Querschnitt zuerst über `UMGESTELLT`, Tests für Übersicht, Buchung, Beleg) |
| **M2** AK47-Test widerspricht dem Kopf | bestätigt: `webwelt` hat zwei Gesellschaften (`api_hilfe.py:145`), der Gesellschafts-Link steht nur bei mehreren | angenommen in der Variante „relative Reihenfolge“ mit fester Kopf-Reihenfolge; als Auslegung von AK47 benannt | Entscheidung „Reihenfolge im Kopf“; Hilfe-Link; Auslegungen; Schritt 7; Spec-Tabelle |
| **M3** doppelte IDs | bestätigt: `buchung.html:65–83`, `freigaben.html:23/62`, `StornoError.feld` gegen `grund-k` | angenommen | B16; Komponenten; Formularfeld; Fehlerliste; Schnittstelle; Schritte 4 und 12 (`test_ids_je_seite_eindeutig`) |
| **M4** Wiederherstellungs-Link per GET | bestätigt: `anmelden.html:6–15` ist ein Formular mit verstecktem `weiter` | angenommen | B6; B17; Codefeld; Schritt 12 (`test_wiederherstellungsweg_behaelt_weiter`); Schritt 14 (AK53); Grenzen; Sicherheit |
| **M5** `/gesellschaft` unter der globalen Sperre | bestätigt: `dienste.py:61–67` (Sperre beim Verbinden und bei `init_db`, kein Merken eines Fehlschlags), SQLite-`timeout` 30 s (`db/__init__.py:93`), kein `connect_timeout` | **teilweise.** Angenommen: eigener Lesezugriff mit Fristen, ohne `init_db`, ohne globale Sperre, auch für die Zähler der aktiven Gesellschaft; Tests für hängende Verbindung und fehlende SQLite-Datei; gilt auch für P2. **Zurückgewiesen für P1:** `_fabrik` selbst umbauen. Grund: Mit dem Lesezugriff öffnet P1 keine weitere Datenbank über `_fabrik`. Das Verhalten für die aktive Gesellschaft stammt aus 10a, und P4 ändert `dienste.py` parallel. Als eigene Korrektur vorgeschlagen | B14; Entscheidungen „Zähler“ und `/gesellschaft`; Schnittstelle; Schritte 6 und 8; Sicherheit; R-P1-5; Übergabe P2; Offener Punkt 3 |
| **M6** Zähler auf Fehlerseiten | bestätigt: `beschaeftigt` rendert über `seite()` (`app.py:133–157`) | angenommen, zusätzlich für 413 und 422 | B15; Zähler; Fehlerseiten; Schritte 6 und 11 |
| **M7** Kennfarbe nicht stabil | bestätigt: Ausweichen in alphabetischer Reihenfolge, Eingabe offen | angenommen: Eingabe immer die ganze Registry, Umfärben als Grenze dokumentiert, Test mit zwei Benutzern. Einen reinen Hash habe ich verworfen, weil er schon bei zwei Gesellschaften mit 1 : 6 dieselbe Farbe ergibt | Kennfarbe; Schnittstelle; Schritt 8; Grenzen; Doku `architektur.md` |
| **M8** AK58 aufgeweicht | bestätigt: AK58 verlangt für jede neue Route mit `HX-Request` ein Fragment | angenommen, und zwar mit Fragmenten statt einer Abweichung (`seite(…, teil="inhalt")`) | Entscheidung „Zwei Formen der neuen Seiten“; Seitenstruktur; Schnittstelle; Schritte 4, 8–10 und 13; Spec-Tabelle |
| **M9** Grundlage veraltet, Konflikte unvollständig | bestätigt; inzwischen 1d3cf59 | angenommen | Kopf; Stand der Grundlage; B9; 403-Zeilen (:593/:650); Schritt 12 (`e.freigabe_gesperrt`); R-P1-4 (P4 und Paket A vollständig, Reihenfolge der Middlewares); Offener Punkt 4 |
| **M10** Chromium für die Browserprobe | bestätigt: `browsers.json` verlangt 1248 und 1555, vorhanden sind 1217 und 1223 | angenommen: Download auf dem Server nur nach Freigabe, Bezugsquelle in CONTRIBUTING und THIRD-PARTY. Rückfall ist Playwright 1.59.1 mit dem vorhandenen Chromium 1217 (Daten per `curl` nachgeprüft). Revision 1223 gehört nur zu einer Vorabversion von 1.60.0 und kommt deshalb nicht in Frage | Recherche; Browserprobe; Schritt 5; Grenzen; R-P1-6; Offener Punkt 6; Doku THIRD-PARTY und CONTRIBUTING |
| **N1** 403-Text | bestätigt: `test_i18n.py:66–68` prüft Gleichheit | angenommen; dadurch entfällt die verschachtelte Übersetzung | 403; Schnittstelle; Schritt 11; Dateien |
| **N2** umgestellte Tests unvollständig | bestätigt: `test_api_sprache.py:34`, `test_api_pruefen.py:326`, `api_hilfe.py:105–108/131–140` | angenommen | B9; Komponenten; Schritte 0, 4, 7, 9 und 15 |
| **N3** Bereichsangaben im Rückverfolgungstest | bestätigt; außerdem `A24–A28` und `A58–A60` | angenommen | Rückverfolgung; Schritt 0 |
| **N4** FastAPI-Parameter | bestätigt: ein Enum- bzw. Literal-Parameter ergibt 422 | angenommen | Hilfe; Seitenstruktur; Sicherheit; Schritte 4, 10 und 12 |
| **N5** Hilfe für die Test-Registry | bestätigt | angenommen (`fehlende_hilfe`) | Hilfe; Schnittstelle; Schritt 10; Spec-Tabelle |
| **N6** `xmlattr` | bestätigt: `jinja2>=3.1`, lokal 3.1.6 | angenommen | Komponenten; Sicherheit; Schritte 4 und 13 |
| **N7** `[hidden]` | bestätigt: `accounti.css:55` | angenommen | Stile; Schritt 1 |
| **N8** leere Zustände | bestätigt: `liste.html:40` | angenommen; wo die nächste Aktion noch keine Seite hat, verlinkt der Leerzustand auf die Hilfe (als Auslegung benannt) | Leere Zustände; Auslegungen; Schritte 10 und 12 |
| **N9** Statusbereich bleibt leer | bestätigt: `_arbeitsflaeche.html:9` | angenommen: P1 schreibt per `hx-swap-oob` in `#status` | Sprunglink/Statusbereich; Schritte 12 und 14; Übergabe P3 |
| **N10** Beispielfragment ohne Route | bestätigt | angenommen: `GET /muster/beispiel` | Seitenstruktur; Schritte 4, 5 und 14; Spec-Tabelle |
| **N11** Lucide-Lizenz mit Feather-Namen | bestätigt am Tarball | angenommen | Recherche; Symbole; Schritt 2 |
| **N12** Safe Area | bestätigt | angenommen | Schmale Bildschirme; Schritt 7 |
| **N13** Protokoll und Schreibweg der Vorlieben | bestätigt: `repo_auth.py:70–73`, `dienst.py:147–157` | angenommen | B18; Fachfunktion; Protokoll; Schritt 3; Sicherheit |
| **N14** Kleinigkeiten | bestätigt: 19 Aufrufe, davon zwei in synchronen Helfern; `Dockerfile` kopiert `alembic/`; `buchungssaetze.status` hat keinen Index; `set -a` fehlt | angenommen, alle sechs Punkte | Rendern; Werkzeuge; Sicherheit; Zähler; Schritt 6 (Messung); Auslegungen (AK55); Doku `betrieb.md`; Regeln (ein Commit je Komponente bzw. Seite) |

Zurückgewiesen sind damit nur zwei Teile: die feste Basis „nach 10b-1, A und F“ mit fest
eingetragener Kette (H1) und der Umbau von `Dienste._fabrik` innerhalb von P1 (M5).

### Zweite Prüfung (Fassung 2 → 3)

Gegenprüfung der Fassung 2 vom 26.10.2026 gegen `main` 18faeaa, 10b-1 43031a7, Paket A 606ef21
und die Branches C, D, E, F (Urteil dort: umsetzbar, vorher H beheben). Seitdem ist Paket A als
#32 gemergt (`main` 87c6c8d, baumgleich mit 606ef21). Jeden Punkt habe ich vor der Übernahme am
Code nachgeprüft (Quelltext per `git show`, Jinja 3.1.6, anyio 4.14.2, Starlette 1.6.0 und
Python 3.12.3 aus dem venv; Nachstellungen nur in einer Kopie im Scratchpad unter
`p1check2/`, am Repository nichts geändert). Die Bestätigungen der Prüfung – Zurückweisungen
aus der ersten Runde berechtigt, M10 nachgerechnet, `db upgrade` erkennt die neue Migration ohne
Änderung an `db/upgrade.py`, der Konflikt in `SCHEMA_STAND = …` als Schutz – habe ich
übernommen (Absatz „Warum P1 auf Paket A wartet“, Migration).

| Befund | Nachprüfung | Entscheidung | Eingearbeitet in |
|--------|-------------|--------------|------------------|
| **H** Migrationstests am Kopf der Kette | bestätigt: der Plan las `KOPF = get_current_head()`, `VOR = get_revision(KOPF).down_revision`; kettet P4 (`plan-10c-p4-einstellungen.md:165–167`) oder ein anderes Paket nach P1 auf `<rev>`, wäre `KOPF` dessen Revision und `VOR` die von P1 – die sechs genannten Tests würden rot oder prüften das Falsche. Vorbild Paket D `test_migration_verrechnungen.py:20–28` gelesen | angenommen: `VORLIEBEN = "<rev>"` fest, `VOR = _vorher(VORLIEBEN)`, Vermerke gegen `SCHEMA_STAND`, „genau ein Kopf“ nur über den Test aus Paket A; `test_ein_kopf_nach_ddc9a184ddb4` ohne Kopfannahme (Vorfahren von `VORLIEBEN`). Die Regel für den P4-Plan steht als offener Punkt 4 (den P4-Plan ändere ich hier nicht) | Stand der Grundlage (Alembic-Kette); B10; Schritt 3; Schritt 15; Migration; Spec-Tabelle A118/AK61; Übergabe „alle“; Offener Punkt 4; Doku CONTRIBUTING |
| **M-a** kopfrelative Tests anderer Pakete | bestätigt: `test_db_upgrade.py:201`, `:227`, `:280`, `:289` auf `main`, `test_migration_anlagen_buchung.py:35` auf F; die CI hat keinen PostgreSQL-Dienst. **Nachgestellt:** eine leere Migration auf `6d38d11fc348` in einer Kopie von 87c6c8d → `test_downgrade_token_index_bricht_vor_dem_loeschen_ab` rot, `:201` grün, prüft aber die falsche Migration. Beim Umstellen fiel zusätzlich auf: vom Kopf aus nähme `downgrade _vorher(TOKEN)` erst die späteren Migrationen zurück, `:227`/`:280` müssen deshalb auf `TOKEN` hinauf statt auf `head` | angenommen, ergänzt um die Umstellung „auf `TOKEN` statt `head`“ und einen Wächtertest (`test_kein_migrationstest_haengt_am_kopf`), damit C, D, F und P2–P7 die Regel nicht neu lernen müssen | Stand der Grundlage (Gesamttest-Branches, Paket A); B10; Schritt 0 (Kopfannahmen auflisten); Schritt 3 (neuer Punkt „Kopfrelative Tests anderer Pakete“); Schritt 15 (ganze Suite mit `ACCOUNTI_TEST_PG`); Dateien; Offener Punkt 1; Spec-Tabelle |
| **M-b** `teil="inhalt"` gegen Importe oben | bestätigt: `buchungen/buchung.html:2`, `pruefen/liste.html:2`, `pruefen/regeln.html:2` importieren oben; nachgestellt mit Jinja 3.1.6: Import oben → `'k' is undefined`, `{% set %}` oben → `'y' is undefined`, `super()` im Block → `there is no parent block called 'inhalt'`; Import im Block → rendert | angenommen in der Variante „Import im Block `inhalt`, kein `set` oben“, ergänzt um „kein `super()`“ und eine Prüfung in `seite()` selbst (je Vorlage einmal, `RuntimeError`), damit schon das Rendern der ganzen Seite scheitert und keine Liste der betroffenen Vorlagen gepflegt werden muss. Nicht gewählt: `_komponenten` als Jinja-Global (verlöre `with context`) und je Seite eine Teilvorlage (doppelte Dateien) | Was 10a/10b liefern (Rendern); B19; Entscheidung „Zwei Formen“; Schnittstelle (`seite`, Komponenten); Schritt 4; Spec-Tabelle A115; Doku `architektur.md` („Neue Seite anschließen“); Übergabe „alle“ |
| **N1** Grundlage veraltet | bestätigt und weiter fortgeschritten: 10b-1 43031a7 (drei Commits nach 1d3cf59: `pruefschlange.py`, `_regelvorschau.html`, `en.yaml`, `lernen.py`, Tests), C 2d1aec2, D 2f62e17, E 243754f, F 410cc64; **Paket A gemergt** (#32, 87c6c8d, Kopf `6d38d11fc348`). Die übrigen zitierten Zeilen ändern sich dadurch nicht | angenommen | Kopf; Stand der Grundlage; Warum P1 auf Paket A wartet; Offener Punkt 2 (erledigt); Doku-Bausteine (Grundlage) |
| **N2** `pruefen.css` überstimmt die Komponenten | bestätigt: keine `@layer`, `.reiter` :3–4, `.knopf` :5, `.hinweis` :24, `.haken` :31–32, `--gedaempft`/`--hintergrund`. Der Vorschlag `@layer seiten` reicht aber nicht: `seiten` steht nach `komponenten` und gewinnt ebenfalls | **teilweise.** Angenommen: in Schritt 1 in eine Ebene fassen, Token umschreiben, je Seiten-Commit Regeln entfernen. **Geändert:** Übergangsebene `bestand` **vor** `komponenten` (auch für die alten Regeln aus `accounti.css`), am Ende von Schritt 12 gestrichen; Tests `test_jede_regel_in_einer_ebene`, `test_jeder_tokenverweis_definiert`, `test_ebenenfolge_wie_entschieden` | Was 10a/10b liefern (Stile); B20; Entscheidung „Eine CSS-Datei“; Schritt 1; Schritt 12 (Einleitung, `pruefen.css` entfernen); Dateien; Spec-Tabelle A89/A121 |
| **N3** 500 im Hilfe-Link-Test | bestätigt: 500 ist schlicht, ihr Index weicht für Angemeldete ab; außerdem entsteht die 500-Seite erst in Schritt 11, der Test in Schritt 7 | angenommen: 500 nur im Vergleich der relativen Reihenfolge, ab Schritt 11 | Schritt 7; Auslegung AK47; Spec-Tabelle AK47 |
| **N4** `?code=` auf `/freigaben` und `/buchungen/{id}` | bestätigt: Seitenstruktur und Test nannten nur `/anmelden` | angenommen; dazu: der Parameter schaltet **alle** Codefelder der Seite um | Seitenstruktur; Schritt 12 (Querschnitt `test_code_parameter_je_seite`, Freigaben, Buchung); Spec-Tabelle A109 |
| **N5** Reihenfolge der Middlewares | bestätigt: der P4-Plan nennt sie nicht (`:160`, `:881`); in Starlette ist die zuletzt mit `add_middleware` eingetragene die äußerste (`applications.py:107`), `main` trägt `Sicherheit` in `app.py:53` ein | angenommen: Strukturtest `test_sicherheit_ist_die_aeusserste_middleware` und Verhaltenstest mit einer werfenden inneren Middleware; Nachtrag im P4-Plan als offener Punkt | Schritt 11; Sicherheit; R-P1-4; Offener Punkt 4; Spec-Tabelle A9 |
| **N6** Strg+Enter | bestätigt: `pruefen.js:98`, `_korrektur.html:51`, Tests `test_api_statisch.py:184` und zusätzlich `test_api_pruefen.py:341` (`test_korrigieren_ist_der_standardknopf`) | angenommen als „Skript und Tests mitziehen“, mit einem Kennzeichen unabhängig von der Optik (`data-hauptknopf`): „Korrigieren“ ist auf der Arbeitsfläche sekundär, `knopf-primaer` träfe es nicht | B21; Schritt 9; Schritt 12 (Prüfen); Dateien; Spec-Tabelle A105 |
| **N7** Starthinweis | bestätigt: `dienste.py:80–101` nennt `alembic upgrade head` und nur die erste Spalte, Test `test_api_schema.py:39`; AK61 nennt `alembic upgrade head` wörtlich | angenommen: die Meldung nennt `accounti db upgrade` und `alembic upgrade head` als Gleichwert mit Vermerk – so bleibt AK61 wörtlich erfüllt und der Test aus 10b Schutz; Nachtrag in der Spec als Auslegung | Was 10a/10b liefern; B22; Auslegungen; Schritt 3 (Schemaprüfung); Migration (Start); Dateien; Spec-Tabelle AK61 |
| **N8** Lizenz axe-core | bestätigt: A117 verlangt BSD/MIT/Apache/ISC, axe-core 4.14.0 ist MPL-2.0 | angenommen | Auslegungen (A117) |
| **N9** 404 schreibt in die Datenbank | bestätigt: `_lade` → `pruefe_sitzung` → `beende_sitzung`/`markiere_sitzung_aktiv` (`auth/dienst.py:618–621`), über `_fabrik`, SQLite-`timeout` 30 s; eine Ausnahme im Exception-Handler wird zur 500 | angenommen, auch für die Hilfe (gleiche Funktion): `vielleicht_angemeldet` gibt bei `SQLAlchemyError` `None` zurück | Was 10a/10b liefern; B23; Entscheidung „Fehlerseiten“; Schnittstelle; Schritte 10 und 11; Sicherheit; Grenzen; Spec-Tabelle A9 |
| **N10** Frist der Zähler | bestätigt: Starlette 1.6.0 ruft `anyio.to_thread.run_sync(func)` ohne `abandon_on_cancel`; gemessen (anyio 4.14.2) bricht `wait_for` trotzdem nach 0,3 s ab, gewährleistet ist das über die erlaubten Fassungen nicht | **teilweise.** Angenommen: die Frist ausdrücklich absichern, Test. **Anders umgesetzt:** eigener `ThreadPoolExecutor` des Lesezugriffs mit `loop.run_in_executor` statt `anyio.to_thread.run_sync(…, abandon_on_cancel=True)`. Grund: anyio steht nicht in `pyproject.toml` (es neu einzutragen verböte AK60), `abandon_on_cancel` gibt es erst ab anyio 4.1, Starlette erlaubt anyio ab 3.6.2; die Standardbibliothek kehrt bei `wait_for` sicher zurück, und hängende Zähler belegen keine Plätze des gemeinsamen Threadpools. Nachgestellt (`p1check2/frist2.py`): 0,3 s, eine zweite Anfrage läuft sofort durch | B1; Entscheidung „Zähler“ und `/gesellschaft`; Schnittstelle; Schritt 6; Grenzen; R-P1-5; Doku `architektur.md` |

Zurückgewiesen ist in dieser Runde nichts ganz. Anders als vorgeschlagen umgesetzt sind zwei
Teile: die Ebene für die alten Regeln (`bestand` vor `komponenten` statt `seiten`, N2) und der
Weg zur Frist (eigener Pool statt `abandon_on_cancel`, N10).


### Angleichung an die Leinwand (Fassung 3 → 4)

Anlass ist keine Prüfung, sondern die Freigabe der Design-Leinwand durch den Nutzer am 26.10.2026.
Gelesen wurden alle zehn Zeichenflächen; gerendert wurden sie hell und dunkel; die Kontraste sind
nachgerechnet (L0, L1). Am Repository ist nichts geändert. Fachlogik, Migration, Zähler,
Lesezugriff, Fehlerwege, Hilfe, Vorlieben, Testregeln und Prüfbefehle sind unverändert.

| Bereich | Änderung | Abschnitte |
|---|---|---|
| Quelle des Aussehens | Neuer Abschnitt „Design-Leinwand“ (L0–L10). Die Leinwand liegt im Repository (`docs/design/2026-10-26-leinwand/`). Wo sie der Spec widerspricht, gilt die Spec; L7 nennt 25 Fälle mit Lösung | Kopf, Ziel, Spec-Zeile, L0, L7, Schritt 0, Dateien |
| Farb-Token | Die Werte stimmen mit der Spec überein und sind jetzt an die Leinwand gebunden (`test_token_wie_leinwand`). Neu: `--fehler-text` (7,15 / 8,86), `--schatten`, `--schleier` (Hover, ≥ 5,41) | L1, Entscheidung „Token“, Schritt 1, Spec-Tabelle A89 |
| Kennfarben | Werte aus der Leinwand (Violett, Blau, Grün, Orange, Rot) plus Oliv aus Fassung 3. Alle ≥ 4,27 : 1 zu den Flächen, das Kürzel darauf ≥ 4,99 : 1. Die Nähe zu den Statusfarben ist hingenommen | L1, Entscheidung „Kennfarbe“, Grenzen, Offener Punkt 9 |
| Kürzel | Monogramm aus dem Namen, in der Registry eindeutig, weil Registry-Kürzel bis zu 30 Zeichen haben (B24) | B24, Schnittstelle, Schritte 7 und 8, L7 Nr. 18 |
| Typografie | Skala mit neun Stufen (12/13/14/16/18/20/22/28/40 px), `tabular-nums` auf `body`, Kürzel 600 statt 700 | L2, Entscheidung „Schrift“, Schritt 1 (`test_schriftgroessen_nur_aus_der_skala`) |
| Abstände, Radien, Maße | Zwischenstufen 20/28/40 px, Feinstufen 2/6/10 px nur in Komponenten, Rundungsregel; Radien 2/4/6/8/10/12/rund; Kopf 56, untere Leiste 64, Seitenleiste 232 px | L3, Entscheidung „Raster und Layouts“, Schritt 1 (`test_abstaende_und_radien_aus_token`), Schritt 7 (`test_masse_des_geruests`) |
| Fokus | Ring 3 px statt 2 px, wie die Leinwand; Auslegung von A104 | L7 Nr. 8, Entscheidung „Fokus“, Auslegungen, Schritt 1 |
| Komponenten | Maße und Zustände aller Komponenten nach der Leinwand. Neu: `aufklapper`, `sammelleiste`, `marke`, `avatar`; `feld` mit Warnung und „bestätigt“; `karte` mit Kennzahl; `zaehler` betont; `knopf` mit `groesse`, `breit`, `laedt`; `reiter(geteilt)`; `tabelle(in_karte)`; `zeile(gewaehlt)`. `kbd` ohne Deckkraft | L4, Entscheidung „Komponenten“, Schnittstelle, Schritt 4 |
| Layouts | Flex-Paar Seitenleiste/Inhalt wie die Leinwand; zweispaltig über die Flex-Basis; Einstellungen und Formular mit den Breiten der Leinwand | L5, Entscheidung „Raster und Layouts“, Auslegung A91 |
| Symbole | 36 statt 37: `square-check-big`, `calendar`, `shield-check` und `menu` statt `list-checks`, `calculator`, `stamp` und `ellipsis`; neu `circle-alert`, `lock`, `arrow-right`; entfallen `gauge`, `circle-user`, `building-2`, `circle-check`. Lizenzzuordnung mit `circle-alert` statt `ellipsis`; Probe-Sprite 6 443 Bytes | L6, Recherche, Entscheidung „Symbole“, Seitenstruktur, Schritt 2 |
| Musterseite | Nachbildung der Zeichenfläche „Bausteine“: ohne Parameter hell und dunkel nebeneinander (`.thema-hell`/`.thema-dunkel`), sieben Abschnitte in der Reihenfolge der Zeichenfläche plus Ergänzungen | L9, Seitenstruktur, Entscheidung „Hell/dunkel“, Schritt 4 |
| Bildvergleich | Referenzbilder aus der Leinwand (`leinwand.mjs`), Gegenüberstellung und Maßprobe (`probe.mjs --vergleich`), Handprüfung der Optik durch den Nutzer; Python-Playwright ist im venv nicht vorhanden und kommt nicht hinein (AK60) | L10, Schritte 5 und 14, Doku CONTRIBUTING |
| Bestandsseiten | Optik der zugeordneten Zeichenfläche mit den bisherigen Inhalten und Wörtern (Übersicht als Kennzahl-Karten, Freigaben als Karten je Lauf, Prüfen mit Reiter und Tabelle, Arbeitsfläche zweispaltig im Gerüst) | L8, Schritt 12, Grenzen |
| Spätere Pakete | Zuordnung, was aus der Leinwand P2, P3, P5 und P7 bauen; P3 entscheidet über den Fokusmodus | L8, Übergabe, Offener Punkt 10 |
| Grundlage | Nachtrag zu `main` 339a30a und 10b-1 2de9a1b; für P1 ohne neue Folgen | Stand der Grundlage |

---

## Umsetzung

Was beim Umsetzen gegenüber dem Plan anders kam, mit Grund. Abschnitt A = Schritte 0–4
(Branch `feat/oberflaeche-p1-design`, abgezweigt von `main` 3fa8463).

### Schritt 0 — Grundlage, Kopf, Ablage

- **Grundlage (03.11.2026):** `main` steht auf **3fa8463** (#39). Gemergt sind Paket A (#32),
  F (#33), D (#34), C (#35), 10b-1 (#36), die Nacharbeit zu 10b-1 (#37) und G (#39, § 14c). Offen
  ist E (#38, Steuer/DATEV/Marktplatz, ohne Migration und ohne Web-Vorlagen); es wird nach dem
  Merge nachgeführt.
- **`K` = `e7153706b43a`** (`alembic heads`: genau ein Kopf), `db.SCHEMA_STAND` = `e7153706b43a`,
  `test_schema_stand_ist_der_kopf_der_migrationen` grün. Kette über Baustein 7: `ddc9a184ddb4` →
  `6d38d11fc348` (A) → `2f7c7043043e` (F) → `a14acef69fae` (D) → `46371a6681c2` (C) →
  `d5a849692843` → `e7153706b43a` (10b-1).
- **Testliste von `main`:** 5 125 Tests (`pytest --collect-only -q`), gesichert unter
  `.claude/arbeit/s/gesamttest/p1a/testliste-main-3fa8463.txt` (für den Abgleich in Schritt 15).
- **Kopfannahmen** (`git grep` wie geplant, dazu Aussagen „X ist der Kopf“):
  - `tests/test_migration_web.py:93` (`SPRACHE in kopf`) und `:96`
    (`f"{KONTIERUNG} -> {SPRACHE} (head)"`) in `test_ein_kopf_nach_den_verrechnungen` (so heißt
    `test_ein_kopf_nach_ddc9a184ddb4` inzwischen) — Schritt 3 stellt um.
  - `tests/test_db_upgrade.py:207`, `:253`, `:287`: `_version(db) == [SCHEMA_STAND] == [SPRACHE]`;
    `:251–252`: `_nach(VERRECHNUNGEN) == [STEUERKENNZEICHEN, KONTIERUNG, SPRACHE]` und
    „(3 Migration(en))“ — Schritt 3 stellt um.
  - Kein relatives Downgrade (`"downgrade", "-N"`) und kein `get_current_head` mehr in `tests/`:
    Paket A (`VOR_TOKEN`) und F (`test_migration_anlagen_buchung.py`) gehen schon auf
    ausdrückliche Revisionen; das bleibt Schutz.
  - `count("(head)") == 1` in `test_db_upgrade.py:612`, `test_migration_belegvollstaendigkeit.py:116`,
    `test_migration_web.py:149` und `len(get_heads()) == 1` in
    `test_migration_steuerkennzeichen.py:43` zählen nur Köpfe — erlaubt.
- **Abweichungen vom „Stand der Grundlage“:**
  - `seite()` hat 20 Aufrufe (Plan: 19); die 403 der Rolle steht in `api/sitzung.py:169`, die
    Klartext-500 in `api/sicherheit.py:106–108` (beides erst ab Schritt 6/11 von Belang).
  - Die Startmeldung (`api/dienste.py:92–103`) nennt schon `accounti db upgrade` (#37), aber nur
    die erste fehlende Spalte und nicht `alembic upgrade head`; `test_api_schema.py` prüft
    `accounti db upgrade` (nicht `alembic upgrade head`, wie der Plan unter Schritt 3 als Schutz
    annimmt).
  - Die Leinwand hat inzwischen **18** Zeichenflächen: zu den zehn freigegebenen kamen
    `Bank-Umsaetze`, `Belege-paperless`, `Buchungen`, `Handy-Bank`, `Handy-Belege`,
    `Rechnungen`, `Kontakt-Detail` und `Anlagen` (laut Spec-Nachtrag N20 noch **nicht**
    freigegeben; Pakete P8–P16). Alle 18 liegen unter `docs/design/2026-10-26-leinwand/`;
    `test_leinwand_abgelegt` liest die Liste aus `canvas.json` (`order`) statt einer festen Zahl.
    Die Token sind in allen 18 widerspruchsfrei; neu ist nur `--papier` (`#fbfaf7` / `#d9d6cf`,
    Vorschaubild eines paperless-Dokuments in `Belege-paperless` und `Handy-Belege`).
- **Spec und Skizzen** liegen unter `docs/specs/2026-10-26-oberflaeche-einrichtung.md` und
  `…-skizzen.md`; in Anhang C steht statt des Scratchpad-Pfads „liegt beim Autor der Spec“, die
  Verweise zwischen Spec und Skizzen zeigen auf die abgelegten Dateien.
- **Rückverfolgung:** zusätzlich `test_anhang_d_nennt_die_kriterien_aus_abschnitt_7` (die Spalte
  „Akzeptanz“ in Anhang D stimmt mit den Klammern der Kriterien überein — am 03.11.2026 ohne
  Abweichung) und `test_spec_und_skizzen_ohne_pfade_auf_den_scratchpad`.
- **Vollständigkeitslisten:** `GLEICHLAUF` nennt für die POST-Endpunkte aus 10a/10b den
  vorhandenen Test (Akzeptanz 1, Korrektur einer freigegebenen Buchung, Storno) oder `Bestand`
  mit dem Plan 10a bzw. 10b; Ausnahmen nach A113 sind Anmeldung, Abmeldung, Wechsel der
  Gesellschaft, Sprachwahl und die Regelvorschau (liest nur). `HTMX_FORMEN` umfasst die Routen der
  Seiten ohne die REST-API; Dateien und Bilder (`/belege/…/datei`, `…/seite/{n}.png`,
  `…/download`) stehen als `ganze_seite` mit eigenem Grund. Die drei Tests sind Schutztests
  (grün mit dem Bestand).
