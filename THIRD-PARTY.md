# Mitgelieferte Fremdbestandteile

accounti selbst steht unter der [MIT-Lizenz](LICENSE). Diese Dateien stammen von
Dritten und werden unverändert mit ihrer eigenen Lizenz mitgeliefert:

| Bestandteil | Datei | Lizenz | Lizenztext |
|-------------|-------|--------|------------|
| htmx 2.0.11 (Big Sky Software) — Teilaustausch der Web-Oberfläche | `src/accounti/api/statisch/htmx-2.0.11.min.js` (SHA-256 `d6fdc75f…f717`, im Test festgehalten) | 0BSD (Zero-Clause BSD) | `src/accounti/api/statisch/LIZENZ-htmx.txt` |
| Lucide-Symbole aus lucide-static 1.55.0 (npm, Integrität `sha512-h18lunTF…blwm/A==`) — 36 Symbole der Web-Oberfläche, erzeugt von `scripts/symbole.py`, Formen unverändert | `src/accounti/api/statisch/symbole.svg` | ISC; die von Feather abgeleiteten Symbole MIT (Cole Bemis) | `src/accounti/api/statisch/LIZENZ-lucide.txt` (vollständige `LICENSE` mit beiden Teilen) |
| Liberation Sans 2.1.5 — Schrift der erzeugten PDFs | `src/accounti/erechnung/schriften/LiberationSans-*.ttf` | SIL Open Font License 1.1 | `src/accounti/erechnung/schriften/LICENSE.txt` |

Python-Abhängigkeiten installiert pip aus `pyproject.toml`; sie werden nicht
mitgeliefert.

Nur für die Entwicklung (nicht ausgeliefert, nicht im Abbild): Playwright 1.59.1
(Apache-2.0) und axe-core 4.14.0 (MPL-2.0, unverändert benutzt) in `scripts/browserprobe/`,
installiert mit `npm ci` aus der Lockdatei (Integritätswerte, `ignore-scripts`). Die
Browser (Chromium, Firefox) lädt `npx playwright install` von Microsofts Playwright-CDN;
sie stehen nicht in der Lockdatei und gelten unter den Lizenzen ihrer Hersteller.
Playwright 1.59.1 nutzt Chromium-Revision 1217 (der Plan sah 1.64.0 vor; dafür fehlte auf
dem Server das passende Chromium, ein Download war nicht freigegeben).
