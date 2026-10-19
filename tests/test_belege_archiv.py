import hashlib
import os
from datetime import date

from accounti.belege.archiv import BelegArchiv, aufbewahrungsende


def test_ablegen_ist_content_adressiert(tmp_path):
    archiv = BelegArchiv(tmp_path)
    inhalt = b"%PDF-1.7 Rechnung"
    h = archiv.ablegen(inhalt, ".pdf")
    assert h == hashlib.sha256(inhalt).hexdigest()
    pfad = tmp_path / h[:2] / h[2:4] / f"{h}.pdf"
    assert archiv.pfad(h) == pfad
    assert pfad.read_bytes() == inhalt
    assert archiv.lese(h) == inhalt


def test_ablegen_ist_idempotent(tmp_path):
    archiv = BelegArchiv(tmp_path)
    h1 = archiv.ablegen(b"abc", ".pdf")
    h2 = archiv.ablegen(b"abc", ".PDF")
    assert h1 == h2
    assert len(list(tmp_path.rglob("*.*"))) == 1


def test_abgelegte_datei_ist_schreibgeschuetzt(tmp_path):
    archiv = BelegArchiv(tmp_path)
    h = archiv.ablegen(b"abc", ".pdf")
    modus = os.stat(archiv.pfad(h)).st_mode
    assert modus & 0o222 == 0
    assert not any(hasattr(archiv, n) for n in ("loesche", "entferne", "delete"))


def test_endung_ohne_punkt_und_leer(tmp_path):
    archiv = BelegArchiv(tmp_path)
    h = archiv.ablegen(b"x", "")
    assert archiv.pfad(h).name == h
    assert archiv.enthaelt(h)
    assert not archiv.enthaelt("0" * 64)


def test_aufbewahrungsende_schluss_des_kalenderjahres():
    assert aufbewahrungsende(date(2026, 3, 5)) == date(2036, 12, 31)
    assert aufbewahrungsende(date(2026, 12, 31)) == date(2036, 12, 31)
