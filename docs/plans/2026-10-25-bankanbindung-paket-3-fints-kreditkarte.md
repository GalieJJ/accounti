# Live-Bankanbindung & Belegabgleich, Paket 3 (FinTS & Kreditkarten) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Nach einmaliger Einrichtung holt `accounti bank abrufen` die Umsätze eines Kontos direkt
bei der Bank über FinTS — ohne weitere Eingabe, abgesehen von der Freigabe, die die Bank selbst
verlangt. Kontoauszüge im Format MT940 und CAMT (camt.052/053/054) werden gelesen, über FinTS wie
aus einem Ordner, und die Bankreferenz fließt in den Dublettenschutz ein. Kreditkarten sind eigene
Bankkonten mit eigenem Sachkonto; ihre Umsätze kommen über einen Provider oder aus der
PDF-Abrechnung, und die Sammelbelastung auf dem Girokonto wird gegen die Summe der Einzelumsätze
abgeglichen — eine Abweichung ist ein Befund, kein gerundeter Rest.

**Spec:** [`docs/specs/2026-08-10-bankanbindung-live.md`](../specs/2026-08-10-bankanbindung-live.md),
Abschnitte 4.1 (Provider `fints`), 4.2 (Zugänge, starke Kundenauthentifizierung), 4.3
(Kreditkarten), 4.6 (CLI), 6 (Teststrategie) · Akzeptanzkriterien 1, 2, 5, 6 ·
**Baut auf:** [Paket 1](2026-10-23-bankanbindung-paket-1-belegabgleich.md),
[Paket 2](2026-10-24-bankanbindung-paket-2-provider.md)

```
                    accounti fints einrichten  (einmalig: PIN, TAN-Verfahren, erste Freigabe)
                                │
Bankkonto (provider fints) ── Tresor: Benutzerkennung, PIN, Sitzung (Kundensystem-ID, BPD/UPD)
   │  accounti bank abrufen / bank lauf  (ohne Rückfrage)
   ▼
bank/fints.py ── python-fints ──▶ FinTS-Server der Bank (Produkt-ID der Installation im HKVVB)
   │   Bank verlangt Freigabe? ─▶ Zustand freigabe_noetig ─▶ accounti fints freigeben (TAN/App)
   │   camt.052 (HKCAZ) bevorzugt, sonst MT940 (HKKAZ)
   ▼
importers/camt.py · importers/mt940.py ── auch für den Datei-Provider und `import bank`
   ▼
Dublettenschutz (+ Bankreferenz: AcctSvcrRef bzw. //Referenz aus :61:)
   ▼
bank lauf: abrufen → Kreditkarten → offene Posten → Belegabgleich → kontieren
                         │
   Kartenkonto (eigenes Sachkonto) ── Umsätze: Provider oder PDF-Abrechnung (Positionssplit)
   Girokonto ── Sammelbelastung ══ Summe der Einzelumsätze?  ja → gebucht · nein → Befund
```

---

## Recherche (Stand 20.10.2026)

