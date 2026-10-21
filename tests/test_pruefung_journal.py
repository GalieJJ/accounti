"""Journal: nur anfügen, hash-verkettet, Abgleich mit dem Bestand (Spec 4.3, Akz. 5)."""

import json
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from accounti.db.repository import setze_status, speichere_buchung
from accounti.db.tabellen import BuchungssatzRow, UnveraenderbarError
from accounti.db.tabellen_pruefung import JournalRow
from accounti.models import BuchungStatus
from accounti.pruefung.journal import (
    GENESIS,
    eintrag_hash,
    lade_journal,
    pruefe_journal,
    schreibe,
    uebernehme_bestand,
)
from accounti.pruefung.person import journal_kontext
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    buchung,
    make_session_fixture,
    umsatz,
)


def _journal(make_session):
    with make_session() as s:
        return lade_journal(s)


def test_buchung_anlegen_steht_im_journal(make_session, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "erika")
    tx = umsatz()
    b = buchung(tx)
    anlegen(make_session, tx, b)
    (e,) = _journal(make_session)
    assert (e.nr, e.vorgang, e.objekt_typ, e.objekt_id) == (
        1,
        "buchung_angelegt",
        "buchung",
        str(b.id),
    )
    assert e.person == "erika"
    assert e.vorher is None
    nachher = json.loads(e.nachher)
    assert nachher["betrag_netto"] == "100.00"
    assert nachher["soll_konto"] == "4900"
    assert e.vorgaenger_hash == GENESIS and len(e.hash) == 64
    with make_session() as s:
        assert pruefe_journal(s).in_ordnung


def test_freigabe_steht_mit_person_und_vorher_nachher_im_journal(make_session):
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s:
        setze_status(s, str(b.id), BuchungStatus.GEPRUEFT, geprueft_von="jan")
        s.commit()
    erster, zweiter = _journal(make_session)
    assert zweiter.vorgang == "buchung_freigegeben"
    assert zweiter.person == "jan"
    assert json.loads(zweiter.vorher)["status"] == "pruefung"
    assert json.loads(zweiter.nachher)["status"] == "geprueft"
    assert zweiter.vorgaenger_hash == erster.hash


def test_kontext_setzt_person_und_grund(make_session):
    with journal_kontext(person="system", grund="Testlauf"), make_session() as s:
        speichere_buchung(s, buchung())
        s.commit()
    (e,) = _journal(make_session)
    assert (e.person, e.grund) == ("system", "Testlauf")


def test_rollback_nimmt_den_eintrag_mit(make_session):
    with make_session() as s:
        speichere_buchung(s, buchung())
        s.flush()
        s.rollback()
    assert _journal(make_session) == []


def test_ohne_aenderung_kein_eintrag(make_session):
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s:
        row = s.get(BuchungssatzRow, str(b.id))
        row.soll_konto = "4900"  # gleicher Wert
        s.commit()
    assert len(_journal(make_session)) == 1


def test_explizit_schreiben(make_session):
    with make_session() as s:
        e = schreibe(s, "export", "export", "datev", nachher={"anzahl": 3})
        s.commit()
    assert e is not None and e.nr == 1
    (gelesen,) = _journal(make_session)
    assert gelesen.hash == e.hash


# --- Unveränderbarkeit ---------------------------------------------------------------


def test_orm_verweigert_aendern_und_loeschen(make_session):
    anlegen(make_session, buchung())
    with make_session() as s:
        row = s.get(JournalRow, 1)
        row.person = "mallory"
        with pytest.raises(UnveraenderbarError):
            s.flush()
        s.rollback()
        s.delete(s.get(JournalRow, 1))
        with pytest.raises(UnveraenderbarError):
            s.flush()


def test_sqlite_trigger_verweigert_rohes_sql(make_session):
    anlegen(make_session, buchung())
    with make_session() as s:
        with pytest.raises(DatabaseError, match="unveränderbar"):
            s.execute(text("UPDATE journal SET person = 'mallory'"))
        s.rollback()
        with pytest.raises(DatabaseError, match="unveränderbar"):
            s.execute(text("DELETE FROM journal"))


