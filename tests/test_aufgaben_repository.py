"""Persistenz der Aufgaben, Kommentare und Benachrichtigungen."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import inspect

from accounti.db import init_db, session_factory
from accounti.db.repo_aufgaben import (
    aktualisiere_aufgabe,
    ids_mit_praefix,
    lade_aufgabe,
    lade_aufgabe_nach_schluessel,
    lade_aufgaben,
    lade_benachrichtigungen,
    lade_kommentare,
    naechste_aufgaben_nr,
    speichere_aufgabe,
    speichere_benachrichtigung,
    speichere_kommentar,
)
from accounti.db.repository import speichere_beleg
from accounti.db.tabellen import BelegRow
from accounti.models.aufgaben import (
    Aufgabe,
    AufgabenStatus,
    Benachrichtigung,
    Kommentar,
    KommentarArt,
    Objekt,
    Prioritaet,
)
from tests.aufgaben_hilfe import JETZT
from tests.test_bank_abgleich import quittung


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'p.db'}")
    init_db(engine)
    yield factory, engine
    engine.dispose()


def _aufgabe(nr, **kw):
    werte = {
        "nr": nr,
        "art": "beleg_fehlt",
        "titel": f"Aufgabe {nr}",
        "objekt_typ": "transaktion",
        "objekt_id": f"tx{nr}",
        "erstellt_am": JETZT,
        "aktualisiert_am": JETZT,
    }
    werte.update(kw)
    return Aufgabe(**werte)


def test_tabellen_werden_registriert(make_session):
    _, engine = make_session
    namen = set(inspect(engine).get_table_names())
    assert {"aufgaben", "aufgaben_kommentare", "aufgaben_benachrichtigungen"} <= namen


def test_aufgabe_hin_und_zurueck(make_session):
    factory, _ = make_session
    a = _aufgabe(
        1,
        beschreibung="Umsatz ohne Beleg",
        zustaendig="jan",
        faellig_am=date(2026, 10, 30),
        prioritaet=Prioritaet.HOCH,
        erzeugt_von="prueflauf:beleg_fehlt",
        merkmale={"bankkonto": "DE12", "betrag": "-59.50"},
        erinnerungsstufe=2,
        gemeldet_am=date(2026, 10, 20),
    )
    with factory() as s:
        assert naechste_aufgaben_nr(s) == 1
        speichere_aufgabe(s, a)
        s.commit()
    with factory() as s:
        assert lade_aufgabe(s, "1") == a
        assert lade_aufgabe(s, str(a.id)[:6]) == a
        assert lade_aufgabe_nach_schluessel(s, a.schluessel) == a
        assert lade_aufgabe_nach_schluessel(s, "gibt|es|nicht") is None
        assert naechste_aufgaben_nr(s) == 2
        geaendert = a.model_copy(
            update={"status": AufgabenStatus.ERLEDIGT, "quittiert_von": "jan"}
        )
        aktualisiere_aufgabe(s, geaendert)
        s.commit()
        assert lade_aufgabe(s, "1").status is AufgabenStatus.ERLEDIGT
        with pytest.raises(ValueError, match="Keine Aufgabe"):
            lade_aufgabe(s, "7")


def test_filter(make_session):
    factory, _ = make_session
    with factory() as s:
        speichere_aufgabe(s, _aufgabe(1))
        speichere_aufgabe(s, _aufgabe(2, art="kontierung_pruefen", erzeugt_von="x"))
        speichere_aufgabe(s, _aufgabe(3, status=AufgabenStatus.HINFAELLIG))
        assert [a.nr for a in lade_aufgaben(s)] == [1, 2, 3]
        aktiv = {AufgabenStatus.OFFEN}
        assert [a.nr for a in lade_aufgaben(s, status=aktiv)] == [1, 2]
        assert [a.nr for a in lade_aufgaben(s, art="beleg_fehlt")] == [1, 3]
        assert [a.nr for a in lade_aufgaben(s, erzeugt_von="x")] == [2]
        assert [
            a.nr for a in lade_aufgaben(s, objekt=Objekt("transaktion", "tx3"))
        ] == [3]


def test_kommentare_an_aufgabe_und_objekt(make_session):
    factory, _ = make_session
    a = _aufgabe(1)
    with factory() as s:
        speichere_aufgabe(s, a)
        speichere_kommentar(
            s,
            Kommentar(
                aufgabe_id=a.id,
                objekt_typ="transaktion",
                objekt_id="tx1",
                art=KommentarArt.EREIGNIS,
                autor="system",
                text="angelegt",
                erstellt_am=JETZT,
            ),
        )
        speichere_kommentar(
            s,
            Kommentar(
                objekt_typ="beleg",
                objekt_id="b1",
                art=KommentarArt.RUECKFRAGE,
                autor="jan",
                text="privat?",
                erstellt_am=JETZT,
            ),
        )
        s.commit()
        assert [k.text for k in lade_kommentare(s, aufgabe_id=a.id)] == ["angelegt"]
        assert [k.text for k in lade_kommentare(s, objekt=Objekt("beleg", "b1"))] == [
            "privat?"
        ]
        assert (
            lade_kommentare(
                s, objekt=Objekt("transaktion", "tx1"), arten={KommentarArt.KOMMENTAR}
            )
            == []
        )
    with pytest.raises(ValueError, match="Aufgabe oder"):
        Kommentar(autor="jan", text="ohne Ziel")


def test_benachrichtigungen(make_session):
    factory, _ = make_session
    b = Benachrichtigung(
        tag=date(2026, 10, 20),
        empfaenger="jan",
        kanal="email",
        adresse="jan@firma.example",
        aufgaben=[1, 4],
        erfolgreich=True,
        zeitpunkt=JETZT,
    )
    with factory() as s:
        speichere_benachrichtigung(s, b)
        s.commit()
        assert lade_benachrichtigungen(s, tag=date(2026, 10, 20)) == [b]
        assert lade_benachrichtigungen(s, tag=date(2026, 10, 21)) == []


def test_praefixsuche(make_session):
    factory, _ = make_session
    b = quittung()
    with factory() as s:
        speichere_beleg(s, b)
        assert ids_mit_praefix(s, BelegRow, str(b.id)[:5]) == [str(b.id)]
        assert ids_mit_praefix(s, BelegRow, str(uuid4())) == []
        assert ids_mit_praefix(s, BelegRow, "%") == []  # kein LIKE-Joker
