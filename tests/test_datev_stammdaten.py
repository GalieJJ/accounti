"""DATEV-Stammdaten: Debitoren/Kreditoren im EXTF-Format (Akzeptanz 4, Golden-Test).

Die Golden-Datei ``examples/datev/EXTF_DebKred_Stamm_golden.csv`` ist gegen DATEVs
eigene Unterlagen geprüft: Kopf- und Überschriftenzeile wie in der DATEV-Musterdatei
``EXTF_DebKred_Stamm.csv``, Feldtypen und Längen nach der Formatbeschreibung des
DATEV-Format-Prüfprogramms (siehe Plan, Recherche). Der Test hält das Ergebnis fest.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from accounti.export.datev_felder import DEBITOREN_KREDITOREN
from accounti.export.datev_format import DatevFormatError
from accounti.export.datev_stammdaten import (
    DatevMandant,
    exportiere_stammdaten,
    lade_datev_mandant,
    stammdaten_saetze,
    wirtschaftsjahr_beginn,
)
from accounti.konfiguration import KonfigurationError
from accounti.models import Kontakt, KontaktStatus

GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "datev"
    / "EXTF_DebKred_Stamm_golden.csv"
)
MANDANT = DatevMandant(berater=29098, mandant=55003, wj_beginn=date(2026, 1, 1))
ERZEUGT = datetime(2026, 9, 1, 8, 30, 15, 123000)


def kontakte():
    return [
        Kontakt(
            id=UUID("11111111-1111-4111-8111-111111111111"),
            name="Galerie am Markt GmbH",
            strasse="Musterstraße 1",
            plz="12345",
            ort="Musterstadt",
            land="DE",
            ust_id="DE999999999",
            iban="DE89370400440532013000",
            email="rechnung@galerie-markt.example",
            debitor_konto="10001",
            zahlungsziel_tage=14,
            skonto_prozent=Decimal("2"),
            skonto_tage=7,
        ),
        Kontakt(
            id=UUID("22222222-2222-4222-8222-222222222222"),
            name="Rahmenwerk Holz OHG",
            strasse="Am Sägewerk 3",
            plz="54321",
            ort="Beispielhausen",
            steuernummer="12/345/67890",
            iban="DE02120300000000202051",
            kreditor_konto="70001",
            zahlungsziel_tage=30,
            skonto_prozent=Decimal("3"),
            skonto_tage=10,
        ),
        Kontakt(
            id=UUID("33333333-3333-4333-8333-333333333333"),
            name='Atelier "Lumière" SARL',
            strasse="12 rue de l'Exemple",
            plz="75001",
            ort="Paris",
            land="FR",
            ust_id="FR12345678901",
            iban="FR1420041010050500013M02606",
            debitor_konto="10002",
            kreditor_konto="70002",
            zahlungsziel_tage=30,
        ),
        Kontakt(
            id=UUID("44444444-4444-4444-8444-444444444444"),
            name="Neuer Lieferant KG mit einem sehr langen Firmennamen der kürzer muss",
            kreditor_konto="70003",
            status=KontaktStatus.ZUR_PRUEFUNG,
        ),
        Kontakt(name="Ohne Personenkonto e.K."),
    ]


def test_akzeptanz_4_golden(tmp_path):
    pfad, anzahl = exportiere_stammdaten(kontakte(), MANDANT, tmp_path, ERZEUGT)
    assert pfad.name == "EXTF_DebKred_Stamm_20260901.csv"
    assert anzahl == 5  # Atelier als Debitor und Kreditor
    assert pfad.read_bytes() == GOLDEN.read_bytes()


def test_golden_ist_datev_format():
    """Struktur der Golden-Datei nach den Regeln aus DATEVs Formatbeschreibung."""
    roh = GOLDEN.read_bytes()
    assert not roh.startswith(b"\xef\xbb\xbf")
    text = roh.decode("cp1252")
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    zeilen = text.split("\r\n")[:-1]
    kopf = zeilen[0].split(";")
    assert len(kopf) == 31
    assert kopf[:5] == ['"EXTF"', "700", "16", '"Debitoren/Kreditoren"', "5"]
    assert zeilen[1] == ";".join(f.name for f in DEBITOREN_KREDITOREN)
    for zeile in zeilen[2:]:
        werte = zeile.split(";")
        assert len(werte) == 254
        for wert, feld in zip(werte, DEBITOREN_KREDITOREN, strict=True):
            if feld.typ == "T":
                assert re.fullmatch(r'"(?:[^"]|"")*"', wert), (feld.name, wert)
                inhalt = wert[1:-1].replace('""', '"')
                assert len(inhalt) <= feld.laenge, (feld.name, wert)
            else:
                assert '"' not in wert, (feld.name, wert)
        assert re.fullmatch(r"\d{5}", werte[0])  # Personenkonto = Sachkontenlänge + 1
        assert werte[6] == '"2"'  # Adressattyp Unternehmen


def test_inhalt_der_saetze():
    saetze = {s[1]: s for s in stammdaten_saetze(kontakte())}
    markt = saetze["10001"]
    assert (markt[2], markt[8], markt[9], markt[10]) == (
        "Galerie am Markt GmbH",
        "Galerie am Mark",  # Kurzbezeichnung, 15 Zeichen
        "DE",
        "999999999",  # EU-UStID ohne Länderpräfix
    )
    assert (markt[45], markt[44], markt[49]) == ("DE89370400440532013000", "DE", "1")
    assert (markt[110], markt[111]) == (14, Decimal("2"))  # Fälligkeit, Skonto
    holz = saetze["70001"]
    assert (holz[112], holz[113], holz[116]) == (10, Decimal("3"), 30)
    assert holz[100] == "12/345/67890"
    # beide Rollen: zwei Sätze, gegenseitig verknüpft
    assert saetze["10002"][232] == "70002" and saetze["70002"][232] == "10002"
    assert saetze["10002"][20] == "FR"
    assert saetze["70003"][2] == "Neuer Lieferant KG mit einem sehr langen Firmennam"


def test_personenkonto_passt_nicht(tmp_path):
    falsch = Kontakt(name="X", debitor_konto="123456")
    with pytest.raises(DatevFormatError, match="Sachkontenlänge"):
        exportiere_stammdaten([falsch], MANDANT, tmp_path, ERZEUGT)


@pytest.mark.parametrize(
    ("stichtag", "beginn", "erwartet"),
    [
        (date(2026, 8, 1), None, date(2026, 1, 1)),
        (date(2027, 3, 1), date(2026, 1, 1), date(2027, 1, 1)),
        # abweichendes Wirtschaftsjahr (§ 4a EStG) ab 1. Juli
        (date(2026, 8, 1), date(2024, 7, 1), date(2026, 7, 1)),
        (date(2026, 3, 1), date(2024, 7, 1), date(2025, 7, 1)),
    ],
)
def test_wirtschaftsjahr_beginn(stichtag, beginn, erwartet):
    assert wirtschaftsjahr_beginn(stichtag, beginn) == erwartet


def test_lade_datev_mandant(tmp_path):
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        "mandant:\n  kontenrahmen: SKR04\n  sachkonten_laenge: 6\n"
        "datev:\n  berater_nummer: '29098'\n  mandanten_nummer: '00042'\n"
        "  wirtschaftsjahr_beginn: '2025-07-01'\n",
        encoding="utf-8",
    )
    m = lade_datev_mandant(konfig, date(2026, 8, 15))
    assert m == DatevMandant(29098, 42, date(2026, 7, 1), 6, "04")
    # Optionen haben Vorrang vor der Konfiguration
    assert lade_datev_mandant(konfig, date(2026, 8, 15), "1001", "7").berater == 1001


def test_lade_datev_mandant_ohne_nummern(tmp_path):
    with pytest.raises(KonfigurationError, match="Mandantennummer"):
        lade_datev_mandant(tmp_path / "fehlt.yaml", date(2026, 8, 1), "29098")
