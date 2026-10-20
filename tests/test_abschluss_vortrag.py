"""Saldovortrag und Jahressperre (Akzeptanz 7)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import update

from accounti.abschluss.kassenbuch import anfangsbestand, buche_kasse
from accounti.abschluss.konfiguration import KassenEinstellungen
from accounti.abschluss.pruefungen import (
    erfasse_kontoauszugssaldo,
    kontext,
    pruefe_abschluss,
)
from accounti.abschluss.vortrag import (
    AbschlussError,
    AbschlussGesperrtError,
    erfasse_eroeffnung,
    eroeffnungssalden,
    oeffne,
    pruefe_protokoll,
    schlusssalden,
    trage_vor,
)
from accounti.anlagen.konfiguration import lade_anlagen
from accounti.anlagen.lauf import afa_lauf
from accounti.db.repo_abschluss import ist_gesperrt, lade_protokoll
from accounti.db.repository import (
    lade_buchungen,
    setze_status,
    speichere_bankkonto,
    speichere_buchung,
)
from accounti.db.tabellen import BuchungssatzRow, UnveraenderbarError
from accounti.db.tabellen_abschluss import JahrGesperrtError, ProtokollRow
from accounti.models import Bankkonto, Buchungssatz, BuchungStatus
from tests.abschluss_hilfe import anlegen, buche, datenbank

D = Decimal
IBAN = "DE02120300000000202051"


@pytest.fixture
def make_session(tmp_path):
    yield from datenbank(tmp_path)


@pytest.fixture
def config(tmp_path):
    return tmp_path / "accounti.yaml"


def _k(s, config, jahr=2026):
    return kontext(s, jahr, config)


@pytest.fixture
def jahr_2026(make_session, config):
    """Eröffnung, laufende Buchungen, abgestimmte Bank — bereit zum Abschluss."""
    with make_session() as s:
        speichere_bankkonto(s, Bankkonto(iban=IBAN, bezeichnung="Giro"))
        einst = _k(s, config).einstellungen
        erfasse_eroeffnung(s, 2026, "1200", D("10000"), "test", einst)
        erfasse_eroeffnung(s, 2026, "0880", D("-10000"), "test", einst)
        s.commit()
    buche(
        make_session,
        date(2026, 3, 1),
        "1200",
        "8400",
        "5000",
        steuer_schluessel=3,
        steuer_betrag=D("950"),
    )
    buche(make_session, date(2026, 4, 1), "4210", "1200", "1200")
    buche(make_session, date(2026, 5, 1), "1800", "1200", "1000")  # Entnahme
    buche(
        make_session,
        date(2026, 6, 1),
        "4930",
        "70001",
        "300",
        steuer_schluessel=9,
        steuer_betrag=D("57"),
    )  # offene Rechnung
    buche(
        make_session,
        date(2026, 7, 1),
        "10001",
        "8400",
        "800",
        steuer_schluessel=3,
        steuer_betrag=D("152"),
    )  # offene Forderung
    with make_session() as s:
        erfasse_kontoauszugssaldo(s, IBAN, date(2026, 12, 31), D("13750"))
        s.commit()


def _eb_2027(make_session, config):
    with make_session() as s:
        kr = _k(s, config).kontenrahmen
        return eroeffnungssalden(s, 2027, kr)


def test_akzeptanz_7_eroeffnung_gleich_schluss_und_vorjahr_gesperrt(
    make_session, config, jahr_2026
):
    with make_session() as s:
        k = _k(s, config)
        schluss = schlusssalden(s, 2026, k.einstellungen, k.kontenrahmen)
        vortrag = trage_vor(s, k, "E. Muster")
        s.commit()
    # Kapital = 10.000 + Ergebnis (5.000 + 950 − 1.200 + 800 + 152 − 300 − 57) − 1.000
    assert vortrag.ergebnis == D("5345")
    assert schluss == {
        "1200": D("13750"),
        "10001": D("952"),
        "70001": D("-357"),
        "0880": D("-14345"),
    }
    assert _eb_2027(make_session, config) == schluss  # exakt gleich
    assert sum(schluss.values()) == 0
    gegen = {(b.soll_konto, b.haben_konto) for b in vortrag.buchungen}
    assert ("10001", "9008") in gegen and ("9009", "70001") in gegen
    assert ("1200", "9000") in gegen and ("9000", "0880") in gegen
    assert all(b.datum == date(2027, 1, 1) for b in vortrag.buchungen)

    with make_session() as s:
        assert ist_gesperrt(s, 2026) and not ist_gesperrt(s, 2027)
        # anlegen, ändern, löschen im gesperrten Jahr scheitert
        speichere_buchung(
            s,
            Buchungssatz(
                datum=date(2026, 12, 31),
                soll_konto="4930",
                haben_konto="1200",
                betrag_netto=D("1"),
                buchungstext="zu spät",
            ),
        )
        with pytest.raises(JahrGesperrtError, match="2026"):
            s.flush()
    with make_session() as s:
        alt = next(b for b in lade_buchungen(s) if b.datum.year == 2026)
        setze_status(s, str(alt.id), BuchungStatus.EXPORTIERT)
        with pytest.raises(JahrGesperrtError):
            s.flush()
    with make_session() as s:
        s.delete(s.get(BuchungssatzRow, str(alt.id)))
        with pytest.raises(JahrGesperrtError):
            s.flush()
    # das neue Jahr ist offen und die Eröffnungsbilanz ausgeglichen
    buche(make_session, date(2027, 1, 2), "4930", "1200", "10")
    with make_session() as s:
        assert pruefe_abschluss(_k(s, config, 2027), nur=["vortragskonten"]) == []
    with make_session() as s:
        protokoll = lade_protokoll(s)
    assert [e.aktion for e in protokoll] == [
        "eroeffnung",
        "eroeffnung",
        "abgeschlossen",
    ]
    eintrag = protokoll[-1]
    assert (eintrag.jahr, eintrag.aktion, eintrag.von) == (
        2026,
        "abgeschlossen",
        "E. Muster",
    )


def test_fehler_befund_verhindert_den_vortrag(make_session, config, jahr_2026):
    buche(make_session, date(2026, 12, 30), "4970", "1200", "5")  # Bank passt nicht
    with make_session() as s, pytest.raises(AbschlussGesperrtError) as fehler:
        trage_vor(s, _k(s, config), "E. Muster")
    assert any(b.pruefung == "bank" for b in fehler.value.befunde)
    assert "Bank" in str(fehler.value)
    with make_session() as s:
        assert not ist_gesperrt(s, 2026)
    assert _eb_2027(make_session, config) == {}


def test_oeffnen_und_erneut_vortragen_bucht_nur_differenzen(
    make_session, config, jahr_2026
):
    with make_session() as s:
        trage_vor(s, _k(s, config), "E. Muster")
        s.commit()
    with make_session() as s, pytest.raises(AbschlussError, match="schon"):
        trage_vor(s, _k(s, config), "E. Muster")
    with make_session() as s, pytest.raises(AbschlussError, match="Grund"):
        oeffne(s, 2026, "E. Muster", " ")
    with make_session() as s:
        oeffne(s, 2026, "E. Muster", "Rechnung 4711 nachgebucht")
        s.commit()
    buche(make_session, date(2026, 12, 20), "4930", "70002", "200")
    with make_session() as s:
        zweiter = trage_vor(s, _k(s, config), "E. Muster")
        k = _k(s, config)
        schluss = schlusssalden(s, 2026, k.einstellungen, k.kontenrahmen)
        s.commit()
    # nur die Änderung: neuer Kreditor und Kapital
    assert sorted(
        (b.soll_konto, b.haben_konto, b.betrag_netto) for b in zweiter.buchungen
    ) == [
        ("0880", "9000", D("200")),
        ("9009", "70002", D("200")),
    ]
    assert _eb_2027(make_session, config) == schluss
    with make_session() as s:
        aktionen = [e.aktion for e in lade_protokoll(s) if e.aktion != "eroeffnung"]
        assert aktionen == ["abgeschlossen", "geoeffnet", "abgeschlossen"]
        assert pruefe_protokoll(s) == []


def test_oeffnen_nur_wenn_folgejahr_offen(make_session, config, jahr_2026):
    with make_session() as s:
        trage_vor(s, _k(s, config), "E. Muster")
        s.commit()
    with (
        make_session() as s,
        pytest.raises(AbschlussError, match="nicht abgeschlossen"),
    ):
        oeffne(s, 2027, "E. Muster", "Test")
    with make_session() as s:
        erfasse_kontoauszugssaldo(s, IBAN, date(2027, 12, 31), D("13750"))
        trage_vor(s, _k(s, config, 2027), "E. Muster")
        s.commit()
    with make_session() as s, pytest.raises(AbschlussError, match="2027"):
        oeffne(s, 2026, "E. Muster", "Test")


def test_protokoll_ist_unveraenderbar(make_session, config, jahr_2026):
    with make_session() as s:
        trage_vor(s, _k(s, config), "E. Muster")
        s.commit()
    with make_session() as s:
        row = s.get(ProtokollRow, 1)
        row.von = "jemand anderes"
        with pytest.raises(UnveraenderbarError):
            s.flush()
    with make_session() as s, pytest.raises(Exception, match="unveränderbar"):
        s.execute(update(ProtokollRow).values(von="x"))


def test_eroeffnung(make_session, config):
    with make_session() as s:
        einst = _k(s, config).einstellungen
        assert erfasse_eroeffnung(s, 2026, "1200", D("5000"), "t", einst) is not None
        assert erfasse_eroeffnung(s, 2026, "1200", D("5000"), "t", einst) is None
        korrektur = erfasse_eroeffnung(s, 2026, "1200", D("6000"), "t", einst)
        assert (
            korrektur.soll_konto,
            korrektur.haben_konto,
            korrektur.betrag_netto,
        ) == (
            "1200",
            "9000",
            D("1000"),
        )
        with pytest.raises(AbschlussError, match="Bestandskonto"):
            erfasse_eroeffnung(s, 2026, "4930", D("1"), "t", einst)
        s.commit()
        assert eroeffnungssalden(s, 2026, _k(s, config).kontenrahmen) == {
            "1200": D("6000")
        }


def test_eroeffnung_nach_vortrag_gesperrt(make_session, config, jahr_2026):
    with make_session() as s:
        trage_vor(s, _k(s, config), "E. Muster")
        s.commit()
    with make_session() as s, pytest.raises(AbschlussError, match="Saldovortrag"):
        erfasse_eroeffnung(s, 2027, "1000", D("50"), "t", _k(s, config).einstellungen)
    with make_session() as s, pytest.raises(JahrGesperrtError):
        erfasse_eroeffnung(s, 2026, "1000", D("50"), "t", _k(s, config).einstellungen)


def test_kasse_und_afa_im_gesperrten_jahr(make_session, config, jahr_2026):
    kasse = KassenEinstellungen(konto="1000")
    with make_session() as s:
        anfangsbestand(s, D("100"), date(2026, 1, 1), kasse)
        s.commit()
    with make_session() as s:
        erfasse_eroeffnung(s, 2026, "1000", D("100"), "t", _k(s, config).einstellungen)
        erfasse_eroeffnung(
            s, 2026, "0880", D("-10100"), "t", _k(s, config).einstellungen
        )
        trage_vor(s, _k(s, config), "E. Muster")
        s.commit()
    with make_session() as s, pytest.raises(JahrGesperrtError):
        buche_kasse(s, D("-5"), "Porto", kasse, date(2026, 12, 31))
    with make_session() as s:
        buche_kasse(s, D("-5"), "Porto", kasse, date(2027, 1, 3))
        s.commit()
    anlegen(make_session, 1300, date(2026, 1, 1), nd=13)
    with make_session() as s, pytest.raises(JahrGesperrtError):
        afa_lauf(s, 2026, lade_anlagen(config))


def test_sperre_gilt_fuer_jeden_cli_befehl():
    """Auch Befehle ohne init_db (z. B. bestaetige, korrigiere) laden die Sperre."""
    import subprocess
    import sys

    pruefung = (
        "import sys, accounti.cli; "
        "print('accounti.db.tabellen_abschluss' in sys.modules)"
    )
    ergebnis = subprocess.run(
        [sys.executable, "-c", pruefung],
        capture_output=True,
        text=True,
        check=True,
    )
    assert ergebnis.stdout.strip() == "True"
