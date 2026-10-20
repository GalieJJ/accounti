import json
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from accounti.db import init_db, session_factory
from accounti.db.repository import lade_ustid_pruefungen
from accounti.db.tabellen import UnveraenderbarError, UstIdPruefungRow
from accounti.kontakte.ustid import (
    GENESIS,
    HttpAntwort,
    UstIdError,
    aktuelle_bestaetigung,
    baue_anfrage,
    pruefe_protokoll,
    pruefe_ustid,
)
from accounti.models import UstIdPruefart

EIGENE = "DE123456789"
UST_ID = "ATU12345678"
TAG = datetime(2026, 10, 20, 10, 0)
ALLES_A = {"ergFirmenname": "A", "ergStrasse": "A", "ergPlz": "A", "ergOrt": "A"}


class Weg:
    """Abfrageweg mit festen Antworten; Ausnahmen werden geworfen."""

    def __init__(self, *antworten: HttpAntwort | Exception) -> None:
        self.antworten = list(antworten)
        self.gesendet: list[dict[str, str]] = []

    def sende(self, daten: dict[str, str]) -> HttpAntwort:
        self.gesendet.append(daten)
        antwort = self.antworten.pop(0)
        if isinstance(antwort, Exception):
            raise antwort
        return antwort


def bzst(status: str, http: int = 200, **felder: str) -> HttpAntwort:
    body = {"id": "f00", "anfrageZeitpunkt": "2026-10-20T10:00:00+02:00"}
    return HttpAntwort(http, json.dumps({**body, "status": status, **felder}))


def anfrage(ust_id: str = UST_ID, einfach: bool = False):
    return baue_anfrage(
        EIGENE, ust_id, "Musterhaus GmbH", "Musterstr. 22", "1010", "Wien", einfach
    )


def bestaetige(session, ust_id=UST_ID, status="evatr-0000", jetzt=TAG, http=200):
    """Qualifizierte Abfrage mit fester Antwort protokollieren (für andere Tests)."""
    felder = ALLES_A if status == "evatr-0000" else {}
    a = baue_anfrage(EIGENE, ust_id, "Musterhaus GmbH", None, None, "Wien")
    return pruefe_ustid(session, Weg(bzst(status, http, **felder)), a, jetzt=jetzt)


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'p.db'}")
    init_db(engine)
    yield factory
    engine.dispose()


def _pruefe(make_session, antwort, jetzt=TAG, **kw):
    with make_session() as s:
        p = pruefe_ustid(s, Weg(antwort), anfrage(**kw), jetzt=jetzt)
        s.commit()
    return p


def test_abfrage_wird_vollstaendig_protokolliert(make_session):
    p = _pruefe(make_session, bzst("evatr-0000", **ALLES_A))
    with make_session() as s:
        (gespeichert,) = lade_ustid_pruefungen(s)
    assert gespeichert == p
    assert (p.nr, p.vorgaenger_hash) == (1, GENESIS)
    assert len(p.hash) == 64
    assert p.art is UstIdPruefart.QUALIFIZIERT
    assert (p.firmenname, p.ort, p.status, p.bzst_id) == (
        "Musterhaus GmbH",
        "Wien",
        "evatr-0000",
        "f00",
    )
    assert json.loads(p.anfrage)["angefragteUstid"] == UST_ID
    assert json.loads(p.antwort or "")["ergOrt"] == "A"
    assert p.aufbewahren_bis == date(2036, 12, 31)


def test_eintraege_sind_verkettet(make_session):
    erster = _pruefe(make_session, bzst("evatr-0000", **ALLES_A))
    zweiter = _pruefe(make_session, bzst("evatr-2001", 404))
    assert (zweiter.nr, zweiter.vorgaenger_hash) == (2, erster.hash)
    with make_session() as s:
        assert pruefe_protokoll(lade_ustid_pruefungen(s)) == []


def test_gescheiterte_abfrage_wird_protokolliert(make_session):
    p = _pruefe(make_session, TimeoutError("timed out"))
    assert (p.status, p.http_status) == (None, None)
    assert "timed out" in (p.fehler or "")
    with make_session() as s:
        assert len(lade_ustid_pruefungen(s)) == 1


def test_unzulaessige_abfrage_geht_nicht_raus(make_session):
    weg = Weg()
    with make_session() as s, pytest.raises(UstIdError):
        pruefe_ustid(s, weg, baue_anfrage(EIGENE, "DE987654321"))
    assert weg.gesendet == []


def test_zeitzone_wird_fuer_die_kette_entfernt(make_session):
    mit_zone = datetime(2026, 10, 20, 10, 0).astimezone()
    _pruefe(make_session, bzst("evatr-0000", **ALLES_A), jetzt=mit_zone)
    with make_session() as s:
        (p,) = lade_ustid_pruefungen(s)
        assert p.zeitpunkt.tzinfo is None
        assert pruefe_protokoll([p]) == []


def test_aendern_und_loeschen_ueber_das_orm_scheitert(make_session):
    p = _pruefe(make_session, bzst("evatr-2001", 404))
    with make_session() as s:
        row = s.get(UstIdPruefungRow, str(p.id))
        row.status = "evatr-0000"
        with pytest.raises(UnveraenderbarError):
            s.flush()
    with make_session() as s:
        s.delete(s.get(UstIdPruefungRow, str(p.id)))
        with pytest.raises(UnveraenderbarError):
            s.flush()


