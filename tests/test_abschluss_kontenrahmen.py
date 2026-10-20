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


@pytest.mark.parametrize(
    ("konto", "art"),
    [
        ("1788", Kontenart.BESTAND),  # Einfuhrumsatzsteuer aufgeschoben
        ("1792", Kontenart.BESTAND),  # Sonstige Verrechnungskonten (Interimskonten)
        ("1793", Kontenart.BESTAND),  # Verrechnungskonto geleistete Anzahlungen
        ("1795", Kontenart.BESTAND),  # Verbindlichkeiten soziale Sicherheit § 4/3
        ("1796", Kontenart.BESTAND),  # Ausgegebene Geschenkgutscheine
        ("1791", Kontenart.ERFOLG),  # Umsatzsteuer frühere Jahre
        ("1794", Kontenart.ERFOLG),  # USt Dreiecksgeschäft
    ],
)
def test_ust_bereich_skr03_ohne_fremde_konten(konto, art):
    assert SKR03.art(konto, "euer") is art
    assert SKR03.art(konto, "bilanz") is Kontenart.BESTAND


@pytest.mark.parametrize(
    "konto",
    ["2100", "2150", "2180", "2200", "2250", "2280", "2300", "2350", "2399"]
    + ["2500", "2550", "2580", "2600", "2650", "2680", "2700", "2750"],
)
def test_privatkonten_skr04_vollhafter_und_teilhafter(konto):
    assert SKR04.art(konto, "euer") is Kontenart.PRIVAT
    assert SKR04.art(konto, "bilanz") is Kontenart.PRIVAT


def test_steuerbereich_skr04_nur_vorsteuer():
    for konto in ("1400", "1406", "1410", "1433", "1434", "1436"):
        assert SKR04.art(konto, "euer") is Kontenart.ERFOLG, konto
    # Forderungen aus Gewerbesteuerüberzahlungen, USt-Forderungen: keine Vorsteuer
    for konto in ("1435", "1420", "1421", "1427"):
        assert SKR04.art(konto, "euer") is Kontenart.BESTAND, konto
    assert SKR04.art("2010", "euer") is Kontenart.BESTAND
    assert SKR04.art("2900", "euer") is Kontenart.BESTAND


@pytest.mark.parametrize(
    ("konto", "saldo", "kz"),
    [
        # Gewerbesteuer: keine Betriebsausgabe (§ 4 Abs. 5b EStG) → „nicht abziehbar“
        ("4320", "100", "168"),
        ("2280", "100", "168"),
        ("2281", "100", "168"),
        ("2282", "-100", "168"),  # Erstattung Vorjahre
        ("2284", "-100", "168"),
        ("4397", "100", "168"),  # nicht abzugsfähige Verspätungszuschläge
        ("4396", "100", "223"),  # abzugsfähige
        # Steuern vom Einkommen: weder Betriebseinnahme noch -ausgabe
        ("2200", "100", "-"),
        ("2208", "100", "-"),
        ("2213", "100", "-"),
        ("2285", "100", "183"),  # sonstige Steuern Vorjahre bleiben Betriebsausgabe
        ("4638", "100", "174"),  # Geschenke ausschließlich betrieblich genutzt
        ("4810", "100", "222"),  # Mietleasing bewegliche WG
        ("4805", "100", "225"),
        ("4853", "100", "138"),  # Kürzung § 7g Abs. 2
        ("4851", "100", "134"),
        ("8195", "-100", "111"),  # Kleinunternehmer
        ("8190", "-100", "104"),  # Durchschnittssätze § 24 UStG
        ("8191", "-100", "112"),
        ("8330", "-100", "112"),
        ("8340", "-100", "112"),  # Erlöse 16 % USt
        ("8338", "-100", "103"),
        ("1794", "-100", "140"),
    ],
)
def test_euer_kennzahl_skr03_einzelregeln(konto, saldo, kz):
    assert SKR03.euer_kz(konto, Decimal(saldo)) == kz


@pytest.mark.parametrize(
    ("konto", "saldo", "kz"),
    [
        ("7610", "100", "168"),  # Gewerbesteuer
        ("7640", "100", "168"),
        ("7642", "-100", "168"),
        ("7600", "100", "-"),  # Körperschaftsteuer
        ("7608", "100", "-"),  # Solidaritätszuschlag
        ("7630", "100", "-"),  # Kapitalertragsteuer
        ("7650", "100", "183"),  # sonstige Betriebssteuern
        ("7685", "100", "145"),  # Kfz-Steuer
        ("6437", "100", "168"),
        ("6436", "100", "223"),
        ("6625", "100", "174"),
        ("6243", "100", "138"),
        ("4185", "-100", "111"),
        ("4180", "-100", "104"),
    ],
)
def test_euer_kennzahl_skr04_einzelregeln(konto, saldo, kz):
    assert SKR04.euer_kz(konto, Decimal(saldo)) == kz
