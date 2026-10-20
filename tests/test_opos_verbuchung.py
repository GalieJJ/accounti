from datetime import date
from decimal import Decimal

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_buchungen,
    lade_kontakte,
    lade_posten,
    speichere_ausgangsrechnung,
    speichere_beleg,
    speichere_kontakt,
)
from accounti.erechnung.ausstellung import stelle_aus
from accounti.klassifikation.engine import Regel, RegelwerkEngine
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Beleg,
    Belegart,
    Belegposition,
    Belegrichtung,
    BelegStatus,
    BuchungStatus,
    Kontakt,
    KontaktStatus,
    PostenRichtung,
)
from accounti.opos.verbuchung import verbuche_belege
from tests.test_erechnung_aufbau import FIRMA, entwurf, kunde, pos

EINSTELLUNGEN = Buchhaltung()


@pytest.fixture
def umgebung(tmp_path):
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    return make_session, BelegArchiv(tmp_path / "archiv")


def eingangsrechnung(**kw):
    b = Beleg(
        datei_hash="a" * 64,
        dateiname="re.pdf",
        kanal="ordner",
        herkunft="x",
        aufbewahren_bis=date(2036, 12, 31),
        belegart=Belegart.EINGANGSRECHNUNG,
        status=BelegStatus.ERFASST,
        belegnummer="RE-2026-0042",
        belegdatum=date(2026, 3, 5),
        lieferant_name="Bürobedarf Müller GmbH",
        lieferant_ust_id="DE123456789",
        iban="DE89370400440532013000",
        netto=Decimal("150.00"),
        steuer=Decimal("22.50"),
        brutto=Decimal("172.50"),
        zahlungsziel=date(2026, 3, 19),
        skonto_prozent=Decimal("2"),
        skonto_tage=7,
    )
    b.positionen = [
        Belegposition(
            beleg_id=b.id,
            bezeichnung="Papier",
            netto=Decimal("100.00"),
            steuersatz=Decimal("19"),
            steuer_betrag=Decimal("19.00"),
        ),
        Belegposition(
            beleg_id=b.id,
            bezeichnung="Fachbuch",
            netto=Decimal("50.00"),
            steuersatz=Decimal("7"),
            steuer_betrag=Decimal("3.50"),
        ),
    ]
    return b.model_copy(update=kw)


def _verbuche(make_session, archiv=None, regelwerk=None):
    with make_session() as s:
        lauf = verbuche_belege(s, EINSTELLUNGEN, archiv=archiv, regelwerk=regelwerk)
        s.commit()
    assert lauf.fehler == []
    return lauf.verbucht


def test_eingangsrechnung_bucht_gegen_kreditor_und_erzeugt_posten(umgebung):
    """Akzeptanz 1."""
    make_session, _ = umgebung
    beleg = eingangsrechnung()
    with make_session() as s:
        speichere_beleg(s, beleg)
        s.commit()
    (v,) = _verbuche(make_session)
    assert v.kontakt_neu
    with make_session() as s:
        (kontakt,) = lade_kontakte(s)
        buchungen = sorted(lade_buchungen(s), key=lambda b: -b.betrag_netto)
        (posten,) = lade_posten(s)
    assert kontakt.kreditor_konto == "70000"
    assert kontakt.status is KontaktStatus.ZUR_PRUEFUNG
    assert (kontakt.iban, kontakt.ust_id) == ("DE89370400440532013000", "DE123456789")
    assert [
        (
            b.soll_konto,
            b.haben_konto,
            b.betrag_netto,
            b.steuer_schluessel,
            b.steuer_betrag,
        )
        for b in buchungen
    ] == [
        ("4900", "70000", Decimal("100.00"), 9, Decimal("19.00")),
        ("4900", "70000", Decimal("50.00"), 8, Decimal("3.50")),
    ]
    assert all(b.beleg_id == beleg.id and b.transaktion_id is None for b in buchungen)
    assert all(b.beleg_nummer == "RE-2026-0042" for b in buchungen)
    # unbekanntes Sachkonto → zur Prüfung
    assert all(b.status is BuchungStatus.ZUR_PRUEFUNG for b in buchungen)
    assert posten.richtung is PostenRichtung.VERBINDLICHKEIT
    assert posten.kontakt_id == kontakt.id
    assert (posten.betrag, posten.restbetrag) == (Decimal("172.50"), Decimal("172.50"))
    assert posten.faellig_am == date(2026, 3, 19)
    assert posten.skonto_bis == date(2026, 3, 12)
    assert posten.skonto_betrag == Decimal("3.45")


