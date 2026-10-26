"""Mappt ein Klassifikationsergebnis auf einen vollständigen Buchungssatz.

Schranke für jede Quelle (Regelwerk, gelernte Regel, LLM): Das Bankkonto muss auf der
Seite stehen, die das Vorzeichen des Umsatzes verlangt — Eingang (Betrag > 0) im Soll,
Ausgang im Haben. Steht es auf der falschen Seite, ist der Umsatz die Gegenrichtung
des Vorschlags (Erstattung auf eine Ausgabe, Rückbuchung auf einen Erlös): Soll und
Haben werden getauscht — dann mindert die Erstattung Aufwand und Vorsteuer (§ 17
Abs. 1 Satz 2 UStG), statt sie zu verdoppeln — und die Buchung geht unabhängig von der
Confidence zur Prüfung. Ohne Bankkonto auf einer Seite (Regel eines anderen
Kontenrahmens) ebenfalls zur Prüfung.
"""

from __future__ import annotations

from decimal import Decimal

from accounti.models import (
    Buchungssatz,
    BuchungStatus,
    Klassifikationsergebnis,
    Transaktion,
)
from accounti.steuer.umsatzsteuer import UStBerechner

# DATEV BU-Schlüssel -> (Steuersatz, ist_vorsteuer)
_SCHLUESSEL_SATZ: dict[int, tuple[Decimal, bool]] = {
    3: (Decimal("19"), False),  # USt 19%
    2: (Decimal("7"), False),  # USt 7%
    9: (Decimal("19"), True),  # VSt 19%
    8: (Decimal("7"), True),  # VSt 7%
}


def zu_buchungssatz(
    transaktion: Transaktion,
    ergebnis: Klassifikationsergebnis,
    auto_schwelle: float = 0.95,
    bank_konto: str = "1200",
) -> Buchungssatz:
    """``bank_konto``: Bankkonto der Buchhaltung; das Sachkonto des Umsatzes
    (Kreditkarte, zweites Giro, PayPal, Kasse) zählt ebenfalls als Bankseite."""
    berechner = UStBerechner()
    soll, haben = ergebnis.soll_konto, ergebnis.haben_konto
    bank = {bank_konto, transaktion.sachkonto} - {None}
    soll_bank, haben_bank = soll in bank, haben in bank
    verkehrt = (transaktion.betrag > 0 and haben_bank and not soll_bank) or (
        transaktion.betrag < 0 and soll_bank and not haben_bank
    )
    if verkehrt:
        soll, haben = haben, soll
    ohne_bank = not (soll_bank or haben_bank)
    brutto = abs(transaktion.betrag)
    schluessel = ergebnis.steuer_schluessel

    if schluessel in _SCHLUESSEL_SATZ:
        satz, _ist_vst = _SCHLUESSEL_SATZ[schluessel]
        netto = berechner.brutto_zu_netto(brutto, satz)
        steuer_betrag: Decimal | None = brutto - netto
    else:
        netto = brutto
        steuer_betrag = None

    confidence = min(ergebnis.confidence, 0.5) if verkehrt else ergebnis.confidence
    pruefen = verkehrt or ohne_bank or ergebnis.pruefen
    if confidence >= auto_schwelle and not pruefen:
        status = BuchungStatus.AUTO_GEBUCHT
    else:
        status = BuchungStatus.ZUR_PRUEFUNG

    return Buchungssatz(
        transaktion_id=transaktion.id,
        datum=transaktion.datum,
        soll_konto=soll,
        haben_konto=haben,
        betrag_netto=netto,
        steuer_schluessel=schluessel,
        steuer_betrag=steuer_betrag,
        buchungstext=ergebnis.buchungstext,
        status=status,
        confidence=confidence,
    )
