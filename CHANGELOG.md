# Changelog

Alle wesentlichen Änderungen an accounti werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [Unreleased]

### Hinzugefügt

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
  Playwright 1.59.1 und axe-core 4.14.0, nicht ausgeliefert). Migration
  `1dd2f6b7c6c8_add_benutzer_vorlieben` (`auth_benutzer`).
- **Web-Oberfläche: Supervisions-Queue, Korrektur → Regel, Deutsch/Englisch** (Baustein 10b,
  Teil 1): `/pruefen` zeigt unsichere Buchungen mit dem Beleg links (PDF im Browser, PNG/JPEG,
  TIFF als Seitenbilder, XRechnung und ZUGFeRD als lesbare Ansicht des strukturierten Teils;
  ohne Beleg die offene Nachforderung bzw. die `belegfrei`-Regel; bei internen Buchungen wie
  AfA Herkunft und Rechenweg) und dem Vorschlag rechts (Konten mit Bezeichnung,
  Steuerschlüssel, Beträge, Confidence, Herkunft und Begründung, Aufgaben). Freigeben,
  korrigieren und zurückstellen (Rückfrage als Aufgabe) in einem Schritt, per Tastatur
  (`j k f e r z b ?`, abschaltbar) und mit HTMX ohne Seitenwechsel; ein Prüfstand in jedem
  Formular verhindert, dass eine veraltete Ansicht storniert, Konflikte und Fachfehler
  erscheinen als Meldung, ein neues Sachkonto verlangt die ausdrückliche Steuerangabe. Aus der
  Korrektur eines Kontierungsvorschlags wird auf Wunsch eine Regel — Muster vorbelegt mit dem
  ganzen Namen der Gegenpartei ohne Rechtsform, mit Vorschau (Treffer je Richtung, verdrängte
  Regel, andere Gegenparteien, Zahlungsdienst, anders gebuchte Treffer; trifft das Muster andere
  Gegenparteien oder jeden Kauf über einen Zahlungsdienst oder hat der Umsatz keinen Namen der
  Gegenpartei, nur nach Bestätigung), nur mit dem neuen Recht `regeln_lernen` zusätzlich zu
  `buchen` (anlegen: buchhalter; sehen, voranschauen und deaktivieren auch der verwalter), nur
  in der Zahlungsrichtung des Umsatzes und nur aus Kontierungsvorschlägen (nicht aus
  Kreditkarte, Anlagen, Marktplatz, offenen Posten), gespeichert in der Datenbank der
  Gesellschaft, im Journal (samt Bestandsabgleich in
  `journal pruefen`) und mit Vorrang vor eigenen und Standardregeln; `/pruefen/regeln` und
  `accounti regeln liste|deaktivieren|uebernehmen`. `/buchungen/{id}` zeigt Storno-Kette, Korrektur und Journal
  und korrigiert freigegebene oder exportierte Buchungen als Storno mit Neubuchung — mit
  frischem Einmalcode. Oberfläche auf Deutsch und Englisch (Sprache je Benutzer, sonst nach
  Browser; Zahlen und Daten je Sprache; Fachbegriffe wie „Buchungssatz“ bleiben deutsch).
  Klassifikation, Kreditkarte, Anlagen, Marktplatz und offene Posten speichern jetzt zu jeder
  Buchung Quelle, Regel und Begründung (`kontierungsgruende`) — beim Marktplatz auch die
  Kursdifferenz einer Auszahlung und ihre Umbuchung nach „anderweitig gebucht“ (Beträge laut
  Bank bzw. Gegenkonto und Abrechnung, verschobener Tag). HTMX 2.0.11 (0BSD) liegt lokal
  unter `/statisch`. Neue Schlüssel `buchhaltung.gelernte_regeln`, `server.sprache`,
  `server.max_vorschau_megapixel`. Gelernte Regeln teilen das Regelmodell der Regeldatei und
  der Standardregeln (Richtung `ausgabe`/`einnahme`, gegen die Richtung nur als Gegenbuchung
  zur Prüfung, Schranke des Mappers gegen die Bankseite) und greifen vor der Regeldatei und
  den Standardregeln im Kontenrahmen der Buchhaltung; greift die Schranke, steht das in der
  Begründung. Zwei Migrationen nach `a14acef69fae` (`d5a849692843`, `e7153706b43a`;
  `SCHEMA_STAND` ist `e7153706b43a`) — **nach dem Update `accounti db upgrade`** für die
  Systemdatenbank und jede Gesellschaft (erkennt auch einen Stand ohne Versionsvermerk vor
  jeder der beiden); `serve` bricht ohne die Migration mit diesem Hinweis ab (Exit 2).
  Auswertungen im Browser (BWA, Kontenblätter, CSV/PDF) folgen mit Teil 2.
- **Belegvollständigkeit & Ordnungsmäßigkeit** (Baustein 7): Prüfregeln als Registry mit
  Schweregrad (`hinweis`, `warnung`, `fehler`) und Schwellen aus dem neuen, optionalen
  Abschnitt `pruefung` — Vollständigkeit (Umsatz ohne Beleg mit Betrag, Datum und
  Gegenpartei; Rechnung ohne Zahlung nach Zahlungsziel; Lücken in Nummernkreisen,
  Kontoauszügen und im Saldoverlauf), Richtigkeit (Pflichtangaben nach § 14 Abs. 4 UStG aus
  dem archivierten Original, Kleinbetragsrechnung nach § 33 UStDV bis 250 €, § 14a UStG bei
  § 13b/§ 6a/§ 3c; Rechenprobe; Steuerschlüssel ./. Sachkonto über die DATEV-Automatikkonten
  der mitgelieferten `accounti/pruefung/skr03.yaml` und Kontenbereiche; Steuersatz zum Land;
  Adressat; Vorsteuer aus ig. Erwerb ohne gültige USt-IdNr.; Dubletten), Zeitgerechtheit
  (unbearbeitete Belege, nach Ablauf des Folgemonats gebucht, Buchung in abgeschlossener
  Periode) und Ordnung (Buchung ohne Beleg, offene Posten mit unplausiblem Alter, Monat nicht
  festgeschrieben) — `accounti pruefen [--period] [--regel] [--archiv] [--ocr]`,
  `pruefen regeln`. Nachforderung: Baustein 7 übernimmt den Prüflauf `beleg_fehlt`
  (Schwellen, begründet belegfreie Umsätze per Muster), `accounti nachfordern`; Anfrage an
  den Lieferanten als Entwurf aus einer Vorlage, gesendet nur mit `--senden`.
  Hash-verkettetes, nur anfügbares Journal über Buchungen (angelegt, korrigiert, freigegeben,
  exportiert, storniert, verworfen), Belege (importiert, verworfene Dubletten, geändert),
  Zahlungsläufe, Jahres- und Monatsabschlüsse, Exporte (`accounti journal`, `journal zeige`,
  `journal pruefen [--kopf]` mit Kette, Verlauf je Objekt und Abgleich von Buchungen,
  Belegen und Sperren aus einem Stand, `journal uebernehmen`). Storno statt Änderung:
  `storniert_durch`/`storno_von` am Buchungssatz, Tabelle `buchungskorrekturen`,
  `accounti buchung storniere|zeige`. Periodenabschluss je Monat (`accounti periode
  schliessen|oeffnen|liste`); EB-Werte des Saldovortrags nimmt ein festgeschriebener Januar
  weiter an; `opos verbuchen --buchungsdatum eingang|offen|JJJJ-MM-TT` für
  Eingangsrechnungen zu einem festgeschriebenen Monat (Vorsteuer nach § 15 Abs. 1 Nr. 1
  UStG, bei Bilanzierung und ohne ausdrückliche `abschluss.gewinnermittlung` nicht über den
  Jahreswechsel). Generierte Verfahrensdokumentation nach GoBD Rz. 151 ff. als Markdown und
  PDF, Fassung im Journal (`accounti verfahrensdoku`). Alembic-Migration `ddc9a184ddb4`
  (Tabellen `journal`, `buchungskorrekturen`, `periodenabschluesse`, Spalten und
  Unique-Indizes `storniert_durch`/`storno_von`, SQLite-Trigger; was ein Befehl vor der
  Migration schon per `init_db` angelegt hat, übernimmt sie) — **nach dem Upgrade einmal
  `accounti journal uebernehmen`**, damit der Bestand von vor dem Journal nicht als „ohne
  Eintrag“ gemeldet wird
- **Anmeldung, Rollen, mehrere Gesellschaften, Betrieb und REST-API** (Baustein 10a):
  Benutzer mit scrypt-Passwort (OWASP: N = 2^17, r = 8, p = 1) und zweitem Faktor nach RFC 6238
  (TOTP, jeder Code einmal; zehn Wiederherstellungscodes, je einer einmal), Sperre nach
  Fehlversuchen (Browser und Server-Shell getrennt; auf der Shell entsperrt man sich mit dem
  zweiten Faktor selbst), Sitzungen mit `__Host-`-Cookie, Leerlauf und Höchstdauer, nur anfügbares
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
- **Live-Bankanbindung, Paket 3 – FinTS & Kreditkarten** (Baustein 5): Provider `fints` über
  python-fints — Produkt-ID je Installation (`ACCOUNTI_FINTS_PRODUKT_ID` oder `bank.fints`),
  Benutzerkennung, PIN und Sitzung (Kundensystem-ID) verschlüsselt im Tresor, camt.052
  bevorzugt, sonst MT940; verlangt die Bank eine Freigabe, setzt `bank abrufen` den Zustand
  `freigabe_noetig`, `accounti fints freigeben` fragt nach der TAN oder wartet auf die App;
  `accounti fints einrichten` wählt das TAN-Verfahren und erledigt die erste Freigabe. Lehnt die
  Bank die Anmeldung ab, steht das Konto auf `zugang_abgelehnt` und der Cron versucht es nicht
  weiter (`accounti fints zugang` nimmt die neue PIN); Konten auf `freigabe_noetig` ruft er
  ebenfalls erst nach `fints freigeben` wieder ab. Das Format (camt/MT940) bleibt fest und
  wechselt nur mit `accounti fints format`; FinTS nur über https.
  Kontoauszüge im Format MT940 und CAMT (camt.052/053/054, .02 und .08) für `import bank`, den
  Datei-Provider und FinTS, mit Saldenprobe. Kreditkarten als eigene Bankkonten mit eigenem
  Sachkonto (`accounti kreditkarte einrichten|liste|uebernehmen|abrechnen|abgleich`): Umsätze aus
  PDF-Abrechnungen oder per Provider, Sammelbelastung auf dem Girokonto gegen die Summe der
  Einzelumsätze — Abweichung ist ein Befund, keine Rundungsbuchung, und bleibt vorläufig, bis ein
  Mensch sie bestätigt (`accounti kreditkarte loesen` löst sie, `--belastung` entscheidet
  „mehrdeutig“); Geldtransit für Karten mit Abruf (der Ausgleich wird nur gegen eine bestätigte
  Sammelbelastung freigegeben). Neuer, optionaler Abschnitt `bank`. Neue Abhängigkeit `fints` 5.0.0 (LGPL-3.0-or-later)
- **FinTS als Zusatzpaket:**  — fints 5.0.0 verlangt lxml < 6.1
  (CVE-2026-41066; accounti ruft den betroffenen Pfad nicht auf); Wechsel auf fints 5.0.1 mit
  lxml ≥ 6.1 ab dem 23.10.2026
- **Steuermeldungen & elektronische Übermittlung** (Baustein 9): Kennziffern der
  Umsatzsteuer-Voranmeldung nach Vordruck 2026 aus den Buchungen (`accounti ustva --period`),
  Plausibilisierung mit Schweregraden (`ustva pruefen`): Buchungen ohne Steuerschlüssel auf
  Erlöskonten und ig. Lieferungen/EU-Leistungen ohne bestätigte USt-IdNr. sperren die Freigabe;
  Freigabe durch den Menschen (`ustva freigeben --von`), gebunden an die Formularwerte;
  ELSTER-Datensatz (UStVA, Dauerfristverlängerung) mit Testmodus ohne Abgabe
  (`ustva uebermitteln --test`), Übermittler-Schnittstelle mit ERiC-Adapter über ctypes und
  Attrappe; Zertifikats-PIN verschlüsselt außerhalb der Datenbank (`elster pin`);
  Übermittlungsprotokoll nur zum Anfügen mit Hash-Kette, Datensatz, Ticket, Zeitpunkt und
  Prüfbericht (`elster protokoll`); Zahllast als offener Posten beim Kreditor „Finanzamt“
  (1780 an Kreditor, fällig zur Frist), Erstattung als Forderung, Berichtigung als
  Differenz und mit dem offenen Posten verrechnet, Nachbuchen mit `elster zahllast`;
  Testmodus beim ersten Lauf; Sondervorauszahlung je Jahr
  (`ustva dauerfrist`); Zusammenfassende Meldung je USt-IdNr. mit CSV für den Portal-Import
  (`accounti zm`); Fristenkalender nach § 108 Abs. 3 AO mit Feiertagen je Bundesland
  (`accounti fristen`); neuer, optionaler Abschnitt `elster`
- **Integrationen & Export, Pakete 1–4** (Baustein 11 ohne REST-API): Marktplatz-Importer für
  Amazon (Abrechnungsbericht Flat File V2 mit Länderdatei), eBay (Transaktionsbericht), PayPal
  (Aktivitäten, als eigenes Konto mit Guthabenkette und Fremdwährungsumrechnung) und Shopify
  (Auszahlungstransaktionen mit Bestellexport); jede Abrechnung wird archiviert, Erlöse je
  Bestellung, Gebühren je Art, Erstattungen und Einbehalte werden einzeln gegen ein
  Verrechnungskonto gebucht, die Summenprobe meldet Abweichungen als Befund, die Auszahlung wird
  exakt gegen den Bankumsatz abgeglichen (`accounti marktplatz import|liste|zeigen|abgleichen`);
  Steuer je Bestimmungsland über `accounti.steuer` (Inland, OSS, ig. Lieferung, Ausfuhr,
  Lieferschwelle aus Vorjahr und laufendem Jahr), Umsatzsteuer der Marktplatzgebühren
  (Amazon mit Vorsteuer), OSS-Quartalsmeldung mit Korrekturen früherer Quartale und ermäßigten
  Sätzen (`accounti marktplatz oss`); Nachträge zu bekannten Abrechnungen; DATEV-Debitoren/Kreditoren
  (EXTF Kategorie 16, Version 5), Belegpaket mit `document.xml` (Version 6.0) und Buchungsstapel
  mit Beleglink (`accounti datev stammdaten|belege`); Kontoauszüge je Finanzkonto, lückenlos
  nummeriert, festgeschrieben mit Hash-Kette, als MT940 mit Saldenverlauf
  (`accounti datev kontoauszuege`). Neuer, optionaler Konfigurationsabschnitt `integrationen`
- **Anlagenbuchhaltung & Jahresabschluss** (Baustein 12): Anlagegüter mit AfA linear
  (monatsgenau, § 7 Abs. 1 Satz 4 EStG), degressiv (2,5-fach/25 % für 2020–2022, 2-fach/20 % für
  04–12/2024, 3-fach/30 % für 07/2025–2027, automatischer Wechsel zur linearen AfA), GWG
  (800 €/410 €/150 € je Anschaffungsjahr), Sammelposten (1/5 je Jahr, einheitliches Wahlrecht),
  digitale Wirtschaftsgüter (BMF 22.02.2022) und E-Fahrzeuge (§ 7 Abs. 2a EStG); Grenzbeträge und
  AfA-Tabelle als Rechtsstand mit Gültigkeitszeiträumen und Quellen; AfA-Lauf je Monat oder Jahr
  als Vorschlag zur Freigabe, Abgang mit Restbuchwert, Erlös und Ergebnis, Anlagenspiegel
  (`accounti anlagen …`). Kassenbuch mit laufender Nummer, Tagessaldo und Kassensturz, das einen
  negativen Bestand ablehnt und nur Stornos statt Änderungen kennt (`accounti kasse …`).
  Jahresabschluss: Kontoauszugssalden und Bank-Saldenabstimmung, Abschlussprüfungen mit Befunden,
  Summen- und Saldenliste, ARAP/PRAP-Vorschläge mit Auflösung in den Folgejahren,
  Einnahmenüberschussrechnung nach Anlage EÜR 2025 und 2026 (Gewerbesteuer als nicht abziehbare
  Betriebsausgabe, Steuern vom Einkommen außerhalb), Eröffnungssalden, Saldovortrag mit
  Jahressperre und Protokoll (`accounti abschluss …`). Neue, optionale Abschnitte `anlagen`,
  `abschluss`, `kasse`
- **Zahlungsverkehr & Mahnwesen** (Baustein 6): `accounti zahlung vorschlag` schlägt offene
  Verbindlichkeiten zum Stichtag vor — Skontofristen vor Nettofälligkeiten, mit Grund je Position
  und Liste der ausgeschlossenen Posten; Zahlungsläufe (`anlegen`, `entfernen`, `pruefen`,
  `freigeben`, `stornieren`) mit Zustandsautomat Entwurf → freigegeben → eingereicht → ausgeführt,
  optionalem Vier-Augen-Prinzip, Freigabe-Hash und Protokoll, das nur wachsen kann; harte Prüfung
  vor Freigabe und Datei: IBAN abweichend vom Stammsatz oder von der Rechnung, Prüfziffer,
  Zahlungssperre, unbestätigter Kontakt, Betrag/Skontofrist, Höchstbetrag, Empfänger im EWR,
  Währung, Namen im SEPA-Zeichensatz, Doppelzahlung (auch per eindeutigem Index und bei
  vorgeschlagenem, noch unbestätigtem Bankumsatz); `accounti zahlung sepa --datei` schreibt die
  SEPA-Sammelüberweisung als `pain.001.001.09` nach DK-TVS GBIC_5 (DFÜ-Abkommen Anlage 3 V3.9/26.11),
  im Test gegen das offizielle Schema geprüft; `zahlung abgleichen` erkennt ausgeführte Läufe,
  sobald `opos zuordnen` die Posten ausgeglichen hat; `zahlung sperre`, `zahlung iban-klaeren`.
  `accounti mahnwesen lauf` mahnt überfällige Forderungen in konfigurierbaren Stufen (Karenz,
  Mindestbetrag, Stufenabstand ab Versand und Fristablauf, Mahnsperre) mit Verzugszinsen nach
  § 288 BGB ab dem Verzugsbeginn nach § 286 BGB (Mahnung, vereinbartes Zahlungsziel oder
  30-Tage-Regel, mit Grund im Schreiben) (Basiszinssatz-Tabelle
  der Bundesbank mit Gültigkeitszeiträumen, Teilzahlungen zeitanteilig), 40-€-Pauschale bei
  Unternehmern mit Anrechnung der Mahngebühren, Mahngebühren nur für Mahnungen im Verzug;
  Mahnschreiben als PDF, Text oder E-Mail
  (`mahnwesen versenden`), Mahnstufe am offenen Posten, Historie (`mahnwesen historie`),
  B2B/B2C-Einstufung (`mahnwesen kunde`). Neue, optionale Abschnitte `zahlung` und `mahnwesen`; die Annahme der Datei durch eine echte Bank ist noch
  nicht geprüft (Bankprobe im Plan)
- **Belegerfassung, Paket 3 – Kanäle E-Mail, Webhook, Connector** (Baustein 2 damit fertig):
  `accounti belege abholen --kanal email` holt die Anhänge neuer Nachrichten aus IMAP-Postfächern
  (TLS mit Zertifikatsprüfung, eigene CA möglich; Ordner nur lesend, `BODY.PEEK[]`; danach
  wahlweise gelesen markieren oder verschieben — nur, wenn alle Anhänge übernommen sind; sonst
  bleibt die Nachricht ungelesen im Posteingang), speichert Absender, Betreff und Message-ID als
  Hinweis (bei weitergeleiteten Rechnungen den ursprünglichen Absender) und merkt sich
  verarbeitete Nachrichten (`accounti kanaele nachrichten`); in den Text eingefügte Fotos von
  Quittungen werden Belege, kleine Logos mit Hinweis übersprungen. Passwörter nur
  per `${UMGEBUNGSVARIABLE}` oder verschlüsselt im Tresor (`accounti kanaele zugang`).
  Tokengeschützter Webhook für Fremdsysteme und Messenger-Weiterleitungen
  (`accounti kanaele webhook token|tokens|widerrufen|starten`, FastAPI): Rohdaten,
  multipart/form-data und JSON mit Base64, Tokens nur als SHA-256 gespeichert, Größe (413) und
  Typ am Inhalt (415) geprüft, bevor etwas gespeichert wird. Connectoren für Belegportale mit
  Registry `BELEG_CONNECTOREN` und generischem JSON/HTTP-Connector (`typ: json`, Seiten,
  Base64-Inhalte, Zugangsdaten nur an den eigenen Host, nur https, abgebrochene Downloads werden
  erneut versucht, mehr Seiten als `max_seiten` sind ein Fehler) — `accounti belege abholen --kanal
  connector`, `accounti kanaele connectoren`. Neuer, optionaler Abschnitt `belegkanaele`; neue
  Tabellen `kanal_nachrichten`, `kanal_nachricht_dateien`, `webhook_tokens`, `kanal_zugaenge`.
  Keine neue Abhängigkeit
- **Aufgaben & Rückfragen** (Baustein 8): Aufgaben mit Bezug auf ein beliebiges Objekt
  (Buchung, Beleg, Umsatz, offener Posten, Kontakt, Bankkonto, eigene Typen anderer Bausteine),
  Zuständigkeit an Benutzer oder Rolle per Regel, unzugewiesen in der gemeinsamen Liste,
  Fälligkeit je Art, Status offen/in_arbeit/wartet/erledigt/hinfaellig und Verlauf, der nur
  wachsen kann. Idempotent über (Art, Objekt) mit eindeutigem Schlüssel — ein wiederholter
  Prüflauf verdoppelt nichts, erledigte Aufgaben bleiben erledigt. Prüfläufe
  `kontierung_pruefen` (Buchung unter der Confidence-Schwelle oder zur Prüfung), `beleg_fehlt`
  (Umsätze ohne Beleg), `beleg_pruefen`, `kontakt_pruefen`, `bank_freigabe`; entfällt der
  Anlass, schließt sich die Aufgabe selbst als `hinfaellig`. Rückfragen und Kommentare am Beleg,
  auch ohne Aufgabe. Erinnerungsstufen mit Eskalation und eine Tagesübersicht je Empfänger statt
  Einzelmails über die Kanäle `email` (SMTP aus `versand`, `Auto-Submitted: auto-generated`)
  und `webhook`. CLI `accounti aufgaben liste|zeige|objekt|zuweisen|status|erledigen|
  kommentieren|rueckfrage|pruefen|erinnern|lauf`; neuer, optionaler Abschnitt `aufgaben`;
  Python-Schnittstelle `melde_aufgabe`, `schliesse_wenn_erledigt`, `gleiche_ab`,
  `registriere_prueflauf` für die Bausteine 7 und 9; deren Prüfläufe, Objekttypen und Kanäle
  in `accounti.<baustein>.aufgaben_anbindung` werden von selbst geladen
- **Live-Bankanbindung, Paket 2 – Provider, Konten, Abruf** (Baustein 5): Bankkonten mit
  Sachkonto und Provider (`accounti bank verbinde|konten`); Zugangsdaten werden mit AES-GCM
  verschlüsselt (Schlüssel aus `ACCOUNTI_SCHLUESSEL`, `accounti bank schluessel`), nie im
  Klartext gespeichert; Provider-Schnittstelle mit Registry und Datei-Provider (Ordner mit
  Kontoauszügen); `accounti bank abrufen` holt neue Umsätze aller Konten ab dem letzten Stand,
  eine Freigabe der Bank wird als Zustand gemeldet; `accounti bank lauf` für Cron: abrufen →
  offene Posten zuordnen → Belege abgleichen → kontieren. Neue Abhängigkeit `cryptography`
  (Apache-2.0/BSD)
