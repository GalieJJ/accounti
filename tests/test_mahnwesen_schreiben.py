"""Mahnschreiben als Text und PDF, Versand per Datei und E-Mail."""

import io
from datetime import date, datetime
from pathlib import Path

import pytest
from pypdf import PdfReader

from accounti.belege.archiv import BelegArchiv
from accounti.db.repo_mahnwesen import lade_mahnung
from accounti.db.repository import lade_einen_posten
from accounti.mahnwesen.konfiguration import MahnEinstellungen, MahnStufe
from accounti.mahnwesen.lauf import MahnError, mahnlauf, versende
from accounti.mahnwesen.schreiben import mahn_pdf, mahntext
from accounti.mahnwesen.versand import Versandauftrag, versende_mahnung
from accounti.models import PostenRichtung
from accounti.models.mahnwesen import MahnungStatus
from tests.test_erechnung_aufbau import FIRMA
from tests.zahlung_hilfe import debitor, neue_db, posten, speichere

E = MahnEinstellungen()
JETZT = datetime(2026, 7, 1, 10, 0)  # Versand am Tag der 1. Mahnung


class FalscherWeg:
    name = "email"

    def __init__(self, fehler=None):
        self.gesendet = []
        self.fehler = fehler

    def sende(self, nachricht):
        if self.fehler:
            raise self.fehler
        self.gesendet.append(nachricht)


@pytest.fixture
def erste_mahnung():
    """B2B-Kunde, Erinnerung am 20.06. versendet, 1. Mahnung vom 01.07.2026 als
    Entwurf (2)."""
    fabrik = neue_db()
    k = debitor(ust_id="DE888888888", email="buchhaltung@atelier-kundin.example")
    p = posten(
        k,
        "2026-0042",
        "1190.00",
        faellig=date(2026, 6, 15),
        belegdatum=date(2026, 6, 1),
        richtung=PostenRichtung.FORDERUNG,
    )
    speichere(fabrik, [k], [p])
    with fabrik() as s:
        mahnlauf(s, date(2026, 6, 20), E)
        versende(s, 1, "pdf", E, zeitpunkt=datetime(2026, 6, 20, 9, 0))
        mahnlauf(s, date(2026, 7, 1), E)
        s.commit()
    return fabrik, k, p


def _text(fabrik, k, nr, e=E):
    with fabrik() as s:
        return mahntext(lade_mahnung(s, nr), k, FIRMA, e)


def test_mahntext_mit_zinsen_pauschale_und_anrechnung(erste_mahnung):
    fabrik, k, _ = erste_mahnung
    text = _text(fabrik, k, 2)
    for erwartet in (
        "Galerie Muster GmbH · Beispielweg 3 · 24103 Kiel",
        "Atelier Kundin GmbH\nKundenstraße 8\n10115 Berlin",
        "Kiel, 01.07.2026",
        "1. Mahnung — Rechnung 2026-0042 vom 01.06.2026",
        "Sie befinden sich mit der Zahlung in Verzug",
        "Offener Rechnungsbetrag",
        "In Verzug seit 01.07.2026: Zahlungserinnerung vom 20.06.2026, Frist bis "
        "30.06.2026 (§ 286 Abs. 1 BGB)",
        "Verzugszinsen 10,52 % vom 01.07.2026 bis 01.07.2026 (1 Tag) auf 1.190,00 €",
        "Basiszinssatz 1,52 % + 9 Prozentpunkte, § 288 Abs. 2 BGB",
        "Pauschale nach § 288 Abs. 5 BGB",
        "Mahngebühren von 5,00 € sind auf die Pauschale angerechnet",
        "1.230,34 €",
        "bis zum 11.07.2026",
        "IBAN DE89 3704 0044 0532 0130 00",
        "Mit freundlichen Grüßen\nGalerie Muster GmbH",
    ):
        assert erwartet in text, erwartet
    assert "0,34 €" in text and "40,00 €" in text


def test_erinnerung_ohne_zinsen_und_eigener_text(erste_mahnung):
    fabrik, k, _ = erste_mahnung
    text = _text(fabrik, k, 1)
    assert "Zahlungserinnerung — Rechnung 2026-0042" in text
    assert "Aufmerksamkeit entgangen" in text
    assert "Verzugszinsen" not in text and "Pauschale" not in text
    eigen = E.model_copy(
        update={
            "stufen": [
                MahnStufe(
                    name="Zahlungserinnerung",
                    ab_tagen=5,
                    text="Liebe {kunde}, bitte {summe} € für {nummer} bis {frist}.",
                ),
                *E.stufen[1:],
            ]
        }
    )
    assert (
        "Liebe Atelier Kundin GmbH, bitte 1.190,00 € für 2026-0042 bis 30.06.2026."
        in _text(fabrik, k, 1, eigen)
    )


def test_pdf_enthaelt_das_mahnschreiben(erste_mahnung):
    fabrik, k, _ = erste_mahnung
    with fabrik() as s:
        pdf = mahn_pdf(lade_mahnung(s, 2), k, FIRMA, E, JETZT)
    assert pdf.startswith(b"%PDF")
    inhalt = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    for erwartet in ("1. Mahnung", "2026-0042", "1.230,34", "Pauschale", "10,52 %"):
        assert erwartet in inhalt, erwartet


