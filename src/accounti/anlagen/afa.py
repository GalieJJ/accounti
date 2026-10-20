"""AfA-Plan — rein rechnend, ohne Datenbank.

Linear wird über die Kumulierte gerechnet: AfA bis Monat k = AK · k / (12 · ND),
kaufmännisch gerundet. Der Jahresbetrag ist die Differenz zweier Kumulierter — so
entsteht keine Rundungsdrift, und die Summe ist exakt die Anschaffungskosten.

Im Anschaffungsjahr zählt der Anschaffungsmonat voll (§ 7 Abs. 1 Satz 4 EStG: es
entfallen nur die vollen Monate davor), im Abgangsjahr zählt der Abgangsmonat voll
(R 7.4 Abs. 8 EStR, monatsweise).
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from accounti.anlagen.rechtsstand import Grenzen, Rechtsstand
from accounti.anzeige import betrag_de
from accounti.models.anlagen import AfaArt, Anlagegut

NULL = Decimal("0")
CENT = Decimal("0.01")

Verteilung = Literal["monatlich", "sofort", "jahresende"]


class AfaRegelError(ValueError):
    """Das Anlagegut verstößt gegen eine AfA-Regel (Grenze, Fenster, Wahlrecht)."""


def runde(betrag: Decimal) -> Decimal:
    return betrag.quantize(CENT, rounding=ROUND_HALF_UP)


def monatsende(jahr: int, monat: int) -> date:
    return date(jahr, monat, calendar.monthrange(jahr, monat)[1])


@dataclass(frozen=True)
class AfaJahr:
    jahr: int
    start_monat: int  # erster Monat mit AfA in diesem Jahr
    monate: int  # Monate mit AfA in diesem Jahr
    betrag: Decimal
    kumuliert: Decimal  # AfA bis Jahresende
    restbuchwert: Decimal
    rechenweg: str
    verteilung: Verteilung = "monatlich"


@dataclass
class AfaPlan:
    anschaffungskosten: Decimal
    anschaffungsjahr: int
    jahre: list[AfaJahr] = field(default_factory=list)
    satz: Decimal | None = None  # degressiv: Anteil vom Restbuchwert
    abgang: date | None = None

    def jahr(self, jahr: int) -> AfaJahr | None:
        return next((j for j in self.jahre if j.jahr == jahr), None)

    def kumuliert_bis(self, jahr: int, monat: int = 12) -> Decimal:
        """AfA vom Beginn bis zum Ende des Monats ``monat`` in ``jahr``."""
        vorher = NULL
        for j in self.jahre:
            if j.jahr < jahr:
                vorher = j.kumuliert
                continue
            if j.jahr > jahr:
                break
            return vorher + self._anteil(j, monat)
        return vorher

    def afa_im_jahr(self, jahr: int, bis_monat: int = 12) -> Decimal:
        return self.kumuliert_bis(jahr, bis_monat) - self.kumuliert_bis(jahr - 1, 12)

    def restbuchwert(self, jahr: int, monat: int = 12) -> Decimal:
        if (jahr, monat) < (self.anschaffungsjahr, 1):
            return NULL
        return self.anschaffungskosten - self.kumuliert_bis(jahr, monat)

    @staticmethod
    def _anteil(j: AfaJahr, monat: int) -> Decimal:
        aktiv = min(max(monat - j.start_monat + 1, 0), j.monate)
        if j.verteilung == "sofort":
            return j.betrag if aktiv > 0 else NULL
        if j.verteilung == "jahresende":
            return j.betrag if monat == 12 else NULL
        if aktiv == j.monate:
            return j.betrag
        return runde(j.betrag * aktiv / j.monate)


def _ende_im_jahr(anlage: Anlagegut, jahr: int) -> tuple[int, bool]:
    """(letzter Monat mit AfA, ist Abgangsjahr)."""
    a = anlage.abgang_datum
    if a is not None and a.year == jahr:
        return a.month, True
    return 12, False


def _nd(anlage: Anlagegut) -> int:
    if anlage.nutzungsdauer is None:
        msg = f"{anlage.bezeichnung}: Nutzungsdauer fehlt ({anlage.afa_art.value})"
        raise AfaRegelError(msg)
    return anlage.nutzungsdauer


def _linear(anlage: Anlagegut) -> AfaPlan:
    ak, start = anlage.anschaffungskosten, anlage.anschaffungsdatum
    gesamt = 12 * _nd(anlage)
    plan = AfaPlan(ak, start.year, abgang=anlage.abgang_datum)
    k, kum, jahr = 0, NULL, start.year
    while k < gesamt:
        von = start.month if jahr == start.year else 1
        bis, abgang = _ende_im_jahr(anlage, jahr)
        monate = min(bis - von + 1, gesamt - k)
        if monate <= 0:
            break
        k += monate
        neu = min(ak, runde(ak * k / gesamt))
        rechenweg = f"linear: {betrag_de(ak)} × {monate}/{gesamt} Monate"
        rbw = ak - neu
        plan.jahre.append(AfaJahr(jahr, von, monate, neu - kum, neu, rbw, rechenweg))
        kum = neu
        if abgang:
            break
        jahr += 1
    return plan


def _degressiv(anlage: Anlagegut, rechtsstand: Rechtsstand) -> AfaPlan:
    fenster = rechtsstand.degressiv_am(anlage.anschaffungsdatum)
    if fenster is None:
        msg = f"degressive AfA am {anlage.anschaffungsdatum:%d.%m.%Y} nicht zulässig"
        raise AfaRegelError(f"{anlage.bezeichnung}: {msg}")
    nd = _nd(anlage)
    satz = fenster.satz(nd)
    prozent = f"{satz * 100:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    ak, start = anlage.anschaffungskosten, anlage.anschaffungsdatum
    plan = AfaPlan(ak, start.year, satz=satz, abgang=anlage.abgang_datum)
    rbw, rest, kum, jahr, linear = ak, 12 * nd, NULL, start.year, False
    while rest > 0 and rbw > 0:
        von = start.month if jahr == start.year else 1
        bis, abgang = _ende_im_jahr(anlage, jahr)
        monate = min(bis - von + 1, rest)
        if monate <= 0:
            break
        # § 7 Abs. 3: Wechsel, sobald linear (Restwert / Restnutzungsdauer) mehr bringt
        if not linear and anlage.wechsel_linear and Decimal(12) / rest >= satz:
            linear = True
        if monate == rest:
            betrag = rbw
            rechenweg = (
                f"Restbuchwert {betrag_de(rbw)} im letzten Jahr der Nutzungsdauer"
            )
        elif linear:
            betrag = runde(rbw * monate / rest)
            rechenweg = (
                f"linear (Wechsel § 7 Abs. 3): {betrag_de(rbw)} × {monate}/{rest} "
                "Restmonate"
            )
        else:
            betrag = runde(rbw * satz * monate / 12)
            rechenweg = f"degressiv {prozent} % von {betrag_de(rbw)} × {monate}/12"
        betrag = min(betrag, rbw)
        rbw -= betrag
        kum += betrag
        rest -= monate
        plan.jahre.append(AfaJahr(jahr, von, monate, betrag, kum, rbw, rechenweg))
        if abgang:
            break
        jahr += 1
    return plan


def _sofort(anlage: Anlagegut, grund: str) -> AfaPlan:
    ak, start = anlage.anschaffungskosten, anlage.anschaffungsdatum
    plan = AfaPlan(ak, start.year, abgang=anlage.abgang_datum)
    rechenweg = f"{grund}: {betrag_de(ak)} im Anschaffungsjahr"
    plan.jahre.append(
        AfaJahr(start.year, start.month, 1, ak, ak, NULL, rechenweg, "sofort")
    )
    return plan


def _fuenftel(ak: Decimal, jahr: int, text: str) -> AfaPlan:
    plan = AfaPlan(ak, jahr)
    teil, kum = runde(ak / 5), NULL
    for i in range(5):
        betrag = ak - kum if i == 4 else teil
        kum += betrag
        rechenweg = f"{text}: 1/5 von {betrag_de(ak)} zum Jahresende"
        plan.jahre.append(
            AfaJahr(jahr + i, 12, 1, betrag, kum, ak - kum, rechenweg, "jahresende")
        )
    return plan


def _im_sammelposten(anlage: Anlagegut) -> bool:
    """Scheidet ein Gut im Anschaffungsjahr aus, gehört es nicht in den Sammelposten
    (BMF 30.09.2010, Rz. 10)."""
    a = anlage.abgang_datum
    return a is None or a.year != anlage.anschaffungsdatum.year


def _e_fahrzeug(anlage: Anlagegut, rechtsstand: Rechtsstand) -> AfaPlan:
    staffel = rechtsstand.e_fahrzeug_am(anlage.anschaffungsdatum)
    if staffel is None:
        msg = (
            f"{anlage.bezeichnung}: Elektrofahrzeug-AfA (§ 7 Abs. 2a EStG) am "
            f"{anlage.anschaffungsdatum:%d.%m.%Y} nicht zulässig"
        )
        raise AfaRegelError(msg)
    ak, start = anlage.anschaffungskosten, anlage.anschaffungsdatum
    plan = AfaPlan(ak, start.year, abgang=anlage.abgang_datum)
    kum = NULL
    for i, prozent in enumerate(staffel.saetze):
        jahr = start.year + i
        bis, abgang = _ende_im_jahr(anlage, jahr)
        voll = ak - kum if i == len(staffel.saetze) - 1 else runde(ak * prozent / 100)
        verteilung: Verteilung
        if i == 0:
            betrag, von, monate, verteilung = voll, start.month, 1, "sofort"
            rechenweg = (
                f"§ 7 Abs. 2a: {prozent} % von {betrag_de(ak)} (ohne Zwölftelung)"
            )
        else:
            von, monate, verteilung = 1, bis, "monatlich"
            betrag = voll if bis == 12 else runde(voll * bis / 12)
            rechenweg = f"§ 7 Abs. 2a: {prozent} % von {betrag_de(ak)} × {bis}/12"
        kum += betrag
        plan.jahre.append(
            AfaJahr(jahr, von, monate, betrag, kum, ak - kum, rechenweg, verteilung)
        )
        if abgang:
            break
    return plan


def plane(anlage: Anlagegut, rechtsstand: Rechtsstand) -> AfaPlan:
    """AfA-Plan eines einzelnen Anlageguts (Sammelposten: sein Fünftel-Anteil)."""
    art = anlage.afa_art
    if art is AfaArt.LINEAR:
        return _linear(anlage)
    if art is AfaArt.DEGRESSIV:
        return _degressiv(anlage, rechtsstand)
    if art is AfaArt.GWG:
        return _sofort(anlage, "GWG-Sofortabzug § 6 Abs. 2 EStG")
    if art is AfaArt.DIGITAL:
        return _sofort(anlage, "digitales Wirtschaftsgut, ND 1 Jahr (BMF 22.02.2022)")
    if art is AfaArt.E_FAHRZEUG:
        return _e_fahrzeug(anlage, rechtsstand)
    if art is AfaArt.SAMMELPOSTEN and _im_sammelposten(anlage):
        return _fuenftel(
            anlage.anschaffungskosten,
            anlage.anschaffungsdatum.year,
            "Anteil am Sammelposten",
        )
    # nicht abnutzbar oder im Anschaffungsjahr aus dem Sammelposten ausgeschieden
    return AfaPlan(
        anlage.anschaffungskosten,
        anlage.anschaffungsdatum.year,
        abgang=anlage.abgang_datum,
    )


def sammelposten_mitglieder(
    konto: str, jahr: int, anlagen: Iterable[Anlagegut]
) -> list[Anlagegut]:
    return [
        a
        for a in anlagen
        if a.afa_art is AfaArt.SAMMELPOSTEN
        and a.konto == konto
        and a.anschaffungsdatum.year == jahr
        and _im_sammelposten(a)
    ]


def plane_sammelposten(
    konto: str, jahr: int, anlagen: Iterable[Anlagegut], rechtsstand: Rechtsstand
) -> AfaPlan:
    """Sammelposten eines Jahrgangs: 1/5 der Summe je Jahr (§ 6 Abs. 2a EStG).

    Der Abgang eines Wirtschaftsguts mindert den Posten nicht (BMF 30.09.2010, Rz. 14).
    """
    summe = sum(
        (a.anschaffungskosten for a in sammelposten_mitglieder(konto, jahr, anlagen)),
        NULL,
    )
    if summe == 0:
        return AfaPlan(NULL, jahr)
    return _fuenftel(summe, jahr, f"Sammelposten {konto}/{jahr}")


# --- Regeln -----------------------------------------------------------------------


def _euro(betrag: Decimal) -> str:
    return f"{betrag_de(betrag)} €"


def pruefe_anlage(
    anlage: Anlagegut,
    rechtsstand: Rechtsstand,
    andere: Iterable[Anlagegut] = (),
) -> None:
    """Grenzen, Fenster und Wahlrechte am Anschaffungstag; Fehler als AfaRegelError."""
    tag, kosten, art = (
        anlage.anschaffungsdatum,
        anlage.anschaffungskosten,
        anlage.afa_art,
    )
    g = rechtsstand.grenzen_am(tag)
    if anlage.abgang_datum is not None and anlage.abgang_datum < tag:
        raise AfaRegelError(f"{anlage.bezeichnung}: Abgang vor der Anschaffung")
    if art in (AfaArt.LINEAR, AfaArt.DEGRESSIV):
        _nd(anlage)
    if anlage.immateriell and art in (
        AfaArt.DEGRESSIV,
        AfaArt.GWG,
        AfaArt.SAMMELPOSTEN,
        AfaArt.E_FAHRZEUG,
    ):
        msg = f"{art.value} nur für bewegliche (materielle) Wirtschaftsgüter"
        raise AfaRegelError(f"{anlage.bezeichnung}: {msg}")
    am = f"am {tag:%d.%m.%Y}"
    if art is AfaArt.DEGRESSIV and rechtsstand.degressiv_am(tag) is None:
        msg = f"degressive AfA für Anschaffungen {am} nicht zulässig"
        raise AfaRegelError(f"{anlage.bezeichnung}: {msg}")
    if art is AfaArt.E_FAHRZEUG and rechtsstand.e_fahrzeug_am(tag) is None:
        msg = f"Elektrofahrzeug-AfA (§ 7 Abs. 2a EStG) {am} nicht zulässig"
        raise AfaRegelError(f"{anlage.bezeichnung}: {msg}")
    if art is AfaArt.DIGITAL and not rechtsstand.digital_am(tag):
        msg = "ND 1 Jahr für digitale Wirtschaftsgüter gilt erst ab 2021"
        raise AfaRegelError(f"{anlage.bezeichnung}: {msg}")
    if art is AfaArt.GWG and kosten > g.gwg:
        msg = (
            f"{anlage.bezeichnung}: GWG nur bis {_euro(g.gwg)} netto bei Anschaffung "
            f"am {tag:%d.%m.%Y} ({g.quelle}) — {_euro(kosten)} liegt darüber"
        )
        raise AfaRegelError(msg)
    if art is AfaArt.SAMMELPOSTEN and not g.im_sammelposten_bereich(kosten):
        bereich = (
            f"mehr als {_euro(g.sammelposten_von)} bis {_euro(g.sammelposten_bis)}"
            if g.sammelposten_von is not None and g.sammelposten_bis is not None
            else "gar nicht"
        )
        msg = (
            f"{anlage.bezeichnung}: Sammelposten am {tag:%d.%m.%Y} nur {bereich} netto"
        )
        raise AfaRegelError(msg)
    if g.pflicht and not anlage.immateriell:
        soll = (
            AfaArt.GWG
            if kosten <= g.gwg
            else AfaArt.SAMMELPOSTEN
            if g.im_sammelposten_bereich(kosten)
            else None
        )
        if soll is not None and art is not soll:
            msg = f"{soll.value} ist bei Anschaffung {am} zwingend ({g.quelle})"
            raise AfaRegelError(f"{anlage.bezeichnung}: {msg}")
    _pruefe_einheitlich(anlage, g, andere)


def _pruefe_einheitlich(
    anlage: Anlagegut, g: Grenzen, andere: Iterable[Anlagegut]
) -> None:
    """§ 6 Abs. 2a Satz 5 EStG: Sammelposten einheitlich für alle Güter des Jahres."""
    jahr = anlage.anschaffungsdatum.year
    kandidaten = [
        anlage,
        *(a for a in andere if a.id != anlage.id and a.anschaffungsdatum.year == jahr),
    ]
    im_bereich = [
        a
        for a in kandidaten
        if not a.immateriell and g.im_sammelposten_bereich(a.anschaffungskosten)
    ]
    sammel = [a for a in im_bereich if a.afa_art is AfaArt.SAMMELPOSTEN]
    abweichend = [a for a in im_bereich if a.afa_art is not AfaArt.SAMMELPOSTEN]
    if sammel and abweichend:
        namen = ", ".join(a.bezeichnung for a in abweichend)
        msg = (
            f"Sammelposten {jahr}: Das Wahlrecht gilt einheitlich für alle Güter von "
            f"mehr als {_euro(g.sammelposten_von or NULL)} bis "
            f"{_euro(g.sammelposten_bis or NULL)} — nicht im Sammelposten: {namen}"
        )
        raise AfaRegelError(msg)


@dataclass(frozen=True)
class Vorschlag:
    art: AfaArt
    begruendung: str


def schlage_art_vor(
    kosten: Decimal,
    tag: date,
    rechtsstand: Rechtsstand,
    sammelposten_jahr: bool = False,
    nutzungsdauer: int | None = None,
) -> Vorschlag:
    """Vorschlag der AfA-Art — der Mensch entscheidet (Wahlrechte)."""
    g = rechtsstand.grenzen_am(tag)
    if g.pflicht and kosten <= g.gwg:
        return Vorschlag(AfaArt.GWG, f"bis {_euro(g.gwg)}: Sofortabzug zwingend")
    if g.pflicht and g.im_sammelposten_bereich(kosten):
        return Vorschlag(AfaArt.SAMMELPOSTEN, f"Sammelposten zwingend ({g.quelle})")
    if g.im_sammelposten_bereich(kosten) and sammelposten_jahr:
        return Vorschlag(
            AfaArt.SAMMELPOSTEN,
            f"im Jahr {tag.year} gibt es einen Sammelposten — Wahlrecht einheitlich",
        )
    if kosten <= g.gwg:
        return Vorschlag(
            AfaArt.GWG,
            f"bis {_euro(g.gwg)} netto: Sofortabzug als GWG (§ 6 Abs. 2 EStG)",
        )
    text = "lineare AfA über die Nutzungsdauer"
    fenster = rechtsstand.degressiv_am(tag)
    if fenster is not None:
        satz = fenster.satz(nutzungsdauer) if nutzungsdauer else None
        text += (
            f"; degressiv möglich: höchstens {fenster.faktor}-fach, "
            f"höchstens {fenster.hoechstsatz} %"
            + (f" (hier {satz * 100:.2f} %)" if satz is not None else "")
        )
    if g.im_sammelposten_bereich(kosten):
        text += "; Sammelposten möglich (einheitlich für das ganze Jahr)"
    return Vorschlag(AfaArt.LINEAR, text)
