"""Kontoauszüge je Finanzkonto: lückenlos nummeriert, mit schlüssigem Saldenverlauf.

Ein Auszug umfasst einen Kalendermonat eines Finanzkontos (Sachkonto der Transaktion,
sonst ``buchhaltung.bank_konto``; PayPal hat sein eigenes). Auszüge sind je
Finanzkonto und Jahr ab 1 lückenlos nummeriert — auch Monate ohne Umsatz bekommen
einen —, und jeder beginnt mit dem Endsaldo seines Vorgängers. Beim Erstellen werden
sie festgeschrieben (Tabellen ``kontoauszuege`` und ``kontoauszug_umsaetze``) und über
eine Hash-Kette verbunden. Umsätze, die erst nach dem Festschreiben für einen
abgeschlossenen Monat eintreffen, kommen als Nachtrag in den nächsten Auszug.

Ausgabe als MT940 (DFÜ-Abkommen Anlage 3, Teil 5 — DATEV liest Kontoumsätze aus
MT940) und als Saldenverlauf (CSV). ``pruefe_auszuege`` rechnet die Kette nach und
meldet Lücken, Nummernsprünge, Saldensprünge und nachträgliche Änderungen.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import groupby
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.repo_export import (
    lade_kontoauszuege,
    speichere_kontoauszug,
    zugeordnete_transaktion_ids,
)
from accounti.db.repository import lade_bankkonten, lade_transaktionen
from accounti.models import Bankkonto, Transaktion
from accounti.models.export import Auszugsbefund, Kontoauszug

NULL = Decimal("0")
TAG = timedelta(days=1)
MEHRZWECK_ZEILEN = 6  # :86: höchstens 6 Zeilen à 65 Zeichen
MEHRZWECK_LAENGE = 65


class KontoauszugError(RuntimeError):
    """Auszüge lassen sich so nicht erstellen oder ausgeben."""


@dataclass
class Auszugslauf:
    neu: list[Kontoauszug] = field(default_factory=list)
    befunde: list[Auszugsbefund] = field(default_factory=list)


def _monatsende(tag: date) -> date:
    return date(tag.year, tag.month, monthrange(tag.year, tag.month)[1])


def _euro(betrag: Decimal) -> str:
    return f"{betrag:.2f}".replace(".", ",")


def auszugs_hash(a: Kontoauszug, umsaetze: list[Transaktion]) -> str:
    """SHA-256 über Kopf, Salden und Umsätze — verkettet mit dem Vorgänger.

    Je Umsatz gehen auch die Texte ein, die das MT940 im Feld ``:86:`` ausgibt
    (Verwendungszweck, Name, IBAN): ein ausgegebener Auszug ändert sich nicht.
    """
    nachtraege = set(a.nachtraege)
    teile = [
        a.vorgaenger_hash,
        a.finanzkonto,
        str(a.jahr),
        str(a.nummer),
        a.von.isoformat(),
        a.bis.isoformat(),
        a.waehrung,
        f"{a.anfangssaldo:.2f}",
        f"{a.endsaldo:.2f}",
    ]
    teile += [
        f"{tx.id}:{tx.datum.isoformat()}:{tx.betrag:.2f}:"
        f"{'N' if tx.id in nachtraege else ''}:"
        + json.dumps(
            [tx.verwendungszweck, tx.gegenkonto_name, tx.gegenkonto_iban],
            ensure_ascii=False,
        )
        for tx in umsaetze
    ]
    return hashlib.sha256("|".join(teile).encode("utf-8")).hexdigest()


def lade_umsaetze(
    session: Session, auszuege: list[Kontoauszug]
) -> dict[UUID, Transaktion]:
    """Die Transaktionen der Auszüge (gelöschte fehlen im Ergebnis)."""
    gesucht = {tx_id for a in auszuege for tx_id in a.umsaetze}
    return {tx.id: tx for tx in lade_transaktionen(session) if tx.id in gesucht}


def _sortierung(tx: Transaktion) -> date:
    """Nach Datum; am selben Tag bleibt die Reihenfolge des Imports (stabil)."""
    return tx.datum


def erstelle_auszuege(
    session: Session,
    finanzkonto: str,
    bis: date,
    *,
    standard_konto: str = "1200",
    anfangssaldo: Decimal | None = None,
    kontrollsaldo: Decimal | None = None,
    ab: date | None = None,
    heute: date | None = None,
    jetzt: datetime | None = None,
) -> Auszugslauf:
    """Schreibt die fehlenden Monatsauszüge bis zum Monatsende ``bis`` fest.

    Der erste Auszug eines Finanzkontos beginnt mit dem Monat von ``ab`` (ohne Angabe:
    dem von ``bis``) und braucht ``anfangssaldo`` (Saldo laut Bank zu Beginn dieses
    Monats); danach schließt jeder Lauf an den letzten Auszug an. Stimmt
    ``kontrollsaldo`` (Saldo laut Bank am ``bis``) nicht mit dem errechneten Endsaldo
    überein, wird nichts festgeschrieben.
    """
    heute = heute or date.today()
    jetzt = jetzt or datetime.now()
    if bis != _monatsende(bis):
        raise KontoauszugError(f"{bis:%d.%m.%Y}: Auszüge enden am Monatsende")
    if bis >= heute:
        msg = f"Monat {bis:%m/%Y} ist noch nicht abgeschlossen — Auszug erst danach"
        raise KontoauszugError(msg)

    vorhanden = lade_kontoauszuege(session, finanzkonto)
    letzter = vorhanden[-1] if vorhanden else None
    if letzter is not None:
        if ab is not None:
            msg = (
                f"Für Finanzkonto {finanzkonto} gibt es schon Auszüge (ab "
                f"{vorhanden[0].von:%m/%Y}) — --ab nur beim ersten Auszug"
            )
            raise KontoauszugError(msg)
        if anfangssaldo is not None and anfangssaldo != letzter.endsaldo:
            msg = (
                f"Der Anfangssaldo steht fest: Endsaldo des Auszugs "
                f"{letzter.nummer}/{letzter.jahr} ist {_euro(letzter.endsaldo)} — "
                "--anfangssaldo weglassen"
            )
            raise KontoauszugError(msg)
        beginn = letzter.bis + TAG
        saldo = letzter.endsaldo
        erster_beginn = vorhanden[0].von
    else:
        beginn = date((ab or bis).year, (ab or bis).month, 1)
        if beginn > bis:
            raise KontoauszugError(f"--ab {beginn:%m/%Y} liegt nach {bis:%m/%Y}")
        if anfangssaldo is None:
            msg = (
                f"Erster Kontoauszug für Finanzkonto {finanzkonto}: --anfangssaldo "
                f"angeben (Saldo laut Bank zu Beginn des {beginn:%d.%m.%Y})"
            )
            raise KontoauszugError(msg)
        saldo = anfangssaldo
        erster_beginn = beginn
    lauf = Auszugslauf()
    if beginn > bis:
        # alles bis ``bis`` steht fest — der Kontrollsaldo prüft dann den Auszug
        if kontrollsaldo is not None:
            _pruefe_kontrollsaldo(vorhanden, bis, kontrollsaldo)
        return lauf

    zugeordnet = zugeordnete_transaktion_ids(session)
    monate: dict[date, list[Transaktion]] = defaultdict(list)
    nachtraege: list[Transaktion] = []
    for tx in sorted(lade_transaktionen(session), key=_sortierung):
        if (tx.sachkonto or standard_konto) != finanzkonto or tx.id in zugeordnet:
            continue
        if tx.datum > bis:
            continue  # kommt in einen späteren Auszug
        if tx.waehrung != "EUR":
            # gemeldet, wenn der Monat jetzt festgeschrieben wird
            if letzter is None or tx.datum >= beginn:
                lauf.befunde.append(
                    Auszugsbefund(
                        code="fremdwaehrung",
                        text=f"Umsatz vom {tx.datum:%d.%m.%Y} in {tx.waehrung} "
                        f"({tx.verwendungszweck[:40]}) steht in keinem EUR-Auszug",
                        finanzkonto=finanzkonto,
                    )
                )
            continue
        if tx.datum < erster_beginn:
            # nur beim ersten Auszug gemeldet: sie stecken im Anfangssaldo
            if letzter is None:
                lauf.befunde.append(
                    Auszugsbefund(
                        code="vor_beginn",
                        text=f"Umsatz vom {tx.datum:%d.%m.%Y} über {_euro(tx.betrag)} "
                        f"liegt vor dem ersten Auszug ({erster_beginn:%d.%m.%Y}) — "
                        "er gehört in den Anfangssaldo",
                        finanzkonto=finanzkonto,
                    )
                )
            continue
        if tx.datum < beginn:
            nachtraege.append(tx)
            monate[beginn].append(tx)
        else:
            monate[date(tx.datum.year, tx.datum.month, 1)].append(tx)

    vorgaenger = letzter
    monat = beginn
    while monat <= bis:
        ende = _monatsende(monat)
        umsaetze = sorted(monate[monat], key=_sortierung)
        nummer = (
            vorgaenger.nummer + 1
            if vorgaenger is not None and vorgaenger.jahr == monat.year
            else 1
        )
        endsaldo = saldo + sum((tx.betrag for tx in umsaetze), NULL)
        auszug = Kontoauszug(
            finanzkonto=finanzkonto,
            jahr=monat.year,
            nummer=nummer,
            von=monat,
            bis=ende,
            anfangssaldo=saldo,
            endsaldo=endsaldo,
            umsaetze=[tx.id for tx in umsaetze],
            nachtraege=[tx.id for tx in umsaetze if tx in nachtraege],
            erstellt_am=jetzt,
            vorgaenger_hash=vorgaenger.hash if vorgaenger is not None else "",
        )
        auszug.hash = auszugs_hash(auszug, umsaetze)
        for tx in umsaetze:
            if tx in nachtraege:
                lauf.befunde.append(
                    Auszugsbefund(
                        code="nachtrag",
                        text=f"Umsatz vom {tx.datum:%d.%m.%Y} über {_euro(tx.betrag)} "
                        f"kam nach dem Abschluss seines Monats — Nachtrag im Auszug "
                        f"{nummer}/{monat.year}",
                        finanzkonto=finanzkonto,
                        nummer=nummer,
                        jahr=monat.year,
                    )
                )
        lauf.neu.append(auszug)
        vorgaenger, saldo, monat = auszug, endsaldo, ende + TAG

    if kontrollsaldo is not None:
        letzter_neu = lauf.neu[-1]
        if kontrollsaldo != letzter_neu.endsaldo:
            msg = (
                f"Kontrollsaldo {_euro(kontrollsaldo)} weicht vom errechneten Endsaldo "
                f"{_euro(letzter_neu.endsaldo)} zum {bis:%d.%m.%Y} ab (Differenz "
                f"{_euro(kontrollsaldo - letzter_neu.endsaldo)}) — fehlen Umsätze? "
                "Nichts festgeschrieben."
            )
            raise KontoauszugError(msg)
        letzter_neu.kontrollsaldo = kontrollsaldo

    for auszug in lauf.neu:
        speichere_kontoauszug(session, auszug)
    return lauf


def _pruefe_kontrollsaldo(
    vorhanden: list[Kontoauszug], bis: date, kontrollsaldo: Decimal
) -> None:
    """Kontrollsaldo gegen den Endsaldo des festgeschriebenen Auszugs zum ``bis``."""
    auszug = next((a for a in vorhanden if a.bis == bis), None)
    if auszug is None:
        msg = f"Kein festgeschriebener Auszug endet am {bis:%d.%m.%Y} — Kontrollsaldo?"
        raise KontoauszugError(msg)
    if auszug.endsaldo != kontrollsaldo:
        msg = (
            f"Kontrollsaldo {_euro(kontrollsaldo)} weicht vom Endsaldo "
            f"{_euro(auszug.endsaldo)} des festgeschriebenen Auszugs "
            f"{auszug.nummer}/{auszug.jahr} ab (Differenz "
            f"{_euro(kontrollsaldo - auszug.endsaldo)}) — fehlen Umsätze?"
        )
        raise KontoauszugError(msg)


def _befund(a: Kontoauszug, code: str, text: str) -> Auszugsbefund:
    return Auszugsbefund(
        code=code,
        text=f"Auszug {a.nummer}/{a.jahr} ({a.finanzkonto}): {text}",
        finanzkonto=a.finanzkonto,
        nummer=a.nummer,
        jahr=a.jahr,
    )


def _pruefe_auszug(
    a: Kontoauszug, vorher: Kontoauszug | None, umsaetze: dict[UUID, Transaktion]
) -> list[Auszugsbefund]:
    befunde: list[Auszugsbefund] = []
    erwartet = vorher.nummer + 1 if vorher and vorher.jahr == a.jahr else 1
    if a.nummer != erwartet or a.jahr != a.von.year:
        befunde.append(_befund(a, "nummer", f"Nummer {a.nummer}, erwartet {erwartet}"))
    if vorher is not None:
        if a.von != vorher.bis + TAG:
            text = (
                f"Zeitraum {(vorher.bis + TAG).isoformat()} bis "
                f"{(a.von - TAG).isoformat()} fehlt"
            )
            befunde.append(_befund(a, "luecke", text))
        if a.anfangssaldo != vorher.endsaldo:
            text = (
                f"Anfangssaldo {_euro(a.anfangssaldo)} ≠ Endsaldo des Vorgängers "
                f"{_euro(vorher.endsaldo)}"
            )
            befunde.append(_befund(a, "saldensprung", text))
    if a.vorgaenger_hash != (vorher.hash if vorher else ""):
        text = "Hash-Kette unterbrochen (Vorgänger fehlt oder wurde geändert)"
        befunde.append(_befund(a, "hash", text))
    vorhanden = [umsaetze[i] for i in a.umsaetze if i in umsaetze]
    for tx_id in a.umsaetze:
        if tx_id not in umsaetze:
            text = f"Umsatz {tx_id} ist nicht mehr vorhanden"
            befunde.append(_befund(a, "umsatz_fehlt", text))
    nachtraege = set(a.nachtraege)
    for tx in vorhanden:
        # im Monat: regulär; davor: nur als Nachtrag; danach: nie
        im_monat = a.von <= tx.datum <= a.bis
        if tx.datum > a.bis or im_monat == (tx.id in nachtraege):
            text = f"Umsatz vom {tx.datum:%d.%m.%Y} passt nicht in den Auszug"
            befunde.append(_befund(a, "zeitraum", text))
    summe = sum((tx.betrag for tx in vorhanden), NULL)
    if a.anfangssaldo + summe != a.endsaldo:
        text = (
            f"Anfangssaldo {_euro(a.anfangssaldo)} + Umsätze {_euro(summe)} ≠ "
            f"Endsaldo {_euro(a.endsaldo)}"
        )
        befunde.append(_befund(a, "summe", text))
    if auszugs_hash(a, vorhanden) != a.hash:
        befunde.append(_befund(a, "hash", "Inhalt seit dem Festschreiben geändert"))
    return befunde


def pruefe_auszuege(
    session: Session, finanzkonto: str | None = None
) -> list[Auszugsbefund]:
    """Rechnet Nummerierung, Zeiträume, Salden und Hash-Kette nach."""
    alle = lade_kontoauszuege(session, finanzkonto)
    umsaetze = lade_umsaetze(session, alle)
    befunde: list[Auszugsbefund] = []
    for _konto, gruppe in groupby(alle, key=lambda a: a.finanzkonto):
        vorher: Kontoauszug | None = None
        for a in gruppe:
            befunde += _pruefe_auszug(a, vorher, umsaetze)
            vorher = a
    return befunde


# ---------------------------------------------------------------------------
# Kontobezeichnung (:25:)
# ---------------------------------------------------------------------------


def kontobezeichnung(
    finanzkonto: str,
    bankkonten: list[Bankkonto] | None,
    paypal_konto: str,
    paypal_bezeichnung: str,
    *,
    session: Session | None = None,
) -> str:
    """``:25:``: BLZ/Kontonummer (deutsche IBAN), sonst IBAN; PayPal laut Konfig."""
    if bankkonten is None:
        bankkonten = lade_bankkonten(session) if session is not None else []
    passend = [k for k in bankkonten if k.sachkonto == finanzkonto]
    if len(passend) > 1:
        ibans = ", ".join(k.iban for k in passend)
        msg = (
            f"Finanzkonto {finanzkonto}: mehrere Bankkonten ({ibans}) — je Bankkonto "
            "ein eigenes Sachkonto einrichten"
        )
        raise KontoauszugError(msg)
    if passend:
        iban = re.sub(r"\s", "", passend[0].iban).upper()
        if re.fullmatch(r"DE\d{20}", iban):
            return f"{iban[4:12]}/{iban[12:].lstrip('0') or '0'}"
        return iban
    if finanzkonto == paypal_konto:
        return paypal_bezeichnung
    msg = (
        f"Für Finanzkonto {finanzkonto} ist kein Bankkonto eingerichtet "
        "(accounti bank verbinde) — oder --kontobezeichnung angeben"
    )
    raise KontoauszugError(msg)


# ---------------------------------------------------------------------------
# MT940
# ---------------------------------------------------------------------------

_ERSATZ = str.maketrans(
    {
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "ẞ": "SS",
        "&": "+",
        "€": "EUR",
        "{": "(",
        "}": ")",
        "[": "(",
        "]": ")",
        ":": ".",
        ";": ".",
    }
)
_NICHT_SWIFT = re.compile(r"[^A-Za-z0-9/\-().,'+ ]")


def swift_text(text: str) -> str:
    """Text im SWIFT-Zeichensatz: Umlaute umschreiben, Akzente weg, Rest Leerzeichen.

    Erlaubt bleiben ``A–Z a–z 0–9 / - ( ) . , ' +`` und das Leerzeichen; ``?`` (Trenner
    der strukturierten Belegung) und ``:`` (Feldkennung) werden nicht durchgereicht.
    """
    zerlegt = unicodedata.normalize("NFKD", text.translate(_ERSATZ))
    ohne_akzente = "".join(z for z in zerlegt if not unicodedata.combining(z))
    return " ".join(_NICHT_SWIFT.sub(" ", ohne_akzente).split())


def _mehrzweck(text: str) -> list[str]:
    """``:86:`` in Zeilen zu 65 Zeichen; keine Zeile beginnt mit ``:`` oder ``-``."""
    zeilen: list[str] = []
    rest = text
    while rest and len(zeilen) < MEHRZWECK_ZEILEN:
        n = min(MEHRZWECK_LAENGE, len(rest))
        while 1 < n < len(rest) and rest[n] in ":-":
            n -= 1
        zeile, rest = rest[:n], rest[n:]
        if zeilen and zeile[:1] in {":", "-"}:
            zeile = " " + zeile[1:]
        zeilen.append(zeile)
    return [":86:" + zeilen[0], *zeilen[1:]] if zeilen else [":86:"]


def _mt_betrag(betrag: Decimal) -> str:
    text = _euro(abs(betrag))
    if len(text) > 15:
        raise KontoauszugError(f"Betrag {text} ist für MT940 zu lang")
    return text


def _saldo(betrag: Decimal, tag: date, waehrung: str) -> str:
    return f"{'C' if betrag >= 0 else 'D'}{tag:%y%m%d}{waehrung}{_mt_betrag(betrag)}"


def referenz(a: Kontoauszug) -> str:
    """``:20:`` — eindeutig je Auszug, höchstens 16 Zeichen."""
    return f"{a.finanzkonto}-{a.jahr % 100:02d}-{a.nummer}"[:16]


def pruefe_kontobezeichnung(text: str) -> str:
    """``:25:`` hat höchstens 35 Zeichen aus dem SWIFT-Zeichensatz."""
    bezeichnung = text.strip()
    if (
        not bezeichnung
        or len(bezeichnung) > 35
        or swift_text(bezeichnung) != bezeichnung
    ):
        msg = (
            f"Kontobezeichnung {text!r} passt nicht in :25: (höchstens 35 Zeichen, "
            "z.B. BLZ/Kontonummer oder IBAN)"
        )
        raise KontoauszugError(msg)
    return bezeichnung


def mt940(
    auszuege: list[Kontoauszug],
    umsaetze: dict[UUID, Transaktion],
    kontobezeichnung: str,
) -> bytes:
    """Eine MT940-Datei mit einer Nachricht je Auszug (CR LF, Nachrichtenende ``-``)."""
    bezeichnung = pruefe_kontobezeichnung(kontobezeichnung)
    nachrichten = []
    for a in auszuege:
        zeilen = [
            f":20:{referenz(a)}",
            f":25:{bezeichnung}",
            f":28C:{a.nummer}/1",
            f":60F:{_saldo(a.anfangssaldo, a.von - TAG, a.waehrung)}",
        ]
        for tx_id in a.umsaetze:
            tx = umsaetze.get(tx_id)
            if tx is None:
                msg = (
                    f"Auszug {a.nummer}/{a.jahr}: Umsatz {tx_id} fehlt — Auszüge prüfen"
                )
                raise KontoauszugError(msg)
            kennung = "C" if tx.betrag >= 0 else "D"
            zeilen.append(
                f":61:{tx.datum:%y%m%d}{tx.datum:%m%d}{kennung}"
                f"{_mt_betrag(tx.betrag)}NMSCNONREF"
            )
            text = " ".join(
                t
                for t in (tx.verwendungszweck, tx.gegenkonto_name, tx.gegenkonto_iban)
                if t
            )
            zeilen += _mehrzweck("999" + swift_text(text))
        zeilen.append(f":62F:{_saldo(a.endsaldo, a.bis, a.waehrung)}")
        nachrichten.append("\r\n" + "\r\n".join(zeilen) + "\r\n-")
    return "".join(nachrichten).encode("ascii")


# ---------------------------------------------------------------------------
# Saldenverlauf
# ---------------------------------------------------------------------------

SALDENVERLAUF_SPALTEN = [
    "Finanzkonto",
    "Jahr",
    "Auszug",
    "Von",
    "Bis",
    "Anfangssaldo",
    "Eingänge",
    "Ausgänge",
    "Endsaldo",
    "Umsätze",
    "Nachträge",
    "Kontrollsaldo",
    "Prüfsumme",
]


def saldenverlauf_csv(
    auszuege: list[Kontoauszug], umsaetze: dict[UUID, Transaktion]
) -> bytes:
    """Ein Auszug je Zeile: Salden, Eingänge, Ausgänge — Semikolon, Windows-1252."""
    zeilen = [";".join(SALDENVERLAUF_SPALTEN)]
    for a in auszuege:
        betraege = [umsaetze[i].betrag for i in a.umsaetze if i in umsaetze]
        zeilen.append(
            ";".join(
                [
                    a.finanzkonto,
                    str(a.jahr),
                    str(a.nummer),
                    f"{a.von:%d.%m.%Y}",
                    f"{a.bis:%d.%m.%Y}",
                    _euro(a.anfangssaldo),
                    _euro(sum((b for b in betraege if b > 0), NULL)),
                    _euro(sum((b for b in betraege if b < 0), NULL)),
                    _euro(a.endsaldo),
                    str(len(a.umsaetze)),
                    str(len(a.nachtraege)),
                    _euro(a.kontrollsaldo) if a.kontrollsaldo is not None else "",
                    a.hash[:16],
                ]
            )
        )
    return ("\r\n".join(zeilen) + "\r\n").encode("cp1252")
