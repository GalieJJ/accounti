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


# ---------------------------------------------------------------------------
# Befund B-M3: Trennung nach dem Ersetzen und auf normalisierten Werten
# ---------------------------------------------------------------------------

ZWEI = """
gesellschaften:
  systemdatenbank: "sqlite:///system.db"
  eintraege:
    a:
      name: A
      datenbank: {db_a}
      archiv: {archiv_a}
      konfiguration: {konfig_a}
      regeln: {regeln_a}
    b:
      name: B
      datenbank: {db_b}
      archiv: {archiv_b}
      konfiguration: {konfig_b}
      regeln: {regeln_b}
"""

GETRENNT = {
    "db_a": "sqlite:///a.db",
    "db_b": "sqlite:///b.db",
    "archiv_a": "archiv/a",
    "archiv_b": "archiv/b",
    "konfig_a": "config/a.yaml",
    "konfig_b": "config/b.yaml",
    "regeln_a": "config/a-regeln.yaml",
    "regeln_b": "config/b-regeln.yaml",
}


@pytest.mark.parametrize(
    ("abweichung", "meldung"),
    [
        ({"db_a": "'${PROBE_DB_A}'", "db_b": "'${PROBE_DB_B}'"}, "dieselbe Datenbank"),
        ({"db_b": "sqlite:///./a.db"}, "dieselbe Datenbank"),
        (
            {
                "db_a": "postgresql+psycopg://x:geheim@DB:5432/acc",
                "db_b": "postgresql://y@db/acc",
            },
            "dieselbe Datenbank",
        ),
        ({"archiv_b": "./archiv/a"}, "dasselbe Archiv"),
        ({"archiv_b": "archiv/x/../a"}, "dasselbe Archiv"),
        ({"konfig_b": "./config/a.yaml"}, "dieselbe Konfiguration"),
        ({"konfig_a": "null", "konfig_b": "null"}, "dieselbe Konfiguration"),
        ({"regeln_b": "config/a-regeln.yaml"}, "dieselbe Regeldatei"),
        (
            {"regeln_a": "null", "regeln_b": "null"},  # regeln.yaml im selben Ordner
            "dieselbe Regeldatei",
        ),
    ],
)
def test_trennung_nach_ersetzen_und_normalisieren(
    tmp_path, monkeypatch, abweichung, meldung
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PROBE_DB_A", "sqlite:///gemeinsam.db")
    monkeypatch.setenv("PROBE_DB_B", "sqlite:///gemeinsam.db")
    werte = {**GETRENNT, **abweichung}
    with pytest.raises(KonfigurationError, match=meldung):
        lade_gesellschaften(schreibe(tmp_path, ZWEI.format(**werte)))


def test_getrennte_registry_wird_angenommen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    g = lade_gesellschaften(schreibe(tmp_path, ZWEI.format(**GETRENNT)))
    assert sorted(g.eintraege) == ["a", "b"]
    # höchstens eine Gesellschaft darf die globale Konfiguration nutzen
    werte = {**GETRENNT, "konfig_a": "null", "regeln_a": "null"}
    assert lade_gesellschaften(schreibe(tmp_path, ZWEI.format(**werte))).mehrere


def test_yaml_fehler_wird_zum_konfigurationsfehler(tmp_path):
    """Befund B-M8: ein Syntaxfehler ist ein KonfigurationError, kein Absturz."""
    with pytest.raises(KonfigurationError, match="kein gültiges YAML"):
        lade_gesellschaften(schreibe(tmp_path, "gesellschaften:\n  eintraege: [\n"))
