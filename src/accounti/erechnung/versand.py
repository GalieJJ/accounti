"""Versand ausgestellter Rechnungen — per E-Mail, später auch über Peppol.

Versendet wird immer die archivierte Datei, nie eine neu erzeugte: Was beim Kunden
ankommt, ist byte-genau das, was geprüft und archiviert wurde. Jeder Versuch — auch
ein gescheiterter — landet im Versandprotokoll.
"""

from __future__ import annotations

import os
import re
import smtplib
import ssl
from datetime import datetime
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid, parseaddr
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from accounti.anzeige import betrag_de
from accounti.belege.archiv import BelegArchiv
from accounti.db.repository import lade_ausgangsrechnung, speichere_versandprotokoll
from accounti.erechnung import lies
from accounti.konfiguration import STANDARD_PFAD, Firma, KonfigurationError
from accounti.models import Ausgangsrechnung, AusgangsrechnungStatus, Versandprotokoll

Format = Literal["zugferd", "xrechnung"]

_FORMATE: dict[str, tuple[str, str, str, str]] = {
    # Format → (Endung, MIME-Haupttyp, MIME-Untertyp, Bezeichnung im Text)
    "zugferd": (
        "pdf",
        "application",
        "pdf",
        "ZUGFeRD (PDF mit eingebetteter XRechnung)",
    ),
    "xrechnung": ("xml", "application", "xml", "XRechnung (XML)"),
}

STANDARD_TEXT = """Sehr geehrte Damen und Herren,

anbei erhalten Sie unsere Rechnung {nummer} vom {datum} über {brutto} EUR.
Bitte überweisen Sie den Betrag bis zum {faellig} unter Angabe der Rechnungsnummer.

Die Rechnung ist eine E-Rechnung im Format {format}.

Mit freundlichen Grüßen
{firma}
"""


class VersandError(RuntimeError):
    """Die Rechnung kann so nicht versendet werden."""


class SmtpKonfiguration(BaseModel):
    host: str
    port: int = 587
    benutzer: str | None = None
    passwort: str | None = None
    verschluesselung: Literal["starttls", "ssl", "keine"] = "starttls"
    timeout: int = 30


class VersandKonfiguration(BaseModel):
    absender: str = Field(description='z.B. "Firma GmbH <rechnung@firma.de>"')
    bcc: str | None = Field(default=None, description="Kopie an sich selbst")
    antwort_an: str | None = None
    smtp: SmtpKonfiguration
    betreff: str = "Rechnung {nummer} von {firma}"
    text: str = STANDARD_TEXT


_VARIABLE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _ersetze_variablen(wert: Any) -> Any:
    """``${NAME}`` in Texten durch Umgebungsvariablen ersetzen (z.B. Passwörter)."""
    if isinstance(wert, dict):
        return {k: _ersetze_variablen(v) for k, v in wert.items()}
    if isinstance(wert, list):
        return [_ersetze_variablen(v) for v in wert]
    if isinstance(wert, str):

        def ersetze(m: re.Match[str]) -> str:
            name = m.group(1)
            if name not in os.environ:
                msg = f"Umgebungsvariable {name} ist nicht gesetzt"
                raise KonfigurationError(msg)
            return os.environ[name]

        return _VARIABLE.sub(ersetze, wert)
    return wert


def lade_versand(pfad: str | Path = STANDARD_PFAD) -> VersandKonfiguration:
    pfad = Path(pfad)
    if not pfad.is_file():
        msg = f"{pfad} fehlt — Vorlage: config/accounti.example.yaml"
        raise KonfigurationError(msg)
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    versand = daten.get("versand") if isinstance(daten, dict) else None
    if not isinstance(versand, dict):
        msg = f"{pfad}: Abschnitt 'versand' fehlt (SMTP-Zugang für den E-Mail-Versand)"
        raise KonfigurationError(msg)
    try:
        return VersandKonfiguration.model_validate(_ersetze_variablen(versand))
    except ValidationError as fehler:
        felder = ", ".join(".".join(map(str, f["loc"])) for f in fehler.errors())
        msg = f"{pfad}: Abschnitt 'versand' unvollständig: {felder}"
        raise KonfigurationError(msg) from fehler


class Versandweg(Protocol):
    name: str

    def sende(self, nachricht: EmailMessage) -> None: ...


class SmtpVersand:
    name = "email"

    def __init__(
        self,
        konfiguration: VersandKonfiguration,
        passwort: str | None = None,
        smtp_klasse: Any = None,
        smtp_ssl_klasse: Any = None,
    ) -> None:
        self.smtp = konfiguration.smtp
        self.passwort = passwort if passwort is not None else self.smtp.passwort
        # erst beim Aufruf auflösen, damit Tests smtplib ersetzen können
        self.smtp_klasse = smtp_klasse
        self.smtp_ssl_klasse = smtp_ssl_klasse

    def sende(self, nachricht: EmailMessage) -> None:
        s = self.smtp
        kontext = ssl.create_default_context()
        if s.verschluesselung == "ssl":
            klasse = self.smtp_ssl_klasse or smtplib.SMTP_SSL
            verbindung = klasse(s.host, s.port, timeout=s.timeout, context=kontext)
        else:
            klasse = self.smtp_klasse or smtplib.SMTP
            verbindung = klasse(s.host, s.port, timeout=s.timeout)
        with verbindung as smtp:
            if s.verschluesselung == "starttls":
                smtp.starttls(context=kontext)
            if s.benutzer:
                smtp.login(s.benutzer, self.passwort or "")
            smtp.send_message(nachricht)


