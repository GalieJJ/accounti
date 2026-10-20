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
| SEPA-Raum | 27 EU-Staaten, 3 EWR-Staaten (IS, LI, NO) und 11 Nicht-EWR-Länder (AL, AD, MD, MC, ME, MK, SM, RS, CH, GB, VA) laut EPC409-09 *EPC List of SEPA Scheme Countries* v8.0 vom 24.12.2025; IBAN-Präfixe zusätzlich GI (Gibraltar); Guernsey/Jersey/Isle of Man führen GB-IBANs, die französischen Überseegebiete FR-IBANs. **IBAN-only nur innerhalb des EWR** — für Zahlungen in die Schweiz, nach Monaco, San Marino, Andorra, in den Vatikan und ins Vereinigte Königreich ist „weiterhin der BIC zusätzlich zur IBAN anzugeben“ (Deutsche Bundesbank, FAQ SEPA); das SCT-Regelwerk verlangt dort zusätzlich die Anschrift des Auftraggebers |
| Empfängerüberprüfung | Seit 09.10.2025 prüft die Bank bei Überweisungen Name ↔ IBAN (Verification of Payee); für Sammler bietet die DK eigene Auftragsarten (CTV) — das geschieht beim Hochladen in der Bank, nicht in accounti |

### Verzugszinsen und Basiszinssatz

