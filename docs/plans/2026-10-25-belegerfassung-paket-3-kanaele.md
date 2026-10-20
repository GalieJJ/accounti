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
| `src/accounti/belege/kanaele/abholung.py` | `KanalError`, `AbholKanal` (Basisklasse der Kanäle mit Gegenstelle, sammelt Hinweise) |
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

- [x] **Anhänge** (`tests/test_kanaele_email.py`): PDF-Anhang byte-genau (Base64, Quoted-Printable), mehrere Anhänge, Anhang in weitergeleiteter Nachricht, eingebettetes Logo übersprungen, Textkörper übersprungen, unerlaubter Typ und zu große Datei als Hinweis, RFC-2231-Dateiname, fehlender Dateiname.
- [x] **IMAP-Attrappe** (`tests/imap_attrappe.py`): LOGIN, CAPABILITY, SELECT/EXAMINE mit UIDVALIDITY, UID SEARCH (ALL, SINCE), UID FETCH (RFC822.SIZE, BODY.PEEK[]), UID STORE, UID MOVE, LOGOUT, STARTTLS; Protokoll der Befehle.
- [x] **EmailKanal gegen die Attrappe:** holt Anhänge mit Herkunft „E-Mail … von …“; zweiter Lauf holt nichts; neue UIDVALIDITY mit gleicher Message-ID → nichts doppelt; Abbruch vor Bestätigung → erneut geholt, Dublette protokolliert; `belassen` nutzt EXAMINE und ändert keine Flags; `gelesen` setzt `\Seen`; `verschieben` nutzt MOVE; falsches Passwort → `KanalError` ohne Passwort im Text; Nachricht über der Größengrenze wird gemerkt, nicht geholt; `ab` → SEARCH SINCE; Nachricht ohne Anhang gemerkt mit Hinweis.
- [x] **TLS:** `ssl` und `starttls` gegen die Attrappe mit eigener CA (`ca_datei`), falscher Hostname scheitert.
- [x] **CLI:** `belege abholen --kanal email --config …` (Akzeptanz 1 Ende-zu-Ende), `--quelle`, ohne Postfach klare Meldung, Verbindungsfehler → Exit 1; `kanaele zugang email NAME` (verdeckte Eingabe, verschlüsselt); `kanaele nachrichten` zeigt Absender (`tests/test_cli_kanaele.py`).

### Paket C — Webhook

- [x] **Token** (`tests/test_kanaele_webhook.py`): erzeugen (Präfix, Länge), nur Hash gespeichert, prüfen, widerrufen, doppelter Name abgelehnt, „zuletzt genutzt“.
- [x] **App mit TestClient:** ohne/falscher/widerrufener Token → 401 mit `WWW-Authenticate`; Rohdaten-PDF → 200 `neu`, Beleg mit Herkunft und Absender; Multipart mit zwei Dateien und Feld `absender`; JSON mit Base64; zu groß (Content-Length und gestreamt) → 413; falscher Typ → 415; kaputtes JSON/Multipart → 400; zu viele Dateien → 413; gleiche Datei zweimal → `dublette`; Erkenner-Fehler → 200 mit Status `pruefung`; `/gesund` ohne Token.
- [x] **CLI:** `kanaele webhook token NAME` zeigt Token einmal; `tokens` zeigt keinen Klartext; `widerrufen`; `starten` übergibt App, Host und Port an uvicorn (uvicorn ersetzt).

### Paket D — Connector

- [x] **Registry und Basisklasse** (`tests/test_kanaele_connector.py`): `BELEG_CONNECTOREN["json"]`, eigene Connector-Klasse über Registry nutzbar; `ConnectorKanal` merkt Dokument-IDs, zweiter Lauf lädt nichts; Download-Fehler → nicht gemerkt, Hinweis; falscher Typ → gemerkt mit Hinweis.
- [x] **JSON-Connector gegen lokalen HTTP-Server:** Liste mit Punktpfad, Seiten (Seitenparameter bis leere Seite / `max_seiten`), Next-URL, Datei binär und als Base64-Feld, `{id}` URL-kodiert, Kopfzeilen mit `${VAR}` und `{zugang}`, Kopfzeilen nicht an fremde Hosts, fremde Download-Hosts nur aus `erlaubte_hosts`, http außerhalb localhost abgelehnt, 401/500 → `KanalError`, Antwort über der Grenze.
- [x] **CLI:** `belege abholen --kanal connector`, `kanaele connectoren`, `kanaele zugang connector NAME`.

