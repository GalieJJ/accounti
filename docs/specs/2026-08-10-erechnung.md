# Spec: E-Rechnung — Eingang & Ausgang

- **Status:** Entwurf (2026-08-10)
- **Baustein:** 3 von 12 (siehe [Bauplan](../bauplan.md))
- **Ziel-Branch:** `feat/erechnung`

## 1. Kontext

Seit dem 1. Januar 2025 muss jedes deutsche Unternehmen E-Rechnungen im inländischen
B2B-Geschäft **empfangen** können. Für den Versand laufen gestaffelte Übergangsfristen. Eine
E-Rechnung ist dabei nicht „PDF per Mail", sondern ein strukturierter Datensatz nach EN 16931.

Für accounti ist das weniger eine Pflicht als ein Geschenk: Eine E-Rechnung liefert genau die
Daten, die Baustein 2 sonst mühsam per OCR aus einem Bild schätzen muss — Positionen, Steuersätze,
Zahlungsbedingungen, Lieferantendaten, alles maschinenlesbar und validierbar. Wo eine E-Rechnung
vorliegt, ist die Erkennungsrate nicht 95 %, sondern 100 %.

Dieser Baustein deckt beide Richtungen ab: Eingangsrechnungen lesen und Ausgangsrechnungen
erzeugen.

## 2. Ziel

> Eingehende XRechnungen und ZUGFeRD-Dateien werden ohne OCR vollständig strukturiert übernommen
> und validiert. Ausgangsrechnungen werden in accounti geschrieben und als konforme E-Rechnung
> versendet.

## 3. Pipeline

```
EINGANG
   Datei aus Baustein 2
        │
        ▼
   [1] Formaterkennung
   ├─ XML (UBL / UN-CEFACT CII)     → XRechnung
   ├─ PDF/A-3 mit eingebettetem XML → ZUGFeRD / Factur-X
   └─ sonst                          → zurück an OCR (Baustein 2)
        │
        ▼
   [2] Parser  → gemeinsames Zwischenmodell (EN 16931)
        │
        ▼
   [3] Validierung (Schema + Schematron + fachliche Regeln)
        │  Fehler → Beleg „ungültig", Grund protokolliert
        ▼
   [4] Beleg + Belegpositionen   (Modell aus Baustein 2)


AUSGANG
   Rechnungsentwurf (Positionen, Kunde, Zahlungsbedingungen)
        │
        ▼
   [1] Steuerermittlung  → steuer/umsatzsteuer.py (Inland / EU / Drittland)
        │
        ▼
   [2] Erzeugung  ├─ XRechnung (XML)
                  └─ ZUGFeRD (PDF/A-3 + XML)
        │
        ▼
   [3] Validierung gegen dieselben Regeln wie im Eingang
        │
        ▼
   [4] Versand (E-Mail / Peppol-Zugangspunkt später)
        │
        ▼
   [5] Buchung + offener Posten (Baustein 4)
```

Dass Ausgangsrechnungen durch dieselbe Validierung laufen wie Eingangsrechnungen, ist Absicht:
Was wir anderen schicken, muss den Maßstab bestehen, den wir an andere anlegen.

## 4. Komponenten & Arbeitspakete

### 4.1 `erechnung/modell.py` — Zwischenmodell *(neu)*

Ein Datenmodell nach EN 16931, auf das alle Formate abgebildet werden. Die restliche Anwendung
kennt nur dieses Modell, nie ein konkretes Format. Enthält Rechnungskopf, Verkäufer, Käufer,
Positionen, Steueraufschlüsselung je Satz, Zahlungsbedingungen, Referenzen (Leitweg-ID,
Bestellnummer).

### 4.2 `erechnung/parser/` — Eingang *(neu)*

- `ubl.py` — XRechnung im UBL-Syntax
- `cii.py` — XRechnung und ZUGFeRD im UN-CEFACT-CII-Syntax
- `zugferd.py` — XML-Anhang aus PDF/A-3 extrahieren, dann an `cii.py`
- Profilerkennung: ZUGFeRD-Profile unterscheiden sich im Umfang; das Profil bestimmt, welche
  Felder erwartet werden dürfen. Ein Minimal-Profil ist kein Fehler, sondern liefert eben weniger.

### 4.3 `erechnung/validierung.py` *(neu)*

