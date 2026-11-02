"""Auswertungen über offene Posten: Liste, Fälligkeitsstaffel, Summen je Kontakt.

Die Liste zum Stichtag ist eine Stichtagsliste (Nachweis der Forderungen und
Verbindlichkeiten im Abschluss): Sie zeigt die Posten, die bis dahin gebucht waren, mit
ihrem Rest zum Ende des Stichtags — Zahlungen und Verrechnungen danach kommen wieder
dazu. Ist ein Beleg in Teilen an verschiedenen Tagen gebucht (Eingangsrechnung: der
§ 13b-/Erwerbsteil zum Tag der Steuerentstehung, Ausgangsrechnung: je Steuerkategorie
zum umsatzsteuerlichen Zeitpunkt), zählt der Posten bis zur letzten Teilbuchung nur
mit dem Teil, der schon auf dem Personenkonto steht. So stimmt sie mit der Saldenliste
zum selben Tag überein.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.abschluss.kontenrahmen import Kontenrahmen, lade_kontenrahmen
from accounti.abschluss.salden import bewegungen as kontobewegungen
from accounti.db.repo_opos import lade_verrechnungen
from accounti.db.repository import (
    lade_buchungen,
    lade_posten,
    lade_transaktionen,
    lade_zuordnungen,
)
from accounti.models import (
    Buchungssatz,
    OffenerPosten,
    PostenRichtung,
    PostenStatus,
    Verrechnung,
    Zahlungszuordnung,
    ZuordnungStatus,
)

NULL = Decimal("0.00")
STAFFELN = ("nicht fällig", "1–30 Tage", "31–60 Tage", "61–90 Tage", "über 90 Tage")


def ueberfaellig_tage(posten: OffenerPosten, stichtag: date) -> int:
    """Tage seit Fälligkeit; 0 oder negativ heißt: noch nicht überfällig."""
    return (stichtag - posten.faellig_am).days


def staffel_von(posten: OffenerPosten, stichtag: date) -> str:
    tage = ueberfaellig_tage(posten, stichtag)
    if tage <= 0:
        return STAFFELN[0]
    if tage <= 30:
        return STAFFELN[1]
    if tage <= 60:
        return STAFFELN[2]
    if tage <= 90:
        return STAFFELN[3]
    return STAFFELN[4]


def offene_posten(
    posten: Iterable[OffenerPosten],
    faellig_bis: date | None = None,
    richtung: PostenRichtung | None = None,
) -> list[OffenerPosten]:
    """Nicht ausgeglichene Posten, optional nur bis zu einem Fälligkeitsdatum."""
    return [
        p
        for p in posten
        if p.status is not PostenStatus.AUSGEGLICHEN
        and (faellig_bis is None or p.faellig_am <= faellig_bis)
        and (richtung is None or p.richtung is richtung)
    ]


def postenbewegungen(
    zuordnungen: Iterable[Zahlungszuordnung],
    tage: Mapping[UUID, date],
    verrechnungen: Iterable[Verrechnung],
) -> dict[UUID, list[tuple[date, Decimal]]]:
    """Je Posten (Tag, Minderung des Rests): gebuchte Zahlungen samt Skonto am Tag des
    Umsatzes (``tage``: Umsatz → Datum) und Verrechnungen — beim Gegenposten
    (Gutschrift, Guthaben) mit umgekehrtem Vorzeichen. Eine Quelle für die
    Stichtagsliste und die Abstimmung mit dem Personenkonto (``opos/abstimmung.py``)."""
    bewegungen: dict[UUID, list[tuple[date, Decimal]]] = defaultdict(list)
    for z in zuordnungen:
        if z.status is ZuordnungStatus.GEBUCHT and z.transaktion_id in tage:
            bewegungen[z.posten_id].append(
                (tage[z.transaktion_id], z.betrag + z.skonto)
            )
    for v in verrechnungen:
        bewegungen[v.posten_id].append((v.datum, v.betrag))
        bewegungen[v.gegen_posten_id].append((v.datum, -v.betrag))
    return dict(bewegungen)


def belegbuchungen(
    buchungen: Iterable[Buchungssatz], kr: Kontenrahmen
) -> dict[UUID, list[tuple[date, Decimal]]]:
    """Je Beleg seine Belegbuchungen (ohne Zahlungen): (Tag, Bewegung auf den
    Personenkonten, Soll − Haben) — mit der Steueraufteilung der Saldenliste
    (``abschluss/salden.bewegungen``: bei ausgewiesener Steuer brutto, bei § 13b und
    ig. Erwerb netto; die Umbuchung von 1548 berührt das Personenkonto nicht)."""
    ergebnis: dict[UUID, list[tuple[date, Decimal]]] = defaultdict(list)
    for b in buchungen:
        if b.beleg_id is None or b.transaktion_id is not None:
            continue
        betrag = sum(
            (
                bw.soll - bw.haben
                for bw in kontobewegungen(b, kr)
                if kr.ist_personenkonto(bw.konto) and not bw.eroeffnung
            ),
            NULL,
        )
        ergebnis[b.beleg_id].append((b.datum, betrag))
    return dict(ergebnis)


def _noch_nicht_gebucht(
    p: OffenerPosten, gebucht: list[tuple[date, Decimal]], stichtag: date
) -> Decimal:
    """Was vom Postenbetrag erst nach dem Stichtag auf das Personenkonto kommt
    (Teilbuchungen eines Belegs an verschiedenen Tagen, Nachprüfung Runde 2, OPOS M).
    Nur Teile in Richtung des Postens zählen — ein Storno nach dem Stichtag hebt die
    Buchung erst danach auf, eine Korrektur (Storno + Neubuchung) gleicht sich aus."""
    vz = -1 if p.richtung is PostenRichtung.VERBINDLICHKEIT else 1
    spaeter = vz * sum((b for tag, b in gebucht if tag > stichtag), NULL)
    if p.betrag > 0 and 0 < spaeter <= p.betrag:
        return spaeter
    if p.betrag < 0 and p.betrag <= spaeter < 0:
        return spaeter
    return NULL


def stand_zum(
    posten: Iterable[OffenerPosten],
    stichtag: date,
    bewegungen: Mapping[UUID, list[tuple[date, Decimal]]],
    belegbuchungen: Mapping[UUID, list[tuple[date, Decimal]]] | None = None,
) -> list[OffenerPosten]:
    """Posten mit ihrem Rest zum Ende des Stichtags (ohne die ausgeglichenen).

    ``bewegungen``: je Posten (Tag, Minderung des Rests) — Zahlungen samt Skonto,
    Verrechnungen (``postenbewegungen``). Was nach dem Stichtag geschah, kommt zum
    heutigen Rest wieder dazu. Ein Guthaben aus einer Überzahlung, das ältere Stände als
    Rest 0 führen (gezahlt mehr als der Betrag), zählt mit (Nachprüfung Runde 2, Neu-4:
    vorher nur in der Abstimmung).

    ``belegbuchungen`` (je Beleg, ``belegbuchungen()``): Ein Posten zählt ab seiner
    frühesten Buchung (eine Ausgangsrechnung zum Leistungsdatum, eine Eingangsrechnung
    aus einem festgeschriebenen Monat zum späteren Buchungstag), ohne Buchung ab dem
    Belegdatum; bis zur letzten Teilbuchung nur mit dem schon gebuchten Teil — so wie
    das Personenkonto in der Saldenliste.
    """
    ergebnis = []
    for p in posten:
        gemindert = sum((b for _, b in bewegungen.get(p.id, [])), NULL)
        heute = min(p.restbetrag, p.betrag - gemindert)
        gebucht = (belegbuchungen or {}).get(p.beleg_id) if p.beleg_id else None
        if gebucht:
            if min(tag for tag, _ in gebucht) > stichtag:
                continue
            ausstehend = _noch_nicht_gebucht(p, gebucht, stichtag)
        elif p.belegdatum > stichtag:
            continue
        else:
            ausstehend = NULL
        spaeter = sum(
            (b for tag, b in bewegungen.get(p.id, []) if tag > stichtag), NULL
        )
        rest = heute + spaeter - ausstehend
        if rest == 0:
            continue
        status = (
            PostenStatus.OFFEN
            if rest == p.betrag - ausstehend
            else PostenStatus.TEILBEZAHLT
        )
        ergebnis.append(p.model_copy(update={"restbetrag": rest, "status": status}))
    return ergebnis


def lade_stand_zum(
    session: Session, stichtag: date, kr: Kontenrahmen | None = None
) -> list[OffenerPosten]:
    """``stand_zum`` aus der Datenbank: Zahlungen (gebuchte Zuordnungen),
    Verrechnungen und die Belegbuchungen der Posten. Ohne ``kr`` SKR03 — der Betrag
    auf dem Personenkonto hängt nur am Steuerschlüssel (SKR03 und SKR04 kennen
    dieselben Schlüssel mit Steuerkonto bzw. Steuerpaar)."""
    tage = {t.id: t.datum for t in lade_transaktionen(session)}
    bewegungen = postenbewegungen(
        lade_zuordnungen(session, status={ZuordnungStatus.GEBUCHT}),
        tage,
        lade_verrechnungen(session),
    )
    return stand_zum(
        lade_posten(session),
        stichtag,
        bewegungen,
        belegbuchungen(lade_buchungen(session), kr or lade_kontenrahmen("SKR03")),
    )


def faelligkeitsstaffel(
    posten: Iterable[OffenerPosten], stichtag: date
) -> dict[str, Decimal]:
    """Summe der Restbeträge je Altersklasse — alle Klassen, auch leere."""
    staffel = dict.fromkeys(STAFFELN, NULL)
    for p in offene_posten(posten):
        staffel[staffel_von(p, stichtag)] += p.restbetrag
    return staffel


def summen_je_kontakt(posten: Iterable[OffenerPosten]) -> dict[UUID, Decimal]:
    summen: dict[UUID, Decimal] = defaultdict(lambda: NULL)
    for p in offene_posten(posten):
        summen[p.kontakt_id] += p.restbetrag
    return dict(summen)
