"""Übermittlungsprotokoll: nur anfügen, Hash-Kette, Archivdateien (Akzeptanz 4)."""

import hashlib
import os
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from accounti.belege.archiv import BelegArchiv
from accounti.db import init_db, session_factory
from accounti.db.repo_elster import (
    lade_freigaben,
    lade_uebermittlungen,
    speichere_freigabe,
)
from accounti.db.tabellen import UnveraenderbarError
from accounti.db.tabellen_elster import (
    SteuermeldungFreigabeRow,
    SteuermeldungProtokollRow,
)
from accounti.elster.protokoll import (
    GENESIS,
    neuer_eintrag,
    protokolliere,
    pruefe_protokoll,
)
from accounti.models.elster import Freigabe, Meldeart, Modus

ZEIT = datetime(2026, 9, 7, 10, 0)


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'p.db'}")
    init_db(engine)
    yield factory
    engine.dispose()


@pytest.fixture
def archiv(tmp_path):
    return BelegArchiv(tmp_path / "archiv")


def _eintrag(archiv, xml="<Elster/>", modus=Modus.ECHT, **kw):
    return neuer_eintrag(
        archiv,
        art=Meldeart.USTVA,
        zeitraum="2026-08",
        modus=modus,
        weg="attrappe",
        datensatz=xml,
        erfolgreich=True,
        ergebnis="angenommen",
        pruefbericht="[]",
        zeitpunkt=ZEIT,
        **kw,
    )


def _drei(make_session, archiv):
    with make_session() as s:
        for i in range(3):
            protokolliere(s, _eintrag(archiv, f"<Elster n='{i}'/>", ticket=f"et{i}"))
        s.commit()
        return lade_uebermittlungen(s)


def test_kette_und_archiv(make_session, archiv):
    eintraege = _drei(make_session, archiv)
    assert [e.nr for e in eintraege] == [1, 2, 3]
    assert eintraege[0].vorgaenger_hash == GENESIS
    assert eintraege[1].vorgaenger_hash == eintraege[0].hash
    assert eintraege[2].ticket == "et2"
    assert eintraege[0].aufbewahren_bis.isoformat() == "2036-12-31"
    erster = eintraege[0]
    assert erster.datensatz_hash == hashlib.sha256(b"<Elster n='0'/>").hexdigest()
    assert archiv.lese(erster.datensatz_hash) == b"<Elster n='0'/>"
    assert pruefe_protokoll(eintraege, archiv) == []


def test_orm_verbietet_aendern_und_loeschen(make_session, archiv):
    _drei(make_session, archiv)
    with make_session() as s:
        row = s.query(SteuermeldungProtokollRow).first()
        row.ticket = "anders"
        with pytest.raises(UnveraenderbarError):
            s.flush()
        s.rollback()
        with pytest.raises(UnveraenderbarError):
            s.delete(s.query(SteuermeldungProtokollRow).first())
            s.flush()


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE steuermeldung_protokolle SET ticket = 'x'",
        "DELETE FROM steuermeldung_protokolle",
        "UPDATE steuermeldung_freigaben SET freigegeben_von = 'x'",
        "DELETE FROM steuermeldung_freigaben",
    ],
)
def test_sqlite_trigger_sperren_rohes_sql(make_session, archiv, sql):
    _drei(make_session, archiv)
    with make_session() as s:
        speichere_freigabe(
            s,
            Freigabe(
                art=Meldeart.USTVA,
                zeitraum="2026-08",
                inhalt_hash="0" * 64,
                werte="{}",
                freigegeben_von="Erika",
            ),
        )
        s.commit()
        with pytest.raises(DatabaseError):
            s.execute(text(sql))
    with make_session() as s:
        assert len(lade_uebermittlungen(s)) == 3
        assert len(lade_freigaben(s)) == 1
        with pytest.raises(UnveraenderbarError):
            s.delete(s.query(SteuermeldungFreigabeRow).first())
            s.flush()


def test_manipulationen_fallen_auf(make_session, archiv):
    a, b, c = _drei(make_session, archiv)
    veraendert = b.model_copy(update={"betrag": Decimal("1.00")})
    assert pruefe_protokoll([a, veraendert, c]) == ["Eintrag 2: Inhalt verändert"]
    assert pruefe_protokoll([a, c]) == [
        "Eintrag 2 fehlt",
        "Eintrag 3: Verkettung zum Vorgänger gebrochen",
    ]
    umgehaengt = c.model_copy(update={"vorgaenger_hash": a.hash})
    assert "Eintrag 3: Verkettung zum Vorgänger gebrochen" in pruefe_protokoll(
        [a, b, umgehaengt]
    )


def test_veraenderte_oder_fehlende_archivdatei(make_session, archiv):
    a, b, _ = _drei(make_session, archiv)
    pfad = archiv.pfad(a.datensatz_hash)
    os.chmod(pfad, 0o644)
    pfad.write_bytes(b"<Elster gefaelscht='1'/>")
    archiv.pfad(b.datensatz_hash).unlink()
    befunde = pruefe_protokoll(lade_alle(make_session), archiv)
    assert befunde == [
        "Eintrag 1: Datensatz im Archiv verändert",
        "Eintrag 2: Datensatz fehlt im Archiv",
    ]


def lade_alle(make_session):
    with make_session() as s:
        return lade_uebermittlungen(s)
