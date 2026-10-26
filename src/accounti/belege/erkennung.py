"""Format- und Belegarterkennung — und der BelegErkenner, der alles verbindet.

Reihenfolge: strukturierte Daten (E-Rechnung) schlagen immer die Textebene eines
PDFs, die Textebene schlägt OCR.
"""

from __future__ import annotations

import enum
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal
from pathlib import PurePath
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from accounti.belege.extraktion import TOLERANZ, Extrakt, extrahiere
from accounti.belege.kanaele import RohBeleg
from accounti.belege.llm import LLMBelegEngine
from accounti.belege.ocr import OCREngine
from accounti.belege.ocr.tesseract import TesseractEngine
from accounti.belege.positionen import (
    ist_kreditkartenabrechnung,
    positionen_aus_steuerzeilen,
    positionen_aus_umsaetzen,
    zerlege_kreditkartenabrechnung,
)
from accounti.erechnung import ERechnungError
from accounti.erechnung import lies as lies_erechnung
from accounti.erechnung.abbildung import zu_beleg
from accounti.erechnung.validierung import pruefe
from accounti.models import Beleg, Belegart, Belegposition, Belegrichtung, BelegStatus


class ErkennungError(RuntimeError):
    """Der Beleg konnte nicht gelesen werden; er geht zur Prüfung."""


class Format(str, enum.Enum):
    ERECHNUNG_XML = "erechnung_xml"  # XRechnung (UBL/CII) als reine XML-Datei
    ZUGFERD_PDF = "zugferd_pdf"  # PDF/A-3 mit eingebetteter E-Rechnung
    PDF = "pdf"
    BILD = "bild"
    TEXT = "text"
    UNBEKANNT = "unbekannt"


@dataclass(frozen=True)
class FormatBefund:
    format: Format
    syntax: str | None = None  # "CII" oder "UBL" bei E-Rechnungen
    xml: bytes | None = None


# Wurzelelemente der E-Rechnungs-Syntaxen (EN 16931)
_ERECHNUNG_WURZEL = {
    "CrossIndustryInvoice": "CII",
    "Invoice": "UBL",
    "CreditNote": "UBL",
}
_BILD_SIGNATUREN = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"II*\x00", b"MM\x00*")
MIN_TEXTEBENE = 20  # Zeichen; darunter gilt ein PDF als Scan


def _erechnung_syntax(xml: bytes) -> str | None:
    """Liest nur das Wurzelelement — der Rest der Datei wird nicht geparst."""
    try:
        for _, element in ET.iterparse(io.BytesIO(xml), events=("start",)):
            return _ERECHNUNG_WURZEL.get(element.tag.rpartition("}")[2])
    except ET.ParseError:
        return None
    return None


def _pdf(inhalt: bytes) -> PdfReader | None:
    try:
        return PdfReader(io.BytesIO(inhalt))
    except (PdfReadError, ValueError, OSError):
        return None


def erkenne_format(roh: RohBeleg) -> FormatBefund:
    kopf = roh.inhalt[:16].lstrip(b"\xef\xbb\xbf \t\r\n")
    if kopf.startswith(b"%PDF"):
        reader = _pdf(roh.inhalt)
        if reader is not None:
            try:
                anhaenge = reader.attachments
            except (PdfReadError, KeyError, ValueError):
                anhaenge = {}
            for name, inhalte in anhaenge.items():
                if not name.lower().endswith(".xml"):
                    continue
                for xml in inhalte:
                    if syntax := _erechnung_syntax(xml):
                        return FormatBefund(Format.ZUGFERD_PDF, syntax, xml)
        return FormatBefund(Format.PDF)
    if kopf.startswith(b"<"):
        syntax = _erechnung_syntax(roh.inhalt)
        if syntax:
            return FormatBefund(Format.ERECHNUNG_XML, syntax, roh.inhalt)
        return FormatBefund(Format.UNBEKANNT)
    if roh.inhalt.startswith(_BILD_SIGNATUREN):
        return FormatBefund(Format.BILD)
    if PurePath(roh.dateiname).suffix.lower() == ".txt":
        return FormatBefund(Format.TEXT)
    return FormatBefund(Format.UNBEKANNT)


