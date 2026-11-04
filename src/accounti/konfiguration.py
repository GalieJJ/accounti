"""Konfiguration — Firmendaten (Mandant) aus ``config/accounti.yaml``.

Die Firmendaten braucht jede Ausgangsrechnung: XRechnung verlangt Anschrift, Kontakt,
elektronische Adresse und Zahlungsdaten des Verkäufers.
"""

from __future__ import annotations

import logging
import os
import string
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from accounti.belege.extraktion import iban_gueltig
from accounti.einstellungen.inventar import Betriebsfeld

# KonfigurationError lebt beim Abschnittsleser (der keine Fachmodule importiert);
# hier bleibt er für alle Lader erreichbar
from accounti.einstellungen.leser import KonfigurationError as KonfigurationError
from accounti.einstellungen.leser import (
    datei_vorhanden,
    lies_abschnitt,
    quelle_vorhanden,
)
from accounti.kontakte.ustid import EVATR_URL

if TYPE_CHECKING:
    from accounti.kontakte.dienst import Partnerdaten

STANDARD_PFAD = Path("config/accounti.yaml")


class Anschrift(BaseModel):
    strasse: str
    plz: str
    ort: str
    land: str = Field(default="DE", min_length=2, max_length=2)


class Kontakt(BaseModel):
    name: str
    telefon: str
    email: str


class Bank(BaseModel):
    iban: str
    bic: str | None = None

    @field_validator("iban")
    @classmethod
    def _iban(cls, wert: str) -> str:
        iban = wert.replace(" ", "").upper()
        if not iban_gueltig(iban):
            msg = f"IBAN {wert!r} ist ungültig (Prüfziffer)"
            raise ValueError(msg)
        return iban


def _felder(format_: str) -> set[str]:
    return {
        name.split(".")[0].split("[")[0]
        for _, name, _, _ in string.Formatter().parse(format_)
        if name is not None
    }


class Rechnungseinstellungen(BaseModel):
    nummernformat: str = "{jahr}-{nummer:04d}"
    zahlungsziel_tage: int = Field(default=14, ge=0)

    @field_validator("nummernformat")
    @classmethod
    def _format(cls, wert: str) -> str:
        try:
            felder = _felder(wert)
            wert.format(jahr=2026, nummer=1)
        except (ValueError, KeyError, IndexError) as fehler:
            msg = f"Format {wert!r} ist ungültig ({fehler})"
            raise ValueError(msg) from fehler
        if "nummer" not in felder:
            msg = (
                f"{wert!r} braucht {{nummer}} — sonst bekäme jede Rechnung dieselbe "
                "Nummer (§ 14 Abs. 4 Satz 1 Nr. 4 UStG)"
            )
            raise ValueError(msg)
        if unbekannt := felder - {"jahr", "nummer"}:
            msg = f"{wert!r}: nur {{jahr}} und {{nummer}}, nicht {sorted(unbekannt)}"
            raise ValueError(msg)
        return wert


class Firma(BaseModel):
    name: str
    kuerzel: str | None = Field(
        default=None, description="Schlüssel des Nummernkreises"
    )
    anschrift: Anschrift
    ust_id: str | None = None
    steuernummer: str | None = None
    email: str = Field(description="Elektronische Adresse für E-Rechnungen (BT-34)")
    kontakt: Kontakt
    bank: Bank
    rechnung: Rechnungseinstellungen = Field(default_factory=Rechnungseinstellungen)
    oss: bool = Field(
        default=False,
        description="OSS-registriert: EU-Privatkunden zahlen den Satz ihres Landes",
    )

    @model_validator(mode="after")
    def _pflichten(self) -> Firma:
        if not (self.ust_id or self.steuernummer):
            msg = "USt-IdNr. oder Steuernummer fehlt (§ 14 Abs. 4 Nr. 2 UStG)"
            raise ValueError(msg)
        if self.kuerzel is None:
            self.kuerzel = self.name
        return self

    @property
    def iban(self) -> str:
        return self.bank.iban

    @property
    def zahlungsziel_tage(self) -> int:
        return self.rechnung.zahlungsziel_tage

    @property
    def nummernkreis(self) -> str:
        return self.kuerzel or self.name

    @property
    def nummer_je_jahr(self) -> bool:
        """Beginnt der Kreis jedes Jahr neu? Nur mit ``{jahr}`` im Format."""
        return "jahr" in _felder(self.rechnung.nummernformat)

    def nummer(self, jahr: int, laufend: int) -> str:
        """Rechnungsnummer aus Jahr und laufender Nummer, z.B. ``2026-0042``."""
        return self.rechnung.nummernformat.format(jahr=jahr, nummer=laufend)


