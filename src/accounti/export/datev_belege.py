"""Belegbilder mit Verknüpfung zum Buchungssatz — DATEV-Belegpaket und Buchungsstapel.

Zwei Dateien für denselben Zeitraum und dieselben freigegebenen Buchungen:

* **Belegpaket** (ZIP, nicht verschachtelt) für DATEV Belegtransfer / Unternehmen
  online: ``document.xml`` nach ``Document_v060.xsd`` (DATEV XML-Schnittstelle online
  6.0) und je Beleg die Originaldatei aus dem Archiv. Jedes Dokument trägt als ``guid``
  die Beleg-ID und ``processID="2"`` (archivierungsrelevant: Ablage im Ordner statt im
  Posteingang, damit der Beleg nicht ein zweites Mal gebucht wird).
* **Buchungsstapel** (EXTF, Version 13, alle 125 Felder) mit Feld 20 „Beleglink“
  ``BEDI "<GUID>"`` — darüber hängt DATEV den Beleg an den Buchungssatz.

Der Beleg einer Buchung ist ihr ``beleg_id`` oder — bei Bankbuchungen — der Beleg aus
einem bestätigten Belegabgleich ihrer Transaktion. Was DATEV nicht annehmen würde
(fehlende Archivdatei, nicht unterstütztes Format, Datei über 20 MB), wird nicht
verknüpft und als Befund gemeldet; die Buchung geht trotzdem in den Stapel.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path, PurePath
from uuid import UUID
from xml.sax.saxutils import quoteattr

from sqlalchemy.orm import Session

from accounti.belege.archiv import BelegArchiv
from accounti.db.repository import lade_abgleiche, lade_belege, lade_buchungen
from accounti.export.datev_felder import BUCHUNGSSTAPEL
from accounti.export.datev_format import (
    Kopf,
    Wert,
    belegfeld1,
    feldnummer,
    kontoart,
    schreibe_extf,
)
from accounti.export.datev_stammdaten import DatevMandant
from accounti.models import AbgleichStatus, Beleg, Belegart, Buchungssatz, BuchungStatus

FREIGEGEBEN = {
    BuchungStatus.AUTO_GEBUCHT,
    BuchungStatus.GEPRUEFT,
    BuchungStatus.KORRIGIERT,
    BuchungStatus.EXPORTIERT,
}
FORMATE = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".xml"}
MAX_DATEI = 20 * 1024 * 1024  # je Datei
MAX_PAKET = 465 * 1024 * 1024  # je Belegpaket
MAX_DOKUMENTE = 4999  # je document.xml
NAMESPACE = "http://xml.datev.de/bedi/tps/document/v06.0"
MONATE = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]
_STEUERZEICHEN = re.compile(r"[\x00-\x1f\x7f]")


class BelegexportError(RuntimeError):
    """Das Belegpaket lässt sich so nicht bilden (DATEV-Grenzen)."""


@dataclass
class Belegexport:
    zip_pfad: Path | None  # None: keine verknüpfbaren Belege, kein Paket
    stapel_pfad: Path
    buchungen: int = 0
    belege: int = 0
    verknuepft: int = 0
    befunde: list[str] = field(default_factory=list)


def guid(beleg_id: UUID) -> str:
    """GUID des Dokuments: die Beleg-ID, groß geschrieben (DATEV-Muster 8-4-4-4-12)."""
    return str(beleg_id).upper()


def beleglink(beleg_id: UUID) -> str:
    return f'BEDI "{guid(beleg_id)}"'


def _text(text: str, laenge: int) -> str:
    """Beschreibung: 1–40 Zeichen (``p10052`` in ``Document_types_v060.xsd``)."""
    return _STEUERZEICHEN.sub(" ", text).strip()[:laenge].strip()


def _document_xml(
    dokumente: list[tuple[Beleg, str]], mandant: DatevMandant, erzeugt_am: datetime
) -> bytes:
    zeilen = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<archive xmlns="{NAMESPACE}" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xsi:schemaLocation="{NAMESPACE} Document_v060.xsd" version="6.0" '
        'generatingSystem="accounti">',
        "  <header>",
        f"    <date>{erzeugt_am:%Y-%m-%dT%H:%M:%S}</date>",
        f"    <consultantNumber>{mandant.berater}</consultantNumber>",
        f"    <clientNumber>{mandant.mandant}</clientNumber>",
        "  </header>",
        "  <content>",
    ]
    for beleg, dateiname in dokumente:
        typ = {
            Belegart.EINGANGSRECHNUNG: ' type="1"',
            Belegart.AUSGANGSRECHNUNG: ' type="2"',
        }.get(beleg.belegart, "")
        datum = beleg.belegdatum or beleg.eingegangen_am.date()
        beschreibung = _text(
            " ".join(t for t in [beleg.belegnummer, beleg.lieferant_name] if t), 40
        )
        zeilen.append(f'    <document guid="{guid(beleg.id)}"{typ} processID="2">')
        if beschreibung:
            zeilen.append(f"      <description>{_xml(beschreibung)}</description>")
        zeilen += [
            f'      <extension xsi:type="File" name={quoteattr(dateiname)}/>',
            "      <repository>",
            '        <level id="1" name="accounti"/>',
            f'        <level id="2" name="Belege {datum:%Y}"/>',
            f'        <level id="3" name="{datum:%m} {MONATE[datum.month - 1]}"/>',
            "      </repository>",
            "    </document>",
        ]
    zeilen += ["  </content>", "</archive>", ""]
    return "\n".join(zeilen).encode("utf-8")


def _xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


_F = {
    "umsatz": feldnummer(BUCHUNGSSTAPEL, "Umsatz (ohne Soll/Haben-Kz)"),
    "sh": feldnummer(BUCHUNGSSTAPEL, "Soll/Haben-Kennzeichen"),
    "konto": feldnummer(BUCHUNGSSTAPEL, "Konto"),
    "gegenkonto": feldnummer(BUCHUNGSSTAPEL, "Gegenkonto (ohne BU-Schlüssel)"),
    "bu": feldnummer(BUCHUNGSSTAPEL, "BU-Schlüssel"),
    "belegdatum": feldnummer(BUCHUNGSSTAPEL, "Belegdatum"),
    "belegfeld1": feldnummer(BUCHUNGSSTAPEL, "Belegfeld 1"),
    "text": feldnummer(BUCHUNGSSTAPEL, "Buchungstext"),
    "beleglink": feldnummer(BUCHUNGSSTAPEL, "Beleglink"),
    "kost1": feldnummer(BUCHUNGSSTAPEL, "KOST1 - Kostenstelle"),
}


def buchungsstapel_satz(b: Buchungssatz, link: str | None) -> dict[int, Wert]:
    """Ein Buchungssatz im Buchungsstapel; Umsatz brutto wie im vorhandenen Export."""
    umsatz = abs(b.betrag_netto) + (abs(b.steuer_betrag) if b.steuer_betrag else 0)
    return {
        _F["umsatz"]: Decimal(umsatz),
        _F["sh"]: "S",
        _F["konto"]: b.soll_konto,
        _F["gegenkonto"]: b.haben_konto,
        _F["bu"]: str(b.steuer_schluessel) if b.steuer_schluessel is not None else None,
        _F["belegdatum"]: b.datum,
        _F["belegfeld1"]: belegfeld1(b.beleg_nummer),
        _F["text"]: b.buchungstext[:60],
        _F["beleglink"]: link,
        _F["kost1"]: b.kostenstelle,
    }


def exportiere_belegpaket(
    session: Session,
    archiv: BelegArchiv,
    mandant: DatevMandant,
    von: date,
    bis: date,
    zip_pfad: str | Path,
    erzeugt_am: datetime | None = None,
    alle: bool = False,
) -> Belegexport:
    """Belegpaket und Buchungsstapel mit Beleglink für ``von``–``bis``."""
    if von.year != bis.year or von > bis:
        raise BelegexportError(
            "Zeitraum muss in einem Kalenderjahr liegen (DATEV-Kopf)"
        )
    erzeugt_am = erzeugt_am or datetime.now()
    zip_pfad = Path(zip_pfad)
    stapel_pfad = zip_pfad.with_name(
        f"EXTF_Buchungsstapel_{von:%Y%m%d}_{bis:%Y%m%d}_Beleglink.csv"
    )
    buchungen = sorted(
        (
            b
            for b in lade_buchungen(session, status=None if alle else FREIGEGEBEN)
            if von <= b.datum <= bis
        ),
        key=lambda b: (b.datum, b.beleg_nummer or "", str(b.id)),
    )
    belege = {b.id: b for b in lade_belege(session)}
    abgeglichen = {
        a.transaktion_id: a.beleg_id
        for a in lade_abgleiche(session, status={AbgleichStatus.BESTAETIGT})
    }
    ergebnis = Belegexport(zip_pfad=zip_pfad, stapel_pfad=stapel_pfad)
    dateien: dict[UUID, tuple[Beleg, str, bytes]] = {}
    abgelehnt: set[UUID] = set()
    saetze = []
    angepasst: list[str] = []
    for b in buchungen:
        if b.beleg_nummer and belegfeld1(b.beleg_nummer) != b.beleg_nummer:
            angepasst.append(f"{b.beleg_nummer!r} → {belegfeld1(b.beleg_nummer)!r}")
        beleg_id = b.beleg_id
        if beleg_id is None and b.transaktion_id is not None:
            beleg_id = abgeglichen.get(b.transaktion_id)
        link = None
        if beleg_id is not None and beleg_id in belege and beleg_id not in abgelehnt:
            if beleg_id not in dateien:
                grund = _pruefe(belege[beleg_id], archiv)
                if grund is None:
                    beleg = belege[beleg_id]
                    endung = PurePath(beleg.dateiname).suffix.lower()
                    inhalt = archiv.lese(beleg.datei_hash)
                    dateien[beleg_id] = (
                        beleg,
                        f"{beleg_id.hex.upper()}{endung}",
                        inhalt,
                    )
                else:
                    abgelehnt.add(beleg_id)
                    ergebnis.befunde.append(
                        f"Buchung {b.beleg_nummer or str(b.id)[:8]}: {grund} — ohne "
                        "Beleglink exportiert"
                    )
            if beleg_id in dateien:
                link = beleglink(beleg_id)
                ergebnis.verknuepft += 1
        for konto in (b.soll_konto, b.haben_konto):
            if kontoart(konto, mandant.sachkontenlaenge) is None:
                ergebnis.befunde.append(
                    f"Buchung {b.beleg_nummer or str(b.id)[:8]}: Konto {konto} passt "
                    f"nicht zur Sachkontenlänge {mandant.sachkontenlaenge}"
                )
        saetze.append(buchungsstapel_satz(b, link))
    if angepasst:
        beispiele = ", ".join(angepasst[:3]) + (" …" if len(angepasst) > 3 else "")
        ergebnis.befunde.append(
            f"Belegfeld 1: {len(angepasst)} Belegnummer(n) auf DATEVs Zeichenvorrat "
            f"gekürzt ({beispiele}) — OPOS-Ausgleich in DATEV prüfen"
        )

    if len(dateien) > MAX_DOKUMENTE:
        msg = (
            f"Belegpaket mit {len(dateien)} Belegen — DATEV nimmt höchstens "
            f"{MAX_DOKUMENTE} Dokumente je Paket; Zeitraum teilen"
        )
        raise BelegexportError(msg)
    if sum(len(d[2]) for d in dateien.values()) > MAX_PAKET:
        raise BelegexportError("Belegpaket größer als 465 MB — Zeitraum teilen")

    zip_pfad.parent.mkdir(parents=True, exist_ok=True)
    if not dateien:
        # Document_v060.xsd verlangt mindestens ein Dokument
        ergebnis.zip_pfad = None
        zip_pfad.unlink(missing_ok=True)
    else:
        _schreibe_paket(zip_pfad, dateien, mandant, erzeugt_am)

    kopf = Kopf(
        kategorie=21,
        formatname="Buchungsstapel",
        formatversion=13,
        berater=mandant.berater,
        mandant=mandant.mandant,
        wj_beginn=mandant.wj_beginn,
        sachkontenlaenge=mandant.sachkontenlaenge,
        datum_von=von,
        datum_bis=bis,
        bezeichnung=f"accounti Belege {von:%Y-%m}"[:30],
        buchungstyp=1,
        rechnungslegungszweck=0,
        festschreibung=0,
        waehrung="EUR",
        skr=mandant.skr,
        erzeugt_am=erzeugt_am,
    )
    stapel_pfad.write_bytes(
        schreibe_extf(kopf, BUCHUNGSSTAPEL, saetze, {_F["belegdatum"]: "%d%m"})
    )
    ergebnis.buchungen = len(saetze)
    ergebnis.belege = len(dateien)
    return ergebnis


def _schreibe_paket(
    zip_pfad: Path,
    dateien: dict[UUID, tuple[Beleg, str, bytes]],
    mandant: DatevMandant,
    erzeugt_am: datetime,
) -> None:
    """ZIP ohne Unterordner: ``document.xml`` und die Belegdateien."""
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "document.xml",
            _document_xml(
                [(beleg, name) for beleg, name, _ in dateien.values()],
                mandant,
                erzeugt_am,
            ),
        )
        for _beleg, name, inhalt in dateien.values():
            z.writestr(name, inhalt)
    zip_pfad.write_bytes(puffer.getvalue())


def _pruefe(beleg: Beleg, archiv: BelegArchiv) -> str | None:
    """Grund, warum DATEV den Beleg nicht annähme — sonst None."""
    endung = PurePath(beleg.dateiname).suffix.lower()
    if endung not in FORMATE:
        return f"Format {endung or 'ohne Endung'} nimmt DATEV Belege online nicht an"
    if not archiv.enthaelt(beleg.datei_hash):
        return f"Belegdatei {beleg.dateiname} ist nicht im Archiv"
    if archiv.pfad(beleg.datei_hash).stat().st_size > MAX_DATEI:
        return f"Belegdatei {beleg.dateiname} ist größer als 20 MB"
    return None
