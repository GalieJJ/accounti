"""Datenbank-Setup. SQLite-Default, Postgres-ready via SQLAlchemy.

Tabellen der Bausteine liegen in Modulen ``accounti.db.tabellen_<bereich>`` und
werden automatisch registriert — für ``init_db`` wie für Alembic.

``session_factory`` und ``init_db`` hängen außerdem die Journal-Ereignisse und die
Storno-Regel auf der Sitzung ein (``registriere_ereignisse``, Baustein 7): Wer eine
Sitzung von hier bekommt, schreibt das Journal und kann freigegebene Buchungen nicht
ändern — unabhängig davon, welche Module er sonst geladen hat.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from typing import Any

from sqlalchemy import (
    Column,
    Engine,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    create_engine,
    func,
    insert,
    inspect,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Tabellen, die nur einzeln über die Sitzung geändert werden (Journal, Storno-Regel,
# Sperren); Massenwege des ORM lehnen ``ereignisse`` bzw. ``AccountiSitzung`` ab
GESCHUETZT = frozenset({"buchungssaetze", "journal", "buchungskorrekturen"})


class Base(DeclarativeBase):
    pass


def _geschuetzt(mapper: Any) -> str | None:
    zustand: Any = inspect(mapper, raiseerr=False)
    tabelle = getattr(getattr(zustand, "mapper", zustand), "local_table", None)
    name = getattr(tabelle, "name", None)
    return name if name in GESCHUETZT else None


def _massenweg(name: str) -> None:
    from accounti.db.tabellen import UnveraenderbarError

    raise UnveraenderbarError(
        f"Massenänderung an {name} ist gesperrt — Buchungen einzeln über die Sitzung "
        "anlegen und ändern (Journal, Storno-Regel, Sperren)"
    )


class AccountiSitzung(Session):
    """Sitzung ohne die alten ``bulk_*``-Wege auf geschützten Tabellen.

    Sie liefen an Sitzungs- und Mapper-Ereignissen vorbei (Journal, Monats- und
    Jahressperre, Storno-Regel)."""

    def bulk_save_objects(self, objects: Iterable[object], *a: Any, **kw: Any) -> None:
        objekte = list(objects)
        for obj in objekte:
            if (name := _geschuetzt(obj)) is not None:
                _massenweg(name)
        super().bulk_save_objects(objekte, *a, **kw)

    def bulk_insert_mappings(
        self, mapper: Any, mappings: Iterable[dict[str, Any]], *a: Any, **kw: Any
    ) -> None:
        if (name := _geschuetzt(mapper)) is not None:
            _massenweg(name)
        super().bulk_insert_mappings(mapper, mappings, *a, **kw)

    def bulk_update_mappings(
        self, mapper: Any, mappings: Iterable[dict[str, Any]]
    ) -> None:
        if (name := _geschuetzt(mapper)) is not None:
            _massenweg(name)
        super().bulk_update_mappings(mapper, mappings)


def session_factory(
    url: str = "sqlite:///accounti.db",
) -> tuple[Engine, sessionmaker[Session]]:
    """Engine und Sitzungsfabrik. ``hide_parameters``: Fehlermeldungen der Datenbank
    enthalten kein ``[parameters: …]`` — sonst landeten Namen und Belegtexte über
    jede Ausnahme im Protokoll (Spec 4.6)."""
    registriere_ereignisse()
    # SQLite: ein langer Lauf hält die Schreibsperre länger als die 5 s, die sqlite3
    # sonst wartet — andere Schreiber warten bis zu 30 s statt „database is locked“
    zusatz = {"connect_args": {"timeout": 30}} if url.startswith("sqlite") else {}
    engine = create_engine(url, hide_parameters=True, **zusatz)
    return engine, sessionmaker(bind=engine, class_=AccountiSitzung)


def registriere_tabellen(
    paket_name: str = __name__, pfade: list[str] | None = None
) -> None:
    """Registriert die Tabellen aus ``tabellen.py`` und allen ``tabellen_*``."""
    from accounti.db import tabellen  # noqa: F401

    for info in pkgutil.iter_modules(pfade if pfade is not None else __path__):
        if info.name.startswith("tabellen_"):
            importlib.import_module(f"{paket_name}.{info.name}")


_EREIGNISSE: list[bool] = []


def registriere_ereignisse() -> None:
    """Tabellen samt ORM-Sperren und die Journal-Ereignisse (Baustein 7) einhängen."""
    if _EREIGNISSE:
        return
    registriere_tabellen()
    importlib.import_module("accounti.pruefung.ereignisse")
    _EREIGNISSE.append(True)


# Alembic-Revision, deren Schema ``init_db`` anlegt — der Kopf der Migrationen
# (tests/test_db_upgrade.py hält beides gleich; beim Zusammenführen neuer Migrationen
# hier nachziehen)
SCHEMA_STAND = "ddc9a184ddb4"
ALEMBIC_VERSION = "alembic_version"


def versionstabelle() -> Table:
    """``alembic_version`` wie Alembic sie anlegt."""
    return Table(
        ALEMBIC_VERSION,
        MetaData(),
        Column("version_num", String(32), nullable=False),
        PrimaryKeyConstraint("version_num", name="alembic_version_pkc"),
    )


def stemple(engine: Engine, revision: str = SCHEMA_STAND) -> None:
    """Versionsvermerk setzen, wenn es noch keinen gibt (wie ``alembic stamp``)."""
    tabelle = versionstabelle()
    try:
        with engine.begin() as v:
            tabelle.create(v, checkfirst=True)
            if not v.execute(select(func.count()).select_from(tabelle)).scalar():
                v.execute(insert(tabelle).values(version_num=revision))
    except IntegrityError:  # gleichzeitig gestempelt — der Vermerk steht
        pass


def init_db(engine: Engine) -> None:
    """Fehlende Tabellen anlegen.

    Eine **neue** Datenbank (keine Tabelle von accounti, kein Versionsvermerk) bekommt
    danach den Vermerk ``SCHEMA_STAND`` — das angelegte Schema ist der Stand dieser
    Migration. Ohne ihn begänne ``alembic upgrade head`` beim nächsten Update mit der
    ersten Migration und bräche an „table … already exists“ ab (Befund Betrieb B2).
    Ältere Datenbanken ohne Vermerk bringt ``accounti db upgrade`` auf den Stand."""
    registriere_ereignisse()
    vorhanden = set(inspect(engine).get_table_names())
    neu = ALEMBIC_VERSION not in vorhanden and not vorhanden & set(Base.metadata.tables)
    Base.metadata.create_all(engine)
    if neu:
        stemple(engine)
