from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.belege.erkennung import BelegErkenner
from accounti.belege.kanaele import RohBeleg
from accounti.belege.llm import LLMBefund, LLMPosition
from accounti.belege.ocr import OCREngine, OCRNichtVerfuegbarError
from accounti.belege.pipeline import erkenne_erneut, nimm_auf
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_belege
from accounti.models import Beleg, Belegart, Belegrichtung, BelegStatus
from tests.pdf_hilfe import pdf_mit_anhang, pdf_mit_bild, pdf_mit_text

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "belege"


def _text(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def _roh(inhalt, name="r.pdf"):
    return RohBeleg(dateiname=name, inhalt=inhalt, kanal="upload", herkunft=name)


def _leer(roh):
    return Beleg(
        datei_hash="a" * 64,
        dateiname=roh.dateiname,
        kanal=roh.kanal,
        herkunft=roh.herkunft,
        aufbewahren_bis=date(2036, 12, 31),
    )


def _erkenne(erkenner, inhalt, name="r.pdf"):
    roh = _roh(inhalt, name)
    return erkenner(roh, _leer(roh))


class KeineOCR(OCREngine):
    name = "keine"

    def erkenne(self, bild):
        raise OCRNichtVerfuegbarError("Tesseract ist nicht installiert")


def test_pdf_rechnung_wird_vollstaendig_erfasst():
    """Akzeptanz 1 und 2."""
    pdf = pdf_mit_text(_text("rechnung_zwei_steuersaetze.txt"))
    b = _erkenne(BelegErkenner(), pdf)
    assert b.status is BelegStatus.ERFASST, b.pruef_grund
    assert b.belegart is Belegart.EINGANGSRECHNUNG
    assert b.lieferant_name == "Bürobedarf Müller GmbH"
    assert b.belegnummer == "RE-2026-0042"
    assert b.belegdatum == date(2026, 3, 5)
    assert (b.netto, b.steuer, b.brutto) == (
        Decimal("150.00"),
        Decimal("22.50"),
        Decimal("172.50"),
    )
    assert b.zahlungsziel == date(2026, 3, 19)
    assert (b.skonto_prozent, b.skonto_tage) == (Decimal("2"), 7)
    assert [(p.steuersatz, p.netto, p.steuer_betrag) for p in b.positionen] == [
        (Decimal("19"), Decimal("100.00"), Decimal("19.00")),
        (Decimal("7"), Decimal("50.00"), Decimal("3.50")),
    ]
    assert all(p.beleg_id == b.id for p in b.positionen)
    assert b.confidence >= 0.8


def test_unvollstaendige_rechnung_geht_zur_pruefung():
    b = _erkenne(
        BelegErkenner(), _text("rechnung_unvollstaendig.txt").encode(), "r.txt"
    )
    assert b.status is BelegStatus.ZUR_PRUEFUNG
    assert "Belegnummer" in b.pruef_grund
    assert "Belegdatum" in b.pruef_grund
    assert b.brutto == Decimal("450.00")


def test_falsche_rechenprobe_geht_zur_pruefung():
    text = (
        "Firma Test GmbH\nRechnung Nr. 1\nDatum: 01.03.2026\n"
        "Nettobetrag 100,00\nzzgl. 19 % MwSt. 19,00\nGesamtbetrag 120,00\n"
    )
    b = _erkenne(BelegErkenner(), text.encode(), "r.txt")
    assert b.status is BelegStatus.ZUR_PRUEFUNG
    assert "Rechenprobe" in b.pruef_grund


def test_quittung_braucht_keine_belegnummer():
    text = _text("quittung_tankstelle.txt").replace("Bon-Nr. 4711", "Kassenbon")
    b = _erkenne(BelegErkenner(), text.encode(), "q.txt")
    assert b.belegart is Belegart.QUITTUNG
    assert b.status is BelegStatus.ERFASST, b.pruef_grund


def test_kreditkartenabrechnung_ergibt_zwoelf_positionen():
    """Akzeptanz 4."""
    b = _erkenne(
        BelegErkenner(), _text("kreditkarte_12_umsaetze.txt").encode(), "k.txt"
    )
    assert b.belegart is Belegart.KONTOAUSZUG
    assert len(b.positionen) == 12
    assert b.status is BelegStatus.ERFASST


def test_ausgangsrechnung_mit_eigener_ust_id():
    erkenner = BelegErkenner(eigene_ust_ids={"DE999999999"})
    b = _erkenne(erkenner, _text("ausgangsrechnung.txt").encode(), "a.txt")
    assert b.belegart is Belegart.AUSGANGSRECHNUNG
    assert b.richtung is Belegrichtung.AUSGANG


ERECHNUNG = FIXTURES.parent / "erechnung"


def test_leere_erechnung_geht_mit_befunden_zur_pruefung():
    xml = b'<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"/>'
    b = _erkenne(BelegErkenner(), xml, "r.xml")
    assert b.belegart is Belegart.EINGANGSRECHNUNG
    assert b.status is BelegStatus.ZUR_PRUEFUNG
    assert "BR-02" in b.pruef_grund


def test_xrechnung_wird_ohne_ocr_und_ohne_text_erfasst():
    """Akzeptanz 1 — über den Erkenner."""
    xml = (ERECHNUNG / "xrechnung_ubl.xml").read_bytes()
    b = _erkenne(BelegErkenner(ocr=KeineOCR()), xml, "rechnung.xml")
    assert b.status is BelegStatus.ERFASST, b.pruef_grund
    assert b.brutto == Decimal("172.50")
    assert len(b.positionen) == 3


def test_zugferd_ergibt_denselben_beleg_wie_das_xml():
    """Akzeptanz 2."""
    xml = (ERECHNUNG / "xrechnung_cii.xml").read_bytes()
    aus_xml = _erkenne(BelegErkenner(), xml, "r.xml")
    aus_pdf = _erkenne(BelegErkenner(), pdf_mit_anhang("factur-x.xml", xml))
    ohne = {"id", "dateiname", "herkunft", "eingegangen_am", "positionen"}
    assert aus_pdf.model_dump(exclude=ohne) == aus_xml.model_dump(exclude=ohne)
    assert [p.model_dump(exclude={"id", "beleg_id"}) for p in aus_pdf.positionen] == [
        p.model_dump(exclude={"id", "beleg_id"}) for p in aus_xml.positionen
    ]


def test_kaputte_erechnung_im_xml_geht_zur_pruefung():
    cbc = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
    xml = (
        '<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
        f'xmlns:cbc="{cbc}"><cbc:IssueDate>gestern</cbc:IssueDate></Invoice>'
    ).encode()
    b = _erkenne(BelegErkenner(), xml, "r.xml")
    assert b.status is BelegStatus.ZUR_PRUEFUNG
    assert "E-Rechnung (UBL) nicht lesbar" in b.pruef_grund


def test_zugferd_mit_kaputtem_xml_nutzt_die_pdf_ansicht():
    import io

    from pypdf import PdfReader, PdfWriter

    text_pdf = pdf_mit_text(_text("rechnung_zwei_steuersaetze.txt"))
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(text_pdf)))
    writer.add_attachment(
        "factur-x.xml",
        b'<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:'
        b'CrossIndustryInvoice:100"><!DOCTYPE x></rsm:CrossIndustryInvoice>',
    )
    out = io.BytesIO()
    writer.write(out)
    b = _erkenne(BelegErkenner(), out.getvalue())
    assert b.status is BelegStatus.ZUR_PRUEFUNG
    assert "nicht lesbar" in b.pruef_grund
    assert b.brutto == Decimal("172.50")  # aus der PDF-Ansicht vorbefüllt