- **Live-Bankanbindung & Belegabgleich, Paket 1 – Belegabgleich** (Baustein 5): `accounti bank
  abgleich` führt Bankumsätze mit Quittungen und sonstigen Belegen zusammen, bevor kontiert
  wird — Referenz (Belegnummer im Verwendungszweck), exakt (Betrag, 0–7 Tage, Gegenpartei über
  IBAN oder Namen) und unscharf als Vorschlag (Betrag ohne Namenstreffer, Rundungsdifferenz,
  Trinkgeld); automatisch nur, was auf beiden Seiten eindeutig ist, zwei gleiche Belege werden
  zwei Vorschläge; Gutschriften werden erkannt, Rücklastschriften gemeldet statt abgeglichen;
  `bank vorschlaege|bestaetigen|ablehnen|offen`. `classify` bucht abgeglichene Umsätze aus dem
  Beleg: je Steuersatz, Vorsteuer aus dem Beleg, Sachkonto aus Kontakt oder Regelwerk auf die
  Belegdaten; Trinkgeld/Differenz ohne Steuer zur Prüfung; Ausgabe „davon n mit Beleg“
- **Kreditoren, Debitoren & offene Posten, Paket 3 – USt-IdNr.-Prüfung** (Baustein 4 damit
  fertig): qualifizierte Bestätigungsabfrage beim BZSt über die eVatR-REST-API
  (`accounti kontakte pruefe-ustid`, `--einfach`); jede Abfrage — auch eine gescheiterte —
  steht mit Rohantwort in einem Protokoll, das nur wachsen kann (Hash-Kette, ORM-Sperre,
  SQLite-Trigger, Aufbewahrungsfrist); `accounti kontakte ustid-protokoll` zeigt, prüft und
  exportiert es (`--csv`); `kontakte zeigen` nennt die letzte Prüfung; neuer, optionaler
  Abschnitt `ustid_pruefung` (`max_alter_tage`, `timeout_sekunden`, `url` bzw.
  `ACCOUNTI_EVATR_URL`); Echtabfrage mit den Testwerten des BZSt als Test
  (`ACCOUNTI_EVATR_LIVE=1`)
- **Kreditoren, Debitoren & offene Posten, Paket 2 – Zahlungen** (Baustein 4): `accounti opos
  zuordnen` ordnet Banktransaktionen offenen Posten zu — Referenz (Belegnummer im
  Verwendungszweck), exakt (einziger Posten des Kontakts), unscharf als Vorschlag (Skonto ohne
  Referenz, Sammelzahlung, Teilbetrag, unbekannter Kontakt); Eindeutiges wird sofort
  ausgeglichen: vollständig, Teilzahlung oder Skonto mit anteiliger Vorsteuer- bzw.
  Umsatzsteuerkorrektur (Skontokonten 3736/3731/3730 und 8736/8731/8730, konfigurierbar);
  Überzahlung bleibt als Guthaben auf dem Personenkonto; `opos vorschlaege|bestaetigen|ablehnen`;
  vorgeschlagene Posten sind für andere Zahlungen reserviert
- **Kreditoren, Debitoren & offene Posten, Paket 1** (Baustein 4): Kontakte mit Personenkonten
  (Kreise konfigurierbar im neuen, optionalen Abschnitt `buchhaltung`), Kontakterkennung aus
  Belegen über IBAN → USt-IdNr. → normalisierten Namen, automatische Neuanlage zur Prüfung;
  `accounti opos verbuchen` bucht erfasste Rechnungen gegen Kreditor bzw. Debitor (Sachkonto aus
  Kontakt-Vorschlag oder Regelwerk, Erlöskonto nach Steuerkategorie) und legt offene Posten mit
  Fälligkeit und Skontofrist an; OPOS-Liste und Fälligkeitsstaffel; CLI `kontakte
  liste|zeigen|bestaetigen|bearbeiten`, `opos verbuchen|liste|staffel`; `korrigiere --lernen`
  merkt sich bei Belegbuchungen das Sachkonto am Kontakt; ein Beleg der eigenen Firma (Name oder
  USt-IdNr. aus `mandant`) wird nie als Kreditor gebucht
- **Beleg:** IBAN des Ausstellers wird übernommen (Extraktion und E-Rechnung)

- **E-Rechnung, Paket 3 – ZUGFeRD und Versand** (Baustein 3 damit fertig): Jede ausgestellte
  Rechnung gibt es zusätzlich als ZUGFeRD-PDF (Profil XRECHNUNG, PDF/A-3b) mit lesbarem Layout
  nach DIN 5008 und der XRechnung als Anhang; formale Prüfung mit Mustang/veraPDF; XML und PDF
  werden archiviert. Versand per E-Mail (`accounti rechnung senden`, SMTP mit STARTTLS/SSL,
  Passwort aus Umgebungsvariable), gesendet wird immer die archivierte Datei; jeder Versuch steht
  im Versandprotokoll; `--eml` schreibt die Nachricht nur in eine Datei. Neue Abhängigkeit
  `fpdf2` (LGPL-3.0), Schrift Liberation Sans (SIL OFL) mitgeliefert
- **Prüfwerkzeuge:** `scripts/pruefwerkzeuge_installieren.sh` installiert KoSIT und Mustang mit
  festen Versionen und SHA-256 nach `.pruefwerkzeuge/` (ersetzt `scripts/kosit_installieren.sh`
  und `.kosit/`); `--ohne-formale-pruefung` (alt: `--ohne-kosit`)
- **E-Rechnung, Paket 2 – Ausgang** (Baustein 3): Ausgangsrechnungen als Entwurf schreiben und
  als XRechnung 3.0 (CII) ausstellen; lückenlose Nummernkreise je Gesellschaft und Jahr, auch bei
  parallelen Zugriffen; Steuer ausschließlich über `steuer/` (Inland, Reverse-Charge bei
  EU-B2B-Dienstleistungen, innergemeinschaftliche Lieferung, Ausfuhr, OSS); vor dem Ausstellen
  fachliche Prüfung und formale Prüfung mit dem KoSIT-Prüftool, bei Fehlern Rollback ohne
  verbrauchte Nummer; ausgestellte Rechnung wird archiviert und als Beleg geführt; CLI
  `accounti rechnung neu|position|zeigen|liste|ausstellen` und `rechnung pruefen --kosit`;
  Firmendaten im Abschnitt `mandant` von `config/accounti.yaml`; `scripts/pruefwerkzeuge_installieren.sh`
- **Steuer:** `UStBerechner` unterscheidet Lieferung und sonstige Leistung — EU-B2B-Dienstleistung
  mit USt-IdNr. ist Reverse Charge (`EU_B2B_REVERSE_CHARGE`, USt-VA Kz 21)
- **E-Rechnung Eingang:** Lieferanschrift (BG-15) wird gelesen; neue Regeln BR-IC-12 und
  BR-DE-10/11; OSS-Sätze des Bestimmungslands gelten als plausibel
- **E-Rechnung, Paket 1 – Eingang** (Baustein 3): Zwischenmodell nach EN 16931; Parser für
  XRechnung (UBL Invoice/CreditNote, CII) und ZUGFeRD/Factur-X mit Profilerkennung; fachliche
  Validierung mit Befunden nach Schweregrad (EN-16931-Geschäftsregeln, BR-DE-3/4/15, § 14 UStG,
  Steuersatz zum Land); E-Rechnungen werden in der Beleg-Pipeline ohne OCR übernommen, Fehler
  gehen mit Regel und Befund zur Prüfung; neuer Befehl `accounti rechnung pruefen`; Fixtures
  unter `examples/erechnung/` inklusive einer Auswahl der offiziellen KoSIT-Testsuite
- **Belegerfassung, Paket 2** (Baustein 2): `BelegErkenner` liest Belege beim Eingang —
  PDF-Textebene über `pypdf` (neue Abhängigkeit), OCR steckbar mit lokaler Tesseract-Engine,
  Erkennung von XRechnung/ZUGFeRD (Übernahme folgt mit Baustein 3), Regelwerk-Extraktion mit
  Rechenprobe, Belegart-Regeln, Positionen je Steuersatz, Zerlegung von
  Kreditkartenabrechnungen, optionale maskierte LLM-Stufe (`--llm`); unvollständige Belege gehen
  mit Begründung in die Prüfung; neuer Befehl `accounti belege erkennen`; Textfixtures unter
  `examples/belege/`
- **Belegerfassung, Paket 1** (Baustein 2): Datenmodell `Beleg`, `Belegposition` und
  Eingangsprotokoll `BelegEingang`; Kanäle `ordner` und `upload` über die Registry
  `BELEG_KANAELE`; content-adressiertes, schreibgeschütztes Belegarchiv mit Aufbewahrungsfrist;
  dreistufige Dublettenerkennung; CLI `accounti belege kanaele|import|abholen|liste`;
  `Buchungssatz.beleg_position_id`; Alembic-Migration `add belege`
- Projektstruktur und Datenmodell
- CLI-Grundgerüst (Import, Classify, BWA, Export, Serve)
- Sparkasse CSV-Importer
- Regelwerk-Engine mit Standard-Kontierungsregeln (SKR03)
- DATEV-ASCII-Export (Buchungsstapel EXTF Format 700)
- BWA-Berechnung nach DATEV-Schema Form 01
- SKR03-Kontenrahmen als YAML-Konfiguration
- **Umsatzsteuer-Modul**: Netto/Brutto-Berechnung, Steuerautomatik
- **EU-Steuersätze**: Vollständige DB aller 27 EU-Staaten + UK
- **OSS-Verfahren**: Schwellenwertprüfung, Quartalsmeldung, Länderzuordnung
- **USt-Voranmeldung**: ELSTER-Kennziffern, Zahllast-Berechnung
- **Geschäftsvorfall-Engine**: Inland, EU B2C (OSS), EU B2B (Reverse Charge), Drittland
- Tests für Klassifikation, DATEV-Export, USt, OSS und EU-Steuersätze
- CI-Pipeline (GitHub Actions)
- **`accounti marktplatz zuordnen <Nummer> <Umsatz>`** (Nachprüfung 5 E, M4/N1): ordnet einen
  Bankumsatz ausdrücklich der Aus- oder Einzahlung einer Abrechnung zu, wo der Abgleich nicht
  entscheidet (Bankreferenz, die wie eine Auszahlungsnummer aussieht; mehrere passende
  Umsätze; eine Zuordnung ohne Nummer, die ein späterer Umsatz bezweifelt). Eine bisherige
  Zuordnung des Umsatzes oder der Auszahlung wird dabei gelöst (accountis Bankbuchung
  storniert, `--datum` für einen abgeschlossenen Zeitraum), danach gleicht accounti alles neu
  ab — der frei gewordene Umsatz findet seine Abrechnung. `--loesen` löst nur, und der Abgleich
  nimmt den Umsatz für diese Auszahlung nicht wieder. Ein als Erlös gebuchter Umsatz wird erst
  mit `korrigiere` umgebucht (die Meldung nennt den Befehl); Betrag und Richtung müssen passen,
  ein Umsatz vor dem Abrechnungszeitraum wird abgelehnt, einer nach dem Zeitfenster nur mit
  `--trotzdem` (eine Einzahlung auch davor, Nachprüfung 9 E), einer mit offenem opos- oder
  Beleg-Vorschlag erst nach dessen Ablehnung (Nachprüfung 6 E). Recht „buchen“ wie
  `korrigiere`, Journal (`auszahlung_zugeordnet`/`auszahlung_geloest`, auch für eine
  mitgelöste Zuordnung) mit der handelnden Person, Hinweis
  an der Abrechnung; die Befunde des Abgleichs nennen den Befehl mit der Umsatz-ID

### Geändert

- **Oberfläche:** Alle Seiten aus 10a und 10b (Anmeldung, Übersicht, Freigaben, Prüfen,
  Buchung, Beleg) im neuen Design, fachlich unverändert. Die Sprachwahl zieht von der
  Kopfleiste nach „Mein Konto“ (`POST /konto/vorlieben`); `POST /einstellungen/sprache`
  antwortet ein Release lang mit 308. „Freigaben“ steht in der Navigation nur noch mit dem
  Recht, Zahlungsläufe oder Steuermeldungen freizugeben (die Seite bleibt für alle lesbar). Das
  Codefeld bei Anmeldung, Freigaben und Storno öffnet auf dem Handy die Zifferntastatur;
  „Wiederherstellungscode verwenden“ schaltet auf ein Textfeld um (ohne JavaScript). Die
  Abschaltung der Tastenkürzel liegt am Benutzer statt im Browser (`localStorage`) – wer sie
  abgeschaltet hatte, schaltet sie einmal unter „Mein Konto“ wieder ab. `pruefen.css` entfällt.
- **Die Regeldatei wird streng geprüft** (Baustein 10b, Teil 1): Ein Eintrag mit einem Feld,
  das der Lader nicht kennt (auch ein Zusatzfeld wie `kommentar:` oder `aktiv:`), einem
  unbekannten Steuerschlüssel, einer Kontonummer außerhalb von 4–9 Ziffern oder einer
  YAML-Zahlform wie `0x1340` hält die **ganze Regeldatei** an — `classify`, `bank lauf`
  (samt Bankabruf), `opos verbuchen` und der REST-Lauf (409) melden den Fehler mit Datei,
  Regel und Schlüssel, bis er berichtigt ist; bisher wurde ein solches Feld still ignoriert.
  Bestandsdateien vor dem Update durchsehen (Kommentare hinter `#`), siehe
  [docs/betrieb.md](docs/betrieb.md), „Upgrades“.
- `accounti korrigiere --lernen` **und `accounti lerne`** speichern die Regel in der Datenbank
  der Gesellschaft (Tabelle `kontierungsregeln`, mit Journal) statt sie an die Regeldatei
  anzuhängen; accounti schreibt die Regeldatei nicht mehr. Gelernte Regeln haben Vorrang vor der
  Regeldatei und den Standardregeln; aus einer Korrektur gelernte gelten nur in der
  Zahlungsrichtung ihres Quellumsatzes, `lerne` ohne `--richtung` in beide. `korrigiere
  --lernen`, `lerne` und `regeln uebernehmen` verlangen mit eingerichteten Benutzern die Rechte
  `buchen` und `regeln_lernen` (ein Einmalcode), `regeln deaktivieren` nur `regeln_lernen`.
  `korrigiere --lernen` schlägt als Muster den ganzen Namen der Gegenpartei ohne Rechtsform vor
  (bisher das erste Wort; Rechtsformen wie „Co“ oder „AB“ kürzen nicht auf ein einzelnes Wort),
  lernt nur aus Kontierungsvorschlägen (Altbuchungen ohne gespeicherte Herkunft weiterhin, aber
  nicht aus dem Kassenbuch) und speichert ein Muster, das andere Gegenparteien oder jeden Kauf
  über einen Zahlungsdienst träfe, nur mit `--trotz-warnung` — ebenso jede Regel aus einem
  Umsatz ohne Namen der Gegenpartei (das Muster stammt dann aus dem Verwendungszweck). Früher
  gelernte `gelernt_*`-Einträge übernimmt `accounti regeln uebernehmen` — mit der Richtung
  ihrer Bankseite.
- `accounti korrigiere` (und die Korrektur im Browser) behält das Finanzkonto eines
  Bankumsatzes auf der Seite seiner Zahlungsrichtung (Ausgabe im Haben, Einnahme im Soll):
  „4930 an 4980“, „4930 an 1000“ (Kasse) oder ein nicht eingerichtetes Bankkonto für einen
  Umsatz auf 1200 wird abgelehnt — der Kontostand der Bücher passte sonst nicht mehr zum
  Kontoauszug. Ein falsch zugeordnetes Finanzkonto (etwa `import bank` ohne `--konto`) lässt
  sich auf ein anderes eingerichtetes Bankkonto umbuchen — mit Warnung und ohne Regel.
- `accounti bestaetige` (und Freigeben im Browser) prüft die Prüfregel
  `steuerschluessel_konto` wie eine Korrektur: Meldet sie einen Fehler (Vorsteuer auf einer
  Privatentnahme, Automatikkonto ohne Schlüssel), wird nicht freigegeben.
- Regeln in der Regeldatei dürfen ein optionales Feld `richtung: ausgabe|einnahme` tragen; ohne
  Angabe gelten sie wie bisher in beide Richtungen.
- `accounti classify`, `bank lauf` und `opos verbuchen` nehmen zur Regeldatei der Gesellschaft die
  gelernten Regeln aus der Datenbank hinzu — wie die REST-Läufe; das Regelwerk wird erst nach der
  Laufsperre geladen.
- `accounti review` zeigt die Begründung und zurückgestellte Buchungen; `bestaetige` und
  `korrigiere` schließen eine offene Rückfrage und die Aufgabe `kontierung_pruefen` zur Buchung.
- `accounti korrigiere` und `buchung storniere` nutzen den Kontenrahmen samt
  `abschluss.kontenzuordnung` — wie Summen- und Saldenliste und Abschluss.
- Die Verfahrensdokumentation nennt die Regeldatei der Gesellschaft und die gelernten Regeln; der
  Aufbewahrungsbericht führt Kontierungsgründe und -regeln.
- Die Seiten aus Baustein 10a sind übersetzbar; das Layout trägt Sprachauswahl und HTMX; die
  Einmalcode-Prüfung des Browsers liegt in `api/einmalcode.py`.
- **Freigegebene Buchungen sind unveränderbar** (Baustein 7): Ab `auto`, `geprueft`,
  `korrigiert`, `exportiert` lehnt die Datenbankschicht jede Änderung außer
  `auto → geprueft`, `→ exportiert` und dem einmaligen Stornovermerk ab, Löschen immer;
  `accounti korrigiere` erzeugt dann Storno und Neubuchung (mit `--datum`, wenn der Zeitraum
  abgeschlossen ist). Ändert sich das Sachkonto einer Buchung mit Steuerschlüssel, verlangt
  `korrigiere` `--steuer` oder `--ohne-steuer` (früher fiel der Schlüssel still weg);
  `bestaetige` und `korrigiere` nehmen ohne `--von` `ACCOUNTI_BENUTZER` bzw. den
  Anmeldenamen. `export datev` und `datev belege` vermerken exportierte Buchungen als
  `exportiert` und schreiben den Export ins Journal; auf DATEV-Automatikkonten bleibt der
  passende Steuerschlüssel weg, eine Buchung ohne Steuer trägt BU 40 (Aufhebung der
  Automatik), ein Storno-Paar in Belegfeld 2 den Bezug zum Original. Massenänderungen über
  die Sitzung (ORM, Core, `bulk_*`) auf Buchungen und Journal sind gesperrt. Die
  Jahressperre nimmt den Stornovermerk an; Sammelläufe (`classify`, `opos zuordnen`,
  `bank abgleich`) überspringen festgeschriebene Monate. Ein reines Storno macht den
  Bankumsatz wieder offen. SQLite wartet bis zu 30 s auf die Schreibsperre (busy timeout)
- **Rollen in den Befehlen von Baustein 7** (Verzahnung mit Baustein 10a): Mit
  eingerichteten Benutzern verlangen — jeweils mit Einmalcode — das Recht zu buchen
  (`buchhalter`): `korrigiere`, `buchung storniere`, `kasse buchen|anfangsbestand|storno`,
  `abschluss eroeffnung`, `bank bestaetigen|ablehnen`, `nachfordern anfrage --senden`;
  Buchungen freizugeben (`buchhalter`, `freigeber`): `bestaetige`, `opos
  bestaetigen|ablehnen`, `abschluss bestaetigen|ablehnen`, `periode schliessen`, `abschluss
  vortrag`, `export datev`, `datev belege`; Steuermeldungen freizugeben (`freigeber`):
  `periode oeffnen`, `abschluss oeffnen` (Funktionstrennung; beim Öffnen nennt accounti
  schon freigegebene oder abgegebene Voranmeldungen des Zeitraums); verwalten
  (`verwalter`): `journal uebernehmen`. `geprueft_von`, Protokolle und Journal nennen den
  Benutzer statt eines Freitexts aus `--von`; Personen ohne Rechteprüfung (Läufe, Importe)
  stehen als „… (ungeprüft)“ im Journal, API-Token als „API-Token <Name>“. Die
  Verfahrensdokumentation beschreibt Benutzer, Rollen, Rechte, Einmalcode und
  Freigabewege (`models.auth.FREIGABEWEGE`), die Datensicherung, `betrieb lauf` und die
  Laufsperre. `abschluss eroeffnung|bestaetigen|ablehnen` nehmen ohne `--von`
  `ACCOUNTI_BENUTZER` bzw. den Anmeldenamen (früher „supervisor“). Ohne Benutzer prüft
  accounti weiterhin keine Rollen
- **Zahlungsverkehr in der Rechteprüfung:** Mit eingerichteten Benutzern verlangt `zahlung
  sepa` (die SEPA-Datei ist der Zahlungsauftrag) das Recht zur Zahlungsfreigabe, `zahlung
  abgleichen` das Recht zu buchen — jeweils mit Einmalcode. Die 10a-Befehle (`zahlung …`,
  `anlagen freigeben`, `ustva …`) und die Freigaben im Browser schreiben den Benutzer
  geprüft ins Journal; eine Person, die ein Vorgang ohne Rechteprüfung selbst mitbringt
  (`--von`), steht dort als „(ungeprüft)“. `opos bestaetigen` setzt `geprueft_von`, die
  Entscheidung über einen Belegabgleich steht im Journal (`abgleich_bestaetigt`,
  `abgleich_abgelehnt`). `anlagen freigeben` nimmt ohne `--von` `ACCOUNTI_BENUTZER` bzw. den
  Anmeldenamen (früher „supervisor“)
- **`journal uebernehmen` nur auf dem Upgrade-Weg:** solange das Journal außer Übernahmen
  leer ist; danach lehnt accounti ab (was dann ohne Eintrag ist, entstand an accounti
  vorbei), und `journal pruefen` meldet jede spätere Übernahme
- **Schreibsperre und Lesestand:** Die Schreibsperre holt nur ein Flush mit Journal- oder
  Sperrbezug (unter PostgreSQL warteten sonst Anmeldungen und Uploads auf jede
  Buchungstransaktion), `fints freigeben` schreibt je Konto fest (keine offene
  Transaktion während der TAN-Abfrage), `bank lauf` ebenso den Abruf; unter PostgreSQL holt
  jede Transaktion, die bestehende Zeilen ändert, die Schreibsperre zuerst (keine
  Deadlocks durch umgekehrte Sperrreihenfolge); `journal pruefen` liest unter PostgreSQL
  aus einem Schnappschuss (`REPEATABLE READ READ ONLY`), hält niemanden auf und lässt die
  Sitzung danach schreibbar; ein gleichzeitiges zweites Storno derselben Buchung endet mit
  einer Meldung statt einem Traceback; ein Journaleintrag, dessen Vorher/Nachher kein
  JSON-Objekt ist, ist ein Befund statt eines Absturzes; der Befund „ohne Eintrag“ empfiehlt
  `journal uebernehmen` nur, solange es noch geht
- **Kontenrahmen-Datei im Paket:** `config/skr03.yaml` liegt jetzt als
  `accounti/pruefung/skr03.yaml` im Paket (Prüfregel und DATEV-Export unabhängig vom
  Arbeitsverzeichnis); eine eigene Datei nennt `pruefung.kontenrahmen_datei`
