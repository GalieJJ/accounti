"""Abgleichslauf: Bankumsätze und Belege zusammenführen, bevor kontiert wird.

Reihenfolge: ``opos zuordnen`` (Rechnungen über offene Posten) → ``bank abgleich``
(Quittungen und sonstige Belege) → ``classify`` (aus dem Beleg, sonst Regelwerk/LLM).
Eindeutiges wird sofort bestätigt, Mehrdeutiges als Vorschlag gespeichert; ein
bestätigter Vorschlag verwirft die konkurrierenden für denselben Umsatz und Beleg.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.bank.abgleich import (
    ABGLEICHBAR,
    Abgleichsergebnis,
    Kandidat,
    gleiche_ab,
)
from accounti.db.repository import (
    gebuchte_beleg_ids,
    lade_abgleiche,
    lade_belege,
    lade_transaktionen,
    lade_zuordnungen,
    setze_abgleich_status,
    speichere_abgleich,
    verbuchte_beleg_ids,
)
from accounti.models import (
    AbgleichStatus,
    Beleg,
    Belegabgleich,
    BelegStatus,
    Transaktion,
    ZuordnungStatus,
)
from accounti.opos.zahlungslauf import offene_transaktionen


class AbgleichError(RuntimeError):
    """Bestätigen oder Ablehnen ist so nicht möglich."""


def _belege_mit_umsatz(session: Session) -> set[UUID]:
    bestaetigt = lade_abgleiche(session, status={AbgleichStatus.BESTAETIGT})
    return (
        {a.beleg_id for a in bestaetigt}
        | gebuchte_beleg_ids(session)
        | verbuchte_beleg_ids(session)
    )


def abgleichbare_belege(session: Session) -> list[Beleg]:
    """Erfasste Quittungen/sonstige Belege mit Betrag, noch ohne Umsatz oder Buchung."""
    belegt = _belege_mit_umsatz(session) | {
        a.beleg_id
        for a in lade_abgleiche(session, status={AbgleichStatus.VORGESCHLAGEN})
    }
    return [
        b
        for b in lade_belege(session, status={BelegStatus.ERFASST})
        if b.belegart in ABGLEICHBAR and b.brutto and b.id not in belegt
    ]


def _speichere(session: Session, k: Kandidat, status: AbgleichStatus) -> None:
    speichere_abgleich(
        session,
        Belegabgleich(
            transaktion_id=k.transaktion.id,
            beleg_id=k.beleg.id,
            stufe=k.stufe.value,
            status=status,
            confidence=k.confidence,
            begruendung=k.begruendung,
            differenz=k.differenz,
        ),
    )


def gleiche_belege_ab(
    session: Session, zeitraum: str | None = None
) -> Abgleichsergebnis:
    """Gleicht offene Umsätze (optional eines Monats, ``JJJJ-MM``) mit Belegen ab."""
    transaktionen = [
        t
        for t in offene_transaktionen(session)
        if not zeitraum or f"{t.datum:%Y-%m}" == zeitraum
    ]
    abgelehnt = {
        (a.transaktion_id, a.beleg_id)
        for a in lade_abgleiche(session, status={AbgleichStatus.ABGELEHNT})
    }
    ergebnis = gleiche_ab(transaktionen, abgleichbare_belege(session), abgelehnt)
    for k in ergebnis.automatisch:
        _speichere(session, k, AbgleichStatus.BESTAETIGT)
    for k in ergebnis.vorschlaege:
        _speichere(session, k, AbgleichStatus.VORGESCHLAGEN)
    return ergebnis


def _vorschlag(session: Session, praefix: str) -> Belegabgleich:
    treffer = lade_abgleiche(
        session, status={AbgleichStatus.VORGESCHLAGEN}, praefix=praefix
    )
    if not treffer:
        raise AbgleichError(f"Kein Vorschlag '{praefix}'.")
    if len(treffer) > 1:
        raise AbgleichError(
            f"'{praefix}' passt auf mehrere Vorschläge — länger angeben."
        )
    return treffer[0]


def _entscheidung_ins_journal(
    session: Session, a: Belegabgleich, vorgang: str, verworfen: list[str]
) -> None:
    """Der Belegabgleich speichert keine Person — die Entscheidung eines Menschen
    steht deshalb im Journal (Person aus dem Journal-Kontext, Baustein 7)."""
    from accounti.pruefung.journal import schreibe

    schreibe(
        session,
        vorgang,
        "belegabgleich",
        str(a.id),
        nachher={
            "transaktion_id": str(a.transaktion_id),
            "beleg_id": str(a.beleg_id),
            "stufe": a.stufe,
            "verworfen": verworfen,
        },
    )


def bestaetige_abgleich(session: Session, praefix: str) -> Belegabgleich:
    """Bestätigt einen Vorschlag und verwirft die konkurrierenden."""
    a = _vorschlag(session, praefix)
    setze_abgleich_status(session, a.id, AbgleichStatus.BESTAETIGT)
    verworfen = []
    for andere in lade_abgleiche(session, status={AbgleichStatus.VORGESCHLAGEN}):
        if andere.transaktion_id == a.transaktion_id or andere.beleg_id == a.beleg_id:
            setze_abgleich_status(session, andere.id, AbgleichStatus.ABGELEHNT)
            verworfen.append(str(andere.id))
    _entscheidung_ins_journal(session, a, "abgleich_bestaetigt", verworfen)
    return a.model_copy(update={"status": AbgleichStatus.BESTAETIGT})


def lehne_abgleich_ab(session: Session, praefix: str) -> Belegabgleich:
    """Verwirft einen Vorschlag; das Paar wird nicht wieder vorgeschlagen."""
    a = _vorschlag(session, praefix)
    setze_abgleich_status(session, a.id, AbgleichStatus.ABGELEHNT)
    _entscheidung_ins_journal(session, a, "abgleich_abgelehnt", [])
    return a.model_copy(update={"status": AbgleichStatus.ABGELEHNT})


@dataclass
class OffenInDerBank:
    umsaetze_ohne_beleg: list[Transaktion] = field(default_factory=list)
    belege_ohne_umsatz: list[Beleg] = field(default_factory=list)


def offen_in_der_bank(session: Session) -> OffenInDerBank:
    """Umsätze ohne Beleg und Quittungen/sonstige Belege ohne Umsatz (Baustein 7)."""
    mit_beleg = {
        a.transaktion_id
        for a in lade_abgleiche(session, status={AbgleichStatus.BESTAETIGT})
    } | {
        z.transaktion_id
        for z in lade_zuordnungen(session, status={ZuordnungStatus.GEBUCHT})
    }
    umsatz_da = _belege_mit_umsatz(session)
    return OffenInDerBank(
        umsaetze_ohne_beleg=sorted(
            (t for t in lade_transaktionen(session) if t.id not in mit_beleg),
            key=lambda t: t.datum,
        ),
        belege_ohne_umsatz=[
            b
            for b in lade_belege(session, status={BelegStatus.ERFASST})
            if b.belegart in ABGLEICHBAR and b.brutto and b.id not in umsatz_da
        ],
    )
