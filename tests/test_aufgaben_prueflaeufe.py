"""Prüfläufe: Daten auswerten, Aufgaben idempotent erzeugen, selbst schließen.

Akzeptanzkriterien 1 (Buchung unter der Schwelle → genau eine Aufgabe), 2 (wiederholter
Lauf verdoppelt nichts) und 3 (Beleg trifft ein → Aufgabe hinfällig).
"""

from datetime import date, datetime, timedelta

import pytest

from accounti.aufgaben import (
    Anlass,
    AufgabenError,
    AufgabenStatus,
    Objekt,
    Prioritaet,
    erledige,
    melde_aufgabe,
)
from accounti.aufgaben.einstellungen import AufgabenEinstellungen
from accounti.aufgaben.prueflaeufe import (
    PRUEFLAEUFE,
    Pruefergebnis,
    fuehre_prueflaeufe_aus,
    registriere_prueflauf,
)
from accounti.bank.abgleichslauf import gleiche_belege_ab
from accounti.buchung.kontierung import kontiere_umsaetze
from accounti.db import init_db, session_factory
from accounti.db.repo_aufgaben import lade_aufgaben, lade_kommentare
from accounti.db.repository import (
    setze_status,
    speichere_bankkonto,
    speichere_beleg,
    speichere_buchung,
    speichere_kontakt,
    speichere_transaktion,
)
from accounti.klassifikation.engine import KlassifikationsEngine
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Bankkonto,
    BelegStatus,
    BuchungStatus,
    Klassifikationsergebnis,
    Kontakt,
    KontaktStatus,
    KontoZustand,
)
from tests.aufgaben_hilfe import buchung
from tests.test_bank_abgleich import quittung, umsatz

STICHTAG = date(2026, 3, 31)
LAUF_JETZT = datetime(2026, 3, 31, 6, 0)


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'p.db'}")
    init_db(engine)
    yield factory
    engine.dispose()


def _anlegen(make_session, *objekte):
    speicher = {
        "Transaktion": speichere_transaktion,
        "Beleg": speichere_beleg,
        "Buchungssatz": speichere_buchung,
        "Kontakt": speichere_kontakt,
        "Bankkonto": speichere_bankkonto,
    }
    with make_session() as s:
        for o in objekte:
            speicher[type(o).__name__](s, o)
        s.commit()


def _lauf(make_session, *namen, einstellungen=None, zeitraum=None, stichtag=STICHTAG):
    with make_session() as s:
        ergebnisse = fuehre_prueflaeufe_aus(
            s,
            einstellungen or AufgabenEinstellungen(),
            stichtag=stichtag,
            namen=list(namen) or None,
            zeitraum=zeitraum,
            jetzt=LAUF_JETZT,
        )
        s.commit()
    return {e.name: e.abgleich for e in ergebnisse}


def _aufgaben(make_session, art=None):
    with make_session() as s:
        return lade_aufgaben(s, art=art)


# --- kontierung_pruefen ------------------------------------------------------


def test_buchung_unter_der_schwelle_erzeugt_genau_eine_aufgabe(make_session):
    """Akzeptanz 1."""
    unsicher = buchung(confidence=0.62)
    sicher = buchung(confidence=1.0, buchungstext="Kontoführung")
    schon_geprueft = buchung(confidence=0.5, status=BuchungStatus.GEPRUEFT)
    _anlegen(make_session, unsicher, sicher, schon_geprueft)
    ergebnis = _lauf(make_session, "kontierung_pruefen")["kontierung_pruefen"]
    assert len(ergebnis.neu) == 1
    (a,) = _aufgaben(make_session)
    assert a.art == "kontierung_pruefen"
    assert a.objekt == Objekt("buchung", unsicher.id)
    assert "0,62" in a.beschreibung and "0,95" in a.beschreibung
    assert a.erzeugt_von == "prueflauf:kontierung_pruefen"
    assert a.faellig_am == unsicher.datum + timedelta(days=10)
    assert a.merkmale["soll_konto"] == "4930"