- **Laufsperre für weitere Sammelläufe:** `opos verbuchen` und `periode schliessen` halten
  die Sperre der Bankkette (`bank`), `nachfordern` die von `aufgaben lauf` — ein zweiter
  Lauf endet mit Exit 1 statt doppelt zu buchen bzw. während eines Buchungslaufs
  festzuschreiben; `journal uebernehmen` holt die Schreibsperre, bevor es liest
- **Sicherung vor einer Migration:** `sicherung erstellen` liest nur Spalten, die es in der
  Datenbank gibt — eine Datenbank vor `alembic upgrade` lässt sich mit dem neuen Code sichern
  (Upgrade-Reihenfolge in `docs/betrieb.md`), fehlende Spalten bleiben beim Zurückspielen
  leer. Journal und Buchungskorrekturen kommen samt SQLite-Triggern zurück, `journal pruefen`
  ist danach in Ordnung
- **Aufbewahrung:** `accounti betrieb aufbewahrung` zählt Journal, Buchungskorrekturen und
  Monatsabschlüsse als Bücher (10 Jahre); ein spät festgeschriebener Monat verschiebt den
  Fristbeginn der Bücher seines Wirtschaftsjahres, ein wieder geöffneter Monat eines nicht
  abgeschlossenen Jahres läuft nicht ab
- `accounti zahlung freigeben`, `accounti ustva freigeben` und `accounti ustva dauerfrist
  --freigeben` verlangen, sobald Benutzer eingerichtet sind, die Rolle `freigeber` und den
  Einmalcode der handelnden Person; ohne Benutzer unverändert.
- `accounti serve` startet die Web-Oberfläche und REST-API (bisher ein Platzhalter) und liest
  `--db`, `--archiv`, `--config` sowie den Abschnitt `server`.
- `alembic/env.py` nimmt die Datenbank aus `ACCOUNTI_DB`, wenn gesetzt.
- Mit eingerichteten Benutzern brauchen auch `accounti zahlung anlegen`, `iban-klaeren`,
  `entfernen`, `sperre` (Recht buchen) und `stornieren` (Recht Zahlungsfreigabe) sowie
  `accounti anlagen freigeben` Rolle und Einmalcode; ins Protokoll kommt der angemeldete Benutzer
  statt `--von`. Wer einen Zahlungslauf anlegt, gibt ihn in der CLI nicht selbst frei.
- `classify`, `bank lauf`, `bank abrufen`, `bank abgleich`, `opos zuordnen`,
  `kreditkarte abgleich` und `fints freigeben` halten eine Laufsperre je Gesellschaft; ein
  zweiter gleichzeitiger Lauf endet mit Exit 1 statt doppelt zu kontieren.
- `classify`, `bank lauf`, `opos verbuchen`, `lerne` und `korrigiere --lernen` nutzen die
  Regeldatei der Gesellschaft (`regeln:` in der Registry) statt immer `config/regeln.yaml`.
- Neu abgelegte Belegdateien bekommen eine bereinigte Endung.
- **Dublettenschutz** über die Bankreferenz (camt `AcctSvcrRef`, MT940 `//Referenz`), wo
  vorhanden: derselbe Umsatz aus zwei Dateien eines Abrufs oder aus camt.053 und camt.054 bleibt
  einer. Ohne Referenz zählt die laufende Nummer gleicher Umsätze je Auszug bzw. Datei statt je
  Abruf: derselbe Umsatz aus Tages- und Monatsauszug bleibt einer
- **Datei-Provider** liest neben CSV auch MT940 und CAMT, überspringt Auszüge fremder Konten,
  liest doppelte Dateien und Auszüge nur einmal und meldet den Saldo
- **`bank lauf`** gleicht vor den offenen Posten die Kreditkarten ab und nennt das Ergebnis
- **`import bank`** übernimmt bei MT940/CAMT nur die Auszüge des Kontos aus `--konto` und lehnt
  Dateien mehrerer Konten ohne `--konto` ab; ein Konto ohne IBAN (Kreditkarte) nimmt keine
  Auszüge eines Bankkontos (IBAN, BLZ/Kontonummer) an
- **Provider-Schnittstelle:** Rückfrage für Freigaben (`freigabe`), aktualisierte Zugänge
  (`Abruf.zugang`, `FreigabeNoetigError.zugang`) werden neu verschlüsselt
- **Kontoauszüge** im Datei-Provider: Dateien mit `.txt`/`.xml` werden nur übernommen, wenn sie
  MT940 oder CAMT enthalten
- `steuer/voranmeldung.py` bildet den amtlichen Vordruck 2026 ab: alle Kennziffern mit Zeile,
  Bemessungsgrundlagen in vollen Euro, Steuer zu Kz 81/86/89/93 wie ELSTER aus der
  Bemessungsgrundlage, Kz 83 als Ergebnis; § 13b getrennt in 46/47, 73/74 und 84/85;
  ig. Erwerb 7 % (Kz 93)
- OSS-Umsätze erscheinen in der Voranmeldung als Nettoumsatz in Kz 45 (vorher: gar nicht)
- DATEV-Exporte mit Beleglink schreiben Belegfeld 1 nur noch mit den von DATEV zugelassenen
  Zeichen (Befund bei Kürzung)
- Buchungen in einem abgeschlossenen Jahr lassen sich nicht mehr anlegen, ändern oder löschen
  (`JahrGesperrtError`); `accounti abschluss oeffnen` hebt die Sperre mit Begründung und Protokoll
  auf. `classify`, `opos zuordnen` und `bank abgleich` lassen Umsätze in abgeschlossenen Jahren
  aus; `opos verbuchen` lässt Rechnungen mit Belegdatum in einem abgeschlossenen Jahr liegen und
  meldet sie unter „Nicht verbucht“, statt den ganzen Lauf abzubrechen
- Offene Posten tragen jetzt ihre Mahnstufe aus dem Mahnwesen (Feld gab es schon, es wurde bisher
  nie gesetzt)
- `accounti belege abholen` kennt `--kanal email|connector`, `--quelle` und `--config`; ein
  unbekannter Kanal nennt alle abholbaren Kanäle, `--kanal webhook` verweist auf
  `accounti kanaele webhook starten`. Bei `email|connector` gilt `mandant` (Name, USt-IdNr.) aus
  der Konfiguration als Vorgabe für `--eigene-firma`/`--eigene-ust-id`
- **Umsätze mehrerer Bankkonten** werden gegen das Sachkonto ihres Kontos gebucht (Kontierung,
  Ausgleich offener Posten, Kontierung mit Beleg) statt pauschal gegen `buchhaltung.bank_konto`
- **`classify`** kontiert über den neuen Kontierungslauf: abgeglichene Umsätze aus dem Beleg,
  Umsätze mit offenem Beleg-Vorschlag bleiben liegen; neue Option `--config`; `opos zuordnen`
  lässt Umsätze mit Beleg-Abgleich in Ruhe
- **Steuerfreie EU-Rechnungen nur mit bestätigter USt-IdNr.:** `rechnung ausstellen` fragt bei
  Kategorie K (innergemeinschaftliche Lieferung) und AE (Reverse Charge) beim BZSt an, wenn
  keine aktuelle Bestätigung vorliegt, und stellt bei ungültiger Nummer oder abweichendem
  Namen/Ort nicht aus (die Nummer bleibt frei); `opos verbuchen` bucht solche Erlöse ohne
  Bestätigung nur zur Prüfung und nennt den Grund
- **CI:** `actions/checkout` und `actions/setup-python` auf v7 (Node 24); Tesseract mit deutschen
  Sprachdaten wird installiert, damit die echten OCR-Tests laufen
- **Belegerkennung:** OCR-Text wird normalisiert (`19 $`, `7°/o` → `%`); hinter einem Betrags-Label
  zählt der erste Betrag; Brutto wird auch in Zeilen mit Netto-Angabe gefunden. Neues Fixture
  `examples/belege/quittung_tankstelle_scan.jpg` für einen echten OCR-Durchlauf
- **Bauplan von 5 auf 12 Bausteine erweitert** — neue Übersicht in [`docs/bauplan.md`](docs/bauplan.md),
  je ein Spec unter `docs/specs/` für die Bausteine 2 bis 12. Neu aufgenommen: Belegerfassung mit
  OCR, E-Rechnung (Eingang und Ausgang), Kreditoren/Debitoren mit offenen Posten,
  Live-Bankanbindung mit Belegabgleich, Zahlungsverkehr und Mahnwesen, Belegvollständigkeits- und
  Ordnungsmäßigkeitsprüfung mit unveränderbarem Journal, Aufgaben und Rückfragen, elektronische
  Übermittlung der Steuermeldungen, Benutzer/Rollen/2FA, vollständige DATEV-Übergabe sowie
  Anlagenbuchhaltung und Jahresabschluss.
- README: Feature-Übersicht nach Bereichen gegliedert und um den Ist-Stand ergänzt; Roadmap folgt
  jetzt den Bausteinen; Positionierung präzisiert (Buchhaltung im eigenen Haus, keine
  Mandantenbetreuung für Dritte).
- `docs/architektur.md`: neue Module beschrieben, Designprinzipien um Unveränderbarkeit und
  Belegbezug erweitert, Datenmodell und Erweiterungspunkte ergänzt.

### Behoben

- **Protokoll:** `httpx2` und `httpcore2` (kommen mit openai 2.x über litellm) schreiben keine
  Adressen mehr auf INFO ins Protokoll; gedämpft waren nur `httpx`, `httpcore` und `urllib3`.
- **Oberfläche:** Die Prüfliste scrollt auf dem Handy nicht mehr waagrecht (Tabellen werden
  unter 64rem zu Karten, darüber scrollt eine zu breite Tabelle in ihrem Rahmen statt
  abgeschnitten zu werden); im Dunkelmodus bleiben Felder und Knöpfe nicht mehr weiß
  (`color-scheme`), `<kbd>` ist lesbar; das Einmalcode-Feld hat ein sichtbares Label; Label und
  Wert in Angabenlisten überlappen nicht mehr; die Hauptaktion ist als primärer Knopf
  erkennbar; die Kopfleiste ist auf dem Handy höchstens 56 px hoch.
- **OSS und Marktplatz: Nachprüfung 9 E** (Runde 10, N1–N4, N9-1, N9-2): Ein Länderkonto des
  Kontenrahmens (im SKR04 auch 8320–8327) lässt sich in `integrationen.oss_erloes_konten`
  keinem anderen Land und in `oss_erloes_ermaessigt` gar nicht mehr geben — OPOS bucht eigene
  Rechnungen dort, die OSS-Meldung nahm das Land aus der Einstellung (`{DK: "8327", BE: null}`:
  BE-Rechnung als DK 25 %; AT und IT vertauscht; IT 22 % als FR 5,5 %); das Laden lehnt ab und
  rät zu einem anderen Konto (z. B. 8328) und zum Umbuchen. `LAND: null` nimmt ein Land nur für
  den Marktplatz heraus, das Konto bleibt das Konto seines Lands. Eine Erstattung im
  Folgequartal auf einem anderen Konto desselben Lands (SKR04 8320 → 4320) berichtigt das
  Ursprungsquartal statt das laufende zu mindern (je Land und Satzart). Die Beispielkonfiguration setzt Kursdifferenz-
  und OSS-Steuerkonto nicht mehr fest (auf SKR04 gestellt gingen Kursdifferenzen still auf die
  Privatkonten 2150/2660). `marktplatz zuordnen --trotzdem` nimmt eine Einzahlung auch vor dem
  Zeitfenster (die Bank bucht die Überweisung zuerst; die Meldung sprach von einer Auszahlung),
  eine Auszahlung davor weiter nie. Der Hinweis `auszahlung_rechnung` nennt eine schon bezahlte
  Rechnung nicht mehr „offen“ und sagt, dass opos den Umsatz dann nicht bucht
- **SKR04: OSS-Umsatzsteuer im Bankbereich** (Merge Paket E mit main nach #36; g3w-fach/
  g3w-merge N1): Eigene Rechnungen (OPOS) buchten die Steuer eines OSS-Fernverkaufs im SKR04
  auf 177720/1779 bzw. 1767 — dort Bank- und Zahlungsmittelbereich (1700–1889). `abschluss
  pruefen` meldete „Bankkonto … nicht eingerichtet“ und sperrte den Abschluss, die Zahlung an
  das BZSt ließ sich nicht als Regel lernen („beide Geldkonten“). Jetzt DATEV SKR04 3817
  „Umsatzsteuer aus im anderen EU-Land steuerpflichtigen Lieferungen“ (Gegenstück zu SKR03
  1767, Steuerkonto, Anlage EÜR Zeile 140), wie beim Marktplatz-Import; der Steuerabgleich
  der OSS-Meldung nimmt ohne Einstellungen das Konto des Kontenrahmens. Schon auf 1777xx
  gebuchte OSS-Steuer auf das Sammelkonto umbuchen (SKR04 3817, SKR03 1767).
- **EU-Steuersätze veraltet** (Gesamttest Steuer B8): Die Tabelle führt je Land Stände mit
  `gueltig_ab`; maßgeblich ist der Satz am Tag der Leistung (Art. 63, 93 MwStSystRL).
  Berichtigt: Rumänien 21/11 % ab 01.08.2025 (vorher 19 % — OSS-Buchung und -Meldung nach
  RO waren falsch), Estland 24/13/9 %, Finnland 25,5/13,5/10 % ab 01.01.2026, Slowakei
  23/19/5 % ab 01.01.2025, Litauen 21/12/5 % ab 01.01.2026, Malta mit 12 %, Luxemburg mit
  Parksatz 14 %, Bulgarien in Euro ab 01.01.2026. Ändert ein Land den Satz im Quartal, hat
  die OSS-Meldung zwei Zeilen; Korrekturen früherer Quartale rechnen mit dem Satz des
  Ursprungsumsatzes. Die Doku versprach eine Überschreibung per `config/eu_steuersaetze.yaml`,
  die es nie gab — die Aussage ist entfernt
- **`export datev` ohne Zeitraum und mit festem Kopf 2026** (Gesamttest Abschluss B1/B2,
  Betrieb B6, Eingang B11): `--period JJJJ-MM` (wie im README und bei `datev belege`), Kopf
  mit Wirtschaftsjahr aus `datev.wirtschaftsjahr_beginn` und dem Zeitraum der Buchungen; ein
  Stapel über die Grenze des Wirtschaftsjahrs wird abgelehnt (DATEV läse das Belegdatum TTMM
  im falschen Jahr). Schon exportierte Buchungen — auch solche in festgeschriebenen Monaten,
  die den Status nicht mehr wechseln, und ungeprüfte, die mit `--alle` im Stapel waren (sie
  stehen als `ungeprueft` im Journal) — kommen nur mit `--erneut` noch einmal; `korrigiere`
  warnt, wenn ein solcher Vorschlag danach noch geändert wird (in DATEV steht das alte Konto),
  nennt jeden Stapel, der laut Journal Buchungen des Monats übergab, und den Ersatz mit
  `--erneut --alle` (ohne `--alle` fehlten dem neuen Stapel die übrigen ungeprüften Vorschläge,
  wer ihn in DATEV ersetzte, verlöre sie; nannte sie nur den letzten Stapel der Buchung, stand
  nach dessen Ersatz der Rest des Monats in DATEV doppelt) und sagt, wenn ein alter Stapel
  nicht genau den Monat umfasste.
  Ein weiterer Export desselben Zeitraums schreibt eine eigene Datei (`…_2.csv`, `…_3.csv`) und
  überschreibt nie einen früheren Stapel (vorher war der erste weg, der SHA-256 im Journal
  verwies ins Leere); die Nummer zählt auch die Stapel, die laut Journal schon übergeben und
  aus dem Ordner geräumt sind (sonst trugen zwei Stapel denselben Namen).
  `--berater`/`--mandant` fallen auf `datev.berater_nummer`/`mandanten_nummer` zurück. Der
  Stapel entsteht aus denselben Bausteinen wie `datev belege`: 31 Kopffelder, Herkunft „RE“,
  Buchungstyp 1, Textfelder maskiert (ein `"` oder `;` im Buchungstext verschob Felder),
  Belegfeld 1 im DATEV-Zeichenvorrat, Kostenstelle in KOST1 (Feld 37 statt Beleginfo);
  Konten, die nicht zur Sachkontenlänge passen (z. B. 177721 bei Länge 4), meldet er als
  Warnung, ebenso ein Personenkonto, das kürzer ist als Sachkontenlänge + 1 (DATEV läse es als
  Sachkonto); ein Konto, das in kein DATEV-Kontofeld passt (10 Stellen), hält den Export an
- **OSS-Konten fest verdrahtet, sechsstellige Steuerkonten** (Gesamttest Steuer B6/B7):
  `integrationen.oss_erloes_konten` ordnet jedem EU-Land ein Erlöskonto zu (Vorgabe wie bisher
  acht Länder, SKR04 4320–4327; `LAND: null` nimmt eines nur für den Marktplatz heraus, das
  Konto bleibt das Konto seines Lands; ein Konto für zwei Länder ist ein Konfigurationsfehler);
  ein Dänemark-Verkauf landete ohne Ausweg auf 8200/1779. Eigene OSS-Erlöskonten (auch
  `oss_erloes_ermaessigt`, z. B. 8328) zählen in der Voranmeldung zu Kz 45 statt die Freigabe
  zu sperren. Die OSS-Umsatzsteuer geht auf das DATEV-Sammelkonto 1767 (SKR04
  3817, `oss_ust_konto`, je Land `oss_ust_konten`) statt auf 177720–177725, die der Stapel mit
  Sachkontenlänge 4 nicht annahm; sie erscheint nicht als „Steuerkonto ohne Kennziffer“ in der
  Voranmeldung. Schon auf 1777xx gebuchte OSS-Steuer auf das Sammelkonto umbuchen (SKR04 3817,
  SKR03 1767), nicht in `oss_ust_konten` einstellen: im SKR04 liegen 1777xx im Bankbereich, im
  SKR03 bucht der Marktplatz neue OSS-Steuer dann wieder sechsstellig.
  OSS-Meldung, Lieferschwelle und Kz 45 lesen die Länderkonten des Kontenrahmens (OPOS, im SKR04
  auch 8320–8327) und die eingestellten `oss_erloes_konten`; die Richtungsprüfung einer
  Korrektur kennt dieselben OSS-Konten wie die Voranmeldung
- **Korrektur nach Abgabe der Voranmeldung ohne Befund** (Gesamttest Steuer B5, Eingang B13,
  Ausgang): `storniere`/`korrigiere` warnen, wenn die Voranmeldung des Zeitraums schon
  abgegeben oder freigegeben ist; der Hinweis beim Storno in einen anderen Monat unterscheidet
  § 17 UStG (Berichtigung im Zeitraum der Änderung) von der Fehlbuchung (Monat öffnen, dort
  stornieren — sonst wirkt die Korrektur doppelt) und verlangt nicht zugleich eine berichtigte
  Anmeldung für den Monat des Originals, den das Storno nicht ändert. `ustva` meldet
  `abgegeben_abweichend`, wenn die Buchungen nicht mehr zur abgegebenen Anmeldung passen
  (§ 153 Abs. 1 AO), und die Prüfregel `abgegeben_abweichend` (`accounti pruefen`) findet
  Buchungen, die laut Journal nach der Abgabe in ihren Zeitraum kamen. Die Plausibilisierung
  bezieht die Prüfregeln aus Baustein 7 über den Zeitraum ein (deren Fehler als Warnung) — der
  Hinweis „Baustein 7 nicht angeschlossen“ ist weg. Nach der echten Abgabe bietet
  `ustva uebermitteln` das Festschreiben an (GoBD Rz. 108–110, nicht erzwungen). Eine
  Saldenvortragsbuchung auf ein Steuerkonto (EB 1576 an 9000) ist kein Umsatz und keine
  Warnung mehr wert
- **Voranmeldung für einen laufenden Zeitraum** (Gesamttest Steuer B10): ein noch nicht
  abgelaufener Zeitraum ist ein Fehler — keine Freigabe, keine Abgabe (§ 18 Abs. 1 UStG); im
  Testmodus eine Warnung, und `uebermitteln --test` sagt dann, ab wann freigegeben werden kann,
  statt „Freigabe möglich“
- **Marktplatz-Auszahlungen als Erlös gebucht** (Gesamttest Steuer B2, Teil Abgleich): `bank lauf`
  (auch über REST) gleicht Auszahlungen importierter Abrechnungen vor dem Kontieren ab und bucht
  sie „Bank an Verrechnungskonto“; in Fremdwährung gilt ein Bankumsatz mit Stichwort oder
  Abrechnungsnummer innerhalb von `integrationen.auszahlung_toleranz_prozent` (Vorgabe 2 %) als
  Treffer — gebucht wird der Bankbetrag, die Differenz auf `kursdifferenz_aufwand`/`_ertrag`
  (SKR03 2150/2660, SKR04 6880/4840), mit Hinweis an der Abrechnung (vorher kam ein Treffer bei
  Fremdwährung praktisch nie zustande, und die Regel buchte die Auszahlung als Erlös 19 %).
  Offene Fehler-Befunde einer Abrechnung stehen als Warnung in der Voranmeldung ihres
  Zeitraums — eine schon als Erlös gebuchte Auszahlung in der Voranmeldung des Monats der
  Bankbuchung, wo der Erlös doppelt steht (Abrechnung 16.–31.08., Auszahlung 03.09.: UStVA 09);
  in Fremdwährung erkennt der Abgleich sie innerhalb derselben Toleranz wie einen Treffer
  (vorher nur bei exakt gleichem Betrag, Kz 81 blieb still doppelt) — nicht aber den Umsatz,
  den accounti schon einer anderen Auszahlung zugeordnet hat, und keine Geldbewegung (nur Bank,
  Verrechnungs-, Geldtransit- und Kursdifferenzkonten): sonst traf die Toleranz den Umsatz der
  vorigen Auszahlung (eBay 30.09. statt 02.10.), der Befund nannte die richtige Buchung, warnte
  in der UStVA 09 statt 10, und solange der eigene Umsatz fehlte, stand ein falscher Fehler.
  Nach der vorgeschlagenen Korrektur (`korrigiere … --soll 1200 --haben 1361 --ohne-steuer`)
  ordnet der nächste Abgleich den Umsatz zu und erledigt den Befund, statt einen zweiten
  anzulegen; in Fremdwährung bucht er die Kursdifferenz vom Verrechnungskonto um (vorher blieb
  die Abrechnung „abweichung“ und die Voranmeldung warnte dauerhaft). Ein Umsatz, dessen
  Verwendungszweck die Nummer einer anderen bekannten Abrechnung desselben Marktplatzes nennt
  (auch einer aus demselben Bericht), ist weder Treffer noch „schon gebucht“; unter mehreren
  entscheidet die eigene Nummer — vorher nahm „schon gebucht“ (und nach der Korrektur der
  Treffer mit Toleranz) den zuerst importierten Umsatz: bucht `bank lauf` zwei eBay-Auszahlungen
  per Regel als Erlös, bevor der Transaktionsbericht kommt, nannten beide Befunde denselben Tag,
  die Voranmeldung des anderen Monats warnte nicht, und die Korrektur ordnete den Umsatz der
  falschen Auszahlung zu (Kursdifferenz 0,41 € statt 0,02 €). Nennt ein Umsatz im Zeitfenster
  die eigene Nummer, zählt nur er, auch ein schon per Regel gebuchter — kein anderer wird
  Treffer, weder mit Toleranz noch mit exaktem Betrag: vorher nahm eine einzeln importierte
  Abrechnung per Toleranz den offenen Umsatz einer noch nicht importierten (0,41 €), während
  ihr eigener als Erlös gebucht dastand; die andere fand danach keinen Umsatz und keinen
  Befund mehr, die Voranmeldung schwieg bei doppeltem Erlös. Nennt ein Umsatz statt der
  eigenen eine andere, noch unbekannte Nummer derselben Form, wird er nicht zugeordnet
  (Warnung `auszahlung_andere_nummer`, mit dem Import jener Abrechnung erledigt); kommt der
  Umsatz mit der eigenen Nummer erst, nachdem einer ohne Nummer zugeordnet wurde, und ist er
  als Erlös gebucht, ist das ein Fehler-Befund „schon gebucht“ (die Zuordnung bleibt). Die
  ganze Regel steht in `integrationen/auszahlung.py`. Ist nicht zu entscheiden, welcher
  gebuchte Umsatz die Auszahlung ist, nennt der Befund alle, statt zu raten, und die
  Voranmeldung jedes ihrer Monate warnt. Ein Befund „schon gebucht“ gilt, solange der Abgleich
  denselben Umsatz findet; nennt ein späterer Lauf einen anderen oder keinen mehr, ist er
  erledigt. Ist die Auszahlung als Geldbewegung auf ein anderes Konto gebucht (z. B. 1360 statt
  1361), warnt der Abgleich (`auszahlung_umgebucht`) mit der Umbuchung — vorher kam seit der
  Korrektur oben kein Befund mehr, das Verrechnungskonto behielt still den Saldo; bei PayPal
  nennt der Korrekturvorschlag das Geldtransitkonto, auf das accounti selbst bucht. `marktplatz
  import` und `marktplatz abgleichen` nehmen die Laufsperre von `bank lauf` (sonst konnten beide dieselbe
  Auszahlung buchen); der Jahresabschluss prüft die Verrechnungskonten der Marktplätze
  (1361–1363)
