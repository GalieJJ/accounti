"""Tresor für Bankzugänge — AES-GCM, Schlüssel aus der Umgebung.

Zugangsdaten (PIN, Benutzerkennung, Tokens) stehen nie im Klartext in der Datenbank
und nie in Logs. Das Chiffrat ist an das Konto gebunden (zusätzliche
authentifizierte Angabe): Es lässt sich keinem anderen Konto unterschieben.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

UMGEBUNG = "ACCOUNTI_SCHLUESSEL"
_VERSION = "v1:"


class TresorError(RuntimeError):
    """Schlüssel fehlt oder das Chiffrat passt nicht."""


def neuer_schluessel() -> str:
    """256-Bit-Schlüssel, Base64 (URL-sicher) — gehört in ACCOUNTI_SCHLUESSEL."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


_UNGUELTIG = (
    f"{UMGEBUNG} ist kein gültiger 256-Bit-Schlüssel (Base64) — "
    "mit 'accounti bank schluessel' erzeugen"
)


def _roh(schluessel: str) -> bytes:
    try:
        roh = base64.urlsafe_b64decode(schluessel.encode())
    except (binascii.Error, ValueError) as fehler:
        raise TresorError(_UNGUELTIG) from fehler
    if len(roh) != 32:
        raise TresorError(_UNGUELTIG)
    return roh


def lade_schluessel() -> str:
    schluessel = os.environ.get(UMGEBUNG)
    if not schluessel:
        msg = (
            f"Umgebungsvariable {UMGEBUNG} fehlt — Bankzugänge werden nur "
            "verschlüsselt gespeichert; einen Schlüssel erzeugt "
            "'accounti bank schluessel'"
        )
        raise TresorError(msg)
    _roh(schluessel)
    return schluessel


def verschluessele(daten: dict[str, str], schluessel: str, bezug: str) -> str:
    nonce = secrets.token_bytes(12)
    klartext = json.dumps(daten, ensure_ascii=False).encode()
    chiffrat = AESGCM(_roh(schluessel)).encrypt(nonce, klartext, bezug.encode())
    return _VERSION + base64.urlsafe_b64encode(nonce + chiffrat).decode()


def entschluessele(text: str, schluessel: str, bezug: str) -> dict[str, str]:
    if not text.startswith(_VERSION):
        raise TresorError("Unbekanntes Format des Zugangs (erwartet v1:)")
    try:
        roh = base64.urlsafe_b64decode(text[len(_VERSION) :].encode())
        klartext = AESGCM(_roh(schluessel)).decrypt(roh[:12], roh[12:], bezug.encode())
    except (InvalidTag, binascii.Error, ValueError) as fehler:
        msg = "Zugang konnte nicht entschlüsselt werden (falscher Schlüssel oder Konto)"
        raise TresorError(msg) from fehler
    daten = json.loads(klartext)
    return {str(k): str(v) for k, v in daten.items()}
