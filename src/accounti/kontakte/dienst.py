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
from accounti.kontakte.erkennung import finde_kontakt, naechste_kontonummer
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
) -> KontaktTreffer:
    """Findet den Kontakt (IBAN → USt-IdNr. → Name) oder legt ihn an.

    ``neu_pruefen``: Neu angelegte Kontakte gehen zur Prüfung, statt still in die
    Stammdaten zu wandern (bei Eingangsbelegen). Fehlende Angaben eines gefundenen
    Kontakts werden aus dem Beleg ergänzt, vorhandene nie überschrieben.
    """
    kontakte = lade_kontakte(session)
    kontakt, merkmal = finde_kontakt(
        kontakte, iban=partner.iban, ust_id=partner.ust_id, name=partner.name
    )
    von, bis = (
        (einstellungen.kreditoren_von, einstellungen.kreditoren_bis)
        if rolle == "kreditor"
        else (einstellungen.debitoren_von, einstellungen.debitoren_bis)
    )
    kontofeld = "kreditor_konto" if rolle == "kreditor" else "debitor_konto"

    if kontakt is None:
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
            status=KontaktStatus.ZUR_PRUEFUNG
            if neu_pruefen
            else KontaktStatus.GEPRUEFT,
            pruef_grund=f"automatisch angelegt aus {anlass}" if neu_pruefen else None,
            kreditor_konto=nummer if rolle == "kreditor" else None,
            debitor_konto=nummer if rolle == "debitor" else None,
        )
        speichere_kontakt(session, kontakt)
        return KontaktTreffer(kontakt, neu=True, merkmal=None)

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
    if getattr(kontakt, kontofeld) is None:
        ergaenzt[kontofeld] = naechste_kontonummer(_belegte_konten(kontakte), von, bis)
    if ergaenzt:
        kontakt = aktualisiere_kontakt(session, kontakt.model_copy(update=ergaenzt))
    return KontaktTreffer(kontakt, neu=False, merkmal=merkmal)
