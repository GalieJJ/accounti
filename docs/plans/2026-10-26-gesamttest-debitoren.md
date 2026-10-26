# Gesamttest Ausgang/Debitoren — Reparatur (Paket D)

Befunde aus dem Gesamttest (main 48b2d9e, Bericht und Gegenprüfung „Ausgang/Debitoren“
B2–B16; B1 namensgleiche Kunden liegt in Paket C). Je Befund ein Test, der ohne die
Korrektur rot war.

## Entscheidungen

**Guthaben ist ein offener Posten (B3, B4, B6).** Eine Überzahlung lässt den Posten mit
negativem Rest offen (statt ihn zu schließen und den Überschuss nur auf dem Personenkonto
zu buchen) — Personenkonto und Postenliste stimmen überein (GoB, Kontokorrent). Ein
eigener Guthabenposten scheidet aus: Posten hängen eindeutig an einem Beleg
(`offene_posten.beleg_id` unique). Negative Posten (Gutschrift, Korrektur, Guthaben)
nehmen an der Zuordnung teil; gerechnet wird aus Sicht der Zahlung („Rest in
Zahlungsrichtung“), die Anteile stehen im Vorzeichen des Postens. Erstattungen treffen
negative Posten, eine Saldozahlung über Rechnung und Gutschrift wird saldiert
(Vorschlag, wie jede Zahlung über mehrere Posten).

**Verrechnung ohne Buchung.** Gutschrift und Rechnung desselben Kunden stehen auf
demselben Personenkonto; ein Buchungssatz „10000 an 10000“ wäre sinnlos (DATEV lehnt
Konto = Gegenkonto ab). `opos verrechnen` gleicht deshalb nur die Posten aus und hält den
Vorgang fest — Tabelle `verrechnungen` (nur anfügen) und Journal `posten_verrechnet`.
Rechtlich: Minderung (§ 441 BGB) kürzt die Forderung, Guthaben aus Überzahlung wird
aufgerechnet (§§ 387, 389 BGB). Eine Gutschrift mit Bezug (BT-25) wird beim Verbuchen mit
der noch offenen Rechnung verrechnet.

**Referenz an Wortgrenzen (B5).** Abweichend vom Vorschlag (Regex auf dem ganz
normalisierten Zweck) muss die Belegnummer aus ganzen Wortfolgen (Ziffern- bzw.
Buchstabenfolgen) bestehen — sonst gingen Treffer wie „Rechnung2026-0315“ oder
„RE2026-0042“ verloren. Das Datum in „EREF+20260315-0042“ bleibt so aber ein Treffer
für 2026-0315. Deshalb: Nennt der Zweck nur Posten eines anderen Kontakts als des
erkannten Zahlers, hat der Zahler Vorrang (höchstens 0,7 bzw. 0,6, nie automatisch).
Eine Nummer gilt als „nur Datum“, wenn jede getroffene Wortfolge zusammen ein Datum
JJJJMMTT ergibt und anders gegliedert ist als die Nummer — „20260315“, „2026-03-15“,
„2026/03/15“ für 2026-0315, nicht aber „RE 2026 0315“ (Nachprüfung M1: zuerst zählte nur
die zusammenhängende Ziffernfolge). Eine Nummer ohne Trennzeichen („20260315“ beim
Format `{jahr}{nummer:04d}`) ist als Datum gleich geschrieben und zählt immer als
mehrdeutig. Folge: ohne erkannten Zahler höchstens ein Vorschlag (der eindeutige Betrag
geht der Referenz vor); beim erkannten Zahler mit eigenem so genannten Posten keine
Referenz — Stufe B (eindeutiger Betrag) bucht automatisch, sonst der genannte Posten als
Vorschlag (höchstens 0,6). Ein nur als Datum genannter Posten *eines anderen Kontakts*
bleibt wie jede fremde Referenz ein Widerspruch (höchstens 0,7, nicht automatisch).
Gegenprüfung: Geprüft werden nur die Ziffernwörter — „RE 2026-03-15“ ist bei
RE-2026-0315 ein Datum (zuerst machte das Präfix die Folge zur Referenz); eine Nummer mit
Präfix und ohne Trennzeichen („RE20260315“) bleibt gleich geschrieben eine Referenz. Neben
einer echten Referenz zählt eine nur als Datum genannte Nummer gar nicht: „RE 2026-0001
vom 2026-03-15“ ist eine Referenz auf 2026-0001 (automatisch wie ohne Datum), eine
Gutschrift 2026-0315 wird dabei nicht saldiert, und ein echt genannter fremder Posten
bleibt ein Widerspruch, auch wenn ein eigener Posten als Datum dasteht.

