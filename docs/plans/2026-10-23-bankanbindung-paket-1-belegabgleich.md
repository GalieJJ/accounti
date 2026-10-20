# Live-Bankanbindung & Belegabgleich, Paket 1 (Belegabgleich) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Ein Bankumsatz, zu dem ein Beleg vorliegt, wird mit ihm zusammengeführt, **bevor**
kontiert wird — und dann aus dem Beleg kontiert statt aus dem Verwendungszweck: Lieferant,
Positionen und Steuersätze sind bekannt, die Vorsteuer steht auf dem Beleg. Unsichere Treffer sind
Vorschläge; zwei gleiche Belege werden nie willkürlich verteilt.

**Spec:** [`docs/specs/2026-08-10-bankanbindung-live.md`](../specs/2026-08-10-bankanbindung-live.md),
Abschnitte 3, 4.4 und 4.6 · Akzeptanzkriterien 3 und 4 · **Baut auf:** Baustein 2 (Belege),
Baustein 4 Paket 2 (Zahlungszuordnung)

## Schnitt von Baustein 5

| Paket | Inhalt | Akzeptanz |
|-------|--------|-----------|
| **1 (dieses)** | Belegabgleich, Kontierung mit Beleg, `bank abgleich/vorschlaege/bestaetigen/ablehnen/offen` | 3, 4 |
| 2 | Provider-Schnittstelle, Datei-Provider, Bankkonten mit verschlüsselten Zugängen, idempotenter Lauf | 2, 5, 6 |
| 3 | FinTS-Provider, Kreditkarten-Sammelbelastung | 1 |

