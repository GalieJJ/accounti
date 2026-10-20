"""CSV-Ausgaben des Jahresabschlusses (Semikolon, deutsche Beträge)."""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from accounti.abschluss.salden import Susa
from accounti.anzeige import betrag_de


def _zahl(wert: Decimal) -> str:
    return betrag_de(wert).replace(".", "")


def susa_csv(susa: Susa) -> str:
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\n")
    w.writerow(["Konto", "Bezeichnung", "Art", "EB", "Soll", "Haben", "Saldo"])
    for z in susa.zeilen:
        w.writerow(
            [
                z.konto,
                z.bezeichnung,
                z.art.value,
                *(_zahl(x) for x in (z.eb, z.soll, z.haben, z.saldo)),
            ]
        )
    return puffer.getvalue()
