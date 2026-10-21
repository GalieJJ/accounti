"""Anlagegut anlegen — mit Vorschlägen aus AfA-Tabelle, Rechtsstand und Beleg.

Der Zugang selbst wird über die normale Belegbuchung gebucht. Steht der Beleg nicht auf
dem Anlagekonto (z.B. als Aufwand kontiert), gibt es einen Hinweis und auf Wunsch einen
Umbuchungsvorschlag — eine zweite Zugangsbuchung entsteht nie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from accounti.anlagen.afa import pruefe_anlage, schlage_art_vor
from accounti.anlagen.konfiguration import AnlagenEinstellungen
from accounti.anlagen.rechtsstand import Rechtsstand
from accounti.anzeige import betrag_de
from accounti.db.repo_abschluss import pruefe_jahr_offen
from accounti.db.repo_anlagen import lade_anlagen, speichere_anlage
from accounti.db.repository import (
    lade_belegbuchungen,
    lade_belege,
    lade_buchungen,
    speichere_buchung,
)
from accounti.models import Beleg, Buchungssatz, BuchungStatus
from accounti.models.anlagen import AfaArt, Anlagegut

NULL = Decimal("0")


class AnlageError(ValueError):
    """Das Anlagegut kann so nicht angelegt werden."""


@dataclass
class Anlageergebnis:
    anlage: Anlagegut
    hinweise: list[str] = field(default_factory=list)
    umbuchung: Buchungssatz | None = None


def finde_beleg(session: Session, schluessel: str) -> Beleg:
    """Beleg über die Belegnummer oder den Anfang der ID."""
    treffer = [
        b
        for b in lade_belege(session)
        if b.belegnummer == schluessel or str(b.id).startswith(schluessel.lower())
    ]
    if len(treffer) != 1:
        grund = "nicht eindeutig" if treffer else "nicht gefunden"
        raise AnlageError(f"Beleg '{schluessel}' {grund}")
    return treffer[0]


def lege_an(
    session: Session,
    einstellungen: AnlagenEinstellungen,
    bezeichnung: str | None = None,
    datum: date | None = None,
    kosten: Decimal | None = None,
    konto: str | None = None,
    nutzungsdauer: int | None = None,
    art: AfaArt | None = None,
    typ: str | None = None,
    beleg: str | None = None,
    umbuchen: bool = False,
    immateriell: bool = False,
    wechsel_linear: bool = True,
    afa_konto: str | None = None,
    rechtsstand: Rechtsstand | None = None,
) -> Anlageergebnis:
    rs = rechtsstand or einstellungen.rechtsstand()
    hinweise: list[str] = []
    beleg_obj = finde_beleg(session, beleg) if beleg else None
    if beleg_obj is not None:
        if kosten is None:
            kosten = beleg_obj.netto
            if kosten is None and beleg_obj.brutto is not None:
                kosten = beleg_obj.brutto
                hinweise.append("Beleg ohne Nettobetrag — Bruttobetrag übernommen")
        datum = datum or beleg_obj.leistungsdatum or beleg_obj.belegdatum
        if bezeichnung is None:
            bezeichnung = (
                beleg_obj.positionen[0].bezeichnung
                if beleg_obj.positionen
                else beleg_obj.lieferant_name
            )
    if not bezeichnung or datum is None or kosten is None or kosten <= 0:
        raise AnlageError("Bezeichnung, Anschaffungsdatum und Kosten (netto) fehlen")
    # ein Zugang im abgeschlossenen Jahr änderte dessen AfA und Anlagenspiegel
    pruefe_jahr_offen(session, datum.year)

    eintrag = rs.afa_tabelle.get(typ) if typ else None
    if typ and eintrag is None:
        raise AnlageError(f"Typ '{typ}' steht nicht in der AfA-Tabelle")
    if eintrag is not None:
        angegeben = nutzungsdauer
        nutzungsdauer = nutzungsdauer or eintrag.nutzungsdauer
        immateriell = immateriell or eintrag.immateriell
        konto = konto or eintrag.konto.get(einstellungen.kontenrahmen)
        # die Art der Tabelle (digital: ND 1 Jahr) gilt nur mit deren Nutzungsdauer —
        # eine angegebene Nutzungsdauer hat Vorrang (BMF 22.02.2022: „kann“)
        if (
            art is None
            and eintrag.afa_art is not None
            and nutzungsdauer == eintrag.nutzungsdauer
        ):
            art = eintrag.afa_art
        if angegeben and angegeben != eintrag.nutzungsdauer:
            hinweise.append(
                f"Nutzungsdauer {angegeben} Jahre angegeben (AfA-Tabelle: "
                f"{eintrag.nutzungsdauer} Jahre laut {eintrag.fundstelle})"
            )
        else:
            hinweise.append(
                f"Nutzungsdauer {eintrag.nutzungsdauer} Jahre laut "
                f"{eintrag.fundstelle} — Vorschlag, änderbar"
            )
    bestand = lade_anlagen(session)
    if art is None:
        sammelposten_jahr = any(
            a.afa_art is AfaArt.SAMMELPOSTEN and a.anschaffungsdatum.year == datum.year
            for a in bestand
        )
        vorschlag = schlage_art_vor(kosten, datum, rs, sammelposten_jahr, nutzungsdauer)
        art = vorschlag.art
        hinweise.append(f"AfA-Art {art.value}: {vorschlag.begruendung}")
    if art is AfaArt.DIGITAL:
        if nutzungsdauer not in (None, 1):
            hinweise.append(
                f"AfA-Art digital: Nutzungsdauer 1 Jahr statt {nutzungsdauer} Jahren "
                "(BMF 22.02.2022) — für eine längere Nutzungsdauer --art linear"
            )
        nutzungsdauer = 1
    if art in (AfaArt.LINEAR, AfaArt.DEGRESSIV) and not nutzungsdauer:
        raise AnlageError("Nutzungsdauer fehlt (--nutzungsdauer oder --typ)")
    if konto is None:
        konto = {
            AfaArt.GWG: einstellungen.konten.gwg,
            AfaArt.SAMMELPOSTEN: einstellungen.konten.sammelposten,
        }.get(art)
    if konto is None:
        raise AnlageError("Anlagekonto fehlt (--konto oder --typ)")

    anlage = Anlagegut(
        bezeichnung=bezeichnung,
        konto=konto,
        afa_konto=afa_konto,
        anschaffungsdatum=datum,
        anschaffungskosten=kosten,
        nutzungsdauer=nutzungsdauer,
        afa_art=art,
        wechsel_linear=wechsel_linear,
        immateriell=immateriell,
        beleg_id=beleg_obj.id if beleg_obj else None,
        typ=typ,
    )
    pruefe_anlage(anlage, rs, bestand)
    anlage = speichere_anlage(session, anlage)
    ergebnis = Anlageergebnis(anlage, hinweise)
    if beleg_obj is not None:
        _pruefe_zugang(session, ergebnis, beleg_obj, umbuchen)
    session.flush()
    return ergebnis


def _pruefe_zugang(
    session: Session, ergebnis: Anlageergebnis, beleg: Beleg, umbuchen: bool
) -> None:
    anlage = ergebnis.anlage
    buchungen = lade_belegbuchungen(session, beleg.id)
    if not buchungen:
        ergebnis.hinweise.append(
            f"Beleg {beleg.belegnummer} ist noch nicht gebucht — Zugang auf "
            f"{anlage.konto} buchen"
        )
        return
    if any(b.soll_konto == anlage.konto for b in buchungen):
        return
    aufwand = [b for b in buchungen if b.soll_konto != anlage.konto]
    konten = sorted({b.soll_konto for b in aufwand})
    ergebnis.hinweise.append(
        f"Beleg {beleg.belegnummer} ist auf {', '.join(konto for konto in konten)} "
        f"gebucht, nicht auf dem Anlagekonto {anlage.konto} — Umbuchung nötig"
        + ("" if umbuchen else " (--umbuchen)")
    )
    if not umbuchen:
        return
    betrag = min(
        anlage.anschaffungskosten, sum((b.betrag_netto for b in aufwand), NULL)
    )
    umbuchung = Buchungssatz(
        beleg_id=beleg.id,
        datum=anlage.anschaffungsdatum,
        soll_konto=anlage.konto,
        haben_konto=konten[0],
        betrag_netto=betrag,
        buchungstext=f"Umbuchung Anlagezugang {anlage.bezeichnung}"[:60],
        beleg_nummer=(beleg.belegnummer or "")[:36] or None,
        status=BuchungStatus.ZUR_PRUEFUNG,
        confidence=1.0,
    )
    speichere_buchung(session, umbuchung)
    ergebnis.umbuchung = umbuchung
    ergebnis.hinweise.append(
        f"Umbuchung {anlage.konto} an {konten[0]} {betrag_de(betrag)} vorgeschlagen"
    )


def vorschlaege(
    session: Session, einstellungen: AnlagenEinstellungen, jahr: int
) -> list[Buchungssatz]:
    """Zugänge auf Anlagekonten im Jahr, zu denen es (noch) kein Anlagegut gibt."""
    belege = {a.beleg_id for a in lade_anlagen(session) if a.beleg_id}
    return [
        b
        for b in lade_buchungen(session)
        if b.datum.year == jahr
        and b.storniert_durch is None  # Storno-Paar: kein Zugang (Baustein 7)
        and b.storno_von is None
        and einstellungen.ist_anlagekonto(b.soll_konto)
        and not einstellungen.ist_anlagekonto(b.haben_konto)
        and not (b.beleg_nummer or "").startswith(("AfA-", "ANL-", "EB-"))
        and (b.beleg_id is None or b.beleg_id not in belege)
    ]
