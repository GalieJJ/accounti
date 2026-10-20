"""Zeitbasierte Einmalcodes nach RFC 6238 (TOTP) — mit ``hmac`` der Standardbibliothek.

T = ⌊(Unixzeit − T0) / X⌋ mit T0 = 0 und X = 30 s; der Code ist HOTP (RFC 4226)
über den Zähler T. Authenticator-Apps können fast nur HMAC-SHA-1 mit 6 Stellen —
das ist der Standard hier; SHA-256/512 gibt es für die Prüfwerte aus Anhang B.

``finde_schritt`` liefert den Zeitschritt des Treffers; dass jeder Schritt nur
einmal angenommen wird (RFC 6238 5.2), sichert der Aufrufer über den zuletzt
angenommenen Schritt am Benutzer (``repo_auth.merke_totp_schritt``).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote, urlencode

SCHRITT_SEKUNDEN = 30
STELLEN = 6
_ALGORITHMEN = {
    "sha1": hashlib.sha1,
    "sha256": hashlib.sha256,
    "sha512": hashlib.sha512,
}


def neues_geheimnis() -> bytes:
    """20 Byte Zufall — so lang wie die HMAC-SHA-1-Ausgabe (RFC 6238 5.1)."""
    return secrets.token_bytes(20)


def base32(geheimnis: bytes) -> str:
    return base64.b32encode(geheimnis).decode().rstrip("=")


def geheimnis_aus_base32(text: str) -> bytes:
    rein = "".join(text.split()).upper()
    try:
        return base64.b32decode(rein + "=" * (-len(rein) % 8))
    except (binascii.Error, ValueError) as fehler:
        raise ValueError("Kein gültiges Base32-Geheimnis") from fehler


def zeitschritt(zeit: float, schritt: int = SCHRITT_SEKUNDEN) -> int:
    return int(zeit // schritt)


def _hotp(geheimnis: bytes, zaehler: int, stellen: int, algorithmus: str) -> str:
    digest = hmac.new(
        geheimnis, struct.pack(">Q", zaehler), _ALGORITHMEN[algorithmus]
    ).digest()
    versatz = digest[-1] & 0x0F
    wert = struct.unpack(">I", digest[versatz : versatz + 4])[0] & 0x7FFFFFFF
    return str(wert % 10**stellen).zfill(stellen)


def code(
    geheimnis: bytes,
    zeit: float,
    stellen: int = STELLEN,
    schritt: int = SCHRITT_SEKUNDEN,
    algorithmus: str = "sha1",
) -> str:
    return _hotp(geheimnis, zeitschritt(zeit, schritt), stellen, algorithmus)


def finde_schritt(
    geheimnis: bytes,
    eingabe: str,
    zeit: float,
    toleranz: int = 1,
    stellen: int = STELLEN,
) -> int | None:
    """Zeitschritt, zu dem die Eingabe passt — höchstens ``toleranz`` Schritte
    neben der aktuellen Zeit (Uhrenabweichung, Netzverzögerung)."""
    rein = "".join(eingabe.split())
    if len(rein) != stellen or not rein.isascii() or not rein.isdigit():
        return None
    aktuell = zeitschritt(zeit)
    treffer: int | None = None
    # alle Kandidaten vergleichen, damit die Laufzeit nichts über den Treffer verrät
    for versatz in range(-toleranz, toleranz + 1):
        schritt = aktuell + versatz
        erwartet = _hotp(geheimnis, schritt, stellen, "sha1")
        if hmac.compare_digest(erwartet, rein) and treffer is None:
            treffer = schritt
    return treffer


def otpauth_uri(geheimnis: bytes, konto: str, aussteller: str = "accounti") -> str:
    """Schlüssel-URI für Authenticator-Apps (als QR-Code oder zum Abtippen)."""
    bezeichnung = quote(f"{aussteller}:{konto}", safe=":@")
    abfrage = urlencode(
        {
            "secret": base32(geheimnis),
            "issuer": aussteller,
            "algorithm": "SHA1",
            "digits": STELLEN,
            "period": SCHRITT_SEKUNDEN,
        },
        quote_via=quote,
    )
    return f"otpauth://totp/{bezeichnung}?{abfrage}"
