"""Ausstellen einer Ausgangsrechnung — Nummer, E-Rechnung, Prüfung, Archiv, Beleg.

Alles läuft in der Transaktion des Aufrufers: Scheitert eine Prüfung, wirft
`stelle_aus` einen `AusstellungError`, der Aufrufer rollt zurück, und die
Rechnungsnummer ist wieder frei. So bleibt der Nummernkreis lückenlos.

Das Rechnungsdatum ist das Ausstellungsdatum (§ 14 Abs. 4 Satz 1 Nr. 3 UStG): nie in
der Zukunft und nie in einem festgeschriebenen Monat — geprüft, bevor eine Nummer
vergeben wird. Ein Nummernformat ohne ``{jahr}`` zählt über den Jahreswechsel weiter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from accounti.belege.archiv import BelegArchiv, aufbewahrungsende
from accounti.db.repository import (
    JAHRESUEBERGREIFEND,
    lade_ausgangsrechnung,
    markiere_ausgestellt,
    naechste_nummer,
    nummer_vergeben,
    speichere_beleg,
)
from accounti.db.tabellen_pruefung import sperrfehler
from accounti.erechnung import lies
from accounti.erechnung.abbildung import zu_beleg
from accounti.erechnung.erzeuger.aufbau import baue_rechnung
from accounti.erechnung.erzeuger.cii import schreibe_cii
from accounti.erechnung.erzeuger.zugferd import schreibe_zugferd
from accounti.erechnung.kosit import KositErgebnis
from accounti.erechnung.modell import Profil, Rechnung
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
from accounti.steuer.leistungszeitpunkt import steuertag

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
    hinweise: list[str] = field(default_factory=list)


def _pruefe_datum(session: Session, rechnungsdatum: date, heute: date) -> None:
    if rechnungsdatum > heute:
        msg = (
            f"Rechnungsdatum {rechnungsdatum:%d.%m.%Y} liegt in der Zukunft — das "
            "Rechnungsdatum ist das Ausstellungsdatum (§ 14 Abs. 4 Satz 1 Nr. 3 UStG)"
        )
        raise AusstellungError(msg)
    if (fehler := sperrfehler(session.connection(), rechnungsdatum)) is not None:
        msg = (
            f"Rechnungsdatum {rechnungsdatum:%d.%m.%Y}: in einen festgeschriebenen "
            f"Zeitraum wird keine Rechnung ausgestellt ({fehler}) — mit dem heutigen "
            "Datum ausstellen"
        )
        raise AusstellungError(msg)


def _vorgaenger(
    session: Session, entwurf: Ausgangsrechnung, rechnungsdatum: date
) -> date | None:
    """Datum der Rechnung, auf die sich eine Gutschrift/Korrektur bezieht (BT-26)."""
    nummer = entwurf.korrektur_zu
    if not nummer:
        return None
    try:
        ursprung = lade_ausgangsrechnung(session, nummer)
    except ValueError as fehler:
        msg = f"Rechnung {nummer}, auf die sich die Korrektur bezieht, gibt es nicht"
        raise AusstellungError(msg) from fehler
    if (
        ursprung.status is not AusgangsrechnungStatus.AUSGESTELLT
        or ursprung.rechnungsdatum is None
    ):
        msg = f"Rechnung {nummer} ist noch nicht ausgestellt"
        raise AusstellungError(msg)
    if rechnungsdatum < ursprung.rechnungsdatum:
        msg = (
            f"Die Korrektur vom {rechnungsdatum:%d.%m.%Y} läge vor der Rechnung "
            f"{nummer} vom {ursprung.rechnungsdatum:%d.%m.%Y}"
        )
        raise AusstellungError(msg)
    return ursprung.rechnungsdatum


def _nummer(session: Session, firma: Firma, rechnungsdatum: date) -> str:
    """Nächste freie Nummer; ohne ``{jahr}`` im Format ein jahresübergreifender Kreis.

    Eine schon vergebene Nummer (etwa nach einem Wechsel des Formats) wird
    übersprungen — sie ist ja belegt, also keine Lücke.
    """
    jahr = rechnungsdatum.year if firma.nummer_je_jahr else JAHRESUEBERGREIFEND
    for _ in range(10_000):
        nummer = firma.nummer(
            rechnungsdatum.year, naechste_nummer(session, firma.nummernkreis, jahr)
        )
        if not nummer_vergeben(session, nummer):
            return nummer
    msg = "Keine freie Rechnungsnummer — Nummernformat prüfen"  # pragma: no cover
    raise AusstellungError(msg)  # pragma: no cover


def _hinweise(session: Session, entwurf: Ausgangsrechnung, r: Rechnung) -> list[str]:
    """Liegt der umsatzsteuerliche Zeitpunkt in einem festgeschriebenen Monat?"""
    hinweise: list[str] = []
    if entwurf.ist_korrektur or r.datum is None:
        return hinweise
    for kategorie in sorted({s.kategorie or "" for s in r.steuern}):
        tag, _ = steuertag(r.datum, r.leistungsdatum, kategorie or None)
        if tag == r.datum or sperrfehler(session.connection(), tag) is None:
            continue
        text = (
            f"Leistungsmonat {tag:%m/%Y} ist festgeschrieben — die Umsatzsteuer "
            "gehört dorthin (§ 13 Abs. 1 UStG): vor 'accounti opos verbuchen' den "
            f"Monat mit Grund öffnen (accounti periode oeffnen {tag:%Y-%m} --grund …) "
            "und die Voranmeldung berichtigen"
        )
        if text not in hinweise:
            hinweise.append(text)
    return hinweise


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
    hinweis_30_tage: bool = False,
) -> AusstellErgebnis:
    """Stellt einen Entwurf aus: XRechnung (bzw. EN 16931) und ZUGFeRD-PDF.

    ``kosit`` prüft das XML, ``pdf_pruefer`` das PDF formal; ``None`` überspringt
    die jeweilige Prüfung. Das KoSIT-Prüftool prüft nur XRechnungen — eine Rechnung
    an Privatkunden nach EN 16931 prüft Mustang. Steuerfreie EU-Rechnungen (K, AE)
    brauchen eine qualifizierte Bestätigung der Kunden-USt-IdNr. im Protokoll,
    höchstens ``ustid_max_alter_tage`` vor dem Rechnungsdatum. ``hinweis_30_tage``:
    Rechnungen an Verbraucher tragen den Hinweis nach § 286 Abs. 3 BGB.
    """
    entwurf = lade_ausgangsrechnung(session, schluessel)
    if entwurf.status is not AusgangsrechnungStatus.ENTWURF:
        msg = f"Rechnung {entwurf.nummer} ist bereits ausgestellt."
        raise AusstellungError(msg)
    jetzt = erstellt_am or datetime.now().astimezone()
    _pruefe_datum(session, rechnungsdatum, jetzt.date())
    vorgaenger_datum = _vorgaenger(session, entwurf, rechnungsdatum)

    nummer = _nummer(session, firma, rechnungsdatum)
    try:
        rechnung = baue_rechnung(
            entwurf,
            firma,
            nummer,
            rechnungsdatum,
            vorgaenger_datum=vorgaenger_datum,
            hinweis_verzug=hinweis_30_tage,
        )
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
    if kosit is not None and rechnung.profil is Profil.XRECHNUNG:
        kosit_ergebnis = kosit.pruefe(xml, f"{nummer}.xml")
        if not kosit_ergebnis.akzeptiert:
            gruende = "; ".join(str(m) for m in kosit_ergebnis.fehler) or "abgelehnt"
            msg = f"KoSIT-Prüftool: {gruende}"
            raise AusstellungError(msg, befunde=befunde, kosit=kosit_ergebnis)

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
        hinweise=_hinweise(session, entwurf, rechnung),
    )
