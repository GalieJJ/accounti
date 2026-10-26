"""Kontonummern prüfen und benennen — gemeinsam für CLI und Browser (Baustein 10b)."""

from __future__ import annotations

import re
from decimal import Decimal
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from accounti.abschluss.kontenrahmen import Kontenrahmen
    from accounti.pruefung.einstellungen import PruefEinstellungen

_KONTO = re.compile(r"^\d{4,8}$")


class KontoError(ValueError):
    """Keine gültige Kontonummer."""


def pruefe_kontonummer(konto: str, feld: str = "Konto") -> str:
    """4 bis 8 Ziffern (Sachkonten 4-stellig, Personenkonten 5-stellig, mehr bei
    erweiterten Kontenrahmen) — sonst ``KontoError``."""
    wert = (konto or "").strip()
    if not _KONTO.match(wert):
        raise KontoError(
            f"{feld}: {wert or '(leer)'} ist keine Kontonummer (4–8 Ziffern)"
        )
    return wert


def finanzkonto_fehler(
    soll: str, haben: str, betrag: Decimal, finanzkonto: str
) -> tuple[str, str] | None:
    """Ein Bankumsatz läuft über sein Finanzkonto — eine Ausgabe im Haben, eine
    Einnahme im Soll. Sonst stimmt der Bestand des Kontos in den Büchern nicht mehr mit
    dem Kontoauszug (Buchungen müssen richtig sein, § 146 Abs. 1 AO, § 239 Abs. 2
    HGB). ``(feld, meldung)`` bei einem Fehler, sonst ``None``."""
    if betrag < 0:
        feld, konto, art, seite = "haben", haben, "eine Ausgabe", "Haben"
    elif betrag > 0:
        feld, konto, art, seite = "soll", soll, "eine Einnahme", "Soll"
    else:
        return None
    if konto == finanzkonto:
        return None
    return feld, (
        f"Der Umsatz ist {art} über das Finanzkonto {finanzkonto} — {finanzkonto} "
        f"muss im {seite} stehen (sonst stimmt der Kontostand in den Büchern nicht "
        "mehr mit dem Kontoauszug)"
    )


@lru_cache(maxsize=8)
def _namen_der_datei(datei: str | None, kontenrahmen: str) -> dict[str, str]:
    from accounti.konfiguration import KonfigurationError
    from accounti.pruefung.einstellungen import PruefEinstellungen
    from accounti.pruefung.regeln.richtigkeit import _lade_konten

    try:
        konten = _lade_konten(
            PruefEinstellungen(kontenrahmen_datei=datei), kontenrahmen
        )
    except KonfigurationError:
        return {}
    return {
        str(nr): str(eintrag.get("name") or "")
        for nr, eintrag in konten.items()
        if isinstance(eintrag, dict)
    }


def kontobezeichnung(
    konto: str,
    kontenrahmen: Kontenrahmen | None = None,
    pruefung: PruefEinstellungen | None = None,
) -> str:
    """Bezeichnung aus dem Kontenrahmen (``namen``), sonst aus der Kontenrahmen-Datei
    der Prüfregeln (``pruefung/skr03.yaml`` bzw. ``pruefung.kontenrahmen_datei``),
    sonst leer — dann zeigt die Oberfläche nur die Nummer."""
    if kontenrahmen is not None:
        name = kontenrahmen.bezeichnung(konto)
        if name:
            return name
    datei = pruefung.kontenrahmen_datei if pruefung is not None else None
    rahmen = kontenrahmen.name if kontenrahmen is not None else "SKR03"
    return _namen_der_datei(str(datei) if datei else None, rahmen).get(konto, "")