**Guthaben nur derselben Richtung (Nachprüfung N1).** Als Guthaben zählt bei der
Zuordnung nur ein Posten der Zahlungsrichtung mit negativem eigenem Rest (beim Eingang
eine Gutschrift oder Überzahlung des Kunden). Die Verbindlichkeit desselben Kontakts
steht auf seinem Kreditorenkonto — sie gegen die Forderung zu rechnen wäre eine
Aufrechnung über zwei Personenkonten; die Handzuordnung lehnt sie ab, ebenso eine
Gutschrift eines anderen Kontakts. Gegenprüfung: Auch wenn der Kontakt der Gutschrift
selbst einen Posten in der Handzuordnung hat, tilgt die Gutschrift nur dessen Posten
(in der angegebenen Reihenfolge, höchstens bis zu ihrem Rest); was übrig bleibt, bleibt
Guthaben — es bezahlt nie die Rechnung eines anderen Kontakts (Gegenseitigkeit, §§ 387,
389 BGB).

**Saldozahlung (Nachprüfung N3).** Rechnung 595 € und Gutschrift 119 € mit einer Zahlung
über 476 € buchen weiter zwei Bankbuchungen (1200 an 10000 595 €, 10000 an 1200 119 €,
zusammen der Auszugsbetrag); die zweite heißt jetzt „Verrechnung …“ statt „Erstattung …“.
Eine Nettobuchung mit eigenem Verrechnungseintrag hätte Zuordnung, Storno und
Stichtagsliste um einen zweiten Weg erweitert — der Text war das Irreführende.

**Datum der Verrechnung (Nachprüfung N2).** Frühestens am Belegdatum beider Posten und am
Tag der Zahlung, aus der ein Guthaben stammt (Aufrechnungslage, § 387 BGB) — sonst passt
die Stichtagsliste nicht zum Personenkonto.

**Berichtigungshinweis (Nachprüfung N8).** Bucht `opos verbuchen` eine Ausgangsrechnung
in einen Zeitraum, dessen Voranmeldung schon echt übermittelt ist (Monat oder Quartal,
`elster.ustva.abgegeben`), nennt es die berichtigte Voranmeldung (§ 153 Abs. 1 AO); die
neue Anmeldung trägt dann Kz 10. Ein festgeschriebener Monat bricht wie bisher ab. Eine
Minderung (Gutschrift, Korrektur mit negativem Brutto) verkürzt keine Steuer — keine
Pflicht nach § 153 Abs. 1 AO; der Hinweis nennt die berichtigte Anmeldung als Möglichkeit
(Anmeldung unter Vorbehalt, § 168, § 164 Abs. 2 AO), sonst erfasst sie die
Jahreserklärung (Gegenprüfung).

**Gutschrift 381 / Rechnungskorrektur 384 mit BT-25/26 (B3).** Bezug auf die
ursprüngliche Rechnung für die Berichtigung beim Kunden (§ 17 Abs. 1 Satz 2 UStG) und zur
Abgrenzung von der umsatzsteuerlichen Gutschrift (Abschn. 14.3 Abs. 1 UStAE) — die
PDF-Ansicht heißt deshalb „Rechnungskorrektur (Gutschrift)“. Die Gutschrift weist die
Minderung positiv aus, die Korrektur die Differenz mit Vorzeichen; ein Einzelpreis ist
nie negativ (BR-27, das Minus steht in der Menge). Beide bestehen KoSIT und Mustang.

