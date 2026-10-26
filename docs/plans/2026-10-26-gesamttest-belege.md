# Gesamttest Eingang/Kreditoren — Reparatur (Paket C)

Befunde aus dem Gesamttest (main 48b2d9e, Bericht und Gegenprüfung „Eingang/Kreditoren“
B02–B06, B09, B12, B14, B16 und die Beobachtungen „Land des Kreditors“, „kontakte
bearbeiten“, „SuSa ohne 1577/1787“; aus „Steuer“ B4, aus „Ausgang“ B1). Je Befund ein
Test, der ohne die Korrektur rot war.

## Entscheidungen

**Hinweis statt Steuerausweis ist eine Steuerangabe (B06).** Bei § 13b verbietet § 14a
Abs. 5 S. 2 UStG den Steuerausweis, Pflichtangabe ist der Hinweis
„Steuerschuldnerschaft des Leistungsempfängers“; ebenso tragen ig. Lieferung (§ 14a
Abs. 3), Kleinunternehmer (§ 19) und steuerfreie Leistungen (§ 4, § 14 Abs. 4 Nr. 8 UStG)
einen Hinweis. accounti liest den Hinweis als Steuerkennzeichen nach UNTDID 5305 (AE, K,
E) — dieselben Codes wie die Kategorien einer E-Rechnung — und speichert es am Beleg
(`belege.steuerkennzeichen`, Migration `46371a6681c2`). Eine 0-%-Steuerzeile zählt als
Steuerzeile. Beim Verbuchen wird aus AE Schlüssel 94 und aus K (ig. Lieferung an uns =
ig. Erwerb, § 1a UStG) Schlüssel 19 — **immer zur Prüfung**: Satz (7 % → 91/18) und
Art der Leistung (Kz 46/47 nur für sonstige Leistungen nach § 3a Abs. 2 eines
EU-Unternehmers, sonst 84/85) kann accounti nicht sicher lesen. Die Steuer berechnet
accounti aus dem Netto (§ 13b Abs. 5, § 13a Abs. 1 Nr. 2 UStG); sie steht nie im
Zahlbetrag. E (steuerfrei, § 19) bleibt ohne Schlüssel.

**Weg aus „zur Prüfung“ (B06, B04).** `belege freigeben` setzt einen geprüften Beleg auf
„erfasst“ und berichtigt dabei Belegart und Steuerfall; Beträge und Lieferant ändert es
nicht (dafür neu erfassen bzw. die Rechnung berichtigen lassen). Verbuchte Belege nie —
dort gilt Storno statt Änderung (GoBD Rz. 58, 107). Recht „buchen“, Journal
`beleg_freigegeben` mit Person und Grund. `belege erkennen --id` liest einen erfassten,
noch nicht verbuchten Beleg neu (z. B. mit der eigenen Firma aus `mandant`).

**Vorzeichen bleiben (B12).** Eine Gutschrift/Rechnungskorrektur des Lieferanten mindert
Aufwand und Vorsteuer (§ 17 Abs. 1 UStG). Gedruckte Minusbeträge werden übernommen; ein
Korrekturbeleg mit positiven Beträgen wird negiert. „Gutschrift“ allein ist mehrdeutig
(§ 14 Abs. 2 S. 2 UStG: Abrechnung durch den Leistungsempfänger wäre ein Erlös) — negiert
und zur Prüfung.

**Ohne Schlüssel brutto (B05).** Eine Position ohne Steuersatz bucht die Steuer in den
Betrag (zur Prüfung), statt sie zu verwerfen — sonst stünde netto auf dem Personenkonto
und brutto im offenen Posten. Ein Helfer für beide Wege (`buchung/steuergruppe.py`:
Rechnung auf das Personenkonto und Bankumsatz mit Beleg). ZUGFeRD MINIMUM/BASIC WL ist
keine Rechnung nach § 14 Abs. 4 UStG und seit 2025 keine E-Rechnung (BMF 15.10.2024): Der
Beleg geht zur Prüfung, Steuersätze kommen aus der PDF-Ansicht, wenn deren Steuerzeilen
zu den XML-Summen passen. Prüfregel `personenkonto_op` und Abschlussprüfung
`personenkonten`: Saldo jedes Personenkontos = Summe seiner offenen Posten (GoBD Rz. 58 ff.,
§ 239 Abs. 2 HGB).

**Vorsteuer bei Eingang im Folgejahr (B16).** Bei Bilanzierung gehören Aufwand und
Verbindlichkeit ins alte Jahr (§ 252 Abs. 1 Nr. 5 HGB), die Vorsteuer in den Zeitraum, in
dem Leistung und Rechnung beide vorliegen (§ 15 Abs. 1 S. 1 Nr. 1 UStG, Abschn. 15.2
Abs. 2 S. 7 UStAE; kein Wahlrecht). accounti bucht die Vorsteuer deshalb auf „Vorsteuer
im Folgejahr abziehbar“ (SKR03 1548, SKR04 1434) und zum ersten offenen Tag des
Eingangsmonats auf das Vorsteuerkonto um; die Kennziffernermittlung zählt die Umbuchung
als Kz 66. Bei Einnahmenüberschussrechnung bleibt es beim bisherigen Weg (Buchung im
Eingangszeitraum mit Hinweis).

