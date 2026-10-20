# Live-Bankanbindung & Belegabgleich, Paket 2 (Provider, Konten, Abruf) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Bankkonten werden einmal eingerichtet; `accounti bank abrufen` holt danach neue Umsätze
aller Konten ohne weitere Eingabe, ein zweiter Abruf erzeugt keine Dubletten, und Zugangsdaten
stehen nie im Klartext in der Datenbank. `accounti bank lauf` macht daraus den geplanten Lauf:
abrufen → offene Posten zuordnen → Belege abgleichen → kontieren.

**Spec:** [`docs/specs/2026-08-10-bankanbindung-live.md`](../specs/2026-08-10-bankanbindung-live.md),
Abschnitte 4.1, 4.2, 4.5 · Akzeptanzkriterien 2, 5, 6 · **Baut auf:** [Paket 1](2026-10-23-bankanbindung-paket-1-belegabgleich.md)

```
Bankkonto (IBAN, Sachkonto, Provider, Einstellungen, Zugang verschlüsselt, Abrufstand, Zustand)
   │  accounti bank abrufen
   ▼
Provider-Registry ── datei (Ordner mit Kontoauszügen, CSV-Profile aus Baustein 1)
   │               └─ fints (Paket 3) · psd2 (später)
   ▼
Dublettenschutz: Schlüssel aus Konto, Datum, Betrag, Verwendungszweck, Gegenpartei + laufende
Nummer gleicher Umsätze → zweiter Abruf, überlappender Zeitraum, doppelter Import: nichts doppelt
   ▼
Transaktion (mit Bankkonto und dessen Sachkonto) ─▶ bank lauf: zuordnen → abgleichen → kontieren
```

---

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Verschlüsselung | AES-GCM (`cryptography` 50.0.2) mit 256-Bit-Schlüssel aus `ACCOUNTI_SCHLUESSEL`; die Konto-ID ist zusätzliche authentifizierte Angabe | Klartext nie in der DB (Akzeptanz 5); ein Chiffrat lässt sich nicht einem anderen Konto unterschieben |
| Schlüssel | `accounti bank schluessel` erzeugt einen; ohne Schlüssel gibt es keinen Zugriff auf gespeicherte Zugänge — klare Meldung statt Klartext-Rückfall | Schlüssel gehört in die Umgebung, nicht in Dateien des Projekts |
| Dubletten | Schlüssel = SHA-256 über Konto, Datum, Betrag, normalisierten Verwendungszweck, Gegen-IBAN/-Name und die laufende Nummer gleicher Umsätze im Abruf; Spalte mit Unique-Index | zwei echte gleiche Umsätze am selben Tag bleiben zwei; derselbe Umsatz aus zwei Abrufen bleibt einer (Akzeptanz 2) |
| `import bank` | nutzt denselben Dublettenschutz; `--konto IBAN` ordnet einem eingerichteten Konto zu | behebt: zweimal dieselbe CSV importiert ergab alles doppelt |
| Provider | Registry + Basisklasse (`felder`, `geheime_felder`, `abrufen(konto, zugang, ab)`); Starke Kundenauthentifizierung als `FreigabeNoetig` → Zustand am Konto, kein Abbruch der anderen Konten | Spec 5: als Zustand gemeldet, nicht als Fehler |
| Datei-Provider | liest alle Kontoauszugsdateien eines Ordners mit den CSV-Profilen aus Baustein 1; Doppeltes fängt der Dublettenschutz | Fallback und Notausgang ohne Bankverbindung (Akzeptanz 6) |
| Abrufstand | Abruf ab letztem Stand minus 14 Tage Überlappung | Banken buchen nach; der Dublettenschutz macht die Überlappung harmlos |
| Sachkonto | Umsätze tragen das Sachkonto ihres Bankkontos; Kontierung, Ausgleich und Kontierung mit Beleg buchen dagegen statt pauschal gegen `buchhaltung.bank_konto` | mehrere Konten (Giro, zweites Giro, Kreditkarte) |
| Lauf | `bank lauf` = abrufen → `opos zuordnen` → `bank abgleich` → `classify` (LLM nur mit `--llm`); Ergebnis je Schritt; idempotent | für Cron/Timer; zweiter Lauf ändert nichts |

## Aufgaben

- [x] **Tresor** (`bank/tresor.py`): Schlüssel erzeugen, ver-/entschlüsseln, falscher Schlüssel, manipuliertes Chiffrat, fremdes Konto, fehlender Schlüssel (`tests/test_bank_tresor.py`).
- [x] **Dublettenschutz** (`bank/dubletten.py`): gleiche Umsätze im Abruf, Wiederholung, Überlappung mit zusätzlichem gleichem Umsatz (`tests/test_bank_dubletten.py`).
- [x] **Modelle und Persistenz:** `Bankkonto`, Transaktion mit Bankkonto, Sachkonto und Dublettenschlüssel; Tabellen, Migration; Repository.
- [x] **Provider und Datei-Provider** (`bank/provider.py`, `bank/datei.py`) (`tests/test_bank_provider.py`).
- [x] **Abruf und Lauf** (`bank/lauf.py`): Akzeptanz 2, 5, 6 als Tests; Freigabe nötig als Zustand; Sachkonto des Bankkontos in Kontierung, Ausgleich und Kontierung mit Beleg (`tests/test_bank_lauf.py`).
- [x] **CLI:** `bank schluessel`, `bank verbinde`, `bank konten`, `bank abrufen`, `bank lauf`; `import bank` mit Dublettenschutz und `--konto` (`tests/test_cli_bank_konten.py`).
- [x] **Abschluss:** `pytest`, `ruff` (ohne Cache), `mypy` grün; README, Bauplan, Architektur, CHANGELOG, Beispielkonfiguration.
