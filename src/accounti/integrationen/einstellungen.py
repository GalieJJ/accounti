"""Abschnitt ``integrationen`` in ``config/accounti.yaml`` — optional, mit Standards.

Die Kontenvorgaben folgen dem SKR03. Die Verrechnungskonten der Marktplätze
(1361–1363) und das PayPal-Konto (1210) sind keine Standardkonten des Kontenrahmens
und müssen im Kanzleiprogramm angelegt bzw. hier angepasst werden. Für SKR04 sind
alle Konten zu überschreiben.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from accounti.konfiguration import (
    STANDARD_PFAD,
    Buchhaltung,
    KonfigurationError,
    lade_buchhaltung,
)


class Marktplatzkonten(BaseModel):
    """Konten und Erkennungsmerkmale eines Marktplatzes."""

    verrechnungskonto: str = Field(
        description="Guthaben beim Marktplatz (PayPal: Konto)"
    )
    einbehalt_konto: str = Field(default="1500", description="einbehaltene Reserven")
    verkaufsgebuehr: str = "4760"  # Verkaufsprovisionen
    versandgebuehr: str = "4780"  # Fremdleistungen Vertrieb (Fulfillment, Etiketten)
    lagergebuehr: str = "4780"
    zahlungsgebuehr: str = "4970"  # Nebenkosten des Geldverkehrs
    sonstige_gebuehr: str = "4760"
    werbung: str = "4610"  # Werbekosten
    ersatzleistung: str = Field(
        default="2700", description="Ersatz für verlorene/beschädigte Ware (Prüfung)"
    )
    klaerung: str = Field(
        default="1590", description="unbekannte Posten bis zur Klärung (Prüfung)"
    )
    bu_gebuehren: int | None = Field(
        default=None, description="BU-Schlüssel für Gebühren, z.B. bei § 13b UStG"
    )
    bank_stichworte: list[str] = Field(
        default_factory=list, description="Merkmale des Bankeingangs der Auszahlung"
    )

    def konto_fuer_gebuehr(self, art: str) -> str:
        return {
            "verkauf": self.verkaufsgebuehr,
            "versand": self.versandgebuehr,
            "lager": self.lagergebuehr,
            "zahlung": self.zahlungsgebuehr,
        }.get(art, self.sonstige_gebuehr)


_STANDARD_MARKTPLAETZE: dict[str, dict[str, Any]] = {
    "amazon": {"verrechnungskonto": "1361", "bank_stichworte": ["AMAZON"]},
    "ebay": {"verrechnungskonto": "1362", "bank_stichworte": ["EBAY"]},
    "shopify": {
        "verrechnungskonto": "1363",
        "verkaufsgebuehr": "4970",
        "bank_stichworte": ["SHOPIFY"],
    },
    "paypal": {
        "verrechnungskonto": "1210",
        "verkaufsgebuehr": "4970",
        "bank_stichworte": ["PAYPAL"],
    },
}


class Integrationen(BaseModel):
    """Abschnitt ``integrationen``."""

    erloes_inland: dict[str, str] = Field(
        default_factory=lambda: {"19": "8400", "7": "8300"}
    )
    bu_inland: dict[str, int] = Field(default_factory=lambda: {"19": 3, "7": 2})
    erloes_ig_lieferung: str = "8125"
    erloes_ausfuhr: str = "8120"
    erloes_unbekannt: str = Field(
        default="8200", description="Erlöse ohne Bestimmungsland (zur Prüfung)"
    )
    geldtransit_konto: str = "1360"
    auszahlung_toleranz_tage: int = Field(default=10, ge=0, le=60)
    ermaessigte_artikel: list[str] = Field(
        default_factory=list, description="SKUs mit ermäßigtem Steuersatz"
    )
    eu_fernverkaeufe_sonstige: dict[int, Decimal] = Field(
        default_factory=dict,
        description=(
            "EU-Fernverkäufe an Privatkunden (netto) je Kalenderjahr, die nicht aus "
            "Marktplatz-Abrechnungen stammen — z.B. das Vorjahr vor accounti oder "
            "eigene Rechnungen; zählen für die Lieferschwelle (§ 3c Abs. 4 UStG)"
        ),
    )
    paypal_kontobezeichnung: str = Field(
        default="PPLXLULL/PAYPAL", description="Feld :25: im MT940 (BIC/Konto)"
    )
    marktplaetze: dict[str, Marktplatzkonten] = Field(
        default_factory=lambda: {
            name: Marktplatzkonten.model_validate(werte)
            for name, werte in _STANDARD_MARKTPLAETZE.items()
        }
    )

    def marktplatz(self, name: str) -> Marktplatzkonten:
        return self.marktplaetze[name]


def _fehlertext(fehler: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(x) for x in f['loc'])}: {f['msg']}" for f in fehler.errors()
    )


def _abschnitt(pfad: Path, name: str) -> Any:
    if not pfad.is_file():
        return None
    daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    return daten.get(name) if isinstance(daten, dict) else None


def lade_integrationen(pfad: str | Path = STANDARD_PFAD) -> Integrationen:
    """Liest den Abschnitt ``integrationen``; fehlende Werte bleiben Standard."""
    pfad = Path(pfad)
    abschnitt = _abschnitt(pfad, "integrationen")
    werte = dict(abschnitt) if isinstance(abschnitt, dict) else {}
    eigene = werte.pop("marktplaetze", None) or {}
    try:
        if not isinstance(eigene, dict):
            msg = f"{pfad}: integrationen.marktplaetze muss Name → Konten zuordnen"
            raise KonfigurationError(msg)
        marktplaetze = {}
        for name in {*_STANDARD_MARKTPLAETZE, *eigene}:
            basis = dict(_STANDARD_MARKTPLAETZE.get(name, {}))
            basis.update(eigene.get(name) or {})
            marktplaetze[name] = Marktplatzkonten.model_validate(basis)
        return Integrationen.model_validate({**werte, "marktplaetze": marktplaetze})
    except ValidationError as fehler:
        msg = f"{pfad}: Abschnitt 'integrationen': {_fehlertext(fehler)}"
        raise KonfigurationError(msg) from fehler


def lade_steuerangaben(pfad: str | Path = STANDARD_PFAD) -> tuple[bool, str]:
    """(OSS-registriert?, Land des Firmensitzes) aus ``mandant``, nachsichtig."""
    mandant = _abschnitt(Path(pfad), "mandant")
    if not isinstance(mandant, dict):
        return False, "DE"
    anschrift = mandant.get("anschrift")
    land = anschrift.get("land") if isinstance(anschrift, dict) else None
    return bool(mandant.get("oss", False)), str(land or "DE").upper()


@dataclass
class Kontext:
    """Alles, was Importlauf und Abgleich über den Mandanten wissen müssen."""

    einstellungen: Integrationen = field(default_factory=Integrationen)
    buchhaltung: Buchhaltung = field(default_factory=Buchhaltung)
    oss_registriert: bool = False
    firmen_land: str = "DE"


def lade_kontext(pfad: str | Path = STANDARD_PFAD) -> Kontext:
    """Abschnitte ``integrationen`` und ``buchhaltung``, OSS-Angaben aus ``mandant``."""
    oss, land = lade_steuerangaben(pfad)
    return Kontext(
        einstellungen=lade_integrationen(pfad),
        buchhaltung=lade_buchhaltung(pfad),
        oss_registriert=oss,
        firmen_land=land,
    )
