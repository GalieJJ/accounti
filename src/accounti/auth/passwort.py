"""Passwort-Hash mit ``hashlib.scrypt`` und Passwortregeln.

Parameter nach dem OWASP Password Storage Cheat Sheet (Stand 20.10.2026): scrypt
mit N = 2^17 (128 MiB), r = 8, p = 1, Salz je Passwort. Die Parameter stehen im
gespeicherten Hash (``scrypt$<log2 N>$<r>$<p>$<salz>$<hash>``) — so lassen sie
sich später anheben, ohne alte Hashes ungültig zu machen.

Regeln nach NIST SP 800-63B-4: Länge statt Zusammensetzung, Abgleich mit einer
Sperrliste. Die Liste hier ist klein; eine vollständige Liste kompromittierter
Passwörter bräuchte einen externen Dienst.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
from dataclasses import dataclass

_PRAEFIX = "scrypt"
_SALZ_BYTES = 16
_HASH_BYTES = 32
MAX_LAENGE = 128


@dataclass(frozen=True)
class Kosten:
    log_n: int
    r: int
    p: int

    @property
    def speicher(self) -> int:
        """Bytes, die scrypt braucht (128 · r · N), plus Spielraum."""
        n: int = 2**self.log_n
        return 128 * self.r * n * (self.p + 1) + 2**20


STANDARD_KOSTEN = Kosten(log_n=17, r=8, p=1)
# geltende Kosten; Tests setzen sie herab, damit nicht jeder Hash 128 MiB braucht
KOSTEN = STANDARD_KOSTEN

# häufige Passwörter und Muster — ganze Zeichenfolge, klein geschrieben
SPERRLISTE = frozenset(
    {
        "passwort1234",
        "password1234",
        "passwort12345",
        "password12345",
        "123456789012",
        "1234567890123",
        "qwertzuiopü",
        "qwertyuiop12",
        "accounti1234",
        "buchhaltung1",
        "buchhaltung123",
        "willkommen123",
        "hallo1234567",
        "sommer2026!!",
        "winter2026!!",
        "letmein12345",
        "admin1234567",
        "administrator",
    }
)


class PasswortRegelError(ValueError):
    """Das Passwort erfüllt die Regeln nicht."""


def _b64(daten: bytes) -> str:
    return base64.b64encode(daten).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text + "=" * (-len(text) % 4), validate=True)


def _scrypt(passwort: str, salz: bytes, kosten: Kosten) -> bytes:
    return hashlib.scrypt(
        passwort.encode("utf-8"),
        salt=salz,
        n=2**kosten.log_n,
        r=kosten.r,
        p=kosten.p,
        maxmem=kosten.speicher,
        dklen=_HASH_BYTES,
    )


def hash_passwort(passwort: str, kosten: Kosten | None = None) -> str:
    kosten = kosten or KOSTEN
    salz = secrets.token_bytes(_SALZ_BYTES)
    wert = _scrypt(passwort, salz, kosten)
    return f"{_PRAEFIX}${kosten.log_n}${kosten.r}${kosten.p}${_b64(salz)}${_b64(wert)}"


def _lies(gespeichert: str) -> tuple[Kosten, bytes, bytes] | None:
    teile = gespeichert.split("$")
    if len(teile) != 6 or teile[0] != _PRAEFIX:
        return None
    try:
        kosten = Kosten(int(teile[1]), int(teile[2]), int(teile[3]))
        salz, wert = _unb64(teile[4]), _unb64(teile[5])
    except (ValueError, binascii.Error):
        return None
    # unsinnige Parameter würden scrypt minutenlang oder ohne Speicher laufen lassen
    if not (1 <= kosten.log_n <= 20 and 1 <= kosten.r <= 32 and 1 <= kosten.p <= 16):
        return None
    if len(salz) < 8 or len(wert) != _HASH_BYTES:
        return None
    return kosten, salz, wert


def pruefe_passwort(passwort: str, gespeichert: str) -> bool:
    """Passt das Passwort? Ein unlesbarer Hash ist nie ein Treffer."""
    gelesen = _lies(gespeichert)
    if gelesen is None or len(passwort) > MAX_LAENGE:
        return False
    kosten, salz, wert = gelesen
    return hmac.compare_digest(_scrypt(passwort, salz, kosten), wert)


def veraltet(gespeichert: str, kosten: Kosten | None = None) -> bool:
    """Schwächere Parameter als die aktuellen → bei der Anmeldung neu hashen."""
    kosten = kosten or KOSTEN
    gelesen = _lies(gespeichert)
    if gelesen is None:
        return True
    alt = gelesen[0]
    return (alt.log_n, alt.r, alt.p) < (kosten.log_n, kosten.r, kosten.p)


def pruefe_regeln(passwort: str, benutzername: str, mindestlaenge: int = 12) -> None:
    if len(passwort) < mindestlaenge:
        msg = f"Das Passwort braucht mindestens {mindestlaenge} Zeichen"
        raise PasswortRegelError(msg)
    if len(passwort) > MAX_LAENGE:
        msg = f"Das Passwort darf höchstens {MAX_LAENGE} Zeichen haben"
        raise PasswortRegelError(msg)
    klein = passwort.lower()
    if benutzername and benutzername.lower() in klein:
        raise PasswortRegelError("Das Passwort darf den Benutzernamen nicht enthalten")
    if klein in SPERRLISTE or len(set(klein)) <= 2:
        msg = "Das Passwort ist zu häufig oder zu einfach — bitte ein anderes"
        raise PasswortRegelError(msg)
