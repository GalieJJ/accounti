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
3. **Paket 3 — Betrieb:** verschlüsselte Sicherung und Wiederherstellung, Aufbewahrung und
   Löschkonzept, geplanter Lauf, Dockerfile, Compose, `docs/betrieb.md`; Probe mit
   `docker compose up` und Alembic gegen PostgreSQL. (Die Protokollierung ohne Personenbezug
   kam schon mit Paket 2, weil `accounti serve` sie braucht.)

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Code-Ort | `auth/` (Fachlogik Anmeldung/Rechte), `api/` (FastAPI: `app.py`, `seiten/`, `rest/`, `vorlagen/`, `statisch/`), `betrieb/` (Gesellschaften, Sicherung, Aufbewahrung, Protokoll, Planer); Modelle `models/auth.py`, Tabellen `db/tabellen_auth.py`, Repository `db/repo_auth.py`; Befehle `befehle/{benutzer,token,gesellschaft,sicherung,betrieb}.py` | Gerüst „Neuen Baustein anschließen“ |
| Passwort-Hash | `hashlib.scrypt` N = 2^17, r = 8, p = 1, 16 Byte Salz, 32 Byte Ergebnis; Format `scrypt$<log2 N>$<r>$<p>$<salz>$<hash>` (Base64); Vergleich mit `hmac.compare_digest`; schwächere gespeicherte Parameter werden bei der nächsten Anmeldung neu gehasht. Keine neue Abhängigkeit | OWASP: scrypt, wenn Argon2id nicht ohne Zusatzpaket verfügbar ist; Parameter im Hash erlauben spätere Anhebung |
| Passwortregeln | 12–128 Zeichen, keine Zusammensetzungsregeln, nicht gleich/enthaltend den Benutzernamen, kleine eingebaute Sperrliste häufiger Passwörter | NIST 800-63B-4: mit zweitem Faktor ≥ 8, keine Kompositionsregeln, Sperrliste; 12 als Standard (`auth.passwort_mindestlaenge`), 128 als Obergrenze gegen Rechenlast |
| Zweiter Faktor | TOTP nach RFC 6238 mit `hmac` (SHA-1, 6 Stellen, 30 s — was Authenticator-Apps können), 20-Byte-Geheimnis, Toleranz ±1 Schritt, **jeder Schritt nur einmal** (letzter angenommener Schritt am Benutzer); Geheimnis mit dem Tresor (`ACCOUNTI_SCHLUESSEL`, AES-GCM, an die Benutzer-ID gebunden) verschlüsselt; aktiv erst nach Eingabe eines gültigen Codes | RFC 6238 5.1/5.2; Geheimnis muss lesbar bleiben, also verschlüsseln statt hashen |
| Wiederherstellungscodes | 10 Codes `xxxxx-xxxxx` (Alphabet ohne 0/O/1/I/L, ~50 Bit), gespeichert als HMAC-SHA-256 über Benutzer-ID und Code mit einem aus `ACCOUNTI_SCHLUESSEL` abgeleiteten Schlüssel (Pepper), geprüft mit einem Nachschlagen; je Code genau einmal; neue Codes ersetzen alle alten | gleiche Arbeit je Anmeldeversuch (zehn scrypt-Hashes verrieten über die Antwortzeit, ob das Passwort stimmte — Prüfbefund). Abweichung von NIST (unter 112 Bit: Passwort-Hash): ohne den Schlüssel ist aus der Datenbank allein nichts zu erraten; wer den Schlüssel hat, entschlüsselt ohnehin das TOTP-Geheimnis |
| Anmeldung | ein Formular: Benutzer, Passwort, Einmalcode (TOTP oder Wiederherstellungscode). Ohne eingerichteten zweiten Faktor keine Anmeldung. Fehler sagen nie, was falsch war; unbekannte Benutzer kosten dieselbe Hash-Zeit | Akzeptanz 4; kein halb angemeldeter Zustand, keine Benutzeraufzählung |
| Sperre | jeder Versuch wird vor der Prüfung atomar gezählt (`UPDATE … SET fehlversuche = fehlversuche + 1 WHERE nicht gesperrt`); jeder `auth.sperre_nach_fehlversuchen`-te (5) Fehlversuch in Folge sperrt `auth.sperre_minuten` (15, höchstens 1440), ab `auth.fehlversuche_obergrenze` (100) bis `benutzer entsperren`; **Browser und CLI zählen getrennt** (`fehlversuche`/`cli_fehlversuche`), die CLI immer mit den Standardwerten; mit gültigem zweitem Faktor entsperrt sich jeder auf der Server-Shell selbst; Erfolg setzt den Zähler des Kanals zurück; eine Sperre nach Fehlversuchen beendet keine Sitzungen | NIST: höchstens 100 in Folge; 5 bremst Raten bei 6-stelligen Codes wirksam; unter Parallelität keine Prüfung über das Fenster hinaus; Sitzungen nicht beenden, sonst wirft jeder, der den Namen kennt, den Freigeber hinaus; getrennte Zähler, damit niemand aus dem Netz den letzten Verwalter dauerhaft aussperrt — ohne gesperrte Verwalter als „nicht vorhanden“ zu werten (das öffnete die Einrichtungsphase aus dem Netz); Sperrwerte nicht aus frei wählbaren Dateien, sonst sperrt eine `fehlversuche_obergrenze: 1` jeden mit einem falschen Code (Nachprüfung R2-M1) |
| Sitzungen | 256-Bit-Zufallstoken im Cookie `__Host-accounti_sitzung` (`Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`), in der Datenbank nur SHA-256; Leerlauf 30 min, absolut 8 h (`auth.sitzung_*`); Abmelden, Passwortwechsel, Sperre und Rollenänderung beenden Sitzungen serverseitig; ohne TLS (Entwicklung) `server.cookie_sicher: false` → Cookie `accounti_sitzung` ohne `Secure` | OWASP Session Management |
| CSRF | Token = HMAC-SHA-256 des Sitzungstokens (nichts zu speichern), Pflicht bei jeder nicht lesenden Anfrage mit Sitzung (Formularfeld `csrf` oder Kopf `X-CSRF-Token` für HTMX); Anmeldeformular mit Double-Submit-Cookie; dazu `SameSite=Strict` | Synchronizer-Token ohne Serverzustand; Login-CSRF abgedeckt |
| Formulare | `application/x-www-form-urlencoded` selbst lesen (`api/formular.py`, Größengrenze), Multipart über `belege.webhook.anfrage` | keine neue Abhängigkeit (`python-multipart`) |
| Rollen → Rechte | `betrachter`: lesen · `buchhalter`: lesen, buchen, Belege einliefern, Läufe starten, Buchungen freigeben (prüfen) · `freigeber`: lesen, Buchungen, Zahlungsläufe und Steuermeldungen freigeben · `verwalter`: lesen, verwalten. Ein Benutzer kann je Gesellschaft mehrere Rollen haben; Rechte = Vereinigung | Spec 4.1; additive Rollen statt Hierarchie: Buchen und Zahlungsfreigabe bleiben trennbar (Vier-Augen) |
| Rechte im Code | `Recht`-Enum und `erfordert(Recht.X)` als FastAPI-Dependency; in der CLI `pruefe_befehlsrecht(db, config, Recht.X, person)` | dieselbe Tabelle für Browser, API und CLI |
| CLI-Identität | Person wie bisher (`zahlung`: mit Vier-Augen der Anmeldename des Betriebssystems, sonst `--von`/`ACCOUNTI_BENUTZER`; `ustva`: `--von`). Ohne eingerichtete Benutzer: keine Prüfung (wie bisher). Mit Benutzern: Person muss Benutzer mit dem Recht in der Gesellschaft der benutzten Datenbank sein und gibt ihren Einmalcode ein (`ACCOUNTI_EINMALCODE` für Skripte) — in der CLI immer: `auth`-Werte aus `--config`/`ACCOUNTI_KONFIG` wirken dort nur strenger (`auth.cli.streng`). Mit Registry gelten `--db`/`--config` der gewählten Gesellschaft; ein Merker `auth_merker` in jeder Gesellschafts-Datenbank hält fest, zu welcher Systemdatenbank und Gesellschaft sie gehört (leere oder fremde Systemdatenbank → Abbruch) | ein Name in einer Umgebungsvariable beweist nichts; der zweite Faktor bindet die Freigabe an die Person — aber nur, wenn ihn keine frei wählbare Datei abschaltet und die Prüfung die Datenbank trifft, in der freigegeben wird (Prüfbefund) |
| Verwaltung in der CLI | `benutzer …`/`token …` brauchen einen `verwalter` mit Einmalcode — erst, sobald ein Verwalter seinen zweiten Faktor eingerichtet hat (vorher Einrichtungsphase); der erste Benutzer muss Verwalter sein. Ein fremdes Konto verwaltet nur, wer in **jeder** Gesellschaft Verwalter ist, in der es Rollen hat; Token nur in der gewählten Gesellschaft. Eigenes Passwort, eigene Codes und eigenen Faktor ändert jeder selbst — mit seinem schon eingerichteten Faktor; den **ersten** Faktor richtet ein Verwalter ein | sonst sperrt man sich beim Einrichten aus; ohne die Einschränkungen könnte jeder mit Shell-Zugang für fremde Benutzer einen Faktor anlegen, und ein Verwalter von b übernähme den Freigeber von a (Prüfbefunde) |
| Fehlversuche | vor der Prüfung in der Datenbank reserviert (`fehlversuche = fehlversuche + 1` nur, solange nicht gesperrt) und sofort festgeschrieben; Erfolg setzt zurück, die Sperre nicht | parallele Versuche verlieren keine Zählung und kommen nicht an der Sperre vorbei; eine Ausnahme beim Aufrufer rollt sie nicht zurück |
| API-Token | `accounti_api_` + 256 Bit, gespeichert nur SHA-256 (wie Webhook-Token); je Token eine Gesellschaft und Rechte aus `opos:lesen`, `buchungen:lesen`, `belege:schreiben`, `laeufe:starten`; optional Ablaufdatum; widerrufbar. Fehlendes/ungültiges Token → 401, fehlendes Recht → 403 mit `WWW-Authenticate: Bearer error="insufficient_scope"` (RFC 6750). **Kein** Recht zum Freigeben per Token | Integrationen Akz. 7; Freigaben bleiben menschlich mit zweitem Faktor |
| REST-Belege | `POST /api/v1/belege` liest wie der Webhook (Rohdaten, Multipart, JSON/Base64), prüft Größe und Typ vor dem Speichern, nimmt über `belege.pipeline.nimm_auf` mit Kanal `api` auf, serialisiert je Gesellschaft | eine Pipeline für alle Kanäle |
| REST-Läufe | `POST /api/v1/laeufe/bank` (= `bank lauf` ohne LLM) und `/laeufe/aufgaben` (Prüfläufe + Erinnerungen); synchron, je Gesellschaft und Art höchstens einer gleichzeitig — auch gegenüber CLI und Dienst `lauf` (`betrieb/laufsperre.py`: PostgreSQL-Advisory-Lock, SQLite-Dateisperre; sonst 409 bzw. Exit 1) | kein Hintergrund-Job-System nötig; ein `threading.Lock` sah den Prozess des Dienstes `lauf` nicht (Prüfbefund) |
| Mehrere Gesellschaften | **eine Datenbank und ein Belegarchiv je Gesellschaft**, eingetragen in der Registry `gesellschaften.eintraege` (Kürzel → Name, Datenbank, Archiv, Konfiguration, Regeln) plus eine **Systemdatenbank** für Benutzer, Rollen, Sitzungen und Token. Ohne Registry gibt es genau eine Gesellschaft `standard`, und die Systemdatenbank ist ihre Datenbank | Trennung durch Bau statt durch Filter: keine der ~80 Tabellen braucht eine Spalte `gesellschaft`, kein Abfragefehler kann Daten der anderen Gesellschaft zeigen; Nummernkreise, Bankkonten und Abschlüsse liegen ohnehin in der Datenbank, Kontenrahmen und Wirtschaftsjahr in der Konfiguration (`buchhaltung.kontenrahmen`, `datev.wirtschaftsjahr_beginn`); Sicherung je Gesellschaft. Verworfen: Spalte `gesellschaft_id` in jeder Tabelle (jede Abfrage aller Bausteine ändern, Baustein 7 baut parallel), Schema je Gesellschaft (nur PostgreSQL) |
| CLI-Option | `accounti --gesellschaft K …` (oder `ACCOUNTI_GESELLSCHAFT`) im Typer-Callback von `cli.py`: setzt über `Context.default_map` die Standardwerte von `--db`, `--archiv` und `--config` **jedes** Befehls (die Option heißt in allen 127 Befehlen gleich); ausdrücklich angegebene Optionen gewinnen. Ohne Gesellschaft gelten `ACCOUNTI_DB`, `ACCOUNTI_ARCHIV`, `ACCOUNTI_KONFIG`, sonst die bisherigen Standards. Mit mehreren Einträgen ohne `standard` verlangen Datenbefehle die Option | ein Eingriff an einer Stelle statt in 127 Befehlen; ohne Option und ohne Umgebung verhält sich alles wie bisher |
| Registry-Ort | Abschnitt `gesellschaften` der globalen Konfiguration (`ACCOUNTI_KONFIG`, sonst `config/accounti.yaml`); Werte mit `${VARIABLE}` (Datenbank-URLs mit Passwort) | Geheimnisse aus der Umgebung |
| Web und Gesellschaft | die Sitzung trägt die aktive Gesellschaft; jede Anfrage prüft die Mitgliedschaft neu; `POST /gesellschaft` wechselt (CSRF). Alle Seiten holen Datenbank, Archiv und Konfiguration über die Dependency `gesellschaft` — es gibt keinen zweiten Weg | Akzeptanz 5: „alle Ansichten konsistent“ |
| Sicherung | `accounti sicherung erstellen --ziel DATEI`: Tar-Strom aus `manifest.json` (Zeilenzahl und SHA-256 je Tabelle, SHA-256 je Archivdatei, fehlende Archivdateien, Art `gesellschaft`/`system`), einer JSON-Zeilen-Datei je Tabelle (typgetreu: Decimal, Datum, Zeit, JSON) und den Archivdateien; alle Tabellen in **einer** Lese-Transaktion (PostgreSQL `REPEATABLE READ READ ONLY`; SQLite aus einer Kopie über die Backup-API); verschlüsselt mit AES-256-GCM in 1-MiB-Stücken (STREAM: Zähler + Endmarke im Nonce, Kopf als zusätzliche Daten), Schlüssel je Sicherung per HKDF-SHA-256 aus `ACCOUNTI_SICHERUNG_SCHLUESSEL` (sonst `ACCOUNTI_SCHLUESSEL`) und Zufallssalz; Datei `0600`, atomar geschrieben. Sitzungen werden nicht gesichert. Fehlt das Archiv, obwohl Belege darauf verweisen: Abbruch. `--system` sichert die Systemdatenbank | datenbankunabhängig (SQLite ↔ PostgreSQL), kein `pg_dump` im Abbild nötig; Stücke erlauben große Archive, Abschneiden und Umsortieren fallen auf; ohne Schnappschuss ließ sich eine Sicherung aus dem laufenden Betrieb nicht zurückspielen (Prüfbefund) |
| Wiederherstellung | nur in eine **leere** Umgebung (keine Zeile in einer accounti-Tabelle, Archivordner leer oder fehlt) und nur, was zum Ziel passt (Gesellschaft des Manifests, sonst `--fremde-gesellschaft`; Systemdatenbank nur mit `--system`); Tabellen in Abhängigkeitsreihenfolge mit Core-INSERT in **einer** Transaktion, Zeilenzahl und Hash je Tabelle geprüft, Archivdateien nur unter `ab/cd/<hash>[.<endung>]` (Endung ohne `/` und Steuerzeichen), Inhalt = Hash; das Archiv kommt vor dem Festschreiben an seinen Platz; bei jedem Fehler Rollback und Entfernen der geschriebenen Dateien; PostgreSQL-Sequenzen nachgezogen. `accounti sicherung pruefen` prüft ohne zu schreiben | Akzeptanz 7; nichts wird überschrieben; Hash-Ketten bleiben gültig, weil Zeilen bytegleich zurückkommen |
| Aufbewahrung | `betrieb/aufbewahrung.py`: Fristen je Unterlagenart nach § 147 AO/§ 14b UStG mit Gültigkeit (Buchungsbelege 8 Jahre, Ausnahme Institute 10), Beginn Jahresende — für Bücher je Wirtschaftsjahr ab Schluss des Jahres der letzten Eintragung, konservativ frühestens dem nach dem Wirtschaftsjahresende, später bei späterem Abschluss (`abschluesse`); `accounti betrieb aufbewahrung` zeigt, was frühestens ausgesondert werden **dürfte** — gelöscht wird nichts; die Ablaufhemmung (§ 147 Abs. 3 Satz 3) prüft ein Mensch | Löschkonzept, das die Frist kennt (§ 147 Abs. 4 AO: Bücher ab der letzten Eintragung, nicht ab dem Buchungsdatum — Prüfbefund); Belegarchiv bleibt ohne Löschpfad |
| Protokollierung | `betrieb/protokoll.py`: ein Filter für alle Logger schwärzt IBAN, E-Mail-Adressen, Bearer-/accounti-Token, Passwörter in URLs und Schlüssel-Parameter; das Zugriffsprotokoll der App schreibt Methode, Routenvorlage (unbekannte Pfade als `(unbekannt)`), Status und Dauer — ohne IP und ohne Benutzer; unbehandelte Ausnahmen nur mit ihrer Art; alle Engines mit `hide_parameters`; das Uvicorn-Zugriffsprotokoll ist aus | Spec 4.6: weder Zugangsdaten noch Belegtexte im Log — auch nicht in Datenbank-Fehlermeldungen oder über einen Pfad mit `%0A` (Prüfbefunde) |
| Geplanter Lauf | `accounti betrieb lauf --intervall-minuten 60` ruft je Gesellschaft `bank lauf` und `aufgaben lauf` als eigene Prozesse; SIGTERM beendet sauber; `--einmal` für Cron | Compose-Dienst `lauf` ohne Cron im Abbild |
| Docker | `python:3.12-slim-bookworm`, Benutzer `accounti` (UID 10001), Paket per `pip install .`, `tesseract-ocr-deu` optional (Build-Argument), Gesundheitsprüfung `/gesund`; Compose mit `db` (postgres:16-alpine, kein veröffentlichter Port), `app` (`accounti serve`, nur `127.0.0.1`) und `lauf`; Geheimnisse ausschließlich aus `.env`/Umgebung, `.dockerignore` hält `config/accounti.yaml`, `.env`, Datenbanken und Archive aus dem Abbild | Spec 4.6, Akzeptanz 6 |
| Schema im Container | die Befehle legen fehlende Tabellen beim Start an (`init_db`, wie bisher); Upgrades bestehender Datenbanken mit `alembic upgrade head` — `alembic.ini` und `alembic/` liegen unter `/app` im Abbild, `alembic/env.py` nimmt `ACCOUNTI_DB` (keine neue Migration) | neue Tabellen bekommen ihre Migration beim Zusammenführen; ohne die Umgebungsvariable müsste die Datenbank-URL samt Passwort in `alembic.ini` stehen |
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

