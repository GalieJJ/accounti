"""Abschlussprüfungen — benannte Prüfungen, die Befunde liefern und nie Daten ändern.

Ein Befund der Schwere „Fehler“ blockiert den Abschluss (Saldovortrag). Baustein 7
(Prüfmechanik, Perioden) gibt es noch nicht; die Befunde hier sind bewusst schlicht.
"""

from __future__ import annotations

import enum
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cached_property
from pathlib import Path

from sqlalchemy.orm import Session

from accounti.abschluss.kassenbuch import bestand
from accounti.abschluss.konfiguration import (
    AbschlussEinstellungen,
    KassenEinstellungen,
    lade_abschluss,
    lade_kasse,
)
from accounti.abschluss.kontenrahmen import Kontenart, Kontenrahmen
from accounti.abschluss.protokoll import pruefe_protokoll
from accounti.abschluss.salden import VORSCHLAG, Susa, summen_und_salden
from accounti.anlagen.konfiguration import AnlagenEinstellungen, lade_anlagen
from accounti.anlagen.lauf import afa_positionen
from accounti.anlagen.spiegel import anlagenspiegel
from accounti.anzeige import betrag_de
from accounti.db.repo_abschluss import (
    kontoauszugssaldo,
    lade_abgrenzungen,
    lade_gesperrte_jahre,
    speichere_kontoauszugssaldo,
)
from accounti.db.repo_anlagen import lade_anlagen as lade_anlagegueter
from accounti.db.repo_kasse import lade_kassenbuch
from accounti.db.repository import (
    gebuchte_transaktion_ids,
    lade_bankkonten,
    lade_bankkonto,
    lade_buchungen,
    lade_transaktionen,
)
from accounti.models.abschluss import AbgrenzungStatus, Kontoauszugssaldo

NULL = Decimal("0")


class Schwere(str, enum.Enum):
    FEHLER = "fehler"  # blockiert den Abschluss
    WARNUNG = "warnung"
    HINWEIS = "hinweis"


@dataclass(frozen=True)
class Befund:
    pruefung: str
    schwere: Schwere
    text: str


@dataclass
class Abschlusskontext:
    session: Session
    jahr: int
    einstellungen: AbschlussEinstellungen
    kasse: KassenEinstellungen
    anlagen: AnlagenEinstellungen

    @property
    def stichtag(self) -> date:
        return date(self.jahr, 12, 31)

    @cached_property
    def kontenrahmen(self) -> Kontenrahmen:
        return self.einstellungen.lade_kontenrahmen()

    @cached_property
    def susa(self) -> Susa:
        return summen_und_salden(
            self.session,
            self.jahr,
            self.kontenrahmen,
            self.einstellungen.gewinnermittlung,
        )

    @property
    def euer(self) -> bool:
        return self.einstellungen.gewinnermittlung == "euer"


def kontext(session: Session, jahr: int, config: str | Path) -> Abschlusskontext:
    return Abschlusskontext(
        session, jahr, lade_abschluss(config), lade_kasse(config), lade_anlagen(config)
    )


def erfasse_kontoauszugssaldo(
    session: Session,
    konto: str,
    stichtag: date,
    saldo: Decimal,
    von: str | None = None,
) -> Kontoauszugssaldo:
    """Saldo laut Kontoauszug eines eingerichteten Bankkontos (IBAN oder ID)."""
    bankkonto = lade_bankkonto(session, konto)
    k = Kontoauszugssaldo(
        bankkonto_id=bankkonto.id, stichtag=stichtag, saldo=saldo, erfasst_von=von
    )
    speichere_kontoauszugssaldo(session, k)
    return k


def _euro(betrag: Decimal) -> str:
    return f"{betrag_de(betrag)} €"


def _liste(konten: list[str], max_anzahl: int = 6) -> str:
    rest = len(konten) - max_anzahl
    return ", ".join(konten[:max_anzahl]) + (f" und {rest} weitere" if rest > 0 else "")


# --- die Prüfungen ----------------------------------------------------------------


