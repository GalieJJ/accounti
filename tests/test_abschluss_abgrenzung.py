"""Rechnungsabgrenzung: Vorschlag mit Auflösung im Folgejahr (Akzeptanz 3)."""

from datetime import date
from decimal import Decimal

import pytest

from accounti.abschluss.abgrenzung import (
    AbgrenzungError,
    Zeitraum,
    anteil_nach,
    bestaetige_abgrenzung,
    finde_zeitraum,
    grenze_ab,
    lehne_abgrenzung_ab,
    schlage_abgrenzungen_vor,
)
from accounti.abschluss.konfiguration import lade_abschluss
from accounti.abschluss.salden import summen_und_salden
from accounti.anlagen.rechtsstand import lade_rechtsstand
from accounti.db.repo_abschluss import lade_abgrenzungen
from accounti.db.repository import (
    lade_buchungen,
    speichere_beleg,
    speichere_transaktion,
)
from accounti.models import (
    Beleg,
    Belegposition,
    BuchungStatus,
    Transaktion,
    TransaktionQuelle,
)
from accounti.models.abschluss import AbgrenzungArt, AbgrenzungStatus
from tests.abschluss_hilfe import buche, datenbank

D = Decimal
STAND = lade_rechtsstand()


@pytest.fixture
def make_session(tmp_path):
    yield from datenbank(tmp_path)


@pytest.fixture
def bilanz(tmp_path):
    datei = tmp_path / "bilanz.yaml"
    datei.write_text("abschluss:\n  gewinnermittlung: bilanz\n", encoding="utf-8")
    return lade_abschluss(datei)


def vorschlagen(make_session, einst, jahr=2026):
    with make_session() as s:
        lauf = schlage_abgrenzungen_vor(s, jahr, einst, STAND)
        s.commit()
    return lauf


@pytest.mark.parametrize(
    ("text", "von", "bis"),
    [
        (
            "Betriebshaftpflicht 01.01.2027 - 31.12.2027",
            date(2027, 1, 1),
            date(2027, 12, 31),
        ),
        ("Zeitraum 01.12.2026 bis 30.11.2027", date(2026, 12, 1), date(2027, 11, 30)),
        ("Beitrag 1.12.26–30.11.27", date(2026, 12, 1), date(2027, 11, 30)),
        ("Wartungsvertrag 01/2027-12/2027", date(2027, 1, 1), date(2027, 12, 31)),
        ("Leasing 12/2026 bis 11/2027", date(2026, 12, 1), date(2027, 11, 30)),
    ],
)
def test_zeitraum_aus_text(text, von, bis):
    assert finde_zeitraum("ohne", text) == Zeitraum(von, bis)


def test_kein_zeitraum():
    assert finde_zeitraum("Porto", None, "RE-4711") is None
    assert finde_zeitraum("31.02.2026 - 31.12.2026") is None
    assert finde_zeitraum("31.12.2027 - 01.01.2027") is None  # rückwärts


def test_anteil_monats_und_taggenau():
    stichtag = date(2026, 12, 31)
    assert anteil_nach(Zeitraum(date(2026, 12, 1), date(2027, 11, 30)), stichtag) == (
        11,
        12,
        "Monate",
    )
    assert anteil_nach(Zeitraum(date(2026, 12, 15), date(2027, 12, 14)), stichtag) == (
        348,
        365,
        "Tage",
    )
    assert anteil_nach(Zeitraum(date(2027, 1, 1), date(2027, 12, 31)), stichtag)[
        :2
    ] == (
        12,
        12,
    )
    assert anteil_nach(Zeitraum(date(2026, 1, 1), date(2026, 12, 31)), stichtag)[0] == 0


