"""AfA-Plan gegen handgerechnete Reihen (Spec 6)."""

from datetime import date
from decimal import Decimal

import pytest

from accounti.anlagen.afa import (
    AfaRegelError,
    plane,
    plane_sammelposten,
    pruefe_anlage,
    schlage_art_vor,
)
from accounti.anlagen.rechtsstand import lade_rechtsstand
from accounti.models.anlagen import AfaArt, Anlagegut

D = Decimal
STAND = lade_rechtsstand()


def gut(kosten, datum, art=AfaArt.LINEAR, nd=None, **kw):
    return Anlagegut(
        bezeichnung=kw.pop("bezeichnung", "Testgut"),
        konto=kw.pop("konto", "0485" if art is AfaArt.SAMMELPOSTEN else "0420"),
        anschaffungsdatum=datum,
        anschaffungskosten=D(str(kosten)),
        nutzungsdauer=nd,
        afa_art=art,
        **kw,
    )


def reihe(plan):
    return {j.jahr: j.betrag for j in plan.jahre}


# --- linear -----------------------------------------------------------------------


def test_akzeptanz_1_september_vier_monate():
    """Akzeptanz 1: Anschaffung im September → 4/12 der Jahres-AfA."""
    plan = plane(gut(3600, date(2026, 9, 15), nd=3), STAND)
    erstes = plan.jahre[0]
    assert (erstes.jahr, erstes.monate, erstes.betrag) == (2026, 4, D("400.00"))
    assert reihe(plan) == {
        2026: D("400.00"),
        2027: D("1200.00"),
        2028: D("1200.00"),
        2029: D("800.00"),
    }
    assert plan.jahre[-1].restbuchwert == 0
    assert "4" in erstes.rechenweg and "36" in erstes.rechenweg


def test_voller_jahresverlauf_ohne_rundungsdrift():
    assert set(reihe(plane(gut(1300, date(2026, 1, 1), nd=13), STAND)).values()) == {
        D("100.00")
    }
    plan = plane(gut(1000, date(2026, 1, 20), nd=3), STAND)
    assert reihe(plan) == {2026: D("333.33"), 2027: D("333.34"), 2028: D("333.33")}
    assert sum(reihe(plan).values()) == D("1000")


def test_abgang_im_laufenden_jahr():
    g = gut(3600, date(2026, 9, 15), nd=3, abgang_datum=date(2028, 5, 10))
    plan = plane(g, STAND)
    assert reihe(plan) == {2026: D("400"), 2027: D("1200"), 2028: D("500")}
    assert plan.restbuchwert(2028, 5) == D("1500.00")
    assert plan.afa_im_jahr(2029) == 0


def test_monatskumulierte():
    plan = plane(gut(3600, date(2026, 9, 15), nd=3), STAND)
    assert plan.kumuliert_bis(2026, 8) == 0
    assert plan.kumuliert_bis(2026, 9) == D("100.00")
    assert plan.kumuliert_bis(2026, 10) == D("200.00")
    assert plan.kumuliert_bis(2027, 3) == D("700.00")
    assert plan.kumuliert_bis(2035, 12) == D("3600.00")
    assert plan.afa_im_jahr(2027, bis_monat=6) == D("600.00")
    assert plan.restbuchwert(2025, 12) == 0  # noch nicht angeschafft
    assert plan.restbuchwert(2026, 9) == D("3500.00")


# --- degressiv --------------------------------------------------------------------


def test_degressiv_30_prozent_mit_wechsel():
    """07/2025–2027: dreifach, höchstens 30 %; Wechsel, sobald linear mehr bringt."""
    plan = plane(gut(36000, date(2025, 9, 15), AfaArt.DEGRESSIV, nd=10), STAND)
    r = reihe(plan)
    assert plan.satz == D("0.3")
    assert r[2025] == D("3600.00")  # 36.000 × 30 % × 4/12
    assert r[2026] == D("9720.00")
    assert r[2027] == D("6804.00")
    assert r[2028] == D("4762.80")
    assert r[2032] == D("1143.55")  # noch degressiv (12/44 < 30 %)
    assert r[2033] == D("1000.61")  # linear: 2.668,28 × 12/32
    assert r[2034] == D("1000.60")
    assert r[2035] == D("667.07")  # Rest im letzten Monat der Nutzungsdauer
    assert sum(r.values()) == D("36000")
    assert "linear" in plan.jahre[8].rechenweg


def test_degressiv_ohne_wechsel_rest_im_letzten_jahr():
    g = gut(36000, date(2025, 9, 15), AfaArt.DEGRESSIV, nd=10, wechsel_linear=False)
    r = reihe(plane(g, STAND))
    assert r[2033] == D("800.48")  # 2.668,28 × 30 %
    assert sum(r.values()) == D("36000")
    assert max(r) == 2035


