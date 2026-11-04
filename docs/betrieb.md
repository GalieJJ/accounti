# accounti — Betrieb

Wie accounti auf einem eigenen Server läuft: mit Docker Compose, PostgreSQL, dem geplanten
Lauf, Anmeldung mit zweitem Faktor, mehreren eigenen Gesellschaften, verschlüsselten
Sicherungen und einem Löschkonzept, das die Aufbewahrungsfristen kennt.

```
 Browser / Fremdsystem ──HTTPS──▶ Reverse-Proxy (TLS) ──HTTP──▶ app  (accounti serve, :8400)
                                                                 │
                                       lauf (accounti betrieb lauf: bank lauf + aufgaben lauf)
                                                                 │
                                                  db (PostgreSQL 16) · Volume daten (Belegarchiv)
```

## Schnellstart mit Docker Compose

1. Konfiguration: `cp config/accounti.example.yaml config/accounti.yaml` und den Abschnitt
   `mandant` ausfüllen. Das Verzeichnis `config/` wird schreibgeschützt nach
   `/arbeit/config` eingehängt (`regeln.yaml`, `banken.yaml` liegen daneben).
2. Geheimnisse in eine Datei `.env` neben `docker-compose.yml` (`chmod 600`, nie ins
   Repository — `.gitignore` und `.dockerignore` schließen sie aus):

   ```bash
   POSTGRES_PASSWORD=$(openssl rand -hex 24)
   ACCOUNTI_SCHLUESSEL=…            # accounti bank schluessel (Tresor: Bank-PIN, TOTP)
   ACCOUNTI_SICHERUNG_SCHLUESSEL=…  # accounti sicherung schluessel
   ```

   Das Datenbank-Passwort steht in einer URL: nur Buchstaben und Ziffern (wie oben) oder
   URL-kodiert.
3. Starten: `docker compose up -d --build`. Es laufen `db` (ohne veröffentlichten Port),
   `app` (nur auf `127.0.0.1:${ACCOUNTI_PORT:-8400}`) und `lauf` (alle
   `${ACCOUNTI_LAUF_MINUTEN:-60}` Minuten `bank lauf` und `aufgaben lauf`). Die Tabellen
   legt accounti beim ersten Befehl selbst an und vermerkt in einer neuen Datenbank den
   Stand der Migrationen (`alembic_version`) — spätere Updates laufen dann mit
   `accounti db upgrade` (unten, Upgrades). `app` und `lauf` haben eine
   Speichergrenze (`${ACCOUNTI_SPEICHER:-1g}`): jede Passwort-Prüfung (scrypt) braucht
   128 MiB, die App prüft höchstens `server.anmeldungen_gleichzeitig` (2) zugleich und
   antwortet sonst nach `server.anmeldung_warten_sekunden` (5) mit 503 und `Retry-After`
   (wer wartet, belegt keinen Arbeitsthread).
4. Ersten Benutzer anlegen — er muss Verwalter sein — und den zweiten Faktor einrichten:

   ```bash
   docker compose exec app accounti benutzer anlegen chef --rolle verwalter --rolle freigeber
   docker compose exec app accounti benutzer 2fa chef   # Schlüssel in die App, Code eingeben
   ```

   Die zehn Wiederherstellungscodes erscheinen genau einmal — ausdrucken oder im
   Passwortmanager ablegen. Ab jetzt verlangen `benutzer …` und `token …` einen
   Verwalter mit Einmalcode, z. B.
   `docker compose exec -e ACCOUNTI_BENUTZER=chef app accounti benutzer anlegen eva --rolle buchhalter`
   (der Code wird abgefragt; ohne `ACCOUNTI_BENUTZER` gilt der Anmeldename im Container,
   `accounti`).
5. Reverse-Proxy mit TLS davor (unten), dann `https://accounti.example.de/anmelden`.

Gesundheit: `GET /gesund` (prüft auch die Datenbank); das Abbild hat einen `HEALTHCHECK`.

### Was im Abbild steckt — und was nicht

- `python:3.12-slim-bookworm`, accounti per `pip install .`, Tesseract (deutsch) für
  Scans (`ACCOUNTI_OCR=nein` baut ohne), Alembic unter `/app`.
- Läuft als Benutzer `accounti` (UID 10001), Dateisystem schreibgeschützt bis auf das
  Volume `/arbeit/daten` und `/tmp`, ohne Linux-Capabilities, `no-new-privileges`.
- **Keine Geheimnisse und keine Daten:** `.dockerignore` hält `.env`, `config/*.yaml`,
  Datenbanken, Archive, Sicherungen, Tests und Prüfwerkzeuge heraus.
- Nicht enthalten: Java mit KoSIT-Validator und Mustang (formale Prüfung von E-Rechnungen,
  `scripts/pruefwerkzeuge_installieren.sh`), ERiC (ELSTER), python-fints (Extra `fints`).

## Umgebungsvariablen

| Variable | Bedeutung |
|----------|-----------|
| `ACCOUNTI_DB` | Datenbank-URL für alle Befehle (statt `--db`), z. B. `postgresql+psycopg://…` |
| `ACCOUNTI_ARCHIV` | Belegarchiv (statt `--archiv`), im Abbild `/arbeit/daten/belege` |
| `ACCOUNTI_KONFIG` | Konfigurationsdatei (statt `--config`) und Ort der Registry `gesellschaften` |
| `ACCOUNTI_GESELLSCHAFT` | Gesellschaft (statt `--gesellschaft`) |
| `ACCOUNTI_SYSTEM_DB` | Systemdatenbank (Benutzer, Rollen, Sitzungen, Token), überstimmt die Registry — gehört eine Gesellschaft schon zu einer anderen, bricht jede Rechteprüfung ab (Merker, unten) |
| `ACCOUNTI_SCHLUESSEL` | Tresor-Schlüssel (Bankzugänge, TOTP-Geheimnisse) — ohne ihn keine Anmeldung |
| `ACCOUNTI_SICHERUNG_SCHLUESSEL` | Schlüssel der Sicherungen (sonst `ACCOUNTI_SCHLUESSEL`) |
| `ACCOUNTI_BENUTZER` | handelnde Person in der CLI |
| `ACCOUNTI_EINMALCODE` | Einmalcode für einen CLI-Befehl in Skripten (gilt einmal) |
| `ACCOUNTI_PROTOKOLL_STUFE` / `_FORMAT` | `INFO` … / `text` oder `json` |
| `ACCOUNTI_FINTS_PRODUKT_ID` | Produkt-ID der Installation (FinTS) |
| `ACCOUNTI_SPEICHER` | Speichergrenze der Container `app` und `lauf` (Compose, Standard `1g`) |

Vorrang: ausdrückliche Option → Gesellschaft aus der Registry → Umgebungsvariable →
bisheriger Standard (`sqlite:///accounti.db`, `archiv/belege`, `config/accounti.yaml`).

Ist die globale Konfiguration kaputt (YAML-Syntax, Registry), laufen `accounti version`
und Befehle mit ausdrücklichem `--db` mit einem Hinweis weiter; wer eine Gesellschaft
wählt (`-g`), eine Rechteprüfung braucht (Freigaben, `benutzer …`, `token …`) oder
`serve`, `betrieb lauf`, `sicherung` startet, bekommt den Fehler.

## Mehrere Gesellschaften

Jede eigene Gesellschaft hat eine eigene Datenbank, ein eigenes Belegarchiv und eine eigene
Konfiguration (Kontenrahmen, Wirtschaftsjahr, Firmendaten, Bankkonten, Nummernkreise). Das
Wirtschaftsjahr (`datev.wirtschaftsjahr_beginn`, nur Tag und Monat) gilt für den
Jahresabschluss: `abschluss … --jahr` ist das Kalenderjahr des WJ-Endes (2026 = 01.07.2025–
30.06.2026); `abschluss vortrag` lehnt ein abweichendes Wirtschaftsjahr noch ab (die
Jahressperre gilt je Kalenderjahr) — die Eröffnungssalden jedes folgenden Wirtschaftsjahres
erfasst man je Bestandskonto mit `abschluss eroeffnung --jahr <Folgejahr>`. Die EÜR nimmt den
Vordruck des Jahres des WJ-Beginns. Die Registry steht in der globalen Konfiguration:

```yaml
gesellschaften:
  systemdatenbank: "${ACCOUNTI_SYSTEM_DB}"   # Benutzer, Rollen, Sitzungen, Token
  standard: muster                            # ohne --gesellschaft
  eintraege:
    muster:
      name: Muster GmbH
      datenbank: "${ACCOUNTI_DB_MUSTER}"
      archiv: /arbeit/daten/muster/belege
      konfiguration: /arbeit/config/muster.yaml
    tochter:
      name: Tochter UG
      datenbank: "${ACCOUNTI_DB_TOCHTER}"
      archiv: /arbeit/daten/tochter/belege
      konfiguration: /arbeit/config/tochter.yaml
      regeln: /arbeit/config/tochter-regeln.yaml   # sonst regeln.yaml neben der Konfiguration
```

- Die Registry prüft die Trennung **nach** dem Ersetzen der `${VARIABLEN}` und auf
  normalisierten Werten (`archiv/a` = `./archiv/a`; Datenbank-URLs ohne Treiber,
  Benutzer und Passwort): keine zwei Gesellschaften teilen Datenbank, Archiv,
  Konfiguration oder Regeldatei. Ohne `konfiguration:` gilt die globale Datei — das
  darf höchstens eine Gesellschaft; ohne `regeln:` gilt `regeln.yaml` neben der
  Konfiguration (liegen zwei Konfigurationen im selben Ordner, `regeln:` angeben).