def test_akzeptanz_3_dezember_jahresversicherung(make_session, bilanz):
    """Im Dezember gezahlte Jahresversicherung → ARAP-Vorschlag samt Auflösung."""
    versicherung = buche(
        make_session,
        date(2026, 12, 15),
        "4360",
        "1200",
        "1200",
        "Betriebshaftpflicht 01.01.2027 - 31.12.2027",
    )
    lauf = vorschlagen(make_session, bilanz)
    (v,) = lauf.vorschlaege
    assert (v.art, v.konto, v.rap_konto, v.betrag, v.status) == (
        AbgrenzungArt.ARAP,
        "4360",
        "0980",
        D("1200.00"),
        AbgrenzungStatus.VORGESCHLAGEN,
    )
    assert v.buchung_id == versicherung.id
    assert "12/12" in v.rechenweg
    # Vorschlag bucht nichts
    with make_session() as s:
        assert len(lade_buchungen(s)) == 1

    with make_session() as s:
        bestaetigt = bestaetige_abgrenzung(s, str(v.nr), "pruefer")
        s.commit()
    assert bestaetigt.status is AbgrenzungStatus.BESTAETIGT
    with make_session() as s:
        neu = {b.id: b for b in lade_buchungen(s)}
    ab = neu[bestaetigt.abgrenzung_buchung_id]
    auf = neu[bestaetigt.aufloesung_buchung_id]
    assert (ab.datum, ab.soll_konto, ab.haben_konto, ab.betrag_netto) == (
        date(2026, 12, 31),
        "0980",
        "4360",
        D("1200.00"),
    )
    # die Umkehrung entsteht im Folgejahr gleich mit
    assert (auf.datum, auf.soll_konto, auf.haben_konto, auf.betrag_netto) == (
        date(2027, 1, 1),
        "4360",
        "0980",
        D("1200.00"),
    )
    assert ab.status is auf.status is BuchungStatus.GEPRUEFT
    kr = bilanz.lade_kontenrahmen()
    with make_session() as s:
        assert summen_und_salden(s, 2026, kr, "bilanz").saldo("4360") == 0
        assert summen_und_salden(s, 2026, kr, "bilanz").saldo("0980") == D("1200")
        folgejahr = summen_und_salden(s, 2027, kr, "bilanz")
    assert folgejahr.saldo("4360") == D("1200") and folgejahr.saldo("0980") == D(
        "-1200"
    )


def test_anteilig_und_passiv(make_session, bilanz):
    buche(
        make_session,
        date(2026, 12, 1),
        "4360",
        "1200",
        "1200",
        "Versicherung 01.12.2026 bis 30.11.2027",
    )
    buche(
        make_session,
        date(2026, 12, 20),
        "1200",
        "8400",
        "2400",
        "Wartungsvertrag 01/2027-12/2027",
        steuer_schluessel=3,
        steuer_betrag=D("456"),
    )
    lauf = vorschlagen(make_session, bilanz)
    nach_art = {v.art: v for v in lauf.vorschlaege}
    assert nach_art[AbgrenzungArt.ARAP].betrag == D("1100.00")  # 11/12
    prap = nach_art[AbgrenzungArt.PRAP]
    assert (prap.konto, prap.rap_konto, prap.betrag) == ("8400", "0990", D("2400.00"))
    with make_session() as s:
        b = bestaetige_abgrenzung(s, str(prap.nr), "pruefer")
        s.commit()
        neu = {x.id: x for x in lade_buchungen(s)}
    ab, auf = neu[b.abgrenzung_buchung_id], neu[b.aufloesung_buchung_id]
    assert (ab.soll_konto, ab.haben_konto) == ("8400", "0990")
    assert (auf.soll_konto, auf.haben_konto, auf.datum) == (
        "0990",
        "8400",
        date(2027, 1, 1),
    )


def test_kein_vorschlag_ohne_folgejahr_und_idempotent(make_session, bilanz):
    buche(make_session, date(2026, 3, 1), "4930", "1200", "50", "Papier")
    buche(
        make_session,
        date(2026, 1, 5),
        "4360",
        "1200",
        "900",
        "Versicherung 01.01.2026 - 31.12.2026",
    )
    buche(
        make_session,
        date(2026, 12, 2),
        "4360",
        "1200",
        "600",
        "Kfz 01.12.2026-30.11.2027",
        status=BuchungStatus.ZUR_PRUEFUNG,
    )
    buche(
        make_session,
        date(2026, 12, 2),
        "4360",
        "1200",
        "1200",
        "Gebäude 01.01.2027-31.12.2027",
    )
    assert len(vorschlagen(make_session, bilanz).vorschlaege) == 1  # nur freigegebene
    assert vorschlagen(make_session, bilanz).vorschlaege == []  # schon vorgeschlagen
    with make_session() as s:
        (v,) = lade_abgrenzungen(s, 2026)
        abgelehnt = lehne_abgrenzung_ab(s, str(v.nr), "pruefer")
        s.commit()
    assert abgelehnt.status is AbgrenzungStatus.ABGELEHNT
    assert vorschlagen(make_session, bilanz).vorschlaege == []
    with make_session() as s, pytest.raises(AbgrenzungError, match="abgelehnt"):
        bestaetige_abgrenzung(s, str(v.nr), "pruefer")


