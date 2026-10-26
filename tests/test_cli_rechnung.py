from pathlib import Path

from typer.testing import CliRunner

from accounti.cli import app
from tests.pdf_hilfe import pdf_mit_anhang, pdf_mit_text

runner = CliRunner()
FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "erechnung"


def test_gueltige_xrechnung():
    r = runner.invoke(app, ["rechnung", "pruefen", str(FIXTURES / "xrechnung_ubl.xml")])
    assert r.exit_code == 0, r.output
    assert "RE-2026-0042" in r.output
    assert "Bürobedarf Müller GmbH" in r.output
    assert "172.50" in r.output
    assert "xrechnung" in r.output.lower()
    assert "Keine Befunde" in r.output


def test_fehlerhafte_rechnung_endet_mit_exit_1():
    datei = FIXTURES / "fehler_rechenprobe_cii.xml"
    r = runner.invoke(app, ["rechnung", "pruefen", str(datei)])
    assert r.exit_code == 1
    assert "BR-S-09" in r.output


def test_zugferd_pdf(tmp_path):
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(
        pdf_mit_anhang("factur-x.xml", (FIXTURES / "minimum_cii.xml").read_bytes())
    )
    r = runner.invoke(app, ["rechnung", "pruefen", str(pdf)])
    assert r.exit_code == 0, r.output
    assert "MIN-2026-9" in r.output
    assert "PROFIL" in r.output


def test_pdf_ohne_erechnung(tmp_path):
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(pdf_mit_text("Rechnung"))
    r = runner.invoke(app, ["rechnung", "pruefen", str(pdf)])
    assert r.exit_code == 1
    assert "keine E-Rechnung" in r.output


# ---------------------------------------------------------------------------
# Ausgangsrechnungen
# ---------------------------------------------------------------------------

FIRMA_YAML = """
mandant:
  name: "Galerie Muster GmbH"
  kuerzel: GM
  anschrift: {strasse: "Beispielweg 3", plz: "24103", ort: Kiel, land: DE}
  ust_id: DE999999999
  email: rechnung@galerie-muster.example
  kontakt: {name: Jan Muster, telefon: "0431 123456", email: jan@galerie-muster.example}
  bank: {iban: "DE89 3704 0044 0532 0130 00"}
"""


def _basis(tmp_path):
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(FIRMA_YAML, encoding="utf-8")
    url = f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    return url, str(konfig)


def _neu(url, *extra):
    r = runner.invoke(
        app,
        [
            "rechnung",
            "neu",
            "--db",
            url,
            "--name",
            "Atelier Kundin GmbH",
            "--strasse",
            "Kundenstraße 8",
            "--plz",
            "10115",
            "--ort",
            "Berlin",
            "--ust-id",
            "DE888888888",
            "--email",
            "rechnung@atelier-kundin.example",
            "--leistungsdatum",
            "2026-03-09",
            *extra,
        ],
    )
    assert r.exit_code == 0, r.output
    return r.output.split("Entwurf ")[1].split()[0]


def _position(url, rid, *args):
    r = runner.invoke(app, ["rechnung", "position", rid, "--db", url, *args])
    assert r.exit_code == 0, r.output
    return r


