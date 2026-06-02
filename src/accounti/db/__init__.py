"""Datenbank-Setup. SQLite-Default, Postgres-ready via SQLAlchemy."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def session_factory(
    url: str = "sqlite:///accounti.db",
) -> tuple[Engine, sessionmaker[Session]]:
    engine = create_engine(url)
    return engine, sessionmaker(bind=engine)


def init_db(engine: Engine) -> None:
    from accounti.db import tabellen  # noqa: F401  (registriert die Tabellen)

    Base.metadata.create_all(engine)
