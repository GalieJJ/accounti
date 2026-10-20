# Kreditoren, Debitoren & offene Posten, Paket 2 (Zahlungen) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Banktransaktionen werden offenen Posten zugeordnet — deterministisch vor unscharf. Sichere
Treffer gleichen den Posten sofort aus (vollständig, Teilzahlung, Skonto mit Steuerkorrektur),
unsichere werden als Vorschlag vorgelegt und erst nach Bestätigung gebucht. Die Bank-Kontierung aus
Baustein 1 lässt zugeordnete Zahlungen in Ruhe.

**Spec:** [`docs/specs/2026-08-10-kreditoren-debitoren-opos.md`](../specs/2026-08-10-kreditoren-debitoren-opos.md),
Abschnitte 4.4 und 4.5 · Akzeptanzkriterien 2–5 · **Baut auf:** [Paket 1](2026-10-20-kontakte-opos-paket-1.md)

```
Banktransaktion (ungebucht, nicht zugeordnet)
   │  accounti opos zuordnen
   ▼
Kontakt der Zahlung: IBAN → Name (wie in Paket 1)
   ▼
Stufe A  Referenz: Belegnummer im Verwendungszweck
           ein Posten:  = Rest → voll · = Rest − Skonto (in Frist) → Skonto · < Rest → Teilzahlung
                        > Rest → Vorschlag (Überzahlung)
           mehrere:     → Vorschlag (Sammelzahlung)
Stufe B  Exakt: genau ein Posten des Kontakts mit Rest = Betrag → voll
Stufe C  Unscharf → Vorschlag mit Confidence:
           Skontobetrag ohne Referenz · Summe mehrerer Posten · Teilbetrag · Betrag ohne Kontakt
   ▼
Ausgleich   Zahlung: Kreditor an Bank / Bank an Debitor
            Skonto:  Kreditor an 3736/3731 mit Vorsteuer-Korrektur
                     8736/8731 an Debitor mit Umsatzsteuer-Korrektur
            Posten:  Rest mindern → teilbezahlt / ausgeglichen
```

---

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Automatisch | nur Stufe A mit genau einem Posten (voll, Skonto in Frist, Teilzahlung) und Stufe B | deterministisch; alles andere geht zum Menschen (Spec 4.4) |
| Skonto-Frist | Zahlungsdatum ≤ Skonto bis + Karenz (Standard 3 Tage, `buchhaltung.skonto_karenz_tage`) | Bankbuchung kommt oft Tage nach der Überweisung |
| Skonto-Betrag | Toleranz 0,02 € gegen den berechneten Skontobetrag; gebucht wird die tatsächliche Differenz | Lieferanten runden je Satz anders |
| Steuerkorrektur | Skonto anteilig auf die Steuersätze der Rechnung (Brutto-Anteile aus den Belegbuchungen), Netto/Steuer je Anteil über `UStBerechner.berechne_vst` | Spec 4.5: immer mit Steuerkorrektur, Steuerlogik nur in `steuer/` |
| Skontokonten (SKR03) | erhalten 3736 (19 %), 3731 (7 %), 3730 (ohne USt); gewährt 8736, 8731, 8730 — überschreibbar in `buchhaltung` | Standardkonten des SKR03 |
| Überzahlung | Vorschlag; nach Bestätigung schließt der Posten, der Überschuss bleibt als Guthaben auf dem Personenkonto | buchhalterisch richtig, nichts geht verloren |
| Sammelzahlung | Teilmengen bis 4 Posten desselben Kontakts, auch mit Skonto je Posten | Akzeptanz 5 |
| Vorschläge | Tabelle `zahlungszuordnungen` (vorgeschlagen / gebucht / abgelehnt); eine Transaktion kann mehrere Posten bedienen | Bestätigen und Ablehnen sind nachvollziehbar |
| Doppelbuchung | `classify` überspringt Transaktionen, die schon gebucht oder zugeordnet sind; `zuordnen` überspringt bereits gebuchte | behebt auch den Fehler, dass ein zweiter `classify`-Lauf alles doppelt bucht |

## Aufgaben

- [x] **Zuordnung** (`opos/zuordnung.py`, reine Funktion): Referenz → voll, Skonto, Teilzahlung, Überzahlung; exakt; Skonto ohne Referenz; Sammelzahlung; Teilbetrag; ohne Kontakt; kein Treffer; Richtung (Ausgabe ↔ Verbindlichkeit, Einnahme ↔ Forderung) (`tests/test_opos_zuordnung.py`).
- [x] **Ausgleich** (`opos/ausgleich.py`): Zahlungsbuchung je Posten; Skonto 19 %/7 % gegen handgerechnete Sollwerte (172,50 € → Skonto 3,45 € = 2,00 + 0,38 VSt und 1,00 + 0,07 VSt); Ausgang mit USt-Korrektur; Posten-Status (`tests/test_opos_ausgleich.py`).
- [x] **Persistenz und Lauf:** Modell `Zahlungszuordnung`, Tabelle, Migration; `zuordne_zahlungen()` bucht Automatisches, speichert Vorschläge; `bestaetige()`/`lehne_ab()` (`tests/test_opos_zahlungslauf.py`).
- [x] **Akzeptanz 2–5** als End-to-End-Tests über Beleg → Posten → Banktransaktion.
- [x] **classify:** überspringt gebuchte und zugeordnete Transaktionen; zweiter Lauf bucht nichts doppelt (`tests/test_cli_end_to_end.py`).
- [x] **CLI:** `opos zuordnen`, `opos vorschlaege`, `opos bestaetigen <ID>`, `opos ablehnen <ID>` (`tests/test_cli_opos.py`).
- [x] **Abschluss:** `pytest`, `ruff`, `mypy` grün; README (Hinweis zur Doppelbuchung entfällt), Bauplan, Architektur, CHANGELOG, Beispielkonfiguration.
