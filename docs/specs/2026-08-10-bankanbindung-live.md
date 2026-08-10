# Spec: Live-Bankanbindung & Belegabgleich

- **Status:** Entwurf (2026-08-10)
- **Baustein:** 5 von 12 (siehe [Bauplan](../bauplan.md))
- **Ziel-Branch:** `feat/bankanbindung-live`

## 1. Kontext

Baustein 1 liest Bankauszüge aus Dateien. Das heißt in der Praxis: jemand loggt sich ins
Onlinebanking ein, exportiert eine CSV, legt sie ab, startet den Import. Jeden Monat. Diese
Handarbeit ist genau das, was accounti eigentlich abschaffen soll — und sie ist der Grund, warum
Buchhaltung schubweise statt laufend passiert.

Der zweite, wichtigere Punkt: Solange Umsätze nur monatlich eintreffen, kann accounti Beleg und
Zahlung nicht zeitnah zusammenbringen. Der Abgleich ist aber die Stelle, an der die Kontierung
richtig gut wird — eine Transaktion mit zugeordnetem Beleg muss nicht geraten werden, sie ist
belegt.

## 2. Ziel

> Kontoumsätze kommen von selbst ins System, mehrmals täglich, aus allen Konten inklusive
> Kreditkarten. Jeder Umsatz wird mit dem passenden Beleg zusammengeführt, bevor kontiert wird.

## 3. Pipeline

```
                 ┌──────────────────────────────────────┐
                 │        Bank-Provider (steckbar)      │
                 │  ┌────────┐ ┌──────────┐ ┌────────┐  │
                 │  │ FinTS  │ │  PSD2-   │ │ Datei  │  │
                 │  │ /HBCI  │ │Aggregator│ │(Fallb.)│  │
                 │  └────┬───┘ └────┬─────┘ └───┬────┘  │
                 └───────┴──────────┴───────────┴───────┘
                                    │
                                    ▼
                      [1] Abruf (inkrementell, seit letztem Stand)
                                    │
                                    ▼
                      [2] Normalisierung → Transaktion
                                    │
                                    ▼
                      [3] Dublettenschutz (Bank-Referenz + Hash)
                                    │
                                    ▼
   Belege (Baustein 2/3) ──────▶ [4] ABGLEICH  Beleg ↔ Umsatz
                                    │   Stufe A: Referenz/Rechnungsnummer
                                    │   Stufe B: Betrag + Datum + Gegenpartei
                                    │   Stufe C: unscharf → Vorschlag
                                    ▼
                      [5] Kontierung (Baustein 1) — jetzt MIT Beleg
                                    │
                                    ▼
                      [6] Offene Posten ausgleichen (Baustein 4)
```

Der Abgleich sitzt bewusst **vor** der Kontierung. Eine Transaktion, deren Beleg bekannt ist,
kennt Positionen, Steuersätze und Lieferant — die Kontierung muss dann nichts mehr aus einem
Verwendungszweck ableiten. Das hebt die Trefferquote der Regel-Stufe deutlich und spart LLM-Aufrufe.

## 4. Komponenten & Arbeitspakete

### 4.1 `bank/provider.py` — Provider-Schnittstelle *(neu)*

Eine Basisklasse plus Registry, wie bei den Bank-Importern in Baustein 1. Ein Provider kann:
Konten auflisten, Umsätze ab einem Zeitpunkt abrufen, Saldo melden — und optional Zahlungen
einreichen (das nutzt Baustein 6).

| Provider | Rolle |
|----------|-------|
| `fints` | Direktverbindung zur Bank über FinTS/HBCI. Default für den Eigenbetrieb: keine dritte Partei sieht die Daten, keine laufenden Kosten |
| `psd2` | Kontoinformationsdienst als Aggregator. Deckt Banken ab, die FinTS nicht oder schlecht unterstützen, sowie viele Kreditkarten. Opt-in, weil ein Dritter mitliest |
| `datei` | Der bestehende Dateiimport aus Baustein 1, hinter dieselbe Schnittstelle gehängt. Bleibt Fallback und Notausgang |

Dass der Dateiimport zum Provider wird, hält die Pipeline hinter dem Abruf für alle Quellen
identisch — und stellt sicher, dass accounti ohne jede Bankverbindung vollständig nutzbar bleibt.

### 4.2 `bank/konten.py` — Bankkonten & Zugänge *(neu)*