- CLI: `accounti --gesellschaft tochter opos liste` — die Option setzt `--db`, `--archiv` und
  `--config` **aller** Befehle. Ohne Option gilt `standard`; gibt es keinen und mehrere
  Gesellschaften, bricht ein Datenbefehl ab (die Hilfe, z. B. `accounti abschluss --help`,
  kommt ohne). `accounti gesellschaft liste|zeigen`.
  `classify`, `bank lauf` und `opos verbuchen` nutzen die Regeldatei der Gesellschaft (ohne
  Registry wie bisher `config/regeln.yaml`) und davor deren gelernte Regeln; `lerne` und
  `korrigiere --lernen` speichern in die Datenbank der Gesellschaft, nicht in die Datei.
- Browser: Rollen gelten je Gesellschaft (`accounti -g tochter benutzer rolle eva --rolle
  buchhalter`); der Wechsler oben rechts schaltet alle Seiten um. Wer in einer Gesellschaft
  keine Rolle hat, sieht sie nicht.
- **Neue Gesellschaft besetzen:** Hatte eine Gesellschaft noch nie einen aktiven Verwalter
  mit zweitem Faktor (zweite oder später ergänzte Gesellschaft), richtet sie ein Verwalter
  **irgendeiner** Gesellschaft mit seinem Einmalcode ein — `accounti -g tochter benutzer
  rolle chef --rolle verwalter`, oder einen eigenen Verwalter mit `accounti -g tochter
  benutzer anlegen bert --rolle verwalter` und `accounti -g tochter benutzer 2fa bert`. Das
  Protokoll vermerkt `einrichtung_gesellschaft`. Die Einrichtung bestimmt nur den ersten
  Verwalter: Benutzer, die in der Gesellschaft schon eine andere Rolle haben (etwa ein
  Freigeber), verwaltet der fremde Verwalter nicht — Passwort, Codes oder Rollen eines
  solchen Kontos gäben ihm dessen Namen. Sobald die Gesellschaft einen eigenen Verwalter
  mit zweitem Faktor hat, verwalten sie nur noch ihre Verwalter (auch wenn dieser später
  wegfällt — siehe „Letzter Verwalter“ unten).
- API: jedes Token gehört zu einer Gesellschaft (`accounti -g tochter token anlegen …`);
  sein Name ist unter den aktiven Token **dieser** Gesellschaft eindeutig (ein „erp“ je
  Gesellschaft, Migration `6d38d11fc348`).
- Docker: weitere Datenbanken anlegen
  (`docker compose exec db createdb -U accounti tochter`), die URLs in `.env` und unter
  `environment` ergänzen; `lauf` arbeitet alle Gesellschaften der Registry ab.
- Grenze: Die Abschnitte `bank` (FinTS-Produkt-ID, Kreditkarten-Muster) gelten für die
  Installation; `import banken` liest `config/banken.yaml` relativ zum
  Arbeitsverzeichnis.
- Grenze — Kontenrahmen: `buchhaltung.kontenrahmen` gilt je Gesellschaft für USt,
  Abschluss, Anlagen, Prüfregeln und DATEV; die Standardkonten daneben (`bank_konto`
  1200, `standard_aufwand` 4900, Skonto 3736/3731/3730 und 8736/8731/8730) sind aber
  SKR03 und wechseln nicht mit. Bei SKR04 in der Konfiguration setzen: 1800, 6300,
  5736/5731/5730 und 4736/4731/4730 (Vorlage `config/accounti.example.yaml`). Bewusst kein
  automatischer Wechsel: Eine SKR04-Gesellschaft, die bisher mit den Standards buchte, hat
  ihre Bankbuchungen auf 1200 — ein stiller Wechsel auf 1800 teilte Bestand und
  Bank-Abstimmung mitten im Jahr. Die Verfahrensdokumentation zeigt die verwendeten
  Konten.

## Benutzer, Rollen, Anmeldung

| Rolle | darf |
|-------|------|
| `betrachter` | lesen |
| `buchhalter` | lesen, buchen/prüfen/korrigieren, Belege einliefern, Läufe starten, Buchungen freigeben |
| `freigeber` | lesen, Buchungen, **Zahlungsläufe** und **Steuermeldungen** freigeben |
| `verwalter` | lesen, Benutzer, Token und Einstellungen verwalten |

Rollen sind nicht hierarchisch, ein Benutzer kann mehrere haben. Sobald Benutzer
eingerichtet sind, legt `zahlung anlegen` nur an, wer buchen darf (`buchhalter`, mit
Einmalcode — angelegt hat dann der Benutzer, nicht ein Freitext), und **wer einen
Zahlungslauf angelegt hat, gibt ihn nicht frei** — in der CLI immer, im Browser, solange
die Konfiguration der Gesellschaft nicht `zahlung.ersteller_darf_freigeben: true` sagt
(nur für Ein-Personen-Betriebe; in der CLI gilt der Schalter nicht, weil die Datei dort
frei wählbar ist). Mit `zahlung.vier_augen: true` braucht die Freigabe zusätzlich zwei
verschiedene Freigeber. Grenze: `vier_augen` steht in der Konfiguration der
Gesellschaft — wer die CLI mit einer eigenen `ACCOUNTI_KONFIG` (auch einer eigenen
Registry) aufruft, kann die Vier-Augen-Pflicht dort abschalten; der eigene Einmalcode
bleibt Pflicht, und das Protokoll zeigt, wer allein freigab. `zahlung entfernen`,
`sperre`, `iban-klaeren` (die Betrugskontrolle) und `abgleichen` verlangen das Recht
buchen, `zahlung stornieren` und `sepa` (die SEPA-Datei ist der Zahlungsauftrag an die
Bank) das Recht zur Zahlungsfreigabe — jeweils mit Einmalcode; ins Protokoll und
geprüft ins Journal kommt der Benutzer, nicht der Freitext aus `--von`.

Buchungen (Baustein 7), jeweils mit Einmalcode (vollständige Liste: `FREIGABEWEGE` in
`models/auth.py`, auch in der Verfahrensdokumentation):

- **buchen** (`buchhalter`): `korrigiere`, `buchung storniere`, `kasse
  buchen|anfangsbestand|storno`, `abschluss eroeffnung` (die EB-Ausnahme der
  Monatssperre), `abschluss saldo` (Saldo laut Kontoauszug für die Bank-Abstimmung),
  `anlagen anlegen|afa|abgang` (ein Abgang scheidet das Anlagegut unwiderruflich aus),
  `abschluss buchen` (derselbe AfA-Lauf wie `anlagen afa`, dazu die
  Abgrenzungsvorschläge) und `abschluss abgrenzen` (Person aus `ACCOUNTI_BENUTZER` bzw.
  dem Anmeldenamen — `--von` ist dort der Leistungszeitraum),
  `bank bestaetigen|ablehnen`, `nachfordern anfrage --senden`, `belege freigeben` (Beleg
  aus der Prüfung, mit Belegart, Steuerfall, Belegnummer oder umgekehrtem Vorzeichen;
  `--grund` Pflicht bei Dublettenverdacht, Rechenprobe, Vorzeichen und mehrdeutigem
  Titel). Wer erfasst
  und korrigiert, legt dabei freigegebene Buchungen an — das Recht zu buchen schließt laut
  Rollen das Freigeben ein (ein Test hält das fest).
- **Buchungen freigeben** (`buchhalter`, `freigeber`): `bestaetige`, `opos
  bestaetigen|ablehnen|verrechnen`, `opos zuordnen --transaktion` (Handzuordnung),
  `abschluss bestaetigen|ablehnen`, `periode schliessen`,
  `abschluss vortrag`, `export datev` und `datev belege` (Übergabe an den Steuerberater,
  Vermerk „exportiert“), `datev kontoauszuege` (schreibt die Auszüge fest).
- **Steuermeldungen freigeben** (`freigeber`): `periode oeffnen`, `abschluss oeffnen` —
  die Festschreibung aufheben ist Funktionstrennung (GoBD Rz. 100–102), meist folgt eine
  berichtigte Voranmeldung; accounti nennt beim Öffnen schon freigegebene oder
  abgegebene Voranmeldungen des Zeitraums. Grund ist Pflicht.
- **verwalten** (`verwalter`): `journal uebernehmen` (nur auf dem Upgrade-Weg, unten).

Im Journal, in `geprueft_von` und in den Protokollen steht der Benutzer; was ein
API-Token anstößt, steht als „API-Token <Name>“ im Journal. Nicht an eine Rolle gebunden
sind Lesebefehle und maschinelle Läufe und Importe (`classify`, `opos verbuchen`, `opos
zuordnen`, `bank abgleich`, `bank lauf`, `aufgaben lauf`, `import`, `belege import`,
`verfahrensdoku`) — dort steht im Journal `ACCOUNTI_BENUTZER` bzw. der Anmeldename mit dem
Zusatz „(ungeprüft)“, sobald die Datenbank zu einer Benutzerverwaltung gehört.

- **Anmeldung im Browser** nur mit Passwort **und** Einmalcode (TOTP-App nach RFC 6238 oder
  ein Wiederherstellungscode, der genau einmal gilt). Jeder Code gilt einmal. Passwörter:
  mindestens 12 Zeichen, keine Zusammensetzungsregeln, scrypt (N = 2^17). Jeder Weg
  kostet genau eine Passwort-Prüfung — die Antwortzeit verrät nicht, ob das Passwort
  stimmte (Wiederherstellungscodes liegen als HMAC mit dem Tresor-Schlüssel vor).
