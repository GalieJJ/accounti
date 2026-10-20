"""Anlagegut anlegen — aus Eingaben, AfA-Tabelle oder Beleg."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from accounti.anlagen.afa import AfaRegelError
from accounti.anlagen.dienst import AnlageError, lege_an, vorschlaege
from accounti.anlagen.konfiguration import lade_anlagen
from accounti.db.repository import (
    lade_buchungen,
    speichere_beleg,
    speichere_buchung,
)
from accounti.models import (
    Beleg,
    Belegart,
    Belegposition,
    Buchungssatz,
    BuchungStatus,
)
from accounti.models.anlagen import AfaArt
from tests.abschluss_hilfe import datenbank

D = Decimal


@pytest.fixture
def make_session(tmp_path):
    yield from datenbank(tmp_path)


@pytest.fixture
def einst(tmp_path):
    return lade_anlagen(tmp_path / "keine.yaml")


def _beleg(make_session, netto="1200.00", konto=None):
    b = Beleg(
        belegart=Belegart.EINGANGSRECHNUNG,
        belegnummer="RE-4711",
        belegdatum=date(2026, 9, 10),
        leistungsdatum=date(2026, 9, 15),
        lieferant_name="Bürohaus GmbH",
        netto=D(netto),
        steuer=(D(netto) * D("0.19")).quantize(D("0.01")),
        brutto=(D(netto) * D("1.19")).quantize(D("0.01")),
        datei_hash="a" * 64,
        dateiname="re.pdf",
        kanal="upload",
        herkunft="test",
        aufbewahren_bis=date(2036, 12, 31),
    )
    b.positionen = [
        Belegposition(beleg_id=b.id, bezeichnung="Schreibtisch Eiche", netto=D(netto))
    ]
    with make_session() as s:
        speichere_beleg(s, b)
        if konto:
            speichere_buchung(
                s,
                Buchungssatz(
                    beleg_id=b.id,
                    datum=date(2026, 9, 10),
                    soll_konto=konto,
                    haben_konto="70001",
                    betrag_netto=D(netto),
                    steuer_schluessel=9,
                    steuer_betrag=b.steuer,
                    buchungstext="RE-4711",
                    status=BuchungStatus.AUTO_GEBUCHT,
                ),
            )
        s.commit()
    return b


def test_aus_der_afa_tabelle(make_session, einst):
    with make_session() as s:
        e = lege_an(
            s,
            einst,
            bezeichnung="Firmenwagen",
            datum=date(2026, 3, 1),
            kosten=D("30000"),
            typ="pkw",
        )
    a = e.anlage
    assert (a.nr, a.konto, a.nutzungsdauer, a.afa_art) == (1, "0320", 6, AfaArt.LINEAR)
    assert any("AfA-Tabelle AV 4.2.1" in h for h in e.hinweise)


def test_nutzungsdauer_eingabe_gewinnt_und_digital(make_session, einst):
    with make_session() as s:
        a = lege_an(
            s,
            einst,
            bezeichnung="Wagen",
            datum=date(2026, 3, 1),
            kosten=D("30000"),
            typ="pkw",
            nutzungsdauer=8,
        ).anlage
        nb = lege_an(
            s,
            einst,
            bezeichnung="Notebook",
            datum=date(2026, 3, 1),
            kosten=D("1500"),
            typ="notebook",
        ).anlage
    assert a.nutzungsdauer == 8
    assert (nb.afa_art, nb.nutzungsdauer, nb.konto) == (AfaArt.DIGITAL, 1, "0410")


def test_gwg_vorschlag_und_konto(make_session, einst):
    with make_session() as s:
        a = lege_an(
            s, einst, bezeichnung="Stuhl", datum=date(2026, 3, 1), kosten=D("700")
        ).anlage
    assert (a.afa_art, a.konto) == (AfaArt.GWG, "0480")


def test_fehlende_angaben_und_regelverstoss(make_session, einst):
    with make_session() as s, pytest.raises(AnlageError, match="Nutzungsdauer"):
        lege_an(s, einst, bezeichnung="X", datum=date(2026, 3, 1), kosten=D("5000"))
    with make_session() as s, pytest.raises(AnlageError, match="Anlagekonto"):
        lege_an(
            s,
            einst,
            bezeichnung="X",
            datum=date(2026, 3, 1),
            kosten=D("5000"),
            nutzungsdauer=5,
        )
    with make_session() as s, pytest.raises(AfaRegelError, match="GWG"):
        lege_an(
            s,
            einst,
            bezeichnung="X",
            datum=date(2026, 3, 1),
            kosten=D("900"),
            art=AfaArt.GWG,
        )


def test_aus_beleg_mit_umbuchungsvorschlag(make_session, einst):
    beleg = _beleg(make_session, konto="4980")
    with make_session() as s:
        e = lege_an(
            s,
            einst,
            beleg="RE-4711",
            typ="bueromoebel",
            umbuchen=True,
        )
        s.commit()
    a = e.anlage
    assert (a.bezeichnung, a.anschaffungsdatum, a.anschaffungskosten) == (
        "Schreibtisch Eiche",
        date(2026, 9, 15),
        D("1200.00"),
    )
    assert a.beleg_id == beleg.id
    assert any("4980" in h for h in e.hinweise)
    u = e.umbuchung
    assert (u.soll_konto, u.haben_konto, u.betrag_netto, u.status) == (
        "0420",
        "4980",
        D("1200.00"),
        BuchungStatus.ZUR_PRUEFUNG,
    )
    with make_session() as s:
        assert len(lade_buchungen(s)) == 2


def test_beleg_schon_auf_anlagekonto(make_session, einst):
    _beleg(make_session, konto="0420")
    with make_session() as s:
        e = lege_an(s, einst, beleg="RE-4711", nutzungsdauer=13, konto="0420")
    assert e.umbuchung is None
    with make_session() as s, pytest.raises(AnlageError, match="Beleg"):
        lege_an(s, einst, beleg="RE-0000", nutzungsdauer=13, konto="0420")


def test_vorschlaege_aus_buchungen_auf_anlagekonten(make_session, einst):
    with make_session() as s:
        for konto, text in (("0420", "Regal"), ("4930", "Papier")):
            speichere_buchung(
                s,
                Buchungssatz(
                    datum=date(2026, 4, 1),
                    soll_konto=konto,
                    haben_konto="1200",
                    betrag_netto=D("2000"),
                    buchungstext=text,
                    status=BuchungStatus.GEPRUEFT,
                    erstellt_am=datetime(2026, 4, 1),
                ),
            )
        s.commit()
        treffer = vorschlaege(s, einst, 2026)
    assert [b.buchungstext for b in treffer] == ["Regal"]


def test_ausdrueckliche_nutzungsdauer_schlaegt_digitale_art_der_tabelle(
    make_session, einst
):
    """BMF 22.02.2022: ND 1 Jahr „kann“ — wer 3 Jahre angibt, schreibt linear ab."""
    from accounti.anlagen.afa import plane

    with make_session() as s:
        e = lege_an(
            s,
            einst,
            bezeichnung="Notebook",
            datum=date(2026, 9, 15),
            kosten=D("1500"),
            typ="notebook",
            nutzungsdauer=3,
        )
    nb = e.anlage
    assert (nb.afa_art, nb.nutzungsdauer, nb.konto) == (AfaArt.LINEAR, 3, "0410")
    assert plane(nb, einst.rechtsstand()).afa_im_jahr(2026) == D("166.67")  # 4/36
    assert not any("Nutzungsdauer 1 Jahre" in h for h in e.hinweise)
    assert any("3 Jahre" in h and "angegeben" in h for h in e.hinweise)
    with make_session() as s:
        # ausdrücklich 1 Jahr: die digitale Art der Tabelle bleibt
        digital = lege_an(
            s,
            einst,
            bezeichnung="Tablet",
            datum=date(2026, 9, 15),
            kosten=D("900"),
            typ="computer",
            nutzungsdauer=1,
        ).anlage
    assert (digital.afa_art, digital.nutzungsdauer) == (AfaArt.DIGITAL, 1)
