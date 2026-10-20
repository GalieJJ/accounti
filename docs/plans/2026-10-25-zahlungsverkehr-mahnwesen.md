# Zahlungsverkehr & Mahnwesen (Baustein 6) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** accounti schlägt vor, was wann zu zahlen ist — Skontofristen vor Nettofälligkeiten, mit
Grund je Position —, macht daraus einen Zahlungslauf, der hart geprüft, freigegeben und als
SEPA-Sammelüberweisung (`pain.001`) zum Hochladen ins Onlinebanking geschrieben wird. Auf der
anderen Seite durchlaufen überfällige Ausgangsrechnungen konfigurierbare Mahnstufen mit
Verzugszinsen nach § 288 BGB, der 40-€-Pauschale im B2B-Geschäft und einem Mahnschreiben als PDF
oder Text; die Mahnstufe steht am offenen Posten.

**Spec:** [`docs/specs/2026-08-10-zahlungsverkehr-mahnwesen.md`](../specs/2026-08-10-zahlungsverkehr-mahnwesen.md)
· Akzeptanzkriterien 1–7 · **Baut auf:** Baustein 4 (Kontakte, offene Posten, Zahlungszuordnung),
Baustein 3 (Firmendaten, Liberation-Schriften, E-Mail-Versandweg)

## Schnitt in Pakete

| Paket | Inhalt | Akzeptanz |
|-------|--------|-----------|
| **1 Zahlungslauf** | Modelle, Tabellen, Repository, Abschnitt `zahlung`; Vorschlag (`vorschlag.py`), blockierende Prüfung (`pruefung.py`), Zustandsautomat mit Freigabe, Vier-Augen, Storno und Protokoll (`freigabe.py`), Zahlungssperre, IBAN-Klärung | 1, 3, 4, 5 |
| **2 SEPA-Datei** | `pain.001.001.09` nach DK-TVS GBIC_5 (`sepa.py`), Schemaprüfung gegen das offizielle XSD, Golden-Test, Abgleich „ausgeführt“, CLI `accounti zahlung …` | 2, 3, 7 |
| **3 Mahnwesen** | Basiszinssatz-Tabelle mit Gültigkeitszeiträumen, Verzugszinsen, Stufenermittlung, B2B/B2C-Einstufung, Mahnlauf, Mahnschreiben (PDF/Text), Versand, Mahnstufe am Posten, CLI `accounti mahnwesen …` | 6, 7 |

```
ZAHLUNGSAUSGANG                                  MAHNWESEN
offene Verbindlichkeiten (opos)                  überfällige Forderungen (opos)
  │ zahlung vorschlag  (Skonto zuerst, Grund)      │ mahnwesen lauf (Karenz, Mindestbetrag,
  ▼                                                │   Stufenabstand, Sperre, B2B/B2C)
Entwurf ── zahlung anlegen / entfernen             ▼
  │ zahlung pruefen  (blockierend)               Mahnung (Entwurf): Rest + Zinsen § 288
  ▼                                                │ + Pauschale (B2B) + Gebühren
freigegeben ── zahlung freigeben (Vier-Augen)      │ mahnwesen versenden (PDF/Text/E-Mail)
  │ zahlung sepa --datei  (Prüfung + Hash)         ▼
  ▼                                              versendet → Mahnstufe am Posten, Historie
eingereicht ── Datei hochladen (Onlinebanking)
  │ Bankumsatz → opos zuordnen (gleicht aus)
  ▼ zahlung abgleichen
ausgeführt          storniert ← Entwurf/freigegeben/eingereicht (mit Grund, Protokoll)
```

## Recherche (Stand 20.10.2026)

### SEPA-Format für deutsche Banken

