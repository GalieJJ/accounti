# Spec: Anlagenbuchhaltung & Jahresabschluss

- **Status:** Entwurf (2026-08-10)
- **Baustein:** 12 von 12 (siehe [Bauplan](../bauplan.md))
- **Ziel-Branch:** `feat/anlagen-jahresabschluss`

## 1. Kontext

Nach den Bausteinen 1 bis 11 läuft die unterjährige Buchhaltung: Belege kommen an, werden kontiert,
Zahlungen fließen, die Voranmeldung geht raus. Was bleibt, ist der Jahreswechsel — und der ist
genau die Stelle, an der bisher der Steuerberater übernimmt.

Dabei besteht der Jahresabschluss zum größten Teil aus Rechenarbeit auf bereits erfassten Daten:
Abschreibungen fortschreiben, Rechnungsabgrenzungen bilden, Rückstellungen bewerten, Konten
abschließen, Ergebnis ermitteln. Das ist mechanisch, wiederkehrend und dokumentierbar — also
automatisierbar.

Was nicht automatisierbar ist, sind Bewertungsentscheidungen: Nutzungsdauer, Wahlrechte, die Höhe
einer Rückstellung. Sie bleiben Vorschläge, die jemand verantwortet.

## 2. Ziel

> Abschreibungen laufen von selbst, Abgrenzungen werden vorgeschlagen, und zum Jahresende steht
> ein prüffähiger Abschluss — als Einnahmenüberschussrechnung oder als Bilanz mit Gewinn- und
> Verlustrechnung, jeweils elektronisch übermittelbar.

## 3. Pipeline

```
UNTERJÄHRIG
   Buchung auf ein Anlagekonto
        │
        ▼
   [1] Anlagegut anlegen (Vorschlag: Nutzungsdauer aus AfA-Tabelle)
        │
        ▼
   [2] Monatliche / jährliche AfA-Buchung  ── automatisch, fortgeschrieben


JAHRESABSCHLUSS
   Abgeschlossene Perioden (Baustein 7)
        │
        ▼
   [1] Abschlussprüfungen
       Salden plausibel · Verrechnungskonten leer · OPOS bewertet ·
       alle Perioden geschlossen · alle Voranmeldungen abgegeben
        │
        ▼
   [2] Abschlussbuchungen
       ├─ AfA des Jahres (auch GWG, Sammelposten)
       ├─ Rechnungsabgrenzung aktiv / passiv
       ├─ Rückstellungen
       ├─ Umbuchung Privatkonten / Verrechnung
       └─ Umsatzsteuer-Jahresabgrenzung
        │  jede Buchung mit Begründung, jede zum Menschen zur Freigabe
        ▼
   [3] Auswertungen
       Summen und Salden · Kontennachweis · Anlagenspiegel ·
       EÜR   oder   Bilanz + Gewinn- und Verlustrechnung
        │
        ▼
   [4] Elektronische Übermittlung  (über die Schicht aus Baustein 9)
       EÜR-Anlage  oder  E-Bilanz-Datensatz  ── nach Freigabe
        │
        ▼
   [5] Saldovortrag ins neue Jahr
```

## 4. Komponenten & Arbeitspakete

### 4.1 `anlagen/` — Anlagenbuchhaltung *(neu)*

`Anlagegut`: Bezeichnung, Anschaffungsdatum, Anschaffungskosten, Nutzungsdauer, Abschreibungsart,
Konto, Beleg, Restbuchwert, Abgangsdatum.

Abschreibungsarten: linear zeitanteilig ab Anschaffungsmonat, geringwertige Wirtschaftsgüter mit
Sofortabzug, Sammelposten mit Auflösung über fünf Jahre. Die Grenzbeträge sind Konfiguration, keine
Konstanten im Code — sie ändern sich mit der Gesetzgebung, und alte Jahre müssen mit den damals
gültigen Werten rechenbar bleiben.

