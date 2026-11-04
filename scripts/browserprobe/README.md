# Browserprobe der Oberfläche

Werkzeug für die Entwicklung (Baustein 10c, Plan P1, Schritte 5 und 14) — nicht
ausgeliefert, nicht im Abbild, nicht Teil von `pytest` und nicht in der CI. Es prüft die
Seiten in einem echten Browser: waagrechtes Scrollen (AK1), axe-core mit WCAG 2.0–2.2
A/AA (AK2), CSP-Meldungen in der Konsole (AK5), Fokus nach einem htmx-Austausch (A104)
und die Maße gegen die Design-Leinwand (Plan P1, L10).

## Versionen und Herkunft

| Paket | Version | Lizenz | Integrität (npm) |
|---|---|---|---|
| `playwright` | 1.59.1 (01.04.2026) | Apache-2.0 | `sha512-C8oWjPR3F81yljW9o5OxcWzfh6avkVwDD2VYdwIGqTkl+OGFISgypqzfu7dOe4QNLL2aqcWBmI3PMtLIK233lw==` |
| `playwright-core` | 1.59.1 | Apache-2.0 | `sha512-HBV/RJg81z5BiiZ9yPzIiClYV/QMsDCKUyogwH9p3MCP6IYjUFu/MActgYAvK0oWyV9NlwM3GLBjADyWgydVyg==` |
| `axe-core` | 4.14.0 (05.10.2026) | MPL-2.0 (unverändert benutzt) | `sha512-9WTZxEjsZ7b13TH8JPmbV2z8CHbl80/2hm3XPEG4JgNdQLK81IBRXmSxHfMAOkSqQeRxT/0dwNDz2GOm3zzpcQ==` |

`package.json` nennt genaue Versionen, `package-lock.json` die Integritätswerte;
`.npmrc` schaltet Installationsskripte ab (`ignore-scripts=true`). `probe.mjs` prüft vor
dem Einspielen zusätzlich die SHA-256 von `axe-core/axe.min.js`
(`20c09fe157a8a34a30e241aaa1fcdade657734f08ab379ecfbeb7d45cc46e878`).

**Playwright 1.59.1 statt 1.64.0** (Plan P1, Schritt 5, Rückfall): 1.59.1 nutzt
Chromium-Revision **1217**, die auf dem Server schon unter `~/.cache/ms-playwright` liegt;
1.64.0 bräuchte Revision 1248 von Microsofts CDN. Die **Browser** selbst stehen nicht in
der Lockdatei: `npx playwright install chromium firefox` lädt sie von Microsofts
Playwright-CDN (Revision aus `playwright-core/browsers.json`), sie gelten unter den
Lizenzen ihrer Hersteller. Auf dem Server gibt es kein Firefox; der Firefox-Lauf
(`--browser firefox`) geschieht beim Nutzer.

## Ablauf

```bash
cd scripts/browserprobe && npm ci && cd ../..        # Browser nur, wenn sie fehlen:
# npx --prefix scripts/browserprobe playwright install chromium firefox
python -m tests.browserprobe_welt --port 8473 --ziel /pfad/zu/einem/neuen/ordner &
node scripts/browserprobe/leinwand.mjs --quelle docs/design/2026-10-26-leinwand \
     --ziel scripts/browserprobe/ergebnisse/leinwand
node scripts/browserprobe/probe.mjs --welt /pfad/zu/einem/neuen/ordner/probe.json \
     --browser chromium --vergleich scripts/browserprobe/ergebnisse/leinwand
kill %1                                              # Welt beenden
```

- `tests/browserprobe_welt.py` baut einen Wegwerf-Bestand (zwei Gesellschaften, je Rolle
  ein Benutzer, Prüfschlange mit PDF-, Bild- und E-Rechnungsbeleg, Zahlungslauf), schreibt
  `probe.json` (Passwörter, TOTP-Geheimnisse, jede GET-Seite mit Beispiel-IDs und dem
  erwarteten Status je Benutzer) und startet die App auf `127.0.0.1`. Der Ordner muss neu
  oder leer sein; `probe.json` steht in `.gitignore`.
- `probe.mjs` meldet sich je Benutzer an (TOTP mit `node:crypto`), öffnet jede erlaubte
  HTML-Seite bei 1440, 390 und 320 px, hell und dunkel (über `prefers-color-scheme`, die
  Darstellung der Benutzer steht auf „automatisch“), und schreibt
  `ergebnisse/<datum>-<browser>.json`. axe läuft in einem Kontext mit `bypassCSP`
  (die eingespielte Datei wäre sonst gesperrt), die CSP-Prüfung in einem ohne Umgehung.
  Auswahl: `--benutzer jan,fritz`, `--seiten /muster,/pruefen`, `--breiten 1440,390`,
  `--themen dunkel`, `--auslassen geruest,fokus,axe,masse`, `--bilder` (Bildschirmfotos).
- Auf `/muster` dazu der Fokus nach dem Austausch über `/muster/beispiel` und die
  **Maßprobe** (L10 Punkt 4): Token hell und dunkel gleich L1, Karte, Knopf, Reiter,
  Optionskarte, Feldrand, Fokusring, Pille, Etikett, Betrag — in beiden Themenrahmen und
  mit `?theme=`; mit dem Gerüst auch Kopfleiste 56 px, Seitenleiste 232 px, untere Leiste
  64 px.
- `leinwand.mjs` legt Referenzbilder der Zeichenflächen an (Kopien mit ersetzten
  Platzhaltern nur im Ergebnisordner, ohne Netz); `--vergleich` stellt Bilder der
  Anwendung daneben (`ergebnisse/<datum>-vergleich/<datum>-vergleich.html`). Ein
  Pixelvergleich ist kein Abbruchgrund: Die Inhalte unterscheiden sich, solange P2 und P3
  fehlen.

- **Abgeschnittenes** (P1 Runde 2, Messung `abschnitt`): je Seite und Breite, ohne und
  (einmal je Breite) mit den Textabständen aus WCAG 1.4.12 — kein Inhalt breiter oder
  höher als ein Rahmen mit `overflow: hidden/clip`, ein scrollender Rahmen ist
  fokussierbar und benannt (`role="region"`, `aria-label`), jedes Bedienelement in Kopf
  und Inhalt trifft `elementFromPoint` in seiner Mitte, der Seitentitel im schmalen Kopf
  liegt ganz in der Kopfleiste, die Seite scrollt nicht waagrecht. Für den Abschluss
  `--breiten 1920,1440,1280,1024,390,320` (axe läuft bei jeder Breite außer 320 px).
- `--ablaeufe` misst außerdem AK8 im Hochformat (794 px) hell und dunkel und den
  Rückweg nach einer htmx-Freigabe (Fokus auf der neuen Überschrift; „Übernehmen“ und
  der Kürzel-Schalter bleiben auf der neuen Buchung). Seit Runde 3 prüft AK8 auch, dass
  auf dem Papier keine Tabelle breiter ist als ihr Rahmen, die Zellen Abstand haben und
  Beträge rechtsbündig stehen. Der Rückweg prüft zusätzlich „Übernehmen“ auf einer Seite
  unter einem POST-Pfad (422 beim Deaktivieren einer Regel): Er muss auf `/pruefen/regeln`
  führen, nicht auf ein GET mit 405. Die Abläufe geben Vorschläge frei: je Lauf eine
  frische Welt.

Der Rückgabewert ist 1, sobald eine Messung einen Befund hat. Die Zusammenfassung
gehört in den PR.
