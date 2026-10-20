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
| Zeitlimit | python-fints sendet über `requests.Session.post` ohne `timeout` — eine hängende Gegenstelle blockiert unbegrenzt | Quelltext `fints/connection.py` 5.0.0 |
| Geldtransit | SKR03 1360, SKR04 1460 (Verrechnungskonto zwischen eigenen Finanzkonten) | Haufe „Kreditkarte/EC-Karte: Zahlungseingänge per Kreditkarte“ |
| Kreditkartenkonto | Die DATEV-Kontenrahmen führen „Kreditkartenabrechnung“ als SKR03 1730 bzw. SKR04 3610 (Verbindlichkeiten). Das Sachkonto bleibt bei der Einrichtung Pflicht (mit der Steuerberatung abstimmen); die Hilfe von `kreditkarte einrichten` nennt beide als Vorschlag | Kontenrahmen-Übersichten SKR03/SKR04 (Kontobezeichnung), Prüfbefund Runde 1 |

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
| Format bleibt fest | `auto` wird bei `fints einrichten` bzw. beim ersten Abruf zu camt oder mt940 aufgelöst und im Zugang gemerkt (`abrufformat`); bietet die Bank später camt an, bleibt der Abruf bei MT940. Ein Wechsel nur ausdrücklich (`accounti fints format --konto … camt`), dann ohne Überlappung: ab dem Tag nach dem Abrufstand (`format_ab` im Zugang, bleibt). Fällt camt bei `auto` weg → Fehler mit diesem Hinweis statt stillem Wechsel | MT940 liefert oft keine Bankreferenz und kürzt den Namen — derselbe Umsatz bekäme im Überlappungszeitraum andere Schlüssel (Akzeptanz 2); Banken stellen gerade um (Recherche) |
| Nur https | FinTS-Adresse muss `https://` sein, Ausnahme `http` zu 127.0.0.1/localhost/::1 (Testbank); geprüft vor der PIN-Abfrage und im Provider | sonst gingen Benutzerkennung und PIN im Klartext über das Netz; python-fints prüft das Schema nicht |
| Produkt-ID | Reihenfolge: Einstellung `produkt_id` am Konto → `ACCOUNTI_FINTS_PRODUKT_ID` → `bank.fints.produkt_id` (auch `${VAR}`); fehlt sie, scheitert der Abruf mit Hinweis auf die Registrierung; höchstens 25 Zeichen, Produktversion höchstens 5 | je Installation registriert, nie im Repo; HKVVB-Feldlängen |
| Zugangsdaten | `geheime_felder` = Benutzerkennung, PIN (Tresor); die Kunden-ID aus `fints einrichten --kunden-id` ebenfalls im Zugang (oft gleich der Benutzerkennung; die Einstellung `kunden_id` bleibt als Rückfall für `bank verbinde`); dazu die Sitzung (`deconstruct(including_private=True)`) ebenfalls verschlüsselt im Zugang; der Provider gibt sie über `Abruf.zugang` bzw. `FreigabeNoetigError.zugang` zurück, `rufe_ab` verschlüsselt neu | die Bank bindet die 180-Tage-Ausnahme an die Kundensystem-ID — ohne gesicherte Sitzung fragte sie bei jedem Abruf nach einer TAN; Akzeptanz 5 |
| Freigabe | `BankProvider(freigabe=…)`: ohne Rückfrage (`bank abrufen`, `bank lauf`, Cron) wird `FreigabeNoetigError` zum Zustand `freigabe_noetig` mit dem Hinweis `accounti fints freigeben`; mit Rückfrage (`fints einrichten`, `fints freigeben`) fragt die CLI nach der TAN bzw. wartet auf die App (Statusabfrage im Abstand `freigabe_intervall_sekunden`, höchstens `freigabe_wartezeit_sekunden`). Steht ein Konto auf `freigabe_noetig`, ruft ein Abruf ohne Rückfrage es **nicht** erneut ab (`KontoAbruf.uebersprungen`, Meldung bleibt), bis `fints freigeben` läuft | Spec 4.2 und 5: als Zustand gemeldet, ein automatischer Lauf legt den Abruf zurück; jeder Dialog löste eine neue Push-/SMS-Anforderung aus, die niemand bestätigt (Prüfbefund 3) |
| PIN falsch / gesperrt | `ZugangAbgelehntError` (Unterklasse von `ProviderError`) → Zustand `zugang_abgelehnt` (neuer Wert in `KontoZustand`); ohne Rückfrage kein weiterer Anmeldeversuch, auch `fints freigeben` ohne `--konto` lässt das Konto aus. `accounti fints zugang --konto …` nimmt Benutzerkennung (leer = unverändert) und neue PIN, wählt das TAN-Verfahren, gibt frei und setzt `bereit` (Abrufstand, Format und Kunden-ID bleiben); vorübergehend gesperrt → nach dem Entsperren `fints freigeben --konto …`. Die Meldung enthält nie Zugangsdaten | viele Banken sperren nach drei Fehlversuchen, der Cron läuft mehrmals täglich (Prüfbefund 2) |
| Erster Abruf | ohne Abrufstand ab heute minus `erster_abruf_tage` (Standard 90) | Umsätze der letzten 90 Tage fallen unter die SCA-Ausnahme |
| Zeitlimit | jede Anfrage an die Bank mit `zeitlimit_sekunden` (Standard 120); auch von python-fints beim Dialogaufbau verpackte Verbindungsfehler werden zu „Bank nicht erreichbar“ | python-fints setzt selbst kein Zeitlimit — ein hängender Server hielte den Cron auf |
| Rückmeldungen der Bank | der Logger `fints` bekommt einen `NullHandler` | python-fints protokolliert jede 3xxx-Rückmeldung als Warnung; ohne eigene Logging-Einrichtung landete das ungefragt auf der Konsole |
| TAN-Verfahren | `fints einrichten` fragt die Verfahren der Bank ab und lässt wählen (Einstellung `tan_verfahren`, ggf. `tan_medium`); ohne Einstellung wählt python-fints das erste zweistufige Verfahren | eine Wahl, die der Mensch einmal trifft, statt bei jedem Lauf |
| MT940-Parser | Standardbibliothek; `@@` als Zeilenumbruch; Buchungsdatum (sonst Valuta) als Datum; D/RC negativ, C/RD positiv; Verwendungszweck = `SVWZ+` (sonst der ganze Text) plus `EREF` als Referenz; Name aus ?32+?33, IBAN aus ?31; Saldenprobe je Auszug (Anfangssaldo + Umsätze = Endsaldo), sonst Fehler | ein Auszug, der nicht aufgeht, ist unvollständig — Fehler statt stiller Lücke |
| CAMT-Parser | camt.052/053/054, Versionen .02 und .08 namensraumunabhängig; nur gebuchte Einträge (BOOK); Vorzeichen aus `CdtDbtInd`; Gegenpartei bei Gutschrift `Dbtr`, bei Belastung `Cdtr`, bei Storno (`RvslInd=true`) umgekehrt; eine Transaktion je `Ntry` (Sammler: Verwendungszwecke zusammengefasst); DTD/Entity abgelehnt — im Parser selbst (expat-Handler), damit UTF-16 nicht vorbeikommt; Saldenprobe, wenn Anfangs- (OPBD/PRCD) und Endsaldo (CLBD) da sind | Vormerkposten sind keine Buchungen; die Kontozeile ist die Buchung; eine Rücklastschrift trägt die Parteien der Lastschrift (Prüfbefunde 12, 14) |
| Fremde Konten | Auszüge, deren Konto (IBAN oder BLZ/Kontonummer) nicht zum Bankkonto passt, überspringt der Datei-Provider, `import bank --konto` lehnt sie ab. Ein Konto ohne IBAN (Kreditkarte, Kennung z.B. `VISA1234`) nimmt keinen Auszug eines Bankkontos an — weder mit IBAN noch mit BLZ/Kontonummer oder BIC/Kontonummer —, außer die Kennung ist genau diese Kontoangabe (eine Kennung `BLZ/Kontonummer` passt auch zur deutschen IBAN desselben Kontos). Andere Formen (z.B. eine maskierte Kartennummer) gelten weiter als passend | ein Ordner mit Auszügen mehrerer Konten ordnet nichts falsch zu; MT940 nennt das Girokonto meist als BLZ/Kontonummer — ein Giro-Auszug landete sonst mit dem Sachkonto der Karte im Journal (Prüfbefunde 11, R2-4). Wer Kartenauszüge mit Kontonummer bekommt, gibt diese bei der Einrichtung als Kennung an |
| Bankreferenz | `Transaktion.quelle_referenz` (NONREF/NOTPROVIDED zählen nicht). Ohne Referenz bleibt der Schlüssel wie in Paket 2 (Konto, Datum, Betrag, Zweck, Gegenpartei, laufende Nummer — die Nummer zählt jetzt je Auszug, siehe nächste Zeile). **Mit** Referenz ist sie der Unterscheider: Konto, Datum, Betrag, Referenz — ohne laufende Nummer und ohne Zweck/Name; `speichere_neue` prüft auch innerhalb eines Abrufs | Spec 5: „Dublettenschutz über Bank-Referenz“; derselbe Umsatz aus zwei Dateien eines Abrufs (doppelter Download, camt.052 neben camt.053) und die camt.054-Auflösung eines Sammlers aus camt.053 (anderer Zweck) bleiben einer (Prüfbefunde 9, 10) |
| Laufende Nummer je Auszug | Ohne Bankreferenz zählt `mit_schluessel` gleiche Umsätze je Abschnitt: Der Provider meldet in `Abruf.abschnitte`, wo ein Auszug (MT940-Nachricht, camt-Statement/-Report) bzw. eine CSV-Datei beginnt (`Abruf.fuege_hinzu`); Folgeseiten eines Auszugs (MT940 `:60M:`, camt `…Pgntn/PgNb` > 1, `Auszug.fortsetzung`) gehören zum vorigen Abschnitt. Gilt für Datei-Provider und FinTS; `import bank` zählt je Datei (wie bisher), die PDF-Übernahme je Abrechnung | Tages- und Monatsauszug desselben Zeitraums im Ordner (MT940 NONREF, CSV) ergaben sonst Dubletten (#1 im Tages-, #2 im Monatsauszug); zwei echte gleiche Umsätze stehen in **einem** Auszug, denn Banken trennen Auszüge nach Buchungstag. Folgeseiten nicht zusammenzuzählen, verlöre dagegen einen echten zweiten Umsatz, wenn die Seitengrenze zwischen beide fällt (Prüfbefund R2-3) |
| Datei-Provider | MT940/CAMT werden am Inhalt erkannt (`.sta`, `.mt940`, `.940`, `.txt`, `.xml`), `format` gilt nur für CSV; Saldo des letzten Auszugs wird gemeldet. Eine Datei mit gleichem Inhalt wie eine schon gelesene und ein Auszug mit gleichem Inhalt (Konto, Salden, Umsätze) zählen nur einmal | Fallback bleibt vollständig (Akzeptanz 6); ohne Bankreferenz ist das der einzige Schutz gegen doppelte Downloads |
| `import bank` | `--format mt940|camt`, `auto` erkennt beide am Inhalt vor den CSV-Profilen. MT940/CAMT mit `--konto`: nur die Auszüge dieses Kontos, gehört keiner dazu → Fehler; ohne `--konto` und mit Auszügen mehrerer Konten → Fehler. Fehler beim Lesen (Saldo geht nicht auf) enden mit Meldung, nicht mit Traceback. Dafür ist `cli.py` minimal geändert (`importiere_fuer_konto`) | fremde Umsätze bekämen sonst still das Sachkonto des genannten Kontos (Prüfbefund 11, 17) |
| Kreditkarte | eigenes Bankkonto (Kennung statt IBAN, z.B. `VISA1234`, eigenes Sachkonto als Pflichtangabe) plus Eintrag in `kreditkarten`: Girokonto, Muster der Sammelbelastung, Endziffern, Abrechnungstag | Vorgabe des Auftrags; die Kartennummer selbst wird nie gespeichert |
| Kartenumsätze | Provider `abrechnung` (PDF über die Belegerfassung, `kreditkarte uebernehmen BELEG`) oder jeder andere Provider (`datei`, `fints`); Übernahme mit Dublettenschutz am Kartenkonto. Der Abgleich übernimmt erfasste Kartenabrechnungen von selbst, aber nur, wenn genau eine Karte eingerichtet ist und sie per PDF abrechnet — sonst Hinweis | Spec 4.3: Provider oder PDF; der PDF-Weg nutzt den vorhandenen Positionssplit. Die PDF einer Karte mit Abruf liegt oft ebenfalls in den Belegen und darf nicht geraten werden |
| Alte PDF-Abrechnungen | Vor jeder Übernahme: Steht im Fenster eine Sammelbelastung mit genau der Summe, die schon gebucht ist und keine Buchung auf das Kartenkonto (bzw. Geldtransit) hat → **nicht** übernehmen (von selbst: Hinweis; von Hand: Fehler, außer mit `--trotzdem`). Liegt der Stichtag vor der Einrichtung der Karte (`erstellt_am`) und gibt es im Fenster keine ungebuchte Belastung → von selbst nicht übernehmen (ein Sammelhinweis), von Hand mit Warnung | Baustein 2 hat Kartenabrechnungen schon als Kontoauszug erfasst; war die Sammelbelastung per Regel als Aufwand gebucht, buchte `classify` die Einzelumsätze ein zweites Mal als Aufwand, ggf. mit Vorsteuer und in abgeschlossenen Perioden (Prüfbefund 1) |
| Abrechnungsbetrag des Belegs | wird **nicht** gegen die Positionen geprüft | den Gesamtbetrag einer Kartenabrechnung liest die Belegextraktion nicht verlässlich (Saldo, Vortrag, Limit); eine fehlende Zeile fällt am Abgleich mit der Sammelbelastung auf |
| Ausgleichszeilen | positive Zeilen mit „Zahlung/Ausgleich/Lastschrift/…“ (`ausgleich_muster`) sind die Begleichung der Vorperiode, kein Einzelumsatz | sonst stimmte keine Summe |
| Abrechnung | PDF: Positionen des Belegs, Stichtag = Belegdatum; Provider: Umsätze bis zum Stichtag (Abrechnungstag des Monats oder `kreditkarte abrechnen --stichtag`), die noch zu keiner Abrechnung gehören — auch spät gelieferte aus einem früheren Zeitraum, nicht aber vor dem Beginn der ersten Abrechnung (mit `--von` nur ab diesem Tag); jeder Umsatz gehört höchstens zu einer Abrechnung. **Nachtragen:** Kommt ein Kartenumsatz, nachdem die Abrechnung seines Zeitraums gebildet wurde, wandert er in die offene (oder vorläufig zugeordnete) Abrechnung mit dem nächsten Stichtag ab seinem Datum; ist die seines Zeitraums schon fest, in die nächste | eindeutiger Abrechnungszeitraum; das Girokonto kommt oft täglich, die Kartenumsätze monatlich per Datei, und Herausgeber rechnen nach Buchungs-, nicht Kaufdatum ab (Prüfbefund 5) |
| Sammelbelastung | Girokonto-Umsatz < 0, Muster (und Endziffern, falls gesetzt) im Text, 0–`belastung_fenster_tage` (30) nach dem Stichtag; das Standardmuster schließt Texte mit `belastung_ausnahme` (Standard `debit`) aus, ein eigenes Muster der Karte nicht. Zuerst exakte Treffer (Betrag = Summe → abgeglichen), dann genau eine Abrechnung für genau eine Belastung → **Befund** mit centgenauer Differenz; konkurrieren Belastungen oder Karten, wird nichts zugeordnet („mehrdeutig“) — die Meldung nennt Umsatz-ID, die umkämpfte(n) Abrechnung(en) und den Befehl `accounti kreditkarte loesen <ABRECHNUNG> --belastung <UMSATZ>`, mit dem ein Mensch einen Kandidaten abtrennt. Eine schon anders gebuchte Belastung wird zugeordnet, aber nicht umgebucht — Befund „anders gebucht“. Längst gebuchte alte Belastungen ohne Abrechnung bleiben still. `kreditkarte einrichten` ohne Endziffern und ohne Muster weist auf das breite Muster hin | Spec 4.3; „streng vor großzügig“; wer die Karte nachträglich einrichtet, soll nicht jeden Monat dieselben Altfälle sehen; Visa-/Mastercard-Debitkarten sind auf Girokonten verbreitet (Prüfbefund 8) |
| Vorläufig über Läufe | Eine Zuordnung mit Abweichung ist **vorläufig**, solange ihre Buchung zur Prüfung steht (bzw. bei „anders gebucht“ eine Differenz bleibt). Jeder Lauf bewertet vorläufige Zuordnungen zusammen mit den offenen Abrechnungen neu: Ergebnis gleich → bleibt; kommt ein exakter Treffer, wird sie gelöst (vorläufige Buchung gelöscht — sie war nie freigegeben) und der Treffer gebucht; kommt ein zweiter Kandidat → beide „mehrdeutig“, nichts gebucht. Geprüft, korrigiert, exportiert oder automatisch gebucht → fest. `accounti kreditkarte loesen <ABRECHNUNG>` löst eine vorläufige Zuordnung von Hand und merkt sich das Paar (Tabelle `kreditkartenablehnungen`), damit es nicht wieder vorgeschlagen wird. **Mehrdeutig von Hand entscheiden:** `kreditkarte loesen <ABRECHNUNG> --belastung <UMSATZ>` (`trenne_belastung`) legt das Paar ebenfalls dort ab, auch ohne bestehende Zuordnung (ist der Umsatz der Abrechnung vorläufig zugeordnet, wird gelöst wie oben); der nächste Lauf ordnet die übrigen Kandidaten zu — centgenau → abgeglichen, sonst Befund. Der Umsatz muss eine Belastung des Girokontos der Karte sein. Ohne diesen Befehl war „mehrdeutig“ eine Sackgasse: beide Kandidaten blieben im Fenster, jeder Lauf erkannte dieselbe Konkurrenz, `loesen` brauchte eine Zuordnung (Prüfbefund R2-2) | „exakter Treffer gewinnt“ galt sonst nur innerhalb eines Laufs: ein früher, ungefährer Kandidat verbrauchte die Abrechnung, die echte Belastung lief danach ins Regelwerk (Prüfbefunde 4, 8); das Ergebnis hängt so nicht mehr davon ab, in welchem Lauf eine Belastung kommt |
| Buchung | PDF-Karte: Sammelbelastung „Kreditkarte an Bank“; Karte mit Abruf: Sammelbelastung „Geldtransit an Bank“, Ausgleichszeile „Kreditkarte an Geldtransit“ (SKR03 1360, SKR04 1460, `geldtransit_konto`). Abgeglichen → automatisch (Confidence 1,0), Abweichung → zur Prüfung mit voller Belastung; nie eine Buchung über die Differenz. Die Ausgleichszeile automatisch nur, wenn eine gleich hohe, über Geldtransit gebuchte **und bestätigte** Sammelbelastung dieser Karte (ihre Buchung automatisch gebucht, geprüft, korrigiert oder exportiert) noch keinen Ausgleich hat; sonst zur Prüfung (Confidence 0,5, Meldung „Ausgleich zur Prüfung“ — bei einer nur vorläufig zugeordneten Belastung mit diesem Grund). Wird die Belastung später bestätigt oder kommt sie erst später, bestätigt der nächste Lauf die vorläufige Ausgleichsbuchung | jede Kontozeile wird genau einmal auf ihrem Finanzkonto gebucht; `classify` fasst gebuchte Umsätze nicht an; die Einzelumsätze kontiert `classify` gegen das Kartenkonto. Ein Ausgleich von einem anderen Konto (privat → Einlage) oder ein abweichender Betrag ließe Geldtransit sonst still offen (Prüfbefund 7). Gegen eine vorläufige Belastung freigegeben, bliebe der Ausgleich stehen, wenn der Abgleich die Belastung später löst (Prüfbefund R2-1). Eine freigegebene Ausgleichsbuchung wird nie nachträglich zurückgestuft: `export datev` nimmt `auto` mit, ohne den Status zu ändern — sie kann schon beim Steuerbüro sein |
| Lauf | `bank lauf`: abrufen → **Kreditkarten** → offene Posten → Belegabgleich → kontieren | die Sammelbelastung darf weder als offener Posten noch per Regelwerk gebucht werden |
| Konfiguration | Abschnitt `bank` (Unterabschnitte `fints`, `kreditkarte`) mit eigenem Lader `bank/einstellungen.py`, alles mit Standardwerten | Muster `lade_buchhaltung`; ohne Abschnitt lauffähig |
| CLI | neue Gruppen `fints` (`einrichten`, `freigeben`, `zugang`, `format`) und `kreditkarte` (`einrichten`, `liste`, `uebernehmen [--trotzdem]`, `abrechnen`, `abgleich`, `loesen [--belastung]`) in `befehle/`; `bank verbinde --provider fints` funktioniert ebenfalls. `cli.py` minimal geändert: `import bank` (Kontoprüfung, Fehler ohne Traceback) und `bank lauf` (gibt den Kartenabgleich über `befehle.kreditkarte.zeige_kartenabgleich` aus) | Dateiregeln; die Gruppen `bank` und `import` gehören `cli.py` — eine stille Fehlbuchung und verschwundene Befunde rechtfertigen die kleine Änderung (Prüfbefunde 11, 17) |
| Tests | nie gegen eine echte Bank: Attrappe des python-fints-Clients (Szenarien: Freigabe bei der Initialisierung, App-Freigabe, TAN beim Abruf, PIN falsch, Verbindung weg) **und** eine lokale Testbank (HTTP auf 127.0.0.1) mit selbst geschriebenen FinTS-Antworten für den echten Client; Kontoauszüge als aufgezeichnete Beispieldateien in `tests/daten/bank/` | Spec 6 |

## Aufgaben

### Paket A – Formate

- [x] **MT940** (`importers/mt940.py`): `:61:` (Valuta/Buchungsdatum, Jahreswechsel, C/D/RC/RD, Bankreferenz, NONREF), `:86:` strukturiert und unstrukturiert, SEPA-Schlüssel, `@@`, mehrere Auszüge, Saldenprobe, Kontokennung (`tests/test_bank_mt940.py`).
- [x] **CAMT** (`importers/camt.py`): 052/053/054 in .02 und .08, Vorzeichen, Status, Storno, Gegenpartei, Referenzen, Sammler, Saldenprobe, DTD abgelehnt (`tests/test_bank_camt.py`).
- [x] **Gemeinsam** (`importers/kontoauszug.py`): Formaterkennung, Kontozuordnung (IBAN, BLZ/Konto), Registry `mt940`/`camt`, `waehle_importer(…, "auto")` erkennt beide.
- [x] **Dublettenschutz mit Bankreferenz** (`bank/dubletten.py`): ohne Referenz unveränderter Schlüssel; verschiedene Referenzen unabhängig von der Reihenfolge; Wiederholung → keine Dublette (`tests/test_bank_dubletten.py`).
- [x] **Datei-Provider** liest MT940/CAMT, überspringt fremde Konten und Notizen, meldet den Saldo; `import bank` mit MT940/CAMT und zweimal importiert → nichts doppelt (Akzeptanz 2, 6) (`tests/test_bank_provider.py`, `tests/test_cli_bank_formate.py`).

### Paket B – FinTS

- [x] **Abhängigkeit** `fints==5.0.0` in `pyproject.toml`, mypy-Ausnahme für das untypisierte Paket.
- [x] **Einstellungen** (`bank/einstellungen.py`): Abschnitt `bank`, Standardwerte, `${VAR}`, `ACCOUNTI_FINTS_PRODUKT_ID`, Fehlertexte (`tests/test_bank_einstellungen.py`).
- [x] **Provider-Schnittstelle**: `Freigabeanfrage`, `BankProvider(freigabe=…)`, `Abruf.zugang`, `FreigabeNoetigError.zugang`; `rufe_ab(…, freigabe=…)` verschlüsselt geänderte Zugänge neu (`tests/test_bank_lauf.py`).
- [x] **Provider `fints`** (`bank/fints.py`) gegen die Attrappe: Produkt-ID (fehlt, Reihenfolge, Länge), Konto über IBAN, camt/MT940, Zeitraum, Saldo, Sitzung, Freigabe bei Initialisierung und Abruf (TAN, App mit Statusabfrage, Abbruch, Zeitüberschreitung, ohne Rückfrage → Zustand), PIN falsch, Verbindung weg, TAN-Verfahren (`tests/test_bank_fints.py`).
- [x] **Einrichtung** (`richte_fints_ein`): TAN-Verfahren und -Medium wählen, erste Freigabe, Konto bei der Bank vorhanden.
- [x] **CLI** `fints einrichten|freigeben` (`befehle/fints.py`); **Akzeptanz 1** mit der Attrappe: einrichten (TAN) → `bank abrufen` zweimal ohne Eingabe → Bank verlangt Freigabe → Zustand, `fints freigeben` → weiter (`tests/test_cli_fints.py`).
- [x] **Akzeptanz 5** für FinTS: weder PIN noch Benutzerkennung noch Sitzung im Klartext in der Datenbank.
- [x] **Testbank** (`tests/fints_testbank.py`): echter python-fints-Client gegen lokale HTTP-Testbank — Produkt-ID im HKVVB, Freigabe bei der Initialisierung, MT940 mit Aufsetzpunkt, camt, zweiter Abruf mit gesicherter Sitzung ohne neue Kundensystem-ID und ohne TAN, falsche PIN, Einrichtung, Zeitlimit bei hängender Bank (`tests/test_bank_fints_testbank.py`).
- [x] **Akzeptanz 6** mit FinTS: Bank fällt aus → `import bank --konto` mit dem Auszug → späterer Abruf bringt nichts doppelt (`tests/test_cli_fints.py`).

### Paket C – Kreditkarten

- [x] **Modelle und Persistenz**: `models/bank.py`, `db/tabellen_bank.py` (`kreditkarten`, `kreditkartenabrechnungen`, `kreditkartenumsaetze`), `db/repo_bank.py` (`tests/test_bank_kreditkarte_repo.py`).
- [x] **Einrichtung und Provider `abrechnung`**: Karte als Bankkonto mit eigenem Sachkonto, Girokonto muss existieren, vorhandenes Konto als Karte markieren.
- [x] **PDF-Übernahme**: Positionen des Belegs (echte Belegerkennung des Beispiels `examples/belege/kreditkarte_12_umsaetze.txt`) → Umsätze am Kartenkonto (Dublettenschutz), Ausgleichszeilen ausgenommen, Abrechnung mit Summe; zweimal → Fehler; nur Kontoauszüge mit Kartenumsätzen; von selbst nur bei genau einer (PDF-)Karte.
- [x] **Abrechnung aus Provider-Umsätzen** (Stichtag, Abrechnungstag).
- [x] **Sammelbelastung**: gleich → abgeglichen und gebucht; 1 Cent Differenz → Befund, zur Prüfung, keine Rundungsbuchung; mehrdeutig → nichts; exakter Treffer gewinnt; Endziffern; Fenster; ohne Abrechnung → Hinweis, alte gebuchte still; schon anders gebucht → Befund; Geldtransit (SKR03/SKR04) für Karten mit Abruf inkl. Ausgleichszeile; idempotent (`tests/test_bank_kreditkarte.py`).
- [x] **Lauf**: Schritt im `bank lauf` vor den offenen Posten; `classify` bucht die Einzelumsätze gegen das Kartenkonto.
- [x] **CLI** `kreditkarte einrichten|liste|uebernehmen|abrechnen|abgleich` (`tests/test_cli_kreditkarte.py`).

### Runde 1 – Prüfbefunde

- [x] **Cron und Zugänge** (Befunde 2, 3, 6, 15): `zugang_abgelehnt` und `freigabe_noetig` ohne Rückfrage überspringen (`test_bank_lauf.py::test_freigabe_noetig_wird_ohne_rueckfrage_nicht_erneut_angefragt`, `::test_abgelehnter_zugang_wird_ohne_rueckfrage_nicht_wiederholt`, `test_bank_fints.py::test_cron_meldet_sich_nach_abgelehnter_pin_nicht_erneut_an`, `::test_cron_loest_keine_neuen_freigabe_anforderungen_aus`); `fints zugang` (`test_cli_fints.py::test_abgelehnter_zugang_wird_mit_fints_zugang_erneuert`); Format fest, Wechsel nur ausdrücklich ohne Überlappung (`test_bank_fints.py::test_auto_bleibt_beim_einmal_gewaehlten_format`, `::test_ausdruecklicher_formatwechsel_ohne_ueberlappung`, `::test_camt_faellt_weg_kein_stiller_wechsel`, `test_cli_fints.py::test_format_nur_ausdruecklich_wechseln`); nur https, Kunden-ID im Tresor (`test_bank_fints.py::test_nur_https_damit_die_pin_nicht_im_klartext_reist`, `test_cli_fints.py::test_kunden_id_liegt_verschluesselt_im_zugang`).
- [x] **Kartenabgleich** (Befunde 1, 4, 5, 7, 8): alte PDF-Abrechnungen (`test_bank_kreditkarte.py::test_alte_abrechnung_mit_schon_gebuchter_belastung_wird_nicht_uebernommen`, `::test_alte_abrechnung_ohne_offene_belastung_nur_von_hand`, `::test_abrechnung_nach_der_einrichtung_wird_von_selbst_uebernommen`); über zwei Läufe (`::test_spaeter_exakter_treffer_loest_die_vorlaeufige_zuordnung`, `::test_zweiter_ungefaehrer_kandidat_in_spaeterem_lauf_macht_mehrdeutig`, `::test_bestaetigte_abweichung_bleibt_bestehen`, `::test_debitkartenzahlung_ist_keine_sammelbelastung`); lösen (`::test_zuordnung_von_hand_loesen`, `::test_geloest_wird_nur_was_noch_nicht_geprueft_ist`, `test_cli_kreditkarte.py::test_vorlaeufige_zuordnung_von_hand_loesen`); Nachtragen (`::test_spaet_kommende_kartenumsaetze_werden_nachgetragen`, `::test_umsatz_nach_abgeglichener_abrechnung_kommt_in_die_naechste`); Ausgleich (`::test_ausgleich_nur_mit_gleich_hoher_sammelbelastung_automatisch`).
- [x] **Dublettenschutz und Import** (Befunde 9–12, 14, 17): `test_bank_dubletten.py::test_mit_bankreferenz_zaehlt_die_wiederholung_nicht`, `::test_mit_bankreferenz_zaehlt_der_verwendungszweck_nicht`; `test_bank_provider.py::test_doppelt_heruntergeladener_auszug_kommt_einmal`, `::test_ueberlappende_auszuege_mit_bankreferenz`, `::test_camt054_neben_camt053_bucht_den_sammler_nicht_doppelt`, `::test_kartenkonto_ohne_iban_ueberspringt_auszuege_mit_iban`; `test_cli_bank_formate.py::test_import_bank_mit_konto_nimmt_nur_dessen_auszuege`, `::test_import_bank_mit_kaputtem_saldo_ohne_traceback`; `test_bank_camt.py::test_ruecklastschrift_mit_beiden_parteien_nennt_den_glaeubiger`, `::test_dtd_auch_in_utf16_abgelehnt`; `test_cli_kreditkarte.py::test_bank_lauf_nennt_das_ergebnis_des_kartenabgleichs`.
- [x] **Recherche** (Befund 13): Kreditkartenkonto SKR03 1730 / SKR04 3610, Vorschlag in der Hilfe von `kreditkarte einrichten`.
- [x] **Migration** (Befund 16): keine Alembic-Migration im Paket (Dateiregel) — Pflichtschritt beim Zusammenführen, siehe Abschluss.

### Runde 2 – Prüfbefunde

- [x] **Ausgleich gegen vorläufige Belastung** (R2-1): nur zur Prüfung, bestätigt mit der Belastung (`test_bank_kreditkarte.py::test_ausgleich_gegen_vorlaeufige_belastung_nur_zur_pruefung` — zwei Läufe, dann mehrdeutig, Saldo Geldtransit der freigegebenen Buchungen 0; `::test_ausgleich_wird_mit_der_gepruefen_belastung_bestaetigt`). `_loese`/`loese_zuordnung` stufen keinen Ausgleich zurück: gegen eine lösbare (vorläufige) Belastung wird keiner mehr freigegeben, und eine freigegebene Buchung kann schon exportiert sein.
- [x] **Mehrdeutig von Hand entscheiden** (R2-2): `trenne_belastung`, `kreditkarte loesen <ABRECHNUNG> --belastung <UMSATZ>`, Meldung nennt Umsatz-ID und Befehl (`test_bank_kreditkarte.py::test_mehrdeutig_wird_von_hand_entschieden` → Befund, `::test_mehrdeutig_zwischen_zwei_karten_wird_von_hand_abgeglichen` → abgeglichen, `::test_trennen_einer_vorlaeufigen_zuordnung_loest_sie`, `::test_trennen_prueft_abrechnung_und_umsatz`; `test_cli_kreditkarte.py::test_mehrdeutig_von_hand_entscheiden`).
- [x] **Laufende Nummer je Auszug** (R2-3): `Abruf.abschnitte`/`fuege_hinzu`, `mit_schluessel(…, abschnitte)`, Folgeseiten (`Auszug.fortsetzung`) (`test_bank_dubletten.py::test_laufende_nummer_je_auszug`; `test_bank_provider.py::test_tages_und_monatsauszug_ohne_bankreferenz` über `rufe_ab`, `::test_zwei_seiten_eines_auszugs_zaehlen_zusammen`; `test_bank_mt940.py::test_folgeseite_mit_zwischensaldo_wird_erkannt`; `test_bank_camt.py::test_folgeseite_eines_auszugs_wird_erkannt`).
- [x] **Kartenkonto und BLZ/Kontonummer** (R2-4): `Auszug.gehoert_zu` (`test_bank_kontoauszug.py::test_gehoert_zu`, `test_cli_bank_formate.py::test_import_bank_auf_ein_kartenkonto_lehnt_giro_auszuege_ab` mit `auszug.sta`, `test_bank_provider.py::test_kartenkonto_ohne_iban_ueberspringt_auszuege_mit_kontonummer`).

### Belege der Akzeptanzkriterien (Spec 7)

| Nr. | Kriterium | Tests |
|-----|-----------|-------|
| 1 | Abruf ohne weitere Eingabe außer der Freigabe | `test_cli_fints.py::test_akzeptanz_1_abruf_ohne_weitere_eingabe_ausser_der_freigabe` (CLI, Attrappe), `test_bank_fints.py::test_freigabe_mit_tan_und_danach_ohne_eingabe`, `test_bank_fints.py::test_abruf_aller_konten_mit_freigabe_und_tresor`, `test_bank_fints_testbank.py::test_mt940_mit_freigabe_und_gesicherter_sitzung` (echter Client) |
| 2 | zweiter Abruf ohne Dubletten | `test_cli_bank_formate.py::test_import_bank_mt940_zweimal_ohne_dubletten`, `test_bank_dubletten.py::test_bankreferenz_unterscheidet_gleich_aussehende_umsaetze`, `test_cli_fints.py::test_akzeptanz_6_dateiimport_wenn_fints_ausfaellt`, `test_cli_fints.py::test_format_nur_ausdruecklich_wechseln`, `test_bank_provider.py::test_doppelt_heruntergeladener_auszug_kommt_einmal`, `::test_ueberlappende_auszuege_mit_bankreferenz`, `::test_camt054_neben_camt053_bucht_den_sammler_nicht_doppelt`, `::test_tages_und_monatsauszug_ohne_bankreferenz`, dazu aus Paket 2 `test_bank_lauf.py::test_abruf_ohne_weitere_eingabe_und_ohne_dubletten` |
| 3 | mit Beleg höhere Regel-Trefferquote | Paket 1: `test_bank_abgleichslauf.py::test_beleg_hebt_die_regel_trefferquote` |
| 4 | zwei gleiche Rechnungen → zwei Vorschläge | Paket 1: `test_bank_abgleich.py::test_zwei_gleiche_quittungen_am_selben_tag_werden_vorgeschlagen` |
| 5 | kein Zugangsdatum im Klartext | `test_bank_fints.py::test_abruf_aller_konten_mit_freigabe_und_tresor`, `test_bank_lauf.py::test_geaenderter_zugang_wird_neu_verschluesselt`, `test_cli_fints.py::test_akzeptanz_1_…`, `test_cli_fints.py::test_kunden_id_liegt_verschluesselt_im_zugang` |
| 6 | Dateiimport bleibt bei Ausfall nutzbar | `test_cli_fints.py::test_akzeptanz_6_dateiimport_wenn_fints_ausfaellt`, `test_bank_provider.py::test_liest_mt940_und_camt_und_meldet_den_saldo`, Paket 2: `test_bank_lauf.py::test_dateiimport_bleibt_nutzbar_wenn_der_provider_ausfaellt` |
| 4.3 | Sammelbelastung gegen Summe, Abweichung = Befund | `test_bank_kreditkarte.py::test_sammelbelastung_gleich_summe_wird_gebucht`, `::test_ein_cent_abweichung_ist_ein_befund_kein_rundungsposten`, `::test_spaeter_exakter_treffer_loest_die_vorlaeufige_zuordnung`, `::test_mehrdeutig_wird_von_hand_entschieden`, `test_cli_kreditkarte.py::test_abweichung_wird_als_befund_gemeldet`, `::test_bank_lauf_nennt_das_ergebnis_des_kartenabgleichs` |

### Abschluss

- [x] `pytest`, `ruff check`, `ruff format --check` (ohne Cache), `mypy` grün; Plan abgehakt; Doku-Bausteine unten aktuell.
- [ ] **Beim Zusammenführen (Pflicht):** Alembic-Migration für die neuen Tabellen `kreditkarten`, `kreditkartenabrechnungen`, `kreditkartenumsaetze` und `kreditkartenablehnungen` erzeugen (`alembic revision --autogenerate`, prüfen, mitliefern) — wie `docs/architektur.md` verlangt; Pakete dürfen laut Dateiregel keine eigene Migration mitbringen. Der neue `KontoZustand`-Wert `zugang_abgelehnt` (16 Zeichen) passt in die vorhandene Spalte `String(20)`, keine Schemaänderung. Wer vorher `init_db` laufen ließ, hat die Tabellen schon (`create_all`) — dann `alembic stamp` statt `upgrade`.

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
  erkennt sie nicht; eine so verlorene Zeile fällt erst beim Abgleich mit der Sammelbelastung
  als Befund auf (der Gesamtbetrag des Belegs wird nicht gegengeprüft, weil die Extraktion ihn
  bei Kartenabrechnungen nicht verlässlich liest). Geprüft ist der Weg mit dem Beispiel aus
  `examples/belege/`, nicht mit Abrechnungen echter Kartenherausgeber.
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
- **`bank lauf --config`** gilt nur für den Abschnitt `buchhaltung`; der Abschnitt `bank` kommt in
  `bank lauf` und `bank abrufen` immer aus `config/accounti.yaml` (Arbeitsverzeichnis) bzw. der
  Umgebung. Befunde eines Laufs stehen in seiner Ausgabe und danach in `kreditkarte liste`; eine
  Aufgabe daraus macht erst Baustein 8.
- **Hilfetext** von `bank verbinde` nennt `fints` noch als „später“ (ebenfalls `cli.py`).
- **Sammelbelastung ohne Abrechnung, „mehrdeutig“ oder gelöst** wird gemeldet, aber nicht
  gebucht — läuft danach `classify`, kann das Regelwerk sie buchen (eine Belastung vor
  `classify` zurückzuhalten, hieße die Auswahl offener Umsätze in `opos/` zu ändern). Abhilfe: PDF
  vor dem Lauf übernehmen, einen Abrechnungstag oder Endziffern einstellen; die Automatik
  übernimmt PDF-Abrechnungen nur bei genau einer Karte. „Mehrdeutig“ entscheidet ein Mensch mit
  `kreditkarte loesen <ABRECHNUNG> --belastung <UMSATZ>`; hat `classify` die echte Belastung bis
  dahin schon gebucht, ordnet der nächste Abgleich sie zu, meldet aber „anders gebucht“ (Befund)
  statt umzubuchen — die Buchung korrigiert dann die Buchhaltung.
- **Karten nachträglich ändern** (Endziffern, Muster, Abrechnungstag) geht nicht per Befehl; ein
  zu breites Muster lässt sich nur je Abrechnung mit `loesen` bzw. `--belastung` ausgleichen.
- **`import bank` ohne `--konto`** prüft nur, dass die Datei höchstens ein Konto enthält, nicht
  welches; CSV-Dateien kennen kein Konto und werden wie bisher übernommen.
- **Bankreferenz gilt als eindeutig** je Konto, Tag und Betrag. Vergäbe eine Bank dieselbe
  `//Referenz` für zwei gleich hohe Umsätze am selben Tag, bliebe einer.
- **Ohne Bankreferenz zählt die laufende Nummer je Auszug** (MT940 `NONREF`; CSV je Datei).
  Stünden zwei echte, in Datum, Betrag, Zweck und Gegenpartei gleiche Umsätze in zwei
  **verschiedenen** Auszügen eines Abrufs (nicht Folgeseiten), bliebe einer — Banken trennen
  Auszüge nach Buchungstag, das ist daher nicht zu erwarten, aber nicht mit echten Bankdaten
  geprüft. `import bank` zählt je Datei: Eine einzelne Datei mit Tages- **und** Monatsauszug
  ergibt dort weiter Dubletten (dafür hätte sich `cli.py` erneut ändern müssen). camt-Folgeseiten
  in getrennten Dateien zählen nur zusammen, wenn sie direkt aufeinander folgen (Dateinamen).
- **Formatwechsel ohne Überlappung:** Nach `fints format` holt der Abruf erst ab dem Tag nach dem
  Abrufstand. Bucht die Bank danach noch etwas mit älterem Datum nach, fehlt es — dann den Auszug
  per `import bank --konto` nachholen.
- **Vorläufige Buchungen werden gelöscht, nicht storniert,** wenn der Kartenabgleich eine
  Zuordnung löst (später exakter Treffer, zweiter Kandidat, `kreditkarte loesen`). Das betrifft
  nur Buchungen zur Prüfung, die weder freigegeben noch exportiert sind; geprüfte, korrigierte,
  exportierte und automatisch gebuchte bleiben unangetastet (`kreditkarte loesen` lehnt ab).
  Ein Ausgleich gegen eine vorläufige Belastung steht zur Prüfung; gibt ein Mensch ihn frei,
  bevor die Belastung bestätigt ist, und löst der Abgleich die Belastung danach, bleibt der
  Ausgleich freigegeben stehen und Geldtransit offen — die Meldung „Ausgleich zur Prüfung“ nennt
  den Grund.
- **Debitkarten-Ausnahme:** Das Standardmuster erkennt keine Sammelbelastung, deren Text „debit“
  enthält (z.B. „SEPA DIRECT DEBIT … KREDITKARTE“); dann ein eigenes `--muster` setzen oder
  `bank.kreditkarte.belastung_ausnahme` ändern.
- **Ausgleichszeilen** werden nur über den Betrag einer Sammelbelastung derselben Karte
  zugeordnet, nicht über das Datum; zwei gleich hohe Abrechnungen können ihre Ausgleiche tauschen
  (für Geldtransit ohne Folgen).
- **Karten mit Abruf und Altbestand:** Bringt der erste Abruf eines Kartenkontos (Ordner, FinTS:
  90 Tage) Umsätze aus Zeiträumen, deren Sammelbelastung auf dem Girokonto schon als Aufwand
  gebucht ist, kontiert `classify` diese Umsätze ein zweites Mal. Die Prüfung für alte
  PDF-Abrechnungen gilt hier nicht — beim Einrichten nur Auszüge ab dem ersten offenen
  Abrechnungszeitraum bereitstellen.
- **Kartenkonto mit Kontonummer:** Ein Konto ohne IBAN nimmt keine Auszüge mit IBAN,
  BLZ/Kontonummer oder BIC/Kontonummer an. Tragen die Kartenauszüge eine solche Kontoangabe, muss
  sie bei der Einrichtung die Kennung sein; sonst überspringt der Datei-Provider sie still (ohne
  Meldung) und `import bank --konto` lehnt sie ab.
- **Keine Alembic-Migration im Paket** (Dateiregel): die vier Kreditkarten-Tabellen entstehen im
  Betrieb über `init_db`; die Migration ist Pflichtschritt beim Zusammenführen (Abschluss).
- **TAN-Medien** (`get_tan_media`) sind nur gegen die Attrappe getestet, nicht gegen die
  Testbank mit dem echten Client.

## Doku-Bausteine

In README, CHANGELOG, Bauplan und Architektur eingearbeitet.
