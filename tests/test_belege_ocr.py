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


@pytest.mark.parametrize(
    ("ocr", "erwartet"),
    [
        ("MwSt 19 $ Netto 63,72", "MwSt 19 % Netto 63,72"),
        ("zzgl. 7°/o USt", "zzgl. 7 % USt"),
        ("19%o MwSt", "19 % MwSt"),
        ("Preis 12 EUR", "Preis 12 EUR"),
    ],
)
def test_ocr_normalisierung(ocr, erwartet):
    from accounti.belege.erkennung import normalisiere_ocr

    assert normalisiere_ocr(ocr) == erwartet


SCAN = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "examples"
    / "belege"
    / "quittung_tankstelle_scan.jpg"
)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract fehlt")
def test_echter_scan_wird_zur_erfassten_quittung():
    from datetime import date
    from decimal import Decimal

    from accounti.belege.erkennung import BelegErkenner
    from accounti.belege.kanaele import RohBeleg
    from accounti.models import Beleg, Belegart, BelegStatus

    roh = RohBeleg(
        dateiname=SCAN.name, inhalt=SCAN.read_bytes(), kanal="upload", herkunft="x"
    )
    leer = Beleg(
        datei_hash="a" * 64,
        dateiname=roh.dateiname,
        kanal="upload",
        herkunft="x",
        aufbewahren_bis=date(2036, 12, 31),
    )
    b = BelegErkenner()(roh, leer)
    assert b.belegart is Belegart.QUITTUNG
    assert b.belegdatum == date(2026, 3, 12)
    assert b.brutto == Decimal("75.83")
    assert [(p.steuersatz, p.netto, p.steuer_betrag) for p in b.positionen] == [
        (Decimal("19"), Decimal("63.72"), Decimal("12.11"))
    ]
    assert b.status is BelegStatus.ERFASST, b.pruef_grund
