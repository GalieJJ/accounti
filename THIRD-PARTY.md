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
