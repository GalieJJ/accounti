"""Aufbewahrungsfristen und Löschkonzept — die Frist kennen, nichts von selbst löschen.

Stand 20.10.2026 (Quellen in ``docs/betrieb.md``):

- § 147 Abs. 3 AO seit dem BEG IV (ab 01.01.2025): **10 Jahre** für Bücher,
  Aufzeichnungen, Inventare, Jahresabschlüsse, Lageberichte, Eröffnungsbilanz und
  Organisationsunterlagen (Abs. 1 Nr. 1), **8 Jahre** für Buchungsbelege (Nr. 4),
  **6 Jahre** für Handels- und Geschäftsbriefe und sonstige Unterlagen (Nr. 2, 3, 5).
  Die 8 Jahre gelten für alle Belege, deren Frist nach altem Recht am 31.12.2024 noch
  lief (Art. 97 § 19a Abs. 2 EGAO); **Kreditinstitute, beaufsichtigte Versicherungen
  und Wertpapierinstitute behalten 10 Jahre** (Abs. 3 i. d. F. des Gesetzes vom
  22.12.2025, BGBl. 2025 I Nr. 369: dauerhaft die Fassung vom 31.12.2024 — die
  zunächst ab 2026 vorgesehene Verkürzung wurde zurückgenommen).
- § 14b Abs. 1 UStG: Rechnungen **8 Jahre**.
- Beginn: Schluss des Kalenderjahres, in dem die Unterlage entstand bzw. die letzte
  Eintragung gemacht wurde (§ 147 Abs. 4 AO, § 14b Abs. 1 Satz 3 UStG). Bücher und
  Aufzeichnungen rechnet accounti **je Wirtschaftsjahr**: Die letzte Eintragung eines
  Wirtschaftsjahres (Abschlussbuchungen) liegt frühestens im Jahr nach seinem Ende —
  später, wenn der Abschluss (``abschluesse``) oder ein Monat des Wirtschaftsjahres
  (``periodenabschluesse``, Baustein 7) später festgeschrieben wurde; ein wieder
  geöffnetes Jahr oder ein wieder geöffneter Monat eines nicht abgeschlossenen Jahres
  läuft nicht ab (die letzte Eintragung steht aus). Den Zeitpunkt einzelner
  Buchungen kennt seit Baustein 7 das Journal — der Bericht wertet ihn nicht aus und
  bleibt bei dieser vorsichtigen Annahme.
- Journal, Buchungskorrekturen und Monatsabschlüsse sind Aufzeichnungen (10 Jahre).
  Das Journal ist eine Hash-Kette: Wer alte Einträge aussondert, kürzt sie — ``journal
  pruefen`` braucht danach einen Anker (``--kopf``) ab dem verbliebenen Anfang.
- Kein Ablauf, solange die Unterlagen für eine Steuer von Bedeutung sind, deren
  Festsetzungsfrist noch läuft (§ 147 Abs. 3 Satz 3 AO) — das prüft ein Mensch.

accounti löscht nichts: Der Bericht zeigt, was **frühestens** ausgesondert werden
dürfte. Das Belegarchiv hat bewusst keinen Löschpfad.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

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

# Art. 97 § 19a Abs. 3 EGAO (i. d. F. vom 22.12.2025): für Institute bleibt es
# dauerhaft bei der alten Fassung
INSTITUT = Frist(
    Unterlage.BUCHUNGSBELEG, 10, "§ 147 Abs. 3 AO a. F. (Art. 97 § 19a Abs. 3 EGAO)"
)


# BEG IV: die 8 Jahre für Buchungsbelege gelten ab dem 01.01.2025
BEG_IV_AB = date(2025, 1, 1)
VOR_BEG_IV = Frist(Unterlage.BUCHUNGSBELEG, 10, "§ 147 Abs. 3 AO a. F. (vor BEG IV)")


def frist(
    unterlage: Unterlage, institut: bool = False, stichtag: date | None = None
) -> Frist:
    if institut and unterlage is Unterlage.BUCHUNGSBELEG:
        return INSTITUT
    if (
        stichtag is not None
        and stichtag < BEG_IV_AB
        and unterlage is Unterlage.BUCHUNGSBELEG
    ):
        return VOR_BEG_IV
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
    # Baustein 7: das Journal nach dem Zeitpunkt des Vorgangs, Storno-Verweise nach
    # dem Storno-Datum, Monatsabschlüsse nach dem Festschreiben
    ("journal", "zeitpunkt", "Journal", Unterlage.BUCH),
    ("buchungskorrekturen", "datum", "Buchungskorrekturen", Unterlage.BUCH),
    ("periodenabschluesse", "geschlossen_am", "Periodenabschlüsse", Unterlage.BUCH),
]


def _als_datum(wert: object) -> date | None:
    if isinstance(wert, datetime):
        return wert.date()
    return wert if isinstance(wert, date) else None


def wirtschaftsjahr(tag: date, beginn: date | None = None) -> tuple[date, date]:
    """Beginn und Ende des Wirtschaftsjahres, in dem ``tag`` liegt (nur Tag und
    Monat von ``beginn`` zählen; ohne: Kalenderjahr)."""
    monat, erster = (beginn.month, beginn.day) if beginn else (1, 1)
    erster = min(erster, 28) if monat == 2 else erster
    anfang = date(tag.year, monat, erster)
    if anfang > tag:
        anfang = anfang.replace(year=tag.year - 1)
    naechstes = anfang.replace(year=anfang.year + 1)
    return anfang, naechstes - timedelta(days=1)


def buecher_frist_ende(
    wj_ende: date, abschluss: date | None = None, jahre: int = 10
) -> date:
    """Letzter Tag der Aufbewahrung der Bücher eines Wirtschaftsjahres: Frist ab
    Schluss des Jahres der letzten Eintragung — frühestens dem nach dem
    Wirtschaftsjahresende (Abschlussbuchungen), später bei späterem Abschluss."""
    letzte = max(wj_ende.year + 1, abschluss.year if abschluss else 0)
    return date(letzte + jahre, 12, 31)


OFFEN = date.max  # wieder geöffnetes Geschäftsjahr: die letzte Eintragung steht aus


def _abschluesse(s: Session, vorhanden: set[str]) -> dict[int, date]:
    """Geschäftsjahr → spätester Abschluss (``abschluesse.abgeschlossen_am``);
    ein wieder geöffnetes Jahr (``gesperrt`` falsch) → ``OFFEN``."""
    tabelle = Base.metadata.tables.get("abschluesse")
    if tabelle is None or "abschluesse" not in vorhanden:
        return {}
    ergebnis: dict[int, date] = {}
    abfrage = select(tabelle.c.jahr, tabelle.c.abgeschlossen_am, tabelle.c.gesperrt)
    for jahr, am, gesperrt in s.execute(abfrage):
        tag = _als_datum(am) if gesperrt else OFFEN
        if tag is not None and (jahr not in ergebnis or tag > ergebnis[jahr]):
            ergebnis[int(jahr)] = tag
    return ergebnis


@dataclass(frozen=True)
class _Monate:
    """Monatsabschlüsse je Wirtschaftsjahr (Schlüssel: dessen letzter Tag)."""

    spaetester: dict[date, date]  # spätestes Festschreiben eines Monats
    wieder_offen: set[date]  # ein Monat wurde geöffnet und ist offen


def _monatsabschluesse(s: Session, vorhanden: set[str], beginn: date | None) -> _Monate:
    tabelle = Base.metadata.tables.get("periodenabschluesse")
    monate = _Monate({}, set())
    if tabelle is None or "periodenabschluesse" not in vorhanden:
        return monate
    abfrage = select(tabelle.c.monat, tabelle.c.gesperrt, tabelle.c.geschlossen_am)
    for monat, gesperrt, am in s.execute(abfrage):
        _, ende = wirtschaftsjahr(date(int(monat[:4]), int(monat[5:7]), 1), beginn)
        if not gesperrt:
            monate.wieder_offen.add(ende)
        elif (tag := _als_datum(am)) is not None:
            monate.spaetester[ende] = max(tag, monate.spaetester.get(ende, tag))
    return monate


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


def _buch_zeile(
    s: Session,
    tabelle: Table,
    spaltenname: str,
    bezeichnung: str,
    f: Frist,
    stichtag: date,
    beginn: date | None,
    abschluesse: dict[int, date],
    monate: _Monate,
) -> Zeile:
    """Bücher und Aufzeichnungen je Wirtschaftsjahr (§ 147 Abs. 4 AO)."""
    spalte = tabelle.c[spaltenname]
    je_wj: dict[date, int] = {}
    aeltester: date | None = None
    tage: Iterable[object] = s.execute(select(spalte)).scalars()
    for wert in tage:
        tag = _als_datum(wert)
        if tag is None:
            continue
        aeltester = tag if aeltester is None or tag < aeltester else aeltester
        _, ende = wirtschaftsjahr(tag, beginn)
        je_wj[ende] = je_wj.get(ende, 0) + 1
    abgelaufen = 0
    for ende, anzahl in je_wj.items():
        anfang, _ = wirtschaftsjahr(ende, beginn)
        # Abschluss des Geschäftsjahres: nach Beginn- oder Endjahr benannt
        abschluss = max(
            (abschluesse[j] for j in {anfang.year, ende.year} if j in abschluesse),
            default=None,
        )
        if abschluss == OFFEN:
            continue  # wieder geöffnet: kann noch bebucht werden
        if abschluss is None and ende in monate.wieder_offen:
            continue  # ein Monat wieder geöffnet, das Jahr nicht abgeschlossen
        if (monat := monate.spaetester.get(ende)) is not None:
            abschluss = max(abschluss or monat, monat)
        if stichtag > buecher_frist_ende(ende, abschluss, f.jahre):
            abgelaufen += anzahl
    return Zeile(bezeichnung, f, aeltester, abgelaufen, sum(je_wj.values()))


def bericht(
    s: Session,
    stichtag: date,
    institut: bool = False,
    wirtschaftsjahr_beginn: date | None = None,
) -> list[Zeile]:
    """Was am Stichtag frühestens ausgesondert werden dürfte — nur lesend."""
    registriere_tabellen()
    vorhanden = set(inspect(s.get_bind()).get_table_names())
    abschluesse = _abschluesse(s, vorhanden)
    monate = _monatsabschluesse(s, vorhanden, wirtschaftsjahr_beginn)
    zeilen = []
    for name, spalte, bezeichnung, unterlage in BESTAND:
        tabelle = Base.metadata.tables.get(name)
        if tabelle is None or name not in vorhanden:
            continue
        f = frist(unterlage, institut, stichtag)
        if unterlage is Unterlage.BUCH:
            zeilen.append(
                _buch_zeile(
                    s,
                    tabelle,
                    spalte,
                    bezeichnung,
                    f,
                    stichtag,
                    wirtschaftsjahr_beginn,
                    abschluesse,
                    monate,
                )
            )
        else:
            zeilen.append(_zeile(s, tabelle, spalte, bezeichnung, f, stichtag))
    return zeilen
