# Skizzen zu Spec 10c — Oberfläche: Übersicht, Einrichtung, Bedienung, Design

Text-Wireframes zur Spec [`2026-10-26-oberflaeche-einrichtung.md`](2026-10-26-oberflaeche-einrichtung.md). Desktop-Skizzen sind etwa 1440 px
breit (≈ 100 Zeichen), Handy-Skizzen 390 px (≈ 40 Zeichen). Die Beispieldaten stammen aus der
Demo-Datenbank bzw. sind erfunden. Konten sind SKR03; „Verrechnung eBay (1362)“ ist ein eigenes
Unterkonto aus der Kontenliste der Gesellschaft (A67).

Gezeigt ist der Zielstand nach P1–P3 und 10b-2 (Übersicht, Prüfschlange, Freigaben) bzw. nach
P4–P7 (Einstellungen, Benutzer, Assistent). Die Skizzen legen Aufbau, Reihenfolge und Texte fest,
nicht Maße oder Farben; maßgeblich sind die Anforderungen der Spec (in Klammern).

Stand 26.10.2026: Die Entscheidungen F1–F5 der Spec (Abschnitt 12) sind eingearbeitet. Neu bzw.
geändert sind die Skizzen 2 (Hinweise), 3a, 4a (Text), 5b (Hinweise), 5d, 6a, 6c, 6d, 7,
8 (Hinweise) und 9.

Zeichen: `[ Knopf ]` primär, `[ Knopf ]` mit `·` davor = sekundär, `Link ›` = stiller Link,
`( )`/`(•)` = Optionsfeld, `[ ]`/`[x]` = Kontrollkästchen, `▸`/`▾` = aufklappbar,
`▌` = Kennfarbe der Gesellschaft, `(12)` = Zähler, `!` = Warnsymbol mit Text,
`⌗` = Tastenkürzel-Hinweis (nur Desktop sichtbar).

---

## 1. Übersicht — Desktop (1440 px, Rolle: verwalter + buchhalter + freigeber)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ accounti    ▌GD  Galerie Demo GmbH  ›                                     Hilfe    Jan Hansen ▾  │
├──────────────────────┬───────────────────────────────────────────────────────────────────────────┤
│                      │                                                                           │
│  Übersicht           │  Guten Morgen, Jan                              Montag, 26. Oktober 2026  │
│  Prüfen         (12) │                                                                           │
│  Belege          (3) │  HEUTE ZU TUN                                                             │
│  Steuern             │  ┌─────────────────────────────────────┐ ┌─────────────────────────────┐  │
│  Auswertungen        │  │ ! Fristen                           │ │ ! Aufgaben & Rückfragen (4) │  │
│  Freigaben       (2) │  │ ! überfällig  ZM 3. Quartal         │ │ ! 1 überfällig:             │  │
│                      │  │               fällig 25.10.         │ │   Beleg fehlt – Amazon 89 € │  │
│                      │  │ OSS 3. Quartal      31.10. ( 5 T.)  │ │ 2 an Sie · 1 an Buchhaltung │  │
│                      │  │ USt-VA September    10.11. (15 T.)  │ │ Neue Rückfrage von Erika:   │  │
│                      │  │               vorbereitet           │ │   „Staples – privat?“       │  │
│  ──────────────────  │  │ Alle Fristen ›                      │ │ Alle Aufgaben ›             │  │
│  Einstellungen       │  └─────────────────────────────────────┘ └─────────────────────────────┘  │
│                      │  ┌─────────────────────────────────────┐ ┌─────────────────────────────┐  │
│                      │  │ Prüfen                         (12) │ │ Wartet auf Freigabe     (2) │  │
│                      │  │ 12 Buchungen, älteste seit 6 Tagen  │ │ Zahlungslauf 2026-14        │  │
│                      │  │ 9 davon in 3 Gruppen sofort         │ │ 4 Zahlungen · 3.212,40 €    │  │
│                      │  │   freigebbar                        │ │ Umsatzsteuer-Voranmeldung   │  │
│                      │  │ 3 Belege: Erkennung unsicher        │ │ September · 1.284,10 €      │  │
│                      │  │                                     │ │                             │  │
│                      │  │ [ Prüfen starten ]                  │ │ [ Freigaben ansehen ]       │  │
│                      │  └─────────────────────────────────────┘ └─────────────────────────────┘  │
│                      │  ┌─────────────────────────────────────┐ ┌─────────────────────────────┐  │
│                      │  │ ! Bank                              │ │ Einrichtung & Betrieb       │  │
│                      │  │ Geschäftskonto      heute 06:00     │ │ ! Letzte Sicherung vor 9    │  │
│                      │  │   Stand 25.10. · ok                 │ │   Tagen                     │  │
│                      │  │ ! Tagesgeld         vor 4 Tagen     │ │ Firmendaten: Bankverbindung │  │
│                      │  │   Zustimmung in Bank-App nötig      │ │   fehlt (für Rechnungen)    │  │
│                      │  │                                     │ │ Einrichtung fortsetzen ›    │  │
│                      │  └─────────────────────────────────────┘ └─────────────────────────────┘  │
│                      │                                                                           │
│                      │  Erledigt: Zahlungen · Forderungen · Prüfhinweise                         │
│                      │                                                                           │
│                      │  In anderen Gesellschaften:  ▌KU Kunsthandel UG – 2 zu prüfen ›           │
│                      │                                                                           │
│                      │  ▸ Kennzahlen (Oktober)                             [ Beträge verbergen ] │
│                      │                                                                           │
└──────────────────────┴───────────────────────────────────────────────────────────────────────────┘
```

Hinweise:

- Jede Zahl ist ein Link (A16).
- Die Karten sind nach Dringlichkeit sortiert (A14): zuerst die beiden mit überfälligen Einträgen
  (Fristen: ZM; Aufgaben: fehlender Beleg), dann die übrigen in der festen Reihenfolge aus A13.
  Karten mit Warnung tragen das Warnsymbol mit Text im Titel.
- Karten ohne Einträge fallen in die Zeile „Erledigt“.
- „Freigaben“ steht in der Seitenleiste, bis „Bank & Zahlungen“ und „Steuern“ eigene Seiten für
  Zahlungsläufe und USt-VA haben (A1). „Bank & Zahlungen“ und „Rechnungen & Kontakte“ fehlen, weil
  es dafür in 10c noch keine Seiten gibt (A2). „Steuern“ führt auf die Fristenliste (A120).
- Die USt-VA September ist vorbereitet und wartet auf Freigabe; deshalb steht sie in beiden
  Karten. Die Fristen der Beispiele: ZM 3. Quartal am 25.10., USt-VA September mit
  Dauerfristverlängerung am 10.11., OSS 3. Quartal am 31.10.
- „Zahlungen“, „Forderungen“ und „Kennzahlen“ gibt es erst mit 10b-2 (A13, A16).

## 2. Übersicht — Handy (390 px)

```
┌────────────────────────────────────────┐
│ ▌GD  Übersicht                  ( JH ) │
├────────────────────────────────────────┤
│ Guten Morgen, Jan                      │
│ Mo., 26.10.2026                        │
│                                        │
│ ┌────────────────────────────────────┐ │
│ │ ! Fristen                          │ │
│ │ ZM 3. Quartal · fällig 25.10.      │ │
│ │ überfällig                         │ │
│ │ OSS 3. Quartal · 31.10. (5 T.)     │ │
│ │ Alle Fristen ›                     │ │
│ └────────────────────────────────────┘ │
│ ┌────────────────────────────────────┐ │
│ │ ! Aufgaben & Rückfragen        (4) │ │
│ │ 1 überfällig · 2 an Sie            │ │
│ │ Alle Aufgaben ›                    │ │
│ └────────────────────────────────────┘ │
│ ┌────────────────────────────────────┐ │
│ │ Prüfen                        (12) │ │
│ │ 12 Buchungen · 9 sofort freigebbar │ │
│ │ ┌────────────────────────────────┐ │ │
│ │ │        Prüfen starten          │ │ │
│ │ └────────────────────────────────┘ │ │
│ └────────────────────────────────────┘ │
│ ┌────────────────────────────────────┐ │
│ │ Wartet auf Freigabe            (2) │ │
│ │ Zahlungslauf 2026-14 · 3.212,40 €  │ │
│ │ USt-VA September · 1.284,10 €      │ │
│ │ ┌────────────────────────────────┐ │ │
│ │ │       Freigaben ansehen        │ │ │
│ │ └────────────────────────────────┘ │ │
│ └────────────────────────────────────┘ │
│ (darunter: Bank, Einrichtung & Betrieb,│
│  Erledigt, andere Gesellschaften,      │
│  Kennzahlen)                           │
├────────────────────────────────────────┤
│ Übersicht  Prüfen  Belege  Freig.  Mehr│
│    ●        (12)    (3)     (2)    ≡   │
└────────────────────────────────────────┘
```

Hinweise:

- Die Kopfleiste ist ≤ 56 px hoch (A4): Kennfarbe, Kürzel und Seitentitel; „( JH )“ führt auf
  `/menue#konto` (A6).
