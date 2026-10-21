"""Datenbank-Setup. SQLite-Default, Postgres-ready via SQLAlchemy.

Tabellen der Bausteine liegen in Modulen ``accounti.db.tabellen_<bereich>`` und
werden automatisch registriert — für ``init_db`` wie für Alembic.
"""

from __future__ import annotations

import importlib
import pkgutil

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def session_factory(
    url: str = "sqlite:///accounti.db",
) -> tuple[Engine, sessionmaker[Session]]:
    """Engine und Sitzungsfabrik. ``hide_parameters``: Fehlermeldungen der Datenbank
    enthalten kein ``[parameters: …]`` — sonst landeten Namen und Belegtexte über
    jede Ausnahme im Protokoll (Spec 4.6)."""
    engine = create_engine(url, hide_parameters=True)
    return engine, sessionmaker(bind=engine)


def registriere_tabellen(
    paket_name: str = __name__, pfade: list[str] | None = None
) -> None:
    """Registriert die Tabellen aus ``tabellen.py`` und allen ``tabellen_*``."""
    from accounti.db import tabellen  # noqa: F401

    for info in pkgutil.iter_modules(pfade if pfade is not None else __path__):
        if info.name.startswith("tabellen_"):
            importlib.import_module(f"{paket_name}.{info.name}")


def init_db(engine: Engine) -> None:
    registriere_tabellen()
    Base.metadata.create_all(engine)
