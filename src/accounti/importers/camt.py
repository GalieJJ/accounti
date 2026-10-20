"""ISO 20022 camt.052 (Umsatzreport), camt.053 (Kontoauszug), camt.054 (Avis).

Gelesen wird namensraumunabhängig, damit die Versionen .02 und .08 (und dazwischen)
denselben Weg gehen: in .02 ist ``Ntry/Sts`` ein Code und die Partei heißt
``RltdPties/Dbtr/Nm``, in .08 steht ``Ntry/Sts/Cd`` und ``RltdPties/Dbtr/Pty/Nm``.
Übernommen werden nur gebuchte Einträge (``BOOK``); das Vorzeichen kommt aus
``CdtDbtInd``, die Bankreferenz aus ``AcctSvcrRef``. DTDs und Entities werden
abgelehnt — ein Kontoauszug braucht sie nie.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
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
    kuerze,
    pruefe_salden,
    referenz,
)
from accounti.models import Transaktion, TransaktionQuelle

_DTD = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)", re.IGNORECASE)
_BEHAELTER = {"Stmt", "Rpt", "Ntfctn"}
_ANFANG = ("OPBD", "PRCD")
_ENDE = "CLBD"


def _name(element: ET.Element) -> str:
    return element.tag.rpartition("}")[2]


def _kinder(element: ET.Element | None, name: str) -> list[ET.Element]:
    if element is None:
        return []
    return [k for k in element if _name(k) == name]


def _knoten(element: ET.Element | None, pfad: str) -> ET.Element | None:
    for teil in pfad.split("/"):
        gefunden = _kinder(element, teil)
        element = gefunden[0] if gefunden else None
        if element is None:
            return None
    return element


def _text(element: ET.Element | None, pfad: str) -> str | None:
    knoten = _knoten(element, pfad)
    if knoten is None or knoten.text is None:
        return None
    return knoten.text.strip() or None


def _alle_texte(element: ET.Element | None, pfad: str) -> list[str]:
    *weg, letzter = pfad.split("/")
    eltern = _knoten(element, "/".join(weg)) if weg else element
    return [
        k.text.strip() for k in _kinder(eltern, letzter) if k.text and k.text.strip()
    ]


def _betrag(element: ET.Element | None, wo: str) -> tuple[Decimal, str | None]:
    amt = _knoten(element, "Amt")
    roh = amt.text.strip() if amt is not None and amt.text else ""
    try:
        betrag = Decimal(roh)
    except InvalidOperation as fehler:
        raise KontoauszugError(f"Kein Betrag in {wo}: {roh!r}") from fehler
    richtung = _text(element, "CdtDbtInd")
    if richtung not in ("CRDT", "DBIT"):
        msg = f"CdtDbtInd fehlt oder ist unbekannt in {wo}: {richtung}"
        raise KontoauszugError(msg)
    waehrung = amt.get("Ccy") if amt is not None else None
    return (-betrag if richtung == "DBIT" else betrag), waehrung


def _datum(element: ET.Element | None, pfad: str) -> date | None:
    wert = _text(element, f"{pfad}/Dt") or _text(element, f"{pfad}/DtTm")
    if wert is None:
        return None
    try:
        return date.fromisoformat(wert[:10])
    except ValueError as fehler:
        raise KontoauszugError(f"Kein Datum in {pfad}: {wert!r}") from fehler


def _status(ntry: ET.Element) -> str | None:
    return _text(ntry, "Sts/Cd") or _text(ntry, "Sts/Prtry") or _text(ntry, "Sts")


def _partei(tx: ET.Element, rolle: str) -> tuple[str | None, str | None]:
    parteien = _knoten(tx, "RltdPties")
    name = _text(parteien, f"{rolle}/Pty/Nm") or _text(parteien, f"{rolle}/Nm")
    iban = _text(parteien, f"{rolle}Acct/Id/IBAN")
    return name, iban


def _zweck(tx: ET.Element) -> str:
    teile = _alle_texte(tx, "RmtInf/Ustrd")
    teile += [
        ref
        for strd in _kinder(_knoten(tx, "RmtInf"), "Strd")
        if (ref := _text(strd, "CdtrRefInf/Ref"))
    ]
    zweck = " ".join(teile)
    eref = referenz(_text(tx, "Refs/EndToEndId"))
    return f"{zweck} EREF: {eref}".strip() if eref else zweck


def _umsatz(ntry: ET.Element, waehrung: str | None, wo: str) -> Transaktion:
    betrag, ccy = _betrag(ntry, wo)
    datum = _datum(ntry, "BookgDt") or _datum(ntry, "ValDt")
    if datum is None:
        raise KontoauszugError(f"Buchungsdatum fehlt in {wo}")
    details = [tx for nd in _kinder(ntry, "NtryDtls") for tx in _kinder(nd, "TxDtls")]
    # Gegenpartei: bei Gutschriften der Zahler, bei Belastungen der Empfänger
    rollen = ("Dbtr", "Cdtr") if betrag >= 0 else ("Cdtr", "Dbtr")
    parteien = set()
    for tx in details:
        name, iban = _partei(tx, rollen[0])
        if name is None and iban is None:
            name, iban = _partei(tx, rollen[1])
        parteien.add((name, iban))
    name, iban = parteien.pop() if len(parteien) == 1 else (None, None)
    zweck = "; ".join(z for tx in details if (z := _zweck(tx)))
    zweck = zweck or _text(ntry, "AddtlNtryInf") or ""
    bankref = referenz(_text(ntry, "AcctSvcrRef"))
    if bankref is None and len(details) == 1:
        bankref = referenz(_text(details[0], "Refs/AcctSvcrRef"))
    return Transaktion(
        datum=datum,
        betrag=betrag,
        waehrung=(ccy or waehrung or "EUR")[:3],
        verwendungszweck=kuerze(zweck, LAENGE_ZWECK) or "",
        gegenkonto_name=kuerze(name, LAENGE_NAME),
        gegenkonto_iban=iban,
        quelle=TransaktionQuelle.BANK,
        quelle_referenz=bankref,
        rohtext=ET.tostring(ntry, encoding="unicode")[:LAENGE_ROHTEXT],
    )


def _auszug(behaelter: ET.Element, nr: int) -> Auszug:
    wo = f"camt-{_name(behaelter)} {nr}"
    auszug = Auszug(
        konto=_text(behaelter, "Acct/Id/IBAN") or _text(behaelter, "Acct/Id/Othr/Id"),
        waehrung=_text(behaelter, "Acct/Ccy"),
    )
    for bal in _kinder(behaelter, "Bal"):
        art = _text(bal, "Tp/CdOrPrtry/Cd")
        if art in _ANFANG and auszug.anfangssaldo is None:
            auszug.anfangssaldo, _ = _betrag(bal, f"{wo}, Saldo {art}")
        elif art == _ENDE:
            auszug.endsaldo, _ = _betrag(bal, f"{wo}, Saldo {art}")
            auszug.endsaldo_datum = _datum(bal, "Dt")
    for i, ntry in enumerate(_kinder(behaelter, "Ntry"), start=1):
        if _status(ntry) not in (None, "BOOK"):
            continue  # Vormerkposten und Informationen sind keine Buchungen
        auszug.umsaetze.append(_umsatz(ntry, auszug.waehrung, f"{wo}, Eintrag {i}"))
    pruefe_salden(auszug, wo)
    return auszug


def lies_camt(daten: bytes) -> list[Auszug]:
    if _DTD.search(daten):
        msg = "DTD/Entity-Deklarationen sind in Kontoauszügen nicht erlaubt"
        raise KontoauszugError(msg)
    try:
        wurzel = ET.fromstring(daten)
    except ET.ParseError as fehler:
        raise KontoauszugError(f"XML nicht wohlgeformt: {fehler}") from fehler
    nachricht = next(
        (k for k in wurzel if _name(k).startswith("BkToCstmr")),
        wurzel if _name(wurzel).startswith("BkToCstmr") else None,
    )
    kinder = list(nachricht) if nachricht is not None else []
    behaelter = [k for k in kinder if _name(k) in _BEHAELTER]
    if not behaelter:
        raise KontoauszugError("Kein camt.052/053/054 (BkToCstmr…) gefunden")
    return [_auszug(b, nr) for nr, b in enumerate(behaelter, start=1)]


class CamtImporter(BankImporter):
    """``accounti import bank auszug.xml --format camt``."""

    name = "camt"

    def importiere(self, pfad: str | Path) -> list[Transaktion]:
        return [t for a in lies_camt(Path(pfad).read_bytes()) for t in a.umsaetze]


BANK_IMPORTERS[CamtImporter.name] = CamtImporter()