def test_bekannter_kontakt_mit_sachkonto_und_zahlungsbedingungen(umgebung):
    make_session, _ = umgebung
    with make_session() as s:
        speichere_kontakt(
            s,
            Kontakt(
                name="Bürobedarf Müller",
                kreditor_konto="70001",
                sachkonto="4930",
                zahlungsziel_tage=30,
                skonto_prozent=Decimal("3"),
                skonto_tage=10,
            ),
        )
        speichere_beleg(
            s,
            eingangsrechnung(
                zahlungsziel=None,
                skonto_prozent=None,
                skonto_tage=None,
                lieferant_name="BUEROBEDARF MÜLLER G.m.b.H.",
                lieferant_ust_id=None,
                iban=None,
            ),
        )
        s.commit()
    (v,) = _verbuche(make_session)
    assert not v.kontakt_neu and v.merkmal == "Name"
    with make_session() as s:
        assert len(lade_kontakte(s)) == 1
        buchungen = lade_buchungen(s)
        (posten,) = lade_posten(s)
    assert {(b.soll_konto, b.haben_konto) for b in buchungen} == {("4930", "70001")}
    assert all(b.status is BuchungStatus.AUTO_GEBUCHT for b in buchungen)
    assert posten.faellig_am == date(2026, 4, 4)
    assert (posten.skonto_bis, posten.skonto_betrag) == (
        date(2026, 3, 15),
        Decimal("5.18"),
    )


def test_regelwerk_liefert_das_sachkonto(umgebung):
    make_session, _ = umgebung
    with make_session() as s:
        speichere_beleg(s, eingangsrechnung())
        s.commit()
    regelwerk = RegelwerkEngine(
        [
            Regel(
                "buero",
                r"b(ü|ue)robedarf",
                "4930",
                "1200",
                9,
                "Bürobedarf",
                feld="beide",
            )
        ]
    )
    _verbuche(make_session, regelwerk=regelwerk)
    with make_session() as s:
        buchungen = lade_buchungen(s)
    assert {b.soll_konto for b in buchungen} == {"4930"}


def test_schreibvarianten_ergeben_einen_kontakt_und_nichts_doppelt(umgebung):
    make_session, _ = umgebung
    with make_session() as s:
        speichere_beleg(s, eingangsrechnung())
        speichere_beleg(
            s,
            eingangsrechnung(
                datei_hash="b" * 64,
                belegnummer="RE-2026-0051",
                lieferant_name="Buerobedarf Mueller",
                lieferant_ust_id=None,
            ),
        )
        speichere_beleg(
            s,
            eingangsrechnung(
                datei_hash="c" * 64,
                belegnummer="RE-2026-0060",
                lieferant_name="Bürobedarf Müller GmbH & Co. KG",
                iban=None,
            ),
        )
        s.commit()
    ergebnis = _verbuche(make_session)
    assert [v.kontakt_neu for v in ergebnis] == [True, False, False]
    assert _verbuche(make_session) == []  # zweiter Lauf: nichts doppelt
    with make_session() as s:
        assert len(lade_kontakte(s)) == 1
        assert len(lade_posten(s)) == 3
        assert len(lade_buchungen(s)) == 6


