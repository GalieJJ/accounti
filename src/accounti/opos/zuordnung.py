"""Zahlungszuordnung — welche Banktransaktion gehört zu welchem offenen Posten?

Dreistufig, nach demselben Muster wie die Kontierung: deterministisch vor unscharf.

A  Referenz   Belegnummer im Verwendungszweck (sicherster Treffer)
B  Exakt      genau ein Posten des Kontakts über genau diesen Betrag
C  Unscharf   Skontobetrag ohne Referenz, Summe mehrerer Posten, Teilbetrag,
              Betrag ohne erkannten Kontakt — immer nur ein Vorschlag

Automatisch gebucht wird nur, was eindeutig ist: Stufe A mit genau einem Posten
(voll, Skonto in der Frist, Teilzahlung) und Stufe B. Alles andere legt accounti
dem Menschen vor.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from itertools import combinations

from accounti.kontakte.erkennung import finde_kontakt
from accounti.models import (
    Kontakt,
    OffenerPosten,
    PostenRichtung,
    PostenStatus,
    Transaktion,
)

NULL = Decimal("0")
SKONTO_TOLERANZ = Decimal("0.02")  # Lieferanten runden Skonto je Satz unterschiedlich
MIN_REFERENZ = 5  # kürzere Belegnummern („4711") treffen zu oft zufällig
MAX_SAMMEL = 4  # Posten je Sammelzahlung
MAX_KANDIDATEN = 12  # älteste offene Posten, die für Summen probiert werden


class Stufe(str, enum.Enum):
    REFERENZ = "referenz"
    EXAKT = "exakt"
    SKONTO = "skonto"
    TEIL = "teil"
    UEBERZAHLUNG = "ueberzahlung"
    SAMMEL = "sammel"
    UNSCHARF = "unscharf"


@dataclass(frozen=True)
class Anteil:
    """Was von einer Zahlung auf einen Posten entfällt."""

    posten: OffenerPosten
    betrag: Decimal  # gezahlt (positiv)
    skonto: Decimal = NULL  # abgezogenes Skonto (positiv)


@dataclass(frozen=True)
class Zuordnungsvorschlag:
    anteile: tuple[Anteil, ...]
    stufe: Stufe
    automatisch: bool
    confidence: float
    begruendung: str
    kontakt: Kontakt | None = None


def _alnum(text: str | None) -> str:
    return re.sub(r"[^0-9a-z]", "", (text or "").casefold())


def _skonto_moeglich(p: OffenerPosten, tx: Transaktion, karenz: int) -> bool:
    """Skonto nur auf den unberührten Posten und innerhalb der Frist (+ Karenz)."""
    return (
        p.skonto_betrag is not None
        and p.skonto_betrag > 0
        and p.skonto_bis is not None
        and p.restbetrag == p.betrag
        and tx.datum <= p.skonto_bis + timedelta(days=karenz)
    )


def _mit_skonto(
    p: OffenerPosten, betrag: Decimal, tx: Transaktion, karenz: int
) -> Anteil | None:
    """Anteil, wenn ``betrag`` dem Rest abzüglich Skonto entspricht."""
    if not _skonto_moeglich(p, tx, karenz) or p.skonto_betrag is None:
        return None
    if abs(betrag - (p.restbetrag - p.skonto_betrag)) <= SKONTO_TOLERANZ:
        return Anteil(p, betrag, p.restbetrag - betrag)
    return None


def _summe(
    posten: list[OffenerPosten], betrag: Decimal, tx: Transaktion, karenz: int
) -> tuple[Anteil, ...] | None:
    """Teilmenge, deren Reste (je Posten ggf. ohne Skonto) genau den Betrag ergeben.

    Kleinere Teilmengen zuerst, innerhalb gleicher Größe die ältesten Posten. Skonto
    zieht nur ein skontofähiger Posten (unberührt, in der Frist) — oft nur ein Teil der
    Sammelzahlung, z. B. Rest einer Teilzahlung plus neue Rechnung abzüglich Skonto
    (§ 17 Abs. 1 UStG: die Minderung des Skontopostens korrigiert die Steuer).
    """
    kandidaten = sorted(posten, key=lambda p: p.faellig_am)[:MAX_KANDIDATEN]
    for groesse in range(2, MAX_SAMMEL + 1):
        for kombination in combinations(kandidaten, groesse):
            reste = sum((p.restbetrag for p in kombination), NULL)
            if reste == betrag:
                return tuple(Anteil(p, p.restbetrag) for p in kombination)
            faehig = [p for p in kombination if _skonto_moeglich(p, tx, karenz)]
            # erst alle skontofähigen Posten mit Skonto, dann kleinere Teilmengen
            for anzahl in range(len(faehig), 0, -1):
                for mit in combinations(faehig, anzahl):
                    abzug = sum((p.skonto_betrag or NULL for p in mit), NULL)
                    if abs(reste - abzug - betrag) <= SKONTO_TOLERANZ * anzahl:
                        return _mit_skonto_anteilen(
                            kombination, {id(p) for p in mit}, betrag - reste + abzug
                        )
    return None


def _mit_skonto_anteilen(
    kombination: tuple[OffenerPosten, ...], mit: set[int], differenz: Decimal
) -> tuple[Anteil, ...]:
    """Anteile einer Sammelzahlung; der Rundungsrest geht auf den letzten Posten mit
    Skonto, damit die Summe stimmt."""
    anteile = [
        Anteil(p, p.restbetrag - (p.skonto_betrag or NULL), p.skonto_betrag or NULL)
        if id(p) in mit
        else Anteil(p, p.restbetrag)
        for p in kombination
    ]
    letzter = max(i for i, p in enumerate(kombination) if id(p) in mit)
    a = anteile[letzter]
    anteile[letzter] = Anteil(a.posten, a.betrag + differenz, a.skonto - differenz)
    return tuple(anteile)


def _auffuellen(posten: list[OffenerPosten], betrag: Decimal) -> tuple[Anteil, ...]:
    """Betrag auf die ältesten Posten verteilen (Vorschlag, wenn nichts aufgeht)."""
    anteile = []
    rest = betrag
    for p in sorted(posten, key=lambda p: p.faellig_am):
        if rest <= 0:
            break
        teil = min(rest, p.restbetrag)
        anteile.append(Anteil(p, teil))
        rest -= teil
    if rest > 0 and anteile:  # Überschuss bleibt auf dem letzten Posten (Guthaben)
        letzter = anteile[-1]
        anteile[-1] = Anteil(letzter.posten, letzter.betrag + rest)
    return tuple(anteile)


def _referenz(
    tx: Transaktion,
    referenziert: list[OffenerPosten],
    betrag: Decimal,
    karenz: int,
    kontakt: Kontakt | None,
) -> Zuordnungsvorschlag:
    if len(referenziert) == 1:
        (p,) = referenziert
        nummer = p.belegnummer
        if betrag == p.restbetrag:
            return Zuordnungsvorschlag(
                (Anteil(p, betrag),),
                Stufe.REFERENZ,
                True,
                1.0,
                f"Belegnummer {nummer} im Verwendungszweck, Betrag = Rest",
                kontakt,
            )
        skonto = _mit_skonto(p, betrag, tx, karenz)
        if skonto is not None:
            return Zuordnungsvorschlag(
                (skonto,),
                Stufe.SKONTO,
                True,
                0.95,
                f"Belegnummer {nummer}, Betrag = Rest abzüglich Skonto in der Frist",
                kontakt,
            )
        if betrag < p.restbetrag:
            return Zuordnungsvorschlag(
                (Anteil(p, betrag),),
                Stufe.TEIL,
                True,
                0.9,
                f"Belegnummer {nummer}, Teilzahlung — Rest bleibt offen",
                kontakt,
            )
        return Zuordnungsvorschlag(
            (Anteil(p, betrag),),
            Stufe.UEBERZAHLUNG,
            False,
            0.6,
            f"Belegnummer {nummer}, Betrag übersteigt den Rest um "
            f"{betrag - p.restbetrag} — Überschuss bliebe als Guthaben",
            kontakt,
        )

    nummern = ", ".join(p.belegnummer or "?" for p in referenziert)
    if sum((p.restbetrag for p in referenziert), NULL) == betrag:
        anteile = tuple(Anteil(p, p.restbetrag) for p in referenziert)
        return Zuordnungsvorschlag(
            anteile,
            Stufe.SAMMEL,
            False,
            0.85,
            f"Sammelzahlung über {nummern}, Summe der Reste = Betrag",
            kontakt,
        )
    mit_skonto = _summe(referenziert, betrag, tx, karenz)
    if mit_skonto is not None and len(mit_skonto) == len(referenziert):
        return Zuordnungsvorschlag(
            mit_skonto,
            Stufe.SAMMEL,
            False,
            0.8,
            f"Sammelzahlung über {nummern} abzüglich Skonto",
            kontakt,
        )
    return Zuordnungsvorschlag(
        _auffuellen(referenziert, betrag),
        Stufe.UNSCHARF,
        False,
        0.5,
        f"Belegnummern {nummern} genannt, Beträge gehen nicht auf — auf die ältesten "
        "verteilt",
        kontakt,
    )


def ordne_zu(
    tx: Transaktion,
    posten: list[OffenerPosten],
    kontakte: list[Kontakt],
    skonto_karenz_tage: int = 3,
) -> Zuordnungsvorschlag | None:
    """Ordnet eine Banktransaktion offenen Posten zu — oder gibt None zurück."""
    betrag = abs(tx.betrag)
    richtung = (
        PostenRichtung.VERBINDLICHKEIT if tx.betrag < 0 else PostenRichtung.FORDERUNG
    )
    kandidaten = [
        p
        for p in posten
        if p.richtung is richtung
        and p.status is not PostenStatus.AUSGEGLICHEN
        and p.restbetrag > 0
    ]
    if betrag == 0 or not kandidaten:
        return None
    kontakt, _ = finde_kontakt(
        kontakte, iban=tx.gegenkonto_iban, name=tx.gegenkonto_name
    )
    karenz = skonto_karenz_tage

    # Stufe A: Referenz
    zweck = _alnum(tx.verwendungszweck)
    referenziert = [
        p
        for p in kandidaten
        if len(_alnum(p.belegnummer)) >= MIN_REFERENZ and _alnum(p.belegnummer) in zweck
    ]
    if referenziert:
        return _referenz(tx, referenziert, betrag, karenz, kontakt)

    # Stufe B: exakt beim erkannten Kontakt
    if kontakt is not None:
        eigene = [p for p in kandidaten if p.kontakt_id == kontakt.id]
        gleich = [p for p in eigene if p.restbetrag == betrag]
        if len(gleich) == 1:
            return Zuordnungsvorschlag(
                (Anteil(gleich[0], betrag),),
                Stufe.EXAKT,
                True,
                0.95,
                f"{kontakt.name}: einziger offener Posten über {betrag}",
                kontakt,
            )
        if gleich:
            aeltester = min(gleich, key=lambda p: p.faellig_am)
            return Zuordnungsvorschlag(
                (Anteil(aeltester, betrag),),
                Stufe.EXAKT,
                False,
                0.6,
                f"{kontakt.name}: {len(gleich)} Posten über {betrag} — "
                "ältester gewählt",
                kontakt,
            )

        # Stufe C: unscharf, aber mit Kontakt
        skonto = [a for p in eigene if (a := _mit_skonto(p, betrag, tx, karenz))]
        if len(skonto) == 1:
            return Zuordnungsvorschlag(
                (skonto[0],),
                Stufe.SKONTO,
                False,
                0.8,
                f"{kontakt.name}: Betrag = Rest abzüglich Skonto, ohne Belegnummer",
                kontakt,
            )
        sammel = _summe(eigene, betrag, tx, karenz)
        if sammel is not None:
            nummern = ", ".join(a.posten.belegnummer or "?" for a in sammel)
            return Zuordnungsvorschlag(
                sammel,
                Stufe.SAMMEL,
                False,
                0.75,
                f"{kontakt.name}: Summe der Posten {nummern} = Betrag",
                kontakt,
            )
        kleiner = [p for p in eigene if betrag < p.restbetrag]
        if kleiner:
            aeltester = min(kleiner, key=lambda p: p.faellig_am)
            return Zuordnungsvorschlag(
                (Anteil(aeltester, betrag),),
                Stufe.TEIL,
                False,
                0.5,
                f"{kontakt.name}: Teilbetrag auf den ältesten offenen Posten",
                kontakt,
            )
        return None

    # Stufe C ohne Kontakt: nur ein eindeutiger Betrag
    gleich = [p for p in kandidaten if p.restbetrag == betrag]
    if len(gleich) == 1:
        return Zuordnungsvorschlag(
            (Anteil(gleich[0], betrag),),
            Stufe.UNSCHARF,
            False,
            0.6,
            f"Kontakt unbekannt, aber genau ein offener Posten über {betrag}",
        )
    return None
