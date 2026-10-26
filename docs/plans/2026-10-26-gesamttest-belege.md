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
„erfasst“ und berichtigt dabei Belegart, Steuerfall, Belegnummer (`--belegnummer`, nie
eine, die derselbe Lieferant schon hat) und das Vorzeichen (`--vorzeichen umkehren`);
andere Beträge und den Lieferanten ändert es nicht (siehe Grenzen). Ein Steuerfall ohne
Steuerausweis (`--steuer 13b|ig-erwerb|steuerfrei`) passt nicht zu Netto ≠ Brutto und
wird dann abgelehnt. Verbuchte Belege nie — dort gilt Storno statt Änderung (GoBD
Rz. 58, 107). Recht „buchen“; die Ausgabe nennt den bisherigen Prüfgrund. `--grund` ist
Pflicht, wenn der Beleg wegen Dublettenverdacht, Rechenprobe oder gedrehtem Vorzeichen in
der Prüfung lag, bei `--vorzeichen` und wenn eine gelesene Belegnummer ersetzt wird —
ein fehlendes Feld nachzutragen braucht keinen. Journal `beleg_freigegeben` mit Person,
Grund und Vorher/Nachher, und zwar nur aus diesem Befehl (`pruefung.ereignisse.
belegfreigabe`); liest `belege erkennen` einen Beleg aus der Prüfung neu und ist er dann
vollständig, steht das als `beleg_geaendert` (vorher als Freigabe ohne Menschen).
`belege erkennen --id` liest einen erfassten, noch nicht verbuchten Beleg neu (z. B. mit
der eigenen Firma aus `mandant`).

**Vorzeichen bleiben (B12).** Eine Gutschrift/Rechnungskorrektur des Lieferanten mindert
Aufwand und Vorsteuer (§ 17 Abs. 1 UStG). Gedruckte Minusbeträge werden übernommen; ein
Korrekturbeleg mit positiven Beträgen wird negiert und geht **immer zur Prüfung** — das
Minus ist eine Deutung des Titels, nicht gedruckt (Nachprüfung M1). Als Titel zählt nur
eine Zeile aus dem Schlüsselwort (Rechnungskorrektur, Korrekturrechnung, Stornorechnung,
Rechnungsstorno, Gutschrift, Credit Note), höchstens mit Nummer, Datum oder Bezug („zur
Rechnung Nr. …“) bzw. einem zweiten Schlüsselwort („Gutschrift (Rechnungskorrektur)“), und
nur, wenn vorher kein Titel „Rechnung“/„Invoice“ steht — ein Satz wie
„Rechnungskorrektur nur schriftlich innerhalb von 8 Tagen“ machte vorher aus einer
Rechnung eine automatisch gebuchte Minderung. „Gutschrift“ allein ist mehrdeutig (§ 14
Abs. 2 S. 2 UStG: Abrechnung durch den Leistungsempfänger wäre ein Erlös) — der Prüfgrund
sagt das zusätzlich. Gutschrift-Nummern („Gutschrift-Nr.“, „Gutschriftsnummer“, „Credit
note no.“) sind Belegnummern.

**Ohne Schlüssel brutto (B05).** Eine Position ohne Steuersatz bucht die Steuer in den
Betrag (zur Prüfung), statt sie zu verwerfen — sonst stünde netto auf dem Personenkonto
und brutto im offenen Posten. Ein Helfer für beide Wege (`buchung/steuergruppe.py`:
Rechnung auf das Personenkonto und Bankumsatz mit Beleg). ZUGFeRD MINIMUM/BASIC WL ist
keine Rechnung nach § 14 Abs. 4 UStG und seit 2025 keine E-Rechnung (BMF 15.10.2024): Der
Beleg geht zur Prüfung, Steuersätze kommen aus der PDF-Ansicht, wenn deren Steuerzeilen
zu den XML-Summen passen. Ein Hinweistext („§ 19“, „Reverse Charge“ …) ersetzt den
Steuerausweis nur bei Netto = Brutto — sonst weist die Rechnung Steuer aus, deren Zeile
nicht gelesen wurde (Prüfung „fehlt: Steuerausweis“); ohne Steuerzeile steht die Position
„Gesamtbetrag“ brutto (Nachprüfung N1). Prüfregel `personenkonto_op` und Abschlussprüfung
`personenkonten`: Saldo jedes Personenkontos = Summe seiner offenen Posten (GoBD Rz. 58 ff.,
§ 239 Abs. 2 HGB).

**Vorsteuer bei Eingang im Folgejahr (B16).** Bei Bilanzierung gehören Aufwand und
Verbindlichkeit ins alte Jahr (§ 252 Abs. 1 Nr. 5 HGB), die Vorsteuer in den Zeitraum, in
dem Leistung und Rechnung beide vorliegen (§ 15 Abs. 1 S. 1 Nr. 1 UStG, Abschn. 15.2
Abs. 2 S. 7 UStAE; kein Wahlrecht). accounti bucht die Vorsteuer deshalb auf „Vorsteuer
im Folgejahr abziehbar“ (SKR03 1548, SKR04 1434) und zum ersten offenen Tag des
Eingangsmonats auf das Vorsteuerkonto um; die Kennziffernermittlung zählt die Umbuchung
als Kz 66. Bei Einnahmenüberschussrechnung gibt es kein 1548: gebucht wird zum
Belegdatum, wenn dessen Monat offen ist (mit § 15-Hinweis und UStVA-Befund
`beleg_nach_zeitraum`); ist er festgeschrieben, mit `--buchungsdatum eingang|offen|…` in
einen offenen Zeitraum, auch über den Jahreswechsel (§ 11 EStG) — siehe Grenzen.

