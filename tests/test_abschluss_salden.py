"""Kontobewegungen mit Steueraufteilung und Summen- und Saldenliste."""

from datetime import date
from decimal import Decimal

import pytest

from accounti.abschluss.kontenrahmen import lade_kontenrahmen
from accounti.abschluss.salden import bewegungen, summen_und_salden
from accounti.models import Buchungssatz, BuchungStatus
from tests.abschluss_hilfe import buche, datenbank

D = Decimal
SKR03 = lade_kontenrahmen("SKR03")


@pytest.fixture
def make_session(tmp_path):
    yield from datenbank(tmp_path)


def b(soll, haben, netto, schluessel=None, steuer=None):
    return Buchungssatz(
        datum=date(2026, 3, 1),
        soll_konto=soll,
        haben_konto=haben,
        betrag_netto=D(netto),
        steuer_schluessel=schluessel,
        steuer_betrag=D(steuer) if steuer is not None else None,
        buchungstext="t",
    )


def paare(buchung):
    return sorted((x.konto, x.soll, x.haben) for x in bewegungen(buchung, SKR03))


@pytest.mark.parametrize(
    ("buchung", "erwartet"),
    [
        # Bankausgabe mit Vorsteuer (Kontierung aus Regelwerk/LLM)
        (
            b("4930", "1200", "100", 9, "19"),
            [("1200", 0, 119), ("1576", 19, 0), ("4930", 100, 0)],
        ),
        # Bankeinnahme mit Umsatzsteuer
        (
            b("1200", "8400", "1000", 3, "190"),
            [("1200", 1190, 0), ("1776", 0, 190), ("8400", 0, 1000)],
        ),
        # Eingangsrechnung auf Kreditor (OPOS)
        (
            b("4930", "70001", "100", 9, "19"),
            [("1576", 19, 0), ("4930", 100, 0), ("70001", 0, 119)],
        ),
        # Skonto erhalten: Vorsteuerkorrektur auf der Haben-Seite
        (
            b("70001", "3736", "2", 9, "0.38"),
            [("1576", 0, D("0.38")), ("3736", 0, 2), ("70001", D("2.38"), 0)],
        ),
        # Gutschrift eines Lieferanten über die Bank
        (
            b("1200", "4930", "100", 9, "19"),
            [("1200", 119, 0), ("1576", 0, 19), ("4930", 0, 100)],
        ),
        # Skonto gewährt: Umsatzsteuerkorrektur auf der Soll-Seite
        (
            b("8736", "10001", "10", 3, "1.90"),
            [("10001", 0, D("11.90")), ("1776", D("1.90"), 0), ("8736", 10, 0)],
        ),
        # ohne Steuer
        (
            b("4910", "1000", "24.90"),
            [("1000", 0, D("24.90")), ("4910", D("24.90"), 0)],
        ),
        # keine Geldseite: Schlüssel entscheidet (Vorsteuer → Soll ist netto)
        (
            b("4930", "1800", "100", 9, "19"),
            [("1576", 19, 0), ("1800", 0, 119), ("4930", 100, 0)],
        ),
        # unbekannter Schlüssel: kein Steuersplit
        (b("3425", "70001", "100", 10, None), [("3425", 100, 0), ("70001", 0, 100)]),
        # § 13b (Gesamttest): Steuer auf 1577/1787, Kreditor netto
        (
            b("4900", "70002", "800", 94, "152"),
            [("1577", 152, 0), ("1787", 0, 152), ("4900", 800, 0), ("70002", 0, 800)],
        ),
        # § 13b-Gutschrift: das Paar gedreht
        (
            b("70002", "4900", "100", 94, "19"),
            [("1577", 0, 19), ("1787", 19, 0), ("4900", 0, 100), ("70002", 100, 0)],
        ),
        # ig. Erwerb 19 %
        (
            b("3425", "70001", "500", 19, "95"),
            [("1574", 95, 0), ("1774", 0, 95), ("3425", 500, 0), ("70001", 0, 500)],
        ),
    ],
)
def test_bewegungen(buchung, erwartet):
    assert paare(buchung) == [(k, D(s), D(h)) for k, s, h in erwartet]
    summe = bewegungen(buchung, SKR03)
    assert sum(x.soll for x in summe) == sum(x.haben for x in summe)


