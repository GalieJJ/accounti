"""Mahnlauf: ein überfälliger Posten durchläuft die Stufen (Akzeptanz 6).

Handgerechnet (Rest 1.190,00 €, fällig 15.06.2026, act/365). Kein vereinbartes
Zahlungsziel: Verzug erst durch die Zahlungserinnerung (§ 286 Abs. 1 BGB) — versendet
am 20.06., Zugang angenommen 23.06., Frist bis 30.06. → erster Zinstag 01.07.2026. Die
1. Mahnung darf erst nach Ablauf dieser Frist entstehen (01.07.), die 2. erst nach der
Frist der 1. (11.07.) und ab Tag 28 nach Fälligkeit (13.07.).

B2B (Basiszins + 9):
  1. Mahnung 01.07.: 01.07. 1 Tag × 10,52 % → 1190 × 0,1052 / 365 = 0,3430 → 0,34
     Pauschale 40,00; Gebühren 5,00 angerechnet → 0,00; Summe 1.230,34
  2. Mahnung 13.07.: 01.–13.07. 13 Tage × 10,52 % → 4,4588 → 4,46
     Gebühren 5 + 10 = 15,00 angerechnet → 0,00; Summe 1.190 + 4,46 + 40 = 1.234,46
B2C (Basiszins + 5):
  1. Mahnung 01.07.: 1 Tag × 6,52 % → 0,2126 → 0,21; Gebühren 5,00; Summe 1.195,21
  2. Mahnung 13.07.: 13 Tage × 6,52 % → 2,7634 → 2,76; Gebühren 15,00; Summe 1.207,76
Zahlungsziel vereinbart (§ 286 Abs. 2 Nr. 1), B2B, 1. Mahnung 01.07.:
  16.–30.06. 15 Tage × 10,27 % → 5,0224 → 5,02; 01.07. → 0,34; Summe 1.235,36
"""

from datetime import date, datetime, time
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
from tests.zahlung_hilfe import (
    debitor,
    neue_db,
    posten,
    speichere,
    zahlung_vorschlagen,
)

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


def _versende(fabrik, nr, am, e=E):
    with fabrik() as s:
        m = versende(s, nr, "pdf", e, zeitpunkt=datetime.combine(am, time(9)))
        s.commit()
    return m


def _stufe(fabrik, p):
    with fabrik() as s:
        return lade_einen_posten(s, p.id).mahnstufe


