from decimal import Decimal
from uuid import uuid4

from accounti.buchung.mit_beleg import kontiere_mit_beleg
from accounti.klassifikation.engine import Regel, RegelwerkEngine
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Belegposition,
    Belegrichtung,
    BuchungStatus,
    Kontakt,
)
from tests.test_bank_abgleich import quittung, umsatz

EINSTELLUNGEN = Buchhaltung()
TANKEN = Regel(
    name="tanken",
    muster=r"shell|aral",
    feld="gegenkonto_name",
    soll_konto="4530",
    haben_konto="1200",
    steuer_schluessel=9,
)
MIETE = Regel(
    name="miete",
    muster=r"miete",
    feld="verwendungszweck",
    soll_konto="4210",
    haben_konto="1200",
    steuer_schluessel=9,
)
REGELN = RegelwerkEngine([TANKEN, MIETE])


def mit_positionen(*positionen, **kw):
    b = quittung(**kw)
    return b.model_copy(
        update={
            "positionen": [
                Belegposition(
                    beleg_id=b.id,
                    bezeichnung=text,
                    netto=Decimal(netto),
                    steuersatz=Decimal(satz) if satz is not None else None,
                    steuer_betrag=Decimal(steuer),
                )
                for text, netto, satz, steuer in positionen
            ]
        }
    )


def _zeilen(buchungen):
    return [
        (
            b.soll_konto,
            b.haben_konto,
            b.betrag_netto,
            b.steuer_schluessel,
            b.steuer_betrag,
        )
        for b in buchungen
    ]


def test_je_steuersatz_eine_buchung_mit_vorsteuer_aus_dem_beleg():
    b = mit_positionen(
        ("Super E10", "50.00", "19", "9.50"),
        ("Snack", "10.00", "7", "0.70"),
        belegnummer="Q-0042-77",
        brutto="70.20",
    )
    tx = umsatz(betrag="-70.20")
    buchungen = kontiere_mit_beleg(tx, b, EINSTELLUNGEN, REGELN)
    assert _zeilen(buchungen) == [
        ("4530", "1200", Decimal("50.00"), 9, Decimal("9.50")),
        ("4530", "1200", Decimal("10.00"), 8, Decimal("0.70")),
    ]
    for x in buchungen:
        assert (x.transaktion_id, x.beleg_id) == (tx.id, b.id)
        assert x.status is BuchungStatus.AUTO_GEBUCHT
        assert x.datum == tx.datum
        assert x.beleg_nummer == "Q-0042-77"
        assert "Shell Station Kiel" in x.buchungstext


def test_sachkonto_aus_vorhandenem_kontakt():
    b = mit_positionen(
        ("Papier", "20.00", "19", "3.80"),
        lieferant_name="Bürobedarf Müller",
        brutto="23.80",
    )
    kontakt = Kontakt(name="Bürobedarf Müller GmbH", sachkonto="4930")
    (x,) = kontiere_mit_beleg(
        umsatz(betrag="-23.80"), b, EINSTELLUNGEN, REGELN, kontakte=[kontakt]
    )
    assert (x.soll_konto, x.status) == ("4930", BuchungStatus.AUTO_GEBUCHT)


def test_regel_auf_den_umsatz_als_rueckfall():
    b = mit_positionen(
        ("März", "500.00", "19", "95.00"),
        lieferant_name="Hausverwaltung Ost",
        brutto="595",
    )
    tx = umsatz(betrag="-595.00", verwendungszweck="Miete März", gegenkonto_name="HV")
    (x,) = kontiere_mit_beleg(tx, b, EINSTELLUNGEN, REGELN)
    assert (x.soll_konto, x.status) == ("4210", BuchungStatus.AUTO_GEBUCHT)


def test_ohne_regel_standardaufwand_zur_pruefung():
    b = mit_positionen(
        ("Ding", "10.00", "19", "1.90"), lieferant_name="X", brutto="11.90"
    )
    tx = umsatz(betrag="-11.90", verwendungszweck="SUMUP", gegenkonto_name="SumUp")
    (x,) = kontiere_mit_beleg(tx, b, EINSTELLUNGEN, REGELN)
    assert (x.soll_konto, x.status) == ("4900", BuchungStatus.ZUR_PRUEFUNG)


