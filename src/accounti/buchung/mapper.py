"""Mappt ein Klassifikationsergebnis auf einen vollständigen Buchungssatz."""
from __future__ import annotations

from decimal import Decimal

from accounti.models import (
    BuchungStatus, Buchungssatz, Klassifikationsergebnis, Transaktion,
)
from accounti.steuer.umsatzsteuer import UStBerechner

# DATEV BU-Schlüssel -> (Steuersatz, ist_vorsteuer)
_SCHLUESSEL_SATZ: dict[int, tuple[Decimal, bool]] = {
    3: (Decimal("19"), False),   # USt 19%
    2: (Decimal("7"), False),    # USt 7%
    9: (Decimal("19"), True),    # VSt 19%
    8: (Decimal("7"), True),     # VSt 7%
}


def zu_buchungssatz(
    transaktion: Transaktion,
    ergebnis: Klassifikationsergebnis,
    auto_schwelle: float = 0.95,
) -> Buchungssatz:
    berechner = UStBerechner()
    brutto = abs(transaktion.betrag)
    schluessel = ergebnis.steuer_schluessel

    if schluessel in _SCHLUESSEL_SATZ:
        satz, _ist_vst = _SCHLUESSEL_SATZ[schluessel]
        netto = berechner.brutto_zu_netto(brutto, satz)
        steuer_betrag: Decimal | None = brutto - netto
    else:
        netto = brutto
        steuer_betrag = None

    if ergebnis.confidence >= auto_schwelle:
        status = BuchungStatus.AUTO_GEBUCHT
    else:
        status = BuchungStatus.ZUR_PRUEFUNG

    return Buchungssatz(
        transaktion_id=transaktion.id,
        datum=transaktion.datum,
        soll_konto=ergebnis.soll_konto,
        haben_konto=ergebnis.haben_konto,
        betrag_netto=netto,
        steuer_schluessel=schluessel,
        steuer_betrag=steuer_betrag,
        buchungstext=ergebnis.buchungstext,
        status=status,
        confidence=ergebnis.confidence,
    )
