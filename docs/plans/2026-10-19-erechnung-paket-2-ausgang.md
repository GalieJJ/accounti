# E-Rechnung, Paket 2 (Ausgang) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Ausgangsrechnungen werden in accounti geschrieben, mit lückenloser Nummer je Gesellschaft
und Jahr ausgestellt, als XRechnung erzeugt und vor dem Ausstellen formal mit dem KoSIT-Prüftool
und fachlich mit `erechnung/validierung.py` geprüft. Die Steuer kommt ausschließlich aus `steuer/`.

**Spec:** [`docs/specs/2026-08-10-erechnung.md`](../specs/2026-08-10-erechnung.md), Ausgangsstrang,
Abschnitte 4.4 und 4.6, Akzeptanzkriterien 4–6 · **Baut auf:** [Paket 1](2026-10-19-erechnung-paket-1-eingang.md)

```
Entwurf (Kunde, Positionen)                              config/accounti.yaml → Firma
   │  accounti rechnung neu / position                         │
   ▼                                                           ▼
ausstellen ── Nummernkreis +1 ──▶ erzeuger/aufbau.py ──(steuer/UStBerechner)──▶ Rechnung (EN 16931)
   │                                                                                │
   │                                         erzeuger/cii.py ◀──────────────────────┘
   │                                                │ XRechnung (CII) XML
   │              validierung.pruefe ◀──────────────┤
   │              kosit.KositPruefer ◀──────────────┘   ← Fehler: Rollback, Nummer bleibt frei
   ▼
Archiv + Beleg (Ausgangsrechnung, über den eigenen Parser gelesen) + Status „ausgestellt"
```

---

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Ausgabeformat | XRechnung 3.0 in CII-Syntax | CII ist zugleich die Syntax von ZUGFeRD; das ZUGFeRD-PDF (PDF/A-3) folgt in Paket 3 zusammen mit dem Versand |
| Formale Prüfung | KoSIT-Validator 1.6.3 + XRechnung-Konfiguration 2026-08-31, per Skript mit fester Version und SHA-256 nach `.kosit/` installiert; Aufruf über Java | das offizielle Prüfwerkzeug (Akzeptanz 4); ohne Prüftool wird nur mit ausdrücklichem `--ohne-kosit` ausgestellt |
| Steuer | `UStBerechner` bestimmt Vorfall und Satz je Position; neu: `ist_sonstige_leistung` → Reverse-Charge bei EU-B2B-Dienstleistungen | keine zweite Steuerlogik (Spec 4.4); Akzeptanz 5 braucht die Unterscheidung Ware/Leistung, und die gehört nach `steuer/` |
| Steuerbetrag | je Kategorie und Satz auf die Summe gerechnet (BR-S-09), über `UStBerechner.berechne_ust` | so rechnet auch die Prüfung |
| Nummernkreis | Tabelle `nummernkreise(kreis, jahr, letzte)`, Hochzählen per `UPDATE` in der Ausstell-Transaktion; scheitert die Prüfung, wird zurückgerollt | lückenlos (Akzeptanz 6), auch bei parallelen Zugriffen |
| Unveränderbarkeit | ausgestellte Rechnungen lassen sich nicht mehr ändern; Korrektur später per Storno | GoBD |
| Firmendaten | Abschnitt `mandant` in `config/accounti.yaml` (Anschrift, USt-IdNr., Steuernummer, IBAN, Kontakt, Nummernformat) | XRechnung verlangt Kontakt, Anschrift und Zahlungsdaten des Verkäufers |
| Kunde | bis Baustein 4 direkt am Entwurf (Name, Anschrift, USt-IdNr., E-Mail, Leitweg-ID) | Debitoren gibt es noch nicht |
| Nicht unterstützt | sonstige Leistung an Drittland (Kategorie O) — klare Fehlermeldung | eigene Regeln (BR-O-*) und eigener Vorfall; eigener Schritt |

## Dateistruktur