| | |
|---|---|
| § 288 Abs. 1 BGB | Verzugszinssatz für das Jahr **5 Prozentpunkte** über dem Basiszinssatz |
| § 288 Abs. 2 BGB | Rechtsgeschäfte ohne Verbraucher, Entgeltforderungen: **9 Prozentpunkte** |
| § 288 Abs. 5 BGB | Schuldner kein Verbraucher: **Pauschale 40 €**; sie ist auf einen Schadensersatz für Kosten der Rechtsverfolgung **anzurechnen** (Satz 3) — Mahngebühren werden also nur verlangt, soweit sie 40 € übersteigen |
| §§ 280 Abs. 1, 2, 286 BGB | Mahnkosten ersetzt der Schuldner nur als **Verzugsschaden** — also nur für Mahnungen, die hinausgehen, wenn er schon in Verzug ist. Die Mahnung, die den Verzug erst begründet (§ 286 Abs. 1), liegt davor und ist nicht erstattungsfähig |
| § 286 BGB | Verzug durch Mahnung nach Fälligkeit (eine Mahnung vor Fälligkeit ist unwirksam), ohne Mahnung bei kalendermäßig bestimmter Zeit (Abs. 2 Nr. 1 — die Zeit muss vereinbart sein; ein einseitig auf der Rechnung gesetztes Zahlungsziel genügt nicht, BGH III ZR 91/07), spätestens 30 Tage nach Fälligkeit und Zugang der Rechnung (Abs. 3; bei Verbrauchern nur mit Hinweis in der Rechnung). IHK-Merkblätter („Mahnung und Verzug“, z.B. IHK Bonn): eine Frist in der Mahnung ist nicht nötig; ob eine gesetzte Frist den Verzug hinausschiebt, ließ sich nicht verbindlich klären |
| § 247 BGB | Basiszinssatz ändert sich zum 1. Januar und 1. Juli; die Bundesbank gibt ihn im Bundesanzeiger bekannt |
| Quelle Gesetzestexte | [gesetze-im-internet.de §§ 247, 286, 288 BGB](https://www.gesetze-im-internet.de/bgb/__288.html), abgerufen 20.10.2026 |
| Basiszinssätze | Tabelle der Deutschen Bundesbank, [Basiszinssatz nach § 247 BGB](https://www.bundesbank.de/de/bundesbank/basiszinssatz-nach---247-bgb-607820), abgerufen 20.10.2026: 01.07.2026 **1,52 %** · 01.01.2026 1,27 % · 01.07.2025 1,27 % · 01.01.2025 2,27 % · 01.07.2024 3,37 % · 01.01.2024 3,62 % · 01.07.2023 3,12 % · 01.01.2023 1,62 % · 01.07.2016–01.07.2022 −0,88 % · … zurück bis 01.07.2002 2,47 % (vollständig in `mahnwesen/basiszins.py`; einmalig von Hand abgeglichen, kein automatischer Abgleich). Der Satz ab 01.01.2027 ist noch nicht bekannt |
| Zinstage | taggenau; ob das Jahr in Schaltjahren 365 oder 366 Tage hat, wird in Ratgebern und Prüfungsunterlagen unterschiedlich gehandhabt (z.B. IHK München „act/act“, andere durchgängig 365) — eine verbindliche Quelle war nicht zu finden, siehe Entscheidung |

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Format | `pain.001.001.09` nach DK-TVS GBIC_5, ein `PmtInf` je Lauf (Sammler), `PmtMtd=TRF`, `SvcLvl=SEPA`, `ChrgBr=SLEV` | Anlage 3 V3.9/V26.11; GBIC_5 gilt 2026 durchgehend |
| Schemaprüfung | im Test gegen das unveränderte offizielle XSD mit `javax.xml.validation` (Java ist durch KoSIT/Mustang ohnehin Pflicht in der CI; Quelltextmodus `java XsdPruefung.java`, keine neue Python-Abhängigkeit); ohne Java übersprungen, in der CI (`ACCOUNTI_PRUEFWERKZEUGE_PFLICHT=1`) Pflicht. Zusätzlich Golden-Test gegen `pain001_soll.xml` | Spec 6; die Standardbibliothek kann kein XSD |
| Zeichen | Namen und Verwendungszweck auf den DK-Zeichensatz (Latin + Umlaute, ß, `& * $ %`), andere Buchstaben ohne Akzent (é → e), Rest → Leerzeichen; Referenzen nur Latin-Pattern, ohne führendes/abschließendes `/` und ohne `//` | Banken müssen den DK-Satz annehmen; nichts geht verloren, was eine Bank nicht lesen kann |
| Sammelbuchung | `zahlung.einzelbuchung: true` (Standard) schreibt `BtchBookg=false` | Jede Überweisung erscheint einzeln mit Empfänger und Rechnungsnummer auf dem Kontoauszug — nur so kann `opos zuordnen` sie dem Posten zuordnen. Ohne Vereinbarung bucht die Bank trotzdem als Sammler (Grenzen) |
| BIC | Empfänger ohne BIC (IBAN-only) — deshalb **nur Empfänger im EWR**: IBANs aus den Nicht-EWR-Ländern des SEPA-Raums (CH, GB, GI, MC, SM, AD, VA, AL, MD, ME, MK, RS) blockiert die Prüfung („Zahlung entfernen und im Onlinebanking einzeln überweisen“). Auftraggeber-BIC aus `zahlung.auftraggeber.bic` bzw. `mandant.bank.bic`, sonst `NOTPROVIDED` | IBAN-only gilt nur im EWR; für Nicht-EWR-Länder verlangen SCT-Regelwerk und Bundesbank (FAQ SEPA) den BIC der Empfängerbank und die Anschrift des Auftraggebers — Kontakte haben kein BIC-Feld (Runde 1, Befund 8); `DbtrAgt` ist laut TVS Pflicht |
| Empfängeradresse | `PstlAdr` nur, wenn Ort und Land bekannt: `StrtNm`/`BldgNb` (Hausnummer abgetrennt), `PstCd`, `TwnNm`, `Ctry` | strukturiert ist der empfohlene Weg; optional im SEPA-Raum |
| IDs | `MsgId` = `ACCOUNTI-<Lauf>-<JJJJMMTThhmmss>`, `PmtInfId` = `ACCOUNTI-<Lauf>`, `EndToEndId` = Rechnungsnummer des Lieferanten (bereinigt), sonst `ACCOUNTI-<Lauf>-<Pos>` | MsgId muss je Datei neu sein (Dublettenschutz der Bank); die Rechnungsnummer hilft dem Lieferanten |
| Verwendungszweck | `<Rechnungsnummer> vom <Belegdatum>`, bei Skonto `abzgl. <x> EUR Skonto` (max. 140) | Spec 4.3; damit trifft `opos zuordnen` Stufe A (Referenz) |
| Vorschlag | Stichtag = geplanter Ausführungstag; Planungshorizont `vorlauf_tage` (Standard 3). Skontoposten (Skonto > 0, Frist ≥ Stichtag, Posten unberührt) werden vorgeschlagen, sobald ihre **Skontofrist** in den Horizont fällt — auch wenn das Nettoziel Wochen entfernt ist; andere, sobald sie fällig sind. Reihenfolge: Skonto nach Frist, dann Fälligkeit. Grund je Position („Skontofrist endet morgen: 2 % = 3,45 € sparen; netto fällig am …“) | Spec 4.1: Skonto hat Vorrang; nicht früher zahlen als nötig |
| Ausgeschlossen | mit Grund gelistet: Zahlungssperre, schon in einem Lauf, **Bankumsatz als Zahlung vorgeschlagen** (`opos zuordnen`, noch nicht bestätigt), Gutschrift (Betrag < 0), Betragsfilter | Nachvollziehbarkeit; Gutschriften verrechnet der Mensch; ein vorgeschlagener Umsatz kann heißen, dass schon bezahlt ist (Lastschrift, Überweisung von Hand) |
| Lauf | `zahlungslaeufe` + `zahlungen` + `zahlungslauf_protokoll`; laufende Nummer je Lauf (`zahlung pruefen 42`). Zahlung friert Empfänger, IBAN, Adresse, Betrag, Skonto, Restbetrag und Verwendungszweck bei der Anlage ein | was freigegeben wird, ist genau das, was in der Datei steht |
| Zustände | Entwurf → freigegeben → eingereicht → ausgeführt; storniert aus Entwurf, freigegeben, eingereicht; alles andere `ZustandError`. Ein Wechsel schreibt nur, wenn der Lauf noch im gelesenen Status ist; die Versionsspalte `zahlungslaeufe.version` macht daraus ein `UPDATE … WHERE version = …` — ein zweiter, gleichzeitiger Prozess scheitert mit `ZustandError`. Der Kopfsatz ist nach der Freigabe am ORM gesperrt (nur Status in erlaubter Richtung, Datei-Felder nur beim Einreichen) | Spec 4.4; zwei gleichzeitige `zahlung sepa` dürfen nicht zwei Dateien erzeugen |
| Eingereicht | mit dem Schreiben der Datei; die XML wird im Lauf gespeichert und bei erneutem `zahlung sepa` byte-gleich ausgegeben (gleiche `MsgId`), nachdem sie mit dem protokollierten SHA-256 verglichen wurde. Die CLI schreibt die Datei **erst nach dem Commit**; vor dem Statuswechsel wird die erzeugte Datei auf leere Elemente geprüft | ab der Datei kann Geld fließen; ein erneutes Hochladen weist die Bank über die `MsgId` ab; ohne Commit darf es keine Datei geben, sonst entstünde beim nächsten Aufruf eine zweite mit neuer `MsgId` |
| Ausgeführt | `zahlung abgleichen`: ein Lauf ist ausgeführt, wenn bei jedem Posten der Rest um mindestens den gezahlten Betrag gesunken ist. accounti gleicht **nicht** selbst aus — das macht der Bankumsatz über `opos zuordnen` | Auftrag: Ausgleich nur über den Bankumsatz; keine Doppelbuchung |
| Doppelzahlung | dreifach: Vorschlag lässt Posten aktiver Läufe weg; Anlage lehnt sie ab; **eindeutiger Index** `zahlungen.sperre` (= Posten-ID, solange der Lauf nicht storniert oder ausgeführt ist) — hält auch bei parallelen Prozessen. Die Prüfung meldet zusätzlich doppelte Posten im selben Lauf | Akzeptanz 3 |
| Prüfung | blockierend, Grund je Befund: Auftraggeber-IBAN und -Name; Ausführungsdatum nicht in der Vergangenheit; Posten offen und unverändert; Betrag = Rest oder Rest − Skonto mit Frist ≥ Ausführung; Höchstbetrag je Zahlung (`hoechstbetrag_zahlung`); Kontakt bestätigt (nicht „zur Prüfung“); Zahlungssperre; IBAN im Stammsatz vorhanden und mit gültiger Prüfziffer; **IBAN der Zahlung = Stammsatz**; **IBAN auf der Rechnung = Stammsatz**; IBAN-Land im **EWR**; Währung EUR; Posten in keinem anderen aktiven Lauf; **kein Bankumsatz als Zahlung vorgeschlagen**; Empfängername, Auftraggebername und Verwendungszweck nach der Bereinigung auf den DK-Zeichensatz **nicht leer** (kyrillische/griechische Namen → „im Stammsatz in lateinischer Schrift pflegen“) | Spec 4.2, Akzeptanz 4; ein leeres `<Nm/>` ist schemawidrig, die Bank wiese die ganze Sammeldatei ab (Runde 1, Befunde 5/9, 6/17) |
| IBAN-Abweichung | Meldung nennt Rechnung, beide IBANs und was zu tun ist („beim Lieferanten auf bekanntem Weg bestätigen …“). Ausweg: Stammsatz nach Rückruf ändern (`kontakte bearbeiten --iban`) **oder** `zahlung iban-klaeren <Lauf> <Pos> --grund … --von …` — dann wird an die Stammsatz-IBAN gezahlt, die Klärung gilt nur für genau dieses IBAN-Paar und steht im Protokoll | genau so funktionieren gefälschte Rechnungen; ein Mensch entscheidet, dokumentiert |
| Freigabe | prüft erneut; speichert einen SHA-256 über Auftraggeber, Ausführungsdatum und alle Zahlungen (`freigabe_hash`); `zahlung sepa` prüft erneut und vergleicht den Hash | freigegeben = unveränderbar; auch direkte DB-Änderungen fallen auf |
| Vier-Augen | `zahlung.vier_augen: true` verlangt zwei verschiedene Personen; eine Freigabe gilt nur für den Inhalt (Hash), den sie gesehen hat. Wer freigibt, ist dann der **Anmeldename über die Benutzerkennung des Prozesses** (`pwd`, nicht `USER`/`LOGNAME`); `--von` mit einem anderen Namen wird abgelehnt, `ACCOUNTI_BENUTZER` zählt nicht. Optional `zahlung.freigeber`: nur diese Personen dürfen freigeben | Spec 4.4; im Einpersonenbetrieb aus. Freitext-Namen hätten eine Person zweimal freigeben lassen (Runde 1, Befunde 7/12) |
| Unveränderbar | Zahlungen eines nicht mehr entworfenen Laufs: Änderungen (außer der Freigabe der Sperre) und Löschen scheitern am ORM; Protokoll nur anfügen (ORM-Sperre, SQLite-Trigger wie beim USt-IdNr.-Protokoll) | Akzeptanz 5, Prinzip 6 |
| Person | `--von`, sonst `ACCOUNTI_BENUTZER`, sonst Anmeldename — außer beim Freigeben mit Vier-Augen (siehe dort) | bis Baustein 10 echte Benutzer bringt |
| Einreichung über Provider | nicht in diesem Paket — `bank/` bleibt unverändert, der Dateiweg ist der einzige | Auftrag; Spec: Dateiweg immer verfügbar |
| Konfiguration | Abschnitte `zahlung` und `mahnwesen` in `config/accounti.yaml` mit eigenen Ladern (`accounti.zahlung.konfiguration.lade_zahlung`, `accounti.mahnwesen.konfiguration.lade_mahnwesen`); ohne Abschnitt gelten Standards | Projektregel; die Spec nannte `config/mahnwesen.yaml` |
| Befehlsgruppen | `accounti zahlung …` und `accounti mahnwesen …` | Bereichsname; die Spec schrieb `accounti mahnen …` |
| Basiszinssatz | Tabelle mit **ab/bis** je Halbjahr in `mahnwesen/basiszins.py` (Bundesbank, Stand 20.10.2026), letzter Zeitraum bis 31.12.2026; neue Sätze per `mahnwesen.basiszinssaetze` (`ab`, `satz`, optional `bis`) ergänzbar, sie gehen vor. Zinstage ohne bekannten Satz → `BasiszinsUnbekanntError` mit Hinweis, statt still mit dem alten Satz zu rechnen | halbjährliche Änderung; alte Zeiträume bleiben rechenbar |
| Verzugsbeginn | erster Zinstag = frühester von: (a) Tag nach Fälligkeit, nur mit `mahnwesen.zahlungsziel_vereinbart: true` (§ 286 Abs. 2 Nr. 1 — ein Zahlungsziel nur auf der Rechnung reicht nicht, BGH III ZR 91/07); (b) erste **versendete** Mahnung nach Fälligkeit (§ 286 Abs. 1): Tag nach dem Zugang (Versand + `zugang_tage`, Standard 3), setzt sie eine Zahlungsfrist, erst Tag nach deren Ablauf; (c) 31. Tag nach Fälligkeit bzw. Zugang der Rechnung (Belegdatum + `zugang_tage`) (§ 286 Abs. 3) — bei Verbrauchern nur mit `hinweis_30_tage: true`. Kein Kandidat → kein Verzug: keine Zinsen, keine Pauschale, keine Gebühren, und der Brief behauptet keinen Verzug. Der Grund steht in der Mahnung („In Verzug seit …: …“) | Runde 1, Befund 2. Ob eine in der Mahnung gesetzte Frist den Verzug hinausschiebt, ist nicht eindeutig (IHK-Merkblätter: Frist nicht nötig) — accounti rechnet konservativ erst ab Fristablauf |
| Zinsen | ab dem Verzugsbeginn bis einschließlich Mahndatum; Abschnitte an jedem Basiszinswechsel und jeder Zahlung (Kapital = heutiger Rest + später gezahlte Beträge laut Zahlungszuordnung); je Abschnitt `Kapital × Satz × Tage / 365`, kaufmännisch auf Cent gerundet, Summe der Abschnitte | handrechenbar, Teilzahlungen werden zeitanteilig berücksichtigt; act/365 ist die verbreitete Praxis |
| B2B/B2C | Reihenfolge: Einstufung am Kontakt (`mahnwesen kunde --unternehmer/--verbraucher`) → Ausgangsrechnung aus accounti: `kunde.privat` → Verbraucher, USt-IdNr. oder Leitweg-ID des Empfängers → Unternehmer bzw. öffentlicher Auftraggeber; eine Rechnung **ohne** `privat` sagt nichts (das ist ihr Standard) → USt-IdNr. im Stammsatz → sonst `mahnwesen.unbekannt_als` (Standard `verbraucher`); der Grund steht in der Mahnung | zu hohe Zinsen gegenüber Verbrauchern wären eine unberechtigte Forderung; zu niedrige schaden nicht (Runde 1, Befund 3) |
| Pauschale | 40 € (`pauschale_b2b`) bei Unternehmern ab der ersten Stufe mit `verzugszinsen: true`, je Posten einmal; Mahngebühren werden nach § 288 Abs. 5 S. 3 angerechnet (`pauschale_anrechnen: true`): verlangt wird `max(0, Gebühren − 40)` zusätzlich | Gesetzeswortlaut |
| Gebühren | `gebuehr` je Stufe, **nur im Verzug** (`lauf.gebuehren_im_verzug`): die eigene, wenn am Mahndatum Verzug besteht, plus die der früheren Mahnungen des Postens, deren Versandtag nicht vor dem Verzugsbeginn liegt — die verzugsbegründende Mahnung kostet nichts. Eine Stufe ohne `verzugszinsen`, aber mit Gebühr ermittelt dafür den Verzug (Grund im Schreiben), verlangt aber weder Zinsen noch Pauschale; ihr Standardtext nennt dann den Gesamtbetrag statt nur den Rest | Mahnkosten sind Verzugsschaden (§§ 280 Abs. 2, 286 BGB); im Verzug versendete Mahnungen bleiben geschuldet (Runde 2, Befund 2) |
| Stufen | eine Stufe je Lauf, keine wird übersprungen: Stufe *n+1* greift, wenn Tage seit Fälligkeit ≥ `ab_tagen` der Stufe **und** > `karenztage` **und** seit dem **Versand** der letzten Mahnung ≥ `stufenabstand_tage` (Standard 7) **und** die Zahlungsfrist dieser Mahnung abgelaufen ist. Rest < `mindestbetrag` → keine Mahnung (Grund). Nach der letzten Stufe: Hinweis, keine weitere | Spec 4.5; „durchläuft die Stufen“; keine 1. Mahnung, solange die Frist der Erinnerung läuft (Runde 1, Befunde 4/11) |
| Mahnung | je Posten eine Mahnung (Entwurf → versendet / verworfen); beim Versenden: Mahnstufe am Posten hochgezählt (`repo_mahnwesen.setze_mahnstufe`), PDF ins Belegarchiv, Hash und Weg an der Mahnung — die versendeten Mahnungen sind die Historie. Versendet wird nur am Mahndatum oder bis `entwurf_gueltig_tage` (Standard 3, < `zahlungsfrist_tage`) danach, sonst „veraltet — verwerfen und Lauf wiederholen“; `mahnwesen versenden --am` hält den tatsächlichen Versandtag fest (nicht in der Zukunft, bei `--email` nur heute). Reihenfolge: Dateien und Archiv, dann die E-Mail, direkt danach der Status | Spec 4.5 [4]; Entwurf zählt nicht; ein spät versendeter Brief wäre rückdatiert; eine E-Mail lässt sich nicht zurückholen (Runde 1, Befunde 4, 10) |
| Ausnahmen | Mahnsperre am Kontakt, offener Mahnentwurf, Zahlung vorgeschlagen (`opos vorschlaege`), letzte Stufe erreicht, Mindestbetrag — jeweils mit Grund; Mahnsperre und vorgeschlagene Zahlung werden **beim Versand erneut** geprüft | nicht mahnen, was gerade bezahlt wurde oder inzwischen gesperrt ist (Runde 1, Befund 13) |
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

- [x] **Basiszinssatz** `mahnwesen/basiszins.py`: Tabelle lückenlos (einmalig am 20.10.2026 von Hand mit der Bundesbank-Seite abgeglichen — einen automatischen Abgleich gibt es nicht), Satz am Stichtag, Ergänzung/Korrektur aus der Konfiguration, Überschneidung, unbekannter Zeitraum → Fehler (`tests/test_mahnwesen_basiszins.py`).
- [x] **Verzugszinsen** `mahnwesen/zinsen.py`: handgerechnete Fälle B2B/B2C, über den Wechsel am 01.07.2026, Teilzahlung im Verzug, Zahlung nach dem Stichtag (`tests/test_mahnwesen_zinsen.py`).
- [x] **Konfiguration** `mahnwesen/konfiguration.py`: Stufen, Karenz, Mindestbetrag, Abstand, Pauschale, Texte mit geprüften Platzhaltern, Basiszins-Ergänzungen nur zum 1.1./1.7. (`tests/test_mahnwesen_konfiguration.py`).
- [x] **Modelle, Tabellen, Repository** `models/mahnwesen.py`, `db/tabellen_mahnwesen.py` (versendete Mahnungen am ORM gesperrt), `db/repo_mahnwesen.py` (`setze_mahnstufe` am offenen Posten).
- [x] **Stufen** `mahnwesen/stufen.py`: der Reihe nach, keine übersprungen, Karenz, Stufenabstand, Ausnahmen mit Grund (`tests/test_mahnwesen_stufen.py`).
- [x] **Mahnlauf, Einstufung B2B/B2C, Versand-Status** `mahnwesen/lauf.py`: ein Posten durchläuft Erinnerung → 1. → 2. Mahnung mit handgerechneten Zinsen, Pauschale und Gebühren (B2B und B2C), Pauschale ohne Anrechnung, kein Verzug → keine Pauschale, Teilzahlung aus der Zahlungszuordnung, Mahnstufe am Posten erst beim Versand (`tests/test_mahnwesen_lauf.py`) — **Akzeptanz 6**.
- [x] **Mahnschreiben** `mahnwesen/schreiben.py` und **Versand** `mahnwesen/versand.py`: Text und PDF (Inhalt per `pypdf` gelesen), eigene Texte, PDF ins Belegarchiv, E-Mail über einen Test-Versandweg, gescheiterte E-Mail ändert nichts (`tests/test_mahnwesen_schreiben.py`).
- [x] **CLI** `befehle/mahnwesen.py`: `lauf`, `liste`, `zeigen`, `versenden --pdf/--text/--email`, `verwerfen`, `sperre`, `kunde`, `basiszins`, `historie` (`tests/test_cli_mahnwesen.py`) — **Akzeptanz 7**.

### Abschluss

- [x] `pytest` (744 bestanden, 1 übersprungen), `ruff check`, `ruff format --check` (ohne Cache), `mypy` grün; Checkboxen abgehakt; Doku-Bausteine unten aktuell; Probelauf beider Befehlsgruppen unter `/tmp` (SEPA-Datei gegen das XSD geprüft, Mahn-PDF angesehen).

### Runde 1 — Befunde der Prüfung (20.10.2026)

Jede Behebung testgetrieben (Test zeigt den Fehler, dann der Fix).

- [x] **Doppelzahlung trotz vorgeschlagenem Bankumsatz** (Befunde 5, 9): `vorschlag.vorgeschlagene_zahlungen`; Vorschlag schließt aus, Prüfung blockiert (`test_zahlung_vorschlag.py::test_posten_mit_vorgeschlagener_zahlung_wird_ausgeschlossen`, `test_zahlung_pruefung.py::test_vorgeschlagene_zahlung_blockiert_freigabe_und_datei`).
- [x] **Nicht-EWR ohne BIC** (Befund 8): `iban.im_ewr`, Prüfung blockiert CH/GB/SM …; Soll-Datei mit FR- statt CH-Empfänger neu erzeugt, XSD-Prüfung grün (`test_zahlung_pruefung.py::test_iban_ausserhalb_des_ewr_blockiert`).
- [x] **Leeres `<Nm/>`** (Befunde 6, 17): Prüfung blockiert Namen/Verwendungszweck ohne erlaubte Zeichen; `sepa.leere_felder` prüft die fertige Datei vor dem Statuswechsel (`test_empfaengername_ohne_lateinische_zeichen_blockiert`, `test_auftraggebername_ohne_lateinische_zeichen_blockiert`, `test_zahlung_sepa.py::test_leere_pflichtfelder_werden_erkannt`).
- [x] **Vier-Augen umgehbar** (Befunde 7, 12): `freigabe.person_fuer_freigabe`, `betriebssystem_benutzer`, `zahlung.freigeber` (`test_zahlung_freigabe.py::test_vier_augen_person_kommt_aus_der_anmeldung`, `::test_nur_eingetragene_freigeber`, `test_cli_zahlung.py::test_vier_augen_ohne_von`).
- [x] **Datei vor dem Commit, Statuswechsel ohne Sperre** (Befund 18): Datei erst nach dem Commit, Wechsel nur aus dem gelesenen Status, Versionsspalte (`test_cli_zahlung.py::test_sepa_datei_erst_nach_dem_commit`, `test_zahlung_datei.py::test_zwei_gleichzeitige_dateien_nur_eine_gewinnt`, `::test_veralteter_kopfsatz_ueberschreibt_nichts`).
- [x] **Datei ohne Hash-Abgleich, Kopfsatz ohne ORM-Sperre** (Befund 14): (`test_zahlung_datei.py::test_gespeicherte_datei_wird_vor_der_ausgabe_mit_dem_hash_verglichen`, `::test_kopfsatz_nach_der_freigabe_am_orm_gesperrt`).
- [x] **Savepoint committet unter pysqlite** (Befund 19): `speichere_lauf` ohne Savepoint, bei Konflikt Rollback der Transaktion (`test_zahlung_freigabe.py::test_anlage_wird_erst_mit_dem_commit_gespeichert`). Dasselbe Muster in `db/repository.py`, `opos/verbuchung.py` und `bank/lauf.py` (außerhalb des Bausteins) → eigenes Ticket, siehe Grenzen.
- [x] **Verzugsbeginn nach § 286 BGB** (Befund 2): `lauf.verzugsbeginn`, Einstellungen `zahlungsziel_vereinbart`, `zugang_tage`, `hinweis_30_tage` statt `verzug_nach_tagen`; Brief ohne Verzug behauptet keinen (`test_mahnwesen_lauf.py::test_verzug_beginnt_mit_dem_zugang_der_erinnerung`, `::test_vereinbartes_zahlungsziel_verzug_ab_faelligkeit`, `::test_ohne_mahnung_und_ohne_vereinbarung_kein_verzug`, `test_mahnwesen_schreiben.py::test_mahnung_ohne_verzug_behauptet_keinen_verzug`).
- [x] **B2B aus `privat=False`** (Befund 3): (`test_mahnwesen_lauf.py::test_ausgangsrechnung_ohne_privat_und_ohne_ust_idnr_gilt_nicht_als_b2b`, `::test_ausgangsrechnung_mit_ust_idnr_oder_leitweg_id`).
- [x] **Folgestufe vor Fristablauf, Abstand ab Berechnung, veraltete Entwürfe** (Befunde 4, 11): (`test_mahnwesen_stufen.py::test_naechste_stufe_erst_nach_ablauf_der_frist`, `test_mahnwesen_lauf.py::test_b2b_posten_durchlaeuft_…` am 30.06./11.07., `::test_veralteter_entwurf_wird_nicht_versendet`, `test_cli_mahnwesen.py::test_versanddatum_und_dateifehler`).
- [x] **Mahnsperre nach dem Lauf** (Befund 13): (`test_mahnwesen_lauf.py::test_mahnsperre_nach_dem_lauf_stoppt_den_versand`, `::test_vorgeschlagene_zahlung_nach_dem_lauf_stoppt_den_versand`).
- [x] **E-Mail vor den Dateien** (Befund 10): (`test_mahnwesen_schreiben.py::test_email_erst_wenn_alles_lokale_geklappt_hat`).
- [x] Basiszins-Abgleich ehrlich beschrieben (Befund 15); Akzeptanzkriterium 2 ausdrücklich „teilweise erfüllt“ mit Prüfanleitung (Befunde 1, 8).
- [ ] Befund 16 (Dateiname des Plans) **nicht umgesetzt**: Die Pläne sind fortlaufend je Tag nummeriert (`2026-10-21-…` bis `2026-10-24-…` wurden ebenfalls am 20.10. angelegt); `2026-10-25` setzt diese Reihe fort.
- [x] `pytest` (775 bestanden, 1 übersprungen), `ruff check`, `ruff format --check`, `mypy` grün.

### Runde 2 — Befunde der Prüfung (20.10.2026)

- [x] **Mahngebühren ohne Verzug** (Befund 2): Gebühren nur für Mahnungen im Verzug, frühere Stufen nur, wenn sie nicht vor dem Verzugsbeginn versendet wurden; Stufen mit Gebühr ermitteln den Verzug auch ohne `verzugszinsen`; der Erinnerungstext nennt bei einer Gebühr den Gesamtbetrag (`test_mahnwesen_lauf.py::test_ohne_mahnung_und_ohne_vereinbarung_kein_verzug` — vorher Gebühr 5,00 als Soll —, `::test_gebuehren_nur_fuer_mahnungen_im_verzug`, `::test_gebuehr_einer_stufe_ohne_zinsen_nur_im_verzug`, `test_mahnwesen_schreiben.py::test_mahnung_ohne_verzug_behauptet_keinen_verzug`, `::test_erinnerung_mit_gebuehr_nennt_den_gesamtbetrag`).
- [ ] **Annahme der pain.001-Datei durch die Bank** (Befund 1): **nicht vom Reparierer schließbar** — dafür müsste eine Datei mit echten Daten bei einer echten Bank eingereicht werden, was accounti und seinen Agenten untersagt ist. Offen beim Nutzer, siehe „Bankprobe“; bis dahin ist 2b eine Grenze.
- [x] `pytest` (778 bestanden, 1 übersprungen), `ruff check`, `ruff format --check`, `mypy` grün.

### Akzeptanzkriterien → Tests

| # | Kriterium | Beleg |
|---|-----------|-------|
| 1 | Skontoposten zuerst, Grund je Position | `test_zahlung_vorschlag.py::test_skontoposten_zuerst_mit_grund` |
| 2 | Sammelüberweisung schemakonform **und von der Bank angenommen** — **teilweise erfüllt** | 2a schemakonform: `test_zahlung_sepa.py::test_pain001_ist_schemakonform_nach_dk_tvs_gbic_5`, `::test_pain001_entspricht_der_soll_datei`, `::test_leere_pflichtfelder_werden_erkannt`. 2b Annahme durch die Bank: **offen** — nicht durch einen Test belegbar; Bankprobe durch den Nutzer, siehe „Bankprobe“ |
| 3 | Posten nie zweimal in einem eingereichten Lauf | `test_zahlung_freigabe.py::test_posten_nie_zweimal_in_einem_aktiven_lauf`, `test_zahlung_pruefung.py::test_doppelter_posten_wird_auch_an_der_sperre_vorbei_erkannt`, `test_zahlung_datei.py::test_datei_macht_den_lauf_eingereicht_und_bleibt_byte_gleich` |
| 4 | Abweichende IBAN blockiert mit klarer Meldung | `test_zahlung_pruefung.py::test_abweichende_iban_auf_der_rechnung_blockiert_mit_klarer_meldung`, `::test_stammsatz_nach_anlage_geaendert_blockiert`, `test_cli_zahlung.py::test_abweichende_iban_blockiert_mit_klarer_meldung` |
| 5 | Freigegebener Lauf nur stornierbar, mit Protokoll | `test_zahlung_freigabe.py::test_freigegebener_lauf_nur_stornierbar_mit_protokoll`, `::test_uebergaenge_in_falscher_reihenfolge_werden_abgelehnt`, `test_zahlung_datei.py::test_aenderung_nach_der_freigabe_wird_erkannt` |
| 6 | Stufen mit korrekten Verzugszinsen und Gebühren | `test_mahnwesen_lauf.py::test_b2b_posten_durchlaeuft_die_stufen_mit_zinsen_pauschale_und_gebuehren`, `::test_b2c_ohne_pauschale_mit_gebuehren`, `::test_verzug_beginnt_mit_dem_zugang_der_erinnerung`, `::test_vereinbartes_zahlungsziel_verzug_ab_faelligkeit`, `::test_ohne_mahnung_und_ohne_vereinbarung_kein_verzug`, `::test_gebuehren_nur_fuer_mahnungen_im_verzug`, `::test_gebuehr_einer_stufe_ohne_zinsen_nur_im_verzug`, `test_mahnwesen_zinsen.py::test_ueber_den_wechsel_des_basiszinssatzes_am_1_juli_2026` — „korrekt“ unter den Annahmen zum Verzugsbeginn (Entscheidungen, Grenzen) |
| 7 | Ohne Live-Bankanbindung bis zur Datei | `test_cli_zahlung.py::test_von_vorschlag_bis_zur_sepa_datei`, `test_cli_mahnwesen.py::test_mahnstufen_bis_zum_versendeten_schreiben` |

## Bankprobe — vom Nutzer durchzuführen (Akzeptanzkriterium 2b)

accounti darf keine Bank mit echten Daten ansprechen; ob die Hausbank die Datei annimmt, kann
nur der Nutzer prüfen, sinnvollerweise vor dem ersten echten Zahlungslauf:

1. Mit echten Stammdaten einen kleinen Lauf anlegen, freigeben und die Datei erzeugen
   (`accounti zahlung sepa <Lauf> --datei ueberweisung.xml`).
2. Die Datei im Onlinebanking bzw. EBICS-Client der Hausbank als SEPA-Sammelüberweisung
   hochladen, Vorprüfung und Auftragsvorschau abwarten (Empfänger, Beträge, Summe,
   Ausführungstag, Einzel-/Sammelbuchung, Empfängerüberprüfung).
3. **Den Auftrag nicht unterschreiben/freigeben**, sondern verwerfen; den Lauf in accounti
   stornieren (`accounti zahlung stornieren <Lauf> --grund "Probe Bankannahme"`).
4. Ergebnis hier festhalten: Bank, Zugang (Onlinebanking/EBICS, Auftragsart), Datum, angenommen
   ja/nein, Meldungen der Vorprüfung.

Stand beim Zusammenführen (20.10.2026): Die Bankprobe steht aus. Akzeptanzkriterium 2 ist
damit nur für den schemakonformen Teil (2a) durch Tests belegt; 2b bleibt eine Grenze, bis das
Ergebnis der Probe hier eingetragen ist. Der Code ist vollständig — es fehlt nur die Bestätigung
durch eine echte Bank.

## Grenzen

- **Annahme durch eine Bank nicht geprüft** (Akzeptanzkriterium 2b offen, siehe oben). Die Datei
  besteht das offizielle DK-Schema (GBIC_5) und folgt den Belegungsregeln der Anlage 3 für
  Empfänger im EWR, wurde aber bei keiner Bank eingereicht. Bankseitige Prüfungen kann accounti
  nicht vorwegnehmen: Ausführungstermin nur an TARGET2-Geschäftstagen, Limits je Auftrag oder
  Tag, `BtchBookg=false` ohne Vereinbarung, Ergebnis der Empfängerüberprüfung (VOP).
- **Nur Empfänger im EWR.** Kontakte haben kein BIC-Feld; Zahlungen in die Nicht-EWR-Länder
  des SEPA-Raums (Schweiz, Vereinigtes Königreich samt Kanalinseln und Isle of Man, Gibraltar,
  Monaco, San Marino, Andorra, Vatikan, Albanien, Moldau, Montenegro, Nordmazedonien, Serbien)
  blockiert die Prüfung — sie gehen einzeln über das Onlinebanking. Für sie bräuchte es BIC
  (`CdtrAgt`) und Auftraggeberanschrift.
- **Namen ohne lateinische Schrift** (Kyrillisch, Griechisch …) werden nicht transliteriert,
  sondern blockiert; der Name muss im Stammsatz in lateinischer Schrift stehen. Gemischte Namen
  verlieren die fremden Zeichen (Bereinigung), was die Empfängerüberprüfung der Bank bemängeln
  kann.
- **Vier-Augen nur so stark wie die Anmeldung am Rechner:** Die freigebende Person ist der
  Anmeldename des Betriebssystems, nicht authentisiert gegenüber accounti. Wer zwei Konten hat,
  per `sudo`/`su` wechselt oder die Datenbank direkt ändert, umgeht es — es ist ein
  organisatorisches Prinzip, bis Baustein 10 echte Benutzer bringt. Ohne `vier_augen` bleibt
  die Person Freitext (`--von`, `ACCOUNTI_BENUTZER`).
- **Savepoints unter SQLite:** Der pysqlite-Treiber eröffnet keine Transaktion vor einem
  Savepoint; dessen RELEASE schreibt dann alles fest. `speichere_lauf` verzichtet deshalb auf
  den Savepoint (bei Konflikt Rollback der ganzen Transaktion). Dasselbe Muster steht schon in
  `db/repository.py` (Z. 661, 1141), `opos/verbuchung.py` (Z. 379) und `bank/lauf.py` (Z. 90) —
  außerhalb dieses Bausteins;
  **eigenes Ticket**: projektweit den von SQLAlchemy dokumentierten pysqlite-Workaround setzen
  (BEGIN selbst senden).
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
- **Unveränderbarkeit:** ORM-Sperren (Zahlungen und Kopfsatz) und (unter SQLite) Trigger
  schützen vor Änderungen über accounti; wer die Datenbank direkt mit SQL ändert, wird vom
  Freigabe-Hash beim Erzeugen der Datei bzw. vom Datei-Hash bei der erneuten Ausgabe
  aufgehalten, nicht vorher.
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
- **Verzugsbeginn mit Annahmen:** Den Zugang einer Mahnung kennt accounti nicht, es nimmt
  Versand + `zugang_tage` (Standard 3) an — auch bei E-Mail. Setzt die Mahnung eine Frist,
  rechnet accounti Verzug erst nach deren Ablauf (konservativ; ob die Frist den Verzug
  hinausschiebt, ist nicht eindeutig geklärt). `zahlungsziel_vereinbart` und `hinweis_30_tage`
  gelten für alle Kunden gleich; ob das Zahlungsziel im Einzelfall vertraglich vereinbart ist
  oder die Rechnung an einen Verbraucher den Hinweis nach § 286 Abs. 3 trug, prüft accounti
  nicht. Bei der 30-Tage-Regel gilt die Rechnung als Belegdatum + `zugang_tage` zugegangen.
- **Versandtag:** Ein Mahnentwurf geht nur bis `entwurf_gueltig_tage` nach dem Mahndatum
  hinaus; der Brief trägt das Mahndatum, nicht den Versandtag. `--am` nimmt die Angabe des
  Nutzers ungeprüft (nur nicht in der Zukunft).
- **Zinsmethode:** act/365 auch im Schaltjahr; act/act ergäbe 2024/2028 minimal weniger.
- **Basiszinssatz ab 01.01.2027 fehlt** zwangsläufig; er muss nach der Bekanntgabe Ende Dezember
  in `mahnwesen.basiszinssaetze` nachgetragen werden (oder per Code-Update), sonst bricht die
  Zinsberechnung für Zeiten ab 2027 mit klarer Meldung ab.
- **B2B/B2C** ist eine Heuristik, solange der Kontakt nicht ausdrücklich eingestuft ist; ohne
  Hinweis (USt-IdNr., Leitweg-ID, `privat` auf der Rechnung) gilt „Verbraucher“ (niedrigerer
  Zins, keine Pauschale). Unternehmer ohne USt-IdNr. müssen mit `mahnwesen kunde --unternehmer`
  eingestuft werden.
- **Mahnkosten sind Konfiguration, keine Rechtsberatung** — z.B. sind die Kosten der
  verzugsbegründenden Erstmahnung nach Rechtsprechung nicht ersatzfähig; die Standardwerte (0 / 5 /
  10 €) folgen dem Beispiel der Spec.
- **Teilzahlungen** fließen nur über Zahlungszuordnungen in die Zinsberechnung ein; ein von Hand
  verringerter Restbetrag gilt rückwirkend (zu niedrige Zinsen, nie zu hohe).
- **Je Posten eine Mahnung**, keine Sammelmahnung je Kunde; keine Mahnsperre je einzelnem Posten
  (nur je Kontakt). Die Pauschale gilt je Forderung (Posten) und steht in jeder Mahnung mit Verzug
  erneut als dieselbe Forderung, nicht zusätzlich.
- **E-Mail-Versand** ist nur gegen einen Test-Versandweg geprüft, nicht gegen einen echten
  SMTP-Server (Auftrag); er nutzt den bereits erprobten SMTP-Weg der E-Rechnung. Scheitert nach
  einer erfolgreichen E-Mail noch der Commit der Datenbank, bleibt die Mahnung ein Entwurf
  (sehr kleines Fenster, da vorher alles geprüft und geschrieben ist).
- **Gebühren kumuliert, nur im Verzug:** Eine Mahnung verlangt ihre eigene Gebühr und die der
  früheren Mahnungen, die im Verzug versendet wurden (Annahme: diese bleiben geschuldet). Der
  Verzugsbeginn ist dabei der heute ermittelte (Annahmen siehe „Verzugsbeginn“); frühere
  Gebühren zählen mit dem **heute konfigurierten** Betrag ihrer Stufe, nicht mit dem damals
  verlangten. Ob die Gebühr der Höhe nach als Schaden durchsetzbar ist (tatsächliche Kosten),
  prüft accounti nicht — Gebühren sind Konfiguration.
- **Postgres:** Eindeutiger Index und ORM-Sperren gelten; die Trigger für das Protokoll gibt es wie
  beim USt-IdNr.-Protokoll nur unter SQLite.
- **Keine Alembic-Migration** (entsteht beim Zusammenführen); neue Tabellen: `zahlungslaeufe`,
  `zahlungen`, `zahlungslauf_protokoll`, `zahlungssperren`, `zahlung_iban_klaerungen`,
  `mahnungen`, `mahn_kontakte`.

## Doku-Bausteine

In README, CHANGELOG, Bauplan und Architektur eingearbeitet.
