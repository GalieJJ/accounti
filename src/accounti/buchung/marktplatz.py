"""Bankumsätze, die der Marktplatz-Abgleich erwartet — ``classify`` lässt sie offen.

Eine Auszahlung von Amazon, eBay, Shopify oder PayPal ist eine Geldbewegung (Bank an
Verrechnungskonto); Erlöse und Gebühren bucht die Abrechnung (``accounti marktplatz
import``), die den Bankumsatz danach abgleicht (``integrationen.auszahlung``). Bucht
``classify`` ihn vorher nach einer Regel als Erlös mit Umsatzsteuer oder als Aufwand,
stehen Erlöse doppelt bzw. Vorsteuer falsch in der Voranmeldung — die Auszahlung ist
Nettobetrag nach Gebühren, kein Entgelt (§ 10 Abs. 1 UStG). Offen bleibt deshalb:

* ein Zahlungseingang mit einem Stichwort eines Marktplatzes
  (``integrationen.marktplaetze.<name>.bank_stichworte``), solange keine Abrechnung
  ihn abgeglichen hat — ohne Marktplatz-Import schaltet ``bank_stichworte: []`` das ab;
* jeder Umsatz, den eine importierte Abrechnung noch erwartet (offene Aus- oder
  Einzahlung, auch mit Abgleichsbefund): im Zeitfenster des Abgleichs, mit gleichem
  Vorzeichen und mit Stichwort, Abrechnungsnummer oder genau dem erwarteten Betrag.

Umsätze des PayPal-Kontos selbst und der Verrechnungskonten kontiert ``classify`` wie
bisher (wie ``gleiche_auszahlungen_ab`` sie auch nicht als Bankumsatz nimmt).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from accounti.db.repo_integrationen import lade_abrechnungen
from accounti.integrationen.einstellungen import Integrationen
from accounti.models import Transaktion, TransaktionQuelle
from accounti.models.integrationen import Postenart

VORLAUF = timedelta(days=2)  # wie integrationen.auszahlung: Bank bucht selten früher


@dataclass(frozen=True)
class _Erwartet:
    marktplatz: str
    nummer: str
    von: date
    bis: date
    eingang: bool  # Auszahlung (Bank +) oder Einzahlung (Bank −)
    betrag: Decimal | None  # None: Fremdwährung ohne Kurs


class Marktplatzauszahlungen:
    """Erkennt Umsätze, die auf ihre Abrechnung warten (einmal je Lauf geladen)."""

    def __init__(
        self, session: Session, integrationen: Integrationen, bank_konto: str
    ) -> None:
        self.einstellungen = integrationen
        self.bank_konto = bank_konto
        self.verrechnungskonten = {
            k.verrechnungskonto for k in integrationen.marktplaetze.values()
        }
        toleranz = timedelta(days=integrationen.auszahlung_toleranz_tage)
        self.erwartet: list[_Erwartet] = []
        for a in lade_abrechnungen(session):
            for p in a.posten:
                if (
                    p.art not in (Postenart.AUSZAHLUNG, Postenart.EINZAHLUNG)
                    or p.bank_transaktion_id is not None
                ):
                    continue
                betrag = p.betrag_eur if p.betrag_eur is not None else p.betrag
                fremd = a.waehrung != "EUR" and p.betrag_eur is None
                self.erwartet.append(
                    _Erwartet(
                        a.marktplatz,
                        a.nummer.upper(),
                        p.datum - VORLAUF,
                        p.datum + toleranz,
                        p.art is Postenart.AUSZAHLUNG,
                        None if fremd else -betrag,
                    )
                )

    def _stichwort(self, marktplatz: str, text: str) -> bool:
        konten = self.einstellungen.marktplaetze.get(marktplatz)
        return konten is not None and any(
            w.strip() and w.upper() in text for w in konten.bank_stichworte
        )

    def marktplatz(self, tx: Transaktion) -> str | None:
        """Der Marktplatz, auf dessen Abrechnung der Umsatz wartet — sonst None."""
        if tx.quelle is TransaktionQuelle.PAYPAL or not tx.betrag:
            return None
        if (tx.sachkonto or self.bank_konto) in self.verrechnungskonten:
            return None
        text = f"{tx.verwendungszweck} {tx.gegenkonto_name or ''}".upper()
        for x in self.erwartet:
            if not (x.von <= tx.datum <= x.bis) or (tx.betrag > 0) != x.eingang:
                continue
            if (
                tx.betrag == x.betrag
                or x.nummer in text
                or self._stichwort(x.marktplatz, text)
            ):
                return x.marktplatz
        if tx.betrag > 0:
            for name in self.einstellungen.marktplaetze:
                if self._stichwort(name, text):
                    return name
        return None


def hinweis(marktplaetze: set[str], anzahl: int) -> str:
    """Was mit offen gelassenen Auszahlungen zu tun ist (für classify, bank lauf)."""
    namen = ", ".join(sorted(marktplaetze))
    return (
        f"{anzahl} Marktplatz-Umsatz/-Umsätze ({namen}) offen gelassen: Erlöse und "
        "Gebühren stehen in der Abrechnung — accounti marktplatz import <marktplatz> "
        "<datei>, dann gleicht accounti die Auszahlung ab (Bank an Verrechnungskonto). "
        "Ohne Marktplatz-Import: integrationen.marktplaetze.<name>.bank_stichworte: []"
    )