def test_versand_als_pdf_und_text_mit_archiv(erste_mahnung, tmp_path):
    fabrik, k, p = erste_mahnung
    archiv = BelegArchiv(tmp_path / "archiv")
    auftrag = Versandauftrag(pdf=tmp_path / "m.pdf", text=tmp_path / "m.txt")
    with fabrik() as s:
        m = versende_mahnung(s, 2, FIRMA, E, auftrag, archiv, jetzt=JETZT)
        s.commit()
    assert m.status is MahnungStatus.VERSENDET and m.versand_weg == "pdf, text"
    assert archiv.lese(m.datei_hash) == (tmp_path / "m.pdf").read_bytes()
    assert "1.230,34 €" in (tmp_path / "m.txt").read_text(encoding="utf-8")
    with fabrik() as s:
        assert lade_einen_posten(s, p.id).mahnstufe == 2


def test_versand_per_email(erste_mahnung, tmp_path):
    fabrik, k, _ = erste_mahnung
    weg = FalscherWeg()
    auftrag = Versandauftrag(weg=weg, absender="Galerie Muster <rechnung@gm.example>")
    with fabrik() as s:
        m = versende_mahnung(s, 2, FIRMA, E, auftrag, None, jetzt=JETZT)
        s.commit()
    (nachricht,) = weg.gesendet
    assert nachricht["To"] == "buchhaltung@atelier-kundin.example"
    assert nachricht["Subject"] == "1. Mahnung: Rechnung 2026-0042"
    assert "1.230,34 €" in nachricht.get_body().get_content()
    (anhang,) = list(nachricht.iter_attachments())
    assert anhang.get_filename() == "mahnung-2.pdf"
    assert m.versand_weg == "email"


def test_gescheiterte_email_versendet_nichts(erste_mahnung):
    fabrik, k, p = erste_mahnung
    auftrag = Versandauftrag(weg=FalscherWeg(OSError("Verbindung abgelehnt")))
    with fabrik() as s:
        with pytest.raises(MahnError, match="Verbindung abgelehnt"):
            versende_mahnung(s, 2, FIRMA, E, auftrag, None, jetzt=JETZT)
        assert lade_mahnung(s, 2).status is MahnungStatus.ENTWURF
        assert lade_einen_posten(s, p.id).mahnstufe == 1
    ohne_adresse = Versandauftrag(weg=FalscherWeg())
    k_ohne = k.model_copy(update={"email": None})
    with fabrik() as s:
        from accounti.db.repository import aktualisiere_kontakt

        aktualisiere_kontakt(s, k_ohne)
        with pytest.raises(MahnError, match="keine E-Mail-Adresse"):
            versende_mahnung(s, 2, FIRMA, E, ohne_adresse, None, jetzt=JETZT)
    with fabrik() as s, pytest.raises(MahnError, match="Mindestens --pdf"):
        versende_mahnung(s, 2, FIRMA, E, Versandauftrag(), None, jetzt=JETZT)


def test_email_erst_wenn_alles_lokale_geklappt_hat(erste_mahnung, tmp_path):
    """Scheitert die PDF-Datei, darf keine E-Mail hinausgegangen sein — sonst bekäme
    der Kunde bei jedem neuen Versuch eine weitere."""
    fabrik, k, p = erste_mahnung
    weg = FalscherWeg()
    auftrag = Versandauftrag(weg=weg, pdf=Path("/nonexistent/ordner/m.pdf"))
    for _ in range(2):
        with fabrik() as s:
            with pytest.raises(MahnError, match="nicht geschrieben"):
                versende_mahnung(s, 2, FIRMA, E, auftrag, None, jetzt=JETZT)
            assert lade_mahnung(s, 2).status is MahnungStatus.ENTWURF
            assert lade_einen_posten(s, p.id).mahnstufe == 1
    assert weg.gesendet == []
    auftrag.pdf = tmp_path / "m.pdf"
    with fabrik() as s:
        m = versende_mahnung(s, 2, FIRMA, E, auftrag, None, jetzt=JETZT)
        s.commit()
    assert len(weg.gesendet) == 1 and m.status is MahnungStatus.VERSENDET


def test_mahnung_ohne_verzug_behauptet_keinen_verzug():
    """Stufe mit Zinsen, aber (noch) kein Verzug: kein „Sie befinden sich in Verzug“."""
    fabrik = neue_db()
    k = debitor()
    p = posten(
        k,
        "2026-0042",
        "1190.00",
        faellig=date(2026, 6, 15),
        belegdatum=date(2026, 6, 1),
        richtung=PostenRichtung.FORDERUNG,
    )
    speichere(fabrik, [k], [p])
    e = MahnEinstellungen(
        stufen=[
            MahnStufe(name="Mahnung", ab_tagen=14, verzugszinsen=True),
            MahnStufe(name="Letzte Mahnung", ab_tagen=28, verzugszinsen=True),
        ]
    )
    with fabrik() as s:
        (m,) = mahnlauf(s, date(2026, 6, 29), e).mahnungen
        s.commit()
    text = _text(fabrik, k, m.nr, e)
    assert "Verzug" not in text and "Verzugszinsen" not in text
    assert "Gesamtbetrag von 1.190,00 €" in text
