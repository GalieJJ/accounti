from datetime import date
from decimal import Decimal

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_buchungen, lade_posten, speichere_beleg
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Belegposition,
    BuchungStatus,
    PostenStatus,
    Transaktion,
    TransaktionQuelle,
)
from accounti.opos.ausgleich import gleiche_aus
from accounti.opos.zuordnung import Anteil
from tests.test_erechnung_aufbau import entwurf, kunde, pos
from tests.test_opos_verbuchung import (
    EINSTELLUNGEN,
    _ausgangsrechnung,
    _verbuche,
    eingangsrechnung,
)


@pytest.fixture
def umgebung(tmp_path):
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    return make_session, BelegArchiv(tmp_path / "archiv")


def tx(betrag, datum=date(2026, 3, 10), zweck="Zahlung"):
    return Transaktion(
        datum=datum,
        betrag=Decimal(betrag),
        verwendungszweck=zweck,
        quelle=TransaktionQuelle.BANK,
        rohtext="x",
    )


def _mit_posten(make_session, beleg=None):
    with make_session() as s:
        speichere_beleg(s, beleg or eingangsrechnung())
        s.commit()
    _verbuche(make_session)
    with make_session() as s:
        (posten,) = lade_posten(s)
    return posten


def _zahlungs_und_skontobuchungen(make_session, transaktion):
    with make_session() as s:
        return sorted(
            [b for b in lade_buchungen(s) if b.transaktion_id == transaktion.id],
            key=lambda b: (b.haben_konto, b.soll_konto),
        )


def _zeile(b):
    return (
        b.soll_konto,
        b.haben_konto,
        b.betrag_netto,
        b.steuer_schluessel,
        b.steuer_betrag,
    )


def test_skonto_mit_vorsteuerkorrektur_19_und_7(umgebung):
    """Akzeptanz 3 — gegen handgerechnete Sollwerte."""
    make_session, _ = umgebung
    posten = _mit_posten(make_session)
    zahlung = tx("-169.05")
    with make_session() as s:
        gleiche_aus(
            s,
            zahlung,
            [Anteil(posten, Decimal("169.05"), Decimal("3.45"))],
            EINSTELLUNGEN,
        )
        s.commit()
        (p,) = lade_posten(s)
    assert [
        _zeile(b) for b in _zahlungs_und_skontobuchungen(make_session, zahlung)
    ] == [
        ("70000", "1200", Decimal("169.05"), None, None),
        ("70000", "3731", Decimal("1.00"), 8, Decimal("0.07")),
        ("70000", "3736", Decimal("2.00"), 9, Decimal("0.38")),
    ]
    assert (p.restbetrag, p.status) == (Decimal("0.00"), PostenStatus.AUSGEGLICHEN)


def test_zahlungsbuchung_traegt_beleg_und_transaktion(umgebung):
    make_session, _ = umgebung
    posten = _mit_posten(make_session)
    zahlung = tx("-172.50")
    with make_session() as s:
        gleiche_aus(s, zahlung, [Anteil(posten, Decimal("172.50"))], EINSTELLUNGEN)
        s.commit()
    (b,) = _zahlungs_und_skontobuchungen(make_session, zahlung)
    assert (b.beleg_id, b.beleg_nummer, b.datum) == (
        posten.beleg_id,
        "RE-2026-0042",
        date(2026, 3, 10),
    )
    assert b.status is BuchungStatus.AUTO_GEBUCHT
    assert "Bürobedarf Müller" in b.buchungstext


def test_teilzahlung_und_rest(umgebung):
    """Akzeptanz 4."""
    make_session, _ = umgebung
    posten = _mit_posten(make_session)
    with make_session() as s:
        gleiche_aus(
            s, tx("-100.00"), [Anteil(posten, Decimal("100.00"))], EINSTELLUNGEN
        )
        s.commit()
        (p,) = lade_posten(s)
    assert (p.restbetrag, p.status) == (Decimal("72.50"), PostenStatus.TEILBEZAHLT)
    with make_session() as s:
        gleiche_aus(s, tx("-72.50"), [Anteil(p, Decimal("72.50"))], EINSTELLUNGEN)
        s.commit()
        (p,) = lade_posten(s)
    assert (p.restbetrag, p.status) == (Decimal("0.00"), PostenStatus.AUSGEGLICHEN)