def _unfreigegeben(k: Abschlusskontext) -> list[Befund]:
    offen = [
        b
        for b in lade_buchungen(k.session, status=set(VORSCHLAG))
        if b.datum.year == k.jahr
    ]
    if not offen:
        return []
    text = (
        f"{len(offen)} Buchung{'en' if len(offen) > 1 else ''} im Jahr {k.jahr} "
        "nicht freigegeben — sie zählen nicht (accounti review, accounti bestaetige)"
    )
    return [Befund("unfreigegeben", Schwere.FEHLER, text)]


def _ungebucht(k: Abschlusskontext) -> list[Befund]:
    gebucht = gebuchte_transaktion_ids(k.session)
    ungebucht = [t for t in lade_transaktionen(k.session) if t.id not in gebucht]
    befunde: list[Befund] = []
    offen = [t for t in ungebucht if t.datum.year == k.jahr]
    if offen:
        summe = sum((t.betrag for t in offen), NULL)
        text = (
            f"{len(offen)} Umsätze im Jahr {k.jahr} ohne Buchung (Summe "
            f"{_euro(summe)}) — accounti opos zuordnen, bank abgleich, classify"
        )
        befunde.append(Befund("ungebucht", Schwere.FEHLER, text))
    # in abgeschlossenen Jahren überspringen classify & Co. die Umsätze
    gesperrt = lade_gesperrte_jahre(k.session) - {k.jahr}
    for jahr in sorted({t.datum.year for t in ungebucht} & gesperrt):
        alt = [t for t in ungebucht if t.datum.year == jahr]
        summe = sum((t.betrag for t in alt), NULL)
        text = (
            f"{len(alt)} Umsätze im abgeschlossenen Jahr {jahr} ohne Buchung (Summe "
            f"{_euro(summe)}) — sie werden nicht kontiert; buchen nur nach accounti "
            f"abschluss oeffnen --jahr {jahr}"
        )
        befunde.append(Befund("ungebucht", Schwere.WARNUNG, text))
    return befunde


def _bank(k: Abschlusskontext) -> list[Befund]:
    befunde: list[Befund] = []
    nach_sachkonto = defaultdict(list)
    for konto in lade_bankkonten(k.session):
        nach_sachkonto[konto.sachkonto].append(konto)
    # das Standard-Bankkonto und jedes Bankkonto des Kontenrahmens mit Bestand oder
    # Verkehr braucht ein eingerichtetes Bankkonto, sonst gibt es keinen Kontoauszug
    bank_sachkonten = {k.einstellungen.bank_konto} | {
        z.konto for z in k.susa.zeilen if k.kontenrahmen.ist_bankkonto(z.konto)
    }
    for sachkonto in sorted(bank_sachkonten - set(nach_sachkonto)):
        z = k.susa.zeile(sachkonto)
        if z is None or not (z.eb or z.soll or z.haben):
            continue
        text = (
            f"Bankkonto {sachkonto} hat Buchungen, ist aber nicht eingerichtet — der "
            "Saldo lässt sich nicht mit dem Kontoauszug abstimmen (accounti bank "
            f"verbinde … --sachkonto {sachkonto}, dann accounti abschluss saldo …)"
        )
        befunde.append(Befund("bank", Schwere.FEHLER, text))
    for sachkonto, konten in sorted(nach_sachkonto.items()):
        buch = k.susa.saldo(sachkonto)
        salden = {
            konto.iban: kontoauszugssaldo(k.session, konto.id, k.stichtag)
            for konto in konten
        }
        fehlend = [iban for iban, s in salden.items() if s is None]
        if fehlend:
            text = (
                f"Bank {sachkonto}: Saldo laut Kontoauszug zum "
                f"{k.stichtag:%d.%m.%Y} fehlt für {_liste(fehlend)} "
                "(accounti abschluss saldo --konto … --saldo …)"
            )
            befunde.append(Befund("bank", Schwere.FEHLER, text))
            continue
        auszug = sum((s.saldo for s in salden.values() if s is not None), NULL)
        if auszug != buch:
            text = (
                f"Bank {sachkonto}: Buchbestand {_euro(buch)} ≠ Kontoauszug "
                f"{_euro(auszug)} zum {k.stichtag:%d.%m.%Y} (Differenz "
                f"{_euro(buch - auszug)}) — der Abschluss ist gesperrt"
            )
            befunde.append(Befund("bank", Schwere.FEHLER, text))
    return befunde