Bankkonto mit IBAN, Bezeichnung, zugehörigem Sachkonto, Provider und Abrufstand. Zugangsdaten
(PIN, Client-Zertifikate, Tokens) werden **verschlüsselt** abgelegt, mit einem Schlüssel aus der
Umgebung, nie in der Datenbank im Klartext und nie in Logs. Das folgt der Zusage in
[Architektur, Sicherheit](../architektur.md#sicherheit), dass API-Schlüssel nicht in der Datenbank
landen.

Starke Kundenauthentifizierung: Der Abruf braucht je nach Bank periodisch eine TAN-Freigabe. Der
Provider meldet das als Zustand, statt still zu scheitern — die CLI fragt interaktiv nach, ein
automatischer Lauf legt den Abruf zurück und meldet ihn als Aufgabe (Baustein 8).

### 4.3 `bank/kreditkarte.py` *(neu)*

Kreditkartenumsätze kommen entweder über einen Provider oder als PDF-Abrechnung. Der PDF-Weg nutzt
die Positionsaufteilung aus Baustein 2: eine Abrechnung, viele Positionen. Die Sammelbelastung auf
dem Girokonto wird gegen die Summe der Einzelumsätze abgeglichen — stimmt sie nicht, ist das ein
Befund, kein gerundeter Restposten.

### 4.4 `bank/abgleich.py` — Beleg ↔ Umsatz *(neu)*

Dreistufig wie überall: Referenz, exakter Treffer, unscharfer Vorschlag mit Confidence. Der
unscharfe Fall nutzt Betragsnähe, Datumsfenster und Ähnlichkeit von Gegenpartei zu Lieferantenname.
Die zweite Stufe ist bewusst streng — ein falscher Abgleich ist teurer als ein fehlender, weil er
eine falsche Vorsteuer begründet.

Gegenrichtung: Umsätze ohne Beleg und Belege ohne Umsatz sind das Rohmaterial für die
Vollständigkeitsprüfung in Baustein 7.

### 4.5 `bank/lauf.py` — geplanter Abruf *(neu)*

Ein Lauf holt alle Konten ab, normalisiert, gleicht ab, kontiert und meldet ein Ergebnis. Läuft per
Cron oder Timer. Idempotent: Ein zweimal gestarteter Lauf erzeugt keine doppelten Transaktionen.

### 4.6 CLI

```bash
accounti bank konten                          # eingerichtete Konten + Abrufstand
accounti bank verbinde --provider fints       # Zugang einrichten (interaktiv, TAN)
accounti bank abrufen                         # alle Konten, inkrementell
accounti bank abgleich --period 2026-08       # Beleg ↔ Umsatz
accounti bank offen                           # Umsätze ohne Beleg, Belege ohne Umsatz
```

## 5. Tech-Entscheidungen (fix)

| Thema | Entscheidung |
|-------|--------------|
| Provider | Registry + Basisklasse; FinTS als Default, PSD2 opt-in, Datei als Fallback |
| Zugangsdaten | Verschlüsselt, Schlüssel aus der Umgebung, nie in Logs oder LLM-Prompts |
| Abruf | Inkrementell ab letztem Stand, idempotent, Dublettenschutz über Bank-Referenz |
| Reihenfolge | Abgleich **vor** Kontierung |
| Starke Authentifizierung | Als Zustand gemeldet, nicht als Fehler; automatischer Lauf erzeugt eine Aufgabe |
| Abgleich | Streng vor großzügig; unsichere Treffer sind Vorschläge |

## 6. Teststrategie

- Provider gegen aufgezeichnete Antworten getestet, nie gegen eine echte Bank im CI.
- Idempotenz: derselbe Abruf zweimal → gleiche Anzahl Transaktionen.
- Abgleich mit Fixtures, die typische Fallen enthalten: zwei Rechnungen über denselben Betrag am
  selben Tag, Zahlung mit Rundungsdifferenz, Gutschrift, Rücklastschrift.
- Verschlüsselung: Test stellt sicher, dass in der Datenbank kein Klartext-Zugangsdatum steht.
- Kreditkarten-Sammelbelastung gegen Summe der Einzelpositionen.

## 7. Akzeptanzkriterien

1. Nach einmaliger Einrichtung holt `accounti bank abrufen` neue Umsätze aller Konten ohne weitere
   Eingabe — abgesehen von der bankseitig geforderten Freigabe.
2. Ein zweiter Abruf im selben Zeitraum erzeugt keine Dubletten.
3. Ein Umsatz, zu dem ein Beleg vorliegt, wird zugeordnet und anschließend mit den Belegdaten
   kontiert — nachweisbar an einer höheren Regel-Trefferquote gegenüber dem Lauf ohne Beleg.
4. Zwei gleich hohe Rechnungen am selben Tag führen nicht zu einer willkürlichen Zuordnung,
   sondern zu zwei Vorschlägen.
5. In der Datenbank steht kein Zugangsdatum im Klartext.
6. Fällt der Provider aus, bleibt der Dateiimport vollständig nutzbar.

## 8. Ausdrücklich NICHT in diesem Baustein

Zahlungsausgang (Baustein 6) · Vollständigkeitsprüfung und Belegnachforderung (Baustein 7) ·
Liquiditätsprognose · Fremdwährungskonten · Wertpapierdepots.
