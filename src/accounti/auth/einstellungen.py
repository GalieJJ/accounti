"""Abschnitt ``auth`` in ``config/accounti.yaml`` — optional, mit Standardwerten.

```yaml
auth:
  passwort_mindestlaenge: 12      # NIST 800-63B-4: mit zweitem Faktor ≥ 8
  sperre_nach_fehlversuchen: 5
  sperre_minuten: 15
  sitzung_leerlauf_minuten: 30    # OWASP: 15–30 min (geringes Risiko)
  sitzung_hoechstdauer_stunden: 8 # OWASP: z. B. 4–8 h
  totp_toleranz_schritte: 1       # RFC 6238 5.2: höchstens ein Schritt empfohlen
  einmalcode_bestaetigung: true   # Freigaben (Browser und CLI) mit Einmalcode
  aussteller: accounti            # Name in der Authenticator-App
```
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from accounti.konfiguration import STANDARD_PFAD, KonfigurationError


class AuthEinstellungen(BaseModel):
    passwort_mindestlaenge: int = Field(default=12, ge=8, le=64)
    sperre_nach_fehlversuchen: int = Field(default=5, ge=1, le=100)
    sperre_minuten: int = Field(default=15, ge=1)
    sitzung_leerlauf_minuten: int = Field(default=30, ge=1)
    sitzung_hoechstdauer_stunden: float = Field(default=8, gt=0, le=24 * 7)
    totp_toleranz_schritte: int = Field(default=1, ge=0, le=2)
    einmalcode_bestaetigung: bool = Field(
        default=True,
        description=(
            "Freigaben im Browser und in der CLI sowie die Verwaltung in der CLI "
            "verlangen den Einmalcode"
        ),
    )
    aussteller: str = Field(default="accounti", min_length=1, max_length=60)


def _fehlertext(fehler: ValidationError) -> str:
    return "; ".join(
        ".".join(str(x) for x in f["loc"])
        + ": "
        + str(f["msg"]).removeprefix("Value error, ")
        for f in fehler.errors()
    )


def lade_auth(pfad: str | Path = STANDARD_PFAD) -> AuthEinstellungen:
    """Abschnitt ``auth``; fehlt Datei oder Abschnitt, gelten die Standardwerte."""
    pfad = Path(pfad)
    if not pfad.is_file():
        return AuthEinstellungen()
    daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    abschnitt = daten.get("auth") if isinstance(daten, dict) else None
    if abschnitt is None:
        return AuthEinstellungen()
    if not isinstance(abschnitt, dict):
        msg = f"{pfad}: Abschnitt 'auth' muss eine Zuordnung sein"
        raise KonfigurationError(msg)
    try:
        return AuthEinstellungen.model_validate(abschnitt)
    except ValidationError as fehler:
        msg = f"{pfad}: Abschnitt 'auth': {_fehlertext(fehler)}"
        raise KonfigurationError(msg) from fehler
