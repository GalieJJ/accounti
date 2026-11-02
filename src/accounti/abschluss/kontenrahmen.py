"""Abschlusszuordnung der Konten — Kontoart, Geld- und Steuerkonten, EÜR-Kennzahl.

Die Zuordnung ist Konfiguration (``kontenrahmen_skr03.yaml``, ``…_skr04.yaml``), wie
die BWA-Zuordnung in ``pruefung/skr03.yaml``. Bereiche werden numerisch verglichen; die
engste passende Spanne gewinnt. Personenkonten sind fünfstellig; längere Sachkonten
(6-stellig) werden an ihren ersten vier Ziffern eingeordnet.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from decimal import Decimal
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from accounti.steuer.umsatzsteuer import (
    DATEV_BU_SCHLUESSEL,
    UST_KONTEN_SKR03,
    VST_KONTEN_SKR03,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

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
    # unbekannte Schlüssel (Tippfehler) lehnt der Lader ab, statt sie still zu verwerfen
    model_config = ConfigDict(extra="forbid")

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
    hinweis: str | None = None  # warum ohne Zeile bzw. was beim Ausfüllen zu tun ist


class Vortragskonten(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

    name: str
    quelle: str = ""
    arten: list[_Art] = Field(default_factory=list)
    geldkonten: list[_Spanne] = Field(default_factory=list)
    bankkonten: list[_Spanne] = Field(default_factory=list)
    # Kasse, Bank, Geldtransit, Kreditkarte; fehlt der Abschnitt (eigene Zuordnung
    # älterer Fassung), gilt der des mitgelieferten Kontenrahmens gleichen Namens
    # (sonst die Bankkonten) — Gesamttest 10b-1, Runde 3
    zahlungsmittel: list[_Spanne] | None = None
    # Geldtransit: ein Zahlungsmittel ohne eigene Umsätze (kein Kontoauszug)
    geldtransit: list[_Spanne] | None = None
    # Forderungen und Verbindlichkeiten aus Lieferungen und Leistungen (Sammelkonten)
    lul_konten: list[_Spanne] | None = None
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

    def _abschnitt(self, name: str) -> list[_Spanne] | None:
        """Abschnitt der Zuordnung — fehlt er (eigene Zuordnung älterer Fassung), der
        des mitgelieferten Kontenrahmens gleichen Namens."""
        eigener: list[_Spanne] | None = getattr(self, name)
        if eigener is not None:
            return eigener
        mitgeliefert = _mitgeliefert(self.name)
        if mitgeliefert is None or mitgeliefert is self:
            return None
        spannen: list[_Spanne] | None = getattr(mitgeliefert, name)
        return spannen

    def _zahlungsmittel(self) -> list[_Spanne]:
        return self._abschnitt("zahlungsmittel") or self.bankkonten

    def ist_zahlungsmittel(self, konto: str) -> bool:
        """Kasse, Bank, Geldtransit, Kreditkarte (``zahlungsmittel``) — anders als
        ``ist_geldkonto`` ohne Forderungen, Verbindlichkeiten und Personenkonten.
        Zwischen zwei solchen Konten gibt es nur Umbuchungen: Sie stehen auf beiden
        Kontoauszügen, daraus wird keine Kontierungsregel (Gesamttest 10b-1, H-1)."""
        if self.ist_personenkonto(konto):
            return False
        return self._engste(self._zahlungsmittel(), konto) is not None

    def ist_geldtransit(self, konto: str) -> bool:
        """Geldtransit (SKR03 1360, SKR04 1460): ein Zahlungsmittel ohne eigenen
        Kontoauszug — eine Regel dagegen bucht nie Soll = Haben."""
        if self.ist_personenkonto(konto):
            return False
        return self._engste(self._abschnitt("geldtransit") or [], konto) is not None

    def ist_lul_konto(self, konto: str) -> bool:
        """Forderungen bzw. Verbindlichkeiten aus Lieferungen und Leistungen
        (Sammelkonten, ``lul_konten``) — wie ein Personenkonto kein Sachkonto eines
        Belegs."""
        if self.ist_personenkonto(konto):
            return False
        return self._engste(self._abschnitt("lul_konten") or [], konto) is not None

    def mit_geldkonten(self, konten: Iterable[str]) -> Kontenrahmen:
        """Kopie, in der auch diese Konten Geldkonten und Zahlungsmittel sind
        (eingerichtete Bank- und Kartenkonten mit eigenem Sachkonto)."""
        alle = sorted({k for k in konten if k.isdigit()})
        geld = [_Spanne(von=k, bis=k) for k in alle if not self.ist_geldkonto(k)]
        mittel = [_Spanne(von=k, bis=k) for k in alle if not self.ist_zahlungsmittel(k)]
        if not geld and not mittel:
            return self
        bisher = self._zahlungsmittel()
        return self.model_copy(
            update={
                "geldkonten": [*self.geldkonten, *geld],
                "zahlungsmittel": [*bisher, *mittel],
            }
        )

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

    def euer_hinweis(self, konto: str) -> str | None:
        """Hinweis der engsten EÜR-Regel, z. B. warum ein Konto keine Zeile hat."""
        regel = self._engste(self.euer, konto)
        hinweis: str | None = regel.hinweis if regel is not None else None
        return hinweis

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


def mit_eingerichteten_konten(kr: Kontenrahmen, session: Session) -> Kontenrahmen:
    """Der Kontenrahmen mit den Sachkonten der eingerichteten Bank- und Kartenkonten
    als Geldkonten (``bank verbinde``, ``kreditkarte einrichten``) — sie tragen bei
    Buchungen mit Steuer den Bruttobetrag wie die Bank (Gesamttest Eingang B08)."""
    from accounti.db.repository import lade_bankkonten

    return kr.mit_geldkonten(k.sachkonto for k in lade_bankkonten(session))


@lru_cache(maxsize=4)
def _mitgeliefert(name: str) -> Kontenrahmen | None:
    """Mitgelieferte Zuordnung zum Namen (``None`` ohne eine) — für Abschnitte, die
    einer eigenen Zuordnung älterer Fassung fehlen."""
    try:
        return lade_kontenrahmen(name)
    except KontenrahmenError:
        return None


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
