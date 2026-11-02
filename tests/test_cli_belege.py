from pathlib import Path

from typer.testing import CliRunner

from accounti.cli import app
from tests.pdf_hilfe import pdf_mit_text

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "belege"
RECHNUNG = (FIXTURES / "rechnung_zwei_steuersaetze.txt").read_text(encoding="utf-8")

runner = CliRunner()


def _args(tmp_path):
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    return ["--db", url, "--archiv", str(tmp_path / "archiv")]


def test_kanaele_listet_registry():
    r = runner.invoke(app, ["belege", "kanaele"])
    assert r.exit_code == 0
    assert "ordner" in r.output
    assert "upload" in r.output


def test_import_meldet_neu_und_dublette(tmp_path):
    datei = tmp_path / "rechnung.pdf"
    datei.write_bytes(b"%PDF Rechnung")
    erst = runner.invoke(app, ["belege", "import", str(datei), *_args(tmp_path)])
    zweit = runner.invoke(app, ["belege", "import", str(datei), *_args(tmp_path)])
    assert erst.exit_code == 0, erst.output
    assert "1 neu" in erst.output
    assert zweit.exit_code == 0
    assert "Dublette" in zweit.output
    assert "1 Dubletten" in zweit.output


def test_import_fehlende_datei(tmp_path):
    r = runner.invoke(
        app, ["belege", "import", str(tmp_path / "gibtsnicht.pdf"), *_args(tmp_path)]
    )
    assert r.exit_code == 1


def test_abholen_leert_ordner_und_liste_zeigt_belege(tmp_path):
    eingang = tmp_path / "eingang"
    eingang.mkdir()
    # echte PDFs: der Ordner prüft den Typ am Inhalt (Gesamttest B03)
    (eingang / "a.pdf").write_bytes(pdf_mit_text("A"))
    (eingang / "b.pdf").write_bytes(pdf_mit_text("B"))

    r = runner.invoke(
        app,
        [
            "belege",
            "abholen",
            "--kanal",
            "ordner",
            "--ordner",
            str(eingang),
            "--ohne-erkennung",
            *_args(tmp_path),
        ],
    )
    assert r.exit_code == 0, r.output
    assert "2 neu" in r.output
    assert sorted(p.name for p in (eingang / "verarbeitet").iterdir()) == [
        "a.pdf",
        "b.pdf",
    ]

    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    liste = runner.invoke(app, ["belege", "liste", "--db", url])
    assert liste.exit_code == 0
    assert "a.pdf" in liste.output
    assert "b.pdf" in liste.output

    leer = runner.invoke(app, ["belege", "liste", "--db", url, "--status", "pruefung"])
    assert leer.exit_code == 0
    assert "Keine Belege" in leer.output


def test_abholen_unbekannter_kanal(tmp_path):
    r = runner.invoke(app, ["belege", "abholen", "--kanal", "fax", *_args(tmp_path)])
    assert r.exit_code == 1
    assert "ordner" in r.output


def test_pdf_im_watch_ordner_wird_erfasst(tmp_path):
    """Akzeptanz 1, end-to-end über die CLI."""
    eingang = tmp_path / "eingang"
    eingang.mkdir()
    (eingang / "rechnung.pdf").write_bytes(pdf_mit_text(RECHNUNG))

    r = runner.invoke(
        app,
        ["belege", "abholen", "--kanal", "ordner", "--ordner", str(eingang)]
        + _args(tmp_path),
    )
    assert r.exit_code == 0, r.output
    assert "eingangsrechnung · 172.50 EUR · erfasst" in r.output

    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    liste = runner.invoke(app, ["belege", "liste", "--db", url, "--status", "erfasst"])
    assert "172.50" in liste.output


