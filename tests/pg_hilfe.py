"""PostgreSQL für einzelne Tests — nur, wenn ``ACCOUNTI_TEST_PG`` gesetzt ist.

``ACCOUNTI_TEST_PG=postgresql+psycopg://nutzer:pw@127.0.0.1:55432/postgres`` zeigt auf
einen Server, auf dem der Benutzer Datenbanken anlegen darf (z. B. ein Wegwerf-Container
``docker run --rm -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=… postgres:16``). Jeder
Test bekommt eine eigene, frische Datenbank, die danach wieder verschwindet.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, make_url

UMGEBUNG = "ACCOUNTI_TEST_PG"

mit_postgresql = pytest.mark.skipif(
    not os.environ.get(UMGEBUNG), reason=f"{UMGEBUNG} nicht gesetzt (kein PostgreSQL)"
)


@pytest.fixture
def pg_datenbank() -> Iterator[Callable[[], str]]:
    """Fabrik für frische Datenbanken auf dem Testserver; räumt hinterher auf."""
    basis = os.environ[UMGEBUNG]
    admin = create_engine(basis, isolation_level="AUTOCOMMIT")
    angelegt: list[str] = []

    def neu() -> str:
        name = f"accounti_test_{uuid4().hex[:12]}"
        with admin.connect() as v:
            v.exec_driver_sql(f'CREATE DATABASE "{name}"')
        angelegt.append(name)
        return make_url(basis).set(database=name).render_as_string(hide_password=False)

    yield neu
    with admin.connect() as v:
        for name in angelegt:
            v.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    admin.dispose()
