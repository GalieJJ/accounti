import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from accounti.belege.extraktion import extrahiere
from accounti.belege.llm import LLMBelegEngine, maskiere_beleg
from accounti.models import Belegart

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "belege"
TEXT = (FIXTURES / "rechnung_zwei_steuersaetze.txt").read_text(encoding="utf-8")


def _antwort(daten):
    return {"choices": [{"message": {"content": json.dumps(daten)}}]}


def test_maskierung_entfernt_personenbezug():
    maskiert = maskiere_beleg(TEXT, extrahiere(TEXT))
    for geheim in (
        "DE89 3704 0044 0532 0130 00",
        "DE123456789",
        "info@buero-mueller.example",
        "040 1234567",
        "Bürobedarf Müller GmbH",
        "RE-2026-0042",
        "100234",
    ):
        assert geheim not in maskiert, geheim
    # Beträge, Daten und Steuersätze bleiben für das Modell lesbar
    assert "172,50" in maskiert
    assert "05.03.2026" in maskiert
    assert "19 %" in maskiert


def test_antwort_wird_geparst():
    daten = {
        "belegart": "eingangsrechnung",
        "belegdatum": "2026-03-05",
        "netto": "150.00",
        "steuer": "22.50",
        "brutto": "172.50",
        "positionen": [
            {"bezeichnung": "Papier", "menge": 10, "netto": "85.00", "steuersatz": 19},
            {"bezeichnung": "Buch", "netto": "50.00", "steuersatz": 7},
        ],
        "confidence": 0.8,
        "begruendung": "Rechnung eines Bürobedarfshändlers",
    }
    with patch("accounti.belege.llm.completion", return_value=_antwort(daten)) as m:
        befund = LLMBelegEngine(model="anthropic/claude-test").lies(
            TEXT, extrahiere(TEXT)
        )
    prompt = m.call_args.kwargs["messages"][0]["content"]
    assert "DE123456789" not in prompt
    assert befund is not None
    assert befund.belegart is Belegart.EINGANGSRECHNUNG
    assert befund.belegdatum == date(2026, 3, 5)
    assert befund.brutto == Decimal("172.50")
    assert [p.bezeichnung for p in befund.positionen] == ["Papier", "Buch"]
    assert befund.positionen[0].menge == Decimal("10")
    assert befund.positionen[1].steuersatz == Decimal("7")
    assert befund.confidence == 0.8


def test_antwort_in_codeblock():
    inhalt = '```json\n{"belegart": "quittung", "confidence": 0.7}\n```'
    with patch(
        "accounti.belege.llm.completion",
        return_value={"choices": [{"message": {"content": inhalt}}]},
    ):
        befund = LLMBelegEngine().lies("x", extrahiere("x"))
    assert befund is not None
    assert befund.belegart is Belegart.QUITTUNG


def test_unbrauchbare_werte_werden_verworfen():
    daten = {"belegart": "rakete", "belegdatum": "gestern", "brutto": "viel"}
    with patch("accounti.belege.llm.completion", return_value=_antwort(daten)):
        befund = LLMBelegEngine().lies("x", extrahiere("x"))
    assert befund is not None
    assert befund.belegart is None
    assert befund.belegdatum is None
    assert befund.brutto is None


def test_fehler_gibt_none():
    with patch("accounti.belege.llm.completion", side_effect=RuntimeError):
        assert LLMBelegEngine().lies("x", extrahiere("x")) is None


def test_maskierung_ist_linear_auf_langen_folgen():
    """Mittel 2 (Nachprüfung C, Runde 4): ``_EMAIL`` setzte an jedem Zeichen eines
    langen Wortes neu an und las bis zu dessen Ende (20 000 Zeichen: 1,2 s,
    quadratisch) — eine E-Mail beginnt nur am Anfang eines Wortes."""
    from tests.test_belege_extraktion import _zeitschranke

    text = "a" * 100_000 + "\nmax.muster+beleg@post.example.com\n"
    with _zeitschranke(2):
        maskiert = maskiere_beleg(text, extrahiere("Firma\n"))
    assert "max.muster+beleg@post.example.com" not in maskiert
    assert maskiert.endswith("\n[EMAIL]\n")
