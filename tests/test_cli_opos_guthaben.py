"""CLI: opos verrechnen, opos zuordnen --transaktion (Gesamttest Ausgang B3, B6)."""

from datetime import date
from decimal import Decimal

from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_posten, speichere_transaktion
from accounti.models import PostenRichtung, Transaktion, TransaktionQuelle
from accounti.pruefung.journal import lade_journal
from tests.zahlung_hilfe import debitor, posten, speichere

runner = CliRunner()


def _db(tmp_path):
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    engine, fabrik = session_factory(url)
    init_db(engine)
    k = debitor(name="Kunde AG", konto="10000")
    speichere(
        fabrik,
        [k],
        [
            posten(k, "2026-0001", "595.00", richtung=PostenRichtung.FORDERUNG),
            posten(k, "2026-0002", "-119.00", richtung=PostenRichtung.FORDERUNG),
        ],
    )
    return url, fabrik


def _text(r):
    return " ".join(r.output.split())


def _reste(fabrik):
    with fabrik() as s:
        return {p.belegnummer: p.restbetrag for p in lade_posten(s)}


def test_opos_verrechnen(tmp_path):
    url, fabrik = _db(tmp_path)
    r = runner.invoke(
        app,
        ["opos", "verrechnen", "2026-0002", "2026-0001", "--db", url, "--von", "Erika"],
    )
    assert r.exit_code == 0, r.output
    assert "2026-0002 gegen 2026-0001" in _text(r) and "119,00" in r.output
    assert _reste(fabrik) == {"2026-0001": Decimal("476.00"), "2026-0002": Decimal("0")}
    with fabrik() as s:
        (eintrag,) = lade_journal(s, vorgang="posten_verrechnet")
    assert (eintrag.person, eintrag.objekt_typ) == ("Erika", "verrechnung")
    nochmal = runner.invoke(
        app, ["opos", "verrechnen", "2026-0002", "2026-0001", "--db", url]
    )
    assert nochmal.exit_code == 1 and "ausgeglichen" in nochmal.output


def test_opos_zuordnen_von_hand(tmp_path):
    url, fabrik = _db(tmp_path)
    t = Transaktion(
        datum=date(2026, 10, 12),
        betrag=Decimal("476.00"),
        verwendungszweck="Zahlung laut Kontoauszug",
        quelle=TransaktionQuelle.BANK,
        rohtext="x",
    )
    with fabrik() as s:
        speichere_transaktion(s, t)
        s.commit()
    ohne = runner.invoke(
        app, ["opos", "zuordnen", "--posten", "2026-0001", "--db", url]
    )
    assert ohne.exit_code == 1
    r = runner.invoke(
        app,
        [
            "opos",
            "zuordnen",
            "--transaktion",
            str(t.id)[:8],
            "--posten",
            "2026-0001",
            "--posten",
            "2026-0002",
            "--db",
            url,
            "--von",
            "Erika",
        ],
    )
    assert r.exit_code == 0, r.output
    assert "von Hand" in _text(r) and "2 Buchungen" in _text(r)
    assert set(_reste(fabrik).values()) == {Decimal("0")}
    offen = runner.invoke(app, ["bank", "offen", "--db", url])
    assert str(t.id)[:8] not in offen.output
