# accounti — Bauplan

Dieses Dokument ist die Landkarte des Projekts: Es beschreibt das Zielbild, zerlegt es in
eigenständige Bausteine und legt fest, in welcher Reihenfolge sie gebaut werden.

Jeder Baustein durchläuft denselben Weg: **Spec → Plan → Build**. Das Spec beschreibt *was* und
*warum* (`docs/specs/`), der Plan beschreibt *wie*, Schritt für Schritt und testgetrieben
(`docs/plans/`). Erst dann wird Code geschrieben.

---

## Zielbild

accounti soll die laufende Buchhaltung eines kleinen Unternehmens **vollständig im Haus** möglich
machen — von der Belegerfassung über die Kontierung und den Zahlungsverkehr bis zur Steuermeldung
und zum Jahresabschluss.

Der Weg dahin ist nicht „ein großes Buchhaltungsprogramm", sondern eine Kette klar getrennter
Stufen, die einzeln nützlich sind. Wer nur Bankauszüge kontieren will, nutzt Baustein 1 und ist
fertig. Wer die gesamte Strecke will, stapelt die Bausteine.

Zwei Dinge bleiben dabei unverhandelbar: **Nachvollziehbarkeit** — jede Buchung weiß, woher sie
kommt — und **der Mensch entscheidet**. Automatisierung erzeugt Vorschläge, keine vollendeten
Tatsachen.

---

## Bausteinkarte

| # | Baustein | Zielmodule | Status | Spec |
|---|----------|------------|--------|------|
| 1 | Bankauszug → Auto-Kontierung (Regeln + KI) → DATEV/CSV | `importers/` `klassifikation/` `buchung/` `export/` `db/` | ✅ fertig | [Spec](specs/2026-06-02-mvp-bank-auto-kontierung.md) |
| 2 | Belegerfassung & Dokumentenmanagement | `belege/` | 🔲 geplant | [Spec](specs/2026-08-10-belegerfassung.md) |
| 3 | E-Rechnung — Eingang & Ausgang | `erechnung/` | 🔲 geplant | [Spec](specs/2026-08-10-erechnung.md) |
| 4 | Kreditoren, Debitoren & offene Posten | `kontakte/` `opos/` | 🔲 geplant | [Spec](specs/2026-08-10-kreditoren-debitoren-opos.md) |
| 5 | Live-Bankanbindung & Belegabgleich | `bank/` | 🔲 geplant | [Spec](specs/2026-08-10-bankanbindung-live.md) |
| 6 | Zahlungsverkehr & Mahnwesen | `zahlung/` `mahnwesen/` | 🔲 geplant | [Spec](specs/2026-08-10-zahlungsverkehr-mahnwesen.md) |
| 7 | Belegvollständigkeit & Ordnungsmäßigkeit | `pruefung/` | 🔲 geplant | [Spec](specs/2026-08-10-belegvollstaendigkeit-gobd.md) |
| 8 | Aufgaben & Rückfragen | `aufgaben/` | 🔲 geplant | [Spec](specs/2026-08-10-aufgaben-rueckfragen.md) |
| 9 | Steuermeldungen & elektronische Übermittlung | `steuer/` `elster/` | 🟨 teilweise | [Spec](specs/2026-08-10-steuermeldungen-elster.md) |
| 10 | Supervision-Web-UI, Auth & Betrieb | `api/` `auth/` | 🔲 geplant | [Spec](specs/2026-08-10-web-ui-auth-betrieb.md) |
| 11 | Integrationen & Export | `importers/` `export/` `api/` | 🟨 teilweise | [Spec](specs/2026-08-10-integrationen-export.md) |
| 12 | Anlagenbuchhaltung & Jahresabschluss | `anlagen/` `abschluss/` | 🔲 geplant | [Spec](specs/2026-08-10-anlagen-jahresabschluss.md) |

Legende: ✅ fertig · 🟨 Grundlage vorhanden, Baustein nicht abgeschlossen · 🔲 geplant

**Baustein 9 ist teilweise fertig,** weil `steuer/umsatzsteuer.py`, `steuer/oss.py` und
`steuer/voranmeldung.py` die Kennziffern bereits berechnen — was fehlt, ist die Übermittlung.
**Baustein 11 ist teilweise fertig,** weil der DATEV-Buchungsstapel-Export existiert — was fehlt,
sind Stammdaten, Belege, Kontoauszüge und die Marktplatz-Importer.

---

## Abhängigkeiten

```
        ┌───────────────────────────────────────────┐
        │  1  Bank → Kontierung → Export  (fertig)  │
        └───────────────┬───────────────────────────┘
                        │
        ┌───────────────┴───────────┐
        ▼                           ▼
  ┌───────────┐              ┌─────────────┐
  │ 2 Belege  │              │ 5 Bank live │
  └─────┬─────┘              └──────┬──────┘
        ▼                           │
  ┌───────────┐                     │
  │ 3 E-Rech. │                     │
  └─────┬─────┘                     │
        └────────────┬──────────────┘
                     ▼
             ┌───────────────┐
             │ 4 OPOS / KRED │
             └───┬───────┬───┘
                 ▼       ▼
        ┌────────────┐  ┌──────────────┐
        │ 6 Zahlung  │  │ 9 Meldungen  │
        └────────────┘  └──────┬───────┘
                               ▼
                        ┌──────────────┐
                        │ 12 Abschluss │
                        └──────────────┘

  Querschnittlich, jederzeit einsetzbar:
  7 Prüfung (braucht 2 + 5)   ·   8 Aufgaben   ·   10 UI/Auth   ·   11 Integrationen
```

