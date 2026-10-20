# Kreditoren, Debitoren & offene Posten, Paket 3 (USt-IdNr.-Prüfung) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Die Regel „EU + B2B mit USt-IdNr. → 0 %“ stützt sich nicht mehr auf ein eingetipptes Feld,
sondern auf eine qualifizierte Bestätigung des Bundeszentralamts für Steuern (§ 18e UStG). Jede
Abfrage landet in einem revisionssicheren Protokoll. Ohne aktuelle Bestätigung stellt accounti
keine steuerfreie innergemeinschaftliche Lieferung (Kategorie K) und keine Reverse-Charge-Leistung
(AE) aus und bucht solche Erlöse nicht automatisch.

**Spec:** [`docs/specs/2026-08-10-kreditoren-debitoren-opos.md`](../specs/2026-08-10-kreditoren-debitoren-opos.md),
Abschnitte 4.2 und 4.7 · Akzeptanzkriterium 7 · **Baut auf:** [Paket 1](2026-10-20-kontakte-opos-paket-1.md),
[Paket 2](2026-10-21-kontakte-opos-paket-2-zahlungen.md)

## Schnittstelle (recherchiert am 20.10.2026)

Das BZSt hat die XML-RPC-Schnittstelle (`evatr.bff-online.de`, `evatrRPC`) zum **30.11.2025
abgeschaltet**. Seit dem **01.07.2025** gibt es die eVatR-REST-API, ohne Anmeldung:

| | |
|---|---|
| Abfrage | `POST https://api.evatr.vies.bzst.de/app/v1/abfrage`, JSON |
| Anfrage | `anfragendeUstid` (eigene DE-Nummer), `angefragteUstid`; für die qualifizierte Abfrage zusätzlich `firmenname` und `ort` (Pflicht), `strasse`, `plz` (optional) |
| Antwort | `id` (technische ID), `anfrageZeitpunkt` (ISO mit Zeitzone), `status` (`evatr-…`), `gueltigAb`, `gueltigBis`, `ergFirmenname`, `ergStrasse`, `ergPlz`, `ergOrt` (A stimmt · B stimmt nicht · C nicht angefragt · D vom Mitgliedstaat nicht mitgeteilt) |
| HTTP | 200 Ergebnis (0000 gültig, 2002/2006 ungültig mit Zeitraum, 2008 gültig mit Besonderheit) · 400 Syntax/Pflichtfelder · 403 nicht berechtigt (z.B. DE an DE) · 404 nicht vergeben (2001) bzw. eigene Nummer ungültig (2005) · 500/503 Störung. Fehlerantworten haben dieselbe JSON-Form |
| Hilfen | `GET /app/v1/info/statusmeldungen` (Meldungstexte), `GET /app/v1/info/eu_mitgliedstaaten` (VIES-Verfügbarkeit) |
| Doku | `https://api.evatr.vies.bzst.de/api-docs` (OpenAPI 3.0.1, „eVATR API“ v1.2.3); Testwerte `DE123456789` / `ATU12345678` liefern eine Beispielantwort |
| Nachweis | Laut BZSt wird die qualifizierte Abfrage über die Schnittstelle durch den empfangenen Datensatz nachgewiesen — deshalb wird die Antwort roh aufbewahrt |

```
accounti kontakte pruefe-ustid 10001          accounti rechnung ausstellen <ID>
            │                                            │ K oder AE und keine aktuelle Bestätigung
            ▼                                            ▼
  kontakte/ustid.py  ── POST /app/v1/abfrage ──▶  BZSt eVatR
            │
            ▼
  Protokoll ustid_pruefungen (nur anfügen, Hash-Kette, eigene Transaktion)
            │
            ├─▶ stelle_aus:      K/AE ohne Bestätigung → AusstellungError mit Grund
            └─▶ opos verbuchen:  K/AE ohne Bestätigung → zur Prüfung mit Grund
```

