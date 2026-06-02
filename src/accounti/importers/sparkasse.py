"""Sparkasse-CSV-Importer (CSV-CAMT-Format).

Dünner Wrapper um den ProfilImporter mit dem eingebauten Sparkasse-Profil.
Bleibt für direkten Import (``from accounti.importers.sparkasse import ...``)
erhalten; die Registrierung erfolgt zentral in ``profil.py``.
"""

from __future__ import annotations

from accounti.importers.profil import EINGEBAUTE_PROFILE, ProfilImporter


class SparkasseImporter(ProfilImporter):
    def __init__(self) -> None:
        super().__init__(EINGEBAUTE_PROFILE["sparkasse"])