- Dieselben Karten in derselben Reihenfolge wie auf dem Desktop, untereinander (A21).
- Die untere Leiste ist fest, „Mehr“ führt auf `/menue` (kein Skript).
- „Freig.“ steht nur mit `ZAHLUNG_FREIGEBEN` oder `STEUER_FREIGEBEN` in der Leiste (A4, F3); als
  `buchhalter` hat die Leiste vier Ziele. Ziel ist `/freigaben` (Skizze 9).
- Die Hauptaktion einer Karte geht über die volle Breite und ist ≥ 44 px hoch.

---

## 3. Prüfschlange — Desktop, Liste mit Gruppen

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ accounti    ▌GD  Galerie Demo GmbH  ›                                     Hilfe    Jan Hansen ▾  │
├──────────────────────┬───────────────────────────────────────────────────────────────────────────┤
│  Übersicht           │  Prüfen                                                                   │
│  Prüfen         (12) │  Offen (12)   Später klären (2)   Regeln                                  │
│  Belege          (3) │                                                                           │
│  …                   │  GLEICHARTIGE VORSCHLÄGE                                                  │
│                      │  ┌─────────────────────────────────────────────────────────────────────┐  │
│                      │  │ 6 × Deutsche Telekom AG   Ausgaben → Telefon (4920), 19 % Vorsteuer │  │
│                      │  │     239,94 € · nach Ihrer Regel „Telekom“                           │  │
│                      │  │                                 · Ansehen    [ Alle 6 freigeben ]   │  │
│                      │  ├─────────────────────────────────────────────────────────────────────┤  │
│                      │  │ 3 × Staples Deutschland   Ausgaben → Bürobedarf (4930), 19 % VSt.   │  │
│                      │  │     412,37 € · wie bisher bei diesem Lieferanten                    │  │
│                      │  │                                 · Ansehen    [ Alle 3 freigeben ]   │  │
│                      │  └─────────────────────────────────────────────────────────────────────┘  │
│                      │                                                                           │
│                      │  EINZELN                                    [ Durcharbeiten  ⌗ j ]        │
│                      │  ┌────┬──────────┬──────────────────────┬──────────┬─────────────────────┐│
│                      │  │[ ] │ Datum    │ Empfänger / Absender │   Betrag │ Vorschlag           ││
│                      │  ├────┼──────────┼──────────────────────┼──────────┼─────────────────────┤│
│                      │  │[ ] │ 05.04.26 │ eBay Sarl            │ + 780,25 │ Erlöse 19 % (8400)  ││
│                      │  │    │          │ EBAY MANAGED PAYM…   │          │ Sicherheit: mittel  ││
│                      │  │    │          │                      │          │ [Freigeben] · Ändern││
│                      │  ├────┼──────────┼──────────────────────┼──────────┼─────────────────────┤│
│                      │  │[ ] │ 12.04.26 │ Hahnemühle FineArt   │ − 1.204, │ Wareneingang 19 %   ││
│                      │  │    │          │ RE 2026-4471         │       90 │ (3400) · ! Betrag   ││
│                      │  │    │          │                      │          │ weicht vom Beleg ab ││
│                      │  │    │          │                      │          │ [Freigeben] · Ändern││
│                      │  └────┴──────────┴──────────────────────┴──────────┴─────────────────────┘│
│                      │                                                                           │
├──────────────────────┴───────────────────────────────────────────────────────────────────────────┤
│  2 ausgewählt · 1.985,15 €                                        · Auswahl aufheben  [Freigeben]│
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Hinweise:

- Ein Eintrag mit Warnung („Betrag weicht vom Beleg ab“) kommt nie in eine Gruppe (E13).
- Die Sammelleiste unten erscheint erst bei einer Auswahl und verdeckt nie den Fokus (A26,
  A104).
- [Alle 6 freigeben] führt auf den Bestätigungsschritt (Skizze 3a).
- Aus Platzgründen stehen Steuer und Sicherheit in der Spalte „Vorschlag“; die Steuer ist bei
  Automatikkonten Teil der Kontobezeichnung („Erlöse 19 %“), sonst steht sie im Klartext dabei
  („19 % Vorsteuer“, A22). Die Gruppen stehen über der Einzelliste (A24).
- Ohne JS gibt es statt der Sammelleiste einen Absendeknopf unter der Liste (A26).

### 3a. Bestätigungsschritt der Massenfreigabe

```
┌──────────────────────────────────────────────────────────────────┐
│ 6 Buchungen freigeben?                                           │
│ Deutsche Telekom AG → Telefon (4920), 19 % Vorsteuer             │
│ nach Ihrer Regel „Telekom“                                       │
│                                                                  │
│   10.04.26   TELEKOM MOBILFUNK APRIL                     39,99 € │
│   10.05.26   TELEKOM MOBILFUNK MAI                       39,99 € │
│   …          (4 weitere)                                         │
│                                                  Summe  239,94 € │
│                                                                  │
│ Jede Freigabe steht einzeln im Verlauf. Berichtigen geht danach  │
│ nur per Storno.                                                  │
│                                                                  │
│ [ 6 Buchungen freigeben ]      · Abbrechen                       │
└──────────────────────────────────────────────────────────────────┘
```

Hinweise:

- Der Kopf nennt Vorschlag und Herkunft (A25). Bei einer Gruppe aus KI-Vorschlägen steht dort
  „Vorschlag der KI · Sicherheit: mittel“. Solche Gruppen gibt es erst ab 3 gleichen Vorschlägen
  und nur ab der Prüfschwelle (E13, entschieden F4).
- Höchstens 100 Buchungen je Vorgang; die Freigabe gilt für alle oder keine (E13).

## 4. Prüfschlange — Desktop, Arbeitsfläche

### 4a. Ausgangszustand (drei Aktionen, kein Eingabefeld)

Beispiel ohne Beleg (Marktplatz-Auszahlung). Mit Beleg steht links die Vorschau (Bild oder
E-Rechnung in der Seite, bei PDF der eingebettete Betrachter wie in 10b-1) mit „In neuem Tab
öffnen ⌗ b“; bei PDF heißt der Knopf „PDF öffnen ⌗ b“ und steht auf jeder Breite (A33, F3).

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│  ‹ Zur Liste      3 von 12      ‹ Voriger  ⌗ k     Nächster ›  ⌗ j                     Verlauf › │
├────────────────────────────────────────────────┬─────────────────────────────────────────────────┤
│ Beleg                                          │ eBay Sarl                                       │
│ ┌────────────────────────────────────────────┐ │ + 780,25 €   Einnahme · 05.04.2026              │
│ │                                            │ │ Geschäftskonto · EBAY MANAGED PAYMENTS          │
│ │                                            │ │ AUSZAHLUNG                                      │
│ │                                            │ │                                                 │
│ │         (kein Beleg zugeordnet)            │ │ ! Kein Beleg zugeordnet. Bei Auszahlungen ist   │
│ │                                            │ │   die Marktplatz-Abrechnung der Beleg.          │
│ │  Umsatzdaten: 05.04.2026 · 780,25 €        │ │                                                 │
│ │  eBay Sarl · LU11 2233 44 …                │ │ VORSCHLAG                                       │
│ │                                            │ │ → Erlöse 19 % USt (8400)                        │
│ │                                            │ │   mit 19 % Umsatzsteuer                         │
│ │                                            │ │ Sicherheit: mittel · Vorschlag der KI           │
│ │                                            │ │ „Betrag und Text deuten auf einen Verkauf“ mehr │
│ │                                            │ │ ▸ Buchungsdetails                               │
│ │                                            │ │                                                 │
│ │                                            │ │ ┌─────────────────────────────────────────────┐ │
│ │                                            │ │ │         Passt – freigeben        ⌗ f        │ │
│ │                                            │ │ └─────────────────────────────────────────────┘ │
│ │                                            │ │ ┌─────────────────────────────────────────────┐ │
│ │                                            │ │ │ ·       Anderes Konto …          ⌗ e        │ │
│ │                                            │ │ └─────────────────────────────────────────────┘ │
│ └────────────────────────────────────────────┘ │   Später klären …  ⌗ z                          │
└────────────────────────────────────────────────┴─────────────────────────────────────────────────┘
```

Hinweise:

- Der Aktionsbereich enthält genau die drei Aktionen (A27, AK16). „Zur Liste“, „Voriger“,
  „Nächster“ und „Verlauf“ sind Navigation, „Buchungsdetails“ ist ein `<details>` (Soll, Haben,
  Netto, Steuer, Steuerschlüssel, Herkunft, Prozentwert); mit der Fachansicht ist es offen.
- „Sicherheit: mittel“ ersetzt „Confidence 62 %“ (Anhang B der Spec).

### 4b. Schritt 1 — „Welches Konto passt?“ (nach „Anderes Konto …“)

```
├────────────────────────────────────────────────┬─────────────────────────────────────────────────┤
│ (Beleg wie oben)                               │ eBay Sarl · + 780,25 € · Einnahme · 05.04.2026  │
│                                                │                                                 │
│                                                │ Welches Konto passt?                            │
│                                                │                                                 │
│                                                │ VORSCHLÄGE                                      │
│                                                │ (•) Verrechnung eBay (1362)               ⌗ 1   │
│                                                │     bisher 11 × bei eBay                        │
│                                                │ ( ) Geldtransit (1360)                    ⌗ 2   │
│                                                │     passt zum Text „AUSZAHLUNG“                 │
│                                                │ ( ) Erlöse 19 % USt (8400)                ⌗ 3   │
│                                                │     bisheriger Vorschlag                        │
│                                                │                                                 │
│                                                │ ANDERES KONTO SUCHEN                      ⌗ /   │
│                                                │ ┌──────────────────────────────┐ · Suchen       │
│                                                │ │ z. B. Porto, 4910, Telefon   │                │
│                                                │ └──────────────────────────────┘                │
│                                                │                                                 │
│                                                │ Steuer: keine (Verrechnungskonto)               │
│                                                │ ▸ Grund für den Verlauf (optional)              │
│                                                │                                                 │
│                                                │ [ Speichern  ⌗ Strg+Enter ]   · Abbrechen       │
└────────────────────────────────────────────────┴─────────────────────────────────────────────────┘
```

Hinweise:

- Die Steuerzeile ist nur Text, weil das Konto keine Wahl lässt (A29). Bei Konten mit mehreren
  Möglichkeiten steht hier eine Auswahl im Klartext („19 % Vorsteuer“, „7 % Vorsteuer“, „ohne
  Vorsteuer“, „Reverse Charge (§ 13b UStG)“).
- Die Treffer der Suche erscheinen als weitere Optionsfelder unter dem Suchfeld (htmx; ohne JS
  über „Suchen“).

### 4c. Schritt 2 — „Künftig immer so?“ (nach dem Speichern)

```
├────────────────────────────────────────────────┬─────────────────────────────────────────────────┤
│ (Beleg wie oben)                               │ ✓ Gespeichert: eBay Sarl → Verrechnung eBay     │
│                                                │   (1362). Verlauf ›                             │
│                                                │                                                 │
│                                                │ Künftig immer so?                               │
│                                                │ ┌─────────────────────────────────────────────┐ │
│                                                │ │ Wenn Absender „eBay“ (Einnahmen)            │ │
│                                                │ │ → Verrechnung eBay (1362)                   │ │
│                                                │ │                                             │ │
│                                                │ │ Hätte 14 frühere Umsätze getroffen,         │ │
│                                                │ │ 11 davon sind schon so gebucht.             │ │
│                                                │ │ ▸ Bedingung anpassen                        │ │
│                                                │ └─────────────────────────────────────────────┘ │
│                                                │                                                 │
│                                                │ [ Ja, Regel anlegen  ⌗ r ]                      │
│                                                │ · Nein, nur dieses Mal  ⌗ n                     │
│                                                │                                                 │
│                                                │ Danach: nächster Eintrag (Staples, 156,78 €)    │
└────────────────────────────────────────────────┴─────────────────────────────────────────────────┘
```

## 5. Prüfschlange — Handy (390 px)

### 5a. Liste

```
┌────────────────────────────────────────┐
│ ▌GD  Prüfen (12)                ( JH ) │
├────────────────────────────────────────┤
│ Offen (12) · Später (2) · Regeln       │
│                                        │
│ GLEICHARTIG                            │
│ ┌────────────────────────────────────┐ │
│ │ 6 × Deutsche Telekom AG            │ │
│ │ → Telefon (4920) · 19 % Vorsteuer  │ │
│ │ 239,94 € · Ihre Regel „Telekom“    │ │
│ │ ┌───────────────┐                  │ │
│ │ │Alle freigeben │   Ansehen ›      │ │
│ │ └───────────────┘                  │ │
│ └────────────────────────────────────┘ │
│                                        │
│ EINZELN                                │
│ ┌────────────────────────────────────┐ │
│ │ eBay Sarl              + 780,25 €  │ │
│ │ 05.04.2026 · Einnahme              │ │
│ │ → Erlöse 19 % USt (8400)           │ │
│ │ Sicherheit: mittel                 │ │
│ │ ┌───────────────┐ ┌──────────────┐ │ │
│ │ │  Freigeben    │ │   Ändern     │ │ │
│ │ └───────────────┘ └──────────────┘ │ │
│ └────────────────────────────────────┘ │
│ ┌────────────────────────────────────┐ │
│ │ Hahnemühle FineArt   − 1.204,90 €  │ │
│ │ ! Betrag weicht vom Beleg ab       │ │
│ │ …                                  │ │
├────────────────────────────────────────┤
│ Übersicht  Prüfen  Belege  Freig.  Mehr│
└────────────────────────────────────────┘
```

Jede Karte ist eine Tabellenzeile mit ausdrücklichen ARIA-Rollen (A111). Es gibt kein
waagrechtes Scrollen (AK1).

### 5b. Arbeitsfläche, erster Bildschirm (390 × 844, alles ohne Scrollen)

```
┌────────────────────────────────────────┐
│ ‹ Liste     3 von 12              ‹  › │
├────────────────────────────────────────┤
│  Vorschlag  │  Beleg                   │
│ ════════════                           │
│ eBay Sarl                              │
│ + 780,25 €                             │
│ Einnahme · 05.04.2026 · Geschäftskonto │
│ EBAY MANAGED PAYMENTS AUSZAHLUNG       │
│                                        │
│ ! Kein Beleg zugeordnet                │
│                                        │
│ VORSCHLAG                              │
│ → Erlöse 19 % USt (8400)               │
│   mit 19 % Umsatzsteuer                │
│ Sicherheit: mittel · Vorschlag der KI  │
│ „Betrag und Text deuten auf einen …“   │
│ ▸ Buchungsdetails                      │
│                                        │
│                                        │
├────────────────────────────────────────┤
│ ┌────────────────────────────────────┐ │
│ │        Passt – freigeben           │ │
│ └────────────────────────────────────┘ │
│ ┌────────────────┐ ┌─────────────────┐ │
│ │ Anderes Konto  │ │ Später klären   │ │
│ └────────────────┘ └─────────────────┘ │
└────────────────────────────────────────┘
```

Hinweise:

- „Vorschlag | Beleg“ ist ein Umschalter (A33). „Beleg“ zeigt ein Bild bzw. die E-Rechnung
  inline. Bei einem PDF zeigt er „PDF öffnen“ und die Eckdaten (E11 A, entschieden F3; Skizze 5d).
- Die Aktionsleiste ist unten fest. Auf der Arbeitsfläche ersetzt sie die untere
  Navigationsleiste; „‹ Liste“ führt zurück.

### 5c. Schritt 1 auf dem Handy

```
┌────────────────────────────────────────┐
│ ‹ Zurück   Anderes Konto               │
├────────────────────────────────────────┤
│ eBay Sarl · + 780,25 € · Einnahme      │
│                                        │
│ Welches Konto passt?                   │
│ ┌────────────────────────────────────┐ │
│ │ (•) Verrechnung eBay (1362)        │ │
│ │     bisher 11 × bei eBay           │ │
│ └────────────────────────────────────┘ │
│ ┌────────────────────────────────────┐ │
│ │ ( ) Geldtransit (1360)             │ │
│ │     passt zum Text „AUSZAHLUNG“    │ │
│ └────────────────────────────────────┘ │
│ ┌────────────────────────────────────┐ │
│ │ ( ) Erlöse 19 % USt (8400)         │ │
│ │     bisheriger Vorschlag           │ │
│ └────────────────────────────────────┘ │
│                                        │
│ Anderes Konto suchen                   │
│ ┌──────────────────────────┐┌────────┐ │
│ │ z. B. Porto, Telefon     ││ Suchen │ │
│ └──────────────────────────┘└────────┘ │
│                                        │
│ Steuer: keine (Verrechnungskonto)      │
├────────────────────────────────────────┤
│ ┌────────────────────────────────────┐ │
│ │             Speichern              │ │
│ └────────────────────────────────────┘ │
└────────────────────────────────────────┘
```

### 5d. Beleg-Reiter mit PDF (390 px)

```
┌────────────────────────────────────────┐
│ ‹ Liste     4 von 12              ‹  › │
├────────────────────────────────────────┤
│  Vorschlag  │  Beleg                   │
│              ════════                  │
│ Rechnung (PDF)                         │
│ Hahnemühle FineArt GmbH                │
│ Nr. RE 2026-4471 · 12.04.2026          │
│ Brutto 1.204,90 €                      │
│                                        │
│ ┌────────────────────────────────────┐ │
│ │            PDF öffnen ↗            │ │
│ └────────────────────────────────────┘ │
│ Öffnet den PDF-Betrachter Ihres Geräts.│
│                                        │
│ Eckdaten erkannt aus dem Beleg; Fehler │
│ melden Sie über „Später klären“.       │
├────────────────────────────────────────┤
│ (Aktionsleiste wie in 5b)              │
└────────────────────────────────────────┘
```

Hinweise:

- PDFs erscheinen nicht in der Seite und nicht als Seitenbild. „PDF öffnen“ öffnet das Original
  im Systembetrachter, also in der PDF-Ansicht von iOS bzw. Android (E11 A, entschieden F3).
  Eine neue Abhängigkeit gibt es dafür nicht.
- Daneben stehen die erkannten Eckdaten Aussteller, Nummer, Datum und Brutto, damit sich der
  Vorschlag meist ohne Öffnen prüfen lässt (A33, AK70).
- Der Knopf ist mindestens 44 px hoch. Ab 64rem steht zusätzlich der eingebettete Betrachter wie
  in 10b-1 (Skizze 4a).

---

## 6. Einrichtungsassistent (Desktop, vier Beispielschritte)

Für alle Schritte gilt: links die Schrittliste, rechts der Inhalt. „Hilfe“ steht wie auf allen
Seiten oben rechts (WCAG 3.2.6).

### 6a. Schritt 1 — Ihr Zugang (zweiter Faktor)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ accounti einrichten                                                                       Hilfe  │
├────────────────────────────┬─────────────────────────────────────────────────────────────────────┤
│ Schritt 1 von 7            │ Ihr Zugang                                                          │
│                            │                                                                     │
│ ✓ Willkommen               │ Benutzername (Pflicht)          Anzeigename                         │
│ ● 1 Ihr Zugang             │ ┌────────────────────────┐      ┌───────────────────────────┐       │
│   2 Ihre Firma             │ │ jan                    │      │ Jan Hansen                │       │
│   3 Steuern & Buchführung  │ └────────────────────────┘      └───────────────────────────┘       │
│   4 Bankkonto              │ Passwort (Pflicht, mindestens 12 Zeichen)                           │
│   5 Belegeingang           │ ┌────────────────────────┐  ✓ lang genug, nicht in der Sperrliste   │
│   6 Steuerberater & DATEV  │ │ ••••••••••••••••       │                                          │
│   7 Weitere Personen       │ └────────────────────────┘                                          │
│   Fertig                   │                                                                     │
│                            │ ZWEITER FAKTOR                                                      │
│                            │ 1. Öffnen Sie Ihre Authenticator-App und scannen Sie den Code.      │
│                            │ ┌──────────────────┐   Kein Scannen möglich? Schlüssel eingeben:    │
│                            │ │ ▄▄▄▄▄ ▄ ▄▄ ▄▄▄▄▄ │   BFU5 BFVZ SQFU ME5K OGEB HXIL C3XE 6WN3      │
│                            │ │ █   █ ▀█▄▀ █   █ │   · Schlüssel kopieren                         │
│                            │ │ █▄▄▄█ ▄▀█▄ █▄▄▄█ │                                                │
│                            │ │ ▄▄▄ ▄▄█▀▄▀▄ ▄▄▄  │   Auf diesem Handy?                            │
│                            │ │ █▄▄▄█ ▀▄█▀ ▄▀█▄▀ │   In Authenticator-App öffnen ›                │
│                            │ └──────────────────┘                                                │
│                            │ 2. Code aus der App (6 Ziffern)                                     │
│                            │ ┌──────────────┐                                                    │
│                            │ │ 482 913      │   Einfügen und Leerzeichen sind erlaubt.           │
│                            │ └──────────────┘                                                    │
│                            │                                                                     │
│                            │ ┌─ Hinweis ─────────────────────────────────────────────────────┐   │
│                            │ │ i  Sie erhalten alle Rollen: verwalten, buchen, freigeben.    │   │
│                            │ │    Mitarbeitende laden Sie in Schritt 7 mit eigenen Rollen    │   │
│                            │ │    ein. Vier-Augen-Freigaben brauchen eine zweite Person mit  │   │
│                            │ │    Freigaberecht.                                             │   │
│                            │ └───────────────────────────────────────────────────────────────┘   │
│                            │                                                                     │
│                            │ [ Weiter ]                                                          │
└────────────────────────────┴─────────────────────────────────────────────────────────────────────┘
```

