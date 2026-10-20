"""Repository der Beleg-Kanäle: Gedächtnis, Webhook-Tokens, Zugänge."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from accounti.db.tabellen_kanaele import (
    KanalNachrichtDateiRow,
    KanalNachrichtRow,
    KanalZugangRow,
    WebhookTokenRow,
)
from accounti.models.kanaele import AbgeholteNachricht, KanalZugang, WebhookToken


def _kurz(text: str | None, laenge: int) -> str | None:
    if text is None:
        return None
    return text if len(text) <= laenge else text[: laenge - 1] + "…"


# ---------------------------------------------------------------------------
# Gedächtnis: verarbeitete Nachrichten
# ---------------------------------------------------------------------------


def nachricht_bekannt(
    session: Session,
    kanal: str,
    quelle: str,
    schluessel: str,
    message_id: str | None = None,
) -> bool:
    """Wurde diese Nachricht (Schlüssel oder Message-ID) schon verarbeitet?"""
    bedingung = KanalNachrichtRow.schluessel == schluessel
    if message_id:
        bedingung = or_(bedingung, KanalNachrichtRow.message_id == message_id)
    treffer = session.scalar(
        select(KanalNachrichtRow.id)
        .where(
            KanalNachrichtRow.kanal == kanal,
            KanalNachrichtRow.quelle == quelle,
            bedingung,
        )
        .limit(1)
    )
    return treffer is not None


def merke_nachricht(session: Session, n: AbgeholteNachricht) -> None:
    session.add(
        KanalNachrichtRow(
            id=str(n.id),
            kanal=n.kanal,
            quelle=n.quelle,
            schluessel=n.schluessel,
            message_id=_kurz(n.message_id, 500),
            absender=_kurz(n.absender, 320),
            absender_name=_kurz(n.absender_name, 200),
            betreff=_kurz(n.betreff, 500),
            gesendet_am=n.gesendet_am,
            abgeholt_am=n.abgeholt_am,
            hinweis=n.hinweis,
        )
    )
    session.flush()  # Nachricht vor ihren Dateien (Fremdschlüssel)
    for nr, datei_hash in enumerate(n.datei_hashes, start=1):
        session.add(
            KanalNachrichtDateiRow(
                id=str(uuid4()), nachricht_id=str(n.id), nr=nr, datei_hash=datei_hash
            )
        )


def _row_zu_nachricht(r: KanalNachrichtRow, hashes: list[str]) -> AbgeholteNachricht:
    return AbgeholteNachricht(
        id=UUID(r.id),
        kanal=r.kanal,
        quelle=r.quelle,
        schluessel=r.schluessel,
        message_id=r.message_id,
        absender=r.absender,
        absender_name=r.absender_name,
        betreff=r.betreff,
        gesendet_am=r.gesendet_am,
        abgeholt_am=r.abgeholt_am,
        datei_hashes=hashes,
        hinweis=r.hinweis,
    )


def _mit_dateien(
    session: Session, rows: list[KanalNachrichtRow]
) -> list[AbgeholteNachricht]:
    hashes: dict[str, list[str]] = {r.id: [] for r in rows}
    if rows:
        dateien = session.scalars(
            select(KanalNachrichtDateiRow)
            .where(KanalNachrichtDateiRow.nachricht_id.in_(list(hashes)))
            .order_by(KanalNachrichtDateiRow.nr)
        )
        for d in dateien:
            hashes[d.nachricht_id].append(d.datei_hash)
    return [_row_zu_nachricht(r, hashes[r.id]) for r in rows]


def lade_nachrichten(
    session: Session,
    kanal: str | None = None,
    quelle: str | None = None,
    limit: int | None = None,
) -> list[AbgeholteNachricht]:
    """Verarbeitete Nachrichten, die jüngsten zuerst."""
    abfrage = select(KanalNachrichtRow).order_by(KanalNachrichtRow.abgeholt_am.desc())
    if kanal is not None:
        abfrage = abfrage.where(KanalNachrichtRow.kanal == kanal)
    if quelle is not None:
        abfrage = abfrage.where(KanalNachrichtRow.quelle == quelle)
    if limit is not None:
        abfrage = abfrage.limit(limit)
    return _mit_dateien(session, list(session.scalars(abfrage)))


def nachricht_zu_datei(session: Session, datei_hash: str) -> AbgeholteNachricht | None:
    """Die jüngste Nachricht, mit der diese Datei gekommen ist."""
    row = session.scalar(
        select(KanalNachrichtRow)
        .join(
            KanalNachrichtDateiRow,
            KanalNachrichtDateiRow.nachricht_id == KanalNachrichtRow.id,
        )
        .where(KanalNachrichtDateiRow.datei_hash == datei_hash)
        .order_by(KanalNachrichtRow.abgeholt_am.desc())
        .limit(1)
    )
    return None if row is None else _mit_dateien(session, [row])[0]


# ---------------------------------------------------------------------------
# Webhook-Tokens
# ---------------------------------------------------------------------------


def _row_zu_token(r: WebhookTokenRow) -> WebhookToken:
    return WebhookToken(
        id=UUID(r.id),
        name=r.name,
        token_hash=r.token_hash,
        erstellt_am=r.erstellt_am,
        widerrufen_am=r.widerrufen_am,
        zuletzt_genutzt_am=r.zuletzt_genutzt_am,
    )


def speichere_webhook_token(session: Session, t: WebhookToken) -> None:
    if session.scalar(select(WebhookTokenRow.id).where(WebhookTokenRow.name == t.name)):
        msg = f"Ein Webhook-Token '{t.name}' gibt es schon (erst widerrufen?)"
        raise ValueError(msg)
    try:
        with session.begin_nested():
            session.add(
                WebhookTokenRow(
                    id=str(t.id),
                    name=t.name,
                    token_hash=t.token_hash,
                    erstellt_am=t.erstellt_am,
                    widerrufen_am=t.widerrufen_am,
                    zuletzt_genutzt_am=t.zuletzt_genutzt_am,
                )
            )
    except IntegrityError as fehler:
        raise ValueError("Webhook-Token konnte nicht gespeichert werden") from fehler


def lade_webhook_tokens(session: Session) -> list[WebhookToken]:
    rows = session.scalars(select(WebhookTokenRow).order_by(WebhookTokenRow.name))
    return [_row_zu_token(r) for r in rows]


def finde_webhook_token(session: Session, token_hash: str) -> WebhookToken | None:
    row = session.scalar(
        select(WebhookTokenRow).where(WebhookTokenRow.token_hash == token_hash)
    )
    return None if row is None else _row_zu_token(row)


def widerrufe_webhook_token(
    session: Session, name: str, zeitpunkt: datetime | None = None
) -> WebhookToken:
    row = session.scalar(select(WebhookTokenRow).where(WebhookTokenRow.name == name))
    if row is None:
        msg = f"Webhook-Token '{name}' nicht gefunden"
        raise ValueError(msg)
    if row.widerrufen_am is None:
        row.widerrufen_am = zeitpunkt or datetime.now()
    return _row_zu_token(row)


def markiere_webhook_token_genutzt(
    session: Session, token_id: UUID, zeitpunkt: datetime | None = None
) -> None:
    row = session.get(WebhookTokenRow, str(token_id))
    if row is not None:
        row.zuletzt_genutzt_am = zeitpunkt or datetime.now()


# ---------------------------------------------------------------------------
# Zugänge (verschlüsselt)
# ---------------------------------------------------------------------------


def speichere_kanal_zugang(session: Session, z: KanalZugang) -> None:
    """Legt den Zugang an oder ersetzt das Chiffrat eines vorhandenen."""
    row = session.scalar(
        select(KanalZugangRow).where(
            KanalZugangRow.kanal == z.kanal, KanalZugangRow.name == z.name
        )
    )
    if row is None:
        session.add(
            KanalZugangRow(
                id=str(z.id),
                kanal=z.kanal,
                name=z.name,
                chiffrat=z.chiffrat,
                geaendert_am=z.geaendert_am,
            )
        )
    else:
        row.chiffrat = z.chiffrat
        row.geaendert_am = z.geaendert_am
    session.flush()


def lade_kanal_zugang(session: Session, kanal: str, name: str) -> KanalZugang | None:
    row = session.scalar(
        select(KanalZugangRow).where(
            KanalZugangRow.kanal == kanal, KanalZugangRow.name == name
        )
    )
    if row is None:
        return None
    return KanalZugang(
        id=UUID(row.id),
        kanal=row.kanal,
        name=row.name,
        chiffrat=row.chiffrat,
        geaendert_am=row.geaendert_am,
    )
