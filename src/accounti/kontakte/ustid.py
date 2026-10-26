"""USt-IdNr.-Prüfung — qualifizierte Bestätigungsabfrage beim BZSt (§ 18e UStG).

Eine steuerfreie innergemeinschaftliche Lieferung (und Reverse Charge bei EU-
Leistungen) setzt eine gültige USt-IdNr. des Abnehmers voraus — und im Streitfall
den Nachweis, dass sie geprüft wurde. Deshalb fragt accounti beim BZSt an und hält
jede Abfrage samt Rohantwort in einem Protokoll fest, das nur wachsen kann.

Schnittstelle: eVatR-REST-API (seit 01.07.2025; XML-RPC ist seit 30.11.2025 aus)
  POST https://api.evatr.vies.bzst.de/app/v1/abfrage
  qualifiziert, sobald ``firmenname`` und ``ort`` mitgeschickt werden
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.anzeige import datum_de
from accounti.belege.archiv import aufbewahrungsende
from accounti.betrieb.aufbewahrung import Unterlage
from accounti.db.repository import (
    lade_ustid_pruefungen,
    letzte_ustid_pruefung,
    speichere_ustid_pruefung,
)
from accounti.models import UstIdPruefart, UstIdPruefung

EVATR_URL = "https://api.evatr.vies.bzst.de/app/v1/abfrage"
GENESIS = "0" * 64  # Vorgänger des ersten Protokolleintrags

# Steuerkategorien (UNCL 5305), die eine bestätigte USt-IdNr. des Käufers brauchen
USTID_KATEGORIEN = frozenset({"K", "AE"})

# Länderkennzeichen laut BZSt (/v1/info/eu_mitgliedstaaten): Griechenland EL,
# Nordirland XI
LAENDER = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "EL",
        "ES",
        "FI",
        "FR",
        "HR",
        "HU",
        "IE",
        "IT",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SE",
        "SI",
        "SK",
        "XI",
    }
)

GUELTIG = frozenset({"evatr-0000", "evatr-2008"})
# Antworten, die eine Aussage über die Nummer treffen: nicht vergeben, abgelaufen,
# noch nicht gültig, syntaktisch falsch, falsches Länderkennzeichen
UNGUELTIG = frozenset(
    {
        "evatr-2001",
        "evatr-2002",
        "evatr-2006",
        "evatr-0005",
        "evatr-0012",
        "evatr-2003",
    }
)

_STOERUNG = (
    "Eine Bearbeitung Ihrer Anfrage ist zurzeit nicht möglich. Bitte versuchen Sie "
    "es später noch einmal."
)
# amtliche Texte aus GET /app/v1/info/statusmeldungen (Stand 20.10.2026)
MELDUNGEN: dict[str, str] = {
    "evatr-0000": "Die angefragte USt-IdNr. ist zum Anfragezeitpunkt gültig.",
    "evatr-0001": "Bitte bestätigen Sie den Datenschutzhinweis.",
    "evatr-0002": "Mindestens eins der Pflichtfelder ist nicht besetzt.",
    "evatr-0003": "Die angefragte USt-IdNr. ist zum Anfragezeitpunkt gültig. "
    "Mindestens eines der Pflichtfelder für eine qualifizierte Bestätigungsanfrage "
    "ist nicht besetzt.",
    "evatr-0004": "Die anfragende DE USt-IdNr. ist syntaktisch falsch. Sie passt "
    "nicht in das deutsche Erzeugungsschema.",
    "evatr-0005": "Die angegebene angefragte USt-IdNr. ist syntaktisch falsch.",
    "evatr-0006": "Die anfragende DE USt-IdNr. ist nicht berechtigt eine DE "
    "USt-IdNr. anzufragen.",
    "evatr-0007": "Fehlerhafter Aufruf.",
    "evatr-0008": "Die maximale Anzahl von qualifizierten Bestätigungsabfragen für "
    "diese Session wurde erreicht. Bitte starten Sie erneut mit einer einfachen "
    "Bestätigungsabfrage.",
    "evatr-0011": _STOERUNG,
    "evatr-0012": "Die angefragte USt-IdNr. ist syntaktisch falsch. Sie passt "
    "nicht in das Erzeugungsschema.",
    "evatr-0013": _STOERUNG,
    "evatr-1001": _STOERUNG,
    "evatr-1002": _STOERUNG,
    "evatr-1003": _STOERUNG,
    "evatr-1004": _STOERUNG,
    "evatr-2001": "Die angefragte USt-IdNr. ist zum Anfragezeitpunkt nicht vergeben.",
    "evatr-2002": "Die angefragte USt-IdNr. ist zum Anfragezeitpunkt nicht gültig. "
    "Sie ist erst gültig ab dem Datum im Feld gueltigAb.",
    "evatr-2003": "Das angegebene Länderkennzeichen der angefragten USt-IdNr. ist "
    "nicht gültig.",
    "evatr-2004": _STOERUNG,
    "evatr-2005": "Die angegebene eigene DE USt-IdNr. ist zum Anfragezeitpunkt "
    "nicht gültig.",
    "evatr-2006": "Die angefragte USt-IdNr. ist zum Anfragezeitpunkt nicht gültig. "
    "Sie war gültig im Zeitraum, der durch die Werte in den Feldern gueltigAb und "
    "gueltigBis beschrieben ist.",
    "evatr-2007": "Bei der Verarbeitung der Daten aus dem angefragten "
    "EU-Mitgliedstaat ist ein Fehler aufgetreten. Ihre Anfrage kann deshalb nicht "
    "bearbeitet werden.",
    "evatr-2008": "Die angefragte USt-IdNr. ist zum Anfragezeitpunkt gültig. Für "
    "die qualifizierte Bestätigungsanfrage liegt eine Besonderheit vor. Für "
    "Rückfragen wenden Sie sich an das BZSt.",
    "evatr-2011": _STOERUNG,
    "evatr-3011": _STOERUNG,
}


class UstIdError(ValueError):
    """Die Abfrage ist so nicht zulässig — sie geht gar nicht erst raus."""


def normalisiere(ust_id: str) -> str:
    """Schreibweise, die VIES erwartet: ohne Trenner, groß, Griechenland als EL."""
    kompakt = re.sub(r"[\s.\-/]", "", ust_id).upper()
    return "EL" + kompakt[2:] if kompakt.startswith("GR") else kompakt


@dataclass(frozen=True)
class Anfrage:
    eigene_ust_id: str
    ust_id: str
    firmenname: str | None = None
    strasse: str | None = None
    plz: str | None = None
    ort: str | None = None

    @property
    def art(self) -> UstIdPruefart:
        return (
            UstIdPruefart.QUALIFIZIERT
            if self.firmenname and self.ort
            else UstIdPruefart.EINFACH
        )

    def als_dict(self) -> dict[str, str]:
        daten = {"anfragendeUstid": self.eigene_ust_id, "angefragteUstid": self.ust_id}
        if self.art is UstIdPruefart.QUALIFIZIERT:
            for feld in ("firmenname", "strasse", "plz", "ort"):
                wert = getattr(self, feld)
                if wert:
                    daten[feld] = wert
        return daten

    def als_json(self) -> str:
        return json.dumps(self.als_dict(), ensure_ascii=False)


def _leer(wert: str | None) -> str | None:
    return wert.strip() or None if wert else None


def baue_anfrage(
    eigene_ust_id: str | None,
    ust_id: str | None,
    firmenname: str | None = None,
    strasse: str | None = None,
    plz: str | None = None,
    ort: str | None = None,
    einfach: bool = False,
) -> Anfrage:
    """Prüft und normalisiert die Abfrage; unzulässige Abfragen gehen nicht raus."""
    eigene = normalisiere(eigene_ust_id or "")
    if not eigene.startswith("DE"):
        msg = (
            "Die eigene USt-IdNr. muss eine deutsche sein (mandant.ust_id) — "
            f"angegeben: {eigene_ust_id or 'keine'}"
        )
        raise UstIdError(msg)
    angefragt = normalisiere(ust_id or "")
    if not angefragt:
        raise UstIdError("Die USt-IdNr. des Geschäftspartners fehlt")
    if angefragt.startswith("DE"):
        msg = (
            f"{angefragt} ist eine inländische USt-IdNr. — das BZSt bestätigt nur "
            "ausländische"
        )
        raise UstIdError(msg)
    if angefragt[:2] not in LAENDER:
        msg = f"{angefragt}: kein Länderkennzeichen eines EU-Mitgliedstaats"
        raise UstIdError(msg)
    if einfach:
        return Anfrage(eigene, angefragt)
    return Anfrage(
        eigene, angefragt, _leer(firmenname), _leer(strasse), _leer(plz), _leer(ort)
    )


@dataclass(frozen=True)
class HttpAntwort:
    status: int
    text: str


class Abfrageweg(Protocol):
    def sende(self, daten: dict[str, str]) -> HttpAntwort: ...


class EvatrClient:
    """HTTP-Zugang zur eVatR-REST-API. Netz- und Zeitfehler steigen als OSError auf."""

    def __init__(self, url: str = EVATR_URL, timeout: float = 60.0) -> None:
        if not url.startswith(("https://", "http://")):
            msg = f"eVatR-URL muss mit http:// oder https:// beginnen: {url}"
            raise UstIdError(msg)
        self.url = url
        self.timeout = timeout

    def sende(self, daten: dict[str, str]) -> HttpAntwort:
        anfrage = urllib.request.Request(
            self.url,
            data=json.dumps(daten).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(anfrage, timeout=self.timeout) as antwort:
                return HttpAntwort(antwort.status, antwort.read().decode("utf-8"))
        except urllib.error.HTTPError as fehler:
            # 4xx/5xx tragen beim BZSt denselben JSON-Datensatz mit Status
            return HttpAntwort(fehler.code, fehler.read().decode("utf-8", "replace"))


def werte_aus(
    anfrage: Anfrage,
    http_status: int | None,
    text: str | None,
    fehler: str | None,
    zeitpunkt: datetime,
    kontakt_id: UUID | None = None,
) -> UstIdPruefung:
    """Macht aus Anfrage und Antwort einen (noch nicht protokollierten) Eintrag."""
    daten: dict[str, object] = {}
    if text is not None and fehler is None:
        try:
            gelesen = json.loads(text)
        except ValueError:
            gelesen = None
        if isinstance(gelesen, dict) and isinstance(gelesen.get("status"), str):
            daten = gelesen
        else:
            fehler = f"Antwort nicht lesbar (HTTP {http_status})"

    def feld(name: str) -> str | None:
        wert = daten.get(name)
        return str(wert) if wert not in (None, "") else None

    gesendet = anfrage.als_dict()

    return UstIdPruefung(
        zeitpunkt=zeitpunkt,
        kontakt_id=kontakt_id,
        eigene_ust_id=anfrage.eigene_ust_id,
        ust_id=anfrage.ust_id,
        art=anfrage.art,
        # Firmendaten nur, wenn sie tatsächlich mitgeschickt wurden
        firmenname=gesendet.get("firmenname"),
        strasse=gesendet.get("strasse"),
        plz=gesendet.get("plz"),
        ort=gesendet.get("ort"),
        http_status=http_status,
        status=feld("status"),
        bzst_id=feld("id"),
        bzst_zeitpunkt=feld("anfrageZeitpunkt"),
        gueltig_ab=feld("gueltigAb"),
        gueltig_bis=feld("gueltigBis"),
        erg_firmenname=feld("ergFirmenname"),
        erg_strasse=feld("ergStrasse"),
        erg_plz=feld("ergPlz"),
        erg_ort=feld("ergOrt"),
        fehler=fehler,
        anfrage=anfrage.als_json(),
        antwort=text,
        # Protokoll = Aufzeichnung (§ 147 Abs. 1 Nr. 1 AO): 10 Jahre
        aufbewahren_bis=aufbewahrungsende(zeitpunkt.date(), Unterlage.BUCH),
    )


@dataclass(frozen=True)
class Bewertung:
    bestaetigt: bool  # taugt als Grundlage für K/AE
    gueltig: bool | None  # None: keine Aussage (Störung, keine Antwort)
    grund: str
    hinweise: tuple[str, ...] = ()
    pruefung: UstIdPruefung | None = None


def _datum(wert: str | None) -> str:
    if not wert:
        return "?"
    try:
        return datum_de(date.fromisoformat(wert[:10]))
    except ValueError:
        return wert


def meldung(status: str | None) -> str:
    if status is None:
        return "keine Antwort"
    text = MELDUNGEN.get(status)
    return f"{text} ({status})" if text else f"unbekannter Status {status}"


_FELDER = (
    ("erg_firmenname", "Firmenname"),
    ("erg_strasse", "Straße"),
    ("erg_plz", "PLZ"),
    ("erg_ort", "Ort"),
)
_PFLICHT = {"erg_firmenname", "erg_ort"}  # tragen den Vertrauensschutz


def bewerte(p: UstIdPruefung) -> Bewertung:
    """Was die Antwort für die Steuerfreiheit bedeutet — mit lesbarem Grund."""
    if p.fehler is not None:
        return Bewertung(False, None, p.fehler, pruefung=p)
    if p.status in UNGUELTIG:
        grund = f"nicht gültig — {meldung(p.status)}"
        if p.gueltig_ab or p.gueltig_bis:
            grund += (
                f"; gültig von {_datum(p.gueltig_ab)} bis {_datum(p.gueltig_bis)}"
                if p.gueltig_bis
                else f"; gültig ab {_datum(p.gueltig_ab)}"
            )
        return Bewertung(False, False, grund, pruefung=p)
    if p.status not in GUELTIG:
        return Bewertung(False, None, meldung(p.status), pruefung=p)
    if p.status == "evatr-2008":
        grund = (
            "gültig, aber das BZSt meldet eine Besonderheit für die qualifizierte "
            "Bestätigung — Rückfrage beim BZSt (evatr-2008)"
        )
        return Bewertung(False, True, grund, pruefung=p)
    if p.art is UstIdPruefart.EINFACH:
        grund = (
            "gültig, aber nur einfach bestätigt — für die Steuerfreiheit ist die "
            "qualifizierte Abfrage mit Name und Ort nötig"
        )
        return Bewertung(False, True, grund, pruefung=p)

    abweichend = [n for f, n in _FELDER if getattr(p, f) == "B" and f in _PFLICHT]
    if abweichend:
        grund = (
            f"gültig, aber {' und '.join(abweichend)} stimmen nicht mit den beim "
            "Mitgliedstaat registrierten Daten überein"
        )
        return Bewertung(False, True, grund, pruefung=p)
    hinweise = tuple(
        f"{n} weicht von den registrierten Daten ab"
        for f, n in _FELDER
        if getattr(p, f) == "B"
    ) + tuple(
        f"{n} vom Mitgliedstaat nicht mitgeteilt"
        for f, n in _FELDER
        if getattr(p, f) == "D"
    )
    return Bewertung(True, True, "gültig, qualifiziert bestätigt", hinweise, p)


# --- Protokoll ---------------------------------------------------------------


def eintrag_hash(p: UstIdPruefung) -> str:
    """SHA-256 über alle Felder außer dem Hash selbst — inklusive Vorgänger-Hash."""
    daten = p.model_dump(mode="json", exclude={"hash"})
    roh = json.dumps(daten, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(roh.encode()).hexdigest()


def protokolliere(session: Session, p: UstIdPruefung) -> UstIdPruefung:
    """Hängt den Eintrag an das Protokoll an (Nummer, Verkettung, Hash)."""
    letzte = letzte_ustid_pruefung(session)
    zeitpunkt = p.zeitpunkt
    if zeitpunkt.tzinfo is not None:  # die Datenbank speichert ohne Zeitzone
        zeitpunkt = zeitpunkt.astimezone().replace(tzinfo=None)
    eintrag = p.model_copy(
        update={
            "nr": letzte.nr + 1 if letzte else 1,
            "vorgaenger_hash": letzte.hash if letzte else GENESIS,
            "zeitpunkt": zeitpunkt,
            "hash": "",
        }
    )
    eintrag = eintrag.model_copy(update={"hash": eintrag_hash(eintrag)})
    speichere_ustid_pruefung(session, eintrag)
    return eintrag


def pruefe_ustid(
    session: Session,
    weg: Abfrageweg,
    anfrage: Anfrage,
    kontakt_id: UUID | None = None,
    jetzt: datetime | None = None,
) -> UstIdPruefung:
    """Fragt beim BZSt an und protokolliert — auch wenn keine Antwort kommt.

    Der Aufrufer schreibt fest (``commit``), und zwar sofort: Der Nachweis darf
    nicht mit einer später scheiternden Buchung oder Ausstellung verschwinden.
    """
    try:
        antwort = weg.sende(anfrage.als_dict())
        http, text, fehler = antwort.status, antwort.text, None
    except OSError as problem:  # keine Verbindung, Zeitüberschreitung
        http, text, fehler = None, None, f"{type(problem).__name__}: {problem}"
    p = werte_aus(anfrage, http, text, fehler, jetzt or datetime.now(), kontakt_id)
    return protokolliere(session, p)


def pruefe_protokoll(eintraege: list[UstIdPruefung]) -> list[str]:
    """Befunde zu Lücken, gebrochener Verkettung und veränderten Einträgen."""
    befunde = []
    vorher, erwartet = GENESIS, 1
    for p in sorted(eintraege, key=lambda e: e.nr):
        if p.nr > erwartet:
            luecke = f"{erwartet} bis {p.nr - 1}" if p.nr - 1 > erwartet else erwartet
            befunde.append(f"Eintrag {luecke} fehlt")
        if p.vorgaenger_hash != vorher:
            befunde.append(f"Eintrag {p.nr}: Verkettung zum Vorgänger gebrochen")
        if eintrag_hash(p) != p.hash:
            befunde.append(f"Eintrag {p.nr}: Inhalt verändert")
        vorher, erwartet = p.hash, p.nr + 1
    return befunde


def aktuelle_bestaetigung(
    session: Session, ust_id: str | None, stichtag: date, max_alter_tage: int
) -> Bewertung:
    """Ist die USt-IdNr. zum Stichtag qualifiziert bestätigt?

    Es zählt die jüngste aussagekräftige Antwort im Zeitraum (``max_alter_tage``
    vor dem Stichtag bis heute): Eine spätere Ungültigkeit sticht eine frühere
    Bestätigung, eine spätere einfache Abfrage schadet einer qualifizierten nicht,
    Störungen ohne Aussage zählen gar nicht.
    """
    if not ust_id:
        return Bewertung(False, None, "keine USt-IdNr. des Käufers angegeben")
    ab = stichtag - timedelta(days=max_alter_tage)
    alle = lade_ustid_pruefungen(session, normalisiere(ust_id))
    # jüngste zuerst, nur Antworten mit einer Aussage über die Nummer
    aussagekraeftig = [
        (p, b) for p in reversed(alle) if (b := bewerte(p)).gueltig is not None
    ]

    nur_einfach: Bewertung | None = None
    for p, b in aussagekraeftig:
        if p.zeitpunkt.date() < ab:
            break
        if b.bestaetigt:
            return b
        if b.gueltig is False:
            return nur_einfach or b  # eine jüngere Gültigkeit hebt sie auf
        if p.art is UstIdPruefart.EINFACH:
            nur_einfach = nur_einfach or b  # weiter nach einer qualifizierten suchen
            continue
        return b  # gültig, aber Name/Ort abweichend oder Besonderheit
    if nur_einfach is not None:
        return nur_einfach

    grund = f"keine Bestätigung seit {datum_de(ab)}"
    frueher = next((p for p, b in aussagekraeftig if b.bestaetigt), None)
    if frueher is not None:
        am = datum_de(frueher.zeitpunkt.date())
        grund += f" — zuletzt qualifiziert bestätigt am {am}"
    elif alle:
        letzter = alle[-1]
        grund += (
            f" — letzter Versuch am {datum_de(letzter.zeitpunkt.date())}: "
            f"{bewerte(letzter).grund}"
        )
    return Bewertung(False, None, grund)
