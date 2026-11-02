from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from accounti.erechnung import lies
from accounti.erechnung.abbildung import zu_beleg
from accounti.erechnung.validierung import pruefe
from accounti.models import Beleg, Belegart, Belegrichtung, BelegStatus

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "erechnung"


def _leer():
    return Beleg(
        datei_hash="a" * 64,
        dateiname="r.xml",
        kanal="upload",
        herkunft="x",
        aufbewahren_bis=date(2036, 12, 31),
    )


def _beleg(name, **kw):
    r = lies((FIXTURES / name).read_bytes())
    return r, zu_beleg(r, pruefe(r), _leer(), **kw)


def _steuer_je_satz(beleg):
    summe = defaultdict(Decimal)
    for p in beleg.positionen:
        summe[p.steuersatz.normalize()] += p.steuer_betrag
    return dict(summe)


def test_xrechnung_wird_vollstaendig_uebernommen():
    """Akzeptanz 1."""
    _, b = _beleg("xrechnung_cii.xml")
    assert b.status is BelegStatus.ERFASST
    assert b.pruef_grund is None
    assert b.confidence == 1.0
    assert b.belegart is Belegart.EINGANGSRECHNUNG
    assert b.belegnummer == "RE-2026-0042"
    assert b.belegdatum == date(2026, 3, 5)
    assert b.leistungsdatum == date(2026, 3, 3)
    assert (b.lieferant_name, b.lieferant_ust_id) == (
        "Bürobedarf Müller GmbH",
        "DE123456789",
    )
    assert (b.netto, b.steuer, b.brutto) == (
        Decimal("150.00"),
        Decimal("22.50"),
        Decimal("172.50"),
    )
    assert b.zahlungsziel == date(2026, 3, 19)
    assert (b.skonto_prozent, b.skonto_tage) == (Decimal("2.00"), 7)
    assert [(p.bezeichnung, p.menge, p.netto, p.steuersatz) for p in b.positionen] == [
        ("Kopierpapier A4, 500 Blatt", Decimal("10"), Decimal("85.00"), Decimal("19")),
        ("Ordner breit", Decimal("10"), Decimal("15.00"), Decimal("19")),
        ("Fachbuch Steuerrecht", Decimal("1"), Decimal("50.00"), Decimal("7")),
    ]
    assert _steuer_je_satz(b) == {
        Decimal("19"): Decimal("19.00"),
        Decimal("7"): Decimal("3.50"),
    }
    assert all(p.beleg_id == b.id for p in b.positionen)


def test_rundungsdifferenz_landet_in_einer_position():
    r = lies((FIXTURES / "xrechnung_cii.xml").read_bytes())
    # drei Positionen à 33,33 zu 19 % → 6,33 je Position, ausgewiesen 19,00 auf 99,99
    for z in r.zeilen:
        z.netto, z.steuerkategorie, z.steuersatz = Decimal("33.33"), "S", Decimal("19")
    r.steuern = r.steuern[:1]
    r.steuern[0].basis, r.steuern[0].betrag = Decimal("99.99"), Decimal("19.00")
    b = zu_beleg(r, [], _leer())
    assert sorted(p.steuer_betrag for p in b.positionen) == [
        Decimal("6.33"),
        Decimal("6.33"),
        Decimal("6.34"),
    ]


def test_nachlass_und_zuschlag_als_positionen():
    r, b = _beleg("mit_nachlass_cii.xml")
    assert b.status is BelegStatus.ERFASST
    bezeichnungen = [p.bezeichnung for p in b.positionen]
    assert "Nachlass: Treuerabatt" in bezeichnungen
    assert "Zuschlag: Versand" in bezeichnungen
    assert sum(p.netto for p in b.positionen) == r.summen.netto
    assert _steuer_je_satz(b) == {
        Decimal("19"): Decimal("18.22"),
        Decimal("7"): Decimal("3.50"),
    }


def test_fehler_gehen_zur_pruefung_mit_lesbarem_befund():
    """Akzeptanz 3."""
    _, b = _beleg("fehler_rechenprobe_cii.xml")
    assert b.status is BelegStatus.ZUR_PRUEFUNG
    assert "BR-S-09" in b.pruef_grund
    assert "Steuerbetrag" in b.pruef_grund


def test_reduziertes_profil_geht_zur_pruefung():
    """B05 (Gesamttest): MINIMUM ist keine Rechnung nach § 14 Abs. 4 UStG — der
    Mensch prüft die PDF-Ansicht, bevor gebucht wird (früher: „erfasst“)."""
    _, b = _beleg("minimum_cii.xml")
    assert b.status is BelegStatus.ZUR_PRUEFUNG
    assert "PROFIL" in b.pruef_grund and "belege freigeben" in b.pruef_grund
    # ohne Positionen: eine Sammelposition über die Nettosumme
    (p,) = b.positionen
    assert (p.netto, p.steuer_betrag) == (Decimal("1000.00"), Decimal("190.00"))


def test_reverse_charge_position_mit_satz_null():
    _, b = _beleg("reverse_charge_ohne_ust_id_ubl.xml")
    assert b.status is BelegStatus.ZUR_PRUEFUNG
    assert b.steuerkennzeichen == "AE"
    assert b.leistungsdatum == date(2026, 3, 10)
    (p,) = b.positionen
    assert (p.steuersatz, p.steuer_betrag) == (Decimal("0"), Decimal("0.00"))


def test_eigene_ust_id_macht_ausgangsrechnung():
    _, b = _beleg("xrechnung_cii.xml", eigene_ust_ids={"DE123456789"})
    assert b.belegart is Belegart.AUSGANGSRECHNUNG
    assert b.richtung is Belegrichtung.AUSGANG


def test_gutschrift_mit_negativen_betraegen():
    r = lies((FIXTURES / "xrechnung_cii.xml").read_bytes())
    r.typ = "381"
    b = zu_beleg(r, [], _leer())
    assert b.brutto == Decimal("-172.50")
    assert sum(p.netto for p in b.positionen) == Decimal("-150.00")