- **Marktplatz: echte Auszahlung mit Bankreferenz nicht zugeordnet, still doppelter Erlös**
  (Nachprüfung 5 E, M4): Nannte der Verwendungszweck statt der Abrechnungsnummer eine andere
  Zahl derselben Länge (`EREF 4711000815`, `KD 40123456789`), hielt der Abgleich den Umsatz für
  die Auszahlung einer noch nicht importierten Abrechnung — nicht zugeordnet, `bank lauf`
  buchte ihn im selben Lauf per Regel als Erlös, die UStVA schwieg bis zum nächsten Abgleich;
  nach dem Zusammenführen mit #31 wäre er für immer offen geblieben. Als fremde
  Auszahlungsnummer zählt jetzt nur eine Zahl mit denselben zwei ersten Ziffern (die Nummern
  eines Marktplatzes laufen fort) und nicht hinter einer Kunden-, Mandats-, Konto- oder
  Rechnungsangabe; die Warnung `auszahlung_andere_nummer` nennt `marktplatz zuordnen`. `bank
  lauf` kontiert keinen Umsatz, über den der Abgleich desselben Laufs einen Befund hat, auch
  nicht aus einem Beleg. Ist derselbe Umsatz ohne Nummer der einzige Kandidat zweier
  Abrechnungen, bekommt ihn keine (`auszahlung_mehrdeutig` an beiden, vorher die zuerst
  geprüfte); dafür gleicht auch der Import einer einzelnen Abrechnung alle ab — eine Warnung,
  die sich mit ihm erledigt, ist sofort erledigt. Eine Zuordnung ohne Nummer im
  Verwendungszweck ist geraten und sagt das als Hinweis (`zuordnung_ohne_nummer`). Ein Bericht
  mit mehreren Abrechnungen gleicht erst ab, wenn alle gespeichert sind. Ein als Erlös gebuchter
  Umsatz mit exakt dem erwarteten Betrag, aber ohne Stichwort und Nummer, ist ein Befund (seit
  Nachprüfung 6 E „vielleicht gebucht“ ohne korrigiere-Befehl, siehe dort); ohne `bank_stichworte`
  warnt der Import (`bank_stichworte_leer`) — in Fremdwährung erkennt der Abgleich eine
  Auszahlung ohne Stichwort und Nummer nicht, die Kontierung buchte sie als Erlös. Die Warnung
  `auszahlung_andere_nummer` kommt auch ohne Stichwort, wo der exakte Betrag Treffer wäre
  (sonst blieb die Auszahlung still offen); „schon gebucht“ erledigt sich nach der Korrektur
  auch, wenn danach mehrere Umsätze passen (vorher blieb der Fehler und schlug die Korrektur
  einer stornierten Buchung vor)
- **Marktplatz: bezweifelte Zuordnung ohne Ausweg** (Nachprüfung 5 E, N1): Kam der Umsatz mit
  der eigenen Nummer nach einer Zuordnung ohne sie, blieb die Zuordnung, auch nach der
  vorgeschlagenen Korrektur — das Verrechnungskonto behielt einen Rest, die andere Abrechnung
  stand für immer „gebucht“ ohne Befund (mit #31 bleibt der eigene Umsatz offen, dann kam gar
  kein Befund). Jetzt warnt der Abgleich (`auszahlung_zweifel`), solange der Umsatz mit der
  Nummer offen oder als Geldbewegung auf dem Verrechnungskonto steht, ebenso wenn der
  zugeordnete Umsatz die Nummer einer inzwischen bekannten anderen Abrechnung nennt; der
  Befund — auch der Fehler „schon gebucht“ — nennt `marktplatz zuordnen`, das die Zuordnung
  löst und beide richtig stellt. Die Ausgabe von `marktplatz abgleichen` und `bank lauf` zählt
  eine bezweifelte Zuordnung nicht mehr als „offen“
- **Marktplatz: eigene Nummer außerhalb der Toleranz ohne Befund** (Nachprüfung 5 E, N2): Ein
  Umsatz mit der eigenen Abrechnungsnummer, vor dem Import als Erlös gebucht, bekam keinen
  Befund, wenn sein Betrag außerhalb der Toleranz lag (falscher `--kurs`, Teilbetrag) — die
  UStVA schwieg bei doppeltem Erlös. Jetzt „schon gebucht“ (Fehler, mit beiden Beträgen, die
  Voranmeldung des Bankmonats warnt), nach der Korrektur `auszahlung_abweichung`; „schon
  gebucht“ geht einer Abweichung vor
- **Marktplatz: opos-Zahlungsvorschlag übergangen, Bankumsatz doppelt gebucht** (Nachprüfung
  6 E, Mb): `marktplatz zuordnen` nahm einen Umsatz, den opos einer fremden Forderung
  vorgeschlagen hatte; nach `opos bestaetigen` stand er zweimal auf der Bank (1200/1361 und
  1200/10001), die fremde Forderung galt als bezahlt. Jetzt lehnt `marktplatz zuordnen` einen
  Umsatz mit offenem Zahlungs- oder Beleg-Vorschlag ab (die Meldung nennt `accounti opos
  ablehnen <Umsatz>` bzw. `bank ablehnen`), `opos bestaetigen` einen inzwischen gebuchten oder
  einer Auszahlung zugeordneten Umsatz („Vorschlag veraltet“), und `bank lauf` gibt Umsätze mit
  Abgleichsbefund auch opos nicht als Zahlung (wie der Kontierung)
- **Marktplatz: „schon gebucht“ bei fremdem Erlös gleicher Höhe, der Vorschlag löschte echten
  Erlös** (Nachprüfung 6 E, Mc): Ein Barverkauf im Kassenbuch oder eine Kundenzahlung mit genau
  dem Betrag der Auszahlung bekam den Fehler „Erlöse wären doppelt“ mit einem korrigiere-Befehl;
  wer ihm folgte, hatte Umsatz und USt zu niedrig gemeldet, danach warnte nichts mehr. Der Fehler
  mit Befehl kommt nur noch für Umsätze mit Stichwort oder eigener Nummer. Ein als Erlös
  gebuchter Umsatz mit genau dem Betrag, aber ohne beides, ist `auszahlung_vielleicht_gebucht`
  ohne Befehl („prüfen“) — ein Hinweis, ohne `bank_stichworte` eine Warnung, bei der auch die
  Voranmeldung seines Monats warnt (dort ist der Betrag das einzige Merkmal; sonst bliebe ein
  doppelter Erlös still). Kassenbuch-Vorgänge und Kartenumsätze (N-d: Bankkonto einer
  Kreditkarte oder ihr Sachkonto) sind keine Kandidaten einer Auszahlung — sie geht aufs
  Bankkonto, wie bei der Kontierung. Grenze: Ohne Stichwort und Nummer klärt sich eine schon
  als Erlös gebuchte Auszahlung nicht mehr über einen fertigen Befehl — der Mensch prüft den
  Kontoauszug und bucht selbst um (der frühere Befehl löschte bei einer fremden Einnahme echten
  Erlös); einen Umsatz, den opos als Zahlung eines Postens gebucht hat, nennt der Befund nicht
- **Marktplatz: PayPal nahm fremde Umsätze gleicher Höhe, ohne Befund** (Nachprüfung 6 E, Md):
  eine Kundenzahlung „RE-2026-12, Galerie Nord GmbH“, eine eBay-Auszahlung „EBAY MANAGED
  PAYMENTS AUSZAHLUNG 6001234567“ oder die Lastschrift einer offenen Eingangsrechnung wurden
  PayPals Auszahlung bzw. Einzahlung (die Rechnung blieb offen, eBay fand nichts, Aufwand und
  Vorsteuer fehlten). Kein Kandidat ist jetzt — ohne die eigene Nummer — ein Umsatz mit dem
  Stichwort eines anderen Marktplatzes (und nicht dem eigenen), mit der bekannten Nummer der
  Abrechnung eines anderen Marktplatzes oder mit der Belegnummer eines opos-Postens. `bank lauf`
  gleicht weiter vor opos ab (die Auszahlung ist gebucht, bevor opos oder eine Regel sie sieht)
  und lässt die Zahlung einer Rechnung so für opos liegen. Ein Treffer ohne Stichwort trägt auch
  bei PayPal den Hinweis `zuordnung_ohne_nummer` (Text „nach Betrag, ohne Stichwort“, mit
  `--loesen`); nennt ein Umsatz, der einziger Kandidat mehrerer Abrechnungen ist, die Nummer
  genau einer, bekommt sie ihn (N-b)
- **Marktplatz: echte Auszahlung wegen einer Belegnummer still offen, als Teilzahlung gebucht
  oder ohne „schon gebucht“** (Nachprüfung 7 E, M1): Der Ausschluss aus Nachprüfung 6 E (Md)
  traf jeden Umsatz, der irgendeine Belegnummer aus opos nannte — „AUSZAHLUNG VOM 03.09.2026“
  die Monatsrechnung 09/2026, „2026-09-03“ den Posten 2026-09, „REF 100045“ eine alte
  Eingangsrechnung. Die Auszahlung blieb ohne Befund offen, opos buchte sie automatisch als
  Teilzahlung einer Monatsforderung, und eine von Hand als Erlös gebuchte verlor den Fehler
  „schon gebucht“ (8400 doppelt, UStVA still). Jetzt ist ein Umsatz nur dann die Zahlung eines
  Postens, wenn er die Belegnummer nennt (nicht als Datum oder Teil eines Datums), den Posten in
  seiner Richtung tilgt und dessen Betrag hat; ein gebuchter mit Stichwort oder Nummer nur, wenn
  opos ihn als Zahlung gebucht hat. Trägt die Zahlung einer Rechnung das Stichwort und den
  Betrag der Auszahlung, sagt es der Hinweis `auszahlung_rechnung`. Auch opos selbst liest einen
  Teil eines Datums nicht mehr als Referenz (`opos.zuordnung.im_datum`)
- **Marktplatz: Auszahlung über PayPal, Datum als Shopify-Nummer** (Nachprüfung 7 E, N1): Eine
  eBay-Auszahlung mit nur „PAYPAL“ im Text blieb still offen; das PayPal-Stichwort schließt jetzt
  nur aus, wenn eine PayPal-Abrechnung den Betrag erwartet (sonst Treffer mit Hinweis, der das
  Stichwort nennt) — andere fremde Stichworte weiter immer. Das Datum, das ein Shopify-Export ohne
  Payout ID als Nummer trägt, gilt nicht als Auszahlungsnummer (die eBay-Auszahlung mit
  „2026-08-21“ im Text war ausgeschlossen, Shopify meldete eine falsche Abweichung)
- **Marktplatz: „vielleicht gebucht“ mit Stichworten verdeckt und ohne UStVA** (Nachprüfung 7 E,
  N2): Der Hinweis erscheint in der Voranmeldung des Bankmonats als Hinweis (nicht sperrend) und
  steht neben einem anderen Befund derselben Auszahlung, statt hinter ihm zu verschwinden
- **`opos zuordnen` schlug eine zurückgehaltene Auszahlung einer Forderung vor** (Nachprüfung
  7 E, Mb-Rest): Wie `bank lauf` und `classify` lässt es Umsätze aus, über die der
  Marktplatz-Abgleich einen Befund hätte
- **Marktplatz: Abläufe aus Nachprüfung 7 E** (N1–N4): Die Kursdifferenz eines vorgebuchten
  Umsatzes bleibt im Wirtschaftsjahr (`datev.wirtschaftsjahr_beginn`) der Auszahlung — bisher
  das Kalenderjahr: bei einem WJ ab 01.07. ging sie in den Juli des nächsten WJ, und ein offener
  Januar desselben WJ galt als gesperrt; die Warnung `auszahlung_gesperrt` nennt das
  Geschäftsjahr mit Beginn und Ende. Eine Kundenzahlung, die opos eindeutig einem offenen
  Posten zuordnet (bekannter Kunde, genau der Rest), hält Regel 4 nicht mehr als „andere
  Nummer“ zurück, auch wenn eine Zahl darin wie eine Auszahlungsnummer aussieht — opos gleicht
  die Rechnung aus, statt dass sie gemahnt wird. `bank lauf` bestätigt keinen Beleg für einen
  Umsatz mit Abgleichsbefund (ebenso `bank abgleich`, jetzt mit `--config`), und
  `marktplatz zuordnen` meldet einen schon bestätigten Beleg
  auf dem Umsatz (er bliebe sonst still ungebucht). `marktplatz zuordnen` nimmt einen Umsatz
  vor dem Zeitfenster einer Auszahlung auch mit `--trotzdem` nicht (die Meldung sprach von
  „spät gebucht“); `--trotzdem` gilt wie in der Hilfe nur nach dem Fenster (bei einer
  Einzahlung auch davor, Nachprüfung 9 E)
- **Marktplatz: festgeschriebener Monat brach jeden Abgleich ab** (Nachprüfung 6 E): Ein
  vorgebuchter Umsatz (nach „schon gebucht“ und der Korrektur auf das Verrechnungskonto) mit
  Kursdifferenz in einem festgeschriebenen Monat ließ `marktplatz abgleichen`, `bank lauf`,
  jeden Marktplatz-Import und `marktplatz zuordnen` mit PeriodeGesperrtError abbrechen. Die
  Kursdifferenz geht jetzt auf den ersten offenen Tag desselben Geschäftsjahres — wie die
  Korrektur selbst mit `--datum` (der festgeschriebene Monat bleibt unverändert, GoBD Rz.
  107 ff.; ohne Umsatzsteuer) —, der Hinweis `kursdifferenz` nennt Tag und Monat, `--loesen`
  storniert auch sie. Ist bis zum Jahresende kein Tag offen (§ 252 Abs. 1 Nr. 5 HGB), wird der
  Umsatz nicht Treffer: Warnung `auszahlung_gesperrt`. `marktplatz zuordnen` eines offenen
  Umsatzes in einem abgeschlossenen Zeitraum lehnt mit klarer Meldung ab
- **`marktplatz zuordnen`, `--loesen`, `classify`: kleinere Lücken** (Nachprüfung 6 E, N-a bis
  N-i): Der gedruckte Befehl ist ausführbar (Nummer in Anführungszeichen, bei PayPal mit
  `--posten`); `--loesen` warnt wie `korrigiere`, wenn die verworfene Vorschlagsbuchung schon an
  DATEV ging (Stapel, `--erneut --alle`), und nennt eine Geldbewegung, die auf dem
  Verrechnungskonto stehen bleibt; `classify` kontiert wie `bank lauf` keinen Umsatz, über den
  der Abgleich einen Befund hätte, auch nicht aus einem Beleg (der Abgleich läuft dafür in einem
  Sicherungspunkt und wird zurückgerollt); Regel 4 zählt eine Zahl hinter RECHNUNGSNUMMER, INV,
  BESTELLNR, ORDER, CUSTOMER, REF (auch END-TO-END-REF) oder BELEG nicht als
  Auszahlungsnummer, hinter EREF weiter
- **UStVA: § 153 Abs. 1 AO auch bei sinkender Zahllast** (Nachprüfung 6 E): Der Befund
  `abgegeben_abweichend` nennt die Pflicht zur Berichtigung nur, wenn Kz 83 steigt (Verkürzung);
  sonst „eine berichtigte Voranmeldung stellt das richtig …, keine Pflicht“ — wie die Hinweise
  der Verbuchung. Grenze (nicht behoben): `opos verbuchen` bucht die OSS-Umsatzsteuer einer
  sonstigen bzw. elektronischen Leistung weiter auf 1767 („… Lieferungen“) statt 1768 (SKR04
  3817 statt 3818) — die Belegposition trägt nicht, ob sie eine Leistung ist (das steht nur an
  der Position der Ausstellung, sie zu übertragen ist kein kleiner Eingriff), und die
  Erlös- und OSS-Konten der Verbuchung sind SKR03-Konten; steuerlich neutral (Kz 45, die
  OSS-Meldung rechnet aus dem Erlös), nur der Kontennachweis
- **`marktplatz import` in einen festgeschriebenen Monat** (Gesamttest Steuer B9): statt eines
  Tracebacks beim Schreiben (und einer verwaisten Datei im Archiv) prüft der Import die Sperre
  vor dem Ablegen und meldet klar, was zu tun ist; `--buchungsdatum offen|JJJJ-MM-TT` bucht die
  Posten wie bei `opos verbuchen` in einen offenen Zeitraum (Belegdatum bleibt), nie in ein
  anderes Geschäftsjahr (§ 252 Abs. 1 Nr. 5 HGB); der Befund sagt, dass accounti die Umsätze
  dann im Buchungsmonat zählt, und warnt davor, den Leistungsmonat zusätzlich von Hand zu
  berichtigen (doppelt gemeldet). Scheitert ein Import nach dem Ablegen, wird die eben
  abgelegte Datei wieder entfernt
- **DATEV-Automatikkonten fehlten** (Gesamttest Abschluss B3): `pruefung/skr03.yaml` kennt
  8801/8820 (AM, Anlagenverkauf 19 %), 8731/8736 (AM, gewährte Skonti), 3731/3736 (AV,
  erhaltene Skonti) — beide DATEV-Exporte lassen dort das BU-Feld
  leer, statt einen Steuerschlüssel zu setzen, den DATEV auf Automatikkonten nicht annimmt
- **Nachbesserung Web-Oberfläche Teil 1** (Prüfberichte 10b-1): gelernte Regeln mit
  `buchhaltung.gelernte_regeln: pruefen` legten Belegbuchungen und offene Posten trotzdem
  automatisch an; übernommene Regeln ohne Richtung buchten Erstattungen als Geldabgang; ein
  TIFF mit sehr vielen Seiten blockierte die Belegvorschau (Seiten werden jetzt nur bis zur
  Höchstzahl gelesen); ein Einmalcode auf `/buchungen/{id}` war verbraucht, auch wenn die
  Korrektur danach fachlich scheiterte (jetzt nur bei Erfolg); die Arbeitsfläche zeigte bei
  Buchungen mit Beleg die Umsatzdaten nicht; Confidence-Werte wie 0,57 erschienen als „56 %“;
  der Hinweis „Der Umsatz ist wieder offen“ erschien auch, wenn ein weiterer Buchungssatz am
  Umsatz blieb; Grund und „an“ ohne Längengrenze auf dem Server; die Arbeitsfläche lud für
  die Geschwister alle Buchungen. E-Rechnungen: DTD- und Entity-Deklarationen werden auch in
  UTF-16 abgelehnt (bisher fand der Byte-Vergleich sie nicht, eine interne Entity wurde in der
  Ansicht expandiert).
- **Web-Oberfläche Teil 1 nach dem Zusammenführen** (Prüfberichte gw-web, gw-storno):
  Erfolgsmeldungen der Prüfung, „nicht gefunden“/„Methode nicht erlaubt“ und „Formular zu
  groß“ erscheinen in der Sprache der Oberfläche, Status, Belegart und Profil der E-Rechnung
  lesbar statt als Rohwert („zur Prüfung“ statt `pruefung`), „Strg“ englisch „Ctrl“;
  Unicode-Ziffern („²“, „٩“, „４９３０“) in Seite, Steuerschlüssel, Konten und Zeitraum der
  USt-VA gaben 500 oder galten als Zahl bzw. Konto (jetzt nur ASCII-Ziffern, sonst 422);
  Fehler und Eingaben des
  Storno-Formulars landeten im Korrektur-Formular; die Sprachwahl auf einer Antwort auf ein
  POST endete mit 405 (jetzt zurück zur Ansicht); eine fehlerhafte `abschluss.kontenzuordnung`
  gab beim Freigeben, Korrigieren und Stornieren 500 statt 409 mit Meldung; ein Doppelklick
  auf Stornieren/Korrigieren zählte einen Fehlversuch oder verbrauchte einen zweiten Code
  (jetzt 409 „inzwischen geändert“). Die Regelseite nennt die Gegenbuchung zur Prüfung.
- `korrigiere --lernen` und `lerne` hängten die Regel ans Ende der Regeldatei — hatte eine frühere
  Regel falsch kontiert, griff die gelernte nie; dabei gingen die Kommentare der Datei verloren,
  und im Container (schreibgeschütztes `config/`) brachen beide ab.
- **Nachbesserung 10b-1 nach dem Zusammenführen mit main** (Prüfberichte gw-regeln,
  gw-migration, gw-storno): Aus einer **Umbuchung zwischen eigenen Geldkonten** (Soll und
  Haben Kasse, Bank, Kreditkarte, Geldtransit oder eingerichtete Konten — neuer Abschnitt
  `zahlungsmittel` der Kontenrahmendateien, eine eigene Kontenzuordnung ohne ihn nimmt die
  Bankkonten) wird keine Regel: `korrigiere --lernen` und `lerne` enden mit Meldung und
  Exit 1, Queue und Regelvorschau mit 422 — bisher wurde aus „1200 an 1210“ auf dem Tagesgeld
  die Regel „1200 an 1200“. **Eine Buchung mit Soll = Haben entsteht nie mehr automatisch**
  (gelernte Regel, Regeldatei, Standardregel, Gegenbuchung, LLM, Beleg): `classify`, `bank
  lauf` und der REST-Lauf lassen den Umsatz offen und nennen ihn (REST
  `kontierung.umbuchung`); Belegbuchung und OPOS nehmen kein Geld-, Personen-, Forderungs- oder
  Verbindlichkeitskonto als Sachkonto (sonst „70001 an 70001“). Neue Prüfregel
  `soll_gleich_haben` (Fehler) meldet Altfälle. `regeln uebernehmen` stellt die übernommenen
  Regeln hinter alle schon gelernten (bisher gewann ein alter Eintrag gegen eine neuere
  Korrektur), lässt Einträge mit `pruefen`/`confidence` und Umbuchungen in der Regeldatei
  (eine gelernte Regel hat kein Prüfkennzeichen und buchte sie automatisch), übernimmt mit
  `--name` auch Einträge ohne Präfix `gelernt_` und nennt, was in der Datei bleibt. **SKR04:**
  Belegbuchung und OPOS buchten Ausgangsbelege auf die SKR03-Erlöskonten 8400/8300/8200 (EÜR
  „nicht zugeordnet“) — jetzt 4400/4300/4200, steuerfrei 4125/4120/4100/4336 (besteht auf
  main). Die Regelvorschau zählt „davon heute anders gebucht“ der Gegenrichtung in deren
  Richtung; eine Regeldatei mit ungültigem Muster, falschem `feld` oder kaputtem YAML ergibt
  eine Meldung mit Regelname statt Traceback bzw. 500 (REST-Lauf: 409). `db upgrade` prüft nach der Migration
  das Schema: Eine Datenbank vom Vorabstand von 10b-1 (Vermerk `e7153706b43a`, Migrationen von
  main fehlen) meldet es mit dem verlustfreien Weg statt „0 Migration(en)“; `db upgrade
  --aus-schema` holt die Migrationen nach. CLI-Befehle auf einer nicht migrierten Datenbank
  nennen `accounti db upgrade` statt eines Tracebacks. Die CLI verbraucht den Einmalcode
  (auch einen Wiederherstellungscode) bei `buchung storniere`, `korrigiere`, `lerne` und
  `bestaetige` erst nach einer Fachprobe — ein fachlicher Fehler kostet ihn nicht mehr
  (besteht auf main).
