"""Einnahmenüberschussrechnung aus der Summen- und Saldenliste (Akzeptanz 6)."""

from datetime import date
from decimal import Decimal

import pytest

from accounti.abschluss.euer import EuerError, erstelle_euer, euer_csv
from accounti.abschluss.kontenrahmen import lade_kontenrahmen
from accounti.abschluss.salden import summen_und_salden
from tests.abschluss_hilfe import buche, datenbank

D = Decimal
SKR03 = lade_kontenrahmen("SKR03")


@pytest.fixture
def make_session(tmp_path):
    yield from datenbank(tmp_path)


@pytest.fixture
def jahr_2026(make_session):
    def b(soll, haben, betrag, schluessel=None, steuer=None, tag=date(2026, 5, 1)):
        buche(
            make_session,
            tag,
            soll,
            haben,
            betrag,
            steuer_schluessel=schluessel,
            steuer_betrag=D(steuer) if steuer else None,
        )

    b("1200", "8400", "10000", 3, "1900")
    b("1000", "8400", "100", 3, "19")
    b("1200", "8125", "2000")  # ig. Lieferung, steuerfrei
    b("4210", "1200", "1000")  # Miete
    b("4930", "1200", "100", 9, "19")
    b("4910", "1000", "24.90")
    b("4830", "0410", "1550")  # AfA
    b("1780", "1200", "500")  # USt-Vorauszahlung
    b("1200", "1780", "120")  # Erstattung
    b("4635", "1200", "50")  # Geschenke nicht abzugsfähig
    b("2200", "1200", "10")  # Körperschaftsteuer: nicht in der EÜR
    b("1800", "1200", "2000")  # Entnahme
    b("1200", "1890", "500")  # Einlage
    b("4930", "1200", "999", tag=date(2025, 5, 1))  # Vorjahr


def _euer(make_session, jahr=2026):
    with make_session() as s:
        susa = summen_und_salden(s, jahr, SKR03, "euer")
    return susa, erstelle_euer(susa, SKR03)


def test_akzeptanz_6_euer_gleich_summen_und_saldenliste(make_session, jahr_2026):
    susa, euer = _euer(make_session)
    betraege = {z.kz: z.betrag for z in [*euer.einnahmen, *euer.ausgaben]}
    assert betraege == {
        "112": D("10100"),
        "103": D("2000"),
        "140": D("1919"),
        "141": D("120"),
        "150": D("1000"),
        "229": D("124.90"),
        "185": D("19"),
        "130": D("1550"),
        "186": D("500"),
    }
    assert [(z.kz, z.betrag) for z in euer.nicht_abziehbar] == [("164", D("50"))]
    assert euer.nicht_zugeordnet == []
    # Körperschaftsteuer: weder Betriebseinnahme noch -ausgabe
    assert [(z.konten, z.betrag) for z in euer.ausserhalb] == [
        ({"2200": D("10")}, D("10"))
    ]
    assert euer.summe_einnahmen == D("14139")
    assert euer.summe_ausgaben == D("3193.90")
    assert euer.gewinn == D("10945.10")
    # Überleitung: EÜR-Gewinn minus nicht abziehbare Betriebsausgaben minus Konten
    # außerhalb der EÜR = Ergebnis der SuSa
    assert (
        euer.gewinn - euer.summe_nicht_abziehbar - euer.summe_ausserhalb
        == susa.ergebnis
        == D("10885.10")
    )
    # jede Zeile ist genau die Summe ihrer Konten aus der SuSa
    for z in [*euer.einnahmen, *euer.ausgaben, *euer.nicht_abziehbar]:
        assert z.betrag == sum(z.konten.values())
        for konto in z.konten:
            assert susa.zeile(konto) is not None
    assert (euer.entnahmen, euer.einlagen) == (D("2000"), D("500"))


