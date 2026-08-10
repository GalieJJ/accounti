# Spec: Kreditoren, Debitoren & offene Posten

- **Status:** Entwurf (2026-08-10)
- **Baustein:** 4 von 12 (siehe [Bauplan](../bauplan.md))
- **Ziel-Branch:** `feat/kreditoren-debitoren-opos`

## 1. Kontext

Baustein 1 bucht direkt gegen das Bankkonto: Zahlung raus, Aufwand rein. Das funktioniert, solange
Rechnung und Zahlung im selben Moment passieren — also fast nie. In Wahrheit liegt zwischen
Rechnungseingang und Zahlung ein Zeitraum, in dem eine Verbindlichkeit besteht. Genau diesen
Zeitraum bildet die Buchhaltung über Personenkonten und offene Posten ab.

Ohne offene Posten weiß niemand, was noch zu zahlen ist, welches Skonto verfällt, welcher Kunde
nicht bezahlt hat und wie die Liquidität nächste Woche aussieht. Und ohne Personenkonten fehlt der
Anker, an dem Belege, Zahlungen und Mahnungen zusammenlaufen.

Dieser Baustein ist die Drehscheibe: Hier laufen der Belegstrang (2, 3) und der Bankstrang (1, 5)
zusammen.

## 2. Ziel

> Aus einem Beleg entsteht eine Buchung auf ein Personenkonto und ein offener Posten. Sobald die
> passende Zahlung eintrifft, wird der Posten automatisch ausgeglichen — inklusive Teilzahlung
> und Skonto.

## 3. Pipeline

```
Eingangsrechnung (Beleg)          Ausgangsrechnung (Baustein 3)
        │                                    │
        ▼                                    ▼
  [1] Kontakt bestimmen                [1] Kontakt bekannt
      (Match / neu anlegen)                  │
        │                                    │
        ▼                                    ▼
  [2] Buchung Aufwand an Kreditor      [2] Buchung Debitor an Erlös
        │                                    │
        └──────────────┬─────────────────────┘
                       ▼
              [3] Offener Posten
                  (fällig am, Skontofrist, Restbetrag)
                       │
     Banktransaktion ──┤
                       ▼
              [4] Zahlungszuordnung
                  Stufe A: Referenz / Rechnungsnummer
                  Stufe B: Betrag + Kontakt exakt
                  Stufe C: unscharf → Vorschlag zur Prüfung
                       │
                       ▼
              [5] Ausgleich
                  ├─ vollständig      → Posten geschlossen
                  ├─ Teilzahlung      → Restbetrag bleibt offen
                  └─ Skonto gezogen   → Skontobuchung + Vorsteuerkorrektur
```

## 4. Komponenten & Arbeitspakete

### 4.1 `kontakte/` — Debitoren- und Kreditorenstammdaten *(neu)*

Ein `Kontakt` ist Lieferant, Kunde oder beides. Felder: Name, Anschrift, Land, USt-IdNr.,
Steuernummer, IBAN, Zahlungsbedingungen (Zahlungsziel, Skontosatz, Skontotage), Personenkontonummer,
Sachkonto-Vorschlag für wiederkehrende Buchungen.

Personenkontonummern werden im jeweiligen Nummernkreis des Kontenrahmens vergeben (im SKR03
Debitoren ab 10000, Kreditoren ab 70000) und sind konfigurierbar, weil die Kreise je Betrieb
abweichen.

**Kontakterkennung** aus Belegdaten: IBAN, USt-IdNr. und Name in dieser Reihenfolge. Erst wenn
nichts greift, entsteht ein neuer Kontakt — und der geht zur Prüfung, statt still angelegt zu
werden. Sonst wächst die Stammdatenliste mit Schreibvarianten desselben Lieferanten zu.

### 4.2 `kontakte/ustid.py` — USt-IdNr.-Prüfung *(neu)*

Eine steuerfreie innergemeinschaftliche Lieferung setzt eine gültige USt-IdNr. des Abnehmers
voraus — und im Streitfall den Nachweis, dass sie zum Zeitpunkt der Lieferung geprüft wurde.
Deshalb: qualifizierte Bestätigungsabfrage gegen die amtliche Schnittstelle, **mit Protokollierung**
von Zeitpunkt, Anfrage und Ergebnis. Das Protokoll ist aufbewahrungspflichtig.

Greift direkt in `steuer/umsatzsteuer.py`: Die dort implementierte Fallunterscheidung „EU + B2B mit
USt-ID → 0 %" bekommt damit erstmals eine belastbare Grundlage statt eines Feldes, das jemand
eingetippt hat.

### 4.3 `opos/` — offene Posten *(neu)*

`OffenerPosten`: Kontakt, Beleg, Richtung, Betrag, Restbetrag, Fälligkeitsdatum, Skontofrist,
Skontobetrag, Status, Mahnstufe.