| Thema | Ergebnis | Quelle |
|-------|----------|--------|
| python-fints | `fints` 5.0.0 vom 06.01.2026 (5.0.1 vom 09.10.2026 ist jünger als zwei Wochen), LGPL-3.0-or-later, Python ≥ 3.9; „maintained, but with limited capacity“; letzte Commits 30.09. und 09.10.2026; nur FinTS 3.0 mit PIN/TAN | `https://pypi.org/pypi/fints/json`, README im sdist, `api.github.com/repos/raphaelm/python-fints` |
| Abhängigkeiten | bleach 6.4.0 (Apache-2.0), mt-940 5.1.1 (BSD-3), sepaxml 2.7.0 (MIT) → xmlschema 4.3.2, elementpath 5.1.4 (MIT), text-unidecode 1.3 (Artistic/GPL-2+ dual), enum-tools 0.12.0 (LGPL-3.0+) → Pygments (BSD-2), lxml 6.0.4 (BSD-3), requests (Apache-2.0); alle älter als zwei Wochen | PyPI-JSON je Paket |
| lxml-Lücke | CVE-2026-41066: lxml < 6.1.0 liest mit Standardparser (resolve_entities) lokale Dateien aus unvertrautem XML. fints 5.0.0 verlangt `lxml~=6.0.2`, erst 5.0.1 erlaubt 6.1.x. lxml nutzt python-fints nur in `camt_parser.camt053_to_dict` (Rückfall von `get_transactions()`) | Debian Security Tracker, Red-Hat-Advisory; Commit „Loosen lxml pin … CVE-2026-41066“ (30.09.2026) |
| mt-940 5.x | legt mit den Standard-Schlüsseln das Unterfeld ?31 (IBAN) und ?32 (Name) zusammen in `applicant_name` — geprüft mit fints 5.0.0 + mt-940 5.1.1 | eigener Versuch |
| Produktregistrierung | Seit 01.08.2019 bekommen nur registrierte Produkte FinTS-Zugang (auch Bibliotheken und Serveranwendungen); Nummer in der Regel in 10–15 Werktagen; Formular im Original an die DK; die Nummer steht bei **jeder** Dialoginitialisierung im Element „Produktbezeichnung“, die „Produktversion“ ist trotzdem zu belegen | `https://www.fints.org/de/hersteller/produktregistrierung`, python-fints-Doku „Getting started“ |
| Feldlängen HKVVB | Produktbezeichnung an..25, Produktversion an..5 | `fints/segments/auth.py` (HKVVB3) |
| Starke Kundenauthentifizierung | Delegierte VO (EU) 2022/2360 ändert RTS 2018/389, gilt ab 25.07.2023: Ausnahme für Saldo und Umsätze der **letzten 90 Tage**; SCA wieder, wenn seit der letzten SCA mehr als **180 Tage** vergangen sind (direkter Zugriff: Art. 10, über Kontoinformationsdienst: Art. 10a) | EUR-Lex 32022R2360 (über lawplayer.com), Ankündigungen österreichischer Banken |
| Freigabe in python-fints | `with client:` öffnet den Dialog; verlangt die Bank eine TAN, steht sie in `client.init_tan_response`; Antwort mit `client.send_tan(antwort, tan)`; App-Freigabe (decoupled, Code 3955) ohne TAN, `send_tan(antwort, "")` liefert so lange erneut eine Freigabe-Anforderung (3956), bis bestätigt ist; `deconstruct(including_private=True)` sichert Kundensystem-ID, BPD/UPD und TAN-Verfahren, nicht die PIN | Quelltext `fints/client.py`, `fints/dialog.py` 5.0.0 |
| MT940 ist abgelöst | Die DK hat MT940/MT942 im November 2025 aus ihrem Regelwerk genommen; Standard für Kontoinformationen ist camt.052/053 (DFÜ-Abkommen Anlage 3, Version 3.9); Banken dürfen MT940 weiter liefern, jede zu eigenem Termin | DATEV „Kontoumsätze bereitstellen – neues Format“, StarMoney-Hilfe, Volksbank Stuttgart, VR Memmingen |
| FinTS-Formate | HKKAZ liefert MT940, HKCAZ camt (Report camt.052, Formate in HICAZS); python-fints: `get_transactions_xml()` gibt die XML-Dokumente roh zurück | Quelltext `fints/client.py` |
| camt.053 .02 vs. .08 | `.02`: `Ntry/Sts` ist ein Code, Parteien `RltdPties/Dbtr/Nm`; `.08`: `Ntry/Sts/Cd`, Parteien `RltdPties/Dbtr/Pty/Nm`; beide: `Ntry/Amt@Ccy`, `CdtDbtInd` (CRDT/DBIT), `RvslInd`, `BookgDt/Dt|DtTm`, `ValDt`, `AcctSvcrRef`, `NtryDtls/TxDtls/Refs/EndToEndId|MndtId`, `RmtInf/Ustrd|Strd`, `AddtlNtryInf`; Salden `Bal/Tp/CdOrPrtry/Cd` (OPBD, PRCD, CLBD) | XSD `camt.053.001.02.xsd` und `camt.053.001.08.xsd` von iso20022.org |
| MT940 | `:61:` = Valuta JJMMTT, opt. Buchungsdatum MMTT, D/C/RD/RC, opt. dritte Währungsstelle, Betrag mit Komma, Buchungsschlüssel (N + 3), Kundenreferenz (NONREF, wenn keine), `//` Bankreferenz, Zeile 2 Zusatz; `:86:` strukturiert: Geschäftsvorfallcode (3 Ziffern), dann `?00` Buchungstext, `?10` Primanota, `?20`–`?29` und `?60`–`?63` Verwendungszweck (mit SEPA-Schlüsseln `EREF+`, `KREF+`, `MREF+`, `CRED+`, `SVWZ+`, `ABWA+` …), `?30` BLZ/BIC, `?31` Konto/IBAN, `?32`/`?33` Name, `?34` Textschlüsselergänzung | DFÜ-Abkommen Anlage 3 Kap. MT940 (Fachkenntnis), gegengeprüft an mBank „Formatbeschreibung MT940“ (`:61:`, NONREF, `//`), HVB „SEPA-Geschäftsvorfallcodes“ (GVC in ?00-Position), Schlüsseltabelle in mt-940 5.1.1 |
| Geldtransit | SKR03 1360, SKR04 1460 (Verrechnungskonto zwischen eigenen Finanzkonten); für ein Kreditkartenkonto gibt es keine belastbar belegte Standardnummer → Sachkonto bei der Einrichtung Pflicht | Haufe „Kreditkarte/EC-Karte: Zahlungseingänge per Kreditkarte“ |

## Schnitt in Pakete

| Paket | Inhalt | Akzeptanz |
|-------|--------|-----------|
| **A – Formate** | `importers/mt940.py`, `importers/camt.py`, gemeinsames `importers/kontoauszug.py`; Registry-Einträge `mt940`/`camt`, Auto-Erkennung in `import bank`; Datei-Provider liest MT940/CAMT; Bankreferenz im Dublettenschutz | 2, 6 |
| **B – FinTS** | Abschnitt `bank` mit Lader, `bank/fints.py` (Provider `fints`), Freigabe als Zustand oder interaktiv, Sitzungsdaten im Tresor, CLI-Gruppe `fints` (`einrichten`, `freigeben`); Attrappe des Clients und lokale Testbank für den echten python-fints-Client | 1, 2, 5 |
| **C – Kreditkarten** | Modelle, Tabellen, Repository; `bank/kreditkarte.py` (Einrichtung, PDF-Übernahme, Abrechnung, Sammelbelastung, Buchung); Provider `abrechnung`; Schritt im `bank lauf`; CLI-Gruppe `kreditkarte` | Spec 4.3, Teststrategie |

