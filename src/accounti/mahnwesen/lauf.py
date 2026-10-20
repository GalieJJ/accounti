"""Mahnlauf: Mahnungen berechnen, versenden, verwerfen.

Ein Lauf legt für jede fällige Stufe eine Mahnung als Entwurf an — mit Verzugszinsen
nach § 288 BGB, der 40-€-Pauschale bei Unternehmern (§ 288 Abs. 5, mit Anrechnung
der Mahngebühren nach Satz 3) und den Gebühren der Stufen. Erst das Versenden zählt
die Mahnstufe am offenen Posten hoch; versendete Mahnungen sind die Historie.

Mahngebühren sind Verzugsschaden (§§ 280 Abs. 2, 286 BGB): Verlangt werden nur die
Gebühren der Mahnungen, die im Verzug hinausgehen — die dieser Mahnung, wenn der
Verzug am Mahndatum schon besteht, und die früheren, deren Versandtag nicht vor dem
Verzugsbeginn liegt. Die Mahnung, die den Verzug erst begründet, kostet nichts.

Verzug (§ 286 BGB) beginnt am frühesten dieser Tage — Zinsen und Pauschale gibt es
erst ab da: am Tag nach Fälligkeit nur bei vertraglich vereinbartem Zahlungsziel
(Abs. 2 Nr. 1, ``mahnwesen.zahlungsziel_vereinbart``); durch die erste versendete
Mahnung (Abs. 1) ab dem Tag nach ihrem Zugang (Versand + ``zugang_tage``), bei einer
darin gesetzten Zahlungsfrist erst nach deren Ablauf; 30 Tage nach Fälligkeit und
Zugang der Rechnung (Abs. 3), bei Verbrauchern nur mit Hinweis auf der Rechnung
(``hinweis_30_tage``).

B2B oder B2C entscheidet in dieser Reihenfolge: Einstufung am Kontakt
(``accounti mahnwesen kunde``) → Ausgangsrechnung aus accounti (Privatkunde,
USt-IdNr. oder Leitweg-ID des Empfängers) → USt-IdNr. im Stammsatz →
``mahnwesen.unbekannt_als`` (Standard: Verbraucher — lieber zu wenig Zinsen verlangen
als eine unberechtigte Forderung stellen). Dass eine Rechnung *nicht* als privat
markiert ist, beweist nichts: Das ist ihr Standard.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.anzeige import datum_de
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
        kunde, nummer = rechnung.kunde, rechnung.nummer
        if kunde.privat:
            return False, f"Ausgangsrechnung {nummer}: Privatkunde"
        if kunde.ust_id:
            return True, f"Ausgangsrechnung {nummer}: USt-IdNr. {kunde.ust_id}"
        if kunde.leitweg_id:
            return (
                True,
                f"Ausgangsrechnung {nummer}: öffentlicher Auftraggeber (Leitweg-ID)",
            )
    if kontakt.ust_id:
        return True, f"USt-IdNr. {kontakt.ust_id} im Stammsatz"
    if e.unbekannt_als == "unternehmer":
        return (
            True,
            "keine Angabe — als Unternehmer behandelt (mahnwesen.unbekannt_als)",
        )
    return False, "keine Angabe — als Verbraucher behandelt (mahnwesen.unbekannt_als)"


@dataclass(frozen=True)
class ErsteMahnung:
    """Die erste versendete Mahnung eines Postens — sie begründet den Verzug."""

    stufe_name: str
    versendet: date
    zahlungsfrist: date


def verzugsbeginn(
    p: OffenerPosten,
    e: MahnEinstellungen,
    unternehmer: bool,
    erste_mahnung: ErsteMahnung | None,
) -> tuple[date | None, str]:
    """(Erster Zinstag, Grund) nach § 286 BGB — oder ``None``, wenn kein Verzug."""
    kandidaten: list[tuple[date, str]] = []
    if e.zahlungsziel_vereinbart:
        kandidaten.append(
            (
                p.faellig_am + timedelta(days=1),
                f"Zahlungsziel {datum_de(p.faellig_am)} vereinbart "
                "(§ 286 Abs. 2 Nr. 1 BGB)",
            )
        )
    if erste_mahnung is not None and erste_mahnung.versendet > p.faellig_am:
        zugang = erste_mahnung.versendet + timedelta(days=e.zugang_tage)
        name = erste_mahnung.stufe_name
        vom = datum_de(erste_mahnung.versendet)
        if erste_mahnung.zahlungsfrist >= zugang:
            ende = erste_mahnung.zahlungsfrist
            grund = f"{name} vom {vom}, Frist bis {datum_de(ende)} (§ 286 Abs. 1 BGB)"
        else:
            ende = zugang
            grund = (
                f"{name} vom {vom}, Zugang angenommen {datum_de(zugang)} "
                "(§ 286 Abs. 1 BGB)"
            )
        kandidaten.append((ende + timedelta(days=1), grund))
    if unternehmer or e.hinweis_30_tage:
        rechnung_da = p.belegdatum + timedelta(days=e.zugang_tage)
        kandidaten.append(
            (
                max(p.faellig_am, rechnung_da) + timedelta(days=31),
                "30 Tage nach Fälligkeit und Zugang der Rechnung (§ 286 Abs. 3 BGB)",
            )
        )
    if not kandidaten:
        return None, (
            "kein Verzug: weder Zahlungsziel vereinbart noch Mahnung zugegangen"
        )
    return min(kandidaten)


def gebuehren_im_verzug(
    e: MahnEinstellungen,
    stufe_nr: int,
    stichtag: date,
    verzug_ab: date | None,
    fruehere: Sequence[tuple[int, date]] = (),
) -> Decimal:
    """Erstattungsfähige Mahngebühren bis zur Stufe ``stufe_nr`` (vor der Anrechnung).

    ``fruehere``: (Stufe, Versandtag) der schon versendeten Mahnungen des Postens.
    Ohne Verzug am Mahndatum gibt es keine — auch nicht die früherer Stufen.
    """
    if verzug_ab is None or verzug_ab > stichtag:
        return NULL
    bisher = sum(
        (
            e.stufen[nr - 1].gebuehr
            for nr, versandtag in fruehere
            if nr < stufe_nr and versandtag >= verzug_ab
        ),
        NULL,
    )
    return bisher + e.stufen[stufe_nr - 1].gebuehr


def berechne(
    p: OffenerPosten,
    stufe_nr: int,
    stichtag: date,
    e: MahnEinstellungen,
    unternehmer: bool,
    grund: str,
    zahlungen: Sequence[tuple[date, Decimal]] = (),
    saetze: Sequence[Basiszins] | None = None,
    erste_mahnung: ErsteMahnung | None = None,
    fruehere: Sequence[tuple[int, date]] = (),
) -> Mahnung:
    """Beträge einer Mahnung — ohne Datenbank.

    ``fruehere``: (Stufe, Versandtag) der schon versendeten Mahnungen des Postens.
    Den Verzug ermittelt nur eine Stufe, die etwas verlangt, das ihn voraussetzt:
    Zinsen und Pauschale (``verzugszinsen``) oder Gebühren.
    """
    stufe = e.stufen[stufe_nr - 1]
    abschnitte = []
    verzug_ab: date | None = None
    verzug_grund: str | None = None
    gebuehr_moeglich = any(s.gebuehr > 0 for s in e.stufen[:stufe_nr])
    if stufe.verzugszinsen or gebuehr_moeglich:
        verzug_ab, verzug_grund = verzugsbeginn(p, e, unternehmer, erste_mahnung)
    im_verzug = verzug_ab is not None and verzug_ab <= stichtag
    folgen = stufe.verzugszinsen and im_verzug  # Zinsen und Pauschale
    if folgen and verzug_ab is not None:
        abschnitte = verzugszinsen(
            p.restbetrag, zahlungen, verzug_ab, stichtag, unternehmer, saetze
        )
    pauschale = e.pauschale_b2b if unternehmer and folgen else NULL
    kumuliert = gebuehren_im_verzug(e, stufe_nr, stichtag, verzug_ab, fruehere)
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
        verzug_grund=verzug_grund,
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


def _versandtag(m: Mahnung) -> date:
    return (m.versendet_am or datetime.combine(m.datum, datetime.min.time())).date()


def _zahlung_vorgeschlagen(session: Session) -> set[UUID]:
    return {
        z.posten_id
        for z in lade_zuordnungen(session, status={ZuordnungStatus.VORGESCHLAGEN})
    }


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
    versendet: dict[UUID, list[Mahnung]] = {}
    entwuerfe: dict[UUID, int] = {}
    for m in lade_mahnungen(session):
        if m.status is MahnungStatus.VERSENDET and m.versendet_am is not None:
            versendet.setdefault(m.posten_id, []).append(m)
        elif m.status is MahnungStatus.ENTWURF:
            entwuerfe[m.posten_id] = m.nr
    letzte: dict[UUID, date] = {}  # Versandtag der letzten Mahnung
    frist: dict[UUID, date] = {}  # die Frist, die sie gesetzt hat
    erste: dict[UUID, ErsteMahnung] = {}
    fruehere: dict[UUID, list[tuple[int, date]]] = {}  # (Stufe, Versandtag)
    for posten_id, liste in versendet.items():
        liste.sort(key=lambda m: (_versandtag(m), m.stufe))
        letzte[posten_id] = _versandtag(liste[-1])
        frist[posten_id] = max(m.zahlungsfrist for m in liste)
        erste[posten_id] = ErsteMahnung(
            liste[0].stufe_name, _versandtag(liste[0]), liste[0].zahlungsfrist
        )
        fruehere[posten_id] = [(m.stufe, _versandtag(m)) for m in liste]
    vorgeschlagen = _zahlung_vorgeschlagen(session)
    faellig, lauf.ausnahmen = ermittle(
        posten,
        kontakte,
        stichtag,
        e,
        letzte_mahnung=letzte,
        frist_bis=frist,
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
                erste.get(f.posten.id),
                fruehere.get(f.posten.id, ()),
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


def pruefe_versendbar(
    session: Session, nr: int, e: MahnEinstellungen, am: date
) -> Mahnung:
    """Der Entwurf, wenn er am Versandtag ``am`` so noch stimmt — sonst ``MahnError``.

    Seit dem Lauf kann der Kunde gezahlt haben, eine Mahnsperre bekommen haben oder
    der Entwurf so alt sein, dass Datum, Zinsen und Frist im Brief nicht mehr passen.
    """
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
    mahnkontakt = lade_mahnkontakte(session).get(m.kontakt_id)
    if mahnkontakt is not None and mahnkontakt.mahnsperre:
        msg = (
            f"Mahnsperre: {mahnkontakt.sperrgrund or 'ohne Grund'} — Mahnung "
            f"{nr} nicht versenden (verwerfen oder Sperre aufheben)"
        )
        raise MahnError(msg)
    if m.posten_id in _zahlung_vorgeschlagen(session):
        msg = (
            f"Zahlung vorgeschlagen für {p.belegnummer} — erst 'accounti opos "
            "bestaetigen' oder 'accounti opos ablehnen'"
        )
        raise MahnError(msg)
    if am < m.datum:
        msg = f"Mahnung {nr} ist auf den {datum_de(m.datum)} datiert — frühestens dann"
        raise MahnError(msg)
    if (am - m.datum).days > e.entwurf_gueltig_tage or m.zahlungsfrist <= am:
        msg = (
            f"Mahnung {nr} vom {datum_de(m.datum)} ist veraltet (mehr als "
            f"{e.entwurf_gueltig_tage} Tage alt, mahnwesen.entwurf_gueltig_tage) — "
            "verwerfen und den Mahnlauf wiederholen"
        )
        raise MahnError(msg)
    return m


def versende(
    session: Session,
    nr: int,
    weg: str,
    e: MahnEinstellungen,
    datei_hash: str | None = None,
    zeitpunkt: datetime | None = None,
) -> Mahnung:
    """Markiert die Mahnung als versendet und zählt die Mahnstufe am Posten hoch."""
    zeitpunkt = zeitpunkt or datetime.now().replace(microsecond=0)
    pruefe_versendbar(session, nr, e, zeitpunkt.date())
    m = setze_mahnung_status(
        session,
        nr,
        MahnungStatus.VERSENDET,
        versendet_am=zeitpunkt,
        versand_weg=weg,
        datei_hash=datei_hash,
    )
    setze_mahnstufe(session, m.posten_id, m.stufe)
    return m


def verwerfe(session: Session, nr: int) -> Mahnung:
    _entwurf(session, nr)
    return setze_mahnung_status(session, nr, MahnungStatus.VERWORFEN)
