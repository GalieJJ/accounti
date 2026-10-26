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


def _gelernt(url: str):  # noqa: ANN202
    from accounti.db.repo_kontierung import lade_kontierungsregeln

    engine, make_session = session_factory(url)
    with make_session() as s:
        regeln = lade_kontierungsregeln(s)
    engine.dispose()
    return regeln


def test_korrigiere_lernen(tmp_path, monkeypatch):
    """(umgestellt, Baustein 10b) Die Regel landet in der Datenbank der Gesellschaft —
    die Regeldatei bleibt unverändert, samt Kommentaren."""
    (tmp_path / "config").mkdir()
    datei = tmp_path / "config" / "regeln.yaml"
    datei.write_text("# eigene Regeln — Kommentar bleibt\n[]\n", encoding="utf-8")
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
    assert res.exit_code == 0, res.output
    assert "Regel gelernt" in res.output
    (regel,) = _gelernt(url)
    # der ganze Name der Gegenpartei (Nachbesserung H1)
    assert regel.muster == "Stadtwerke Hamburg" and regel.ist_text
    assert regel.richtung is not None and regel.richtung.value == "ausgabe"
    assert (
        datei.read_text(encoding="utf-8") == "# eigene Regeln — Kommentar bleibt\n[]\n"
    )


def test_korrigiere_lernt_den_schluessel_der_neubuchung(tmp_path, monkeypatch):
    """Befund N-N5: Die Regel bucht künftig wie die Korrektur — bleibt das Sachkonto,
    bleibt der Schlüssel und wird mit gelernt; ein neues Sachkonto verlangt ihn
    ohnehin ausdrücklich. (umgestellt: Schlüssel in ``kontierungsregeln``;
    Nachbesserung M1: bisher wechselte hier das Geldkonto 1200 → 1210 — das lehnt
    die Korrektur jetzt ab, der Kontostand passte sonst nicht mehr zum Auszug. Das
    Sachkonto bleibt deshalb durch eine unveränderte Bestätigung des Vorschlags.)"""
    monkeypatch.chdir(tmp_path)
    url = _url(tmp_path)
    bs = _seed(url, [BuchungStatus.ZUR_PRUEFUNG])
    pid = str(bs[0].id)[:8]
    geldkonto = ["korrigiere", pid, "--soll", "4900", "--haben", "1210", "--lernen"]
    res = runner.invoke(app, [*geldkonto, "--db", url])
    assert res.exit_code == 1 and "Finanzkonto 1200" in res.output
    assert _gelernt(url) == []
    args = ["korrigiere", pid, "--soll", "4900", "--haben", "1200", "--lernen"]
    res = runner.invoke(app, [*args, "--db", url])
    assert res.exit_code == 0, res.output
    _, make_session = session_factory(url)
    with make_session() as s:
        assert finde_buchung(s, pid).steuer_schluessel == 9
    (regel,) = _gelernt(url)
    assert regel.steuer_schluessel == 9 and regel.haben_konto == "1200"
    assert not (tmp_path / "config" / "regeln.yaml").exists()


def test_korrigiere_nutzt_die_kontenzuordnung_der_gesellschaft(tmp_path):
    """``abschluss.kontenzuordnung`` gilt auch für die Korrektur (wie für die SuSa):
    Hier ist 1800 ein Geldkonto — das Storno von 4900 an 1800 mit Vorsteuer ist
    umkehrbar; mit dem SKR03-Standard (1800 Privatentnahme) wäre es das nicht."""
    from accounti.abschluss.kontenrahmen import lade_kontenrahmen

    url = _url(tmp_path)
    (b,) = _seed(url, [BuchungStatus.GEPRUEFT])
    engine, make_session = session_factory(url)
    with make_session() as s:
        from sqlalchemy import text

        s.execute(text("UPDATE buchungssaetze SET haben_konto = '1800'"))
        s.commit()
    engine.dispose()
    args = ["korrigiere", str(b.id)[:8], "--soll", "4930", "--haben", "1800"]
    args += ["--steuer", "9", "--db", url]
    res = runner.invoke(app, args)
    assert res.exit_code == 1 and "dieselbe Natur" in res.output
    kr = lade_kontenrahmen().model_dump(mode="json")
    kr["geldkonten"].append({"von": "1800", "bis": "1800"})
    zuordnung = tmp_path / "kontenrahmen.yaml"
    zuordnung.write_text(yaml.safe_dump(kr, allow_unicode=True), encoding="utf-8")
    config = tmp_path / "accounti.yaml"
    config.write_text(
        f"abschluss:\n  kontenzuordnung: '{zuordnung}'\n", encoding="utf-8"
    )
    res = runner.invoke(app, [*args, "--config", str(config)])
    assert res.exit_code == 0, res.output
    assert "Storniert" in res.output


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


def test_review_zeigt_begruendung_und_zurueckgestellt(tmp_path):
    """``review`` nutzt die Prüfschlange: Begründung je Vorschlag, Zähler und
    Ansicht der zurückgestellten Buchungen."""
    from accounti.buchung.pruefschlange import zurueckstellen
    from accounti.db.repo_kontierung import speichere_kontierungsgrund

    url = _url(tmp_path)
    erste, zweite = _seed(url, [BuchungStatus.ZUR_PRUEFUNG, BuchungStatus.ZUR_PRUEFUNG])
    _, make_session = session_factory(url)
    with make_session() as s:
        speichere_kontierungsgrund(
            s, erste.id, quelle="llm", begruendung="Stromabschlag laut Zweck"
        )
        zurueckstellen(s, zweite.id, "Wofür?", "jan")
        s.commit()
    res = runner.invoke(app, ["review", "--db", url], env={"COLUMNS": "250"})
    assert res.exit_code == 0, res.output
    assert "Stromabschlag laut Zweck" in res.output
    assert "zurückgest." in res.output and str(zweite.id)[:8] not in res.output
    res = runner.invoke(
        app, ["review", "--zurueckgestellt", "--db", url], env={"COLUMNS": "250"}
    )
    assert str(zweite.id)[:8] in res.output and str(erste.id)[:8] not in res.output