---

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| FinTS-Bibliothek | `fints==5.0.0` als Abhängigkeit, nichts daraus kopiert (auch keine Testdaten); Upgrade auf 5.0.1 frühestens ab 23.10.2026 | einzige gepflegte Python-Implementierung; LGPL-3.0 als eingebundene Bibliothek ist mit MIT vereinbar, solange ihr Code nicht im Repo landet; 5.0.1 ist jünger als zwei Wochen |
| lxml < 6.1 | hingenommen bis zum Upgrade: accounti ruft `get_transactions()`/`camt053_to_dict` nie auf, CAMT liest der eigene Parser mit der Standardbibliothek und lehnt DTD/Entities ab | CVE-2026-41066 betrifft nur Parser mit `resolve_entities`; der lxml-Pfad von python-fints wird nicht betreten |
| Umsätze holen | camt über `get_transactions_xml()` (öffentlich), wenn die Bank HKCAZ anbietet; sonst MT940 **roh** über eine dünne Unterklasse (`_fetch_with_touchdowns` mit eigener Antwortverarbeitung) und eigenen Parser; Einstellung `format` = auto/camt/mt940 | DK-Standard ist seit 11/2025 camt; mt-940 5.x vermischt IBAN und Name; ein Parser für FinTS und Dateien; die Nutzung interner API ist durch die Testbank mit dem echten Client abgesichert |
| Produkt-ID | Reihenfolge: Einstellung `produkt_id` am Konto → `ACCOUNTI_FINTS_PRODUKT_ID` → `bank.fints.produkt_id` (auch `${VAR}`); fehlt sie, scheitert der Abruf mit Hinweis auf die Registrierung; höchstens 25 Zeichen, Produktversion höchstens 5 | je Installation registriert, nie im Repo; HKVVB-Feldlängen |
| Zugangsdaten | `geheime_felder` = Benutzerkennung, PIN (Tresor); dazu die Sitzung (`deconstruct(including_private=True)`) ebenfalls verschlüsselt im Zugang; der Provider gibt sie über `Abruf.zugang` bzw. `FreigabeNoetigError.zugang` zurück, `rufe_ab` verschlüsselt neu | die Bank bindet die 180-Tage-Ausnahme an die Kundensystem-ID — ohne gesicherte Sitzung fragte sie bei jedem Abruf nach einer TAN; Akzeptanz 5 |
| Freigabe | `BankProvider(freigabe=…)`: ohne Rückfrage (`bank abrufen`, `bank lauf`, Cron) wird `FreigabeNoetigError` zum Zustand `freigabe_noetig` mit dem Hinweis `accounti fints freigeben`; mit Rückfrage (`fints einrichten`, `fints freigeben`) fragt die CLI nach der TAN bzw. wartet auf die App (Statusabfrage im Abstand `freigabe_intervall_sekunden`, höchstens `freigabe_wartezeit_sekunden`) | Spec 4.2 und 5: als Zustand gemeldet; ein Cron-Lauf darf nie auf eine Eingabe warten; Baustein 8 macht aus dem Zustand eine Aufgabe |
| PIN falsch / gesperrt | `ProviderError` ohne Wiederholung; die Meldung enthält nie Zugangsdaten | python-fints sperrt die PIN nach 9xxx-Antworten; jeder weitere Versuch kann den Zugang sperren |
| Erster Abruf | ohne Abrufstand ab heute minus `erster_abruf_tage` (Standard 90) | Umsätze der letzten 90 Tage fallen unter die SCA-Ausnahme |
| TAN-Verfahren | `fints einrichten` fragt die Verfahren der Bank ab und lässt wählen (Einstellung `tan_verfahren`, ggf. `tan_medium`); ohne Einstellung wählt python-fints das erste zweistufige Verfahren | eine Wahl, die der Mensch einmal trifft, statt bei jedem Lauf |
| MT940-Parser | Standardbibliothek; `@@` als Zeilenumbruch; Buchungsdatum (sonst Valuta) als Datum; D/RC negativ, C/RD positiv; Verwendungszweck = `SVWZ+` (sonst der ganze Text) plus `EREF` als Referenz; Name aus ?32+?33, IBAN aus ?31; Saldenprobe je Auszug (Anfangssaldo + Umsätze = Endsaldo), sonst Fehler | ein Auszug, der nicht aufgeht, ist unvollständig — Fehler statt stiller Lücke |
| CAMT-Parser | camt.052/053/054, Versionen .02 und .08 namensraumunabhängig; nur gebuchte Einträge (BOOK); Vorzeichen aus `CdtDbtInd`; Gegenpartei bei Gutschrift `Dbtr`, bei Belastung `Cdtr`; eine Transaktion je `Ntry` (Sammler: Verwendungszwecke zusammengefasst); DTD/Entity abgelehnt; Saldenprobe, wenn Anfangs- (OPBD/PRCD) und Endsaldo (CLBD) da sind | Vormerkposten sind keine Buchungen; die Kontozeile ist die Buchung |
| Fremde Konten | Auszüge, deren Konto (IBAN oder BLZ/Kontonummer) nicht zum Bankkonto passt, überspringt der Datei-Provider | ein Ordner mit Auszügen mehrerer Konten ordnet nichts falsch zu |
| Bankreferenz | `Transaktion.quelle_referenz`; fließt nur ein, wenn vorhanden (NONREF/NOTPROVIDED zählen nicht) → bestehende Schlüssel bleiben gleich | Spec 5: „Dublettenschutz über Bank-Referenz“; zwei gleich aussehende Umsätze mit verschiedener Referenz bleiben zwei, unabhängig von der Reihenfolge |
| Datei-Provider | MT940/CAMT werden am Inhalt erkannt (`.sta`, `.mt940`, `.940`, `.txt`, `.xml`), `format` gilt nur für CSV; Saldo des letzten Auszugs wird gemeldet | Fallback bleibt vollständig (Akzeptanz 6) |
| `import bank` | `--format mt940|camt`, `auto` erkennt beide am Inhalt vor den CSV-Profilen | eine Stelle für alle Dateiformate |
| Kreditkarte | eigenes Bankkonto (Kennung statt IBAN, z.B. `VISA1234`, eigenes Sachkonto als Pflichtangabe) plus Eintrag in `kreditkarten`: Girokonto, Muster der Sammelbelastung, Endziffern, Abrechnungstag | Vorgabe des Auftrags; die Kartennummer selbst wird nie gespeichert |
| Kartenumsätze | Provider `abrechnung` (PDF über die Belegerfassung, `kreditkarte uebernehmen BELEG`) oder jeder andere Provider (`datei`, `fints`); Übernahme mit Dublettenschutz am Kartenkonto | Spec 4.3: Provider oder PDF; der PDF-Weg nutzt den vorhandenen Positionssplit |
| Ausgleichszeilen | positive Zeilen mit „Zahlung/Ausgleich/Lastschrift/…“ (`ausgleich_muster`) sind die Begleichung der Vorperiode, kein Einzelumsatz | sonst stimmte keine Summe |
| Abrechnung | PDF: Positionen des Belegs, Stichtag = Belegdatum; Provider: Umsätze nach dem letzten Stichtag bis zum Stichtag (Abrechnungstag des Monats oder `kreditkarte abrechnen --stichtag`); jeder Umsatz gehört höchstens zu einer Abrechnung | eindeutiger Abrechnungszeitraum |
| Sammelbelastung | Girokonto-Umsatz < 0, Muster (und Endziffern, falls gesetzt) im Text, 0–`belastung_fenster_tage` (30) nach dem Stichtag. Betrag = Summe → abgeglichen; sonst **Befund** mit centgenauer Differenz; mehrere Kandidaten → keine Zuordnung, Hinweis | Spec 4.3; „streng vor großzügig“ |
| Buchung | PDF-Karte: Sammelbelastung „Kreditkarte an Bank“; Karte mit Abruf: Sammelbelastung „Geldtransit an Bank“, Ausgleichszeile „Kreditkarte an Geldtransit“ (SKR03 1360, SKR04 1460, `geldtransit_konto`). Abgeglichen → automatisch (Confidence 1,0), Abweichung → zur Prüfung mit voller Belastung; nie eine Buchung über die Differenz | jede Kontozeile wird genau einmal auf ihrem Finanzkonto gebucht; `classify` fasst gebuchte Umsätze nicht an; die Einzelumsätze kontiert `classify` gegen das Kartenkonto |
| Lauf | `bank lauf`: abrufen → **Kreditkarten** → offene Posten → Belegabgleich → kontieren | die Sammelbelastung darf weder als offener Posten noch per Regelwerk gebucht werden |
| Konfiguration | Abschnitt `bank` (Unterabschnitte `fints`, `kreditkarte`) mit eigenem Lader `bank/einstellungen.py`, alles mit Standardwerten | Muster `lade_buchhaltung`; ohne Abschnitt lauffähig |
| CLI | neue Gruppen `fints` (`einrichten`, `freigeben`) und `kreditkarte` (`einrichten`, `liste`, `uebernehmen`, `abrechnen`, `abgleich`) in `befehle/`; `cli.py` bleibt unverändert; `bank verbinde --provider fints` funktioniert ebenfalls | Dateiregeln; die Gruppe `bank` gehört `cli.py` |
| Tests | nie gegen eine echte Bank: Attrappe des python-fints-Clients (Szenarien: Freigabe bei der Initialisierung, App-Freigabe, TAN beim Abruf, PIN falsch, Verbindung weg) **und** eine lokale Testbank (HTTP auf 127.0.0.1) mit selbst geschriebenen FinTS-Antworten für den echten Client; Kontoauszüge als aufgezeichnete Beispieldateien in `tests/daten/bank/` | Spec 6 |

