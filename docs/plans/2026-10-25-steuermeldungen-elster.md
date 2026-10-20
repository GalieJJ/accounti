# Steuermeldungen & elektronische Übermittlung (Baustein 9) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Die Umsatzsteuer-Voranmeldung entsteht aus den gebuchten Daten mit den Kennziffern des
amtlichen Vordrucks 2026, wird plausibilisiert, von einem Menschen freigegeben und als
ELSTER-Datensatz übermittelt — im Testmodus nur erzeugt und geprüft. Datensatz, Ticket, Zeitpunkt
und Prüfbericht liegen danach unveränderbar im Protokoll; die Zahllast steht als offener Posten
gegenüber dem Finanzamt in der OPOS-Liste. Fristen sind berechnet (inkl. § 108 Abs. 3 AO), die
Zusammenfassende Meldung ist aus den Buchungen ableitbar und als Portaldatei exportierbar.

**Spec:** [`docs/specs/2026-08-10-steuermeldungen-elster.md`](../specs/2026-08-10-steuermeldungen-elster.md)
· Akzeptanzkriterien 1–7 · **Baut auf:** Baustein 4 (Kontakte, offene Posten, USt-IdNr.-Protokoll),
Baustein 5 Paket 2 (Tresor), Baustein 2 (Belegarchiv)

```
Buchungssätze (endgültig: auto · geprüft · korrigiert · exportiert)
   │  steuer/kennziffern.py: Steuerschlüssel (DATEV 2/3/8/9/18/19/91/94) + Kennzifferkonten
   ▼
UStVoranmeldung 2026 (steuer/voranmeldung.py) ── BMG volle Euro, Steuer wie ELSTER, Kz 83
   │  steuer/plausibilitaet.py: offene Buchungen · ohne Steuerschlüssel · USt-IdNr. · Verprobung
   │                            · Vormonat/Vorjahresmonat · EU-Privatkunden mit dt. USt (OSS)
   ▼
accounti ustva freigeben --von NAME   ── Mensch, gebunden an den Hash der Formularwerte
   ▼
elster/datensatz.py: ELSTER-XML (TransferHeader v11, Nutzdaten ustva/v2026, Kz09)
   │  interne Datensatzprüfung  ─┐
   ▼                             │
Übermittler ── Attrappe (Tests) · ERiC über ctypes (nur mit Bibliothek, Zertifikat, PIN-Datei)
   │  Testmodus: Testmerker 700000004, prüfen ohne Versand
   ▼
elster/protokoll.py: steuermeldung_protokolle (nur anfügen, Hash-Kette, Trigger) + Belegarchiv
   ▼
elster/zahllast.py: Eigenbeleg → 1780 an Kreditor „Finanzamt“ → offener Posten, fällig zur Frist
```

## Schnitt in Pakete

| Paket | Inhalt | Akzeptanz |
|-------|--------|-----------|
| **1** Kennziffern & Plausibilisierung | Vordruck 2026 in `steuer/voranmeldung.py`, Ermittlung aus Buchungen, Plausibilisierung, `accounti ustva --period`, `ustva pruefen` | 1, 2, 7 |
| **2** Fristen | Feiertage (Bund, optional Land), § 108 Abs. 3 AO, UStVA/DFV/SVZ/ZM/OSS-Fristen, `accounti fristen --jahr` | 6 |
| **3** Datensatz, Übermittlung, Protokoll | ELSTER-XML, Steuernummer im ELSTER-Format, Datensatzprüfung, Freigabe, Übermittler-Schnittstelle (Attrappe, ERiC/ctypes), PIN im Tresor, Protokoll, `ustva freigeben/uebermitteln [--test]`, `elster protokoll/pin` | 3, 4 |
| **4** Zahllast, Dauerfrist, ZM | Zahllast als offener Posten (Kreditor Finanzamt), Berichtigung als Differenz, Sondervorauszahlung/Dauerfristverlängerung, Zusammenfassende Meldung + CSV-Export, `accounti zm` | 5 (und 7 für die ZM) |

## Recherche (Stand 20.10.2026)

