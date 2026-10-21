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
   legt accounti beim ersten Befehl selbst an.
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
| `ACCOUNTI_SYSTEM_DB` | Systemdatenbank (Benutzer, Rollen, Sitzungen, Token), überstimmt die Registry |
| `ACCOUNTI_SCHLUESSEL` | Tresor-Schlüssel (Bankzugänge, TOTP-Geheimnisse) — ohne ihn keine Anmeldung |
| `ACCOUNTI_SICHERUNG_SCHLUESSEL` | Schlüssel der Sicherungen (sonst `ACCOUNTI_SCHLUESSEL`) |
| `ACCOUNTI_BENUTZER` | handelnde Person in der CLI |
| `ACCOUNTI_EINMALCODE` | Einmalcode für einen CLI-Befehl in Skripten (gilt einmal) |
| `ACCOUNTI_PROTOKOLL_STUFE` / `_FORMAT` | `INFO` … / `text` oder `json` |
| `ACCOUNTI_FINTS_PRODUKT_ID` | Produkt-ID der Installation (FinTS) |

Vorrang: ausdrückliche Option → Gesellschaft aus der Registry → Umgebungsvariable →
bisheriger Standard (`sqlite:///accounti.db`, `archiv/belege`, `config/accounti.yaml`).

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

- CLI: `accounti --gesellschaft tochter opos liste` — die Option setzt `--db`, `--archiv` und
  `--config` **aller** Befehle. Ohne Option gilt `standard`; gibt es keinen und mehrere
  Gesellschaften, bricht ein Datenbefehl ab. `accounti gesellschaft liste|zeigen`.
- Browser: Rollen gelten je Gesellschaft (`accounti -g tochter benutzer rolle eva --rolle
  buchhalter`); der Wechsler oben rechts schaltet alle Seiten um. Wer in einer Gesellschaft
  keine Rolle hat, sieht sie nicht.
- API: jedes Token gehört zu einer Gesellschaft (`accounti -g tochter token anlegen …`).
- Docker: weitere Datenbanken anlegen
  (`docker compose exec db createdb -U accounti tochter`), die URLs in `.env` und unter
  `environment` ergänzen; `lauf` arbeitet alle Gesellschaften der Registry ab.
- Grenze: Die Abschnitte `bank` (FinTS-Produkt-ID, Kreditkarten-Muster) gelten für die
  Installation; `classify`, `bank lauf`, `korrigiere --lernen` in der **CLI** lesen
  `config/regeln.yaml` relativ zum Arbeitsverzeichnis — eigene Regeln je Gesellschaft gibt es
  bisher nur im Browser und in der API (`regeln:` in der Registry).

## Benutzer, Rollen, Anmeldung

| Rolle | darf |
|-------|------|
| `betrachter` | lesen |
| `buchhalter` | lesen, buchen/prüfen/korrigieren, Belege einliefern, Läufe starten, Buchungen freigeben |
| `freigeber` | lesen, Buchungen, **Zahlungsläufe** und **Steuermeldungen** freigeben |
| `verwalter` | lesen, Benutzer, Token und Einstellungen verwalten |

Rollen sind nicht hierarchisch, ein Benutzer kann mehrere haben. Wer Zahlungen anlegt
(`buchhalter`), gibt sie nicht frei — das trägt das Vier-Augen-Prinzip
(`zahlung.vier_augen: true`: zwei verschiedene Freigeber).

- **Anmeldung im Browser** nur mit Passwort **und** Einmalcode (TOTP-App nach RFC 6238 oder
  ein Wiederherstellungscode, der genau einmal gilt). Jeder Code gilt einmal. Nach 5
  Fehlversuchen ist das Konto 15 Minuten gesperrt (`auth.sperre_*`, `accounti benutzer
  entsperren`). Passwörter: mindestens 12 Zeichen, keine Zusammensetzungsregeln, scrypt
  (N = 2^17).
- **Sitzungen:** Cookie `__Host-accounti_sitzung` (Secure, HttpOnly, SameSite=Strict),
  30 Minuten Leerlauf, höchstens 8 Stunden; Abmelden, Passwortwechsel, Sperre und
  Rollenänderung beenden sie serverseitig. Jede Freigabe im Browser verlangt zusätzlich einen
  frischen Einmalcode.
