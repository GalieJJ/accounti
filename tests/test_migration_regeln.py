"""Regeln für Migrationstests aller Pakete (Plan 10c P1, Befund B10).

Kein Migrationstest hängt am Kopf der Kette: jeder Test führt seine eigene Revision als
Konstante und liest den Vorgänger aus dem ``ScriptDirectory``; Downgrades gehen auf
ausdrückliche Revisionen. Sonst würde ein Test rot (oder prüfte das Falsche), sobald ein
anderes Paket eine Migration darüber kettet. Erlaubt ist nur, Köpfe zu zählen
(``count("(head)") == 1``); ob ``SCHEMA_STAND`` der Kopf ist, prüft allein
``tests/test_db_upgrade.py::test_schema_stand_ist_der_kopf_der_migrationen``.
"""

from __future__ import annotations

import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent

VERBOTEN = (
    (re.compile(r"""["']downgrade["']\s*,\s*["']-\d+["']"""), "relatives Downgrade"),
    (re.compile(r"""["']upgrade["']\s*,\s*["']\+\d+["']"""), "relatives Upgrade"),
    (re.compile(r"\bget_current_head\s*\("), "get_current_head()"),
    (
        re.compile(r"""\(head\)["']?\s*(?!\)\s*\.count|["']\)\s*==)"""),
        "Aussage über (head)",
    ),
)
ERLAUBT = re.compile(r"""\.count\(\s*["']\(head\)["']\s*\)\s*==\s*1""")


def verstoesse(text: str) -> list[tuple[int, str]]:
    funde = []
    for nummer, zeile in enumerate(text.splitlines(), 1):
        ohne = ERLAUBT.sub("", zeile)
        for muster, art in VERBOTEN:
            if muster.search(ohne):
                funde.append((nummer, art))
    return funde


def test_kein_migrationstest_haengt_am_kopf():
    funde = {
        datei.name: f
        for datei in sorted(TESTS.glob("test_*.py"))
        if datei.name != Path(__file__).name
        and (f := verstoesse(datei.read_text(encoding="utf-8")))
    }
    assert funde == {}


def test_waechter_erkennt_kopfannahmen():
    assert verstoesse('alembic(db, "downgrade", "-1")') == [(1, "relatives Downgrade")]
    assert verstoesse("kopf = skripte.get_current_head()") == [
        (1, "get_current_head()")
    ]
    assert verstoesse('assert f"{A} -> {B} (head)" in verlauf') == [
        (1, "Aussage über (head)")
    ]
    assert verstoesse('assert ok(alembic(db, "heads")).count("(head)") == 1') == []
    assert verstoesse('alembic(db, "downgrade", VOR)') == []
