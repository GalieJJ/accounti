"""Persistenz für Benutzer, Rollen, Sitzungen, API-Token und Ereignisse."""

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DatabaseError

from accounti.db import init_db, session_factory
from accounti.db.repo_auth import (
    anzahl_benutzer,
    beende_sitzung,
    beende_sitzungen_von,
    entferne_rolle,
    ersetze_wiederherstellungscodes,
    fuege_rolle_hinzu,
    lade_api_token_nach_hash,
    lade_api_tokens,
    lade_benutzer,
    lade_benutzer_id,
    lade_ereignisse,
    lade_sitzung_nach_hash,
    markiere_sitzung_aktiv,
    merke_totp_schritt,
    offene_wiederherstellungscodes,
    protokolliere_ereignis,
    rollen_von,
    speichere_api_token,
    speichere_benutzer,
    speichere_sitzung,
    verbrauche_wiederherstellungscode,
    widerrufe_api_token,
)
from accounti.db.tabellen import UnveraenderbarError
from accounti.db.tabellen_auth import AuthEreignisRow
from accounti.models.auth import (
    ApiToken,
    AuthEreignis,
    Benutzer,
    Recht,
    Rolle,
    Rollenzuordnung,
    Sitzung,
    TokenRecht,
    rechte_der_rollen,
)

JETZT = datetime(2026, 10, 20, 9, 0)


@pytest.fixture
def sitzung(tmp_path):
    engine, fabrik = session_factory(f"sqlite:///{tmp_path / 'system.db'}")
    init_db(engine)
    with fabrik() as s:
        yield s
    engine.dispose()


def benutzer(name: str = "jan") -> Benutzer:
    return Benutzer(name=name, passwort_hash="scrypt$x", angelegt_am=JETZT)


def test_tabellen_werden_angelegt(sitzung):
    namen = set(inspect(sitzung.get_bind()).get_table_names())
    assert {
        "auth_benutzer",
        "auth_rollen",
        "auth_wiederherstellungscodes",
        "auth_sitzungen",
        "api_tokens",
        "auth_ereignisse",
    } <= namen


def test_benutzer_speichern_und_laden(sitzung):
    assert anzahl_benutzer(sitzung) == 0
    b = benutzer()
    speichere_benutzer(sitzung, b)
    sitzung.commit()
    assert anzahl_benutzer(sitzung) == 1
    geladen = lade_benutzer(sitzung, "jan")
    assert geladen == b
    assert lade_benutzer_id(sitzung, b.id) == b
    assert lade_benutzer(sitzung, "JAN") is None  # Namen sind klein geschrieben
    geaendert = b.model_copy(update={"fehlversuche": 3, "totp_aktiv": True})
    speichere_benutzer(sitzung, geaendert)
    assert lade_benutzer(sitzung, "jan").fehlversuche == 3


def test_benutzername_eindeutig(sitzung):
    speichere_benutzer(sitzung, benutzer())
    sitzung.commit()
    with pytest.raises(ValueError, match="gibt es schon"):
        speichere_benutzer(sitzung, benutzer())


def test_ungueltiger_name():
    with pytest.raises(ValueError):
        Benutzer(name="Jan Müller", passwort_hash="x", angelegt_am=JETZT)


def test_rollen_je_gesellschaft(sitzung):
    b = benutzer()
    speichere_benutzer(sitzung, b)
    fuege_rolle_hinzu(sitzung, Rollenzuordnung(b.id, "a", Rolle.BUCHHALTER))
    fuege_rolle_hinzu(sitzung, Rollenzuordnung(b.id, "a", Rolle.BUCHHALTER))  # doppelt
    fuege_rolle_hinzu(sitzung, Rollenzuordnung(b.id, "b", Rolle.FREIGEBER))
    assert sorted(
        (z.gesellschaft, z.rolle.value) for z in rollen_von(sitzung, b.id)
    ) == [
        ("a", "buchhalter"),
        ("b", "freigeber"),
    ]
    assert entferne_rolle(sitzung, b.id, "a", Rolle.BUCHHALTER)
    assert not entferne_rolle(sitzung, b.id, "a", Rolle.BUCHHALTER)
    assert [z.gesellschaft for z in rollen_von(sitzung, b.id)] == ["b"]


