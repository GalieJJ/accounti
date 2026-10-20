"""Mahnlauf: Mahnungen berechnen, versenden, verwerfen.

Ein Lauf legt für jede fällige Stufe eine Mahnung als Entwurf an — mit Verzugszinsen
nach § 288 BGB, der 40-€-Pauschale bei Unternehmern (§ 288 Abs. 5, mit Anrechnung
der Mahngebühren nach Satz 3) und den Gebühren der Stufen. Erst das Versenden zählt
die Mahnstufe am offenen Posten hoch; versendete Mahnungen sind die Historie.

B2B oder B2C entscheidet in dieser Reihenfolge: Einstufung am Kontakt
(``accounti mahnwesen kunde``) → Ausgangsrechnung aus accounti → USt-IdNr. im
Stammsatz → ``mahnwesen.unbekannt_als`` (Standard: Verbraucher — lieber zu wenig
Zinsen verlangen als eine unberechtigte Forderung stellen).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.repo_mahnwesen import (
    lade_mahnkontakte,
    lade_mahnung,
    lade_mahnungen,
    naechste_mahnnummer,
    setze_mahnstufe,
    setze_mahnung_status,
    speichere_mahnung,
)
from accounti.db.repository import (
    lade_ausgangsrechnungen,
    lade_einen_posten,
    lade_kontakte,
    lade_posten,
    lade_transaktion,
    lade_zuordnungen,
)
from accounti.mahnwesen.basiszins import Basiszins, BasiszinsUnbekanntError
from accounti.mahnwesen.konfiguration import MahnEinstellungen
from accounti.mahnwesen.stufen import Ausnahme, ermittle
from accounti.mahnwesen.zinsen import summe, verzugszinsen
from accounti.models import (
    Ausgangsrechnung,
    Kontakt,
    OffenerPosten,
    PostenRichtung,
    PostenStatus,
    ZuordnungStatus,
)
from accounti.models.mahnwesen import MahnKontakt, Mahnung, MahnungStatus

NULL = Decimal("0.00")


class MahnError(RuntimeError):
    """Die Mahnung kann so nicht versendet oder verworfen werden."""


@dataclass
class Mahnlauf:
    stichtag: date
    mahnungen: list[Mahnung] = field(default_factory=list)
    ausnahmen: list[Ausnahme] = field(default_factory=list)


def einstufung(
    kontakt: Kontakt,
    mahnkontakt: MahnKontakt | None,
    rechnung: Ausgangsrechnung | None,
    e: MahnEinstellungen,
) -> tuple[bool, str]:
    """(Unternehmer?, Grund)."""
    if mahnkontakt is not None and mahnkontakt.unternehmer is not None:
        art = "Unternehmer" if mahnkontakt.unternehmer else "Verbraucher"
        return (
            mahnkontakt.unternehmer,
            f"als {art} eingestuft (accounti mahnwesen kunde)",
        )
    if rechnung is not None:
        art = "Privatkunde" if rechnung.kunde.privat else "Unternehmer"
        return not rechnung.kunde.privat, f"Ausgangsrechnung {rechnung.nummer}: {art}"
    if kontakt.ust_id:
        return True, f"USt-IdNr. {kontakt.ust_id} im Stammsatz"
    if e.unbekannt_als == "unternehmer":
        return (
            True,
            "keine Angabe — als Unternehmer behandelt (mahnwesen.unbekannt_als)",
        )
    return False, "keine Angabe — als Verbraucher behandelt (mahnwesen.unbekannt_als)"


def berechne(
    p: OffenerPosten,
    stufe_nr: int,
    stichtag: date,
    e: MahnEinstellungen,
    unternehmer: bool,
    grund: str,
    zahlungen: Sequence[tuple[date, Decimal]] = (),
    saetze: Sequence[Basiszins] | None = None,
) -> Mahnung:
    """Beträge einer Mahnung — ohne Datenbank."""
    stufe = e.stufen[stufe_nr - 1]
    abschnitte = []
    verzug_ab = None
    if stufe.verzugszinsen:
        verzug_ab = p.faellig_am + timedelta(days=1 + e.verzug_nach_tagen)
        abschnitte = verzugszinsen(
            p.restbetrag, zahlungen, verzug_ab, stichtag, unternehmer, saetze
        )
    im_verzug = verzug_ab is not None and verzug_ab <= stichtag
    pauschale = e.pauschale_b2b if unternehmer and im_verzug else NULL
    kumuliert = sum((s.gebuehr for s in e.stufen[:stufe_nr]), NULL)
    gebuehren = kumuliert
    if pauschale > 0 and e.pauschale_anrechnen:
        gebuehren = max(NULL, kumuliert - pauschale)
    zinsen = summe(abschnitte)
    return Mahnung(
        posten_id=p.id,
        kontakt_id=p.kontakt_id,
        stufe=stufe_nr,
        stufe_name=stufe.name,
        datum=stichtag,
        belegnummer=p.belegnummer,
        belegdatum=p.belegdatum,
        faellig_am=p.faellig_am,
        rechnungsbetrag=p.betrag,
        restbetrag=p.restbetrag,
        verzug_ab=verzug_ab,
        zinsen=zinsen,
        zinsabschnitte=abschnitte,
        gebuehren_kumuliert=kumuliert,
        gebuehren=gebuehren,
        pauschale=pauschale,
        summe=p.restbetrag + zinsen + pauschale + gebuehren,
        zahlungsfrist=stichtag + timedelta(days=e.zahlungsfrist_tage),
        unternehmer=unternehmer,
        einstufung=grund,
    )


def zahlungen_auf(session: Session, posten_id: UUID) -> list[tuple[date, Decimal]]:
    """(Tag, Betrag inkl. Skonto) der gebuchten Zahlungen auf einen Posten."""
    ergebnis = []
    for z in lade_zuordnungen(session, status={ZuordnungStatus.GEBUCHT}):
        if z.posten_id != posten_id:
            continue
        tx = lade_transaktion(session, z.transaktion_id)
        if tx is not None:
            ergebnis.append((tx.datum, z.betrag + z.skonto))
    return ergebnis


def mahnlauf(session: Session, stichtag: date, e: MahnEinstellungen) -> Mahnlauf:
    """Legt für jede fällige Stufe eine Mahnung als Entwurf an."""
    lauf = Mahnlauf(stichtag)
    posten = lade_posten(
        session,
        richtung=PostenRichtung.FORDERUNG,
        status={PostenStatus.OFFEN, PostenStatus.TEILBEZAHLT},
    )
    kontakte = {k.id: k for k in lade_kontakte(session)}
    mahnkontakte = lade_mahnkontakte(session)
    letzte: dict[UUID, date] = {}
    entwuerfe: dict[UUID, int] = {}
    for m in lade_mahnungen(session):
        if m.status is MahnungStatus.VERSENDET:
            letzte[m.posten_id] = max(m.datum, letzte.get(m.posten_id, m.datum))
        elif m.status is MahnungStatus.ENTWURF:
            entwuerfe[m.posten_id] = m.nr
    vorgeschlagen = {
        z.posten_id
        for z in lade_zuordnungen(session, status={ZuordnungStatus.VORGESCHLAGEN})
    }
    faellig, lauf.ausnahmen = ermittle(
        posten,
        kontakte,
        stichtag,
        e,
        letzte_mahnung=letzte,
        offene_entwuerfe=entwuerfe,
        zahlung_vorgeschlagen=vorgeschlagen,
        mahnkontakte=mahnkontakte,
    )
    rechnungen = {r.beleg_id: r for r in lade_ausgangsrechnungen(session) if r.beleg_id}
    saetze = e.basiszinstabelle()
    for f in faellig:
        unternehmer, grund = einstufung(
            f.kontakt,
            mahnkontakte.get(f.kontakt.id),
            rechnungen.get(f.posten.beleg_id),
            e,
        )
        try:
            m = berechne(
                f.posten,
                f.stufe_nr,
                stichtag,
                e,
                unternehmer,
                grund,
                zahlungen_auf(session, f.posten.id),
                saetze,
            )
        except BasiszinsUnbekanntError as fehler:
            lauf.ausnahmen.append(Ausnahme(f.posten, f.kontakt, str(fehler)))
            continue
        m = m.model_copy(update={"nr": naechste_mahnnummer(session)})
        speichere_mahnung(session, m)
        lauf.mahnungen.append(m)
    return lauf


def _entwurf(session: Session, nr: int) -> Mahnung:
    try:
        m = lade_mahnung(session, nr)
    except ValueError as fehler:
        raise MahnError(str(fehler)) from fehler
    if m.status is not MahnungStatus.ENTWURF:
        msg = (
            f"Mahnung {nr} ist {m.status.value} — nur Entwürfe werden versendet "
            "oder verworfen"
        )
        raise MahnError(msg)
    return m


def pruefe_versendbar(session: Session, nr: int) -> Mahnung:
    """Der Entwurf, wenn er so noch stimmt — sonst ``MahnError`` mit Grund."""
    m = _entwurf(session, nr)
    p = lade_einen_posten(session, m.posten_id)
    if p.status is PostenStatus.AUSGEGLICHEN or p.restbetrag <= 0:
        msg = f"Posten {p.belegnummer} ist inzwischen ausgeglichen — Mahnung verwerfen"
        raise MahnError(msg)
    if p.restbetrag != m.restbetrag:
        msg = (
            f"Der Rest von {p.belegnummer} hat sich seit der Berechnung geändert — "
            "Mahnung verwerfen und den Lauf wiederholen"
        )
        raise MahnError(msg)
    if p.mahnstufe >= m.stufe:
        msg = f"Posten {p.belegnummer} hat schon Mahnstufe {p.mahnstufe}"
        raise MahnError(msg)
    return m


def versende(
    session: Session,
    nr: int,
    weg: str,
    datei_hash: str | None = None,
    zeitpunkt: datetime | None = None,
) -> Mahnung:
    """Markiert die Mahnung als versendet und zählt die Mahnstufe am Posten hoch."""
    pruefe_versendbar(session, nr)
    m = setze_mahnung_status(
        session,
        nr,
        MahnungStatus.VERSENDET,
        versendet_am=zeitpunkt or datetime.now().replace(microsecond=0),
        versand_weg=weg,
        datei_hash=datei_hash,
    )
    setze_mahnstufe(session, m.posten_id, m.stufe)
    return m


def verwerfe(session: Session, nr: int) -> Mahnung:
    _entwurf(session, nr)
    return setze_mahnung_status(session, nr, MahnungStatus.VERWORFEN)