def test_scan_ohne_ocr_wirft_damit_die_pipeline_pruefung_setzt():
    with pytest.raises(OCRNichtVerfuegbarError):
        _erkenne(BelegErkenner(ocr=KeineOCR()), pdf_mit_bild(b"\xff\xd8\xff\xe0X"))


def test_scan_ohne_ocr_landet_in_pruefung(tmp_path):
    """Akzeptanz 5 — über die Pipeline."""
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    with make_session() as s:
        nimm_auf(
            s,
            BelegArchiv(tmp_path),
            _roh(pdf_mit_bild(b"\xff\xd8\xff\xe0X"), "scan.pdf"),
            erkenner=BelegErkenner(ocr=KeineOCR()),
        )
        s.commit()
        (b,) = lade_belege(s)
    assert b.status is BelegStatus.ZUR_PRUEFUNG
    assert "Tesseract ist nicht installiert" in b.pruef_grund


def test_llm_fuellt_nur_luecken():
    llm = MagicMock()
    llm.lies.return_value = LLMBefund(
        belegart=Belegart.QUITTUNG,
        belegdatum=date(2026, 3, 1),
        brutto=Decimal("999.00"),
        positionen=[LLMPosition("Gestaltung Flyer", Decimal("450.00"))],
        confidence=0.7,
    )
    b = _erkenne(
        BelegErkenner(llm=llm), _text("rechnung_unvollstaendig.txt").encode(), "r.txt"
    )
    assert b.belegart is Belegart.EINGANGSRECHNUNG  # Regelwerk gewinnt
    assert b.brutto == Decimal("450.00")  # Regelwerk gewinnt
    assert b.belegdatum == date(2026, 3, 1)  # Lücke vom LLM gefüllt
    assert [p.bezeichnung for p in b.positionen] == ["Gestaltung Flyer"]
    assert b.status is BelegStatus.ZUR_PRUEFUNG  # Belegnummer fehlt weiter
    assert "LLM" in b.pruef_grund


