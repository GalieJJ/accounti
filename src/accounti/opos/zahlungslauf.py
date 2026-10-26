"""Zahlungslauf: Banktransaktionen den offenen Posten zuordnen und ausgleichen.

Eindeutige Treffer werden sofort ausgeglichen, Vorschläge warten auf Bestätigung.
Eine Transaktion, die schon kontiert, zugeordnet oder vorgeschlagen ist, wird nicht
erneut angefasst — und die Bank-Kontierung (`classify`) lässt umgekehrt alles in
Ruhe, was hier zugeordnet ist.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.repo_abschluss import lade_gesperrte_jahre
from accounti.db.repo_opos import finde_posten
from accounti.db.repository import (
    gebuchte_transaktion_ids,
    lade_abgleiche,
    lade_einen_posten,
    lade_kontakte,
    lade_posten,
    lade_transaktion,
    lade_transaktionen,
    lade_zuordnungen,
    setze_zuordnung_skonto,
    setze_zuordnungen_status,
    speichere_zuordnung,
)
from accounti.db.tabellen_pruefung import gesperrte_monate
from accounti.konfiguration import Buchhaltung
from accounti.kontakte.erkennung import finde_kontakt
from accounti.models import (
    AbgleichStatus,
    Buchungssatz,
    BuchungStatus,
    OffenerPosten,
    PostenStatus,
    Transaktion,
    Zahlungszuordnung,
    ZuordnungStatus,
)
from accounti.opos.ausgleich import gleiche_aus
from accounti.opos.zuordnung import (
    Anteil,
    Stufe,
    Zuordnungsvorschlag,
    ordne_zu,
    verteile,
)


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
    monate = gesperrte_monate(session.connection())  # Baustein 7: festgeschrieben
    return sorted(
        (
            t
            for t in lade_transaktionen(session)
            if t.id not in belegt
            and t.datum.year not in gesperrt
            and f"{t.datum:%Y-%m}" not in monate
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
    session: Session,
    praefix: str,
    einstellungen: Buchhaltung,
    von: str | None = None,
    skonto: Mapping[str, Decimal] | None = None,
) -> list[Buchungssatz]:
    """Bucht einen Vorschlag; die Buchungen gelten als vom Menschen (``von``)
    geprüft.

    ``skonto``: Belegnummer → Skonto, das der Mensch für diesen Posten anerkennt (statt
    des vorgeschlagenen) — gebucht mit anteiliger Steuerkorrektur wie jedes Skonto;
    Zahlung und Skonto dürfen den Rest des Postens nicht übersteigen.
    """
    zuordnungen = _vorschlag_zu(session, praefix)
    tx = lade_transaktion(session, zuordnungen[0].transaktion_id)
    if tx is None:
        msg = f"Transaktion {zuordnungen[0].transaktion_id} nicht gefunden."
        raise ZahlungslaufError(msg)
    offen = dict(skonto or {})
    anteile = []
    for z in zuordnungen:
        posten = lade_einen_posten(session, z.posten_id)
        abzug = z.skonto
        if posten.belegnummer is not None and posten.belegnummer in offen:
            abzug = offen.pop(posten.belegnummer)
            if abzug < 0 or z.betrag + abzug > posten.restbetrag:
                msg = (
                    f"Skonto {abzug} auf {posten.belegnummer}: Zahlung {z.betrag} plus "
                    f"Skonto übersteigt den Rest {posten.restbetrag}"
                )
                raise ZahlungslaufError(msg)
            setze_zuordnung_skonto(session, z.id, abzug)
        anteile.append(Anteil(posten, z.betrag, abzug))
    if offen:
        msg = (
            f"--skonto: {', '.join(sorted(offen))} gehört nicht zu diesem Vorschlag "
            "(accounti opos vorschlaege)"
        )
        raise ZahlungslaufError(msg)
    try:
        buchungen = gleiche_aus(
            session,
            tx,
            anteile,
            einstellungen,
            status=BuchungStatus.GEPRUEFT,
            geprueft_von=von[:50] if von else None,
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


@dataclass
class Handzuordnung:
    transaktion: Transaktion
    anteile: tuple[Anteil, ...]
    buchungen: list[Buchungssatz]
    hinweise: list[str] = field(default_factory=list)


def _offener_umsatz(session: Session, praefix: str) -> Transaktion:
    treffer = [t for t in lade_transaktionen(session) if str(t.id).startswith(praefix)]
    if not treffer:
        msg = f"Kein Bankumsatz mit der ID '{praefix}'."
        raise ZahlungslaufError(msg)
    if len(treffer) > 1:
        msg = f"'{praefix}' passt auf mehrere Bankumsätze — länger angeben."
        raise ZahlungslaufError(msg)
    (tx,) = treffer
    if lade_zuordnungen(
        session, status={ZuordnungStatus.VORGESCHLAGEN}, transaktion_praefix=str(tx.id)
    ):
        msg = (
            f"Für den Umsatz {str(tx.id)[:8]} liegt ein Zuordnungsvorschlag vor — erst "
            f"accounti opos ablehnen {str(tx.id)[:8]} (oder bestaetigen)"
        )
        raise ZahlungslaufError(msg)
    if tx.id not in {t.id for t in offene_transaktionen(session, fuer_kontierung=True)}:
        msg = (
            f"Umsatz {str(tx.id)[:8]} ist nicht offen — schon gebucht oder zugeordnet, "
            "im Belegabgleich oder in einem gesperrten Zeitraum"
        )
        raise ZahlungslaufError(msg)
    return tx


def ordne_von_hand(
    session: Session,
    praefix: str,
    posten_schluessel: list[str],
    einstellungen: Buchhaltung,
    von: str | None = None,
) -> Handzuordnung:
    """Ordnet einen Bankumsatz von Hand offenen Posten zu und gleicht sie aus.

    Gutschriften und Guthaben unter den Posten werden ganz verrechnet, der Betrag dann
    in der angegebenen Reihenfolge verteilt; ein Überschuss bleibt als Guthaben auf dem
    letzten Posten. Die Buchungen gelten als von ``von`` geprüft.
    """
    tx = _offener_umsatz(session, praefix)
    posten: list[OffenerPosten] = []
    for schluessel in posten_schluessel:
        try:
            p = finde_posten(session, schluessel)
        except ValueError as fehler:
            raise ZahlungslaufError(str(fehler)) from fehler
        if p.status is PostenStatus.AUSGEGLICHEN or p.restbetrag == 0:
            msg = f"Posten {p.belegnummer or p.id} ist schon ausgeglichen."
            raise ZahlungslaufError(msg)
        if p.id in {x.id for x in posten}:
            msg = f"Posten {p.belegnummer or p.id} ist doppelt angegeben."
            raise ZahlungslaufError(msg)
        posten.append(p)
    vorgeschlagen = {
        z.posten_id
        for z in lade_zuordnungen(session, status={ZuordnungStatus.VORGESCHLAGEN})
    }
    for p in posten:
        if p.id in vorgeschlagen:
            msg = (
                f"Für Posten {p.belegnummer} ist eine andere Zahlung vorgeschlagen — "
                "erst accounti opos bestaetigen oder ablehnen"
            )
            raise ZahlungslaufError(msg)
    try:
        anteile = verteile(tx, posten)
    except ValueError as fehler:
        raise ZahlungslaufError(str(fehler)) from fehler

    hinweise = []
    ohne = [p for p in posten if p.id not in {a.posten.id for a in anteile}]
    if ohne:
        nummern = ", ".join(p.belegnummer or "?" for p in ohne)
        hinweise.append(f"Der Betrag reicht nicht bis {nummern} — bleibt offen")
    zahler, _ = finde_kontakt(
        lade_kontakte(session), iban=tx.gegenkonto_iban, name=tx.gegenkonto_name
    )
    if zahler is not None and any(p.kontakt_id != zahler.id for p in posten):
        hinweise.append(
            f"Zahler {zahler.name} ist nicht der Kontakt aller Posten — so gewollt?"
        )
    buchungen = gleiche_aus(
        session,
        tx,
        list(anteile),
        einstellungen,
        status=BuchungStatus.GEPRUEFT,
        geprueft_von=von[:50] if von else None,
    )
    vorschlag = Zuordnungsvorschlag(
        anteile,
        Stufe.HAND,
        False,
        1.0,
        "von Hand zugeordnet" + (f" ({von})" if von else ""),
        zahler,
    )
    _speichere(session, tx, vorschlag, ZuordnungStatus.GEBUCHT)
    return Handzuordnung(tx, anteile, buchungen, hinweise)