### Paket E — Akzeptanz und Abschluss

- [x] **Akzeptanz 1–6 über die neuen Kanäle** (`tests/test_kanaele_akzeptanz.py`).
- [x] CLI-Probelauf unter `/tmp` (Webhook mit curl, `belege abholen --kanal email` gegen die Attrappe).
- [x] `pytest`, `ruff check`, `ruff format --check`, `mypy src` grün; Checkboxen abhaken.

**Probelauf (20.10.2026, `/tmp/accounti-kanaele-probe`):** IMAP-Attrappe als eigener
Prozess, `belege abholen --kanal email` → `Rechnung.pdf` erfasst (172,50 EUR), ZIP-Anhang als
Hinweis; `kanaele webhook starten` mit echtem uvicorn: `GET /gesund` 200, ohne Token 401,
dieselbe Rechnung per `curl -F` 200 `dublette`, ZIP 415, Tankquittungs-Scan per Rohdaten 200
`neu` und mit dem installierten Tesseract erfasst (75,83 EUR); `kanaele nachrichten` zeigt
Absender und Hinweise, `kanaele webhook tokens` keinen Klartext.

## Akzeptanzkriterien → Tests

| Nr | Kriterium (Spec 7) | Tests |
|----|--------------------|-------|
| 1 | PDF-Rechnung wird ohne Zutun zu einem `Beleg` mit Beträgen, Belegdatum, Lieferant | `test_kanaele_akzeptanz.py::test_akzeptanz_1_pdf_rechnung_wird_ohne_zutun_zum_beleg[email,webhook,connector]`, `test_cli_kanaele.py::test_pdf_per_email_wird_erfasst`, `::test_connector_ende_zu_ende`; Watch-Ordner weiter `test_cli_belege.py::test_pdf_im_watch_ordner_wird_erfasst` |
| 2 | Zwei Steuersätze → zwei `Belegposition` | `test_kanaele_akzeptanz.py::test_akzeptanz_2_zwei_steuersaetze_zwei_positionen[email,webhook,connector]` |
| 3 | Derselbe Beleg über mehrere Kanäle → ein Datensatz, Dublette protokolliert | `test_kanaele_akzeptanz.py::test_akzeptanz_3_derselbe_beleg_ueber_vier_kanaele_ein_datensatz` (Ordner, E-Mail, Webhook, Connector, dazu andere Datei mit gleicher Belegnummer), `test_kanaele_webhook.py::test_gleiche_datei_zweimal_ist_dublette`, `::test_gleichzeitige_gleiche_uploads_ergeben_einen_beleg` |
| 4 | Kreditkartenabrechnung mit zwölf Umsätzen → zwölf Positionen | `test_kanaele_akzeptanz.py::test_akzeptanz_4_kreditkartenabrechnung_per_connector` |
| 5 | Unlesbarer Scan → „zur Prüfung“ mit Begründung, Pipeline läuft weiter | `test_kanaele_akzeptanz.py::test_akzeptanz_5_unlesbarer_scan_per_email_geht_zur_pruefung`, `test_kanaele_webhook.py::test_erkenner_fehler_geht_zur_pruefung` |
| 6 | Originaldatei unverändert im Archiv | `test_kanaele_akzeptanz.py::test_akzeptanz_6_original_unveraendert_im_archiv[email,webhook,connector]`, `test_kanaele_webhook.py::test_rohdaten_werden_aufgenommen`, `test_kanaele_email.py::test_pdf_anhang_byte_genau_und_absender` |