Kurz gesagt: Der Belegstrang (2→3) und der Bankstrang (1, 5) laufen in Baustein 4 zusammen. Erst
wenn offene Posten existieren, ergeben Zahlungsverkehr (6) und Jahresabschluss (12) Sinn.

---

## Phasen

| Release | Bausteine | Was danach möglich ist |
|---------|-----------|------------------------|
| **v0.1** Fundament | 1 | Bankauszug rein, kontierter DATEV-Stapel raus |
| **v0.2** Beleg & E-Rechnung | 2, 3 | Belege landen automatisch im System, E-Rechnungen werden gelesen und geschrieben |
| **v0.3** Personenkonten & Bank | 4, 5 | Kontoumsätze kommen von selbst, offene Posten sind sichtbar |
| **v0.4** Zahlung & Prüfung | 6, 7 | Rechnungen werden bezahlt und angemahnt, fehlende Belege fallen auf |
| **v0.5** Oberfläche & Betrieb | 8, 10 | Bedienung im Browser statt auf der Kommandozeile, Mehrbenutzerbetrieb |
| **v0.6** Integrationen | 11 | ERP- und Marktplatzdaten fließen ein, DATEV-Übergabe ist vollständig |
| **v1.0** Meldungen & Abschluss | 9, 12 | Voranmeldung geht elektronisch raus, AfA läuft, Jahresabschluss steht |

Die Reihenfolge ist eine Empfehlung, keine Zwangsjacke — wer nur den Steuerteil braucht, kann
Baustein 9 vorziehen, sobald 4 steht.

---

## Nicht-Ziele

Klar benennen, was accounti **nicht** wird, hält den Bauplan ehrlich:

- **Kein Kanzleiprodukt.** accounti ist für die eigene Buchhaltung gebaut — mehrere eigene
  Gesellschaften ja, ein Mandantenportal mit fremden Firmen nein. Das ist keine technische
  Beschränkung, sondern eine Produktentscheidung: Die Hilfeleistung in Steuersachen für Dritte ist
  in Deutschland ein reglementierter Beruf, die eigene Buchführung dagegen frei.
- **Keine Lohnbuchhaltung.** Entgeltabrechnung, Sozialversicherung und Meldewesen sind ein eigenes,
  großes Feld mit eigenen Zertifizierungsanforderungen. Bis v1.0 nicht im Bauplan.
- **Keine Steuerberatung.** accounti rechnet und meldet, es berät nicht. Fachliche
  Zweifelsfragen bleiben fachliche Zweifelsfragen.
- **Kein Warenwirtschaftssystem.** Artikel, Lager und Bestellwesen bleiben draußen; accounti liest
  aus solchen Systemen, ersetzt sie nicht.
- **Keine Kassensoftware.** Ein Kassenbuch führen ja (Baustein 12), ein TSE-zertifiziertes
  Kassensystem sein nein.

---

## Fachliche Leitplanken

Diese Anforderungen gelten quer über alle Bausteine und sind in jedem Spec mitzudenken:

**GoBD.** Buchungen sind unveränderbar: Korrekturen erfolgen als Storno mit Neubuchung, nie durch
Überschreiben. Das Journal ist fortlaufend und lückenlos. Jede Änderung ist protokolliert und einer
Person zuordenbar. Jede Buchung verweist auf ihren Beleg oder ist begründet belegfrei.

**Aufbewahrung.** Belege, Buchungen, Journale und Übermittlungsprotokolle sind zehn Jahre
aufzubewahren, im Originalformat und maschinell auswertbar. Ein Löschkonzept muss die Frist kennen,
statt sie zu ignorieren.

**Umsatzsteuer.** Pflichtangaben nach § 14 UStG, korrekte Behandlung von Inland, innergemeinschaftlichen
Lieferungen, Reverse-Charge und Drittland. Die Regeln stehen bereits in `steuer/` und sind die
Referenz für alle neuen Bausteine.

**DATEV-Formatkonformität.** Exporte müssen 1:1 importierbar sein. Der Maßstab ist eine echte
DATEV-Datei, nicht die Formatdokumentation — deshalb sind die Export-Tests als Golden-Tests gegen
anonymisierte Echt-Dateien gebaut.

**Datenschutz.** Self-Hosted ist der Default. Zugangsdaten werden verschlüsselt abgelegt.
LLM-Prompts enthalten keine echten Kontodaten, sondern maskierte Muster — siehe
[Architektur, Abschnitt Sicherheit](architektur.md#sicherheit).

---

## Verwandte Dokumente

- [Architektur](architektur.md) — Module, Datenmodell, Datenfluss, Erweiterungspunkte
- [Specs](specs/) — je Baustein: Ziel, Komponenten, Akzeptanzkriterien
- [Pläne](plans/) — je Baustein: testgetriebene Umsetzungsschritte
- [Mitmachen](../CONTRIBUTING.md) — wo Beiträge besonders gebraucht werden