- [x] **Verschlüsselung** (`betrieb/verschluesselung.py`): Stückweise AES-GCM, falscher Schlüssel, manipuliert, abgeschnitten, umsortiert, Kopf geprüft, Schlüssel aus der Umgebung (`tests/test_betrieb_verschluesselung.py`).
- [x] **Sicherung** (`betrieb/sicherung.py`, `befehle/sicherung.py`): erstellen, prüfen, wiederherstellen in eine leere Umgebung — Buchungen und Belege vollständig (Akzeptanz 7), nicht leer → Abbruch, falscher Schlüssel/verändert → Rollback ohne Rest, fremde Archivdateien, Pfade und Einträge, unpassende Zeilen, typgetreue Werte, ohne Archiv, Ordner als Ziel, mit Gesellschaft (`tests/test_betrieb_sicherung.py`, `tests/test_cli_sicherung.py`).
- [x] **Aufbewahrung** (`betrieb/aufbewahrung.py`, `accounti betrieb aufbewahrung`): Fristen nach § 147 AO/§ 14b UStG, Jahresende, Institute, Bericht ohne Löschen (`tests/test_betrieb_aufbewahrung.py`, `tests/test_cli_sicherung.py::test_aufbewahrung`).
- [x] **Geplanter Lauf** (`betrieb/planer.py`, `accounti betrieb lauf`): Schritte je Gesellschaft, ein Fehler hält die anderen nicht auf, Ausgabe nur geschwärzt, SIGTERM, echter Kindprozess (`tests/test_betrieb_planer.py`).
- [x] **Docker** (`Dockerfile`, `docker-compose.yml`, `.dockerignore`, `docs/betrieb.md`, `alembic/env.py` liest `ACCOUNTI_DB`): `docker compose up` mit Projekt `accounti-test-b10a` ausgeführt (Akzeptanz 6, Ergebnis unten), Alembic gegen PostgreSQL 16; Abbild ohne Geheimnisse (`tests/test_betrieb_docker.py` prüft die Dateien statisch und `alembic upgrade head` über `ACCOUNTI_DB`).
- [x] **Abschluss:** gegnerische Prüfung (Befunde unten), `pytest`, `ruff`, `mypy` grün; Doku-Bausteine.

