"""Rückfragen und Kommentare am Beleg — auch ohne Aufgabe (Akzeptanz 4)."""

from datetime import timedelta
from decimal import Decimal

import pytest

from accounti.aufgaben import (
    AufgabenError,
    aufgaben_zu,
    erledige,
    halte_rueckfrage_fest,
    kommentare_zu,
    kommentiere,
    melde_aufgabe,
)
from accounti.aufgaben.objekte import beschreibe, loese_auf, registriere_objekttyp
from accounti.db import init_db, session_factory
from accounti.db.repo_aufgaben import lade_kommentare
from accounti.db.repository import (
    speichere_bankkonto,
    speichere_beleg,
    speichere_buchung,
    speichere_kontakt,
    speichere_transaktion,
)
from accounti.db.tabellen import UnveraenderbarError
from accounti.db.tabellen_aufgaben import KommentarRow
from accounti.models import Bankkonto, Kontakt
from accounti.models.aufgaben import AufgabenStatus, KommentarArt, Objekt
from tests.aufgaben_hilfe import JETZT, buchung
from tests.test_bank_abgleich import quittung, umsatz


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'r.db'}")
    init_db(engine)
    yield factory
    engine.dispose()


@pytest.fixture
def beleg(make_session):
    b = quittung(belegnummer="Q-2026-00042", dateiname="shell.jpg")
    with make_session() as s:
        speichere_beleg(s, b)
        s.commit()
    return b


def test_rueckfrage_am_beleg_ohne_aufgabe_ist_spaeter_auffindbar(make_session, beleg):
    """Akzeptanz 4."""
    objekt = Objekt("beleg", beleg.id)
    with make_session() as s:
        r = halte_rueckfrage_fest(
            s, objekt, "Ist das Tanken privat oder betrieblich?", "jan", jetzt=JETZT
        )
        s.commit()
    assert r.aufgabe is None and r.kommentar.art is KommentarArt.RUECKFRAGE
    # später, neue Sitzung, nur über den Beleg gesucht
    with make_session() as s:
        (gefunden,) = kommentare_zu(s, Objekt("beleg", str(beleg.id)))
        assert aufgaben_zu(s, objekt) == []
    assert gefunden.text == "Ist das Tanken privat oder betrieblich?"
    assert (gefunden.autor, gefunden.erstellt_am) == ("jan", JETZT)
    assert gefunden.aufgabe_id is None


def test_rueckfrage_mit_aufgabe_und_antwort(make_session, beleg):
    objekt = Objekt("beleg", beleg.id)
    with make_session() as s:
        r = halte_rueckfrage_fest(
            s,
            objekt,
            "Bitte Bewirtungsanlass nachreichen",
            "erika",
            an="jan",
            jetzt=JETZT,
        )
        assert r.aufgabe is not None and r.aufgabe.art == "rueckfrage"
        assert r.aufgabe.zustaendig == "jan" and r.aufgabe.objekt == objekt
        assert r.kommentar.aufgabe_id == r.aufgabe.id
        kommentiere(s, "Geschäftsessen mit Kunde Müller", "jan", aufgabe="1")
        erledige(s, "1", von="jan")
        # eine neue Rückfrage öffnet dieselbe Aufgabe wieder
        zweite = halte_rueckfrage_fest(
            s, objekt, "Und die Teilnehmerliste?", "erika", als_aufgabe=True
        )
        assert zweite.aufgabe is not None and zweite.aufgabe.nr == 1
        assert zweite.aufgabe.status is AufgabenStatus.OFFEN
        s.commit()
    with make_session() as s:
        texte = [k.text for k in kommentare_zu(s, objekt)]
        mit_verlauf = kommentare_zu(s, objekt, mit_ereignissen=True)
        (aufgabe,) = aufgaben_zu(s, objekt)
    # Rückfrage, Antwort an der Aufgabe und zweite Rückfrage — alle am Beleg
    assert texte == [
        "Bitte Bewirtungsanlass nachreichen",
        "Geschäftsessen mit Kunde Müller",
        "Und die Teilnehmerliste?",
    ]
    assert len(mit_verlauf) > len(texte)
    assert aufgabe.nr == 1


def test_kommentar_braucht_ziel_und_text(make_session, beleg):
    with make_session() as s:
        with pytest.raises(AufgabenError, match="Aufgabe oder Objekt"):
            kommentiere(s, "Hallo", "jan")
        with pytest.raises(AufgabenError, match="leer"):
            kommentiere(s, "  ", "jan", objekt=Objekt("beleg", beleg.id))
        melde_aufgabe(s, "beleg_pruefen", Objekt("beleg", beleg.id), titel="x")
        with pytest.raises(AufgabenError, match="anderes Objekt"):
            kommentiere(s, "x", "jan", aufgabe="1", objekt=Objekt("beleg", "fremd"))