| | |
|---|---|
| Regelwerk | DFÜ-Abkommen der Deutschen Kreditwirtschaft (DK), **Anlage 3 „Spezifikation der Datenformate“**. Gültig ist **Version 3.9** (für SEPA ab **05.10.2025**); **Version 26.11** vom 09.04.2026 gilt ab **15.11.2026** ([ebics.de/de/datenformate](https://www.ebics.de/de/datenformate), [Gültige Version](https://www.ebics.de/de/datenformate/gueltige-version)) |
| Nachricht | SEPA-Überweisung (BTF `SCT///pain.001/`, Auftragsart CCT bzw. CTV mit VOP): **`pain.001.001.09`**, Namespace `urn:iso:std:iso:20022:tech:xsd:pain.001.001.09`, DK-TVS **`pain.001.001.09_GBIC_5.xsd`** — in 3.9 und 26.11 identisch (Anlage 3 V26.11, Kap. 2, S. 81; Vorgänger GBIC_4 galt für 3.7/3.8) |
| Altformat | `pain.001.001.03` (GBIC_3): Abkündigung zu 11/2026 ausgesetzt, „vorübergehend weiter verwendbar“ (DK, *SEPA-Formatversionen im Verfahren „DFÜ mit Kunden“* V2.0 vom 24.09.2026, [Format-LifeCycle](https://www.ebics.de/de/datenformate/format-lifecycle)) — für Neues kein Grund, es zu nutzen |
| Schema | `pain.001.001.09_GBIC_5.xsd` aus „DK-TVS_SEPA_GBIC_5zzglISO_Originale.zip“ ([Ergänzende Dokumente](https://www.ebics.de/de/datenformate/ergaenzende-dokumente)), Dateistand 01.04.2025, SHA-256 `d64da6e1553cf8dd38f98818fe3234fb79daec792d0a69483a1ab8e90dec8b8c`; unverändert als Testdatei unter `tests/daten/zahlung/`. Das DK-Beispiel `pain.001.001.09.xml` aus „XML-Beispiele_SEPA.zip“ besteht die Prüfung |
| Zeichensatz | UTF-8 ohne BOM; Latin Character Set (`a–z A–Z 0–9 ' : ? , - ( + . ) /` und Leerzeichen); Banken müssen zusätzlich `Ä Ö Ü ä ö ü ß & * $ %` annehmen (Anlage 3, S. 84 f.). Referenzen dürfen nicht mit `/` beginnen/enden und kein `//` enthalten; `MsgId`, `PmtInfId`, `EndToEndId` per Pattern auf den Latin-Satz beschränkt |
| Längen | Namen 70 Zeichen (`Max140Text_SCT_SCTinst`), Verwendungszweck `Ustrd` 140, IDs 35; Betrag 0,01–999.999.999,99, zwei Nachkommastellen, nur `EUR` |
| Pflichtfelder | `DbtrAgt` ist Pflicht: BIC oder `Othr/Id = NOTPROVIDED`; `CdtrAgt` (BIC des Empfängers) optional |
| Sammelbuchung | `BtchBookg` `false` = Einzelbuchung je Überweisung auf dem Kontoauszug — **nur mit Vereinbarung** mit der Bank, sonst bucht sie immer als Sammelposten (Anlage 3, Kap. 2.2.1, BatchBooking) |
| Adressen | `PstlAdr` des Empfängers optional; wenn angegeben, sind `TwnNm` und `Ctry` Pflicht, seit GBIC_5 hybrid mit bis zu 2 `AdrLine`. Für den Zahler empfiehlt die DK, keine Adresse anzugeben. SWIFT/EPC dulden unstrukturierte Adressen über 11/2026 hinaus (Hinweis Format-LifeCycle) |
| SEPA-Raum | 27 EU-Staaten, 3 EWR-Staaten (IS, LI, NO) und 11 Nicht-EWR-Länder (AL, AD, MD, MC, ME, MK, SM, RS, CH, GB, VA) laut EPC409-09 *EPC List of SEPA Scheme Countries* v8.0 vom 24.12.2025; IBAN-Präfixe zusätzlich GI (Gibraltar); Guernsey/Jersey/Isle of Man führen GB-IBANs, die französischen Überseegebiete FR-IBANs |
| Empfängerüberprüfung | Seit 09.10.2025 prüft die Bank bei Überweisungen Name ↔ IBAN (Verification of Payee); für Sammler bietet die DK eigene Auftragsarten (CTV) — das geschieht beim Hochladen in der Bank, nicht in accounti |

### Verzugszinsen und Basiszinssatz

| | |
|---|---|
| § 288 Abs. 1 BGB | Verzugszinssatz für das Jahr **5 Prozentpunkte** über dem Basiszinssatz |
| § 288 Abs. 2 BGB | Rechtsgeschäfte ohne Verbraucher, Entgeltforderungen: **9 Prozentpunkte** |
| § 288 Abs. 5 BGB | Schuldner kein Verbraucher: **Pauschale 40 €**; sie ist auf einen Schadensersatz für Kosten der Rechtsverfolgung **anzurechnen** (Satz 3) — Mahngebühren werden also nur verlangt, soweit sie 40 € übersteigen |
| § 286 BGB | Verzug durch Mahnung nach Fälligkeit, ohne Mahnung bei kalendermäßig bestimmter Zeit (Abs. 2 Nr. 1), spätestens 30 Tage nach Fälligkeit und Zugang der Rechnung (Abs. 3; bei Verbrauchern nur mit Hinweis in der Rechnung) |
| § 247 BGB | Basiszinssatz ändert sich zum 1. Januar und 1. Juli; die Bundesbank gibt ihn im Bundesanzeiger bekannt |
| Quelle Gesetzestexte | [gesetze-im-internet.de §§ 247, 286, 288 BGB](https://www.gesetze-im-internet.de/bgb/__288.html), abgerufen 20.10.2026 |
| Basiszinssätze | Tabelle der Deutschen Bundesbank, [Basiszinssatz nach § 247 BGB](https://www.bundesbank.de/de/bundesbank/basiszinssatz-nach---247-bgb-607820), abgerufen 20.10.2026: 01.07.2026 **1,52 %** · 01.01.2026 1,27 % · 01.07.2025 1,27 % · 01.01.2025 2,27 % · 01.07.2024 3,37 % · 01.01.2024 3,62 % · 01.07.2023 3,12 % · 01.01.2023 1,62 % · 01.07.2016–01.07.2022 −0,88 % · … zurück bis 01.07.2002 2,47 % (vollständig in `mahnwesen/basiszins.py`). Der Satz ab 01.01.2027 ist noch nicht bekannt |
| Zinstage | taggenau; ob das Jahr in Schaltjahren 365 oder 366 Tage hat, wird in Ratgebern und Prüfungsunterlagen unterschiedlich gehandhabt (z.B. IHK München „act/act“, andere durchgängig 365) — eine verbindliche Quelle war nicht zu finden, siehe Entscheidung |

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Format | `pain.001.001.09` nach DK-TVS GBIC_5, ein `PmtInf` je Lauf (Sammler), `PmtMtd=TRF`, `SvcLvl=SEPA`, `ChrgBr=SLEV` | Anlage 3 V3.9/V26.11; GBIC_5 gilt 2026 durchgehend |
| Schemaprüfung | im Test gegen das unveränderte offizielle XSD mit `javax.xml.validation` (Java ist durch KoSIT/Mustang ohnehin Pflicht in der CI; Quelltextmodus `java XsdPruefung.java`, keine neue Python-Abhängigkeit); ohne Java übersprungen, in der CI (`ACCOUNTI_PRUEFWERKZEUGE_PFLICHT=1`) Pflicht. Zusätzlich Golden-Test gegen `pain001_soll.xml` | Spec 6; die Standardbibliothek kann kein XSD |
| Zeichen | Namen und Verwendungszweck auf den DK-Zeichensatz (Latin + Umlaute, ß, `& * $ %`), andere Buchstaben ohne Akzent (é → e), Rest → Leerzeichen; Referenzen nur Latin-Pattern, ohne führendes/abschließendes `/` und ohne `//` | Banken müssen den DK-Satz annehmen; nichts geht verloren, was eine Bank nicht lesen kann |
| Sammelbuchung | `zahlung.einzelbuchung: true` (Standard) schreibt `BtchBookg=false` | Jede Überweisung erscheint einzeln mit Empfänger und Rechnungsnummer auf dem Kontoauszug — nur so kann `opos zuordnen` sie dem Posten zuordnen. Ohne Vereinbarung bucht die Bank trotzdem als Sammler (Grenzen) |
| BIC | Empfänger ohne BIC (IBAN-only); Auftraggeber-BIC aus `zahlung.auftraggeber.bic` bzw. `mandant.bank.bic`, sonst `NOTPROVIDED` | SEPA braucht seit 2016 keinen BIC; `DbtrAgt` ist laut TVS Pflicht |
| Empfängeradresse | `PstlAdr` nur, wenn Ort und Land bekannt: `StrtNm`/`BldgNb` (Hausnummer abgetrennt), `PstCd`, `TwnNm`, `Ctry` | strukturiert ist der empfohlene Weg; optional im SEPA-Raum |
| IDs | `MsgId` = `ACCOUNTI-<Lauf>-<JJJJMMTThhmmss>`, `PmtInfId` = `ACCOUNTI-<Lauf>`, `EndToEndId` = Rechnungsnummer des Lieferanten (bereinigt), sonst `ACCOUNTI-<Lauf>-<Pos>` | MsgId muss je Datei neu sein (Dublettenschutz der Bank); die Rechnungsnummer hilft dem Lieferanten |
| Verwendungszweck | `<Rechnungsnummer> vom <Belegdatum>`, bei Skonto `abzgl. <x> EUR Skonto` (max. 140) | Spec 4.3; damit trifft `opos zuordnen` Stufe A (Referenz) |
| Vorschlag | Stichtag = geplanter Ausführungstag; Planungshorizont `vorlauf_tage` (Standard 3). Skontoposten (Skonto > 0, Frist ≥ Stichtag, Posten unberührt) werden vorgeschlagen, sobald ihre **Skontofrist** in den Horizont fällt — auch wenn das Nettoziel Wochen entfernt ist; andere, sobald sie fällig sind. Reihenfolge: Skonto nach Frist, dann Fälligkeit. Grund je Position („Skontofrist endet morgen: 2 % = 3,45 € sparen; netto fällig am …“) | Spec 4.1: Skonto hat Vorrang; nicht früher zahlen als nötig |
| Ausgeschlossen | mit Grund gelistet: Zahlungssperre, schon in einem Lauf, Gutschrift (Betrag < 0), Betragsfilter | Nachvollziehbarkeit; Gutschriften verrechnet der Mensch |
| Lauf | `zahlungslaeufe` + `zahlungen` + `zahlungslauf_protokoll`; laufende Nummer je Lauf (`zahlung pruefen 42`). Zahlung friert Empfänger, IBAN, Adresse, Betrag, Skonto, Restbetrag und Verwendungszweck bei der Anlage ein | was freigegeben wird, ist genau das, was in der Datei steht |
| Zustände | Entwurf → freigegeben → eingereicht → ausgeführt; storniert aus Entwurf, freigegeben, eingereicht; alles andere `ZustandError` | Spec 4.4 |
| Eingereicht | mit dem Schreiben der Datei; die XML wird im Lauf gespeichert und bei erneutem `zahlung sepa` byte-gleich ausgegeben (gleiche `MsgId`) | ab der Datei kann Geld fließen; ein erneutes Hochladen weist die Bank über die `MsgId` ab |
| Ausgeführt | `zahlung abgleichen`: ein Lauf ist ausgeführt, wenn bei jedem Posten der Rest um mindestens den gezahlten Betrag gesunken ist. accounti gleicht **nicht** selbst aus — das macht der Bankumsatz über `opos zuordnen` | Auftrag: Ausgleich nur über den Bankumsatz; keine Doppelbuchung |
| Doppelzahlung | dreifach: Vorschlag lässt Posten aktiver Läufe weg; Anlage lehnt sie ab; **eindeutiger Index** `zahlungen.sperre` (= Posten-ID, solange der Lauf nicht storniert oder ausgeführt ist) — hält auch bei parallelen Prozessen. Die Prüfung meldet zusätzlich doppelte Posten im selben Lauf | Akzeptanz 3 |
| Prüfung | blockierend, Grund je Befund: Auftraggeber-IBAN; Ausführungsdatum nicht in der Vergangenheit; Posten offen und unverändert; Betrag = Rest oder Rest − Skonto mit Frist ≥ Ausführung; Höchstbetrag je Zahlung (`hoechstbetrag_zahlung`); Kontakt bestätigt (nicht „zur Prüfung“); Zahlungssperre; IBAN im Stammsatz vorhanden und mit gültiger Prüfziffer; **IBAN der Zahlung = Stammsatz**; **IBAN auf der Rechnung = Stammsatz**; IBAN-Land im SEPA-Raum; Währung EUR; Posten in keinem anderen aktiven Lauf | Spec 4.2, Akzeptanz 4 |
| IBAN-Abweichung | Meldung nennt Rechnung, beide IBANs und was zu tun ist („beim Lieferanten auf bekanntem Weg bestätigen …“). Ausweg: Stammsatz nach Rückruf ändern (`kontakte bearbeiten --iban`) **oder** `zahlung iban-klaeren <Lauf> <Pos> --grund … --von …` — dann wird an die Stammsatz-IBAN gezahlt, die Klärung gilt nur für genau dieses IBAN-Paar und steht im Protokoll | genau so funktionieren gefälschte Rechnungen; ein Mensch entscheidet, dokumentiert |
| Freigabe | prüft erneut; speichert einen SHA-256 über Auftraggeber, Ausführungsdatum und alle Zahlungen (`freigabe_hash`); `zahlung sepa` prüft erneut und vergleicht den Hash | freigegeben = unveränderbar; auch direkte DB-Änderungen fallen auf |
| Vier-Augen | `zahlung.vier_augen: true` verlangt zwei verschiedene Personen; eine Freigabe gilt nur für den Inhalt (Hash), den sie gesehen hat | Spec 4.4; im Einpersonenbetrieb aus |
| Unveränderbar | Zahlungen eines nicht mehr entworfenen Laufs: Änderungen (außer der Freigabe der Sperre) und Löschen scheitern am ORM; Protokoll nur anfügen (ORM-Sperre, SQLite-Trigger wie beim USt-IdNr.-Protokoll) | Akzeptanz 5, Prinzip 6 |
| Person | `--von`, sonst `ACCOUNTI_BENUTZER`, sonst Anmeldename | bis Baustein 10 echte Benutzer bringt |
| Einreichung über Provider | nicht in diesem Paket — `bank/` bleibt unverändert, der Dateiweg ist der einzige | Auftrag; Spec: Dateiweg immer verfügbar |
| Konfiguration | Abschnitte `zahlung` und `mahnwesen` in `config/accounti.yaml` mit eigenen Ladern (`accounti.zahlung.konfiguration.lade_zahlung`, `accounti.mahnwesen.konfiguration.lade_mahnwesen`); ohne Abschnitt gelten Standards | Projektregel; die Spec nannte `config/mahnwesen.yaml` |
| Befehlsgruppen | `accounti zahlung …` und `accounti mahnwesen …` | Bereichsname; die Spec schrieb `accounti mahnen …` |
| Basiszinssatz | Tabelle mit **ab/bis** je Halbjahr in `mahnwesen/basiszins.py` (Bundesbank, Stand 20.10.2026), letzter Zeitraum bis 31.12.2026; neue Sätze per `mahnwesen.basiszinssaetze` (`ab`, `satz`, optional `bis`) ergänzbar, sie gehen vor. Zinstage ohne bekannten Satz → `BasiszinsUnbekanntError` mit Hinweis, statt still mit dem alten Satz zu rechnen | halbjährliche Änderung; alte Zeiträume bleiben rechenbar |
| Zinsen | ab dem Tag nach Fälligkeit + `verzug_nach_tagen` (Standard 0) bis einschließlich Mahndatum; Abschnitte an jedem Basiszinswechsel und jeder Zahlung (Kapital = heutiger Rest + später gezahlte Beträge laut Zahlungszuordnung); je Abschnitt `Kapital × Satz × Tage / 365`, kaufmännisch auf Cent gerundet, Summe der Abschnitte | handrechenbar, Teilzahlungen werden zeitanteilig berücksichtigt; act/365 ist die verbreitete Praxis |
| B2B/B2C | Reihenfolge: Einstufung am Kontakt (`mahnwesen kunde --unternehmer/--verbraucher`) → Ausgangsrechnung aus accounti (`kunde.privat`) → USt-IdNr. im Stammsatz → sonst `mahnwesen.unbekannt_als` (Standard `verbraucher`); der Grund steht in der Mahnung | zu hohe Zinsen gegenüber Verbrauchern wären eine unberechtigte Forderung; zu niedrige schaden nicht |
| Pauschale | 40 € (`pauschale_b2b`) bei Unternehmern ab der ersten Stufe mit `verzugszinsen: true`, je Posten einmal; Mahngebühren werden nach § 288 Abs. 5 S. 3 angerechnet (`pauschale_anrechnen: true`): verlangt wird `max(0, Gebühren − 40)` zusätzlich | Gesetzeswortlaut |
| Gebühren | `gebuehr` je Stufe; eine Mahnung verlangt die Summe der Gebühren aller Stufen bis zu ihrer | bisherige Mahngebühren bleiben geschuldet |
| Stufen | eine Stufe je Lauf, keine wird übersprungen: Stufe *n+1* greift, wenn Tage seit Fälligkeit ≥ `ab_tagen` der Stufe **und** > `karenztage` **und** seit der letzten versendeten Mahnung ≥ `stufenabstand_tage` (Standard 7). Rest < `mindestbetrag` → keine Mahnung (Grund). Nach der letzten Stufe: Hinweis, keine weitere | Spec 4.5; „durchläuft die Stufen“ |
| Mahnung | je Posten eine Mahnung (Entwurf → versendet / verworfen); beim Versenden: Mahnstufe am Posten hochgezählt (`repo_mahnwesen.setze_mahnstufe`), PDF ins Belegarchiv, Hash und Weg an der Mahnung — die versendeten Mahnungen sind die Historie | Spec 4.5 [4]; Entwurf zählt nicht |
| Ausnahmen | Mahnsperre am Kontakt, offener Mahnentwurf, Zahlung vorgeschlagen (`opos vorschlaege`), letzte Stufe erreicht, Mindestbetrag — jeweils mit Grund | nicht mahnen, was gerade bezahlt wurde |
| Mahnschreiben | PDF mit fpdf2 und den Liberation-Schriften aus `erechnung/schriften` (kein PDF/A nötig) oder Text; Absender aus `mandant` (`lade_firma`); Texte je Stufe mit Standard, überschreibbar (`text` mit Platzhaltern) | wie `accounti.erechnung`; Text für eigene Vorlagen |
| E-Mail | `mahnwesen versenden --email` nutzt Abschnitt `versand` und den SMTP-Versandweg aus `erechnung/versand.py` (nur importiert) | ein SMTP-Zugang für alles |

## Aufgaben

### Paket 1 — Zahlungslauf

- [x] **Modelle** `models/zahlung.py`: `LaufStatus`, `Zahlung`, `Zahlungslauf`, `LaufProtokoll`, `Zahlungssperre`, `IbanKlaerung`.
- [x] **Tabellen** `db/tabellen_zahlung.py` (eindeutiger Index `zahlungen.sperre`, ORM-Sperre für Zahlungen nicht-entworfener Läufe, Protokoll nur anfügen + SQLite-Trigger) und **Repository** `db/repo_zahlung.py`.
- [x] **Konfiguration** `zahlung/konfiguration.py`: `lade_zahlung()` mit Standards, Auftraggeber aus `mandant` (`tests/test_zahlung_konfiguration.py`).
- [x] **IBAN-Hilfen** `zahlung/iban.py` (Schreibweise, Prüfziffer, SEPA-Raum) und **Zeichensatz** `zahlung/zeichen.py` (Umlaute bleiben, Akzente fallen, Fremdes wird Leerzeichen, Längen, Schrägstrich-Regeln; `tests/test_zahlung_sepa.py`).
- [x] **Vorschlag** `zahlung/vorschlag.py`: Skontofrist morgen vs. Nettofälligkeit heute, Skonto verfallen, Teilzahlung, gesperrter Kontakt, schon im Lauf, Gutschrift, Filter, ohne Skonto, Horizont (`tests/test_zahlung_vorschlag.py`) — **Akzeptanz 1**.
- [x] **Prüfung** `zahlung/pruefung.py`: abweichende IBAN (Rechnung und Stammsatz), ungültige Prüfziffer, fehlende IBAN, Nicht-SEPA-Land, doppelter Posten (auch am Index vorbei), Sperre, Kontakt zur Prüfung, Posten geändert/bezahlt, Skontofrist, Höchstbetrag, Fremdwährung, Datum, Auftraggeber — jeweils „blockiert, mit Begründung“; IBAN-Klärung (`tests/test_zahlung_pruefung.py`) — **Akzeptanz 4**.
- [x] **Freigabe** `zahlung/freigabe.py`: Anlegen, Entfernen nur im Entwurf, Übergänge in falscher Reihenfolge abgelehnt, Vier-Augen, Hash, Storno mit Grund und Protokoll, Posten wieder frei, Unveränderbarkeit auf ORM- und SQLite-Ebene, Doppelzahlung über den Index (`tests/test_zahlung_freigabe.py`) — **Akzeptanz 3, 5**.

### Paket 2 — SEPA-Datei

- [x] **pain.001.001.09** schreiben (`zahlung/sepa.py`): Golden-Test gegen `tests/daten/zahlung/pain001_soll.xml`; Schemaprüfung gegen `pain.001.001.09_GBIC_5.xsd` mit `tests/daten/zahlung/XsdPruefung.java` (Soll-Datei, Sammelbuchung, Grenzfall mit Höchstlängen, Höchstbetrag, Sonderzeichen, ohne BIC und ohne Anschrift; Gegenprobe mit kaputter Datei) (`tests/test_zahlung_sepa.py`) — **Akzeptanz 2**.
- [x] **Datei erzeugen**: nur freigegeben, Prüfung + Hash (Änderung am ORM vorbei wird erkannt), eingereicht, gespeicherte XML byte-gleich wieder ausgeben, Posten bleiben gesperrt; `pruefe_ausfuehrung` setzt „ausgeführt“, sobald `opos zuordnen` den Posten über den Bankumsatz ausgeglichen hat (`tests/test_zahlung_datei.py`) — **Akzeptanz 3**.
- [x] **CLI** `befehle/zahlung.py`: `vorschlag`, `anlegen`, `liste`, `zeigen`, `entfernen`, `pruefen`, `freigeben`, `sepa --datei`, `stornieren`, `abgleichen`, `sperre`, `iban-klaeren`; Ende-zu-Ende ohne Bankanbindung bis zur Datei (`tests/test_cli_zahlung.py`) — **Akzeptanz 7**.

### Paket 3 — Mahnwesen

- [x] **Basiszinssatz** `mahnwesen/basiszins.py`: Tabelle lückenlos (mit der Bundesbank-Seite abgeglichen), Satz am Stichtag, Ergänzung/Korrektur aus der Konfiguration, Überschneidung, unbekannter Zeitraum → Fehler (`tests/test_mahnwesen_basiszins.py`).
- [x] **Verzugszinsen** `mahnwesen/zinsen.py`: handgerechnete Fälle B2B/B2C, über den Wechsel am 01.07.2026, Teilzahlung im Verzug, Zahlung nach dem Stichtag (`tests/test_mahnwesen_zinsen.py`).
- [x] **Konfiguration** `mahnwesen/konfiguration.py`: Stufen, Karenz, Mindestbetrag, Abstand, Pauschale, Texte mit geprüften Platzhaltern, Basiszins-Ergänzungen nur zum 1.1./1.7. (`tests/test_mahnwesen_konfiguration.py`).
- [x] **Modelle, Tabellen, Repository** `models/mahnwesen.py`, `db/tabellen_mahnwesen.py` (versendete Mahnungen am ORM gesperrt), `db/repo_mahnwesen.py` (`setze_mahnstufe` am offenen Posten).
- [x] **Stufen** `mahnwesen/stufen.py`: der Reihe nach, keine übersprungen, Karenz, Stufenabstand, Ausnahmen mit Grund (`tests/test_mahnwesen_stufen.py`).
- [x] **Mahnlauf, Einstufung B2B/B2C, Versand-Status** `mahnwesen/lauf.py`: ein Posten durchläuft Erinnerung → 1. → 2. Mahnung mit handgerechneten Zinsen, Pauschale und Gebühren (B2B und B2C), Pauschale ohne Anrechnung, kein Verzug → keine Pauschale, Teilzahlung aus der Zahlungszuordnung, Mahnstufe am Posten erst beim Versand (`tests/test_mahnwesen_lauf.py`) — **Akzeptanz 6**.
- [x] **Mahnschreiben** `mahnwesen/schreiben.py` und **Versand** `mahnwesen/versand.py`: Text und PDF (Inhalt per `pypdf` gelesen), eigene Texte, PDF ins Belegarchiv, E-Mail über einen Test-Versandweg, gescheiterte E-Mail ändert nichts (`tests/test_mahnwesen_schreiben.py`).
- [x] **CLI** `befehle/mahnwesen.py`: `lauf`, `liste`, `zeigen`, `versenden --pdf/--text/--email`, `verwerfen`, `sperre`, `kunde`, `basiszins`, `historie` (`tests/test_cli_mahnwesen.py`) — **Akzeptanz 7**.

### Abschluss

- [x] `pytest` (744 bestanden, 1 übersprungen), `ruff check`, `ruff format --check` (ohne Cache), `mypy` grün; Checkboxen abgehakt; Doku-Bausteine unten aktuell; Probelauf beider Befehlsgruppen unter `/tmp` (SEPA-Datei gegen das XSD geprüft, Mahn-PDF angesehen).

### Akzeptanzkriterien → Tests

| # | Kriterium | Beleg |
|---|-----------|-------|
| 1 | Skontoposten zuerst, Grund je Position | `test_zahlung_vorschlag.py::test_skontoposten_zuerst_mit_grund` |
| 2 | Sammelüberweisung schemakonform | `test_zahlung_sepa.py::test_pain001_ist_schemakonform_nach_dk_tvs_gbic_5`, `::test_pain001_entspricht_der_soll_datei` — Annahme durch eine Bank **nicht** belegt (Grenzen) |
| 3 | Posten nie zweimal in einem eingereichten Lauf | `test_zahlung_freigabe.py::test_posten_nie_zweimal_in_einem_aktiven_lauf`, `test_zahlung_pruefung.py::test_doppelter_posten_wird_auch_an_der_sperre_vorbei_erkannt`, `test_zahlung_datei.py::test_datei_macht_den_lauf_eingereicht_und_bleibt_byte_gleich` |
| 4 | Abweichende IBAN blockiert mit klarer Meldung | `test_zahlung_pruefung.py::test_abweichende_iban_auf_der_rechnung_blockiert_mit_klarer_meldung`, `::test_stammsatz_nach_anlage_geaendert_blockiert`, `test_cli_zahlung.py::test_abweichende_iban_blockiert_mit_klarer_meldung` |
| 5 | Freigegebener Lauf nur stornierbar, mit Protokoll | `test_zahlung_freigabe.py::test_freigegebener_lauf_nur_stornierbar_mit_protokoll`, `::test_uebergaenge_in_falscher_reihenfolge_werden_abgelehnt`, `test_zahlung_datei.py::test_aenderung_nach_der_freigabe_wird_erkannt` |
| 6 | Stufen mit korrekten Verzugszinsen und Gebühren | `test_mahnwesen_lauf.py::test_b2b_posten_durchlaeuft_die_stufen_mit_zinsen_pauschale_und_gebuehren`, `::test_b2c_ohne_pauschale_mit_gebuehren`, `test_mahnwesen_zinsen.py::test_ueber_den_wechsel_des_basiszinssatzes_am_1_juli_2026` |
| 7 | Ohne Live-Bankanbindung bis zur Datei | `test_cli_zahlung.py::test_von_vorschlag_bis_zur_sepa_datei`, `test_cli_mahnwesen.py::test_mahnstufen_bis_zum_versendeten_schreiben` |

## Grenzen

- **Annahme durch eine Bank nicht geprüft.** Die Datei besteht das offizielle DK-Schema (GBIC_5) und
  folgt den Belegungsregeln der Anlage 3, wurde aber bei keiner Bank eingereicht (Auftrag: keine
  echten Bankdaten). Bankindividuelle Zusatzprüfungen (z.B. Ausführungstermin nur an
  TARGET2-Geschäftstagen, Limits) kann accounti nicht vorwegnehmen.
- **Keine Einreichung über den Bank-Provider.** `bank/` blieb unverändert; `--einreichen` aus der
  Spec fehlt. Der Dateiweg (`zahlung sepa --datei`) ist der einzige Weg.
- **Sammelbuchung:** `BtchBookg=false` wirkt nur mit Vereinbarung mit der Bank. Bucht die Bank den
  Lauf als einen Sammelposten, kann `opos zuordnen` ihn nicht automatisch auf die Posten verteilen
  (nur Summen bis 4 Posten als Vorschlag) — dann bleiben Läufe „eingereicht“, bis die Posten von
  Hand ausgeglichen sind.
- **Ausführungsdatum:** Wochenenden und Feiertage werden nicht verschoben; das macht die Bank.
  `zahlung pruefen/freigeben/sepa` prüfen gegen das heutige Datum — ein Lauf mit Termin in der
  Vergangenheit muss storniert und neu angelegt werden.
- **Storno nach dem Einreichen** gibt die Posten wieder frei. Ob die Datei schon bei der Bank
  hochgeladen wurde, weiß accounti nicht; die CLI weist darauf hin, den Auftrag dann bei der
  Bank zurückzurufen — sonst droht beim nächsten Lauf eine Doppelzahlung.
- **Unveränderbarkeit:** ORM-Sperren und (unter SQLite) Trigger schützen vor Änderungen über
  accounti; wer die Datenbank direkt mit SQL ändert, wird vom Freigabe-Hash beim Erzeugen der
  Datei aufgehalten, nicht vorher.
- **Empfängerüberprüfung (VOP)** findet bei der Bank statt; accounti vergleicht nur die IBAN mit
  dem Stammsatz und der Rechnung, nicht den Kontoinhabernamen.
- **Nicht im Umfang (Spec 8):** Lastschrift (`pain.008`), Echtzeitüberweisung, Fremdwährung (wird
  blockiert), Verrechnung von Gutschriften (werden nur gelistet), Rückruf eingereichter Aufträge,
  Liquiditätsplanung, gerichtliches Mahnverfahren, Inkasso.
- **Schema-Lizenz:** Das XSD ist Material der Deutschen Kreditwirtschaft/SIZ, frei als
  Implementierungshilfe veröffentlicht, ohne ausdrückliche Lizenz; es liegt unverändert und nur
  als Testdatei im Repository (Quelle und Prüfsumme in `tests/daten/zahlung/QUELLE.txt`). Vor
  einer Veröffentlichung sollte das geklärt werden; notfalls wird die Datei wie die Prüfwerkzeuge
  per Skript mit Prüfsumme geladen statt eingecheckt.
- **Verzugsbeginn vereinfacht:** Zinsen laufen ab dem Tag nach Fälligkeit (+ `verzug_nach_tagen`).
  Ob tatsächlich Verzug besteht (kalendermäßige Zahlungsfrist vereinbart, Mahnung zugegangen,
  30-Tage-Regel, Hinweis an Verbraucher), prüft accounti nicht. Wer konservativ sein will, setzt
  `verzug_nach_tagen: 30` oder schaltet Zinsen erst ab der 1. Mahnung ein.
- **Zinsmethode:** act/365 auch im Schaltjahr; act/act ergäbe 2024/2028 minimal weniger.
- **Basiszinssatz ab 01.01.2027 fehlt** zwangsläufig; er muss nach der Bekanntgabe Ende Dezember
  in `mahnwesen.basiszinssaetze` nachgetragen werden (oder per Code-Update), sonst bricht die
  Zinsberechnung für Zeiten ab 2027 mit klarer Meldung ab.
- **B2B/B2C** ist eine Heuristik, solange der Kontakt nicht ausdrücklich eingestuft ist; ohne
  Hinweis gilt „Verbraucher“ (niedrigerer Zins, keine Pauschale).
- **Mahnkosten sind Konfiguration, keine Rechtsberatung** — z.B. sind die Kosten der
  verzugsbegründenden Erstmahnung nach Rechtsprechung nicht ersatzfähig; die Standardwerte (0 / 5 /
  10 €) folgen dem Beispiel der Spec.
- **Teilzahlungen** fließen nur über Zahlungszuordnungen in die Zinsberechnung ein; ein von Hand
  verringerter Restbetrag gilt rückwirkend (zu niedrige Zinsen, nie zu hohe).
- **Je Posten eine Mahnung**, keine Sammelmahnung je Kunde; keine Mahnsperre je einzelnem Posten
  (nur je Kontakt). Die Pauschale gilt je Forderung (Posten) und steht in jeder Mahnung mit Verzug
  erneut als dieselbe Forderung, nicht zusätzlich.
- **E-Mail-Versand** ist nur gegen einen Test-Versandweg geprüft, nicht gegen einen echten
  SMTP-Server (Auftrag); er nutzt den bereits erprobten SMTP-Weg der E-Rechnung.
- **Gebühren kumuliert:** Eine Mahnung verlangt die Gebühren aller Stufen bis zu ihrer (Annahme:
  frühere Mahngebühren bleiben geschuldet). Wer das anders will, setzt die Gebühren je Stufe
  entsprechend.
- **Postgres:** Eindeutiger Index und ORM-Sperren gelten; die Trigger für das Protokoll gibt es wie
  beim USt-IdNr.-Protokoll nur unter SQLite.
- **Keine Alembic-Migration** (entsteht beim Zusammenführen); neue Tabellen: `zahlungslaeufe`,
  `zahlungen`, `zahlungslauf_protokoll`, `zahlungssperren`, `zahlung_iban_klaerungen`,
  `mahnungen`, `mahn_kontakte`.

## Doku-Bausteine

### README — Statuszeilen in der Feature-Tabelle „Buchen & Zahlen“

```markdown
| ✅ | **Zahlungsverkehr** | Zahlungsvorschlag mit Skonto zuerst und Grund je Position, Zahlungslauf mit blockierender Prüfung (IBAN ≠ Stammsatz oder Rechnung stoppt), Freigabe (optional Vier-Augen) und Storno mit Protokoll, SEPA-Sammelüberweisung `pain.001.001.09` (DK GBIC_5) als Datei |
| ✅ | **Mahnwesen** | Konfigurierbare Stufen, Verzugszinsen nach § 288 BGB mit datiertem Basiszinssatz, 40-€-Pauschale im B2B, Mahnschreiben als PDF/Text/E-Mail, Mahnstufe am offenen Posten |
```

### README — Nutzungsblock (nach „Offene Posten“)

````markdown
### Zahlungsverkehr

```bash
accounti zahlung vorschlag --stichtag 2026-10-21      # Skonto zuerst, Grund je Position
accounti zahlung anlegen --stichtag 2026-10-21        # Entwurf = Lauf 1
accounti zahlung entfernen 1 3                         # Position 3 nicht zahlen (nur im Entwurf)
accounti zahlung pruefen 1                             # blockierend: IBAN, Betrag, Sperre, Dubletten
accounti zahlung freigeben 1 --von "Erika Muster"      # mit zahlung.vier_augen: zweite Person nötig
accounti zahlung sepa 1 --datei ueberweisung.xml      # pain.001.001.09 → im Onlinebanking hochladen
accounti opos zuordnen                                 # Kontoumsätze gleichen die Posten aus
accounti zahlung abgleichen                            # Lauf → ausgeführt
accounti zahlung stornieren 1 --grund "doppelt"       # freigegebene Läufe: nur Storno, mit Protokoll
accounti zahlung sperre 70003 --grund "Reklamation"   # Kreditor vom Zahlungsverkehr ausnehmen
```

Weicht die IBAN der Rechnung vom Stammsatz ab, stoppt der Lauf — so funktionieren gefälschte
Rechnungen. Nach einem Rückruf beim Lieferanten auf bekanntem Weg: Stammsatz ändern
(`accounti kontakte bearbeiten 70003 --iban …`) oder mit `accounti zahlung iban-klaeren 1 2
--grund "…"` festhalten, dass an die Stammsatz-IBAN gezahlt wird.

### Mahnwesen

```bash
accounti mahnwesen lauf --stichtag 2026-10-21          # Mahnentwürfe mit Zinsen, Pauschale, Gebühren
accounti mahnwesen zeigen 7                            # Mahnschreiben als Text
accounti mahnwesen versenden 7 --pdf mahnung-7.pdf     # oder --text, --email; Mahnstufe am Posten +1
accounti mahnwesen kunde 10001 --unternehmer           # B2B: 9 Prozentpunkte + 40 € Pauschale
accounti mahnwesen sperre 10002 --grund "Ratenzahlung" # Kunde vom Mahnlauf ausnehmen
accounti mahnwesen basiszins                           # Basiszinssätze mit Gültigkeitszeitraum
accounti mahnwesen historie 10001                      # versendete Mahnungen eines Kunden
```
````

### CHANGELOG

```markdown
### Hinzugefügt
- **Zahlungsverkehr & Mahnwesen** (Baustein 6): `accounti zahlung vorschlag` schlägt offene
  Verbindlichkeiten zum Stichtag vor — Skontofristen vor Nettofälligkeiten, mit Grund je Position
  und Liste der ausgeschlossenen Posten; Zahlungsläufe (`anlegen`, `entfernen`, `pruefen`,
  `freigeben`, `stornieren`) mit Zustandsautomat Entwurf → freigegeben → eingereicht → ausgeführt,
  optionalem Vier-Augen-Prinzip, Freigabe-Hash und Protokoll, das nur wachsen kann; harte Prüfung
  vor Freigabe und Datei: IBAN abweichend vom Stammsatz oder von der Rechnung, Prüfziffer,
  Zahlungssperre, unbestätigter Kontakt, Betrag/Skontofrist, Höchstbetrag, SEPA-Land, Währung,
  Doppelzahlung (auch per eindeutigem Index); `accounti zahlung sepa --datei` schreibt die
  SEPA-Sammelüberweisung als `pain.001.001.09` nach DK-TVS GBIC_5 (DFÜ-Abkommen Anlage 3 V3.9/26.11),
  im Test gegen das offizielle Schema geprüft; `zahlung abgleichen` erkennt ausgeführte Läufe,
  sobald `opos zuordnen` die Posten ausgeglichen hat; `zahlung sperre`, `zahlung iban-klaeren`.
  `accounti mahnwesen lauf` mahnt überfällige Forderungen in konfigurierbaren Stufen (Karenz,
  Mindestbetrag, Stufenabstand, Mahnsperre) mit Verzugszinsen nach § 288 BGB (Basiszinssatz-Tabelle
  der Bundesbank mit Gültigkeitszeiträumen, Teilzahlungen zeitanteilig), 40-€-Pauschale bei
  Unternehmern mit Anrechnung der Mahngebühren; Mahnschreiben als PDF, Text oder E-Mail
  (`mahnwesen versenden`), Mahnstufe am offenen Posten, Historie (`mahnwesen historie`),
  B2B/B2C-Einstufung (`mahnwesen kunde`). Neue, optionale Abschnitte `zahlung` und `mahnwesen`

### Geändert
- Offene Posten tragen jetzt ihre Mahnstufe aus dem Mahnwesen (Feld gab es schon, es wurde bisher
  nie gesetzt)

### Behoben
- —
```

### docs/bauplan.md — Absatz nach Baustein 5, Statuszeile 6 auf „✅ fertig“

```markdown
**Baustein 6 ist fertig:** Zahlungsvorschlag mit Skonto-Vorrang, Zahlungslauf mit blockierender
Prüfung, Freigabe (optional Vier-Augen) und Storno mit Protokoll, SEPA-Sammelüberweisung als
`pain.001.001.09` nach DK-TVS GBIC_5 sowie Mahnwesen mit Stufen, Verzugszinsen nach § 288 BGB,
B2B-Pauschale und Mahnschreiben ([Plan](plans/2026-10-25-zahlungsverkehr-mahnwesen.md)). Offen
als Erweiterungen: Einreichung über den Bank-Provider (braucht FinTS aus Baustein 5),
Sammelmahnung je Kunde, Verrechnung von Gutschriften im Zahlungslauf.
```

### docs/architektur.md — Modulabschnitt (ersetzt „`zahlung/` und `mahnwesen/` *(geplant …)*“)

```markdown
### `zahlung/` und `mahnwesen/` *(vorhanden — [Baustein 6](specs/2026-08-10-zahlungsverkehr-mahnwesen.md))*

`zahlung/vorschlag.py` erzeugt aus offenen Verbindlichkeiten die Vorschlagsliste zum Stichtag:
Skontoposten, sobald ihre Skontofrist in den Planungshorizont (`zahlung.vorlauf_tage`) fällt, vor
fälligen Posten, mit Grund je Position; Gutschriften, gesperrte Kontakte und Posten aktiver Läufe
werden mit Grund ausgeschlossen. `zahlung/freigabe.py` führt den Zahlungslauf als Zustandsautomaten
(Entwurf → freigegeben → eingereicht → ausgeführt, Storno aus den ersten drei) mit Protokoll
(`zahlungslauf_protokoll`, nur anfügen), optionalem Vier-Augen-Prinzip und Freigabe-Hash; die
Zahlungen frieren Empfänger, IBAN, Betrag und Verwendungszweck ein und sind nach der Freigabe am
ORM gesperrt; ein eindeutiger Index auf `zahlungen.sperre` lässt einen Posten nie in zwei aktive
Läufe. `zahlung/pruefung.py` prüft blockierend — eine IBAN, die vom Stammsatz oder von der Rechnung
abweicht, stoppt den Lauf, bis der Stammsatz geändert oder die Abweichung mit Grund geklärt ist.
`zahlung/sepa.py` schreibt `pain.001.001.09` nach DK-TVS GBIC_5 (DFÜ-Abkommen Anlage 3), speichert
die Datei im Lauf und gibt sie nur noch byte-gleich aus. Ausgeglichen wird nie hier, sondern über
den Bankumsatz (`opos zuordnen`); `zahlung abgleichen` setzt danach „ausgeführt“. Die Einreichung
über den Bank-Provider fehlt noch — der Dateiweg funktioniert ohne jede Bankverbindung.

`mahnwesen/` liest Stufen aus dem Abschnitt `mahnwesen` (Karenz, Mindestbetrag, Stufenabstand,
Gebühr und Zinsen je Stufe), ermittelt je überfälligem Posten die nächste Stufe (keine wird
übersprungen), stuft Kunden als Unternehmer oder Verbraucher ein (Kontakt → Ausgangsrechnung →
USt-IdNr. → Standard Verbraucher) und rechnet Verzugszinsen nach § 288 BGB taggenau (act/365)
mit der Basiszinssatz-Tabelle aus `mahnwesen/basiszins.py` — jeder Satz mit Gültigkeitszeitraum,
Teilzahlungen aus den Zahlungszuordnungen zeitanteilig, die 40-€-Pauschale mit Anrechnung der
Mahngebühren. Mahnungen sind Entwürfe, bis sie versendet werden (PDF mit fpdf2, Text oder E-Mail
über den Versandweg aus `erechnung/versand.py`); dann zählt die Mahnstufe am offenen Posten hoch,
das PDF liegt im Belegarchiv, und die versendeten Mahnungen sind die Historie.
```

Zusätzlich in der Tabelle „Datenmodell“ die Zeile `Zahlung` ergänzen:

```markdown
| `Zahlungslauf` | Nr., Status (Entwurf → freigegeben → eingereicht → ausgeführt / storniert), Ausführungstag, Auftraggeber, Freigabe-Hash, SEPA-Datei | → `Zahlung`, Protokoll |
| `Zahlung` | Lauf, Posten, Empfänger, IBAN, Betrag, Skonto, Verwendungszweck, EndToEndId | → `OffenerPosten`, `Kontakt` |
| `Mahnung` | Nr., Stufe, Datum, Rest, Zinsen mit Abschnitten, Pauschale, Gebühren, Frist, B2B/B2C mit Grund, Status, Datei-Hash | → `OffenerPosten`, `Kontakt` |
```

### config/accounti.example.yaml — neue Abschnitte

```yaml
# Zahlungsverkehr (optional — ohne diesen Abschnitt gelten die Standards)
zahlung:
  vorlauf_tage: 3              # Skontofristen und Fälligkeiten so weit voraus einplanen
  skonto_ziehen: true          # Skonto nutzen, solange die Frist läuft
  # mindestbetrag: 1.00        # Vorschlag: kleinere Posten weglassen
  # hoechstbetrag: 50000.00    # Vorschlag: größere Posten weglassen
  # hoechstbetrag_zahlung: 25000.00   # Prüfung: größere Einzelzahlungen blockieren
  vier_augen: false            # true: zwei verschiedene Personen geben frei
  einzelbuchung: true          # BtchBookg=false — wirkt nur mit Vereinbarung mit der Bank
  # auftraggeber:              # Standard: mandant.name und mandant.bank
  #   name: "Meine Firma GmbH"
  #   iban: "DE89 3704 0044 0532 0130 00"
  #   bic: "COBADEFFXXX"

# Mahnwesen (optional — Mahngebühren sind Konfiguration, keine Rechtsberatung)
mahnwesen:
  karenztage: 3                # so lange nach Fälligkeit wird nicht gemahnt
  mindestbetrag: 10.00         # kleinere Reste nicht mahnen
  stufenabstand_tage: 7        # Mindestabstand zur letzten Mahnung
  zahlungsfrist_tage: 10       # neue Frist im Mahnschreiben
  verzug_nach_tagen: 0         # Verzugszinsen ab Fälligkeit + n Tagen (§ 286 Abs. 3: 30)
  unbekannt_als: verbraucher   # oder unternehmer — wenn weder Kontakt noch Rechnung es sagen
  pauschale_b2b: 40.00         # § 288 Abs. 5 BGB
  pauschale_anrechnen: true    # Mahngebühren nur, soweit sie die Pauschale übersteigen
  stufen:
    - name: Zahlungserinnerung
      ab_tagen: 5
      gebuehr: 0.00
      verzugszinsen: false
    - name: 1. Mahnung
      ab_tagen: 14
      gebuehr: 5.00
      verzugszinsen: true
    - name: 2. Mahnung
      ab_tagen: 28
      gebuehr: 10.00
      verzugszinsen: true
      # text: "…{nummer} … {summe} … bis zum {frist} …"   # eigener Brieftext; Platzhalter:
      #   {kunde} {nummer} {datum} {faellig} {betrag} {summe} {frist} {firma} {stufe}
  # basiszinssaetze:           # neue Sätze nach Bekanntgabe der Bundesbank
  #   - ab: 2027-01-01
  #     satz: 1.52
```