def test_massenaenderung_ueber_das_orm_gesperrt(make_session):
    anlegen(make_session, buchung())
    with make_session() as s:
        with pytest.raises(UnveraenderbarError, match="Massenänderung"):
            s.query(BuchungssatzRow).delete()
        with pytest.raises(UnveraenderbarError, match="Massenänderung"):
            s.query(JournalRow).update({"person": "x"})


# --- Manipulation (Akzeptanz 5) ------------------------------------------------


def _manipuliere(make_session, sql: str) -> None:
    """Wer Zugriff auf die Datenbank hat, kann die Trigger entfernen."""
    with make_session() as s:
        s.execute(text("DROP TRIGGER journal_kein_update"))
        s.execute(text("DROP TRIGGER journal_kein_delete"))
        s.execute(text(sql))
        s.commit()


def test_veraenderter_eintrag_wird_gefunden(make_session):
    tx = umsatz()
    anlegen(make_session, tx, buchung(tx), buchung(tx))
    _manipuliere(make_session, "UPDATE journal SET person = 'mallory' WHERE nr = 2")
    with make_session() as s:
        p = pruefe_journal(s)
    assert not p.in_ordnung
    assert [b.art for b in p.befunde] == ["veraendert"]
    assert "Eintrag 2 wurde verändert" in p.befunde[0].text


def test_neu_berechneter_hash_bricht_die_kette(make_session):
    """Auch wer den geänderten Eintrag mit neu berechnetem Hash zurückschreibt, fällt
    auf — der Nachfolger verweist auf den alten Hash."""
    anlegen(make_session, buchung(), buchung())
    with make_session() as s:
        erster = lade_journal(s)[0]
    gefaelscht = erster.model_copy(update={"person": "mallory"})
    neuer_hash = eintrag_hash(gefaelscht)
    assert neuer_hash != erster.hash
    _manipuliere(
        make_session,
        f"UPDATE journal SET person = 'mallory', hash = '{neuer_hash}' WHERE nr = 1",
    )
    with make_session() as s:
        befunde = pruefe_journal(s).befunde
    assert [b.art for b in befunde] == ["verkettung"]
    assert "Eintrag 2" in befunde[0].text


def test_entfernter_eintrag_wird_gefunden(make_session):
    anlegen(make_session, buchung(), buchung(), buchung())
    _manipuliere(make_session, "DELETE FROM journal WHERE nr = 2")
    with make_session() as s:
        p = pruefe_journal(s)
    arten = {b.art for b in p.befunde}
    assert {"luecke", "verkettung", "ohne_eintrag"} <= arten


def test_abgeschnittenes_ende_faellt_am_bestand_auf(make_session):
    b = buchung()
    anlegen(make_session, buchung(), b)
    _manipuliere(make_session, "DELETE FROM journal WHERE nr = 2")
    with make_session() as s:
        p = pruefe_journal(s)
    assert [x.art for x in p.befunde] == ["ohne_eintrag"]
    assert p.befunde[0].objekt == str(b.id)


def test_buchung_an_accounti_vorbei_geaendert(make_session):
    b = buchung(status=BuchungStatus.GEPRUEFT)
    anlegen(make_session, b)
    with make_session() as s:
        s.execute(
            text("UPDATE buchungssaetze SET betrag_netto = 10 WHERE id = :id"),
            {"id": str(b.id)},
        )
        s.commit()
        p = pruefe_journal(s)
    (befund,) = p.befunde
    assert befund.art == "abweichung"
    assert "betrag_netto: '100.00' → '10.00'" in befund.text


def test_buchung_an_accounti_vorbei_geloescht(make_session):
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s:
        s.execute(text("DELETE FROM buchungssaetze"))
        s.commit()
        (befund,) = pruefe_journal(s).befunde
    assert befund.art == "fehlt" and befund.objekt == str(b.id)


