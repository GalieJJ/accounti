# Spec: Integrationen & Export

- **Status:** Entwurf (2026-08-10)
- **Baustein:** 11 von 12 (siehe [Bauplan](../bauplan.md))
- **Ziel-Branch:** `feat/integrationen-export`

## 1. Kontext

accounti exportiert heute einen DATEV-Buchungsstapel im EXTF-Format, formatgeprüft gegen echte
Dateien. Das ist die halbe Übergabe: Ohne Debitoren- und Kreditorenstammdaten sind die
Personenkonten aus Baustein 4 leere Nummern, und ohne Belegbilder muss der Empfänger die Belege
weiterhin getrennt bekommen.

Auf der Eingangsseite fehlt der gesamte Geschäftsverkehr, der nicht über das Bankkonto sichtbar
wird. Bei einem Händler ist das die Mehrheit der Vorgänge: Marktplätze rechnen mit Gebühren,
Erstattungen und Einbehalten ab und überweisen nur den Saldo. Wer nur die Auszahlung bucht,
verliert Erlöse, Gebühren und — bei Verkäufen ins EU-Ausland — die Grundlage für die OSS-Meldung.

Die Zielsysteme, mit denen der Erlösstrang zu tun hat, kennt `models/TransaktionQuelle` bereits:
`JTL_WAWI`, `AMAZON`, `EBAY`, `SHOPIFY`, `PAYPAL`. Importer dafür gibt es noch nicht.

## 2. Ziel

> Erlösdaten kommen vollständig und mit Bestimmungsland ins System, statt als Saldo auf dem
> Bankkonto. Die Übergabe an DATEV umfasst Buchungen, Stammdaten, Belege und Kontoauszüge.

## 3. Aufbau

```
   EINGANG                                   AUSGANG
   ───────                                   ───────
   ERP / Warenwirtschaft ┐              ┌── DATEV Buchungsstapel   (vorhanden)
   Marktplätze           ├── Importer ──┤    Debitoren/Kreditoren  (neu)
   Zahlungsdienstleister ┘      │       │    Belegbilder           (neu)
                                │       └── Kontoauszüge           (neu)
                                ▼
                    Transaktion + Bestimmungsland
                                │                    ┌── CSV / JSON      (vorhanden)
                                ▼                    ├── Prüfungsdaten-  (neu)
                    Klassifikation (Baustein 1)      │   überlassung
                                │                    └── REST-API        (neu)
                                ▼
                    Steuer (steuer/, vorhanden)
                    Inland / OSS / ig. Lieferung / Ausfuhr
```

Der entscheidende Punkt ist das **Bestimmungsland**. Es steht in den Marktplatzdaten und nirgends
sonst — auf dem Bankkonto ist es unwiederbringlich verloren. Ohne es kann `steuer/oss.py` seine
Arbeit nicht tun, und die Schwellenwertprüfung läuft ins Leere.

## 4. Komponenten & Arbeitspakete

### 4.1 `importers/jtl.py` — Warenwirtschaft *(neu)*

Rechnungen, Gutschriften, Zahlungen und Stornos aus der Datenbank der Warenwirtschaft. Mit
Lieferadresse, USt-IdNr. des Kunden und Steuersatz je Position. Erzeugt Ausgangsrechnungen als
Belege (Baustein 3) und offene Posten (Baustein 4), keine reinen Zahlbeträge.

Abgrenzung: accounti liest aus dem ERP, es schreibt nicht zurück.

### 4.2 `importers/amazon.py` — Abrechnungsberichte *(neu)*

Ein Abrechnungszeitraum enthält Bestellungen, Erstattungen, Gebühren, Werbekosten, Einbehalte und
Ausgleichsposten. Alle Bestandteile werden einzeln gebucht; die Auszahlung ist am Ende nur die
Differenz, die gegen den Kontoumsatz abgeglichen wird. Stimmt die Summe der Einzelposten nicht mit
der Auszahlung überein, ist das ein Befund für Baustein 7 — keine Rundungsdifferenz, die
verschwindet.

Marktplätze der Länder aus der README-Übersicht, Bestimmungsland je Bestellung, Zuordnung zu den
OSS-Erlöskonten, die `steuer/umsatzsteuer.py` bereits kennt.

### 4.3 `importers/ebay.py`, `importers/paypal.py`, `importers/shopify.py` *(neu)*

Gleiches Muster: Bruttoerlös, Gebühren und Erstattungen getrennt, Bestimmungsland mitführen,
Auszahlung als Abgleichspunkt gegen die Bank. PayPal ist dabei ein eigenes Konto mit eigenem Saldo,
kein Zahlungsweg — es wird geführt wie ein Bankkonto.

### 4.4 `export/datev_stammdaten.py` *(neu)*

Debitoren und Kreditoren im EXTF-Stammdatenformat: Konto, Name, Anschrift, USt-IdNr.,
Bankverbindung, Zahlungsbedingungen. Quelle ist `kontakte/` aus Baustein 4.