def test_kontierung_aus_classify_mit_unsicherem_llm(make_session):
    """Akzeptanz 1 über den echten Kontierungslauf — classify bleibt unverändert."""

    class UnsicheresLLM:
        def klassifiziere(self, tx):
            return Klassifikationsergebnis(
                transaktion_id=tx.id,
                soll_konto="4930",
                haben_konto="1200",
                steuer_schluessel=9,
                buchungstext="Bürobedarf",
                confidence=0.6,
                begruendung="klingt nach Büro",
                quelle="llm",
            )

    tx = umsatz(
        "-100.00",
        verwendungszweck="RE 2026-311 Kopierpapier",
        gegenkonto_name="Schreibwaren Meier e.K.",
    )
    _anlegen(make_session, tx)
    with make_session() as s:
        engine = KlassifikationsEngine(llm=UnsicheresLLM())  # type: ignore[arg-type]
        lauf = kontiere_umsaetze(s, engine, Buchhaltung())
        s.commit()
    assert lauf.kontiert == 1
    _lauf(make_session, "kontierung_pruefen")
    (a,) = _aufgaben(make_session, art="kontierung_pruefen")
    assert a.objekt.typ == "buchung" and "0,60" in a.beschreibung


def test_wiederholter_lauf_verdoppelt_nichts(make_session):
    """Akzeptanz 2: zwei Prüfläufe über denselben Zeitraum → eine Aufgabe je Anlass."""
    tx = umsatz()
    _anlegen(make_session, tx, buchung(transaktion_id=tx.id, datum=tx.datum))
    erster = _lauf(make_session, zeitraum="2026-03")
    zweiter = _lauf(make_session, zeitraum="2026-03")
    dritter = _lauf(make_session)
    assert len(erster["kontierung_pruefen"].neu) == 1
    assert len(erster["beleg_fehlt"].neu) == 1
    for lauf in (zweiter, dritter):
        assert all(not e.neu and not e.hinfaellig for e in lauf.values())
    assert len(zweiter["beleg_fehlt"].unveraendert) == 1
    alle = _aufgaben(make_session)
    assert sorted(a.art for a in alle) == ["beleg_fehlt", "kontierung_pruefen"]


def test_gepruefte_buchung_macht_die_aufgabe_hinfaellig(make_session):
    b = buchung()
    _anlegen(make_session, b)
    _lauf(make_session, "kontierung_pruefen")
    with make_session() as s:
        setze_status(s, str(b.id)[:8], BuchungStatus.GEPRUEFT, geprueft_von="jan")
        s.commit()
    ergebnis = _lauf(make_session, "kontierung_pruefen")["kontierung_pruefen"]
    (a,) = ergebnis.hinfaellig
    assert a.status is AufgabenStatus.HINFAELLIG and a.quittiert_von is None
    assert "geprüft" in (a.abschluss_grund or "")


def test_confidence_knapp_unter_der_schwelle(make_session):
    """Die Anzeige rundet nicht über die Schwelle: 0,949 ist „0,94“, nicht „0,95“."""
    _anlegen(make_session, buchung(confidence=0.949))
    _lauf(make_session, "kontierung_pruefen")
    (a,) = _aufgaben(make_session)
    assert "Confidence 0,94 unter Schwelle 0,95" in a.beschreibung
    assert a.merkmale["confidence"] == "0.94"
    fein = AufgabenEinstellungen.model_validate(
        {"pruefung": {"kontierung_schwelle": 0.955}}
    )
    _anlegen(make_session, buchung(confidence=0.9549, buchungstext="Porto"))
    _lauf(make_session, "kontierung_pruefen", einstellungen=fein)
    porto = next(a for a in _aufgaben(make_session) if "Porto" in a.titel)
    assert "Confidence 0,954 unter Schwelle 0,955" in porto.beschreibung


def test_zur_pruefung_auch_mit_hoher_confidence(make_session):
    b = buchung(confidence=1.0, status=BuchungStatus.ZUR_PRUEFUNG)
    _anlegen(make_session, b)
    _lauf(make_session, "kontierung_pruefen")
    (a,) = _aufgaben(make_session)
    assert "zur Prüfung" in a.beschreibung


def test_schwelle_aus_der_konfiguration(make_session):
    _anlegen(make_session, buchung(confidence=0.9, status=BuchungStatus.AUTO_GEBUCHT))
    streng = AufgabenEinstellungen.model_validate(
        {"pruefung": {"kontierung_schwelle": 0.95}}
    )
    locker = AufgabenEinstellungen.model_validate(
        {"pruefung": {"kontierung_schwelle": 0.8}}
    )
    assert not _lauf(make_session, "kontierung_pruefen", einstellungen=locker)[
        "kontierung_pruefen"
    ].neu
    assert _lauf(make_session, "kontierung_pruefen", einstellungen=streng)[
        "kontierung_pruefen"
    ].neu


# --- beleg_fehlt ----------------------------------------------------------------


