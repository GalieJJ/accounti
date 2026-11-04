# Design-Leinwand „accounti Oberfläche“ (Baustein 10c)

**Freigabe** durch den Nutzer am 26.10.2026 für die ersten zehn Zeichenflächen:

> „Die Richtung passt. Setz das Design so in Baustein 10c um.“

Die Leinwand stammt aus Claude Design (`canvas.json` v3). Sie liegt hier unverändert, damit
P1–P7 und die Pakete aus dem Nachtrag dieselbe Vorlage haben.

## Lesart

- **Format:** `<x-dc>` mit Stilen in `<helmet><style>`. Die Farb-Token stehen als
  CSS-Variablen auf `.a` (hell) und `.a.dunkel` (dunkel). Alles andere steht als Inline-`style=`
  im Markup, dazu Platzhalter `{{…}}`, `sc-if`/`sc-for` und Klicklogik in `DCLogic`. Das
  eingebundene `support.js` gehört zum Design-Werkzeug und liegt nicht bei.
- **Maßgeblich** sind Aussehen, Abstände, Farben, Komponenten und Texte — nicht Markup,
  Inline-Stile oder Skriptlogik.
- **Nicht als Vorlage kopieren.** Die Seiten von accounti haben keine Inline-Stile und kein
  Inline-Skript (CSP). Token, Maße, Komponenten, Layouts und Symbole stehen im Plan von P1
  (`docs/plans/2026-10-28-oberflaeche-p1-design.md`, Abschnitt „Design-Leinwand“ L0–L10) und in
  `src/accounti/api/statisch/accounti.css`. Wo die Leinwand der Spec widerspricht, gilt die Spec;
  L7 im Plan sagt, wie das Aussehen trotzdem erreicht wird.
- Die Tokenblöcke stimmen in allen Zeichenflächen überein
  (`tests/test_spec_rueckverfolgung.py::test_leinwand_abgelegt`), und die Farben in
  `accounti.css` stimmen mit ihnen überein (`tests/test_design_token.py::test_token_wie_leinwand`).

## Zeichenflächen — wer baut was

Freigegeben am 26.10.2026 (Spec 10c, Pakete P1–P7):

| Zeichenfläche | Inhalt | baut |
|---|---|---|
| `Main` | Übersicht Desktop: Kopfleiste, Seitenleiste mit Zählern, „Heute zu tun“, Kennzahlen | Gerüst, Karte, Raster P1; Inhalte P2 |
| `Pruefen-Liste` | Reiter, Gruppen mit Sammelfreigabe, Tabelle mit Auswahl, Sammelleiste | Reiter, Tabelle, Sammelleiste P1; Gruppen, Auswahl P3 |
| `Pruefen-Arbeitsflaeche` | Beleg und Vorschlag, drei Schritte der Korrektur | zweispaltiges Layout P1; Abläufe P3 |
| `Handy-Uebersicht` | schmale Kopfleiste, Karten, untere Leiste | Kopf, untere Leiste P1; Karten P2 |
| `Handy-Pruefen` | Reiter Vorschlag/Beleg, Aktionsleiste | Aktionsleiste P1; Seite P3 |
| `Handy-Freigaben` | Karte je Freigabe mit Codefeld | Karten-Optik P1; Aufklapper, USt-VA P2 |
| `Handy-Mehr` | `/menue`: Bereiche, Gesellschaft, Mein Konto | P1 |
| `Assistent-Steuern` | Schrittliste, Optionskarten, Wahlpillen, Prüfhinweise | Komponenten P1; Seite P7 |
| `Einstellungen-Firma` | Unternavigation, Abschnittskarten, Kennfarbe | Layout, Komponenten P1; Seite P5 |
| `Bausteine` | Farben, Schrift, Knöpfe, Status, Felder, Hinweise, Tabelle — hell und dunkel | `/muster` P1 |

Später dazugekommen, **noch nicht freigegeben** (Spec-Nachtrag „Alle Ansichten“, Pakete P8–P16,
Abgleich dort in Anhang G):

| Zeichenfläche | Inhalt |
|---|---|
| `Bank-Umsaetze` | Bank & Zahlungen: Umsätze je Konto |
| `Belege-paperless` | Belege mit paperless-ngx (Token `--papier` für das Vorschaubild) |
| `Buchungen` | Journal |
| `Handy-Bank` | Bankumsätze auf dem Handy |
| `Handy-Belege` | Belege auf dem Handy |
| `Rechnungen` | Rechnungen & Kontakte: Rechnungen |
| `Kontakt-Detail` | Rechnungen & Kontakte: Kontakt |
| `Anlagen` | Anlagenverzeichnis |

Die Leinwand zeichnet das aufgeklappte Benutzermenü, Fehlerseiten, Anmeldung, `/konto`,
`/gesellschaft` und die Hilfe nicht; ihr Aussehen leitet P1 aus Token und Mustern ab.
