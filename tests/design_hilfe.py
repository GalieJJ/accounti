"""Hilfen für die Design-Tests (Plan P1): Kontrast nach WCAG 2.2, ein kleiner
CSS-Leser für ``accounti.css`` (Ebenen, Tokenblöcke, Regeln mit ihrem Kontext) und der
Leser für die Tokenblöcke der Design-Leinwand.

Der CSS-Leser kennt nur, was ``accounti.css`` nutzt: Kommentare, ``@layer``-Anweisungen
und -Blöcke, ``@media`` und Regeln mit Deklarationen — keine CSS-Verschachtelung.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
STATISCH = WURZEL / "src" / "accounti" / "api" / "statisch"
CSS = STATISCH / "accounti.css"
PRUEFEN_CSS = STATISCH / "pruefen.css"
LEINWAND = WURZEL / "docs" / "design" / "2026-10-26-leinwand"

# --- Kontrast ------------------------------------------------------------------------


def _rgb(farbe: str) -> tuple[float, float, float]:
    farbe = farbe.strip().lstrip("#")
    if len(farbe) == 3:
        farbe = "".join(z * 2 for z in farbe)
    return tuple(int(farbe[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(k * 255):02x}" for k in rgb)


def leuchtdichte(farbe: str) -> float:
    """Relative Leuchtdichte nach WCAG 2.2 (sRGB)."""

    def linear(k: float) -> float:
        return k / 12.92 if k <= 0.04045 else ((k + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(k) for k in _rgb(farbe))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def kontrast(a: str, b: str) -> float:
    hell, dunkel = sorted((leuchtdichte(a), leuchtdichte(b)), reverse=True)
    return (hell + 0.05) / (dunkel + 0.05)


def mische(schleier: str, flaeche: str) -> str:
    """``rgb(r g b / alpha)`` über einer deckenden Fläche (wie der Browser in sRGB)."""
    m = re.fullmatch(
        r"rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)\s*[/,]\s*([\d.]+)\s*\)",
        schleier.strip(),
    )
    assert m, schleier
    alpha = float(m.group(4))
    oben = [int(m.group(i)) / 255 for i in (1, 2, 3)]
    unten = _rgb(flaeche)
    return _hex(
        tuple(alpha * o + (1 - alpha) * u for o, u in zip(oben, unten, strict=True))
    )  # type: ignore[arg-type]


# --- CSS lesen ---------------------------------------------------------------------


@dataclass
class Regel:
    """Eine Regel bzw. At-Regel. ``kinder`` hat nur eine At-Regel mit Block;
    ``anweisung`` ist eine At-Regel ohne Block (``@layer a, b;``)."""

    kopf: str
    deklarationen: list[tuple[str, str]] = field(default_factory=list)
    kinder: list[Regel] = field(default_factory=list)
    anweisung: bool = False

    def wert(self, name: str) -> str | None:
        werte = [w for n, w in self.deklarationen if n == name]
        return werte[-1] if werte else None


def _deklaration(text: str) -> tuple[str, str] | None:
    text = text.strip()
    if not text:
        return None
    name, _, wert = text.partition(":")
    return name.strip().lower(), " ".join(wert.split())


def lies_css(text: str) -> list[Regel]:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    pos = 0

    def koerper() -> tuple[list[tuple[str, str]], list[Regel]]:
        nonlocal pos
        deklarationen: list[tuple[str, str]] = []
        kinder: list[Regel] = []
        puffer = ""
        while pos < len(text):
            zeichen = text[pos]
            pos += 1
            if zeichen in "\"'":
                ende = text.index(zeichen, pos)
                puffer += zeichen + text[pos : ende + 1]
                pos = ende + 1
            elif zeichen == "{":
                kopf = " ".join(puffer.split())
                d, k = koerper()
                kinder.append(Regel(kopf, d, k))
                puffer = ""
            elif zeichen == "}":
                break
            elif zeichen == ";":
                if puffer.strip().startswith("@"):
                    kinder.append(Regel(" ".join(puffer.split()), anweisung=True))
                elif (d := _deklaration(puffer)) is not None:
                    deklarationen.append(d)
                puffer = ""
            else:
                puffer += zeichen
        if (d := _deklaration(puffer)) is not None and not puffer.strip().startswith(
            "@"
        ):
            deklarationen.append(d)
        return deklarationen, kinder

    _, oben = koerper()
    return oben


@dataclass(frozen=True)
class Stelle:
    """Eine Stilregel mit den At-Regeln, in denen sie steht (außen zuerst)."""

    kontext: tuple[str, ...]
    regel: Regel

    @property
    def ebene(self) -> str | None:
        for kopf in self.kontext:
            if kopf.startswith("@layer "):
                return kopf.removeprefix("@layer ").strip()
        return None

    @property
    def medien(self) -> tuple[str, ...]:
        return tuple(k for k in self.kontext if k.startswith("@media"))


def stilregeln(regeln: list[Regel], kontext: tuple[str, ...] = ()) -> Iterator[Stelle]:
    for regel in regeln:
        if regel.anweisung:
            continue
        if regel.kopf.startswith("@"):
            yield from stilregeln(regel.kinder, (*kontext, regel.kopf))
        else:
            yield Stelle(kontext, regel)


def medienregeln(regeln: list[Regel]) -> Iterator[str]:
    for regel in regeln:
        if regel.kopf.startswith("@media"):
            yield regel.kopf
        yield from medienregeln(regel.kinder)


def selektoren(kopf: str) -> list[str]:
    return [" ".join(s.split()) for s in kopf.split(",")]


def css(datei: Path = CSS) -> list[Regel]:
    return lies_css(datei.read_text(encoding="utf-8"))


HELL = ":root, .thema-hell"
DUNKEL = ':root[data-theme="dunkel"], .thema-dunkel'
AUTO = ':root[data-theme="auto"]'
DUNKEL_MEDIEN = "@media (prefers-color-scheme: dark)"


@dataclass(frozen=True)
class Token:
    hell: dict[str, str]
    dunkel: dict[str, str]  # der Block für data-theme="dunkel" und .thema-dunkel
    dunkel_auto: dict[str, str]  # derselbe Block unter prefers-color-scheme: dark
    masse: dict[str, str]  # Maß-Token, für beide Modi gleich (:root allein)
    color_scheme: dict[str, str]  # Selektor → color-scheme


def token(regeln: list[Regel] | None = None) -> Token:
    regeln = css() if regeln is None else regeln
    bloecke: dict[tuple[tuple[str, ...], str], Regel] = {}
    for stelle in stilregeln(regeln):
        if stelle.ebene == "token":
            bloecke[(stelle.medien, " ".join(stelle.regel.kopf.split()))] = stelle.regel

    def variablen(schluessel: tuple[tuple[str, ...], str]) -> dict[str, str]:
        regel = bloecke.get(schluessel)
        if regel is None:
            return {}
        return {n: w for n, w in regel.deklarationen if n.startswith("--")}

    return Token(
        hell=variablen(((), HELL)),
        dunkel=variablen(((), DUNKEL)),
        dunkel_auto=variablen(((DUNKEL_MEDIEN,), AUTO)),
        masse=variablen(((), ":root")),
        color_scheme={
            kopf: r.wert("color-scheme") or ""
            for (medien, kopf), r in bloecke.items()
            if not medien and r.wert("color-scheme")
        },
    )


# --- Leinwand ----------------------------------------------------------------------


def _tokenbloecke(datei: Path) -> dict[bool, dict[str, str]]:
    text = datei.read_text(encoding="utf-8")
    bloecke: dict[bool, dict[str, str]] = {False: {}, True: {}}
    for dunkel, inhalt in re.findall(r"\.a(\.dunkel)?\s*\{([^}]*)\}", text):
        for name, wert in re.findall(r"(--[\w-]+)\s*:\s*([^;]+)", inhalt):
            bloecke[bool(dunkel)][name] = wert.strip()
    return bloecke


def leinwand_tokenbloecke(datei: Path) -> dict[bool, dict[str, str]]:
    """Hell (``False``, ``.a{…}``) und dunkel (``True``, ``.a.dunkel{…}``) einer
    Zeichenfläche."""
    return _tokenbloecke(datei)


def leinwand_token() -> dict[bool, dict[str, str]]:
    """Die Farb-Token der Leinwand je Modus über alle Zeichenflächen; ein Widerspruch
    zwischen zwei Zeichenflächen lässt den aufrufenden Test scheitern."""
    werte: dict[bool, dict[str, set[str]]] = {False: {}, True: {}}
    for datei in sorted(LEINWAND.glob("*.dc.html")):
        for dunkel, bloecke in _tokenbloecke(datei).items():
            for name, wert in bloecke.items():
                werte[dunkel].setdefault(name, set()).add(wert)
    widerspruch = {
        (dunkel, name): sorted(w)
        for dunkel, namen in werte.items()
        for name, w in namen.items()
        if len(w) > 1
    }
    assert widerspruch == {}
    return {
        dunkel: {name: next(iter(w)) for name, w in namen.items()}
        for dunkel, namen in werte.items()
    }
