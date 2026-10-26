"""Abschnitt ``elster`` in ``config/accounti.yaml`` — alles optional.

Ohne den Abschnitt rechnet accounti monatlich, ohne Dauerfristverlängerung, mit den
bundeseinheitlichen Feiertagen und kann nur im Testmodus übermitteln (kein ERiC).
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from accounti.konfiguration import STANDARD_PFAD, KonfigurationError

__all__ = [
    "BUNDESLAENDER",
    "ElsterEinstellungen",
    "EricEinstellungen",
    "Finanzamt",
    "KonfigurationError",
    "bereiche",
    "lade_elster",
]

BUNDESLAENDER = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}
_BEREICH = re.compile(r"^(\d{1,8})(?:-(\d{1,8}))?$")


def bereiche(angaben: list[str] | None) -> tuple[tuple[int, int], ...] | None:
    """``["8000-8999", "2700"]`` → ``((8000, 8999), (2700, 2700))``."""
    if angaben is None:
        return None
    ergebnis = []
    for angabe in angaben:
        treffer = _BEREICH.match(str(angabe).strip())
        if treffer is None:
            raise ValueError(f"Kontenbereich {angabe!r} — erwartet z.B. 8000-8999")
        von = int(treffer.group(1))
        bis = int(treffer.group(2) or von)
        ergebnis.append((von, bis))
    return tuple(ergebnis)


class Finanzamt(BaseModel):
    name: str | None = Field(default=None, description="Kreditor für die Zahllast")
    iban: str | None = None

    @field_validator("iban")
    @classmethod
    def _iban(cls, wert: str | None) -> str | None:
        return wert.replace(" ", "").upper() if wert else None


class EricEinstellungen(BaseModel):
    """ERiC (ELSTER Rich Client) — nur aktiv mit Bibliothek, Zertifikat und PIN."""

    bibliothek: str | None = Field(default=None, description="Pfad zu libericapi.so")
    plugins: str | None = Field(default=None, description="Plugin-Verzeichnis")
    log: str | None = Field(default=None, description="Verzeichnis für eric.log")
    zertifikat: str | None = Field(default=None, description="ELSTER-Zertifikat (.pfx)")
    pin_datei: str | None = Field(default=None, description="verschlüsselte PIN")
    # Versionen der Strukturen aus eric_types.h — mit dem geladenen ERiC abgleichen
    druck_parameter_version: int = Field(default=2, ge=1)
    verschluesselungs_parameter_version: int = Field(default=2, ge=1)


class ElsterEinstellungen(BaseModel):
    voranmeldungszeitraum: Literal["monat", "quartal"] = "monat"
    dauerfristverlaengerung: bool = False
    sondervorauszahlung: dict[int, Decimal] = Field(
        default_factory=dict,
        description="festgesetzte SVZ je Jahr (Kz 39 im Dezember), vor dem Protokoll",
    )
    bundesland: str | None = None
    steuernummer: str | None = Field(
        default=None, description="sonst mandant.steuernummer"
    )
    finanzamt: Finanzamt = Field(default_factory=Finanzamt)
    hersteller_id: str | None = Field(default=None, description="eigene, für Kz09")
    produkt_name: str = "accounti"
    uebermittler: Literal["eric", "attrappe"] = "eric"
    eric: EricEinstellungen = Field(default_factory=EricEinstellungen)
    abweichung_prozent: Decimal = Decimal("50")
    abweichung_mindestens: Decimal = Decimal("1000")
    steuerrelevante_konten: list[str] | None = None
    kennziffern_konten: dict[str, int] = Field(default_factory=dict)
    konten_ohne_kennziffer: list[str] = Field(
        default_factory=list,
        description=(
            "Steuerkonten außerhalb der deutschen Voranmeldung (ohne Warnung) — "
            "die OSS-Umsatzsteuerkonten aus integrationen ergänzt lade_elster"
        ),
    )
    konto_vorauszahlung: str | None = Field(
        default=None, description="Standard 1780 (SKR03) bzw. 3820 (SKR04)"
    )
    konto_sondervorauszahlung: str | None = Field(
        default=None, description="Standard 1781 (SKR03) bzw. 3830 (SKR04)"
    )

    @field_validator("bundesland")
    @classmethod
    def _land(cls, wert: str | None) -> str | None:
        if wert is None:
            return None
        land = wert.strip().upper()
        if land not in BUNDESLAENDER:
            msg = f"Bundesland {wert!r} unbekannt — erlaubt: {', '.join(BUNDESLAENDER)}"
            raise ValueError(msg)
        return land

    @field_validator("hersteller_id")
    @classmethod
    def _hersteller(cls, wert: str | None) -> str | None:
        if wert is not None and not str(wert).strip().isdigit():
            raise ValueError("Hersteller-ID besteht nur aus Ziffern")
        return str(wert).strip() if wert is not None else None

    @field_validator("steuerrelevante_konten")
    @classmethod
    def _bereiche(cls, wert: list[str] | None) -> list[str] | None:
        bereiche(wert)
        return wert

    @field_validator("sondervorauszahlung", mode="before")
    @classmethod
    def _svz_je_jahr(cls, wert: Any) -> Any:
        if wert is None:
            return {}
        if not isinstance(wert, dict):
            msg = (
                "Sondervorauszahlung je Jahr angeben, z.B. {2026: 4000.00} — ein Wert "
                "ohne Jahr gälte sonst in jedem Folgejahr"
            )
            raise ValueError(msg)
        return wert

    @field_validator("kennziffern_konten")
    @classmethod
    def _kennziffern(cls, wert: dict[str, int]) -> dict[str, int]:
        from accounti.steuer.kennziffern import zuordenbar

        for konto, kz in wert.items():
            if not zuordenbar(kz):
                msg = (
                    f"Konto {konto}: Kz {kz} ist keine Bemessungsgrundlage und kein "
                    "Steuerfeld im Vordruck (Kz 83 und 39 rechnet accounti selbst)"
                )
                raise ValueError(msg)
        return {str(k): v for k, v in wert.items()}


def _fehlertext(fehler: ValidationError) -> str:
    teile = []
    for f in fehler.errors():
        pfad = ".".join(str(x) for x in f["loc"])
        grund = str(f["msg"]).removeprefix("Value error, ")
        teile.append(f"elster.{pfad}: {grund}" if pfad else f"elster: {grund}")
    return "; ".join(teile)


def lade_elster(pfad: str | Path = STANDARD_PFAD) -> ElsterEinstellungen:
    pfad = Path(pfad)
    if not pfad.is_file():
        return ElsterEinstellungen()
    daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    abschnitt = daten.get("elster") if isinstance(daten, dict) else None
    try:
        einstellungen = ElsterEinstellungen.model_validate(abschnitt or {})
    except ValidationError as fehler:
        msg = f"{pfad}: {_fehlertext(fehler)}"
        raise KonfigurationError(msg) from fehler
    return _mit_oss_konten(einstellungen, pfad)


def _mit_oss_konten(
    einstellungen: ElsterEinstellungen, pfad: Path
) -> ElsterEinstellungen:
    """OSS-Erlöskonten aus ``integrationen`` sind Konten mit fester Funktion: der
    Nettoumsatz eines Fernverkaufs gehört in Kz 45 (Anleitung USt 1 E 2026 zu Zeile
    36); die OSS-Umsatzsteuer meldet die OSS-Erklärung (§ 18j UStG), nicht die
    Voranmeldung. Eigene Angaben in ``elster.kennziffern_konten`` gehen vor."""
    from accounti.integrationen.einstellungen import lade_integrationen
    from accounti.konfiguration import lade_buchhaltung
    from accounti.steuer.kennziffern import KENNZIFFERN_KONTEN

    i = lade_integrationen(pfad)
    fest = KENNZIFFERN_KONTEN.get(lade_buchhaltung(pfad).kontenrahmen.upper(), {})
    oss = {
        konto
        for konto in (*i.oss_erloes_konten.values(), *i.oss_erloes_ermaessigt.values())
        if fest.get(konto) != 45
    }
    steuer = {i.oss_ust_konto, *i.oss_ust_konten.values()}
    return einstellungen.model_copy(
        update={
            "kennziffern_konten": {
                **dict.fromkeys(sorted(oss), 45),
                **einstellungen.kennziffern_konten,
            },
            "konten_ohne_kennziffer": sorted(
                {*einstellungen.konten_ohne_kennziffer, *steuer}
            ),
        }
    )


def lade_oss(pfad: str | Path = STANDARD_PFAD) -> bool:
    """``mandant.oss`` — nachsichtig gelesen (fehlt der Mandant, gilt: kein OSS)."""
    pfad = Path(pfad)
    if not pfad.is_file():
        return False
    daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    mandant = daten.get("mandant") if isinstance(daten, dict) else None
    return bool(isinstance(mandant, dict) and mandant.get("oss"))


def lade_mandant(pfad: str | Path = STANDARD_PFAD) -> dict[str, str]:
    """Name, Anschrift und Steuernummer aus ``mandant`` — nachsichtig gelesen."""
    pfad = Path(pfad)
    daten: Any = {}
    if pfad.is_file():
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    mandant = daten.get("mandant") if isinstance(daten, dict) else None
    mandant = mandant if isinstance(mandant, dict) else {}
    anschrift = mandant.get("anschrift")
    anschrift = anschrift if isinstance(anschrift, dict) else {}
    werte = {
        "name": mandant.get("name"),
        "strasse": anschrift.get("strasse"),
        "plz": anschrift.get("plz"),
        "ort": anschrift.get("ort"),
        "steuernummer": mandant.get("steuernummer"),
    }
    return {k: str(v).strip() for k, v in werte.items() if v not in (None, "")}
