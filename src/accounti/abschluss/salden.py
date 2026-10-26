"""Kontobewegungen und Summen- und Saldenliste.

Ein Buchungssatz mit Steuer (BU-Schlüssel 2, 3, 8, 9) trägt Nettobetrag und Steuer. In
der Saldenliste wird er in drei Bewegungen zerlegt: die Nettoseite (das Konto, das kein
Geld- oder Personenkonto ist), die Steuer auf derselben Seite auf das Steuerkonto, die
Gegenseite brutto. Haben beide Seiten dieselbe Natur, entscheidet der Schlüssel:
Vorsteuer → Soll ist netto, Umsatzsteuer → Haben ist netto. So buchen Kontierung,
Belegbuchung, offene Posten und Skonto in accounti.

§ 13b und ig. Erwerb (94/91, 19/18): Die Steuer steckt nicht im Zahlbetrag. Beide
Seiten tragen das Netto, die Steuer steht als Vorsteuer und als Umsatzsteuer auf dem
Steuerpaar des Kontenrahmens (z. B. SKR03 1577/1787) — ergebnisneutral.

Gezählt werden nur freigegebene Buchungen — wie im DATEV-Export.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.abschluss.kontenrahmen import Gewinnermittlung, Kontenart, Kontenrahmen
from accounti.db.repository import lade_buchungen
from accounti.models import Buchungssatz, BuchungStatus

NULL = Decimal("0")

FREIGEGEBEN = frozenset(
    {
        BuchungStatus.AUTO_GEBUCHT,
        BuchungStatus.GEPRUEFT,
        BuchungStatus.KORRIGIERT,
        BuchungStatus.EXPORTIERT,
    }
)
VORSCHLAG = frozenset({BuchungStatus.ENTWURF, BuchungStatus.ZUR_PRUEFUNG})


@dataclass(frozen=True)
class Bewegung:
    konto: str
    datum: date
    soll: Decimal
    haben: Decimal
    buchung_id: UUID
    eroeffnung: bool  # gegen ein Saldenvortragskonto (EB-Wert)


def bewegungen(b: Buchungssatz, kr: Kontenrahmen) -> list[Bewegung]:
    eb = kr.ist_saldenvortrag(b.soll_konto) or kr.ist_saldenvortrag(b.haben_konto)

    def bw(konto: str, soll: Decimal = NULL, haben: Decimal = NULL) -> Bewegung:
        return Bewegung(konto, b.datum, soll, haben, b.id, eb)

    netto = b.betrag_netto
    steuer = b.steuer_betrag or NULL
    paar = kr.steuerpaar(b.steuer_schluessel)
    if paar is not None and steuer:
        vorsteuer, umsatzsteuer = paar
        soll_geld = kr.ist_geldkonto(b.soll_konto)
        haben_geld = kr.ist_geldkonto(b.haben_konto)
        # Bezug: Sachkonto im Soll; Minderung (Sachkonto im Haben): Paar gedreht
        bezug = haben_geld if soll_geld != haben_geld else True
        steuerseiten = (
            [bw(vorsteuer, soll=steuer), bw(umsatzsteuer, haben=steuer)]
            if bezug
            else [bw(vorsteuer, haben=steuer), bw(umsatzsteuer, soll=steuer)]
        )
        return [
            bw(b.soll_konto, soll=netto),
            bw(b.haben_konto, haben=netto),
            *steuerseiten,
        ]
    steuerkonto = kr.steuerkonto(b.steuer_schluessel)
    if steuerkonto is None or steuer == 0:
        return [bw(b.soll_konto, soll=netto), bw(b.haben_konto, haben=netto)]
    soll_geld = kr.ist_geldkonto(b.soll_konto)
    haben_geld = kr.ist_geldkonto(b.haben_konto)
    if soll_geld != haben_geld:
        netto_im_soll = haben_geld
    else:
        netto_im_soll = kr.ist_vorsteuer(b.steuer_schluessel)
    brutto = netto + steuer
    if netto_im_soll:
        return [
            bw(b.soll_konto, soll=netto),
            bw(steuerkonto, soll=steuer),
            bw(b.haben_konto, haben=brutto),
        ]
    return [
        bw(b.soll_konto, soll=brutto),
        bw(b.haben_konto, haben=netto),
        bw(steuerkonto, haben=steuer),
    ]


def lade_bewegungen(
    session: Session,
    kr: Kontenrahmen,
    von: date | None = None,
    bis: date | None = None,
) -> list[Bewegung]:
    """Bewegungen aus freigegebenen Buchungen im Zeitraum (Grenzen eingeschlossen)."""
    ergebnis: list[Bewegung] = []
    for b in lade_buchungen(session, status=set(FREIGEGEBEN)):
        if (von is None or b.datum >= von) and (bis is None or b.datum <= bis):
            ergebnis.extend(bewegungen(b, kr))
    return ergebnis


@dataclass
class SusaZeile:
    konto: str
    bezeichnung: str
    art: Kontenart
    eb: Decimal = NULL  # Eröffnungssaldo (Soll − Haben)
    soll: Decimal = NULL  # Verkehrszahlen ohne EB
    haben: Decimal = NULL

    @property
    def saldo(self) -> Decimal:
        return self.eb + self.soll - self.haben


@dataclass
class Susa:
    jahr: int
    bis: date
    gewinnermittlung: Gewinnermittlung
    zeilen: list[SusaZeile] = field(default_factory=list)

    def zeile(self, konto: str) -> SusaZeile | None:
        return next((z for z in self.zeilen if z.konto == konto), None)

    def saldo(self, konto: str) -> Decimal:
        z = self.zeile(konto)
        return z.saldo if z is not None else NULL

    @property
    def summe_soll(self) -> Decimal:
        return sum((z.soll + max(z.eb, NULL) for z in self.zeilen), NULL)

    @property
    def summe_haben(self) -> Decimal:
        return sum((z.haben + max(-z.eb, NULL) for z in self.zeilen), NULL)

    @property
    def ergebnis(self) -> Decimal:
        """Saldo der Erfolgskonten, Gewinn positiv (bei EÜR inkl. Steuerkonten)."""
        return -sum((z.saldo for z in self.zeilen if z.art is Kontenart.ERFOLG), NULL)


def summen_und_salden(
    session: Session,
    jahr: int,
    kr: Kontenrahmen,
    gewinnermittlung: Gewinnermittlung,
    bis: date | None = None,
) -> Susa:
    """Summen- und Saldenliste des Geschäftsjahres (Kalenderjahr) bis zum Stichtag."""
    stichtag = bis or date(jahr, 12, 31)
    werte: dict[str, list[Decimal]] = defaultdict(lambda: [NULL, NULL, NULL])
    for bw in lade_bewegungen(session, kr, date(jahr, 1, 1), stichtag):
        w = werte[bw.konto]
        if bw.eroeffnung:
            w[0] += bw.soll - bw.haben
        else:
            w[1] += bw.soll
            w[2] += bw.haben
    susa = Susa(jahr, stichtag, gewinnermittlung)
    for konto in sorted(werte, key=lambda k: (len(k), k)):
        eb, soll, haben = werte[konto]
        susa.zeilen.append(
            SusaZeile(
                konto,
                kr.bezeichnung(konto),
                kr.art(konto, gewinnermittlung),
                eb,
                soll,
                haben,
            )
        )
    return susa
