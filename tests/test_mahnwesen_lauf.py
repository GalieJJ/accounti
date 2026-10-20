"""Mahnlauf: ein überfälliger Posten durchläuft die Stufen (Akzeptanz 6).

Handgerechnet (Rest 1.190,00 €, fällig 15.06.2026, Verzug ab 16.06.2026, act/365):

B2B (Basiszins + 9):
  1. Mahnung 29.06.: 16.–29.06. 14 Tage × 10,27 %
                     → 1190 × 0,1027 × 14 / 365 = 4,6876 → 4,69
     Pauschale 40,00; Gebühren 5,00 angerechnet → 0,00; Summe 1.234,69
  2. Mahnung 13.07.: 16.–30.06. 15 Tage × 10,27 % → 5,0224 → 5,02
                     01.–13.07. 13 Tage × 10,52 % → 4,4588 → 4,46; Zinsen 9,48
     Gebühren 5 + 10 = 15,00 angerechnet → 0,00; Summe 1.190 + 9,48 + 40 = 1.239,48
B2C (Basiszins + 5):
  1. Mahnung 29.06.: 14 Tage × 6,27 % → 2,8619 → 2,86; Gebühren 5,00; Summe 1.197,86
  2. Mahnung 13.07.: 15 Tage × 6,27 % → 3,0663 → 3,07; 13 Tage × 6,52 % → 2,7634 → 2,76
     Zinsen 5,83; Gebühren 15,00; Summe 1.210,83
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from accounti.db.repo_mahnwesen import lade_mahnungen, speichere_mahnkontakt
from accounti.db.repository import (
    aktualisiere_posten,
    lade_einen_posten,
    speichere_ausgangsrechnung,
    speichere_transaktion,
    speichere_zuordnung,
)
from accounti.db.tabellen import UnveraenderbarError
from accounti.db.tabellen_mahnwesen import MahnungRow
from accounti.mahnwesen.konfiguration import MahnEinstellungen
from accounti.mahnwesen.lauf import MahnError, mahnlauf, versende, verwerfe
from accounti.models import (
    Ausgangsrechnung,
    AusgangsrechnungStatus,
    PostenRichtung,
    PostenStatus,
    Rechnungsempfaenger,
    Transaktion,
    TransaktionQuelle,
    Zahlungszuordnung,
    ZuordnungStatus,
)
from accounti.models.mahnwesen import MahnKontakt, MahnungStatus
from tests.zahlung_hilfe import debitor, neue_db, posten, speichere

D = Decimal
E = MahnEinstellungen()


def _umgebung(**kunde):
    fabrik = neue_db()
    k = debitor(**kunde)
    p = posten(
        k,
        "2026-0042",
        "1190.00",
        faellig=date(2026, 6, 15),
        belegdatum=date(2026, 6, 1),
        richtung=PostenRichtung.FORDERUNG,
    )
    speichere(fabrik, [k], [p])
    return fabrik, k, p


def _lauf(fabrik, stichtag, e=E):
    with fabrik() as s:
        ergebnis = mahnlauf(s, stichtag, e)
        s.commit()
    return ergebnis


def _versende(fabrik, nr):
    with fabrik() as s:
        m = versende(s, nr, "pdf", zeitpunkt=datetime(2026, 7, 1, 9, 0))
        s.commit()
    return m


def _stufe(fabrik, p):
    with fabrik() as s:
        return lade_einen_posten(s, p.id).mahnstufe


def test_b2b_posten_durchlaeuft_die_stufen_mit_zinsen_pauschale_und_gebuehren():
    fabrik, k, p = _umgebung(ust_id="DE888888888")

    (erinnerung,) = _lauf(fabrik, date(2026, 6, 20)).mahnungen
    assert (erinnerung.nr, erinnerung.stufe, erinnerung.stufe_name) == (
        1,
        1,
        "Zahlungserinnerung",
    )
    assert erinnerung.unternehmer is True
    assert erinnerung.einstufung == "USt-IdNr. DE888888888 im Stammsatz"
    assert (erinnerung.zinsen, erinnerung.pauschale, erinnerung.gebuehren) == (
        D("0.00"),
        D("0.00"),
        D("0.00"),
    )
    assert erinnerung.summe == D("1190.00") and erinnerung.verzug_ab is None
    assert erinnerung.zahlungsfrist == date(2026, 6, 30)
    assert _stufe(fabrik, p) == 0  # ein Entwurf zählt nicht
    _versende(fabrik, 1)
    assert _stufe(fabrik, p) == 1

    assert _lauf(fabrik, date(2026, 6, 26)).mahnungen == []  # Stufenabstand
    (erste,) = _lauf(fabrik, date(2026, 6, 29)).mahnungen
    assert (erste.stufe, erste.stufe_name, erste.verzug_ab) == (
        2,
        "1. Mahnung",
        date(2026, 6, 16),
    )
    assert [(a.tage, a.satz, a.zinsen) for a in erste.zinsabschnitte] == [
        (14, D("10.27"), D("4.69"))
    ]
    assert erste.zinsen == D("4.69") and erste.pauschale == D("40.00")
    assert erste.gebuehren_kumuliert == D("5.00") and erste.gebuehren == D("0.00")
    assert erste.summe == D("1234.69")
    _versende(fabrik, erste.nr)
    assert _stufe(fabrik, p) == 2

    (zweite,) = _lauf(fabrik, date(2026, 7, 13)).mahnungen
    assert [(a.von, a.tage, a.satz, a.zinsen) for a in zweite.zinsabschnitte] == [
        (date(2026, 6, 16), 15, D("10.27"), D("5.02")),
        (date(2026, 7, 1), 13, D("10.52"), D("4.46")),
    ]
    assert zweite.zinsen == D("9.48") and zweite.pauschale == D("40.00")
    assert zweite.gebuehren_kumuliert == D("15.00") and zweite.gebuehren == 0
    assert zweite.summe == D("1239.48")
    _versende(fabrik, zweite.nr)
    assert _stufe(fabrik, p) == 3

    letzter = _lauf(fabrik, date(2026, 8, 1))
    assert letzter.mahnungen == []
    assert "letzte Stufe (2. Mahnung) erreicht" in letzter.ausnahmen[0].grund
    with fabrik() as s:
        historie = lade_mahnungen(s, posten_id=p.id)
    assert [(m.stufe, m.status) for m in historie] == [
        (1, MahnungStatus.VERSENDET),
        (2, MahnungStatus.VERSENDET),
        (3, MahnungStatus.VERSENDET),
    ]


def test_b2c_ohne_pauschale_mit_gebuehren():
    fabrik, k, p = _umgebung(ust_id=None)
    _lauf(fabrik, date(2026, 6, 20))
    _versende(fabrik, 1)
    (erste,) = _lauf(fabrik, date(2026, 6, 29)).mahnungen
    assert erste.unternehmer is False
    assert "als Verbraucher behandelt" in erste.einstufung
    assert (erste.zinsen, erste.pauschale, erste.gebuehren, erste.summe) == (
        D("2.86"),
        D("0.00"),
        D("5.00"),
        D("1197.86"),
    )
    _versende(fabrik, erste.nr)
    (zweite,) = _lauf(fabrik, date(2026, 7, 13)).mahnungen
    assert [a.zinsen for a in zweite.zinsabschnitte] == [D("3.07"), D("2.76")]
    assert (zweite.zinsen, zweite.gebuehren, zweite.summe) == (
        D("5.83"),
        D("15.00"),
        D("1210.83"),
    )


def test_pauschale_ohne_anrechnung():
    fabrik, k, p = _umgebung(ust_id="DE888888888")
    e = E.model_copy(update={"pauschale_anrechnen": False})
    _lauf(fabrik, date(2026, 6, 20), e)
    _versende(fabrik, 1)
    (erste,) = _lauf(fabrik, date(2026, 6, 29), e).mahnungen
    assert (erste.zinsen, erste.pauschale, erste.gebuehren, erste.summe) == (
        D("4.69"),
        D("40.00"),
        D("5.00"),
        D("1239.69"),
    )


def test_ohne_verzug_weder_zinsen_noch_pauschale():
    """verzug_nach_tagen: 30 (§ 286 Abs. 3 BGB) — am 29.06. noch kein Verzug."""
    fabrik, k, p = _umgebung(ust_id="DE888888888")
    e = E.model_copy(update={"verzug_nach_tagen": 30})
    _lauf(fabrik, date(2026, 6, 20), e)
    _versende(fabrik, 1)
    (erste,) = _lauf(fabrik, date(2026, 6, 29), e).mahnungen
    assert erste.verzug_ab == date(2026, 7, 16)
    assert (erste.zinsen, erste.pauschale, erste.gebuehren, erste.summe) == (
        D("0.00"),
        D("0.00"),
        D("5.00"),
        D("1195.00"),
    )


def test_einstufung_aus_ausgangsrechnung_und_kontakt():
    fabrik, k, p = _umgebung(ust_id="DE888888888")
    with fabrik() as s:
        speichere_ausgangsrechnung(
            s,
            Ausgangsrechnung(
                status=AusgangsrechnungStatus.AUSGESTELLT,
                nummer="2026-0042",
                kunde=Rechnungsempfaenger(name=k.name, privat=True),
                beleg_id=p.beleg_id,
            ),
        )
        s.commit()
    (m,) = _lauf(fabrik, date(2026, 6, 20)).mahnungen
    assert (m.unternehmer, m.einstufung) == (
        False,
        "Ausgangsrechnung 2026-0042: Privatkunde",
    )
    with fabrik() as s:
        verwerfe(s, m.nr)
        speichere_mahnkontakt(s, MahnKontakt(kontakt_id=k.id, unternehmer=True))
        s.commit()
    (m2,) = _lauf(fabrik, date(2026, 6, 20)).mahnungen
    assert m2.unternehmer is True
    assert m2.einstufung == "als Unternehmer eingestuft (accounti mahnwesen kunde)"


def test_teilzahlung_aus_der_zahlungszuordnung():
    fabrik, k, p = _umgebung(ust_id="DE888888888")
    with fabrik() as s:
        tx = Transaktion(
            datum=date(2026, 6, 23),
            betrag=D("1000.00"),
            verwendungszweck="2026-0042 Teilzahlung",
            quelle=TransaktionQuelle.BANK,
            rohtext="x",
        )
        speichere_transaktion(s, tx)
        speichere_zuordnung(
            s,
            Zahlungszuordnung(
                transaktion_id=tx.id,
                posten_id=p.id,
                betrag=D("1000.00"),
                stufe="teil",
                status=ZuordnungStatus.GEBUCHT,
                confidence=1.0,
                begruendung="Test",
            ),
        )
        aktualisiere_posten(s, p.id, D("190.00"), PostenStatus.TEILBEZAHLT)
        s.commit()
    e = MahnEinstellungen(
        stufen=[{"name": "Mahnung", "ab_tagen": 14, "verzugszinsen": True}],
        pauschale_b2b=D("0"),
    )
    (m,) = _lauf(fabrik, date(2026, 6, 29), e).mahnungen
    # 16.–22.06.: 7 Tage auf 1.190 → 1190 × 10,27 % × 7 / 365 = 2,3438 → 2,34
    # 23.–29.06.: 7 Tage auf   190 →  190 × 10,27 % × 7 / 365 = 0,3742 → 0,37
    assert [(a.kapital, a.tage, a.zinsen) for a in m.zinsabschnitte] == [
        (D("1190.00"), 7, D("2.34")),
        (D("190.00"), 7, D("0.37")),
    ]
    assert m.restbetrag == D("190.00") and m.summe == D("192.71")


def test_entwurf_wird_nicht_doppelt_angelegt_und_versendet_ist_historie():
    fabrik, k, p = _umgebung()
    _lauf(fabrik, date(2026, 6, 20))
    zweiter = _lauf(fabrik, date(2026, 6, 20))
    assert zweiter.mahnungen == []
    assert zweiter.ausnahmen[0].grund.startswith("Mahnung 1 ist noch ein Entwurf")
    _versende(fabrik, 1)
    with fabrik() as s:
        with pytest.raises(MahnError, match="nur Entwürfe"):
            versende(s, 1, "pdf")
        with pytest.raises(MahnError, match="nur Entwürfe"):
            verwerfe(s, 1)
    with fabrik() as s:
        zeile = s.scalars(select(MahnungRow)).first()
        zeile.summe = D("1.00")
        with pytest.raises(UnveraenderbarError):
            s.flush()


def test_bezahlter_posten_wird_nicht_mehr_versendet():
    fabrik, k, p = _umgebung()
    _lauf(fabrik, date(2026, 6, 20))
    with fabrik() as s:
        aktualisiere_posten(s, p.id, D("0.00"), PostenStatus.AUSGEGLICHEN)
        s.commit()
    with fabrik() as s, pytest.raises(MahnError, match="inzwischen ausgeglichen"):
        versende(s, 1, "pdf")