def test_trinkgeld_ohne_vorsteuer_zur_pruefung():
    b = mit_positionen(("Essen", "41.85", "19", "7.95"), brutto="49.80")
    (x,) = kontiere_mit_beleg(umsatz(betrag="-55.00"), b, EINSTELLUNGEN, REGELN)
    assert _zeilen([x]) == [("4530", "1200", Decimal("47.05"), 9, Decimal("7.95"))]
    assert x.status is BuchungStatus.ZUR_PRUEFUNG


def test_gutschrift_korrigiert_die_vorsteuer():
    b = mit_positionen(("Erstattung", "-16.80", "19", "-3.19"), brutto="-19.99")
    (x,) = kontiere_mit_beleg(umsatz(betrag="19.99"), b, EINSTELLUNGEN, REGELN)
    assert _zeilen([x]) == [("1200", "4530", Decimal("16.80"), 9, Decimal("3.19"))]


def test_gutschrift_findet_das_konto_ueber_eine_ausgaberegel():
    """Ausgaberegeln mit Richtung (Gesamttest B07) liefern das Aufwandskonto auch
    für die Gutschrift, die denselben Aufwand mindert."""
    tanken = Regel(
        name="tanken",
        muster=r"shell|aral",
        feld="gegenkonto_name",
        soll_konto="4530",
        haben_konto="1200",
        steuer_schluessel=9,
        richtung="ausgabe",
    )
    b = mit_positionen(("Erstattung", "-16.80", "19", "-3.19"), brutto="-19.99")
    (x,) = kontiere_mit_beleg(
        umsatz(betrag="19.99"), b, EINSTELLUNGEN, RegelwerkEngine([tanken])
    )
    assert _zeilen([x]) == [("1200", "4530", Decimal("16.80"), 9, Decimal("3.19"))]


def test_ohne_positionen_aus_den_belegsummen():
    b = quittung(netto=Decimal("50.00"), steuer=Decimal("9.50"))
    (x,) = kontiere_mit_beleg(umsatz(), b, EINSTELLUNGEN, REGELN)
    assert _zeilen([x]) == [("4530", "1200", Decimal("50.00"), 9, Decimal("9.50"))]


def test_ohne_steuerangaben_zur_pruefung():
    (x,) = kontiere_mit_beleg(umsatz(), quittung(), EINSTELLUNGEN, REGELN)
    assert _zeilen([x]) == [("4530", "1200", Decimal("59.50"), None, None)]
    assert x.status is BuchungStatus.ZUR_PRUEFUNG


def test_unbekannter_steuersatz_brutto_zur_pruefung():
    b = mit_positionen(("Hotel AT", "100.00", "10", "10.00"), brutto="110.00")
    (x,) = kontiere_mit_beleg(umsatz(betrag="-110.00"), b, EINSTELLUNGEN, REGELN)
    assert _zeilen([x]) == [("4530", "1200", Decimal("110.00"), None, None)]
    assert x.status is BuchungStatus.ZUR_PRUEFUNG


def test_steuerfrei_ohne_pruefung():
    b = mit_positionen(("Briefmarken", "8.50", "0", "0"), brutto="8.50")
    (x,) = kontiere_mit_beleg(umsatz(betrag="-8.50"), b, EINSTELLUNGEN, REGELN)
    assert _zeilen([x]) == [("4530", "1200", Decimal("8.50"), None, None)]
    assert x.status is BuchungStatus.AUTO_GEBUCHT


def test_ausgangsbeleg_bucht_erloese():
    b = mit_positionen(
        ("Rahmen", "100.00", "19", "19.00"),
        ("Katalog", "20.00", "7", "1.40"),
        richtung=Belegrichtung.AUSGANG,
        brutto="140.40",
        datei_hash=uuid4().hex * 2,
    )
    buchungen = kontiere_mit_beleg(umsatz(betrag="140.40"), b, EINSTELLUNGEN, REGELN)
    assert _zeilen(buchungen) == [
        ("1200", "8400", Decimal("100.00"), 3, Decimal("19.00")),
        ("1200", "8300", Decimal("20.00"), 2, Decimal("1.40")),
    ]
    assert all(x.status is BuchungStatus.AUTO_GEBUCHT for x in buchungen)