**Gutschrift: Minderung im Zeitraum der Änderung (Nachprüfung M2).** § 15 Abs. 1 S. 1
Nr. 1 UStG regelt nur den Abzug. Eine Lieferantengutschrift berichtigt den
Vorsteuerabzug für den Zeitraum, in dem sich die Bemessungsgrundlage geändert hat (§ 17
Abs. 1 S. 2, 8 UStG), unabhängig vom Zugang des Belegs (Abschn. 17.1 UStAE). accounti
nimmt dafür das Belegdatum der Gutschrift: kein 1548-Weg (vorher ging die Minderung bei
Eingang im Folgejahr erst in den Eingangsmonat — die Vorsteuer des alten Jahres war zu
hoch), kein § 15-Hinweis und kein Befund `beleg_nach_zeitraum` (nur für Kz 66 > 0),
stattdessen ein Hinweis auf § 17 Abs. 1 S. 8, wenn die Gutschrift erst in einem späteren
Monat erfasst wurde. Ist der Monat des Belegdatums festgeschrieben, nennt die Meldung den
Weg (Monat mit Grund öffnen, zum Belegdatum buchen); mit `--buchungsdatum` später gebucht,
geht die Minderung zur Prüfung, und der Hinweis nennt die zu berichtigende Voranmeldung.

**Kontakte, die dem Beleg widersprechen (B14, Ausgang B1).** Eine andere USt-IdNr. ist ein
anderes Unternehmen, auch bei gleicher IBAN oder gleichem normalisiertem Namen; ein
anderes Land schließt einen Namenstreffer aus. Kunden aus eigenen Rechnungen werden mit
einem gleichnamigen Debitor nur bei gleicher PLZ oder E-Mail zusammengeführt (Mahnung an
Dritte: Art. 5 Abs. 1 lit. f DSGVO, keine Mahnung i. S. § 286 Abs. 1 BGB). Die ZM meldet
je USt-IdNr. der Rechnung (§ 18a Abs. 7 Nr. 1 UStG), die OSS-Kontierung nimmt das Land der
Rechnung (§ 18j UStG). Das Land eines Kreditors kommt aus dem Präfix der USt-IdNr., sonst
der IBAN (vorher immer „DE“, damit nie Kz 46/47).

**Skonto (B09, B02).** „Ohne Abzug“, „rein netto“, „netto Kasse“, „kein Skonto“ heißen
Skonto 0 % am Beleg; 0 % schlägt das Kontakt-Skonto. Zahlungsbedingungen werden je
Teilsatz gelesen („30 Tage ohne Abzug oder 10 Tage mit 2 % Skonto“: Skontofrist 10,
Ziel 30 — vorher Skontofrist 30 und kein Ziel; Nachprüfung N5). Eine Sammelzahlung darf Skonto auf
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
- **Später Eingang im selben Jahr bzw. bei EÜR** (Nachprüfung N4): Ist der Monat des
  Belegdatums offen, bucht accounti zum Belegdatum und verschiebt die Vorsteuer nicht von
  sich aus — „Eingang“ ist die Erfassung, kein Zugangsnachweis (bei einem Stapelimport
  wäre jede Verschiebung falsch); `--buchungsdatum` wirkt nur für festgeschriebene Monate.
  Hinweis beim Verbuchen und UStVA-Befund `beleg_nach_zeitraum` sagen das; eine
  Umbuchung im Jahr (wie 1548) macht accounti nicht.
- **Zeitpunkt der Änderung bei Gutschriften** ist das Belegdatum der Gutschrift; ein
  davon abweichender Tag der Rücknahme bzw. Vereinbarung steht nicht im Beleg.
- **Korrekturtitel per Muster:** Ein Korrekturbeleg mit positiven Beträgen und anderem
  Titel (etwa „Ihre Gutschrift“, „Credit memo“, Titel erst nach „Rechnung“) bleibt
  positiv und bucht wie eine Rechnung; gedruckte Minusbeträge sind davon unabhängig.
- **Freigabe berichtigt keine Beträge außer dem Vorzeichen** und nicht den Lieferanten.
  Ein erneuter Import endet als Dublette (Datei-Hash); falsch gelesene Beträge: ohne
  Änderung freigeben, verbuchen (zur Prüfung) und die Buchung mit `korrigiere`
  berichtigen — der offene Posten bleibt beim gelesenen Betrag, `personenkonto_op` meldet
  die Differenz. Eine Betragskorrektur am Beleg mit neuer Rechenprobe und neuen Positionen
  wäre ein eigener Baustein.
- **Journal vor dieser Korrektur:** ältere Einträge `beleg_freigegeben` aus `belege
  erkennen` bleiben, wie sie sind (das Journal ist unveränderbar).
