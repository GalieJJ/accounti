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

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.repo_integrationen import (
    ergaenze_befunde,
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


def status_von(abrechnung: Abrechnung) -> AbrechnungStatus:
    if any(b.schweregrad is Schweregrad.FEHLER for b in abrechnung.befunde):
        return AbrechnungStatus.ABWEICHUNG
    offen = [
        p
        for p in abrechnung.posten
        if p.art in (Postenart.AUSZAHLUNG, Postenart.EINZAHLUNG)
        and p.bank_transaktion_id is None
        and (p.betrag or p.betrag_eur)
    ]
    return AbrechnungStatus.GEBUCHT if offen else AbrechnungStatus.ABGEGLICHEN


def gleiche_auszahlungen_ab(
    session: Session,
    kontext: Kontext,
    abrechnungen: list[Abrechnung] | None = None,
) -> list[Abgleich]:
    """Gleicht offene Auszahlungen (und PayPal-Einzahlungen) mit der Bank ab."""
    e = kontext.einstellungen
    if abrechnungen is None:
        abrechnungen = lade_abrechnungen(session)
    offen_ids = {t.id for t in offene_transaktionen(session, fuer_kontierung=True)}
    gebucht = gebuchte_transaktion_ids(session)
    marktkonten = {k.verrechnungskonto for k in e.marktplaetze.values()}
    bankumsaetze = [
        t
        for t in lade_transaktionen(session)
        if t.quelle is not TransaktionQuelle.PAYPAL
        and (t.sachkonto or kontext.buchhaltung.bank_konto) not in marktkonten
    ]
    benutzt: set[UUID] = set()
    ergebnisse: list[Abgleich] = []
    for a in abrechnungen:
        offene_posten = [
            p
            for p in a.posten
            if p.art in (Postenart.AUSZAHLUNG, Postenart.EINZAHLUNG)
            and p.bank_transaktion_id is None
        ]
        if not offene_posten:
            continue
        neue_befunde: list[Befund] = []
        for p in offene_posten:
            if a.waehrung != "EUR" and p.betrag_eur is None:
                continue  # ohne Kurs nicht gebucht, also auch nicht abzugleichen
            erwartet = -(p.betrag_eur if p.betrag_eur is not None else p.betrag)
            if not erwartet:
                continue
            ergebnis = _gleiche_ab(
                session,
                kontext,
                a,
                p,
                erwartet,
                bankumsaetze,
                offen_ids,
                gebucht,
                benutzt,
            )
            ergebnisse.append(ergebnis)
            if ergebnis.befund is not None:
                neue_befunde.append(ergebnis.befund)
        if neue_befunde:
            ergaenze_befunde(session, a.id, neue_befunde)
            a.befunde.extend(neue_befunde)
        a.status = status_von(a)
        setze_abrechnungsstatus(session, a.id, a.status)
    return ergebnisse


def _gleiche_ab(
    session: Session,
    kontext: Kontext,
    a: Abrechnung,
    p: Marktplatzposten,
    erwartet: Decimal,
    bankumsaetze: list[Transaktion],
    offen_ids: set[UUID],
    gebucht: set[UUID],
    benutzt: set[UUID],
) -> Abgleich:
    konten = kontext.einstellungen.marktplatz(a.marktplatz)
    stichworte = [w.upper() for w in konten.bank_stichworte]
    bis = p.datum + timedelta(days=kontext.einstellungen.auszahlung_toleranz_tage)

    def im_fenster(t: Transaktion) -> bool:
        return p.datum - VORLAUF <= t.datum <= bis

    def erkennbar(t: Transaktion) -> bool:
        text = f"{t.verwendungszweck} {t.gegenkonto_name or ''}".upper()
        return any(w in text for w in stichworte) or a.nummer.upper() in text

    kandidaten = [
        t
        for t in bankumsaetze
        if t.id in offen_ids
        and t.id not in benutzt
        and t.betrag == erwartet
        and im_fenster(t)
    ]
    if len(kandidaten) > 1:
        kandidaten = [t for t in kandidaten if erkennbar(t)] or kandidaten
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    if len(kandidaten) == 1:
        (t,) = kandidaten
        _buche(session, kontext, a, t)
        benutzt.add(t.id)
        setze_bank_transaktion(session, p.id, t.id)
        p.bank_transaktion_id = t.id
        return Abgleich(a, p, t)
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
    anders = [
        t
        for t in bankumsaetze
        if t.id in offen_ids
        and im_fenster(t)
        and erkennbar(t)
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
    schon = [
        t
        for t in bankumsaetze
        if t.id in gebucht and im_fenster(t) and t.betrag == erwartet and erkennbar(t)
    ]
    if schon:
        t = schon[0]
        ids = [
            str(b.id)[:8] for b in lade_buchungen(session) if b.transaktion_id == t.id
        ]
        bank = t.sachkonto or kontext.buchhaltung.bank_konto
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
                    f"--soll {bank} --haben {konten.verrechnungskonto}"
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
    pruefen = a.status is AbrechnungStatus.ABWEICHUNG
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
