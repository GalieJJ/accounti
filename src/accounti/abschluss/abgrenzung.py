"""Rechnungsabgrenzung (ARAP/PRAP) — Vorschlag mit Auflösung in den Folgejahren.

Gesucht werden freigegebene Buchungen des Jahres auf ein Erfolgskonto, deren
Leistungszeitraum über den Stichtag reicht — erkennbar an Text wie
„01.12.2026 – 30.11.2027“ oder „01/2027–12/2027“ in Buchungstext, Belegnummer,
Belegpositionen oder Verwendungszweck. Der Anteil nach dem Stichtag wird bei ganzen
Monaten monatsgenau, sonst taggenau gerechnet.

Ein Vorschlag bucht nichts. Bestätigt der Mensch, entstehen Abgrenzung (31.12.) und
Auflösung zusammen, damit die Umkehrung nicht vergessen wird: je Folgejahr eine
Auflösung zum 01.01. in Höhe des Anteils dieses Jahres. Bei einem Zeitraum über mehr
als ein Folgejahr bleibt der Rest so im Abgrenzungsposten, bis sein Jahr kommt. Nur
bei Bilanzierung (§ 5 Abs. 5 EStG, § 250 HGB) — die EÜR folgt dem
Zufluss-/Abflussprinzip (§ 11 EStG).

Mit abweichendem Wirtschaftsjahr (``datev.wirtschaftsjahr_beginn``) gelten statt 31.12.
und 01.01. Ende und Beginn der Wirtschaftsjahre; ``jahr`` ist das Kalenderjahr des
Wirtschaftsjahresendes (``konfiguration.wirtschaftsjahr``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from accounti.abschluss.konfiguration import (
    AbschlussEinstellungen,
    wirtschaftsjahr,
    wirtschaftsjahr_zum,
)
from accounti.abschluss.kontenrahmen import Kontenart, Kontenrahmen
from accounti.abschluss.salden import FREIGEGEBEN
from accounti.anlagen.afa import monatsende, runde
from accounti.anlagen.rechtsstand import Rechtsstand
from accounti.anzeige import betrag_de
from accounti.db.repo_abschluss import (
    abgegrenzte_buchungen,
    aktualisiere_abgrenzung,
    lade_abgrenzung,
    lade_abgrenzungen,
    pruefe_jahr_offen,
    speichere_abgrenzung,
)
from accounti.db.repository import (
    finde_buchung,
    lade_belege,
    lade_buchungen,
    lade_transaktionen,
    speichere_buchung,
)
from accounti.models import Buchungssatz, BuchungStatus
from accounti.models.abschluss import Abgrenzung, AbgrenzungArt, AbgrenzungStatus

NULL = Decimal("0")

_DATUM = r"(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})(?!\d)"
_TRENNER = r"\s*(?:-|–|—|bis)\s*"
_TAGE = re.compile(_DATUM + _TRENNER + _DATUM)
_MONATE = re.compile(r"(?<![\d.])(\d{1,2})/(\d{4})" + _TRENNER + r"(\d{1,2})/(\d{4})")


class AbgrenzungError(ValueError):
    """Die Abgrenzung ist so nicht möglich."""


@dataclass(frozen=True)
class Zeitraum:
    von: date
    bis: date


def _jahr(text: str) -> int:
    return int(text) + 2000 if len(text) == 2 else int(text)


def finde_zeitraum(*texte: str | None) -> Zeitraum | None:
    """Erster gültiger Leistungszeitraum in den Texten."""
    for text in texte:
        if not text:
            continue
        for m in _TAGE.finditer(text):
            try:
                von = date(_jahr(m[3]), int(m[2]), int(m[1]))
                bis = date(_jahr(m[6]), int(m[5]), int(m[4]))
            except ValueError:
                continue
            if von <= bis:
                return Zeitraum(von, bis)
        for m in _MONATE.finditer(text):
            try:
                von = date(int(m[2]), int(m[1]), 1)
                bis = monatsende(int(m[4]), int(m[3]))
            except ValueError:
                continue
            if von <= bis:
                return Zeitraum(von, bis)
    return None


def _monate(von: date, bis: date) -> int:
    return (bis.year - von.year) * 12 + bis.month - von.month + 1


def anteil_nach(zeitraum: Zeitraum, stichtag: date) -> tuple[int, int, str]:
    """(Einheiten nach dem Stichtag, Einheiten gesamt, Einheit)."""
    von, bis = zeitraum.von, zeitraum.bis
    ab = max(von, stichtag + timedelta(days=1))
    if von.day == 1 and bis == monatsende(bis.year, bis.month):
        nach = _monate(ab, bis) if ab <= bis else 0
        return nach, _monate(von, bis), "Monate"
    nach = (bis - ab).days + 1 if ab <= bis else 0
    return nach, (bis - von).days + 1, "Tage"


def aufloesungen(
    a: Abgrenzung, beginn: date | None = None
) -> list[tuple[int, Decimal]]:
    """(Jahr, Betrag) der Auflösung je Folge-Wirtschaftsjahr — jeweils der Anteil
    dieses Jahres (``beginn``: Wirtschaftsjahresbeginn, ohne: Kalenderjahr).

    Gerechnet über den Rest nach jedem Stichtag (kaufmännisch gerundet), damit die
    Summe der Auflösungen genau den abgegrenzten Betrag ergibt.
    """
    zeitraum = Zeitraum(a.von, a.bis)
    nach_jahr = anteil_nach(zeitraum, wirtschaftsjahr(a.jahr, beginn).bis)[0]
    ergebnis: list[tuple[int, Decimal]] = []
    rest = a.betrag
    letztes = max(wirtschaftsjahr_zum(a.bis, beginn).jahr, a.jahr + 1)
    for jahr in range(a.jahr + 1, letztes + 1):
        stichtag = wirtschaftsjahr(jahr, beginn).bis
        nach = anteil_nach(zeitraum, stichtag)[0] if nach_jahr else 0
        neuer_rest = runde(a.betrag * nach / nach_jahr) if nach else NULL
        if rest != neuer_rest:
            ergebnis.append((jahr, rest - neuer_rest))
        rest = neuer_rest
    return ergebnis


@dataclass
class AbgrenzungsLauf:
    vorschlaege: list[Abgrenzung] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)


def _art(b: Buchungssatz, kr: Kontenrahmen) -> tuple[AbgrenzungArt, str] | None:
    soll = kr.art(b.soll_konto, "bilanz") is Kontenart.ERFOLG
    haben = kr.art(b.haben_konto, "bilanz") is Kontenart.ERFOLG
    if soll and not haben:
        return AbgrenzungArt.ARAP, b.soll_konto
    if haben and not soll:
        return AbgrenzungArt.PRAP, b.haben_konto
    return None


def _vorschlag(
    b: Buchungssatz,
    zeitraum: Zeitraum,
    jahr: int,
    einst: AbschlussEinstellungen,
    kr: Kontenrahmen,
) -> Abgrenzung | None:
    art_konto = _art(b, kr)
    if art_konto is None:
        return None
    art, konto = art_konto
    stichtag = einst.wirtschaftsjahr(jahr).bis
    nach, gesamt, einheit = anteil_nach(zeitraum, stichtag)
    betrag = runde(b.betrag_netto * nach / gesamt)
    if betrag == 0:
        return None
    rechenweg = (
        f"{betrag_de(b.betrag_netto)} × {nach}/{gesamt} {einheit} nach dem "
        f"{stichtag:%d.%m.%Y} "
        f"(Zeitraum {zeitraum.von:%d.%m.%Y}–{zeitraum.bis:%d.%m.%Y})"
    )
    a = Abgrenzung(
        jahr=jahr,
        buchung_id=b.id,
        art=art,
        konto=konto,
        rap_konto=einst.arap_konto if art is AbgrenzungArt.ARAP else einst.prap_konto,
        betrag=betrag,
        von=zeitraum.von,
        bis=zeitraum.bis,
        rechenweg=rechenweg,
    )
    teile = aufloesungen(a, einst.wirtschaftsjahr_beginn)
    if len(teile) > 1:
        je_jahr = " · ".join(f"{j} {betrag_de(t)}" for j, t in teile)
        a = a.model_copy(update={"rechenweg": f"{rechenweg}; Auflösung {je_jahr}"})
    return a


def schlage_abgrenzungen_vor(
    session: Session,
    jahr: int,
    einst: AbschlussEinstellungen,
    rechtsstand: Rechtsstand,
) -> AbgrenzungsLauf:
    pruefe_jahr_offen(session, jahr)
    lauf = AbgrenzungsLauf()
    if einst.gewinnermittlung != "bilanz":
        lauf.hinweise.append(
            "Einnahmenüberschussrechnung: keine Rechnungsabgrenzung "
            "(Zufluss-/Abflussprinzip, § 11 EStG) — die 10-Tage-Regel für regelmäßig "
            "wiederkehrende Zahlungen bitte selbst prüfen"
        )
        return lauf
    kr = einst.lade_kontenrahmen()
    wj = einst.wirtschaftsjahr(jahr)
    stichtag = wj.bis
    verzicht = einst.rap_verzicht_bis_gwg and rechtsstand.rap_verzicht_moeglich(
        stichtag
    )
    grenze = rechtsstand.grenzen_am(stichtag).gwg
    schon = abgegrenzte_buchungen(session)
    belege = {b.id: b for b in lade_belege(session)}
    umsaetze = {t.id: t for t in lade_transaktionen(session)}
    verzichtet = 0
    for b in lade_buchungen(session, status=set(FREIGEGEBEN)):
        if not wj.enthaelt(b.datum) or b.id in schon:
            continue
        if b.storniert_durch or b.storno_von:
            continue  # Storno-Paar hebt sich auf; abgegrenzt wird die Neubuchung
        if (b.beleg_nummer or "").startswith(("RAP-", "EB-")):
            continue
        texte = [b.buchungstext, b.beleg_nummer]
        beleg = belege.get(b.beleg_id) if b.beleg_id else None
        if beleg is not None:
            texte += [beleg.belegnummer, *(p.bezeichnung for p in beleg.positionen)]
        umsatz = umsaetze.get(b.transaktion_id) if b.transaktion_id else None
        if umsatz is not None:
            texte.append(umsatz.verwendungszweck)
        zeitraum = finde_zeitraum(*texte)
        if zeitraum is None or zeitraum.bis <= stichtag:
            continue
        vorschlag = _vorschlag(b, zeitraum, jahr, einst, kr)
        if vorschlag is None:
            continue
        if verzicht and b.betrag_netto <= grenze:
            verzichtet += 1
            continue
        lauf.vorschlaege.append(speichere_abgrenzung(session, vorschlag))
    if verzichtet:
        lauf.hinweise.append(
            f"{verzichtet} Ausgaben/Einnahmen bis {betrag_de(grenze)} € nicht "
            "abgegrenzt (Wahlrecht § 5 Abs. 5 Satz 2 EStG, einheitlich ausgeübt)"
        )
    session.flush()
    return lauf


def grenze_ab(
    session: Session,
    buchung: str,
    von: date,
    bis: date,
    einst: AbschlussEinstellungen,
) -> Abgrenzung:
    """Abgrenzungsvorschlag für eine bestimmte Buchung mit angegebenem Zeitraum."""
    try:
        b = finde_buchung(session, buchung)
    except ValueError as fehler:
        raise AbgrenzungError(str(fehler)) from fehler
    jahr = einst.wirtschaftsjahr_zum(b.datum).jahr
    pruefe_jahr_offen(session, jahr)
    if b.id in abgegrenzte_buchungen(session):
        raise AbgrenzungError(
            f"Für Buchung {str(b.id)[:8]} gibt es schon einen Vorschlag"
        )
    if von > bis:
        raise AbgrenzungError("Der Zeitraum endet vor seinem Beginn")
    vorschlag = _vorschlag(
        b, Zeitraum(von, bis), jahr, einst, einst.lade_kontenrahmen()
    )
    if vorschlag is None:
        msg = (
            "Abgrenzen lässt sich nur eine Buchung auf ein Erfolgskonto, deren "
            "Zeitraum über den Stichtag reicht"
        )
        raise AbgrenzungError(msg)
    return speichere_abgrenzung(session, vorschlag)


def _offen(session: Session, schluessel: str) -> Abgrenzung:
    try:
        a = lade_abgrenzung(session, schluessel)
    except ValueError as fehler:
        raise AbgrenzungError(str(fehler)) from fehler
    if a.status is not AbgrenzungStatus.VORGESCHLAGEN:
        raise AbgrenzungError(f"Abgrenzung {a.nr} ist schon {a.status.value}")
    return a


def bestaetige_abgrenzung(
    session: Session, schluessel: str, von: str, beginn: date | None = None
) -> Abgrenzung:
    """Bucht die Abgrenzung zum Ende des Wirtschaftsjahres (31.12.) und je Folgejahr
    die Auflösung zu dessen Beginn (01.01.); ``beginn`` aus
    ``AbschlussEinstellungen.wirtschaftsjahr_beginn``."""
    a = _offen(session, schluessel)
    teile = aufloesungen(a, beginn)
    for jahr in [a.jahr, *(j for j, _ in teile)]:
        pruefe_jahr_offen(session, jahr)
    name = a.art.value.upper()
    if a.art is AbgrenzungArt.ARAP:
        soll, haben = a.rap_konto, a.konto
    else:
        soll, haben = a.konto, a.rap_konto

    def buchung(
        datum: date, soll: str, haben: str, text: str, betrag: Decimal
    ) -> Buchungssatz:
        return Buchungssatz(
            datum=datum,
            soll_konto=soll,
            haben_konto=haben,
            betrag_netto=betrag,
            buchungstext=text[:60],
            beleg_nummer=f"RAP-{a.jahr}-{a.nr}",
            status=BuchungStatus.GEPRUEFT,
            confidence=1.0,
            geprueft_von=von,
        )

    text = f"{name} {a.jahr} {a.konto} (Nr. {a.nr})"
    ende = wirtschaftsjahr(a.jahr, beginn).bis
    abgrenzung = buchung(ende, soll, haben, text, a.betrag)
    speichere_buchung(session, abgrenzung)
    gebucht = [
        buchung(
            wirtschaftsjahr(jahr, beginn).von,
            haben,
            soll,
            f"Auflösung {jahr} {text}",
            betrag,
        )
        for jahr, betrag in teile
    ]
    for aufloesung in gebucht:
        speichere_buchung(session, aufloesung)
    a = a.model_copy(
        update={
            "status": AbgrenzungStatus.BESTAETIGT,
            "abgrenzung_buchung_id": abgrenzung.id,
            "aufloesung_buchung_id": gebucht[0].id if gebucht else None,
            "entschieden_am": datetime.now(),
            "entschieden_von": von,
        }
    )
    aktualisiere_abgrenzung(session, a)
    return a


def lehne_abgrenzung_ab(session: Session, schluessel: str, von: str) -> Abgrenzung:
    a = _offen(session, schluessel).model_copy(
        update={
            "status": AbgrenzungStatus.ABGELEHNT,
            "entschieden_am": datetime.now(),
            "entschieden_von": von,
        }
    )
    aktualisiere_abgrenzung(session, a)
    return a


def offene_abgrenzungen(session: Session, jahr: int) -> list[Abgrenzung]:
    return lade_abgrenzungen(session, jahr, AbgrenzungStatus.VORGESCHLAGEN)