def test_summen_und_saldenliste(make_session):
    buche(
        make_session, date(2026, 1, 1), "1200", "9000", "5000", "EB", beleg_nummer="EB"
    )
    buche(
        make_session, date(2026, 1, 1), "9000", "0880", "5000", "EB", beleg_nummer="EB"
    )
    buche(
        make_session,
        date(2026, 3, 1),
        "1200",
        "8400",
        "1000",
        steuer_schluessel=3,
        steuer_betrag=D("190"),
    )
    buche(
        make_session,
        date(2026, 4, 1),
        "4930",
        "1200",
        "100",
        steuer_schluessel=9,
        steuer_betrag=D("19"),
    )
    # nicht freigegeben: zählt nicht
    buche(
        make_session,
        date(2026, 5, 1),
        "4930",
        "1200",
        "999",
        status=BuchungStatus.ZUR_PRUEFUNG,
    )
    # anderes Jahr: zählt nicht
    buche(make_session, date(2025, 5, 1), "4930", "1200", "50")

    with make_session() as s:
        susa = summen_und_salden(s, 2026, SKR03, "euer")
    z = {x.konto: x for x in susa.zeilen}
    assert (z["1200"].eb, z["1200"].soll, z["1200"].haben, z["1200"].saldo) == (
        D("5000"),
        D("1190"),
        D("119"),
        D("6071"),
    )
    assert z["9000"].saldo == 0
    assert z["0880"].saldo == D("-5000")
    assert z["8400"].saldo == D("-1000") and z["1776"].saldo == D("-190")
    assert z["1576"].saldo == D("19") and z["4930"].saldo == D("100")
    assert z["1200"].bezeichnung == "Bank"
    assert susa.summe_soll == susa.summe_haben
    assert sum(x.saldo for x in susa.zeilen) == 0
    assert susa.saldo("1200") == D("6071") and susa.saldo("4711") == 0
    # Stichtag innerhalb des Jahres
    with make_session() as s:
        maerz = summen_und_salden(s, 2026, SKR03, "euer", bis=date(2026, 3, 31))
    assert maerz.saldo("1200") == D("6190")
    # Ergebnis: Erfolgskonten (bei EÜR inkl. Steuerkonten), Haben positiv
    assert susa.ergebnis == D("1000") + D("190") - D("100") - D("19")
    with make_session() as s:
        bilanz = summen_und_salden(s, 2026, SKR03, "bilanz")
    assert bilanz.ergebnis == D("900")


def test_13b_im_skr04_auf_1407_und_3837():
    skr04 = lade_kontenrahmen("SKR04")
    paare_skr04 = sorted(
        (x.konto, x.soll, x.haben)
        for x in bewegungen(b("6300", "70002", "800", 94, "152"), skr04)
    )
    assert paare_skr04 == [
        ("1407", D(152), D(0)),
        ("3837", D(0), D(152)),
        ("6300", D(800), D(0)),
        ("70002", D(0), D(800)),
    ]


def test_erstattung_auf_der_kreditkarte_brutto_auf_dem_kartenkonto():
    """Gesamttest Eingang B08: 1730 an 4930 mit Vorsteuer — die Karte bekommt den
    Bruttobetrag, die Vorsteuer wird gemindert (bisher Netto auf 1730)."""
    assert paare(b("1730", "4930", "20.16", 9, "3.83")) == [
        ("1576", D("0"), D("3.83")),
        ("1730", D("23.99"), D("0")),
        ("4930", D("0"), D("20.16")),
    ]


def test_eingerichtetes_bankkonto_ist_geldkonto_in_der_susa(make_session):
    from accounti.db.repository import speichere_bankkonto
    from accounti.models import Bankkonto

    with make_session() as s:
        speichere_bankkonto(
            s, Bankkonto(iban="VISA1234", bezeichnung="Visa Firma", sachkonto="1738")
        )
        s.commit()
    buche(
        make_session,
        date(2026, 3, 1),
        "1738",
        "4930",
        "20.16",
        steuer_schluessel=9,
        steuer_betrag=D("3.83"),
    )
    with make_session() as s:
        z = {x.konto: x for x in summen_und_salden(s, 2026, SKR03, "euer").zeilen}
    assert z["1738"].soll == D("23.99")
    assert z["1576"].haben == D("3.83")