- **Nachbesserung 10b-1, Runde 3** (Prüfberichte gw2-regeln, gw2-umbuchung, gw2-web,
  gw2-betrieb, gw2-merge): **SKR04: OSS-Fernverkäufe** aus eigenen Rechnungen fehlten in der
  OSS-Meldung (Sammelkonto 4320, die Meldung kannte nur 8320–8327) — jetzt Länderkonten
  4320–4327 wie im SKR03; Meldung, Lieferschwelle, Kz 45 und Prüfregel lesen die Konten des
  Kontenrahmens; ein Land ohne Länderkonto bucht auf „Erlöse“ zur Prüfung mit Hinweis (bisher
  meldete die OSS-Meldung es als Frankreich). **Regeldatei:** ein leeres Konto (gebucht als
  „None“), `soll_konto: 0420` ohne Anführungszeichen (YAML-Oktalzahl, gebucht auf 272), ein
  leeres Muster (traf jeden Umsatz), ein Steuerschlüssel als Text, eine Datei, die nicht UTF-8
  ist, oder ein Verzeichnis ergeben eine Meldung mit Regelname statt einer Fehlbuchung,
  eines Tracebacks bzw. 500 (REST-Lauf 409); `0420` bleibt das Konto 0420; `feld:
  gegenkonto_iban` ist wieder zulässig. `regeln uebernehmen` prüft die Einträge ebenso, meldet
  eine kaputte Datei statt eines Tracebacks und hält die Reihenfolge der Datei auch über
  mehrere Läufe (ein zweiter Lauf mit `--name` stellte seinen Eintrag vor die früher
  übernommenen). **Belegbuchung und OPOS** übergingen Wertpapiere (1348), Festgeld (1290,
  SKR04 1890), Rückdeckungsversicherung und Verrechnungskonten als Sachkonto — jetzt nur noch
  Zahlungsmittel, Personenkonten und die Sammelkonten der Forderungen und Verbindlichkeiten aus
  Lieferungen und Leistungen (Abschnitt `lul_konten`); die Begründung nennt ein übergangenes
  Konto, und ein solches Konto wird nicht mehr als Sachkonto am Kontakt „gelernt“. Eine Regel
  gegen Geldtransit (1360/1460, Abschnitt `geldtransit`) ist wieder lernbar; eine eigene
  Kontenzuordnung ohne `zahlungsmittel` nimmt die mitgelieferten Zahlungsmittel (Kasse und
  Karte galten sonst nicht als Geldkonto), und Regelvorschau und Speichern urteilen gleich.
  `korrigiere --lernen` (bzw. der Haken „Regel“) aus einer Umbuchung korrigiert jetzt ohne
  Regel mit Hinweis, statt auch die Korrektur zu verwerfen. **Soll = Haben von Hand** lehnt
  accounti ab: Korrektur in Queue, `/buchungen/{id}`, CLI und REST, `kasse buchen --konto`
  mit dem Kassenkonto; ein Altvorschlag „1210 an 1210“ lässt sich nicht freigeben. **Einmalcode:**
  `regeln deaktivieren` (Tippfehler im Namen, schon deaktiviert), `regeln uebernehmen`
  (kaputte Datei), `kasse …` und `periode schliessen/oeffnen` verbrauchen ihn erst nach einer
  Fachprobe; im Browser prüft die Freigabe von USt-VA und Zahlungslauf erst Zeitraum und
  Fachlogik (bisher war der Code bei „2026-13“ oder einem gesperrten Monat verbraucht), und ein
  Doppelklick auf Freigeben bekommt 409 statt „Einmalcode falsch“ samt Fehlversuch. Zahlen
  mit mehr als 4300 Ziffern bzw. ab 2^63 (Seite, Steuerschlüssel, Seitennummer der
  Belegvorschau, Nummer des Zahlungslaufs) geben Seite 1, 422 bzw. 404 statt 500.
- **Nachbesserung 10b-1, Runde 4** (Nachprüfung g3w-fach, g3w-merge, g3w-web): **§ 14c
  UStG nach dem Zusammenführen:** Eine Belegbuchung mit ausgewiesener Umsatzsteuer (Schlüssel
  3/2) ließ sich per `korrigiere --steuer 94/91/19/18 --grund …` (bei einem Beleg ohne
  Positionssatz mit jedem Schlüssel) umschlüsseln, auch per POST im Browser — die USt fiel
  still aus der Voranmeldung. Wie auf main sperrt wieder jede Schlüsseländerung (§ 14c Abs. 1
  UStG: geschuldet bis zur Berichtigung); § 13b bzw. ig. Erwerb auf Belegen ohne ausgewiesene
  USt (Paket C) bleibt möglich. **Regeldatei:** ein Steuerschlüssel ab 2^63 (REST-Lauf 500,
  Traceback in `classify` und `regeln uebernehmen` nach dem Einmalcode) oder einer, den
  accounti nicht kennt (0, −9, 99), unbekannte Schlüssel wie `prüfen` oder
  `steuerschluessel` (still ignoriert: automatisch statt zur Prüfung bzw. ohne Vorsteuer) und
  YAML-Zahlformen wie `0x1340`, `1:20:00`, `4_920` (gebucht auf 4928, 4800, 4920) ergeben eine
  Meldung mit Regelname. **Kontonummern nur aus ASCII-Ziffern:** „１２００“ umging die Sperre
  gegen Soll = Haben, galt als Bank und ließ `export datev` abbrechen (CLI `korrigiere`,
  `lerne`, `kasse buchen`, Regeldatei). **`korrigiere --steuer`** und **`lerne --steuer`**
  lehnen unbekannte Schlüssel (−1, 0, 4 …) ab wie der Browser. **Kassenbuch:** Gegenkonto
  „abc“ bzw. „12“, ein Steuersatz außer 19/7 % (50 % buchte 5 € Vorsteuer aus 15 €), eine
  Kombination, die die Prüfregel `steuerschluessel_konto` als Fehler einstuft (Vorsteuer auf
  Erlös, USt auf Aufwand), und ein Vorgang im festgeschriebenen Monat werden abgelehnt.
  **Einmalcode:** `ustva freigeben`, `zahlung freigeben` und `belege freigeben` prüfen vor dem
  Code (Zeitraum, gesperrte USt-VA, unbekannter Lauf bzw. Beleg); `regeln uebernehmen` prüft
  mit dem echten Lauf (zurückgerollt) und verbraucht keinen Code, wenn es nichts übernähme;
  Namen, die erst nach 100 Zeichen verschieden sind, und zu lange Muster sind ungültig statt
  ein Fehler beim Speichern. **Zeitraum mit Jahr 0000** gibt eine Meldung bzw. 422 statt
  Traceback bzw. 500. **SKR04:** Forderungen gegen verbundene Unternehmen (1260–1269) bzw.
  Beteiligungsunternehmen (1280–1289) sind wie im SKR03 (1594/1596) als Sachkonto eines Belegs
  zulässig; gesperrt bleiben die Forderungen aus Lieferungen und Leistungen. Hilfe und
  betrieb.md: übernommene Einträge erst nach allen Läufen mit `--name` aus der Regeldatei
  löschen.
- **Nachbesserung 10b-1, Runde 5** (Nachprüfung g4w): **§ 14c/§ 17 UStG beim Tausch von
  Soll und Haben:** `korrigiere <id> --soll 8400 --haben 10001` auf „10001 an 8400, Schlüssel
  3“ lief ohne Grund durch (auch im Browser über das normale Formular und in der Queue) — die
  Voranmeldung zeigte danach Kz 81 −500 und Kz 83 −95 („Erstattung“) und ließ die Freigabe zu
  (schon auf main). Bei einer Belegbuchung bestimmt jetzt der Beleg die Richtung: Eine
  Korrektur, die die Sachseite umdreht, wird abgelehnt — bei jeder Belegbuchung, auch mit
  Vorsteuer oder ohne Steuer; die Berichtigung ist ein eigener Beleg
  (Gutschrift/Rechnungskorrektur). Konten derselben Seite bleiben korrigierbar.
  **Storno ohne Neubuchung:** Hat ein Beleg mit ausgewiesener Umsatzsteuer danach keine
  wirksame Buchung mehr, warnt das Storno (§ 14c Abs. 1 UStG), und die neue Prüfregel
  `beleg_ust_ohne_buchung` meldet ihn. **Kontenrahmen-Datei:** Eine fehlende oder kaputte
  `pruefung.kontenrahmen_datei` ergibt bei `kasse buchen --konto …` und `korrigiere` eine
  Meldung (Exit 1) statt eines Tracebacks. **`regeln uebernehmen`:** Ein langer Name, der in
  den ersten 100 Zeichen einer übernommenen Regel mit anderem Inhalt gleicht, ist ungültig
  („Regelname … ist schon vergeben“) statt still „schon vorhanden“. **Neunstellige
  Personenkonten** (DATEV-Sachkontenlänge 8): `korrigiere`, Queue, `lerne`, Regeldatei und
  `kasse buchen --konto` nehmen Konten mit 4–9 Ziffern, der Kontenrahmen erkennt 9 Stellen
  als Personenkonto, und `export datev` trägt die Sachkontenlänge aus
  `mandant.sachkonten_laenge` in den Kopf (bisher immer 4) und warnt bei Konten, die nicht
  dazu passen. **Regeldatei:** Steuerschlüssel 1 (umsatzsteuerfrei, Kennziffer aus dem Konto)
  ist wieder zulässig. **Geplanter Lauf:** Schlägt ein Schritt fehl, steht der Grund (die
  letzten Zeilen der Ausgabe, geschwärzt) mit im Protokoll statt nur „bank lauf → 1“.
- **Nachbesserung 10b-1, Runde 6** (Nachprüfung g5w): **Richtungssperre:** Runde 5 sperrte
  auch Korrekturen derselben Seite, wenn die Konten die Sachseite nicht bestimmen — „4360 an
  1200 → 1800 an 1200“ (Privatanteil), Spende, Wertpapier 1348, Geldtransit, Lohn- und
  sonstige Verbindlichkeit (SKR04 ebenso), in CLI, Queue und `/buchungen`; ein Vorschlag hing
  fest (auch auf dem Automatikkonto 3400), und die Meldung behauptete einen Seitenwechsel.
  Umgekehrt ging ein echter Tausch ohne Gegenkonto durch („1576 an 1548“ getauscht: Kz 66
  kehrte still um; „10001 an 8125 → 8125 an 8120“; „4930 an 70001 → 1700 an 4930“). Gesperrt
  ist jetzt, was die Seiten vertauscht: ein Konto wechselt die Seite, die aus den Konten
  bestimmte Sachseite oder die Seite des Erfolgskontos dreht, oder eine Kennziffer der
  Voranmeldung kehrt ihr Vorzeichen um. Die Meldung nennt die vertauschten Konten und beim
  Vorschlag den Weg, der geht (freigeben, dann mit Grund stornieren). **§ 14c-Warnung und
  `beleg_ust_ohne_buchung`:** gezählt wird je Satz die wirksam gebuchte ausgewiesene Steuer —
  sie fehlen nicht mehr bei bezahlten Rechnungen (die Zahlung trägt dieselbe `beleg_id`) und
  bei Belegen mit mehreren Sätzen; sie melden nicht mehr fälschlich beim Storno einer
  Gutschrift („die -95,00 € fehlt“) und bei einer wirksam gebuchten Dublette derselben
  Rechnung. **`regeln uebernehmen`:** Ein vergebener kurzer Name mit anderem Inhalt, eine nur
  in der Richtung geänderte Regel und derselbe Name zweimal in einer Datei mit anderem Inhalt
  sind ungültig („… anderem Inhalt … umbenennen“) statt still „schon vorhanden“.
  **Protokoll:** Benutzer und Passwort einer Webhook-Adresse standen teilweise in der Warnung
  des geplanten Laufs (Zeilenumbruch nach 80 Zeichen, Adresse samt Zugangsdaten in der
  Meldung) — jetzt nur Rechner und Port, die Schritte laufen ohne Umbruch, und die Schwärzung
  kennt die ganze userinfo jeder URL, zerschnittene Adressen, verbreitete Zugangstoken,
  „Passwort: …“ und PIN/TAN; die Verfahrensdokumentation nennt Connector-Adressen ohne
  Zugangsdaten. **DATEV:** `mandant.sachkonten_laenge` muss eine ganze Zahl 4–8 sein (bisher
  standen 0, 3, 9, -1 oder true im Kopf), kaputtes YAML ist eine Meldung statt Traceback, und
  `export datev` warnt je Personenkonto, das nicht Sachkontenlänge + 1 Stellen hat.
  **Personenkontenbereiche** (`buchhaltung.debitoren_von` …) nehmen höchstens 9 Stellen.
- **Nachbesserung 10b-1, Runde 7** (Nachprüfung g6w): **Richtungssperre über die
  Korrekturkette:** Zwei Korrekturen hintereinander konnten die Seiten einer Belegbuchung
  tauschen („10001 an 8125 → 10001 an 1590 → 8125 an 1200“ buchte Kz 41 −500; ebenso über
  Aufwand, Privat, Verrechnung, SKR04 und als Vorschlag), weil nur mit der vorigen Buchung
  verglichen wurde. Jetzt gilt jeder frühere Stand der Kette (Original, Neubuchungen,
  direkt korrigierte Vorschläge laut Journal); bestimmt keiner die Seite, die der Rechnung
  (Gutschrift dreht). Eine Kennziffer, die erst durch die Korrektur entsteht und negativ ist
  wie bei einer Gutschrift („10001 an 8125 → 8120 an 8125“: Kz 43 −500), sperrt ebenso.
  **Fehlschlüssel:** Ein Vorschlag „4930 an 1200, Schlüssel 3“ auf einer Eingangsrechnung hing
  fest (keine Freigabe, keine Korrektur, kein Storno) — ein Umsatzsteuerschlüssel auf einem
  Eingangsbeleg ist keine ausgewiesene Steuer (§ 14c gilt für eigene Rechnungen); der
  Schlüssel, den der Beleg vorgibt (19 % → 9, 7 % → 8; Ausgang 3 bzw. 2), ist immer wählbar,
  auch in Queue und `/buchungen`. **`beleg_ust_ohne_buchung`** meldet im Zeitraum des
  Stornos der Umsatzsteuer, nicht in dem eines späteren Zahlungsstornos.
  **`regeln uebernehmen`:** Ein geänderter Buchungstext bei gleichem Namen ist ungültig
  („anderem Inhalt“) statt still übersprungen. **Geplanter Lauf:** Mit `COLUMNS=10000` (Runde
  6) wurde ein Traceback eines Schritts 10 000 Zeichen breit (DEBUG-Protokoll 64-mal so
  groß, Rahmen in der Warnung) — jetzt der Traceback von Python, ohne Rahmenzeichen, Zeilen
  höchstens 1000 Zeichen. **Adressen:** Mit unkodiertem `#` oder `?` im Passwort nannten
  Verfahrensdokumentation („json: alarm:Kassel“), Webhook-Warnung und
  `aufgaben_benachrichtigungen` Benutzer bzw. Passwortziffern als Rechner und Port — jetzt
  nur der Rechner hinter dem letzten `@`; die Schwärzung nimmt „:4711#Sonne“ nicht mehr als
  Port. Eine ungültige Connector-`basis_url` bricht die Verfahrensdokumentation nicht mehr ab
  (der Fehler steht im Dokument). **Kaputtes YAML** ergibt in jedem Befehl eine Meldung
  (`datev stammdaten`, `datev belege`, `pruefen`, `verfahrensdoku` …) statt eines
  Tracebacks. **Abwärtsverträglich:** Eine offene Obergrenze (`kreditoren_bis: 9999999999`)
  gilt mit Hinweis als 999999999 statt jeden Befehl anzuhalten, `sachkonten_laenge: 4.0` als
  4.
