import shutil
import subprocess
from unittest.mock import patch

import pytest

from accounti.belege.ocr import OCR_ENGINES, OCRError, OCRNichtVerfuegbarError
from accounti.belege.ocr.tesseract import TesseractEngine


def test_registry_kennt_tesseract():
    assert OCR_ENGINES["tesseract"] is TesseractEngine


def test_fehlendes_programm_gibt_hinweis():
    with (
        patch("accounti.belege.ocr.tesseract.shutil.which", return_value=None),
        pytest.raises(OCRNichtVerfuegbarError, match="tesseract-ocr"),
    ):
        TesseractEngine().erkenne(b"bild")


def test_ruft_tesseract_mit_sprache_auf():
    fertig = subprocess.CompletedProcess([], 0, stdout=b"Rechnung\n", stderr=b"")
    with (
        patch("accounti.belege.ocr.tesseract.shutil.which", return_value="/bin/t"),
        patch(
            "accounti.belege.ocr.tesseract.subprocess.run", return_value=fertig
        ) as run,
    ):
        assert TesseractEngine(sprache="deu+eng").erkenne(b"bild") == "Rechnung\n"
    befehl = run.call_args.args[0]
    assert befehl == ["/bin/t", "stdin", "stdout", "-l", "deu+eng"]
    assert run.call_args.kwargs["input"] == b"bild"


def test_fehlercode_wird_zu_ocr_fehler():
    kaputt = subprocess.CompletedProcess(
        [], 1, stdout=b"", stderr=b"Error opening data"
    )
    with (
        patch("accounti.belege.ocr.tesseract.shutil.which", return_value="/bin/t"),
        patch("accounti.belege.ocr.tesseract.subprocess.run", return_value=kaputt),
        pytest.raises(OCRError, match="Error opening data"),
    ):
        TesseractEngine().erkenne(b"bild")


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract fehlt")
def test_echter_lauf_mit_ungueltigem_bild():
    with pytest.raises(OCRError):
        TesseractEngine().erkenne(b"kein bild")