**Kontakte, die dem Beleg widersprechen (B14, Ausgang B1).** Eine andere USt-IdNr. ist ein
anderes Unternehmen, auch bei gleicher IBAN oder gleichem normalisiertem Namen; ein
anderes Land schließt einen Namenstreffer aus. Kunden aus eigenen Rechnungen werden mit
einem gleichnamigen Debitor nur bei gleicher PLZ oder E-Mail zusammengeführt (Mahnung an
Dritte: Art. 5 Abs. 1 lit. f DSGVO, keine Mahnung i. S. § 286 Abs. 1 BGB). Die ZM meldet
je USt-IdNr. der Rechnung (§ 18a Abs. 7 Nr. 1 UStG), die OSS-Kontierung nimmt das Land der
Rechnung (§ 18j UStG). Das Land eines Kreditors kommt aus dem Präfix der USt-IdNr., sonst
der IBAN (vorher immer „DE“, damit nie Kz 46/47).

**Skonto (B09, B02).** „Ohne Abzug“, „rein netto“, „netto Kasse“, „kein Skonto“ heißen
Skonto 0 % am Beleg; 0 % schlägt das Kontakt-Skonto. Eine Sammelzahlung darf Skonto auf
einer Teilmenge ihrer Posten ziehen; `opos bestaetigen --skonto` erkennt Skonto von Hand
an — immer mit anteiliger Steuerkorrektur (§ 17 Abs. 1 UStG).

**Dateiprüfung (B03).** Der Ordner-Kanal prüft wie E-Mail, Webhook und Connector Typ (am
Inhalt) und Größe; der Handimport `belege import` bleibt ungeprüft (die Datei wählt der
Anwender, Text-Belege für Beispiele). Die Verfahrensdokumentation beschreibt den Istzustand
(GoBD Rz. 151 ff.).

## Grenzen

- **„Eingang“ ist die Erfassung in accounti** (`eingegangen_am`, meist der Import), nicht
  der tatsächliche Zugang der Rechnung. Lag die Rechnung schon im alten Jahr bzw. Zeitraum
  vor, sind 1548-Buchung und Befund `beleg_nach_zeitraum` falsch — Hinweis und Befund sagen
  das, die Buchungen korrigiert der Mensch. Die 1548-Buchung macht nur `opos verbuchen`
  (Rechnung auf das Personenkonto), nicht `classify` mit Beleg, und nur für Schlüssel 8/9.
- **§ 13b-Kennziffer nach dem Land des Kreditors:** Werklieferungen und andere Fälle des
  § 13b Abs. 2 eines EU-Unternehmers gehören nach Kz 84/85, accounti legt sie bei
  EU-Kreditor nach 46/47 — deshalb geht jeder § 13b-Vorschlag zur Prüfung. 7 % (91/18) nur
  von Hand (`korrigiere --steuer 91`).
- **Hinweistexte per Muster** (deutsch und die gängigen EU-Formulierungen); ein Hinweis bei
  einer besteuerten Rechnung erzeugt keine 0-%-Zeile, setzt aber das Kennzeichen — Schlüssel
  94/19 gibt es nur für 0-%-Positionen.
- **MINIMUM/BASIC WL:** nur die Textebene der PDF-Ansicht (kein OCR); passen ihre
  Steuerzeilen nicht zu den XML-Summen, bleibt die Position ohne Satz (brutto, zur Prüfung).
- **Land aus der IBAN** ist nur der Ersatz ohne USt-IdNr. — ein Konto bei einer
  ausländischen Bank sagt nichts über den Sitz; ein schon gepflegtes Land oder eine
  Anschrift überschreibt accounti nicht (`kontakte bearbeiten --land`).
- **Widerspruchserkennung** nur über USt-IdNr., Name, Land und (für Debitoren aus eigenen
  Rechnungen) PLZ/E-Mail; Kreditoren mit gleichem Namen ohne USt-IdNr. auf dem Beleg werden
  weiterhin zusammengeführt. Die ZM nimmt die USt-IdNr. nur aus in accounti ausgestellten
  Rechnungen (Tabelle `ausgangsrechnungen`), sonst aus dem Kontakt.
- **Sammelzahlungen:** höchstens 4 Posten aus den 12 ältesten (`MAX_SAMMEL`,
  `MAX_KANDIDATEN`); `--skonto` nur für Posten des Vorschlags.
- **Personenkonto-Abstimmung** ist eine Warnung und blockiert nichts; Eröffnungsbuchungen
  zählen nicht mit (der Saldovortrag wiederholt die Vorjahre).
- **Handimport ohne Dateiprüfung** (`belege import`), siehe oben.