- **Sperre:** Jeder Versuch wird vor der Prüfung in der Datenbank gezählt, auch bei
  gleichzeitigen Versuchen. Nach 5 Fehlversuchen ist das Konto 15 Minuten gesperrt, danach
  gibt es wieder 5 Versuche; der Zähler läuft über die Sperren hinweg, ab 100
  Fehlversuchen in Folge bleibt es bis zum Entsperren gesperrt (NIST 800-63B-4: höchstens
  100). Browser und Server-Shell **zählen getrennt**: Fehlversuche aus dem Netz sperren
  die Anmeldung im Browser (und Freigaben dort), nie den Einmalcode in der CLI. Im Browser
  gelten `auth.sperre_nach_fehlversuchen`, `auth.sperre_minuten` (höchstens 1440) und
  `auth.fehlversuche_obergrenze` aus der Konfiguration von `accounti serve`; die CLI
  zählt immer mit 5 / 15 Minuten / 100 — eine eigene `--config` setzt dort keine
  Sperrwerte. Eine Sperre durch Fehlversuche beendet **keine** offenen Sitzungen (sonst
  könnte jeder, der einen Namen kennt, den Freigeber hinauswerfen) — wer jemanden wirklich
  aussperren will, nimmt `accounti benutzer sperren`.
- **Rückweg nach einer Sperre:** Auf der Server-Shell entsperrt sich jeder selbst mit
  seinem zweiten Faktor,
  `ACCOUNTI_BENUTZER=chef accounti benutzer entsperren chef` (Einmalcode wird abgefragt;
  in Docker `docker compose exec -e ACCOUNTI_BENUTZER=chef app accounti benutzer
  entsperren chef`). Andere entsperrt ein Verwalter — damit auch eine Sperre des
  Einmalcodes in der CLI. Ein mit `benutzer sperren` stillgelegtes Konto öffnet nur ein
  Verwalter wieder (wer es selbst versucht, bekommt diese Meldung und Exit 1). Gesperrte Verwalter zählen weiter
  als Verwalter — eine Flut aus dem Netz öffnet keine Einrichtungsphase.
- **Letzter Verwalter:** `benutzer sperren` und `benutzer rolle NAME --rolle verwalter
  --entfernen` lehnen ab, wenn NAME in einer Gesellschaft der letzte aktive Verwalter mit
  zweitem Faktor ist (Exit 1, nichts geändert) — erst einen weiteren einrichten. Früher
  öffnete das die Einrichtungsphase: jeder an der Shell legte ohne Code einen Verwalter
  an. Eine Gesellschaft, die einmal einen Verwalter mit zweitem Faktor hatte (Merker
  `verwaltet:<Kürzel>` in `auth_merker` der Systemdatenbank), öffnet ihre
  Einrichtungsphase nie wieder, auch wenn der Verwalter an accounti vorbei wegfällt; dann
  bleibt nur die Datenbank: `UPDATE auth_benutzer SET aktiv = true WHERE name = 'chef'`. Ist auch der
  Einmalcode in der CLI gesperrt (100 falsche Codes auf der Shell) und kein anderer
  Verwalter da, bleibt nur die Datenbank:
  `UPDATE auth_benutzer SET fehlversuche = 0, gesperrt_bis = NULL, cli_fehlversuche = 0,
  cli_gesperrt_bis = NULL WHERE name = 'chef'`. Grenze: Wer den Namen kennt, kann neue
  Anmeldungen im Browser je 15 Minuten und nach 100 Versuchen bis zum Entsperren
  blockieren; eine Begrenzung je IP gehört in den Proxy (z. B. `limit_req` für
  `/anmelden`).
- **Sitzungen:** Cookie `__Host-accounti_sitzung` (Secure, HttpOnly, SameSite=Strict),
  30 Minuten Leerlauf, höchstens 8 Stunden; Abmelden, Passwortwechsel, `benutzer sperren`,
  Rollenänderung und ein neuer zweiter Faktor beenden sie serverseitig. Freigaben mit
  Außenwirkung und endgültige Korrekturen verlangen im Browser zusätzlich einen frischen
  Einmalcode: Zahlungsläufe und USt-VA (gelten nur für den angezeigten Inhalt — Empfänger,
  IBAN, Betrag, Verwendungszweck; hat sich der Entwurf seitdem geändert, 409) sowie Storno
  und Korrektur freigegebener Buchungen (`/buchungen/…`). Vorschläge in der
  Supervisions-Queue (`/pruefen`) entscheidet die angemeldete Sitzung ohne weiteren Code —
  sie ist mit Passwort und zweitem Faktor entstanden und läuft nach 30 Minuten Leerlauf ab;
  in der CLI verlangen dieselben Befehle den Einmalcode, weil sie keine Sitzung hat.
- **Mein Konto:** Jeder Benutzer wählt unter `/konto` Sprache, Darstellung (automatisch, hell,
  dunkel), Fachansicht, ob die Übersicht Beträge verbirgt und ob Tastenkürzel gelten. Die Werte
  liegen in der Systemdatenbank am Benutzer und gelten auf jedem Gerät; ohne Anmeldung gilt
  „automatisch“. Die Hilfe (`/hilfe`) ist ohne Anmeldung erreichbar und enthält keine Daten.
- **CLI:** Ohne eingerichtete Benutzer prüft accounti nichts. Mit Benutzern verlangen
  `zahlung freigeben`, `ustva freigeben`, `ustva dauerfrist --freigeben` (Rolle
  `freigeber`), `zahlung anlegen` (`buchhalter`) und `anlagen freigeben`
  (Buchungsfreigabe) den Einmalcode der handelnden Person (`--von` bzw.
  `ACCOUNTI_BENUTZER`, mit Vier-Augen der Anmeldename); ebenso `zahlung entfernen`,
  `sperre`, `iban-klaeren`, `abgleichen`, `sepa` und `stornieren` sowie die Befehle aus
  Baustein 7 (siehe oben). `buchung storniere`, `korrigiere`, `lerne`, `bestaetige`,
  `regeln deaktivieren`, `regeln uebernehmen`, `kasse anfangsbestand/buchen/storno`,
  `periode schliessen/oeffnen`, `ustva freigeben`, `zahlung freigeben` und `belege
  freigeben` führen die Aktion nach der Rechteprüfung zuerst zur Probe aus (zurückgerollt)
  und bestätigen den Code erst danach — ein fachlicher Fehler (Storno-Datum vor der Buchung,
  Soll = Haben, ungültiges Muster, Prüfregel, unbekannte Regel, kaputte Regeldatei, Kasse im
  Minus, Monat schon festgeschrieben, Zeitraum unverständlich, USt-VA gesperrt, unbekannter
  Zahlungslauf oder Beleg) verbraucht ihn nicht, wie im Browser (dort auch bei der Freigabe
  von Zahlungslauf und USt-VA); ein `regeln uebernehmen`, das nichts übernähme, endet vor dem
  Code. Die übrigen Befehle prüfen nach dem Code (siehe Grenzen im Plan).
  Der Einmalcode lässt sich in
  der CLI nicht abschalten: `auth`-Werte aus `--config`/`ACCOUNTI_KONFIG` wirken dort
  höchstens strenger als der Standard (`einmalcode_bestaetigung: false` gilt nur im
  Browser), Sperrwerte gar nicht.
- **Bindung an Gesellschaft und Systemdatenbank:** Mit Registry gelten für Freigaben
  Datenbank und Konfiguration der gewählten Gesellschaft — ein abweichendes `--db` oder
  `--config` wird abgewiesen. Jede Gesellschafts-Datenbank trägt einen Merker
  (`auth_merker`, Schlüssel `benutzerverwaltung`), zu welcher Systemdatenbank und
  Gesellschaft sie gehört; `benutzer anlegen` setzt ihn für alle Gesellschaften der
  Registry, `benutzer rolle` und jede Prüfung für die gewählte. Zeigt
  `ACCOUNTI_SYSTEM_DB` (oder eine andere Registry) auf eine leere oder fremde
  Systemdatenbank, bricht die Prüfung ab, statt zu entfallen. Wer eine Gesellschaft
  bewusst einer neuen Benutzerverwaltung zuordnet (z. B. nach Verlust der
  Systemdatenbank), löscht den Merker in deren Datenbank von Hand
  (`DELETE FROM auth_merker WHERE schluessel = 'benutzerverwaltung'`) — ein Eingriff,
  der Zugang zur Datenbank voraussetzt. `sicherung wiederherstellen
  --fremde-gesellschaft` setzt die Bindung selbst neu (an das Ziel).
- **Grenzen des Merkers:**
  - *Trust on first use:* Eine Gesellschaft, die noch nie gebunden wurde (kein `benutzer
    anlegen`, noch keine Prüfung), bindet die erste Prüfung — auch eine mit fremder
    Registry oder leerer `ACCOUNTI_SYSTEM_DB`. Danach fällt der Fehler auf, weil die
    echte Prüfung abbricht. Deshalb den ersten Verwalter gleich nach dem Einrichten
    der Registry anlegen.
  - Der Merker hält die **Kennung** der Systemdatenbank fest, nicht ihren Ort: eine
    **Kopie** (oder ältere Sicherung) der Systemdatenbank besteht die Prüfung. Wer sie
    lesen kann, kann darin Rollen ändern und mit seinem eigenen zweiten Faktor freigeben;
    der Einmalcode wird dann nur in der Kopie verbraucht, das Ereignis fehlt im echten
    Protokoll. Das setzt Lesezugriff auf die Systemdatenbank voraus — sie gehört so
    geschützt wie die Gesellschafts-Datenbanken.
  - Der **Browser** prüft den Merker nicht: welche Systemdatenbank er nutzt, legt der
    Betreiber beim Start von `accounti serve` fest (Registry bzw. `ACCOUNTI_SYSTEM_DB`).
- **Verwaltung:** `benutzer 2fa|codes|passwort|sperren|entsperren|rolle` für ein fremdes
  Konto darf nur, wer in **jeder** Gesellschaft Verwalter ist, in der dieses Konto Rollen
  hat (Passwort und zweiter Faktor gelten für alle Gesellschaften). `token liste` und
  `token widerrufen` wirken nur in der gewählten Gesellschaft.
