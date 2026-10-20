# Belegerfassung, Paket 3 (Kanäle: E-Mail, Webhook, Connector) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Belege kommen nicht mehr nur aus dem Watch-Ordner und per Upload, sondern auch aus einem
IMAP-Postfach, über einen tokengeschützten HTTP-Endpunkt (Fremdsysteme, Messenger-Weiterleitungen
über n8n/Make/Zapier) und aus Belegportalen über deren API. Alle drei Kanäle liefern nur
Rohdatei plus Herkunft; Archiv, Erkennung, Dublettenprüfung und Eingangsprotokoll laufen
unverändert über `belege/pipeline.nimm_auf`. Damit ist Baustein 2 fertig.

**Spec:** [`docs/specs/2026-08-10-belegerfassung.md`](../specs/2026-08-10-belegerfassung.md),
Abschnitte 4.1 und 4.8 · Akzeptanzkriterien 1–6 (für die neuen Kanäle erneut belegt) ·
**Baut auf:** [Paket 1](2026-10-19-belegerfassung-paket-1.md), [Paket 2](2026-10-19-belegerfassung-paket-2.md)

```
IMAP-Postfach ──▶ EmailKanal ──────┐   (UID, BODY.PEEK[], Anhänge, Absender als Hinweis)
HTTP POST ──────▶ Webhook (FastAPI) ┼─▶ Dateiprüfung ─▶ RohBeleg ─▶ nimm_auf (Archiv,
Portal-API ─────▶ ConnectorKanal ───┘   (Typ am Inhalt,             Dubletten, Erkennung,
                  └ BELEG_CONNECTOREN   Größe)                      Eingangsprotokoll)
                    └ json (generisch, per Konfiguration)
                                        │
                kanal_nachrichten ◀─────┘ verarbeitete Nachrichten/Dokumente, Absender
```

## Recherche (Stand 20.10.2026)