# Typische OCR-Verwechslungen beim Prozentzeichen: 19 $ · 7°/o · 19%o
_OCR_PROZENT = re.compile(r"(?<=\d)\s?(?:\$|°/o|o/o|%o|%)(?=\s|$)", re.MULTILINE)


def normalisiere_ocr(text: str) -> str:
    """Korrigiert OCR-Fehler, die das Regelwerk sonst aus dem Tritt bringen."""
    return _OCR_PROZENT.sub(" %", text)


def _scanbilder(reader: PdfReader) -> list[bytes]:
    """JPEG-Seitenbilder unverändert aus dem PDF holen (DCT/JPX: kein Dekodieren)."""
    bilder = []
    for seite in reader.pages:
        ressourcen = seite.get("/Resources")
        xobjekte = ressourcen.get_object().get("/XObject") if ressourcen else None
        if not xobjekte:
            continue
        for ref in xobjekte.get_object().values():
            obj = ref.get_object()
            if obj.get("/Subtype") != "/Image":
                continue
            filter_ = obj.get("/Filter")
            filter_ = filter_[-1] if isinstance(filter_, list) else filter_
            if filter_ not in ("/DCTDecode", "/JPXDecode"):
                msg = f"Bildformat {filter_} im Scan wird noch nicht unterstützt"
                raise ErkennungError(msg)
            bilder.append(obj.get_data())
    return bilder


def hole_text(
    roh: RohBeleg, befund: FormatBefund, ocr: OCREngine | None
) -> tuple[str, str]:
    """Liefert (Text, Quelle) mit Quelle ``pdf``, ``ocr`` oder ``text``."""
    if befund.format is Format.TEXT:
        try:
            return roh.inhalt.decode("utf-8"), "text"
        except UnicodeDecodeError:
            return roh.inhalt.decode("cp1252", "replace"), "text"

    bilder: list[bytes]
    if befund.format in (Format.PDF, Format.ZUGFERD_PDF):
        reader = _pdf(roh.inhalt)
        if reader is None:
            raise ErkennungError("PDF ist beschädigt und nicht lesbar")
        text = "\n".join(seite.extract_text() or "" for seite in reader.pages)
        if len(text.strip()) >= MIN_TEXTEBENE:
            return text, "pdf"
        bilder = _scanbilder(reader)
        if not bilder:
            raise ErkennungError("PDF hat weder Textebene noch Seitenbilder")
    elif befund.format is Format.BILD:
        bilder = [roh.inhalt]
    else:
        msg = f"Format von {roh.dateiname} nicht erkannt"
        raise ErkennungError(msg)

    if ocr is None:
        raise ErkennungError("Scan ohne Textebene, aber keine OCR-Engine aktiv")
    return "\n".join(ocr.erkenne(b) for b in bilder), "ocr"


# ---------------------------------------------------------------------------
# Belegart
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BelegartBefund:
    belegart: Belegart
    confidence: float
    begruendung: str