- Die CLI läuft auf dem Server: wer sie aufrufen kann, kommt meist auch an die
  Datenbank — die Prüfung bindet Freigaben an eine Person und fängt Versehen und
  einfache Umwege ab, sie ersetzt keine Zugriffskontrolle auf den Server.
- Protokoll: `accounti benutzer protokoll [--anzahl 50]` (die neuesten Anmeldungen,
  Fehlversuche, Sperren, Rollen, Token; nur anfügen). Mit mehreren Gesellschaften zeigt
  es die Ereignisse der Gesellschaften, in denen der Aufrufer Verwalter ist (dazu die
  gewählte, wenn er sie gerade einrichtet), und die ohne Gesellschaft (z. B. ein neuer
  Benutzer, Sperren, Passwort, Codes) — diese nur über Benutzer, die in einer dieser
  Gesellschaften eine Rolle haben (oder gar keine). Ein Verwalter von b sieht so nicht,
  was in a geschah; über Benutzer mit Rollen in a **und** b sieht er auch, was sie in a
  betrifft, soweit es keiner Gesellschaft zugeordnet ist (Passwort und zweiter Faktor
  gelten global).

## REST-API

```bash
accounti token anlegen erp --recht opos:lesen --recht belege:schreiben --gueltig-bis 2027-12-31
curl -H "Authorization: Bearer accounti_api_…" https://accounti.example.de/api/v1/offene-posten
curl -H "Authorization: Bearer accounti_api_…" -H "X-Dateiname: re-77.pdf" \
     --data-binary @re-77.pdf https://accounti.example.de/api/v1/belege
```

| Endpunkt | Recht | |
|----------|-------|---|
| `GET /api/v1/ich` | jedes gültige Token | Name, Gesellschaft, Rechte |
| `GET /api/v1/offene-posten?richtung=&faellig_bis=` | `opos:lesen` | Beträge als Zeichenkette |
| `GET /api/v1/buchungen?von=&bis=&status=` | `buchungen:lesen` | |
| `POST /api/v1/belege` | `belege:schreiben` | Rohdaten, Multipart oder JSON/Base64, wie der Webhook |
| `POST /api/v1/laeufe/bank` | `laeufe:starten` | `bank lauf` ohne LLM |
| `POST /api/v1/laeufe/aufgaben` | `laeufe:starten` | Prüfläufe und Erinnerungen |

Token werden nur als SHA-256 gespeichert und einmal angezeigt; ohne gültiges Token 401, ohne
Recht 403 (`WWW-Authenticate: Bearer error="insufficient_scope"`). Freigeben kann kein Token.
Je Gesellschaft läuft `bank lauf` bzw. `aufgaben lauf` höchstens einmal zugleich — über
API, Dienst `lauf` und CLI hinweg (PostgreSQL: Advisory-Lock; SQLite: Dateisperre neben
der Datenbank, `*.lauf-bank.sperre`); ein zweiter Lauf wartet nicht (API 409, CLI Exit 1).
Dieselbe Sperre halten die Einzelschritte der Bankkette (`bank abrufen`, `fints
freigeben`, `kreditkarte abgleich`, `opos zuordnen`, `bank abgleich`, `classify`) — ein
`classify` neben dem geplanten Lauf kontiert denselben Umsatz nicht doppelt —, dazu
`opos verbuchen` (bucht dieselben Belege) und `periode schliessen` (nicht festschreiben,
während ein Lauf in den Monat bucht); `nachfordern` hält die Sperre von `aufgaben lauf`. Die
Sperrdateien (`*.lauf-*.sperre`) stehen in `.gitignore`.

## Reverse-Proxy mit TLS

accounti spricht selbst nur HTTP auf `127.0.0.1`. Davor gehört ein Proxy mit TLS; nur dessen
Adresse steht in `server.vertrauenswuerdige_proxies` (Standard `127.0.0.1`). Im Container ist
das die Adresse des Docker-Netzes bzw. des Proxys — sonst gelten `X-Forwarded-*` nicht.
Ohne TLS (nur zum Ausprobieren auf dem eigenen Rechner) `server.cookie_sicher: false`.

**Caddy** (holt das Zertifikat selbst):

```caddyfile
accounti.example.de {
    encode gzip
    header Strict-Transport-Security "max-age=31536000; includeSubDomains"
    request_body {
        max_size 25MB
    }
    reverse_proxy 127.0.0.1:8400
}
```

**nginx:**

```nginx
# im http-Block: Anmeldeversuche je Adresse bremsen (die Kontosperre zählt je Konto)
limit_req_zone $binary_remote_addr zone=anmelden:10m rate=10r/m;

server {
    listen 443 ssl;
    http2 on;
    server_name accounti.example.de;
    ssl_certificate     /etc/letsencrypt/live/accounti.example.de/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/accounti.example.de/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    client_max_body_size 25m;
    access_log off;            # accounti protokolliert selbst ohne IP und Abfrage
    location = /anmelden {
        limit_req zone=anmelden burst=5 nodelay;
        proxy_pass http://127.0.0.1:8400;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
    location / {
        proxy_pass http://127.0.0.1:8400;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
server { listen 80; server_name accounti.example.de; return 301 https://$host$request_uri; }
```

Die Anwendung muss unter `/` liegen (das Cookie-Präfix `__Host-` verlangt `Path=/`). Die
Anmeldung bremst Raten über die Kontosperre; eine Begrenzung je IP gehört in den Proxy
(z. B. `limit_req` für `/anmelden`).

Zusätzlich die Länge der Anfragezeile im Proxy begrenzen: accounti braucht nur kurze Pfade.
uvicorn (h11) begrenzt nur, was von einer Anfrage noch unvollständig im Puffer liegt (16 KB);
kommt sie in einem Stück an, nimmt er auch 40 000 Zeichen und mehr an (über `localhost`
gemessen). accounti kürzt lange Pfade im Zugriffsprotokoll selbst (höchstens 200 Zeichen),
schwärzt in linearer Zeit und rechnet Pfad und Kopfzeilen jeder Anfrage linear — bis Runde 8
hielt ein unangemeldetes `GET /statisch/<15 000 Zeichen>` den Server mehrere Sekunden an,
bis zur Nachprüfung des Folgepakets F ein `POST` (auch `PUT`, `DELETE` …) auf einen Pfad
mit vielen „/“ (40 000 Zeichen: 3,7 s) bzw. ein `Accept-Language` mit langer
Leerraumfolge. Bei nginx z. B. `large_client_header_buffers 4 4k;` im `server`-Block
(längere Anfragezeilen enden mit 414; Standard 8k), bei Caddy die globale Option
`servers { max_header_size 16KB }`.

## Sicherung und Wiederherstellung

```bash
accounti sicherung schluessel                                 # einmal: Schlüssel erzeugen
accounti sicherung erstellen --ziel /sicherungen/             # Datenbank + Belegarchiv
accounti sicherung erstellen --system --ziel /sicherungen/    # Systemdatenbank (mehrere Gesellschaften)
accounti sicherung pruefen /sicherungen/accounti-standard-20261020-030000.sicherung
accounti sicherung wiederherstellen DATEI --db postgresql+psycopg://…/leer --archiv /leer/belege
```

- Eine Datei enthält alle Tabellen (typgetreu, über SQLAlchemy — SQLite und PostgreSQL in
  beide Richtungen) und alle Dateien des Belegarchivs, verschlüsselt mit AES-256-GCM in
  Stücken; der Schlüssel jeder Sicherung wird per HKDF aus `ACCOUNTI_SICHERUNG_SCHLUESSEL`
  abgeleitet. Ein Manifest hält Zeilenzahl und SHA-256 je Tabelle und Datei fest; Sitzungen
  werden nicht gesichert. Die Datei hat die Rechte 0600 und wird nie überschrieben;
  Dateinamen sind auch in derselben Sekunde eindeutig (`…-2.sicherung`).
- **Im laufenden Betrieb:** alle Tabellen werden in einer Lese-Transaktion gelesen
  (PostgreSQL `REPEATABLE READ READ ONLY`) — die Sicherung ist ein Stand, auch wenn `app`
  und `lauf` gerade schreiben. Eine SQLite-Datei kopiert accounti zuerst mit der
  Backup-API von SQLite in eine Zwischendatei und liest aus der Kopie — Schreiber warten
  nur, solange die Seiten kopiert werden. Die Kopie liegt **neben der Datenbank**
  (`.accounti-sicherung-*.db`, Rechte 0600, danach gelöscht; dort braucht es so viel
  freien Platz wie die Datenbank groß ist), große Tabellen werden neben der Sicherung
  ausgelagert — beides nicht im Temporärordner, der im Container im Speicher liegt, und
  keine unverschlüsselte Kopie im Sicherungsordner (oft ein entferntes Laufwerk). Bricht
  der Prozess hart ab (z. B. `kill -9`), kann neben der Datenbank eine Kopie liegen
  bleiben: löschen.
- **Nur aus einer echten Datenbank:** Gibt es die SQLite-Datei nicht (relativer Pfad aus
  einem anderen Arbeitsverzeichnis, Tippfehler), bricht `erstellen` ab und legt nichts
  an; ebenso, wenn die Datenbank keine Tabellen von accounti hat.
- **Datenbank und Archiv passen zusammen:** fehlt das Archiv oder ist es leer, obwohl
  Belege darauf verweisen (z. B. Cron aus einem anderen Arbeitsverzeichnis, falsches
  `--archiv`), bricht `erstellen` ab. Fehlen einzelne Dateien, nennt die Ausgabe ihre
  Zahl und das Manifest ihre Hashes (`fehlende_archivdateien`).
