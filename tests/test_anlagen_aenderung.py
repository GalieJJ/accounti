"""Anlagegut ändern, Abgang zurücknehmen (Gesamttest Abschluss B7).

Ein Tippfehler (6.000 statt 600) sperrte den Jahresabschluss dauerhaft: Anlagegut und
Abgang ließen sich nach dem Anlegen weder ändern noch zurücknehmen.
"""

from datetime import date
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from accounti.abschluss.pruefungen import kontext, pruefe_abschluss
from accounti.anlagen.abgang import AbgangError, buche_abgang
from accounti.anlagen.aenderung import aendere_anlage, nimm_abgang_zurueck
from accounti.anlagen.dienst import AnlageError
from accounti.anlagen.konfiguration import lade_anlagen
from accounti.anlagen.lauf import afa_lauf, freigeben
from accounti.cli import app
from accounti.db.repo_anlagen import lade_afa_vorgaenge, lade_anlage
from accounti.db.repository import lade_buchungen
from accounti.db.tabellen_abschluss import JahrGesperrtError
from accounti.models import BuchungStatus
from accounti.models.anlagen import AbgangArt, AfaArt
from accounti.pruefung.journal import lade_journal, pruefe_journal
from tests.abschluss_hilfe import anlegen, buche, datenbank

D = Decimal
J = 2026


@pytest.fixture
def make_session(tmp_path):
    yield from datenbank(tmp_path)


@pytest.fixture
def config(tmp_path):
    return tmp_path / "accounti.yaml"  # fehlt: Standards


@pytest.fixture
def einst(config):
    return lade_anlagen(config)


def _anlagen_befunde(make_session, config):
    with make_session() as s:
        return pruefe_abschluss(kontext(s, J, config), ["anlagen"])


def _monitor(make_session, kosten="6000"):
    """Zugang 600 € richtig gebucht, das Anlagegut mit Tippfehler angelegt."""
    buche(make_session, date(J, 3, 1), "0420", "1200", "600")
    return anlegen(
        make_session, kosten, date(J, 3, 1), nd=13, konto="0420", bezeichnung="Monitor"
    )


def _afa(make_session, einst, freigabe=True, bis_monat=12):
    with make_session() as s:
        lauf = afa_lauf(s, J, einst, bis_monat)
        if freigabe:
            freigeben(s, J, "pruefer")
        s.commit()
    return lauf


def _gebucht(make_session, objekt):
    with make_session() as s:
        return sum(
            (v.betrag for v in lade_afa_vorgaenge(s, J) if v.objekt == objekt), D(0)
        )


def test_tippfehler_nach_freigegebener_afa_wird_per_korrektur_behoben(
    make_session, einst, config
):
    a = _monitor(make_session)
    _afa(make_session, einst)
    assert _anlagen_befunde(make_session, config)  # Saldo ≠ Restbuchwert
    with make_session() as s:
        e = aendere_anlage(s, "1", einst, kosten=D("600"), grund="Tippfehler 6000")
        s.commit()
    assert e.geaendert == {"anschaffungskosten": (D("6000"), D("600"))}
    nb = e.neuberechnung
    assert nb.verworfen == []  # die freigegebene AfA bleibt stehen
    (korrektur,) = nb.buchungen
    # 6.000/13 × 10/12 = 384,62 gebucht; Soll 600/13 × 10/12 = 38,46
    assert (korrektur.soll_konto, korrektur.haben_konto) == ("0420", "4830")
    assert korrektur.betrag_netto == D("346.16")
    assert korrektur.status is BuchungStatus.ZUR_PRUEFUNG
    assert _gebucht(make_session, a.objekt) == D("38.46")
    with make_session() as s:
        freigeben(s, J, "pruefer")
        s.commit()
    assert _anlagen_befunde(make_session, config) == []
    with make_session() as s:
        (eintrag,) = [
            x for x in lade_journal(s, objekt_id=str(a.id)) if x.objekt_typ == "anlage"
        ]
        assert eintrag.vorgang == "anlage_geaendert"
        assert eintrag.grund == "Tippfehler 6000"
        assert '"anschaffungskosten":"6000.00"' in eintrag.vorher
        assert '"anschaffungskosten":"600"' in eintrag.nachher
        assert pruefe_journal(s).in_ordnung


