"""Kontakt zu einem Beleg finden oder anlegen — mit Personenkonto in der Rolle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from accounti.db.repository import (
    aktualisiere_kontakt,
    lade_kontakte,
    speichere_kontakt,
)
from accounti.konfiguration import Buchhaltung
from accounti.kontakte.erkennung import naechste_kontonummer, suche_kontakt
from accounti.models import Kontakt, KontaktStatus

Rolle = Literal["kreditor", "debitor"]


@dataclass(frozen=True)
class Partnerdaten:
    """Was ein Beleg über den Geschäftspartner verrät."""

    name: str
    ust_id: str | None = None
    iban: str | None = None
    strasse: str | None = None
    plz: str | None = None
    ort: str | None = None
    land: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class KontaktTreffer:
    kontakt: Kontakt
    neu: bool
    merkmal: str | None  # IBAN, USt-IdNr., Name — oder None bei Neuanlage
    # Treffer widerspricht dem Beleg (Buchung zur Prüfung) bzw. warum ein vorhandener
    # Kontakt nicht genommen wurde (Neuanlage zur Prüfung)
    widerspruch: str | None = None


def _belegte_konten(kontakte: list[Kontakt]) -> set[str]:
    return {
        konto
        for k in kontakte
        for konto in (k.kreditor_konto, k.debitor_konto)
        if konto is not None
    }


def kontakt_fuer(
    session: Session,
    einstellungen: Buchhaltung,
    rolle: Rolle,
    partner: Partnerdaten,
    *,
    neu_pruefen: bool,
    anlass: str,
    mit_anschrift: bool = False,
) -> KontaktTreffer:
    """Findet den Kontakt (IBAN → USt-IdNr. → Name) oder legt ihn an.

    ``neu_pruefen``: Neu angelegte Kontakte gehen zur Prüfung, statt still in die
    Stammdaten zu wandern (bei Eingangsbelegen). Fehlende Angaben eines gefundenen
    Kontakts werden aus dem Beleg ergänzt, vorhandene nie überschrieben.
    ``mit_anschrift``: Namenstreffer nur bei gleicher PLZ oder E-Mail (Kunden aus
    eigenen Rechnungen). Wurde ein gleichnamiger Kontakt bzw. einer mit gleicher IBAN
    verworfen, geht die Neuanlage immer zur Prüfung; ein Treffer, der dem Beleg
    widerspricht, wird nicht ergänzt (``widerspruch`` → Buchung zur Prüfung).
    """
    kontakte = lade_kontakte(session)
    suche = suche_kontakt(
        kontakte,
        iban=partner.iban,
        ust_id=partner.ust_id,
        name=partner.name,
        land=partner.land if mit_anschrift else None,
        plz=partner.plz,
        email=partner.email,
        mit_anschrift=mit_anschrift,
    )
    kontakt, merkmal = suche.kontakt, suche.merkmal
    von, bis = (
        (einstellungen.kreditoren_von, einstellungen.kreditoren_bis)
        if rolle == "kreditor"
        else (einstellungen.debitoren_von, einstellungen.debitoren_bis)
    )
    kontofeld = "kreditor_konto" if rolle == "kreditor" else "debitor_konto"

    if kontakt is None:
        pruefen = neu_pruefen or suche.widerspruch is not None
        grund = f"automatisch angelegt aus {anlass}" + (
            f" — {suche.widerspruch}" if suche.widerspruch else ""
        )
        nummer = naechste_kontonummer(_belegte_konten(kontakte), von, bis)
        kontakt = Kontakt(
            name=partner.name,
            strasse=partner.strasse,
            plz=partner.plz,
            ort=partner.ort,
            land=(partner.land or "DE").upper(),
            ust_id=partner.ust_id,
            iban=partner.iban,
            email=partner.email,
            status=KontaktStatus.ZUR_PRUEFUNG if pruefen else KontaktStatus.GEPRUEFT,
            pruef_grund=grund[:500] if pruefen else None,
            kreditor_konto=nummer if rolle == "kreditor" else None,
            debitor_konto=nummer if rolle == "debitor" else None,
        )
        speichere_kontakt(session, kontakt)
        return KontaktTreffer(
            kontakt, neu=True, merkmal=None, widerspruch=suche.widerspruch
        )
    if suche.widerspruch is not None:
        # nichts aus einem Beleg übernehmen, der zu diesem Kontakt nicht passt
        if getattr(kontakt, kontofeld) is None:
            konto = naechste_kontonummer(_belegte_konten(kontakte), von, bis)
            kontakt = aktualisiere_kontakt(
                session, kontakt.model_copy(update={kontofeld: konto})
            )
        return KontaktTreffer(kontakt, False, merkmal, suche.widerspruch)

    ergaenzt = {
        feld: wert
        for feld, wert in (
            ("ust_id", partner.ust_id),
            ("iban", partner.iban),
            ("strasse", partner.strasse),
            ("plz", partner.plz),
            ("ort", partner.ort),
            ("email", partner.email),
        )
        if wert and getattr(kontakt, feld) is None
    }
    if (
        partner.land
        and partner.land.upper() != kontakt.land.upper()
        and kontakt.land.upper() == "DE"
        and not (kontakt.strasse or kontakt.plz or kontakt.ort)
        and not (kontakt.ust_id or "").replace(" ", "").upper().startswith("DE")
    ):
        # „DE“ war nur die Vorgabe (Kreditor aus einem PDF ohne Land) — das Land aus
        # der USt-IdNr. des Belegs gilt
        ergaenzt["land"] = partner.land.upper()
    if getattr(kontakt, kontofeld) is None:
        ergaenzt[kontofeld] = naechste_kontonummer(_belegte_konten(kontakte), von, bis)
    if ergaenzt:
        kontakt = aktualisiere_kontakt(session, kontakt.model_copy(update=ergaenzt))
    return KontaktTreffer(kontakt, neu=False, merkmal=merkmal)
