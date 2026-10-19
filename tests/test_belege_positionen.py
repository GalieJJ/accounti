from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from accounti.belege.extraktion import Steuerzeile
from accounti.belege.positionen import (
    ist_kreditkartenabrechnung,
    positionen_aus_steuerzeilen,
    positionen_aus_umsaetzen,
    zerlege_kreditkartenabrechnung,
)

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "belege"


def test_zwei_steuersaetze_ergeben_zwei_positionen():
    beleg_id = uuid4()
    positionen = positionen_aus_steuerzeilen(
        beleg_id,
        [
            Steuerzeile(Decimal("19"), Decimal("100.00"), Decimal("19.00")),
            Steuerzeile(Decimal("7"), Decimal("50.00"), Decimal("3.50")),
        ],
    )
    assert [(p.netto, p.steuersatz, p.steuer_betrag) for p in positionen] == [
        (Decimal("100.00"), Decimal("19"), Decimal("19.00")),
        (Decimal("50.00"), Decimal("7"), Decimal("3.50")),
    ]
    assert all(p.beleg_id == beleg_id for p in positionen)


def test_kreditkartenabrechnung_ergibt_zwoelf_positionen():
    text = (FIXTURES / "kreditkarte_12_umsaetze.txt").read_text(encoding="utf-8")
    assert ist_kreditkartenabrechnung(text)

    umsaetze = zerlege_kreditkartenabrechnung(text, abrechnungsdatum=date(2026, 3, 31))

    assert len(umsaetze) == 12
    assert umsaetze[0].datum == date(2026, 3, 2)
    assert umsaetze[0].beschreibung == "AMAZON MKTPLACE LUXEMBOURG"
    assert umsaetze[0].betrag == Decimal("-23.99")
    gutschrift = umsaetze[6]
    assert "GUTSCHRIFT" in gutschrift.beschreibung
    assert gutschrift.betrag == Decimal("23.99")
    assert sum(u.betrag for u in umsaetze) == Decimal("-698.65")

    positionen = positionen_aus_umsaetzen(uuid4(), umsaetze)
    assert len(positionen) == 12
    assert positionen[1].bezeichnung == "03.03.2026 AWS EMEA"
    assert positionen[1].netto == Decimal("-89.50")


def test_jahreswechsel_in_der_abrechnung():
    text = (
        "Kreditkartenabrechnung\n"
        "28.12. 29.12. HOTEL 100,00-\n"
        "02.01. 03.01. BAHN 50,00-\n"
    )
    umsaetze = zerlege_kreditkartenabrechnung(text, abrechnungsdatum=date(2026, 1, 15))
    assert [u.datum for u in umsaetze] == [date(2025, 12, 28), date(2026, 1, 2)]


def test_rechnung_ist_keine_kreditkartenabrechnung():
    text = (FIXTURES / "rechnung_zwei_steuersaetze.txt").read_text(encoding="utf-8")
    assert not ist_kreditkartenabrechnung(text)