Nutzungsdauer wird aus einer hinterlegten AfA-Tabelle vorgeschlagen (`config/afa.yaml`), bleibt aber
änderbar. Anlagenspiegel mit Zugängen, Abgängen, Abschreibungen und Restbuchwerten je Gruppe.

Anlagenabgang mit Restbuchwert, Erlös und Ergebnis aus dem Abgang.

### 4.2 `abschluss/abgrenzung.py` *(neu)*

Erkennt Aufwand und Ertrag, die wirtschaftlich ins andere Jahr gehören — Versicherungen, Mieten,
Wartungsverträge, Leasing —, in der Regel erkennbar am Leistungszeitraum auf dem Beleg. Schlägt die
Abgrenzungsbuchung vor und die Auflösung im Folgejahr gleich mit, damit die Umkehrung nicht
vergessen wird.

### 4.3 `abschluss/rueckstellungen.py` *(neu)*

Wiederkehrende Rückstellungen als Vorlagen: Abschluss- und Prüfungskosten, Aufbewahrung von
Unterlagen, Urlaubsrückstellung, ausstehende Rechnungen. Vorschlag mit Berechnungsweg; die Höhe ist
eine Bewertungsentscheidung und wird bestätigt, nicht gesetzt. Auflösung oder Fortführung im
Folgejahr wird beim nächsten Abschluss abgefragt.

### 4.4 `abschluss/kassenbuch.py` *(neu)*

Bargeschäfte mit fortlaufender Nummerierung, Tagessaldo und Kassensturzfähigkeit. Ein negativer
Kassenbestand ist rechnerisch unmöglich und wird deshalb hart abgelehnt, nicht als Warnung geführt —
ein Kassenbuch, das kurzzeitig ins Minus läuft, ist der klassische Befund in jeder Betriebsprüfung.

