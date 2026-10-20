# Aufgaben & Rückfragen (Baustein 8) — Umsetzungsplan

> **Für agentische Umsetzer:** Aufgaben der Reihe nach, jede testgetrieben (Test zuerst, rot sehen,
> implementieren, grün sehen). Checkboxen (`- [ ]`) zum Abhaken.

**Ziel:** Alles, was ein Mensch entscheiden muss, landet als Aufgabe an einem Ort — mit Bezug zu
einem beliebigen Objekt (Buchung, Beleg, Transaktion, offener Posten, Kontakt, Bankkonto, später
Fristen und Zahlungsläufe), Zuständigkeit, Fälligkeit und Verlauf. Prüfläufe werten vorhandene
Daten aus und erzeugen Aufgaben idempotent; entfällt der Anlass, wird die Aufgabe von selbst
`hinfaellig`. Rückfragen stehen am Beleg. Fällige Aufgaben gehen einmal am Tag gebündelt hinaus
(E-Mail über den SMTP-Zugang aus `versand`, optional Webhook), nicht als Einzelmails.

**Spec:** [`docs/specs/2026-08-10-aufgaben-rueckfragen.md`](../specs/2026-08-10-aufgaben-rueckfragen.md),
Abschnitte 4.1–4.6 · Akzeptanzkriterien 1–6 · **Baut auf:** Baustein 1 (Buchungen mit
Confidence), Baustein 2 (Belege), Baustein 4 (Kontakte), Baustein 5 (`bank/abgleichslauf.py`:
`offen_in_der_bank`, Bankkonten mit Zustand), Baustein 3 (`erechnung/versand.py`: SMTP-Versand)

```
 vorhandene Daten                     Prüfläufe (aufgaben/prueflaeufe.py)          Aufgaben
 ────────────────                     ───────────────────────────────────          ────────
 Buchungen (Confidence, Status)  ──▶  kontierung_pruefen ─┐
 offen_in_der_bank (Bank 5)      ──▶  beleg_fehlt         │   melde_aufgabe()        aufgaben
 Belege zur Prüfung              ──▶  beleg_pruefen       ├─▶ (Idempotenzschlüssel ─▶ (offen, in_arbeit,
 Kontakte zur Prüfung            ──▶  kontakt_pruefen     │    art|objekt_typ|id)    wartet, erledigt,
 Bankkonten „Freigabe nötig“     ──▶  bank_freigabe      ─┘   Anlass weg → hinfaellig  hinfaellig)
 Bausteine 7, 9 … ───────────────────────────────────────────▶ melde_aufgabe / schliesse_wenn_erledigt
                                                                     │
 accounti aufgaben rueckfrage <Beleg> ──▶ aufgaben_kommentare ◀──────┤ Verlauf (append-only)
                                                                     ▼
                                   aufgaben erinnern: Stufen [0, 3, 7] Tage nach Fälligkeit,
                                   Eskalation, Tagesübersicht je Empfänger ──▶ Kanal-Registry
                                   (email über versand.smtp, webhook) ──▶ aufgaben_benachrichtigungen
```

---

## Recherche (Stand 20.10.2026)