- **Den Schlüssel getrennt von den Sicherungen aufbewahren** (Passwortmanager, Tresor):
  ohne ihn ist keine Sicherung lesbar, mit ihm und der Datei alles.
- Wiederhergestellt wird nur in eine **leere** Datenbank und ein leeres Archiv, in einer
  Transaktion: erst wenn alles zum Manifest passt, wird festgeschrieben; sonst bleibt nichts
  zurück. Hash-Ketten der Protokolle und des Journals bleiben gültig: Die Zeilen kommen
  über die Verbindung zurück (an den ORM-Sperren vorbei), die SQLite-Trigger von `journal`
  und `buchungskorrekturen` nehmen Einfügen an und wirken danach weiter; `accounti journal
  pruefen` ist nach dem Zurückspielen in Ordnung (auch mit dem notierten `--kopf`).
- Wiederhergestellt wird nur, was zum Ziel passt: eine Sicherung der Gesellschaft a nicht
  in b (`--fremde-gesellschaft` übernimmt bewusst), eine Sicherung der Systemdatenbank
  nur mit `--system` (Ziel: `--db`, sonst die Systemdatenbank der Registry bzw.
  `ACCOUNTI_SYSTEM_DB`). Das Archiv kommt vor dem Festschreiben an seinen Platz; scheitert
  etwas, bleiben Datenbank und Archiv leer.
- Mehrere Gesellschaften: je Gesellschaft `accounti -g K sicherung erstellen …`, dazu die
  Systemdatenbank `accounti sicherung erstellen --system …` (ohne Gesellschaft, Datei
  `accounti-system-<Zeit>.sicherung`).
- Eine **ältere** Sicherung der Systemdatenbank bringt den Stand von damals zurück:
  inzwischen widerrufene Token gelten wieder, verbrauchte Wiederherstellungscodes und alte
  Passwörter auch, gesperrte Benutzer sind wieder aktiv, entzogene Rollen wieder da. Nach
  dem Zurückspielen `accounti benutzer liste` und `accounti token liste` prüfen, nicht
  mehr gewollte Token widerrufen, Benutzer sperren bzw. Rollen entziehen und betroffenen
  Benutzern neue Codes geben (`benutzer codes`). Die Merker der Gesellschaften stehen in ihren Datenbanken: wer nur
  eine Gesellschaft zurückspielt, braucht die passende Systemdatenbank (sonst brechen
  Freigaben ab, siehe Bindung oben).
- `sicherung erstellen` prüft keine Rolle (läuft per Cron, ohne Einmalcode); die Datei
  enthält Passwort-Hashes und verschlüsselte TOTP-Geheimnisse — Sicherungsschlüssel und
  Dateien so schützen wie die Datenbank selbst.
- In Docker:
  `docker compose exec app accounti sicherung erstellen --ziel /arbeit/daten/sicherungen/`
  und die Datei vom Server weg kopieren (z. B. per `restic`/`borg` — die Datei ist schon
  verschlüsselt).

### Wiederherstellungstest (jedes Quartal und nach jedem Update)

Eine Sicherung zählt erst, wenn sie sich zurückspielen lässt:

```bash
mkdir -p /tmp/probe
P=sqlite:////tmp/probe/x.db
accounti sicherung pruefen DATEI
accounti -g K sicherung wiederherstellen DATEI --db $P --archiv /tmp/probe/belege
accounti -g K opos liste --db $P                       # mit dem Original vergleichen
accounti -g K journal pruefen --db $P --kopf NR:HASH   # Kopf vom Original
accounti -g K abschluss susa --jahr 2026 --db $P       # Stichprobe Buchungen (Salden)
accounti -g K journal --db $P --von 2026-10-01         # Stichprobe Journal
rm -rf /tmp/probe
```

`-g K` ist die Gesellschaft der Sicherung (Dateiname `accounti-K-<Datum>-<Uhrzeit>.sicherung`;
ohne Registry entfällt `-g`). Als Stichprobe nur Befehle, die lesen: `export datev` lehnt
mit eingerichteten Benutzern eine abweichende `--db` ab (Bindung an die Gesellschaft) und
schriebe sonst den Vermerk „exportiert“ und einen Journaleintrag in die Probe. Die
Systemdatenbank übt man mit `accounti sicherung wiederherstellen DATEI --system --db
sqlite:////tmp/probe/system.db`.

Ergebnis (Datum, Datei, Zahlen aus `pruefen`) im Betriebsprotokoll festhalten. Der Test
`tests/test_betrieb_sicherung.py::test_akzeptanz_7_wiederherstellung_in_leere_umgebung`
vergleicht nach dem Zurückspielen jede Tabelle Zeile für Zeile und jede Archivdatei
bytegleich.

## Aufbewahrung und Löschkonzept

Stand 20.10.2026 — § 147 AO in der Fassung des BEG IV (verkündet am 29.10.2024, BGBl. 2024
I Nr. 323, ab 01.01.2025), Art. 97 § 19a EGAO, § 14b UStG:

| Unterlagen in accounti | Frist | Grundlage |
|------------------------|-------|-----------|
| Buchungen (`buchungssaetze`), Journal, Buchungskorrekturen, Monatsabschlüsse, Kassenbuch, Protokolle (USt-IdNr., Übermittlung, Zahlungslauf, Abschluss), Jahresabschluss | **10 Jahre** ab Schluss des Jahres der letzten Eintragung je Wirtschaftsjahr | § 147 Abs. 1 Nr. 1, Abs. 3, Abs. 4 AO |
| Belege (`belege`, Belegarchiv) als Buchungsbelege | **8 Jahre** | § 147 Abs. 1 Nr. 4, Abs. 3 AO |
| Rechnungen (Ein- und Ausgang) | **8 Jahre** | § 14b Abs. 1 UStG |
| Handels- und Geschäftsbriefe, sonstige Unterlagen | **6 Jahre** | § 147 Abs. 1 Nr. 2, 3, 5 AO |
| Kreditinstitute, Versicherungen, Wertpapierinstitute: Buchungsbelege | **10 Jahre** (dauerhaft) | Art. 97 § 19a Abs. 3 EGAO i. d. F. vom 22.12.2025 (BGBl. 2025 I Nr. 369) |

- Die Frist beginnt mit dem Schluss des Kalenderjahres, in dem die Unterlage entstand —
  für Bücher und Aufzeichnungen mit dem Schluss des Kalenderjahres, in dem die **letzte
  Eintragung** gemacht wurde, für Jahresabschlüsse mit dem der Aufstellung (§ 147 Abs. 4
  AO). accounti rechnet Bücher je Wirtschaftsjahr (`datev.wirtschaftsjahr_beginn`):
  Beginn frühestens mit dem Schluss des Jahres **nach** dem Wirtschaftsjahresende
  (Abschlussbuchungen fallen ins Folgejahr), später, wenn der Abschluss (`abschluesse`)
  oder ein Monat des Wirtschaftsjahres (`periodenabschluesse`) später festgeschrieben
  wurde. Ein Beispiel: Buchungen des Kalenderjahres 2015 mit Abschluss 2016 —
  aufzubewahren bis 31.12.2026, nicht bis 31.12.2025. Wann eine Buchung eingetragen wurde,
  steht seit Baustein 7 im Journal; der Bericht wertet das nicht aus — wer ein
  Wirtschaftsjahr mehr als ein Jahr nach seinem Ende noch bebucht hat, ohne es oder seine
  Monate festzuschreiben, prüft die Frist von Hand (`accounti journal --von …`). Ein
  **wieder geöffnetes** Geschäftsjahr (`abschluesse.gesperrt` falsch) läuft nicht ab — es
  kann noch bebucht werden; ebenso ein wieder geöffneter Monat, solange sein Jahr nicht
  abgeschlossen ist. Das Journal ist eine Hash-Kette: Wer alte Einträge aussondert, prüft
  danach mit einem Anker ab dem verbliebenen Anfang (`journal pruefen --kopf`). Die 8 Jahre
  gelten für alle Belege, deren alte Frist am 31.12.2024 noch lief; ein Bericht mit
  `--stichtag` vor dem 01.01.2025 rechnet Belege nach altem Recht mit 10 Jahren.
- Sie läuft nicht ab, solange die Unterlagen für eine Steuer von Bedeutung sind, deren
  Festsetzungsfrist noch läuft — etwa bei Außenprüfung, Einspruch, vorläufiger Festsetzung
  (§ 147 Abs. 3 Satz 3 AO). Handelsrechtlich gilt § 257 HGB entsprechend.
- **accounti löscht nichts von selbst.** `accounti betrieb aufbewahrung [--stichtag]
  [--institut]` zeigt je Bestand, was frühestens ausgesondert werden **dürfte** (das
  Wirtschaftsjahr aus `--config` bzw. der Gesellschaft). Das
  Belegarchiv hat bewusst keinen Löschpfad; Buchungen und Protokolle sind unveränderbar.
  `belege.aufbewahren_bis` kommt aus derselben Quelle (`betrieb/aufbewahrung.py`):
  Buchungsbelege und Rechnungen 8 Jahre ab Schluss des Jahres des **Belegdatums** (ohne
  erkanntes Belegdatum des Eingangs; ein erkanntes Belegdatum vor dem Vorjahr des Eingangs
  gilt als möglicher Lesefehler und verkürzt die Frist nicht — dann ab Eingang),
  Übermittlungs- und USt-IdNr.-Protokolle als
  Aufzeichnungen 10 Jahre. Belege, die vor dieser Umstellung angelegt wurden, tragen noch
  10 Jahre ab Eingang — länger aufzubewahren ist zulässig. Der Bericht zählt Belege
  vorsichtig ab dem Eingang (nie früher aussonderbar als nach dem Belegdatum).
