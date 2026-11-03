"""Verfahrensdokumentation (Spec 4.6, Akzeptanz 7): beschreibt den eingerichteten
Stand — eine Änderung an Konfiguration oder System schlägt sich im Dokument nieder."""

from datetime import date
from pathlib import Path

import pytest
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


def test_akzeptanz_7_beschreibt_den_eingerichteten_stand(tmp_path, monkeypatch):
    from tests.auth_hilfe import billige_hashes

    billige_hashes(monkeypatch)
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
        # Befund N-M4: die Ausnahme der Festschreibung steht im Verfahren
        "Eröffnungsbuchungen (EB-Werte) des Saldovortrags",
        "nur neu angelegt, nur am 01.01.",
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
        # Stand mit Baustein 10a (Befund M-4 der Schlussprüfung)
        "Benutzer und Rechte: keine Benutzer eingerichtet",
        "accounti sicherung erstellen",
        "verschlüsselt",
        "accounti betrieb lauf",
        "Laufsperre",
        # N-3: Gewinnermittlung ohne Angabe und vollständige EB-Form
        "Einnahmenüberschussrechnung (Standard, nicht ausdrücklich angegeben",
        "die andere ein Bestandskonto, kein Storno",
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
    from accounti.models.auth import Rolle
    from tests.auth_hilfe import lege_person_an

    with fabrik() as s:
        speichere_bankkonto(
            s, Bankkonto(iban="DE02120300000000202051", bezeichnung="Kreditkarte")
        )
        s.commit()
        lege_person_an(s, "eva", Rolle.BUCHHALTER)
        lege_person_an(s, "chef", Rolle.FREIGEBER, Rolle.VERWALTER, mit_2fa=False)
        zweite = erzeuge(s, config, db_url="sqlite:///x.db", stand=date(2026, 10, 21))
    for erwartet in (
        "eingang2",
        "imap.zwei.example",
        "Kreditkarte",
        "| op_alter | ordnung | warnung | aktiv |",
        "ab_betrag=10",
        "Vier-Augen-Prinzip nein",
        # Benutzer, Rollen, Rechte, Einmalcode und Freigabewege aus der
        # Systemdatenbank
        "Benutzer und Rechte: 2 Benutzer",
        "| eva | buchhalter (standard) | ja | ja |",
        "| chef | freigeber (standard), verwalter (standard) | nein | ja |",
        "buchhalter: lesen, buchen und korrigieren",
        "Einmalcode",
        "(ungeprüft)",
        "periode oeffnen",
        "journal uebernehmen",
    ):
        assert erwartet in zweite, erwartet
    assert "keine Benutzer eingerichtet" not in zweite
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


def test_kontierung_nennt_richtung_pruefung_und_marktplatz(tmp_path, monkeypatch):
    """Gesamttest Kontierung (Eingang B07/B15, Betrieb B3, Steuer B2): Die
    Verfahrensdokumentation beschreibt, was unabhängig von der Confidence zur
    Prüfung geht, welche Standardregeln im Kontenrahmen gelten und dass classify
    Marktplatz-Auszahlungen bis zum Abgleich offen lässt."""
    monkeypatch.chdir(tmp_path)  # config/regeln.yaml der Gesellschaft
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "regeln.yaml").write_text(
        "- {name: miete, muster: miete, richtung: ausgabe, soll_konto: '6310',\n"
        "   haben_konto: '1800', steuer_schluessel: null, pruefen: true}\n",
        encoding="utf-8",
    )
    config = tmp_path / "accounti.yaml"
    config.write_text(
        "mandant: {name: X}\nbuchhaltung: {kontenrahmen: SKR04, bank_konto: '1800'}\n",
        encoding="utf-8",
    )
    engine, fabrik = _fabrik(tmp_path)
    with fabrik() as s:
        text = erzeuge(s, config)
    for erwartet in (
        "0 gelernte Regeln",
        "1 eigenen Regeln",
        "5 Standardregeln im Kontenrahmen SKR04",
        "| Regel | Muster | Feld | Richtung | Soll | Haben | Schlüssel | Prüfen |",
        "| miete | miete | verwendungszweck | ausgabe | 6310 | 1800 | — | ja |",
        "unabhängig von der Confidence",
        "Gegenbuchung",
        "Bankkonto auf der falschen oder auf keiner Seite",
        "Marktplatz-Auszahlungen",
    ):
        assert erwartet in text, erwartet
    engine.dispose()


