"""Eine Schwelle des automatischen Buchens überall (Baustein 10c P4a, Befund
verhalten-2).

``llm.auto_buchen_schwelle`` gilt nicht nur für Umsätze ohne Beleg
(``zu_buchungssatz``), sondern auch für das Sachkonto, das eine Regel einer
Belegbuchung (``kontiere_beleg``, ``sachkonto_fuer_beleg``) und ``opos verbuchen``
liefert. Bisher verglichen beide fest mit 0,95: Bei Schwelle 0,99 und Regel 0,97 ging
der Umsatz ohne Beleg zur Prüfung, derselbe mit Beleg wurde automatisch gebucht — und
die Verfahrensdokumentation beschrieb das falsch.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from accounti.bank.abgleichslauf import gleiche_belege_ab
from accounti.buchung.kontierung import kontiere_umsaetze
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_buchungen,
    speichere_beleg,
    speichere_kontakt,
    speichere_transaktion,
)
from accounti.klassifikation.engine import KlassifikationsEngine, Regel, RegelwerkEngine
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Belegposition,
    BuchungStatus,
    Kontakt,
    KontaktStatus,
)
from accounti.opos.verbuchung import verbuche_belege
from tests.pruefung_hilfe import db_url
from tests.test_bank_abgleich import quittung, umsatz
from tests.test_opos_verbuchung import eingangsrechnung

runner = CliRunner()

# (Schwelle, Confidence der Regel, erwarteter Status mit und ohne Beleg)
FAELLE = [
    pytest.param(0.99, 0.97, BuchungStatus.ZUR_PRUEFUNG, id="streng"),
    pytest.param(0.80, 0.94, BuchungStatus.AUTO_GEBUCHT, id="locker"),
]


def _tanken(confidence: float) -> Regel:
    return Regel(
        "tanken",
        r"shell",
        "4530",
        "1200",
        9,
        "Tanken",
        feld="beide",
        confidence=confidence,
    )


def tankquittung():
    """Tankquittung 59,50 € mit einer Position zu 19 % (Steuer bekannt)."""
    b = quittung(brutto="59.50")
    return b.model_copy(
        update={
            "positionen": [
                Belegposition(
                    beleg_id=b.id,
                    bezeichnung="Super E10",
                    netto=Decimal("50.00"),
                    steuersatz=Decimal("19"),
                    steuer_betrag=Decimal("9.50"),
                )
            ]
        }
    )


@pytest.fixture
def fabrik(tmp_path):
    engine, fabrik = session_factory(db_url(tmp_path))
    init_db(engine)
    yield fabrik
    engine.dispose()


def _mit_und_ohne_beleg(fabrik) -> None:  # noqa: ANN001
    """Zwei Umsätze an Shell, einer mit bestätigtem Beleg."""
    with fabrik() as s:
        speichere_transaktion(s, umsatz(betrag="-59.50", tag=0))
        speichere_transaktion(s, umsatz(betrag="-33.00", tag=5))
        speichere_beleg(s, tankquittung())
        s.commit()
    with fabrik() as s:
        assert len(gleiche_belege_ab(s).automatisch) == 1
        s.commit()


def _status(fabrik) -> dict[str, set[BuchungStatus]]:  # noqa: ANN001
    with fabrik() as s:
        buchungen = lade_buchungen(s)
    status: dict[str, set[BuchungStatus]] = {"mit": set(), "ohne": set()}
    for b in buchungen:
        status["mit" if b.beleg_id else "ohne"].add(b.status)
    return status


@pytest.mark.parametrize(("schwelle", "confidence", "erwartet"), FAELLE)
def test_mit_und_ohne_beleg_dieselbe_schwelle(fabrik, schwelle, confidence, erwartet):
    """Im selben Lauf: Umsatz mit und ohne Beleg, dieselbe Regel — derselbe Status."""
    _mit_und_ohne_beleg(fabrik)
    engine = KlassifikationsEngine(
        regelwerk=RegelwerkEngine([_tanken(confidence)]),
        auto_buchen_schwelle=schwelle,
    )
    with fabrik() as s:
        lauf = kontiere_umsaetze(s, engine, Buchhaltung())
        s.commit()
    assert (lauf.kontiert, lauf.mit_beleg) == (2, 1)
    assert _status(fabrik) == {"mit": {erwartet}, "ohne": {erwartet}}


@pytest.mark.parametrize(("schwelle", "confidence", "erwartet"), FAELLE)
def test_sachkonto_fuer_beleg_nimmt_die_schwelle(schwelle, confidence, erwartet):
    from accounti.buchung.mit_beleg import kontiere_beleg, sachkonto_fuer_beleg

    werk = RegelwerkEngine([_tanken(confidence)])
    beleg = tankquittung()
    sk = sachkonto_fuer_beleg(
        beleg, None, Buchhaltung(), werk, umsatz(), auto_schwelle=schwelle
    )
    assert (sk.konto, sk.pruefen) == ("4530", erwartet is BuchungStatus.ZUR_PRUEFUNG)
    k = kontiere_beleg(umsatz(), beleg, Buchhaltung(), werk, auto_schwelle=schwelle)
    assert {b.status for b in k.buchungen} == {erwartet}
    # ohne Angabe der Standard 0,95 (AUTO_SCHWELLE) — wie bisher
    standard = sachkonto_fuer_beleg(beleg, None, Buchhaltung(), werk, umsatz())
    assert standard.pruefen is (confidence < 0.95)


# --- opos verbuchen -----------------------------------------------------------------


def _bekannter_lieferant(fabrik) -> None:  # noqa: ANN001
    """Geprüfter Kreditor ohne Sachkonto — das Konto liefert die Regel."""
    with fabrik() as s:
        speichere_kontakt(
            s,
            Kontakt(
                name="Bürobedarf Müller GmbH",
                ust_id="DE123456789",
                iban="DE89370400440532013000",
                kreditor_konto="70000",
                status=KontaktStatus.GEPRUEFT,
            ),
        )
        speichere_beleg(s, eingangsrechnung())
        s.commit()


def _buero(confidence: float) -> Regel:
    return Regel(
        "buero",
        r"b(ü|ue)robedarf",
        "4930",
        "1200",
        9,
        "Bürobedarf",
        feld="beide",
        confidence=confidence,
    )


@pytest.mark.parametrize(("schwelle", "confidence", "erwartet"), FAELLE)
def test_opos_verbuchen_nimmt_die_schwelle(fabrik, schwelle, confidence, erwartet):
    _bekannter_lieferant(fabrik)
    with fabrik() as s:
        lauf = verbuche_belege(
            s,
            Buchhaltung(),
            regelwerk=RegelwerkEngine([_buero(confidence)]),
            auto_schwelle=schwelle,
        )
        s.commit()
    assert lauf.fehler == []
    with fabrik() as s:
        buchungen = lade_buchungen(s)
    assert {b.soll_konto for b in buchungen} == {"4930"}
    assert {b.status for b in buchungen} == {erwartet}


def _cli_umgebung(tmp_path: Path, monkeypatch, schwelle: str, regel: str) -> Path:  # noqa: ANN001
    monkeypatch.chdir(tmp_path)
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_KONFIG"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "regeln.yaml").write_text(regel, encoding="utf-8")
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        f"llm:\n  auto_buchen_schwelle: {schwelle}\n  pruefung_schwelle: 0.5\n",
        encoding="utf-8",
    )
    return konfig


BUERO_097 = (
    "- name: buero\n  muster: 'b(ü|ue)robedarf'\n  feld: beide\n"
    "  soll_konto: '4930'\n  haben_konto: '1200'\n  steuer_schluessel: 9\n"
    "  confidence: 0.97\n"
)


def test_cli_opos_verbuchen_nimmt_die_schwelle_der_konfiguration(
    fabrik, tmp_path, monkeypatch
):
    """``opos verbuchen`` liest ``llm.auto_buchen_schwelle`` wie classify: Schwelle
    0,99, Regel 0,97 — zur Prüfung (bisher fest 0,95: automatisch gebucht)."""
    konfig = _cli_umgebung(tmp_path, monkeypatch, "0.99", BUERO_097)
    _bekannter_lieferant(fabrik)
    r = runner.invoke(
        app,
        [
            "opos", "verbuchen", "--db", db_url(tmp_path), "--config", str(konfig),
            "--archiv", str(tmp_path / "archiv"),
        ],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    with fabrik() as s:
        buchungen = lade_buchungen(s)
    assert buchungen and {b.status for b in buchungen} == {BuchungStatus.ZUR_PRUEFUNG}


def test_cli_opos_verbuchen_haelt_bei_fehlerhaftem_llm_abschnitt(
    fabrik, tmp_path, monkeypatch
):
    """Wie classify und bank lauf: Ist der Abschnitt ``llm`` ungültig, ist die Schwelle
    unbekannt — ``opos verbuchen`` bucht nichts und endet mit Exit 1."""
    konfig = _cli_umgebung(tmp_path, monkeypatch, "0.99", BUERO_097)
    konfig.write_text(
        "llm:\n  auto_buchen_schwelle: 0.6\n  pruefung_schwelle: 0.7\n", "utf-8"
    )
    _bekannter_lieferant(fabrik)
    r = runner.invoke(
        app,
        [
            "opos", "verbuchen", "--db", db_url(tmp_path), "--config", str(konfig),
            "--archiv", str(tmp_path / "archiv"),
        ],
    )  # fmt: skip
    assert r.exit_code == 1, r.output
    assert "pruefung_schwelle" in r.output
    with fabrik() as s:
        assert lade_buchungen(s) == []


# --- Verfahrensdokumentation -------------------------------------------------------


@pytest.mark.parametrize(
    ("schwelle", "confidence", "pruefen"),
    [("0.99", "0.97", "ja"), ("0.8", "0.94", "nein")],
)
def test_verfahrensdoku_nennt_die_eine_schwelle(
    fabrik, tmp_path, monkeypatch, schwelle, confidence, pruefen
):
    """GoBD-Dokument: die Schwelle gilt für Umsätze, Belegbuchungen und opos verbuchen;
    die Spalte „Prüfen“ der eigenen Regeln stimmt damit für jeden Weg."""
    from accounti.pruefung.verfahrensdoku import erzeuge

    konfig = _cli_umgebung(
        tmp_path,
        monkeypatch,
        schwelle,
        BUERO_097.replace("0.97", confidence),
    )
    with fabrik() as s:
        text = erzeuge(s, konfig, db_url=db_url(tmp_path))
    assert (
        f"**Automatisch gebucht** (Status auto) wird ab Confidence {schwelle}" in text
    )
    assert (
        "Dieselbe Schwelle gilt für das Sachkonto aus einer Regel bei der Buchung aus "
        "dem Beleg (classify, bank lauf) und bei accounti opos verbuchen" in text
    )
    (zeile,) = [z for z in text.splitlines() if z.startswith("| buero |")]
    assert zeile.endswith(f"| {pruefen} |")


def test_kein_fester_vergleich_mehr():
    """Strukturtest: ``AUTO_SCHWELLE`` ist nur noch Standardwert eines Parameters —
    kein Modul vergleicht eine Confidence fest mit ihr."""
    import re

    quellen = Path(__file__).resolve().parents[1] / "src" / "accounti"
    vergleich = re.compile(r"[<>]=?\s*AUTO_SCHWELLE|AUTO_SCHWELLE\s*[<>]")
    treffer = [
        f"{p.relative_to(quellen)}:{n}"
        for p in sorted(quellen.rglob("*.py"))
        for n, zeile in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if vergleich.search(zeile)
    ]
    assert treffer == []
