# E-Rechnung, Paket 3 (ZUGFeRD und Versand) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Jede ausgestellte Rechnung gibt es zusätzlich als ZUGFeRD-PDF: ein lesbares PDF/A-3 mit
der XRechnung als eingebettetem Anhang. Beides wird vor dem Ausstellen formal geprüft und
archiviert. Ausgestellte Rechnungen werden per E-Mail versendet, und jeder Versandversuch
landet im Versandprotokoll.

**Spec:** [`docs/specs/2026-08-10-erechnung.md`](../specs/2026-08-10-erechnung.md), Ausgangsstrang
Schritte 2 und 4, Abschnitt 4.5 · **Baut auf:** [Paket 2](2026-10-19-erechnung-paket-2-ausgang.md)

```
ausstellen ─▶ XRechnung (CII) ─┬─▶ KoSIT-Prüftool ──────────────┐
                               └─▶ ZUGFeRD-PDF/A-3 ─▶ Mustang ───┤  Fehler → Rollback
                                    (fpdf2, XML eingebettet)     ▼
                                                     Archiv: XML + PDF, Beleg, Nummer
senden ─▶ Datei aus dem Archiv (nie neu erzeugt) ─▶ E-Mail ─▶ Versandprotokoll
```

---

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| PDF-Bibliothek | `fpdf2` 2.8.9 (LGPL-3.0) mit `enforce_compliance="PDF/A-3B"` | bringt Schrift-Subsetting, sRGB-Output-Intent, Associated Files und eigenes XMP mit; reportlab bräuchte das Meiste von Hand |
| Abhängigkeiten | Pillow 12.3 und fontTools 4.66 statt der wenige Tage alten Versionen 13.0/4.67; `pillow<13` bis die neue Hauptversion erprobt ist | nur abgehangene Versionen |
| Schrift | Liberation Sans 2.1.5 (SIL OFL 1.1) mitgeliefert in `erechnung/schriften/` | PDF/A verlangt eingebettete Schriften; keine Abhängigkeit von Systemschriften |
| ZUGFeRD-Profil | XRECHNUNG: Anhang `xrechnung.xml`, `AFRelationship=Alternative`, XMP `fx:ConformanceLevel=XRECHNUNG` | dasselbe XML wie die XRechnung — ein Erzeuger, eine Prüfung |
| Formale PDF-Prüfung | Mustang-CLI 2.26.0 (Apache-2.0): veraPDF für PDF/A-3b plus Prüfung des eingebetteten XML | ein Werkzeug für beides; im Prototyp gegengeprüft: konformes PDF *valid*, PDF ohne PDF/A *invalid* |
| Prüfwerkzeuge | gemeinsames Verzeichnis `.pruefwerkzeuge/` (KoSIT + Mustang), Skript `scripts/pruefwerkzeuge_installieren.sh` mit festen Versionen und SHA-256 | ersetzt `.kosit/`; ein Ort, ein Skript, ein CI-Cache |
| Ausstellen | erzeugt XML und PDF, prüft beide, archiviert beide; `--ohne-formale-pruefung` (alt: `--ohne-kosit`) | was gesendet wird, ist geprüft und archiviert |
| Versand | `senden` liest die Datei aus dem Archiv, erzeugt nie neu; SMTP über `smtplib`, Konfiguration im Abschnitt `versand`, Passwort aus Umgebungsvariable | gesendet wird genau das archivierte Original |
| Versandprotokoll | Tabelle `versandprotokolle`, auch Fehlschläge | Nachweis gegenüber Kunde und Betriebsprüfung |
| Erweiterbarkeit | Versandweg als Schnittstelle (`email`, später `peppol`) | Spec 4.5 |
| Trockenlauf | `senden --eml datei.eml` schreibt die Nachricht nur in eine Datei | prüfen, bevor etwas rausgeht |

## Aufgaben

- [x] **PDF:** `erechnung/erzeuger/zugferd.py` — Rechnungslayout (Absender, Anschriftfeld, Kopfdaten, Positionen, Steuer je Satz, Summen, Hinweise, Zahlungsbedingungen mit lesbarem Skonto, Fußzeile mit Steuer- und Bankdaten), XML-Anhang, XMP mit Factur-X-Erweiterung; deterministisch bei gleichem Zeitstempel (`tests/test_erechnung_zugferd.py`).
- [x] **Round-Trip:** der eigene Beleg-Erkenner liest aus dem PDF exakt das eingebettete XML; Text der PDF-Ansicht enthält Nummer, Summen und Reverse-Charge-Hinweis.
- [x] **Prüfwerkzeuge:** Skript installiert KoSIT und Mustang nach `.pruefwerkzeuge/`; `erechnung/mustang.py` wertet den Bericht aus (PDF/A, XML, Gesamt); erzeugte PDFs aller Steuerfälle sind *valid* (`tests/test_erechnung_mustang.py`).
- [x] **Ausstellen:** XML + PDF, beide geprüft und archiviert, `pdf_hash` an der Rechnung; abgelehntes PDF → Rollback (`tests/test_ausstellung.py`).
- [x] **Versand:** Konfiguration laden (`${UMGEBUNGSVARIABLE}`), Nachricht bauen (Betreff, Text, Anhang, Message-ID), über SMTP senden (Fake im Test), Protokoll bei Erfolg und Fehler; nur ausgestellte Rechnungen (`tests/test_versand.py`).
- [x] **CLI:** `rechnung senden <Nr> [--format zugferd|xrechnung] [--eml datei]`; `rechnung zeigen` zeigt das Versandprotokoll; `rechnung liste` zeigt den Versandstand (`tests/test_cli_rechnung.py`).
- [x] **CI:** Cache und Installation auf `.pruefwerkzeuge/` umstellen; Pflicht-Variable `ACCOUNTI_PRUEFWERKZEUGE_PFLICHT`.
- [x] **Abschluss:** `pytest`, `ruff`, `mypy` grün; README, Bauplan, Architektur, CHANGELOG, Beispielkonfiguration.