def test_fehlerhafte_regeldatei_steht_im_dokument(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "regeln.yaml").write_text(
        "- {name: kaputt, muster: x, soll_konto: '4900', haben_konto: '1200',\n"
        "   richtung: rueckwaerts}\n",
        encoding="utf-8",
    )
    engine, fabrik = _fabrik(tmp_path)
    with fabrik() as s:
        text = erzeuge(s, _konfig(tmp_path / "accounti.yaml"))
    assert "Regeldatei fehlerhaft" in text and "kaputt" in text
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


@pytest.mark.parametrize(
    ("gewinnermittlung", "erwartet"),
    [("euer", "auch im Folgejahr"), ("bilanz", "desselben Geschäftsjahres")],
)
def test_buchungsdatum_nach_gewinnermittlung(tmp_path, gewinnermittlung, erwartet):
    """Befund N-12: Bei EÜR darf die spätere Eingangsrechnung ins Folgejahr."""
    engine, fabrik = _fabrik(tmp_path)
    config = _konfig(tmp_path / "accounti.yaml")
    config.write_text(
        config.read_text(encoding="utf-8")
        + f"abschluss:\n  gewinnermittlung: {gewinnermittlung}\n",
        encoding="utf-8",
    )
    with fabrik() as s:
        text = erzeuge(s, config, stand=date(2026, 10, 21))
    assert erwartet in " ".join(text.split())
    engine.dispose()


def test_benutzer_bei_falscher_systemdatenbank_und_je_gesellschaft(
    tmp_path, monkeypatch
):
    """Abschlussprüfung N-C: Zeigt die Systemdatenbank ins Leere, steht in der Doku
    nicht „keine Benutzer“, wenn die Datenbank zu einer Benutzerverwaltung gehört —
    und es entsteht keine leere SQLite-Datei. Die Benutzerliste zeigt nur die
    Rollen der aktiven Gesellschaft."""
    from datetime import datetime

    from accounti.db.repo_auth import setze_merker_einmal
    from accounti.models.auth import Rolle
    from tests.auth_hilfe import billige_hashes, lege_person_an

    billige_hashes(monkeypatch)
    engine, fabrik = _fabrik(tmp_path)
    config = _konfig(tmp_path / "accounti.yaml")
    fehlt = tmp_path / "gibt-es-nicht.db"
    with fabrik() as s:
        setze_merker_einmal(
            s,
            "benutzerverwaltung",
            '{"gesellschaft": "a", "system": "x"}',
            datetime.now(),
        )
        s.commit()
        text = erzeuge(s, config, system_db=f"sqlite:///{fehlt}", gesellschaft="a")
    assert "keine Benutzer eingerichtet" not in text
    assert "nicht lesbar" in text and "ACCOUNTI_SYSTEM_DB" in text
    assert not fehlt.exists()

    system = tmp_path / "system.db"
    s_engine, s_fabrik = session_factory(f"sqlite:///{system}")
    init_db(s_engine)
    with s_fabrik() as s:
        lege_person_an(s, "eva", Rolle.BUCHHALTER, gesellschaft="a")
        lege_person_an(s, "bob", Rolle.FREIGEBER, gesellschaft="b")
    s_engine.dispose()
    with fabrik() as s:
        text = erzeuge(s, config, system_db=f"sqlite:///{system}", gesellschaft="a")
    engine.dispose()
    assert "| eva | buchhalter (a) |" in text
    assert "bob" not in text


def test_gelernte_regeln_in_der_verfahrensdoku(tmp_path, monkeypatch):
    """Baustein 10b: Regeldatei der Gesellschaft, gelernte Regeln aus der Datenbank
    (aktiv, deaktiviert, Richtung, wer und wann) und der Schalter."""
    from accounti.klassifikation.lernen import deaktiviere, lerne_regex
    from accounti.models.kontierung import Richtung

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "regeln.yaml").write_text(
        "- name: miete\n  muster: miete\n  soll_konto: '4210'\n  haben_konto: '1200'\n",
        encoding="utf-8",
    )
    engine, fabrik = _fabrik(tmp_path)
    config = tmp_path / "accounti.yaml"
    config.write_text("buchhaltung:\n  gelernte_regeln: pruefen\n", encoding="utf-8")
    with fabrik() as s:
        lerne_regex(
            s, "telekom", "telekom", "4920", "1200", 9, "jan", richtung=Richtung.AUSGABE
        )
        alt = lerne_regex(s, "aral", "aral", "4530", "1200", 9, "eva")
        deaktiviere(s, alt.id, "chef", "Privatwagen")
        s.commit()
        text = erzeuge(s, config, db_url="sqlite:///x.db", stand=date(2026, 10, 21))
    engine.dispose()
    assert "1 gelernte Regeln" in text and "1 eigenen Regeln" in text
    assert "gelernte_regeln: **pruefen**" in text
    assert "| telekom | /telekom/ | ausgabe | 4920 | 1200 | 9 | jan, " in text
    assert "deaktiviert (chef: Privatwagen)" in text
    assert "Kontierungsregeln lernen" in text  # Recht in der Rechtetabelle