Abgrenzung: Ein Kassenbuch führen ja, ein zertifiziertes Kassensystem sein nein (siehe
[Bauplan, Nicht-Ziele](../bauplan.md#nicht-ziele)).

### 4.5 `abschluss/pruefungen.py` *(neu)*

Vor dem Abschluss: Sind alle Perioden geschlossen? Alle Voranmeldungen abgegeben? Sind
Verrechnungs- und Interimskonten ausgeglichen? Stimmt die Summe der Personenkonten mit den
Sammelkonten überein? Sind alle Bankkonten bis zum Stichtag abgeglichen und die Salden identisch
mit dem Kontoauszug? Sind offene Posten bewertet?

Diese Prüfungen nutzen die Mechanik aus Baustein 7 und liefern Befunde mit Schweregrad.

### 4.6 `abschluss/auswertungen.py` *(neu)*

Summen- und Saldenliste, Kontennachweis, Betriebsvermögensvergleich. Darauf aufbauend:

- **Einnahmenüberschussrechnung** nach amtlichem Schema — für die kleineren Gesellschaften
- **Bilanz und Gewinn- und Verlustrechnung** nach dem Gliederungsschema des HGB, in der für die
  Größenklasse zulässigen Form

Die BWA-Zuordnung je Konto liegt in `config/skr03.yaml` bereits vor und ist die Vorlage dafür, wie
die Abschlusszuordnung modelliert wird.

### 4.7 `abschluss/uebermittlung.py` *(neu)*

Elektronische Übermittlung über dieselbe Schicht wie in Baustein 9, mit denselben Grundsätzen:
Testmodus zuerst, Freigabe durch den Menschen immer, Protokoll unveränderbar abgelegt. Für die
E-Bilanz kommt die Zuordnung der Konten zur amtlichen Taxonomie hinzu — sie wird als Konfiguration
gepflegt und einmal je Kontenrahmen erstellt.

### 4.8 `abschluss/vortrag.py` *(neu)*

Saldovortrag ins neue Jahr: Bestandskonten mit Saldo, Erfolgskonten auf null, Ergebnis auf das
Kapitalkonto. Das Vorjahr wird gesperrt; eine spätere Änderung ist nur mit erneutem Abschluss und
Protokoll möglich.

### 4.9 CLI

```bash
accounti anlagen liste
accounti anlagen anlegen --beleg 4711 --nutzungsdauer 3
accounti anlagen afa --jahr 2026                    # AfA-Lauf
accounti anlagen spiegel --jahr 2026
accounti kasse buchen --betrag -24.90 --text "Porto"
accounti abschluss pruefen --jahr 2026
accounti abschluss buchen --jahr 2026               # Vorschläge zur Freigabe
accounti abschluss euer --jahr 2026
accounti abschluss bilanz --jahr 2026
accounti abschluss uebermitteln --jahr 2026 --test
accounti abschluss vortrag --jahr 2026
```

## 5. Tech-Entscheidungen (fix)

| Thema | Entscheidung |
|-------|--------------|
| Grenzbeträge | Konfiguration mit Gültigkeitszeitraum, damit alte Jahre korrekt bleiben |
| Nutzungsdauer | Vorschlag aus AfA-Tabelle, immer änderbar |
| Abschlussbuchungen | Immer Vorschlag mit Begründung, nie automatisch gebucht |
| Bewertungen | Rückstellungshöhe und Wahlrechte werden bestätigt, nicht gesetzt |
| Kassenbuch | Negativer Bestand wird abgelehnt, nicht gewarnt |
| Übermittlung | Über die Schicht aus Baustein 9, Testmodus zuerst |
| Taxonomie | Kontenzuordnung als Konfiguration je Kontenrahmen |
| Vortrag | Sperrt das Vorjahr; Änderung nur mit erneutem Abschluss und Protokoll |

## 6. Teststrategie

- AfA gegen handgerechnete Reihen: unterjähriger Zugang, voller Jahresverlauf, Abgang im
  laufenden Jahr, Sammelposten über fünf Jahre, geringwertiges Wirtschaftsgut.
- Grenzbeträge mit unterschiedlichen Gültigkeitszeiträumen: ein Zugang aus einem alten Jahr rechnet
  mit den damaligen Werten.
- Abgrenzung und Auflösung als Paar — der Test prüft, dass die Umkehrung im Folgejahr entsteht.
- Kassenbuch: Buchung, die den Bestand negativ machen würde, wird abgelehnt.
- Abschlussprüfungen je einzeln mit auslösendem und nicht auslösendem Fixture.
- Vollständiger Durchlauf über ein synthetisches Geschäftsjahr: Buchungen → Abschluss → EÜR →
  Vortrag → Eröffnungssalden stimmen mit den Schlusssalden überein.

## 7. Akzeptanzkriterien

1. Ein im September angeschafftes Wirtschaftsgut wird zeitanteilig mit vier Monaten abgeschrieben.
2. Der Anlagenspiegel stimmt in Zugängen, Abschreibungen und Restbuchwerten mit der Sollrechnung
   überein.
3. Eine im Dezember gezahlte Jahresversicherung wird als Abgrenzung vorgeschlagen, inklusive
   Auflösung im Folgejahr.
4. Eine Kassenbuchung, die den Bestand negativ machen würde, wird abgelehnt.
5. Weichen Buchbestand und Kontoauszugssaldo zum Stichtag ab, blockiert das den Abschluss.
6. Die Einnahmenüberschussrechnung stimmt mit der Summen- und Saldenliste überein.
7. Nach dem Saldovortrag entsprechen die Eröffnungssalden exakt den Schlusssalden des Vorjahres,
   und das Vorjahr ist gesperrt.

## 8. Ausdrücklich NICHT in diesem Baustein

Körperschaft-, Gewerbe- und Einkommensteuererklärung · Konzernabschluss · internationale
Rechnungslegung · latente Steuern · Anhang und Lagebericht als Text · Offenlegung im
Unternehmensregister · steuerliche Gestaltungsberatung.
