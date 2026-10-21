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


def test_korrigiere_lernt_den_schluessel_der_neubuchung(tmp_path, monkeypatch):
    """Befund N-N5: Die Regel bucht künftig wie die Korrektur — bleibt das Sachkonto
    (nur das Geldkonto wechselt), bleibt der Schlüssel und wird mit gelernt; ein neues
    Sachkonto verlangt ihn ohnehin ausdrücklich."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "regeln.yaml").write_text("[]\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    url = _url(tmp_path)
    bs = _seed(url, [BuchungStatus.ZUR_PRUEFUNG])
    pid = str(bs[0].id)[:8]
    args = ["korrigiere", pid, "--soll", "4900", "--haben", "1210", "--lernen"]
    res = runner.invoke(app, [*args, "--db", url])
    assert res.exit_code == 0, res.output
    _, make_session = session_factory(url)
    with make_session() as s:
        assert finde_buchung(s, pid).steuer_schluessel == 9
    regeln = yaml.safe_load((tmp_path / "config" / "regeln.yaml").read_text("utf-8"))
    (regel,) = regeln
    assert regel["steuer_schluessel"] == 9


def test_korrigiere_neues_sachkonto_braucht_steuerangabe(tmp_path):
    url = _url(tmp_path)
    bs = _seed(url, [BuchungStatus.AUTO_GEBUCHT])
    pid = str(bs[0].id)[:8]
    args = ["korrigiere", pid, "--soll", "4360", "--haben", "1200", "--db", url]
    res = runner.invoke(app, args)
    assert res.exit_code == 1
    assert "--ohne-steuer" in res.output and "Traceback" not in res.output
    res = runner.invoke(app, [*args, "--ohne-steuer"])
    assert res.exit_code == 0, res.output


def test_korrigiere_nutzt_die_kontenrahmen_datei_der_konfiguration(tmp_path):
    """Befund N-N6: wie accounti pruefen — pruefung.kontenrahmen_datei zählt."""
    url = _url(tmp_path)
    bs = _seed(url, [BuchungStatus.ZUR_PRUEFUNG])
    pid = str(bs[0].id)[:8]
    eigene = tmp_path / "konten.yaml"
    eigene.write_text(
        "konten:\n  '4930':\n    typ: aufwand\n"
        "    steuer: {schluessel: 9, automatik: true}\n",
        encoding="utf-8",
    )
    config = tmp_path / "accounti.yaml"
    config.write_text(f"pruefung:\n  kontenrahmen_datei: {eigene}\n", encoding="utf-8")
    args = ["korrigiere", pid, "--soll", "4930", "--haben", "1200", "--steuer", "8"]
    res = runner.invoke(app, [*args, "--db", url, "--config", str(config)])
    assert res.exit_code == 1, res.output
    assert "Automatikkonto" in res.output