def test_verfahrensdoku_nennt_regeln_ohne_richtung(tmp_path, monkeypatch):
    """Nachbesserung M3: Die Verfahrensdoku behauptet nicht mehr pauschal, gelernte
    Regeln gälten nur in ihrer Zahlungsrichtung — ``accounti lerne`` ohne
    ``--richtung`` gilt für Ein- und Ausgänge, und die Doku zählt solche Regeln."""
    from accounti.klassifikation.lernen import lerne_regex

    monkeypatch.chdir(tmp_path)
    engine, fabrik = _fabrik(tmp_path)
    with fabrik() as s:
        lerne_regex(s, "telekom", "telekom", "4920", "1200", 9, "jan")
        s.commit()
        text = erzeuge(
            s,
            tmp_path / "fehlt.yaml",
            db_url="sqlite:///x.db",
            stand=date(2026, 10, 21),
        )
    engine.dispose()
    assert "nur in der Zahlungsrichtung ihres Quellumsatzes" not in text
    assert "„beide“" in text and "aktiv sind 1 solche Regeln" in text
    assert "| telekom | /telekom/ | beide |" in text


def test_belegeingang_beschreibt_kanaele_und_dateipruefung_wie_sie_sind(tmp_path):
    """Gesamttest B03: Ordner → belege abholen (geprüft), Upload → belege import
    (Handimport, ungeprüft) — vorher vertauscht und „Prüfung je Kanal“ behauptet."""
    engine, fabrik = _fabrik(tmp_path)
    with fabrik() as s:
        text = erzeuge(s, _konfig(tmp_path / "accounti.yaml"), stand=date(2026, 10, 21))
    engine.dispose()
    zeile = next(z for z in text.splitlines() if z.startswith("| ordner"))
    assert "belege abholen --kanal ordner" in zeile
    zeile = next(z for z in text.splitlines() if z.startswith("| upload"))
    assert "belege import" in zeile
    assert "Dateiprüfung für E-Mail, Webhook, Connector und Ordner" in text
    assert "Handimport einzelner Dateien (accounti belege import) prüft" in text


def test_regelmuster_feld_und_aufbewahrung(tmp_path, monkeypatch):
    """Gesamttest Abschluss B10: das Muster stand als ``re.compile(…)`` im Dokument,
    das Feld fehlte; die Aufbewahrung nannte 10 Jahre ab Ende des Eingangsjahres —
    im Widerspruch zu ``betrieb aufbewahrung``."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "regeln.yaml").write_text(
        '- {name: alpha, muster: "ALPHA", feld: beide, soll_konto: "1200", '
        'haben_konto: "8400", steuer_schluessel: 3}\n',
        encoding="utf-8",
    )
    engine, fabrik = _fabrik(tmp_path)
    with fabrik() as s:
        text = erzeuge(s, _konfig(tmp_path / "accounti.yaml"))
    engine.dispose()
    kopf = "| Regel | Muster | Feld | Richtung | Soll | Haben | Schlüssel | Prüfen |"
    assert kopf in text
    assert "| alpha | ALPHA | beide | beide | 1200 | 8400 | 3 | nein |" in text
    assert "re.compile" not in text
    assert "Ende des Eingangsjahres" not in text
    assert "Aufbewahrung der Buchungsbelege 8 Jahre" in text
    assert "Rechnungen 8 Jahre (§ 14b Abs. 1 UStG)" in text
    assert "ab Schluss des Kalenderjahres des Belegdatums" in text
    assert "Bücher und Aufzeichnungen 10 Jahre" in text


def test_regelmuster_mit_senkrechtem_strich(tmp_path, monkeypatch):
    """Nachprüfung F, N6: ``|`` im Muster wurde in der Tabelle zu ``/`` — die
    dokumentierte Regel war eine andere als die angewandte (GoBD Rz. 151 ff.)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "regeln.yaml").write_text(
        '- {name: porto, muster: "PORTO|BRIEFMARKE", feld: verwendungszweck, '
        'soll_konto: "4910", haben_konto: "1200"}\n',
        encoding="utf-8",
    )
    engine, fabrik = _fabrik(tmp_path)
    with fabrik() as s:
        text = erzeuge(s, _konfig(tmp_path / "accounti.yaml"))
    engine.dispose()
    zeile = "| porto | PORTO\\|BRIEFMARKE | verwendungszweck | beide | 4910 | 1200 |"
    assert zeile in text
    assert "PORTO/BRIEFMARKE" not in text
    pdf = als_pdf(text, tmp_path / "doku.pdf")
    inhalt = "".join(seite.extract_text() for seite in PdfReader(pdf).pages)
    assert "PORTO|BRIEFMARKE" in inhalt and "PORTO\\|" not in inhalt