def _fehlertext(
    fehler: ValidationError,
    abschnitt: str = "mandant",
    herkunft: dict[str, str] | None = None,
) -> str:
    """Fehler je Feld mit dem Abschnitt davor (``buchhaltung.kontenrahmen: …``);
    ``herkunft`` nennt für einzelne Felder einen anderen Abschnitt (der Kontenrahmen
    aus ``mandant``) — Nachprüfung N5: bisher stand immer „mandant.“ davor."""
    teile = []
    for f in fehler.errors():
        pfad = ".".join(str(x) for x in f["loc"])
        grund = (
            "fehlt"
            if f["type"] == "missing"
            else str(f["msg"]).removeprefix("Value error, ")
        )
        wo = (herkunft or {}).get(str(f["loc"][0]), abschnitt) if pfad else ""
        teile.append(f"{wo}.{pfad}: {grund}" if pfad else grund)
    return "; ".join(teile)


# Wo der Abschnitt mandant später im Browser gepflegt wird (Spec 10c, AK77)
SEITE_FIRMA = "Einstellungen › Firma & Steuern"


def lade_firma(pfad: str | Path = STANDARD_PFAD) -> Firma:
    """Abschnitt ``mandant`` über den Abschnittsleser (Datenbank vor Datei, D25: auch
    ohne Datei)."""
    pfad = Path(pfad)
    if not quelle_vorhanden(pfad, "mandant"):
        if not datei_vorhanden(pfad):
            msg = (
                f"{pfad} fehlt — Vorlage: config/accounti.example.yaml kopieren und "
                f"den Abschnitt 'mandant' ausfüllen ({SEITE_FIRMA})"
            )
        else:
            msg = f"{pfad}: Abschnitt 'mandant' fehlt ({SEITE_FIRMA})"
        raise KonfigurationError(msg)
    try:
        return Firma.model_validate(lies_abschnitt(pfad, "mandant"))
    except ValidationError as fehler:
        msg = f"{pfad}: {_fehlertext(fehler)} ({SEITE_FIRMA})"
        raise KonfigurationError(msg) from fehler


KONTENRAHMEN = ("SKR03", "SKR04")
PERSONENKONTO_MAX = 999_999_999  # DATEV: höchstens 9 Stellen
LOG = logging.getLogger("accounti.konfiguration")
_GEMELDET: set[tuple[str, str]] = set()  # Hinweise je Datei und Feld einmal


class Buchhaltung(BaseModel):
    """Abschnitt ``buchhaltung`` — optional, ohne ihn gelten die Standards.

    ``kontenrahmen`` ist die eine Quelle für USt, Abschluss, Anlagen, Prüfregeln und
    DATEV (``lade_buchhaltung`` übernimmt ``mandant.kontenrahmen`` älterer
    Konfigurationen)."""

    kontenrahmen: str = "SKR03"
    debitoren_von: int = 10000
    debitoren_bis: int = 69999
    kreditoren_von: int = 70000
    kreditoren_bis: int = 99999
    bank_konto: str = "1200"
    standard_aufwand: str = Field(
        default="4900", description="Sachkonto, wenn nichts Besseres bekannt ist"
    )
    standard_zahlungsziel_tage: int = 14
    skonto_karenz_tage: int = Field(
        default=3,
        description="Skonto gilt noch, wenn die Bank so viele Tage später bucht",
    )
    # Skontokonten je Steuersatz (SKR03); "0" für steuerfreie Rechnungen
    skonto_erhalten: dict[str, str] = Field(
        default_factory=lambda: {"19": "3736", "7": "3731", "0": "3730"}
    )
    skonto_gewaehrt: dict[str, str] = Field(
        default_factory=lambda: {"19": "8736", "7": "8731", "0": "8730"}
    )
    # gelernte Kontierungsregeln (Datenbank, Baustein 10b): automatisch buchen (wie
    # jede Regel), nur vorschlagen (Confidence 0,9 → zur Prüfung) oder nicht laden
    gelernte_regeln: Literal["automatisch", "pruefen", "aus"] = "automatisch"

    @field_validator(
        "debitoren_von", "debitoren_bis", "kreditoren_von", "kreditoren_bis"
    )
    @classmethod
    def _personenkonten(cls, wert: int) -> int:
        # DATEV-Personenkonten haben höchstens 9 Stellen (Sachkontenlänge 8 + 1); ein
        # 10-stelliger Debitor wurde gebucht, ließ sich aber weder korrigieren noch in
        # der Kasse gegenbuchen (Kontonummern 4–9 Ziffern) — Runde 6, g5w-konten N3
        if not 0 <= wert <= PERSONENKONTO_MAX:
            msg = f"{wert}: Personenkonten haben höchstens 9 Stellen (DATEV)"
            raise ValueError(msg)
        return wert

    @field_validator("kontenrahmen", mode="before")
    @classmethod
    def _kontenrahmen(cls, wert: object) -> str:
        text = str(wert).strip().upper()
        if text not in KONTENRAHMEN:
            # bisher fiel ein Tippfehler still auf SKR03 zurück
            msg = f"kontenrahmen {wert!r}: SKR03 oder SKR04"
            raise ValueError(msg)
        return text


