# Anlagenbuchhaltung & Jahresabschluss (Baustein 12) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Anlagegüter werden geführt und schreiben sich selbst fort — linear zeitanteilig nach
Monaten, degressiv in den gesetzlichen Zeitfenstern, als geringwertiges Wirtschaftsgut, im
Sammelposten, als digitales Wirtschaftsgut oder als Elektrofahrzeug —, jeweils mit den Grenzbeträgen,
die **am Anschaffungstag** galten. Zum Jahresende stehen Anlagenspiegel, Summen- und Saldenliste und
Einnahmenüberschussrechnung; Abgrenzungen werden vorgeschlagen (mit Auflösung im Folgejahr), das
Kassenbuch kann nicht ins Minus laufen, ein Bankkonto, dessen Buchbestand nicht zum Kontoauszug
passt, sperrt den Abschluss, und der Saldovortrag trägt die Schlusssalden exakt ins neue Jahr und
sperrt das alte.

**Spec:** [`docs/specs/2026-08-10-anlagen-jahresabschluss.md`](../specs/2026-08-10-anlagen-jahresabschluss.md),
Abschnitte 4.1, 4.2, 4.4, 4.5, 4.6 (SuSa, EÜR), 4.8, 4.9 · Akzeptanzkriterien 1–7 ·
**Baut auf:** Baustein 1 (Buchungssätze, Kontierung), 4 (Personenkonten), 5 (Bankkonten, Sachkonto
am Umsatz)

```
UNTERJÄHRIG                                   JAHRESABSCHLUSS (Jahr J)
Beleg/Buchung auf Anlagekonto                 accounti abschluss pruefen --jahr J
   │  anlagen anlegen (ND aus AfA-Tabelle)        ├─ unfreigegebene / ungebuchte Vorgänge
   ▼                                             ├─ Bank: Buchbestand = Kontoauszug?  (sperrt)
Anlagegut ── Rechtsstand am Anschaffungstag      ├─ Kasse: Kassenbuch = Kassenkonto?
   │  (GWG-/Sammelposten-Grenzen, degressiv)     ├─ Anlagen: AfA gebucht? RBW = Anlagekonto?
   ▼                                             ├─ Abgrenzungen entschieden? Vortragskonten = 0?
anlagen afa --jahr J [--bis-monat M]          accounti abschluss buchen  → AfA + ARAP/PRAP-Vorschläge
   │  bucht Soll − schon gebucht (Vorschlag)  accounti abschluss susa | euer
   ▼                                          accounti abschluss vortrag --jahr J
Anlagenspiegel · Abgang (RBW, Erlös, Ergebnis)   └─ EB-Buchungen 01.01.J+1, Jahr J gesperrt,
                                                    Protokoll; Änderung nur nach "oeffnen"
Kassenbuch: kasse buchen (lfd. Nr., Bestand ≥ 0, unveränderbar, Storno statt Änderung)
```

---

## Recherche (Stand 20.10.2026)

