"""Verrechnung gegenläufiger offener Posten desselben Kontakts — ohne Bankumsatz.

Eine Gutschrift oder Rechnungskorrektur (negativer Posten) und ein Guthaben aus einer
Überzahlung mindern, was der Kunde noch schuldet. Beide Posten stehen auf demselben
Personenkonto, dessen Saldo schon stimmt; offen ist nur die Zuordnung der Posten
untereinander (Kontokorrent). Die Verrechnung bucht deshalb nichts: Sie gleicht die
Posten aus und hält den Vorgang fest (Tabelle ``verrechnungen``, nur anfügen, und
Journal ``posten_verrechnet``).

Rechtlich mindert eine Gutschrift wegen Minderung (§ 441 BGB) die Forderung selbst; ein
Guthaben aus Überzahlung wird aufgerechnet (§§ 387, 389 BGB). Verrechnet werden nur
Posten derselben Richtung und desselben Kontakts — Forderung gegen Verbindlichkeit
(Aufrechnung über zwei Personenkonten) bucht accounti nicht.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from accounti.db.repo_opos import (
    finde_posten,
    lade_verrechnungen,
    speichere_verrechnung,
)
from accounti.db.repository import aktualisiere_posten, lade_zuordnungen
from accounti.db.tabellen_pruefung import sperrfehler
from accounti.models import (
    OffenerPosten,
    PostenStatus,
    Verrechnung,
    ZuordnungStatus,
)

__all__ = [
    "VerrechnungError",
    "lade_verrechnungen",
    "verrechne",
    "verrechne_posten",
]

NULL = Decimal("0")


class VerrechnungError(RuntimeError):
    """Die Posten lassen sich so nicht verrechnen."""


def verrechne(
    session: Session,
    schluessel: list[str],
    datum: date,
    person: str | None = None,
    grund: str | None = None,
) -> list[Verrechnung]:
    """Verrechnet die Posten (Belegnummer oder Anfang der ID) miteinander."""
    posten = []
    for k in schluessel:
        try:
            posten.append(finde_posten(session, k))
        except ValueError as fehler:
            raise VerrechnungError(str(fehler)) from fehler
    if len({p.id for p in posten}) != len(posten):
        msg = "Ein Posten ist doppelt angegeben."
        raise VerrechnungError(msg)
    return verrechne_posten(session, posten, datum, person, grund)


def verrechne_posten(
    session: Session,
    posten: list[OffenerPosten],
    datum: date,
    person: str | None = None,
    grund: str | None = None,
) -> list[Verrechnung]:
    """Gutschriften/Guthaben (negativer Rest) gegen offene Beträge, in der
    angegebenen Reihenfolge — so weit, wie beide Seiten reichen."""
    if len(posten) < 2:
        msg = "Verrechnen braucht mindestens zwei Posten."
        raise VerrechnungError(msg)
    for p in posten:
        if p.status is PostenStatus.AUSGEGLICHEN or p.restbetrag == 0:
            msg = f"Posten {p.belegnummer or p.id} ist schon ausgeglichen."
            raise VerrechnungError(msg)
    if len({p.kontakt_id for p in posten}) > 1:
        msg = (
            "Die Posten gehören zu verschiedenen Kontakten — verrechnet werden nur "
            "Posten desselben Kontakts"
        )
        raise VerrechnungError(msg)
    if len({p.richtung for p in posten}) > 1:
        msg = (
            "Forderung gegen Verbindlichkeit (Aufrechnung über zwei Personenkonten) "
            "bucht accounti nicht — nur Posten derselben Richtung verrechnen"
        )
        raise VerrechnungError(msg)
    offen = [p for p in posten if p.restbetrag > 0]
    gutschriften = [p for p in posten if p.restbetrag < 0]
    if not offen or not gutschriften:
        msg = (
            "Verrechnen braucht gegenläufige Posten: einen offenen Betrag und eine "
            "Gutschrift bzw. ein Guthaben (negativer Rest)"
        )
        raise VerrechnungError(msg)
    vorgeschlagen = {
        z.posten_id
        for z in lade_zuordnungen(session, status={ZuordnungStatus.VORGESCHLAGEN})
    }
    for p in posten:
        if p.id in vorgeschlagen:
            msg = (
                f"Für Posten {p.belegnummer} ist eine Zahlung vorgeschlagen — erst "
                "accounti opos bestaetigen oder ablehnen"
            )
            raise VerrechnungError(msg)
    if (fehler := sperrfehler(session.connection(), datum)) is not None:
        msg = f"Verrechnung am {datum:%d.%m.%Y}: {fehler}"
        raise VerrechnungError(msg)

    rest = {p.id: p.restbetrag for p in posten}
    ergebnis: list[Verrechnung] = []
    for g in gutschriften:
        for p in offen:
            betrag = min(rest[p.id], -rest[g.id])
            if betrag <= 0:
                continue
            rest[p.id] -= betrag
            rest[g.id] += betrag
            v = Verrechnung(
                kontakt_id=p.kontakt_id,
                posten_id=p.id,
                gegen_posten_id=g.id,
                betrag=betrag,
                datum=datum,
                person=person,
                grund=grund
                or f"{g.belegnummer or 'Gutschrift'} gegen {p.belegnummer or 'Posten'}",
            )
            speichere_verrechnung(session, v)
            ergebnis.append(v)
    for p in posten:
        if rest[p.id] != p.restbetrag:
            status = (
                PostenStatus.AUSGEGLICHEN
                if rest[p.id] == 0
                else PostenStatus.TEILBEZAHLT
            )
            aktualisiere_posten(session, p.id, rest[p.id], status)
    return ergebnis