Auftragspunkte zusätzlich: Passwort nie im Klartext (`test_kanaele_einstellungen.py::test_passwort_im_klartext_ist_ein_fehler`,
`test_kanaele_gedaechtnis.py::test_zugang_verschluesselt_und_gebunden`, `test_cli_kanaele.py::test_zugang_im_tresor_und_abholen_damit`),
verarbeitete Nachrichten gemerkt (`test_kanaele_email.py::test_holt_anhaenge_merkt_nachrichten_und_laesst_postfach_unberuehrt`,
`::test_neue_uidvalidity_gleiche_message_id_holt_nichts_doppelt`, `::test_ohne_bestaetigung_wird_nicht_gemerkt`),
Absender als Hinweis (`test_kanaele_akzeptanz.py::test_absender_ist_hinweis_zum_beleg`), Token nur gehasht
(`test_kanaele_webhook.py::test_token_nur_als_hash_gespeichert`), Größen- und Typprüfung (`::test_zu_gross_413`,
`::test_falscher_typ_415_und_nichts_gespeichert`, `test_kanaele_pruefung.py`), Webhook per CLI startbar
(`test_cli_kanaele.py::test_webhook_starten_uebergibt_app_an_uvicorn`), generischer Connector
(`test_kanaele_connector.py`).

## Grenzen

- **Kein OAuth2 (XOAUTH2) für IMAP.** Angemeldet wird mit `LOGIN` (Benutzer + Passwort bzw.
  App-Passwort). Microsoft 365/Exchange Online (Basic Auth abgeschaltet) lässt sich damit nicht
  anbinden, Gmail nur mit App-Passwort.
- **Kein Dauerbetrieb im E-Mail-Kanal:** kein IMAP IDLE, kein eingebauter Zeitplaner —
  `accounti belege abholen --kanal email` per Cron/systemd-Timer aufrufen.
- **Ordnernamen nur ASCII**; modified UTF-7 (RFC 3501 5.1.3) ist nicht umgesetzt.
- **E-Mails ohne Anhang** (Rechnung nur im HTML-Text, z. B. Plattform-Quittungen) werden kein
  Beleg; sie stehen mit Hinweis „keine Belegdatei“ in `kanal_nachrichten`. Die E-Mail selbst wird
  nicht archiviert. Enthält sie selbst steuerlich Relevantes (Handels-/Geschäftsbrief, BFH XI R
  15/23), muss das Mailarchiv sie aufbewahren — accounti tut das nicht. Die GoBD-Randziffern nach
  der 2. Änderung (14.07.2025) habe ich nur aus Sekundärquellen, nicht am BMF-Text geprüft.
- **Nicht angenommene Formate:** ZIP, Office-Dateien, `.eml`, GIF, **HEIC/WebP** (übliche
  Handyfotos!) werden mit Hinweis abgelehnt — die Erkennung könnte sie nicht lesen.
- **Message-ID:** Eine andere Nachricht mit bereits bekannter Message-ID (fehlerhaftes
  Absendersystem) wird übersprungen — mit Hinweis, aber ohne Beleg.
- **Kein „Vergessen“:** Gemerkte Nachrichten/Dokumente lassen sich nicht per CLI zurücksetzen;
  erneutes Abholen nur über die Datenbank.
- **Verschieben** nur, wenn der Server MOVE kann; sonst bricht der Lauf vorher mit Meldung ab.
- **Webhook:** kein eigenes TLS (Reverse-Proxy nötig), kein Rate-Limit und keine Sperre nach
  Fehlversuchen, keine direkte Anbindung von Messenger-APIs (Telegram-Bot, WhatsApp Business) —
  nur Weiterleitung über Automationswerkzeuge. Die Sperre gegen gleichzeitige Aufnahmen gilt nur
  innerhalb eines Prozesses: mehrere uvicorn-Worker oder ein gleichzeitig laufendes
  `belege abholen` sind nicht gegeneinander abgesichert (die Dublettenprüfung der Pipeline ist
  nicht atomar — das gilt schon seit Paket 1). Die LLM-Stufe ist im Webhook-Dienst nicht wählbar.
