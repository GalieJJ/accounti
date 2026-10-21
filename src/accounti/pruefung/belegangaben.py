"""Was auf dem Beleg steht — Grundlage der Pflichtangaben (§ 14 Abs. 4 UStG).

Der gespeicherte Beleg kennt Lieferant, USt-IdNr., Nummer, Datum und Beträge, aber
weder die Steuernummer noch den Empfänger. Deshalb wird das Original aus dem Archiv
gelesen — in der Reihenfolge der Erfassung (Baustein 2):

1. E-Rechnung (XRechnung, ZUGFeRD): das Rechnungsmodell nach EN 16931 —
   Verkäufer mit Steuernummer (BT-32) und USt-IdNr. (BT-31), Käufer (BT-44).
2. PDF mit Textebene, Textdatei: Muster für Steuernummer, USt-IdNr., Postleitzahl
   und Ort, Leistungszeitpunkt, Steuerbefreiung.
3. Scan: nur mit OCR (``--ocr``); sonst „nicht prüfbar“.

Ohne Archiv bleibt es bei den gespeicherten Feldern (``quelle == "felder"``) — eine
fehlende Steuernummer ist dann *nicht erkannt*, nicht *nicht vorhanden*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from accounti.belege.archiv import BelegArchiv
from accounti.belege.erkennung import (
    ErkennungError,
    erkenne_format,
    hole_text,
    normalisiere_ocr,
)
from accounti.belege.extraktion import extrahiere
from accounti.belege.kanaele import RohBeleg
from accounti.belege.ocr import OCREngine
from accounti.erechnung import ERechnungError
from accounti.erechnung import lies as lies_erechnung
from accounti.models import Beleg

_I = re.IGNORECASE
_STEUERNUMMER_LABEL = re.compile(
    r"(?:\bSt(?:euer)?[\s.-]*(?:Nr|Nummer)\b|\bStNr\b)\.?\s*[:.]?\s*"
    r"(\d[\d\s/.-]{8,18}\d)",
    _I,
)
_STEUERNUMMER_FORMAT = re.compile(r"\b\d{2,3}/\d{3,4}/\d{4,5}\b")
_PLZ_ORT = re.compile(r"\b\d{5}\s+[A-ZÄÖÜ][\wäöüß.-]+")
_LEISTUNGSDATUM = re.compile(
    r"leistungsdatum|lieferdatum|liefertag|leistungszeitraum|leistungszeitpunkt|"
    r"lieferzeitraum|entspricht\s+(?:dem\s+)?rechnungsdatum|"
    r"datum\s+der\s+(?:lieferung|leistung)",
    _I,
)
_BEFREIUNG = re.compile(
    r"steuerfrei|reverse[\s-]*charge|steuerschuldnerschaft\s+des\s+"
    r"leistungsempf|§\s*13\s*b|§\s*19\s*(?:abs\.?\s*1\s*)?ustg|kleinunternehmer|"
    r"innergemeinschaftliche\s+lieferung|§\s*4\s*nr",
    _I,
)
_GUTSCHRIFT = re.compile(r"\bgutschrift\b", _I)
# Steuerkategorien ohne deutsche Steuer: Befreiung, Reverse Charge, ig. Lieferung …
_KATEGORIEN_OHNE_STEUER = {"E", "AE", "K", "G", "O", "Z"}


@dataclass
class Belegangaben:
    quelle: str  # erechnung, pdf, text, ocr, felder
    hinweis: str | None = None  # warum nicht mehr gelesen werden konnte
    leistender_name: str | None = None
    leistender_anschrift: bool | None = None  # None: nicht feststellbar
    steuernummer: str | None = None
    ust_ids: list[str] = field(default_factory=list)
    empfaenger_name: str | None = None
    empfaenger_ust_id: str | None = None
    text: str | None = None
    leistungsbeschreibung: bool | None = None
    leistungszeitpunkt: bool | None = None
    steuerbefreiung: bool = False
    gutschrift: bool = False

    @property
    def gelesen(self) -> bool:
        """Wurde das Original gelesen (nicht nur die gespeicherten Felder)?"""
        return self.quelle != "felder"


def finde_steuernummer(text: str) -> str | None:
    """Steuernummer (10–13 Ziffern) — mit Bezeichnung oder im Format 12/345/67890."""
    for m in _STEUERNUMMER_LABEL.finditer(text):
        ziffern = re.sub(r"\D", "", m.group(1))
        if 10 <= len(ziffern) <= 13:
            return m.group(1).strip()
    format_ = _STEUERNUMMER_FORMAT.search(text)
    return format_.group(0) if format_ else None


def _aus_feldern(beleg: Beleg, hinweis: str | None = None) -> Belegangaben:
    return Belegangaben(
        quelle="felder",
        hinweis=hinweis,
        leistender_name=beleg.lieferant_name,
        ust_ids=[beleg.lieferant_ust_id] if beleg.lieferant_ust_id else [],
        leistungszeitpunkt=True if beleg.leistungsdatum else None,
    )


def _aus_erechnung(xml: bytes, beleg: Beleg) -> Belegangaben | None:
    try:
        r = lies_erechnung(xml)
    except ERechnungError:
        return None
    v, k = r.verkaeufer, r.kaeufer
    return Belegangaben(
        quelle="erechnung",
        leistender_name=v.name,
        leistender_anschrift=bool(v.anschrift.plz and v.anschrift.ort),
        steuernummer=v.steuernummer,
        ust_ids=[v.ust_id] if v.ust_id else [],
        empfaenger_name=k.name,
        empfaenger_ust_id=k.ust_id,
        leistungsbeschreibung=bool(r.zeilen) and all(z.bezeichnung for z in r.zeilen),
        leistungszeitpunkt=bool(
            r.leistungsdatum or r.leistungszeitraum_von or r.leistungszeitraum_bis
        ),
        steuerbefreiung=any(
            (s.kategorie or "").upper() in _KATEGORIEN_OHNE_STEUER for s in r.steuern
        ),
        gutschrift=r.typ == "381",
    )


def _aus_text(text: str, quelle: str, beleg: Beleg) -> Belegangaben:
    extrakt = extrahiere(text)
    return Belegangaben(
        quelle=quelle,
        leistender_name=beleg.lieferant_name or extrakt.lieferant_name,
        leistender_anschrift=bool(_PLZ_ORT.search(text)),
        steuernummer=finde_steuernummer(text),
        ust_ids=list(dict.fromkeys(extrakt.ust_ids)),
        text=text,
        leistungszeitpunkt=bool(
            beleg.leistungsdatum
            or extrakt.leistungsdatum
            or _LEISTUNGSDATUM.search(text)
        ),
        steuerbefreiung=bool(_BEFREIUNG.search(text)),
        gutschrift=bool(_GUTSCHRIFT.search(text)),
    )


def lies_angaben(
    beleg: Beleg, archiv: BelegArchiv | None, ocr: OCREngine | None = None
) -> Belegangaben:
    """Angaben des Belegs — aus dem Original, wenn es im Archiv liegt."""
    if archiv is None or not archiv.enthaelt(beleg.datei_hash):
        return _aus_feldern(beleg, "Original nicht im Archiv")
    roh = RohBeleg(
        dateiname=beleg.dateiname,
        inhalt=archiv.lese(beleg.datei_hash),
        kanal=beleg.kanal,
        herkunft=beleg.herkunft,
        eingegangen_am=beleg.eingegangen_am,
    )
    befund = erkenne_format(roh)
    if befund.xml is not None:
        angaben = _aus_erechnung(befund.xml, beleg)
        if angaben is not None:
            return angaben
    try:
        text, quelle = hole_text(roh, befund, ocr)
    except ErkennungError as fehler:
        return _aus_feldern(beleg, f"{fehler} — mit --ocr prüfen")
    if quelle == "ocr":
        text = normalisiere_ocr(text)
    return _aus_text(text, quelle, beleg)