def test_rechte_der_rollen():
    assert rechte_der_rollen([Rolle.BETRACHTER]) == {Recht.LESEN}
    buchhalter = rechte_der_rollen([Rolle.BUCHHALTER])
    assert Recht.BUCHEN in buchhalter
    assert Recht.ZAHLUNG_FREIGEBEN not in buchhalter
    freigeber = rechte_der_rollen([Rolle.FREIGEBER])
    assert {Recht.ZAHLUNG_FREIGEBEN, Recht.STEUER_FREIGEBEN} <= freigeber
    assert Recht.BUCHEN not in freigeber
    assert Recht.VERWALTEN in rechte_der_rollen([Rolle.VERWALTER])
    assert rechte_der_rollen([Rolle.BUCHHALTER, Rolle.FREIGEBER]) == (
        buchhalter | freigeber
    )


def test_wiederherstellungscodes_genau_einmal(sitzung):
    b = benutzer()
    speichere_benutzer(sitzung, b)
    ersetze_wiederherstellungscodes(sitzung, b.id, ["h1", "h2"], JETZT)
    codes = offene_wiederherstellungscodes(sitzung, b.id)
    assert sorted(c.code_hash for c in codes) == ["h1", "h2"]
    assert verbrauche_wiederherstellungscode(sitzung, codes[0].id, JETZT)
    assert not verbrauche_wiederherstellungscode(sitzung, codes[0].id, JETZT)
    assert len(offene_wiederherstellungscodes(sitzung, b.id)) == 1
    ersetze_wiederherstellungscodes(sitzung, b.id, ["h3"], JETZT)
    assert [c.code_hash for c in offene_wiederherstellungscodes(sitzung, b.id)] == [
        "h3"
    ]


def test_fehlversuche_in_der_datenbank_gezaehlt(tmp_path):
    """Zwei Sitzungen mit veraltetem Stand verlieren keinen Fehlversuch; die Sperre
    setzt den Zähler nicht zurück (Befund A-H3: sonst wären Fehlversuche in Folge
    unbegrenzt)."""
    from datetime import timedelta

    from accounti.db.repo_auth import reserviere_versuch, setze_sperre

    engine, fabrik = session_factory(f"sqlite:///{tmp_path / 's.db'}")
    init_db(engine)
    b = benutzer()
    with fabrik() as s:
        speichere_benutzer(s, b)
        s.commit()
    regel = {"schwelle": 2, "dauer": timedelta(minutes=15), "obergrenze": 100}
    with fabrik() as s1:
        assert lade_benutzer(s1, "jan").fehlversuche == 0
        assert reserviere_versuch(s1, b.id, JETZT, **regel).fehlversuche == 1
        s1.commit()
    with fabrik() as s2:
        stand = reserviere_versuch(s2, b.id, JETZT, **regel)
        assert stand.fehlversuche == 2 and stand.gesperrt
        # gesperrt: kein weiterer Versuch frei, der Zähler bleibt
        assert reserviere_versuch(s2, b.id, JETZT, **regel) is None
        setze_sperre(s2, b.id, JETZT + timedelta(hours=1))
        s2.commit()
        gesperrt = lade_benutzer(s2, "jan")
    assert gesperrt.fehlversuche == 2
    assert gesperrt.gesperrt_bis == JETZT + timedelta(hours=1)
    engine.dispose()


def test_ereignisse_die_neuesten(sitzung):
    """Befund A-M5: ``neueste`` liefert die letzten ``grenze`` Ereignisse."""
    from datetime import timedelta

    for i in range(10):
        protokolliere_ereignis(
            sitzung,
            AuthEreignis(
                zeitpunkt=JETZT + timedelta(minutes=i), art=f"e{i}", quelle="cli"
            ),
        )
    assert [e.art for e in lade_ereignisse(sitzung, grenze=3, neueste=True)] == [
        "e7",
        "e8",
        "e9",
    ]
    assert [e.art for e in lade_ereignisse(sitzung, grenze=2)] == ["e0", "e1"]


