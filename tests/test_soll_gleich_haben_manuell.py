"""Soll = Haben von Hand (Gesamttest 10b-1, Runde 3: gegen:web:0, gw2-umbuchung N-3,
gw2-merge B3).

Die Nachbesserung H-1 schloss nur die automatischen Wege: Eine Korrektur „1200 an
1200“ auf einem Bankumsatz (Queue, ``/buchungen/{id}``, CLI ``korrigiere``) und
``kasse buchen --konto`` mit dem Kassenkonto buchten weiter — die Bewegung fehlte in den
Büchern (§ 239 Abs. 2 HGB, § 146 Abs. 1 AO), erst ``accounti pruefen`` meldete sie.
Ein Altvorschlag „1210 an 1210“ ließ sich ohne Hinweis freigeben. Jetzt lehnt die
Fachfunktion ab (``storno.korrigiere``, Queue ``_konten``, ``buche_kasse``,
``freigeben``) — CLI, Browser und REST gleich.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from accounti.abschluss.kassenbuch import KassenbuchError, buche_kasse
from accounti.abschluss.konfiguration import KassenEinstellungen
from accounti.buchung.pruefschlange import (
    PruefregelError,
    freigeben,
    lade_eintrag,
)
from accounti.cli import app
from accounti.konfiguration import Buchhaltung
from accounti.models import BuchungStatus
from accounti.pruefung.storno import StornoError, korrigiere
from tests.api_hilfe import csrf, formularwert
from tests.auth_hilfe import billige_hashes
from tests.pruefen_hilfe import queuewelt, stand_aus
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    buchung,
    db_url,
    kurz,
    make_session_fixture,
    umsatz,
)

runner = CliRunner()
HX = {"HX-Request": "true"}


def test_fachfunktion_korrigiere_lehnt_soll_gleich_haben_ab(make_session):
    tx = umsatz("-20.00")
    b = buchung(tx, soll="4930", haben="1200")
    anlegen(make_session, tx, b)
    with make_session() as s, pytest.raises(StornoError, match="dasselbe Konto") as f:
        korrigiere(s, str(b.id), "1200", "1200", ohne_steuer=True, grund="x")
    assert f.value.feld == "haben"


def test_cli_korrigiere_1200_an_1200_exit_1(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    from accounti.db import init_db, session_factory

    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    tx = umsatz("-20.00")
    b = buchung(tx, soll="4930", haben="1200", status=BuchungStatus.GEPRUEFT)
    anlegen(fabrik, tx, b)
    engine.dispose()
    r = runner.invoke(
        app,
        ["korrigiere", kurz(b.id), "--soll", "1200", "--haben", "1200",
         "--ohne-steuer", "--grund", "x", "--db", url],
    )  # fmt: skip
    assert r.exit_code == 1 and "dasselbe Konto" in r.output, r.output


@pytest.mark.parametrize(
    "befehl",
    [
        ["korrigiere", "{id}", "--soll", "１２００", "--haben", "1200",
         "--ohne-steuer", "--grund", "x"],
        ["lerne", "--muster", "telekom", "--soll", "４９３０", "--haben", "1200",
         "--name", "telekom"],
    ],
    ids=["korrigiere", "lerne"],
)  # fmt: skip
def test_cli_unicode_ziffern_sind_keine_kontonummer(tmp_path, monkeypatch, befehl):
    """Runde 4 (g3w-fach N6): „１２００ an 1200“ ging an der Sperre gegen Soll = Haben
    vorbei, ein Phantomkonto „１２００“ galt als Bank, und ``export datev`` brach mit
    UnicodeEncodeError ab. Nur ASCII-Ziffern sind eine Kontonummer, wie im Browser."""
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    from accounti.db import init_db, session_factory
    from accounti.db.repo_kontierung import lade_kontierungsregeln
    from accounti.db.repository import lade_buchungen

    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    tx = umsatz("-20.00")
    b = buchung(tx, soll="4930", haben="1200", status=BuchungStatus.GEPRUEFT)
    anlegen(fabrik, tx, b)
    args = [a.replace("{id}", kurz(b.id)) for a in befehl]
    r = runner.invoke(app, [*args, "--db", url], env={"COLUMNS": "250"})
    assert r.exit_code == 1 and "keine Kontonummer" in r.output, r.output
    with fabrik() as s:
        assert [x.soll_konto for x in lade_buchungen(s)] == ["4930"]
        assert lade_kontierungsregeln(s) == []
    engine.dispose()


def test_kasse_buchen_mit_kassenkonto_als_gegenkonto_abgelehnt(make_session):
    kasse = KassenEinstellungen(konto="1000")
    with make_session() as s:
        buche_kasse(
            s, Decimal("500"), "Einlage", kasse, date(2026, 10, 1), None, "1200"
        )
        with pytest.raises(KassenbuchError, match="Kassenkonto"):
            buche_kasse(
                s, Decimal("-20"), "Porto", kasse, date(2026, 10, 2), None, kasse.konto
            )


# --- Browser -------------------------------------------------------------------------


@pytest.fixture
def qw(tmp_path, monkeypatch):
    billige_hashes(monkeypatch)
    return queuewelt(tmp_path)


def test_queue_korrektur_1200_an_1200_422(qw):
    b = qw.unsicher(betrag="-20.00", zweck="RE 4721", name="Bürobedarf Müller")
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    daten = {"csrf": csrf(client), "stand": stand_aus(seite), "soll": "1200",
             "haben": "1200", "steuer": "ohne"}  # fmt: skip
    for kopf in ({}, HX):
        r = client.post(
            f"/pruefen/{b.id}/korrigieren", data=daten, headers=kopf,
            follow_redirects=False,
        )  # fmt: skip
        assert r.status_code == 422 and "dasselbe Konto" in r.text, r.status_code
    assert qw.sql("SELECT soll_konto, status FROM buchungssaetze WHERE id = :i",
                  i=str(b.id)) != [("1200", "korrigiert")]  # fmt: skip


def test_buchungsseite_korrektur_4930_an_4930_422_ohne_code(qw):
    b = qw.buchung(status=BuchungStatus.GEPRUEFT)
    client = qw.web.angemeldet("jan")
    code = qw.web.personen["jan"].codes[-1]
    seite = client.get(f"/buchungen/{b.id}").text
    daten = {
        "csrf": csrf(client),
        "stand": formularwert(seite, "stand"),
        "soll": "4930",
        "haben": "4930",
        "steuer": "9",
        "einmalcode": code,
    }
    r = client.post(f"/buchungen/{b.id}/korrigieren", data=daten)
    assert r.status_code == 422 and "dasselbe Konto" in r.text
    assert len(qw.sql("SELECT id FROM buchungssaetze")) == 1
    r = client.post(f"/buchungen/{b.id}/stornieren", data={**daten, "grund": "doppelt"})
    assert r.status_code == 200  # derselbe Code gilt noch


def test_altvorschlag_soll_gleich_haben_nicht_freigeben(qw):
    """gw2-merge B3: Ein Vorschlag „1210 an 1210“ (vor H-1 aus einer gelernten
    Umbuchung) bekam den Knopf „Freigeben“ und wurde mit einem Klick geprüft."""
    b = qw.unsicher(betrag="400.00", zweck="Übertrag", name="Probe GmbH",
                    sachkonto="1210")  # fmt: skip
    qw.sql(
        "UPDATE buchungssaetze SET soll_konto = '1210', haben_konto = '1210', "
        "steuer_schluessel = NULL, steuer_betrag = NULL WHERE id = :i",
        i=str(b.id),
    )
    with qw.fabrik()() as s:
        e = lade_eintrag(s, b.id, buchhaltung=Buchhaltung())
        assert e.freigabe_gesperrt
        assert any("dasselbe Konto" in text for _, text in e.steuer_befunde)
        with pytest.raises(PruefregelError, match="so nicht freigeben"):
            freigeben(s, b.id, "fritz")
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    assert "dasselbe Konto" in seite
    r = client.post(
        f"/pruefen/{b.id}/freigeben",
        data={"csrf": csrf(client), "stand": stand_aus(seite)},
        follow_redirects=False,
    )
    assert r.status_code in (409, 422) and "dasselbe Konto" in r.text
    assert qw.sql("SELECT status FROM buchungssaetze WHERE id = :i", i=str(b.id)) == [
        ("pruefung",)
    ]
