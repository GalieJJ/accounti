"""Wiederherstellungscodes — für den Fall, dass das Gerät mit der App fehlt.

Zehn Codes ``XXXXX-XXXXX`` aus einem Alphabet ohne verwechselbare Zeichen
(0/O, 1/I/L): je Code etwa 50 Bit. Gespeichert wird je Code ein HMAC-SHA-256 mit
einem Schlüssel aus dem Tresor (``ACCOUNTI_SCHLUESSEL``, „Pepper“) über
Benutzer-ID und Code — ohne den Schlüssel lässt sich aus der Datenbank allein kein
Code erraten. Geprüft wird mit **einem** Nachschlagen statt einer Passwort-Prüfung
je offenem Code: die Arbeit je Anmeldeversuch hängt nicht davon ab, ob das Passwort
stimmte (Befund A-M1, Antwortzeit als Seitenkanal). Jeder Code gilt genau einmal.

NIST SP 800-63B-4 verlangt für Nachschlage-Geheimnisse unter 112 Bit einen
gesalzenen Passwort-Hash gegen Offline-Angriffe. Hier schützt der Schlüssel: Wer ihn
hat, kann auch das TOTP-Geheimnis entschlüsseln (derselbe Tresor) — der zweite
Faktor ist dann ohnehin offen. Grenze in ``docs/betrieb.md``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from uuid import UUID

ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
LAENGE = 10
ANZAHL = 10
_PRAEFIX = "hmac-sha256$"
_ZWECK = b"accounti wiederherstellungscode v1"


def neue_codes(anzahl: int = ANZAHL) -> list[str]:
    codes = []
    for _ in range(anzahl):
        roh = "".join(secrets.choice(ALPHABET) for _ in range(LAENGE))
        codes.append(f"{roh[:5]}-{roh[5:]}")
    return codes


def normalisiere(eingabe: str) -> str | None:
    """Großbuchstaben ohne Leerzeichen und Bindestriche — oder ``None``."""
    rein = "".join(z for z in eingabe.upper() if z not in " -\t")
    if len(rein) != LAENGE or any(z not in ALPHABET for z in rein):
        return None
    return rein


def _schluessel(tresor: str) -> bytes:
    """Eigener Schlüssel für diesen Zweck, abgeleitet aus dem Tresor-Schlüssel."""
    return hmac.new(tresor.encode("utf-8"), _ZWECK, hashlib.sha256).digest()


def hash_code(code: str, tresor: str, benutzer_id: UUID) -> str:
    rein = normalisiere(code)
    if rein is None:
        raise ValueError("Kein Wiederherstellungscode")
    wert = hmac.new(
        _schluessel(tresor), f"{benutzer_id}:{rein}".encode(), hashlib.sha256
    ).hexdigest()
    return f"{_PRAEFIX}{wert}"


def passt(eingabe: str, code_hash: str, tresor: str, benutzer_id: UUID) -> bool:
    try:
        erwartet = hash_code(eingabe, tresor, benutzer_id)
    except ValueError:
        return False
    return hmac.compare_digest(erwartet, code_hash)