def test_zeitraum_aus_beleg_und_umsatz(make_session, bilanz):
    beleg = Beleg(
        belegnummer="RE-99",
        datei_hash="b" * 64,
        dateiname="re.pdf",
        kanal="upload",
        herkunft="test",
        aufbewahren_bis=date(2036, 12, 31),
    )
    beleg.positionen = [
        Belegposition(
            beleg_id=beleg.id,
            bezeichnung="Softwarewartung 01.01.2027-31.12.2027",
            netto=D("600"),
        )
    ]
    tx = Transaktion(
        datum=date(2026, 12, 28),
        betrag=D("-360"),
        verwendungszweck="Miete Lager 01/2027-06/2027",
        quelle=TransaktionQuelle.BANK,
        rohtext="x",
    )
    with make_session() as s:
        speichere_beleg(s, beleg)
        speichere_transaktion(s, tx)
        s.commit()
    buche(
        make_session,
        date(2026, 12, 20),
        "4806",
        "70001",
        "600",
        "RE-99",
        beleg_id=beleg.id,
    )
    buche(
        make_session,
        date(2026, 12, 28),
        "4210",
        "1200",
        "360",
        "Miete",
        transaktion_id=tx.id,
    )
    betraege = sorted(v.betrag for v in vorschlagen(make_session, bilanz).vorschlaege)
    assert betraege == [D("360.00"), D("600.00")]


def test_rap_verzicht_bis_gwg_grenze(make_session, tmp_path):
    datei = tmp_path / "verzicht.yaml"
    datei.write_text(
        "abschluss:\n  gewinnermittlung: bilanz\n  rap_verzicht_bis_gwg: true\n",
        encoding="utf-8",
    )
    einst = lade_abschluss(datei)
    buche(
        make_session,
        date(2026, 12, 1),
        "4360",
        "1200",
        "800",
        "Versicherung 01.01.2027-31.12.2027",
    )
    buche(
        make_session,
        date(2026, 12, 1),
        "4360",
        "1200",
        "800.01",
        "Versicherung 01.01.2027-31.12.2027",
    )
    lauf = vorschlagen(make_session, einst)
    assert [v.betrag for v in lauf.vorschlaege] == [D("800.01")]
    assert any("§ 5 Abs. 5 Satz 2" in h and "800,00" in h for h in lauf.hinweise)


def test_euer_kennt_keine_rechnungsabgrenzung(make_session, tmp_path):
    euer = lade_abschluss(tmp_path / "fehlt.yaml")
    buche(
        make_session,
        date(2026, 12, 15),
        "4360",
        "1200",
        "1200",
        "Versicherung 01.01.2027 - 31.12.2027",
    )
    lauf = vorschlagen(make_session, euer)
    assert lauf.vorschlaege == []
    assert any("§ 11 EStG" in h for h in lauf.hinweise)


def test_manuell_abgrenzen(make_session, bilanz):
    b = buche(make_session, date(2026, 11, 2), "4360", "1200", "1200", "Versicherung")
    with make_session() as s:
        v = grenze_ab(s, str(b.id)[:8], date(2026, 11, 1), date(2027, 10, 31), bilanz)
        s.commit()
    assert v.betrag == D("1000.00")  # 10/12
    with make_session() as s, pytest.raises(AbgrenzungError, match="schon"):
        grenze_ab(s, str(b.id)[:8], date(2026, 11, 1), date(2027, 10, 31), bilanz)
    bank = buche(make_session, date(2026, 11, 2), "1200", "1360", "5", "Umbuchung")
    with make_session() as s, pytest.raises(AbgrenzungError, match="Erfolgskonto"):
        grenze_ab(s, str(bank.id)[:8], date(2026, 11, 1), date(2027, 10, 31), bilanz)


