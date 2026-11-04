"""Abhängigkeiten und Fremdhosts (Spec 10c A99, A117, AK50, AK60; Plan P1, Schritt 13).

P1 bringt keine neue Python-Abhängigkeit: die **Paketnamen** in ``dependencies`` und
``optional-dependencies`` bleiben die von ``main`` (geänderte Versionsgrenzen
bestehender Pakete sind erlaubt und stehen im PR; P6 trägt hier ``segno`` nach).
Vorlagen, Stile und eigene Skripte verweisen auf keinen fremden Host; beigelegte Dateien
Dritter haben ihre Lizenz daneben. Die Browserprobe (``scripts/browserprobe/``) ist ein
Node-Werkzeug mit genauen Versionen, Lockdatei mit Integrität und ``ignore-scripts``.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
API = WURZEL / "src" / "accounti" / "api"
STATISCH = API / "statisch"
PROBE = WURZEL / "scripts" / "browserprobe"

# Paketnamen auf main (8765dd7), ohne Versionsgrenzen und Extras
PAKETE = {
    "sqlalchemy",
    "psycopg",
    "alembic",
    "pydantic",
    "pydantic-settings",
    "typer",
    "rich",
    "pyyaml",
    "litellm",
    "fastapi",
    "uvicorn",
    "jinja2",
    "python-dateutil",
    "pypdf",
    "fpdf2",
    "pillow",
    "cryptography",
}
OPTIONAL = {
    "fints": {"fints"},
    "dev": {
        "pytest",
        "pytest-cov",
        "pytest-asyncio",
        "ruff",
        "mypy",
        "pre-commit",
        "types-pyyaml",
    },
}


def _name(anforderung: str) -> str:
    return re.split(r"[\s\[<>=!~;]", anforderung.strip(), maxsplit=1)[0].lower()


def test_pyproject_ohne_neue_abhaengigkeit():
    projekt = tomllib.loads((WURZEL / "pyproject.toml").read_text(encoding="utf-8"))
    projekt = projekt["project"]
    assert {_name(a) for a in projekt["dependencies"]} == PAKETE
    optional = {
        gruppe: {_name(a) for a in liste}
        for gruppe, liste in projekt.get("optional-dependencies", {}).items()
    }
    assert optional == OPTIONAL
    assert "playwright" not in (WURZEL / "pyproject.toml").read_text(encoding="utf-8")


# erlaubt: der SVG-Namensraum im Sprite (keine Anfrage, nur ein Name)
ERLAUBT = {"http://www.w3.org/2000/svg"}
URL = re.compile(r"""(?:https?:)?//[a-z0-9.-]+\.[a-z]{2,}[^\s"'<>)]*""", re.I)


def _eigene_dateien() -> list[Path]:
    dateien = list((API / "vorlagen").rglob("*.html"))
    dateien += [STATISCH / "accounti.css", STATISCH / "symbole.svg"]
    dateien += [p for p in STATISCH.glob("*.js") if not p.name.startswith("htmx-")]
    return dateien


def test_keine_url_auf_fremde_hosts():
    """AK50: kein CDN, keine Schrift, kein Bild von fremden Servern."""
    for datei in _eigene_dateien():
        text = datei.read_text(encoding="utf-8")
        fremd = {u for u in URL.findall(text) if u not in ERLAUBT}
        assert not fremd, (datei.name, fremd)
    # @import und url() in den Stilen nur relativ (und keine Schrift von außen)
    css = (STATISCH / "accounti.css").read_text(encoding="utf-8")
    assert "@import" not in css and "@font-face" not in css
    for wert in re.findall(r"url\(([^)]*)\)", css):
        assert not wert.strip("'\" ").startswith(("http", "//")), wert


def test_lizenzen_beigelegt():
    """A117: htmx (0BSD) und Lucide (ISC, Feather-Teil MIT) mit Lizenz neben der Datei
    und in THIRD-PARTY.md."""
    htmx = (STATISCH / "LIZENZ-htmx.txt").read_text(encoding="utf-8")
    assert "Zero-Clause BSD" in htmx and "2.0.11" in htmx
    lucide = (STATISCH / "LIZENZ-lucide.txt").read_text(encoding="utf-8")
    assert "ISC License" in lucide and "MIT" in lucide and "1.55.0" in lucide
    assert "Cole Bemis" in lucide
    dritte = (WURZEL / "THIRD-PARTY.md").read_text(encoding="utf-8")
    assert "htmx 2.0.11" in dritte and "lucide-static 1.55.0" in dritte
    assert "LIZENZ-lucide.txt" in dritte
    # die Werkzeuge der Browserprobe sind genannt, aber nicht ausgeliefert
    assert "Playwright 1.59.1" in dritte and "axe-core 4.14.0" in dritte


def test_browserprobe_versionen_fest():
    """Node-Werkzeug mit genauen Versionen, Lockdatei mit Integrität, ohne Skripte."""
    paket = json.loads((PROBE / "package.json").read_text(encoding="utf-8"))
    assert paket.get("private") is True
    assert not paket.get("dependencies")
    abhaengig = paket["devDependencies"]
    assert abhaengig == {"axe-core": "4.14.0", "playwright": "1.59.1"}
    for version in abhaengig.values():
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), version
    sperre = json.loads((PROBE / "package-lock.json").read_text(encoding="utf-8"))
    pakete = {
        name.removeprefix("node_modules/"): eintrag
        for name, eintrag in sperre["packages"].items()
        if name
    }
    assert set(pakete) >= {"axe-core", "playwright", "playwright-core"}
    for name, eintrag in pakete.items():
        assert eintrag["integrity"].startswith("sha512-"), name
        assert eintrag["resolved"].startswith("https://registry.npmjs.org/"), name
    assert pakete["playwright-core"]["version"] == "1.59.1"
    npmrc = (PROBE / ".npmrc").read_text(encoding="utf-8").split()
    assert "ignore-scripts=true" in npmrc and "save-exact=true" in npmrc
    ignoriert = (WURZEL / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in ignoriert and "probe.json" in ignoriert
