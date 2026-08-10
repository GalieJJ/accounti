# Spec: Steuermeldungen & elektronische Übermittlung

- **Status:** Entwurf (2026-08-10)
- **Baustein:** 9 von 12 (siehe [Bauplan](../bauplan.md))
- **Ziel-Branch:** `feat/steuermeldungen-elster`

## 1. Kontext

Dieser Baustein ist zur Hälfte gebaut. `steuer/umsatzsteuer.py` bestimmt den Geschäftsvorfall und
rechnet die Steuer, `steuer/voranmeldung.py` ermittelt die ELSTER-Kennziffern und die Zahllast,
`steuer/oss.py` prüft die Schwelle und erstellt die Quartalsmeldung, `steuer/eu_steuersaetze.py`
kennt die Sätze aller 27 Mitgliedstaaten und des Vereinigten Königreichs.

Was fehlt, ist der letzte Schritt: **die Übermittlung**. Heute enden alle Auswertungen in einer
Textzusammenfassung oder einer CSV-Datei, die jemand abtippt oder weiterreicht. Genau dieser
manuelle Schritt ist der teuerste, weil er termingebunden ist und Fehler erst im Bescheid auffallen.

Dazu kommen zwei Meldungen, die bislang ganz fehlen: die Zusammenfassende Meldung für
innergemeinschaftliche Lieferungen und die Dauerfristverlängerung mit ihrer Sondervorauszahlung.

## 2. Ziel

> Die Umsatzsteuer-Voranmeldung wird aus den gebuchten Daten erzeugt, plausibilisiert und
> elektronisch übermittelt — mit revisionssicher abgelegtem Übertragungsprotokoll. Fristen sind
> bekannt und werden erinnert.

## 3. Pipeline

```
Buchungssätze (Baustein 1/4)
        │
        ▼
  [1] Kennziffernermittlung            ← steuer/voranmeldung.py (vorhanden)
      Kz 81, 86, 41, 43, 66, 89 …
        │
        ▼
  [2] Plausibilisierung
      ├─ Kennziffern intern konsistent
      ├─ Vorjahres-/Vormonatsvergleich (Ausreißer melden)
      ├─ Buchungen ohne Steuerschlüssel im Zeitraum
      ├─ Periode abgeschlossen? (Baustein 7)
      └─ offene Prüfbefunde mit Schweregrad „fehler"?
        │
        ▼
  [3] Freigabe durch den Menschen  ── immer, nie automatisch
        │
        ▼
  [4] Übermittlung
      ├─ Umsatzsteuer-Voranmeldung
      ├─ Dauerfristverlängerung + Sondervorauszahlung
      ├─ Zusammenfassende Meldung
      └─ (Jahreserklärungen → Baustein 12)
        │
        ▼
  [5] Protokoll  ── Übertragungsticket, Zeitpunkt, übermittelter Datensatz,
                    Prüfbericht — unveränderbar abgelegt, 10 Jahre
        │
        ▼
  [6] Zahllast  → offener Posten gegenüber dem Finanzamt (Baustein 4)


  OSS-Quartalsmeldung  ← steuer/oss.py (vorhanden)
        └─ Datei-Export für das Portal; getrennter Weg, eigene Frist
```

Schritt 3 ist bewusst nicht abkürzbar. Eine Steuererklärung ist eine Erklärung — sie wird abgegeben,
nicht ausgelöst. Das entspricht dem Architekturprinzip „Supervisor hat das letzte Wort".

## 4. Komponenten & Arbeitspakete

### 4.1 `steuer/plausibilitaet.py` *(neu)*

Prüfungen vor der Abgabe, mit Schweregraden wie in Baustein 7:
- Rechnerische Konsistenz der Kennziffern untereinander
- Vergleich mit Vormonat und Vorjahresmonat; auffällige Abweichungen als Hinweis
- Buchungen im Zeitraum ohne Steuerschlüssel auf steuerrelevanten Konten
- Innergemeinschaftliche Lieferungen ohne geprüfte USt-IdNr. des Abnehmers (Baustein 4)
- Erlöse in OSS-Ländern, die nicht in der OSS-Meldung auftauchen
- Offene Befunde mit Schweregrad „fehler" blockieren die Freigabe

### 4.2 `elster/uebermittlung.py` *(neu)*

Anbindung an die amtliche Übermittlungsschnittstelle. Kapselung als schmale Schicht mit einem
Testmodus, in dem der Datensatz erzeugt und geprüft, aber nicht abgegeben wird — der Normalfall
während der Entwicklung und beim ersten Echtlauf eines Betriebs.

Zertifikat und Passwort liegen verschlüsselt außerhalb der Datenbank, wie die Bankzugänge in
Baustein 5.

### 4.3 `elster/protokoll.py` *(neu)*

