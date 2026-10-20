"""Webhook-Tokens — erzeugt mit 256 Bit Zufall, gespeichert nur als SHA-256.

Bei so viel Entropie ist ein schneller Hash ohne Salz ausreichend: Raten ist
aussichtslos, und aus dem Hash lässt sich das Token nicht zurückgewinnen. Der
Klartext wird genau einmal angezeigt — bei der Erzeugung.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from sqlalchemy.orm import Session

from accounti.belege.kanaele.einstellungen import NAME_MUSTER
from accounti.db.repo_kanaele import finde_webhook_token, speichere_webhook_token
from accounti.models.kanaele import WebhookToken

PRAEFIX = "accounti_wh_"
_MAX_LAENGE = 200


def neues_token() -> str:
    return PRAEFIX + secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def lege_token_an(session: Session, name: str) -> str:
    """Legt ein Token an und gibt den Klartext zurück — nur dieses eine Mal."""
    if not re.match(NAME_MUSTER, name):
        msg = f"Ungültiger Name '{name}' (Buchstaben, Ziffern, . _ -)"
        raise ValueError(msg)
    token = neues_token()
    speichere_webhook_token(
        session, WebhookToken(name=name, token_hash=token_hash(token))
    )
    return token


def pruefe_token(session: Session, token: str) -> WebhookToken | None:
    """Das aktive Token zu diesem Klartext oder ``None``."""
    if not token or len(token) > _MAX_LAENGE:
        return None
    gesucht = token_hash(token)
    eintrag = finde_webhook_token(session, gesucht)
    if eintrag is None or not eintrag.aktiv:
        return None
    if not hmac.compare_digest(eintrag.token_hash, gesucht):
        return None
    return eintrag
