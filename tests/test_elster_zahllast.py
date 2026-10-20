"""Zahllast als offener Posten gegenüber dem Finanzamt (Akzeptanz 5)."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import session_factory
from accounti.db.repository import (
    lade_beleg,
    lade_belegbuchungen,
    lade_kontakte,
    lade_posten,
    speichere_buchung,
)
from accounti.elster.freigabe import gib_frei
from accounti.elster.konfiguration import lade_elster
from accounti.elster.uebermittlung import AttrappenUebermittler
from accounti.elster.ustva import bereite_vor, uebermittle
from accounti.elster.zahllast import buche_zahllast
from accounti.konfiguration import Buchhaltung
from accounti.models import Belegart, PostenRichtung
from accounti.models.elster import Modus
from accounti.opos.auswertung import faelligkeitsstaffel, offene_posten
from accounti.steuer.zeitraum import Zeitraum
from tests.test_cli_ustva import buchung, umgebung
from tests.test_elster_ustva import KONTEXT

AUGUST = Zeitraum.lies("2026-08")
JETZT = datetime(2026, 9, 7, 10, 30)


@pytest.fixture
def db(tmp_path):
    url, konfig = umgebung(tmp_path)
    engine, make_session = session_factory(url)
    yield make_session, lade_elster(konfig), BelegArchiv(tmp_path / "archiv")
    engine.dispose()


def abgeben(s, einstellungen, archiv, modus=Modus.ECHT, buchhaltung=None):
    buchhaltung = buchhaltung or Buchhaltung()
    v = bereite_vor(s, AUGUST, buchhaltung=buchhaltung, einstellungen=einstellungen)
    if modus is Modus.ECHT:
        gib_frei(s, v, "Erika Muster", jetzt=JETZT)
    u = uebermittle(
        s, v, modus=modus, kontext=KONTEXT, uebermittler=AttrappenUebermittler(),
        archiv=archiv, jetzt=JETZT,
    )  # fmt: skip
    s.commit()
    return u


def zahllast(s, u, einstellungen, buchhaltung=None):
    z = buche_zahllast(
        s,
        u,
        buchhaltung=buchhaltung or Buchhaltung(),
        einstellungen=einstellungen,
        steuernummer=KONTEXT.steuernummer,
    )
    s.commit()
    return z


def test_akzeptanz_5_zahllast_als_offener_posten_beim_finanzamt(db):
    make_session, einstellungen, archiv = db
    with make_session() as s:
        u = abgeben(s, einstellungen, archiv)
        z = zahllast(s, u, einstellungen)
        (posten,) = lade_posten(s)
        finanzamt = next(k for k in lade_kontakte(s) if k.id == posten.kontakt_id)
        beleg = lade_beleg(s, posten.beleg_id)
        (b,) = lade_belegbuchungen(s, beleg.id)
    assert z is not None and z.betrag == Decimal("2145.18")
    assert finanzamt.name == "Finanzamt München"
    assert finanzamt.kreditor_konto == "70003"  # nächstes freies Kreditorenkonto
    assert posten.richtung is PostenRichtung.VERBINDLICHKEIT
    assert (posten.betrag, posten.restbetrag) == (Decimal("2145.18"),) * 2
    assert posten.faellig_am == date(2026, 9, 10)  # 10. des Folgemonats
    assert posten.belegnummer == "UStVA 2026-08"
    # Eigenbeleg: der übermittelte Datensatz aus dem Archiv
    assert beleg.belegart is Belegart.SONSTIGES and beleg.kanal == "elster"
    assert beleg.datei_hash == u.datensatz_hash
    assert (b.soll_konto, b.haben_konto, b.betrag_netto) == (
        "1780",
        "70003",
        Decimal("2145.18"),
    )
    assert b.steuer_schluessel is None
    assert offene_posten([posten]) == [posten]
    staffel = faelligkeitsstaffel([posten], date(2026, 9, 7))
    assert staffel["nicht fällig"] == Decimal("2145.18")


def test_berichtigung_bucht_die_differenz(db):
    make_session, einstellungen, archiv = db
    with make_session() as s:
        zahllast(s, abgeben(s, einstellungen, archiv), einstellungen)
        speichere_buchung(s, buchung("10001", "8400", "100.00", 3, "19.00"))
        s.commit()
        zweite = zahllast(s, abgeben(s, einstellungen, archiv), einstellungen)
        alle = lade_posten(s)
    assert zweite.betrag == Decimal("19.00")  # 2.164,18 − 2.145,18
    assert sorted(p.betrag for p in alle) == [Decimal("19.00"), Decimal("2145.18")]
    assert {p.kontakt_id for p in alle} == {zweite.kontakt.id}  # ein Finanzamt
    assert "berichtigt" in zweite.posten.belegnummer


def test_erstattung_ist_ein_negativer_posten(db):
    make_session, einstellungen, archiv = db
    with make_session() as s:
        speichere_buchung(s, buchung("0420", "70001", "20000.00", 9, "3800.00"))
        s.commit()
        z = zahllast(s, abgeben(s, einstellungen, archiv), einstellungen)
        (b,) = lade_belegbuchungen(s, z.beleg.id)
    assert z.betrag == Decimal("-1654.82")  # 2.145,18 − 3.800,00
    assert z.posten.betrag == Decimal("-1654.82")
    assert (b.soll_konto, b.haben_konto) == ("70003", "1780")


def test_nur_nach_echter_erfolgreicher_abgabe_und_nur_einmal(db):
    make_session, einstellungen, archiv = db
    with make_session() as s:
        test = abgeben(s, einstellungen, archiv, modus=Modus.PRUEFUNG)
        assert zahllast(s, test, einstellungen) is None
        echt = abgeben(s, einstellungen, archiv)
        assert zahllast(s, echt, einstellungen) is not None
        assert zahllast(s, echt, einstellungen) is None
        assert len(lade_posten(s)) == 1


def test_skr04_und_dauerfristverlaengerung(db):
    make_session, einstellungen, archiv = db
    einstellungen = einstellungen.model_copy(update={"dauerfristverlaengerung": True})
    skr04 = Buchhaltung(kontenrahmen="SKR04")
    with make_session() as s:
        z = zahllast(s, abgeben(s, einstellungen, archiv), einstellungen, skr04)
        (b,) = lade_belegbuchungen(s, z.beleg.id)
    assert b.soll_konto == "3820"
    assert z.posten.faellig_am == date(2026, 10, 12)  # 10.10.2026 ist ein Samstag


def test_finanzamt_mit_iban_wird_wiedergefunden(db):
    make_session, einstellungen, archiv = db
    einstellungen = einstellungen.model_copy(
        update={
            "finanzamt": einstellungen.finanzamt.model_copy(
                update={"iban": "DE12500105170648489890"}
            )
        }
    )
    with make_session() as s:
        z = zahllast(s, abgeben(s, einstellungen, archiv), einstellungen)
        speichere_buchung(s, buchung("10001", "8400", "100.00", 3, "19.00"))
        s.commit()
        zweite = zahllast(s, abgeben(s, einstellungen, archiv), einstellungen)
    assert z.kontakt.iban == "DE12500105170648489890"
    assert zweite.kontakt.id == z.kontakt.id
