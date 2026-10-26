# Changelog

Alle wesentlichen Änderungen an accounti werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [Unreleased]

### Hinzugefügt
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

### Geändert
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
