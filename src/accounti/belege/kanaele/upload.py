"""Upload — einzelne Dateien von der Kommandozeile (später auch aus der Web-UI)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from accounti.belege.kanaele import BelegKanal, RohBeleg, registriere


@registriere
class UploadKanal(BelegKanal):
    """Liefert genau die übergebenen Dateien und lässt sie, wo sie sind."""

    name = "upload"
    beschreibung = "Einzelne Dateien per CLI (accounti belege import)"

    def __init__(self, dateien: Iterable[str | Path]) -> None:
        self.dateien = [Path(d) for d in dateien]

    def abholen(self) -> Iterator[RohBeleg]:
        for pfad in self.dateien:
            yield RohBeleg(
                dateiname=pfad.name,
                inhalt=pfad.read_bytes(),
                kanal=self.name,
                herkunft=str(pfad.resolve()),
            )
