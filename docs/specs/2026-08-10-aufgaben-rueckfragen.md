# Spec: Aufgaben & Rückfragen

- **Status:** Entwurf (2026-08-10)
- **Baustein:** 8 von 12 (siehe [Bauplan](../bauplan.md))
- **Ziel-Branch:** `feat/aufgaben-rueckfragen`

## 1. Kontext

accounti erzeugt an vielen Stellen Arbeit für Menschen: eine Buchung unterhalb der
Confidence-Schwelle, ein Beleg, dessen OCR nichts hergab, ein fehlender Beleg aus der
Vollständigkeitsprüfung, ein Zahlungslauf, der eine Freigabe braucht, ein Bankabruf, der eine TAN
erwartet.

Diese Arbeit liegt heute verstreut in Listen, die man kennen muss. Was fehlt, ist ein gemeinsamer
Ort: eine Aufgabe, die weiß, woran sie hängt, wer zuständig ist und bis wann sie erledigt sein
sollte — und ein Weg, eine Rückfrage direkt am Beleg zu klären statt in einer Mailkette, in der
zwei Wochen später niemand mehr weiß, welche Rechnung gemeint war.

Wichtig zur Abgrenzung: Das ist ein **internes** Werkzeug für die eigene Buchhaltung. Ein Portal
für externe Mandanten ist ausdrücklich kein Ziel (siehe [Bauplan, Nicht-Ziele](../bauplan.md#nicht-ziele)).

## 2. Ziel

> Alles, was ein Mensch entscheiden muss, landet als Aufgabe an einem Ort — mit Bezug zum Objekt,
> Zuständigkeit, Frist und Verlauf. Rückfragen werden am Beleg geführt, nicht per E-Mail.

## 3. Pipeline

```
   Quellen                              Aufgabe                     Abschluss
   ───────                              ───────                     ─────────
Kontierung unsicher      ┐
Beleg unlesbar           │
Beleg fehlt (Baustein 7) ├──▶  Aufgabe erzeugt  ──▶  zugewiesen  ──▶  erledigt
Zahlungslauf freizugeben │      ├─ Bezug (Beleg / Buchung /          │
Bank braucht Freigabe    │      │   Posten / Lauf)                   │
Neuer Kontakt zu prüfen  ┘      ├─ Fälligkeit                        │
                                ├─ Zuständigkeit                     │
                                └─ Verlauf (Kommentare)              │
                                        │                            │
                                        ▼                            │
                                   Erinnerung                        │
                                   (Frist, Eskalation)               │
                                        │                            │
                                        ▼                            │
                                 Benachrichtigung                    │
                                 (E-Mail / Webhook)                  │
                                                                     ▼
                                                        automatisch schließen,
                                                        wenn der Anlass entfällt
```

Der letzte Pfeil ist der wichtigste: Eine Aufgabe „Beleg fehlt" schließt sich selbst, sobald der
Beleg eintrifft und zugeordnet wird. Aufgabenlisten, die nur wachsen, werden ignoriert.

## 4. Komponenten & Arbeitspakete

### 4.1 `aufgaben/modell.py` *(neu)*

```
Aufgabe                        Kommentar
───────                        ─────────
id                             id
art (prüfung, beleg_fehlt,     aufgabe_id / objekt_ref
     freigabe, rückfrage, …)   autor
titel / beschreibung           text
objekt_typ / objekt_id         erstellt_am
zustaendig                     anhang_beleg_id
faellig_am
status (offen, in_arbeit,
        wartet, erledigt,
        hinfaellig)
prioritaet
erzeugt_von (Regel/System)
quittiert_von / erledigt_am
```

Kommentare hängen wahlweise an einer Aufgabe oder direkt an einem Objekt (Beleg, Buchungssatz,
offener Posten) — eine Rückfrage zu einer Rechnung soll auch dann am Beleg stehen, wenn nie eine
Aufgabe daraus wurde.

### 4.2 `aufgaben/erzeugung.py` *(neu)*

Andere Bausteine erzeugen Aufgaben über eine schmale Schnittstelle mit einem **Idempotenzschlüssel**
aus Art und Objekt. Ohne den entstünde bei jedem Prüflauf eine neue Aufgabe für denselben fehlenden
Beleg. Ein zweiter Aufruf aktualisiert stattdessen die bestehende Aufgabe.

Gegenstück: `schliesse_wenn_erledigt(art, objekt)` — von der Prüfung und vom Abgleich aufgerufen,
sobald der Anlass entfallen ist. Solche Aufgaben enden als `hinfaellig`, nicht als `erledigt`; der
Unterschied ist für die Auswertung relevant.

### 4.3 `aufgaben/erinnerung.py` *(neu)*

Fristen mit Eskalationsstufen, konfigurierbar je Aufgabenart. Erinnerungen laufen im selben
geplanten Lauf wie der Bankabruf aus Baustein 5.

### 4.4 `aufgaben/benachrichtigung.py` *(neu)*

Kanäle als Registry, wie überall im Projekt: E-Mail zuerst, Webhook für Anbindung an vorhandene
Werkzeuge. Tagesübersicht statt Einzelmeldung ist der Default — eine Buchhaltungssoftware, die
zwanzig Mails am Tag schickt, wird stummgeschaltet und damit nutzlos.

### 4.5 `aufgaben/zustaendigkeit.py` *(neu)*

Zuweisung an Benutzer (aus Baustein 10) oder an eine Rolle. Regeln der Art „alle Aufgaben zu
Belegen der Gesellschaft X gehen an Y" als Konfiguration. Ohne Regel bleibt die Aufgabe unzugewiesen
und taucht in der gemeinsamen Liste auf — unzugewiesen ist ein sichtbarer Zustand, kein
verschwundener.

### 4.6 CLI

```bash
accounti aufgaben liste --offen --zustaendig ich
accounti aufgaben zeige 42                       # inkl. Verlauf und Bezugsobjekt
accounti aufgaben zuweisen 42 --an jan
accounti aufgaben kommentieren 42 --text "Beim Lieferanten angefragt"
accounti aufgaben erledigen 42
accounti aufgaben erinnern                        # fällige Erinnerungen versenden
```

## 5. Tech-Entscheidungen (fix)

| Thema | Entscheidung |
|-------|--------------|
| Erzeugung | Idempotent über (Art, Objekt) — kein Aufgaben-Wildwuchs bei wiederholten Läufen |
| Abschluss | Automatisch `hinfaellig`, wenn der Anlass entfällt |
| Kommentare | An Aufgabe **oder** direkt am Objekt |
| Benachrichtigung | Kanal-Registry; Tagesübersicht als Default |
| Zuständigkeit | Benutzer oder Rolle; unzugewiesen ist ein sichtbarer Zustand |
| Abgrenzung | Intern. Kein externes Portal, keine Fremdnutzerkonten |

## 6. Teststrategie

- Idempotenz: Zwei Prüfläufe über denselben Zeitraum erzeugen eine Aufgabe, nicht zwei.
- Selbstabschluss: Beleg nachreichen → Aufgabe wird `hinfaellig`, ohne dass jemand sie anfasst.
- Eskalation gegen feste Stichtage.
- Benachrichtigungskanäle gemockt; geprüft wird die Bündelung zur Tagesübersicht.
- Kommentare an Objekten ohne Aufgabe.

## 7. Akzeptanzkriterien

1. Eine Buchung unterhalb der Confidence-Schwelle erzeugt genau eine Aufgabe mit Bezug zur Buchung.
2. Ein wiederholter Prüflauf verdoppelt die Aufgaben nicht.
3. Trifft der fehlende Beleg ein, schließt sich die Aufgabe von selbst als `hinfaellig`.
4. Eine Rückfrage lässt sich am Beleg festhalten und ist dort später auffindbar.
5. Fällige Aufgaben landen in einer gebündelten Tagesübersicht, nicht in Einzelmails.
6. Eine unzugewiesene Aufgabe ist in der gemeinsamen Liste sichtbar.

## 8. Ausdrücklich NICHT in diesem Baustein

Externes Mandanten- oder Kundenportal · Chat in Echtzeit · Rechteverwaltung und Benutzerkonten
(Baustein 10) · Zeiterfassung · Anbindung externer Aufgabenwerkzeuge über das Webhook hinaus.
