"""Aufgaben anlegen, aktualisieren, abschließen — idempotent über (Art, Objekt)."""

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from accounti.aufgaben import (
    AufgabenError,
    Vorgang,
    erledige,
    melde_aufgabe,
    schliesse_wenn_erledigt,
    setze_status,
    weise_zu,
)
from accounti.aufgaben.einstellungen import AufgabenEinstellungen
from accounti.db import init_db, session_factory
from accounti.db.repo_aufgaben import lade_aufgabe, lade_aufgaben, lade_kommentare
from accounti.models.aufgaben import (
    Aufgabe,
    AufgabenStatus,
    KommentarArt,
    Objekt,
    Prioritaet,
)
from tests.aufgaben_hilfe import HEUTE, JETZT


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'a.db'}")
    init_db(engine)
    yield factory
    engine.dispose()


TX = Objekt("transaktion", uuid4())


def _melde(s, objekt=TX, **kw):
    werte = {
        "titel": "Beleg fehlt: SHELL 59,50 €",
        "erzeugt_von": "test",
        "jetzt": JETZT,
    }
    werte.update(kw)
    return melde_aufgabe(s, "beleg_fehlt", objekt, **werte)


def test_objekt():
    tx_id = uuid4()
    o = Objekt("transaktion", tx_id)
    assert o.id == str(tx_id) and o == Objekt("transaktion", str(tx_id))
    assert str(o) == f"transaktion:{tx_id}"
    assert Objekt.aus_text(str(o)) == o
    assert len({o, Objekt("transaktion", str(tx_id))}) == 1
    for falsch in ("Beleg", "1beleg", "beleg-x", ""):
        with pytest.raises(ValueError, match="Objekttyp"):
            Objekt(falsch, "1")
    with pytest.raises(ValueError, match="ID"):
        Objekt("beleg", "")
    with pytest.raises(ValueError, match="typ:id"):
        Objekt.aus_text("beleg")


def test_neue_aufgabe_mit_nummer_frist_und_verlauf(make_session):
    with make_session() as s:
        m = _melde(s, beschreibung="Umsatz vom 13.03.", merkmale={"betrag": "-59.50"})
        zweite = _melde(s, Objekt("transaktion", uuid4()))
        s.commit()
    a = m.aufgabe
    assert m.vorgang is Vorgang.NEU and a.nr == 1 and zweite.aufgabe.nr == 2
    assert a.schluessel == f"beleg_fehlt|transaktion|{TX.id}"
    assert a.objekt == TX and a.status is AufgabenStatus.OFFEN
    assert a.unzugewiesen and a.aktiv
    # ohne Angabe: Frist der Art aus den Einstellungen (beleg_fehlt: 10 Tage)
    assert a.faellig_am == HEUTE + timedelta(days=10)
    with make_session() as s:
        geladen = lade_aufgabe(s, "1")
        assert geladen == lade_aufgabe(s, str(a.id)[:8])
        (ereignis,) = lade_kommentare(s, aufgabe_id=a.id)
    assert geladen.merkmale == {"betrag": "-59.50"}
    assert geladen.beschreibung == "Umsatz vom 13.03."
    assert ereignis.art is KommentarArt.EREIGNIS and "angelegt" in ereignis.text
    assert ereignis.objekt == TX  # Verlauf ist auch am Objekt auffindbar


def test_zweiter_aufruf_aktualisiert_statt_zu_verdoppeln(make_session):
    with make_session() as s:
        _melde(s, faellig_am=date(2026, 3, 23))
        s.commit()
    with make_session() as s:
        gleich = _melde(s, faellig_am=date(2026, 3, 23))
        neu = _melde(
            s, titel="Beleg fehlt: SHELL 60,00 €", faellig_am=date(2026, 3, 24)
        )
        s.commit()
        (a,) = lade_aufgaben(s)
    assert gleich.vorgang is Vorgang.UNVERAENDERT
    assert neu.vorgang is Vorgang.AKTUALISIERT
    assert a.titel == "Beleg fehlt: SHELL 60,00 €" and a.faellig_am == date(2026, 3, 24)
    assert a.nr == 1


def test_prioritaet_wird_durch_den_anlass_nie_gesenkt(make_session):
    with make_session() as s:
        _melde(s, prioritaet=Prioritaet.HOCH)
        m = _melde(s, prioritaet=Prioritaet.NORMAL)
        assert m.aufgabe.prioritaet is Prioritaet.HOCH
        assert m.vorgang is Vorgang.UNVERAENDERT


