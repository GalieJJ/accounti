"""Datei-Provider — Kontoauszüge aus einem Ordner.

Fallback und Notausgang: accounti bleibt ohne jede Bankverbindung voll nutzbar.
CSV-Dateien laufen über die Profile aus Baustein 1 (Einstellung ``format``), MT940
und CAMT werden am Inhalt erkannt. Auszüge eines anderen Kontos werden übersprungen.
Jeder Abruf liest alle Dateien des Ordners; was schon da ist, fängt der
Dublettenschutz ab.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from accounti.bank.provider import Abruf, BankProvider, ProviderError, registriere
from accounti.importers.kontoauszug import erkenne_auszugsformat, lies_kontoauszug
from accounti.importers.profil import waehle_importer
from accounti.models import Bankkonto

# Endungen, unter denen Banken MT940 und CAMT ausliefern — erkannt wird am Inhalt
AUSZUG_ENDUNGEN = frozenset({".sta", ".mt940", ".940", ".txt", ".xml", ".camt"})


def _lies_auszuege(datei: Path, konto: Bankkonto, abruf: Abruf) -> None:
    daten = datei.read_bytes()
    if erkenne_auszugsformat(daten) is None:
        return  # Notiz, Rechnung o.ä. — kein Kontoauszug
    for auszug in lies_kontoauszug(daten):
        if not auszug.gehoert_zu(konto.iban):
            continue
        abruf.transaktionen.extend(auszug.umsaetze)
        datum = auszug.endsaldo_datum
        neuer = abruf.saldo_datum is None or (datum and datum >= abruf.saldo_datum)
        if auszug.endsaldo is not None and datum is not None and neuer:
            abruf.saldo, abruf.saldo_datum = auszug.endsaldo, datum


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
        format = konto.einstellungen.get("format") or "auto"  # gilt für CSV
        abruf = Abruf()
        for datei in sorted(ordner.iterdir()):
            endung = datei.suffix.lower()
            try:
                if endung == ".csv":
                    importer = waehle_importer(datei, format)
                    abruf.transaktionen.extend(importer.importiere(datei))
                elif endung in AUSZUG_ENDUNGEN and datei.is_file():
                    _lies_auszuege(datei, konto, abruf)
            except (ValueError, KeyError, UnicodeDecodeError) as fehler:
                raise ProviderError(f"{datei.name}: {fehler}") from fehler
        return abruf