**Leistungsmonat ohne Steuerperioden-Feld (B2, B12).** Kleine Variante: Ausgangsrechnungen
werden zum umsatzsteuerlichen Zeitpunkt *gebucht* (`steuer/leistungszeitpunkt.py`) —
Leistungsdatum bei Leistung in einem früheren Monat (§ 13 Abs. 1 Nr. 1 Buchst. a UStG),
ig. Lieferung im Rechnungsmonat, spätestens am Ende des Folgemonats (§ 13 Abs. 1 Nr. 6,
§ 18b Satz 2, § 18a Abs. 8 UStG), Gutschrift/Korrektur zu ihrem Datum (§ 17 Abs. 1
Satz 7 UStG). Gründe gegen das Feld `steuerperiode`: (1) Voranmeldung, ZM, OSS-Meldung,
Saldenliste, Abschluss, Sperren und DATEV gehen alle vom Buchungsdatum aus und bleiben so
ohne Änderung stimmig — mit einem eigenen Feld liefen Hauptbuch und Voranmeldung
auseinander (USt-Konten-Abstimmung, Storno/Korrektur müssten das Feld mitführen,
DATEV 116); (2) fachlich ist die Buchung zur Leistung auch handelsrechtlich richtig
(Realisationsprinzip, § 252 Abs. 1 Nr. 4 HGB — gerade beim Jahreswechsel); (3) keine
Migration und keine Berührung der Bereiche anderer Pakete (Kennziffern, DATEV-Export).
Offener Posten, Fälligkeit und Mahnwesen bleiben beim Rechnungsdatum.

**Leistungsort B2C-Dienstleistung (B9).** § 3a Abs. 1 bzw. Abs. 3 Nr. 3 Buchst. c UStG —
deutsche Steuer; OSS nur für Fernverkäufe (§ 3c) und die neue Positionsart „elektronische
Leistung“ (§ 3a Abs. 5 UStG).

**B2C ohne XRechnung (B16).** Keine E-Rechnungspflicht gegenüber Privatkunden (§ 14
Abs. 2 Satz 2 Nr. 1 UStG): Fehlen E-Mail, PLZ oder Ort, entsteht eine Rechnung nach
EN 16931 (ZUGFeRD-Profil EN 16931). Über 250 € braucht jede Rechnung die vollständige
Anschrift — Straße oder Postfach (Abschn. 14.5 Abs. 2 UStAE), PLZ und Ort (§ 14 Abs. 4
Satz 1 Nr. 1 UStG; Nachprüfung N5: zuerst fehlte die Straße, und nur beim Privatkunden
wurde geprüft) —, bis 250 € genügt die Kleinbetragsrechnung (§ 33 UStDV). Geprüft wird
beim Ausstellen (Gegenprüfung: zuerst auch in `rechnung zeigen`, das bei schon ohne Straße
ausgestellten Rechnungen dann abbrach); die Anzeige nennt das Fehlende nur. Eine Korrektur
ohne `--name` übernimmt den Kunden der Rechnung, `--strasse`, `--plz`, `--ort`, `--email`,
`--ust-id`, `--leitweg-id` ergänzen ihn. Das
KoSIT-Prüftool hat nur XRechnung-Szenarien — die EN-16931-Rechnung prüft Mustang.

## Grenzen

- **Anzahlungs-/Vorausrechnungen:** Liegt die Leistung nach dem Rechnungsdatum, bucht
  accounti zum Rechnungsdatum und weist darauf hin; die Mindest-Ist-Versteuerung bei
  Anzahlungen (§ 13 Abs. 1 Nr. 1 Buchst. a Satz 4 UStG) bildet accounti nicht ab.
- **Katalogleistungen an Privatkunden im Drittland** (§ 3a Abs. 4 Satz 2 UStG, z.B.
  Überlassung von Urheberrechten, Beratung) erkennt accounti nicht — es setzt deutsche
  Steuer (zu viel, nicht zu wenig). Elektronische Leistungen dorthin (§ 3a Abs. 5 Satz 1
  UStG) und Dienstleistungen an Unternehmer im Drittland (§ 3a Abs. 2, Kategorie O)
  werden weiter abgelehnt.
- **Sonderorte des § 3a Abs. 3 und § 3b UStG** (Nachprüfung N4): Grundstücksleistungen
  (Nr. 1), kurzfristige Vermietung von Beförderungsmitteln (Nr. 2), Veranstaltungen (Nr. 3
  Buchst. a), Vermittlung an Privatkunden (Nr. 4) und Beförderungen erkennt accounti
  nicht; an Privatkunden gelten sie als im Inland ausgeführt. Für eine Galerie selten —
  eine eigene Positionsart wäre nötig, wie `--elektronisch`.
