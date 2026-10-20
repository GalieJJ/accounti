"""Lieferschwelle § 3c Abs. 4 UStG: Vorjahr und laufendes Jahr, Jahr je Posten.

Die Schwelle von 10.000 € gilt nur, wenn sie im vorangegangenen Kalenderjahr nicht
überschritten wurde **und** im laufenden nicht überschritten wird. Ohne
OSS-Registrierung geht deshalb nach einem Vorjahr über 10.000 € schon der erste
EU-Fernverkauf im Januar zur Prüfung.
"""

from dataclasses import replace
from decimal import Decimal

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_buchungen
from accounti.integrationen.einstellungen import Integrationen, lade_integrationen
from accounti.integrationen.lauf import Kontext, eu_fernverkaeufe, importiere
from accounti.konfiguration import Buchhaltung
from accounti.models import BuchungStatus

D = Decimal

EBAY_KOPF = (
    '"Datum der Transaktionserstellung";"Typ";"Bestellnummer";"Versandziel - Land";'
    '"Betrag abzügl. Kosten";"Auszahlungswährung";"Auszahlungsdatum";'
    '"Auszahlung Nr.";"Transaktionsbetrag (inkl. Kosten)";"Beschreibung"'
)


def ebay_bericht(*zeilen: tuple[str, str, str, str, str, str, str]) -> bytes:
    """(Datum, Typ, Bestellnummer, Land, Betrag, Auszahlung Nr., Auszahlungsdatum)."""
    text = [EBAY_KOPF]
    for datum, typ, bestellung, land, betrag, nummer, auszahlungsdatum in zeilen:
        werte = [
            datum,
            typ,
            bestellung,
            land,
            betrag,
            "EUR",
            auszahlungsdatum,
            nummer,
            betrag if typ == "Bestellung" else "",
            "",
        ]
        text.append(";".join(f'"{w}"' for w in werte))
    return ("\r\n".join(text) + "\r\n").encode("utf-8")


@pytest.fixture
def umgebung(tmp_path):
    engine, make = session_factory(f"sqlite:///{tmp_path / 'l.db'}")
    init_db(engine)
    kontext = Kontext(
        einstellungen=lade_integrationen(tmp_path / "keine.yaml"),
        buchhaltung=Buchhaltung(),
        oss_registriert=False,
    )
    with make() as s:
        yield s, BelegArchiv(tmp_path / "archiv"), kontext


def fr_buchung(session, bestellung):
    (b,) = [
        b
        for b in lade_buchungen(session)
        if b.beleg_nummer == bestellung and b.haben_konto == "8400"
    ]
    return b


def test_vorjahr_ueber_der_schwelle_erster_januarverkauf_zur_pruefung(umgebung):
    s, archiv, kontext = umgebung
    vorjahr = ebay_bericht(
        ("10.12.2025", "Bestellung", "25-1", "Frankreich", "17850,00", "P25", ""),
        ("15.12.2025", "Auszahlung", "", "", "-17850,00", "P25", "15.12.2025"),
    )
    importiere(s, archiv, kontext, "ebay", vorjahr, "2025.csv")
    assert eu_fernverkaeufe(s, "DE")[2025] == D("15000.00")
    januar = ebay_bericht(
        ("05.01.2026", "Bestellung", "26-1", "Frankreich", "119,00", "P26", ""),
        ("08.01.2026", "Auszahlung", "", "", "-119,00", "P26", "08.01.2026"),
    )
    (ergebnis,) = importiere(s, archiv, kontext, "ebay", januar, "2026.csv")
    (befund,) = [b for b in ergebnis.abrechnung.befunde if b.code == "lieferschwelle"]
    assert "Vorjahr" in befund.text and "26-1" in befund.text
    assert fr_buchung(s, "26-1").status is BuchungStatus.ZUR_PRUEFUNG


def test_jahr_je_posten_nicht_je_abrechnung(umgebung):
    """Abrechnung über den Jahreswechsel: der Januar-Posten zählt zum neuen Jahr."""
    s, archiv, kontext = umgebung
    neues_jahr = ebay_bericht(
        ("10.01.2026", "Bestellung", "26-1", "Frankreich", "11840,50", "PA", ""),
        ("12.01.2026", "Auszahlung", "", "", "-11840,50", "PA", "12.01.2026"),
    )
    importiere(s, archiv, kontext, "ebay", neues_jahr, "a.csv")  # 9.950 € netto
    wechsel = ebay_bericht(
        ("28.12.2025", "Bestellung", "25-9", "Deutschland", "59,50", "PB", ""),
        ("03.01.2026", "Bestellung", "26-2", "Frankreich", "119,00", "PB", ""),
        ("05.01.2026", "Auszahlung", "", "", "-178,50", "PB", "05.01.2026"),
    )
    (ergebnis,) = importiere(s, archiv, kontext, "ebay", wechsel, "b.csv")
    assert ergebnis.abrechnung.von.year == 2025
    assert any(b.code == "lieferschwelle" for b in ergebnis.abrechnung.befunde)
    assert fr_buchung(s, "26-2").status is BuchungStatus.ZUR_PRUEFUNG
    assert eu_fernverkaeufe(s, "DE") == {2026: D("10050.00")}


def test_vorjahreswert_aus_der_konfiguration(umgebung, tmp_path):
    """Fehlen die Vorjahresdaten in accounti, zählt der eingestellte Wert."""
    s, archiv, kontext = umgebung
    pfad = tmp_path / "c.yaml"
    pfad.write_text(
        "integrationen:\n  eu_fernverkaeufe_sonstige:\n    2025: 12000\n",
        encoding="utf-8",
    )
    kontext = replace(kontext, einstellungen=lade_integrationen(pfad))
    assert kontext.einstellungen.eu_fernverkaeufe_sonstige == {2025: D("12000")}
    januar = ebay_bericht(
        ("05.01.2026", "Bestellung", "26-1", "Frankreich", "119,00", "P26", ""),
        ("08.01.2026", "Auszahlung", "", "", "-119,00", "P26", "08.01.2026"),
    )
    (ergebnis,) = importiere(s, archiv, kontext, "ebay", januar, "2026.csv")
    assert any(b.code == "lieferschwelle" for b in ergebnis.abrechnung.befunde)
    assert fr_buchung(s, "26-1").status is BuchungStatus.ZUR_PRUEFUNG


def test_unter_der_schwelle_kein_befund(umgebung):
    s, archiv, kontext = umgebung
    januar = ebay_bericht(
        ("05.01.2026", "Bestellung", "26-1", "Frankreich", "119,00", "P26", ""),
        ("08.01.2026", "Auszahlung", "", "", "-119,00", "P26", "08.01.2026"),
    )
    (ergebnis,) = importiere(s, archiv, kontext, "ebay", januar, "2026.csv")
    assert not [b for b in ergebnis.abrechnung.befunde if b.code == "lieferschwelle"]
    assert fr_buchung(s, "26-1").status is BuchungStatus.AUTO_GEBUCHT


def test_standard_ohne_sonstige_fernverkaeufe():
    assert Integrationen().eu_fernverkaeufe_sonstige == {}
