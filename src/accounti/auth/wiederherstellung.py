"""Wiederherstellungscodes — für den Fall, dass das Gerät mit der App fehlt.

Zehn Codes ``XXXXX-XXXXX`` aus einem Alphabet ohne verwechselbare Zeichen
(0/O, 1/I/L): je Code etwa 50 Bit. NIST SP 800-63B-4 verlangt für
Nachschlage-Geheimnisse unter 112 Bit einen gesalzenen Passwort-Hash; scrypt mit
N = 2^14 hält die Prüfung aller offenen Codes unter einer Sekunde. Jeder Code gilt
genau einmal.
"""

from __future__ import annotations

import secrets

from accounti.auth.passwort import Kosten, hash_passwort, pruefe_passwort

ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
LAENGE = 10
ANZAHL = 10
KOSTEN = Kosten(log_n=14, r=8, p=1)


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


def hash_code(code: str) -> str:
    rein = normalisiere(code)
    if rein is None:
        raise ValueError("Kein Wiederherstellungscode")
    return hash_passwort(rein, KOSTEN)


def passt(eingabe: str, code_hash: str) -> bool:
    rein = normalisiere(eingabe)
    return rein is not None and pruefe_passwort(rein, code_hash)
