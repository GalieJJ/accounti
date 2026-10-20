"""Dublettenschutz für Bankumsätze — ein Umsatz kommt genau einmal ins System.

Der Schlüssel fasst Konto, Datum, Betrag, Verwendungszweck und Gegenpartei zusammen,
plus die laufende Nummer gleicher Umsätze im selben Abruf: Zwei echte Parkgebühren
über 5 € am selben Tag bleiben zwei, derselbe Umsatz aus einem überlappenden zweiten
Abruf oder einem doppelten Import bleibt einer.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter

from accounti.models import Transaktion


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


def _basis(tx: Transaktion, konto: str) -> str:
    return "|".join(
        [
            konto,
            tx.datum.isoformat(),
            str(tx.betrag.normalize()),
            _norm(tx.verwendungszweck),
            re.sub(r"\s", "", tx.gegenkonto_iban or "").upper(),
            _norm(tx.gegenkonto_name),
        ]
    )


def mit_schluessel(transaktionen: list[Transaktion], konto: str) -> list[Transaktion]:
    """Kopien mit Dublettenschlüssel; ``konto`` ist IBAN oder Bezeichnung der Quelle."""
    gezaehlt: Counter[str] = Counter()
    ergebnis = []
    for tx in transaktionen:
        basis = _basis(tx, konto)
        gezaehlt[basis] += 1
        schluessel = hashlib.sha256(f"{basis}|{gezaehlt[basis]}".encode()).hexdigest()
        ergebnis.append(tx.model_copy(update={"dublettenschluessel": schluessel}))
    return ergebnis
