"""Mahnungen versenden: als PDF- und/oder Textdatei und per E-Mail.

Das PDF entsteht einmal, geht unverändert in alle Kanäle und ins Belegarchiv
(Handelsbrief, § 257 HGB). Reihenfolge: erst alles Lokale (Dateien, Archiv), dann
die E-Mail als einziger Schritt, der sich nicht zurückholen lässt, direkt danach der
Status. Scheitert etwas Lokales, ist keine E-Mail hinausgegangen; scheitert die
E-Mail, bleibt die Mahnung ein Entwurf und die Mahnstufe unverändert. Für E-Mails
wird der SMTP-Versandweg der E-Rechnung genutzt (Abschnitt ``versand``).
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid, parseaddr
from pathlib import Path

from sqlalchemy.orm import Session

from accounti.belege.archiv import BelegArchiv
from accounti.db.repository import lade_kontakt
from accounti.erechnung.versand import Versandweg
from accounti.konfiguration import Firma
from accounti.mahnwesen.konfiguration import MahnEinstellungen
from accounti.mahnwesen.lauf import MahnError, pruefe_versendbar, versende
from accounti.mahnwesen.schreiben import mahn_pdf, mahntext
from accounti.models.mahnwesen import Mahnung


@dataclass
class Versandauftrag:
    pdf: Path | None = None  # PDF hierhin schreiben
    text: Path | None = None  # Text hierhin schreiben
    weg: Versandweg | None = None  # E-Mail
    absender: str | None = None
    an: str | None = None  # sonst die E-Mail-Adresse des Kontakts
    bcc: str | None = None


def _nachricht(
    m: Mahnung, text: str, pdf: bytes, auftrag: Versandauftrag, an: str, jetzt: datetime
) -> EmailMessage:
    nachricht = EmailMessage()
    if auftrag.absender:
        nachricht["From"] = auftrag.absender
    nachricht["To"] = an
    if auftrag.bcc:
        nachricht["Bcc"] = auftrag.bcc
    nachricht["Subject"] = f"{m.stufe_name}: Rechnung {m.belegnummer or '—'}"
    nachricht["Date"] = format_datetime(jetzt.astimezone())
    adresse = parseaddr(auftrag.absender or "")[1]
    domain = Address(addr_spec=adresse).domain if "@" in adresse else None
    nachricht["Message-ID"] = make_msgid(domain=domain or None)
    nachricht.set_content(text)
    nachricht.add_attachment(
        pdf, maintype="application", subtype="pdf", filename=f"mahnung-{m.nr}.pdf"
    )
    return nachricht


def versende_mahnung(
    session: Session,
    nr: int,
    firma: Firma,
    e: MahnEinstellungen,
    auftrag: Versandauftrag,
    archiv: BelegArchiv | None,
    jetzt: datetime | None = None,
) -> Mahnung:
    if auftrag.pdf is None and auftrag.text is None and auftrag.weg is None:
        msg = "Wohin? Mindestens --pdf, --text oder --email angeben."
        raise MahnError(msg)
    jetzt = jetzt or datetime.now().replace(microsecond=0)
    m = pruefe_versendbar(session, nr, e, jetzt.date())
    kontakt = lade_kontakt(session, str(m.kontakt_id))
    text = mahntext(m, kontakt, firma, e)
    pdf = mahn_pdf(m, kontakt, firma, e, jetzt)
    an = None
    if auftrag.weg is not None:
        an = auftrag.an or kontakt.email
        if not an:
            msg = f"{kontakt.name} hat keine E-Mail-Adresse — mit --an angeben"
            raise MahnError(msg)
    wege = []
    try:
        if auftrag.pdf is not None:
            auftrag.pdf.write_bytes(pdf)
            wege.append("pdf")
        if auftrag.text is not None:
            auftrag.text.write_text(text, encoding="utf-8")
            wege.append("text")
        datei_hash = archiv.ablegen(pdf, ".pdf") if archiv is not None else None
    except OSError as fehler:
        msg = f"Mahnschreiben {nr} nicht geschrieben: {fehler} — nichts versendet"
        raise MahnError(msg) from fehler
    if auftrag.weg is not None and an is not None:
        try:
            auftrag.weg.sende(_nachricht(m, text, pdf, auftrag, an, jetzt))
        except (smtplib.SMTPException, OSError) as fehler:
            msg = f"E-Mail an {an} gescheitert: {fehler}"
            raise MahnError(msg) from fehler
        wege.append(auftrag.weg.name)
    return versende(session, nr, ", ".join(wege), e, datei_hash, jetzt)
