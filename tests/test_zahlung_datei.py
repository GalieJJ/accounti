"""Vom freigegebenen Lauf zur Datei — und über den Bankumsatz zu „ausgeführt“."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from accounti.db import init_db, session_factory
from accounti.db.repo_zahlung import lade_lauf, lade_protokoll
from accounti.db.repository import (
    aktualisiere_kontakt,
    lade_einen_posten,
    lade_kontakt,
    speichere_transaktion,
)
from accounti.db.tabellen import UnveraenderbarError
from accounti.db.tabellen_zahlung import ZahlungslaufRow
from accounti.konfiguration import Buchhaltung
from accounti.models import PostenStatus, Transaktion, TransaktionQuelle
from accounti.models.zahlung import LaufStatus
from accounti.opos.zahlungslauf import zuordne_zahlungen
from accounti.zahlung import sepa
from accounti.zahlung.freigabe import (
    LaufError,
    LaufGesperrtError,
    ZustandError,
    freigeben,
    lege_an,
    pruefe_ausfuehrung,
    storniere,
)
from accounti.zahlung.konfiguration import Auftraggeber, ZahlungEinstellungen
from accounti.zahlung.sepa import erzeuge_datei
from accounti.zahlung.vorschlag import lade_vorschlag
from tests.zahlung_hilfe import (
    IBAN_BETRUG,
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
JETZT = datetime(2026, 10, 20, 9, 30)


@pytest.fixture
def freigegeben():
    return _freigegeben(neue_db())


def _freigegeben(fabrik):
    m = kreditor()
    a = posten(
        m,
        "RE-2026-0200",
        "1190.00",
        faellig=date(2026, 11, 15),
        skonto_bis=date(2026, 10, 21),
        skonto_prozent="2",
    )
    speichere(fabrik, [m], [a])
    with fabrik() as s:
        lauf = lege_an(s, lade_vorschlag(s, STICHTAG, E), E, "erika")
        freigeben(s, lauf.nr, "erika", E, heute=STICHTAG)
        s.commit()
    return fabrik, a


def _datei(fabrik, nr=1, heute=STICHTAG, jetzt=JETZT):
    with fabrik() as s:
        ergebnis = erzeuge_datei(s, nr, E, "erika", heute=heute, jetzt=jetzt)
        s.commit()
    return ergebnis


def test_datei_nur_aus_freigegebenem_lauf():
    fabrik = neue_db()
    m = kreditor()
    speichere(fabrik, [m], [posten(m, faellig=date(2026, 10, 19))])
    with fabrik() as s:
        lege_an(s, lade_vorschlag(s, STICHTAG, E), E, "erika")
        s.commit()
    with fabrik() as s, pytest.raises(ZustandError, match="erst freigeben"):
        erzeuge_datei(s, 1, E, "erika", heute=STICHTAG)


def test_datei_macht_den_lauf_eingereicht_und_bleibt_byte_gleich(freigegeben):
    fabrik, a = freigegeben
    lauf, xml, neu = _datei(fabrik)
    assert neu and lauf.status is LaufStatus.EINGEREICHT
    assert b"<MsgId>ACCOUNTI-1-20261020093000</MsgId>" in xml
    assert b"<Ustrd>RE-2026-0200 vom 10.10.2026, abzgl. 23,80 EUR Skonto</Ustrd>" in xml
    with fabrik() as s:
        gespeichert = lade_lauf(s, 1)
        assert gespeichert.datei == xml.decode("utf-8")
        assert gespeichert.msg_id == "ACCOUNTI-1-20261020093000"
        assert gespeichert.eingereicht_am == JETZT
        letzter = lade_protokoll(s, gespeichert.id)[-1]
        assert (
            letzter.aktion == "eingereicht" and gespeichert.datei_hash in letzter.text
        )
        # der Posten bleibt gesperrt, solange das Geld unterwegs ist
        v = lade_vorschlag(s, STICHTAG, E)
        assert v.positionen == []
        assert v.ausgeschlossen[0].grund == "bereits in Zahlungslauf 1 (eingereicht)"
    # später noch einmal: dieselbe Datei, kein neuer Protokolleintrag
    lauf2, xml2, neu2 = _datei(fabrik, heute=date(2026, 10, 25), jetzt=datetime.now())
    assert xml2 == xml and not neu2
    with fabrik() as s:
        assert len(lade_protokoll(s, lauf2.id)) == 3


def test_aenderung_nach_der_freigabe_wird_erkannt(freigegeben):
    fabrik, _ = freigegeben
    with fabrik() as s:
        # am ORM vorbei — die Datenbank kennt die Sperre nicht
        s.execute(text("UPDATE zahlungen SET iban = :i"), {"i": IBAN_BETRUG})
        s.commit()
    with pytest.raises(LaufError, match="seit der Freigabe verändert"):
        _datei(fabrik)


def test_vor_der_datei_wird_erneut_geprueft(freigegeben):
    fabrik, _ = freigegeben
    with fabrik() as s:
        k = lade_kontakt(s, "70001")
        aktualisiere_kontakt(s, k.model_copy(update={"iban": IBAN_BETRUG}))
        s.commit()
    with pytest.raises(LaufGesperrtError, match="weicht vom Stammsatz"):
        _datei(fabrik)
    with fabrik() as s:
        assert lade_lauf(s, 1).status is LaufStatus.FREIGEGEBEN


def test_bankumsatz_gleicht_aus_und_der_lauf_wird_ausgefuehrt(freigegeben):
    """accounti gleicht nicht selbst aus — das macht `opos zuordnen` mit dem Umsatz."""
    fabrik, a = freigegeben
    _datei(fabrik)
    with fabrik() as s:
        assert pruefe_ausfuehrung(s, "erika") == []
        assert lade_einen_posten(s, a.id).status is PostenStatus.OFFEN
        speichere_transaktion(
            s,
            Transaktion(
                datum=date(2026, 10, 21),
                betrag=Decimal("-1166.20"),
                verwendungszweck="RE-2026-0200 vom 10.10.2026, abzgl. 23,80 EUR Skonto",
                gegenkonto_name="Bürobedarf Müller GmbH",
                gegenkonto_iban="DE89370400440532013000",
                quelle=TransaktionQuelle.BANK,
                rohtext="x",
            ),
        )
        lauf = zuordne_zahlungen(s, Buchhaltung())
        assert len(lauf.gebucht) == 1
        assert lade_einen_posten(s, a.id).status is PostenStatus.AUSGEGLICHEN
        (fertig,) = pruefe_ausfuehrung(s, "erika")
        s.commit()
    assert fertig.status is LaufStatus.AUSGEFUEHRT
    with fabrik() as s:
        assert lade_protokoll(s, fertig.id)[-1].aktion == "ausgefuehrt"
        with pytest.raises(ZustandError, match="ausgefuehrt → storniert"):
            storniere(s, 1, "erika", "zu spät")


def test_gespeicherte_datei_wird_vor_der_ausgabe_mit_dem_hash_verglichen(freigegeben):
    fabrik, _ = freigegeben
    _datei(fabrik)
    with fabrik() as s:
        # am ORM vorbei: aus 1.166,20 € werden 9.166,20 €
        s.execute(
            text(
                "UPDATE zahlungslaeufe SET datei = replace(datei, '1166.20', '9166.20')"
            )
        )
        s.commit()
    with pytest.raises(LaufError, match="weicht vom protokollierten SHA-256 ab"):
        _datei(fabrik)


def test_kopfsatz_nach_der_freigabe_am_orm_gesperrt(freigegeben):
    fabrik, _ = freigegeben
    with fabrik() as s:
        zeile = s.scalars(select(ZahlungslaufRow)).one()
        zeile.auftraggeber_iban = IBAN_BETRUG
        with pytest.raises(UnveraenderbarError, match="Kopfsatz"):
            s.flush()
    _datei(fabrik)
    with fabrik() as s:
        zeile = s.scalars(select(ZahlungslaufRow)).one()
        zeile.datei = "<Document/>"
        with pytest.raises(UnveraenderbarError, match="Kopfsatz"):
            s.flush()
    with fabrik() as s:
        zeile = s.scalars(select(ZahlungslaufRow)).one()
        zeile.status = "freigegeben"
        with pytest.raises(UnveraenderbarError, match="eingereicht → freigegeben"):
            s.flush()


def _datei_db(tmp_path):
    engine, fabrik = session_factory(f"sqlite:///{(tmp_path / 'a.db').as_posix()}")
    init_db(engine)
    _freigegeben(fabrik)
    return engine, fabrik


def test_zwei_gleichzeitige_dateien_nur_eine_gewinnt(tmp_path, monkeypatch):
    """Zwei Prozesse erzeugen gleichzeitig die Datei: Der zweite scheitert, statt
    eine zweite Datei mit neuer MsgId zu schreiben."""
    engine, fabrik = _datei_db(tmp_path)
    original = sepa.schreibe_pain001
    schon = []

    def dazwischen(*args, **kw):
        if not schon:  # während der langsame Prozess schreibt, ist der andere fertig
            schon.append(True)
            _datei(fabrik)
        return original(*args, **kw)

    monkeypatch.setattr(sepa, "schreibe_pain001", dazwischen)
    with fabrik() as langsam, pytest.raises(ZustandError, match="inzwischen geändert"):
        erzeuge_datei(langsam, 1, E, "jan", heute=STICHTAG, jetzt=datetime.now())
    with fabrik() as s:
        assert lade_lauf(s, 1).msg_id == "ACCOUNTI-1-20261020093000"
        assert [e.aktion for e in lade_protokoll(s, lade_lauf(s, 1).id)][-1] == (
            "eingereicht"
        )
    engine.dispose()


def test_veralteter_kopfsatz_ueberschreibt_nichts(tmp_path):
    """Wer den Lauf vor der Änderung eines anderen gelesen hat, schreibt nicht."""
    engine, fabrik = _datei_db(tmp_path)
    with fabrik() as alt:
        zeile = alt.scalars(select(ZahlungslaufRow)).one()  # bleibt im Speicher
        _datei(fabrik)  # ein anderer Prozess reicht ein
        assert zeile.status == "freigegeben"
        with pytest.raises(ZustandError, match="inzwischen geändert"):
            storniere(alt, 1, "jan", "versehentlich")
    with fabrik() as s:
        assert lade_lauf(s, 1).status is LaufStatus.EINGEREICHT
    engine.dispose()