def test_ueberzahlung_bucht_den_vollen_betrag_und_laesst_das_guthaben_offen(umgebung):
    """Das Guthaben (27,50 beim Kreditor) bleibt als negativer Rest ein offener Posten
    — sonst wichen Personenkonto und Postenliste voneinander ab (Gesamttest B4)."""
    make_session, _ = umgebung
    posten = _mit_posten(make_session)
    zahlung = tx("-200.00")
    with make_session() as s:
        gleiche_aus(s, zahlung, [Anteil(posten, Decimal("200.00"))], EINSTELLUNGEN)
        s.commit()
        (p,) = lade_posten(s)
    (b,) = _zahlungs_und_skontobuchungen(make_session, zahlung)
    assert b.betrag_netto == Decimal("200.00")
    assert (p.restbetrag, p.status) == (Decimal("-27.50"), PostenStatus.TEILBEZAHLT)


def test_skonto_bei_steuerfreier_rechnung(umgebung):
    make_session, _ = umgebung
    beleg = eingangsrechnung(
        netto=Decimal("100.00"),
        steuer=Decimal("0.00"),
        brutto=Decimal("100.00"),
        skonto_prozent=Decimal("3"),
    )
    beleg.positionen = [
        Belegposition(
            beleg_id=beleg.id,
            bezeichnung="Buch",
            netto=Decimal("100.00"),
            steuersatz=Decimal("0"),
            steuer_betrag=Decimal("0.00"),
        )
    ]
    posten = _mit_posten(make_session, beleg)
    zahlung = tx("-97.00")
    with make_session() as s:
        gleiche_aus(
            s,
            zahlung,
            [Anteil(posten, Decimal("97.00"), Decimal("3.00"))],
            EINSTELLUNGEN,
        )
        s.commit()
    assert [
        _zeile(b) for b in _zahlungs_und_skontobuchungen(make_session, zahlung)
    ] == [
        ("70000", "1200", Decimal("97.00"), None, None),
        ("70000", "3730", Decimal("3.00"), None, None),
    ]


def test_ausgang_skonto_mit_umsatzsteuerkorrektur(umgebung):
    make_session, archiv = umgebung
    _ausgangsrechnung(
        make_session,
        archiv,
        entwurf(
            kunde(),
            pos("Bilderrahmen", "250", "4"),
            pos("Katalog", "25", ermaessigt=True),
            skonto_prozent=Decimal("2"),
            skonto_tage=7,
        ),
    )
    _verbuche(make_session, archiv=archiv)
    with make_session() as s:
        (posten,) = lade_posten(s)
    assert (posten.betrag, posten.skonto_betrag) == (
        Decimal("1216.75"),
        Decimal("24.34"),
    )
    zahlung = tx("1192.41", datum=date(2026, 3, 15))
    with make_session() as s:
        gleiche_aus(
            s,
            zahlung,
            [Anteil(posten, Decimal("1192.41"), Decimal("24.34"))],
            EINSTELLUNGEN,
        )
        s.commit()
        (p,) = lade_posten(s)
    assert [
        _zeile(b) for b in _zahlungs_und_skontobuchungen(make_session, zahlung)
    ] == [
        ("1200", "10000", Decimal("1192.41"), None, None),
        ("8731", "10000", Decimal("0.50"), 2, Decimal("0.04")),
        ("8736", "10000", Decimal("20.00"), 3, Decimal("3.80")),
    ]
    assert p.status is PostenStatus.AUSGEGLICHEN