def _dateiname(nummer: str, endung: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", nummer) + f".{endung}"


def baue_nachricht(
    rechnung: Ausgangsrechnung,
    firma: Firma,
    konfiguration: VersandKonfiguration,
    archiv: BelegArchiv,
    format: str,
    empfaenger: str,
    jetzt: datetime | None = None,
) -> EmailMessage:
    """Baut die E-Mail mit der archivierten Rechnung als Anhang."""
    if rechnung.status is not AusgangsrechnungStatus.AUSGESTELLT:
        msg = "Nur ausgestellte Rechnungen können versendet werden (erst ausstellen)."
        raise VersandError(msg)
    if format not in _FORMATE:
        msg = f"Unbekanntes Format {format!r} (zugferd oder xrechnung)"
        raise VersandError(msg)
    endung, haupttyp, untertyp, bezeichnung = _FORMATE[format]
    datei_hash = rechnung.pdf_hash if format == "zugferd" else rechnung.datei_hash
    if datei_hash is None or rechnung.datei_hash is None:
        msg = f"Für Rechnung {rechnung.nummer} ist kein {bezeichnung} archiviert" + (
            " — mit --format xrechnung senden" if format == "zugferd" else ""
        )
        raise VersandError(msg)
    inhalt = archiv.lese(datei_hash)
    daten = lies(archiv.lese(rechnung.datei_hash))  # Summen aus der XRechnung

    werte = {
        "nummer": rechnung.nummer,
        "firma": firma.name,
        "datum": f"{rechnung.rechnungsdatum:%d.%m.%Y}"
        if rechnung.rechnungsdatum
        else "",
        "faellig": f"{rechnung.zahlungsziel:%d.%m.%Y}" if rechnung.zahlungsziel else "",
        "brutto": betrag_de(daten.summen.brutto),
        "format": bezeichnung,
        "kunde": rechnung.kunde.name,
    }
    nachricht = EmailMessage()
    nachricht["From"] = konfiguration.absender
    nachricht["To"] = empfaenger
    if konfiguration.bcc:
        nachricht["Bcc"] = konfiguration.bcc
    if konfiguration.antwort_an:
        nachricht["Reply-To"] = konfiguration.antwort_an
    nachricht["Subject"] = konfiguration.betreff.format(**werte)
    nachricht["Date"] = format_datetime((jetzt or datetime.now()).astimezone())
    domain = Address(addr_spec=parseaddr(konfiguration.absender)[1]).domain
    nachricht["Message-ID"] = make_msgid(domain=domain or None)
    nachricht.set_content(konfiguration.text.format(**werte))
    nachricht.add_attachment(
        inhalt,
        maintype=haupttyp,
        subtype=untertyp,
        filename=_dateiname(rechnung.nummer or "rechnung", endung),
    )
    return nachricht


def versende(
    session: Session,
    archiv: BelegArchiv,
    schluessel: str,
    firma: Firma,
    konfiguration: VersandKonfiguration,
    weg: Versandweg,
    format: str = "zugferd",
    an: str | None = None,
) -> Versandprotokoll:
    """Versendet eine ausgestellte Rechnung und protokolliert den Versuch."""
    rechnung = lade_ausgangsrechnung(session, schluessel)
    if rechnung.status is not AusgangsrechnungStatus.AUSGESTELLT:
        msg = "Nur ausgestellte Rechnungen können versendet werden (erst ausstellen)."
        raise VersandError(msg)
    empfaenger = an or rechnung.kunde.email
    if not empfaenger:
        msg = (
            f"Kein Empfänger für Rechnung {rechnung.nummer} — Adresse mit --an angeben"
        )
        raise VersandError(msg)

    nachricht = baue_nachricht(
        rechnung, firma, konfiguration, archiv, format, empfaenger
    )
    anhang = next(iter(nachricht.iter_attachments()))
    datei_hash = rechnung.pdf_hash if format == "zugferd" else rechnung.datei_hash
    fehler: str | None = None
    try:
        weg.sende(nachricht)
    except (smtplib.SMTPException, OSError) as problem:
        fehler = f"{type(problem).__name__}: {problem}"

    protokoll = Versandprotokoll(
        rechnung_id=rechnung.id,
        weg=weg.name,
        empfaenger=empfaenger,
        format=format,
        dateiname=anhang.get_filename() or "",
        datei_hash=datei_hash or "",
        message_id=nachricht["Message-ID"],
        erfolgreich=fehler is None,
        fehler=fehler,
    )
    speichere_versandprotokoll(session, protokoll)
    return protokoll
