"""Verschlüsselter Datenstrom für Sicherungen — AES-256-GCM in Stücken.

Aufbau (STREAM-Konstruktion nach Hoang/Reyhanitabar/Rogaway/Vizár)::

    Kopf:   "ACCSICH" · Version (1 Byte) · Salz (32) · Stückgröße (4) · Nonce-Präfix (7)
    Stücke: AES-GCM(Stück i) mit Nonce = Präfix · i (4 Byte) · Endmarke (1 Byte),
            zusätzliche Daten = Kopf; das letzte Stück trägt die Endmarke 1.

Der Schlüssel jeder Sicherung wird mit HKDF-SHA-256 aus dem Hauptschlüssel und dem
Zufallssalz abgeleitet — gleiche Nonces in zwei Sicherungen schaden so nicht.
Vertauschte, fehlende oder veränderte Stücke und ein abgeschnittenes Ende fallen
beim Lesen auf (``SicherungsschluesselError`` bzw. ``ManipuliertError``).

Hauptschlüssel aus ``ACCOUNTI_SICHERUNG_SCHLUESSEL``, sonst ``ACCOUNTI_SCHLUESSEL``
(256 Bit, Base64 wie der Tresor; erzeugen mit ``accounti sicherung schluessel``).
"""

from __future__ import annotations

import base64
import binascii
import os
import secrets
import struct
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIE = b"ACCSICH"
VERSION = 1
STUECK = 1024 * 1024
_TAG = 16
_KOPF = struct.Struct(">7sB32sI7s")
UMGEBUNG = "ACCOUNTI_SICHERUNG_SCHLUESSEL"
UMGEBUNG_ERSATZ = "ACCOUNTI_SCHLUESSEL"


class SicherungsschluesselError(RuntimeError):
    """Schlüssel fehlt, ist ungültig oder passt nicht zur Sicherung."""


class ManipuliertError(RuntimeError):
    """Die Datei ist keine accounti-Sicherung, abgeschnitten oder verändert."""


def lade_sicherungsschluessel() -> bytes:
    for name in (UMGEBUNG, UMGEBUNG_ERSATZ):
        wert = os.environ.get(name)
        if wert:
            return roher_schluessel(wert, name)
    msg = (
        f"{UMGEBUNG} (oder {UMGEBUNG_ERSATZ}) fehlt — Sicherungen werden nur "
        "verschlüsselt geschrieben; einen Schlüssel erzeugt 'accounti sicherung "
        "schluessel'. Den Schlüssel getrennt von der Sicherung aufbewahren."
    )
    raise SicherungsschluesselError(msg)


def roher_schluessel(text: str, name: str = UMGEBUNG) -> bytes:
    try:
        roh = base64.urlsafe_b64decode(text.encode())
    except (binascii.Error, ValueError) as fehler:
        raise SicherungsschluesselError(f"{name} ist kein Base64-Schlüssel") from fehler
    if len(roh) != 32:
        raise SicherungsschluesselError(f"{name} hat nicht 256 Bit")
    return roh


def _ableiten(hauptschluessel: bytes, salz: bytes) -> AESGCM:
    schluessel = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salz,
        info=b"accounti-sicherung v1",
    ).derive(hauptschluessel)
    return AESGCM(schluessel)


def _nonce(praefix: bytes, nr: int, letztes: bool) -> bytes:
    if nr >= 2**32:
        raise ManipuliertError("Zu viele Stücke")
    return praefix + struct.pack(">IB", nr, 1 if letztes else 0)


