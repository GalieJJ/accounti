"""`accounti kreditkarte …` — von der PDF-Abrechnung bis zum Befund."""

import pytest
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repo_bank import lade_abrechnungen
from accounti.db.repository import lade_belege, lade_buchungen, lade_transaktionen
from tests.pdf_hilfe import pdf_mit_text
from tests.test_bank_kreditkarte import BEISPIEL, GIRO, GIRO_APRIL

runner = CliRunner()


def _text(ergebnis):
    return " ".join(ergebnis.output.split())


def _run(*args, eingabe=None):
    return runner.invoke(app, list(args), input=eingabe)


@pytest.fixture
def umgebung(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    url = f"sqlite:///{(tmp_path / 'k.db').as_posix()}"
    ordner = tmp_path / "giro"
    ordner.mkdir()
    r = _run(
        "bank",
        "verbinde",
        "--provider",
        "datei",
        "--iban",
        GIRO,
        "--bezeichnung",
        "Giro",
        "--feld",
        f"ordner={ordner}",
        "--db",
        url,
    )
    assert r.exit_code == 0, r.output
    return url, ordner, tmp_path


def _db(url):
    engine, make_session = session_factory(url)
    init_db(engine)
    return engine, make_session


def _karte_und_pdf(url, tmp_path):
    r = _run(
        "kreditkarte",
        "einrichten",
        "--kennung",
        "VISA1234",
        "--bezeichnung",
        "Visa Firma",
        "--sachkonto",
        "1730",
        "--girokonto",
        GIRO,
        "--endziffern",
        "1234",
        "--db",
        url,
    )
    assert r.exit_code == 0, r.output
    assert "Visa Firma" in _text(r) and "1730" in _text(r)
    pdf = tmp_path / "visa-maerz.pdf"
    pdf.write_bytes(pdf_mit_text(BEISPIEL.read_text(encoding="utf-8")))
    r = _run(
        "belege", "import", str(pdf), "--db", url, "--archiv", str(tmp_path / "archiv")
    )
    assert r.exit_code == 0, r.output
    engine, make_session = _db(url)
    with make_session() as s:
        (beleg,) = lade_belege(s)
    engine.dispose()
    return str(beleg.id)[:8]


def test_pdf_abrechnung_uebernehmen_und_abgleichen(umgebung):
    url, ordner, tmp_path = umgebung
    beleg = _karte_und_pdf(url, tmp_path)
    r = _run("kreditkarte", "uebernehmen", beleg, "--db", url)
    assert r.exit_code == 0, r.output
    assert "12 Umsätze" in _text(r) and "-698,65" in _text(r)
    assert "31.03.2026" in _text(r)
    assert "vor der Einrichtung" in _text(r)  # Karte heute eingerichtet
    r = _run("kreditkarte", "uebernehmen", beleg, "--db", url)
    assert r.exit_code == 1 and "schon übernommen" in _text(r)

    (ordner / "april.sta").write_bytes(GIRO_APRIL.encode("cp1252"))
    r = _run("bank", "abrufen", "--db", url)
    assert "1 neu" in _text(r)
    r = _run("kreditkarte", "abgleich", "--db", url)
    assert r.exit_code == 0, r.output
    assert "abgeglichen" in _text(r) and "Visa Firma" in _text(r)

    r = _run("kreditkarte", "liste", "--db", url)
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "VISA1234" in text and "abgeglichen" in text and "-698,65" in text
    engine, make_session = _db(url)
    with make_session() as s:
        konten = {(b.soll_konto, b.haben_konto) for b in lade_buchungen(s)}
    engine.dispose()
    assert konten == {("1730", "1200")}


def test_abweichung_wird_als_befund_gemeldet(umgebung):
    url, ordner, tmp_path = umgebung
    beleg = _karte_und_pdf(url, tmp_path)
    assert _run("kreditkarte", "uebernehmen", beleg, "--db", url).exit_code == 0
    (ordner / "april.sta").write_bytes(
        GIRO_APRIL.replace("DR698,65", "DR698,75")
        .replace("4301,35", "4301,25")
        .encode("cp1252")
    )
    _run("bank", "abrufen", "--db", url)
    r = _run("kreditkarte", "abgleich", "--db", url)
    assert r.exit_code == 0, r.output
    text = _text(r)
    assert "Befund" in text and "Differenz -0,10 €" in text
    r = _run("kreditkarte", "liste", "--db", url)
    assert "abweichung" in _text(r)


def test_ohne_abrechnung_kommt_ein_hinweis(umgebung):
    url, ordner, tmp_path = umgebung
    _run(
        "kreditkarte",
        "einrichten",
        "--kennung",
        "VISA1234",
        "--bezeichnung",
        "Visa Firma",
        "--sachkonto",
        "1730",
        "--girokonto",
        GIRO,
        "--db",
        url,
    )
    (ordner / "april.sta").write_bytes(GIRO_APRIL.encode("cp1252"))
    _run("bank", "abrufen", "--db", url)
    r = _run("kreditkarte", "abgleich", "--db", url)
    assert "ohne Abrechnung" in _text(r)
    assert "kreditkarte uebernehmen" in _text(r)


def test_karte_mit_abruf_und_abrechnung_von_hand(umgebung):
    url, _, tmp_path = umgebung
    karte = tmp_path / "karte"
    karte.mkdir()
    (karte / "maerz.sta").write_bytes(
        "\r\n".join(
            [
                ":20:X",
                ":25:DKBVISA9",
                ":60F:D260301EUR0,00",
                ":61:2603020302DR100,00NMSCNONREF",
                ":86:HOTEL KIEL",
                ":61:2603200320DR50,00NMSCNONREF",
                ":86:BAHN",
                ":62F:D260320EUR150,00",
                "-",
            ]
        ).encode()
    )
    r = _run(
        "kreditkarte",
        "einrichten",
        "--kennung",
        "DKBVISA9",
        "--bezeichnung",
        "Visa DKB",
        "--sachkonto",
        "1732",
        "--girokonto",
        GIRO,
        "--provider",
        "datei",
        "--feld",
        f"ordner={karte}",
        "--db",
        url,
    )
    assert r.exit_code == 0, r.output
    assert "Geldtransit" in _text(r)
    assert "2 neu" in _text(_run("bank", "abrufen", "--db", url))
    r = _run(
        "kreditkarte",
        "abrechnen",
        "--karte",
        "dkbvisa9",
        "--stichtag",
        "20.03.2026",
        "--db",
        url,
    )
    assert r.exit_code == 0, r.output
    assert "2 Umsätze" in _text(r) and "-150,00" in _text(r)
    r = _run(
        "kreditkarte",
        "abrechnen",
        "--karte",
        "DKBVISA9",
        "--stichtag",
        "2026-03-31",
        "--db",
        url,
    )
    assert "Keine" in _text(r)
    r = _run(
        "kreditkarte",
        "abrechnen",
        "--karte",
        "DKBVISA9",
        "--stichtag",
        "31.02.2026",
        "--db",
        url,
    )
    assert r.exit_code == 1


@pytest.mark.parametrize(
    ("args", "grund"),
    [
        (["--girokonto", "DE00"], "DE00"),
        (["--girokonto", GIRO, "--kennung", "X1"], "fehlt"),
        (["--girokonto", GIRO, "--konto", "GIBTSNICHT"], "GIBTSNICHT"),
        (["--girokonto", GIRO, "--konto", GIRO], "Girokonto"),
    ],
)
def test_einrichten_fehler(umgebung, args, grund):
    url, _, _ = umgebung
    r = _run("kreditkarte", "einrichten", *args, "--db", url)
    assert r.exit_code == 1
    assert grund in _text(r)


def test_uebernehmen_ohne_karte(umgebung):
    url, _, _ = umgebung
    r = _run("kreditkarte", "uebernehmen", "abc", "--db", url)
    assert r.exit_code == 1
    assert "Keine Kreditkarte" in _text(r)


def test_liste_ohne_karten(umgebung):
    url, _, _ = umgebung
    r = _run("kreditkarte", "liste", "--db", url)
    assert r.exit_code == 0 and "Keine Kreditkarten" in _text(r)


def test_einrichten_ohne_endziffern_weist_auf_das_breite_muster_hin(umgebung):
    url, _, _ = umgebung
    r = _run(
        "kreditkarte",
        "einrichten",
        "--kennung",
        "VISA1234",
        "--bezeichnung",
        "Visa Firma",
        "--sachkonto",
        "1730",
        "--girokonto",
        GIRO,
        "--db",
        url,
    )
    assert r.exit_code == 0, r.output
    assert "--endziffern" in _text(r)


def test_vorlaeufige_zuordnung_von_hand_loesen(umgebung):
    url, ordner, tmp_path = umgebung
    beleg = _karte_und_pdf(url, tmp_path)
    assert _run("kreditkarte", "uebernehmen", beleg, "--db", url).exit_code == 0
    (ordner / "april.sta").write_bytes(
        GIRO_APRIL.replace("DR698,65", "DR29,00")
        .replace("4301,35", "4971,00")
        .replace("KREDITKARTENABRECHNUNG", "KARTENJAHRESGEBUEHR VISA")
        .encode("cp1252")
    )
    _run("bank", "abrufen", "--db", url)
    r = _run("kreditkarte", "abgleich", "--db", url)
    assert "Befund" in _text(r) and "Differenz 669,65 €" in _text(r)
    engine, make_session = _db(url)
    with make_session() as s:
        (a,) = lade_abrechnungen(s)
    engine.dispose()
    r = _run("kreditkarte", "liste", "--db", url)
    assert str(a.id)[:8] in _text(r)

    r = _run("kreditkarte", "loesen", str(a.id)[:8], "--db", url)
    assert r.exit_code == 0, r.output
    assert "gelöst" in _text(r) and "-29,00" in _text(r)
    engine, make_session = _db(url)
    with make_session() as s:
        assert lade_buchungen(s) == []
    engine.dispose()
    r = _run("kreditkarte", "abgleich", "--db", url)
    assert "Nichts Neues" in _text(r)
    r = _run("kreditkarte", "loesen", str(a.id)[:8], "--db", url)
    assert r.exit_code == 1 and "keine zugeordnete" in _text(r)


def test_bank_lauf_nennt_das_ergebnis_des_kartenabgleichs(umgebung):
    url, ordner, tmp_path = umgebung
    beleg = _karte_und_pdf(url, tmp_path)
    assert _run("kreditkarte", "uebernehmen", beleg, "--db", url).exit_code == 0
    (ordner / "april.sta").write_bytes(
        GIRO_APRIL.replace("DR698,65", "DR698,75")
        .replace("4301,35", "4301,25")
        .encode("cp1252")
    )
    r = _run("bank", "lauf", "--db", url)  # ohne config/regeln.yaml: Standardregeln
    assert r.exit_code == 0, r.output
    assert "Befund" in _text(r) and "Differenz -0,10 €" in _text(r)


def test_mehrdeutig_von_hand_entscheiden(umgebung):
    """Erst eine Jahresgebühr (vorläufig zugeordnet), dann die echte
    Sammelbelastung mit Abweichung: beide mehrdeutig. Die Meldung nennt den
    Befehl, mit dem ein Mensch die Gebühr abtrennt."""
    url, ordner, tmp_path = umgebung
    beleg = _karte_und_pdf(url, tmp_path)
    assert _run("kreditkarte", "uebernehmen", beleg, "--db", url).exit_code == 0
    (ordner / "gebuehr.sta").write_bytes(
        GIRO_APRIL.replace("DR698,65", "DR29,00")
        .replace("4301,35", "4971,00")
        .replace("KREDITKARTENABRECHNUNG", "KARTENJAHRESGEBUEHR VISA")
        .replace("2604050000099", "2604050000098")
        .encode("cp1252")
    )
    _run("bank", "abrufen", "--db", url)
    assert "Befund" in _text(_run("kreditkarte", "abgleich", "--db", url))
    (ordner / "april.sta").write_bytes(
        GIRO_APRIL.replace("DR698,65", "DR703,65")
        .replace("4301,35", "4296,35")
        .encode("cp1252")
    )
    _run("bank", "abrufen", "--db", url)
    r = _run("kreditkarte", "abgleich", "--db", url)
    assert r.exit_code == 0, r.output
    engine, make_session = _db(url)
    with make_session() as s:
        (a,) = lade_abrechnungen(s)
        gebuehr = next(t for t in lade_transaktionen(s) if t.betrag == -29)
    engine.dispose()
    abrechnung, umsatz = str(a.id)[:8], str(gebuehr.id)[:8]
    text = _text(r)
    assert text.count("mehrdeutig") == 2
    assert f"accounti kreditkarte loesen {abrechnung} --belastung {umsatz}" in text

    r = _run("kreditkarte", "loesen", abrechnung, "--db", url)
    assert r.exit_code == 1 and "keine zugeordnete" in _text(r)
    r = _run("kreditkarte", "loesen", abrechnung, "--belastung", umsatz, "--db", url)
    assert r.exit_code == 0, r.output
    assert "Getrennt" in _text(r) and "-29,00" in _text(r)
    r = _run("kreditkarte", "abgleich", "--db", url)
    text = _text(r)
    assert "mehrdeutig" not in text
    assert "Befund" in text and "Differenz -5,00 €" in text
    r = _run(
        "kreditkarte", "loesen", abrechnung, "--belastung", "ffffffff", "--db", url
    )
    assert r.exit_code == 1 and "Kein Umsatz" in _text(r)