- **Generischer Connector:** nur GET mit Kopfzeilen/Parametern; kein OAuth-Ablauf, kein
  POST-Listing, keine inkrementellen Filter (z. B. „seit letztem Lauf“) — jedes Mal wird die
  ganze Liste gelesen, Bekanntes aber nicht erneut geladen. Die Liste muss ein JSON-Array sein;
  die GetMyInvoices-Doku beschreibt `records` als Objekt — passt die echte Antwort nicht, braucht
  es einen eigenen Connector-Typ. Gescheiterte Downloads werden bei jedem Lauf ohne Pause erneut
  versucht. Das GetMyInvoices-Beispiel ist **nicht** gegen ein Konto geprüft.
- **Keine echten Gegenstellen:** Kein echter Mailserver und kein echtes Portal wurden
  angesprochen; alle Tests laufen gegen den lokalen IMAP-Server, den TestClient und einen lokalen
  HTTP-Server.
- **Absender ≠ Kontakt:** Der Absender wird gespeichert, aber `kontakte/erkennung.py` nutzt ihn
  (noch) nicht zur Zuordnung.
- **Datenbank:** vier neue Tabellen (`kanal_nachrichten`, `kanal_nachricht_dateien`,
  `webhook_tokens`, `kanal_zugaenge`) ohne Migration (entsteht beim Zusammenführen); getestet nur
  mit SQLite.
- Starlette 1.6 meldet im Test eine `DeprecationWarning` für `httpx` im TestClient — betrifft nur
  die Testumgebung.

## Doku-Bausteine

### README — Statuszeile (Tabelle „Belege & Rechnungen“)

```markdown
| ✅ | **Belegeingang** | Überwachter Ordner, Upload, IMAP-Postfach (Anhänge, Absender als Hinweis, verarbeitete Nachrichten gemerkt), tokengeschützter Webhook für Fremdsysteme und Messenger-Weiterleitungen, Connectoren für Belegportale (generisch per JSON/HTTP-Konfiguration); Typ- und Größenprüfung am Inhalt, Dublettenschutz über alle Kanäle |
```

### README — Nutzungsblock (unter „Belege und E-Rechnungen“)

```bash
# Belege aus dem Postfach holen (Abschnitt belegkanaele.email; Passwort per ${VAR} oder Tresor)
accounti kanaele zugang email rechnungen         # Passwort verschlüsselt ablegen (ACCOUNTI_SCHLUESSEL)
accounti belege abholen --kanal email            # alle Postfächer, oder --quelle rechnungen
accounti kanaele nachrichten --kanal email       # verarbeitete Nachrichten mit Absender

# Webhook für Fremdsysteme und Messenger-Weiterleitungen (n8n, Make, Zapier, curl)
accounti kanaele webhook token n8n               # Token wird nur jetzt angezeigt
accounti kanaele webhook starten                 # 127.0.0.1:8410 — TLS über einen Reverse-Proxy
curl -H "Authorization: Bearer $TOKEN" -F datei=@rechnung.pdf -F absender="Telegram Erika" \
  http://127.0.0.1:8410/belege

# Belegportal über seine API (Abschnitt belegkanaele.connectoren)
accounti kanaele connectoren                     # Typen und Prüfung der Konfiguration
accounti kanaele zugang connector getmyinvoices  # API-Schlüssel verschlüsselt ablegen
accounti belege abholen --kanal connector
```

### CHANGELOG

**Hinzugefügt**