def test_llm_wird_bei_vollstaendigem_beleg_nicht_gefragt():
    llm = MagicMock()
    _erkenne(
        BelegErkenner(llm=llm), pdf_mit_text(_text("rechnung_zwei_steuersaetze.txt"))
    )
    llm.lies.assert_not_called()


def test_erkenne_erneut_liest_original_aus_dem_archiv(tmp_path):
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    archiv = BelegArchiv(tmp_path)
    pdf = pdf_mit_text(_text("rechnung_zwei_steuersaetze.txt"))
    with make_session() as s:
        nimm_auf(s, archiv, _roh(pdf))  # ohne Erkenner → eingegangen
        s.commit()
    with make_session() as s:
        (alt,) = lade_belege(s)
        assert alt.status is BelegStatus.EINGEGANGEN
        neu = erkenne_erneut(s, archiv, alt, BelegErkenner())
        s.commit()
    with make_session() as s:
        (geladen,) = lade_belege(s)
    assert neu.id == alt.id
    assert geladen.status is BelegStatus.ERFASST
    assert geladen.brutto == Decimal("172.50")
    assert len(geladen.positionen) == 2
    assert geladen.datei_hash == alt.datei_hash
    assert geladen.kanal == alt.kanal


def test_erkenne_erneut_findet_dublette_im_bestand(tmp_path):
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    archiv = BelegArchiv(tmp_path)
    text = _text("rechnung_zwei_steuersaetze.txt")
    with make_session() as s:
        nimm_auf(s, archiv, _roh(text.encode(), "a.txt"), erkenner=BelegErkenner())
        nimm_auf(s, archiv, _roh(pdf_mit_text(text), "b.pdf"))  # noch nicht gelesen
        s.commit()
        offen = lade_belege(s, status={BelegStatus.EINGEGANGEN})
        neu = erkenne_erneut(s, archiv, offen[0], BelegErkenner())
    assert neu.status is BelegStatus.ZUR_PRUEFUNG
    assert "Dublette" in neu.pruef_grund