def test_vor_der_freigabe_wird_der_vorschlag_neu_gerechnet(make_session, einst):
    a = _monitor(make_session)
    (alt,) = _afa(make_session, einst, freigabe=False).buchungen
    with make_session() as s:
        e = aendere_anlage(
            s, "1", einst, kosten=D("600"), nutzungsdauer=10, grund="Rechnung"
        )
        s.commit()
        ids = {b.id for b in lade_buchungen(s)}
    assert [b.id for b in e.neuberechnung.verworfen] == [alt.id]
    assert alt.id not in ids
    (neu,) = e.neuberechnung.buchungen
    assert (neu.soll_konto, neu.haben_konto, neu.betrag_netto) == (
        "4830",
        "0420",
        D("50.00"),  # 600/10 × 10/12
    )
    assert _gebucht(make_session, a.objekt) == D("50.00")


def test_gemeinsame_afa_buchung_bleibt_und_wird_korrigiert(make_session, einst):
    """Eine AfA-Buchung für mehrere Güter wird nicht verworfen — korrigiert wird
    nur der Anteil des geänderten Guts."""
    a = _monitor(make_session)
    anlegen(make_session, "1300", date(J, 1, 1), nd=13, konto="0420")
    (gemeinsam,) = _afa(make_session, einst, freigabe=False).buchungen
    with make_session() as s:
        e = aendere_anlage(s, "1", einst, kosten=D("600"), grund="Tippfehler")
        s.commit()
        ids = {b.id for b in lade_buchungen(s)}
    assert e.neuberechnung.verworfen == [] and gemeinsam.id in ids
    (korrektur,) = e.neuberechnung.buchungen
    assert korrektur.buchungstext.startswith("AfA-Korrektur")
    assert _gebucht(make_session, a.objekt) == D("38.46")


def test_aendern_braucht_grund_und_offenes_jahr(make_session, einst):
    from accounti.db.repo_abschluss import setze_jahresabschluss
    from accounti.models.abschluss import Jahresabschluss

    _monitor(make_session)
    _afa(make_session, einst)
    with make_session() as s:
        with pytest.raises(AnlageError, match="Grund"):
            aendere_anlage(s, "1", einst, kosten=D("600"))
        with pytest.raises(AnlageError, match="nichts"):
            aendere_anlage(s, "1", einst, kosten=D("6000"), grund="x")
        # Bezeichnung ändert den AfA-Plan nicht: ohne Grund
        aendere_anlage(s, "1", einst, bezeichnung="Monitor 27 Zoll")
        setze_jahresabschluss(
            s,
            Jahresabschluss(
                jahr=J,
                gesperrt=True,
                gewinnermittlung="euer",
                ergebnis=D("0"),
                abgeschlossen_am=date(J + 1, 3, 1),
                von="chef",
            ),
        )
        s.commit()
    with make_session() as s, pytest.raises(JahrGesperrtError):
        aendere_anlage(s, "1", einst, kosten=D("600"), grund="zu spät")
    with make_session() as s:
        assert lade_anlage(s, "1").bezeichnung == "Monitor 27 Zoll"


def test_regelverstoss_bei_der_aenderung(make_session, einst):
    from accounti.anlagen.afa import AfaRegelError

    anlegen(make_session, "600", date(J, 3, 1), nd=5, konto="0420")
    with make_session() as s, pytest.raises(AfaRegelError):
        # GWG über der Grenze von 800 €
        aendere_anlage(
            s, "1", einst, kosten=D("5000"), art=AfaArt.GWG, grund="falsche Art"
        )


