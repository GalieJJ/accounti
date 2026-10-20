"""Gemeinsame Helfer der Tests zu Anlagen und Jahresabschluss (Baustein 12)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from accounti.db import init_db, session_factory
from accounti.db.repo_anlagen import speichere_anlage
from accounti.db.repository import speichere_buchung
from accounti.models import Buchungssatz, BuchungStatus
from accounti.models.anlagen import AfaArt, Anlagegut

D = Decimal


def datenbank(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    yield factory
    engine.dispose()


def anlegen(
    make_session: sessionmaker[Session],
    kosten: object,
    datum: date,
    art: AfaArt = AfaArt.LINEAR,
    nd: int | None = None,
    konto: str | None = None,
    **kw: object,
) -> Anlagegut:
    konto = konto or {AfaArt.GWG: "0480", AfaArt.SAMMELPOSTEN: "0485"}.get(art, "0420")
    g = Anlagegut.model_validate(
        {
            "bezeichnung": kw.pop("bezeichnung", f"Gut {kosten}"),
            "konto": konto,
            "anschaffungsdatum": datum,
            "anschaffungskosten": D(str(kosten)),
            "nutzungsdauer": nd,
            "afa_art": art,
            **kw,
        }
    )
    with make_session() as s:
        g = speichere_anlage(s, g)
        s.commit()
    return g


def buche(
    make_session: sessionmaker[Session],
    datum: date,
    soll: str,
    haben: str,
    betrag: object,
    text: str = "Buchung",
    status: BuchungStatus = BuchungStatus.GEPRUEFT,
    **kw: object,
) -> Buchungssatz:
    b = Buchungssatz.model_validate(
        {
            "datum": datum,
            "soll_konto": soll,
            "haben_konto": haben,
            "betrag_netto": D(str(betrag)),
            "buchungstext": text,
            "status": status,
            **kw,
        }
    )
    with make_session() as s:
        speichere_buchung(s, b)
        s.commit()
    return b