_I = re.IGNORECASE
_REGELN: list[tuple[re.Pattern[str], Belegart, float, str]] = [
    (
        re.compile(r"kontoauszug|(?:alter|neuer)\s+kontostand", _I),
        Belegart.KONTOAUSZUG,
        0.9,
        "Kontoauszug mit Kontostand",
    ),
    (
        re.compile(r"kassenbon|bon[\s-]*nr|\bquittung\b|kassenbeleg|\bTSE\b", _I),
        Belegart.QUITTUNG,
        0.9,
        "Kassenbon/Quittung",
    ),
    (
        re.compile(r"\brechnung|\binvoice\b|\bgutschrift\b", _I),
        Belegart.EINGANGSRECHNUNG,
        0.9,
        "Rechnungsmerkmal im Text",
    ),
    (
        re.compile(r"\w*vertrag\b|vertragslaufzeit|vertragsbeginn", _I),
        Belegart.VERTRAG,
        0.8,
        "Vertragsmerkmal im Text",
    ),
]


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def erkenne_belegart(
    text: str,
    extrakt: Extrakt,
    eigene_ust_ids: set[str] | None = None,
    eigene_firma: str | None = None,
) -> BelegartBefund:
    """Regelwerk: das erste passende Merkmal entscheidet."""
    if ist_kreditkartenabrechnung(text):
        return BelegartBefund(Belegart.KONTOAUSZUG, 0.95, "Kreditkartenabrechnung")
    for muster, art, confidence, grund in _REGELN:
        if not muster.search(text):
            continue
        if art is Belegart.EINGANGSRECHNUNG:
            eigene = {_norm(u) for u in eigene_ust_ids or set()}
            if (
                extrakt.lieferant_ust_id and _norm(extrakt.lieferant_ust_id) in eigene
            ) or (
                eigene_firma and _norm(extrakt.lieferant_name) == _norm(eigene_firma)
            ):
                return BelegartBefund(
                    Belegart.AUSGANGSRECHNUNG,
                    confidence,
                    "Rechnung mit eigenem Absender",
                )
        return BelegartBefund(art, confidence, grund)
    return BelegartBefund(Belegart.SONSTIGES, 0.3, "kein Merkmal erkannt")


# ---------------------------------------------------------------------------
# BelegErkenner — der `erkenner` der Pipeline
# ---------------------------------------------------------------------------

_PFLICHTFELDER: dict[Belegart, tuple[str, ...]] = {
    Belegart.EINGANGSRECHNUNG: (
        "Lieferant",
        "Belegnummer",
        "Belegdatum",
        "Bruttobetrag",
        "Steuerausweis",
    ),
    Belegart.AUSGANGSRECHNUNG: (
        "Lieferant",
        "Belegnummer",
        "Belegdatum",
        "Bruttobetrag",
        "Steuerausweis",
    ),
    Belegart.QUITTUNG: ("Lieferant", "Belegdatum", "Bruttobetrag"),
}


def _fehlende_felder(art: Belegart, werte: dict[str, Any]) -> list[str]:
    """Pflichtfelder ohne Wert. Als Steuerangabe zählt auch ein Hinweis statt des
    Steuerausweises (§ 13b, ig. Lieferung, § 19, § 4 UStG — ``steuerkennzeichen``)."""
    vorhanden = {
        "Lieferant": werte["lieferant_name"],
        "Belegnummer": werte["belegnummer"],
        "Belegdatum": werte["belegdatum"],
        "Bruttobetrag": werte["brutto"],
        "Steuerausweis": werte["steuer"]
        if werte["steuer"] is not None
        else werte.get("steuerkennzeichen"),
    }
    return [f for f in _PFLICHTFELDER.get(art, ()) if vorhanden[f] is None]