def test_sqlite_trigger_sperrt_auch_rohes_sql(make_session):
    _pruefe(make_session, bzst("evatr-2001", 404))
    with make_session() as s:
        with pytest.raises(DatabaseError, match="unveränderbar"):
            s.execute(text("UPDATE ustid_pruefungen SET status = 'evatr-0000'"))
        s.rollback()
        with pytest.raises(DatabaseError, match="unveränderbar"):
            s.execute(text("DELETE FROM ustid_pruefungen"))


def _ohne_trigger(s):
    s.execute(text("DROP TRIGGER ustid_pruefungen_kein_update"))
    s.execute(text("DROP TRIGGER ustid_pruefungen_kein_delete"))


def test_manipulation_faellt_auf(make_session):
    for status in ("evatr-2001", "evatr-0000", "evatr-2006"):
        _pruefe(make_session, bzst(status))
    with make_session() as s:
        _ohne_trigger(s)
        s.execute(text("UPDATE ustid_pruefungen SET status='evatr-0000' WHERE nr=1"))
        s.commit()
        befunde = pruefe_protokoll(lade_ustid_pruefungen(s))
    assert befunde == ["Eintrag 1: Inhalt verändert"]


def test_luecke_faellt_auf(make_session):
    for status in ("evatr-2001", "evatr-0000", "evatr-2006"):
        _pruefe(make_session, bzst(status))
    with make_session() as s:
        _ohne_trigger(s)
        s.execute(text("DELETE FROM ustid_pruefungen WHERE nr=2"))
        s.commit()
        befunde = pruefe_protokoll(lade_ustid_pruefungen(s))
    assert befunde == [
        "Eintrag 2 fehlt",
        "Eintrag 3: Verkettung zum Vorgänger gebrochen",
    ]


# --- Aktualität ----------------------------------------------------------------

STICHTAG = date(2026, 10, 20)


def _lage(make_session, ust_id=UST_ID, stichtag=STICHTAG, max_alter=30):
    with make_session() as s:
        return aktuelle_bestaetigung(s, ust_id, stichtag, max_alter)


def test_ohne_abfrage_nicht_bestaetigt(make_session):
    lage = _lage(make_session)
    assert not lage.bestaetigt
    assert "keine Bestätigung" in lage.grund


def test_aktuelle_qualifizierte_bestaetigung(make_session):
    p = _pruefe(make_session, bzst("evatr-0000", **ALLES_A), jetzt=TAG)
    lage = _lage(make_session, ust_id="atu 123 456 78")
    assert lage.bestaetigt
    assert lage.pruefung == p


def test_zu_alte_bestaetigung_zaehlt_nicht(make_session):
    _pruefe(make_session, bzst("evatr-0000", **ALLES_A), jetzt=TAG - timedelta(31))
    lage = _lage(make_session)
    assert not lage.bestaetigt
    assert "19.09.2026" in lage.grund  # zuletzt bestätigt


def test_spaetere_ungueltigkeit_sticht(make_session):
    _pruefe(make_session, bzst("evatr-0000", **ALLES_A), jetzt=TAG - timedelta(5))
    _pruefe(make_session, bzst("evatr-2001", 404), jetzt=TAG)
    lage = _lage(make_session)
    assert not lage.bestaetigt
    assert "nicht vergeben" in lage.grund


def test_stoerung_entwertet_keine_bestaetigung(make_session):
    _pruefe(make_session, bzst("evatr-0000", **ALLES_A), jetzt=TAG - timedelta(5))
    _pruefe(make_session, bzst("evatr-1001", 503), jetzt=TAG)
    _pruefe(make_session, OSError("Netz weg"), jetzt=TAG)
    assert _lage(make_session).bestaetigt


def test_spaetere_einfache_abfrage_schadet_nicht(make_session):
    _pruefe(make_session, bzst("evatr-0000", **ALLES_A), jetzt=TAG - timedelta(5))
    _pruefe(make_session, bzst("evatr-0000"), jetzt=TAG, einfach=True)
    assert _lage(make_session).bestaetigt


def test_nur_einfach_reicht_nicht(make_session):
    _pruefe(make_session, bzst("evatr-0000"), jetzt=TAG, einfach=True)
    lage = _lage(make_session)
    assert not lage.bestaetigt
    assert "einfach" in lage.grund


def test_nur_stoerungen(make_session):
    _pruefe(make_session, bzst("evatr-1001", 503), jetzt=TAG)
    lage = _lage(make_session)
    assert not lage.bestaetigt
    assert "zurzeit nicht möglich" in lage.grund


def test_andere_nummern_zaehlen_nicht(make_session):
    _pruefe(make_session, bzst("evatr-0000", **ALLES_A), ust_id="FR12345678901")
    assert not _lage(make_session).bestaetigt


def test_ohne_ust_id(make_session):
    lage = _lage(make_session, ust_id=None)
    assert not lage.bestaetigt
    assert "keine USt-IdNr." in lage.grund