## Aufgaben

### Paket A – Formate

- [ ] **MT940** (`importers/mt940.py`): `:61:` (Valuta/Buchungsdatum, Jahreswechsel, C/D/RC/RD, Bankreferenz, NONREF), `:86:` strukturiert und unstrukturiert, SEPA-Schlüssel, `@@`, mehrere Auszüge, Saldenprobe, Kontokennung (`tests/test_bank_mt940.py`).
- [ ] **CAMT** (`importers/camt.py`): 052/053/054 in .02 und .08, Vorzeichen, Status, Storno, Gegenpartei, Referenzen, Sammler, Saldenprobe, DTD abgelehnt (`tests/test_bank_camt.py`).
- [ ] **Gemeinsam** (`importers/kontoauszug.py`): Formaterkennung, Kontozuordnung (IBAN, BLZ/Konto), Registry `mt940`/`camt`, `waehle_importer(…, "auto")` erkennt beide.
- [ ] **Dublettenschutz mit Bankreferenz** (`bank/dubletten.py`): ohne Referenz unveränderter Schlüssel; verschiedene Referenzen unabhängig von der Reihenfolge; Wiederholung → keine Dublette (`tests/test_bank_dubletten.py`).
- [ ] **Datei-Provider** liest MT940/CAMT, überspringt fremde Konten und Notizen, meldet den Saldo; `import bank` mit MT940/CAMT und zweimal importiert → nichts doppelt (Akzeptanz 2, 6) (`tests/test_bank_provider.py`, `tests/test_cli_bank_formate.py`).

