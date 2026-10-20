"""Geheimnisse der Kanäle (IMAP-Passwort, API-Schlüssel) im Tresor.

Dieselbe Verschlüsselung wie bei den Bankzugängen (AES-GCM, Schlüssel aus
``ACCOUNTI_SCHLUESSEL``). Das Chiffrat ist an Kanal und Name gebunden und lässt sich
keinem anderen Postfach unterschieben.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from accounti.bank.tresor import entschluessele, lade_schluessel, verschluessele
from accounti.db.repo_kanaele import lade_kanal_zugang, speichere_kanal_zugang
from accounti.models.kanaele import KanalZugang


def bezug(kanal: str, name: str) -> str:
    return f"kanal:{kanal}:{name}"


def speichere_zugang(
    session: Session,
    kanal: str,
    name: str,
    geheimnis: str,
    schluessel: str | None = None,
) -> None:
    schluessel = schluessel or lade_schluessel()
    chiffrat = verschluessele({"geheimnis": geheimnis}, schluessel, bezug(kanal, name))
    speichere_kanal_zugang(
        session,
        KanalZugang(
            kanal=kanal, name=name, chiffrat=chiffrat, geaendert_am=datetime.now()
        ),
    )


def entschluessele_zugang(zugang: KanalZugang, schluessel: str) -> str:
    daten = entschluessele(
        zugang.chiffrat, schluessel, bezug(zugang.kanal, zugang.name)
    )
    return daten["geheimnis"]


def lade_zugang(
    session: Session, kanal: str, name: str, schluessel: str | None = None
) -> str | None:
    """Das Geheimnis oder ``None``, wenn keins gespeichert ist."""
    zugang = lade_kanal_zugang(session, kanal, name)
    if zugang is None:
        return None
    return entschluessele_zugang(zugang, schluessel or lade_schluessel())