def test_degressiv_2024_zweifach_hoechstens_20():
    plan = plane(gut(10000, date(2024, 4, 1), AfaArt.DEGRESSIV, nd=8), STAND)
    assert plan.satz == D("0.2")
    assert reihe(plan)[2024] == D("1500.00")  # 10.000 × 20 % × 9/12


@pytest.mark.parametrize("tag", [date(2025, 3, 15), date(2023, 7, 1), date(2028, 1, 2)])
def test_degressiv_ausserhalb_des_fensters(tag):
    with pytest.raises(AfaRegelError, match="degressiv"):
        pruefe_anlage(gut(10000, tag, AfaArt.DEGRESSIV, nd=8), STAND)


def test_degressiv_nicht_fuer_immaterielle():
    with pytest.raises(AfaRegelError, match="beweglich"):
        pruefe_anlage(
            gut(10000, date(2026, 1, 1), AfaArt.DEGRESSIV, nd=5, immateriell=True),
            STAND,
        )


# --- GWG, Sammelposten, digital, E-Fahrzeug ---------------------------------------


@pytest.mark.parametrize(
    ("tag", "kosten", "erlaubt"),
    [
        (date(2026, 5, 1), "800.00", True),
        (date(2026, 5, 1), "800.01", False),
        (date(2015, 5, 1), "410.00", True),
        (date(2015, 5, 1), "500.00", False),  # damals 410 €
        (date(2009, 5, 1), "150.00", True),
        (date(2009, 5, 1), "400.00", False),  # damals 150 €
    ],
)
def test_gwg_grenze_am_anschaffungstag(tag, kosten, erlaubt):
    g = gut(kosten, tag, AfaArt.GWG)
    if erlaubt:
        pruefe_anlage(g, STAND)
        plan = plane(g, STAND)
        assert reihe(plan) == {tag.year: D(kosten)}
        assert plan.kumuliert_bis(tag.year, tag.month - 1) == 0
        assert plan.kumuliert_bis(tag.year, tag.month) == D(kosten)
    else:
        with pytest.raises(AfaRegelError, match="GWG"):
            pruefe_anlage(g, STAND)


def test_sammelposten_ueber_fuenf_jahre():
    a = gut("333.33", date(2026, 11, 3), AfaArt.SAMMELPOSTEN)
    b = gut("666.68", date(2026, 2, 1), AfaArt.SAMMELPOSTEN)
    c = gut("500.00", date(2025, 6, 1), AfaArt.SAMMELPOSTEN)  # anderer Jahrgang
    plan = plane_sammelposten("0485", 2026, [a, b, c], STAND)
    assert reihe(plan) == {
        2026: D("200.00"),
        2027: D("200.00"),
        2028: D("200.00"),
        2029: D("200.00"),
        2030: D("200.01"),
    }
    # Auflösung zum Ende des Wirtschaftsjahres, unabhängig vom Anschaffungsmonat
    assert plan.kumuliert_bis(2026, 11) == 0
    assert plan.kumuliert_bis(2026, 12) == D("200.00")


def test_sammelposten_abgang_mindert_nicht_ausser_im_anschaffungsjahr():
    a = gut("600", date(2026, 3, 1), AfaArt.SAMMELPOSTEN, abgang_datum=date(2027, 5, 1))
    b = gut("900", date(2026, 3, 1), AfaArt.SAMMELPOSTEN)
    plan = plane_sammelposten("0485", 2026, [a, b], STAND)
    assert sum(reihe(plan).values()) == D("1500")
    assert reihe(plan)[2027] == D("300.00")
    # im Anschaffungsjahr ausgeschieden: nicht im Sammelposten
    c = gut("400", date(2026, 3, 1), AfaArt.SAMMELPOSTEN, abgang_datum=date(2026, 8, 1))
    plan = plane_sammelposten("0485", 2026, [a, b, c], STAND)
    assert sum(reihe(plan).values()) == D("1500")
    assert reihe(plane(c, STAND)) == {}
    assert plane(c, STAND).restbuchwert(2026, 8) == D("400")


@pytest.mark.parametrize(
    ("tag", "kosten", "erlaubt"),
    [
        (date(2026, 1, 1), "250.01", True),
        (date(2026, 1, 1), "250.00", False),
        (date(2026, 1, 1), "1000.00", True),
        (date(2026, 1, 1), "1000.01", False),
        (date(2015, 1, 1), "150.01", True),
        (date(2007, 1, 1), "500.00", False),  # vor 2008 kein Sammelposten
    ],
)
def test_sammelposten_grenzen(tag, kosten, erlaubt):
    g = gut(kosten, tag, AfaArt.SAMMELPOSTEN)
    if erlaubt:
        pruefe_anlage(g, STAND)
    else:
        with pytest.raises(AfaRegelError, match="Sammelposten"):
            pruefe_anlage(g, STAND)