def test_beleg_trifft_ein_und_die_aufgabe_schliesst_sich_selbst(make_session):
    """Akzeptanz 3: niemand fasst die Aufgabe an."""
    tx = umsatz()
    _anlegen(make_session, tx)
    _lauf(make_session, "beleg_fehlt")
    (offen,) = _aufgaben(make_session)
    assert offen.status is AufgabenStatus.OFFEN
    assert offen.objekt == Objekt("transaktion", tx.id)
    assert "SHELL" in offen.titel and "-59,50" in offen.titel
    assert offen.faellig_am == tx.datum + timedelta(days=10)

    # der Beleg trifft ein und wird wie gewohnt abgeglichen
    _anlegen(make_session, quittung())
    with make_session() as s:
        assert len(gleiche_belege_ab(s).automatisch) == 1
        s.commit()

    ergebnis = _lauf(make_session, "beleg_fehlt")["beleg_fehlt"]
    (zu,) = ergebnis.hinfaellig
    assert zu.id == offen.id
    assert zu.status is AufgabenStatus.HINFAELLIG
    assert zu.quittiert_von is None  # vom System, nicht von einem Menschen
    assert "Shell Station Kiel" in (zu.abschluss_grund or "")
    with make_session() as s:
        verlauf = [k.text for k in lade_kommentare(s, aufgabe_id=zu.id)]
    assert any(t.startswith("hinfällig: Beleg zugeordnet") for t in verlauf)


def test_der_lauf_besitzt_seine_art(make_session):
    """Akzeptanz 3 auch für eine Aufgabe, die ein anderer Erzeuger (z.B. Baustein 7)
    mit derselben Art angelegt hat: Der Prüflauf schließt sie, sobald der Beleg da
    ist — der Idempotenzschlüssel kennt den Erzeuger nicht."""
    tx = umsatz()
    _anlegen(make_session, tx)
    with make_session() as s:
        melde_aufgabe(
            s,
            "beleg_fehlt",
            Objekt("transaktion", tx.id),
            titel="Beleg fehlt: SHELL",
            erzeugt_von="pruefung:beleg_fehlt",
            jetzt=LAUF_JETZT,
        )
        s.commit()
    # der Lauf übernimmt die vorhandene Aufgabe (gleicher Schlüssel), keine zweite
    ersterlauf = _lauf(make_session, "beleg_fehlt")["beleg_fehlt"]
    assert not ersterlauf.neu and len(ersterlauf.aktualisiert) == 1
    _anlegen(make_session, quittung())
    with make_session() as s:
        assert len(gleiche_belege_ab(s).automatisch) == 1
        s.commit()
    (zu,) = _lauf(make_session, "beleg_fehlt")["beleg_fehlt"].hinfaellig
    assert zu.erzeugt_von == "pruefung:beleg_fehlt"
    assert zu.status is AufgabenStatus.HINFAELLIG


def test_baustein_7_ersetzt_den_eingebauten_lauf(make_session):
    """Belegfreiheit nach Regel: Ein anderer Baustein trägt seinen Lauf unter dem
    Namen ``beleg_fehlt`` ein (ersetzt den eingebauten), statt dieselbe Art daneben
    zu melden und zu schließen — sonst öffnete der eingebaute Lauf jedes Mal wieder,
    was der andere geschlossen hat."""
    gebuehr = umsatz("-5.90", verwendungszweck="Kontoführung", gegenkonto_name="Bank")
    _anlegen(make_session, gebuehr, umsatz())
    assert len(_lauf(make_session, "beleg_fehlt")["beleg_fehlt"].neu) == 2
    eingebaut = PRUEFLAEUFE["beleg_fehlt"]

    class MitRegeln:
        name = "beleg_fehlt"
        beschreibung = "Umsätze ohne Beleg, Gebühren belegfrei"
        grund_entfallen = "Umsatz hat einen Beleg oder ist nach Regel belegfrei"

        def finde(self, session, einstellungen, stichtag, zeitraum):
            befund = eingebaut.finde(session, einstellungen, stichtag, zeitraum)
            befund.anlaesse = [
                a for a in befund.anlaesse if a.merkmale["gegenpartei"] != "Bank"
            ]
            return befund

    registriere_prueflauf(MitRegeln())
    try:
        erster = _lauf(make_session, "beleg_fehlt")["beleg_fehlt"]
        zweiter = _lauf(make_session, "beleg_fehlt")["beleg_fehlt"]
    finally:
        registriere_prueflauf(eingebaut)
    assert len(erster.hinfaellig) == 1 and len(erster.unveraendert) == 1
    assert not zweiter.hinfaellig and not zweiter.wieder_offen
    zu = next(a for a in _aufgaben(make_session) if not a.aktiv)
    assert zu.merkmale["gegenpartei"] == "Bank"


