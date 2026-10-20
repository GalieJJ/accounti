"""Repository für Marktplatz-Abrechnungen, ihre Posten und Befunde (Baustein 11)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.tabellen_integrationen import (
    MarktplatzAbrechnungRow,
    MarktplatzBefundRow,
    MarktplatzPostenRow,
)
from accounti.models.integrationen import (
    Abrechnung,
    AbrechnungStatus,
    Befund,
    Gebuehrenart,
    Marktplatzposten,
    Postenart,
    Schweregrad,
)


def _dec(wert: Decimal | None) -> Decimal | None:
    return Decimal(str(wert)) if wert is not None else None


def _posten_zeile(abrechnung_id: UUID, p: Marktplatzposten) -> MarktplatzPostenRow:
    return MarktplatzPostenRow(
        id=str(p.id),
        abrechnung_id=str(abrechnung_id),
        nr=p.nr,
        art=p.art.value,
        datum=p.datum,
        betrag=p.betrag,
        waehrung=p.waehrung,
        betrag_eur=p.betrag_eur,
        beschreibung=p.beschreibung[:500],
        gebuehrenart=p.gebuehrenart.value if p.gebuehrenart else None,
        bestellnummer=(p.bestellnummer or "")[:80] or None,
        artikel=(p.artikel or "")[:100] or None,
        bestimmungsland=p.bestimmungsland,
        abgangsland=p.abgangsland,
        kaeufer_ust_id=(p.kaeufer_ust_id or "")[:20] or None,
        versand_durch_marktplatz=p.versand_durch_marktplatz,
        geschaeftskunde=p.geschaeftskunde,
        auszahlungs_nr=p.auszahlungs_nr,
        referenz=p.referenz,
        gegenpartei=(p.gegenpartei or "")[:200] or None,
        bank_transaktion_id=str(p.bank_transaktion_id)
        if p.bank_transaktion_id
        else None,
    )


def _befund_zeile(abrechnung_id: UUID, b: Befund) -> MarktplatzBefundRow:
    return MarktplatzBefundRow(
        id=str(b.id),
        abrechnung_id=str(abrechnung_id),
        code=b.code,
        schweregrad=b.schweregrad.value,
        text=b.text[:1000],
        posten_nr=b.posten_nr,
        erstellt_am=b.erstellt_am,
    )


def speichere_abrechnung(session: Session, a: Abrechnung) -> None:
    session.add(
        MarktplatzAbrechnungRow(
            id=str(a.id),
            marktplatz=a.marktplatz,
            nummer=a.nummer,
            von=a.von,
            bis=a.bis,
            auszahlungsdatum=a.auszahlungsdatum,
            waehrung=a.waehrung,
            auszahlung=a.auszahlung,
            kurs=a.kurs,
            anfangssaldo=a.anfangssaldo,
            endsaldo=a.endsaldo,
            dateiname=a.dateiname[:255],
            beleg_id=str(a.beleg_id) if a.beleg_id else None,
            status=a.status.value,
            importiert_am=a.importiert_am,
        )
    )
    session.flush()
    for p in a.posten:
        session.add(_posten_zeile(a.id, p))
    for b in a.befunde:
        session.add(_befund_zeile(a.id, b))
    session.flush()


def _abrechnung(
    r: MarktplatzAbrechnungRow,
    posten: list[MarktplatzPostenRow],
    befunde: list[MarktplatzBefundRow],
) -> Abrechnung:
    return Abrechnung(
        id=UUID(r.id),
        marktplatz=r.marktplatz,
        nummer=r.nummer,
        von=r.von,
        bis=r.bis,
        auszahlungsdatum=r.auszahlungsdatum,
        waehrung=r.waehrung,
        auszahlung=_dec(r.auszahlung),
        kurs=_dec(r.kurs),
        anfangssaldo=_dec(r.anfangssaldo),
        endsaldo=_dec(r.endsaldo),
        dateiname=r.dateiname,
        beleg_id=UUID(r.beleg_id) if r.beleg_id else None,
        status=AbrechnungStatus(r.status),
        importiert_am=r.importiert_am,
        posten=[
            Marktplatzposten(
                id=UUID(p.id),
                nr=p.nr,
                art=Postenart(p.art),
                datum=p.datum,
                betrag=Decimal(str(p.betrag)),
                waehrung=p.waehrung,
                betrag_eur=_dec(p.betrag_eur),
                beschreibung=p.beschreibung,
                gebuehrenart=Gebuehrenart(p.gebuehrenart) if p.gebuehrenart else None,
                bestellnummer=p.bestellnummer,
                artikel=p.artikel,
                bestimmungsland=p.bestimmungsland,
                abgangsland=p.abgangsland,
                kaeufer_ust_id=p.kaeufer_ust_id,
                versand_durch_marktplatz=bool(p.versand_durch_marktplatz),
                geschaeftskunde=bool(p.geschaeftskunde),
                auszahlungs_nr=p.auszahlungs_nr,
                referenz=p.referenz,
                gegenpartei=p.gegenpartei,
                bank_transaktion_id=UUID(p.bank_transaktion_id)
                if p.bank_transaktion_id
                else None,
            )
            for p in sorted(posten, key=lambda x: (x.nr, x.datum))
        ],
        befunde=[
            Befund(
                id=UUID(b.id),
                code=b.code,
                schweregrad=Schweregrad(b.schweregrad),
                text=b.text,
                posten_nr=b.posten_nr,
                erstellt_am=b.erstellt_am,
            )
            for b in sorted(befunde, key=lambda x: x.erstellt_am)
        ],
    )


def lade_abrechnungen(
    session: Session, marktplatz: str | None = None
) -> list[Abrechnung]:
    query = session.query(MarktplatzAbrechnungRow)
    if marktplatz is not None:
        query = query.filter(MarktplatzAbrechnungRow.marktplatz == marktplatz)
    rows = query.order_by(MarktplatzAbrechnungRow.von, MarktplatzAbrechnungRow.nummer)
    ergebnis = []
    for r in rows.all():
        posten = (
            session.query(MarktplatzPostenRow)
            .filter(MarktplatzPostenRow.abrechnung_id == r.id)
            .all()
        )
        befunde = (
            session.query(MarktplatzBefundRow)
            .filter(MarktplatzBefundRow.abrechnung_id == r.id)
            .all()
        )
        ergebnis.append(_abrechnung(r, posten, befunde))
    return ergebnis


def lade_abrechnung(session: Session, schluessel: str) -> Abrechnung:
    """Abrechnung über ihre Nummer oder den Anfang der ID."""
    treffer = [
        a
        for a in lade_abrechnungen(session)
        if a.nummer == schluessel or str(a.id).startswith(schluessel.lower())
    ]
    if len(treffer) != 1:
        msg = (
            f"Keine Abrechnung '{schluessel}'"
            if not treffer
            else f"'{schluessel}' ist nicht eindeutig"
        )
        raise ValueError(msg)
    return treffer[0]


def abrechnung_vorhanden(session: Session, marktplatz: str, nummer: str) -> bool:
    return (
        session.query(MarktplatzAbrechnungRow.id)
        .filter(
            MarktplatzAbrechnungRow.marktplatz == marktplatz,
            MarktplatzAbrechnungRow.nummer == nummer,
        )
        .first()
        is not None
    )


def vorhandene_referenzen(session: Session, marktplatz: str) -> set[str]:
    """Referenzen (PayPal-Transaktionscodes) schon importierter Posten."""
    rows = (
        session.query(MarktplatzPostenRow.referenz)
        .join(
            MarktplatzAbrechnungRow,
            MarktplatzAbrechnungRow.id == MarktplatzPostenRow.abrechnung_id,
        )
        .filter(
            MarktplatzAbrechnungRow.marktplatz == marktplatz,
            MarktplatzPostenRow.referenz.is_not(None),
        )
        .all()
    )
    return {r for (r,) in rows if r}


def ergaenze_befunde(
    session: Session, abrechnung_id: UUID, befunde: list[Befund]
) -> int:
    """Hängt neue Befunde an; gleiche (Code und Text) werden nicht wiederholt."""
    vorhanden = {
        (b.code, b.text)
        for b in session.query(MarktplatzBefundRow)
        .filter(MarktplatzBefundRow.abrechnung_id == str(abrechnung_id))
        .all()
    }
    neu = 0
    for b in befunde:
        if (b.code, b.text[:1000]) in vorhanden:
            continue
        session.add(_befund_zeile(abrechnung_id, b))
        vorhanden.add((b.code, b.text[:1000]))
        neu += 1
    session.flush()
    return neu


def setze_bank_transaktion(
    session: Session, posten_id: UUID, transaktion_id: UUID
) -> None:
    row = session.get(MarktplatzPostenRow, str(posten_id))
    if row is None:
        raise ValueError(f"Posten {posten_id} nicht gefunden")
    row.bank_transaktion_id = str(transaktion_id)
    session.flush()


def setze_abrechnungsstatus(
    session: Session, abrechnung_id: UUID, status: AbrechnungStatus
) -> None:
    row = session.get(MarktplatzAbrechnungRow, str(abrechnung_id))
    if row is None:
        raise ValueError(f"Abrechnung {abrechnung_id} nicht gefunden")
    row.status = status.value
    session.flush()


def transaktionen_zu_schluesseln(
    session: Session, schluessel: set[str]
) -> dict[str, UUID]:
    """Dublettenschlüssel → ID der schon gespeicherten Transaktion."""
    from accounti.db.tabellen import TransaktionRow

    if not schluessel:
        return {}
    rows = (
        session.query(TransaktionRow.dublettenschluessel, TransaktionRow.id)
        .filter(TransaktionRow.dublettenschluessel.in_(list(schluessel)))
        .all()
    )
    return {s: UUID(i) for s, i in rows if s}
