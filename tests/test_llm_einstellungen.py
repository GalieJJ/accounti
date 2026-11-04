"""Abschnitt ``llm`` wirkt (Baustein 10c P4, Schritt 5; D18, G-M5, A44).

``lade_llm`` liest Anbieter, Modell, Schlüssel und die Schwellen; ``classify``,
``bank lauf`` und die REST-Route reichen ``auto_buchen_schwelle`` über die
``KlassifikationsEngine`` an ``zu_buchungssatz`` und Anbieter/Modell an die LLM-Stufe.
``${VAR}`` gilt nur in ``api_key`` und nachsichtig: Fehlt die Variable, ist der
Schlüssel ``None`` (litellm liest ihn dann wie bisher selbst aus der Umgebung).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from accounti.buchung.kontierung import kontiere_umsaetze
from accounti.cli import app
from accounti.db.repository import lade_buchungen
from accounti.klassifikation.engine import KlassifikationsEngine
from accounti.konfiguration import Buchhaltung, KonfigurationError
from accounti.models import BuchungStatus, Klassifikationsergebnis, Transaktion
from tests.pruefung_hilfe import (  # noqa: F401
    anlegen,
    db_url,
    make_session_fixture,
    umsatz,
)

WURZEL = Path(__file__).resolve().parents[1]
VORLAGE = WURZEL / "config" / "accounti.example.yaml"
runner = CliRunner()


class LLMAttrappe:
    model = "attrappe/kontierer-1"

    def klassifiziere(self, tx: Transaktion) -> Klassifikationsergebnis:
        return Klassifikationsergebnis(
            transaktion_id=tx.id,
            soll_konto="4980",
            haben_konto="1200",
            steuer_schluessel=9,
            buchungstext=tx.verwendungszweck[:60],
            confidence=0.9,
            begruendung="Bürobedarf",
            quelle="llm",
            modell=self.model,
        )


def test_standard_wie_bisher(tmp_path, monkeypatch):
    """Ohne Abschnitt dieselben Werte wie bisher fest im Code (0,95; Standardmodell der
    LLM-Stufe), die Vorlage ebenso."""
    from accounti.buchung.mapper import AUTO_SCHWELLE
    from accounti.klassifikation.einstellungen import LlmEinstellungen, lade_llm

    standard = lade_llm(tmp_path / "fehlt.yaml")
    assert standard == LlmEinstellungen()
    assert standard.auto_buchen_schwelle == AUTO_SCHWELLE == 0.95
    assert standard.pruefung_schwelle == 0.70
    assert standard.modell == "anthropic/claude-sonnet-4-20250514"
    assert standard.api_key is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-probe")
    vorlage = lade_llm(VORLAGE)
    assert vorlage.model_copy(update={"api_key": None}) == standard
    assert vorlage.api_key == "sk-probe"


@pytest.mark.parametrize(
    ("schwelle", "status"),
    [(0.85, BuchungStatus.AUTO_GEBUCHT), (0.95, BuchungStatus.ZUR_PRUEFUNG)],
)
def test_schwelle_wirkt_auf_den_status(make_session, schwelle, status):
    """Confidence 0,9: mit Schwelle 0,85 automatisch gebucht, mit 0,95 zur Prüfung."""
    anlegen(make_session, umsatz("-23.80", zweck="Unbekannter Laden", name="Laden"))
    engine = KlassifikationsEngine(
        llm=LLMAttrappe(),  # type: ignore[arg-type]
        auto_buchen_schwelle=schwelle,
    )
    with make_session() as s:
        kontiere_umsaetze(s, engine, Buchhaltung())
        s.commit()
        (buchung,) = lade_buchungen(s)
    assert buchung.status is status


def test_classify_nimmt_die_schwelle_der_konfiguration(tmp_path, monkeypatch):
    """``classify`` liest ``llm.auto_buchen_schwelle`` der Konfiguration (bisher immer
    0,95): eine Regel mit Confidence 0,9 bucht bei 0,85 automatisch."""
    monkeypatch.chdir(tmp_path)
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_KONFIG"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "regeln.yaml").write_text(
        "- name: laden\n  muster: unbekannter laden\n  soll_konto: '4980'\n"
        "  haben_konto: '1200'\n  steuer_schluessel: 9\n  confidence: 0.9\n",
        encoding="utf-8",
    )
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text("llm:\n  auto_buchen_schwelle: 0.85\n", encoding="utf-8")
    from accounti.db import init_db, session_factory

    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    anlegen(fabrik, umsatz("-23.80", zweck="Unbekannter Laden", name="Laden"))
    r = runner.invoke(
        app, ["classify", "--db", url, "--no-llm", "--config", str(konfig)]
    )
    assert r.exit_code == 0, r.output
    with fabrik() as s:
        (buchung,) = lade_buchungen(s)
    engine.dispose()
    assert buchung.status is BuchungStatus.AUTO_GEBUCHT


TANKEN = (
    "- name: tanken\n  muster: shell\n  feld: beide\n  soll_konto: '4530'\n"
    "  haben_konto: '1200'\n  steuer_schluessel: 9\n  confidence: {confidence}\n"
)


@pytest.mark.parametrize(
    ("schwelle", "confidence", "status"),
    [
        pytest.param("0.85", "0.9", BuchungStatus.AUTO_GEBUCHT, id="locker"),
        pytest.param("0.99", "0.97", BuchungStatus.ZUR_PRUEFUNG, id="streng"),
    ],
)
def test_bank_lauf_nimmt_die_schwelle_der_konfiguration(
    tmp_path, monkeypatch, schwelle, confidence, status
):
    """tests-4: ``bank lauf --no-llm`` liest ``llm.auto_buchen_schwelle`` wie classify —
    für den Umsatz ohne Beleg und für den, den der Lauf selbst mit einer Quittung
    abgleicht (verhalten-2). Mit dem festen Standard 0,95 stünde in beiden Fällen der
    andere Status."""
    from accounti.db import init_db, session_factory
    from accounti.db.repository import speichere_beleg, speichere_transaktion
    from tests.test_bank_abgleich import umsatz as bankumsatz
    from tests.test_schwelle_ueberall import tankquittung

    monkeypatch.chdir(tmp_path)
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_KONFIG"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "regeln.yaml").write_text(
        TANKEN.format(confidence=confidence), encoding="utf-8"
    )
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        f"llm:\n  auto_buchen_schwelle: {schwelle}\n  pruefung_schwelle: 0.5\n",
        encoding="utf-8",
    )
    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    with fabrik() as s:
        speichere_transaktion(s, bankumsatz(betrag="-59.50", tag=0))
        speichere_transaktion(s, bankumsatz(betrag="-33.00", tag=5))
        speichere_beleg(s, tankquittung())
        s.commit()
    r = runner.invoke(
        app, ["bank", "lauf", "--db", url, "--no-llm", "--config", str(konfig)]
    )
    assert r.exit_code == 0, r.output
    assert "Kontierung: 2 kontiert (davon 1 mit Beleg)" in r.output
    with fabrik() as s:
        buchungen = lade_buchungen(s)
    engine.dispose()
    assert {(b.beleg_id is not None, b.status) for b in buchungen} == {
        (True, status),
        (False, status),
    }


def test_rest_banklauf_nimmt_die_schwelle_der_gesellschaft(tmp_path, monkeypatch):
    """tests-4: ``POST /api/v1/laeufe/bank`` gibt ``bank_lauf`` eine Engine mit
    ``llm.auto_buchen_schwelle`` der Gesellschaft des Tokens — a aus ihrer Datei, b aus
    einer Version ihrer Datenbank; ohne Abschnitt der Standard."""
    import accounti.bank.lauf as lauf
    from accounti.db import session_factory
    from accounti.db.repo_einstellungen import fuege_version_an
    from accounti.models.auth import TokenRecht
    from tests.api_hilfe import webwelt
    from tests.auth_hilfe import billige_hashes

    billige_hashes(monkeypatch)
    welt = webwelt(tmp_path)
    pfad = welt.umgebung.config["a"]
    pfad.write_text(
        pfad.read_text(encoding="utf-8") + "llm:\n  auto_buchen_schwelle: 0.85\n",
        encoding="utf-8",
    )
    engine, fabrik = session_factory(welt.umgebung.db["b"])
    with fabrik() as s:
        fuege_version_an(
            s,
            "llm",
            {"auto_buchen_schwelle": 0.99},
            person="erika",
            grund="Probe",
            quelle="cli",
        )
        s.commit()
    engine.dispose()
    gesehen: list[float] = []

    def bank_lauf(s, engine, buchhaltung, **_):  # noqa: ANN001, ANN003, ANN202
        gesehen.append(engine.auto_buchen_schwelle)
        raise RuntimeError("nur bis hierher")

    monkeypatch.setattr(lauf, "bank_lauf", bank_lauf)
    for kuerzel in ("a", "b"):
        token = welt.token(kuerzel, TokenRecht.LAEUFE_STARTEN, name=f"erp-{kuerzel}")
        welt.client().post(
            "/api/v1/laeufe/bank", headers={"Authorization": f"Bearer {token}"}
        )
    assert gesehen == [0.85, 0.99]


def test_llm_stufe_bekommt_modell_und_schluessel(tmp_path, monkeypatch):
    """Anbieter und Modell (und ein Schlüssel aus ``${VAR}``) gehen an die LLM-Stufe."""
    from accounti.klassifikation import llm as llm_modul
    from accounti.klassifikation.einstellungen import lade_llm

    monkeypatch.setenv("MEIN_LLM_SCHLUESSEL", "sk-test")
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        "llm:\n  provider: ollama\n  model: llama3\n"
        "  api_key: ${MEIN_LLM_SCHLUESSEL}\n",
        encoding="utf-8",
    )
    einstellungen = lade_llm(konfig)
    assert einstellungen.modell == "ollama/llama3"
    gesehen: dict[str, object] = {}

    def completion(**kw: object) -> object:
        gesehen.update(kw)
        raise RuntimeError("kein Netz im Test")

    monkeypatch.setattr(llm_modul, "completion", completion)
    stufe = llm_modul.LLMEngine(
        model=einstellungen.modell, api_key=einstellungen.api_key
    )
    assert stufe.klassifiziere(umsatz()) is None
    assert gesehen["model"] == "ollama/llama3"
    assert gesehen["api_key"] == "sk-test"
    stufe = llm_modul.LLMEngine()
    gesehen.clear()
    stufe.klassifiziere(umsatz())
    assert "api_key" not in gesehen  # litellm liest die Umgebung selbst


def test_pruefschwelle_ueber_auto_ist_fehler(tmp_path):
    from accounti.klassifikation.einstellungen import lade_llm

    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        "llm:\n  auto_buchen_schwelle: 0.6\n  pruefung_schwelle: 0.7\n", "utf-8"
    )
    with pytest.raises(KonfigurationError, match=r"llm.*pruefung_schwelle"):
        lade_llm(konfig)
    konfig.write_text("llm:\n  auto_buchen_schwelle: 1.5\n", "utf-8")
    with pytest.raises(KonfigurationError, match=r"llm\.auto_buchen_schwelle"):
        lade_llm(konfig)


def test_verfahrensdoku_nennt_die_wirksame_schwelle(tmp_path):
    from accounti.db import init_db, session_factory
    from accounti.pruefung.verfahrensdoku import erzeuge

    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        "mandant:\n  name: Probe GmbH\nllm:\n  provider: ollama\n  model: llama3\n"
        "  auto_buchen_schwelle: 0.85\n",
        encoding="utf-8",
    )
    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    with fabrik() as s:
        text = erzeuge(s, konfig, db_url=url)
    engine.dispose()
    assert "**Automatisch gebucht** (Status auto) wird ab Confidence 0.85" in text
    assert "LLM-Stufe: Modell ollama/llama3" in text


def test_ohne_api_key_variable_laeuft_no_llm(tmp_path, monkeypatch):
    """G-M5: Vorlage, ``ANTHROPIC_API_KEY`` nicht gesetzt → ``api_key`` ist ``None``;
    ``bank lauf --no-llm`` und ``verfahrensdoku`` laufen wie bisher."""
    from accounti.db import init_db, session_factory
    from accounti.klassifikation.einstellungen import lade_llm

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_KONFIG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    assert lade_llm(VORLAGE).api_key is None
    url = db_url(tmp_path)
    engine, _ = session_factory(url)
    init_db(engine)
    engine.dispose()
    r = runner.invoke(
        app, ["bank", "lauf", "--db", url, "--no-llm", "--config", str(VORLAGE)]
    )
    assert r.exit_code == 0, r.output
    r = runner.invoke(
        app,
        [
            "verfahrensdoku", "--db", url, "--config", str(VORLAGE), "--ausgabe",
            str(tmp_path / "doku.md"),
        ],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