Hinweise:

- Mit „Weiter“ prüft der Server den Code aus der App und legt erst dann den Benutzer an, in einer
  Transaktion mit Rollen, Faktor und Wiederherstellungscodes (A72). Bricht jemand vorher ab,
  entsteht kein Benutzer, und der Einrichtungscode aus Schritt 0 gilt weiter.
- Danach folgen auf eigener Seite die Wiederherstellungscodes: anzeigen, „als Textdatei
  speichern“, „drucken“ und `[ ] Ich habe die Codes sicher abgelegt`. Erst danach geht es zu
  Schritt 2. Wer hier abbricht, meldet sich später normal an und erzeugt neue Codes unter „Mein
  Konto“ (A87).
- Die Seiten sind `no-store`, der QR-Code ist ein SVG-`data:`-Bild (E10).
- Der erste Benutzer bekommt alle Rollen (`verwalter`, `freigeber`, `buchhalter`; A78,
  entschieden F2). Die Frage „Arbeiten Sie allein?“ aus dem ersten Entwurf entfällt; der Hinweis
  verweist auf Schritt 7 (Skizze 6d).
- Auf dem Handy stehen die Felder untereinander, der QR-Code entfällt zugunsten von „In
  Authenticator-App öffnen“ und dem Schlüssel als Text; „Weiter“ liegt in der festen
  Aktionsleiste (A76).