- Personenbezogene Daten (Kontakte, Belege, Benutzer) dürfen während der gesetzlichen
  Aufbewahrung nicht gelöscht werden (Art. 17 Abs. 3 lit. b DSGVO); danach entscheidet der
  Verantwortliche über das Aussondern. Ein protokolliertes Aussondern ist noch nicht
  umgesetzt — bis dahin bleibt der Bestand vollständig.
- Sicherungen fallen unter dieselben Fristen; alte Sicherungen nach Ablauf der längsten
  enthaltenen Frist vernichten (Rotation im Sicherungswerkzeug).

## Protokollierung

- Das Zugriffsprotokoll schreibt Methode, die **Vorlage** der Route (z. B.
  `/freigaben/zahlungslauf/{nr}`, ohne IDs und ohne Abfrage), Status und Dauer — keine
  IP-Adresse, keinen Benutzer. Pfade ohne Route stehen dort als `(unbekannt)`: ein Name
  oder ein `%0A` im Pfad kann so keine Zeile ins Protokoll schreiben. Das Protokoll von
  Uvicorn ist aus, HTTP-Bibliotheken schreiben erst ab Warnung (ihre Adressen tragen oft
  Token).
- Unbehandelte Ausnahmen der App protokollieren nur ihre Art (z. B. `IntegrityError`) —
  keinen Traceback, keine Meldung; Datenbank-Engines verbergen die SQL-Parameter
  (`hide_parameters`), Belegtexte und Namen erscheinen auch in Fehlermeldungen nicht.