def lade_buchhaltung(pfad: str | Path = STANDARD_PFAD) -> Buchhaltung:
    """Abschnitt ``buchhaltung``. Fehlt dort ``kontenrahmen``, gilt
    ``mandant.kontenrahmen`` (so stand es früher in der Vorlage); widersprechen sich
    beide, ist das ein Fehler — sonst rechneten USt und Abschluss mit dem einen, der
    DATEV-Kopf mit dem anderen Kontenrahmen (Gesamttest Betrieb B4)."""
    pfad = Path(pfad)
    # über den Abschnittsleser (Baustein 10c P4): Datenbank vor Datei, ohne Datei {}
    werte: dict[str, Any] = lies_abschnitt(pfad, "buchhaltung")
    herkunft: dict[str, str] = {}
    alt = lies_abschnitt(pfad, "mandant").get("kontenrahmen")
    if alt is not None:
        eigen = werte.get("kontenrahmen")
        if eigen is None:
            werte = {**werte, "kontenrahmen": alt}
            herkunft["kontenrahmen"] = "mandant"
        elif str(eigen).strip().upper() != str(alt).strip().upper():
            msg = (
                f"{pfad}: buchhaltung.kontenrahmen ({eigen}) und mandant.kontenrahmen "
                f"({alt}) widersprechen sich — nur buchhaltung.kontenrahmen angeben"
            )
            raise KonfigurationError(msg)
    werte = _offene_obergrenzen(pfad, werte)
    try:
        return Buchhaltung.model_validate(werte)
    except ValidationError as fehler:
        text = _fehlertext(fehler, "buchhaltung", herkunft)
        msg = f"{pfad}: Abschnitt 'buchhaltung': {text}"
        raise KonfigurationError(msg) from fehler


def _offene_obergrenzen(pfad: Path, werte: dict[str, Any]) -> dict[str, Any]:
    """Eine Obergrenze über 9 Stellen (``kreditoren_bis: 9999999999`` als „offen“)
    gilt als 999999999 — mit Hinweis statt Abbruch: Bis Runde 5 lief so eine
    Konfiguration, seit Runde 6 hielt sie jeden Befehl an (Gesamttest 10b-1, Runde 7:
    g6w B-5). Eine Untergrenze über 9 Stellen bleibt ein Fehler (dann gäbe es kein
    gültiges Personenkonto im Bereich)."""
    neu = dict(werte)
    for feld in ("debitoren_bis", "kreditoren_bis"):
        wert = neu.get(feld)
        if isinstance(wert, bool) or not isinstance(wert, int | str):
            continue
        try:
            zahl = int(str(wert).strip())
        except ValueError:
            continue  # den Fehler meldet die Prüfung des Modells
        if zahl <= PERSONENKONTO_MAX:
            continue
        neu[feld] = PERSONENKONTO_MAX
        if (str(pfad), feld) not in _GEMELDET:
            _GEMELDET.add((str(pfad), feld))
            LOG.warning(
                "%s: buchhaltung.%s %s — Personenkonten haben höchstens 9 Stellen "
                "(DATEV), es gilt %s; bitte in der Konfiguration berichtigen "
                "(docs/betrieb.md, Upgrades)",
                pfad,
                feld,
                zahl,
                PERSONENKONTO_MAX,
            )
    return neu


class UstIdEinstellungen(BaseModel):
    """Bestätigungsabfrage beim BZSt (Abschnitt ``ustid_pruefung``)."""

    url: Betriebsfeld[str] = EVATR_URL
    timeout_sekunden: float = Field(default=60, gt=0)
    max_alter_tage: int = Field(
        default=30,
        ge=0,
        description="so lange vor dem Rechnungsdatum gilt eine Bestätigung",
    )


def lade_ustid_pruefung(pfad: str | Path = STANDARD_PFAD) -> UstIdEinstellungen:
    """Abschnitt ``ustid_pruefung``; ``ACCOUNTI_EVATR_URL`` ersetzt die URL."""
    pfad = Path(pfad)
    werte = lies_abschnitt(pfad, "ustid_pruefung")
    if os.environ.get("ACCOUNTI_EVATR_URL"):
        werte["url"] = os.environ["ACCOUNTI_EVATR_URL"]
    try:
        return UstIdEinstellungen.model_validate(werte)
    except ValidationError as fehler:
        msg = f"{pfad}: Abschnitt 'ustid_pruefung': "
        msg += _fehlertext(fehler, "ustid_pruefung")
        raise KonfigurationError(msg) from fehler


def lade_eigene_firma(pfad: str | Path = STANDARD_PFAD) -> Partnerdaten | None:
    """Name, USt-IdNr. und IBAN der eigenen Firma — nachsichtig gelesen.

    Anders als `lade_firma` verlangt das keine vollständigen Firmendaten: Es reicht,
    die eigene Firma wiederzuerkennen (z.B. damit sie nie als Kreditor angelegt wird).
    """
    from accounti.kontakte.dienst import Partnerdaten

    mandant = lies_abschnitt(Path(pfad), "mandant")
    if not mandant.get("name"):
        return None
    bank_roh = mandant.get("bank")
    bank: dict[str, Any] = bank_roh if isinstance(bank_roh, dict) else {}
    return Partnerdaten(
        name=str(mandant["name"]),
        ust_id=mandant.get("ust_id"),
        iban=str(bank.get("iban", "")).replace(" ", "") or None,
    )