### 4.5 `export/datev_belege.py` *(neu)*

Belegbilder mit der Verknüpfung zur zugehörigen Buchung, sodass sie beim Empfänger am Buchungssatz
hängen und nicht als loser Ordner ankommen. Quelle ist das Belegarchiv aus Baustein 2.

### 4.6 `export/kontoauszuege.py` *(neu)*

Kontoauszüge als eigenständiger Export, mit Saldenverlauf und lückenloser Auszugsnummerierung —
die Vollständigkeitsprüfung aus Baustein 7 hängt daran.

### 4.7 `export/pruefungsdaten.py` *(neu)*

Datenüberlassung für die Betriebsprüfung: Buchungen, Stammdaten, Journal und Belegverweise in
maschinell auswertbarer Form mit Beschreibungsdatei. In Baustein 7 bewusst ausgeklammert und hier
nachgeholt.

### 4.8 `api/v1/` — REST-Schnittstelle *(neu)*

Für Drittsysteme: Belege einliefern, Buchungen und offene Posten abfragen, Auswertungen ziehen,
Läufe anstoßen. Authentifizierung über Token mit Geltungsbereich, Rollen aus Baustein 10.
OpenAPI-Beschreibung fällt bei FastAPI ohnehin an.

### 4.9 Beleg-Connectoren *(Erweiterung Baustein 2)*

Der Kanal `connector` aus Baustein 2 bekommt hier konkrete Anbindungen an Belegsammeldienste und
Portale, die Rechnungen automatisch einsammeln.

### 4.10 CLI

```bash
accounti import jtl --von 2026-08-01 --bis 2026-08-31
accounti import amazon ./abrechnung.csv --markt DE
accounti import paypal ./umsaetze.csv
accounti export datev --period 2026-08 --berater 23426 --mandant 40005   # vorhanden
accounti export stammdaten --period 2026-08
accounti export belege --period 2026-08 --ausgabe ./belege-08.zip
accounti export kontoauszuege --period 2026-08
accounti export pruefungsdaten --jahr 2025
```

## 5. Tech-Entscheidungen (fix)

| Thema | Entscheidung |
|-------|--------------|
| Marktplätze | Alle Bestandteile einzeln buchen, Auszahlung ist nur der Abgleichspunkt |
| Bestimmungsland | Pflichtfeld aus Marktplatzdaten; ohne es keine korrekte OSS-Behandlung |
| Differenzen | Abweichung zwischen Einzelposten und Auszahlung ist ein Befund, kein Rundungsrest |
| ERP | Nur lesend |
| PayPal | Eigenes Konto mit Saldo, nicht bloß ein Zahlungsweg |
| DATEV | Buchungen, Stammdaten, Belege, Kontoauszüge — Belege mit Buchungsverknüpfung |
| API | Token mit Geltungsbereich, Rollen aus Baustein 10, OpenAPI aus FastAPI |

## 6. Teststrategie

- Anonymisierte Abrechnungsberichte je Marktplatz als Fixtures, inklusive Erstattung, Gebühr,
  Einbehalt und Währungsumrechnung.
- Summenprobe: Einzelposten eines Abrechnungszeitraums ergeben exakt die Auszahlung.
- OSS-Zuordnung über mehrere Bestimmungsländer gegen handgerechnete Sollwerte, unter Nutzung der
  vorhandenen Tests in `tests/test_steuer.py`.
- Stammdaten- und Belegexport als Golden-Tests gegen anonymisierte Echt-Dateien, wie beim
  bestehenden Buchungsstapel.
- API: Berechtigungsmatrix je Token-Geltungsbereich.

## 7. Akzeptanzkriterien

1. Ein Abrechnungszeitraum eines Marktplatzes wird vollständig gebucht; Erlöse, Gebühren und
   Erstattungen erscheinen getrennt.
2. Die Summe der Einzelposten entspricht der Auszahlung auf dem Bankkonto; eine Abweichung wird
   gemeldet statt geglättet.
3. Verkäufe in drei EU-Länder landen auf den richtigen OSS-Erlöskonten und in der Quartalsmeldung.
4. Der Stammdatenexport ist in DATEV importierbar (Golden-Test).
5. Exportierte Belege hängen beim Empfänger am zugehörigen Buchungssatz.
6. Der Kontoauszugsexport ist lückenlos nummeriert und der Saldenverlauf schlüssig.
7. Die API liefert offene Posten und nimmt Belege entgegen; ein Token ohne passenden
   Geltungsbereich wird abgewiesen.

## 8. Ausdrücklich NICHT in diesem Baustein

Rückschreiben in ERP- oder Marktplatzsysteme · Direktanbindung an DATEV-Cloud-Dienste ·
Bestands- und Artikelverwaltung · Anbindung an Kassensysteme · Datenübernahme aus Altsystemen.