def test_rechnung_schreiben_und_ausstellen(tmp_path):
    from accounti.erechnung.kosit import KositPruefer

    url, konfig = _basis(tmp_path)
    rid = _neu(url, "--bestellnummer", "PO-77")
    _position(
        url, rid, "--text", "Bilderrahmen Eiche", "--preis", "250", "--menge", "4"
    )
    _position(url, rid, "--text", "Katalog", "--preis", "25", "--ermaessigt")

    vorschau = runner.invoke(
        app, ["rechnung", "zeigen", rid, "--db", url, "--config", konfig]
    )
    assert vorschau.exit_code == 0, vorschau.output
    assert "1216.75" in vorschau.output
    assert "S 19 %" in vorschau.output and "S 7 %" in vorschau.output

    ausgabe = tmp_path / "rechnungen"
    argumente = [
        "rechnung",
        "ausstellen",
        rid,
        "--db",
        url,
        "--config",
        konfig,
        "--archiv",
        str(tmp_path / "archiv"),
        "--ausgabe",
        str(ausgabe),
        "--datum",
        "2026-03-10",
    ]
    from accounti.erechnung.mustang import MustangPruefer

    if not (KositPruefer().verfuegbar() and MustangPruefer().verfuegbar()):
        argumente.append("--ohne-formale-pruefung")
    r = runner.invoke(app, argumente)
    assert r.exit_code == 0, r.output
    assert "2026-0001" in r.output
    xml = (ausgabe / "2026-0001.xml").read_bytes()
    assert b"<ram:ID>2026-0001</ram:ID>" in xml
    pdf = (ausgabe / "2026-0001.pdf").read_bytes()
    assert pdf.startswith(b"%PDF-")
    assert xml in pdf or b"xrechnung.xml" in pdf

    liste = runner.invoke(app, ["rechnung", "liste", "--db", url])
    assert "2026-0001" in liste.output and "ausgestellt" in liste.output
    belege = runner.invoke(app, ["belege", "liste", "--db", url])
    assert "ausgangsrechnung" in belege.output

    nochmal = runner.invoke(
        app,
        [
            "rechnung",
            "position",
            "2026-0001",
            "--db",
            url,
            "--text",
            "x",
            "--preis",
            "1",
        ],
    )
    assert nochmal.exit_code == 1
    assert "unveränderlich" in nochmal.output

    pruefen = runner.invoke(
        app, ["rechnung", "pruefen", str(ausgabe / "2026-0001.xml")]
    )
    assert pruefen.exit_code == 0, pruefen.output


def test_reverse_charge_vorschau(tmp_path):
    url, konfig = _basis(tmp_path)
    r = runner.invoke(
        app,
        [
            "rechnung",
            "neu",
            "--db",
            url,
            "--name",
            "Rahmenwerk Wien GmbH",
            "--strasse",
            "Graben 1",
            "--plz",
            "1010",
            "--ort",
            "Wien",
            "--land",
            "AT",
            "--ust-id",
            "ATU12345678",
            "--email",
            "office@rahmenwerk.example",
        ],
    )
    rid = r.output.split("Entwurf ")[1].split()[0]
    _position(
        url,
        rid,
        "--text",
        "Hängung",
        "--preis",
        "90",
        "--menge",
        "8",
        "--einheit",
        "HUR",
        "--leistung",
    )
    vorschau = runner.invoke(
        app, ["rechnung", "zeigen", rid, "--db", url, "--config", konfig]
    )
    assert vorschau.exit_code == 0, vorschau.output
    assert "AE 0 %" in vorschau.output
    assert "Reverse Charge" in vorschau.output
    assert "720.00" in vorschau.output


