"""Testdaten für Zahlungsverkehr und Mahnwesen: Kontakte, Belege, offene Posten."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from accounti.db import init_db, session_factory
from accounti.db.repository import (
    speichere_beleg,
    speichere_kontakt,
    speichere_posten,
    speichere_transaktion,
    speichere_zuordnung,
)
from accounti.models import (
    Beleg,
    Belegart,
    Belegrichtung,
    BelegStatus,
    Kontakt,
    KontaktStatus,
    OffenerPosten,
    PostenRichtung,
    PostenStatus,
    Transaktion,
    TransaktionQuelle,
    Zahlungszuordnung,
    ZuordnungStatus,
)

IBAN_MUELLER = "DE89370400440532013000"
IBAN_SCHULZ = "DE02120300000000202051"
IBAN_BETRUG = "DE75512108001245126199"
IBAN_EIGEN = "DE12500105170648489890"
STICHTAG = date(2026, 10, 20)


def neue_db():
    """Leere In-Memory-Datenbank, gibt die Session-Fabrik zurück."""
    engine, fabrik = session_factory("sqlite:///:memory:")
    init_db(engine)
    return fabrik


def kreditor(
    name: str = "Bürobedarf Müller GmbH",
    konto: str = "70001",
    iban: str | None = IBAN_MUELLER,
    **kw: object,
) -> Kontakt:
    werte: dict[str, object] = {
        "strasse": "Hauptstraße 12a",
        "plz": "24103",
        "ort": "Kiel",
        "status": KontaktStatus.GEPRUEFT,
    }
    werte.update(kw)
    return Kontakt(name=name, kreditor_konto=konto, iban=iban, **werte)


def debitor(
    name: str = "Atelier Kundin GmbH", konto: str = "10001", **kw: object
) -> Kontakt:
    werte: dict[str, object] = {
        "strasse": "Kundenstraße 8",
        "plz": "10115",
        "ort": "Berlin",
        "status": KontaktStatus.GEPRUEFT,
    }
    werte.update(kw)
    return Kontakt(name=name, debitor_konto=konto, **werte)


def posten(
    kontakt: Kontakt,
    nummer: str = "RE-2026-0042",
    betrag: str = "1190.00",
    faellig: date = date(2026, 11, 15),
    belegdatum: date = date(2026, 10, 10),
    skonto_bis: date | None = None,
    skonto_prozent: str | None = None,
    rest: str | None = None,
    richtung: PostenRichtung = PostenRichtung.VERBINDLICHKEIT,
    **kw: object,
) -> OffenerPosten:
    brutto = Decimal(betrag)
    skonto_betrag = (
        (brutto * Decimal(skonto_prozent) / 100).quantize(Decimal("0.01"))
        if skonto_prozent
        else None
    )
    restbetrag = Decimal(rest) if rest is not None else brutto
    status = PostenStatus.OFFEN if restbetrag == brutto else PostenStatus.TEILBEZAHLT
    if restbetrag == 0:
        status = PostenStatus.AUSGEGLICHEN
    werte: dict[str, object] = {
        "kontakt_id": kontakt.id,
        "beleg_id": uuid4(),
        "richtung": richtung,
        "belegnummer": nummer,
        "belegdatum": belegdatum,
        "betrag": brutto,
        "restbetrag": restbetrag,
        "faellig_am": faellig,
        "skonto_bis": skonto_bis,
        "skonto_prozent": Decimal(skonto_prozent) if skonto_prozent else None,
        "skonto_betrag": skonto_betrag,
        "status": status,
    }
    werte.update(kw)
    return OffenerPosten.model_validate(werte)


def beleg_zu(
    p: OffenerPosten, iban: str | None = IBAN_MUELLER, waehrung: str = "EUR"
) -> Beleg:
    eingang = p.richtung is PostenRichtung.VERBINDLICHKEIT
    return Beleg(
        id=p.beleg_id,
        belegart=Belegart.EINGANGSRECHNUNG if eingang else Belegart.AUSGANGSRECHNUNG,
        richtung=Belegrichtung.EINGANG if eingang else Belegrichtung.AUSGANG,
        belegnummer=p.belegnummer,
        belegdatum=p.belegdatum,
        kontakt_id=p.kontakt_id,
        iban=iban,
        brutto=p.betrag,
        waehrung=waehrung,
        datei_hash=p.beleg_id.hex + p.beleg_id.hex,
        dateiname=f"{p.belegnummer}.pdf",
        kanal="ordner",
        herkunft="test",
        aufbewahren_bis=date(2036, 12, 31),
        status=BelegStatus.ERFASST,
    )


def speichere(
    make_session: object,
    kontakte: list[Kontakt],
    alle_posten: list[OffenerPosten],
    belege: list[Beleg] | None = None,
) -> None:
    """Kontakte, Belege (Standard: je Posten einer mit Stammsatz-IBAN) und Posten."""
    nach_id = {k.id: k for k in kontakte}
    if belege is None:
        belege = [beleg_zu(p, nach_id[p.kontakt_id].iban) for p in alle_posten]
    with make_session() as s:
        for k in kontakte:
            speichere_kontakt(s, k)
        for b in belege:
            speichere_beleg(s, b)
        for p in alle_posten:
            speichere_posten(s, p)
        s.commit()


def zahlung_vorschlagen(
    make_session: object,
    p: OffenerPosten,
    betrag: str | None = None,
    datum: date = date(2026, 10, 18),
    status: ZuordnungStatus = ZuordnungStatus.VORGESCHLAGEN,
) -> Zahlungszuordnung:
    """Bankumsatz zum Posten, den ``opos zuordnen`` ihm als Zahlung vorschlägt."""
    wert = Decimal(betrag) if betrag is not None else p.restbetrag
    ausgang = p.richtung is PostenRichtung.VERBINDLICHKEIT
    tx = Transaktion(
        datum=datum,
        betrag=-wert if ausgang else wert,
        verwendungszweck=f"{p.belegnummer} Zahlung",
        quelle=TransaktionQuelle.BANK,
        rohtext="test",
    )
    zuordnung = Zahlungszuordnung(
        transaktion_id=tx.id,
        posten_id=p.id,
        betrag=wert,
        stufe="referenz",
        status=status,
        confidence=0.9,
        begruendung="Test",
    )
    with make_session() as s:
        speichere_transaktion(s, tx)
        speichere_zuordnung(s, zuordnung)
        s.commit()
    return zuordnung