### Probe mit Docker und PostgreSQL (ausgeführt am 21.10.2026)

Projekt `accounti-test-b10a`, Port `127.0.0.1:18471`, Geheimnisse zufällig in einer `.env`
unter `/tmp`; danach `docker compose down -v` und `docker rmi accounti:accounti-test-b10a`
— keine Container, Volumes, Netze oder Abbilder mit `accounti` blieben zurück, fremde Container
wurden nicht angefasst.

- `docker compose up -d --build`: `db` (postgres:16-alpine) gesund, `app` gesund
  (`HEALTHCHECK` → `/gesund` 200), `lauf` lief jede Minute: `bank lauf → 0`,
  `aufgaben lauf → 1` (ohne Abschnitt `versand` scheitert die Tagesübersicht — Verhalten aus
  Baustein 8). `docker compose stop lauf` beendete den Lauf sofort mit Exit 0 (SIGTERM).
- Im Container mit PostgreSQL: `benutzer anlegen chef --rolle verwalter --rolle freigeber`,
  `benutzer 2fa chef` (TOTP auf dem Host berechnet); Anmeldung ohne Code → 401, mit Code →
  303 und `__Host-`-Cookie, Startseite 200; `token anlegen` mit Wiederherstellungscode;
  `POST /api/v1/belege` → 200 (Belegerkennung lief; das Probe-PDF war absichtlich minimal
  und ging „unlesbar“ zur Prüfung — Tesseract selbst wurde nicht ausgelöst), `GET /api/v1/offene-posten`
  → 200, `GET /api/v1/buchungen` ohne Recht → 403 `insufficient_scope`.
- Sicherung → `pruefen` → `wiederherstellen` in eine neue, leere PostgreSQL-Datenbank:
  Belege, Archivdatei und Benutzer vollständig. Kreuzprobe: Testbestand aus SQLite gesichert,
  in PostgreSQL zurückgespielt, dort wieder gesichert und in SQLite zurückgespielt — alle
  Tabellen Zeile für Zeile gleich (Decimal, Datum, JSON, Wahrheitswerte).
- Protokoll der Container: keine Benutzernamen, Dateinamen, Token, IP-Adressen.
- **Alembic gegen PostgreSQL 16:** alle 18 Migrationen bis `33d478b807fc` laufen fehlerfrei
  (die SQLite-Trigger sind per Dialekt bedingt, `batch_alter_table` wirkt auf PostgreSQL wie
  ein normales `ALTER`). `compare_metadata` gegen die Modelle findet **nur** die sechs neuen
  Tabellen dieses Bausteins samt Indizes (`auth_benutzer`, `auth_rollen`,
  `auth_wiederherstellungscodes`, `auth_sitzungen`, `api_tokens`, `auth_ereignisse`) — keine
  Abweichung bei Typen oder bestehenden Tabellen. Die Migration dafür entsteht beim
  Zusammenführen (mit dem Trigger für `auth_ereignisse` unter SQLite).

### Gegnerische Prüfung (21.10.2026) — Befunde und Behebung

- Fehlversuche wurden als „lesen, +1, schreiben“ gezählt — parallele Versuche hätten Zählungen
  verloren. Jetzt `UPDATE … SET fehlversuche = fehlversuche + 1` in der Datenbank
  (damals `repo_auth.erhoehe_fehlversuche`; nach der zweiten Prüfung ersetzt durch die
  Reservierung **vor** der Prüfung, `repo_auth.reserviere_versuch`, siehe unten).
- Wer Zugang zur Server-Shell hatte, konnte als `ACCOUNTI_BENUTZER=eva` für einen Benutzer
  **ohne** zweiten Faktor einen eigenen anlegen und sich dann im Browser als eva anmelden
  (Passwort vorausgesetzt). Jetzt richtet den ersten zweiten Faktor nur ein Verwalter ein
  (bzw. jeder in der Einrichtungsphase) (`tests/test_auth_cli.py::test_verwaltung_einrichtungsphase_und_danach`).
- Das Cookie des Anmeldeformulars hatte kein `__Host-`-Präfix (eine Subdomain hätte es setzen
  können) — jetzt wie das Sitzungscookie (`tests/test_api_anmeldung.py::test_sitzungscookie_attribute`).
- Eine Sicherung mit Zeilen, die nicht zum Schema passen, endete mit einer rohen
  Datenbankausnahme (deren Text SQL und Werte enthält) — jetzt `SicherungError` ohne Werte,
  Rollback (`tests/test_betrieb_sicherung.py::test_unpassende_zeilen_werden_abgelehnt`);
  fremde Einträge und Pfade (`../`) werden abgelehnt (`::test_fremde_eintraege_werden_abgelehnt`).
- `--ziel /pfad/` für einen noch nicht vorhandenen Ordner schrieb eine Datei namens `pfad` —
  jetzt legt ein `/` am Ende den Ordner an (`tests/test_cli_sicherung.py`).
- Geprüft und in Ordnung: Sitzungs-ID neu nach der Anmeldung, Abmelden serverseitig, Rechte
  bei jeder Anfrage neu gelesen, CSRF an jeder nicht lesenden Anfrage mit Sitzung, REST nur
  mit Token (kein Cookie, also kein CSRF), keine CORS-Freigabe, Weiterleitung nur relativ,
  Autoescape, TOTP-Schritt und Wiederherstellungscode atomar verbraucht, unbekannte Benutzer
  kosten dieselbe Hash-Zeit, Token nur als SHA-256, Rechte-Matrix vollständig, jedes
  Akzeptanzkriterium scheitert im Test, wenn die Prüfung fehlt.

### Zweite gegnerische Prüfung (21.10.2026, Technik und Fachlich) — Befunde und Behebung

Beide Prüfer hielten den Stand für nicht mergefähig. Jeder Befund unten hat einen Test, der
ohne die Korrektur scheitert (Präfix A = Technik, B = Fachlich, wie im Prüfbericht).

- **Sicherung ohne Schnappschuss (A-H1 = B-H2):** jede Tabelle hatte ein eigenes SELECT —
  ein Schreibzugriff zwischen `kontakte` und `offene_posten` ergab eine Sicherung, die
  PostgreSQL beim Zurückspielen ablehnte. Jetzt eine Lese-Transaktion über alle Tabellen
  (`betrieb/sicherung.lesetransaktion`: PostgreSQL `REPEATABLE READ READ ONLY`); eine
  SQLite-Datei wird zuerst mit der Backup-API in eine Temporärdatei kopiert
  (`lesequelle`, ein Schritt — ein ausdrückliches `BEGIN` hätte Schreiber ohne WAL bis zum
  Ende der Sicherung blockiert) (`tests/test_betrieb_sicherung.py::test_sicherung_ist_ein_schnappschuss_ueber_alle_tabellen`,
  `::test_sicherung_ist_ein_schnappschuss_postgresql`,
  `::test_lesetransaktion_postgresql_ist_repeatable_read_read_only`,
  `::test_sqlite_wird_ueber_die_backup_api_gelesen` — PostgreSQL über
  `ACCOUNTI_TEST_PG`, `tests/pg_hilfe.py`; ausgeführt gegen `postgres:16-alpine` im Container
  `accounti-test-pg10a`, danach entfernt).
- **Freigabe-Bindung in der CLI (A-H2, B-H1, A-N3):** Rechte wurden in `-g b` geprüft, während
  `--db` auf a zeigte; `auth.einmalcode_bestaetigung: false` in einem eigenen `--config`
  schaltete den zweiten Faktor ab; eine leere `ACCOUNTI_SYSTEM_DB` ließ jede Prüfung
  entfallen. Jetzt: mit Registry müssen `--db`/`--config` die der gewählten Gesellschaft
  sein; Merker `auth_merker` (Kennung der Systemdatenbank, Bindung jeder
  Gesellschafts-Datenbank an Systemdatenbank und Kürzel) — fail-closed bei leerer, fremder
  oder vertippter Systemdatenbank; `auth`-Werte gelten in der CLI nur in der strengeren
  Richtung (`auth.cli.streng`) (`tests/test_cli_bindung.py`,
  `tests/test_auth_cli.py::test_abgeschalteter_einmalcode_gilt_in_der_cli_nicht` — ersetzt
  den Test, der das Abschalten bestätigt hatte, `::test_strenge_einstellungen_nur_in_die_strengere_richtung`).
- **Kontosperre (A-H3, B-N4):** geprüft wurde vor dem langsamen scrypt, gezählt danach, und
  `setze_sperre` setzte den Zähler auf 0 — 40 parallele Versuche prüften 18 Codes, über die
  Zeit waren Fehlversuche unbegrenzt. Jetzt reserviert ein einziges `UPDATE … SET
  fehlversuche = fehlversuche + 1 WHERE nicht gesperrt` den Versuch vor der Prüfung
  (`repo_auth.reserviere_versuch`); der Zähler läuft über Sperren hinweg, jeder fünfte sperrt
  15 Minuten, ab `auth.fehlversuche_obergrenze` (100) bis `entsperren`; nach Ablauf sperrt
  nicht schon ein Fehlversuch (`tests/test_auth_befunde.py::test_sperre_wirkt_unter_parallelitaet`,
  `::test_zweiter_faktor_allein_unter_parallelitaet`, `::test_sperre_setzt_den_zaehler_nicht_zurueck`,
  `::test_nach_ablauf_sperrt_nicht_schon_ein_fehlversuch`,
  `tests/test_auth_repo.py::test_fehlversuche_in_der_datenbank_gezaehlt` — korrigiert, er
  bestätigte das Zurücksetzen).
- **Antwortzeit (A-M1):** ein wiederherstellungscode-förmiger Code kostete bei richtigem
  Passwort zehn zusätzliche scrypt-Hashes. Jetzt HMAC-SHA-256 mit einem aus dem
  Tresor-Schlüssel abgeleiteten Pepper, ein Nachschlagen; jeder Weg kostet genau eine
  Passwort-Prüfung (`::test_gleiche_arbeit_ob_das_passwort_stimmt`,
  `::test_wiederherstellungscodes_nur_mit_dem_schluessel`).
- **Speicher-DoS (A-M2):** höchstens `server.anmeldungen_gleichzeitig` (2) Passwort-Prüfungen
  zugleich, sonst nach `server.anmeldung_warten_sekunden` 503; `mem_limit` für `app` und
  `lauf` (`tests/test_api_anmeldung.py::test_gleichzeitige_anmeldungen_sind_begrenzt`,
  `tests/test_betrieb_docker.py::test_speichergrenze_fuer_app_und_lauf`).