### 6b. Schritt 3 — Steuern & Buchführung (mit Vorschlägen)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ accounti einrichten · ▌GD Galerie Demo GmbH                                               Hilfe  │
├────────────────────────────┬─────────────────────────────────────────────────────────────────────┤
│ Schritt 3 von 7            │ Steuern & Buchführung                                               │
│                            │                                                                     │
│ ✓ Willkommen               │ ┌─ Vorschlag ─────────────────────────────────────────────────────┐ │
│ ✓ 1 Ihr Zugang             │ │ i  Sie haben „GmbH“ gewählt. Eine GmbH muss Bücher führen und   │ │
│ ✓ 2 Ihre Firma             │ │    bilanzieren (§§ 238, 242 HGB). Bitte stimmen Sie Kontenrahmen│ │
│ ● 3 Steuern & Buchführung  │ │    und Zeiträume mit Ihrem Steuerberater ab – accounti berät    │ │
│   4 Bankkonto              │ │    nicht.                                                       │ │
│   5 Belegeingang           │ └─────────────────────────────────────────────────────────────────┘ │
│   6 Steuerberater & DATEV  │                                                                     │
│   7 Weitere Personen       │ Gewinnermittlung                                                    │
│   Fertig                   │ Bilanz – für GmbH vorgeschrieben, keine Wahl (§§ 238, 242 HGB)      │
│                            │                                                                     │
│                            │ Kontenrahmen (Pflicht, nach der ersten Buchung nicht mehr änderbar) │
│                            │ (•) SKR03 – am weitesten verbreitet                                 │
│                            │ ( ) SKR04 – gegliedert wie die Bilanz                               │
│                            │     Ihr Steuerberater nutzt einen bestimmten? Den wählen.           │
│                            │                                                                     │
│                            │ Wirtschaftsjahr beginnt am (Pflicht)                                │
│                            │ (•) 1. Januar (Kalenderjahr)   ( ) anderem Tag: [TT.MM.]            │
│                            │                                                                     │
│                            │ Bundesland            Steuernummer                                  │
│                            │ ┌─────────────────┐   ┌──────────────────┐                          │
│                            │ │ Bayern        ▾ │   │ 143/123/45678    │  ✓ Format passt          │
│                            │ └─────────────────┘   └──────────────────┘  ELSTER: 9143012345678   │
│                            │ USt-IdNr.                                                           │
│                            │ ┌──────────────────┐                                                │
│                            │ │ DE123456789      │  ! Prüfziffer stimmt nicht – bitte prüfen      │
│                            │ └──────────────────┘    · jetzt online prüfen (nur auf Klick)       │
│                            │                                                                     │
│                            │ Umsatzsteuer-Voranmeldung                                           │
│                            │ Wie hoch war die Umsatzsteuer im Vorjahr ungefähr?                  │
│                            │ ( ) bis 2.000 €  ( ) bis 9.000 €  (•) über 9.000 €  ( ) Gründung    │
│                            │ → Vorschlag: monatlich (§ 18 Abs. 2 UStG). Ihr Bescheid geht vor.   │
│                            │ [x] Dauerfristverlängerung beantragt (Frist + 1 Monat, Sonder-      │
│                            │     vorauszahlung 1/11)                                             │
│                            │ [ ] OSS-registriert (Fernverkäufe an EU-Privatkunden > 10.000 €)    │
│                            │     Ihre Marktplatzdaten 2026 bisher: 7.840 € EU-Fernverkäufe       │
│                            │                                                                     │
│                            │ [ Weiter ]    · Später ergänzen    · Zurück                         │
└────────────────────────────┴─────────────────────────────────────────────────────────────────────┘
```

Hinweise:

- „Später ergänzen“ speichert, was da ist, als unvollständig, und setzt die fehlenden Angaben auf
  die Checkliste der Übersicht (A76, A79).
- Die Steuernummer wird je Bundesland offline geprüft; dazu wird die 13-stellige ELSTER-Form
  angezeigt. Die USt-IdNr. ist offline nach dem Prüfzifferverfahren geprüft (`DE123456789` hat
  die falsche Prüfziffer, richtig wäre `…788`). Die Werte im Beispiel sind erfunden.
- Nicht gezeigt, weiter unten im Schritt: Finanzamt (optional), die Fragen nach
  Kleinunternehmerregelung und Ist-Versteuerung mit dem Hinweis, dass accounti beides noch nicht
  trägt (Nicht-Ziele der Spec), und „Zurück“ ohne Datenverlust (A76).
- Die Gewinnermittlung ist hier Text, weil die Rechtsform sie festlegt; bei Einzelunternehmen und
  e. K. steht dort eine Wahl mit Hinweis (A74).
- Gespeichert wird in `buchhaltung`, `abschluss`, `elster`, `mandant` und
  `datev.wirtschaftsjahr_beginn` (A73).

### 6c. Fertig — Was jetzt?

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ accounti einrichten · ▌GD Galerie Demo GmbH                                               Hilfe  │
├────────────────────────────┬─────────────────────────────────────────────────────────────────────┤
│ Fertig                     │ accounti ist eingerichtet                                           │
│                            │                                                                     │
│ ✓ Willkommen               │ ERLEDIGT                                                            │
│ ✓ 1 Ihr Zugang             │ ✓ Zugang mit zweitem Faktor für Jan Hansen                          │
│ ✓ 2 Ihre Firma             │ ✓ Galerie Demo GmbH · Bilanz · SKR03 · Wirtschaftsjahr = Kalender-  │
│ ✓ 3 Steuern & Buchführung  │   jahr · USt-VA monatlich mit Dauerfristverlängerung                │
│ ✓ 4 Bankkonto              │ ✓ Geschäftskonto DE89 3704 … 3000 → Bank (1200), Import per Datei   │
│                            │   auch auf Rechnungen und als Auftraggeber für Zahlungsläufe        │
│ – 5 Belegeingang  später   │                                                                     │
│ – 6 Steuerberater später   │ NOCH OFFEN (steht auch auf Ihrer Übersicht)                         │
│ – 7 Weitere Pers. später   │ ! E-Mail für Rechnungen fehlt – nötig für Ausgangsrechnungen        │
│ ● Fertig                   │ · Belegeingang per E-Mail-Postfach einrichten       Einrichten ›    │
│                            │ · DATEV-Berater- und Mandantennummer                Einrichten ›    │
│                            │ · Weitere Personen einladen (empfohlen)             Einladen ›      │
│                            │                                                                     │
│                            │ WAS JETZT?                                                          │
│                            │ 1. Kontoauszug importieren (CSV, MT940, CAMT)       Importieren ›   │
│                            │ 2. Ersten Beleg hochladen – auch per Handy-Kamera   Hochladen ›     │
│                            │ 3. Vorschläge prüfen, sobald accounti kontiert hat  Prüfen ›        │
│                            │ 4. Verfahrensdokumentation erzeugen (GoBD)          Erzeugen ›      │
│                            │ 5. Sicherung einrichten – Sache des Betreibers:                     │
│                            │    accounti sicherung erstellen (siehe Betriebsdoku) Anleitung ›    │
│                            │                                                                     │
│                            │ [ Zur Übersicht ]                                                   │
└────────────────────────────┴─────────────────────────────────────────────────────────────────────┘
```

