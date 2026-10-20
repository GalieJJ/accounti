"""Gemeinsame Bausteine für die Tests von Baustein 8 (Aufgaben & Rückfragen)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from accounti.models import Buchungssatz, BuchungStatus

JETZT = datetime(2026, 10, 20, 9, 0)
HEUTE = JETZT.date()


def buchung(confidence: float = 0.62, **kw: Any) -> Buchungssatz:
    werte: dict[str, Any] = {
        "datum": date(2026, 10, 14),
        "soll_konto": "4930",
        "haben_konto": "1200",
        "betrag_netto": Decimal("84.03"),
        "steuer_schluessel": 9,
        "steuer_betrag": Decimal("15.97"),
        "buchungstext": "Bürobedarf Schreibwaren Meier",
        "status": BuchungStatus.ZUR_PRUEFUNG
        if confidence < 0.95
        else BuchungStatus.AUTO_GEBUCHT,
        "confidence": confidence,
    }
    werte.update(kw)
    return Buchungssatz(**werte)
