# Anmeldung, Rollen, mehrere Gesellschaften, Betrieb und REST-API (Baustein 10a) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** accounti kennt benannte Benutzer mit Rollen (`betrachter`, `buchhalter`, `freigeber`,
`verwalter`), die sich im Browser nur mit Passwort **und** zweitem Faktor (TOTP nach RFC 6238 oder
einmaligem Wiederherstellungscode) anmelden. Freigaben von Zahlungsläufen und Steuermeldungen sind
an die Rolle gebunden — im Browser und in der CLI. Mehrere eigene Gesellschaften laufen getrennt
(je Gesellschaft eine Datenbank, ein Belegarchiv, eine Konfiguration); der Wechsel per
`--gesellschaft` oder in der Oberfläche schaltet alle Ansichten zugleich um. Eine REST-API mit
Token und Berechtigungen liefert offene Posten und Buchungen, nimmt Belege an und stößt Läufe an.
`docker compose up` startet Anwendung, PostgreSQL und den geplanten Lauf; `accounti sicherung`
sichert Datenbank und Belegarchiv verschlüsselt und stellt sie in eine leere Umgebung wieder her.
Die FastAPI-Anwendung ist das Gerüst, auf dem die Web-Oberfläche (Supervisions-Queue,
Auswertungen, Zweisprachigkeit) danach aufbaut.

**Spec:** [`docs/specs/2026-08-10-web-ui-auth-betrieb.md`](../specs/2026-08-10-web-ui-auth-betrieb.md),
Abschnitte 4.1, 4.4, 4.6, 4.7 · Akzeptanzkriterien 3, 4, 5, 6, 7 ·
[`docs/specs/2026-08-10-integrationen-export.md`](../specs/2026-08-10-integrationen-export.md)
Akzeptanzkriterium 7 (REST-API) · **Baut auf:** Baustein 2 (Belegarchiv, Pipeline, Webhook),
4 (offene Posten), 5 (Tresor, `bank lauf`), 6 (Zahlungslauf mit Vier-Augen), 8 (`aufgaben lauf`),
9 (`ustva freigeben`) · **Nicht hier:** Spec 4.2, 4.3, 4.5 (Supervisions-Queue, Auswertungen,
Zweisprachigkeit; Akzeptanz 1 und 2) — baut der nächste Auftrag auf der hier beschriebenen
Schnittstelle.

```
                 Browser                         Fremdsystem (ERP, n8n …)
                    │ Cookie __Host-accounti_sitzung   │ Authorization: Bearer accounti_api_…
                    ▼                                  ▼
  accounti.api.erstelle_app ── Sicherheitskopfzeilen · Zugriffsprotokoll ohne Personenbezug
     ├─ seiten/ (Registry, Jinja2, CSRF)         ├─ rest/ (Registry, /api/v1, Token-Rechte)
     │   anmelden · abmelden · start             │   offene-posten · buchungen
     │   gesellschaft wechseln · freigaben       │   belege (Pipeline) · laeufe/bank|aufgaben
     ▼                                           ▼
  Dependencies: angemeldet → erfordert(Recht) → gesellschaft_db (Session der aktiven Gesellschaft)
                    │
  accounti.auth ── Benutzer · Rollen je Gesellschaft · scrypt · TOTP · Wiederherstellungscodes
                    │ Sitzungen · Sperre · API-Token · Ereignisprotokoll   ──▶ Systemdatenbank
  accounti.betrieb ── Registry `gesellschaften` (je Kürzel: Datenbank, Archiv, Konfiguration)
                    │ CLI: --gesellschaft setzt --db/--archiv/--config aller Befehle
                    │ Sicherung (AES-256-GCM, Datenbank + Archiv) · Aufbewahrung · Protokoll · Planer
                    ▼
  bestehende Module (zahlung.freigabe, elster.freigabe, belege.pipeline, bank.lauf, aufgaben …)
```

---

## Recherche (Stand 20.10.2026)