def test_gleichzeitig_angelegt_bleibt_eine_aufgabe(make_session, monkeypatch):
    """Zwei Läufe sehen beide „keine Aufgabe“ — der eindeutige Schlüssel rettet."""
    with make_session() as s:
        _melde(s)
        s.commit()
    import accounti.aufgaben.erzeugung as erzeugung

    echt = erzeugung.lade_aufgabe_nach_schluessel
    aufrufe = []

    def erst_nichts(session, schluessel):
        aufrufe.append(schluessel)
        return None if len(aufrufe) == 1 else echt(session, schluessel)

    monkeypatch.setattr(erzeugung, "lade_aufgabe_nach_schluessel", erst_nichts)
    with make_session() as s:
        m = _melde(s, titel="anderer Titel")
        s.commit()
        assert len(lade_aufgaben(s)) == 1
    assert m.vorgang is Vorgang.AKTUALISIERT and m.aufgabe.nr == 1


def test_eindeutiger_schluessel_in_der_datenbank(make_session):
    from accounti.db.repo_aufgaben import speichere_aufgabe

    a = Aufgabe(art="beleg_fehlt", titel="x", objekt_typ="beleg", objekt_id="1", nr=1)
    b = a.model_copy(update={"id": uuid4(), "nr": 2})
    with make_session() as s:
        speichere_aufgabe(s, a)
        with pytest.raises(IntegrityError):
            speichere_aufgabe(s, b)


def test_hinfaellig_wenn_der_anlass_entfaellt(make_session):
    with make_session() as s:
        _melde(s)
        a = schliesse_wenn_erledigt(
            s, "beleg_fehlt", TX, grund="Beleg zugeordnet", jetzt=JETZT
        )
        assert a is not None and a.status is AufgabenStatus.HINFAELLIG
        assert a.abschluss_grund == "Beleg zugeordnet" and a.quittiert_von is None
        assert a.erledigt_am == JETZT
        # nichts mehr offen: zweiter Aufruf und fremde Objekte sind harmlos
        assert schliesse_wenn_erledigt(s, "beleg_fehlt", TX, grund="x") is None
        assert (
            schliesse_wenn_erledigt(s, "beleg_fehlt", Objekt("beleg", "9"), grund="x")
            is None
        )
        texte = [k.text for k in lade_kommentare(s, aufgabe_id=a.id)]
    assert any("hinfällig" in t and "Beleg zugeordnet" in t for t in texte)


def test_hinfaellige_aufgabe_oeffnet_sich_wieder(make_session):
    with make_session() as s:
        erste = _melde(s).aufgabe
        schliesse_wenn_erledigt(s, "beleg_fehlt", TX, grund="Beleg zugeordnet")
        m = _melde(s)
        assert m.vorgang is Vorgang.WIEDER_OFFEN
        assert m.aufgabe.id == erste.id and m.aufgabe.status is AufgabenStatus.OFFEN
        assert m.aufgabe.abschluss_grund is None and m.aufgabe.erledigt_am is None
        assert len(lade_aufgaben(s)) == 1


def test_erledigt_bleibt_erledigt(make_session):
    """Die Entscheidung eines Menschen überstimmt kein späterer Prüflauf."""
    with make_session() as s:
        _melde(s)
        a = erledige(s, "1", von="jan", text="Kontoführungsgebühr, kein Beleg nötig")
        assert a.status is AufgabenStatus.ERLEDIGT and a.quittiert_von == "jan"
        m = _melde(s, titel="neuer Titel")
        assert m.vorgang is Vorgang.ABGESCHLOSSEN
        assert m.aufgabe.status is AufgabenStatus.ERLEDIGT
        assert m.aufgabe.titel == "Beleg fehlt: SHELL 59,50 €"
        assert schliesse_wenn_erledigt(s, "beleg_fehlt", TX, grund="x") is None
        # ausdrücklich wieder öffnen (z.B. neue Rückfrage) geht
        w = _melde(s, wieder_oeffnen=True)
        assert w.vorgang is Vorgang.WIEDER_OFFEN and w.aufgabe.quittiert_von is None
        texte = [k.text for k in lade_kommentare(s, aufgabe_id=a.id)]
    assert "Kontoführungsgebühr, kein Beleg nötig" in texte
    assert any("erledigt von jan" in t for t in texte)


