"""OCR — steckbar; lokale Engine als Default, Cloud-Dienste nur bewusst aktiviert."""

from __future__ import annotations


class OCRError(RuntimeError):
    """Die Texterkennung ist fehlgeschlagen."""


class OCRNichtVerfuegbarError(OCRError):
    """Die OCR-Engine ist auf diesem System nicht installiert."""


class OCREngine:
    """Basisklasse: Bild rein (JPEG, PNG, TIFF …), Text raus."""

    name: str = "base"

    def erkenne(self, bild: bytes) -> str:
        raise NotImplementedError


# Registry: Name -> Engine-Klasse.
OCR_ENGINES: dict[str, type[OCREngine]] = {}


def registriere(engine: type[OCREngine]) -> type[OCREngine]:
    OCR_ENGINES[engine.name] = engine
    return engine


from accounti.belege.ocr import tesseract  # noqa: E402, F401