Hinweise:

- „Willkommen“ und „Fertig“ zählen in „Schritt n von 7“ nicht mit (A76).
- Mit „später“ übersprungene Schritte erscheinen hier und als Checkliste auf der Übersichtskarte
  „Einrichtung & Betrieb“, bis sie erledigt oder ausgeblendet sind (A79).
- Die Bankverbindung wurde in Schritt 4 einmal eingegeben und für Rechnungen und Zahlungsläufe
  übernommen (A73, WCAG 3.3.7).
- „Weitere Personen einladen“ ist empfohlen, weil Mitarbeitende mit eigenem Zugang arbeiten
  (F2, A73). Sobald zwei Personen freigeben dürfen, kommt der empfohlene Punkt „Vier-Augen für
  Steuermeldungen einschalten?“ dazu (A79, A125).

### 6d. Schritt 7 — Weitere Personen (Einladung)

Im Ablauf zwischen Schritt 6 und „Fertig“ (6c).

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ accounti einrichten · ▌GD Galerie Demo GmbH                                               Hilfe  │
├────────────────────────────┬─────────────────────────────────────────────────────────────────────┤
│ Schritt 7 von 7            │ Weitere Personen (empfohlen)                                        │
│                            │                                                                     │
│ ✓ Willkommen               │ Arbeiten Mitarbeitende mit accounti? Laden Sie sie ein. Jede Person │
│ ✓ 1 Ihr Zugang             │ setzt Passwort und zweiten Faktor selbst.                           │
│ ✓ 2 Ihre Firma             │                                                                     │
│ ✓ 3 Steuern & Buchführung  │ Benutzername (Pflicht)          Anzeigename                         │
│ ✓ 4 Bankkonto              │ ┌────────────────────────┐      ┌───────────────────────────┐       │
│ – 5 Belegeingang  später   │ │ tom                    │      │ Tom Beispiel              │       │
│ ✓ 6 Steuerberater & DATEV  │ └────────────────────────┘      └───────────────────────────┘       │
│ ● 7 Weitere Personen       │                                                                     │
│   Fertig                   │ Rollen in Galerie Demo GmbH                                         │
│                            │ [x] Buchhalter – buchen und korrigieren, Belege einliefern,         │
│                            │     Läufe starten, Buchungen freigeben                              │
│                            │ [ ] Freigeber – Buchungen, Zahlungsläufe und Steuermeldungen        │
│                            │     freigeben                                                       │
│                            │ [ ] Verwalter – Benutzer und Einstellungen verwalten                │
│                            │ [ ] Betrachter – nur lesen                                          │
│                            │                                                                     │
│                            │ ┌─ Hinweis ─────────────────────────────────────────────────────┐   │
│                            │ │ i  Vier-Augen-Prinzip: Zahlungsläufe und Steuermeldungen      │   │
│                            │ │    lassen sich so einstellen, dass zwei Personen freigeben.   │   │
│                            │ │    Das setzt eine zweite Person mit der Rolle „Freigeber“     │   │
│                            │ │    voraus. Ab Werk ist es aus; einstellbar unter Firma &      │   │
│                            │ │    Steuern bzw. Bank & Zahlungen.                             │   │
│                            │ └───────────────────────────────────────────────────────────────┘   │
│                            │                                                                     │
│                            │ [ Einladung erstellen ]    · Später ergänzen    · Zurück            │
│                            │                                                                     │
│                            │ EINGELADEN                                                          │
│                            │ Erika Muster (erika) · Buchhalter · Link gültig bis 29.10., 12:40   │
│                            │   · Link kopieren    · Per E-Mail senden    · Zurückziehen          │
└────────────────────────────┴─────────────────────────────────────────────────────────────────────┘
```

Hinweise:

- Mitarbeitende arbeiten mit eigenem Zugang (F2). Die Einladung ist ein Link (E9): einmalig,
  72 h gültig, an Benutzername und Rollen gebunden. Passwort und zweiten Faktor setzt die Person
  selbst. „Per E-Mail senden“ erscheint nur, wenn der Versand eingerichtet ist (A82).
- Die Rollen sind getrennt: Vorbelegt ist nur „Buchhalter“, „Freigeber“ und „Verwalter“ nie. Jede
  Rolle nennt ihre Rechte im Klartext. Wer „Freigeber“ oder „Verwalter“ bekommt, wird allen
  Verwaltern und Freigebern gemeldet (A60, A82).
- Eine Rolle für den Steuerberater gibt es nicht (F2). Er bekommt die Daten über DATEV (Schritt 6).
- Der Hinweis erklärt das Vier-Augen-Prinzip und seine Voraussetzung, schaltet aber nichts ein
  (A125). Sobald zwei Personen freigeben dürfen, steht die Empfehlung auf der Checkliste (A79).
- Bei mehreren Gesellschaften gibt es je Gesellschaft eine Rollengruppe.

---

## 7. Einstellungsseite „Firma & Steuern“ (Desktop)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ accounti    ▌GD  Galerie Demo GmbH  ›                                     Hilfe    Jan Hansen ▾  │
├──────────────────────┬───────────────────────────────────────────────────────────────────────────┤
│  Übersicht           │  Einstellungen › Firma & Steuern                                          │
│  Prüfen         (12) │                                                                           │
│  …                   │  ┌────────────────────────┐  FIRMENDATEN                                  │
│  ──────────────────  │  │ ● Firmendaten          │  Quelle: Datenbank, Version 4 vom 21.10.2026, │
│  Einstellungen       │  │   Steuern & Meldungen  │  Jan Hansen · Verlauf ›                       │
│                      │  │   Buchhaltung        ! │                                               │
│                      │  │   Abschluss            │  Name (Pflicht)                               │
│                      │  │   Anlagen  (Experte)   │  ┌────────────────────────────────────────┐   │
│                      │  │   USt-IdNr.-Prüfung    │  │ Galerie Demo GmbH                      │   │
│                      │  └────────────────────────┘  └────────────────────────────────────────┘   │
│                      │                              Rechtsform          Kennfarbe                │
│                      │                              ┌──────────────┐    (•)▌ ( )▌ ( )▌ ( )▌ …    │
│                      │                              │ GmbH       ▾ │                             │
│                      │                              └──────────────┘                             │
│                      │                              Straße und Nr.                               │
│                      │                              ┌────────────────────────────────────────┐   │
│                      │                              │ Musterstraße 1                         │   │
│                      │                              └────────────────────────────────────────┘   │
│                      │                              PLZ          Ort                             │
│                      │                              ┌────────┐   ┌───────────────────────────┐   │
│                      │                              │ 12345  │   │ Musterstadt               │   │
│                      │                              └────────┘   └───────────────────────────┘   │
│                      │                              E-Mail für Rechnungen (BT-34)                │
│                      │                              ┌────────────────────────────────────────┐   │
│                      │                              │ rechnung@meine-firma.example           │   │
│                      │                              └────────────────────────────────────────┘   │
│                      │                              … Ansprechpartner, Rechnungsnummern,         │
│                      │                                Zahlungsziel, Bankverbindung               │
│                      │                              [ Firmendaten speichern ]                    │
│                      │                                                                           │
│                      │  STEUERN & MELDUNGEN                                                      │
│                      │  Quelle: `elster` aus Datei config/accounti.yaml (noch nicht im Browser   │
│                      │  geändert); `mandant` aus Datenbank, Version 4 · Verlauf ›                │
│                      │  ┌─ Achtung ────────────────────────────────────────────────────────────┐ │
│                      │  │ ! Steuerrelevant: Änderungen brauchen einen Grund und den Code aus   │ │
│                      │  │   Ihrer Authenticator-App (danach 10 Minuten ohne erneuten Code).    │ │
│                      │  └──────────────────────────────────────────────────────────────────────┘ │
│                      │  Voranmeldungszeitraum                                                    │
│                      │   2026  monatlich      gesperrt – USt-VA Januar bis August übermittelt    │
│                      │   ab 2027 [ vierteljährlich ▾ ]   · weiteres Jahr hinzufügen              │
│                      │  Dauerfristverlängerung   2026 [x]   ab 2027 [x]                          │
│                      │  OSS-registriert          ab 1. Quartal 2027 [ ]                          │
│                      │  Bundesland [ Bayern ▾ ]  Steuernummer [ 143/123/45678 ]  ✓ Format passt  │
│                      │  USt-IdNr.  [ DE123456788 ]  ✓ Prüfziffer passt   · online prüfen         │
│                      │  Finanzamt  [ Finanzamt München                       ]                   │
│                      │  Vier-Augen für Steuermeldungen  [ ] aus (Voreinstellung)                 │
│                      │    USt-VA und Dauerfristantrag brauchen dann zwei Freigaben verschiedener │
│                      │    Personen. Setzt zwei Personen mit Freigaberecht voraus – derzeit: 1.   │
│                      │    · Mitarbeitende einladen ›                                             │
│                      │  ERiC-Bibliothek, Zertifikat: vom Betreiber in config/accounti.yaml       │
│                      │    festgelegt (/opt/eric/lib/…) – hier nur lesbar                         │
│                      │                                                                           │
│                      │  Grund der Änderung (Pflicht)                                             │
│                      │  [ Bescheid des Finanzamts vom 12.10.2026: ab 2027 vierteljährlich   ]    │
│                      │  Code aus der Authenticator-App (Pflicht)  [ ______ ]                     │
│                      │  [ Steuern & Meldungen speichern ]                                        │
│                      │                                                                           │
│                      │  BUCHHALTUNG                                                              │
│                      │  ! Hinweis zur Datei: „kontenrahmen“ steht dort unter „mandant“ und wird  │
│                      │    so nicht gelesen (N1). Wirksam ist SKR03, derselbe Wert.               │
│                      │    Gegenüberstellung › · Datei-Stand übernehmen ›                         │
│                      │  Kontenrahmen  SKR03 – gesperrt, es gibt bereits Buchungen                │
│                      │  Wirtschaftsjahr beginnt am 01.01. – gesperrt, es gibt bereits Buchungen  │
│                      │  …                                                                        │
└──────────────────────┴───────────────────────────────────────────────────────────────────────────┘
```