def test_pflicht_2008_2009():
    with pytest.raises(AfaRegelError, match="zwingend"):
        pruefe_anlage(gut(400, date(2009, 3, 1), nd=5), STAND)
    with pytest.raises(AfaRegelError, match="zwingend"):
        pruefe_anlage(gut(100, date(2009, 3, 1), nd=5), STAND)
    pruefe_anlage(gut(400, date(2009, 3, 1), AfaArt.SAMMELPOSTEN), STAND)
    pruefe_anlage(gut(2000, date(2009, 3, 1), nd=5), STAND)


def test_einheitliches_wahlrecht_im_wirtschaftsjahr():
    sp = gut(600, date(2026, 2, 1), AfaArt.SAMMELPOSTEN)
    # im Sammelposten-Jahr darf ein 700-€-Gut nicht als GWG abgezogen werden
    with pytest.raises(AfaRegelError, match="einheitlich"):
        pruefe_anlage(gut(700, date(2026, 9, 1), AfaArt.GWG), STAND, andere=[sp])
    with pytest.raises(AfaRegelError, match="einheitlich"):
        pruefe_anlage(gut(950, date(2026, 9, 1), nd=5), STAND, andere=[sp])
    # bis 250 € und über 1.000 € bleibt frei, anderes Jahr ebenso
    pruefe_anlage(gut(200, date(2026, 9, 1), AfaArt.GWG), STAND, andere=[sp])
    pruefe_anlage(gut(1200, date(2026, 9, 1), nd=5), STAND, andere=[sp])
    pruefe_anlage(gut(700, date(2027, 9, 1), AfaArt.GWG), STAND, andere=[sp])
    # umgekehrt: GWG schon gewählt, Sammelposten danach widerspricht
    gwg = gut(700, date(2026, 2, 1), AfaArt.GWG)
    with pytest.raises(AfaRegelError, match="einheitlich"):
        pruefe_anlage(gut(900, date(2026, 9, 1), AfaArt.SAMMELPOSTEN), STAND, [gwg])


def test_digital_voll_im_anschaffungsjahr():
    g = gut(1500, date(2026, 9, 15), AfaArt.DIGITAL, nd=1)
    pruefe_anlage(g, STAND)
    assert reihe(plane(g, STAND)) == {2026: D("1500")}
    with pytest.raises(AfaRegelError, match="digital"):
        pruefe_anlage(gut(1500, date(2020, 9, 15), AfaArt.DIGITAL, nd=1), STAND)


def test_e_fahrzeug_staffel():
    g = gut(50000, date(2025, 10, 15), AfaArt.E_FAHRZEUG, konto="0320")
    pruefe_anlage(g, STAND)
    assert reihe(plane(g, STAND)) == {
        2025: D("37500.00"),
        2026: D("5000.00"),
        2027: D("2500.00"),
        2028: D("2500.00"),
        2029: D("1500.00"),
        2030: D("1000.00"),
    }
    with pytest.raises(AfaRegelError, match="Elektro"):
        pruefe_anlage(gut(50000, date(2025, 5, 1), AfaArt.E_FAHRZEUG), STAND)


def test_linear_braucht_nutzungsdauer_und_keine_afa():
    with pytest.raises(AfaRegelError, match="Nutzungsdauer"):
        pruefe_anlage(gut(5000, date(2026, 1, 1)), STAND)
    g = gut(20000, date(2026, 1, 1), AfaArt.KEINE)
    assert reihe(plane(g, STAND)) == {}
    assert plane(g, STAND).restbuchwert(2030, 12) == D("20000")


# --- Vorschlag der AfA-Art --------------------------------------------------------


@pytest.mark.parametrize(
    ("kosten", "tag", "sammelposten_jahr", "art"),
    [
        ("200", date(2026, 1, 1), False, AfaArt.GWG),
        ("700", date(2026, 1, 1), False, AfaArt.GWG),
        ("700", date(2026, 1, 1), True, AfaArt.SAMMELPOSTEN),
        ("900", date(2026, 1, 1), False, AfaArt.LINEAR),
        ("900", date(2026, 1, 1), True, AfaArt.SAMMELPOSTEN),
        ("500", date(2015, 1, 1), False, AfaArt.LINEAR),
        ("400", date(2009, 1, 1), False, AfaArt.SAMMELPOSTEN),
        ("5000", date(2026, 1, 1), False, AfaArt.LINEAR),
    ],
)
def test_vorschlag(kosten, tag, sammelposten_jahr, art):
    vorschlag = schlage_art_vor(D(kosten), tag, STAND, sammelposten_jahr)
    assert vorschlag.art is art
    assert vorschlag.begruendung


def test_vorschlag_nennt_degressive_moeglichkeit():
    v = schlage_art_vor(D("36000"), date(2026, 3, 1), STAND, nutzungsdauer=10)
    assert v.art is AfaArt.LINEAR
    assert "degressiv" in v.begruendung and "30" in v.begruendung
