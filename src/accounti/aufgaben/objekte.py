"""Bezugsobjekte: beschreiben und aus einer Kurzangabe auflösen.

Eine Aufgabe zeigt auf ``Objekt(typ, id)``. Für die Typen, die es schon gibt, steht
hier, wie man sie findet (Anfang der ID, Personenkonto, IBAN) und wie man sie in
einer Zeile beschreibt. Andere Bausteine tragen eigene Typen mit
``registriere_objekttyp`` in ihrem Modul ``aufgaben_anbindung`` ein; unbekannte
Typen (z.B. Fristen ohne eigene Tabelle) funktionieren trotzdem — sie werden nur
nicht aufgelöst und roh angezeigt.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.anzeige import betrag_de, datum_de
from accounti.aufgaben.anbindung import lade_anbindungen
from accounti.aufgaben.fehler import AufgabenError
from accounti.db import Base
from accounti.db.repo_aufgaben import ids_mit_praefix
from accounti.db.repository import (
    finde_buchung,
    lade_bankkonto,
    lade_beleg,
    lade_einen_posten,
    lade_kontakt,
    lade_transaktion,
)
from accounti.db.tabellen import (
    BelegRow,
    BuchungssatzRow,
    OffenerPostenRow,
    TransaktionRow,
)
from accounti.models.aufgaben import Objekt

Beschreiber = Callable[[Session, str], "str | None"]
Finder = Callable[[Session, str], list[str]]


@dataclass(frozen=True)
class Objekttyp:
    typ: str
    bezeichnung: str
    beschreibe: Beschreiber  # None, wenn es das Objekt nicht (mehr) gibt
    finde: Finder  # vollständige IDs zu einer Kurzangabe


OBJEKTTYPEN: dict[str, Objekttyp] = {}


def registriere_objekttyp(
    typ: str, bezeichnung: str, *, beschreibe: Beschreiber, finde: Finder
) -> None:
    Objekt(typ, "probe")  # prüft den Bezeichner
    OBJEKTTYPEN[typ] = Objekttyp(typ, bezeichnung, beschreibe, finde)


def beschreibe(session: Session, objekt: Objekt) -> str:
    """Eine Zeile zum Objekt; unbekannte Typen als ``typ:id``."""
    lade_anbindungen()  # Objekttypen anderer Bausteine
    eintrag = OBJEKTTYPEN.get(objekt.typ)
    if eintrag is None:
        return str(objekt)
    try:
        text = eintrag.beschreibe(session, objekt.id)
    except ValueError:
        text = None
    return text if text is not None else f"{objekt} (nicht gefunden)"


def loese_auf(session: Session, typ: str, schluessel: str) -> Objekt:
    """Kurzangabe (Anfang der ID, Personenkonto, IBAN …) → vollständiges Objekt."""
    lade_anbindungen()
    eintrag = OBJEKTTYPEN.get(typ)
    if eintrag is None:
        try:
            return Objekt(typ, schluessel)
        except ValueError as fehler:  # ungültiger Typ oder leere ID
            raise AufgabenError(str(fehler)) from fehler
    try:
        treffer = eintrag.finde(session, schluessel)
    except ValueError as fehler:
        raise AufgabenError(str(fehler)) from fehler
    if not treffer:
        msg = f"Kein Objekt vom Typ {eintrag.bezeichnung} zu '{schluessel}' gefunden."
        raise AufgabenError(msg)
    if len(treffer) > 1:
        msg = f"'{schluessel}' ist mehrdeutig ({eintrag.bezeichnung}) — länger angeben."
        raise AufgabenError(msg)
    return Objekt(typ, treffer[0])


# ---------------------------------------------------------------------------
# Eingebaute Typen
# ---------------------------------------------------------------------------


def _praefix(row_klasse: type[Base]) -> Finder:
    return lambda session, schluessel: ids_mit_praefix(session, row_klasse, schluessel)


def _buchung(session: Session, ident: str) -> str | None:
    b = finde_buchung(session, ident)
    confidence = f"{b.confidence:.2f}".replace(".", ",")
    return (
        f"Buchung {datum_de(b.datum)} {b.soll_konto} an {b.haben_konto} "
        f"{betrag_de(b.betrag_netto)} € netto · {b.buchungstext} · "
        f"{b.status.value} · Confidence {confidence}"
    )


def _beleg(session: Session, ident: str) -> str | None:
    b = lade_beleg(session, ident)
    if b is None:
        return None
    wer = " ".join(filter(None, [b.lieferant_name, b.belegnummer]))
    teile = [f"Beleg {b.dateiname}", b.belegart.value]
    if wer:
        teile.append(wer)
    if b.belegdatum:
        teile.append(datum_de(b.belegdatum))
    if b.brutto is not None:
        teile.append(f"{betrag_de(b.brutto)} {b.waehrung}")
    teile.append(b.status.value)
    return " · ".join(teile)


def _transaktion(session: Session, ident: str) -> str | None:
    t = lade_transaktion(session, ident)
    if t is None:
        return None
    wer = " · ".join(filter(None, [t.gegenkonto_name, t.verwendungszweck[:50]]))
    return f"Umsatz {datum_de(t.datum)} {betrag_de(t.betrag)} € · {wer}"


def _posten(session: Session, ident: str) -> str | None:
    try:
        p = lade_einen_posten(session, UUID(ident))
    except ValueError:
        return None
    return (
        f"Offener Posten {p.belegnummer or '—'} · {p.richtung.value} · "
        f"Rest {betrag_de(p.restbetrag)} € · fällig {datum_de(p.faellig_am)}"
    )


def _kontakt(session: Session, ident: str) -> str | None:
    k = lade_kontakt(session, ident)
    konten = ", ".join(filter(None, [k.kreditor_konto, k.debitor_konto]))
    return (
        f"Kontakt {k.name}"
        + (f" ({konten})" if konten else "")
        + (f" · {k.status.value}")
    )


def _bankkonto(session: Session, ident: str) -> str | None:
    k = lade_bankkonto(session, ident)
    return f"Bankkonto {k.bezeichnung} {k.iban} · {k.zustand.value}"


registriere_objekttyp(
    "buchung",
    "Buchung",
    beschreibe=_buchung,
    finde=_praefix(BuchungssatzRow),
)
registriere_objekttyp("beleg", "Beleg", beschreibe=_beleg, finde=_praefix(BelegRow))
registriere_objekttyp(
    "transaktion", "Umsatz", beschreibe=_transaktion, finde=_praefix(TransaktionRow)
)
registriere_objekttyp(
    "offener_posten",
    "offener Posten",
    beschreibe=_posten,
    finde=_praefix(OffenerPostenRow),
)
registriere_objekttyp(
    "kontakt",
    "Kontakt",
    beschreibe=_kontakt,
    finde=lambda s, schluessel: [str(lade_kontakt(s, schluessel).id)],
)
registriere_objekttyp(
    "bankkonto",
    "Bankkonto",
    beschreibe=_bankkonto,
    finde=lambda s, schluessel: [str(lade_bankkonto(s, schluessel).id)],
)
