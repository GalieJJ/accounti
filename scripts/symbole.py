"""Symbol-Sprite der Oberfläche aus ``lucide-static`` erzeugen (Baustein 10c, Plan P1).

Nur für Entwickler, nicht im Abbild. Aufruf::

    python scripts/symbole.py PFAD/package [--tarball lucide-static-1.55.0.tgz]

``PFAD/package`` ist das entpackte npm-Paket (``package.json``, ``LICENSE``,
``icons/<name>.svg``); den Tarball in einem eigenen, leeren Ordner laden und
entpacken, dieses Skript nicht darin. Mit ``--tarball`` prüft das Skript vorher dessen
SHA-512 gegen die npm-Integrität. Es schreibt ``src/accounti/api/statisch/symbole.svg``
(je Symbol ein ``<symbol id viewBox>`` nur mit den Formen; Strich, Füllung und
Linienenden setzt ``accounti.css``) und ``LIZENZ-lucide.txt`` (Kopf mit Version,
Integrität, Symbolliste und den Feather-Namen, dahinter die vollständige ``LICENSE``
mit ISC- und MIT-Teil).

Ein Wechsel der Lucide-Version ist eine bewusste Änderung: neue ``VERSION`` und
``INTEGRITAET`` (das Release mindestens zwei Wochen alt), Sprite neu erzeugen.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path

VERSION = "1.55.0"
INTEGRITAET = (
    "sha512-h18lunTFsIJWnY0FMRPjXeO9KcAtNi7fDqtqgWHOFbssfgUWsctn"
    "/pA7bpiyrd4g1DuBOJ24CsRnPfkYblwm/A=="
)
ZIEL = Path(__file__).resolve().parents[1] / "src" / "accounti" / "api" / "statisch"

# Auswahl nach der Design-Leinwand (Plan P1, L6) — die Reihenfolge ist die des Sprites
SYMBOLE = (
    "house",  # Übersicht
    "square-check-big",  # Prüfen
    "file-text",  # Belege
    "landmark",  # Bank & Zahlungen
    "receipt",  # Rechnungen & Kontakte
    "calendar",  # Steuern
    "chart-column",  # Auswertungen
    "shield-check",  # Freigaben
    "settings",  # Einstellungen
    "menu",  # Mehr
    "circle-help",  # Hilfe
    "log-out",  # Abmelden
    "check",  # erledigt, freigegeben, leerer Zustand
    "triangle-alert",  # Achtung, überfällig
    "circle-x",  # Fehler am Feld
    "info",  # Hinweis
    "circle-alert",  # Beleg fehlt, Angabe fehlt
    "lock",  # gesperrt
    "arrow-right",  # Vorschlag
    "chevron-down",
    "chevron-right",
    "chevron-left",
    "external-link",  # PDF öffnen
    "search",
    "upload",
    "download",
    "calendar-clock",  # Frist
    "sun",  # Darstellung hell
    "moon",  # Darstellung dunkel
    "monitor",  # Darstellung automatisch
    "arrow-up-down",  # Sortierung
    "arrow-up",
    "arrow-down",
    "loader-circle",  # lädt (steht still)
    "x",
    "keyboard",  # Tastenkürzel
)
# Symbole, die die LICENSE im MIT-Teil (Feather) unter ihrem alten Namen führt
FEATHER_NAMEN = {
    "triangle-alert": "alert-triangle",
    "circle-help": "help-circle",
    "circle-x": "x-circle",
    "circle-alert": "alert-circle",
}

_FORM = re.compile(r"<(path|circle|ellipse|line|polyline|polygon|rect)\b[^<>]*?/>")


class SymbolError(ValueError):
    """Eine Datei passt nicht zum erwarteten Aufbau der Lucide-Symbole."""


def wandle(svg: str, name: str) -> str:
    """``<svg …>Formen</svg>`` einer Lucide-Datei → ``<symbol id viewBox>…</symbol>``.

    Die Wurzelattribute (Größe, Strich, Klasse) entfallen; die Formen bleiben, wie sie
    sind. Erlaubt sind nur einfache Formen ohne Verweise, Stile oder Skript."""
    text = re.sub(r"<!--.*?-->", "", svg, flags=re.S).strip()
    wurzel = re.fullmatch(r"<svg\b([^>]*)>(.*)</svg>", text, flags=re.S)
    if wurzel is None:
        raise SymbolError(f"{name}: keine SVG-Wurzel")
    if 'viewBox="0 0 24 24"' not in wurzel.group(1):
        raise SymbolError(f"{name}: viewBox ist nicht 0 0 24 24")
    formen = [
        " ".join(m.group(0).split()).replace(" />", "/>")
        for m in _FORM.finditer(wurzel.group(2))
    ]
    rest = _FORM.sub("", wurzel.group(2)).strip()
    if rest or not formen:
        raise SymbolError(f"{name}: unerwarteter Inhalt {rest[:40]!r}")
    for form in formen:
        if re.search(r"\s(on\w+|style|href|xlink:href|class)=|url\(", form):
            raise SymbolError(f"{name}: Attribut nicht erlaubt in {form[:40]!r}")
    return f'<symbol id="{name}" viewBox="0 0 24 24">{"".join(formen)}</symbol>'


def sprite(paket: Path, namen: tuple[str, ...] = SYMBOLE) -> str:
    kopf = (
        f"<!-- Lucide-Symbole aus lucide-static {VERSION} (ISC; von Feather "
        "abgeleitete unter MIT), Lizenz: LIZENZ-lucide.txt. Erzeugt von "
        "scripts/symbole.py, nicht von Hand ändern. -->"
    )
    teile = [
        wandle((paket / "icons" / f"{n}.svg").read_text("utf-8"), n) for n in namen
    ]
    zeilen = [kopf, '<svg xmlns="http://www.w3.org/2000/svg">', *teile, "</svg>"]
    return "\n".join(zeilen) + "\n"


def feather_symbole(lizenz: str, namen: tuple[str, ...] = SYMBOLE) -> list[str]:
    """Die gewählten Symbole, die der MIT-Teil der LICENSE nennt (alter Name zählt)."""
    teil = lizenz.split("derived from the Feather project:", 1)
    if len(teil) != 2:
        raise SymbolError("LICENSE ohne Liste der Feather-Symbole")
    liste = {n.strip() for n in teil[1].split("\n\n", 2)[1].split(",")}
    return [n for n in namen if FEATHER_NAMEN.get(n, n) in liste]


def lizenz(paket: Path, namen: tuple[str, ...] = SYMBOLE) -> str:
    text = (paket / "LICENSE").read_text("utf-8")
    feather = feather_symbole(text, namen)
    zuordnung = ", ".join(
        f"{n} ← {FEATHER_NAMEN[n]}" for n in feather if n in FEATHER_NAMEN
    )
    kopf = [
        "Lucide-Symbole in symbole.svg",
        "",
        f"Herkunft: npm-Paket lucide-static {VERSION}",
        f"Integrität: {INTEGRITAET}",
        f"Symbole ({len(namen)}): {', '.join(namen)}",
        f"Davon von Feather abgeleitet (MIT-Teil unten, {len(feather)}): "
        + ", ".join(feather),
        f"Im MIT-Teil unter ihrem alten Feather-Namen: {zuordnung}",
        "Die Formen sind unverändert übernommen; Größe, Strich und Füllung setzt",
        "accounti.css. Erzeugt von scripts/symbole.py.",
        "",
        "Vollständige LICENSE des Pakets:",
        "",
    ]
    return "\n".join(kopf) + "\n" + text.rstrip() + "\n"


def pruefe_paket(paket: Path, tarball: Path | None) -> None:
    version = json.loads((paket / "package.json").read_text("utf-8")).get("version")
    if version != VERSION:
        raise SymbolError(f"package.json nennt {version}, erwartet {VERSION}")
    if tarball is not None:
        digest = hashlib.sha512(tarball.read_bytes()).digest()
        ist = "sha512-" + base64.b64encode(digest).decode("ascii")
        if ist != INTEGRITAET:
            raise SymbolError(f"{tarball.name}: Integrität {ist} statt {INTEGRITAET}")


def main(argv: list[str] | None = None) -> int:
    teiler = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    teiler.add_argument("paket", type=Path, help="entpacktes Paket (Ordner package/)")
    teiler.add_argument("--tarball", type=Path, help="Tarball, SHA-512 prüfen")
    teiler.add_argument(
        "--ziel", type=Path, default=ZIEL, help="Ordner für die Dateien"
    )
    args = teiler.parse_args(argv)
    try:
        pruefe_paket(args.paket, args.tarball)
        inhalt = sprite(args.paket)
        lizenztext = lizenz(args.paket)
    except (OSError, SymbolError) as fehler:
        print(f"Fehler: {fehler}", file=sys.stderr)  # noqa: T201
        return 1
    (args.ziel / "symbole.svg").write_text(inhalt, encoding="utf-8")
    (args.ziel / "LIZENZ-lucide.txt").write_text(lizenztext, encoding="utf-8")
    print(f"symbole.svg: {len(inhalt.encode())} Bytes, {len(SYMBOLE)} Symbole")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
