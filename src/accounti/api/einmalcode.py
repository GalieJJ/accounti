"""Frischer zweiter Faktor für eine einzelne Freigabe im Browser.

Zahlungsläufe und USt-VA (Baustein 10a) sowie Storno und Korrektur freigegebener
Buchungen (``/buchungen/{id}``, Baustein 10b) verlangen zusätzlich zur Sitzung einen
Einmalcode (TOTP oder Wiederherstellungscode, mit Schutz vor Wiederverwendung) —
abschaltbar mit ``auth.einmalcode_bestaetigung: false``. Fehlversuche zählen wie bei
der Anmeldung.
"""

from __future__ import annotations

import threading
from urllib.parse import urlencode

from fastapi import HTTPException

from accounti.api.dienste import Dienste
from accounti.api.sitzung import Angemeldet
from accounti.auth.dienst import pruefe_zweiten_faktor
from accounti.auth.fehler import AnmeldungError, AuthError
from accounti.bank.tresor import TresorError
from accounti.db.repo_auth import lade_benutzer_id
from accounti.i18n import Text

_SPERREN: dict[str, threading.Lock] = {}
_SPERREN_ZUGRIFF = threading.Lock()


def freigabesperre(datenbank: str) -> threading.Lock:
    """Aktionen mit Einmalcode einer Gesellschaft schließen nacheinander ab (Stand
    prüfen, Einmalcode, Lauf) — im Server-Prozess (``accounti serve`` startet einen).
    Ein Doppelklick wartet hier und bekommt 409 ohne Fehlversuch (gw-storno N2; für
    Zahlungslauf und USt-VA Gesamttest 10b-1, Runde 3)."""
    with _SPERREN_ZUGRIFF:
        return _SPERREN.setdefault(datenbank, threading.Lock())


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


def code_variante(code: str | None) -> str:
    """``?code=wiederherstellung`` schaltet die Codefelder einer Seite auf den
    Wiederherstellungscode (Text); jeder andere Wert wird ignoriert (A109)."""
    return "wiederherstellung" if code == "wiederherstellung" else "app"


def code_wechsel(pfad: str, variante: str, **abfrage: str) -> str:
    """Link „Wiederherstellungscode verwenden“ bzw. zurück „Code aus der App
    verwenden“ auf dieselbe Seite (ohne Skript); ``abfrage`` (``weiter``) bleibt."""
    if variante == "app":
        abfrage = {**abfrage, "code": "wiederherstellung"}
    return f"{pfad}?{urlencode(abfrage)}" if abfrage else pfad
