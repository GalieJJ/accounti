"""Gemeinsame Bausteine der Tests zu Baustein 7 (Prüfung, Journal, Storno)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.orm import Session, sessionmaker

from accounti.db import init_db, session_factory
from accounti.db.repository import (
    speichere_beleg,
    speichere_buchung,
    speichere_kontakt,
    speichere_transaktion,
)
from accounti.models import (
    Beleg,
    Belegart,
    Belegposition,
    Belegrichtung,
    BelegStatus,
    Buchungssatz,
    BuchungStatus,
    Kontakt,
    Transaktion,
    TransaktionQuelle,
)


def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'a.db').as_posix()}"


@pytest.fixture(name="make_session")
def make_session_fixture(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    """Leere SQLite-Datenbank mit allen Tabellen (Import im Test: ``# noqa: F401``)."""
    engine, factory = session_factory(db_url(tmp_path))
    init_db(engine)
    yield factory
    engine.dispose()


def umsatz(
    betrag: str = "-119.00",
    tag: date = date(2026, 8, 12),
    zweck: str = "STADTWERKE STROM ABSCHLAG",
    name: str | None = "Stadtwerke Hamburg",
    **kw: object,
) -> Transaktion:
    return Transaktion(
        datum=tag,
        betrag=Decimal(betrag),
        verwendungszweck=zweck,
        gegenkonto_name=name,
        quelle=TransaktionQuelle.BANK,
        rohtext="x",
        **kw,  # type: ignore[arg-type]
    )


def buchung(
    tx: Transaktion | None = None,
    *,
    status: BuchungStatus = BuchungStatus.ZUR_PRUEFUNG,
    soll: str = "4900",
    haben: str = "1200",
    netto: str = "100.00",
    steuer: str | None = "19.00",
    schluessel: int | None = 9,
    tag: date | None = None,
    **kw: object,
) -> Buchungssatz:
    return Buchungssatz(
        transaktion_id=tx.id if tx else None,
        datum=tag or (tx.datum if tx else date(2026, 8, 12)),
        soll_konto=soll,
        haben_konto=haben,
        betrag_netto=Decimal(netto),
        steuer_schluessel=schluessel,
        steuer_betrag=Decimal(steuer) if steuer is not None else None,
        buchungstext="Strom",
        status=status,
        confidence=0.5,
        **kw,  # type: ignore[arg-type]
    )


def beleg(
    *,
    belegart: Belegart = Belegart.EINGANGSRECHNUNG,
    richtung: Belegrichtung = Belegrichtung.EINGANG,
    nummer: str | None = "RE-2026-0815",
    tag: date | None = date(2026, 8, 10),
    netto: str | None = "100.00",
    steuer: str | None = "19.00",
    brutto: str | None = "119.00",
    lieferant: str | None = "Stadtwerke Hamburg GmbH",
    ust_id: str | None = None,
    datei_hash: str = "a" * 64,
    status: BelegStatus = BelegStatus.ERFASST,
    positionen: list[tuple[str, str, str | None, str | None]] | None = None,
    **kw: object,
) -> Beleg:
    b = Beleg(
        belegart=belegart,
        richtung=richtung,
        belegnummer=nummer,
        belegdatum=tag,
        lieferant_name=lieferant,
        lieferant_ust_id=ust_id,
        netto=Decimal(netto) if netto is not None else None,
        steuer=Decimal(steuer) if steuer is not None else None,
        brutto=Decimal(brutto) if brutto is not None else None,
        datei_hash=datei_hash,
        dateiname="rechnung.pdf",
        kanal="ordner",
        herkunft="test",
        eingegangen_am=datetime(2026, 8, 11, 9, 0),
        aufbewahren_bis=date(2036, 12, 31),
        status=status,
        **kw,  # type: ignore[arg-type]
    )
    if positionen is None:
        positionen = [("Strom August", netto or "0", "19", steuer)]
    return b.model_copy(
        update={
            "positionen": [
                Belegposition(
                    beleg_id=b.id,
                    bezeichnung=text,
                    netto=Decimal(n),
                    steuersatz=Decimal(s) if s is not None else None,
                    steuer_betrag=Decimal(st) if st is not None else None,
                )
                for text, n, s, st in positionen
            ]
        }
    )


def kontakt(**kw: object) -> Kontakt:
    werte: dict[str, object] = {
        "name": "Stadtwerke Hamburg GmbH",
        "land": "DE",
        "kreditor_konto": "70001",
    }
    werte.update(kw)
    return Kontakt.model_validate(werte)


def anlegen(make_session: sessionmaker[Session], *objekte: object) -> None:
    with make_session() as s:
        for o in objekte:
            if isinstance(o, Transaktion):
                speichere_transaktion(s, o)
            elif isinstance(o, Buchungssatz):
                speichere_buchung(s, o)
            elif isinstance(o, Beleg):
                speichere_beleg(s, o)
            elif isinstance(o, Kontakt):
                speichere_kontakt(s, o)
            else:  # pragma: no cover
                raise TypeError(o)
            s.flush()
        s.commit()


def kurz(ident: UUID) -> str:
    return str(ident)[:8]