class BelegErkenner:
    """Format → Text → Regelwerk → (optional) LLM → strukturierter Beleg.

    Ein Fehler beim Lesen (kaputtes PDF, keine OCR) wird nicht abgefangen: Die
    Pipeline legt den Beleg dann mit der Fehlermeldung in die Prüfung.
    """

    def __init__(
        self,
        ocr: OCREngine | None = None,
        llm: LLMBelegEngine | None = None,
        eigene_ust_ids: set[str] | None = None,
        eigene_firma: str | None = None,
    ) -> None:
        self.ocr = ocr if ocr is not None else TesseractEngine()
        self.llm = llm
        self.eigene_ust_ids = eigene_ust_ids or set()
        self.eigene_firma = eigene_firma

    def __call__(self, roh: RohBeleg, beleg: Beleg) -> Beleg:
        befund = erkenne_format(roh)
        unlesbar: str | None = None
        if befund.xml is not None:
            # Strukturierte Daten schlagen immer die Ansicht.
            try:
                rechnung = lies_erechnung(befund.xml)
            except ERechnungError as fehler:
                unlesbar = f"E-Rechnung ({befund.syntax}) nicht lesbar: {fehler}"
            else:
                erkannt = zu_beleg(
                    rechnung, pruefe(rechnung), beleg, self.eigene_ust_ids
                )
                if rechnung.profil.reduziert and befund.format is Format.ZUGFERD_PDF:
                    erkannt = self._mit_pdf_steuerzeilen(roh, befund, erkannt)
                return erkannt
            if befund.format is Format.ERECHNUNG_XML:
                return beleg.model_copy(
                    update={
                        "belegart": Belegart.EINGANGSRECHNUNG,
                        "status": BelegStatus.ZUR_PRUEFUNG,
                        "pruef_grund": unlesbar,
                    }
                )

        # ZUGFeRD mit kaputtem XML: die PDF-Ansicht füllt vor, der Mensch prüft.
        text, quelle = hole_text(roh, befund, self.ocr)
        if quelle == "ocr":
            text = normalisiere_ocr(text)
        erkannt = self._lies(text, beleg)
        if unlesbar:
            erkannt = erkannt.model_copy(
                update={
                    "status": BelegStatus.ZUR_PRUEFUNG,
                    "pruef_grund": "; ".join(
                        filter(None, [unlesbar, erkannt.pruef_grund])
                    ),
                }
            )
        return erkannt

    def _mit_pdf_steuerzeilen(
        self, roh: RohBeleg, befund: FormatBefund, beleg: Beleg
    ) -> Beleg:
        """MINIMUM/BASIC WL: Steuersätze aus der PDF-Ansicht, wenn deren Steuerzeilen
        zu den Summen des XML passen — der Beleg bleibt zur Prüfung."""
        try:
            text, _ = hole_text(roh, befund, None)  # ohne OCR: nur die Textebene
        except ErkennungError:
            return beleg
        extrakt = extrahiere(text)
        if not extrakt.steuerzeilen or beleg.netto is None or beleg.steuer is None:
            return beleg
        netto = sum((s.netto for s in extrakt.steuerzeilen), Decimal("0"))
        steuer = sum((s.steuer for s in extrakt.steuerzeilen), Decimal("0"))
        if abs(netto - beleg.netto) > TOLERANZ or abs(steuer - beleg.steuer) > TOLERANZ:
            return beleg
        return beleg.model_copy(
            update={
                "positionen": positionen_aus_steuerzeilen(
                    beleg.id, extrakt.steuerzeilen, extrakt.steuerkennzeichen
                ),
                "steuerkennzeichen": beleg.steuerkennzeichen
                or extrakt.steuerkennzeichen,
            }
        )

    def _lies(self, text: str, beleg: Beleg) -> Beleg:
        extrakt = extrahiere(text)
        art = erkenne_belegart(text, extrakt, self.eigene_ust_ids, self.eigene_firma)
        belegart = art.belegart

        if belegart is Belegart.KONTOAUSZUG and ist_kreditkartenabrechnung(text):
            stichtag = extrakt.belegdatum or beleg.eingegangen_am.date()
            positionen = positionen_aus_umsaetzen(
                beleg.id, zerlege_kreditkartenabrechnung(text, stichtag)
            )
        elif extrakt.steuerzeilen:
            positionen = positionen_aus_steuerzeilen(
                beleg.id, extrakt.steuerzeilen, extrakt.steuerkennzeichen
            )
        else:
            positionen = []

        werte: dict[str, Any] = {
            "belegnummer": extrakt.belegnummer,
            "belegdatum": extrakt.belegdatum,
            "leistungsdatum": extrakt.leistungsdatum,
            "lieferant_name": extrakt.lieferant_name,
            "lieferant_ust_id": extrakt.lieferant_ust_id,
            "iban": extrakt.iban,
            "netto": extrakt.netto,
            "steuer": extrakt.steuer,
            "brutto": extrakt.brutto,
            "zahlungsziel": extrakt.zahlungsziel,
            "skonto_prozent": extrakt.skonto_prozent,
            "skonto_tage": extrakt.skonto_tage,
            "steuerkennzeichen": extrakt.steuerkennzeichen,
        }
        fehlend = _fehlende_felder(belegart, werte)

        # Stufe 2: LLM füllt nur Lücken — das Regelwerk gewinnt immer.
        vom_llm: list[str] = []
        if self.llm is not None and (fehlend or belegart is Belegart.SONSTIGES):
            llm = self.llm.lies(text, extrakt)
            if llm is not None:
                if belegart is Belegart.SONSTIGES and llm.belegart is not None:
                    belegart = llm.belegart
                    vom_llm.append("Belegart")
                for feld in (
                    "belegdatum",
                    "leistungsdatum",
                    "netto",
                    "steuer",
                    "brutto",
                ):
                    if werte[feld] is None and getattr(llm, feld) is not None:
                        werte[feld] = getattr(llm, feld)
                        vom_llm.append(feld.capitalize())
                if not positionen and llm.positionen:
                    positionen = [
                        Belegposition(
                            beleg_id=beleg.id,
                            bezeichnung=p.bezeichnung,
                            menge=p.menge,
                            netto=p.netto,
                            steuersatz=p.steuersatz,
                        )
                        for p in llm.positionen
                    ]
                    vom_llm.append("Positionen")
                fehlend = _fehlende_felder(belegart, werte)

        betrag = werte["netto"] or werte["brutto"]
        if not positionen and belegart in _PFLICHTFELDER and betrag:
            positionen = [
                Belegposition(
                    beleg_id=beleg.id, bezeichnung="Gesamtbetrag", netto=betrag
                )
            ]

        gruende = []
        if belegart is Belegart.SONSTIGES:
            gruende.append("Belegart nicht erkannt")
        if fehlend:
            gruende.append("fehlt: " + ", ".join(fehlend))
        if extrakt.rechenprobe is False:
            gruende.append(
                "Rechenprobe stimmt nicht (Netto + Steuer ≠ Brutto oder Vorzeichen "
                "uneinheitlich)"
            )
        if extrakt.korrektur == "gutschrift" and extrakt.vorzeichen_gedreht:
            # § 14 Abs. 2 S. 2 UStG: „Gutschrift“ heißt auch die Abrechnung durch den
            # Leistungsempfänger — die wäre keine Minderung, sondern ein Erlös
            gruende.append(
                "Gutschrift mit positiven Beträgen als Minderung (Rechnungskorrektur) "
                "übernommen — ist es eine Abrechnung des Leistungsempfängers (§ 14 "
                "Abs. 2 S. 2 UStG), ist sie kein Aufwand: prüfen"
            )
        if vom_llm:
            gruende.append("vom LLM ergänzt, bitte prüfen: " + ", ".join(vom_llm))

        confidence = art.confidence
        if fehlend or extrakt.rechenprobe is False or vom_llm:
            confidence *= 0.5
        elif extrakt.rechenprobe:
            confidence = min(1.0, confidence + 0.05)

        return beleg.model_copy(
            update={
                **werte,
                "belegart": belegart,
                "richtung": (
                    Belegrichtung.AUSGANG
                    if belegart is Belegart.AUSGANGSRECHNUNG
                    else Belegrichtung.EINGANG
                ),
                "positionen": positionen,
                "status": BelegStatus.ZUR_PRUEFUNG if gruende else BelegStatus.ERFASST,
                "pruef_grund": "; ".join(gruende) or None,
                "confidence": round(confidence, 2),
            }
        )
