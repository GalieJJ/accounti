# Spec: Supervision-Web-UI, Auth & Betrieb

- **Status:** Entwurf (2026-08-10)
- **Baustein:** 10 von 12 (siehe [Bauplan](../bauplan.md))
- **Ziel-Branch:** `feat/web-ui-auth-betrieb`

## 1. Kontext

accounti ist bislang ein Kommandozeilenwerkzeug. Für Import, Export und geplante Läufe ist das
genau richtig. Für die eine Tätigkeit, die den Kern des Produktversprechens ausmacht — das Prüfen
und Freigeben von Vorschlägen — ist es das nicht: Wer eine unsichere Kontierung beurteilen will,
muss den Beleg sehen, und ein Beleg ist ein Bild.

Dazu kommt: Sobald mehr als eine Person mit dem System arbeitet, brauchen Aufgaben (Baustein 8),
Freigaben (Baustein 6) und das Journal (Baustein 7) benannte Benutzer. Bis heute gibt es keine.
Das Feld `geprueft_von` in `models/` ist ein freier Text.

## 2. Ziel

> Vorschläge werden im Browser geprüft — Beleg links, Buchungsvorschlag rechts, Korrektur in einem
> Schritt. Mehrere Benutzer arbeiten getrennt und nachvollziehbar. Der Betrieb ist mit einem Befehl
> aufgesetzt und gesichert.

## 3. Aufbau

```
   Browser (HTMX + Jinja2, kein Build-Schritt)
        │
        ▼
   FastAPI  ── api/
   ├─ /pruefen        Supervisions-Queue: Beleg | Vorschlag | Korrektur
   ├─ /belege         Eingang, Archiv, Suche
   ├─ /opos           offene Posten, Fälligkeitsstaffel
   ├─ /zahlung        Vorschlagsliste, Freigabe
   ├─ /aufgaben       Liste, Zuweisung, Kommentare
   ├─ /auswertungen   BWA, Vorjahresvergleich, Summen und Salden
   ├─ /pruefung       Befunde aus Baustein 7
   └─ /einstellungen  Gesellschaften, Konten, Regeln, Benutzer
        │
        ▼
   auth/  ── Benutzer, Rollen, Sitzungen, 2FA
        │
        ▼
   bestehende Module (unverändert)
```

Die Oberfläche ruft dieselben Funktionen auf wie die CLI. Es gibt keine Logik, die nur im Browser
existiert — sonst zerfällt das Produkt in zwei Programme, die sich langsam auseinanderentwickeln.

## 4. Komponenten & Arbeitspakete

### 4.1 `auth/` — Benutzer, Rollen, Sitzungen *(neu)*

Benutzer mit Passwort-Hash, Rollen, Zwei-Faktor-Authentifizierung über zeitbasierte Einmalcodes,
Wiederherstellungscodes, Sitzungsverwaltung.

Rollen als grobe Vorgaben, verfeinerbar: `betrachter` (nur lesen), `buchhalter` (erfassen, prüfen,
korrigieren), `freigeber` (Zahlungsläufe und Steuermeldungen freigeben), `verwalter`
(Einstellungen, Benutzer). Die Trennung von `buchhalter` und `freigeber` ist die Voraussetzung
dafür, dass das Vier-Augen-Prinzip aus Baustein 6 überhaupt greifen kann.

Jede Aktion, die im Journal landet, trägt ab hier einen echten Benutzer statt einer freien
Zeichenkette.

### 4.2 `api/pruefen` — Supervisions-Queue *(neu, Kern der Oberfläche)*

Die eine Ansicht, die das Produkt trägt: links die Belegvorschau, rechts der Buchungsvorschlag mit
Konto, Steuerschlüssel, Betrag, Confidence und **der Begründung, die die Klassifikation
mitgeliefert hat**. Korrigieren, freigeben oder zurückstellen in einem Schritt, Tastaturbedienung
für schnelles Durcharbeiten.

Eine Korrektur bietet unmittelbar an, daraus eine Regel zu machen — das ist die Lernschleife aus
`docs/architektur.md`, die bislang nur in der CLI existiert. Sie hier sichtbar zu machen ist der
Grund, warum das System mit der Zeit weniger Rückfragen stellt.

### 4.3 `api/auswertungen` *(neu)*

BWA mit Vorjahresvergleich (Berechnung liegt in `bwa/` bereits vor), Summen- und Saldenliste,
Kontenblätter mit Absprung zum Beleg, OPOS-Auswertungen. Export als CSV und PDF.

### 4.4 Mehrere Gesellschaften *(Erweiterung)*