Hinweise:

- **Speichern je Formulargruppe:** Jede Gruppe (Firmendaten, Steuern & Meldungen, Buchhaltung …)
  hat ihren eigenen Knopf (A56). Die Versionen aller berührten Abschnitte gehen als versteckte
  Felder mit; „Steuern & Meldungen“ schreibt `mandant` und `elster` in einer Transaktion und
  scheitert ganz, wenn einer der beiden inzwischen geändert wurde (A45).
- **Herkunft:** steht über jeder Gruppe, je Abschnitt (A43).
- **Bestätigung:** Grund und Code nur bei K2-Feldern (Anhang A der Spec). Im Verwaltungsmodus,
  also 10 Minuten nach einem Code, entfällt das Codefeld (A59).
- **Betriebswerte:** nur lesbar, mit Hinweis auf die Datei (A42).
- **Periodenwerte:** Jahr für Jahr. Ein Jahr mit übermittelter USt-VA ist gesperrt (A46, E3).
- **Eine Steuernummer:** Das Feld schreibt `mandant.steuernummer`; eine abweichende
  `elster.steuernummer` erschiene als Warnung (A122).
- **Vier-Augen für Steuermeldungen** (`elster.vier_augen`, A125, entschieden F2): Voreinstellung
  aus. Mit nur einer freigabeberechtigten Person lässt sich der Schalter nicht einschalten; die
  Seite sagt, warum, und verlinkt die Einladung. Einschalten ist K2. Ausschalten bei aktivem
  Schalter wird ein Antrag an eine zweite Person (K3). Das gilt ebenso für das Senken der
  KI-Schwelle.
