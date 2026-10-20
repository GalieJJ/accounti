"""API-Token für Fremdsysteme — 256 Bit Zufall, gespeichert nur als SHA-256.

Bei dieser Entropie genügt ein schneller Hash ohne Salz (wie bei den
Webhook-Token): Raten ist aussichtslos, und aus dem Hash lässt sich das Token nicht
zurückgewinnen. Jedes Token gehört zu genau einer Gesellschaft und trägt
ausdrücklich genannte Rechte; Freigaben kann kein Token.
"""

from __future__ import annotations

import hmac
import re
import secrets
from collections.abc import Iterable
from datetime import date, datetime

from sqlalchemy.orm import Session

from accounti.auth.dienst import ereignis, token_hash
from accounti.db.repo_auth import (
    lade_api_token_nach_hash,
    markiere_api_token_genutzt,
    speichere_api_token,
)
from accounti.models.auth import ApiToken, TokenRecht, pruefe_gesellschaft

PRAEFIX = "accounti_api_"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,59}$")
_MAX_LAENGE = 200


def lege_api_token_an(
    s: Session,
    name: str,
    gesellschaft: str,
    rechte: Iterable[TokenRecht],
    angelegt_von: str,
    *,
    gueltig_bis: date | None = None,
    jetzt: datetime | None = None,
) -> str:
    """Legt das Token an und gibt den Klartext zurück — nur dieses eine Mal."""
    jetzt = jetzt or datetime.now()
    if not _NAME.match(name):
        msg = f"Ungültiger Name {name!r} (Buchstaben, Ziffern, . _ -)"
        raise ValueError(msg)
    liste = sorted(set(rechte), key=lambda r: r.value)
    if not liste:
        raise ValueError("Ein Token braucht mindestens eines der Rechte")
    if gueltig_bis is not None and gueltig_bis < jetzt.date():
        raise ValueError("Das Ablaufdatum liegt in der Vergangenheit")
    klartext = PRAEFIX + secrets.token_urlsafe(32)
    speichere_api_token(
        s,
        ApiToken(
            name=name,
            token_hash=token_hash(klartext),
            gesellschaft=pruefe_gesellschaft(gesellschaft),
            rechte=liste,
            angelegt_von=angelegt_von,
            angelegt_am=jetzt,
            gueltig_bis=gueltig_bis,
        ),
    )
    ereignis(
        s,
        "token_angelegt",
        jetzt,
        angelegt_von,
        gesellschaft=gesellschaft,
        hinweis=f"{name}: {', '.join(r.value for r in liste)}",
    )
    return klartext


def pruefe_api_token(
    s: Session, klartext: str, jetzt: datetime | None = None
) -> ApiToken | None:
    """Das gültige Token zu diesem Klartext — sonst ``None``."""
    jetzt = jetzt or datetime.now()
    if not klartext or len(klartext) > _MAX_LAENGE:
        return None
    gesucht = token_hash(klartext)
    token = lade_api_token_nach_hash(s, gesucht)
    if token is None or not hmac.compare_digest(token.token_hash, gesucht):
        return None
    if not token.gilt(jetzt):
        return None
    markiere_api_token_genutzt(s, token.id, jetzt)
    return token.model_copy(update={"zuletzt_genutzt_am": jetzt})