Das Datenmodell bekommt eine Gesellschaft als Dimension: eigene Nummernkreise, eigener
Kontenrahmen, eigenes Wirtschaftsjahr, eigene Bankkonten. Der Wechsel geschieht in der Oberfläche
oder per Parameter in der CLI.

Gemeint sind ausdrücklich **eigene** Gesellschaften — kein Mandantenportal für fremde Firmen
(siehe [Bauplan, Nicht-Ziele](../bauplan.md#nicht-ziele)).

### 4.5 Zweisprachigkeit *(neu)*

Oberfläche auf Deutsch und Englisch. Fachbegriffe bleiben deutsch, wo es keine tragfähige
Entsprechung gibt — „Buchungssatz" wird nicht zu „booking record". Code und Datenmodell bleiben wie
bisher deutschsprachig benannt.

### 4.6 Betrieb *(neu)*

- `docker-compose.yml` mit Anwendung, PostgreSQL und dem geplanten Lauf aus Baustein 5
- Konfiguration über Umgebungsvariablen, Geheimnisse nie im Abbild
- Verschlüsselte Sicherung von Datenbank **und** Belegarchiv; ein Wiederherstellungstest ist Teil
  der Dokumentation, nicht bloß der Sicherungsbefehl
- Aufbewahrungs- und Löschkonzept, das die Zehnjahresfrist kennt
- Reverse-Proxy mit TLS als dokumentiertes Beispiel
- Protokollierung ohne personenbezogene Inhalte; Zugangsdaten und Belegtexte erscheinen nie im Log

### 4.7 CLI-Ergänzungen

```bash
accounti benutzer anlegen --name jan --rolle buchhalter
accounti benutzer 2fa jan                        # Einrichtung, Wiederherstellungscodes
accounti gesellschaft liste
accounti serve --host 0.0.0.0 --port 8000
```

## 5. Tech-Entscheidungen (fix)

| Thema | Entscheidung |
|-------|--------------|
| Stack | FastAPI + Jinja2 + HTMX, kein Build-Schritt (Entscheidung steht bereits im README) |
| Logik | Oberfläche ruft dieselben Funktionen wie die CLI; keine UI-eigene Logik |
| Auth | Sitzungen mit Cookie, 2FA über zeitbasierte Einmalcodes, Wiederherstellungscodes |
| Rollen | `betrachter` / `buchhalter` / `freigeber` / `verwalter`; Trennung trägt das Vier-Augen-Prinzip |
| Mehrfirmen | Gesellschaft als Dimension im Datenmodell; keine fremden Mandanten |
| Sprachen | Deutsch und Englisch in der Oberfläche; Code bleibt deutsch benannt |
| Betrieb | Docker Compose, Geheimnisse aus der Umgebung, verschlüsselte Sicherungen |

## 6. Teststrategie

- Berechtigungen als Matrix: jede Rolle gegen jeden Endpunkt, Erwartung erlaubt/verweigert.
- Trennung der Gesellschaften: Ein Benutzer der Gesellschaft A sieht keine Daten von B — mit einem
  Test, der das negativ prüft.
- 2FA: Anmeldung ohne zweiten Faktor scheitert; Wiederherstellungscode funktioniert genau einmal.
- Oberfläche über den Testclient; die Supervisions-Queue zusätzlich als Durchlauf: Vorschlag →
  Korrektur → Regel → erneuter Lauf trifft die Regel.
- Sicherung und Wiederherstellung als ausgeführter Test, nicht als Dokumentationssatz.
- Kein personenbezogener Inhalt im Log: Test gegen die Protokollausgabe.

## 7. Akzeptanzkriterien

1. Eine unsichere Buchung lässt sich im Browser mit Belegansicht prüfen, korrigieren und freigeben.
2. Aus einer Korrektur entsteht auf Wunsch eine Regel, die beim nächsten Lauf greift.
3. Ein `betrachter` kann nichts freigeben; ein `buchhalter` kann keinen Zahlungslauf freigeben.
4. Anmeldung ohne zweiten Faktor schlägt fehl.
5. Der Wechsel der Gesellschaft ändert alle Ansichten konsistent.
6. `docker compose up` startet Anwendung, Datenbank und geplanten Lauf.
7. Eine Sicherung lässt sich in eine leere Umgebung zurückspielen — Buchungen und Belege sind
   vollständig.

## 8. Ausdrücklich NICHT in diesem Baustein

Einzelrechteverwaltung unterhalb der Rollen · Anmeldung über externe Identitätsanbieter ·
mobile App · Mehrbetrieb für fremde Firmen · Themes und Gestaltungsoptionen.
