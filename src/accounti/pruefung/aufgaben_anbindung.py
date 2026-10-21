"""Anbindung an Baustein 8: Baustein 7 übernimmt den Prüflauf ``beleg_fehlt``.

Dieses Modul lädt ``accounti.aufgaben`` von selbst (``lade_anbindungen``). Der
eingebaute Lauf bleibt der Kern; die Regel ``umsatz_ohne_beleg`` legt Schwellen und
begründete Belegfreiheit darüber (``nachforderung.BelegFehltNachRegel``). Ohne
Abschnitt ``pruefung`` verhält sich der Lauf wie der eingebaute.
"""

from __future__ import annotations

from accounti.aufgaben import PRUEFLAEUFE, registriere_prueflauf
from accounti.pruefung.nachforderung import ART, BelegFehltNachRegel

_eingebaut = PRUEFLAEUFE[ART]
if not isinstance(_eingebaut, BelegFehltNachRegel):
    registriere_prueflauf(BelegFehltNachRegel(_eingebaut))
