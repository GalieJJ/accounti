"""Einstellungen: Datei und Datenbank (Baustein 10c, Paket P4).

Einstellungen leben ab der ersten Änderung in der Datenbank der Gesellschaft — nur
anfügend versioniert (``db/tabellen_einstellungen.py``). ``leser`` liest den wirksamen
Abschnitt (Vorrang: Umgebung, Festlegung in der Datei, Datenbank, Datei, Standard).
"""

from __future__ import annotations

from accounti.einstellungen.leser import normalform

__all__ = ["normalform"]