- **Nummernformat ohne Trennzeichen** (`{jahr}{nummer:04d}`): Nummern, die wie ein Datum
  aussehen, bucht die Zuordnung ohne erkannten Zahler nie automatisch — Format mit
  Trennzeichen (Standard `{jahr}-{nummer:04d}`) oder Präfix (`RE{jahr}…`) wählen. Bei
  beiden bucht nur die gleich gegliederte Schreibweise automatisch („2026-0315“ bzw.
  „RE20260315“); ein anders gegliedertes Datum („RE 2026-03-15“) bleibt ohne Zahler ein
  Vorschlag, auch mit Präfix.
- **Altrechnungen ohne Straße:** Rechnungen über 250 €, die vor dieser Version ohne
  Straße ausgestellt wurden, zeigt `rechnung zeigen` mit Hinweis; einen Berichtigungsbeleg
  nur für die Anschrift (§ 31 Abs. 5 UStDV, ohne Betragsänderung) bildet accounti nicht
  eigens ab — eine Korrektur mit Betrag kann die Straße mit `--strasse` ergänzen.
- **Korrektur nur zu Rechnungen aus accounti:** `--korrektur-zu` verlangt eine in accounti
  ausgestellte Rechnung (für BT-26 und den Kunden).
- **Verrechnung über zwei Personenkonten** (Forderung gegen Verbindlichkeit desselben
  Kontakts, Gutschrift eines anderen Kontakts) bucht accounti nicht — weder `opos
  verrechnen` noch Zuordnungsvorschlag oder Handzuordnung; eine solche Saldozahlung
  bleibt eine Teilzahlung auf die Forderung.
- **Verrechnung zurücknehmen:** Eine Verrechnung ist unveränderbar (nur anfügen) und
  lässt sich nicht aufheben — wie ein Zahlungsausgleich, dessen Storno den Posten
  ebenfalls nicht wieder öffnet; vor `opos verrechnen` die Nummern prüfen.
- **Stichtagsliste:** rekonstruiert den Rest aus gebuchten Zuordnungen und Verrechnungen;
  die Verrechnung der Zahllast mit Erstattungen (`elster/zahllast.py`) ist undatiert und
  gilt als vor jedem Stichtag geschehen.
- **Prüfregel Personenkonto = Summe offene Posten** ergänzt Paket C (Eingang B05).
- **Verzugshinweis:** Rechnungen, die vor dieser Version ausgestellt wurden, tragen den
  Hinweis nach § 286 Abs. 3 BGB nicht; `mahnwesen.hinweis_30_tage` gilt für sie trotzdem.
- **Berichtigungshinweis nur für Ausgangsrechnungen:** Eine Eingangsrechnung in einem
  schon gemeldeten Zeitraum erhöht nur die Vorsteuer — keine Berichtigungspflicht nach
  § 153 AO; den Zeitraum der Vorsteuer regeln `--buchungsdatum` und Paket C/E. Aus
  demselben Grund nennt der Hinweis bei einer Gutschrift die Berichtigung nur als
  Möglichkeit. Unterschieden wird am Vorzeichen des Bruttos: Eine Korrektur, die eine
  Steuerart erhöht und eine andere stärker mindert, gilt als Minderung.
- **Ohne Migration** (N7): Der neue Code setzt Migration `a14acef69fae` voraus; ohne sie
  enden Befehle an den neuen Spalten mit einem Datenbankfehler statt einer Meldung. Die
  Doku verlangt die Migration vor dem ersten Befehl (`accounti db upgrade` aus Paket A, mit
  Versionsvermerk gleichwertig `alembic upgrade head`); eine Schemaprüfung beim Start
  gehört zu Paket A (Versionsvermerk), nicht hierher.
- **Trigger nur unter SQLite:** Wie bei Journal und Protokollen sperrt PostgreSQL rohes
  SQL auf `verrechnungen` nicht; dort fällt eine Änderung im Bestandsabgleich von
  `journal pruefen` auf.