- **Lauf-Sperre nur im App-Prozess (A-M3):** `betrieb/laufsperre.py` — PostgreSQL
  `pg_try_advisory_lock`, SQLite Dateisperre neben der Datenbank; CLI `bank lauf`,
  `aufgaben lauf` und REST nutzen sie (`tests/test_betrieb_laufsperre.py`, mit echtem
  zweitem Prozess, auch gegen PostgreSQL).
- **Aussperren (A-M4):** Fehlversuche beenden keine Sitzungen mehr, eine Sperre nach
  Fehlversuchen lässt offene Sitzungen weiterlaufen; `benutzer sperren` beendet sie
  (`::test_fehlversuche_anderer_beenden_keine_sitzung`,
  `tests/test_auth_dienst.py::test_gesperrter_benutzer_verliert_sitzung` — korrigiert).
- **Protokoll (A-M5):** absteigend mit `LIMIT` (`tests/test_cli_benutzer.py::test_protokoll_zeigt_die_neuesten_auch_bei_vielen_ereignissen`,
  `tests/test_auth_repo.py::test_ereignisse_die_neuesten`).
- **Verwaltung über Gesellschaften (A-M6 = B-M5):** VERWALTEN in jeder Gesellschaft, in der
  das Zielkonto Rollen hat; Token nur in der eigenen Gesellschaft
  (`tests/test_cli_bindung.py::test_verwalter_von_b_uebernimmt_kein_konto_mit_rollen_in_a`,
  `::test_token_nur_in_der_eigenen_gesellschaft`).
- **Archiv-Abgleich (B-M1), Endungen (B-M2), Systemdatenbank (B-M9), Manifest ↔ Ziel (B-N3),
  Archiv vor dem Festschreiben (A-N5 = B-N1):** `tests/test_betrieb_sicherung.py::test_archiv_fehlt_obwohl_belege_darauf_verweisen`,
  `::test_ungewoehnliche_endung_blockiert_die_sicherung_nicht`, `::test_archiv_endung_wird_beim_ablegen_bereinigt`,
  `::test_sicherung_der_systemdatenbank`, `::test_gesellschaft_im_manifest_muss_zum_ziel_passen`,
  `::test_archiv_wird_vor_dem_festschreiben_an_seinen_platz_gelegt`;
  `tests/test_cli_sicherung.py::test_falscher_archivpfad_bricht_ab`,
  `::test_systemdatenbank_sichern_ohne_gesellschaft`, `::test_wiederherstellen_in_die_falsche_gesellschaft`.
- **Registry (B-M3), Regeln (B-M4), YAML (B-M8):** Trennung nach dem Ersetzen und
  normalisiert, eigene Konfiguration und Regeldatei je Gesellschaft; `classify`, `bank lauf`,
  `opos verbuchen`, `lerne`/`korrigiere --lernen` mit der Regeldatei der Gesellschaft;
  YAML-Fehler als `KonfigurationError`, Befehle ohne Gesellschaft laufen weiter
  (`tests/test_betrieb_gesellschaften.py::test_trennung_nach_ersetzen_und_normalisieren`,
  `::test_yaml_fehler_wird_zum_konfigurationsfehler`,
  `tests/test_cli_gesellschaft.py::test_regeln_je_gesellschaft_auch_in_der_cli`,
  `::test_kaputte_konfiguration_blockiert_befehle_ohne_konfigurationsbedarf_nicht`).
- **Werte in Fehlermeldungen (B-M7 = A-N2), Pfade im Protokoll (A-N1):** `hide_parameters`
  für alle Engines, unbehandelte Ausnahmen protokolliert die App nur mit ihrer Art; das
  Zugriffsprotokoll schreibt die Routenvorlage, unbekannte Pfade als `(unbekannt)`
  (`tests/test_betrieb_protokoll.py::test_datenbankfehler_ohne_werte_im_protokoll`,
  `::test_zugriffsprotokoll_mit_routenvorlage_statt_pfad`).
- **Vier-Augen (B-M10):** `zahlung anlegen` braucht das Recht buchen (mit Einmalcode, der
  Ersteller ist der Benutzer); wer anlegt, gibt nicht frei (`zahlung.ersteller_darf_freigeben`,
  Standard aus) — CLI und Browser (`tests/test_cli_rechte_freigaben.py::test_vier_augen_wer_anlegt_gibt_nicht_frei`,
  `::test_ersteller_darf_freigeben_wenn_bewusst_eingestellt`,
  `tests/test_api_rechte_matrix.py::test_wer_den_lauf_anlegt_gibt_ihn_im_browser_nicht_frei`).
- **Browser-Freigabe an den Inhalt gebunden (B-M11):** die Seite zeigt Empfänger, IBAN,
  Betrag, Verwendungszweck und schickt den Freigabe-Hash mit; weicht er ab, 409
  (`::test_freigabe_gilt_nur_fuer_den_angezeigten_inhalt`).
- **AfA-Freigabe (B-M12):** `anlagen freigeben` an `Recht.BUCHUNG_FREIGEBEN` mit Einmalcode,
  geprüft hat der Benutzer statt `--von`-Freitext
  (`tests/test_cli_rechte_freigaben.py::test_anlagen_freigeben_nur_mit_rolle`).
- **Aufbewahrung der Bücher (A-N4 = B-M6):** je Wirtschaftsjahr ab Schluss des Jahres nach dem
  Wirtschaftsjahresende bzw. des Abschlusses (`tests/test_betrieb_aufbewahrung.py::test_buecher_ab_dem_jahr_der_letzten_eintragung`,
  `::test_buecher_mit_abweichendem_wirtschaftsjahr`; `::test_bericht_zeigt_nur_was_abgelaufen_ist`
  korrigiert — er bestätigte die zu frühe Frist).
- **Akzeptanz 5 mit Daten (B-N2):** `/freigaben` zeigt nach dem Wechsel die Zahlungsläufe von
  B, die Konfiguration wirkt je Gesellschaft im Browser (Vier-Augen nur in B)
  (`tests/test_api_gesellschaften.py::test_akzeptanz_5_wechsel_aendert_alle_ansichten`,
  `::test_eigene_konfiguration_je_gesellschaft`).
- **Sitzungen und zweiter Faktor (A-N6):** ein neuer zweiter Faktor beendet die Sitzungen
  (`tests/test_auth_befunde.py::test_neuer_zweiter_faktor_beendet_die_sitzungen`); dass ältere
  Sicherungen widerrufene Token und verbrauchte Codes zurückbringen und `sicherung
  erstellen` keine Rolle prüft, steht als Grenze unten und in `docs/betrieb.md`.

### Nachprüfung Runde 2 (21.10.2026) — Befunde und Behebung

Beide Nachprüfer bestätigten die Behebung der Befunde oben (Mutationen: jede entfernte
Prüfung lässt ihren Test scheitern), fanden aber zwei neue mittlere Befunde.

- **Dauersperre ohne Rückweg (R2-M1 = NEU-M1):** Die Obergrenze (100) sperrte bis
  `entsperren` — aus dem Netz auslösbar in knapp 5 Stunden, und weil auch die CLI an der
  Sperre scheiterte, half selbst der gesperrte Verwalter mit gültigem Code nicht mehr;
  `streng()` übernahm „strengere“ Sperrwerte aus einer frei wählbaren Datei
  (`fehlversuche_obergrenze: 1` sperrte mit einem falschen Code), `sperre_minuten` war
  unbegrenzt. Jetzt zählen Browser und CLI getrennt, die CLI immer mit den Standardwerten,
  `sperre_minuten` ≤ 1440, und `benutzer entsperren NAME` geht auf der Server-Shell für
  sich selbst mit gültigem zweitem Faktor. Gesperrte Verwalter zählen weiter (keine
  Einrichtungsphase aus dem Netz) (`tests/test_cli_sperre.py`: `::test_netzflut_sperrt_die_server_shell_nicht`,
  `::test_jeder_entsperrt_sich_selbst_mit_dem_zweiten_faktor`,
  `::test_praeparierte_konfiguration_setzt_keine_sperrwerte`,
  `::test_sperre_minuten_hat_eine_obergrenze`, Schutztests
  `::test_selbst_entsperren_aktiviert_kein_gesperrtes_konto`,
  `::test_gesperrter_verwalter_oeffnet_keine_einrichtungsphase`;
  `tests/test_auth_cli.py::test_strenge_einstellungen_ohne_sperrwerte_aus_der_datei` —
  korrigiert, er bestätigte die übernommenen Sperrwerte).
- **Einzelschritte ohne Laufsperre (R2-M2):** `classify`, `opos zuordnen`, `bank
  abgleich`, `bank abrufen` und `kreditkarte abgleich` halten dieselbe Sperre wie `bank
  lauf` (`befehle.laufsperre_oder_ende`) — bevorzugt vor einer Eindeutigkeit je
  `transaktion_id`, weil Storno-Paare später mehrere Buchungen je Umsatz anlegen
  (`tests/test_betrieb_laufsperre.py::test_einzelschritte_der_bankkette_halten_die_laufsperre`,
  `::test_classify_parallel_zu_bank_lauf_kontiert_nicht_doppelt`).
- **Sicherung aus dem falschen Arbeitsverzeichnis (NEU-M2 = R2-N6):** fehlt die
  SQLite-Datei oder hat die Datenbank keine Tabellen von accounti, bricht `erstellen` ab
  und legt nichts an (`tests/test_betrieb_sicherung.py::test_fehlende_oder_fremde_sqlite_datei_wird_nicht_gesichert`,
  `tests/test_cli_sicherung.py::test_sicherung_aus_dem_falschen_arbeitsverzeichnis`).
- **Vier-Augen-Schalter (R2-N4 = N1):** `zahlung.ersteller_darf_freigeben` gilt in der CLI
  nicht mehr (nur strenger), im Browser mit der Konfiguration von `accounti serve`
  (`tests/test_cli_rechte_freigaben.py::test_ersteller_darf_freigeben_gilt_in_der_cli_nicht`
  — korrigiert, `tests/test_api_rechte_matrix.py::test_ersteller_darf_freigeben_im_browser_mit_der_serverkonfiguration`);
  `vier_augen` als Grenze dokumentiert.