```markdown
- **Belegerfassung, Paket 3 – Kanäle E-Mail, Webhook, Connector** (Baustein 2 damit fertig):
  `accounti belege abholen --kanal email` holt die Anhänge neuer Nachrichten aus IMAP-Postfächern
  (TLS mit Zertifikatsprüfung, eigene CA möglich; Ordner nur lesend, `BODY.PEEK[]`; danach
  wahlweise gelesen markieren oder verschieben), speichert Absender, Betreff und Message-ID als
  Hinweis und merkt sich verarbeitete Nachrichten (`accounti kanaele nachrichten`); Passwörter nur
  per `${UMGEBUNGSVARIABLE}` oder verschlüsselt im Tresor (`accounti kanaele zugang`).
  Tokengeschützter Webhook für Fremdsysteme und Messenger-Weiterleitungen
  (`accounti kanaele webhook token|tokens|widerrufen|starten`, FastAPI): Rohdaten,
  multipart/form-data und JSON mit Base64, Tokens nur als SHA-256 gespeichert, Größe (413) und
  Typ am Inhalt (415) geprüft, bevor etwas gespeichert wird. Connectoren für Belegportale mit
  Registry `BELEG_CONNECTOREN` und generischem JSON/HTTP-Connector (`typ: json`, Seiten,
  Base64-Inhalte, Zugangsdaten nur an den eigenen Host) — `accounti belege abholen --kanal
  connector`, `accounti kanaele connectoren`. Neuer, optionaler Abschnitt `belegkanaele`; neue
  Tabellen `kanal_nachrichten`, `kanal_nachricht_dateien`, `webhook_tokens`, `kanal_zugaenge`.
  Keine neue Abhängigkeit
```

**Geändert**

```markdown
- `accounti belege abholen` kennt `--kanal email|connector`, `--quelle` und `--config`; ein
  unbekannter Kanal nennt alle abholbaren Kanäle, `--kanal webhook` verweist auf
  `accounti kanaele webhook starten`
```

**Behoben**

```markdown
(nichts in diesem Paket)
```

### docs/bauplan.md

Zeile der Bausteinkarte:

```markdown
| 2 | Belegerfassung & Dokumentenmanagement | `belege/` | ✅ fertig | [Spec](specs/2026-08-10-belegerfassung.md) |
```

Absatz (ersetzt „Baustein 2 ist teilweise fertig …“):

```markdown
**Baustein 2 ist fertig:** Ordner- und Upload-Kanal, Archiv, Dublettenprüfung, Eingangsprotokoll
([Paket 1](plans/2026-10-19-belegerfassung-paket-1.md)), Erkennung, OCR und Positionssplit
([Paket 2](plans/2026-10-19-belegerfassung-paket-2.md)) sowie die Kanäle E-Mail (IMAP),
Webhook und Connector für Belegportale ([Paket 3](plans/2026-10-25-belegerfassung-paket-3-kanaele.md)).
Offen als Erweiterungen: OAuth2 für Microsoft 365 und Gmail, IMAP IDLE statt Abruf per Timer,
HEIC-Fotos, Rechnungen im E-Mail-Text und eigene Connector-Typen für einzelne Portale.
```

### docs/architektur.md — Modulabschnitt `belege/`

Kopf: `### belege/ *(vorhanden — [Baustein 2](specs/2026-08-10-belegerfassung.md))*`; die Zeile
zu `kanaele/` wird ersetzt durch:

```markdown
- `kanaele/` — `BELEG_KANAELE`-Registry: `ordner`, `upload`, `email`, `webhook`, `connector`. Alle liefern nur Rohdatei plus Herkunft; `pruefung.py` prüft für alle Typ am Inhalt (PDF, XML ohne DTD, JPEG, PNG, TIFF) und Größe. `email.py` holt Anhänge per IMAP (UID-Befehle, `BODY.PEEK[]`, Ordner nur lesend, TLS mit Zertifikatsprüfung), Absender als Hinweis; `gedaechtnis.py` merkt verarbeitete Nachrichten in `kanal_nachrichten` (Ordner + UIDVALIDITY + UID, Message-ID) erst, wenn alle Anhänge aufgenommen sind. `connector.py` ist Basisklasse und Registry `BELEG_CONNECTOREN` für Belegportale, `json_http.py` der generische JSON/HTTP-Connector. Geheimnisse nur als `${VAR}` oder im Tresor (`zugaenge.py`, AES-GCM wie `bank/tresor.py`). Konfiguration: Abschnitt `belegkanaele` (`einstellungen.py`). *(vorhanden)*
- `webhook/` — FastAPI-Endpunkt `POST /belege` für Fremdsysteme und Messenger-Weiterleitungen: Bearer-Token (gespeichert nur als SHA-256), Rohdaten/multipart/JSON, Größe und Typ werden geprüft, bevor etwas gespeichert wird; Aufnahmen je Prozess serialisiert. Start mit `accounti kanaele webhook starten`, TLS über einen Reverse-Proxy. *(vorhanden)*
```