Was übermittelt wurde, muss nachweisbar bleiben: der erzeugte Datensatz, das Übertragungsticket,
der Zeitpunkt, das Ergebnis und der zurückgemeldete Prüfbericht. Ablage wie das Belegarchiv aus
Baustein 2, unveränderbar und aufbewahrungspflichtig. Eine korrigierte Anmeldung ersetzt die alte
nicht, sondern tritt daneben.

### 4.4 `steuer/fristen.py` *(neu)*

Fristen sind rechenbar und deshalb erinnerbar: Voranmeldung bis zum 10. des Folgemonats bzw.
-quartals, mit Dauerfristverlängerung einen Monat später; die Sondervorauszahlung ist bis zum 10.
Februar anzumelden; die OSS-Quartalsmeldung ist bis zum Monatsletzten nach Quartalsende fällig
(diese Regel steckt bereits in `steuer/oss.py`). Verschiebung bei Wochenenden und Feiertagen,
Feiertage je Bundesland.

Aus jeder Frist entsteht rechtzeitig eine Aufgabe (Baustein 8).

### 4.5 `steuer/zusammenfassende_meldung.py` *(neu)*

Innergemeinschaftliche Lieferungen und sonstige Leistungen je Abnehmer und USt-IdNr., summiert je
Meldezeitraum. Grundlage sind die Buchungen auf den entsprechenden Erlöskonten und die geprüften
USt-IdNr. aus Baustein 4.

### 4.6 Zahllast als offener Posten *(Erweiterung)*

Die ermittelte Zahllast wird gebucht und als offener Posten gegenüber dem Finanzamt geführt. Damit
taucht sie in der Fälligkeitsstaffel auf und lässt sich über den Zahlungsvorschlag aus Baustein 6
begleichen — inklusive der Besonderheit, dass bei erteiltem Lastschriftmandat das Finanzamt selbst
abbucht und der Posten durch den Kontoumsatz ausgeglichen wird.

### 4.7 CLI

```bash
accounti ustva --period 2026-08                    # Kennziffern + Plausibilisierung
accounti ustva pruefen --period 2026-08
accounti ustva uebermitteln --period 2026-08 --test
accounti ustva uebermitteln --period 2026-08
accounti zm --period 2026-08                       # Zusammenfassende Meldung
accounti oss meldung --quartal 2026-Q3             # vorhanden, Datei-Export
accounti fristen --jahr 2026                       # Fristenkalender
```

## 5. Tech-Entscheidungen (fix)

| Thema | Entscheidung |
|-------|--------------|
| Basis | Bestehende Module in `steuer/` bleiben die Rechenlogik; dieser Baustein ergänzt nur Prüfung, Abgabe und Protokoll |
| Freigabe | Immer durch den Menschen, nie automatisch |
| Testmodus | Erzeugen und prüfen ohne Abgabe — Default beim ersten Lauf |
| Zertifikate | Verschlüsselt außerhalb der Datenbank, wie Bankzugänge |
| Protokoll | Unveränderbar, 10 Jahre, korrigierte Anmeldung tritt neben die alte |
| Fristen | Berechnet inklusive Wochenend- und Feiertagsverschiebung, erzeugen Aufgaben |
| OSS | Bleibt Datei-Export über das Portal, eigener Weg und eigene Frist |

## 6. Teststrategie

- Kennziffernermittlung gegen handgerechnete Sollwerte je Konstellation: Inland 19 % und 7 %,
  innergemeinschaftliche Lieferung, Reverse-Charge als Leistungsempfänger, Ausfuhr, OSS.
- Plausibilisierung: je Prüfung ein auslösendes und ein nicht auslösendes Fixture.
- Übermittlung ausschließlich gemockt; im CI wird nie abgegeben.
- Protokollablage: Manipulationstest analog zum Journal aus Baustein 7.
- Fristenberechnung gegen einen Kalender mit Wochenenden, bundeseinheitlichen und regionalen
  Feiertagen; Sonderfall 10. Februar.

## 7. Akzeptanzkriterien

1. `accounti ustva --period` liefert dieselben Kennziffern wie die handgerechnete Sollrechnung.
2. Eine Buchung ohne Steuerschlüssel auf einem steuerrelevanten Konto verhindert die Freigabe.
3. Der Testmodus erzeugt einen prüffähigen Datensatz, ohne etwas abzugeben.
4. Nach der Übermittlung liegen Datensatz, Ticket, Zeitpunkt und Prüfbericht unveränderbar vor.
5. Die Zahllast erscheint als offener Posten gegenüber dem Finanzamt.
6. Der Fristenkalender verschiebt den 10., der auf ein Wochenende fällt, korrekt.
7. Eine innergemeinschaftliche Lieferung ohne geprüfte USt-IdNr. wird vor der Abgabe bemängelt.

## 8. Ausdrücklich NICHT in diesem Baustein

Jahreserklärungen und E-Bilanz (Baustein 12) · Lohnsteueranmeldung · Gewerbesteuer- und
Körperschaftsteuervorauszahlungen · steuerliche Auslegung von Zweifelsfragen · Bescheidabgleich.