def test_erledigen_nur_aktiver_aufgaben(make_session):
    with make_session() as s:
        _melde(s)
        erledige(s, "1", von="jan")
        with pytest.raises(AufgabenError, match="erledigt"):
            erledige(s, "1", von="jan")
        with pytest.raises(AufgabenError, match="Keine Aufgabe"):
            erledige(s, "99", von="jan")


def test_status_wechsel(make_session):
    with make_session() as s:
        _melde(s)
        a = setze_status(s, "1", AufgabenStatus.IN_ARBEIT, von="jan")
        assert a.status is AufgabenStatus.IN_ARBEIT
        a = setze_status(s, "1", AufgabenStatus.WARTET, von="jan")
        assert a.status is AufgabenStatus.WARTET
        for verboten in (AufgabenStatus.ERLEDIGT, AufgabenStatus.HINFAELLIG):
            with pytest.raises(AufgabenError):
                setze_status(s, "1", verboten, von="jan")
        texte = [k.text for k in lade_kommentare(s, aufgabe_id=a.id)]
    assert any("in_arbeit → wartet" in t for t in texte)


def test_zuweisen_an_benutzer_rolle_und_zurueck(make_session):
    with make_session() as s:
        _melde(s)
        a = weise_zu(s, "1", an="jan", von="erika")
        assert (a.zustaendig, a.rolle, a.unzugewiesen) == ("jan", None, False)
        a = weise_zu(s, "1", rolle="buchhaltung", von="erika")
        assert (a.zustaendig, a.rolle) == (None, "buchhaltung")
        a = weise_zu(s, "1", von="erika")
        assert a.unzugewiesen
        with pytest.raises(AufgabenError, match="Benutzer oder Rolle"):
            weise_zu(s, "1", an="jan", rolle="buchhaltung", von="erika")
        texte = [k.text for k in lade_kommentare(s, aufgabe_id=a.id)]
    assert any("zugewiesen an jan" in t for t in texte)
    assert any("gemeinsame Liste" in t for t in texte)


def test_zustaendigkeitsregel_beim_anlegen(make_session):
    einstellungen = AufgabenEinstellungen.model_validate(
        {
            "zustaendigkeit": [
                {"wenn": {"art": "beleg_*", "bankkonto": "DE12*"}, "an": "erika"},
                {"wenn": {"objekt_typ": "transaktion"}, "rolle": "buchhaltung"},
            ]
        }
    )
    with make_session() as s:
        a = _melde(s, merkmale={"bankkonto": "DE1234"}, einstellungen=einstellungen)
        b = _melde(s, Objekt("transaktion", "2"), einstellungen=einstellungen)
        ausdruecklich = _melde(
            s, Objekt("transaktion", "3"), einstellungen=einstellungen, zustaendig="jan"
        )
    assert a.aufgabe.zustaendig == "erika"
    assert (b.aufgabe.zustaendig, b.aufgabe.rolle) == (None, "buchhaltung")
    assert ausdruecklich.aufgabe.zustaendig == "jan"


def test_zuweisung_ueberlebt_den_naechsten_lauf(make_session):
    einstellungen = AufgabenEinstellungen.model_validate(
        {"zustaendigkeit": [{"wenn": {"art": "*"}, "an": "erika"}]}
    )
    with make_session() as s:
        _melde(s, einstellungen=einstellungen)
        weise_zu(s, "1", an="jan", von="erika")
        m = _melde(s, einstellungen=einstellungen, titel="geändert")
    assert m.aufgabe.zustaendig == "jan"


def test_ungueltige_angaben(make_session):
    with make_session() as s:
        with pytest.raises(ValueError):
            melde_aufgabe(s, "Beleg fehlt", TX, titel="x")
        with pytest.raises(ValueError):
            melde_aufgabe(s, "beleg_fehlt", TX, titel="")


def test_zeitstempel(make_session):
    spaeter = JETZT + timedelta(hours=2)
    with make_session() as s:
        _melde(s)
        m = _melde(s, titel="neu", jetzt=spaeter)
    assert m.aufgabe.erstellt_am == JETZT and m.aufgabe.aktualisiert_am == spaeter
    assert isinstance(m.aufgabe.erstellt_am, datetime)
