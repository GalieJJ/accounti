"""Auszahlung ↔ Bankumsatz: der einzige Abgleichspunkt einer Abrechnung.

Gesucht wird ein noch nicht gebuchter, keinem offenen Posten zugeordneter Bankumsatz
mit **exakt** dem erwarteten Betrag im Zeitfenster um das Auszahlungsdatum. Gibt es
mehrere, entscheidet das Stichwort im Verwendungszweck — bleibt es mehrdeutig, wird
nicht geraten. Ein Umsatz in anderer Höhe mit Stichwort oder Abrechnungsnummer ist
ein Befund, ebenso ein Umsatz, den schon eine Regel als Erlös gebucht hat.

Gebucht wird „Bank an Verrechnungskonto“ (PayPal: Bank an Geldtransit) mit der
``transaktion_id`` des Bankumsatzes — damit lässt ``classify`` ihn in Ruhe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.repo_integrationen import (
    ergaenze_befunde,
    erledige_befunde,
    lade_abrechnungen,
    setze_abrechnungsstatus,
    setze_bank_transaktion,
)
from accounti.db.repository import (
    gebuchte_transaktion_ids,
    lade_buchungen,
    lade_transaktionen,
    speichere_buchung,
)
from accounti.integrationen.buchung import ANZEIGE, eur_text
from accounti.integrationen.einstellungen import Kontext
from accounti.models import Buchungssatz, BuchungStatus, Transaktion, TransaktionQuelle
from accounti.models.integrationen import (
    Abrechnung,
    AbrechnungStatus,
    Befund,
    Marktplatzposten,
    Postenart,
    Schweregrad,
)
from accounti.opos.zahlungslauf import offene_transaktionen

VORLAUF = timedelta(days=2)  # Bank bucht selten vor dem gemeldeten Auszahlungsdatum


@dataclass
class Abgleich:
    abrechnung: Abrechnung
    posten: Marktplatzposten
    transaktion: Transaktion | None = None
    befund: Befund | None = None


ABGLEICHSBEFUNDE = {
    "auszahlung_abweichung",
    "auszahlung_mehrdeutig",
    "auszahlung_anderweitig_gebucht",
}


def status_von(abrechnung: Abrechnung) -> AbrechnungStatus:
    """Status aus den offenen Befunden und den noch nicht abgeglichenen Posten."""
    if any(b.schweregrad is Schweregrad.FEHLER for b in abrechnung.offene_befunde):
        return AbrechnungStatus.ABWEICHUNG
    if not abrechnung.vollstaendig:
        return AbrechnungStatus.GEBUCHT  # die Auszahlung steht noch aus
    offen = [
        p
        for p in abrechnung.posten
        if p.art in (Postenart.AUSZAHLUNG, Postenart.EINZAHLUNG)
        and p.bank_transaktion_id is None
        and (p.betrag or p.betrag_eur)
    ]
    return AbrechnungStatus.GEBUCHT if offen else AbrechnungStatus.ABGEGLICHEN


@dataclass
class _Lauf:
    """Gemeinsamer Stand eines Abgleichslaufs über mehrere Abrechnungen."""

    session: Session
    kontext: Kontext
    bankumsaetze: list[Transaktion]
    offen_ids: set[UUID]
    gebucht: set[UUID]
    benutzt: set[UUID] = field(default_factory=set)


def gleiche_auszahlungen_ab(
    session: Session,
    kontext: Kontext,
    abrechnungen: list[Abrechnung] | None = None,
) -> list[Abgleich]:
    """Gleicht offene Auszahlungen (und PayPal-Einzahlungen) mit der Bank ab.

    Erst werden alle eindeutigen exakten Treffer zugeordnet — wiederholt, weil jeder
    Treffer die Kandidaten der übrigen verkleinert —, danach erst Befunde für den
    Rest gebildet. So ist ein Umsatz, den im selben Lauf eine andere Auszahlung
    bekommen hat, für niemanden eine Abweichung, unabhängig von der Reihenfolge.
    """
    e = kontext.einstellungen
    if abrechnungen is None:
        abrechnungen = lade_abrechnungen(session)
    marktkonten = {k.verrechnungskonto for k in e.marktplaetze.values()}
    lauf = _Lauf(
        session=session,
        kontext=kontext,
        bankumsaetze=[
            t
            for t in lade_transaktionen(session)
            if t.quelle is not TransaktionQuelle.PAYPAL
            and (t.sachkonto or kontext.buchhaltung.bank_konto) not in marktkonten
        ],
        offen_ids={t.id for t in offene_transaktionen(session, fuer_kontierung=True)},
        gebucht=gebuchte_transaktion_ids(session),
    )
    offene: list[tuple[Abrechnung, Marktplatzposten, Decimal]] = []
    for a in abrechnungen:
        for p in a.posten:
            if (
                p.art not in (Postenart.AUSZAHLUNG, Postenart.EINZAHLUNG)
                or p.bank_transaktion_id is not None
            ):
                continue
            if a.waehrung != "EUR" and p.betrag_eur is None:
                continue  # ohne Kurs nicht gebucht, also auch nicht abzugleichen
            erwartet = -(p.betrag_eur if p.betrag_eur is not None else p.betrag)
            if erwartet:
                offene.append((a, p, erwartet))

    ergebnisse: dict[UUID, Abgleich] = {}
    weiter = True
    while weiter:
        weiter = False
        for a, p, erwartet in offene:
            if p.id in ergebnisse:
                continue
            kandidaten = _kandidaten(lauf, a, p, erwartet)
            if len(kandidaten) == 1:
                ergebnisse[p.id] = _zuordnen(lauf, a, p, kandidaten[0])
                weiter = True
    neue_befunde: dict[UUID, list[Befund]] = {}
    for a, p, erwartet in offene:
        if p.id not in ergebnisse:
            ergebnis = _befund(lauf, a, p, erwartet)
            ergebnisse[p.id] = ergebnis
            if ergebnis.befund is not None:
                neue_befunde.setdefault(a.id, []).append(ergebnis.befund)

    for a in {a.id: a for a, _p, _e in offene}.values():
        befunde = neue_befunde.get(a.id, [])
        if befunde:
            ergaenze_befunde(session, a.id, befunde)
            a.befunde.extend(befunde)
        a.status = status_von(a)
        setze_abrechnungsstatus(session, a.id, a.status)
    return [ergebnisse[p.id] for _a, p, _e in offene]


def _fenster(lauf: _Lauf, p: Marktplatzposten) -> tuple[date, date]:
    toleranz = timedelta(days=lauf.kontext.einstellungen.auszahlung_toleranz_tage)
    return p.datum - VORLAUF, p.datum + toleranz


def _erkennbar(lauf: _Lauf, a: Abrechnung, t: Transaktion) -> bool:
    konten = lauf.kontext.einstellungen.marktplatz(a.marktplatz)
    text = f"{t.verwendungszweck} {t.gegenkonto_name or ''}".upper()
    return (
        any(w.upper() in text for w in konten.bank_stichworte)
        or a.nummer.upper() in text
    )


def _kandidaten(
    lauf: _Lauf, a: Abrechnung, p: Marktplatzposten, erwartet: Decimal
) -> list[Transaktion]:
    """Freie Bankumsätze mit exakt dem erwarteten Betrag im Zeitfenster."""
    von, bis = _fenster(lauf, p)
    kandidaten = [
        t
        for t in lauf.bankumsaetze
        if t.id in lauf.offen_ids
        and t.id not in lauf.benutzt
        and t.betrag == erwartet
        and von <= t.datum <= bis
    ]
    if len(kandidaten) > 1:
        kandidaten = [t for t in kandidaten if _erkennbar(lauf, a, t)] or kandidaten
    return kandidaten


def _zuordnen(
    lauf: _Lauf, a: Abrechnung, p: Marktplatzposten, t: Transaktion
) -> Abgleich:
    """Exakter Treffer: Befunde zu diesem Posten aus früheren Läufen erledigen sich."""
    erledigt = [
        b
        for b in a.offene_befunde
        if b.code in ABGLEICHSBEFUNDE and b.posten_nr == p.nr
    ]
    for b in erledigt:
        b.erledigt = True
    erledige_befunde(lauf.session, [b.id for b in erledigt])
    lauf.benutzt.add(t.id)
    setze_bank_transaktion(lauf.session, p.id, t.id)
    p.bank_transaktion_id = t.id
    a.status = status_von(a)
    _buche(lauf.session, lauf.kontext, a, t)
    return Abgleich(a, p, t)


def _befund(
    lauf: _Lauf, a: Abrechnung, p: Marktplatzposten, erwartet: Decimal
) -> Abgleich:
    """Kein eindeutiger Treffer: mehrdeutig, abweichend, anderweitig gebucht — oder
    einfach noch nicht auf der Bank."""
    konten = lauf.kontext.einstellungen.marktplatz(a.marktplatz)
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    von, bis = _fenster(lauf, p)
    kandidaten = _kandidaten(lauf, a, p, erwartet)
    if kandidaten:
        return Abgleich(
            a,
            p,
            befund=Befund(
                code="auszahlung_mehrdeutig",
                schweregrad=Schweregrad.WARNUNG,
                text=(
                    f"{markt} {a.nummer}: {len(kandidaten)} Bankumsätze über "
                    f"{eur_text(erwartet)} € passen — bitte zuordnen, es wird nicht "
                    "geraten"
                ),
                posten_nr=p.nr,
            ),
        )
    frei = [
        t
        for t in lauf.bankumsaetze
        if t.id not in lauf.benutzt and von <= t.datum <= bis and _erkennbar(lauf, a, t)
    ]
    anders = [
        t
        for t in frei
        if t.id in lauf.offen_ids
        and t.betrag != erwartet
        and (t.betrag > 0) == (erwartet > 0)
    ]
    if anders:
        t = anders[0]
        return Abgleich(
            a,
            p,
            befund=Befund(
                code="auszahlung_abweichung",
                schweregrad=Schweregrad.FEHLER,
                text=(
                    f"{markt} {a.nummer}: Bankumsatz vom {t.datum:%d.%m.%Y} über "
                    f"{eur_text(t.betrag)} € ≠ Auszahlung laut Abrechnung "
                    f"{eur_text(erwartet)} € — nicht gebucht, Differenz klären"
                ),
                posten_nr=p.nr,
            ),
        )
    schon = [t for t in frei if t.id in lauf.gebucht and t.betrag == erwartet]
    if schon:
        t = schon[0]
        ids = [
            str(b.id)[:8]
            for b in lade_buchungen(lauf.session)
            if b.transaktion_id == t.id
        ]
        bank = t.sachkonto or lauf.kontext.buchhaltung.bank_konto
        return Abgleich(
            a,
            p,
            befund=Befund(
                code="auszahlung_anderweitig_gebucht",
                schweregrad=Schweregrad.FEHLER,
                text=(
                    f"{markt} {a.nummer}: Der Bankumsatz vom {t.datum:%d.%m.%Y} ist "
                    f"schon gebucht ({', '.join(ids)}) — Erlöse wären doppelt. "
                    f"Korrigieren mit accounti korrigiere {ids[0] if ids else '<ID>'} "
                    f"--soll {bank} --haben {konten.verrechnungskonto} --ohne-steuer "
                    "(die Auszahlung ist eine Geldbewegung ohne Umsatzsteuer)"
                ),
                posten_nr=p.nr,
            ),
        )
    return Abgleich(a, p)


def _buche(session: Session, kontext: Kontext, a: Abrechnung, t: Transaktion) -> None:
    e = kontext.einstellungen
    bank = t.sachkonto or kontext.buchhaltung.bank_konto
    gegen = (
        e.geldtransit_konto
        if a.marktplatz == "paypal"
        else e.marktplatz(a.marktplatz).verrechnungskonto
    )
    soll, haben = (bank, gegen) if t.betrag > 0 else (gegen, bank)
    pruefen = status_von(a) is AbrechnungStatus.ABWEICHUNG
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    art = "Auszahlung" if t.betrag > 0 else "Einzahlung"
    speichere_buchung(
        session,
        Buchungssatz(
            transaktion_id=t.id,
            beleg_id=a.beleg_id,
            datum=t.datum,
            soll_konto=soll,
            haben_konto=haben,
            betrag_netto=abs(t.betrag),
            buchungstext=f"{markt} {art} {a.nummer}"[:60],
            beleg_nummer=a.nummer[:36],
            status=BuchungStatus.ZUR_PRUEFUNG
            if pruefen
            else BuchungStatus.AUTO_GEBUCHT,
            confidence=0.5 if pruefen else 1.0,
        ),
    )
    session.flush()
