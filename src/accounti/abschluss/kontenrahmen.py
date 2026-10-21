"""Abschlusszuordnung der Konten — Kontoart, Geld- und Steuerkonten, EÜR-Kennzahl.

Die Zuordnung ist Konfiguration (``kontenrahmen_skr03.yaml``, ``…_skr04.yaml``), wie
die BWA-Zuordnung in ``pruefung/skr03.yaml``. Bereiche werden numerisch verglichen; die
engste passende Spanne gewinnt. Personenkonten sind fünfstellig; längere Sachkonten
(6-stellig) werden an ihren ersten vier Ziffern eingeordnet.
"""

from __future__ import annotations

import enum
from decimal import Decimal
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from accounti.steuer.umsatzsteuer import (
    DATEV_BU_SCHLUESSEL,
    UST_KONTEN_SKR03,
    VST_KONTEN_SKR03,
)

Gewinnermittlung = Literal["euer", "bilanz"]

# EÜR-Kennzahl „gehört nicht in die EÜR“ (weder Betriebseinnahme noch -ausgabe, z. B.
# Steuern vom Einkommen) — anders als ``None`` (Zuordnung fehlt, zählt mit)
NICHT_IN_EUER = "-"


class KontenrahmenError(ValueError):
    """Die Kontenzuordnung fehlt oder ist nicht lesbar."""


class Kontenart(str, enum.Enum):
    BESTAND = "bestand"
    ERFOLG = "erfolg"
    STEUER = "steuer"  # nur in der Datei: EÜR → Erfolg, Bilanz → Bestand
    PRIVAT = "privat"
    VORTRAG = "vortrag"


class _Spanne(BaseModel):
    von: str
    bis: str

    def enthaelt(self, nummer: int) -> bool:
        return int(self.von) <= nummer <= int(self.bis)

    @property
    def breite(self) -> int:
        return int(self.bis) - int(self.von)


class _Art(_Spanne):
    art: Kontenart


class _EuerRegel(_Spanne):
    kz: str | None
    kz_haben: str | None = None


class Vortragskonten(BaseModel):
    sachkonten: str = "9000"
    debitoren: str = "9008"
    kreditoren: str = "9009"


def _vorsteuer_schluessel() -> dict[int, tuple[Decimal, bool]]:
    """DATEV-BU-Schlüssel → (Steuersatz, Vorsteuer?) aus accounti.steuer."""
    ergebnis: dict[int, tuple[Decimal, bool]] = {}
    for name, schluessel in DATEV_BU_SCHLUESSEL.items():
        art, _, satz = name.partition("_")
        if schluessel is not None and art in ("ust", "vst") and satz.isdigit():
            ergebnis[schluessel] = (Decimal(satz), art == "vst")
    return ergebnis


STEUERSCHLUESSEL = _vorsteuer_schluessel()