| Thema | Befund | Quelle |
|-------|--------|--------|
| IMAP | IMAP4rev2 ist RFC 9051 (ersetzt RFC 3501). Postfachname + UIDVALIDITY + UID bezeichnen eine Nachricht „für immer“ (2.3.1.1); `BODY.PEEK[]` setzt `\Seen` nicht (6.4.5); `UID SEARCH` liefert UIDs (6.4.9); MOVE ist Teil von IMAP4rev2 (6.4.8, vorher RFC 6851) | [RFC 9051](https://www.rfc-editor.org/rfc/rfc9051.html) |
| imaplib | `IMAP4_SSL(host, port, ssl_context=…, timeout=…)` (timeout seit 3.9), `starttls(ssl_context)`; **ohne** `ssl.create_default_context()` werden Zertifikat und Hostname **nicht** geprüft; `uid()` für UID-Befehle; `MOVE` ist in `imaplib.Commands` (3.12 geprüft); Postfachnamen werden nicht automatisch gequotet | [docs.python.org/3/library/imaplib](https://docs.python.org/3/library/imaplib.html), lokale Quelle Python 3.12.3 |
| Anmeldung Gmail | seit 14.03.2025 kein Zugriff mehr mit reinem Benutzername/Passwort („less secure apps“) für IMAP; OAuth oder App-Passwort | [Google Workspace: Transition from less secure apps to OAuth](https://knowledge.workspace.google.com/admin/sync/transition-from-less-secure-apps-to-oauth) |
| Anmeldung Microsoft 365 | Basic Authentication für IMAP/POP in Exchange Online abgeschaltet (seit 01.10.2022), OAuth 2.0 nötig | [Microsoft Learn: Deprecation of Basic authentication in Exchange Online](https://learn.microsoft.com/en-us/exchange/clients-and-mobile-in-exchange-online/deprecation-of-basic-authentication-exchange-online) |
| GoBD und E-Mail | Dient eine E-Mail nur als Transportmittel (z. B. für eine angehängte Rechnung), ist sie selbst nicht aufbewahrungspflichtig („wie der Papierbriefumschlag“); Anhänge sind im Originalformat aufzubewahren (GoBD 2019 Rz. 121, sinngemäß zitiert nach Fachbeiträgen; die Randziffern nach der 2. Änderung vom 14.07.2025 habe ich nicht am Primärtext geprüft). Eingehende elektronische Belege sind im empfangenen Format aufzubewahren (Rz. 131 laut KPMG) | [KPMG zur 2. GoBD-Änderung](https://kpmg.com/de/de/themen/2025/07/bmf-gobd-zweite-aenderung.html), [Bitkom-Merksätze E-Mails und GoBD](https://www.bitkom.org/sites/main/files/file/import/160108-BIT-Merksaetze-Emails-und-GoBD.pdf) |
| E-Mail als Handelsbrief | BFH, Beschl. v. 30.04.2025, XI R 15/23: E-Mails können Handels- oder Geschäftsbriefe (§ 147 Abs. 1 Nr. 2, 3 AO) und damit selbst aufbewahrungspflichtig sein | [PwC-Blog](https://blogs.pwc.de/de/steuern-und-recht/article/250902/e-mails-als-vorzulegende-handels-und-geschaeftsbriefe/), [KPMG](https://kpmg.com/de/de/home/themen/2025/09/bfh-email-handelsbrief-vorlage.html) |
| HTTP-Status | 401 Unauthorized (15.5.2), 413 Content Too Large (15.5.14, Verbindung darf geschlossen werden), 415 Unsupported Media Type (15.5.16) | [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html) |
| Bearer-Token | `Authorization: Bearer <token>`, Antwort 401 mit `WWW-Authenticate: Bearer` | RFC 6750 |
| Datei-Upload in FastAPI | `File`/`UploadFile`/Formulare brauchen `python-multipart` — in der venv **nicht** installiert | [FastAPI: Request Files](https://fastapi.tiangolo.com/tutorial/request-files/) |
| multipart/form-data | RFC 7578; der `email`-Parser der Standardbibliothek liest es byte-genau (selbst geprüft: 300 Zufallsdateien mit CR/LF/Boundary-ähnlichen Folgen, RFC-2231-Dateinamen und rohe UTF-8-Dateinamen) | RFC 7578, eigener Versuch |
| Anhangsgrenze | Gmail: 25 MB beim Senden, 50 MB beim Empfang (Sekundärquellen) | [IONOS Digital Guide](https://www.ionos.com/digitalguide/e-mail/technical-matters/gmail-attachment-size-limit/) |
| Belegportal (Beispiel) | GetMyInvoices API v3 (OpenAPI 3.0, Stand der Datei 17.09.2026): Anmeldung per Kopfzeile `X-API-KEY`, eindeutiger `User-Agent` Pflicht; `GET /documents` mit `perPage`/`pageNumber`, Einträge unter `records` mit `documentUid`, `filename`, `companyName`; `GET /documents/{documentUid}` liefert `fileContent` (Base64 wie beim Upload) | `https://api.getmyinvoices.com/accounts/v3/doc/api.json` (abgerufen 20.10.2026), **nicht** gegen ein Konto geprüft |

---

## Schnitt in Pakete

| Paket | Inhalt | Commit |
|-------|--------|--------|
| A Grundlagen | Abschnitt `belegkanaele` mit Lader, Dateiprüfung (Typ am Inhalt, Größe), Gedächtnis `kanal_nachrichten`, Zugänge im Tresor | ja |
| B E-Mail | `EmailKanal` (IMAP, Anhänge, Absender, Merken, Nachbehandlung), IMAP-Attrappe als echter lokaler Server (auch TLS/STARTTLS), `belege abholen --kanal email`, `kanaele zugang`, `kanaele nachrichten` | ja |
| C Webhook | `WebhookKanal`, FastAPI-App (`belege/webhook/`), Tokens gehasht, Rohdaten/Multipart/JSON, Größe und Typ, `kanaele webhook token|tokens|widerrufen|starten` | ja |
| D Connector | `BelegConnector` + `BELEG_CONNECTOREN`, `ConnectorKanal`, generischer JSON/HTTP-Connector gegen lokalen HTTP-Server, `belege abholen --kanal connector`, `kanaele connectoren` | ja |
| E Akzeptanz | Akzeptanzkriterien 1–6 über die neuen Kanäle, CLI-Probelauf unter /tmp, Plan abhaken | ja |

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Schnittstelle | Alle neuen Kanäle sind `BelegKanal` in `BELEG_KANAELE` und liefern `RohBeleg`; aufgenommen wird nur über `nimm_auf` | Spec 4.1 „kein Kanal kennt Buchhaltungslogik“; Akzeptanz 1–6 gelten damit für jeden Kanal |
| Konfiguration | Abschnitt `belegkanaele` in `config/accounti.yaml`, Lader `lade_belegkanaele` im Paket; ohne Abschnitt Standardwerte (keine Postfächer, keine Connectoren, Webhook 127.0.0.1:8410) | Vorgabe; alles läuft auch ohne |
| `${VAR}` | wird erst beim Bau des gewählten Kanals aufgelöst | eine fehlende Variable eines anderen Postfachs stört nicht |
| Passwort | `passwort` darf nur `${UMGEBUNGSVARIABLE}` sein — Klartext ist ein Konfigurationsfehler; fehlt es, kommt es aus dem Tresor (`accounti kanaele zugang email NAME`, AES-GCM aus `bank/tresor.py`, Bezug `kanal:email:NAME`) | nie Klartext in Dateien |
| Geheimnisse beim Connector | Kopfzeilen und Parameter mit Namen wie `authorization`, `*key*`, `*token*`, `*secret*`, `*passw*`, `cookie` müssen `${VAR}` oder `{zugang}` (Tresor) enthalten | dieselbe Regel für API-Schlüssel |
| Dateiprüfung | Typ am Inhalt (Signatur), nicht an Endung oder Content-Type: PDF, XML (wohlgeformtes Wurzelelement, keine DTD), JPEG, PNG, TIFF — dieselben Formate wie `erkennung.py`; Standard höchstens 25 MB je Datei; leere Dateien abgelehnt; Dateiname ohne Pfadanteile, Endung passend zum Typ | was die Erkennung nicht lesen kann, gehört nicht ins Archiv; 25 MB = übliche Anhangsgrenze |
| IMAP | `imaplib` (Standardbibliothek), nur UID-Befehle; `EXAMINE` (nur lesen), solange nichts markiert oder verschoben wird; Abruf mit `BODY.PEEK[]`; Größe vorab per `RFC822.SIZE` (Standard höchstens 50 MB je Nachricht) | keine Abhängigkeit; das Postfach bleibt unverändert |
| Verschlüsselung | `ssl` (Standard, 993), `starttls` (143), `keine` nur für localhost; immer `ssl.create_default_context()` (Zertifikat und Hostname), eigene CA per `ca_datei` | imaplib prüft sonst nicht |
| Anmeldung | `LOGIN` mit Benutzer und (App-)Passwort; kein OAuth2 | siehe Grenzen |
| Verarbeitete merken | Tabelle `kanal_nachrichten`, eindeutig über (Kanal, Quelle, Schlüssel); Schlüssel bei E-Mail `Ordner:UIDVALIDITY:UID`, zusätzlich Message-ID je Quelle; bei Connectoren die Dokument-ID | RFC 9051 2.3.1.1; Message-ID fängt neu angelegte Postfächer ab |
| Wann gemerkt wird | erst wenn alle Anhänge einer Nachricht aufgenommen und bestätigt sind; bricht der Lauf ab, holt der nächste die Nachricht erneut — schon Aufgenommenes fängt die Hash-Dublettenprüfung | kein Belegverlust bei Absturz, vorhandene Dublettenprüfung |
| Nach dem Abholen | `belassen` (Standard), `gelesen` (`\Seen`), `verschieben` (`UID MOVE`, nur wenn der Server MOVE kann) | das Postfach gehört dem Menschen; das Gedächtnis in der DB reicht |
| Anhänge | jeder MIME-Teil mit Dateiname oder Belegtyp, auch in weitergeleiteten Nachrichten; Textkörper und eingebettete Bilder (`inline` mit `Content-ID`, z. B. Signaturlogos) werden übersprungen; Abgelehntes steht als Hinweis an der Nachricht | Logos sind keine Belege; nichts verschwindet still |
| Absender | From-Adresse und -Name, Betreff, Datum, Message-ID in `kanal_nachrichten`; Adresse und Betreff zusätzlich in `Beleg.herkunft`; `absender_zu_beleg()` liefert den Hinweis zum Beleg | Spec 4.1: Hinweis auf den Kreditor, keine Logik |
| E-Mail selbst | wird nicht archiviert, nur ihre Anhänge byte-genau | GoBD: Mail als Transportmittel nicht aufbewahrungspflichtig; Mails mit eigenem Inhalt → Grenzen |
| Webhook-Framework | FastAPI + uvicorn (vorhanden); Body selbst gelesen und mitgezählt, `Content-Length` vorab geprüft | `python-multipart` fehlt; Größenlimit greift, bevor gepuffert wird |
| Webhook-Formate | Rohdaten (Dateiname per `X-Dateiname` oder `?dateiname=`), `multipart/form-data` (Standardbibliothek `email`), JSON `{"absender", "dateien": [{"dateiname", "inhalt_base64"}]}`; höchstens 10 Dateien und 60 MB je Anfrage | deckt curl, n8n, Make, Zapier ab — ohne neue Abhängigkeit |
| Token | `accounti_wh_` + 256 Bit aus `secrets`; gespeichert nur SHA-256 (Tabelle `webhook_tokens`), Klartext genau einmal bei der Erzeugung; `Authorization: Bearer`; widerrufbar; „zuletzt genutzt“ | hohe Entropie → schneller Hash ohne Salz genügt; Tokens nie in URLs (Logs) |
| Antworten | 200 mit Ergebnis je Datei (`neu`/`dublette`/`verdacht`, Beleg-ID, Status), 400, 401 (+`WWW-Authenticate: Bearer`), 413, 415 | RFC 9110, RFC 6750 |
| Nebenläufigkeit | Aufnahme im Threadpool, je Prozess durch eine Sperre serialisiert | die Dublettenprüfung liest den Bestand — zwei gleichzeitige gleiche Uploads dürfen nicht zwei Belege werden |
| Webhook-Herkunft | `Webhook <Tokenname>` plus optionaler Absender (`absender`-Feld, `X-Absender`); Eintrag in `kanal_nachrichten` | Absender als Hinweis wie bei E-Mail |
| Bindung | Standard `127.0.0.1:8410`; TLS über einen Reverse-Proxy | kein eigener TLS-Stack im Prozess |
| Connector | Basisklasse `BelegConnector` (`dokumente()`, `lade()`) mit eigenem Einstellungsmodell, Registry `BELEG_CONNECTOREN` (Typ → Klasse); der Kanal `connector` holt über die konfigurierten Instanzen und merkt Dokument-IDs | Spec 4.1, analog `BANK_PROVIDER` |
| Generischer Connector | `typ: json`: Liste per GET (Punktpfad zu den Einträgen, Felder `id`/`dateiname`/`absender`/`datum`/`url`), Seiten über Seitenparameter oder Next-URL, Datei binär oder als Base64-Feld einer JSON-Antwort | beschreibt typische REST-Portale ohne Code (Beispiel GetMyInvoices) |
| HTTP-Client | `urllib` (Standardbibliothek), Zeitlimit, Antwortgröße begrenzt | wie `kontakte/ustid.py`; `httpx` ist keine erklärte Abhängigkeit |
| Connector-Sicherheit | `https` Pflicht (`http` nur localhost); Kopfzeilen nur an den Host von `basis_url`; Download-URLs fremder Hosts nur aus `erlaubte_hosts` und dann ohne Kopfzeilen; keine Weiterleitungen auf fremde Hosts mit Zugangsdaten | eine Portalantwort darf Zugangsdaten nicht an Dritte umleiten |
| CLI | `belege abholen --kanal email|connector [--quelle NAME] [--config]` (minimale Erweiterung in `cli.py`), neue Gruppe `kanaele`: `zugang`, `nachrichten`, `connectoren`, `webhook token|tokens|widerrufen|starten` | Spec 4.8 nennt `belege abholen --kanal email` |

## Dateistruktur

| Pfad | Verantwortung |
|------|---------------|
| `src/accounti/belege/kanaele/einstellungen.py` | Pydantic-Modelle und `lade_belegkanaele`, `${VAR}` auflösen, Klartextsperre |
| `src/accounti/belege/kanaele/pruefung.py` | `erkenne_dateityp`, `Dateipruefung`, `DateiAbgelehntError`, `sicherer_dateiname` |
| `src/accounti/belege/kanaele/gedaechtnis.py` | `Gedaechtnis` (Protokoll) und `DbGedaechtnis` (eigene Transaktion) |
| `src/accounti/belege/kanaele/zugaenge.py` | Geheimnisse der Kanäle im Tresor |
| `src/accounti/belege/kanaele/fehler.py` | `KanalError` |
| `src/accounti/belege/kanaele/email.py` | `EmailKanal`, `belegdateien` (Anhänge aus einer Nachricht) |
| `src/accounti/belege/kanaele/webhook.py` | `WebhookKanal` |
| `src/accounti/belege/kanaele/connector.py` | `BelegConnector`, `BELEG_CONNECTOREN`, `ConnectorKanal` |
| `src/accounti/belege/kanaele/json_http.py` | `JsonConnector` (`typ: json`) |
| `src/accounti/belege/kanaele/aufbau.py` | `baue_kanaele` — Kanäle aus der Konfiguration für `belege abholen` |
| `src/accounti/belege/webhook/` | FastAPI-App, Token, Anfrage lesen |
| `src/accounti/models/kanaele.py` | `AbgeholteNachricht`, `WebhookToken`, `KanalZugang` |
| `src/accounti/db/tabellen_kanaele.py` | `kanal_nachrichten`, `webhook_tokens`, `kanal_zugaenge` |
| `src/accounti/db/repo_kanaele.py` | Repository-Funktionen |
| `src/accounti/befehle/kanaele.py` | Befehlsgruppe `kanaele` |
| `tests/imap_attrappe.py` | kleiner IMAP4rev1-Server (Klartext, SSL, STARTTLS) für Tests |

---

## Aufgaben

### Paket A — Grundlagen

- [x] **Einstellungen** (`tests/test_kanaele_einstellungen.py`): ohne Datei/Abschnitt Standardwerte; Postfach, Webhook, Connector lesen; Klartext-Passwort → Fehler; `${VAR}` erst beim Auflösen, fehlende Variable → Fehler mit Namen; `keine` Verschlüsselung nur für localhost; doppelte Namen → Fehler; Geheimnis im Klartext in Connector-Kopfzeilen → Fehler.
- [x] **Dateiprüfung** (`tests/test_kanaele_pruefung.py`): PDF, XML, JPEG, PNG, TIFF erkannt; Text, ZIP, DOCX, HTML, XML mit DTD abgelehnt; leer und zu groß abgelehnt; Typauswahl aus der Konfiguration; Dateiname ohne Pfad, Steuerzeichen, mit passender Endung.
- [x] **Gedächtnis und Zugänge** (`tests/test_kanaele_gedaechtnis.py`): Modelle, Tabellen, Repository; `bekannt` über Schlüssel und Message-ID; eigene Transaktion; Absender zum Beleg über den Datei-Hash; Zugang verschlüsselt, an Kanal und Name gebunden, ohne Schlüssel klare Meldung.

### Paket B — E-Mail

- [ ] **Anhänge** (`tests/test_kanaele_email.py`): PDF-Anhang byte-genau (Base64, Quoted-Printable), mehrere Anhänge, Anhang in weitergeleiteter Nachricht, eingebettetes Logo übersprungen, Textkörper übersprungen, unerlaubter Typ und zu große Datei als Hinweis, RFC-2231-Dateiname, fehlender Dateiname.
- [ ] **IMAP-Attrappe** (`tests/imap_attrappe.py`): LOGIN, CAPABILITY, SELECT/EXAMINE mit UIDVALIDITY, UID SEARCH (ALL, SINCE), UID FETCH (RFC822.SIZE, BODY.PEEK[]), UID STORE, UID MOVE, LOGOUT, STARTTLS; Protokoll der Befehle.
- [ ] **EmailKanal gegen die Attrappe:** holt Anhänge mit Herkunft „E-Mail … von …“; zweiter Lauf holt nichts; neue UIDVALIDITY mit gleicher Message-ID → nichts doppelt; Abbruch vor Bestätigung → erneut geholt, Dublette protokolliert; `belassen` nutzt EXAMINE und ändert keine Flags; `gelesen` setzt `\Seen`; `verschieben` nutzt MOVE; falsches Passwort → `KanalError` ohne Passwort im Text; Nachricht über der Größengrenze wird gemerkt, nicht geholt; `ab` → SEARCH SINCE; Nachricht ohne Anhang gemerkt mit Hinweis.
- [ ] **TLS:** `ssl` und `starttls` gegen die Attrappe mit eigener CA (`ca_datei`), falscher Hostname scheitert.
- [ ] **CLI:** `belege abholen --kanal email --config … ` (Akzeptanz 1 Ende-zu-Ende), `--quelle`, ohne Postfach klare Meldung, Verbindungsfehler → Exit 1; `kanaele zugang email NAME` (verdeckte Eingabe, verschlüsselt); `kanaele nachrichten` zeigt Absender (`tests/test_cli_kanaele.py`).

### Paket C — Webhook

- [ ] **Token** (`tests/test_kanaele_webhook.py`): erzeugen (Präfix, Länge), nur Hash gespeichert, prüfen, widerrufen, doppelter Name abgelehnt, „zuletzt genutzt“.
- [ ] **App mit TestClient:** ohne/falscher/widerrufener Token → 401 mit `WWW-Authenticate`; Rohdaten-PDF → 200 `neu`, Beleg mit Herkunft und Absender; Multipart mit zwei Dateien und Feld `absender`; JSON mit Base64; zu groß (Content-Length und gestreamt) → 413; falscher Typ → 415; kaputtes JSON/Multipart → 400; zu viele Dateien → 413; gleiche Datei zweimal → `dublette`; Erkenner-Fehler → 200 mit Status `pruefung`; `/gesund` ohne Token.
- [ ] **CLI:** `kanaele webhook token NAME` zeigt Token einmal; `tokens` zeigt keinen Klartext; `widerrufen`; `starten` übergibt App, Host und Port an uvicorn (uvicorn ersetzt).

### Paket D — Connector

- [ ] **Registry und Basisklasse** (`tests/test_kanaele_connector.py`): `BELEG_CONNECTOREN["json"]`, eigene Connector-Klasse über Registry nutzbar; `ConnectorKanal` merkt Dokument-IDs, zweiter Lauf lädt nichts; Download-Fehler → nicht gemerkt, Hinweis; falscher Typ → gemerkt mit Hinweis.
- [ ] **JSON-Connector gegen lokalen HTTP-Server:** Liste mit Punktpfad, Seiten (Seitenparameter bis leere Seite / `max_seiten`), Next-URL, Datei binär und als Base64-Feld, `{id}` URL-kodiert, Kopfzeilen mit `${VAR}` und `{zugang}`, Kopfzeilen nicht an fremde Hosts, fremde Download-Hosts nur aus `erlaubte_hosts`, http außerhalb localhost abgelehnt, 401/500 → `KanalError`, Antwort über der Grenze.
- [ ] **CLI:** `belege abholen --kanal connector`, `kanaele connectoren`, `kanaele zugang connector NAME`.

### Paket E — Akzeptanz und Abschluss

- [ ] **Akzeptanz 1–6 über die neuen Kanäle** (`tests/test_kanaele_akzeptanz.py`).
- [ ] CLI-Probelauf unter `/tmp` (Webhook mit curl, `belege abholen --kanal email` gegen die Attrappe).
- [ ] `pytest`, `ruff check`, `ruff format --check`, `mypy src` grün; Checkboxen abhaken.

## Grenzen

(wird mit dem Bau vervollständigt)

## Doku-Bausteine

(wird mit dem Bau vervollständigt)
