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


# --- späte Eingangsrechnung für einen festgeschriebenen Monat (Befund B-H3) ---------


def test_spaete_eingangsrechnung_mit_buchungsdatum(make_session):
    """§ 15 Abs. 1 Nr. 1 UStG: Vorsteuer im Zeitraum, in dem die Rechnung vorliegt —
    nicht den festgeschriebenen Monat des Belegdatums wieder öffnen."""
    from accounti.konfiguration import Buchhaltung
    from accounti.opos.verbuchung import verbuche_beleg
    from tests.pruefung_hilfe import beleg

    rechnung = beleg(tag=date(2026, 8, 10))  # eingegangen 11.08.2026
    anlegen(make_session, rechnung)
    _geschlossen(make_session)  # 2026-08
    with make_session() as s:
        for art in ("beleg", "eingang"):
            with (
                pytest.raises(PeriodeGesperrtError, match="--buchungsdatum"),
                s.begin_nested(),
            ):
                verbuche_beleg(s, rechnung, Buchhaltung(), buchungsdatum=art)
        with pytest.raises(PeriodeGesperrtError, match="JJJJ-MM-TT"):  # wie die CLI
            verbuche_beleg(s, rechnung, Buchhaltung())
        v = verbuche_beleg(s, rechnung, Buchhaltung(), buchungsdatum="offen")
        s.commit()
    assert {b.datum for b in v.buchungen} == {date(2026, 9, 1)}
    assert v.posten.belegdatum == date(2026, 8, 10)  # der Beleg bleibt, wie er ist
    assert any("§ 15 Abs. 1 Nr. 1 UStG" in h for h in v.hinweise)


def test_buchungsdatum_eingang_und_fester_tag(make_session):
    from accounti.konfiguration import Buchhaltung
    from accounti.opos.verbuchung import VerbuchungError, verbuche_beleg
    from tests.pruefung_hilfe import beleg

    erste = beleg(tag=date(2026, 7, 28), nummer="RE-1", datei_hash="1" * 64)
    zweite = beleg(tag=date(2026, 7, 29), nummer="RE-2", datei_hash="2" * 64)
    anlegen(make_session, erste, zweite)
    _geschlossen(make_session, "2026-07")
    with make_session() as s:
        v = verbuche_beleg(s, erste, Buchhaltung(), buchungsdatum="eingang")
        assert {b.datum for b in v.buchungen} == {date(2026, 8, 11)}
        with pytest.raises(VerbuchungError, match="vor dem Belegdatum"):
            verbuche_beleg(s, zweite, Buchhaltung(), buchungsdatum=date(2026, 7, 1))
        v = verbuche_beleg(s, zweite, Buchhaltung(), buchungsdatum=date(2026, 8, 20))
        assert {b.datum for b in v.buchungen} == {date(2026, 8, 20)}


def _dezember_rechnung(make_session):
    from datetime import datetime

    from tests.pruefung_hilfe import beleg

    dez = beleg(tag=date(2026, 12, 15), nummer="RE-DEZ", datei_hash="d" * 64)
    dez = dez.model_copy(update={"eingegangen_am": datetime(2027, 1, 10, 9, 0)})
    anlegen(make_session, dez)
    _geschlossen(make_session, "2026-12")
    return dez


@pytest.mark.parametrize("art", ["eingang", "offen"])
def test_buchungsdatum_nicht_ueber_den_jahreswechsel_bei_bilanz(make_session, art):
    """Befund N-M1: Aufwand und Verbindlichkeit gehören ins Geschäftsjahr des Belegs
    (§ 252 Abs. 1 Nr. 5 HGB, GoBD Rz. 51) — Dezember öffnen, Vorsteuer 1548."""
    from accounti.konfiguration import Buchhaltung
    from accounti.opos.verbuchung import VerbuchungError, verbuche_beleg

    dez = _dezember_rechnung(make_session)
    with make_session() as s, pytest.raises(VerbuchungError, match="1548") as fehler:
        verbuche_beleg(
            s, dez, Buchhaltung(), buchungsdatum=art, gewinnermittlung="bilanz"
        )
    assert "accounti periode oeffnen 2026-12" in str(fehler.value)


def test_buchungsdatum_ueber_den_jahreswechsel_bei_euer_mit_hinweis(make_session):
    from accounti.konfiguration import Buchhaltung
    from accounti.opos.verbuchung import verbuche_beleg

    dez = _dezember_rechnung(make_session)
    with make_session() as s:
        v = verbuche_beleg(
            s, dez, Buchhaltung(), buchungsdatum="eingang", gewinnermittlung="euer"
        )
    assert {b.datum for b in v.buchungen} == {date(2027, 1, 10)}
    assert any("Geschäftsjahr 2027" in h for h in v.hinweise)


def test_buchungsdatum_nur_fuer_belege_aus_gesperrten_monaten(make_session):
    """Befund N-N8/N-N7: Der Lauf verschiebt nur Belege, deren Monat gesperrt ist —
    und „offen“ beginnt beim späteren von Belegdatum und Eingang."""
    from datetime import datetime

    from accounti.konfiguration import Buchhaltung
    from accounti.opos.verbuchung import verbuche_belege
    from tests.pruefung_hilfe import beleg

    juli = beleg(tag=date(2026, 7, 28), nummer="RE-JULI", datei_hash="1" * 64)
    sept = beleg(tag=date(2026, 9, 3), nummer="RE-SEPT", datei_hash="2" * 64)
    sept = sept.model_copy(update={"eingegangen_am": datetime(2026, 10, 20, 9, 0)})
    anlegen(make_session, juli, sept)
    _geschlossen(make_session, "2026-07")
    with make_session() as s:
        lauf = verbuche_belege(s, Buchhaltung(), buchungsdatum="offen")
        s.commit()
    datum = {v.beleg.belegnummer: {b.datum for b in v.buchungen} for v in lauf.verbucht}
    assert datum == {
        "RE-JULI": {date(2026, 8, 11)},  # Eingang 11.08., nicht schon der 01.08.
        "RE-SEPT": {date(2026, 9, 3)},  # September offen: Belegdatum
    }