def test_frueherer_stichtag_schliesst_nichts_juengeres(make_session):
    """Ein Lauf mit --stichtag in der Vergangenheit kann jüngere Umsätze nicht
    beurteilen — ihre Aufgaben bleiben offen, Stufe und Meldung bleiben stehen."""
    _anlegen(make_session, umsatz(tag=8))  # 20.03.
    assert _lauf(make_session, "beleg_fehlt")["beleg_fehlt"].neu
    frueher = _lauf(make_session, "beleg_fehlt", stichtag=date(2026, 3, 10))
    assert not frueher["beleg_fehlt"].hinfaellig
    (a,) = _aufgaben(make_session)
    assert a.status is AufgabenStatus.OFFEN
    wieder = _lauf(make_session, "beleg_fehlt")["beleg_fehlt"]
    assert not wieder.wieder_offen and len(wieder.unveraendert) == 1
    # ebenso, wenn nach_tagen ihn am Stichtag noch nicht erfasst
    e = AufgabenEinstellungen.model_validate(
        {"pruefung": {"beleg_fehlt_nach_tagen": 30}}
    )
    assert not _lauf(make_session, "beleg_fehlt", einstellungen=e)[
        "beleg_fehlt"
    ].hinfaellig


def test_belegfrei_erledigt_bleibt_erledigt(make_session):
    gebuehr = umsatz("-5.90", verwendungszweck="Kontoführung", gegenkonto_name="Bank")
    _anlegen(make_session, gebuehr)
    _lauf(make_session, "beleg_fehlt")
    with make_session() as s:
        erledige(s, "1", von="jan", text="Kontoführungsgebühr, belegfrei")
        s.commit()
    ergebnis = _lauf(make_session, "beleg_fehlt")["beleg_fehlt"]
    assert len(ergebnis.abgeschlossen) == 1 and not ergebnis.neu
    (a,) = _aufgaben(make_session)
    assert a.status is AufgabenStatus.ERLEDIGT


def test_beleg_fehlt_mit_schwellen(make_session):
    _anlegen(
        make_session,
        umsatz("-4.00", tag=10, verwendungszweck="Parken"),  # 22.03., klein
        umsatz("-80.00", tag=18, verwendungszweck="Tanken"),  # 30.03., jung
        umsatz("-120.00", tag=0, verwendungszweck="Hotel"),  # 12.03.
    )
    e = AufgabenEinstellungen.model_validate(
        {"pruefung": {"beleg_fehlt_ab_betrag": "10", "beleg_fehlt_nach_tagen": 3}}
    )
    _lauf(make_session, "beleg_fehlt", einstellungen=e)
    assert [a.merkmale["betrag"] for a in _aufgaben(make_session)] == ["-120.00"]


def test_vorschlag_wird_genannt(make_session):
    tx = umsatz()
    _anlegen(make_session, tx, quittung(), quittung())  # zwei gleiche → Vorschläge
    with make_session() as s:
        assert len(gleiche_belege_ab(s).vorschlaege) == 2
        s.commit()
    _lauf(make_session, "beleg_fehlt")
    (a,) = _aufgaben(make_session)
    assert "accounti bank vorschlaege" in a.beschreibung


def test_zeitraum_schliesst_nichts_ausserhalb(make_session):
    maerz = umsatz(tag=1)
    april = umsatz(tag=0, datum=date(2026, 4, 2), verwendungszweck="April")
    _anlegen(make_session, maerz, april)
    _lauf(make_session, "beleg_fehlt", stichtag=date(2026, 4, 30))
    assert len(_aufgaben(make_session)) == 2
    # Beleg für den April-Umsatz erledigt sich nicht durch einen März-Lauf
    ergebnis = _lauf(make_session, "beleg_fehlt", zeitraum="2026-03")["beleg_fehlt"]
    assert not ergebnis.hinfaellig and len(ergebnis.unveraendert) == 1
    with pytest.raises(AufgabenError, match="JJJJ-MM"):
        _lauf(make_session, zeitraum="März")


# --- weitere Quellen ------------------------------------------------------------