Drei Stufen: XML-Schema, Schematron-Regeln der jeweiligen Spezifikation, fachliche Zusatzprüfungen
(Pflichtangaben nach § 14 UStG, Rechenprobe Netto + Steuer = Brutto je Satz, Plausibilität des
Steuersatzes zum Land). Ergebnis ist eine Liste von Befunden mit Schweregrad — ein Beleg mit
Warnungen wird gebucht, ein Beleg mit Fehlern geht zur Prüfung.

### 4.4 `erechnung/erzeuger/` — Ausgang *(neu)*

Erzeugt XRechnung und ZUGFeRD aus dem Zwischenmodell. Die Steuerermittlung kommt vollständig aus
`steuer/umsatzsteuer.py` — es gibt keine zweite Steuerlogik im Rechnungsschreiber. Damit gelten
für Ausgangsrechnungen automatisch dieselben Regeln für innergemeinschaftliche Lieferungen,
Reverse-Charge, OSS und Ausfuhr, die bereits implementiert sind.

Rechnungsnummernkreise sind fortlaufend und lückenlos je Gesellschaft und Jahr.

### 4.5 `erechnung/versand.py` *(neu)*

E-Mail-Versand mit der E-Rechnung als Anhang, Versandprotokoll am Beleg. Ein Peppol-Zugangspunkt
ist als späterer Provider vorgesehen, aber nicht Teil dieses Bausteins — die Schnittstelle wird so
geschnitten, dass er sich einhängen lässt.

### 4.6 CLI

```bash
accounti rechnung neu --kunde 10001              # Entwurf anlegen
accounti rechnung position 2026-0042 --text "Beratung" --netto 1200 --satz 19
accounti rechnung erzeugen 2026-0042 --format zugferd
accounti rechnung pruefen ./eingang.xml          # Validierung ohne Import
accounti rechnung senden 2026-0042
```

## 5. Tech-Entscheidungen (fix)

| Thema | Entscheidung |
|-------|--------------|
| Zwischenmodell | EN 16931 als gemeinsamer Nenner, Formate nur an den Rändern |
| Eingangsformate | XRechnung (UBL + CII), ZUGFeRD/Factur-X ab dem Profil, das Pflichtangaben trägt |
| Ausgangsformate | ZUGFeRD als Default (PDF bleibt lesbar), XRechnung wenn gefordert |
| Steuer | Ausschließlich über `steuer/umsatzsteuer.py`, keine zweite Logik |
| Validierung | Schema + Schematron + fachliche Prüfungen, Befunde mit Schweregrad |
| Versand | E-Mail zuerst, Peppol als späterer Provider hinter derselben Schnittstelle |

## 6. Teststrategie

- Fixtures echter, anonymisierter E-Rechnungen je Format und Profil in `examples/erechnung/`.
- Round-Trip-Test: erzeugte Rechnung → eigener Parser → identisches Zwischenmodell.
- Validierung gegen bewusst fehlerhafte Fixtures (falsche Rechenprobe, fehlende USt-IdNr. bei
  innergemeinschaftlicher Lieferung, unplausibler Steuersatz).
- Steuerfälle über alle Konstellationen, die `steuer/` kennt: Inland, EU-B2B, EU-B2C, Drittland.
- Nummernkreis-Test: Lückenlosigkeit auch bei parallelen Zugriffen.

## 7. Akzeptanzkriterien

1. Eine eingehende XRechnung wird ohne OCR vollständig übernommen, inklusive aller Positionen und
   der Steueraufschlüsselung je Satz.
2. Eine ZUGFeRD-Datei liefert dasselbe Ergebnis wie die identische Rechnung als reines XML.
3. Eine Rechnung mit falscher Rechenprobe wird abgelehnt, der Befund ist am Beleg lesbar.
4. Eine in accounti geschriebene Ausgangsrechnung besteht die Validierung und wird von einem
   externen Prüfwerkzeug als konform anerkannt.
5. Eine Ausgangsrechnung an einen EU-Kunden mit USt-IdNr. weist 0 % mit Hinweis auf Reverse-Charge
   aus — abgeleitet aus `steuer/`, nicht neu implementiert.
6. Rechnungsnummern sind je Gesellschaft und Jahr lückenlos fortlaufend.

## 8. Ausdrücklich NICHT in diesem Baustein

Peppol-Zugangspunkt · Mahnwesen (Baustein 6) · offene Posten (Baustein 4) · Layoutgestaltung der
PDF-Ansicht über das Nötige hinaus · Angebote, Auftragsbestätigungen, Lieferscheine.
