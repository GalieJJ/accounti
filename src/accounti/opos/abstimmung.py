"""Abstimmung Personenkonto ↔ offene Posten (Hauptbuch = Nebenbuch).

Der Saldo eines Kreditoren- bzw. Debitorenkontos muss der Summe seiner offenen Posten
entsprechen: Beide entstehen aus demselben Beleg (Rechnungsbuchung und Posten) und
mindern sich durch denselben Ausgleich (Zahlung, Skonto). Weichen sie ab, ist eine
Seite falsch — z. B. eine Rechnung netto gebucht, der Posten aber brutto (GoBD
Rz. 58 ff., Richtigkeit; § 239 Abs. 2 HGB). Gerechnet wird zum Stichtag:

* Saldo: alle Bewegungen des Personenkontos bis zum Stichtag (mit Steueraufteilung wie
  in der Saldenliste), Vorschläge eingeschlossen — der Posten entsteht beim Verbuchen,
  nicht erst bei der Freigabe; ohne Eröffnungsbuchungen (der Saldovortrag wiederholt
  nur, was die Bewegungen der Vorjahre schon enthalten).
* Posten: die Stichtagsliste (``opos/auswertung.py``, ``stand_zum``) — Rest jedes
  Postens, dessen Rechnung bis zum Stichtag gebucht ist, zuzüglich der gebuchten
  Zuordnungen (Zahlung und Skonto) und der Verrechnungen (Gutschrift mit Bezug,
  ``opos verrechnen``) nach dem Stichtag. Ein Guthaben aus einer Überzahlung, das ältere
  Stände als Rest 0 führen (gezahlt mehr als der Betrag), zählt mit.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from accounti.abschluss.kontenrahmen import Kontenrahmen
from accounti.abschluss.salden import bewegungen
from accounti.models import (
    Buchungssatz,
    Kontakt,
    OffenerPosten,
    PostenRichtung,
    Transaktion,
    Verrechnung,
    Zahlungszuordnung,
)
from accounti.opos.auswertung import gebucht_ab, postenbewegungen, stand_zum

NULL = Decimal("0")


@dataclass(frozen=True)
class Abweichung:
    konto: str
    kontakt: Kontakt
    saldo: Decimal  # Verbindlichkeit bzw. Forderung laut Hauptbuch
    posten: Decimal  # dasselbe laut offenen Posten

    @property
    def differenz(self) -> Decimal:
        return self.saldo - self.posten


def _personenkonto(k: Kontakt, richtung: PostenRichtung) -> str | None:
    """Wie ``opos.ausgleich``: Konto der Rolle, sonst das einzige des Kontakts."""
    if richtung is PostenRichtung.VERBINDLICHKEIT:
        return k.kreditor_konto or k.debitor_konto
    return k.debitor_konto or k.kreditor_konto


def abweichungen(
    stichtag: date,
    kr: Kontenrahmen,
    buchungen: Iterable[Buchungssatz],
    posten: Iterable[OffenerPosten],
    kontakte: Mapping[UUID, Kontakt],
    zuordnungen: Iterable[Zahlungszuordnung],
    transaktionen: Mapping[UUID, Transaktion],
    verrechnungen: Iterable[Verrechnung],
) -> list[Abweichung]:
    """Personenkonten, deren Saldo nicht der Summe ihrer offenen Posten entspricht."""
    buchungen = list(buchungen)
    personenkonten: dict[str, Kontakt] = {}
    for k in kontakte.values():
        for konto in (k.kreditor_konto, k.debitor_konto):
            if konto:
                personenkonten[konto] = k
    kreditoren = {k.kreditor_konto for k in kontakte.values() if k.kreditor_konto}

    saldo: dict[str, Decimal] = defaultdict(lambda: NULL)
    for b in buchungen:
        if b.datum > stichtag:
            continue
        for bw in bewegungen(b, kr):
            if bw.konto in personenkonten and not bw.eroeffnung:
                saldo[bw.konto] += bw.soll - bw.haben

    minderungen = postenbewegungen(
        zuordnungen, {i: t.datum for i, t in transaktionen.items()}, verrechnungen
    )
    heute = []
    for p in posten:
        # heute offen: der Rest — ältere Stände führen ein Guthaben aus einer
        # Überzahlung als Rest 0 (gezahlt mehr als der Betrag)
        gemindert = sum((b for _, b in minderungen.get(p.id, [])), NULL)
        rest = min(p.restbetrag, p.betrag - gemindert)
        heute.append(p.model_copy(update={"restbetrag": rest}))

    stand: dict[str, Decimal] = defaultdict(lambda: NULL)
    for p in stand_zum(heute, stichtag, minderungen, gebucht_ab(buchungen)):
        kontakt = kontakte.get(p.kontakt_id)
        konto = _personenkonto(kontakt, p.richtung) if kontakt is not None else None
        if konto is None:
            continue
        # eine Forderung auf einem Kreditorenkonto (Erstattung) mindert die
        # Verbindlichkeit — und umgekehrt
        verbindlichkeit = p.richtung is PostenRichtung.VERBINDLICHKEIT
        vz = 1 if verbindlichkeit == (konto in kreditoren) else -1
        stand[konto] += vz * p.restbetrag

    ergebnis = []
    for konto in sorted(set(saldo) | set(stand)):
        # Kreditor: Haben-Saldo ist die Verbindlichkeit; Debitor: Soll-Saldo
        hauptbuch = -saldo[konto] if konto in kreditoren else saldo[konto]
        if hauptbuch != stand[konto]:
            ergebnis.append(
                Abweichung(konto, personenkonten[konto], hauptbuch, stand[konto])
            )
    return ergebnis


def befundtext(a: Abweichung, stichtag: date) -> str:
    """Befundtext für Prüfregel und Abschlussprüfung."""
    from accounti.anzeige import betrag_de, datum_de

    return (
        f"Personenkonto {a.konto} ({a.kontakt.name}) zum {datum_de(stichtag)}: Saldo "
        f"{betrag_de(a.saldo)} €, offene Posten {betrag_de(a.posten)} € — Hauptbuch "
        f"und Offene-Posten-Liste weichen um {betrag_de(a.differenz)} € ab (z. B. "
        "Rechnung netto gebucht, Posten brutto; Zahlung ohne Posten)"
    )
