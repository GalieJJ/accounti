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
from accounti.erechnung.kosit import KositErgebnis
from accounti.erechnung.validierung import Befund, Schwere, pruefe
from accounti.konfiguration import Firma
from accounti.models import (
    Ausgangsrechnung,
    AusgangsrechnungStatus,
    Beleg,
    Belegart,
    Belegrichtung,
)


class FormalerPruefer(Protocol):
    def pruefe(self, xml: bytes, name: str = ...) -> KositErgebnis: ...


class AusstellungError(RuntimeError):
    def __init__(
        self,
        text: str,
        befunde: list[Befund] | None = None,
        kosit: KositErgebnis | None = None,
    ) -> None:
        super().__init__(text)
        self.befunde = befunde or []
        self.kosit = kosit


@dataclass
class AusstellErgebnis:
    rechnung: Ausgangsrechnung
    xml: bytes
    beleg: Beleg
    befunde: list[Befund] = field(default_factory=list)
    kosit: KositErgebnis | None = None


def stelle_aus(
    session: Session,
    archiv: BelegArchiv,
    schluessel: str,
    firma: Firma,
    rechnungsdatum: date,
    kosit: FormalerPruefer | None = None,
) -> AusstellErgebnis:
    """Stellt einen Entwurf aus. ``kosit=None`` überspringt die formale Prüfung."""
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

    datei_hash = archiv.ablegen(xml, ".xml")
    jetzt = datetime.now()
    beleg = zu_beleg(
        gelesen,
        befunde,
        Beleg(
            datei_hash=datei_hash,
            dateiname=f"{nummer}.xml",
            kanal="rechnung",
            herkunft=f"accounti rechnung ausstellen {nummer}",
            eingegangen_am=jetzt,
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
    )
    return AusstellErgebnis(
        rechnung=lade_ausgangsrechnung(session, nummer),
        xml=xml,
        beleg=beleg,
        befunde=befunde,
        kosit=kosit_ergebnis,
    )
