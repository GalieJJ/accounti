"""Abschnitt `aufgaben` in config/accounti.yaml — alles hat Standardwerte."""

from decimal import Decimal

import pytest

from accounti.aufgaben.einstellungen import (
    AufgabenEinstellungen,
    lade_aufgaben_einstellungen,
)
from accounti.konfiguration import KonfigurationError


def test_ohne_datei_und_ohne_abschnitt(tmp_path):
    e = lade_aufgaben_einstellungen(tmp_path / "fehlt.yaml")
    assert e == AufgabenEinstellungen()
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text("mandant: {name: X}\n", encoding="utf-8")
    e = lade_aufgaben_einstellungen(pfad)
    assert e.frist_tage("beleg_fehlt") == 10
    assert e.frist_tage("kontierung_pruefen") == 10
    assert e.frist_tage("bank_freigabe") == 0
    assert e.frist_tage("irgendwas_neues") == 7
    assert e.pruefung.kontierung_schwelle == 0.95
    assert e.pruefung.beleg_fehlt_ab_betrag == Decimal("0")
    assert e.erinnerung.plan("beleg_fehlt").stufen == [0, 3, 7]
    assert e.benachrichtigung.kanaele == ["email"]
    assert e.zustaendigkeit == [] and e.rollen == {}


def test_vollstaendiger_abschnitt(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTI_AUFGABEN_WEBHOOK", "https://chat.example/hooks/geheim")
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(
        """
aufgaben:
  ich: jan
  rollen:
    buchhaltung: [jan, erika]
  zustaendigkeit:
    - wenn: {art: beleg_fehlt}
      an: erika
  fristen:
    standard: 5
    beleg_fehlt: 14
  erinnerung:
    stufen: [0, 2, 5]
    eskalation_an: "@leitung"
    arten:
      beleg_fehlt: {stufen: [0, 7, 14]}
  pruefung:
    kontierung_schwelle: 0.9
    beleg_fehlt_ab_betrag: 25
    beleg_fehlt_nach_tagen: 3
    abgeschaltet: [kontakt_pruefen]
  benachrichtigung:
    kanaele: [email, webhook]
    absender: "accounti <accounti@firma.example>"
    empfaenger:
      jan: jan@firma.example
      gemeinsam: buchhaltung@firma.example
    webhook:
      url: "${ACCOUNTI_AUFGABEN_WEBHOOK}"
""",
        encoding="utf-8",
    )
    e = lade_aufgaben_einstellungen(pfad)
    assert e.ich == "jan" and e.rollen == {"buchhaltung": ["jan", "erika"]}
    assert e.zustaendigkeit[0].an == "erika"
    assert e.frist_tage("beleg_fehlt") == 14
    assert e.frist_tage("kontierung_pruefen") == 10  # Standard der Art bleibt
    assert e.frist_tage("neu") == 5
    assert e.erinnerung.plan("beleg_fehlt").stufen == [0, 7, 14]
    assert e.erinnerung.plan("beleg_fehlt").eskalation_an == "@leitung"
    assert e.erinnerung.plan("kontierung_pruefen").stufen == [0, 2, 5]
    assert e.pruefung.kontierung_schwelle == 0.9
    assert e.pruefung.beleg_fehlt_ab_betrag == Decimal("25")
    assert e.pruefung.abgeschaltet == ["kontakt_pruefen"]
    assert e.benachrichtigung.kanaele == ["email", "webhook"]
    assert e.benachrichtigung.webhook is not None
    assert e.benachrichtigung.webhook.url == "https://chat.example/hooks/geheim"
    assert e.benachrichtigung.empfaenger["gemeinsam"] == "buchhaltung@firma.example"


@pytest.mark.parametrize(
    ("abschnitt", "meldung"),
    [
        ("pruefung: {kontierung_schwelle: 1.5}", "kontierung_schwelle"),
        ("erinnerung: {stufen: [3, 0]}", "aufsteigend"),
        ("erinnerung: {stufen: [-1]}", "stufen"),
        ("benachrichtigung: {kanaele: [brieftaube]}", "brieftaube"),
        ("benachrichtigung: {kanaele: []}", "mindestens ein Kanal"),
        ("zustaendigkeit: [{wenn: {art: x}}]", "an oder rolle"),
        ("zustaendigkeit: [{wenn: {art: x}, an: jan, rolle: b}]", "an oder rolle"),
        ("fristen: {beleg_fehlt: -2}", "fristen"),
        ("benachrichtigung: {kanaele: [webhook]}", "webhook.url"),
    ],
)
def test_fehler_werden_benannt(tmp_path, abschnitt, meldung):
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(f"aufgaben:\n  {abschnitt}\n", encoding="utf-8")
    with pytest.raises(KonfigurationError, match=meldung):
        lade_aufgaben_einstellungen(pfad)


def test_fehlende_umgebungsvariable(tmp_path, monkeypatch):
    monkeypatch.delenv("ACCOUNTI_FEHLT", raising=False)
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(
        "aufgaben:\n  benachrichtigung:\n    webhook: {url: '${ACCOUNTI_FEHLT}'}\n",
        encoding="utf-8",
    )
    with pytest.raises(KonfigurationError, match="ACCOUNTI_FEHLT"):
        lade_aufgaben_einstellungen(pfad)