| Thema | Ergebnis | Quelle (abgerufen 20.10.2026) |
|-------|----------|-------------------------------|
| Passwort-Hash | Reihenfolge: Argon2id, sonst **scrypt**, bcrypt nur für Altsysteme, PBKDF2 bei FIPS. scrypt mindestens N = 2^17 (128 MiB), r = 8, p = 1; Salz je Passwort; Pepper optional und getrennt vom Hash | [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) |
| Passwortregeln | mit zweitem Faktor mindestens 8 Zeichen (allein 15), mindestens 64 Zeichen zulassen, **keine** Zusammensetzungsregeln, Abgleich mit einer Sperrliste; höchstens 100 Fehlversuche in Folge; ein Einmalcode gilt nur einmal; Nachschlage-Geheimnisse (Wiederherstellungscodes) nur einmal und — unter 112 Bit — gesalzen mit einem Passwort-Hash | [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html) |
| Sitzungen | Sitzungs-ID ≥ 64 Bit Entropie (CSPRNG ≥ 128 Bit); Cookie `Secure`, `HttpOnly`, `SameSite=Strict` (bevorzugt), Präfix `__Host-` (Secure, Path=/, ohne Domain); Leerlauf 15–30 min bei geringem, 2–5 min bei hohem Risiko, absolut z. B. 4–8 h; neue ID nach Anmeldung und Rechteänderung; Abmelden macht die Sitzung **serverseitig** ungültig | [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) |
| TOTP | T = ⌊(Unixzeit − T0) / X⌋, X = 30 s, T0 = 0; HOTP mit HMAC-SHA-1, SHA-256/512 erlaubt; höchstens ein Zeitschritt Toleranz für Netzverzögerung empfohlen; „The verifier MUST NOT accept the second attempt of the OTP“ nach erfolgreicher Prüfung; Schlüssel zufällig, Länge der HMAC-Ausgabe (SHA-1: 20 Byte); Prüfwerte in Anhang B | [RFC 6238](https://datatracker.ietf.org/doc/html/rfc6238), Abschnitte 4, 5.1, 5.2, Anhang B |
| Aufbewahrung | § 147 Abs. 3 AO (seit dem BEG IV, verkündet am 29.10.2024, BGBl. 2024 I Nr. 323, ab 01.01.2025): **10 Jahre** für Bücher, Aufzeichnungen, Inventare, Jahresabschlüsse, Lageberichte, Eröffnungsbilanz und Organisationsunterlagen (Abs. 1 Nr. 1) sowie Zollunterlagen (Nr. 4a); **8 Jahre** für Buchungsbelege (Nr. 4); **6 Jahre** für empfangene und abgesandte Handels- und Geschäftsbriefe und sonstige steuerlich bedeutsame Unterlagen (Nr. 2, 3, 5). Fristbeginn mit dem Schluss des Kalenderjahres (Abs. 4); kein Ablauf, solange die Unterlagen für eine Steuer von Bedeutung sind, deren Festsetzungsfrist nicht abgelaufen ist (Abs. 3 Satz 3) | [§ 147 AO](https://www.gesetze-im-internet.de/ao_1977/__147.html); [IHK Karlsruhe zum BEG IV](https://www.ihk.de/karlsruhe/fachthemen/steuerrecht/aktuelles/neuer-inhalt4-buerokratieentlastungsgesetz-6347138) |
| Übergang | die 8 Jahre gelten für alle Unterlagen, deren Frist nach altem Recht am 31.12.2024 noch nicht abgelaufen war (Art. 97 § 19a Abs. 2 EGAO); **Ausnahme:** Kreditinstitute (§ 1 Abs. 1b KWG), beaufsichtigte Versicherungen und Wertpapierinstitute behalten die alte Fassung (10 Jahre, Abs. 3) | [Art. 97 § 19a EGAO](https://www.gesetze-im-internet.de/aoeg_1977/art_97__19a.html); [EY, Längere Aufbewahrungsfristen bei Banken, Versicherungen und Wertpapierinstituten](https://www.ey.com/de_de/technical/steuernachrichten/laengere-aufbewahrungsfristen-bei-banken-versicherungen-und-wertpapierinstituten) |
| Rechnungen | § 14b Abs. 1 UStG: Doppel der Rechnungen **acht Jahre**, Beginn mit Schluss des Kalenderjahres der Ausstellung; § 147 Abs. 3 AO bleibt unberührt | [§ 14b UStG](https://www.gesetze-im-internet.de/ustg_1980/__14b.html) |
| Formulare ohne Zusatzpaket | Starlettes `request.form()` braucht `python-multipart` (nicht installiert); der Webhook liest Multipart schon mit dem `email`-Parser der Standardbibliothek, `application/x-www-form-urlencoded` genügt `urllib.parse` | Quelltext `accounti.belege.webhook.anfrage`; `pip list` der venv |
| Typer | Typer 0.27 bringt eine eigene Click-Kopie (`typer._click`); der Gruppen-Callback läuft **vor** dem Anlegen des Unterbefehl-Kontexts, `Context.default_map` vererbt sich je Befehlsname nach unten | `typer/core.py` (`TyperGroup.invoke`), `typer/_click/core.py` (`Context.__init__`, `lookup_default`) |

## Schnitt in Pakete

1. **Paket 1 — Anmeldung, Rollen und Gesellschaften in der CLI:** Modelle, Tabellen,
   Repository; scrypt, TOTP, Wiederherstellungscodes, Sperre, Sitzungen, API-Token,
   Ereignisprotokoll; Registry `gesellschaften`, Kontext und globale Option
   `--gesellschaft` in `cli.py` (setzt `--db`/`--archiv`/`--config` aller Befehle),
   `ACCOUNTI_DB`/`ACCOUNTI_ARCHIV`/`ACCOUNTI_KONFIG`; Befehle `accounti benutzer …`,
   `accounti token …`, `accounti gesellschaft …`; Rechteprüfung in `zahlung freigeben`,
   `ustva freigeben` und `ustva dauerfrist --freigeben`. Die beiden Teile hängen
   aneinander (Rollen gelten je Gesellschaft, Benutzer liegen in der Systemdatenbank der
   Registry) und kommen deshalb in einem Paket.
2. **Paket 2 — Web-Gerüst und REST-API:** App-Fabrik, Sitzungs-Login mit zweitem Faktor,
   CSRF, Rollen-Dependency, Router-Registries, Jinja2-Grundlayout, Gesellschaftswechsel,
   Freigaben im Browser, REST `/api/v1`, `accounti serve`.
3. **Paket 3 — Betrieb:** Protokollierung ohne Personenbezug, verschlüsselte Sicherung und
   Wiederherstellung, Aufbewahrung und Löschkonzept, geplanter Lauf, Dockerfile, Compose,
   `docs/betrieb.md`; Probe mit `docker compose up` und Alembic gegen PostgreSQL.

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Code-Ort | `auth/` (Fachlogik Anmeldung/Rechte), `api/` (FastAPI: `app.py`, `seiten/`, `rest/`, `vorlagen/`, `statisch/`), `betrieb/` (Gesellschaften, Sicherung, Aufbewahrung, Protokoll, Planer); Modelle `models/auth.py`, Tabellen `db/tabellen_auth.py`, Repository `db/repo_auth.py`; Befehle `befehle/{benutzer,token,gesellschaft,sicherung,betrieb}.py` | Gerüst „Neuen Baustein anschließen“ |
| Passwort-Hash | `hashlib.scrypt` N = 2^17, r = 8, p = 1, 16 Byte Salz, 32 Byte Ergebnis; Format `scrypt$<log2 N>$<r>$<p>$<salz>$<hash>` (Base64); Vergleich mit `hmac.compare_digest`; schwächere gespeicherte Parameter werden bei der nächsten Anmeldung neu gehasht. Keine neue Abhängigkeit | OWASP: scrypt, wenn Argon2id nicht ohne Zusatzpaket verfügbar ist; Parameter im Hash erlauben spätere Anhebung |
| Passwortregeln | 12–128 Zeichen, keine Zusammensetzungsregeln, nicht gleich/enthaltend den Benutzernamen, kleine eingebaute Sperrliste häufiger Passwörter | NIST 800-63B-4: mit zweitem Faktor ≥ 8, keine Kompositionsregeln, Sperrliste; 12 als Standard (`auth.passwort_mindestlaenge`), 128 als Obergrenze gegen Rechenlast |
| Zweiter Faktor | TOTP nach RFC 6238 mit `hmac` (SHA-1, 6 Stellen, 30 s — was Authenticator-Apps können), 20-Byte-Geheimnis, Toleranz ±1 Schritt, **jeder Schritt nur einmal** (letzter angenommener Schritt am Benutzer); Geheimnis mit dem Tresor (`ACCOUNTI_SCHLUESSEL`, AES-GCM, an die Benutzer-ID gebunden) verschlüsselt; aktiv erst nach Eingabe eines gültigen Codes | RFC 6238 5.1/5.2; Geheimnis muss lesbar bleiben, also verschlüsseln statt hashen |
| Wiederherstellungscodes | 10 Codes `xxxxx-xxxxx` (Alphabet ohne 0/O/1/I/L, ~50 Bit), scrypt mit N = 2^14 gehasht, je Code genau einmal; neue Codes ersetzen alle alten | NIST: einmalig, unter 112 Bit gesalzen gehasht; geringere Kosten, weil bis zu 10 Hashes je Versuch |
| Anmeldung | ein Formular: Benutzer, Passwort, Einmalcode (TOTP oder Wiederherstellungscode). Ohne eingerichteten zweiten Faktor keine Anmeldung. Fehler sagen nie, was falsch war; unbekannte Benutzer kosten dieselbe Hash-Zeit | Akzeptanz 4; kein halb angemeldeter Zustand, keine Benutzeraufzählung |
| Sperre | nach `auth.sperre_nach_fehlversuchen` (5) Fehlversuchen in Folge `auth.sperre_minuten` (15) gesperrt — für Web, CLI-Einmalcode und Wiederherstellungscode gleich; Erfolg setzt zurück; `benutzer entsperren` | NIST erlaubt ≤ 100; 5 bremst Raten bei 6-stelligen Codes wirksam |
| Sitzungen | 256-Bit-Zufallstoken im Cookie `__Host-accounti_sitzung` (`Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`), in der Datenbank nur SHA-256; Leerlauf 30 min, absolut 8 h (`auth.sitzung_*`); Abmelden, Passwortwechsel, Sperre und Rollenänderung beenden Sitzungen serverseitig; ohne TLS (Entwicklung) `server.cookie_sicher: false` → Cookie `accounti_sitzung` ohne `Secure` | OWASP Session Management |
| CSRF | Token = HMAC-SHA-256 des Sitzungstokens (nichts zu speichern), Pflicht bei jeder nicht lesenden Anfrage mit Sitzung (Formularfeld `csrf` oder Kopf `X-CSRF-Token` für HTMX); Anmeldeformular mit Double-Submit-Cookie; dazu `SameSite=Strict` | Synchronizer-Token ohne Serverzustand; Login-CSRF abgedeckt |
| Formulare | `application/x-www-form-urlencoded` selbst lesen (`api/formular.py`, Größengrenze), Multipart über `belege.webhook.anfrage` | keine neue Abhängigkeit (`python-multipart`) |
| Rollen → Rechte | `betrachter`: lesen · `buchhalter`: lesen, buchen, Belege einliefern, Läufe starten, Buchungen freigeben (prüfen) · `freigeber`: lesen, Buchungen, Zahlungsläufe und Steuermeldungen freigeben · `verwalter`: lesen, verwalten. Ein Benutzer kann je Gesellschaft mehrere Rollen haben; Rechte = Vereinigung | Spec 4.1; additive Rollen statt Hierarchie: Buchen und Zahlungsfreigabe bleiben trennbar (Vier-Augen) |
| Rechte im Code | `Recht`-Enum und `erfordert(Recht.X)` als FastAPI-Dependency; in der CLI `pruefe_befehlsrecht(db, config, Recht.X, person)` | dieselbe Tabelle für Browser, API und CLI |
| CLI-Identität | Person wie bisher (`zahlung`: mit Vier-Augen der Anmeldename des Betriebssystems, sonst `--von`/`ACCOUNTI_BENUTZER`; `ustva`: `--von`). Ohne eingerichtete Benutzer: keine Prüfung (wie bisher). Mit Benutzern: Person muss Benutzer mit dem Recht in der aktiven Gesellschaft sein; mit `auth.einmalcode_bestaetigung` (Standard an) fragt die CLI ihren Einmalcode ab (`ACCOUNTI_EINMALCODE` für Skripte) | ein Name in einer Umgebungsvariable beweist nichts; der zweite Faktor bindet die Freigabe an die Person |
| Verwaltung in der CLI | `benutzer …`/`token …` brauchen einen `verwalter` mit Einmalcode — erst, sobald ein Verwalter seinen zweiten Faktor eingerichtet hat (vorher Einrichtungsphase); der erste Benutzer muss Verwalter sein | sonst sperrt man sich beim Einrichten aus |
| API-Token | `accounti_api_` + 256 Bit, gespeichert nur SHA-256 (wie Webhook-Token); je Token eine Gesellschaft und Rechte aus `opos:lesen`, `buchungen:lesen`, `belege:schreiben`, `laeufe:starten`; optional Ablaufdatum; widerrufbar. Fehlendes/ungültiges Token → 401, fehlendes Recht → 403 mit `WWW-Authenticate: Bearer error="insufficient_scope"` (RFC 6750). **Kein** Recht zum Freigeben per Token | Integrationen Akz. 7; Freigaben bleiben menschlich mit zweitem Faktor |
| REST-Belege | `POST /api/v1/belege` liest wie der Webhook (Rohdaten, Multipart, JSON/Base64), prüft Größe und Typ vor dem Speichern, nimmt über `belege.pipeline.nimm_auf` mit Kanal `api` auf, serialisiert je Gesellschaft | eine Pipeline für alle Kanäle |
| REST-Läufe | `POST /api/v1/laeufe/bank` (= `bank lauf` ohne LLM) und `/laeufe/aufgaben` (Prüfläufe + Erinnerungen); synchron, je Gesellschaft und Art höchstens einer gleichzeitig (sonst 409) | kein Hintergrund-Job-System nötig |
| Mehrere Gesellschaften | **eine Datenbank und ein Belegarchiv je Gesellschaft**, eingetragen in der Registry `gesellschaften.eintraege` (Kürzel → Name, Datenbank, Archiv, Konfiguration, Regeln) plus eine **Systemdatenbank** für Benutzer, Rollen, Sitzungen und Token. Ohne Registry gibt es genau eine Gesellschaft `standard`, und die Systemdatenbank ist ihre Datenbank | Trennung durch Bau statt durch Filter: keine der ~80 Tabellen braucht eine Spalte `gesellschaft`, kein Abfragefehler kann Daten der anderen Gesellschaft zeigen; Nummernkreise, Bankkonten und Abschlüsse liegen ohnehin in der Datenbank, Kontenrahmen und Wirtschaftsjahr in der Konfiguration (`buchhaltung.kontenrahmen`, `datev.wirtschaftsjahr_beginn`); Sicherung je Gesellschaft. Verworfen: Spalte `gesellschaft_id` in jeder Tabelle (jede Abfrage aller Bausteine ändern, Baustein 7 baut parallel), Schema je Gesellschaft (nur PostgreSQL) |
| CLI-Option | `accounti --gesellschaft K …` (oder `ACCOUNTI_GESELLSCHAFT`) im Typer-Callback von `cli.py`: setzt über `Context.default_map` die Standardwerte von `--db`, `--archiv` und `--config` **jedes** Befehls (die Option heißt in allen 127 Befehlen gleich); ausdrücklich angegebene Optionen gewinnen. Ohne Gesellschaft gelten `ACCOUNTI_DB`, `ACCOUNTI_ARCHIV`, `ACCOUNTI_KONFIG`, sonst die bisherigen Standards. Mit mehreren Einträgen ohne `standard` verlangen Datenbefehle die Option | ein Eingriff an einer Stelle statt in 127 Befehlen; ohne Option und ohne Umgebung verhält sich alles wie bisher |
| Registry-Ort | Abschnitt `gesellschaften` der globalen Konfiguration (`ACCOUNTI_KONFIG`, sonst `config/accounti.yaml`); Werte mit `${VARIABLE}` (Datenbank-URLs mit Passwort) | Geheimnisse aus der Umgebung |
| Web und Gesellschaft | die Sitzung trägt die aktive Gesellschaft; jede Anfrage prüft die Mitgliedschaft neu; `POST /gesellschaft` wechselt (CSRF). Alle Seiten holen Datenbank, Archiv und Konfiguration über die Dependency `gesellschaft` — es gibt keinen zweiten Weg | Akzeptanz 5: „alle Ansichten konsistent“ |
| Sicherung | `accounti sicherung erstellen --ziel DATEI`: Tar-Strom aus `manifest.json` (Zeilenzahl und SHA-256 je Tabelle, SHA-256 je Archivdatei), einer JSON-Zeilen-Datei je Tabelle (typgetreu: Decimal, Datum, Zeit, JSON) und den Archivdateien; verschlüsselt mit AES-256-GCM in 1-MiB-Stücken (STREAM: Zähler + Endmarke im Nonce, Kopf als zusätzliche Daten), Schlüssel je Sicherung per HKDF-SHA-256 aus `ACCOUNTI_SICHERUNG_SCHLUESSEL` (sonst `ACCOUNTI_SCHLUESSEL`) und Zufallssalz; Datei `0600`, atomar geschrieben. Sitzungen werden nicht gesichert | datenbankunabhängig (SQLite ↔ PostgreSQL), kein `pg_dump` im Abbild nötig; Stücke erlauben große Archive, Abschneiden und Umsortieren fallen auf |
| Wiederherstellung | nur in eine **leere** Umgebung (keine Zeile in einer accounti-Tabelle, Archivordner leer oder fehlt); Tabellen in Abhängigkeitsreihenfolge mit Core-INSERT in **einer** Transaktion, Zeilenzahl und Hash je Tabelle geprüft, Archivdateien nur unter `ab/cd/<hash>.<endung>`, Inhalt = Hash; bei jedem Fehler Rollback und Entfernen der geschriebenen Dateien; PostgreSQL-Sequenzen nachgezogen. `accounti sicherung pruefen` prüft ohne zu schreiben | Akzeptanz 7; nichts wird überschrieben; Hash-Ketten bleiben gültig, weil Zeilen bytegleich zurückkommen |
| Aufbewahrung | `betrieb/aufbewahrung.py`: Fristen je Unterlagenart nach § 147 AO/§ 14b UStG mit Gültigkeit (Buchungsbelege 8 Jahre, Ausnahme Institute 10), Beginn Jahresende; `accounti betrieb aufbewahrung` zeigt, was frühestens ausgesondert werden **dürfte** — gelöscht wird nichts; die Ablaufhemmung (§ 147 Abs. 3 Satz 3) prüft ein Mensch | Löschkonzept, das die Frist kennt; Belegarchiv bleibt ohne Löschpfad |
| Protokollierung | `betrieb/protokoll.py`: ein Filter für alle Logger schwärzt IBAN, E-Mail-Adressen, Bearer-/accounti-Token, Passwörter in URLs und Schlüssel-Parameter; das Zugriffsprotokoll der App schreibt Methode, Pfad ohne Abfrage, Status und Dauer — ohne IP und ohne Benutzer; das Uvicorn-Zugriffsprotokoll ist aus | Spec 4.6: weder Zugangsdaten noch Belegtexte im Log |
| Geplanter Lauf | `accounti betrieb lauf --intervall-minuten 60` ruft je Gesellschaft `bank lauf` und `aufgaben lauf` als eigene Prozesse; SIGTERM beendet sauber; `--einmal` für Cron | Compose-Dienst `lauf` ohne Cron im Abbild |
| Docker | `python:3.12-slim-bookworm`, Benutzer `accounti` (UID 10001), Paket per `pip install .`, `tesseract-ocr-deu` optional (Build-Argument), Gesundheitsprüfung `/gesund`; Compose mit `db` (postgres:16-alpine, kein veröffentlichter Port), `app` (`accounti serve`, nur `127.0.0.1`) und `lauf`; Geheimnisse ausschließlich aus `.env`/Umgebung, `.dockerignore` hält `config/accounti.yaml`, `.env`, Datenbanken und Archive aus dem Abbild | Spec 4.6, Akzeptanz 6 |
| Schema im Container | die Befehle legen fehlende Tabellen beim Start an (`init_db`, wie bisher); Upgrades bestehender Datenbanken mit `alembic upgrade head` | neue Tabellen bekommen ihre Migration beim Zusammenführen |
| `serve` | der vorhandene Platzhalter `accounti serve` in `cli.py` ruft jetzt `accounti.api.server.starte` (Uvicorn, ohne Zugriffsprotokoll, `proxy_headers` nur für `server.vertrauenswuerdige_proxies`) | Spec 4.7 nennt genau diesen Befehl |
| Konfiguration | Abschnitte `auth` (`auth/einstellungen.py`), `server` (`api/einstellungen.py`, der Abschnitt steht schon in der Beispielkonfiguration), `gesellschaften` (`betrieb/gesellschaften.py`), `betrieb` (`betrieb/einstellungen.py`) — alle optional mit Standardwerten | Dateiregeln des Projekts |

## Aufgaben

### Paket 1 — Anmeldung, Rollen und Gesellschaften in der CLI

- [x] **Modelle und Tabellen** (`models/auth.py`, `db/tabellen_auth.py`, `db/repo_auth.py`): Benutzer, Rollenzuordnung je Gesellschaft, Wiederherstellungscodes, Sitzungen, API-Token, Ereignisprotokoll (nur anfügen: ORM-Sperre, SQLite-Trigger per `after_create`) (`tests/test_auth_repo.py`).
- [x] **Passwort** (`auth/passwort.py`): scrypt-Format, falsches Passwort, Parameter-Anhebung, Regeln (`tests/test_auth_passwort.py`).
- [x] **TOTP** (`auth/totp.py`): RFC-6238-Prüfwerte (Anhang B, SHA-1/256/512), Toleranz, otpauth-URI (`tests/test_auth_totp.py`).
- [x] **Dienst** (`auth/dienst.py`, `auth/wiederherstellung.py`, `auth/einstellungen.py`): anlegen, 2FA einrichten/bestätigen, Wiederherstellungscodes (genau einmal), Anmeldung (Akzeptanz 4), Code nur einmal, Sperre, Fehlversuche überstehen den Rollback, Sitzungen (Leerlauf, absolut, Abmelden, Passwortwechsel, Rollenänderung), Rechte je Gesellschaft (`tests/test_auth_dienst.py`).
- [x] **API-Token** (`auth/token.py`): Klartext einmal, nur Hash gespeichert, Rechte, Ablauf, Widerruf (`tests/test_auth_token.py`).
- [x] **Registry** (`betrieb/gesellschaften.py`): Abschnitt `gesellschaften`, `${VAR}` erst bei Bedarf, Kürzel, Standard, Systemdatenbank, keine geteilte Datenbank/kein geteiltes Archiv (`tests/test_betrieb_gesellschaften.py`).
- [x] **Kontext und Option** (`betrieb/kontext.py`, `betrieb/cli.py`, Callback in `cli.py`): `--gesellschaft`, `ACCOUNTI_GESELLSCHAFT`, `ACCOUNTI_DB/ARCHIV/KONFIG`; jeder Befehl mit `--db`/`--archiv`/`--config` bekommt die Werte der Gesellschaft; ausdrückliche Optionen gewinnen; Akzeptanz 5 in der CLI; `accounti gesellschaft liste|zeigen` ohne Passwörter (`tests/test_cli_gesellschaft.py`).
- [x] **CLI-Rechte** (`auth/cli.py`): ohne Benutzer wie bisher; Person ohne Recht abgewiesen; Einmalcode; Einrichtungsphase der Verwaltung (`tests/test_auth_cli.py`).
- [x] **Freigaben anbinden:** `zahlung freigeben`, `ustva freigeben`, `ustva dauerfrist --freigeben` (Akzeptanz 3 in der CLI) (`tests/test_cli_rechte_freigaben.py`).
- [x] **CLI** `accounti benutzer anlegen|2fa|codes|liste|rolle|passwort|sperren|entsperren|protokoll` und `accounti token anlegen|liste|widerrufen` (`tests/test_cli_benutzer.py`).

### Paket 2 — Web-Gerüst und REST-API

- [x] **App-Fabrik und Dienste** (`api/app.py`, `api/dienste.py`, `api/einstellungen.py`, `api/sicherheit.py`): Systemdatenbank, Gesellschaften, Engines je Gesellschaft, Sicherheitskopfzeilen, `/gesund` (`tests/test_api_anmeldung.py::test_sicherheitskopfzeilen`, `::test_gesund`).
- [x] **Anmeldung** (`api/sitzung.py`, `api/seiten/anmeldung.py`, `api/formular.py`): Formular mit Double-Submit, Anmeldung ohne zweiten Faktor scheitert (Akzeptanz 4 im Browser), Cookie-Attribute, Abmelden serverseitig, Leerlauf, Sperre, Weiterleitung nur relativ (`tests/test_api_anmeldung.py`).
- [x] **CSRF und Rollen-Dependency** (`api/sitzung.py`): POST ohne/mit falschem Token, fremde Seite → 403; `X-CSRF-Token` für HTMX (`tests/test_api_anmeldung.py::test_csrf_falsch_oder_fremde_seite`).
- [x] **Registry, Layout, Start, Gesellschaftswechsel** (`api/registry.py`, `api/vorlagen.py`, `api/vorlagen/`, `api/statisch/`, `api/seiten/start.py`, `api/seiten/gesellschaft.py`): Akzeptanz 5 im Browser über **alle** Seiten, Benutzer der Gesellschaft A sieht B nicht, Navigation nach Rechten, Autoescape (`tests/test_api_gesellschaften.py`, `tests/test_api_app.py`).
- [x] **Freigaben im Browser** (`api/seiten/freigaben.py`): Zahlungslauf (auch Vier-Augen) und USt-VA über dieselben Funktionen wie die CLI, mit frischem Einmalcode; Rechte-Matrix jede Rolle × jeder Endpunkt, Vollständigkeit der Matrix (Akzeptanz 3) (`tests/test_api_rechte_matrix.py`).
- [x] **REST** (`api/rest/`): `ich`, offene Posten, Buchungen, Belege (Pipeline, Kanal `api`), Läufe; Token-Rechte je Endpunkt (Integrationen Akz. 7), Gesellschaft des Tokens, Ablauf und Widerruf, keine Sitzung als Token (`tests/test_api_rest.py`, `tests/test_api_rechte_matrix.py`).
- [x] **Protokollierung** (`betrieb/protokoll.py`, `api/sicherheit.py`): Schwärzung an jedem Handler, Zugriffsprotokoll ohne Abfrage und IP, HTTP-Bibliotheken leise; Test gegen die Ausgabe eines Durchlaufs mit Namen, IBAN, Token und Passwort (`tests/test_betrieb_protokoll.py`).
- [x] **`accounti serve`** (`api/server.py`, Platzhalter in `cli.py` ersetzt) (`tests/test_api_server.py`).

### Paket 3 — Betrieb

- [ ] **Verschlüsselung** (`betrieb/verschluesselung.py`): Stückweise AES-GCM, falscher Schlüssel, manipuliert, abgeschnitten, umsortiert (`tests/test_betrieb_verschluesselung.py`).
- [ ] **Sicherung** (`betrieb/sicherung.py`, `befehle/sicherung.py`): erstellen, prüfen, wiederherstellen in eine leere Umgebung — Buchungen und Belege vollständig (Akzeptanz 7), nicht leer → Abbruch, Pfade im Archiv, Typen (`tests/test_betrieb_sicherung.py`, `tests/test_cli_sicherung.py`).
- [ ] **Aufbewahrung** (`betrieb/aufbewahrung.py`, `befehle/betrieb.py aufbewahrung`) (`tests/test_betrieb_aufbewahrung.py`).
- [ ] **Geplanter Lauf** (`betrieb/planer.py`, `befehle/betrieb.py lauf`) (`tests/test_betrieb_planer.py`).
- [ ] **Docker** (`Dockerfile`, `docker-compose.yml`, `.dockerignore`, `docs/betrieb.md`): `docker compose up` mit Projekt `accounti-test-…` geprüft (Akzeptanz 6), Alembic gegen PostgreSQL; Abbild ohne Geheimnisse (`tests/test_betrieb_docker.py` prüft die Dateien statisch).
- [ ] **Abschluss:** gegnerische Prüfung, `pytest`, `ruff`, `mypy` grün; Doku-Bausteine.

## Schnittstelle für die Web-Oberfläche

Die Supervisions-Queue, Auswertungen und die Zweisprachigkeit (Spec 4.2, 4.3, 4.5) entstehen
auf diesem Gerüst, ohne `app.py`, `sitzung.py` oder das Grundlayout umzubauen.

**Neue Seite = neues Modul** in `src/accounti/api/seiten/<bereich>.py` — automatisch eingehängt
(`api/registry.routermodule`, Muster wie `accounti.befehle`; Module mit `_` am Anfang zählen
nicht):

```python
from typing import Annotated
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from accounti.api.formular import formular            # urlencoded-Formular, zwischengespeichert
from accounti.api.registry import Navigationspunkt
from accounti.api.sitzung import Angemeldet, dienste_von, erfordert, gesellschaft_db
from accounti.api.vorlagen import seite
from accounti.models.auth import Recht

router = APIRouter()
NAVIGATION = [Navigationspunkt("Prüfen", "/pruefen", Recht.BUCHEN, reihenfolge=10)]

@router.get("/pruefen", response_class=HTMLResponse)
async def queue(
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.BUCHEN))],   # sonst 303 / 403
    s: Annotated[Session, Depends(gesellschaft_db)],              # DB der aktiven Gesellschaft
) -> HTMLResponse:
    vorschlaege = await run_in_threadpool(lade_pruefliste, s)     # dieselbe Funktion wie die CLI
    return seite(request, "pruefen.html", {"titel": "Prüfen", "vorschlaege": vorschlaege})

@router.post("/pruefen/{buchung_id}/freigeben")
async def freigeben(
    buchung_id: str,
    request: Request,
    a: Annotated[Angemeldet, Depends(erfordert(Recht.BUCHUNG_FREIGEBEN))],
    s: Annotated[Session, Depends(gesellschaft_db)],
) -> HTMLResponse:
    felder = await formular(request)    # CSRF ist an dieser Stelle schon geprüft
    ...                                 # Person für Journal/geprueft_von: a.benutzer.name
```

- **Rechte** (`models/auth.py`, Rollen → Rechte in `ROLLEN_RECHTE`): `Recht.LESEN`, `BUCHEN`
  (erfassen, prüfen, korrigieren), `BELEGE_EINLIEFERN`, `LAEUFE_STARTEN`, `BUCHUNG_FREIGEBEN`,
  `ZAHLUNG_FREIGEBEN`, `STEUER_FREIGEBEN`, `VERWALTEN`. `erfordert(Recht.X)` liefert
  `Angemeldet` mit `benutzer` (`name` für Journal und `geprueft_von`), `gesellschaft`
  (`kuerzel`, `name`, `datenbank`, `archiv`, `konfiguration`, `regeln`), `gesellschaften` (für
  den Wechsel), `rechte`, `darf(recht)` und `csrf`. Ohne Sitzung: Seiten 303 nach
  `/anmelden?weiter=…`, Pfade unter `/api/` 401; ohne Recht 403. `AngemeldetDep` gibt es für
  Seiten, die nur eine Anmeldung brauchen.
- **Daten nur über `gesellschaft_db`** und `a.gesellschaft`: Archiv
  `BelegArchiv(a.gesellschaft.archiv)`, Konfiguration `lade_…(a.gesellschaft.konfiguration)`,
  Regeln `lade_regeln(a.gesellschaft.regeln)`. Nie `config/accounti.yaml` oder `archiv/belege`
  fest einsetzen und nie einen Lader ohne Pfad aufrufen — sonst zeigt eine Seite nach dem Wechsel
  die falsche Gesellschaft. Committen tut die Seite selbst (`s.commit()`).
- **Blockierendes** (Datenbank, OCR, scrypt) in `run_in_threadpool` oder als `def`-Handler.
- **Formulare:** jedes nicht lesende Formular trägt
  `<input type="hidden" name="csrf" value="{{ csrf }}">`; HTMX schickt den Kopf, z. B.
  `<body hx-headers='{"X-CSRF-Token": "{{ csrf }}"}'>`. Felder liest `await formular(request)`;
  Datei-Uploads liest `accounti.belege.webhook.anfrage.lies_anfrage` (Multipart mit der
  Standardbibliothek). `python-multipart` ist nicht installiert, `request.form()` geht nicht.
- **Freigaben mit frischem Einmalcode:** vor jeder Freigabe
  `api.seiten.freigaben.bestaetige_einmalcode(dienste_von(request), a, felder["einmalcode"])`
  (Schalter `auth.einmalcode_bestaetigung`) — wie bei Zahlungslauf und USt-VA.
- **Vorlagen** in `src/accounti/api/vorlagen/` mit `{% extends "basis.html" %}`, Blöcke `titel`,
  `kopf` (eigene Stylesheets/Skripte), `inhalt`; Kontext immer `angemeldet`, `csrf`,
  `navigation`, `version`, `titel`, `meldung`, `fehler`. Autoescape und `StrictUndefined` sind
  an; Filter `betrag` (1.234,50) und `datum` (TT.MM.JJJJ). Das Layout zeigt „Gesellschaft:
  **Name**“ und bei mehreren den Wechsler (`POST /gesellschaft`). Für die Zweisprachigkeit gibt
  es noch keinen Übersetzungsmechanismus (`lang="de"` im Layout).
- **Statisches** in `src/accounti/api/statisch/` unter `/statisch/…` — HTMX als Datei dort
  ablegen, nicht von einem CDN laden. Die CSP erlaubt nur eigene Skripte und Stile, keine
  Inline-Skripte und keine `style=`-Attribute; Belege dürfen in `<iframe>`/`<object>` derselben
  Herkunft (`frame-src`/`object-src 'self'`, `frame-ancestors 'self'`). Antworten außer
  `/statisch` tragen `Cache-Control: no-store`.
- **Pfade** enthalten nur IDs, keine Namen — das Zugriffsprotokoll schreibt den Pfad (ohne
  Abfrage).
- **Rechte-Matrix:** jeder neue Endpunkt gehört in `SEITEN` bzw. `REST` in
  `tests/test_api_rechte_matrix.py`, sonst schlägt `test_jeder_endpunkt_steht_in_der_matrix`
  fehl.
- **REST-Module** in `src/accounti/api/rest/` (Präfix `/api/v1`):
  `Depends(erfordert_recht(TokenRecht.X))` für das Recht, `TokenDb` für die Datenbank der
  Gesellschaft des Tokens; Beträge als Zeichenkette. Neue Token-Rechte ergänzen `TokenRecht`.
- **Testen:** `tests/api_hilfe.py` — `webwelt(tmp_path)` (zwei Gesellschaften, steuerbare `Uhr`),
  `person(name, Rolle…)`, `angemeldet(name)` → Testclient mit Sitzung, `token(kuerzel,
  TokenRecht…)`, `csrf(client)`; Basisadresse `https://accounti.test` (das Cookie ist `Secure`).
- **Start:** `accounti serve` (mit Registry alle Gesellschaften); in Tests
  `erstelle_app(Dienste(systemdatenbank, {kuerzel: Gesellschaft}, uhr=…, schluessel=…))`.

## Akzeptanzkriterien → Tests

*(wird beim Bau ausgefüllt)*

## Grenzen

*(wird beim Bau ausgefüllt)*

## Doku-Bausteine

*(am Ende)*