# --- Gesamttest Paket C -----------------------------------------------------------


def test_reverse_charge_pdf_wird_erfasst():
    """B06: 0 % mit Hinweis „Steuerschuldnerschaft des Leistungsempfängers“ ist kein
    fehlender Steuerausweis — der Beleg bleibt nicht in der Prüfung hängen."""
    from tests.test_belege_extraktion import REVERSE_CHARGE

    b = _erkenne(BelegErkenner(), pdf_mit_text(REVERSE_CHARGE))
    assert b.status is BelegStatus.ERFASST, b.pruef_grund
    assert b.steuerkennzeichen == "AE"
    (p,) = b.positionen
    assert (p.netto, p.steuersatz, p.steuer_betrag) == (
        Decimal("600.00"),
        Decimal("0"),
        Decimal("0.00"),
    )
    assert "§ 13b" in p.bezeichnung


def test_lieferantengutschrift_mit_negativen_betraegen():
    """B12: Netto, Steuer, Brutto und Position negativ — die Verbuchung dreht."""
    from tests.test_belege_extraktion import GUTSCHRIFT

    b = _erkenne(BelegErkenner(), pdf_mit_text(GUTSCHRIFT))
    assert b.status is BelegStatus.ERFASST, b.pruef_grund
    assert (b.netto, b.steuer, b.brutto) == (
        Decimal("-200.00"),
        Decimal("-38.00"),
        Decimal("-238.00"),
    )
    (p,) = b.positionen
    assert (p.netto, p.steuer_betrag) == (Decimal("-200.00"), Decimal("-38.00"))


def test_gutschrift_mit_positiven_betraegen_zur_pruefung():
    text = (
        "Rahmenwerk Nord GmbH\nGutschrift\nGutschrift Nr. G-17\n"
        "Datum: 20.10.2026\nSumme netto 200,00\nzzgl. 19 % USt 38,00\n"
        "Gesamtbetrag 238,00\n"
    )
    b = _erkenne(BelegErkenner(), text.encode(), "g.txt")
    assert b.brutto == Decimal("-238.00")
    assert b.status is BelegStatus.ZUR_PRUEFUNG
    assert "§ 14 Abs. 2 S. 2" in b.pruef_grund


def test_zugferd_minimum_nimmt_steuersatz_aus_der_pdf_ansicht():
    """B05: MINIMUM liefert keinen Satz; die PDF-Ansicht schon — zur Prüfung bleibt
    der Beleg trotzdem (Buchungshilfe, keine E-Rechnung)."""
    import io

    from pypdf import PdfReader, PdfWriter

    ansicht = pdf_mit_text(
        "Druckerei Beispiel GmbH\nRechnung MIN-2026-9\nNettobetrag 1.000,00\n"
        "zzgl. 19 % USt 190,00\nGesamtbetrag 1.190,00\n"
    )
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(ansicht)))
    writer.add_attachment("factur-x.xml", (ERECHNUNG / "minimum_cii.xml").read_bytes())
    puffer = io.BytesIO()
    writer.write(puffer)
    b = _erkenne(BelegErkenner(), puffer.getvalue())
    assert b.status is BelegStatus.ZUR_PRUEFUNG
    assert "PROFIL" in b.pruef_grund
    (p,) = b.positionen
    assert (p.netto, p.steuersatz, p.steuer_betrag) == (
        Decimal("1000.00"),
        Decimal("19"),
        Decimal("190.00"),
    )
    nur_xml = _erkenne(
        BelegErkenner(),
        pdf_mit_anhang("factur-x.xml", (ERECHNUNG / "minimum_cii.xml").read_bytes()),
    )
    (p,) = nur_xml.positionen
    assert p.steuersatz is None and nur_xml.status is BelegStatus.ZUR_PRUEFUNG
