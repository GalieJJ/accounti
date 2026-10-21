"""Nachforderung (Spec 4.2): aus dem Befund „Umsatz ohne Beleg“ wird eine Aufgabe.

Die Aufgabe kommt aus Baustein 8 — mit Umsatz, Betrag, Gegenpartei und
Zuständigkeit, Erinnerungen in konfigurierbaren Abständen und Eskalation. Weil eine
Aufgabenart genau einem Prüflauf gehört, ersetzt Baustein 7 den eingebauten Lauf
``beleg_fehlt`` unter demselben Namen (``aufgaben_anbindung``): Er übernimmt die
Anlässe des eingebauten Laufs und legt die Regel ``umsatz_ohne_beleg`` darüber —
Schwellen und ``belegfrei``-Muster aus dem Abschnitt ``pruefung``. Trifft der Beleg
ein und greift der Abgleich, entfällt der Anlass, und der nächste Lauf schließt die
Aufgabe als ``hinfaellig``: Sie verstummt.

Die Anfrage beim Lieferanten ist ein Entwurf aus der Vorlage
(``pruefung.nachforderung``). Verschickt wird sie nur, wenn ein Mensch es für diese
eine Anfrage verlangt (``accounti nachfordern anfrage TX --senden``) — kein Lauf
schreibt von selbst an Dritte.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.anzeige import betrag_de, datum_de
from accounti.aufgaben import (
    AufgabenEinstellungen,
    AufgabenError,
    Objekt,
    Pruefergebnis,
    Prueflauf,
    aufgaben_zu,
    kommentiere,
)
from accounti.db.repository import lade_buchungen, lade_kontakte, lade_transaktionen
from accounti.erechnung.versand import Versandweg
from accounti.konfiguration import KonfigurationError
from accounti.kontakte.erkennung import finde_kontakt
from accounti.models import Transaktion
from accounti.pruefung.einstellungen import PruefEinstellungen, lade_pruefung
from accounti.pruefung.journal import schreibe
from accounti.pruefung.regeln.vollstaendigkeit import UmsatzOhneBeleg

ART = "beleg_fehlt"
REGEL = UmsatzOhneBeleg()

_EINSTELLUNGEN: ContextVar[PruefEinstellungen | None] = ContextVar(
    "accounti_pruefeinstellungen", default=None
)


class NachforderungError(ValueError):
    """Die Anfrage lässt sich so nicht bilden oder senden."""


@contextmanager
def mit_pruefeinstellungen(e: PruefEinstellungen) -> Iterator[None]:
    """Abschnitt ``pruefung`` für den Prüflauf (sonst ``config/accounti.yaml``)."""
    token = _EINSTELLUNGEN.set(e)
    try:
        yield
    finally:
        _EINSTELLUNGEN.reset(token)


def _pruefeinstellungen() -> PruefEinstellungen:
    e = _EINSTELLUNGEN.get()
    if e is not None:
        return e
    try:
        return lade_pruefung()
    except KonfigurationError as fehler:
        raise AufgabenError(str(fehler)) from fehler


class BelegFehltNachRegel:
    """``beleg_fehlt`` mit den Schwellen und Ausnahmen der Prüfregel."""

    name = ART
    beschreibung = "Umsätze ohne Beleg (Prüfregel umsatz_ohne_beleg, Baustein 7)"
    grund_entfallen = "Umsatz hat einen Beleg oder fällt nicht mehr unter die Prüfung"

    def __init__(self, eingebaut: Prueflauf) -> None:
        self.eingebaut = eingebaut

    def finde(
        self,
        session: Session,
        einstellungen: AufgabenEinstellungen,
        stichtag: date,
        zeitraum: str | None,
    ) -> Pruefergebnis:
        ergebnis = self.eingebaut.finde(session, einstellungen, stichtag, zeitraum)
        pe = _pruefeinstellungen()
        try:
            parameter = REGEL.Parameter.model_validate(pe.regeln.get(REGEL.name, {}))
        except ValueError as fehler:
            raise AufgabenError(f"pruefung.regeln.{REGEL.name}: {fehler}") from fehler
        schwere = pe.schwere.get(REGEL.name, REGEL.schwere)
        umsaetze = {str(t.id): t for t in lade_transaktionen(session)}
        mit_beleg = {
            str(b.transaktion_id)
            for b in lade_buchungen(session)
            if b.transaktion_id and b.beleg_id
        }
        anlaesse = []
        for a in ergebnis.anlaesse:
            tx = umsaetze.get(a.objekt.id)
            if tx is None:  # pragma: no cover — der eingebaute Lauf kennt ihn
                continue
            regel = pe.belegfrei_nach_regel(tx.verwendungszweck, tx.gegenkonto_name)
            if regel is not None:
                ergebnis.gruende[a.objekt] = (
                    f"belegfrei nach Regel {regel.name}: {regel.begruendung}"
                )
                continue
            if a.objekt.id in mit_beleg:
                ergebnis.gruende[a.objekt] = "Beleg über die Buchung zugeordnet"
                continue
            if abs(tx.betrag) < parameter.ab_betrag:
                ergebnis.gruende[a.objekt] = (
                    f"unter der Schwelle von {betrag_de(parameter.ab_betrag)} €"
                )
                continue
            if (stichtag - tx.datum).days < parameter.nach_tagen:
                ergebnis.ausgenommen.add(a.objekt)  # noch zu jung: nicht schließen
                continue
            a.merkmale = {**a.merkmale, "befund": REGEL.name, "schwere": schwere.value}
            anlaesse.append(a)
        ergebnis.anlaesse = anlaesse
        return ergebnis


# ---------------------------------------------------------------------------
# Anfrage beim Lieferanten — Entwurf aus der Vorlage, Versand nur auf Befehl
# ---------------------------------------------------------------------------


@dataclass
class Anfrage:
    transaktion: Transaktion
    an: str | None
    betreff: str
    text: str


def finde_umsatz(session: Session, schluessel: str) -> Transaktion:
    treffer = [
        t
        for t in lade_transaktionen(session)
        if str(t.id).startswith(schluessel.lower())
    ]
    if len(treffer) != 1:
        grund = "nicht eindeutig" if treffer else "nicht gefunden"
        raise NachforderungError(f"Umsatz '{schluessel}' {grund}")
    return treffer[0]


def baue_anfrage(
    session: Session,
    schluessel: str,
    einstellungen: PruefEinstellungen,
    firma: str,
    antwort: str | None = None,
    an: str | None = None,
) -> Anfrage:
    """Entwurf der Anfrage — Empfänger aus ``an`` oder der E-Mail des Kontakts."""
    tx = finde_umsatz(session, schluessel)
    if an is None:
        kontakt, _ = finde_kontakt(
            lade_kontakte(session), iban=tx.gegenkonto_iban, name=tx.gegenkonto_name
        )
        an = kontakt.email if kontakt is not None else None
    vorlage = einstellungen.nachforderung
    werte = {
        "datum": datum_de(tx.datum),
        "betrag": betrag_de(abs(tx.betrag)),
        "verwendungszweck": tx.verwendungszweck,
        "gegenpartei": tx.gegenkonto_name or "",
        "firma": firma,
        "antwort": vorlage.antwort_an or antwort or "die Absenderadresse dieser E-Mail",
    }
    try:
        return Anfrage(
            tx, an, vorlage.betreff.format(**werte), vorlage.text.format(**werte)
        )
    except (KeyError, IndexError, ValueError) as fehler:
        msg = (
            f"Vorlage pruefung.nachforderung: Platzhalter {fehler} unbekannt (möglich: "
            "{datum} {betrag} {verwendungszweck} {gegenpartei} {firma} {antwort})"
        )
        raise NachforderungError(msg) from fehler


def sende_anfrage(
    session: Session, anfrage: Anfrage, weg: Versandweg, absender: str, person: str
) -> EmailMessage:
    """Diese eine Anfrage verschicken; Kommentar an der Aufgabe, Eintrag im Journal."""
    if not anfrage.an:
        raise NachforderungError(
            "Kein Empfänger: beim Kontakt eine E-Mail hinterlegen oder --an angeben"
        )
    nachricht = EmailMessage()
    nachricht["From"] = absender
    nachricht["To"] = anfrage.an
    nachricht["Subject"] = anfrage.betreff
    nachricht.set_content(anfrage.text)
    weg.sende(nachricht)
    objekt = Objekt("transaktion", anfrage.transaktion.id)
    aufgabe = next((a for a in aufgaben_zu(session, objekt) if a.art == ART), None)
    kommentiere(
        session,
        f"Beleg angefordert bei {anfrage.an}: {anfrage.betreff}",
        person,
        aufgabe=aufgabe,
        objekt=None if aufgabe is not None else objekt,
    )
    schreibe(
        session,
        "beleg_angefordert",
        "transaktion",
        str(anfrage.transaktion.id),
        nachher={"an": anfrage.an, "betreff": anfrage.betreff},
        person=person,
    )
    return nachricht


__all__ = [
    "ART",
    "Anfrage",
    "BelegFehltNachRegel",
    "NachforderungError",
    "UUID",
    "baue_anfrage",
    "mit_pruefeinstellungen",
    "sende_anfrage",
]
