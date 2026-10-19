"""Gemeinsame XML-Helfer: sicheres Parsen und knappe Pfadzugriffe."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation

from accounti.erechnung.modell import ERechnungError

_DTD = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)", re.IGNORECASE)


def parse_sicher(xml: bytes) -> ET.Element:
    """Parst eine E-Rechnung; DTDs und Entities werden grundsätzlich abgelehnt."""
    if _DTD.search(xml):
        msg = "DTD/Entity-Deklarationen sind in E-Rechnungen nicht erlaubt"
        raise ERechnungError(msg)
    try:
        return ET.fromstring(xml)
    except ET.ParseError as fehler:
        msg = f"XML nicht wohlgeformt: {fehler}"
        raise ERechnungError(msg) from fehler


def lokaler_name(element: ET.Element) -> str:
    return element.tag.rpartition("}")[2]


class Leser:
    """Pfadzugriffe relativ zu einem Element, mit festem Namensraum-Mapping."""

    def __init__(self, element: ET.Element | None, ns: dict[str, str]) -> None:
        self.element = element
        self.ns = ns

    def __bool__(self) -> bool:
        return self.element is not None

    def knoten(self, pfad: str) -> Leser:
        gefunden = (
            self.element.find(pfad, self.ns) if self.element is not None else None
        )
        return Leser(gefunden, self.ns)

    def alle(self, pfad: str) -> list[Leser]:
        if self.element is None:
            return []
        return [Leser(e, self.ns) for e in self.element.findall(pfad, self.ns)]

    def text(self, pfad: str = ".") -> str | None:
        k = self.knoten(pfad) if pfad != "." else self
        if k.element is None or k.element.text is None:
            return None
        return k.element.text.strip() or None

    def attr(self, pfad: str, name: str) -> str | None:
        k = self.knoten(pfad)
        return k.element.get(name) if k.element is not None else None

    def dezimal(self, pfad: str) -> Decimal | None:
        wert = self.text(pfad)
        if wert is None:
            return None
        try:
            return Decimal(wert)
        except InvalidOperation as fehler:
            msg = f"Kein Betrag in {pfad}: {wert!r}"
            raise ERechnungError(msg) from fehler

    def datum(self, pfad: str) -> date | None:
        """ISO (UBL) oder CII-Format 102 (JJJJMMTT)."""
        wert = self.text(pfad)
        if wert is None:
            return None
        ziffern = wert.replace("-", "")
        try:
            return date(int(ziffern[:4]), int(ziffern[4:6]), int(ziffern[6:8]))
        except ValueError as fehler:
            msg = f"Kein Datum in {pfad}: {wert!r}"
            raise ERechnungError(msg) from fehler