def _erinnerung_versendet(fabrik, e=E):
    """Zahlungserinnerung am 20.06. berechnet und versendet (Frist 30.06.)."""
    (erinnerung,) = _lauf(fabrik, date(2026, 6, 20), e).mahnungen
    _versende(fabrik, erinnerung.nr, date(2026, 6, 20), e)
    return erinnerung


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
    _versende(fabrik, 1, date(2026, 6, 20))
    assert _stufe(fabrik, p) == 1

    assert _lauf(fabrik, date(2026, 6, 26)).mahnungen == []  # Stufenabstand
    # Tag 15 nach Fälligkeit, Abstand 10 Tage — aber die Frist der Erinnerung läuft
    assert _lauf(fabrik, date(2026, 6, 30)).mahnungen == []
    (erste,) = _lauf(fabrik, date(2026, 7, 1)).mahnungen
    assert (erste.stufe, erste.stufe_name, erste.verzug_ab) == (
        2,
        "1. Mahnung",
        date(2026, 7, 1),
    )
    assert erste.verzug_grund == (
        "Zahlungserinnerung vom 20.06.2026, Frist bis 30.06.2026 (§ 286 Abs. 1 BGB)"
    )
    assert [(a.tage, a.satz, a.zinsen) for a in erste.zinsabschnitte] == [
        (1, D("10.52"), D("0.34"))
    ]
    assert erste.zinsen == D("0.34") and erste.pauschale == D("40.00")
    assert erste.gebuehren_kumuliert == D("5.00") and erste.gebuehren == D("0.00")
    assert erste.summe == D("1230.34") and erste.zahlungsfrist == date(2026, 7, 11)
    _versende(fabrik, erste.nr, date(2026, 7, 1))
    assert _stufe(fabrik, p) == 2

    assert _lauf(fabrik, date(2026, 7, 11)).mahnungen == []  # Frist der 1. Mahnung
    (zweite,) = _lauf(fabrik, date(2026, 7, 13)).mahnungen
    assert [(a.von, a.tage, a.satz, a.zinsen) for a in zweite.zinsabschnitte] == [
        (date(2026, 7, 1), 13, D("10.52"), D("4.46")),
    ]
    assert zweite.verzug_ab == date(2026, 7, 1)  # die erste Mahnung zählt
    assert zweite.zinsen == D("4.46") and zweite.pauschale == D("40.00")
    assert zweite.gebuehren_kumuliert == D("15.00") and zweite.gebuehren == 0
    assert zweite.summe == D("1234.46")
    _versende(fabrik, zweite.nr, date(2026, 7, 13))
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
    _erinnerung_versendet(fabrik)
    (erste,) = _lauf(fabrik, date(2026, 7, 1)).mahnungen
    assert erste.unternehmer is False
    assert "als Verbraucher behandelt" in erste.einstufung
    assert (erste.zinsen, erste.pauschale, erste.gebuehren, erste.summe) == (
        D("0.21"),
        D("0.00"),
        D("5.00"),
        D("1195.21"),
    )
    _versende(fabrik, erste.nr, date(2026, 7, 1))
    (zweite,) = _lauf(fabrik, date(2026, 7, 13)).mahnungen
    assert [a.zinsen for a in zweite.zinsabschnitte] == [D("2.76")]
    assert (zweite.zinsen, zweite.gebuehren, zweite.summe) == (
        D("2.76"),
        D("15.00"),
        D("1207.76"),
    )


def test_pauschale_ohne_anrechnung():
    fabrik, k, p = _umgebung(ust_id="DE888888888")
    e = E.model_copy(update={"pauschale_anrechnen": False})
    _erinnerung_versendet(fabrik, e)
    (erste,) = _lauf(fabrik, date(2026, 7, 1), e).mahnungen
    assert (erste.zinsen, erste.pauschale, erste.gebuehren, erste.summe) == (
        D("0.34"),
        D("40.00"),
        D("5.00"),
        D("1235.34"),
    )


def test_vereinbartes_zahlungsziel_verzug_ab_faelligkeit():
    """§ 286 Abs. 2 Nr. 1 BGB: nur, wenn das Zahlungsziel vertraglich vereinbart ist."""
    fabrik, k, p = _umgebung(ust_id="DE888888888")
    e = E.model_copy(update={"zahlungsziel_vereinbart": True})
    _erinnerung_versendet(fabrik, e)
    (erste,) = _lauf(fabrik, date(2026, 7, 1), e).mahnungen
    assert erste.verzug_ab == date(2026, 6, 16)
    assert erste.verzug_grund == (
        "Zahlungsziel 15.06.2026 vereinbart (§ 286 Abs. 2 Nr. 1 BGB)"
    )
    assert [(a.tage, a.zinsen) for a in erste.zinsabschnitte] == [
        (15, D("5.02")),
        (1, D("0.34")),
    ]
    assert erste.summe == D("1235.36")


def test_verzug_beginnt_mit_dem_zugang_der_erinnerung():
    """Kurze Frist, später Versand: Verzug ab Zugang (Versand + zugang_tage)."""
    fabrik, k, p = _umgebung(ust_id=None)
    e = E.model_copy(update={"zahlungsfrist_tage": 2, "entwurf_gueltig_tage": 1})
    _lauf(fabrik, date(2026, 6, 20), e)  # Frist 22.06.
    _versende(fabrik, 1, date(2026, 6, 21), e)  # Zugang angenommen 24.06.
    (erste,) = _lauf(fabrik, date(2026, 6, 29), e).mahnungen
    assert erste.verzug_ab == date(2026, 6, 25)
    assert erste.verzug_grund == (
        "Zahlungserinnerung vom 21.06.2026, Zugang angenommen 24.06.2026 "
        "(§ 286 Abs. 1 BGB)"
    )
    # 25.–29.06.: 5 Tage × 6,27 % auf 1.190 → 1,0220 → 1,02
    assert erste.zinsen == D("1.02")


