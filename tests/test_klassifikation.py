"""Tests für die Klassifikations-Engine."""

from decimal import Decimal
from datetime import date

from accounti.models import Transaktion, TransaktionQuelle
from accounti.klassifikation.engine import (
    KlassifikationsEngine,
    Regel,
    RegelwerkEngine,
)


def _beispiel_transaktion(**kwargs) -> Transaktion:
    """Hilfs-Funktion: erzeugt eine Beispiel-Transaktion."""
    defaults = dict(
        datum=date(2026, 4, 15),
        betrag=Decimal("-29.99"),
        verwendungszweck="AMAZON WEB SERVICES AWS EMEA",
        gegenkonto_name="Amazon Web Services EMEA",
        quelle=TransaktionQuelle.BANK,
        rohtext="test-row",
    )
    defaults.update(kwargs)
    return Transaktion(**defaults)


class TestRegelwerkEngine:
    """Tests für die regelbasierte Kontierung."""

    def test_aws_wird_erkannt(self) -> None:
        engine = RegelwerkEngine()
        t = _beispiel_transaktion(
            verwendungszweck="AMAZON WEB SERVICES AWS EMEA",
            gegenkonto_name="Amazon Web Services",
        )
        ergebnis = engine.klassifiziere(t)
        assert ergebnis is not None
        assert ergebnis.confidence == 1.0
        assert ergebnis.quelle == "regelwerk"

    def test_unbekannte_transaktion_gibt_none(self) -> None:
        engine = RegelwerkEngine()
        t = _beispiel_transaktion(
            verwendungszweck="XYZUNBEKANNT 12345",
            gegenkonto_name="Firma Unbekannt",
        )
        ergebnis = engine.klassifiziere(t)
        assert ergebnis is None

    def test_eigene_regel_hat_vorrang(self) -> None:
        eigene_regel = Regel(
            name="test_spezial",
            muster=r"SPEZIALFALL",
            soll_konto="4930",
            haben_konto="1200",
            steuer_schluessel=9,
            buchungstext="Spezialfall-Buchung",
        )
        engine = RegelwerkEngine()
        engine.regel_hinzufuegen(eigene_regel)

        t = _beispiel_transaktion(verwendungszweck="SPEZIALFALL XY")
        ergebnis = engine.klassifiziere(t)
        assert ergebnis is not None
        assert ergebnis.soll_konto == "4930"
        assert ergebnis.buchungstext == "Spezialfall-Buchung"

    def test_amazon_erloes_positiv(self) -> None:
        engine = RegelwerkEngine()
        t = _beispiel_transaktion(
            betrag=Decimal("150.00"),
            verwendungszweck="Gutschrift Amazon",
            gegenkonto_name="Amazon Payments Europe",
        )
        ergebnis = engine.klassifiziere(t)
        assert ergebnis is not None
        assert ergebnis.haben_konto == "8400"
        assert ergebnis.steuer_schluessel == 3


class TestKlassifikationsEngine:
    """Tests für den Gesamt-Orchestrator."""

    def test_regelwerk_wird_zuerst_gefragt(self) -> None:
        engine = KlassifikationsEngine()
        t = _beispiel_transaktion(
            verwendungszweck="Miete Büro April",
        )
        ergebnis = engine.klassifiziere(t)
        assert ergebnis is not None
        assert ergebnis.quelle == "regelwerk"

    def test_ohne_match_gibt_none(self) -> None:
        engine = KlassifikationsEngine()
        t = _beispiel_transaktion(
            verwendungszweck="Völlig unbekannte Buchung 999",
            gegenkonto_name="Niemand",
        )
        ergebnis = engine.klassifiziere(t)
        assert ergebnis is None
