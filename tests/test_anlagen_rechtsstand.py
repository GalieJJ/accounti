"""Rechtsstand: Grenzbeträge gelten ab dem Anschaffungstag (Spec 5, Teststrategie)."""

from datetime import date
from decimal import Decimal

import pytest

from accounti.anlagen.rechtsstand import RechtsstandError, lade_rechtsstand
from accounti.models.anlagen import AfaArt


@pytest.fixture(scope="module")
def stand():
    return lade_rechtsstand()


@pytest.mark.parametrize(
    ("tag", "gwg", "sp_von", "sp_bis", "pflicht"),
    [
        (date(2007, 6, 1), Decimal("410"), None, None, False),
        (date(2009, 12, 31), Decimal("150"), Decimal("150"), Decimal("1000"), True),
        (date(2015, 3, 1), Decimal("410"), Decimal("150"), Decimal("1000"), False),
        (date(2017, 12, 31), Decimal("410"), Decimal("150"), Decimal("1000"), False),
        (date(2018, 1, 1), Decimal("800"), Decimal("250"), Decimal("1000"), False),
        (date(2026, 10, 20), Decimal("800"), Decimal("250"), Decimal("1000"), False),
    ],
)
def test_grenzen_am_anschaffungstag(stand, tag, gwg, sp_von, sp_bis, pflicht):
    g = stand.grenzen_am(tag)
    assert (g.gwg, g.sammelposten_von, g.sammelposten_bis, g.pflicht) == (
        gwg,
        sp_von,
        sp_bis,
        pflicht,
    )
    assert g.quelle


@pytest.mark.parametrize(
    ("tag", "faktor", "hoechst"),
    [
        (date(2019, 12, 31), None, None),
        (date(2020, 1, 1), Decimal("2.5"), Decimal("25")),
        (date(2022, 12, 31), Decimal("2.5"), Decimal("25")),
        (date(2023, 6, 1), None, None),
        (date(2024, 3, 31), None, None),
        (date(2024, 4, 1), Decimal("2"), Decimal("20")),
        (date(2025, 3, 15), None, None),  # Lücke 01.01.–30.06.2025
        (date(2025, 6, 30), None, None),
        (date(2025, 7, 1), Decimal("3"), Decimal("30")),
        (date(2027, 12, 31), Decimal("3"), Decimal("30")),
        (date(2028, 1, 1), None, None),
    ],
)
def test_degressive_fenster(stand, tag, faktor, hoechst):
    f = stand.degressiv_am(tag)
    if faktor is None:
        assert f is None
    else:
        assert (f.faktor, f.hoechstsatz) == (faktor, hoechst)


def test_e_fahrzeug_und_digital(stand):
    assert stand.e_fahrzeug_am(date(2025, 6, 30)) is None
    staffel = stand.e_fahrzeug_am(date(2026, 2, 1))
    assert staffel.saetze == [Decimal(s) for s in (75, 10, 5, 5, 3, 2)]
    assert sum(staffel.saetze) == 100
    assert not stand.digital_am(date(2020, 12, 31))
    assert stand.digital_am(date(2021, 1, 1))
    assert not stand.rap_verzicht_moeglich(date(2020, 12, 31))
    assert stand.rap_verzicht_moeglich(date(2022, 12, 31))


def test_afa_tabelle(stand):
    pkw = stand.afa_tabelle["pkw"]
    assert (pkw.nutzungsdauer, pkw.fundstelle, pkw.konto["SKR03"]) == (
        6,
        "AfA-Tabelle AV 4.2.1",
        "0320",
    )
    assert pkw.kfz
    assert stand.afa_tabelle["bueromoebel"].nutzungsdauer == 13
    notebook = stand.afa_tabelle["notebook"]
    assert (notebook.nutzungsdauer, notebook.afa_art) == (1, AfaArt.DIGITAL)
    assert stand.afa_tabelle["software"].immateriell


def test_eigene_datei_geht_vor_und_ergaenzt(tmp_path):
    datei = tmp_path / "rechtsstand.yaml"
    datei.write_text(
        """
grenzen:
  - von: 2027-01-01
    gwg: 1000
    verzeichnis_ab: 250
    sammelposten_von: 250
    sammelposten_bis: 5000
    quelle: "angenommene Gesetzesänderung"
afa_tabelle:
  pkw:
    bezeichnung: "Pkw (eigene Schätzung)"
    nutzungsdauer: 8
    fundstelle: "eigene Festlegung"
  lastenrad:
    bezeichnung: "Lastenfahrrad"
    nutzungsdauer: 7
    fundstelle: "AfA-Tabelle AV 4.2.2"
""",
        encoding="utf-8",
    )
    stand = lade_rechtsstand(datei)
    assert stand.grenzen_am(date(2027, 2, 1)).gwg == Decimal("1000")
    assert stand.grenzen_am(date(2026, 12, 31)).gwg == Decimal("800")  # alt bleibt
    assert stand.afa_tabelle["pkw"].nutzungsdauer == 8
    assert "lastenrad" in stand.afa_tabelle
    assert "bueromoebel" in stand.afa_tabelle


def test_kaputte_datei(tmp_path):
    datei = tmp_path / "r.yaml"
    datei.write_text("grenzen:\n  - von: kein-datum\n", encoding="utf-8")
    with pytest.raises(RechtsstandError, match="r.yaml"):
        lade_rechtsstand(datei)
    with pytest.raises(RechtsstandError, match="fehlt"):
        lade_rechtsstand(tmp_path / "gibtsnicht.yaml")


def test_quelle_des_corona_fensters(stand):
    """2,5-fach/25 %: Zweites Corona-Steuerhilfegesetz, verlängert durch das Vierte."""
    quelle = stand.degressiv_am(date(2021, 6, 1)).quelle
    assert "29.06.2020" in quelle and "Zweiten Corona-Steuerhilfegesetzes" in quelle
    assert "19.06.2022" in quelle and "Vierte Corona-Steuerhilfegesetz" in quelle
    assert "27.03.2024" not in quelle
