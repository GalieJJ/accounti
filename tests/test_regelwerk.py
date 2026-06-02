"""Regressionstests für das ausgelieferte Regelwerk (config/regeln.yaml)."""

from pathlib import Path

import pytest

from accounti.klassifikation.engine import RegelwerkEngine
from accounti.klassifikation.regeln_loader import lade_regeln
from accounti.models import Transaktion, TransaktionQuelle

REGELN = Path(__file__).resolve().parents[1] / "config" / "regeln.yaml"
ENGINE = RegelwerkEngine(lade_regeln(REGELN))


def _klass(zweck: str, gegenkonto: str | None = None):
    tx = Transaktion(
        datum="2026-04-10",
        betrag="-50.00",
        verwendungszweck=zweck,
        gegenkonto_name=gegenkonto,
        quelle=TransaktionQuelle.BANK,
        rohtext="x",
    )
    return ENGINE.klassifiziere(tx)


# (zweck, gegenkonto, soll, haben, steuer_schluessel)
CASES = [
    ("Gehalt April Mustermann", None, "4120", "1200", None),
    ("Beitrag", "AOK Nordwest", "4130", "1200", None),
    ("AMAZON WEB SERVICES AWS EMEA HOSTING", None, "4900", "1200", None),
    ("Rechnung 123", "IONOS SE", "4900", "1200", 9),
    ("TELEKOM MOBILFUNK APRIL", "Deutsche Telekom AG", "4920", "1200", 9),
    ("Paketmarke", "DHL Paket GmbH", "4910", "1200", 9),
    ("Briefporto", "Deutsche Post AG", "4910", "1200", None),
    ("Buromaterial Rechnung 88", "Staples Deutschland GmbH", "4930", "1200", 9),
    ("Tankquittung", "Aral", "4500", "1200", 9),
    ("Fahrkarte ICE", "Deutsche Bahn", "4600", "1200", None),
    ("Beitrag Q2", "Allianz Versicherung", "4360", "1200", None),
    ("Abschlag Strom", "Stadtwerke Hamburg", "4900", "1200", 9),
    ("Gewerbemiete Buero April", "Vermieter Immobilien GmbH", "4210", "1200", 9),
    ("Honorar", "Rechtsanwalt Schmidt", "4950", "1200", 9),
    ("Rechnung", "Steuerberater Mueller", "4955", "1200", 9),
    ("Kontofuehrungsentgelt", None, "4970", "1200", None),
    ("Rundfunkbeitrag Q2", "ARD ZDF Beitragsservice", "4900", "1200", None),
    ("Mitgliedsbeitrag", "IHK Hamburg", "4900", "1200", None),
    # Einnahmen
    ("GUTSCHRIFT", "Amazon Payments Europe S.C.A.", "1200", "8400", 3),
    ("PAYPAL GUTSCHRIFT 12345", "PayPal Europe", "1200", "8400", 3),
    ("EBAY MANAGED PAYMENTS AUSZAHLUNG", "eBay Sarl", "1200", "8400", 3),
    ("Auszahlung", "Stripe Payments", "1200", "8400", 3),
]


@pytest.mark.parametrize("zweck,gegenkonto,soll,haben,schluessel", CASES)
def test_regel_klassifiziert(zweck, gegenkonto, soll, haben, schluessel):
    erg = _klass(zweck, gegenkonto)
    assert erg is not None, f"keine Regel für {zweck!r} / {gegenkonto!r}"
    assert erg.soll_konto == soll
    assert erg.haben_konto == haben
    assert erg.steuer_schluessel == schluessel


def test_unbekannte_buchung_ohne_regel():
    assert _klass("XZ-9921 Unbekannt", "Niemand GmbH") is None