def test_bereits_ausgeglichener_posten_wird_nicht_nochmal_ausgeglichen(umgebung):
    make_session, _ = umgebung
    posten = _mit_posten(make_session)
    with make_session() as s:
        gleiche_aus(
            s, tx("-172.50"), [Anteil(posten, Decimal("172.50"))], EINSTELLUNGEN
        )
        s.commit()
    with make_session() as s, pytest.raises(ValueError, match="ausgeglichen"):
        gleiche_aus(
            s, tx("-172.50"), [Anteil(posten, Decimal("172.50"))], EINSTELLUNGEN
        )


# --- Skonto auf § 13b und ig. Erwerb (Nachprüfung Merge M-2) -----------------------

SKR04 = Buchhaltung(
    kontenrahmen="SKR04",
    standard_aufwand="6300",
    skonto_erhalten={"19": "5736", "7": "5731", "0": "5730"},
)


def _beleg_ohne_steuer(positionen, kennzeichen, **kw):
    """Eingangsrechnung mit § 13b-Hinweis (AE) bzw. als ig. Lieferung (K)."""
    werte = {
        "netto": sum((Decimal(n) for _, n, _, _ in positionen), Decimal("0")),
        "steuer": sum((Decimal(st) for _, _, _, st in positionen), Decimal("0")),
        "zahlungsziel": None,
        "skonto_prozent": Decimal("2"),
        "skonto_tage": 10,
        **kw,
    }
    werte["brutto"] = werte["netto"] + werte["steuer"]
    b = eingangsrechnung(**werte)
    b = b.model_copy(update={"steuerkennzeichen": kennzeichen})
    b.positionen = [
        Belegposition(
            beleg_id=b.id,
            bezeichnung=text,
            netto=Decimal(n),
            steuersatz=Decimal(satz),
            steuer_betrag=Decimal(st),
        )
        for text, n, satz, st in positionen
    ]
    return b


def _skonto_und_voranmeldung(make_session, beleg, einstellungen, schluessel=None):
    """Verbuchen (``schluessel``: wie nach accounti korrigiere … --steuer), mit Skonto
    bezahlen — die Skontobuchungen und die Voranmeldung 03/2026."""
    from sqlalchemy import text

    from accounti.db.repository import lade_kontakte, setze_status
    from accounti.opos.verbuchung import verbuche_belege
    from accounti.steuer.kennziffern import STEUERSCHLUESSEL, Kontenplan, ermittle
    from accounti.steuer.zeitraum import Zeitraum

    with make_session() as s:
        speichere_beleg(s, beleg)
        s.commit()
    with make_session() as s:
        lauf = verbuche_belege(s, einstellungen)
        assert lauf.fehler == []
        for b in lade_buchungen(s):
            if schluessel is not None and b.steuer_schluessel in (19, 94):
                s.execute(
                    text(
                        "UPDATE buchungssaetze SET steuer_schluessel = :s, "
                        "steuer_betrag = :st WHERE id = :id"
                    ),
                    {
                        "s": schluessel,
                        "st": str(
                            b.betrag_netto * STEUERSCHLUESSEL[schluessel].satz / 100
                        ),
                        "id": str(b.id),
                    },
                )
        s.commit()
        (posten,) = lade_posten(s)
    zahlung = tx(str(-(posten.betrag - posten.skonto_betrag)), zweck="RE-2026-0042")
    with make_session() as s:
        gleiche_aus(
            s,
            zahlung,
            [
                Anteil(
                    posten, posten.betrag - posten.skonto_betrag, posten.skonto_betrag
                )
            ],
            einstellungen,
        )
        s.commit()
    skonto = [
        _zeile(b)
        for b in _zahlungs_und_skontobuchungen(make_session, zahlung)
        if b.haben_konto != "1200"
    ]
    with make_session() as s:
        for b in lade_buchungen(s):
            setze_status(s, str(b.id), BuchungStatus.GEPRUEFT)
        s.commit()
        e = ermittle(
            lade_buchungen(s),
            Zeitraum.lies("2026-03"),
            Kontenplan(kontenrahmen=einstellungen.kontenrahmen),
            lade_kontakte(s),
            {p.beleg_id: p.kontakt_id for p in lade_posten(s)},
        )
    return skonto, e.voranmeldung.werte


