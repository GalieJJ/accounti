"""Welcher Beleg gehört zu einer Buchung? (Queue, Buchungsansicht, Kontenblatt)

Reihenfolge: der Beleg der Buchung selbst, sonst der bestätigte Belegabgleich ihres
Umsatzes (Baustein 5), sonst der Beleg des offenen Postens, dem die Zahlung zugeordnet
ist (Baustein 4) — sonst keiner.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounti.db.repository import lade_beleg, lade_einen_posten
from accounti.db.tabellen import BelegabgleichRow, ZahlungszuordnungRow
from accounti.models import AbgleichStatus, Beleg, Buchungssatz, ZuordnungStatus


def beleg_id_zur_buchung(session: Session, buchung: Buchungssatz) -> str | None:
    if buchung.beleg_id is not None:
        return str(buchung.beleg_id)
    if buchung.transaktion_id is None:
        return None
    tx = str(buchung.transaktion_id)
    abgleich = session.scalars(
        select(BelegabgleichRow.beleg_id)
        .where(
            BelegabgleichRow.transaktion_id == tx,
            BelegabgleichRow.status == AbgleichStatus.BESTAETIGT.value,
        )
        .order_by(BelegabgleichRow.erstellt_am.desc())
        .limit(1)
    ).first()
    if abgleich is not None:
        return str(abgleich)
    posten_id = session.scalars(
        select(ZahlungszuordnungRow.posten_id)
        .where(
            ZahlungszuordnungRow.transaktion_id == tx,
            ZahlungszuordnungRow.status == ZuordnungStatus.GEBUCHT.value,
        )
        .order_by(ZahlungszuordnungRow.erstellt_am)
        .limit(1)
    ).first()
    if posten_id is None:
        return None
    try:
        posten = lade_einen_posten(session, posten_id)  # type: ignore[arg-type]
    except ValueError:
        return None
    return str(posten.beleg_id) if posten.beleg_id is not None else None


def beleg_zur_buchung(session: Session, buchung: Buchungssatz) -> Beleg | None:
    ident = beleg_id_zur_buchung(session, buchung)
    return lade_beleg(session, ident) if ident is not None else None
