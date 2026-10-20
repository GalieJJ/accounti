"""Repository der Beleg-Kanäle: Gedächtnis, Webhook-Tokens, Zugänge."""

from __future__ import annotations

import hashlib
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
from accounti.models.kanaele import (
    AbgeholteNachricht,
    Absender,
    KanalZugang,
    WebhookToken,
)

SCHLUESSEL_LAENGE = 300
MESSAGE_ID_LAENGE = 500


def _kurz(text: str | None, laenge: int) -> str | None:
    if text is None:
        return None
    return text if len(text) <= laenge else text[: laenge - 1] + "…"


def _kennung(text: str, laenge: int) -> str:
    """Eine Kennung, die in die Spalte passt und eindeutig bleibt: zu lange Werte
    werden gekürzt und mit ihrem SHA-256 abgeschlossen — beim Speichern und beim
    Vergleichen gleich."""
    if len(text) <= laenge:
        return text
    return text[: laenge - 65] + "#" + hashlib.sha256(text.encode()).hexdigest()


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
    bedingung = KanalNachrichtRow.schluessel == _kennung(schluessel, SCHLUESSEL_LAENGE)
    if message_id:
        bedingung = or_(
            bedingung,
            KanalNachrichtRow.message_id == _kennung(message_id, MESSAGE_ID_LAENGE),
        )
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
            schluessel=_kennung(n.schluessel, SCHLUESSEL_LAENGE),
            message_id=(
                _kennung(n.message_id, MESSAGE_ID_LAENGE) if n.message_id else None
            ),
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
        ursprung = n.urspruenglich.get(datei_hash) or Absender()
        session.add(
            KanalNachrichtDateiRow(
                id=str(uuid4()),
                nachricht_id=str(n.id),
                nr=nr,
                datei_hash=datei_hash,
                absender=_kurz(ursprung.adresse, 320),
                absender_name=_kurz(ursprung.name, 200),
            )
        )


def _row_zu_nachricht(
    r: KanalNachrichtRow, dateien: list[KanalNachrichtDateiRow]
) -> AbgeholteNachricht:
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
        datei_hashes=[d.datei_hash for d in dateien],
        urspruenglich={
            d.datei_hash: Absender(adresse=d.absender, name=d.absender_name)
            for d in dateien
            if d.absender or d.absender_name
        },
        hinweis=r.hinweis,
    )


def _mit_dateien(
    session: Session, rows: list[KanalNachrichtRow]
) -> list[AbgeholteNachricht]:
    dateien: dict[str, list[KanalNachrichtDateiRow]] = {r.id: [] for r in rows}
    if rows:
        for d in session.scalars(
            select(KanalNachrichtDateiRow)
            .where(KanalNachrichtDateiRow.nachricht_id.in_(list(dateien)))
            .order_by(KanalNachrichtDateiRow.nr)
        ):
            dateien[d.nachricht_id].append(d)
    return [_row_zu_nachricht(r, dateien[r.id]) for r in rows]


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
    """Die erste Nachricht, mit der diese Datei kam — die der Neuaufnahme.

    Spätere Eingänge derselben Datei (Weiterleitung, Webhook) sind Dubletten und
    ändern den Hinweis auf den Kreditor nicht."""
    row = session.scalar(
        select(KanalNachrichtRow)
        .join(
            KanalNachrichtDateiRow,
            KanalNachrichtDateiRow.nachricht_id == KanalNachrichtRow.id,
        )
        .where(KanalNachrichtDateiRow.datei_hash == datei_hash)
        .order_by(KanalNachrichtRow.abgeholt_am)
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


def _aktives_token(session: Session, name: str) -> WebhookTokenRow | None:
    return session.scalar(
        select(WebhookTokenRow).where(
            WebhookTokenRow.name == name, WebhookTokenRow.widerrufen_am.is_(None)
        )
    )


def speichere_webhook_token(session: Session, t: WebhookToken) -> None:
    """Eindeutig ist der Name nur unter aktiven Tokens (Ersetzen nach Widerruf)."""
    if _aktives_token(session, t.name) is not None:
        msg = (
            f"Ein aktives Webhook-Token '{t.name}' gibt es schon — zum Ersetzen erst "
            f"widerrufen: accounti kanaele webhook widerrufen {t.name}"
        )
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
    rows = session.scalars(
        select(WebhookTokenRow).order_by(
            WebhookTokenRow.name, WebhookTokenRow.erstellt_am
        )
    )
    return [_row_zu_token(r) for r in rows]


def finde_webhook_token(session: Session, token_hash: str) -> WebhookToken | None:
    row = session.scalar(
        select(WebhookTokenRow).where(WebhookTokenRow.token_hash == token_hash)
    )
    return None if row is None else _row_zu_token(row)


def widerrufe_webhook_token(
    session: Session, name: str, zeitpunkt: datetime | None = None
) -> WebhookToken:
    """Widerruft das aktive Token dieses Namens (schon widerrufen: unverändert)."""
    row = _aktives_token(session, name) or session.scalar(
        select(WebhookTokenRow)
        .where(WebhookTokenRow.name == name)
        .order_by(WebhookTokenRow.erstellt_am.desc())
        .limit(1)
    )
    if row is None:
        msg = f"Webhook-Token '{name}' nicht gefunden"
        raise ValueError(msg)
    if row.widerrufen_am is None:
        row.widerrufen_am = zeitpunkt or datetime.now()
        session.flush()
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