def test_gesperrtes_jahr(make_session, bilanz):
    from datetime import datetime

    from accounti.db.repo_abschluss import setze_jahresabschluss
    from accounti.db.tabellen_abschluss import JahrGesperrtError
    from accounti.models.abschluss import Jahresabschluss

    b = buche(
        make_session,
        date(2026, 12, 1),
        "4360",
        "1200",
        "1200",
        "Versicherung 01.01.2027-31.12.2027",
    )
    with make_session() as s:
        setze_jahresabschluss(
            s,
            Jahresabschluss(
                jahr=2026,
                gesperrt=True,
                gewinnermittlung="bilanz",
                ergebnis=D("0"),
                abgeschlossen_am=datetime.now(),
                von="test",
            ),
        )
        s.commit()
    with make_session() as s, pytest.raises(JahrGesperrtError):
        schlage_abgrenzungen_vor(s, 2026, bilanz, STAND)
    with make_session() as s, pytest.raises(JahrGesperrtError):
        grenze_ab(s, str(b.id)[:8], date(2026, 12, 1), date(2027, 11, 30), bilanz)


def _rap_bestand(make_session, konto, bis):
    with make_session() as s:
        return sum(
            (
                (b.betrag_netto if b.soll_konto == konto else -b.betrag_netto)
                for b in lade_buchungen(s)
                if konto in (b.soll_konto, b.haben_konto) and b.datum <= bis
            ),
            D("0"),
        )


@pytest.mark.parametrize(
    ("text", "betrag", "rap", "aufwand"),
    [
        (
            "Wartung 01.12.2026 - 30.11.2028",
            "2400",
            "2300.00",
            {2026: "100.00", 2027: "1200.00", 2028: "1100.00"},
        ),
        (
            "Versicherung 01.12.2026 - 30.11.2029",
            "3600",
            "3500.00",
            {2026: "100.00", 2027: "1200.00", 2028: "1200.00", 2029: "1100.00"},
        ),
        (
            "Lizenz 15.12.2026 - 14.12.2028",  # 731 Tage zu je 10 €
            "7310",
            "7140.00",
            {2026: "170.00", 2027: "3650.00", 2028: "3490.00"},
        ),
    ],
)
def test_mehrjaehriger_zeitraum_wird_je_jahr_aufgeloest(
    make_session, bilanz, text, betrag, rap, aufwand
):
    """§ 250 HGB: aufgelöst wird je Folgejahr nur dessen Anteil, der Rest bleibt."""
    buche(make_session, date(2026, 12, 10), "4360", "1200", betrag, text)
    (v,) = vorschlagen(make_session, bilanz).vorschlaege
    assert v.betrag == D(rap)
    assert "2027" in v.rechenweg and str(max(aufwand)) in v.rechenweg
    with make_session() as s:
        bestaetige_abgrenzung(s, str(v.nr), "pruefer")
        s.commit()
    kr = bilanz.lade_kontenrahmen()
    with make_session() as s:
        for jahr, soll in aufwand.items():
            saldo = summen_und_salden(s, jahr, kr, "bilanz").saldo("4360")
            assert saldo == D(soll), jahr
    rest = D(rap)
    for jahr, soll in aufwand.items():
        if jahr > 2026:
            rest -= D(soll)
        assert _rap_bestand(make_session, "0980", date(jahr, 12, 31)) == rest, jahr
    assert rest == 0
    # die Folgejahre schlagen die Auflösungen nicht erneut vor
    for jahr in aufwand:
        if jahr > 2026:
            assert vorschlagen(make_session, bilanz, jahr).vorschlaege == []


def test_entscheider_wird_auf_die_spaltenlaenge_gekuerzt(make_session, bilanz):
    buche(
        make_session,
        date(2026, 12, 1),
        "4360",
        "1200",
        "1200",
        "Versicherung 01.01.2027-31.12.2027",
    )
    (v,) = vorschlagen(make_session, bilanz).vorschlaege
    with make_session() as s:
        lehne_abgrenzung_ab(s, str(v.nr), "X" * 80)
        s.commit()
    with make_session() as s:
        (a,) = lade_abgrenzungen(s, 2026)
    assert a.entschieden_von == "X" * 50