def _kasse(k: Abschlusskontext) -> list[Befund]:
    buch = lade_kassenbuch(k.session)
    kassenbuch = bestand(buch, k.stichtag)
    konto = k.susa.saldo(k.kasse.konto)
    if kassenbuch == konto:
        return []
    text = (
        f"Kasse {k.kasse.konto}: Kassenbuch {_euro(kassenbuch)} ≠ Kassenkonto "
        f"{_euro(konto)} zum {k.stichtag:%d.%m.%Y} — ungebuchte Kassenvorgänge "
        "oder fehlender Eröffnungssaldo?"
    )
    return [Befund("kasse", Schwere.FEHLER, text)]


def _anlagen(k: Abschlusskontext) -> list[Befund]:
    befunde: list[Befund] = []
    rs = k.anlagen.rechtsstand()
    for p in afa_positionen(k.session, k.jahr, k.anlagen, 12, rs):
        if p.differenz:
            text = (
                f"AfA {k.jahr} nicht vollständig gebucht: {p.bezeichnung} — Soll "
                f"{_euro(p.soll)}, gebucht {_euro(p.gebucht)} "
                f"(accounti anlagen afa --jahr {k.jahr})"
            )
            befunde.append(Befund("anlagen", Schwere.FEHLER, text))
    rbw: dict[str, Decimal] = defaultdict(lambda: NULL)
    for z in anlagenspiegel(lade_anlagegueter(k.session), k.jahr, rs).gruppen:
        rbw[z.gruppe.split("/")[0]] += z.rbw_ende
    konten = set(rbw) | {
        z.konto for z in k.susa.zeilen if k.anlagen.ist_anlagekonto(z.konto)
    }
    for konto in sorted(konten):
        saldo = k.susa.saldo(konto)
        if saldo != rbw[konto]:
            text = (
                f"Anlagekonto {konto}: Saldo {_euro(saldo)} ≠ Restbuchwert laut "
                f"Anlagenverzeichnis {_euro(rbw[konto])}"
            )
            befunde.append(Befund("anlagen", Schwere.FEHLER, text))
    return befunde


def _abgrenzungen(k: Abschlusskontext) -> list[Befund]:
    offen = lade_abgrenzungen(k.session, k.jahr, AbgrenzungStatus.VORGESCHLAGEN)
    if not offen:
        return []
    nummern = _liste([str(a.nr) for a in offen])
    text = (
        f"{len(offen)} Abgrenzungsvorschl{'äge' if len(offen) > 1 else 'ag'} "
        f"{k.jahr} nicht entschieden (Nr. {nummern}) — accounti abschluss "
        "bestaetigen … oder ablehnen …"
    )
    return [Befund("abgrenzungen", Schwere.FEHLER, text)]


def _verrechnungskonten(k: Abschlusskontext) -> list[Befund]:
    return [
        Befund(
            "verrechnungskonten",
            Schwere.WARNUNG,
            f"Verrechnungskonto {konto} ist zum {k.stichtag:%d.%m.%Y} nicht "
            f"ausgeglichen: {_euro(k.susa.saldo(konto))}",
        )
        for konto in k.einstellungen.verrechnungskonten
        if k.susa.saldo(konto) != 0
    ]


def _vortragskonten(k: Abschlusskontext) -> list[Befund]:
    summe = sum(
        (z.saldo for z in k.susa.zeilen if k.kontenrahmen.ist_saldenvortrag(z.konto)),
        NULL,
    )
    if summe == 0:
        return []
    text = (
        f"Eröffnungsbilanz {k.jahr} nicht ausgeglichen: die Saldenvortragskonten "
        f"ergeben {_euro(summe)} (accounti abschluss eroeffnung …)"
    )
    return [Befund("vortragskonten", Schwere.FEHLER, text)]


