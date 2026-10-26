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


def test_stornierter_zugang_ist_kein_vorschlag(make_session, einst):
    """Befund B-M4: ein per Storno korrigierter Zugang auf 0420 ist kein Anlagegut."""
    from accounti.pruefung.storno import korrigiere

    zugang = Buchungssatz(
        datum=date(2026, 9, 1),
        soll_konto="0420",
        haben_konto="1200",
        betrag_netto=D("1260.50"),
        steuer_schluessel=9,
        steuer_betrag=D("239.50"),
        buchungstext="Notebook",
        status=BuchungStatus.AUTO_GEBUCHT,
    )
    with make_session() as s:
        speichere_buchung(s, zugang)
        s.commit()
        korrigiere(
            s, str(zugang.id), "4855", "1200", steuer=9, grund="doch Aufwand", von="x"
        )
        s.commit()
        assert vorschlaege(s, einst, 2026) == []


# --- Gesamttest Abschluss B11: Zugang ohne Beleg ------------------------------------


def _bankzugang(make_session, netto="1500", konto="0410", tag=date(2026, 2, 15)):
    b = Buchungssatz(
        datum=tag,
        soll_konto=konto,
        haben_konto="1200",
        betrag_netto=D(netto),
        steuer_schluessel=9,
        steuer_betrag=(D(netto) * D("0.19")).quantize(D("0.01")),
        buchungstext="CYBERPORT NOTEBOOK",
        status=BuchungStatus.AUTO_GEBUCHT,
    )
    with make_session() as s:
        speichere_buchung(s, b)
        s.commit()
    return b


def test_anlegen_mit_zugangsbuchung_ohne_beleg(make_session, einst):
    """Befund B11: Bankumsatz direkt auf 0410, kein Beleg — nach dem Anlegen blieb er
    in ``vorschlaege``; ``--buchung`` verknüpft ihn."""
    from accounti.db.repo_anlagen import lade_anlage

    b = _bankzugang(make_session)
    with make_session() as s:
        assert [x.id for x in vorschlaege(s, einst, 2026)] == [b.id]
        e = lege_an(s, einst, buchung=str(b.id)[:8], typ="notebook", nutzungsdauer=3)
        s.commit()
    a = e.anlage
    assert (a.buchung_id, a.anschaffungskosten, a.anschaffungsdatum, a.konto) == (
        b.id,
        D("1500"),
        date(2026, 2, 15),
        "0410",
    )
    assert not any("≠" in h or "Umbuchung" in h for h in e.hinweise)
    with make_session() as s:
        assert lade_anlage(s, "1").buchung_id == b.id
        assert vorschlaege(s, einst, 2026) == []


def test_zugangsbuchung_mit_abweichung_und_storno(make_session, einst):
    from accounti.pruefung.storno import storniere

    b = _bankzugang(make_session, "600", "0420", date(2026, 3, 1))
    with make_session() as s:
        e = lege_an(
            s,
            einst,
            buchung=str(b.id),
            bezeichnung="Monitor",
            kosten=D("6000"),
            nutzungsdauer=13,
            art=AfaArt.LINEAR,
        )
        s.commit()
    assert any("6.000,00 ≠ Buchung" in h for h in e.hinweise)
    anderer = _bankzugang(make_session, "700", "0420", date(2026, 3, 2))
    with make_session() as s:
        storniere(s, str(anderer.id), grund="falsch", von="erika")
        s.commit()
        with pytest.raises(AnlageError, match="storniert"):
            lege_an(s, einst, buchung=str(anderer.id), nutzungsdauer=5)
        with pytest.raises(AnlageError, match="gefunden"):
            lege_an(s, einst, buchung="ffffffff", nutzungsdauer=5)


def test_vermutlich_erfasst_statt_vorschlag(make_session, einst):
    """Ohne Verknüpfung: ein Gut mit Konto, Datum und Kosten der Buchung heißt
    „vermutlich erfasst“ — ein zweiter gleicher Zugang bleibt Vorschlag."""
    from accounti.anlagen.dienst import vermutlich_erfasst

    b1 = _bankzugang(make_session)
    b2 = _bankzugang(make_session)
    with make_session() as s:
        a = lege_an(
            s,
            einst,
            bezeichnung="Notebook",
            datum=date(2026, 2, 15),
            kosten=D("1500"),
            typ="notebook",
            nutzungsdauer=3,
        ).anlage
        s.commit()
        offen = vorschlaege(s, einst, 2026)
        vermutlich = vermutlich_erfasst(s, einst, 2026)
    assert len(offen) == 1 and len(vermutlich) == 1
    assert {offen[0].id, vermutlich[0][0].id} == {b1.id, b2.id}
    assert vermutlich[0][1].id == a.id
