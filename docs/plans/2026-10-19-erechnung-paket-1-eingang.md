# E-Rechnung, Paket 1 (Eingang) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Eingehende XRechnungen (UBL und CII) und ZUGFeRD/Factur-X-Dateien werden ohne OCR
vollständig in einen `Beleg` mit allen Positionen und der Steueraufschlüsselung je Satz übernommen
und fachlich validiert. Ein Beleg mit Fehlern geht mit lesbarem Befund zur Prüfung.

**Spec:** [`docs/specs/2026-08-10-erechnung.md`](../specs/2026-08-10-erechnung.md), Eingangsstrang
und Abschnitte 4.1–4.3 · **Baut auf:** Baustein 2 (`belege/erkennung.py` erkennt das Format schon)

**Architektur:**

```
Beleg-Pipeline (Baustein 2)
  └─ BelegErkenner: Format E-Rechnung?
        └─ erechnung.lies(xml) ─▶ parser/cii.py | parser/ubl.py ─▶ Rechnung (EN 16931)
                                                                     │
                                  validierung.pruefe(rechnung) ◀─────┤
                                                                     ▼
                                                   abbildung.zu_beleg(rechnung, befunde)
```

Die restliche Anwendung kennt nur das Zwischenmodell `Rechnung`, nie UBL oder CII.

---

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| XML-Sicherheit | stdlib `ElementTree`; Dateien mit `<!DOCTYPE`/`<!ENTITY` werden abgelehnt | E-Rechnungen brauchen keine DTD; schließt Entity-Angriffe ohne neue Abhängigkeit aus |
| Validierung | fachliche Prüfung in Python: Auswahl der EN-16931-Geschäftsregeln (BR-01…16, BR-CO-10…16, BR-S/AE/E/IC, BR-DE-15) plus § 14 UStG und Steuersatz-Plausibilität über `steuer/eu_steuersaetze.py` | die formale Prüfung gegen XSD und Schematron (KoSIT-Prüftool, Java) kommt mit dem Ausgang in Paket 2, wo Akzeptanzkriterium 4 sie verlangt |
| Befunde | `Befund(regel, schwere, text)` mit Schwere `fehler`/`warnung` | Spec 4.3: Warnungen werden gebucht, Fehler gehen zur Prüfung |
| Profile | aus BT-24 erkannt (MINIMUM, BASIC WL, BASIC, EN 16931, EXTENDED, XRechnung) | MINIMUM und BASIC WL liefern keine Positionen — kein Fehler, aber eine Warnung (keine E-Rechnung im Sinne von § 14 UStG) |
| Positionen | eine `Belegposition` je Rechnungszeile, dazu je Nachlass/Zuschlag auf Belegebene; Steuer je Zeile so verteilt, dass die Summe je Satz exakt der Aufschlüsselung (BG-23) entspricht | die amtliche Aufschlüsselung je Satz bleibt erhalten, ohne das Beleg-Modell zu erweitern |
| Skonto | XRechnung-Konvention `#SKONTO#TAGE=7#PROZENT=2.00#` in BT-20 | so liefert es der deutsche Markt |
| Kaputte E-Rechnung | XML: zur Prüfung mit Grund; ZUGFeRD: zusätzlich Text der PDF-Ansicht als Vorbefüllung | strukturierte Daten schlagen OCR — außer, sie sind unlesbar |

## Dateistruktur

| Pfad | Verantwortung |
|------|---------------|
| `src/accounti/erechnung/__init__.py` | `lies(xml) -> Rechnung`, `ERechnungError` |
| `src/accounti/erechnung/modell.py` | `Rechnung`, `Partei`, `Rechnungszeile`, `ZuAbschlag`, `Steueraufschluesselung`, `Summen`, Profilerkennung |
| `src/accounti/erechnung/parser/_xml.py` | sicheres Parsen, Pfad-Helfer |
| `src/accounti/erechnung/parser/cii.py` | UN/CEFACT CII (XRechnung, ZUGFeRD, Factur-X) |
| `src/accounti/erechnung/parser/ubl.py` | UBL Invoice und CreditNote |
| `src/accounti/erechnung/validierung.py` | `pruefe(rechnung) -> list[Befund]` |
| `src/accounti/erechnung/abbildung.py` | `zu_beleg(rechnung, befunde, beleg)` |
| `src/accounti/belege/erkennung.py` | E-Rechnung über `erechnung` statt „zur Prüfung, Baustein 3" |
| `src/accounti/cli.py` | `accounti rechnung pruefen <datei>` |
| `examples/erechnung/` | anonymisierte Fixtures |

