from accounti.klassifikation.engine import Regel
from accounti.models import Transaktion, TransaktionQuelle


def _tx(zweck: str, gegenkonto: str | None) -> Transaktion:
    return Transaktion(
        datum="2026-04-10",
        betrag="-50.00",
        verwendungszweck=zweck,
        gegenkonto_name=gegenkonto,
        quelle=TransaktionQuelle.BANK,
        rohtext="x",
    )


def _regel() -> Regel:
    return Regel(
        name="telekom",
        muster=r"telekom",
        soll_konto="4920",
        haben_konto="1200",
        steuer_schluessel=9,
        feld="beide",
    )


def test_beide_trifft_im_verwendungszweck():
    assert _regel().passt(_tx("TELEKOM RECHNUNG", None)) is True


def test_beide_trifft_im_gegenkonto():
    assert _regel().passt(_tx("Lastschrift 4711", "Deutsche Telekom AG")) is True


def test_beide_kein_treffer():
    assert _regel().passt(_tx("Stadtwerke Strom", "Stadtwerke")) is False