def test_zugangsbuchung_nachtraeglich_verknuepfen(make_session, einst):
    """Befund B11: verknüpfen geht auch nach dem Anlegen."""
    from accounti.anlagen.dienst import vorschlaege

    zugang = buche(make_session, date(J, 3, 1), "0420", "1200", "600")
    anlegen(make_session, "600", date(J, 3, 2), nd=13, konto="0420")
    with make_session() as s:
        assert [b.id for b in vorschlaege(s, einst, J)] == [zugang.id]
        aendere_anlage(s, "1", einst, buchung=str(zugang.id)[:8])
        s.commit()
        assert vorschlaege(s, einst, J) == []
        assert lade_anlage(s, "1").buchung_id == zugang.id


# --- Abgang zurücknehmen -------------------------------------------------------------


def _abgang(make_session, einst, tag=date(J, 4, 1)):
    with make_session() as s:
        e = buche_abgang(s, "1", tag, einst, AbgangArt.VERSCHROTTUNG)
        s.commit()
    return e


def test_abgang_mit_falschem_datum_zuruecknehmen(make_session, einst, config):
    a = _monitor(make_session, "600")
    _afa(make_session, einst)  # 10/12 freigegeben
    e = _abgang(make_session, einst, date(J, 4, 1))
    assert e.buchungen and e.afa.buchungen  # RBW-Vorschlag, AfA-Korrektur
    with make_session() as s:
        with pytest.raises(AbgangError, match="Grund"):
            nimm_abgang_zurueck(s, "1", einst, " ")
        r = nimm_abgang_zurueck(s, "1", einst, "Datum vertippt")
        s.commit()
        ids = {b.id for b in lade_buchungen(s)}
        assert pruefe_journal(s).in_ordnung
        (eintrag,) = [
            x
            for x in lade_journal(s, objekt_id=str(a.id))
            if x.vorgang == "anlage_abgang_zurueck"
        ]
        assert eintrag.grund == "Datum vertippt"
    verworfen = {b.id for b in r.neuberechnung.verworfen}
    assert verworfen == {b.id for b in [*e.buchungen, *e.afa.buchungen]}
    assert not verworfen & ids
    assert r.anlage.abgang_datum is None and r.neuberechnung.buchungen == []
    assert _gebucht(make_session, a.objekt) == D("38.46")
    assert _anlagen_befunde(make_session, config) == []
    with make_session() as s, pytest.raises(AbgangError, match="keinen Abgang"):
        nimm_abgang_zurueck(s, "1", einst, "nochmal")
    # jetzt mit dem richtigen Datum
    e = _abgang(make_session, einst, date(J, 12, 31))
    assert e.anlage.abgang_datum == date(J, 12, 31)


def test_freigegebener_abgang_erst_stornieren(make_session, einst):
    from accounti.pruefung.storno import freigeben as freigabe
    from accounti.pruefung.storno import storniere

    _monitor(make_session, "600")
    _afa(make_session, einst)
    e = _abgang(make_session, einst)
    (rbw,) = e.buchungen
    with make_session() as s:
        freigabe(s, str(rbw.id), von="chef")
        s.commit()
        with pytest.raises(AbgangError, match="storniere"):
            nimm_abgang_zurueck(s, "1", einst, "Irrtum")
    with make_session() as s:
        storniere(s, str(rbw.id), grund="Irrtum", von="chef")
        s.commit()
        r = nimm_abgang_zurueck(s, "1", einst, "Irrtum")
        s.commit()
    assert r.anlage.abgang_datum is None


def test_aendern_nach_abgang_erst_zuruecknehmen(make_session, einst):
    _monitor(make_session, "600")
    _abgang(make_session, einst)
    with make_session() as s, pytest.raises(AnlageError, match="--zuruecknehmen"):
        aendere_anlage(s, "1", einst, kosten=D("500"), grund="x")


# --- CLI (Repro des Gesamttests) ------------------------------------------------------


