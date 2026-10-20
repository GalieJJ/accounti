"""Abschnitt ``bank`` in ``config/accounti.yaml`` — optional, mit Standardwerten.

```yaml
bank:
  fints:
    produkt_id: "${ACCOUNTI_FINTS_PRODUKT_ID}"   # Registrierung der DK, nie ins Repo
  kreditkarte:
    geldtransit_konto: "1360"
```

``${NAME}`` wird durch die Umgebungsvariable ersetzt (fehlt sie: leer);
``ACCOUNTI_FINTS_PRODUKT_ID`` geht dem Wert aus der Datei vor.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from accounti.konfiguration import STANDARD_PFAD, KonfigurationError

UMGEBUNG_PRODUKT_ID = "ACCOUNTI_FINTS_PRODUKT_ID"
_VARIABLE = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


class FinTSEinstellungen(BaseModel):
    produkt_id: str | None = Field(
        default=None, description="Registrierungsnummer der DK (HKVVB, an..25)"
    )
    produkt_version: str = Field(default="0.1", min_length=1, max_length=5)
    erster_abruf_tage: int = Field(
        default=90, ge=1, description="erster Abruf ohne Stand: so weit zurück"
    )
    freigabe_wartezeit_sekunden: float = Field(default=300, gt=0)
    freigabe_intervall_sekunden: float = Field(default=3, ge=0)
    zeitlimit_sekunden: float = Field(
        default=120, gt=0, description="je Anfrage an die Bank — kein ewiges Warten"
    )

    @field_validator("produkt_id")
    @classmethod
    def _produkt_id(cls, wert: str | None) -> str | None:
        wert = (wert or "").strip()
        if len(wert) > 25:
            msg = "Produkt-ID hat höchstens 25 Zeichen (Produktbezeichnung im HKVVB)"
            raise ValueError(msg)
        return wert or None


class KreditkartenEinstellungen(BaseModel):
    geldtransit_konto: str | None = Field(
        default=None, description="leer: SKR03 1360, SKR04 1460"
    )
    belastung_muster: str = Field(
        default=r"kreditkart|kartenabrechnung|visa|master ?card|american express|amex",
        description="erkennt die Sammelbelastung auf dem Girokonto",
    )
    belastung_ausnahme: str = Field(
        default=r"debit",
        description="keine Sammelbelastung, obwohl das Muster passt (Debitkarte)",
    )
    ausgleich_muster: str = Field(
        default=(
            r"ihre zahlung|zahlung erhalten|zahlung.{0,3}danke|zahlungseingang"
            r"|ausgleich|lastschrift|einzug|begleich|abbuchung"
        ),
        description="erkennt die Begleichung der Vorperiode auf dem Kartenkonto",
    )
    belastung_fenster_tage: int = Field(default=30, ge=0)

    @field_validator("belastung_muster", "belastung_ausnahme", "ausgleich_muster")
    @classmethod
    def _muster(cls, wert: str) -> str:
        try:
            re.compile(wert)
        except re.error as fehler:
            raise ValueError(f"Muster ist kein regulärer Ausdruck: {fehler}") from None
        return wert

    def geldtransit(self, kontenrahmen: str) -> str:
        if self.geldtransit_konto:
            return self.geldtransit_konto
        return "1460" if kontenrahmen.upper() == "SKR04" else "1360"

    def ist_belastung(self, text: str) -> bool:
        """Sammelbelastung nach dem Standardmuster — ohne Debitkartenzahlungen
        („VISA Debit …“), die auf Girokonten häufig sind."""
        if re.search(self.belastung_muster, text, re.IGNORECASE) is None:
            return False
        ausnahme = self.belastung_ausnahme
        return not ausnahme or re.search(ausnahme, text, re.IGNORECASE) is None

    def ist_ausgleich(self, text: str) -> bool:
        return re.search(self.ausgleich_muster, text, re.IGNORECASE) is not None


class BankEinstellungen(BaseModel):
    fints: FinTSEinstellungen = Field(default_factory=FinTSEinstellungen)
    kreditkarte: KreditkartenEinstellungen = Field(
        default_factory=KreditkartenEinstellungen
    )


def _ersetze(wert: Any) -> Any:
    if isinstance(wert, dict):
        return {k: _ersetze(v) for k, v in wert.items()}
    if isinstance(wert, list):
        return [_ersetze(v) for v in wert]
    if isinstance(wert, str):
        return _VARIABLE.sub(lambda m: os.environ.get(m.group(1), ""), wert)
    return wert


def _fehlertext(fehler: ValidationError) -> str:
    teile = []
    for f in fehler.errors():
        pfad = ".".join(str(x) for x in f["loc"])
        grund = str(f["msg"]).removeprefix("Value error, ")
        teile.append(f"{pfad}: {grund}" if pfad else grund)
    return "; ".join(teile)


def lade_bank_einstellungen(pfad: str | Path = STANDARD_PFAD) -> BankEinstellungen:
    pfad = Path(pfad)
    abschnitt: Any = None
    if pfad.is_file():
        daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
        abschnitt = daten.get("bank") if isinstance(daten, dict) else None
    if abschnitt is not None and not isinstance(abschnitt, dict):
        msg = f"{pfad}: Abschnitt 'bank' muss eine Zuordnung sein"
        raise KonfigurationError(msg)
    werte: dict[str, Any] = _ersetze(abschnitt or {})
    if os.environ.get(UMGEBUNG_PRODUKT_ID):
        fints = werte.get("fints")
        werte["fints"] = {
            **(fints if isinstance(fints, dict) else {}),
            "produkt_id": os.environ[UMGEBUNG_PRODUKT_ID],
        }
    try:
        return BankEinstellungen.model_validate(werte)
    except ValidationError as fehler:
        msg = f"{pfad}: Abschnitt 'bank': {_fehlertext(fehler)}"
        raise KonfigurationError(msg) from fehler
