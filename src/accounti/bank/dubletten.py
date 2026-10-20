"""Dublettenschutz für Bankumsätze — ein Umsatz kommt genau einmal ins System.

Der Schlüssel fasst Konto, Datum, Betrag, Verwendungszweck und Gegenpartei zusammen,
plus die laufende Nummer gleicher Umsätze im selben Abruf: Zwei echte Parkgebühren
über 5 € am selben Tag bleiben zwei, derselbe Umsatz aus einem überlappenden zweiten
Abruf oder einem doppelten Import bleibt einer. Liefert die Bank eine Referenz
(camt ``AcctSvcrRef``, MT940 ``//Referenz``), gehört sie dazu — dann hängt die
Unterscheidung gleich aussehender Umsätze nicht mehr an der Reihenfolge.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter

from accounti.importers.kontoauszug import LEERE_REFERENZEN
from accounti.models import Transaktion


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


def _basis(tx: Transaktion, konto: str) -> str:
    teile = [
        konto,
        tx.datum.isoformat(),
        str(tx.betrag.normalize()),
        _norm(tx.verwendungszweck),
        re.sub(r"\s", "", tx.gegenkonto_iban or "").upper(),
        _norm(tx.gegenkonto_name),
    ]
    referenz = (tx.quelle_referenz or "").strip()
    if referenz.upper() not in LEERE_REFERENZEN:
        teile.append(f"ref:{referenz}")  # Bankreferenz, wo vorhanden
    return "|".join(teile)


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