def _euer_personenkonten(k: Abschlusskontext) -> list[Befund]:
    if not k.euer:
        return []
    offen = [
        z
        for z in k.susa.zeilen
        if k.kontenrahmen.ist_personenkonto(z.konto) and z.saldo != 0
    ]
    if not offen:
        return []
    text = (
        f"EÜR mit offenen Personenkonten zum {k.stichtag:%d.%m.%Y}: "
        f"{_liste([z.konto for z in offen])} — Erlöse/Aufwand dieser Rechnungen "
        "stehen schon in der EÜR, obwohl nicht zu- oder abgeflossen (§ 11 EStG)"
    )
    return [Befund("euer_personenkonten", Schwere.WARNUNG, text)]


def _euer_zuordnung(k: Abschlusskontext) -> list[Befund]:
    """Konten ohne Zeile der Anlage EÜR (Warnung, mit dem Hinweis ihrer Regel) und
    Konten, deren Regel einen Hinweis trägt (z. B. § 6b-Abzug, Umwandlungsergebnis)."""
    if not k.euer:
        return []
    ohne: dict[str | None, list[str]] = defaultdict(list)
    mit_hinweis: dict[str, list[str]] = defaultdict(list)
    for z in k.susa.zeilen:
        if z.art is not Kontenart.ERFOLG or z.saldo == 0:
            continue
        hinweis = k.kontenrahmen.euer_hinweis(z.konto)
        if k.kontenrahmen.euer_kz(z.konto, z.saldo) is None:
            ohne[hinweis].append(z.konto)
        elif hinweis:
            mit_hinweis[hinweis].append(z.konto)
    befunde = []
    for hinweis, konten in sorted(ohne.items(), key=lambda g: (g[0] is not None, g[1])):
        text = f"Konten ohne Zeile der Anlage EÜR: {_liste(konten)} — sie zählen als "
        if hinweis:
            text += f"„nicht zugeordnet“. {hinweis}"
        else:
            text += "„nicht zugeordnet“ (abschluss.kontenzuordnung)"
        befunde.append(Befund("euer_zuordnung", Schwere.WARNUNG, text))
    for hinweis, konten in sorted(mit_hinweis.items(), key=lambda g: g[1]):
        art = "Konto " if len(konten) == 1 else "Konten "
        text = f"{art}{_liste(konten)}: {hinweis}"
        befunde.append(Befund("euer_zuordnung", Schwere.HINWEIS, text))
    return befunde


def _protokoll(k: Abschlusskontext) -> list[Befund]:
    """Hash-Kette des Abschlussprotokolls — eine Warnung, kein Fehler: Ein einmal
    gebrochenes Protokoll lässt sich (nur anfügen) nicht mehr heilen und sperrte sonst
    jeden künftigen Abschluss."""
    fehler = pruefe_protokoll(k.session)
    if not fehler:
        return []
    text = (
        f"Abschlussprotokoll an accounti vorbei geändert: {_liste(fehler)} — "
        "Datenbestand prüfen (GoBD: Unveränderbarkeit)"
    )
    return [Befund("protokoll", Schwere.WARNUNG, text)]


PRUEFUNGEN: dict[str, Callable[[Abschlusskontext], list[Befund]]] = {
    "unfreigegeben": _unfreigegeben,
    "ungebucht": _ungebucht,
    "bank": _bank,
    "kasse": _kasse,
    "anlagen": _anlagen,
    "abgrenzungen": _abgrenzungen,
    "verrechnungskonten": _verrechnungskonten,
    "vortragskonten": _vortragskonten,
    "euer_personenkonten": _euer_personenkonten,
    "euer_zuordnung": _euer_zuordnung,
    "protokoll": _protokoll,
}


def pruefe_abschluss(k: Abschlusskontext, nur: list[str] | None = None) -> list[Befund]:
    namen = nur if nur is not None else list(PRUEFUNGEN)
    unbekannt = [n for n in namen if n not in PRUEFUNGEN]
    if unbekannt:
        raise ValueError(f"Prüfung unbekannt: {', '.join(unbekannt)}")
    befunde: list[Befund] = []
    for name in namen:
        befunde.extend(PRUEFUNGEN[name](k))
    return befunde


def blockiert(befunde: list[Befund]) -> bool:
    return any(b.schwere is Schwere.FEHLER for b in befunde)
