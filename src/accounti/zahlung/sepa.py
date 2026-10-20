"""SEPA-Überweisungen als ``pain.001.001.09`` nach DK-TVS GBIC_5.

Grundlage ist Anlage 3 des DFÜ-Abkommens der Deutschen Kreditwirtschaft (Version 3.9,
für SEPA ab 05.10.2025; unverändert in Version 26.11 ab 15.11.2026): Nachricht
``pain.001.001.09``, Schema ``pain.001.001.09_GBIC_5.xsd``. Zeichensatz und
Referenzen: ``accounti.zahlung.zeichen``.

Die Datei entsteht nur aus einem freigegebenen Lauf, nach erneuter Prüfung und
Vergleich mit dem Freigabe-Hash. Sie wird im Lauf gespeichert und danach nur noch
byte-gleich ausgegeben — ein zweites Hochladen weist die Bank über die ``MsgId`` ab.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from accounti.db.repo_zahlung import lade_lauf
from accounti.models.zahlung import LaufStatus, Zahlung, Zahlungslauf
from accounti.zahlung.freigabe import (
    LaufError,
    LaufGesperrtError,
    ZustandError,
    freigabe_hash,
    markiere_eingereicht,
)
from accounti.zahlung.konfiguration import ZahlungEinstellungen
from accounti.zahlung.pruefung import pruefe_lauf
from accounti.zahlung.zeichen import referenz, sepa_text, verwendungszweck

__all__ = [
    "PAIN_001",
    "erzeuge_datei",
    "leere_felder",
    "msg_id",
    "referenz",
    "schreibe_pain001",
    "sepa_text",
    "verwendungszweck",
]

# --- pain.001.001.09 ----------------------------------------------------------------

PAIN_001 = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"
_HAUSNUMMER = re.compile(
    r"^(?P<strasse>.*?\D)\s*(?P<nr>\d+\s*[A-Za-z]?(?:\s*[-/]\s*\d+\s*[A-Za-z]?)?)$"
)


def msg_id(lauf: Zahlungslauf, erstellt: datetime) -> str:
    """Je Datei neu — die Bank erkennt daran doppelt eingereichte Dateien."""
    return referenz(f"ACCOUNTI-{lauf.nr}-{erstellt:%Y%m%d%H%M%S}")


def _knoten(eltern: ET.Element, name: str, text: str | None = None) -> ET.Element:
    knoten = ET.SubElement(eltern, f"{{{PAIN_001}}}{name}")
    if text is not None:
        knoten.text = text
    return knoten


def _pfad(eltern: ET.Element, pfad: str, text: str) -> ET.Element:
    """``Id/IBAN`` → verschachtelte Knoten, Text im letzten."""
    knoten = eltern
    for name in pfad.split("/"):
        knoten = _knoten(knoten, name)
    knoten.text = text
    return knoten


def _betrag(wert: Decimal) -> str:
    return f"{wert.quantize(Decimal('0.01')):.2f}"


def _anschrift(eltern: ET.Element, z: Zahlung) -> None:
    """Strukturierte Anschrift (TwnNm, Ctry Pflicht) — nur wenn der Ort bekannt ist."""
    ort = sepa_text(z.ort, 35)
    land = (z.land or z.iban[:2]).upper()
    if not ort or not re.fullmatch(r"[A-Z]{2}", land):
        return
    adresse = _knoten(eltern, "PstlAdr")
    strasse = (z.strasse or "").strip()
    treffer = _HAUSNUMMER.match(strasse)
    if treffer:
        _knoten(adresse, "StrtNm", sepa_text(treffer["strasse"], 70))
        _knoten(adresse, "BldgNb", sepa_text(treffer["nr"].replace(" ", ""), 16))
    elif sepa_text(strasse, 70):
        _knoten(adresse, "StrtNm", sepa_text(strasse, 70))
    if sepa_text(z.plz, 16):
        _knoten(adresse, "PstCd", sepa_text(z.plz, 16))
    _knoten(adresse, "TwnNm", ort)
    _knoten(adresse, "Ctry", land)


def schreibe_pain001(
    lauf: Zahlungslauf, erstellt: datetime, einzelbuchung: bool = True
) -> bytes:
    """SEPA-Sammelüberweisung (ein ``PmtInf``, je Zahlung ein ``CdtTrfTxInf``).

    ``einzelbuchung`` schreibt ``BtchBookg=false``: Jede Überweisung erscheint einzeln
    auf dem Kontoauszug — sofern die Bank das mit dem Kunden vereinbart hat.
    """
    ET.register_namespace("", PAIN_001)
    anzahl = str(len(lauf.zahlungen))
    summe = _betrag(sum((z.betrag for z in lauf.zahlungen), Decimal("0")))
    name = sepa_text(lauf.auftraggeber_name, 70)

    dokument = ET.Element(f"{{{PAIN_001}}}Document")
    auftrag = _knoten(dokument, "CstmrCdtTrfInitn")
    kopf = _knoten(auftrag, "GrpHdr")
    _knoten(kopf, "MsgId", msg_id(lauf, erstellt))
    _knoten(kopf, "CreDtTm", erstellt.isoformat(timespec="seconds"))
    _knoten(kopf, "NbOfTxs", anzahl)
    _knoten(kopf, "CtrlSum", summe)
    _pfad(kopf, "InitgPty/Nm", name)

    info = _knoten(auftrag, "PmtInf")
    _knoten(info, "PmtInfId", referenz(f"ACCOUNTI-{lauf.nr}"))
    _knoten(info, "PmtMtd", "TRF")
    _knoten(info, "BtchBookg", "false" if einzelbuchung else "true")
    _knoten(info, "NbOfTxs", anzahl)
    _knoten(info, "CtrlSum", summe)
    _pfad(info, "PmtTpInf/SvcLvl/Cd", "SEPA")
    _pfad(info, "ReqdExctnDt/Dt", lauf.ausfuehrung.isoformat())
    _pfad(info, "Dbtr/Nm", name)
    _pfad(info, "DbtrAcct/Id/IBAN", lauf.auftraggeber_iban)
    institut = _knoten(_knoten(info, "DbtrAgt"), "FinInstnId")
    if lauf.auftraggeber_bic:
        _knoten(institut, "BICFI", lauf.auftraggeber_bic)
    else:
        _pfad(institut, "Othr/Id", "NOTPROVIDED")
    _knoten(info, "ChrgBr", "SLEV")

    for z in lauf.zahlungen:
        tx = _knoten(info, "CdtTrfTxInf")
        _pfad(tx, "PmtId/EndToEndId", z.end_to_end_id or "NOTPROVIDED")
        _pfad(tx, "Amt/InstdAmt", _betrag(z.betrag)).set("Ccy", "EUR")
        empfaenger = _knoten(tx, "Cdtr")
        _knoten(empfaenger, "Nm", sepa_text(z.empfaenger, 70))
        _anschrift(empfaenger, z)
        _pfad(tx, "CdtrAcct/Id/IBAN", z.iban)
        _pfad(tx, "RmtInf/Ustrd", sepa_text(z.verwendungszweck, 140))

    ET.indent(dokument, space="  ")
    text = ET.tostring(dokument, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + text + "\n").encode("utf-8")


def leere_felder(xml: bytes) -> list[str]:
    """Pfade aller Elemente ohne Inhalt — das Schema verlangt überall mindestens ein
    Zeichen. Letzte Sicherung, bevor eine Datei den Lauf auf „eingereicht“ setzt."""

    def name(knoten: ET.Element) -> str:
        return knoten.tag.rpartition("}")[2]

    def suche(knoten: ET.Element, pfad: str) -> list[str]:
        kinder = list(knoten)
        if not kinder:
            return [] if (knoten.text or "").strip() else [pfad]
        leer = []
        for kind in kinder:
            gleiche = [k for k in kinder if k.tag == kind.tag]
            stelle = f"[{gleiche.index(kind) + 1}]" if len(gleiche) > 1 else ""
            unterpfad = f"{pfad}/{name(kind)}{stelle}" if pfad else name(kind) + stelle
            leer += suche(kind, unterpfad)
        return leer

    return suche(ET.fromstring(xml), "")


def erzeuge_datei(
    session: Session,
    lauf_nr: int,
    einstellungen: ZahlungEinstellungen,
    person: str,
    heute: date,
    jetzt: datetime | None = None,
) -> tuple[Zahlungslauf, bytes, bool]:
    """Die SEPA-Datei eines Laufs: ``(Lauf, Datei, neu erzeugt?)``.

    Aus einem freigegebenen Lauf wird sie nach erneuter Prüfung erzeugt, gespeichert
    und der Lauf als eingereicht markiert. Danach gibt es nur noch die gespeicherte
    Datei, byte-gleich.
    """
    lauf = lade_lauf(session, lauf_nr)
    if lauf.datei is not None and lauf.status in (
        LaufStatus.EINGEREICHT,
        LaufStatus.AUSGEFUEHRT,
    ):
        gespeichert = lauf.datei.encode("utf-8")
        if hashlib.sha256(gespeichert).hexdigest() != lauf.datei_hash:
            msg = (
                f"Die gespeicherte SEPA-Datei von Lauf {lauf.nr} weicht vom "
                f"protokollierten SHA-256 ab ({lauf.datei_hash}) — nicht hochladen, "
                "die Datenbank wurde verändert"
            )
            raise LaufError(msg)
        return lauf, gespeichert, False
    if lauf.status is LaufStatus.ENTWURF:
        msg = (
            f"Lauf {lauf.nr} ist ein Entwurf — erst freigeben "
            f"(accounti zahlung freigeben {lauf.nr})"
        )
        raise ZustandError(msg)
    if lauf.status is not LaufStatus.FREIGEGEBEN:
        msg = f"Lauf {lauf.nr} ist {lauf.status.value} — keine Datei"
        raise ZustandError(msg)
    if freigabe_hash(lauf) != lauf.freigabe_hash:
        msg = (
            f"Lauf {lauf.nr} wurde seit der Freigabe verändert — keine Datei; "
            "stornieren und neu anlegen"
        )
        raise LaufError(msg)
    ergebnis = pruefe_lauf(session, lauf, einstellungen, heute)
    if not ergebnis.ok:
        raise LaufGesperrtError(ergebnis)
    erstellt = (jetzt or datetime.now()).replace(microsecond=0)
    xml = schreibe_pain001(lauf, erstellt, einstellungen.einzelbuchung)
    leer = leere_felder(xml)
    if leer:
        msg = (
            f"Lauf {lauf.nr}: SEPA-Datei unvollständig, leer: {', '.join(leer)} — "
            "keine Datei, der Lauf bleibt freigegeben"
        )
        raise LaufError(msg)
    lauf = markiere_eingereicht(
        session, lauf, person, xml.decode("utf-8"), msg_id(lauf, erstellt), erstellt
    )
    return lauf, xml, True
