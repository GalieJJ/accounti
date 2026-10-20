# Kreditoren, Debitoren & offene Posten, Paket 1 — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Aus einem erfassten Beleg entsteht eine Buchung auf ein Personenkonto und ein offener
Posten mit Fälligkeit und Skontofrist. Kontakte werden aus den Belegdaten erkannt statt doppelt
angelegt. OPOS-Liste und Fälligkeitsstaffel zeigen, was offen ist.

**Spec:** [`docs/specs/2026-08-10-kreditoren-debitoren-opos.md`](../specs/2026-08-10-kreditoren-debitoren-opos.md),
Abschnitte 4.1, 4.3, 4.6 · Akzeptanzkriterien 1 und 6

## Schnitt von Baustein 4

| Paket | Inhalt | Akzeptanz |
|-------|--------|-----------|
| **1** (dieses) | Kontakte + Personenkonten + Erkennung; Beleg → Buchung gegen Kreditor/Debitor + offener Posten; OPOS-Liste, Fälligkeitsstaffel | 1, 6 |
| 2 | Zahlungszuordnung (Referenz → exakt → unscharf), Ausgleich, Teil- und Sammelzahlung, Skonto mit Steuerkorrektur; Bank-Kontierung überspringt zugeordnete Zahlungen | 2–5 |
| 3 | USt-IdNr.-Prüfung (BZSt) mit revisionssicherem Protokoll; Sperre der steuerfreien ig. Lieferung bei ungültiger Nummer | 7 |

```
Beleg (erfasst)                                 config/accounti.yaml → buchhaltung (optional)
   │  accounti opos verbuchen
   ▼
Kontakterkennung: IBAN → USt-IdNr. → Name (normalisiert)
   ├─ Treffer                → Kontakt
   └─ kein Treffer           → neuer Kontakt, Status „zur Prüfung", nächste freie Personenkontonummer
   ▼
Buchungen je Steuersatz      Eingang: Aufwand  an Kreditor (BU 9/8, Vorsteuer)
                             Ausgang: Debitor an Erlös     (BU 3/2 bzw. steuerfreie Erlöskonten)
   ▼
Offener Posten               Brutto, Restbetrag, fällig am, Skonto bis, Skontobetrag
```

---

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Personenkonten | Debitoren 10000–69999, Kreditoren 70000–99999 (SKR03 und SKR04), überschreibbar im neuen Abschnitt `buchhaltung`; nächste freie Nummer im Kreis | Spec 4.1; Kreise weichen je Betrieb ab |
| Konfiguration | `buchhaltung` ist optional — ohne Datei gelten die Standards | OPOS soll ohne vollständige E-Rechnungs-Firmendaten nutzbar sein |
| Kontakterkennung | IBAN → USt-IdNr. → normalisierter Name (Rechtsform, Satzzeichen, Umlaute, Groß/Klein egal); kein Treffer → neuer Kontakt *zur Prüfung* | Spec 4.1: eine Firma, nicht drei Schreibvarianten |
| Sachkonto (Eingang) | Vorschlag am Kontakt → Regelwerk aus Baustein 1 auf den Lieferantennamen → sonst 4900 mit Status *zur Prüfung* | wiederkehrende Lieferanten werden still richtig gebucht, Unbekanntes geht zum Menschen |
| Erlöskonto (Ausgang) | aus Steuerkategorie und Satz der Position: S 19 % → 8400 (BU 3), S 7 % → 8300 (BU 2), K → 8125, AE → 8338, G → 8120, anderer EU-Satz (OSS) → 8320 | Konten nach SKR03; Steuer kommt aus der Rechnung, nicht neu gerechnet |
| Buchungssatz | `transaktion_id` wird optional, neu `beleg_id` | Belegbuchungen haben keine Banktransaktion; Bankbuchungen bleiben unverändert |
| Gutschriften | negative Beträge → Soll/Haben getauscht, OP mit negativem Betrag | Gutschrift mindert den offenen Saldo des Kontakts |
| Doppelte Verbuchung | ein Beleg wird genau einmal verbucht (`beleg_id` am OP, eindeutig) | sonst doppelte Verbindlichkeit |
| Fälligkeit | Zahlungsziel aus dem Beleg → Zahlungsbedingungen des Kontakts → 14 Tage ab Belegdatum | Spec Akzeptanz 1 |

## Aufgaben

- [x] **Modell und Persistenz:** `Kontakt`, `OffenerPosten`; `Buchungssatz.transaktion_id` optional + `beleg_id`; Tabellen, Repository, Migration (`tests/test_kontakte_repository.py`).
- [x] **Personenkonten:** nächste freie Nummer je Kreis, Kreis voll → klarer Fehler (`tests/test_kontakte.py`).
- [x] **Kontakterkennung:** IBAN, USt-IdNr., Name; „Bürobedarf Müller GmbH", „BUEROBEDARF MÜLLER G.m.b.H." und „Bürobedarf Müller" ergeben einen Kontakt; Neuanlage zur Prüfung (`tests/test_kontakte.py`).
- [x] **Verbuchung:** Eingangsrechnung mit 19 % und 7 % → zwei Buchungen Aufwand an Kreditor + ein OP mit Fälligkeit aus Zahlungsziel und Skontofrist (Akzeptanz 1); Ausgangsrechnung → Debitor an Erlös je Kategorie; Gutschrift; zweiter Lauf verbucht nichts doppelt (`tests/test_opos_verbuchung.py`).
- [x] **Auswertungen:** OPOS-Liste je Richtung, Fälligkeitsstaffel (nicht fällig / 1–30 / 31–60 / 61–90 / über 90) gegen handgerechnete Sollwerte (Akzeptanz 6), Summen je Kontakt (`tests/test_opos_auswertung.py`).
- [x] **CLI:** `kontakte liste [--typ]`, `kontakte zeigen`, `kontakte bestaetigen`, `kontakte bearbeiten` (Sachkonto, Zahlungsbedingungen); `opos verbuchen`, `opos liste [--richtung] [--faellig]`, `opos staffel [--stichtag]` (`tests/test_cli_opos.py`).
- [x] **Bestehendes:** `review`, `korrigiere`, DATEV-Export und BWA kommen mit Belegbuchungen ohne Transaktion zurecht.
- [x] **Abschluss:** `pytest`, `ruff`, `mypy` grün; README, Bauplan, Architektur, CHANGELOG, Beispielkonfiguration.
