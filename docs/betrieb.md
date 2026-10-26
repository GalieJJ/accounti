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
   legt accounti beim ersten Befehl selbst an. `app` und `lauf` haben eine
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
Konfiguration (Kontenrahmen, Wirtschaftsjahr, Firmendaten, Bankkonten, Nummernkreise). Die
Registry steht in der globalen Konfiguration:

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
  Gesellschaften, bricht ein Datenbefehl ab. `accounti gesellschaft liste|zeigen`.
  `classify`, `bank lauf`, `opos verbuchen`, `lerne` und `korrigiere --lernen` nutzen die
  Regeldatei der Gesellschaft (ohne Registry wie bisher `config/regeln.yaml`).
- Browser: Rollen gelten je Gesellschaft (`accounti -g tochter benutzer rolle eva --rolle
  buchhalter`); der Wechsler oben rechts schaltet alle Seiten um. Wer in einer Gesellschaft
  keine Rolle hat, sieht sie nicht.
- API: jedes Token gehört zu einer Gesellschaft (`accounti -g tochter token anlegen …`).
- Docker: weitere Datenbanken anlegen
  (`docker compose exec db createdb -U accounti tochter`), die URLs in `.env` und unter
  `environment` ergänzen; `lauf` arbeitet alle Gesellschaften der Registry ab.
- Grenze: Die Abschnitte `bank` (FinTS-Produkt-ID, Kreditkarten-Muster) gelten für die
  Installation; `import banken` liest `config/banken.yaml` relativ zum
  Arbeitsverzeichnis.

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
  Monatssperre), `bank bestaetigen|ablehnen`, `nachfordern anfrage --senden`, `belege
  freigeben` (Beleg aus der Prüfung, mit Belegart, Steuerfall, Belegnummer oder
  umgekehrtem Vorzeichen; `--grund` Pflicht bei Dublettenverdacht, Rechenprobe und
  Vorzeichen). Wer erfasst
  und korrigiert, legt dabei freigegebene Buchungen an — das Recht zu buchen schließt laut
  Rollen das Freigeben ein (ein Test hält das fest).
- **Buchungen freigeben** (`buchhalter`, `freigeber`): `bestaetige`, `opos
  bestaetigen|ablehnen`, `abschluss bestaetigen|ablehnen`, `periode schliessen`,
  `abschluss vortrag`, `export datev` und `datev belege` (Übergabe an den Steuerberater,
  Vermerk „exportiert“).
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
  als Verwalter — eine Flut aus dem Netz öffnet keine Einrichtungsphase. Ist auch der
  Einmalcode in der CLI gesperrt (100 falsche Codes auf der Shell) und kein anderer
  Verwalter da, bleibt nur die Datenbank:
  `UPDATE auth_benutzer SET fehlversuche = 0, gesperrt_bis = NULL, cli_fehlversuche = 0,
  cli_gesperrt_bis = NULL WHERE name = 'chef'`. Grenze: Wer den Namen kennt, kann neue
  Anmeldungen im Browser je 15 Minuten und nach 100 Versuchen bis zum Entsperren
  blockieren; eine Begrenzung je IP gehört in den Proxy (z. B. `limit_req` für
  `/anmelden`).
- **Sitzungen:** Cookie `__Host-accounti_sitzung` (Secure, HttpOnly, SameSite=Strict),
  30 Minuten Leerlauf, höchstens 8 Stunden; Abmelden, Passwortwechsel, `benutzer sperren`,
  Rollenänderung und ein neuer zweiter Faktor beenden sie serverseitig. Jede Freigabe im
  Browser verlangt zusätzlich einen frischen Einmalcode und gilt nur für den angezeigten
  Inhalt (Empfänger, IBAN, Betrag, Verwendungszweck; hat sich der Entwurf seitdem
  geändert, 409).
- **CLI:** Ohne eingerichtete Benutzer prüft accounti nichts. Mit Benutzern verlangen
  `zahlung freigeben`, `ustva freigeben`, `ustva dauerfrist --freigeben` (Rolle
  `freigeber`), `zahlung anlegen` (`buchhalter`) und `anlagen freigeben`
  (Buchungsfreigabe) den Einmalcode der handelnden Person (`--von` bzw.
  `ACCOUNTI_BENUTZER`, mit Vier-Augen der Anmeldename); ebenso `zahlung entfernen`,
  `sperre`, `iban-klaeren`, `abgleichen`, `sepa` und `stornieren` sowie die Befehle aus
  Baustein 7 (siehe oben). Der Einmalcode lässt sich in
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
  Fehlversuche, Sperren, Rollen, Token; nur anfügen).

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

## Sicherung und Wiederherstellung

```bash
accounti sicherung schluessel                                 # einmal: Schlüssel erzeugen
accounti sicherung erstellen --ziel /sicherungen/             # Datenbank + Belegarchiv
accounti sicherung erstellen --system --ziel /sicherungen/    # Systemdatenbank (mehrere Gesellschaften)
accounti sicherung pruefen /sicherungen/accounti-standard-20261020-0300.sicherung
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
accounti sicherung pruefen DATEI
accounti sicherung wiederherstellen DATEI --db sqlite:////tmp/probe/x.db --archiv /tmp/probe/belege
accounti opos liste --db sqlite:////tmp/probe/x.db         # mit dem Original vergleichen
accounti journal pruefen --db sqlite:////tmp/probe/x.db --kopf NR:HASH   # Kopf vom Original
accounti export datev --db sqlite:////tmp/probe/x.db …     # Stichprobe Buchungen
rm -rf /tmp/probe
```

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
| Kreditinstitute, Versicherungen, Wertpapierinstitute: Buchungsbelege | **10 Jahre** | Art. 97 § 19a Abs. 3 EGAO |

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
  `belege.aufbewahren_bis` rechnet noch mit 10 Jahren (vor dem BEG IV angelegt) — länger
  aufzubewahren ist zulässig.
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
  Passwörter in URLs und Parameter wie `passwort=`, `token=`, `code=` — auch in Stacktraces.
- Namen und Belegtexte erkennt kein Muster; der Code schreibt sie nicht ins Protokoll. Der
  geplante Lauf protokolliert nur Schritt, Rückgabewert und Dauer (die Ausgabe der Befehle
  geschwärzt auf Stufe DEBUG).
- `ACCOUNTI_PROTOKOLL_FORMAT=json` für einen Log-Sammler; in Docker landet alles in
  `docker compose logs`.

## Upgrades

```bash
docker compose build
docker compose stop app lauf     # bis zum Ende des Updates schreibt nichts mehr
docker compose run --rm app sicherung erstellen --ziel /arbeit/daten/sicherungen/   # Einstiegspunkt ist accounti
docker compose run --rm --entrypoint alembic app -c /app/alembic.ini upgrade head
docker compose up -d
```

Alembic liest die Datenbank aus `ACCOUNTI_DB`. Tabellen, für die es noch keine Migration
gibt, legt accounti beim ersten Befehl selbst an (`init_db`).

**Update auf Baustein 7** (Migration `ddc9a184ddb4`: Journal, Buchungskorrekturen,
Monatsabschlüsse, `storniert_durch`/`storno_von`, SQLite-Trigger): Die Sicherung vorher
liest die alte Datenbank auch mit dem neuen Abbild (nur vorhandene Spalten). Nach `alembic
upgrade head` und **vor** `docker compose up -d` einmal

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