@pytest.mark.parametrize(
    ("einstellungen", "konto"), [(EINSTELLUNGEN, "3730"), (SKR04, "5730")]
)
def test_skonto_auf_13b_rechnung_mindert_bemessungsgrundlage_und_steuer(
    umgebung, einstellungen, konto
):
    """§ 13b-Rechnung über 600 € mit 2 % Skonto, gezahlt 588 €: Das Skonto mindert
    Bemessungsgrundlage, Steuer und Vorsteuer (§ 17 Abs. 1 Satz 1, 2 UStG) — mit
    demselben Schlüssel, die Steuer aus dem Netto. Vorher ohne Schlüssel: Kz 84/85/67
    blieben auf 600/114/114."""
    make_session, _ = umgebung
    beleg = _beleg_ohne_steuer([("Montage", "600.00", "0", "0.00")], "AE")
    skonto, werte = _skonto_und_voranmeldung(make_session, beleg, einstellungen)
    assert skonto == [("70000", konto, Decimal("12.00"), 94, Decimal("2.28"))]
    assert werte == {
        84: Decimal("588.00"),
        85: Decimal("111.72"),
        67: Decimal("111.72"),
    }


@pytest.mark.parametrize(
    ("kennzeichen", "schluessel", "steuer", "erwartet"),
    [
        ("AE", 91, "0.84", {84: "588.00", 85: "41.16", 67: "41.16"}),
        ("K", None, "2.28", {89: "588.00", 61: "111.72"}),
        ("K", 18, "0.84", {93: "588.00", 61: "41.16"}),
    ],
)
def test_skonto_auf_13b_7_prozent_und_ig_erwerb(
    umgebung, kennzeichen, schluessel, steuer, erwartet
):
    make_session, _ = umgebung
    lieferant = (
        {}
        if kennzeichen == "AE"
        else {
            "lieferant_name": "Fournisseur SARL",
            "lieferant_ust_id": "FR12345678901",
            "iban": "FR7630006000011234567890189",
        }
    )
    beleg = _beleg_ohne_steuer(
        [("Ware", "600.00", "0", "0.00")], kennzeichen, **lieferant
    )
    skonto, werte = _skonto_und_voranmeldung(
        make_session, beleg, EINSTELLUNGEN, schluessel
    )
    erwarteter_schluessel = schluessel or {"AE": 94, "K": 19}[kennzeichen]
    assert skonto == [
        ("70000", "3730", Decimal("12.00"), erwarteter_schluessel, Decimal(steuer))
    ]
    assert werte == {kz: Decimal(b) for kz, b in erwartet.items()}


def test_skonto_auf_gemischte_13b_rechnung_nach_zahlbetrag(umgebung):
    """§ 13b 600 € und 100 € + 19 % (Posten 719 €), Skonto 14,38 €: verteilt nach dem
    Zahlbetrag (600 : 119), nicht nach Netto plus selbst berechneter Steuer (714 : 119)
    — sonst war die Vorsteuerkorrektur 0,33 statt 0,38 € und Kz 66 um 0,05 € zu
    hoch."""
    make_session, _ = umgebung
    beleg = _beleg_ohne_steuer(
        [("Montage", "600.00", "0", "0.00"), ("Material", "100.00", "19", "19.00")],
        "AE",
    )
    skonto, werte = _skonto_und_voranmeldung(make_session, beleg, EINSTELLUNGEN)
    assert sorted(skonto) == [
        ("70000", "3730", Decimal("12.00"), 94, Decimal("2.28")),
        ("70000", "3736", Decimal("2.00"), 9, Decimal("0.38")),
    ]
    assert werte == {
        66: Decimal("18.62"),
        67: Decimal("111.72"),
        84: Decimal("588.00"),
        85: Decimal("111.72"),
    }
