"""Herkunft je Buchung und gelernte Regeln in der Datenbank (Baustein 10b, Paket 1)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, text, update

from accounti.db.repo_bank import loesche_buchung
from accounti.db.repo_kontierung import (
    deaktiviere_regel,
    lade_kontierungsgruende,
    lade_kontierungsgrund,
    lade_kontierungsregel,
    lade_kontierungsregeln,
    speichere_kontierungsgrund,
    speichere_regel,
)
from accounti.db.tabellen import UnveraenderbarError
from accounti.db.tabellen_kontierung import KontierungsgrundRow, KontierungsregelRow
from accounti.models.kontierung import Kontierungsregel, RegelHerkunft, Richtung
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    buchung,
    make_session_fixture,
    umsatz,
)


def regel(name: str = "gelernt_mueller", **kw: object) -> Kontierungsregel:
    werte: dict[str, object] = {
        "name": name,
        "muster": "Müller",
        "ist_text": True,
        "feld": "beide",
        "richtung": Richtung.AUSGABE,
        "soll_konto": "4930",
        "haben_konto": "1200",
        "steuer_schluessel": 9,
        "herkunft": RegelHerkunft.KORREKTUR,
        "angelegt_von": "jan",
    }
    werte.update(kw)
    return Kontierungsregel.model_validate(werte)


def test_grund_nur_anfuegen(make_session, tmp_path):
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s:
        g = speichere_kontierungsgrund(
            s, b.id, quelle="llm", modell="m", begruendung="Bürobedarf"
        )
        s.commit()
    with make_session() as s:
        zeile = s.get(KontierungsgrundRow, str(g.id))
        assert zeile is not None
        zeile.begruendung = "geändert"
        with pytest.raises(UnveraenderbarError):
            s.flush()
        s.rollback()
        zeile = s.get(KontierungsgrundRow, str(g.id))
        s.delete(zeile)
        with pytest.raises(UnveraenderbarError):
            s.flush()
        s.rollback()
    # rohes SQL: SQLite-Trigger
    with sqlite3.connect(tmp_path / "a.db") as v:
        with pytest.raises(sqlite3.DatabaseError, match="unveränderbar"):
            v.execute("UPDATE kontierungsgruende SET begruendung = 'x'")
        with pytest.raises(sqlite3.DatabaseError, match="unveränderbar"):
            v.execute("DELETE FROM kontierungsgruende")


def test_grund_ohne_buchungsbezug_bleibt_nach_verworfenem_vorschlag(make_session):
    """Der Kartenabgleich löscht vorläufige Buchungen — ohne Fremdschlüssel geht das
    durch, der Grund bleibt wie ein Journaleintrag stehen."""
    tx = umsatz()
    b = buchung(tx)
    anlegen(make_session, tx, b)
    with make_session() as s:
        speichere_kontierungsgrund(s, b.id, quelle="kreditkarte", begruendung="x")
        s.commit()
    with make_session() as s:
        loesche_buchung(s, b.id)
        s.commit()
    with make_session() as s:
        assert lade_kontierungsgrund(s, b.id) is not None


def test_neuester_grund_gilt(make_session):
    b = buchung()
    anlegen(make_session, b)
    jetzt = datetime(2026, 10, 1, 9, 0)
    with make_session() as s:
        speichere_kontierungsgrund(
            s, b.id, quelle="llm", begruendung="alt", jetzt=jetzt
        )
        speichere_kontierungsgrund(
            s,
            b.id,
            quelle="regelwerk",
            regel="r",
            begruendung="neu",
            jetzt=jetzt + timedelta(seconds=1),
        )
        s.commit()
    with make_session() as s:
        g = lade_kontierungsgrund(s, b.id)
        assert g is not None and g.begruendung == "neu" and g.regel == "r"
        alle = lade_kontierungsgruende(s, [b.id, uuid4()])
        assert set(alle) == {b.id} and alle[b.id].begruendung == "neu"


def test_begruendung_wird_gekuerzt(make_session):
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s:
        g = speichere_kontierungsgrund(s, b.id, quelle="llm", begruendung="x" * 900)
        s.commit()
    assert len(g.begruendung) == 500


def test_regel_name_eindeutig(make_session):
    with make_session() as s:
        speichere_regel(s, regel())
        s.commit()
    from sqlalchemy.exc import IntegrityError

    with make_session() as s, pytest.raises(IntegrityError):
        speichere_regel(s, regel())
        s.flush()


def test_regel_nur_deaktivierbar(make_session):
    r = regel()
    with make_session() as s:
        speichere_regel(s, r)
        s.commit()
    with make_session() as s:
        zeile = s.get(KontierungsregelRow, str(r.id))
        assert zeile is not None
        zeile.soll_konto = "4980"
        with pytest.raises(UnveraenderbarError):
            s.flush()
        s.rollback()
        zeile = s.get(KontierungsregelRow, str(r.id))
        s.delete(zeile)
        with pytest.raises(UnveraenderbarError):
            s.flush()
        s.rollback()
    with make_session() as s:
        aus = deaktiviere_regel(s, r.id, "jan", "falsch gelernt")
        s.commit()
    assert not aus.aktiv and aus.deaktiviert_von == "jan"
    with make_session() as s:
        zeile = s.get(KontierungsregelRow, str(r.id))
        assert zeile is not None
        zeile.aktiv = True  # wieder einschalten geht nicht
        with pytest.raises(UnveraenderbarError):
            s.flush()
        s.rollback()
        assert lade_kontierungsregel(s, r.id).deaktiviert_grund == "falsch gelernt"


def test_regeln_neueste_zuerst_nur_aktive(make_session):
    jetzt = datetime(2026, 10, 1, 9, 0)
    erste = regel("gelernt_a", angelegt_am=jetzt)
    zweite = regel("gelernt_b", angelegt_am=jetzt + timedelta(minutes=1))
    dritte = regel("gelernt_c", angelegt_am=jetzt + timedelta(minutes=2))
    with make_session() as s:
        for r in (erste, zweite, dritte):
            speichere_regel(s, r)
        s.commit()
    with make_session() as s:
        deaktiviere_regel(s, dritte.id, "jan", "weg")
        s.commit()
    with make_session() as s:
        assert [r.name for r in lade_kontierungsregeln(s, nur_aktive=True)] == [
            "gelernt_b",
            "gelernt_a",
        ]
        assert [r.name for r in lade_kontierungsregeln(s)] == [
            "gelernt_c",
            "gelernt_b",
            "gelernt_a",
        ]


def test_massenaenderung_gesperrt(make_session):
    with make_session() as s:
        speichere_regel(s, regel())
        s.commit()
    with make_session() as s:
        for anweisung in (
            update(KontierungsregelRow).values(soll_konto="4980"),
            delete(KontierungsregelRow),
            update(KontierungsgrundRow).values(begruendung="x"),
        ):
            with pytest.raises(UnveraenderbarError):
                s.execute(anweisung)
        with pytest.raises(UnveraenderbarError):
            s.bulk_insert_mappings(
                KontierungsgrundRow,  # type: ignore[arg-type]
                [{"id": "x", "buchung_id": "y"}],
            )
        assert s.execute(text("SELECT count(*) FROM kontierungsregeln")).scalar() == 1