- Ein Filter an jedem Handler schwärzt IBAN, E-Mail-Adressen, accounti- und Bearer-Token,
  verbreitete Zugangstoken (GitHub, GitLab, Slack), Benutzer und Passwort in URLs (auch eine
  vom Zeilenumbruch zerschnittene Adresse), Parameter wie `passwort=`, `token=`, `code=`,
  „Passwort: …“ sowie PIN und TAN als Zahl — auch in Stacktraces. Zwischen Schlüsselwort
  und Wert darf innerhalb einer Zeile beliebig viel Leerraum stehen (geprüft in linearer
  Zeit); über einen Zeilenumbruch hinweg nur, solange keine der beiden Zeilen gekürzt wird
  (Grenze: „PIN“, Tausende Leerzeichen und der Wert erst in der nächsten Zeile — die Kürzung
  trennt sie, der Wert bleibt stehen). Eine Zeile über 4000 Zeichen kürzt er vorher auf
  Anfang und Ende (je höchstens 1500 Zeichen, geschnitten an Leerraum), jede Zeile für
  sich. Jedes Stück schwärzt er zuvor mit 250 Zeichen über die Schnittkante hinaus
  (das Ende auch über einen Abstand hinweg, in dem diese 250 Zeichen beginnen): Ein
  Geheimnis, das an der Kante beginnt, steht vorn geschwärzt da und fällt hinten ganz weg;
  ein Wert hinter der Kante verliert sein Schlüsselwort nicht. (Die Fassung vor dem
  Folgepaket F schwärzte erst nach dem Schnitt —
  die hintere Kante konnte „Bearer“, „passwort:“, „PIN“ oder „TAN“ von ihrem Wert trennen,
  der dann ungeschwärzt stand.) Ein `:Ziffern` hinter `://` gilt nur als Port, wenn der
  Teil davor wie ein Rechner aussieht — mit Punkt (auch IPv4) oder `localhost` — und die
  Zahl höchstens 65535 ist; sonst ist es ein Passwort einer abgeschnittenen Adresse
  („https://alarm:4711?x=…“ → „https://alarm:***“). Grenze: Ein Rechner ohne Punkt (Name
  im Docker-Netz wie „http://n8n:5678/…“ oder „https://host:8443?x=1“) erscheint so als
  „http://n8n:***/…“ — Sicherheit vor Bequemlichkeit; ein Benutzername mit Punkt vor einem
  Ziffern-Passwort einer abgeschnittenen Adresse („https://jan.muster:4711?…“) gilt
  umgekehrt als Rechner mit Port. Fehlermeldungen nennen eine Webhook-Adresse nur mit
  Schema, Rechner und Port; ebenso die Verfahrensdokumentation eine Connector-`basis_url`.
  Zugangsdaten stehen vor dem ersten `/`, `?` oder `#` und enden am letzten `@` dort — ein
  `@` in Abfrage oder Fragment ist keine Zugangsangabe. Ein unkodiertes `#`, `?` oder `/` im
  Passwort erkennt accounti, wenn das `@` im Abschnitt dahinter steht (bis zum nächsten
  `/`; „https://alarm:4711#Sonne@rechner/…“, „https://alarm:4711/Sonne@rechner/…“).
  **Mehrdeutig** ist eine Adresse mit Zugangsdaten „benutzer:…@“ vor einem `#` bzw. `?`
  und einem weiteren `@` dahinter („https://alarm:Son@ne#x@rechner/…“: Rechner „ne“ oder
  „rechner“?) — dann nennen Warnung, `aufgaben_benachrichtigungen.adresse` und
  Verfahrensdokumentation keinen Rechner, sondern „(Adresse nicht eindeutig – @ # ? / im
  Passwort prozentkodieren …)“; das gilt auch für eine Adresse mit Zugangsdaten und einer
  E-Mail-Adresse in der Abfrage. Nicht erkennbar ist ein Passwort mit Ziffern vorn und zwei
  unkodierten `/` („https://alarm:4711/a/b@rechner/…“ — Meldung und Schwärzung nennen
  „alarm:4711“ als Rechner und Port), ein `@` im Passwort vor einem `/`
  („https://alarm:Son@ne/x@rechner/…“ nennt „ne“, wie die Bibliothek die Adresse liest),
  und mit Port und einem `@` in der Abfrage („https://rechner:8443?an=jan@firma.example“)
  nennt die Meldung im Zweifel den Teil nach dem `@`. Deshalb Sonderzeichen im Passwort
  einer Adresse prozentkodieren (`#` → `%23`, `?` → `%3F`, `/` → `%2F`, `@` → `%40`):
  Sonst fragt die Bibliothek ohnehin einen anderen Rechner an, als die Meldung nennt.
- Namen und Belegtexte erkennt kein Muster; der Code schreibt sie nicht ins Protokoll. Der
  geplante Lauf protokolliert Schritt, Rückgabewert und Dauer (die Ausgabe der Befehle, ohne
  Zeilenumbruch erzeugt, ohne Rahmenzeichen, geschwärzt und je Zeile höchstens 1000 Zeichen
  auf Stufe DEBUG; ein Traceback kommt von Python, nicht als Rich-Rahmen in Terminalbreite);
  schlägt ein Schritt fehl, steht in der Warnung auch der Grund
  — die letzten Zeilen seiner Ausgabe, geschwärzt, höchstens 600 Zeichen (z. B. „bank lauf →
  1 (5 s): config/regeln.yaml: Regel telekom: unbekannter Schlüssel kommentar …“). Diese
  Meldung kann einen Namen enthalten, etwa den einer Regel oder Gegenpartei.
- `ACCOUNTI_PROTOKOLL_FORMAT=json` für einen Log-Sammler; in Docker landet alles in
  `docker compose logs`.

## Upgrades

```bash
docker compose build
docker compose stop app lauf     # bis zum Ende des Updates schreibt nichts mehr
docker compose run --rm app sicherung erstellen --ziel /arbeit/daten/sicherungen/   # Einstiegspunkt ist accounti
docker compose run --rm app db upgrade      # = alembic upgrade head, auch ohne Versionsvermerk
docker compose up -d
```

`accounti db upgrade` nimmt die Datenbank aus `--db`, `-g` bzw. `ACCOUNTI_DB` und die
Migrationen aus `/app/alembic.ini` (im Quellbaum aus dessen `alembic.ini`; sonst
`--alembic-ini`). Mehrere Gesellschaften: je Gesellschaft `accounti -g K db upgrade`,
die Systemdatenbank mit `accounti -g K db upgrade --db <URL der Systemdatenbank>`.
`docker compose run --rm --entrypoint alembic app -c /app/alembic.ini upgrade head`
bleibt gleichwertig für Datenbanken **mit** Versionsvermerk.

- **Versionsvermerk:** Eine Datenbank, die `accounti db init` oder der erste Befehl neu
  anlegt (`init_db`), bekommt den Vermerk des Codes, der sie anlegt (Tabelle
  `alembic_version`). Datenbanken aus älteren Fassungen haben keinen — dort begann
  `alembic upgrade head` bei der ersten Migration und brach an „table … already exists“
  ab. `accounti db upgrade` leitet den Stand dann aus dem Schema ab (die Migrationen
  laufen dazu Schritt für Schritt in einer Wegwerf-Datenbank; maßgeblich sind neue
  Tabellen und Spalten), stempelt ihn und migriert weiter; die Ausgabe nennt den
  abgeleiteten Stand. Von Hand ginge das mit `alembic stamp <Revision>` und `alembic
  upgrade head` — für eine Datenbank aus der Zeit vor Baustein 7 ist die Revision
  `a684d10751de`.
- Tabellen, für die es noch keine Migration gibt, legt accounti beim ersten Befehl selbst
  an (`init_db`); spätere Migrationen übernehmen sie.
- `db upgrade` legt keine SQLite-Datei neu an (ein Tippfehler in `--db` ergäbe sonst eine
  frisch migrierte leere Datenbank, die echte bliebe alt) — neu anlegen ist `db init`.
  Scheitert eine Migration, nennt es Grund und erreichten Stand (Exit 1). Unter SQLite
  laufen manche Schritte ohne Transaktion: dann die Sicherung von vor dem Update
  zurückspielen und `db upgrade` erneut, **bevor** ein anderer Befehl läuft.
- **Grenze — sehr alte Datenbanken:** Hat nach dem Update schon ein Befehl des neuen Codes
  eine Datenbank ohne Versionsvermerk angefasst (`init_db` legt fehlende Tabellen an), und
  stammt sie aus der Zeit vor den Bankkonten (Migration `6a51b56d7c30`) bzw. vor den
  Benutzern (`a684d10751de`), scheitert `db upgrade` an „table … already exists“: Nur die
  Migrationen ab Baustein 7 vertragen schon vorhandene Tabellen, die älteren nicht.
  Abhilfe: die Sicherung von vor dem Update zurückspielen und `db upgrade` als ersten
  Befehl ausführen. Bewusst nicht nachgerüstet — dafür müsste jede ältere Migration
  vorhandene Tabellen erkennen und nur Fehlendes ergänzen.
- Das Downgrade von `6d38d11fc348` bricht ab, solange zwei Gesellschaften aktive Token
  gleichen Namens haben (erst eines widerrufen); es prüft das vor dem Löschen des Index.
- Eine Sicherung bringt ihren Versionsvermerk nicht mit, wenn das Ziel schon einen hat:
  `sicherung wiederherstellen` legt das Schema nach dem laufenden Code an und vermerkt
  dessen Stand — die Daten passen hinein, alte Spalten bleiben leer.

**Vermerk passt nicht zum Schema** (eine Prüfung für alle Fälle): `db upgrade` vergleicht
das Schema mit den Tabellen und Spalten des Codes — vor dem Upgrade, wenn nichts offen ist,
und danach. Fehlt etwas, trägt die Datenbank einen Vermerk, dessen Migrationen sie nicht
alle hat: meist ein Entwicklungszweig mit anderer Reihenfolge der Migrationen (Vorabstand von
Baustein 10b: Vermerk `e7153706b43a` ohne die Migrationen von main; Zweig von Paket C:
`46371a6681c2` direkt hinter `ddc9a184ddb4`; 10b-1 vor dem zweiten Zusammenführen:
`e7153706b43a` ohne `belege.steuerkennzeichen`). Dann bricht `db upgrade` mit einer Meldung
ab: die fehlenden Tabellen und Spalten, der Stand, den das Schema zeigt, und zwei
verlustfreie Wege — die Daten seit dem Update bleiben, die Migrationen übernehmen Vorhandenes:

```bash
docker compose run --rm app -g muster sicherung erstellen --ziel /sicherungen/   # vorher sichern
docker compose run --rm app -g muster db upgrade --aus-schema   # Stand aus dem Schema, Migrationen nach
# oder von Hand, mit dem Stand aus der Meldung (hier der Zweig von Paket C):
docker compose run --rm --entrypoint alembic app -c /app/alembic.ini stamp --purge ddc9a184ddb4
docker compose run --rm app -g muster db upgrade
```

`--aus-schema` leitet den Stand auch bei vorhandenem Vermerk aus dem Schema ab, stempelt ihn,
wenn er älter ist (`alembic stamp --purge`), und migriert bis zum Kopf; auch ein Vermerk mit
zwei Zeilen (nach `alembic upgrade heads` mit zwei Köpfen) geht nur so. Im Quellbaum
entsprechend `alembic stamp --purge …` mit einer ini-Kopie auf diese Datenbank und `accounti
db upgrade --db …`; oder `sicherung erstellen` aus der alten Datenbank und `sicherung
wiederherstellen` in eine leere (das Schema legt der laufende Code an). Fehlende Indizes oder
Trigger erkennt die Prüfung nicht; `--aus-schema` stempelt nur zurück, nie vor.

**Update Gesamttest Belege** (Migration `46371a6681c2` nach `a14acef69fae`: Spalte
`belege.steuerkennzeichen`, der Steuerfall einer Rechnung ohne Steuerausweis): ohne die
Migration scheitern Befehle an der neuen Spalte — die Datenbank wie oben mit `accounti db
upgrade` migrieren, bevor das neue Abbild den ersten Befehl ausführt. Ohne
Versionsvermerk erkennt `db upgrade` den Stand `a14acef69fae` an der fehlenden Spalte
(`init_db` ergänzt keine Spalten an vorhandenen Tabellen).
Eine Datenbank, die schon auf dem Entwicklungszweig von Paket C mit `alembic upgrade
head` migriert wurde (Vermerk `46371a6681c2`, dort an `ddc9a184ddb4`), fehlen die
Migrationen von main dazwischen (`6d38d11fc348`, `2f7c7043043e`, `a14acef69fae`) — siehe
„Vermerk passt nicht zum Schema“ oben (Stand laut Schema `ddc9a184ddb4`); die Migration
`46371a6681c2` übernimmt die schon vorhandene Spalte samt Inhalt.

**Update Gesamttest Debitoren** (Migration `a14acef69fae` nach `2f7c7043043e`: Tabelle
`verrechnungen` mit SQLite-Triggern, Spalten `ausgangsrechnungen.rechnungstyp`/
`korrektur_zu`, `ausgangspositionen.elektronisch`): ohne die Migration scheitern Befehle
an den neuen Spalten (die CLI meldet den Datenbankfehler mit dem Hinweis auf `accounti db
upgrade`, wie für jede fehlende Tabelle oder Spalte) — also die Datenbank wie oben mit
`accounti db upgrade` migrieren, bevor das neue Abbild den ersten Befehl ausführt. Hat
ein Befehl des neuen Abbilds die Tabelle `verrechnungen` schon angelegt (`init_db`),
übernimmt die Migration sie; ohne Versionsvermerk erkennt `db upgrade` den Stand
`2f7c7043043e` an den fehlenden Spalten. Neue Verrechnungen gleicht `accounti journal
pruefen` mit dem Bestand ab; eine Übernahme ist nicht nötig (die Tabelle ist neu).

**Update auf Baustein 7** (Migration `ddc9a184ddb4`: Journal, Buchungskorrekturen,
Monatsabschlüsse, `storniert_durch`/`storno_von`, SQLite-Trigger): Die Sicherung vorher
liest die alte Datenbank auch mit dem neuen Abbild (nur vorhandene Spalten). Nach `db
upgrade` (bzw. `alembic upgrade head`) und **vor** `docker compose up -d` einmal

```bash
docker compose run --rm app journal uebernehmen    # Bestand von vor dem Journal eintragen
docker compose run --rm app journal pruefen        # in Ordnung; den Kopf notieren
```

— sonst meldet `journal pruefen` jede ältere Buchung und jeden älteren Beleg als „ohne
Eintrag“ und jedes früher abgeschlossene Jahr als „an accounti vorbei gesperrt“. **Die
Übernahme gleich nach der Migration, bevor accounti selbst schreibt** (den Dienst `lauf`
erst danach wieder starten): Steht im Journal schon ein regulärer Eintrag, lehnt `journal
uebernehmen` ab — was dann ohne Eintrag ist, entstand an accounti vorbei und bleibt ein
Befund; eine später doch eingetragene Übernahme meldet `journal pruefen`. Mit
eingerichteten Benutzern braucht `journal uebernehmen` die Rolle `verwalter` und den
Einmalcode (z. B. `-e ACCOUNTI_BENUTZER=chef -e ACCOUNTI_EINMALCODE=…`). Hat ein Befehl
des neuen Abbilds die neuen Tabellen vor der Migration schon angelegt (`init_db`),
übernimmt die Migration sie und ergänzt nur, was fehlt.

**Update auf Baustein 10b** (Migrationen `d5a849692843` und `e7153706b43a` nach
`46371a6681c2`: `kontierungsgruende`, `kontierungsregeln` samt `rang`,
`auth_benutzer.sprache`):
`accounti db upgrade` migriert — bei mehreren Gesellschaften **jede** Datenbank einzeln, die
Systemdatenbank zuerst (ohne `auth_benutzer.sprache` startet `serve` nicht: Exit 2 mit dem
Hinweis auf `accounti db upgrade`). Ohne Versionsvermerk erkennt `db upgrade` den Stand vor
jeder der beiden Migrationen (`46371a6681c2` an den fehlenden Tabellen der Kontierung,
`d5a849692843` an der fehlenden Spalte `sprache`; hat ein Befehl des neuen Abbilds die
Tabellen schon angelegt, zeigt die fehlende Spalte `belege.steuerkennzeichen` den Stand
`a14acef69fae`, und alle drei Migrationen übernehmen das Vorhandene). Die URLs stehen in `.env` und werden auf dem Host
eingesetzt — deshalb zuerst die `.env` in die Shell laden:

```bash
set -a; . ./.env; set +a
docker compose run --rm app -g muster db upgrade --db "$ACCOUNTI_SYSTEM_DB"   # Systemdatenbank
docker compose run --rm app -g muster db upgrade
docker compose run --rm app -g tochter db upgrade
docker compose run --rm app -g muster regeln uebernehmen --probe   # alte gelernt_*-Regeln ansehen, dann ohne --probe
```

Gleichwertig für Datenbanken **mit** Versionsvermerk: `docker compose run --rm -e
ACCOUNTI_DB="$ACCOUNTI_SYSTEM_DB" --entrypoint alembic app -c /app/alembic.ini upgrade head`
(je Datenbank). Eine Datenbank, die schon mit einem **Vorabstand von Baustein 10b** migriert
wurde (die beiden Migrationen hingen dort an `ddc9a184ddb4` bzw. `a14acef69fae`), steht auf
dem Kopf `e7153706b43a`, ohne Migrationen von main (`verrechnungen`,
`anlagegueter.buchung_id`, `belege.steuerkennzeichen` …) oder ohne `kontierungsregeln.rang`
— `db upgrade` bricht ab, `db upgrade --aus-schema` holt sie nach (siehe „Vermerk passt
nicht zum Schema“ oben).

Früher gelernte Regeln (`gelernt_*` am Ende der Regeldatei) übernimmt `regeln uebernehmen` in die
Datenbank, mit der Richtung ihrer Bankseite (mit eingerichteten Benutzern mit den Rechten
`buchen` und `regeln_lernen` — Rolle `buchhalter` — und Einmalcode, z. B.
`-e ACCOUNTI_BENUTZER=eva -e ACCOUNTI_EINMALCODE=…`); Einträge ohne erkennbare Bankseite meldet
der Befehl, sie gelten für Ein- und Ausgänge. Übernommene Regeln stehen hinter den schon in der
Datenbank gelernten (eine Korrektur seit dem Update behält Vorrang), untereinander in der
Reihenfolge der Datei — auch wenn ein zweiter Lauf (`--name`) weitere übernimmt. Die Einträge
prüft derselbe Lader wie für die Regeldatei (Kontonummern, Muster, Steuerschlüssel; ungültige
nennt die Ausgabe mit Grund); eine Datei, die kein YAML, nicht UTF-8 oder keine Liste ist,
meldet der Befehl vor dem Einmalcode. „Schon vorhanden (übersprungen)“ heißt: dieselbe Regel
(Muster, Konten, Schlüssel, Feld, Buchungstext; die Richtung, wenn der Eintrag sie nennt) steht
schon in der Datenbank bzw. früher in derselben Datei. Trägt eine Regel der Datenbank den Namen mit anderem
Inhalt, ist der Eintrag ungültig („Regelname … ist schon vergeben … anderem Inhalt“) — in der
Datei umbenennen, nicht löschen, sonst geht die Änderung verloren. **Andere Einträge bleiben in der Regeldatei** und greifen
dort wie bisher, nach den gelernten — die Ausgabe nennt sie: Regeln, die auf main mit `accounti lerne
--name X` gelernt wurden (ohne Präfix `gelernt_`; mit `regeln uebernehmen --name X`
übernehmen), Einträge mit `pruefen: true` oder `confidence` unter 1 (eine gelernte Regel hat
kein eigenes Prüfkennzeichen — übernommen buchte sie automatisch; dauerhaft prüfen lässt
sich nur über `buchhaltung.gelernte_regeln: pruefen` für alle) und Umbuchungen zwischen
Geldkonten. Danach — erst nach allen Läufen, auch denen mit `--name` — die übernommenen
Einträge von Hand aus der Datei löschen: Jeder Lauf ordnet nach der Stelle in der Datei zur
Zeit des Laufs; wer vorher löscht und dann `--name` verwendet, rückt dessen Eintrag womöglich
vor früher übernommene Regeln (`regeln liste` zeigt den Vorrang; bei Bedarf deaktivieren und
neu lernen). Ein Lauf, der nichts übernähme (keine Datei, nur ungültige Einträge, nur
unbekannte Namen), verbraucht keinen Einmalcode. Hat ein Befehl des neuen Abbilds die neuen
Tabellen vor der Migration schon angelegt, übernimmt die Migration sie.

**Verhaltensänderung: Die Regeldatei wird streng geprüft** (10b-1). Jeder Eintrag der
Regeldatei (`config/regeln.yaml` bzw. die der Gesellschaft) muss gültig sein — sonst hält
die **ganze Datei** an: `classify`, `bank lauf` (samt Bankabruf), `opos verbuchen` und der
REST-Lauf (409) brechen mit einer Meldung ab (Datei, Regel, Schlüssel), bis der Eintrag
berichtigt ist. Ein Fehler ist ein Feld, das der Lader nicht kennt (auch ein Zusatzfeld wie
`kommentar:` oder `aktiv:`, ein Tippfehler wie `prüfen:` — es wirkte bisher still nicht),
ein Steuerschlüssel, den accounti nicht kennt (0, 4, 40, 99 …; bekannt sind 1, 2, 3, 8, 9,
18, 19, 91, 94), eine Kontonummer außerhalb von 4–9 ASCII-Ziffern und YAML-Zahlformen wie
`0x1340`, `1:20:00` oder `4_920`. Gebucht wird dadurch nichts falsch; der erste Lauf nach
der Korrektur holt alles nach. Eigene Bestandsdateien haben den neuen Kopfkommentar der
mitgelieferten `config/regeln.yaml` nicht — vor dem Update auf Zusatzfelder durchsehen
(Kommentare gehören hinter `#`). Im geplanten Lauf steht die Meldung im Protokoll
(`docker compose logs lauf`).

**Verhaltensänderung: Kontenlängen werden geprüft** (10b-1). `mandant.sachkonten_laenge`
muss eine ganze Zahl von 4 bis 8 sein (DATEV) — sonst brechen `export datev`, `datev belege`
und `datev stammdaten` mit einer Meldung ab. `4.0` gilt als 4; `4.5`, `9`, `true` oder `"abc"`
nicht. Die Personenkontenbereiche (`buchhaltung.debitoren_von`/`_bis`,
`kreditoren_von`/`_bis`) haben höchstens 9 Stellen: Eine **Untergrenze** mit mehr Stellen ist
ein Fehler, jeder Befehl, der die Buchhaltung lädt, hält an (`classify`, `bank lauf`,
`pruefen`, `export datev` …). Eine **Obergrenze** darüber (etwa `kreditoren_bis: 9999999999`
als „offen“) gilt als 999999999 — die Befehle laufen, jeder nennt einen Hinweis (auch im
Protokoll des geplanten Laufs); die Zeile in der Konfiguration berichtigen. `export datev`
warnt je Personenkonto, dessen Länge nicht Sachkontenlänge + 1 ist. Die Konfiguration vor dem
Update durchsehen. Kaputtes YAML in der Konfiguration meldet jeder Befehl mit Datei und Stelle
(„… kein gültiges YAML (…)“, rc 1) statt mit einem Traceback.

**Update auf Baustein 10c, Paket 1** (Migration `1dd2f6b7c6c8_add_benutzer_vorlieben` auf
`e7153706b43a`: `auth_benutzer.darstellung`, `fachansicht`, `betraege_verbergen`,
`tastenkuerzel`): Vorher wie oben stoppen und sichern. Wie bei 10b liegt `auth_benutzer` in
**jeder** Datenbank – die Systemdatenbank zuerst migrieren (ohne die Spalten startet `serve`
nicht), danach jede Gesellschaftsdatenbank. Die URLs stehen in `.env` und werden auf dem Host
eingesetzt, deshalb zuerst die `.env` in die Shell laden:

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

**Update auf Baustein 10c, Paket P4a** (Migration `83dfa5750c7f_add_einstellungen` auf
`1dd2f6b7c6c8`: Tabellen `einstellungen`, `einstellungsantraege`, `geheimnisse`; Trigger gegen
Ändern und Löschen der Versionen unter SQLite und PostgreSQL): `db upgrade` wie oben — die
Systemdatenbank und jede Gesellschaftsdatenbank —, sonst nichts. Die Tabellen bleiben leer,
bis Einstellungen in der Datenbank gepflegt werden (`accounti einstellungen`, mit Paket P4b);
bis dahin gelten die Werte der Datei wie bisher. Jeder Befehl liest die Einstellungen aus der
Datenbank, mit der er arbeitet (`--db`, Gesellschaft bzw. `ACCOUNTI_DB`, sonst
`sqlite:///accounti.db`); `fristen`, `pruefen regeln`, `kanaele connectoren` und `elster pin`
haben dafür jetzt `--db`. Ist diese Datenbank nicht erreichbar, bricht ein Befehl ab, statt
still die Datei zu nehmen. Das Downgrade geht nur, solange die drei Tabellen leer sind.

Drei Dinge wirken ab diesem Stand neu:

- `llm.auto_buchen_schwelle`, `llm.provider` und `llm.model` (bisher ohne Wirkung, immer
  0,95 und das Standardmodell) — wer in der Datei einen anderen Wert stehen hat, bekommt ihn
  jetzt; vor dem Update prüfen. `llm.api_key: "${ANTHROPIC_API_KEY}"` ohne gesetzte Variable
  stört nicht: `bank lauf --no-llm`, `classify --no-llm` und `verfahrensdoku` laufen wie
  bisher.
- `datev.wirtschaftsjahr_beginn` zählt nur nach Tag und Monat und darf so geschrieben werden
  (`"07-01"` oder `"01.07."`); ein Datum mit Jahr bleibt gültig.
- Werte, die vom Zeitraum abhängen, können ein „ab“ tragen — ein Einzelwert gilt wie bisher
  für alle Zeiträume:

  ```yaml
  elster:
    voranmeldungszeitraum: { 2026: monat, 2027: quartal }   # 2026 bleibt monatlich
    dauerfristverlaengerung: { 2026: true, 2027: false }
  mandant:
    oss: { 2026-Q1: false, 2027-Q1: true }                  # ab einem Quartal
  abschluss:
    gewinnermittlung: { 2026: euer, 2027: bilanz }          # je Wirtschaftsjahr (Jahr des Endes)
  ```

  Es gilt der Eintrag mit dem größten Zeitraum, der nicht nach dem gefragten liegt; der
  früheste gilt auch für alle Zeiträume davor. Ein Schlüssel in falscher Form (`2027` bei
  `oss`, `2027-Q5`) ist ein Fehler mit Feldpfad.

Fehlt die Konfigurationsdatei, ist sie ein leerer Startwert: Es gelten die Einstellungen der
Datenbank, sonst die Standards (bzw. die bisherige Meldung „… fehlt — Vorlage …“).
Optional legt die Datei Abschnitte fest — sie werden dann nie aus der Datenbank gelesen:

```yaml
einstellungen:
  quelle: datei                   # alle Abschnitte aus der Datei
  # festgelegt: [elster, zahlung]  # oder nur diese
```
