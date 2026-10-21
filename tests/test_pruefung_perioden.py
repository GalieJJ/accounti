"""Periodenabschluss (Spec 4.5): Monatssperre neben der Jahressperre aus Baustein 12."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from accounti.abschluss.protokoll import pruefe_protokoll
from accounti.db.repo_abschluss import lade_protokoll, setze_jahresabschluss
from accounti.db.repository import finde_buchung, lade_buchungen, speichere_buchung
from accounti.db.tabellen import BuchungssatzRow
from accounti.db.tabellen_abschluss import JahrGesperrtError
from accounti.db.tabellen_pruefung import PeriodeGesperrtError
from accounti.models import BuchungStatus
from accounti.models.abschluss import Jahresabschluss
from accounti.opos.zahlungslauf import offene_transaktionen
from accounti.pruefung.journal import lade_journal, pruefe_journal
from accounti.pruefung.perioden import (
    PeriodeError,
    lade_perioden,
    oeffne,
    schliesse,
    sperre_am,
)
from accounti.pruefung.storno import StornoError, korrigiere
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    buchung,
    kurz,
    make_session_fixture,
    umsatz,
)

AUG = date(2026, 8, 15)


def _geschlossen(make_session, monat="2026-08", **kw):
    with make_session() as s:
        schliesse(s, monat, "erika", **kw)
        s.commit()


def test_geschlossener_monat_nimmt_keine_buchung_an(make_session):
    alt = buchung(status=BuchungStatus.GEPRUEFT, tag=AUG)
    anlegen(make_session, alt)
    _geschlossen(make_session)
    with make_session() as s:
        speichere_buchung(s, buchung(status=BuchungStatus.GEPRUEFT, tag=AUG))
        with pytest.raises(PeriodeGesperrtError, match="2026-08"):
            s.flush()
        s.rollback()
        # gemeinsame Fehlerklasse: wer die Jahressperre fängt, fängt auch diese
        speichere_buchung(s, buchung(tag=date(2026, 8, 1)))
        with pytest.raises(JahrGesperrtError):
            s.flush()
        s.rollback()
        s.delete(s.get(BuchungssatzRow, str(alt.id)))
        with pytest.raises(PeriodeGesperrtError):
            s.flush()
        s.rollback()
        # Nachbarmonat offen
        speichere_buchung(s, buchung(tag=date(2026, 9, 1)))
        s.commit()


def test_vorschlaege_verhindern_den_abschluss(make_session):
    anlegen(make_session, buchung(status=BuchungStatus.ZUR_PRUEFUNG, tag=AUG))
    with make_session() as s, pytest.raises(PeriodeError, match="1 Vorschlag"):
        schliesse(s, "2026-08", "erika")


def test_ungebuchte_umsaetze_nur_mit_trotzdem(make_session):
    anlegen(make_session, umsatz(tag=AUG))
    with make_session() as s, pytest.raises(PeriodeError, match="ungebucht"):
        schliesse(s, "2026-08", "erika")
    _geschlossen(make_session, trotzdem=True)
    with make_session() as s:
        # Sammelläufe (classify, opos zuordnen, bank abgleich) lassen ihn aus
        assert offene_transaktionen(s) == []


def test_oeffnen_nur_mit_grund_protokolliert_und_im_journal(make_session):
    _geschlossen(make_session)
    with make_session() as s:
        with pytest.raises(PeriodeError, match="Grund"):
            oeffne(s, "2026-08", "jan", " ")
        oeffne(s, "2026-08", "jan", "Rechnung nachgereicht")
        s.commit()
        speichere_buchung(s, buchung(tag=AUG))
        s.commit()
        (periode,) = lade_perioden(s)
        assert not periode.gesperrt and periode.grund == "Rechnung nachgereicht"
        protokoll = lade_protokoll(s)
        assert [e.aktion for e in protokoll] == [
            "periode_geschlossen",
            "periode_geoeffnet",
        ]
        assert pruefe_protokoll(s) == []
        eintraege = [e for e in lade_journal(s) if e.objekt_typ == "periode"]
        assert pruefe_journal(s).in_ordnung
    assert [(e.vorgang, e.objekt_id, e.person, e.grund) for e in eintraege] == [
        ("periode_geschlossen", "2026-08", "erika", None),
        ("periode_geoeffnet", "2026-08", "jan", "Rechnung nachgereicht"),
    ]


def test_doppelt_und_falsches_format(make_session):
    _geschlossen(make_session)
    with make_session() as s:
        with pytest.raises(PeriodeError, match="schon"):
            schliesse(s, "2026-08", "erika")
        with pytest.raises(PeriodeError, match="JJJJ-MM"):
            schliesse(s, "08/2026", "erika")
        with pytest.raises(PeriodeError, match="nicht geschlossen"):
            oeffne(s, "2026-09", "jan", "x")


def _jahr_gesperrt(make_session, jahr=2026):
    with make_session() as s:
        setze_jahresabschluss(
            s,
            Jahresabschluss(
                jahr=jahr,
                gesperrt=True,
                gewinnermittlung="euer",
                ergebnis=Decimal("0"),
                abgeschlossen_am=date(2027, 2, 1),
                von="erika",
            ),
        )
        s.commit()


def test_jahressperre_geht_vor(make_session):
    _geschlossen(make_session)
    _jahr_gesperrt(make_session)
    with make_session() as s:
        with pytest.raises(PeriodeError, match="abschluss oeffnen"):
            oeffne(s, "2026-08", "jan", "x")
        with pytest.raises(PeriodeError, match="Geschäftsjahr 2026"):
            schliesse(s, "2026-09", "erika")
        sperre = sperre_am(s, AUG)
        assert sperre is not None and sperre.art == "jahr"


def test_sperre_am(make_session):
    _geschlossen(make_session)
    with make_session() as s:
        monat = sperre_am(s, AUG)
        assert monat is not None and (monat.art, monat.zeitraum) == ("monat", "2026-08")
        assert sperre_am(s, date(2026, 9, 1)) is None


def test_storno_im_geschlossenen_monat(make_session):
    b = buchung(status=BuchungStatus.GEPRUEFT, tag=AUG)
    anlegen(make_session, b)
    _geschlossen(make_session)
    with make_session() as s:
        with pytest.raises(StornoError, match="--datum"):
            korrigiere(s, kurz(b.id), "4930", "1200", steuer=9)
        k = korrigiere(s, kurz(b.id), "4930", "1200", steuer=9, datum=date(2026, 9, 2))
        s.commit()
        assert finde_buchung(s, kurz(b.id)).storniert_durch == k.storno.id
        assert len(lade_buchungen(s)) == 3


def test_entsperren_an_accounti_vorbei_faellt_auf(make_session):
    _geschlossen(make_session)
    with make_session() as s:
        s.execute(text("UPDATE periodenabschluesse SET gesperrt = 0"))
        s.commit()
        (befund,) = pruefe_journal(s).befunde
    assert befund.art == "abweichung" and "2026-08" in befund.text