def test_nur_erfasste_rechnungen_werden_verbucht(umgebung):
    make_session, _ = umgebung
    with make_session() as s:
        speichere_beleg(s, eingangsrechnung(status=BelegStatus.ZUR_PRUEFUNG))
        speichere_beleg(
            s, eingangsrechnung(datei_hash="q" * 64, belegart=Belegart.QUITTUNG)
        )
        s.commit()
    assert _verbuche(make_session) == []


def test_gutschrift_dreht_soll_und_haben(umgebung):
    make_session, _ = umgebung
    beleg = eingangsrechnung(
        brutto=Decimal("-119.00"), netto=Decimal("-100.00"), steuer=Decimal("-19.00")
    )
    beleg.positionen = [
        Belegposition(
            beleg_id=beleg.id,
            bezeichnung="Gutschrift",
            netto=Decimal("-100.00"),
            steuersatz=Decimal("19"),
            steuer_betrag=Decimal("-19.00"),
        )
    ]
    with make_session() as s:
        speichere_beleg(s, beleg)
        s.commit()
    _verbuche(make_session)
    with make_session() as s:
        (b,) = lade_buchungen(s)
        (p,) = lade_posten(s)
    assert (b.soll_konto, b.haben_konto, b.betrag_netto, b.steuer_betrag) == (
        "70000",
        "4900",
        Decimal("100.00"),
        Decimal("19.00"),
    )
    assert p.betrag == Decimal("-119.00")


def _ausgangsrechnung(make_session, archiv, e):
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        stelle_aus(s, archiv, str(e.id)[:8], FIRMA, date(2026, 3, 10))
        s.commit()


def test_ausgangsrechnung_bucht_debitor_an_erloes(umgebung):
    make_session, archiv = umgebung
    _ausgangsrechnung(
        make_session,
        archiv,
        entwurf(
            kunde(),
            pos("Bilderrahmen", "250", "4"),
            pos("Katalog", "25", ermaessigt=True),
        ),
    )
    (v,) = _verbuche(make_session, archiv=archiv)
    with make_session() as s:
        (kontakt,) = lade_kontakte(s)
        buchungen = sorted(lade_buchungen(s), key=lambda b: -b.betrag_netto)
        (posten,) = lade_posten(s)
    assert (kontakt.name, kontakt.debitor_konto, kontakt.status) == (
        "Atelier Kundin GmbH",
        "10000",
        KontaktStatus.GEPRUEFT,
    )
    assert kontakt.ust_id == "DE888888888"
    assert [
        (
            b.soll_konto,
            b.haben_konto,
            b.betrag_netto,
            b.steuer_schluessel,
            b.steuer_betrag,
            b.status,
        )
        for b in buchungen
    ] == [
        (
            "10000",
            "8400",
            Decimal("1000.00"),
            3,
            Decimal("190.00"),
            BuchungStatus.AUTO_GEBUCHT,
        ),
        (
            "10000",
            "8300",
            Decimal("25.00"),
            2,
            Decimal("1.75"),
            BuchungStatus.AUTO_GEBUCHT,
        ),
    ]
    assert posten.richtung is PostenRichtung.FORDERUNG
    assert (posten.betrag, posten.faellig_am) == (Decimal("1216.75"), date(2026, 3, 24))
    assert v.beleg.richtung is Belegrichtung.AUSGANG


@pytest.mark.parametrize(
    ("k", "position", "erloes"),
    [
        (
            kunde(land="AT", ust_id="ATU12345678"),
            pos("Hängung", "90", "8", sonstige_leistung=True),
            "8338",
        ),
        (kunde(land="FR", ust_id="FR12345678901"), pos("Rahmen", "100"), "8125"),
        (kunde(land="CH", ust_id=None), pos("Rahmen", "100"), "8120"),
    ],
    ids=["reverse_charge", "ig_lieferung", "ausfuhr"],
)
def test_steuerfreie_erloese(umgebung, k, position, erloes):
    make_session, archiv = umgebung
    _ausgangsrechnung(make_session, archiv, entwurf(k, position))
    _verbuche(make_session, archiv=archiv)
    with make_session() as s:
        (b,) = lade_buchungen(s)
    assert (b.soll_konto, b.haben_konto, b.steuer_schluessel) == ("10000", erloes, None)
    assert b.status is BuchungStatus.AUTO_GEBUCHT