- **Nebenbefund N1:** erscheint als Hinweis zur Datei im Abschnitt Buchhaltung.
- **Schmale Bildschirme:** Die Unternavigation links wird zur Liste oben. Die Felder stehen
  untereinander, jede Gruppe hat ihren Speichern-Knopf in voller Breite.

---

## 8. Seite „Mehr“ — Handy (390 px, `/menue`)

Ergänzend zu E14 und A4: das Ziel von „Mehr“ in der unteren Leiste und des Benutzersymbols.

```
┌────────────────────────────────────────┐
│ ▌GD  Mehr                       ( JH ) │
├────────────────────────────────────────┤
│ BEREICHE                               │
│ Übersicht                            › │
│ Prüfen                          (12) › │
│ Belege                           (3) › │
│ Steuern                              › │
│ Auswertungen                         › │
│ Freigaben                        (2) › │
│ Aufgaben                         (4) › │
│ Einstellungen                        › │
│                                        │
│ GESELLSCHAFT                           │
│ ▌GD Galerie Demo GmbH        (aktiv)   │
│ ▌KU Kunsthandel UG    2 zu prüfen  ›   │
│                                        │
│ MEIN KONTO (Jan Hansen)                │
│ Sprache · Darstellung · Fachansicht  › │
│ Hilfe                                › │
│ Abmelden                             › │
├────────────────────────────────────────┤
│ Übersicht  Prüfen  Belege  Freig.  Mehr│
│                                     ●  │
└────────────────────────────────────────┘
```

Hinweise:

- Eine gewöhnliche Seite ohne Skript und ohne Fokusfalle (E14); jeder Eintrag ist ein Link mit
  mindestens 44 px Höhe (A106).
- Der Wechsel der Gesellschaft ist ein Formular mit CSRF (A5); „Abmelden“ ebenso.
- „Einstellungen“ erscheint nur mit `VERWALTEN`, „Freigaben“ nur mit `ZAHLUNG_FREIGEBEN` oder
  `STEUER_FREIGEBEN` (A2, A4).

---

## 9. Freigaben — Handy (390 px, Rolle: verwalter + buchhalter + freigeber)

Neu nach F3: Zahlungsläufe und USt-VA lassen sich unterwegs freigeben (A126).

```
┌────────────────────────────────────────┐
│ ▌GD  Freigaben (2)              ( JH ) │
├────────────────────────────────────────┤
│ ┌────────────────────────────────────┐ │
│ │ Zahlungslauf 2026-14               │ │
│ │ 4 Zahlungen · 3.212,40 €           │ │
│ │ Ausführung 28.10.2026              │ │
│ │ angelegt von Erika Muster          │ │
│ │ ▸ Zahlungen ansehen (4)            │ │
│ │                                    │ │
│ │ Code aus Ihrer Authenticator-App   │ │
│ │ ┌────────────────────────────────┐ │ │
│ │ │                                │ │ │
│ │ └────────────────────────────────┘ │ │
│ │ ┌────────────────────────────────┐ │ │
│ │ │     Zahlungslauf freigeben     │ │ │
│ │ └────────────────────────────────┘ │ │
│ └────────────────────────────────────┘ │
│ ┌────────────────────────────────────┐ │
│ │ Umsatzsteuer-Voranmeldung          │ │
│ │ September 2026                     │ │
│ │ Zahllast 1.284,10 €                │ │
│ │ Frist 10.11. (15 T.)               │ │
│ │ Prüfung: keine Befunde             │ │
│ │ ▸ Kennziffern ansehen              │ │
│ │ (Code und Knopf wie oben)          │ │
│ │ Anderer Zeitraum …                 │ │
│ └────────────────────────────────────┘ │
├────────────────────────────────────────┤
│ Übersicht  Prüfen  Belege  Freig.  Mehr│
│                              ●         │
└────────────────────────────────────────┘
```

### 9a. Zahlungen aufgeklappt

```
│ ┌────────────────────────────────────┐ │
│ │ ▾ Zahlungen (4)                    │ │
│ │ Hahnemühle FineArt GmbH            │ │
│ │ DE89 3704 0044 0532 0130 00        │ │
│ │ RE 2026-4471            1.204,90 € │ │
│ │ ─────────────────────────────────  │ │
│ │ Staples Deutschland GmbH           │ │
│ │ DE44 5001 0517 5407 3249 31        │ │
│ │ 10-88231                  412,37 € │ │
│ │ … (2 weitere)                      │ │
│ └────────────────────────────────────┘ │
```

Hinweise:

- Zusammenfassung, Codefeld und Knopf der ersten Karte liegen im ersten Bildschirm; der Knopf
  geht über die volle Breite und ist ≥ 44 px hoch (A126, AK101).
- Freigegeben wird genau der angezeigte Inhalt: Zahlungen und Kennziffern lassen sich vorher
  aufklappen (`<details>`, ohne Skript). Hat sich der Inhalt seit der Anzeige geändert, gibt es
  409 mit Meldung und keine Freigabe.
- Die USt-VA-Karten kommen aus dem Fristenkalender; der Zeitraum wird gewählt, nicht getippt.
  „Anderer Zeitraum …“ bleibt für Nachmeldungen.
- Mit Vier-Augen (`zahlung.vier_augen` bzw. `elster.vier_augen`) steht nach der ersten Freigabe
  „wartet auf eine zweite Person · freigegeben von Erika Muster“ statt Codefeld und Knopf (A125).
- Jede Freigabe verlangt einen frischen Code (10a, E6); der Verwaltungsmodus gilt hier nicht.
- Ohne Freigaberecht fehlt „Freigaben“ in der unteren Leiste (A4). Wer die Seite trotzdem
  aufruft (Recht `LESEN`), sieht die Karten ohne Codefeld und Knopf.
- Die IBAN steht in der aufgeklappten Liste vollständig, damit sich ein geänderter Empfänger
  erkennen lässt. Alle Werte sind erfunden.

