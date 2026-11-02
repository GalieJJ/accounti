"""Plausibilisierung der Voranmeldung vor der Freigabe.

Befunde tragen einen Schweregrad wie die Prüfregeln aus Baustein 7: ``fehler`` sperrt
die Freigabe, ``warnung`` und ``hinweis`` muss der Mensch gesehen haben, sie halten
nichts auf.
Die Regeln ändern nie Daten.

- ``offene_buchungen``     Buchungen im Zeitraum, die noch zur Prüfung liegen (fehler)
- ``ohne_steuerschluessel`` Erlöse ohne Steuerschlüssel und ohne Kennziffer (fehler)
- ``ustid``                ig. Lieferung, Dreiecksgeschäft oder EU-Leistung ohne
                           qualifiziert bestätigte USt-IdNr. des Abnehmers (fehler)
- ``konsistenz``           Bemessungsgrundlage ohne Steuer und umgekehrt (fehler),
                           § 13b-Steuer passt zu keinem Satz (warnung)
- ``verprobung``           gebuchte Umsatzsteuer weicht von der gemeldeten ab (warnung)
- ``oss``                  EU-Privatkunde mit deutscher Umsatzsteuer trotz OSS (warnung)
- ``vergleich``            Kz 83 weicht stark von Vormonat/Vorjahresmonat ab (hinweis)
- ``ermittlung``           Auffälligkeiten der Kennziffernermittlung: § 13b ohne
                           bekannten Leistenden, Steuerkonto ohne Kennziffer, EU-Kunde
                           auf einem nicht steuerbaren Konto (warnung); fehlender
                           Steuerbetrag (hinweis)
- ``periode``              Periodenabschluss/Prüfbefunde (Baustein 7) ungeprüft
                           (hinweis)
- ``beleg_nach_zeitraum``  Vorsteuer aus einer Rechnung, die erst nach Ende des
                           Zeitraums einging (warnung, § 15 Abs. 1 Nr. 1 UStG)
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from accounti.anzeige import betrag_de
from accounti.models import Buchungssatz, Kontakt
from accounti.steuer.eu_steuersaetze import ist_eu_land
from accounti.steuer.kennziffern import Ermittlung, Kontenplan
from accounti.steuer.voranmeldung import KENNZIFFERN_2026, UStVoranmeldung

_PAARE = ((35, 36), (76, 80), (95, 98), (94, 96), (46, 47), (73, 74), (84, 85))
_SAETZE_13B = (Decimal("19"), Decimal("7"))


class Schweregrad(str, enum.Enum):
    FEHLER = "fehler"
    WARNUNG = "warnung"
    HINWEIS = "hinweis"


@dataclass(frozen=True)
class Befund:
    regel: str
    schweregrad: Schweregrad
    text: str
    buchung_id: UUID | None = None


class Lage(Protocol):
    @property
    def bestaetigt(self) -> bool: ...

    @property
    def grund(self) -> str: ...


Bestaetigung = Callable[[str | None, date], Lage]


@dataclass(frozen=True)
class Schwellen:
    abweichung_prozent: Decimal = Decimal("50")
    abweichung_mindestens: Decimal = Decimal("1000")
    verprobung_toleranz: Decimal = Decimal("1.00")


def freigabe_gesperrt(befunde: Iterable[Befund]) -> bool:
    return any(b.schweregrad is Schweregrad.FEHLER for b in befunde)


def _kurz(b: Buchungssatz) -> str:
    return (
        f"{b.datum:%d.%m.%Y} {b.soll_konto} an {b.haben_konto} "
        f"{betrag_de(b.betrag_netto)} €"
        + (f" ({b.beleg_nummer})" if b.beleg_nummer else "")
    )


def ustid_befunde(e: Ermittlung, bestaetigung: Bestaetigung) -> list[Befund]:
    """EU-Umsätze ohne qualifiziert bestätigte USt-IdNr. des Abnehmers."""
    befunde = []
    for u in e.eu:
        if u.betrag <= 0:
            continue  # Minderungen brauchen keine neue Bestätigung
        art = {"L": "ig. Lieferung", "D": "Dreiecksgeschäft", "S": "EU-Leistung"}[u.art]
        k = u.kontakt
        name = u.name or (k.name if k else None)
        if k is None and name is None:
            text = f"{_kurz(u.buchung)}: {art}, Abnehmer unbekannt — kein Personenkonto"
        elif not u.ust_id:
            text = f"{_kurz(u.buchung)}: {art} an {name} ohne USt-IdNr."
        else:
            lage = bestaetigung(u.ust_id, u.buchung.datum)
            if lage.bestaetigt:
                continue
            konto = (k.debitor_konto or str(k.id)[:8]) if k else u.ust_id
            text = (
                f"{_kurz(u.buchung)}: {art} an {name}, USt-IdNr. {u.ust_id} nicht "
                f"bestätigt: {lage.grund} — accounti kontakte pruefe-ustid {konto}"
            )
        befunde.append(Befund("ustid", Schweregrad.FEHLER, text, u.buchung.id))
    return befunde


def offene_befunde(e: Ermittlung) -> list[Befund]:
    """Buchungen im Zeitraum, über die noch ein Mensch entscheiden muss."""
    return [
        Befund(
            "offene_buchungen",
            Schweregrad.FEHLER,
            f"{_kurz(b)}: noch zur Prüfung ({b.status.value}) — erst entscheiden "
            "(accounti review), dann melden",
            b.id,
        )
        for b in e.offen
    ]


def _konsistenz(va: UStVoranmeldung) -> list[Befund]:
    befunde = []
    for bmg, steuer in _PAARE:
        b, s = va.bmg(bmg), va.wert(steuer)
        if (b == 0) != (s == 0):
            fehlt = steuer if s == 0 else bmg
            text = (
                f"Kz {bmg}/{steuer}: {KENNZIFFERN_2026[bmg].bezeichnung[:50]} — "
                f"Kz {fehlt} fehlt"
            )
            befunde.append(Befund("konsistenz", Schweregrad.FEHLER, text))
        elif (
            b
            and bmg in (46, 84)
            and not any(
                abs(b * satz / 100 - s) <= abs(b) / 100 + 1 for satz in _SAETZE_13B
            )
        ):
            text = (
                f"Kz {steuer} ({betrag_de(s)} €) passt zu keinem Steuersatz auf "
                f"Kz {bmg} ({betrag_de(b)} €)"
            )
            befunde.append(Befund("konsistenz", Schweregrad.WARNUNG, text))
    return befunde


def _verprobung(e: Ermittlung, toleranz: Decimal) -> list[Befund]:
    va = e.voranmeldung
    gemeldet = va.steuer(81) + va.steuer(86)
    differenz = e.gebuchte_umsatzsteuer - gemeldet
    if abs(differenz) <= toleranz:
        return []
    text = (
        f"Gebuchte Umsatzsteuer {betrag_de(e.gebuchte_umsatzsteuer)} € weicht von der "
        f"gemeldeten {betrag_de(gemeldet)} € (Kz 81/86 × Satz) um "
        f"{betrag_de(differenz)} € "
        "ab — Steuerbeträge der Buchungen prüfen"
    )
    return [Befund("verprobung", Schweregrad.WARNUNG, text)]


def _oss(e: Ermittlung, plan: Kontenplan, kontakte: Sequence[Kontakt]) -> list[Befund]:
    debitoren = {k.debitor_konto: k for k in kontakte if k.debitor_konto}
    befunde = []
    for z in e.zugeordnet:
        b = z.buchung
        if b.steuer_schluessel not in (2, 3):
            continue
        for konto in (b.soll_konto, b.haben_konto):
            k = debitoren.get(konto)
            if (
                k is None
                or k.ust_id
                or k.land.upper() == "DE"
                or not ist_eu_land(k.land)
            ):
                continue
            text = (
                f"{_kurz(b)}: {k.name} ({k.land}) ist Privatkunde im EU-Ausland — mit "
                "OSS gilt der Steuersatz des Bestimmungslands, nicht die deutsche USt"
            )
            befunde.append(Befund("oss", Schweregrad.WARNUNG, text, b.id))
    return befunde


def _beleg_nach_zeitraum(
    e: Ermittlung, belegeingang: Mapping[UUID, date]
) -> list[Befund]:
    """Vorsteuer (Kz 66) aus einer Belegbuchung, deren Rechnung erst nach Ende des
    Zeitraums erfasst wurde: abziehbar ist sie erst, wenn die Rechnung vorliegt.

    Nur der Abzug: Eine Gutschrift (Kz 66 negativ) mindert die Vorsteuer im Zeitraum
    der Änderung, gleich wann sie eingeht (§ 17 Abs. 1 S. 8 UStG)."""
    befunde = []
    for z in e.zugeordnet:
        b = z.buchung
        eingang = belegeingang.get(b.beleg_id) if b.beleg_id else None
        kz66 = sum((x.betrag for x in z.beitraege if x.kz == 66), Decimal("0"))
        if (
            eingang is None
            or b.transaktion_id is not None
            or b.steuer_schluessel not in (8, 9)
            or eingang <= e.zeitraum.bis
            or kz66 <= 0
        ):
            continue
        text = (
            f"{_kurz(b)}: Vorsteuer aus einer Rechnung, die erst am "
            f"{eingang:%d.%m.%Y} — nach Ende des Zeitraums — erfasst wurde; abziehbar "
            "ist sie erst im Zeitraum, in dem die Rechnung vorliegt (§ 15 Abs. 1 Nr. 1 "
            "UStG). Lag sie vorher vor (Eingang = Erfassung in accounti), ist nichts "
            "zu tun"
        )
        befunde.append(Befund("beleg_nach_zeitraum", Schweregrad.WARNUNG, text, b.id))
    return befunde


def _vergleich(
    va: UStVoranmeldung,
    vergleiche: Sequence[tuple[str, UStVoranmeldung | None]],
    schwellen: Schwellen,
) -> list[Befund]:
    befunde = []
    for name, alt in vergleiche:
        if alt is None:
            continue
        differenz = va.kz83 - alt.kz83
        basis = abs(alt.kz83)
        if abs(differenz) < schwellen.abweichung_mindestens:
            continue
        if basis and abs(differenz) * 100 / basis < schwellen.abweichung_prozent:
            continue
        text = (
            f"Kz 83 {betrag_de(va.kz83)} € gegenüber {name} {betrag_de(alt.kz83)} € "
            f"({'+' if differenz > 0 else ''}{betrag_de(differenz)} €) — Ausreißer?"
        )
        befunde.append(Befund("vergleich", Schweregrad.HINWEIS, text))
    return befunde


def plausibilisiere(
    e: Ermittlung,
    *,
    bestaetigung: Bestaetigung,
    plan: Kontenplan | None = None,
    kontakte: Sequence[Kontakt] = (),
    vorperiode: UStVoranmeldung | None = None,
    vorjahr: UStVoranmeldung | None = None,
    oss_aktiv: bool = False,
    schwellen: Schwellen | None = None,
    weitere: Iterable[Befund] | None = None,
    belegeingang: Mapping[UUID, date] | None = None,
) -> list[Befund]:
    """Alle Befunde, Fehler zuerst.

    ``bestaetigung(ust_id, stichtag)``: aktuelle qualifizierte Bestätigung der USt-IdNr.
    (in accounti: ``kontakte.ustid.aktuelle_bestaetigung``). ``weitere``: Befunde
    anderer Bausteine (Periodenabschluss, offene Prüfbefunde); ``None`` heißt, es gibt
    sie nicht.
    """
    plan = plan or Kontenplan()
    schwellen = schwellen or Schwellen()
    befunde = offene_befunde(e)
    befunde += [
        Befund(
            "ohne_steuerschluessel", Schweregrad.FEHLER, f"{_kurz(b)}: {grund}", b.id
        )
        for b, grund in e.ohne_kennziffer
    ]
    befunde += ustid_befunde(e, bestaetigung)
    befunde += _konsistenz(e.voranmeldung)
    befunde += _verprobung(e, schwellen.verprobung_toleranz)
    if oss_aktiv:
        befunde += _oss(e, plan, kontakte)
    vormonat = "Vormonat" if e.zeitraum.art == "monat" else "Vorquartal"
    befunde += _vergleich(
        e.voranmeldung,
        [(vormonat, vorperiode), ("Vorjahreszeitraum", vorjahr)],
        schwellen,
    )
    befunde += [Befund("ermittlung", Schweregrad.WARNUNG, w) for w in e.warnungen]
    befunde += _beleg_nach_zeitraum(e, belegeingang or {})
    befunde += [Befund("ermittlung", Schweregrad.HINWEIS, h) for h in e.hinweise]
    if weitere is None:
        befunde.append(
            Befund(
                "periode",
                Schweregrad.HINWEIS,
                "Periodenabschluss und offene Prüfbefunde (Baustein 7) sind noch nicht "
                "angeschlossen und deshalb nicht geprüft",
            )
        )
    else:
        befunde += list(weitere)
    rang = {Schweregrad.FEHLER: 0, Schweregrad.WARNUNG: 1, Schweregrad.HINWEIS: 2}
    return sorted(befunde, key=lambda x: rang[x.schweregrad])
