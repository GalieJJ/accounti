"""Tesseract — lokale Texterkennung über das Kommandozeilenprogramm."""

from __future__ import annotations

import shutil
import subprocess

from accounti.belege.ocr import (
    OCREngine,
    OCRError,
    OCRNichtVerfuegbarError,
    registriere,
)

INSTALLATIONSHINWEIS = (
    "Tesseract ist nicht installiert — "
    "z.B. `apt install tesseract-ocr tesseract-ocr-deu`"
)


@registriere
class TesseractEngine(OCREngine):
    name = "tesseract"

    def __init__(
        self, sprache: str = "deu", programm: str = "tesseract", timeout: int = 120
    ) -> None:
        self.sprache = sprache
        self.programm = programm
        self.timeout = timeout

    def erkenne(self, bild: bytes) -> str:
        pfad = shutil.which(self.programm)
        if pfad is None:
            raise OCRNichtVerfuegbarError(INSTALLATIONSHINWEIS)
        try:
            ergebnis = subprocess.run(
                [pfad, "stdin", "stdout", "-l", self.sprache],
                input=bild,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as fehler:
            msg = f"Tesseract nach {self.timeout}s abgebrochen"
            raise OCRError(msg) from fehler
        if ergebnis.returncode != 0:
            meldung = ergebnis.stderr.decode("utf-8", "replace").strip()
            raise OCRError(f"Tesseract: {meldung or ergebnis.returncode}")
        return ergebnis.stdout.decode("utf-8", "replace")
