"""Datei-Provider — Kontoauszüge aus einem Ordner, mit den CSV-Profilen aus Baustein 1.

Fallback und Notausgang: accounti bleibt ohne jede Bankverbindung voll nutzbar.
Jeder Abruf liest alle Dateien des Ordners; was schon da ist, fängt der
Dublettenschutz ab.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from accounti.bank.provider import Abruf, BankProvider, ProviderError, registriere
from accounti.importers.profil import waehle_importer
from accounti.models import Bankkonto


@registriere
class DateiProvider(BankProvider):
    name = "datei"
    felder = ("ordner", "format")

    def abrufen(
        self, konto: Bankkonto, zugang: dict[str, str], ab: date | None
    ) -> Abruf:
        ordner = Path(konto.einstellungen.get("ordner") or "")
        if not konto.einstellungen.get("ordner") or not ordner.is_dir():
            msg = f"Ordner für Kontoauszüge fehlt: {ordner} (Einstellung 'ordner')"
            raise ProviderError(msg)
        format = konto.einstellungen.get("format") or "auto"
        abruf = Abruf()
        for datei in sorted(ordner.iterdir()):
            if datei.suffix.lower() != ".csv":
                continue
            try:
                importer = waehle_importer(datei, format)
                abruf.transaktionen.extend(importer.importiere(datei))
            except (ValueError, KeyError, UnicodeDecodeError) as fehler:
                raise ProviderError(f"{datei.name}: {fehler}") from fehler
        return abruf