---

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| HTTP | Standardbibliothek (`urllib`), Zeitlimit 60 s, URL über `ustid_pruefung.url` oder `ACCOUNTI_EVATR_URL` überschreibbar | keine neue Abhängigkeit; VIES-Rückfragen dauern; Tests laufen gegen einen lokalen Server |
| Abfrageart | qualifiziert, sobald Name und Ort bekannt sind; `--einfach` erzwingt die einfache Abfrage (Ausweg bei evatr-0008) | Spec 4.2: qualifizierte Bestätigung |
| Bestätigt | `evatr-0000` aus einer qualifizierten Abfrage, Name und Ort nicht „B“. „D“ (Mitgliedstaat liefert nicht) wird akzeptiert, „B“ bei Straße/PLZ ist nur ein Hinweis. `evatr-2008` gilt als nicht bestätigt (Rückfrage beim BZSt) | Vertrauensschutz (§ 6a Abs. 4 UStG) hängt an Name und Ort |
| Aktualität | Bestätigt ist, wer innerhalb von `ustid_pruefung.max_alter_tage` (Standard 30) vor dem Rechnungsdatum bestätigt wurde. Es zählt die jüngste aussagekräftige Antwort: eine spätere Ungültigkeit sticht eine frühere Bestätigung; technische Fehler (5xx, Netz) zählen nicht | Stammkunden monatlich statt bei jeder Rechnung; eine Störung beim BZSt entwertet keine gültige Bestätigung |
| Protokoll | Tabelle `ustid_pruefungen`, nur anfügen: laufende Nummer, Zeitpunkt, Anfrage und Antwort roh, BZSt-Zeitstempel und -ID, Status, Ergebnisse, `aufbewahren_bis` (§ 147 AO). Auch gescheiterte Abfragen werden protokolliert | Nachweis „zum Zeitpunkt der Lieferung geprüft“ |
| Unveränderbar | SHA-256-Hash-Kette über jeden Eintrag samt Vorgänger-Hash; Änderungen und Löschungen über das ORM verboten; unter SQLite zusätzlich Trigger in der Datenbank. `ustid-protokoll` prüft Kette und Lückenlosigkeit | Manipulationen und Lücken fallen auf (Spec 6) |
| Eigene Transaktion | Protokolleinträge werden sofort festgeschrieben, unabhängig davon, ob die Rechnung danach ausgestellt wird | ein Rollback beim Ausstellen darf den Nachweis nicht verschlucken |
| Sperre Ausstellen | `stelle_aus` verweigert K und AE ohne aktuelle Bestätigung; `rechnung ausstellen` fragt vorher selbst qualifiziert an, wenn keine aktuelle Bestätigung vorliegt | Akzeptanz 7; die Rechnungsnummer bleibt frei |
| Sperre Verbuchen | `opos verbuchen` setzt Erlöse auf 8125/8338 ohne aktuelle Bestätigung auf „zur Prüfung“ und nennt den Grund; keine Netzabfrage | Akzeptanz 7 auch für Ausgangsrechnungen aus anderen Programmen |
| Inländische Nummern | DE-Nummern werden nicht angefragt (das BZSt bestätigt nur ausländische, evatr-0006); die eigene Nummer muss mit DE beginnen | sonst nur vermeidbare Fehlversuche im Protokoll |
| Schreibweise | Leerzeichen, Punkte und Bindestriche entfernt, Großbuchstaben, GR → EL; zulässig sind die Länderkennzeichen der BZSt-Liste (inkl. EL, XI) | so erwartet VIES die Nummer |
| Meldungstexte | amtliche Liste aus `/v1/info/statusmeldungen` im Code; unbekannte Codes werden roh angezeigt | Gründe auch ohne Netz lesbar |
| Postgres | ORM-Sperre und Hash-Kette gelten; einen Datenbank-Trigger gibt es vorerst nur für SQLite | ohne Postgres-Testumgebung kein ungetesteter Trigger |

## Aufgaben

- [x] **Abfrage auswerten** (`kontakte/ustid.py`, rein): Schreibweise, Länderkennzeichen, Anfrage-JSON einfach/qualifiziert, Antwort lesen (alle Status, Fehlerantworten, unlesbare Antwort), Bewertung bestätigt/ungültig/Fehler mit Grund (`tests/test_ustid.py`).
- [x] **Client** (`EvatrClient`): echte HTTP-Aufrufe gegen einen lokalen Server — 200, 404 mit JSON-Body, 503, keine Verbindung, Zeitüberschreitung (`tests/test_ustid_client.py`).
- [x] **Protokoll:** Modell `UstIdPruefung`, Tabelle, Migration (mit SQLite-Trigger); `pruefe_ustid()` fragt an und protokolliert, auch Fehlschläge; Hash-Kette; Änderung und Löschung scheitern; `pruefe_protokoll()` erkennt geänderte, gelöschte und umsortierte Einträge (`tests/test_ustid_protokoll.py`).
- [x] **Aktualität:** `aktuelle_bestaetigung(session, ust_id, stichtag, max_alter_tage)` — jüngste aussagekräftige Antwort zählt, einfache allein reicht nicht, Fehler zählen nicht.
- [x] **Akzeptanz 7:** `stelle_aus` verweigert K/AE ohne Bestätigung mit Grund, Nummer bleibt frei; mit Bestätigung wie bisher. `opos verbuchen` bucht K/AE ohne Bestätigung zur Prüfung mit Grund (`tests/test_ausstellung.py`, `tests/test_opos_verbuchung.py`).
- [x] **CLI:** `kontakte pruefe-ustid <KONTO> [--einfach]`, `kontakte ustid-protokoll [UST_ID] [--csv DATEI]` mit Integritätsprüfung, letzte Prüfung in `kontakte zeigen`, automatische Abfrage in `rechnung ausstellen` (`tests/test_cli_ustid.py`).
- [x] **Echtabfrage:** Test mit den Testwerten des BZSt, nur mit `ACCOUNTI_EVATR_LIVE=1` (nicht in der CI).
- [x] **Abschluss:** `pytest`, `ruff` (ohne Cache), `mypy` grün; README, Bauplan, Architektur, CHANGELOG, Beispielkonfiguration.
