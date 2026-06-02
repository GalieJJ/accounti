from unittest.mock import patch

from accounti.klassifikation.llm import LLMEngine, maskiere_pii
from accounti.models import Transaktion, TransaktionQuelle


def _tx() -> Transaktion:
    return Transaktion(
        datum="2026-04-10",
        betrag="-39.99",
        verwendungszweck="TELEKOM DE12345678901234567890 Kundennr 4711",
        gegenkonto_name="Deutsche Telekom AG",
        quelle=TransaktionQuelle.BANK,
        rohtext="x",
    )


def test_maskiert_iban():
    assert "DE12345678901234567890" not in maskiere_pii(_tx().verwendungszweck)


def test_llm_ergebnis_wird_geparst():
    antwort = (
        '{"soll_konto": "4920", "haben_konto": "1200", "steuer_schluessel": 9, '
        '"buchungstext": "Telefon", "confidence": 0.9, "begruendung": "Telekom"}'
    )
    with patch("accounti.klassifikation.llm.completion") as mock:
        mock.return_value = {"choices": [{"message": {"content": antwort}}]}
        erg = LLMEngine(model="anthropic/claude-test").klassifiziere(_tx())
    assert erg is not None
    assert erg.soll_konto == "4920"
    assert erg.quelle == "llm"
    assert erg.confidence == 0.9


def test_llm_fehler_gibt_none():
    with patch("accounti.klassifikation.llm.completion", side_effect=RuntimeError):
        erg = LLMEngine(model="anthropic/claude-test").klassifiziere(_tx())
    assert erg is None
