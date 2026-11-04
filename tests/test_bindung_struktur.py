"""Kein Lader fällt im Quellcode still auf ``config/accounti.yaml`` zurück (Baustein 10c
P4a, Prüfung sicher-1/verhalten-1).

Ein Lader ohne Pfad liest die Standarddatei des Arbeitsordners. Unter einer Registry ist
das für ``-g b`` womöglich die Konfiguration einer anderen Gesellschaft (CLI) bzw. nicht
die der gebundenen (Web) — der Stand weist das ab (D5), der Lauf bricht ab. Darum gilt
statisch (AST über ``src/accounti``): Kein Aufruf eines Laders lässt den Pfad weg oder
gibt den Standardpfad ausdrücklich an — außer den wenigen Rückfällen unten, je mit
Grund. Für jeden davon prüft ein zweiter Test, dass der Quellcode ihn nie erreicht (die
Aufrufer geben die Einstellungen mit).

Lader sind die Funktionen aus ``inventar.LADER``, jede Funktion ``lade_*`` mit einem
Pfadparameter mit Standardwert und jede Funktion mit dem Standardpfad als Standardwert.
"""

from __future__ import annotations

import ast
import functools
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from accounti.einstellungen.inventar import LADER

WURZEL = Path(__file__).resolve().parents[1]
SRC = WURZEL / "src"
PFADNAMEN = ("pfad", "config", "konfiguration")

# (Funktion, Lader) → Grund; jeder Eintrag hat unten einen Test, dass der Quellcode den
# Rückfall nicht erreicht
AUSNAHMEN: dict[tuple[str, str], str] = {
    ("accounti.bank.lauf.bank_lauf", "lade_bank_einstellungen"): (
        "nur ohne bank_einstellungen (Werkzeuge, Tests ohne Stand) — CLI und REST "
        "geben sie mit"
    ),
    ("accounti.bank.fints.FinTSProvider.einstellungen", "lade_bank_einstellungen"): (
        "nur ohne mitgegebene FinTS-Einstellungen — rufe_ab und richte_fints_ein "
        "bekommen sie in CLI und REST immer"
    ),
    ("accounti.pruefung.nachforderung._pruefeinstellungen", "lade_pruefung"): (
        "nur ohne mit_pruefeinstellungen — jeder Prüflauf im Quellcode läuft darin"
    ),
}


@dataclass(frozen=True)
class Lader:
    name: str
    stelle: int | None  # Index des Pfads unter den Positionsargumenten
    parameter: str
    definition: str


@functools.cache
def _geparst(wurzel: Path) -> tuple[tuple[str, ast.Module], ...]:
    module = []
    for datei in sorted((wurzel / "accounti").rglob("*.py")):
        relativ = datei.relative_to(wurzel).as_posix()
        modul = relativ.removesuffix(".py").removesuffix("/__init__").replace("/", ".")
        module.append((modul, ast.parse(datei.read_text(encoding="utf-8"))))
    return tuple(module)


def _module(wurzel: Path) -> Iterator[tuple[str, ast.Module]]:
    yield from _geparst(wurzel)


def _ist_standardpfad(knoten: ast.AST | None) -> bool:
    """``STANDARD_PFAD`` (auch ``modul.STANDARD_PFAD``), ``"config/accounti.yaml"``
    oder ``Path("config/accounti.yaml")``."""
    if isinstance(knoten, ast.Name):
        return knoten.id == "STANDARD_PFAD"
    if isinstance(knoten, ast.Attribute):
        return knoten.attr == "STANDARD_PFAD"
    if isinstance(knoten, ast.Constant):
        return knoten.value == "config/accounti.yaml"
    if isinstance(knoten, ast.Call) and len(knoten.args) == 1:  # Path("…")
        return isinstance(knoten.args[0], ast.Constant) and _ist_standardpfad(
            knoten.args[0]
        )
    return False


def _definitionen(
    wurzel: Path,
) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """(Punktname, Knoten) jeder Funktion — Methoden als ``modul.Klasse.methode``,
    verschachtelte als ``modul.außen.innen``."""

    def tiefer(
        knoten: ast.AST, praefix: str
    ) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
        for kind in ast.iter_child_nodes(knoten):
            if isinstance(kind, ast.FunctionDef | ast.AsyncFunctionDef):
                yield f"{praefix}.{kind.name}", kind
                yield from tiefer(kind, f"{praefix}.{kind.name}")
            elif isinstance(kind, ast.ClassDef):
                yield from tiefer(kind, f"{praefix}.{kind.name}")
            else:
                yield from tiefer(kind, praefix)

    for modul, baum in _module(wurzel):
        yield from tiefer(baum, modul)