- **CLI:** Ohne eingerichtete Benutzer prüft accounti nichts. Mit Benutzern verlangen
  `zahlung freigeben`, `ustva freigeben` und `ustva dauerfrist --freigeben` die Rolle
  `freigeber` und den Einmalcode der handelnden Person (`--von` bzw. `ACCOUNTI_BENUTZER`,
  mit Vier-Augen der Anmeldename). Die CLI läuft auf dem Server: wer sie aufrufen kann,
  kommt meist auch an die Datenbank — die Prüfung bindet Freigaben an eine Person, sie
  ersetzt keine Zugriffskontrolle auf den Server.
- Protokoll: `accounti benutzer protokoll` (Anmeldungen, Fehlversuche, Sperren, Rollen,
  Token; nur anfügen).

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
accounti sicherung pruefen /sicherungen/accounti-standard-20261020-0300.sicherung
accounti sicherung wiederherstellen DATEI --db postgresql+psycopg://…/leer --archiv /leer/belege
```

- Eine Datei enthält alle Tabellen (typgetreu, über SQLAlchemy — SQLite und PostgreSQL in
  beide Richtungen) und alle Dateien des Belegarchivs, verschlüsselt mit AES-256-GCM in
  Stücken; der Schlüssel jeder Sicherung wird per HKDF aus `ACCOUNTI_SICHERUNG_SCHLUESSEL`
  abgeleitet. Ein Manifest hält Zeilenzahl und SHA-256 je Tabelle und Datei fest; Sitzungen
  werden nicht gesichert. Die Datei hat die Rechte 0600 und wird nie überschrieben.
- **Den Schlüssel getrennt von den Sicherungen aufbewahren** (Passwortmanager, Tresor):
  ohne ihn ist keine Sicherung lesbar, mit ihm und der Datei alles.
- Wiederhergestellt wird nur in eine **leere** Datenbank und ein leeres Archiv, in einer
  Transaktion: erst wenn alles zum Manifest passt, wird festgeschrieben; sonst bleibt nichts
  zurück. Hash-Ketten der Protokolle bleiben gültig.
- Mehrere Gesellschaften: je Gesellschaft `accounti -g K sicherung erstellen …`, dazu die
  Systemdatenbank `accounti sicherung erstellen --db "$ACCOUNTI_SYSTEM_DB" --ohne-archiv …`.
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
| Buchungen (`buchungssaetze`), Journale, Kassenbuch, Protokolle (USt-IdNr., Übermittlung, Zahlungslauf, Abschluss), Jahresabschluss | **10 Jahre** | § 147 Abs. 1 Nr. 1, Abs. 3 AO |
| Belege (`belege`, Belegarchiv) als Buchungsbelege | **8 Jahre** | § 147 Abs. 1 Nr. 4, Abs. 3 AO |
| Rechnungen (Ein- und Ausgang) | **8 Jahre** | § 14b Abs. 1 UStG |
| Handels- und Geschäftsbriefe, sonstige Unterlagen | **6 Jahre** | § 147 Abs. 1 Nr. 2, 3, 5 AO |
| Kreditinstitute, Versicherungen, Wertpapierinstitute: Buchungsbelege | **10 Jahre** | Art. 97 § 19a Abs. 3 EGAO |

- Die Frist beginnt mit dem Schluss des Kalenderjahres, in dem die Unterlage entstand
  (§ 147 Abs. 4 AO). Die 8 Jahre gelten für alle Belege, deren alte Frist am 31.12.2024 noch
  lief.
- Sie läuft nicht ab, solange die Unterlagen für eine Steuer von Bedeutung sind, deren
  Festsetzungsfrist noch läuft — etwa bei Außenprüfung, Einspruch, vorläufiger Festsetzung
  (§ 147 Abs. 3 Satz 3 AO). Handelsrechtlich gilt § 257 HGB entsprechend.
- **accounti löscht nichts von selbst.** `accounti betrieb aufbewahrung [--stichtag]
  [--institut]` zeigt je Bestand, was frühestens ausgesondert werden **dürfte**. Das
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

- Das Zugriffsprotokoll schreibt Methode, Pfad **ohne Abfrage**, Status und Dauer — keine
  IP-Adresse, keinen Benutzer. Das Protokoll von Uvicorn ist aus, HTTP-Bibliotheken schreiben
  erst ab Warnung (ihre Adressen tragen oft Token).
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
docker compose run --rm app sicherung erstellen --ziel /arbeit/daten/sicherungen/   # Einstiegspunkt ist accounti
docker compose run --rm --entrypoint alembic app -c /app/alembic.ini upgrade head
docker compose up -d
```

Alembic liest die Datenbank aus `ACCOUNTI_DB`. Tabellen, für die es noch keine Migration
gibt, legt accounti beim ersten Befehl selbst an (`init_db`).