def test_ausstellen_ohne_pruefwerkzeug_braucht_ausdrueckliche_zustimmung(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ACCOUNTI_PRUEFWERKZEUGE", str(tmp_path / "nirgends"))
    url, konfig = _basis(tmp_path)
    rid = _neu(url)
    _position(url, rid, "--text", "Rahmen", "--preis", "100")
    r = runner.invoke(
        app,
        [
            "rechnung",
            "ausstellen",
            rid,
            "--db",
            url,
            "--config",
            konfig,
            "--archiv",
            str(tmp_path / "archiv"),
            "--ausgabe",
            str(tmp_path / "out"),
        ],
    )
    assert r.exit_code == 1
    assert "--ohne-formale-pruefung" in r.output
    liste = runner.invoke(app, ["rechnung", "liste", "--db", url])
    assert "entwurf" in liste.output


def test_ausstellen_ohne_firmendaten(tmp_path):
    url, _ = _basis(tmp_path)
    rid = _neu(url)
    _position(url, rid, "--text", "Rahmen", "--preis", "100")
    r = runner.invoke(
        app,
        [
            "rechnung",
            "ausstellen",
            rid,
            "--db",
            url,
            "--config",
            str(tmp_path / "fehlt.yaml"),
            "--ohne-kosit",
        ],
    )
    assert r.exit_code == 1
    assert "accounti.example.yaml" in r.output


def test_pruefen_mit_kosit(tmp_path):
    from accounti.erechnung.kosit import KositPruefer

    if not KositPruefer().verfuegbar():
        import pytest

        pytest.skip("KoSIT-Prüftool fehlt")
    r = runner.invoke(
        app,
        [
            "rechnung",
            "pruefen",
            str(FIXTURES / "fehler_rechenprobe_cii.xml"),
            "--kosit",
        ],
    )
    assert r.exit_code == 1
    assert "KoSIT" in r.output and "REJECT" in r.output.upper()


# ---------------------------------------------------------------------------
# Versand
# ---------------------------------------------------------------------------

VERSAND_YAML = """
versand:
  absender: "Galerie Muster GmbH <rechnung@galerie-muster.example>"
  smtp:
    host: smtp.example
    benutzer: rechnung
    passwort: "${ACCOUNTI_SMTP_PASSWORT}"
"""


def _ausgestellt(tmp_path, monkeypatch):
    url, konfig = _basis(tmp_path)
    Path(konfig).write_text(FIRMA_YAML + VERSAND_YAML, encoding="utf-8")
    monkeypatch.setenv("ACCOUNTI_SMTP_PASSWORT", "geheim")
    rid = _neu(url)
    _position(url, rid, "--text", "Rahmen", "--preis", "100")
    archiv = str(tmp_path / "archiv")
    r = runner.invoke(
        app,
        [
            "rechnung",
            "ausstellen",
            rid,
            "--db",
            url,
            "--config",
            konfig,
            "--archiv",
            archiv,
            "--ausgabe",
            str(tmp_path / "out"),
            "--datum",
            "2026-03-10",
            "--ohne-formale-pruefung",
        ],
    )
    assert r.exit_code == 0, r.output
    return url, konfig, archiv


def test_senden_per_smtp(tmp_path, monkeypatch):
    from tests.test_versand import FalscherSmtp

    FalscherSmtp.gesendet, FalscherSmtp.fehler = [], None
    monkeypatch.setattr("accounti.erechnung.versand.smtplib.SMTP", FalscherSmtp)
    url, konfig, archiv = _ausgestellt(tmp_path, monkeypatch)
    r = runner.invoke(
        app,
        [
            "rechnung",
            "senden",
            "2026-0001",
            "--db",
            url,
            "--config",
            konfig,
            "--archiv",
            archiv,
        ],
    )
    assert r.exit_code == 0, r.output
    assert "versendet" in r.output
    ((verbindung, nachricht),) = FalscherSmtp.gesendet
    assert nachricht["To"] == "rechnung@atelier-kundin.example"
    assert verbindung.schritte == ["verbinden", "starttls", "login rechnung"]

    zeigen = runner.invoke(
        app, ["rechnung", "zeigen", "2026-0001", "--db", url, "--config", konfig]
    )
    assert (
        "Versand" in zeigen.output
        and "rechnung@atelier-kundin.example" in zeigen.output
    )
    liste = runner.invoke(app, ["rechnung", "liste", "--db", url])
    assert "versendet" in liste.output


def test_senden_fehlschlag(tmp_path, monkeypatch):
    import smtplib

    from tests.test_versand import FalscherSmtp

    FalscherSmtp.gesendet = []
    FalscherSmtp.fehler = smtplib.SMTPAuthenticationError(535, b"Anmeldung abgelehnt")
    monkeypatch.setattr("accounti.erechnung.versand.smtplib.SMTP", FalscherSmtp)
    url, konfig, archiv = _ausgestellt(tmp_path, monkeypatch)
    r = runner.invoke(
        app,
        [
            "rechnung",
            "senden",
            "2026-0001",
            "--db",
            url,
            "--config",
            konfig,
            "--archiv",
            archiv,
        ],
    )
    assert r.exit_code == 1
    assert "Anmeldung abgelehnt" in r.output
    zeigen = runner.invoke(
        app, ["rechnung", "zeigen", "2026-0001", "--db", url, "--config", konfig]
    )
    assert "fehlgeschlagen" in zeigen.output
    FalscherSmtp.fehler = None


def test_senden_als_eml_datei(tmp_path, monkeypatch):
    from email import message_from_bytes
    from email.policy import default

    url, konfig, archiv = _ausgestellt(tmp_path, monkeypatch)
    eml = tmp_path / "vorschau.eml"
    r = runner.invoke(
        app,
        [
            "rechnung",
            "senden",
            "2026-0001",
            "--db",
            url,
            "--config",
            konfig,
            "--archiv",
            archiv,
            "--format",
            "xrechnung",
            "--eml",
            str(eml),
        ],
    )
    assert r.exit_code == 0, r.output
    nachricht = message_from_bytes(eml.read_bytes(), policy=default)
    (anhang,) = list(nachricht.iter_attachments())
    assert anhang.get_filename() == "2026-0001.xml"
    liste = runner.invoke(app, ["rechnung", "liste", "--db", url])
    assert "versendet" not in liste.output  # nur Vorschau, kein Versand
