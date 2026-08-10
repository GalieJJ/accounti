# Spec: Zahlungsverkehr & Mahnwesen

- **Status:** Entwurf (2026-08-10)
- **Baustein:** 6 von 12 (siehe [Bauplan](../bauplan.md))
- **Ziel-Branch:** `feat/zahlungsverkehr-mahnwesen`

## 1. Kontext

Nach Baustein 4 weiß accounti, was zu zahlen und was zu bekommen ist. Beides passiert bislang
außerhalb: Überweisungen werden im Onlinebanking abgetippt, Mahnungen von Hand geschrieben — oder,
realistischer, gar nicht.

Beides sind mechanische Tätigkeiten mit klarer Datengrundlage, und beide kosten unmittelbar Geld,
wenn sie liegen bleiben: verfallenes Skonto auf der einen Seite, spät oder nie bezahlte
Ausgangsrechnungen auf der anderen.

## 2. Ziel

> accounti schlägt vor, was wann zu zahlen ist, erzeugt daraus eine Sammelüberweisung nach
> Freigabe — und mahnt überfällige Ausgangsrechnungen automatisch in Stufen.

## 3. Pipeline

```
ZAHLUNGSAUSGANG
   Offene Posten (Baustein 4)
        │
        ▼
   [1] Zahlungsvorschlagsliste
       Auswahl nach Fälligkeit und Skontofrist
       „zahle heute, weil morgen 2 % Skonto verfallen"
        │
        ▼
   [2] Prüfung   ├─ IBAN vorhanden und plausibel
                 ├─ Betrag = Restbetrag oder Restbetrag − Skonto
                 ├─ Dublettenzahlung? (gleicher Posten schon eingereicht)
                 └─ Sperrvermerk am Kontakt?
        │
        ▼
   [3] Freigabe  (optional Vier-Augen-Prinzip)
        │
        ▼
   [4] SEPA-Sammelüberweisung (pain.001)
       ├─ Einreichung über Bank-Provider (Baustein 5)
       └─ oder Datei zum manuellen Upload
        │
        ▼
   [5] Rückmeldung → Posten als „eingereicht" markiert
        │
        ▼
   [6] Kontoumsatz trifft ein → Ausgleich (Baustein 4)


MAHNWESEN
   Überfällige Debitoren-Posten
        │
        ▼
   [1] Stufenermittlung (Karenztage, Mindestbetrag, Stufenabstand)
        │
        ▼
   [2] Erzeugung  Zahlungserinnerung → 1. Mahnung → 2. Mahnung → letzte Mahnung
        │          (+ Verzugszinsen, + Mahngebühr je Stufe)
        ▼
   [3] Freigabe / Versand (E-Mail, PDF)
        │
        ▼
   [4] Mahnstufe am offenen Posten hochgezählt, Historie protokolliert
```

## 4. Komponenten & Arbeitspakete

### 4.1 `zahlung/vorschlag.py` *(neu)*

Erzeugt aus den offenen Kreditoren-Posten eine Vorschlagsliste zum Stichtag. Die Auswahllogik ist
die eigentliche Intelligenz: Ein Posten mit 2 % Skonto bei 10 Tagen und 30 Tagen Nettoziel ist
wirtschaftlich hoch verzinst — Skontofristen haben Vorrang vor Nettofälligkeiten. Konfigurierbar
sind Stichtag, Mindest-/Höchstbetrag, Kontaktfilter und ob Skonto grundsätzlich gezogen wird.

### 4.2 `zahlung/pruefung.py` *(neu)*

Zahlungsverkehr ist der Punkt, an dem ein Softwarefehler unmittelbar Geld bewegt. Deshalb prüft
diese Stufe hart und blockierend statt nur zu warnen: IBAN-Prüfziffer, Übereinstimmung der IBAN mit
dem Kontaktstammsatz, Betragsgrenzen, Dublettenzahlung desselben Postens, Sperrvermerke.

Eine IBAN, die von der im Stammsatz hinterlegten abweicht, ist ein Stoppschild — genau so
funktionieren gefälschte Rechnungen mit ausgetauschter Bankverbindung.

### 4.3 `zahlung/sepa.py` *(neu)*

Erzeugt SEPA-Überweisungen als `pain.001`, einzeln oder als Sammler. Ausführungsdatum,
Verwendungszweck aus Rechnungsnummer und Belegdatum, Endbetrag nach Skonto. Ausgabe entweder direkt
über den Bank-Provider aus Baustein 5 oder als Datei für den manuellen Upload — der Dateiweg bleibt
immer verfügbar, damit die Funktion auch ohne Live-Anbindung nutzbar ist.

