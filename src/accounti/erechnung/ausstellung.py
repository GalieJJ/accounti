"""Ausstellen einer Ausgangsrechnung — Nummer, E-Rechnung, Prüfung, Archiv, Beleg.

Alles läuft in der Transaktion des Aufrufers: Scheitert eine Prüfung, wirft
`stelle_aus` einen `AusstellungError`, der Aufrufer rollt zurück, und die
Rechnungsnummer ist wieder frei. So bleibt der Nummernkreis lückenlos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from accounti.belege.archiv import BelegArchiv, aufbewahrungsende
from accounti.db.repository import (
    lade_ausgangsrechnung,
    markiere_ausgestellt,
    naechste_nummer,
    speichere_beleg,
)
from accounti.erechnung import lies
from accounti.erechnung.abbildung import zu_beleg
from accounti.erechnung.erzeuger.aufbau import baue_rechnung
from accounti.erechnung.erzeuger.cii import schreibe_cii
from accounti.erechnung.erzeuger.zugferd import schreibe_zugferd
from accounti.erechnung.kosit import KositErgebnis
from accounti.erechnung.mustang import MustangErgebnis
from accounti.erechnung.validierung import Befund, Schwere, pruefe
from accounti.konfiguration import Firma
from accounti.kontakte.ustid import (
    USTID_KATEGORIEN,
    Bewertung,
    aktuelle_bestaetigung,
)
from accounti.models import (
    Ausgangsrechnung,
    AusgangsrechnungStatus,
    Beleg,
    Belegart,
    Belegrichtung,
)

_STEUERFALL = {
    "K": "steuerfreie innergemeinschaftliche Lieferung",
    "AE": "Rechnung mit Reverse Charge",
}


class FormalerPruefer(Protocol):
    def pruefe(self, xml: bytes, name: str = ...) -> KositErgebnis: ...


class PdfPruefer(Protocol):
    def pruefe(self, pdf: bytes, name: str = ...) -> MustangErgebnis: ...


class AusstellungError(RuntimeError):
    def __init__(
        self,
        text: str,
        befunde: list[Befund] | None = None,
        kosit: KositErgebnis | None = None,
        mustang: MustangErgebnis | None = None,
    ) -> None:
        super().__init__(text)
        self.befunde = befunde or []
        self.kosit = kosit
        self.mustang = mustang


@dataclass
class AusstellErgebnis:
    rechnung: Ausgangsrechnung
    xml: bytes
    pdf: bytes
    beleg: Beleg
    befunde: list[Befund] = field(default_factory=list)
    kosit: KositErgebnis | None = None
    mustang: MustangErgebnis | None = None
    ustid: Bewertung | None = None  # nur bei K/AE: Bestätigung der Kunden-USt-IdNr.


def stelle_aus(
    session: Session,
    archiv: BelegArchiv,
    schluessel: str,
    firma: Firma,
    rechnungsdatum: date,
    kosit: FormalerPruefer | None = None,
    pdf_pruefer: PdfPruefer | None = None,
    erstellt_am: datetime | None = None,
    ustid_max_alter_tage: int = 30,
) -> AusstellErgebnis:
    """Stellt einen Entwurf aus: XRechnung und ZUGFeRD-PDF.

    ``kosit`` prüft das XML, ``pdf_pruefer`` das PDF formal; ``None`` überspringt
    die jeweilige Prüfung. Steuerfreie EU-Rechnungen (K, AE) brauchen eine
    qualifizierte Bestätigung der Kunden-USt-IdNr. im Protokoll, höchstens
    ``ustid_max_alter_tage`` vor dem Rechnungsdatum.
    """
    entwurf = lade_ausgangsrechnung(session, schluessel)
    if entwurf.status is not AusgangsrechnungStatus.ENTWURF:
        msg = f"Rechnung {entwurf.nummer} ist bereits ausgestellt."
        raise AusstellungError(msg)

    laufend = naechste_nummer(session, firma.nummernkreis, rechnungsdatum.year)
    nummer = firma.nummer(rechnungsdatum.year, laufend)
    try:
        rechnung = baue_rechnung(entwurf, firma, nummer, rechnungsdatum)
    except ValueError as fehler:
        raise AusstellungError(str(fehler)) from fehler

    # 0 % nur mit bestätigter USt-IdNr. (§ 6a Abs. 1 Nr. 4, § 18e UStG)
    ustid = None
    kategorien = {s.kategorie for s in rechnung.steuern}
    steuerfaelle = sorted(k for k in USTID_KATEGORIEN if k in kategorien)
    if steuerfaelle:
        ust_id = entwurf.kunde.ust_id
        ustid = aktuelle_bestaetigung(
            session, ust_id, rechnungsdatum, ustid_max_alter_tage
        )
        if not ustid.bestaetigt:
            ohne = " und ".join(_STEUERFALL[k] for k in steuerfaelle)
            msg = (
                f"USt-IdNr. {ust_id or '—'} des Kunden nicht bestätigt: {ustid.grund}. "
                f"Ohne qualifizierte Bestätigung des BZSt keine {ohne}."
            )
            raise AusstellungError(msg)

    xml = schreibe_cii(rechnung)

    # Was wir anderen schicken, muss den Maßstab bestehen, den wir an andere anlegen:
    # dieselbe Prüfung wie im Eingang, auf das tatsächlich erzeugte XML.
    gelesen = lies(xml)
    befunde = pruefe(gelesen)
    fachfehler = [b for b in befunde if b.schwere is Schwere.FEHLER]
    if fachfehler:
        msg = "Fachliche Prüfung: " + "; ".join(str(b) for b in fachfehler)
        raise AusstellungError(msg, befunde=befunde)

    kosit_ergebnis = None
    if kosit is not None:
        kosit_ergebnis = kosit.pruefe(xml, f"{nummer}.xml")
        if not kosit_ergebnis.akzeptiert:
            gruende = "; ".join(str(m) for m in kosit_ergebnis.fehler) or "abgelehnt"
            msg = f"KoSIT-Prüftool: {gruende}"
            raise AusstellungError(msg, befunde=befunde, kosit=kosit_ergebnis)

    jetzt = erstellt_am or datetime.now().astimezone()
    pdf = schreibe_zugferd(rechnung, xml, jetzt)
    mustang_ergebnis = None
    if pdf_pruefer is not None:
        mustang_ergebnis = pdf_pruefer.pruefe(pdf, f"{nummer}.pdf")
        if not mustang_ergebnis.gueltig:
            gruende = "; ".join(mustang_ergebnis.meldungen) or "abgelehnt"
            msg = f"ZUGFeRD-PDF (Mustang/veraPDF): {gruende}"
            raise AusstellungError(
                msg, befunde=befunde, kosit=kosit_ergebnis, mustang=mustang_ergebnis
            )

    datei_hash = archiv.ablegen(xml, ".xml")
    pdf_hash = archiv.ablegen(pdf, ".pdf")
    beleg = zu_beleg(
        gelesen,
        befunde,
        Beleg(
            datei_hash=datei_hash,
            dateiname=f"{nummer}.xml",
            kanal="rechnung",
            herkunft=f"accounti rechnung ausstellen {nummer}",
            eingegangen_am=jetzt.replace(tzinfo=None),
            aufbewahren_bis=aufbewahrungsende(rechnungsdatum),
        ),
    ).model_copy(
        update={
            "belegart": Belegart.AUSGANGSRECHNUNG,
            "richtung": Belegrichtung.AUSGANG,
        }
    )
    speichere_beleg(session, beleg)
    markiere_ausgestellt(
        session,
        entwurf.id,
        nummer=nummer,
        rechnungsdatum=rechnungsdatum,
        zahlungsziel=rechnung.faellig,
        beleg_id=beleg.id,
        datei_hash=datei_hash,
        pdf_hash=pdf_hash,
    )
    return AusstellErgebnis(
        rechnung=lade_ausgangsrechnung(session, nummer),
        xml=xml,
        pdf=pdf,
        beleg=beleg,
        befunde=befunde,
        kosit=kosit_ergebnis,
        mustang=mustang_ergebnis,
        ustid=ustid,
    )