| Thema | Ergebnis | Quelle |
|-------|----------|--------|
| Zeitgerechte Erfassung (GoBD Rz. 47, 48, 50) | Unbare Geschäftsvorfälle: Erfassung innerhalb von **zehn Tagen** unbedenklich (Rz. 47, in der Neufassung 2019 ohne BFH-Verweis beibehalten); Kasse täglich (Rz. 48); periodenweise Buchung der unbaren Vorfälle eines Monats bis Ablauf des Folgemonats nicht zu beanstanden, wenn die Unterlagen bis dahin gesichert sind (Rz. 50). Die zehn Tage sind keine starre Frist, sondern eine Unbedenklichkeitsgrenze | GoBD, BMF-Schreiben vom 28.11.2019, geändert am 11.03.2024 und 14.07.2025 (2. Änderung, betrifft Rz. 76, 118–127, nicht Rz. 47–50); Wortlaut nach [PSP, „Experten erläutern die GoBD – Zeitgerechtheit“](https://www.psp.eu/assets/pdfs/beitrag_expertenerlaeuterungen_gobd_zeitgerechtheit.pdf) und [Rödl & Partner zur Neufassung 2019](https://www.roedl.com/insights/2019-neufassung-bmf-buchfuehrung-details-aenderungen/); Änderungsstand: [KPMG zur 2. Änderung](https://kpmg.com/de/de/themen/2025/07/bmf-gobd-zweite-aenderung.html). Das BMF-PDF selbst war am 20.10.2026 nicht abrufbar (HTTP 503) |
| Aufbewahrung | § 147 Abs. 3 AO seit BEG IV (ab 2025): Bücher/Aufzeichnungen 10 Jahre, Buchungsbelege (Abs. 1 Nr. 4) 8 Jahre, sonstige steuerlich bedeutsame Unterlagen 6 Jahre | [gesetze.legal, § 147 AO](https://gesetze.legal/bund/ao/147), [IHK Ostwestfalen](https://www.ihk.de/ostwestfalen/recht-und-steuern/recht-von-a-z/aufbewahrungsfristen-7036558) |
| Automatische E-Mails | RFC 3834 Abschnitt 5: `Auto-Submitted: auto-generated` SOLL bei Nachrichten automatischer (oft periodischer) Prozesse gesetzt werden; Abwesenheitsnotizen antworten darauf nicht. `Precedence` wird ausdrücklich nicht empfohlen | [RFC 3834](https://datatracker.ietf.org/doc/html/rfc3834), [IANA-Registry](https://www.iana.org/assignments/auto-submitted-keywords/auto-submitted-keywords.xhtml) |
| Webhook-Format | Slack-Incoming-Webhook: `POST`, `Content-Type: application/json`, Body `{"text": "…"}`, Erfolg = HTTP 200 „ok“. Mattermost akzeptiert dasselbe (`text` Pflicht, Slack-Payloads werden übersetzt) | [Slack](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/), [Mattermost](https://developers.mattermost.com/integrate/webhooks/incoming/) |
| Lokaler SMTP-Testserver | `smtpd` ist seit Python 3.12 entfernt (PEP 594); `aiosmtpd` wäre eine neue Abhängigkeit. Ein minimaler Server nach RFC 5321 (EHLO/MAIL/RCPT/DATA/QUIT, Punkt-Maskierung) mit `socketserver` genügt für die Tests | [PEP 594](https://peps.python.org/pep-0594/), [RFC 5321](https://datatracker.ietf.org/doc/html/rfc5321) |

---

## Entscheidungen

| Thema | Entscheidung | Grund |
|-------|--------------|-------|
| Bezugsobjekt | `Objekt(typ, id)` mit freiem, kleingeschriebenem Typ (`buchung`, `beleg`, `transaktion`, `offener_posten`, `kontakt`, `bankkonto`, später z.B. `frist`) und Zeichenketten-ID; Beschreiber/Auflöser je Typ in einer Registry (`aufgaben/objekte.py`, `registriere_objekttyp`) | „beliebiges Objekt“ ohne Fremdschlüssel auf jede Tabelle; Baustein 9 kann Fristen wie `Objekt("frist", "ustva-2026-09")` anhängen, ohne hier etwas zu ändern |
| Aufgabenart | freier Bezeichner (`^[a-z][a-z0-9_]*$`), keine geschlossene Enum; Konstanten für die eigenen Arten | andere Bausteine bringen eigene Arten mit (`frist_ustva`, `zahlungslauf_freigeben`), ohne dieses Modul anzufassen |
| Idempotenz | Schlüssel `art|objekt_typ|objekt_id`, eindeutiger Index über alle Aufgaben (nicht nur aktive). Zweiter Aufruf aktualisiert Titel, Beschreibung, Priorität, Fälligkeit, Merkmale — nie Zuständigkeit oder Status. Gleichzeitiges Anlegen: `IntegrityError` im Savepoint → vorhandene Aufgabe laden und aktualisieren | Akzeptanz 2; der Index macht auch parallele Läufe sicher |
| Wiederkehrender Anlass | `hinfaellig` → wieder `offen` (Verlauf „Anlass besteht wieder“, Erinnerungsstufe zurück). `erledigt` bleibt erledigt; nur `melde_aufgabe(..., wieder_oeffnen=True)` öffnet sie (Rückfragen) | Das System schließt, was es geöffnet hat; die Entscheidung eines Menschen („Gebühr, braucht keinen Beleg“ → erledigt) überstimmt kein späterer Prüflauf |
| Abschluss | `erledigt` nur durch einen Menschen (`erledige`, mit `quittiert_von`), `hinfaellig` nur durch das System (`schliesse_wenn_erledigt`, Prüflauf) mit `abschluss_grund` | Spec 4.2: der Unterschied zählt für die Auswertung |
| Prüfläufe | Registry `PRUEFLAEUFE`; jeder Lauf besitzt eine Art, liefert Anlässe und optional den geprüften Umfang. Danach werden aktive Aufgaben dieses Laufs (`erzeugt_von = prueflauf:<name>`), deren Objekt im Umfang liegt und keinen Anlass mehr hat, `hinfaellig` | Akzeptanz 3 ohne Eingriff in `classify`, `bank abgleich`, `opos zuordnen`; ein Lauf über einen Monat schließt nichts außerhalb dieses Monats |
| `kontierung_pruefen` | Anlass: Buchung nicht von einem Menschen entschieden (nicht `geprueft`/`korrigiert`/`exportiert`) und Confidence < `pruefung.kontierung_schwelle` (Standard 0,95 = `auto_schwelle` in `buchung/mapper.py`) oder Status `pruefung`. Bezug: die Buchung | Akzeptanz 1; liest nur, was `classify` ohnehin speichert |
| `beleg_fehlt` | Anlass: Umsatz aus `offen_in_der_bank().umsaetze_ohne_beleg`, ab `beleg_fehlt_ab_betrag` (Standard 0,00) und nach `beleg_fehlt_nach_tagen` (Standard 0). Fällig: Umsatzdatum + 10 Tage. Gebühren u.ä. erledigt ein Mensch einmal mit Begründung | Akzeptanz 3; zehn Tage nach GoBD Rz. 47; die Belegfreiheit ist eine menschliche Entscheidung (Baustein 7 bringt später Schwellen und Regeln) |
| Weitere Quellen | `beleg_pruefen` (Beleg zur Prüfung, z.B. unlesbar), `kontakt_pruefen` (automatisch angelegter Kontakt), `bank_freigabe` (Konto verlangt TAN-Freigabe, Priorität hoch, fällig sofort) | stehen in der Spec-Pipeline und liegen als Zustand bereits in der Datenbank |
| Fälligkeit | ohne Angabe: Anlagetag + `fristen.<art>` (Standard 7, `beleg_fehlt`/`kontierung_pruefen`/`beleg_pruefen` 10, `bank_freigabe` 0); Prüfläufe rechnen vom Datum des Objekts | jede Aufgabe hat eine Frist; keine Steuerfristen hier — die rechnet Baustein 9 in `steuer/` und übergibt `faellig_am` |
| Zuständigkeit | Benutzer **oder** Rolle (zwei Felder); Regeln `zustaendigkeit: [{wenn: {art, objekt_typ, <merkmal>…}, an | rolle}]` mit Platzhaltern (`fnmatch`), erste passende gewinnt, nur beim Anlegen. Ohne Treffer: unzugewiesen = gemeinsame Liste | Spec 4.5; „Belege der Gesellschaft X an Y“ geht über das Merkmal `gesellschaft`, sobald ein Baustein es mitliefert |
| „ich“ | `aufgaben.ich`, sonst `ACCOUNTI_BENUTZER`, sonst Login-Name; Rollenmitglieder aus `aufgaben.rollen` | Benutzerkonten kommen erst mit Baustein 10 |
| Kommentare | eine Tabelle für Kommentar, Rückfrage und Ereignis (Verlauf); hängt an Aufgabe und/oder Objekt — ein Kommentar an einer Aufgabe trägt deren Objekt mit, ist also auch am Beleg auffindbar. Nur anfügen (ORM-Sperre) | Spec 4.1 und 5; Akzeptanz 4; ein Verlauf, den man umschreiben kann, ist keiner |
| Rückfrage | `halte_rueckfrage_fest(objekt, text)` speichert am Objekt; mit `an`/`rolle`/`als_aufgabe` zusätzlich Aufgabe `rueckfrage` (öffnet eine erledigte Rückfrage wieder) | „auch dann am Beleg, wenn nie eine Aufgabe daraus wurde“ |
| Erinnerung | Stufen in Tagen nach Fälligkeit, Standard `[0, 3, 7]`, je Art überschreibbar; Stufe = Anzahl erreichter Schwellen; letzte Stufe mit `eskalation_an` = Eskalation (Priorität hoch, Kopie an Ziel, Verlauf). Erreicht eine Aufgabe eine neue Stufe, steht sie in der nächsten Tagesübersicht; die Stufe wird erst nach erfolgreicher Zustellung gespeichert | Spec 4.3; gegen feste Stichtage testbar; ein ausgefallener Lauf holt die Erinnerung nach |
| Tagesübersicht | je Empfänger (Benutzer, `@rolle`, `gemeinsam`) eine Nachricht mit „Fällig und Erinnerungen“, „Neu“, „Eskaliert“ und Summenzeile; Empfänger ohne Adresse fallen auf `gemeinsam` zurück; leere Übersicht wird nicht verschickt. Höchstens eine Übersicht je Empfänger, Kanal und Tag (Protokoll `aufgaben_benachrichtigungen`) | Akzeptanz 5; „zwanzig Mails am Tag“ ist genau das, was die Spec verbietet |
| Kanäle | Registry `KANAELE`: `email` (Standard; SMTP und Absender aus Abschnitt `versand`, `SmtpVersand` aus Baustein 3, Header `Auto-Submitted: auto-generated`), `webhook` (JSON mit `text` für Slack/Mattermost plus strukturierte Felder, `urllib`) | Spec 4.4; keine neue Abhängigkeit |
| Zustellung | Fehler eines Kanals stehen im Protokoll und in der Ausgabe; Stufe und „gemeldet“ werden erst gesetzt, wenn jeder Kanal die Aufgabe heute erfolgreich übermittelt hat | sonst ginge eine Erinnerung bei einem SMTP-Ausfall verloren |
| Lauf | `accounti aufgaben lauf` = alle Prüfläufe + Erinnerungen; gedacht für Cron direkt nach `accounti bank lauf`. `bank lauf` selbst bleibt unverändert | Spec 4.3 will denselben geplanten Lauf; der Auftrag verbietet, bestehende Abläufe umzubauen — das Einhängen ist beim Zusammenführen eine Zeile |
| Konfiguration | eigener Abschnitt `aufgaben` mit Lader `lade_aufgaben_einstellungen()` im Paket; alles hat Standardwerte; `${UMGEBUNGSVARIABLE}` wie in `versand` (z.B. Webhook-URL mit Token) | Dateiregeln des Projekts |
| Nummer | Aufgaben haben eine laufende Nummer (`aufgaben zeige 42`), eindeutiger Index; IDs (Anfang genügt) gehen auch | Spec 4.6 |

## Schnittstelle für andere Bausteine

Alles aus `accounti.aufgaben`; Funktionen arbeiten in der Sitzung des Aufrufers, schreiben mit
`flush()` und committen nicht.

```python
from accounti.aufgaben import (
    Objekt, Prioritaet, AufgabenStatus,          # Modelle (aus accounti.models.aufgaben)
    melde_aufgabe,           # idempotent anlegen/aktualisieren → Meldung(aufgabe, vorgang)
    schliesse_wenn_erledigt, # Anlass entfallen → hinfaellig (None, wenn keine aktive Aufgabe)
    gleiche_ab,              # Menge von Anlässen einer Art abgleichen: neu/aktualisiert/hinfällig
    finde_aufgabe, erledige, setze_status, weise_zu,
    kommentiere, halte_rueckfrage_fest, kommentare_zu, aufgaben_zu,
    lade_aufgaben_einstellungen,                 # Abschnitt `aufgaben`
    Anlass, Pruefergebnis, PRUEFLAEUFE, registriere_prueflauf, fuehre_prueflaeufe_aus,
    registriere_objekttyp, beschreibe, loese_auf,  # eigene Objekttypen, z.B. "frist"
    stelle_zusammen, versende_tagesuebersichten, baue_kanaele, KANAELE,
    AufgabenError,
)

# Baustein 7 (Belegvollständigkeit), direkt aus der Nachforderung:
melde_aufgabe(
    session, "beleg_fehlt", Objekt("transaktion", tx.id),
    titel=f"Beleg fehlt: {tx.gegenkonto_name} {tx.betrag} €",
    faellig_am=tx.datum + timedelta(days=10),
    merkmale={"bankkonto": iban, "gegenpartei": tx.gegenkonto_name or ""},
    erzeugt_von="pruefung:beleg_fehlt",
)
schliesse_wenn_erledigt(session, "beleg_fehlt", Objekt("transaktion", tx.id),
                        grund="Beleg zugeordnet")

# Baustein 9 (Fristen), Objekt ohne eigene Tabelle:
melde_aufgabe(session, "frist_ustva", Objekt("frist", "ustva-2026-09"),
              titel="USt-Voranmeldung 09/2026 abgeben", faellig_am=date(2026, 10, 12),
              prioritaet=Prioritaet.HOCH, erzeugt_von="steuer:fristen")

# Oder als eigener Prüflauf, der mit `accounti aufgaben pruefen` mitläuft:
class FristenLauf:
    name = "frist_ustva"; beschreibung = "…"; grund_entfallen = "Voranmeldung abgegeben"
    def finde(self, session, einstellungen, stichtag, zeitraum) -> Pruefergebnis: ...
registriere_prueflauf(FristenLauf())
```

## Aufgaben

### Paket 1 — Aufgabenkern, Zuständigkeit, Rückfragen

- [x] **Modelle** (`models/aufgaben.py`): `Objekt`, `Aufgabe`, `Kommentar`, `Benachrichtigung`, `AufgabenStatus`, `Prioritaet`, `KommentarArt`.
- [x] **Tabellen und Repository** (`db/tabellen_aufgaben.py`, `db/repo_aufgaben.py`): `aufgaben` (eindeutig: `nr`, `schluessel`), `aufgaben_kommentare` (nur anfügen), `aufgaben_benachrichtigungen`; Präfixsuche für Objekte (`tests/test_aufgaben_repository.py`).
- [x] **Konfiguration** (`aufgaben/einstellungen.py`): Abschnitt `aufgaben` mit Standardwerten, ohne Datei/Abschnitt lauffähig, Fehler als `KonfigurationError`, `${VAR}` (`tests/test_aufgaben_einstellungen.py`).
- [x] **Erzeugung** (`aufgaben/erzeugung.py`): `melde_aufgabe` idempotent (auch bei gleichzeitigem Anlegen), wieder öffnen nach `hinfaellig`, `erledigt` bleibt; `schliesse_wenn_erledigt`, `erledige`, `setze_status`, `weise_zu`; Verlauf (`tests/test_aufgaben_erzeugung.py`).
- [x] **Zuständigkeit** (`aufgaben/zustaendigkeit.py`): Regeln mit Platzhaltern, Benutzer oder Rolle, unzugewiesen; „ich“ und Rollenmitgliedschaft; Akzeptanz 6 auf API-Ebene (`tests/test_aufgaben_zustaendigkeit.py`).
- [x] **Kommentare und Rückfragen** (in `erzeugung.py`, Objekte in `aufgaben/objekte.py`): an Aufgabe oder Objekt, Rückfrage am Beleg ohne Aufgabe, auffindbar in neuer Sitzung; Akzeptanz 4 (`tests/test_aufgaben_rueckfragen.py`).

### Paket 2 — Prüfläufe

- [x] **Registry und Abgleich** (`aufgaben/prueflaeufe.py`, `gleiche_ab`): neu/aktualisiert/unverändert/wieder offen/hinfällig; Umfang bei Zeitraum (`tests/test_aufgaben_prueflaeufe.py`).
- [x] **`kontierung_pruefen`:** Akzeptanz 1 — auch durch echten `kontiere_umsaetze` mit LLM-Attrappe; Akzeptanz 2 — zweiter Lauf verdoppelt nichts; geprüfte Buchung → `hinfaellig`.
- [x] **`beleg_fehlt`:** Akzeptanz 3 — Beleg trifft ein, `bank abgleich` bestätigt, nächster Prüflauf schließt als `hinfaellig`; Schwellen; erledigte Aufgabe bleibt erledigt.
- [x] **`beleg_pruefen`, `kontakt_pruefen`, `bank_freigabe`.**

### Paket 3 — Erinnerung und Tagesübersicht

- [x] **Erinnerungsstufen** (`aufgaben/erinnerung.py`): Stufen gegen feste Stichtage, je Art, Eskalation (`tests/test_aufgaben_erinnerung.py`).
- [x] **Tagesübersicht** (`aufgaben/benachrichtigung.py`): Bündelung je Empfänger, Rückfall auf `gemeinsam`, Text und Betreff, leere Übersicht entfällt.
- [x] **Kanäle:** `email` gegen lokalen SMTP-Testserver (echtes `smtplib`, kein Versand nach außen), `webhook` gegen lokalen HTTP-Server; Protokoll, höchstens einmal je Tag, Wiederholung nach Fehler; Akzeptanz 5 (`tests/test_aufgaben_benachrichtigung.py`).

### Paket 4 — CLI

- [x] **`accounti aufgaben`** (`befehle/aufgaben.py`): `liste [--offen|--alle] [--zustaendig ich|NAME] [--unzugewiesen] [--art] [--faellig]`, `zeige NR`, `zuweisen NR --an|--rolle|--frei`, `kommentieren NR|--beleg|--objekt --text`, `rueckfrage BELEG --text [--an]`, `objekt TYP ID`, `status NR`, `erledigen NR`, `pruefen [--lauf] [--zeitraum]`, `erinnern [--vorschau]`, `lauf`; Akzeptanz 6 sichtbar in der Liste (`tests/test_cli_aufgaben.py`).
- [x] **Abschluss:** `pytest`, `ruff` (ohne Cache), `mypy` grün; Checkboxen abgehakt; Doku-Bausteine unten vollständig.

## Akzeptanzkriterien → Tests

| # | Kriterium | Tests |
|---|-----------|-------|
| 1 | Buchung unter der Confidence-Schwelle → genau eine Aufgabe mit Bezug zur Buchung | `test_aufgaben_prueflaeufe.py::test_buchung_unter_der_schwelle_erzeugt_genau_eine_aufgabe`, `::test_kontierung_aus_classify_mit_unsicherem_llm` |
| 2 | Wiederholter Prüflauf verdoppelt nichts | `test_aufgaben_prueflaeufe.py::test_wiederholter_lauf_verdoppelt_nichts`, `test_aufgaben_erzeugung.py::test_zweiter_aufruf_aktualisiert_statt_zu_verdoppeln`, `::test_gleichzeitig_angelegt_bleibt_eine_aufgabe`, `test_cli_aufgaben.py::test_pruefen_ist_idempotent` |
| 3 | Fehlender Beleg trifft ein → Aufgabe von selbst `hinfaellig` | `test_aufgaben_prueflaeufe.py::test_beleg_trifft_ein_und_die_aufgabe_schliesst_sich_selbst`, `test_cli_aufgaben.py::test_beleg_trifft_ein_cli` |
| 4 | Rückfrage am Beleg festhalten und dort wiederfinden | `test_aufgaben_rueckfragen.py::test_rueckfrage_am_beleg_ohne_aufgabe_ist_spaeter_auffindbar`, `::test_rueckfrage_mit_aufgabe_und_antwort`, `test_cli_aufgaben.py::test_rueckfrage_am_beleg_und_wiederfinden` |
| 5 | Fällige Aufgaben gebündelt in einer Tagesübersicht, keine Einzelmails | `test_aufgaben_benachrichtigung.py::test_faellige_aufgaben_kommen_gebuendelt`, `::test_hoechstens_eine_uebersicht_am_tag`, `test_cli_aufgaben.py::test_erinnern_vorschau_und_versand` |
| 6 | Unzugewiesene Aufgabe in der gemeinsamen Liste sichtbar | `test_aufgaben_zustaendigkeit.py::test_unzugewiesene_aufgabe_in_der_gemeinsamen_liste`, `test_cli_aufgaben.py::test_unzugewiesen_in_der_gemeinsamen_liste` |

## Grenzen

- **Selbstabschluss beim nächsten Prüflauf, nicht im selben Augenblick.** Die Aufgabe „Beleg
  fehlt“ wird `hinfaellig`, sobald nach dem Abgleich `accounti aufgaben pruefen` (oder `lauf`)
  läuft. `bank abgleich`, `bank lauf`, `opos zuordnen` und `classify` wurden bewusst nicht
  angefasst; `bank lauf` ruft die Prüfläufe nicht selbst auf. Für Cron:
  `accounti bank lauf && accounti aufgaben lauf`. Beim Zusammenführen kann `bank_lauf()` am Ende
  `fuehre_prueflaeufe_aus()` aufrufen (eine Zeile) — dann gilt Spec 4.3 („derselbe geplante Lauf“)
  wörtlich. Auch `bank_freigabe` entsteht erst mit dem nächsten Prüflauf nach dem Abruf.
- **Keine Benutzerkonten, keine Rechte.** Benutzer und Rollen sind Zeichenketten aus der
  Konfiguration (`aufgaben.ich`, `ACCOUNTI_BENUTZER`, Login-Name, `aufgaben.rollen`). Wer die
  CLI bedienen kann, kann jede Aufgabe zuweisen und erledigen und mit `--von` unter jedem Namen
  kommentieren. Anmeldung und Rollenrechte bringt Baustein 10.
- **Zuständigkeitsregeln greifen nur beim Anlegen.** Geänderte Regeln verteilen vorhandene
  Aufgaben nicht neu. Eine Regel „Belege der Gesellschaft X an Y“ ist technisch vorbereitet
  (Merkmal `gesellschaft`), aber accounti führt die Gesellschaft noch nicht am Beleg — kein
  Erzeuger liefert das Merkmal bisher.
- **`beleg_fehlt` kennt kein „begründet belegfrei“.** Gebühren, Zinsen, Steuerzahlungen
  erscheinen zunächst als Aufgabe und werden von einem Menschen einmal mit Begründung erledigt
  (bleibt erledigt). Filter gibt es nur nach Betrag und Alter; feinere Regeln und Schwellen
  bringt Baustein 7. Beim ersten Lauf auf einem Altbestand entsteht je alter Umsatz eine Aufgabe;
  weil die Frist vom Umsatzdatum rechnet, stehen sie in der ersten Übersicht gleich auf der
  letzten Stufe.
- **Fristen ohne Kalender.** Fälligkeit = Datum des Objekts (bzw. Anlage) plus Tage je Art;
  keine Verschiebung bei Wochenende oder Feiertag, keine steuerlichen Fristen (USt-VA,
  ZM) — die rechnet Baustein 9 in `steuer/` und übergibt `faellig_am`. Die zehn Tage beruhen
  auf GoBD Rz. 47 (Unbedenklichkeitsgrenze, keine starre Frist); der BMF-Wortlaut wurde über
  Sekundärquellen geprüft, das amtliche PDF war am 20.10.2026 nicht abrufbar (HTTP 503).
- **Eskalation:** genau eine Eskalationsstufe (die letzte); eine Art kann eine global gesetzte
  Eskalation nicht abschalten, nur ein anderes Ziel setzen.
- **Tagesübersicht:** höchstens eine je Empfänger, Kanal und Tag; was nach der Übersicht neu
  entsteht, kommt am nächsten Tag. Empfänger ohne Adresse (auch `@rolle`) landen in
  `gemeinsam`; zwei Empfängerschlüssel mit derselben Adresse bekommen zwei Mails. Mitglieder einer
  Rolle bekommen keine persönliche Kopie der Rollen-Übersicht.
- **E-Mail nur lokal geprüft.** Getestet gegen einen eigenen SMTP-Testserver auf 127.0.0.1 ohne
  TLS und ohne Anmeldung, mit echtem `smtplib`. STARTTLS, SSL und Login stammen unverändert aus
  `SmtpVersand` (Baustein 3, dort mit Attrappe getestet). Es wurde keine echte E-Mail versendet.
- **Webhook generisch.** JSON mit `text` (Slack-/Mattermost-Format laut Doku) plus eigenen
  Feldern; nicht gegen echte Slack-, Mattermost- oder Teams-Instanzen getestet — Microsoft Teams
  (Workflows) erwartet ein anderes Format. Kein Wiederholen innerhalb eines Laufs, der nächste
  Lauf holt nach. Ein externer Chatdienst bekommt Titel mit Gegenparteien und Beträgen — der
  Kanal ist deshalb opt-in.
- **Verlauf nur per ORM gesperrt.** Kommentare und Ereignisse lassen sich über die Anwendung
  nicht ändern oder löschen (wie beim USt-IdNr.-Protokoll), es gibt aber weder Datenbank-Trigger
  noch Hash-Kette; rohes SQL kann ändern. Titel und Beschreibung einer Aufgabe überschreibt der
  Prüflauf ohne Historie.
- **Aufbewahrung und Datenschutz offen.** Kein Lösch-Pfad und kein Löschkonzept für Aufgaben und
  Kommentare. Ob Rückfragen „sonstige Unterlagen“ nach § 147 Abs. 1 Nr. 5 AO (sechs Jahre) sind,
  ist nicht geklärt; Kommentare können personenbezogene Daten enthalten (DSGVO-Löschung gehört ins
  Löschkonzept von Baustein 10).
- **Nicht abgedeckte Quellen:** offene Abgleich-/Zuordnungsvorschläge (`bank vorschlaege`,
  `opos vorschlaege`) erzeugen keine eigene Aufgabe (nur ein Hinweis in „Beleg fehlt“);
  Zahlungsläufe zur Freigabe gibt es erst mit Baustein 6.
- **Technik:** Tabellen `aufgaben`, `aufgaben_kommentare`, `aufgaben_benachrichtigungen` ohne
  Migration (entsteht beim Zusammenführen); nur unter SQLite getestet. Eine Aufgaben-ID, deren
  Anfang nur aus Ziffern besteht, wird als Nummer gelesen — dann mehr Zeichen angeben.
  `${VARIABLE}` wird über `_ersetze_variablen` aus `erechnung/versand.py` aufgelöst (privater
  Name, unverändert mitbenutzt); beim Zusammenführen ggf. nach `konfiguration.py` heben.

## Doku-Bausteine

### README — Statuszeile (Tabelle „Prüfung & Ordnung“, ersetzt die Zeile „Aufgaben & Rückfragen“)

```markdown
| ✅ | **Aufgaben & Rückfragen** | Aufgaben mit Bezug auf Buchung, Beleg, Umsatz, Kontakt oder Bankkonto; Prüfläufe (unsichere Kontierung, Beleg fehlt, Beleg/Kontakt zur Prüfung, Bankfreigabe) idempotent und mit Selbstabschluss; Zuständigkeit an Person oder Rolle, sonst gemeinsame Liste; Rückfragen am Beleg; gebündelte Tagesübersicht per E-Mail oder Webhook |
```

Roadmap v0.5: `- [x] Aufgaben, Rückfragen am Beleg, Zuständigkeiten, Erinnerungen`

### README — Nutzungsblock (neuer Abschnitt nach „USt-IdNr.-Prüfung“)

````markdown
### Aufgaben und Rückfragen

Alles, was ein Mensch entscheiden muss, steht an einem Ort. Prüfläufe werten vorhandene Daten
aus — eine zweite Ausführung verdoppelt nichts, und eine Aufgabe ohne Anlass schließt sich
selbst als `hinfaellig` (z.B. sobald der fehlende Beleg abgeglichen ist).

```bash
accounti aufgaben pruefen                      # unsichere Kontierung, Beleg fehlt, Beleg/Kontakt zur Prüfung, Bankfreigabe
accounti aufgaben liste                        # offene Aufgaben; unzugewiesen = gemeinsame Liste
accounti aufgaben liste --zustaendig ich       # eigene und die der eigenen Rollen
accounti aufgaben zeige 42                     # mit Bezugsobjekt und Verlauf
accounti aufgaben zuweisen 42 --an jan         # oder --rolle buchhaltung, --frei
accounti aufgaben kommentieren 42 --text "Beim Lieferanten angefragt"
accounti aufgaben erledigen 42 --text "Kontoführungsgebühr, belegfrei"
accounti aufgaben rueckfrage 3fa2c1 --text "Wer war beim Essen dabei?" --an erika
accounti aufgaben objekt beleg 3fa2c1          # Rückfragen, Kommentare, Aufgaben am Beleg
accounti aufgaben erinnern --vorschau          # Tagesübersicht ansehen, nichts senden
accounti aufgaben erinnern                     # je Empfänger eine Übersicht (E-Mail über 'versand')
accounti aufgaben lauf                         # Cron: prüfen + erinnern, z.B. nach 'accounti bank lauf'
```

Erledigt bleibt erledigt: Wer eine Aufgabe mit Begründung schließt, bekommt sie vom nächsten
Prüflauf nicht wieder. Erinnerungen kommen am Fälligkeitstag, nach drei und nach sieben Tagen
(einstellbar je Art, die letzte Stufe eskaliert auf Wunsch) — gebündelt, nicht als Einzelmail.
````

### CHANGELOG

**Hinzugefügt**

```markdown
- **Aufgaben & Rückfragen** (Baustein 8): Aufgaben mit Bezug auf ein beliebiges Objekt
  (Buchung, Beleg, Umsatz, offener Posten, Kontakt, Bankkonto, eigene Typen anderer Bausteine),
  Zuständigkeit an Benutzer oder Rolle per Regel, unzugewiesen in der gemeinsamen Liste,
  Fälligkeit je Art, Status offen/in_arbeit/wartet/erledigt/hinfaellig und Verlauf, der nur
  wachsen kann. Idempotent über (Art, Objekt) mit eindeutigem Schlüssel — ein wiederholter
  Prüflauf verdoppelt nichts, erledigte Aufgaben bleiben erledigt. Prüfläufe
  `kontierung_pruefen` (Buchung unter der Confidence-Schwelle oder zur Prüfung), `beleg_fehlt`
  (Umsätze ohne Beleg), `beleg_pruefen`, `kontakt_pruefen`, `bank_freigabe`; entfällt der
  Anlass, schließt sich die Aufgabe selbst als `hinfaellig`. Rückfragen und Kommentare am Beleg,
  auch ohne Aufgabe. Erinnerungsstufen mit Eskalation und eine Tagesübersicht je Empfänger statt
  Einzelmails über die Kanäle `email` (SMTP aus `versand`, `Auto-Submitted: auto-generated`)
  und `webhook`. CLI `accounti aufgaben liste|zeige|objekt|zuweisen|status|erledigen|
  kommentieren|rueckfrage|pruefen|erinnern|lauf`; neuer, optionaler Abschnitt `aufgaben`;
  Python-Schnittstelle `melde_aufgabe`, `schliesse_wenn_erledigt`, `gleiche_ab`,
  `registriere_prueflauf` für die Bausteine 7 und 9
```

**Geändert**

```markdown
- Keine Änderung an bestehenden Abläufen: `classify`, `bank abgleich`, `bank lauf` und
  `opos zuordnen` arbeiten wie bisher; die Prüfläufe lesen nur, was sie speichern
```

**Behoben**

```markdown
- —
```

### `docs/bauplan.md`

Bausteinkarte, Zeile 8:

```markdown
| 8 | Aufgaben & Rückfragen | `aufgaben/` | ✅ fertig | [Spec](specs/2026-08-10-aufgaben-rueckfragen.md) |
```

Absatz unter der Karte:

```markdown
**Baustein 8 ist fertig** ([Plan](plans/2026-10-25-aufgaben-rueckfragen.md)): Aufgaben mit
Bezug auf ein beliebiges Objekt, idempotent über (Art, Objekt), mit Zuständigkeit (Benutzer,
Rolle oder gemeinsame Liste), Fälligkeit, Verlauf und Selbstabschluss als `hinfaellig`;
Prüfläufe für unsichere Kontierung, fehlende Belege, Belege und Kontakte zur Prüfung und
Bankfreigaben; Rückfragen am Beleg; Erinnerungsstufen und eine gebündelte Tagesübersicht per
E-Mail oder Webhook. Die Bausteine 7 und 9 melden ihre Aufgaben über `accounti.aufgaben`.
Offen: Einhängen in `bank lauf` (bis dahin `accounti aufgaben lauf` im selben Cron-Eintrag),
Benutzerkonten und Rechte (Baustein 10).
```

### `docs/architektur.md` — Modulabschnitt (ersetzt „`aufgaben/` *(geplant …)*“)

```markdown
### `aufgaben/` *(vorhanden — [Baustein 8](specs/2026-08-10-aufgaben-rueckfragen.md))*

Alles, was ein Mensch entscheiden muss, an einem Ort. Eine `Aufgabe` (`models/aufgaben.py`)
zeigt auf `Objekt(typ, id)` — Buchung, Beleg, Transaktion, offener Posten, Kontakt, Bankkonto
oder einen Typ, den ein anderer Baustein mitbringt (z.B. `frist`). Art und Objekttyp sind
freie Bezeichner; `objekte.py` beschreibt und löst die bekannten Typen auf
(`registriere_objekttyp`).

- `erzeugung.py` — die Schnittstelle für andere Bausteine: `melde_aufgabe` ist idempotent über
  den Schlüssel `art|objekt_typ|objekt_id` (eindeutiger Index, auch bei parallelen Läufen);
  ein zweiter Aufruf aktualisiert. `schliesse_wenn_erledigt` setzt `hinfaellig` (System),
  `erledige` setzt `erledigt` (Mensch) — erledigt bleibt erledigt, hinfällig öffnet sich wieder,
  wenn der Anlass zurückkehrt. Kommentare und Rückfragen hängen an Aufgabe und/oder Objekt;
  der Verlauf ist nur anfügbar. *(vorhanden)*
- `prueflaeufe.py` — Registry `PRUEFLAEUFE`: `kontierung_pruefen`, `beleg_fehlt` (über
  `bank/abgleichslauf.offen_in_der_bank`), `beleg_pruefen`, `kontakt_pruefen`, `bank_freigabe`.
  Prüfläufe lesen nur; `gleiche_ab` meldet die Anlässe und schließt Aufgaben ohne Anlass im
  geprüften Umfang. *(vorhanden)*
- `zustaendigkeit.py` — Regeln `wenn → an | rolle` aus `aufgaben.zustaendigkeit`; ohne Treffer
  unzugewiesen = gemeinsame Liste. *(vorhanden)*
- `erinnerung.py` — Stufen in Tagen nach Fälligkeit (Standard 0/3/7, je Art), die letzte
  eskaliert. *(vorhanden)*
- `benachrichtigung.py` — Tagesübersicht je Empfänger statt Einzelmeldungen, Kanal-Registry
  `KANAELE`: `email` (SMTP aus `versand`, `Auto-Submitted` nach RFC 3834), `webhook` (JSON mit
  `text`); Protokoll `aufgaben_benachrichtigungen`, höchstens eine Übersicht je Empfänger, Kanal
  und Tag, als gemeldet gilt nur Zugestelltes. *(vorhanden)*

Intern gedacht: kein Portal für externe Nutzer.
```

Datenmodell-Tabelle, neue Zeile unter `Aufgabe`:

```markdown
| `Kommentar` | Art (Kommentar, Rückfrage, Ereignis), Autor, Text, Zeitpunkt, Anhang-Beleg | → `Aufgabe` und/oder beliebiges Objekt (nur anfügen) |
```

Erweiterungspunkte, neuer Abschnitt:

```markdown
### Aufgaben aus einem anderen Baustein melden

Direkt: `melde_aufgabe(session, art, Objekt(typ, id), titel=…, erzeugt_von=…)` und
`schliesse_wenn_erledigt(…)`, sobald der Anlass entfällt. Als Prüflauf: eine Klasse mit
`name`, `beschreibung`, `grund_entfallen` und `finde(session, einstellungen, stichtag,
zeitraum) -> Pruefergebnis`, eingetragen mit `registriere_prueflauf` — dann läuft sie mit
`accounti aufgaben pruefen` und schließt Entfallenes selbst. Jeder Prüflauf besitzt genau eine
Aufgabenart. Ein neuer Benachrichtigungskanal implementiert `adresse()` und `sende()` und trägt
sich in `KANAELE` ein.
```

### `config/accounti.example.yaml` — neuer Abschnitt

```yaml
# Aufgaben & Rückfragen (optional — ohne diesen Abschnitt gelten die Standards)
aufgaben:
  ich: "jan"                     # für --zustaendig ich (sonst ACCOUNTI_BENUTZER bzw. Login-Name)
  rollen:
    buchhaltung: [jan, erika]
  zustaendigkeit:                # erste passende Regel gewinnt; ohne Treffer: gemeinsame Liste
    - wenn: {art: bank_freigabe}
      an: jan
    - wenn: {art: "beleg_*", bankkonto: "DE12*"}   # Merkmale: bankkonto, gegenpartei, kanal, …
      rolle: buchhaltung
  fristen:                       # Tage bis zur Fälligkeit je Art
    standard: 7
    beleg_fehlt: 10              # ab Umsatzdatum (GoBD Rz. 47: zehn Tage unbedenklich)
    kontierung_pruefen: 10
    bank_freigabe: 0
  erinnerung:
    stufen: [0, 3, 7]            # Tage nach Fälligkeit: fällig, 1. Erinnerung, letzte Stufe
    eskalation_an: "@leitung"    # optional: Benutzer oder @rolle bekommt die letzte Stufe in Kopie
    arten:
      beleg_fehlt: {stufen: [0, 7, 14]}
  pruefung:
    kontierung_schwelle: 0.95    # darunter wird eine Buchung zur Aufgabe
    beleg_fehlt_ab_betrag: 0.00
    beleg_fehlt_nach_tagen: 0
    abgeschaltet: []             # z.B. [kontakt_pruefen]
  benachrichtigung:
    kanaele: [email]             # email (SMTP aus 'versand'), webhook
    neue_melden: true            # neue Aufgaben in die Tagesübersicht
    # absender: "accounti <accounti@meine-firma.example>"   # sonst versand.absender
    empfaenger:                  # ohne Adresse landet alles in 'gemeinsam'
      jan: "jan@meine-firma.example"
      "@leitung": "chefin@meine-firma.example"
      gemeinsam: "buchhaltung@meine-firma.example"
    # webhook:
    #   url: "${ACCOUNTI_AUFGABEN_WEBHOOK}"   # Slack/Mattermost-kompatibel (Feld "text")
    #   timeout_sekunden: 10
```
