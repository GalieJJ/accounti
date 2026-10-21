"""Passwort-Hash mit scrypt und Passwortregeln."""

import pytest

from accounti.auth import passwort
from accounti.auth.passwort import (
    STANDARD_KOSTEN,
    Kosten,
    PasswortRegelError,
    hash_passwort,
    pruefe_passwort,
    pruefe_regeln,
    veraltet,
)

BILLIG = Kosten(log_n=10, r=8, p=1)


def test_standard_folgt_owasp():
    # OWASP Password Storage: scrypt N=2^17, r=8, p=1
    assert Kosten(log_n=17, r=8, p=1) == STANDARD_KOSTEN


def test_hash_und_pruefung():
    h = hash_passwort("richtig langes Passwort", BILLIG)
    assert h.startswith("scrypt$10$8$1$")
    assert "richtig" not in h
    assert pruefe_passwort("richtig langes Passwort", h)
    assert not pruefe_passwort("richtig langes passwort", h)
    assert not pruefe_passwort("", h)


def test_salz_macht_jeden_hash_anders():
    assert hash_passwort("gleich gleich", BILLIG) != hash_passwort(
        "gleich gleich", BILLIG
    )


def test_standardkosten_wirklich_genutzt(monkeypatch):
    monkeypatch.setattr(passwort, "KOSTEN", STANDARD_KOSTEN)
    h = hash_passwort("ein Passwort mit Standardkosten")
    assert h.startswith("scrypt$17$8$1$")
    assert pruefe_passwort("ein Passwort mit Standardkosten", h)


def test_kaputter_hash_ist_kein_treffer():
    for kaputt in ("", "scrypt$", "md5$abc", "scrypt$99$8$1$aa$bb", "scrypt$x$8$1$a$b"):
        assert not pruefe_passwort("egal", kaputt)


def test_veraltete_parameter_werden_erkannt():
    assert veraltet(hash_passwort("x" * 12, BILLIG), STANDARD_KOSTEN)
    assert not veraltet(hash_passwort("x" * 12, BILLIG), BILLIG)
    assert veraltet("kaputt")


def test_regeln():
    pruefe_regeln("ein langer satz als passwort", "jan")
    with pytest.raises(PasswortRegelError, match="mindestens 12"):
        pruefe_regeln("kurz", "jan")
    with pytest.raises(PasswortRegelError, match="höchstens 128"):
        pruefe_regeln("x" * 129, "jan")
    with pytest.raises(PasswortRegelError, match="Benutzernamen"):
        pruefe_regeln("jan.mueller-1234", "jan.mueller")
    with pytest.raises(PasswortRegelError, match="zu häufig"):
        pruefe_regeln("passwort1234", "jan")
    with pytest.raises(PasswortRegelError, match="zu häufig"):
        pruefe_regeln("aaaaaaaaaaaa", "jan")
    # keine Zusammensetzungsregeln (NIST 800-63B-4)
    pruefe_regeln("nurkleinbuchstabenundlang", "jan")
    pruefe_regeln("ein langer satz", "jan", mindestlaenge=8)


def test_eingebaute_sperrliste_ist_klein_geschrieben():
    assert all(w == w.lower() for w in passwort.SPERRLISTE)