def test_kopf_als_anker(make_session):
    anlegen(make_session, buchung(), buchung())
    with make_session() as s:
        p = pruefe_journal(s)
        assert p.kopf_nr == 2
        anker = f"2:{p.kopf_hash[:12]}"
        assert pruefe_journal(s, kopf=anker).in_ordnung
        falsch = pruefe_journal(s, kopf="2:abcdef")
        assert [b.art for b in falsch.befunde] == ["kopf"]


def test_bestand_von_vor_dem_journal_uebernehmen(make_session):
    b = buchung()
    anlegen(make_session, b)
    with make_session() as s:
        s.execute(text("DROP TRIGGER journal_kein_delete"))
        s.execute(text("DELETE FROM journal"))
        s.commit()
        assert [x.art for x in pruefe_journal(s).befunde] == ["ohne_eintrag"]
        assert uebernehme_bestand(s, person="jan") == 1
        s.commit()
        assert pruefe_journal(s).in_ordnung
        assert uebernehme_bestand(s) == 0
    (e,) = _journal(make_session)
    assert (e.vorgang, e.person) == ("bestand_uebernommen", "jan")


def test_sperren_von_vor_dem_journal_uebernehmen(make_session):
    """Aktualisierte Datenbank: Jahr und Monat waren vor dem Journal gesperrt."""
    b = buchung(tag=date(2025, 6, 1))
    anlegen(make_session, b)
    with make_session() as s:
        s.execute(text("DROP TRIGGER journal_kein_delete"))
        s.execute(text("DELETE FROM journal"))
        s.execute(
            text(
                "INSERT INTO abschluesse (jahr, gesperrt, gewinnermittlung, ergebnis, "
                "abgeschlossen_am, von) VALUES (2025, 1, 'euer', 0, "
                "'2026-02-01 10:00:00', 'erika')"
            )
        )
        s.execute(
            text(
                "INSERT INTO periodenabschluesse (monat, gesperrt, geschlossen_am, "
                "geschlossen_von) VALUES ('2026-01', 1, '2026-02-10 10:00:00', 'erika')"
            )
        )
        s.execute(
            text(
                "INSERT INTO periodenabschluesse (monat, gesperrt, geschlossen_am, "
                "geschlossen_von) VALUES ('2026-02', 0, '2026-03-10 10:00:00', 'erika')"
            )
        )
        s.commit()
        texte = [x.text for x in pruefe_journal(s).befunde]
        assert any(
            "Geschäftsjahr 2025 ist gesperrt, laut Journal offen" in x for x in texte
        )
        assert any("Monat 2026-01 ist gesperrt" in x for x in texte)
        assert uebernehme_bestand(s, person="jan") == 3  # Buchung, Jahr, Monat
        s.commit()
        p = pruefe_journal(s)
        assert p.in_ordnung, [x.text for x in p.befunde]
        assert uebernehme_bestand(s) == 0
    assert {(e.vorgang, e.objekt_typ, e.objekt_id) for e in _journal(make_session)} == {
        ("bestand_uebernommen", "buchung", str(b.id)),
        ("sperre_uebernommen", "geschaeftsjahr", "2025"),
        ("sperre_uebernommen", "periode", "2026-01"),
    }


def test_ohne_journaltabelle_wird_nicht_protokolliert(tmp_path):
    from accounti.db import session_factory
    from accounti.db.tabellen import Base

    engine, factory = session_factory(f"sqlite:///{tmp_path / 'alt.db'}")
    tabellen = [t for n, t in Base.metadata.tables.items() if n in ("buchungssaetze",)]
    Base.metadata.create_all(engine, tables=tabellen)
    with factory() as s:
        speichere_buchung(s, buchung(netto="1.00"))
        s.commit()
        p = pruefe_journal(s)
    assert not p.vorhanden and not p.in_ordnung
    engine.dispose()