- **Nachbesserung 10b-1, Runde 8** (Nachprüfung g7w): **Sicherheit — langer Pfad im
  Zugriffsprotokoll:** Ein unangemeldetes `GET /statisch/<15 000 Zeichen>` hielt den
  Webserver mehrere Sekunden an (40 000 Zeichen: 35 s; schon vor 10b-1, durch Runde 7
  verschärft): Der Pfad stand ganz im Zugriffsprotokoll, und die Schwärzung lief im
  Event-Loop mit quadratischer Laufzeit. Jetzt steht ein statischer Pfad gekürzt auf 200
  Zeichen im Protokoll, die Schwärzung kürzt Zeilen über 4000 Zeichen vorher auf Anfang und
  Ende (ohne ein angeschnittenes Geheimnis stehen zu lassen), und ihre Muster laufen linear
  (100 000 Zeichen in Millisekunden); betrieb.md empfiehlt zusätzlich eine Grenze der
  Anfragezeile im Proxy. **Altfälle:** Eine falsch herum gebuchte Belegbuchung, die vor der
  Richtungssperre (main, Runde ≤ 4) umgedreht wurde, ist wieder korrigierbar (anderer
  Debitor, Erlöskonto, ig. Lieferung → Ausfuhr, Aktivierung) — es zählt der berichtigte
  Stand, nicht der Fehlstand davor. **Zahlungen zum Beleg:** Die Seite der Rechnung gilt nur
  für ihre Buchung; „1200 an 70001 → 1200 an 4930“ (Erstattung als Preisnachlass) und „1590
  an 10001 → 8730 an 10001“ (Skonto) gehen wieder, und Skonto, Rabatt, Bonus und Nachlass zur
  gebuchten Rechnung dürfen eine Kennziffer negativ buchen („8736 an 10001, Schlüssel 3“).
  **Erlöse auf Quittung, Marktplatzabrechnung und unbekanntem Beleg:** Umsatzsteuer auf
  einem Erlöskonto ist dort ausgewiesene Steuer (§ 14c), kein Fehlschlüssel — kein Vorschlag
  9, kein „ohne Steuer“, das Storno warnt wieder. **Adressen:** Ein `@` in Abfrage oder
  Fragment („https://host?an=jan@firma.example“) machte den Teil dahinter zum Rechner, ein
  Rechner mit Umlauten (IDN) galt als fehlerhaft, und ein unkodiertes `/` im Passwort hinter
  Ziffern („https://alarm:4711/Sonne@…“) ließ „alarm:4711“ in Warnung,
  `aufgaben_benachrichtigungen` und Verfahrensdokumentation stehen. **Schwärzung:** Port und
  Abfrage („https://rechner.example:8443?x=1“) und das Wort vor einem „:“
  („Empfänger:max@firma.de“) verschwinden nicht mehr. **Prüfen und `/buchungen`:** Bei fehlerhafter Konfiguration der
  Gesellschaft eine Meldung samt Datei statt still gerechneter Standardwerte; Freigeben,
  Korrigieren und Stornieren erst nach der Berichtigung. **Registry in anderer Kodierung als
  UTF-8** (oder unlesbar): eine Meldung statt eines Tracebacks in jedem Befehl, in `serve`
  und im Planer.
- **Nacharbeit 10b-1** (Nachprüfung g8w, Folgepaket F): **Schwärzung:** Die Kürzung langer
  Zeilen konnte an der hinteren Kante „Bearer“, „passwort:“, „PIN“, „TAN“ oder „secret:“
  von ihrem Wert trennen, der dann ungeschwärzt im Protokoll stand — jetzt wird vor dem
  Schnitt mit Vorlauf geschwärzt. Ein Ziffern-Passwort einer abgeschnittenen Adresse
  („https://alarm:4711?x=…“) galt als Port (Port jetzt nur hinter einem Rechner mit Punkt
  oder `localhost`; „https://host:8443“ ohne Punkt erscheint als „host:***“), Zugangsdaten
  hinter einem Schema nach 42 Buchstaben ohne Trenner blieben stehen, und „PIN“ mit langer
  Leerraumfolge lief quadratisch. Eine Adresse mit „@“ im Passwort vor „#“/„?“ nannte einen
  Passwortteil als Rechner — jetzt der Hinweis „Adresse nicht eindeutig“. **Steuer:** Eine
  auf Quittung oder Marktplatzabrechnung als Erlös im Soll gebuchte Ausgabe („8400 an 1000,
  Schlüssel 3“) lässt sich wieder auf Aufwand mit Vorsteuer berichtigen (keine § 14c-Sperre,
  keine falsche Storno-Warnung); Steuerauswahl im Browser und Prüfregel
  `beleg_ust_ohne_buchung` lesen `elster.steuerrelevante_konten` wie Korrektur und Storno;
  ein Rechnungsteil auf zwei Gegenkonten („10001 an 1590“) wird nicht mehr zur
  Erlösschmälerung mit Umsatzsteuer; die § 14c-Lücke einer Marktplatzabrechnung zählt keine
  Gebührenposition mehr (95 € statt 114 €).
- **Sicherheit: Webserver ohne Anmeldung anhaltbar** (Nachprüfung Folgepaket F, F-B1, schon
  in #36): POST, PUT, DELETE, PATCH … auf einen langen Pfad mit vielen „/“ (z. B. 40 000
  Zeichen) hielt den Event-Loop sekundenlang an — die 404-Seite suchte die Ansicht für die
  Sprachwahl quadratisch; ebenso ein `Accept-Language`-Kopf mit langer Leerraumfolge auf
  jeder Seite, auch `/anmelden`. Beides jetzt linear und begrenzt.
- **Nacharbeit 10b-1, Runde 2** (Nachprüfung Folgepaket F): Auf Quittung oder
  Marktplatzabrechnung verlor ein Erlös seine Umsatzsteuer nicht mehr still in zwei Schritten
  — über eine Erlösschmälerung im Haben („1000 an 8700“, danach „ohne Steuer“) bleibt § 14c,
  und nach Kontowechsel („→ 2700“) und Storno warnen Storno und Prüfregel
  `beleg_ust_ohne_buchung` wieder (die Obergrenze der Lücke zählt die ganze Korrekturkette).
  Skonto zur Zahlung einer Rechnung über ein Verrechnungskonto (1590, SKR04 1370) geht
  wieder. Ein Wert hinter mehr als 40 Leerraumzeichen nach „PIN“, „Passwort:“, „Bearer“ …
  wird wieder geschwärzt.
- **Nacharbeit 10b-1, Runde 3** (Nachprüfung F Runde 2): Eine stornierte oder berichtigte
  Erlösschmälerung („8700 an 1000, Schlüssel 3“) auf Quittung oder Marktplatzabrechnung
  senkt die § 14c-Obergrenze nicht mehr — das Storno des Erlöses warnt wieder mit dem
  ausgewiesenen Betrag (95 € statt keiner Warnung bzw. 76 €), die Prüfregel meldet ihn. Ein
  Rechnungsteil „10001 an 1590“ neben „10001 an 8400“ und „1590 an 8400“ gilt nicht mehr als
  Zahlung (kein Skonto mit Umsatzsteuer daraus). betrieb.md beschreibt den Abstand zwischen
  Schlüsselwort und Wert jetzt so, wie die Schwärzung ihn hält.
- **§ 14c-Lücke, Paket G** (Nachprüfung F Runde 3, gf3-obergrenze GF3-1): Auf einem
  Beleg ohne Steuerzeile (Position „Gesamtbetrag“ ohne Satz) machte eine kleine, auch
  stornierte Erlösschmälerung oder Erstattung („8700 an 1000, Schlüssel 3“) die
  ausgewiesene Umsatzsteuer negativ — das Storno des Erlöses warnte nicht,
  `beleg_ust_ohne_buchung` meldete nichts, die Umsatzsteuer fehlte still (Quittung,
  Marktplatzabrechnung, Ausgangsrechnung). Jetzt zählt je Satz die höchste
  Rechnungsbuchung.
- **Debitoren: Gutschriften, Guthaben, Verrechnung, Handzuordnung** (Gesamttest Ausgang
  B3, B4, B6): `rechnung neu --korrektur-zu <Nr> [--korrektur-art gutschrift|korrektur]`
  stellt eine Gutschrift (Typ 381, Minderung positiv ausgewiesen) bzw. Rechnungskorrektur
  (384, Differenz mit Vorzeichen) mit Bezug auf die Rechnung (BT-25/26) aus — ohne
  `--name` mit dem Kunden der Rechnung, den `--strasse`, `--plz`, `--ort`, `--email`,
  `--ust-id` und `--leitweg-id` ergänzen (etwa die Straße einer älteren Rechnung); KoSIT
  und Mustang prüfen sie wie jede Rechnung.
  Eine negative Menge oder ein negativer Preis wird nie als negativer Einzelpreis
  ausgewiesen (BR-27). Beim Verbuchen wird die Gutschrift mit der noch offenen Rechnung
  verrechnet. Eine Überzahlung schließt den Posten nicht mehr still: Sein Rest wird
  negativ und steht als Guthaben in der Postenliste wie auf dem Personenkonto. Negative
  Posten nehmen an der Zuordnung teil: Erstattungen (Zahlung in Gegenrichtung) treffen
  Gutschriften und Guthaben — auch bei Lieferanten —, nennt der Verwendungszweck
  Rechnung und Gutschrift, wird saldiert, und eine Zahlung „Rest abzüglich Guthaben“
  wird vorgeschlagen; der Gutschriftanteil einer Saldozahlung heißt in der Buchung
  „Verrechnung …“ (nicht „Erstattung“). Als Guthaben zählen nur Posten derselben Richtung —
  die Verbindlichkeit desselben Kontakts ist bei einem Zahlungseingang keins (keine
  Aufrechnung über zwei Personenkonten, auch nicht in der Handzuordnung — dort tilgt eine
  Gutschrift nur Posten desselben Kontakts, höchstens bis zu deren Rest). Neu: `opos
  verrechnen <Nr> <Nr>…` (gegenläufige Posten desselben Kontakts, ohne Buchung, frühestens
  am Belegdatum beider Posten und am Tag der Zahlung, aus der ein Guthaben stammt; Tabelle
  `verrechnungen` nur anfügen — unter SQLite per Trigger, im Bestandsabgleich von `journal
  pruefen` —, Journal `posten_verrechnet`) und `opos zuordnen --transaktion <ID> --posten
  <Nr>…` (Handzuordnung, freigegeben wie `opos bestaetigen`); `bank offen` zeigt die
  Umsatz-IDs. Beim erkannten Kunden mit genau einem offenen Posten wird eine Überzahlung
  vorgeschlagen. Der Mahnlauf mahnt keinen Kunden mit Guthaben, sondern nennt `opos
  verrechnen`; die Prüfregel `op_alter` meldet ein Guthaben als Hinweis statt als Fehler.
  Alembic-Migration `a14acef69fae` nach `2f7c7043043e` (`verrechnungen` mit
  SQLite-Triggern, `ausgangsrechnungen.rechnungstyp`/`korrektur_zu`,
  `ausgangspositionen.elektronisch`; hat `init_db` die Tabelle schon angelegt, übernimmt
  sie sie, und `db upgrade` erkennt den Stand ohne Vermerk an den fehlenden Spalten) —
  **nach dem Update die Datenbank migrieren** (`accounti db upgrade`, siehe
  [Upgrades](docs/betrieb.md#upgrades)), sonst scheitern Befehle an den neuen Spalten
- **Zahlungszuordnung: Belegnummer nur an Wortgrenzen, fremder Zahler nur als Vorschlag**
  (B5): „2026-0315“ trifft nicht mehr das Datum in „EREF+20260315…“ als Teil einer
  längeren Zahl oder IBAN; nennt der Zweck nur Posten eines anderen Kontakts als des
  erkannten Zahlers, hat der Zahler Vorrang und gebucht wird nichts automatisch. Steht
  die Nummer nur als Datum im Zweck — zusammenhängend („EREF+20260315-0042“) oder mit
  Trennzeichen anders gegliedert („Lieferung vom 2026-03-15“, „2026/03/15“, auch mit
  Präfix „RE 2026-03-15“ bei RE-2026-0315 — es zählen die Ziffernwörter) —, bleibt es
  bei unbekanntem Zahler ein Vorschlag (eine Nummer ohne Trennzeichen wie „20260315“ ist
  vom Datum nicht zu unterscheiden und deshalb ohne Zahler nie automatisch); beim
  erkannten Zahler entscheidet dann der eindeutige Betrag. Neben einer echten Referenz
  zählt eine nur als Datum genannte Nummer nicht („RE 2026-0001 vom 2026-03-15“ nennt
  weder die Rechnung noch die Gutschrift 2026-0315, und ein fremder echt genannter Posten
  bleibt ein Widerspruch)
- **Nummernformat ohne `{jahr}`** (B7): zählt über den Jahreswechsel weiter (statt am
  1. Januar mit `IntegrityError` stehen zu bleiben), beginnt hinter dem höchsten bisherigen
  Stand und überspringt schon vergebene Nummern; das Format wird beim Laden geprüft
  (`{nummer}` Pflicht, nur `{jahr}`/`{nummer}`); ein Datenbankfehler beim Ausstellen
  endet mit einer Meldung statt eines Tracebacks
- **Ausgangsrechnungen im Monat der Leistung** (B2, B12): `opos verbuchen` bucht eine
  Ausgangsrechnung zum Leistungsdatum, wenn die Leistung in einem früheren Monat lag
  (§ 13 Abs. 1 Nr. 1 Buchst. a UStG) — Voranmeldung, ZM, OSS, Saldenliste und DATEV
  folgen dem Buchungsdatum; eine ig. Lieferung im Rechnungsmonat, spätestens am Ende des
  Folgemonats der Lieferung (§ 13 Abs. 1 Nr. 6, § 18b Satz 2 UStG); eine
  Gutschrift/Korrektur zu ihrem Datum (§ 17 Abs. 1 Satz 7 UStG). Liegt der Monat
  festgeschrieben, bricht die Verbuchung mit Hinweis auf Öffnen und Berichtigung ab statt
  still später zu buchen; ist die Voranmeldung des Zeitraums schon übermittelt, nennt sie
  die berichtigte Voranmeldung (§ 153 Abs. 1 AO) — bei einer Gutschrift oder Korrektur nach
  unten als Möglichkeit, nicht als Pflicht (sie verkürzt keine Steuer). `rechnung
  ausstellen` weist ein Rechnungsdatum in der Zukunft oder in einem festgeschriebenen Monat
  ab (vor der Nummernvergabe) und weist auf einen festgeschriebenen Leistungsmonat hin
- **Leistungsort von Dienstleistungen an Privatkunden** (B9): § 3a Abs. 1 bzw. Abs. 3 Nr. 3
  Buchst. c UStG — deutsche Steuer auch für EU- und Drittlandskunden; OSS nur noch für
  Fernverkäufe und die neue Positionsart `rechnung position --elektronisch` (§ 3a Abs. 5
  UStG). Elektronische Leistungen an Privatkunden im Drittland (§ 3a Abs. 5 Satz 1 UStG,
  Ort am Wohnsitz) werden weiterhin abgelehnt (Kategorie O). Sonderorte des § 3a Abs. 3
  (Grundstück, Vermietung von Beförderungsmitteln, Veranstaltungen, Vermittlung) und
  Beförderungen (§ 3b) an Privatkunden erkennt accounti nicht — sie gelten als im Inland
  ausgeführt
- **Rechnungen an Privatkunden ohne E-Mail, Kleinbetragsrechnung** (B16): fehlen E-Mail,
  PLZ oder Ort, wird die Rechnung nach EN 16931 statt XRechnung erzeugt (ZUGFeRD-Profil
  EN 16931, `factur-x.xml`, geprüft von Mustang; KoSIT nur für XRechnung). Über 250 €
  braucht jede Rechnung — auch die XRechnung an Unternehmen — Straße oder Postfach, PLZ und
  Ort des Empfängers (§ 14 Abs. 4 Satz 1 Nr. 1 UStG, Abschn. 14.5 Abs. 2 UStAE), bis 250 €
  genügt der Name (§ 33 UStDV) — geprüft beim Ausstellen; `rechnung zeigen` zeigt auch
  eine früher ohne Straße ausgestellte Rechnung (und einen solchen Entwurf) und nennt das
  Fehlende als Hinweis
- **§ 286-Hinweis** (B10): mit `mahnwesen.hinweis_30_tage: true` tragen Rechnungen an
  Verbraucher den Hinweis nach § 286 Abs. 3 BGB (bisher nahm nur der Mahnlauf ihn an)
- **Offene Posten zum Stichtag** (B8): `opos liste|staffel --stichtag` zeigen den Stand
  zum Ende des Tages — gebuchte Posten mit dem Rest nach Zahlungen und Verrechnungen bis
  dahin — passend zur Saldenliste; Guthaben sind gekennzeichnet
- **Kleinere Befunde Ausgang** (B11, B13–B15): Prüfregel `beleg_ohne_zahlung` nennt
  `accounti mahnwesen lauf` und bei Teilzahlung den offenen Rest; Skonto nur mit Satz und
  Frist, 0 < Satz < 100 (auch beim Ausstellen); `rechnung senden --eml` verlangt eine
  ausgestellte Rechnung; `rechnung zeigen` schreibt 20 % statt „2E+1 %“;
  `beleg_unbearbeitet` nennt bei Ausgangsrechnungen den Kunden statt der eigenen Firma
- **Jahresabschluss ignorierte das abweichende Wirtschaftsjahr** (Gesamttest Betrieb B5):
  `abschluss susa|pruefen|buchen|abgrenzungen|abgrenzen|bestaetigen|euer|eroeffnung`
  rechnen jetzt mit `datev.wirtschaftsjahr_beginn` der Gesellschaft (ein Helfer
  `abschluss/konfiguration.wirtschaftsjahr`). **`--jahr` ist das Kalenderjahr des
  Wirtschaftsjahresendes** (2026 = 01.07.2025–30.06.2026, § 4a Abs. 2 Nr. 2 EStG):
  Saldenliste und Prüfungen über das Wirtschaftsjahr zum Stichtag seines Endes,
  Abgrenzung zum WJ-Ende mit Auflösung zum WJ-Beginn, Eröffnungssalden am WJ-Beginn
  (Belegnummer `EB-<Jahr des WJ-Endes>`, auch in einen festgeschriebenen ersten Monat),
  `abschluss buchen` lässt den AfA-Lauf in beiden berührten Kalenderjahren laufen. Der
  AfA-Lauf rechnet dabei je Abschnitt des Kalenderjahres (`anlagen afa --jahr 2025` bei
  Beginn 1. Juli: Juli–Dezember, `--bis-monat 6`: Januar–Juni) — so bucht das erste
  Wirtschaftsjahr nicht die AfA des Vor-WJ aus dem Eröffnungssaldo mit, auch beim Abgang
  und bei `anlagen aendern`. Der Anlagenabgleich zum WJ-Ende zählt im Sammelposten nur Güter
  bis zum Stichtag. Die EÜR nimmt den Vordruck des Jahres des **WJ-Beginns** (Anlage EÜR
  2025 für 2025/2026, BMF 29.08.2025) und nennt bei abweichendem Wirtschaftsjahr die
  zeitanteilige Verteilung des Gewinns auf zwei Kalenderjahre (§ 4a Abs. 2 Nr. 1 EStG,
  Land- und Forstwirte) als Hinweis. Grenzen: `abschluss vortrag` lehnt ein abweichendes
  Wirtschaftsjahr ab (die Jahressperre gilt je Kalenderjahr und sperrte das falsche
  Halbjahr) — die Eröffnungssalden jedes Folge-WJ erfasst man mit `abschluss eroeffnung
  --jahr <Folgejahr>`; `abschluss pruefen` warnt bei degressiver AfA, Sammelposten und
  E-Fahrzeug-Staffel (je Wirtschaftsjahr, der Plan rechnet im Kalenderjahr); `anlagen
  afa`/`spiegel` weisen darauf hin
- **Verfahrensdokumentation und Aufbewahrungsfrist** (Gesamttest Abschluss B10): Die
  Tabelle der Kontierungsregeln zeigte das Muster als `re.compile(…)` und nicht das Feld;
  jetzt Muster und Feld, ein `|` im Muster bleibt erhalten (in Markdown maskiert, im PDF
  wie konfiguriert). Die Aufbewahrung der Belege kommt aus einer Quelle
  (`betrieb/aufbewahrung.py`) für Archiv, Bericht und Dokument: Buchungsbelege und
  Rechnungen 8 Jahre (§ 147 Abs. 3 AO i. d. F. des BEG IV, § 14b UStG) ab Schluss des
  Jahres des Belegdatums, ohne Belegdatum des Eingangs (§ 147 Abs. 4 AO, § 14b Abs. 1 Satz
  3 UStG) — vorher fest 10 Jahre ab Eingangsjahr; ein erkanntes Belegdatum vor dem
  Vorjahr des Eingangs (möglicher Lesefehler) verkürzt die Frist nicht. Übermittlungs- und
  USt-IdNr.-Protokolle bleiben Aufzeichnungen mit 10 Jahren. Institute behalten 10 Jahre
  (Art. 97 § 19a Abs. 3 EGAO i. d. F. vom 22.12.2025, gegengeprüft)
- **Anlagegut und Abgang ließen sich nicht korrigieren** (Gesamttest Abschluss B7): Ein
  Tippfehler bei den Anschaffungskosten oder ein falsches Abgangsdatum sperrte den
  Jahresabschluss dauerhaft. Neu `accounti anlagen aendern <Nr>` (Bezeichnung, Datum,
  Kosten, Nutzungsdauer, Art, Konten; AfA-relevante Änderungen nur mit `--grund`): eigene
  AfA-Vorschläge werden verworfen und neu gerechnet, freigegebene AfA bleibt stehen und
  bekommt eine AfA-Korrektur als Vorschlag; gebuchte AfA in einem abgeschlossenen Jahr
  sperrt die Änderung (Grenze: die Korrektur im ersten offenen Jahr nach dem
  Bilanzenzusammenhang unterstützt accounti nicht). Ein neues Anlagekonto oder ein
  Anschaffungsdatum im Vorjahr nennt den umzubuchenden Buchwert bzw. den fehlenden
  AfA-Lauf als Hinweis. `accounti anlagen abgang <Nr> --zuruecknehmen --grund …` nimmt einen
  Abgang zurück, solange Restbuchwert- und Erlösbuchung Vorschläge sind (freigegebene erst
  stornieren). Beides steht im Journal (`objekt_typ` `anlage`, vorher/nachher, Grund);
  `abgang` braucht `--datum` nur noch ohne `--zuruecknehmen`
- **`anlagen vorschlaege` nannte angelegte Güter weiter** (Gesamttest Abschluss B11): Ein
  Bankumsatz direkt auf das Anlagekonto hat keinen Beleg, der Abgleich lief nur über den
  Beleg. Neu `anlagen anlegen --buchung <ID>` (übernimmt fehlende Angaben, Hinweis bei
  abweichenden Kosten oder Konto) und `anlagen aendern <Nr> --buchung <ID>`; verknüpfte
  Zugänge sind kein Vorschlag mehr, ein Gut mit gleichem Konto, Datum und Kosten erscheint
  als „vermutlich erfasst“. Alembic-Migration `2f7c7043043e` nach `6d38d11fc348` (Spalte
  `anlagegueter.buchung_id`; schon per `init_db` angelegt, übernimmt sie sie; ohne
  Versionsvermerk erkennt `db upgrade` den Stand davor an der fehlenden Spalte)
- **Kassen-Storno nach `classify` kehrte nichts um** (Gesamttest Abschluss B5): Ein
  Kassenvorgang ohne `--konto` wird von `classify` am Umsatz kontiert; das nur anfügbare
  Kassenbuch kennt diese Buchung nicht. `kasse storno` findet die gültige Buchung jetzt
  über den Umsatz (nach `korrigiere` die Neubuchung, auch Splitbuchungen) und kehrt sie
  als Storno mit Verknüpfung um (`storno_von`, Buchungskorrektur). Ein noch nicht
  freigegebener Vorschlag wird nicht storniert (erst freigeben oder korrigieren); ein
  noch nicht kontierter Vorgang bleibt ohne Buchung, mit Hinweis, beide Umsätze gleich
  zu kontieren
- **Storno vor dem Original** (Gesamttest Abschluss B9): `buchung storniere`,
  `korrigiere --datum` und `kasse storno --datum` lehnen ein Datum vor der Buchung bzw.
  dem Kassenvorgang ab (§ 17 Abs. 1 Satz 7 UStG; Kassensturzfähigkeit, § 146 Abs. 1
  AO) und `kasse storno` auch ein Datum vor der umzukehrenden Buchung (nach `korrigiere
  --datum` liegt die Neubuchung später). `kasse storno` ohne `--datum` nimmt heute,
  frühestens den Tag des Originals bzw. dieser Buchung
- **Wiederherstellungstest passte nicht zu mehreren Gesellschaften** (Betrieb B10):
  `docs/betrieb.md` zeigt den Test jetzt mit `-g K` und als Stichprobe nur lesende Befehle
  (`abschluss susa`, `journal`) statt `export datev` (das eine abweichende `--db`
  ablehnt und sonst in die Probe schriebe); Dateinamensbeispiel mit Sekunden. Der Hinweis
  nach `sicherung erstellen` nennt `-g K` bzw. `--system`
- **`opos verbuchen` endete mit Exit 0, auch wenn Rechnungen nicht verbucht wurden**
  (Gesamttest Eingang): Die übrigen Rechnungen werden weiter verbucht, am Ende steht „N
  Rechnung(en) nicht verbucht“ und Exit 1 — Skripte und Cron sehen den Fehler
- **Betrachter schrieb Anlagen, Saldo und Kontoauszüge** (Abschluss B8): `anlagen
  anlegen|afa|abgang`, `abschluss saldo|buchen|abgrenzen` liefen mit eingerichteten
  Benutzern ohne Rechteprüfung (ein Betrachter schied einen Pkw unwiderruflich aus, legte
  über `abschluss buchen` — derselbe AfA-Lauf wie `anlagen afa` — AfA-Buchungen an, im
  Journal „… (ungeprüft)“), `datev kontoauszuege` schrieb Auszüge fest. Jetzt buchen
  (`buchhalter`) bzw. Buchungen freigeben für die Kontoauszüge, jeweils mit Einmalcode;
  `anlagen anlegen|afa|abgang` und `abschluss buchen` haben `--von` (bei `abschluss
  abgrenzen` ist `--von` der Leistungszeitraum, die Person kommt aus
  `ACCOUNTI_BENUTZER`), `abschluss saldo` vermerkt den geprüften Benutzer.
  `FREIGABEWEGE`, README und Verfahrensdokumentation nennen die Befehle
- **Token-Namen und Anmeldeprotokoll über Gesellschaftsgrenzen** (Betrieb B9): Der Index
  `uq_api_token_aktiv` lag nur auf `name` — b konnte kein Token „erp“ anlegen, solange a
  eines hatte, und die Meldung riet zu einem Widerruf, der in b nicht ging. Eindeutig ist
  der Name jetzt unter den aktiven Token einer Gesellschaft (Index, Prüfung, Widerruf;
  Alembic-Migration `6d38d11fc348`, verträgt einen schon von `init_db` angelegten Index;
  ihr Downgrade bricht bei gleichen aktiven Namen in mehreren Gesellschaften ab, bevor es
  den Index löscht).
  `benutzer protokoll` zeigt mit mehreren Gesellschaften nur die Ereignisse der
  Gesellschaften, in denen der Aufrufer Verwalter ist, und die ohne Gesellschaft — diese
  nur über Benutzer mit einer Rolle dort oder ohne Rolle (der Verwalter von b sah sonst
  Sperren und Codes eines Benutzers nur von a)
- **Zweite Gesellschaft bekam keinen Verwalter, der letzte Verwalter öffnete die
  Einrichtungsphase** (Betrieb B7, B8): Nach der Einrichtung verlangte `-g b benutzer
  rolle|anlegen` einen Verwalter **in** b — eine später ergänzte Gesellschaft ließ sich nur
  per SQL besetzen. Jetzt richtet ein Verwalter irgendeiner Gesellschaft mit Einmalcode
  eine Gesellschaft ein, die noch nie einen Verwalter mit zweitem Faktor hatte (Ereignis
  `einrichtung_gesellschaft`). Umgekehrt legte sich der letzte Verwalter mit `benutzer
  sperren` still oder nahm sich die Rolle, und jeder an der Shell legte ohne Code einen
  neuen an. `sperren` und `rolle verwalter --entfernen` lehnen das für den letzten aktiven
  Verwalter mit zweitem Faktor einer Gesellschaft ab; der Merker `verwaltet:<Kürzel>`
  hält die Einrichtungsphase einer einmal verwalteten Gesellschaft geschlossen (fail-closed).
  Die Einrichtung erstreckt sich nicht auf Benutzer, die in der Gesellschaft schon eine
  andere Rolle als `verwalter` haben (sonst setzte der Verwalter von a Passwort und Codes
  eines Freigebers von b); `wiederherstellungscodes_neu` nennt im Protokoll, wer die Codes
  eines anderen erneuert hat
- **`mandant.kontenrahmen` aus der Vorlage wurde ignoriert** (Betrieb B4 = Steuer B3 =
  Abschluss B6): Die Vorlage führte den Kontenrahmen unter `mandant`, gelesen wurde für USt,
  Abschluss, Anlagen und Prüfregeln nur `buchhaltung.kontenrahmen` — eine SKR04-Gesellschaft
  rechnete mit SKR03, nur der DATEV-Kopf sagte „04“. Eine Quelle: `lade_buchhaltung`
  übernimmt `mandant.kontenrahmen`, wenn `buchhaltung.kontenrahmen` fehlt; widersprechen
  sich beide, bricht accounti mit einer Meldung ab; ein unbekannter Wert (`SKR4`) ist ein
  Fehler statt still SKR03. Die DATEV-Stammdaten lesen über denselben Lader; die Vorlage
  führt den Schlüssel unter `buchhaltung`. Fehlermeldungen zu `buchhaltung` und
  `ustid_pruefung` nennen ihren Abschnitt (bisher stand immer „mandant.“ vor dem Feld)
- **Upgrade-Weg für Datenbanken aus `db init`** (Betrieb B2): `init_db` legte nur Tabellen
  an, ohne Versionsvermerk — der dokumentierte `alembic upgrade head` begann bei der ersten
  Migration und brach an „table … already exists“ ab, der neue Code ohne Migration an
  „no such column storniert_durch“. Eine neue Datenbank bekommt jetzt den Vermerk des
  Codes, der sie anlegt (`alembic_version`); der neue Befehl `accounti db upgrade` leitet
  bei Datenbanken ohne Vermerk den Stand aus dem Schema ab, stempelt ihn und migriert
  (`--alembic-ini`, sonst die des Quellbaums bzw. `/app/alembic.ini`). `alembic/env.py`
  nimmt dafür eine übergebene Verbindung. `sicherung wiederherstellen` behält den Vermerk
  des Ziels statt einer älteren Revision aus der Sicherung. Scheitert eine Migration,
  meldet `db upgrade` den Grund und den erreichten Stand (Exit 1) statt eines Tracebacks;
  eine SQLite-Datei, die es nicht gibt (Tippfehler in `--db`), legt es nicht neu an —
  das ist `db init`
- **`-g`/`ACCOUNTI_DB` wirkten nicht bei `ustva`, `pruefen`, `journal` und `nachfordern`**
  (Gesamttest Betrieb B1): Befehlsgruppen mit eigenem Callback bekamen `--db` und
  `--config` der Gesellschaft nicht — `accounti -g sued ustva` zeigte die Kennziffern einer
  leeren `accounti.db` im Arbeitsverzeichnis, `pruefen` „keine Befunde“, `nachfordern`
  schrieb dorthin. Der Kontext setzt die Standardwerte jetzt auch an der Gruppe selbst
- **`--help` brauchte bei mehreren Gesellschaften `-g`** (Betrieb B11): `accounti abschluss
  --help` brach mit Exit 2 ab. Die Hilfe kommt jetzt ohne Gesellschaft, auch hinter
  Optionen einer Gruppe (`ustva --period 2025-08 pruefen --help`); ob es eine Hilfe ist,
  entscheidet Clicks Parser (`--text --help` bleibt ein Wert und bricht ab)
- **Gutschriften wie Ausgaben kontiert** (Gesamttest Eingang B07, Abschluss B4, Steuer B1):
  `classify` buchte eine Erstattung (+119 € Telekom) auf eine Ausgaberegel als zweite Ausgabe
  mit zusätzlicher Vorsteuer (Kz 66 doppelt statt null) und eine „Untermiete“ als Mietaufwand.
  Regeln haben jetzt eine `richtung` (`ausgabe`, `einnahme`, `beide`; mitgelieferte und
  eingebaute Regeln getaggt) und gelten nur für Umsätze dieser Richtung; passt sonst keine Regel
  und kein LLM-Vorschlag, schlägt accounti die Regel als Gegenbuchung vor — Soll/Haben
  getauscht, immer zur Prüfung (Minderung von Aufwand und Vorsteuer, § 17 Abs. 1 Satz 2 UStG).
  Schranke im Mapper für jede Quelle (gelernte Regeln ohne Richtung, LLM): Bankkonto auf der
  falschen Seite → tauschen und zur Prüfung; keine Seite das Bankkonto → zur Prüfung. Neue
  Regelfelder `pruefen` (Treffer immer zur Prüfung) und `confidence`; ein falscher Wert in der
  Regeldatei ist ein Konfigurationsfehler mit Regelname (`classify`, `bank lauf`,
  `opos verbuchen`: Meldung und Exit 1 statt Traceback). Die Verfahrensdokumentation
  (Abschnitt 2.3) nennt Richtung und Prüfkennzeichen der eigenen Regeln (Muster lesbar statt
  `re.compile(…)`), die Standardregeln im Kontenrahmen der Buchhaltung und was unabhängig von
  der Confidence zur Prüfung geht bzw. als Marktplatz-Auszahlung offen bleibt; eine
  fehlerhafte Regeldatei steht dort als Hinweis, statt die Erzeugung abzubrechen
- **`classify` buchte Marktplatz-Auszahlungen vor dem Abgleich** (Gesamttest Steuer B2,
  Teil Kontierung): Eine Amazon-Auszahlung wurde nach Regel Erlös 8400 mit Umsatzsteuer
  (Erlös doppelt in Kz 81), eine Shopify-Auszahlung Aufwand mit Vorsteuer. `classify`,
  `bank lauf` und `POST /laeufe/bank` lassen jetzt offen, was der Marktplatz-Abgleich
  erwartet — Zahlungseingänge mit einem Stichwort aus
  `integrationen.marktplaetze.<name>.bank_stichworte` und Umsätze zu einer offenen Aus- oder
  Einzahlung einer importierten Abrechnung (auch mit Abgleichsbefund: Zeitfenster,
  Vorzeichen, Stichwort, Abrechnungsnummer oder genauer Betrag) — und sagen, was zu tun ist
  (`marktplatz import`; ohne Marktplatz-Import `bank_stichworte: []`). Umsätze des
  PayPal-Kontos selbst kontiert `classify` weiter. Neu: `kontierung.marktplatz` in der
  Antwort von `POST /laeufe/bank`
- **Standardregeln im SKR03 auch für SKR04-Gesellschaften** (Gesamttest Betrieb B3): Die
  eingebauten Regeln kommen aus `standard_regeln(kontenrahmen, bank_konto)` — SKR04-Fassung
  (Bank 1800, Miete 6310, Versicherung 6400, Sonstiges 6300, Geldtransit 1460), für andere
  Kontenrahmen keine. Miete ohne Vorsteuer und zur Prüfung (§ 4 Nr. 12, § 9 UStG), AWS ohne
  Schlüssel auf sonstige Aufwendungen statt Nebenkosten des Geldverkehrs und zur Prüfung
  (§ 13b UStG), Amazon/PayPal-Auszahlung als Geldtransit statt Erlös 8400 mit Umsatzsteuer.
  Neue Prüfregel `bankumsatz_ohne_bankkonto` (Fehler): Buchung zu einem Bankumsatz, die
  weder dessen Bankkonto noch ein eingerichtetes Bank-/Kartenkonto trägt (SKR03-Regel mit
  1200 in SKR04, wo die Bereichsprüfung nichts sieht), und `buchhaltung.bank_konto`, das im
  Kontenrahmen kein Bankkonto ist (SKR04 ohne Angabe: Standard 1200)
- **Trinkgeld in der Zeile mit Vorsteuer** (Gesamttest Eingang B10): Zahlte der Umsatz mehr
  oder weniger als der Beleg (Quittung 59,50 €, Karte 65,00 €), schlug `classify` die
  Differenz der größten Zeile zu — mit Schlüssel 9; der DATEV-Export trug dann 65,00 € mit
  BU 9 (DATEV rechnet 10,38 € Vorsteuer statt 9,50 €), `pruefen` meldete die eigene
  Rechenprobe. Die Differenz kommt jetzt in die Zeile ohne Schlüssel des Kontos (sonst eine
  eigene Zeile „Trinkgeld/Differenz …“), zur Prüfung; die Belegzeilen bleiben, wie der Beleg
  sie ausweist. Trinkgeld ist kein Entgelt des Wirts (Abschn. 10.1 Abs. 5 UStAE)
- **Kreditkartenumsätze auf 1730 nicht korrigierbar** (Gesamttest Eingang B08): Mit dem
  Kartenkonto aus dem README (SKR03 1730, SKR04 3610 „Kreditkartenabrechnung“) lehnten
  `korrigiere` und `buchung storniere` jeden Kartenumsatz mit Vorsteuer ab („beide Seiten
  haben dieselbe Natur“), und eine Erstattung auf der Karte stand in der Saldenliste netto
  auf 1730. 1730 bzw. 3610 sind jetzt Geldkonten (1731–1739 bleiben Sachkonten:
  Agenturwaren, Kautionen, Steuerverbindlichkeiten), und Salden, Storno und Korrektur
  zählen die Sachkonten aller eingerichteten Bank- und Kartenkonten als Geldkonten
- **`config/regeln.yaml`** (Gesamttest Eingang B15): Reisekosten auf 4670 (Reisekosten
  Unternehmer, EÜR Kz 221) statt 4600 Werbekosten; Miete ohne Steuerschlüssel und zur
  Prüfung (bisher Vorsteuer 19 % automatisch aus jedem Dauerauftrag); EU-Digitalleistungen
  zur Prüfung; Marktplatz- und Zahlungsdienst-Auszahlungen als „Bank an Verrechnungskonto
  bzw. Geldtransit“ ohne Umsatzsteuer zur Prüfung statt Erlös 8400 mit Schlüssel 3
- **Rechnungen ohne Steuerausweis hingen in der Prüfung, § 13b ohne Anmeldung**
  (Gesamttest Eingang B06, Steuer B4): Die Belegerkennung verwarf jede 0-%-Steuerzeile —
  jede Rechnung ohne Umsatzsteuer (§ 13b, § 19, § 4 UStG) ging mit „fehlt:
  Steuerausweis“ zur Prüfung, und es gab keinen Weg zurück. Jetzt zählen eine 0-%-Zeile
  und der Hinweistext („Steuerschuldnerschaft des Leistungsempfängers“, Reverse Charge,
  ig. Lieferung, § 19, steuerfrei nach § 4) als Steuerangabe (§ 14a Abs. 5 UStG verbietet
  bei § 13b den Ausweis) und werden als Steuerkennzeichen am Beleg gespeichert (AE, K, E
  nach UNTDID 5305; bei E-Rechnungen aus den Kategorien). `opos verbuchen` schlägt bei
  einer Eingangsrechnung mit § 13b Schlüssel 94 vor, bei einer ig. Lieferung an uns
  Schlüssel 19 (ig. Erwerb) — jeweils zur Prüfung, bei 7 % `korrigiere … --steuer
  91`/`18`; die Steuer berechnet accounti aus dem Netto. Den Hinweis „USt-IdNr. nicht
  bestätigt“ (er nannte unsere eigene Nummer) gibt es nur noch bei Ausgangsrechnungen.
  Das Land eines Kreditors aus einem PDF kommt aus dem Präfix der USt-IdNr. bzw. der IBAN
  statt immer „DE“ — sonst landete § 13b nie in Kz 46/47 —, ein nur vorgegebenes „DE“
  wird ergänzt; `kontakte bearbeiten --strasse --plz --ort --land` pflegt die Anschrift.
  Neu: **`belege freigeben <ID> [--belegart …] [--steuer 13b|ig-erwerb|steuerfrei|ohne]
  [--belegnummer …] [--vorzeichen umkehren] [--grund …]`** — der Beleg wird nach Prüfung
  des Originals „erfasst“ (Rechnungen nur mit Lieferant und Betrag, verbuchte nie; Recht
  „buchen“, Journal `beleg_freigegeben` mit Person und Grund — nur aus diesem Befehl, ein
  Neulesen durch `belege erkennen` steht als `beleg_geaendert`). Die Ausgabe nennt den
  bisherigen Prüfgrund; `--grund` ist Pflicht bei Dublettenverdacht, Rechenprobe,
  gedrehtem Vorzeichen, `--vorzeichen` und beim Ersetzen einer gelesenen Belegnummer.
  `--steuer` ohne Steuerausweis wird bei Netto ≠ Brutto abgelehnt. `korrigiere --steuer 94/91/19/18` geht auch bei Belegbuchungen
  (die Steuer steht nie auf dem Beleg), jeweils mit `--grund`. Die UStVA warnt bei Aufwand
  ohne Schlüssel gegen einen EU-Kreditor mit USt-IdNr. („§ 13b prüfen“). Saldenliste:
  § 13b und ig. Erwerb mit Steuerpaar (SKR03 1577/1787, 1578/1785, 1574/1774, 1572/1772;
  SKR04 1407/3837, 1408/3835, 1404/3804, 1402/3802), ergebnisneutral; im DATEV-Export ist
  der Umsatz bei BU 94/91/19/18 das Netto (DATEV rechnet die Steuer selbst), nicht Netto
  plus Steuer. Alembic-Migration `46371a6681c2` nach `a14acef69fae`
  (`belege.steuerkennzeichen`; schon per `init_db` angelegt, übernimmt sie die Spalte;
  ohne Versionsvermerk erkennt `db upgrade` den Stand davor an der fehlenden Spalte) —
  **nach dem Update die Datenbank migrieren** (`accounti db upgrade`, siehe
  [Upgrades](docs/betrieb.md#upgrades))
- **Lieferanten-Gutschriften erhöhten Aufwand und Vorsteuer** (Eingang B12): Steuerzeilen
  verloren ihr Vorzeichen (−200/−38 wurde +200/+38, eine Gutschrift über 238 € buchte
  76 € Vorsteuer falsch). Beträge behalten jetzt ihr Vorzeichen, „Gutschriftbetrag“ und
  „Erstattungsbetrag“ gelten als Bruttobetrag, uneinheitliche Vorzeichen bestehen die
  Rechenprobe nicht; ein Korrekturbeleg (Rechnungskorrektur, Stornorechnung, Credit Note,
  Gutschrift) mit positiven Beträgen wird als Minderung übernommen und geht immer zur
  Prüfung (bei „Gutschrift“ mit dem Hinweis auf die Abrechnung des Leistungsempfängers,
  § 14 Abs. 2 S. 2 UStG); als Titel zählt nur eine Zeile aus dem Schlüsselwort mit
  höchstens Nummer, Datum oder Bezug und kein vorheriger Titel „Rechnung“ — ein Satz wie
  „Rechnungskorrektur nur schriftlich innerhalb von 8 Tagen“ macht aus einer Rechnung
  keine Minderung. Ist es doch eine Rechnung: `belege freigeben … --vorzeichen umkehren`.
  „Gutschrift-Nr.“, „Gutschriftsnummer“ und „Credit note no.“ sind Belegnummern. Die
  Verbuchung mindert Aufwand und Vorsteuer (§ 17 Abs. 1 UStG) im Zeitraum des
  Belegdatums der Gutschrift (§ 17 Abs. 1 S. 8 UStG) — auch wenn sie erst später oder im
  Folgejahr eingeht (kein 1548-Weg, kein § 15-Hinweis, kein Befund
  `beleg_nach_zeitraum`); in einem späteren Zeitraum gebucht (festgeschriebener Monat,
  `--buchungsdatum`), geht sie zur Prüfung
- **Belegeingang hing an einer Titelzeile im Spaltenlayout (ReDoS)** (Nachprüfung C,
  H/M-1): Das Muster der Titelerkennung brauchte exponentiell lange, wenn eine Zeile mit
  „Rechnung“/„Gutschrift“ begann und am Ende nicht passte (Spaltenlayout mit 12
  Leerzeichen: 15 s; mit 25 hing `belege import`) — jedes PDF an Postfach oder Webhook
  konnte den Eingang lahmlegen. Die Titelmuster sind jetzt linear (atomare Gruppen,
  possessive Wiederholung, einfache Leerzeichen), eine Titelzeile hat höchstens 120
  Zeichen, und die Belegerkennung kürzt Leerraum vor allen Mustern auf höchstens 20
  Leerzeichen am Stück und eine Leerzeile (an langen Leerraum-Folgen wurden auch
  Belegnummer, Belegdatum, USt-IdNr., Skonto und die Kreditkartenzerlegung
  quadratisch). Als Titel gelten auch „Gutschrift GS-2026-12“, „Credit Note CN-77“,
  „Rechnungskorrektur zu RE-5“ (Nummer ohne „Nr.“, kein Betrag) und eine Seitenzahl in
  der Titelzeile (Nachprüfung C, N-1)
- **Gutschrift mit Rechnungsbezug im Infoblock als Rechnung gebucht** (Nachprüfung C,
  Runde 4, Mittel 1): Seit eine bloße Nummer im Titel zählte, galt die Bezugszeile
  „Rechnung: RE-2026-5“ (ebenso „Rechnung RE-2026-5“, „Rechnung Seite 1“, „Invoice:
  INV-77“) vor dem Titel „Gutschrift“ als Rechnungstitel — die Gutschrift wurde als
  Rechnung mit Vorsteuer erfasst, ohne Prüfung. Steht vor einem Korrekturtitel eine
  Zeile wie ein Rechnungstitel, bleiben die Beträge jetzt wie gedruckt, und der Beleg
  geht mit „Titel mehrdeutig“ zur Prüfung (`belege freigeben` nur mit `--grund`; ist es
  eine Gutschrift: `--vorzeichen umkehren`); die Gutschrift-Nr. geht als Belegnummer vor.
  Das gilt auch für „Rechnung Nr. RE-5“ und „Rechnung vom …“ im Infoblock (vorher schon
  als Rechnung erfasst) und für eine Rechnung mit der Zwischenüberschrift „Gutschrift“
  (vorher erfasst, jetzt zur Prüfung)
- **Belegeingang hing an langen Folgen ohne Leerzeichen** (Nachprüfung C, Runde 4,
  Mittel 2): Die Leerraumgrenze half nicht gegen lange Wörter oder Ziffernfolgen —
  `\w*vertrag`, Beträge, die Belegnummer, `steuerfrei…`, die E-Mail-Maskierung der
  LLM-Stufe und die Suche hinter jedem Summen-Label einer Zeile wurden quadratisch; ein
  komprimiertes PDF von 1,1 KB mit 300 KB Text hielt `belege import` rund 12 min auf,
  der Prüflauf las das Original sogar ohne Leerraumgrenze. Die Muster sind jetzt linear,
  und der Belegtext ist auf 100.000 Zeichen begrenzt: Von einem längeren bleiben Anfang
  und Ende, der Beleg geht mit „Belegtext gekürzt“ zur Prüfung (im Prüflauf als Hinweis)
- **Gutschrift „zur Rechnung Nr. RE-5“ als Dublette verworfen** (Nachprüfung C, M-2):
  Die erste Nummer im Text war die Belegnummer — die Gutschrift trug die Nummer der
  Rechnung, wurde als deren Dublette nicht gespeichert, und die Minderung der Vorsteuer
  fehlte ohne Meldung. Eine Nummer nach „zur/zu/für die/der/zu unserer … Rechnung“ oder
  „Bezug:“ ist ein Bezug, nicht die eigene Nummer; bei einem Korrekturbeleg geht die
  Gutschrift-/Korrekturnummer vor (neu: „Korrektur-Nr.“, „Storno-Nr.“), bei einer
  Rechnung die Rechnungsnummer; ohne eigene Nummer bleibt das Feld leer (zur Prüfung).
  Gleiche Belegnummer desselben Lieferanten mit anderem Bruttobetrag ist nur noch
  Dublettenverdacht (gespeichert, zur Prüfung) statt Dublette
- **Meldungen zu Gutschriften über den Jahreswechsel** (Nachprüfung C, N-2, N-4): Bei
  Bilanzierung nennt die Meldung für eine Gutschrift aus dem Vorjahr nicht mehr den
  1548-Weg der Rechnung, sondern die Minderung im Zeitraum der Änderung (§ 17 Abs. 1
  S. 8 UStG); die Sperrmeldung bietet `--buchungsdatum` nur an, wo es zulässig ist, und
  nur die Werte, die gehen (Runde 4: bei Eingang im Folgejahr nicht mehr „eingang“ und
  „offen“, die beide über den Jahreswechsel geführt hätten). Der
  Hinweis bei einer später gebuchten Gutschrift sagt, dass diese Buchung zu stornieren
  und zum Belegdatum neu zu buchen ist — sonst zählt die Minderung nach der Berichtigung
  der Voranmeldung doppelt
- **Abstimmung Personenkonto ↔ offene Posten nach einer Verrechnung** (Nachprüfung
  Merge, M-1): `pruefen --regel personenkonto_op` und die Abschlussprüfung
  `personenkonten` zählten nur Zahlungen, nicht die Verrechnungen — nach jeder
  Gutschrift mit Bezug (BT-25) und nach `opos verrechnen` stand ein falscher Befund
  „Hauptbuch und Offene-Posten-Liste weichen ab“ mit dem Rat, eine richtige Buchung zu
  korrigieren. Die Abstimmung rechnet jetzt mit der Stichtagsliste (`opos liste
  --stichtag`) selbst; dort zählt ein Posten ab seiner ersten Buchung — eine
  Eingangsrechnung aus einem festgeschriebenen Monat, mit `--buchungsdatum` später
  gebucht, stand vorher zum Monatsende in der Liste, aber nicht auf dem Kreditor
- **Skonto auf § 13b- und Erwerbsrechnungen ohne Steuerkorrektur** (Nachprüfung Merge,
  M-2): Das Skonto einer Rechnung mit Schlüssel 94/91 bzw. 19/18 ging ohne Schlüssel auf
  das Skontokonto — Bemessungsgrundlage, Steuer und Vorsteuer blieben auf dem vollen
  Betrag (600 € mit 2 % Skonto: Kz 84/85/67 = 600/114/114 statt 588/111,72/111,72), still.
  Jetzt mit demselben Schlüssel, die Steuer aus dem Netto (§ 17 Abs. 1 S. 1, 2 UStG), auf
  dem Skontokonto ohne Satz (`skonto_erhalten["0"]`, SKR03 3730). Bei einer gemischten
  Rechnung verteilt sich das Skonto nach dem Zahlbetrag (vorher zählte die selbst
  berechnete Steuer mit, Kz 66 war um Cent zu hoch)
- **Gutschrift mit Bezug an eine neue Anschrift** (Nachprüfung Merge, N-1): Ein
  umgezogener Privatkunde ohne E-Mail bekam für die Gutschrift einen zweiten Debitor, die
  Verrechnung mit der Rechnung fiel still aus (die Rechnung blieb voll offen). Eine
  Gutschrift/Korrektur mit Bezug (BT-25) nimmt jetzt den Debitor der Rechnung, wenn der
  Käufer dort derselbe ist (Name, keine andere USt-IdNr., kein anderes Land), und meldet
  die abweichende Anschrift; nennt sie einen anderen Kunden, sagt der Hinweis, warum
  nicht verrechnet wurde
- **§ 13b-Gutschrift des Lieferanten im festgeschriebenen Monat** (Nachprüfung Merge,
  N-3): Eine Gutschrift ohne Steuerausweis (§ 13b, ig. Erwerb) galt nicht als Minderung —
  die Sperrmeldung bot die Wege einer Rechnung an, `--buchungsdatum offen` begründete die
  Buchung mit § 15. Jetzt wie jede Lieferanten-Gutschrift: Steuer und Vorsteuer mindern
  sich im Zeitraum der Änderung (§ 17 Abs. 1 S. 5, 8 UStG), später gebucht zur Prüfung
- **§ 13b und ig. Erwerb im Eingang zum Zeitpunkt der Steuerentstehung** (Nachprüfung
  Merge, N-4): `opos verbuchen` buchte sie immer zum Rechnungsdatum. Jetzt bucht der
  § 13b-/Erwerbsteil einer Eingangsrechnung bei einer sonstigen Leistung eines
  EU-Unternehmers zum Leistungsdatum, wenn es in einem früheren Monat liegt (§ 13b Abs. 1
  UStG: Ablauf des Voranmeldungszeitraums der Leistung), sonst zum Rechnungsdatum,
  spätestens zum Ende des Folgemonats der Leistung (§ 13b Abs. 2, § 13 Abs. 1 Nr. 6 UStG);
  die Vorsteuer im selben Zeitraum (§ 15 Abs. 1 S. 1 Nr. 3, 4 UStG). Ohne Leistungsdatum
  (bei § 13b Abs. 1), mit Leistung nach dem Rechnungsdatum oder im festgeschriebenen
  Monat bleibt es beim Buchungstag, mit Hinweis
- **`db upgrade` meldete Erfolg, obwohl Spalten fehlten** (Nachprüfung Merge, N-2): Eine
  auf dem Zweig von Paket C mit `alembic upgrade head` migrierte Datenbank (Vermerk
  `46371a6681c2`, ohne `6d38d11fc348`, `2f7c7043043e`, `a14acef69fae`) galt als
  aktuell. Jetzt prüft `db upgrade` das Schema gegen die Tabellen und Spalten des Codes
  (dieselbe Prüfung wie für den Vorabstand von 10b-1, vor und nach dem Lauf) und nennt die
  verlustfreien Wege (`accounti db upgrade --aus-schema` oder von Hand `alembic stamp
  --purge ddc9a184ddb4`, dann noch einmal `accounti db upgrade`;
  [Upgrades](docs/betrieb.md#upgrades))
- **Nachlasszeile machte aus einer § 13b- bzw. Erwerbsrechnung eine Gutschrift**
  (Nachprüfung Runde 2): Jeder Nachlass einer E-Rechnung (BG-20) ist eine negative Zeile
  ohne Steuerausweis — accounti nahm die ganze Rechnung als Lieferanten-Gutschrift. Die
  Umdatierung zum Tag der Steuerentstehung fiel aus (AT-Beratung im Februar mit Rabatt:
  VA 03 statt 02), Sperr- und Jahreswechselmeldung verwiesen auf § 17. Jetzt zählt wie
  bei der Vorsteuer die Summe je Steuerfall: ein Nachlass mindert das Entgelt von
  vornherein (§ 10 Abs. 1 UStG, Abschn. 10.3 UStAE), Gutschrift ist nur ein negatives
  Netto
- **Steuer des Empfängers in einer schon übermittelten Voranmeldung** (Nachprüfung
  Runde 2): Liegt der Tag der Steuerentstehung (§ 13b, ig. Erwerb) in einem Zeitraum,
  dessen Voranmeldung übermittelt ist, nennt `opos verbuchen` die berichtigte
  Voranmeldung — bei vollem Vorsteuerabzug ohne Pflicht nach § 153 Abs. 1 AO, die
  Zahllast ändert sich nicht. Bei der Einnahmenüberschussrechnung bleibt eine Rechnung
  mit Leistung im Vorjahr beim Rechnungsdatum (der Aufwand gehörte sonst in die EÜR des
  Vorjahres, § 11 Abs. 2 EStG), der Hinweis nennt die Voranmeldung, in die Steuer und
  Vorsteuer gehören. Bei abgeschlossenem Leistungsjahr nennt der Hinweis `abschluss
  oeffnen --jahr` statt `periode oeffnen`; ein ig. Erwerb mit Rechnung vor der Lieferung
  und eine grundstücksbezogene Leistung eines EU-Unternehmers (§ 13b Abs. 2 Nr. 1)
  bekommen einen Hinweis
- **PDF-Leistungszeitraum „A - B“ lieferte den Beginn** (Nachprüfung Runde 2): Das
  Leistungsdatum ist jetzt das Ende des Zeitraums (Abschn. 13.1 Abs. 3 UStAE), wie BT-74
  bei der E-Rechnung — die Umdatierung nach § 13b stand sonst einen Monat zu früh
- **Stichtagsliste bei geteilt gebuchten Rechnungen** (Nachprüfung Runde 2): Eine
  gemischte Eingangsrechnung (§ 13b-Teil zum Tag der Steuerentstehung, Rest zum
  Rechnungsdatum) und eine Ausgangsrechnung mit ig. Lieferung und sonstiger Leistung im
  Vormonat zählten in `opos liste --stichtag` ab der ersten Teilbuchung voll —
  `pruefen --regel personenkonto_op` und die Abschlussprüfung `personenkonten` meldeten
  eine Abweichung (auch zum 31.12.) und rieten, eine richtige Buchung zu korrigieren.
  Bis zur letzten Teilbuchung zählt der Posten jetzt nur mit dem gebuchten Teil. Das
  Guthaben eines Altfalls (Überzahlung als Rest 0) rechnet die Stichtagsliste wie die
  Abstimmung mit
- **Verrechnung vor der Buchung eines Postens** (Nachprüfung Runde 2): `opos verrechnen`
  nahm einen Tag zwischen Belegdatum und Buchung einer später gebuchten Rechnung an;
  jetzt frühestens am Tag der ersten Buchung beider Posten
- **Gutschrift mit falschem Bezug bei gleichnamigen Kunden** (Nachprüfung Runde 2): Nannte
  die Gutschrift den einen „Max Müller“ (PLZ, E-Mail bzw. USt-IdNr. eindeutig), der Bezug
  (BT-25) aber die Rechnung des anderen, minderte sie dessen Forderung. Trifft der Käufer
  einen anderen Kontakt genauer, bleibt die Gutschrift jetzt bei ihm, unverrechnet, mit
  Hinweis „Bezug prüfen“
- **DATEV-Export: Skonto mit BU-Schlüssel auf Automatikkonten** (Nachprüfung Runde 2):
  SKR03 3731/3736 (erhaltene Skonti 7 %/19 % Vorsteuer) und 8731/8736 (gewährte Skonti
  7 %/19 % USt) fehlten in `pruefung/skr03.yaml` — der Export setzte BU 8/9 bzw. 2/3 auf
  Konten mit Automatik. Jetzt bleibt das Feld dort leer
- **ZUGFeRD MINIMUM: Steuer verloren, Personenkonto ≠ offener Posten** (Eingang B05): Eine
  Belegposition ohne Steuersatz buchte netto an den Kreditor, der offene Posten stand
  brutto. Ohne Schlüssel wird die Steuer jetzt in den Betrag gebucht (brutto, zur
  Prüfung) — in `opos verbuchen` wie in `classify` mit Beleg, ein gemeinsamer Helfer.
  Ohne Steuerzeile steht die Position „Gesamtbetrag“ brutto, und ein Hinweistext ersetzt
  den Steuerausweis nur bei Netto = Brutto (sonst „fehlt: Steuerausweis“).
  ZUGFeRD MINIMUM und BASIC WL sind keine Rechnung nach § 14 Abs. 4 UStG (BMF 15.10.2024):
  der Beleg geht zur Prüfung (PROFIL), die Steuersätze kommen aus der PDF-Ansicht, wenn
  deren Steuerzeilen zu den Summen des XML passen. `korrigiere --steuer` nimmt einen
  Schlüssel an, wenn der Beleg keinen Satz liefert. Neue Prüfregel `personenkonto_op`
  (Ordnung, Warnung) und Abschlussprüfung `personenkonten`: Saldo jedes Personenkontos
  zum Stichtag gegen die Summe seiner offenen Posten (GoBD Rz. 58 ff., § 239 Abs. 2 HGB)
- **Vorsteuer aus Rechnungen, die erst im Folgejahr eingehen** (Eingang B16): bei
  Bilanzierung (auch ohne Angabe der Gewinnermittlung) bucht `opos verbuchen` Aufwand und
  Verbindlichkeit zum Belegdatum, die Vorsteuer auf „Vorsteuer im Folgejahr abziehbar“
  (SKR03 1548, SKR04 1434) und zum ersten offenen Tag des Eingangsmonats auf das
  Vorsteuerkonto um; die UStVA zählt die Umbuchung als Kz 66 (§ 15 Abs. 1 S. 1 Nr. 1
  UStG, Abschn. 15.2 Abs. 2 S. 7 UStAE) — vorher stand sie ohne Warnung in der alten
  Voranmeldung. Den § 15-Hinweis gibt es auch beim Buchen zum Belegdatum, wenn der Beleg
  erst in einem späteren Monat erfasst wurde (nicht bei § 13b und ig. Erwerb: dort hängt
  der Abzug nicht an der Rechnung; bei Gutschriften der Hinweis auf § 17 Abs. 1 S. 8
  UStG); neuer UStVA-Befund `beleg_nach_zeitraum` (Warnung, nur für den Abzug). „Eingang“
  ist die Erfassung in accounti, nicht der tatsächliche Zugang — Hinweise und Befund sagen
  das; bei offenem Monat verschiebt accounti die Vorsteuer nicht selbst
- **Kontakterkennung: Treffer, die dem Beleg widersprechen** (Eingang B14, Ausgang B1):
  Eine andere USt-IdNr. ist ein anderes Unternehmen — auch bei gleicher IBAN (Factoring,
  Zahlungsdienst) oder gleichem normalisiertem Namen („Atelier Nord SARL“/„SRL“); ein
  anderes Land schließt einen Namenstreffer aus. Gleiche IBAN, anderer Name ohne passende
  USt-IdNr.: Buchung zur Prüfung, aus dem Beleg wird nichts ergänzt. Kunden aus eigenen
  Rechnungen werden mit einem gleichnamigen Debitor nur bei gleicher PLZ oder E-Mail
  zusammengeführt (zwei Privatkunden „Max Müller“ sind zwei Debitoren — Mahnung an die
  richtige Anschrift); wurde ein Kandidat verworfen, geht der neue Kontakt mit Grund zur
  Prüfung. ZM und USt-IdNr.-Prüfung der UStVA nehmen die USt-IdNr. der Rechnung (§ 18a
  Abs. 7 Nr. 1 UStG), die OSS-Kontierung das Land der Rechnung (Lieferanschrift, sonst
  Käufer) und bucht die ausländische Steuer auf das OSS-Steuerkonto, statt sie zu
  verwerfen
- **„Zahlbar ohne Abzug“ nahm das Skonto des Kontakts** (Eingang B09): „ohne Abzug“, „rein
  netto“, „netto Kasse“, „kein Skonto“ heißen jetzt Skonto 0 % am Beleg, und 0 % schlägt
  das Kontakt-Skonto (vorher galt es als „unbekannt“). Zahlungsbedingungen in einer Zeile
  werden je Teilsatz gelesen: „30 Tage ohne Abzug oder 10 Tage mit 2 % Skonto“ ergab
  Skontofrist 30 Tage und kein Zahlungsziel, jetzt 10 Tage und Ziel nach 30
- **Ordner und Handimport kannten die eigene Firma nicht** (Eingang B04): `belege import`
  (neu `--config`) und `belege abholen --kanal ordner` nehmen die eigene Firma aus
  `mandant` wie E-Mail, Webhook und Connector — eine eigene Rechnung wird
  Ausgangsrechnung; `belege erkennen --id <ID>` liest auch einen erfassten, noch nicht
  verbuchten Beleg neu
- **Dateiprüfung im Ordner, Verfahrensdokumentation** (Eingang B03): Der Ordner-Kanal
  prüft Typ (am Inhalt) und Größe aus `belegkanaele` wie E-Mail und Webhook; abgelehnte
  Dateien wandern nach `abgelehnt/` und werden gemeldet. Der Handimport `belege import`
  bleibt ungeprüft (die Datei wählt der Anwender) — die Verfahrensdokumentation sagt das
  jetzt, statt eine Prüfung je Kanal zu behaupten, und ordnet die Befehle richtig zu
  (Ordner `belege abholen --kanal ordner`, Upload `belege import`; vorher vertauscht)
- **Sammelzahlung mit Skonto nur auf einem Teil der Posten** (Eingang B02): wurde nie
  erkannt (Meldung „Beträge gehen nicht auf“, Skonto und Steuerkorrektur fehlten); jetzt
  prüft die Zuordnung jede Teilmenge der skontofähigen Posten (§ 17 Abs. 1 UStG).
  `opos bestaetigen <ID> --skonto BELEGNR=BETRAG` erkennt Skonto von Hand an (gebucht mit
  anteiliger Steuerkorrektur; Zahlung plus Skonto höchstens der Rest des Postens)
- **`--ohne-steuer` bei § 13b und ig. Erwerb** (Schlüssel 18, 19, 91, 94): eigene Meldung und
  Warnung — es entfernt Steuerschuld und Vorsteuer und ist nur richtig, wenn gar kein
  solcher Fall vorliegt; die Abhilfe der Prüfregel schlägt dort nicht mehr „Vorsteuer
  entfernen“ vor, und das Brutto einer Korrektur enthält die selbst berechnete Steuer nicht
  (eine Verbindlichkeit über 100 € wurde zu 119 €). `opos verbuchen --buchungsdatum` mit
  festem Tag nach einem offenen Eingangsmonat warnt, dass die Vorsteuer in den
  Eingangsmonat gehört. Der DATEV-Export warnt bei einem Automatikkonto mit Steuerbetrag,
  aber ohne Schlüssel. Die Anfrage an den Lieferanten ohne `antwort_an` bittet um den Beleg
  „an die Absenderadresse dieser E-Mail“ statt „an uns“
- **`korrigiere` zerstörte Buchungen mit Beleg** (Baustein 7): Die Korrektur einer
  Transaktionsbuchung baute sie aus dem Umsatz neu auf — mit dem ganzen Umsatzbetrag statt
  dem der Buchung und ohne `beleg_id`; Belegbuchungen, Ausgleichs- und Skontobuchungen und
  Splitbuchungen behalten jetzt Beleg, Belegposition, Belegnummer und Betrag
- **Kreditkartenabgleich umging die Jahressperre**: Vorläufige Buchungen wurden per
  Massen-`DELETE` entfernt; jetzt einzeln über die Sitzung (Sperre und Journal greifen)
- **Abschluss – Kontenrahmen SKR03/SKR04:** EÜR-Kennzahlen und Kontoarten gegen die
  DATEV-Kontenrahmen 2026 (Art.-Nr. 11174/11175, dazu 11079/11080 für § 4 Abs. 3 EStG) und
  die Anlage EÜR 2025 mit Anleitung geprüft und berichtigt. SKR04 ordnete 4700–4999
  pauschal Kz 103 zu: Erlösschmälerungen stehen jetzt bei der Kennzahl ihrer Erlöse (19 %
  → 112, steuerfrei → 103, § 19 UStG → 111), Bestandsveränderungen (SKR03 8960–8989,
  SKR04 4800–4819) außerhalb der EÜR, Anlagenverkäufe 4844/4850–4852 bei Kz 102. Außerdem
  u. a.: Kleinunternehmerkonto 2026 ist 8192/4184; Erlöse 0 % USt und Innenumsätze Kz 103;
  Erlöse/Erträge mit 7 %/16 %/19 % USt Kz 112; Forderungsverluste mindern die Erlöse;
  doppelte Haushaltsführung 152, Arbeitszimmer 172/162 (auch dessen AfA), Tagespauschale
  163; Gebäudeversicherung, -reparaturen und Grundsteuer 151; Fremdleistungen,
  Verkaufsprovisionen 110; Abfall 226; Zinsen für Anlagevermögen 232; Kfz-Fahrtkosten des
  Unternehmers 146 und Wege Wohnung–Betriebsstätte 142/176 (DATEV-Dok. 1036862);
  Verpflegungsmehraufwand Unternehmer und doppelte Haushaltsführung 171; nicht abziehbare
  Anteile (sonstige eingeschränkt abziehbare BA, Reisekosten, Werbe-/Repräsentationskosten,
  Steuer-Nebenleistungen § 4 Abs. 5b EStG) 168, abzugsfähige Verspätungszuschläge 183;
  Spenden, kalkulatorische Kosten und Ergebnisverwendung außerhalb der EÜR; SKR04-Konten,
  die der Kontenrahmen 2026 verschoben hat (Reisekosten Unternehmer, Raumkosten, Leasing,
  Ausgleichsabgabe, Gewährleistung). Kontoarten: SKR03 3990–3999 (verrechnete Stoffkosten)
  sind Erfolgskonten; Vorsteuer nach § 15a UStG, aufzuteilende Vorsteuer (SKR03) und die
  Vorsteuer-Gegenkonten § 4 Abs. 3 EStG (SKR04 1480–1482) sowie unberechtigt ausgewiesene
  USt (SKR04 3851) sind Steuerkonten. Nach Gegenprüfung außerdem: Ergebnisanteile aus
  Personengesellschaften (SKR03 2603/2614/2618/4872, SKR04 7003/7004/7008/7208) außerhalb
  der Zeilen 12–75; bis 2025 belegte, 2026 reservierte Konten (8195/8196/8330,
  4185/4186) behalten ihre Kennzahl, außer 8330/4330: accounti hatte 8330 als
  OSS-Erlöskonto vorgeschlagen, es bleibt wie 8320–8329 bei Kz 103, und das Beispiel
  `oss_erloes_ermaessigt` in `config/accounti.example.yaml` nennt jetzt 8328 (8330/4330
  sind 2026 reserviert, 8331/4331 nur für elektronische Dienstleistungen);
  USt-Forderungen (SKR03 1539/1545/1546, SKR04 1420/1422/1425) und Verbindlichkeiten aus
  USt-Vorauszahlungen (1797/3860) wirken bei der EÜR wie die USt-Zahlungskonten
  (Erstattung Zeile 18, Zahlung Zeile 58); USt nicht fällig, OSS-Umsatzsteuer und
  Steuerzahlungen an andere Länder (SKR03 1728/1729/1754/1760–1769/1798, SKR04
  3798/3799/3854) sind in beiden Rahmen Steuerkonten, sodass OSS-Umsatzsteuer und ihre
  Zahlung sich ausgleichen; Umsatzsteuer aus § 13b, ig. Erwerb, Dreiecksgeschäft und
  Auslagerung steht wie ihre Vorsteuer in Zeile 57; Nachsteuer Kz 140, USt laufendes Jahr
  gleicht die Vorauszahlungen in Zeile 58 aus; Konten ohne Steuersatz in SKR03 und SKR04
  einheitlich nach DATEV-Posten; §§ 25/25a „ohne USt“ und abgeschriebene Forderungen
  Kz 112; Sonderbetriebseinnahmen ohne Zeile (Anlage SE); Lizenzen 183;
  Bestandsveränderungen Waren außerhalb der EÜR; Rücklagen nach § 6c/§ 6b, R 6.6, § 4g
  in Zeile 22 (Kz 124) und 59 (Kz 190). Anlage EÜR: Zeilen für Kz 124, 142, 162, 163,
  176 und 190; alle Zeilen 2025 und 2026 gegen die BMF-Vordrucke (29.08.2025,
  01.09.2026) geprüft. Offene Punkte sind in den Zuordnungsdateien mit „prüfen:“
  markiert
- **Abschluss – Kontenrahmen SKR03/SKR04, Konten ohne EÜR-Kennzahl:** Erfolgskonten
  ohne Zeile der Anlage EÜR gegen das Gegenstück im anderen Kontenrahmen und die
  DATEV-Kontenrahmen für § 4 Abs. 3 EStG (11079/11080) geprüft. SKR04: sonstige
  betriebliche Erträge und Aufwendungen 7400–7599 (Restrukturierung, reserviert) Kz 103
  bzw. 183 wie SKR03 2500–2599/2000–2099, reserviert 7900 und SKR03 2900 Kz 183
  (DATEV-Posten „Neutrale Aufwendungen“), Kaufleasing 6250–6259 Kz 222; SKR03
  2800–2839 außerhalb der EÜR wie die übrige Ergebnisverwendung. Außerhalb der EÜR
  stehen auch das Umwandlungsergebnis (Verschmelzung, Umwandlung: SKR03 2004/2504,
  SKR04 7451/7551; weder Zu- noch Abfluss) und die Abschreibungen auf Vorräte (SKR03
  4892/4893, SKR04 6278/6279; die Anschaffungskosten waren schon beim Abfluss
  Betriebsausgabe; bisher Kz 183). Der Abzug nach § 6b EStG (SKR03 4859, 4873/4874,
  SKR04 6249, 7250/7255) steht als Übertragung stiller Reserven in Zeile 59 (Kz 190,
  2026 Zeile 60; bisher GWG Kz 132, Sonderabschreibung Kz 134 bzw. Kz 183).
  Abschreibungen auf Finanzanlagen, Wertpapiere und übriges Umlaufvermögen sowie
  Wertberichtigungen auf Forderungen (SKR03 2440–2459 und 4866–4899, SKR04 6270–6277,
  6290–6299, 6910–6912 und 7200–7299, jeweils ohne die schon genannten Konten und
  4872/7208) haben in beiden Rahmen bewusst keine Zeile: Eine Teilwertabschreibung ist
  in der EÜR nicht zulässig, Anschaffungskosten von Wertpapieren und nicht abnutzbarem
  Anlagevermögen zählen erst bei der Veräußerung. Ebenso die Konten zur freien
  Verfügung (SKR03 4400–4499 wie 5000–6999, SKR04 7800–7899, 8000–8999), deren Zeile
  vom Inhalt abhängt. Sie erscheinen mit Hinweis als „nicht zugeordnet“, der Gewinn
  bleibt unverändert (im SKR03 bisher Kz 183, 4866 sogar GWG Kz 132). Ein Test hält die
  verbleibenden Konten ohne Kennzahl fest. EÜR und Abschlussprüfung nennen für diese Konten den Grund statt
  nur „Zuordnung prüfen“ (z. B. „Teilwertabschreibung in der EÜR nicht zulässig –
  Buchung stornieren“; neuer Schlüssel `hinweis` der EÜR-Regeln), ebenso für § 6b-Abzug,
  Vorräte und Umwandlungsergebnis. Eine eigene Kontenzuordnung
  (`abschluss.kontenzuordnung`) mit unbekanntem Schlüssel wird abgelehnt, statt die
  Angabe still zu verwerfen
- `import bank --format auto` erkennt MT940- und CAMT-Dateien, statt „Bankformat nicht
  erkannt“ zu melden
- `import bank` endet bei einem unlesbaren Auszug mit einer Meldung statt einem Traceback
- **UStVA:** Das Skonto, das der Ausgleich für den 0-%-Anteil einer Mischrechnung (z. B.
  Kz 41 + Kz 81) ohne Steuerschlüssel bucht, sperrte die Freigabe; es wird jetzt der einzigen
  steuerfreien Kennziffer der Rechnung zugeordnet
- `opos verbuchen` bucht EU-Leistungen mit Steuerschuld des Empfängers (Kategorie AE) auf
  8336 statt 8338 (8338 ist im SKR03 „Drittland, nicht steuerbar“); ältere Buchungen auf
  8338/8339 an EU-Unternehmer mit USt-IdNr. meldet die Plausibilisierung als Warnung
- Zahlungsausgleich: ein Posten gegen einen Kontakt mit nur einem Personenkonto (z. B.
  Erstattung des Finanzamts) bucht auf dieses Konto, statt abzubrechen
- DATEV-Steuerschlüssel für ig. Erwerb (19/18) und § 13b (94) in `steuer/umsatzsteuer.py`
- OSS-Meldung und Schwellenprüfung (`steuer/oss.py`) zählten Erstattungen auf OSS-Erlöskonten
  als Umsatz statt als Minderung
- OSS-Meldung (`steuer/oss.py`): Erstattungen früherer Quartale werden als Korrektur des
  Ursprungsquartals ausgewiesen, die CSV lässt negative Zeilen nicht mehr weg, ermäßigte Sätze
  über eigene Erlöskonten, Steuer je Land und Satz aus der Summe der Bemessungsgrundlagen
- **`import bank`** hat dieselbe Datei beim zweiten Import doppelt eingelesen; Umsätze tragen
  jetzt einen Dublettenschlüssel und werden nur einmal gespeichert
- Ein zweiter `accounti classify`-Lauf hat alle Transaktionen erneut gebucht; jetzt werden nur
  Transaktionen ohne Buchung und ohne Zahlungszuordnung kontiert
- Die Belegnummer eines Buchungssatzes wurde nicht gespeichert — der DATEV-Export ließ
  „Belegfeld 1" deshalb leer
