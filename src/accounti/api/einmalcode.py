"""Frischer zweiter Faktor für eine einzelne Freigabe im Browser.

Zahlungsläufe und USt-VA (Baustein 10a) sowie Storno und Korrektur freigegebener
Buchungen (``/buchungen/{id}``, Baustein 10b) verlangen zusätzlich zur Sitzung einen
Einmalcode (TOTP oder Wiederherstellungscode, mit Schutz vor Wiederverwendung) —
abschaltbar mit ``auth.einmalcode_bestaetigung: false``. Fehlversuche zählen wie bei
der Anmeldung.
"""

from __future__ import annotations

from fastapi import HTTPException

from accounti.api.dienste import Dienste
from accounti.api.sitzung import Angemeldet
from accounti.auth.dienst import pruefe_zweiten_faktor
from accounti.auth.fehler import AnmeldungError, AuthError
from accounti.bank.tresor import TresorError
from accounti.db.repo_auth import lade_benutzer_id
from accounti.i18n import Text


def bestaetige_einmalcode(dienste: Dienste, a: Angemeldet, einmalcode: str) -> None:
    """Frischer zweiter Faktor für genau diese Freigabe (zählt Fehlversuche)."""
    if not dienste.auth.einmalcode_bestaetigung:
        return
    with dienste.system() as s:
        b = lade_benutzer_id(s, a.benutzer.id)
        if b is None:
            raise HTTPException(403, Text("Benutzer unbekannt"))
        try:
            pruefe_zweiten_faktor(
                s,
                b,
                einmalcode,
                dienste.schluessel(),
                dienste.auth,
                dienste.uhr(),
                quelle="web",
            )
        except AnmeldungError as fehler:
            raise HTTPException(
                403, Text("Einmalcode falsch oder schon benutzt")
            ) from fehler
        except (AuthError, TresorError) as fehler:
            raise HTTPException(403, str(fehler)) from fehler
        s.commit()