def test_connector_adresse_ohne_zugangsdaten(tmp_path):
    """g5w-konten N1 (Runde 6): die Verfahrensdokumentation nannte netloc der
    ``basis_url`` — samt Benutzer und Passwort, wenn die Adresse sie trägt."""
    zusatz = (
        "  connectoren:\n    - name: portal\n      typ: json\n"
        "      basis_url: https://jan:sehr-geheim@portal.example:8443/api\n"
    )
    engine, fabrik = _fabrik(tmp_path)
    with fabrik() as s:
        text = erzeuge(
            s,
            _konfig(tmp_path / "accounti.yaml", zusatz_postfach=zusatz),
            stand=date(2026, 10, 21),
        )
    engine.dispose()
    zeile = next(z for z in text.splitlines() if z.startswith("| connector"))
    assert "portal.example:8443" in zeile
    assert "sehr-geheim" not in text and "jan:" not in zeile


@pytest.mark.parametrize(
    ("basis", "erwartet", "darf_nicht"),
    [
        ("https://alarm:Kassel#2026@portal.example/api", "json: portal.example |",
         "Kassel"),
        ("https://alarm:Wint3r?Sonne@portal.example/api", "json: portal.example |",
         "Wint3r"),
        ("https://alarm:1234#abc@portal.example:8443/api", "portal.example:8443",
         "1234"),
    ],
    ids=["raute", "fragezeichen", "ziffern"],
)  # fmt: skip
def test_connector_adresse_mit_unkodiertem_passwort(
    tmp_path, basis, erwartet, darf_nicht
):
    """g6w B-2 (Runde 7): „netloc.rpartition('@')“ nannte bei unkodiertem # oder ? im
    Passwort Benutzer und Passwortanfang („json: alarm:Kassel“)."""
    zusatz = (
        "  connectoren:\n    - name: portal\n      typ: json\n"
        f'      basis_url: "{basis}"\n'
    )
    engine, fabrik = _fabrik(tmp_path)
    with fabrik() as s:
        text = erzeuge(
            s,
            _konfig(tmp_path / "accounti.yaml", zusatz_postfach=zusatz),
            stand=date(2026, 10, 21),
        )
    engine.dispose()
    zeile = next(z for z in text.splitlines() if z.startswith("| connector"))
    assert erwartet in zeile, zeile
    assert darf_nicht not in text and "alarm" not in zeile


def test_connector_mit_ungueltiger_adresse_bricht_nicht_ab(tmp_path):
    """g6w B-4 (Runde 7): „https://[::1/api“ (Tippfehler) endete mit ValueError aus
    urlsplit, es entstand kein Dokument. Jetzt steht der Fehler im Dokument."""
    zusatz = (
        "  connectoren:\n    - name: portal\n      typ: json\n"
        '      basis_url: "https://[::1/api"\n'
    )
    engine, fabrik = _fabrik(tmp_path)
    with fabrik() as s:
        text = erzeuge(
            s,
            _konfig(tmp_path / "accounti.yaml", zusatz_postfach=zusatz),
            stand=date(2026, 10, 21),
        )
    engine.dispose()
    zeile = next(z for z in text.splitlines() if z.startswith("| connector"))
    assert "(Adresse fehlerhaft)" in zeile
    assert (
        "**Konfiguration belegkanaele.connectoren[portal].basis_url fehlerhaft:**"
        in text
    )
    assert "## 3" in text  # das Dokument geht weiter
