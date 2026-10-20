"""Gemeinsame Helfer der Befehlsgruppen anlagen, kasse und abschluss (Baustein 12)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import NoReturn, TypeVar

import typer
from rich.markup import escape
from sqlalchemy.orm import Session, sessionmaker

from accounti.befehle import console

T = TypeVar("T")


def ende(text: str) -> NoReturn:
    console.print(f"[red]{escape(text)}[/red]")
    raise typer.Exit(1)


def betrag(text: str, name: str = "Betrag") -> Decimal:
    from accounti.belege.zahlen import parse_betrag

    wert = parse_betrag(text)
    if wert is None:
        ende(f"{name}: '{text}' ist kein Betrag (z.B. 24,90 oder -24.90)")
    return wert


def datum(text: str | None, name: str = "Datum") -> date:
    from accounti.belege.zahlen import parse_datum

    if text is None:
        return date.today()
    wert = parse_datum(text)
    if wert is None:
        ende(f"{name}: '{text}' ist kein Datum (JJJJ-MM-TT oder TT.MM.JJJJ)")
    return wert


def sitzung(db: str) -> sessionmaker[Session]:
    from accounti.db import init_db, session_factory

    engine, make_session = session_factory(db)
    init_db(engine)
    return make_session


def lade(lader: Callable[[str], T], pfad: str) -> T:
    from accounti.konfiguration import KonfigurationError

    try:
        return lader(pfad)
    except (KonfigurationError, ValueError) as fehler:
        ende(str(fehler))