| Thema | Ergebnis | Quelle |
|-------|----------|--------|
| Vordruck 2026 | USt 1 A, USt 1 H, USt 1 E, USt 5 E mit BMF-Schreiben vom **29.12.2025**, GZ III C 3 - S 7344/00039/007/036, ab Januar 2026 anzuwenden. Kennziffern: 81, 86, **87 (0 %, § 12 Abs. 3)**, 35/36, 77, 76/80 · 41, 44, 49, 43, 48 · 91, 89, 93, **90**, 95/98, 94/96 · 46/47 (nur § 13b Abs. 1: sonstige Leistung eines EU-Unternehmers), 73/74, 84/85 · 42, 60, 21, 45 · 66, 61, 62, 67, 63, 59, 64 · 65, 69, 39, **83** · 50, 37 (§ 17-Minderungen) · 10, 22, 70, 29, 26, **500** (ersetzt Kz 23). Neu: Zeile 18 (76/80) und SAFE-Umsätze in Kz 43 | [BMF-PDF](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Umsatzsteuer/2025-12-29-vordruckmuster-USt-voranmeldung-2026.pdf?__blob=publicationFile&v=7) |
| Beträge | „Bemessungsgrundlagen … nur Beträge in vollen Euro; bei den Umsatzsteuer- und Vorsteuerbeträgen ist stets auch die Eintragung von Centbeträgen erforderlich“; negative Beträge mit Minus | USt 1 E 2026, S. 1 |
| OSS in der Voranmeldung | Zeile 36 (**Kz 45**) umfasst ausdrücklich „innergemeinschaftliche Fernverkäufe, die ein Unternehmer an Nichtunternehmer … im übrigen Gemeinschaftsgebiet ausführt“ — die Steuer geht ins OSS, der Nettoumsatz in Kz 45. Die bisherige Aussage „OSS nicht Teil der VA“ war falsch | USt 1 E 2026, Zeile 36 |
| Sondervorauszahlung | bis **10. Februar** anzumelden; 1/11 der Summe der Vorauszahlungen des Vorjahres **zuzüglich** der im Vorjahr abgezogenen SVZ (Beispiel: 39.000 € + 5.000 € → 4.000 €, Kz 38); Überschuss → 0 €; Abzug in Kz 39 der letzten Voranmeldung (Dezember) | USt 5 E 2026 |
| Fristen | UStVA bis 10. Tag nach Ablauf des Voranmeldungszeitraums (§ 18 Abs. 1 UStG), Dauerfristverlängerung + 1 Monat (§ 46 UStDV); Monatszahler ab Vorjahressteuer > 9.000 €, Befreiung ≤ 2.000 € (seit 2025) | § 18 UStG, [Lexware](https://www.lexware.de/wissen/unternehmerlexikon/voranmeldezeitraum/) |
| Fristverschiebung | „Fällt das Ende einer Frist auf einen Sonntag, einen gesetzlichen Feiertag oder einen Sonnabend, so endet die Frist mit dem Ablauf des nächstfolgenden Werktags“; maßgeblich ist das Feiertagsrecht am Behördensitz | § 108 Abs. 3 AO; BFH VI R 14/15; [Deubner](https://www.deubner-steuern.de/produkte/taxki/doc/-108-ao-fristen-und-termine-259398) |
| Feiertage | bundeseinheitlich 9 (Neujahr, Karfreitag, Ostermontag, 1. Mai, Himmelfahrt, Pfingstmontag, 3. Oktober, 25./26. Dezember); landesweit zusätzlich: 6.1. BW/BY/ST · 8.3. BE/MV · Fronleichnam BW/BY/HE/NW/RP/SL · 15.8. SL · 20.9. TH · 31.10. BB/HB/HH/MV/NI/SN/ST/SH/TH · 1.11. BW/BY/NW/RP/SL · Buß- und Bettag SN | [Wikipedia](https://de.wikipedia.org/wiki/Gesetzliche_Feiertage_in_Deutschland) |
| OSS-Frist | Ende des Folgemonats nach Quartalsende, **ohne** Verschiebung auf den nächsten Werktag (Sekundärquelle; Regel steht schon in `steuer/oss.py`) | [pandotax](https://pandotax.de/rechtliches/one-stop-shop-mit-anlaufschwierigkeiten-fehler-bei-oss-meldung/) |
| ZM | bis 25. Tag nach Ablauf des Kalendermonats; vierteljährlich, wenn ig. Lieferungen + Dreiecksgeschäfte im laufenden und den vier vorangegangenen Quartalen je ≤ 50.000 €; sonstige Leistungen vierteljährlich; Beträge volle Euro; Arten L, D, S | [BZSt Anleitung ZM 1/2021](https://www.bzst.de/SharedDocs/Downloads/DE/ZM/zm_ausfuellanleitung.pdf?__blob=publicationFile&v=14) |
| ZM-Datei | CSV-Import im ELSTER-Portal: erste Zeile `#v3.0`, UTF-8, Kopfzeile `Umsatzsteuer-Identifikationsnummer (USt-IdNr.),Summe (Euro),Art der Leistung`, höchstens 1500 Zeilen, Betrag ganzzahlig | [ELSTER-Hilfe ZM-Import](https://www.elster.de/eportal/helpGlobal?themaGlobal=zmdo_import_eop) |
| ERiC | C-Bibliothek der Steuerverwaltung, kostenlos; nur nach **Registrierung als Entwickler** (Prüfung durch den IuK-Bereich des **Bayerischen Landesamts für Steuern**, Zugangsdaten „innerhalb weniger Tage“, kein Anspruch auf einen Account), Download im Entwicklerbereich, Hersteller-ID über „Anträge und Formulare“ | [elster.de/Entwickler](https://www.elster.de/elsterweb/infoseite/entwickler) |
| ERiC-API | Linux: `libericapi.so` mit `RTLD_GLOBAL` laden; `EricMtInstanzErzeugen(pluginPfad, logPfad)`, `EricMtGetHandleToCertificate`, `EricMtBearbeiteVorgang(xml, datenartVersion, flags, druckParameter, cryptoParameter, transferHandle, rueckgabe, serverantwort)`, Rückgabepuffer erzeugen/lesen/freigeben, `EricMtCloseHandleToCertificate`, `EricMtInstanzFreigeben`. Flags: VALIDIERE 1<<1, SENDE 1<<2, DRUCKE 1<<5, PRUEFE_HINWEISE 1<<7. Anwendungsfälle: EBV-1 Validiere, EBV-8 Hinweisprüfung + Validiere, EBV-6 send-Auth + PDF. `datenartVersion` = `UStVA_2026` (UStVA AZ 2016–2026 in ERiC 43). Transferticket erzeugt ERiC seit Release 38 selbst. Rückgabecodes: 610001002 Plausibilitätsfehler, 610301202 Test-Hersteller-ID gesperrt | [ERiC 43.3.2.0 Entwicklerhandbuch](https://instantview.org/data/CyberEnterprise/ERiC/ERiC-Entwicklerhandbuch.pdf) Kap. 2.5, 4.2.2, 6.2, 6.5, 10.1; Struct-Felder nach [erica (MIT)](https://github.com/digitalservicebund/erica/blob/main/erica/worker/pyeric/eric.py) |
| Test-Hersteller-ID | 74931 „dient in der Dokumentation nur noch zu Illustrationszwecken“; **seit ERiC 39.4.x gesperrt** für Test- und Echtfälle (ERIC_IO_TESTHERSTELLERID_GESPERRT). Testfälle brauchen die eigene Hersteller-ID | Entwicklerhandbuch 6.5.3, 10.1.1 |
| Testmerker | 700000004: „Testfall, der sofort nach Eingang in dem ELSTER-Annahmeserver gelöscht wird“; bei Echtfällen nicht erlaubt; Teststeuernummern nur Bayern (z. B. 198/113/10010) | Entwicklerhandbuch 6.5.1, 6.5.5 |
| Datensatz UStVA | `<Elster xmlns="http://www.elster.de/elsterxml/schema/v11">`, TransferHeader v11 (Verfahren `ElsterAnmeldung`, DatenArt `UStVA`, Vorgang `send-Auth`, Testmerker, HerstellerID, DatenLieferant, Datei: CMSEncryptedData/GZIP), NutzdatenHeader v11 (Empfänger `id="F"` = Finanzamtsnummer), Nutzdaten `<Anmeldungssteuern xmlns="http://finkonsens.de/elster/elsteranmeldung/ustva/v2026" version="2026">` mit Erstellungsdatum, DatenLieferant (Name 45, Straße 30, PLZ, Ort 30), `Steuerfall/Umsatzsteuervoranmeldung` (Jahr, Zeitraum, Steuernummer 13-stellig, **Kz09 = Hersteller-ID, Pflicht 2026**, Kennzahlen aufsteigend, Steuer mit Punkt). Kein Attribut `art` mehr. Die Schemas selbst gibt es nur im ERiC-Paket (Entwicklerbereich) | Entwicklerhandbuch 8.1, 8.5; ERiC-43-Erfahrung in [haben PR #59](https://github.com/firsttris/haben/pull/59) (nur Fakten übernommen, kein Code — AGPL) |
| Dauerfristverlängerung | gleiche Datenart UStVA; ohne Sondervorauszahlung „ist nur Kz 09 zu füllen“, Berichtigung dann nicht möglich | Entwicklerhandbuch 8.5.1 |
| Steuernummer | ELSTER-Format 13-stellig = Bundesfinanzamtsnummer (4) + 0 + Bezirk/Unterscheidung/Prüfziffer (8); Länderpräfixe BW 28, BY 9, BE 11, BB 3, HB 24, HH 22, HE 26, MV 4, NI 23, NW 5, RP 27, SL 10, SN 3, ST 3, SH 21, TH 4 | [Wikipedia Steuernummer](https://de.wikipedia.org/wiki/Steuernummer) |
| DATEV-Schlüssel | 2/3 USt 7/19 %, 8/9 VSt 7/19 %, 18/19 ig. Erwerb 7/19 %, 91/94 § 13b 7/19 % | [Lexware FAQ](https://www.lexware.de/support/faq/faq-beitrag/000002619-datev-steuerschluessel-hinterlegen/), [DATEV-Community](https://www.datev-community.de/t5/Betriebliches-Rechnungswesen/Steuerschl%C3%BCssel-DATEV-19-oder-94-bei-reverse-charge/td-p/154778) |
| SKR03-Erlöskonten | 8125 ig. Lieferung (Kz 41), 8120 Ausfuhr (Kz 43), 8100 § 4 Nr. 8 ff. (Kz 48), **8336** EU-Leistung Steuerschuld Empfänger (Kz 21), 8337 § 13b-Leistungen (Kz 60), **8338** Drittland nicht steuerbar (Kz 45), 8339 EU nicht steuerbar (Kz 45); SKR04 analog 41xx/43xx | NWB „ABC der Kontierung“ (Sekundärquelle) |

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Vordruck | `steuer/voranmeldung.py` bildet die Kennziffern des Vordrucks 2026 mit Zeile, Bezeichnung und Art ab (Bemessungsgrundlage, Steuer, Merker); Kz 83 = Zeile 37 − Zeilen 38–44 + 65 + 69 − 39 | Akzeptanz 1 gegen den amtlichen Vordruck; alte Klasse kannte 10 von über 40 Kennziffern, Kz 89 nur 19 %, 46 für alle § 13b-Fälle |
| Rundung | Bemessungsgrundlagen auf volle Euro **abgeschnitten**; Steuer zu 81/86/89/93 = BMG × Satz (so rechnet ELSTER, sie wird nicht übertragen); alle übrigen Steuerfelder mit Cent aus der Buchung | Vordruck verlangt volle Euro; Kz 83 muss zu ELSTERs eigener Rechnung passen, sonst Plausibilitätsfehler |
| Ermittlung | Aus endgültigen Buchungssätzen: Steuerschlüssel → Kennziffer (3→81, 2→86, 9/8→66, 19/18→89/93+61, 94/91→46/47+67 bei EU-Kreditor, sonst 84/85+67); ohne Schlüssel über Kennzifferkonten (SKR03/SKR04-Standard, per `elster.kennziffern_konten` ergänzbar). Vorzeichen über die Seite des Sachkontos; Gegenkonten sind Personen-, Geld-, **Geldtransit-, Durchlaufende-Posten- und Privatkonten** (SKR03 1360, 1590, 1800–1899; SKR04 1370, 1460, 2100–2199). Stehen beide Seiten (oder keine) auf Gegenkonten, entscheidet das Erlöskonto: bei USt-Schlüsseln ist es das Sachkonto, bei Vorsteuerschlüsseln die Gegenseite | Buchungssätze tragen BU-Schlüssel wie DATEV; Gutschriften und Skonti mindern automatisch; Stornos über Zwischenkonten erhöhten sonst den Umsatz (Prüfbefund Runde 1) |
| Kennzifferkonten | Jede Seite einer Buchung ohne Schlüssel wird für sich bewertet. Ein Konto mit fester Funktion bucht seinen Zugang auf der Seite seiner Kennziffer (`zugangsseite`): Umsätze (A, B, E), Umsatzsteuerfelder und Kz 37 im Haben, Erwerbe und § 13b-Bezüge (C, D), Vorsteuerfelder und Kz 50 im Soll. `elster.kennziffern_konten` nimmt alle Bemessungsgrundlagen **und Steuerfelder** außer Kz 83/39 (z. B. `1588: 62` Einfuhrumsatzsteuer) | Kz 91/90/95/94/73 und Steuerfelder hatten sonst das falsche Vorzeichen bzw. ließen sich gar nicht zuordnen |
| Erlösschmälerung ohne Schlüssel | folgt der Kennziffer der Rechnungsbuchung desselben Belegs — **nur für echte Minderungen**: Erlöskonto im Soll oder Erlösschmälerungskonto (SKR03 8700–8799, SKR04 4700–4799, auch dessen Storno im Haben), **gegen ein Gegenkonto** (Personen-, Geld-, Transit-, Durchlaufende-Posten- oder Privatkonto). Kandidaten sind die Kennziffern der Funktionskonten **und der Umsatzsteuerschlüssel** (3 → 81, 2 → 86) auf dem Beleg; nur wenn genau eine übrig bleibt und sie über ein Funktionskonto läuft (steuerfrei), gilt die Minderung. Mehrere Kennziffern (Mischrechnung) oder eine steuerpflichtige Rechnung → Fehler. Ein Erlös im Haben ohne Schlüssel ist ein Fehler, auch auf einem Beleg mit ig. Lieferung; ebenso die Gegenseite einer Funktionskonto-Buchung (`8125 an 8400`, `8400 an 8125`) | `opos/ausgleich` bucht Skonto auf 0-%-Rechnungen ohne Schlüssel; die Minderung einer steuerpflichtigen Rechnung ohne Schlüssel berichtigt die Umsatzsteuer nicht (§ 17 UStG); Akzeptanz 2 war sonst umgehbar (Prüfbefunde Runde 1 und 2) |
| OSS | Erlöse auf den OSS-Konten → Kz 45 (netto); `UStBerechner` meldet für EU-B2C-OSS Kz 45 | Anleitung 2026, Zeile 36 |
| AE-Erlöskonto | `opos verbuchen` bucht EU-Leistungen mit Steuerschuld des Empfängers auf **8336** statt 8338 | 8338 ist im SKR03 „Drittland, nicht steuerbar“ (Kz 45); mit 8338 fehlte der Umsatz in Kz 21 und in der ZM |
| DATEV-Schlüssel | `DATEV_BU_SCHLUESSEL` ig. Erwerb 19/18 und § 13b 94 statt 10/11/19 | Konflikt mit DATEV (19 = ig. Erwerb 19 %); bisher von keinem Code benutzt |
| Endgültig | gezählt werden Buchungen mit Status auto, geprüft, korrigiert, exportiert; Buchungen „zur Prüfung“/„Entwurf“ im Zeitraum sind ein Fehler | eine Erklärung über unbestätigte Vorschläge wäre unvollständig |
| Steuerrelevante Konten | Konten, auf denen ein Umsatz gebucht wird: Umsatzerlöse, Erlösschmälerungen, unentgeltliche Wertabgaben und die Erlöskonten unter den sonstigen Erträgen, die der DATEV-Kontenrahmen 2026 als Automatikkonten mit Umsatzsteuer (AM) führt, samt Geschwistern ohne Steuersatz — **SKR03** 2750–2752, 8000–8959; **SKR04** 4000–4799, 4833–4836, 4841–4842, 4844–4845, 4848–4852, 4860–4869, 4940–4949 (Sachbezüge, z. B. 4947 Kfz-Gestellung), 6884–6892 (Anlagenverkäufe bei Buchverlust); `elster.steuerrelevante_konten` ersetzt die Liste. Buchung darauf ohne Steuerschlüssel, ohne Kennzifferkonto und ohne Rechnungsbezug → **Fehler**; als Erlöskonten entscheiden sie auch das Vorzeichen. Bestandsveränderungen, aktivierte Eigenleistungen, Währungsumrechnung, Restbuchwerte, Auflösungen, Zuschreibungen, Versicherungsentschädigungen und erstattete Vorsteuer (SKR03 8960–8999, 2700–2749; SKR04 4800–4832, 4837–4840, 4843, 4846–4847, 4855–4859, 4870–4939, 4950–4999) gehören nicht dazu | Akzeptanz 2; Aufwand ohne Vorsteuer ist oft richtig (Versicherung, Gebühren) und deshalb kein Fehler; nicht steuerbare Erträge sperrten sonst als Fehlalarm (Runde 1); die Begrenzung auf 4000–4799 ließ steuerpflichtige SKR04-Erlöse wie 4845 und 4947 still durch (Runde 2). Quelle: DATEV SKR 03/04 2026, Spalte Programmverbindung (AM) und GuV-Posten |
| Steuerkonten ohne Kennziffer | Buchung ohne Schlüssel auf einem Vorsteuer- oder USt-Konto (SKR03 1570–1588, 1770–1779, 1782–1788; SKR04 1400–1433, 3800–3819, 3832–3837), das keiner Kennziffer zugeordnet ist → **Warnung** mit Hinweis auf `elster.kennziffern_konten`; Vorauszahlungen, SVZ und USt laufendes Jahr/Vorjahr ausgenommen | Einfuhrumsatzsteuer ging sonst ohne Befund verloren |
| Warnungen der Ermittlung | `Ermittlung.warnungen` → Befund `ermittlung` mit Schweregrad **warnung**: § 13b ohne bekannten Leistenden (Kz 84/85 statt 46/47), Steuerkonto ohne Kennziffer, 8338/8339 (SKR04 4338/4339) an EU-Unternehmer mit USt-IdNr. (gehört auf 8336/4336, Kz 21, ZM) | Der Mensch muss es vor der Freigabe gesehen haben |
| Leistender bei § 13b | über Personenkonto, offenen Posten **oder `Beleg.kontakt_id`** des Belegs | Werbe-/SaaS-Rechnungen aus dem EU-Ausland werden oft direkt über die Bank gebucht |
| USt-IdNr. | Kz 41, 42 und 21 brauchen eine aktuelle qualifizierte Bestätigung (`kontakte.ustid.aktuelle_bestaetigung`, Stichtag = Buchungsdatum, `ustid_pruefung.max_alter_tage`); Abnehmer über das Personenkonto oder den offenen Posten des Belegs | Akzeptanz 7; Steuerfreiheit nur mit Nachweis (§ 6a Abs. 4 UStG) |
| Plausibilisierung | Befunde mit Schweregrad `fehler`/`warnung`/`hinweis` (wie Baustein 7 geplant); Fehler sperren die Freigabe. Weitere Regeln: Umsatzsteuer-Verprobung (gebucht ./. Formular > 1 €), Vormonat/Vorjahresmonat (> 50 % und > 1.000 €), EU-Privatkunden mit deutscher USt bei OSS-Registrierung, Kz 83 rechnerisch | Spec 4.1; Schwellen konfigurierbar |
| Baustein 7/8 | Periodenabschluss und offene Prüfbefunde: Schnittstelle `weitere_befunde`, ohne Baustein 7 ein Hinweis; Aufgaben aus Fristen: `faellige_fristen()` liefert sie, eingehängt wird später | Bausteine 7 und 8 entstehen parallel |
| Freigabe | eigener Schritt `ustva freigeben --von NAME`; speichert Name, Zeitpunkt, Formularwerte und deren Hash; echte Übermittlung nur mit passender, noch nicht verbrauchter Freigabe; ändern sich Buchungen, passt der Hash nicht mehr; vor der Abgabe wird erneut plausibilisiert, neue Fehler sperren auch mit gültiger Freigabe | „immer durch den Menschen, nie automatisch“ |
| Datensatz | `elster/datensatz.py` baut ELSTER-XML mit `xml.etree` (Elementreihenfolge laut Recherche); Zeitraum 01–12 bzw. 41–44; Steuernummer ins ELSTER-Format (`elster/steuernummer.py`, 13-stellig auch direkt) | keine neue Abhängigkeit; Schema nicht öffentlich |
| Datensatzprüfung | intern: wohlgeformt, Namensräume, Pflichtfelder, Steuernummer/Finanzamt, Betragsformate, Kz 83 aus den Werten im XML nachgerechnet, Testmerker passend zum Modus; mit ERiC zusätzlich EBV-8 | „prüffähig“ auch ohne ERiC nachweisbar |
| Testmodus | `--test`: Datensatz mit Testmerker 700000004, Prüfung, **kein Versand**, Datei optional (`--ausgabe`), Protokoll mit Modus `pruefung`; `--testfall` sendet mit Testmerker über ERiC (Server löscht ihn). **Default beim ersten Lauf:** Ohne erfolgreichen Prüf- oder Testfall-Lauf über denselben Weg (je Meldeart) leitet `ustva uebermitteln` bzw. `ustva dauerfrist --uebermitteln` in den Testmodus um und sagt es; `uebermittle()` selbst verweigert die echte Abgabe dann | Spec 5 „Testmodus — Default beim ersten Lauf“; Testfall prüft Zertifikat und Leitung |
| Übermittler | Protokoll `Uebermittler` (`pruefe`, `sende`); `EricUebermittler` (ctypes, Mt-API) nur, wenn `elster.eric.bibliothek`, `zertifikat` und `pin_datei` gesetzt sind und existieren; `AttrappenUebermittler` für Tests und Probeläufe (`elster.uebermittler: attrappe`, im Protokoll als Weg „attrappe“) — **nur in den Modi `pruefung` und `testfall`**, nie „echt“. Tests des Abgabewegs nutzen ein Doppel, das sich als ERiC meldet (`tests/elster_hilfe.py`). Unerwartete Ausnahmen des Übermittlers werden ein gescheiterter Protokolleintrag („Abgabe ungewiss — in Mein ELSTER prüfen“) | Spec 4.2: schmale Schicht; CI gibt nie ab; ein Attrappen-„Echtlauf“ im unveränderbaren Protokoll machte die erste wirkliche Abgabe zur Berichtigung und die Zahllast zur Differenz |
| ctypes-Test | eine kleine C-Attrappe von `libericapi` wird im Test mit `cc` gebaut (übersprungen ohne Compiler) | der Adapter wird so echt über ctypes geprüft, ohne ELSTER |
| ERiC-Rückgabe | Prüfen ohne Versand gilt nur bei `ERIC_OK` oder `ERIC_GLOBAL_HINWEISE` (610001003) als Erfolg; Plugin-Verzeichnis ohne Konfiguration `<lib>/plugins2` | Codes und Pfad wie in erica (`eric_errors.py`, `eric.py`) |
| PIN | AES-GCM über `bank.tresor`, Schlüssel aus `ACCOUNTI_SCHLUESSEL`, Bezug `elster-pin`, Datei `elster.eric.pin_datei` (0600) außerhalb der DB; `accounti elster pin` fragt verdeckt | Spec 5: verschlüsselt außerhalb der Datenbank |
| Protokoll | Tabelle `steuermeldung_protokolle`: laufende Nummer, Zeitpunkt, Art, Zeitraum, Modus, Weg, berichtigt, Freigabe, Datensatz (XML) und dessen Hash, Ticket, Ergebnis, Prüfbericht, Serverantwort, Hash des ERiC-PDF, Zahllast, `aufbewahren_bis`, Vorgänger-Hash, Hash. Nur anfügen (ORM-Sperre, SQLite-Trigger), Hash-Kette wie `ustid_pruefungen`; Datensatz und PDF zusätzlich im Belegarchiv; jeder Lauf wird protokolliert, auch Fehlschläge; `elster protokoll` prüft Kette, Lücken und Archivdateien | Akzeptanz 4; korrigierte Anmeldung (Kz 10) tritt daneben |
| Eigene Transaktion | Protokolleintrag wird sofort festgeschrieben, Zahllast-Buchung danach | Nachweis darf nicht mit einem späteren Fehler verschwinden |
| Zahllast | Eigenbeleg (Belegart sonstiges, Datei = übermittelter Datensatz) → Buchung 1780 an Kreditor (SKR04 3820) → offener Posten, fällig zur Abgabefrist; **Erstattung als Forderung mit positivem Betrag** (Kreditor an 1780; der Ausgleich bucht auf das Kreditorenkonto, `opos/ausgleich` nimmt das einzige Personenkonto des Kontakts); Berichtigung bucht nur die Differenz zur letzten Anmeldung und **verrechnet sie zuerst mit dem offenen Posten des Zeitraums** (Minderung kürzt die offene Zahllast, Erhöhung die offene Erstattung), nur der Rest wird ein neuer Posten; Sondervorauszahlung 1781 (SKR04 3830). Scheitert die Buchung nach dem festgeschriebenen Protokoll, meldet die CLI das und `accounti elster zahllast` holt sie nach | Akzeptanz 5, Spec 4.6: Lastschrift und Erstattung gleichen den Posten über den Kontoumsatz aus (getestet über `zuordne_zahlungen`) |
| Finanzamt | Kreditor über `kontakte.dienst.kontakt_fuer` (Name `elster.finanzamt.name`, Standard „Finanzamt <Nr>“, IBAN optional) | ein Kontakt für alle Steuerposten |
| Fristen | `steuer/fristen.py`: UStVA 10. Folgemonat/-quartal, mit DFV + 1 Monat; SVZ 10.2.; DFV-Antrag Quartalszahler 10.4.; ZM 25. nach Ablauf; OSS Monatsletzter (unverschoben). § 108 Abs. 3 AO mit Feiertagen des Bundeslands (`elster.bundesland`, ohne: bundeseinheitlich), ZM mit NW (BZSt Bonn) | Akzeptanz 6 |
| ZM | `steuer/zusammenfassende_meldung.py`: L/D/S je USt-IdNr. aus Kz-41/42/21-Buchungen, volle Euro; Export CSV mit `#v3.0` und `#ve3.2.1` wie im Beispiel der ELSTER-Hilfe; Fehler bei fehlender Bestätigung; keine Direktübermittlung | ZMDO-Schema nur im Entwicklerbereich; Portal-Import ist dokumentiert |
| Dauerfrist | `ustva dauerfrist --jahr J` meldet DFV und SVZ an (1/11 aus dem Protokoll des Vorjahres oder `--summe-vorjahr`), gleicher Weg wie die UStVA (Freigabe, Protokoll, Posten); die Freigabe enthält das Berichtigt-Kennzeichen (Kz 10). **Eine Quelle je Jahr** (`festgesetzte_svz`): `elster.sondervorauszahlung: {Jahr: Betrag}` für genau dieses Jahr, sonst die zuletzt abgegebene Anmeldung im Protokoll — für Kz 39 im Dezember und für die SVZ des Vorjahres in der Berechnung; weicht die Konfiguration von der angemeldeten SVZ ab, eine Warnung. Ein Wert ohne Jahr wird abgelehnt | Spec 4.2; ein jahresloser Wert galt sonst in jedem Folgejahr (Prüfbefund Runde 1) |
| Konfiguration | Abschnitt `elster` mit Lader `accounti.elster.konfiguration.lade_elster`, alles optional | Muster `lade_buchhaltung` |
| CLI | Module `befehle/ustva.py`, `zm.py`, `fristen.py`, `elster.py` | Erweiterungspunkt „Neuen Baustein anschließen“; `cli.py` bleibt unverändert |

## Aufgaben

### Paket 1 — Kennziffern & Plausibilisierung

- [x] **Zeitraum** (`steuer/zeitraum.py`): `2026-08`, `2026-Q3`, `2026`; von/bis, ELSTER-Code 01–12/41–44, Vorperioden (`tests/test_steuer_zeitraum.py`).
- [x] **Vordruck 2026** (`steuer/voranmeldung.py`): Kennziffern mit Zeile/Art, BMG volle Euro, Steuer 81/86/89/93 berechnet, Kz 83, Zusammenfassung; `UStBerechner` OSS → Kz 45, DATEV-Schlüssel korrigiert (`tests/test_steuer_voranmeldung.py`).
- [x] **Ermittlung aus Buchungen** (`steuer/kennziffern.py`): Schlüssel, Kennzifferkonten, Vorzeichen, Gutschrift, Skonto, Erlösschmälerung über den Beleg, offene/unbekannte Buchungen als Befund (`tests/test_steuer_kennziffern.py`).
- [x] **AE-Erlöskonto 8336** in `opos/verbuchung.py` (`tests/test_opos_verbuchung.py`).
- [x] **Plausibilisierung** (`steuer/plausibilitaet.py`): je Regel ein auslösendes und ein nicht auslösendes Fixture (`tests/test_steuer_plausibilitaet.py`).
- [x] **CLI** `accounti ustva --period`, `ustva pruefen` — Akzeptanz 1 (handgerechnete Sollrechnung), 2 und 7 (`tests/test_cli_ustva.py`).

### Paket 2 — Fristen

- [x] **Feiertage** (`steuer/feiertage.py`): bundeseinheitlich, je Land, Ostersonntag selbst berechnet (Meeus/Jones/Butcher; `dateutil` hat keine Typstubs) (`tests/test_steuer_fristen.py`).
- [x] **Fristen** (`steuer/fristen.py`): § 108 Abs. 3 AO, UStVA/DFV/SVZ/ZM/OSS, Kalender eines Jahres, fällige Fristen ab Stichtag; Akzeptanz 6 (10. auf Samstag/Sonntag, Feiertag, Kette Karfreitag–Ostermontag, Sonderfall 10. Februar).
- [x] **CLI** `accounti fristen --jahr` (`tests/test_cli_fristen.py`).

### Paket 3 — Datensatz, Übermittlung, Protokoll

- [x] **Konfiguration** (`elster/konfiguration.py`): Abschnitt `elster` mit Standards (`tests/test_elster_konfiguration.py`).
- [x] **Steuernummer** (`elster/steuernummer.py`): 16 Länder, 13-stellig direkt, Fehler (`tests/test_elster_steuernummer.py`).
- [x] **Datensatz** (`elster/datensatz.py`): UStVA-XML, Testmerker, Prüfung, Kz 83 nachgerechnet (`tests/test_elster_datensatz.py`).
- [x] **Modelle, Tabellen, Repository** (`models/elster.py`, `db/tabellen_elster.py`, `db/repo_elster.py`).
- [x] **Protokoll** (`elster/protokoll.py`): Hash-Kette, Änderung/Löschung scheitern (ORM, Trigger), Manipulation, Lücke, Archivdatei verändert (`tests/test_elster_protokoll.py`).
- [x] **Übermittler** (`elster/uebermittlung.py`): Schnittstelle, Attrappe, Auswahl (`tests/test_elster_uebermittlung.py`).
- [x] **PIN** (`elster/pin.py`): Tresor, Datei 0600, falscher Schlüssel (`tests/test_elster_pin.py`).
- [x] **ERiC-Adapter** (`elster/eric.py`): ctypes gegen eine im Test gebaute C-Attrappe (`tests/test_elster_eric.py`).
- [x] **Freigabe und Ablauf** (`elster/freigabe.py`, `elster/ustva.py`): Freigabe nur ohne Fehler, Hash-Bindung, verbraucht; Akzeptanz 3 und 4.
- [x] **CLI** `ustva freigeben`, `ustva uebermitteln [--test|--testfall] [--ausgabe]`, `elster protokoll`, `elster pin` (`tests/test_cli_ustva.py`, `tests/test_cli_elster.py`).

### Paket 4 — Zahllast, Dauerfrist, ZM

- [x] **Zahllast** (`elster/zahllast.py`): Kreditor Finanzamt, Eigenbeleg, Buchung, Posten zur Frist, Erstattung, Berichtigung als Differenz; Akzeptanz 5 (`tests/test_elster_zahllast.py`).
- [x] **Dauerfrist/Sondervorauszahlung**: Berechnung, Datensatz, `ustva dauerfrist`, Kz 39 im Dezember (`tests/test_elster_dauerfrist.py`).
- [x] **Zusammenfassende Meldung** (`steuer/zusammenfassende_meldung.py`): L/D/S je USt-IdNr., Minderungen, Bestätigung, CSV `#v3.0`; `accounti zm` (`tests/test_steuer_zm.py`, `tests/test_cli_zm.py`).
- [x] **Abgabesperre nach der Freigabe**: Vor der echten Abgabe wird erneut plausibilisiert; ein Fehler, der erst nach der Freigabe entsteht, ohne die Werte zu ändern (Buchung ohne Steuerschlüssel, abgelaufene USt-IdNr.-Bestätigung), sperrt die Abgabe (`test_neuer_fehler_nach_der_freigabe_sperrt_die_abgabe`).
- [x] **Abschluss**: `pytest`, `ruff` (ohne Cache), `ruff format --check`, `mypy` grün; Checkboxen, Doku-Bausteine; CLI-Probelauf unter `/tmp` mit Attrappe.

### Runde 1 — Prüfbefunde (20.10.2026)

- [x] **Akzeptanz 2 nicht mehr umgehbar**: Belegregel nur für echte Minderungen (Erlöskonto im Soll, Erlösschmälerungskonto); Erlös im Haben ohne Schlüssel und Gegenseite einer Funktionskonto-Buchung sind Fehler; Funktionskonten auf beiden Seiten zählen beide (`tests/test_steuer_kennziffern.py`).
- [x] **Vorzeichen**: Geldtransit, durchlaufende Posten, Privat als Gegenkonten; sonst entscheidet das Erlöskonto; Kennzifferkonten mit Zugangsseite je Kennziffer; Steuerfelder in `kennziffern_konten` (`tests/test_steuer_kennziffern.py`, `tests/test_elster_konfiguration.py`).
- [x] **Steuerrelevante Bereiche** auf Umsatzerlöse begrenzt; je Kontenrahmen ein nicht auslösendes Fixture.
- [x] **Warnungen der Ermittlung**: § 13b ohne Leistenden, Steuerkonto ohne Kennziffer, 8338/8339 an EU-Unternehmer; Leistender auch über `Beleg.kontakt_id` (`tests/test_steuer_plausibilitaet.py`, `tests/test_elster_ustva.py`).
- [x] **Sondervorauszahlung je Jahr**, eine Quelle für Kz 39 und Berechnung; DFV-Freigabe mit Kz 10 (`tests/test_elster_dauerfrist.py`).
- [x] **Attrappe nie „echt“, Testmodus beim ersten Lauf**, unerwartete Übermittler-Fehler als „Abgabe ungewiss“ protokolliert (`tests/test_elster_ustva.py`, `tests/test_cli_ustva.py`).
- [x] **Zahllast**: Erstattung als Forderung, Berichtigung verrechnet, Ausgleich per Kontoumsatz getestet, `elster zahllast` holt fehlende Buchungen nach (`tests/test_elster_zahllast.py`, `tests/test_cli_ustva.py`).
- [x] **Kleinigkeiten**: Jahr als Zeitraum mit klarer Meldung, `elster protokoll` mit Kz 38 für die DFV, ERiC nur `ERIC_GLOBAL_HINWEISE` als Erfolg, Plugin-Verzeichnis `plugins2`, ZM-CSV mit `#ve3.2.1`.

### Runde 2 — Prüfbefunde (20.10.2026)

- [x] **SKR04: steuerpflichtige Erlöse oberhalb 4799**: Automatikkonten mit USt unter den sonstigen Erträgen (4833–4836, 4841–4842, 4844–4845, 4848–4852, 4860–4869, 4940–4949, 6884–6892) und SKR03 2750–2752 sind steuerrelevant; 4845/4947 ohne Schlüssel sperren, Storno über 3790 ergibt Kz 81 = 0; nicht steuerbare 48xx/49xx bleiben ohne Befund (`tests/test_steuer_kennziffern.py`).
- [x] **Belegregel**: Minderung nur gegen ein Gegenkonto (`8400 an 8125`, `8730 an 2700` sperren); Umsatzsteuerschlüssel des Belegs zählen als Kandidaten, Mischrechnung (41 + 81) und steuerpflichtige Rechnung ohne Schlüssel sperren (`tests/test_steuer_kennziffern.py`).

## Grenzen

- **Keine echte Übermittlung erprobt.** Es gibt keine Entwicklerregistrierung, keine Hersteller-ID, kein Zertifikat und keinen ERiC-Download für dieses Projekt. Der ctypes-Adapter folgt dem Entwicklerhandbuch 43.3.2.0 und der Struct-Belegung aus erica; geprüft ist er nur gegen eine selbstgebaute C-Attrappe. Die Struct-Versionen (`druck_parameter_version`, `verschluesselungs_parameter_version`) sind konfigurierbar, weil `eric_types.h` nicht öffentlich ist — vor dem ersten Echtlauf gegen den Header des geladenen ERiC prüfen. Ohne eigene Hersteller-ID lehnt ERiC seit 39.4 auch Testfälle ab.
- **Datensatz nicht gegen das amtliche Schema validiert.** Die XSD für UStVA 2026 und Dauerfristverlängerung liegen nur im Entwicklerbereich. Aufbau und Reihenfolge stammen aus dem Entwicklerhandbuch und einer mit ERiC 43.4.6 geprüften Fremdimplementierung (nur für die UStVA); die Elementnamen der **Dauerfristverlängerung** (`Dauerfristverlaengerung`, Kz 38) sind nicht belegt. Mit ERiC wird jeder Datensatz vor dem Versand von ERiC validiert, ohne ERiC nur intern.
- **Rundung** der Bemessungsgrundlagen (abschneiden, auch bei negativen Beträgen gegen null) und der ZM-Beträge ist nicht amtlich belegt, nur „volle Euro“.
- **Kennziffern, die accounti nicht von selbst aus Buchungen ableitet:** 87, 35/36, 77, 76/80, 44, 49, 91, 90, 95/98, 94/96, 73/74, 60 (nur über Konto 8337), 62 (Einfuhrumsatzsteuer), 63, 59, 64, 65, 69, 50, 37. Sie lassen sich über `elster.kennziffern_konten` auf Konten legen — Bemessungsgrundlagen und Steuerfelder, Vorzeichen über die Zugangsseite der Kennziffer; bei Paaren (z. B. 73/74) braucht jedes Feld sein eigenes Konto. Die Merker 10, 22, 70, 29, 26, 500 und die berechneten Kz 83/39 gehen nicht über Konten. Besondere Schlüssel (z. B. 16 %/5 %, EUSt als Schlüssel) erzeugen einen Fehler-Befund statt einer Kennziffer.
- **Steuerkonten-Warnung:** Die Bereiche der Vorsteuer- und USt-Konten (SKR03 1570–1588, 1770–1779, 1782–1788; SKR04 1400–1433, 3800–3819, 3832–3837) stammen aus Sekundärquellen und sind nicht abschließend; Steuerkonten außerhalb fallen nicht auf. Die Warnung kommt nur bei Buchungen ohne Steuerschlüssel.
- **Vorzeichen ohne Gegen- und ohne Erlöskonto:** Bucht ein Steuerschlüssel zwischen zwei Konten, die weder Gegen- noch Erlöskonten sind (z. B. USt-Schlüssel auf 2700 „sonstige Erträge“ gegen ein Verrechnungskonto), gilt die Normalseite des Schlüssels — ein Storno in diese Richtung erhöht dann den Umsatz. Die Verprobung rechnet mit derselben Seite und schlägt nicht an.
- **§ 13b:** Vorsteuer aus § 13b wird voll abziehbar angenommen (Kz 67 = Kz 47/85). 46/47 vs. 84/85 entscheidet das Land des Kreditors (EU ≠ DE → 46/47) — eine Werklieferung eines EU-Unternehmers landet damit fälschlich in 46/47.
- **OSS-Konten SKR04** sind im Code nicht definiert (wie bisher nur SKR03 8320–8327); das Bestimmungsland kennt eine Buchung nur über das Konto. Die OSS-Regel der Plausibilisierung erkennt EU-Privatkunden nur über Personenkonto und Kontakt.
- **Steuerrelevant** sind standardmäßig die Erlöskonten nach dem DATEV-Kontenrahmen 2026 (Entscheidung oben). Die Liste ist gegen das Kontenverzeichnis SKR 03/04 2026 abgeglichen, nicht gegen ältere Jahrgänge oder Branchenkontenrahmen; eigene Erlöskonten außerhalb der Bereiche fallen ohne Schlüssel nicht auf. Sammelkonten der sonstigen Erträge, auf denen Umsatzsteuer möglich, aber nicht automatisch ist (SKR03 2700–2749, SKR04 4830, 4832, 4839), sind nicht steuerrelevant — ein steuerpflichtiger Ertrag dort ohne Schlüssel fällt nicht auf. Fehlende Vorsteuerschlüssel auf Aufwandskonten fallen nicht auf; ebenso wenig erhaltene, versteuerte Anzahlungen (SKR03 1711–1718, SKR04 3260–3272) und Forderungsverluste mit USt (SKR03 2401–2408, 2431–2436; SKR04 6281–6286, 6931–6938) ohne Schlüssel — Anzahlungen fehlen dann in Kz 81, Forderungsverluste mindern die Umsatzsteuer nicht. Umgekehrt sperren die Konten „ohne USt“ bzw. steuerfrei innerhalb der Bereiche (Wertabgaben SKR03 89xx, SKR04 46xx; Sachbezüge 8614/4949; Finanzanlagen 8838/4851; sonstige Erträge 8603–8607 und Zinsen 8650/8660 im SKR03) ohne Schlüssel die Freigabe — ausnehmen über `elster.steuerrelevante_konten`.
- **Skonto auf Mischrechnungen:** Hat eine Rechnung einen steuerfreien Teil über ein Kennzifferkonto (z. B. 8125) und einen steuerpflichtigen Teil mit Schlüssel, bucht `opos/ausgleich` das Skonto des 0-%-Anteils ohne Schlüssel auf das 0-%-Skontokonto. Die Ermittlung kann es keiner Kennziffer sicher zuordnen und sperrt die Freigabe („Rechnung mit mehreren Kennziffern“). Abhilfe: das Skonto auf ein Konto mit fester Kennziffer umbuchen (z. B. 8743 „Skonti ig. Lieferungen“ über `elster.kennziffern_konten: {"8743": 41}`).
- **Kontenplan `config/skr03.yaml`** nennt 8100 als Ausfuhr und Schlüssel 10/11/40 — nicht angepasst (Konfiguration eines anderen Bausteins); maßgeblich sind die Tabellen in `steuer/kennziffern.py`.
- **Baustein 7/8 fehlen:** „Periode abgeschlossen?“ und „offene Prüfbefunde“ werden nicht geprüft (Hinweis-Befund, Schnittstelle vorhanden); Fristen werden nicht zu Aufgaben, `faellige_fristen()` liefert sie nur.
- **Feiertage:** nur landesweite; Fronleichnam in Teilen von SN/TH, Mariä Himmelfahrt in Teilen BY, Augsburger Friedensfest und einmalige Feiertage (8.5.2025 BE) fehlen. Maßgeblich ist das Land des Finanzamts — accounti nimmt `elster.bundesland`.
- **ZM:** keine Direktübermittlung (ZMDO), nur Portaldatei; Dreiecksgeschäfte nur über Konto 8130; Konsignationslager nicht abgebildet; die Wahl monatlich/vierteljährlich (50.000-€-Grenze) prüft accounti nicht selbst. Die Datei beginnt mit `#v3.0` und `#ve3.2.1` wie das Beispiel der ELSTER-Hilfe (dort „CSV-Version“ und „Excel-Version“); ob die zweite Zeile Pflicht ist, sagt die Hilfe nicht — **ein echter Probeimport im ELSTER-Portal steht aus**.
- **OSS-Meldung** bleibt der bestehende Datei-Export; die Frist ist unverschoben übernommen.
- **Postgres:** Protokoll-Trigger nur unter SQLite (wie USt-IdNr.-Protokoll).
- **Attrappe nur für Prüf- und Testfall-Läufe.** Ein CLI-Probelauf mit `elster.uebermittler: attrappe` erreicht den Abgabeweg (Freigabe → echt → Zahllast) nicht mehr; der ist nur in Tests mit dem ERiC-Doppel geprüft. Der Testlauf vor der ersten Abgabe zählt nur über denselben Weg — ein Prüflauf ohne ERiC oder mit der Attrappe genügt für ERiC nicht.
- **„Abgabe ungewiss“:** Wirft der Übermittler nach dem Versand eine unerwartete Ausnahme, steht ein gescheiterter Eintrag im Protokoll und die Freigabe bleibt unverbraucht. Ob ELSTER die Anmeldung angenommen hat, muss der Mensch in Mein ELSTER prüfen; accounti sperrt einen erneuten Versand nicht.
- **Verrechnete Posten:** Eine Berichtigung nach unten kürzt den offenen Posten über `aktualisiere_posten`; der Status bleibt „offen“ bzw. „teilbezahlt“, eine eigene Kennzeichnung „durch Berichtigung gemindert“ gibt es nicht — nachvollziehbar ist es über den Eigenbeleg der Berichtigung. `opos/ausgleich` nimmt bei einem Kontakt mit nur einem Personenkonto dieses für beide Richtungen (Erstattung des Finanzamts auf das Kreditorenkonto).
- **Eine Voranmeldung je Zeitraum** für die eine Firma aus `mandant`; mehrere Gesellschaften (Baustein 11) nicht.

## Doku-Bausteine

### README — Statuszeilen (Tabelle „Steuer & Abschluss“)

```markdown
| ✅ | **USt-Voranmeldung** | Kennziffern nach Vordruck 2026 aus den Buchungen (Steuerschlüssel + Automatikkonten), volle Euro wie ELSTER, Plausibilisierung (ohne Steuerschlüssel, unbestätigte USt-IdNr., Verprobung, Vormonatsvergleich), Freigabe durch den Menschen |
| 🟨 | **Elektronische Übermittlung** | ELSTER-Datensatz UStVA/Dauerfristverlängerung, Testmodus ohne Abgabe, ERiC-Anbindung über ctypes (mit eigener Hersteller-ID und Zertifikat), unveränderbares Protokoll, Zahllast als offener Posten beim Finanzamt; Zusammenfassende Meldung als Portaldatei |
| ✅ | **Fristenkalender** | UStVA, Dauerfristverlängerung, Sondervorauszahlung, ZM, OSS — verschoben nach § 108 Abs. 3 AO mit Feiertagen des Bundeslands |
```

### README — Nutzungsblock (nach „USt-IdNr.-Prüfung“)

````markdown
### Umsatzsteuer-Voranmeldung und ELSTER

```bash
accounti ustva --period 2026-08                 # Kennziffern (Vordruck 2026) + Plausibilisierung
accounti ustva pruefen --period 2026-08         # nur die Befunde; Fehler sperren die Freigabe
accounti ustva freigeben --period 2026-08 --von "Erika Muster"
accounti ustva uebermitteln --period 2026-08 --test --ausgabe ustva.xml   # prüfen, nichts geht raus
accounti ustva uebermitteln --period 2026-08    # abgeben (ERiC), Protokoll, Zahllast als offener Posten
accounti ustva dauerfrist --jahr 2027           # Dauerfristverlängerung + Sondervorauszahlung (1/11)
accounti zm --period 2026-Q3 --csv zm.csv       # Zusammenfassende Meldung für den Portal-Import
accounti fristen --jahr 2026 --bundesland BY    # Fristenkalender mit Wochenend- und Feiertagsverschiebung
accounti elster pin                             # Zertifikats-PIN verschlüsselt ablegen
accounti elster protokoll                       # Übermittlungsprotokoll + Prüfung auf Unverändertheit
accounti elster zahllast                        # fehlende Zahllast-Buchungen zu Abgaben nachholen
```

Abgegeben wird nur, was ein Mensch freigegeben hat — die Freigabe hängt an den Formularwerten;
ändern sich danach Buchungen, passt sie nicht mehr, und ein neuer Fehler-Befund sperrt die Abgabe
auch mit Freigabe. Der erste Lauf eines Betriebs ist immer der Testmodus: Ohne erfolgreichen
Prüflauf über ERiC wird nur geprüft, erst der nächste Aufruf gibt ab. Ohne ERiC (Registrierung beim
Bayerischen Landesamt für Steuern, eigene Hersteller-ID, Zertifikat) bleibt der Testmodus: Der
Datensatz wird erzeugt und geprüft, aber nicht abgegeben; die Attrappe (`elster.uebermittler:
attrappe`) prüft und testet nur, sie gibt nie ab.
````

### README — Abschnitt „OSS-Verfahren“, letzte Zeile ersetzen

```markdown
- Meldet OSS-Umsätze in der USt-Voranmeldung **nur als Nettoumsatz in Kz 45** (Anleitung 2026, Zeile 36) — die Steuer läuft über die OSS-Meldung
```

### CHANGELOG

```markdown
### Hinzugefügt
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

### Geändert
- `steuer/voranmeldung.py` bildet den amtlichen Vordruck 2026 ab: alle Kennziffern mit Zeile,
  Bemessungsgrundlagen in vollen Euro, Steuer zu Kz 81/86/89/93 wie ELSTER aus der
  Bemessungsgrundlage, Kz 83 als Ergebnis; § 13b getrennt in 46/47, 73/74 und 84/85;
  ig. Erwerb 7 % (Kz 93)
- OSS-Umsätze erscheinen in der Voranmeldung als Nettoumsatz in Kz 45 (vorher: gar nicht)

### Behoben
- `opos verbuchen` bucht EU-Leistungen mit Steuerschuld des Empfängers (Kategorie AE) auf
  8336 statt 8338 (8338 ist im SKR03 „Drittland, nicht steuerbar“); ältere Buchungen auf
  8338/8339 an EU-Unternehmer mit USt-IdNr. meldet die Plausibilisierung als Warnung
- Zahlungsausgleich: ein Posten gegen einen Kontakt mit nur einem Personenkonto (z. B.
  Erstattung des Finanzamts) bucht auf dieses Konto, statt abzubrechen
- DATEV-Steuerschlüssel für ig. Erwerb (19/18) und § 13b (94) in `steuer/umsatzsteuer.py`
```

### docs/bauplan.md — Absatz (Bausteinkarte: Baustein 9 bleibt 🟨)

```markdown
**Baustein 9 ist teilweise fertig:** Kennziffern nach Vordruck 2026 aus den Buchungen,
Plausibilisierung, Freigabe durch den Menschen, ELSTER-Datensatz mit Testmodus, Übermittler mit
ERiC-Adapter, unveränderbares Übermittlungsprotokoll, Zahllast als offener Posten,
Sondervorauszahlung, Zusammenfassende Meldung als Portaldatei und Fristenkalender stehen
([Plan](plans/2026-10-25-steuermeldungen-elster.md)). Was fehlt, ist der erste echte Lauf: Er
braucht die Registrierung als Entwickler beim Bayerischen Landesamt für Steuern, eine eigene
Hersteller-ID (die Test-ID 74931 ist seit ERiC 39.4 gesperrt) und ein ELSTER-Zertifikat. Fristen
werden Aufgaben, sobald Baustein 8 steht; Periodenabschluss und Prüfbefunde prüft die
Plausibilisierung, sobald Baustein 7 steht.
```

### docs/architektur.md — Modulabschnitt (ersetzt „`elster/` *(geplant …)*“, ergänzt `steuer/`)

```markdown
### `elster/` *(teilweise — [Baustein 9](specs/2026-08-10-steuermeldungen-elster.md))*

Die Rechenlogik liegt in `steuer/`; hier kommen Datensatz, Abgabe und Nachweis dazu.

- `konfiguration.py` — Abschnitt `elster` (`lade_elster`), alles optional. *(vorhanden)*
- `steuernummer.py` — Steuernummer des Landes → 13-stelliges ELSTER-Format, Finanzamtsnummer. *(vorhanden)*
- `datensatz.py` — ELSTER-XML (TransferHeader/NutzdatenHeader v11, Nutzdaten `ustva/v2026`, Kz09 = Hersteller-ID) für Voranmeldung und Dauerfristverlängerung; interne Prüfung inkl. nachgerechneter Kz 83. *(vorhanden)*
- `uebermittlung.py` — Schnittstelle `Uebermittler` (`pruefe`, `sende`), `AttrappenUebermittler`, Auswahl: ERiC nur mit Bibliothek, Zertifikat und PIN-Datei. *(vorhanden)*
- `eric.py` — ERiC über ctypes (Mt-API: Instanz, Zertifikat, `EricMtBearbeiteVorgang` mit EBV-8 zum Prüfen und EBV-6 zum Senden, Transferticket und PDF; Plugins aus `plugins2`). *(vorhanden, nicht gegen ELSTER erprobt)*
- `pin.py` — Zertifikats-PIN mit dem Tresor aus `bank/` verschlüsselt in einer Datei außerhalb der Datenbank. *(vorhanden)*
- `freigabe.py` — Freigabe durch einen Menschen, gebunden an den Hash der Formularwerte, einmal verwendbar. *(vorhanden)*
- `protokoll.py` — Tabelle `steuermeldung_protokolle`: Datensatz, Ticket, Zeitpunkt, Ergebnis, Prüfbericht, Serverantwort; nur anfügen, Hash-Kette, SQLite-Trigger, Datensatz und PDF im Belegarchiv; `pruefe_protokoll()` findet Lücken, Änderungen und veränderte Archivdateien. Eine berichtigte Anmeldung tritt daneben. *(vorhanden)*
- `zahllast.py` — Zahllast als Eigenbeleg, Buchung 1780 (SKR04 3820) an Kreditor „Finanzamt“ und offener Posten zur Abgabefrist, Erstattung als Forderung; Berichtigung bucht die Differenz und verrechnet sie mit dem offenen Posten; Sondervorauszahlung auf 1781/3830; `buche_fehlende` holt gescheiterte Buchungen nach. *(vorhanden)*
- `ustva.py` — Ablauf vorbereiten → freigeben → übermitteln (Testmodus, Testfall, echt; Testmodus beim ersten Lauf, Attrappe nie echt). *(vorhanden)*

Ergänzungen in `steuer/`:

- **`voranmeldung.py`** — Vordruck 2026: alle Kennziffern mit Zeile und Art, Bemessungsgrundlagen in vollen Euro, Steuer zu 81/86/89/93 wie ELSTER, Kz 83.
- **`kennziffern.py`** — Ermittlung aus Buchungssätzen: DATEV-Schlüssel und Kennzifferkonten (SKR03/SKR04), Vorzeichen über die Sachkontoseite bzw. die Zugangsseite der Kennziffer, Erlösschmälerungen über den Beleg, Warnungen (§ 13b ohne Leistenden, Steuerkonto ohne Kennziffer).
- **`plausibilitaet.py`** — Befunde mit Schweregrad vor der Abgabe; Fehler sperren die Freigabe.
- **`zeitraum.py`**, **`feiertage.py`**, **`fristen.py`** — Meldezeiträume, Feiertage je Land, Fristen nach § 108 Abs. 3 AO.
- **`zusammenfassende_meldung.py`** — ZM je USt-IdNr. (L/D/S) mit CSV für den Portal-Import.
```

### config/accounti.example.yaml — neuer Abschnitt

```yaml
# Steuermeldungen & ELSTER (optional — ohne diesen Abschnitt gelten die Standards)
elster:
  voranmeldungszeitraum: monat     # monat oder quartal (§ 18 Abs. 2 UStG)
  dauerfristverlaengerung: false   # Frist + 1 Monat (§ 46 UStDV)
  # sondervorauszahlung: {2026: 4000.00}  # festgesetzte SVZ je Jahr (Kz 39 im Dezember);
  #                                      # sonst die angemeldete aus dem Protokoll
  bundesland: BY                   # Feiertage (§ 108 Abs. 3 AO) und Steuernummer im ELSTER-Format
  # steuernummer: "9181081508155"  # 13-stellig; sonst mandant.steuernummer
  finanzamt:
    name: "Finanzamt München"      # Kreditor für die Zahllast
    # iban: "DE…"                  # hilft der Zahlungszuordnung
  # hersteller_id: "12345"         # eigene Hersteller-ID (Kz09) — ohne sie nur Testmodus
  uebermittler: eric               # eric oder attrappe (nur --test/--testfall, gibt nie ab)
  eric:
    bibliothek: /opt/eric/lib/libericapi.so
    plugins: /opt/eric/lib/plugins2  # Standard: plugins2 neben der Bibliothek
    log: /var/log/accounti/eric
    zertifikat: /etc/accounti/elster.pfx
    pin_datei: /etc/accounti/elster-pin.enc   # 'accounti elster pin', Schlüssel aus ACCOUNTI_SCHLUESSEL
  abweichung_prozent: 50           # Vormonats-/Vorjahresvergleich: ab hier ein Hinweis …
  abweichung_mindestens: 1000      # … wenn die Differenz mindestens so groß ist (Euro)
  # steuerrelevante_konten: ["2750-2752", "8000-8959"]  # ersetzt die Standardliste
  #                                           # der Erlöskonten (SKR04: 4000-4799,
  #                                           # 4833-4836, 4841-4842, 4844-4845,
  #                                           # 4848-4852, 4860-4869, 4940-4949,
  #                                           # 6884-6892)
  # kennziffern_konten: {"8150": 43, "1588": 62}  # eigene Konten → Kennziffer
  #                                           # (Bemessungsgrundlage oder Steuerfeld)
```
