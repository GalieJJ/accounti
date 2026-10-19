"""E-Rechnung — XRechnung (UBL/CII) und ZUGFeRD/Factur-X lesen und prüfen."""

from __future__ import annotations

from accounti.erechnung.modell import ERechnungError, Profil, Rechnung
from accounti.erechnung.parser._xml import lokaler_name, parse_sicher
from accounti.erechnung.parser.cii import lies_cii
from accounti.erechnung.parser.ubl import lies_ubl

__all__ = ["ERechnungError", "Profil", "Rechnung", "lies"]


def lies(xml: bytes) -> Rechnung:
    """Liest eine E-Rechnung (CII oder UBL) in das Zwischenmodell."""
    wurzel = parse_sicher(xml)
    name = lokaler_name(wurzel)
    if name == "CrossIndustryInvoice":
        return lies_cii(wurzel)
    if name in ("Invoice", "CreditNote"):
        return lies_ubl(wurzel)
    msg = f"Unbekanntes Wurzelelement <{name}> — weder CII noch UBL"
    raise ERechnungError(msg)
