"""Formale Prüfung mit dem KoSIT-Prüftool (Validator + XRechnung-Konfiguration).

Das Prüftool ist eine Java-Anwendung der Koordinierungsstelle für IT-Standards und prüft
gegen XML-Schema und Schematron der XRechnung — das ist der Maßstab, an dem Empfänger
eine E-Rechnung messen. Installiert wird es mit ``scripts/kosit_installieren.sh``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path, PurePath

REP = "{http://www.xoev.de/de/validator/varl/1}"


class KositNichtVerfuegbarError(RuntimeError):
    """Java oder das Prüftool fehlt."""


@dataclass(frozen=True)
class KositMeldung:
    stufe: str  # error, warning, information
    code: str
    text: str

    def __str__(self) -> str:
        return f"{self.code}: {self.text}"


@dataclass
class KositErgebnis:
    akzeptiert: bool
    meldungen: list[KositMeldung] = field(default_factory=list)

    @property
    def fehler(self) -> list[KositMeldung]:
        return [m for m in self.meldungen if m.stufe in ("error", "fatal")]


def werte_bericht_aus(bericht: bytes) -> KositErgebnis:
    wurzel = ET.fromstring(bericht)
    akzeptiert = wurzel.find(f"{REP}assessment/{REP}accept") is not None
    meldungen = [
        KositMeldung(
            stufe=m.get("level", "error"),
            code=m.get("code", ""),
            text=" ".join((m.text or "").split()),
        )
        for m in wurzel.iter(f"{REP}message")
    ]
    return KositErgebnis(akzeptiert=akzeptiert, meldungen=meldungen)


def _standard_verzeichnis() -> Path:
    return Path(os.environ.get("ACCOUNTI_KOSIT_DIR", ".kosit"))


class KositPruefer:
    def __init__(
        self,
        verzeichnis: str | Path | None = None,
        java: str | None = None,
        timeout: int = 300,
    ) -> None:
        self.verzeichnis = Path(verzeichnis) if verzeichnis else _standard_verzeichnis()
        self.java = java or os.environ.get("ACCOUNTI_JAVA", "java")
        self.timeout = timeout

    @property
    def _jar(self) -> Path | None:
        treffer = sorted(self.verzeichnis.glob("validator-*-standalone.jar"))
        return treffer[-1] if treffer else None

    @property
    def _konfiguration(self) -> Path:
        return self.verzeichnis / "xrechnung"

    def verfuegbar(self) -> bool:
        return (
            self._jar is not None
            and (self._konfiguration / "scenarios.xml").is_file()
            and shutil.which(self.java) is not None
        )

    def pruefe(self, xml: bytes, name: str = "rechnung.xml") -> KositErgebnis:
        return self.pruefe_mehrere({name: xml})[name]

    def pruefe_mehrere(self, dateien: dict[str, bytes]) -> dict[str, KositErgebnis]:
        """Prüft mehrere Dateien in einem Lauf (die JVM startet nur einmal)."""
        jar = self._jar
        if not self.verfuegbar() or jar is None:
            msg = (
                f"KoSIT-Prüftool nicht gefunden in {self.verzeichnis} "
                "(oder Java fehlt) — Installation: scripts/kosit_installieren.sh"
            )
            raise KositNichtVerfuegbarError(msg)
        with tempfile.TemporaryDirectory(prefix="accounti-kosit-") as tmp:
            eingang, ausgang = Path(tmp, "eingang"), Path(tmp, "bericht")
            eingang.mkdir()
            ausgang.mkdir()
            pfade = {}
            for name, inhalt in dateien.items():
                pfad = eingang / PurePath(name).name
                pfad.write_bytes(inhalt)
                pfade[name] = pfad
            try:
                lauf = subprocess.run(
                    [
                        self.java,
                        "-jar",
                        str(jar),
                        "-s",
                        str(self._konfiguration / "scenarios.xml"),
                        "-r",
                        str(self._konfiguration),
                        "-o",
                        str(ausgang),
                        *map(str, pfade.values()),
                    ],
                    capture_output=True,
                    timeout=self.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as fehler:
                msg = f"KoSIT-Prüftool nach {self.timeout}s abgebrochen"
                raise RuntimeError(msg) from fehler
            ergebnisse = {}
            for name, pfad in pfade.items():
                bericht = ausgang / f"{pfad.stem}-report.xml"
                if not bericht.is_file():
                    ausgabe = lauf.stderr.decode("utf-8", "replace")[-500:]
                    msg = f"KoSIT-Prüftool ohne Bericht für {name}: {ausgabe}"
                    raise RuntimeError(msg)
                ergebnisse[name] = werte_bericht_aus(bericht.read_bytes())
            return ergebnisse
