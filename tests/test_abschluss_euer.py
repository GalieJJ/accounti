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


def test_arbeitszimmer_abziehbar_und_nicht_abziehbar(make_session):
    """Anlage EÜR Zeile 65 (2026: 66) „abziehbar“/„nicht abziehbar“, Zeile 66 (67)
    Tagespauschale; die AfA des Arbeitszimmers gehört ebenfalls in Zeile 65. Zeilen
    2025 und 2026 nach den BMF-Vordrucken vom 29.08.2025 und 01.09.2026."""
    for jahr in (2025, 2026):
        buche(make_session, date(jahr, 3, 1), "1200", "8400", "5000")
        buche(make_session, date(jahr, 4, 1), "4288", "1200", "400")  # abziehbar
        buche(make_session, date(jahr, 4, 2), "4833", "0149", "100")  # AfA
        buche(make_session, date(jahr, 4, 3), "4289", "1200", "300")  # nicht abziehbar
        buche(make_session, date(jahr, 4, 4), "4287", "1890", "120")  # Tagespauschale
    for jahr, versatz in ((2025, 0), (2026, 1)):
        susa, euer = _euer(make_session, jahr)
        zeilen = {z.kz: (z.zeile, z.betrag) for z in euer.ausgaben}
        assert zeilen == {
            "172": (65 + versatz, D("500")),
            "163": (66 + versatz, D("120")),
        }
        [nicht] = euer.nicht_abziehbar
        assert (nicht.kz, nicht.zeile, nicht.betrag) == ("162", 65 + versatz, D("300"))
        assert euer.nicht_zugeordnet == []
        assert euer.summe_ausgaben == D("620")
        assert euer.gewinn - euer.summe_nicht_abziehbar == susa.ergebnis == D("4080")


def test_wege_wohnung_betriebsstaette(make_session):
    """Zeile 72 (2026: 73) mindert die Kfz-Kosten um die tatsächlichen Aufwendungen für
    die Wege, Zeile 73 (74) setzt die Entfernungspauschale an (DATEV-Dok. 1036862;
    Zeilen nach dem BMF-Vordruck 2026)."""
    buche(make_session, date(2026, 2, 1), "1200", "8400", "10000")
    buche(make_session, date(2026, 3, 1), "4530", "1200", "4000")  # Kfz-Kosten
    buche(make_session, date(2026, 12, 31), "4679", "4680", "4320")  # 0,03 %-Wert
    buche(make_session, date(2026, 12, 31), "4678", "4679", "2156")  # Pauschale
    susa, euer = _euer(make_session)
    zeilen = {z.kz: (z.zeile, z.betrag) for z in euer.ausgaben}
    assert zeilen == {
        "146": (71, D("4000")),
        "142": (73, D("-4320")),
        "176": (74, D("2156")),
    }
    assert euer.summe_ausgaben == D("1836")
    # der nicht abziehbare Anteil ergibt sich aus den Zeilen 73/74 und steht außerhalb
    assert [(z.konten, z.betrag) for z in euer.ausserhalb] == [
        ({"4679": D("2164")}, D("2164"))
    ]
    assert euer.gewinn - euer.summe_ausserhalb == susa.ergebnis == D("6000")
    # Zeile 73 ist ein Abzug: der negative Betrag trägt das Vorzeichen, der Text nicht
    text = euer_csv(euer)
    assert "(−)" not in text
    assert (
        "73;142;Fahrtkosten für Wege zwischen Wohnung und erster Betriebsstätte, "
        "Familienheimfahrten (pauschaliert oder tatsächlich);-4320,00;4680 -4320,00"
    ) in text


def test_oss_umsatzsteuer_und_zahlung_gleichen_sich_aus(make_session):
    """OSS: vereinnahmte USt (1767, Zeile 17) und Zahlung an andere Länder (1754,
    Zeile 58) wirken beide in der EÜR (DATEV-Posten „Umsatzsteuer“/„Neutrale
    Aufwendungen“) und heben sich im Gewinn auf."""
    buche(make_session, date(2026, 3, 1), "1200", "8320", "1000")  # OSS-Erlös
    buche(make_session, date(2026, 3, 1), "1200", "1767", "200")  # USt Frankreich
    buche(make_session, date(2026, 4, 30), "1754", "1200", "200")  # Zahlung
    susa, euer = _euer(make_session)
    betraege = {z.kz: z.betrag for z in [*euer.einnahmen, *euer.ausgaben]}
    assert betraege == {"103": D("1000"), "140": D("200"), "186": D("200")}
    assert euer.gewinn == susa.ergebnis == D("1000")


