"""Einstellungen der Beleg-Kanäle — Abschnitt ``belegkanaele`` in config/accounti.yaml.

Der Abschnitt ist optional: Ohne ihn gibt es keine Postfächer und keine Connectoren,
und der Webhook lauscht nur lokal. Geheimnisse stehen nie im Klartext in der Datei —
ein Passwort ist entweder ``${UMGEBUNGSVARIABLE}`` oder liegt verschlüsselt im
Tresor (``accounti kanaele zugang``). Variablen werden erst aufgelöst, wenn der
Kanal gebaut wird: Eine fehlende Variable eines anderen Postfachs stört nicht.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from accounti.belege.kanaele.pruefung import DATEITYPEN, Dateipruefung
from accounti.konfiguration import STANDARD_PFAD, KonfigurationError

ABSCHNITT = "belegkanaele"
LOKALE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
NAME_MUSTER = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,59}$"

_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_NUR_VARIABLE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")
MB = 1024 * 1024


def loese_auf(wert: str) -> str:
    """``${NAME}`` durch die Umgebungsvariable ersetzen."""

    def ersetze(treffer: re.Match[str]) -> str:
        name = treffer.group(1)
        if name not in os.environ:
            msg = f"Umgebungsvariable {name} ist nicht gesetzt"
            raise KonfigurationError(msg)
        return os.environ[name]

    return _VARIABLE.sub(ersetze, wert)


def hat_variable(wert: str) -> bool:
    return bool(_VARIABLE.search(wert))


class EmailPostfach(BaseModel):
    """Ein IMAP-Postfach (ein Ordner darin)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=NAME_MUSTER, description="frei wählbar, z.B. rechnungen")
    host: str
    port: int | None = Field(default=None, ge=1, le=65535)
    verschluesselung: Literal["ssl", "starttls", "keine"] = "ssl"
    benutzer: str
    passwort: str | None = Field(
        default=None, description="nur ${UMGEBUNGSVARIABLE}; sonst aus dem Tresor"
    )
    ordner: str = "INBOX"
    ab: date | None = Field(default=None, description="ältere Nachrichten auslassen")
    nach_abholen: Literal["belassen", "gelesen", "verschieben"] = "belassen"
    ziel_ordner: str | None = None
    ca_datei: str | None = Field(default=None, description="eigene CA (PEM)")
    timeout_sekunden: float = Field(default=60, gt=0)
    max_nachricht_mb: float = Field(default=50, gt=0)

    @field_validator("ordner", "ziel_ordner")
    @classmethod
    def _ascii(cls, wert: str | None) -> str | None:
        if wert is not None and not wert.isascii():
            msg = "Ordnernamen nur in ASCII (modified UTF-7 wird nicht umgesetzt)"
            raise ValueError(msg)
        return wert

    @model_validator(mode="after")
    def _regeln(self) -> EmailPostfach:
        if self.passwort is not None and not _NUR_VARIABLE.match(self.passwort):
            msg = (
                "Passwort im Klartext ist nicht erlaubt — ${UMGEBUNGSVARIABLE} "
                f"verwenden oder 'accounti kanaele zugang email {self.name}'"
            )
            raise ValueError(msg)
        if self.verschluesselung == "keine" and self.host not in LOKALE_HOSTS:
            msg = "verschluesselung 'keine' ist nur für localhost erlaubt"
            raise ValueError(msg)
        if self.nach_abholen == "verschieben" and not self.ziel_ordner:
            msg = "nach_abholen 'verschieben' braucht ziel_ordner"
            raise ValueError(msg)
        return self

    @property
    def port_oder_standard(self) -> int:
        if self.port is not None:
            return self.port
        return 993 if self.verschluesselung == "ssl" else 143

    @property
    def max_nachricht_bytes(self) -> int:
        return int(self.max_nachricht_mb * MB)


class WebhookEinstellungen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(default=8410, ge=1, le=65535)
    max_dateien: int = Field(default=10, ge=1)
    max_anfrage_mb: float = Field(default=60, gt=0)

    @property
    def max_anfrage_bytes(self) -> int:
        return int(self.max_anfrage_mb * MB)


class ConnectorEintrag(BaseModel):
    """Ein konfigurierter Connector; die übrigen Felder prüft sein Typ."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(pattern=NAME_MUSTER)
    typ: str

    def einstellungen(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class KanalEinstellungen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_groesse_mb: float = Field(default=25, gt=0, description="je Datei")
    dateitypen: list[str] = Field(default_factory=lambda: list(DATEITYPEN))
    email: list[EmailPostfach] = Field(default_factory=list)
    webhook: WebhookEinstellungen = Field(default_factory=WebhookEinstellungen)
    connectoren: list[ConnectorEintrag] = Field(default_factory=list)

    @field_validator("dateitypen")
    @classmethod
    def _typen(cls, typen: list[str]) -> list[str]:
        unbekannt = sorted(set(typen) - set(DATEITYPEN))
        if unbekannt:
            msg = (
                f"unbekannte Dateitypen {', '.join(unbekannt)} "
                f"(möglich: {', '.join(DATEITYPEN)})"
            )
            raise ValueError(msg)
        return typen

    @model_validator(mode="after")
    def _eindeutig(self) -> KanalEinstellungen:
        for art, namen in (
            ("email", [p.name for p in self.email]),
            ("connectoren", [c.name for c in self.connectoren]),
        ):
            doppelt = sorted({n for n in namen if namen.count(n) > 1})
            if doppelt:
                msg = f"{art}: Name doppelt vergeben: {', '.join(doppelt)}"
                raise ValueError(msg)
        return self

    def pruefung(self) -> Dateipruefung:
        return Dateipruefung(
            max_bytes=int(self.max_groesse_mb * MB), typen=frozenset(self.dateitypen)
        )

    def postfach(self, name: str) -> EmailPostfach:
        for p in self.email:
            if p.name == name:
                return p
        bekannt = ", ".join(p.name for p in self.email) or "keine"
        msg = f"Postfach '{name}' ist nicht konfiguriert (vorhanden: {bekannt})"
        raise KonfigurationError(msg)

    def connector(self, name: str) -> ConnectorEintrag:
        for c in self.connectoren:
            if c.name == name:
                return c
        bekannt = ", ".join(c.name for c in self.connectoren) or "keine"
        msg = f"Connector '{name}' ist nicht konfiguriert (vorhanden: {bekannt})"
        raise KonfigurationError(msg)


def _fehlertext(fehler: ValidationError) -> str:
    teile = []
    for f in fehler.errors():
        pfad = ".".join(str(x) for x in f["loc"])
        grund = (
            "fehlt"
            if f["type"] == "missing"
            else str(f["msg"]).removeprefix("Value error, ")
        )
        teile.append(f"{ABSCHNITT}.{pfad}: {grund}" if pfad else grund)
    return "; ".join(teile)


def lade_belegkanaele(pfad: str | Path = STANDARD_PFAD) -> KanalEinstellungen:
    """Abschnitt ``belegkanaele``; ohne Datei oder Abschnitt gelten die Standards."""
    pfad = Path(pfad)
    if not pfad.is_file():
        return KanalEinstellungen()
    daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    abschnitt = daten.get(ABSCHNITT) if isinstance(daten, dict) else None
    try:
        return KanalEinstellungen.model_validate(abschnitt or {})
    except ValidationError as fehler:
        msg = f"{pfad}: {_fehlertext(fehler)}"
        raise KonfigurationError(msg) from fehler
