"""Formale Prüfung eines ZUGFeRD-PDF mit Mustang (Java).

Mustang prüft beides, was ein ZUGFeRD-PDF ausmacht: PDF/A-3 über veraPDF und das
eingebettete XML (hier: XRechnung). Installiert wird es mit
``scripts/pruefwerkzeuge_installieren.sh``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path, PurePath

from accounti.erechnung.kosit import pruefwerkzeuge


class MustangNichtVerfuegbarError(RuntimeError):
    """Java oder Mustang fehlt."""


@dataclass
class MustangErgebnis:
    gueltig: bool
    pdfa_konform: bool | None = None
    xml_gueltig: bool | None = None
    profil: str | None = None
    meldungen: list[str] = field(default_factory=list)


def _status(element: ET.Element | None) -> bool | None:
    if element is None:
        return None
    summary = element.find("summary")
    return None if summary is None else summary.get("status") == "valid"


def werte_bericht_aus(ausgabe: str) -> MustangErgebnis:
    """Liest den XML-Bericht aus der Ausgabe von ``--action validate``."""
    start = ausgabe.find("<?xml")
    start = start if start >= 0 else ausgabe.find("<validation")
    if start < 0:
        msg = f"Mustang hat kein Prüfbericht geliefert: {ausgabe[-500:]}"
        raise RuntimeError(msg)
    wurzel = ET.fromstring(ausgabe[start:].strip().encode("utf-8"))
    pdf = wurzel.find("pdf")
    xml = wurzel.find("xml")
    pdfa = _status(pdf)
    if pdf is not None and pdf.text and "isCompliant=" in pdf.text:
        pdfa = "isCompliant=true" in pdf.text
    return MustangErgebnis(
        gueltig=_status(wurzel) is True,
        pdfa_konform=pdfa,
        xml_gueltig=_status(xml),
        profil=xml.findtext("info/profile") if xml is not None else None,
        meldungen=[" ".join((e.text or "").split()) for e in wurzel.iter("error")],
    )


class MustangPruefer:
    def __init__(
        self,
        verzeichnis: str | Path | None = None,
        java: str | None = None,
        timeout: int = 300,
    ) -> None:
        self.verzeichnis = (
            Path(verzeichnis) if verzeichnis else pruefwerkzeuge() / "mustang"
        )
        self.java = java or os.environ.get("ACCOUNTI_JAVA", "java")
        self.timeout = timeout

    @property
    def _jar(self) -> Path | None:
        treffer = sorted(self.verzeichnis.glob("Mustang-CLI-*.jar"))
        return treffer[-1] if treffer else None

    def verfuegbar(self) -> bool:
        return self._jar is not None and shutil.which(self.java) is not None

    def pruefe(self, pdf: bytes, name: str = "rechnung.pdf") -> MustangErgebnis:
        jar = self._jar
        if jar is None or not self.verfuegbar():
            msg = (
                f"Mustang nicht gefunden in {self.verzeichnis} (oder Java fehlt) — "
                "Installation: scripts/pruefwerkzeuge_installieren.sh"
            )
            raise MustangNichtVerfuegbarError(msg)
        with tempfile.TemporaryDirectory(prefix="accounti-mustang-") as tmp:
            datei = Path(tmp) / PurePath(name).name
            datei.write_bytes(pdf)
            try:
                lauf = subprocess.run(
                    [
                        self.java,
                        "-jar",
                        str(jar.resolve()),
                        "--action",
                        "validate",
                        "--source",
                        str(datei),
                        "--no-notices",
                    ],
                    capture_output=True,
                    timeout=self.timeout,
                    check=False,  # bei ungültigen Dateien endet Mustang mit Code ≠ 0
                    cwd=tmp,
                )
            except subprocess.TimeoutExpired as fehler:
                msg = f"Mustang nach {self.timeout}s abgebrochen"
                raise RuntimeError(msg) from fehler
        ausgabe = lauf.stdout.decode("utf-8", "replace")
        if "<validation" not in ausgabe:
            ausgabe += lauf.stderr.decode("utf-8", "replace")
        return werte_bericht_aus(ausgabe)
