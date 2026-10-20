"""Belegabgleich — welcher Bankumsatz gehört zu welchem Beleg?

Abgeglichen werden Belege, die direkt gegen die Bank gebucht werden (Quittungen,
sonstige Belege). Rechnungen laufen über offene Posten (Baustein 4) und haben dort
ihren Zahlungsausgleich.

Dreistufig wie überall, und streng vor großzügig — ein falscher Abgleich begründet
eine falsche Vorsteuer:

A  Referenz   Belegnummer im Verwendungszweck, Betrag exakt
B  Exakt      Betrag exakt, 0–7 Tage nach dem Beleg, Gegenpartei passt
C  Unscharf   Betrag ohne Namenstreffer, Rundungsdifferenz, Trinkgeld — Vorschlag

Automatisch wird ein A- oder B-Paar nur, wenn es auf beiden Seiten das einzige ist.
Sonst entscheidet der Mensch.
"""

from __future__ import annotations

import enum
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from accounti.kontakte.erkennung import normalisiere_name
from accounti.models import Beleg, Belegart, Belegrichtung, Transaktion

ABGLEICHBAR = frozenset({Belegart.QUITTUNG, Belegart.SONSTIGES})
MIN_REFERENZ = 5  # kürzere Belegnummern treffen zu oft zufällig
RUNDUNG = Decimal("0.05")
TRINKGELD = Decimal("0.15")  # höchstens 15 % mehr gezahlt als auf dem Beleg
MAX_VORSCHLAEGE = 3

_RUECKLASTSCHRIFT = re.compile(r"r(ü|ue)ck(lastschrift|buchung|belastung)", re.I)


class Stufe(str, enum.Enum):
    REFERENZ = "referenz"
    EXAKT = "exakt"
    UNSCHARF = "unscharf"


@dataclass(frozen=True)
class Kandidat:
    transaktion: Transaktion
    beleg: Beleg
    stufe: Stufe
    confidence: float
    begruendung: str
    differenz: Decimal  # gezahlt minus Belegbetrag, beide positiv gerechnet


@dataclass
class Abgleichsergebnis:
    automatisch: list[Kandidat] = field(default_factory=list)
    vorschlaege: list[Kandidat] = field(default_factory=list)
    ruecklastschriften: list[Transaktion] = field(default_factory=list)
    ohne_treffer: int = 0


def _alnum(text: str | None) -> str:
    return re.sub(r"[^0-9a-z]", "", (text or "").casefold())


def _woerter(text: str | None) -> set[str]:
    return {w for w in normalisiere_name(text or "").split() if len(w) >= 3}


def namens_treffer(lieferant: str | None, gegenseite: str | None) -> bool:
    """Steht mindestens die Hälfte der Lieferantenwörter auf der Bankseite?"""
    eigene = _woerter(lieferant)
    if not eigene:
        return False
    return len(eigene & _woerter(gegenseite)) * 2 >= len(eigene)


def ist_ruecklastschrift(tx: Transaktion) -> bool:
    return bool(_RUECKLASTSCHRIFT.search(tx.verwendungszweck))


def _iban(wert: str | None) -> str:
    return re.sub(r"\s", "", wert or "").upper()