- **Wo billig:** `--fremde-gesellschaft` bindet das Ziel neu (R2-N2,
  `tests/test_cli_sicherung.py::test_fremde_gesellschaft_bekommt_den_merker_des_ziels`);
  Warten auf einen Anmeldeplatz im Event-Loop, 503 mit `Retry-After` (R2-N3,
  `tests/test_api_anmeldung.py::test_wartende_anmeldungen_blockieren_keine_arbeitsthreads`);
  Zwischendateien der Sicherung neben dem Ziel (R2-N5,
  `tests/test_betrieb_sicherung.py::test_zwischendateien_liegen_neben_dem_ziel`); wieder
  geöffnetes Geschäftsjahr läuft nicht ab, Stichtag vor 2025 rechnet Belege mit 10 Jahren
  (N2, N3, `tests/test_betrieb_aufbewahrung.py::test_wieder_geoeffnetes_geschaeftsjahr_laeuft_nicht_ab`,
  `::test_vor_dem_beg_iv_gelten_fuer_belege_zehn_jahre`); `zahlung iban-klaeren`,
  `entfernen`, `sperre` (Recht buchen) und `stornieren` (Zahlungsfreigabe) mit Einmalcode und
  Benutzer im Protokoll (Rest B-M12, `tests/test_cli_rechte_freigaben.py::test_weitere_zahlungsbefehle_mit_rolle_und_angemeldetem_benutzer`).
- **Doku (R2-N1, N4):** Grenzen des Merkers (Trust on first use, Kopie der
  Systemdatenbank, Browser prüft ihn nicht), Rückweg nach einer Sperre und ältere
  Sicherungen (auch gesperrte Benutzer und entzogene Rollen kommen zurück) stehen in
  `docs/betrieb.md`.
- Nicht behoben: kosmetischer Rest von A-N1 (unter `/statisch/…` steht der maskierte Pfad
  im Protokoll), `localhost` ↔ `127.0.0.1` und `file:`-URIs im Registry-Abgleich, leere
  SQLite-Dateien aus Tippfehlern bei anderen Befehlen als `sicherung` (A-N3-Nebenwirkung).

### Nachprüfung Runde 3 (21.10.2026) — mergefähig, Niedrig-Befunde nachgezogen

- Selbst-Entsperren eines mit `benutzer sperren` stillgelegten Kontos meldete „entsperrt“
  (Exit 0) und ließ es stillgelegt — jetzt ehrliche Meldung, Exit 1, nichts geändert
  (N-R3-1, `tests/test_cli_sperre.py::test_selbst_entsperren_eines_stillgelegten_kontos_meldet_das_ehrlich`).
- `fints freigeben` hält die Laufsperre (N-R3-2, `tests/test_cli_fints.py::test_freigeben_haelt_die_laufsperre`).
- Nicht erreichbare Datenbank bei `sicherung erstellen|wiederherstellen`: Meldung ohne
  Passwort, Exit 1 (N-R3-3, `tests/test_cli_sicherung.py::test_datenbank_nicht_erreichbar`).
- Die Zwischenkopie der SQLite-Datei liegt neben der Datenbank, nicht im Sicherungsordner
  (N-R3-4, `tests/test_betrieb_sicherung.py::test_zwischenkopie_liegt_neben_der_datenbank`).
- Die Meldung „wer anlegt, gibt nicht frei“ nennt CLI und Browser (N-R3-5, Meldungstext in
  `tests/test_cli_rechte_freigaben.py::test_ersteller_darf_freigeben_gilt_in_der_cli_nicht`).
- Testlücken, die Mutationen überleben ließen (N-R3-6):
  `tests/test_cli_sperre.py::test_verwalter_hebt_auch_die_cli_sperre_auf`,
  `tests/test_api_anmeldung.py::test_anmeldeplatz_wartet_selbst_nie`; die Zeitmessung in
  `::test_wartende_anmeldungen_blockieren_keine_arbeitsthreads` beginnt vor der Pause.
- `pruefe_zweiten_faktor(…, quelle=…)` ist Pflicht (Kanal der Zählung), `*.lauf-*.sperre`
  in `.gitignore`.

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
  (Schalter `auth.einmalcode_bestaetigung`) — wie bei Zahlungslauf und USt-VA. Jedes
  Freigabe-Formular trägt den Hash des angezeigten Inhalts (verstecktes Feld, z. B.
  `freigabe_hash` mit `zahlung.freigabe.freigabe_hash`); weicht der Inhalt beim Absenden
  ab, 409 (`freigabe.freigeben(…, gesehen=…)`). Wer eine Buchung bzw. einen Lauf anlegt,
  gibt sie nicht frei (`ersteller_ausgeschlossen`).
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

| Nr. | Kriterium | Test |
|-----|-----------|------|
| Spec 3 | Ein `betrachter` kann nichts freigeben; ein `buchhalter` kann keinen Zahlungslauf freigeben | Browser: `tests/test_api_rechte_matrix.py::test_akzeptanz_3_betrachter_nichts_buchhalter_kein_zahlungslauf` (jede Freigabe-Route, Lauf bleibt `entwurf`, Freigeber ohne Code scheitert, mit Code `freigegeben`), `::test_jede_rolle_gegen_jeden_endpunkt` (Matrix), `::test_jeder_endpunkt_steht_in_der_matrix`, `::test_vier_augen_im_browser`, `::test_ustva_freigabe_im_browser`; CLI: `tests/test_cli_rechte_freigaben.py::test_akzeptanz_3_zahlungslauf_nur_durch_freigeber`, `::test_akzeptanz_3_ustva_nur_durch_freigeber`, `::test_dauerfrist_freigabe_nur_durch_freigeber`, `::test_ohne_benutzer_wie_bisher`, `::test_anlagen_freigeben_nur_mit_rolle`; `tests/test_auth_cli.py::test_akzeptanz_3_rollen_in_der_cli`; nicht über eine andere Gesellschaft, Konfiguration oder Systemdatenbank: `tests/test_cli_bindung.py` |
| Spec 4 | Anmeldung ohne zweiten Faktor schlägt fehl | `tests/test_api_anmeldung.py::test_akzeptanz_4_anmeldung_ohne_zweiten_faktor_scheitert` (ohne Code, falscher Code, Benutzer ohne eingerichteten Faktor → 401 ohne Sitzung), `tests/test_auth_dienst.py::test_akzeptanz_4_anmeldung_ohne_zweiten_faktor_scheitert`; dazu `::test_totp_code_nur_einmal`, `::test_wiederherstellungscode_genau_einmal` (Teststrategie: „funktioniert genau einmal“), `::test_sperre_nach_fehlversuchen`; Docker-Probe (401 ohne Code im Container) |
| Spec 5 | Der Wechsel der Gesellschaft ändert alle Ansichten konsistent | Browser: `tests/test_api_gesellschaften.py::test_akzeptanz_5_wechsel_aendert_alle_ansichten` (jede Seite der Registry zeigt danach Gesellschaft B), `::test_benutzer_von_a_sieht_b_nicht` (negativ, Teststrategie), `::test_rolle_entzogen_wirkt_sofort`, `::test_token_sieht_nur_seine_gesellschaft`, `::test_eigene_konfiguration_je_gesellschaft`; CLI: `tests/test_cli_gesellschaft.py::test_akzeptanz_5_wechsel_aendert_die_ansichten` (Kontakte, OPOS-Liste, Staffel, Zahlungsvorschlag, Belege), `::test_jeder_befehl_bekommt_datenbank_archiv_und_konfiguration` (alle Befehle mit `--db`/`--archiv`/`--config`), `::test_hilfe_zeigt_die_datenbank_der_gesellschaft`, `::test_gesellschaft_liste_und_zeigen_ohne_passwort` (eigener Kontenrahmen, eigenes Wirtschaftsjahr) |
| Spec 6 | `docker compose up` startet Anwendung, Datenbank und geplanten Lauf | Probe oben (ausgeführt, Projekt `accounti-test-b10a`); statisch `tests/test_betrieb_docker.py::test_compose_mit_anwendung_datenbank_und_lauf`, `::test_geheimnisse_nur_aus_der_umgebung`, `::test_abbild_ohne_geheimnisse_und_nicht_als_root`, `::test_alembic_liest_accounti_db`; Lauf `tests/test_betrieb_planer.py` |
| Spec 7 | Eine Sicherung lässt sich in eine leere Umgebung zurückspielen — Buchungen und Belege vollständig | `tests/test_betrieb_sicherung.py::test_akzeptanz_7_wiederherstellung_in_leere_umgebung` (jede Tabelle Zeile für Zeile, jede Archivdatei bytegleich, Hash-Kette gültig), `::test_sicherung_ist_ein_schnappschuss_ueber_alle_tabellen` und `::test_sicherung_ist_ein_schnappschuss_postgresql` (auch während geschrieben wird), `::test_archiv_fehlt_obwohl_belege_darauf_verweisen`, `::test_falscher_schluessel_laesst_alles_leer`, `::test_veraenderte_sicherung_wird_zurueckgerollt`, `::test_nur_in_leere_umgebung`; `tests/test_cli_sicherung.py::test_sichern_pruefen_wiederherstellen` (Ansichten gleich); Docker-Probe (PostgreSQL, SQLite ↔ PostgreSQL) |
| Integr. 7 | REST-API liefert offene Posten und nimmt Belege entgegen; ein Token ohne passende Berechtigung wird abgewiesen | `tests/test_api_rest.py::test_akzeptanz_7_offene_posten_lesen`, `::test_akzeptanz_7_belege_einliefern` (Archiv und Datenbank der Gesellschaft des Tokens, Dublette), `::test_akzeptanz_7_token_ohne_recht_wird_abgewiesen` (403 `insufficient_scope`, nichts gespeichert); `tests/test_api_rechte_matrix.py::test_jedes_token_recht_gegen_jeden_rest_endpunkt` |
| Teststrategie | Kein personenbezogener Inhalt im Log | `tests/test_betrieb_protokoll.py::test_durchlauf_ohne_personenbezogene_inhalte_im_protokoll` (Anmeldung, Seiten, API mit Namen, IBAN, Token, Passwort), `::test_schwaerzung`, `::test_filter_gilt_fuer_alle_logger_und_ausnahmen` |

## Grenzen

**Nicht in diesem Auftrag**
- Spec 4.2, 4.3, 4.5 (Supervisions-Queue, Auswertungen, Zweisprachigkeit) und damit Akzeptanz 1
  und 2 baut der nächste Auftrag auf der Schnittstelle oben. Das Grundlayout hat keinen
  Übersetzungsmechanismus.
- Keine Alembic-Migration für die sieben neuen Tabellen (`auth_benutzer` — mit
  `cli_fehlversuche`/`cli_gesperrt_bis` —, `auth_rollen`,
  `auth_wiederherstellungscodes`, `auth_sitzungen`, `api_tokens`, `auth_ereignisse`,
  `auth_merker`) — entsteht beim Zusammenführen und muss unter SQLite die Trigger
  `auth_ereignisse_kein_update/_delete` anlegen (wie `c7e19f7158a3` für `ustid_pruefungen`);
  der Index `uq_api_token_aktiv` ist ein Teilindex (`sqlite_where`/`postgresql_where`).
