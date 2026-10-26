"""Abschnitt ``anlagen`` in ``config/accounti.yaml`` — optional.

Ohne Abschnitt gelten die Konten des Kontenrahmens aus ``buchhaltung.kontenrahmen``
(DATEV SKR03 bzw. SKR04, Stand 2026) und der mitgelieferte Rechtsstand.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from accounti.anlagen.rechtsstand import Rechtsstand, lade_rechtsstand
from accounti.konfiguration import STANDARD_PFAD, KonfigurationError, lade_buchhaltung
from accounti.models.anlagen import AfaArt, Anlagegut


class AnlagenKonten(BaseModel):
    afa: str  # Abschreibungen auf Sachanlagen
    afa_kfz: str
    afa_immateriell: str
    gwg_afa: str  # Sofortabschreibung GWG
    sammelposten_afa: str
    gwg: str  # Anlagekonto GWG
    sammelposten: str  # Anlagekonto Sammelposten
    abgang_buchverlust: str  # Restbuchwert bei Buchverlust
    abgang_buchgewinn: str  # Restbuchwert bei Buchgewinn
    erloes_buchverlust: str  # 19 % USt
    erloes_buchgewinn: str
    erloes_buchverlust_ohne_ust: str
    erloes_buchgewinn_ohne_ust: str


# DATEV-Kontenrahmen „Gültig für 2026“ (Art.-Nr. 11174 SKR 03, 11175 SKR 04)
STANDARDS: dict[str, dict[str, Any]] = {
    "SKR03": {
        "konten": {
            "afa": "4830",
            "afa_kfz": "4832",
            "afa_immateriell": "4822",
            "gwg_afa": "4855",
            "sammelposten_afa": "4862",
            "gwg": "0480",
            "sammelposten": "0485",
            "abgang_buchverlust": "2310",
            "abgang_buchgewinn": "2315",
            "erloes_buchverlust": "8801",
            "erloes_buchgewinn": "8820",
            "erloes_buchverlust_ohne_ust": "8800",
            "erloes_buchgewinn_ohne_ust": "8829",
        },
        "kfz_konten": ["0320", "0350"],
        "immaterielle_konten": [["0010", "0049"]],
        "anlagekonten": [["0010", "0499"]],
    },
    "SKR04": {
        "konten": {
            "afa": "6220",
            "afa_kfz": "6222",
            "afa_immateriell": "6200",
            "gwg_afa": "6260",
            "sammelposten_afa": "6264",
            "gwg": "0670",
            "sammelposten": "0675",
            "abgang_buchverlust": "6895",
            "abgang_buchgewinn": "4855",
            "erloes_buchverlust": "6885",
            "erloes_buchgewinn": "4845",
            "erloes_buchverlust_ohne_ust": "6889",
            "erloes_buchgewinn_ohne_ust": "4849",
        },
        "kfz_konten": ["0520", "0540"],
        "immaterielle_konten": [["0010", "0199"]],
        "anlagekonten": [["0010", "0799"]],
    },
}


def _in(konto: str, bereiche: list[tuple[str, str]]) -> bool:
    if not konto.isdigit():
        return False
    return any(int(von) <= int(konto) <= int(bis) for von, bis in bereiche)


class AnlagenEinstellungen(BaseModel):
    kontenrahmen: str = "SKR03"
    konten: AnlagenKonten
    kfz_konten: list[str] = Field(default_factory=list)
    immaterielle_konten: list[tuple[str, str]] = Field(default_factory=list)
    anlagekonten: list[tuple[str, str]] = Field(default_factory=list)
    rechtsstand_datei: str | None = Field(default=None, alias="rechtsstand")
    wirtschaftsjahr_beginn: date | None = Field(
        default=None, description="aus datev.wirtschaftsjahr_beginn (Tag und Monat)"
    )

    model_config = {"populate_by_name": True}

    def rechtsstand(self) -> Rechtsstand:
        return lade_rechtsstand(self.rechtsstand_datei)

    def afa_abschnitt(self, bis_monat: int) -> tuple[int, int]:
        """(erster, letzter Monat) des Teils eines Kalenderjahres, in dem ``bis_monat``
        liegt — bei abweichendem Wirtschaftsjahr gehört ein Kalenderjahr zu zwei
        Wirtschaftsjahren (Januar bis WJ-Ende, danach bis Dezember), sonst (1, 12).

        Die AfA steht je Wirtschaftsjahr zu (§ 7 Abs. 1 Satz 1 und 4 EStG); der
        AfA-Lauf rechnet je Abschnitt, damit das erste Wirtschaftsjahr in accounti nicht
        die AfA des Vor-WJ mitbucht. Beginnt das Wirtschaftsjahr nicht am Monatsersten,
        zählt der Monat seines Endes zum endenden Wirtschaftsjahr."""
        from accounti.abschluss.konfiguration import wirtschaftsjahr

        ende = wirtschaftsjahr(2001, self.wirtschaftsjahr_beginn).bis.month
        return (1, ende) if bis_monat <= ende else (ende + 1, 12)

    def ist_anlagekonto(self, konto: str) -> bool:
        return _in(konto, self.anlagekonten)

    def ist_kfz(self, anlage: Anlagegut) -> bool:
        return anlage.konto in self.kfz_konten or anlage.afa_art is AfaArt.E_FAHRZEUG

    def afa_konto(self, anlage: Anlagegut) -> str:
        """Aufwandskonto: am Anlagegut hinterlegt, sonst nach Art und Anlagekonto."""
        if anlage.afa_konto:
            return anlage.afa_konto
        if anlage.afa_art is AfaArt.GWG:
            return self.konten.gwg_afa
        if anlage.afa_art is AfaArt.SAMMELPOSTEN:
            return self.konten.sammelposten_afa
        if anlage.immateriell or _in(anlage.konto, self.immaterielle_konten):
            return self.konten.afa_immateriell
        if self.ist_kfz(anlage):
            return self.konten.afa_kfz
        return self.konten.afa


def lade_anlagen(pfad: str | Path = STANDARD_PFAD) -> AnlagenEinstellungen:
    from accounti.abschluss.konfiguration import lade_wirtschaftsjahr_beginn

    pfad = Path(pfad)
    kontenrahmen = lade_buchhaltung(pfad).kontenrahmen.upper()
    standard = STANDARDS.get(kontenrahmen, STANDARDS["SKR03"])
    abschnitt: Any = None
    if pfad.is_file():
        daten: Any = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
        abschnitt = daten.get("anlagen") if isinstance(daten, dict) else None
    eigene: dict[str, Any] = dict(abschnitt) if isinstance(abschnitt, dict) else {}
    try:
        konten = eigene.pop("konten", None) or {}
        if not isinstance(konten, dict):
            raise TypeError("'konten' muss eine Zuordnung sein")
        werte = {
            **standard,
            **eigene,
            "konten": {**standard["konten"], **konten},
            "kontenrahmen": kontenrahmen,
            "wirtschaftsjahr_beginn": lade_wirtschaftsjahr_beginn(pfad),
        }
        return AnlagenEinstellungen.model_validate(werte)
    except (ValidationError, TypeError) as fehler:
        msg = f"{pfad}: Abschnitt 'anlagen': {fehler}"
        raise KonfigurationError(msg) from fehler
