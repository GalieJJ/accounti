"""Aufgaben & Rückfragen (Baustein 8) — die Schnittstelle für andere Bausteine.

Alles, was ein Mensch entscheiden muss, landet als Aufgabe an einem Ort: mit Bezug
zu einem Objekt, Zuständigkeit, Fälligkeit und Verlauf. Andere Bausteine nutzen nur,
was hier exportiert wird::

    from accounti.aufgaben import Objekt, melde_aufgabe, schliesse_wenn_erledigt

    melde_aufgabe(session, "beleg_fehlt", Objekt("transaktion", tx.id),
                  titel="Beleg fehlt: …", erzeugt_von="pruefung:beleg_fehlt")
    schliesse_wenn_erledigt(session, "beleg_fehlt", Objekt("transaktion", tx.id),
                            grund="Beleg zugeordnet")

Die Funktionen arbeiten in der Sitzung des Aufrufers und committen nicht.
"""

from __future__ import annotations

from accounti.aufgaben.benachrichtigung import (
    KANAELE,
    Tagesuebersicht,
    baue_kanaele,
    stelle_zusammen,
    versende_tagesuebersichten,
)
from accounti.aufgaben.einstellungen import (
    AufgabenEinstellungen,
    lade_aufgaben_einstellungen,
)
from accounti.aufgaben.erzeugung import (
    Abgleich,
    Anlass,
    Meldung,
    Rueckfrage,
    Vorgang,
    aufgaben_zu,
    erledige,
    gleiche_ab,
    halte_rueckfrage_fest,
    kommentare_zu,
    kommentiere,
    melde_aufgabe,
    schliesse_wenn_erledigt,
    setze_status,
    weise_zu,
)
from accounti.aufgaben.fehler import AufgabenError
from accounti.aufgaben.objekte import beschreibe, loese_auf, registriere_objekttyp
from accounti.aufgaben.prueflaeufe import (
    PRUEFLAEUFE,
    Laufergebnis,
    Pruefergebnis,
    Prueflauf,
    fuehre_prueflaeufe_aus,
    registriere_prueflauf,
)
from accounti.models.aufgaben import (
    Aufgabe,
    AufgabenStatus,
    Kommentar,
    KommentarArt,
    Objekt,
    Prioritaet,
)

__all__ = [
    "KANAELE",
    "PRUEFLAEUFE",
    "Abgleich",
    "Anlass",
    "Aufgabe",
    "AufgabenEinstellungen",
    "AufgabenError",
    "AufgabenStatus",
    "Kommentar",
    "KommentarArt",
    "Laufergebnis",
    "Meldung",
    "Objekt",
    "Prioritaet",
    "Pruefergebnis",
    "Prueflauf",
    "Rueckfrage",
    "Tagesuebersicht",
    "Vorgang",
    "aufgaben_zu",
    "baue_kanaele",
    "beschreibe",
    "erledige",
    "fuehre_prueflaeufe_aus",
    "gleiche_ab",
    "halte_rueckfrage_fest",
    "kommentare_zu",
    "kommentiere",
    "lade_aufgaben_einstellungen",
    "loese_auf",
    "melde_aufgabe",
    "registriere_objekttyp",
    "registriere_prueflauf",
    "schliesse_wenn_erledigt",
    "setze_status",
    "stelle_zusammen",
    "versende_tagesuebersichten",
    "weise_zu",
]