def _pfadparameter(
    knoten: ast.FunctionDef | ast.AsyncFunctionDef, *, nur_standardpfad: bool
) -> tuple[int | None, str] | None:
    """(Index unter den Positionsargumenten bzw. ``None``, Name) des Pfadparameters mit
    Standardwert — ``nur_standardpfad``: nur mit dem Standardpfad als Standard."""
    a = knoten.args
    positionell = [*a.posonlyargs, *a.args]
    standards: list[ast.expr | None] = [None] * (len(positionell) - len(a.defaults))
    standards += a.defaults
    kandidaten: list[tuple[int | None, ast.arg, ast.expr | None]] = [
        (i, p, d) for i, (p, d) in enumerate(zip(positionell, standards, strict=True))
    ]
    nur_benannt = zip(a.kwonlyargs, a.kw_defaults, strict=True)
    kandidaten += [(None, p, d) for p, d in nur_benannt]
    for i, p, d in kandidaten:
        if d is None:
            continue
        if _ist_standardpfad(d) or (not nur_standardpfad and p.arg in PFADNAMEN):
            return i, p.arg
    return None


def _lader(wurzel: Path) -> dict[str, list[Lader]]:
    """Lader je Funktionsname (ein Name kann mehrfach vorkommen)."""
    inventar = {name.rsplit(".", 1)[-1] for name in LADER}
    lader: dict[str, list[Lader]] = {}
    for punktname, knoten in _definitionen(wurzel):
        allgemein = knoten.name.startswith("lade_") or knoten.name in inventar
        treffer = _pfadparameter(knoten, nur_standardpfad=not allgemein)
        if treffer is not None:
            stelle, parameter = treffer
            lader.setdefault(knoten.name, []).append(
                Lader(knoten.name, stelle, parameter, punktname)
            )
    return lader


Bloecke = tuple[ast.With | ast.AsyncWith, ...]


