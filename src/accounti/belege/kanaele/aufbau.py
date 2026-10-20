"""Kanäle aus der Konfiguration bauen — für ``accounti belege abholen``.

Geheimnisse werden erst beim Abholen ermittelt (``${VAR}`` oder Tresor): Ein
fehlendes Passwort eines Postfachs hält die anderen nicht auf.
"""

from __future__ import annotations

from functools import partial

from sqlalchemy.orm import Session, sessionmaker

from accounti.bank.tresor import TresorError
from accounti.belege.kanaele.abholung import AbholKanal, KanalError
from accounti.belege.kanaele.einstellungen import (
    EmailPostfach,
    KanalEinstellungen,
    loese_auf,
)
from accounti.belege.kanaele.email import EmailKanal
from accounti.belege.kanaele.gedaechtnis import DbGedaechtnis
from accounti.belege.kanaele.zugaenge import lade_zugang
from accounti.konfiguration import KonfigurationError

ABHOLBAR = ("ordner", "email", "connector")


def geheimnis_aus_tresor(
    make_session: sessionmaker[Session], kanal: str, name: str
) -> str | None:
    try:
        with make_session() as s:
            return lade_zugang(s, kanal, name)
    except TresorError as fehler:
        raise KanalError(f"{kanal} {name}: {fehler}") from fehler


def passwort_fuer(postfach: EmailPostfach, make_session: sessionmaker[Session]) -> str:
    """Passwort aus ``${VAR}`` oder aus dem Tresor — nie aus der Datei selbst."""
    if postfach.passwort:
        try:
            return loese_auf(postfach.passwort)
        except KonfigurationError as fehler:
            raise KanalError(f"Postfach {postfach.name}: {fehler}") from fehler
    passwort = geheimnis_aus_tresor(make_session, "email", postfach.name)
    if passwort is None:
        msg = (
            f"Kein Passwort für Postfach {postfach.name}: passwort: ${{VARIABLE}} im "
            f"Abschnitt belegkanaele.email oder 'accounti kanaele zugang email "
            f"{postfach.name}'"
        )
        raise KanalError(msg)
    return passwort


def baue_kanaele(
    kanal: str,
    einstellungen: KanalEinstellungen,
    make_session: sessionmaker[Session],
    quelle: str | None = None,
) -> list[AbholKanal]:
    """Die konfigurierten Quellen eines Kanals (alle oder nur ``quelle``)."""
    gedaechtnis = DbGedaechtnis(make_session)
    pruefung = einstellungen.pruefung()
    if kanal == "email":
        postfaecher = (
            [einstellungen.postfach(quelle)] if quelle else list(einstellungen.email)
        )
        if not postfaecher:
            msg = "Kein Postfach konfiguriert — Abschnitt belegkanaele.email anlegen"
            raise KonfigurationError(msg)
        return [
            EmailKanal(
                p,
                partial(passwort_fuer, p, make_session),
                gedaechtnis,
                pruefung,
            )
            for p in postfaecher
        ]
    if kanal == "webhook":
        msg = (
            "Der Kanal 'webhook' wird nicht abgeholt, er empfängt: "
            "accounti kanaele webhook starten"
        )
        raise KonfigurationError(msg)
    msg = (
        f"Kanal '{kanal}' kann nicht abgeholt werden. Verfügbar: "
        f"{', '.join(ABHOLBAR)} (Einzeldateien: accounti belege import)"
    )
    raise KonfigurationError(msg)
