"""Übermittlungsprotokoll — Datensatz, Ticket, Zeitpunkt, Ergebnis, Prüfbericht.

Muster wie das USt-IdNr.-Protokoll (``kontakte/ustid.py``): Einträge werden nur
angefügt, jeder trägt den Hash seines Vorgängers; Änderungen und Löschungen scheitern
am ORM und unter SQLite an Triggern. Der Datensatz liegt zusätzlich unverändert im
Belegarchiv (content-adressiert, schreibgeschützt). ``pruefe_protokoll`` findet
Lücken, veränderte Einträge und veränderte Archivdateien. Eine berichtigte Anmeldung
tritt neben die alte.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.belege.archiv import BelegArchiv, aufbewahrungsende
from accounti.betrieb.aufbewahrung import Unterlage
from accounti.db.repo_elster import letzte_uebermittlung, speichere_uebermittlung
from accounti.models.elster import Meldeart, Modus, Uebermittlung

GENESIS = "0" * 64


def neuer_eintrag(
    archiv: BelegArchiv | None,
    *,
    art: Meldeart,
    zeitraum: str,
    modus: Modus,
    weg: str,
    datensatz: str,
    erfolgreich: bool,
    ergebnis: str,
    pruefbericht: str,
    zeitpunkt: datetime | None = None,
    berichtigt: bool = False,
    freigabe_id: UUID | None = None,
    freigegeben_von: str | None = None,
    ticket: str | None = None,
    server_antwort: str | None = None,
    pdf: bytes | None = None,
    betrag: Decimal | None = None,
) -> Uebermittlung:
    """Eintrag mit Datensatz (und ERiC-PDF) im Archiv — noch nicht protokolliert."""
    inhalt = datensatz.encode("utf-8")
    datensatz_hash = (
        archiv.ablegen(inhalt, ".xml")
        if archiv is not None
        else hashlib.sha256(inhalt).hexdigest()
    )
    pdf_hash = None
    if pdf is not None:
        pdf_hash = (
            archiv.ablegen(pdf, ".pdf")
            if archiv is not None
            else hashlib.sha256(pdf).hexdigest()
        )
    zeitpunkt = zeitpunkt or datetime.now()
    return Uebermittlung(
        zeitpunkt=zeitpunkt,
        art=art,
        zeitraum=zeitraum,
        modus=modus,
        weg=weg,
        berichtigt=berichtigt,
        freigabe_id=freigabe_id,
        freigegeben_von=freigegeben_von,
        datensatz=datensatz,
        datensatz_hash=datensatz_hash,
        ticket=ticket,
        erfolgreich=erfolgreich,
        ergebnis=ergebnis,
        pruefbericht=pruefbericht,
        server_antwort=server_antwort,
        protokoll_pdf_hash=pdf_hash,
        betrag=betrag,
        # Protokoll = Aufzeichnung (§ 147 Abs. 1 Nr. 1 AO): 10 Jahre
        aufbewahren_bis=aufbewahrungsende(zeitpunkt.date(), Unterlage.BUCH),
    )


def eintrag_hash(u: Uebermittlung) -> str:
    """SHA-256 über alle Felder außer dem Hash — inklusive Vorgänger-Hash."""
    daten: dict[str, Any] = u.model_dump(mode="json", exclude={"hash"})
    roh = json.dumps(daten, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(roh.encode()).hexdigest()


def protokolliere(session: Session, u: Uebermittlung) -> Uebermittlung:
    """Hängt den Eintrag an (Nummer, Verkettung, Hash). Der Aufrufer schreibt sofort
    fest — der Nachweis darf nicht mit einem späteren Fehler verschwinden."""
    letzte = letzte_uebermittlung(session)
    zeitpunkt = u.zeitpunkt
    if zeitpunkt.tzinfo is not None:  # die Datenbank speichert ohne Zeitzone
        zeitpunkt = zeitpunkt.astimezone().replace(tzinfo=None)
    # Werte so, wie die Datenbank sie zurückgibt — sonst passt der Hash nach dem Laden
    betrag = u.betrag.quantize(Decimal("0.01")) if u.betrag is not None else None
    eintrag = u.model_copy(
        update={
            "nr": letzte.nr + 1 if letzte else 1,
            "vorgaenger_hash": letzte.hash if letzte else GENESIS,
            "zeitpunkt": zeitpunkt,
            "betrag": betrag,
            "hash": "",
        }
    )
    eintrag = eintrag.model_copy(update={"hash": eintrag_hash(eintrag)})
    speichere_uebermittlung(session, eintrag)
    return eintrag


def pruefe_protokoll(
    eintraege: list[Uebermittlung], archiv: BelegArchiv | None = None
) -> list[str]:
    """Befunde zu Lücken, gebrochener Verkettung, veränderten Einträgen und Dateien."""
    befunde = []
    vorher, erwartet = GENESIS, 1
    for u in sorted(eintraege, key=lambda e: e.nr):
        if u.nr > erwartet:
            luecke = f"{erwartet} bis {u.nr - 1}" if u.nr - 1 > erwartet else erwartet
            befunde.append(f"Eintrag {luecke} fehlt")
        if u.vorgaenger_hash != vorher:
            befunde.append(f"Eintrag {u.nr}: Verkettung zum Vorgänger gebrochen")
        if eintrag_hash(u) != u.hash:
            befunde.append(f"Eintrag {u.nr}: Inhalt verändert")
        if hashlib.sha256(u.datensatz.encode()).hexdigest() != u.datensatz_hash:
            befunde.append(f"Eintrag {u.nr}: Datensatz passt nicht zu seinem Hash")
        if archiv is not None:
            befunde += _archiv_befunde(u, archiv)
        vorher, erwartet = u.hash, u.nr + 1
    return befunde


def _archiv_befunde(u: Uebermittlung, archiv: BelegArchiv) -> list[str]:
    befunde = []
    for name, datei_hash in (
        ("Datensatz", u.datensatz_hash),
        ("Protokoll-PDF", u.protokoll_pdf_hash),
    ):
        if datei_hash is None:
            continue
        if not archiv.enthaelt(datei_hash):
            befunde.append(f"Eintrag {u.nr}: {name} fehlt im Archiv")
        elif hashlib.sha256(archiv.lese(datei_hash)).hexdigest() != datei_hash:
            befunde.append(f"Eintrag {u.nr}: {name} im Archiv verändert")
    return befunde
