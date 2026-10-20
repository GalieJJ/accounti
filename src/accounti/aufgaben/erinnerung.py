"""Erinnerungen: Stufen in Tagen nach Fälligkeit, die letzte eskaliert.

Standard ``[0, 3, 7]``: am Fälligkeitstag „fällig“, drei Tage später die erste
Erinnerung, sieben Tage später die letzte Stufe — mit ``eskalation_an`` eine
Eskalation. Die Stufe einer Aufgabe ergibt sich allein aus Fälligkeit und Stichtag;
gespeichert wird nur, welche Stufe zuletzt gemeldet wurde. Fiel ein Lauf aus, meldet
der nächste einmal die erreichte Stufe, statt Erinnerungen nachzuholen.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from accounti.aufgaben.einstellungen import AufgabenEinstellungen, Erinnerungsplan
from accounti.models.aufgaben import Aufgabe


def stufe_am(aufgabe: Aufgabe, plan: Erinnerungsplan, stichtag: date) -> int:
    """Anzahl der bis zum Stichtag erreichten Stufen (0 = noch nicht fällig)."""
    if aufgabe.faellig_am is None:
        return 0
    tage = (stichtag - aufgabe.faellig_am).days
    return sum(1 for schwelle in plan.stufen if tage >= schwelle)


@dataclass
class Erinnerung:
    aufgabe: Aufgabe
    stufe: int
    ueberfaellig_tage: int
    eskaliert_an: str | None = None  # gesetzt, wenn diese Meldung eskaliert

    @property
    def bezeichnung(self) -> str:
        tage = self.ueberfaellig_tage
        if tage == 0:
            zusatz = "fällig heute"
        else:
            zusatz = "1 Tag überfällig" if tage == 1 else f"{tage} Tage überfällig"
        if self.eskaliert_an:
            return f"eskaliert an {self.eskaliert_an} · {zusatz}"
        if self.stufe <= 1:
            return zusatz
        return f"{self.stufe - 1}. Erinnerung · {zusatz}"


def faellige_erinnerungen(
    aufgaben: Iterable[Aufgabe], einstellungen: AufgabenEinstellungen, stichtag: date
) -> list[Erinnerung]:
    """Aktive Aufgaben, die seit der letzten Meldung eine neue Stufe erreicht haben."""
    ergebnis = []
    for a in aufgaben:
        if not a.aktiv or a.faellig_am is None:
            continue
        plan = einstellungen.erinnerung.plan(a.art)
        stufe = stufe_am(a, plan, stichtag)
        if stufe <= a.erinnerungsstufe:
            continue
        letzte = stufe == len(plan.stufen)
        ergebnis.append(
            Erinnerung(
                a,
                stufe,
                (stichtag - a.faellig_am).days,
                plan.eskalation_an if letzte else None,
            )
        )
    return ergebnis