### Paket B – FinTS

- [ ] **Abhängigkeit** `fints==5.0.0` in `pyproject.toml`, mypy-Ausnahme für das untypisierte Paket.
- [ ] **Einstellungen** (`bank/einstellungen.py`): Abschnitt `bank`, Standardwerte, `${VAR}`, `ACCOUNTI_FINTS_PRODUKT_ID`, Fehlertexte (`tests/test_bank_einstellungen.py`).
- [ ] **Provider-Schnittstelle**: `Freigabeanfrage`, `BankProvider(freigabe=…)`, `Abruf.zugang`, `FreigabeNoetigError.zugang`; `rufe_ab(…, freigabe=…)` verschlüsselt geänderte Zugänge neu (`tests/test_bank_lauf.py`).
- [ ] **Provider `fints`** (`bank/fints.py`) gegen die Attrappe: Produkt-ID (fehlt, Reihenfolge, Länge), Konto über IBAN, camt/MT940, Zeitraum, Saldo, Sitzung, Freigabe bei Initialisierung und Abruf (TAN, App mit Statusabfrage, Abbruch, Zeitüberschreitung, ohne Rückfrage → Zustand), PIN falsch, Verbindung weg, TAN-Verfahren (`tests/test_bank_fints.py`).
- [ ] **Einrichtung** (`richte_fints_ein`): TAN-Verfahren und -Medium wählen, erste Freigabe, Konto bei der Bank vorhanden.
- [ ] **CLI** `fints einrichten|freigeben` (`befehle/fints.py`); **Akzeptanz 1** mit der Attrappe: einrichten (TAN) → `bank abrufen` zweimal ohne Eingabe → Bank verlangt Freigabe → Zustand, `fints freigeben` → weiter (`tests/test_cli_fints.py`).
- [ ] **Akzeptanz 5** für FinTS: weder PIN noch Benutzerkennung noch Sitzung im Klartext in der Datenbank.
- [ ] **Testbank** (`tests/fints_testbank.py`): echter python-fints-Client gegen lokale HTTP-Testbank — Produkt-ID im HKVVB, Freigabe bei der Initialisierung, MT940 mit Aufsetzpunkt, camt, zweiter Abruf mit gesicherter Sitzung ohne neue Kundensystem-ID und ohne TAN (`tests/test_bank_fints_testbank.py`).

### Paket C – Kreditkarten

- [ ] **Modelle und Persistenz**: `models/bank.py`, `db/tabellen_bank.py` (`kreditkarten`, `kreditkartenabrechnungen`, `kreditkartenumsaetze`), `db/repo_bank.py` (`tests/test_bank_kreditkarte_repo.py`).
- [ ] **Einrichtung und Provider `abrechnung`**: Karte als Bankkonto mit eigenem Sachkonto, Girokonto muss existieren, vorhandenes Konto als Karte markieren.
- [ ] **PDF-Übernahme**: Positionen des Belegs → Umsätze am Kartenkonto (Dublettenschutz), Ausgleichszeilen ausgenommen, Abrechnung mit Summe; zweimal → Fehler; Abweichung der Positionen vom Abrechnungsbetrag → Befund.
- [ ] **Abrechnung aus Provider-Umsätzen** (Stichtag, Abrechnungstag).
- [ ] **Sammelbelastung**: gleich → abgeglichen und gebucht; 1 Cent Differenz → Befund, zur Prüfung, keine Rundungsbuchung; mehrdeutig → nichts; ohne Abrechnung → Hinweis; Geldtransit für Karten mit Abruf inkl. Ausgleichszeile; idempotent (`tests/test_bank_kreditkarte.py`).
- [ ] **Lauf**: Schritt im `bank lauf` vor den offenen Posten; `classify` bucht die Einzelumsätze gegen das Kartenkonto.
- [ ] **CLI** `kreditkarte einrichten|liste|uebernehmen|abrechnen|abgleich` (`tests/test_cli_kreditkarte.py`).

