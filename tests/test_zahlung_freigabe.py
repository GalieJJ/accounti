"""Zahlungslauf als Zustandsautomat: Anlage, Freigabe, Storno, Protokoll."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from accounti.db import init_db, session_factory
from accounti.db.repo_zahlung import lade_laeufe, lade_lauf, lade_protokoll
from accounti.db.repository import lade_kontakte, lade_posten
from accounti.db.tabellen import UnveraenderbarError
from accounti.db.tabellen_zahlung import LaufProtokollRow, ZahlungRow
from accounti.models.zahlung import LaufStatus
from accounti.zahlung.freigabe import (
    LaufError,
    ZustandError,
    betriebssystem_benutzer,
    entferne,
    freigeben,
    lege_an,
    markiere_eingereicht,
    person_fuer_freigabe,
    storniere,
)
from accounti.zahlung.konfiguration import Auftraggeber, ZahlungEinstellungen
from accounti.zahlung.vorschlag import erstelle_vorschlag, lade_vorschlag
from tests.zahlung_hilfe import (
    IBAN_EIGEN,
    STICHTAG,
    kreditor,
    neue_db,
    posten,
    speichere,
)

E = ZahlungEinstellungen(
    auftraggeber=Auftraggeber(name="Galerie Muster GmbH", iban=IBAN_EIGEN)
)


@pytest.fixture
def db():
    fabrik = neue_db()
    m = kreditor()
    s = kreditor("Schulz KG", "70002", iban="DE02120300000000202051", ort="Hamburg")
    a = posten(
        m,
        "RE-200",
        "1190.00",
        faellig=date(2026, 11, 15),
        skonto_bis=date(2026, 10, 21),
        skonto_prozent="2",
    )
    b = posten(s, "SK-77", "250.00", faellig=date(2026, 10, 19))
    speichere(fabrik, [m, s], [a, b])
    return fabrik, a, b


def _anlegen(fabrik, person="erika", e=E, **kw):
    with fabrik() as s:
        lauf = lege_an(s, lade_vorschlag(s, STICHTAG, e), e, person, **kw)
        s.commit()
    return lauf


def _freigeben(fabrik, nr, person="erika", e=E):
    with fabrik() as s:
        lauf = freigeben(s, nr, person, e, heute=STICHTAG)
        s.commit()
    return lauf


def test_lauf_wird_aus_dem_vorschlag_angelegt(db):
    fabrik, a, b = db
    lauf = _anlegen(fabrik)
    assert lauf.nr == 1 and lauf.status is LaufStatus.ENTWURF
    assert lauf.ausfuehrung == STICHTAG and lauf.erstellt_von == "erika"
    assert lauf.auftraggeber_iban == IBAN_EIGEN
    erste, zweite = lauf.zahlungen
    assert (erste.nr, erste.posten_id, erste.empfaenger) == (
        1,
        a.id,
        "Bürobedarf Müller GmbH",
    )
    assert erste.betrag == Decimal("1166.20") and erste.skonto == Decimal("23.80")
    assert erste.verwendungszweck == "RE-200 vom 10.10.2026, abzgl. 23,80 EUR Skonto"
    assert erste.end_to_end_id == "RE-200"
    assert erste.restbetrag_vorher == Decimal("1190.00")
    assert erste.iban == "DE89370400440532013000" and erste.ort == "Kiel"
    assert zweite.posten_id == b.id and zweite.betrag == Decimal("250.00")
    assert "überfällig" in zweite.grund
    with fabrik() as s:
        gespeichert = lade_lauf(s, 1)
        protokoll = lade_protokoll(s, gespeichert.id)
    assert gespeichert.summe == Decimal("1416.20")
    assert [(p.aktion, p.person, p.nach_status) for p in protokoll] == [
        ("angelegt", "erika", LaufStatus.ENTWURF)
    ]
    assert "2 Zahlungen über 1.416,20 €" in protokoll[0].text


def test_ohne_posten_oder_auftraggeber_kein_lauf(db):
    fabrik, *_ = db
    with fabrik() as s:
        leer = lade_vorschlag(s, date(2026, 1, 1), E)
        leer.positionen.clear()
        with pytest.raises(LaufError, match="Nichts zu zahlen"):
            lege_an(s, leer, E, "erika")
        ohne = ZahlungEinstellungen()
        with pytest.raises(LaufError, match="Auftraggeber.*IBAN"):
            lege_an(s, lade_vorschlag(s, STICHTAG, ohne), ohne, "erika")


def test_posten_nie_zweimal_in_einem_aktiven_lauf(db):
    """Akzeptanz 3: weder über den Vorschlag noch direkt noch in der Datenbank."""
    fabrik, a, _ = db
    lauf = _anlegen(fabrik)
    _freigeben(fabrik, lauf.nr)
    with fabrik() as s:
        assert lade_vorschlag(s, STICHTAG, E).positionen == []
    # ein veralteter Vorschlag (von vor dem ersten Lauf) wird abgelehnt
    with fabrik() as s:
        alt = erstelle_vorschlag(
            lade_posten(s), {k.id: k for k in lade_kontakte(s)}, STICHTAG, E
        )
        with pytest.raises(LaufError, match="bereits in einem aktiven Zahlungslauf"):
            lege_an(s, alt, E, "erika")
    # auch an der Ablauflogik vorbei verhindert der eindeutige Index die Doppelung
    with fabrik() as s:
        doppelt = s.scalars(select(ZahlungRow)).first()
        with pytest.raises(IntegrityError, match="zahlungen.sperre"):
            s.execute(
                text(
                    "INSERT INTO zahlungen (id, lauf_id, nr, posten_id, sperre,"
                    " kontakt_id, empfaenger, iban, betrag, skonto, restbetrag_vorher,"
                    " verwendungszweck, end_to_end_id, grund) VALUES ('x', :l, 9, :p,"
                    " :p, :k, 'X', 'DE', 1, 0, 1, 'x', 'x', 'x')"
                ),
                {"l": doppelt.lauf_id, "p": str(a.id), "k": doppelt.kontakt_id},
            )


def test_entfernen_nur_im_entwurf(db):
    fabrik, a, b = db
    lauf = _anlegen(fabrik)
    with fabrik() as s:
        weg = entferne(s, lauf.nr, 1, "erika")
        s.commit()
    assert weg.posten_id == a.id
    with fabrik() as s:
        rest = lade_lauf(s, lauf.nr)
        assert [z.posten_id for z in rest.zahlungen] == [b.id]
        assert lade_protokoll(s, rest.id)[-1].text.startswith("Zahlung 1 entfernt")
        # der entfernte Posten ist wieder frei
        assert [p.posten.id for p in lade_vorschlag(s, STICHTAG, E).positionen] == [
            a.id
        ]
        with pytest.raises(LaufError, match="keine Zahlung 7"):
            entferne(s, lauf.nr, 7, "erika")


def test_freigegebener_lauf_nur_stornierbar_mit_protokoll(db):
    """Akzeptanz 5."""
    fabrik, a, _ = db
    lauf = _anlegen(fabrik)
    frei = _freigeben(fabrik, lauf.nr, "jan")
    assert frei.status is LaufStatus.FREIGEGEBEN and frei.freigabe_hash

    with (
        fabrik() as s,
        pytest.raises(ZustandError, match="Lauf 1 ist freigegeben.*stornieren"),
    ):
        entferne(s, lauf.nr, 1, "jan")
    # auch am Ablauf vorbei: Zahlungen sind über das ORM gesperrt
    with fabrik() as s:
        zeile = s.scalars(select(ZahlungRow)).first()
        zeile.betrag = Decimal("1.00")
        with pytest.raises(UnveraenderbarError):
            s.flush()
    with fabrik() as s:
        s.delete(s.scalars(select(ZahlungRow)).first())
        with pytest.raises(UnveraenderbarError):
            s.flush()

    with fabrik() as s:
        with pytest.raises(LaufError, match="Grund"):
            storniere(s, lauf.nr, "jan", "  ")
        storno = storniere(s, lauf.nr, "jan", "Rechnung RE-200 doppelt erfasst")
        s.commit()
    assert storno.status is LaufStatus.STORNIERT
    with fabrik() as s:
        protokoll = lade_protokoll(s, storno.id)
        # Posten sind wieder frei
        assert {p.posten.id for p in lade_vorschlag(s, STICHTAG, E).positionen} == {
            a.id,
            lauf.zahlungen[1].posten_id,
        }
    assert [(p.aktion, p.person, p.von_status, p.nach_status) for p in protokoll] == [
        ("angelegt", "erika", None, LaufStatus.ENTWURF),
        ("freigabe", "jan", LaufStatus.ENTWURF, LaufStatus.FREIGEGEBEN),
        ("storniert", "jan", LaufStatus.FREIGEGEBEN, LaufStatus.STORNIERT),
    ]
    assert protokoll[-1].text == "Rechnung RE-200 doppelt erfasst"

    # das Protokoll lässt sich weder ändern noch löschen — ORM und Datenbank
    with fabrik() as s:
        eintrag = s.scalars(select(LaufProtokollRow)).first()
        eintrag.text = "geschönt"
        with pytest.raises(UnveraenderbarError):
            s.flush()
    with fabrik() as s, pytest.raises(Exception, match="unveränderbar"):
        s.execute(text("DELETE FROM zahlungslauf_protokoll"))


def test_uebergaenge_in_falscher_reihenfolge_werden_abgelehnt(db):
    fabrik, *_ = db
    lauf = _anlegen(fabrik)
    with fabrik() as s, pytest.raises(ZustandError, match="entwurf → eingereicht"):
        markiere_eingereicht(s, lade_lauf(s, lauf.nr), "erika", "<x/>", "M1")
    _freigeben(fabrik, lauf.nr)
    with fabrik() as s:
        with pytest.raises(ZustandError, match="freigegeben → freigegeben"):
            freigeben(s, lauf.nr, "erika", E, heute=STICHTAG)
        storniere(s, lauf.nr, "erika", "Test")
        s.commit()
    with fabrik() as s:
        with pytest.raises(ZustandError, match="storniert → freigegeben"):
            freigeben(s, lauf.nr, "erika", E, heute=STICHTAG)
        with pytest.raises(ZustandError, match="storniert → storniert"):
            storniere(s, lauf.nr, "erika", "nochmal")


def test_vier_augen_prinzip(db):
    fabrik, *_ = db
    e = E.model_copy(update={"vier_augen": True})
    lauf = _anlegen(fabrik, e=e)
    erste = _freigeben(fabrik, lauf.nr, "erika", e)
    assert erste.status is LaufStatus.ENTWURF
    with fabrik() as s:
        with pytest.raises(LaufError, match="erika hat bereits freigegeben"):
            freigeben(s, lauf.nr, "erika", e, heute=STICHTAG)
        # wer nach der ersten Freigabe etwas ändert, macht sie ungültig
        entferne(s, lauf.nr, 2, "erika")
        s.commit()
    zweite = _freigeben(fabrik, lauf.nr, "jan", e)
    assert zweite.status is LaufStatus.ENTWURF
    dritte = _freigeben(fabrik, lauf.nr, "erika", e)
    assert dritte.status is LaufStatus.FREIGEGEBEN
    with fabrik() as s:
        aktionen = [(p.aktion, p.person) for p in lade_protokoll(s, dritte.id)]
    assert aktionen == [
        ("angelegt", "erika"),
        ("freigabe", "erika"),
        ("entfernt", "erika"),
        ("freigabe", "jan"),
        ("freigabe", "erika"),
    ]


def test_vier_augen_person_kommt_aus_der_anmeldung(monkeypatch):
    """Mit zahlung.vier_augen zählt nur der Anmeldename — kein --von, keine Variable."""
    vier = E.model_copy(update={"vier_augen": True})
    ich = betriebssystem_benutzer()
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "mallory")
    monkeypatch.setenv("USER", "mallory")
    monkeypatch.setenv("LOGNAME", "mallory")
    assert person_fuer_freigabe(None, vier) == ich
    assert person_fuer_freigabe(ich, vier) == ich
    with pytest.raises(LaufError, match="--von ist mit zahlung.vier_augen nicht"):
        person_fuer_freigabe("erika" if ich != "erika" else "jan", vier)
    # ohne Vier-Augen bleibt alles wie bisher
    assert person_fuer_freigabe("erika", E) == "erika"
    assert person_fuer_freigabe(None, E) == "mallory"


def test_nur_eingetragene_freigeber(db):
    fabrik, *_ = db
    e = E.model_copy(update={"freigeber": ["erika", "jan"]})
    lauf = _anlegen(fabrik, e=e)
    with fabrik() as s, pytest.raises(LaufError, match="mallory ist nicht als"):
        freigeben(s, lauf.nr, "mallory", e, heute=STICHTAG)
    assert _freigeben(fabrik, lauf.nr, "jan", e).status is LaufStatus.FREIGEGEBEN


def test_anlage_wird_erst_mit_dem_commit_gespeichert(tmp_path):
    """Kein Savepoint, der unter SQLite den Lauf vorzeitig festschreibt."""
    engine, fabrik = session_factory(f"sqlite:///{(tmp_path / 'a.db').as_posix()}")
    init_db(engine)
    m = kreditor()
    speichere(fabrik, [m], [posten(m, faellig=date(2026, 10, 19))])
    with fabrik() as s:
        lege_an(s, lade_vorschlag(s, STICHTAG, E), E, "erika")
        s.rollback()
    with fabrik() as s:
        assert lade_laeufe(s) == []
    engine.dispose()
