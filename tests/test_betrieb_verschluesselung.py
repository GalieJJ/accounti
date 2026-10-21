"""Verschlüsselter Strom der Sicherung: AES-256-GCM in Stücken."""

import io
import secrets

import pytest

from accounti.bank.tresor import neuer_schluessel
from accounti.betrieb.verschluesselung import (
    EntschluesselnderLeser,
    ManipuliertError,
    SicherungsschluesselError,
    VerschluesselnderSchreiber,
    lade_sicherungsschluessel,
    roher_schluessel,
)

SCHLUESSEL = secrets.token_bytes(32)
KOPF = 51  # 7 + 1 + 32 + 4 + 7


def verschluessele(daten: bytes, stueck: int = 1024, schluessel=SCHLUESSEL) -> bytes:
    ziel = io.BytesIO()
    w = VerschluesselnderSchreiber(ziel, schluessel, stueck)
    for i in range(0, len(daten), 333):
        w.write(daten[i : i + 333])
    w.close()
    return ziel.getvalue()


def entschluessele(chiffrat: bytes, schluessel=SCHLUESSEL) -> bytes:
    leser = EntschluesselnderLeser(io.BytesIO(chiffrat), schluessel)
    teile = []
    while True:
        teil = leser.read(500)
        if not teil:
            break
        teile.append(teil)
    leser.lies_bis_zum_ende()
    return b"".join(teile)


@pytest.mark.parametrize("laenge", [0, 1, 1023, 1024, 1025, 5000])
def test_hin_und_zurueck(laenge):
    daten = secrets.token_bytes(laenge)
    chiffrat = verschluessele(daten)
    assert entschluessele(chiffrat) == daten
    assert daten[:16] not in chiffrat or laenge < 16


def test_gleicher_inhalt_ergibt_andere_datei():
    assert verschluessele(b"x" * 100) != verschluessele(b"x" * 100)


def test_falscher_schluessel():
    chiffrat = verschluessele(b"geheime buchungen" * 100)
    with pytest.raises(SicherungsschluesselError):
        entschluessele(chiffrat, secrets.token_bytes(32))


def test_veraendert():
    chiffrat = bytearray(verschluessele(secrets.token_bytes(3000)))
    chiffrat[KOPF + 1040 + 5] ^= 1  # im zweiten Stück
    with pytest.raises(ManipuliertError):
        entschluessele(bytes(chiffrat))


def test_abgeschnitten_an_der_stueckgrenze():
    chiffrat = verschluessele(secrets.token_bytes(3000))
    ohne_ende = chiffrat[: KOPF + 2 * (1024 + 16)]
    with pytest.raises(ManipuliertError):
        entschluessele(ohne_ende)


def test_stuecke_vertauscht():
    chiffrat = verschluessele(secrets.token_bytes(4000))
    kopf, rest = chiffrat[:KOPF], chiffrat[KOPF:]
    s = 1024 + 16
    stuecke = [rest[i : i + s] for i in range(0, len(rest), s)]
    stuecke[0], stuecke[1] = stuecke[1], stuecke[0]
    with pytest.raises((ManipuliertError, SicherungsschluesselError)):
        entschluessele(kopf + b"".join(stuecke))


def test_kopf_geprueft():
    with pytest.raises(ManipuliertError, match="Keine accounti-Sicherung"):
        entschluessele(b"PK\x03\x04" + b"0" * 100)
    chiffrat = bytearray(verschluessele(b"abc"))
    chiffrat[7] = 9  # Version
    with pytest.raises(ManipuliertError, match="Version"):
        entschluessele(bytes(chiffrat))
    chiffrat = bytearray(verschluessele(b"abc"))
    chiffrat[20] ^= 1  # Salz — der Kopf ist zusätzliche Daten
    with pytest.raises(SicherungsschluesselError):
        entschluessele(bytes(chiffrat))


def test_schluessel_aus_der_umgebung(monkeypatch):
    monkeypatch.delenv("ACCOUNTI_SICHERUNG_SCHLUESSEL", raising=False)
    monkeypatch.delenv("ACCOUNTI_SCHLUESSEL", raising=False)
    with pytest.raises(SicherungsschluesselError, match="fehlt"):
        lade_sicherungsschluessel()
    ersatz = neuer_schluessel()
    monkeypatch.setenv("ACCOUNTI_SCHLUESSEL", ersatz)
    assert lade_sicherungsschluessel() == roher_schluessel(ersatz)
    eigen = neuer_schluessel()
    monkeypatch.setenv("ACCOUNTI_SICHERUNG_SCHLUESSEL", eigen)
    assert lade_sicherungsschluessel() == roher_schluessel(eigen)
    monkeypatch.setenv("ACCOUNTI_SICHERUNG_SCHLUESSEL", "zu-kurz")
    with pytest.raises(SicherungsschluesselError):
        lade_sicherungsschluessel()
