from typer.testing import CliRunner

from accounti.cli import app

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
    (eingang / "a.pdf").write_bytes(b"A")
    (eingang / "b.pdf").write_bytes(b"B")

    r = runner.invoke(
        app,
        [
            "belege",
            "abholen",
            "--kanal",
            "ordner",
            "--ordner",
            str(eingang),
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
    r = runner.invoke(app, ["belege", "abholen", "--kanal", "email", *_args(tmp_path)])
    assert r.exit_code == 1
    assert "ordner" in r.output
