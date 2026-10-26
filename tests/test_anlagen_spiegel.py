"""Anlagenspiegel gegen eine handgerechnete Sollrechnung (Akzeptanz 2)."""

import csv
import io
from datetime import date
from decimal import Decimal

from accounti.anlagen.rechtsstand import lade_rechtsstand
from accounti.anlagen.spiegel import als_csv, anlagenspiegel
from accounti.models.anlagen import AbgangArt, AfaArt, Anlagegut

D = Decimal
STAND = lade_rechtsstand()


def gut(nr, bezeichnung, konto, kosten, datum, art=AfaArt.LINEAR, nd=None, **kw):
    return Anlagegut(
        nr=nr,
        bezeichnung=bezeichnung,
        konto=konto,
        anschaffungskosten=D(str(kosten)),
        anschaffungsdatum=datum,
        afa_art=art,
        nutzungsdauer=nd,
        **kw,
    )


BESTAND = [
    gut(1, "Büromöbel", "0420", 13000, date(2026, 1, 10), nd=13),
    gut(
        2,
        "Schreibtisch",
        "0420",
        3600,
        date(2026, 9, 15),
        nd=3,
        abgang_datum=date(2027, 5, 20),
        abgang_art=AbgangArt.VERKAUF,
    ),
    gut(3, "Regal", "0420", 2400, date(2027, 7, 1), nd=8),
    gut(4, "Drucker", "0480", 700, date(2027, 3, 1), AfaArt.GWG),
    gut(5, "Stuhl", "0485", 600, date(2026, 2, 1), AfaArt.SAMMELPOSTEN),
    gut(6, "Lampe", "0485", 900, date(2026, 6, 1), AfaArt.SAMMELPOSTEN),
    gut(7, "Kamera", "0420", 5000, date(2028, 1, 1), nd=7),  # erst 2028
    gut(
        8, "Alt", "0420", 1000, date(2020, 1, 1), nd=5, abgang_datum=date(2026, 6, 1)
    ),  # vor 2027 abgegangen
]


def _werte(z):
    return (
        z.ak_beginn,
        z.zugang,
        z.abgang,
        z.ak_ende,
        z.afa_beginn,
        z.afa_jahr,
        z.afa_abgang,
        z.afa_ende,
        z.rbw_beginn,
        z.rbw_ende,
    )


def test_akzeptanz_2_anlagenspiegel_gleich_sollrechnung():
    spiegel = anlagenspiegel(BESTAND, 2027, STAND)
    gruppen = {z.gruppe: z for z in spiegel.gruppen}
    assert list(gruppen) == ["0420", "0480", "0485/2026"]
    # 0420 von Hand: AK 13.000 + 3.600, Zugang Regal 2.400, Abgang Schreibtisch 3.600;
    # AfA Beginn 1.000 + 400, AfA 2027 1.000 + 500 (Jan–Mai) + 150 (6/96 von 2.400),
    # AfA auf Abgang 400 + 500
    assert _werte(gruppen["0420"]) == tuple(
        D(x)
        for x in (
            "16600",
            "2400",
            "3600",
            "15400",
            "1400",
            "1650",
            "900",
            "2150",
            "15200",
            "13250",
        )
    )
    assert _werte(gruppen["0480"]) == tuple(
        D(x) for x in ("0", "700", "0", "700", "0", "700", "0", "700", "0", "0")
    )
    assert _werte(gruppen["0485/2026"]) == tuple(
        D(x)
        for x in ("1500", "0", "0", "1500", "300", "300", "0", "600", "1200", "900")
    )
    assert _werte(spiegel.summe) == tuple(
        D(x)
        for x in (
            "18100",
            "3100",
            "3600",
            "17600",
            "1700",
            "2650",
            "900",
            "3450",
            "16400",
            "14150",
        )
    )
    einzeln = {z.gruppe: z for z in spiegel.einzeln}
    assert "7" not in einzeln and "8" not in einzeln
    assert einzeln["2"].rbw_ende == 0 and einzeln["2"].abgang == D("3600")
    assert einzeln["1"].rbw_ende == D("11000")


def test_restbuchwerte_schliessen_ans_vorjahr_an():
    vorjahr = anlagenspiegel(BESTAND, 2026, STAND)
    jahr = anlagenspiegel(BESTAND, 2027, STAND)
    # Abgang 8 aus 2026 steht im Spiegel 2026
    assert vorjahr.summe.abgang == D("1000")
    assert vorjahr.summe.rbw_ende == jahr.summe.rbw_beginn


def test_csv():
    text = als_csv(anlagenspiegel(BESTAND, 2027, STAND))
    zeilen = list(csv.reader(io.StringIO(text), delimiter=";"))
    assert zeilen[0][:3] == ["Gruppe", "Bezeichnung", "AK 01.01."]
    assert zeilen[-1][0] == "Summe"
    assert zeilen[-1][-1] == "14150,00"


def test_restbuchwerte_sammelposten_ohne_spaetere_zugaenge():
    """Nachprüfung F, N5: Zum Stichtag eines abweichenden WJ (30.06.2026) zählte der
    Sammelposten 2026 auch das Gut aus September 2026 mit (1.400 statt 500 €)."""
    from accounti.anlagen.spiegel import restbuchwerte

    maerz = gut(1, "Regal", "0485", "500", date(2026, 3, 1), AfaArt.SAMMELPOSTEN)
    sept = gut(2, "Tisch", "0485", "900", date(2026, 9, 1), AfaArt.SAMMELPOSTEN)
    assert restbuchwerte([maerz, sept], date(2026, 6, 30), STAND) == {
        "0485": Decimal("500")
    }
    # zum Jahresende beide, ein Fünftel abgeschrieben
    assert restbuchwerte([maerz, sept], date(2026, 12, 31), STAND) == {
        "0485": Decimal("1120")
    }
