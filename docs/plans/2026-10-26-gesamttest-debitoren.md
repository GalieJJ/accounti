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
erkannten Zahlers, hat der Zahler Vorrang (höchstens 0,7 bzw. 0,6, nie automatisch);
ist der Zahler unbekannt und steht eine Nummer mit Trennzeichen nur als
zusammenhängende Ziffernfolge im Zweck, die ein Datum JJJJMMTT ist, bleibt es ein
Vorschlag (der eindeutige Betrag geht dann der Referenz vor).

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
EN 16931 (ZUGFeRD-Profil EN 16931). Über 250 € braucht sie die Anschrift (§ 14 Abs. 4
Satz 1 Nr. 1 UStG), bis 250 € genügt die Kleinbetragsrechnung (§ 33 UStDV). Das
KoSIT-Prüftool hat nur XRechnung-Szenarien — die EN-16931-Rechnung prüft Mustang.

## Grenzen

- **Anzahlungs-/Vorausrechnungen:** Liegt die Leistung nach dem Rechnungsdatum, bucht
  accounti zum Rechnungsdatum und weist darauf hin; die Mindest-Ist-Versteuerung bei
  Anzahlungen (§ 13 Abs. 1 Nr. 1 Buchst. a Satz 4 UStG) bildet accounti nicht ab.
- **Katalogleistungen an Privatkunden im Drittland** (§ 3a Abs. 4 Satz 2 UStG, z.B.
  Überlassung von Urheberrechten, Beratung) erkennt accounti nicht — es setzt deutsche
  Steuer (zu viel, nicht zu wenig). Elektronische Leistungen dorthin und Dienstleistungen
  an Unternehmer im Drittland (Kategorie O) werden weiter abgelehnt.
- **Korrektur nur zu Rechnungen aus accounti:** `--korrektur-zu` verlangt eine in accounti
  ausgestellte Rechnung (für BT-26 und den Kunden).
- **Verrechnung über zwei Personenkonten** (Forderung gegen Verbindlichkeit desselben
  Kontakts) bucht accounti nicht.
- **Verrechnung zurücknehmen:** Eine Verrechnung ist unveränderbar (nur anfügen) und
  lässt sich nicht aufheben — wie ein Zahlungsausgleich, dessen Storno den Posten
  ebenfalls nicht wieder öffnet; vor `opos verrechnen` die Nummern prüfen.
- **Stichtagsliste:** rekonstruiert den Rest aus gebuchten Zuordnungen und Verrechnungen;
  die Verrechnung der Zahllast mit Erstattungen (`elster/zahllast.py`) ist undatiert und
  gilt als vor jedem Stichtag geschehen.
- **Prüfregel Personenkonto = Summe offene Posten** ergänzt Paket C (Eingang B05).
- **Verzugshinweis:** Rechnungen, die vor dieser Version ausgestellt wurden, tragen den
  Hinweis nach § 286 Abs. 3 BGB nicht; `mahnwesen.hinweis_30_tage` gilt für sie trotzdem.
