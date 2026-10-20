"""Zusammenfassende Meldung (§ 18a UStG).

Je USt-IdNr. des Abnehmers und Art der Leistung die Summe der Bemessungsgrundlagen
eines Meldezeitraums, in vollen Euro: ``L`` innergemeinschaftliche Lieferung (Kz 41),
``D`` Lieferung des ersten Abnehmers im Dreiecksgeschäft (Kz 42), ``S`` sonstige
Leistung nach § 3a Abs. 2 UStG (Kz 21). Minderungen (Gutschrift, Skonto) stehen in dem
Zeitraum, in dem sie eintreten (Anleitung ZM 1/2021).

Abgegeben wird beim BZSt; accounti erzeugt die CSV-Datei für den Import im
ELSTER-Portal (Version 3.0, UTF-8, Komma, höchstens 1500 Zeilen).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from accounti.steuer.kennziffern import Ermittlung, EuUmsatz
from accounti.steuer.voranmeldung import volle_euro
from accounti.steuer.zeitraum import Zeitraum

CSV_VERSION = "#v3.0"
CSV_KOPF = (
    "Umsatzsteuer-Identifikationsnummer (USt-IdNr.),Summe (Euro),Art der Leistung"
)
MAX_ZEILEN = 1500
ARTEN = {"L": "ig. Lieferungen", "D": "Dreiecksgeschäfte", "S": "sonstige Leistungen"}


def normalisiere(ust_id: str) -> str:
    kompakt = re.sub(r"[\s.\-/]", "", ust_id).upper()
    return "EL" + kompakt[2:] if kompakt.startswith("GR") else kompakt


@dataclass(frozen=True)
class ZMZeile:
    ust_id: str
    art: str  # L, D, S
    betrag: Decimal  # volle Euro
    name: str


@dataclass
class ZusammenfassendeMeldung:
    zeitraum: Zeitraum
    zeilen: list[ZMZeile] = field(default_factory=list)
    ohne_ustid: list[EuUmsatz] = field(default_factory=list)

    def summe(self, art: str) -> Decimal:
        return sum((z.betrag for z in self.zeilen if z.art == art), Decimal("0"))

    def als_csv(self) -> str:
        """Datei für den ZM-Import im ELSTER-Portal (CSV-Version 3.0)."""
        if len(self.zeilen) > MAX_ZEILEN:
            msg = f"{len(self.zeilen)} Zeilen — der Import nimmt höchstens {MAX_ZEILEN}"
            raise ValueError(msg)
        zeilen = [CSV_VERSION, CSV_KOPF]
        zeilen += [f"{z.ust_id},{int(z.betrag)},{z.art}" for z in self.zeilen]
        return "\n".join(zeilen) + "\n"


def erstelle_zm(e: Ermittlung) -> ZusammenfassendeMeldung:
    """ZM des ermittelten Zeitraums aus dessen EU-Umsätzen."""
    summen: dict[tuple[str, str], Decimal] = {}
    namen: dict[str, str] = {}
    meldung = ZusammenfassendeMeldung(e.zeitraum)
    for u in e.eu:
        if u.kontakt is None or not u.kontakt.ust_id:
            meldung.ohne_ustid.append(u)
            continue
        ust_id = normalisiere(u.kontakt.ust_id)
        namen.setdefault(ust_id, u.kontakt.name)
        schluessel = (ust_id, u.art)
        summen[schluessel] = summen.get(schluessel, Decimal("0")) + u.betrag
    for (ust_id, art), betrag in sorted(summen.items()):
        euro = volle_euro(betrag)
        if euro != 0:
            meldung.zeilen.append(ZMZeile(ust_id, art, euro, namen[ust_id]))
    return meldung
