# Supervisions-Queue, Auswertungen und Zweisprachigkeit (Baustein 10b „Web-Oberfläche“) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken. Ablageort beim Zusammenführen:
> `docs/plans/2026-10-27-web-oberflaeche.md`.
>
> **Fassung 3** (21.10.2026): an den neuen Stand angeglichen — `main` **3d20af3** (Baustein 10a
> #27, Kontenrahmen-Korrektur #28) und Baustein 7 `feat/belegvollstaendigkeit-gobd` **81d3b51**
> (main eingemergt, Migration `ddc9a184ddb4`, kurz vor dem Merge). Grundlage bleibt Fassung 2
> nach gegnerischer Prüfung (`plan-10b-pruefung.md`: H1–H3, M1–M10, N1–N17 eingearbeitet). Was
> sich durch 10a, 7 und #28 geändert hat, steht gesammelt im Abschnitt „Abgleich mit dem neuen
> Stand“ und ist an den betroffenen Stellen eingearbeitet. **Abzweigen erst, wenn 7 auf `main`
> ist** (Alembic-Kopf `ddc9a184ddb4`); ändert sich 7 bis dahin noch, die im Abschnitt „Was 7
> liefert“ genannten Signaturen neu lesen. Umsetzung in **zwei PRs** wie in Fassung 2: 10b-1
> (Pakete 1–3, Akzeptanz 1 und 2) und 10b-2 (Paket 4, Auswertungen), Abschluss je PR.

**Ziel:** Unsichere Buchungen werden im Browser geprüft: links der Beleg (PDF, Bild oder
E-Rechnung als lesbare Ansicht), rechts der Vorschlag mit Konto, Steuerschlüssel, Betrag,
Confidence und **der gespeicherten Herkunft und Begründung** (Klassifikation, Kreditkarte, Anlagen,
Marktplatz, offene Posten). Freigeben, korrigieren oder zurückstellen geht in einem Schritt und per
Tastatur — auch mit HTMX mit sichtbaren Fehlermeldungen. Eine Korrektur eines
Kontierungsvorschlags bietet an, daraus eine Regel zu machen — mit Vorschau, was die Regel treffen
wird, nur mit Recht, **nur in der Zahlungsrichtung des Quellumsatzes**, abschaltbar und so
gespeichert, dass sie beim nächsten Lauf **vor** der Regel greift, die falsch kontiert hat.
Freigegebene und exportierte Buchungen korrigiert die Oberfläche nur über Storno und Neubuchung aus
Baustein 7 — mit frischem Einmalcode wie Zahlungslauf und USt-VA; im Journal steht immer der
angemeldete Benutzer. Auswertungen zeigen BWA mit Vorjahresvergleich (kumuliert im Wirtschaftsjahr
der Gesellschaft, Zuordnung im Einklang mit den EÜR-Kennzahlen des korrigierten Kontenrahmens),
Summen- und Saldenliste, Kontenblätter mit Übertrag und Absprung zum Beleg und offene Posten,
jeweils als CSV und PDF. Die Oberfläche spricht Deutsch und Englisch, Fachbegriffe ohne tragfähige
Entsprechung bleiben deutsch. Die Oberfläche ruft dafür dieselben Funktionen auf wie die CLI. Was
dort fehlt (BWA, Kontenblatt, Lernschleife in der Datenbank, Prüfschlange), entsteht hier als
Fachfunktion **mit** CLI-Befehl, nicht als Browserlogik.

**Spec:** [`docs/specs/2026-08-10-web-ui-auth-betrieb.md`](../specs/2026-08-10-web-ui-auth-betrieb.md),
Abschnitte 4.2, 4.3, 4.5 · Akzeptanzkriterien 1 und 2 · Teststrategie (Testclient, Durchlauf
Vorschlag → Korrektur → Regel → erneuter Lauf, Rechte-Matrix, Log ohne Personenbezug) ·
**Baut auf:** Baustein 10a (Gerüst, Anmeldung, Rollen, Gesellschaften, CSP, CSRF, Einmalcode,
Laufsperre, Sicherung, REST), 7 (Storno statt Änderung, Journal, Periodenabschluss,
Belegnachforderung, Prüfregel `steuerschluessel_konto`), 8 (Rückfragen, Aufgaben), 2/3
(Belegarchiv, E-Rechnung lesen), 4 (offene Posten), 12 (Bewegungen, Summen und Salden,
Kontenrahmen mit EÜR-Kennzahlen, korrigiert in #28) · **Nicht hier:** Spec 4.1, 4.4, 4.6, 4.7
(Baustein 10a); Seiten `/belege` (Liste, Suche), `/opos` (Zuordnung), `/zahlung`, `/aufgaben`,
`/pruefung` (Befunde, Periodenabschluss), `/einstellungen` außer Sprache und gelernten Regeln.

```
 Browser (Jinja2 serverseitig · HTMX 2.0.11 lokal · pruefen.js für Tasten und Fehlerhinweis · kein Build-Schritt)
    │  Cookie-Sitzung mit 2FA (10a) · CSRF in jedem Formular · CSP ohne Inline-Skript/-Stil
    │  HTMX: 409/422 als Fragment mit Meldung · ohne Sitzung HX-Redirect · CSRF-403 HX-Refresh · 503 Hinweis
    ▼
 api/seiten/  pruefen.py ─ /pruefen, /pruefen/{id}, freigeben · korrigieren · regelvorschau · zurückstellen
              buchungen.py ─ /buchungen/{id} (Storno-Kette, Journal) · korrigieren · stornieren (Einmalcode)
              belege.py ─ /belege/{id}, /datei (PDF/PNG/JPEG inline), /seite/{n}.png (TIFF), /download
              auswertungen.py ─ BWA · SuSa · Kontenblatt · OPOS · /export/{csv|pdf}
              sprache.py ─ POST /einstellungen/sprache
    │  aus 10a: erfordert(Recht.X) → gesellschaft_db → a.gesellschaft (Archiv, Konfig, Regeln)
    │  api/handeln.im_namen(a) → geprueft_als(a.benutzer.name) (7) · api/einmalcode.py (10a, verschoben)
    ▼
 i18n/ ── Katalog en.yaml, Sprachwahl, Zahlen-/Datumsformate (Jinja-i18n, ohne Babel)
    ▼
 Fachfunktionen (CLI und Browser gleich)
   buchung/pruefschlange.py  ── Reihenfolge, Herkunft, Stand (Schnappschuss aus 7, unter der Schreibsperre),
                                freigeben/korrigieren/zurückstellen ─▶ pruefung/storno.py (7)
   klassifikation/lernen.py  ── Entwurf (mit Richtung) · Vorschau · lerne/übernehme → kontierungsregeln (Journal über erfasse)
                                ─▶ lade_regelwerk(s, regeln_datei() | g.regeln, einstellung)
   db/tabellen_kontierung.py ── kontierungsgruende (Herkunft je Buchung, nur anfügen) · kontierungsregeln
   bwa/ (neu gerechnet, Schema je Kontenrahmen, Einklang mit EÜR-Kz, Wirtschaftsjahr) · abschluss/kontenblatt.py
   auswertung/ (Bericht → CSV/PDF) · belege/zuordnung.py · erechnung.lies · belege.erkennung.erkenne_format
```

---

## Kontext und Abgrenzung

### Stand der Grundlage (gelesen am 21.10.2026)

| Stand | Commit | Für 10b maßgeblich |
|-------|--------|--------------------|
| `main` | **3d20af3** | Baustein 10a (#27, c019c2a): `api/`, `auth/`, `betrieb/`, Migration `a684d10751de`; Kontenrahmen-Korrektur (#28): `abschluss/kontenrahmen_skr03.yaml`, `…_skr04.yaml`, `euer_vordrucke.yaml` |
| Baustein 7 | **81d3b51** auf `feat/belegvollstaendigkeit-gobd` (Worktree `.claude/worktrees/agent-a70e9b830283a9e54`, main eingemergt in 398a3a8) | `pruefung/` (Journal, Storno, Perioden, Nachforderung, Prüfregeln, Verfahrensdoku), `befehle.handelnde_person`, `pruefung/skr03.yaml` (vorher `config/skr03.yaml`), Migration `ddc9a184ddb4`, Plan `docs/plans/2026-10-26-belegvollstaendigkeit-gobd.md` |
| Alembic-Kette | — | `… → 33d478b807fc → a684d10751de` (10a: `api_tokens`, `auth_benutzer` **ohne** `sprache`, `auth_ereignisse`, `auth_merker`, `auth_rollen`, `auth_sitzungen`, `auth_wiederherstellungscodes`) `→ ddc9a184ddb4` (7: `journal`, `buchungskorrekturen`, `periodenabschluesse`, `buchungssaetze.storniert_durch/storno_von`, SQLite-Trigger; down_revision `a684d10751de`). **10b-1 hängt an `ddc9a184ddb4`:** `<rev>_add_kontierung` → `<rev>_add_benutzer_sprache`. 10b-2 braucht keine Migration |

Gelesen wurde der Quelltext beider Stände (`git -C /opt/accounti show main:…` bzw. der Worktree),
ohne CLI-Lauf gegen eine Datenbank. Zeilenangaben beziehen sich auf den Stand von 7 (81d3b51), der
nach dem Merge der Stand von `main` ist; Abweichungen zu `main` sind genannt.

### Was 10a liefert (auf `main`)

- **App und Registry:** `erstelle_app(dienste: Dienste) -> FastAPI` (`api/app.py:37`); jedes Modul
  in `api/seiten/` mit `router` (nicht mit `_` beginnend) wird eingehängt, `NAVIGATION` aus
  `Navigationspunkt(titel, pfad, recht=Recht.LESEN, reihenfolge=100)` (`api/registry.py:22–46`);
  `app.state.endpunkte` hält `route.path` **mit** Konverter.
- **Dependencies** (`api/sitzung.py`): `erfordert(recht)` (:135) liefert `Angemeldet` (:69:
  `benutzer`, `sitzung`, `gesellschaft` mit `kuerzel, name, datenbank, archiv, konfiguration,
  regeln`, `gesellschaften`, `rechte`, `csrf`, `darf()`), 403 „Ihre Rolle in … erlaubt das nicht“;
  `gesellschaft_db` (:149) ist ein **synchroner** Generator, liefert die Session der aktiven
  Gesellschaft, committet **nicht** — die Seite committet selbst in ihrer Thread-Funktion.
- **CSRF:** in `angemeldet()` (:118) für alle Methoden außer GET/HEAD/OPTIONS; `pruefe_csrf`
  (:107) liest **zuerst** den Kopf `X-CSRF-Token`, sonst das Feld `csrf`; danach Fetch-Metadata
  (`cross-site` → 403). CSRF-403 und Rollen-403 sind dieselbe `HTTPException(403)` — ohne
  Unterscheidungsmerkmal. `formular()` (`api/formular.py:19`) nur urlencoded, ≤ `max_formular_kb`,
  ≤ 200 Felder; `python-multipart` fehlt.
- **Jinja** (`api/vorlagen.py`): Autoescape, `StrictUndefined`, Filter `betrag`, `datum`, `iban`;
  `seite(request, vorlage, werte=None, status=200)` mit Kontext `angemeldet, csrf, navigation,
  version, titel, meldung, fehler`; **keine** i18n-Erweiterung, kein `Vary`. Vorlagen:
  `anmelden.html`, `basis.html` (`<html lang="de">` fest, Blöcke `titel`, `kopf`, `inhalt`,
  „Gesellschaft: <strong>…</strong>“, CSS ohne Versionsanhang), `freigaben.html`, `meldung.html`,
  `start.html`.
- **CSP** (`api/sicherheit.py:41–45`) wörtlich `default-src 'self'; script-src 'self'; style-src
  'self'; img-src 'self' data:; object-src 'self'; frame-src 'self'; frame-ancestors 'self';
  form-action 'self'; base-uri 'none'`; Kopfzeilen nur, wenn die Antwort sie nicht setzt;
  `no-store` außer `/statisch/`; `/statisch` ohne `Cache-Control` (heuristisch zwischengespeichert);
  unbehandelte Ausnahme → `PlainTextResponse("Interner Fehler", 500)`; das Zugriffsprotokoll
  schreibt die **Routenvorlage**, nicht den Pfad (`protokollpfad`, :29–38). `api/statisch/`
  enthält nur `accounti.css`.
- **Fehlerwege** (`api/app.py`): `nicht_angemeldet` (:67) → `/api/` 401, sonst 303 auf
  `/anmelden?weiter=…` (`weiter` = Pfad nur bei GET, sonst `/`); `http_fehler` (:78) rendert
  `meldung.html` mit `str(fehler.detail)`; `ungueltig` (:94) 422. **Keine** HTMX-Behandlung.
- **Einmalcode im Browser:** `bestaetige_einmalcode(dienste, a, einmalcode)`
  (`api/seiten/freigaben.py:48`): ohne `auth.einmalcode_bestaetigung` nichts, sonst
  `pruefe_zweiten_faktor(…, quelle="web")` in der Systemdatenbank (TOTP oder
  Wiederherstellungscode, Replay-Schutz über `repo_auth.merke_totp_schritt`), Fehler 403 „Einmalcode
  falsch oder schon benutzt“. Genutzt von `/freigaben/zahlungslauf/{nr}` und `/freigaben/ustva`.
  Die 10a-Schnittstelle (Plan 10a, „Schnittstelle für die Web-Oberfläche“) sieht ihn „vor jeder
  Freigabe“ vor — für 10b entschieden unter „Person, Einmalcode, Sperren“.
- **Rollen** (`models/auth.py:32–74`, in 7 unverändert): `LESEN, BUCHEN, BELEGE_EINLIEFERN,
  LAEUFE_STARTEN, BUCHUNG_FREIGEBEN, ZAHLUNG_FREIGEBEN, STEUER_FREIGEBEN, VERWALTEN`; betrachter
  `LESEN`; buchhalter `LESEN, BUCHEN, BELEGE_EINLIEFERN, LAEUFE_STARTEN, BUCHUNG_FREIGEBEN`;
  freigeber `LESEN, BUCHUNG_FREIGEBEN, ZAHLUNG_FREIGEBEN, STEUER_FREIGEBEN`; verwalter `LESEN,
  VERWALTEN`.
- **Auth-Daten** in der Systemdatenbank (`betrieb/kontext.py:74`); weil `Base.metadata`
  gemeinsam ist, legen `init_db` und Alembic die `auth_*`-Tabellen aber in **jeder** Datenbank an.
  `init_db` (= `create_all`, legt Tabellen an, keine Spalten) läuft träge beim ersten Zugriff je
  URL (`api/dienste.py:52–57`). Alembic liest nur `ACCOUNTI_DB` (`alembic/env.py`); wie System-
  und Gesellschaftsdatenbanken einzeln migriert werden, beschreibt `docs/betrieb.md` nicht. Beim
  Start prüft `serve` kein Schema (`api/server.py:39–78` warnt nur bei fehlenden Benutzern oder
  fehlendem Tresorschlüssel).
- **Regeldatei je Gesellschaft:** `betrieb.kontext.regeln_datei()` (:101; Registry `regeln:`, sonst
  `config/regeln.yaml`) in `opos verbuchen` (`cli.py:1460`), `bank lauf` (:2191), `classify`
  (:2249) und `_regel_speichern` (:2379, für `lerne` und `korrigiere --lernen`); im Web
  `a.gesellschaft.regeln` (ohne Registry `regeln.yaml` neben der Konfiguration,
  `api/dienste.py:121`); REST `lade_regeln(g.regeln)` (`api/rest/laeufe.py:43`). Test
  `tests/test_cli_gesellschaft.py:184` `test_regeln_je_gesellschaft_auch_in_der_cli` (`lerne` mit
  `-g b` schreibt in `b-regeln.yaml`).
- **Laufsperre** (`betrieb/laufsperre.py:96`, `LaufLaeuftError`): je Datenbank und Art, wartet nie
  (PostgreSQL Advisory-Lock, SQLite `flock`). CLI über `befehle.laufsperre_oder_ende` (`classify`,
  `opos verbuchen` (7), `opos zuordnen`, `bank abgleich|abrufen`, Karten, FinTS, `periode` (7),
  `nachfordern` (7, Art `aufgaben`)), `bank lauf` direkt; REST `_gesperrt` (`api/rest/laeufe.py:
  129–142`, 409). **Keine Seite** nutzt sie.
- **Sicherung** generisch über `Base.metadata.sorted_tables` (ohne `auth_sitzungen`), nur
  vorhandene Spalten (7: `betrieb/sicherung.py:268`); neue Tabellen sind automatisch dabei.
- **Tests:** `tests/api_hilfe.py` (keine Fixtures; `Webwelt` mit `client()`, `person(name,
  *rollen, gesellschaft="a")`, `token()`, `code()`, `angemeldet(name)`; `csrf(client)`,
  `freigabe_hash()`, `webwelt(tmp_path)` mit zwei Gesellschaften); `tests/test_api_rechte_matrix.py`
  (`SEITEN` = **ein** Wert je Endpunkt; `anfrage()` zieht bei **jedem** Aufruf einen der zehn
  Wiederherstellungscodes der Person); `tests/test_api_gesellschaften.py:36`
  `test_akzeptanz_5_wechsel_aendert_alle_ansichten` (buchhalter jan; jede GET-Seite ohne `{`:
  200 und „Gesellschaft: <strong>Beta Rahmen KG</strong>“); `tests/test_betrieb_protokoll.py`
  (`test_durchlauf_ohne_personenbezogene_inhalte_im_protokoll`); `tests/test_betrieb_sicherung.py`.

### Was 7 liefert (Branch, nach dem Merge auf `main`)

- **Storno** (`pruefung/storno.py`): `freigeben(session, buchung_id, von=None) -> (Buchung,
  geändert)` (:426; Vorschlag **oder `auto`** → `geprueft`); `korrigiere(session, id, soll, haben,
  *, steuer=None, ohne_steuer=False, von=None, grund=None, datum=None, kontenrahmen=None,
  buchhaltung=None, einstellungen=None) -> Korrektur` (:311; Vorschlag direkt, freigegeben Storno +
  Neubuchung; `datum` nur beim Storno); `storniere(session, id, *, grund, von=None, datum=None,
  kontenrahmen=None)` (:286). Ohne Angabe fallen `kontenrahmen` auf `lade_kontenrahmen()` (SKR03),
  `buchhaltung` auf `Buchhaltung()`, `einstellungen` auf `PruefEinstellungen()` (mitgelieferte
  `pruefung/skr03.yaml`), `von` auf `aktuelle_person()` (`ACCOUNTI_BENUTZER`, sonst Anmeldename
  des Prozesses) zurück. Prüfungen: Sachkontowechsel einer Buchung mit Schlüssel verlangt
  `steuer` oder `ohne_steuer` (`_pruefe_ausdruecklich`, :121); bei Belegbuchungen kein anderer
  Schlüssel, `ohne_steuer` nur mit Grund, nie für ausgewiesene USt 2/3 (§ 14c Abs. 1 UStG,
  `_steuer`, :149); DATEV-Automatikkonto ohne Schlüssel und Fehler der Prüfregel
  `steuerschluessel_konto` werden abgelehnt (`_pruefe_steuerschluessel`, :386); Storno nur
  freigegebener, nicht stornierter Buchungen, nicht von Stornobuchungen (`_nicht_storniert`, :103);
  gesperrter Zeitraum verlangt `datum` (`_stornodatum`, :200); Warnung bei Storno in anderem
  Voranmeldungszeitraum (:270). Alle Fehler als `StornoError` mit Meldungen, die CLI-Optionen
  nennen (`--steuer`, `--ohne-steuer`, `--datum`).
- **Sperren:** `_pruefe_festschreibung` (`pruefung/ereignisse.py:365`) erlaubt an freigegebenen
  Buchungen nur `status` (erlaubte Wege), `geprueft_von` (nur `auto` → `geprueft`) und einmal
  `storniert_durch`; Jahres- und Monatssperre (`PeriodeGesperrtError(JahrGesperrtError)`,
  `db/tabellen_pruefung.py:137`), `perioden.sperre_am(session, tag) -> Sperre(art, zeitraum,
  text) | None` (:65); `perioden.schliesse` verlangt **keine Vorschläge** im Monat. Fehlerklassen:
  `StornoError`, `JahrGesperrtError`, `UnveraenderbarError` (Oberklasse von
  `BuchungFestgeschriebenError`).
- **Journal** (`pruefung/journal.py`): `journal_kontext(person, grund, bezug)`
  (`pruefung/person.py:47`, ContextVar, innen gewinnt); Person eines Eintrags =
  `Vorgang.person or kontext().person or aktuelle_person()` (:199) — **die Storno-Funktionen setzen
  einen eigenen inneren Kontext mit `aktuelle_person(von)`**, ein äußerer `journal_kontext` allein
  genügt dort also nicht. `schreibsperre(verbindung)` (:132) holt jeder Flush (`before_flush`,
  `ereignisse.py:459`) und jedes `schreibe`; `lesestand` (:562) für konsistentes Lesen;
  `schnappschuss(tabelle, zeile, ohne=())` (:94), `kanonisch()` (:54); Abgleich feldweise
  (`_unterschiede`, :381; eine neue Spalte mit `NULL` in Altzeilen ist **kein** Befund); `BESTAND`
  (:296) = `buchung`, `beleg`; Journaleinträge entstehen nur für Tabellen, die mit
  `erfasse(tabelle, Erfassung(objekt_typ, einordnen))` (`ereignisse.py:110`) angemeldet sind;
  `schreibe()` für Vorgänge ohne eigene Zeile. Nur-anfügen-Tabellen: ORM-Sperre
  (`UnveraenderbarError`), SQLite-Trigger über `after_create` **und** in der Migration,
  Massenwege gesperrt über `db.GESCHUETZT` (`buchungssaetze`, `journal`, `buchungskorrekturen`).
- **CLI mit Recht und Einmalcode:** `befehle.handelnde_person(db, config, recht, von)` prüft mit
  eingerichteten Benutzern Rolle **und** Einmalcode (`auth/cli.pruefe_recht_in`, TOTP/Wiederherstellungscode,
  für Skripte `ACCOUNTI_EINMALCODE`) und setzt den Benutzer in `journal_kontext`. `bestaetige` →
  `BUCHUNG_FREIGEBEN` (`cli.py:2478`), `korrigiere` → `BUCHEN` (:2545), `buchung storniere` →
  `BUCHEN` — Begründung im Plan 7: wer buchen darf, darf freigeben (Test
  `tests/test_cli_rechte_pruefung.py::test_buchen_umfasst_die_freigabe`), zwei Prüfungen verlangten
  zwei Einmalcodes. `review` ohne Recht. `accounti buchung zeige` nutzt `repo_pruefung.korrektur_zu`
  und `journal.lade_journal(objekt_id=…)`.
- **Belegnachforderung** (`pruefung/nachforderung.py`): Prüflauf `beleg_fehlt` an
  `Objekt("transaktion", id)` mit Schwellen und `belegfrei`-Mustern
  (`PruefEinstellungen.belegfrei_nach_regel`); Anfrage an den Lieferanten nur per
  `accounti nachfordern anfrage TX --senden`.
- **Wieder offen nach reinem Storno:** `repository.gebuchte_transaktion_ids` (:988) zählt ein
  Storno-Paar am selben Umsatz nicht — der nächste Lauf kontiert den Umsatz neu.
- **Weiteres:** `pruefung/skr03.yaml` (42 Konten mit DATEV-Namen, Automatik, Schlüsselnamen; dazu
  43 × `bwa_zeile` der **alten** 23-Zeilen-BWA, die niemand liest), `pruefung/verfahrensdoku.py`
  (Kontierung liest die Regeln fest aus `config/regeln.yaml`, :258), `betrieb/aufbewahrung.BESTAND`
  (Tabellenliste mit Fristart, 7 ergänzt Journal, Korrekturen, Monatsabschlüsse),
  `opos/verbuchung` mit Option `buchungsdatum` (Hinweise nur ausgegeben, nicht gespeichert),
  Migrationstest `tests/test_migration_belegvollstaendigkeit.py` (Alembic als Unterprozess, auch
  „übernimmt, was `init_db` schon anlegte“), `tests/pruefung_hilfe.py`, `tests/pg_hilfe.py`
  (PostgreSQL über `ACCOUNTI_TEST_PG`).

### Bereits erledigt — nicht neu bauen

| Thema | erledigt durch | 10b tut nur |
|-------|----------------|-------------|
| Storno statt Änderung, Korrektur, Freigabe, Sperren, Journal | 7 | ruft `pruefung/storno.py`; strukturiert die Fehler für Formulare (`StornoError.feld`), legt den Kontenrahmen-Lader für CLI und Web zusammen |
| Rechte und Einmalcode in der CLI (`bestaetige`, `korrigiere`, `buchung storniere`) | 7 (`handelnde_person`) | erweitert um mehrere Rechte mit einem Code (`korrigiere --lernen`), neue Befehle `lerne`, `regeln …` nutzen dasselbe |
| Person im Journal für REST | 7 (`Zugang.person`, `journal_kontext` in `rest/laeufe.py`, `rest/belege.py`) | Seiten setzen `journal_kontext` aus der Sitzung |
| `buchung zeige` (Storno-Kette, Korrektur, Journal) | 7 | `/buchungen/{id}` mit denselben Funktionen |
| Monats- und Jahressperre, `sperre_am` | 7, 12 | Anzeige und Fehlerwege im Web, Hinweis in den Auswertungen; **keine** Seite zum Festschreiben |
| Belegnachforderung, `belegfrei`-Regeln | 7 | Anzeige in der Arbeitsfläche |
| Laufsperre in CLI und REST | 10a, 7 | nichts an den Sperren; Regelwerk wird nach der Sperre in der Sitzung geladen |
| Einmalcode im Browser | 10a (`bestaetige_einmalcode`) | verschiebt die Funktion nach `api/einmalcode.py`, nutzt sie für `/buchungen/{id}` |
| Auth-Migration, Journal-Migration | 10a (`a684d10751de`), 7 (`ddc9a184ddb4`) | zwei Migrationen dahinter |
| Sicherung neuer Tabellen | 10a/7 (generisch) | nur Rundlauftest mit den neuen Tabellen und Triggern |
| Regeldatei je Gesellschaft | 10a (`regeln_datei()`, `g.regeln`) | kein eigener Pfad |
| Kontenrahmen mit Kontoarten und EÜR-Kennzahlen | 12, berichtigt in #28 | BWA-Schema daran ausgerichtet und dagegen getestet; neuer Schlüssel `ergebnisverwendung` |
| Prüfregel `steuerschluessel_konto`, Automatikkonten | 7 | wirkt über `storno.korrigiere`, sofern das Web `lade_pruefung(g.konfiguration)` übergibt |
| Rechte-Matrix, Akzeptanz-5-Test, Protokolltest, Testwelt | 10a | erweitert |

### Abgleich mit dem neuen Stand (Fassung 2 → Fassung 3)

| # | Fassung 2 nahm an | Stand jetzt (Beleg) | Folge in Fassung 3 |
|---|-------------------|---------------------|--------------------|
| A1 | 10a liegt auf `feat/auth-betrieb-api` | auf `main` (#27, c019c2a) | Abzweigen von `main` nach dem Merge von 7 |
| A2 | „Noch keine Alembic-Migration für die Auth-Tabellen“ | `a684d10751de` existiert, 7 kettet `ddc9a184ddb4` daran | 10b-Migrationen auf `ddc9a184ddb4`, idempotent wie diese (Tabellen/Spalten/Trigger, die `init_db` schon anlegte, werden übernommen); Test „ein Kopf“ |
| A3 | Spalte `sprache` nur in der Systemdatenbank | `auth_benutzer` liegt wegen der gemeinsamen Metadaten in **jeder** Datenbank; Alembic nur über `ACCOUNTI_DB` | Migration läuft in jeder Datenbank; Schemaprüfung beim Start nur gegen die Systemdatenbank (`api/server.starte_aus_cli`); Doku-Baustein „jede Datenbank migrieren“ |
| A4 | Person im Web über `von=` und `journal_kontext` | Storno-Funktionen setzen einen inneren Kontext mit `aktuelle_person(von)`; alle anderen Schreibwege (Rückfrage, Regel, Grund) lesen den äußeren Kontext | beides: `von=a.benutzer.name` an jede Fachfunktion **und** `api/handeln.im_namen(a)` um jede schreibende Thread-Funktion; Test über alle POST-Endpunkte mit `ACCOUNTI_BENUTZER=mallory` |
| A5 | Buchungsfreigaben im Browser ohne Einmalcode „wie `accounti bestaetige`“ | `bestaetige`, `korrigiere`, `buchung storniere` verlangen in der CLI Recht **und** Einmalcode (7); die 10a-Schnittstelle sieht Einmalcode „vor jeder Freigabe“ vor | Queue (Vorschläge) ohne Code in der 2FA-Sitzung, Storno/Korrektur freigegebener Buchungen auf `/buchungen/{id}` **mit** Code — Begründung unter „Person, Einmalcode, Sperren“ |
| A6 | Korrigieren braucht `BUCHEN` **und** `BUCHUNG_FREIGEBEN` | 7: `BUCHEN` genügt, Invariante getestet (`test_buchen_umfasst_die_freigabe`) | Web wie CLI: `BUCHEN`; Matrix braucht dafür keine Mengen mehr (nur noch `EinesVon` fürs Zurückstellen) |
| A7 | `korrigiere(…, kontenrahmen, buchhaltung)` | zusätzlich `einstellungen: PruefEinstellungen`; Meldungen mit CLI-Optionen | Web übergibt `lade_pruefung(g.konfiguration)`; `StornoError` bekommt `meldung`, `feld`, `cli`; `storno.steuer_optionen(b, beleg)` für das Formular (Runde 7: mit dem Schlüssel laut Beleg) |
| A8 | Web nimmt `lade_abschluss(pfad).lade_kontenrahmen()` | CLI `korrigiere`/`buchung storniere` nehmen `lade_kontenrahmen(buchhaltung.kontenrahmen)` (ohne `abschluss.kontenzuordnung`), SuSa/Abschluss mit | ein Lader `storno.lade_korrekturumgebung(pfad)` für CLI und Web (mit Kontenzuordnung) |
| A9 | `stand` aus dem Schnappschuss | Schreibsperre erst beim ersten Flush | `pruefschlange` holt `schreibsperre` **vor** dem Lesen und Vergleichen des Stands |
| A10 | Befund 4: neue Spalte bricht den Journalabgleich | Abgleich feldweise, `NULL` in Altzeilen zählt nicht; aber `_pruefe_festschreibung` sperrt jede andere Spalte freigegebener Buchungen, und jeder Journaleintrag einer Buchung trüge die Begründung erneut | eigene Tabelle bleibt; Begründung neu formuliert |
| A11 | `kontierungsgruende.buchung_id` als Primärschlüssel mit Bezug | `bank/kreditkarte._loese` löscht vorläufige Buchungen (`repo_bank.loesche_buchung`) — mit Fremdschlüssel und Nur-anfügen scheiterte das | `id` als Schlüssel, `buchung_id` indiziert **ohne** Fremdschlüssel (wie `journal.objekt_id`); neuester Grund gilt |
| A12 | Regeln „über `erfasse`“ ins Journal | nur angemeldete Tabellen schreiben Einträge, nur `BESTAND` wird abgeglichen; Nur-anfügen braucht ORM-Sperre, Trigger, `GESCHUETZT` | `kontierungsregeln`: `erfasse` + `BESTAND` + `GESCHUETZT`, Änderung nur `aktiv` → aus; `kontierungsgruende`: Trigger + ORM-Sperre + `GESCHUETZT`, nicht im Journal |
| A13 | Periodenabschluss nur über `sperre_am` beim Storno-Datum | Monatssperre, Schließen ohne Vorschläge, `PeriodeGesperrtError` | Queue-Eintrag zeigt eine Sperre statt Aktionen; `/buchungen` verlangt Datum; Auswertungen zeigen, ob der Monat festgeschrieben ist |
| A14 | Laufsperre nicht betrachtet | CLI/REST-Läufe sperren; Seiten starten keine Läufe; SQLite wartet bis 30 s (`session_factory`, 7) | 10b-Seiten nehmen keine Laufsperre (wie `bestaetige`); `OperationalError` „database is locked“ → 503 mit Hinweis; Regelwerk erst nach der Laufsperre laden |
| A15 | Ansicht „ohne Beleg“ | Belegnachforderung (`beleg_fehlt`) und `belegfrei`-Regeln aus 7 | Arbeitsfläche zeigt offene Nachforderung bzw. „belegfrei nach Regel …“ |
| A16 | Entscheidung schließt nur die Rückfrage | Baustein 8 legt je unsicherer Buchung eine Aufgabe `kontierung_pruefen` an (`aufgaben/prueflaeufe.py:129`) | Entscheidung schließt auch diese sofort (`schliesse_wenn_erledigt`) |
| A17 | `config/skr03.yaml` mit `bwa_zeile` „veraltet“ kennzeichnen | verschoben nach `src/accounti/pruefung/skr03.yaml`; `bwa_zeile` folgt der alten 23-Zeilen-Nummerierung, kein Leser; `models.Konto.bwa_zeile` tot | `bwa_zeile` aus der Datei und `models.Konto` **entfernen**; README-Abschnitt „Kontenrahmen & Steuer“ anpassen |
| A18 | Startzuordnung „gegen Kontenlisten vom 20.10.2026 abgeglichen“ | #28: SKR03 3990–3999 jetzt Erfolg; EÜR-Kz verfeinert (Erlösschmälerungen 112, Ergebnisverwendung „-“, Forderungsverluste 112, …) | Startzuordnung neu (Lücke 3990–3999, Ergebnisverwendung, rund 20 Zeilen an EÜR und das SKR-Gegenstück angeglichen), per Skript gegen #28 geprüft; Konsistenztest BWA ↔ EÜR; `ergebnisverwendung` im Kontenrahmen |
| A19 | „Konto mit Bezeichnung aus dem Kontenrahmen“ | `Kontenrahmen.namen` kennt 45 (SKR03) bzw. 26 (SKR04) Konten, `pruefung/skr03.yaml` 42 | Bezeichnung aus beiden Quellen, sonst nur die Nummer (Grenze) |
| A20 | Rechte-Matrix nur um Mengen erweitern | `anfrage()` verbraucht je Aufruf einen von zehn Wiederherstellungscodes | Code nur noch für Endpunkte mit Einmalcode ziehen |
| A21 | CSRF-403 → `HX-Refresh` | CSRF- und Rollen-403 nicht unterscheidbar | `angemeldet()` setzt `HX-Refresh` am CSRF-Fehler selbst |
| A22 | ohne Sitzung `HX-Redirect: /anmelden?weiter=<Pfad>` | `weiter` = Pfad nur bei GET | bei HTMX `weiter` aus `HX-Current-URL` (nur Pfad, nur eigene Herkunft) |
| A23 | Verfahrensdoku nicht betrachtet | 7 nennt nur die Regeln aus `config/regeln.yaml` | Verfahrensdoku 2.3: Regeldatei der Gesellschaft, gelernte Regeln, Schalter |
| A24 | Aufbewahrung nicht betrachtet | `aufbewahrung.BESTAND` listet die Tabellen | `kontierungsgruende` und `kontierungsregeln` eintragen |
| A25 | Herkunft aus sieben Quellen | dazu `anlagen/dienst.py:195–206` (Umbuchung Anlagenzugang, zur Prüfung) und `integrationen/buchung.py:202–218` (Marktplatz-Abrechnung) | beide schreiben einen Grund; `opos/verbuchung` speichert auch den Hinweis zum Buchungsdatum |
| A26 | ein neuer Leser `lade_wirtschaftsjahr_beginn` | drei Leser (`befehle/betrieb._wirtschaftsjahr_beginn`, `befehle/gesellschaft._wirtschaftsjahr`, `export/datev_stammdaten`), Zeitraum schon in `betrieb.aufbewahrung.wirtschaftsjahr(tag, beginn)` | `befehle/betrieb._wirtschaftsjahr_beginn` nach `konfiguration.py` herauslösen, alle drei nutzen ihn; Zeitraum über die vorhandene Funktion |
| A27 | `accounti bwa --period` bekommt `--csv/--pdf` | `bwa`, `opos liste`, `opos staffel` haben kein `--config` (`bwa` auch kein `--db`) — `--gesellschaft` greift dort nicht | `--db`/`--config` ergänzen |
| A28 | CLI-Läufe laden das Regelwerk | `classify`, `bank lauf` bauen die Engine **vor** Sitzung und Laufsperre | `lade_regelwerk` in der Sitzung nach der Laufsperre |
| A29 | htmx 2.0.11 | unverändert `latest`, Werte erneut nachgerechnet (Recherche) | — |

### Abgleich mit `main` ec32890 (Umsetzung PR 10b-1, 21.10.2026)

Fassung 3 las Baustein 7 bei 81d3b51; `main` (ec32890, 7 als #29) bringt danach u. a.
`FREIGABEWEGE`, die Kennzeichnung „(ungeprüft)“, `geprueft_als`, die Rechtebindung von
`opos bestaetigen|ablehnen`, `bank bestaetigen|ablehnen`, `export datev`, die Schreibsperre bei
UPDATE/DELETE unter PostgreSQL und weitere Storno-Prüfungen. Gelesen mit
`git diff 81d3b51 ec32890 -- src/`; Alembic-Kopf unverändert `ddc9a184ddb4`.

| # | Fassung 3 nahm an | Stand `main` ec32890 | Folge |
|---|-------------------|----------------------|-------|
| B1 | `im_namen(a)` = `journal_kontext(person=a.benutzer.name)` | `fuege_an` kennzeichnet Personen ohne `geprueft=True` als „(ungeprüft)“, sobald die Datenbank an eine Benutzerverwaltung gebunden ist (`journal.benutzer_eingerichtet`); 10a-Freigaben nutzen `pruefung.person.geprueft_als(a.benutzer.name)` | `im_namen(a)` = `geprueft_als(a.benutzer.name)`; die Storno-Funktionen setzen innen `journal_kontext(person=von)` mit **derselben** Person — `geprueft` bleibt dann erhalten (`person == alt.person`). Test: gebundene Datenbank, jeder Web-Eintrag ohne „(ungeprüft)“ |
| B2 | Recht `REGELN_LERNEN` nur in `Recht`, `RECHT_TEXT`, `ROLLEN_RECHTE` | `models.auth.FREIGABEWEGE` listet je Recht die gebundenen CLI-Befehle (Verfahrensdoku 2.x) | Eintrag `Recht.REGELN_LERNEN: ("lerne", "korrigiere --lernen", "regeln deaktivieren\|uebernehmen")` |
| B3 | Stellen von `raise StornoError` wie bei 81d3b51 | neu: `--ohne-steuer` bei § 13b/ig. Erwerb (`SELBST_BERECHNET`) nur mit Grund, Warnung `_warnung_selbst`, gleichzeitiges Storno (`IntegrityError` → `StornoError`) | `steuer_optionen` kennt „ohne Steuer nur mit Grund“ auch für 18/19/91/94 (Hinweis `HINWEIS_SELBST_BERECHNET`); die neuen Stellen bekommen `meldung`/`feld` |
| B4 | `StornoError(meldung, *, feld, cli)` mit `str() = meldung + cli` | die CLI-Optionen stehen in den Texten aus 7 **mitten im Satz** („… bestätigen mit --steuer 9 oder entfernen mit --ohne-steuer“) — Anhängen ergäbe nicht den bisherigen Wortlaut | `cli` ist der **vollständige** bisherige Text, `meldung` die Fassung ohne Optionen; `str()` liefert `cli` (sonst `meldung`) — Wortlaut der CLI und der Tests aus 7 unverändert |
| B5 | `bank_lauf(s, engine, einstellungen)` | `bank_lauf(…, sichern=s.commit)` in CLI und REST (Zwischencommit nach dem Abruf) | Regelwerk wird vor `bank_lauf` in derselben Sitzung geladen; an `sichern` ändert sich nichts |
| B6 | REST setzt `journal_kontext(person=zugang.person)` | `zugang.journal()` (geprüft) | nichts zu tun; Akzeptanz 2 erwartet „API-Token erp“ ohne „(ungeprüft)“ |
| B7 | Schreibsperre nur für erfasste/geschützte Tabellen | unter PostgreSQL holt jeder Flush mit UPDATE/DELETE die Sperre (`ereignisse._braucht_sperre`) | `kontierungsgruende`/`kontierungsregeln` stehen in `GESCHUETZT` bzw. `ERFASST` und holen sie ohnehin; keine Änderung |
| B8 | Migrationstest von 7 bleibt unberührt | `test_migration_belegvollstaendigkeit.py::test_downgrade_und_wieder_hinauf` geht mit `downgrade -1` vom Kopf aus — nach 10b nimmt das nur die Sprachspalte zurück | **umgestellt:** `downgrade a684d10751de` (der Stand vor 7), Absicht unverändert |
| B9 | `journal.BESTAND` nur mit vorhandenen Tabellen | Bestandsabgleich liest jede Tabelle aus `BESTAND` | Abgleich überspringt Tabellen, die (vor der Migration) fehlen — `kontierungsregeln` ist in Altdatenbanken noch nicht da |

### Zusammenführen mit `main` 339a30a (26.10.2026, nach der gegnerischen Prüfung)

`main` bringt seit ec32890 Kontenrahmen (#28/#30), Paket B „Kontierung“ (#31), Paket A
„Betrieb“ (#32), Paket F „Abschluss“ (#33) und Paket D „Debitoren“ (#34). Zusammengeführt per
Merge (kein Rebase):

| # | Stelle | Lösung |
|---|--------|--------|
| M1 | `Regel.richtung` (B) und gelernte Regeln mit `Richtung` (10b) | ein Modell `engine.Regel`: Werte `ausgabe`/`einnahme` (= `Richtung.value`, „beide“ = ohne), `passt` = Muster **und** Richtung, `passt_muster`/`passt_richtung` einzeln (ohne Betrag: Richtung passt), `pruefen`, `confidence`, `hinweis`; `RegelwerkEngine.gegenrichtung` (Muster passt, Richtung nicht) gilt auch für gelernte Regeln; `regel_aus_db` setzt bei `gelernte_regeln: pruefen` das Prüfkennzeichen |
| M2 | Lader des Regelwerks | `lernen.lade_regelwerk(…, buchhaltung=)` — gelernt → Regeldatei → `standard_regeln(kontenrahmen, bank_konto)`; CLI (`classify`, `bank lauf`, `opos verbuchen`), REST und Regelvorschau nutzen ihn; die CLI prüft die Regeldatei vorher (`KonfigurationError` → Exit 1), die Regelvorschau übergeht eine fehlerhafte Regeldatei |
| M3 | Schranke des Mappers | gilt für jede Quelle; `mapper.bankseite` zeigt, ob sie eingreift — dann steht es in der Begründung (`kontierungsgruende`); Belegbuchungen gehen auch bei `pruefen` einer Regel zur Prüfung |
| M4 | `pruefung/storno.py` | `StornoError` mit Feld und CLI-Text auch für „Storno nie vor dem Original“ (`feld="datum"`); `steuer_optionen`, `lade_korrekturumgebung` unverändert, `korrigiere`/`storniere` mit `mit_eingerichteten_konten` |
| M5 | Migrationen | `d5a849692843` hängt an `a14acef69fae` (vorher `ddc9a184ddb4`), `e7153706b43a` dahinter; `SCHEMA_STAND = "e7153706b43a"`; Tests gehen auf feste Revisionen zurück; `db upgrade` erkennt den Stand ohne Vermerk vor jeder der beiden; `serve` nennt bei fehlender Migration `accounti db upgrade` |
| M6 | i18n | `main` bringt keine neuen Texte in die Vorlagen oder `api/`; Fachmeldungen (Begründungen, Storno, Prüfregeln) bleiben deutsch wie bisher; geändert (DE und EN): der Hinweis der Startprüfung und „Gegenrichtung …“ in der Regelvorschau |
| M7 | Akzeptanz 2, Erstattung derselben Gegenpartei | bisher offen; jetzt höchstens die Gegenbuchung der gelernten Regel zur Prüfung (1200 an 4930, wie jede Regel mit Richtung) — Regelvorschau „Gegenrichtung (höchstens als Gegenbuchung zur Prüfung)“; kein Geldabgang |

### Browser-Spike (21.10.2026, vor Paket 3)

Durchgeführt mit einer Wegwerf-App (Middleware `api/sicherheit.Sicherheit` aus 10a, htmx 2.0.11
aus dem Tarball, `htmx-config` wie unter „HTMX“, eigenes Fehlerskript) auf 127.0.0.1, gesteuert
mit Playwright 1.59.1 (lokal vorhanden; der Playwright-MCP-Server startet als root kein Chromium
ohne `--no-sandbox`). **Browser:** Chromium-Build 1223 (neuer Headless-Modus) und
`chrome-headless-shell` 1223. **Firefox ist auf dem Server nicht vorhanden — die Firefox-Probe
bleibt offen (Browserprobe beim Nutzer).**

| Frage | Ergebnis Chromium |
|-------|-------------------|
| (1) PDF im `<iframe>`, Antwort-CSP = Seiten-CSP mit `form-action 'none'` | Betrachter lädt und zeigt das PDF (Seitenleiste, Text sichtbar) |
| (1) strengere Antwort-CSP `default-src 'none'; object-src 'self'; form-action 'none'` | Betrachter lädt ebenso |
| (1) `chrome-headless-shell` | zeigt PDFs nie an (kein Betrachter) — für die Probe ungeeignet, kein Befund |
| (2) 409 und 422 mit Fragment | eingetauscht (`responseHandling` `409\|422` mit `swap:true, error:false`) |
| (2) 500 und 503 | nicht eingetauscht, `htmx:responseError` → versteckter Hinweis wird sichtbar (Status im Hinweis) |
| (2) CSP-Meldungen in der Konsole | keine (kein `eval`, kein Indikatorstil, keine Inline-Skripte); nur die üblichen „Failed to load resource“ je 4xx/5xx |
| (3) ohne Sitzung: 200 mit `HX-Redirect: /anmelden?weiter=…` | ganze Seite navigiert zur Anmeldung, `weiter` bleibt erhalten |
| CSRF-403 mit `HX-Refresh: true` | Seite lädt neu |

**Entscheidung:** Belegdateien (PDF) bekommen die Seiten-CSP mit `form-action 'none'` statt
`form-action 'self'` (Variante A). Die strengere Variante B funktioniert in Chromium, ist aber
ohne Firefox-Probe nicht belegt — sie wird erst nach der Firefox-Probe erwogen (Grenze).
`test_pdf_inline_mit_sicheren_kopfzeilen` prüft Variante A.

### Bestandsaufnahme — was die Oberfläche nicht einfach anzeigen kann

| # | Befund (Quelltext, Stand 7) | Folge für 10b |
|---|-----------------------------|---------------|
| 1 | **Die BWA ist ein Gerüst:** `bwa/berechnung.py` berechnet Summenzeilen nicht („TODO: Formelparser“, :184, Summen immer 0,00 :185–186), `betrag_kumuliert` = Monat (:192), kein Vorjahr, Soll und Haben werden addiert statt saldiert (:164–170), überlappende Bereiche werden **addiert** (4300–4399 ⊃ 4360–4399, :55–62; 7000–7299 ⊃ 7100–7199, :87–94), die Neutral- und Steuerzeilen nehmen **SKR04-Nummern** (7100, 7300, 7600) im SKR03-Schema (:83–106) — dort ist Klasse 7 Bestand (`kontenrahmen_skr03.yaml:52`), Schuldzinsen liegen bei 2100–2149 (:189), Zinserträge in 2600–2799 (:143); Zeile 1 lässt 8200–8299 aus (:21), Zeile 4 schließt die Bestände 3970–3989 ein; SKR04 wirft `NotImplementedError` (:127–132); `accounti bwa` ist ein Platzhalter (`cli.py:2283–2291`, main :2258–2266); kein Test. README („✅ BWA“, :107) und Spec 4.3 („Berechnung liegt in `bwa/` bereits vor“, :78) stimmen nicht | Paket 4 baut die BWA als Fachfunktion neu (Schema je Kontenrahmen, „engste Spanne gewinnt“, Startzuordnung, Leitkonten, Einklang mit den EÜR-Kennzahlen, Vorjahr, Wirtschaftsjahr, aus `abschluss.salden.lade_bewegungen`) und ersetzt den Platzhalter |
| 2 | Kein Kontenblatt, nirgends | Paket 4: `abschluss/kontenblatt.py` + CLI |
| 3 | **Die Begründung wird verworfen:** `buchung/mapper.zu_buchungssatz` übernimmt aus `Klassifikationsergebnis` weder `begruendung` noch `quelle` (`mapper.py:46–57`); `buchung/mit_beleg.Sachkonto.quelle` (:36–40) ebenso (:163–184), dazu `opos/verbuchung._sachkonto_eingang` (:144–152). Architekturprinzip 2 („jede Buchung speichert ihre Herkunft … und welche Begründung die KI gegeben hat“) ist nicht erfüllt | Paket 1: Tabelle `kontierungsgruende`, geschrieben von jeder Quelle (Befund 14) |
| 4 | **Eine Spalte an `buchungssaetze` passt nicht:** Der Journalabgleich vergleicht feldweise und übersieht `NULL` in Altzeilen (`journal._unterschiede`, :381) — aber `_pruefe_festschreibung` (`ereignisse.py:365`) lässt an freigegebenen Buchungen nur `status`, `geprueft_von`, `storniert_durch` zu, jeder Journaleintrag einer Buchung (angelegt, freigegeben, exportiert, storniert) trüge Herkunft und bis zu 500 Zeichen Begründung im Vorher/Nachher erneut, und Plan 7 beschränkt `models.Buchungssatz` auf die Storno-Felder | Herkunft in eigener Tabelle, nur anfügen |
| 5 | **Die Lernschleife lebt in `cli.py`** (`_regel_speichern` :2365–2400, `lerne` :2404–2413, `_lerne_sachkonto` :2518–2541, Musterableitung in `korrigiere` :2649–2662) — die Oberfläche müsste sie kopieren. Die Regel geht über `regeln_datei()` in die Datei der Gesellschaft, wird aber **ans Ende** gehängt, und es gilt „die ERSTE passende Regel gewinnt“ (`config/regeln.yaml:3`, `engine.py:117`) — hat eine frühere Regel falsch kontiert, greift die gelernte nie; `yaml.safe_dump` löscht alle Kommentare; im Container ist `config/` schreibgeschützt; die Sicherung umfasst Datenbank und Archiv, nicht `config/` (`betrieb/sicherung.py:1`). `RegelwerkEngine.regel_hinzufuegen` (Position 0, `engine.py:132–134`) nutzt nur ein Test. 7 lernt beim Sachkontowechsel den Schlüssel der Neubuchung (`test_korrigiere_lernt_den_schluessel_der_neubuchung`) | Paket 1: `klassifikation/lernen.py`; gelernte Regeln (auch aus `accounti lerne`) in der Datenbank der Gesellschaft, mit Vorrang; `accounti regeln uebernehmen` holt alte `gelernt_*` |
| 6 | Zwei Aufrufer, dieselbe Datei: CLI `regeln_datei()` (`cli.py:1460`, :2191, :2249), REST `g.regeln` (`api/rest/laeufe.py:43`); keine Datenbankregeln | ein Lader `lade_regelwerk(session, regeldatei, einstellung)`; die CLI übergibt `regeln_datei()`, Web und REST `g.regeln` — **kein eigener Ausweichpfad** |
| 7 | `lade_pruefliste` (`repository.py:191–207`) ohne Reihenfolge, nur `zur Prüfung`; `finde_buchung` (:225) sucht per `LIKE '<präfix>%'` (:210–222), ebenso `storno._lade` (:92) und der Aufgaben-Objekttyp „buchung“ | Prüfschlange mit fester Reihenfolge; im Web nur volle UUIDs (Pfadkonverter `uuid`) — ein voller UUID-Text als „Präfix“ ist eindeutig |
| 8 | Standardwerte der Storno-Funktionen (Kontenrahmen SKR03, `Buchhaltung()`, `PruefEinstellungen()`, `aktuelle_person()`; siehe „Was 7 liefert“) | Web übergibt **immer** `lade_korrekturumgebung(g.konfiguration)` und `von=a.benutzer.name`; Test mit SKR04-Gesellschaft, eigenem Bankkonto und eigener Kontenrahmen-Datei |
| 9 | Kein Zustand „zurückgestellt“ (`BuchungStatus`: entwurf, auto, pruefung, geprueft, korrigiert, exportiert — `models/__init__.py:37–45`) | Rückfrage als Aufgabe aus Baustein 8 (`halte_rueckfrage_fest`, `aufgaben/erzeugung.py:448`) |
| 10 | HTMX ist nicht ausgeliefert (`api/statisch/` nur `accounti.css`), obwohl Spec 5 „FastAPI + Jinja2 + HTMX“ festlegt | Paket 2 liefert HTMX lokal aus |
| 11 | `test_akzeptanz_5_wechsel_aendert_alle_ansichten` ruft **jede** GET-Seite ohne Pfadparameter als buchhalter auf und erwartet 200 und „Gesellschaft: **Name**“ | Seiten ohne Parameter liefern 200 (Auswahl statt Fehler) und brauchen `LESEN`; Exporte haben Pfadparameter |
| 12 | `Rechnung` (E-Rechnung) liest keine eingebetteten Anlagen (BT-125) | Anzeige ohne Anlagen (Grenze) |
| 13 | **Regeln kennen keine Zahlungsrichtung:** `Regel.passt` prüft nur das Muster (`engine.py:44–54`), `zu_buchungssatz` nimmt `abs(betrag)` (`mapper.py:30`) und bucht ab 0,95 automatisch (:41–42). Eine aus einer Ausgabe gelernte Regel bucht die **Erstattung** derselben Gegenpartei als Geldabgang, mit Confidence 1,0 im Status `auto` | gelernte Regeln tragen `richtung` aus dem Vorzeichen des Quellumsatzes; `Regel(richtung=…)` auch für `regeln.yaml` (optional) |
| 14 | **Die Queue enthält mehr als Kontierungsvorschläge:** `zur Prüfung` buchen auch Kreditkarte (`bank/kreditkarte.py:923–940`, :1042–1057), Anlagen (`anlagen/lauf.py:199–229`, `anlagen/abgang.py:127`, :154, **`anlagen/dienst.py:195–206`**), Marktplatz (`integrationen/auszahlung.py:309–324`, **`integrationen/buchung.py:202–218`**) und `opos/verbuchung.py:321–371` (Confidence 0,5 bei `pruefen`). Gründe stehen teils schon anderswo: `AfaVorgang.begruendung` (`db/tabellen_anlagen.py:49`), `Beleg.pruef_grund` (`db/tabellen.py:105`), `Kontakt.pruef_grund` (:236), `Zahlungszuordnung.begruendung` (:276), `Belegabgleich.begruendung` (:308) | `lade_eintrag` liefert die Herkunft für jede Quelle; Regelangebot nur für Kontierungsvorschläge; Ansicht „weder Umsatz noch Beleg“ |
| 15 | **htmx tauscht 4xx/5xx nicht ein:** In 2.0.11 gilt `responseHandling` = `[45]..` → `swap:false` (`htmx.js:264–268`, :4899–4900). `HX-Location`/`HX-Refresh`/`HX-Redirect` wertet htmx **vor** `responseHandling` aus (:4867–4887); XHR folgt einer 303 still | `responseHandling` im `htmx-config`, Fehlerfragmente mit 409/422, `HX-Redirect` ohne Sitzung, `HX-Refresh` bei CSRF-403 |
| 16 | **Wirtschaftsjahr je Gesellschaft gibt es schon:** `datev.wirtschaftsjahr_beginn` (`config/accounti.example.yaml:40`), `export/datev_stammdaten.wirtschaftsjahr_beginn()` (:170–180), `betrieb/aufbewahrung.wirtschaftsjahr(tag, beginn)` (:145), drei Leser der Einstellung (A26). Saldovortrag (EB am 01.01., `abschluss/vortrag.py:153`, :190, seit 7 im EB-Rahmen `eroeffnungsbuchungen`), Jahres- und Monatssperre und SuSa rechnen im Kalenderjahr | BWA kumuliert im Wirtschaftsjahr; SuSa/Kontenblatt bleiben Kalenderjahr mit Hinweis |
| 17 | **OPOS-Befehle gibt es schon:** `accounti opos liste --richtung eingang\|ausgang --faellig --stichtag` (`cli.py:1513–1576`), `opos staffel` (:1579–1619), `_richtung_option` (:1396–1407); `--stichtag` wirkt nur auf Fälligkeit und Überfälligkeitstage, der Restbetrag ist der Stand von heute | `--csv`/`--pdf` an die vorhandenen Befehle; ehrliche Beschriftung |
| 18 | **Kontenblatt-Grundlage:** `Bewegung` (`abschluss/salden.py:40–47`) kennt `buchung_id`, aber weder Gegenkonto noch Text; `lade_bewegungen(session, kr, von, bis)` (:81–91) nur freigegebene Buchungen, Datum in Python gefiltert; EB-Werte nur aus Buchungen gegen 9000/9008/9009 (:149–150) — ohne gebuchten Saldovortrag beginnt ein Bestandskonto still bei 0 | Kontenblatt aus `lade_buchungen` + `bewegungen(b, kr)`; Hinweis „Saldovortrag noch nicht gebucht“ |
| 19 | **Bilddekodierung:** `erkenne_format` (`belege/erkennung.py:85`) erkennt Bilder an den ersten Bytes (`_BILD_SIGNATUREN`, :64) und liefert nur `BILD`; `Image.open()` ohne `formats` probiert alle Pillow-Plugins (u. a. EPS → Ghostscript; Beschränkung `PIL/Image.py:3629–3630`); die Bombenprüfung beim Öffnen gilt nur dem ersten Bild (`_open_core`, :3678), Folgeseiten prüft Pillow erst beim `load()` (`TiffImagePlugin.load_prepare`, :1309–1313) | Bildart nach Signatur; `Image.open(…, formats=["TIFF"])`; eigene Pixelgrenze je Seite **vor** `load()` |
| 20 | **Aufgaben zur Buchung:** Baustein 8 legt für unsichere Buchungen Aufgaben `kontierung_pruefen` an (`aufgaben/prueflaeufe.py:129–170`), die erst der nächste Aufgabenlauf als `hinfaellig` schließt | Entscheidung in der Queue schließt sie sofort; die Arbeitsfläche zeigt Zuständigkeit und Frist |
| 21 | **Kontenbezeichnungen:** `Kontenrahmen.bezeichnung()` (`kontenrahmen.py:174`) aus `namen` (45 bzw. 26 Konten), `pruefung/skr03.yaml` 42 Konten mit DATEV-Namen, sonst nichts; Steuerschlüssel mit Bezeichnung in `steuer/kennziffern.STEUERSCHLUESSEL` (:76) | Bezeichnung aus beiden Quellen, sonst nur die Nummer |

### Abgrenzung

| Thema | 10a | 7 | 10b (dieser Plan) |
|-------|-----|---|-------------------|
| Anmeldung, Rollen, Sitzung, CSRF, CSP, Einmalcode | ✅ | — | nutzt; neues Recht `REGELN_LERNEN`, Spalte `auth_benutzer.sprache` |
| Gesellschaften | ✅ (je DB, Archiv, Konfig, Regeln) | — | alle Daten nur über `gesellschaft_db`/`a.gesellschaft` |
| Freigabe Zahlungslauf/USt-VA | ✅ | — | nur Übersetzung der Seiten |
| Buchung freigeben/korrigieren/stornieren | — | ✅ Fachlogik, CLI mit Recht + Einmalcode | Bedienung im Browser über genau diese Funktionen |
| Journal | — | ✅ (CLI, REST) | Person = angemeldeter Benutzer in jeder Seite; Regeln ins Journal |
| Periodenabschluss, Belegnachforderung | — | ✅ (CLI) | nur Anzeige und Fehlerwege |
| Rückfragen, Aufgaben | — | (8) ✅ | „Zurückstellen“, Aufgaben der Buchung schließen |
| Supervisions-Queue, Belegvorschau | — | — | **neu** |
| BWA, Kontenblatt, Exporte | — | — | **neu** (Fachfunktion + CLI + Seite) |
| Zweisprachigkeit | `lang="de"`, kein Mechanismus | — | **neu**, inkl. der Seiten aus 10a |

**Voraussetzung:** 7 ist auf `main` zusammengeführt (Alembic-Kopf `ddc9a184ddb4`, `pruefung/`,
`befehle.handelnde_person`); 10b zweigt danach als `feat/web-oberflaeche` ab. 10b greift in
`cli.py` nur in `classify`, `bank lauf`, `opos verbuchen`, `opos liste`, `opos staffel`, `review`,
`bestaetige`, `korrigiere`, `lerne` und `bwa` ein; die Rechteprüfung aus 7
(`handelnde_person`) bleibt, `korrigiere --lernen` prüft dabei zusätzlich `REGELN_LERNEN` mit
demselben Einmalcode. Die 7-Tests `test_korrigiere_lernen` und
`test_korrigiere_lernt_den_schluessel_der_neubuchung` (`tests/test_cli_supervisor.py:146`, :174)
und der 10a-Test `test_regeln_je_gesellschaft_auch_in_der_cli` prüfen heute die Regeldatei — 10b
stellt sie auf die Datenbank um (Absicht bleibt: je Gesellschaft, Schlüssel der Neubuchung).

---

## Recherche (Stand 21.10.2026)

| Thema | Ergebnis | Quelle |
|-------|----------|--------|
| HTMX (erneut geprüft) | `dist-tags`: `latest` = **2.0.11**, `next` = 4.0.0 (28.08.2026, Versionssprung — nicht verwenden); kein 2.0.12. 2.0.11 veröffentlicht **2026-09-22T20:20:43.983Z** — 29 Tage vor dem 21.10.2026, also älter als zwei Wochen; Vorgänger 2.0.10 vom 21.04.2026. Lizenz **0BSD** (`package.json` und `LICENSE` im Paket: „Zero-Clause BSD“). Tarball `htmx.org-2.0.11.tgz`: npm-Integrität `sha512-Thx/WtpeOQqSrqBCw/A1cwGJGg4UrVa3+sW0GmrM3p4gJgO89ecH4qtbnyzDDWFvBTqjnIMCgELTNt636dtamA==` (nachgerechnet, stimmt), `shasum` (SHA-1) `a85363c4c5af94cd634df04c4b83d06dd0e91aa7` (stimmt); `package/dist/htmx.min.js` 52 182 Bytes, SHA-256 **`d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717`**; `dist/htmx.js` meldet `version: '2.0.11'` | [npm-Registry htmx.org](https://registry.npmjs.org/htmx.org), Tarball [htmx.org-2.0.11.tgz](https://registry.npmjs.org/htmx.org/-/htmx.org-2.0.11.tgz), geladen und nachgerechnet am 21.10.2026 (eigener Ordner im Scratchpad, nicht ausgeführt) |
| HTMX und CSP | `allowEval` (Standard `true`, `htmx.js:154`) nutzt `eval`; `allowScriptTags` (`true`, :160) führt `<script>` aus geladenem Inhalt aus; `includeIndicatorStyles` (`true`, :118, ausgewertet :5136) fügt ein `<style>` ein, das `style-src 'self'` blockiert; `historyCacheSize` 10 (:89) im **`sessionStorage`**, `<= 0` leert ihn (:3221); unabhängig davon schreibt htmx den aktuellen **Pfad** nach `sessionStorage` (:3193, keine Seiteninhalte); `selfRequestsOnly` `true` (:241); Konfiguration per `<meta name="htmx-config">` (:5151) | Quelltext 2.0.11 |
| HTMX und Fehler | `responseHandling` (:264–268): `204` kein Tausch, `[23]..` Tausch, `[45]..` **kein Tausch** + `htmx:responseError`; das Muster ist ein regulärer Ausdruck auf den Status (`codeMatches`, :4796); `HX-Location`, `HX-Refresh`, `HX-Redirect` wirken **vor** `responseHandling` (:4867–4887); XHR folgt einer 303 still; `historyRestoreAsHxRequest` (`true`, :281/:3368) schickt bei Verlaufsabrufen `HX-Request` und `HX-History-Restore-Request`; `hx-disabled-elt` (:3443) | Quelltext 2.0.11 |
| GoBD und Einmalcode | Die GoBD verlangen Unveränderbarkeit und Protokollierung von Änderungen (Rz. 58, 59, 107–110), rückbeziehbare Korrektur- und Stornobuchungen (Rz. 64) und ein internes Kontrollsystem: Kontrollen einrichten, ausüben, protokollieren; Beispiele u. a. Zugangs- und Zugriffsberechtigungskontrollen auf Basis eines Berechtigungskonzepts und Funktionstrennungen; die Ausgestaltung richtet sich nach Komplexität der Geschäftstätigkeit, Organisation und DV-System (Rz. 100). Ein zweiter Faktor je Buchung oder je Freigabe wird nicht verlangt. Rz. 101 betrifft die anlassbezogene Prüfung, ob das System der Dokumentation entspricht (nicht die Ausgestaltung) | Rz. 58/59/64/107–110 wie Plan 7 (Recherche dort); Rz. 100/101: [Haufe, GoBD Abschnitt 6 IKS](https://www.haufe.de/id/norm/grundsaetze-zur-ordnungsmaessigen-fuehrung-und-aufbewahrung-6-internes-kontrollsystem-iks-HI16886309_p6.html), [FGS zu IDW PH 9.860.4](https://www.fgs.de/news-and-insights/blog/detail/gobd-compliance-teil-2-idw-veroeffentlicht-neuen-pruefungshinweis-zu-den-grundsaetzen-digitaler-buchfuehrung-der-finanzverwaltung-idw-ph-98604) — Sekundärquellen, Wortlaut beim Zusammenführen gegen das BMF-Schreiben (Fassung 14.07.2025) prüfen |
| Bilder | Pillow 12.3: `Image.open(fp, formats=[…])` beschränkt die Decoder (`PIL/Image.py:3629–3630`); ohne Angabe probiert Pillow alle Plugins, darunter EPS (Ghostscript); `MAX_IMAGE_PIXELS` 89 478 485 (:86), Warnung ab einfachem, Fehler ab doppeltem Wert (:3570/:3577), beim Öffnen nur für das erste Bild (:3678); Folgeseiten eines TIFF prüft `TiffImagePlugin.load_prepare` beim `load()` (:1309–1313) | `dist-info` und Quelltext der venv |
| Wirtschaftsjahr | `export/datev_stammdaten.wirtschaftsjahr_beginn(stichtag, beginn)` (:170–180) und `betrieb/aufbewahrung.wirtschaftsjahr(tag, beginn) -> (beginn, ende)` (:145) liefern Beginn bzw. Zeitraum des Wirtschaftsjahres, in dem ein Tag liegt (§ 4a EStG) | Quelltext |
| PDF im Rahmen | Chromium zeigt PDFs in Sandbox-Kontexten nicht an; `Content-Security-Policy: sandbox` blockiert PDFs seit Chrome 88, Firefox nicht. Auch `default-src 'none'` steht im Verdacht, den Betrachter zu blockieren — **Browserprobe nötig** | [SAP-Forum](https://answers.sap.com/questions/13392550/chrome-blocking-pdf-content-accessed-via-media-url.html), [textslashplain](https://textslashplain.com/2024/05/06/err_blocked_by_client-and-html5-sandbox/), [Metabase-Forum](https://discourse.metabase.com/t/iframe-pdf-from-local-server-is-blocked/176181) |
| CSV-Formelinjektion | gefährlich am Zellanfang: `=`, `+`, `-`, `@`, Tab, CR, LF und Vollbreiten-Varianten; Gegenmittel: Feld in Anführungszeichen, `'` voranstellen, innere `"` verdoppeln; in Excel nie völlig sicher. `abschluss/ausgabe.susa_csv` (:17–30) nutzt `csv.writer(delimiter=";", lineterminator="\n")` ohne Schutz | [OWASP CSV Injection](https://community.owasp.org/attacks/CSV_Injection), Quelltext |
| E-Rechnung hybrid | seit 2025 ist bei ZUGFeRD der **strukturierte Teil** maßgeblich (GoBD Rz. 118/119 in der Fassung vom 14.07.2025, siehe Plan 7) | Plan 7, Recherche |
| Jinja-Übersetzung | `jinja2.ext.i18n` (Jinja2 3.1.6): `install_gettext_callables(gettext, ngettext, newstyle=True)` (`jinja2/ext.py:264`), Newstyle escapt Platzhalter bei Autoescape (:171–176); `Environment.extract_translations()` (:266) | Quelltext der venv |
| Dateiantworten | Starlette 1.6.0 `FileResponse`: `content_disposition_type` (`responses.py:309`), `filename*=utf-8''…` (:323), `Accept-Ranges: bytes` (:319) mit Range-Verarbeitung (:362–369) | Quelltext der venv |
| Abhängigkeiten | laut `dist-info/METADATA` in `/opt/accounti/.venv`: FastAPI 0.141.1, Starlette 1.6.0, Jinja2 3.1.6, fpdf2 2.8.9 (`FPDF.table`), Pillow 12.3.0, pypdf 6.21.1, httpx 0.28.1, uvicorn 0.52.1, SQLAlchemy 2.0.51, pydantic 2.13.4; **nicht** vorhanden: Babel, python-multipart. **Keine neue Python-Abhängigkeit** | `dist-info` der venv |

---

## Schnitt in Pakete

Der Schnitt aus Fassung 2 bleibt: PR 10b-1 liefert Akzeptanz 1 und 2 vollständig (Fachkern,
Gerüst, Queue), PR 10b-2 die Auswertungen, die nur über die Absprungziele `/buchungen/{id}` und
`/belege/{id}` an 10b-1 hängen. 7 und 10a haben keinen Teil eines Pakets erledigt, aber jedes
Paket kleiner gemacht (markiert mit **[7]**/**[10a]**: vorhanden, nur nutzen).

**PR 10b-1** (Pakete 1–3, Akzeptanz 1 und 2, zwei Migrationen):

1. **Paket 1 — Fachkern für die Oberfläche (ohne Seiten):** Herkunft je Buchung speichern (alle
   neun Quellen der Queue); Lernschleife als Funktion mit gelernten Regeln in der Datenbank, mit
   Richtung, Vorrang, Schalter und Journal (`erfasse`, `BESTAND`); ein Lader für das Regelwerk;
   Übernahme alter `gelernt_*`; Prüfschlange (Reihenfolge, Herkunft, Stand unter der Schreibsperre,
   Beleg zur Buchung, Aufgaben, Sperre, freigeben/korrigieren/zurückstellen); Storno-Fehler mit
   Feld und ohne CLI-Optionen im Text, `steuer_optionen`, `lade_korrekturumgebung`; Recht
   `REGELN_LERNEN`; CLI `review`, `bestaetige`, `korrigiere --lernen`, `lerne`, `classify`,
   `bank lauf`, `opos verbuchen` und neu `accounti regeln liste|deaktivieren|uebernehmen`;
   Verfahrensdoku und Aufbewahrung; **Migration** `<rev>_add_kontierung`.
   **[7]** Storno, Journal, Sperren, `handelnde_person`, Laufsperre in den Läufen; **[10a]**
   `regeln_datei()`.
2. **Paket 2 — Zweisprachiges Seitengerüst:** `i18n/` (Katalog, Sprachwahl, Formate), Jinja-i18n
   im Gerüst aus 10a, Übersetzung der Seiten aus 10a, Sprachwahl am Benutzer (**Migration**
   `<rev>_add_benutzer_sprache`, Schemaprüfung beim Start), HTMX samt Fehlerwegen (409/422,
   `HX-Redirect`, `HX-Refresh`, 503) und eigenes Skript lokal ausgeliefert, CSP-Regeln als Test,
   `api/handeln.py`, `api/einmalcode.py` (verschoben). **[10a]** Gerüst, CSP, CSRF, Registry,
   Einmalcode-Prüfung.
3. **Paket 3 — Supervisions-Queue:** zuerst ein **Browser-Spike** (PDF-Antwort-CSP in Chrome und
   Firefox, HTMX-Fehlerfragment), dann `/pruefen` (Liste, Arbeitsfläche, Aktionen, Regelvorschau,
   gelernte Regeln), `/belege/{id}` (Vorschau PDF/Bild/E-Rechnung), `/buchungen/{id}`
   (Storno-Korrektur mit Einmalcode), Tastaturbedienung, Rechte-Matrix (Codes nur für
   Einmalcode-Endpunkte), Person-Test über alle POST-Endpunkte, Akzeptanz 1 und 2 als
   Ende-zu-Ende-Tests. **[7]** `buchung zeige`-Daten, Nachforderung, Perioden; **[8]** Rückfragen.

**PR 10b-2** (Paket 4, nach 10b-1, ohne Migration):

4. **Paket 4 — Auswertungen:** BWA neu (Schema SKR03/SKR04 mit korrigierter Startzuordnung,
   Leitkonten, Konsistenz mit den EÜR-Kennzahlen, `ergebnisverwendung` im Kontenrahmen, Monat,
   kumuliert im Wirtschaftsjahr, Vorjahr, Festschreibungsstand), Kontenblatt mit Übertrag,
   OPOS-Bericht, gemeinsames Berichtsmodell mit CSV und PDF; CLI ohne neue Gruppe: `accounti bwa`
   rechnet (mit `--db`, `--config`, `--csv`, `--pdf`), `abschluss kontenblatt`, `abschluss susa
   --pdf`, `opos liste|staffel --csv/--pdf` (mit `--config`); `bwa_zeile` entfernt; Seiten unter
   `/auswertungen` mit Absprung bis zum Beleg (ohne Diagramm). **[12/#28]** Kontenrahmen,
   `lade_bewegungen`, `summen_und_salden`; **[4]** `opos.auswertung`; **[7]** `sperre_am`.
5. **Abschluss (je PR):** Protokolltest über alle neuen Wege, Browserprobe (Chrome, Firefox),
   gegnerische Prüfung, Migration gegen jede Datenbank (SQLite und PostgreSQL über
   `ACCOUNTI_TEST_PG`), Sicherungs-Rundlauf, `pytest`/`ruff`/`mypy`, Doku-Bausteine.

---

## Entscheidungen

### Seiten und Technik

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Darstellung | **Serverseitig gerendert** (Jinja2), progressive Verbesserung: Jede Funktion geht ohne JavaScript (Formulare, Links, POST → 303). HTMX tauscht nur Teile aus (nächster Eintrag der Queue, Regelvorschau); ein eigenes kleines Skript `statisch/pruefen.js` übernimmt Tasten und Fehlerhinweis. Kein SPA, kein Build-Schritt | Spec 5 (fix); alle Logik im Python-Code und damit im Testclient prüfbar; strenge CSP aus 10a bleibt unverändert |
| HTMX | **htmx 2.0.11** als Datei `statisch/htmx-2.0.11.min.js` (versionierter Name, weil `/statisch` zwischengespeichert wird; Inhalt = `package/dist/htmx.min.js` aus `htmx.org-2.0.11.tgz`) mit Lizenztext `statisch/LIZENZ-htmx.txt` (Paket-`LICENSE`, darüber Version, npm-Integrität und SHA-256); SHA-256 `d6fdc75f…f717` im Test festgehalten. Konfiguration im Layout: `<meta name="htmx-config" content='{"allowEval":false,"allowScriptTags":false,"includeIndicatorStyles":false,"historyCacheSize":0,"refreshOnHistoryMiss":true,"selfRequestsOnly":true,"responseHandling":[{"code":"204","swap":false},{"code":"[23]..","swap":true},{"code":"409\|422","swap":true,"error":false},{"code":"[45]..","swap":false,"error":true}]}'>`, `<body hx-history="false" hx-headers='{"X-CSRF-Token": "…"}'>`; Absende-Knöpfe mit `hx-disabled-elt="this"`. Keine `hx-on`-Attribute, keine `js:`-Ausdrücke | einzige neue „Abhängigkeit“ (JavaScript, keine Python-Bibliothek), > 2 Wochen alt, 0BSD; ohne `eval` und ohne Inline-Stil CSP-verträglich; kein Seitenstand mit Belegdaten im `sessionStorage` (dort nur der Pfad, der ohnehin nur UUIDs enthält); 409/422 kommen beim Benutzer an |
| Teilantworten | Eine Route, zwei Formen: mit `HX-Request` (und ohne `HX-History-Restore-Request`) das Fragment (`vorlagen/pruefen/_arbeitsflaeche.html`) plus `HX-Push-Url`, sonst die ganze Seite bzw. 303. Fragmente sind eigene Vorlagen, die die ganze Seite per `include` nutzt | kein Zweitweg; ohne HTMX dieselbe Funktion |
| Fehler im HTMX-Weg | **409/422** (veralteter `stand`, Fachfehler aus 7, ungültige Eingabe): mit `HX-Request` das Arbeitsflächen-Fragment mit Meldung (`role="alert"`), **neuem** `stand` und dem markierten Feld (`StornoError.feld`), Eingaben vorbelegt; ohne HTMX die ganze Seite mit demselben Status. **Ohne Sitzung:** bei `HX-Request` Status 200 mit `HX-Redirect: /anmelden?weiter=<Pfad>` statt 303 — `weiter` aus `HX-Current-URL` (nur Pfad, nur eigene Herkunft, sonst `/`), weil 10a bei POST `/` einsetzt (Handler `nicht_angemeldet` erweitern). **CSRF-403** bei `HX-Request`: `angemeldet()` setzt am CSRF-Fehler selbst `HX-Refresh: true` (die 403 der Rolle sieht gleich aus und bekommt den Kopf nicht). **Datenbank beschäftigt** (`sqlalchemy.exc.OperationalError` „database is locked“ unter SQLite, Sperr-Zeitüberschreitung unter PostgreSQL): eigener Handler in `api/app.py` → 503 mit `Retry-After: 5` und Meldung „Ein Lauf schreibt gerade — bitte gleich noch einmal“, alle anderen `OperationalError` bleiben 500. Übrige 4xx/5xx und Netzfehler: `pruefen.js` hört auf `htmx:responseError`/`htmx:sendError` und zeigt einen serverseitig gerenderten, versteckten Hinweis (`hidden` umschalten, kein `innerHTML`; eigener Text für 503) | htmx tauscht 4xx/5xx sonst nicht ein (Befund 15); 10a unterscheidet CSRF- und Rollen-403 nicht; ein Bank- oder Kontierungslauf hält die SQLite-Schreibsperre länger, `session_factory` wartet 30 s (7) — danach soll kein „Interner Fehler“ erscheinen; der Testclient führt kein htmx aus — daher Servertests auf Status, Fragment und Kopfzeilen plus Browserprobe |
| Stile | eigene Datei je Bereich (`statisch/pruefen.css`, `statisch/auswertungen.css`) über Block `kopf`; keine `style=`-Attribute (CSP `style-src 'self'` sperrt sie); Breiten und Höhen über Klassen; **alle** eigenen Dateien (auch `accounti.css` aus 10a) mit `?v={{ version }}` | 10a-CSP; `StaticFiles` sendet kein `Cache-Control`, Browser speichern heuristisch — ohne Versionsanhang liefe nach einem Update altes `pruefen.js` |
| IDs im Pfad | Starlette-Konverter `{buchung_id:uuid}`, `{beleg_id:uuid}`, `{regel_id:uuid}`; nie eine Präfixsuche im Web; an Fachfunktionen geht `str(uuid)` (ein voller UUID-Text trifft in `finde_buchung` genau eine Zeile) | `LIKE '<eingabe>%'` würde `_`/`%` als Muster lesen; feste Routen wie `/pruefen/regeln` kollidieren nicht mit `{id}` |
| Seiten ohne Parameter | `/pruefen`, `/pruefen/regeln`, `/auswertungen`, `/auswertungen/bwa`, `/auswertungen/susa`, `/auswertungen/kontenblatt`, `/auswertungen/opos` liefern ohne Angaben **200** (Standardzeitraum bzw. Auswahlformular), Recht `LESEN` | Akzeptanz-5-Test aus 10a ruft jede solche Seite als buchhalter auf |
| Blockierendes und Commit | Datenbank, PDF-Erzeugung, Bildumwandlung in `run_in_threadpool`; die Thread-Funktion öffnet `with im_namen(a):` (`api/handeln.py`: `geprueft_als(a.benutzer.name)` — Person aus der 2FA-Sitzung, im Journal ohne „(ungeprüft)“ —, gibt den Namen zurück), ruft die Fachfunktion mit `person=`/`von=` und committet selbst (`s.commit()`, im Fehlerfall `s.rollback()`), wie die 10a-Seiten | `gesellschaft_db` committet nicht (10a); der Kontext soll nicht davon abhängen, ob Context-Variablen in den Thread wandern; 7 liest die Person aus dem Kontext |
| Schema beim Start | `api/server.starte_aus_cli` prüft in der Systemdatenbank, ob `auth_benutzer.sprache` vorhanden ist (`Dienste.pruefe_schema()`); fehlt sie, bricht `serve` mit „`alembic upgrade head` für die Systemdatenbank ausführen (siehe docs/betrieb.md)“ ab (Exit 2, ohne URL/Passwort). Die Gesellschaftsdatenbanken prüft der Start nicht: `kontierungsgruende`/`kontierungsregeln` legt `init_db` beim ersten Zugriff an (samt SQLite-Triggern über `after_create`), die Migration übernimmt sie später | `init_db` (`create_all`) legt keine Spalten an — ein bestehendes `auth_benutzer` ohne `sprache` ließe jede Anmeldung mit einem SQL-Fehler scheitern; fehlende Tabellen dagegen entstehen von selbst |

### Belegvorschau

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Zugriff | Beleg nur per UUID aus `gesellschaft_db`, Datei nur aus `BelegArchiv(a.gesellschaft.archiv)`; `datei_hash` aus der Datenbank gegen `^[0-9a-f]{64}$` geprüft, aufgelöster Pfad muss unter der Archivwurzel liegen (`Path.resolve().is_relative_to`); fehlt die Datei → 404 ohne Pfad in der Meldung; **SHA-256 des gelesenen Inhalts = `datei_hash`**, sonst 409 „Beleg im Archiv verändert“ (und kein Inhalt) | Belegzugriff nur in der eigenen Gesellschaft; `BelegArchiv.pfad` globbt mit `f"{datei_hash}*"` (`belege/archiv.py:47–52`) — kein Wert aus der Anfrage darf dorthin; das Archiv ist inhaltsadressiert, die Probe kostet einen Hash und zeigt Manipulationen (GoBD Unveränderbarkeit) |
| Typ | **aus dem Inhalt**, nicht aus Dateiname oder Endung: `belege.erkennung.erkenne_format(RohBeleg)` → `ZUGFERD_PDF`/`PDF`, `ERECHNUNG_XML`, `BILD`, sonst `UNBEKANNT`/`TEXT`; für `BILD` zusätzlich `belegantwort.bildart(inhalt)` nach Signatur (`\xff\xd8\xff` JPEG, `\x89PNG` PNG, `II*\0`/`MM\0*` TIFF). Das Ergebnis wird je Anfrage einmal bestimmt (`erkenne_format` parst PDFs mit pypdf vollständig) | Absender bestimmen Dateinamen; derselbe Erkenner wie bei der Belegaufnahme; `erkenne_format` unterscheidet Bildarten nicht |
| PDF | `<iframe class="beleg" src="/belege/{id}/datei" title="…">` (CSP `frame-src 'self'` aus 10a), daneben „In neuem Tab öffnen“ und „Herunterladen“. Antwort: `FileResponse` mit ausdrücklichem `media_type="application/pdf"` (nie aus der Endung), `content_disposition_type="inline"`, `filename="beleg-<uuid>.pdf"` (fester ASCII-Name), `Cross-Origin-Resource-Policy: same-origin`, `nosniff`, `no-store`; CSP der Seite plus `form-action 'none'`. **Kein** `sandbox` (Chromium zeigt sonst nichts an). Der **Browser-Spike zu Beginn von Paket 3** entscheidet in Chrome und Firefox, ob eine strengere Antwort-CSP (`default-src 'none'; object-src 'self'; form-action 'none'`) den Betrachter noch lädt — das Ergebnis steht im Plan, **bevor** `test_pdf_inline_mit_sicheren_kopfzeilen` geschrieben wird | Spec 4.2 „Beleg links“; das Risiko aktiver PDF-Inhalte steht unter Grenzen |
| Bilder | PNG und JPEG direkt per `<img src="/belege/{id}/datei">` (nicht dekodiert, `Content-Type` aus der Signatur); TIFF (Scanner, Faxe) per Pillow seitenweise als PNG unter `/belege/{id}/seite/{n}.png` (höchstens 20 Seiten): `Image.open(fp, formats=["TIFF"])`, **vor jedem `load()` je Seite** `breite × höhe` gegen die eigene Grenze (Konfiguration `server.max_vorschau_megapixel`, Standard 40, unterhalb `MAX_IMAGE_PIXELS`), `DecompressionBombWarning` als Fehler, Modus nach `RGB`/`L` (CMYK, 16 Bit, Fax-G4); andere Bildformate (HEIC, WebP …) nur zum Herunterladen | Browser zeigen TIFF nicht an; Bildbomben dürfen den Server nicht lahmlegen; ohne `formats` probiert Pillow jedes Plugin (EPS → Ghostscript), und Pillows eigene Prüfung greift für Folgeseiten erst im `load()` und nur gegen das Doppelte von `MAX_IMAGE_PIXELS` |
| E-Rechnung | XML wird **nie** roh angezeigt: `erechnung.lies(xml)` (DTD/Entities abgelehnt, `parse_sicher`) → Vorlage `belege/_erechnung.html` mit Profil, Nummer, Datum, Typ, Verkäufer/Käufer (Name, Anschrift, USt-IdNr., Steuernummer), Leistungsdatum/-zeitraum, Positionen, Zu-/Abschläge, Steueraufschlüsselung, Summen, Fälligkeit, IBAN, Zahlungsbedingungen (inkl. Skonto), Notizen. Bei ZUGFeRD: PDF und Reiter „E-Rechnung (maßgeblich)“, Abweichungen bei Nummer, Datum und Brutto zwischen Beleg-Feldern und XML als Hinweis. Rohdatei nur als Download; Größe vor dem Lesen begrenzt (`server.max_beleg_mb`, dieselbe Grenze wie bei der Annahme) | seit 2025 gilt der strukturierte Teil; XML/XHTML inline wäre aktiver Inhalt derselben Herkunft |
| Unbekannt | Text, SVG, HTML, E-Mail, Office … nie inline; nur `/belege/{id}/download` mit `application/octet-stream`, `Content-Disposition: attachment; filename="beleg-<uuid>.<endung aus dem erkannten Typ oder .bin>"`, eigene CSP `default-src 'none'; sandbox` | SVG/HTML aus Fremdquellen könnten unter unserer Herkunft Skripte ausführen |
| Ohne Beleg | Bankbuchung ohne zugeordneten Beleg: links die Umsatzdaten (Datum, Betrag, Gegenkonto, IBAN lesbar, Verwendungszweck) und — aus 7 — entweder „belegfrei nach Regel *Name*: *Begründung*“ (`PruefEinstellungen.belegfrei_nach_regel`, Einstellungen der Gesellschaft) oder die offene Nachforderung (`aufgaben_zu(s, Objekt("transaktion", id))`, Art `beleg_fehlt`: Status, zuständig, fällig) samt Hinweis „Anfrage an den Lieferanten: `accounti nachfordern anfrage <ID>`“, sonst „kein Beleg zugeordnet“. **Weder Umsatz noch Beleg** (AfA, Anlagenabgang, Abgrenzung): links Herkunft und Rechenweg (z. B. `AfaVorgang.begruendung`) und „belegfrei: interne Buchung“ | auch das ist die Grundlage der Prüfung; Architekturprinzip 7 (Begründung der Belegfreiheit); Nachforderung und Versand bleiben bei 7 (CLI), die Oberfläche zeigt den Stand |
| Beleg zur Buchung | `belege/zuordnung.beleg_zur_buchung(session, buchung)`: `beleg_id` der Buchung, sonst bestätigter Belegabgleich der Transaktion (`lade_abgleiche(status={BESTAETIGT})`), sonst Beleg des offenen Postens, dem die Zahlung zugeordnet ist; sonst `None`. Genutzt von Queue, Buchungsansicht und Kontenblatt | eine Funktion statt drei Abfragen in Vorlagen |

### Prüfen, Korrigieren, Lernen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Begründung / Herkunft | neue Tabelle `kontierungsgruende`: `id` (Schlüssel), `buchung_id` (indiziert, **ohne** Fremdschlüssel), `quelle` ∈ `regelwerk`/`llm`/`beleg`/`kontakt`/`standard`/`opos`/`kreditkarte`/`anlagen`/`marktplatz`, `regel` (Name, optional), `modell` (LLM-Modell, optional), `begruendung` ≤ 500, `erstellt_am`; je Buchung gilt der neueste Grund. Geschrieben **in derselben Transaktion** wie die Buchung von `kontiere_umsaetze` (Regelwerk/LLM: `ergebnis.begruendung`, `quelle`, neues Feld `Klassifikationsergebnis.regel`, `LLMEngine.model`), `kontiere_mit_beleg` (`Sachkonto.quelle`, ggf. „Zahlbetrag weicht um x € vom Beleg ab“), `opos/verbuchung` (Belegbuchung samt `hinweise`, auch zum Buchungsdatum nach 7), Kreditkarte (Befund der Abrechnung), Anlagen (`anlagen/lauf.py`, `abgang.py`, **`dienst.py`** Umbuchung Anlagenzugang), Marktplatz (`integrationen/auszahlung.py`, **`integrationen/buchung.py`** Abrechnung). Ohne Zeile: `pruefschlange.herkunft()` liest ersatzweise `AfaVorgang`, bestätigten `Belegabgleich.begruendung`, `Zahlungszuordnung.begruendung`, `Beleg.pruef_grund`, `Kontakt.pruef_grund`; für Neubuchung und Stornobuchung einer Korrektur `buchungskorrekturen` (Grund, Person, Original); sonst „keine Begründung gespeichert“ | Spec 4.2 „Begründung, die die Klassifikation mitgeliefert hat“; Befund 3, 4 und 14. Kein Fremdschlüssel, weil `bank/kreditkarte._loese` vorläufige Buchungen löscht (`repo_bank.loesche_buchung`) — ein nur anfügbarer Grund mit Bezug bräche das; der Grund bleibt wie ein Journaleintrag zur verworfenen Buchung stehen |
| Nur anfügen | `kontierungsgruende`: ORM-Ereignis `before_update`/`before_delete` → `UnveraenderbarError`, SQLite-Trigger `kontierungsgruende_kein_update`/`_kein_delete` per `after_create` **und** in der Migration (wie `journal` in 7), Tabelle in `db.GESCHUETZT` (Massenwege gesperrt). Nicht im Journal | Muster aus 7; ein Journaleintrag je Grund verdoppelte das Journal ohne Mehrwert — die Buchung selbst steht dort |
| Prüfschlange | `buchung/pruefschlange.py`: Buchungen `zur Prüfung` der aktiven Datenbank, Reihenfolge Datum, dann ID; Ansichten `offen` (ohne offene Rückfrage) und `zurueckgestellt`; je Eintrag Buchung, Umsatz, Beleg, Kontakt, Herkunft, Geschwister (weitere Buchungssätze desselben Umsatzes/Belegs), offene Rückfrage, offene Aufgaben der Buchung (`kontierung_pruefen`) und des Umsatzes (`beleg_fehlt`), `belegfrei`, `sperre` (`perioden.sperre_am`), `stand`, `regel_moeglich`, `steuer_optionen`. `accounti review` nutzt dieselbe Funktion (zusätzliche Spalte „Begründung“, Zähler „zurückgestellt“, die Storno-Zeile aus 7 bleibt). Die Liste zeigt höchstens 200 Einträge je Seite (`?seite=n`) | eine Reihenfolge für CLI und Browser; „nächster Eintrag“ ist definiert |
| Stand | `stand` = SHA-256 über `kanonisch(schnappschuss(BuchungssatzRow.__table__, zeile))` aus 7 (alle Spalten, auch `beleg_id`, `datum`, `buchungstext`, `storniert_durch`, `storno_von`), 16 Hex-Zeichen, als verstecktes Feld in jedem Formular. Jede ändernde Funktion der Prüfschlange holt **zuerst** `journal.schreibsperre(session.connection())`, liest dann die Zeile und vergleicht; weicht der Stand ab → `StandVeraltetError` (409 „inzwischen geändert“ mit aktuellem Stand, im HTMX-Weg als Fragment) | zwei Personen an derselben Queue oder ein Doppelklick: ohne Prüfung würde eine zweite „Korrektur“ eines inzwischen freigegebenen Vorschlags still **ein Storno** erzeugen; 7 holt die Schreibsperre erst beim ersten Flush — ohne sie vor dem Vergleich könnte ein zweiter Schreiber zwischen Vergleich und Änderung committen |
| Nur Vorschläge | `/pruefen/{id}/freigeben\|korrigieren\|zurueckstellen` nehmen nur Buchungen mit Status `entwurf`/`zur Prüfung` an (`storno.VORSCHLAG`); sonst `NichtInPruefungError` → 409 „nicht mehr in der Prüfung“ mit Verweis auf `/buchungen/{id}` | eine handgebaute Anfrage mit aktuellem Stand löst auf der Queue-Route kein Storno aus; Storno nur auf `/buchungen/{id}` (mit Einmalcode) |
| Freigeben | `pruefschlange.freigeben(s, id, person, stand)` → `storno.freigeben(…, von=person)`; schließt eine offene Rückfrage der Buchung und die Aufgabe `kontierung_pruefen` als `hinfaellig` (`aufgaben.schliesse_wenn_erledigt(s, art, Objekt("buchung", id), "Buchung geprüft von <person>", von=person)`). `accounti bestaetige` ruft dieselbe Funktion (ohne `stand`); `storno.freigeben` nimmt weiterhin auch `auto` an (CLI), die Queue-Route nicht | Spec 4.2; Baustein 8 schließt `kontierung_pruefen` sonst erst beim nächsten Aufgabenlauf |
| Korrigieren | `pruefschlange.korrigieren(s, id, Aenderung(soll, haben, steuer, ohne_steuer, grund, datum), person, stand, umgebung, lernen=entwurf\|None)` → `storno.korrigiere(…, von=person, kontenrahmen=u.kontenrahmen, buchhaltung=u.buchhaltung, einstellungen=u.pruefung)`; Kontonummern gegen `^\d{4,8}$` (gemeinsamer Prüfer `buchung/konten.pruefe_kontonummer`, auch in der CLI), unbekannte, aber gültige Konten mit Hinweis; schließt Rückfrage und `kontierung_pruefen` wie Freigeben. Fehler aus `StornoError`, `JahrGesperrtError` (inkl. `PeriodeGesperrtError`), `UnveraenderbarError` → 409 mit der Meldung; `StornoError` mit `feld` und ungültige Eingaben → 422 | Baustein 7 bleibt die einzige Stelle, die bucht |
| Steuerangabe im Formular | Das Korrekturformular hat ein Auswahlfeld „Steuerschlüssel“ mit „unverändert (*Schlüssel*: *Bezeichnung*)“, den zulässigen Schlüsseln mit Bezeichnung (`STEUERSCHLUESSEL[n].bezeichnung`) und „ohne Steuer“; welche Optionen es gibt, sagt **`storno.steuer_optionen(b)`** — dieselbe Funktion, mit der `_steuer` prüft (bei Belegbuchungen kein anderer Schlüssel, „ohne Steuer“ nur mit Grund und nie bei ausgewiesener USt 2/3, dort der Hinweis auf § 14c Abs. 1 UStG). Ändert sich das Sachkonto und steht „unverändert“, lehnt `korrigiere` ab: 422, das Feld verliert „unverändert“ und ist Pflicht („Das Sachkonto ändert sich (4980 → 4930) — Steuerschlüssel bestätigen oder ‚ohne Steuer‘ wählen“). Dazu bekommt `StornoError` die Felder `meldung` (ohne CLI-Optionen), `feld` (`steuer`, `datum`, `grund` oder `None`) und `cli` (der bisherige Optionshinweis); `str(fehler)` bleibt wörtlich wie heute, die CLI und die Tests aus 7 ändern sich nicht. Das Web zeigt `meldung` (deutsches Detail, `<span lang="de">`) unter einem übersetzten Rahmen | 7 verlangt bei Sachkontowechsel die ausdrückliche Angabe, damit kein Schlüssel still mitgeht (Vorsteuer auf 4360, USt auf eine Auszahlung) — ein vorbelegtes Feld wäre wieder still; die Formularlogik darf die Regeln aus 7 nicht nachbauen (Spec 3: keine UI-eigene Logik); „--steuer 9 angeben“ ist im Browser keine Anleitung |
| Recht für Korrigieren | `BUCHEN` wie `accounti korrigiere` und `buchung storniere` (7); mit Regel zusätzlich `REGELN_LERNEN` | 7: jede Rolle mit `BUCHEN` hat `BUCHUNG_FREIGEBEN` (Test `test_buchen_umfasst_die_freigabe`) — dieselbe Regel in Browser und CLI; die Korrektur setzt `korrigiert`, einen freigegebenen Status |
| Kontenrahmen, Buchhaltung, Prüfeinstellungen | `storno.lade_korrekturumgebung(pfad) -> Korrekturumgebung(kontenrahmen=lade_abschluss(pfad).lade_kontenrahmen(), buchhaltung=lade_buchhaltung(pfad), pruefung=lade_pruefung(pfad))`; im Web mit `pfad = a.gesellschaft.konfiguration`, in der CLI mit `--config`; `cli.korrigiere` und `befehle/buchung.storniere` nutzen ihn statt `lade_kontenrahmen(buchhaltung.kontenrahmen)` | Befund 8; ohne `einstellungen` prüfte das Web gegen die mitgelieferte SKR03-Automatikdatei; mit eigener `abschluss.kontenzuordnung` sahen Korrektur (Umkehrbarkeit, Steuerkonto) und SuSa bisher verschiedene Kontenrahmen |
| Zurückstellen | `pruefschlange.zurueckstellen(s, id, text, person, an, einstellungen)` → `aufgaben.halte_rueckfrage_fest(s, Objekt("buchung", id), text, person, als_aufgabe=True, an=an, einstellungen=lade_aufgaben_einstellungen(g.konfiguration))`; Buchung bleibt `zur Prüfung`, erscheint in der Ansicht `zurueckgestellt`; Text Pflicht; **nur aus der Ansicht `offen`** — ist schon eine Rückfrage offen, 409 „schon zurückgestellt“. Recht: `BUCHEN` **oder** `BUCHUNG_FREIGEBEN` | kein neuer Status in `BuchungStatus`; die Frage landet dort, wo Baustein 8 sie verwaltet (Zuständigkeit, Erinnerung); auch ein `freigeber` muss nachfragen können; Zurückstellen ändert den `stand` nicht |
| Gelernte Regeln | **in der Datenbank der Gesellschaft**, Tabelle `kontierungsregeln` (`id`, `name` eindeutig, `muster` ≤ 200, `ist_text`, `feld`, **`richtung`**, `soll_konto`, `haben_konto`, `steuer_schluessel`, `buchungstext`, `quelle_buchung_id`, `herkunft` ∈ `korrektur`/`lerne`/`uebernahme`, `angelegt_von`/`_am`, `aktiv`, `deaktiviert_von`/`_am`, `deaktiviert_grund`). Ins Journal über `ereignisse.erfasse(KontierungsregelRow.__table__, Erfassung("kontierungsregel", _regel))`: Anlage → `regel_gelernt` bzw. `regel_uebernommen`, aktiv → aus → `regel_deaktiviert`; Person aus dem Kontext. Objekttyp `kontierungsregel` in `journal.BESTAND` (Abgleich mit dem Bestand), Tabelle in `db.GESCHUETZT`; ORM-Sperre: Löschen nie, Ändern nur `aktiv` von an nach aus samt `deaktiviert_*` — eine Regel wird nicht bearbeitet, sondern deaktiviert und neu gelernt. `accounti korrigiere --lernen` **und `accounti lerne`** schreiben dorthin (`lerne`: Regex vom Betreiber, `ist_text=False`, mit `re.compile` geprüft, ≤ 200 Zeichen); `_regel_speichern` entfällt; accounti schreibt `config/regeln.yaml` nie mehr | Befund 5: je Gesellschaft ohne Pfadlogik, in der Sicherung, transaktional mit der Korrektur, mehrere Benutzer gleichzeitig, im Container trotz schreibgeschütztem `config/`, nachvollziehbar im Journal; eine an accounti vorbei geänderte Regel bucht künftig automatisch falsch — `journal pruefen` meldet sie über den Bestandsabgleich. Verworfen: Datei `regeln.gelernt.yaml` (schreibgeschützt im Container, nicht gesichert, Wettlauf zweier Schreiber) |
| Richtung | `richtung` ∈ {`ausgabe`, `einnahme`} aus dem Vorzeichen des Quellumsatzes (`betrag < 0` → Ausgabe); `Regel` bekommt den optionalen Parameter `richtung`, `passt()` prüft ihn (ohne Angabe wie bisher beide Richtungen; in `regeln.yaml` als optionales Feld erlaubt). Belegdaten laufen als Pseudo-Ausgabe (`mit_beleg.py`, negativer Betrag) und passen zu Ausgaberegeln | Befund 13 |
| Vorrang | `klassifikation/lernen.lade_regelwerk(session, regeldatei, einstellung)` = aktive gelernte Regeln (neueste zuerst) → Regeldatei der Gesellschaft → `STANDARD_REGELN`. CLI (`classify`, `bank lauf`, `opos verbuchen`) übergibt `betrieb.kontext.regeln_datei()`, `api/rest/laeufe._bank` `g.regeln`; **kein eigener Ausweichpfad**. Weil die Regeln jetzt in der Datenbank liegen, bauen `classify` und `bank lauf` die Engine **in** der Sitzung, nachdem sie die Laufsperre haben (bisher davor). Genutzt auch von `sachkonto_fuer_beleg` | Akzeptanz 2: „greift beim nächsten Lauf“ — auch wenn eine eigene Regel vorher falsch getroffen hat |
| Schalter | `buchhaltung.gelernte_regeln: automatisch \| pruefen \| aus` (Standard `automatisch`). `automatisch`: Confidence 1,0 wie jede Regel; `pruefen`: Confidence 0,9 — unter der Schwelle von `zu_buchungssatz`, also `zur Prüfung` mit Grund „Regel 'gelernt_…' (Einstellung: prüfen)“; `aus`: gelernte Regeln werden nicht geladen (Lernen bleibt möglich) | vorsichtige Einführung möglich; Akzeptanz 2 gilt in beiden Stufen |
| Übernahme | `accounti regeln uebernehmen [--probe]`: Einträge `gelernt_*` aus der Regeldatei der Gesellschaft → `kontierungsregeln` (`ist_text=False`, weil schon `re.escape`, `richtung` aus der Bankseite — Bank im Haben → Ausgabe, im Soll → Einnahme, sonst ein Geldkonto des Kontenrahmens; ohne Bankseite leer und gemeldet —, `herkunft=uebernahme`); die Datei bleibt unverändert, die Ausgabe nennt die Einträge, die von Hand zu löschen sind; derselbe Eintrag wird übersprungen, ein vergebener Name mit anderem Inhalt ist ungültig (Runde 6) | vor 10b gelernte Regeln stehen mit kaputter Stellung am Dateiende |
| Regelangebot | Haken „Regel daraus machen“ nur, wenn `herkunft.quelle` ∈ {`regelwerk`, `llm`, `standard`} und ein Umsatz vorliegt; bei Belegbuchungen mit Personenkonto „Sachkonto am Kontakt lernen“; bei `kreditkarte`, `anlagen`, `marktplatz`, `opos` ohne Personenkonto kein Angebot | eine Regel aus „VISA“ (Sammelbelastung) oder einer AfA-Buchung wäre Unsinn |
| Regelentwurf | `entwurf_aus_korrektur(korrektur, umsatz, buchhaltung)`: Muster = der ganze Name der Gegenpartei ohne Rechtsform (Nachbesserung H1), ohne Namen das erste Wort des Verwendungszwecks (ist es kürzer als 3 Zeichen, die ersten zwei Wörter; dann verlangt die Regel immer die Bestätigung, Nachprüfung H-1), im Browser änderbar; Treffer **nur auf ganze Wörter** (`\b…\b` um den escapten Text); Feld `gegenkonto_name`/`verwendungszweck`/`beide`; `richtung` aus dem Umsatz; Soll/Haben aus der Korrektur, Schlüssel **der Neubuchung** (`korrektur.neu.steuer_schluessel` — bei neuem Sachkonto ausdrücklich angegeben, sonst der des unveränderten Sachkontos, wie 7 es in `korrigiere --lernen` festgelegt hat); steht dort das Finanzkonto des Umsatzes (`tx.sachkonto`, z. B. Kreditkarte), speichert die Regel `buchhaltung.bank_konto`, weil `kontiere_umsaetze` das Finanzkonto beim Anwenden wieder einsetzt | die Regel bucht künftig wie die Korrektur; „Müller“ soll „Müllerstraße“ nicht treffen |
| Muster nur als Text | im Browser ist das Muster **Text, kein regulärer Ausdruck** (gespeichert mit `ist_text`, beim Laden `re.escape`), 3–100 Zeichen | eigene Regexe aus dem Browser liefen über alle Umsätze (ReDoS); Regexe bleiben Sache des Betreibers (`config/regeln.yaml`, `accounti lerne`) |
| Vorschau | `pruefe_entwurf(s, entwurf, umsatz, regelwerk)` → Trefferzahl über die Umsätze der Gesellschaft der **letzten 24 Monate**, getrennt nach Richtung (Gegenrichtung als „nicht betroffen“), bis zu fünf Beispiele (Datum, Gegenkonto, Betrag, bisherige Kontierung), davon anders kontiert, „greift für diesen Umsatz: ja/nein“, „verdrängt Regel X“, Warnungen (zu kurz, zu breit > 20 % aller Umsätze, gleiches Muster schon gelernt, Konto unbekannt, Schalter steht auf `aus`). Hinweis: wirkt nur auf noch nicht gebuchte Umsätze (und auf Umsätze, die ein reines Storno wieder öffnet). Im Browser per `POST` (HTMX-Fragment, ohne JS über eine Schaltfläche „Vorschau“) | Spec-Auftrag „Vorschau der Regel“; POST, weil Muster Lieferantennamen enthalten — sie gehören nicht in URLs, Verlauf und Proxy-Protokolle |
| Lernen bei Belegbuchungen | Buchung ohne Umsatz, mit Beleg und Personenkonto: `lerne_sachkonto(s, buchung, soll, haben, person)` (aus `cli._lerne_sachkonto` herausgelöst) setzt `Kontakt.sachkonto`; Journal `schreibe(s, "sachkonto_gelernt", "kontakt", id, vorher=…, nachher=…)`. Vorschau zeigt „Sachkonto 4930 künftig für Lieferant X vorschlagen“ | gleiche Lernschleife wie in der CLI; Kontakte stehen nicht im Journal-Bestand |
| Rückgängig | `/pruefen/regeln` listet gelernte Regeln (wer, wann, aus welcher Buchung, Richtung, Treffer seither laut `kontierungsgruende.regel`), „Deaktivieren“ mit Grund (eine schon deaktivierte Regel → 409); CLI `accounti regeln liste\|deaktivieren ID --grund\|uebernehmen` | eine falsch gelernte Regel bucht sonst stillschweigend automatisch weiter |
| Neues Recht | `Recht.REGELN_LERNEN` („Kontierungsregeln lernen“), Rollen `buchhalter` und `verwalter`. Der `verwalter` hat kein `BUCHEN`, kann also nicht aus einer Korrektur lernen, wohl aber Regeln sehen, voranschauen und **deaktivieren** — Spec 3 führt „Regeln“ unter `/einstellungen`. In der CLI: `lerne`, `regeln deaktivieren`, `regeln uebernehmen` über `handelnde_person(…, REGELN_LERNEN, …)`; `korrigiere --lernen` über `handelnde_person(…, BUCHEN, …, weitere=(REGELN_LERNEN,))` — `auth/cli.pruefe_recht_in` prüft dafür eine Menge von Rechten mit **einem** Einmalcode; `regeln liste` ohne Recht (wie `review`) | gelernte Regeln buchen künftige Umsätze automatisch — das gehört an ein eigenes, prüfbares Recht; Einzelrechte unterhalb der Rollen bleiben ausgeschlossen (Spec 8); zwei Prüfungen verlangten zwei Codes (Plan 7) |

### Person, Einmalcode, Sperren

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Person im Web | Jede schreibende Thread-Funktion läuft in `api/handeln.im_namen(a)` (`geprueft_als(a.benutzer.name)`, siehe B1) und übergibt dieselbe Person ausdrücklich an jede Fachfunktion (`von=`, `person=`, `autor=`, `angelegt_von`). Nie `aktuelle_person(None)` im Web. Test über **alle** POST-Endpunkte der Registry mit `ACCOUNTI_BENUTZER=mallory` und einem Prozess-Login „mallory“: kein Journaleintrag, kein `geprueft_von`, keine Korrektur, Regel oder Rückfrage trägt „mallory“ | Spec 4.1 „echter Benutzer statt Zeichenkette“; in der CLI setzt `handelnde_person` den Kontext nach Recht und Einmalcode, in REST `Zugang.person` — im Browser ist es die Sitzung; `storno` setzt einen inneren Kontext mit `aktuelle_person(von)`, ohne `von` stünde dort der Server-Prozess |
| Einmalcode in der Queue | **Kein** Einmalcode für Freigeben, Korrigieren (auch mit Regel) und Zurückstellen von **Vorschlägen** in `/pruefen` | **Spec 4.2:** „Korrigieren, freigeben oder zurückstellen in einem Schritt, Tastaturbedienung für schnelles Durcharbeiten“ — ein Code je Buchung bricht beides. **Spec 4.1:** der `buchhalter` „erfasst, prüft, korrigiert“; Freigaben mit Vier-Augen-Bezug sind Zahlungsläufe und Steuermeldungen (`freigeber`, Baustein 6). **Authentisierung:** Eine Browser-Sitzung entsteht nur mit Passwort **und** zweitem Faktor (Akzeptanz 4, 10a), sie endet nach 30 min Leerlauf bzw. 8 h; die CLI hat keine Sitzung — dort *ist* der Einmalcode der Nachweis der Person („Ein Name in `ACCOUNTI_BENUTZER` oder `--von` beweist nichts, der zweite Faktor schon“, `auth/cli.py`). Gleiches Schutzziel, verschiedene Mittel; deshalb verlangt `bestaetige` in der CLI weiterhin den Code. **GoBD:** verlangt sind Unveränderbarkeit und Protokollierung (Rz. 58, 59, 107–110), rückbeziehbare Korrekturen (Rz. 64) und ein IKS mit Zugriffskontrollen und Funktionstrennung, dessen Ausgestaltung sich nach der Komplexität richtet (Rz. 100) — kein zweiter Faktor je Buchung. Erfüllt durch Rolle je Gesellschaft, 2FA-Anmeldung, Journal mit dem angemeldeten Benutzer, Storno statt Änderung, Festschreibung. **Umkehrbar:** ein freigegebener Vorschlag lässt sich jederzeit per Storno korrigieren, sichtbar im Journal |
| Einmalcode auf `/buchungen/{id}` | **Mit** frischem Einmalcode (`api/einmalcode.bestaetige_einmalcode`, aus `api/seiten/freigaben.py` verschoben, Schalter `auth.einmalcode_bestaetigung`): „Korrigieren (Storno und Neubuchung)“ und „Stornieren“ freigegebener Buchungen; Feld `einmalcode` im Formular, Prüfung **vor** dem Storno, falscher Code 403 ohne Änderung | Hier gilt die 10a-Schnittstelle („Freigaben mit frischem Einmalcode … wie bei Zahlungslauf und USt-VA“): Ein Storno ist in accounti endgültig (eine Stornobuchung wird nicht storniert, `_nicht_storniert`), betrifft oft schon exportierte oder gemeldete Zeiträume (Warnung „berichtigte Voranmeldung“) und ist selten — kein Tastaturfluss leidet. Der Schritt entspricht in Gewicht den Freigaben aus 10a |
| Vier-Augen bei Buchungen | `ersteller_ausgeschlossen` (10a) gilt für Zahlungsläufe, nicht für Buchungsvorschläge | Vorschläge legt die Klassifikation an, nicht eine Person; weder Spec noch GoBD verlangen für Buchungen ein Vier-Augen-Prinzip (Grenze) |
| Text der Einstellung | `auth.einmalcode_bestaetigung` (Beschreibung in `auth/einstellungen.py` und Beispielkonfiguration): „Zahlungsläufe, Steuermeldungen und Storno/Korrektur freigegebener Buchungen im Browser mit Einmalcode; in der CLI jeder Befehl mit Recht“ | bisher „Freigaben im Browser“ — ohne Klarstellung läse man die Queue mit hinein |
| Sperren im Web | `lade_eintrag` liefert `sperre` (`perioden.sperre_am(s, buchung.datum)`); ein gesperrter Vorschlag zeigt statt der Aktionen die Sperre (Monat festgeschrieben / Geschäftsjahr abgeschlossen) mit eigenem, übersetzbarem Text aus `Sperre.art` und `Sperre.zeitraum` (nicht `Sperre.text`, der CLI-Befehle nennt); eine trotzdem gesendete Aktion → 409 aus `JahrGesperrtError`. Auf `/buchungen/{id}`: liegt das Datum gesperrt, ist das Datumsfeld Pflicht und **nicht vorbelegt** (7: „keine stille Wahl“); `korrektur.warnungen` (anderer Voranmeldungszeitraum) erscheinen als Meldung nach der Aktion. **Kein** Festschreiben oder Öffnen von Monaten im Web | Monatsschluss verlangt „keine Vorschläge im Monat“ (7), Vorschläge in gesperrten Zeiträumen gibt es also nur unter der Jahressperre — selten, aber dann ohne sinnlose Knöpfe; Festschreiben gehört zu `/pruefung` bzw. bleibt in der CLI (nicht in 10b) |
| Laufsperre | Seiten aus 10b starten **keine** Läufe und nehmen keine Laufsperre (wie `bestaetige`/`korrigiere` in der CLI); Läufe gibt es weiter über CLI, geplanten Lauf und REST (`/api/v1/laeufe/bank` mit Laufsperre, 409, `journal_kontext("API-Token <Name>")`). Schreibt ein Lauf lange, wartet eine Aktion bis zu 30 s auf die SQLite-Sperre und bekommt danach 503 statt 500 (siehe „Fehler im HTMX-Weg“). Ein künftiger „Lauf starten“-Knopf müsste `betrieb.laufsperre` wie REST nutzen | die Laufsperre verhindert doppeltes Kontieren desselben Umsatzes; Freigeben und Korrigieren kontieren keine Umsätze, ein Storno öffnet einen Umsatz erst nach dem Commit für den nächsten Lauf |
| Korrektur freigegebener Buchungen | `/buchungen/{id}` zeigt, was `accounti buchung zeige` zeigt (dieselben Funktionen: `repo_pruefung.korrektur_zu`, `journal.lade_journal(objekt_id=…)`, dazu `herkunft`), und bietet „Korrigieren (Storno und Neubuchung)“ und „Stornieren“ an — mit Steuerauswahl wie in der Queue, Grund (beim Stornieren Pflicht, beim Korrigieren vorbelegt mit dem Text, den `korrigiere` erzeugt), Datum bei Sperre, Einmalcode. Nach einem **reinen Storno** einer Bankbuchung der Hinweis „Der Umsatz ist wieder offen und wird beim nächsten Lauf neu kontiert (gegebenenfalls über eine gelernte Regel)“ | Auftrag: Storno statt Änderung bei festgeschriebenen/exportierten Buchungen, über die Dienste aus 7; 7 öffnet den Umsatz nach reinem Storno wieder (`gebuchte_transaktion_ids`) |

### Bedienung der Queue

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Seiten | `/pruefen` = Liste (wie `accounti review`: Datum, Gegenpartei, Betrag, Vorschlag, Confidence, Begründung kurz) mit „Durcharbeiten“; `/pruefen/{id}` = Arbeitsfläche: links Beleg, rechts Vorschlag (Konto mit Bezeichnung, wo bekannt — `Kontenrahmen.bezeichnung`, sonst `pruefung/skr03.yaml` bzw. `pruefung.kontenrahmen_datei`, sonst nur die Nummer; Steuerschlüssel mit Bezeichnung, Netto/Steuer/Brutto, Datum, Buchungstext, Confidence abgerundet in Prozent mit Schwelle aus `buchung.mapper` wie Baustein 8, Quelle und Begründung, Umsatzdaten, Geschwister, Rückfragen, Aufgaben mit Zuständigkeit, Sperre), darunter die drei Aktionen; Kopf „3 von 57“ mit vor/zurück | Spec 4.2 |
| Tasten | `statisch/pruefen.js` (Ereignisdelegation am `document`, übersteht HTMX-Austausch; kein `eval`, kein `innerHTML`): `j`/`k` nächster/voriger, `f` freigeben, `e` Korrektur (Fokus auf Soll), `r` Regel-Haken, `z` zurückstellen (Fokus auf Text), `b` Beleg in neuem Tab, `?` Tastenhilfe (serverseitig gerendert, `hidden` umgeschaltet); in Eingabefeldern nur `Strg+Enter` (absenden) und `Esc` (Feld verlassen). **Ignoriert** werden Ereignisse mit `ctrlKey`/`metaKey`/`altKey` (außer `Strg+Enter` im Feld), mit `repeat`, mit `isComposing` und mit Fokus in `input`, `textarea`, `select` oder `[contenteditable]`. Aktionen lösen den Knopf des Formulars aus (`button.click()`), nie eine eigene Anfrage. Schalter „Tastenkürzel aus“ in der Tastenhilfe, gemerkt in `localStorage` (nur dieser Wahrheitswert). Zuordnung über `data-taste`-Attribute; Hinweise als `<kbd>`; Tasten in beiden Sprachen gleich. Auf `/buchungen/{id}` keine Ein-Tasten-Kürzel | Spec 4.2; WCAG 2.1.4; Storno ist kein Tastenfluss |
| Nach der Aktion | ohne HTMX 303 auf den nächsten Eintrag derselben Ansicht (oder Liste mit „fertig“); mit HTMX das Fragment des nächsten Eintrags, `HX-Push-Url`; Meldung „freigegeben/korrigiert/zurückgestellt“ oben; bei 409/422 bleibt die Arbeitsfläche mit Meldung stehen | Fluss ohne Seitenwechsel, Zurück-Taste funktioniert |
| Ohne Recht | Formulare erscheinen nur, wenn `a.darf(...)`; die Route prüft trotzdem selbst | Betrachter sehen die Queue lesend |

### Auswertungen und Export

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| BWA-Schema | YAML je Kontenrahmen im Paket (`bwa/schema_skr03.yaml`, `bwa/schema_skr04.yaml`), eigenes Schema über Abschnitt `bwa.schema` der Konfiguration. **Format:** `zeilen: [{nr, bezeichnung, art, konten: [{von, bis}], formel}]` mit `art` ∈ `ertrag` (Saldo Haben − Soll), `aufwand` (Soll − Haben), `summe` (nur `formel`), `unbesetzt` (Kontenklasse ohne Bedeutung, Haben − Soll, geht ins Ergebnis vor Steuern). **Zuordnung wie im Kontenrahmen: die engste passende Spanne gewinnt** (dieselben `_Spanne`-Objekte und `_engste` aus `abschluss/kontenrahmen.py`). **Ergebnisverwendung** steht nicht im BWA-Schema, sondern einmal im Kontenrahmen: neuer Schlüssel `ergebnisverwendung: [{von, bis}]` in `abschluss/kontenrahmen_skr03.yaml`/`…_skr04.yaml` (`Kontenrahmen.ist_ergebnisverwendung(konto)`); diese Spannen nehmen an der „engsten Spanne“ teil und schließen ein Konto aus der BWA aus. Ein eigenes Schema darf zusätzlich `ausgeschlossen: [{von, bis, grund}]` führen; eine eigene Kontenzuordnung (`abschluss.kontenzuordnung`) ohne `ergebnisverwendung` ergibt den Hinweis „Ergebnisverwendung nicht abgegrenzt“. Zeilen angelehnt an DATEV-BWA Form 01, Startzuordnung im Abschnitt „BWA-Startzuordnung“; Quelle im Dateikopf — **eigene Zuordnung von accounti, keine DATEV-Tabelle** | Befund 1; SKR04 sonst nicht möglich; das alte Gerüst scheiterte an der **Addition** überlappender Zeilen, nicht an der Überlappung; die Ergebnisverwendung an einer Stelle hält BWA und EÜR (Kz „-“) zusammen |
| BWA-Rechnung | `bwa.berechnung.berechne_bwa(session, jahr, monat, kr, schema, wj_beginn)` aus `abschluss.salden.lade_bewegungen` (nur freigegebene Buchungen, Steuer abgespalten, Storno hebt sich auf) — **einmal** geladen für den Zeitraum Beginn des Vor-Wirtschaftsjahres bis Monatsende, danach je (Konto, Monat) summiert: je Basiszeile Saldo der Konten nach `art` der **Zeile**, Summenzeilen per Formel aus Zeilennummern mit `+`/`-` (eigener Mini-Parser, kein `eval`, Bezüge nur auf frühere Zeilen); Spalten Monat, kumuliert (**Beginn des Wirtschaftsjahres** bis Monatsende), Vorjahresmonat, Vorjahr kumuliert (dieselben Monate des vorigen Wirtschaftsjahres), Abweichung kumuliert absolut und in Prozent (Basis 0 → „—“, Basis negativ → bezogen auf den Betrag); je Zeile die Konten mit Beträgen (für den Absprung); Hinweise „n Vorschläge nicht enthalten“, „keine Vorjahreszahlen“, „n Konten in keiner Zeile“ (nur bei eigenem Schema), **Festschreibungsstand** des Monats („festgeschrieben“ bzw. „nicht festgeschrieben — Zahlen vorläufig“, aus `perioden.sperre_am(session, monatsende)`). `BWAZeile` bekommt `art`, `betrag_vorjahr`, `betrag_vorjahr_kumuliert`, `konten` | eine Quelle für SuSa, Kontenblatt und BWA; ein Ladevorgang statt vier; 7 macht den Festschreibungsstand erst verfügbar |
| Prüfbarkeit | **Leitkonten-Test** je Kontenrahmen (Tabelle „Leitkonten“): Konto → erwartete Zeile bzw. „nicht in der BWA“/„Ergebnisverwendung“. **Vollständigkeit:** jede Nummer 0000–9999 mit `kr.art(nr, "bilanz") is ERFOLG` liegt in genau einer Zeile oder in der Ergebnisverwendung; keine zwei gleich engen Treffer verschiedener Zeilen. **Einklang mit der EÜR** (neu, gegen die in #28 berichtigten Kennzahlen): (a) für jedes Erfolgskonto steht das Paar (BWA-Zeile, `kr.euer_kz(konto, ±1)`) in der Tabelle „Erlaubte Kombinationen“ unten oder in einer benannten Ausnahme mit Spanne und Grund; (b) **Richtung:** Konten mit Einnahme-Kennzahl liegen nur in Ertrags-/unbesetzten Zeilen, Konten mit Ausgabe-Kennzahl nur in Aufwandszeilen — Ausnahmen nur Forderungsverluste (Kz 112, mindern die Einnahmen) und SKR03 8959/SKR04 4699 (Kz 183 in Zeile 1); (c) jede `ergebnisverwendung`-Spanne hat EÜR-Kz „-“. **Invariante:** vorläufiges Ergebnis (Zeile 29) = − Σ Saldo der Erfolgskonten (Modus Bilanz) ohne Ergebnisverwendung; bei Wirtschaftsjahr = Kalenderjahr zusätzlich = `Susa.ergebnis` + Σ Saldo der Ergebnisverwendungskonten (bei EÜR außerdem + Σ Saldo der Steuerkonten, die nur bei EÜR erfolgswirksam sind; `Susa.ergebnis` = − Σ Saldo der Erfolgskonten, `abschluss/salden.py:132–135`); eine handgerechnete BWA als Beispiel | DATEVs genaue BWA-Zuordnung ist nicht frei verfügbar; Lücken, Doppelzählungen und Widersprüche zur EÜR lassen sich trotzdem ausschließen — der Richtungstest hätte den Fehler, den #28 behob (Erlösschmälerungen SKR04 als sonstige Erträge), in BWA-Form gefunden; Ergebnisverwendung in einer BWA-Zeile fängt nur der Leitkonten- bzw. Kz-Test |
| Geschäftsjahr | **BWA im Wirtschaftsjahr** der Gesellschaft: Beginn aus `datev.wirtschaftsjahr_beginn` über **einen** Leser `konfiguration.lade_wirtschaftsjahr_beginn(pfad) -> date \| None` (herausgelöst aus `befehle/betrieb._wirtschaftsjahr_beginn`; `befehle/gesellschaft` und `export/datev_stammdaten` nutzen ihn ebenfalls), Zeitraum mit der vorhandenen `betrieb.aufbewahrung.wirtschaftsjahr(tag, beginn)`. SuSa und Kontenblatt bleiben im **Kalenderjahr** wie Saldovortrag, Jahres- und Monatssperre; ist das Wirtschaftsjahr abweichend, zeigen sie den Hinweis „Kalenderjahr — das Wirtschaftsjahr beginnt am TT.MM.“ | Spec 4.4 „eigenes Wirtschaftsjahr“; drei Leser derselben Einstellung sind zwei zu viel |
| Kontenblatt | `abschluss/kontenblatt.kontenblatt(session, konto, kr, jahr, von=None, bis=None)` aus `lade_buchungen` + `bewegungen(b, kr)` je Buchung, `kr = lade_abschluss(pfad).lade_kontenrahmen()` wie die SuSa: Zeile „EB-Wert“ (Eröffnungsbuchungen des Jahres, auch die aus dem EB-Rahmen von 7 mit Belegnummer `EB-JJJJ`), Zeile „Übertrag“ (Bewegungen vom 1. Januar bis zum Tag vor `von`), je Bewegung Datum, Belegnummer, Text, Gegenkonto (Gegenseite, bei Steuerzeilen die Bruttoseite), Soll, Haben, laufender Saldo, Buchungs-ID, Beleg-ID (`beleg_zur_buchung`), Kennzeichen Storno/storniert (`storno_von`/`storniert_durch`); Summen, Endsaldo, Festschreibungsstand. Hinweis „Saldovortrag JJJJ noch nicht gebucht (accounti abschluss vortrag)“, wenn ein Bestandskonto keinen EB-Wert hat, im Vorjahr aber Bewegungen. Personenkonten wie Sachkonten. Invariante: Endsaldo bis `bis` = `Susa.saldo(konto)` bis `bis` | Spec 4.3 „Kontenblätter mit Absprung zum Beleg“; ein stiller Anfangssaldo 0 wäre irreführend |
| OPOS | `opos/auswertung` wie vorhanden (`offene_posten`, `faelligkeitsstaffel`, `summen_je_kontakt`) mit Filter Richtung und Stichtag; Beschriftung „Stand heute, Fälligkeit bezogen auf den TT.MM.JJJJ“ | nichts neu rechnen; `--stichtag` ändert die Staffel, nicht den Bestand |
| Berichtsmodell | `auswertung/bericht.py`: `Bericht(titel, untertitel, spalten, zeilen, summen, hinweise)` mit Spaltenarten (Text, Betrag, Datum, Prozent); Umwandler `bwa_bericht`, `susa_bericht`, `kontenblatt_bericht`, `opos_bericht` (Spaltenköpfe über einen Übersetzer, Standard Deutsch) | CSV und PDF für alle Auswertungen aus einer Form |
| CSV | `auswertung/ausgabe.bericht_csv(bericht)`: Semikolon, deutsche Beträge ohne Tausenderpunkt, Datum `TT.MM.JJJJ`, UTF-8 **ohne** BOM, Zeilenende LF — wie alle CSV-Ausgaben der CLI; **unabhängig von der Sprache der Oberfläche**; Textzellen, die mit `=`, `+`, `-`, `@`, Tab, CR, LF oder deren Vollbreiten-Form beginnen, bekommen ein `'` vorangestellt **und** werden in Anführungszeichen gesetzt; Zellen der Spaltenart Betrag/Datum/Prozent bleiben unberührt; `abschluss.ausgabe.susa_csv` nutzt denselben Schreiber. Web-Download = dieselben Bytes wie `--csv` | gleiche Datei aus Browser und CLI; Buchungstexte und Kontaktnamen sind Fremddaten |
| PDF | `auswertung/ausgabe.bericht_pdf(bericht, gesellschaft, erstellt_am)` mit fpdf2 und Liberation Sans aus `erechnung/schriften`, A4 quer für BWA und SuSa, `FPDF.table()`, Kopf mit Gesellschaft (`lade_eigene_firma(pfad).name`), Zeitraum, Stand, Festschreibungsstand, Fuß mit Seitenzahl und „nur freigegebene Buchungen“; Zahlen und Spaltenköpfe in der Sprache der Oberfläche, Kontenbezeichnungen deutsch; höchstens 20 000 Zeilen, darüber 422 „zu groß für PDF — bitte CSV oder kürzeren Zeitraum“ | vorhandene Abhängigkeit und Schriften |
| Download | `GET /auswertungen/{bericht}/export/{format}` mit Abfrage wie die Seite; `Content-Disposition: attachment; filename="bwa-2026-09.csv"` (Name nur aus geprüften Werten), `text/csv; charset=utf-8` bzw. `application/pdf`; Recht `LESEN` | Pfadparameter (Befund 11); keine Seiteneffekte, daher GET |
| CLI | **keine neue Gruppe**: `accounti bwa --period JJJJ-MM [--vergleich] [--csv DATEI] [--pdf DATEI] [--db] [--config]` (rechnet statt „Noch nicht implementiert“; CSV/PDF enthalten die Vorjahresspalten immer); neu `accounti abschluss kontenblatt --konto --jahr [--von] [--bis] [--csv] [--pdf]` neben `abschluss susa`; `abschluss susa` bekommt `--pdf`; `accounti opos liste` und `opos staffel` bekommen `--csv`/`--pdf` und `--config` (für den PDF-Kopf) | keine Auswertung nur im Browser; ohne `--db`/`--config` griffe `--gesellschaft` bei `bwa` nicht |
| `bwa_zeile` | entfällt: aus `src/accounti/pruefung/skr03.yaml` (43 Einträge, alte 23-Zeilen-Nummerierung) und `models.Konto` (`models/__init__.py:464`) entfernt; `pruefung/regeln/richtigkeit._lade_konten` liest das Feld nicht, eigene Dateien mit dem Feld laden weiter. Test: keine mitgelieferte YAML enthält `bwa_zeile` | zwei BWA-Quellen mit verschiedener Nummerierung würden sich widersprechen; „veraltet“ markieren (Fassung 2) ließe den Widerspruch stehen |
| Diagramm | **nicht in 10b** — die Übersicht `/auswertungen` zeigt die Kennzahlen (Gesamtleistung, Betriebsergebnis, vorläufiges Ergebnis; Monat und kumuliert, je mit Vorjahr) als Tabelle mit Links auf die Berichte | steht nicht in Spec 4.3 (YAGNI) |
| Drill-down | BWA-Zeile → Konten der Zeile → Kontenblatt → Buchung (`/buchungen/{id}`) → Beleg (`/belege/{id}`) | Spec 4.3 |

### BWA-Startzuordnung (gegen #28 geprüft; „(prüfen)“ vor dem Umsetzen entscheiden)

Ausgangspunkt für `schema_skr03.yaml`/`schema_skr04.yaml`. Gegenüber Fassung 2 nach den in #28
berichtigten Kontoarten und EÜR-Kennzahlen korrigiert (Lücke SKR03 3990–3999, Ergebnisverwendung,
rund 20 Zeilen an die EÜR-Kennzahl und an das Gegenstück im anderen Kontenrahmen angeglichen,
abgeleitet aus der Spalte „Posten in der Gewinnermittlung“ der DATEV-Kontenrahmen § 4/3,
Art.-Nr. 11079/11080). **Geprüft am 21.10.2026 mit dem echten Modul `abschluss.kontenrahmen`
(Stand #28):** keine Lücke unter den Erfolgskonten, keine Spanne über Nicht-Erfolgskonten, kein
Gleichstand zweier Zeilen, alle Leitkonten richtig (Skript `scratchpad/bwa-check/vorschlag.py`).
**„(prüfen)“** heißt: vor dem Schreiben des Schemas anhand der DATEV-Kontenliste SKR 03/04
„Gültig für 2026“ (Art.-Nr. 11174/11175) und der DATEV-Hilfe zur BWA Form 01 entscheiden und die
Quelle im Dateikopf vermerken. Es gilt die **engste Spanne**; breite Spannen sind Auffangbereiche
ihrer Kontenklasse; „darin … → n“ nennt engere Spannen, die einer anderen Zeile gehören.

| Nr | Zeile | Art | SKR03 | SKR04 |
|----|-------|-----|-------|-------|
| 1 | Umsatzerlöse | ertrag | 8000–8799 (darin 8700–8799 Erlösschmälerungen, gewährte Skonti — mindernd; 8570–8579, 8600–8649 → 7; 8650–8669 → 24), 8610–8614 Sachbezüge, 8900–8949 unentgeltliche Wertabgaben (prüfen), 8950–8959 Innenumsätze, § 24-Vergütung, direkt verbundene Steuern (prüfen) | 4000–4799 (darin 4700–4799 Erlösschmälerungen; 4570–4579 → 7), 4600–4699 unentgeltliche Wertabgaben (prüfen), 4940–4949 Sachbezüge |
| 2 | Bestandsveränderungen FE/UE | ertrag | 8960–8989 | 4800–4819 |
| 3 | Aktivierte Eigenleistungen | ertrag | 8990–8999 | 4820–4829 |
| 4 | Gesamtleistung | summe | 1+2+3 | 1+2+3 |
| 5 | Material-/Wareneinkauf | aufwand | 3000–3969, **3990–3999** (verrechnete Stoffkosten, seit #28 Erfolg), 4000–4099 | 5000–5999 |
| 6 | Rohertrag | summe | 4−5 | 4−5 |
| 7 | Sonstige betriebliche Erlöse | ertrag | 8570–8579, 8600–8649 (darin 8603, 8606 → 25; 8610–8614 → 1) (prüfen) | 4570–4579, 4833–4838, 4841–4842 (prüfen) |
| 8 | Betrieblicher Rohertrag | summe | 6+7 | 6+7 |
| 9 | Personalkosten | aufwand | 4100–4199 | 6000–6199, 6440 (Ausgleichsabgabe) |
| 10 | Raumkosten | aufwand | 4200–4299 | 6305–6359 (darin 6352 neutral → 23) |
| 11 | Betriebliche Steuern | aufwand | 4340–4359, 4510 (Kfz-Steuer) | 7650–7699 (darin 7685 Kfz-Steuer; 7690–7699 → 23) |
| 12 | Versicherungen/Beiträge | aufwand | 4360–4399 | 6400–6439 |
| 13 | Besondere Kosten | aufwand | (leer; prüfen) | (leer; prüfen) |
| 14 | Fahrzeugkosten (ohne Steuer) | aufwand | 4500–4599 | 6500–6599 |
| 15 | Werbe-/Reisekosten | aufwand | 4600–4699 | 6600–6699 |
| 16 | Kosten der Warenabgabe | aufwand | 4700–4799 | 6700–6799 |
| 17 | Abschreibungen | aufwand | 4820–4869, 4815 Kaufleasing (prüfen) | 6200–6269 (darin 6250 Kaufleasing) |
| 18 | Reparatur/Instandhaltung | aufwand | 4800–4809 | 6450–6499 (darin 6498–6499 Mietleasing → 19) |
| 19 | Sonstige Kosten | aufwand | 4000–4999 als Auffang der Klasse 4 (darin 4300–4306 nicht abziehbare Vorsteuer (prüfen), 4810–4819 Leasing, 4900–4999), 2400–2429 Forderungsverluste übliche Höhe | 6000–6999 als Auffang der Klasse 6 (darin 6270–6304 (prüfen), 6800–6859), 6498–6499, 6930–6939 Forderungsverluste übliche Höhe, 6970–6979 kalkulatorische Kosten |
| 20 | Gesamtkosten | summe | 9+10+…+19 | 9+10+…+19 |
| 21 | Betriebsergebnis | summe | 8−20 | 8−20 |
| 22 | Zinsaufwand | aufwand | 2100–2149 | 7300–7399 (darin 7390–7399 → 23) |
| 23 | Sonstiger neutraler Aufwand | aufwand | 2000–2099, 2150–2199, 2290–2499 (darin 2400–2429 → 19, Ergebnisverwendung ausgenommen), 2285–2289 Steuern Vorjahre für sonstige Steuern, 2430–2439 Forderungsverluste unüblich hoch, 4870–4899 (prüfen) | 6880–6999 als Auffang (darin 6884–6892 und 6980–6989 → 25, 6930–6939 und 6970–6979 → 19), 6280–6289 Forderungsverluste unüblich hoch, 6352, 6390–6399 Spenden, 7200–7299, 7390–7399 Verlustübernahme, 7500–7599, 7690–7699, 4855–4859 Restbuchwert bei Buchgewinn |
| 24 | Zinserträge | ertrag | 2650–2699 (darin 2660–2669 → 25), 8650–8669 Erlöse Zinsen und Diskontspesen (prüfen) | 7100–7199 (darin 7190–7199 → 25) |
| 25 | Sonstiger neutraler Ertrag | ertrag | 2500–2649, 2700–2999 (darin 2890–2899 verrechnete kalkulatorische Kosten; Ergebnisverwendung ausgenommen), 2660–2669, 8603, 8606, 8800–8899 Erlöse aus Anlagenverkäufen (prüfen) | 4840–4999 als Auffang (darin 4855–4859 → 23, 4940–4949 → 1), 4830–4832, 4839–4840, 4843, 6884–6892 Erlöse bei Buchverlust, 6980–6989 verrechnete kalkulatorische Kosten, 7000–7099, 7190–7199, 7400–7499 (prüfen) |
| 26 | Kontenklasse unbesetzt | unbesetzt | 5000–6999 | 8000–8999, 7800–7999 (zur freien Verfügung, prüfen) |
| 27 | Ergebnis vor Steuern | summe | 21−22−23+24+25+26 | 21−22−23+24+25+26 |
| 28 | Steuern vom Einkommen und Ertrag | aufwand | 2200–2289 (darin 2285–2289 → 23), 4320 Gewerbesteuer | 7600–7649 |
| 29 | Vorläufiges Ergebnis | summe | 27−28 | 27−28 |
| — | `ergebnisverwendung` (Kontenrahmen, EÜR-Kz „-“) | — | 2480–2489, 2495–2499, 2795–2799, 2840–2889 | 7700–7799 |

Offen bleiben fachlich (gleich in beiden Kontenrahmen gelöst, aber gegen die DATEV-BWA zu
prüfen): Grundsteuer (SKR03 2375 in 23 ↔ SKR04 7680 in 11 — angleichen), unentgeltliche
Wertabgaben in Zeile 1, Anlagenverkäufe in Zeile 25, 8950–8959/4690–4699 in Zeile 1.

**Leitkonten** (`tests/test_bwa_schema.py::test_leitkonten`, je Kontenrahmen parametrisiert):

| | SKR03 | SKR04 |
|---|-------|-------|
| Umsatzerlöse (1) | 8400, 8300, 8736 (gewährte Skonti, mindernd) | 4400, 4300, 4940 |
| Bestandsveränderungen (2) | 8960 | 4800 |
| Material-/Wareneinkauf (5) | 3400, 3736 (erhaltene Skonti, mindernd), 3990 | 5400 |
| Personal (9) | 4120 | 6000, 6440 |
| Raum (10) | 4210 | 6310 |
| Betriebliche Steuern (11) | 4510 | 7685 |
| Versicherungen (12) | 4360 | 6400 |
| Fahrzeug (14) | 4530 | 6530 |
| Werbe-/Reise (15) | 4600 | 6600 |
| Warenabgabe (16) | 4700 | 6700 |
| Abschreibungen (17) | 4830 | 6220 |
| Reparatur (18) | 4800 | 6460 |
| Sonstige Kosten (19) | 4930, 2400 | 6815, 6930 |
| Zinsaufwand (22) | 2100 | 7300 |
| Sonstiger neutraler Aufwand (23) | 2430 | 6280, 7390 |
| Zinserträge (24) | — (prüfen) | 7100 |
| Kontenklasse unbesetzt (26) | 5000 | 8000 |
| Steuern vom Einkommen und Ertrag (28) | 4320, 2200 | 7610, 7600 |
| Ergebnisverwendung | 2860, 2496 | 7751 |
| nicht in der BWA | 1200, 1576, 1776, 1800, 3970, 7000, 9000 | 1800, 1406, 3806, 2100, 9000 |

**Erlaubte Kombinationen BWA-Zeile ↔ EÜR-Kennzahl** (`tests/test_bwa_schema.py::test_einklang_mit_der_euer`;
aus der Startzuordnung abgeleitet, bei jeder Änderung des Schemas mitpflegen; `∅` = keine Kz):

| EÜR-Kz | erlaubte BWA-Zeilen |
|--------|---------------------|
| Einnahmen 111, 104, 112, 103 | 1, 3, 7, 24, 25 — Ausnahme Forderungsverluste (SKR03 2400–2439, SKR04 6280–6289, 6930–6939) in 19/23 |
| Entnahmen 106, 108 | 1 |
| 102, 124 | 25 |
| 135, 190 | 23 |
| 100, 110 | 5, 16, 19, 23 (in 23 nur SKR03 2327–2328, SKR04 6907–6908) |
| 120 | 9, 15 |
| 130–132, 134, 136–138 | 17 |
| 150, 152, 162, 163 | 10 |
| 172 | 10, 17 |
| 151 | 10, 11, 12, 18, 23 |
| 144, 146, 147, 142, 176 | 14, 15 |
| 145 | 11, 14 |
| 164, 165, 171, 174, 175, 177, 221, 224 | 15 |
| 168 | 12, 15, 19, 22, 23, 28 |
| 194, 226, 229, 280, 281 | 19 |
| 222 | 17, 19 |
| 223 | 12 |
| 225, 228 | 18 |
| 227 | 16 |
| 232, 234 | 22 |
| 183 | 11, 12, 15, 16, 19, 22, 23 — Ausnahme SKR03 8959, SKR04 4699 in 1 |
| 140, 141, 185, 186 | keine (darf es unter den Erfolgskonten im Modus Bilanz nicht geben) |
| „-“ | 2, 5, 15, 19, 23, 25, 28, Ergebnisverwendung |
| ∅ | 1 (Sonderbetriebseinnahmen 8500–8505/4500–4505), 17, 18, 19, 23, 25, 26, 28 |

### Zweisprachigkeit

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Mechanismus | `jinja2.ext.i18n` mit `install_gettext_callables(gettext, ngettext, newstyle=True)`; die Funktionen lesen die Sprache der Anfrage aus einer Context-Variable (`i18n.aktive_sprache`), die `seite()` beim Rendern setzt **und im `finally` per Token zurücksetzt** — auch auf dem Weg über die Fehlerseite (Starlette rendert im Konstruktor von `TemplateResponse`, also im selben Kontext). Deutsch ist die Quellsprache (msgid = deutscher Text), Katalog `i18n/en.yaml` (deutscher Text → englischer Text; Mehrzahl als `{one, other}`). In Python: `_()` zur Laufzeit, `N_()` als Marker (z. B. `Navigationspunkt(N_("Prüfen"), …)`), `Text(msgid, **werte)` für Meldungen in `HTTPException` (deutsch in `str()`, übersetzt in der Fehlerseite) | keine neue Abhängigkeit; Babel + `.po`/`.mo` bräuchte einen Build-Schritt; Newstyle escapt Platzhalter |
| Vollständigkeit | Test sammelt alle Texte aus allen Vorlagen (`Environment.extract_translations`), aus `_()`/`N_()`/`Text()` im Python-Code unter `api/` (AST) und die Zeilenbezeichnungen der mitgelieferten BWA-Schemata; jeder braucht einen Eintrag in `en.yaml`, kein Eintrag ist verwaist, Platzhalter (`%(name)s`) stimmen überein | neue Seiten können nicht unübersetzt durchrutschen |
| Fachbegriffe | geschützte Begriffe bleiben im Englischen deutsch, der Test prüft es: „Buchungssatz“, „BWA“, „Steuerschlüssel“, „GoBD“, „Festschreibung“, „USt-IdNr.“, „USt-VA“, „SKR03“/„SKR04“, „DATEV“, „ELSTER“, „ZUGFeRD“, „XRechnung“. Übersetzt, weil tragfähig: Soll/Haben → Debit/Credit, Summen- und Saldenliste → Trial balance, Kontenblatt → Account ledger, offene Posten → Open items, Storno → Reversal, Vorsteuer → Input VAT, Beleg → Document, Einmalcode → One-time code. Glossar als Kopfkommentar in `en.yaml` | Spec 4.5 |
| Sprachwahl | Reihenfolge: `auth_benutzer.sprache` (neue Spalte, `NULL` = automatisch) → `Accept-Language` (q-Werte; `en`/`en-*` → en, `de`/`de-*` → de) → `server.sprache` (Standard `de`). Wechsel über eine Auswahl im Kopf (`POST /einstellungen/sprache`, CSRF, „automatisch/Deutsch/English“), gespeichert über `auth.dienst.setze_sprache` in der Systemdatenbank. Anmeldeseite nach `Accept-Language`. `<html lang="…">`, `Vary: Accept-Language` (in `seite()`) | „je Benutzer“ geht über Geräte mit |
| Formate | Beträge DE `1.234,50`, EN `1,234.50`; Datum DE `21.10.2026`, EN `2026-10-21`; im Fließtext DE `1.234,50 €`, EN `€1,234.50`; in Tabellen ohne Zeichen, Spaltenkopf „EUR“; Prozent DE `12,5 %`, EN `12.5%`; Monatsnamen aus dem Katalog. Filter `betrag`, `datum`, `prozent`, `monat` lesen die aktive Sprache (`@pass_context`); `iban` (10a) bleibt sprachunabhängig. Eingaben sprachunabhängig: `<input type="date">` liefert ISO, Konten und Schlüssel sind Ziffern | keine Zahleneingaben in fremder Schreibweise zu parsen |
| Kontenbezeichnungen | bleiben deutsch (aus Kontenrahmen bzw. `pruefung/skr03.yaml`); BWA-Zeilen der mitgelieferten Schemata haben englische Einträge, eigene Schemata bleiben deutsch | DATEV-Bezeichnungen sind Fachsprache; Spec 4.5 |
| Nicht übersetzt | Meldungen der Fachmodule (`StornoError.meldung`, Sperrtexte aus 7 u. a.) erscheinen auf Englisch mit übersetztem Rahmen und deutschem Detail (`<span lang="de">`); CLI, E-Mails, PDFs anderer Bausteine, CSV-Spaltenköpfe | ehrlich statt halb übersetzt; CSV bleibt maschinenlesbar gleich |
| Seiten aus 10a | `basis.html`, `anmelden.html`, `start.html`, `freigaben.html`, `meldung.html` und die Meldungen in `sitzung.py`/`seiten/*.py` werden auf `_()`/`Text()` umgestellt; der Wortlaut auf Deutsch bleibt (der Akzeptanz-5-Test prüft „Gesellschaft: <strong>…</strong>“) | Zweisprachigkeit gilt für die ganze Oberfläche |

### Rechte und CSRF

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Je Seite | jede Route hängt an `erfordert(Recht.X)` (Tabelle „Seitenstruktur“); das einzige zusammengesetzte Recht (Zurückstellen: `BUCHEN` **oder** `BUCHUNG_FREIGEBEN`) prüft die Route nach der Dependency `angemeldet` mit `a.darf()`, die Regel bei der Korrektur (`REGELN_LERNEN`) prüft die Route, bevor sie etwas speichert; jede neue Route steht in `SEITEN` der Rechte-Matrix. Die Matrix erweitert ihre Erwartung um `EinesVon(frozenset)`; Schlüssel mit Konverter (`/pruefen/{buchung_id:uuid}`); `anfrage()` zieht einen Wiederherstellungscode **nur** für Endpunkte in `MIT_EINMALCODE` (Zahlungslauf, USt-VA, `/buchungen/{id}/korrigieren`, `/buchungen/{id}/stornieren`) | 10a-Muster; mit rund 20 neuen Endpunkten gingen die zehn Codes je Person sonst aus (`IndexError`) |
| CSRF | jedes Formular (auch Sprache, Regelvorschau, Deaktivieren) trägt `<input type="hidden" name="csrf">`; HTMX schickt zusätzlich `X-CSRF-Token` aus `hx-headers`; die Prüfung macht `angemeldet()` aus 10a. Test: **jeder** POST-Endpunkt der Registry ohne bzw. mit falschem Token → 403, nichts geändert | ein Test über die Registry statt je Seite |
| GET ohne Wirkung | Seiten, Belegdateien und Exporte ändern nichts; das Sitzungscookie ist `SameSite=Strict` (10a), fremde Seiten können Belege also auch nicht per `<img>`/`<iframe>` mit Anmeldung laden | Lese-Endpunkte brauchen kein CSRF-Token |

---

## Seitenstruktur

| Methode, Pfad | Recht | Einmalcode | Fachfunktion (gleich in der CLI) |
|---------------|-------|------------|----------------------------------|
| GET `/pruefen` | `LESEN` | — | `pruefschlange.lade_pruefschlange` (`accounti review`) |
| GET `/pruefen/{buchung_id:uuid}` | `LESEN` | — | `pruefschlange.lade_eintrag` |
| POST `/pruefen/{buchung_id:uuid}/freigeben` | `BUCHUNG_FREIGEBEN` | nein | `pruefschlange.freigeben` (`accounti bestaetige`) |
| POST `/pruefen/{buchung_id:uuid}/korrigieren` | `BUCHEN` (mit Regel + `REGELN_LERNEN`) | nein | `pruefschlange.korrigieren` (`accounti korrigiere [--lernen]`) |
| POST `/pruefen/{buchung_id:uuid}/regelvorschau` | `REGELN_LERNEN` | nein | `lernen.pruefe_entwurf` |
| POST `/pruefen/{buchung_id:uuid}/zurueckstellen` | `BUCHEN` oder `BUCHUNG_FREIGEBEN` | nein | `pruefschlange.zurueckstellen` (`accounti aufgaben rueckfrage --typ buchung --aufgabe`) |
| GET `/pruefen/regeln` | `LESEN` | — | `lernen.lade_gelernte_regeln` (`accounti regeln liste`) |
| POST `/pruefen/regeln/{regel_id:uuid}/deaktivieren` | `REGELN_LERNEN` | nein | `lernen.deaktiviere` (`accounti regeln deaktivieren`) |
| GET `/buchungen/{buchung_id:uuid}` | `LESEN` | — | `korrektur_zu`, `lade_journal(objekt_id=…)`, `herkunft` (`accounti buchung zeige`) |
| POST `/buchungen/{buchung_id:uuid}/korrigieren` | `BUCHEN` | **ja** | `storno.korrigiere` über `pruefschlange.korrigieren(…, nur_vorschlaege=False)` (`accounti korrigiere`) |
| POST `/buchungen/{buchung_id:uuid}/stornieren` | `BUCHEN` | **ja** | `storno.storniere` über `pruefschlange.stornieren` (`accounti buchung storniere`) |
| GET `/belege/{beleg_id:uuid}` | `LESEN` | — | Beleg, Vorschau, Buchungen (`lade_belegbuchungen`), Rückfragen (`kommentare_zu`) |
| GET `/belege/{beleg_id:uuid}/datei` | `LESEN` | — | Archiv der Gesellschaft (nur PDF, PNG, JPEG) |
| GET `/belege/{beleg_id:uuid}/seite/{n:int}.png` | `LESEN` | — | TIFF-Seite als PNG |
| GET `/belege/{beleg_id:uuid}/download` | `LESEN` | — | Original als Anhang |
| GET `/auswertungen` | `LESEN` | — | Übersicht mit Kennzahlen (aus `berechne_bwa` des laufenden Monats) und Links |
| GET `/auswertungen/bwa` | `LESEN` | — | `berechne_bwa` (`accounti bwa --period`) |
| GET `/auswertungen/susa` | `LESEN` | — | `summen_und_salden` (`accounti abschluss susa`) |
| GET `/auswertungen/kontenblatt` | `LESEN` | — | `kontenblatt` (`accounti abschluss kontenblatt`) |
| GET `/auswertungen/opos` | `LESEN` | — | `opos.auswertung` (`accounti opos liste`, `opos staffel`) |
| GET `/auswertungen/{bericht}/export/{format}` | `LESEN` | — | `bericht_csv` / `bericht_pdf` (`--csv` / `--pdf`); `bericht` und `format` als `Literal`/Enum (sonst 404) |
| POST `/einstellungen/sprache` | angemeldet | nein | `auth.dienst.setze_sprache` |

Navigation: „Prüfen“ (10, `LESEN`), „Auswertungen“ (30, `LESEN`) — Titel mit `N_()`.

## Schnittstelle (Fachfunktionen für CLI und Browser)

```python
# buchung/pruefschlange.py — alles in der Sitzung des Aufrufers, flush statt commit
eintraege = lade_pruefschlange(s, ansicht=Ansicht.OFFEN, seite=1)   # [Eintrag], Datum, dann ID
e = lade_eintrag(s, buchung_id, pruefung=u.pruefung)  # buchung, umsatz, beleg, kontakt, herkunft,
    # geschwister, rueckfrage, aufgaben, belegfrei, sperre, stand, regel_moeglich, steuer_optionen
herkunft(s, buchung) -> Herkunft  # quelle, text, regel — kontierungsgruende, sonst AfA/Abgleich/Zuordnung/
                                  # Prüfgründe/buchungskorrekturen
naechster(s, nach=buchung_id, ansicht=Ansicht.OFFEN) -> UUID | None
freigeben(s, buchung_id, person="jan", stand=e.stand)   # schreibsperre → Stand → storno.freigeben;
    # StandVeraltetError / NichtInPruefungError → 409; schließt Rückfrage und kontierung_pruefen
korrigieren(s, buchung_id, Aenderung(soll="4930", haben="1200", steuer=9, ohne_steuer=False,
            grund=None, datum=None), person="jan", stand=e.stand, umgebung=u,
            lernen=entwurf, nur_vorschlaege=True)   # -> storno.Korrektur
zurueckstellen(s, buchung_id, "Wofür war das?", person="jan", an=None, einstellungen=aufg)  # schon offen → 409
stornieren(s, buchung_id, grund="…", datum=None, person="jan", stand=e.stand, umgebung=u)  # /buchungen, buchung storniere

# pruefung/storno.py (aus 7, ergänzt)
u = lade_korrekturumgebung(pfad)   # Korrekturumgebung(kontenrahmen mit Kontenzuordnung, buchhaltung, pruefung)
steuer_optionen(buchung, beleg=None, plan=None) -> SteuerOptionen   # andere_schluessel, ohne_steuer, ohne_nur_mit_grund, hinweis, laut_beleg; plan: ein Erlös ohne eindeutige Belegart ist kein Eingang (Runde 8)
StornoError(meldung, *, feld=None, cli=None)  # str() wie bisher: meldung + CLI-Hinweis

# klassifikation/lernen.py
entwurf = entwurf_aus_korrektur(korrektur, umsatz, buchhaltung)   # RegelEntwurf (Text, Feld, Richtung, Konten,
                                                                  # Schlüssel der Neubuchung)
vorschau = pruefe_entwurf(s, entwurf, umsatz, regelwerk)         # letzte 24 Monate, je Richtung
regel = lerne(s, entwurf, person="jan")                 # kontierungsregeln; Journal „regel_gelernt“ über erfasse
lerne_regex(s, name, muster, soll, haben, steuer, person)  # accounti lerne: ist_text=False, re.compile geprüft
lerne_sachkonto(s, buchung, soll, haben, person="jan")  # Belegbuchung → Kontakt.sachkonto, Journal über schreibe
deaktiviere(s, regel_id, person="jan", grund="…")       # schon inaktiv → RegelError (409)
uebernehme_aus_datei(s, regeldatei, person, probe=False) -> Uebernahme  # gelernt_* → Datenbank
regelwerk = lade_regelwerk(s, regeldatei, buchhaltung.gelernte_regeln)  # gelernt → eigene → Standard
# regeldatei: CLI betrieb.kontext.regeln_datei(), Web/REST g.regeln — nie ein eigener Ausweichpfad
# engine.Regel(..., richtung: Literal["ausgabe", "einnahme"] | None = None); passt() prüft das Vorzeichen

# Herkunft
speichere_kontierungsgrund(s, buchung_id, quelle="llm", regel=None, modell="…", begruendung="…")
lade_kontierungsgrund(s, buchung_id) -> Kontierungsgrund | None   # der neueste

# Web
with im_namen(a) as person: ...                   # api/handeln.py: geprueft_als(a.benutzer.name)
bestaetige_einmalcode(dienste, a, felder["einmalcode"])   # api/einmalcode.py (aus seiten/freigaben.py)

# CLI (7, erweitert)
with handelnde_person(db, config, Recht.BUCHEN, von, weitere=(Recht.REGELN_LERNEN,)) as person: ...

# Auswertungen (PR 10b-2)
wj = lade_wirtschaftsjahr_beginn(g.konfiguration)          # date | None, aus datev.wirtschaftsjahr_beginn
kr = lade_abschluss(g.konfiguration).lade_kontenrahmen()   # mit ergebnisverwendung
bwa = berechne_bwa(s, jahr=2026, monat=9, kr=kr, schema=lade_bwa_schema(kr.name, eigenes), wj_beginn=wj)
blatt = kontenblatt(s, "4930", kr, jahr=2026, von=date(2026, 9, 1), bis=date(2026, 9, 30))
bericht = bwa_bericht(bwa, t)            # t: Übersetzer, Standard deutsch
bericht_csv(bericht) -> str ; bericht_pdf(bericht, gesellschaft="Alpha Papier GmbH", erstellt_am=…) -> bytes
```

---

## Aufgaben

> **Schutztests** sind als „(Schutz)“ markiert: Sie sind von Anfang an grün und sichern einen
> bestehenden Zustand gegen die Änderung ab — kein TDD-Rot erwartet. **Umgestellt** heißt: ein
> vorhandener Test aus 7 oder 10a prüft künftig das neue Verhalten.

### Paket 1 — Fachkern für die Oberfläche (PR 10b-1)

- [x] **Tabellen, Repository, Migration** (`db/tabellen_kontierung.py`, `db/repo_kontierung.py`,
  `models/kontierung.py`, `alembic/versions/<rev>_add_kontierung.py` mit `down_revision =
  "ddc9a184ddb4"`; Muster `ddc9a184ddb4`: vorhandene Tabellen, Indizes und Trigger übernehmen,
  SQLite-Trigger von Hand; `db.GESCHUETZT` um beide Tabellen ergänzt): `kontierungsgruende`
  (Schlüssel `id`, `buchung_id` indiziert ohne Fremdschlüssel, nur anfügen: ORM-Sperre + Trigger
  über `after_create`), `kontierungsregeln` (`name` eindeutig, `ist_text`, `richtung`, `herkunft`;
  ORM-Sperre: kein Löschen, Änderung nur `aktiv` an → aus samt `deaktiviert_*`). *Test zuerst*
  `tests/test_repo_kontierung.py::test_grund_nur_anfuegen` (ORM und rohes SQL unter SQLite),
  `::test_grund_ohne_buchungsbezug_bleibt_nach_verworfenem_vorschlag` (Kartenabgleich löst
  Zuordnung, `loesche_buchung` geht durch), `::test_neuester_grund_gilt`,
  `::test_regel_name_eindeutig`, `::test_regel_nur_deaktivierbar`,
  `::test_regeln_neueste_zuerst_nur_aktive`, `::test_massenaenderung_gesperrt`;
  `tests/test_migration_web.py::test_ein_kopf_nach_ddc9a184ddb4` (`alembic heads` = genau eine
  Revision, Kette `a684d10751de → ddc9a184ddb4 → <kontierung>`),
  `::test_upgrade_auf_bestand` (Datenbank auf `ddc9a184ddb4` mit Buchungen → `upgrade head`,
  Tabellen und Trigger da), `::test_migration_uebernimmt_was_init_db_schon_anlegte`,
  `::test_downgrade_und_wieder_hinauf` — Alembic als Unterprozess mit `ACCOUNTI_DB` wie
  `tests/test_migration_belegvollstaendigkeit.py`; rot; Umsetzung; grün.
- [x] **Journal** (`ereignisse.erfasse` für `kontierungsregeln` mit `_regel`: `regel_gelernt`,
  `regel_uebernommen`, `regel_deaktiviert`; `journal.BESTAND["kontierungsregel"]`): *Tests*
  `tests/test_kontierungsgrund.py::test_journal_bleibt_in_ordnung` (Schutz: Bestand mit Journal
  aus 7, Kontierungslauf mit Gründen → `pruefe_journal(...).in_ordnung`),
  `tests/test_lernen.py::test_lernen_im_journal_mit_person`,
  `::test_an_accounti_vorbei_geaenderte_regel_meldet_journal_pruefen` (rohes `UPDATE` auf
  `soll_konto` → Befund „abweichung“), `::test_verlauf_einer_regel` (gelernt → deaktiviert).
- [x] **Herkunft schreiben** (`models.Klassifikationsergebnis.regel`, `klassifikation/engine.py`,
  `klassifikation/llm.py` (Modellname), `buchung/kontierung.py`, `buchung/mit_beleg.py`,
  `opos/verbuchung.py` (auch Hinweis zum Buchungsdatum), `bank/kreditkarte.py`,
  `anlagen/lauf.py`, `anlagen/abgang.py`, `anlagen/dienst.py`, `integrationen/auszahlung.py`,
  `integrationen/buchung.py`): *Tests* `tests/test_kontierungsgrund.py::test_regelwerk_grund_mit_regelname`,
  `::test_llm_begruendung_quelle_und_modell` (LLM-Attrappe), `::test_belegbuchung_sachkonto_quelle`,
  `::test_abweichung_vom_beleg_im_grund`, `::test_opos_verbuchung_speichert_grund_und_hinweise`
  (auch „Buchungsdatum Eingang, Monat festgeschrieben“), `::test_kreditkarte_abweichung_als_grund`,
  `::test_afa_vorschlag_mit_rechenweg`, `::test_anlagenzugang_umbuchung_mit_grund`,
  `::test_marktplatz_auszahlung_und_abrechnung_mit_grund`, `::test_grund_in_derselben_transaktion`
  (Rollback nimmt Buchung und Grund zurück); rot; Umsetzung; grün.
- [x] **Richtung** (`klassifikation/engine.Regel`, `klassifikation/regeln_loader.py` (optionales
  Feld `richtung`)): *Tests* `tests/test_lernen.py::test_gelernte_regel_nur_in_ihrer_richtung`
  (Ausgaberegel „Müller“ trifft die Erstattung von Müller nicht),
  `::test_yaml_regel_ohne_richtung_wie_bisher`, `::test_belegdaten_passen_zu_ausgaberegel`; rot;
  Umsetzung; grün.
- [x] **Regelwerk-Lader und Schalter** (`klassifikation/lernen.py::lade_regelwerk`;
  `konfiguration.Buchhaltung.gelernte_regeln`; `cli.py` `classify`, `bank lauf`, `opos verbuchen`
  mit `regeln_datei()`, Engine **in** der Sitzung nach der Laufsperre; `api/rest/laeufe._bank` mit
  `g.regeln`): *Tests* `tests/test_lernen.py::test_reihenfolge_gelernt_eigene_standard`,
  `::test_gelernte_regel_schlaegt_falsch_treffende_eigene_regel` (Regression zu Befund 5),
  `::test_deaktivierte_regel_greift_nicht`, `::test_schalter_pruefen_legt_vor` (Confidence 0,9 →
  `zur Prüfung`), `::test_schalter_aus_laedt_keine_gelernten`; `tests/test_api_rest.py::test_bank_lauf_mit_gelernter_regel`.
  Der 10a-Test `test_regeln_je_gesellschaft_auch_in_der_cli` bleibt für `classify` grün (Schutz).
- [x] **Lernschleife** (`klassifikation/lernen.py`: `RegelEntwurf`, `entwurf_aus_korrektur`,
  `pruefe_entwurf`, `lerne`, `lerne_regex`, `lerne_sachkonto`, `deaktiviere`,
  `uebernehme_aus_datei`): *Tests* `tests/test_lernen.py::test_entwurf_erstes_wort_sonst_zwei_woerter`,
  `::test_text_muster_ist_kein_regex` (`.*` und `(a+)+$` werden wörtlich gesucht),
  `::test_text_muster_nur_ganze_woerter`, `::test_finanzkonto_wird_standard_bankkonto`,
  `::test_richtung_aus_dem_umsatz`, `::test_schluessel_der_neubuchung` (Sachkonto bleibt →
  bisheriger Schlüssel; neues Sachkonto → ausdrücklich angegebener; wie 7),
  `::test_vorschau_treffer_beispiele_verdraengte_regel`, `::test_vorschau_zaehlt_gegenrichtung_getrennt`,
  `::test_vorschau_nur_24_monate`, `::test_vorschau_warnt_zu_kurz_zu_breit_doppelt`,
  `::test_regel_nur_in_der_eigenen_datenbank`, `::test_lerne_sachkonto_am_kontakt_mit_journal`,
  `::test_lerne_regex_wird_geprueft` (ungültiger Ausdruck, > 200 Zeichen → Fehler),
  `::test_deaktivieren_zweimal_fehler`, `::test_uebernahme_gelernter_eintraege_aus_datei` (Datei
  unverändert, Doppelte übersprungen, Journal `regel_uebernommen`); rot; Umsetzung; grün.
- [x] **Storno-Anpassungen** (`pruefung/storno.py`: `StornoError(meldung, *, feld, cli)` an allen
  Stellen, `steuer_optionen(b)` aus `_steuer` herausgelöst und von dort genutzt,
  `lade_korrekturumgebung(pfad)`; `cli.korrigiere` und `befehle/buchung.storniere` auf
  `lade_korrekturumgebung`): *Tests* `tests/test_pruefung_storno.py::test_meldung_ohne_cli_optionen`
  (parametrisiert über alle `raise StornoError`: `meldung` ohne `--`, `str()` unverändert),
  `::test_feld_bei_steuer_datum_grund`, `::test_steuer_optionen_wie_korrigiere` (für Bank-,
  Beleg-, USt-2/3- und Vorsteuerbuchung: `korrigiere` lehnt genau ab, was nicht angeboten wird),
  `tests/test_cli_supervisor.py::test_korrigiere_nutzt_die_kontenzuordnung_der_gesellschaft`
  (eigene `abschluss.kontenzuordnung`); die CLI-Tests aus 7 (`test_cli_supervisor.py`,
  `test_cli_journal_storno.py`, `test_pruefung_storno.py`) bleiben grün (Schutz).
- [x] **Prüfschlange** (`buchung/pruefschlange.py`, `belege/zuordnung.py`, `buchung/konten.py`):
  *Tests* `tests/test_pruefschlange.py::test_reihenfolge_stabil`, `::test_ansichten_offen_und_zurueckgestellt`,
  `::test_beleg_zur_buchung_direkt_abgleich_posten_keiner`,
  `::test_herkunft_fuer_jede_quelle` (parametrisiert: Regelwerk, LLM, Beleg, Kontakt, Standard,
  OPOS, Kreditkarte, Anlagen (Lauf, Abgang, Zugang), Marktplatz (Auszahlung, Abrechnung),
  Altbuchung ohne Zeile, AfA ohne Zeile über `AfaVorgang`, Neubuchung über
  `buchungskorrekturen`), `::test_regelangebot_nur_fuer_kontierungsvorschlaege`,
  `::test_stand_aendert_sich_mit_jeder_spalte` (u. a. `beleg_id`, `datum`, `buchungstext`,
  `storniert_durch`), `::test_stand_unter_der_schreibsperre` (zweite Sitzung ändert zwischen Laden
  und Freigeben → `StandVeraltetError`, nichts geändert), `::test_freigeben_mit_veraltetem_stand_scheitert`,
  `::test_korrektur_mit_veraltetem_stand_storniert_nicht`, `::test_nur_vorschlaege`
  (freigegebene oder `auto`-Buchung → `NichtInPruefungError`),
  `::test_entscheidung_schliesst_rueckfrage_und_kontierung_pruefen`,
  `::test_zurueckstellen_legt_rueckfrage_als_aufgabe_an`, `::test_zurueckstellen_zweimal_fehler`,
  `::test_person_ist_der_uebergebene_benutzer` (`ACCOUNTI_BENUTZER=mallory` → Journal,
  `geprueft_von`, Korrektur tragen „jan“), `::test_umgebung_der_gesellschaft` (SKR04,
  `bank_konto` 1800, eigene `pruefung.kontenrahmen_datei`: Steuerkonto, Umkehrbarkeit und
  Automatikprüfung stimmen), `::test_sperre_im_eintrag` (Jahr abgeschlossen),
  `::test_belegnachforderung_und_belegfrei_im_eintrag`, `::test_kontonummer_geprueft`; rot;
  Umsetzung; grün.
- [x] **CLI auf die Fachfunktionen** (`cli.py` `review`, `bestaetige`, `korrigiere`, `lerne`;
  `_regel_speichern` und `_lerne_sachkonto` entfallen; `befehle.handelnde_person(…, weitere=…)`
  und `auth/cli.pruefe_recht_in` mit einer Menge von Rechten und einem Code; neu
  `befehle/regeln.py`: `accounti regeln liste|deaktivieren|uebernehmen`): *Tests* **umgestellt**
  `tests/test_cli_supervisor.py::test_korrigiere_lernen` (Regel in der Datenbank, Regeldatei
  unverändert samt Kommentaren) und `::test_korrigiere_lernt_den_schluessel_der_neubuchung` (Schlüssel
  in `kontierungsregeln`), **umgestellt** `tests/test_cli_gesellschaft.py::test_regeln_je_gesellschaft_auch_in_der_cli`
  (`-g b lerne` schreibt in die Datenbank von b, nicht von a; `b-regeln.yaml` unverändert); neu
  `::test_review_zeigt_begruendung_und_zurueckgestellt`, `tests/test_cli_lernen.py::test_lerne_schreibt_in_die_datenbank`
  (auch bei schreibgeschützter Datei), `::test_regeln_liste_und_deaktivieren`,
  `::test_regeln_uebernehmen_probe_und_echt`, `::test_gelernte_regel_greift_beim_naechsten_classify`,
  `tests/test_cli_rechte_pruefung.py::test_korrigiere_lernen_braucht_regeln_lernen_ein_code`
  (freigeber ohne `BUCHEN`, buchhalter mit einem Einmalcode), `::test_lerne_und_regeln_mit_recht`.
- [x] **Recht** `REGELN_LERNEN` in `models/auth.py` (`Recht`, `RECHT_TEXT`, `ROLLEN_RECHTE`
  für `buchhalter` und `verwalter`): *Test* `tests/test_auth_dienst.py::test_regeln_lernen_nur_buchhalter_und_verwalter`;
  `test_buchen_umfasst_die_freigabe` (7) bleibt grün (Schutz).
- [x] **Verfahrensdoku und Aufbewahrung** (`pruefung/verfahrensdoku._kontierung`: Regeldatei über
  `regeln_datei()` statt fest `config/regeln.yaml`, gelernte Regeln aus der Datenbank (aktiv,
  deaktiviert, Richtung, angelegt von/am), Schalter `buchhaltung.gelernte_regeln`;
  `betrieb/aufbewahrung.BESTAND`: `kontierungsgruende` nach `erstellt_am` und
  `kontierungsregeln` nach `angelegt_am`, je `Unterlage.BUCH`): *Tests*
  `tests/test_pruefung_verfahrensdoku.py::test_gelernte_regeln_in_der_verfahrensdoku`,
  `tests/test_betrieb_aufbewahrung.py::test_kontierungstabellen_im_bericht`.

**Umsetzung Paket 1 (21.10.2026) — Abweichungen vom Plan:**

- Migration `d5a849692843_add_kontierung` (auf `ddc9a184ddb4`), idempotent wie
  `ddc9a184ddb4`; die Tests in `tests/test_migration_web.py` heißen wie geplant, die
  Kette prüft `test_ein_kopf_nach_ddc9a184ddb4`. Umgestellt (B8):
  `test_migration_belegvollstaendigkeit.py::test_downgrade_und_wieder_hinauf`.
- `StornoError(meldung, *, feld, cli)`: `cli` ist der vollständige bisherige Text (B4).
  Getestet über `test_meldung_ohne_cli_optionen` (sieben Fallgruppen),
  `test_meldung_ohne_cli_optionen_beim_storno`, `test_feld_bei_steuer_datum_grund`,
  `test_steuer_optionen_wie_korrigiere` (sechs Buchungsarten gegen `_steuer` und
  `korrigiere`), dazu `test_lade_korrekturumgebung_mit_kontenzuordnung`.
- Herkunft bei Belegbuchungen aus `kontiere_umsaetze`: `quelle` ist `kontakt`,
  `regelwerk` (mit Regelname) oder `standard` je nach Herkunft des Sachkontos
  (Ausgang: `beleg`) — so gilt das Regelangebot (Regelwerk/LLM/Standard) auch für eine
  Belegbuchung mit Umsatz, deren Sachkonto aus einer Regel oder dem Standard kam.
  Marktplatz: `Buchungsergebnis.gruende` je Buchung (Befunde seit der letzten Buchung).
- `herkunft()`: Reihenfolge Grund → Korrektur (Neubuchung `korrektur`, Storno `storno`)
  → AfA → bestätigter Abgleich → Zuordnung → Prüfgrund Beleg/Kontakt. Test aufgeteilt in
  `test_herkunft_fuer_jede_gespeicherte_quelle` (neun Quellen) und
  `test_herkunft_ohne_zeile_abgeleitet`; die Schreiber je Quelle prüft
  `tests/test_kontierungsgrund.py`.
- `lerne_sachkonto` schreibt `sachkonto_gelernt` mit `nachher={sachkonto, bisher}` und
  **ohne** `vorher` — `kontakte bearbeiten` ändert Kontakte ohne Journal, ein
  `vorher` ergäbe sonst falsche Verlaufsbefunde in `journal pruefen`.
- Vorschau: Warnung „zu breit“ erst ab 10 Umsätzen im Zeitraum; „Konto unbekannt“ nur
  mit übergebenem Kontenrahmen (`pruefe_entwurf(…, kontenrahmen=…)`).
- Gelernte Regel mit (an accounti vorbei) ungültigem Ausdruck wird beim Laden
  übersprungen statt den Lauf abzubrechen (`journal pruefen` meldet die Änderung).
- `accounti review --zurueckgestellt` zeigt die zweite Ansicht; `korrigiere --muster`
  setzt das Text-Muster der Regel. `lerne` hat `--feld`, `--richtung`, `--von`, `--db`,
  `--config`.
- Kontonummern prüft `pruefschlange.korrigieren` nach dem Laden der Buchung (eine
  unbekannte ID meldet weiter „Keine Buchung“, Test aus 7 unverändert).

### Paket 2 — Zweisprachiges Seitengerüst (PR 10b-1)

- [x] **Kern** (`i18n/__init__.py`: `aktive_sprache`, `waehle_sprache`, `uebersetze`,
  `ngettext`, `N_`, `Text`, `betrag`, `datum`, `prozent`, `monat`; `i18n/en.yaml`): *Tests*
  `tests/test_i18n.py::test_accept_language_mit_q_werten`, `::test_benutzersprache_gewinnt`,
  `::test_unbekannte_sprache_faellt_auf_standard`, `::test_fehlender_eintrag_bleibt_deutsch`,
  `::test_platzhalter_werden_escaped`, `::test_mehrzahl`, `::test_formate_je_sprache`
  (`1.234,50`/`1,234.50`, `21.10.2026`/`2026-10-21`, negative Beträge, `None` → `—`).
- [x] **Jinja und Layout** (`api/vorlagen.py`: Erweiterung `jinja2.ext.i18n`, Callables, Filter
  mit `pass_context`, Sprache in `seite()` mit Token gesetzt und zurückgesetzt, `Vary`; `api/app.py`:
  Fehlerseite übersetzt `Text`; `basis.html`: `lang`, Sprachauswahl, `htmx-config`,
  `hx-history="false"`, `hx-headers`, Skript `htmx-2.0.11.min.js` mit `defer`, alle eigenen
  Dateien mit `?v={{ version }}`): *Tests* `tests/test_api_sprache.py::test_html_lang_und_navigation_englisch`,
  `::test_anmeldeseite_nach_accept_language`, `::test_fehlerseite_uebersetzt` (403-Rolle auf
  Englisch), `::test_vary_accept_language`, `::test_sprache_leckt_nicht_in_die_naechste_anfrage`.
- [x] **HTMX-Fehlerwege und Hilfen** (`api/app.py`: `nicht_angemeldet` mit `HX-Redirect` und
  `weiter` aus `HX-Current-URL`, Handler für `OperationalError` „beschäftigt“ → 503;
  `api/sitzung.angemeldet`: `HX-Refresh` am CSRF-Fehler; `api/htmx.py`: `ist_htmx(request)`,
  `ist_verlaufsabruf(request)`; `api/handeln.py`: `im_namen(a)`; `api/einmalcode.py`:
  `bestaetige_einmalcode` aus `seiten/freigaben.py` verschoben): *Tests*
  `tests/test_api_htmx.py::test_ohne_sitzung_hx_redirect_statt_303`,
  `::test_hx_redirect_weiter_aus_current_url_nur_eigene_herkunft`, `::test_csrf_fehler_hx_refresh`,
  `::test_rollen_403_ohne_hx_refresh`, `::test_verlaufsabruf_bekommt_ganze_seite`,
  `::test_ohne_htmx_unveraendert_303`, `::test_datenbank_beschaeftigt_503_mit_retry_after`
  (`OperationalError` per `monkeypatch`), `::test_andere_operationalerror_bleiben_500`;
  `tests/test_api_rechte_matrix.py::test_ustva_freigabe_im_browser` und
  `::test_vier_augen_im_browser` bleiben grün (Schutz für die verschobene Einmalcode-Prüfung).
- [x] **Sprachwahl am Benutzer** (Spalte `auth_benutzer.sprache`, `models/auth.Benutzer.sprache`,
  `db/tabellen_auth.py`, `db/repo_auth.py`, `auth/dienst.setze_sprache`, `api/seiten/sprache.py`,
  Migration `alembic/versions/<rev>_add_benutzer_sprache.py` mit `down_revision` = Kontierung,
  idempotent; `Dienste.pruefe_schema()` und Abbruch in `api/server.starte_aus_cli`): *Tests*
  `tests/test_api_sprache.py::test_sprache_wechseln_braucht_csrf`, `::test_sprache_bleibt_nach_neuer_anmeldung`,
  `::test_automatisch_folgt_wieder_dem_browser`,
  `tests/test_migration_web.py::test_upgrade_ergaenzt_sprache_in_bestehender_tabelle` (System- und
  Gesellschaftsdatenbank), `tests/test_api_schema.py::test_start_ohne_migration_bricht_mit_hinweis_ab`
  (Meldung ohne URL, Exit 2), `::test_frische_datenbank_startet`.
- [x] **Seiten aus 10a übersetzen** (`anmelden.html`, `start.html`, `freigaben.html`,
  `meldung.html`, Meldungen in `api/sitzung.py`, `api/seiten/*.py`): *Tests*
  `tests/test_api_sprache.py::test_jede_seite_in_beiden_sprachen` (alle GET-Seiten ohne Parameter:
  200, `lang`, „Company: <strong>…“ bzw. „Gesellschaft: <strong>…“),
  `tests/test_api_gesellschaften.py::test_akzeptanz_5_wechsel_aendert_alle_ansichten` bleibt grün
  (Schutz).
- [x] **Katalogtests** (`tests/test_i18n_katalog.py`): `::test_jeder_text_hat_eine_uebersetzung`,
  `::test_keine_verwaisten_eintraege`, `::test_platzhalter_gleich`, `::test_fachbegriffe_bleiben_deutsch`.
  Ab hier rot bei jedem neuen Text ohne Eintrag.
- [x] **Statisches und CSP** (`api/statisch/htmx-2.0.11.min.js` = `package/dist/htmx.min.js` aus
  `htmx.org-2.0.11.tgz`, `LIZENZ-htmx.txt` (Paket-`LICENSE` plus Version, npm-Integrität,
  SHA-256), `pruefen.js`, `pruefen.css`, `auswertungen.css`): *Tests*
  `tests/test_api_statisch.py::test_htmx_pruefsumme_und_lizenz` (SHA-256
  `d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717`, „Zero-Clause BSD“),
  `::test_htmx_konfiguration` (kein `eval`, keine Skripte, kein Indikatorstil, Verlaufscache 0,
  `responseHandling` tauscht `409|422` ein und andere 4xx/5xx nicht),
  `::test_keine_inline_skripte_stile_oder_ereignisattribute` (jede gerenderte Seite und jede
  Vorlage), `::test_eigenes_skript_ohne_eval_und_innerhtml`, `::test_eigene_dateien_mit_versionsanhang`
  (auch `accounti.css`).

**Umsetzung Paket 2 (21.10.2026) — Abweichungen vom Plan:**

- Migration `e7153706b43a_add_benutzer_sprache` (auf `d5a849692843`); Schemaprüfung
  `Dienste.pruefe_schema()` beim Start von `serve` (Exit 2, Meldung ohne URL).
- `Text` in `HTTPException.detail`: `str()` bleibt deutsch (API, Protokoll, Tests aus
  10a), die Fehlerseite übersetzt (`meldung | uebersetzt`). Die Jinja-Filter lesen die
  Sprache aus dem Vorlagenkontext (`sprache`), `_()`/`ngettext` ebenso; `seite()` setzt
  zusätzlich `i18n.aktive_sprache` und setzt sie im `finally` zurück.
- Mehrzahl im Katalog als `{one, other}` unter dem Einzahl-Schlüssel, Platzhalter der
  Newstyle-Konvention `%(num)s`.
- Rechte-Matrix: `MIT_EINMALCODE` schon in Paket 2 (A20) — `anfrage()` zieht nur dort
  einen Wiederherstellungscode; `POST /einstellungen/sprache` = angemeldet.
- `test_verlaufsabruf_bekommt_ganze_seite` prüft in Paket 2 `ist_htmx`/
  `ist_verlaufsabruf` an der Anfrage (die erste Fragment-Route kommt mit Paket 3, dort
  `test_api_pruefen.py::test_htmx_fragment_mit_push_url`).
- 503 erkennt auch PostgreSQL-Deadlocks (SQLSTATE `40P01`) neben Sperr-Zeitüberschreitung
  (`55P03`); das Protokoll nennt nur Methode und Routenvorlage.
- `THIRD-PARTY.md` (neu, Wurzel) vermerkt htmx 2.0.11 (0BSD) und Liberation Sans (OFL);
  `pruefen.js` übernimmt neben den Tasten den Fehlerhinweis und liegt im Grundlayout.
  `pruefen.css` kommt mit Paket 3, `auswertungen.css` mit Paket 4.

### Paket 3 — Supervisions-Queue, Belegvorschau, Korrektur → Regel (PR 10b-1)

- [x] **Browser-Spike** (erledigt 21.10.2026 in Chromium, Ergebnis unter „Browser-Spike“ oben; Firefox offen) (vor allen Kopfzeilentests, Ergebnis als Absatz „Spike“ in diesem Plan):
  `accounti serve` mit Testbestand, Chrome und Firefox (Playwright oder von Hand): (1) PDF im
  `<iframe>` mit der Seiten-CSP plus `form-action 'none'` und mit der strengeren Variante
  `default-src 'none'; object-src 'self'; form-action 'none'` — welche zeigt der Betrachter in
  beiden Browsern an? (2) Ein 409-Fragment über `responseHandling` wird eingetauscht, ein 500
  und ein 503 zeigen den Hinweis aus `pruefen.js`. (3) Abgelaufene Sitzung → `HX-Redirect` führt
  zur Anmeldung und danach zurück. Die gewählte PDF-CSP geht in `test_pdf_inline_mit_sicheren_kopfzeilen`.
- [x] **Testwelt** (`tests/pruefen_hilfe.py` auf `api_hilfe.webwelt` und `pruefung_hilfe`
  (`umsatz`, `buchung`, `beleg`, `kontakt`, `anlegen`)): unsichere Buchung über den echten
  `kontiere_umsaetze` mit LLM-Attrappe (Confidence 0,62, Begründung), Beleg im Archiv der
  Gesellschaft (PDF aus `tests/pdf_hilfe`, PNG, TIFF ein- und mehrseitig, XRechnung UBL/CII,
  ZUGFeRD, SVG, Text, EPS mit TIFF-Signatur), bestätigter Abgleich, AfA-Vorschlag,
  Kreditkarten-Sammelbelastung mit Abweichung, offene Nachforderung `beleg_fehlt`, `belegfrei`-Regel,
  abgeschlossenes Vorjahr mit Vorschlag; Gesellschaften a (SKR03) und b (SKR04, `bank_konto`
  1800, eigene `pruefung.kontenrahmen_datei`); Personen mit allen vier Rollen.
- [x] **Liste und Arbeitsfläche** (`api/seiten/pruefen.py`, `vorlagen/pruefen/liste.html`,
  `arbeitsflaeche.html`, `_arbeitsflaeche.html`, `_vorschlag.html`, `_korrektur.html`,
  `_tastenhilfe.html`): *Tests* `tests/test_api_pruefen.py::test_liste_mit_confidence_und_begruendung`,
  `::test_arbeitsflaeche_beleg_links_vorschlag_rechts`, `::test_konto_mit_bezeichnung_und_schluessel_mit_bedeutung`
  (bekanntes Konto mit Namen, unbekanntes nur mit Nummer), `::test_ohne_begruendung_hinweis`,
  `::test_herkunft_afa_ohne_umsatz_und_beleg`, `::test_ohne_beleg_zeigt_nachforderung_oder_belegfrei`,
  `::test_aufgaben_der_buchung_mit_zustaendigkeit`, `::test_gesperrter_vorschlag_ohne_aktionen`,
  `::test_kein_regelangebot_fuer_kreditkarte_anlagen_marktplatz`, `::test_position_und_vor_zurueck`,
  `::test_liste_seitenweise`, `::test_betrachter_sieht_keine_formulare`, `::test_fremde_gesellschaft_404`,
  `::test_nur_volle_uuid` (Präfix → 404), `::test_tastenbelegung_im_markup`,
  `tests/test_api_statisch.py::test_tasten_in_markup_und_skript_gleich`.
- [x] **Aktionen** (freigeben, korrigieren, zurückstellen): *Tests*
  `tests/test_api_pruefen.py::test_freigeben_und_weiter`, `::test_korrigieren_vorschlag_direkt`,
  `::test_korrigieren_braucht_buchen` (freigeber, verwalter → 403),
  `::test_steuerauswahl_aus_steuer_optionen` (Belegbuchung ohne „anderer Schlüssel“, USt 2/3 ohne
  „ohne Steuer“), `::test_sachkontowechsel_verlangt_steuerangabe_422` (Feld markiert, Meldung ohne
  `--`), `::test_automatikkonto_ohne_schluessel_422`, `::test_ohne_steuer_bei_beleg_verlangt_grund`,
  `::test_zurueckstellen_als_freigeber`, `::test_veralteter_stand_409`,
  `::test_doppelt_absenden_storniert_nicht`, `::test_zurueckstellen_zweimal_409`,
  `::test_queue_route_storniert_nie` (freigegebene oder `auto`-Buchung mit aktuellem Stand → 409,
  kein Storno), `::test_zurueckstellen_und_ansicht_zurueckgestellt`, `::test_htmx_fragment_mit_push_url`,
  `::test_htmx_409_fragment_mit_meldung_und_neuem_stand`, `::test_htmx_422_fragment_mit_feld`,
  `::test_ohne_htmx_303_auf_den_naechsten`, `::test_entscheidung_schliesst_kontierung_pruefen`,
  `::test_fehler_der_fachlogik_als_409_mit_meldung` (Jahressperre), `::test_skr04_gesellschaft_mit_eigenem_bankkonto`,
  `::test_keine_einmalcode_abfrage_in_der_queue`.
- [x] **Regelvorschau und gelernte Regeln** (`vorlagen/pruefen/_regelvorschau.html`,
  `regeln.html`): *Tests* `tests/test_api_regeln.py::test_vorschau_fragment_und_ohne_js`,
  `::test_vorschau_nur_per_post` (GET → 405), `::test_vorschau_ohne_recht_403`,
  `::test_vorschau_zeigt_richtung_und_gegenrichtung`,
  `::test_korrektur_mit_regel_ohne_recht_403_und_nichts_gespeichert` (Recht per `monkeypatch`
  aus `ROLLEN_RECHTE` entfernt: weder Korrektur noch Regel), `::test_regeln_liste_und_deaktivieren`,
  `::test_verwalter_deaktiviert`, `::test_muster_mit_markup_escaped`.
- [x] **Belegvorschau** (`api/seiten/belege.py`, `api/belegantwort.py`, `vorlagen/belege/beleg.html`,
  `_vorschau.html`, `_erechnung.html`): *Tests* `tests/test_api_belege.py::test_pdf_inline_mit_sicheren_kopfzeilen`
  (Typ, `inline` mit festem Namen, `nosniff`, `no-store`, CORP, CSP laut Spike, Bytes = Archiv),
  `::test_range_anfrage`, `::test_png_und_jpeg`, `::test_tiff_als_png_seiten`,
  `::test_bildbombe_wird_nicht_dekodiert`, `::test_bildbombe_auf_seite_zwei`,
  `::test_tiff_nur_mit_tiff_decoder` (EPS mit TIFF-Signatur → abgelehnt, nicht dekodiert),
  `::test_veraenderte_archivdatei_409`, `::test_xrechnung_als_lesbare_ansicht` (UBL und CII),
  `::test_zugferd_pdf_und_strukturierter_teil`, `::test_xml_svg_html_text_nie_inline`,
  `::test_dateiname_des_absenders_nie_im_kopf` (`"`, CRLF, Nicht-ASCII), `::test_typ_aus_dem_inhalt`
  (PDF mit Endung `.png`), `::test_beleg_anderer_gesellschaft_404`, `::test_datei_fehlt_404_ohne_pfad`,
  `::test_markup_in_erechnung_und_begruendung_escaped`.
- [x] **Buchungsansicht und Storno mit Einmalcode** (`api/seiten/buchungen.py`,
  `vorlagen/buchungen/buchung.html`): *Tests* `tests/test_api_buchungen.py::test_storno_kette_korrektur_und_journal_sichtbar`
  (dieselben Daten wie `accounti buchung zeige`), `::test_freigegebene_buchung_korrigieren_ist_storno_und_neubuchung`
  (Original unverändert bis auf `storniert_durch`, `buchungskorrekturen.person` = jan),
  `::test_exportierte_buchung_nur_per_storno`, `::test_korrigieren_und_stornieren_verlangen_einmalcode`
  (ohne/falscher Code 403, nichts geändert; Code verbraucht), `::test_ohne_einmalcode_bestaetigung_kein_code`
  (`auth.einmalcode_bestaetigung: false`), `::test_gesperrter_zeitraum_verlangt_datum_ohne_vorbelegung`,
  `::test_warnung_anderer_voranmeldungszeitraum`, `::test_stornieren_verlangt_grund`,
  `::test_veralteter_stand_409_kein_storno`, `::test_reines_storno_hinweis_umsatz_wieder_offen`,
  `::test_storno_eines_stornos_abgelehnt`.
- [x] **Person aus der Sitzung** (`tests/test_api_journal_person.py`):
  `::test_kein_web_eintrag_ohne_angemeldeten_benutzer` — `ACCOUNTI_BENUTZER=mallory`,
  `getpass.getuser` → „mallory“; jeder POST-Endpunkt der Registry wird mit gültigen Daten
  aufgerufen; kein neuer Journaleintrag, kein `geprueft_von`, keine Korrektur, Regel oder
  Rückfrage trägt „mallory“, alle tragen den angemeldeten Benutzer.
- [x] **Rechte-Matrix** (`tests/test_api_rechte_matrix.py`): `EinesVon` ergänzen; alle neuen
  Endpunkte in `SEITEN` (Pfade mit Konverter); `anfrage()` ersetzt `{buchung_id:uuid}`,
  `{beleg_id:uuid}`, `{regel_id:uuid}`, `{n:int}`, `{bericht}`, `{format}`, liefert `stand` und
  zieht einen Wiederherstellungscode **nur** für `MIT_EINMALCODE`;
  `::test_jede_rolle_gegen_jeden_endpunkt` und `::test_jeder_endpunkt_steht_in_der_matrix` grün;
  neu `tests/test_api_csrf.py::test_jeder_post_ohne_csrf_403_und_nichts_geaendert`.
- [x] **Akzeptanz 1 und 2 als Ende-zu-Ende-Tests** (`tests/test_akzeptanz_web.py`, Ablauf in der Tabelle
  „Spec und Akzeptanz“ unten).

**Umsetzung Paket 3 (22.10.2026) — Abweichungen vom Plan:**

- `/buchungen/{id}/korrigieren|stornieren`: erst der Prüfstand (409 verbraucht keinen
  Einmalcode), dann die fachliche Vorabprüfung (422), erst dann `bestaetige_einmalcode`
  und die Ausführung (`tests/test_api_buchungen.py::test_veralteter_stand_409_kein_storno`).
- Belegrouten: `/belege/{id}/datei` nur für PDF/PNG/JPEG (sonst 415, kein Download über
  diese Route), `/belege/{id}/seite/{n}.png` für TIFF-Seiten, `/belege/{id}/download` mit
  `default-src 'none'; sandbox` und festem Dateinamen aus der Beleg-ID; XML nie inline.
  `test_api_belege.py` hat 18 Prüfungen (einige Planpunkte zusammengefasst).
- Leere Queue nach der letzten Entscheidung: der HTMX-Weg antwortet mit `HX-Redirect` auf
  die Liste statt mit einem Fragment; ohne JS 303.
- Protokolltest heißt `test_betrieb_protokoll.py::test_queue_belege_ohne_belegtexte_im_protokoll`
  (ohne Auswertungen und CSV — die kommen mit Paket 4).
- Prüfschlange auch unter PostgreSQL geprüft (`tests/test_pruefschlange.py::test_stand_und_aktionen_unter_postgresql`,
  Stand-Prüfung unter der Schreibsperre).
- Befunde der Browserprobe (Chromium), behoben: (1) `Strg+Enter` löste den **ersten**
  Absendeknopf des Formulars aus — das war „Vorschau“ (Regelvorschau), nicht „Korrigieren“;
  jetzt steht „Korrigieren“ als erster Absendeknopf (`.hauptknopf`, auch für Enter ohne
  Skript) und `pruefen.js` sucht zuerst `button.hauptknopf`
  (`test_api_pruefen.py::test_korrigieren_ist_der_standardknopf`). (2) Der Vorschau-Knopf
  erbte `hx-disabled-elt="find button"` des Formulars und fand unter sich nichts
  (Konsolenfehler) — jetzt `hx-disabled-elt="this"`. (3) CSP-Meldungen „Applying inline
  style“ kamen von htmx: `attributesToSettle` überträgt standardmäßig `style`, und ein
  leeres `style=""` (hier von Werkzeugen gesetzt) wird so zum Inline-Stil — `style` aus
  `attributesToSettle` entfernt (`test_api_statisch.py::test_htmx_konfiguration`).
  (4) Schmale Ansicht (420 px): Formulare liefen 10 px über — `.aktionen` mit
  `minmax(0, 1fr)`, Eingaben `min-width: 0`, Abschnitte unter 60rem `overflow-x: auto`.
- Der Vorschau-Knopf heißt „Regelvorschau“ (eindeutiger als „Vorschau“ neben der
  Belegvorschau).

**Nachbesserung nach den Prüfberichten (26.10.2026)** — fachliche Prüfung `fach-10b-1.md`,
technische Prüfung `befunde-10b1-technik.md`; je Befund ein Test, der ohne die Korrektur
scheitert:

| Befund | Korrektur | Test |
|--------|-----------|------|
| Fach H1 — Muster nur erstes Wort | Vorschlag = ganzer Name der Gegenpartei ohne Rechtsform (`lernen.ohne_rechtsform`); Vorschau nennt andere Gegenparteien, Zahlungsdienst und weitere anders gebuchte Treffer; trifft das Muster andere Gegenparteien oder einen Zahlungsdienst, speichert `korrigieren` die Regel nur mit `LernWunsch.bestaetigt` (Browser: Haken `regel_bestaetigt` = Muster, sonst 422 mit Vorschau; CLI `--trotz-warnung`); Text-Muster dulden mehrfachen Leerraum | `test_lernen.py::test_mustervorschlag_ohne_rechtsform`, `::test_vorschau_warnt_vor_fremden_gegenparteien`, `::test_vorschau_warnt_vor_zahlungsdienst`, `test_pruefschlange.py::test_regel_auf_fremde_gegenparteien_nur_mit_bestaetigung`, `test_api_regeln.py::test_standardmuster_trifft_keine_fremde_gegenpartei`, `::test_breites_muster_422_mit_vorschau_und_bestaetigung`, `test_cli_lernen.py::test_korrigiere_lernen_breites_muster_nur_mit_trotz_warnung` |
| Fach M1 — Finanzkonto verlassen | `konten.finanzkonto_fehler`: Ausgabe → Finanzkonto im Haben, Einnahme → im Soll; in `korrigieren` (wenn die Buchung das Finanzkonto berührt) und in `entwurf_fuer` | `test_pruefschlange.py::test_korrektur_behaelt_das_finanzkonto`, `::test_erstattung_auf_der_falschen_seite_laesst_sich_richtigstellen`, `test_lernen.py::test_entwurf_behaelt_das_finanzkonto_auf_seiner_seite`, `test_api_pruefen.py::test_korrektur_verlaesst_das_finanzkonto_422` |
| Fach M2 — Schalter bei Belegbuchungen | `sachkonto_fuer_beleg` legt vor, wenn die Regel-Confidence unter `mapper.AUTO_SCHWELLE` liegt | `test_lernen.py::test_schalter_pruefen_gilt_auch_fuer_belegbuchungen` |
| Fach M3 — Übernahme ohne Richtung | `richtung_der_bankseite` (Bankkonto, sonst Geldkonto des Kontenrahmens); ohne Bankseite gemeldet; Verfahrensdoku und Regelseite ohne Pauschalaussage | `test_lernen.py::test_uebernahme_leitet_die_richtung_aus_der_bankseite_ab`, `test_pruefung_verfahrensdoku.py::test_verfahrensdoku_nennt_regeln_ohne_richtung` |
| Fach M4 — Freigeben ohne Prüfregel | `storno.steuer_befunde`; `freigeben(…, umgebung=)` lehnt bei Fehler ab (422), Arbeitsfläche zeigt die Befunde statt „Freigeben“; `bestaetige` ebenso | `test_pruefschlange.py::test_freigeben_prueft_die_pruefregel_steuerschluessel`, `test_api_pruefen.py::test_freigeben_mit_pruefregel_fehler_gesperrt` |
| Fach M5 — Umsatzdaten mit Beleg | `_umsatz.html` rechts über dem Vorschlag | `test_api_pruefen.py::test_umsatzdaten_auch_mit_beleg` |
| Fach M6 — CLI lernt aus Kreditkarte | `regel_lernbar` unabhängig von `nur_vorschlaege`; CLI mit `unbekannte_herkunft_lernbar` | `test_pruefschlange.py::test_lernen_nur_aus_kontierungsvorschlaegen_auch_ausserhalb_der_queue`, `test_cli_lernen.py::test_korrigiere_lernen_nicht_aus_kreditkarte` |
| Technik M1 / Fach N8 — Verwalter legt Regeln an | `lerne` und `regeln uebernehmen` über `handelnde_person(…, BUCHEN, …, (REGELN_LERNEN,))`; `FREIGABEWEGE` | `test_cli_rechte_pruefung.py::test_verwalter_legt_keine_regeln_an_deaktiviert_aber` |
| Technik M2 — TIFF mit vielen Seiten | Seiten per `seek` bis `MAX_SEITEN` statt `n_frames` | `test_api_belege.py::test_tiff_mit_sehr_vielen_seiten_liest_nur_die_ersten` |
| Technik M3 — Einmalcode bei 422 verbraucht | Probelauf der Aktion mit Rollback vor dem Code, dann Code, dann Lauf. Abweichung vom Vorschlag (Aktion bis zum Flush, Code, Commit): ohne Registry liegen Benutzer und Buchungen in derselben SQLite-Datei, die Codebestätigung wartete auf die eigene Schreibsperre | `test_api_buchungen.py::test_fachlich_abgelehnte_aktion_verbraucht_keinen_einmalcode` |
| Fach N1 — Confidence | `confidence_prozent` (`floor(round(c·100, 6))`) | `test_api_pruefen.py::test_confidence_ohne_gleitkommafehler` |
| Fach N4 — „wieder offen“ | nur, wenn der Umsatz in `offene_transaktionen(…, fuer_kontierung=True)` steht | `test_api_buchungen.py::test_storno_hinweis_nur_wenn_der_umsatz_wirklich_offen_ist` |
| Fach N6 — Doku | README `regeln liste`, betrieb `.env` laden | — |
| Fach N7 — Testlücken | Mutationen N10/N19 und der Ablauf mit Abgleich vor der Kontierung | `test_lernen.py::test_uebernahme_behaelt_die_reihenfolge_der_datei`, `::test_text_regel_aus_der_datenbank_bleibt_woertlich`, `test_akzeptanz_web.py::test_akzeptanz_1_mit_abgleich_vor_der_kontierung` |
| Technik N1 — DTD in UTF-16 | expat-Vorprüfung in `parse_sicher` (wie `importers.camt`) | `test_erechnung_parser.py::test_doctype_auch_in_utf16_abgelehnt` |
| Technik N2 — alle Buchungen je Ansicht | `repository.lade_buchungen_zu` für die Geschwister | `test_pruefschlange.py::test_arbeitsflaeche_laedt_nur_die_geschwister` |
| Technik N3 — Freitextlängen | Grund ≤ 500, „an“ ≤ 100 → 422 | `test_pruefschlange.py::test_freitexte_mit_laengengrenze` |
| Technik N5, N6 | `.haken input { flex: none; }`; Katalogwerte nur mit den Tags ihrer msgid | `test_i18n_katalog.py::test_katalogwert_nur_mit_den_tags_seiner_msgid` |

Angepasste Tests, die altes Verhalten festschrieben: das Standardmuster „erstes Wort“
(`Bürobedarf`, `Stadtwerke`, `gelernt_bürobedarf` in `test_lernen.py`, `test_api_rest.py`,
`test_akzeptanz_web.py`, `test_cli_supervisor.py`), „Übernahme ohne Richtung“
(`test_uebernahme_gelernter_eintraege_aus_datei`), der Geldkontowechsel als Vehikel
(`test_cli_supervisor.py::test_korrigiere_lernt_den_schluessel_der_neubuchung`,
`test_cli_journal_storno.py::test_cli_ausgleichsbuchung`) und `FREIGABEWEGE`
(`test_auth_dienst.py`).

Bewusst nicht behoben (Eingaben für 10c bzw. Grenze unten): Fach N2 (Meldungen ohne
JavaScript über den 303), N3 (Herkunft „korrigiert von …“ statt der LLM-Begründung), N5
(„Strg“, rohe Statuswerte, Glossar „Booking“), N9 (Lernen am Kontakt bei Herkunft `kontakt`),
der UI-Teil von H1 (Vorschau automatisch beim Haken, Treffer nach Gegenpartei gruppiert,
Händler aus dem Verwendungszweck bei Zahlungsdiensten); Technik N3 „an“ gegen die Benutzer
prüfen (Auswahlfeld in 10c), N4 (PostgreSQL ohne Trigger für `kontierungsgruende`).

**Nachprüfung, dritte Runde (26.10.2026)** — Prüfbericht zu 1d3cf59 (H-1, M-1, N-1 bis N-5);
je Befund ein Test, der ohne die Korrektur scheitert:

| Befund | Korrektur | Test |
|--------|-----------|------|
| H-1 — ohne Namen der Gegenpartei keine Warnung | `Vorschau.ohne_namen`: jeder weitere Treffer zählt als fremd (mit dem Anfang seines Verwendungszwecks), `bestaetigung_noetig` immer — 422 bzw. `--trotz-warnung` wie bei fremden Gegenparteien | `test_lernen.py::test_vorschau_ohne_namen_der_gegenpartei_verlangt_bestaetigung`, `test_pruefschlange.py::test_regel_ohne_namen_der_gegenpartei_nur_mit_bestaetigung`, `test_cli_lernen.py::test_korrigiere_lernen_ohne_namen_nur_mit_trotz_warnung`, `test_api_regeln.py::test_ohne_namen_der_gegenpartei_422_mit_vorschau_und_bestaetigung` |
| M-1 — falsch zugeordnetes Finanzkonto nicht mehr richtigzustellen (Regression aus 593216c) | `_pruefe_finanzkonto` lässt den Wechsel auf ein anderes eingerichtetes Bankkonto (`eingerichtete_bankkonten`) zu: `Bankkontowechsel` mit Warnung in `Korrektur.warnungen`, ohne Regel (422 Feld `regel`); nach dem Wechsel gilt das neue Bankkonto als Finanzkonto der Buchung; Aufwand, Kasse, nicht eingerichtete Konten weiter 422 | `test_pruefschlange.py::test_falsch_zugeordnetes_bankkonto_laesst_sich_richtigstellen`, `test_cli_supervisor.py::test_korrigiere_falsch_zugeordnetes_bankkonto` |
| N-2 — CLI lernt aus dem Kassenbuch | Kassenvorgänge (`quelle=manuell`) zählen nicht als Altbuchung ohne Herkunft | `test_cli_lernen.py::test_korrigiere_lernen_nicht_aus_dem_kassenbuch` |
| N-3 — „Co“, „AB“, „AS“, „SE“ kürzen auf ein Wort | `_MEHRDEUTIG`: kürzt nur, wenn davor zwei Wörter bleiben | `test_lernen.py::test_mustervorschlag_ohne_rechtsform` (neue Fälle) |
| N-5 — Plan veraltet | Übernahme (Richtung aus der Bankseite), Regelentwurf und Grenze „ohne Gegenpartei“ nachgezogen | — |

Nicht behoben: N-1 (TIFF mit Millionen Strips: braucht einen eigenen Leser der
TIFF-Verzeichnisse vor `Image.open`, keine Regression) und N-4 (Einmalcode bei Zahlungs- und
UStVA-Freigabe vor der Fachprüfung, Baustein 10a; das Probe-Muster aus Technik M3 verlangt dort
erst eine Prüfung der Seiteneffekte von `gib_frei` und der Zahlungsfreigabe) — beides Folgearbeit.

**Nachprüfung nach dem Zusammenführen mit main (2de9a1b)** — Prüfberichte gw-regeln,
gw-migration, gw-storno, gw-regress (fachlicher Teil; die Web-Befunde behebt ein eigener
Zweig); je Befund ein Test, der ohne die Korrektur scheitert:

| Befund | Korrektur | Test |
|--------|-----------|------|
| gw-regeln H-1 (a) — aus einer Umbuchung Giro ↔ Tagesgeld wird „1200 an 1200“ | `entwurf_fuer` und `lerne_regex`: Soll und Haben beide Zahlungsmittel (`Kontenrahmen.ist_zahlungsmittel`, neuer Abschnitt `zahlungsmittel` der Kontenrahmendateien, dazu Bankkonto, Finanzkonto des Umsatzes, eingerichtete Konten; `buchung.konten.umbuchung_fehler`) → `RegelError` Feld `regel`; CLI Exit 1 ohne Korrektur, Queue/Vorschau 422 | `test_umbuchung_geldkonten.py::test_aus_einer_umbuchung_wird_keine_regel`, `::test_lerne_regex_lehnt_umbuchung_ab`, `::test_cli_korrigiere_lernen_aus_umbuchung_exit_1_ohne_regel`, `::test_cli_lerne_umbuchung_exit_1`, `::test_web_korrektur_mit_regel_aus_umbuchung_422` |
| H-1 (b) — Soll = Haben automatisch (Regeldatei „1210 an 1200“ auf 1210, gelernte Altregeln, Gegenrichtung, LLM) | eine Schranke in `kontiere_umsaetze` für alle Quellen (Beleg, Regel, LLM, Gegenrichtung) — deckt `classify`, `bank lauf` und den REST-Lauf; der Umsatz bleibt offen (`Kontierungslauf.umbuchungen`, CLI-Hinweis, REST `kontierung.umbuchung`). OPOS läuft nicht durch `kontiere_umsaetze`: `sachkonto_fuer_beleg` (Belegbuchung und OPOS) nimmt kein Geld-, Personen-, Forderungs- oder Verbindlichkeitskonto als Sachkonto (`konten.kein_sachkonto`) — sonst „70001 an 70001“ | `::test_regeldatei_umbuchung_auf_dem_zweiten_konto_bleibt_offen`, `::test_alte_gelernte_umbuchungsregeln_buchen_nie_soll_gleich_haben`, `::test_llm_vorschlag_mit_soll_gleich_haben_bleibt_offen`, `::test_belegbuchung_nimmt_kein_geld_oder_personenkonto_als_sachkonto`, `::test_opos_verbuchen_mit_kreditorregel_bucht_nicht_kreditor_an_kreditor`, `::test_classify_meldet_die_offene_umbuchung`, `::test_bank_lauf_bleibt_offen`, `::test_rest_lauf_bleibt_offen_und_meldet_die_umbuchung` |
| H-1 (c) — Altfälle fallen nicht auf | Prüfregel `soll_gleich_haben` (Richtigkeit, Fehler; ohne stornierte Paare) | `::test_pruefen_meldet_buchungen_mit_soll_gleich_haben`, `::test_pruefregel_uebergeht_stornierte` |
| M-1 — Übernahme vor neueren Korrekturen | `lade_kontierungsregeln` ordnet nach Herkunft: übernommene hinter allen anderen gelernten, untereinander wie in der Datei (kein geschönter Zeitstempel) | `test_lernen.py::test_uebernahme_steht_hinter_vorhandenen_gelernten_regeln`, `test_cli_lernen.py::test_regeln_uebernehmen_hinter_der_korrektur` |
| M-2 — `pruefen`/`confidence` gehen verloren | Einträge mit `pruefen: true` oder `confidence` < 1 bleiben in der Regeldatei (greifen dort wie bisher) und werden genannt — **keine Migration**: die Regeldatei kennt das Kennzeichen schon; ein Feld je gelernter Regel bräuchte Schema, Journal-Bestand, Liste, Browser und REST, und im Browser lässt sich ohnehin keine solche Regel anlegen. Ebenso Umbuchungen | `test_lernen.py::test_uebernahme_laesst_eintraege_mit_pruefkennzeichen_in_der_datei`, `test_cli_lernen.py::test_regeln_uebernehmen_nennt_was_in_der_datei_bleibt` |
| M-3 — SKR04-Ausgangsbeleg auf 8400 (besteht auf main) | `buchung.konten.erloeskonten` je Kontenrahmen (SKR04 4400/4300/4200; steuerfrei aus `KENNZIFFERN_KONTEN`: 4125/4120/4100/4336; OSS 4320 zur Prüfung) für `mit_beleg` und `opos/verbuchung` | `test_erloeskonten_kontenrahmen.py` (SKR03/SKR04, EÜR Kz 112 ohne „nicht zugeordnet“), `test_opos_verbuchung.py::test_ausgangsrechnung_im_skr04_auf_skr04_erloese`, `::test_steuerfreie_erloese_im_skr04` |
| gw-regeln N-1 — „davon heute anders gebucht“ der falschen Richtung | `Vorschau.gegenrichtung_anders`, Vorlage `_regelvorschau.html` | `test_lernen.py::test_vorschau_zaehlt_anders_gebuchte_je_richtung`, `test_api_regeln.py::test_vorschau_gegenrichtung_zaehlt_ihre_eigenen_anders_gebuchten` |
| gw-regeln N-2 — kaputtes Muster/`feld`: 500 bzw. Traceback | Lader: `re.error`, unbekanntes `feld`, YAML-Fehler, keine Liste → `KonfigurationError` mit Regelname; der REST-Lauf antwortet darauf 409 | `test_regeln_loader.py::test_fehlerhafte_regeldatei_meldet_konfigurationsfehler`, `::test_classify_mit_kaputtem_muster_meldung_statt_traceback`, `::test_rest_lauf_mit_kaputter_regeldatei_409_statt_500` |
| gw-migration N-1 / gw-regress N1 — Vorabstand: „0 Migration(en)“, dann OperationalError | `db upgrade` prüft das Schema gegen die Tabellen und Spalten des Codes (`fehlendes_schema`) und bricht mit abgeleitetem Stand und verlustfreiem Weg ab; `db upgrade --aus-schema` stempelt zurück (`purge`) und migriert | `test_db_upgrade.py::test_db_upgrade_erkennt_den_vorabstand_und_bricht_mit_weg_ab`, `::test_db_upgrade_aus_schema_holt_die_migrationen_verlustfrei_nach` |
| gw-migration N-2 — `lerne --name` von main nicht übernommen | `regeln uebernehmen --name`; die Ausgabe nennt die Einträge, die in der Datei bleiben | `test_lernen.py::test_uebernahme_mit_namen_und_hinweis_auf_eigene_eintraege` |
| gw-migration N-3 — Traceback auf nicht migrierter Datenbank | die Wurzelgruppe der CLI fängt „no such column/table“ (PostgreSQL 42703/42P01) und nennt `accounti db upgrade` | `test_db_upgrade.py::test_cli_auf_nicht_migrierter_datenbank_hinweis_statt_traceback` |
| gw-storno N3 — Einmalcode vor der Fachprüfung verbraucht (besteht auf main) | Fachprobe nach der Rechteprüfung und vor dem Code (`handelnde_person(vorab=…)`, `befehle.fachprobe`) für `buchung storniere`, `korrigiere`, `lerne`, dazu `bestaetige` | `test_cli_einmalcode_fachprobe.py` |

Angepasst: `test_api_rest.py::test_laeufe_anstossen` (neuer Schlüssel `umbuchung`),
`test_pruefung_regeln.py::test_alle_regeln_aus_der_spec_sind_registriert`
(`soll_gleich_haben`).

**Nachprüfung nach dem Zusammenführen mit `main` (26.10.2026)** — Prüfberichte gw-web
(N1–N7) und gw-storno (N1, N2) zu 2de9a1b; Tests in `test_api_web_nachpruefung.py`, je ohne
die Korrektur rot:

| Befund | Korrektur | Test |
|--------|-----------|------|
| gw-web N1 — Erfolgsmeldungen der Queue im Englischen deutsch | `ERLEDIGT` und „Regel deaktiviert.“ als `Text` (übersetzt wird nur `Text`) | `::test_erfolgsmeldungen_der_queue_englisch_mit_und_ohne_htmx` |
| gw-web N2 — „²“ gibt 500, „٩“ gilt als 9, „４９３０“ als Konto | `pruefen.ascii_zahl` (Seite, Steuerschlüssel) und `formularkonto` (Soll/Haben in Queue, Regelvorschau, `/buchungen/{id}/korrigieren`): nur ASCII-Ziffern, sonst 422 bzw. Seite 1; Content-Length in `formular.py` und `rest/belege.py` ebenso; der Zeitraum der USt-VA-Freigabe vor dem Einmalcode | `::test_seite_mit_unicode_ziffer_ist_seite_eins`, `::test_steuer_mit_unicode_ziffer_422_auf_allen_wegen`, `::test_konto_mit_unicode_ziffern_422`, `::test_formular_und_rest_koerper_mit_unicode_laenge`, `::test_ustva_zeitraum_mit_unicode_ziffern_422_ohne_code` |
| gw-web N3 — Storno-Fehler im Korrektur-Formular | `aktion_formular` (korrektur/storno): Markierung und Eingaben nur im abgesendeten Formular | `::test_storno_fehler_im_storno_formular`, `::test_korrektur_fehler_bleibt_im_korrektur_formular` |
| gw-web N4 — Sprachwahl nach einem POST: 405 | `vorlagen.ansichtspfad`: nach einem POST die nächste Seite darüber, die GET beantwortet (sonst `/`); `sicheres_ziel` bleibt | `::test_sprachwahl_nach_post_fuehrt_auf_eine_get_seite` |
| gw-web N5 — Rohwerte von Enums, „Strg“ | Filter `bezeichnung` (`vorlagen.BEZEICHNUNGEN` je Enum-Klasse: Buchungs-, Beleg-, Aufgabenstatus, Belegart, Profil der E-Rechnung); „Strg“ übersetzbar („Ctrl“) | `::test_jeder_statuswert_hat_eine_bezeichnung`, `::test_statuswerte_und_tasten_lesbar_in_beiden_sprachen`, `::test_profil_der_e_rechnung_lesbar` |
| gw-web N6 — Regelseite ohne Gegenrichtung | Text nennt die Gegenbuchung zur Prüfung (DE, EN) | `::test_regelseite_nennt_die_gegenbuchung_zur_pruefung` |
| gw-web N7 — „Not Found“, „Method Not Allowed“, „Formular zu groß“ | `app.fehlertext`: Statusphrase von Starlette als `Text` (REST-API unverändert); Formularmeldungen als `Text`; die Sprachwahl am Benutzer gilt auch für Fehler vor der Seite (CSRF, Formular: `request.state.benutzersprache`; 404/405 ohne Route: `sitzung.merke_benutzersprache`) | `::test_starlette_und_formulartexte_uebersetzt`, `::test_formular_und_csrf_fehler_in_der_sprache_des_benutzers` |
| gw-storno N1 — `KontenrahmenError` gibt 500 | `_fehlerbild`: `KonfigurationError` und `KontenrahmenError` → 409 mit Meldung (Queue und `/buchungen/{id}`) | `::test_fehlerhafte_kontenzuordnung_409_statt_500` |
| gw-storno N2 — Doppelklick: Fehlversuch bzw. zweiter Code verbraucht | Abschlusssperre je Gesellschaft (Server-Prozess): Stand erneut prüfen, dann Code, dann Lauf — der zweite Klick bekommt 409 ohne Fehlversuch und ohne Code (Grenze oben). Die Queue fragt keinen Code ab und vergleicht den Stand unter der Schreibsperre: dort schon 409 | `::test_doppelklick_mit_demselben_code_409_ohne_fehlversuch`, `::test_doppelklick_verbraucht_keinen_zweiten_code`, `::test_doppelklick_in_der_queue_409` |

Hinweis außerhalb der Web-Schicht: `buchung/konten.pruefe_kontonummer` prüft mit `\d` und
nimmt in der CLI vollbreite Ziffern als Kontonummer an (Folgearbeit Fachkern).

**Nachprüfung nach dem Merge, Runde 3 (02.11.2026)** — Prüfberichte gw2-regeln, gw2-umbuchung,
gw2-web, gw2-betrieb, gw2-merge mit den Gegenprüfungen (`gw2b-ergebnis.json`); je Befund ein
Test, der ohne die Korrektur scheitert:

| Befund | Korrektur | Test |
|--------|-----------|------|
| gegen:regeln:0 (Mittel) — SKR04: OSS-Fernverkäufe auf 4320 fehlen in der OSS-Meldung | Länderkonten im SKR04 wie im SKR03 (4320–4327 zu 8320–8327; `umsatzsteuer.oss_erloeskonten`, `oss_konto_land`); OSS-Meldung, Lieferschwelle, Kz 45 und Prüfregel `pflichtangaben` lesen die Konten des Kontenrahmens (im SKR04 auch die Marktplatzkonten 8320–8327 — Klasse 8 ist dort frei). Ein Land ohne eigenes Konto geht nicht mehr auf das Sammelkonto (die Meldung zählte es als FR), sondern auf „Erlöse“ zur Prüfung, mit Hinweis | `test_oss_kontenrahmen.py` |
| gegen:regeln:1 (Mittel) — zweiter Lauf von `regeln uebernehmen` stellt seinen Eintrag vor früher übernommene | `kontierungsregeln.rang`: Stelle des Eintrags in der Datei (in `d5a849692843`, die Migration ergänzt die Spalte an einer schon angelegten Tabelle); `lade_kontierungsregeln` ordnet übernommene nach `rang`, bei gleicher Stelle den früher übernommenen zuerst | `test_regeldatei_werte.py::test_zweiter_lauf_behaelt_die_reihenfolge_der_datei` |
| gegen:regeln:3 (Mittel) und gw2-regeln N-1, gw2-web B3 — Werte der Regeldatei ungeprüft, Latin-1/Verzeichnis 500 | `regeln_loader.pruefe_eintrag`: Konten 4–8 Ziffern (eine Zahl mit führender Null bleibt Text — eigener YAML-Lader ohne Oktalzahlen), Muster nicht leer, Steuerschlüssel und `confidence` Zahlen; `lies_regeldatei`: nicht UTF-8, Verzeichnis, kein YAML, keine Liste → `KonfigurationError`. `regeln uebernehmen` prüft mit demselben Lader (Grund je ungültigem Eintrag) | `test_regeldatei_werte.py`, `test_regeln_loader.py::test_rest_lauf_mit_unlesbarer_regeldatei_409_statt_500` |
| gw2-merge B1 — `feld: gegenkonto_iban` abgelehnt | wieder zulässig (Lader und `Feld` der gelernten Regeln) | `test_regeldatei_werte.py::test_feld_gegenkonto_iban_bleibt_wirksam` |
| gegen:umbuchung:0 (Mittel) — Belegbuchung und OPOS verwerfen legitime Sachkonten | `kein_sachkonto` nur noch für Zahlungsmittel, Personenkonten und Forderungen/Verbindlichkeiten aus LuL (neuer Abschnitt `lul_konten`: SKR03 1400–1499, 1600–1699; SKR04 1200–1299, 3300–3399) — Wertpapiere (1348, § 266 Abs. 2 B III HGB), Festgeld 1290/1890, Rückdeckung 1355, Verrechnungskonten bleiben Sachkonto; die Begründung nennt ein übergangenes Konto; `lerne_sachkonto` lernt ein solches Konto nicht (Hinweis, die Korrektur gilt) | `test_umbuchung_geldkonten.py::test_bestandskonten_bleiben_sachkonto_eines_belegs`, `::test_uebergangenes_sachkonto_steht_in_der_begruendung`, `::test_lerne_sachkonto_lehnt_geldkonto_ab_korrektur_bleibt` |
| gw2-umbuchung N-2 — Regel gegen Geldtransit abgelehnt | Abschnitt `geldtransit` (1360/1460): ein Zahlungsmittel ohne Kontoauszug, `umbuchung_fehler` lässt Regeln dagegen zu | `::test_regel_gegen_geldtransit_bleibt_lernbar` (angepasst: `test_aus_einer_umbuchung_wird_keine_regel` ohne den Geldtransit-Fall) |
| gw2-umbuchung N-1 — alte Kontenzuordnung ohne `zahlungsmittel`; Vorschau ≠ Speichern | fehlende Abschnitte (`zahlungsmittel`, `geldtransit`, `lul_konten`) kommen aus dem mitgelieferten Kontenrahmen gleichen Namens; die Regelvorschau nimmt denselben Kontenrahmen samt eingerichteter Konten wie das Speichern | `::test_alte_kontenzuordnung_ohne_zahlungsmittel_nimmt_die_mitgelieferten` |
| gw2-merge B2 — mit `--lernen` ging bei einer Umbuchung auch die Korrektur verloren | `UmbuchungError`: die Korrektur gilt, nur ohne Regel, mit Hinweis „Keine Regel gelernt …“ (CLI und Queue) | `::test_cli_korrigiere_lernen_aus_umbuchung_ohne_regel`, `::test_web_korrektur_mit_regel_aus_umbuchung_ohne_regel` (angepasst: vorher Exit 1 bzw. 422) |
| gegen:web:0 (Mittel), gw2-umbuchung N-3 — Soll = Haben von Hand | `konten.soll_gleich_haben` in der Fachfunktion `storno.korrigiere` (CLI, `/buchungen`, REST), früh in `pruefschlange._konten` (Queue, Feld `haben`) und in `buche_kasse` (Gegenkonto = Kassenkonto) | `test_soll_gleich_haben_manuell.py` |
| gw2-merge B3 — Altvorschlag „1210 an 1210“ freigebbar | `freigeben` lehnt Soll = Haben ab (`PruefregelError`, auch ohne Umgebung); `steuer_befunde` zeigt den Fehler, der Knopf „Freigeben“ fehlt | `test_soll_gleich_haben_manuell.py::test_altvorschlag_soll_gleich_haben_nicht_freigeben` |
| gw-storno N3 Rest (gw2-betrieb B-1, B-2) — Code vor der Fachprüfung | Fachprobe vor dem Code auch für `regeln deaktivieren`, `regeln uebernehmen`, `kasse anfangsbestand/buchen/storno`, `periode schliessen/oeffnen` | `test_cli_einmalcode_fachprobe.py` (neue Fälle; `test_korrigiere_lernen_…` prüft jetzt Soll = Haben) |
| gw2-web — USt-VA-Freigabe verbraucht den Code vor Zeitraum- und Fachprüfung; Doppelklick auf Freigeben (USt-VA, Zahlungslauf) zählt einen Fehlversuch | wie Storno: die Freigabe zur Probe (zurückgerollt; 422/409/404 ohne Code), dann unter der Freigabesperre der Gesellschaft (`einmalcode.freigabesperre`, dieselbe wie für `/buchungen`) Probe, Code, Freigabe; die USt-VA-Probe meldet 409, wenn genau diese Werte schon offen freigegeben sind | `test_api_web_nachpruefung.py::test_ustva_fachfehler_verbraucht_den_code_nicht`, `::test_ustva_doppelklick_409_ohne_fehlversuch`, `::test_zahlungslauf_doppelklick_409_ohne_fehlversuch` |
| gw2-web — mehr als 4300 Ziffern bzw. ab 2^63: 500 | `ascii_zahl` höchstens 18 Stellen; `/belege/{id}/seite/{n}.png` und `/freigaben/zahlungslauf/{nr}` lesen die Zahl selbst (404) | `::test_grosse_zahlen_ohne_500` |

Kein Fehler (gegen:regeln:2): ein Eintrag mit `pruefen` bleibt in der Datei und greift hinter
den gelernten Regeln — dokumentiert (Grenze unten, CLI-Ausgabe).

**Zweites Zusammenführen mit main (2305d47, Paket C #35)** — Migrationskette `a14acef69fae` →
`46371a6681c2` (`belege.steuerkennzeichen`) → `d5a849692843` → `e7153706b43a` (ein Kopf,
`SCHEMA_STAND`). `db/upgrade.py`: eine Schemaprüfung (`fehlendes_schema`: fehlende Tabellen
und Spalten, vor dem Lauf, wenn nichts offen ist, und danach) statt zweier — `_pruefe_spalten`
von Paket C entfällt, ihre Meldung (Stand laut Schema, `alembic stamp --purge …`) steht in
der einen Meldung neben `--aus-schema`; ein Vermerk mit zwei Zeilen ergibt eine Meldung statt
eines `CommandError`. Tests: `test_db_upgrade.py::test_db_upgrade_erkennt_vermerk_ohne_die_
migrationen_davor` (keine Doppelmeldung), `::test_db_upgrade_aus_schema_fuer_den_zweig_von_
paket_c`, `::test_db_upgrade_vorabstand_ohne_steuerkennzeichen_und_rang`,
`::test_db_upgrade_vermerk_mit_zwei_zeilen`, `::test_postgresql_zweig_von_paket_c_aus_schema`,
`test_migration_web.py::test_migration_ergaenzt_rang_an_vorhandener_tabelle`. OPOS: das
Erlöskonto des OSS-Fernverkaufs aus `erloeskonten` (Länderkonten je Kontenrahmen), die
OSS-Steuer wie Paket C auf `OSS_UST_KONTEN_SKR03` (1777xx, sonst 1779 — eigene Konten, auch im
SKR04; Grenze), das Bestimmungsland aus der Rechnung.

### Paket 4 — Auswertungen (PR 10b-2)

- [ ] **Kontenrahmen: Ergebnisverwendung** (`abschluss/kontenrahmen.py`: Schlüssel
  `ergebnisverwendung`, `Kontenrahmen.ist_ergebnisverwendung`; `kontenrahmen_skr03.yaml`
  2480–2489, 2495–2499, 2795–2799, 2840–2889; `kontenrahmen_skr04.yaml` 7700–7799): *Tests*
  `tests/test_abschluss_kontenrahmen.py::test_ergebnisverwendung_hat_euer_kz_strich` (jedes Konto
  der Spannen: Erfolg im Modus Bilanz, Kz „-“ in beiden Richtungen),
  `::test_eigene_kontenzuordnung_ohne_ergebnisverwendung_laedt`.
- [ ] **BWA-Schema** (`bwa/schema.py`, `bwa/schema_skr03.yaml`, `bwa/schema_skr04.yaml`, Abschnitt
  `bwa` in der Konfiguration): zuerst die „(prüfen)“-Stellen der Startzuordnung anhand der
  DATEV-Kontenlisten 2026 und der DATEV-Hilfe zur BWA Form 01 entscheiden, Quellen in den
  Dateikopf. *Tests* `tests/test_bwa_schema.py::test_leitkonten` (SKR03, SKR04, Tabelle
  „Leitkonten“), `::test_jedes_erfolgskonto_genau_eine_engste_zeile` (0000–9999 mit
  `art(nr, "bilanz") is ERFOLG`, Ergebnisverwendung zählt mit, keine zwei gleich engen Treffer),
  `::test_einklang_mit_der_euer` (Tabelle „Erlaubte Kombinationen“, Ausnahmen mit Grund),
  `::test_richtung_wie_euer` (Einnahme-Kz nur in Ertragszeilen, Ausgabe-Kz nur in Aufwandszeilen,
  Ausnahmen Forderungsverluste und 8959/4699), `::test_steuer_privat_bestand_nie_in_der_bwa`
  (auch bei EÜR), `::test_klasse_7_skr03_nicht_in_der_bwa`, `::test_formel_nur_fruehere_zeilen`,
  `::test_formel_ohne_eval`, `::test_eigenes_schema`.
- [ ] **`bwa_zeile` entfernen** (`src/accounti/pruefung/skr03.yaml`, `models.Konto`): *Test*
  `tests/test_bwa_schema.py::test_keine_bwa_zeile_in_mitgelieferten_dateien`;
  `tests/test_pruefung_regeln.py` bleibt grün (Schutz).
- [ ] **BWA-Rechnung** (`bwa/berechnung.py` neu, `models.BWAZeile` ergänzt,
  `konfiguration.lade_wirtschaftsjahr_beginn` aus `befehle/betrieb.py` herausgelöst und von
  `befehle/betrieb.py`, `befehle/gesellschaft.py`, `export/datev_stammdaten.py` genutzt): *Tests*
  `tests/test_bwa.py::test_handgerechnete_bwa` (Monat, kumuliert, Vorjahr, Abweichung),
  `::test_saldiert_je_zeile`, `::test_engste_spanne` (4510 → Betriebliche Steuern, 4520 →
  Fahrzeugkosten), `::test_storno_hebt_sich_auf`, `::test_steuer_nicht_in_der_bwa`,
  `::test_ergebnisverwendung_nicht_in_der_bwa`, `::test_vorschlaege_nicht_enthalten_aber_gezaehlt`,
  `::test_vorlaeufiges_ergebnis_gleich_erfolgssalden` (EÜR und Bilanz, gegen `Susa.ergebnis`
  bereinigt um Ergebnisverwendung bzw. Steuerkonten), `::test_kumuliert_ab_abweichendem_wirtschaftsjahr`,
  `::test_ohne_vorjahr_hinweis`, `::test_festschreibungsstand_im_hinweis`,
  `::test_abweichung_prozent_bei_null_und_negativ`, `::test_skr04`, `::test_konten_je_zeile_fuer_absprung`,
  `::test_bewegungen_einmal_geladen`; `tests/test_cli_gesellschaft.py` und
  `tests/test_betrieb_aufbewahrung.py` bleiben grün (Schutz für den verschobenen Leser).
- [ ] **Kontenblatt** (`abschluss/kontenblatt.py`): *Tests*
  `tests/test_kontenblatt.py::test_bewegungen_gegenkonto_laufender_saldo`,
  `::test_endsaldo_gleich_susa`, `::test_steuerzeile_auf_dem_steuerkonto`, `::test_eb_wert`
  (auch EB-Rahmen aus 7), `::test_von_mit_uebertrag`, `::test_hinweis_ohne_saldovortrag`,
  `::test_personenkonto`, `::test_beleg_id_direkt_und_ueber_abgleich`, `::test_storno_gekennzeichnet`,
  `::test_hinweis_kalenderjahr_bei_abweichendem_wirtschaftsjahr`.
- [ ] **Bericht, CSV, PDF** (`auswertung/bericht.py`, `auswertung/ausgabe.py`;
  `abschluss/ausgabe.susa_csv` auf den gemeinsamen Schreiber): *Tests*
  `tests/test_auswertung_ausgabe.py::test_csv_formelinjektion_entschaerft`,
  `::test_csv_format_wie_cli`, `::test_csv_unabhaengig_von_der_sprache`,
  `::test_pdf_enthaelt_werte` (Text mit pypdf auslesen), `::test_pdf_englisch_kontenbezeichnung_deutsch`,
  `::test_pdf_zeilengrenze`; `tests/test_cli_abschluss.py` bleibt grün (Schutz).
- [ ] **CLI** (`cli.py::bwa` mit `--db`, `--config`, `--csv`, `--pdf`; `befehle/abschluss.py::kontenblatt`
  neu und `susa --pdf`; `cli.py::opos_liste`/`opos_staffel` mit `--csv`, `--pdf`, `--config`):
  *Tests* `tests/test_cli_auswertung.py::test_bwa_statt_platzhalter`, `::test_bwa_period_wie_bisher`,
  `::test_bwa_csv_pdf`, `::test_kontenblatt_csv_pdf`, `::test_opos_liste_und_staffel_csv`,
  `::test_susa_pdf`, `::test_mit_gesellschaft` (`--gesellschaft b` für `bwa`, `opos liste`,
  `abschluss kontenblatt`).
- [ ] **Seiten** (`api/seiten/auswertungen.py`, `vorlagen/auswertungen/*.html`): *Tests*
  `tests/test_api_auswertungen.py::test_seiten_ohne_parameter_200`,
  `::test_uebersicht_kennzahlen_mit_vorjahr`, `::test_bwa_mit_vorjahr`,
  `::test_drilldown_bwa_kontenblatt_buchung_beleg`, `::test_susa_wie_cli`,
  `::test_opos_staffel_beschriftung_stand_heute`, `::test_festschreibungsstand_sichtbar`,
  `::test_export_gleich_cli` (parametrisiert: bwa, susa, kontenblatt, opos × csv, pdf — CSV
  bytegleich, PDF mit denselben Werten), `::test_export_unbekannter_bericht_404`,
  `::test_export_dateiname_fest`, `::test_nur_aktive_gesellschaft`, `::test_englisch_zahlen_und_monate`.

### Abschluss (je PR)

- [x] **Protokoll** (`tests/test_betrieb_protokoll.py` ergänzt; für 10b-1 als
  `::test_queue_belege_ohne_belegtexte_im_protokoll`, Auswertungen und CSV mit 10b-2):
  `::test_queue_belege_auswertungen_ohne_belegtexte_im_protokoll` — Durchlauf mit
  unverwechselbaren Markern in Verwendungszweck, Lieferant, Begründung, Belegdatei, E-Rechnung,
  Regelmuster, Rückfragetext, Einmalcode, CSV; die gesammelte Protokollausgabe enthält keinen davon
  (auch nicht bei 409/404/422/503/500); im Zugriffsprotokoll stehen Routenvorlagen.
- [x] **Migration gegen jede Datenbank** (erledigt 22.10.2026: SQLite und PostgreSQL 16 im Test
  und von Hand — Rundlauf unten; nur PR 10b-1): `alembic upgrade head` als Unterprozess
  gegen SQLite im Test, gegen PostgreSQL über `tests/pg_hilfe.mit_postgresql`
  (`ACCOUNTI_TEST_PG`) und in der Docker-Probe wie in 10a — für die Systemdatenbank **und** jede
  Gesellschaftsdatenbank; danach `compare_metadata` ohne Abweichung für die neuen Tabellen und die
  Spalte (`tests/test_migration_web.py::test_schema_gleich_metadaten`).
- [x] **Sicherung** (`tests/test_betrieb_sicherung.py` ergänzt, SQLite und PostgreSQL): Rundlauf mit
  `kontierungsgruende` und `kontierungsregeln` (Zeilen gleich, Nur-anfügen-Trigger beim
  Zurückspielen nicht im Weg und danach wirksam, `journal pruefen` danach in Ordnung) — die
  Sicherung selbst ist generisch (kein Code).
- [x] **Browserprobe** (erledigt 22.10.2026 in Chromium, Ergebnis unten; Firefox offen) (vom Umsetzer durchzuführen, Ergebnis im Plan festhalten wie die
  Docker-Probe in 10a): `accounti serve` mit Testbestand; Chrome und Firefox: PDF im Rahmen
  sichtbar (mit der gewählten Antwort-CSP), TIFF, E-Rechnung, Tasten `j k f e r z b ?`,
  `Strg+Enter`, **`Strg+F` löst nichts aus**, gehaltenes `f` gibt nur einmal frei, Kürzel
  abschaltbar, HTMX-Austausch ohne CSP-Fehler in der Konsole, **409/422 im HTMX-Weg sichtbar**
  (Steuerangabe beim Sachkontowechsel), **abgelaufene Sitzung führt zur Anmeldung** (nicht ins
  Fragment), Storno mit Einmalcode auf `/buchungen/{id}`, 503 während eines laufenden
  `bank lauf`, Zurück-Taste, Sprache wechseln, Druck/Download von CSV und PDF, schmale Ansicht.
- [x] **Gegnerische Prüfung** (Runde 1 = Befunde der Browserprobe, siehe „Umsetzung Paket 3“;
  eine weitere Runde durch eine zweite Person steht aus), `pytest`, `ruff` (ohne Cache), `mypy`
  grün; Checkboxen abgehakt; Doku-Bausteine für Paket 1–3 eingearbeitet (10b-1).

**Abschluss PR 10b-1 (22.10.2026):**

- Migrationen `d5a849692843_add_kontierung` und `e7153706b43a_add_benutzer_sprache` (auf
  `ddc9a184ddb4`, ein Head). Rundlauf von Hand gegen SQLite (ini-Kopie, Scratch-Datenbank):
  `upgrade head`, `accounti check`, Nur-anfügen-Trigger von Hand geprüft, `downgrade -1`,
  `upgrade head`; gegen PostgreSQL 16 (Container `accounti-test-pg10b`, nur 127.0.0.1, danach
  entfernt) derselbe Rundlauf plus `tests/test_migration_web.py::test_postgresql_rundlauf`,
  `test_betrieb_sicherung.py` (Kontierungstabellen), `test_pruefschlange.py` (PG),
  `test_betrieb_laufsperre.py`, `test_pruefung_nebenlaeufigkeit.py` mit `ACCOUNTI_TEST_PG`.
- Browserprobe (Chromium 1.59.1 über Playwright, `accounti serve` auf 127.0.0.1:8472 mit
  Scratch-Bestand aus `examples/`, Benutzer mit TOTP): PDF im Rahmen sichtbar (Antwort-CSP
  mit `form-action 'none'`), JPEG als Bild, XRechnung als lesbare Ansicht ohne Rahmen; Tasten
  `j k f e r z b ?` und `Strg+Enter`; `Strg+F` löst nichts aus; gehaltenes `f` gibt genau einmal
  frei; Kürzel in der Hilfe abschaltbar (localStorage, dann kein POST auf `f`); HTMX-Austausch
  ohne CSP-Fehler in der Konsole (nach Befund 3); 422 beim Sachkontowechsel im HTMX-Weg mit
  markiertem Feld, 409 im Test; abgelaufene Sitzung → `HX-Redirect` zur Anmeldung mit `weiter`
  und zurück zur Arbeitsfläche; Storno mit Einmalcode auf `/buchungen/{id}` (englische
  Oberfläche); Zurück- und Vorwärts-Taste nach `hx-push-url`; Sprache wechseln (`lang`,
  Titel „Review · accounti“); schmale Ansicht 420/360 px ohne Seitenscroll. Bildschirmfotos
  DE/EN liegen beim Umsetzer. **Nicht geprobt:** Firefox (nicht installiert), TIFF im Browser
  (nur TestClient), 503 während eines laufenden `bank lauf` (nur TestClient mit
  `OperationalError`), Druck sowie CSV/PDF (Paket 4).

---

## Dateien

**Neu (PR 10b-1):** `src/accounti/i18n/__init__.py`, `i18n/en.yaml` ·
`src/accounti/buchung/pruefschlange.py`, `buchung/konten.py` · `src/accounti/klassifikation/lernen.py` ·
`src/accounti/belege/zuordnung.py` · `src/accounti/models/kontierung.py`, `db/tabellen_kontierung.py`,
`db/repo_kontierung.py` · `src/accounti/befehle/regeln.py` · `src/accounti/api/seiten/pruefen.py`,
`buchungen.py`, `belege.py`, `sprache.py` · `src/accounti/api/belegantwort.py`, `api/htmx.py`,
`api/handeln.py`, `api/einmalcode.py` (aus `seiten/freigaben.py`) ·
`src/accounti/api/vorlagen/pruefen/` (`liste.html`, `arbeitsflaeche.html`, `_arbeitsflaeche.html`,
`_vorschlag.html`, `_korrektur.html`, `_regelvorschau.html`, `_tastenhilfe.html`, `regeln.html`),
`vorlagen/buchungen/buchung.html`, `vorlagen/belege/` (`beleg.html`, `_vorschau.html`,
`_erechnung.html`), `vorlagen/_makros.html` · `src/accounti/api/statisch/htmx-2.0.11.min.js`,
`LIZENZ-htmx.txt`, `pruefen.js`, `pruefen.css` · `alembic/versions/<rev>_add_kontierung.py`
(auf `ddc9a184ddb4`), `alembic/versions/<rev>_add_benutzer_sprache.py` · Tests wie oben,
`tests/pruefen_hilfe.py`.

**Neu (PR 10b-2):** `src/accounti/bwa/schema.py`, `bwa/schema_skr03.yaml`, `bwa/schema_skr04.yaml` ·
`src/accounti/abschluss/kontenblatt.py` · `src/accounti/auswertung/__init__.py`, `bericht.py`,
`ausgabe.py` · `src/accounti/api/seiten/auswertungen.py` · `vorlagen/auswertungen/`
(`uebersicht.html`, `bwa.html`, `susa.html`, `kontenblatt.html`, `opos.html`) ·
`api/statisch/auswertungen.css` · Tests wie oben.

**Geändert (PR 10b-1):** `models/__init__.py` (`Klassifikationsergebnis.regel`), `models/auth.py`
(`Recht.REGELN_LERNEN`, `Benutzer.sprache`), `db/tabellen_auth.py`, `db/repo_auth.py`,
`auth/dienst.py` (`setze_sprache`), `auth/cli.py` (`pruefe_recht_in` mit mehreren Rechten),
`auth/einstellungen.py` (Beschreibung `einmalcode_bestaetigung`) · `db/__init__.py`
(`GESCHUETZT`) · `pruefung/storno.py` (`StornoError` mit `meldung`/`feld`/`cli`,
`steuer_optionen`, `lade_korrekturumgebung`), `pruefung/ereignisse.py` (`erfasse` für Regeln),
`pruefung/journal.py` (`BESTAND`), `pruefung/verfahrensdoku.py` (gelernte Regeln, `regeln_datei()`)
· `befehle/__init__.py` (`handelnde_person(…, weitere=…)`), `befehle/buchung.py`
(`lade_korrekturumgebung`) · `betrieb/aufbewahrung.py` (`BESTAND`) · `klassifikation/engine.py`
(`Regel.richtung`), `klassifikation/regeln_loader.py` (Feld `richtung`), `klassifikation/llm.py`
(Modellname im Ergebnis), `buchung/kontierung.py`, `buchung/mit_beleg.py`, `opos/verbuchung.py`,
`bank/kreditkarte.py`, `anlagen/lauf.py`, `anlagen/abgang.py`, `anlagen/dienst.py`,
`integrationen/auszahlung.py`, `integrationen/buchung.py` (Herkunft) · `konfiguration.py`
(`Buchhaltung.gelernte_regeln`) · `cli.py` (`classify`, `bank lauf`, `opos verbuchen`, `review`,
`bestaetige`, `korrigiere`, `lerne`; `_regel_speichern` und `_lerne_sachkonto` entfallen) ·
`api/rest/laeufe.py` (`lade_regelwerk`) · `api/vorlagen.py`, `api/app.py` (Fehlerseite mit `Text`,
HTMX-Wege, 503), `api/sitzung.py` (`HX-Refresh` am CSRF-Fehler, Texte), `api/seiten/*.py`
(Texte; `freigaben.py` importiert `api/einmalcode`), `api/server.py` und `api/dienste.py`
(Schemaprüfung), `api/einstellungen.py` (`sprache`, `max_vorschau_megapixel`),
`api/vorlagen/*.html` (10a), `api/statisch/accounti.css` (Sprachauswahl, Ladeanzeige,
Fehlerhinweis) · `tests/test_api_rechte_matrix.py`, `tests/test_cli_supervisor.py`
(`test_korrigiere_lernen`, `test_korrigiere_lernt_den_schluessel_der_neubuchung`),
`tests/test_cli_gesellschaft.py::test_regeln_je_gesellschaft_auch_in_der_cli`,
`tests/test_betrieb_protokoll.py`, `tests/test_betrieb_sicherung.py` ·
`config/accounti.example.yaml`.

**Geändert (PR 10b-2):** `models/__init__.py` (`BWAZeile`; `Konto.bwa_zeile` entfällt) ·
`abschluss/kontenrahmen.py`, `abschluss/kontenrahmen_skr03.yaml`, `…_skr04.yaml`
(`ergebnisverwendung`) · `pruefung/skr03.yaml` (`bwa_zeile` entfällt) · `bwa/berechnung.py` (neu
geschrieben) · `konfiguration.py` (`lade_wirtschaftsjahr_beginn`), `befehle/betrieb.py`,
`befehle/gesellschaft.py`, `export/datev_stammdaten.py` (nutzen ihn) · `abschluss/ausgabe.py`,
`befehle/abschluss.py` (`kontenblatt`, `susa --pdf`) · `cli.py` (`bwa`, `opos liste`,
`opos staffel`) · `config/accounti.example.yaml`.

---

## Spec und Akzeptanz → Paket → Test

| Spec | Punkt | Paket | Test |
|------|-------|-------|------|
| 4.2 | Belegvorschau links | 3 | `test_api_pruefen.py::test_arbeitsflaeche_beleg_links_vorschlag_rechts`, `test_api_belege.py::test_pdf_inline_mit_sicheren_kopfzeilen`, `::test_png_und_jpeg`, `::test_tiff_als_png_seiten`, `::test_xrechnung_als_lesbare_ansicht`, `::test_zugferd_pdf_und_strukturierter_teil`, `test_api_pruefen.py::test_ohne_beleg_zeigt_nachforderung_oder_belegfrei` |
| 4.2 | Vorschlag mit Konto, Steuerschlüssel, Betrag, Confidence | 3 | `test_api_pruefen.py::test_liste_mit_confidence_und_begruendung`, `::test_konto_mit_bezeichnung_und_schluessel_mit_bedeutung` |
| 4.2 | **Begründung, die die Klassifikation mitgeliefert hat** | 1, 3 | `test_kontierungsgrund.py::test_regelwerk_grund_mit_regelname`, `::test_llm_begruendung_quelle_und_modell`, `::test_belegbuchung_sachkonto_quelle`, `::test_kreditkarte_abweichung_als_grund`, `::test_afa_vorschlag_mit_rechenweg`, `::test_marktplatz_auszahlung_und_abrechnung_mit_grund`, `test_pruefschlange.py::test_herkunft_fuer_jede_quelle`, `test_api_pruefen.py::test_ohne_begruendung_hinweis`, `::test_herkunft_afa_ohne_umsatz_und_beleg` |
| 4.2 | Korrigieren, freigeben, zurückstellen in einem Schritt | 1, 2, 3 | `test_pruefschlange.py::test_stand_unter_der_schreibsperre`, `::test_zurueckstellen_legt_rueckfrage_als_aufgabe_an`, `test_api_pruefen.py::test_freigeben_und_weiter`, `::test_korrigieren_vorschlag_direkt`, `::test_sachkontowechsel_verlangt_steuerangabe_422`, `::test_keine_einmalcode_abfrage_in_der_queue`, `::test_zurueckstellen_und_ansicht_zurueckgestellt`, `::test_htmx_409_fragment_mit_meldung_und_neuem_stand`, `test_api_htmx.py::test_ohne_sitzung_hx_redirect_statt_303`; Browserprobe (409/422 sichtbar) |
| 4.2 | Tastaturbedienung | 2, 3 | `test_api_pruefen.py::test_tastenbelegung_im_markup`, `test_api_statisch.py::test_tasten_in_markup_und_skript_gleich`, `::test_eigenes_skript_ohne_eval_und_innerhtml`; Browserprobe (auch `Strg+F`) |
| 4.2 | Korrektur bietet an, eine Regel zu machen (Lernschleife sichtbar) | 1, 3 | `test_lernen.py::test_vorschau_treffer_beispiele_verdraengte_regel`, `::test_gelernte_regel_nur_in_ihrer_richtung`, `::test_schluessel_der_neubuchung`, `test_api_regeln.py::test_vorschau_fragment_und_ohne_js`, `::test_vorschau_zeigt_richtung_und_gegenrichtung`, `::test_regeln_liste_und_deaktivieren`, `test_api_pruefen.py::test_kein_regelangebot_fuer_kreditkarte_anlagen_marktplatz` |
| 4.3 | BWA mit Vorjahresvergleich | 4 | `test_bwa.py::test_handgerechnete_bwa`, `::test_saldiert_je_zeile`, `::test_kumuliert_ab_abweichendem_wirtschaftsjahr`, `::test_vorlaeufiges_ergebnis_gleich_erfolgssalden`, `test_bwa_schema.py::test_leitkonten`, `::test_jedes_erfolgskonto_genau_eine_engste_zeile`, `::test_einklang_mit_der_euer`, `::test_richtung_wie_euer`, `test_api_auswertungen.py::test_bwa_mit_vorjahr` |
| 4.3 | Summen- und Saldenliste | 4 | `test_api_auswertungen.py::test_susa_wie_cli` |
| 4.3 | Kontenblätter mit Absprung zum Beleg | 4 | `test_kontenblatt.py::test_endsaldo_gleich_susa`, `::test_von_mit_uebertrag`, `::test_hinweis_ohne_saldovortrag`, `::test_beleg_id_direkt_und_ueber_abgleich`, `test_api_auswertungen.py::test_drilldown_bwa_kontenblatt_buchung_beleg` |
| 4.3 | OPOS-Auswertungen | 4 | `test_api_auswertungen.py::test_opos_staffel_beschriftung_stand_heute`, `test_cli_auswertung.py::test_opos_liste_und_staffel_csv` |
| 4.3 | Export als CSV und PDF | 4 | `test_auswertung_ausgabe.py::test_csv_formelinjektion_entschaerft`, `::test_pdf_enthaelt_werte`, `test_api_auswertungen.py::test_export_gleich_cli` (vier Berichte × CSV/PDF) |
| 4.5 | Oberfläche auf Deutsch und Englisch | 2 | `test_api_sprache.py::test_jede_seite_in_beiden_sprachen`, `test_i18n_katalog.py::test_jeder_text_hat_eine_uebersetzung` |
| 4.5 | Fachbegriffe ohne tragfähige Entsprechung bleiben deutsch | 2 | `test_i18n_katalog.py::test_fachbegriffe_bleiben_deutsch`, `test_auswertung_ausgabe.py::test_pdf_englisch_kontenbezeichnung_deutsch` |
| 4.5 | Code und Datenmodell bleiben deutsch benannt | alle | Durchsicht in der gegnerischen Prüfung (keine Umbenennung) |
| 4.1 | „Jede Aktion, die im Journal landet, trägt einen echten Benutzer“ | 2, 3 | `test_api_journal_person.py::test_kein_web_eintrag_ohne_angemeldeten_benutzer`, `test_pruefschlange.py::test_person_ist_der_uebergebene_benutzer` |
| 3 | „Oberfläche ruft dieselben Funktionen wie die CLI“ | 1, 4 | `test_cli_lernen.py::test_gelernte_regel_greift_beim_naechsten_classify`, `::test_lerne_schreibt_in_die_datenbank`, `test_cli_supervisor.py::test_review_zeigt_begruendung_und_zurueckgestellt`, `::test_korrigiere_nutzt_die_kontenzuordnung_der_gesellschaft`, `test_pruefung_storno.py::test_steuer_optionen_wie_korrigiere`, `test_api_buchungen.py::test_storno_kette_korrektur_und_journal_sichtbar`, `test_api_auswertungen.py::test_export_gleich_cli`, `test_cli_auswertung.py::test_bwa_statt_platzhalter` |
| **Akz. 1** | Eine unsichere Buchung lässt sich im Browser mit Belegansicht prüfen, korrigieren und freigeben | 3 | `test_akzeptanz_web.py::test_akzeptanz_1_unsichere_buchung_pruefen_korrigieren_freigeben`: buchhalter jan meldet sich an (Passwort + TOTP) → `/pruefen` listet die Buchung (Confidence 62 %, Begründung der Attrappe) → Arbeitsfläche mit `<iframe src="/belege/{id}/datei">` → Datei = Archivbytes, `application/pdf`, `inline` → Korrektur 4930/1200 mit **ausdrücklichem** Schlüssel 9 (Sachkonto ändert sich) → Status `korrigiert`, `geprueft_von` jan, Journal „buchung_korrigiert“ mit Person jan (trotz `ACCOUNTI_BENUTZER=mallory`), Aufgabe `kontierung_pruefen` hinfällig → nächster Eintrag → freigeben (ohne Einmalcode) → `geprueft`, Journal „buchung_freigegeben“ jan → Liste leer. Dazu `::test_akzeptanz_1_mit_bild_und_erechnung` (PNG, TIFF, XRechnung, ZUGFeRD), `::test_akzeptanz_1_freigegebene_buchung_per_storno` (exportierte Buchung über `/buchungen/{id}` mit Einmalcode → Storno + Neubuchung, beide sichtbar, `journal pruefen` in Ordnung), `::test_akzeptanz_1_betrachter_kann_nicht_freigeben`, `::test_akzeptanz_1_htmx_mit_veraltetem_stand` (zweite Person hat inzwischen freigegeben → 409-Fragment, kein Storno), `::test_akzeptanz_1_htmx_steuerangabe_fehlt` (422-Fragment, Feld markiert, danach mit Schlüssel erfolgreich), `::test_akzeptanz_1_skr04_gesellschaft` |
| **Akz. 2** | Aus einer Korrektur entsteht auf Wunsch eine Regel, die beim nächsten Lauf greift | 1, 3 | `test_akzeptanz_web.py::test_akzeptanz_2_korrektur_wird_regel_und_greift_beim_naechsten_lauf`: Umsatz „Bürobedarf Müller GmbH“ −59,50 € (LLM-Attrappe: 4980, 0,62) → Regelvorschau „trifft 1 Ausgabe, greift für diesen Umsatz“ → Korrektur 4930 mit Schlüssel 9 und Regel → Tabelle `kontierungsregeln` in Gesellschaft a (`richtung` = ausgabe, Schlüssel 9), Journal „regel_gelernt“ jan → neuer Umsatz derselben Gegenpartei → `POST /api/v1/laeufe/bank` (Token a, ohne LLM, unter der Laufsperre) → neue Buchung 4930, Confidence 1,0, Grund „Regel 'gelernt_…'“, Journal-Person „API-Token erp“, Attrappe nicht gefragt; ebenso `accounti --gesellschaft a classify --no-llm`. Dazu `::test_akzeptanz_2_vor_falsch_treffender_eigener_regel`, `::test_akzeptanz_2_erstattung_derselben_gegenpartei_nur_als_gegenbuchung` (seit dem Zusammenführen mit main: Gegenbuchung zur Prüfung statt offen), `::test_akzeptanz_2_schalter_pruefen`, `::test_akzeptanz_2_ohne_haken_keine_regel`, `::test_akzeptanz_2_nur_in_der_eigenen_gesellschaft`, `::test_akzeptanz_2_belegbuchung_lernt_sachkonto`, `::test_akzeptanz_2_lauf_laeuft_schon_409` (Laufsperre gehalten → REST 409, Regel bleibt für den nächsten Lauf) |
| 6 | Berechtigungen als Matrix | 3 | `test_api_rechte_matrix.py::test_jede_rolle_gegen_jeden_endpunkt` (mit `EinesVon`, Codes nur für Einmalcode-Endpunkte), `::test_jeder_endpunkt_steht_in_der_matrix`, `test_api_csrf.py::test_jeder_post_ohne_csrf_403_und_nichts_geaendert` |
| 6 | Trennung der Gesellschaften negativ | 3, 4 | `test_api_pruefen.py::test_fremde_gesellschaft_404`, `test_api_belege.py::test_beleg_anderer_gesellschaft_404`, `test_api_auswertungen.py::test_nur_aktive_gesellschaft`, `test_lernen.py::test_regel_nur_in_der_eigenen_datenbank` |
| 6 | Durchlauf Vorschlag → Korrektur → Regel → erneuter Lauf | 3 | `test_akzeptanz_web.py::test_akzeptanz_2_korrektur_wird_regel_und_greift_beim_naechsten_lauf` |
| 6 | Kein personenbezogener Inhalt im Log | Abschluss | `test_betrieb_protokoll.py::test_queue_belege_auswertungen_ohne_belegtexte_im_protokoll` |

---

## Sicherheit

**Rechte.** Jede Route hängt an `erfordert(Recht.X)` (Seitenstruktur); das zusammengesetzte Recht
fürs Zurückstellen und das Lernrecht bei der Korrektur prüft die Route zusätzlich, bevor sie
etwas ändert. Formulare erscheinen nur mit Recht, die Prüfung hängt aber nie am Formular. Die
Rechte-Matrix aus 10a deckt jede neue Route ab und scheitert, wenn eine fehlt. Browser und CLI
verlangen dieselben Rechte (`korrigiere` und Storno: `BUCHEN`, Freigabe: `BUCHUNG_FREIGEBEN`,
Lernen: `REGELN_LERNEN`). Gelernte Regeln buchen künftig ohne Prüfung — deshalb ein eigenes
Recht, Richtung, Journal mit Bestandsabgleich, Vorschau, ein globaler Schalter und ein Weg zum
Deaktivieren.

**Person und Einmalcode.** Im Journal, in `geprueft_von`, in Korrekturen, Regeln und Rückfragen
steht immer der angemeldete Benutzer (`im_namen(a)` und ausdrückliches `von=`), nie eine
Umgebungsvariable oder der Server-Prozess — ein Test geht alle POST-Endpunkte durch. Die Sitzung
selbst entstand mit Passwort und zweitem Faktor; einen frischen Einmalcode verlangen zusätzlich
Zahlungslauf und USt-VA (10a) sowie Storno und Korrektur freigegebener Buchungen
(`/buchungen/{id}`), nicht aber die Entscheidung über Vorschläge in der Queue (Begründung unter
„Person, Einmalcode, Sperren“).

**CSRF.** Alle ändernden Anfragen sind POST und laufen durch `angemeldet()` aus 10a (Token aus dem
Sitzungstoken, Kopf oder Feld, plus Fetch-Metadata gegen `cross-site`); ein Test geht **alle**
POST-Endpunkte der Registry durch. GET-Routen ändern nichts. `SameSite=Strict` verhindert, dass
fremde Seiten Belege oder Exporte mit Anmeldung laden. Ein CSRF-Fehler im HTMX-Weg führt per
`HX-Refresh` zum Neuladen statt zu einer stillen Ablehnung.

**CSP.** Die Richtlinie aus 10a bleibt unverändert. Keine Inline-Skripte, keine `<style>`, keine
`style=`- oder `on…=`-Attribute (Test über alle Seiten und Vorlagen). HTMX lokal (Prüfsumme im
Test), ohne `eval`, ohne Skriptausführung aus Antworten, ohne Indikator-Stil, ohne Verlaufscache
im `sessionStorage`; Fehlerantworten nur 409/422 werden eingetauscht. Eigene Antwort-CSP nur für
Belegdateien (PDF: Seite plus `form-action 'none'` oder strenger laut Spike; Download:
`default-src 'none'; sandbox`).

**Belegzugriff nur in der eigenen Gesellschaft.** Beleg per UUID aus der Datenbank der aktiven
Gesellschaft, Datei aus deren Archiv; kein Hash, Pfad oder Dateiname aus der Anfrage; Hash-Format
und Pfad unter der Archivwurzel geprüft, Inhalt gegen `datei_hash` geprüft. Typ aus dem Inhalt;
inline nur PDF, PNG, JPEG (TIFF umgewandelt mit `formats=["TIFF"]` und Pixelgrenze je Seite);
XML, SVG, HTML, Text, Office nie inline. Dateinamen in `Content-Disposition` fest
(`beleg-<uuid>.<endung>`), nie der Name des Absenders. `Cross-Origin-Resource-Policy:
same-origin`, `nosniff`, `no-store`.

**Fremddaten.** Verwendungszweck, Gegenpartei, Begründung (auch LLM-Ausgabe), Dateiname,
E-Rechnungsfelder, Journal-Stände und Regelmuster sind Fremddaten: Autoescape und
`StrictUndefined` bleiben an, kein `|safe`, Test mit Markup in jedem dieser Felder. E-Rechnungen
nur über `parse_sicher` (DTD/Entities abgelehnt), Größe vor dem Lesen begrenzt
(`server.max_beleg_mb`). CSV-Zellen gegen Formelinjektion entschärft. Regelmuster aus dem Browser
sind Text (`re.escape`, Wortgrenzen), höchstens 100 Zeichen — kein ReDoS; Regexe nur vom Betreiber
über die CLI (`re.compile` geprüft, ≤ 200 Zeichen).

**Integrität.** Buchungen ändert nur `pruefung/storno.py` (Storno statt Änderung bei
freigegebenen und exportierten Buchungen, Sperren aus 7 greifen, Steuerangabe beim
Sachkontowechsel, § 14c, Automatikkonten); Kontenrahmen, Buchhaltung und Prüfeinstellungen kommen
immer aus der Gesellschaft (`lade_korrekturumgebung`). Der `stand` (Schnappschuss der ganzen
Zeile, verglichen unter der Schreibsperre) in jedem Formular verhindert, dass eine veraltete
Ansicht oder ein Doppelklick ein Storno auslöst; die Queue-Routen nehmen nur Vorschläge an,
Zurückstellen nur ohne offene Rückfrage. Gründe sind nur anfügbar (ORM, Trigger, `GESCHUETZT`),
Regeln nur deaktivierbar und im Journal-Bestandsabgleich. Tastenkürzel reagieren nicht auf
Modifikatoren und Tastenwiederholung (`Strg+F` gibt nichts frei).

**Keine Belegtexte im Log.** Pfade enthalten nur UUIDs, Kontonummern und Zeiträume, das
Zugriffsprotokoll schreibt ohnehin die Routenvorlage (10a); Muster, Rückfragen, Einmalcodes und
Vorschauen gehen per POST. Fachfehler werden der Person angezeigt, nicht protokolliert; der
503-Handler protokolliert nur die Fehlerart. Test gegen die gesamte Protokollausgabe eines
Durchlaufs mit Markern in allen Fremddaten.

---

## Grenzen

**Belegvorschau**
- PDFs zeigt der eingebaute Betrachter des Browsers. PDFs aus fremden Postfächern können aktive
  Inhalte (JavaScript, Formularaktionen, Links) tragen; Chromium und Firefox führen sie im
  Betrachter abgeschottet aus, die Seite erreichen sie nicht, das Sitzungscookie ist `HttpOnly`.
  Eine CSP-Sandbox für das PDF ist nicht möglich, weil Chromium es dann nicht anzeigt; eine
  serverseitige Umwandlung in Bilder bräuchte einen PDF-Renderer (neue Abhängigkeit).
- Keine Vorschau für HEIC, WebP, Office, E-Mail; TIFF höchstens 20 Seiten (weitere Seiten
  liest accounti nicht einmal ein; ein Hinweis auf sie fehlt). Eingebettete Anlagen
  einer XRechnung (BT-125) werden nicht gelesen und nicht angezeigt. Die E-Rechnungsansicht ist
  eine eigene Darstellung, nicht die KoSIT-Visualisierung, und kein Prüfbericht.
- Die Nachforderung wird nur angezeigt; die Anfrage an den Lieferanten verschickt weiter nur
  `accounti nachfordern anfrage … --senden` (7).

**Queue und Korrektur**
- Die Queue zeigt nur Buchungen `zur Prüfung`. Eine Stichprobe automatisch gebuchter Buchungen
  ist nicht vorgesehen, ebenso keine Mehrfachauswahl und keine Sammelfreigabe.
- Freigabe, Korrektur und Zurückstellen von Vorschlägen verlangen keinen frischen Einmalcode; ein
  versehentliches `f` gibt frei (Modifikatoren und Tastenwiederholung ausgefiltert, Kürzel
  abschaltbar). Rückgängig nur per Storno — dann mit Einmalcode und sichtbar im Journal. In der
  CLI verlangt dieselbe Freigabe den Code (keine Sitzung).
- Kein Vier-Augen-Prinzip für Buchungen (wie in 7); Funktionstrennung über die Rollen.
- Freigeben prüft nur die Prüfregel `steuerschluessel_konto` (Schwere Fehler sperrt, Warnungen
  stehen als Hinweis da) — die übrigen Prüfregeln laufen weiter über `accounti pruefen`.
- Storno und Korrektur auf `/buchungen/{id}` laufen erst zur Probe (zurückgerollt), dann unter
  einer Sperre je Gesellschaft im Server-Prozess: Stand erneut prüfen, Einmalcode, Lauf. Ein
  Doppelklick oder eine zweite Person im Browser bekommt 409 ohne Fehlversuch und ohne
  verbrauchten Code; ändert ein anderer Prozess (CLI, ein zweiter Server) die Buchung genau
  zwischen dieser Prüfung und dem Lauf, ist der Code trotzdem verbraucht (Meldung 409).
- „an“ beim Zurückstellen ist ein freier Name (≤ 100 Zeichen) wie in `aufgaben rueckfrage`
  (auch Rollen und Empfänger aus `aufgaben.zustaendigkeit`); eine Auswahl der Benutzer folgt
  mit 10c.
- Gleichzeitige Bearbeitung wird erkannt (409), nicht zusammengeführt. Schreibt ein Lauf länger
  als 30 s, bekommt eine Aktion 503 und muss wiederholt werden.
- Kontenbezeichnungen gibt es nur für die Konten der mitgelieferten Listen (rund 45 SKR03, 26
  SKR04, dazu 42 aus `pruefung/skr03.yaml`); andere Konten erscheinen nur mit Nummer.
- Meldungen der Fachmodule erscheinen deutsch (auch in der englischen Oberfläche).
- Festschreiben und Öffnen von Monaten gibt es nur in der CLI (`accounti periode …`).
- Tastaturbedienung ist nur in der Browserprobe geprüft, nicht automatisch; keine Prüfung mit
  Bildschirmlesern über die Grundregeln (Beschriftungen, `lang`, `role="img"`, Fokus) hinaus.

**Lernen**
- Gelernte Regeln buchen künftige Umsätze in der Standardeinstellung mit Confidence 1,0
  automatisch — so arbeitet das Regelwerk heute schon; mit `buchhaltung.gelernte_regeln:
  pruefen` legen sie nur vor. Kein Vier-Augen-Prinzip für Regeln, nur Recht, Richtung,
  Vorschau, Journal, Schalter und Deaktivieren. Regeln wirken nur auf noch nicht gebuchte
  Umsätze, nicht rückwirkend (ein reines Storno öffnet einen Umsatz aber wieder).
- Die Richtung schützt vor vertauschten Seiten bei Erstattungen, nicht vor einer falschen
  Kontierung in derselben Richtung. `accounti lerne` ohne `--richtung` gilt wie eine Regel der
  Regeldatei in beide Richtungen; `regeln uebernehmen` leitet die Richtung aus der Bankseite ab
  und lässt Einträge ohne Geldkonto ohne Richtung (gemeldet).
- Mustervorschlag: der Name der Gegenpartei bis vor die erste Rechtsform (feste Liste deutscher
  und gängiger ausländischer Rechtsformen). „Andere Gegenpartei“ vergleicht diesen Namen ohne
  Groß-/Kleinschreibung — Schreibvarianten derselben Firma („Telekom Deutschland GmbH“ neben
  „Deutsche Telekom AG“) zählen als andere und verlangen die Bestätigung. Zahlungsdienste
  erkennt accounti nur an einer festen Namensliste (PayPal, Klarna, Stripe …); einen
  Händler aus dem Verwendungszweck schlägt es nicht vor (10c). Rechtsformen, die auch Wörter
  sind („Co“, „AB“, „AS“, „SE“, „SA“, „SL“), kürzen nur, wenn davor zwei Wörter bleiben
  („Spotify AB“ bleibt ganz). Ohne Namen der Gegenpartei (CSV ohne Namensspalte, MT940 ohne
  `?32`) bleibt der Vorschlag das erste Wort des Verwendungszwecks; jeder weitere Treffer zählt
  dann als fremd, und die Regel verlangt **immer** die Bestätigung — auch ohne Treffer im
  Bestand, weil sich nicht prüfen lässt, ob künftige Treffer von derselben Gegenpartei stammen.
  Mit Namen kommt die Bestätigung nur, wenn passende fremde Umsätze schon im Bestand sind.
- Die Bestätigung gilt für das Muster, für das der Haken gesetzt wurde; die Vorschau lädt
  nicht automatisch beim Setzen des Regel-Hakens (10c) — ohne Vorschau gespeichert wird aber
  nur ein Muster ohne solche Warnung.
- Die CLI lernt weiterhin aus Altbuchungen ohne gespeicherte Herkunft (vor 10b) — darunter
  können auch Kreditkarten- oder Marktplatzbuchungen sein; der Browser bietet dort keine
  Regel an.
- Die Finanzkonto-Prüfung der Korrektur greift nur, wenn die Buchung das Finanzkonto des
  Umsatzes (`tx.sachkonto`, sonst `buchhaltung.bank_konto` der Konfiguration) oder — nach einem
  Wechsel — ein anderes eingerichtetes Bankkonto auf der Seite der Zahlung heute berührt —
  Skonto- und Restbuchungen am selben Umsatz und eine CLI-Korrektur mit falscher `--config`
  bleiben ungeprüft.
- Ein falsch zugeordnetes Finanzkonto (Umsatz über `import bank` ohne `--konto`, falsches
  `--konto`) stellt die Korrektur richtig: Der Wechsel auf ein **anderes eingerichtetes
  Bankkonto** (`buchhaltung.bank_konto` oder `accounti bank verbinde … --sachkonto`, auch
  Kartenkonten) geht mit Warnung; ob der Umsatz wirklich auf dem Auszug dieses Kontos steht,
  prüft accounti nicht — erst die Bankabstimmung im Abschluss. Die Kontozuordnung des Umsatzes
  (`tx.sachkonto`) bleibt: nach einem Storno bucht `classify` ihn wieder über das alte Konto.
  Aus einem Wechsel wird keine Regel gelernt. Kasse, Aufwand und nicht eingerichtete Konten
  bleiben abgewiesen (die Meldung nennt `accounti bank verbinde`, wenn das Konto im
  Bankbereich des Kontenrahmens liegt).
- Die CLI lernt nicht aus Kassenvorgängen (Kassenbuch, `quelle=manuell`); sie speichern keine
  Herkunft und zählen nicht als Altbuchung.
- Im Browser nur Text-Muster; Regexe nur über `accounti lerne` und von Hand in der Regeldatei.
  accounti schreibt die Regeldatei nicht mehr; `accounti regeln uebernehmen` holt alte
  `gelernt_*`-Einträge in die Datenbank, löscht sie aber nicht aus der Datei.
- Regeln lassen sich nicht bearbeiten, nur deaktivieren und neu lernen.
- Lernen bei Belegbuchungen ändert das Sachkonto am Kontakt; Kontakte stehen nicht im
  Journal-Bestand (nur der Vorgang über `schreibe`).
- Auf `/buchungen/{id}` (Storno-Korrektur) gibt es kein Regelangebot; dort hilft
  `accounti korrigiere … --lernen`.
- Die Vorschau zählt über die Umsätze der letzten 24 Monate (ein Durchlauf in Python).
- Umbuchungen zwischen eigenen Geldkonten erkennt accounti an den Konten (Abschnitt
  `zahlungsmittel` des Kontenrahmens, Bankkonto, Finanzkonto des Umsatzes, eingerichtete Bank-
  und Kartenkonten); ein Geldkonto außerhalb davon (z. B. ein eigenes Geldtransit-Konto aus
  `integrationen`) zählt nicht. Eine Regel, die eine Umbuchung nur auf einem der beiden Konten
  richtig bucht (Regeldatei, `lerne` vor dieser Korrektur), bucht dort weiter; auf dem anderen
  Konto bleibt der Umsatz offen (die Umbuchung steht auf beiden Auszügen und wird so nur einmal
  gebucht) — wie er dort zu buchen ist, entscheidet der Mensch. Die Regelvorschau im Browser
  kennt eingerichtete Konten außerhalb der Bereiche nicht (gespeichert wird trotzdem nicht).
- `regeln uebernehmen` lässt Einträge mit `pruefen`/`confidence` und Umbuchungen in der
  Regeldatei; dort greifen sie nach den gelernten Regeln. Ein eigenes Prüfkennzeichen je
  gelernter Regel gibt es nicht (nur den Schalter `buchhaltung.gelernte_regeln` für alle).
  Ein unbekannter Name bei `--name` wird gemeldet, die übrigen Einträge werden trotzdem
  übernommen.
- Die Einmalcode-Probe der CLI läuft vor dem Code; ändert jemand die Buchung genau zwischen
  Probe und Lauf, ist der Code verbraucht (wie im Browser). Eine Fachprobe haben `buchung
  storniere`, `korrigiere`, `lerne`, `bestaetige`, `regeln deaktivieren`/`uebernehmen`, `kasse`,
  `periode` und (Runde 4) `ustva freigeben`, `zahlung freigeben`, `belege freigeben`; die
  übrigen Befehle mit Einmalcode (`anlagen`, `abschluss`, `opos`
  zuordnen/verrechnen/bestätigen/ablehnen, Belegabgleich `bank bestaetigen`/`ablehnen`,
  `export datev`, `nachfordern`, `journal uebernehmen`, `ustva dauerfrist`, `zahlung
  anlegen`/`entfernen`/`sepa`/`stornieren`/`abgleichen`/`sperre`/`iban-klaeren`) prüfen nach
  dem Code — ein Fachfehler kostet dort den Code. Die Probe bräuchte je Befehl eine Prüfung der
  Seiteneffekte (Dateien, E-Mail, Export); Folgearbeit. Die Probe von `regeln uebernehmen`
  speichert und rollt zurück (Fehler beim Speichern fallen dort auf); ein Datenbankfehler
  außerhalb der geprüften Spalten (Name, Muster, Buchungstext) bliebe ein Fehler nach der
  Probe, vor dem Code.
- Im Browser prüfen Zahlungslauf und USt-VA wie Storno erst zur Probe, dann unter der
  Freigabesperre den Code — die Sperre gilt nur im Server-Prozess; wer zugleich in der CLI
  freigibt, kann einen Code verbrauchen, ohne dass der Browser freigibt (wie bei Storno).
- SKR04: Erlöse eines OSS-Fernverkaufs gehen auf die Länderkonten 4320–4327 (zur Prüfung; eine
  Konvention von accounti wie 8320–8327 im SKR03 — DATEV führt dort ein Konto 4320 mit
  Bestimmungsland und Steuersatz in der Buchung, ein solches Feld hat der Buchungssatz nicht);
  ein Land ohne Länderkonto (nur FR, IT, ES, NL, SE, PL, AT, BE haben eines) bucht auf „Erlöse“
  zur Prüfung, und die OSS-Meldung erfasst es nicht (Hinweis bei der Verbuchung, selbst
  melden). Der ermäßigte Satz des Bestimmungslands hat in OPOS kein eigenes Konto (die Meldung
  rechnet mit dem Normalsatz; nur die Marktplatz-Abrechnung kennt `oss_erloes_ermaessigt`). Die
  DATEV-Automatik von 4400/4300 kennt accounti im SKR04 nur mit einer eigenen
  `pruefung.kontenrahmen_datei` (sonst trägt der Export den BU-Schlüssel mit).
  Marktplatz-Abrechnungen (`integrationen`) folgen weiter ihren konfigurierten Konten (im SKR04
  8320–8327; Meldung und Kz 45 zählen sie mit). Die OSS-Steuer selbst bucht OPOS (seit Paket C)
  in beiden Kontenrahmen auf die eigenen Konten 1777xx (Rückfall 1779) — im SKR04 liegen sie
  außerhalb der Steuerkonten (3800 ff.), die Anlage EÜR führt sie dort als Bestand; ein
  SKR04-eigenes OSS-Steuerkonto fehlt (Folgearbeit, mit DATEV abzustimmen). Im SKR04 liegen
  1777xx/1779 zudem im Bank- und Zahlungsmittelbereich (1700–1889): `abschluss pruefen` meldet
  sie als nicht eingerichtetes Bankkonto (Abschluss gesperrt, Rat „bank verbinde“ irreführend),
  und die Zahlung der OSS-Steuer an das BZSt lässt sich nicht als Regel lernen („beide
  Geldkonten“). Das behebt Paket E beim nächsten Zusammenführen, das die OSS-Steuerkonten
  ohnehin ändert (g3w-fach/g3w-merge N1, Runde 4 nicht behoben).
- Im Browser bietet die Korrektur einer Belegbuchung den bisherigen Schlüssel und den, den der
  Beleg vorgibt (`steuer_optionen(b, beleg).laut_beleg`: sein einziger Satz mit seiner
  Richtung — 19 % Eingang 9, 7 % 8, Ausgang 3 bzw. 2; ohne Satz in den Positionen das
  Verhältnis Steuer/Netto, dann nur mit Grund wie in Gesamttest B05; Runde 7, g6w N5); § 13b bzw. ig. Erwerb auf einer Belegbuchung
  (Paket C) setzt die CLI (`korrigiere … --steuer 94 --grund …`) — nie auf einer Belegbuchung
  mit ausgewiesener Umsatzsteuer (2/3 auf einem Ausgangsbeleg, § 14c Abs. 1 UStG: Berichtigung
  als neuer Beleg; Runde 4). Ein Umsatzsteuerschlüssel auf einem Eingangsbeleg (`richtung`
  Eingang, nicht Ausgangsrechnung) ist ein Fehlschlüssel, keine ausgewiesene Steuer: „ohne
  Steuer“ mit Grund und der Schlüssel laut Beleg gehen, § 14c-Warnung und
  `beleg_ust_ohne_buchung` zählen ihn nicht. Ohne eindeutige Belegart (Quittung,
  Marktplatzabrechnung als `SONSTIGES`, unbekannt) zählt die Buchung: Bucht sie ein
  Erlöskonto auf der Seite einer Rechnung (Erlös im Haben, Erlösschmälerung im Soll; ein
  negativer Beleg spiegelt), gilt der Beleg wie ein Ausgangsbeleg — § 14c, kein Hinweis
  „Fehlschlüssel“, kein Schlüssel 9, kein „ohne Steuer“, Storno-Warnung und
  `beleg_ust_ohne_buchung` zählen ihn (Runde 8, g7w R7-3). Ebenso jede Buchung mit
  Erlöskonto, die einen Umsatz mit dem Vorzeichen einer Rechnung bucht (positive
  Umsatz-Kennziffer, bei negativem Beleg negativ): auch eine Erlösschmälerung im Haben
  („1000 an 8700, Schlüssel 3“ bucht Kz 81 +500; F Runde 2, gf-richtung GF-1a). Ein Erlös
  im Soll eines positiven Belegs („8400 an 1000, Schlüssel 3“ auf einer Tankquittung) ist
  eine Erstattung bzw. eine falsch kontierte Ausgabe und lässt sich direkt auf „4530 an 1000
  --steuer 9“ berichtigen (Folgepaket F, g8w G8R-1). Weist ein solcher Beleg Umsatzsteuer nur
  über seine Erlösbuchungen aus, zählt als ausgewiesen je Satz höchstens die Steuer dieser
  Buchungen (eine Gebührenposition desselben Satzes nicht; g8w G8R-4) — je Korrekturkette
  ihr höchster positiver Erlös-Stand, auch ein durch eine Neubuchung ersetztes Original
  („1000 an 8400 → 1000 an 2700, Schlüssel 3“, dann Storno: die Lücke bleibt 95 €; GF-1b).
  Eine Erlösschmälerung („8700 an 1000, Schlüssel 3“) senkt die Obergrenze nicht, ob wirksam,
  storniert oder berichtigt (Untergrenze 0 je Kette; sonst hob sie den Erlös auf: Storno ohne
  Warnung bzw. 76 statt 95 €, F Runde 3, gf2-richtung GF2-1, GF2-2); eine Minderung, die der
  Beleg selbst ausweist (Position Rücksendung), mindert schon die ausgewiesene Steuer. Steht
  sie neben einer Gebühr desselben Satzes und sind Erstattung und Verkauf storniert, heben
  sich Erstattung und Gebühr in der ausgewiesenen Steuer auf: Die Lücke meldet dann zu viel
  (19 € statt nichts, Teil-Erstattung 95 statt 76 €; gf3-obergrenze GF3-2) — eine Warnung zu
  viel, nie eine fehlende; eine engere Obergrenze zog die Erstattung bei netto gebuchtem Erlös
  doppelt ab und ließ Umsatzsteuer still fehlen (Paket G, gg GG-1). Nennt der
  Beleg keinen Satz und keine eindeutige Belegsteuer (Beleg ohne Steuerzeile: Position
  „Gesamtbetrag“ ohne Satz), weist er je Satz die höchste Steuer seiner Rechnungsbuchungen
  aus, auch einer stornierten — auch auf einer Ausgangsrechnung; eine Minderung ist keine
  Rechnungsbuchung (als jüngste Buchung machte sie die ausgewiesene Steuer ≤ 0: Storno des
  Erlöses ohne Warnung, Paket G, GF3-1). Auswahl der Oberfläche,
  Korrektur, Storno-Warnung und Prüfregel lesen dieselben Konten (mit
  `elster.steuerrelevante_konten` und `kennziffern_konten`; g8w G8R-2). Grenzen: Nennt der
  Beleg mehrere Sätze und die Buchung keine Position, gibt es keinen Schlüssel laut Beleg
  (Weg: „ohne Steuer“ mit Grund bzw. Storno). Eine Erlösschmälerung im Soll eines positiven
  Belegs ohne eindeutige Belegart gilt als eigene Minderung des Unternehmers (§ 14c, wie
  R7-3 X2), auch wenn sie in Wahrheit eine Gebühr ist (Weg: Storno bzw. Umbuchung über ein
  Aufwandskonto). Die Obergrenze der Lücke ist die höchste gebuchte Erlössteuer der Kette —
  war der Erlös mit zu wenig Steuer gebucht, meldet die Lücke nur diese. Bleibt neben dem
  stornierten Erlös eine Erlösschmälerung wirksam, die der Beleg nicht ausweist („8700 an
  1000, Schlüssel 3“, Kz 81 −500), melden Storno und Prüfregel die ganzen 95 € (wie d36ac77).
  Bleibt dagegen eine Erstattung gebucht, die der Beleg selbst ausweist, und wird nur der
  Verkauf storniert, zählt die Summe der Positionen: Bei voller Erstattung meldet die Lücke
  neben einer Gebühr desselben Satzes nur deren Vorsteuer (19 statt 95 €), ohne Gebühr
  nichts, obwohl die Voranmeldung um die Erstattung mindert (beides wie bisher). Ohne
  Steuerzeile kennt die Lücke den Betrag des Belegs nicht: Ist die Rechnung auf mehrere
  Buchungen desselben Satzes verteilt, zählt nur die höchste (das Storno eines kleineren
  Teils meldet nichts, wie bisher), und nach Storno und Neubuchung mit niedrigerem Betrag
  meldet sie den Unterschied zur stornierten Buchung. Wird ein Vorschlag
  direkt (ohne Storno) auf ein Konto ohne Erlös umgebucht („1000 an 2700, Schlüssel 3“ ohne
  `elster.steuerrelevante_konten`) und dann storniert, kennt die Lücke den früheren Stand
  nicht (er steht nur im Journal; wie d36ac77); „→ 2700, dann ohne Steuer mit Grund“ bleibt
  erlaubt (Grenze 5 aus F), meldet aber die Prüfregel.
- Bei einer Belegbuchung bestimmt der Beleg die Richtung (Runde 5, g4w N1; Runde 6, g5w
  NEU-1/NEU-2): `korrigiere` lehnt eine Korrektur ab, die die Seiten vertauscht — für jede
  Belegbuchung, nicht nur bei ausgewiesener USt: (a) ein Konto wechselt die Seite (neues Soll
  = altes Haben oder umgekehrt, auch bei zwei Gegenkonten wie einer Zahlung „1200 an 10001“);
  (b) die Sachseite ist vorher und nachher aus den Konten bestimmt
  (`kennziffern.sachseite_aus_konten`: gegenüber dem einzigen Gegen-, sonst das einzige
  Erlöskonto — wie die Voranmeldung, ohne deren Rückfall auf die Seite des Schlüssels) und
  eine andere; (e) ein Erfolgskonto (Kontoart der Abschlusszuordnung) steht vorher und
  nachher allein auf einer Seite, nachher auf der anderen; (d) eine Kennziffer der
  Voranmeldung kehrt ihr Vorzeichen um (mit `elster.kennziffern_konten` und
  `steuerrelevante_konten`). Bestimmen die Konten die Seite nicht (zwei Gegenkonten wie „1800
  an 1200“, zwei Sachkonten ohne Erlös wie „4120 an 1740“), sperrt das nicht (c) — Runde 5
  las dort „Haben“ und sperrte Privatanteil, Spende, Wertpapier, Geldtransit, Lohn- und
  sonstige Verbindlichkeit. Die Regeln gelten gegen jeden früheren Stand der Korrekturkette,
  nicht nur gegen die vorige Buchung (Runde 7, g6w N1: „10001 an 8125 → 10001 an 1590 → 8125
  an 1200“ buchte Kz 41 −500): Original und Neubuchungen über `buchungskorrekturen`, direkt
  korrigierte Vorschläge über das Journal (`storno.fruehere_staende`). Bricht ein späterer
  Stand mit der Richtung eines früheren (Altbestand: main bzw. Runde ≤ 4 korrigierten ohne
  Sperre), zählt der frühere nicht mehr — es gilt der berichtigte Stand (Runde 8, g7w R7-1:
  nach „8400 an 10001 → 10001 an 8400“ auf main war jede Korrektur gesperrt). Bestimmt kein
  Stand eine Seite, gilt für das Erfolgskonto die Seite der Rechnung (Eingangsrechnung:
  Aufwand im Soll, Ausgangsrechnung: Erlös im Haben; negativer Beleg dreht) — außer bei einem
  Altfall „4900 an 4900“ und bei einer Zahlung, Erstattung, Verrechnung oder einem Skonto zur
  gebuchten Rechnung (jeder Stand nur Geld-, Personen- und Verrechnungskonten bzw. ein
  Minderungskonto dagegen, und eine andere wirksame Buchung des Belegs bucht die Rechnung;
  Runde 8, g7w R7-2) — sie bucht ein Geld- oder Personenkonto auf der Gegenseite der
  Rechnungsbuchung („1200 an 10001“ zu „10001 an 8400“) bzw. deren Gegenkonto selbst, auch
  ein Verrechnungs- oder Transitkonto („1200 an 1590“ zu „1590 an 8400“, SKR04 1370; F Runde
  2, gf-richtung GF-2). Ein Teil der Rechnung auf zwei
  Gegenkonten („10001 an 1590“ neben „10001 an 8400“, Barverkauf „1000 an 1590“) bucht es
  auf derselben Seite und ist keine Nebenbuchung — auch nicht, wenn eine zweite
  Rechnungsbuchung über dieses Gegenkonto läuft („1590 an 8400“ daneben: das Gegenkonto der
  Rechnung zählt nur für eine Buchung, die kein Gegenkonto einer Rechnungsbuchung auf deren
  Seite bucht; F Runde 3, gf2-richtung GF2-3); gibt eine Korrektur einer Nebenbuchung ein
  Erlös- bzw. Aufwandskonto mit Schlüssel, das kein Minderungskonto ist (Auszahlung einer
  Gutschrift „10001 an 1200 → 10001 an 8400, Schlüssel 3“), gelten Rückfall und (d) wieder
  (Folgepaket F, g8w G8R-3). (d) sperrt auch eine Kennziffer, die erst durch die Korrektur entsteht
  und negativ ist (Vorzeichen einer Gutschrift), wenn kein Stand der Kette eine Kennziffer
  negativ bucht und der Beleg keine Gutschrift ist („10001 an 8125 → 8120 an 8125“: Kz 43
  −500; g6w N2) — nicht bei Skonto, Rabatt, Bonus oder Nachlass zur gebuchten Rechnung
  (Erlösschmälerungen, erhaltene Nachlässe 37xx bzw. 57xx, Skontokonten der Buchhaltung:
  „1590 an 10001 → 8736 an 10001, Schlüssel 3“).
  Grenzen: Werden beide Konten ersetzt, ohne dass eine dieser Regeln greift (z. B. „0420 an
  1700 → 1701 an 0421“: Bestandskonten ohne Gegenkonto, ohne Erfolgskonto, ohne Kennziffer),
  erkennt die Sperre den Tausch nicht. Ohne Journal (Datenbank von vor Baustein 7) kennt sie
  den ersten Stand eines direkt korrigierten Vorschlags nicht. Eine Belegbuchung, die nach
  Storno ohne Neubuchung neu entsteht (`classify`, OPOS), beginnt eine neue Kette. Ein
  Belegtyp außer Eingangs- und Ausgangsrechnung (Quittung, unbekannt) gibt keine Seite vor.
  Bei einem Altbestand mit Richtungswechsel gilt der jüngere Stand, auch wenn er der falsche
  ist (dann das Storno). Eine Zahlung zum Beleg erkennt die Sperre an den Konten; ist die
  Rechnung nicht als eigene Buchung gebucht (geparkt auf zwei Gegenkonten), misst sie an der
  Seite der Rechnung. Die Anzahlungsverrechnung auf einer Schlussrechnung („1590 an 10001 →
  1718 an 10001, Schlüssel 3“, Kz 81 −) sperrt (d) weiter (wie Runde 6 über den Schlüssel:
  Storno bzw. Buchung über OPOS). Das Vorzeichen der
  Kennziffern allein genügt nicht: „4930 an 70001, Schlüssel 9 → 1700 an 4930“ lässt die
  Voranmeldung gleich und bucht den Aufwand ins Haben. Ist die Belegbuchung selbst falsch
  herum gebucht, bleibt das Storno mit Grund (ein Vorschlag wird dafür erst freigegeben);
  eine Neubuchung mit demselben Beleg von Hand gibt es nicht (Folgearbeit), und ein Storno
  einer Buchung aus einem bestätigten Belegabgleich führt `classify` wieder zur selben
  Buchung — die Korrektur ist der Weg.
- Ein Storno ohne Neubuchung bleibt erlaubt (Runde 5, g4w N2). Fehlt danach ausgewiesene USt
  eines Belegs in der Voranmeldung, warnt es, und `beleg_ust_ohne_buchung` meldet den Beleg im
  Zeitraum des Stornos, bis wieder gebucht ist — eine Begründung, die den Befund schließt,
  gibt es nicht (wie bei den anderen Prüfregeln: Befund mit Begründung stehen lassen).
  Gezählt wird je Satz die wirksam gebuchte Steuer (Schlüssel 2/3, Rechnungsseite) gegen die
  der Belegpositionen (Runde 6, g5w NEU-3/NEU-4); der Zeitraum ist der des letzten Stornos
  einer solchen Buchung, ein späteres Zahlungsstorno verschiebt ihn nicht (Runde 7, g6w N3): Eine Zahlung mit derselben `beleg_id`, eine
  Buchung zu einem anderen Satz und eine Minderung (Skonto) decken sie nicht; eine
  wegfallende Gutschrift fehlt nicht; eine wirksam gebuchte Kopie derselben Rechnung
  (`belege.dubletten.kopien`: Richtung, Lieferant, Nummer, Betrag gleich) deckt sie. Grenzen:
  Steuer, die ohne Schlüssel direkt auf ein USt-Konto gebucht ist, zählt nicht (der Befund
  bleibt mit Begründung); Sätze außer 19/7 % (OSS) prüft die Regel nicht; je Position
  höchstens ein Cent Rundungsabstand. Vorsteuer warnt nicht.
- Steuerschlüssel 1 (umsatzsteuerfrei) nimmt nur die Regeldatei (und `regeln uebernehmen`)
  wieder an (Runde 5, g4w N6); `korrigiere --steuer`, `lerne --steuer` und der Browser bieten
  ihn wie in Runde 4 entschieden nicht an.
- Personenkonten erkennt der Kontenrahmen an der Länge: 5 Stellen (Sachkontenlänge 4) oder 9
  (Sachkontenlänge 8, Runde 5, g4w N5); bei Sachkontenlänge 5–7 (Personenkonten 6–8 Stellen)
  nicht — accounti rechnet mit 4-stelligen Sachkonten, 6-stellige sind Unterkonten. Die
  Voranmeldung und die Prüfregeln nehmen Personenkonten aus den Bereichen der Buchhaltung
  (`debitoren_von` …), die höchstens 9 Stellen haben (Runde 6, g5w-konten N3: eine Untergrenze
  mit mehr Stellen lehnt die Konfiguration ab, eine Obergrenze darüber gilt mit Hinweis als
  999999999 — Runde 7, g6w B-5). `export datev`, `datev belege` und `datev stammdaten` nehmen
  die Sachkontenlänge aus `mandant.sachkonten_laenge` (eine ganze Zahl 4–8, auch als `4.0`,
  sonst Fehler; Runde 6, g5w-konten N2); `export datev` warnt bei Konten, die nicht dazu passen, und bei
  Personenkonten (Bereiche der Buchhaltung) ohne Sachkontenlänge + 1 Stellen — die Konten
  prüft es nur der Länge nach (Warnung), wie `datev belege`.
- Die Werte der Regeldatei prüft der Lader nur der Form nach (Kontonummer 4–9 ASCII-Ziffern,
  Muster nicht leer, bekannter Steuerschlüssel samt 1, keine unbekannten Schlüssel,
  `confidence` von 0 bis 1); ob es das Konto im Kontenrahmen gibt, prüft er nicht. Ein
  Fehler in einem Eintrag hält die ganze Regeldatei an (Meldung mit Regelname), wie bisher bei
  Regex und `feld` — auch ein Zusatzfeld (z. B. `kommentar:`) ist jetzt ein Fehler; Kommentare
  gehören hinter `#`. Ebenso prüft das Kassenbuch das Gegenkonto der Form und der Prüfregel
  `steuerschluessel_konto` nach, nicht auf sein Vorkommen im Kontenrahmen.
- Übernommene Regeln stehen untereinander in der Reihenfolge ihrer Stelle in der Datei beim
  Übernehmen (`rang`); ändert der Betreiber die Datei zwischen zwei Läufen, gilt die Stelle zur
  Zeit des jeweiligen Laufs (bei gleicher Stelle der früher übernommene zuerst). Vor Runde 3
  übernommene Regeln (ohne `rang`) behalten ihre alte Ordnung, vor den neuen. Wer die
  übernommenen Einträge löscht und erst danach `--name` verwendet, stellt dessen Eintrag nach
  seiner neuen Stelle ein — womöglich vor früher übernommene (gegen:regeln:1, Rest); Hilfe,
  Ausgabe und betrieb.md sagen deshalb „erst nach allen Läufen löschen“.
- Als Sachkonto eines Belegs übergeht accounti Zahlungsmittel, Personenkonten und die
  LuL-Sammelkonten (`lul_konten`); andere Bestands- und Verrechnungskonten nimmt es, wenn Kontakt
  oder Regel sie liefern — ob das fachlich passt, entscheidet der Mensch in der Prüfung.
- `db upgrade` erkennt einen unpassenden Vermerk an fehlenden Tabellen und Spalten, nicht an
  fehlenden Indizes oder Triggern; `--aus-schema` stempelt nur zurück, nie vor.
- Kaputtes YAML der Konfiguration ist in jedem strengen Lader ein `KonfigurationError`
  („… kein gültiges YAML (…)“, `konfiguration.lies_yaml`; Runde 7, g6w B-3 — auch
  `lade_pruefung` und `lade_elster`, bisher Grenze), ebenso eine Datei in anderer Kodierung
  als UTF-8 — auch die Registry (`betrieb.gesellschaften.lies_yaml`, dort auch eine unlesbare
  Datei) und `lade_auth` (Runde 8, g7w B7-5). Die Prüfen-Arbeitsfläche und `/buchungen/{id}`
  zeigen den Fehler samt Datei und keine Entscheidung, statt mit Standardwerten zu rechnen
  (`seiten.pruefen.seitenkonfiguration`; Runde 8, g7w B7-4); die Regelvorschau rechnet bei
  fehlerhafter Regeldatei weiter ohne sie („verdrängt Regel …“ bleibt offen). Roh lesen weiter nur die nachsichtig
  gelesenen Angaben (`lade_eigene_firma`, `lade_oss`, `lade_mandant`, die Anzeige des
  Wirtschaftsjahrs in `gesellschaft liste`); jeder Befehl, der sie nutzt, lädt vorher einen
  strengen Abschnitt.
- Die Schwärzung des Protokolls ist musterbasiert (Namen, kleingeschriebene IBANs erkennt sie
  nicht). Ihre Muster laufen linear und beginnen an „://“, gleich, was davor steht
  (Folgepaket F, g8w B8-3); zwischen Schlüsselwort und Wert erkennen sie innerhalb einer
  Zeile beliebig viel Leerraum, possessiv (`\s*+`) und damit linear (g8w B8-1; die Grenze von
  40 Zeichen aus F ließ dahinter den Wert stehen, F Runde 2: gf-betrieb F-B2). Eine Zeile
  über 4000 Zeichen kürzt sie vorher auf Anfang und Ende (je höchstens 1500 Zeichen, an
  Leerraum), jede Zeile für sich — Grenze: Reicht der Abstand über einen Zeilenumbruch und ist
  eine der beiden Zeilen gekürzt („PIN“, 4100 Leerzeichen, „\n471147“), trennt die Kürzung
  Schlüsselwort und Wert, der Wert bleibt stehen (wie d36ac77; F Runde 3, gf2-betrieb
  GF2B-1: betrieb.md versprach mehr). Sie schwärzt jedes Stück zuvor mit 250 Zeichen über
  die Kante hinaus, das Ende auch über einen Abstand hinweg, in dem diese beginnen — ein
  Geheimnis an der Kante steht vorn geschwärzt da und fällt hinten ganz weg (g8w B8-1: die
  Fassung aus Runde 8 schnitt zuerst und trennte hinten „Bearer“, „passwort:“, „PIN“ von
  ihrem Wert). Ein statischer Pfad steht gekürzt auf 200 Zeichen im Zugriffsprotokoll, andere
  Pfade als Routenvorlage bzw. „(unbekannt)“ (Runde 8, g7w DoS-1; echter `serve`-Lauf mit
  40 000 Zeichen in Pfad, Abfrage und User-Agent: `GET /anmelden` wartet höchstens 0,03 s).
  Die Sprachwahl nach einem POST (`vorlagen.ansichtspfad`) steigt nur von einem Pfad mit
  Route und höchstens 16 Abschnitte hinauf, sonst „/“ — für die 404-Seite eines Pfads mit
  vielen „/“ rechnete sie quadratisch (`POST /x…` mit 40 000 Zeichen: jede andere Anfrage
  wartete 3,7 s; schon in #36, F Runde 2: gf-betrieb F-B1); `Accept-Language` liest ein
  possessives Muster (lange Leerraumfolge: vorher 1,2 s je 16 000 Zeichen).
  Das Wort vor einem „:“ gehört nicht zur E-Mail-Adresse, außer ein Passwortzeichen folgt
  („alarm:4711#Sonne@rechner“ ohne Schema). Ein `:Ziffern` ist nur ein Port, wenn der Teil
  davor wie ein Rechner aussieht (Punkt, auch IPv4, oder `localhost`) und die Zahl 1–65535
  ist; dann bleibt er vor `/`, Leerraum, Ende, einer Abfrage und `#/`, vor „#“ mit Text
  („https://rechner.example:8443#anker“) gilt er als Passwort (Runde 8, g7w B7-3; g8w B8-2).
  Grenzen: Ein Rechner ohne Punkt („https://host:8443?x=1“, Dienstname im Docker-Netz)
  erscheint als „host:***“; ein Benutzername mit Punkt vor einem Ziffern-Passwort einer
  abgeschnittenen Adresse gilt als Rechner mit Port. Adressen nennt accounti in
  Meldungen nur über `betrieb.protokoll.rechner_der_adresse` (Schema, Rechner, Port; auch IDN):
  Zugangsdaten stehen vor dem ersten `/`, `?` oder `#` und enden am letzten `@` dort, ein `@`
  in Abfrage oder Fragment ist keine Zugangsangabe (Runde 8, g7w B7-1). Ein unkodiertes `#`,
  `?` oder `/` im Passwort erkennt sie, wenn hinter „benutzer:…“ im Abschnitt bis zum nächsten
  `/` ein `@` steht (Runde 7, g6w B-2; Runde 8, g7w B7-2); ein `@` am Anfang oder weiter
  hinten im Pfad bleibt Pfad. Hat eine Adresse zwei Lesarten — Zugangsdaten „benutzer:…@“
  vor einem `#` bzw. `?` und dahinter ein weiteres `@` („https://alarm:Son@ne#x@rechner“) —,
  nennt sie keinen Rechner, sondern `MEHRDEUTIGE_ADRESSE` („Adresse nicht eindeutig – @ # ?
  / im Passwort prozentkodieren …“) in Warnung, `aufgaben_benachrichtigungen.adresse` und
  Verfahrensdokumentation (Folgepaket F, g8w B8-4; auch bei Zugangsdaten mit einer
  E-Mail-Adresse in der Abfrage). Grenzen: Ein Passwort mit Ziffern vorn und zwei
  unkodierten `/` („https://alarm:4711/a/b@rechner“) erscheint als „alarm:4711“; ein `@` im
  Passwort vor einem `/` („https://alarm:Son@ne/x@rechner“) nennt „ne“ (so liest urllib die
  Adresse); mit Port und `@` in der Abfrage („https://rechner:8443?an=jan@firma.example“)
  nennt die Meldung den Teil nach dem `@`; ein Benutzer ohne Passwort mit unkodiertem `#`/`?`
  erscheint als Rechner. Mit
  unkodiertem `#`, `?` oder `/` im Passwort verbindet sich urllib ohnehin mit dem Teil davor
  (Fehlkonfiguration; die Meldung nennt den gemeinten Rechner, nicht den angefragten) —
  Zugangsdaten in einer Adresse prozentkodieren (`%23`, `%3F`, `%2F`, `%40`). Der geplante Lauf
  schreibt die Ausgabe der Schritte ohne Rahmenzeichen, je Zeile höchstens 1000 Zeichen
  (DEBUG), Tracebacks von Python statt Rich (g6w B-1).

**Auswertungen**
- Die BWA-Zuordnung ist accountis eigene, an DATEV-Form 01 angelehnte Tabelle — nicht
  zahlengleich mit der BWA eines DATEV-Kanzleisystems (Sonderzeilen, Kostenstellen, „% der
  Gesamtleistung“, statistische Konten fehlen). Sie widerspricht den EÜR-Kennzahlen des
  Kontenrahmens nicht (Test), die „(prüfen)“-Bereiche werden bei der Umsetzung entschieden;
  SKR03 und SKR04 sind ohne Steuerberater zugeordnet — vor Einsatz gegenlesen lassen.
- Die BWA kumuliert im Wirtschaftsjahr. SuSa, EB-Werte und Kontenblatt bleiben im Kalenderjahr
  wie Saldovortrag, Jahres- und Monatssperre; bei abweichendem Wirtschaftsjahr steht dort ein
  Hinweis. Ein Abschluss im abweichenden Wirtschaftsjahr ist nicht Teil von 10b.
- Gezählt werden nur freigegebene Buchungen; offene Vorschläge stehen als Zahl im Hinweis; ein
  nicht festgeschriebener Monat ist als vorläufig gekennzeichnet.
- Eine eigene Kontenzuordnung ohne `ergebnisverwendung` grenzt die Ergebnisverwendung nicht ab
  (Hinweis in der BWA).
- `lade_buchungen` lädt alle Buchungen und filtert in Python — bei großen Beständen werden BWA und
  Kontenblatt langsam; keine Seitenaufteilung im Kontenblatt; PDF höchstens 20 000 Zeilen.
- Die OPOS-Auswertung zeigt den Stand von heute; der Stichtag bestimmt nur die
  Fälligkeitsstaffel.
- Kein Diagramm (Monatsverlauf).
- CSV ohne BOM wie alle CSV-Ausgaben der CLI; Formelinjektion entschärft, in Excel nie völlig
  ausgeschlossen (OWASP).

**Zweisprachigkeit**
- Übersetzt ist die Oberfläche; CLI, E-Mails, Mahnungen, Verfahrensdoku, ZUGFeRD-PDFs und
  CSV-Spaltenköpfe bleiben deutsch, Kontenbezeichnungen ebenso. Eigene BWA-Schemata bleiben
  deutsch. Die englischen Texte hat niemand mit englischer Muttersprache durchgesehen.
- Die Sprache wählt man nur im Browser (kein CLI-Befehl).

**Technik**
- Zwei Migrationen (`kontierungsgruende` und `kontierungsregeln` samt `rang`;
  `auth_benutzer.sprache`) hinter `46371a6681c2` (Paket C; davor hinter `a14acef69fae`,
  ursprünglich `ddc9a184ddb4`), Kopf und `SCHEMA_STAND` `e7153706b43a`, auszuführen gegen die Systemdatenbank **und** jede Gesellschaftsdatenbank
  (Alembic liest nur `ACCOUNTI_DB`); ohne die Spalte startet `serve` nicht. Altbuchungen haben
  keine Begründung (außer AfA über `AfaVorgang` und Prüfgründe an Beleg, Abgleich, Zuordnung,
  Kontakt).
- Unter PostgreSQL sind `kontierungsgruende` wie das Journal nur über die ORM-Sperre und
  `db.GESCHUETZT` unveränderbar, ohne Datenbank-Trigger (SQLite: Trigger); ein UPDATE an
  accounti vorbei geht durch und fällt, anders als bei Regeln, keinem Bestandsabgleich auf.
- Die HTMX-Fehlerwege sind serverseitig getestet; ob htmx sie im Browser eintauscht, prüft nur die
  Browserprobe (kein automatischer Browsertest im Projekt).
- Nicht in 10b: Seiten `/belege` (Liste, Suche, Eingang), `/opos` (Zuordnen, Vorschläge),
  `/zahlung` (Vorschlagsliste), `/aufgaben`, `/pruefung` (Befunde, Periodenabschluss),
  `/einstellungen` außer Sprache und gelernten Regeln — der Baum aus Spec 3 ist damit nur zum
  Teil gebaut. Die Vorschau vor der Freigabe von Zahlungslauf und USt-VA (Grenze in 10a) fehlt
  weiterhin.

---

## Offene Punkte (vor bzw. bei der Umsetzung)

1. *(erledigt: Abschnitt „Abgleich mit `main` ec32890“, Kopf unverändert `ddc9a184ddb4`)* **Merge von 7 abwarten** und die Signaturen aus „Was 7 liefert“ gegen `main` prüfen; ändert
   der Merge den Alembic-Kopf, die `down_revision` der Kontierungs-Migration anpassen.
2. *(in Chromium erledigt, Firefox offen — Abschnitt „Browser-Spike“)* **Browser-Spike** zu Beginn von Paket 3 (PDF-Antwort-CSP, 409/422-Fragment, `HX-Redirect`).
3. **„(prüfen)“-Stellen der BWA-Startzuordnung** gegen DATEV-Kontenliste 2026 und BWA-Form-01-Hilfe
   entscheiden (Zeilen 1, 7, 13, 17, 23–26; Grundsteuer 2375/7680 angleichen).
4. **GoBD-Randziffern** (Rz. 100 Wortlaut) gegen das BMF-Schreiben in der Fassung vom 14.07.2025
   prüfen, bevor die Begründung in die Verfahrensdoku oder die README geht.
5. **Migrationsweg je Datenbank** in `docs/betrieb.md` (Doku-Baustein unten) mit der Docker-Probe
   bestätigen; ein Befehl, der alle Datenbanken der Registry migriert, wäre ein eigener kleiner
   Baustein (nicht in 10b).
6. Nebenbefund für 10a: der Kommentar in `db/tabellen_auth.py:5–6` („beim Zusammenführen gehört er
   in die Migration“) ist überholt — beim Anfassen der Datei mit berichtigen.
7. Nebenbefund für den Kontenrahmen (nicht 10b): SKR04 7200–7299, 7400–7599, 6270–6279, 6290–6299
   und 6920/6923/6925–6927 haben keine EÜR-Kennzahl, die SKR03-Gegenstücke (4870–4899,
   2440–2451) Kz 183 — gegen die Anlage EÜR prüfen.

---

## Doku-Bausteine

**Stand 22.10.2026 (PR 10b-1):** Die Teile zu Paket 1–3 sind eingearbeitet — README (Zeilen
Supervisionsansicht, Benutzer & Rollen, neue Zeile Deutsch/Englisch, Abschnitt „Prüfen im
Browser“, Roadmap v0.5), CHANGELOG `[Unreleased]` (Hinzugefügt ohne Auswertungen, Geändert ohne
BWA, Behoben nur `korrigiere --lernen`/`lerne`), bauplan (Zeile 10 mit `i18n/`, weiter
„teilweise“, Absatz zu 10b Teil 1 und offenem Teil 2, Satz zur Verzahnung mit 7), architektur
(`api/`, `i18n/`, `pruefung/`, `klassifikation/` Stufe 3, Datenmodell, Sicherheit ohne CSV,
Erweiterungspunkte ohne „Auswertung mit Export“, „Neue Kontierungsregel“), betrieb (Sitzungen,
Mehrere Gesellschaften, „Update auf Baustein 10b“), `config/accounti.example.yaml` (`server.sprache`,
`server.max_vorschau_megapixel`, `auth.einmalcode_bestaetigung`, `buchhaltung.gelernte_regeln`).
**Offen für PR 10b-2:** README-Zeile BWA, Auswertungs-Beispiele unter „Erster Import“,
Kontenrahmen-Absatz und `bwa_zeile`, Abschnitt „BWA“; CHANGELOG-Punkte zu BWA, `bwa_zeile` und
CSV; bauplan „fertig“; architektur `bwa/`, `auswertung/`, Zeile „Auswertung mit Export“;
Konfigurationsabschnitt `bwa`.

Fertige Texte zum Einarbeiten beim Zusammenführen (diese Dateien werden in diesem Auftrag nicht
geändert). Grundlage ist der Stand **nach** dem Merge von 7 (README, CHANGELOG, Bauplan,
Architektur und Betrieb tragen dann die Texte aus 81d3b51).

### README.md

**Ersetzt** in der Feature-Tabelle die Zeilen `| 🔲 | **Supervisionsansicht** | … |`,
`| ✅ | **BWA** | Betriebswirtschaftliche Auswertung nach DATEV-Schema |` und
`| 🟨 | **Benutzer & Rollen** | … ; DE/EN folgt |` durch:

```markdown
| ✅ | **Supervisionsansicht** | Prüfen im Browser: Beleg links (PDF, Bild, E-Rechnung lesbar), Vorschlag rechts mit Confidence und gespeicherter Herkunft und Begründung; freigeben, korrigieren, zurückstellen per Tastatur; aus einer Korrektur wird auf Wunsch eine Regel mit Vorschau — nur in der Zahlungsrichtung des Umsatzes, abschaltbar —, die beim nächsten Lauf Vorrang hat; freigegebene Buchungen nur per Storno mit Einmalcode |
| ✅ | **BWA** | Kurzfristige Erfolgsrechnung angelehnt an DATEV-BWA Form 01 für SKR03 und SKR04, im Einklang mit den EÜR-Kennzahlen des Kontenrahmens: Monat, kumuliert im Wirtschaftsjahr, Vorjahresvergleich; Summen- und Saldenliste, Kontenblätter mit Übertrag und Absprung zum Beleg, OPOS-Auswertungen — im Browser und in der CLI, als CSV und PDF |
| ✅ | **Benutzer & Rollen** | Anmeldung mit Passwort (scrypt) und zweitem Faktor (TOTP, Wiederherstellungscodes), Sperre nach Fehlversuchen (Browser und Server-Shell getrennt gezählt), Rollen betrachter/buchhalter/freigeber/verwalter je Gesellschaft; Zahlungsläufe, Steuermeldungen und Storno freigegebener Buchungen nur mit Rolle und Einmalcode (Browser und CLI), in der CLI auch Buchungsfreigabe, Korrektur und Festschreibung; Vier-Augen-Freigabe |
| ✅ | **Deutsch/Englisch** | Oberfläche zweisprachig, Sprache je Benutzer oder nach Browser; Fachbegriffe wie „Buchungssatz“ bleiben deutsch |
```

**Ersetzt** im Abschnitt „### Erster Import“ die Zeilen

```bash
# BWA generieren
accounti bwa --period 2026-04
```

durch:

```bash
# Auswertungen
accounti bwa --period 2026-04 --vergleich                 # BWA mit Vorjahr (kumuliert im Wirtschaftsjahr)
accounti bwa --period 2026-04 --pdf bwa.pdf --csv bwa.csv
accounti abschluss kontenblatt --konto 4930 --jahr 2026 --von 2026-04-01 --bis 2026-04-30 --csv 4930.csv
accounti opos liste --richtung eingang --csv opos.csv     # eingang = Verbindlichkeiten
accounti opos staffel --pdf staffel.pdf
accounti abschluss susa --jahr 2026 --pdf susa.pdf
```

**Neuer Abschnitt** nach „### Betrieb, Benutzer und mehrere Gesellschaften“ (vor „## Architektur“):

````markdown
### Prüfen im Browser

```bash
accounti serve                          # dann https://…/pruefen (TLS über den Reverse-Proxy)
accounti review                         # dieselbe Liste in der Konsole, mit Begründung
accounti korrigiere 3f2a… --soll 4930 --haben 1200 --steuer 9 --lernen   # Regel in der Datenbank, mit Vorrang
accounti lerne --name miete --muster 'miete\s+\d{4}' --soll 4210 --haben 1200   # Regex, ebenfalls in der Datenbank
accounti regeln liste                   # gelernte, eigene und Standardregeln in Reihenfolge
accounti regeln deaktivieren <ID> --grund "zu breit"
accounti regeln uebernehmen --probe     # alte gelernt_*-Einträge aus der Regeldatei übernehmen
```

Gelernte Regeln gelten nur in der Zahlungsrichtung des Umsatzes, aus dem sie entstanden sind.
Mit `buchhaltung.gelernte_regeln: pruefen` legen sie ihre Buchungen nur vor, mit `aus` greifen sie
gar nicht. Tasten in der Queue: `j`/`k` weiter/zurück, `f` freigeben, `e` korrigieren, `r` Regel,
`z` zurückstellen, `b` Beleg öffnen, `?` Hilfe (dort auch abschaltbar). Ändert eine Korrektur das
Sachkonto, fragt accounti den Steuerschlüssel ausdrücklich ab. Vorschläge entscheidet man in der
angemeldeten Sitzung (Passwort und zweiter Faktor); freigegebene Buchungen korrigiert accounti als
Storno mit Neubuchung, mit frischem Einmalcode. Jede Aktion steht mit dem angemeldeten Benutzer im
Journal.
````

**Ersetzt** im Abschnitt „## Kontenrahmen & Steuer“ den Punkt `- BWA-Zuordnung (BWA-Zeile je
Konto)` durch nichts, im YAML-Beispiel die Zeilen `bwa_zeile: 1` und `bwa_zeile: 14` durch nichts,
und ergänzt nach dem Satz zu `kontenrahmen_skr03.yaml`:

```markdown
Die BWA-Zuordnung steht getrennt davon in `accounti/bwa/schema_skr03.yaml` bzw. `…_skr04.yaml`;
die Ergebnisverwendung (`ergebnisverwendung`) steht einmal im Kontenrahmen und gilt für BWA und EÜR.
```

**Ersetzt** den Abschnitt „## BWA (Betriebswirtschaftliche Auswertung)“ (Tabelle mit Zeilen und
Kontenbereichen) durch:

```markdown
## BWA (Betriebswirtschaftliche Auswertung)

Die BWA wird aus den freigegebenen Buchungssätzen berechnet — aus denselben Kontobewegungen wie
Summen- und Saldenliste und Kontenblatt, mit abgespaltener Steuer; Stornos heben sich auf. Der
Aufbau lehnt sich an die DATEV-BWA Form 01 (Kurzfristige Erfolgsrechnung) an: Gesamtleistung,
Rohertrag, Kostenarten, Betriebsergebnis, neutrales Ergebnis, Ergebnis vor Steuern, vorläufiges
Ergebnis. Die Zuordnung der Konten steht je Kontenrahmen in `src/accounti/bwa/schema_skr03.yaml`
bzw. `schema_skr04.yaml` (eigene Datei über `bwa.schema`) und ist eine Tabelle von accounti, keine
DATEV-Tabelle: Die engste passende Kontenspanne bestimmt die Zeile, jedes Erfolgskonto gehört zu
genau einer Zeile oder zur Ergebnisverwendung, keine Zeile widerspricht der EÜR-Kennzahl des
Kontos (Einnahmen nur in Ertragszeilen, Ausgaben nur in Aufwandszeilen), und das vorläufige
Ergebnis entspricht dem Saldo der Erfolgskonten ohne Ergebnisverwendung. Spalten: Monat, kumuliert
ab Beginn des Wirtschaftsjahres (`datev.wirtschaftsjahr_beginn`), Vorjahresmonat, Vorjahr
kumuliert, Abweichung; ein nicht festgeschriebener Monat ist als vorläufig gekennzeichnet.
```

**Ersetzt in „### v0.5 — Oberfläche & Betrieb“** die Zeilen
`- [ ] Web-UI: Supervisions-Queue mit Belegansicht, BWA mit Vorjahresvergleich` und
`- [ ] DE/EN in der Oberfläche` durch:

```markdown
- [x] Web-UI: Supervisions-Queue mit Belegansicht, Korrektur → Regel, BWA mit Vorjahresvergleich, Kontenblätter, CSV/PDF
- [x] DE/EN in der Oberfläche
```

### CHANGELOG.md

**Unter `## [Unreleased]` → `### Hinzugefügt`** oben einfügen:

```markdown
- **Web-Oberfläche: Supervisions-Queue, Auswertungen, Deutsch/Englisch** (Baustein 10b):
  `/pruefen` zeigt unsichere Buchungen mit dem Beleg links (PDF im Browser, PNG/JPEG, TIFF als
  Seitenbilder, XRechnung und ZUGFeRD als lesbare Ansicht des strukturierten Teils; ohne Beleg
  die offene Nachforderung bzw. die `belegfrei`-Regel; bei internen Buchungen wie AfA Herkunft
  und Rechenweg) und dem Vorschlag rechts (Konten mit Bezeichnung, Steuerschlüssel, Beträge,
  Confidence, Herkunft und Begründung, Aufgaben). Freigeben, korrigieren und zurückstellen
  (Rückfrage als Aufgabe) in einem Schritt, per Tastatur (`j k f e r z b ?`, abschaltbar) und mit
  HTMX ohne Seitenwechsel; ein Prüfstand in jedem Formular verhindert, dass eine veraltete Ansicht
  storniert, Konflikte und Fachfehler erscheinen als Meldung, ein neues Sachkonto verlangt die
  ausdrückliche Steuerangabe. Aus der Korrektur eines Kontierungsvorschlags wird auf Wunsch eine
  Regel — mit Vorschau (Treffer je Richtung, verdrängte Regel, Warnungen), nur mit dem neuen Recht
  `regeln_lernen` (buchhalter, verwalter), nur in der Zahlungsrichtung des Umsatzes, gespeichert
  in der Datenbank der Gesellschaft, im Journal (samt Bestandsabgleich in `journal pruefen`) und
  mit Vorrang vor eigenen und Standardregeln; `/pruefen/regeln` und
  `accounti regeln liste|deaktivieren|uebernehmen`. `/buchungen/{id}` zeigt Storno-Kette,
  Korrektur und Journal und korrigiert freigegebene oder exportierte Buchungen als Storno mit
  Neubuchung — mit frischem Einmalcode. `/auswertungen`: BWA mit Vorjahresvergleich (kumuliert im
  Wirtschaftsjahr, im Einklang mit den EÜR-Kennzahlen), Summen- und Saldenliste, Kontenblätter
  mit Übertrag und Absprung über die Buchung zum Beleg, offene Posten mit Fälligkeitsstaffel —
  jeweils als CSV (gleich der CLI-Ausgabe) und PDF; `accounti abschluss kontenblatt`,
  `--csv`/`--pdf` an `accounti bwa`, `opos liste`, `opos staffel`, `--pdf` an `abschluss susa`.
  Oberfläche auf Deutsch und Englisch (Sprache je Benutzer, sonst nach Browser; Zahlen und Daten
  je Sprache; Fachbegriffe wie „Buchungssatz“ bleiben deutsch). Klassifikation, Kreditkarte,
  Anlagen, Marktplatz und offene Posten speichern jetzt zu jeder Buchung Quelle, Regel und
  Begründung (`kontierungsgruende`). HTMX 2.0.11 (0BSD) liegt lokal unter `/statisch`. Neue
  Abschnitte `bwa` (optional); neue Schlüssel `buchhaltung.gelernte_regeln`, `server.sprache`,
  `server.max_vorschau_megapixel`; Kontenrahmen mit `ergebnisverwendung`. Zwei Migrationen
  hinter `46371a6681c2` — `accounti db upgrade` für die Systemdatenbank und jede Gesellschaft.
```

**Unter `### Geändert`** oben einfügen:

```markdown
- `accounti korrigiere --lernen` **und `accounti lerne`** speichern die Regel in der Datenbank
  der Gesellschaft (Tabelle `kontierungsregeln`, mit Journal) statt sie an die Regeldatei
  anzuhängen; accounti schreibt die Regeldatei nicht mehr. Gelernte Regeln haben Vorrang vor der
  Regeldatei und den Standardregeln und gelten nur in der Zahlungsrichtung ihres Quellumsatzes.
  `korrigiere --lernen`, `lerne` und `regeln deaktivieren|uebernehmen` verlangen mit
  eingerichteten Benutzern das Recht `regeln_lernen` (bei `korrigiere --lernen` mit demselben
  Einmalcode). Früher gelernte `gelernt_*`-Einträge übernimmt `accounti regeln uebernehmen`.
- Regeln in der Regeldatei dürfen ein optionales Feld `richtung: ausgabe|einnahme` tragen; ohne
  Angabe gelten sie wie bisher in beide Richtungen.
- `accounti classify`, `bank lauf` und `opos verbuchen` nehmen zur Regeldatei der Gesellschaft die
  gelernten Regeln aus der Datenbank hinzu — wie die REST-Läufe; das Regelwerk wird erst nach der
  Laufsperre geladen.
- `accounti review` zeigt die Begründung und zurückgestellte Buchungen; `bestaetige` und
  `korrigiere` schließen eine offene Rückfrage und die Aufgabe `kontierung_pruefen` zur Buchung.
- `accounti korrigiere` und `buchung storniere` nutzen den Kontenrahmen samt
  `abschluss.kontenzuordnung` — wie Summen- und Saldenliste und Abschluss.
- `accounti bwa --period` rechnet jetzt (bisher ein Platzhalter), kumuliert im Wirtschaftsjahr;
  `bwa`, `opos liste` und `opos staffel` kennen `--config` (und `bwa` `--db`), `--gesellschaft`
  greift damit auch dort.
- Die Verfahrensdokumentation nennt die Regeldatei der Gesellschaft und die gelernten Regeln; der
  Aufbewahrungsbericht führt Kontierungsgründe und -regeln.
- Die Seiten aus Baustein 10a sind übersetzbar; das Layout trägt Sprachauswahl und HTMX; die
  Einmalcode-Prüfung des Browsers liegt in `api/einmalcode.py`.
- Das Feld `bwa_zeile` (alte BWA-Nummerierung) ist aus `pruefung/skr03.yaml` und dem Modell
  `Konto` entfernt; maßgeblich ist `bwa/schema_*.yaml`.
```

**Unter `### Behoben`** oben einfügen:

```markdown
- BWA: Summenzeilen wurden nicht berechnet, Soll und Haben addiert statt saldiert, Kontenbereiche
  doppelt gezählt (4360–4399, 7100–7199), Stornos nicht aufgehoben und in SKR03 Bestandskonten
  der Klasse 7 als Zinsen und Steuern gewertet (SKR04-Nummern im SKR03-Schema); SKR04 fehlte.
- `korrigiere --lernen` und `lerne` hängten die Regel ans Ende der Regeldatei — hatte eine frühere
  Regel falsch kontiert, griff die gelernte nie; dabei gingen die Kommentare der Datei verloren,
  und im Container (schreibgeschütztes `config/`) brachen beide ab.
- CSV-Ausgaben der Summen- und Saldenliste entschärfen Textzellen gegen Formelinjektion.
```

### docs/bauplan.md

**Ersetzt in der Bausteinkarte** die Zeile `| 10 | Supervision-Web-UI, Auth & Betrieb | … | 🟨 teilweise | … |` durch:

```markdown
| 10 | Supervision-Web-UI, Auth & Betrieb | `api/` `auth/` `betrieb/` `i18n/` | ✅ fertig | [Spec](specs/2026-08-10-web-ui-auth-betrieb.md) |
```

**Ersetzt** im Absatz zu Baustein 7 den Satz „Mit Baustein 10a verzahnt: Freigabe, Korrektur,
Storno und Festschreibung nur mit Rolle und Einmalcode, im Journal der angemeldete Benutzer, …“
am Anfang durch:

```markdown
Mit Baustein 10 verzahnt: Freigabe, Korrektur, Storno und Festschreibung nur mit Rolle — in der
CLI mit Einmalcode, im Browser in der Sitzung mit zweitem Faktor (Storno freigegebener Buchungen
auch dort mit Einmalcode) —, im Journal der angemeldete Benutzer, …
```

**Ersetzt** den Absatz „**Baustein 10 ist teilweise fertig** …“ durch:

```markdown
**Baustein 10 ist fertig** ([Plan 10a](plans/2026-10-26-auth-gesellschaften-betrieb-api.md),
[Plan 10b](plans/2026-10-27-web-oberflaeche.md)): Benutzer mit Passwort und zweitem Faktor,
Rollen je Gesellschaft, Freigaben von Zahlungsläufen und Steuermeldungen nur mit Rolle und
Einmalcode, mehrere eigene Gesellschaften, REST-API, Docker Compose mit verschlüsselter Sicherung
und Aufbewahrungsbericht (10a). Dazu die Oberfläche (10b): Supervisions-Queue mit Belegansicht
(PDF, Bild, E-Rechnung), gespeicherter Herkunft und Begründung, Korrektur in einem Schritt und per
Tastatur, Korrektur → Regel mit Vorschau und Vorrang (in der Datenbank, im Journal),
Storno-Korrektur freigegebener Buchungen über Baustein 7 mit Einmalcode, BWA mit
Vorjahresvergleich im Einklang mit der EÜR, Summen- und Saldenliste, Kontenblätter mit Absprung
zum Beleg, OPOS-Auswertungen, CSV und PDF, Deutsch und Englisch. Weitere Seiten des Spec-Baums
(Belegliste, OPOS-Zuordnung, Zahlungsvorschlag, Aufgaben, Prüfbefunde und Periodenabschluss,
Einstellungen) laufen weiter über die CLI.
```

### docs/architektur.md

**Ersetzt** den Abschnitt `### bwa/` durch:

```markdown
### `bwa/` *(vorhanden — [Baustein 10](specs/2026-08-10-web-ui-auth-betrieb.md))*

`berechnung.py` berechnet die BWA aus `abschluss.salden.lade_bewegungen` (nur freigegebene
Buchungen, Steuer abgespalten, Stornos heben sich auf): je Basiszeile der Saldo ihrer Konten nach
der Art der Zeile (Erträge Haben − Soll, Aufwand Soll − Haben), Summenzeilen per Formel aus
Zeilennummern (eigener Parser, kein `eval`), Monat, kumuliert ab Beginn des Wirtschaftsjahres,
Vorjahr, Abweichung, Festschreibungsstand; je Zeile die Konten für den Absprung. `schema.py` lädt
`schema_skr03.yaml`/`schema_skr04.yaml` (oder `bwa.schema`) und prüft: die engste passende Spanne
bestimmt die Zeile (wie im Kontenrahmen), jedes Erfolgskonto liegt in genau einer Zeile oder in
der Ergebnisverwendung des Kontenrahmens, Formeln nur auf frühere Zeilen. Angelehnt an DATEV-BWA
Form 01, eigene Zuordnung von accounti; Leitkonten und der Einklang mit den EÜR-Kennzahlen
(`kontenrahmen.euer_kz`) im Test festgeschrieben.
```

**Ersetzt** im Abschnitt `### api/` den letzten Absatz („Die Oberfläche ruft dieselben Funktionen
wie die CLI. Geplant auf diesem Gerüst: …“) durch:

```markdown
- `seiten/pruefen.py` — Supervisions-Queue: Liste, Arbeitsfläche (Beleg | Vorschlag mit
  Confidence, Herkunft und Begründung | Aktionen), freigeben, korrigieren (mit Regel),
  zurückstellen, Regelvorschau (HTMX-Fragment), gelernte Regeln. Ruft `buchung.pruefschlange` und
  `klassifikation.lernen` — dieselben Funktionen wie `review`, `bestaetige`, `korrigiere`, `lerne`.
- `seiten/buchungen.py` — Buchung mit Storno-Kette und Journal; Korrektur und Storno über
  `pruefung.storno` (Baustein 7), mit frischem Einmalcode (`einmalcode.py`, auch für die
  Freigaben in `seiten/freigaben.py`).
- `seiten/belege.py`, `belegantwort.py` — Belegvorschau nur aus dem Archiv der aktiven
  Gesellschaft: Typ aus dem Inhalt, inline nur PDF/PNG/JPEG, TIFF als PNG-Seiten, E-Rechnung als
  eigene Ansicht, alles andere nur als Download.
- `seiten/auswertungen.py` — BWA, SuSa, Kontenblatt, OPOS, Export (`auswertung.ausgabe`),
  Übersicht mit Kennzahlen.
- `seiten/sprache.py` — Sprache am Benutzer.
- `handeln.py` — `im_namen(a)`: der angemeldete Benutzer als Person im Journal
  (`pruefung.person.journal_kontext`).
- `htmx.py` — HTMX-Erkennung; 409/422 als Fragment, ohne Sitzung `HX-Redirect`, CSRF-Fehler
  `HX-Refresh`, Datenbank beschäftigt 503 (htmx tauscht andere Fehlerantworten nicht ein).
- `statisch/` — `accounti.css` und je Bereich ein Stylesheet, `htmx-2.0.11.min.js` (ohne `eval`,
  ohne Verlaufscache, Prüfsumme im Test), `pruefen.js` (Tasten, Fehlerhinweis). Keine
  Inline-Skripte und -Stile; eigene Dateien mit Versionsanhang.

Die Oberfläche ruft dieselben Funktionen wie die CLI; jede Seite liest Daten nur über
`gesellschaft_db` und `a.gesellschaft`, Personen im Journal sind angemeldete Benutzer.
```

**Ersetzt** im Abschnitt `### pruefung/` im Punkt `journal.py` + `ereignisse.py` den Satz „Person
und Grund aus `person.journal_kontext` — mit Benutzern setzt ihn die Rechteprüfung der CLI
(`befehle.handelnde_person`), für API-Token die REST-API.“ durch:

```markdown
Person und Grund aus `person.journal_kontext` — mit Benutzern setzt ihn die Rechteprüfung der CLI
(`befehle.handelnde_person`), im Browser die Sitzung (`api/handeln.im_namen`), für API-Token die
REST-API. Erfasst sind auch die gelernten Kontierungsregeln (`kontierungsregeln`, mit
Bestandsabgleich).
```

**Neue Abschnitte** nach `### api/`:

```markdown
### `i18n/` *(vorhanden — [Baustein 10](specs/2026-08-10-web-ui-auth-betrieb.md))*

Zweisprachigkeit der Oberfläche ohne Zusatzpaket: `jinja2.ext.i18n` (newstyle) mit Callables,
die die Sprache der Anfrage aus einer Context-Variable lesen; Deutsch ist Quellsprache, `en.yaml`
der Katalog (Glossar im Kopf). Sprachwahl: Benutzer → `Accept-Language` → `server.sprache`.
Formate für Beträge, Daten, Prozent, Monate je Sprache. `N_()` markiert Texte im Python-Code,
`Text()` übersetzbare Meldungen. Ein Test fordert für jeden Text einen Eintrag; geschützte
Fachbegriffe bleiben deutsch. CSV, CLI und E-Mails bleiben deutsch.

### `auswertung/` *(vorhanden — [Baustein 10](specs/2026-08-10-web-ui-auth-betrieb.md))*

`bericht.py` — ein Berichtsmodell (Spalten, Zeilen, Summen, Hinweise) mit Umwandlern für BWA,
SuSa, Kontenblatt, OPOS; `ausgabe.py` — CSV (Semikolon, deutsche Zahlen, Schutz gegen
Formelinjektion) und PDF (fpdf2, Liberation Sans). CLI und Browser erzeugen dieselben Dateien.
```

**Ergänzt** im Abschnitt `### klassifikation/` nach dem Diagramm:

```markdown
**Stufe 3 — Lernschleife** (`lernen.py`): Aus der Korrektur eines Kontierungsvorschlags entsteht
auf Wunsch eine Regel (Text-Muster aus Gegenpartei oder Verwendungszweck, nur ganze Wörter,
Zahlungsrichtung des Umsatzes, Konten der Korrektur und Schlüssel der Neubuchung), mit Vorschau
der Treffer und der verdrängten Regel. Gelernte Regeln — auch Regexe aus `accounti lerne` — liegen
je Gesellschaft in der Tabelle `kontierungsregeln` (im Journal, nur deaktivierbar) und gehen in
`lade_regelwerk` vor der Regeldatei und den Standardregeln — die erste passende Regel gewinnt.
`buchhaltung.gelernte_regeln` schaltet sie auf automatisch, vorlegen oder aus. Bei Belegbuchungen
lernt der Kontakt sein Sachkonto. Jede Kontierung speichert Quelle, Regel und Begründung in
`kontierungsgruende` (auch Kreditkarte, Anlagen, Marktplatz, offene Posten; nur anfügen).
```

**Ergänzt** die Tabelle im Abschnitt „## Datenmodell“ um (und streicht im Satz darunter nichts;
`Konto.bwa_zeile` entfällt):

```markdown
| `Kontierungsgrund` | Quelle (Regelwerk, LLM, Beleg, Kontakt, Standard, OPOS, Kreditkarte, Anlagen, Marktplatz), Regel, LLM-Modell, Begründung, Zeitpunkt | → `Buchungssatz` (ohne Fremdschlüssel, nur anfügen) |
| `Kontierungsregel` | Name, Muster (Text oder Regex), Feld, Richtung, Soll, Haben, Steuerschlüssel, Buchungstext, Herkunft, angelegt/deaktiviert von und am, Grund | → `Buchungssatz` (Quelle), im Journal |
```

**Ergänzt im Abschnitt „## Sicherheit“** am Ende:

```markdown
- Belege gehen nur aus dem Archiv der aktiven Gesellschaft an den Browser, per ID, mit dem Typ
  aus dem Inhalt; inline nur PDF und Bilder, E-Rechnungen als eigene Ansicht, alles andere als
  Download. Keine Inline-Skripte und -Stile, HTMX ohne `eval`
- Vorschläge entscheidet die angemeldete Sitzung (Passwort und zweiter Faktor); Storno und
  Korrektur freigegebener Buchungen verlangen wie Zahlungslauf und USt-VA einen frischen
  Einmalcode; im Journal steht immer der angemeldete Benutzer
- Regelmuster aus dem Browser sind Text, keine regulären Ausdrücke; gelernte Regeln gelten nur in
  ihrer Zahlungsrichtung; CSV-Exporte sind gegen Formelinjektion entschärft
- TIFF-Belege dekodiert nur der TIFF-Decoder von Pillow, mit Pixelgrenze je Seite; Belegdateien
  werden vor der Auslieferung gegen ihren Hash geprüft
```

**Ersetzt** den Abschnitt `### Neue Kontierungsregel hinzufügen` (Überschrift und Kommentar
„(geplant)“) durch:

````markdown
### Neue Kontierungsregel hinzufügen

Am einfachsten aus der Korrektur: im Browser „Regel daraus machen“ oder
`accounti korrigiere <ID> --soll … --haben … --lernen`; einen regulären Ausdruck nimmt
`accounti lerne --muster … --soll … --haben … --name …` — beide landen in der Datenbank der
Gesellschaft und haben Vorrang. Handgeschriebene Regeln (auch reguläre Ausdrücke) stehen in der
Regeldatei der Gesellschaft (ohne Registry `config/regeln.yaml`; accounti schreibt sie nicht);
die erste passende gewinnt, `richtung` ist optional:

```yaml
- name: "mein_lieferant"
  muster: "Firma XY GmbH"
  feld: "gegenkonto_name"
  richtung: "ausgabe"          # optional: ausgabe | einnahme, ohne Angabe beide
  soll_konto: "3300"
  haben_konto: "1200"
  steuer_schluessel: 9
  buchungstext: "Wareneinkauf Firma XY"
```
````

**Ergänzt** die Tabelle in „### Neuen Baustein anschließen“ um:

```markdown
| Texte der Oberfläche | `_()`/`{% trans %}` in Vorlagen, `N_()`/`Text()` im Code, Eintrag in `src/accounti/i18n/en.yaml` | `tests/test_i18n_katalog.py` |
| Auswertung mit Export | Fachfunktion + Umwandler in `auswertung/bericht.py` | `bericht_csv`, `bericht_pdf`; Seite unter `/auswertungen`, in der CLI `--csv`/`--pdf` am fachlich passenden Befehl (keine eigene Befehlsgruppe) |
| Schreibende Seite | Thread-Funktion in `with im_namen(a):`, Fachfunktion mit `von=`/`person=`, Commit in der Seite; Freigaben mit Außenwirkung zusätzlich `einmalcode.bestaetige_einmalcode` | `tests/test_api_journal_person.py`, Rechte-Matrix |
```

### docs/betrieb.md

**Ersetzt** im Abschnitt „## Benutzer, Rollen, Anmeldung“ im Punkt **Sitzungen** den Satz „Jede
Freigabe im Browser verlangt zusätzlich einen frischen Einmalcode und gilt nur für den angezeigten
Inhalt (…)“ durch:

```markdown
Freigaben mit Außenwirkung und endgültige Korrekturen verlangen im Browser zusätzlich einen
frischen Einmalcode: Zahlungsläufe
und USt-VA (gelten nur für den angezeigten Inhalt — Empfänger, IBAN, Betrag, Verwendungszweck; hat
sich der Entwurf seitdem geändert, 409) sowie Storno und Korrektur freigegebener Buchungen
(`/buchungen/…`). Vorschläge in der Supervisions-Queue (`/pruefen`) entscheidet die angemeldete
Sitzung ohne weiteren Code — sie ist mit Passwort und zweitem Faktor entstanden und läuft nach
30 Minuten Leerlauf ab; in der CLI verlangen dieselben Befehle den Einmalcode, weil sie keine
Sitzung hat.
```

**Ersetzt** im Abschnitt „## Mehrere Gesellschaften“ den Satz „`classify`, `bank lauf`,
`opos verbuchen`, `lerne` und `korrigiere --lernen` nutzen die Regeldatei der Gesellschaft (ohne
Registry wie bisher `config/regeln.yaml`).“ durch:

```markdown
`classify`, `bank lauf` und `opos verbuchen` nutzen die Regeldatei der Gesellschaft (ohne
Registry wie bisher `config/regeln.yaml`) und davor deren gelernte Regeln; `lerne` und
`korrigiere --lernen` speichern in die Datenbank der Gesellschaft, nicht in die Datei.
```

**Ergänzt** im Abschnitt „## Upgrades“ nach dem Absatz zu Baustein 7:

````markdown
**Update auf Baustein 10b** (Migrationen auf `ddc9a184ddb4`: `kontierungsgruende`,
`kontierungsregeln`, `auth_benutzer.sprache`): Alembic migriert die Datenbank aus `ACCOUNTI_DB` —
bei mehreren Gesellschaften **jede** Datenbank einzeln, die Systemdatenbank zuerst (ohne
`auth_benutzer.sprache` startet `serve` nicht); die URLs stehen in `.env`:

```bash
docker compose run --rm -e ACCOUNTI_DB="$ACCOUNTI_SYSTEM_DB" --entrypoint alembic app -c /app/alembic.ini upgrade head
docker compose run --rm -e ACCOUNTI_DB="$ACCOUNTI_DB_MUSTER" --entrypoint alembic app -c /app/alembic.ini upgrade head
docker compose run --rm -e ACCOUNTI_DB="$ACCOUNTI_DB_TOCHTER" --entrypoint alembic app -c /app/alembic.ini upgrade head
docker compose run --rm app -g muster regeln uebernehmen --probe   # alte gelernt_*-Regeln ansehen, dann ohne --probe
```

Früher gelernte Regeln (`gelernt_*` am Ende der Regeldatei) übernimmt `regeln uebernehmen` in die
Datenbank (mit eingerichteten Benutzern mit dem Recht `regeln_lernen` und Einmalcode, z. B.
`-e ACCOUNTI_BENUTZER=chef -e ACCOUNTI_EINMALCODE=…`); danach die genannten Einträge von Hand
aus der Datei löschen. Hat ein Befehl des neuen
Abbilds die neuen Tabellen vor der Migration schon angelegt, übernimmt die Migration sie.
````

### config/accounti.example.yaml

**Ergänzt** im Abschnitt `server`:

```yaml
  sprache: de                     # Oberfläche, wenn weder Benutzer noch Browser eine Sprache nennen (de|en)
  max_vorschau_megapixel: 40      # TIFF-Belege werden darüber nicht als Bild umgewandelt
```

**Ersetzt** im Abschnitt `auth` den Kommentar der Zeile `einmalcode_bestaetigung: true` durch:

```yaml
  einmalcode_bestaetigung: true   # Browser: Zahlungslauf, USt-VA, Storno freigegebener Buchungen mit Einmalcode (CLI: immer)
```

**Ergänzt** im Abschnitt `buchhaltung`:

```yaml
  gelernte_regeln: automatisch    # automatisch | pruefen (nur vorlegen) | aus — Regeln aus Korrekturen und accounti lerne
```

**Neuer, optionaler Abschnitt:**

```yaml
# BWA (optional — ohne Abschnitt gilt das mitgelieferte Schema zum Kontenrahmen)
# bwa:
#   schema: config/bwa.yaml       # eigene Zeilen und Kontenbereiche, Format wie src/accounti/bwa/schema_skr03.yaml
```