def bewerte_paar(tx: Transaktion, beleg: Beleg) -> Kandidat | None:
    """Passt der Umsatz zum Beleg — und wie sicher?"""
    if not beleg.brutto:
        return None
    # Eingangsbeleg ↔ Ausgabe, Ausgangsbeleg ↔ Einnahme; Gutschrift kehrt um
    erwartet_einnahme = (beleg.richtung is Belegrichtung.AUSGANG) == (beleg.brutto > 0)
    if (tx.betrag > 0) != erwartet_einnahme or tx.betrag == 0:
        return None

    soll = abs(beleg.brutto)
    differenz = abs(tx.betrag) - soll
    belegdatum = beleg.belegdatum or beleg.eingegangen_am.date()
    tage = (tx.datum - belegdatum).days
    nummer = _alnum(beleg.belegnummer)
    referenz = len(nummer) >= MIN_REFERENZ and nummer in _alnum(tx.verwendungszweck)
    iban = bool(beleg.iban) and _iban(beleg.iban) == _iban(tx.gegenkonto_iban)
    name = namens_treffer(
        beleg.lieferant_name, f"{tx.gegenkonto_name or ''} {tx.verwendungszweck}"
    )
    partner = "IBAN" if iban else (f"Name {beleg.lieferant_name}" if name else None)
    was = beleg.belegnummer or beleg.lieferant_name or beleg.dateiname

    def kandidat(stufe: Stufe, confidence: float, grund: str) -> Kandidat:
        return Kandidat(tx, beleg, stufe, confidence, f"{was}: {grund}", differenz)

    if referenz and differenz == 0 and -5 <= tage <= 60:
        return kandidat(Stufe.REFERENZ, 1.0, "Belegnummer im Verwendungszweck")
    if differenz == 0 and 0 <= tage <= 7 and partner:
        return kandidat(Stufe.EXAKT, 0.95, f"Betrag, {tage} Tage, {partner}")
    if not -3 <= tage <= 30:
        return None
    if differenz == 0:
        grund = f"Betrag, {tage} Tage" + (f", {partner}" if partner else ", Name fehlt")
        return kandidat(Stufe.UNSCHARF, 0.75 if partner else 0.6, grund)
    if abs(differenz) <= RUNDUNG:
        return kandidat(Stufe.UNSCHARF, 0.6, f"Rundungsdifferenz {differenz} €")
    if partner and 0 < differenz <= soll * TRINKGELD:
        return kandidat(Stufe.UNSCHARF, 0.5, f"{differenz} € mehr gezahlt (Trinkgeld?)")
    return None


def gleiche_ab(
    transaktionen: list[Transaktion],
    belege: list[Beleg],
    abgelehnt: set[tuple[UUID, UUID]] | frozenset[tuple[UUID, UUID]] = frozenset(),
) -> Abgleichsergebnis:
    """Gleicht Umsätze und Belege ab; Eindeutiges automatisch, sonst Vorschläge."""
    ergebnis = Abgleichsergebnis()
    kandidaten: list[Kandidat] = []
    for tx in transaktionen:
        if ist_ruecklastschrift(tx):
            ergebnis.ruecklastschriften.append(tx)
            continue
        for beleg in belege:
            if (tx.id, beleg.id) in abgelehnt:
                continue
            k = bewerte_paar(tx, beleg)
            if k is not None:
                kandidaten.append(k)

    vergeben_tx: set[UUID] = set()
    vergeben_beleg: set[UUID] = set()

    def frei(k: Kandidat) -> bool:
        return k.transaktion.id not in vergeben_tx and k.beleg.id not in vergeben_beleg

    # erst Referenzen, dann Referenzen und exakte Treffer — jeweils nur Eindeutiges
    for stufen in ({Stufe.REFERENZ}, {Stufe.REFERENZ, Stufe.EXAKT}):
        stark = [k for k in kandidaten if k.stufe in stufen and frei(k)]
        je_tx = Counter(k.transaktion.id for k in stark)
        je_beleg = Counter(k.beleg.id for k in stark)
        for k in stark:
            if je_tx[k.transaktion.id] == 1 and je_beleg[k.beleg.id] == 1:
                ergebnis.automatisch.append(k)
                vergeben_tx.add(k.transaktion.id)
                vergeben_beleg.add(k.beleg.id)

    for tx in transaktionen:
        if tx.id in vergeben_tx or ist_ruecklastschrift(tx):
            continue
        eigene = sorted(
            (k for k in kandidaten if k.transaktion.id == tx.id and frei(k)),
            key=lambda k: -k.confidence,
        )[:MAX_VORSCHLAEGE]
        if eigene:
            ergebnis.vorschlaege.extend(eigene)
        else:
            ergebnis.ohne_treffer += 1
    return ergebnis