### Abschluss

- [ ] `pytest`, `ruff check`, `ruff format --check` (ohne Cache), `mypy` grün; Plan abgehakt; Doku-Bausteine unten aktuell.

## Grenzen

- **Keine echte Bank geprüft.** Getestet ist gegen eine Attrappe des python-fints-Clients und eine
  selbst geschriebene lokale Testbank; jede Bank setzt FinTS etwas anders um (TAN-Verfahren,
  Pflicht zur TAN beim Abruf, Formate). Der erste echte Abruf ist ein Probelauf.
- **Produktregistrierung nötig.** Ohne eigene Produkt-ID der DK (10–15 Werktage) kein Abruf; die
  Nummer gehört der jeweiligen Installation und steht nie im Repo.
- **TAN-Verfahren:** unterstützt sind Verfahren mit TAN-Eingabe (z.B. SMS, chipTAN manuell) und
  App-Freigabe (pushTAN/decoupled). Flickercode (chipTAN optisch) und photoTAN-Grafik kann die
  Konsole nicht anzeigen — die CLI weist darauf hin.
- **Aufgabe statt Zustand:** Der Lauf setzt den Zustand `freigabe_noetig`; eine Aufgabe daraus
  erzeugt Baustein 8 (in Arbeit), nicht dieses Paket.
- **Unbeaufsichtigter Abruf heißt: PIN im Tresor.** Sie liegt verschlüsselt mit dem Schlüssel aus
  `ACCOUNTI_SCHLUESSEL`; wer Datenbank **und** Schlüssel hat, hat den Zugang.
- **python-fints 5.0.0 und lxml < 6.1 (CVE-2026-41066).** accounti betritt den betroffenen Pfad
  nicht, das Paket liegt aber in der Umgebung; Upgrade auf fints 5.0.1 mit lxml ≥ 6.1 ab
  23.10.2026 nachziehen. Der MT940-Abruf nutzt interne Methoden von python-fints
  (`_fetch_with_touchdowns`, `_find_highest_supported_command`); bei jedem Upgrade muss die
  Testbank grün bleiben. Ab 5.0.1 verpackt python-fints Verbindungsfehler selbst; 5.0.0 lässt
  `requests`-Fehler durch — accounti fängt beide.
- **Kreditkarten per FinTS (DKKKU)** werden nicht abgefragt (in python-fints „reverse engineered,
  probably wrong“); Karten kommen per PDF, Datei (CSV/MT940/CAMT) oder später PSD2. Der
  PSD2-Provider ist nicht Teil dieses Pakets.
- **PDF-Abrechnungen** nutzen die vorhandene Zeilenerkennung aus Baustein 2 (Zeilen, die mit
  einem Datum beginnen). Zeilen ohne Datum, Fremdwährungsangaben und mehrzeilige Umsätze
  erkennt sie nicht — die Abweichung zwischen Positionen und Abrechnungsbetrag wird dann zum
  Befund, nicht still übernommen.
- **Abrechnungszeitraum bei Abruf-Karten** nur über einen monatlichen Abrechnungstag oder von
  Hand (`kreditkarte abrechnen`); Wochen- oder Sonderrhythmen nicht.
- **Sammelbuchungen** (mehrere `TxDtls` in einem `Ntry`, MT940-Sammler) werden eine Transaktion
  mit zusammengefasstem Verwendungszweck, nicht in Einzelzahlungen zerlegt.
- **Vormerkposten** (camt `PDNG`, MT942) werden nicht übernommen.
- **Bankreferenz** steht nur im Dublettenschlüssel und im Rohtext, nicht in einer eigenen
  Spalte — das bräuchte eine Migration der Tabelle `transaktionen`.
- **Gemischte Quellen** für dasselbe Konto (erst CSV, dann FinTS) erkennt der Dublettenschutz nur
  bei gleichem Inhalt; der Verwendungszweck sieht je Format anders aus.
- **`classify` allein** (ohne `bank lauf` oder `kreditkarte abgleich` davor) kann eine
  Sammelbelastung per Regelwerk buchen; der Kartenabgleich meldet sie danach als „schon
  gebucht“, statt sie umzubuchen.
- **Hilfetext** von `bank verbinde` nennt `fints` noch als „später“ (steht in `cli.py`, das dieses
  Paket nicht ändert).

## Doku-Bausteine

### README — Zeile in der Feature-Tabelle „Buchen & Zahlen“

```markdown
| ✅ | **Live-Bankanbindung** | Bankkonten mit verschlüsselten Zugängen, FinTS-Direktabruf (python-fints, eigene Produkt-ID, TAN/App-Freigabe als Zustand oder interaktiv), Datei-Provider, MT940 und CAMT (camt.052/053/054) mit Bankreferenz im Dublettenschutz, Kreditkarten als eigene Konten mit Abgleich der Sammelbelastung, geplanter Lauf `bank lauf`; PSD2 folgt |
```

