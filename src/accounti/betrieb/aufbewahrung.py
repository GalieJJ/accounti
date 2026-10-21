"""Aufbewahrungsfristen und Löschkonzept — die Frist kennen, nichts von selbst löschen.

Stand 20.10.2026 (Quellen in ``docs/betrieb.md``):

- § 147 Abs. 3 AO seit dem BEG IV (ab 01.01.2025): **10 Jahre** für Bücher,
  Aufzeichnungen, Inventare, Jahresabschlüsse, Lageberichte, Eröffnungsbilanz und
  Organisationsunterlagen (Abs. 1 Nr. 1), **8 Jahre** für Buchungsbelege (Nr. 4),
  **6 Jahre** für Handels- und Geschäftsbriefe und sonstige Unterlagen (Nr. 2, 3, 5).
  Die 8 Jahre gelten für alle Belege, deren Frist nach altem Recht am 31.12.2024 noch
  lief (Art. 97 § 19a Abs. 2 EGAO); **Kreditinstitute, beaufsichtigte Versicherungen
  und Wertpapierinstitute behalten 10 Jahre** (Abs. 3).
- § 14b Abs. 1 UStG: Rechnungen **8 Jahre**.
- Beginn: Schluss des Kalenderjahres, in dem die Unterlage entstand bzw. die letzte
  Eintragung gemacht wurde (§ 147 Abs. 4 AO, § 14b Abs. 1 Satz 3 UStG).
- Kein Ablauf, solange die Unterlagen für eine Steuer von Bedeutung sind, deren
  Festsetzungsfrist noch läuft (§ 147 Abs. 3 Satz 3 AO) — das prüft ein Mensch.

accounti löscht nichts: Der Bericht zeigt, was **frühestens** ausgesondert werden
dürfte. Das Belegarchiv hat bewusst keinen Löschpfad.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import Table, func, inspect, select
from sqlalchemy.orm import Session

from accounti.db import Base, registriere_tabellen


class Unterlage(str, enum.Enum):
    BUCH = "buch"  # Bücher, Aufzeichnungen, Journale, Protokolle
    JAHRESABSCHLUSS = "jahresabschluss"
    BUCHUNGSBELEG = "buchungsbeleg"
    RECHNUNG = "rechnung"
    HANDELSBRIEF = "handelsbrief"
    SONSTIGE = "sonstige"


@dataclass(frozen=True)
class Frist:
    unterlage: Unterlage
    jahre: int
    grundlage: str


_NR1 = "§ 147 Abs. 1 Nr. 1, Abs. 3 AO"
FRISTEN: dict[Unterlage, Frist] = {
    Unterlage.BUCH: Frist(Unterlage.BUCH, 10, _NR1),
    Unterlage.JAHRESABSCHLUSS: Frist(Unterlage.JAHRESABSCHLUSS, 10, _NR1),
    Unterlage.BUCHUNGSBELEG: Frist(
        Unterlage.BUCHUNGSBELEG, 8, "§ 147 Abs. 1 Nr. 4, Abs. 3 AO (BEG IV)"
    ),
    Unterlage.RECHNUNG: Frist(Unterlage.RECHNUNG, 8, "§ 14b Abs. 1 UStG"),
    Unterlage.HANDELSBRIEF: Frist(
        Unterlage.HANDELSBRIEF, 6, "§ 147 Abs. 1 Nr. 2, 3, Abs. 3 AO"
    ),
    Unterlage.SONSTIGE: Frist(Unterlage.SONSTIGE, 6, "§ 147 Abs. 1 Nr. 5, Abs. 3 AO"),
}

# Art. 97 § 19a Abs. 3 EGAO: für Institute bleibt es bei der alten Fassung
INSTITUT = Frist(
    Unterlage.BUCHUNGSBELEG, 10, "§ 147 Abs. 3 AO a. F. (Art. 97 § 19a Abs. 3 EGAO)"
)


def frist(unterlage: Unterlage, institut: bool = False) -> Frist:
    if institut and unterlage is Unterlage.BUCHUNGSBELEG:
        return INSTITUT
    return FRISTEN[unterlage]


def frist_ende(unterlage: Unterlage, entstanden: date, institut: bool = False) -> date:
    """Letzter Tag der Aufbewahrung: Jahresende des Entstehungsjahres + Frist."""
    return date(entstanden.year + frist(unterlage, institut).jahre, 12, 31)


def aussonderbar_ab(
    unterlage: Unterlage, entstanden: date, institut: bool = False
) -> date:
    """Frühester Tag, an dem die Unterlage ausgesondert werden dürfte."""
    return date(frist_ende(unterlage, entstanden, institut).year + 1, 1, 1)


@dataclass(frozen=True)
class Zeile:
    bezeichnung: str
    frist: Frist
    aeltester: date | None
    aussonderbar: int
    gesamt: int


# Tabelle, Spalte mit dem Entstehungsdatum, Bezeichnung, Unterlage
BESTAND: list[tuple[str, str, str, Unterlage]] = [
    ("buchungssaetze", "datum", "Buchungen", Unterlage.BUCH),
    ("belege", "eingegangen_am", "Belege", Unterlage.BUCHUNGSBELEG),
    ("ustid_pruefungen", "zeitpunkt", "USt-IdNr.-Protokoll", Unterlage.BUCH),
    ("steuermeldung_protokolle", "zeitpunkt", "Übermittlungsprotokoll", Unterlage.BUCH),
    ("zahlungslauf_protokoll", "zeitpunkt", "Zahlungslauf-Protokoll", Unterlage.BUCH),
    ("abschlussprotokoll", "zeitpunkt", "Abschlussprotokoll", Unterlage.BUCH),
    ("kassenbuch", "datum", "Kassenbuch", Unterlage.BUCH),
]


def _als_datum(wert: object) -> date | None:
    if isinstance(wert, datetime):
        return wert.date()
    return wert if isinstance(wert, date) else None


def _zeile(
    s: Session,
    tabelle: Table,
    spaltenname: str,
    bezeichnung: str,
    f: Frist,
    stichtag: date,
) -> Zeile:
    spalte = tabelle.c[spaltenname]
    # entstanden vor dem 1.1. von (Stichtagsjahr − Frist) → Frist am Stichtag abgelaufen
    grenze = date(stichtag.year - f.jahre, 1, 1)
    gesamt = s.execute(select(func.count()).select_from(tabelle)).scalar() or 0
    aeltester = _als_datum(s.execute(select(func.min(spalte))).scalar())
    abgelaufen = (
        s.execute(
            select(func.count()).select_from(tabelle).where(spalte < grenze)
        ).scalar()
        or 0
    )
    return Zeile(bezeichnung, f, aeltester, abgelaufen, gesamt)


def bericht(s: Session, stichtag: date, institut: bool = False) -> list[Zeile]:
    """Was am Stichtag frühestens ausgesondert werden dürfte — nur lesend."""
    registriere_tabellen()
    vorhanden = set(inspect(s.get_bind()).get_table_names())
    zeilen = []
    for name, spalte, bezeichnung, unterlage in BESTAND:
        tabelle = Base.metadata.tables.get(name)
        if tabelle is None or name not in vorhanden:
            continue
        zeilen.append(
            _zeile(
                s, tabelle, spalte, bezeichnung, frist(unterlage, institut), stichtag
            )
        )
    return zeilen
