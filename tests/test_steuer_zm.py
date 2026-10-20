"""Zusammenfassende Meldung (§ 18a UStG) aus den Buchungen."""

from datetime import date
from decimal import Decimal

from accounti.models import Buchungssatz, BuchungStatus, Kontakt
from accounti.steuer.kennziffern import Kontenplan, ermittle
from accounti.steuer.zeitraum import Zeitraum
from accounti.steuer.zusammenfassende_meldung import erstelle_zm

D = Decimal
WIEN = Kontakt(
    name="Rahmen Wien", land="AT", ust_id="ATU 123 456 78", debitor_konto="10002"
)
PARIS = Kontakt(
    name="Atelier Paris", land="FR", ust_id="FR12345678901", debitor_konto="10003"
)
ATHEN = Kontakt(
    name="Galerie Athen", land="GR", ust_id="GR123456789", debitor_konto="10005"
)
OHNE = Kontakt(name="Ohne Nummer", land="NL", debitor_konto="10004")
KONTAKTE = [WIEN, PARIS, ATHEN, OHNE]


def b(soll, haben, netto, tag=date(2026, 8, 14)):
    return Buchungssatz(
        datum=tag,
        soll_konto=soll,
        haben_konto=haben,
        betrag_netto=D(netto),
        buchungstext="Test",
        status=BuchungStatus.AUTO_GEBUCHT,
    )


def zm(buchungen, zeitraum="2026-08"):
    e = ermittle(buchungen, Zeitraum.lies(zeitraum), Kontenplan(), KONTAKTE)
    return erstelle_zm(e)


def test_je_ustid_und_art_summiert_in_vollen_euro():
    m = zm(
        [
            b("10002", "8125", "3000.60"),
            b("10002", "8125", "2000.70"),
            b("8125", "10002", "20.00"),  # Minderung im selben Zeitraum
            b("10002", "8336", "300.99"),  # sonstige Leistung an denselben Kunden
            b("10003", "8125", "1000.00"),
            b("10005", "8130", "500.00"),  # Dreiecksgeschäft, Griechenland → EL
        ]
    )
    assert [(z.ust_id, z.art, z.betrag, z.name) for z in m.zeilen] == [
        ("ATU12345678", "L", D("4981"), "Rahmen Wien"),  # 4.981,30 → 4.981
        ("ATU12345678", "S", D("300"), "Rahmen Wien"),
        ("EL123456789", "D", D("500"), "Galerie Athen"),
        ("FR12345678901", "L", D("1000"), "Atelier Paris"),
    ]
    assert m.summe("L") == D("5981") and m.summe("S") == D("300")
    assert m.ohne_ustid == []


def test_csv_fuer_den_portal_import():
    m = zm([b("10002", "8125", "5000"), b("10003", "8336", "250.50")])
    assert m.als_csv() == (
        "#v3.0\n#ve3.2.1\n"
        "Umsatzsteuer-Identifikationsnummer (USt-IdNr.),Summe (Euro),Art der Leistung\n"
        "ATU12345678,5000,L\n"
        "FR12345678901,250,S\n"
    )


def test_abnehmer_ohne_ustid_und_nullsummen():
    m = zm(
        [
            b("10004", "8125", "100"),
            b("10002", "8125", "100"),
            b("8125", "10002", "100"),
        ]
    )
    assert m.zeilen == []  # Lieferung und Gutschrift heben sich auf
    assert [u.kontakt.name for u in m.ohne_ustid] == ["Ohne Nummer"]


def test_quartal_und_andere_monate():
    buchungen = [
        b("10002", "8125", "100", date(2026, 7, 1)),
        b("10002", "8125", "100", date(2026, 9, 30)),
        b("10002", "8125", "100", date(2026, 10, 1)),
    ]
    assert zm(buchungen, "2026-Q3").summe("L") == D("200")
    assert zm(buchungen, "2026-08").zeilen == []
