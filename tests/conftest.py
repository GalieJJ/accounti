"""Gemeinsame Test-Einstellungen."""

import importlib.util

from tests.pg_hilfe import pg_datenbank  # noqa: F401 - Fixture (ACCOUNTI_TEST_PG)

# FinTS ist ein Zusatzpaket (`pip install "accounti[fints]"`): ohne python-fints
# entfallen die Tests, die das Paket selbst brauchen.
collect_ignore = []
if importlib.util.find_spec("fints") is None:
    collect_ignore += [
        "test_bank_fints.py",
        "test_bank_fints_testbank.py",
        "test_cli_fints.py",
    ]
