"""Datei-Provider — Kontoauszüge aus einem Ordner.

Fallback und Notausgang: accounti bleibt ohne jede Bankverbindung voll nutzbar.
CSV-Dateien laufen über die Profile aus Baustein 1 (Einstellung ``format``), MT940
und CAMT werden am Inhalt erkannt. Auszüge eines anderen Kontos werden übersprungen.
Jeder Abruf liest alle Dateien des Ordners; was schon da ist, fängt der
Dublettenschutz ab — er zählt gleiche Umsätze je Auszug (CSV: je Datei), sodass
derselbe Umsatz aus Tages- und Monatsauszug einer bleibt. Eine Datei, die zweimal im
Ordner liegt (erneuter Download), und ein Auszug, der in zwei Dateien steckt, zählen
nur einmal.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from accounti.bank.provider import Abruf, BankProvider, ProviderError, registriere
from accounti.importers.kontoauszug import (
    Auszug,
    erkenne_auszugsformat,
    lies_kontoauszug,
)
from accounti.importers.profil import waehle_importer
from accounti.models import Bankkonto

# Endungen, unter denen Banken MT940 und CAMT ausliefern — erkannt wird am Inhalt
AUSZUG_ENDUNGEN = frozenset({".sta", ".mt940", ".940", ".txt", ".xml", ".camt"})


def _kennung(auszug: Auszug) -> tuple[object, ...]:
    """Inhalt eines Auszugs — derselbe Auszug aus zwei Dateien zählt einmal."""
    return (
        auszug.konto,
        auszug.anfangssaldo,
        auszug.endsaldo,
        auszug.endsaldo_datum,
        tuple(
            (
                t.datum,
                t.betrag,
                t.verwendungszweck,
                t.gegenkonto_name,
                t.gegenkonto_iban,
                t.quelle_referenz,
            )
            for t in auszug.umsaetze
        ),
    )


def _lies_auszuege(
    daten: bytes, konto: Bankkonto, abruf: Abruf, gelesen: set[tuple[object, ...]]
) -> None:
    if erkenne_auszugsformat(daten) is None:
        return  # Notiz, Rechnung o.ä. — kein Kontoauszug
    for auszug in lies_kontoauszug(daten):
        kennung = _kennung(auszug)
        if not auszug.gehoert_zu(konto.iban) or kennung in gelesen:
            continue
        gelesen.add(kennung)
        abruf.fuege_hinzu(auszug.umsaetze, auszug.fortsetzung)
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
        dateien: set[str] = set()  # Inhalt — eine Kopie derselben Datei zählt einmal
        auszuege: set[tuple[object, ...]] = set()
        for datei in sorted(ordner.iterdir()):
            endung = datei.suffix.lower()
            if not datei.is_file() or endung not in {".csv", *AUSZUG_ENDUNGEN}:
                continue
            try:
                daten = datei.read_bytes()
                inhalt = hashlib.sha256(daten).hexdigest()
                if inhalt in dateien:
                    continue
                dateien.add(inhalt)
                if endung == ".csv":
                    importer = waehle_importer(datei, format)
                    abruf.fuege_hinzu(importer.importiere(datei))
                else:
                    _lies_auszuege(daten, konto, abruf, auszuege)
            except (ValueError, KeyError, UnicodeDecodeError) as fehler:
                raise ProviderError(f"{datei.name}: {fehler}") from fehler
        return abruf