def test_beleg_zur_pruefung(make_session):
    unlesbar = quittung(
        status=BelegStatus.ZUR_PRUEFUNG,
        pruef_grund="OCR lieferte keinen Text",
        dateiname="scan.jpg",
        eingegangen_am=datetime(2026, 3, 20, 8, 0),
    )
    _anlegen(make_session, unlesbar)
    _lauf(make_session, "beleg_pruefen")
    (a,) = _aufgaben(make_session)
    assert a.objekt == Objekt("beleg", unlesbar.id)
    assert "scan.jpg" in a.titel and "OCR lieferte keinen Text" in a.beschreibung
    assert a.faellig_am == date(2026, 3, 30)
    from accounti.db.repository import aktualisiere_beleg

    with make_session() as s:
        aktualisiere_beleg(
            s, unlesbar.model_copy(update={"status": BelegStatus.ERFASST})
        )
        s.commit()
    assert _lauf(make_session, "beleg_pruefen")["beleg_pruefen"].hinfaellig


def test_kontakt_zur_pruefung(make_session):
    k = Kontakt(
        name="Neuer Lieferant GmbH",
        kreditor_konto="70001",
        status=KontaktStatus.ZUR_PRUEFUNG,
        pruef_grund="automatisch angelegt aus Beleg",
    )
    _anlegen(make_session, k)
    _lauf(make_session, "kontakt_pruefen")
    (a,) = _aufgaben(make_session)
    assert a.objekt == Objekt("kontakt", k.id) and "70001" in a.beschreibung
    assert a.merkmale["rolle"] == "kreditor"


def test_bank_verlangt_freigabe(make_session):
    konto = Bankkonto(
        iban="DE12345678901234567890",
        bezeichnung="Giro",
        zustand=KontoZustand.FREIGABE_NOETIG,
        meldung="TAN-Freigabe nötig",
        letzter_abruf=datetime(2026, 3, 30, 5, 0),
    )
    _anlegen(make_session, konto)
    _lauf(make_session, "bank_freigabe")
    (a,) = _aufgaben(make_session)
    assert a.prioritaet is Prioritaet.HOCH and a.faellig_am == STICHTAG
    assert a.merkmale["bankkonto"] == "DE12345678901234567890"
    from accounti.db.repository import aktualisiere_bankkonto

    with make_session() as s:
        aktualisiere_bankkonto(
            s, konto.model_copy(update={"zustand": KontoZustand.BEREIT})
        )
        s.commit()
    (zu,) = _lauf(make_session, "bank_freigabe")["bank_freigabe"].hinfaellig
    assert zu.status is AufgabenStatus.HINFAELLIG


# --- Registry -------------------------------------------------------------------


def test_registry_und_abschalten(make_session):
    assert {
        "kontierung_pruefen",
        "beleg_fehlt",
        "beleg_pruefen",
        "kontakt_pruefen",
        "bank_freigabe",
    } <= set(PRUEFLAEUFE)
    with pytest.raises(AufgabenError, match="Unbekannter Prüflauf"):
        _lauf(make_session, "gibt_es_nicht")
    aus = AufgabenEinstellungen.model_validate(
        {"pruefung": {"abgeschaltet": ["beleg_fehlt"]}}
    )
    _anlegen(make_session, umsatz())
    assert "beleg_fehlt" not in _lauf(make_session, einstellungen=aus)
    # ausdrücklich genannt läuft er trotzdem
    assert "beleg_fehlt" in _lauf(make_session, "beleg_fehlt", einstellungen=aus)


def test_eigener_prueflauf_eines_anderen_bausteins(make_session):
    class Fristen:
        name = "frist_ustva"
        beschreibung = "USt-Voranmeldung abgeben"
        grund_entfallen = "Voranmeldung abgegeben"

        def __init__(self):
            self.offen = True

        def finde(self, session, einstellungen, stichtag, zeitraum):
            anlaesse = []
            if self.offen:
                anlaesse.append(
                    Anlass(
                        Objekt("frist", "ustva-2026-03"),
                        titel="USt-Voranmeldung 03/2026",
                        faellig_am=date(2026, 4, 10),
                        prioritaet=Prioritaet.HOCH,
                    )
                )
            return Pruefergebnis(anlaesse)

    lauf = Fristen()
    registriere_prueflauf(lauf)
    try:
        assert _lauf(make_session, "frist_ustva")["frist_ustva"].neu
        lauf.offen = False
        (a,) = _lauf(make_session, "frist_ustva")["frist_ustva"].hinfaellig
        assert a.abschluss_grund == "Voranmeldung abgegeben"
    finally:
        PRUEFLAEUFE.pop("frist_ustva")