| Thema | Ergebnis | Quelle |
|-------|----------|--------|
| GWG-Grenze § 6 Abs. 2 EStG | Sofortabzug, wenn die AK/HK **ohne Vorsteuer 800 €** nicht übersteigen; Verzeichnis ab mehr als 250 €, entfällt, wenn die Angaben aus der Buchführung ersichtlich sind. Gilt für Anschaffungen **ab 01.01.2018**; die im Wachstumschancengesetz diskutierte Anhebung auf 1.000 € ist nicht Gesetz geworden. | [§ 6 EStG, gesetze-im-internet.de](https://www.gesetze-im-internet.de/estg/__6.html) (abgerufen 20.10.2026); Gesetz gegen schädliche Steuerpraktiken im Zusammenhang mit Rechteüberlassungen v. 27.06.2017 ([Deubner](https://www.deubner-steuern.de/news/details/artikel/gesetz-gegen-schaedliche-steuerpraktiken-neues-bei-gwg-und-sanierungsgewinnen/)) |
| Sammelposten § 6 Abs. 2a EStG | mehr als **250 €** bis **1.000 €**; Auflösung im Bildungsjahr und den vier Folgejahren mit **je einem Fünftel**, unabhängig vom Anschaffungsmonat und von der Nutzungsdauer; Abgang mindert den Sammelposten nicht; Wahlrecht **einheitlich** für alle Wirtschaftsgüter des Wirtschaftsjahres; bis 250 € Sofortabzug. Scheidet ein Wirtschaftsgut im Anschaffungsjahr aus, gehört es nicht in den Sammelposten. | § 6 Abs. 2a EStG (wie oben); [BMF 30.09.2010, IV C 6 - S 2180/09/10001](https://kommunsense.de/wp_16/wp-content/uploads/newsmappen/bmf/bmf_30_09_2010.pdf) Rz. 6, 7, 10, 14, 15 |
| Frühere Grenzen | 2010–2017: GWG 410 €, Sammelposten 150–1.000 € (Wahlrecht, Wachstumsbeschleunigungsgesetz v. 22.12.2009, BGBl. 2009 I S. 3950). 2008–2009: Sofortabzug bis 150 € **zwingend**, Sammelposten 150–1.000 € **zwingend** (Unternehmensteuerreformgesetz 2008). Vor 2008: GWG 410 €, kein Sammelposten. | BMF 30.09.2010 (Einleitung, Rz. 2–7); [iww, Unternehmensteuerreform 2008](https://www.iww.de/asr/archiv/unternehmensteuerreform-2008-bei-der-abschreibung-gelten-neue-regeln-f20382); H 6.13 EStH 2008 |
| Degressive AfA — Investitionssofortprogramm | bewegliche Wirtschaftsgüter, angeschafft/hergestellt **nach dem 30.06.2025 und vor dem 01.01.2028**: höchstens das **Dreifache** des linearen Satzes, **höchstens 30 %**. Gesetz für ein steuerliches Investitionssofortprogramm, verkündet 18.07.2025 (BGBl. 2025 I Nr. 161). Nicht 2,5-fach/25 % — so stand es nur in Vorabtabellen von 2024. Für 01.01.–30.06.2025 gibt es **keine** degressive AfA. | [§ 7 EStG, gesetze-im-internet.de](https://www.gesetze-im-internet.de/estg/__7.html) (Abs. 2 nennt nur noch dieses Fenster); [EY, Stand Verkündung 18.07.2025](https://www.ey.com/content/dam/ey-unified-site/ey-com/de-de/technical/steuernachrichten/steuerl_invprogramm_22072025_final.pdf) |
| Degressive AfA — Wachstumschancengesetz | angeschafft **nach dem 31.03.2024 und vor dem 01.01.2025**: höchstens **Zweifaches**, **höchstens 20 %** (§ 7 Abs. 2 EStG i. d. F. v. 27.03.2024). | EY (wie oben, Abschnitt 2: „gilt weiterhin in der Fassung vom 27.03.2024“); [Haufe, degressive Abschreibung](https://www.haufe.de/id/beitrag/abschreibung-degressive-HI13891330.html) |
| Degressive AfA — Corona | angeschafft **nach dem 31.12.2019 und vor dem 01.01.2023**: höchstens **2,5-fach**, **höchstens 25 %**. | EY (wie oben) |
| Elektrofahrzeuge § 7 Abs. 2a EStG | rein elektrische Fahrzeuge, angeschafft 01.07.2025–31.12.2027: **75 %** im Anschaffungsjahr (auch unterjährig, keine Zwölftelung), dann **10, 5, 5, 3, 2 %** der AK. | EY (wie oben, Abschnitt 6.2) |
| Zeitanteilige AfA § 7 Abs. 1 Satz 4 EStG | im Anschaffungsjahr ein Zwölftel weniger für jeden **vollen Monat vor** dem Anschaffungsmonat — Anschaffung im September: 4/12. Übergang degressiv → linear zulässig (§ 7 Abs. 3), umgekehrt nicht. Im Jahr des Ausscheidens nur zeitanteilig (R 7.4 Abs. 8 EStR, in der Praxis monatsweise). | § 7 EStG (wie oben); [Haufe zu R 7.4 Abs. 8](https://www.haufe.de/id/kommentar/frotschergeurts-estg-7-absetzung-fuer-abnutzung-oder-1654-afa-im-jahr-der-anschaffung-und-veraeusserung-7-abs5-s3-estg-HI11888944.html) |
| Computerhardware/Software | betriebsgewöhnliche Nutzungsdauer **1 Jahr** kann zugrunde gelegt werden; keine Sofortabschreibung, aber „es wird nicht beanstandet“, wenn die AfA im Anschaffungsjahr in voller Höhe vorgenommen wird (Rz. 1.4). Gilt für Wirtschaftsjahre, die nach dem 31.12.2020 enden. | BMF 22.02.2022, IV C 3 - S 2190/21/10002 :025 (ersetzt BMF 26.02.2021); [FGS](https://www.fgs.de/news-and-insights/blog/detail/praezisierung-des-bmf-schreibens-zur-nutzungsdauer-von-computerhardware-und-software-zur-dateneingabe-und-verarbeitung) |
| AfA-Tabelle AV | BMF 15.12.2000, IV D 2 - S 1551 - 188/00, BStBl I 2000 S. 1532; gilt für Anschaffungen nach dem 31.12.2000. Hinterlegt (Fundstelle → Jahre): Pkw 4.2.1 → 6, Motorräder/Fahrräder 4.2.2 → 7, Lkw 4.2.3 → 9, Stapler 4.5 → 8, Mobilfunkendgeräte 6.13.2.2 → 5, Telefonanlagen 6.13.1 → 10, Faxgeräte 6.13.3 → 6, PC/Notebook/Peripherie 6.14.3.2 → 3 (überholt: 1 Jahr nach BMF 2022), Foto/Video/Audio 6.14.4 → 7, Präsentationsgeräte 6.14.6 → 8, Registrierkassen 6.14.7 → 6, Kopierer 6.14.10 → 7, Aktenvernichter 6.14.13 → 8, Büromöbel 6.15 → 13, Klimageräte mobil 6.5 → 11, Ladeneinbauten 3.7 → 8, Container 3.6 → 10, Tresore 6.19.2 → 23, Werkstatt-/Lagereinrichtung 6.1 → 14, Messestände 6.3 → 6, Photovoltaik 3.1.6 → 20. | [AfA-Tabelle AV (IHK München, Originalabdruck)](https://www.ihk-muenchen.de/ihk/documents/Recht-Steuern/Steuerrecht/Einkommensteuer/AfA-Tabelle-AV.pdf) |
| RAP-Verzicht | § 5 Abs. 5 Satz 2 EStG: Auf aktive/passive RAP kann verzichtet werden, wenn die einzelne Ausgabe/Einnahme die GWG-Grenze nicht übersteigt; einheitlich für alle. Erstmals für Wirtschaftsjahre, die nach dem 31.12.2021 enden (JStG 2022). | [§ 5 EStG](https://www.gesetze-im-internet.de/estg/__5.html); [BT-Drs. 20/4229](https://xpert.digital/wp-content/uploads/2022/12/Drucksache-20-4229.pdf) |
| Anlage EÜR 2025 | BMF 29.08.2025, IV C 6 - S 2142/00023/010/001, BStBl I 2025 S. 1652. Zeilen (Kennzahl): 12 (111) Kleinunternehmer · 15 (112) USt-pflichtige BE · 16 (103) steuerfreie/nicht steuerbare BE · 17 (140) vereinnahmte USt · 18 (141) erstattete USt · 19 (102) Veräußerung/Entnahme AV · 20 (106) private Kfz-Nutzung · 21 (108) sonstige Entnahmen · 23 (159) Summe BE · 27 (100) Waren · 29 (110) Fremdleistungen · 30 (120) Personal · 31 (136) AfA Grundstücke · 32 (131) AfA immateriell · 33 (130) AfA beweglich · 34 (134) Sonder-AfA · 36 (132) GWG · 37 (137) Sammelposten · 38 (135) Restbuchwerte · 39 (150) Miete · 41 (151) sonstige Grundstücksaufwendungen · 43 (280) Telekommunikation · 44 (221) Reisekosten · 45 (281) Fortbildung · 46 (194) Beratung/Buchführung · 47 (222) Miete/Leasing bewegl. WG · 48 (225) Erhaltung · 49 (223) Beiträge/Versicherungen · 50 (228) EDV · 51 (229) Arbeitsmittel · 52 (226) Entsorgung · 53 (227) Verpackung/Transport · 54 (224) Werbung · 55 (232)/56 (234) Schuldzinsen · 57 (185) Vorsteuer · 58 (186) an das FA gezahlte USt · 60 (183) übrige · 62 (174) Geschenke · 63 (175) Bewirtung · 68 (144) Kfz-Leasing · 69 (145) Kfz-Steuern/Versicherung/Maut · 70 (146) sonstige Fahrtkosten · 71 (147) fremde Fahrzeuge · 75 (199) Summe BA · 76/77 Gewinnermittlung · 106 (122) Entnahmen · 107 (123) Einlagen. | [BMF-Schreiben mit Vordruck (Abdruck)](https://www.steuerschroeder.de/blog/wp-content/uploads/2025/09/2025-08-29-anlage-EUER-2025.pdf) — Zeilen aus Vordruck und Anleitung abgeglichen |
| Anlage EÜR 2026 | BMF 01.09.2026, IV C 6 - S 2142/00024/010/001. Neue Zeile 27 (Rücklage Tierbewertung LuF); Waren rücken nach 29, ab da **alle Zeilen +1** (z. B. AfA beweglich 34, GWG 37, Sammelposten 38, RBW 39, Vorsteuer 58, Summe BA 76, Entnahmen 107, Einlagen 108). Kennzahlen unverändert. | [BMF, Anlage EÜR 2026 (PDF)](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Einkommensteuer/2026-09-01-anlage-EUER-2026.pdf?__blob=publicationFile&v=4) |
| Kontenrahmen | DATEV SKR 03 und SKR 04, „Gültig für 2026“ (Art.-Nr. 11174/11175). SKR03: 0027 EDV-Software, 0320 Pkw, 0350 Lkw, 0400–0440 BGA, 0480 GWG, 0485 Sammelposten, 0490 sonstige BGA, 0880 Variables Kapital, 0980 ARAP, 0990 PRAP, 1000 Kasse, 1360 Geldtransit, 1590 Durchlaufende Posten, 1780 USt-Vorauszahlungen, 1800 Privatentnahmen, 1890 Privateinlagen, 2310/2315 Anlagenabgänge RBW bei Buchverlust/-gewinn, 4822 AfA immateriell, 4830 AfA Sachanlagen, 4832 AfA Fahrzeuge, 4855 Sofortabschreibung GWG, 4862 AfA Sammelposten, 8801/8820 Erlöse Anlagenverkäufe 19 % bei Buchverlust/-gewinn, 8800/8829 ohne USt, 9000/9008/9009 Saldenvorträge. SKR04: 0135, 0520, 0540, 0630–0690, 0670 GWG, 0675 Sammelposten, 1401/1406 VSt, 1460 Geldtransit, 1600 Kasse, 1800 Bank, 1900 ARAP, 2010 Variables Kapital, 2100/2180 Privat, 3801/3806 USt, 3820 USt-Vorauszahlungen, 3900 PRAP, 4845/4849 Erlöse Anlagenverkäufe bei Buchgewinn, 4855 RBW bei Buchgewinn, 6200/6220/6222 AfA, 6260 GWG, 6264 Sammelposten, 6885/6889 Erlöse bei Buchverlust, 6895 RBW bei Buchverlust. **2320/2720 sind im SKR03 2026 reserviert**, **4800 ist „Reparaturen und Instandhaltungen“** (nicht AfA). | [DATEV SKR 03 2026](https://www.datev.de/content/dam/markenassets/themen-und-produktgruppen/zielgruppen/mandant/unternehmer/branche/bau/11174%20SKR03%20BilrUg.pdf), [DATEV SKR 04 2026](https://www.datev.de/content/dam/markenassets/themen-und-produktgruppen/zielgruppen/mandant/unternehmer/branche/bau/11175%20SKR04%20BilrUg.pdf) |

## Schnitt in Pakete

| Paket | Inhalt | Akzeptanz |
|-------|--------|-----------|
| **1 Anlagenbuchhaltung** | Rechtsstand mit Gültigkeitszeiträumen, AfA-Tabelle, Anlagegut, AfA-Plan (linear, degressiv mit Wechsel, GWG, Sammelposten, digital, E-Fahrzeug), Wahlrechtsprüfung, AfA-Lauf (Monat/Jahr, idempotent, Korrektur), Abgang, Anlagenspiegel, `accounti anlagen …` | 1, 2 |
| **2 Kasse, Salden, Prüfungen** | Kontenrahmen-Zuordnung (Bestand/Erfolg/Steuer/Privat/Vortrag, SKR03/SKR04), Kontobewegungen mit Steueraufteilung, Summen- und Saldenliste, Kassenbuch, Kontoauszugssalden, Abschlussprüfungen mit Befunden, `accounti kasse …`, `accounti abschluss saldo|pruefen|susa` | 4, 5 |
| **3 Abgrenzung, EÜR, Vortrag** | ARAP/PRAP-Vorschläge mit Auflösung, EÜR nach Kennzahlen mit Zeilen je Vordruckjahr, Eröffnungssalden, Saldovortrag mit Jahressperre und Protokoll, Wiederöffnen, Durchlauf über ein Geschäftsjahr, `accounti abschluss buchen|abgrenzungen|euer|vortrag|oeffnen|eroeffnung` | 3, 6, 7 |

---

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Grenzbeträge | `anlagen/rechtsstand.yaml` im Paket: Zeiträume mit `von`/`bis` und Quelle für GWG, Verzeichnis, Sammelposten (inkl. Pflicht 2008/2009), degressive Fenster (Faktor, Höchstsatz), E-Fahrzeug-Staffel, digitale WG, RAP-Verzicht. Eigene Datei per `anlagen.rechtsstand` ersetzt/ergänzt Einträge. Maßgeblich ist das **Anschaffungsdatum** | Spec 5: Konfiguration mit Gültigkeitszeitraum; ein Zugang 2015 rechnet mit 410 €, ohne dass Code geändert wird |
| AfA-Tabelle | im selben Rechtsstand: Schlüssel → Bezeichnung, Jahre, Fundstelle, Vorschlagskonto je Kontenrahmen, ggf. AfA-Art; `--typ pkw` schlägt ND und Konto vor, `--nutzungsdauer` gewinnt immer | Spec: Vorschlag, immer änderbar |
| Anschaffungskosten | netto (ohne abziehbare Vorsteuer, § 9b EStG) | GWG-/Sammelpostengrenzen sind Nettogrenzen |
| Linear | monatsgenau: AfA kumuliert bis Monat k = AK · k / (12 · ND), kaufmännisch gerundet, gedeckelt auf AK; Jahresbetrag = Differenz der Kumulierten. Anschaffungsmonat zählt voll, Abgangsmonat auch | § 7 Abs. 1 Satz 4; keine Rundungsdrift, Summe = AK exakt |
| Degressiv | Satz = min(Faktor/ND, Höchstsatz) des Fensters am Anschaffungstag; vom Restbuchwert, im ersten und im Abgangsjahr zeitanteilig; automatischer Wechsel zur linearen AfA, sobald linear ≥ degressiv (§ 7 Abs. 3), abschaltbar (`wechsel_linear=False`). Außerhalb eines Fensters, für immaterielle WG oder ohne ND: Fehler | Wahlrecht bleibt beim Menschen (Art wird gewählt, nicht gesetzt), die Rechnung ist mechanisch |
| GWG | ganze AK im Anschaffungsmonat; nur bis zur GWG-Grenze des Anschaffungstags, sonst Fehler | § 6 Abs. 2 |
| Sammelposten | je Anlagekonto und Anschaffungsjahr ein Posten; 1/5 der Summe je Jahr **zum Jahresende** (Monatsläufe buchen ihn erst mit Monat 12), Rest im fünften Jahr; Abgang mindert nicht, außer im Anschaffungsjahr (dann normaler Abgang zum vollen Wert) | BMF 30.09.2010 Rz. 10, 14, 15 |
| Wahlrecht einheitlich | Ein Sammelposten im Jahr verlangt, dass alle Zugänge > Untergrenze bis 1.000 € des Jahres Sammelposten sind; 2008/2009 sind Sofortabzug und Sammelposten Pflicht. Verstöße: Fehler beim Anlegen | § 6 Abs. 2a Satz 5 |
| Digitale WG | Art `digital`: ND 1 Jahr, volle AfA im Anschaffungsjahr, ab Anschaffung 2021 | BMF 22.02.2022 Rz. 1.4 |
| E-Fahrzeuge | Art `e_fahrzeug`: Staffel aus dem Rechtsstand, Jahr 1 voll ab Anschaffungsmonat, Folgejahre (und Abgangsjahr) zeitanteilig | § 7 Abs. 2a |
| AfA-Lauf | `anlagen afa --jahr J [--bis-monat M]` bucht je Anlagegut **Soll bis M minus schon gebucht** (Tabelle `afa_vorgaenge`) — idempotent, monatlich oder jährlich nutzbar, ein nachträglicher Abgang erzeugt eine Korrektur. Eine Buchung je (AfA-Konto, Anlagekonto), Status „zur Prüfung“, Begründung je Anlagegut im Vorgang; Freigabe mit `anlagen freigeben --jahr J` oder `accounti bestaetige` | Spec 5: Abschlussbuchungen sind Vorschläge; Nachholen früherer Jahre gibt es bewusst nicht |
| Anlagekonto | Zugang wird über die normale Belegbuchung gebucht; `anlagen anlegen --beleg` prüft, ob der Beleg auf dem Anlagekonto steht, und schlägt sonst eine Umbuchung vor (`--umbuchen`) | keine doppelte Zugangsbuchung |
| Abgang | AfA bis einschließlich Abgangsmonat, RBW an 2310 (Buchverlust) bzw. 2315 (Buchgewinn/0); Erlös optional mit `--gegenkonto` auf 8801/8820 (19 % USt über `accounti.steuer`) bzw. 8800/8829 (`--ohne-ust`) | DATEV SKR03 2026 (2320/2720 reserviert) |
| Anlagenspiegel | aus dem AfA-Plan (Sollrechnung), je Anlagekonto bzw. Sammelposten-Jahrgang: AK Beginn, Zugang, Abgang, AK Ende, AfA kumuliert Beginn, AfA Jahr, AfA auf Abgänge, AfA kumuliert Ende, RBW Beginn/Ende; kein fiktiver Abgang für GWG/Sammelposten | Akzeptanz 2; die gebuchte AfA prüft `abschluss pruefen` gegen den Plan |
| Zählende Buchungen | Salden, SuSa, EÜR und Vortrag zählen nur freigegebene Buchungen (auto, geprüft, korrigiert, exportiert — wie der DATEV-Export); Vorschläge im Jahr sind ein Fehler-Befund | eine Bewertung wird bestätigt, nicht gesetzt |
| Steueraufteilung | Buchung mit BU 2/3/8/9 und Steuerbetrag: Nettoseite = die Seite, die kein Geld-/Personenkonto ist (sonst: VSt-Schlüssel → Soll, USt-Schlüssel → Haben); Steuer auf derselben Seite auf das Steuerkonto, die Gegenseite brutto. SKR03-Steuerkonten aus `accounti.steuer`, SKR04 aus der Kontenrahmendatei | genau so buchen Mapper, Belegkontierung, OPOS und Skonto; SuSa bleibt ausgeglichen |
| Kontenrahmen | `abschluss/kontenrahmen_skr03.yaml` und `…_skr04.yaml`: Kontoarten (Bestand, Erfolg, Steuer, Privat, Vortrag), Geldkonten, Steuerkonten, EÜR-Kennzahl je Kontenbereich (die engste Spanne gewinnt; Steuer- und USt-Vorauszahlungskonten nach Saldorichtung), Namen; eigene Datei per `abschluss.kontenzuordnung` | Spec 4.6: Zuordnung als Konfiguration wie die BWA-Zuordnung in `config/skr03.yaml` |
| EÜR | Kennzahl je Konto, Zeile und Text je Vordruckjahr (`abschluss/euer_vordrucke.yaml`, 2025 und 2026); fehlt das Jahr, gilt der jüngste ältere Vordruck mit Hinweis. Konten ohne Zuordnung erscheinen als „nicht zugeordnet“ (Warnung) und zählen mit — Gewinn = Saldo aller EÜR-Konten der SuSa | Akzeptanz 6; Zeilen verschieben sich (2026: +1), Kennzahlen nicht |
| EÜR-Steuerkonten | bei `gewinnermittlung: euer` sind Vorsteuer, Umsatzsteuer und USt-Vorauszahlungen Erfolgskonten (Kz 185, 140, 186/141), bei `bilanz` Bestandskonten | Zufluss-/Abflussprinzip |
| Abgrenzung | nur bei `gewinnermittlung: bilanz`. Kandidat: freigegebene Buchung des Jahres auf ein Erfolgskonto mit Leistungszeitraum im Text (Positionen, Belegnummer, Verwendungszweck, Buchungstext; Formen `01.12.2026–30.11.2027`, `… bis …`, `12/2026–11/2027`), der über den Stichtag reicht; Anteil monatsgenau bei ganzen Monaten, sonst taggenau; ARAP 0980/1900, PRAP 0990/3900. Vorschlag speichert Abgrenzung **und** Auflösung (01.01.J+1); Bestätigen bucht beide, Ablehnen keine; Vorschlag je Buchung genau einmal; manuell `abschluss abgrenzen <BUCHUNG> --von --bis`. RAP-Verzicht bis GWG-Grenze nur mit `rap_verzicht_bis_gwg: true` | Akzeptanz 3, Spec 4.2; EÜR kennt keine RAP (§ 11 EStG) |
| Kassenbuch | eigene Tabelle `kassenbuch`: laufende Nummer, Datum, Betrag (+/−), Text, Beleg, Gegenkonto, Steuersatz, Erfassungszeitpunkt; nur anfügen (ORM-Sperre, Storno als Gegeneintrag). Vor jedem Eintrag wird der Bestandsverlauf ab dem Buchungstag nachgerechnet — fällt er an irgendeinem Tag unter 0, **wird abgelehnt** (`KasseNegativError`), auch bei Rückdatierung und Storno | Akzeptanz 4, § 146 Abs. 1 AO |
| Kasse → Buchung | jeder Kassenvorgang wird eine Transaktion mit dem Kassenkonto als Sachkonto (dann kontiert `classify`, gleicht `opos zuordnen`/`bank abgleich` ab); mit `--konto` sofort ein geprüfter Buchungssatz, Steuer über `accounti.steuer` | ein Pfad für alle Geldbewegungen |
| Bank-Abstimmung | Tabelle `kontoauszugssalden` (Bankkonto, Stichtag, Saldo, Erfasser); Prüfung je Sachkonto: Summe der Kontoauszugssalden zum 31.12. = Buchbestand (inkl. EB); fehlender Saldo, Abweichung oder ein nicht eingerichtetes Bankkonto mit Buchungen sind **Fehler** und blockieren den Vortrag | Akzeptanz 5 |
| Abschlussprüfungen | benannte Prüfungen, je einzeln aufrufbar, Befund mit Schwere (Fehler/Warnung/Hinweis): unfreigegeben, ungebucht, Bank, Kasse, Anlagen (AfA gebucht, RBW = Anlagekonto), Abgrenzungen offen, Verrechnungskonten, Vortragskonten ausgeglichen, EÜR: offene Personenkonten, EÜR: nicht zugeordnete Konten | Spec 4.5; Baustein 7 existiert noch nicht, deshalb eigene schlanke Befunde |
| Saldovortrag | Schlusssalden = Bestandskonten, Erfolgs- und Privatkonten (bei EÜR auch Steuerkonten) auf das Kapitalkonto (`ergebnis_konto`, SKR03 0880 / SKR04 2010); EB-Buchungen am 01.01.J+1 gegen 9000 (Debitoren 9008, Kreditoren 9009), gebucht wird nur die Differenz zu schon vorhandenen EB-Werten (erneuter Vortrag nach Wiederöffnen = Korrektur, keine Löschung). Nur ohne Fehler-Befund | Akzeptanz 7 |
| Jahressperre | Tabelle `abschluesse`; ein ORM-Ereignis auf `buchungssaetze` (in `tabellen_abschluss.py`, ohne Änderung an bestehendem Code) verweigert Anlegen, Ändern und Löschen von Buchungen in gesperrten Jahren (`JahrGesperrtError`); Kassenbuch und AfA-Lauf prüfen vorher. `abschluss oeffnen --grund` hebt die Sperre auf, nur wenn das Folgejahr offen ist; jede Aktion steht in `abschlussprotokoll` (nur anfügen, Hash-Kette) | Spec 4.8: Änderung nur mit erneutem Abschluss und Protokoll |
| Eröffnungssalden | `abschluss eroeffnung --jahr J --konto K --saldo S` für das erste Jahr in accounti (EB gegen 9000/9008/9009, geprüft) | ohne EB-Werte kann der Bankabgleich nicht stimmen |
| Konfiguration | Abschnitte `anlagen`, `abschluss`, `kasse` mit eigenen Ladern (`lade_anlagen`, `lade_abschluss`, `lade_kasse`); Standards je Kontenrahmen aus `buchhaltung.kontenrahmen` (SKR03/SKR04); alles läuft ohne die Abschnitte | Auftrag |
| Abhängigkeiten | keine neuen | Standardbibliothek, pydantic, sqlalchemy, pyyaml, typer, rich reichen |

## Aufgaben

### Paket 1 — Anlagenbuchhaltung

- [x] **Rechtsstand** (`anlagen/rechtsstand.py`, `rechtsstand.yaml`): Grenzen am Stichtag (2007, 2009, 2015, 2026), degressives Fenster (2020–2022, 04–12/2024, 07/2025–2027; Lücke 01–06/2025), E-Fahrzeug, digital, eigene Datei ersetzt/ergänzt (`tests/test_anlagen_rechtsstand.py`).
- [x] **Modell, Tabellen, Repository:** `models/anlagen.py` (`AfaArt`, `Anlagegut`, `AfaVorgang`), `db/tabellen_anlagen.py`, `db/repo_anlagen.py` (laufende Inventarnummer).
- [x] **AfA-Plan** (`anlagen/afa.py`, rein): linear September 4/12 (**Akzeptanz 1**), voller Jahresverlauf, Abgang im laufenden Jahr, degressiv 30 % mit Wechsel, 2024 20 %, außerhalb des Fensters Fehler, GWG 800/410/150 je Jahr, Sammelposten über fünf Jahre (Summe, Rest), digital, E-Fahrzeug, Monatskumulierte, Vorschlag der Art, einheitliches Wahlrecht (`tests/test_anlagen_afa.py`).
- [x] **Konfiguration** (`anlagen/konfiguration.py`): Konten je Kontenrahmen, eigener Rechtsstand, ohne Abschnitt Standards (`tests/test_anlagen_konfiguration.py`).
- [x] **AfA-Lauf** (`anlagen/lauf.py`): Monatslauf + Jahreslauf ergeben zusammen die Jahres-AfA, zweiter Lauf bucht nichts, Korrektur nach Abgang, Sammelposten erst im Dezember, Begründung, Status zur Prüfung, Freigabe (`tests/test_anlagen_lauf.py`).
- [x] **Abgang** (`anlagen/abgang.py`): RBW, Buchgewinn/-verlust-Konten, Erlös mit USt, Sammelposten unverändert, Abgang im Anschaffungsjahr (`tests/test_anlagen_abgang.py`).
- [x] **Anlagenspiegel** (`anlagen/spiegel.py`): gegen handgerechnete Sollrechnung (**Akzeptanz 2**) (`tests/test_anlagen_spiegel.py`).
- [x] **Anlegen aus Beleg:** AK/Datum/Bezeichnung aus dem Beleg, Umbuchungsvorschlag, wenn der Beleg auf einem Aufwandskonto steht; Vorschläge aus Buchungen auf Anlagekonten ohne Anlagegut.
- [x] **CLI** (`befehle/anlagen.py`): `liste`, `tabelle`, `anlegen`, `plan`, `afa`, `freigeben`, `abgang`, `spiegel [--csv]`, `vorschlaege` (`tests/test_cli_anlagen.py`).

### Paket 2 — Kasse, Salden, Prüfungen

- [x] **Kontenrahmen** (`abschluss/kontenrahmen.py`, `kontenrahmen_skr03.yaml`, `kontenrahmen_skr04.yaml`): Kontoart je Gewinnermittlung, Geldkonten, Steuerkonten, EÜR-Kennzahl, engste Spanne gewinnt (`tests/test_abschluss_kontenrahmen.py`).
- [x] **Salden** (`abschluss/salden.py`): Bewegungen mit Steueraufteilung für alle Buchungsmuster (Bank, Beleg, OPOS, Skonto, Gutschrift), nur freigegebene, EB-Werte, SuSa ausgeglichen (`tests/test_abschluss_salden.py`).
- [x] **Konfiguration** (`abschluss/konfiguration.py`): `abschluss` und `kasse`, Standards je Kontenrahmen.
- [x] **Kassenbuch** (`abschluss/kassenbuch.py`, `models/kasse.py`, `db/tabellen_kasse.py`, `db/repo_kasse.py`): laufende Nummer, Bestand, Tagessaldo, Ablehnung bei negativem Bestand (**Akzeptanz 4**) — auch rückdatiert und per Storno, unveränderbar, Transaktion/Buchung, gesperrtes Jahr (`tests/test_kassenbuch.py`).
- [x] **Kontoauszugssalden und Prüfungen** (`abschluss/pruefungen.py`, `models/abschluss.py`, `db/tabellen_abschluss.py`, `db/repo_abschluss.py`): jede Prüfung mit auslösendem und nicht auslösendem Fixture; Bankabweichung blockiert (**Akzeptanz 5**) (`tests/test_abschluss_pruefungen.py`).
- [x] **CLI** (`befehle/kasse.py`, `befehle/abschluss.py`): `kasse anfangsbestand|buchen|storno|liste|bestand`, `abschluss saldo|pruefen|susa [--csv]` (`tests/test_cli_kasse.py`, `tests/test_cli_abschluss.py`).

### Paket 3 — Abgrenzung, EÜR, Vortrag

- [x] **Abgrenzung** (`abschluss/abgrenzung.py`): Zeitraum aus Text, Anteil monats-/taggenau, Dezember-Jahresversicherung → ARAP-Vorschlag mit Auflösung 01.01. (**Akzeptanz 3**), PRAP, ohne Zeitraum/ohne Folgejahr kein Vorschlag, idempotent, Bestätigen bucht beide, Ablehnen keine, RAP-Verzicht, EÜR ohne Vorschläge (`tests/test_abschluss_abgrenzung.py`); Prüfung `abgrenzungen` — offene Vorschläge sind ein Fehler-Befund (`tests/test_abschluss_pruefungen.py`).
- [x] **EÜR** (`abschluss/euer.py`, `euer_vordrucke.yaml`): Zeilen 2025/2026, Kennzahlen, Summen, nicht zugeordnete Konten, Entnahmen/Einlagen; EÜR = SuSa (**Akzeptanz 6**) (`tests/test_abschluss_euer.py`).
- [x] **Vortrag und Sperre** (`abschluss/vortrag.py`): Eröffnungssalden, Schlusssalden, EB = Schluss (**Akzeptanz 7**), Sperre gegen Anlegen/Ändern/Löschen, Fehler-Befund verhindert Vortrag, Wiederöffnen mit Protokoll, erneuter Vortrag bucht nur Differenzen, Protokoll-Hash-Kette, Kassenbuch/AfA-Lauf/Abgang prüfen die Sperre vorher, Sperre auch in CLI-Befehlen ohne `init_db` (`tests/test_abschluss_vortrag.py`).
- [ ] **Durchlauf:** synthetisches Geschäftsjahr — Eröffnung, Bank, Kasse, Belege, Anlage, AfA, Abgrenzung, Prüfung, SuSa, EÜR, Vortrag, Eröffnungssalden = Schlusssalden (`tests/test_abschluss_durchlauf.py`).
- [ ] **CLI:** `abschluss eroeffnung|buchen|abgrenzungen|abgrenzen|bestaetigen|ablehnen|euer [--csv]|vortrag|oeffnen` (`tests/test_cli_abschluss.py`).
- [ ] **Abschluss:** `pytest`, `ruff check`, `ruff format --check`, `mypy` grün; Checkboxen abgehakt; Doku-Bausteine vollständig.

---

## Grenzen

- **Bilanz und GuV nach HGB-Gliederung, E-Bilanz, Übermittlung (EÜR-Datensatz/E-Bilanz über
  ELSTER), Rückstellungen** (Spec 4.3, 4.6 zweiter Teil, 4.7) sind **nicht** umgesetzt. Die
  Übermittlungsschicht aus Baustein 9 existiert noch nicht; eine EÜR wird berechnet und angezeigt,
  aber nicht übermittelt. `abschluss bilanz` und `abschluss uebermitteln` aus Spec 4.9 gibt es nicht.
- Die **EÜR endet bei „Summe Betriebseinnahmen − Summe Betriebsausgaben“** (Zeilen 76/77 bzw.
  77/78). Hinzurechnungen und Kürzungen der Zeilen ab 78 (steuerfreie Einnahmen, § 3c, IAB § 7g,
  § 4 Abs. 4a, nicht abziehbare Beträge wie Gewerbesteuer, 30 % Bewirtung) werden nicht berechnet;
  nicht abziehbare Aufwendungen stehen in der Zeile, auf die ihr Konto zeigt. Kleinunternehmer
  (Zeile 12), Land- und Forstwirte, Anlage AVEÜR als Formular und die EÜR-Zuordnung für jedes
  einzelne SKR-Konto (es gibt Bereichsregeln, keine DATEV-Zuordnungstabelle) fehlen.
- **EÜR mit offenen Posten:** Bucht man Rechnungen über Personenkonten (Baustein 4), stehen offene
  Rechnungen am Stichtag schon in der EÜR. accounti erkennt das (Warnung „offene Personenkonten“),
  korrigiert es aber nicht (DATEV-Verfahren „EÜR mit OPOS“ fehlt).
- **10-Tage-Regel** (§ 11 Abs. 1 Satz 2, Abs. 2 Satz 2 EStG) und Verteilung von Vorauszahlungen
  über fünf Jahre (§ 11 Abs. 2 Satz 3) werden für die EÜR nicht automatisch angewendet.
- **Abgrenzung** erkennt den Leistungszeitraum nur aus Text (Positionen, Belegnummer,
  Verwendungszweck, Buchungstext); der Rechnungszeitraum einer E-Rechnung (BT-73/74) wird nicht aus
  dem Archiv gelesen, weil der Beleg nur BT-74 trägt. Ohne erkennbaren Zeitraum gibt es keinen
  Vorschlag — dann bleibt `abschluss abgrenzen <BUCHUNG> --von --bis`.
- **Degressive AfA vor 2020** (z. B. 2009/2010) und Sonderabschreibungen (§ 7g, § 7b), Gebäude-AfA
  nach festen Prozentsätzen (§ 7 Abs. 4/5), Teilwertabschreibungen, außerplanmäßige AfA,
  Investitionsabzugsbetrag, nachträgliche AK, Einlagen zum Teilwert und Rumpfwirtschaftsjahre /
  abweichende Wirtschaftsjahre (alles rechnet im Kalenderjahr) sind nicht umgesetzt; ältere
  Fenster lassen sich über `anlagen.rechtsstand` nachtragen. Die Verzeichnisgrenze vor 2008 ist
  nicht hinterlegt.
- **Entnahme** eines Anlageguts wird wie ein Verkauf gerechnet; die umsatzsteuerliche
  Bemessungsgrundlage (§ 10 Abs. 4 UStG) prüft accounti nicht.
- **GWG und Sammelposten** bleiben mit RBW 0 im Anlagenspiegel (kein fiktiver Abgang). Ob ein
  Wirtschaftsgut „selbständig nutzbar“ ist, entscheidet der Mensch.
- **Kontoauszugssalden** werden erfasst (`abschluss saldo`); den Saldo, den ein Provider im
  `Abruf` meldet, übernimmt der Bankabruf noch nicht (der Datei-Provider liefert keinen).
- **Steueraufteilung in der SuSa** kennt die BU-Schlüssel 2, 3, 8, 9. Andere Schlüssel (ig. Erwerb,
  § 13b) bucht accounti bisher ohne Steuerbetrag; ein Steuerbetrag bei einem anderen Schlüssel
  bliebe unberücksichtigt.
- **Mehrere Kapital-/Privatkonten** (Gesellschafter einer Personengesellschaft) werden nicht
  getrennt vorgetragen: Ergebnis und alle Privatkonten gehen auf ein `ergebnis_konto`.
- **Jahressperre:** Das ORM-Ereignis greift für jeden Code, der `accounti.db.tabellen_abschluss`
  geladen hat (`init_db`/`registriere_tabellen` tun das; die CLI lädt es beim Start über
  `befehle/abschluss.py`, also auch für `bestaetige`, `korrigiere`, `classify`). Rohes SQL und
  Massen-`insert()`/`update()` an der ORM-Einheit vorbei sperrt es nicht (kein Datenbanktrigger). Ein `classify`-Lauf, der einen Umsatz in ein gesperrtes Jahr
  buchen will, bricht mit `JahrGesperrtError` ab.
- **Bestehende Kontenrahmendatei:** `config/skr03.yaml` (Auszug, von keinem Code gelesen) nennt
  4800 „Abschreibungen auf Sachanlagen“ und 0650 „Büromaschinen, EDV-Anlagen“; im DATEV SKR03 2026
  ist 4800 „Reparaturen und Instandhaltungen“ und 0650 ein Verbindlichkeiten-Davon-Konto. Auch das
  BWA-Schema rechnet 4800–4899 zu Abschreibungen. Baustein 12 nutzt die DATEV-Nummern; die Datei
  und das BWA-Schema bleiben unverändert (fremde Module).
- **Perioden geschlossen / Voranmeldungen abgegeben** (Spec 4.5) sind nicht prüfbar, solange es
  Baustein 7 und 9 nicht gibt. Die Summe der Personenkonten wird nicht gegen die OPOS-Liste
  abgestimmt.
- **Postgres:** Getestet ist unter SQLite; die Tabellen sind portabel, die Sperre ist ORM-seitig.

## Doku-Bausteine

### README — Feature-Tabelle (Abschnitt Steuern & Abschluss), zwei Zeilen ersetzen

```markdown
| ✅ | **Anlagenbuchhaltung** | Anlagegüter mit AfA linear (monatsgenau), degressiv (2020–2022, 2024, 07/2025–2027 mit Wechsel zur linearen AfA), GWG, Sammelposten, digitale Wirtschaftsgüter, E-Fahrzeuge — Grenzbeträge mit Gültigkeitszeitraum, AfA-Tabelle, AfA-Lauf je Monat oder Jahr, Abgang mit Ergebnis, Anlagenspiegel |
| 🟨 | **Jahresabschluss** | Kassenbuch ohne negativen Bestand, Bank-Saldenabstimmung als Abschlusssperre, Abschlussprüfungen, Summen- und Saldenliste, ARAP/PRAP-Vorschläge mit Auflösung, Einnahmenüberschussrechnung nach Anlage EÜR 2025/2026, Saldovortrag mit Jahressperre; Bilanz/GuV, Rückstellungen und Übermittlung folgen |
```

### README — Nutzungsblock (nach „USt-IdNr.-Prüfung“)

````markdown
### Anlagen und Jahresabschluss

```bash
# Anlagegut aus einem Beleg anlegen — Nutzungsdauer aus der AfA-Tabelle, immer änderbar
accounti anlagen tabelle                       # hinterlegte Nutzungsdauern mit Fundstelle
accounti anlagen anlegen --beleg RE-4711 --typ notebook
accounti anlagen anlegen --bezeichnung "Transporter" --datum 2026-09-15 \
  --kosten 36000 --typ lkw --art degressiv     # 3-fach, höchstens 30 % (07/2025–2027)
accounti anlagen plan 1                        # AfA-Plan bis zum Ende
accounti anlagen afa --jahr 2026 --bis-monat 9 # monatlich oder am Jahresende — idempotent
accounti anlagen freigeben --jahr 2026         # AfA-Vorschläge freigeben
accounti anlagen abgang 1 --datum 2026-11-30 --erloes 500 --gegenkonto 1200
accounti anlagen spiegel --jahr 2026 --csv anlagenspiegel.csv

# Kassenbuch — ein Eintrag, der den Bestand negativ machen würde, wird abgelehnt
accounti kasse anfangsbestand --betrag 300 --datum 2026-01-01
accounti kasse buchen --betrag -24.90 --text "Porto" --konto 4910
accounti kasse liste --jahr 2026               # laufende Nummer, Tagessaldo, Bestand
accounti kasse bestand --gezaehlt 275.10       # Kassensturz

# Jahresabschluss
accounti abschluss eroeffnung --jahr 2026 --konto 1200 --saldo 5000   # nur im ersten Jahr
accounti abschluss saldo --konto DE12… --stichtag 2026-12-31 --saldo 12345,67
accounti abschluss buchen --jahr 2026          # AfA + Abgrenzungsvorschläge
accounti abschluss abgrenzungen --jahr 2026    # bestaetigen <ID> | ablehnen <ID>
accounti abschluss pruefen --jahr 2026         # Fehler blockieren den Vortrag
accounti abschluss susa --jahr 2026
accounti abschluss euer --jahr 2026            # Anlage EÜR nach Zeilen und Kennzahlen
accounti abschluss vortrag --jahr 2026 --von "E. Muster"   # EB 01.01.2027, 2026 gesperrt
accounti abschluss oeffnen --jahr 2026 --grund "Nachbuchung Beleg 4711" --von "E. Muster"
```

Grenzbeträge (GWG, Sammelposten, degressive Fenster) gelten **ab dem Anschaffungstag** — ein Zugang
aus 2015 rechnet mit 410 €, einer aus 2026 mit 800 €. Abschlussbuchungen sind immer Vorschläge zur
Freigabe; gezählt wird in Salden und Auswertungen nur, was freigegeben ist.
````

### CHANGELOG

**Hinzugefügt**

```markdown
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
  Summen- und Saldenliste, ARAP/PRAP-Vorschläge mit Auflösung im Folgejahr,
  Einnahmenüberschussrechnung nach Anlage EÜR 2025 und 2026, Eröffnungssalden, Saldovortrag mit
  Jahressperre und Protokoll (`accounti abschluss …`). Neue, optionale Abschnitte `anlagen`,
  `abschluss`, `kasse`
```

**Geändert**

```markdown
- Buchungen in einem abgeschlossenen Jahr lassen sich nicht mehr anlegen, ändern oder löschen
  (`JahrGesperrtError`); `accounti abschluss oeffnen` hebt die Sperre mit Begründung und Protokoll
  auf
```

**Behoben**

```markdown
- (keine)
```

### docs/bauplan.md — Absatz nach dem Absatz zu Baustein 11, Status in der Bausteinkarte: 🟨 teilweise

```markdown
**Baustein 12 ist teilweise fertig,** weil die Anlagenbuchhaltung (AfA linear, degressiv, GWG,
Sammelposten, digitale Wirtschaftsgüter, E-Fahrzeuge, Abgang, Anlagenspiegel — Grenzbeträge mit
Gültigkeitszeitraum), das Kassenbuch, die Abschlussprüfungen mit Bank-Saldenabstimmung, Summen- und
Saldenliste, Abgrenzungsvorschläge, die Einnahmenüberschussrechnung und der Saldovortrag mit
Jahressperre stehen ([Plan](plans/2026-10-25-anlagen-jahresabschluss.md)) — was fehlt, sind Bilanz
und GuV nach HGB, Rückstellungen und die elektronische Übermittlung (braucht die Schicht aus
Baustein 9).
```

### docs/architektur.md — Abschnitt `anlagen/` und `abschluss/` ersetzen

```markdown
### `anlagen/` und `abschluss/` *(teilweise — [Baustein 12](specs/2026-08-10-anlagen-jahresabschluss.md))*

`anlagen/` führt Anlagegüter (`Anlagegut` in `models/anlagen.py`, Tabellen `anlagegueter`,
`afa_vorgaenge`) und schreibt die AfA fort.

- `rechtsstand.py` + `rechtsstand.yaml` — Grenzbeträge mit Gültigkeitszeitraum und Quelle: GWG,
  Verzeichnis, Sammelposten (2008/2009 Pflicht), degressive Fenster (Faktor, Höchstsatz),
  E-Fahrzeug-Staffel, digitale Wirtschaftsgüter, RAP-Verzicht, AfA-Tabelle. Maßgeblich ist der
  Anschaffungstag. Eigene Datei per `anlagen.rechtsstand`. *(vorhanden)*
- `afa.py` — AfA-Plan, rein: linear monatsgenau über die Kumulierte (keine Rundungsdrift),
  degressiv vom Restbuchwert mit Wechsel zur linearen AfA, GWG, Sammelposten (1/5 der Summe zum
  Jahresende), digital, E-Fahrzeug; Prüfung der Wahlrechte (einheitlicher Sammelposten). *(vorhanden)*
- `lauf.py` — AfA-Lauf: je Anlagegut Soll bis Monat minus schon gebucht, eine Buchung je
  AfA-/Anlagekonto, Begründung im Vorgang, Status „zur Prüfung“. *(vorhanden)*
- `abgang.py` — AfA bis Abgangsmonat, Restbuchwert auf 2310/2315, Erlös auf 8801/8820 mit USt aus
  `steuer/`. `spiegel.py` — Anlagenspiegel aus dem Plan. *(vorhanden)*

`abschluss/` arbeitet auf freigegebenen Buchungen.

- `kontenrahmen.py` + `kontenrahmen_skr03.yaml`/`…_skr04.yaml` — Kontoarten, Geld- und
  Steuerkonten, EÜR-Kennzahl je Kontenbereich. *(vorhanden)*
- `salden.py` — Kontobewegungen mit Steueraufteilung (Nettoseite, Steuerkonto, Bruttoseite),
  EB-Werte, Summen- und Saldenliste. *(vorhanden)*
- `kassenbuch.py` — Kassenbuch (Tabelle `kassenbuch`, nur anfügen): laufende Nummer, Bestand nie
  negativ, auch nicht rückwirkend; jeder Vorgang wird Transaktion des Kassenkontos. *(vorhanden)*
- `pruefungen.py` — benannte Abschlussprüfungen mit Befunden (Fehler/Warnung/Hinweis): u. a.
  Bank-Saldenabstimmung gegen `kontoauszugssalden`, Kassenbuch, AfA, offene Vorschläge. *(vorhanden)*
- `abgrenzung.py` — ARAP/PRAP-Vorschläge aus dem Leistungszeitraum, Auflösung im Folgejahr gleich
  mit (Tabelle `abgrenzungen`). *(vorhanden)*
- `euer.py` + `euer_vordrucke.yaml` — EÜR nach Kennzahlen, Zeilen je Vordruckjahr. *(vorhanden)*
- `vortrag.py` — Eröffnungssalden, Saldovortrag (EB gegen 9000/9008/9009), Jahressperre
  (`abschluesse`, ORM-Ereignis auf `buchungssaetze`), Protokoll `abschlussprotokoll`. *(vorhanden)*
- Bilanz/GuV, Rückstellungen und Übermittlung *(geplant)*.
```

### config/accounti.example.yaml — neue Abschnitte (nach `ustid_pruefung`)

```yaml
# Anlagenbuchhaltung (optional — ohne diesen Abschnitt gelten die Standards des Kontenrahmens
# aus buchhaltung.kontenrahmen; hier SKR03)
anlagen:
  # rechtsstand: config/rechtsstand.yaml   # eigene Grenzbeträge/AfA-Tabelle (ergänzt den Stand)
  konten:
    afa: "4830"                  # Abschreibungen auf Sachanlagen
    afa_kfz: "4832"
    afa_immateriell: "4822"
    gwg_afa: "4855"              # Sofortabschreibung GWG
    sammelposten_afa: "4862"
    abgang_buchverlust: "2310"   # Restbuchwert
    abgang_buchgewinn: "2315"
    erloes_buchverlust: "8801"   # 19 % USt
    erloes_buchgewinn: "8820"
    erloes_buchverlust_ohne_ust: "8800"
    erloes_buchgewinn_ohne_ust: "8829"
  kfz_konten: ["0320", "0350"]
  anlagekonten: [["0010", "0499"]]   # Buchungen hierauf ohne Anlagegut → anlagen vorschlaege

# Jahresabschluss (optional)
abschluss:
  gewinnermittlung: euer         # euer oder bilanz (nur bei bilanz: ARAP/PRAP)
  ergebnis_konto: "0880"         # Kapitalkonto für Ergebnis und Privatkonten (SKR04: 2010)
  rap_verzicht_bis_gwg: false    # § 5 Abs. 5 Satz 2 EStG, einheitlich für alle
  verrechnungskonten: ["1360", "1590"]   # sollen zum Stichtag ausgeglichen sein
  # kontenzuordnung: config/kontenzuordnung.yaml   # eigene Kontoarten/EÜR-Zuordnung

# Kassenbuch (optional)
kasse:
  konto: "1000"                  # SKR04: 1600
```
