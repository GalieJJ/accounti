"""Zuständigkeit: Benutzer oder Rolle; unzugewiesen ist sichtbar (Akzeptanz 6)."""

from uuid import uuid4

import pytest

from accounti.aufgaben import melde_aufgabe, weise_zu
from accounti.aufgaben.einstellungen import AufgabenEinstellungen
from accounti.aufgaben.zustaendigkeit import (
    Zustaendigkeitsregel,
    bestimme_zustaendigkeit,
    gemeinsame_liste,
    meine_aufgaben,
    rollen_von,
    wer_bin_ich,
)
from accounti.db import init_db, session_factory
from accounti.db.repo_aufgaben import lade_aufgaben
from accounti.models.aufgaben import Objekt
from tests.aufgaben_hilfe import JETZT


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'z.db'}")
    init_db(engine)
    yield factory
    engine.dispose()


REGELN = [
    Zustaendigkeitsregel(wenn={"art": "bank_*"}, rolle="leitung"),
    Zustaendigkeitsregel(wenn={"objekt_typ": "beleg", "kanal": "email"}, an="erika"),
]


def test_erste_passende_regel_gewinnt():
    beleg = Objekt("beleg", "1")
    assert bestimme_zustaendigkeit(REGELN, "bank_freigabe", beleg, {}) == (
        None,
        "leitung",
    )
    assert bestimme_zustaendigkeit(
        REGELN, "beleg_pruefen", beleg, {"kanal": "email"}
    ) == (
        "erika",
        None,
    )
    # Merkmal fehlt → Regel greift nicht → unzugewiesen
    assert bestimme_zustaendigkeit(REGELN, "beleg_pruefen", beleg, {}) == (None, None)
    assert bestimme_zustaendigkeit([], "x", beleg, {}) == (None, None)


def test_wer_bin_ich(monkeypatch):
    monkeypatch.delenv("ACCOUNTI_BENUTZER", raising=False)
    assert wer_bin_ich(AufgabenEinstellungen(ich="jan")) == "jan"
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "erika")
    assert wer_bin_ich(AufgabenEinstellungen(ich="jan")) == "jan"
    assert wer_bin_ich(AufgabenEinstellungen()) == "erika"
    monkeypatch.delenv("ACCOUNTI_BENUTZER")
    assert wer_bin_ich(AufgabenEinstellungen())  # Login-Name als letzter Ausweg


def test_rollen():
    e = AufgabenEinstellungen(
        rollen={"buchhaltung": ["jan", "erika"], "leitung": ["jan"]}
    )
    assert rollen_von(e, "jan") == {"buchhaltung", "leitung"}
    assert rollen_von(e, "erika") == {"buchhaltung"}
    assert rollen_von(e, "gast") == set()


def test_unzugewiesene_aufgabe_in_der_gemeinsamen_liste(make_session):
    """Akzeptanz 6: Ohne Regel bleibt die Aufgabe unzugewiesen — und sichtbar."""
    e = AufgabenEinstellungen(rollen={"buchhaltung": ["erika"]})
    with make_session() as s:
        for art, an in (("beleg_fehlt", None), ("kontierung_pruefen", "jan")):
            melde_aufgabe(
                s,
                art,
                Objekt("transaktion", uuid4()),
                titel=art,
                jetzt=JETZT,
                zustaendig=an,
            )
        melde_aufgabe(
            s,
            "rueckfrage",
            Objekt("beleg", uuid4()),
            titel="Rolle",
            rolle="buchhaltung",
        )
        s.commit()
        alle = lade_aufgaben(s)
    gemeinsam = gemeinsame_liste(alle)
    assert [a.art for a in gemeinsam] == ["beleg_fehlt"]
    assert gemeinsam[0].unzugewiesen
    assert [a.art for a in meine_aufgaben(alle, "jan", e)] == ["kontierung_pruefen"]
    assert [a.art for a in meine_aufgaben(alle, "erika", e)] == ["rueckfrage"]


def test_erledigte_fallen_aus_der_gemeinsamen_liste(make_session):
    from accounti.aufgaben import erledige

    with make_session() as s:
        melde_aufgabe(s, "beleg_fehlt", Objekt("transaktion", "1"), titel="x")
        assert len(gemeinsame_liste(lade_aufgaben(s))) == 1
        erledige(s, "1", von="jan", text="belegfrei")
        assert gemeinsame_liste(lade_aufgaben(s)) == []
        melde_aufgabe(s, "beleg_fehlt", Objekt("transaktion", "2"), titel="y")
        weise_zu(s, "2", an="jan", von="jan")
        assert gemeinsame_liste(lade_aufgaben(s)) == []