def _aufrufe(wurzel: Path) -> Iterator[tuple[str, ast.Call, Bloecke]]:
    """(umgebende Funktion, Aufruf, umgebende ``with``-Blöcke) jedes Aufrufs."""

    def tiefer(
        knoten: ast.AST, funktion: str, bloecke: Bloecke
    ) -> Iterator[tuple[str, ast.Call, Bloecke]]:
        for kind in ast.iter_child_nodes(knoten):
            name, innen = funktion, bloecke
            if isinstance(kind, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                name = f"{funktion}.{kind.name}"
            if isinstance(kind, ast.With | ast.AsyncWith):
                innen = (*bloecke, kind)
            if isinstance(kind, ast.Call):
                yield funktion, kind, bloecke
            yield from tiefer(kind, name, innen)

    for modul, baum in _module(wurzel):
        yield from tiefer(baum, modul, ())


def _name(aufruf: ast.Call) -> str | None:
    if isinstance(aufruf.func, ast.Name):
        return aufruf.func.id
    if isinstance(aufruf.func, ast.Attribute):
        return aufruf.func.attr
    return None


def _ohne_pfad(aufruf: ast.Call, lader: Lader) -> bool:
    """Lässt der Aufruf den Pfad weg (oder gibt er den Standardpfad an)?"""
    if any(isinstance(x, ast.Starred) for x in aufruf.args) or any(
        k.arg is None for k in aufruf.keywords
    ):
        return False  # *args/**kw: nicht statisch entscheidbar
    wert: ast.expr | None = None
    if lader.stelle is not None and len(aufruf.args) > lader.stelle:
        wert = aufruf.args[lader.stelle]
    for k in aufruf.keywords:
        if k.arg == lader.parameter:
            wert = k.value
    return wert is None or _ist_standardpfad(wert)


def rueckfaelle(wurzel: Path = SRC) -> set[tuple[str, str]]:
    """(Funktion, Lader) jedes Aufrufs eines Laders ohne Pfad im Quellcode."""
    lader = _lader(wurzel)
    funde = set()
    for funktion, aufruf, _ in _aufrufe(wurzel):
        kandidaten = lader.get(_name(aufruf) or "", [])
        # gleichnamige Lader: ein Fund nur, wenn der Pfad für jeden fehlt; der Lader
        # selbst (Rekursion) zählt nicht
        if (
            kandidaten
            and all(funktion != k.definition for k in kandidaten)
            and all(_ohne_pfad(aufruf, k) for k in kandidaten)
        ):
            funde.add((funktion, kandidaten[0].name))
    return funde


def test_kein_lader_ohne_pfad():
    """Jeder Aufruf eines Laders in ``src`` gibt den Pfad der Gesellschaft an — die
    Ausnahmen sind klein, begründet und alle noch nötig."""
    funde = rueckfaelle()
    assert funde - set(AUSNAHMEN) == set(), sorted(funde - set(AUSNAHMEN))
    assert set(AUSNAHMEN) - funde == set(), "Ausnahme nicht mehr nötig"
    assert all(grund.strip() for grund in AUSNAHMEN.values())


def test_die_lader_des_inventars_sind_erkannt():
    """Die Suche kennt jeden Lader aus ``inventar.LADER`` mit Pfad-Standardwert —
    sonst sähe sie seine Aufrufe nicht."""
    erkannt = {k.definition for liste in _lader(SRC).values() for k in liste}
    definitionen = dict(_definitionen(SRC))
    fehlt = [
        name
        for name in sorted(LADER)
        if _pfadparameter(definitionen[name], nur_standardpfad=False) is not None
        and name not in erkannt
    ]
    assert fehlt == []
    assert {"accounti.integrationen.einstellungen.lade_kontext"} <= erkannt
    assert "accounti.pruefung.verfahrensdoku.erzeuge" in erkannt  # Standard als Wert


def test_suche_erkennt_einen_rueckfall(tmp_path):
    """Die Suche selbst: ohne Pfad, mit dem Standardpfad und über ``modul.lader`` ein
    Fund; mit Pfad (positionell, benannt) keiner."""
    paket = tmp_path / "accounti"
    paket.mkdir()
    (paket / "lader.py").write_text(
        "from pathlib import Path\n"
        "STANDARD_PFAD = Path('config/accounti.yaml')\n"
        "def lade_x(pfad=STANDARD_PFAD): ...\n"
        "def erzeuge(s, config=STANDARD_PFAD): ...\n",
        encoding="utf-8",
    )
    (paket / "rufer.py").write_text(
        "from accounti import lader\n"
        "from accounti.lader import STANDARD_PFAD, erzeuge, lade_x\n"
        "def ohne(): lade_x()\n"
        "def standard(): lader.lade_x(STANDARD_PFAD)\n"
        "def doku(s): erzeuge(s)\n"
        "class K:\n"
        "    def methode(self): return lade_x(pfad=STANDARD_PFAD)\n"
        "def mit(p, s):\n"
        "    lade_x(p), lade_x(pfad=p), erzeuge(s, p), erzeuge(s, config=p)\n",
        encoding="utf-8",
    )
    assert rueckfaelle(tmp_path) == {
        ("accounti.rufer.ohne", "lade_x"),
        ("accounti.rufer.standard", "lade_x"),
        ("accounti.rufer.doku", "erzeuge"),
        ("accounti.rufer.K.methode", "lade_x"),
    }


# --- die Rückfälle der Ausnahmen erreicht der Quellcode nicht -----------------------


def _aufrufe_von(name: str) -> list[tuple[str, ast.Call, Bloecke]]:
    return [(f, a, w) for f, a, w in _aufrufe(SRC) if _name(a) == name]


def _gibt(aufruf: ast.Call, parameter: str, stelle: int | None = None) -> bool:
    """Gibt der Aufruf ``parameter`` an (benannt bzw. an ``stelle``), nicht als
    ``None``?"""
    werte = [k.value for k in aufruf.keywords if k.arg == parameter]
    if stelle is not None and len(aufruf.args) > stelle:
        werte.append(aufruf.args[stelle])
    return any(not (isinstance(w, ast.Constant) and w.value is None) for w in werte)


def test_bank_lauf_und_abruf_bekommen_die_bank_einstellungen():
    """``bank_lauf`` und ``rufe_ab``: jeder Aufruf im Quellcode gibt
    ``bank_einstellungen`` mit — so bekommt auch der FinTS-Provider seine."""
    for name in ("bank_lauf", "rufe_ab"):
        aufrufe = _aufrufe_von(name)
        assert aufrufe, name
        ohne = [f for f, a, _ in aufrufe if not _gibt(a, "bank_einstellungen")]
        assert ohne == [], (name, ohne)


def test_fints_provider_bekommt_seine_einstellungen():
    """Jeder ``FinTSProvider(…)`` und jedes ``richte_fints_ein(…)`` im Quellcode gibt
    die Einstellungen mit (``rufe_ab`` siehe oben)."""
    for name, stelle in (("FinTSProvider", 1), ("richte_fints_ein", None)):
        aufrufe = _aufrufe_von(name)
        assert aufrufe, name
        ohne = [f for f, a, _ in aufrufe if not _gibt(a, "einstellungen", stelle)]
        assert ohne == [], (name, ohne)


def test_prueflaeufe_laufen_mit_den_pruefeinstellungen():
    """Jeder ``fuehre_prueflaeufe_aus(…)`` im Quellcode steht in einem ``with
    mit_pruefeinstellungen(…)`` — der Prüflauf ``beleg_fehlt`` liest dann nie die
    Standarddatei."""
    aufrufe = _aufrufe_von("fuehre_prueflaeufe_aus")
    assert aufrufe
    ohne = [
        f
        for f, _, bloecke in aufrufe
        if not any(
            isinstance(e.context_expr, ast.Call)
            and _name(e.context_expr) == "mit_pruefeinstellungen"
            for w in bloecke
            for e in w.items
        )
    ]
    assert ohne == []