def test_zeilen_je_vordruckjahr(make_session, jahr_2026):
    _, euer = _euer(make_session)
    zeilen = {z.kz: z.zeile for z in [*euer.einnahmen, *euer.ausgaben]}
    assert euer.vordruck_jahr == 2026
    assert (zeilen["112"], zeilen["130"], zeilen["185"], zeilen["150"]) == (
        15,
        34,
        58,
        40,
    )
    assert euer.summe_ausgaben_zeile == 76
    with make_session() as s:
        susa = summen_und_salden(s, 2025, SKR03, "euer")
    vorjahr = erstelle_euer(susa, SKR03)
    assert vorjahr.vordruck_jahr == 2025
    assert vorjahr.ausgaben[0].zeile == 51  # Arbeitsmittel 2025: Zeile 51
    assert vorjahr.summe_ausgaben_zeile == 75


def test_ohne_vordruck_gilt_der_juengste_aeltere(make_session):
    buche(make_session, date(2027, 2, 1), "1200", "8400", "100")
    _, euer = _euer(make_session, 2027)
    assert euer.vordruck_jahr == 2026
    assert any("2026" in h for h in euer.hinweise)


def test_nur_bei_euer(make_session):
    with make_session() as s:
        susa = summen_und_salden(s, 2026, SKR03, "bilanz")
    with pytest.raises(EuerError, match="bilanz"):
        erstelle_euer(susa, SKR03)


def test_csv(make_session, jahr_2026):
    _, euer = _euer(make_session)
    text = euer_csv(euer)
    assert "Zeile;Kennzahl;Bezeichnung;Betrag" in text
    assert "15;112;Umsatzsteuerpflichtige Betriebseinnahmen;10100,00" in text
    assert "Gewinn" in text and "10945,10" in text
    zeile = ";Nicht in der EÜR (keine Betriebseinnahme/-ausgabe);10,00;2200 10,00"
    assert zeile in text


def test_gewerbesteuer_ist_keine_betriebsausgabe(make_session):
    """§ 4 Abs. 5b EStG: Spalte „nicht abziehbar“, Kz 168 — nicht in der Summe BA."""
    for jahr in (2025, 2026):
        buche(make_session, date(jahr, 3, 1), "1210", "8400", "100")
        buche(make_session, date(jahr, 5, 15), "4320", "1210", "2000")  # Vorauszahlung
        buche(make_session, date(jahr, 6, 15), "2280", "1210", "300")  # Nachzahlung
        buche(make_session, date(jahr, 7, 15), "1210", "2282", "50")  # Erstattung
    for jahr, zeile in ((2025, 67), (2026, 68)):
        susa, euer = _euer(make_session, jahr)
        assert euer.ausgaben == [] and euer.nicht_zugeordnet == []
        assert euer.summe_ausgaben == 0
        assert euer.gewinn == D("100")
        [gewst] = euer.nicht_abziehbar
        assert (gewst.kz, gewst.zeile, gewst.betrag) == ("168", zeile, D("2250"))
        assert euer.gewinn - euer.summe_nicht_abziehbar == susa.ergebnis == D("-2150")


def test_kapitalertragsteuer_steht_ausserhalb_der_euer(make_session):
    buche(make_session, date(2026, 3, 1), "1200", "8400", "1000")
    buche(make_session, date(2026, 3, 2), "2213", "1200", "25")
    susa, euer = _euer(make_session)
    assert euer.summe_ausgaben == 0 and euer.gewinn == D("1000")
    assert [(z.konten, z.betrag) for z in euer.ausserhalb] == [
        ({"2213": D("25")}, D("25"))
    ]
    assert euer.gewinn - euer.summe_ausserhalb == susa.ergebnis == D("975")
    assert not any("ohne Zeile" in h for h in euer.hinweise)


def test_verrechnungskonten_im_ust_bereich_sind_keine_ust(make_session):
    buche(make_session, date(2026, 3, 1), "1200", "8400", "1000")
    buche(make_session, date(2026, 3, 2), "1792", "1200", "500")  # Interimskonto
    buche(make_session, date(2026, 3, 3), "1200", "1795", "300")  # § 4/3-Verbindl.
    susa, euer = _euer(make_session)
    assert euer.zeile("186") is None and euer.zeile("141") is None
    assert euer.summe_ausgaben == 0 and euer.gewinn == D("1000")
    assert susa.ergebnis == D("1000")