- Der Browser zeigt vor der Freigabe der USt-VA keine Kennziffern — die Freigabe hängt am
  Hash der Werte zum Zeitpunkt der Freigabe, aber wer im Browser freigibt, sieht sie nicht.
  Eine Vorschau (Kennziffern, Befunde) gehört vor das Formular; das ist Arbeit der
  Web-Oberfläche. (Zahlungsläufe zeigt die Seite jetzt Zahlung für Zahlung und bindet die
  Freigabe an den angezeigten Inhalt.)

**Anmeldung und Rechte**
- In der CLI sind Freigaben (`zahlung freigeben`, `ustva freigeben`, `ustva dauerfrist
  --freigeben`, `anlagen freigeben`), `zahlung anlegen` und die Verwaltung (`benutzer …`,
  `token …`) an Rollen gebunden. `bestaetige`, `korrigiere`, `storniere`, `periode
  schliessen`, `review`, `lerne` (Buchungen prüfen/freigeben, Journal, Periodenabschluss)
  liegen in `cli.py`, das der parallele Branch `feat/belegvollstaendigkeit-gobd` umbaut —
  beim Zusammenführen dort `befehlsrecht_oder_ende(db, config, Recht.BUCHUNG_FREIGEBEN,
  person)` bzw. `Recht.BUCHEN` aufrufen und den zurückgegebenen Benutzer (`b.name`) statt
  `--von` als Person ins Journal schreiben (Spec 4.1: „jede Aktion trägt einen echten
  Benutzer“). Alle anderen schreibenden CLI-Befehle prüfen keine Rolle: die CLI ist das
  Werkzeug des Betreibers auf dem Server.
- Die CLI-Identität ist `--von`/`ACCOUNTI_BENUTZER` (mit `zahlung.vier_augen` der Anmeldename);
  belastbar wird sie erst durch den Einmalcode (in der CLI immer verlangt, sobald Benutzer
  eingerichtet sind).
  Im Container ist der Anmeldename immer `accounti` — Vier-Augen-Freigaben in Docker also im
  Browser.
- Sind alle Verwalter stillgelegt (`benutzer sperren`) oder ohne zweiten Faktor, gilt wieder
  die Einrichtungsphase (Notzugang über die Server-Shell) — gewollt, aber zu wissen. Eine
  Sperre nach Fehlversuchen zählt dafür nicht (sonst öffnete eine Flut aus dem Netz die
  Einrichtungsphase); dagegen hilft `benutzer entsperren NAME` mit eigenem Einmalcode. Freigaben öffnet sie nicht:
  eine leere oder fremde Systemdatenbank scheitert am Merker der Gesellschaft.
- Merker `auth_merker`: wer die CLI mit einer fremden Registry aufruft, **bevor** eine
  Gesellschaft je gebunden wurde (kein `benutzer anlegen`, keine Prüfung), bindet sie an
  diese (Trust on first use) — danach ist der Fehler sichtbar, weil die echte Prüfung
  abbricht. Bewusst neu binden (Systemdatenbank verloren) geht über die Datenbank
  (`DELETE FROM auth_merker WHERE schluessel = 'benutzerverwaltung'`) oder beim
  Zurückspielen mit `--fremde-gesellschaft`. Der Merker vergleicht die Kennung, nicht den
  Ort: eine **Kopie** der Systemdatenbank besteht ihn (wer sie lesen kann, kann darin
  Rollen ändern und mit eigenem zweitem Faktor freigeben; der Code wird nur in der Kopie
  verbraucht). Der Browser (`accounti serve`) prüft den Merker nicht; seine
  Systemdatenbank legt der Betreiber beim Start fest. Alles auch in `docs/betrieb.md`.
- Kontosperre: wer einen Benutzernamen kennt, blockiert dessen **neue** Anmeldungen im
  Browser je 15 Minuten und nach 100 Fehlversuchen bis zum Entsperren (offene Sitzungen
  laufen weiter, die CLI zählt getrennt; Rückweg: `benutzer entsperren NAME` auf der
  Server-Shell mit eigenem Einmalcode). Eine Bremsung je IP gehört in den Proxy
  (`limit_req`-Beispiel in `docs/betrieb.md`); eine schrittweise verlängerte Sperre ist
  nicht umgesetzt. 100 falsche Codes **auf der Shell** sperren auch die CLI bis zum
  Entsperren — dann ein anderer Verwalter oder SQL (Shell-Zugang ist Betreiberebene).
- `zahlung.ersteller_darf_freigeben` gilt nur im Browser (Konfiguration von `accounti
  serve`); in der CLI gilt mit Benutzern immer „wer anlegt, gibt nicht frei“.
  `zahlung.vier_augen` steht in der Konfiguration der Gesellschaft — die wählt in der CLI
  der Aufrufer (`--config` ohne Registry, eine eigene `ACCOUNTI_KONFIG`/Registry mit
  Registry; der Abgleich `--config` ↔ Registry prüft nur gegen die Registry des
  Aufrufers). Vier-Augen lässt sich in der CLI so abschalten; den eigenen zweiten Faktor
  nicht, und das Protokoll zeigt, wer allein freigab.
- Den zweiten Faktor richtet nur die CLI ein (`benutzer 2fa`, auf dem Server); es gibt keine
  Selbstregistrierung im Browser, kein Zurücksetzen per E-Mail, keine Passkeys/WebAuthn.
- TOTP nur SHA-1, 6 Stellen, 30 s (was Apps können); Toleranz ±1 Schritt — RFC 6238
  empfiehlt höchstens einen Schritt für die Netzverzögerung, der Schritt nach vorn deckt
  Uhrenabweichung (Wiederverwendung ist trotzdem ausgeschlossen).
- Die Sperrliste der Passwörter ist klein; kein Abgleich mit Listen kompromittierter Passwörter
  (bräuchte einen externen Dienst). Keine Begrenzung je IP — das gehört in den Proxy.
- `ACCOUNTI_SCHLUESSEL` verschlüsselt auch die TOTP-Geheimnisse: wer ihn wechselt, muss den
  zweiten Faktor aller Benutzer neu einrichten (wie die Bankzugänge); ein Befehl zum Umschlüsseln
  fehlt.
- Abgelaufene Sitzungen bleiben als Zeilen stehen (kein Aufräumen), `auth_ereignisse` wächst
  ohne Löschung (Benutzernamen sind personenbezogen; eine Frist für das Anmeldeprotokoll ist
  nicht umgesetzt). Keine Übersicht „meine Sitzungen“.

**REST-API**
- Keine Seitenaufteilung bei offenen Posten und Buchungen, keine OpenAPI-Seite, keine
  Begrenzung der Aufrufe; Läufe laufen synchron (ein langer `bank lauf` kann in die
  Zeitgrenze des Proxys laufen), die Belegerkennung (OCR) ebenfalls im Aufruf.

**Mehrere Gesellschaften**
- `import banken` liest `config/banken.yaml` fest relativ zum Arbeitsverzeichnis (die
  Regeln je Gesellschaft gelten jetzt auch in `classify`, `bank lauf`, `opos verbuchen`,
  `lerne` und `korrigiere --lernen`). Der Abschnitt `bank` wird in `bank/lauf.py`,
  `bank/kreditkarte.py` und `bank/fints.py` teils ohne Pfad geladen — er gilt deshalb für
  die ganze Installation (FinTS-Produkt-ID ist ohnehin je Installation).
- Rollen und Token verweisen auf das Kürzel; wer eine Gesellschaft in der Registry umbenennt,
  verwaist sie.
- Die Systemdatenbank wird bei mehreren Gesellschaften getrennt gesichert
  (`sicherung erstellen --system`). Eine ältere Sicherung bringt widerrufene Token,
  verbrauchte Wiederherstellungscodes und alte Passwörter zurück (Hinweis in
  `docs/betrieb.md`); `sicherung erstellen` prüft keine Rolle (läuft per Cron ohne
  Einmalcode).

**Betrieb**
- Sicherung: Tabellen über 16 MB werden beim Schreiben unverschlüsselt in eine Temporärdatei
  (0600) ausgelagert und gleich wieder gelöscht (in Docker liegt `/tmp` im Speicher); eine
  SQLite-Datenbank wird vorher ganz in den Temporärordner kopiert (Backup-API, 0600).
  Abgeglichen werden nur `belege.datei_hash` mit dem Archiv (andere Dateiverweise, z. B.
  ELSTER-Protokolle, nicht).
  Wiederhergestellt wird in einer Transaktion (große Bestände → lange Transaktion); das Archiv
  wird nach dem Festschreiben an seinen Platz umbenannt. Keine inkrementellen Sicherungen,
  kein eingebauter Zeitplan (Cron/`docker compose run`). Das Ziel-Schema kommt aus den
  aktuellen Modellen — eine ältere Sicherung in eine neuere Version mit neuen Pflichtspalten
  ließe sich nicht zurückspielen.
- Aufbewahrung: nur Bericht, kein protokolliertes Aussondern. Wann eine Buchung eingetragen
  wurde, speichert accounti nicht — die Frist der Bücher beginnt deshalb konservativ mit dem
  Jahr nach dem Wirtschaftsjahresende bzw. dem Abschluss; wer ein Jahr länger nachbucht,
  ohne abzuschließen, prüft von Hand. `belege.aufbewahren_bis` setzt
  `belege/archiv.py` (Baustein 2) noch auf 10 Jahre; rechtlich genügen seit dem BEG IV 8 Jahre
  für Buchungsbelege — beim Zusammenführen entscheiden, ob das Feld umgestellt wird (länger
  aufbewahren ist zulässig).
- Protokollierung: Namen und Belegtexte erkennt kein Muster; geschützt ist nur, was der Code
  nicht schreibt. Ausgaben der CLI (Tabellen mit Namen) gehen ins Terminal, nicht ins Protokoll;
  der geplante Lauf gibt sie nur geschwärzt auf Stufe DEBUG weiter.
- Docker: kein Java (KoSIT, Mustang), kein ERiC, kein python-fints im Abbild; `config/` ist
  schreibgeschützt eingehängt (`korrigiere --lernen` kann dort nicht schreiben); das Abbild baut
  mit den neuesten Versionen innerhalb der Grenzen aus `pyproject.toml` (keine Sperrdatei);
  `aufgaben lauf` endet ohne Abschnitt `versand` mit 1, der Lauf meldet dann jede Runde eine
  Warnung. Ohne TLS ist keine Anmeldung möglich, außer mit `server.cookie_sicher: false`.
- `accounti serve` startet einen Uvicorn-Prozess ohne Worker-Option.