class Kontenrahmen(BaseModel):
    name: str
    quelle: str = ""
    arten: list[_Art] = Field(default_factory=list)
    geldkonten: list[_Spanne] = Field(default_factory=list)
    bankkonten: list[_Spanne] = Field(default_factory=list)
    vortragskonten: Vortragskonten = Field(default_factory=Vortragskonten)
    steuerkonten: dict[int, str] = Field(default_factory=dict)
    euer: list[_EuerRegel] = Field(default_factory=list)
    namen: dict[str, str] = Field(default_factory=dict)

    @staticmethod
    def _nummer(konto: str) -> int | None:
        """Sachkontennummer für die Bereichssuche (6-stellig → erste vier Ziffern)."""
        if not konto.isdigit():
            return None
        return int(konto[:4]) if len(konto) > 5 else int(konto)

    @staticmethod
    def ist_personenkonto(konto: str) -> bool:
        return konto.isdigit() and len(konto) == 5

    def _engste(self, regeln: list[Any], konto: str) -> Any:
        nummer = self._nummer(konto)
        if nummer is None:
            return None
        passend = [r for r in regeln if r.enthaelt(nummer)]
        return min(passend, key=lambda r: r.breite) if passend else None

    def art(self, konto: str, gewinnermittlung: Gewinnermittlung) -> Kontenart:
        if self.ist_personenkonto(konto):
            return Kontenart.BESTAND
        regel = self._engste(self.arten, konto)
        art = regel.art if regel is not None else Kontenart.ERFOLG
        if art is Kontenart.STEUER:
            return Kontenart.ERFOLG if gewinnermittlung == "euer" else Kontenart.BESTAND
        return art

    def ist_geldkonto(self, konto: str) -> bool:
        if self.ist_personenkonto(konto):
            return True
        return self._engste(self.geldkonten, konto) is not None

    def ist_bankkonto(self, konto: str) -> bool:
        """Bankkonto laut Kontenrahmen — wird mit dem Kontoauszug abgestimmt."""
        if self.ist_personenkonto(konto):
            return False
        return self._engste(self.bankkonten, konto) is not None

    def steuerkonto(self, schluessel: int | None) -> str | None:
        if schluessel is None or schluessel not in STEUERSCHLUESSEL:
            return None
        if self.steuerkonten:
            return self.steuerkonten.get(schluessel)
        satz, vorsteuer = STEUERSCHLUESSEL[schluessel]
        konten = VST_KONTEN_SKR03 if vorsteuer else UST_KONTEN_SKR03
        return konten.get(str(int(satz))) or None

    @staticmethod
    def ist_vorsteuer(schluessel: int | None) -> bool:
        return schluessel in STEUERSCHLUESSEL and STEUERSCHLUESSEL[schluessel][1]

    def euer_kz(self, konto: str, saldo: Decimal) -> str | None:
        """Kennzahl der Anlage EÜR; Saldo = Soll − Haben."""
        regel = self._engste(self.euer, konto)
        if regel is None:
            return None
        if saldo < 0 and regel.kz_haben:
            return regel.kz_haben  # type: ignore[no-any-return]
        return regel.kz  # type: ignore[no-any-return]

    def vortragskonto(
        self,
        konto: str,
        debitoren: tuple[int, int],
        kreditoren: tuple[int, int],
    ) -> str:
        if self.ist_personenkonto(konto):
            nummer = int(konto)
            if debitoren[0] <= nummer <= debitoren[1]:
                return self.vortragskonten.debitoren
            if kreditoren[0] <= nummer <= kreditoren[1]:
                return self.vortragskonten.kreditoren
        return self.vortragskonten.sachkonten

    def ist_saldenvortrag(self, konto: str) -> bool:
        v = self.vortragskonten
        return konto in (v.sachkonten, v.debitoren, v.kreditoren)

    def bezeichnung(self, konto: str) -> str:
        return self.namen.get(konto, "")


def _pruefe(text: str, name: str) -> Kontenrahmen:
    try:
        daten: Any = yaml.safe_load(text) or {}
        return Kontenrahmen.model_validate(daten)
    except (yaml.YAMLError, ValidationError) as fehler:
        raise KontenrahmenError(f"{name}: {fehler}") from fehler


def lade_kontenrahmen(
    name: str = "SKR03", eigene: str | Path | None = None
) -> Kontenrahmen:
    """Mitgelieferte Zuordnung je Kontenrahmen oder eine eigene Datei (ersetzt sie)."""
    if eigene is not None:
        pfad = Path(eigene)
        if not pfad.is_file():
            raise KontenrahmenError(f"Kontenzuordnung {pfad} fehlt")
        return _pruefe(pfad.read_text(encoding="utf-8"), str(pfad))
    datei = f"kontenrahmen_{name.lower()}.yaml"
    quelle = resources.files("accounti.abschluss").joinpath(datei)
    if not quelle.is_file():
        msg = f"Für den Kontenrahmen {name} gibt es keine Abschlusszuordnung"
        raise KontenrahmenError(msg)
    return _pruefe(quelle.read_text(encoding="utf-8"), datei)
