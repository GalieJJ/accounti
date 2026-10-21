"""Verfahrensdokumentation (Spec 4.6, Akzeptanz 7): beschreibt den eingerichteten
Stand — eine Änderung an Konfiguration oder System schlägt sich im Dokument nieder."""

from datetime import date
from pathlib import Path

from pypdf import PdfReader
from typer.testing import CliRunner

from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import speichere_bankkonto
from accounti.models import Bankkonto
from accounti.pruefung.journal import lade_journal
from accounti.pruefung.perioden import schliesse
from accounti.pruefung.verfahrensdoku import als_pdf, erzeuge, fassung, vermerke
from tests.pruefung_hilfe import db_url

KONFIG = """
mandant:
  name: Galerie Muster GmbH
  ust_id: DE999999999
  anschrift: {{strasse: Beispielweg 3, plz: "24103", ort: Kiel}}
buchhaltung:
  kontenrahmen: SKR03
belegkanaele:
  email:
    - name: rechnungen
      host: imap.galerie.example
      benutzer: rechnungen@galerie.example
      passwort: "${{ACCOUNTI_IMAP_PASSWORT}}"
{zusatz_postfach}
pruefung:
  abgeschaltet: [{abgeschaltet}]
  regeln:
    umsatz_ohne_beleg: {{ab_betrag: {ab_betrag}}}
  belegfrei:
    - {{name: kontofuehrung, muster: "kontoführung", begruendung: "Bankentgelt"}}
aufgaben:
  rollen:
    buchhaltung: [jan, erika]
zahlung:
  vier_augen: {vier_augen}
"""


def _konfig(pfad: Path, **kw: object) -> Path:
    werte = {
        "zusatz_postfach": "",
        "abgeschaltet": "op_alter",
        "ab_betrag": 5,
        "vier_augen": "true",
    }
    werte.update(kw)
    pfad.write_text(KONFIG.format(**werte), encoding="utf-8")
    return pfad


def _fabrik(tmp_path):
    engine, fabrik = session_factory(db_url(tmp_path))
    init_db(engine)
    return engine, fabrik


def test_akzeptanz_7_beschreibt_den_eingerichteten_stand(tmp_path):
    engine, fabrik = _fabrik(tmp_path)
    config = _konfig(tmp_path / "accounti.yaml")
    with fabrik() as s:
        speichere_bankkonto(
            s,
            Bankkonto(
                iban="DE89370400440532013000",
                bezeichnung="Giro Sparkasse",
                sachkonto="1200",
            ),
        )
        schliesse(s, "2026-08", "erika")
        s.commit()
        erste = erzeuge(s, config, db_url="sqlite:///x.db", stand=date(2026, 10, 21))
    for erwartet in (
        "# Verfahrensdokumentation — Galerie Muster GmbH",
        "Stand: 21.10.2026",
        "rechnungen",
        "imap.galerie.example",
        "Giro Sparkasse",
        "DE89370400440532013000",
        "| op_alter | ordnung | warnung | abgeschaltet |",
        "ab_betrag=5",
        "kontofuehrung",
        "Vier-Augen-Prinzip ja",
        "| buchhaltung | jan, erika |",
        "2026-08 | festgeschrieben",
        "ab Confidence 0.95",
        # alle Wege, auf denen accounti ohne Freigabe bucht (Status auto)
        "accounti opos verbuchen",
        "Belegabgleich",
        "Zahlungsausgleich",
        "Kreditkartenabgleich",
        "Marktplatz-Abrechnungen und -Auszahlungen",
        "Zahllast",
        "Kontenrahmen:** SKR03",
        "## 4 Betriebsdokumentation",
    ):
        assert erwartet in erste, erwartet
    assert "${ACCOUNTI_IMAP_PASSWORT}" not in erste  # keine Geheimnisse

    # Konfiguration und System ändern sich — das Dokument zieht nach
    _konfig(
        config,
        zusatz_postfach=(
            "    - name: eingang2\n      host: imap.zwei.example\n"
            "      benutzer: zwei@galerie.example\n"
        ),
        abgeschaltet="",
        ab_betrag=10,
        vier_augen="false",
    )
    with fabrik() as s:
        speichere_bankkonto(
            s, Bankkonto(iban="DE02120300000000202051", bezeichnung="Kreditkarte")
        )
        s.commit()
        zweite = erzeuge(s, config, db_url="sqlite:///x.db", stand=date(2026, 10, 21))
    for erwartet in (
        "eingang2",
        "imap.zwei.example",
        "Kreditkarte",
        "| op_alter | ordnung | warnung | aktiv |",
        "ab_betrag=10",
        "Vier-Augen-Prinzip nein",
    ):
        assert erwartet in zweite, erwartet
    assert "ab_betrag=5" not in zweite and fassung(erste) != fassung(zweite)
    engine.dispose()


def test_fassungen_im_journal_und_historie(tmp_path):
    engine, fabrik = _fabrik(tmp_path)
    config = _konfig(tmp_path / "accounti.yaml")
    with fabrik() as s:
        erste = erzeuge(s, config)
        e = vermerke(s, erste, "verfahrensdoku.md")
        s.commit()
        assert e is not None and e.bezug == fassung(erste)
        zweite = erzeuge(s, config)
        (eintrag,) = lade_journal(s, vorgang="verfahrensdoku_erstellt")
    assert "Änderungshistorie" in zweite and fassung(erste)[:16] in zweite
    assert eintrag.nr == e.nr
    engine.dispose()


def test_fehlerhafte_konfiguration_steht_im_dokument(tmp_path):
    engine, fabrik = _fabrik(tmp_path)
    config = tmp_path / "accounti.yaml"
    config.write_text("mandant: {name: X}\npruefung: {abgeschaltet: 5}\n", "utf-8")
    with fabrik() as s:
        text = erzeuge(s, config)
    assert "Konfiguration pruefung fehlerhaft" in text
    engine.dispose()


def test_pdf(tmp_path):
    engine, fabrik = _fabrik(tmp_path)
    with fabrik() as s:
        text = erzeuge(s, _konfig(tmp_path / "accounti.yaml"))
    pdf = als_pdf(text, tmp_path / "doku.pdf")
    assert pdf.read_bytes().startswith(b"%PDF")
    inhalt = "".join(seite.extract_text() for seite in PdfReader(pdf).pages)
    assert "Verfahrensdokumentation" in inhalt and "Galerie Muster GmbH" in inhalt
    engine.dispose()


def test_cli(tmp_path):
    engine, fabrik = _fabrik(tmp_path)
    config = _konfig(tmp_path / "accounti.yaml")
    ausgabe, pdf = tmp_path / "vd.md", tmp_path / "vd.pdf"
    r = CliRunner().invoke(
        app,
        [
            "verfahrensdoku",
            "--ausgabe",
            str(ausgabe),
            "--pdf",
            str(pdf),
            "--db",
            db_url(tmp_path),
            "--config",
            str(config),
        ],
    )
    assert r.exit_code == 0, r.output
    assert ausgabe.read_text("utf-8").startswith("# Verfahrensdokumentation")
    assert pdf.is_file()
    with fabrik() as s:
        (e,) = lade_journal(s, vorgang="verfahrensdoku_erstellt")
    assert e.bezug == fassung(ausgabe.read_text("utf-8"))
    engine.dispose()
