"""Repository des Mahnwesens: Mahnungen, Mahnstufe am Posten, Kundeneinstellungen."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounti.db.tabellen import OffenerPostenRow
from accounti.db.tabellen_mahnwesen import MahnKontaktRow, MahnungRow
from accounti.models.mahnwesen import (
    MahnKontakt,
    Mahnung,
    MahnungStatus,
    Zinsabschnitt,
)

_BETRAEGE = (
    "rechnungsbetrag",
    "restbetrag",
    "zinsen",
    "gebuehren_kumuliert",
    "gebuehren",
    "pauschale",
    "summe",
)
_FELDER = (
    "nr",
    "stufe",
    "stufe_name",
    "datum",
    "belegnummer",
    "belegdatum",
    "faellig_am",
    "verzug_ab",
    "zahlungsfrist",
    "unternehmer",
    "einstufung",
    "versendet_am",
    "versand_weg",
    "datei_hash",
    "erstellt_am",
    *_BETRAEGE,
)


def _mahnung(r: MahnungRow) -> Mahnung:
    werte = {f: getattr(r, f) for f in _FELDER}
    for feld in _BETRAEGE:
        werte[feld] = Decimal(str(werte[feld]))
    return Mahnung(
        id=UUID(r.id),
        posten_id=UUID(r.posten_id),
        kontakt_id=UUID(r.kontakt_id),
        status=MahnungStatus(r.status),
        zinsabschnitte=[
            Zinsabschnitt.model_validate(a) for a in json.loads(r.zinsabschnitte)
        ],
        **werte,
    )


def naechste_mahnnummer(session: Session) -> int:
    return (session.scalar(select(func.max(MahnungRow.nr))) or 0) + 1


def speichere_mahnung(session: Session, m: Mahnung) -> None:
    session.add(
        MahnungRow(
            id=str(m.id),
            posten_id=str(m.posten_id),
            kontakt_id=str(m.kontakt_id),
            status=m.status.value,
            zinsabschnitte=json.dumps(
                [a.model_dump(mode="json") for a in m.zinsabschnitte]
            ),
            **{f: getattr(m, f) for f in _FELDER},
        )
    )
    session.flush()


def _zeile(session: Session, nr: int) -> MahnungRow:
    zeile = session.scalar(select(MahnungRow).where(MahnungRow.nr == nr))
    if zeile is None:
        msg = f"Keine Mahnung {nr}."
        raise ValueError(msg)
    return zeile


def lade_mahnung(session: Session, nr: int) -> Mahnung:
    return _mahnung(_zeile(session, nr))


def lade_mahnungen(
    session: Session,
    status: Iterable[MahnungStatus] | None = None,
    posten_id: UUID | None = None,
    kontakt_id: UUID | None = None,
) -> list[Mahnung]:
    abfrage = select(MahnungRow).order_by(MahnungRow.nr)
    if status is not None:
        abfrage = abfrage.where(MahnungRow.status.in_([s.value for s in status]))
    if posten_id is not None:
        abfrage = abfrage.where(MahnungRow.posten_id == str(posten_id))
    if kontakt_id is not None:
        abfrage = abfrage.where(MahnungRow.kontakt_id == str(kontakt_id))
    return [_mahnung(r) for r in session.scalars(abfrage).all()]


def setze_mahnung_status(
    session: Session,
    nr: int,
    status: MahnungStatus,
    versendet_am: datetime | None = None,
    versand_weg: str | None = None,
    datei_hash: str | None = None,
) -> Mahnung:
    zeile = _zeile(session, nr)
    zeile.status = status.value
    zeile.versendet_am = versendet_am
    zeile.versand_weg = versand_weg
    zeile.datei_hash = datei_hash
    session.flush()
    return _mahnung(zeile)


def setze_mahnstufe(session: Session, posten_id: UUID, stufe: int) -> None:
    """Die Mahnstufe am offenen Posten (Feld aus Baustein 4)."""
    zeile = session.get(OffenerPostenRow, str(posten_id))
    if zeile is None:
        msg = f"Offener Posten {posten_id} nicht gefunden."
        raise ValueError(msg)
    zeile.mahnstufe = stufe
    session.flush()


def lade_mahnkontakte(session: Session) -> dict[UUID, MahnKontakt]:
    return {
        UUID(r.kontakt_id): MahnKontakt(
            kontakt_id=UUID(r.kontakt_id),
            mahnsperre=r.mahnsperre,
            sperrgrund=r.sperrgrund,
            unternehmer=r.unternehmer,
        )
        for r in session.scalars(select(MahnKontaktRow)).all()
    }


def speichere_mahnkontakt(session: Session, k: MahnKontakt) -> None:
    zeile = session.get(MahnKontaktRow, str(k.kontakt_id))
    if zeile is None:
        zeile = MahnKontaktRow(kontakt_id=str(k.kontakt_id))
        session.add(zeile)
    zeile.mahnsperre = k.mahnsperre
    zeile.sperrgrund = k.sperrgrund
    zeile.unternehmer = k.unternehmer
    session.flush()
