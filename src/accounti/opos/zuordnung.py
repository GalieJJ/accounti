"""Zahlungszuordnung — welche Banktransaktion gehört zu welchem offenen Posten?

Dreistufig, nach demselben Muster wie die Kontierung: deterministisch vor unscharf.

A  Referenz   Belegnummer im Verwendungszweck (sicherster Treffer)
B  Exakt      genau ein Posten des Kontakts über genau diesen Betrag
C  Unscharf   Skontobetrag ohne Referenz, Summe mehrerer Posten, Teilbetrag,
              Überzahlung, Betrag ohne erkannten Kontakt — immer nur ein Vorschlag

Automatisch gebucht wird nur, was eindeutig ist: Stufe A mit genau einem Posten
(voll, Skonto in der Frist, Teilzahlung) und Stufe B. Alles andere legt accounti
dem Menschen vor — auch jeder Treffer, bei dem der erkannte Zahler nicht der Kontakt
des Postens ist, und eine Belegnummer, die nur als Datum im Zweck steht („2026-0315“ in
„EREF+20260315-0042“ oder „Lieferung vom 2026-03-15“): bei unbekanntem Zahler höchstens
ein Vorschlag, beim erkannten Zahler entscheidet der eindeutige Betrag (Stufe B).

Gutschriften und Guthaben: Ein Posten mit negativem Rest (Gutschrift,
Rechnungskorrektur, Überzahlung) wird durch eine Zahlung in Gegenrichtung getilgt
(Erstattung) oder mit gegenläufigen Posten desselben Kontakts saldiert. Gerechnet wird
deshalb aus Sicht der Zahlung: Jeder Posten, den diese Zahlung verkleinert, hat einen
positiven „Rest in Zahlungsrichtung“, ein gegenläufiger einen negativen. Die
``Anteil``-Beträge stehen dagegen im Vorzeichen des Postens — um so viel sinkt sein
Rest.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from itertools import combinations
from uuid import UUID

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
FREMDER_ZAHLER = 0.6  # höchstens so sicher, wenn der Zahler nicht der Kontakt ist
WIDERSPRUCH = 0.7  # höchstens so sicher, wenn der Zweck einen fremden Posten nennt


class Stufe(str, enum.Enum):
    REFERENZ = "referenz"
    EXAKT = "exakt"
    SKONTO = "skonto"
    TEIL = "teil"
    UEBERZAHLUNG = "ueberzahlung"
    SAMMEL = "sammel"
    UNSCHARF = "unscharf"
    HAND = "hand"  # von Hand zugeordnet (accounti opos zuordnen --transaktion)


@dataclass(frozen=True)
class Anteil:
    """Was von einer Zahlung auf einen Posten entfällt.

    ``betrag``: um so viel sinkt der Rest des Postens — im Vorzeichen des Postens,
    bei einer Gutschrift (negativer Posten) also negativ. ``skonto``: abgezogenes
    Skonto (positiv).
    """

    posten: OffenerPosten
    betrag: Decimal
    skonto: Decimal = NULL


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


_WORT = re.compile(r"[0-9]+|[a-z]+")


def woerter(text: str | None) -> list[str]:
    """Wörter eines Verwendungszwecks: Ziffern- und Buchstabenfolgen, klein."""
    return _WORT.findall((text or "").casefold())


def nennt(zweck: list[str], nummer: str | None) -> bool:
    """Steht die Belegnummer als ganze Wörter im Verwendungszweck (``woerter``)?

    Trennzeichen dürfen fehlen oder anders sein („RE 2026 0042“ = „RE-2026-0042“),
    die Nummer muss aber an Wortgrenzen beginnen und enden: „2026-0315“ steckt nicht
    in „120260315“, „2026-03150“ oder einer IBAN.
    """
    return bool(_treffer(zweck, nummer))


def _treffer(zweck: list[str], nummer: str | None) -> list[list[str]]:
    """Die Wortfolgen des Zwecks, die zusammen genau die Belegnummer ergeben."""
    ziel = _alnum(nummer)
    if len(ziel) < MIN_REFERENZ:
        return []
    treffer = []
    for i in range(len(zweck)):
        folge: list[str] = []
        for wort in zweck[i:]:
            folge.append(wort)
            if len("".join(folge)) >= len(ziel):
                break
        if "".join(folge) == ziel:
            treffer.append(folge)
    return treffer


def _ist_datum(wort: str) -> bool:
    """JJJJMMTT — so stehen Daten in Ende-zu-Ende-Referenzen (EREF+20260315…)."""
    if len(wort) != 8 or not wort.isdigit():
        return False
    try:
        date(int(wort[:4]), int(wort[4:6]), int(wort[6:]))
    except ValueError:
        return False
    return True


def _datumsfolge(folge: list[str], nummer: str | None) -> bool:
    """Ergibt die getroffene Wortfolge ein Datum JJJJMMTT, das anders gegliedert ist
    als die Nummer („20260315“, „2026-03-15“, „2026/03/15“ für 2026-0315)? Eine Nummer
    ohne Trennzeichen („20260315“ beim Format ``{jahr}{nummer:04d}``) ist als Datum
    gleich geschrieben — dann zählt jeder Treffer, der ein Datum ist."""
    teile = woerter(nummer)
    return _ist_datum("".join(folge)) and (
        len(teile) == 1 or [len(w) for w in folge] != [len(w) for w in teile]
    )


def nur_als_datum(zweck: list[str], nummer: str | None) -> bool:
    """Steht die Belegnummer nur als Datum im Zweck („EREF+20260315-0042“, „Lieferung
    vom 2026-03-15“ für 2026-0315)? Beim Format ``{jahr}-{nummer:04d}`` sehen die
    Nummern 0101 bis 1231 wie Tage aus — dann ist die Referenz mehrdeutig. Gleich
    gegliedert wie die Nummer („RE 2026 0315“) bleibt sie eine Referenz."""
    treffer = _treffer(zweck, nummer)
    return bool(treffer) and all(_datumsfolge(t, nummer) for t in treffer)


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
    """Teilmenge, deren Reste (ggf. abzüglich Skonto) genau den Betrag ergeben.

    Kleinere Teilmengen zuerst, innerhalb gleicher Größe die ältesten Posten. Ein
    gegenläufiger Posten (Guthaben) zählt mit seinem negativen Rest.
    """
    kandidaten = sorted(posten, key=lambda p: p.faellig_am)[:MAX_KANDIDATEN]
    for groesse in range(2, MAX_SAMMEL + 1):
        for kombination in combinations(kandidaten, groesse):
            if all(p.restbetrag < 0 for p in kombination):
                continue
            if sum((p.restbetrag for p in kombination), NULL) == betrag:
                return tuple(Anteil(p, p.restbetrag) for p in kombination)
            if all(_skonto_moeglich(p, tx, karenz) for p in kombination):
                netto = sum(
                    (p.restbetrag - (p.skonto_betrag or NULL) for p in kombination),
                    NULL,
                )
                if abs(netto - betrag) <= SKONTO_TOLERANZ * groesse:
                    anteile = [
                        Anteil(
                            p,
                            p.restbetrag - (p.skonto_betrag or NULL),
                            p.skonto_betrag or NULL,
                        )
                        for p in kombination
                    ]
                    # Rundungsrest auf den letzten Anteil, damit die Summe stimmt
                    differenz = betrag - netto
                    letzter = anteile[-1]
                    anteile[-1] = Anteil(
                        letzter.posten,
                        letzter.betrag + differenz,
                        letzter.skonto - differenz,
                    )
                    return tuple(anteile)
    return None


def auffuellen(posten: list[OffenerPosten], betrag: Decimal) -> tuple[Anteil, ...]:
    """Betrag auf die Posten in ihrer Reihenfolge verteilen; der Überschuss bleibt
    auf dem letzten (Guthaben)."""
    anteile = []
    rest = betrag
    for p in posten:
        if rest <= 0:
            break
        teil = min(rest, p.restbetrag)
        anteile.append(Anteil(p, teil))
        rest -= teil
    if rest > 0 and anteile:  # Überschuss bleibt auf dem letzten Posten (Guthaben)
        letzter = anteile[-1]
        anteile[-1] = Anteil(letzter.posten, letzter.betrag + rest)
    return tuple(anteile)


def _auffuellen(posten: list[OffenerPosten], betrag: Decimal) -> tuple[Anteil, ...]:
    """Betrag auf die ältesten Posten verteilen (Vorschlag, wenn nichts aufgeht)."""
    return auffuellen(sorted(posten, key=lambda p: p.faellig_am), betrag)


def _nummern(posten: list[OffenerPosten]) -> str:
    return ", ".join(p.belegnummer or "?" for p in posten)


def _mit_guthaben(
    p: OffenerPosten, guthaben: list[OffenerPosten], betrag: Decimal
) -> tuple[Anteil, ...] | None:
    """Rest des Postens abzüglich eines (oder aller) Guthaben desselben Kontakts."""
    for auswahl in [[g] for g in guthaben] + ([guthaben] if len(guthaben) > 1 else []):
        if p.restbetrag + sum((g.restbetrag for g in auswahl), NULL) == betrag:
            return (
                Anteil(p, p.restbetrag),
                *(Anteil(g, g.restbetrag) for g in auswahl),
            )
    return None


def _saldo(
    referenziert: list[OffenerPosten],
    gegen: list[OffenerPosten],
    betrag: Decimal,
    kontakt: Kontakt | None,
) -> Zuordnungsvorschlag:
    """Der Zweck nennt Rechnungen und Gutschriften: Saldo der genannten Posten."""
    gutschriften = tuple(Anteil(g, g.restbetrag) for g in gegen)
    nummern, gegen_nummern = _nummern(referenziert), _nummern(gegen)
    saldo = sum((p.restbetrag for p in referenziert + gegen), NULL)
    if saldo == betrag:
        return Zuordnungsvorschlag(
            tuple(Anteil(p, p.restbetrag) for p in referenziert) + gutschriften,
            Stufe.SAMMEL,
            False,
            0.85,
            f"Saldo aus {nummern} und Gutschrift/Guthaben {gegen_nummern} = Betrag",
            kontakt,
        )
    verteilt = _auffuellen(referenziert, betrag - sum(a.betrag for a in gutschriften))
    return Zuordnungsvorschlag(
        verteilt + gutschriften,
        Stufe.UNSCHARF,
        False,
        0.5,
        f"{nummern} und Gutschrift/Guthaben {gegen_nummern} genannt, Saldo {saldo} "
        "geht nicht auf — Gutschriften ganz, der Rest auf die ältesten Posten",
        kontakt,
    )


def _referenz(
    tx: Transaktion,
    referenziert: list[OffenerPosten],
    gegen: list[OffenerPosten],
    gegenlaeufig: list[OffenerPosten],
    betrag: Decimal,
    karenz: int,
    kontakt: Kontakt | None,
) -> Zuordnungsvorschlag:
    if gegen:
        return _saldo(referenziert, gegen, betrag, kontakt)
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
            guthaben = [g for g in gegenlaeufig if g.kontakt_id == p.kontakt_id]
            mit_guthaben = _mit_guthaben(p, guthaben, betrag)
            if mit_guthaben is not None:
                verrechnet = _nummern([a.posten for a in mit_guthaben[1:]])
                return Zuordnungsvorschlag(
                    mit_guthaben,
                    Stufe.SAMMEL,
                    False,
                    0.8,
                    f"Belegnummer {nummer}, Betrag = Rest abzüglich Guthaben aus "
                    f"{verrechnet}",
                    kontakt,
                )
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

    nummern = _nummern(referenziert)
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


def _beim_kontakt(
    tx: Transaktion,
    kandidaten: list[OffenerPosten],
    gegenlaeufig: list[OffenerPosten],
    betrag: Decimal,
    karenz: int,
    kontakt: Kontakt,
) -> Zuordnungsvorschlag | None:
    """Stufe B und C beim erkannten Kontakt (ohne Belegnummer im Zweck)."""
    eigene = [p for p in kandidaten if p.kontakt_id == kontakt.id]
    guthaben = [g for g in gegenlaeufig if g.kontakt_id == kontakt.id]
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
            f"{kontakt.name}: {len(gleich)} Posten über {betrag} — ältester gewählt",
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
    sammel = _summe(eigene + guthaben, betrag, tx, karenz)
    if sammel is not None:
        nummern = _nummern([a.posten for a in sammel])
        mit = " (mit Guthaben)" if any(a.betrag < 0 for a in sammel) else ""
        return Zuordnungsvorschlag(
            sammel,
            Stufe.SAMMEL,
            False,
            0.75,
            f"{kontakt.name}: Summe der Posten {nummern}{mit} = Betrag",
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
    if len(eigene) == 1:
        (p,) = eigene
        return Zuordnungsvorschlag(
            (Anteil(p, betrag),),
            Stufe.UEBERZAHLUNG,
            False,
            0.5,
            f"{kontakt.name}: einziger offener Posten {p.belegnummer}, Betrag "
            f"übersteigt den Rest um {betrag - p.restbetrag} — Überschuss bliebe als "
            "Guthaben",
            kontakt,
        )
    return None


def _nur_vorschlag(
    v: Zuordnungsvorschlag, zusatz: str, hoechstens: float
) -> Zuordnungsvorschlag:
    return replace(
        v,
        automatisch=False,
        confidence=min(v.confidence, hoechstens),
        begruendung=v.begruendung + zusatz,
    )


def _ordne(
    tx: Transaktion,
    betrag: Decimal,
    kandidaten: list[OffenerPosten],
    gegenlaeufig: list[OffenerPosten],
    kontakt: Kontakt | None,
    karenz: int,
) -> Zuordnungsvorschlag | None:
    # Stufe A: Referenz — Belegnummer an Wortgrenzen im Verwendungszweck
    zweck = woerter(tx.verwendungszweck)
    referenziert = [p for p in kandidaten if nennt(zweck, p.belegnummer)]
    if (
        kontakt is None
        and referenziert
        and all(nur_als_datum(zweck, p.belegnummer) for p in referenziert)
    ):
        return _datum_statt_referenz(tx, betrag, kandidaten, referenziert, karenz)
    fremd: list[OffenerPosten] = []
    if kontakt is not None and referenziert:
        eigene = [p for p in referenziert if p.kontakt_id == kontakt.id]
        # Nennt der Zweck nur Posten anderer Kontakte, hat der Zahler Vorrang
        fremd, referenziert = ([], eigene) if eigene else (referenziert, [])
        if eigene and all(nur_als_datum(zweck, p.belegnummer) for p in eigene):
            return _eigenes_datum(
                tx, betrag, kandidaten, gegenlaeufig, eigene, karenz, kontakt
            )
    if referenziert:
        kontakte = {p.kontakt_id for p in referenziert}
        gegen = [
            g
            for g in gegenlaeufig
            if g.kontakt_id in kontakte and nennt(zweck, g.belegnummer)
        ]
        return _referenz(tx, referenziert, gegen, gegenlaeufig, betrag, karenz, kontakt)

    if kontakt is not None:
        v = _beim_kontakt(tx, kandidaten, gegenlaeufig, betrag, karenz, kontakt)
        if not fremd:
            return v
        if v is not None:
            return _nur_vorschlag(
                v,
                f" — der Verwendungszweck nennt {_nummern(fremd)} eines anderen "
                "Kontakts",
                WIDERSPRUCH,
            )
        v = _referenz(tx, fremd, [], gegenlaeufig, betrag, karenz, kontakt)
        return _nur_vorschlag(
            v,
            f" — Posten eines anderen Kontakts, Zahler ist {kontakt.name}",
            FREMDER_ZAHLER,
        )

    return _ohne_kontakt(betrag, kandidaten)


def _ohne_kontakt(
    betrag: Decimal, kandidaten: list[OffenerPosten]
) -> Zuordnungsvorschlag | None:
    """Stufe C ohne Kontakt: nur ein eindeutiger Betrag."""
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


def _nur_datum(referenziert: list[OffenerPosten]) -> str:
    return (
        f" — {_nummern(referenziert)} steht nur als Datum im Verwendungszweck "
        "(JJJJMMTT), keine sichere Referenz"
    )


def _datum_statt_referenz(
    tx: Transaktion,
    betrag: Decimal,
    kandidaten: list[OffenerPosten],
    referenziert: list[OffenerPosten],
    karenz: int,
) -> Zuordnungsvorschlag:
    """Die Belegnummer steht nur als Datum im Zweck, der Zahler ist unbekannt:
    höchstens ein Vorschlag — der eindeutige Betrag geht der Referenz vor."""
    v = _ohne_kontakt(betrag, kandidaten) or _referenz(
        tx, referenziert, [], [], betrag, karenz, None
    )
    return _nur_vorschlag(v, _nur_datum(referenziert), FREMDER_ZAHLER)


def _eigenes_datum(
    tx: Transaktion,
    betrag: Decimal,
    kandidaten: list[OffenerPosten],
    gegenlaeufig: list[OffenerPosten],
    eigene: list[OffenerPosten],
    karenz: int,
    kontakt: Kontakt,
) -> Zuordnungsvorschlag:
    """Der Zweck nennt Posten des erkannten Zahlers nur als Datum: keine Referenz —
    was beim Kontakt eindeutig ist (Stufe B), bucht automatisch; sonst höchstens ein
    Vorschlag auf den genannten Posten."""
    v = _beim_kontakt(tx, kandidaten, gegenlaeufig, betrag, karenz, kontakt)
    if v is not None and v.automatisch:
        return v
    v = _referenz(tx, eigene, [], gegenlaeufig, betrag, karenz, kontakt)
    return _nur_vorschlag(v, _nur_datum(eigene), FREMDER_ZAHLER)


def faktor(p: OffenerPosten, zahlung: Decimal) -> int:
    """+1, wenn eine Zahlung mit diesem Vorzeichen einen positiven Rest des Postens
    verkleinert (Forderung: Eingang, Verbindlichkeit: Ausgang), sonst -1."""
    vorzeichen = 1 if zahlung > 0 else -1
    return vorzeichen if p.richtung is PostenRichtung.FORDERUNG else -vorzeichen


def in_zahlungsrichtung(p: OffenerPosten, f: int) -> OffenerPosten:
    """Der Posten aus Sicht der Zahlung: Rest > 0, wenn die Zahlung ihn tilgt."""
    if f == 1:
        return p
    return p.model_copy(
        update={
            "betrag": -p.betrag,
            "restbetrag": -p.restbetrag,
            "skonto_betrag": None,
            "skonto_bis": None,
        }
    )


def _mal(f: int, wert: Decimal) -> Decimal:
    return wert if f == 1 or not wert else -wert


def zurueck(
    anteile: tuple[Anteil, ...],
    original: dict[UUID, OffenerPosten],
    faktoren: dict[UUID, int],
) -> tuple[Anteil, ...]:
    """Anteile aus Sicht der Zahlung → Anteile im Vorzeichen der Posten."""
    return tuple(
        Anteil(
            original[a.posten.id],
            _mal(faktoren[a.posten.id], a.betrag),
            _mal(faktoren[a.posten.id], a.skonto),
        )
        for a in anteile
    )


def ordne_zu(
    tx: Transaktion,
    posten: list[OffenerPosten],
    kontakte: list[Kontakt],
    skonto_karenz_tage: int = 3,
) -> Zuordnungsvorschlag | None:
    """Ordnet eine Banktransaktion offenen Posten zu — oder gibt None zurück."""
    betrag = abs(tx.betrag)
    if betrag == 0:
        return None
    original = {p.id: p for p in posten if p.status is not PostenStatus.AUSGEGLICHEN}
    faktoren = {i: faktor(p, tx.betrag) for i, p in original.items()}
    sicht = [in_zahlungsrichtung(p, faktoren[p.id]) for p in original.values()]
    kandidaten = [p for p in sicht if p.restbetrag > 0]
    # Guthaben: nur Posten der Zahlungsrichtung mit negativem eigenem Rest — eine
    # Verbindlichkeit beim Zahlungseingang (Forderung beim Ausgang) stünde auf dem
    # anderen Personenkonto des Kontakts (keine Aufrechnung über zwei Konten)
    gegenlaeufig = [p for p in sicht if p.restbetrag < 0 and faktoren[p.id] == 1]
    if not kandidaten:
        return None
    kontakt, _ = finde_kontakt(
        kontakte, iban=tx.gegenkonto_iban, name=tx.gegenkonto_name
    )
    v = _ordne(tx, betrag, kandidaten, gegenlaeufig, kontakt, skonto_karenz_tage)
    if v is None:
        return None
    return replace(v, anteile=zurueck(v.anteile, original, faktoren))


def verteile(tx: Transaktion, posten: list[OffenerPosten]) -> tuple[Anteil, ...]:
    """Handzuordnung: Gutschriften und Guthaben unter den Posten ganz, dann der
    Betrag in der angegebenen Reihenfolge; ein Überschuss bleibt als Guthaben auf dem
    letzten Posten."""
    faktoren = {p.id: faktor(p, tx.betrag) for p in posten}
    sicht = [in_zahlungsrichtung(p, faktoren[p.id]) for p in posten]
    offen = [p for p in sicht if p.restbetrag > 0]
    gegen = [p for p in sicht if p.restbetrag < 0]
    if not offen or tx.betrag == 0:
        msg = (
            "Keiner der Posten wird von dieser Zahlung getilgt — ein Eingang tilgt "
            "Forderungen und Guthaben bei Lieferanten, ein Ausgang Verbindlichkeiten "
            "und Gutschriften an Kunden"
        )
        raise ValueError(msg)
    kontakte = {p.kontakt_id for p in offen}
    fremd = [g for g in gegen if faktoren[g.id] != 1 or g.kontakt_id not in kontakte]
    if fremd:
        msg = (
            f"{_nummern(fremd)} stünde gegen Posten auf einem anderen Personenkonto "
            "(Forderung gegen Verbindlichkeit oder Gutschrift eines anderen Kontakts) "
            "— eine Aufrechnung über zwei Personenkonten bucht accounti nicht"
        )
        raise ValueError(msg)
    gutschriften = tuple(Anteil(g, g.restbetrag) for g in gegen)
    verteilt = auffuellen(offen, abs(tx.betrag) - sum(a.betrag for a in gutschriften))
    return zurueck(gutschriften + verteilt, {p.id: p for p in posten}, faktoren)