---

## Aufgabe 1: Fixtures

- [x] `xrechnung_cii.xml` und `xrechnung_ubl.xml`: dieselbe Rechnung (drei Positionen, 19 % und 7 %, Skonto, IBAN, Leitweg-ID) in beiden Syntaxen.
- [x] `mit_nachlass_cii.xml`: Rabatt und Versandzuschlag auf Belegebene.
- [x] `fehler_rechenprobe_cii.xml`: Steuerbetrag je Satz falsch.
- [x] `reverse_charge_ohne_ust_id_ubl.xml`: Kategorie AE, Käufer ohne USt-IdNr.
- [x] `minimum_cii.xml`: Factur-X MINIMUM.

## Aufgabe 2: Zwischenmodell und Parser

**Tests:** `tests/test_erechnung_parser.py`

- [x] CII: Kopf, Verkäufer, Käufer, Zeilen, Aufschlüsselung, Summen, Zahlungsdaten, Profil.
- [x] UBL: dieselbe Rechnung ergibt dasselbe Zwischenmodell wie CII (bis auf die Syntax).
- [x] Nachlass und Zuschlag auf Belegebene werden gelesen.
- [x] UBL CreditNote wird gelesen.
- [x] DOCTYPE/ENTITY wird abgelehnt; unbekanntes Wurzelelement → `ERechnungError`.
- [x] Skonto aus `#SKONTO#…#`.

## Aufgabe 3: Validierung

**Tests:** `tests/test_erechnung_validierung.py`

- [x] Gültige Fixtures: keine Fehler.
- [x] (Akzeptanz 3) falsche Rechenprobe → Fehler BR-S-09 bzw. BR-CO-14/15.
- [x] Reverse-Charge ohne Käufer-USt-IdNr. → Fehler BR-AE-02.
- [x] Pflichtangaben je Regel (fehlende Nummer, Datum, Verkäufer, Positionen) — je ein Fall.
- [x] Steuersatz 16 % bei deutschem Verkäufer → Warnung; MINIMUM-Profil → Warnung, keine Fehler.
- [x] XRechnung ohne Leitweg-ID → Fehler BR-DE-15.

## Aufgabe 4: Abbildung auf den Beleg

**Tests:** `tests/test_erechnung_abbildung.py`

- [x] (Akzeptanz 1) alle Zeilen als Positionen; Summe der Positionssteuer je Satz = Aufschlüsselung; Beleg `erfasst`.
- [x] Nachlass/Zuschlag als eigene Positionen; Positionen summieren sich zu BT-109.
- [x] Fehler → `pruefung`, Befunde im `pruef_grund`; Warnungen stehen im `pruef_grund`, Status bleibt `erfasst`.
- [x] Eigene USt-IdNr. als Verkäufer → Ausgangsrechnung.

## Aufgabe 5: Anbindung an die Beleg-Pipeline

**Tests:** `tests/test_belege_erkenner.py`

- [x] XRechnung über `belege import` → erfasster Beleg, ohne OCR und ohne Textextraktion.
- [x] (Akzeptanz 2) ZUGFeRD-PDF ergibt denselben Beleg wie das reine XML.
- [x] Unlesbare E-Rechnung → `pruefung` mit Grund.

## Aufgabe 6: CLI

**Tests:** `tests/test_cli_rechnung.py`

- [x] `accounti rechnung pruefen <xml|pdf>` zeigt Kopf, Summen und Befunde; Exit-Code 1 bei Fehlern.

## Abschluss

- [x] `pytest`, `ruff`, `mypy` grün; README, Bauplan, Architektur, CHANGELOG nachziehen.