### 4.4 `zahlung/freigabe.py` *(neu)*

Ein Zahlungslauf hat einen Zustand: Entwurf → freigegeben → eingereicht → ausgeführt. Das
Vier-Augen-Prinzip ist konfigurierbar (im Einpersonenbetrieb sinnlos, im Team unverzichtbar). Jede
Freigabe wird mit Person und Zeitpunkt protokolliert. Freigegebene Läufe sind unveränderbar; wer
korrigieren will, storniert.

### 4.5 `mahnwesen/` *(neu)*

Mahnstufen als Konfiguration, nicht als Code:

```yaml
# config/mahnwesen.yaml (Beispiel)
stufen:
  - name: Zahlungserinnerung
    ab_tagen: 5
    gebuehr: 0.00
    verzugszinsen: false
  - name: 1. Mahnung
    ab_tagen: 14
    gebuehr: 5.00
    verzugszinsen: true
  - name: 2. Mahnung
    ab_tagen: 28
    gebuehr: 10.00
    verzugszinsen: true
mindestbetrag: 10.00
karenztage: 3
```

Verzugszinsen werden nach den gesetzlichen Sätzen berechnet (Basiszinssatz plus Aufschlag, im
B2B-Geschäft höher als gegenüber Verbrauchern); der Basiszinssatz ist datiert hinterlegt, weil er
sich halbjährlich ändert. Mahngebühren sind Konfiguration, keine Rechtsberatung.

Ausgabe als PDF und E-Mail, Historie am offenen Posten. Kontakte lassen sich vom Mahnlauf ausnehmen.

### 4.6 CLI

```bash
accounti zahlung vorschlag --stichtag 2026-08-20   # Vorschlagsliste
accounti zahlung pruefen 42                         # Lauf prüfen
accounti zahlung freigeben 42
accounti zahlung sepa 42 --datei ueberweisung.xml   # oder --einreichen
accounti mahnen lauf --stichtag 2026-08-20
accounti mahnen versenden 7
```

## 5. Tech-Entscheidungen (fix)

| Thema | Entscheidung |
|-------|--------------|
| Format | SEPA `pain.001`, Sammler mit mehreren Posten |
| Einreichung | Über Bank-Provider (Baustein 5) **oder** Datei — Dateiweg immer verfügbar |
| Prüfungen | Blockierend, nicht beratend; abweichende IBAN stoppt den Lauf |
| Freigabe | Zustandsautomat mit Protokoll; Vier-Augen konfigurierbar; freigegeben = unveränderbar |
| Skonto | Fristen haben Vorrang vor Nettofälligkeiten |
| Mahnstufen | YAML-Konfiguration, wie das Regelwerk in Baustein 1 |
| Verzugszinsen | Datierter Basiszinssatz, B2B/B2C unterschieden |

## 6. Teststrategie

- `pain.001` gegen das offizielle Schema validiert, zusätzlich Golden-Test gegen eine bekannte
  Soll-Datei.
- Vorschlagslogik gegen handgerechnete Fälle: Skontofrist morgen vs. Nettofälligkeit heute,
  Teilzahlung, gesperrter Kontakt.
- Prüfstufe: abweichende IBAN, ungültige Prüfziffer, doppelt eingereichter Posten — jeweils
  Erwartung „blockiert, mit Begründung".
- Zustandsautomat: Übergänge in falscher Reihenfolge werden abgelehnt.
- Mahnstufen und Verzugszinsen gegen handgerechnete Werte, inklusive Stichtag rund um eine
  Basiszinssatz-Änderung.

## 7. Akzeptanzkriterien

1. Die Vorschlagsliste zieht Skontoposten vor und nennt den Grund je Position.
2. Eine erzeugte Sammelüberweisung ist schemakonform und wird von der Bank angenommen.
3. Ein Posten kann nicht zweimal in einen eingereichten Lauf geraten.
4. Eine vom Stammsatz abweichende IBAN blockiert den Lauf mit klarer Meldung.
5. Ein freigegebener Lauf lässt sich nicht mehr ändern, nur stornieren — mit Protokoll.
6. Ein überfälliger Debitorenposten durchläuft die konfigurierten Stufen mit korrekt berechneten
   Verzugszinsen und Gebühren.
7. Ohne Live-Bankanbindung funktioniert alles bis zur Datei.

## 8. Ausdrücklich NICHT in diesem Baustein

Lastschrifteinzug (`pain.008`) · Echtzeitüberweisung · Fremdwährungszahlungen · Liquiditätsplanung ·
gerichtliches Mahnverfahren und Inkasso-Übergabe · Zahlungsdienstleister-Anbindung.
