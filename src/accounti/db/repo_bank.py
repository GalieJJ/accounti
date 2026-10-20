"""Repository für Kreditkarten und ihre Abrechnungen (Baustein 5, Paket 3)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from accounti.db.repository import _row_zu_transaktion
from accounti.db.tabellen import BankkontoRow, BuchungssatzRow, TransaktionRow
from accounti.db.tabellen_bank import (
    KreditkartenablehnungRow,
    KreditkartenabrechnungRow,
    KreditkartenumsatzRow,
    KreditkarteRow,
)
from accounti.models import Transaktion
from accounti.models.bank import (
    AbrechnungStatus,
    Kreditkarte,
    Kreditkartenabrechnung,
)


def _uuid(wert: str | None) -> UUID | None:
    return UUID(wert) if wert else None


def _str(wert: UUID | None) -> str | None:
    return str(wert) if wert else None


# --- Kreditkarten -----------------------------------------------------------------


def _row_zu_karte(r: KreditkarteRow) -> Kreditkarte:
    return Kreditkarte(
        id=UUID(r.id),
        bankkonto_id=UUID(r.bankkonto_id),
        girokonto_id=UUID(r.girokonto_id),
        endziffern=r.endziffern,
        muster=r.muster,
        abrechnungstag=r.abrechnungstag,
        erstellt_am=r.erstellt_am,
    )


def speichere_kreditkarte(session: Session, k: Kreditkarte) -> None:
    try:
        with session.begin_nested():
            session.add(
                KreditkarteRow(
                    id=str(k.id),
                    bankkonto_id=str(k.bankkonto_id),
                    girokonto_id=str(k.girokonto_id),
                    endziffern=k.endziffern,
                    muster=k.muster,
                    abrechnungstag=k.abrechnungstag,
                    erstellt_am=k.erstellt_am,
                )
            )
    except IntegrityError as fehler:
        raise ValueError(
            "Dieses Konto ist schon als Kreditkarte eingerichtet"
        ) from fehler


def lade_kreditkarten(session: Session) -> list[Kreditkarte]:
    rows = session.query(KreditkarteRow).order_by(KreditkarteRow.erstellt_am).all()
    return [_row_zu_karte(r) for r in rows]


def lade_kreditkarte(session: Session, schluessel: str) -> Kreditkarte:
    """Karte über die Kennung ihres Kontos (Leerzeichen egal) oder den ID-Anfang."""
    kompakt = re.sub(r"\s", "", schluessel).upper()
    kennungen = {
        r.id: r.iban for r in session.query(BankkontoRow.id, BankkontoRow.iban).all()
    }
    treffer = [
        k
        for k in lade_kreditkarten(session)
        if kennungen.get(str(k.bankkonto_id)) == kompakt
        or str(k.id).startswith(schluessel.lower())
    ]
    if len(treffer) != 1:
        msg = (
            f"Keine Kreditkarte '{schluessel}'"
            if not treffer
            else f"'{schluessel}' ist nicht eindeutig"
        )
        raise ValueError(msg)
    return treffer[0]


# --- Abrechnungen -----------------------------------------------------------------


def _row_zu_abrechnung(r: KreditkartenabrechnungRow) -> Kreditkartenabrechnung:
    return Kreditkartenabrechnung(
        id=UUID(r.id),
        kreditkarte_id=UUID(r.kreditkarte_id),
        stichtag=r.stichtag,
        von=r.von,
        beleg_id=_uuid(r.beleg_id),
        summe=Decimal(str(r.summe)),
        anzahl=r.anzahl,
        belastung_id=_uuid(r.belastung_id),
        belastung_betrag=(
            Decimal(str(r.belastung_betrag)) if r.belastung_betrag is not None else None
        ),
        status=AbrechnungStatus(r.status),
        befund=r.befund,
        erstellt_am=r.erstellt_am,
    )


def _werte(a: Kreditkartenabrechnung) -> dict[str, object]:
    return {
        "kreditkarte_id": str(a.kreditkarte_id),
        "stichtag": a.stichtag,
        "von": a.von,
        "beleg_id": _str(a.beleg_id),
        "summe": a.summe,
        "anzahl": a.anzahl,
        "belastung_id": _str(a.belastung_id),
        "belastung_betrag": a.belastung_betrag,
        "status": a.status.value,
        "befund": (a.befund or "")[:500] or None,
        "erstellt_am": a.erstellt_am,
    }


def speichere_abrechnung(
    session: Session, a: Kreditkartenabrechnung, transaktion_ids: Iterable[UUID]
) -> None:
    """Abrechnung samt Zuordnung ihrer Einzelumsätze (jeder höchstens einmal)."""
    try:
        with session.begin_nested():
            session.add(KreditkartenabrechnungRow(id=str(a.id), **_werte(a)))
            session.flush()
            for tx_id in transaktion_ids:
                session.add(
                    KreditkartenumsatzRow(
                        transaktion_id=str(tx_id), abrechnung_id=str(a.id)
                    )
                )
    except IntegrityError as fehler:
        msg = "Abrechnung oder einer ihrer Umsätze ist schon erfasst"
        raise ValueError(msg) from fehler


def aktualisiere_abrechnung(session: Session, a: Kreditkartenabrechnung) -> None:
    row = session.get(KreditkartenabrechnungRow, str(a.id))
    if row is None:
        raise ValueError(f"Abrechnung {a.id} nicht gefunden")
    for feld, wert in _werte(a).items():
        setattr(row, feld, wert)
    session.flush()


def lade_abrechnungen(
    session: Session,
    kreditkarte_id: UUID | None = None,
    status: set[AbrechnungStatus] | None = None,
) -> list[Kreditkartenabrechnung]:
    query = session.query(KreditkartenabrechnungRow)
    if kreditkarte_id is not None:
        query = query.filter(
            KreditkartenabrechnungRow.kreditkarte_id == str(kreditkarte_id)
        )
    if status is not None:
        query = query.filter(
            KreditkartenabrechnungRow.status.in_([s.value for s in status])
        )
    rows = query.order_by(
        KreditkartenabrechnungRow.stichtag, KreditkartenabrechnungRow.erstellt_am
    ).all()
    return [_row_zu_abrechnung(r) for r in rows]


def ergaenze_abrechnung(
    session: Session, a: Kreditkartenabrechnung, transaktion_ids: Iterable[UUID]
) -> None:
    """Weitere Umsätze einer Abrechnung zuordnen (Summe und Anzahl stehen in ``a``)."""
    try:
        with session.begin_nested():
            for tx_id in transaktion_ids:
                session.add(
                    KreditkartenumsatzRow(
                        transaktion_id=str(tx_id), abrechnung_id=str(a.id)
                    )
                )
            session.flush()
    except IntegrityError as fehler:
        raise ValueError("Ein Umsatz gehört schon zu einer Abrechnung") from fehler
    aktualisiere_abrechnung(session, a)


def lehne_belastung_ab(session: Session, abrechnung_id: UUID, tx_id: UUID) -> None:
    if session.get(KreditkartenablehnungRow, (str(abrechnung_id), str(tx_id))):
        return
    session.add(
        KreditkartenablehnungRow(
            abrechnung_id=str(abrechnung_id), transaktion_id=str(tx_id)
        )
    )
    session.flush()


def abgelehnte_belastungen(session: Session) -> set[tuple[UUID, UUID]]:
    """(Abrechnung, Belastung), die ein Mensch getrennt hat."""
    rows = session.query(
        KreditkartenablehnungRow.abrechnung_id, KreditkartenablehnungRow.transaktion_id
    ).all()
    return {(UUID(a), UUID(t)) for a, t in rows}


def loesche_buchung(session: Session, buchung_id: UUID) -> None:
    """Vorläufige Buchung des Kartenabgleichs entfernen (noch nicht freigegeben).

    Über die Sitzung, nicht als Massen-``DELETE``: So greifen Jahres- und
    Monatssperre, die Storno-Regel und das Journal (Baustein 7).
    """
    zeile = session.get(BuchungssatzRow, str(buchung_id))
    if zeile is not None:
        session.delete(zeile)
    session.flush()


def abgerechnete_transaktion_ids(session: Session) -> set[UUID]:
    """Umsätze von Kartenkonten, die schon zu einer Abrechnung gehören."""
    rows = session.query(KreditkartenumsatzRow.transaktion_id).all()
    return {UUID(t) for (t,) in rows}


def lade_transaktionen_nach_schluessel(
    session: Session, schluessel: Iterable[str]
) -> dict[str, Transaktion]:
    werte = [s for s in schluessel if s]
    if not werte:
        return {}
    rows = (
        session.query(TransaktionRow)
        .filter(TransaktionRow.dublettenschluessel.in_(werte))
        .all()
    )
    return {str(r.dublettenschluessel): _row_zu_transaktion(r) for r in rows}
