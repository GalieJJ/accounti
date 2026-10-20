"""Kontoauszüge als Datei (MT940, CAMT) — gemeinsames Modell und Formaterkennung.

Anders als die CSV-Profile bringen MT940 und CAMT das Konto, die Salden und eine
Referenz der Bank mit. Die Parser liefern deshalb je Auszug ein ``Auszug``-Objekt;
der Dateiimport, der Datei-Provider und FinTS nutzen dieselben Parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from accounti.importers import BankImporter
from accounti.models import Transaktion

# Platzhalter, die Banken statt einer Referenz liefern — zählen nicht als Referenz
LEERE_REFERENZEN = frozenset({"", "NONREF", "NOTPROVIDED", "NOT PROVIDED"})

# Spaltenlängen der Tabelle ``transaktionen``
LAENGE_ZWECK = 500
LAENGE_NAME = 200
LAENGE_ROHTEXT = 2000

_IBAN = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}")
_CAMT = re.compile(rb"<(?:\w+:)?BkToCstmr(?:Stmt|AcctRpt|DbtCdtNtfctn)\b")
_MT940_FELDER = (rb":20:", rb":25:")
_MT940_SALDO = re.compile(rb":60[FM]:")


class KontoauszugError(ValueError):
    """Der Kontoauszug ist unlesbar, unvollständig oder unsicher."""


def referenz(wert: str | None) -> str | None:
    """Referenz der Bank — ``None`` für fehlende Werte und Platzhalter."""
    text = (wert or "").strip()
    return None if text.upper() in LEERE_REFERENZEN else text


def kuerze(text: str | None, laenge: int) -> str | None:
    if text is None:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text[:laenge] or None


def _kompakt(text: str) -> str:
    return re.sub(r"\s", "", text).upper()


@dataclass
class Auszug:
    """Ein Auszug (MT940-Nachricht, camt-Statement/-Report) mit seinen Umsätzen."""

    konto: str | None = None  # IBAN oder "BLZ/Kontonummer", wie in der Datei
    waehrung: str | None = None
    anfangssaldo: Decimal | None = None
    endsaldo: Decimal | None = None
    endsaldo_datum: date | None = None
    umsaetze: list[Transaktion] = field(default_factory=list)

    def gehoert_zu(self, iban: str) -> bool:
        """Passt der Auszug zum Konto? Im Zweifel ja — ausgeschlossen wird nur,
        was erkennbar zu einem anderen Konto gehört."""
        if not self.konto:
            return True
        konto, eigene = _kompakt(self.konto), _kompakt(iban)
        treffer = _IBAN.search(konto)
        if not _IBAN.fullmatch(eigene):
            # z.B. eine Kreditkarte: ein Auszug mit IBAN gehört zu einem Girokonto
            return konto == eigene or treffer is None
        if treffer:
            return treffer.group(0) == eigene
        blz, _, nummer = konto.partition("/")
        nummer = re.sub(r"[A-Z]+$", "", nummer)
        if not (blz.isdigit() and nummer.isdigit()) or not eigene.startswith("DE"):
            return True
        return eigene[4:12] == blz and int(eigene[12:]) == int(nummer)


def pruefe_salden(auszug: Auszug, name: str) -> None:
    """Anfangssaldo + Umsätze = Endsaldo, sonst fehlt etwas (oder ist zu viel)."""
    if auszug.anfangssaldo is None or auszug.endsaldo is None:
        return
    summe = sum((t.betrag for t in auszug.umsaetze), Decimal("0"))
    if auszug.anfangssaldo + summe != auszug.endsaldo:
        msg = (
            f"Saldo von {name} geht nicht auf: Anfangssaldo {auszug.anfangssaldo} "
            f"+ Umsätze {summe} ≠ Endsaldo {auszug.endsaldo} — Auszug unvollständig?"
        )
        raise KontoauszugError(msg)


def erkenne_auszugsformat(daten: bytes) -> str | None:
    """``"camt"``, ``"mt940"`` oder ``None`` — am Inhalt, nicht an der Endung."""
    kopf = daten[:65536]
    if _CAMT.search(kopf):
        return "camt"
    if all(f in kopf for f in _MT940_FELDER) and _MT940_SALDO.search(kopf):
        return "mt940"
    return None


def dekodiere(daten: bytes) -> str:
    """MT940 kommt als UTF-8 oder in einer ISO-8859-Variante (cp1252)."""
    try:
        return daten.decode("utf-8-sig")
    except UnicodeDecodeError:
        return daten.decode("cp1252", errors="replace")


def lies_kontoauszug(daten: bytes) -> list[Auszug]:
    format = erkenne_auszugsformat(daten)
    if format == "camt":
        from accounti.importers.camt import lies_camt

        return lies_camt(daten)
    if format == "mt940":
        from accounti.importers.mt940 import lies_mt940

        return lies_mt940(dekodiere(daten))
    raise KontoauszugError("Kein Kontoauszug im Format MT940 oder CAMT")


def umsaetze_fuer_konto(auszuege: list[Auszug], konto: str | None) -> list[Transaktion]:
    """Umsätze der Auszüge, die zum Konto gehören.

    Ohne Konto nur, wenn die Datei höchstens ein Konto enthält — sonst landeten die
    Umsätze fremder Konten mit dem Sachkonto des einen im Journal. Gehört kein
    Auszug zum genannten Konto, ist es die falsche Datei."""
    if konto is None:
        konten = sorted({_kompakt(a.konto) for a in auszuege if a.konto})
        if len(konten) > 1:
            msg = (
                f"Die Datei enthält Auszüge mehrerer Konten ({', '.join(konten)}) — "
                "mit --konto das Konto wählen"
            )
            raise KontoauszugError(msg)
        return [t for a in auszuege for t in a.umsaetze]
    passend = [a for a in auszuege if a.gehoert_zu(konto)]
    if auszuege and not passend:
        fremd = ", ".join(sorted({a.konto for a in auszuege if a.konto}))
        msg = f"Die Datei gehört nicht zum Konto {konto} (sie nennt {fremd})"
        raise KontoauszugError(msg)
    return [t for a in passend for t in a.umsaetze]


class AuszugImporter(BankImporter):
    """Importer für Kontoauszüge mit Kontoangabe (MT940, CAMT)."""

    def auszuege(self, pfad: str | Path) -> list[Auszug]:
        raise NotImplementedError

    def importiere(
        self, pfad: str | Path, konto: str | None = None
    ) -> list[Transaktion]:
        return umsaetze_fuer_konto(self.auszuege(pfad), konto)


def importiere_fuer_konto(
    importer: BankImporter, pfad: str | Path, konto: str | None
) -> list[Transaktion]:
    """``import bank``: MT940/CAMT nur mit den Auszügen des Kontos (CSV kennt kein
    Konto und bleibt wie gehabt)."""
    if isinstance(importer, AuszugImporter):
        return importer.importiere(pfad, konto)
    return importer.importiere(pfad)
