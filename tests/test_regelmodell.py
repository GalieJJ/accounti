"""Ein Regelmodell für gelernte Regeln, Regeldatei und Standardregeln (Zusammenführung
von Baustein 10b mit Paket B „Kontierung“).

Gleiche Richtungswerte (``ausgabe``/``einnahme``), dieselbe Gegenbuchung zur Prüfung,
dieselbe Schranke des Mappers — und der Vorrang gelernt → Regeldatei → Standardregeln
im Kontenrahmen der Buchhaltung.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from accounti.buchung.kontierung import kontiere_umsaetze
from accounti.db.repo_kontierung import lade_kontierungsgrund
from accounti.db.repository import lade_buchungen
from accounti.klassifikation.engine import (
    RICHTUNGEN,
    KlassifikationsEngine,
    Regel,
)
from accounti.klassifikation.lernen import (
    entwurf_fuer,
    lade_regelwerk,
    lerne,
    lerne_regex,
    regel_aus_db,
    uebernehme_aus_datei,
)
from accounti.klassifikation.regeln_loader import lade_regeln
from accounti.konfiguration import Buchhaltung
from accounti.models import BuchungStatus
from accounti.models.kontierung import Richtung
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    make_session_fixture,
    umsatz,
)

BH = Buchhaltung()
SKR04 = Buchhaltung(kontenrahmen="SKR04", bank_konto="1800")


def telekom(betrag: str, zweck: str = "Rechnung 10/2026") -> object:
    return umsatz(betrag, date(2026, 10, 5), zweck, "Telekom Deutschland GmbH")


def test_richtungswerte_gleich():
    """Datenbank (``Richtung``), Regeldatei und Standardregeln: dieselben Werte."""
    assert tuple(r.value for r in Richtung) == RICHTUNGEN
    for wert in RICHTUNGEN:
        assert Regel("x", "x", "4920", "1200", richtung=wert).richtung == wert
    # „beide“ heißt in der Regeldatei wie in der Übernahme: ohne Richtung
    assert Regel("x", "x", "4920", "1200", richtung="beide").richtung is None


def test_vorrang_gelernt_regeldatei_standard_des_kontenrahmens(make_session, tmp_path):
    datei = tmp_path / "regeln.yaml"
    datei.write_text(
        "- name: eigene_telekom\n  muster: telekom\n  feld: beide\n"
        "  richtung: ausgabe\n  soll_konto: '6805'\n  haben_konto: '1800'\n",
        encoding="utf-8",
    )
    with make_session() as s:
        lerne_regex(
            s, "gelernt_telekom", "telekom", "6810", "1800", 9, "jan",
            richtung=Richtung.AUSGABE,
        )  # fmt: skip
        s.commit()
        werk = lade_regelwerk(s, datei, "automatisch", buchhaltung=SKR04)
    namen = [r.name for r in werk.regeln]
    assert namen[:2] == ["gelernt_telekom", "eigene_telekom"]
    # dahinter die Standardregeln im SKR04 mit dem Bankkonto der Buchhaltung
    versicherung = next(r for r in werk.regeln if r.name == "versicherung")
    assert (versicherung.soll_konto, versicherung.haben_konto) == ("6400", "1800")
    e = werk.klassifiziere(telekom("-59.50"))
    assert e is not None and e.regel == "gelernt_telekom" and e.soll_konto == "6810"
    # ohne Buchhaltung: SKR03 wie bisher
    with make_session() as s:
        standard = lade_regelwerk(s, None, "aus")
    assert [r.haben_konto for r in standard.regeln if r.name == "miete"] == ["1200"]


def test_gelernte_regel_gegenrichtung_als_gegenbuchung_zur_pruefung(make_session):
    """Die Erstattung derselben Gegenpartei auf eine gelernte Ausgaberegel: keine
    zweite Ausgabe, sondern die Gegenbuchung — Soll/Haben getauscht, zur Prüfung
    (§ 17 Abs. 1 Satz 2 UStG), mit der Regel im Kontierungsgrund."""
    gutschrift = telekom("119.00", "Gutschrift Rechnung 09/2026")
    anlegen(make_session, gutschrift)
    with make_session() as s:
        lerne(s, entwurf_fuer(telekom("-59.50"), "4920", "1200", 9, BH), "jan")
        s.commit()
    with make_session() as s:
        werk = lade_regelwerk(s, None, buchhaltung=BH)
        lauf = kontiere_umsaetze(s, KlassifikationsEngine(regelwerk=werk), BH)
        s.commit()
        (b,) = lade_buchungen(s)
        grund = lade_kontierungsgrund(s, b.id)
    assert lauf.kontiert == 1
    assert (b.soll_konto, b.haben_konto) == ("1200", "4920")
    assert b.status is BuchungStatus.ZUR_PRUEFUNG and b.confidence <= 0.5
    assert grund is not None and grund.regel == "gelernt_telekom_deutschland"
    assert "Gegenbuchung" in grund.begruendung


def test_schranke_greift_fuer_gelernte_regel_ohne_richtung(make_session):
    """``accounti lerne`` ohne ``--richtung``: Die Regel trifft auch die Erstattung —
    der Mapper tauscht die Seiten (Bank im Soll bei einem Eingang) und legt sie zur
    Prüfung vor; der Grund nennt die Schranke."""
    erstattung = telekom("119.00", "Erstattung Telekom")
    anlegen(make_session, erstattung)
    with make_session() as s:
        lerne_regex(s, "telekom", "telekom", "4920", "1200", 9, "jan", feld="beide")
        s.commit()
    with make_session() as s:
        werk = lade_regelwerk(s, None, buchhaltung=BH)
        assert werk.regeln[0].richtung is None
        kontiere_umsaetze(s, KlassifikationsEngine(regelwerk=werk), BH)
        s.commit()
        (b,) = lade_buchungen(s)
        grund = lade_kontierungsgrund(s, b.id)
    assert (b.soll_konto, b.haben_konto) == ("1200", "4920")
    assert b.status is BuchungStatus.ZUR_PRUEFUNG
    assert b.steuer_betrag == Decimal("19.00")  # mindert die Vorsteuer
    assert grund is not None and grund.regel == "telekom"
    assert "Soll und Haben getauscht" in grund.begruendung


def test_einstellung_pruefen_setzt_das_pruefkennzeichen(make_session):
    with make_session() as s:
        r = lerne(s, entwurf_fuer(telekom("-59.50"), "4920", "1200", 9, BH), "jan")
        s.commit()
    regel = regel_aus_db(r, "pruefen")
    assert regel.pruefen and regel.richtung == "ausgabe"
    e = regel.ergebnis(telekom("-59.50"))
    assert e.pruefen and "Einstellung: prüfen" in e.begruendung
    assert not regel_aus_db(r).pruefen


def test_uebernahme_beide_ohne_richtung(make_session, tmp_path):
    datei = tmp_path / "regeln.yaml"
    datei.write_text(
        "- name: gelernt_telekom\n  muster: telekom\n  richtung: beide\n"
        "  soll_konto: '4920'\n  haben_konto: '1200'\n"
        "- name: gelernt_aral\n  muster: aral\n"
        "  soll_konto: '4530'\n  haben_konto: '1200'\n",
        encoding="utf-8",
    )
    assert [r.richtung for r in lade_regeln(datei)] == [None, None]
    with make_session() as s:
        u = uebernehme_aus_datei(s, datei, "jan", probe=True)
    assert u.uebernommen == ["gelernt_telekom", "gelernt_aral"] and not u.ungueltig
    # ausdrücklich „beide“ bleibt ohne Richtung, sonst die Richtung der Bankseite
    assert u.ohne_richtung == ["gelernt_telekom"]
