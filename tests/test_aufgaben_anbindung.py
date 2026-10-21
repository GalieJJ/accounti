"""Anbindungen anderer Bausteine: Prüfläufe, Objekttypen und Kanäle aus einem Modul
``<paket>.<baustein>.aufgaben_anbindung`` werden gefunden, ohne dass jemand es
importiert."""

import sys
import textwrap
from datetime import date

import pytest

from accounti.aufgaben import anbindung
from accounti.aufgaben.benachrichtigung import KANAELE, baue_kanaele
from accounti.aufgaben.einstellungen import AufgabenEinstellungen
from accounti.aufgaben.objekte import OBJEKTTYPEN, beschreibe
from accounti.aufgaben.prueflaeufe import PRUEFLAEUFE, fuehre_prueflaeufe_aus
from accounti.db import init_db, session_factory
from accounti.models.aufgaben import Objekt

ANBINDUNG = """
from accounti.aufgaben import (
    KANAELE,
    Anlass,
    Objekt,
    Pruefergebnis,
    registriere_objekttyp,
    registriere_prueflauf,
)


class FristenLauf:
    name = "frist_probe"
    beschreibung = "Probefrist"
    grund_entfallen = "abgegeben"

    def finde(self, session, einstellungen, stichtag, zeitraum):
        return Pruefergebnis(
            [Anlass(Objekt("frist_probe", "ustva-2026-09"), titel="USt-VA 09/2026")]
        )


registriere_prueflauf(FristenLauf())
registriere_objekttyp(
    "frist_probe",
    "Frist",
    beschreibe=lambda session, ident: f"Frist {ident}",
    finde=lambda session, schluessel: [schluessel],
)
KANAELE["brieftaube_probe"] = lambda einstellungen, pfad: object()
"""


@pytest.fixture
def fremdpaket(tmp_path, monkeypatch):
    wurzel = tmp_path / "fremdpaket"
    for unter in ("", "steuer", "ohne"):
        (wurzel / unter).mkdir(parents=True, exist_ok=True)
        (wurzel / unter / "__init__.py").write_text("", encoding="utf-8")
    (wurzel / "steuer" / "aufgaben_anbindung.py").write_text(
        textwrap.dedent(ANBINDUNG), encoding="utf-8"
    )
    (wurzel / "einzeln.py").write_text("raise RuntimeError('nie laden')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(anbindung, "PAKETE", ["accounti", "fremdpaket"])
    yield
    PRUEFLAEUFE.pop("frist_probe", None)
    OBJEKTTYPEN.pop("frist_probe", None)
    KANAELE.pop("brieftaube_probe", None)
    anbindung.vergiss()
    for name in [n for n in sys.modules if n.startswith("fremdpaket")]:
        del sys.modules[name]


EIGENE = ["accounti.pruefung.aufgaben_anbindung"]  # Baustein 7: beleg_fehlt


def test_anbindungen_werden_gefunden(fremdpaket):
    erwartet = [*EIGENE, "fremdpaket.steuer.aufgaben_anbindung"]
    assert anbindung.lade_anbindungen() == erwartet
    assert "frist_probe" in PRUEFLAEUFE
    # ein zweiter Aufruf lädt nichts doppelt
    assert anbindung.lade_anbindungen() == erwartet


def test_pruefen_laedt_die_anbindungen_selbst(fremdpaket, tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'a.db'}")
    init_db(engine)
    try:
        with factory() as s:
            (lauf,) = fuehre_prueflaeufe_aus(
                s,
                AufgabenEinstellungen(),
                stichtag=date(2026, 10, 20),
                namen=["frist_probe"],
            )
            assert len(lauf.abgleich.neu) == 1
            objekt = Objekt("frist_probe", "ustva-2026-09")
            assert beschreibe(s, objekt) == "Frist ustva-2026-09"
    finally:
        engine.dispose()


def test_kanaele_laden_die_anbindungen_selbst(fremdpaket, tmp_path):
    e = AufgabenEinstellungen.model_validate(
        {"benachrichtigung": {"kanaele": ["brieftaube_probe"]}}
    )
    kanaele, fehler = baue_kanaele(e, tmp_path / "fehlt.yaml")
    assert set(kanaele) == {"brieftaube_probe"} and fehler == {}


def test_accounti_bringt_nur_die_anbindung_von_baustein_7():
    assert anbindung.lade_anbindungen() == EIGENE