Abschnitt „Neuen Beleg-Kanal hinzufügen“ (ohne „*(geplant)*“), ergänzt um:

```markdown
Ein Belegportal braucht meist keinen neuen Kanal, sondern nur einen Eintrag unter
`belegkanaele.connectoren` mit `typ: json`. Reicht das nicht (OAuth, POST-Abfragen, eigene
Formate), implementiert ein Connector `BelegConnector` (`dokumente()`, `lade()`, eigenes
Einstellungsmodell) und trägt sich mit `registriere_connector` in `BELEG_CONNECTOREN` ein —
Dateiprüfung, Gedächtnis, Dublettenprüfung und Archiv bleiben dieselben.
```

Und im Datenmodell eine Zeile:

```markdown
| `AbgeholteNachricht` | Kanal, Quelle, Schlüssel (UIDVALIDITY/UID, Dokument-ID), Message-ID, Absender, Betreff, Dateien (Hash), Hinweis | → `Beleg` über den Datei-Hash |
```

### config/accounti.example.yaml — neuer Abschnitt

```yaml
# Beleg-Kanäle (optional — ohne diesen Abschnitt gibt es nur Ordner und Upload)
belegkanaele:
  max_groesse_mb: 25           # je Datei; der Typ wird am Inhalt geprüft
  dateitypen: [pdf, xml, jpeg, png, tiff]
  email:                       # accounti belege abholen --kanal email
    - name: rechnungen
      host: "imap.meine-firma.example"
      port: 993
      verschluesselung: ssl    # ssl, starttls oder keine (nur localhost)
      benutzer: "rechnungen@meine-firma.example"
      passwort: "${ACCOUNTI_IMAP_PASSWORT}"   # oder: accounti kanaele zugang email rechnungen
      ordner: INBOX
      # ab: 2026-01-01          # ältere Nachrichten nicht abholen
      nach_abholen: belassen   # belassen, gelesen oder verschieben (dann ziel_ordner)
      # ziel_ordner: "Belege/abgeholt"
      # ca_datei: /etc/ssl/firma-ca.pem   # eigene CA des Mailservers
  webhook:                     # accounti kanaele webhook starten
    host: "127.0.0.1"          # TLS über einen Reverse-Proxy davor
    port: 8410
    max_dateien: 10
    max_anfrage_mb: 60
  connectoren:                 # accounti belege abholen --kanal connector
    # Beispiel nach der OpenAPI-Doku von GetMyInvoices (v3) — nicht gegen ein Konto geprüft
    - name: getmyinvoices
      typ: json
      basis_url: "https://api.getmyinvoices.com/accounts/v3"
      kopfzeilen:
        X-API-KEY: "{zugang}"  # accounti kanaele zugang connector getmyinvoices
        User-Agent: "accounti (Konto 12345)"   # verlangt einen eindeutigen User-Agent
      liste:
        pfad: /documents
        parameter: {perPage: "100", archivedFilter: "1"}
        eintraege: records
        seite_parameter: pageNumber
      felder: {id: documentUid, dateiname: filename, absender: companyName}
      datei:
        pfad: "/documents/{id}"
        parameter: {includeDocument: "true"}
        inhalt: fileContent    # Base64 in der JSON-Antwort
```
