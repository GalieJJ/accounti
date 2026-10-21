# Changelog

Alle wesentlichen Änderungen an accounti werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [Unreleased]

### Hinzugefügt
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
