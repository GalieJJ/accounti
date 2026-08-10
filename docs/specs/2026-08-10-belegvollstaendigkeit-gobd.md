# Spec: Belegvollständigkeit & Ordnungsmäßigkeit

- **Status:** Entwurf (2026-08-10)
- **Baustein:** 7 von 12 (siehe [Bauplan](../bauplan.md))
- **Ziel-Branch:** `feat/belegvollstaendigkeit-gobd`

## 1. Kontext

Eine automatisierte Buchhaltung ist schnell — und schnell falsch, wenn niemand prüft, ob sie
vollständig ist. Der klassische Fehler ist nicht die falsch kontierte Buchung, sondern die Zahlung,
zu der nie ein Beleg auftauchte, und die drei Jahre später in der Betriebsprüfung den Vorsteuerabzug
kostet.

Die GoBD verlangen von einer Buchführung Vollständigkeit, Richtigkeit, zeitgerechte Erfassung,
Ordnung, Unveränderbarkeit und Nachvollziehbarkeit. Bislang erfüllt accounti davon die
Nachvollziehbarkeit (jede Buchung kennt ihre Herkunft und Confidence) — der Rest ist Anspruch ohne
Mechanik.

Dieser Baustein baut die Mechanik: die Prüfungen, die Nachforderung fehlender Belege und das
unveränderbare Journal.

## 2. Ziel

> accounti sagt jederzeit, was der Buchhaltung fehlt und was daran nicht stimmt — und fordert
> fehlende Belege selbstständig an. Gebuchtes lässt sich nicht mehr heimlich ändern.

## 3. Pipeline

```
Belege (2/3) ─┐
Umsätze (1/5) ─┼──▶ [1] PRÜFREGELN ──▶ Befundliste
Buchungen (1) ─┘         │              (Regel, Schweregrad, Objekt, Begründung)
                         │
        ┌────────────────┼────────────────┬─────────────────┐
        ▼                ▼                ▼                 ▼
  Vollständigkeit    Richtigkeit     Zeitgerechtheit     Ordnung
  ─────────────      ───────────     ───────────────     ───────
  Umsatz ohne        Rechenprobe     Beleg älter als     Nummernkreise
  Beleg              § 14 UStG       Frist, nicht        lückenlos
  Beleg ohne         Steuerschlüssel erfasst             Periode
  Umsatz             ./. Konto       Buchung nach        abgeschlossen
  Lücke im           Adressat        Periodenabschluss
  Nummernkreis       ./. Kontakt
        │
        ▼
  [2] NACHFORDERUNG  → Aufgabe (Baustein 8) + Erinnerung
        │
        ▼
  [3] JOURNAL (append-only)  ── jede Buchung, jede Änderung, jede Freigabe
        │
        ▼
  [4] VERFAHRENSDOKUMENTATION (generiert)
```

## 4. Komponenten & Arbeitspakete

### 4.1 `pruefung/regeln/` — Prüfregeln *(neu)*

Regeln sind einzelne, benannte Prüfungen mit Schweregrad (`hinweis`, `warnung`, `fehler`) und
einer Begründung im Klartext. Sie laufen über einen Zeitraum und liefern Befunde — sie ändern
nichts.

**Vollständigkeit**
- Banktransaktion ohne zugeordneten Beleg (ab konfigurierbarem Betrag)
- Beleg ohne zugeordnete Zahlung nach Ablauf des Zahlungsziels
- Lücke in einem Nummernkreis (Ausgangsrechnungen, Belegnummern)
- Kontoauszug fehlt: Lücke in der Auszugsnummer oder im Saldoverlauf

**Richtigkeit**
- Pflichtangaben nach § 14 UStG unvollständig (Datum, Nummer, Steuernummer/USt-IdNr., Entgelt,
  Steuersatz, Steuerbetrag, Leistungsbeschreibung)
- Rechenprobe: Summe der Positionen ≠ Belegsumme; Netto + Steuer ≠ Brutto je Satz
- Steuerschlüssel passt nicht zum Sachkonto (nutzt die Steuerautomatik aus `config/skr03.yaml`)
- Steuersatz unplausibel zum Land des Kontakts (nutzt `steuer/eu_steuersaetze.py`)
- Adressat des Belegs ist nicht die buchende Gesellschaft
- Vorsteuerabzug ohne gültige USt-IdNr. des Lieferanten bei innergemeinschaftlichem Erwerb
- Auffällige Dubletten: gleicher Betrag, gleicher Kontakt, enges Zeitfenster

**Zeitgerechtheit**
- Beleg liegt länger als die konfigurierte Frist unbearbeitet
- Buchung mit Datum in einer bereits abgeschlossenen Periode

**Ordnung**
- Buchungen ohne Belegbezug und ohne Begründung für Belegfreiheit
- Offene Posten mit unplausiblem Alter

Regeln liegen als Konfiguration vor, wo es geht — nach dem Vorbild von `config/regeln.yaml`, damit
Betriebe Schwellenwerte anpassen können, ohne Code zu ändern.

### 4.2 `pruefung/nachforderung.py` *(neu)*

Aus einem Befund „Umsatz ohne Beleg" wird eine Aufgabe (Baustein 8) mit Kontext: welcher Umsatz,
welcher Betrag, welche Gegenpartei, wer ist zuständig. Erinnerungen laufen in konfigurierbaren
Abständen, eskalieren nach Frist und verstummen automatisch, sobald der Beleg eintrifft und der
Abgleich greift.

