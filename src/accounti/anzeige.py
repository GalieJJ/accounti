"""Deutsche Darstellung von Beträgen und Daten für Konsole, PDF und E-Mail."""

from __future__ import annotations

from datetime import date
from decimal import Decimal


def betrag_de(wert: Decimal | None) -> str:
    """``Decimal('1234.5')`` → ``1.234,50``; ``None`` → ``—``."""
    if wert is None:
        return "—"
    text = f"{wert.quantize(Decimal('0.01')):,.2f}"
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def datum_de(wert: date | None) -> str:
    return f"{wert:%d.%m.%Y}" if wert else "—"
