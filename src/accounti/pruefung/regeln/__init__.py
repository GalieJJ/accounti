"""Prüfregeln (Spec 4.1): benannt, mit Schweregrad, Schwellen aus der Konfiguration.

Eine Regel ist ein Objekt mit ``name``, ``kategorie``, ``schwere`` (Standard),
``beschreibung``, einem Pydantic-Modell ``Parameter`` (Schwellen mit Standardwerten)
und ``pruefe(kontext, parameter) -> list[Befund]``. Sie **liest nur** — ein Lauf
ändert nichts an der Datenbank. Eigene Regeln trägt ``registriere_pruefregel`` ein;
eine Regel gleichen Namens wird ersetzt.

    from accounti.pruefung.regeln import Kontext, registriere_pruefregel

    class Grossbetrag:
        name = "grossbetrag"; kategorie = Kategorie.ORDNUNG
        schwere = Schwere.HINWEIS; beschreibung = "Buchungen über 10.000 €"
        class Parameter(BaseModel):
            ab: Decimal = Decimal("10000")
        def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]: ...

    registriere_pruefregel(Grossbetrag())
"""

from __future__ import annotations

import re
from calendar import monthrange
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from accounti.belege.archiv import BelegArchiv
from accounti.belege.ocr import OCREngine
from accounti.konfiguration import Buchhaltung, KonfigurationError
from accounti.kontakte.dienst import Partnerdaten
from accounti.models import (
    Beleg,
    Buchungssatz,
    Kontakt,
    OffenerPosten,
    Transaktion,
)
from accounti.models.pruefung import Befund, Kategorie, Schwere
from accounti.pruefung.einstellungen import PruefEinstellungen

_ZEITRAUM = re.compile(r"^(\d{4})(?:-(0[1-9]|1[0-2]))?$")


class PruefungError(ValueError):
    """Der Prüflauf ist so nicht möglich (Zeitraum, unbekannte Regel …)."""


def zeitraum(text: str | None) -> tuple[date | None, date | None]:
    """``JJJJ-MM`` → Monat, ``JJJJ`` → Jahr, ``None`` → alles."""
    if text is None:
        return None, None
    m = _ZEITRAUM.match(text.strip())
    if m is None:
        raise PruefungError(f"Zeitraum {text!r}: JJJJ-MM oder JJJJ, z.B. 2026-08")
    jahr = int(m.group(1))
    if m.group(2) is None:
        return date(jahr, 1, 1), date(jahr, 12, 31)
    monat = int(m.group(2))
    return date(jahr, monat, 1), date(jahr, monat, monthrange(jahr, monat)[1])


class Pruefregel(Protocol):
    name: str
    kategorie: Kategorie
    schwere: Schwere
    beschreibung: str

    @property
    def Parameter(self) -> type[BaseModel]: ...  # noqa: N802 — Schwellen der Regel

    def pruefe(self, k: Kontext, p: Any) -> list[Befund]: ...


PRUEFREGELN: dict[str, Pruefregel] = {}