| Pfad | Verantwortung |
|------|---------------|
| `src/accounti/steuer/umsatzsteuer.py` | `ist_sonstige_leistung` in `bestimme_vorfall`/`berechne_ust` |
| `src/accounti/konfiguration.py` | `Firma`, `lade_firma()` |
| `src/accounti/models/__init__.py` | `Ausgangsrechnung`, `AusgangsPosition`, `Rechnungsempfaenger`, `AusgangsrechnungStatus` |
| `src/accounti/db/tabellen.py`, `repository.py`, Alembic | Tabellen, `naechste_nummer()` |
| `src/accounti/erechnung/erzeuger/aufbau.py` | Entwurf + Firma → `Rechnung` (Steuer über `steuer/`) |
| `src/accounti/erechnung/erzeuger/cii.py` | `Rechnung` → XRechnung-CII-XML |
| `src/accounti/erechnung/kosit.py` | `KositPruefer` (Java-Aufruf, Bericht auswerten) |
| `src/accounti/erechnung/ausstellung.py` | `stelle_aus()` — Nummer, Erzeugung, Prüfung, Archiv, Beleg |
| `scripts/kosit_installieren.sh` | Prüftool mit fester Version und Prüfsumme installieren |
| `src/accounti/cli.py` | `rechnung neu`, `position`, `zeigen`, `liste`, `ausstellen`; `pruefen --kosit` |

---

## Aufgaben

- [x] **Steuer:** EU-B2B-Dienstleistung mit USt-IdNr. → `EU_B2B_REVERSE_CHARGE`; Ware bleibt ig. Lieferung; Inland/OSS/Drittland unverändert (`tests/test_steuer.py`).
- [x] **Firma:** `lade_firma` liest `mandant`, meldet fehlende Pflichtangaben verständlich (`tests/test_konfiguration.py`).
- [x] **Modell und Persistenz:** Entwurf mit Positionen speichern/laden; ausgestellte Rechnung ist unveränderlich (`tests/test_ausgangsrechnung_repository.py`).
- [x] **Nummernkreis:** fortlaufend je Kreis und Jahr, neues Jahr beginnt bei 1; 4 Threads × 10 Nummern auf einer Datei-DB ergeben 1…40 ohne Lücke und Doppelung (Akzeptanz 6, `tests/test_nummernkreis.py`).
- [x] **Aufbau:** Inland 19 %/7 % gemischt; EU-B2B-Dienstleistung → AE 0 % mit Reverse-Charge-Hinweis (Akzeptanz 5); EU-B2B-Ware → K mit Lieferland; Drittland → G; EU-B2C → OSS-Satz des Ziellands; Steuer je Satz auf die Summe (`tests/test_erechnung_aufbau.py`).
- [x] **CII-Erzeuger:** Round-Trip `lies(schreibe_cii(r)) == r` für alle Steuerfälle; eigene Prüfung ohne Fehler; Skonto im XRechnung-Format (`tests/test_erechnung_erzeuger.py`).
- [x] **KoSIT:** Wrapper wertet Bericht aus (accept/reject, Meldungen mit Code); erzeugte Rechnungen aller Steuerfälle werden akzeptiert (Akzeptanz 4); Tests laufen, wenn `.kosit/` installiert ist (`tests/test_erechnung_kosit_pruefer.py`).
- [x] **Ausstellen:** vergibt Nummer, schreibt XML, archiviert, legt Beleg (Ausgangsrechnung) an; bei Prüffehler Rollback ohne verbrauchte Nummer (`tests/test_ausstellung.py`).
- [x] **CLI:** Entwurf anlegen, Positionen, Vorschau, Ausstellen, Liste; `pruefen --kosit` (`tests/test_cli_rechnung.py`).
- [x] **CI:** Java ist auf den Runnern vorhanden; Prüftool per Skript installieren, Cache auf die Skript-Prüfsumme.
- [x] **Abschluss:** `pytest`, `ruff`, `mypy` grün; README, Bauplan, Architektur, CHANGELOG, Beispielkonfiguration.
