"""Dublettenerkennung — derselbe Beleg kommt oft über mehrere Kanäle.

Drei Stufen, von sicher nach unsicher:
1. identischer Datei-Hash                         → Dublette
2. gleicher Lieferant + gleiche Belegnummer       → Dublette
3. gleicher Lieferant + Brutto + Datum im Fenster → Verdacht (Mensch entscheidet)
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from accounti.models import Beleg, Eingangsergebnis

DATUM_FENSTER = timedelta(days=3)


@dataclass(frozen=True)
class DublettenBefund:
    ergebnis: Eingangsergebnis
    beleg_id: UUID | None = None
    grund: str = ""


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def _gleicher_lieferant(a: Beleg, b: Beleg) -> bool:
    """USt-IdNr. ist eindeutig und schlägt den Namen; sonst zählt der Name."""
    if a.lieferant_ust_id and b.lieferant_ust_id:
        return _norm(a.lieferant_ust_id) == _norm(b.lieferant_ust_id)
    if a.lieferant_name and b.lieferant_name:
        return _norm(a.lieferant_name) == _norm(b.lieferant_name)
    return False


def gleiche_belegnummer(kandidat: Beleg, bestand: Iterable[Beleg]) -> Beleg | None:
    """Ein anderer Beleg desselben Lieferanten mit derselben Belegnummer (Stufe 2)."""
    if not kandidat.belegnummer:
        return None
    for b in bestand:
        if (
            b.id != kandidat.id
            and _norm(b.belegnummer) == _norm(kandidat.belegnummer)
            and _gleicher_lieferant(b, kandidat)
        ):
            return b
    return None


def pruefe_dublette(kandidat: Beleg, bestand: Iterable[Beleg]) -> DublettenBefund:
    """Prüft einen neuen Beleg gegen den Bestand; die sicherste Stufe gewinnt."""
    bestand = [b for b in bestand if b.id != kandidat.id]

    for b in bestand:
        if b.datei_hash == kandidat.datei_hash:
            return DublettenBefund(
                Eingangsergebnis.DUBLETTE, b.id, "identische Datei (Hash)"
            )

    if (gleich := gleiche_belegnummer(kandidat, bestand)) is not None:
        return DublettenBefund(
            Eingangsergebnis.DUBLETTE,
            gleich.id,
            f"Lieferant und Belegnummer {kandidat.belegnummer} bekannt",
        )

    if kandidat.brutto is not None and kandidat.belegdatum is not None:
        for b in bestand:
            if (
                b.brutto == kandidat.brutto
                and b.belegdatum is not None
                and abs(b.belegdatum - kandidat.belegdatum) <= DATUM_FENSTER
                and _gleicher_lieferant(b, kandidat)
            ):
                return DublettenBefund(
                    Eingangsergebnis.VERDACHT,
                    b.id,
                    f"gleicher Lieferant und Betrag {kandidat.brutto} "
                    f"bei Belegdatum {b.belegdatum:%d.%m.%Y}",
                )

    return DublettenBefund(Eingangsergebnis.NEU)
