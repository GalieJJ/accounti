import pytest

from accounti.bank.tresor import (
    TresorError,
    entschluessele,
    lade_schluessel,
    neuer_schluessel,
    verschluessele,
)

ZUGANG = {"benutzer": "jan.muster", "pin": "geheim-4711"}


def test_hin_und_zurueck():
    schluessel = neuer_schluessel()
    chiffrat = verschluessele(ZUGANG, schluessel, "konto-1")
    assert chiffrat.startswith("v1:")
    assert "geheim-4711" not in chiffrat and "jan.muster" not in chiffrat
    assert entschluessele(chiffrat, schluessel, "konto-1") == ZUGANG


def test_jedes_mal_anders():
    schluessel = neuer_schluessel()
    assert verschluessele(ZUGANG, schluessel, "k") != verschluessele(
        ZUGANG, schluessel, "k"
    )


def test_falscher_schluessel():
    chiffrat = verschluessele(ZUGANG, neuer_schluessel(), "konto-1")
    with pytest.raises(TresorError, match="entschlüsselt"):
        entschluessele(chiffrat, neuer_schluessel(), "konto-1")


def test_fremdes_konto():
    schluessel = neuer_schluessel()
    chiffrat = verschluessele(ZUGANG, schluessel, "konto-1")
    with pytest.raises(TresorError):
        entschluessele(chiffrat, schluessel, "konto-2")


def test_manipuliert():
    schluessel = neuer_schluessel()
    chiffrat = verschluessele(ZUGANG, schluessel, "k")
    kaputt = chiffrat[:-4] + ("AAAA" if not chiffrat.endswith("AAAA") else "BBBB")
    with pytest.raises(TresorError):
        entschluessele(kaputt, schluessel, "k")
    with pytest.raises(TresorError, match="Format"):
        entschluessele("klartext", schluessel, "k")


def test_schluessel_aus_der_umgebung(monkeypatch):
    schluessel = neuer_schluessel()
    monkeypatch.setenv("ACCOUNTI_SCHLUESSEL", schluessel)
    assert lade_schluessel() == schluessel
    monkeypatch.delenv("ACCOUNTI_SCHLUESSEL")
    with pytest.raises(TresorError, match="ACCOUNTI_SCHLUESSEL"):
        lade_schluessel()
    monkeypatch.setenv("ACCOUNTI_SCHLUESSEL", "zu-kurz")
    with pytest.raises(TresorError, match="256"):
        lade_schluessel()
