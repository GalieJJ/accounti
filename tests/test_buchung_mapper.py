from decimal import Decimal

from accounti.buchung.mapper import zu_buchungssatz
from accounti.models import (
    BuchungStatus, Klassifikationsergebnis, Transaktion, TransaktionQuelle,
)


def _tx(betrag: str) -> Transaktion:
    return Transaktion(
        datum="2026-04-15", betrag=betrag, verwendungszweck="TEST",
        quelle=TransaktionQuelle.BANK, rohtext="TEST",
    )


def _erg(soll: str, haben: str, schluessel, conf: float) -> Klassifikationsergebnis:
    return Klassifikationsergebnis(
        transaktion_id="00000000-0000-0000-0000-000000000000",
        soll_konto=soll, haben_konto=haben, steuer_schluessel=schluessel,
        buchungstext="TEST", confidence=conf, begruendung="x", quelle="regelwerk",
    )


def test_vorsteuer_split_19():
    # Ausgabe 119,00 brutto, VSt 19% (Schlüssel 9) -> netto 100,00, Steuer 19,00
    tx = _tx("-119.00")
    b = zu_buchungssatz(tx, _erg("4930", "1200", 9, 1.0))
    assert b.betrag_netto == Decimal("100.00")
    assert b.steuer_betrag == Decimal("19.00")
    assert b.steuer_schluessel == 9


def test_umsatzsteuer_split_19():
    # Erlös 119,00 brutto, USt 19% (Schlüssel 3) -> netto 100,00, Steuer 19,00
    tx = _tx("119.00")
    b = zu_buchungssatz(tx, _erg("1200", "8400", 3, 1.0))
    assert b.betrag_netto == Decimal("100.00")
    assert b.steuer_betrag == Decimal("19.00")


def test_ohne_steuer():
    tx = _tx("-320.00")
    b = zu_buchungssatz(tx, _erg("4360", "1200", None, 1.0))
    assert b.betrag_netto == Decimal("320.00")
    assert b.steuer_betrag is None


def test_status_aus_confidence():
    tx = _tx("-119.00")
    hoch = zu_buchungssatz(tx, _erg("4930", "1200", 9, 0.99), auto_schwelle=0.95)
    niedrig = zu_buchungssatz(tx, _erg("4930", "1200", 9, 0.50), auto_schwelle=0.95)
    assert hoch.status is BuchungStatus.AUTO_GEBUCHT
    assert niedrig.status is BuchungStatus.ZUR_PRUEFUNG