def test_totp_schritt_nur_aufsteigend(sitzung):
    b = benutzer()
    speichere_benutzer(sitzung, b)
    assert merke_totp_schritt(sitzung, b.id, 100)
    assert not merke_totp_schritt(sitzung, b.id, 100)  # derselbe Code noch einmal
    assert not merke_totp_schritt(sitzung, b.id, 99)
    assert merke_totp_schritt(sitzung, b.id, 101)


def test_sitzungen(sitzung):
    b = benutzer()
    speichere_benutzer(sitzung, b)
    s1 = Sitzung(
        token_hash="a" * 64,
        benutzer_id=b.id,
        gesellschaft="standard",
        angelegt_am=JETZT,
        zuletzt_aktiv_am=JETZT,
        laeuft_ab_am=JETZT + timedelta(hours=8),
    )
    s2 = s1.model_copy(update={"id": uuid4(), "token_hash": "b" * 64})
    speichere_sitzung(sitzung, s1)
    speichere_sitzung(sitzung, s2)
    assert lade_sitzung_nach_hash(sitzung, "a" * 64) == s1
    markiere_sitzung_aktiv(sitzung, s1.id, JETZT + timedelta(minutes=5), "b")
    geladen = lade_sitzung_nach_hash(sitzung, "a" * 64)
    assert geladen.zuletzt_aktiv_am == JETZT + timedelta(minutes=5)
    assert geladen.gesellschaft == "b"
    beende_sitzung(sitzung, s1.id, JETZT)
    assert lade_sitzung_nach_hash(sitzung, "a" * 64).beendet_am == JETZT
    assert beende_sitzungen_von(sitzung, b.id, JETZT) == 1
    assert lade_sitzung_nach_hash(sitzung, "b" * 64).beendet_am == JETZT


def test_api_token(sitzung):
    t = ApiToken(
        name="erp",
        token_hash="c" * 64,
        gesellschaft="standard",
        rechte=[TokenRecht.OPOS_LESEN, TokenRecht.BELEGE_SCHREIBEN],
        angelegt_von="jan",
        angelegt_am=JETZT,
        gueltig_bis=date(2027, 1, 1),
    )
    speichere_api_token(sitzung, t)
    assert lade_api_token_nach_hash(sitzung, "c" * 64) == t
    assert t.gilt(JETZT)
    assert not t.gilt(datetime(2027, 1, 2))
    with pytest.raises(ValueError, match="aktives Token"):
        speichere_api_token(
            sitzung, t.model_copy(update={"id": uuid4(), "token_hash": "d" * 64})
        )
    widerrufe_api_token(sitzung, "erp", JETZT)
    widerrufen = lade_api_token_nach_hash(sitzung, "c" * 64)
    assert widerrufen.widerrufen_am == JETZT
    assert not widerrufen.gilt(JETZT)
    # nach dem Widerruf ist der Name wieder frei
    speichere_api_token(
        sitzung, t.model_copy(update={"id": uuid4(), "token_hash": "e" * 64})
    )
    assert len(lade_api_tokens(sitzung)) == 2
    with pytest.raises(ValueError, match="kein aktives Token"):
        widerrufe_api_token(sitzung, "gibtsnicht", JETZT)


def test_ereignisse_nur_anfuegen(sitzung):
    e = AuthEreignis(
        zeitpunkt=JETZT, art="anmeldung", benutzer="jan", quelle="web", ok=True
    )
    protokolliere_ereignis(sitzung, e)
    sitzung.commit()
    assert lade_ereignisse(sitzung) == [e]
    zeile = sitzung.get(AuthEreignisRow, str(e.id))
    zeile.art = "anders"
    with pytest.raises(UnveraenderbarError):
        sitzung.flush()
    sitzung.rollback()
    # SQLite sperrt auch rohes SQL (Trigger aus after_create)
    with pytest.raises(DatabaseError):
        sitzung.execute(text("UPDATE auth_ereignisse SET art = 'x'"))
    sitzung.rollback()
    with pytest.raises(DatabaseError):
        sitzung.execute(text("DELETE FROM auth_ereignisse"))
