"""Saldovortrag und Jahressperre (Akzeptanz 7)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import update

from accounti.abschluss.kassenbuch import anfangsbestand, buche_kasse
from accounti.abschluss.konfiguration import KassenEinstellungen
from accounti.abschluss.protokoll import pruefe_protokoll
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
    # ein Zugang im abgeschlossenen Jahr änderte dessen Anlagenspiegel
    from accounti.anlagen.dienst import lege_an

    with make_session() as s, pytest.raises(JahrGesperrtError):
        lege_an(
            s,
            lade_anlagen(config),
            bezeichnung="Regal",
            datum=date(2026, 12, 1),
            kosten=D("1300"),
            konto="0420",
            nutzungsdauer=13,
        )


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


def test_interimskonten_im_ust_bereich_werden_vorgetragen(make_session, config):
    buche(make_session, date(2026, 3, 2), "1792", "1200", "500")
    buche(make_session, date(2026, 3, 3), "1200", "1795", "300")
    with make_session() as s:
        k = _k(s, config)
        schluss = schlusssalden(s, 2026, k.einstellungen, k.kontenrahmen)
    assert schluss == {"1200": D("-200"), "1792": D("500"), "1795": D("-300")}


def test_skr04_privatkonten_und_gewerbesteuerforderung(make_session, tmp_path):
    from accounti.abschluss.euer import erstelle_euer

    config = tmp_path / "skr04.yaml"
    config.write_text("buchhaltung:\n  kontenrahmen: SKR04\n", encoding="utf-8")
    buche(make_session, date(2026, 3, 1), "1800", "4400", "1000")
    buche(make_session, date(2026, 3, 2), "2250", "1800", "100")  # Spende
    buche(make_session, date(2026, 3, 3), "2200", "1800", "40")  # Sonderausgabe
    buche(make_session, date(2026, 3, 4), "2500", "1800", "50")  # Entnahme Teilhafter
    buche(make_session, date(2026, 3, 5), "1435", "1800", "200")  # GewSt-Überzahlung
    with make_session() as s:
        k = _k(s, config)
        schluss = schlusssalden(s, 2026, k.einstellungen, k.kontenrahmen)
        euer = erstelle_euer(k.susa, k.kontenrahmen)
    assert schluss == {"1435": D("200"), "1800": D("610"), "2010": D("-810")}
    assert euer.entnahmen == D("190")
    assert euer.zeile("185") is None  # keine Vorsteuer
    assert euer.gewinn == D("1000")


def _sperre(make_session, jahr):
    from datetime import datetime

    from accounti.db.repo_abschluss import setze_jahresabschluss
    from accounti.models.abschluss import Jahresabschluss

    with make_session() as s:
        setze_jahresabschluss(
            s,
            Jahresabschluss(
                jahr=jahr,
                gesperrt=True,
                gewinnermittlung="euer",
                ergebnis=D("0"),
                abgeschlossen_am=datetime.now(),
                von="test",
            ),
        )
        s.commit()


def test_classify_ueberspringt_umsaetze_im_gesperrten_jahr(tmp_path):
    """Ein spät importierter Dezember-Umsatz hält die Kontierung 2027 nicht auf."""
    from typer.testing import CliRunner

    from accounti.cli import app
    from accounti.db import init_db, session_factory
    from accounti.db.repository import speichere_transaktion
    from accounti.models import Transaktion, TransaktionQuelle

    url = f"sqlite:///{(tmp_path / 'c.db').as_posix()}"
    engine, factory = session_factory(url)
    init_db(engine)
    _sperre(factory, 2026)
    with factory() as s:
        for tag in (date(2026, 12, 30), date(2027, 1, 5)):
            speichere_transaktion(
                s,
                Transaktion(
                    datum=tag,
                    betrag=D("-800"),
                    verwendungszweck=f"Miete Büro {tag:%m/%Y}",
                    quelle=TransaktionQuelle.BANK,
                    rohtext="test",
                ),
            )
        s.commit()
    r = CliRunner().invoke(
        app,
        ["classify", "--db", url, "--no-llm", "--config", str(tmp_path / "x.yaml")],
    )
    assert r.exit_code == 0, r.output
    with factory() as s:
        assert [b.datum for b in lade_buchungen(s)] == [date(2027, 1, 5)]
    engine.dispose()


def _rechnungen_um_den_jahreswechsel(make_session):
    """Eine Eingangsrechnung vom Dezember 2026 und eine vom Januar 2027."""
    from accounti.db.repository import speichere_beleg
    from tests.test_opos_verbuchung import eingangsrechnung

    alt = eingangsrechnung(
        belegnummer="RE-ALT",
        belegdatum=date(2026, 12, 20),
        zahlungsziel=date(2027, 1, 3),
        datei_hash="b" * 64,
    )
    neu = eingangsrechnung(
        belegnummer="RE-NEU",
        belegdatum=date(2027, 1, 10),
        zahlungsziel=date(2027, 1, 24),
        datei_hash="c" * 64,
    )
    with make_session() as s:
        speichere_beleg(s, alt)
        speichere_beleg(s, neu)
        s.commit()
    return alt, neu


def test_verbuchen_laesst_rechnungen_im_gesperrten_jahr_liegen(make_session):
    """Eine Rechnung im abgeschlossenen Jahr bricht den Lauf nicht ab."""
    from accounti.db.repository import lade_posten
    from accounti.opos.verbuchung import verbuche_belege
    from tests.test_opos_verbuchung import EINSTELLUNGEN

    _sperre(make_session, 2026)
    alt, neu = _rechnungen_um_den_jahreswechsel(make_session)
    with make_session() as s:
        lauf = verbuche_belege(s, EINSTELLUNGEN)
        s.commit()
    assert [v.beleg.id for v in lauf.verbucht] == [neu.id]
    ((beleg, grund),) = lauf.fehler
    assert beleg.id == alt.id
    assert "20.12.2026" in grund and "abgeschlossen" in grund
    assert "oeffnen --jahr 2026" in grund
    with make_session() as s:
        assert {b.datum for b in lade_buchungen(s)} == {date(2027, 1, 10)}
        assert [p.belegnummer for p in lade_posten(s)] == ["RE-NEU"]
    # nach dem Öffnen des Jahres lässt sich die Rechnung verbuchen
    with make_session() as s:
        oeffne(s, 2026, grund="Rechnung nachgereicht", von="test")
        s.commit()
    with make_session() as s:
        lauf = verbuche_belege(s, EINSTELLUNGEN)
        s.commit()
    assert [v.beleg.id for v in lauf.verbucht] == [alt.id]
    assert lauf.fehler == []


def test_verbuchen_faengt_auch_die_orm_sperre_je_beleg_ab(make_session, monkeypatch):
    """Ohne die Vorprüfung greift die ORM-Sperre — nur im Savepoint des Belegs."""
    import accounti.opos.verbuchung as verbuchung
    from tests.test_opos_verbuchung import EINSTELLUNGEN

    monkeypatch.setattr(verbuchung, "ist_gesperrt", lambda *_: False)
    _sperre(make_session, 2026)
    alt, neu = _rechnungen_um_den_jahreswechsel(make_session)
    with make_session() as s:
        lauf = verbuchung.verbuche_belege(s, EINSTELLUNGEN)
        s.commit()
    assert [v.beleg.id for v in lauf.verbucht] == [neu.id]
    ((beleg, grund),) = lauf.fehler
    assert beleg.id == alt.id and "2026 ist abgeschlossen" in grund
    with make_session() as s:
        assert {b.datum for b in lade_buchungen(s)} == {date(2027, 1, 10)}


def test_cli_opos_verbuchen_im_gesperrten_jahr_ohne_abbruch(tmp_path):
    from typer.testing import CliRunner

    from accounti.cli import app
    from accounti.db import init_db, session_factory

    url = f"sqlite:///{(tmp_path / 'v.db').as_posix()}"
    engine, factory = session_factory(url)
    init_db(engine)
    _sperre(factory, 2026)
    _rechnungen_um_den_jahreswechsel(factory)
    r = CliRunner().invoke(
        app,
        [
            "opos",
            "verbuchen",
            "--db",
            url,
            "--archiv",
            str(tmp_path / "archiv"),
            "--config",
            str(tmp_path / "x.yaml"),
        ],
    )
    assert r.exit_code == 0, r.output
    assert r.exception is None
    assert "Nicht verbucht" in r.output and "RE-ALT" in r.output
    with factory() as s:
        assert {b.datum for b in lade_buchungen(s)} == {date(2027, 1, 10)}
    engine.dispose()


def test_ungebuchte_umsaetze_in_gesperrten_vorjahren_werden_gemeldet(
    make_session, config
):
    from accounti.abschluss.pruefungen import Schwere
    from accounti.db.repository import speichere_transaktion
    from accounti.models import Transaktion, TransaktionQuelle

    _sperre(make_session, 2026)
    with make_session() as s:
        speichere_transaktion(
            s,
            Transaktion(
                datum=date(2026, 12, 30),
                betrag=D("-800"),
                verwendungszweck="Miete",
                quelle=TransaktionQuelle.BANK,
                rohtext="test",
            ),
        )
        s.commit()
    with make_session() as s:
        (b,) = pruefe_abschluss(_k(s, config, 2027), nur=["ungebucht"])
    assert b.schwere is Schwere.WARNUNG
    assert "2026" in b.text and "abgeschlossen" in b.text and "oeffnen" in b.text


def test_lange_freitexte_kuerzen_ohne_die_hash_kette_zu_brechen(
    make_session, config, jahr_2026
):
    from accounti.db.repo_abschluss import kontoauszugssaldo, lade_jahresabschluss

    with make_session() as s:
        k = erfasse_kontoauszugssaldo(s, IBAN, date(2026, 12, 31), D("13750"), "E" * 80)
        trage_vor(s, _k(s, config), "V" * 80)
        s.commit()
    with make_session() as s:
        oeffne(s, 2026, "O" * 80, "G" * 600)
        s.commit()
    with make_session() as s:
        eintraege = lade_protokoll(s)
        assert pruefe_protokoll(s) == []
        assert lade_jahresabschluss(s, 2026).von == "V" * 50
        gespeichert = kontoauszugssaldo(s, k.bankkonto_id, date(2026, 12, 31))
    assert gespeichert.erfasst_von == "E" * 50
    assert (eintraege[-1].von, eintraege[-1].grund) == ("O" * 50, "G" * 500)


def test_pruefung_protokoll_meldet_manipulation(make_session, config, jahr_2026):
    from sqlalchemy import text

    from accounti.abschluss.pruefungen import Schwere

    with make_session() as s:
        trage_vor(s, _k(s, config), "E. Muster")
        s.commit()
    with make_session() as s:
        assert pruefe_abschluss(_k(s, config, 2027), nur=["protokoll"]) == []
    with make_session() as s:  # an ORM und Trigger vorbei, wie rohes SQL unter Postgres
        s.execute(text("DROP TRIGGER abschlussprotokoll_kein_update"))
        s.execute(text("UPDATE abschlussprotokoll SET von = 'jemand' WHERE nr = 1"))
        s.commit()
    with make_session() as s:
        (b,) = pruefe_abschluss(_k(s, config, 2027), nur=["protokoll"])
    assert b.schwere is Schwere.WARNUNG
    assert "Eintrag 1 wurde verändert" in b.text


# --- Monatssperre und Saldovortrag (Baustein 7, Befund B-H3) -------------------------


def test_vortrag_in_einen_festgeschriebenen_januar(make_session, config, jahr_2026):
    """Der Januar ist mit der UStVA festgeschrieben, der Abschluss folgt später: Die
    EB-Werte am 01.01. tragen die Schlussbilanz vor und ändern weder Verkehrszahlen
    noch UStVA des Januars — sie nimmt die Monatssperre an, die Jahressperre nicht."""
    from accounti.pruefung.journal import pruefe_journal
    from accounti.pruefung.perioden import schliesse
    from tests.test_pruefung_regeln import pruefe

    with make_session() as s:
        schliesse(s, "2027-01", "erika", trotzdem=True)
        s.commit()
    with make_session() as s:
        vortrag = trage_vor(s, _k(s, config), "E. Muster")
        s.commit()
        assert vortrag.buchungen and all(
            b.datum == date(2027, 1, 1) for b in vortrag.buchungen
        )
        assert pruefe_journal(s).in_ordnung
        # eine gewöhnliche Buchung im Januar bleibt gesperrt
        speichere_buchung(
            s,
            Buchungssatz(
                datum=date(2027, 1, 1),
                soll_konto="4930",
                haben_konto="1200",
                betrag_netto=D("10"),
                buchungstext="nachgereicht",
                status=BuchungStatus.GEPRUEFT,
            ),
        )
        with pytest.raises(JahrGesperrtError, match="2027-01"):
            s.flush()
    befunde = pruefe(make_session, "buchung_in_gesperrter_periode", period="2027-01")
    assert befunde == []