## Doku-Bausteine

Fertige Texte zum Einarbeiten beim Zusammenführen (diese Dateien wurden hier nicht geändert).

### README.md

**Ersetzt die drei Zeilen** `| 🔲 | **REST-API** | …`, `| 🔲 | **Mehrere Gesellschaften** | …`
und `| 🔲 | **Benutzer & Rollen** | …` in der Feature-Tabelle durch:

```markdown
| ✅ | **REST-API** | `/api/v1` mit API-Token und Rechten (`opos:lesen`, `buchungen:lesen`, `belege:schreiben`, `laeufe:starten`): offene Posten und Buchungen abfragen, Belege einliefern (Pipeline wie der Webhook), `bank lauf` und `aufgaben lauf` anstoßen; Token nur als Hash gespeichert, ohne Recht 403 |
| ✅ | **Mehrere Gesellschaften** | Je eigene Gesellschaft eine Datenbank, ein Belegarchiv und eine Konfiguration (Kontenrahmen, Wirtschaftsjahr, Nummernkreise, Bankkonten); `accounti --gesellschaft K …` für alle Befehle, Wechsel im Browser |
| 🟨 | **Benutzer & Rollen** | Anmeldung mit Passwort (scrypt) und zweitem Faktor (TOTP, Wiederherstellungscodes), Sperre nach Fehlversuchen, Rollen betrachter/buchhalter/freigeber/verwalter je Gesellschaft, Freigaben nur mit Rolle und Einmalcode (Browser und CLI), Vier-Augen-Freigabe; DE/EN folgt |
| ✅ | **Betrieb** | `docker compose up` mit PostgreSQL und geplantem Lauf, Geheimnisse nur aus der Umgebung, verschlüsselte Sicherung von Datenbank und Belegarchiv mit Wiederherstellung, Aufbewahrungsfristen nach § 147 AO, Protokoll ohne Personenbezug — [Betrieb](docs/betrieb.md) |
```

**Ersetzt im Abschnitt „Installation“** die letzten Zeilen ab `# Starten` (bis zum Ende des
Codeblocks) durch:

```bash
# Ersten Benutzer (Verwalter) anlegen und zweiten Faktor einrichten
accounti bank schluessel            # die ausgegebene Zeile „export ACCOUNTI_SCHLUESSEL=…“ ausführen
accounti benutzer anlegen chef --rolle verwalter --rolle freigeber
accounti benutzer 2fa chef

# Web-Oberfläche und REST-API (TLS über einen Reverse-Proxy, siehe docs/betrieb.md)
accounti serve
```

**Neuer Abschnitt** nach „### Aufgaben und Rückfragen“ (vor „## Architektur“):

````markdown
### Betrieb, Benutzer und mehrere Gesellschaften

```bash
docker compose up -d --build                       # App, PostgreSQL, geplanter Lauf (docs/betrieb.md)
accounti benutzer anlegen eva --rolle buchhalter   # Rollen: betrachter, buchhalter, freigeber, verwalter
accounti benutzer 2fa eva                          # TOTP-App + zehn Wiederherstellungscodes
accounti benutzer liste | rolle | passwort | sperren | entsperren | protokoll
accounti token anlegen erp --recht opos:lesen --recht belege:schreiben
accounti gesellschaft liste                        # Registry `gesellschaften`
accounti --gesellschaft tochter opos liste         # setzt --db/--archiv/--config aller Befehle
accounti sicherung erstellen --ziel /sicherungen/  # Datenbank + Belegarchiv, verschlüsselt
accounti sicherung wiederherstellen DATEI --db sqlite:////tmp/probe/x.db --archiv /tmp/probe/belege
accounti betrieb aufbewahrung                      # was frühestens ausgesondert werden dürfte
accounti betrieb lauf --intervall-minuten 60       # bank lauf + aufgaben lauf je Gesellschaft
```

Mit eingerichteten Benutzern verlangen `zahlung freigeben` und `ustva freigeben` die Rolle
`freigeber` und den Einmalcode der handelnden Person; ohne Benutzer bleibt alles wie bisher.
````

**Ersetzt in „### v0.5 — Oberfläche & Betrieb“** die Zeilen
`- [ ] Benutzer, Rollen, 2FA, Vier-Augen-Freigabe, DE/EN` und
`- [ ] Docker-Setup, verschlüsselte Sicherungen, Löschkonzept` durch:

```markdown
- [x] Benutzer, Rollen, 2FA, Vier-Augen-Freigabe, mehrere Gesellschaften, REST-API
- [x] Docker-Setup, verschlüsselte Sicherungen, Löschkonzept
- [ ] DE/EN in der Oberfläche
```

### CHANGELOG.md

**Unter `## [Unreleased]` → `### Hinzugefügt`** oben einfügen:

```markdown
- **Anmeldung, Rollen, mehrere Gesellschaften, Betrieb und REST-API** (Baustein 10a):
  Benutzer mit scrypt-Passwort (OWASP: N = 2^17, r = 8, p = 1) und zweitem Faktor nach RFC 6238
  (TOTP, jeder Code einmal; zehn Wiederherstellungscodes, je einer einmal), Sperre nach
  Fehlversuchen, Sitzungen mit `__Host-`-Cookie, Leerlauf und Höchstdauer, nur anfügbares
  Anmeldeprotokoll (`accounti benutzer anlegen|2fa|codes|liste|rolle|passwort|sperren|entsperren|protokoll`).
  Rollen `betrachter`, `buchhalter`, `freigeber`, `verwalter` je Gesellschaft. Web-Gerüst mit
  FastAPI und Jinja2 (`accounti serve`): Anmeldung nur mit zweitem Faktor, CSRF-Schutz,
  Rollenprüfung als Dependency, Router-Registry, Grundlayout mit Gesellschaftswechsel,
  Freigabe von Zahlungslauf und USt-VA mit frischem Einmalcode, strenge CSP. REST-API
  `/api/v1` mit API-Token und Rechten (`accounti token anlegen|liste|widerrufen`): offene
  Posten, Buchungen, Belege einliefern, `bank lauf`/`aufgaben lauf` anstoßen. Mehrere eigene
  Gesellschaften über die Registry `gesellschaften` (je Datenbank, Archiv, Konfiguration) und
  die globale Option `--gesellschaft`; `ACCOUNTI_DB`, `ACCOUNTI_ARCHIV`, `ACCOUNTI_KONFIG`
  setzen die Standards aller Befehle (`accounti gesellschaft liste|zeigen`). Betrieb:
  `Dockerfile` und `docker-compose.yml` (App, PostgreSQL 16, geplanter Lauf
  `accounti betrieb lauf`), verschlüsselte Sicherung von Datenbank und Belegarchiv mit
  Wiederherstellung in eine leere Umgebung (`accounti sicherung schluessel|erstellen|pruefen|wiederherstellen`),
  Aufbewahrungsbericht nach § 147 AO/§ 14b UStG (`accounti betrieb aufbewahrung`),
  Protokollierung ohne personenbezogene Inhalte, `docs/betrieb.md` mit Reverse-Proxy und TLS.
  Neue Abschnitte `auth`, `gesellschaften` (optional); `server` wird jetzt gelesen.
```

**Unter `### Geändert`** oben einfügen:

```markdown
- `accounti zahlung freigeben`, `accounti ustva freigeben` und `accounti ustva dauerfrist
  --freigeben` verlangen, sobald Benutzer eingerichtet sind, die Rolle `freigeber` und den
  Einmalcode der handelnden Person; ohne Benutzer unverändert.
- `accounti serve` startet die Web-Oberfläche und REST-API (bisher ein Platzhalter) und liest
  `--db`, `--archiv`, `--config` sowie den Abschnitt `server`.
- `alembic/env.py` nimmt die Datenbank aus `ACCOUNTI_DB`, wenn gesetzt.
```

**Unter `### Behoben`**: nichts.

### docs/bauplan.md

**Ersetzt in der Bausteinkarte** die Zeile `| 10 | Supervision-Web-UI, Auth & Betrieb | … | 🔲 geplant | … |` durch:

```markdown
| 10 | Supervision-Web-UI, Auth & Betrieb | `api/` `auth/` `betrieb/` | 🟨 teilweise | [Spec](specs/2026-08-10-web-ui-auth-betrieb.md) |
```

**Ersetzt im Absatz „Baustein 11 ist teilweise fertig“** den Satz `Was fehlt, sind die REST-API
(mit Baustein 10), JTL-Wawi, …` durch `Die REST-API kam mit Baustein 10a; was fehlt, sind
JTL-Wawi, die Prüfungsdatenüberlassung und die Beleg-Connectoren.`

**Neuer Absatz** nach dem Absatz zu Baustein 8:

```markdown
**Baustein 10 ist teilweise fertig** ([Plan](plans/2026-10-26-auth-gesellschaften-betrieb-api.md)):
Benutzer mit Passwort und zweitem Faktor (TOTP nach RFC 6238, Wiederherstellungscodes), Sperre,
Sitzungen, Rollen `betrachter`/`buchhalter`/`freigeber`/`verwalter` je Gesellschaft — Freigaben
von Zahlungsläufen und Steuermeldungen nur mit Rolle und Einmalcode, im Browser wie in der CLI;
mehrere eigene Gesellschaften mit eigener Datenbank, eigenem Archiv und eigener Konfiguration
(`--gesellschaft`); das FastAPI-Gerüst mit Anmeldung, CSRF, Rollen-Dependency, Router-Registry
und Grundlayout; die REST-API (Akzeptanz 7 aus Baustein 11); Docker Compose mit PostgreSQL und
geplantem Lauf, verschlüsselte Sicherung mit Wiederherstellung, Aufbewahrungsbericht und
Protokoll ohne Personenbezug ([Betrieb](betrieb.md)). Was fehlt, ist die Oberfläche selbst:
Supervisions-Queue mit Belegansicht, Korrektur → Regel, Auswertungen und Zweisprachigkeit
(Akzeptanz 1 und 2).
```

### docs/architektur.md

**Ersetzt** den Abschnitt `### auth/ *(geplant — …)*` (ein Absatz) durch:

