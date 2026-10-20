"""Kassenbuch: laufende Nummer, Bestand, Ablehnung negativer Bestände (Akzeptanz 4)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import update

from accounti.abschluss.kassenbuch import (
    KassenbuchError,
    KasseNegativError,
    anfangsbestand,
    bestand,
    buche_kasse,
    storniere,
    tagessalden,
    verlauf,
)
from accounti.abschluss.konfiguration import KassenEinstellungen
from accounti.db.repo_kasse import lade_kassenbuch
from accounti.db.repository import lade_buchungen, lade_transaktionen
from accounti.db.tabellen import UnveraenderbarError
from accounti.db.tabellen_kasse import KassenvorgangRow
from accounti.models import BuchungStatus
from tests.abschluss_hilfe import datenbank

D = Decimal
KASSE = KassenEinstellungen(konto="1000")


@pytest.fixture
def make_session(tmp_path):
    yield from datenbank(tmp_path)


def _buche(make_session, betrag, tag, text="Vorgang", **kw):
    with make_session() as s:
        v = buche_kasse(s, D(betrag), text, KASSE, datum=tag, **kw)
        s.commit()
    return v


def _start(make_session, betrag="100", tag=date(2026, 3, 1)):
    with make_session() as s:
        anfangsbestand(s, D(betrag), tag, KASSE)
        s.commit()


def _bestand(make_session, bis=None):
    with make_session() as s:
        return bestand(lade_kassenbuch(s), bis)


def test_akzeptanz_4_negativer_bestand_wird_abgelehnt(make_session):
    _start(make_session)
    _buche(make_session, "-24.90", date(2026, 3, 2), "Porto")
    assert _bestand(make_session) == D("75.10")
    with pytest.raises(KasseNegativError, match="−4,90"):
        _buche(make_session, "-80.00", date(2026, 3, 3), "Druckerpatronen")
    # nichts gespeichert: kein Eintrag, keine Transaktion
    assert _bestand(make_session) == D("75.10")
    with make_session() as s:
        assert len(lade_kassenbuch(s)) == 2
        assert len(lade_transaktionen(s)) == 1


def test_rueckdatierte_ausgabe_die_spaeter_ins_minus_fuehrt(make_session):
    _start(make_session)
    _buche(make_session, "-90", date(2026, 3, 10))
    # am 05.03. wären noch 50 € da, aber am 10.03. −40 €
    with pytest.raises(KasseNegativError, match="10.03.2026"):
        _buche(make_session, "-50", date(2026, 3, 5))
    _buche(make_session, "30", date(2026, 3, 5), "Bareinnahme")
    _buche(make_session, "-40", date(2026, 3, 5))
    assert _bestand(make_session) == 0


def test_ohne_anfangsbestand_ist_jede_ausgabe_zu_viel(make_session):
    with pytest.raises(KasseNegativError):
        _buche(make_session, "-1", date(2026, 1, 2))
    with pytest.raises(KassenbuchError, match="0"):
        _buche(make_session, "0", date(2026, 1, 2))


def test_laufende_nummer_verlauf_und_tagessalden(make_session):
    _start(make_session)
    _buche(make_session, "50", date(2026, 3, 2), "Einnahme")
    _buche(make_session, "-20", date(2026, 3, 2), "Ausgabe")
    _buche(make_session, "-5", date(2026, 3, 1), "Nachtrag")  # rückdatiert, Nr. 4
    with make_session() as s:
        buch = lade_kassenbuch(s)
    assert [v.nr for v in buch] == [1, 2, 3, 4]
    assert [(v.nr, b) for v, b in verlauf(buch)] == [
        (1, D("100")),
        (4, D("95")),
        (2, D("145")),
        (3, D("125")),
    ]
    assert _bestand(make_session, date(2026, 3, 1)) == D("95")
    tage = tagessalden(buch, date(2026, 3, 1), date(2026, 3, 31))
    assert [(t.datum, t.einnahmen, t.ausgaben, t.bestand) for t in tage] == [
        (date(2026, 3, 1), D("100"), D("5"), D("95")),
        (date(2026, 3, 2), D("50"), D("20"), D("125")),
    ]


def test_transaktion_und_buchung_mit_steuer(make_session):
    _start(make_session, "500")
    aus = _buche(
        make_session,
        "-119",
        date(2026, 3, 2),
        "Bürobedarf",
        gegenkonto="4930",
        steuersatz=D("19"),
        belegnummer="Q-1",
    )
    ein = _buche(
        make_session,
        "119",
        date(2026, 3, 3),
        "Barverkauf",
        gegenkonto="8400",
        steuersatz=D("19"),
    )
    ohne = _buche(make_session, "-10", date(2026, 3, 4), "Trinkgeld")
    with make_session() as s:
        txs = {t.id: t for t in lade_transaktionen(s)}
        buchungen = {b.transaktion_id: b for b in lade_buchungen(s)}
    t = txs[aus.transaktion_id]
    assert (t.betrag, t.sachkonto, t.verwendungszweck) == (
        D("-119"),
        "1000",
        "Bürobedarf",
    )
    b = buchungen[aus.transaktion_id]
    assert (b.soll_konto, b.haben_konto, b.betrag_netto, b.steuer_schluessel) == (
        "4930",
        "1000",
        D("100.00"),
        9,
    )
    assert b.steuer_betrag == D("19.00") and b.status is BuchungStatus.GEPRUEFT
    assert b.beleg_nummer == "Q-1"
    e = buchungen[ein.transaktion_id]
    assert (e.soll_konto, e.haben_konto, e.betrag_netto, e.steuer_schluessel) == (
        "1000",
        "8400",
        D("100.00"),
        3,
    )
    # ohne Gegenkonto: nur die Transaktion — die Kontierung macht 'classify'
    assert ohne.transaktion_id in txs and ohne.transaktion_id not in buchungen


def test_unveraenderbar(make_session):
    _start(make_session)
    with make_session() as s:
        row = s.get(KassenvorgangRow, str(lade_kassenbuch(s)[0].id))
        row.betrag = D("1000")
        with pytest.raises(UnveraenderbarError):
            s.flush()
    with make_session() as s:
        s.delete(s.get(KassenvorgangRow, str(lade_kassenbuch(s)[0].id)))
        with pytest.raises(UnveraenderbarError):
            s.flush()
    with make_session() as s, pytest.raises(Exception, match="unveränderbar"):
        s.execute(update(KassenvorgangRow).values(text="geändert"))


def test_storno(make_session):
    _start(make_session)
    einnahme = _buche(make_session, "50", date(2026, 3, 2), "Einnahme")
    ausgabe = _buche(
        make_session, "-120", date(2026, 3, 3), "Ausgabe", gegenkonto="4930"
    )
    # Storno der Einnahme ließe den Bestand am 03.03. ins Minus fallen
    with make_session() as s, pytest.raises(KasseNegativError):
        storniere(s, einnahme.nr, "falsch erfasst", KASSE)
    with make_session() as s:
        st = storniere(s, ausgabe.nr, "doppelt erfasst", KASSE, datum=date(2026, 3, 4))
        s.commit()
    assert (st.betrag, st.storno_von) == (D("120"), ausgabe.nr)
    assert _bestand(make_session) == D("150")
    with make_session() as s:
        gegen = [b for b in lade_buchungen(s) if b.transaktion_id == st.transaktion_id]
    assert [(b.soll_konto, b.haben_konto, b.betrag_netto) for b in gegen] == [
        ("1000", "4930", D("120"))
    ]
    with make_session() as s, pytest.raises(KassenbuchError, match="schon storniert"):
        storniere(s, ausgabe.nr, "nochmal", KASSE)


def test_anfangsbestand_nur_einmal(make_session):
    _start(make_session)
    with make_session() as s, pytest.raises(KassenbuchError, match="Anfangsbestand"):
        anfangsbestand(s, D("10"), date(2026, 4, 1), KASSE)