def test_verlauf_ist_unveraenderbar(make_session, beleg):
    with make_session() as s:
        kommentiere(s, "Erste Fassung", "jan", objekt=Objekt("beleg", beleg.id))
        s.commit()
        row = s.query(KommentarRow).one()
        row.text = "umgeschrieben"
        with pytest.raises(UnveraenderbarError):
            s.flush()
        s.rollback()
        s.delete(s.query(KommentarRow).one())
        with pytest.raises(UnveraenderbarError):
            s.flush()
        s.rollback()
        (k,) = lade_kommentare(s, objekt=Objekt("beleg", beleg.id))
    assert k.text == "Erste Fassung"


def test_objekte_beschreiben_und_aufloesen(make_session, beleg):
    tx = umsatz()
    b = buchung(transaktion_id=tx.id)
    kontakt = Kontakt(name="Schreibwaren Meier GmbH", kreditor_konto="70001")
    konto = Bankkonto(iban="DE12345678901234567890", bezeichnung="Giro")
    with make_session() as s:
        speichere_transaktion(s, tx)
        speichere_buchung(s, b)
        speichere_kontakt(s, kontakt)
        speichere_bankkonto(s, konto)
        s.commit()
        assert loese_auf(s, "beleg", str(beleg.id)[:8]) == Objekt("beleg", beleg.id)
        assert loese_auf(s, "buchung", str(b.id)[:6]).id == str(b.id)
        assert loese_auf(s, "transaktion", str(tx.id)[:6]).id == str(tx.id)
        assert loese_auf(s, "kontakt", "70001").id == str(kontakt.id)
        assert loese_auf(s, "bankkonto", "DE12 3456 7890 1234 5678 90").id == str(
            konto.id
        )
        # unbekannte Typen (z.B. Fristen aus Baustein 9) werden nicht aufgelöst
        assert loese_auf(s, "frist", "ustva-2026-09") == Objekt(
            "frist", "ustva-2026-09"
        )
        with pytest.raises(AufgabenError, match="Kein"):
            loese_auf(s, "beleg", "ffffffff")
        texte = {
            typ: beschreibe(s, Objekt(typ, i))
            for typ, i in (
                ("beleg", beleg.id),
                ("buchung", b.id),
                ("transaktion", tx.id),
                ("kontakt", kontakt.id),
                ("bankkonto", konto.id),
                ("frist", "ustva-2026-09"),
            )
        }
        weg = beschreibe(s, Objekt("beleg", "weg"))
    assert "shell.jpg" in texte["beleg"] and "59,50" in texte["beleg"]
    assert "4930" in texte["buchung"] and "0,62" in texte["buchung"]
    assert "SHELL" in texte["transaktion"] and "-59,50" in texte["transaktion"]
    assert "Schreibwaren Meier" in texte["kontakt"] and "70001" in texte["kontakt"]
    assert "DE12345678901234567890" in texte["bankkonto"]
    assert texte["frist"] == "frist:ustva-2026-09"
    assert weg == "beleg:weg (nicht gefunden)"


def test_eigener_objekttyp(make_session):
    registriere_objekttyp(
        "frist",
        "Frist",
        beschreibe=lambda _s, i: f"Frist {i} (10.11.2026)",
        finde=lambda _s, schluessel: [schluessel],
    )
    try:
        with make_session() as s:
            assert beschreibe(s, Objekt("frist", "ustva-2026-09")) == (
                "Frist ustva-2026-09 (10.11.2026)"
            )
            assert loese_auf(s, "frist", "ustva-2026-09").id == "ustva-2026-09"
    finally:
        from accounti.aufgaben.objekte import OBJEKTTYPEN

        OBJEKTTYPEN.pop("frist")


def test_kommentar_mit_belegbezug(make_session, beleg):
    with make_session() as s:
        melde_aufgabe(
            s,
            "beleg_fehlt",
            Objekt("transaktion", "tx1"),
            titel="Beleg fehlt",
            faellig_am=JETZT.date() + timedelta(days=1),
        )
        k = kommentiere(
            s, "Beleg liegt hier", "jan", aufgabe="1", anhang_beleg_id=beleg.id
        )
        assert k.anhang_beleg_id == beleg.id
        (geladen,) = kommentare_zu(s, Objekt("transaktion", "tx1"))
    assert geladen.anhang_beleg_id == beleg.id
    assert beleg.brutto == Decimal("59.50")
