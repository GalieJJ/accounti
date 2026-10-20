"""Zahllast als offener Posten gegenüber dem Finanzamt (Akzeptanz 5)."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import session_factory
from accounti.db.repository import (
    lade_beleg,
    lade_belegbuchungen,
    lade_buchungen,
    lade_einen_posten,
    lade_kontakte,
    lade_posten,
    speichere_buchung,
    speichere_transaktion,
)
from accounti.elster.freigabe import gib_frei
from accounti.elster.konfiguration import lade_elster
from accounti.elster.ustva import bereite_vor, hat_testlauf, uebermittle
from accounti.elster.zahllast import buche_fehlende, buche_zahllast
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Belegart,
    PostenRichtung,
    PostenStatus,
    Transaktion,
    TransaktionQuelle,
)
from accounti.models.elster import Meldeart, Modus
from accounti.opos.auswertung import faelligkeitsstaffel, offene_posten
from accounti.opos.zahlungslauf import zuordne_zahlungen
from accounti.steuer.zeitraum import Zeitraum
from tests.elster_hilfe import EricDoppel
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
        if not hat_testlauf(s, Meldeart.USTVA, "eric"):
            abgeben(s, einstellungen, archiv, Modus.PRUEFUNG, buchhaltung)
    u = uebermittle(
        s, v, modus=modus, kontext=KONTEXT, uebermittler=EricDoppel(),
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


def test_erstattung_ist_eine_forderung_gegen_das_finanzamt(db):
    make_session, einstellungen, archiv = db
    with make_session() as s:
        speichere_buchung(s, buchung("0420", "70001", "20000.00", 9, "3800.00"))
        s.commit()
        z = zahllast(s, abgeben(s, einstellungen, archiv), einstellungen)
        (b,) = lade_belegbuchungen(s, z.beleg.id)
    assert z.betrag == Decimal("-1654.82")  # 2.145,18 − 3.800,00
    assert z.posten.richtung is PostenRichtung.FORDERUNG
    assert (z.posten.betrag, z.posten.restbetrag) == (Decimal("1654.82"),) * 2
    assert (b.soll_konto, b.haben_konto) == ("70003", "1780")


# --- Ausgleich über den Kontoumsatz (Spec 4.6) --------------------------------------

FA_IBAN = "DE12500105170648489890"


def mit_iban(einstellungen):
    finanzamt = einstellungen.finanzamt.model_copy(update={"iban": FA_IBAN})
    return einstellungen.model_copy(update={"finanzamt": finanzamt})


def kontoumsatz(s, betrag, zweck):
    tx = Transaktion(
        datum=date(2026, 9, 10),
        betrag=Decimal(betrag),
        verwendungszweck=zweck,
        gegenkonto_name="Finanzamt München",
        gegenkonto_iban=FA_IBAN,
        quelle=TransaktionQuelle.BANK,
        rohtext=zweck,
    )
    speichere_transaktion(s, tx)
    s.commit()
    lauf = zuordne_zahlungen(s, Buchhaltung())
    s.commit()
    return tx, lauf


def test_lastschrift_gleicht_die_zahllast_aus(db):
    make_session, einstellungen, archiv = db
    einstellungen = mit_iban(einstellungen)
    with make_session() as s:
        z = zahllast(s, abgeben(s, einstellungen, archiv), einstellungen)
        tx, lauf = kontoumsatz(
            s, "-2145.18", "SEPA-Lastschrift USt 08/2026 9181081508155"
        )
        posten = lade_einen_posten(s, z.posten.id)
        buchungen = [b for b in lade_buchungen(s) if b.transaktion_id == tx.id]
    assert [t.id for t, _ in lauf.gebucht] == [tx.id]
    assert posten.status is PostenStatus.AUSGEGLICHEN and posten.restbetrag == 0
    assert [(b.soll_konto, b.haben_konto) for b in buchungen] == [("70003", "1200")]


def test_erstattung_wird_ueber_den_kontoumsatz_ausgeglichen(db):
    make_session, einstellungen, archiv = db
    einstellungen = mit_iban(einstellungen)
    with make_session() as s:
        speichere_buchung(s, buchung("0420", "70001", "20000.00", 9, "3800.00"))
        s.commit()
        z = zahllast(s, abgeben(s, einstellungen, archiv), einstellungen)
        tx, lauf = kontoumsatz(s, "1654.82", "Erstattung UStVA 2026-08")
        posten = lade_einen_posten(s, z.posten.id)
        buchungen = [b for b in lade_buchungen(s) if b.transaktion_id == tx.id]
    assert [t.id for t, _ in lauf.gebucht] == [tx.id]
    assert posten.status is PostenStatus.AUSGEGLICHEN
    assert [(b.soll_konto, b.haben_konto) for b in buchungen] == [("1200", "70003")]


def test_berichtigung_nach_unten_verrechnet_den_offenen_posten(db):
    make_session, einstellungen, archiv = db
    einstellungen = mit_iban(einstellungen)
    with make_session() as s:
        erste = zahllast(s, abgeben(s, einstellungen, archiv), einstellungen)
        speichere_buchung(s, buchung("4930", "70001", "500.00", 9, "95.00"))
        s.commit()
        zweite = zahllast(s, abgeben(s, einstellungen, archiv), einstellungen)
        alle = lade_posten(s)
        _, lauf = kontoumsatz(s, "-2050.18", "SEPA-Lastschrift USt 08/2026")
        nachher = lade_einen_posten(s, erste.posten.id)
    assert zweite.betrag == Decimal("-95.00") and zweite.posten is None
    assert zweite.verrechnet == Decimal("95.00")
    (posten,) = alle  # kein negativer Posten daneben
    assert posten.richtung is PostenRichtung.VERBINDLICHKEIT
    assert posten.restbetrag == Decimal("2050.18")
    assert len(lauf.gebucht) == 1 and nachher.status is PostenStatus.AUSGEGLICHEN


def test_berichtigung_nach_unten_nach_der_zahlung_ist_eine_erstattung(db):
    make_session, einstellungen, archiv = db
    einstellungen = mit_iban(einstellungen)
    with make_session() as s:
        zahllast(s, abgeben(s, einstellungen, archiv), einstellungen)
        kontoumsatz(s, "-2145.18", "SEPA-Lastschrift USt 08/2026")
        speichere_buchung(s, buchung("4930", "70001", "500.00", 9, "95.00"))
        s.commit()
        zweite = zahllast(s, abgeben(s, einstellungen, archiv), einstellungen)
    assert zweite.verrechnet == 0
    assert zweite.posten.richtung is PostenRichtung.FORDERUNG
    assert zweite.posten.betrag == Decimal("95.00")


def test_fehlende_zahllast_wird_nachgebucht(db):
    make_session, einstellungen, archiv = db
    with make_session() as s:
        u = abgeben(s, einstellungen, archiv)  # Buchung danach gescheitert
        nachgeholt = buche_fehlende(
            s, buchhaltung=Buchhaltung(), einstellungen=einstellungen,
            steuernummer=KONTEXT.steuernummer,
        )  # fmt: skip
        s.commit()
        noch_einmal = buche_fehlende(
            s, buchhaltung=Buchhaltung(), einstellungen=einstellungen,
            steuernummer=KONTEXT.steuernummer,
        )  # fmt: skip
    assert [z.betrag for z in nachgeholt] == [Decimal("2145.18")]
    assert u.nr == 2 and noch_einmal == []


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
