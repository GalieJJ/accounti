from datetime import date
from decimal import Decimal

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.belege.kanaele import RohBeleg
from accounti.belege.pipeline import nimm_auf
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_belege, lade_eingaenge
from accounti.models import BelegStatus, Eingangsergebnis


@pytest.fixture
def umgebung(tmp_path):
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    return make_session, BelegArchiv(tmp_path / "archiv")


def _roh(inhalt=b"%PDF Rechnung", kanal="upload", name="rechnung.pdf"):
    return RohBeleg(dateiname=name, inhalt=inhalt, kanal=kanal, herkunft=f"/{name}")


def test_neuer_beleg_wird_archiviert_und_gespeichert(umgebung):
    make_session, archiv = umgebung
    with make_session() as s:
        eingang = nimm_auf(s, archiv, _roh())
        s.commit()
    with make_session() as s:
        (beleg,) = lade_belege(s)
        (protokoll,) = lade_eingaenge(s)
    assert eingang.ergebnis is Eingangsergebnis.NEU
    assert protokoll.beleg_id == beleg.id
    assert beleg.status is BelegStatus.EINGEGANGEN
    assert beleg.kanal == "upload"
    assert beleg.dateiname == "rechnung.pdf"
    # ohne Belegdatum ab Eingang; Buchungsbelege 8 Jahre (§ 147 Abs. 3 AO, BEG IV)
    assert beleg.aufbewahren_bis == date(beleg.eingegangen_am.year + 8, 12, 31)
    # Akzeptanz 6: Original unverändert im Archiv
    assert archiv.lese(beleg.datei_hash) == b"%PDF Rechnung"


def test_selber_beleg_ueber_zwei_kanaele_ergibt_einen_datensatz(umgebung):
    make_session, archiv = umgebung
    with make_session() as s:
        erst = nimm_auf(s, archiv, _roh(kanal="ordner"))
        zweit = nimm_auf(s, archiv, _roh(kanal="upload", name="kopie.pdf"))
        s.commit()
    with make_session() as s:
        belege = lade_belege(s)
        eingaenge = lade_eingaenge(s)
    assert len(belege) == 1
    assert len(eingaenge) == 2
    assert zweit.ergebnis is Eingangsergebnis.DUBLETTE
    assert zweit.beleg_id == erst.beleg_id
    assert zweit.hinweis


def _erkenner(lieferant, nummer, brutto, datum):
    def erkenne(roh, beleg):
        return beleg.model_copy(
            update={
                "lieferant_name": lieferant,
                "belegnummer": nummer,
                "brutto": Decimal(brutto),
                "belegdatum": datum,
                "status": BelegStatus.ERFASST,
            }
        )

    return erkenne


def test_erkannte_felder_loesen_stufe2_aus(umgebung):
    make_session, archiv = umgebung
    erkenner = _erkenner("Müller GmbH", "RE-1", "119.00", date(2026, 3, 5))
    with make_session() as s:
        nimm_auf(s, archiv, _roh(b"Datei A"), erkenner=erkenner)
        zweit = nimm_auf(s, archiv, _roh(b"Datei B"), erkenner=erkenner)
        s.commit()
        assert len(lade_belege(s)) == 1
    assert zweit.ergebnis is Eingangsergebnis.DUBLETTE


def test_verdacht_wird_gespeichert_und_vorgelegt(umgebung):
    make_session, archiv = umgebung
    with make_session() as s:
        erst = nimm_auf(
            s,
            archiv,
            _roh(b"A"),
            erkenner=_erkenner("Müller GmbH", "RE-1", "119.00", date(2026, 3, 5)),
        )
        zweit = nimm_auf(
            s,
            archiv,
            _roh(b"B"),
            erkenner=_erkenner("Müller GmbH", "RE-2", "119.00", date(2026, 3, 6)),
        )
        s.commit()
        pruefung = lade_belege(s, status={BelegStatus.ZUR_PRUEFUNG})
    assert zweit.ergebnis is Eingangsergebnis.VERDACHT
    assert len(pruefung) == 1
    assert pruefung[0].id == zweit.beleg_id
    assert str(erst.beleg_id)[:8] in (pruefung[0].pruef_grund or "")


def test_fehler_im_erkenner_bricht_nicht_ab(umgebung):
    make_session, archiv = umgebung

    def kaputt(roh, beleg):
        raise ValueError("Scan unlesbar")

    with make_session() as s:
        eingang = nimm_auf(s, archiv, _roh(), erkenner=kaputt)
        s.commit()
        (beleg,) = lade_belege(s)
    assert eingang.ergebnis is Eingangsergebnis.NEU
    assert beleg.status is BelegStatus.ZUR_PRUEFUNG
    assert "Scan unlesbar" in (beleg.pruef_grund or "")


def test_aufbewahrung_ab_belegdatum(umgebung):
    """Gesamttest Abschluss B10: Beginn mit dem Schluss des Jahres, in dem der Beleg
    entstanden ist (§ 147 Abs. 4 AO, § 14b Abs. 1 Satz 3 UStG) — nicht des
    Eingangsjahres; 8 statt 10 Jahre."""
    from datetime import datetime

    make_session, archiv = umgebung
    roh = RohBeleg(
        dateiname="dez.pdf",
        inhalt=b"Dezember",
        kanal="upload",
        herkunft="/dez.pdf",
        eingegangen_am=datetime(2027, 1, 4, 9, 0),
    )
    erkenner = _erkenner("Müller GmbH", "RE-12", "119.00", date(2026, 12, 28))
    with make_session() as s:
        nimm_auf(s, archiv, roh, erkenner=erkenner)
        s.commit()
        (beleg,) = lade_belege(s)
    assert beleg.aufbewahren_bis == date(2034, 12, 31)


def test_aufbewahrung_unplausibles_belegdatum_ab_eingang(umgebung):
    """Nachprüfung F, N10: ein falsch gelesenes altes Belegdatum (2016 statt 2026)
    verkürzte die Frist — vor dem Vorjahr des Eingangs zählt vorsichtig der Eingang."""
    from datetime import datetime

    make_session, archiv = umgebung
    roh = RohBeleg(
        dateiname="alt.pdf",
        inhalt=b"Lesefehler",
        kanal="upload",
        herkunft="/alt.pdf",
        eingegangen_am=datetime(2026, 3, 10, 9, 0),
    )
    erkenner = _erkenner("Müller GmbH", "RE-13", "119.00", date(2016, 3, 1))
    with make_session() as s:
        nimm_auf(s, archiv, roh, erkenner=erkenner)
        s.commit()
        (beleg,) = lade_belege(s)
    assert beleg.belegdatum == date(2016, 3, 1)
    assert beleg.aufbewahren_bis == date(2034, 12, 31)  # nicht 2024
