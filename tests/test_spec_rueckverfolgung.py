"""Rückverfolgung der Spec 10c (Anhang D) und die abgelegte Design-Leinwand (Plan P1,
Schritt 0).

Die Spec ordnet jeder Anforderung A1–A126 in Anhang D ihre Akzeptanzkriterien zu; die
Kriterien in Abschnitt 7 nennen ihre Anforderungen in Klammern, auch als Bereich
(„(A1–A4)“). Der Test hält beides beim Nachtragen stimmig. Die Leinwand liegt
unverändert unter ``docs/design/2026-10-26-leinwand/``; ihre Tokenblöcke (``.a{…}``
hell, ``.a.dunkel{…}`` dunkel) müssen in allen Zeichenflächen übereinstimmen.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.design_hilfe import LEINWAND, leinwand_token, leinwand_tokenbloecke

WURZEL = Path(__file__).resolve().parents[1]
SPEC = WURZEL / "docs" / "specs" / "2026-10-26-oberflaeche-einrichtung.md"
SKIZZEN = WURZEL / "docs" / "specs" / "2026-10-26-oberflaeche-skizzen.md"


def _abschnitt(text: str, anfang: str, ende: str) -> str:
    a = text.index(anfang)
    return text[a : text.index(ende, a)]


def bezuege(text: str) -> set[int]:
    """Anforderungen, die ein Kriterium in Klammern nennt — Bereiche wie „A1–A4“
    (Halbgeviertstrich oder Bindestrich) aufgelöst."""
    nummern: set[int] = set()
    for klammer in re.findall(r"\(([^()]*)\)", text):
        for von, bis in re.findall(r"\bA(\d+)\s*[–-]\s*A(\d+)\b", klammer):
            nummern |= set(range(int(von), int(bis) + 1))
        nummern |= {int(n) for n in re.findall(r"\bA(\d+)\b", klammer)}
    return nummern


@dataclass(frozen=True)
class Spec:
    anforderungen: dict[int, str]  # Nummer → Paket aus Abschnitt 6
    kriterien: dict[int, set[int]]  # AK-Nummer → genannte Anforderungen
    d: dict[int, tuple[str, set[int]]]  # Anhang D: Nummer → (Paket, Kriterien)


@pytest.fixture(scope="module")
def spec() -> Spec:
    text = SPEC.read_text(encoding="utf-8")
    s6 = _abschnitt(text, "\n## 6. Anforderungen", "\n## 7. ")
    s7 = _abschnitt(text, "\n## 7. Akzeptanzkriterien", "\n## 8. ")
    anhang_d = text[text.index("\n## Anhang D") :]
    anforderungen = {
        int(n): paket.strip()
        for n, paket in re.findall(r"^- \*\*A(\d+) \(([^)]*)\)", s6, re.M)
    }
    teile = re.split(r"^\d+\. \*\*AK(\d+)\*\*", s7, flags=re.M)
    kriterien = {int(teile[i]): bezuege(teile[i + 1]) for i in range(1, len(teile), 2)}
    zeilen = re.findall(r"^\| A(\d+) \| ([^|]+) \| [^|]+ \| ([^|]+) \|", anhang_d, re.M)
    tabelle = {
        int(a): (paket.strip(), {int(k) for k in re.findall(r"AK(\d+)", ak)})
        for a, paket, ak in zeilen
    }
    return Spec(anforderungen, kriterien, tabelle)


def test_bereichsangaben_werden_aufgeloest():
    assert bezuege("Text (A1–A4).") == {1, 2, 3, 4}
    assert bezuege("(A24-A28, A58–A60)") == {24, 25, 26, 27, 28, 58, 59, 60}
    assert bezuege("(A22, A107) und AK44 ohne Klammer A9") == {22, 107}


def test_bereichsangabe_in_ak44_nennt_a2_und_a3(spec):
    assert {1, 2, 3, 4} <= spec.kriterien[44]


def test_jede_anforderung_in_anhang_d(spec):
    anforderungen = spec.anforderungen
    assert sorted(anforderungen) == list(range(1, 127))
    assert set(spec.d) == set(anforderungen)


def test_jede_anforderung_in_einem_kriterium(spec):
    genannt = set().union(*spec.kriterien.values())
    assert set(spec.anforderungen) - genannt == set()


def test_kriterien_nennen_nur_vorhandene_anforderungen(spec):
    genannt = set().union(*spec.kriterien.values())
    assert genannt - set(spec.anforderungen) == set()


def test_paket_in_anhang_d_wie_im_abschnitt_6(spec):
    abweichend = {
        a: (paket, spec.d[a][0])
        for a, paket in spec.anforderungen.items()
        if spec.d[a][0] != paket
    }
    assert abweichend == {}


def test_anhang_d_nennt_die_kriterien_aus_abschnitt_7(spec):
    """Anhang D ist aus den Verweisen der Kriterien erzeugt — beim Nachtragen beides."""
    kriterien = spec.kriterien
    abweichend = {}
    for a in spec.anforderungen:
        aus_7 = {k for k, r in kriterien.items() if a in r}
        if aus_7 != spec.d[a][1]:
            abweichend[a] = (sorted(aus_7), sorted(spec.d[a][1]))
    assert abweichend == {}


def test_spec_und_skizzen_ohne_pfade_auf_den_scratchpad():
    for datei in (SPEC, SKIZZEN):
        text = datei.read_text(encoding="utf-8")
        assert "/tmp/" not in text and "scratchpad" not in text.lower(), datei.name


def test_leinwand_abgelegt():
    """Alle Zeichenflächen, die ``canvas.json`` in ``order`` nennt, liegen da (die
    Leinwand ist seit Fassung 4 des Plans gewachsen — keine feste Zahl), jede hat einen
    hellen und einen dunklen Tokenblock, und die Token stimmen überall überein."""
    leinwand = json.loads((LEINWAND / "canvas.json").read_text(encoding="utf-8"))
    flaechen = leinwand["order"]
    assert len(flaechen) >= 10 and set(flaechen) == set(leinwand["boards"])
    vorhanden = {p.name for p in LEINWAND.glob("*.dc.html")}
    assert vorhanden == set(flaechen)
    for name in flaechen:
        bloecke = leinwand_tokenbloecke(LEINWAND / name)
        assert bloecke[False] and set(bloecke[False]) == set(bloecke[True]), name
    token = leinwand_token()
    assert set(token[False]) == set(token[True])
    readme = (LEINWAND / "README.md").read_text(encoding="utf-8")
    assert "Die Richtung passt. Setz das Design so in Baustein 10c um." in readme
    for name in flaechen:
        assert name.removesuffix(".dc.html") in readme, name