Auswertungen: OPOS-Liste je Richtung, Fälligkeitsstaffel (nicht fällig / 1–30 / 31–60 / 61–90 /
über 90 Tage), Summen je Kontakt.

### 4.4 `opos/zuordnung.py` — Zahlungszuordnung *(neu)*

Dreistufig, nach demselben Muster wie die Kontierung: deterministisch vor unscharf, und was unsicher
bleibt, geht zum Menschen.

1. **Referenz** — Rechnungsnummer im Verwendungszweck. Sicherster Treffer.
2. **Exakt** — Betrag stimmt mit einem offenen Posten desselben Kontakts überein.
3. **Unscharf** — Betrag entspricht dem Rechnungsbetrag abzüglich Skonto; oder eine Zahlung deckt
   mehrere Posten; oder Teilzahlung. Ergebnis ist ein Vorschlag mit Confidence, kein Automatismus.

### 4.5 `opos/ausgleich.py` *(neu)*

Bucht den Ausgleich. Bei gezogenem Skonto entstehen zwei Nebenwirkungen, die oft vergessen werden
und deshalb hier explizit stehen: die Skontobuchung auf das passende Erlösschmälerungs- bzw.
Aufwandsminderungskonto **und** die anteilige Korrektur der Vorsteuer bzw. Umsatzsteuer. Beides
läuft über `steuer/umsatzsteuer.py`.

### 4.6 Anpassung `buchung/mapper.py` *(bestehend)*

Der Mapper kennt heute nur Sachkonten. Er bekommt einen zweiten Pfad: Liegt ein Beleg mit Kontakt
vor, wird gegen das Personenkonto gebucht und ein offener Posten erzeugt. Der bestehende Pfad
(Bankbuchung ohne Beleg) bleibt unverändert bestehen — er ist für Bankgebühren, Zinsen und
Ähnliches weiterhin richtig.

### 4.7 CLI

```bash
accounti kontakte liste --typ kreditor
accounti kontakte pruefe-ustid 10001          # qualifizierte Abfrage + Protokoll
accounti opos liste --richtung eingang --faellig
accounti opos staffel                          # Fälligkeitsstaffel
accounti opos zuordnen --period 2026-08        # Zahlungen automatisch zuordnen
```

## 5. Tech-Entscheidungen (fix)

| Thema | Entscheidung |
|-------|--------------|
| Personenkonten | Nummernkreise je Kontenrahmen konfigurierbar, Default nach SKR03/SKR04 |
| Kontakterkennung | IBAN → USt-IdNr. → Name; Neuanlage immer zur Prüfung |
| USt-IdNr. | Qualifizierte Abfrage mit revisionssicherem Protokoll |
| Zuordnung | Dreistufig, unscharfe Treffer sind Vorschläge |
| Skonto | Immer mit Steuerkorrektur, nie als reine Betragsdifferenz |
| Steuerlogik | Ausschließlich `steuer/umsatzsteuer.py` |

## 6. Teststrategie

- Zuordnung über alle Fälle: exakt, Skonto, Teilzahlung, Sammelzahlung über mehrere Rechnungen,
  Überzahlung, Zahlung ohne passenden Posten.
- Skontobuchung mit Steuerkorrektur gegen handgerechnete Sollwerte (19 % und 7 %).
- Kontakterkennung mit Schreibvarianten desselben Lieferanten — Erwartung: ein Kontakt, nicht drei.
- USt-IdNr.-Abfrage gemockt; geprüft wird, dass das Protokoll vollständig und unveränderbar ist.
- Fälligkeitsstaffel gegen ein Fixture mit bekannten Stichtagen.

## 7. Akzeptanzkriterien

1. Eine Eingangsrechnung erzeugt eine Buchung gegen das Kreditorenkonto und einen offenen Posten
   mit korrektem Fälligkeitsdatum aus den Zahlungsbedingungen.
2. Die passende Banktransaktion gleicht den Posten automatisch aus.
3. Eine Zahlung mit gezogenem Skonto gleicht vollständig aus und bucht Skonto **inklusive**
   Vorsteuerkorrektur.
4. Eine Teilzahlung lässt den Restbetrag offen; eine zweite Zahlung schließt den Posten.
5. Eine Sammelzahlung über drei Rechnungen wird als Vorschlag erkannt und nach Bestätigung
   korrekt aufgeteilt.
6. Die Fälligkeitsstaffel stimmt mit der handgerechneten Sollliste überein.
7. Eine ungültige USt-IdNr. verhindert die Buchung als steuerfreie innergemeinschaftliche
   Lieferung und meldet den Grund.

## 8. Ausdrücklich NICHT in diesem Baustein

Zahlungsausgang und Sammelüberweisungen (Baustein 6) · Mahnwesen (Baustein 6) · Liquiditätsplanung
und Prognosen · Fremdwährungsbewertung · Anzahlungen und Dauerrechnungen.