def test_ohne_mahnung_und_ohne_vereinbarung_kein_verzug():
    """Erste Stufe gleich mit Zinsen: B2B erst nach 30 Tagen (§ 286 Abs. 3), B2C
    ohne Hinweis auf der Rechnung gar nicht — weder Zinsen noch Pauschale noch
    Gebühren: Mahnkosten sind Verzugsschaden (§§ 280 Abs. 2, 286 BGB), die Mahnung,
    die den Verzug erst begründet, ist nicht erstattungsfähig."""
    e = MahnEinstellungen(
        stufen=[
            {"name": "Mahnung", "ab_tagen": 14, "gebuehr": 5, "verzugszinsen": True}
        ]
    )
    fabrik, k, p = _umgebung(ust_id="DE888888888")
    (b2b,) = _lauf(fabrik, date(2026, 6, 29), e).mahnungen
    assert b2b.verzug_ab == date(2026, 7, 16)
    assert b2b.verzug_grund == (
        "30 Tage nach Fälligkeit und Zugang der Rechnung (§ 286 Abs. 3 BGB)"
    )
    assert (b2b.zinsen, b2b.pauschale, b2b.gebuehren, b2b.summe) == (
        D("0.00"),
        D("0.00"),
        D("0.00"),
        D("1190.00"),
    )
    assert b2b.gebuehren_kumuliert == 0
    fabrik, k, p = _umgebung(ust_id=None)
    (b2c,) = _lauf(fabrik, date(2026, 8, 31), e).mahnungen
    assert b2c.verzug_ab is None and b2c.zinsen == 0
    assert (b2c.gebuehren, b2c.gebuehren_kumuliert, b2c.summe) == (
        D("0.00"),
        D("0.00"),
        D("1190.00"),
    )
    assert b2c.verzug_grund == (
        "kein Verzug: weder Zahlungsziel vereinbart noch Mahnung zugegangen"
    )
    mit_hinweis = e.model_copy(update={"hinweis_30_tage": True})
    with fabrik() as s:
        verwerfe(s, b2c.nr)
        s.commit()
    (b2c,) = _lauf(fabrik, date(2026, 8, 31), mit_hinweis).mahnungen
    assert b2c.verzug_ab == date(2026, 7, 16) and b2c.zinsen > 0
    assert b2c.gebuehren == D("5.00")  # im Verzug gemahnt: erstattungsfähig


def test_gebuehren_nur_fuer_mahnungen_im_verzug():
    """Die erste Stufe kostet etwas, begründet aber erst den Verzug: ihre Gebühr
    verlangt weder sie selbst noch die nächste Stufe.

    B2C, kein Hinweis auf § 286 Abs. 3: 1. Mahnung am 29.06. versendet, Frist bis
    09.07. → Verzug ab 10.07. 2. Mahnung am 13.07.: 10.–13.07. 4 Tage × 6,52 % auf
    1.190 → 0,8503 → 0,85; Gebühren nur die eigenen 10,00; Summe 1.200,85.
    """
    e = MahnEinstellungen(
        stufen=[
            {"name": "1. Mahnung", "ab_tagen": 14, "gebuehr": 5, "verzugszinsen": True},
            {
                "name": "2. Mahnung",
                "ab_tagen": 28,
                "gebuehr": 10,
                "verzugszinsen": True,
            },
        ]
    )
    fabrik, k, p = _umgebung(ust_id=None)
    (erste,) = _lauf(fabrik, date(2026, 6, 29), e).mahnungen
    assert (erste.verzug_ab, erste.gebuehren_kumuliert, erste.gebuehren) == (
        None,
        D("0.00"),
        D("0.00"),
    )
    assert erste.summe == D("1190.00")
    _versende(fabrik, erste.nr, date(2026, 6, 29), e)

    (zweite,) = _lauf(fabrik, date(2026, 7, 13), e).mahnungen
    assert zweite.verzug_ab == date(2026, 7, 10)
    assert zweite.zinsen == D("0.85")
    assert (zweite.gebuehren_kumuliert, zweite.gebuehren) == (D("10.00"), D("10.00"))
    assert zweite.summe == D("1200.85")


