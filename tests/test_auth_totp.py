"""TOTP nach RFC 6238 — gegen die Prüfwerte aus Anhang B."""

import base64
from urllib.parse import parse_qs, urlsplit

import pytest

from accounti.auth.totp import (
    base32,
    code,
    finde_schritt,
    geheimnis_aus_base32,
    neues_geheimnis,
    otpauth_uri,
    zeitschritt,
)

SHA1 = b"12345678901234567890"
SHA256 = b"12345678901234567890123456789012"
SHA512 = b"1234567890" * 6 + b"1234"

# RFC 6238, Anhang B (8 Stellen)
PRUEFWERTE = [
    (59, "94287082", "46119246", "90693936"),
    (1111111109, "07081804", "68084774", "25091201"),
    (1111111111, "14050471", "67062674", "99943326"),
    (1234567890, "89005924", "91819424", "93441116"),
    (2000000000, "69279037", "90698825", "38618901"),
    (20000000000, "65353130", "77737706", "47863826"),
]


@pytest.mark.parametrize(("zeit", "sha1", "sha256", "sha512"), PRUEFWERTE)
def test_rfc6238_anhang_b(zeit, sha1, sha256, sha512):
    assert code(SHA1, zeit, stellen=8) == sha1
    assert code(SHA256, zeit, stellen=8, algorithmus="sha256") == sha256
    assert code(SHA512, zeit, stellen=8, algorithmus="sha512") == sha512


def test_zeitschritt():
    assert zeitschritt(59) == 1
    assert zeitschritt(60) == 2
    assert zeitschritt(1111111109) == 0x23523EC


def test_geheimnis_hat_die_laenge_der_hmac_ausgabe():
    g = neues_geheimnis()
    assert len(g) == 20  # SHA-1: 160 Bit (RFC 6238 5.1)
    assert neues_geheimnis() != g
    assert geheimnis_aus_base32(base32(g)) == g
    assert "=" not in base32(g)
    assert geheimnis_aus_base32(base32(g).lower().replace("", " ").strip()) == g


def test_toleranz_ein_schritt():
    jetzt = 1_800_000_000
    aktuell = code(SHA1, jetzt)
    assert finde_schritt(SHA1, aktuell, jetzt) == zeitschritt(jetzt)
    vorher = code(SHA1, jetzt - 30)
    assert finde_schritt(SHA1, vorher, jetzt) == zeitschritt(jetzt) - 1
    nachher = code(SHA1, jetzt + 30)
    assert finde_schritt(SHA1, nachher, jetzt) == zeitschritt(jetzt) + 1
    zu_alt = code(SHA1, jetzt - 60)
    assert finde_schritt(SHA1, zu_alt, jetzt) is None
    assert finde_schritt(SHA1, zu_alt, jetzt, toleranz=2) == zeitschritt(jetzt) - 2


def test_eingabe_wird_bereinigt_und_geprueft():
    jetzt = 1_800_000_000
    c = code(SHA1, jetzt)
    assert finde_schritt(SHA1, f"{c[:3]} {c[3:]}", jetzt) is not None
    for falsch in ("", "12345", "1234567", "abcdef", "١٢٣٤٥٦"):
        assert finde_schritt(SHA1, falsch, jetzt) is None


def test_otpauth_uri():
    uri = otpauth_uri(SHA1, "jan", aussteller="accounti Muster GmbH")
    teile = urlsplit(uri)
    assert teile.scheme == "otpauth"
    assert teile.netloc == "totp"
    assert teile.path == "/accounti%20Muster%20GmbH:jan"
    werte = parse_qs(teile.query)
    assert werte["secret"] == [base64.b32encode(SHA1).decode().rstrip("=")]
    assert werte["issuer"] == ["accounti Muster GmbH"]
    assert werte["digits"] == ["6"]
    assert werte["period"] == ["30"]
    assert werte["algorithm"] == ["SHA1"]
