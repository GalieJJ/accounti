"""Belegvorschau (Spec 4.2 „Beleg links“; Baustein 10b, Paket 3)."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

from accounti.api.sicherheit import CSP
from tests.auth_hilfe import billige_hashes
from tests.pruefen_hilfe import jpeg, pdf, png, queuewelt, tiff

ERECHNUNG = Path(__file__).resolve().parents[1] / "examples" / "erechnung"


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def qw(tmp_path):
    return queuewelt(tmp_path)


@pytest.fixture
def jan(qw):
    return qw.web.angemeldet("jan")


def test_pdf_inline_mit_sicheren_kopfzeilen(qw, jan):
    inhalt = pdf()
    b = qw.beleg(inhalt, ".pdf", dateiname='Rechnung "böse".pdf')
    r = jan.get(f"/belege/{b.id}/datei")
    assert r.status_code == 200 and r.content == inhalt
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == f'inline; filename="beleg-{b.id}.pdf"'
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["cross-origin-resource-policy"] == "same-origin"
    csp = r.headers["content-security-policy"]
    assert csp == CSP.replace("form-action 'self'", "form-action 'none'")
    assert "sandbox" not in csp and "frame-ancestors 'self'" in csp


def test_range_anfrage(qw, jan):
    inhalt = pdf()
    b = qw.beleg(inhalt)
    r = jan.get(f"/belege/{b.id}/datei", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and r.content == inhalt[:10]
    assert r.headers["accept-ranges"] == "bytes"


def test_png_und_jpeg(qw, jan):
    for inhalt, typ in ((png(), "image/png"), (jpeg(), "image/jpeg")):
        b = qw.beleg(inhalt, ".bin", dateiname="scan")
        r = jan.get(f"/belege/{b.id}/datei")
        assert r.status_code == 200 and r.headers["content-type"] == typ
        assert r.content == inhalt
        seite = jan.get(f"/belege/{b.id}").text
        assert f'<img class="beleg-bild" src="/belege/{b.id}/datei"' in seite


def test_tiff_als_png_seiten(qw, jan):
    from PIL import Image

    b = qw.beleg(tiff((5, 4), (6, 3), (2, 2)), ".tif")
    seite = jan.get(f"/belege/{b.id}").text
    for n in (1, 2, 3):
        assert f'src="/belege/{b.id}/seite/{n}.png"' in seite
    r = jan.get(f"/belege/{b.id}/seite/2.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    import io

    with Image.open(io.BytesIO(r.content)) as bild:
        assert bild.format == "PNG" and bild.size == (6, 3)
    assert jan.get(f"/belege/{b.id}/seite/4.png").status_code == 404
    assert jan.get(f"/belege/{b.id}/datei").status_code == 415  # TIFF nie roh inline
    fax = qw.beleg(tiff((8, 8), modus="1"), ".tif")
    assert jan.get(f"/belege/{fax.id}/seite/1.png").status_code == 200


def test_bildbombe_wird_nicht_dekodiert(qw, jan, monkeypatch):
    from PIL import ImageFile

    b = qw.beleg(tiff((3000, 3000)), ".tif")  # 9 MP
    qw.web.dienste.server.max_vorschau_megapixel = 5
    geladen: list[object] = []
    original = ImageFile.ImageFile.load
    monkeypatch.setattr(
        ImageFile.ImageFile, "load", lambda self: geladen.append(self) or original(self)
    )
    r = jan.get(f"/belege/{b.id}/seite/1.png")
    assert r.status_code == 415 and geladen == []


def test_bildbombe_auf_seite_zwei(qw, jan):
    b = qw.beleg(tiff((10, 10), (3000, 3000)), ".tif")
    qw.web.dienste.server.max_vorschau_megapixel = 5
    assert jan.get(f"/belege/{b.id}/seite/1.png").status_code == 200
    assert jan.get(f"/belege/{b.id}/seite/2.png").status_code == 415


@pytest.mark.filterwarnings("ignore:Corrupt EXIF data")
def test_tiff_nur_mit_tiff_decoder(qw, jan, monkeypatch):
    """EPS-Inhalt mit TIFF-Signatur: abgelehnt, nie durch einen anderen Decoder
    (EPS → Ghostscript)."""
    from PIL import Image

    aufrufe: list[object] = []
    original = Image.open

    def offen(fp, mode="r", formats=None):  # noqa: ANN001, ANN202
        aufrufe.append(formats)
        return original(fp, mode, formats)

    monkeypatch.setattr(Image, "open", offen)
    eps = b"II*\x00" + b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\n" * 20
    b = qw.beleg(eps, ".tif")
    assert jan.get(f"/belege/{b.id}/seite/1.png").status_code == 415
    assert aufrufe and all(f == ["TIFF"] for f in aufrufe)


def test_veraenderte_archivdatei_409(qw, jan):
    b = qw.beleg(pdf())
    pfad = qw.archiv().pfad(b.datei_hash)
    os.chmod(pfad, stat.S_IRUSR | stat.S_IWUSR)
    pfad.write_bytes(pdf("manipuliert"))
    r = jan.get(f"/belege/{b.id}/datei")
    assert r.status_code == 409 and "%PDF" not in r.text
    assert "verändert" in r.text
    seite = jan.get(f"/belege/{b.id}").text
    assert "passt nicht zum gespeicherten Prüfwert" in seite


@pytest.mark.parametrize("datei", ["xrechnung_ubl.xml", "xrechnung_cii.xml"])
def test_xrechnung_als_lesbare_ansicht(qw, jan, datei):
    inhalt = (ERECHNUNG / datei).read_bytes()
    b = qw.beleg(inhalt, ".xml", belegart="eingangsrechnung")
    seite = jan.get(f"/belege/{b.id}").text
    assert "<h3>E-Rechnung</h3>" in seite and "Rechnungsnummer" in seite
    assert "Positionen" in seite and "Steueraufschlüsselung" in seite
    assert "&lt;?xml" not in seite and "<?xml" not in seite
    assert jan.get(f"/belege/{b.id}/datei").status_code == 415
    roh = jan.get(f"/belege/{b.id}/download")
    assert roh.headers["content-type"] == "application/octet-stream"
    assert (
        roh.headers["content-disposition"] == f'attachment; filename="beleg-{b.id}.xml"'
    )


def test_zugferd_pdf_und_strukturierter_teil(qw, jan):
    from tests.test_erechnung_zugferd import _pdf

    rechnung, _xml, zugferd = _pdf()
    b = qw.beleg(zugferd, ".pdf", belegnummer="ANDERE-NR")
    seite = jan.get(f"/belege/{b.id}").text
    assert f'src="/belege/{b.id}/datei"' in seite
    assert "E-Rechnung (maßgeblich)" in seite
    assert f"Nummer: ANDERE-NR ≠ {rechnung.nummer}" in seite
    assert jan.get(f"/belege/{b.id}/datei").headers["content-type"] == "application/pdf"


@pytest.mark.parametrize(
    ("inhalt", "endung"),
    [
        (
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            ".svg",
        ),
        (b"<html><script>alert(1)</script></html>", ".html"),
        (b"<?xml version='1.0'?><kein>e-rechnung</kein>", ".xml"),
        (b"Nur Text\n", ".txt"),
    ],
)
def test_xml_svg_html_text_nie_inline(qw, jan, inhalt, endung):
    b = qw.beleg(inhalt, endung)
    assert jan.get(f"/belege/{b.id}/datei").status_code == 415
    seite = jan.get(f"/belege/{b.id}").text
    assert "Keine Vorschau" in seite and "<script>alert" not in seite
    r = jan.get(f"/belege/{b.id}/download")
    assert r.status_code == 200 and r.content == inhalt
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert (
        r.headers["content-disposition"] == f'attachment; filename="beleg-{b.id}.bin"'
    )


def test_dateiname_des_absenders_nie_im_kopf(qw, jan):
    for name in ('a"b.pdf', "x\r\nSet-Cookie: y.pdf", "Ärger €.pdf"):
        b = qw.beleg(pdf(name), ".pdf", dateiname=name)
        for pfad in ("datei", "download"):
            kopf = jan.get(f"/belege/{b.id}/{pfad}").headers["content-disposition"]
            assert kopf.endswith(f'filename="beleg-{b.id}.pdf"'), kopf
            assert "Ärger" not in kopf and "Set-Cookie" not in kopf


def test_typ_aus_dem_inhalt(qw, jan):
    b = qw.beleg(pdf(), ".png", dateiname="foto.png")
    r = jan.get(f"/belege/{b.id}/datei")
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].endswith(f'beleg-{b.id}.pdf"')


def test_beleg_anderer_gesellschaft_404(qw, jan):
    fremd = qw.beleg(pdf("Beta"), kuerzel="b")
    for pfad in ("", "/datei", "/download", "/seite/1.png"):
        assert jan.get(f"/belege/{fremd.id}{pfad}").status_code == 404, pfad


def test_datei_fehlt_404_ohne_pfad(qw, jan):
    b = qw.beleg(pdf())
    pfad = qw.archiv().pfad(b.datei_hash)
    os.chmod(pfad, stat.S_IRUSR | stat.S_IWUSR)
    pfad.unlink()
    r = jan.get(f"/belege/{b.id}/datei")
    assert r.status_code == 404 and str(pfad) not in r.text
    assert b.datei_hash not in r.text and "archiv-a" not in r.text


def test_hash_aus_der_datenbank_wird_geprueft(qw, jan):
    b = qw.beleg(pdf())
    qw.sql("UPDATE belege SET datei_hash = '../../etc/passwd'")
    assert jan.get(f"/belege/{b.id}/datei").status_code == 404


def test_markup_in_erechnung_und_begruendung_escaped(qw, jan):
    from accounti.db.repo_kontierung import speichere_kontierungsgrund

    xml = (ERECHNUNG / "xrechnung_ubl.xml").read_text(encoding="utf-8")
    import re

    xml = re.sub(
        r"(<cbc:Note>)([^<]*)", r"\1&lt;script&gt;alert(1)&lt;/script&gt;", xml, count=1
    )
    if "<cbc:Note>" not in xml:
        xml = xml.replace(
            "</cbc:DocumentCurrencyCode>",
            "</cbc:DocumentCurrencyCode><cbc:Note>&lt;script&gt;alert(1)&lt;/script&gt;"
            "</cbc:Note>",
            1,
        )
    b = qw.beleg(xml.encode(), ".xml")
    buchung = qw.buchung(beleg_id=b.id)
    with qw.fabrik()() as s:
        speichere_kontierungsgrund(
            s, buchung.id, quelle="llm", begruendung="<img src=x onerror=alert(1)>"
        )
        s.commit()
    for pfad in (f"/belege/{b.id}", f"/pruefen/{buchung.id}"):
        seite = jan.get(pfad).text
        assert "<script>alert(1)</script>" not in seite
        assert "<img src=x" not in seite


def test_sha256_wie_archiv(qw, jan):
    inhalt = png()
    b = qw.beleg(inhalt)
    assert hashlib.sha256(jan.get(f"/belege/{b.id}/datei").content).hexdigest() == (
        b.datei_hash
    )