def test_gebuehr_einer_stufe_ohne_zinsen_nur_im_verzug():
    """Eine Stufe ohne Verzugszinsen, aber mit Gebühr: Die Gebühr gibt es nur im
    Verzug — dann stehen Verzugsbeginn und Grund in der Mahnung, Zinsen und Pauschale
    verlangt die Stufe trotzdem nicht. Spätere Stufen verlangen sie mit."""
    e = MahnEinstellungen(
        stufen=[
            {"name": "Zahlungserinnerung", "ab_tagen": 5, "gebuehr": "2.50"},
            {"name": "1. Mahnung", "ab_tagen": 14, "gebuehr": 5, "verzugszinsen": True},
        ]
    )
    fabrik, k, p = _umgebung(ust_id="DE888888888")
    (ohne,) = _lauf(fabrik, date(2026, 6, 20), e).mahnungen
    assert ohne.verzug_ab == date(2026, 7, 16)  # erst nach 30 Tagen (§ 286 Abs. 3)
    assert (ohne.gebuehren, ohne.summe) == (D("0.00"), D("1190.00"))

    vereinbart = e.model_copy(update={"zahlungsziel_vereinbart": True})
    fabrik, k, p = _umgebung(ust_id="DE888888888")
    (erinnerung,) = _lauf(fabrik, date(2026, 6, 20), vereinbart).mahnungen
    assert erinnerung.verzug_ab == date(2026, 6, 16)
    assert (erinnerung.zinsen, erinnerung.pauschale, erinnerung.gebuehren) == (
        D("0.00"),
        D("0.00"),
        D("2.50"),
    )
    assert erinnerung.summe == D("1192.50")
    _versende(fabrik, erinnerung.nr, date(2026, 6, 20), vereinbart)
    (erste,) = _lauf(fabrik, date(2026, 7, 1), vereinbart).mahnungen
    assert erste.gebuehren_kumuliert == D("7.50")  # Erinnerung im Verzug versendet
    assert (erste.pauschale, erste.gebuehren) == (D("40.00"), D("0.00"))  # angerechnet


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


def _rechnung(fabrik, p, **kunde):
    with fabrik() as s:
        speichere_ausgangsrechnung(
            s,
            Ausgangsrechnung(
                status=AusgangsrechnungStatus.AUSGESTELLT,
                nummer="2026-0042",
                kunde=Rechnungsempfaenger(name="Max Mustermann", **kunde),
                beleg_id=p.beleg_id,
            ),
        )
        s.commit()


def test_ausgangsrechnung_ohne_privat_und_ohne_ust_idnr_gilt_nicht_als_b2b():
    """privat=False ist nur der Standard der Rechnung, kein Beleg für Unternehmer."""
    fabrik, k, p = _umgebung(name="Max Mustermann", ust_id=None)
    _rechnung(fabrik, p)
    (m,) = _lauf(fabrik, date(2026, 6, 20)).mahnungen
    assert (m.unternehmer, m.einstufung) == (
        False,
        "keine Angabe — als Verbraucher behandelt (mahnwesen.unbekannt_als)",
    )


