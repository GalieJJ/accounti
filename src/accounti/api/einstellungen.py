"""Abschnitt ``server`` in ``config/accounti.yaml`` — optional, mit Standardwerten.

```yaml
server:
  host: "127.0.0.1"               # im Container 0.0.0.0, davor der Reverse-Proxy
  port: 8400
  cookie_sicher: true             # Secure + __Host-; nur ohne TLS (lokal) false
  vertrauenswuerdige_proxies: ["127.0.0.1"]   # nur deren X-Forwarded-* gelten
  max_formular_kb: 64
  max_beleg_mb: 20                # je Anfrage an POST /api/v1/belege
```
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from accounti.konfiguration import STANDARD_PFAD, KonfigurationError


class ServerEinstellungen(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8400, ge=1, le=65535)
    cookie_sicher: bool = Field(
        default=True,
        description="Cookie nur über HTTPS (Secure, Präfix __Host-)",
    )
    vertrauenswuerdige_proxies: list[str] = Field(
        default_factory=lambda: ["127.0.0.1"],
        description="Adressen, deren X-Forwarded-For/-Proto Uvicorn glaubt",
    )
    max_formular_kb: int = Field(default=64, ge=1, le=10_240)
    max_beleg_mb: float = Field(default=20, gt=0, le=200)

    @property
    def max_formular_bytes(self) -> int:
        return self.max_formular_kb * 1024

    @property
    def max_beleg_bytes(self) -> int:
        return int(self.max_beleg_mb * 1024 * 1024)


def lade_server(pfad: str | Path = STANDARD_PFAD) -> ServerEinstellungen:
    pfad = Path(pfad)
    if not pfad.is_file():
        return ServerEinstellungen()
    daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    abschnitt = daten.get("server") if isinstance(daten, dict) else None
    if abschnitt is None:
        return ServerEinstellungen()
    if not isinstance(abschnitt, dict):
        msg = f"{pfad}: Abschnitt 'server' muss eine Zuordnung sein"
        raise KonfigurationError(msg)
    try:
        return ServerEinstellungen.model_validate(abschnitt)
    except ValidationError as fehler:
        teile = "; ".join(
            ".".join(str(x) for x in f["loc"]) + ": " + str(f["msg"])
            for f in fehler.errors()
        )
        msg = f"{pfad}: Abschnitt 'server': {teile}"
        raise KonfigurationError(msg) from fehler