**FinTS braucht eine Produktregistrierung** bei der Deutschen Kreditwirtschaft: Seit 01.08.2019
erhalten nur registrierte Produkte FinTS-Zugang. Das Formular geht im Original an
`registrierung@hbci-zka.de`, die Nummer kommt in 10–15 Werktagen und ist derzeit kostenlos
([fints.org](https://www.fints.org/de/hersteller/produktregistrierung)). Nummern von Bibliotheken
sind nur für interne Tests — registriert wird die Anwendung. Paket 3 wartet darauf; die
Produkt-ID wird je Installation konfiguriert, nicht ins Repository geschrieben.

```
import bank ─▶ opos zuordnen ─▶ bank abgleich ─▶ classify
               (Rechnungen über     │                 │
                offene Posten)      │                 ├─ abgeglichen: aus dem Beleg kontieren
                                    │                 └─ sonst: Regelwerk/LLM wie bisher
          Quittungen, sonstige Belege ↔ Umsätze
            A  Belegnummer im Verwendungszweck, Betrag exakt          → automatisch, wenn eindeutig
            B  Betrag exakt, 0–7 Tage, Gegenpartei (IBAN/Name) passt  → automatisch, wenn eindeutig
            C  Rundungsdifferenz, Trinkgeld, Betrag ohne Namenstreffer → Vorschlag
```

---

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Abgrenzung | Ein- und Ausgangsrechnungen laufen über offene Posten (Baustein 4); abgeglichen werden **Quittungen und sonstige Belege** mit Betrag, die direkt gegen die Bank gebucht werden | Eine Rechnung hat ihren Zahlungsausgleich schon über `opos zuordnen` — zwei Wege für denselben Beleg wären eine Doppelbuchung |
| Vorzeichen | Eingangsbeleg ↔ Ausgabe, Ausgangsbeleg ↔ Einnahme; eine Gutschrift (Brutto < 0) kehrt das um | Gutschrift als Testfall der Spec |
| Gegenpartei | IBAN gleich, oder mindestens die Hälfte der Wörter des Lieferanten (nach `normalisiere_name`, ab 3 Zeichen) steht im Gegenkonto-Namen oder Verwendungszweck | Kartenumsätze tragen den Händler oft nur im Verwendungszweck |
| Automatisch | A und B nur, wenn das Paar auf **beiden** Seiten das einzige A/B-Paar ist; A wird vor B vergeben | streng vor großzügig: ein falscher Abgleich begründet eine falsche Vorsteuer |
| Mehrdeutig | Alle Kandidaten eines Umsatzes werden Vorschläge (höchstens 3, nach Confidence); Bestätigen eines Vorschlags verwirft die konkurrierenden für denselben Umsatz und denselben Beleg | Akzeptanz 4: zwei gleiche Belege → zwei Vorschläge |
| Stufe C | Betrag exakt ohne Namenstreffer (−3 … +30 Tage); Rundungsdifferenz ≤ 0,05 €; mit Namenstreffer bis 15 % mehr gezahlt (Trinkgeld) | typische Abweichungen; immer nur Vorschlag |
| Rücklastschrift | Umsätze mit „Rücklastschrift/Rückbuchung/Rückbelastung“ im Verwendungszweck werden nicht abgeglichen, sondern gemeldet | sonst passt die Rückgabe als „Gutschrift“ zum Beleg |
| Kontierung mit Beleg | `classify` bucht abgeglichene Umsätze aus dem Beleg: je Steuersatz eine Buchung, Vorsteuer aus dem Beleg (BU 9/8, Ausgang 3/2), Sachkonto aus vorhandenem Kontakt → Regelwerk auf die Belegdaten → Regelwerk auf den Umsatz → Standardaufwand (zur Prüfung). Der Buchungssatz trägt Transaktion **und** Beleg | höhere Regeltrefferquote (Akzeptanz 3); kein Kreditor je Kassenbon |
| Differenz | Steuer immer aus dem Beleg; die Differenz zum gezahlten Betrag geht auf das Sachkonto der größten Gruppe, die Buchung zur Prüfung | Trinkgeld enthält keine Vorsteuer |
| Persistenz | Tabelle `belegabgleiche` (vorgeschlagen / bestätigt / abgelehnt) mit Stufe, Confidence, Begründung; abgelehnte Paare werden nicht erneut vorgeschlagen | nachvollziehbar wie die Zahlungszuordnung |
| Wechselwirkung | `opos zuordnen` überspringt Umsätze mit Beleg-Abgleich; `classify` überspringt Umsätze mit offenem Beleg-Vorschlag; `bank abgleich` nimmt nur Umsätze ohne Buchung und ohne Zahlungszuordnung | keine Doppelbuchung, kein Überholen eines offenen Vorschlags |
| Bericht | `bank offen`: Umsätze ohne Beleg (weder abgeglichen noch einem Posten zugeordnet) und Quittungen/sonstige Belege ohne Umsatz | Rohmaterial für die Vollständigkeitsprüfung (Baustein 7) |

## Aufgaben

- [x] **Abgleich** (`bank/abgleich.py`, rein): Vorzeichen und Gutschrift, Stufen A/B/C, Datumsfenster, Gegenpartei über IBAN und Namen, Eindeutigkeit auf beiden Seiten, A vor B, zwei gleiche Belege → Vorschläge, Rundungsdifferenz, Trinkgeld, Rücklastschrift (`tests/test_bank_abgleich.py`).
- [x] **Kontierung mit Beleg** (`buchung/mit_beleg.py`): Sachkonto-Ermittlung (gemeinsam mit `opos/verbuchung.py`), je Steuersatz eine Buchung mit Vorsteuer aus dem Beleg, Gutschrift, Differenz zur Prüfung, Ausgangsbeleg (`tests/test_buchung_mit_beleg.py`).
- [x] **Persistenz und Lauf:** Modell `Belegabgleich`, Tabelle, Migration; `gleiche_belege_ab()`, `bestaetige_abgleich()`, `lehne_abgleich_ab()`, `offene_posten_bank()`; `offene_transaktionen` und `classify` berücksichtigen Abgleiche (`tests/test_bank_abgleichslauf.py`).
- [x] **Akzeptanz 3 und 4** als Tests: mit Beleg greift eine Regel, die auf dem Umsatz allein nicht greift; zwei gleiche Quittungen am selben Tag → zwei Vorschläge.
- [x] **CLI:** `bank abgleich [--period]`, `bank vorschlaege`, `bank bestaetigen <ID>`, `bank ablehnen <ID>`, `bank offen`; `classify` meldet „davon n mit Beleg“ (`tests/test_cli_bank.py`).
- [x] **Abschluss:** `pytest`, `ruff` (ohne Cache), `mypy` grün; README, Bauplan, Architektur, CHANGELOG.