def test_paragraf_13b_blaeht_zeilen_17_18_57_nicht_auf(make_session):
    """§ 13b UStG: Umsatzsteuer und gleich hohe Vorsteuer heben sich in Zeile 57 auf
    (Anleitung zu Zeile 57: solche Rechnungen enthalten keine Vorsteuer)."""
    buche(make_session, date(2026, 3, 1), "3123", "1200", "1000")
    buche(make_session, date(2026, 3, 1), "1577", "1787", "190")
    susa, euer = _euer(make_session)
    assert euer.zeile("140") is None and euer.zeile("141") is None
    vorsteuer = euer.zeile("185")
    assert vorsteuer is not None and vorsteuer.betrag == 0
    assert euer.summe_ausgaben == D("1000")
    assert euer.gewinn == susa.ergebnis == D("-1000")


def test_ust_laufendes_jahr_gleicht_vorauszahlungen_aus(make_session):
    """DATEV-Dok. 1037179: 1789 neutralisiert die erst im Folgejahr gezahlte
    Vorauszahlung in Zeile 58 — keine Erstattung in Zeile 18."""
    buche(make_session, date(2026, 12, 31), "1780", "1704", "1000")  # § 11 Abs. 2
    buche(make_session, date(2026, 12, 31), "1780", "1789", "2000")
    _, euer = _euer(make_session)
    zahlung = euer.zeile("186")
    assert zahlung is not None and zahlung.betrag == D("1000")
    assert euer.zeile("141") is None


def test_ust_erstattung_aus_der_jahreserklaerung(make_session):
    """DATEV-Dok. 1037179 Kap. 3.2: Die Erstattung aus der Jahreserklärung wird bei
    Zahlung über 1546 (SKR03) gebucht und ist Betriebseinnahme in Zeile 18."""
    buche(make_session, date(2026, 3, 1), "1200", "8400", "1000")
    buche(make_session, date(2026, 5, 1), "1200", "1546", "900")
    susa, euer = _euer(make_session)
    erstattung = euer.zeile("141")
    assert erstattung is not None
    assert (erstattung.zeile, erstattung.betrag) == (18, D("900"))
    assert euer.gewinn == susa.ergebnis == D("1900")


def test_verbindlichkeit_ust_vorauszahlung_neutralisiert_1780(make_session):
    """1797 (KR-EÜR Posten „Umsatzsteuer-Erstattungen“): die gebuchte, noch nicht
    gezahlte Vorauszahlung ist keine Betriebsausgabe."""
    buche(make_session, date(2026, 3, 1), "1200", "8400", "1000")
    buche(make_session, date(2026, 12, 31), "1780", "1797", "300")
    susa, euer = _euer(make_session)
    zahlung = euer.zeile("186")
    assert zahlung is not None and zahlung.betrag == 0
    assert euer.zeile("141") is None
    assert euer.gewinn == susa.ergebnis == D("1000")


def test_ruecklagen_zeilen_22_und_59(make_session):
    """Bildung (Kz 190, Zeile 59/2026: 60) und Auflösung (Kz 124, Zeile 22) nach
    § 6c/§ 6b EStG, R 6.6 EStR, § 4g EStG; sonstige steuerliche Rücklagen haben keine
    Zeile und erscheinen als „nicht zugeordnet“ mit Hinweis, zählen aber mit."""
    for jahr in (2025, 2026):
        buche(make_session, date(jahr, 3, 1), "1200", "8400", "1000")
        buche(make_session, date(jahr, 12, 31), "2342", "0930", "300")  # Bildung
        buche(make_session, date(jahr, 12, 31), "0930", "2727", "100")  # Auflösung
        buche(make_session, date(jahr, 12, 31), "2345", "0940", "50")  # sonstige
    for jahr, zeile in ((2025, 59), (2026, 60)):
        susa, euer = _euer(make_session, jahr)
        assert {z.kz: (z.zeile, z.betrag) for z in euer.einnahmen} == {
            "112": (15, D("1000")),
            "124": (22, D("100")),
        }
        assert {z.kz: (z.zeile, z.betrag) for z in euer.ausgaben} == {
            "190": (zeile, D("300"))
        }
        [ohne] = euer.nicht_zugeordnet
        assert (ohne.text, ohne.konten) == ("Ausgaben", {"2345": D("50")})
        assert any("2345" in h for h in euer.hinweise)
        assert euer.summe_einnahmen == D("1100")
        assert euer.summe_ausgaben == D("350")
        assert euer.gewinn == susa.ergebnis == D("750")


def test_erloesschmaelerungen_mindern_ihre_erloeszeile(make_session):
    buche(make_session, date(2026, 3, 1), "1200", "8400", "1000")
    buche(make_session, date(2026, 3, 2), "8736", "1200", "20")  # Skonto 19 %
    buche(make_session, date(2026, 3, 3), "1200", "8125", "2000")  # ig. Lieferung
    buche(make_session, date(2026, 3, 4), "8743", "1200", "40")  # Skonto darauf
    buche(make_session, date(2026, 3, 5), "1200", "8192", "500")  # Kleinunternehmer
    buche(make_session, date(2026, 3, 6), "8707", "1200", "5")
    _, euer = _euer(make_session)
    betraege = {z.kz: z.betrag for z in euer.einnahmen}
    assert betraege == {"112": D("980"), "103": D("1960"), "111": D("495")}
    assert euer.ausgaben == []


