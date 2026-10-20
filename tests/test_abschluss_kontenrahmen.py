"""Abschlusszuordnung der Konten: Kontoart, Geldkonten, Steuerkonten, EÜR-Kennzahl."""

from decimal import Decimal

import pytest

from accounti.abschluss.kontenrahmen import (
    Kontenart,
    KontenrahmenError,
    lade_kontenrahmen,
)

SKR03 = lade_kontenrahmen("SKR03")
SKR04 = lade_kontenrahmen("SKR04")


@pytest.mark.parametrize(
    ("konto", "euer", "bilanz"),
    [
        ("0420", Kontenart.BESTAND, Kontenart.BESTAND),
        ("1200", Kontenart.BESTAND, Kontenart.BESTAND),
        ("1576", Kontenart.ERFOLG, Kontenart.BESTAND),  # Steuerkonto
        ("1780", Kontenart.ERFOLG, Kontenart.BESTAND),
        ("177720", Kontenart.ERFOLG, Kontenart.BESTAND),  # 6-stellig: OSS-USt
        ("1800", Kontenart.PRIVAT, Kontenart.PRIVAT),
        ("4930", Kontenart.ERFOLG, Kontenart.ERFOLG),
        ("3980", Kontenart.BESTAND, Kontenart.BESTAND),
        ("8400", Kontenart.ERFOLG, Kontenart.ERFOLG),
        ("9000", Kontenart.VORTRAG, Kontenart.VORTRAG),
        ("70001", Kontenart.BESTAND, Kontenart.BESTAND),  # Personenkonto
    ],
)
def test_kontoart_skr03(konto, euer, bilanz):
    assert SKR03.art(konto, "euer") is euer
    assert SKR03.art(konto, "bilanz") is bilanz


def test_kontoart_skr04():
    assert SKR04.art("6220", "euer") is Kontenart.ERFOLG
    assert SKR04.art("1406", "bilanz") is Kontenart.BESTAND
    assert SKR04.art("1406", "euer") is Kontenart.ERFOLG
    assert SKR04.art("2100", "euer") is Kontenart.PRIVAT
    assert SKR04.art("2010", "euer") is Kontenart.BESTAND


def test_geldkonten():
    for konto in ("1000", "1200", "1360", "1400", "1600", "10001", "70001"):
        assert SKR03.ist_geldkonto(konto), konto
    for konto in ("4930", "1576", "0420", "8400", "1800"):
        assert not SKR03.ist_geldkonto(konto), konto
    assert SKR04.ist_geldkonto("1800") and not SKR04.ist_geldkonto("6815")


def test_steuerkonten():
    assert [SKR03.steuerkonto(s) for s in (9, 8, 3, 2, 40, None)] == [
        "1576",
        "1571",
        "1776",
        "1771",
        None,
        None,
    ]
    assert [SKR04.steuerkonto(s) for s in (9, 8, 3, 2)] == [
        "1406",
        "1401",
        "3806",
        "3801",
    ]
    assert SKR03.ist_vorsteuer(9) and not SKR03.ist_vorsteuer(3)


@pytest.mark.parametrize(
    ("konto", "saldo", "kz"),
    [
        ("8400", "-100", "112"),
        ("8125", "-100", "103"),
        ("8820", "-100", "102"),
        ("8921", "-100", "106"),
        ("4930", "100", "229"),
        ("4830", "100", "130"),
        ("4855", "100", "132"),
        ("4862", "100", "137"),
        ("2315", "100", "135"),
        ("1576", "100", "185"),
        ("1776", "-100", "140"),
        ("1780", "100", "186"),
        ("1780", "-100", "141"),
        ("4635", "100", "164"),
        ("4806", "100", "228"),  # engste Spanne gewinnt
        ("4999", "100", "183"),
        ("2200", "100", None),
        ("0420", "100", None),
    ],
)
def test_euer_kennzahl_skr03(konto, saldo, kz):
    assert SKR03.euer_kz(konto, Decimal(saldo)) == kz


def test_euer_kennzahl_skr04():
    assert SKR04.euer_kz("4400", Decimal("-1")) == "112"
    assert SKR04.euer_kz("6220", Decimal("1")) == "130"
    assert SKR04.euer_kz("6895", Decimal("1")) == "135"
    assert SKR04.euer_kz("6805", Decimal("1")) == "280"
    assert SKR04.euer_kz("3820", Decimal("-1")) == "141"


def test_vortragskonten_und_namen():
    assert SKR03.vortragskonto("1200", (10000, 69999), (70000, 99999)) == "9000"
    assert SKR03.vortragskonto("10001", (10000, 69999), (70000, 99999)) == "9008"
    assert SKR03.vortragskonto("70001", (10000, 69999), (70000, 99999)) == "9009"
    assert SKR03.bezeichnung("0980") == "Aktive Rechnungsabgrenzung"
    assert SKR03.bezeichnung("4711") == ""


def test_eigene_zuordnung_und_unbekannter_kontenrahmen(tmp_path):
    datei = tmp_path / "zuordnung.yaml"
    datei.write_text(
        "name: eigen\narten:\n  - {von: '0000', bis: '9999', art: erfolg}\n"
        "euer:\n  - {von: '4000', bis: '4999', kz: '183'}\n",
        encoding="utf-8",
    )
    eigen = lade_kontenrahmen("SKR03", datei)
    assert eigen.art("0420", "euer") is Kontenart.ERFOLG
    assert eigen.euer_kz("4930", Decimal("1")) == "183"
    with pytest.raises(KontenrahmenError, match="SKR99"):
        lade_kontenrahmen("SKR99")