def registriere_pruefregel(regel: Pruefregel) -> None:
    """Trägt die Regel ein; eine Regel gleichen Namens wird ersetzt."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", regel.name):
        raise PruefungError(f"Regelname {regel.name!r}: klein, Ziffern, Unterstrich")
    PRUEFREGELN[regel.name] = regel


@dataclass
class Kontext:
    """Alles, was eine Regel lesen darf — mit einmal geladenen Beständen."""

    session: Session
    einstellungen: PruefEinstellungen
    buchhaltung: Buchhaltung
    stichtag: date
    von: date | None = None
    bis: date | None = None
    firma: Partnerdaten | None = None
    firma_steuernummer: str | None = None
    archiv: BelegArchiv | None = None
    ocr: OCREngine | None = None

    def im_zeitraum(self, tag: date | None) -> bool:
        if tag is None:
            return self.von is None
        return (self.von is None or tag >= self.von) and (
            self.bis is None or tag <= self.bis
        )

    @cached_property
    def buchungen(self) -> list[Buchungssatz]:
        from accounti.db.repository import lade_buchungen

        return lade_buchungen(self.session)

    @cached_property
    def belege(self) -> dict[UUID, Beleg]:
        from accounti.db.repository import lade_belege

        return {b.id: b for b in lade_belege(self.session)}

    @cached_property
    def transaktionen(self) -> dict[UUID, Transaktion]:
        from accounti.db.repository import lade_transaktionen

        return {t.id: t for t in lade_transaktionen(self.session)}

    @cached_property
    def kontakte(self) -> dict[UUID, Kontakt]:
        from accounti.db.repository import lade_kontakte

        return {k.id: k for k in lade_kontakte(self.session)}

    @cached_property
    def posten(self) -> list[OffenerPosten]:
        from accounti.db.repository import lade_posten

        return lade_posten(self.session)

    def kontakt_zum_beleg(self, beleg: Beleg) -> Kontakt | None:
        if beleg.kontakt_id is not None and beleg.kontakt_id in self.kontakte:
            return self.kontakte[beleg.kontakt_id]
        for p in self.posten:
            if p.beleg_id == beleg.id:
                return self.kontakte.get(p.kontakt_id)
        return None

    def kontakt_zum_konto(self, konto: str) -> Kontakt | None:
        return next(
            (
                k
                for k in self.kontakte.values()
                if konto in (k.kreditor_konto, k.debitor_konto)
            ),
            None,
        )


@dataclass
class Pruefbericht:
    von: date | None
    bis: date | None
    stichtag: date
    regeln: list[str] = field(default_factory=list)
    befunde: list[Befund] = field(default_factory=list)

    def anzahl(self, schwere: Schwere) -> int:
        return sum(1 for b in self.befunde if b.schwere is schwere)

    @property
    def fehler(self) -> bool:
        return self.anzahl(Schwere.FEHLER) > 0


def _lade_regeln() -> None:
    """Die eingebauten Regeln tragen sich beim Import ein."""
    from accounti.pruefung.regeln import (  # noqa: F401
        ordnung,
        richtigkeit,
        vollstaendigkeit,
        zeitgerechtheit,
    )


def _parameter(regel: Pruefregel, einstellungen: PruefEinstellungen) -> BaseModel:
    werte = einstellungen.regeln.get(regel.name, {})
    try:
        return regel.Parameter.model_validate(werte)
    except ValidationError as fehler:
        felder = "; ".join(
            f"{'.'.join(map(str, f['loc']))}: {f['msg']}" for f in fehler.errors()
        )
        msg = f"pruefung.regeln.{regel.name}: {felder}"
        raise KonfigurationError(msg) from fehler


def pruefe_konfiguration(einstellungen: PruefEinstellungen) -> None:
    """Unbekannte Regeln und falsche Schwellen sind Konfigurationsfehler."""
    _lade_regeln()
    bekannt = set(PRUEFREGELN)
    for wo, namen in (
        ("abgeschaltet", einstellungen.abgeschaltet),
        ("schwere", list(einstellungen.schwere)),
        ("regeln", list(einstellungen.regeln)),
    ):
        unbekannt = sorted(set(namen) - bekannt)
        if unbekannt:
            msg = (
                f"pruefung.{wo}: unbekannte Regel {', '.join(unbekannt)} "
                f"(vorhanden: {', '.join(sorted(bekannt))})"
            )
            raise KonfigurationError(msg)
    for regel in PRUEFREGELN.values():
        _parameter(regel, einstellungen)


def fuehre_regeln_aus(
    k: Kontext,
    namen: Sequence[str] | None = None,
    fortschritt: Callable[[str], None] | None = None,
) -> Pruefbericht:
    """Die genannten (sonst alle nicht abgeschalteten) Regeln über den Zeitraum."""
    pruefe_konfiguration(k.einstellungen)
    if namen:
        unbekannt = [n for n in namen if n not in PRUEFREGELN]
        if unbekannt:
            msg = (
                f"Unbekannte Regel {', '.join(unbekannt)} "
                f"(vorhanden: {', '.join(sorted(PRUEFREGELN))})"
            )
            raise PruefungError(msg)
        regeln = [PRUEFREGELN[n] for n in namen]
    else:
        regeln = [
            r
            for name, r in sorted(PRUEFREGELN.items())
            if name not in k.einstellungen.abgeschaltet
        ]
    bericht = Pruefbericht(k.von, k.bis, k.stichtag)
    for regel in regeln:
        if fortschritt is not None:
            fortschritt(regel.name)
        schwere = k.einstellungen.schwere.get(regel.name)
        befunde = regel.pruefe(k, _parameter(regel, k.einstellungen))
        if schwere is not None:
            befunde = [b.model_copy(update={"schwere": schwere}) for b in befunde]
        bericht.regeln.append(regel.name)
        bericht.befunde.extend(befunde)
    bericht.befunde.sort(key=lambda b: (-b.schwere.rang, b.kategorie.value, b.regel))
    return bericht


def befund(
    regel: Pruefregel,
    objekt_typ: str,
    objekt_id: object,
    text: str,
    *,
    schwere: Schwere | None = None,
    **felder: Any,
) -> Befund:
    return Befund(
        regel=regel.name,
        kategorie=regel.kategorie,
        schwere=schwere or regel.schwere,
        objekt_typ=objekt_typ,
        objekt_id=str(objekt_id),
        text=text,
        **felder,
    )


__all__ = [
    "PRUEFREGELN",
    "Kontext",
    "Pruefbericht",
    "PruefungError",
    "Pruefregel",
    "befund",
    "fuehre_regeln_aus",
    "pruefe_konfiguration",
    "registriere_pruefregel",
    "zeitraum",
]
