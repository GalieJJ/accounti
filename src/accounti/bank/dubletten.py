"""Dublettenschutz für Bankumsätze — ein Umsatz kommt genau einmal ins System.

Der Schlüssel fasst Konto, Datum, Betrag, Verwendungszweck und Gegenpartei zusammen,
plus die laufende Nummer gleicher Umsätze im selben Auszug (bzw. in derselben Datei
oder demselben Abruf, wenn der Provider keine Auszüge kennt): Zwei echte Parkgebühren
über 5 € am selben Tag bleiben zwei, derselbe Umsatz aus einem überlappenden zweiten
Abruf, einem doppelten Import oder aus Tages- und Monatsauszug bleibt einer.

Liefert die Bank eine Referenz (camt ``AcctSvcrRef``, MT940 ``//Referenz``), ist sie
der Unterscheider: Der Schlüssel besteht dann aus Konto, Datum, Betrag und Referenz,
ohne laufende Nummer und ohne Verwendungszweck. So bleibt derselbe Umsatz einer,
auch wenn er in zwei Dateien eines Abrufs steht (doppelter Download, camt.052 neben
camt.053) oder je Nachricht anders beschrieben ist (camt.054 löst einen Sammler aus
camt.053 auf). Eine Referenz gilt dabei als eindeutig je Konto, Tag und Betrag.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Sequence

from accounti.importers.kontoauszug import LEERE_REFERENZEN
from accounti.models import Transaktion


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


def _basis(tx: Transaktion, konto: str) -> tuple[str, bool]:
    """Grundlage des Schlüssels und ob eine Bankreferenz darin steckt."""
    kern = [konto, tx.datum.isoformat(), str(tx.betrag.normalize())]
    referenz = (tx.quelle_referenz or "").strip()
    if referenz.upper() not in LEERE_REFERENZEN:
        return "|".join([*kern, f"ref:{referenz}"]), True
    teile = [
        *kern,
        _norm(tx.verwendungszweck),
        re.sub(r"\s", "", tx.gegenkonto_iban or "").upper(),
        _norm(tx.gegenkonto_name),
    ]
    return "|".join(teile), False


def mit_schluessel(
    transaktionen: list[Transaktion], konto: str, abschnitte: Sequence[int] = ()
) -> list[Transaktion]:
    """Kopien mit Dublettenschlüssel; ``konto`` ist IBAN oder Bezeichnung der Quelle.

    Gleiche Schlüssel sind mit Bankreferenz derselbe Umsatz, ohne sie zählt die
    laufende Nummer — je Abschnitt: ``abschnitte`` nennt, wo in ``transaktionen``
    ein neuer Auszug bzw. eine neue Datei beginnt (leer: alles ein Abschnitt)."""
    beginn = set(abschnitte)
    gezaehlt: Counter[str] = Counter()
    ergebnis = []
    for i, tx in enumerate(transaktionen):
        if i in beginn:
            gezaehlt.clear()
        basis, mit_referenz = _basis(tx, konto)
        gezaehlt[basis] += 1
        nummer = 1 if mit_referenz else gezaehlt[basis]
        schluessel = hashlib.sha256(f"{basis}|{nummer}".encode()).hexdigest()
        ergebnis.append(tx.model_copy(update={"dublettenschluessel": schluessel}))
    return ergebnis
