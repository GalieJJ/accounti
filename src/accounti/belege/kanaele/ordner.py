"""Watch-Ordner — Datei rein, Beleg rein."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from accounti.belege.kanaele import BelegKanal, RohBeleg, registriere

VERARBEITET = "verarbeitet"


@registriere
class OrdnerKanal(BelegKanal):
    """Liest alle Dateien eines Ordners; verarbeitete wandern nach ``verarbeitet/``."""

    name = "ordner"
    beschreibung = "Überwachter Ordner; verarbeitete Dateien landen in verarbeitet/"

    def __init__(self, ordner: str | Path) -> None:
        self.ordner = Path(ordner)

    def abholen(self) -> Iterator[RohBeleg]:
        for pfad in sorted(self.ordner.iterdir()):
            if pfad.name.startswith(".") or not pfad.is_file():
                continue
            yield RohBeleg(
                dateiname=pfad.name,
                inhalt=pfad.read_bytes(),
                kanal=self.name,
                herkunft=str(pfad),
            )

    def bestaetige(self, roh: RohBeleg) -> None:
        quelle = Path(roh.herkunft)
        ziel_ordner = self.ordner / VERARBEITET
        ziel_ordner.mkdir(exist_ok=True)
        ziel = ziel_ordner / quelle.name
        zaehler = 1
        while ziel.exists():
            ziel = ziel_ordner / f"{quelle.stem}-{zaehler}{quelle.suffix}"
            zaehler += 1
        quelle.rename(ziel)