def test_cli_aendern_und_abgang_zuruecknehmen(tmp_path):
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    config = str(tmp_path / "accounti.yaml")
    runner = CliRunner()

    def run(*args):
        r = runner.invoke(
            app, [*args, "--db", url, "--config", config], env={"COLUMNS": "200"}
        )
        return r, " ".join(r.output.split())

    r, _ = run(
        "anlagen", "anlegen", "--bezeichnung", "Monitor", "--datum", "2026-03-01",
        "--kosten", "6000", "--nutzungsdauer", "13", "--art", "linear",
        "--konto", "0420",
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    run("anlagen", "afa", "--jahr", "2026")
    run("anlagen", "freigeben", "--jahr", "2026", "--von", "t")
    r, text = run("anlagen", "aendern", "1", "--kosten", "600")
    assert r.exit_code == 1 and "Grund" in text
    r, text = run("anlagen", "aendern", "1", "--kosten", "600", "--grund", "Tippfehler")
    assert r.exit_code == 0, r.output
    assert "6000.00 → 600" in text and "346,16" in text
    assert "anlagen freigeben --jahr 2026" in text
    r, text = run("anlagen", "abgang", "1", "--art", "verschrottung")
    assert r.exit_code == 1 and "--datum" in text
    r, _ = run(
        "anlagen", "abgang", "1", "--datum", "2026-04-01", "--art", "verschrottung"
    )
    assert r.exit_code == 0, r.output
    r, text = run("anlagen", "abgang", "1", "--zuruecknehmen", "--grund", "Datum")
    assert r.exit_code == 0, r.output
    assert "zurückgenommen" in text and "01.04.2026" in text
    r, _ = run(
        "anlagen", "abgang", "1", "--datum", "2026-12-31", "--art", "verschrottung"
    )
    assert r.exit_code == 0, r.output


def test_cli_betrachter_darf_nicht_aendern_und_zuruecknehmen(tmp_path, monkeypatch):
    """Rollenmodell: ändern und zurücknehmen erzeugen bzw. verwerfen Vorschläge —
    Recht *buchen* mit Einmalcode, wie ``anlegen``/``abgang``."""
    from datetime import datetime

    from accounti.db import init_db, session_factory
    from accounti.models.auth import Rolle
    from tests.auth_hilfe import billige_hashes, lege_person_an, setze_schluessel

    billige_hashes(monkeypatch)
    setze_schluessel(monkeypatch)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    url = f"sqlite:///{(tmp_path / 'r.db').as_posix()}"
    engine, fabrik = session_factory(url)
    init_db(engine)
    anlegen(fabrik, "600", date(J, 3, 1), nd=13, konto="0420")
    with fabrik() as s:
        lege_person_an(s, "jan", Rolle.BETRACHTER, jetzt=datetime.now())
    engine.dispose()
    for befehl in (
        ["aendern", "1", "--kosten", "500", "--grund", "x"],
        ["abgang", "1", "--zuruecknehmen", "--grund", "x"],
    ):
        r = CliRunner().invoke(
            app,
            ["anlagen", *befehl, "--von", "jan", "--db", url, "--config", "x.yaml"],
            env={"COLUMNS": "250"},
        )
        assert r.exit_code == 1, (befehl, r.output)
        assert "jan darf" in r.output, (befehl, r.output)


def test_hinweise_bei_kontowechsel_und_frueherem_datum(make_session, einst, config):
    """Nachprüfung F, N7: ``--konto`` nach gebuchter AfA ließ Zugang und AfA auf dem
    alten Konto (``pruefen``: zwei Fehler) und ``--datum`` ins Vorjahr die AfA des
    Vorjahres fehlen — beides ohne Hinweis."""
    _monitor(make_session, kosten="600")
    _afa(make_session, einst)  # 600/13 × 10/12 = 38,46
    with make_session() as s:
        e = aendere_anlage(s, "1", einst, konto="0410", grund="falsches Konto")
        s.commit()
    (hinweis,) = e.neuberechnung.hinweise
    assert "0420 → 0410" in hinweis and "561,54" in hinweis
    assert "korrigiere" in hinweis
    with make_session() as s:
        aendere_anlage(s, "1", einst, konto="0420", grund="zurück")
        e = aendere_anlage(
            s, "1", einst, datum=date(J - 1, 11, 1), grund="Datum falsch"
        )
        s.commit()
    assert any(
        f"AfA {J - 1} fehlt" in h and f"anlagen afa --jahr {J - 1}" in h
        for h in e.neuberechnung.hinweise
    )