Anfrage per E-Mail an den Lieferanten ist möglich, aber optional und mit Vorlage — automatisch
verschickte Nachrichten an Dritte sind eine Entscheidung des Betriebs, kein Default.

### 4.3 `pruefung/journal.py` — unveränderbares Journal *(neu)*

Ein fortlaufendes, append-only Journal über alle buchungsrelevanten Vorgänge: Buchung angelegt,
korrigiert, storniert, freigegeben, exportiert; Beleg importiert, verworfen; Zahlungslauf
freigegeben. Jeder Eintrag: laufende Nummer, Zeitstempel, Person, Vorgang, Objekt, Vorher-/Nachherwert.

Verkettung über einen Hash des Vorgängereintrags, damit nachträgliches Entfernen auffällt. Kein
Löschen, kein Ändern — auch nicht durch die Anwendung selbst.

### 4.4 Storno statt Änderung *(Änderung am Bestand)*

Heute darf ein Supervisor eine Buchung korrigieren; der Status `KORRIGIERT` existiert bereits in
`models/`. Ab Freigabe bzw. Export gilt das nicht mehr: Dann ist die Korrektur ein Storno mit
Neubuchung, beide bleiben sichtbar und sind gegenseitig referenziert.

Vor der Freigabe bleibt die direkte Korrektur erlaubt und sinnvoll — ein Vorschlag ist noch keine
Buchung. Die Grenze ist die Freigabe, und sie steht im Journal.

### 4.5 `pruefung/perioden.py` *(neu)*

Periodenabschluss: Ein abgeschlossener Monat nimmt keine neuen Buchungen mehr an. Wiedereröffnen ist
möglich, aber protokolliert und begründungspflichtig.

### 4.6 `pruefung/verfahrensdoku.py` *(neu)*

Die Verfahrensdokumentation ist Pflicht und wird üblicherweise als Fließtext einmal geschrieben und
dann nie wieder angefasst — worauf sie nicht mehr stimmt. accounti generiert sie stattdessen aus
dem tatsächlichen Systemzustand: eingerichtete Belegkanäle, Bankkonten und Provider, aktive Regeln,
Kontenrahmen, Aufbewahrungsfristen, Rollen, Freigabewege, eingesetzte LLM-Modelle und die Schwelle,
ab der automatisch gebucht wird. Ausgabe als Markdown und PDF, mit Stand-Datum.

### 4.7 CLI

```bash
accounti pruefen --period 2026-08                  # alle Regeln
accounti pruefen --regel beleg_fehlt --period 2026-08
accounti nachfordern --period 2026-08              # Aufgaben erzeugen
accounti journal --von 2026-08-01 --bis 2026-08-31
accounti journal pruefen                            # Verkettung verifizieren
accounti periode schliessen 2026-08
accounti verfahrensdoku --ausgabe verfahrensdoku.md
```

## 5. Tech-Entscheidungen (fix)

| Thema | Entscheidung |
|-------|--------------|
| Prüfregeln | Benannt, konfigurierbar, mit Schweregrad; ändern nie Daten |
| Journal | Append-only, hashverkettet, kein Löschpfad in der Anwendung |
| Korrektur | Vor Freigabe direkt, nach Freigabe nur per Storno |
| Nachforderung | Erzeugt Aufgaben; E-Mail an Dritte ist opt-in |
| Verfahrensdoku | Generiert aus dem Systemzustand, nicht handgeschrieben |
| Perioden | Abschluss sperrt; Wiedereröffnung protokolliert und begründet |

## 6. Teststrategie

- Je Prüfregel mindestens ein Fixture, das sie auslöst, und eines, das sie nicht auslösen darf —
  Fehlalarme sind hier so schädlich wie übersehene Befunde.
- Journal: Manipulationstest — ein nachträglich geänderter Eintrag muss die Verkettungsprüfung
  brechen.
- Storno-Pfad: Korrekturversuch an einer freigegebenen Buchung wird abgelehnt und als Storno
  angeboten.
- Periodensperre: Buchung in abgeschlossenem Monat wird abgelehnt.
- Verfahrensdokumentation: Änderung an der Konfiguration schlägt sich im generierten Dokument nieder.

## 7. Akzeptanzkriterien

1. Eine Zahlung ohne Beleg erscheint als Befund mit Betrag, Datum und Gegenpartei.
2. Eine Rechnung mit fehlender Steuernummer wird als unvollständig nach § 14 UStG gemeldet.
3. Ein Steuerschlüssel, der nicht zum Sachkonto passt, wird erkannt.
4. Aus einem Befund entsteht eine Aufgabe, die verstummt, sobald der Beleg eintrifft.
5. Ein manipulierter Journaleintrag wird von `accounti journal pruefen` gefunden.
6. Eine freigegebene Buchung lässt sich nur per Storno korrigieren; beide Buchungen bleiben sichtbar.
7. Die generierte Verfahrensdokumentation beschreibt den tatsächlich eingerichteten Stand.

## 8. Ausdrücklich NICHT in diesem Baustein

Zertifizierung der Buchführung · Datenzugriff für die Betriebsprüfung im amtlichen Format (Z3) —
später in Baustein 11 · Archivierung auf revisionssicherer Hardware · Kassenführung mit TSE.
