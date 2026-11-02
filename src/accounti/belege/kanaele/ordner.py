"""Watch-Ordner — Datei rein, Beleg rein.

Mit Dateiprüfung (``belegkanaele``: Typ am Inhalt, Größe) wie E-Mail und Webhook: Eine
abgelehnte Datei wandert nach ``abgelehnt/`` und wird als Hinweis gemeldet — nie still
verworfen und nie im Belegarchiv.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from accounti.belege.kanaele import BelegKanal, RohBeleg, registriere
from accounti.belege.kanaele.pruefung import DateiAbgelehntError, Dateipruefung

VERARBEITET = "verarbeitet"
ABGELEHNT = "abgelehnt"


@registriere
class OrdnerKanal(BelegKanal):
    """Liest alle Dateien eines Ordners; verarbeitete wandern nach ``verarbeitet/``."""

    name = "ordner"
    beschreibung = "Überwachter Ordner; verarbeitete Dateien landen in verarbeitet/"

    def __init__(
        self, ordner: str | Path, pruefung: Dateipruefung | None = None
    ) -> None:
        self.ordner = Path(ordner)
        self.pruefung = pruefung
        self.hinweise: list[str] = []

    def abholen(self) -> Iterator[RohBeleg]:
        for pfad in sorted(self.ordner.iterdir()):
            if pfad.name.startswith(".") or not pfad.is_file():
                continue
            inhalt = pfad.read_bytes()
            if self.pruefung is not None:
                try:
                    self.pruefung.pruefe(pfad.name, inhalt)
                except DateiAbgelehntError as fehler:
                    self._verschiebe(pfad, ABGELEHNT)
                    self.hinweise.append(f"{fehler} — liegt jetzt in {ABGELEHNT}/")
                    continue
            yield RohBeleg(
                dateiname=pfad.name,
                inhalt=inhalt,
                kanal=self.name,
                herkunft=str(pfad),
            )

    def bestaetige(self, roh: RohBeleg) -> None:
        self._verschiebe(Path(roh.herkunft), VERARBEITET)

    def _verschiebe(self, quelle: Path, unterordner: str) -> None:
        ziel_ordner = self.ordner / unterordner
        ziel_ordner.mkdir(exist_ok=True)
        ziel = ziel_ordner / quelle.name
        zaehler = 1
        while ziel.exists():
            ziel = ziel_ordner / f"{quelle.stem}-{zaehler}{quelle.suffix}"
            zaehler += 1
        quelle.rename(ziel)
