from pathlib import Path

from typer.testing import CliRunner

from accounti.cli import app

runner = CliRunner()
BELEGE = Path(__file__).resolve().parents[1] / "examples" / "belege"


def _db(tmp_path):
    return f"sqlite:///{(tmp_path / 'a.db').as_posix()}"


def _run(*args):
    r = runner.invoke(app, list(args))
    return r


def _eingangsrechnung_verbuchen(tmp_path):
    url = _db(tmp_path)
    archiv = str(tmp_path / "archiv")
    r = _run(
        "belege",
        "import",
        str(BELEGE / "rechnung_zwei_steuersaetze.txt"),
        "--db",
        url,
        "--archiv",
        archiv,
    )
    assert r.exit_code == 0, r.output
    r = _run(
        "opos",
        "verbuchen",
        "--db",
        url,
        "--archiv",
        archiv,
        "--config",
        str(tmp_path / "keine.yaml"),
    )
    assert r.exit_code == 0, r.output
    return url, r.output


def test_verbuchen_legt_kontakt_buchungen_und_posten_an(tmp_path):
    url, ausgabe = _eingangsrechnung_verbuchen(tmp_path)
    assert "RE-2026-0042" in ausgabe
    assert "70000" in ausgabe and "Bürobedarf Müller GmbH" in ausgabe
    assert "neu" in ausgabe and "172,50" in ausgabe and "19.03.2026" in ausgabe

    liste = _run("kontakte", "liste", "--db", url)
    assert "70000" in liste.output and "pruefung" in liste.output
    review = _run("review", "--db", url)
    assert "Bürobedarf Müller" in review.output

    nochmal = _run(
        "opos",
        "verbuchen",
        "--db",
        url,
        "--archiv",
        str(tmp_path / "archiv"),
        "--config",
        str(tmp_path / "keine.yaml"),
    )
    assert "Nichts zu verbuchen" in nochmal.output


def test_kontakt_bestaetigen_und_bearbeiten(tmp_path):
    url, _ = _eingangsrechnung_verbuchen(tmp_path)
    r = _run("kontakte", "bestaetigen", "70000", "--db", url)
    assert r.exit_code == 0, r.output
    r = _run(
        "kontakte",
        "bearbeiten",
        "70000",
        "--db",
        url,
        "--sachkonto",
        "4930",
        "--zahlungsziel",
        "30",
        "--skonto-prozent",
        "2",
        "--skonto-tage",
        "10",
    )
    assert r.exit_code == 0, r.output
    zeigen = _run("kontakte", "zeigen", "70000", "--db", url)
    for erwartet in (
        "Bürobedarf Müller GmbH",
        "geprueft",
        "4930",
        "30 Tage",
        "2",
        "10 Tage",
        "DE123456789",
        "172,50",
    ):
        assert erwartet in zeigen.output, erwartet
    assert (
        _run("kontakte", "liste", "--db", url, "--status", "pruefung").output.count(
            "70000"
        )
        == 0
    )
    unbekannt = _run("kontakte", "zeigen", "79999", "--db", url)
    assert unbekannt.exit_code == 1


def test_opos_liste_und_staffel(tmp_path):
    url, _ = _eingangsrechnung_verbuchen(tmp_path)
    liste = _run("opos", "liste", "--db", url, "--richtung", "eingang")
    assert "RE-2026-0042" in liste.output and "172,50" in liste.output
    assert "Bürobedarf" in liste.output  # Name darf bei 80 Spalten umbrechen
    leer = _run("opos", "liste", "--db", url, "--richtung", "ausgang")
    assert "Keine offenen Posten" in leer.output
    nicht_faellig = _run(
        "opos", "liste", "--db", url, "--faellig", "--stichtag", "2026-03-10"
    )
    assert "Keine offenen Posten" in nicht_faellig.output

    staffel = _run("opos", "staffel", "--db", url, "--stichtag", "2026-04-30")
    assert staffel.exit_code == 0, staffel.output
    zeilen = [z for z in staffel.output.splitlines() if "31–60" in z]
    assert zeilen and "172,50" in zeilen[0]


def test_ungueltige_richtung(tmp_path):
    r = _run("opos", "liste", "--db", _db(tmp_path), "--richtung", "seitwaerts")
    assert r.exit_code == 1


def test_ausgangsrechnung_wird_debitor(tmp_path):
    from tests.test_cli_rechnung import FIRMA_YAML

    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(FIRMA_YAML, encoding="utf-8")
    url, archiv = _db(tmp_path), str(tmp_path / "archiv")
    r = _run(
        "rechnung",
        "neu",
        "--db",
        url,
        "--name",
        "Atelier Kundin GmbH",
        "--plz",
        "10115",
        "--ort",
        "Berlin",
        "--email",
        "r@kundin.example",
        "--ust-id",
        "DE888888888",
    )
    rid = r.output.split("Entwurf ")[1].split()[0]
    _run("rechnung", "position", rid, "--db", url, "--text", "Rahmen", "--preis", "100")
    r = _run(
        "rechnung",
        "ausstellen",
        rid,
        "--db",
        url,
        "--config",
        str(konfig),
        "--archiv",
        archiv,
        "--ausgabe",
        str(tmp_path / "out"),
        "--ohne-formale-pruefung",
    )
    assert r.exit_code == 0, r.output
    r = _run(
        "opos", "verbuchen", "--db", url, "--archiv", archiv, "--config", str(konfig)
    )
    assert r.exit_code == 0, r.output
    assert "Debitor 10000" in r.output and "Atelier Kundin GmbH" in r.output
    staffel = _run("opos", "staffel", "--db", url)
    assert "Forderungen" in staffel.output and "119,00" in staffel.output
