"""Erzeugt minimale PDFs für Tests — ohne zusätzliche Bibliothek."""

from __future__ import annotations

import io


def _escape(text: str) -> bytes:
    roh = text.encode("cp1252")
    return roh.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _pdf(objekte: list[bytes]) -> bytes:
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for nr, obj in enumerate(objekte, start=1):
        offsets.append(out.tell())
        out.write(f"{nr} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objekte) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objekte) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


def _stream(kopf: bytes, daten: bytes) -> bytes:
    return (
        b"<< "
        + kopf
        + b" /Length %d >>\nstream\n" % len(daten)
        + daten
        + (b"\nendstream")
    )


def pdf_mit_text(text: str) -> bytes:
    """Eine Seite, jede Textzeile als eigene Zeile in Helvetica."""
    inhalt = b"BT /F1 10 Tf 14 TL 40 800 Td\n"
    for zeile in text.splitlines():
        inhalt += b"(" + _escape(zeile) + b") Tj T*\n"
    inhalt += b"ET"
    return _pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding >>",
            _stream(b"", inhalt),
        ]
    )


def pdf_mit_bild(jpeg: bytes) -> bytes:
    """Eine gescannte Seite: nur ein JPEG-Bild, keine Textebene."""
    return _pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /XObject << /Im1 4 0 R >> >> /Contents 5 0 R >>",
            _stream(
                b"/Type /XObject /Subtype /Image /Width 1 /Height 1 "
                b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /DCTDecode",
                jpeg,
            ),
            _stream(b"", b"q 595 0 0 842 0 0 cm /Im1 Do Q"),
        ]
    )


def pdf_mit_anhang(name: str, inhalt: bytes) -> bytes:
    """Leere Seite mit eingebetteter Datei (wie bei ZUGFeRD/Factur-X)."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(595, 842)
    writer.add_attachment(name, inhalt)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
