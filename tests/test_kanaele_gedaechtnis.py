from datetime import date, datetime

import pytest

from accounti.bank.tresor import TresorError, neuer_schluessel
from accounti.belege.kanaele.gedaechtnis import DbGedaechtnis, absender_zu_beleg
from accounti.belege.kanaele.zugaenge import lade_zugang, speichere_zugang
from accounti.db import init_db, session_factory
from accounti.db.repo_kanaele import (
    lade_kanal_zugang,
    lade_nachrichten,
    merke_nachricht,
    nachricht_bekannt,
)
from accounti.models import Beleg
from accounti.models.kanaele import AbgeholteNachricht


@pytest.fixture
def make_session(tmp_path):
    engine, make = session_factory(f"sqlite:///{(tmp_path / 'k.db').as_posix()}")
    init_db(engine)
    return make


def _nachricht(**werte):
    basis = {
        "kanal": "email",
        "quelle": "rechnungen",
        "schluessel": "INBOX:7:1",
        "message_id": "<a@b>",
        "absender": "rechnung@lieferant.example",
        "absender_name": "Lieferant GmbH",
        "betreff": "Ihre Rechnung",
        "gesendet_am": datetime(2026, 10, 1, 9, 30),
        "datei_hashes": ["a" * 64, "b" * 64],
    }
    return AbgeholteNachricht(**{**basis, **werte})


def test_nachricht_roundtrip_und_bekannt(make_session):
    with make_session() as s:
        merke_nachricht(s, _nachricht())
        s.commit()
    with make_session() as s:
        assert nachricht_bekannt(s, "email", "rechnungen", "INBOX:7:1")
        assert not nachricht_bekannt(s, "email", "rechnungen", "INBOX:7:2")
        assert not nachricht_bekannt(s, "email", "anderes", "INBOX:7:1")
        # neue UIDVALIDITY, aber dieselbe Message-ID → schon verarbeitet
        assert nachricht_bekannt(s, "email", "rechnungen", "INBOX:8:1", "<a@b>")
        assert not nachricht_bekannt(s, "email", "anderes", "INBOX:8:1", "<a@b>")
        (n,) = lade_nachrichten(s)
    assert n.absender == "rechnung@lieferant.example"
    assert n.datei_hashes == ["a" * 64, "b" * 64]
    assert n.gesendet_am == datetime(2026, 10, 1, 9, 30)


def test_db_gedaechtnis_schreibt_in_eigener_transaktion(make_session):
    g = DbGedaechtnis(make_session)
    assert not g.bekannt("email", "rechnungen", "INBOX:7:1")
    g.merke(_nachricht())
    g.merke(_nachricht())  # doppelt gemerkt schadet nicht
    assert g.bekannt("email", "rechnungen", "INBOX:7:1")
    with make_session() as s:
        assert len(lade_nachrichten(s)) == 1


def test_absender_zum_beleg_ueber_den_datei_hash(make_session):
    DbGedaechtnis(make_session).merke(_nachricht())
    beleg = Beleg(
        datei_hash="b" * 64,
        dateiname="r.pdf",
        kanal="email",
        herkunft="E-Mail",
        aufbewahren_bis=date(2036, 12, 31),
    )
    with make_session() as s:
        n = absender_zu_beleg(s, beleg)
        assert n is not None
        assert n.absender == "rechnung@lieferant.example"
        assert (
            absender_zu_beleg(s, beleg.model_copy(update={"datei_hash": "c"})) is None
        )


def test_zugang_verschluesselt_und_gebunden(make_session, monkeypatch):
    schluessel = neuer_schluessel()
    monkeypatch.setenv("ACCOUNTI_SCHLUESSEL", schluessel)
    with make_session() as s:
        speichere_zugang(s, "email", "rechnungen", "s3cr3t-pw")
        s.commit()
    with make_session() as s:
        roh = lade_kanal_zugang(s, "email", "rechnungen")
        assert roh is not None
        assert "s3cr3t" not in roh.chiffrat
        assert lade_zugang(s, "email", "rechnungen") == "s3cr3t-pw"
        assert lade_zugang(s, "email", "andere") is None
        # neues Passwort ersetzt das alte
        speichere_zugang(s, "email", "rechnungen", "neu")
        s.commit()
        assert lade_zugang(s, "email", "rechnungen") == "neu"
    # Chiffrat eines Postfachs passt nicht zu einem anderen
    with make_session() as s:
        z = lade_kanal_zugang(s, "email", "rechnungen")
        assert z is not None
        from accounti.belege.kanaele.zugaenge import entschluessele_zugang

        with pytest.raises(TresorError):
            entschluessele_zugang(z.model_copy(update={"name": "andere"}), schluessel)


def test_zugang_ohne_schluessel_klare_meldung(make_session, monkeypatch):
    monkeypatch.delenv("ACCOUNTI_SCHLUESSEL", raising=False)
    with make_session() as s, pytest.raises(TresorError, match="ACCOUNTI_SCHLUESSEL"):
        speichere_zugang(s, "email", "rechnungen", "pw")