class VerschluesselnderSchreiber:
    """Dateiähnliches Ziel für ``tarfile`` (Modus ``w|``): schreibt Stück für Stück."""

    def __init__(
        self, ziel: BinaryIO, hauptschluessel: bytes, stueck: int = STUECK
    ) -> None:
        salz = secrets.token_bytes(32)
        self._praefix = secrets.token_bytes(7)
        self._kopf = _KOPF.pack(MAGIE, VERSION, salz, stueck, self._praefix)
        self._aead = _ableiten(hauptschluessel, salz)
        self._ziel = ziel
        self._stueck = stueck
        self._puffer = bytearray()
        self._nr = 0
        self._geschlossen = False
        ziel.write(self._kopf)

    def write(self, daten: bytes | bytearray | memoryview) -> int:
        if self._geschlossen:
            raise ValueError("Schreiber ist geschlossen")
        self._puffer += daten
        while len(self._puffer) > self._stueck:
            stueck = bytes(self._puffer[: self._stueck])
            del self._puffer[: self._stueck]
            self._schreibe(stueck, letztes=False)
        return len(daten)

    def _schreibe(self, stueck: bytes, letztes: bool) -> None:
        nonce = _nonce(self._praefix, self._nr, letztes)
        self._ziel.write(self._aead.encrypt(nonce, stueck, self._kopf))
        self._nr += 1

    def flush(self) -> None:
        """Nichts zu tun — Stücke werden erst voll oder beim Schließen geschrieben."""

    def close(self) -> None:
        if not self._geschlossen:
            self._schreibe(bytes(self._puffer), letztes=True)
            self._puffer.clear()
            self._geschlossen = True


class EntschluesselnderLeser:
    """Dateiähnliche Quelle für ``tarfile`` (Modus ``r|``)."""

    def __init__(self, quelle: BinaryIO, hauptschluessel: bytes) -> None:
        kopf = quelle.read(_KOPF.size)
        if len(kopf) != _KOPF.size:
            raise ManipuliertError("Keine accounti-Sicherung (Kopf zu kurz)")
        magie, version, salz, stueck, praefix = _KOPF.unpack(kopf)
        if magie != MAGIE:
            raise ManipuliertError("Keine accounti-Sicherung")
        if version != VERSION:
            raise ManipuliertError(f"Unbekannte Version {version} der Sicherung")
        if not 1024 <= stueck <= 64 * 1024 * 1024:
            raise ManipuliertError("Ungültige Stückgröße")
        self._kopf = kopf
        self._praefix = praefix
        self._aead = _ableiten(hauptschluessel, salz)
        self._quelle = quelle
        self._laenge = stueck + _TAG
        self._nr = 0
        self._puffer = bytearray()
        self._naechstes = quelle.read(self._laenge)
        self._ende = False
        self._erstes = True

    def _lies_stueck(self) -> None:
        aktuell = self._naechstes
        self._naechstes = self._quelle.read(self._laenge)
        letztes = not self._naechstes
        if len(aktuell) < _TAG:
            raise ManipuliertError("Sicherung abgeschnitten")
        try:
            klartext = self._aead.decrypt(
                _nonce(self._praefix, self._nr, letztes), aktuell, self._kopf
            )
        except InvalidTag as fehler:
            if self._erstes:
                msg = (
                    "Sicherung lässt sich nicht entschlüsseln — falscher Schlüssel "
                    "oder veränderte Datei"
                )
                raise SicherungsschluesselError(msg) from fehler
            msg = "Sicherung verändert, abgeschnitten oder Stücke vertauscht"
            raise ManipuliertError(msg) from fehler
        self._erstes = False
        self._nr += 1
        self._puffer += klartext
        self._ende = letztes

    def read(self, anzahl: int = -1) -> bytes:
        while not self._ende and (anzahl < 0 or len(self._puffer) < anzahl):
            self._lies_stueck()
        if anzahl < 0:
            anzahl = len(self._puffer)
        daten = bytes(self._puffer[:anzahl])
        del self._puffer[:anzahl]
        return daten

    def lies_bis_zum_ende(self) -> None:
        """Prüft auch die Stücke hinter dem Tar-Ende (Endmarke, Unversehrtheit)."""
        while not self._ende:
            self._lies_stueck()
        self._puffer.clear()