### README — Nutzungsblock (nach „Bankkonten und geplanter Lauf“)

````markdown
### FinTS und Kreditkarten

FinTS braucht eine **Produkt-ID**, die jede Installation selbst bei der Deutschen Kreditwirtschaft
registriert (https://www.fints.org/de/hersteller/produktregistrierung, 10–15 Werktage). Sie gehört
in die Umgebung oder in `config/accounti.yaml`, nie ins Repo.

```bash
export ACCOUNTI_FINTS_PRODUKT_ID=…             # oder bank.fints.produkt_id
accounti fints einrichten --iban DE12… --bezeichnung "Giro Sparkasse" \
  --blz 12345678 --server https://fints.example-bank.de/fints30
                                               # Benutzerkennung, PIN, TAN-Verfahren, erste Freigabe
accounti bank abrufen                          # danach ohne Eingabe (Cron); verlangt die Bank
                                               # wieder eine Freigabe, steht das Konto auf
                                               # freigabe_noetig:
accounti fints freigeben                       # TAN eingeben oder in der App bestätigen

accounti import bank auszug.sta                # MT940 und CAMT werden am Inhalt erkannt
accounti import bank camt053.xml --konto DE12…

accounti kreditkarte einrichten --kennung VISA1234 --bezeichnung "Visa Firma" \
  --sachkonto 1730 --girokonto DE12… --endziffern 1234
accounti belege import abrechnung-maerz.pdf    # PDF-Abrechnung wird in Umsätze zerlegt …
accounti kreditkarte uebernehmen <BELEG-ID>    # … und landet am Kartenkonto
accounti kreditkarte abgleich                  # Sammelbelastung ./. Summe der Einzelumsätze
accounti kreditkarte liste                     # Karten, Abrechnungen, Befunde
```

Stimmt die Sammelbelastung auf dem Girokonto nicht centgenau mit der Summe der Einzelumsätze
überein, bucht accounti sie zur Prüfung und nennt die Differenz als Befund — es gibt keinen
Rundungsposten. `accounti bank lauf` erledigt den Kartenabgleich vor dem Kontieren selbst.
````

### README — Roadmap v0.3

```markdown
- [x] Live-Bankanbindung: FinTS/HBCI, Kreditkarten (PSD2 optional folgt)
- [x] FinTS-Provider und Kreditkarten (FinTS braucht eine Produktregistrierung)
```

### CHANGELOG

```markdown
### Hinzugefügt
- **Live-Bankanbindung, Paket 3 – FinTS & Kreditkarten** (Baustein 5): Provider `fints` über
  python-fints — Produkt-ID je Installation (`ACCOUNTI_FINTS_PRODUKT_ID` oder `bank.fints`),
  Benutzerkennung, PIN und Sitzung (Kundensystem-ID) verschlüsselt im Tresor, camt.052
  bevorzugt, sonst MT940; verlangt die Bank eine Freigabe, setzt `bank abrufen` den Zustand
  `freigabe_noetig`, `accounti fints freigeben` fragt nach der TAN oder wartet auf die App;
  `accounti fints einrichten` wählt das TAN-Verfahren und erledigt die erste Freigabe.
  Kontoauszüge im Format MT940 und CAMT (camt.052/053/054, .02 und .08) für `import bank`, den
  Datei-Provider und FinTS, mit Saldenprobe. Kreditkarten als eigene Bankkonten mit eigenem
  Sachkonto (`accounti kreditkarte einrichten|liste|uebernehmen|abrechnen|abgleich`): Umsätze aus
  PDF-Abrechnungen oder per Provider, Sammelbelastung auf dem Girokonto gegen die Summe der
  Einzelumsätze — Abweichung ist ein Befund, keine Rundungsbuchung; Geldtransit für Karten mit
  Abruf. Neuer, optionaler Abschnitt `bank`. Neue Abhängigkeit `fints` 5.0.0 (LGPL-3.0-or-later)

### Geändert
- **Dublettenschutz** bezieht die Bankreferenz ein (camt `AcctSvcrRef`, MT940 `//Referenz`), wo
  vorhanden; Schlüssel ohne Referenz bleiben unverändert
- **Datei-Provider** liest neben CSV auch MT940 und CAMT, überspringt Auszüge fremder Konten und
  meldet den Saldo
- **`bank lauf`** gleicht vor den offenen Posten die Kreditkarten ab
- **Provider-Schnittstelle:** Rückfrage für Freigaben (`freigabe`), aktualisierte Zugänge
  (`Abruf.zugang`) werden neu verschlüsselt

### Behoben
- `import bank --format auto` erkennt MT940- und CAMT-Dateien, statt „Bankformat nicht
  erkannt“ zu melden
```

### docs/bauplan.md — Absatz zu Baustein 5 (ersetzt den bisherigen) und Statuszeile

```markdown
| 5 | Live-Bankanbindung & Belegabgleich | `bank/` | ✅ fertig | [Spec](specs/2026-08-10-bankanbindung-live.md) |
```

```markdown
**Baustein 5 ist fertig:** Belegabgleich vor der Kontierung
([Paket 1](plans/2026-10-23-bankanbindung-paket-1-belegabgleich.md)), Bankkonten mit
verschlüsselten Zugängen, Provider-Schnittstelle, Datei-Provider, Dublettenschutz und geplanter
Lauf ([Paket 2](plans/2026-10-24-bankanbindung-paket-2-provider.md)) sowie FinTS mit Freigabe als
Zustand, MT940/CAMT und Kreditkarten mit Abgleich der Sammelbelastung
([Paket 3](plans/2026-10-25-bankanbindung-paket-3-fints-kreditkarte.md)). FinTS braucht je
Installation eine Produktregistrierung bei der Deutschen Kreditwirtschaft (10–15 Werktage).
Offen als Erweiterung: der PSD2-Provider (opt-in) und Kreditkarten per FinTS.
```

### docs/architektur.md — Abschnitt `bank/` (ergänzt die Liste) und `importers/`

```markdown
- `fints.py` — Provider `fints` über python-fints (FinTS 3.0, PIN/TAN). Produkt-ID der
  Installation (Konto-Einstellung → `ACCOUNTI_FINTS_PRODUKT_ID` → `bank.fints.produkt_id`), Konto
  über die IBAN aus HKSPA, Umsätze als camt.052 (HKCAZ) oder MT940 (HKKAZ, roh) durch die eigenen
  Parser. Die Sitzung (Kundensystem-ID, BPD/UPD, TAN-Verfahren) liegt verschlüsselt im Zugang,
  sonst verlöre die Bank die 180-Tage-Ausnahme. Freigaben: ohne Rückfrage `FreigabeNoetigError`
  (Zustand `freigabe_noetig`), mit Rückfrage TAN-Eingabe bzw. Statusabfrage für die App.
  `richte_fints_ein` wählt TAN-Verfahren und -Medium. *(vorhanden)*
- `einstellungen.py` — Abschnitt `bank` (`fints`, `kreditkarte`) mit Standardwerten. *(vorhanden)*
- `kreditkarte.py` — Kreditkarte = eigenes Bankkonto mit eigenem Sachkonto plus Tabelle
  `kreditkarten` (Girokonto, Muster, Endziffern, Abrechnungstag). Umsätze per Provider oder aus
  der PDF-Abrechnung (Positionssplit aus `belege/`, Provider `abrechnung`); Abrechnungen
  (`kreditkartenabrechnungen`, `kreditkartenumsaetze`) mit Summe der Einzelumsätze; die
  Sammelbelastung auf dem Girokonto wird centgenau dagegen geprüft — Abweichung = Befund und
  Buchung zur Prüfung, nie ein Rundungsposten. Gebucht wird „Kreditkarte an Bank“ (PDF-Karten)
  bzw. über Geldtransit (Karten mit Abruf). Läuft in `bank lauf` vor den offenen Posten.
  *(vorhanden)*
- `dubletten.py` — … bezieht die Bankreferenz (camt `AcctSvcrRef`, MT940 `//Referenz`) ein,
  wo vorhanden. *(vorhanden)*
```

```markdown
- `mt940.py` — SWIFT MT940 nach DK-Belegung (`:61:`, `:86:` mit ?00/?20–?29/?30–?34/?60–?63,
  SEPA-Schlüssel), Saldenprobe je Auszug. *(vorhanden)*
- `camt.py` — camt.052/053/054 (.02 und .08), nur gebuchte Einträge, Bankreferenz, DTD/Entities
  abgelehnt, Saldenprobe. *(vorhanden)*
- `kontoauszug.py` — gemeinsames `Auszug`-Modell, Formaterkennung am Inhalt, Kontozuordnung
  (IBAN oder BLZ/Kontonummer). Registry-Einträge `mt940` und `camt`; `--format auto` erkennt sie
  vor den CSV-Profilen. *(vorhanden)*
```

### config/accounti.example.yaml — neuer Abschnitt

```yaml
# Live-Bankanbindung (optional — ohne diesen Abschnitt gelten die Standards)
bank:
  fints:
    # Produkt-ID der eigenen Registrierung bei der Deutschen Kreditwirtschaft —
    # nie ins Repo; alternativ ACCOUNTI_FINTS_PRODUKT_ID oder Einstellung am Konto
    produkt_id: "${ACCOUNTI_FINTS_PRODUKT_ID}"
    produkt_version: "0.1"       # höchstens 5 Zeichen
    erster_abruf_tage: 90        # erster Abruf ohne Stand: so weit zurück (SCA-Ausnahme: 90 Tage)
    freigabe_wartezeit_sekunden: 300   # so lange auf die Freigabe in der App warten
    freigabe_intervall_sekunden: 3     # Abstand der Statusabfragen
  kreditkarte:
    geldtransit_konto: "1360"    # SKR04: 1460; leer = nach buchhaltung.kontenrahmen
    belastung_fenster_tage: 30   # Sammelbelastung so viele Tage nach dem Abrechnungsstichtag
    # belastung_muster: "kreditkart|kartenabrechnung|visa|master ?card|american express|amex"
    # ausgleich_muster: "zahlung|ausgleich|lastschrift|einzug|begleich|abbuchung"
```