```markdown
### `auth/` *(vorhanden — [Baustein 10](specs/2026-08-10-web-ui-auth-betrieb.md))*

Benutzer, Rollen, Sitzungen, zweiter Faktor, API-Token — alles in der **Systemdatenbank**
(ohne Registry: die Datenbank der Gesellschaft). Modelle `models/auth.py`, Tabellen
`db/tabellen_auth.py` (`auth_benutzer`, `auth_rollen`, `auth_wiederherstellungscodes`,
`auth_sitzungen`, `api_tokens`, `auth_ereignisse` — nur anfügen, SQLite-Trigger —,
`auth_merker`), Repository `db/repo_auth.py`.

- `passwort.py` — `hashlib.scrypt` (N = 2^17, r = 8, p = 1), Parameter im Hash, Neuberechnung
  bei der Anmeldung; Regeln nach NIST 800-63B-4 (Länge, Sperrliste, keine Zusammensetzung).
- `totp.py` — RFC 6238 mit `hmac` (Prüfwerte aus Anhang B), Toleranz ±1 Schritt, otpauth-URI;
  jeder Schritt wird nur einmal angenommen (`UPDATE … WHERE letzter < schritt`).
- `wiederherstellung.py` — zehn Codes je Benutzer, als HMAC mit einem Pepper aus dem Tresor
  gespeichert (ein Nachschlagen, gleiche Arbeit je Versuch), je einer genau einmal.
- `dienst.py` — anlegen, 2FA bestätigen (Geheimnis im Tresor, an den Benutzer gebunden),
  `pruefe_anmeldung` (Passwort **und** zweiter Faktor, sonst `AnmeldungError` ohne Grund;
  jeder Weg kostet eine Passwort-Prüfung), Sperre (jeder Versuch vor der Prüfung atomar
  gezählt, Obergrenze in Folge), Sitzungen (256-Bit-Token, nur SHA-256 gespeichert,
  Leerlauf, Höchstdauer; Passwortwechsel, `benutzer sperren`, Rollenänderung und neuer
  zweiter Faktor beenden sie — Fehlversuche anderer nicht), Rollen je Gesellschaft.
- `token.py` — API-Token `accounti_api_…` mit Gesellschaft, Rechten (`TokenRecht`), Ablauf;
  nur SHA-256. Kein Token kann freigeben.
- `cli.py` — Rechte in der CLI: ohne Benutzer keine Prüfung; sonst Person mit Recht in der
  Gesellschaft der benutzten Datenbank und Einmalcode (in der CLI immer). Bindung jeder
  Gesellschafts-Datenbank an ihre Systemdatenbank (Merker `auth_merker`, fail-closed).
  Verwaltung mit Einrichtungsphase, fremde Konten nur durch Verwalter aller ihrer
  Gesellschaften. Eingebunden in `zahlung anlegen|freigeben`, `ustva freigeben`,
  `ustva dauerfrist`, `anlagen freigeben`.
- `einstellungen.py` — Abschnitt `auth`.

Rollen → Rechte (`ROLLEN_RECHTE`): `betrachter` lesen · `buchhalter` lesen, buchen, Belege
einliefern, Läufe starten, Buchungen freigeben · `freigeber` lesen, Buchungen, Zahlungsläufe,
Steuermeldungen freigeben · `verwalter` lesen, verwalten. Additiv, nicht hierarchisch.
```

**Ersetzt** den Abschnitt `### api/` (REST-API-Liste, Web-UI, Kernansicht) durch:

```markdown
### `api/` *(Gerüst und REST-API vorhanden — [Baustein 10](specs/2026-08-10-web-ui-auth-betrieb.md))*

FastAPI-Anwendung aus `app.erstelle_app(Dienste)`: Systemdatenbank, Gesellschaften und ihre
Datenbanken (`dienste.py`), Sicherheitskopfzeilen und Zugriffsprotokoll ohne Personenbezug
(`sicherheit.py`), `/gesund`, `/statisch`. Gestartet mit `accounti serve` (`server.py`).

- `sitzung.py` — Dependencies `angemeldet`, `erfordert(Recht.X)`, `gesellschaft_db`; CSRF-Token
  aus dem Sitzungstoken, Pflicht bei jeder nicht lesenden Anfrage (Feld `csrf` oder Kopf
  `X-CSRF-Token`). Die aktive Gesellschaft steht in der Sitzung; Mitgliedschaft und Rechte
  werden je Anfrage neu gelesen.
- `seiten/` — HTML-Router-Registry (jedes Modul mit `router`, optional `NAVIGATION`):
  `anmeldung.py` (Passwort + Einmalcode, Double-Submit gegen Login-CSRF), `start.py`,
  `gesellschaft.py` (Wechsel), `freigaben.py` (Zahlungslauf, USt-VA mit frischem Einmalcode).
- `rest/` — REST-Registry unter `/api/v1`, nur mit API-Token (`erfordert_recht`, `TokenDb`):
  `ich`, `offene-posten`, `buchungen`, `belege` (über `belege.pipeline`, Kanal `api`),
  `laeufe/bank`, `laeufe/aufgaben`.
- `vorlagen/` + `vorlagen.py` (Jinja2, Autoescape, `basis.html`), `statisch/` (CSS), `formular.py`
  (urlencoded ohne `python-multipart`), `registry.py`, `einstellungen.py` (Abschnitt `server`).

Die Oberfläche ruft dieselben Funktionen wie die CLI. Geplant auf diesem Gerüst: die
Supervisions-Queue (links Beleg, rechts Vorschlag mit Confidence und Begründung, Korrektur in
einem Schritt, Angebot einer Regel), Auswertungen, DE/EN.
```

**Neuer Abschnitt** nach `### api/`:

```markdown
### `betrieb/` *(vorhanden — [Baustein 10](specs/2026-08-10-web-ui-auth-betrieb.md), [Betrieb](betrieb.md))*

- `gesellschaften.py` — Registry `gesellschaften`: je Kürzel Name, Datenbank, Archiv,
  Konfiguration, Regeln; Systemdatenbank; `${VAR}` erst bei Bedarf ersetzt.
- `kontext.py`, `cli.py` — Kontext je CLI-Aufruf: `--gesellschaft`/`ACCOUNTI_GESELLSCHAFT` bzw.
  `ACCOUNTI_DB`/`ARCHIV`/`KONFIG` setzen über `Context.default_map` die Standards von `--db`,
  `--archiv`, `--config` **aller** Befehle (Callback in `cli.py`).
- `verschluesselung.py`, `sicherung.py` — Sicherung als Tar-Strom (Tabellen als JSON-Zeilen,
  typgetreu; Archivdateien; Manifest mit SHA-256), AES-256-GCM in Stücken (STREAM, HKDF je
  Sicherung); Wiederherstellung nur in eine leere Umgebung, alles oder nichts.
- `aufbewahrung.py` — Fristen nach § 147 AO (BEG IV) und § 14b UStG, Bericht ohne Löschen.
- `planer.py` — geplanter Lauf (`bank lauf`, `aufgaben lauf` je Gesellschaft als Prozesse).
- `laufsperre.py` — je Gesellschaft und Art höchstens ein Lauf, über Prozesse hinweg
  (PostgreSQL-Advisory-Lock, SQLite-Dateisperre).
- `protokoll.py` — Schwärzung (IBAN, E-Mail, Token, Passwörter in URLs) an jedem Handler.
```

**Ergänzt im Abschnitt „## Sicherheit“** am Ende:

```markdown
- Anmeldung nur mit zweitem Faktor; Passwörter mit scrypt, Sitzungs- und API-Token nur als
  SHA-256, TOTP-Geheimnisse im Tresor; Freigaben mit Rolle und frischem Einmalcode
- Protokolle ohne IP-Adressen, Abfrageparameter, Namen, Token und Passwörter; Sicherungen
  verschlüsselt mit einem Schlüssel aus der Umgebung, getrennt aufzubewahren
```

**Ersetzt in „### Neuen Baustein anschließen“** nichts; ergänzt die Tabelle um:

```markdown
| HTML-Seiten der Oberfläche | `src/accounti/api/seiten/<bereich>.py` mit `router` (optional `NAVIGATION`) | `routermodule()` in `api/app.py` |
| REST-Endpunkte | `src/accounti/api/rest/<bereich>.py` mit `router` | `routermodule()` in `api/app.py`, Präfix `/api/v1` |
```

### config/accounti.example.yaml

**Ersetzt** den Abschnitt am Ende

```yaml
# Server
server:
  host: "127.0.0.1"
  port: 8400
```

durch:

```yaml
# Web-Oberfläche und REST-API (accounti serve) — TLS über einen Reverse-Proxy (docs/betrieb.md)
server:
  host: "127.0.0.1"               # im Container 0.0.0.0
  port: 8400
  cookie_sicher: true             # Secure + __Host-; nur ohne TLS (lokal) false
  vertrauenswuerdige_proxies: ["127.0.0.1"]   # nur deren X-Forwarded-* gelten
  max_formular_kb: 64
  max_beleg_mb: 20                # je Anfrage an POST /api/v1/belege
  anmeldungen_gleichzeitig: 2     # scrypt: 128 MiB je Passwort-Prüfung, sonst 503
  anmeldung_warten_sekunden: 5

# Anmeldung (optional — ohne Abschnitt gelten diese Werte; in der CLI nur strenger)
auth:
  passwort_mindestlaenge: 12      # mit zweitem Faktor; NIST 800-63B-4 verlangt ≥ 8
  sperre_nach_fehlversuchen: 5
  sperre_minuten: 15
  fehlversuche_obergrenze: 100    # in Folge, dann gesperrt bis „benutzer entsperren“
  sitzung_leerlauf_minuten: 30
  sitzung_hoechstdauer_stunden: 8
  totp_toleranz_schritte: 1
  einmalcode_bestaetigung: true   # Browser-Freigaben mit Einmalcode (in der CLI immer)
  aussteller: accounti            # Name in der Authenticator-App

# Mehrere eigene Gesellschaften (optional — ohne Abschnitt gibt es eine: „standard“)
# gesellschaften:
#   systemdatenbank: "${ACCOUNTI_SYSTEM_DB}"   # Benutzer, Rollen, Sitzungen, Token
#   standard: muster
#   eintraege:
#     muster:
#       name: Muster GmbH
#       datenbank: "${ACCOUNTI_DB_MUSTER}"
#       archiv: archiv/muster
#       konfiguration: config/muster.yaml     # eigener Kontenrahmen, Wirtschaftsjahr, Firmendaten
#     tochter:
#       name: Tochter UG
#       datenbank: "${ACCOUNTI_DB_TOCHTER}"
#       archiv: archiv/tochter
#       konfiguration: config/tochter.yaml
```

**Ergänzt im Abschnitt `zahlung`** der Beispieldatei:

```yaml
  ersteller_darf_freigeben: false # mit Benutzern: wer den Lauf anlegt, gibt ihn nicht frei
```

(Der Eintrag `database: url:` am Anfang der Beispieldatei wird von keinem Befehl gelesen; die
Datenbank kommt aus `--db` bzw. `ACCOUNTI_DB` — beim Zusammenführen den Kommentar dort
entsprechend ändern: `# Datenbank: --db oder ACCOUNTI_DB (dieser Eintrag wird nicht gelesen)`.)
