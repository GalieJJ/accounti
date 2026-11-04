# Spec: Oberfläche — Übersicht, Einrichtung, Bedienung, Design

- **Status:** entschieden (2026-10-26). Die Fragen F1–F5 sind beantwortet (Abschnitt 12), die
  Folgen sind in Entscheidungen, Anforderungen, Akzeptanzkriterien, Paketschnitt und Skizzen
  eingearbeitet. Grundlage für die Paketpläne
- **Baustein:** 10c — dritter Teil von Baustein 10 (siehe [Bauplan](../bauplan.md)); nach 10a (#27)
  und 10b-1 (`feat/web-oberflaeche`, fa6ceb9)
- **Ziel-Branches:** je Paket ein PR, siehe Abschnitt 9 (`feat/oberflaeche-p1-design` …)
- **Grundlage:** `main` 48b2d9e; Worktree `web-oberflaeche` fa6ceb9 (Plan
  `docs/plans/2026-10-27-web-oberflaeche.md`); Vorschau `http://127.0.0.1:8400` am 26.10.2026,
  angemeldet als `demo`. Screenshots unter `ui-ist/` (Anhang C), Text-Skizzen in
  [`2026-10-26-oberflaeche-skizzen.md`](2026-10-26-oberflaeche-skizzen.md)
- **Ablage beim Zusammenführen:** `docs/specs/2026-10-26-oberflaeche-einrichtung.md`,
  Skizzen als `docs/specs/2026-10-26-oberflaeche-skizzen.md`

### Auf einen Blick

| Frage | Festlegung (Begründung in Abschnitt 5, Entscheidungen vom 26.10.2026 in Abschnitt 12) |
|-------|----------------------------------------|
| Wo leben Einstellungen? | In der Gesellschaftsdatenbank, nur anfügend versioniert, mit Journal; ab der ersten Änderung im Browser gilt der Stand aus der Datenbank. Die YAML bleibt Startwert und kann Abschnitte festlegen; Betriebswerte bleiben in Datei und Umgebung; `config/` bleibt schreibgeschützt (E1, E2; entschieden F1) |
| Geheimnisse? | Tresor-Tabelle in der Gesellschaftsdatenbank (AES-GCM, `ACCOUNTI_SCHLUESSEL`); `${VAR}` in der Datei geht vor (E4) |
| Wie bestätigt? | drei Stufen: frei, Einmalcode (10 min Verwaltungsmodus), Antrag mit zweiter Person für das Abschwächen von Kontrollen (E6) |
| Wer arbeitet mit? | Inhaber mit allen Rollen; Mitarbeitende mit eigenem Zugang per Einladungslink und getrennten Rollen; kein Zugang für den Steuerberater. Vier-Augen für Steuermeldungen ist wählbar, Voreinstellung aus, bei Mitarbeitenden empfohlen (entschieden F2; A78, A82, A125) |
| Erster Start? | Assistent im Browser, nur mit Einrichtungscode aus dem Serverstart (E7) |
| Prüfschlange? | Ausgangszustand ohne Eingabefeld, drei Aktionen; Korrektur über Kontovorschläge statt Kontonummer; Regel als Angebot danach; Gruppen und Massenfreigabe, KI-Vorschläge ab 3 gleichen über der Prüfschwelle (6.3; entschieden F4) |
| Handy? | Übersicht, Prüfen, Beleg hochladen und, für Freigabe-Berechtigte, Freigaben von Zahlungsläufen und USt-VA; PDF-Belege über „PDF öffnen“ im Systembetrachter, keine neue Abhängigkeit (entschieden F3; E11, A126) |
| Übersicht? | „Heute zu tun“ in Karten nach Dringlichkeit, rollenabhängig, jede Zahl ein Link (6.2) |
| Design? | eigenes ruhiges Design-System: Token hell/dunkel, Systemschrift, CSS ohne Framework, htmx, CSP ohne Inline-Code, WCAG 2.2 AA (6.8, 6.9) |
| Reihenfolge? | Welle 1: P1 Design & Gerüst parallel zu P4 Einstellungen (Kern + CLI); Welle 2: P2 Übersicht, P3 Prüfschlange, P5 Einstellungsseiten, 10b-2 nach P1; Welle 3: P6 Benutzer; Welle 4: P7 Assistent (entschieden F5, Abschnitt 9) |

---

## 1. Kontext

### 1.1 Rückmeldung des Nutzers

Nach der ersten Vorschau von 10b-1 (Prüfschlange mit Belegvorschau, Korrektur → Regel, DE/EN):
„An der UI müssen wir noch arbeiten. Wir brauchen auch eine UI, um alles einzurichten.“
Auf Nachfrage nannte er drei Dinge, die am meisten stören:

1. **Bedienung und Abläufe.** Es stehen zu viele Felder auf einmal da, und es ist unklar, was zu
   tun ist. Korrektur und Regel sind zu umständlich.
2. **Es fehlt eine Übersicht.** Eine Startseite, die zeigt, was heute zu tun ist, gibt es nicht.
   Die Navigation ist unklar.
3. **Handy und Tablet.** Die Oberfläche muss auch auf kleinen Bildschirmen gut bedienbar sein.

Das Aussehen selbst war nicht der Hauptpunkt. Gewünscht ist trotzdem ein **eigenes, ruhiges
Design**: hell und dunkel, klare Tabellen, weiter serverseitig mit htmx, kein schweres
JS-Framework.

Die Einrichtung soll **alles** abdecken:

- Firma und Steuern
- Bank und Zahlungen
- Benutzer und Rollen
- Belege und Anbindungen

Gewünschter Ablauf: ein **Assistent beim ersten Start**, der Schritt für Schritt nur das
Nötigste abfragt, und dazu **Einstellungsseiten** für alles Weitere.

### 1.2 Was die Vorschau heute zeigt (gemessen am 26.10.2026)

Chromium 1223 über Playwright, Fenster 1440 × 900 und 390 × 844, hell und dunkel (Dateien in
Anhang C).

| # | Befund | Messung bzw. Beleg | Folge |
|---|--------|--------------------|-------|
| I1 | Auf 390 px scrollt die Prüfliste waagrecht | `scrollWidth` von `/pruefen` = **741 px** bei 390 px Fensterbreite | WCAG 1.4.10 (Reflow) verletzt; auf dem Handy kaum bedienbar |
| I2 | „Freigeben“ liegt auf dem Handy unter dem ersten Bildschirm | Arbeitsfläche 390 px: Seite **2064 px** hoch. Oberkante des Knopfs „Freigeben“ bei **1117 px**, Bildschirmhöhe 844 px. Vor dem Vorschlag (ab 610 px) steht der Beleg (ab 280 px) | Die häufigste Aktion braucht auf dem Handy Scrollen |
| I3 | Zu viele Felder auf einmal | In der Arbeitsfläche stehen **9 Eingabefelder** und **4 Knöpfe** gleichzeitig: Soll, Haben, Steuerschlüssel, Grund, Regel-Haken, Muster, „Suchen in“, Rückfrage, „an“ sowie Freigeben, Korrigieren, Regelvorschau, Zurückstellen | Nutzerbefund 1: unklar, was zu tun ist |
| I4 | Konten muss man als Nummer eintippen | Soll und Haben sind freie Textfelder (`pattern="[0-9]{4,8}"`). Die Liste zeigt nur „4980 an 1200 · Steuerschlüssel 9“ | Man muss den Kontenrahmen kennen |
| I5 | Fachkürzel ohne Erklärung | „Confidence 62 %“, „KI-Vorschlag (LLM)“, „Steuerschlüssel 3“, „Zahlungsrichtung“, „Muster (Text, nur ganze Wörter)“ | Für den Inhaber schwer lesbar |
| I6 | Die Übersicht zeigt nur vier Zahlen | Offene Posten, Buchungen zur Prüfung, Belege zur Prüfung, Zahlungsläufe. Keine Links, keine Fristen, kein Bankstatus, keine Aufgaben | Nutzerbefund 2 |
| I7 | Die Navigation reicht nicht aus | Drei Punkte (Übersicht, Prüfen, Freigaben), kein `aria-current`. Belege, Bank, Steuern, Auswertungen und Einstellungen fehlen | Nutzerbefund 2 |
| I8 | Die Kopfleiste ist auf dem Handy überladen | Gesellschaft, Sprachauswahl mit eigenem Knopf „Übernehmen“, Benutzer und Abmelden belegen rund **165 px** (≈ 20 % der Höhe). Die Gesellschaft steht zusätzlich als „Gesellschaft: …“ im Inhalt | Platz für Inhalt fehlt |
| I9 | Im Dunkelmodus bleiben Felder und Knöpfe hell | Grund: `color-scheme` fehlt. Eingabefelder und Knöpfe bleiben weiß, das `<kbd>f</kbd>` im Knopf „Freigeben“ wird zum schwarzen Kasten | Unruhig; Text nicht lesbar |
| I10 | Das Einmalcode-Feld hat kein sichtbares Label | Auf `/freigaben` nur Platzhalter und `aria-label` | WCAG 3.3.2: Der Hinweis verschwindet beim Tippen |
| I11 | Die Label-Spalte ist zu schmal | „Verwendungszweck“ läuft in den Wert hinein (Spalte 9rem) | Unsauber |
| I12 | Die Hauptaktion ist optisch nicht hervorgehoben | „Freigeben“ sieht aus wie „Zurückstellen“ (Browserstandard) | Die nächste Aktion ist unklar |

Was 10b-1 bereits gut gelöst hat, bleibt: die Fachfunktionen (Prüfschlange, Lernschleife mit
Richtung, Storno statt Änderung), die Belegvorschau mit strengen Kopfzeilen, die htmx-Fehlerwege,
die Tastenkürzel, die Zweisprachigkeit, CSRF, Rechte-Matrix und Einmalcode.

### 1.3 Wo Einstellungen heute leben

| Ort | Inhalt | Schreibweg heute |
|-----|--------|------------------|
| YAML je Gesellschaft (`config/accounti.yaml` bzw. `gesellschaften.eintraege.<k>.konfiguration`) | 21 Abschnitte: `mandant`, `buchhaltung`, `datev`, `integrationen`, `llm`, `import`, `bank`, `ustid_pruefung`, `belegkanaele`, `elster`, `anlagen`, `abschluss`, `kasse`, `zahlung`, `mahnwesen`, `aufgaben`, `pruefung`, `versand`, `server`, `auth`, `gesellschaften` | Editor auf dem Server. Im Container ist `config/` schreibgeschützt (`./config:/arbeit/config:ro`, `read_only: true` in `docker-compose.yml`) |
| `regeln.yaml` je Gesellschaft | Kontierungsregeln | Editor; `accounti lerne` schreibt die Datei (10b verlegt das Lernen in die Datenbank) |
| Gesellschaftsdatenbank | Bankkonten (mit Einstellungs-JSON und verschlüsseltem `zugang`), Kreditkarten, Kanalzugänge (Tresor), Webhook-Token (Hash), ab 10b gelernte Regeln | CLI (`bank`, `fints`, `kreditkarte`, `kanaele`) |
| Systemdatenbank | Benutzer, Rollen je Gesellschaft, TOTP-Geheimnis (Tresor), Wiederherstellungscodes, Sitzungen, API-Token, Ereignisse | nur CLI (`benutzer`, `token`) |
| Umgebung | `ACCOUNTI_SCHLUESSEL` (Tresor), `ACCOUNTI_SICHERUNG_SCHLUESSEL`, `${VAR}`-Platzhalter in der YAML (IMAP, SMTP, LLM, FinTS-Produkt-ID, Datenbank-URLs) | Betreiber |
| Datei außerhalb von `config/` | ELSTER-Zertifikat und PIN-Datei (`elster pin`, Tresor) | CLI |

**Lader.** Es gibt 25 `lade_*`-Funktionen für Konfiguration. `yaml.safe_load` wird auf `main`
48b2d9e an 30 Stellen in 25 Dateien aufgerufen (mit 10b-1: 31 in 26), und jede Funktion liest die
Datei bei jedem Aufruf neu. Insgesamt sind es
rund 135 Aufrufstellen, allein `lade_buchhaltung` hat 24 und `lade_bank_einstellungen` 13. Die
Validierung läuft über pydantic-Modelle (`Firma`, `Buchhaltung`, `ElsterEinstellungen`,
`UstIdEinstellungen` …), die Fehlertexte nennen den Abschnittspfad. Die vollständige Zuordnung
steht in Anhang A.

**Nebenbefunde (unabhängig von 10c zu beheben):**

- **N1 — Kontenrahmen an der falschen Stelle.** Die Beispielkonfiguration setzt den Kontenrahmen
  unter `mandant.kontenrahmen` (`config/accounti.example.yaml:11`). Gelesen wird aber überall
  `buchhaltung.kontenrahmen` (`konfiguration.py:Buchhaltung`, Standard `SKR03`); nur der
  DATEV-Stammdatenexport liest beide (`export/datev_stammdaten.py:233`).
  Folge: Wer der Vorlage folgt und `SKR04` einträgt, bekommt überall außer im DATEV-Export SKR03.
- **N2 — Wirtschaftsjahr mit Jahreszahl.** `datev.wirtschaftsjahr_beginn` wird als Datum mit Jahr
  gepflegt (`"2026-01-01"`), gemeint ist nur Tag und Monat.
- **N3 — Konfiguration fehlt in der Sicherung.** Die Sicherung (10a) enthält Datenbank und
  Belegarchiv, aber nicht die YAML. Eine Wiederherstellung braucht die Konfiguration also getrennt.
- **N4 — Wenige Kontobezeichnungen.** Mitgeliefert sind nur 45 (SKR03) bzw. 26 (SKR04) Namen in
  `abschluss/kontenrahmen_skr0*.yaml` und 42 Konten in `pruefung/skr03.yaml`. „Bezeichnung statt
  Nummer“ (Abschnitt 6.3) braucht deutlich mehr (A36).
- **N5 — Steuernummer an zwei Stellen.** `mandant.steuernummer` (Rechnungen) und
  `elster.steuernummer` (ELSTER, Standard „sonst `mandant.steuernummer`“,
  `elster/konfiguration.py:96`). Ein Formular mit zwei Feldern lädt zu Abweichungen ein; 10c pflegt
  nur eine Steuernummer (A122).
- **N6 — Wirtschaftsjahr im DATEV-Abschnitt.** Der Beginn des Wirtschaftsjahres steht in
  `datev.wirtschaftsjahr_beginn` und wird auch von Auswertungen (10b-2) und Aufbewahrung gelesen.
  Er bleibt dort (kein Umzug in 10c), wird aber in der Oberfläche unter „Buchhaltung“ gepflegt
  (Anhang A).

---

## 2. Ziel

> Wer accounti öffnet, sieht zuerst, was heute zu tun ist, und erledigt das Häufigste mit einem
> Klick, auch auf dem Handy. Eine Korrektur heißt „anderes Konto wählen“, nicht „Kontonummer
> wissen“. Eine Regel ist ein Angebot danach, kein Pflichtfeld davor. Ein neues accounti wird im
> Browser eingerichtet. Alles, was heute in YAML-Dateien steht, lässt sich danach im Browser
> pflegen: nachvollziehbar, mit Verlauf und mit Rückweg zur Datei. Die Oberfläche ist ruhig, hell
> oder dunkel, und für alle bedienbar (WCAG 2.2 AA).

**Erfolgsmaße** (alle in Abschnitt 7 als Akzeptanzkriterien prüfbar):

| Maß | heute | Ziel | geprüft in |
|-----|-------|------|------------|
| Eingabefelder in der Arbeitsfläche, bevor man etwas tut | 9 | 0 | AK16 |
| Bedienschritte für eine Korrektur mit vorgeschlagenem Konto | ≥ 4, dazu die Kontonummer kennen | 3, ohne Nummer | AK17 |
| Lage von „Freigeben“ auf 390 × 844 | Oberkante 1117 px | ganz im ersten Bildschirm | AK15 |
| Waagrechtes Scrollen bei 320 und 390 px | `/pruefen` 741 px breit | auf keiner Seite | AK1 |
| Ersteinrichtung | nur CLI und YAML | vollständig im Browser, Pflichtteil höchstens 10 Pflichtfelder und unter 10 min | AK36, AK97 |
| Freigabe eines Zahlungslaufs oder einer USt-VA auf 390 × 844 | Zahlungsläufe als verschachtelte Tabelle (mit Läufen nicht gemessen); USt-VA nur per getipptem Zeitraum, die Werte erscheinen erst nach der Freigabe | Zusammenfassung, Codefeld und Knopf im ersten Bildschirm; Werte vor der Freigabe sichtbar | AK101 |
| Verstöße der Stufen A/AA laut axe-core | nicht gemessen | 0 | AK2 |

---

## 3. Nicht-Ziele

- **Kein SPA, kein Build-Schritt, kein JS-Framework.** Es bleibt bei Jinja2, htmx 2.0.11 und
  kleinen eigenen Skripten (Spec 10, Abschnitt 5).
- **Keine mobile App.** Ziel ist eine responsive Web-Oberfläche. Eine App bleibt Nicht-Ziel wie in
  Spec 10.
- **Keine wählbaren Themes oder Gestaltungsoptionen** (Spec 10, Abschnitt 8). Es gibt *ein*
  Design mit hell, dunkel und automatisch. Die Kennfarbe je Gesellschaft dient der
  Unterscheidung, nicht dem Schmuck.
- **Keine neue Fachlogik im Browser.** Jede neue Aktion entsteht als Fachfunktion mit CLI-Befehl
  (Abschnitt 4).
- **Keine Steuerberatung.** Vorschläge im Assistenten (Gewinnermittlung, Kontenrahmen,
  Voranmeldungszeitraum) sind als Vorschlag gekennzeichnet und verweisen auf den Steuerberater
  (Bauplan, Nicht-Ziele).
- **Kein Kontenrahmenwechsel und keine Umstellung des Wirtschaftsjahres.** Beide werden nach der
  ersten Buchung gesperrt. Eine Umstellung ist ein eigener Vorgang mit Saldenübertrag.
- **Kleinunternehmerregelung (§ 19 UStG) und Ist-Versteuerung (§ 20 UStG)** fragt der Assistent
  nur ab, um ehrlich zu sagen, dass accounti sie noch nicht trägt. Die Fachlogik dafür gibt es
  nicht.
- **Belegprüfung mit Feldkorrektur** (Lieferant, Datum und Betrag einer unsicher erkannten
  Rechnung bearbeiten) ist nicht Teil von 10c. 10c zeigt diese Belege nur an, siehe A11; die
  Feldkorrektur kommt als eigener Teil.
- **Auswertungen** (BWA, SuSa, Kontenblatt, OPOS) entstehen in 10b-2, dann bereits im neuen
  Design (Abschnitt 9).
- **Bankdialoge im Browser** (FinTS-Einrichtung, TAN-Freigabe, Abruf anstoßen) brauchen einen
  Hintergrundlauf. In 10c gibt es dafür Status und Anleitung, der Dialog selbst folgt später
  (E18).
- **Eine Gesellschaft im Browser anlegen** gehört nicht zu 10c (E8).
- **Kein Zugang und keine eigene Rolle für den Steuerberater** (F2). Mit eigenem Zugang arbeiten
  der Inhaber und Mitarbeitende. Der Steuerberater bekommt die Daten wie bisher über DATEV-Export
  und Verfahrensdokumentation; Schritt 6 des Assistenten erfasst nur Berater- und
  Mandantennummer.
- **Keine PDF-Seitenbilder auf dem Server** (F3). PDF-Belege öffnen auf dem Handy im
  Systembetrachter (E11 A); `pypdfium2` oder PDF.js kommen nicht dazu.
- **Hauptbereiche „Bank & Zahlungen“ und „Rechnungen & Kontakte“** (Umsatzliste, Zahlungsläufe
  anlegen, Rechnungen schreiben, Kontakte pflegen) entstehen nicht in 10c. 10c legt nur ihren Platz
  in der Navigation fest (A1, A2); ihre Einstellungen gehören dagegen zu 10c (A55).

### 3.1 Abgrenzung zu 10b-1 und 10b-2

| Thema | 10b-1 (`feat/web-oberflaeche`, fa6ceb9) | 10b-2 (Paket 4 des 10b-Plans) | 10c (diese Spec) |
|-------|------------------------------------------|-------------------------------|------------------|
| Fachkern Prüfschlange (`pruefschlange`, `lernen`, `kontierungsgruende`, `steuer_optionen`, Recht `REGELN_LERNEN`) | **liefert** | — | nutzt; ergänzt Gruppen, Mehrfachfreigabe, Kontovorschläge und -suche (A24–A28) |
| Seiten `/pruefen`, `/belege/{id}`, `/buchungen/{id}` | **liefert** (Vorlagen, `pruefen.js`, Tastenkürzel) | — | ersetzt Vorlagen und Stile (P1: neues Design; P3: neue Bedienung); Routen und Fachfunktionen bleiben |
| Zweisprachigkeit, htmx-Fehlerwege, CSP-Test, Rechte-Matrix | **liefert** | nutzt | nutzt und erweitert um jede neue Route (A114, A115, A119) |
| Sprachwahl `POST /einstellungen/sprache` | **liefert** | — | zieht nach „Mein Konto“ um (`/konto/vorlieben`, A87); der alte Pfad leitet weiter |
| Auswertungen (BWA, SuSa, Kontenblatt, OPOS, Exporte) unter `/auswertungen` | — | **liefert** Fachfunktion, CLI und Seiten | liefert nur Design und Komponenten (P1); die Übersichtskarten „Zahlungen“, „Forderungen“ und „Kennzahlen“ verlinken auf 10b-2 und erscheinen erst mit 10b-2 (A13, A16) |
| Übersicht, Navigation, Seitengerüst | Grundlayout aus 10a, vier Zahlen | — | **neu** (P1, P2) |
| Einstellungen, Einrichtung, Benutzerverwaltung im Browser | — | — | **neu** (P4–P7) |

Reihenfolge und Begründung: E19.

---

## 4. Leitlinien

1. **Eine Logik, zwei Wege.** Was der Browser kann, kann auch die CLI, und zwar über dieselbe
   Fachfunktion (Spec 10, Abschnitt 3). Das gilt auch für Übersicht, Einstellungen, Einrichtung,
   Massenfreigabe und Kontosuche.
2. **Progressive Verbesserung.** Jede Funktion geht ohne JavaScript (Formular, POST, Antwort 303).
   htmx tauscht nur Teile aus.
3. **Erst das Häufige.** Der Ausgangszustand jeder Seite zeigt die eine wahrscheinlichste Aktion.
   Selteneres liegt einen Schritt tiefer und ist nicht versteckt.
4. **Klare Sprache vor Fachkürzel.** Kontobezeichnung vor Nummer, „19 % Vorsteuer“ vor
   „Schlüssel 9“. Die Fachsprache bleibt in einer „Fachansicht“ erreichbar (Anhang B).
5. **Handy zuerst für vier Abläufe:** Übersicht lesen, Vorschläge prüfen und freigeben, Beleg
   hochladen und, für Freigabe-Berechtigte, Zahlungsläufe und USt-VA freigeben (F3).
   Einstellungen und Assistent müssen auf dem Handy funktionieren, sind aber für größere
   Bildschirme gestaltet.
6. **GoBD bleibt Maßstab.** Steuer- und buchungsrelevante Einstellungen haben einen Verlauf mit
   Person, Zeitpunkt und Grund. Die Verfahrensdokumentation kennt diesen Verlauf.
7. **Sicherheit bleibt streng.** CSP ohne Inline-Code, CSRF bei jedem POST, Einmalcode bei
   Freigaben. Geheimnisse stehen nie im Klartext in Datenbank, Seite, Log oder Export.

---

## 5. Entscheidungen

Jede Vorlage nennt die Varianten, die gewählte Variante und den Grund. Die Anforderungen in
Abschnitt 6 setzen sie um.

**Stand 26.10.2026:** Die Vorlagen, zu denen Abschnitt 12 eine Frage gestellt hat, sind
entschieden: E1 und E2 (F1), E6 Voreinstellung und E9 (F2), E11 (F3), E13 (F4), E20 und die
Reihenfolge (F5). Bei ihnen steht „**Entschieden**“. Zu den übrigen Vorlagen gab es keine Frage;
dort gilt die Empfehlung (Abschnitt 12, Einleitung).

### E1 — Wo leben Einstellungen?

| Variante | Kurz | Dafür | Dagegen |
|----------|------|-------|---------|
| A | Die Datei bleibt die Wahrheit, der Browser schreibt die YAML | eine Quelle, CLI unverändert | `config/` ist im Container schreibgeschützt; die Härtung müsste fallen. Kommentare gehen beim Zurückschreiben verloren (oder eine neue Abhängigkeit wie `ruamel.yaml`). Kein Verlauf, keine Person (GoBD). Gleichzeitiges Bearbeiten überschreibt. Nicht in der Sicherung |
| **B** | **Abschnitte in der Gesellschaftsdatenbank, nur anfügend versioniert; die Datei ist Startwert und kann festlegen** | läuft mit schreibgeschütztem `config/`. Verlauf mit Person, Grund und Journal. Automatisch in der Sicherung (behebt N3). Gesellschaften durch Bau getrennt wie in 10a. Gleichzeitigkeit über eine Versionsnummer | zwei Quellen, der Vorrang muss sichtbar sein; Lader-Umbau (E5); ein Export als Rückweg ist nötig |
| C | Feldweise Überlagerung der Datei aus der Datenbank | die Datei bleibt vollständig | Welche Quelle wirkt, ist je Feld anders. Listen (Mahnstufen, Postfächer, Zuständigkeitsregeln) lassen sich nicht sinnvoll mischen. Spätere Dateiänderungen wirken nur teilweise |
| D | Alles in die Datenbank, YAML abschaffen | eine Quelle | bricht den Datei- und CLI-Betrieb, Tests, Doku und Infrastruktur-als-Code. Betriebswerte wie die Datenbank-URL können nicht in der Datenbank stehen, die sie erst öffnen |
| E | Beschreibbare YAML im Datenvolumen | kein Datenbankschema | wie A ohne Verlauf; Doppelung mit `config/`; nicht in der Sicherung |

**Entschieden: B** (F1, 26.10.2026; so empfohlen). Nur B erfüllt zugleich: Betrieb im
gehärteten Container, nachvollziehbare Änderungen (GoBD), Trennung der Gesellschaften und
Sicherung samt Einstellungen. Die Datei behält zwei Rollen: Sie ist Startwert für neue
Installationen und den Assistenten, und sie kann Abschnitte für Betreiber festlegen, die
Konfiguration als Code führen (E2).

### E2 — Vorrang und Festlegung

Abschnittsweise statt feldweise (Begründung bei E1/C). Der wirksame Wert eines Abschnitts ergibt
sich in dieser Reihenfolge:

1. **Umgebung**, wo heute vorgesehen: `${VAR}`-Platzhalter und `ACCOUNTI_EVATR_URL`. Das gilt
   für einzelne Werte und ist unverändert.
2. **Festlegung in der Datei:** `einstellungen.quelle: datei` gilt für alle Abschnitte,
   `einstellungen.festgelegt: [elster, zahlung]` nur für die genannten. Die Oberfläche zeigt diese
   Abschnitte dann nur lesend.
3. **Neueste Version in der Datenbank.**
4. **Datei** als Startwert.
5. **Standardwerte** des pydantic-Modells.

**Betriebswerte** sind ausgenommen, sie kommen immer aus Datei oder Umgebung (A42). Ist ein
Abschnitt in der Datenbank gepflegt und weicht die Datei ab, zeigt die Seite das an und bietet
„Datei-Stand übernehmen“ (A43). Die **erste** Datenbank-Version eines Abschnitts ist immer der
vollständige wirksame Abschnitt (Datei bzw. Standard plus Änderung), nie nur die geänderten Felder;
so gibt es keine stille Mischung aus Datei und Datenbank. **Entschieden** wie beschrieben (F1,
26.10.2026). Ohne Datenbank-Version ändert sich für bestehende Installationen nichts (A53).

### E3 — Steuerwerte, die vom Zeitraum abhängen

Einige Werte gelten je Zeitraum, nicht „ab heute“: Voranmeldungszeitraum und
Dauerfristverlängerung je Kalenderjahr, OSS ab Quartalsbeginn, Gewinnermittlung je
Wirtschaftsjahr. Eine USt-VA für Dezember 2026, die im Januar 2027 nach dem Wechsel auf Quartal
erstellt wird, muss noch „Monat“ sehen.

| Variante | Kurz | Dagegen |
|----------|------|---------|
| A | Jede Version bekommt ein `gueltig_ab`, und alle Lader bekommen einen Stichtag | 25 Lader und rund 135 Aufrufstellen brauchen ein Datum, auch wo es keinen Sinn hat |
| **B** | **Periodenwerte im Abschnitt selbst**, nach dem vorhandenen Muster `sondervorauszahlung: {2026: 4000}`: `voranmeldungszeitraum: {2026: monat, 2027: quartal}`. Ein Einzelwert gilt immer (abwärtskompatibel). Der Lader liefert `wert_fuer(zeitraum)` | betrifft nur vier Werte |

**Empfehlung: B.** Der Versionsverlauf dient der Nachvollziehbarkeit, die Periodenwerte der
Fachlogik. Gesperrt wird nach Fachzustand (A46).

### E4 — Geheimnisse

Gemeint sind IMAP- und SMTP-Passwort, LLM-API-Schlüssel, FinTS-PIN und ELSTER-PIN.

| Variante | Kurz | Dagegen |
|----------|------|---------|
| A | nur `${VAR}` in der YAML (heute) | im Browser nicht setzbar |
| **B** | **Tresor-Tabelle `geheimnisse` in der Gesellschaftsdatenbank** (AES-GCM mit `ACCOUNTI_SCHLUESSEL`, Bezug = Gesellschaft + Name, wie `kanal_zugaenge`); `${VAR}` in der Datei hat Vorrang | keiner, solange der Schlüssel in der Umgebung liegt |
| C | im Klartext in `einstellungen` | verboten (Leitlinie 7) |

**Empfehlung: B.** Kanalzugänge und Bankzugänge bleiben, wo sie sind (schon im Tresor). Die
ELSTER-PIN darf in die Tabelle wandern. Die PIN-Datei bleibt erlaubt und hat Vorrang, wenn sie
konfiguriert ist.

### E5 — Umbau der Lader

| Variante | Kurz | Dafür | Dagegen |
|----------|------|-------|---------|
| A | Alle Lader nehmen ein `Einstellungen`-Objekt statt eines Pfads | ausdrücklich, typsicher | etwa 135 Aufrufstellen in fast allen Modulen; großer Eingriff parallel zu anderen Bausteinen |
| **B** | **Ein zentraler Abschnittsleser `einstellungen.lies_abschnitt(pfad, name)`** ersetzt alle `yaml.safe_load`-Stellen, die Abschnitte der Konfiguration lesen (von 30 auf `main`; Daten-Dateien wie Kontenrahmen und Regeln bleiben). Er fragt die Einstellungsquelle der aktiven Datenbank aus einer Kontextvariable; die CLI setzt sie im Callback, das Web je Anfrage | Signaturen bleiben gleich, ein Eingriff je Lader; das Muster gibt es schon (`aktueller_kontext`, `geprueft_als`) | implizit; braucht einen Test, der Umgehungen findet |

**Empfehlung: B**, mit Test: `yaml.safe_load` ist außerhalb einer Positivliste verboten (AST).
Ohne gesetzte Quelle (Unit-Tests, Werkzeuge ohne Datenbank) liest der Abschnittsleser nur die
Datei, wie heute. Die Datenbank-Einstellungen gelten für die Datenbank, mit der der Befehl
arbeitet (`--db` bzw. die Gesellschaft). So passen Einstellungen und Daten immer zusammen, auch
wenn `--config` auf eine andere Datei zeigt.

### E6 — Bestätigung von Änderungen

| Variante | Kurz | Dagegen |
|----------|------|---------|
| A | Einmalcode bei jeder Änderung | zu viel Reibung beim Einrichten |
| **B** | **Drei Stufen:** K1 ohne Code; K2 (steuer- und sicherheitsrelevant, Liste in Anhang A) mit Einmalcode, danach gilt ein **Verwaltungsmodus** 10 min für weitere K2-Änderungen dieser Sitzung; K3 (Lockerung einer Kontrolle bei aktivem Vier-Augen-Prinzip) wird ein **Änderungsantrag**, den eine zweite Person mit Freigaberecht und eigenem Code bestätigt | — |
| C | keine Bestätigung | Ein offener Browser reicht, um die Auftraggeber-IBAN zu ändern |

**Empfehlung: B.** Freigaben von Zahlungsläufen und Steuermeldungen behalten den frischen Code je
Freigabe (10a); der Verwaltungsmodus gilt nur für Einstellungen. Die Regel für K3 lautet: Wer eine
Kontrolle abschwächen will, braucht die Kontrolle. Beispiele sind `zahlung.vier_augen` aus,
`elster.vier_augen` aus, Höchstbetrag anheben, Freigeberliste erweitern oder
`auth.einmalcode_bestaetigung` (ist ohnehin nur in der Datei änderbar).

Festlegungen dazu:

- **K2 verlangt den Code immer**, auch wenn `auth.einmalcode_bestaetigung: false` gesetzt ist. Der
  Schalter aus 10a gilt für Freigaben; Bankverbindung und Auftraggeber sind das Ziel von
  Zahlungsbetrug und bleiben geschützt. Jeder Benutzer hat seit 10a einen zweiten Faktor, der Code
  ist also immer verfügbar.
- **Wann K3 greift und wer bestätigt:**
  - Felder von `zahlung` (Anhang A): solange `zahlung.vier_augen` an ist; bestätigt von einer
    zweiten Person mit `ZAHLUNG_FREIGEBEN`.
  - Steuer- und buchungsrelevante Lockerungen (`llm.auto_buchen_schwelle` senken,
    `pruefung.abgeschaltet` erweitern, `elster.vier_augen` aus): solange das Vier-Augen-Prinzip
    für Steuermeldungen an ist (`elster.vier_augen`, A125); bestätigt von einer zweiten Person
    mit `STEUER_FREIGEBEN`.
- **Voreinstellung Vier-Augen für Steuermeldungen (entschieden F2, 26.10.2026):**
  `elster.vier_augen` ist eine Einstellung wie `zahlung.vier_augen`, in der Datenbank gepflegt
  und im Browser schaltbar (Firma & Steuern › Steuern & Meldungen), Standard `false`. Bei
  Mitarbeitenden empfiehlt accounti sie, schaltet sie aber nie selbst ein; die Begründung steht in
  A125. Der erste Entwurf sah dafür ein Feld `einstellungen.steuer_vier_augen` nur in der Datei
  vor. Das entfällt, weil der Inhaber den Schalter nach F1 und F2 im Browser setzen können soll.
  Wer ihn als Betreiber fest vorgeben will, legt den Abschnitt `elster` in der Datei fest (E2).
- **Ein Antrag läuft nach 7 Tagen ab.** Gibt es keine zweite Person, bleibt der Weg über den
  Betreiber: Abschnitt in der Datei festlegen (E2). Das ist gewollt, weil sich eine Kontrolle
  sonst durch die kontrollierte Person aufheben ließe.

### E7 — Erster Start im Browser

| Variante | Kurz | Dagegen |
|----------|------|---------|
| A | nur CLI (`accounti benutzer anlegen`, heute) | widerspricht dem Wunsch |
| B | Assistent ohne Schutz, solange kein Benutzer existiert | Wer zuerst die Adresse aufruft, wird Verwalter (Wettlauf, typisch für Installer-Seiten) |
| **C** | **Assistent nur mit Einrichtungscode.** Den Code gibt `accounti serve` beim Start aus, solange die Systemdatenbank keinen Benutzer hat; abrufbar auch mit `accounti einrichtung code` | — |

**Empfehlung: C.** Das Muster ist von Jupyter bekannt. Wer den Code sieht, hat ohnehin Zugriff auf
Server oder Container-Log. Weitere Gründe: Der Server bindet ab Werk an `127.0.0.1`, und es gilt
eine Sperre nach Fehlversuchen (A72). Der Code öffnet nur das Anlegen des **ersten** Benutzers.
Gibt es schon einen Benutzer (etwa per CLI angelegt), wird kein Code ausgegeben, und der Weg ist
die Anmeldung; so kann der Code kein zweites Verwalterkonto neben einem bestehenden erzeugen.

### E8 — Eine Gesellschaft im Browser anlegen?

| Variante | Kurz | Dagegen |
|----------|------|---------|
| **A** | **Gesellschaften im Browser nur lesend** (Liste, Datenbank ohne Passwort, Archiv). Zum Anlegen zeigt die Seite einen fertigen YAML-Schnipsel und die Befehle. Neu ist `accounti gesellschaft anlegen K --name …`: legt das Schema an, prüft die Trennung und gibt den Schnipsel aus. Danach führt der Assistent durch die Einstellungen der neuen Gesellschaft | ein Schritt beim Betreiber |
| B | Der Browser legt an, nach einer Vorlage `gesellschaften.vorlage` (z. B. `postgresql://…/accounti_{kuerzel}`, Archiv `/daten/{kuerzel}`) | braucht das Recht `CREATEDB` für den Anwendungsbenutzer und eine Registry in der Systemdatenbank statt in der Datei; beides lockert die Trennung von Betrieb und Anwendung |

**Empfehlung: A** in 10c. B lässt sich später ergänzen, ohne A zu ändern; es bleibt daher ohne
eigene Frage.

### E9 — Weitere Benutzer anlegen

| Variante | Kurz | Dagegen |
|----------|------|---------|
| A | Der Verwalter setzt Passwort und zweiten Faktor (wie die CLI) | Der Verwalter kennt fremde Geheimnisse; die Freigabe ist nicht mehr an die Person gebunden |
| **B** | **Einladungslink:** einmalig, 72 h gültig, an Benutzername und Rollen gebunden. Passwort und zweiten Faktor setzt die Person selbst. Den Link kopiert der Verwalter, auf Wunsch geht er per E-Mail raus, wenn `versand` eingerichtet ist | — |

**Entschieden: B** (F2, 26.10.2026: Mitarbeitende arbeiten mit eigenem Zugang). Die CLI behält A
für den Betrieb ohne Browser. „Zugang zurücksetzen“ erzeugt ebenfalls eine Einladung. Die
Einladung trägt die Rollen der Person; Mitarbeitende bekommen nur die Rollen ihrer Aufgabe (A82).

### E10 — QR-Code für den zweiten Faktor

| Variante | Kurz | Lizenz / Stand | Bewertung |
|----------|------|----------------|-----------|
| **A** | **segno 1.6.6**: reines Python, keine Abhängigkeiten, SVG und PNG | BSD-3-Clause, Release 12.03.2025 (über 2 Wochen alt) | klein, gezielt, ohne Pillow |
| B | qrcode 8.2 | BSD, Release 01.05.2025; PNG nur mit Pillow oder pypng | größer, unnötige Varianten |
| C | eigener Encoder (Reed-Solomon, Masken, Versionen) | — | rund 500 Zeilen Fehlerquelle für eine Nebensache |
| D | kein QR, nur Schlüssel als Text und `otpauth://`-Link | — | umständlich am Rechner |

**Empfehlung: A**, eingetragen als `segno>=1.6.6,<2`. Ausgabe als SVG in einem `data:`-Bild; die
CSP erlaubt `img-src 'self' data:`, die Seite ist `no-store`. D bleibt zusätzlich bestehen:
Schlüssel in Vierergruppen und ein `otpauth://`-Link für die Einrichtung auf demselben Handy.
Eine Abhängigkeit ist also nötig, weil weder die Standardbibliothek noch Pillow QR-Codes erzeugen.

### E11 — Belegvorschau auf dem Handy

Mobile Browser zeigen PDFs in einem `<iframe>` schlecht an. iOS Safari zeigt nur die erste Seite
ohne Blättern; Android Chrome zeigt nichts oder bietet den Download an. Das ist Erfahrungswissen
und muss in der Browserprobe bestätigt werden.

| Variante | Kurz | Dagegen |
|----------|------|---------|
| **A** | Bilder und E-Rechnung inline (beides gibt es in 10b). Für PDF ein Knopf „PDF öffnen“, der den Systembetrachter öffnet, daneben die erkannten Eckdaten (Aussteller, Datum, Nummer, Brutto) | ein Wechsel aus der Seite |
| B | Seitenbilder serverseitig mit **pypdfium2 5.14.0** (Apache-2.0/BSD-3-Clause, Release 04.10.2026). Eigener Prozess mit Grenzen für Seiten, Pixel, Zeit und Speicher; Bilder `no-store` | neue Abhängigkeit (~5 MB, nativer PDF-Parser für fremde Dateien) |
| C | PDF.js im Browser | rund 1 MB JavaScript; die CSP bräuchte `worker-src`; widerspricht „kein schweres JS“ |

**Entschieden: A** in P3 (F3, 26.10.2026). Der Knopf „PDF öffnen“ genügt; B und C entfallen, es
kommt keine neue Abhängigkeit dazu (A117). Ob iOS und Android das PDF im Systembetrachter
öffnen, bestätigt die Browserprobe von P3 (AK70).

### E12 — Kontoauswahl bei der Korrektur

| Variante | Kurz | Dagegen |
|----------|------|---------|
| A | freie Kontonummer (heute) | Befund I4 |
| B | ARIA-Combobox mit eigenem Skript | Tastatur- und Screenreader-Verhalten ist schwer richtig zu bauen; ohne Skript wertlos |
| **C** | **Optionsliste:** bis zu 6 Vorschläge als Optionsfelder (Bezeichnung, Nummer, Grund des Vorschlags), darunter ein Suchfeld. Die Treffer kommen wieder als Optionsfelder: live mit htmx, ohne JS über einen Suchknopf | — |

**Empfehlung: C.** Optionsfelder sind ohne Zusatzaufwand barrierefrei, große Trefferflächen passen
zum Handy, und das Ganze funktioniert ohne Skript.

### E13 — Massenfreigabe

| Frage | Varianten | Entschieden (F4, 26.10.2026; so empfohlen) |
|-------|-----------|------------|
| Was passiert bei einem Fehler? | teilweise freigeben und Fehler überspringen, oder **alles oder nichts** | **Alles oder nichts** in einer Transaktion. Ändert sich bei einem Eintrag der Stand, wird keiner freigegeben, und die Liste wird neu geladen |
| Welche Vorschläge dürfen in Gruppen? | alle; ohne KI; **KI nur in Gruppen ab 3 mit gleichem Vorschlag** | Regelwerk, Kontakt, Beleg, OPOS, Marktplatz, Kreditkarte, Anlagen: ja. KI: ja, aber nur in Gruppen ab 3 mit gleichem Vorschlag und Sicherheit ≥ `llm.pruefung_schwelle` (also mindestens „mittel“, Anhang B). Herkunft `standard` (Ausweichkonto 4900): nie. Einträge mit Sperre oder Warnhinweis: nie |
| Wie groß darf eine Gruppe sein? | — | höchstens 100 je Vorgang, mit Bestätigungsschritt (Anzahl, Summe, Liste, Herkunft) |

### E14 — Navigation

| Variante | Kurz | Dagegen |
|----------|------|---------|
| A | Kopfleiste wie heute | Befunde I7 und I8 |
| **B** | **Seitenleiste ab 64rem, darunter eine untere Leiste mit höchstens 5 Zielen und eine Seite „Mehr“** (ein Link, kein Skript) | — |
| C | Hamburger-Menü mit Skript | versteckt die Bereiche; braucht Skript und Fokusfalle |

**Empfehlung: B.**

### E15 — Schrift und Symbole

**Empfehlung:** Systemschrift (`system-ui`-Stapel) mit `tabular-nums` für Beträge. Eine eigene
Webschrift (etwa Inter, OFL) brächte 100–300 KB ohne Nutzen für die Lesbarkeit. Die Symbole kommen
als **lokales SVG-Sprite** aus einer Teilmenge von Lucide (ISC-Lizenz, Lizenztext beigelegt,
etwa 25 Symbole) und stehen nie ohne Text bzw. ohne `aria-label`.

### E16 — Hell und dunkel

| Variante | Kurz | Dagegen |
|----------|------|---------|
| A | nur `prefers-color-scheme` (heute) | ohne `color-scheme` bleiben Felder hell (I9); keine eigene Wahl |
| **B** | **Wahl am Benutzer** (automatisch/hell/dunkel) in der Systemdatenbank wie die Sprache. Der Server setzt `data-theme` (`auto`, `hell` oder `dunkel`) an `<html>`; dazu `color-scheme: light dark` (auto), `light` (hell) bzw. `dark` (dunkel). Vor der Anmeldung gilt „auto“ | — |
| C | Wahl in `localStorage` mit Skript | Flackern beim Laden; wandert nicht mit auf andere Geräte |

**Empfehlung: B.**

### E17 — Sicherung im Browser

| Variante | Kurz | Dagegen |
|----------|------|---------|
| **A** | **Status anzeigen:** letzte Sicherung, Art, Gesellschaft, Größe, Prüfergebnis. Dafür kommt ein neues Sicherungsprotokoll in die Systemdatenbank, das `sicherung erstellen` und `sicherung pruefen` schreiben. Auslösen bleibt beim Betreiber (Cron/CLI) | — |
| B | Knopf „Jetzt sichern“ in ein konfiguriertes Ziel | Ziel und Schlüssel sind Betreibersache; das Container-Dateisystem ist schreibgeschützt; lange Laufzeit im Request |

**Empfehlung: A.** Die Übersicht warnt, wenn die letzte Sicherung älter als 7 Tage oder unbekannt
ist.

### E18 — Bankdialoge im Browser (FinTS-Einrichtung, TAN-Freigabe, Abruf)

| Variante | Kurz | Dagegen |
|----------|------|---------|
| **A** | Status, Einstellungen und Anleitung im Browser. Für den Dialog zeigt die Seite den passenden Befehl (`accounti fints einrichten …`, `accounti fints freigeben`) | ein Schritt in der Shell |
| B | Hintergrundlauf mit Statusabfrage (htmx alle 3 s) bis zur Freigabe in der Bank-App | braucht ein Job-Modell (Tabelle, Worker, Laufsperre, Abbruch); FinTS ist ohne Produkt-ID (10–15 Werktage) ohnehin nicht der erste Schritt |

**Empfehlung: A** in 10c, B als eigener Teil.

### E19 — Verhältnis zu 10b-1 und 10b-2

**Empfehlung:**

- **10b-1 wird fachlich unverändert zusammengeführt.** Es ist geprüft und liefert den Fachkern.
  10b-1 zweigt von ec32890 ab; vor dem Merge wird es auf `main` 48b2d9e (#30) gebracht, ohne
  inhaltliche Änderung.
- **10c baut darauf auf.** Die Vorlagen und Stile von 10b-1 werden in P1 (Design) und P3
  (Bedienung der Prüfschlange) ersetzt, die Fachfunktionen nur ergänzt.
- **10b-2 (Auswertungen) entsteht nach P1** im neuen Design. Paket 4 des 10b-Plans bleibt
  fachlich, wie es ist, nur Vorlagen und Stile kommen aus dem Design-System. Zusätzlich trägt
  10b-2 die Übersichtskarten „Zahlungen“, „Forderungen“ und „Kennzahlen“ ein und gibt der
  OPOS-Seite die Filter, die diese Karten verlinken (Art, fällig bis, überfällig) (A13, A16).

Die Alternative wäre, 10c-P1 und P3 in den offenen 10b-1-PR zu falten. Dagegen spricht: ein großer
PR mit geprüftem Fachkern und neuer Oberfläche gemischt; die Prüfung von 10b-1 müsste von vorn
beginnen.

### E20 — Paketschnitt

| Variante | Kurz | Dagegen |
|----------|------|---------|
| A | Ein großer PR „10c“ | nicht prüfbar; keine frühe Rückmeldung des Nutzers |
| B | Fünf Pakete wie im ersten Entwurf (Gerüst und Übersicht zusammen) | das erste Paket stellt alle Seiten um **und** baut die Übersicht samt Fachfunktion; zu groß für eine Prüfung (R8) |
| **C** | **Sieben Pakete P1–P7 in vier Wellen** (Abschnitt 9): Design-System und Gerüst ohne neue Fachlogik und der Einstellungs-Fachkern ohne Seiten zuerst und parallel, dann Übersicht, Prüfschlange und Einstellungsseiten, dann Benutzer, zuletzt der Assistent | mehr PRs; Abhängigkeiten müssen eingehalten werden; zwei parallele Pakete teilen sich die Migrationskette |

**Entschieden: C** (F5, 26.10.2026), mit der Reihenfolge aus Abschnitt 9: Welle 1 P1 und P4
parallel; Welle 2 P2, P3 und P5, dazu 10b-2 nach P1; Welle 3 P6; Welle 4 P7. Jedes Paket ist
für sich nutzbar und testbar. Der Nutzer sieht nach P1 das neue Design; der Lader-Umbau aus P4,
der fast alle Module berührt (R2), beginnt so früh wie möglich. Die Nummern P1–P7 bleiben
unverändert, auch wo die Reihenfolge von ihnen abweicht, damit die Verweise stabil bleiben.

---

## 6. Anforderungen

Nummern A1–A126. Die Nummern sind stabil: Später ergänzte Anforderungen tragen Nummern ab A120
und stehen im passenden Abschnitt (A125 und A126 kommen aus den Entscheidungen vom 26.10.2026).
In Klammern steht das Paket aus Abschnitt 9. Jede Anforderung hat mindestens ein testbares
Akzeptanzkriterium in Abschnitt 7; die Zuordnung steht in Anhang D.

### 6.1 Seitengerüst und Navigation

- **A1 (P1) Ziel-Gliederung.** Die Hauptbereiche sind:
  - Übersicht
  - Prüfen
  - Belege
  - Bank & Zahlungen
  - Rechnungen & Kontakte
  - Steuern
  - Auswertungen

  **Einstellungen** stehen davon abgesetzt, ebenso das Benutzermenü. „Freigaben“ (10a) bleibt
  eigener Punkt, bis „Bank & Zahlungen“ und „Steuern“ eigene Seiten für Zahlungsläufe und USt-VA
  haben. Danach liegen Zahlungsläufe und USt-VA dort und in der Übersicht.

  Stand nach 10c und 10b-2: Übersicht, Prüfen, Belege (P3), Steuern (Fristenliste, A120),
  Auswertungen (10b-2), Freigaben, Einstellungen. „Bank & Zahlungen“ und „Rechnungen & Kontakte“
  erscheinen erst mit eigenen Seiten (Nicht-Ziele).
- **A2 (P1) Registry.** `Navigationspunkt` aus 10a bekommt `bereich`, `symbol` und eine optionale
  Zählerfunktion (z. B. offene Prüfungen). Ein Bereich erscheint nur, wenn mindestens eine Seite
  dazu existiert und der Benutzer das Recht hat. Der aktive Bereich trägt
  `aria-current="page"`. „Freigaben“ braucht künftig `ZAHLUNG_FREIGEBEN` oder `STEUER_FREIGEBEN`
  (in 10a: `LESEN`); `/freigaben` selbst bleibt für `LESEN` erreichbar.
- **A3 (P1) Breite Bildschirme (≥ 64rem).** Links eine Seitenleiste (Symbol, Text, Zähler).
  Oben eine Kopfleiste mit der aktiven Gesellschaft (Kennfarbe, Kürzel, Name; Link zum Wechsel),
  „Hilfe“ und dem Benutzermenü. Inhaltsbreite höchstens 90rem, Fließtext höchstens 75ch.
- **A4 (P1) Schmale Bildschirme (< 64rem).**
  - Die Kopfleiste ist höchstens 56 px hoch: Kürzel und Kennfarbe der Gesellschaft, Seitentitel,
    Benutzersymbol.
  - Unten liegt eine feste Leiste mit höchstens fünf Zielen: Übersicht, Prüfen (Zähler), Belege
    und „Mehr“, dazu „Freigaben“ (Zähler) nur bei `ZAHLUNG_FREIGEBEN` oder `STEUER_FREIGEBEN`
    (F3: Freigaben unterwegs ja, A126). Ohne Freigaberecht hat die Leiste vier Ziele. Ziele ohne
    Seite entfallen nach A2 (vor P3 also „Belege“).
  - „Mehr“ ist eine eigene Seite `/menue` mit allen Bereichen, Gesellschaftswechsel, Mein Konto,
    Hilfe und Abmelden.
  - Auf der Arbeitsfläche der Prüfschlange und im Assistenten ersetzt eine Aktionsleiste die
    untere Leiste (A34, A76); der Rückweg steht dann oben („‹ Liste“ bzw. „Zurück“).
  - Die Leiste beachtet `env(safe-area-inset-bottom)` und verdeckt keinen Fokus (A104).
- **A5 (P1) Aktive Gesellschaft.** Kennfarbe und Kürzel sind auf jeder Seite sichtbar, der Name
  steht im `<title>` („Prüfen · Galerie GmbH · accounti“). Gewechselt wird über die Seite
  `/gesellschaft`: eine Liste mit Name, Kürzel, Kennfarbe und offenen Prüfungen und Freigaben je
  Gesellschaft, Wechsel per POST mit CSRF. Die Auswahlliste mit Knopf in der Kopfleiste entfällt,
  ebenso die doppelte Zeile „Gesellschaft: …“ im Inhalt. Der Akzeptanz-5-Test aus 10a wird auf
  die Kopfleiste umgestellt. Die Kennfarbe wählt der Verwalter aus 6 geprüften Farben
  (Einstellungen › Firma, Feld `mandant.kennfarbe` = 1–6); ohne Wahl wird sie stabil aus dem
  Kürzel abgeleitet. Sie wirkt über eine CSS-Klasse (`marke-1` … `marke-6`), nie über `style=`.
- **A6 (P1) Benutzermenü.** Es enthält Mein Konto, Sprache, Darstellung, Hilfe und Abmelden. Ab
  64rem ist es ein `<details>`-Aufklapper in der Kopfleiste; unter 64rem führt das Benutzersymbol
  auf `/menue#konto`. Sprache und Darstellung wirken über Optionsfelder mit einem Absendeknopf
  (POST, 303); mit htmx genügt die Auswahl.
- **A7 (P1) Seitentitel und Brotkrumen.** Jede Seite hat genau eine `h1`. Unterseiten tragen
  Brotkrumen (`nav aria-label="Brotkrumen"`), z. B. „Einstellungen › Bank & Zahlungen ›
  Bankkonten“.
- **A8 (P1) Hilfe.** Je Bereich gibt es eine lokale Hilfeseite unter `/hilfe/<bereich>`: Kurzanleitung, Begriffe
  aus Anhang B, Tastenkürzel. Der Link steht auf jeder Seite an derselben Stelle (WCAG 3.2.6).
  Keine externen Links nötig.
- **A9 (P1) Fehler- und Statusseiten.** 403, 404, 409 und 500 erscheinen im Design mit einem Weg
  zurück. 403 nennt wie in 10a die fehlende Rolle. 500 zeigt keine technischen Einzelheiten.
- **A121 (P1) Bestehende Seiten im neuen Design** (neu). Anmeldung, `/freigaben`, `/pruefen` (Liste,
  Arbeitsfläche, Regeln), `/belege/{id}` und `/buchungen/{id}` aus 10a/10b-1 bekommen Gerüst,
  Komponenten und Token, ohne fachliche Änderung. Dabei werden die Befunde I1 und I8–I12 behoben
  (waagrechtes Scrollen der Prüfliste über die Tabellen-Komponente aus A93, Kopfleiste,
  Dunkelmodus, sichtbares Label am Einmalcode, Label-Spalte, hervorgehobene Hauptaktion). Die neue Bedienung der Prüfschlange (I2–I5) folgt erst in P3. Alle Tests aus
  10a und 10b-1 bleiben grün; Tests, die auf Markup prüfen, werden auf Rollen und Texte
  umgestellt, nicht gelöscht.
- **A10 (P2) Aufgabenliste `/aufgaben`.** Filter: an mich, an meine Rolle, unzugewiesen, alle,
  überfällig. Jede Aufgabe verweist auf ihr Objekt (Buchung → `/pruefen/{id}`, Beleg →
  `/belege/{id}`, Lauf → `/freigaben`). Aktionen: „erledigt“, „mir zuweisen“, „kommentieren“, jeweils
  über die Fachfunktionen aus Baustein 8. Rechte wie in der CLI. Gleichlauf: dieselben Einträge
  wie `accounti aufgaben liste` mit dem entsprechenden Filter.
- **A11 (P3) Belege, Minimalumfang.**
  - `/belege/hochladen`: Datei oder Kamera (`accept="application/pdf,image/*,.xml"`,
    `capture="environment"` als Angebot). Aufnahme über die Pipeline mit Kanal `upload`;
    Multipart-Lesen wie beim Webhook, ohne `python-multipart`. Rückmeldung mit Status
    der Erkennung. Größengrenze wie beim Webhook; darüber 413 mit Meldung. Recht
    `BELEGE_EINLIEFERN`. Gleichlauf: `accounti belege import DATEI` mit demselben Ergebnis.
  - `/belege?status=pruefung`: Liste mit Vorschau und „erneut erkennen“ (`belege erkennen`).
    Gleichlauf: `accounti belege liste --status pruefung`. Feldkorrektur ist Nicht-Ziel.

### 6.2 Übersicht (Startseite)

- **A12 (P2) Aufbau.** Von oben nach unten:
  1. Begrüßung mit Datum
  2. „Heute zu tun“: alle Karten mit Einträgen, sortiert nach Dringlichkeit (A14); Fristen und Bank
     sind Karten wie die anderen
  3. „Erledigt“-Zeile mit den Karten ohne Einträge
  4. „In anderen Gesellschaften“ (A17)
  5. Kennzahlen (aufklappbar, Beträge verbergbar, A18)
- **A13 (P2) Karten.**

  | Karte | Inhalt | Quelle | sichtbar mit | Ziel |
  |-------|--------|--------|--------------|------|
  | Prüfen | Buchungen zur Prüfung (Anzahl, älteste seit n Tagen; ab P3 zusätzlich „davon in Gruppen sofort freigebbar“); Belege mit unsicherer Erkennung | `pruefschlange.lade_pruefschlange` (10b), neu `pruefschlange.gruppen` (A24); `lade_belege({ZUR_PRUEFUNG})` | `LESEN`; Knopf nur mit `BUCHEN` oder `BUCHUNG_FREIGEBEN` | `/pruefen`, `/belege?status=pruefung` |
  | Wartet auf Freigabe | Zahlungsläufe im Entwurf (Anzahl, Summe; „wartet auf eine zweite Person“, wenn Vier-Augen gilt und man selbst erstellt oder schon freigegeben hat); USt-VA bereit zur Freigabe (Zeitraum, Zahllast; „wartet auf eine zweite Person“, wenn `elster.vier_augen` gilt und man selbst schon freigegeben hat, A125); Dauerfrist-Antrag fällig | `lade_laeufe([ENTWURF])`, `elster` Freigaben/Protokoll | `ZAHLUNG_FREIGEBEN` bzw. `STEUER_FREIGEBEN` | `/freigaben` (A126) |
  | Fristen | die nächsten drei Fristen (USt-VA, Sondervorauszahlung, ZM, OSS) mit Stand (offen, vorbereitet, freigegeben, übermittelt) und Resttagen; überfällige zuerst, mit dem Wort „überfällig“ | `steuer.fristen.fristenkalender` mit den wirksamen `elster`-Werten (Periodenwerte E3), `faellige_fristen`, Übermittlungsprotokoll | `LESEN` | `/steuern/fristen` (A120); vorbereitete Meldung → `/freigaben` |
  | Zahlungen | fällige Verbindlichkeiten innerhalb `zahlung.vorlauf_tage`; auslaufendes Skonto mit Betrag | `zahlung.vorschlag` (nur lesen) | `LESEN` | OPOS-Liste der Verbindlichkeiten aus 10b-2 (`/auswertungen/opos?art=verbindlichkeiten&faellig_bis=…`); erscheint erst mit 10b-2 |
  | Forderungen | überfällige Forderungen (Anzahl, Summe); Mahnvorschläge | `opos.auswertung`, Mahnwesen-Vorschlag (nur lesen) | `LESEN` | `/auswertungen/opos` (10b-2); erscheint erst mit 10b-2 |
  | Aufgaben & Rückfragen | an mich, an meine Rolle, unzugewiesen, überfällig; neue Rückfragen an mich (die ersten drei mit Titel) | `lade_aufgaben` (8) | `LESEN` | `/aufgaben` (A10) |
  | Bank | je Konto: Bezeichnung, letzter Abruf, Abrufstand, Zustand, Meldung. Warnung bei Abruf älter als 3 Tage, Fehler oder ausstehender Freigabe | `lade_bankkonten` (`letzter_abruf`, `abrufstand`, `zustand`, `meldung`) | `LESEN` | Einstellungen › Bankkonten (Verwalter), sonst nur Anzeige |
  | Prüfhinweise | offene Aufgaben aus den Prüfregeln (Baustein 7) nach Art; Zeitpunkt des letzten Prüflaufs. Ab dem letzten Monat des Wirtschaftsjahres der Hinweis „Jahresabschluss vorbereiten“ | Aufgaben (8) aus `aufgaben lauf` | `LESEN` | `/aufgaben?art=…` |
  | Einrichtung & Betrieb | offene Einrichtungsschritte (A79); Sicherung älter als 7 Tage oder unbekannt (E17); `ACCOUNTI_SCHLUESSEL` fehlt; gesperrte Benutzer; abgelaufene Bankzugänge; Datei weicht von Datenbank-Einstellungen ab (A43). Jeder Punkt erscheint mit dem Paket, das seine Quelle liefert: P2 Schlüssel, gesperrte Benutzer, Bankzugänge; P4 Abweichung; P5 Sicherung; P7 Einrichtungsschritte | `einrichtung.stand`, Sicherungsprotokoll, `lade_alle_benutzer`, `lade_bankkonten` | `VERWALTEN` | Einstellungen (ab P5), bis dahin Befehlshinweis ohne Zahl |
  | Kennzahlen | Saldo der Bank-Sachkonten; Einnahmen und Ausgaben im laufenden Monat und im Vorjahresmonat; vorläufige USt-Zahllast des laufenden Voranmeldungszeitraums | Salden (12), USt-Kennziffern (9) | `LESEN` | `/auswertungen` (10b-2); erscheint erst mit 10b-2 |

- **A14 (P2) Dringlichkeit.** Zuerst kommen Karten mit überfälligen, dann mit heute fälligen, dann
  mit bald fälligen Einträgen (innerhalb von 7 Tagen), dann die übrigen. Innerhalb einer Stufe
  gilt die Reihenfolge der Tabelle in A13. Eine Karte mit Warnung (z. B. Bankabruf) trägt das
  Warnsymbol mit Text im Titel, rückt aber nicht vor. Karten ohne Einträge fallen in eine Zeile „Erledigt: Prüfen,
  Freigaben, Aufgaben“. Ist alles erledigt, steht da „Alles erledigt“ mit dem Zeitpunkt des
  letzten Bankabrufs.
- **A15 (P2) Rollen.** Es erscheinen nur Karten, für die der Benutzer das Recht hat, und Knöpfe nur
  mit dem Recht der Aktion. Ein `betrachter` sieht Zahlen und Fristen ohne Knöpfe.
- **A16 (P2) Keine toten Zahlen.** Jede Zahl (Anzahl oder Summe) ist ein Link auf eine Liste mit
  genau diesen Einträgen. Eine Karte erscheint nur, wenn ihre Zielseite in der Registry existiert
  und der Benutzer sie öffnen darf; bis 10b-2 fehlen daher „Zahlungen“, „Forderungen“ und
  „Kennzahlen“. Zeitangaben (letzter Abruf, Resttage) sind keine Zahlen in diesem Sinn.
- **A17 (P2) Weitere Gesellschaften.** Eine Zeile „In anderen Gesellschaften“ zeigt offene
  Prüfungen und Freigaben je weiterer Gesellschaft, in der der Benutzer eine Rolle hat, mit Link
  zum Wechsel.
- **A18 (P2) Beträge verbergen.** Am Benutzer einstellbar (Mein Konto und Schalter „Beträge
  verbergen“ auf der Übersicht, beides POST): Die Kennzahlen zeigen dann „•••“, etwa beim
  Bildschirmteilen. Der Server lässt die Beträge weg, statt sie nur per CSS zu verstecken. Es
  ist ein Schalter, kein Schutz.
- **A19 (P2) Leistung.** Die Übersicht rechnet beim Aufruf nichts Teures, also weder BWA noch
  Prüfregeln. Prüfbefunde kommen aus dem letzten geplanten Lauf. Serverzeit ≤ 300 ms (p95) bei
  50.000 Buchungen und 5.000 Belegen.
- **A20 (P2) Gleichlauf.** Fachfunktion `uebersicht.lade_uebersicht(s, rechte, heute,
  einstellungen) -> Uebersicht`, dazu CLI `accounti uebersicht [--json]` mit denselben Inhalten.
- **A21 (P2) Handy.** Dieselben Karten untereinander. Die Hauptaktion einer Karte geht über die
  volle Breite und ist mindestens 44 px hoch.
- **A120 (P2) Fristenliste `/steuern/fristen`** (neu). Erste Seite des Bereichs „Steuern“ und Ziel
  der Fristen-Karte: alle Fristen der nächsten 12 Monate und alle überfälligen, mit Art, Zeitraum,
  Datum, Resttagen und Stand (offen, vorbereitet, freigegeben, übermittelt; mit
  `elster.vier_augen` dazwischen „1 von 2 Freigaben“, A125); vorbereitete Meldungen verlinken
  auf `/freigaben`. Nur lesend, Recht `LESEN`. Gleichlauf: dieselben Einträge
  wie `accounti fristen` (Fachfunktionen `steuer.fristen.fristenkalender` und `faellige_fristen`
  mit den wirksamen Periodenwerten).
- **A126 (P2) Freigaben unterwegs** (neu, F3). Zahlungsläufe und USt-VA lassen sich auf dem Handy
  freigeben. Routen, Rechte und der frische Einmalcode je Freigabe bleiben wie in 10a. Neu ist nur
  der Abgleich des gesehenen Inhalts bei der USt-VA: `elster.freigabe.gib_frei` bekommt wie die
  Freigabe eines Zahlungslaufs einen Parameter `gesehen`.
  - **Karten:** `/freigaben` zeigt je offene Freigabe eine Karte (ab 40rem als Tabelle).
    Zahlungslauf: Nummer, Ausführung, Anzahl, Summe, angelegt von, Stand. USt-VA: Zeitraum,
    Zahllast (Kz 83), Frist mit Resttagen, Befunde der Plausibilitätsprüfung, Stand.
  - **Erst sehen, dann freigeben:** Die Zahlungen eines Laufs (Empfänger, IBAN, Betrag,
    Verwendungszweck) und die Kennziffern einer USt-VA stehen in einem `<details>` an der Karte.
    Freigegeben wird genau der angezeigte Inhalt: beim Lauf mit dem Freigabe-Hash aus 10a, bei der
    USt-VA mit dem Hash der angezeigten Werte (`elster.freigabe.inhalt_hash`). Weichen die Werte
    beim Absenden ab, antwortet der Server mit 409 und Meldung; es entsteht keine Freigabe.
  - **Zeitraum wählen statt tippen:** Die USt-VA-Karten kommen aus dem Fristenkalender (A120):
    fällige und vorbereitete Zeiträume. Ein anderer Zeitraum bleibt über „Anderer Zeitraum …“
    möglich.
  - **Handy:** Bei 390 × 844 liegen Zusammenfassung, Codefeld (A109) und [Freigeben] der ersten
    Karte im ersten Bildschirm; der Knopf ist mindestens 44 px hoch und geht über die volle
    Breite. Es gibt kein waagrechtes Scrollen, auch nicht in der Zahlungsliste.
  - **Stand:** „wartet auf eine zweite Person“ bei Vier-Augen (`zahlung.vier_augen`,
    `elster.vier_augen` aus A125), mit dem Namen der ersten freigebenden Person.
  - **Rechte:** Knöpfe nur mit `ZAHLUNG_FREIGEBEN` bzw. `STEUER_FREIGEBEN`; ohne Recht ist die
    Karte nur lesbar. In der unteren Leiste steht „Freigaben“ nur mit Freigaberecht (A4).
  - **Gleichlauf:** Die Werte der USt-VA-Karte gleichen `accounti ustva --json` für denselben
    Zeitraum; Freigabe im Browser und mit `accounti ustva freigeben` bzw.
    `accounti zahlung freigeben` ergeben denselben Eintrag.

### 6.3 Prüfschlange

- **A22 (P3) Liste.**
  - **Ab 40rem als Tabelle:** Datum; Empfänger bzw. Absender mit Text; Betrag mit Richtung;
    Vorschlag als Kontobezeichnung mit Nummer klein dahinter; Steuer im Klartext; Sicherheit als
    Wort („niedrig“, „mittel“) und Symbol; Aktionen [Freigeben] [Ändern].
  - **Darunter als Karten:** keine Tabelle, kein waagrechtes Scrollen.
  - **Reiter:** „Offen (n)“, „Später klären (n)“ und „Regeln“ (aus 10b).
- **A23 (P3) Ein-Klick-Freigabe.**
  - [Freigeben] steht in jeder Zeile und als Hauptknopf in der Arbeitsfläche.
  - Mit htmx wird die Zeile durch „freigegeben ✓ · Verlauf“ ersetzt, der Fokus springt auf die
    nächste Zeile. Ohne JS: POST, dann 303.
  - Gesendet wird der `stand` aus 10b; bei Abweichung 409 mit Meldung.
- **A24 (P3) Gruppen gleichartiger Vorschläge.**
  - **Gruppenschlüssel:** Kontakt (sonst normalisierte Gegenpartei), Richtung, vorgeschlagenes
    Gegenkonto, Steuerschlüssel, Herkunft (Quelle + Regel aus `kontierungsgruende`, 10b).
  - **Gruppenbildung:** ab 2 Einträgen; KI-Vorschläge erst ab 3 gleichen und nur mit Sicherheit
    ≥ `llm.pruefung_schwelle` (E13, entschieden F4).
  - **Anzeige oberhalb der Liste:** „6 × Deutsche Telekom → Telefon (4920), 19 % Vorsteuer ·
    239,94 € · Grund: Regel „Telekom““, mit [Ansehen] und [Alle freigeben].
  - **Fachfunktion:** `pruefschlange.gruppen(s, einstellungen) -> list[Gruppe]`.
- **A25 (P3) Massenfreigabe.**
  - [Alle freigeben] führt auf einen Bestätigungsschritt: Liste aus Datum, Gegenpartei und
    Betrag, dazu Anzahl und Summe, Knopf „6 Buchungen freigeben“. Der Kopf nennt Vorschlag und
    Herkunft; bei einer Gruppe aus KI-Vorschlägen steht dort „Vorschlag der KI · Sicherheit:
    mittel“ (F4).
  - Höchstens 100 Buchungen je Vorgang. Die Freigabe läuft in **einer** Transaktion, jeder
    `stand` wird geprüft (E13).
  - Jede Freigabe erhält einen eigenen Journaleintrag mit dem gemeinsamen Bezug
    `sammelfreigabe:<uuid>`.
  - Recht: `BUCHUNG_FREIGEBEN`.
  - Fachfunktion: `pruefschlange.freigeben_mehrere(s, [(id, stand)], person, bezug)`.
  - CLI: `accounti bestaetige --gruppe SCHLUESSEL` bzw. mehrere IDs; `accounti review --gruppen`.
- **A26 (P3) Eigene Auswahl.** Jede Zeile hat ein Kontrollkästchen. Bei Auswahl erscheint eine
  feste Sammelleiste am unteren Rand: „3 ausgewählt · 1.234,50 € · [Freigeben]“. Danach folgt
  derselbe Bestätigungsschritt wie A25. Ohne JS funktioniert das als Formular mit Absendeknopf
  unter der Liste.
- **A27 (P3) Arbeitsfläche im Ausgangszustand.**
  - **Kopf:** Gegenpartei; Betrag groß mit Richtung (Ausgabe/Einnahme); Datum; Bankkonto;
    Verwendungszweck.
  - **Vorschlag als Satz:** „→ **Telefon** (4920) · mit 19 % Vorsteuer“, dazu „Sicherheit:
    mittel“ und die Begründung in klarer Sprache, gekürzt mit „mehr“. Hinweise (Sperre,
    Betragsabweichung, Beleg fehlt) stehen als Hinweis-Komponente darüber.
  - **Genau drei Aktionen:** [Passt – freigeben] (primär), [Anderes Konto …] (sekundär), „Später
    klären …“ (Link-Stil).
  - **Kein Eingabefeld im Ausgangszustand.**
  - **„Buchungsdetails“** (Soll, Haben, Netto, Steuer, Brutto, Steuerschlüssel, Herkunft, Modell,
    Prozentwert) liegen in einem `<details>`. Mit der Benutzer-Einstellung „Fachansicht“ (A87)
    sind sie immer offen.
- **A28 (P3) Korrektur, Schritt 1 „Welches Konto passt?“.**
  - **Vorschläge:** bis zu 6 Optionsfelder mit Bezeichnung, Nummer und Grund. Mögliche Gründe:
    „bisher 8 × bei Deutsche Telekom“, „Sachkonto am Kontakt“, „zuletzt von Ihnen benutzt“,
    „passt zum Text“.
  - **Suchfeld:** findet nach Bezeichnung, Nummer und Stichwort. Bis zu 20 Treffer als
    Optionsfelder (htmx `input changed delay:250ms`; ohne JS über einen Suchknopf).
  - **Reihenfolge:** Konten passend zur Richtung zuerst (Aufwand und Wareneingang bei Ausgaben,
    Erlöse bei Einnahmen). Geldtransit-, Verrechnungs- und Privatkonten erscheinen immer.
  - **Gegenseite fest:** Die Gegenseite ist fest und wird nicht abgefragt: bei Bankumsätzen das
    Sachkonto des Bankkontos, bei Belegbuchungen das Personenkonto bzw. die Seite, die der
    Vorschlag nicht ändert (`lade_korrekturumgebung`, 10b). Gewählt wird nur das Konto, um das es
    geht. Soll und Haben stehen nur in der Fachansicht; dort bleiben beide änderbar wie in 10b.
  - **Unbekannte Nummern** sind nur über die Suche möglich, mit dem Hinweis „nicht im
    Kontenrahmen bekannt“ und einer Bestätigung.
  - **Neue Fachfunktionen:** `konten.vorschlaege(s, buchung, person, kontenrahmen)` und
    `konten.suche(kontenrahmen, text, richtung)`.
- **A29 (P3) Steuer nur, wenn nötig.**
  - Die Steuer wird aus dem Konto abgeleitet. Bei einem Automatikkonto steht sie nur als Text
    („19 % Umsatzsteuer, automatisch“).
  - Eine Auswahl erscheint nur, wenn `storno.steuer_optionen` (10b) mehr als eine Möglichkeit
    lässt oder Baustein 7 eine Wahl verlangt (Feld `steuer`).
  - Die Optionen stehen im Klartext: „19 % Vorsteuer“, „7 % Vorsteuer“, „ohne Vorsteuer“,
    „Reverse Charge (§ 13b UStG)“. Den Schlüssel zeigt nur die Fachansicht.
- **A30 (P3) Grund.** Der Grund ist optional; vorbelegt mit „Konto geändert: Bürobedarf (4930) →
  Telefon (4920)“. Pflicht ist er nur, wo Baustein 7 ihn verlangt (ohne Steuer; Storno nach
  Freigabe).
- **A31 (P3) Schritt 2 „Künftig immer so?“** (nach dem Speichern, optional).
  - **Wann:** nur mit `REGELN_LERNEN` und wenn eine Regel möglich ist (`regel_moeglich` bzw.
    `sachkonto_lernbar`, 10b).
  - **Wie:** als Satz, etwa „Wenn Absender **eBay** (Einnahmen) → **Verrechnung eBay** (1362)“,
    dazu die Vorschau: „trifft 14 frühere Umsätze, 12 davon schon so gebucht“.
  - **Knöpfe:** [Ja, Regel anlegen] und [Nein, nur dieses Mal]. „Bedingung anpassen“ (Muster,
    Feld) liegt in einem `<details>`.
  - **Kein Angebot**, wenn schon eine gleichwirkende Regel existiert.
  - **Nicht blockierend:** Das Angebot steht neben dem Weg zum nächsten Eintrag. Wer weitergeht
    (`j`, „Nächster“), hat „Nein“ gewählt; es wird nichts gespeichert. Die Korrektur selbst ist mit
    dem Speichern in Schritt 1 abgeschlossen (AK17 zählt bis dahin).
  - **Hervorhebung:** Hat dieselbe Person dieselbe Korrektur zum dritten Mal gemacht, steht da
    „Sie haben das jetzt 3 × so korrigiert“.
  - **Technik:** Korrektur und Regel sind zwei POSTs. Die Regel nutzt `lernen.lerne` (10b) mit
    dem Entwurf aus der Korrektur. Die Lernschleife aus Spec 10 Akzeptanz 2 bleibt erfüllt.
- **A32 (P3) Später klären.**
  - Die Rückfrage (Pflicht) richtet sich an „wen?“; zur Wahl stehen die Benutzer mit Rolle in der
    Gesellschaft und die Rollen, kein freies Textfeld mehr. Eine Frist ist optional.
  - Fachfunktion wie in 10b (`pruefschlange.zurueckstellen`).
- **A33 (P3) Belegvorschau.**
  - **Ab 64rem:** links neben dem Vorschlag, beim Scrollen mitlaufend (`position: sticky`).
  - **Darunter:** ein Umschalter „Vorschlag | Beleg“ (Reiter-Semantik; ohne JS über
    `?zeige=beleg`), Standard „Vorschlag“.
  - **Inhalt:** Bilder inline, mit Link auf die Originalgröße; E-Rechnung als HTML (10b). PDF
    nach E11 A (entschieden F3): auf jeder Breite ein Knopf „PDF öffnen“ (öffnet den
    Systembetrachter, mindestens 44 px hoch) mit den erkannten Eckdaten Aussteller, Datum,
    Nummer und Brutto daneben; ab 64rem zusätzlich der eingebettete Betrachter wie in 10b-1
    (Tablets im Querformat zeigen ihn unter Umständen nur teilweise, der Knopf bleibt der Weg).
- **A34 (P3) Ziel auf dem Handy.** Auf 390 × 844 sind Gegenpartei, Betrag, Vorschlag und [Passt –
  freigeben] ohne Scrollen sichtbar. Die drei Aktionen liegen in einer festen Aktionsleiste am
  unteren Rand (sie ersetzt dort die Navigationsleiste, A4), alle mindestens 44 × 44 px. Die
  Kopfdaten und der Vorschlagssatz enden oberhalb der Aktionsleiste; Begründung und
  Buchungsdetails dürfen darunter weiterlaufen.
- **A35 (P3) Tastatur.**
  - Die Kürzel aus 10b bleiben mit neuer Bedeutung, wo sich die Bedienung ändert: `j`/`k`
    (nächster/voriger), `f` (freigeben), `e` (anderes Konto; in 10b: Fokus ins Soll-Feld), `z`
    (später klären), `b` (Beleg), `?` (Hilfe). `r` war in 10b der Regel-Haken und gilt nur noch in
    Schritt 2.
  - In Schritt 1: `1`–`6` wählt einen Vorschlag, `/` springt in die Suche, `Strg+Enter`
    speichert.
  - In Schritt 2: `r` (Regel anlegen), `n` (nur dieses Mal).
  - In Eingabefeldern gelten nur `Strg+Enter` und `Esc`. Die Kürzel sind abschaltbar (10b).
- **A36 (P3) Kontobezeichnungen und Stichwörter.**
  - **Bezeichnungen:** Für SKR03 und SKR04 liegt je eine Liste der im Alltag kleiner Unternehmen
    gebrauchten Konten mit Bezeichnung bei, mindestens 300 je Rahmen (heute 45 bzw. 26, N4).
  - **Stichwörter:** dazu etwa 150 Stichwörter je Rahmen (z. B. „Handy“, „Mobilfunk“ →
    Telefon), als eigene Zusammenstellung mit Quellenangabe. Der vollständige DATEV-Kontenrahmen
    wird nicht kopiert (Risiko R5).
  - **Eigene Bezeichnungen** je Gesellschaft gehen vor (A67). Ein Test prüft, dass jedes Konto in
    mitgelieferten Regeln, Standardwerten und Marktplatz-Einstellungen eine Bezeichnung hat.
- **A37 (P3) Gleichlauf.**
  - Neue CLI-Befehle: `accounti konten suche TEXT [--richtung ausgabe|einnahme]`,
    `accounti konten vorschlag BUCHUNG`, `accounti review --gruppen`,
    `accounti bestaetige --gruppe`.
  - Bestehende Wege wie in 10b: Korrektur über `pruefschlange.korrigieren`, Regel über
    `lernen.lerne`.
- **A38 (P3) Rückmeldung, kein Rückgängig.**
  - Nach jeder Aktion erscheint eine Statuszeile mit Zusammenfassung und Link „Verlauf“ (Journal).
  - Ein „Rückgängig“ für Freigaben gibt es nicht. Eine Freigabe ist ein Journalvorgang, die
    Berichtigung läuft über Storno (Baustein 7).
- **A123 (P3) Antwortzeiten** (neu). Bei 50.000 Buchungen: Freigeben einer Zeile, Laden der
  Arbeitsfläche und Kontosuche je ≤ 300 ms Serverzeit (p95); die Gruppenbildung (A24) für 500
  offene Einträge ≤ 500 ms. Die Kontosuche läuft im Speicher über Kontenliste und Stichwörter,
  ohne Datenbankabfrage je Tastendruck.

### 6.4 Einstellungsarchitektur (Fachkern)

**GoBD-Bezug.** Einstellungen sind keine Buchungen, steuern aber, wie gebucht, gemeldet und
geprüft wird (Kontenrahmen, Steuerzeiträume, Schwellen der automatischen Kontierung,
Prüfregeln, Vier-Augen). Deshalb gelten für sie dieselben Grundsätze wie für Stammdaten:

| Grundsatz (GoBD, BMF 28.11.2019, geändert 11.03.2024 und 14.07.2025; die Randziffern unten sind durch die Änderungen nicht berührt) | Umsetzung |
|------|-----------|
| Änderungen nicht ohne Kenntlichmachung, ursprünglicher Inhalt feststellbar (Rz. 58, 107–108; § 146 Abs. 4 AO) | nur anfügende Versionen, Trigger gegen `UPDATE`/`DELETE`, Hash-Kette (A39) |
| Änderungen protokollieren; Mittel u. a. Historisierung (Rz. 59, 110) | Version mit Person, Zeitpunkt, Quelle und Grund; Journaleintrag (A39, A40) |
| Internes Kontrollsystem, Zugriffs- und Freigaberegeln (Rz. 100–102) | Recht `VERWALTEN`, Bestätigungsstufen K2/K3, Benachrichtigung (A58–A60) |
| Verfahrensdokumentation versioniert, Änderungshistorie nachvollziehbar (Rz. 151–155, insbesondere Rz. 154) | Verfahrensdoku zum Stichtag mit Änderungsanhang (A51) |
| Aufbewahrung der Organisationsunterlagen 10 Jahre (§ 147 Abs. 1 Nr. 1, Abs. 3 AO) | Versionen nie löschen, in Sicherung und Aufbewahrungsbericht (A52) |

Periodenwerte (E3) sorgen zusätzlich dafür, dass eine spätere Änderung nicht rückwirkend auf
abgeschlossene Zeiträume wirkt (A46). Die Quellen der Randziffern stehen im Plan zu Baustein 7
(`docs/plans/2026-10-26-belegvollstaendigkeit-gobd.md`).

- **A39 (P4) Tabelle `einstellungen`** in jeder Gesellschaftsdatenbank. Spalten:
  - `id`, `abschnitt`, `version` (je Abschnitt fortlaufend)
  - `daten` (JSON, ohne Geheimnisse), `schema_version`
  - `vollstaendig` und `fehlend` (Liste der fehlenden Felder)
  - `person`, `grund`, `quelle` ∈ `browser`/`cli`/`assistent`/`datei_uebernahme`/`antrag`
  - `erstellt_am`, `hash` und `vorgaenger_hash` (SHA-256 über die kanonische JSON-Form der Zeile;
    die Kette läuft je Abschnitt, `einstellungen pruefen` prüft sie)

  **Schutz:** Die Tabelle ist nur anfügend. Dafür sorgen ein ORM-Ereignis, ein SQLite-Trigger
  per `after_create` und in der Migration (wie `journal` aus Baustein 7) sowie der Eintrag in
  `db.GESCHUETZT`.

  **Änderungsanträge (K3)** liegen in `einstellungsantraege`: Abschnitt, vorgeschlagene Daten,
  Antragsteller, Status, Bestätiger. Die Version entsteht erst mit der Bestätigung.
- **A40 (P4) Journal.** Jede neue Version erzeugt einen Journaleintrag `einstellung_geaendert`
  mit `objekt_typ` `einstellung` und `objekt_id` = Abschnitt. `vorher`/`nachher` enthalten nur die
  geänderten Felder, ohne Geheimnisse, dazu `grund` und `person`.
- **A41 (P4) Wirksamer Wert** nach E2. Granularität ist der Abschnitt. Jeder Lader liefert
  denselben Modelltyp wie heute.
- **A42 (P4) Betriebswerte nur aus Datei oder Umgebung.** Dazu gehören:
  - die Abschnitte `database`, `server`, `auth`, `gesellschaften`
  - die Felder `elster.eric.*`, `elster.pin_datei`, `pruefung.archiv`,
    `belegkanaele.webhook.host|port`, `belegkanaele.email[].ca_datei`, Ordnerpfade,
    `ustid_pruefung.url`, `bank.fints.produkt_id`

  Die Felder liegen in einer Liste `BETRIEBSFELDER`. Auch bei einem in der Datenbank
  gepflegten Abschnitt kommen sie aus der Datei. Die Oberfläche zeigt sie lesend mit dem Hinweis
  „vom Betreiber in `<Datei>` festgelegt“.
- **A43 (P4/P5) Herkunft sichtbar.**
  - `einstellungen.herkunft(abschnitt)` liefert, woher der Wert stammt: Datenbank (Version n vom
    …, von …), Datei (Pfad), Standard oder festgelegt.
  - Haben Datei und Datenbank beide Werte und unterscheiden sie sich, gibt es einen Hinweis „Die
    Datei weicht ab – es gilt der Stand aus der Datenbank“ mit Gegenüberstellung.
  - Aktion „Datei-Stand übernehmen“ legt eine neue Version mit Pflicht-Grund an.
  - `accounti serve` und `accounti einstellungen pruefen` melden Abweichungen beim Start.
- **A44 (P4) Validierung.**
  - **Modelle:** Es gelten dieselben pydantic-Modelle wie in den Ladern. Fehlende Modelle für
    `import`, `llm` und `datev` werden ergänzt; `datev.wirtschaftsjahr_beginn` wird Tag und Monat
    (N2). Ein Datum mit Jahr wird weiter gelesen (Jahr ignoriert), damit bestehende Dateien
    gültig bleiben; geschrieben wird `MM-TT`.
  - **Querprüfungen über Abschnitte:**
    - Konten existieren im Kontenrahmen.
    - Das Sachkonto eines Bankkontos ist ein Bankkonto des Rahmens.
    - Skontokonten passen zum Kontenrahmen.
    - Die Auftraggeber-IBAN gehört zu einem eigenen Bankkonto.
  - **Unvollständige Abschnitte:** Was der Assistent als „später“ übersprungen hat, wird mit
    `vollstaendig=false` gespeichert. Streng geprüft wird wie heute dort, wo der Wert gebraucht
    wird (z. B. `lade_firma` beim Ausstellen einer Rechnung), mit einem Verweis auf die
    Einstellungsseite.
- **A45 (P4) Gleichzeitigkeit.** Jedes Formular trägt die Version jedes Abschnitts, dessen Felder
  es enthält (ein Formular kann Felder mehrerer Abschnitte zeigen, z. B. „Steuern & Meldungen“
  aus `mandant` und `elster`). Gespeichert wird je geändertem Abschnitt eine neue Version, alle in
  einer Transaktion. Weicht eine Version beim Speichern ab, antwortet der Server mit 409 und einer
  Gegenüberstellung („inzwischen von Erika geändert“). Gespeichert wird dann nichts.
- **A46 (P4) Periodenwerte und Sperren** (E3).
  - **Periodenwerte:** `elster.voranmeldungszeitraum`, `elster.dauerfristverlaengerung`,
    `mandant.oss` und `abschluss.gewinnermittlung` (je Wirtschaftsjahr), jeweils als Zuordnung
    „ab Zeitraum → Wert“.
  - **Gesperrt:**
    - ein Periodenwert für einen Zeitraum mit freigegebener oder übermittelter Meldung bzw. mit
      Jahresabschluss oder Jahressperre
    - `buchhaltung.kontenrahmen` und der Beginn des Wirtschaftsjahres nach der ersten Buchung
  - Die Sperrprüfung ist eine Fachfunktion und gilt in der CLI ebenso.
- **A47 (P4) Lader-Umbau** (E5).
  - Ein Abschnittsleser `einstellungen.lies_abschnitt(pfad, name)` ersetzt alle Stellen, die Konfigurationsabschnitte lesen. Er
    hat einen Zwischenspeicher je Datei (mtime) und je Datenbank (höchste Version).
  - Die Kontextvariable `einstellungsquelle` setzen der CLI-Callback (Datenbank aus `--db` bzw.
    der Gesellschaft) und die Web-Dependency `gesellschaft_db`.
  - Ein AST-Test verbietet `yaml.safe_load` außerhalb einer Positivliste (Abschnittsleser,
    Regel- und Kontenrahmendateien, Registry).
- **A48 (P4) Geheimnisse** (E4).
  - Neue Tabelle `geheimnisse` in der Gesellschaftsdatenbank: `name` (z. B.
    `versand.smtp.passwort`, `llm.api_key`, `elster.pin`), `chiffrat`, `gesetzt_am`,
    `gesetzt_von`. Die Bindung über den Tresor-Bezug lautet `<gesellschaft>:<name>`.
  - Die Oberfläche zeigt nur „gesetzt am … von …“, nie den Wert. „Ersetzen“ und „Entfernen“
    brauchen K2 (Einmalcode).
  - Fehlt `ACCOUNTI_SCHLUESSEL`, sind die Felder gesperrt, mit Hinweis für den Betreiber.
  - Ein `${VAR}` in der Datei geht vor; angezeigt wird dann „aus Umgebungsvariable `X` (gesetzt)“.
  - Das Journal vermerkt nur „Geheimnis `<name>` ersetzt“.
- **A49 (P4) CLI** (Verwalter mit Einmalcode wie 10a):

  ```bash
  accounti einstellungen zeigen [ABSCHNITT] [--herkunft] [--json]
  accounti einstellungen setzen ABSCHNITT.FELD WERT --grund "…"
  accounti einstellungen verlauf ABSCHNITT
  accounti einstellungen pruefen                  # Validierung, unvollständig, Datei ≠ Datenbank
  accounti einstellungen uebernehmen --aus-datei [ABSCHNITT] --grund "…"
  accounti einstellungen export [--ziel DATEI]    # Rückweg zur Datei (A50)
  accounti einstellungen geheimnis setzen NAME    # liest aus stdin, nie als Argument
  accounti einstellungen antraege [bestaetigen ID|ablehnen ID]
  accounti einstellungen setzen ABSCHNITT --datei TEIL.yaml --grund "…"   # ganzer Abschnitt
  ```

  `WERT` wird als YAML-Skalar gelesen und mit dem Modell geprüft; Listen und Zuordnungen gehen
  über `--datei`. Eine K3-Änderung erzeugt auch in der CLI einen Antrag statt einer Version. Ein
  festgelegter Abschnitt (E2) wird abgewiesen.
- **A50 (P4) Rückweg zur Datei.** `einstellungen export` erzeugt eine vollständige YAML der
  wirksamen Werte. Geheimnisse erscheinen als `${…}`-Platzhalter, dazu ein Kommentar je Abschnitt
  mit Herkunft und Version. Zusammen mit `einstellungen.quelle: datei` ergibt das dieselben
  wirksamen Werte (Rundlauf-Test).
- **A51 (P4) Verfahrensdokumentation.** `accounti verfahrensdoku` und der Download auf der
  Betriebsseite nehmen einen **Stichtag** und verwenden die dann gültigen Versionen. Neu ist ein
  Anhang „Änderungen der Einstellungen“: Datum, Abschnitt, Feld, alt → neu (ohne Geheimnisse),
  Person, Grund. Hintergrund: GoBD Rz. 154 verlangt eine versionierte Verfahrensdokumentation mit
  nachvollziehbarer Änderungshistorie; Änderungen und ihre Protokollierung nach Rz. 59 und 110
  (GoBD-Bezug am Anfang von 6.4).
- **A52 (P4) Aufbewahrung und Sicherung.**
  - `einstellungen`, `einstellungsantraege` und `geheimnisse` (nur als Chiffrat) laufen in
    Sicherung und Wiederherstellung (10a) mit.
  - Der Aufbewahrungsbericht führt Einstellungsversionen als Organisationsunterlagen (§ 147
    Abs. 1 Nr. 1, Abs. 3 AO: 10 Jahre). Sie werden nie gelöscht.
  - `docs/betrieb.md`: Geheimnisse lassen sich nur mit demselben `ACCOUNTI_SCHLUESSEL`
    wiederherstellen.
- **A53 (P4) Übergang für bestehende Installationen.**
  - Es gibt keine automatische Übernahme. Ohne Datenbank-Version gilt die Datei wie bisher; das
    Verhalten ist unverändert, bis jemand im Browser speichert.
  - Zu N1: Steht `kontenrahmen` nur unter `mandant`, warnen `einstellungen pruefen` und die
    Firma-Seite. Bei „Datei-Stand übernehmen“ wird der Wert in `buchhaltung` übernommen.
- **A54 (P4) Schnappschuss je Anfrage.** Innerhalb einer Web-Anfrage bzw. eines CLI-Befehls gilt
  ein Stand. Zwei Lader in derselben Anfrage sehen dieselbe Version.
- **A122 (P4) Eine Steuernummer** (neu, N5). Gepflegt wird `mandant.steuernummer`.
  `elster.steuernummer` bleibt lesbar und wirkt wie heute, erscheint in der Oberfläche aber nur,
  wenn es gesetzt ist und abweicht (Experten-Ansicht, mit Hinweis). `einstellungen pruefen` und
  die Seite warnen, wenn beide gesetzt sind und sich unterscheiden.
- **A124 (P4) Neue und geänderte Felder** (neu), jeweils abwärtskompatibel (eine bestehende Datei
  bleibt gültig und ergibt dieselben Werte):
  - `mandant.rechtsform` (Auswahlliste mit „sonstige“), `mandant.kennfarbe` (1–6)
  - Periodenwerte nach E3 für `elster.voranmeldungszeitraum`, `elster.dauerfristverlaengerung`,
    `mandant.oss`, `abschluss.gewinnermittlung`; ein Einzelwert gilt für alle Zeiträume
  - `datev.wirtschaftsjahr_beginn` als Tag und Monat (A44)
  - Datei-Abschnitt `einstellungen` mit `quelle` und `festgelegt` (E2)
  - `elster.vier_augen` (ja/nein, Standard `false`, A125)
  - Datenbank-Abschnitt `einrichtung` mit ausgeblendeten Checklistenpunkten (A79)
  - `config/accounti.example.yaml` und `docs/betrieb.md` beschreiben alle neuen Felder; N1 wird in
    der Vorlage berichtigt (`kontenrahmen` unter `buchhaltung`).
- **A125 (P4) Vier-Augen für Steuermeldungen** (neu, F2). Eine Einstellung wie
  `zahlung.vier_augen`, nur für Steuermeldungen (Meldearten aus Baustein 9: USt-VA und
  Dauerfristantrag).
  - **Feld:** `elster.vier_augen`, ja/nein, Standard `false`. Gepflegt in der Datenbank wie jeder
    Abschnitt (E1, E2), im Browser unter Firma & Steuern › Steuern & Meldungen (A55, ab P5), in der
    CLI mit `accounti einstellungen setzen elster.vier_augen true --grund …`.
  - **Wirkung bei `true`:**
    - Wo heute eine Freigabe nötig ist, braucht es zwei Freigaben derselben Werte (gleicher
      `inhalt_hash`) von zwei verschiedenen Personen mit `STEUER_FREIGEBEN`.
      `ustva uebermitteln` bzw. `ustva dauerfrist --uebermitteln` verweigern im Echtmodus mit nur
      einer Freigabe die Abgabe, mit der Meldung „eine zweite Person muss freigeben“.
    - Die erste Freigabe wird vermerkt („erste Freigabe – eine zweite Person muss freigeben“).
      Dieselbe Person kann nicht zweimal freigeben. Ändern sich die Werte danach, zählt die erste
      Freigabe nicht mehr (Hash wie heute).
    - Als Person zählt wie bei `zahlung.vier_augen` nur der angemeldete bzw. per Einmalcode
      bestätigte Benutzer, nie `--von`.
    - Der Schalter steuert zugleich K3 für steuerrelevante Lockerungen (E6).
  - **Ohne Schalter** bleibt alles wie vor 10c: eine Freigabe genügt.
  - **Bestätigung:** Einschalten ist K2. Ausschalten bei aktivem Schalter ist K3, bestätigt von
    einer zweiten Person mit `STEUER_FREIGEBEN` (E6).
  - **Kein Aussperren:** Mit eingerichteten Benutzern lässt sich der Schalter nur einschalten,
    wenn in der Gesellschaft mindestens zwei aktive Benutzer `STEUER_FREIGEBEN` haben. Sonst gibt
    es einen Feldfehler: „Vier-Augen braucht eine zweite Person mit dem Recht ‚Steuermeldungen
    freigeben‘ – zuerst einladen (Einstellungen › Benutzer & Rollen).“
  - **Voreinstellung aus.** Begründung:
    1. *Die Trennung der Rollen trägt die Kontrolle schon.* Mitarbeitende arbeiten als
       `buchhalter`: Sie buchen und bereiten vor, Steuermeldungen freigeben dürfen sie nicht. Das
       darf nur, wer `STEUER_FREIGEBEN` hat, im Betrieb des Nutzers in der Regel nur der Inhaber.
       Sobald Mitarbeitende buchen, sind an jeder Meldung so schon zwei Menschen beteiligt: wer
       bucht und wer freigibt. Dafür braucht es keinen Schalter.
    2. *Vier-Augen braucht zwei Freigabe-Berechtigte.* Hat nur der Inhaber das Recht, bliebe mit
       dem Schalter jede USt-VA und jeder Dauerfristantrag hängen.
    3. *Fristen sind hart.* Die USt-VA ist am 10. des Folgemonats fällig (mit
       Dauerfristverlängerung einen Monat später, § 18 Abs. 1 UStG, § 46 UStDV). Fehlt die
       zweite Person, droht ein Verspätungszuschlag (§ 152 AO). Weil das Ausschalten selbst K3
       ist, käme man dann ohne diese Person nur über den Betreiber wieder heraus (E2).
    4. *Keine Pflicht.* Die GoBD verlangen ein internes Kontrollsystem (Rz. 100–102), schreiben
       aber kein Vier-Augen-Prinzip für Steuermeldungen vor [V]. `zahlung.vier_augen` steht aus
       demselben Grund ab Werk auf `false` (Baustein 6).
  - **Empfehlen, nicht erzwingen:**
    - Schritt 7 des Assistenten und die Benutzerseite erklären den Schalter und seine
      Voraussetzung, sobald Mitarbeitende eingeladen werden (A73, A82).
    - Haben mindestens zwei aktive Benutzer `STEUER_FREIGEBEN` und ist der Schalter aus, führt die
      Einrichtungs-Checkliste den empfohlenen, ausblendbaren Punkt „Vier-Augen für
      Steuermeldungen einschalten?“ (A79).
    - accounti schaltet nie selbst ein.
  - **Sichtbarkeit:** Übersicht (A13), Fristenliste (A120, „1 von 2 Freigaben“) und
    `/freigaben` (A126) zeigen „wartet auf eine zweite Person“. Die Verfahrensdokumentation nennt
    den Schalter wie den für Zahlungsläufe („Steuermeldungen: Vier-Augen-Prinzip ja/nein“).
    Ändern des Schalters löst eine Benachrichtigung aus (A60).
  - **Technik:** Fachfunktion in `elster.freigabe` (`offene_freigabe` prüft zwei Personen); keine
    Migration, weil die Freigabetabelle schon mehrere Freigaben je Zeitraum aufnimmt. Gleichlauf
    über `accounti ustva freigeben` und `accounti ustva dauerfrist --freigeben` der zweiten Person.

### 6.5 Einstellungsseiten

- **A55 (P5) Gliederung** `/einstellungen` (Startseite mit Status je Bereich: vollständig,
  unvollständig, festgelegt):
  1. **Firma & Steuern**
     - Firmendaten: Name, Rechtsform (neu: `mandant.rechtsform`), Anschrift, E-Mail für
       Rechnungen (BT-34), Ansprechpartner, Kürzel und Nummernkreis, Rechnungsnummernformat,
       Zahlungsziel, Bankverbindung auf Rechnungen, Kennfarbe (neu: `mandant.kennfarbe`)
     - Steuern & Meldungen: Steuernummer (eine, A122), Bundesland, Finanzamt, USt-IdNr.,
       Voranmeldungszeitraum, Dauerfristverlängerung, Sondervorauszahlung, OSS, ZM-Zeitraum,
       Vier-Augen für Steuermeldungen (A125)
     - Buchhaltung: Kontenrahmen, Beginn des Wirtschaftsjahres (`datev`, N6), Gewinnermittlung,
       Personenkontenkreise, Standardkonten, Skontokonten, Kontenliste (A67)
     - Abschluss
     - Anlagen (Experten-Ansicht)
     - USt-IdNr.-Prüfung (Experten-Ansicht)
  2. **Bank & Zahlungen**
     - Bankkonten, Kreditkarten, FinTS (Status), Bankimport, Kasse
     - Zahlungsverkehr (Auftraggeber, Vorlauf, Skonto, Grenzen, Vier-Augen, Ersteller darf
       freigeben)
     - Mahnwesen
  3. **Benutzer & Rollen**
     - Benutzer, Einladungen, API-Token, Anmeldeprotokoll (6.7)
     - Aufgaben-Zuständigkeit & Benachrichtigung
  4. **Belege & Anbindungen**
     - Belegeingang (Hochladen, Ordner, E-Mail-Postfächer, Webhook, Connectoren)
     - Marktplätze & Zahlungsdienste (Amazon, eBay, PayPal, Shopify)
     - DATEV, ELSTER
     - KI-Kontierung, Kontierungsregeln, Prüfregeln
     - E-Mail-Versand
  5. **Gesellschaften** (E8 A)
  6. **Betrieb**, nur lesend mit Status: Version und Schemastand, Sicherung, Aufbewahrung,
     Verfahrensdokumentation (Download), Server und Anmeldung, Tresorschlüssel vorhanden
- **A56 (P5) Formularmuster.**
  - Das Label steht über dem Feld. Hilfetext mit Rechtsbezug, wo es hilft (z. B. „§ 18 Abs. 2
    UStG“). Pflicht ist im Text gekennzeichnet („Pflicht“), nicht nur mit einem Sternchen.
  - Fehler stehen am Feld und als Liste oben mit Links (A108).
  - Gespeichert wird **je Formulargruppe** (eine Überschrift mit eigenem Knopf), nicht je Seite;
    versioniert wird je Abschnitt der Datenhaltung (A45). Steuerrelevante Änderungen (K2) brauchen
    einen Grund. Jede Formulargruppe hat einen Link „Verlauf“ (A70).
  - Ungespeicherte Änderungen gehen beim Wechsel der Formulargruppe nicht still verloren: ohne
    JS speichert jede Gruppe für sich; mit JS warnt die Seite vor dem Verlassen (eigenes Skript,
    abschaltbar).
- **A57 (P5) Experten-Ansicht.**
  - Gilt für Abschnitte und Teile ohne eigenes Formular: `integrationen` (über die Marktplatz-Felder
    hinaus), `anlagen`, `aufgaben.zustaendigkeit`, `pruefung.regeln` und `pruefung.belegfrei`,
    `belegkanaele.connectoren`, `elster.kennziffern_konten`, `elster.steuerrelevante_konten`,
    `bwa`.
  - Ein YAML-Textfeld je Abschnitt zum Lesen und Schreiben, gelesen mit `yaml.safe_load` über die
    Parse-Funktion des Abschnittslesers (Positivliste, A47), geprüft mit demselben Modell.
  - Grenze 64 KB (`server.max_formular_kb`). Bei einem Syntaxfehler werden Zeile und Spalte
    genannt. Anker und Aliase (`&`, `*`) werden abgewiesen, weil sie beim Speichern als JSON
    vervielfacht würden.
- **A58 (P5) Rechte.** Die Einstellungsseiten unter `/einstellungen` brauchen `VERWALTEN`.
  „Mein Konto“ (`/konto`, A87) steht jedem offen; die Sprachwahl aus 10b-1
  (`POST /einstellungen/sprache`) zieht deshalb schon in P1 nach `/konto/vorlieben` um. Die
  Prüfung macht die Route, die Rechte-Matrix (10a) bekommt jeden neuen Endpunkt.
- **A59 (P5) Bestätigungsstufen** (E6).
  - K1: ohne Einmalcode.
  - K2: Einmalcode oder aktiver Verwaltungsmodus, 10 min je Sitzung; Spalte
    `auth_sitzungen.verwaltung_bis`. Unabhängig von `auth.einmalcode_bestaetigung` (E6). Der
    Verwaltungsmodus endet mit Abmeldung, Sitzungsende und jeder Rollenänderung.
  - K3: Änderungsantrag mit Bestätigung durch eine zweite Person mit `ZAHLUNG_FREIGEBEN` bzw.
    `STEUER_FREIGEBEN` und eigenem Code. K3 gilt nur, solange `zahlung.vier_augen` bzw. die neue
    Einstellung `elster.vier_augen` (A125) aktiv ist. Anträge laufen nach 7 Tagen ab;
    Antragsteller und Bestätiger müssen verschiedene Personen sein (E6).
  - Welches Feld zu welcher Stufe gehört, steht in Anhang A.
- **A60 (P5; Rollen-Teil P6) Benachrichtigung.** Änderungen an Bankverbindungen, Auftraggeber,
  Freigaberegeln (auch `zahlung.vier_augen` und `elster.vier_augen`) und Zahlungsgrenzen sowie
  neue API-Token melden alle Verwalter und Freigeber über den Kanal von Baustein 8, sofort und
  nicht erst in der Tagesübersicht. Schutz gegen Zahlungsbetrug. Ab P6 gilt dasselbe, wenn eine
  Person eine Rolle mit Freigabe- oder Verwaltungsrecht (`freigeber`, `verwalter`) bekommt, per
  Einladung oder Rollenänderung (F2: Mitarbeitende mit eigenem Zugang).
- **A61 (P5) Bankkonten und Kreditkarten.**
  - **Liste:** Bezeichnung, IBAN, Sachkonto mit Bezeichnung, Abrufweg, letzter Abruf, Zustand,
    Meldung.
  - **Anlegen:** IBAN mit Prüfziffer (`iban_gueltig`), Sachkonto mit Vorschlag aus dem
    Kontenrahmen, Abrufweg (Datei-Import oder Provider bzw. FinTS). FinTS selbst nach E18 A:
    Status und Befehl.
  - **Deaktivieren** statt löschen, sobald Umsätze vorhanden sind.
  - **Kreditkarten:** wie in der CLI `kreditkarte einrichten`.
  - Alle Aktionen über dieselben Fachfunktionen wie `bank konten`/`kreditkarte`.
- **A62 (P5) Zahlungsverkehr und Mahnwesen.**
  - **Mahnstufen:** Editor mit Name, „ab Tagen“, Gebühr, Verzugszinsen und Text. Hinzufügen,
    Entfernen und Sortieren laufen über Knöpfe (Hoch/Runter), nicht per Ziehen (WCAG 2.5.7).
  - **Vorschau** des Mahnschreibens für einen Beispielposten.
  - **Hinweis** zu Gebühren: „Konfiguration, keine Rechtsberatung“.
- **A63 (P5) Belegeingang.**
  - **E-Mail-Postfach:** Host, Port, Verschlüsselung, Benutzer, Ordner, „nach dem Abholen“; das
    Passwort über `kanaele zugang` (Tresor).
  - **„Verbindung testen“:** IMAP-Anmeldung und Ordnerliste, Zeitlimit 15 s, es wird nichts
    abgeholt.
  - **Webhook-Token:** anlegen (Klartext genau einmal), widerrufen.
  - **Ordner** und **Webhook-Adresse** nur lesend (A42).
- **A64 (P5) Marktplätze, DATEV, ELSTER.**
  - **Marktplätze:** je Marktplatz aktivieren, Verrechnungskonto (Vorschlag), USt der Gebühren,
    Bank-Stichworte; dazu der aktuelle Stand der EU-Fernverkäufe des Jahres als Hilfe für OSS.
  - **DATEV:** Berater- und Mandantennummer, Sachkontenlänge.
  - **ELSTER:** Übermittler bzw. Testmodus, Hersteller-ID, PIN als Geheimnis. Zertifikat- und
    ERiC-Pfade nur lesend.
- **A65 (P5) KI-Kontierung und Prüfregeln.**
  - **KI:** Anbieter, Modell, `auto_buchen_schwelle` und `pruefung_schwelle` mit Klartext („Ab
    95 % bucht accounti ohne Prüfung“), API-Schlüssel als Geheimnis. Die Schwellen gehören zu K2;
    eine niedrigere Auto-Schwelle bei aktivem Vier-Augen-Prinzip für Steuermeldungen
    (`elster.vier_augen`, A125) zu K3.
  - **Prüfregeln (Baustein 7):** Liste aller Regeln mit Schwere und Schwellen. Abschalten gehört
    zu K2. Belegfrei-Regeln in der Experten-Ansicht.
- **A66 (P5) Kontierungsregeln.** `regeln.yaml` wird nur lesend als Liste gezeigt, mit
  Trefferzahl der letzten 12 Monate. Gelernte Regeln wie in 10b. Neu ist „Regel anlegen“ ohne
  vorherige Korrektur: Bedingung (Feld, Text), Richtung, Konto (Kontosuche A28), Steuer, Vorschau.
  Gespeichert wird als gelernte Regel mit Quelle `formular`, als Fachfunktion in `lernen`.
- **A67 (P5) Kontenliste.** Eigene Bezeichnungen und Stichwörter je Gesellschaft, etwa „1361
  Verrechnung Amazon“ oder eigene Unterkonten. Gespeichert im Abschnitt `buchhaltung.konten` und
  verwendet von der Kontosuche (A28) und überall, wo Konten angezeigt werden.
- **A68 (P5) Gesellschaften** (E8 A). Liste mit Datenbank ohne Passwort (`ohne_passwort` aus
  10a), Archiv und Konfigurationsdatei. Anleitung „Gesellschaft hinzufügen“ mit einem Schnipsel,
  vorausgefüllt nach Kürzel und Name. CLI `accounti gesellschaft anlegen`. Für eine neue
  Gesellschaft ohne Einstellungen gibt es den Assistenten ab Schritt 2 (A71).
- **A69 (P5) Betrieb** (E17 A).
  - Sicherungsprotokoll in der Systemdatenbank: `zeit`, `art`, `gesellschaft`, `groesse`,
    `ergebnis`, `pruefung`; kein Zielpfad, keine Schlüssel. `sicherung erstellen` und
    `sicherung pruefen` schreiben es.
  - Anzeige der letzten Sicherung und Prüfung je Gesellschaft, mit Warnung ab 7 Tagen.
  - Server- und Anmeldewerte nur lesend.
- **A70 (P5) Verlauf je Abschnitt.** Versionen mit Datum, Person, Quelle, Grund und den
  geänderten Feldern (alt → neu). Ein Vergleich zweier Versionen ist möglich. Zurücksetzen auf
  eine frühere Version ist eine neue Version mit Grund und Bestätigungsstufe des Abschnitts.

### 6.6 Einrichtungsassistent

- **A71 (P7) Auslöser.**
  1. Die Systemdatenbank hat keinen Benutzer: Jede Seite leitet auf `/einrichtung`.
  2. Die Einrichtung eines angemeldeten Verwalters ist unvollständig: Die Übersicht zeigt
     „Einrichtung fortsetzen“.
  3. Eine Gesellschaft hat weder Datei- noch Datenbankwerte für `mandant`: Assistent ab Schritt 2
     für diese Gesellschaft.
- **A72 (P7) Einrichtungscode** (E7).
  - **Bildung und Speicherung:** 128 Bit, Base32 in Fünfergruppen. Gespeichert wird nur der Hash
    in der Systemdatenbank.
  - **Ausgabe:** `accounti serve` gibt den Code auf stderr aus, solange die Systemdatenbank keinen
    Benutzer hat. `accounti einrichtung code` erzeugt einen neuen; der alte wird damit ungültig.
    Gibt es einen Benutzer, verweigern beide die Ausgabe mit Hinweis auf die Anmeldung.
  - **Gültigkeit:** bis der erste Benutzer angelegt ist. Das Anlegen geschieht erst mit dem
    bestätigten zweiten Faktor, in einer Transaktion (Benutzer, Rollen, TOTP, Codes); bricht
    jemand vorher ab, entsteht kein Benutzer, und der Code gilt weiter.
  - **Zwischenstand** in `auth_einrichtung` (Systemdatenbank): Hash des Codes, Fehlversuche, das
    noch unbestätigte TOTP-Geheimnis (im Tresor, gebunden an eine Einrichtungssitzung, 30 min
    gültig).
  - **Sperre:** 5 Fehlversuche in 15 min. Das Zugriffsprotokoll enthält den Code nie.
- **A73 (P7) Schritte.**

  | Nr. | Schritt | Pflicht? | Inhalt | gespeichert als |
  |-----|---------|----------|--------|-----------------|
  | 0 | Willkommen | Pflicht | Sprache; Einrichtungscode | — |
  | 1 | Ihr Zugang | Pflicht | Benutzername, Anzeigename, Passwort (12–128 Zeichen, Sperrliste, Regeln aus 10a); zweiter Faktor (A77); Wiederherstellungscodes; Hinweis zu den Rollen (alle Rollen, A78) | Benutzer und Rollen (Systemdatenbank), angelegt erst mit bestätigtem Faktor (A72) |
  | 2 | Ihre Firma | Name und Rechtsform Pflicht; Rest „später“ | Name, Rechtsform, Anschrift, E-Mail für Rechnungen, Ansprechpartner | Abschnitt `mandant` |
  | 3 | Steuern & Buchführung | Gewinnermittlung, Kontenrahmen und Wirtschaftsjahr Pflicht; Rest „später“ | Gewinnermittlung, Kontenrahmen, Wirtschaftsjahr, Bundesland und Finanzamt, Steuernummer, USt-IdNr., Voranmeldungszeitraum, Dauerfristverlängerung, OSS; Frage nach Kleinunternehmer und Ist-Versteuerung (Nicht-Ziel: nur Hinweis) | `buchhaltung`, `abschluss`, `elster`, `mandant`, `datev` (nur `wirtschaftsjahr_beginn`, N6) |
  | 4 | Bankkonto | empfohlen, überspringbar | IBAN, Bezeichnung, Sachkonto (Vorschlag), Abrufweg; FinTS nach E18 A. Angehakt vorbelegt: „Diese Verbindung auf Rechnungen nennen“ und „als Auftraggeber für Zahlungsläufe verwenden“ (keine zweite Eingabe, WCAG 3.3.7) | Bankkonto (Datenbank); `mandant` (Bankverbindung), `zahlung.auftraggeber` (Name aus Schritt 2, IBAN) |
  | 5 | Belegeingang | überspringbar | Hochladen (immer an); E-Mail-Postfach mit Test; Webhook-Token | `belegkanaele`, Kanalzugang |
  | 6 | Steuerberater & DATEV | überspringbar | Berater- und Mandantennummer; kein Zugang für den Steuerberater (F2, Nicht-Ziele) | `datev` |
  | 7 | Weitere Personen | empfohlen, überspringbar | Einladungen für Mitarbeitende mit eigenen Rollen (A82); Hinweis zum Vier-Augen-Prinzip und seiner Voraussetzung (A125) | Einladungen |
  | 8 | Fertig – was jetzt? | — | Zusammenfassung; „später“-Punkte als Checkliste; nächste Schritte: Kontoauszug importieren, Beleg hochladen, Prüfen ansehen, Verfahrensdokumentation erzeugen, Sicherung beim Betreiber einrichten | — |

  Pflichtumfang: Die Schritte 0–3 haben zusammen höchstens 10 Pflichtfelder (Code, Benutzername,
  Passwort, Faktor-Code, Haken „Codes abgelegt“, Name, Rechtsform, Gewinnermittlung, Kontenrahmen,
  Wirtschaftsjahr; Gewinnermittlung entfällt, wo die Rechtsform sie festlegt). Die frühere Frage
  „Arbeiten Sie allein?“ entfällt mit F2 (A78). Alles andere hat „später“.

- **A74 (P7) Vorschläge.** Jeder steht als „Vorschlag“ in einer Hinweis-Komponente: „Bitte mit
  Ihrem Steuerberater abstimmen – accounti berät nicht.“

  | Frage | Vorschlag | Grundlage (Stand vor Umsetzung prüfen) |
  |-------|-----------|----------------------------------------|
  | Gewinnermittlung | **Bilanz** ohne Wahl bei GmbH, UG, AG, eG, OHG, KG, GmbH & Co. KG (Kaufleute kraft Rechtsform bzw. Handelsgesellschaften). **Wahl mit Hinweis** bei e. K. (Befreiung nach § 241a HGB bis 800.000 € Umsatz und 80.000 € Jahresüberschuss), Einzelunternehmen und gewerblicher GbR (§ 141 AO: Bilanz erst über 800.000 € Umsatz oder 80.000 € Gewinn und nach Aufforderung). **EÜR** bei Freiberuflern und freiberuflicher GbR | §§ 238, 241a HGB, § 140 und § 141 AO; Grenzen nach dem Wachstumschancengesetz für Wirtschaftsjahre nach dem 31.12.2023 |
  | Kontenrahmen | Hat der Steuerberater einen Rahmen festgelegt: diesen. Sonst SKR03 (am weitesten verbreitet); SKR04 als Alternative, besonders bei Bilanz (aufgebaut wie die Bilanz nach § 266 HGB) | Hinweis „Steuerberater fragen“; nach der ersten Buchung gesperrt |
  | Wirtschaftsjahr | Kalenderjahr. „Abweichend“ nur bei Gewerbetreibenden im Handelsregister, mit Hinweis auf die Zustimmung des Finanzamts zur Umstellung | § 4a Abs. 1 EStG |
  | Voranmeldungszeitraum | Monat, wenn die USt des Vorjahres über 9.000 € lag; Quartal bis 9.000 €; Hinweis auf mögliche Befreiung bis 2.000 €. Bei Gründung: 2021–2026 nach voraussichtlicher Steuer, ab 2027 Monat im Gründungs- und Folgejahr. Der Bescheid des Finanzamts geht vor | § 18 Abs. 2 Satz 1–6 UStG (am 26.10.2026 gelesen) |
  | Dauerfristverlängerung | Hinweis: verlängert jede Abgabefrist um einen Monat. Antrag bis zum 10.02. (Monatszahler, mit Sondervorauszahlung von 1/11 der Vorauszahlungen des Vorjahres) bzw. bis zum 10.04. (Quartalszahler, ohne Sondervorauszahlung); einmal gewährt gilt sie fort, bis sie widerrufen wird | §§ 46–48 UStDV |
  | OSS | Hinweis bei Fernverkäufen an Privatkunden in der EU über 10.000 € im Jahr; Registrierung beim BZSt vor Beginn des Quartals. Gibt es Marktplatzdaten, wird der Jahresstand angezeigt | § 3c Abs. 4, § 18j UStG |
  | Bank-Sachkonto | erstes Bankkonto SKR03 1200 / SKR04 1800, weitere 1210 ff. / 1810 ff. | Kontenrahmen (`bankkonten` in `abschluss/kontenrahmen_*.yaml`) |

- **A75 (P7) Validierung.**
  - **Offline, sofort** (Feldfehler mit Erklärung):
    - IBAN: Prüfziffer.
    - USt-IdNr.: Länderformat, deutsche Nummer mit Prüfziffer nach BZSt-Verfahren (Fachfunktion
      neu in `kontakte/ustid.py`).
    - Steuernummer: Format je Bundesland über `elster.steuernummer.elster_steuernummer`; die
      13-stellige ELSTER-Form wird zur Kontrolle angezeigt.
    - PLZ (DE 5 Ziffern), E-Mail-Syntax, Konten im Kontenrahmen.
  - **Online nur auf ausdrücklichen Klick** („jetzt online prüfen“), nie automatisch:
    - eVatR (§ 18e UStG) bestätigt nur Nummern anderer Mitgliedstaaten. Die eigene deutsche
      Nummer prüft es nur mittelbar, als Nummer des Anfragenden; den Fehlercode in der
      Schnittstellenbeschreibung prüfen.
    - Deshalb bietet der Assistent die Online-Prüfung nur an, wenn schon ein EU-Kontakt mit
      USt-IdNr. existiert. Sonst steht da „wird bei der ersten Abfrage mitgeprüft“.
    - VIES als weiterer Dienst ist nicht vorgesehen.
  - **Steuernummer-Prüfziffer über ERiC** nur, wenn ERiC eingerichtet ist.
- **A76 (P7) Speichern und Fortsetzen.**
  - Jeder Schritt speichert beim „Weiter“ sofort als Version mit `quelle=assistent`. „Zurück“
    verliert nichts, Eingaben werden nicht erneut verlangt (WCAG 3.3.7). Der Assistent lässt sich
    jederzeit verlassen und fortsetzen.
  - Fortschritt als „Schritt 3 von 7“ (Willkommen und Fertig zählen nicht) und Schrittliste
    (`nav` mit `aria-current="step"`; erledigt, aktuell, später).
  - Die Aktionen „Weiter“, „Später ergänzen“ und „Zurück“ stehen am Ende des Formulars; unter
    64rem in einer festen Aktionsleiste statt der Navigationsleiste (A4).
  - „Später“ ist ein eigener Knopf neben „Weiter“; er speichert, was da ist, als unvollständig.
- **A77 (P6, genutzt in P7) Zweiter Faktor einrichten** (auch für Einladung und Mein Konto).
  - **Anzeige:** QR-Code (E10, `segno`, SVG als `data:`-Bild, Alternativtext „QR-Code für die
    Authenticator-App“), daneben der Schlüssel als Text in Vierergruppen mit Knopf „kopieren“
    (eigenes kleines Skript; ohne JS markierbar) und der Link „In Authenticator-App öffnen“
    (`otpauth://`, für dasselbe Handy).
  - **Bestätigung:** ein Feld für den Code (`autocomplete="one-time-code"`,
    `inputmode="numeric"`, Einfügen erlaubt, Leerzeichen toleriert).
  - **Wiederherstellungscodes:** einmal anzeigen, „als Textdatei speichern“ und „drucken“;
    „Weiter“ erst nach dem Haken „Ich habe die Codes sicher abgelegt“.
  - **Schutz:** Die Seite ist `no-store`; Geheimnis und Codes stehen nie im Log.
- **A78 (P7) Rollen des ersten Benutzers** (geändert nach F2).
  - Der erste Benutzer bekommt alle Rollen: `verwalter`, `freigeber` und `buchhalter` in allen
    eingetragenen Gesellschaften. Damit hat er jedes Recht; `betrachter` ist darin enthalten.
  - Grund: Der Inhaber muss allein arbeitsfähig sein, auch bevor Mitarbeitende eingeladen sind.
    Mitarbeitende bekommen über die Einladung nur die Rollen ihrer Aufgabe (A82); so bleiben die
    Rollen getrennt.
  - Die Frage „Arbeiten Sie allein?“ aus dem ersten Entwurf entfällt; Schritt 7 „Weitere
    Personen“ ist immer „empfohlen“.
  - Schritt 1 zeigt den Hinweis: „Sie erhalten alle Rollen. Mitarbeitende laden Sie in Schritt 7
    mit eigenen Rollen ein. Vier-Augen-Freigaben brauchen eine zweite Person mit Freigaberecht.“
- **A79 (P7) Einrichtungsstand.**
  - Fachfunktion `einrichtung.stand(gesellschaft) -> Checkliste` liefert die Punkte Pflicht
    erledigt, empfohlene offen und Hinweise, etwa „Bankverbindung fehlt – für Ausgangsrechnungen
    nötig“. CLI: `accounti einrichtung status`.
  - Die Übersichtskarte für Verwalter (A13) bleibt sichtbar, bis alle empfohlenen Punkte erledigt
    oder einzeln ausgeblendet sind. Ausgeblendete Punkte stehen im Datenbank-Abschnitt
    `einrichtung` (nur Datenbank, K1) und lassen sich auf `/einstellungen` wieder einblenden.
  - **Vier-Augen prüfen** (F2): Haben in einer Gesellschaft mindestens zwei aktive Benutzer
    `STEUER_FREIGEBEN` und ist `elster.vier_augen` aus, steht der empfohlene Punkt „Vier-Augen
    für Steuermeldungen einschalten?“ auf der Liste, mit Link zur Einstellung (A125). Für
    `zahlung.vier_augen` und `ZAHLUNG_FREIGEBEN` gilt dasselbe. Der Punkt ist eine Empfehlung,
    lässt sich ausblenden und schaltet nichts selbst ein.
- **A80 (P7) Bestehende Installationen.** Wer schon Benutzer und eine vollständige Datei hat,
  muss nicht durch den Assistenten. Die Checkliste wird aus der wirksamen Konfiguration
  berechnet.

### 6.7 Benutzerverwaltung und Mein Konto

- **A81 (P6) Benutzerliste.** Name, Anzeigename, Rollen je Gesellschaft, zweiter Faktor
  eingerichtet, Status (aktiv, gesperrt, eingeladen, Einladung abgelaufen) und letzte Anmeldung.
  Ein Verwalter sieht nur die Gesellschaften, in denen er selbst Verwalter ist.
- **A82 (P6) Einladen** (E9, entschieden F2: Mitarbeitende mit eigenem Zugang).
  - Formular: Benutzername, Anzeigename, Rollen je Gesellschaft.
  - **Rollen getrennt:** Die Rollen stehen als Kontrollkästchen mit ihren Rechten im Klartext
    (`RECHT_TEXT`, z. B. „buchen und korrigieren“, „Zahlungsläufe freigeben“). Vorbelegt ist
    `buchhalter`; `freigeber` und `verwalter` sind nie vorbelegt. Bekommt eine eingeladene Person
    `freigeber`, nennt ein Hinweis die Folgen („darf Zahlungsläufe und Steuermeldungen
    freigeben“) und den Vier-Augen-Schalter (A125).
  - Eine eigene Rolle für den Steuerberater gibt es nicht (F2).
  - Ergebnis: ein Einladungslink (256 Bit, nur der Hash gespeichert, 72 h gültig, einmalig, an
    Name und Rollen gebunden) mit „Link kopieren“; per E-Mail nur, wenn `versand` eingerichtet
    ist. Neue Tabelle `auth_einladungen`.
  - Annahme unter `/einladung/<token>`: Passwort, zweiter Faktor (A77), Codes. Erst danach ist der
    Benutzer aktiv.
  - Wird der Link mehrfach falsch aufgerufen, gilt die Sperre wie bei der Anmeldung.
- **A83 (P6) Rollen ändern, sperren, entsperren, Zugang zurücksetzen.**
  - Alle Aktionen mit K2 und mit Eintrag im Ereignisprotokoll (`auth_ereignisse`).
  - „Zugang zurücksetzen“ macht Passwort, Faktor und Sitzungen ungültig und erzeugt eine neue
    Einladung.
  - Rollenänderungen beenden die Sitzungen der Person (wie 10a).
- **A84 (P6) Schutzregeln aus 10a.**
  - Der letzte aktive Verwalter mit Faktor kann sich weder die Rolle entziehen noch sich sperren.
  - Ein fremdes Konto verwaltet nur, wer in jeder Gesellschaft Verwalter ist, in der das Konto
    Rollen hat.
- **A85 (P6) API-Token.**
  - Anlegen mit Name, Gesellschaft, Rechten aus der festen Liste (`opos:lesen`,
    `buchungen:lesen`, `belege:schreiben`, `laeufe:starten`) und Ablauf (Standard 90 Tage).
  - Der Klartext erscheint genau einmal. Die Liste zeigt Name, Rechte und Ablauf. Widerrufen ist
    möglich.
  - Alles mit K2; jedes neue Token wird gemeldet (A60).
- **A86 (P6) Anmeldeprotokoll.** `auth_ereignisse` lesbar und filterbar (Person, Art, Zeitraum),
  ohne IP-Adressen (wie 10a).
- **A87 (P1/P6) Mein Konto** (jede Rolle).
  - Schon in P1 (ohne zweiten Faktor), Seite `/konto`, gespeichert per `POST /konto/vorlieben`:
    - Sprache, Darstellung (automatisch/hell/dunkel)
    - Fachansicht an/aus
    - Beträge auf der Übersicht verbergen (wirkt ab P2)
    - Tastenkürzel an/aus (bisher `localStorage`, jetzt am Benutzer; das Skript liest den Wert aus
      einem `data-`-Attribut am `<body>`)
    - `POST /einstellungen/sprache` aus 10b-1 antwortet mit 308 auf `/konto/vorlieben`; entfällt
      ein Release später.
  - Mit P6:
    - Passwort ändern (aktuelles Passwort und Code)
    - zweiten Faktor neu einrichten (mit dem bisherigen Faktor)
    - neue Wiederherstellungscodes
    - eigene Sitzungen ansehen und beenden
- **A88 (P6) Gleichlauf.**
  - Fachfunktionen in `auth.dienst`:
    - vorhanden: anlegen, rolle, sperren, entsperren, passwort, codes
    - neu: `einladen`, `einladung_annehmen`, `zugang_zuruecksetzen`; `setze_vorlieben` schon in
      P1 (Sprache, Darstellung, Fachansicht, Beträge, Tastenkürzel; ersetzt `setze_sprache`)
  - CLI: `accounti benutzer einladen NAME --rolle …`, `accounti benutzer zuruecksetzen NAME`.

### 6.8 Design-System

- **A89 (P1) Farb-Token.** Alle Farben als CSS-Variablen auf `:root`: hell als Standard, dunkel
  über `[data-theme="dunkel"]` und, bei der Wahl „automatisch“ (`[data-theme="auto"]`), über
  `@media (prefers-color-scheme: dark)`. Dazu `color-scheme` passend zur Wahl (`light dark`,
  `light`, `dark`; E16), das I9 behebt.
  Kontraste wurden am 26.10.2026 nach WCAG gerechnet:

  | Token | hell | dunkel | Zweck | Kontrast (hell / dunkel) |
  |-------|------|--------|-------|--------------------------|
  | `--grund` | `#f5f4f1` | `#121417` | Seitenhintergrund (warmes Papier bzw. Schiefer) | — |
  | `--flaeche` | `#ffffff` | `#1a1d21` | Karten, Tabellen, Felder | — |
  | `--flaeche-2` | `#efede8` | `#22262b` | Kopfzeilen, Hervorhebung | — |
  | `--text` | `#1b1f24` | `#e8eaed` | Text | 16,6 / 14,0 auf Fläche |
  | `--text-2` | `#555d66` | `#a7aeb6` | Nebentext | 6,7 / 7,6 auf Fläche; 5,7 / 6,8 auf Fläche-2 |
  | `--linie` | `#d6d3cc` | `#33383f` | Trennlinien (nur Schmuck) | — |
  | `--linie-stark` | `#7a8088` | `#6f7781` | Feldränder, Rahmen von Bedienelementen | 4,0 / 3,7 auf Fläche (≥ 3:1) |
  | `--akzent` | `#1a5a73` | `#7dc3db` | Hauptknopf, Links, Auswahl (Petrol) | 7,6 / 8,6 auf Fläche |
  | `--akzent-text` | `#ffffff` | `#0e1a1f` | Text auf Akzent | 7,6 / 9,0 |
  | `--akzent-flaeche` | `#e3eef2` | `#183039` | ausgewählte Zeile | Akzent darauf 6,5 / 7,0 |
  | `--fokus` | `#b35c00` | `#ffb366` | Fokusring (Bernstein, von Akzent und Fehler unterscheidbar) | 4,7 / 9,6 auf Fläche, 4,3 / 10,5 auf Grund |
  | `--ok` / `--ok-flaeche` | `#1d6b3a` / `#e5f2e9` | `#7fd19b` / `#16291d` | Erfolg | 5,7 / 8,4 |
  | `--warn` / `--warn-flaeche` | `#8a5a00` / `#fbf0d9` | `#f0c46a` / `#2e2614` | Warnung, Fristen | 5,2 / 9,1 |
  | `--fehler` / `--fehler-flaeche` | `#a8241f` / `#fbe7e5` | `#ff9a92` / `#341a19` | Fehler, überfällig | 6,0 / 7,9 |
  | `--info` / `--info-flaeche` | `#1f5fa8` / `#e6eef9` | `#8db8f0` / `#172436` | Hinweis | 5,5 / 7,6 |
  | `--marke-1` … `--marke-6` | 6 Kennfarben für Gesellschaften | dieselben, aufgehellt | Kennfarbe (A5) | jeweils ≥ 3:1 zur Fläche, mit Kürzel als Text |

  Farbe trägt nie allein Bedeutung. Status hat immer Wort und Symbol (WCAG 1.4.1).
- **A90 (P1) Typografie.** `system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans",
  sans-serif`. Größen 0,875 / 1 / 1,125 / 1,375 / 1,75 rem, Grundgröße 1rem (16 px),
  Zeilenhöhe 1,5 (Überschriften 1,25). Beträge, Daten und Kontonummern in
  `font-variant-numeric: tabular-nums`. Gewichte 400 und 600, nichts dünner.
- **A91 (P1) Abstände und Raster.** 4-px-Raster mit den Token `--a-1` … `--a-8` (0,25 / 0,5 /
  0,75 / 1 / 1,5 / 2 / 3 / 4 rem). Radien 6 px (Felder, Knöpfe) und 10 px (Karten). Höchstens ein
  Schatten (Karten im Dunkelmodus ohne Schatten, mit Linie). Breakpoints 40rem, 64rem, 90rem.
  Layouts:
  - `einspaltig`
  - `zweispaltig` (Beleg | Vorschlag; ab 64rem)
  - `karten` (`repeat(auto-fit, minmax(18rem, 1fr))`)
  - `einstellungen` (Unternavigation links ab 64rem, darunter oben als Liste)
- **A92 (P1) Komponenten** als Jinja-Makros in `vorlagen/_komponenten.html`, mit Stilen in
  `statisch/accounti.css`. Jede Komponente hat die Zustände normal, hover, fokus, aktiv,
  deaktiviert, lädt und fehler, soweit sinnvoll.
  - **Bedienung:** Knopf (primär, sekundär, still, gefährlich; normal und klein; mit Symbol),
    Link-Knopf, Optionskarte (Optionsfeld mit Titel, Nebentext, Grund), Segment/Reiter
  - **Inhalte:** Karte (Titel, Zähler, Inhalt, Hauptaktion), Abzeichen/Zähler, Status-Pille
    (Wort + Symbol), Sicherheitsanzeige (niedrig/mittel/hoch)
  - **Daten:** Tabelle (A93), Beschreibungsliste (Label/Wert, Label-Spalte passend, behebt I11),
    Betrag (mit Richtung und Vorzeichen in Text, nicht nur rot/grün)
  - **Formular:** Formularfeld (A94), Feldgruppe, Fehlerliste
  - **Rückmeldung:** Hinweis (info, erfolg, warnung, fehler), leerer Zustand, Ladeanzeige
    (`htmx-request`, nur CSS)
  - **Abläufe:** Schrittanzeige, Bestätigungsschritt (eigene Seite oder Fragment statt Modal)
  - **Navigation:** Seitenleiste, untere Leiste, Brotkrumen, Seitenblättern
- **A93 (P1) Tabellen.**
  - Ruhig: Linien statt Zebra, Kopf auf `--flaeche-2`, beim Scrollen fixiert. Zahlen
    rechtsbündig, Summenzeile abgesetzt.
  - Sortierung serverseitig über Links (`aria-sort`). Dichte „normal“ (Zeilenhöhe ≥ 44 px) und
    „kompakt“ für Auswertungen.
  - Unter 40rem werden Zeilen zu Karten (Label über `data-label` in CSS) mit ausdrücklichen
    ARIA-Rollen, siehe A111.
  - `caption` ist Pflicht (darf visuell versteckt sein).
- **A94 (P1) Formulare.**
  - Das Label steht über dem Feld, Hilfetext darunter (`aria-describedby`). Der Fehler steht unter
    dem Feld, mit Symbol, Wort und `aria-invalid`.
  - Breiten passend zum Inhalt (IBAN breit, PLZ schmal). Vollständige `autocomplete`-Angaben
    (`organization`, `street-address`, `postal-code`, `address-level2`, `email`, `tel`, `username`,
    `new-password`, `current-password`, `one-time-code`).
  - Kein Platzhalter als Label (behebt I10).
- **A95 (P1) Hinweise und leere Zustände.**
  - Hinweise mit Symbol, Wort („Hinweis“, „Erledigt“, „Achtung“, „Fehler“) und Text.
    `role="status"` bzw. `role="alert"` nur für neu erscheinende Meldungen.
  - Jede Liste hat einen leeren Zustand mit Satz und nächster Aktion, z. B. „Nichts zu prüfen.
    Nächster Bankabruf: heute 14:00.“
- **A96 (P1) Symbole.** SVG-Sprite `statisch/symbole.svg` aus einer Lucide-Teilmenge (ISC,
  `statisch/LIZENZ-lucide.txt`), eingebunden mit `<svg><use href="/statisch/symbole.svg?v=…#name">`.
  Dekorative Symbole sind `aria-hidden="true"`; ohne sichtbaren Text gibt es `aria-label`.
- **A97 (P1) Druck.** `@media print`:
  - Navigation, Aktionsleisten und Knöpfe aus; Schwarz auf Weiß.
  - Ein Kopf mit Gesellschaft, Seitentitel, Datum und Benutzer (als serverseitig gerenderter,
    sonst versteckter Block).
  - Tabellen ohne Zeilenumbruch innerhalb einer Zeile (`break-inside: avoid`), Kopf wiederholt
    (`display: table-header-group`).
  - Offizielle Berichte bleiben PDF (10b-2).
- **A98 (P1) CSP.**
  - Kein `style=`, kein Inline-`<script>`, keine `on…`-Attribute, kein `javascript:`. Die CSP aus
    10a bleibt unverändert.
  - Ein Vorlagen-Test prüft alle Vorlagen auf diese Muster. Eigene Dateien tragen `?v={{ version }}`.
- **A99 (P1) Gewicht und Unabhängigkeit.**
  - Kein CDN, keine Schrift und kein Skript von Dritten.
  - Budgets, unkomprimiert: CSS ≤ 40 KB, eigene Skripte ≤ 20 KB (htmx 50 KB kommt dazu), Symbole
    ≤ 15 KB.
  - Jede Seite ist ohne JS bedienbar (A2 der Leitlinien).
- **A100 (P1) Bewegung.** Übergänge ≤ 150 ms und nur für Farbe und Deckkraft; mit
  `prefers-reduced-motion: reduce` gibt es keine.
- **A101 (P1) Musterseite** `/muster` (angemeldet, Recht `LESEN`, nicht in der Navigation; nur
  erfundene Beispieldaten, keine Daten der Gesellschaft). Sie zeigt alle Komponenten und Zustände
  in hell und dunkel (Umschalter per `?theme=`) und dient als Grundlage für Browserprobe,
  axe-Prüfung und Bildvergleich.

### 6.9 Barrierefreiheit

- **A102 (alle) Ziel** ist WCAG 2.2 Stufe AA, freiwillig; die BFSG-Einschätzung steht in 13.3.
  Dazu gehören die neuen Kriterien 2.4.11, 2.5.7, 2.5.8, 3.2.6, 3.3.7 und 3.3.8 (Tabelle in 13.4).
- **A103 (P1) Kontrast.** Ein Test rechnet aus den Token-Werten der CSS-Datei: Text mindestens
  4,5:1, große Schrift, Bedienelement-Ränder und Fokus mindestens 3:1, in hell und dunkel.
- **A104 (P1) Fokus.** Sichtbar als 2-px-Ring in `--fokus` mit 2 px Abstand (`:focus-visible`).
  Feste Leisten verdecken den Fokus nie (`scroll-padding-top/-bottom` in Höhe der Leisten;
  WCAG 2.4.11). Nach einem htmx-Austausch geht der Fokus gezielt auf die Überschrift des neuen
  Inhalts (`tabindex="-1"`) bzw. die nächste Zeile.
- **A105 (alle) Tastatur.** Alles ist ohne Maus erreichbar, ohne Falle, in sinnvoller
  Reihenfolge. „Zum Inhalt springen“ ist der erste Link. Einbuchstaben-Kürzel sind abschaltbar
  (WCAG 2.1.4, aus 10b).
- **A106 (alle) Ziele und Ziehen.** Klickziele mindestens 24 × 24 px (2.5.8); bei
  `pointer: coarse` mindestens 44 × 44 px. Keine Funktion verlangt Ziehen (2.5.7): Sortieren
  über Knöpfe, Datei-Ablage nur zusätzlich zum Auswahlknopf.
- **A107 (alle) Umbruch und Zoom.** Bei 320 CSS-px scrollt keine Seite waagrecht (1.4.10). 200 %
  Zoom ohne Verlust (1.4.4). Erhöhte Text- und Zeilenabstände brechen nichts (1.4.12).
- **A108 (alle) Formulare und Fehler.**
  - Fehlerliste oben (`role="alert"`, Links zu den Feldern), Fehlertext am Feld mit
    Lösungshinweis (3.3.1, 3.3.3).
  - Eingaben bleiben bei Fehlern erhalten. Redundante Eingaben werden vermieden (3.3.7).
- **A109 (P1) Anmeldung** (3.3.8).
  - Passwortmanager funktionieren, Einfügen ist überall erlaubt.
  - Für den Code gibt es **ein** Feld: `inputmode="numeric"` für TOTP, mit dem Link
    „Wiederherstellungscode verwenden“, der ein Textfeld anbietet (ohne JS als eigene Seite).
  - Keine sechs Einzelfelder, kein CAPTCHA.
  - Dasselbe gilt für alle Einmalcode-Felder (Freigaben, K2).
- **A110 (alle) Dynamik.**
  - Ergebnisse von htmx-Aktionen werden in einem `role="status"`-Bereich angekündigt (4.1.3), etwa
    „Freigegeben. Nächster Eintrag: Staples, 156,78 €.“
  - Ladezustände sind mit `aria-busy` gekennzeichnet.
- **A111 (P1) Tabellen als Karten.** Wird eine Tabelle unter 40rem per CSS umgebrochen, tragen
  `table`, `tr`, `th` und `td` ausdrücklich `role="table"`, `"row"`, `"columnheader"` und
  `"cell"`. Andernfalls verlieren manche Browser die Tabellensemantik, sobald sich `display`
  ändert.
- **A112 (alle) Sprache und Prüfung.**
  - `lang` für jede Seite, `lang="de"` für deutsche Fachbegriffe in der englischen Oberfläche
    (aus 10b).
  - Automatische Prüfung mit axe-core über Playwright in der Browserprobe. Das ist nur ein
    Entwicklungswerkzeug (MPL-2.0) und wird nicht ausgeliefert.
  - Je Paket ein Durchlauf von Hand: nur Tastatur, NVDA + Firefox, VoiceOver auf iOS, jeweils für
    die betroffenen Abläufe.

### 6.10 Technik, Sicherheit, Betrieb

- **A113 (alle) Gleichlauf.** Keine Logik nur im Browser. Jede neue Aktion ist eine Fachfunktion
  mit CLI-Befehl; der Test ruft beide Wege auf und vergleicht. Ausgenommen sind reine
  Anzeige-Vorlieben (A87, wie die Sprachwahl in 10b) und die Einladungsannahme im Browser (die CLI
  hat dafür `benutzer anlegen`).
- **A114 (alle) Rechte, CSRF, Einmalcode.** Jede neue Route steht in der Rechte-Matrix (10a/10b),
  jeder POST hat CSRF. Endpunkte mit Einmalcode stehen in `MIT_EINMALCODE` des Tests. Der
  Verwaltungsmodus (K2) ist eine Sitzungseigenschaft, die die Route prüft.
- **A115 (alle) htmx.** Konfiguration aus 10b unverändert (`allowEval:false`,
  `selfRequestsOnly:true` …). Muster „eine Route, zwei Formen“ (Fragment mit `HX-Request`, sonst
  ganze Seite bzw. 303). Fehlerwege für 409, 422, `HX-Redirect`, `HX-Refresh` und 503 wie 10b.
- **A116 (alle) Protokoll ohne Personenbezug.** Einstellungswerte wie IBAN, Steuernummer,
  USt-IdNr., E-Mail und Namen erscheinen nie im Log. Einrichtungscode, Einladungs-Token,
  TOTP-Geheimnis und Wiederherstellungscodes ebenso nicht. Ein Test prüft das gegen die
  Protokollausgabe (10a).
- **A117 (alle) Abhängigkeiten.** Neu ist nur `segno>=1.6.6,<2` (P6, genutzt in P7). `pypdfium2`
  kommt nicht dazu (E11 A, entschieden F3). Jede Abhängigkeit hat ein Release, das mindestens
  zwei Wochen alt ist, eine BSD/MIT/Apache/ISC-Lizenz, ist gepinnt mit Obergrenze und steht im
  Plan mit Prüfsumme. Lucide-Symbole werden als Dateien mit Lizenz beigelegt, nicht als Paket.
- **A118 (P1–P7) Migrationen und Schemaprüfung.**
  - **Gesellschaftsdatenbank:** `einstellungen`, `einstellungsantraege`, `geheimnisse`.
  - **Systemdatenbank:**
    - neue Spalten in `auth_benutzer`: `darstellung`, `fachansicht`, `betraege_verbergen`,
      `tastenkuerzel`
    - neue Spalte in `auth_sitzungen`: `verwaltung_bis`
    - neue Tabellen `auth_einladungen`, `auth_einrichtung`, `sicherungsprotokoll`
  - Zuordnung: P1 Vorlieben-Spalten; P4 `einstellungen`, `einstellungsantraege`, `geheimnisse`;
    P5 `verwaltung_bis`, `sicherungsprotokoll`; P6 `auth_einladungen`; P7 `auth_einrichtung`.
    A125 braucht keine Migration.
  - Alle Migrationen liegen in einer Alembic-Kette. Laufen zwei Pakete mit Migration parallel
    (P1 und P4 in Welle 1), setzt das später gemergte Paket `down_revision` auf den neuen Kopf,
    damit `alembic heads` genau einen Kopf zeigt.
  - Je Paket höchstens eine Migration je Datenbankart. Beim Start prüft `serve` das Schema wie in
    10b (`Dienste.pruefe_schema`) und bricht mit einem Hinweis auf `alembic upgrade head` ab.
- **A119 (alle) Zweisprachigkeit.** Alle neuen Texte stehen in `i18n/en.yaml`, der
  Vollständigkeitstest aus 10b gilt. Die Begriffe aus Anhang B gibt es in beiden Sprachen.

---

## 7. Akzeptanzkriterien

Jedes Kriterium ist automatisch prüfbar (Testclient oder Browserprobe), wo nicht anders vermerkt.
In Klammern stehen die Anforderungen, die es prüft; Anhang D ordnet jeder Anforderung ihre
Kriterien zu. Das Paket ergibt sich aus der Anforderung. „Browserprobe“ heißt Playwright mit
Chromium (Server) und Firefox (beim Nutzer, wie 10b).

**Gerüst, Design, Barrierefreiheit**

1. **AK1** Bei 320 und 390 px Breite ist `document.documentElement.scrollWidth` auf jeder Seite
   der Registry (angemeldet als jede Rolle) ≤ Fensterbreite (A22, A107). Heute misst `/pruefen`
   741 px.
2. **AK2** axe-core meldet 0 Verstöße der Stufen A und AA auf allen Seiten, in hell und dunkel,
   bei 1440 und 390 px (A112).
3. **AK3** Der Token-Kontrasttest besteht: Text ≥ 4,5:1, Bedienelemente und Fokus ≥ 3:1, in beiden
   Modi (A89, A103).
4. **AK4** Im Dunkelmodus ist der berechnete Hintergrund von `input`, `select`, `textarea` und
   `button` nicht weiß, und `<kbd>` hat ≥ 4,5:1 Kontrast (A89, behebt I9).
5. **AK5** Der Vorlagen-Test findet kein `style=`, kein Inline-Skript, kein `on…=`. Die
   Browserprobe zeigt keine CSP-Meldung in der Konsole (A98).
6. **AK6** Unter 64rem gibt es eine untere Leiste mit ≤ 5 Zielen, der aktive Punkt trägt
   `aria-current="page"`. „Freigaben“ steht darin nur mit `ZAHLUNG_FREIGEBEN` oder
   `STEUER_FREIGEBEN` (als `buchhalter`: vier Ziele, als `freigeber`: mit „Freigaben“). Die
   Kopfleiste ist ≤ 56 px hoch (heute ≈ 165 px). Die Seite `/menue` funktioniert ohne JS (A4).
7. **AK7** Der Gesellschaftswechsel über `/gesellschaft` ändert alle Ansichten (Akzeptanz 5 aus
   Spec 10 bleibt grün). Kennfarbe (Klasse `marke-n`) und Kürzel stehen auf jeder Seite, der
   `<title>` folgt dem Muster „Seite · Gesellschaft · accounti“ (A5).
8. **AK8** Die Druckansicht (Emulation `print`) einer Liste enthält keine Navigation und keine
   Knöpfe (A97).

**Übersicht**

9. **AK9** Rollen-Matrix der Übersicht:
   - `betrachter`: keine Aktionsknöpfe.
   - `freigeber`: Karte „Wartet auf Freigabe“.
   - `buchhalter`: Karte „Prüfen“ mit Knopf.
   - `verwalter`: Karte „Einrichtung & Betrieb“.

   Keine Rolle sieht eine Karte ohne Recht (A15).
10. **AK10** Jede Anzahl und Summe der Übersicht ist ein Link; die Zielliste hat genau so viele
    Einträge bzw. dieselbe Summe. Ohne registrierte Zielseite (Test-Registry ohne
    `/auswertungen`) fehlen die Karten „Zahlungen“, „Forderungen“ und „Kennzahlen“ (A13, A16).
11. **AK11** Die nächste USt-VA-Frist erscheint mit dem Datum aus `fristenkalender`, inklusive
    Dauerfristverlängerung und Periodenwert. Eine überfällige Frist steht oben, mit dem Wort
    „überfällig“ (A13, A14).
12. **AK12** Die Bank-Karte warnt, wenn der letzte Abruf älter als 3 Tage ist oder der Zustand
    Fehler meldet (A13).
13. **AK13** Bei 50.000 Buchungen und 5.000 Belegen liegt die Serverzeit der Übersicht bei
    ≤ 300 ms (p95 über 20 Aufrufe) (A19).
14. **AK14** `accounti uebersicht --json` liefert dieselben Zahlen wie die Seite (A20).

**Prüfschlange**

15. **AK15** Auf 390 × 844 liegt [Passt – freigeben] vollständig im ersten Bildschirm
    (Unterkante ≤ 844 px, ohne Scrollen). Gegenpartei, Betrag und Vorschlagssatz enden oberhalb
    der Oberkante der Aktionsleiste. Alle drei Aktionen sind ≥ 44 × 44 px (A34). Heute liegt die
    Oberkante von „Freigeben“ bei 1117 px.
16. **AK16** Die Arbeitsfläche enthält im Ausgangszustand 0 sichtbare Eingabefelder (`input`
    außer `hidden`, `select`, `textarea`) und im Aktionsbereich (`[data-aktionen]`) genau
    3 Bedienelemente: [Passt – freigeben], [Anderes Konto …], „Später klären …“ (A27).
    Navigation (Liste, Voriger, Nächster, Verlauf) und das Aufklappen der Buchungsdetails zählen
    nicht. Heute: 9 Felder, 4 Knöpfe.
17. **AK17** Eine Korrektur mit Kontovorschlag läuft in 3 Bedienschritten: „Anderes Konto“,
    Vorschlag wählen, Speichern. Keine Nummer wird getippt. Die Buchung trägt das neue Konto,
    das Journal die angemeldete Person. Danach führt „Nächster“ ohne weitere Entscheidung zum
    nächsten Eintrag, und es entsteht keine Regel (A28, A31).
18. **AK18** Das Steuerfeld erscheint nur, wenn `steuer_optionen` mehr als eine Möglichkeit lässt.
    Bei einem Automatikkonto (Test mit SKR03 8400) fehlt es (A29).
19. **AK19** Das Regelangebot kommt erst nach gespeicherter Korrektur und nur mit
    `REGELN_LERNEN`. „Nein“ speichert keine Regel. „Ja“ führt dazu, dass der nächste `bank lauf`
    die Regel trifft (Durchlauf wie Spec 10 Akzeptanz 2) (A31).
20. **AK20** Massenfreigabe einer Gruppe mit n Einträgen: n Buchungen freigegeben, n
    Journaleinträge mit gemeinsamem Bezug. Ändert sich ein `stand` zwischen Anzeige und
    Bestätigung, wird keiner freigegeben (409). Einträge mit Sperre, Warnhinweis oder Herkunft
    `standard` kommen nie in eine Gruppe. Eine Gruppe mit mehr als 100 Einträgen bietet „Die ersten
    100 freigeben“; der Rest bleibt als Gruppe stehen. Der Bestätigungsschritt einer KI-Gruppe
    nennt „Vorschlag der KI“ und die Sicherheit als Wort (A24, A25, E13).
21. **AK21** In Liste und Arbeitsfläche steht jede Kontonummer mit Bezeichnung, wenn der
    Kontenrahmen oder die Kontenliste sie kennt. Alle Konten aus mitgelieferten Regeln,
    Standards und Marktplatzwerten haben eine Bezeichnung (A36).
22. **AK22** Die Kontosuche findet „Handy“ → Telefon (SKR03 4920 / SKR04 6805) und „4920“ →
    Telefon. Ohne JS liefert der Suchknopf dieselben Treffer (A28).
23. **AK23** Ohne JavaScript funktionieren Freigeben, Korrigieren mit Kontosuche, Regel anlegen,
    Massenfreigabe, „Später klären“, Beleg hochladen, Einstellungen speichern und der Assistent
    (Testclient ohne `HX-Request`) (Leitlinie 2, A99, A115).

**Einstellungen**

24. **AK24** Eine Änderung im Browser, z. B. `mandant.rechnung.zahlungsziel_tage`, ergibt eine
    neue Version und einen Journaleintrag mit Person, `vorher` und `nachher`.
    `accounti einstellungen zeigen` und `lade_firma` liefern den neuen Wert. Der Ablauf gelingt
    im Container mit `read_only: true` und `config/:ro` (Docker-Probe) (A39, A40, A47).
25. **AK25** `UPDATE` und `DELETE` auf `einstellungen` scheitern über ORM und Trigger, in SQLite
    wie in PostgreSQL (A39).
26. **AK26** Ein festgelegter Abschnitt ist im Browser nur lesbar, sein POST wird abgewiesen.
    Betriebsfelder kommen immer aus der Datei (A42, E2).
27. **AK27** Weichen Datei und Datenbank ab, ist der Hinweis sichtbar. „Datei-Stand übernehmen“
    erzeugt eine Version mit Grund (A43).
28. **AK28** Speichern mit veralteter Version ergibt 409, gespeichert wird nichts (A45).
29. **AK29** Eine K2-Änderung ohne gültigen Einmalcode und ohne Verwaltungsmodus scheitert.
    Innerhalb von 10 min nach einem Code gelingt eine weitere K2-Änderung ohne Code. Eine
    Zahlungsfreigabe verlangt trotzdem einen frischen Code (A59).
30. **AK30** Ist `zahlung.vier_augen` an, wird das Abschalten zum Antrag. Wirksam wird es erst
    nach Bestätigung durch eine zweite Person mit `ZAHLUNG_FREIGEBEN`. Dieselbe Person kann ihren
    Antrag nicht bestätigen (A59).
31. **AK31** Sperren und Periodenwerte:
    - Der Voranmeldungszeitraum 2026 lässt sich nicht ändern, sobald eine USt-VA 2026
      übermittelt ist.
    - Der Kontenrahmen ist nach der ersten Buchung gesperrt.
    - Eine USt-VA für Dezember 2026 nutzt „Monat“, auch wenn für 2027 „Quartal“ eingetragen ist.

    (A46, E3)
32. **AK32** Ein gesetztes Geheimnis erscheint im Klartext weder in der Datenbank (nur Chiffrat)
    noch im Journal, im Log, auf einer Seite oder im Export. Der Export enthält einen
    `${…}`-Platzhalter (A48, A50).
33. **AK33** Rundlauf: `einstellungen export` + `einstellungen.quelle: datei` ergibt dieselben
    wirksamen Werte wie vorher (A50).
34. **AK34** Die Verfahrensdokumentation zu einem Stichtag vor einer Änderung zeigt den alten
    Wert, zu einem Stichtag danach den neuen, beide mit Änderungsanhang (A51).
35. **AK35** Sicherung und Wiederherstellung in eine leere Umgebung bringen Einstellungsversionen,
    Anträge und Geheimnisse zurück; Geheimnisse sind mit demselben Schlüssel entschlüsselbar
    (A52).

**Assistent und Benutzer**

36. **AK36** Ohne Benutzer leitet jede Seite auf `/einrichtung`. Ohne gültigen Einrichtungscode
    entsteht kein Konto. Mit Code entsteht ein Verwalter mit zweitem Faktor, danach ist der Code
    ungültig. Bricht die Einrichtung vor dem bestätigten Faktor ab, gibt es keinen Benutzer, und
    der Code gilt weiter. Gibt es einen Benutzer, geben `serve` und `einrichtung code` keinen Code
    aus. Der 6. Fehlversuch in 15 min wird gesperrt. Der Code steht nicht im Log (A71, A72).
37. **AK37** Der QR-Code ist die SVG-Kodierung genau der `otpauth`-URI des Benutzers. Der Test
    vergleicht mit `segno.make(uri)`. Die Seite ist `no-store` (A77).
38. **AK38** Pflichtschritte gehen nur mit gültigen Werten weiter. Mit „Später“ übersprungene
    Punkte erscheinen in `einrichtung status` und auf der Übersicht. Mit „Zurück“ bleiben alle
    Eingaben erhalten (A73, A76, A79).
39. **AK39** Validierung offline: Ein falsch geprüftes IBAN, eine USt-IdNr. mit falscher
    Prüfziffer und eine Steuernummer im falschen Format für das gewählte Bundesland ergeben
    jeweils einen Feldfehler mit Erklärung. Ohne Klick auf „online prüfen“ gibt es keinen
    Netzzugriff (Test mit gesperrtem Netz) (A75).
40. **AK40** Vorschläge: Rechtsform GmbH ergibt „Bilanz“ ohne EÜR-Wahl, mit Begründung.
    Einzelunternehmen ergibt eine Wahl mit Hinweis. Jeder Vorschlag trägt den Hinweis „mit
    Steuerberater abstimmen“ (A74).
41. **AK41** Ein Einladungslink gilt genau einmal und läuft nach 72 h ab. Nach der Annahme ist
    die Person aktiv, mit zweitem Faktor und genau den Rollen der Einladung. Das Passwort steht
    nirgends beim Verwalter. Im Einladungsformular ist nur `buchhalter` vorbelegt, `freigeber`
    und `verwalter` nie; jede Rolle zeigt ihre Rechte im Klartext. Der letzte Verwalter kann sich
    weder Rolle entziehen noch sich sperren (A82, A84).
42. **AK42** Ein im Browser angelegtes API-Token erscheint genau einmal im Klartext; danach steht
    nur der Hash in der Datenbank. Nach dem Widerruf liefert der nächste REST-Aufruf 401 (A85).
43. **AK43** Von Hand (je Paket): ein Durchlauf nur mit Tastatur und je einer mit NVDA + Firefox
    und VoiceOver auf iOS für Übersicht, Prüfen, Einstellungen Firma & Steuern und Assistent.
    Das Protokoll liegt im PR (A102, A105, A112).

**Ergänzende Kriterien — Gerüst, Design, Querschnitt (P1 und alle Pakete)**

44. **AK44** Registry-Test je Rolle (`betrachter`, `buchhalter`, `freigeber`, `verwalter`): Die
    Navigation enthält genau die Bereiche, für die eine Seite registriert ist und das Recht
    besteht, in der Reihenfolge aus A1. „Einstellungen“ erscheint nur mit `VERWALTEN`,
    „Freigaben“ nur mit `ZAHLUNG_FREIGEBEN` oder `STEUER_FREIGEBEN`. Browserprobe: Bei 1440 px ist
    die Seitenleiste sichtbar und die untere Leiste nicht (berechnetes `display`), bei 390 px
    umgekehrt; die Inhaltsbreite ist ≤ 90rem (A1–A4).
45. **AK45** Darstellung „dunkel“ gespeichert: Nach Anmeldung in einem neuen Browserkontext trägt
    `<html>` `data-theme="dunkel"`, und `color-scheme` ist `dark`; „auto“ folgt der Emulation von
    `prefers-color-scheme`. Sprache, Darstellung, Fachansicht, Beträge verbergen und Tastenkürzel
    lassen sich ohne JS ändern (POST, 303). `POST /einstellungen/sprache` antwortet mit 308 auf
    `/konto/vorlieben`. Mit „Tastenkürzel aus“ löst `f` auf der Arbeitsfläche nichts aus, und das
    Skript liest kein `localStorage` mehr (A6, A87).
46. **AK46** Vorlagen-Test über alle GET-Routen: genau ein `h1` je Seite; jede Seite unterhalb
    eines Bereichs hat eine Brotkrumen-Navigation (`nav` mit übersetztem `aria-label`) (A7).
47. **AK47** Jede Seite, auch Anmeldung, Assistent und Fehlerseiten, enthält den Hilfe-Link an
    derselben Stelle der Kopfleiste und derselben Stelle der Fokusreihenfolge. Für jeden Bereich
    der Registry liefert `/hilfe/<bereich>` 200 und enthält keinen Link auf einen fremden Host
    (A8).
48. **AK48** Provozierte 403, 404, 409 und 500 liefern die Design-Vorlage mit einem Link zurück;
    403 nennt die fehlende Rolle; 500 enthält weder Traceback noch Ausnahmetext (A9).
49. **AK49** Alle Tests aus 10a und 10b-1 sind grün; keiner ist gelöscht, umgestellte Tests stehen
    im PR. Browserprobe auf Anmeldung, `/freigaben`, `/pruefen`, `/belege/{id}` und
    `/buchungen/{id}`: Das Einmalcode-Feld hat ein sichtbares `<label>` (I10); Label und Wert
    einer Beschreibungsliste überlappen nicht (Bounding-Boxen, I11); die Hauptaktion ist ein
    primärer Knopf (I12) (A121).
50. **AK50** Statischer Test: `accounti.css` ≤ 40 KB, eigene Skripte zusammen ≤ 20 KB,
    `symbole.svg` ≤ 15 KB; keine URL auf einen fremden Host in Vorlagen, CSS und Skripten; nur die
    Schriftgewichte 400 und 600; `LIZENZ-lucide.txt` liegt bei. Browserprobe: Beträge haben
    `font-variant-numeric: tabular-nums`; mit `prefers-reduced-motion: reduce` ist jede
    `transition-duration` 0 s; jedes Symbol ohne sichtbaren Text hat ein `aria-label`, alle anderen
    sind `aria-hidden` (A90, A91, A96, A99, A100).
51. **AK51** Jedes Makro aus `_komponenten.html` wird auf `/muster` mindestens einmal aufgerufen
    (Test vergleicht die Makronamen mit dem Vorlagen-Quelltext), in den Zuständen aus A92;
    `/muster` besteht AK2 und verlangt eine Anmeldung (A92, A101).
52. **AK52** Jede `<table>` hat eine `<caption>`; sortierbare Spalten tragen `aria-sort`. Bei
    390 px tragen Tabellen in Kartenform `role="table"`, `"row"`, `"columnheader"` und `"cell"`,
    und der ARIA-Schnappschuss von Playwright zeigt Zeilen und Zellen (A93, A111).
53. **AK53** Vorlagen-Test: Jedes sichtbare Eingabefeld hat ein `<label for>`, keines nur einen
    Platzhalter. Ein Formular mit Fehlern antwortet mit 422, einer Fehlerliste (`role="alert"`,
    Links auf die Felder), `aria-invalid="true"` und `aria-describedby` am Feld; alle Eingaben
    außer Passwörtern und Codes bleiben erhalten. Jedes Code-Feld ist ein einzelnes Feld mit
    `autocomplete="one-time-code"`; Einfügen funktioniert (Browserprobe); „Wiederherstellungscode
    verwenden“ geht ohne JS (A94, A108, A109).
54. **AK54** Mit leerer Datenbank zeigt jede Liste einen Satz und einen Link zur nächsten Aktion.
    Nach einer Freigabe per htmx steht der Ergebnistext im Bereich `role="status"`; während der
    Anfrage trägt der ausgetauschte Bereich `aria-busy="true"` (A95, A110).
55. **AK55** Browserprobe mit Tab durch Prüfliste, Arbeitsfläche und eine Einstellungsseite bei 390
    und 1440 px: Das fokussierte Element liegt nie vollständig unter einer festen Leiste
    (Bounding-Box-Vergleich); der Fokusring ist ≥ 2 px breit; der erste Tab-Stopp ist „Zum Inhalt
    springen“; Tab erreicht nach endlich vielen Schritten wieder den Seitenanfang (keine Falle).
    Alle Klickziele sind ≥ 24 × 24 px, mit Emulation `pointer: coarse` ≥ 44 × 44 px; ausgenommen
    sind Links im Fließtext (A104–A106).
56. **AK56** Bei 1280 px Fensterbreite und 200 % Zoom sowie mit den Textabständen aus WCAG 1.4.12
    (eingefügtes Test-Stylesheet) ist `scrollWidth` auf jeder Seite der Registry ≤ Fensterbreite,
    und kein Text ist abgeschnitten (`scrollHeight` ≤ `clientHeight` bei Elementen mit
    `overflow: hidden`) (A107).
57. **AK57** Jede Seite hat `lang` passend zur Sprache des Benutzers; der i18n-Vollständigkeitstest
    aus 10b ist für alle neuen Texte grün; jeder Begriff aus Anhang B hat einen Eintrag in
    `en.yaml` (A112, A119).
58. **AK58** Vollständigkeitstests: Jede Route steht in der Rechte-Matrix; jeder POST ohne
    CSRF-Token ergibt 403; jeder Einmalcode-Endpunkt steht in `MIT_EINMALCODE` und scheitert ohne
    Code; jede neue Fachfunktion mit Schreibwirkung hat einen Gleichlauftest (Liste im Test, gegen
    die Router geprüft; Ausnahmen nach A113 ausdrücklich benannt). Jede neue Route liefert mit
    `HX-Request` ein Fragment und ohne die ganze Seite bzw. 303; 409, 422 und 503 kommen mit htmx
    als Fragment (A113–A115).
59. **AK59** Protokolltest: Über alle neuen Wege werden bekannte Testwerte gesendet (IBAN,
    Steuernummer, USt-IdNr., E-Mail, Name, Einrichtungscode, Einladungs-Token, TOTP-Geheimnis,
    Wiederherstellungscode, Geheimnisse); keiner erscheint in der Protokollausgabe (A116).
60. **AK60** Abhängigkeitstest: Gegenüber `main` kommt in `pyproject.toml` nur
    `segno>=1.6.6,<2` hinzu (ab P6); der Plan nennt Version, Lizenz und Prüfsumme (A117).
61. **AK61** Jede Migration läuft auf SQLite und PostgreSQL (`ACCOUNTI_TEST_PG`) hoch und wieder
    herunter; `serve` bricht mit älterem Schema mit Hinweis auf `alembic upgrade head` ab; kein
    Paket bringt mehr als eine Migration je Datenbankart; nach jedem Merge zeigt `alembic heads`
    genau einen Kopf (A118).

**Ergänzende Kriterien — Übersicht (P2)**

62. **AK62** `/aufgaben` liefert mit jedem Filter dieselben Aufgaben wie `accounti aufgaben liste`
    mit dem entsprechenden Filter (fehlende Filter bekommt die CLI dazu). „Erledigt“, „mir
    zuweisen“ und „kommentieren“ ändern die Aufgabe wie die CLI; ohne Recht 403 (A10).
63. **AK63** Testdaten mit überfälliger ZM, offenen Prüfungen und ohne Aufgaben: Die Fristen-Karte
    steht vor „Prüfen“, „Aufgaben“ steht in der „Erledigt“-Zeile; ohne offene Einträge steht
    „Alles erledigt“ mit dem Zeitpunkt des letzten Abrufs. Eine zweite Gesellschaft mit Rolle
    erscheint unter „In anderen Gesellschaften“, eine ohne Rolle nicht. Mit „Beträge verbergen“
    enthält das HTML der Kennzahlen keinen Betrag, nur „•••“ (Test-Registry mit `/auswertungen`).
    Bei 390 px ist die Hauptaktion jeder Karte so breit wie der Karteninhalt und ≥ 44 px hoch
    (A12, A14, A17, A18, A21).
64. **AK64** `/steuern/fristen` zeigt dieselben Fristen (Art, Zeitraum, Datum, Stand) wie
    `accounti fristen` für 12 Monate; mit Dauerfristverlängerung 2026 und Periodenwert 2027
    „Quartal“ stimmen Datum und Zeitraum für Dezember 2026 und das 1. Quartal 2027 (A120).

**Ergänzende Kriterien — Prüfschlange (P3)**

65. **AK65** Hochladen ohne JS (multipart POST) einer PDF, eines JPEG und einer XRechnung legt je
    einen Beleg mit Kanal `upload` im Archiv der Gesellschaft an und zeigt den Erkennungsstatus.
    Eine Datei über der Grenze ergibt 413, ohne `BELEGE_EINLIEFERN` 403.
    `/belege?status=pruefung` zeigt dieselben Belege wie `accounti belege liste --status
    pruefung`; „erneut erkennen“ wirkt wie `belege erkennen` (A11).
66. **AK66** Bei 1440 px ist die Prüfliste eine Tabelle, bei 390 px eine Kartenliste (berechnetes
    `display`); jede Zeile zeigt Kontobezeichnung, Steuer im Klartext und Sicherheit als Wort.
    [Freigeben] in einer Zeile ersetzt mit htmx die Zeile, und `document.activeElement` liegt
    danach in der nächsten Zeile; ohne JS 303 auf die Liste; ein veralteter `stand` ergibt 409
    mit Meldung (A22, A23).
67. **AK67** Testdaten: 6 Telekom-Vorschläge aus einer Regel, 2 gleiche KI-Vorschläge, 3 gleiche
    KI-Vorschläge über der Prüfschwelle, 3 gleiche KI-Vorschläge darunter, 1 Eintrag mit
    Warnhinweis, 2 Einträge mit Herkunft `standard`. Ergebnis: genau zwei Gruppen (Telekom × 6,
    KI × 3 über der Schwelle), alles andere einzeln. `accounti review --gruppen` liefert dieselben
    Gruppen (A24).
68. **AK68** Die Auswahl von 3 Zeilen zeigt die Sammelleiste mit Anzahl und Summe; „Freigeben“
    führt auf den Bestätigungsschritt mit genau diesen 3 Einträgen; ohne JS führt der Absendeknopf
    unter der Liste zum selben Schritt (A26).
69. **AK69** Der Grund ist mit „Konto geändert: alt → neu“ vorbelegt; ohne Grund wird gespeichert,
    außer Baustein 7 verlangt ihn (Testfall „ohne Steuer“: 422 mit Feldfehler). „Später klären“
    bietet als Empfänger nur Benutzer mit Rolle in der Gesellschaft und die Rollen an, kein
    Freitext; die Rückfrage ist der Auswahl zugewiesen, eine Frist wird übernommen (A30, A32).
70. **AK70** Bei 1440 px steht die Belegvorschau links und bleibt beim Scrollen sichtbar; bei
    390 px gibt es den Umschalter mit Reiter-Semantik (`role="tab"`, `aria-selected`), und
    `?zeige=beleg` zeigt den Beleg ohne JS. Bild und E-Rechnung erscheinen in der Seite, bei PDF
    auf jeder Breite „PDF öffnen“ (≥ 44 px hoch, Link auf das Original mit Typ
    `application/pdf`) und die Eckdaten Aussteller, Datum, Nummer und Brutto. Von Hand: Auf iOS
    Safari und Android Chrome öffnet „PDF öffnen“ das PDF im Systembetrachter (Protokoll im PR).
    Keine Antwort enthält Seitenbilder eines PDFs (A33, E11).
71. **AK71** Browserprobe: `f`, `e`, `z`, `j`, `k`, `b` und `?` wirken auf der Arbeitsfläche; in
    Schritt 1 wählen `1`–`6` einen Vorschlag, `/` fokussiert die Suche, `Strg+Enter` speichert; in
    Schritt 2 wirken `r` und `n`. Mit Fokus in einem Eingabefeld lösen Buchstaben nichts aus; mit
    abgeschalteten Kürzeln wirkt keines (A35).
72. **AK72** `accounti konten suche Handy` und `accounti konten vorschlag ID` liefern dieselben
    Konten in derselben Reihenfolge wie Suche und Vorschläge im Browser; `accounti bestaetige
    --gruppe` gibt dieselben Buchungen frei wie [Alle freigeben] (A37).
73. **AK73** Nach Freigeben, Korrigieren, Regel anlegen und „Später klären“ erscheint eine
    Statuszeile mit Link „Verlauf“ auf den Journaleintrag. Keine Vorlage enthält eine Aktion
    „Rückgängig“ (A38).
74. **AK74** Existiert eine gleichwirkende Regel, erscheint kein Regelangebot; ohne
    `REGELN_LERNEN` ebenso nicht. Nach der dritten gleichen Korrektur derselben Person steht „Sie
    haben das jetzt 3 × so korrigiert“ da. Die Vorschau nennt dieselben Zahlen wie
    `lernen.pruefe_entwurf` (A31).
75. **AK75** Lasttest (Marker `last`) mit 50.000 Buchungen: p95 über 20 Aufrufe ≤ 300 ms für
    Freigeben, Arbeitsfläche und Kontosuche; Gruppenbildung für 500 offene Einträge ≤ 500 ms
    (A123).

**Ergänzende Kriterien — Einstellungen, Fachkern (P4)**

76. **AK76** Vorrang-Matrix, je Fall ein Test: Umgebung schlägt alles; ein festgelegter Abschnitt
    nimmt die Datei trotz Datenbank-Version; Datenbank schlägt Datei; ohne beides gilt der
    Standard. Die erste Datenbank-Version enthält den vollständigen Abschnitt. Wird während einer
    Anfrage eine neue Version geschrieben, sehen alle Lader dieser Anfrage noch die alte (A41,
    A54).
77. **AK77** Ein unbekanntes Konto, ein Bankkonto-Sachkonto ohne Kontoart Bank, ein Skontokonto aus
    dem anderen Rahmen und eine Auftraggeber-IBAN ohne eigenes Bankkonto ergeben je einen Fehler
    mit Abschnittspfad. Ein unvollständiger `mandant` lässt sich speichern; das Ausstellen einer
    Rechnung scheitert dann mit Verweis auf „Einstellungen › Firma & Steuern“ (A44).
78. **AK78** AST-Test: `yaml.safe_load` steht nur an Stellen der Positivliste. Je Lader ein Test:
    Ein Wert aus der Datenbank-Version wirkt in CLI und Web; mit `--db` bzw. `--gesellschaft` auf
    eine andere Gesellschaft wirken deren Einstellungen (A47).
79. **AK79** `einstellungen setzen` ändert einen Wert mit Grund; K2 ohne Code scheitert; K3 erzeugt
    einen Antrag statt einer Version; ein festgelegter Abschnitt wird abgewiesen.
    `einstellungen geheimnis setzen NAME` liest den Wert nur von stdin (es gibt keine Option für
    den Wert). `einstellungen pruefen` meldet gebrochene Hash-Kette, Unvollständiges und Datei ≠
    Datenbank und endet bei Fehlern mit Exit-Code ≠ 0 (A49).
80. **AK80** Golden-Test: Mit der Beispielkonfiguration und ohne Datenbank-Version liefern alle
    Lader dieselben Modelle wie `main` vor 10c. Einzelwerte für Periodenwerte und ein
    `wirtschaftsjahr_beginn` mit Jahr bleiben gültig. Steht `kontenrahmen` nur unter `mandant`,
    warnt `einstellungen pruefen` (N1); die Beispielkonfiguration führt ihn unter `buchhaltung`
    (A53, A124).
81. **AK81** Die Firma-Seite hat genau ein Feld „Steuernummer“, es schreibt `mandant`. Sind
    `mandant.steuernummer` und `elster.steuernummer` verschieden gesetzt, warnen Seite und
    `einstellungen pruefen` (A122).

**Ergänzende Kriterien — Einstellungsseiten (P5)**

82. **AK82** `/einstellungen` zeigt die sechs Bereiche aus A55 mit Status (vollständig,
    unvollständig, festgelegt). Jede Route unter `/einstellungen` antwortet ohne `VERWALTEN` mit
    403; `/konto` ist für jede Rolle erreichbar (A55, A58).
83. **AK83** Die Formulargruppe „Steuern & Meldungen“ speichert Änderungen an `mandant` und
    `elster` als zwei Versionen in einer Transaktion; ist eine der beiden Versionen veraltet,
    entsteht keine (409). Eine K2-Änderung ohne Grund ergibt 422 mit Feldfehler. Jede
    Formulargruppe hat einen eigenen Speichern-Knopf und einen Link „Verlauf“ (A45, A56).
84. **AK84** Experten-Ansicht: Ein YAML-Syntaxfehler nennt Zeile und Spalte, ein Modellfehler den
    Pfad; mehr als 64 KB ergeben 413; ein Dokument mit Anker, Alias oder Python-Tag wird
    abgewiesen; eine gültige Änderung ergibt eine Version wie über das Formular (A57).
85. **AK85** Eine Änderung an der IBAN eines Bankkontos, am Auftraggeber, an `zahlung.vier_augen`
    oder `elster.vier_augen` oder an einer Zahlungsgrenze sowie ein neues API-Token erzeugen
    sofort je eine Benachrichtigung an jeden Verwalter und Freigeber über den Kanal aus
    Baustein 8 (Test fängt die Ausgabe), nicht erst in der Tagesübersicht. Ab P6 gilt das auch für
    eine Einladung oder Rollenänderung mit `freigeber` oder `verwalter`, nicht aber für eine mit
    nur `buchhalter` oder `betrachter` (A60).
86. **AK86** Ein Bankkonto mit falscher IBAN-Prüfziffer wird mit Feldfehler abgewiesen; das
    vorgeschlagene Sachkonto ist das nächste freie Bankkonto des Rahmens; ein Konto mit Umsätzen
    lässt sich nur deaktivieren. Anlegen im Browser und mit der CLI ergibt denselben Datensatz
    (A61).
87. **AK87** Mahnstufen lassen sich ohne JS per Knopf hinzufügen, entfernen und verschieben; die
    Vorschau zeigt das Mahnschreiben für einen Beispielposten; keine Funktion verlangt Ziehen
    (A62).
88. **AK88** „Verbindung testen“ gegen einen lokalen IMAP-Testserver listet die Ordner und holt
    nichts ab; gegen einen Server, der nicht antwortet, erscheint nach höchstens 16 s eine
    Meldung. Ein Webhook-Token erscheint genau einmal im Klartext; nach dem Widerruf weist der
    Webhook es ab. Ordner und Webhook-Adresse sind nur lesbar (A63).
89. **AK89** Felder von Marktplätzen, DATEV, ELSTER, KI-Kontierung und Prüfregeln landen im
    richtigen Abschnitt (ein Test je Formulargruppe); ERiC- und Zertifikatspfade sind nur lesbar;
    die KI-Schwellen und das Abschalten einer Prüfregel verlangen K2; der Klartext zur Schwelle
    („Ab 95 % …“) nennt den gespeicherten Wert (A64, A65).
90. **AK90** „Regel anlegen“ ohne Korrektur legt eine gelernte Regel mit Quelle `formular` an, die
    der nächste `bank lauf` trifft; `regeln.yaml` ist nur lesbar. Eine eigene Kontobezeichnung
    („1361 Verrechnung Amazon“) erscheint in Kontosuche, Prüfliste und Arbeitsfläche (A66, A67).
91. **AK91** Die Gesellschaftsseite zeigt alle Gesellschaften, Datenbankadressen ohne Passwort.
    Der Schnipsel „Gesellschaft hinzufügen“ ist gleich der Ausgabe von `accounti gesellschaft
    anlegen K --name …`; der Befehl legt das Schema an und prüft die Trennung (A68).
92. **AK92** `sicherung erstellen` und `sicherung pruefen` schreiben je einen Eintrag ins
    Sicherungsprotokoll, ohne Pfad und Schlüssel; die Betriebsseite zeigt ihn; ist die letzte
    Sicherung älter als 7 Tage oder unbekannt, warnt die Übersicht (A69, E17).
93. **AK93** Der Verlauf zeigt je Version Datum, Person, Quelle, Grund und geänderte Felder; der
    Vergleich zweier Versionen zeigt alt → neu; „Zurücksetzen“ auf Version n erzeugt eine neue
    Version mit Grund und den Daten von n; keine Version wird geändert oder gelöscht (A70).

**Ergänzende Kriterien — Benutzer (P6)**

94. **AK94** Die Benutzerliste eines Verwalters zeigt nur Gesellschaften, in denen er Verwalter
    ist. Rollenänderung, Sperren und „Zugang zurücksetzen“ verlangen K2, schreiben
    `auth_ereignisse` und beenden die Sitzungen der Person; nach dem Zurücksetzen gelten Passwort
    und Faktor nicht mehr, und es gibt eine neue Einladung. Das Anmeldeprotokoll lässt sich nach
    Person, Art und Zeitraum filtern und enthält keine IP-Adressen (A81, A83, A86).
95. **AK95** Passwort ändern verlangt das aktuelle Passwort und einen Code; den Faktor neu
    einrichten verlangt einen Code des bisherigen; neue Wiederherstellungscodes machen die alten
    ungültig; eine eigene Sitzung lässt sich beenden. `accounti benutzer einladen` und `benutzer
    zuruecksetzen` ergeben denselben Zustand wie der Browser (A87, A88).

**Ergänzende Kriterien — Assistent (P7)**

96. **AK96** Der erste Benutzer hat nach dem Assistenten `verwalter`, `freigeber` und `buchhalter`
    in allen eingetragenen Gesellschaften; Schritt 1 enthält keine Frage nach dem Alleinarbeiten,
    Schritt 7 ist als „empfohlen“ markiert. Eine Installation mit Benutzer und vollständiger Datei
    leitet nicht auf `/einrichtung`; `einrichtung status` berechnet die Checkliste aus der
    wirksamen Konfiguration. Mit zwei aktiven Benutzern mit `STEUER_FREIGEBEN` und
    `elster.vier_augen` aus enthält die Checkliste den empfohlenen Punkt „Vier-Augen für
    Steuermeldungen einschalten?“, mit einem solchen Benutzer nicht; ausgeblendet bleibt er weg,
    und eingeschaltet wird nichts (A78, A79, A80).
97. **AK97** Die Schritte 0–3 haben zusammen höchstens 10 Pflichtfelder (Zählung der
    `required`-Felder). Die Browserprobe durchläuft die Schritte 0–8 mit „Später“ ab Schritt 4
    ohne Fehler. Von Hand: Eine Person, die accounti nicht kennt, schafft den Pflichtteil in unter
    10 min (Protokoll im PR) (A73).
98. **AK98** Nach Schritt 4 mit den vorbelegten Haken stehen IBAN und Name in `mandant`
    (Bankverbindung) und in `zahlung.auftraggeber`, ohne zweite Eingabe (A73, WCAG 3.3.7).
99. **AK99** Die Schrittanzeige zeigt „Schritt n von 7“ mit `aria-current="step"`; „Später
    ergänzen“ speichert die Eingaben mit `vollstaendig=false`; der Assistent lässt sich verlassen
    und an derselben Stelle fortsetzen; bei 390 px liegen „Weiter“ und „Später ergänzen“ in der
    festen Aktionsleiste (A76).

**Ergänzende Kriterien — aus den Entscheidungen vom 26.10.2026 (P4: AK100, P2: AK101)**

100. **AK100** Vier-Augen für Steuermeldungen, Standard `false`: Ohne Schalter genügt eine
     Freigabe wie vor 10c (Golden-Test). Mit `elster.vier_augen: true`:
     - Nach der ersten Freigabe einer USt-VA verweigert `ustva uebermitteln` (Attrappe, Echtmodus)
       mit „eine zweite Person muss freigeben“.
     - Dieselbe Person kann nicht ein zweites Mal freigeben; `--von` zählt nicht als Person.
     - Nach der Freigabe durch eine zweite Person mit `STEUER_FREIGEBEN` gelingt die Abgabe.
     - Ändert sich zwischen den Freigaben eine Buchung im Zeitraum, zählt die erste nicht mehr.
     - Dasselbe gilt für `ustva dauerfrist --freigeben` und `--uebermitteln`.

     Einschalten mit nur einem aktiven Benutzer mit `STEUER_FREIGEBEN` ergibt einen Fehler mit
     Hinweis auf die Einladung. Einschalten verlangt K2. Ausschalten bei aktivem Schalter erzeugt
     einen Antrag (K3), den nur eine zweite Person mit `STEUER_FREIGEBEN` bestätigt; ebenso das
     Senken von `llm.auto_buchen_schwelle`. Die Verfahrensdokumentation nennt den Schalter (A125).
101. **AK101** Browserprobe bei 390 × 844 als `freigeber` mit einem Zahlungslauf und einer
     vorbereiteten USt-VA:
     - Auf `/freigaben` liegen Zusammenfassung, Codefeld und [Freigeben] der ersten Karte im
       ersten Bildschirm, ohne waagrechtes Scrollen; der Knopf ist ≥ 44 × 44 px.
     - Zahlungen und Kennziffern lassen sich aufklappen, auch ohne JS.
     - Die USt-VA-Karte zeigt dieselbe Zahllast wie `accounti ustva --json`, und der Zeitraum
       wird gewählt, nicht getippt.
     - Ändert sich nach der Anzeige eine Buchung im Zeitraum, ergibt [Freigeben] 409 mit Meldung,
       und es entsteht keine Freigabe.
     - Mit `elster.vier_augen` zeigt die Karte nach der ersten Freigabe „wartet auf eine zweite
       Person“ mit dem Namen der ersten.
     - Als `betrachter` sind die Karten nur lesbar, ohne Codefeld und Knopf (A126).

---

## 8. Teststrategie

- **Fachfunktionen zuerst** (testgetrieben wie in allen Plänen):
  - `uebersicht`, `pruefschlange.gruppen`/`freigeben_mehrere`, `konten.vorschlaege`/`suche`
  - `einstellungen` (Leser, Vorrang, Sperren, Periodenwerte, Geheimnisse, Export), `einrichtung`
  - `elster.freigabe` mit Vier-Augen für Steuermeldungen (A125, AK100)
  - `auth.dienst` (Einladung, Zurücksetzen)
- **Gleichlauf:** Für jede neue Aktion ein Test, der CLI und Route mit denselben Daten aufruft
  und denselben Zustand erwartet (A113).
- **Rechte-Matrix und CSRF** aus 10a/10b um alle neuen Routen erweitern. Die Vollständigkeit der
  Matrix ist selbst ein Test.
- **Abschnittsleser:** Ein AST-Test verbietet `yaml.safe_load` außerhalb der Positivliste. Ein
  Test je Lader zeigt, dass Datenbankwerte wirken. Ein Golden-Test hält fest, dass ohne
  Datenbank-Version alles wie vor 10c bleibt (AK80).
- **Browserprobe** (Playwright mit Chromium und Firefox; Firefox fehlt auf dem Server, die Probe
  läuft beim Nutzer, wie in 10b):
  - 1440, 390 und 320 px, hell und dunkel, mit axe-core
  - Messungen aus AK1, AK4, AK6, AK15, AK16, AK44, AK55, AK56 und AK101
  - Screenshots der Musterseite und der Kernseiten als Referenz im PR, ohne Pixelvergleich als
    Abbruchgrund
- **Ohne JavaScript:** Testclient ohne htmx-Köpfe für AK23.
- **Last:** Erzeugte Testdatenbank mit 50.000 Buchungen für AK13, nicht im Standardlauf (Marker
  `last`).
- **Docker-Probe:** `docker compose up` mit schreibgeschütztem `config/`; Einstellung im Browser
  ändern; Neustart; Wert bleibt (AK24).
- **Sicherungs-Rundlauf** mit Einstellungen und Geheimnissen (AK35). **Protokolltest** ohne
  Personenbezug über alle neuen Wege (AK59).
- **Rückverfolgung:** Jeder Paketplan übernimmt aus Anhang D die Anforderungen und Kriterien
  seines Pakets; der PR nennt zu jedem Kriterium den Test bzw. das Handprotokoll.

---

## 9. Paketschnitt und Reihenfolge

Schnitt nach E20 C: sieben Pakete in vier Wellen (entschieden F5, 26.10.2026). Die Nummern P1–P7
bleiben, auch wo die Reihenfolge von ihnen abweicht.

**Voraussetzungen:** 10b-1 ist auf `main` (fachlich unverändert, auf 48b2d9e gebracht, E19). Vor
P4 sind die offenen Gesamttest-Branches (`fix/gesamttest-*`) zusammengeführt, weil der
Lader-Umbau fast alle Module berührt (R2). P1 beginnt, sobald 10b-1 auf `main` ist; P4, sobald
zusätzlich die Gesamttest-Branches zusammengeführt sind. Danach laufen beide parallel.

```
 Voraussetzung  10b-1 auf main (E19)               Gesamttest-Branches zusammengeführt (R2)
                        │                                        │
                        ▼                                        ▼
 Welle 1        P1  Design-System & Gerüst         P4  Einstellungen: Fachkern + CLI
                    (Token, Komponenten,               (keine Seiten; Lader-Umbau,
                     Navigation, bestehende             Vier-Augen für Steuermeldungen)
                     Seiten, Vorlieben)                          │
                     │          │          │                     │
                     ▼          ▼          ▼                     ▼
 Welle 2        P2  Übersicht  P3  Prüf-   10b-2           P5  Einstellungsseiten
                    & Aufgaben     schlange    Auswertungen    (braucht P1 und P4)
                    (+ Fristen,    (+ Belege-  (nur nach P1)         │
                     Freigaben      Minimum)                         │
                     unterwegs)                                      ▼
 Welle 3                                                   P6  Benutzer & Mein Konto
                                                               (Einladung, 2FA mit QR)
                                                                     │
                                                                     ▼
 Welle 4                                                   P7  Einrichtungsassistent
                                                               (braucht P4, P5, P6)
```

| Paket | Welle | Inhalt | Anforderungen | Akzeptanz | hängt ab von | Umfang |
|-------|-------|--------|---------------|-----------|--------------|--------|
| **P1** Design-System & Gerüst | 1 | Token hell/dunkel, Komponenten, Musterseite, Symbole; Seitenleiste, untere Leiste (Freigaben nur mit Freigaberecht), `/menue`, Kopf mit Gesellschaft und Benutzermenü, `/gesellschaft`, Hilfe, Fehlerseiten; Mein Konto (Vorlieben) mit Umzug der Sprachwahl; bestehende Seiten aus 10a/10b-1 ins neue Design (ohne neue Bedienung); Migration Vorlieben. Querschnittsregeln (A102–A119) gelten ab hier für jedes Paket | A1–A9, A87 (Vorlieben), A89–A101, A121; A102–A119 | AK1–AK8, AK44–AK61; AK43 je Paket für dessen Abläufe | 10b-1 auf `main` | L |
| **P4** Einstellungen, Fachkern | 1 | Tabellen `einstellungen`, `einstellungsantraege`, `geheimnisse`; Abschnittsleser und Lader-Umbau; Vorrang, Festlegung, Betriebsfelder, Herkunft; Validierung; Periodenwerte und Sperren; Anträge (K3) als Fachfunktion; CLI `einstellungen`; Export; Verfahrensdoku zum Stichtag; Sicherung; neue Felder; Vier-Augen für Steuermeldungen (`elster.vier_augen`) als Fachfunktion und CLI | A39–A54, A122, A124, A125 | AK24 (CLI-Teil), AK25, AK26 (Fachkern), AK30 (CLI-Teil), AK31–AK35, AK76–AK81, AK100 | 10b-1 auf `main`, Gesamttest-Branches zusammengeführt | L |
| **P2** Übersicht & Aufgaben | 2 | Fachfunktion `uebersicht` + CLI, Karten nach Dringlichkeit und Rolle, „In anderen Gesellschaften“, Beträge verbergen, `/aufgaben`, `/steuern/fristen`, `/freigaben` für unterwegs (Karten, Werte vor der Freigabe, Zeitraum wählen) | A10, A12–A21, A120, A126 | AK9–AK14, AK62–AK64, AK101 | P1; P4 nur für die Anzeige „wartet auf eine zweite Person“ bei Steuermeldungen (A125) | M |
| **P3** Prüfschlange | 2 | Liste neu (Tabelle/Karten), Ein-Klick-Freigabe, Gruppen (KI ab 3 gleichen, F4), Massenfreigabe, Arbeitsfläche mit drei Aktionen, Kontovorschläge und -suche, Steuer nur wenn nötig, Regel als Schritt 2, „Später klären“ mit Personenwahl, Belegvorschau mobil mit „PDF öffnen“ (E11 A, F3), Kontobezeichnungen und Stichwörter, Belege hochladen und Liste | A11, A22–A38, A123 | AK15–AK23, AK65–AK75 | P1 (P2 nur für die Gruppenzahl auf der Prüfen-Karte) | L |
| **P5** Einstellungsseiten | 2 | alle Seiten aus A55–A70, Formularmuster, Experten-Ansicht, Verwaltungsmodus (K2) und Anträge im Browser (K3), Schalter Vier-Augen für Steuermeldungen, Benachrichtigung, Bankkonten, Belegeingang mit Verbindungstest, Verlauf, Betrieb mit Sicherungsprotokoll | A55–A70 | AK24 (Browser, Docker-Probe), AK26–AK30, AK82–AK93 (AK85 ohne den Rollen-Teil) | P1, P4 | L |
| **P6** Benutzer & Mein Konto | 3 | Benutzerliste, Einladung mit getrennten Rollen, Rollen, Sperren, Zurücksetzen, API-Token, Anmeldeprotokoll, Mein Konto (Sicherheit), 2FA-Einrichtung mit QR (`segno`), Benachrichtigung bei Freigabe- und Verwaltungsrollen | A77, A81–A88; A60 (Rollen-Teil) | AK37, AK41, AK42, AK85 (Rollen-Teil), AK94, AK95 | P5 (Gliederung „Benutzer & Rollen“, Verwaltungsmodus) | M |
| **P7** Assistent | 4 | Einrichtungscode, Schritte 0–8, erster Benutzer mit allen Rollen, Vorschläge, Validierung, Checkliste (Einrichtungspunkte der Übersichtskarte „Einrichtung & Betrieb“, Empfehlung Vier-Augen) | A71–A80 | AK36, AK38–AK40, AK96–AK99 | P4, P5, P6 | M |

**Begründung der Reihenfolge** (F5):

- **Welle 1, P1 und P4 parallel.** P1 zuerst, weil alle Pakete mit Seiten Design und Gerüst
  brauchen. P1 bringt keine neue Fachlogik, ist also gut prüfbar, und behebt schon den
  Dunkelmodus, die Kopfleiste und das waagrechte Scrollen (I1, I8–I12). P4 hat keine Seiten und
  hängt nicht an P1. Der Lader-Umbau berührt fast alle Module (R2); je früher er auf `main` ist,
  desto weniger spätere Branches müssen ihn nachziehen. P5 und P7 warten ohnehin auf P4, und die
  CLI bekommt `einstellungen` sofort.
- **Berührungspunkte von P1 und P4:** P1 ändert Vorlagen, CSS, Navigation und die Systemdatenbank
  (Vorlieben), P4 Lader, das neue Modul `einstellungen`, CLI und die Gesellschaftsdatenbank.
  Gemeinsam sind nur die Alembic-Kette (A118: das später gemergte Paket setzt `down_revision`
  neu) und `docs/betrieb.md`.
- **Welle 2:** P2 (Übersicht, zweiter Nutzerbefund) und P3 (Bedienung, erster Nutzerbefund)
  brauchen nur P1 und dürfen parallel laufen; das später gemergte der beiden trägt die
  Gruppenzahl auf der Prüfen-Karte ein (A13). P5 braucht P1 und P4. 10b-2 hängt nur an P1
  (Design) und an den Absprungzielen aus 10b-1.
- **Welle 3, P6:** braucht die Gliederung „Benutzer & Rollen“ und den Verwaltungsmodus aus P5.
- **Welle 4, Assistent zuletzt:** Er setzt sich aus Fachkern (P4), Einstellungsformularen (P5) und
  2FA-Einrichtung (P6) zusammen. Früher gebaut, entstünden Formulare doppelt. Der Nutzer hat
  seine Einrichtung schon per YAML; sie bleibt nach F1 Startwert (A53).

**Bei nur einem Arbeitsstrang** gelten dieselben Wellen, innerhalb einer Welle in dieser Folge:
P1 → P4 → P2 → P3 → 10b-2 → P5 → P6 → P7.

**Branches:** `feat/oberflaeche-p1-design`, `feat/oberflaeche-p2-uebersicht`,
`feat/oberflaeche-p3-pruefen`, `feat/oberflaeche-p4-einstellungen-kern`,
`feat/oberflaeche-p5-einstellungen-seiten`, `feat/oberflaeche-p6-benutzer`,
`feat/oberflaeche-p7-assistent`; je ein PR mit Squash-Merge gegen `main`. Zu jedem Paket gehört
ein Umsetzungsplan in `docs/plans/` im Stil der bisherigen Pläne, mit der Liste seiner
Anforderungen und Akzeptanzkriterien aus Anhang D.

---

## 10. Abhängigkeiten

**Intern**

- **10a:** Gerüst, Anmeldung, Rollen, Gesellschaften, CSP, CSRF, Einmalcode, Laufsperre,
  Sicherung, Ereignisprotokoll.
- **10b-1:**
  - Prüfschlange, `kontierungsgruende` (Gruppen), Lernschleife (`lernen.lerne`, Richtung),
    `storno.steuer_optionen`
  - Belegvorschau, i18n, htmx-Fehlerwege, `pruefen.js`
  - Muss vor P1 und P4 auf `main` sein.
- **Baustein 7:** Journal (Einstellungsänderungen), Sperren (A46), Storno statt Rückgängig,
  Verfahrensdoku (A51), Prüfregeln (A65).
- **Baustein 8:** Aufgaben (Übersicht, `/aufgaben`, Benachrichtigung A60).
- **Baustein 9:** `steuer.fristen`, ELSTER-Protokoll und -Freigaben (Übersicht, A126),
  `elster.freigabe` (Vier-Augen für Steuermeldungen, A125), `elster.steuernummer` (A75).
- **Baustein 5:** `bankkonten` (Status), Tresor, `fints` (E18 A).
- **Baustein 4:** `kontakte.ustid` (A75), `opos.auswertung`.
- **Baustein 6:** `zahlung.vorschlag`, Vier-Augen (K3).
- **Baustein 12:** Kontenrahmen (Bezeichnungen, Kontoarten für die Richtung in A28).

**Extern**

| Was | Version | Lizenz | Zweck | Paket |
|-----|---------|--------|-------|-------|
| `segno` | 1.6.6 (12.03.2025) | BSD-3-Clause | QR-Code als SVG | P6 (P7 nutzt es) |
| Lucide-Symbole (Dateien) | aktuelle Version, mindestens 2 Wochen alt | ISC | Symbole | P1 |
| axe-core *(nur Entwicklung)* | aktuelle Version, mindestens 2 Wochen alt | MPL-2.0 | Barrierefreiheitsprüfung in der Browserprobe | P1 |

htmx 2.0.11 ist schon eingebunden (10b). Python-Abhängigkeiten für Formulare kommen nicht dazu,
Multipart geht weiter über `belege.webhook.anfrage`. `pypdfium2` (E11 B) entfällt nach F3.

**Daten:** Kontobezeichnungen und Stichwörter SKR03/SKR04 (A36) als eigene Zusammenstellung. Ohne
sie erfüllt P3 die Kriterien AK21 und AK22 nicht.

---

## 11. Risiken und Gegenmittel

| # | Risiko | Gegenmittel |
|---|--------|-------------|
| R1 | Zwei Quellen für Einstellungen verwirren („Ich habe die YAML geändert, nichts passiert“) | Herkunft auf jeder Seite, Hinweis bei Abweichung, Warnung beim Start (`serve`, `einstellungen pruefen`), Festlegung in der Datei, Export als Rückweg (A43, A50) |
| R2 | Der Lader-Umbau trifft fast alle Module, andere Bausteine (Gesamttest) bauen parallel | E5 B: gleiche Signaturen, ein Eingriff je Lader; P4 als eigenes Paket mit AST-Test; Umbau erst nach den laufenden Gesamttest-Branches, dann aber in Welle 1, damit möglichst wenige spätere Branches ihn nachziehen müssen (F5) |
| R3 | Massenfreigabe gibt falsche Vorschläge in großer Zahl frei | Gruppenregeln (E13), KI-Vorschläge erst ab 3 gleichen und ab der Prüfschwelle, Bestätigungsschritt mit Liste, Summe und Herkunft, höchstens 100, alles oder nichts; Berichtigung über Storno (F4 so entschieden) |
| R4 | Der Einrichtungscode landet in einem zentralen Log | nur auf stderr beim Start, nicht im Anwendungsprotokoll; mit `einrichtung code` neu erzeugbar; gültig nur bis zum ersten Verwalter (A72) |
| R5 | Rechte an den Kontobezeichnungen (DATEV-Kontenrahmen) | eigene Zusammenstellung der gebräuchlichen Konten mit Quellenangabe, nicht der vollständige Rahmen; vor dem Zusammenführen prüfen, ob kurze Sachbezeichnungen überhaupt schutzfähig sind; im Zweifel eigene Formulierungen (A36) |
| R6 | Mobile PDF-Anzeige bleibt unbefriedigend | E11 A (F3 so entschieden): „PDF öffnen“ im Systembetrachter, Eckdaten des Belegs daneben, Handprobe auf iOS und Android (AK70). Seitenbilder (E11 B) wären eine neue Entscheidung mit neuer Abhängigkeit |
| R7 | Der Verwaltungsmodus erweitert die Angriffsfläche einer gestohlenen Sitzung | auf 10 min begrenzt, nur Einstellungen (keine Freigaben), endet mit der Sitzung; K3 für Lockerungen; Benachrichtigung bei Bank- und Freigabeänderungen (A59, A60) |
| R8 | Das Paket P1 wird groß, weil alle Seiten umgestellt werden | Übersicht in eigenes Paket P2 ausgelagert (E20); Design-System und Musterseite zuerst, dann Seite für Seite, jede mit Browserprobe; Umfang „L“ ehrlich eingeplant |
| R9 | Die Vorschläge im Assistenten werden als Beratung verstanden | überall als „Vorschlag“ gekennzeichnet, Hinweis auf den Steuerberater, keine Vorauswahl bei echten Wahlrechten (A74) |
| R10 | Zwischen P1 und P3 hat die Prüfschlange das neue Aussehen, aber noch die alte Bedienung | kurzer Zeitraum; P1 behebt dabei nur Darstellung (I1, I8–I12), keine halbe neue Bedienung (A121); P3 beginnt in Welle 2 direkt nach P1, parallel zu P2 |
| R11 | Ohne zweite Person kann ein K3-Antrag nie bestätigt werden | gewollt; Ausweg über die Festlegung in der Datei durch den Betreiber; Antrag läuft nach 7 Tagen ab (E6) |
| R12 | Rechtsstand der Vorschläge im Assistenten (Schwellen § 18 UStG, § 141 AO) ändert sich | Grundlage je Vorschlag mit Stand in A74; Werte als Daten in einer Datei mit Datum, nicht im Code; vor jeder Umsetzung von P7 neu prüfen |
| R13 | Mit `elster.vier_augen` fehlt kurz vor einer Frist die zweite Person, die USt-VA geht zu spät raus | Voreinstellung aus (A125); Einschalten nur mit zwei Freigabe-Berechtigten; Übersicht und Fristenliste zeigen „1 von 2 Freigaben“ mit Resttagen; Ausweg über die Festlegung in der Datei durch den Betreiber |
| R14 | Mitarbeitende bekommen mehr Rechte als nötig, etwa Freigabe oder Verwaltung | getrennte Rollen; im Einladungsformular nur `buchhalter` vorbelegt, Rechte im Klartext; Benachrichtigung aller Verwalter und Freigeber bei jeder Vergabe von `freigeber` oder `verwalter` (A60, A82) |

---

## 12. Entscheidungen (26.10.2026)

Die Fragen F1–F5 aus dem Entwurf sind beantwortet. F1–F4 hat der Nutzer entschieden, F5 wurde
in der Umsetzungsplanung festgelegt. Zu Vorlagen ohne eigene Frage gilt die Empfehlung aus
Abschnitt 5. Je Frage folgen die Antwort und die Stellen, die sie ändert.

1. **F1 — Einstellungen in der Datenbank.** *Status: entschieden 26.10.2026.*
   - **Frage:** Gilt ab der ersten Änderung im Browser der Stand aus der Datenbank, oder bleibt
     die YAML maßgeblich und der Browser zeigt nur an?
   - **Entscheidung:** Die Datenbank ist maßgeblich, wie empfohlen (E1 B, E2). Ab der ersten
     Änderung im Browser gilt der Stand aus der Datenbank, mit Verlauf und Grund. Die YAML ist nur
     noch Startwert; einzelne Abschnitte können in der Datei festgelegt bleiben.
   - **Folgen:** keine Änderung an A39–A54 und A124 (sie setzten die Empfehlung schon um). Neu
     ist nur, dass `elster.vier_augen` als Datenbank-Einstellung gepflegt wird (F2, A125).
2. **F2 — Wer arbeitet mit?** *Status: entschieden 26.10.2026.*
   - **Frage:** Arbeiten weitere Personen mit eigenem Zugang mit?
   - **Entscheidung:** Außer dem Inhaber arbeiten **Mitarbeitende** mit eigenem Zugang. Ein Zugang
     für den Steuerberater ist nicht vorgesehen.
   - **Folgen:**
     - **Rollen getrennt:** Einladung per Link (E9 B entschieden). Das Formular belegt nur
       `buchhalter` vor und zeigt die Rechte im Klartext (A82, AK41). Wer `freigeber` oder
       `verwalter` bekommt, wird allen Verwaltern und Freigebern gemeldet (A60, AK85, R14).
     - **Erster Benutzer:** bekommt alle Rollen (`verwalter`, `freigeber`, `buchhalter`). Die
       Frage „Arbeiten Sie allein?“ entfällt, damit sinkt der Pflichtteil auf höchstens
       10 Felder; Schritt 7 „Weitere Personen“ ist empfohlen (A73, A78, AK96, AK97, Skizzen 6a,
       6c, 6d).
     - **Vier-Augen für Steuermeldungen:** als Einstellung `elster.vier_augen` verfügbar,
       Voreinstellung aus (A125, AK100, Skizze 7). Begründung der Voreinstellung in A125: Die
       Trennung der Rollen trägt die Kontrolle schon, Vier-Augen braucht zwei
       Freigabe-Berechtigte, Fristen sind hart, und es gibt keine Pflicht dazu. Bei Mitarbeitenden empfiehlt accounti den Schalter,
       erzwingt ihn aber nicht (A79, AK96). Das Feld ersetzt das frühere
       `einstellungen.steuer_vier_augen` aus der Datei (E6, A59, A65, A124, Anhang A).
     - **Kein Steuerberater-Zugang:** neues Nicht-Ziel (Abschnitt 3); Schritt 6 bleibt bei
       Berater- und Mandantennummer (A73).
3. **F3 — Handy.** *Status: entschieden 26.10.2026.*
   - **Frage:** Reicht für PDF-Belege ein Knopf „PDF öffnen“, und sollen Zahlungsläufe unterwegs
     freigegeben werden?
   - **Entscheidung:** PDF über den Knopf „PDF öffnen“ im Systembetrachter, ohne die neue
     Abhängigkeit `pypdfium2` (E11 A entschieden). Freigaben von Zahlungslauf und USt-VA auch
     unterwegs; in der unteren Leiste steht „Freigaben“ nur für Freigabe-Berechtigte.
   - **Folgen:** A33 und AK70 (PDF-Knopf auf jeder Breite, Handprobe iOS/Android), A117 und
     Abschnitt 10 (kein `pypdfium2`), neues Nicht-Ziel; Leitlinie 5 nennt Freigaben als vierten
     Handy-Ablauf; A4 und AK6 (Leiste nur mit Freigaberecht); neu A126 „Freigaben unterwegs“ mit
     AK101 (Karten, Werte vor der Freigabe sichtbar, Zeitraum wählen statt tippen); Skizzen 2, 5b,
     5d und 9.
4. **F4 — KI-Vorschläge gesammelt freigeben.** *Status: entschieden 26.10.2026.*
   - **Frage:** Dürfen gleichartige KI-Vorschläge gesammelt freigegeben werden?
   - **Entscheidung:** Ja, unter den Bedingungen der Spec (E13): ab 3 gleichen Vorschlägen, nur
     ab der Prüfschwelle (Sicherheit mindestens „mittel“), höchstens 100 je Vorgang, alles oder
     nichts.
   - **Folgen:** E13, A24, R3 als entschieden markiert. Der Bestätigungsschritt nennt bei
     KI-Gruppen „Vorschlag der KI“ und die Sicherheit (A25, AK20, Skizze 3a). AK67 prüft die
     Gruppenregeln unverändert.
5. **F5 — Reihenfolge.** *Status: entschieden 26.10.2026 (in der Umsetzungsplanung festgelegt).*
   - **Frage:** Bleibt es bei „erst Design, Übersicht und Prüfschlange, danach Einstellungen,
     Benutzer und Assistent“, oder kommt die Einrichtung früher?
   - **Entscheidung:** P1 (Design-System & Gerüst) und P4 (Einstellungen: Fachkern + CLI) laufen
     parallel als erste Pakete. Danach folgen P2, P3 und P5, dann P6, dann P7; 10b-2 kommt nach
     P1.
   - **Folgen:** E20 entschieden, Abschnitt 9 in vier Wellen mit neuem Diagramm und Begründung;
     A118 und AK61 (ein Alembic-Kopf bei parallelen Migrationen); R2 und R10 angepasst. Die
     Paketnummern bleiben.

### Nachträge aus P1 (04.11.2026)

Folgen der Leinwand-Freigabe und der Umsetzung von Paket 1 (Plan
`docs/plans/2026-10-28-oberflaeche-p1-design.md`, Abschnitte „Abweichungen von der Spec“ und
„Umsetzung“). Keine neuen Fragen; der Nutzer bestätigt sie mit dem PR.

- **A6:** Sprache und Darstellung im Benutzermenü werden auch mit htmx erst mit „Übernehmen“
  gespeichert, nicht schon bei der Auswahl (WCAG 3.2.2).
- **A4:** Die schmale Kopfleiste trägt zusätzlich das Hilfe-Symbol (A8, AK47; WCAG 3.2.6).
- **A90/A91:** Schriftskala mit 12, 13, 20 und 40 px neben 14/16/18/22/28 px; zum 4-px-Raster
  die Zwischenstufen 20/28/40 px und, nur in Komponenten, 2/6/10 px; Radien 2, 4, 6, 8, 10,
  12 px und „rund“ (Leinwand).
- **A5/A89:** Kennfarben aus der Leinwand plus Oliv als sechste; das Kürzel auf der Marke ist
  ein Monogramm aus dem Namen (das Registry-Kürzel ist dafür zu lang).
- **A92:** zusätzliche Komponenten Aufklapper, Sammelleiste, Marke und Avatar; `feld` mit
  „Warnung“ und „bestätigt“; `karte` mit Summe rechts im Kopf.
- **A93/A111:** Tabellen werden unter **64rem** (statt 40rem) zu Karten — bei 200 % Zoom mit
  Textabständen (AK56) schnitt der Tabellenrahmen sonst breite Tabellen ab.
- **A96:** 36 statt „etwa 25“ Symbole (Auswahl nach der Leinwand), Budget eingehalten.
- **A99/A92:** alle Stile in einer Datei `accounti.css`; je Bereich eigene Dateien gibt es nicht
  mehr (`pruefen.css` entfällt).
- **Auslegungen:** A104 „2-px-Ring“ als Mindestmaß (3 px wie die Leinwand); A91 „zweispaltig ab
  64rem“ als „zwei Spalten, sobald beide Platz haben“; AK47 gleicher Index je angemeldetem
  Benutzer, gleiche relative Reihenfolge auf schlichten Seiten; AK54 Link auf den
  Hilfeabschnitt, wo die nächste Aktion keine Seite hat; AK55 an `/konto` statt einer
  Einstellungsseite gemessen; AK61 nennt `accounti db upgrade` und `alembic upgrade head` als
  Gleichwert mit Vermerk; A117 gilt für `pyproject.toml` und Ausgeliefertes (axe-core,
  MPL-2.0, ist ein Entwicklungswerkzeug).
- **Werkzeug:** Die Browserprobe läuft mit Playwright 1.59.1 und Chromium 1217 (vorhanden)
  statt 1.64.0 (Download nicht freigegeben); Firefox, NVDA und VoiceOver prüft der Nutzer.

---

## 13. Recherche (Stand 26.10.2026)

Übernommen werden Muster, keine Texte, Bilder oder Abläufe im Detail. [B] bedeutet: belegt in
Hilfe- oder Produktseiten des Herstellers. [T] bedeutet: aus Testberichten oder anderen
Drittquellen. [V] bedeutet: eigene Ableitung.

### 13.1 Wettbewerber

| Produkt | Prüfen/Freigeben | Startseite | Ersteinrichtung | Mobil |
|---------|------------------|------------|-----------------|-------|
| sevDesk | Zuordnungsvorschläge mit Haken/X und „Alle bestätigen“; eigener Abschnitt „Automatisch zugeordnet“ zur Nachkontrolle; Leerzustand „Alles erledigt“ [B] | Übersicht mit USt-Zahllast, „Buchhaltungsscore“, Kontoständen, offenen Rechnungen, Aufgaben [B] | Einstellungen Buchhaltung & Steuern (Regel-/Kleinunternehmer, EÜR/GuV, Ist/Soll, SKR); Warnung vor unterjährigem Wechsel; Änderungsprotokoll [B] | Apps zum Fotografieren und Verbuchen [B] |
| Lexware Office | Reiter „Vorschläge prüfen“ mit Zähler; Haken/X je Zeile, Mehrfachauswahl, „Alle annehmen“ (höchstens 1.000); „Ein Zuordnungsvorschlag allein verbucht noch nichts“; lernt aus manuellen Zuordnungen; **keine eigenen Regeln**; Kategoriesuche mit Stichwort ab 3 Zeichen und alten Namen [B] | Steuerkachel USt-VA mit Frist (inklusive Dauerfrist), Warnsymbol, „Einrichten“, wenn Angaben fehlen; „Privat-Modus“ blendet Zahlen aus [B] | Startcheckliste mit „optional“ und „empfohlen“; **Gewinnermittlung aus der Rechtsform abgeleitet**; USt-Einstellungen gesperrt nach der ersten übermittelten USt-VA [B] | Buchhaltungs- und Scan-App [B] |
| BuchhaltungsButler | Buchungsvorschläge bestätigen; Sammelfunktionen für ähnliche Transaktionen [T]; Automatisierungs- und Buchhaltungsregeln, von Hand angelegt [B]; Plausibilitätsprüfung [B] | Kennzahlen, fehlende und unbezahlte Rechnungen, To-dos; **Einrichtungsassistent auf der Startseite zeigt fehlende Angaben** [B/T] | Modus (selbst buchen oder vorbereitend), EÜR/Bilanz, Bank, USt-ID, SKR03 als Standard [T] | Scan-App; Web laut Test nicht mobil optimiert [T] |
| DATEV Unternehmen online | Automatisierungsservice Bank: Vorschläge als sicher/unsicher/unvollständig gekennzeichnet, KI-Symbol; „sicher“ bucht automatisch mit Kennzeichnung; lernt bei Bestätigen und Ändern [B]. Belegfreigabe: mehrstufig, Vertretung, Vier-Augen, Betragsgrenzen, Protokoll wer/wann [B] | nicht öffentlich dokumentiert | Stammdaten über die Kanzlei [V] | Upload-App, mobile Freigabe [B] |
| Candis | **Feldvorschläge je Geschäftspartner mit Ampel und Prozentwert** (pro Rolle abschaltbar); mehrstufige Workflows, Betragsbedingungen, Vertretung, Erinnerungen [B] | **rollenabhängiges Dashboard**: „My Tasks“ nach Arbeitsschritt; „Monitoring“ nur für Admin und Buchhaltung [B] | Erste Schritte: Organisation, Inbox, Benutzer, Workflows; **Geschäftsjahr ist irreversibel** [B] | freigeben und ablehnen in der App, Push [B] |
| GetMyInvoices | Freigabe-Workflows mit Budgetgrenzen und Vertretung; ohne Freigabebedarf automatisch freigegeben [B] | kaum dokumentiert | Setup-Guide: Portale → Postfach → App → Export → Bank → Benutzer [B] | Scan offline, Freigabe in der App [B] |

**Übernommene Muster:**

| Muster | Herkunft | wo in 10c |
|--------|----------|-----------|
| Eigene Prüfansicht mit Zähler und Leerzustand „Alles erledigt“ | sevDesk, Lexware | A2, A14, A95 |
| Haken je Zeile, Mehrfachauswahl, „Alle“ nur begrenzt | Lexware, sevDesk | A23, A25, A26 |
| Ein Vorschlag bucht nichts ohne Bestätigung; Herkunft und Sicherheit sichtbar, als Wort und nicht nur als Farbe | Lexware, DATEV, Candis | A27, A89 |
| Lernen je Geschäftspartner | Candis, DATEV, Lexware | A28 (Vorschläge „bisher 8 × bei …“) |
| Kontosuche nach Stichwort mit Erklärung | Lexware | A28, A36 |
| Startseite als Aufgabenliste, rollenabhängig; Überwachung nur für passende Rollen | Candis | A12–A15 |
| USt-VA-Kachel mit Frist, Dauerfrist, Warnung, „Einrichten“ bei fehlenden Angaben | Lexware | A13 (Fristen), A79 |
| Beträge auf der Startseite ausblenden | Lexware | A18 |
| Checkliste mit „empfohlen“ und „optional“; Rest als Assistent auf der Startseite | Lexware, BuchhaltungsButler | A73, A79 |
| Gewinnermittlung aus der Rechtsform; SKR03 als Vorgabe | Lexware, BuchhaltungsButler | A74 |
| Unumkehrbare Einstellungen warnen bzw. sperren | Lexware, sevDesk, Candis | A46 |
| Vier-Augen als zweite Stufe, Betragsgrenzen, Protokoll | DATEV, Candis, GetMyInvoices | K3 (A59) |

**Wo accounti bewusst abweicht:** Keines der Produkte dokumentiert Tastaturkürzel für die
Prüfschlange, und keines bietet nach einer Korrektur ausdrücklich eine Regel an. Lexware
verzichtet sogar ausdrücklich auf eigene Regeln. accounti hält an beidem fest (10b), aber als
**optionalen zweiten Schritt mit Satz und Vorschau** statt als Formularteil (A31). Grund ist das
Produktversprechen: Regeln sind sichtbar und prüfbar, nicht nur implizit gelernt.

### 13.2 Quellen

- sevDesk: https://intercom.help/sevdesk/de/articles/9382118-automatische-transaktionszuordnung ·
  https://intercom.help/sevdesk/de/articles/9382213-einstellung-zu-buchhaltung-steuer ·
  https://sevdesk.de/dashboard/
- Lexware Office: https://help.lexware.de/de-form/articles/548900-zuordnungsvorschlage-fur-deine-bankumsatze ·
  https://help.lexware.de/de-form/articles/548575-die-richtige-kategorie-finden ·
  https://help.lexware.de/de-form/articles/548063-die-steuerkachel-im-dashboard ·
  https://help.lexware.de/de-form/articles/786908-die-richtigen-angaben-in-den-allgemeinen-einstellungen-wahlen ·
  https://help.lexware.de/de-form/articles/547927-checkliste-fur-einen-optimalen-start-mit-lexware-office
- BuchhaltungsButler: https://www.buchhaltungsbutler.de/funktionen/ ·
  https://www.experte.de/buchhaltung/buchhaltungsbutler
- DATEV: https://www.datev.de/web/de/steuerberatung/loesungen/rechnungswesen/buchfuehrung-erstellen/automatisierungsservices-rechnungswesen/datev-automatisierungsservice-bank ·
  https://www.datev.de/web/de/steuerberatung/loesungen/rechnungswesen/belege-und-daten-digital-in-die-kanzlei-uebertragen/digital-zusammenarbeiten/belege-freigeben-mit-datev-unternehmen-online
- Candis: https://hilfe.candis.io/en/articles/257633-field-suggestions ·
  https://hilfe.candis.io/en/articles/410234-dashboard-overview ·
  https://hilfe.candis.io/en/collections/616917-first-steps
- GetMyInvoices: https://help.getmyinvoices.com/en/faq/how-to-create-an-approval-process/ ·
  https://help.getmyinvoices.com/en/guide/
- UStG § 18: https://www.gesetze-im-internet.de/ustg_1980/__18.html (gelesen am 26.10.2026)
- GoBD Rz. 154 (Versionierung der Verfahrensdokumentation):
  https://www.iww.de/bbp/bilanzierung/sonderthema-die-neuen-gobd-in-der-praxis-die-neuen-gobd-teil-3-verfahrensdokumentation-pragmatisch-anpacken-f84986
  — Wortlaut gegen die GoBD in der Fassung vom 14.07.2025 prüfen
- PyPI-Metadaten: `segno` 1.6.6, `qrcode` 8.2, `pypdfium2` 5.14.0 (abgerufen am 26.10.2026)

### 13.3 BFSG — gilt es für accounti?

Das Barrierefreiheitsstärkungsgesetz erfasst Dienstleistungen nur, wenn sie **für Verbraucher**
erbracht werden (§ 1 Abs. 3 BFSG). Darunter fallen etwa Bankdienstleistungen für Verbraucher und
Dienstleistungen im elektronischen Geschäftsverkehr. Letztere liegen nach § 2 Nr. 26 BFSG nur vor,
wenn der Dienst auf den Abschluss eines Verbrauchervertrags zielt. Verbraucher ist nach § 2 Nr. 16
BFSG, wer überwiegend nicht gewerblich oder selbstständig beruflich handelt. Kleinstunternehmen
(weniger als 10 Beschäftigte und höchstens 2 Mio. € Umsatz oder Bilanzsumme, § 2 Nr. 17 BFSG) sind
als Dienstleister ausgenommen (§ 3 Abs. 3 BFSG). Konformität gilt als vermutet, wenn die
harmonisierten Normen eingehalten sind (§ 4 BFSG, praktisch EN 301 549 mit WCAG 2.1 AA). Die
Bundesfachstelle Barrierefreiheit hält reine B2B-Dienste für nicht betroffen.

**Einschätzung [V]:** Ein selbst gehostetes accounti, das ein Unternehmen intern für die eigene
Buchhaltung nutzt, fällt **nicht** unter das BFSG. Es gibt keinen Verbraucher, keinen
Verbrauchervertrag, und Anwendungssoftware steht nicht in der Produktliste des § 1 Abs. 2 BFSG.
Anders könnte es aussehen, wenn jemand accounti als gehosteten Dienst mit Online-Vertragsschluss
für Privatpersonen anbietet. Das ist kein Ziel des Projekts (Bauplan: kein Kanzleiprodukt, keine
fremden Mandanten).

**Folge für 10c:** WCAG 2.2 AA bleibt **freiwilliges** Ziel (A102). Gründe: Mitarbeitende mit
Einschränkungen, Bedienung unterwegs, gute Tastaturbedienung für Vielbucher, und es kostet im
Neubau wenig. Wird es später Pflicht, ist es schon erfüllt.

Quellen: https://www.gesetze-im-internet.de/bfsg/__1.html · https://www.gesetze-im-internet.de/bfsg/__2.html ·
https://www.gesetze-im-internet.de/bfsg/__3.html · https://www.gesetze-im-internet.de/bfsg/__4.html ·
https://www.bundesfachstelle-barrierefreiheit.de/DE/Barrierefreiheitsstaerkungsgesetz/FAQ/faq_node

### 13.4 WCAG 2.2 — neue Kriterien der Stufen A/AA und was sie hier bedeuten

| Kriterium | Stufe | Bedeutung für accounti | Anforderung |
|-----------|-------|------------------------|-------------|
| 2.4.11 Focus Not Obscured (Minimum) | AA | Feste Kopfleiste, untere Leiste, Sammelleiste und Aktionsleiste dürfen die fokussierte Zeile nicht verdecken (`scroll-padding`); nach einem htmx-Austausch den Fokus gezielt setzen | A104 |
| 2.5.7 Dragging Movements | AA | Mahnstufen sortieren und Belege ablegen gehen immer auch per Knopf | A62, A106 |
| 2.5.8 Target Size (Minimum) | AA | ≥ 24 × 24 px für Haken, Kontrollkästchen und Seitenblättern in dichten Tabellen; auf Touch 44 px | A106 |
| 3.2.6 Consistent Help | A | Der Hilfe-Link steht auf allen Seiten an derselben Stelle, auch im Assistenten | A8 |
| 3.3.7 Redundant Entry | A | Der Assistent fragt nichts doppelt ab (Firmenadresse → Auftraggeber, IBAN → Bankkonto) | A76 |
| 3.3.8 Accessible Authentication (Minimum) | AA | Passwortmanager, Einfügen erlaubt, **ein** Codefeld mit `autocomplete="one-time-code"`, keine sechs Einzelfelder, kein CAPTCHA. Laut W3C ist Abtippen ohne Einfügemöglichkeit nicht konform | A109 |

4.1.1 Parsing entfällt in WCAG 2.2. Quellen: https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/ ·
https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html

---

## Anhang A — Einstellungs-Inventar

Spaltenlegende:

- **Lader (Aufrufe):** Funktion und Zahl der Aufrufstellen auf `main` 48b2d9e.
- **Ziel:** DB = Abschnitt in `einstellungen`; Datei = nur Datei/Umgebung (A42); G = Geheimnis
  (A48).
- **Stufe:** Bestätigungsstufe nach A59 für die genannten Felder; alle anderen Felder sind K1.
- **Periode:** Periodenwert nach E3.

| Abschnitt | Lader (Aufrufe) | Ziel | Seite | Stufe K2/K3 | Periode |
|-----------|-----------------|------|-------|-------------|---------|
| `mandant` | `lade_firma` (2), `lade_eigene_firma` (8), `elster.lade_mandant` (1), `elster.lade_oss` (3); Auftraggeber-Standard in `zahlung` | DB | Firma & Steuern › Firmendaten, Steuern | K2: `ust_id`, `steuernummer` (die eine, A122), `bank.iban`, `oss`, `rechtsform`. Neu sind `rechtsform` und `kennfarbe` (K1) | `oss` (Quartal) |
| `buchhaltung` | `lade_buchhaltung` (24) | DB | Firma & Steuern › Buchhaltung | K2: `kontenrahmen` (gesperrt nach erster Buchung), `bank_konto`, Skontokonten, `konten` (eigene Namen: K1) | — |
| `datev` | `export.datev`, `lade_datev_mandant` (2), `befehle/gesellschaft`, `befehle/betrieb` | DB | Belege & Anbindungen › DATEV; `wirtschaftsjahr_beginn` → Buchhaltung | K2: `wirtschaftsjahr_beginn` (gesperrt nach erster Buchung) | — |
| `abschluss` | `lade_abschluss` (2) | DB | Firma & Steuern › Abschluss | K2: `gewinnermittlung`, `ergebnis_konto` | `gewinnermittlung` (Wirtschaftsjahr) |
| `kasse` | `lade_kasse` (1) | DB | Bank & Zahlungen › Kasse | — | — |
| `anlagen` | `lade_anlagen` (6) | DB | Firma & Steuern › Anlagen (Experten-Ansicht) | K2: Konten | — |
| `elster` | `lade_elster` (7) | DB; Datei: `eric.*`, `pin_datei`; G: PIN | Firma & Steuern › Steuern & Meldungen; Anbindungen › ELSTER | K2: `voranmeldungszeitraum`, `dauerfristverlaengerung`, `sondervorauszahlung`, `steuernummer` (nur abweichend, Experten-Ansicht, A122), `bundesland`, `kennziffern_konten`, `steuerrelevante_konten`, `uebermittler`, `hersteller_id`, `vier_augen` einschalten (neu, A125); **K3** (solange `vier_augen` an ist): `vier_augen` aus | `voranmeldungszeitraum`, `dauerfristverlaengerung` (Jahr) |
| `ustid_pruefung` | `lade_ustid_pruefung` (6) | DB; Datei/Umgebung: `url` | Firma & Steuern › USt-IdNr.-Prüfung (Experten-Ansicht) | — | — |
| `bank` | `lade_bank_einstellungen` (13) | DB; Datei/Umgebung: `fints.produkt_id` | Bank & Zahlungen › FinTS, Kreditkarte | K2: `kreditkarte.geldtransit_konto` | — |
| `import` | CLI `import` | DB (Modell neu) | Bank & Zahlungen › Bankimport | — | — |
| `zahlung` | `lade_zahlung` (2) | DB | Bank & Zahlungen › Zahlungsverkehr | K2: `auftraggeber`, `einzelbuchung`; **K3** (solange `vier_augen` an ist): `vier_augen` aus, `ersteller_darf_freigeben` an, `freigeber` erweitern, `hoechstbetrag` bzw. `hoechstbetrag_zahlung` anheben oder entfernen | — |
| `mahnwesen` | `lade_mahnwesen` (1) | DB | Bank & Zahlungen › Mahnwesen | — | — |
| `belegkanaele` | `lade_belegkanaele` (5) | DB; Datei: `webhook.host/port`, `email[].ca_datei`, Ordnerpfade; Passwörter weiter in `kanal_zugaenge` (Tresor) | Belege & Anbindungen › Belegeingang | K2: Postfach-Passwort | — |
| `integrationen` | `lade_integrationen` (1), `lade_kontext` (4), `lade_steuerangaben` (1) | DB | Belege & Anbindungen › Marktplätze (+ Experten-Ansicht) | K2: Erlöskonten, `bu_*`, `ust_gebuehren`, OSS-Konten | — |
| `llm` | Klassifikation | DB (Modell neu); G: `api_key` | Belege & Anbindungen › KI-Kontierung | K2: `auto_buchen_schwelle`, `pruefung_schwelle`, `api_key`; **K3** (solange `elster.vier_augen` an ist): `auto_buchen_schwelle` senken | — |
| `pruefung` | `lade_pruefung` (7) | DB; Datei: `archiv`, `kontenrahmen_datei` | Belege & Anbindungen › Prüfregeln | K2: `abgeschaltet`, `schwere`, `belegfrei`; **K3** (solange `elster.vier_augen` an ist): `abgeschaltet` erweitern | — |
| `aufgaben` | `lade_aufgaben_einstellungen` (3), `lade_anbindungen` (4) | DB; G: Webhook-URL mit Geheimnis | Benutzer & Rollen › Aufgaben & Benachrichtigung | — | — |
| `versand` | `lade_versand` (4) | DB; G: `smtp.passwort` | Belege & Anbindungen › E-Mail-Versand | K2: `smtp.passwort` | — |
| `bwa` (10b-2) | `berechne_bwa` | DB | Auswertungen › Schema (Experten-Ansicht) | — | — |
| `server` | `lade_server` (1) | Datei | Betrieb (lesend) | — | — |
| `auth` | `lade_auth` (2) | Datei | Betrieb (lesend) | — | — |
| `gesellschaften` | `lade_gesellschaften` (1) | Datei | Gesellschaften (lesend) | — | — |
| `database` | wird nicht gelesen (`--db`/`ACCOUNTI_DB`) | Datei/Umgebung | — | — | — |
| `einstellungen` *(neu)* | Abschnittsleser | Datei | Betrieb (lesend): `quelle`, `festgelegt` (das frühere `steuer_vier_augen` ist jetzt `elster.vier_augen`, A125) | — | — |
| `einrichtung` *(neu)* | `einrichtung.stand` | nur DB | Einstellungen (Startseite): ausgeblendete Checklistenpunkte | — | — |
| `regeln.yaml` | `lade_regeln` (5) | Datei (je Gesellschaft); gelernte Regeln in der Datenbank (10b) | Belege & Anbindungen › Kontierungsregeln | K2: neue Regel per Formular, Regel deaktivieren | — |
| Bankkonten, Kreditkarten | Datenbank (5) | bleibt | Bank & Zahlungen | K2: anlegen, IBAN, Sachkonto, Zugang | — |
| Kanalzugänge, Webhook-Token | Datenbank (2) | bleibt | Belege & Anbindungen | K2 | — |
| Benutzer, Rollen, Token | Systemdatenbank (10a) | bleibt | Benutzer & Rollen | K2; Vergabe von `freigeber` oder `verwalter` zusätzlich mit Benachrichtigung (A60) | — |

## Anhang B — Klare Sprache

| heute (10b-1) | Standardansicht 10c | Fachansicht / Details |
|---------------|---------------------|-----------------------|
| Soll 4980 / Haben 1200 | „→ Betriebsbedarf (4980)“; Bankseite nicht genannt | Soll 4980 an Haben 1200 |
| Steuerschlüssel 9 | „mit 19 % Vorsteuer“ | Steuerschlüssel 9 (Vorsteuer 19 %) |
| Confidence 62 % | „Sicherheit: mittel“ (niedrig < `pruefung_schwelle` ≤ mittel < `auto_buchen_schwelle`) | 62 % |
| KI-Vorschlag (LLM) · Modell … | „Vorschlag der KI“ | Quelle `llm`, Modell, Begründung |
| Regelwerk · Regel X | „nach Ihrer Regel „X““ | Quelle `regelwerk`, Regel |
| Kontakt | „wie bisher bei diesem Lieferanten/Kunden“ | Quelle `kontakt` |
| Freigeben | „Passt – freigeben“ | — |
| Korrigieren | „Anderes Konto …“ | — |
| Zurückstellen mit Rückfrage | „Später klären …“ | — |
| Regel daraus machen · Muster (Text, nur ganze Wörter) · Suchen in | „Künftig immer so? Wenn Absender „eBay“ (Einnahmen) → …“ | Muster, Feld, Richtung |
| Zahlungsrichtung | „Ausgaben“ / „Einnahmen“ | Richtung |
| Gegenpartei | „Empfänger“ (Ausgabe) / „Absender“ (Einnahme) | Gegenpartei |
| Buchung und Journal | „Verlauf“ | Journal |
| Einmalcode | „Code aus Ihrer Authenticator-App“ | Einmalcode |
| USt-VA | „Umsatzsteuer-Voranmeldung“ (erste Nennung je Seite), danach „USt-VA“ | — |
| OPOS / offene Posten | „offene Rechnungen“ (Forderungen / Verbindlichkeiten) | offene Posten |
| Storno | „Buchung berichtigen (Storno)“ | Storno |

Fachbegriffe ohne tragfähige Entsprechung bleiben, wie in 10b, auch im Englischen deutsch
(„Buchungssatz“, „GoBD“, „SKR03“ …). Die Fachansicht ist eine Benutzer-Einstellung (A87), keine
Rolle.

## Anhang C — Ist-Screenshots (26.10.2026)

Ablage: liegt beim Autor der Spec (Bildschirmfotos nicht eingecheckt)

| Datei | Seite | Breite |
|-------|-------|--------|
| `01-anmelden-desktop.png`, `01-anmelden-390.png` | Anmeldung | 1440 / 390 |
| `02-start-desktop.png`, `02-start-390.png` | Übersicht | 1440 / 390 |
| `03-pruefen-liste-desktop.png`, `03-pruefen-liste-390.png` | Prüfliste (390: waagrechtes Scrollen, I1) | 1440 / 390 |
| `04-freigaben-desktop.png`, `04-freigaben-390.png` | Freigaben | 1440 / 390 |
| `10-pruefen-arbeitsflaeche-desktop.png`, `10-pruefen-arbeitsflaeche-390.png`, `10-pruefen-arbeitsflaeche-390-erster-bildschirm.png` | Arbeitsfläche (I2, I3) | 1440 / 390 |
| `11-pruefen-regeln-*.png`, `12-pruefen-zurueckgestellt-*.png` | Regeln, Zurückgestellt | 1440 / 390 |
| `20-start-dunkel-desktop.png`, `21-arbeitsflaeche-dunkel-desktop.png` | Dunkelmodus (I9) | 1440 |
| `messwerte.json` | `scrollWidth`/`scrollHeight` je Seite, Lage der Aktionen auf 390 px | — |

## Anhang D — Rückverfolgung: Anforderung → Akzeptanzkriterium

Jede Anforderung hat mindestens ein Kriterium aus Abschnitt 7. Die Tabelle ist aus den Verweisen
in Klammern hinter den Kriterien erzeugt und wird bei jeder Änderung neu abgeglichen (Prüfskript
im Plan von P1: jede Nummer A1–A126 kommt in mindestens einem Kriterium vor). Stand: abgeglichen
am 26.10.2026 nach Einarbeitung der Entscheidungen F1–F5. Für die
Entscheidungen E1–E20 gibt es keine eigenen Kriterien; sie wirken über die Anforderungen, die
sie umsetzen.

| Anforderung | Paket | Titel | Akzeptanz |
|-------------|-------|-------|-----------|
| A1 | P1 | Ziel-Gliederung | AK44 |
| A2 | P1 | Registry | AK44 |
| A3 | P1 | Breite Bildschirme (≥ 64rem) | AK44 |
| A4 | P1 | Schmale Bildschirme (< 64rem) | AK6, AK44 |
| A5 | P1 | Aktive Gesellschaft | AK7 |
| A6 | P1 | Benutzermenü | AK45 |
| A7 | P1 | Seitentitel und Brotkrumen | AK46 |
| A8 | P1 | Hilfe | AK47 |
| A9 | P1 | Fehler- und Statusseiten | AK48 |
| A10 | P2 | Aufgabenliste `/aufgaben` | AK62 |
| A11 | P3 | Belege, Minimalumfang | AK65 |
| A12 | P2 | Aufbau | AK63 |
| A13 | P2 | Karten | AK10, AK11, AK12 |
| A14 | P2 | Dringlichkeit | AK11, AK63 |
| A15 | P2 | Rollen | AK9 |
| A16 | P2 | Keine toten Zahlen | AK10 |
| A17 | P2 | Weitere Gesellschaften | AK63 |
| A18 | P2 | Beträge verbergen | AK63 |
| A19 | P2 | Leistung | AK13 |
| A20 | P2 | Gleichlauf | AK14 |
| A21 | P2 | Handy | AK63 |
| A22 | P3 | Liste | AK1, AK66 |
| A23 | P3 | Ein-Klick-Freigabe | AK66 |
| A24 | P3 | Gruppen gleichartiger Vorschläge | AK20, AK67 |
| A25 | P3 | Massenfreigabe | AK20 |
| A26 | P3 | Eigene Auswahl | AK68 |
| A27 | P3 | Arbeitsfläche im Ausgangszustand | AK16 |
| A28 | P3 | Korrektur, Schritt 1 „Welches Konto passt?“ | AK17, AK22 |
| A29 | P3 | Steuer nur, wenn nötig | AK18 |
| A30 | P3 | Grund | AK69 |
| A31 | P3 | Schritt 2 „Künftig immer so?“ | AK17, AK19, AK74 |
| A32 | P3 | Später klären | AK69 |
| A33 | P3 | Belegvorschau | AK70 |
| A34 | P3 | Ziel auf dem Handy | AK15 |
| A35 | P3 | Tastatur | AK71 |
| A36 | P3 | Kontobezeichnungen und Stichwörter | AK21 |
| A37 | P3 | Gleichlauf | AK72 |
| A38 | P3 | Rückmeldung, kein Rückgängig | AK73 |
| A39 | P4 | Tabelle `einstellungen` | AK24, AK25 |
| A40 | P4 | Journal | AK24 |
| A41 | P4 | Wirksamer Wert | AK76 |
| A42 | P4 | Betriebswerte nur aus Datei oder Umgebung | AK26 |
| A43 | P4/P5 | Herkunft sichtbar | AK27 |
| A44 | P4 | Validierung | AK77 |
| A45 | P4 | Gleichzeitigkeit | AK28, AK83 |
| A46 | P4 | Periodenwerte und Sperren | AK31 |
| A47 | P4 | Lader-Umbau | AK24, AK78 |
| A48 | P4 | Geheimnisse | AK32 |
| A49 | P4 | CLI | AK79 |
| A50 | P4 | Rückweg zur Datei | AK32, AK33 |
| A51 | P4 | Verfahrensdokumentation | AK34 |
| A52 | P4 | Aufbewahrung und Sicherung | AK35 |
| A53 | P4 | Übergang für bestehende Installationen | AK80 |
| A54 | P4 | Schnappschuss je Anfrage | AK76 |
| A55 | P5 | Gliederung | AK82 |
| A56 | P5 | Formularmuster | AK83 |
| A57 | P5 | Experten-Ansicht | AK84 |
| A58 | P5 | Rechte | AK82 |
| A59 | P5 | Bestätigungsstufen | AK29, AK30 |
| A60 | P5; Rollen-Teil P6 | Benachrichtigung | AK85 |
| A61 | P5 | Bankkonten und Kreditkarten | AK86 |
| A62 | P5 | Zahlungsverkehr und Mahnwesen | AK87 |
| A63 | P5 | Belegeingang | AK88 |
| A64 | P5 | Marktplätze, DATEV, ELSTER | AK89 |
| A65 | P5 | KI-Kontierung und Prüfregeln | AK89 |
| A66 | P5 | Kontierungsregeln | AK90 |
| A67 | P5 | Kontenliste | AK90 |
| A68 | P5 | Gesellschaften | AK91 |
| A69 | P5 | Betrieb | AK92 |
| A70 | P5 | Verlauf je Abschnitt | AK93 |
| A71 | P7 | Auslöser | AK36 |
| A72 | P7 | Einrichtungscode | AK36 |
| A73 | P7 | Schritte | AK38, AK97, AK98 |
| A74 | P7 | Vorschläge | AK40 |
| A75 | P7 | Validierung | AK39 |
| A76 | P7 | Speichern und Fortsetzen | AK38, AK99 |
| A77 | P6, genutzt in P7 | Zweiter Faktor einrichten | AK37 |
| A78 | P7 | Rollen des ersten Benutzers | AK96 |
| A79 | P7 | Einrichtungsstand | AK38, AK96 |
| A80 | P7 | Bestehende Installationen | AK96 |
| A81 | P6 | Benutzerliste | AK94 |
| A82 | P6 | Einladen | AK41 |
| A83 | P6 | Rollen ändern, sperren, entsperren, Zugang zurücksetzen | AK94 |
| A84 | P6 | Schutzregeln aus 10a | AK41 |
| A85 | P6 | API-Token | AK42 |
| A86 | P6 | Anmeldeprotokoll | AK94 |
| A87 | P1/P6 | Mein Konto | AK45, AK95 |
| A88 | P6 | Gleichlauf | AK95 |
| A89 | P1 | Farb-Token | AK3, AK4 |
| A90 | P1 | Typografie | AK50 |
| A91 | P1 | Abstände und Raster | AK50 |
| A92 | P1 | Komponenten | AK51 |
| A93 | P1 | Tabellen | AK52 |
| A94 | P1 | Formulare | AK53 |
| A95 | P1 | Hinweise und leere Zustände | AK54 |
| A96 | P1 | Symbole | AK50 |
| A97 | P1 | Druck | AK8 |
| A98 | P1 | CSP | AK5 |
| A99 | P1 | Gewicht und Unabhängigkeit | AK23, AK50 |
| A100 | P1 | Bewegung | AK50 |
| A101 | P1 | Musterseite | AK51 |
| A102 | alle | Ziel | AK43 |
| A103 | P1 | Kontrast | AK3 |
| A104 | P1 | Fokus | AK55 |
| A105 | alle | Tastatur | AK43, AK55 |
| A106 | alle | Ziele und Ziehen | AK55 |
| A107 | alle | Umbruch und Zoom | AK1, AK56 |
| A108 | alle | Formulare und Fehler | AK53 |
| A109 | P1 | Anmeldung | AK53 |
| A110 | alle | Dynamik | AK54 |
| A111 | P1 | Tabellen als Karten | AK52 |
| A112 | alle | Sprache und Prüfung | AK2, AK43, AK57 |
| A113 | alle | Gleichlauf | AK58 |
| A114 | alle | Rechte, CSRF, Einmalcode | AK58 |
| A115 | alle | htmx | AK23, AK58 |
| A116 | alle | Protokoll ohne Personenbezug | AK59 |
| A117 | alle | Abhängigkeiten | AK60 |
| A118 | P1–P7 | Migrationen und Schemaprüfung | AK61 |
| A119 | alle | Zweisprachigkeit | AK57 |
| A120 | P2 | Fristenliste `/steuern/fristen` | AK64 |
| A121 | P1 | Bestehende Seiten im neuen Design | AK49 |
| A122 | P4 | Eine Steuernummer | AK81 |
| A123 | P3 | Antwortzeiten | AK75 |
| A124 | P4 | Neue und geänderte Felder | AK80 |
| A125 | P4 | Vier-Augen für Steuermeldungen | AK100 |
| A126 | P2 | Freigaben unterwegs | AK101 |