@pytest.mark.parametrize(
    ("kunde", "erwartet"),
    [
        (
            {"ust_id": "DE777777777"},
            "Ausgangsrechnung 2026-0042: USt-IdNr. DE777777777",
        ),
        (
            {"leitweg_id": "991-12345-67"},
            "Ausgangsrechnung 2026-0042: öffentlicher Auftraggeber (Leitweg-ID)",
        ),
    ],
)
def test_ausgangsrechnung_mit_ust_idnr_oder_leitweg_id(kunde, erwartet):
    fabrik, k, p = _umgebung(name="Max Mustermann", ust_id=None)
    _rechnung(fabrik, p, **kunde)
    (m,) = _lauf(fabrik, date(2026, 6, 20)).mahnungen
    assert (m.unternehmer, m.einstufung) == (True, erwartet)


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
        zahlungsziel_vereinbart=True,
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
    _versende(fabrik, 1, date(2026, 6, 20))
    with fabrik() as s:
        with pytest.raises(MahnError, match="nur Entwürfe"):
            versende(s, 1, "pdf", E, zeitpunkt=datetime(2026, 6, 20, 10))
        with pytest.raises(MahnError, match="nur Entwürfe"):
            verwerfe(s, 1)
    with fabrik() as s:
        zeile = s.scalars(select(MahnungRow)).first()
        zeile.summe = D("1.00")
        with pytest.raises(UnveraenderbarError):
            s.flush()


def _versuch(fabrik, am, nr=1):
    with fabrik() as s:
        return versende(s, nr, "pdf", E, zeitpunkt=datetime.combine(am, time(9)))


def test_bezahlter_posten_wird_nicht_mehr_versendet():
    fabrik, k, p = _umgebung()
    _lauf(fabrik, date(2026, 6, 20))
    with fabrik() as s:
        aktualisiere_posten(s, p.id, D("0.00"), PostenStatus.AUSGEGLICHEN)
        s.commit()
    with pytest.raises(MahnError, match="inzwischen ausgeglichen"):
        _versuch(fabrik, date(2026, 6, 20))


def test_veralteter_entwurf_wird_nicht_versendet():
    """Am 20.06. berechnet, erst am 24.06. verschickt: Datum, Zinsen und Frist im
    Brief stimmen nicht mehr — neu berechnen."""
    fabrik, k, p = _umgebung()
    _lauf(fabrik, date(2026, 6, 20))
    with pytest.raises(MahnError) as fehler:
        _versuch(fabrik, date(2026, 6, 24))
    assert str(fehler.value) == (
        "Mahnung 1 vom 20.06.2026 ist veraltet (mehr als 3 Tage alt, "
        "mahnwesen.entwurf_gueltig_tage) — verwerfen und den Mahnlauf wiederholen"
    )
    with pytest.raises(MahnError, match="auf den 20.06.2026 datiert"):
        _versuch(fabrik, date(2026, 6, 19))
    assert _versuch(fabrik, date(2026, 6, 23)).status is MahnungStatus.VERSENDET


def test_mahnsperre_nach_dem_lauf_stoppt_den_versand():
    fabrik, k, p = _umgebung()
    _lauf(fabrik, date(2026, 6, 20))
    with fabrik() as s:
        speichere_mahnkontakt(
            s,
            MahnKontakt(
                kontakt_id=k.id, mahnsperre=True, sperrgrund="Reklamation offen"
            ),
        )
        s.commit()
    with pytest.raises(MahnError, match="Mahnsperre: Reklamation offen"):
        _versuch(fabrik, date(2026, 6, 20))
    assert _stufe(fabrik, p) == 0


def test_vorgeschlagene_zahlung_nach_dem_lauf_stoppt_den_versand():
    fabrik, k, p = _umgebung()
    _lauf(fabrik, date(2026, 6, 20))
    zahlung_vorschlagen(fabrik, p, datum=date(2026, 6, 19))
    with pytest.raises(MahnError, match="Zahlung vorgeschlagen"):
        _versuch(fabrik, date(2026, 6, 20))
    assert _stufe(fabrik, p) == 0
