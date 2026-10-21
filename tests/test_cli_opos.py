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


# ---------------------------------------------------------------------------
# Zahlungszuordnung
# ---------------------------------------------------------------------------

KOPF = (
    "Auftragskonto;Buchungstag;Valutadatum;Buchungstext;Verwendungszweck;"
    "Begünstigter/Zahlungspflichtiger;Kontonummer;BLZ;Betrag;Währung;Info"
)


def _bankdatei(tmp_path, *zeilen):
    datei = tmp_path / "bank.csv"
    datei.write_text("\n".join([KOPF, *zeilen]) + "\n", encoding="utf-8")
    return str(datei)


def test_zuordnen_gleicht_skontozahlung_aus_und_classify_laesst_sie_in_ruhe(tmp_path):
    url, _ = _eingangsrechnung_verbuchen(tmp_path)
    csv = _bankdatei(
        tmp_path,
        "DE12;10.03.26;10.03.26;UEBERWEISUNG;RE-2026-0042 abzgl. 2% Skonto;"
        "Bürobedarf Müller GmbH;DE89370400440532013000;COBADEFFXXX;-169,05;EUR;gebucht",
        "DE12;11.03.26;11.03.26;ENTGELT;Kontoführung März;Sparkasse;;;-5,90;EUR;"
        "gebucht",
    )
    assert (
        _run("import", "bank", csv, "--db", url, "--format", "sparkasse").exit_code == 0
    )
    r = _run("opos", "zuordnen", "--db", url, "--config", str(tmp_path / "keine.yaml"))
    assert r.exit_code == 0, r.output
    assert "RE-2026-0042" in r.output and "Skonto 3,45" in r.output
    assert "1 ausgeglichen" in r.output and "0 Vorschläge" in r.output
    assert "Keine offenen Posten" in _run("opos", "liste", "--db", url).output

    kontiert = _run("classify", "--db", url, "--no-llm")
    assert kontiert.exit_code == 0, kontiert.output
    # nur die Kontoführungsgebühr ist noch offen für die Kontierung
    zahlen = [int(w) for w in kontiert.output.replace("[", " ").split() if w.isdigit()]
    assert sum(zahlen[:2]) == 1


def _vorschlag(tmp_path):
    from datetime import date
    from decimal import Decimal

    from accounti.db import init_db, session_factory
    from accounti.db.repository import speichere_transaktion
    from accounti.models import Transaktion, TransaktionQuelle
    from tests.test_opos_zahlungslauf import _rechnung, _rechnungen

    url = _db(tmp_path)
    engine, make_session = session_factory(url)
    init_db(engine)
    _rechnungen(
        make_session,
        _rechnung("RE-1001", "100.00", "1"),
        _rechnung("RE-1002", "200.00", "2"),
        _rechnung("RE-1003", "300.00", "3"),
    )
    t = Transaktion(
        datum=date(2026, 3, 10),
        betrag=Decimal("-600.00"),
        verwendungszweck="RE-1001 RE-1002 RE-1003",
        quelle=TransaktionQuelle.BANK,
        rohtext="x",
    )
    with make_session() as s:
        speichere_transaktion(s, t)
        s.commit()
    engine.dispose()
    r = _run("opos", "zuordnen", "--db", url, "--config", str(tmp_path / "keine.yaml"))
    assert "1 Vorschläge" in r.output, r.output
    return url, str(t.id)[:8]


def test_vorschlag_anzeigen_und_bestaetigen(tmp_path):
    url, tx = _vorschlag(tmp_path)
    liste = _run("opos", "vorschlaege", "--db", url)
    assert tx in liste.output and "sammel" in liste.output
    for nummer in ("RE-1001", "RE-1002", "RE-1003"):
        assert nummer in liste.output
    r = _run(
        "opos", "bestaetigen", tx, "--db", url, "--config", str(tmp_path / "keine.yaml")
    )
    assert r.exit_code == 0, r.output
    assert "3 Buchungen" in r.output
    assert "Keine offenen Posten" in _run("opos", "liste", "--db", url).output
    assert "Keine Vorschläge" in _run("opos", "vorschlaege", "--db", url).output


def test_vorschlag_ablehnen(tmp_path):
    url, tx = _vorschlag(tmp_path)
    r = _run("opos", "ablehnen", tx, "--db", url)
    assert r.exit_code == 0, r.output
    assert "abgelehnt" in r.output
    assert "RE-1001" in _run("opos", "liste", "--db", url).output
    unbekannt = _run("opos", "bestaetigen", tx, "--db", url)
    assert unbekannt.exit_code == 1


def test_verbuchen_in_festgeschriebenen_monat_mit_buchungsdatum(tmp_path):
    """Befund B-H3: die Rechnung vom 05.03. kommt nach der Festschreibung des März."""
    from datetime import date

    from accounti.db import session_factory
    from accounti.db.repository import lade_buchungen

    url = _db(tmp_path)
    archiv = str(tmp_path / "archiv")
    datei = str(BELEGE / "rechnung_zwei_steuersaetze.txt")
    r = _run("belege", "import", datei, "--db", url, "--archiv", archiv)
    assert r.exit_code == 0, r.output
    r = _run("periode", "schliessen", "2026-03", "--db", url, "--von", "erika")
    assert r.exit_code == 0, r.output
    basis = ["--db", url, "--archiv", archiv, "--config", str(tmp_path / "k.yaml")]
    r = _run("opos", "verbuchen", *basis)
    assert "Nicht verbucht" in r.output and "--buchungsdatum" in r.output
    r = _run("opos", "verbuchen", *basis, "--buchungsdatum", "eingang")
    assert r.exit_code == 0, r.output
    assert "§ 15 Abs. 1 Nr. 1 UStG" in r.output
    _, fabrik = session_factory(url)
    with fabrik() as s:
        assert {b.datum for b in lade_buchungen(s)} == {date.today()}
