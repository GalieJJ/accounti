"""Stufenermittlung: Welche Forderung bekommt heute welche Mahnstufe?

Eine Forderung ist mahnfähig, wenn sie mehr als ``karenztage`` überfällig ist. Ihre
nächste Stufe ist die nach der aktuellen Mahnstufe am Posten — keine wird
übersprungen. Sie greift, wenn die Tage seit Fälligkeit ihr ``ab_tagen`` erreichen,
seit dem Versand der letzten Mahnung mindestens ``stufenabstand_tage`` vergangen sind
und die Zahlungsfrist, die diese Mahnung gesetzt hat, abgelaufen ist.

Hat der Kunde ein Guthaben (Gutschrift, Rechnungskorrektur, Überzahlung: ein Posten mit
negativem Rest), schuldet er weniger, als die einzelne Forderung ausweist — dann wird
nicht gemahnt, sondern erst verrechnet (``accounti opos verrechnen``).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from accounti.anzeige import betrag_de
from accounti.mahnwesen.konfiguration import MahnEinstellungen, MahnStufe
from accounti.models import Kontakt, OffenerPosten, PostenRichtung, PostenStatus
from accounti.models.mahnwesen import MahnKontakt


@dataclass(frozen=True)
class FaelligeStufe:
    posten: OffenerPosten
    kontakt: Kontakt
    stufe_nr: int  # 1 = erste konfigurierte Stufe
    stufe: MahnStufe
    tage: int  # seit Fälligkeit


@dataclass(frozen=True)
class Ausnahme:
    posten: OffenerPosten
    kontakt: Kontakt | None
    grund: str


def _ausnahme(
    p: OffenerPosten,
    e: MahnEinstellungen,
    mahnkontakt: MahnKontakt | None,
    entwurf: int | None,
    vorgeschlagen: bool,
) -> str | None:
    if mahnkontakt is not None and mahnkontakt.mahnsperre:
        return f"Mahnsperre: {mahnkontakt.sperrgrund or 'ohne Grund'}"
    if entwurf is not None:
        return f"Mahnung {entwurf} ist noch ein Entwurf — erst versenden oder verwerfen"
    if vorgeschlagen:
        return (
            "Zahlung vorgeschlagen — erst 'accounti opos bestaetigen' oder "
            "'accounti opos ablehnen'"
        )
    if p.restbetrag < e.mindestbetrag:
        return (
            f"Rest {betrag_de(p.restbetrag)} € unter dem Mindestbetrag von "
            f"{betrag_de(e.mindestbetrag)} €"
        )
    if p.mahnstufe >= len(e.stufen):
        return (
            f"letzte Stufe ({e.stufen[-1].name}) erreicht — weiter nur außerhalb von "
            "accounti (gerichtliches Mahnverfahren, Inkasso)"
        )
    return None


def ermittle(
    posten: Iterable[OffenerPosten],
    kontakte: Mapping[UUID, Kontakt],
    stichtag: date,
    e: MahnEinstellungen,
    *,
    letzte_mahnung: Mapping[UUID, date] | None = None,
    frist_bis: Mapping[UUID, date] | None = None,
    offene_entwuerfe: Mapping[UUID, int] | None = None,
    zahlung_vorgeschlagen: set[UUID] | None = None,
    mahnkontakte: Mapping[UUID, MahnKontakt] | None = None,
) -> tuple[list[FaelligeStufe], list[Ausnahme]]:
    faellig: list[FaelligeStufe] = []
    ausnahmen: list[Ausnahme] = []
    posten = list(posten)
    guthaben: dict[UUID, list[OffenerPosten]] = defaultdict(list)
    for p in posten:
        if (
            p.richtung is PostenRichtung.FORDERUNG
            and p.status is not PostenStatus.AUSGEGLICHEN
            and p.restbetrag < 0
        ):
            guthaben[p.kontakt_id].append(p)
    for p in posten:
        if (
            p.richtung is not PostenRichtung.FORDERUNG
            or p.status is PostenStatus.AUSGEGLICHEN
            or p.restbetrag <= 0
        ):
            continue
        tage = (stichtag - p.faellig_am).days
        if tage <= e.karenztage:
            continue
        k = kontakte.get(p.kontakt_id)
        grund = _ausnahme(
            p,
            e,
            (mahnkontakte or {}).get(p.kontakt_id),
            (offene_entwuerfe or {}).get(p.id),
            p.id in (zahlung_vorgeschlagen or set()),
        )
        if grund is None and guthaben.get(p.kontakt_id):
            gegen = guthaben[p.kontakt_id]
            summe = sum((g.restbetrag for g in gegen), Decimal("0"))
            nummern = " ".join(g.belegnummer or str(g.id)[:8] for g in gegen)
            grund = (
                f"Guthaben des Kunden {betrag_de(-summe)} € (Gutschrift/Überzahlung "
                f"{nummern}) — erst verrechnen: accounti opos verrechnen "
                f"{p.belegnummer or str(p.id)[:8]} {nummern}"
            )
        if grund is not None or k is None:
            ausnahmen.append(Ausnahme(p, k, grund or "Kontakt fehlt"))
            continue
        nr = p.mahnstufe + 1
        stufe = e.stufen[nr - 1]
        letzte = (letzte_mahnung or {}).get(p.id)
        if tage < stufe.ab_tagen:
            continue
        if letzte is not None and (stichtag - letzte).days < e.stufenabstand_tage:
            continue
        frist = (frist_bis or {}).get(p.id)
        if frist is not None and stichtag <= frist:
            continue  # die Frist der letzten Mahnung läuft noch
        faellig.append(FaelligeStufe(p, k, nr, stufe, tage))
    faellig.sort(key=lambda f: (f.posten.faellig_am, f.posten.belegnummer or ""))
    return faellig, ausnahmen
