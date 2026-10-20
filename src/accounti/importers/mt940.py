"""SWIFT MT940 mit der Belegung der Deutschen Kreditwirtschaft.

``:61:`` trägt Valuta, Buchungsdatum, Soll/Haben, Betrag, Kunden- und Bankreferenz;
``:86:`` den strukturierten Verwendungszweck: Geschäftsvorfallcode, dann ``?00``
Buchungstext, ``?10`` Primanota, ``?20``–``?29`` und ``?60``–``?63`` Verwendungszweck
(mit SEPA-Schlüsseln wie ``EREF+`` und ``SVWZ+``), ``?30`` BLZ/BIC, ``?31``
Konto/IBAN, ``?32``/``?33`` Name, ``?34`` Textschlüsselergänzung. Jeder Auszug muss
aufgehen: Anfangssaldo + Umsätze = Endsaldo.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from accounti.importers import BANK_IMPORTERS, BankImporter
from accounti.importers.kontoauszug import (
    LAENGE_NAME,
    LAENGE_ROHTEXT,
    LAENGE_ZWECK,
    Auszug,
    KontoauszugError,
    dekodiere,
    kuerze,
    pruefe_salden,
    referenz,
)
from accounti.models import Transaktion, TransaktionQuelle

_FELD = re.compile(r"^:(\d{2}[A-Z]?):(.*)$")
_SWIFT_KOPF = re.compile(r"\{[1-3]:[^{}]*\}|\{4:")
_SALDO = re.compile(
    r"^(?P<dc>[CD])(?P<datum>\d{6})(?P<waehrung>[A-Z]{3})(?P<betrag>\d+,\d*)$"
)
_UMSATZ = re.compile(
    r"^(?P<valuta>\d{6})(?P<buchung>\d{4})?(?P<dc>RC|RD|C|D)(?P<kennung>[A-Z])?"
    r"(?P<betrag>\d+,\d*)(?P<schluessel>[NFS][A-Z0-9]{3})"
    r"(?P<kundenref>(?:(?!//)[^\n]){0,16})(?://(?P<bankref>[^\n]{0,16}))?"
    r"(?:\n(?P<zusatz>.*))?$",
    re.DOTALL,
)
_SEPA = re.compile(
    r"(EREF|KREF|MREF|CRED|DEBT|SVWZ|ABWA|ABWE|IBAN|BIC|PURP|COAM|OAMT"
    r"|SQTP|ORCR|ORMR|DDAT|MDAT)\+"
)
_IBAN = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}")
_ZWECK_FELDER = [f"{n:02d}" for n in (*range(20, 30), *range(60, 64))]


def _betrag(roh: str) -> Decimal:
    try:
        return Decimal(roh.replace(",", "."))
    except InvalidOperation as fehler:
        raise KontoauszugError(f"Kein Betrag: {roh!r}") from fehler


def _datum(jjmmtt: str) -> date:
    try:
        return date(2000 + int(jjmmtt[:2]), int(jjmmtt[2:4]), int(jjmmtt[4:6]))
    except ValueError as fehler:
        raise KontoauszugError(f"Kein Datum: {jjmmtt!r}") from fehler


def _saldo(roh: str) -> tuple[Decimal, date, str]:
    m = _SALDO.match(roh.strip())
    if not m:
        raise KontoauszugError(f"Saldo nicht lesbar: {roh!r}")
    betrag = _betrag(m["betrag"])
    return (-betrag if m["dc"] == "D" else betrag), _datum(m["datum"]), m["waehrung"]


def _buchungsdatum(valuta: date, mmtt: str | None) -> date:
    if not mmtt:
        return valuta
    monat, tag = int(mmtt[:2]), int(mmtt[2:])
    jahr = valuta.year
    if valuta.month == 12 and monat == 1:
        jahr += 1
    elif valuta.month == 1 and monat == 12:
        jahr -= 1
    try:
        return date(jahr, monat, tag)
    except ValueError as fehler:
        raise KontoauszugError(f"Kein Buchungsdatum: {mmtt!r}") from fehler


def _felder(text: str) -> list[list[tuple[str, str]]]:
    """Nachrichten als Listen von (Feld, Inhalt); Folgezeilen gehören zum Feld."""
    text = text.replace("@@", "\n").replace("\r\n", "\n").replace("\r", "\n")
    text = _SWIFT_KOPF.sub("\n", text)
    nachrichten: list[list[tuple[str, str]]] = []
    aktuell: list[tuple[str, str]] = []
    for zeile in text.split("\n"):
        if zeile.strip() in ("-", "-}", "}"):
            if aktuell:
                nachrichten.append(aktuell)
            aktuell = []
            continue
        m = _FELD.match(zeile)
        if m:
            if m.group(1) == "20" and any(f == "20" for f, _ in aktuell):
                nachrichten.append(aktuell)  # neue Nachricht ohne Trennstrich
                aktuell = []
            aktuell.append((m.group(1), m.group(2)))
        elif aktuell and zeile.strip():
            feld, inhalt = aktuell[-1]
            aktuell[-1] = (feld, f"{inhalt}\n{zeile}")
    if aktuell:
        nachrichten.append(aktuell)
    return nachrichten


def _sepa(zweck: str) -> tuple[str, dict[str, str]]:
    """Freitext vor dem ersten Schlüssel und die SEPA-Schlüssel (``SVWZ`` usw.)."""
    teile = _SEPA.split(zweck)
    schluessel = {teile[i]: teile[i + 1].strip() for i in range(1, len(teile) - 1, 2)}
    return teile[0].strip(), schluessel


def _details(roh: str) -> tuple[str, str | None, str | None]:
    """Verwendungszweck, Name und IBAN der Gegenseite aus ``:86:``."""
    flach = roh.replace("\n", "")
    m = re.match(r"^\d{3}([^\w\s])\d{2}", flach)
    if not m:
        return re.sub(r"\s+", " ", roh.replace("\n", " ")).strip(), None, None
    trenner = m.group(1)
    teile = re.split(re.escape(trenner) + r"(\d{2})", flach[3:])
    felder: dict[str, str] = {}
    for i in range(1, len(teile) - 1, 2):
        felder[teile[i]] = felder.get(teile[i], "") + teile[i + 1]
    roher_zweck = "".join(felder.get(n, "") for n in _ZWECK_FELDER)
    frei, schluessel = _sepa(roher_zweck)
    if schluessel:
        zweck = schluessel.get("SVWZ") or frei
        eref = referenz(schluessel.get("EREF"))
        if eref:
            zweck = f"{zweck} EREF: {eref}".strip()
    else:
        zweck = roher_zweck.strip()
    zweck = zweck or felder.get("00", "").strip()
    name = (felder.get("32", "") + felder.get("33", "")).strip() or None
    konto = re.sub(r"\s", "", felder.get("31", "")).upper()
    iban = konto if _IBAN.fullmatch(konto) else schluessel.get("IBAN")
    return zweck, name, iban


def _umsatz(roh: str, details: str | None, waehrung: str) -> Transaktion:
    m = _UMSATZ.match(roh.strip())
    if not m:
        raise KontoauszugError(f"Umsatzzeile :61: nicht lesbar: {roh!r}")
    valuta = _datum(m["valuta"])
    betrag = _betrag(m["betrag"])
    if m["dc"] in ("D", "RC"):  # Belastung bzw. Storno einer Gutschrift
        betrag = -betrag
    zweck, name, iban = _details(details) if details is not None else ("", None, None)
    rohtext = f":61:{roh}" + (f"\n:86:{details}" if details is not None else "")
    return Transaktion(
        datum=_buchungsdatum(valuta, m["buchung"]),
        betrag=betrag,
        waehrung=waehrung,
        verwendungszweck=kuerze(zweck, LAENGE_ZWECK) or "",
        gegenkonto_name=kuerze(name, LAENGE_NAME),
        gegenkonto_iban=iban,
        quelle=TransaktionQuelle.BANK,
        quelle_referenz=referenz(m["bankref"]),
        rohtext=rohtext[:LAENGE_ROHTEXT],
    )


def _auszug(nachricht: list[tuple[str, str]]) -> Auszug:
    auszug = Auszug()
    offen: list[tuple[str, str | None]] = []  # :61: mit zugehörigem :86:
    abgeschlossen = False  # ein :86: nach :62: gehört zum Auszug, nicht zum Umsatz
    for feld, inhalt in nachricht:
        if feld == "25":
            auszug.konto = inhalt.strip()
        elif feld in ("60F", "60M"):
            auszug.anfangssaldo, _, auszug.waehrung = _saldo(inhalt)
        elif feld == "61":
            offen.append((inhalt, None))
        elif feld == "86" and offen and offen[-1][1] is None and not abgeschlossen:
            offen[-1] = (offen[-1][0], inhalt)
        elif feld in ("62F", "62M"):
            auszug.endsaldo, auszug.endsaldo_datum, waehrung = _saldo(inhalt)
            auszug.waehrung = auszug.waehrung or waehrung
            abgeschlossen = True
    if auszug.anfangssaldo is None or auszug.endsaldo is None:
        raise KontoauszugError("MT940-Auszug ohne Anfangs- oder Endsaldo (:60:/:62:)")
    waehrung = auszug.waehrung or "EUR"
    auszug.umsaetze = [_umsatz(roh, details, waehrung) for roh, details in offen]
    return auszug


def lies_mt940(text: str) -> list[Auszug]:
    nachrichten = [n for n in _felder(text) if any(f == "20" for f, _ in n)]
    if not nachrichten:
        raise KontoauszugError("Keine MT940-Nachricht gefunden (:20: fehlt)")
    auszuege = []
    for nr, nachricht in enumerate(nachrichten, start=1):
        auszug = _auszug(nachricht)
        pruefe_salden(auszug, f"MT940-Auszug {nr}")
        auszuege.append(auszug)
    return auszuege


class MT940Importer(BankImporter):
    """``accounti import bank auszug.sta --format mt940``."""

    name = "mt940"

    def importiere(self, pfad: str | Path) -> list[Transaktion]:
        auszuege = lies_mt940(dekodiere(Path(pfad).read_bytes()))
        return [t for a in auszuege for t in a.umsaetze]


BANK_IMPORTERS[MT940Importer.name] = MT940Importer()
