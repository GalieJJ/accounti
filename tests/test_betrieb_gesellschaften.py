"""Registry der Gesellschaften (Abschnitt ``gesellschaften``, Spec 4.4)."""

import pytest

from accounti.betrieb.gesellschaften import lade_gesellschaften
from accounti.konfiguration import KonfigurationError

REGISTRY = """
gesellschaften:
  systemdatenbank: "sqlite:///system.db"
  standard: muster
  eintraege:
    muster:
      name: Muster GmbH
      datenbank: "sqlite:///muster.db"
      archiv: archiv/muster
      konfiguration: config/muster.yaml
    tochter:
      name: Tochter UG
      datenbank: "postgresql+psycopg://accounti:${PG_PASSWORT_TEST}@db/tochter"
      archiv: archiv/tochter
"""


def schreibe(tmp_path, text):
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(text, encoding="utf-8")
    return pfad


def test_ohne_abschnitt_leer(tmp_path):
    g = lade_gesellschaften(tmp_path / "fehlt.yaml")
    assert g.eintraege == {}
    assert not g.mehrere
    assert (
        lade_gesellschaften(schreibe(tmp_path, "mandant: {name: x}\n")).eintraege == {}
    )


def test_registry_lesen_und_variablen_spaet_ersetzen(tmp_path, monkeypatch):
    monkeypatch.delenv("PG_PASSWORT_TEST", raising=False)
    g = lade_gesellschaften(schreibe(tmp_path, REGISTRY))
    assert sorted(g.eintraege) == ["muster", "tochter"]
    assert g.mehrere
    muster = g.finde("muster")
    assert muster.kuerzel == "muster"
    assert muster.name == "Muster GmbH"
    assert muster.datenbank == "sqlite:///muster.db"
    assert muster.konfiguration == "config/muster.yaml"
    assert muster.regeln == "config/regeln.yaml"  # neben der Konfiguration
    # eine fehlende Variable betrifft nur die Gesellschaft, die sie braucht
    with pytest.raises(KonfigurationError, match="PG_PASSWORT_TEST"):
        g.finde("tochter")
    monkeypatch.setenv("PG_PASSWORT_TEST", "geheim")
    tochter = g.finde("tochter")
    assert tochter.datenbank.endswith(":geheim@db/tochter")
    assert tochter.konfiguration == str(tmp_path / "accounti.yaml")  # global
    assert g.system() == "sqlite:///system.db"
    assert g.standard == "muster"


def test_unbekannte_gesellschaft(tmp_path):
    g = lade_gesellschaften(schreibe(tmp_path, REGISTRY))
    with pytest.raises(KonfigurationError, match="muster, tochter"):
        g.finde("gibtsnicht")


@pytest.mark.parametrize(
    ("text", "meldung"),
    [
        (
            "gesellschaften:\n  eintraege:\n    a: {name: A, datenbank: x, archiv: y}\n"
            "    b: {name: B, datenbank: x2, archiv: y2}\n",
            "systemdatenbank",
        ),
        (
            "gesellschaften:\n  systemdatenbank: s\n  standard: c\n  eintraege:\n"
            "    a: {name: A, datenbank: x, archiv: y}\n",
            "standard",
        ),
        (
            "gesellschaften:\n  systemdatenbank: s\n  eintraege:\n"
            "    'Groß Firma': {name: A, datenbank: x, archiv: y}\n",
            "Kürzel",
        ),
        (
            "gesellschaften:\n  systemdatenbank: s\n  eintraege:\n"
            "    a: {name: A, datenbank: x, archiv: y}\n"
            "    b: {name: B, datenbank: x, archiv: y2}\n",
            "dieselbe Datenbank",
        ),
        (
            "gesellschaften:\n  systemdatenbank: s\n  eintraege:\n"
            "    a: {name: A, datenbank: x, archiv: y}\n"
            "    b: {name: B, datenbank: x2, archiv: y}\n",
            "dasselbe Archiv",
        ),
        ("gesellschaften: [1, 2]\n", "Zuordnung"),
    ],
)
def test_fehler_in_der_registry(tmp_path, text, meldung):
    with pytest.raises(KonfigurationError, match=meldung):
        lade_gesellschaften(schreibe(tmp_path, text))


def test_eine_gesellschaft_ist_von_selbst_standard(tmp_path):
    g = lade_gesellschaften(
        schreibe(
            tmp_path,
            "gesellschaften:\n  eintraege:\n"
            "    a: {name: A, datenbank: x, archiv: y}\n",
        )
    )
    assert g.standard == "a"
    # ohne Systemdatenbank liegen die Benutzer in der Datenbank der Gesellschaft
    assert g.system() == "x"
