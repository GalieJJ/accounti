"""Zahlungslauf: Banktransaktionen den offenen Posten zuordnen und ausgleichen.

Eindeutige Treffer werden sofort ausgeglichen, Vorschläge warten auf Bestätigung.
Eine Transaktion, die schon kontiert, zugeordnet oder vorgeschlagen ist, wird nicht
erneut angefasst — und die Bank-Kontierung (`classify`) lässt umgekehrt alles in
Ruhe, was hier zugeordnet ist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.repo_abschluss import lade_gesperrte_jahre
from accounti.db.repository import (
    gebuchte_transaktion_ids,
    lade_abgleiche,
    lade_einen_posten,
    lade_kontakte,
    lade_posten,
    lade_transaktion,
    lade_transaktionen,
    lade_zuordnungen,
    setze_zuordnungen_status,
    speichere_zuordnung,
)
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    AbgleichStatus,
    Buchungssatz,
    BuchungStatus,
    PostenStatus,
    Transaktion,
    Zahlungszuordnung,
    ZuordnungStatus,
)
from accounti.opos.ausgleich import gleiche_aus
from accounti.opos.zuordnung import Anteil, Zuordnungsvorschlag, ordne_zu


class ZahlungslaufError(RuntimeError):
    """Bestätigen oder Ablehnen ist so nicht möglich."""


@dataclass
class Zahlungslauf:
    gebucht: list[tuple[Transaktion, Zuordnungsvorschlag]] = field(default_factory=list)
    vorgeschlagen: list[tuple[Transaktion, Zuordnungsvorschlag]] = field(
        default_factory=list
    )
    ohne_treffer: int = 0


def offene_transaktionen(
    session: Session, fuer_kontierung: bool = False
) -> list[Transaktion]:
    """Transaktionen ohne Buchung, ohne (aktive) Zuordnung und ohne offenen Abgleich.

    Für die Kontierung zählen abgelehnte Vorschläge als frei; für die Zuordnung
    nicht — eine abgelehnte Zuordnung wird nicht immer wieder vorgeschlagen.
    Umsätze in abgeschlossenen Geschäftsjahren (Baustein 12) bleiben draußen: Dort
    ließe sich nichts buchen, und ein einziger solcher Umsatz bräche sonst den ganzen
    Lauf ab. ``accounti abschluss pruefen`` meldet sie.
    """
    belegt = {
        z.transaktion_id
        for z in lade_zuordnungen(session)
        if z.status is not ZuordnungStatus.ABGELEHNT or not fuer_kontierung
    }
    # Beleg-Abgleich (Baustein 5): ein offener Vorschlag hält beide fern; ein
    # bestätigter Beleg gehört zur Kontierung, nicht mehr zur Zuordnung.
    belegt |= {
        a.transaktion_id
        for a in lade_abgleiche(session)
        if a.status is AbgleichStatus.VORGESCHLAGEN
        or (a.status is AbgleichStatus.BESTAETIGT and not fuer_kontierung)
    }
    belegt |= gebuchte_transaktion_ids(session)
    gesperrt = lade_gesperrte_jahre(session)
    return sorted(
        (
            t
            for t in lade_transaktionen(session)
            if t.id not in belegt and t.datum.year not in gesperrt
        ),
        key=lambda t: t.datum,
    )


def _speichere(
    session: Session,
    tx: Transaktion,
    vorschlag: Zuordnungsvorschlag,
    status: ZuordnungStatus,
) -> None:
    for anteil in vorschlag.anteile:
        speichere_zuordnung(
            session,
            Zahlungszuordnung(
                transaktion_id=tx.id,
                posten_id=anteil.posten.id,
                betrag=anteil.betrag,
                skonto=anteil.skonto,
                stufe=vorschlag.stufe.value,
                status=status,
                confidence=vorschlag.confidence,
                begruendung=vorschlag.begruendung,
            ),
        )


def zuordne_zahlungen(
    session: Session, einstellungen: Buchhaltung, zeitraum: str | None = None
) -> Zahlungslauf:
    """Ordnet alle offenen Transaktionen zu (optional nur eines Monats, ``JJJJ-MM``)."""
    lauf = Zahlungslauf()
    kontakte = lade_kontakte(session)
    reserviert: set[UUID] = {
        z.posten_id
        for z in lade_zuordnungen(session, status={ZuordnungStatus.VORGESCHLAGEN})
    }
    for tx in offene_transaktionen(session):
        if zeitraum and f"{tx.datum:%Y-%m}" != zeitraum:
            continue
        posten = [
            p
            for p in lade_posten(
                session, status={PostenStatus.OFFEN, PostenStatus.TEILBEZAHLT}
            )
            if p.id not in reserviert
        ]
        vorschlag = ordne_zu(tx, posten, kontakte, einstellungen.skonto_karenz_tage)
        if vorschlag is None:
            lauf.ohne_treffer += 1
            continue
        if vorschlag.automatisch:
            gleiche_aus(session, tx, list(vorschlag.anteile), einstellungen)
            _speichere(session, tx, vorschlag, ZuordnungStatus.GEBUCHT)
            lauf.gebucht.append((tx, vorschlag))
        else:
            _speichere(session, tx, vorschlag, ZuordnungStatus.VORGESCHLAGEN)
            reserviert |= {a.posten.id for a in vorschlag.anteile}
            lauf.vorgeschlagen.append((tx, vorschlag))
    return lauf


def _vorschlag_zu(session: Session, praefix: str) -> list[Zahlungszuordnung]:
    zuordnungen = lade_zuordnungen(
        session, status={ZuordnungStatus.VORGESCHLAGEN}, transaktion_praefix=praefix
    )
    if not zuordnungen:
        msg = f"Kein Vorschlag zur Transaktion '{praefix}'."
        raise ZahlungslaufError(msg)
    if len({z.transaktion_id for z in zuordnungen}) > 1:
        msg = f"'{praefix}' passt auf mehrere Transaktionen — länger angeben."
        raise ZahlungslaufError(msg)
    return zuordnungen


def bestaetige(
    session: Session, praefix: str, einstellungen: Buchhaltung
) -> list[Buchungssatz]:
    """Bucht einen Vorschlag; die Buchungen gelten als vom Menschen geprüft."""
    zuordnungen = _vorschlag_zu(session, praefix)
    tx = lade_transaktion(session, zuordnungen[0].transaktion_id)
    if tx is None:
        msg = f"Transaktion {zuordnungen[0].transaktion_id} nicht gefunden."
        raise ZahlungslaufError(msg)
    anteile = [
        Anteil(lade_einen_posten(session, z.posten_id), z.betrag, z.skonto)
        for z in zuordnungen
    ]
    try:
        buchungen = gleiche_aus(
            session, tx, anteile, einstellungen, status=BuchungStatus.GEPRUEFT
        )
    except ValueError as fehler:
        raise ZahlungslaufError(f"Vorschlag veraltet: {fehler}") from fehler
    setze_zuordnungen_status(session, tx.id, ZuordnungStatus.GEBUCHT)
    return buchungen


def lehne_ab(session: Session, praefix: str) -> Transaktion | None:
    """Verwirft einen Vorschlag; die Transaktion geht zurück in die Kontierung."""
    zuordnungen = _vorschlag_zu(session, praefix)
    setze_zuordnungen_status(
        session, zuordnungen[0].transaktion_id, ZuordnungStatus.ABGELEHNT
    )
    return lade_transaktion(session, zuordnungen[0].transaktion_id)
