"""Kontierung einer Banktransaktion aus ihrem Beleg.

Ist der Beleg zu einem Umsatz bekannt, muss nichts aus dem Verwendungszweck geraten
werden: Lieferant, Positionen und Steuersätze stehen auf dem Beleg. Gebucht wird je
Steuersatz, die Vorsteuer genau so, wie sie auf dem Beleg steht. Weicht der gezahlte
Betrag ab (Trinkgeld, Rundung), geht die Differenz ohne Steuer auf das Sachkonto und
die Buchung zur Prüfung.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from accounti.klassifikation.engine import RegelwerkEngine
from accounti.konfiguration import Buchhaltung
from accounti.kontakte.erkennung import finde_kontakt
from accounti.models import (
    Beleg,
    Belegrichtung,
    Buchungssatz,
    BuchungStatus,
    Kontakt,
    KontaktStatus,
    Transaktion,
    TransaktionQuelle,
)

NULL = Decimal("0")
_VST = {Decimal("19"): 9, Decimal("7"): 8}
_UST = {Decimal("19"): 3, Decimal("7"): 2}
_ERLOES = {Decimal("19"): "8400", Decimal("7"): "8300"}
_ERLOES_UNBEKANNT = "8200"


@dataclass(frozen=True)
class Sachkonto:
    konto: str
    pruefen: bool
    quelle: str


def sachkonto_fuer_beleg(
    beleg: Beleg,
    kontakt: Kontakt | None,
    einstellungen: Buchhaltung,
    regelwerk: RegelwerkEngine | None,
    umsatz: Transaktion | None = None,
) -> Sachkonto:
    """Aufwandskonto: Kontakt-Vorschlag, Regelwerk auf die Belegdaten, Regelwerk auf
    den Umsatz, sonst der Standardaufwand (zur Prüfung)."""
    ungeprueft = kontakt is not None and kontakt.status is not KontaktStatus.GEPRUEFT
    if kontakt is not None and kontakt.sachkonto:
        return Sachkonto(kontakt.sachkonto, ungeprueft, f"Kontakt {kontakt.name}")
    if regelwerk is not None:
        name = beleg.lieferant_name or (kontakt.name if kontakt else None)
        text = " ".join(
            filter(
                None, [beleg.belegnummer, *(p.bezeichnung for p in beleg.positionen)]
            )
        )
        pseudo = Transaktion(
            datum=beleg.belegdatum or beleg.eingegangen_am.date(),
            betrag=-(beleg.brutto or NULL),
            verwendungszweck=text or name or "",
            gegenkonto_name=name,
            quelle=TransaktionQuelle.MANUELL,
            rohtext=f"Beleg {beleg.id}",
        )
        for quelle, tx in (("Belegdaten", pseudo), ("Umsatz", umsatz)):
            if tx is None:
                continue
            ergebnis = regelwerk.klassifiziere(tx)
            # nur Ausgaberegeln (… an Bank) taugen als Aufwandskonto
            if (
                ergebnis is not None
                and ergebnis.haben_konto == einstellungen.bank_konto
            ):
                return Sachkonto(ergebnis.soll_konto, ungeprueft, f"Regel ({quelle})")
    return Sachkonto(einstellungen.standard_aufwand, True, "Standard")


@dataclass
class _Gruppe:
    konto: str
    schluessel: int | None
    pruefen: bool
    netto: Decimal = NULL
    steuer: Decimal = NULL


def _saetze(beleg: Beleg) -> list[tuple[Decimal | None, Decimal, Decimal]]:
    """(Steuersatz, Netto, Steuer) je Position — ohne Positionen aus den Summen."""
    if beleg.positionen:
        return [
            (
                p.steuersatz.normalize() if p.steuersatz is not None else None,
                p.netto,
                p.steuer_betrag or NULL,
            )
            for p in beleg.positionen
        ]
    if beleg.netto is not None and beleg.steuer is not None:
        satz = None
        if beleg.steuer == 0:
            satz = NULL
        elif beleg.netto:
            satz = (beleg.steuer / beleg.netto * 100).quantize(Decimal("1")).normalize()
        return [(satz, beleg.netto, beleg.steuer)]
    return [(None, beleg.brutto or NULL, NULL)]


def kontiere_mit_beleg(
    tx: Transaktion,
    beleg: Beleg,
    einstellungen: Buchhaltung,
    regelwerk: RegelwerkEngine | None = None,
    kontakte: list[Kontakt] | tuple[Kontakt, ...] = (),
) -> list[Buchungssatz]:
    """Bucht den Umsatz aus dem Beleg: je Steuersatz ein Buchungssatz."""
    eingang = beleg.richtung is Belegrichtung.EINGANG
    sachkonto = None
    if eingang:
        kontakt, _ = finde_kontakt(
            list(kontakte),
            iban=beleg.iban,
            ust_id=beleg.lieferant_ust_id,
            name=beleg.lieferant_name,
        )
        sachkonto = sachkonto_fuer_beleg(beleg, kontakt, einstellungen, regelwerk, tx)

    gruppen: dict[tuple[str, int | None], _Gruppe] = {}
    for satz, netto, steuer in _saetze(beleg):
        if sachkonto is not None:
            konto, pruefen = sachkonto.konto, sachkonto.pruefen
            schluessel = _VST.get(satz) if satz is not None else None
        else:
            konto = _ERLOES.get(satz, _ERLOES_UNBEKANNT) if satz else _ERLOES_UNBEKANNT
            schluessel, pruefen = (
                (_UST.get(satz) if satz else None),
                satz not in _ERLOES,
            )
        if schluessel is None and satz != 0:
            pruefen = True  # Steuersatz unbekannt: brutto buchen, Mensch entscheidet
        g = gruppen.setdefault((konto, schluessel), _Gruppe(konto, schluessel, pruefen))
        g.pruefen = g.pruefen or pruefen
        if schluessel is None:
            g.netto += netto + steuer
        else:
            g.netto += netto
            g.steuer += steuer

    # Gezahlt ≠ Beleg (Trinkgeld, Rundung): Differenz ohne Steuer, zur Prüfung
    gutschrift = (beleg.brutto or NULL) < 0
    belegsumme = sum((abs(g.netto) + abs(g.steuer) for g in gruppen.values()), NULL)
    differenz = abs(tx.betrag) - belegsumme
    if differenz:
        groesste = max(gruppen.values(), key=lambda g: abs(g.netto))
        groesste.netto += -differenz if gutschrift else differenz
        groesste.pruefen = True

    text = f"{beleg.lieferant_name or ''} {beleg.belegnummer or ''}".strip()
    buchungen = []
    for g in gruppen.values():
        soll, haben = g.konto, einstellungen.bank_konto
        if not eingang:
            soll, haben = haben, soll
        if gutschrift:
            soll, haben = haben, soll
        buchungen.append(
            Buchungssatz(
                transaktion_id=tx.id,
                beleg_id=beleg.id,
                datum=tx.datum,
                soll_konto=soll,
                haben_konto=haben,
                betrag_netto=abs(g.netto),
                steuer_schluessel=g.schluessel,
                steuer_betrag=abs(g.steuer) if g.schluessel is not None else None,
                buchungstext=(text or tx.verwendungszweck)[:60],
                beleg_nummer=(beleg.belegnummer or "")[:36] or None,
                status=BuchungStatus.ZUR_PRUEFUNG
                if g.pruefen
                else BuchungStatus.AUTO_GEBUCHT,
                confidence=0.5 if g.pruefen else 1.0,
            )
        )
    return buchungen
