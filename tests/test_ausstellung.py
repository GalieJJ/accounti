from datetime import date
from decimal import Decimal

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    fuege_position_hinzu,
    lade_ausgangsrechnung,
    lade_belege,
    speichere_ausgangsrechnung,
)
from accounti.erechnung import lies
from accounti.erechnung.ausstellung import AusstellungError, stelle_aus
from accounti.erechnung.kosit import KositErgebnis, KositMeldung
from accounti.erechnung.mustang import MustangErgebnis
from accounti.models import (
    AusgangsrechnungStatus,
    Belegart,
    Belegrichtung,
    BelegStatus,
)
from tests.test_erechnung_aufbau import FIRMA, entwurf, kunde, pos

DATUM = date(2026, 3, 10)


class FalscherPruefer:
    def __init__(self, akzeptiert=True):
        self.akzeptiert = akzeptiert
        self.geprueft = []

    def pruefe(self, xml, name="rechnung.xml"):
        self.geprueft.append(name)
        meldungen = [] if self.akzeptiert else [KositMeldung("error", "BR-DE-1", "x")]
        return KositErgebnis(self.akzeptiert, meldungen)


class FalscherPdfPruefer:
    def __init__(self, gueltig=True):
        self.gueltig = gueltig
        self.geprueft = []

    def pruefe(self, pdf, name="rechnung.pdf"):
        self.geprueft.append(name)
        meldungen = [] if self.gueltig else ["Not a PDF/A-3"]
        return MustangErgebnis(self.gueltig, self.gueltig, True, None, meldungen)


@pytest.fixture
def umgebung(tmp_path):
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    return make_session, BelegArchiv(tmp_path / "archiv")


def _anlegen(make_session, *positionen):
    e = entwurf(kunde(), *(positionen or [pos("Bilderrahmen", "250", "4")]))
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        s.commit()
    return str(e.id)[:8]


def test_ausstellen_vergibt_nummer_archiviert_und_legt_beleg_an(umgebung):
    make_session, archiv = umgebung
    schluessel = _anlegen(make_session)
    pruefer = FalscherPruefer()
    with make_session() as s:
        ergebnis = stelle_aus(s, archiv, schluessel, FIRMA, DATUM, kosit=pruefer)
        s.commit()
    assert ergebnis.rechnung.nummer == "2026-0001"
    assert pruefer.geprueft == ["2026-0001.xml"]
    with make_session() as s:
        r = lade_ausgangsrechnung(s, "2026-0001")
        (beleg,) = lade_belege(s)
    assert r.status is AusgangsrechnungStatus.AUSGESTELLT
    assert r.rechnungsdatum == DATUM
    assert r.zahlungsziel == date(2026, 3, 24)
    assert r.beleg_id == beleg.id
    # Das archivierte XML ist genau das ausgestellte
    assert archiv.lese(r.datei_hash) == ergebnis.xml
    assert lies(ergebnis.xml).nummer == "2026-0001"
    assert beleg.belegart is Belegart.AUSGANGSRECHNUNG
    assert beleg.richtung is Belegrichtung.AUSGANG
    assert beleg.status is BelegStatus.ERFASST
    assert beleg.brutto == Decimal("1190.00")
    assert beleg.kanal == "rechnung"


def test_nummern_laufen_fort(umgebung):
    make_session, archiv = umgebung
    nummern = []
    for _ in range(3):
        schluessel = _anlegen(make_session)
        with make_session() as s:
            nummern.append(
                stelle_aus(s, archiv, schluessel, FIRMA, DATUM).rechnung.nummer
            )
            s.commit()
    assert nummern == ["2026-0001", "2026-0002", "2026-0003"]


def test_abgelehnt_vom_pruefwerkzeug_verbraucht_keine_nummer(umgebung):
    make_session, archiv = umgebung
    schluessel = _anlegen(make_session)
    with make_session() as s:
        with pytest.raises(AusstellungError, match="BR-DE-1") as info:
            stelle_aus(
                s, archiv, schluessel, FIRMA, DATUM, kosit=FalscherPruefer(False)
            )
        assert info.value.kosit is not None
        s.rollback()
    with make_session() as s:
        assert (
            lade_ausgangsrechnung(s, schluessel).status
            is AusgangsrechnungStatus.ENTWURF
        )
        assert lade_belege(s) == []
        ergebnis = stelle_aus(s, archiv, schluessel, FIRMA, DATUM)
        s.commit()
    assert ergebnis.rechnung.nummer == "2026-0001"


def test_unvollstaendiger_entwurf_wird_nicht_ausgestellt(umgebung):
    make_session, archiv = umgebung
    e = entwurf(kunde().model_copy(update={"email": None}), pos("Rahmen", "100"))
    with make_session() as s:
        speichere_ausgangsrechnung(s, e)
        with pytest.raises(AusstellungError, match="E-Mail"):
            stelle_aus(s, archiv, str(e.id)[:8], FIRMA, DATUM)


def test_zweimal_ausstellen_geht_nicht(umgebung):
    make_session, archiv = umgebung
    schluessel = _anlegen(make_session)
    with make_session() as s:
        stelle_aus(s, archiv, schluessel, FIRMA, DATUM)
        s.commit()
        with pytest.raises(AusstellungError, match="bereits ausgestellt"):
            stelle_aus(s, archiv, schluessel, FIRMA, DATUM)


def test_ausgestellt_nicht_mehr_aenderbar(umgebung):
    make_session, archiv = umgebung
    schluessel = _anlegen(make_session)
    with make_session() as s:
        stelle_aus(s, archiv, schluessel, FIRMA, DATUM)
        s.commit()
        with pytest.raises(ValueError, match="unveränderlich"):
            fuege_position_hinzu(s, "2026-0001", pos("Nachtrag", "1"))


def test_ausstellen_erzeugt_und_archiviert_das_zugferd_pdf(umgebung):
    from accounti.belege.erkennung import erkenne_format
    from accounti.belege.kanaele import RohBeleg

    make_session, archiv = umgebung
    schluessel = _anlegen(make_session)
    pdf_pruefer = FalscherPdfPruefer()
    with make_session() as s:
        ergebnis = stelle_aus(
            s, archiv, schluessel, FIRMA, DATUM, pdf_pruefer=pdf_pruefer
        )
        s.commit()
        r = lade_ausgangsrechnung(s, "2026-0001")
    assert pdf_pruefer.geprueft == ["2026-0001.pdf"]
    assert ergebnis.pdf.startswith(b"%PDF-")
    assert archiv.lese(r.pdf_hash) == ergebnis.pdf
    roh = RohBeleg(dateiname="x.pdf", inhalt=ergebnis.pdf, kanal="t", herkunft="t")
    assert erkenne_format(roh).xml == ergebnis.xml


def test_abgelehntes_pdf_verbraucht_keine_nummer(umgebung):
    make_session, archiv = umgebung
    schluessel = _anlegen(make_session)
    with make_session() as s:
        with pytest.raises(AusstellungError, match="PDF/A") as info:
            stelle_aus(
                s,
                archiv,
                schluessel,
                FIRMA,
                DATUM,
                pdf_pruefer=FalscherPdfPruefer(False),
            )
        assert info.value.mustang is not None
        s.rollback()
    with make_session() as s:
        assert stelle_aus(s, archiv, schluessel, FIRMA, DATUM).rechnung.nummer == (
            "2026-0001"
        )