def test_ohne_erkennung_und_spaeter_erkennen(tmp_path):
    datei = tmp_path / "rechnung.pdf"
    datei.write_bytes(pdf_mit_text(RECHNUNG))
    imp = runner.invoke(
        app, ["belege", "import", str(datei), "--ohne-erkennung", *_args(tmp_path)]
    )
    assert imp.exit_code == 0, imp.output
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    offen = runner.invoke(
        app, ["belege", "liste", "--db", url, "--status", "eingegangen"]
    )
    assert "rechnung.pdf" in offen.output

    r = runner.invoke(app, ["belege", "erkennen", *_args(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "1 erfasst" in r.output
    leer = runner.invoke(
        app, ["belege", "liste", "--db", url, "--status", "eingegangen"]
    )
    assert "Keine Belege" in leer.output


def test_unlesbare_datei_landet_in_pruefung(tmp_path):
    datei = tmp_path / "kaputt.pdf"
    datei.write_bytes(b"%PDF kaputt")
    r = runner.invoke(app, ["belege", "import", str(datei), *_args(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "zur Prüfung" in r.output


# --- Gesamttest Paket C: Freigabe, eigene Firma, Dateiprüfung im Ordner -----------


def _url(tmp_path):
    return f"sqlite:///{(tmp_path / 'a.db').as_posix()}"


def _beleg_id(tmp_path):
    from accounti.db import session_factory
    from accounti.db.repository import lade_belege

    engine, make_session = session_factory(_url(tmp_path))
    with make_session() as s:
        (b,) = lade_belege(s)
    engine.dispose()
    return str(b.id)[:8], b


def test_beleg_zur_pruefung_freigeben_mit_steuerfall(tmp_path):
    """B06: Der Weg aus „zur Prüfung“ — freigeben mit Steuerfall § 13b, danach
    verbucht opos verbuchen ihn mit Schlüssel 94."""
    datei = tmp_path / "rc.pdf"
    datei.write_bytes(
        pdf_mit_text(
            "Galerietechnik Salzburg GmbH\nUID: ATU12345678\nRechnung\n"
            "Rechnungsnummer: GS-2026-045\nRechnungsdatum: 02.04.2026\n"
            "Rechnungsbetrag 600,00 €\n"
        )
    )
    r = runner.invoke(app, ["belege", "import", str(datei), *_args(tmp_path)])
    assert "zur Prüfung" in r.output and "Steuerausweis" in r.output
    kurz, _ = _beleg_id(tmp_path)
    keine = str(tmp_path / "keine.yaml")
    falsch = runner.invoke(
        app,
        ["belege", "freigeben", kurz, "--steuer", "19", "--db", _url(tmp_path)],
    )
    assert falsch.exit_code == 1 and "13b" in falsch.output
    r = runner.invoke(
        app,
        [
            "belege",
            "freigeben",
            kurz,
            "--steuer",
            "13b",
            "--grund",
            "Hinweis auf Seite 2",
            "--db",
            _url(tmp_path),
            "--config",
            keine,
        ],
    )
    assert r.exit_code == 0, r.output
    assert "Freigegeben" in r.output and "AE" in r.output
    _, b = _beleg_id(tmp_path)
    assert (b.status.value, b.steuerkennzeichen, b.pruef_grund) == (
        "erfasst",
        "AE",
        None,
    )
    r = runner.invoke(
        app,
        [
            "opos",
            "verbuchen",
            "--db",
            _url(tmp_path),
            "--archiv",
            str(tmp_path / "archiv"),
            "--config",
            keine,
        ],
    )
    assert r.exit_code == 0, r.output
    assert "§ 13b" in r.output
    from accounti.db import session_factory
    from accounti.pruefung.journal import lade_journal

    engine, make_session = session_factory(_url(tmp_path))
    with make_session() as s:
        freigabe = [e for e in lade_journal(s) if e.vorgang == "beleg_freigegeben"]
    engine.dispose()
    assert [e.grund for e in freigabe] == ["Hinweis auf Seite 2"]
    nochmal = runner.invoke(app, ["belege", "freigeben", kurz, "--db", _url(tmp_path)])
    assert nochmal.exit_code == 1 and "schon verbucht" in nochmal.output
    # mit Benutzerverwaltung: Recht „buchen“ — steht in der Liste der Freigabewege
    # (Verfahrensdokumentation, docs/betrieb.md)
    from accounti.models.auth import FREIGABEWEGE, Recht

    assert "belege freigeben" in FREIGABEWEGE[Recht.BUCHEN]


def test_import_erkennt_eigene_rechnung_aus_der_konfiguration(tmp_path):
    """B04: belege import (und Ordner) nehmen die eigene Firma aus mandant — wie
    E-Mail und Webhook; ein falsch erkannter, unverbuchter Beleg lässt sich mit
    belege erkennen --id neu lesen."""
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        'mandant:\n  name: "Galerie Muster GmbH"\n  ust_id: "DE999999999"\n',
        encoding="utf-8",
    )
    text = (FIXTURES / "ausgangsrechnung.txt").read_text(encoding="utf-8")
    datei = tmp_path / "ausgang.pdf"
    datei.write_bytes(pdf_mit_text(text))
    # ohne Konfiguration: als Eingangsrechnung erfasst (der alte Weg)
    r = runner.invoke(
        app,
        [
            "belege",
            "import",
            str(datei),
            "--config",
            str(tmp_path / "keine.yaml"),
            *_args(tmp_path),
        ],
    )
    assert "eingangsrechnung" in r.output
    kurz, _ = _beleg_id(tmp_path)
    r = runner.invoke(
        app,
        ["belege", "erkennen", "--id", kurz, "--config", str(konfig), *_args(tmp_path)],
    )
    assert r.exit_code == 0, r.output
    _, b = _beleg_id(tmp_path)
    assert b.belegart.value == "ausgangsrechnung"
    # und direkt beim Import mit Konfiguration
    zweit = tmp_path / "zweit"
    zweit.mkdir()
    r = runner.invoke(
        app,
        [
            "belege",
            "import",
            str(datei),
            "--config",
            str(konfig),
            "--db",
            f"sqlite:///{(zweit / 'a.db').as_posix()}",
            "--archiv",
            str(zweit / "archiv"),
        ],
    )
    assert "ausgangsrechnung" in r.output, r.output


def test_ordner_lehnt_fremde_und_zu_grosse_dateien_ab(tmp_path):
    """B03: Dateiprüfung auch im Ordner — wie E-Mail und Webhook."""
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text("belegkanaele:\n  max_groesse_mb: 1\n", encoding="utf-8")
    eingang = tmp_path / "eingang"
    eingang.mkdir()
    (eingang / "programm.exe").write_bytes(b"MZ\x90\x00 keine Rechnung")
    (eingang / "gross.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 1_200_000)
    (eingang / "rechnung.pdf").write_bytes(pdf_mit_text(RECHNUNG))
    r = runner.invoke(
        app,
        [
            "belege",
            "abholen",
            "--kanal",
            "ordner",
            "--ordner",
            str(eingang),
            "--config",
            str(konfig),
            *_args(tmp_path),
        ],
    )
    assert r.exit_code == 0, r.output
    assert "1 neu" in r.output
    assert "programm.exe" in r.output and "gross.pdf" in r.output
    assert sorted(p.name for p in (eingang / "abgelehnt").iterdir()) == [
        "gross.pdf",
        "programm.exe",
    ]
    archiviert = [p for p in (tmp_path / "archiv").rglob("*") if p.is_file()]
    assert len(archiviert) == 1