def test_fehlerhafter_beleg_haelt_den_lauf_nicht_auf(umgebung):
    make_session, _ = umgebung
    ohne_lieferant = eingangsrechnung(datei_hash="z" * 64, lieferant_name=None)
    with make_session() as s:
        speichere_beleg(s, ohne_lieferant)
        speichere_beleg(s, eingangsrechnung())
        s.commit()
    with make_session() as s:
        lauf = verbuche_belege(s, EINSTELLUNGEN)
        s.commit()
        assert len(lauf.verbucht) == 1
        ((beleg, grund),) = lauf.fehler
        assert beleg.id == ohne_lieferant.id
        assert "kein Lieferant" in grund
        assert len(lade_posten(s)) == 1


def test_belegbuchung_im_datev_export(umgebung, tmp_path):
    """Kreditor als Gegenkonto, BU-Schlüssel, Bruttobetrag und Belegfeld 1."""
    import csv

    from accounti.export.datev import DATEVConfig, DATEVExporter

    make_session, _ = umgebung
    with make_session() as s:
        speichere_beleg(s, eingangsrechnung())
        s.commit()
    _verbuche(make_session)
    with make_session() as s:
        buchungen = lade_buchungen(s)
    datei = DATEVExporter(
        DATEVConfig(berater_nummer="1", mandanten_nummer="2")
    ).exportiere(buchungen, tmp_path)
    zeilen = list(
        csv.reader(datei.read_text(encoding="cp1252").splitlines()[1:], delimiter=";")
    )
    kopf, daten = zeilen[0], zeilen[1:]
    spalte = {name: i for i, name in enumerate(kopf)}
    werte = sorted(
        (
            z[spalte["Umsatz (ohne Soll/Haben-Kz)"]],
            z[spalte["Konto"]],
            z[spalte["Gegenkonto (ohne BU-Schlüssel)"]],
            z[spalte["BU-Schlüssel"]],
            z[spalte["Belegfeld 1"]],
        )
        for z in daten
    )
    assert werte == [
        ("119,00", "4900", "70000", "9", "RE-2026-0042"),
        ("53,50", "4900", "70000", "8", "RE-2026-0042"),
    ]


def test_eigene_firma_wird_nicht_zum_kreditor(umgebung):
    from accounti.kontakte.dienst import Partnerdaten

    make_session, _ = umgebung
    with make_session() as s:
        speichere_beleg(
            s,
            eingangsrechnung(
                lieferant_name="Galerie Muster GmbH",
                lieferant_ust_id="DE999999999",
                iban=None,
            ),
        )
        s.commit()
    eigene = Partnerdaten(name="Galerie Muster GmbH", ust_id="DE999999999")
    with make_session() as s:
        lauf = verbuche_belege(s, EINSTELLUNGEN, eigene_firma=eigene)
        s.commit()
        assert lauf.verbucht == []
        ((_, grund),) = lauf.fehler
        assert "eigene Firma" in grund
        assert lade_kontakte(s) == []


def test_eigene_kennungen_aus_der_konfiguration(tmp_path):
    from accounti.konfiguration import lade_eigene_firma

    pfad = tmp_path / "accounti.yaml"
    assert lade_eigene_firma(pfad) is None
    pfad.write_text(
        'mandant:\n  name: "Galerie Muster GmbH"\n  ust_id: DE999999999\n',
        encoding="utf-8",
    )
    eigene = lade_eigene_firma(pfad)
    assert (eigene.name, eigene.ust_id) == ("Galerie Muster GmbH", "DE999999999")