def test_bestandsveraenderungen_sind_keine_betriebseinnahmen(make_session):
    buche(make_session, date(2026, 3, 1), "1200", "8400", "1000")
    buche(make_session, date(2026, 12, 31), "7110", "8980", "300")
    susa, euer = _euer(make_session)
    assert euer.summe_einnahmen == D("1000")
    assert [(z.konten, z.betrag) for z in euer.ausserhalb] == [
        ({"8980": D("-300")}, D("-300"))
    ]
    assert euer.gewinn - euer.summe_ausserhalb == susa.ergebnis == D("1300")


def test_skr04_wege_und_kalkulatorische_kosten(make_session):
    skr04 = lade_kontenrahmen("SKR04")
    buche(make_session, date(2026, 2, 1), "1800", "4400", "10000")
    buche(make_session, date(2026, 3, 1), "6530", "1800", "4000")
    buche(make_session, date(2026, 12, 31), "6689", "6690", "4320")
    buche(make_session, date(2026, 12, 31), "6688", "6689", "2156")
    buche(make_session, date(2026, 12, 31), "6970", "6980", "30000")  # kalkulatorisch
    with make_session() as s:
        susa = summen_und_salden(s, 2026, skr04, "euer")
    euer = erstelle_euer(susa, skr04)
    betraege = {z.kz: z.betrag for z in euer.ausgaben}
    assert betraege == {"146": D("4000"), "142": D("-4320"), "176": D("2156")}
    assert euer.nicht_zugeordnet == []
    assert euer.gewinn == D("8164")
    assert euer.gewinn - euer.summe_ausserhalb == susa.ergebnis == D("6000")


def test_hinweis_je_konto_skr03(make_session):
    """Abschreibung auf Finanzanlagen: keine Zeile — die EÜR nennt Konto und Grund
    statt nur „Zuordnung prüfen“; Konten ohne hinterlegten Hinweis bleiben allgemein."""
    buche(make_session, date(2026, 3, 1), "1200", "8400", "1000")
    buche(make_session, date(2026, 12, 31), "4870", "0525", "200")  # Teilwert
    buche(make_session, date(2026, 12, 31), "5900", "1200", "10")  # frei, ohne Hinweis
    buche(make_session, date(2026, 12, 31), "4892", "3980", "30")  # Vorräte: „-“
    susa, euer = _euer(make_session)
    [teilwert] = [h for h in euer.hinweise if "4870" in h]
    assert teilwert.startswith("Konten ohne Zeile der Anlage EÜR: 4870")
    assert "Teilwertabschreibung in der EÜR nicht zulässig – Buchung stornieren" in (
        teilwert
    )
    assert "5900" not in teilwert and "Zuordnung prüfen" not in teilwert
    [allgemein] = [h for h in euer.hinweise if "5900" in h]
    assert "Zuordnung prüfen" in allgemein
    [vorraete] = [h for h in euer.hinweise if "4892" in h]
    assert vorraete.startswith("Konto 4892: Abschreibung auf Vorräte")
    # der Gewinn bleibt wie gebucht: 4870 und 5900 zählen mit, 4892 steht außerhalb
    assert euer.summe_ausgaben == D("210")
    assert euer.gewinn - euer.summe_ausserhalb == susa.ergebnis == D("760")


def test_hinweis_je_konto_skr04(make_session):
    skr04 = lade_kontenrahmen("SKR04")
    buche(make_session, date(2026, 3, 1), "1800", "4400", "1000")
    buche(make_session, date(2026, 12, 31), "7200", "0900", "200")  # Teilwert
    buche(make_session, date(2026, 12, 31), "6249", "0520", "50")  # § 6b-Abzug
    with make_session() as s:
        susa = summen_und_salden(s, 2026, skr04, "euer")
    euer = erstelle_euer(susa, skr04)
    [teilwert] = [h for h in euer.hinweise if "7200" in h]
    assert "Teilwertabschreibung in der EÜR nicht zulässig – Buchung stornieren" in (
        teilwert
    )
    assert "Anschaffungskosten von Finanzanlagen und Wertpapieren erst bei" in teilwert
    [abzug] = [h for h in euer.hinweise if "6249" in h]
    assert abzug.startswith("Konto 6249: Abzug nach § 6c i. V. m. § 6b EStG")
    assert {z.kz: z.betrag for z in euer.ausgaben} == {"190": D("50")}
