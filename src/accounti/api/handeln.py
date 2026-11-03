"""Wer im Browser handelt: der angemeldete Benutzer — nie der Server-Prozess.

Jede schreibende Thread-Funktion einer Seite läuft in ``im_namen(a)``: die Person der
Sitzung (Passwort und zweiter Faktor) steht als **geprüfte** Person im Journal (ohne
„(ungeprüft)“, wie die Freigaben aus Baustein 10a). Zusätzlich übergibt die Seite
dieselbe Person ausdrücklich an jede Fachfunktion (``von=``, ``person=``) — die
Storno-Funktionen setzen einen inneren Kontext mit genau dieser Person.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from accounti.api.sitzung import Angemeldet
from accounti.pruefung.person import geprueft_als


@contextmanager
def im_namen(a: Angemeldet) -> Iterator[str]:
    with geprueft_als(a.benutzer.name):
        yield a.benutzer.name
