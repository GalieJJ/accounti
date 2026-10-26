"""Abschnitt ``integrationen`` in ``config/accounti.yaml`` — optional, mit Standards.

Die Kontenvorgaben folgen dem SKR03. Die Verrechnungskonten der Marktplätze
(1361–1363) und das PayPal-Konto (1210) sind keine Standardkonten des Kontenrahmens
und müssen im Kanzleiprogramm angelegt bzw. hier angepasst werden. Für SKR04 sind
alle Konten zu überschreiben — außer den OSS- und Kursdifferenzkonten, deren
Vorgabe dem Kontenrahmen aus ``buchhaltung.kontenrahmen`` folgt.

OSS (Fernverkäufe an Privatkunden im übrigen Gemeinschaftsgebiet, § 3c UStG,
Meldung nach § 18j UStG): die Meldung ordnet das Bestimmungsland über das
Erlöskonto zu — je Land ein eigenes Konto aus ``oss_erloes_konten`` (DATEV-Bereich
„Erlöse aus im anderen EU-Land steuerpflichtigen Lieferungen“ SKR03 8320–8329,
SKR04 4320–4329; Kontenrahmen 2026), ermäßigte Sätze aus ``oss_erloes_ermaessigt``.
Die Umsatzsteuer des anderen Lands geht auf das DATEV-Sammelkonto „Umsatzsteuer aus
im anderen EU-Land steuerpflichtigen Lieferungen“ (SKR03 1767, SKR04 3817), das Land
steht im Buchungstext; ``oss_ust_konten`` legt einzelne Länder auf eigene Konten.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from accounti.konfiguration import (
    STANDARD_PFAD,
    Buchhaltung,
    KonfigurationError,
    lade_buchhaltung,
)
from accounti.steuer.eu_steuersaetze import ist_oss_land
from accounti.steuer.umsatzsteuer import (
    OSS_ERLOES_KONTEN_SKR03,
    OSS_ERLOES_KONTEN_SKR04,
    OSS_UST_KONTO_SKR03,
    OSS_UST_KONTO_SKR04,
)

UStModus = Literal["vorsteuer", "13b", "ohne"]


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
    ust_gebuehren: UStModus | None = Field(
        default=None,
        description=(
            "Umsatzsteuer in den Gebühren: vorsteuer (Bericht brutto mit deutscher USt "
            "— Amazon seit 01.08.2024), 13b (Leistung aus dem Ausland, BU-Schlüssel "
            "bu_gebuehren), ohne (steuerfrei, z.B. PayPal); nicht eingestellt: "
            "ohne Vorsteuer zur Prüfung"
        ),
    )
    ust_werbung: UStModus | None = Field(
        default=None, description="wie ust_gebuehren, für Werbekosten"
    )
    bu_gebuehren: int | None = Field(
        default=None, description="BU-Schlüssel der Gebühren bei ust_gebuehren: 13b"
    )
    bu_werbung: int | None = Field(
        default=None, description="BU-Schlüssel der Werbung bei ust_werbung: 13b"
    )
    bank_stichworte: list[str] = Field(
        default_factory=list, description="Merkmale des Bankeingangs der Auszahlung"
    )
    lager_nur_inland: bool = Field(
        default=False,
        description=(
            "Versand durch den Marktplatz (FBA) nur aus Lagern im Land des "
            "Firmensitzes, kein Pan-EU/CEE — dann gilt ein fehlendes Abgangsland "
            "als Inland"
        ),
    )

    def konto_fuer_gebuehr(self, art: str) -> str:
        return {
            "verkauf": self.verkaufsgebuehr,
            "versand": self.versandgebuehr,
            "lager": self.lagergebuehr,
            "zahlung": self.zahlungsgebuehr,
        }.get(art, self.sonstige_gebuehr)


_STANDARD_MARKTPLAETZE: dict[str, dict[str, Any]] = {
    # Amazon EU S.à r.l. berechnet deutschen Händlern seit 01.08.2024 deutsche USt
    # auf Verkaufs-, Versand-, Lager- und Abogebühren; Werbung rechnet sie nicht ab
    "amazon": {
        "verrechnungskonto": "1361",
        "bank_stichworte": ["AMAZON"],
        "ust_gebuehren": "vorsteuer",
    },
    "ebay": {"verrechnungskonto": "1362", "bank_stichworte": ["EBAY"]},
    "shopify": {
        "verrechnungskonto": "1363",
        "verkaufsgebuehr": "4970",
        "bank_stichworte": ["SHOPIFY"],
    },
    # PayPal-Gebühren: Finanzdienstleistung, steuerfrei (§ 4 Nr. 8 UStG)
    "paypal": {
        "verrechnungskonto": "1210",
        "verkaufsgebuehr": "4970",
        "bank_stichworte": ["PAYPAL"],
        "ust_gebuehren": "ohne",
        "ust_werbung": "ohne",
    },
}


# DATEV-Kontenrahmen 2026: OSS-Erlöse je Land (bisherige Vorgabe, acht Länder), das
# Sammelkonto für die Umsatzsteuer des anderen EU-Lands und die Konten für
# Kursdifferenzen (Aufwand, Ertrag aus der Währungsumrechnung: SKR03 2150/2660,
# SKR04 6880/4840)
KONTEN_STANDARD: dict[str, dict[str, Any]] = {
    "SKR03": {
        "oss_erloes_konten": OSS_ERLOES_KONTEN_SKR03,
        "oss_ust_konto": OSS_UST_KONTO_SKR03,
        "kursdifferenz_aufwand": "2150",
        "kursdifferenz_ertrag": "2660",
    },
    "SKR04": {
        "oss_erloes_konten": OSS_ERLOES_KONTEN_SKR04,
        "oss_ust_konto": OSS_UST_KONTO_SKR04,
        "kursdifferenz_aufwand": "6880",
        "kursdifferenz_ertrag": "4840",
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
    auszahlung_toleranz_prozent: Decimal = Field(
        default=Decimal("2"),
        ge=0,
        le=10,
        description=(
            "Fremdwährung: so weit darf der Bankbetrag von der umgerechneten "
            "Auszahlung abweichen (Kurs der Bank ≠ Kurs der Abrechnung); die "
            "Differenz geht auf die Kursdifferenzkonten"
        ),
    )
    kursdifferenz_aufwand: str = Field(
        default="2150", description="Aufwendungen aus der Währungsumrechnung"
    )
    kursdifferenz_ertrag: str = Field(
        default="2660", description="Erträge aus der Währungsumrechnung"
    )
    oss_erloes_konten: dict[str, str] = Field(
        default_factory=lambda: dict(KONTEN_STANDARD["SKR03"]["oss_erloes_konten"]),
        description=(
            "Land → OSS-Erlöskonto zum Normalsatz; ergänzt die Vorgabe des "
            "Kontenrahmens (acht Länder) — ohne Konto geht ein Fernverkauf zur "
            "Prüfung und nicht in die OSS-Meldung"
        ),
    )
    oss_ust_konto: str = Field(
        default="1767",
        description="Umsatzsteuer aus im anderen EU-Land steuerpflichtigen Lieferungen",
    )
    oss_ust_konten: dict[str, str] = Field(
        default_factory=dict, description="Land → eigenes OSS-Umsatzsteuerkonto"
    )
    ermaessigte_artikel: list[str] = Field(
        default_factory=list, description="SKUs mit ermäßigtem Steuersatz"
    )
    oss_erloes_ermaessigt: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Land → Erlöskonto für OSS-Umsätze zum ermäßigten Satz (anzulegen); "
            "ohne Konto gehen sie zur Prüfung und nicht in die OSS-Meldung"
        ),
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

    def oss_ust_konto_fuer(self, land: str) -> str:
        return self.oss_ust_konten.get(land.upper(), self.oss_ust_konto)

    @model_validator(mode="after")
    def _oss_konten(self) -> Integrationen:
        """Ein OSS-Erlöskonto gehört zu genau einem Land und Satz — die Meldung
        liest das Bestimmungsland aus dem Konto."""
        self.oss_erloes_konten = {
            k.upper(): v for k, v in self.oss_erloes_konten.items()
        }
        self.oss_erloes_ermaessigt = {
            k.upper(): v for k, v in self.oss_erloes_ermaessigt.items()
        }
        self.oss_ust_konten = {k.upper(): v for k, v in self.oss_ust_konten.items()}
        laender = [*self.oss_erloes_konten, *self.oss_erloes_ermaessigt]
        laender += list(self.oss_ust_konten)
        fremd = sorted({land for land in laender if not ist_oss_land(land)})
        if fremd:
            msg = f"OSS-Konten für {', '.join(fremd)}: kein EU-Land im OSS-Verfahren"
            raise ValueError(msg)
        gesehen: dict[str, str] = {}
        for art, konten in (
            ("oss_erloes_konten", self.oss_erloes_konten),
            ("oss_erloes_ermaessigt", self.oss_erloes_ermaessigt),
        ):
            for land, konto in konten.items():
                wer = f"{art}.{land}"
                if konto in gesehen:
                    msg = (
                        f"OSS-Erlöskonto {konto} doppelt ({gesehen[konto]}, {wer}) — "
                        "die Meldung erkennt Land und Satz am Konto"
                    )
                    raise ValueError(msg)
                gesehen[konto] = wer
        return self


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
    rahmen = lade_buchhaltung(pfad).kontenrahmen.upper()
    standard = KONTEN_STANDARD.get(rahmen, KONTEN_STANDARD["SKR03"])
    oss = werte.get("oss_erloes_konten") or {}
    if not isinstance(oss, dict):
        msg = f"{pfad}: integrationen.oss_erloes_konten muss Land → Konto zuordnen"
        raise KonfigurationError(msg)
    werte = {
        **{k: v for k, v in standard.items() if k != "oss_erloes_konten"},
        **werte,
        # eigene Länder ergänzen die Vorgabe; ``LAND: null`` nimmt ein Land heraus
        "oss_erloes_konten": {
            land: str(konto)
            for land, konto in {
                **standard["oss_erloes_konten"],
                **{str(k).upper(): v for k, v in oss.items()},
            }.items()
            if konto is not None
        },
    }
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
