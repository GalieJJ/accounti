from datetime import date
from decimal import Decimal

import yaml
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    finde_buchung,
    speichere_buchung,
    speichere_transaktion,
)
from accounti.models import (
    Buchungssatz,
    BuchungStatus,
    Transaktion,
    TransaktionQuelle,
)

runner = CliRunner()


def _url(tmp_path) -> str:
    return f"sqlite:///{(tmp_path / 'a.db').as_posix()}"


def _seed(url: str, statuses: list[BuchungStatus]) -> list[Buchungssatz]:
    engine, make_session = session_factory(url)
    init_db(engine)
    tx = Transaktion(
        datum=date(2026, 4, 15),
        betrag=Decimal("-119.00"),
        verwendungszweck="STADTWERKE STROM ABSCHLAG",
        gegenkonto_name="Stadtwerke Hamburg",
        quelle=TransaktionQuelle.BANK,
        rohtext="x",
    )
    buchungen: list[Buchungssatz] = []
    with make_session() as s:
        speichere_transaktion(s, tx)
        for st in statuses:
            b = Buchungssatz(
                transaktion_id=tx.id,
                datum=tx.datum,
                soll_konto="4900",
                haben_konto="1200",
                betrag_netto=Decimal("100.00"),
                steuer_schluessel=9,
                steuer_betrag=Decimal("19.00"),
                buchungstext="Strom",
                status=st,
                confidence=0.5,
            )
            speichere_buchung(s, b)
            buchungen.append(b)
        s.commit()
    return buchungen


def test_review_zeigt_pruefliste(tmp_path):
    url = _url(tmp_path)
    bs = _seed(url, [BuchungStatus.ZUR_PRUEFUNG, BuchungStatus.AUTO_GEBUCHT])
    res = runner.invoke(app, ["review", "--db", url])
    assert res.exit_code == 0
    assert "pruefung" in res.stdout
    assert str(bs[0].id)[:8] in res.stdout


def test_bestaetige(tmp_path):
    url = _url(tmp_path)
    bs = _seed(url, [BuchungStatus.ZUR_PRUEFUNG])
    pid = str(bs[0].id)[:8]
    res = runner.invoke(app, ["bestaetige", pid, "--db", url])
    assert res.exit_code == 0
    _, make_session = session_factory(url)
    with make_session() as s:
        assert finde_buchung(s, pid).status is BuchungStatus.GEPRUEFT


def test_bestaetige_unbekannt_fehler(tmp_path):
    url = _url(tmp_path)
    _seed(url, [BuchungStatus.ZUR_PRUEFUNG])
    res = runner.invoke(app, ["bestaetige", "ffffffff", "--db", url])
    assert res.exit_code == 1


def test_korrigiere(tmp_path):
    url = _url(tmp_path)
    bs = _seed(url, [BuchungStatus.ZUR_PRUEFUNG])
    pid = str(bs[0].id)[:8]
    res = runner.invoke(
        app,
        [
            "korrigiere",
            pid,
            "--soll",
            "4930",
            "--haben",
            "1200",
            "--steuer",
            "9",
            "--db",
            url,
        ],
    )
    assert res.exit_code == 0
    _, make_session = session_factory(url)
    with make_session() as s:
        b = finde_buchung(s, pid)
        assert b.soll_konto == "4930"
        assert b.betrag_netto == Decimal("100.00")
        assert b.status is BuchungStatus.KORRIGIERT


def test_export_nur_freigegeben(tmp_path):
    url = _url(tmp_path)
    _seed(
        url,
        [
            BuchungStatus.AUTO_GEBUCHT,
            BuchungStatus.AUTO_GEBUCHT,
            BuchungStatus.ZUR_PRUEFUNG,
        ],
    )
    out = tmp_path / "export"
    args = [
        "export",
        "datev",
        "--db",
        url,
        "--berater",
        "1",
        "--mandant",
        "2",
        "--output",
        str(out),
    ]
    res = runner.invoke(app, args)
    assert res.exit_code == 0
    assert "2 Buchungen" in res.stdout
    res_alle = runner.invoke(app, [*args, "--alle"])
    assert "3 Buchungen" in res_alle.stdout


def test_korrigiere_lernen(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "regeln.yaml").write_text("[]\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    url = _url(tmp_path)
    bs = _seed(url, [BuchungStatus.ZUR_PRUEFUNG])
    pid = str(bs[0].id)[:8]
    res = runner.invoke(
        app,
        [
            "korrigiere",
            pid,
            "--soll",
            "4900",
            "--haben",
            "1200",
            "--steuer",
            "9",
            "--lernen",
            "--db",
            url,
        ],
    )
    assert res.exit_code == 0
    regeln = yaml.safe_load((tmp_path / "config" / "regeln.yaml").read_text("utf-8"))
    assert any(r["muster"] == "Stadtwerke" for r in regeln)
