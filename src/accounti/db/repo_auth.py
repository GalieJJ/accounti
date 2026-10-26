"""Repository für Benutzer, Rollen, Sitzungen, API-Token und Ereignisse.

Die Funktionen arbeiten in der Sitzung des Aufrufers, schreiben mit ``flush()`` und
committen nicht.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import CursorResult, and_, case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from accounti.db.tabellen_auth import (
    ApiTokenRow,
    AuthEreignisRow,
    AuthMerkerRow,
    BenutzerRow,
    RollenzuordnungRow,
    SitzungRow,
    WiederherstellungscodeRow,
)
from accounti.models.auth import (
    ApiToken,
    AuthEreignis,
    Benutzer,
    Rolle,
    Rollenzuordnung,
    Sitzung,
    TokenRecht,
    Wiederherstellungscode,
)

# ---------------------------------------------------------------------------
# Benutzer
# ---------------------------------------------------------------------------

_BENUTZER_FELDER = (
    "name",
    "anzeigename",
    "passwort_hash",
    "totp_chiffrat",
    "totp_aktiv",
    "totp_letzter_schritt",
    "fehlversuche",
    "gesperrt_bis",
    "cli_fehlversuche",
    "cli_gesperrt_bis",
    "aktiv",
    "angelegt_am",
    "passwort_geaendert_am",
    "letzte_anmeldung_am",
)


def _zu_benutzer(r: BenutzerRow) -> Benutzer:
    werte: dict[str, Any] = {f: getattr(r, f) for f in _BENUTZER_FELDER}
    return Benutzer(id=UUID(r.id), **werte)


def anzahl_benutzer(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(BenutzerRow)) or 0


def speichere_benutzer(session: Session, b: Benutzer) -> None:
    """Legt an oder schreibt alle Felder zurück."""
    zeile = session.get(BenutzerRow, str(b.id))
    werte = {f: getattr(b, f) for f in _BENUTZER_FELDER}
    if zeile is None:
        msg = f"Benutzer {b.name!r} gibt es schon"
        if lade_benutzer(session, b.name) is not None:
            raise ValueError(msg)
        session.add(BenutzerRow(id=str(b.id), **werte))
        try:
            session.flush()
        except IntegrityError as fehler:  # gleichzeitig angelegt
            session.rollback()
            raise ValueError(msg) from fehler
        return
    for feld, wert in werte.items():
        setattr(zeile, feld, wert)
    session.flush()


def lade_benutzer(session: Session, name: str) -> Benutzer | None:
    zeile = session.scalar(select(BenutzerRow).where(BenutzerRow.name == name))
    return _zu_benutzer(zeile) if zeile else None


def lade_benutzer_id(session: Session, benutzer_id: UUID) -> Benutzer | None:
    zeile = session.get(BenutzerRow, str(benutzer_id), populate_existing=True)
    return _zu_benutzer(zeile) if zeile else None


def lade_alle_benutzer(session: Session) -> list[Benutzer]:
    zeilen = session.scalars(select(BenutzerRow).order_by(BenutzerRow.name))
    return [_zu_benutzer(z) for z in zeilen]


# Sperre bis „benutzer entsperren“ (Obergrenze der Fehlversuche in Folge erreicht)
DAUERHAFT = datetime(9999, 12, 31, 23, 59, 59)


@dataclass(frozen=True)
class Versuch:
    """Ein reservierter Versuch: Stand des Zählers danach und ob er sperrt."""

    fehlversuche: int
    gesperrt_bis: datetime | None
    gesperrt: bool


WEB = "web"
CLI = "cli"


def _spalten(kanal: str) -> tuple[Any, Any]:
    """Zähler und Sperre je Kanal: Browser (``web``) oder Server-Shell (``cli``)."""
    if kanal == CLI:
        return BenutzerRow.cli_fehlversuche, BenutzerRow.cli_gesperrt_bis
    return BenutzerRow.fehlversuche, BenutzerRow.gesperrt_bis


def reserviere_versuch(
    session: Session,
    benutzer_id: UUID,
    jetzt: datetime,
    *,
    schwelle: int,
    dauer: timedelta,
    obergrenze: int,
    kanal: str = WEB,
) -> Versuch | None:
    """Zählt einen Versuch **vor** der Prüfung — ein einziges ``UPDATE … SET
    fehlversuche = fehlversuche + 1 WHERE nicht gesperrt``, daher auch unter
    Parallelität nie mehr als ``schwelle`` Versuche je Sperrfenster.

    Der Zähler zählt Fehlversuche **in Folge** (über Sperren hinweg, erst Erfolg oder
    ``entsperren`` setzen ihn zurück): jeder ``schwelle``-te sperrt für ``dauer``,
    ab ``obergrenze`` bis ``entsperren``. Nach Ablauf einer Sperre gibt es wieder ein
    volles Fenster — nicht schon ein Fehlversuch sperrt erneut. ``None``: gesperrt.
    ``kanal``: Browser und CLI zählen getrennt — wer aus dem Netz flutet, sperrt die
    Anmeldung im Browser, nie den Einmalcode auf der Server-Shell.
    """
    zaehler, sperre = _spalten(kanal)
    neu = zaehler + 1
    zeile = session.execute(
        update(BenutzerRow)
        .where(
            BenutzerRow.id == str(benutzer_id),
            or_(sperre.is_(None), sperre <= jetzt),
            zaehler < obergrenze,
        )
        .values(
            {
                zaehler: neu,
                sperre: case(
                    (neu >= obergrenze, DAUERHAFT),
                    ((neu % schwelle) == 0, jetzt + dauer),
                    else_=sperre,
                ),
            }
        )
        .returning(zaehler, sperre)
        .execution_options(synchronize_session=False)
    ).first()
    if zeile is None:
        return None
    stand, bis = int(zeile[0]), zeile[1]
    return Versuch(stand, bis, bis is not None and bis > jetzt)


def setze_zurueck(
    session: Session, benutzer_id: UUID, kanal: str | None = None
) -> None:
    """Erfolg in einem Kanal (``web``/``cli``) oder ``entsperren`` (beide):
    Zähler auf null, keine Sperre."""
    kanaele = [kanal] if kanal is not None else [WEB, CLI]
    werte: dict[Any, Any] = {}
    for k in kanaele:
        zaehler, sperre = _spalten(k)
        werte[zaehler] = 0
        werte[sperre] = None
    session.execute(
        update(BenutzerRow)
        .where(BenutzerRow.id == str(benutzer_id))
        .values(werte)
        .execution_options(synchronize_session=False)
    )


def setze_sperre(session: Session, benutzer_id: UUID, bis: datetime | None) -> None:
    """Sperre von Hand — der Zähler der Fehlversuche bleibt, wie er ist."""
    session.execute(
        update(BenutzerRow)
        .where(BenutzerRow.id == str(benutzer_id))
        .values(gesperrt_bis=bis)
        .execution_options(synchronize_session=False)
    )


def merke_totp_schritt(session: Session, benutzer_id: UUID, schritt: int) -> bool:
    """Nimmt einen Zeitschritt nur an, wenn er jünger ist als der letzte.

    Ein einziges ``UPDATE … WHERE``: zwei gleichzeitige Anmeldungen mit demselben
    Code können nicht beide gewinnen (RFC 6238 5.2).
    """
    ergebnis = cast(
        CursorResult[Any],
        session.execute(
            update(BenutzerRow)
            .where(
                BenutzerRow.id == str(benutzer_id),
                or_(
                    BenutzerRow.totp_letzter_schritt.is_(None),
                    BenutzerRow.totp_letzter_schritt < schritt,
                ),
            )
            .values(totp_letzter_schritt=schritt)
            .execution_options(synchronize_session=False)
        ),
    )
    return ergebnis.rowcount == 1


# ---------------------------------------------------------------------------
# Rollen
# ---------------------------------------------------------------------------


def rollen_von(
    session: Session, benutzer_id: UUID, gesellschaft: str | None = None
) -> list[Rollenzuordnung]:
    abfrage = select(RollenzuordnungRow).where(
        RollenzuordnungRow.benutzer_id == str(benutzer_id)
    )
    if gesellschaft is not None:
        abfrage = abfrage.where(RollenzuordnungRow.gesellschaft == gesellschaft)
    zeilen = session.scalars(
        abfrage.order_by(RollenzuordnungRow.gesellschaft, RollenzuordnungRow.rolle)
    )
    return [
        Rollenzuordnung(UUID(z.benutzer_id), z.gesellschaft, Rolle(z.rolle))
        for z in zeilen
    ]


def fuege_rolle_hinzu(session: Session, z: Rollenzuordnung) -> bool:
    """Fügt die Rolle hinzu; ``False``, wenn sie schon da war."""
    if z in rollen_von(session, z.benutzer_id, z.gesellschaft):
        return False
    session.add(
        RollenzuordnungRow(
            id=str(uuid4()),
            benutzer_id=str(z.benutzer_id),
            gesellschaft=z.gesellschaft,
            rolle=z.rolle.value,
        )
    )
    session.flush()
    return True


def entferne_rolle(
    session: Session, benutzer_id: UUID, gesellschaft: str, rolle: Rolle
) -> bool:
    ergebnis = cast(
        CursorResult[Any],
        session.execute(
            delete(RollenzuordnungRow).where(
                RollenzuordnungRow.benutzer_id == str(benutzer_id),
                RollenzuordnungRow.gesellschaft == gesellschaft,
                RollenzuordnungRow.rolle == rolle.value,
            )
        ),
    )
    return ergebnis.rowcount > 0


def benutzer_mit_rolle(
    session: Session, rolle: Rolle, gesellschaft: str | None = None
) -> list[Benutzer]:
    """Benutzer mit der Rolle — in der Gesellschaft, ohne Angabe in irgendeiner."""
    abfrage = (
        select(BenutzerRow)
        .join(RollenzuordnungRow, RollenzuordnungRow.benutzer_id == BenutzerRow.id)
        .where(RollenzuordnungRow.rolle == rolle.value)
    )
    if gesellschaft is not None:
        abfrage = abfrage.where(RollenzuordnungRow.gesellschaft == gesellschaft)
    return [_zu_benutzer(z) for z in session.scalars(abfrage.distinct())]


# ---------------------------------------------------------------------------
# Wiederherstellungscodes
# ---------------------------------------------------------------------------


def ersetze_wiederherstellungscodes(
    session: Session, benutzer_id: UUID, hashes: list[str], jetzt: datetime
) -> None:
    """Neue Codes machen alle alten ungültig."""
    session.execute(
        update(WiederherstellungscodeRow)
        .where(
            WiederherstellungscodeRow.benutzer_id == str(benutzer_id),
            WiederherstellungscodeRow.verbraucht_am.is_(None),
        )
        .values(verbraucht_am=jetzt)
        .execution_options(synchronize_session=False)
    )
    for code_hash in hashes:
        session.add(
            WiederherstellungscodeRow(
                id=str(uuid4()),
                benutzer_id=str(benutzer_id),
                code_hash=code_hash,
                angelegt_am=jetzt,
            )
        )
    session.flush()


def offene_wiederherstellungscodes(
    session: Session, benutzer_id: UUID
) -> list[Wiederherstellungscode]:
    zeilen = session.scalars(
        select(WiederherstellungscodeRow)
        .where(
            WiederherstellungscodeRow.benutzer_id == str(benutzer_id),
            WiederherstellungscodeRow.verbraucht_am.is_(None),
        )
        .order_by(WiederherstellungscodeRow.id)
    )
    return [
        Wiederherstellungscode(
            id=UUID(z.id),
            benutzer_id=UUID(z.benutzer_id),
            code_hash=z.code_hash,
            angelegt_am=z.angelegt_am,
            verbraucht_am=z.verbraucht_am,
        )
        for z in zeilen
    ]


def verbrauche_wiederherstellungscode_mit_hash(
    session: Session, benutzer_id: UUID, code_hash: str, jetzt: datetime
) -> bool:
    """Ein Nachschlagen statt einer Prüfung je Code: markiert den passenden, noch
    offenen Code als verbraucht — ``False``, wenn es keinen gibt (oder er schon
    verbraucht war)."""
    ergebnis = cast(
        CursorResult[Any],
        session.execute(
            update(WiederherstellungscodeRow)
            .where(
                WiederherstellungscodeRow.benutzer_id == str(benutzer_id),
                WiederherstellungscodeRow.code_hash == code_hash,
                WiederherstellungscodeRow.verbraucht_am.is_(None),
            )
            .values(verbraucht_am=jetzt)
            .execution_options(synchronize_session=False)
        ),
    )
    return ergebnis.rowcount == 1


def verbrauche_wiederherstellungscode(
    session: Session, code_id: UUID, jetzt: datetime
) -> bool:
    """Markiert den Code als verbraucht — ``False``, wenn er es schon war."""
    ergebnis = cast(
        CursorResult[Any],
        session.execute(
            update(WiederherstellungscodeRow)
            .where(
                WiederherstellungscodeRow.id == str(code_id),
                WiederherstellungscodeRow.verbraucht_am.is_(None),
            )
            .values(verbraucht_am=jetzt)
            .execution_options(synchronize_session=False)
        ),
    )
    return ergebnis.rowcount == 1


# ---------------------------------------------------------------------------
# Sitzungen
# ---------------------------------------------------------------------------


def _zu_sitzung(r: SitzungRow) -> Sitzung:
    return Sitzung(
        id=UUID(r.id),
        token_hash=r.token_hash,
        benutzer_id=UUID(r.benutzer_id),
        gesellschaft=r.gesellschaft,
        angelegt_am=r.angelegt_am,
        zuletzt_aktiv_am=r.zuletzt_aktiv_am,
        laeuft_ab_am=r.laeuft_ab_am,
        beendet_am=r.beendet_am,
    )


def speichere_sitzung(session: Session, s: Sitzung) -> None:
    session.add(
        SitzungRow(
            id=str(s.id),
            token_hash=s.token_hash,
            benutzer_id=str(s.benutzer_id),
            gesellschaft=s.gesellschaft,
            angelegt_am=s.angelegt_am,
            zuletzt_aktiv_am=s.zuletzt_aktiv_am,
            laeuft_ab_am=s.laeuft_ab_am,
            beendet_am=s.beendet_am,
        )
    )
    session.flush()


def lade_sitzung_nach_hash(session: Session, token_hash: str) -> Sitzung | None:
    zeile = session.scalar(
        select(SitzungRow)
        .where(SitzungRow.token_hash == token_hash)
        .execution_options(populate_existing=True)
    )
    return _zu_sitzung(zeile) if zeile else None


def markiere_sitzung_aktiv(
    session: Session, sitzung_id: UUID, jetzt: datetime, gesellschaft: str | None = None
) -> None:
    werte: dict[str, Any] = {"zuletzt_aktiv_am": jetzt}
    if gesellschaft is not None:
        werte["gesellschaft"] = gesellschaft
    session.execute(
        update(SitzungRow)
        .where(SitzungRow.id == str(sitzung_id))
        .values(**werte)
        .execution_options(synchronize_session=False)
    )


def beende_sitzung(session: Session, sitzung_id: UUID, jetzt: datetime) -> None:
    session.execute(
        update(SitzungRow)
        .where(SitzungRow.id == str(sitzung_id), SitzungRow.beendet_am.is_(None))
        .values(beendet_am=jetzt)
        .execution_options(synchronize_session=False)
    )


def beende_sitzungen_von(session: Session, benutzer_id: UUID, jetzt: datetime) -> int:
    ergebnis = cast(
        CursorResult[Any],
        session.execute(
            update(SitzungRow)
            .where(
                SitzungRow.benutzer_id == str(benutzer_id),
                SitzungRow.beendet_am.is_(None),
            )
            .values(beendet_am=jetzt)
            .execution_options(synchronize_session=False)
        ),
    )
    return ergebnis.rowcount


# ---------------------------------------------------------------------------
# API-Token
# ---------------------------------------------------------------------------


def _zu_token(r: ApiTokenRow) -> ApiToken:
    return ApiToken(
        id=UUID(r.id),
        name=r.name,
        token_hash=r.token_hash,
        gesellschaft=r.gesellschaft,
        rechte=[TokenRecht(x) for x in r.rechte],
        angelegt_von=r.angelegt_von,
        angelegt_am=r.angelegt_am,
        gueltig_bis=r.gueltig_bis,
        widerrufen_am=r.widerrufen_am,
        zuletzt_genutzt_am=r.zuletzt_genutzt_am,
    )


def speichere_api_token(session: Session, t: ApiToken) -> None:
    """Eindeutig ist der Name unter den aktiven Token einer Gesellschaft."""
    msg = (
        f"Es gibt schon ein aktives Token {t.name!r} in {t.gesellschaft} — erst "
        "widerrufen"
    )
    if session.scalar(
        select(ApiTokenRow.id).where(
            ApiTokenRow.name == t.name,
            ApiTokenRow.gesellschaft == t.gesellschaft,
            ApiTokenRow.widerrufen_am.is_(None),
        )
    ):
        raise ValueError(msg)
    session.add(
        ApiTokenRow(
            id=str(t.id),
            name=t.name,
            token_hash=t.token_hash,
            gesellschaft=t.gesellschaft,
            rechte=[r.value for r in t.rechte],
            angelegt_von=t.angelegt_von,
            angelegt_am=t.angelegt_am,
            gueltig_bis=t.gueltig_bis,
            widerrufen_am=t.widerrufen_am,
            zuletzt_genutzt_am=t.zuletzt_genutzt_am,
        )
    )
    try:
        session.flush()
    except IntegrityError as fehler:  # gleichzeitig angelegt
        session.rollback()
        raise ValueError(msg) from fehler


def lade_api_token_nach_hash(session: Session, token_hash: str) -> ApiToken | None:
    zeile = session.scalar(
        select(ApiTokenRow)
        .where(ApiTokenRow.token_hash == token_hash)
        .execution_options(populate_existing=True)
    )
    return _zu_token(zeile) if zeile else None


def lade_api_tokens(session: Session) -> list[ApiToken]:
    zeilen = session.scalars(
        select(ApiTokenRow).order_by(ApiTokenRow.name, ApiTokenRow.angelegt_am)
    )
    return [_zu_token(z) for z in zeilen]


def widerrufe_api_token(
    session: Session, name: str, jetzt: datetime, gesellschaft: str
) -> None:
    """Das aktive Token ``name`` der Gesellschaft widerrufen."""
    ergebnis = cast(
        CursorResult[Any],
        session.execute(
            update(ApiTokenRow)
            .where(
                ApiTokenRow.name == name,
                ApiTokenRow.gesellschaft == gesellschaft,
                ApiTokenRow.widerrufen_am.is_(None),
            )
            .values(widerrufen_am=jetzt)
            .execution_options(synchronize_session=False)
        ),
    )
    if ergebnis.rowcount == 0:
        msg = f"Es gibt kein aktives Token {name!r} in {gesellschaft}"
        raise ValueError(msg)


def markiere_api_token_genutzt(
    session: Session, token_id: UUID, jetzt: datetime
) -> None:
    session.execute(
        update(ApiTokenRow)
        .where(ApiTokenRow.id == str(token_id))
        .values(zuletzt_genutzt_am=jetzt)
        .execution_options(synchronize_session=False)
    )


# ---------------------------------------------------------------------------
# Ereignisse
# ---------------------------------------------------------------------------


def protokolliere_ereignis(session: Session, e: AuthEreignis) -> None:
    session.add(
        AuthEreignisRow(
            id=str(e.id),
            zeitpunkt=e.zeitpunkt,
            art=e.art,
            benutzer=e.benutzer,
            gesellschaft=e.gesellschaft,
            quelle=e.quelle,
            ok=e.ok,
            hinweis=(e.hinweis or None) and e.hinweis[:500],
        )
    )
    session.flush()


def lade_ereignisse(
    session: Session,
    benutzer: str | None = None,
    grenze: int = 1000,
    *,
    neueste: bool = False,
    gesellschaften: set[str] | None = None,
    fremde: set[str] | None = None,
) -> list[AuthEreignis]:
    """Ereignisse aufsteigend nach Zeit — die ersten ``grenze`` oder, mit
    ``neueste``, die letzten ``grenze`` (absteigend gelesen, ``LIMIT``). Mit
    ``gesellschaften`` nur deren Ereignisse und die ohne Gesellschaft — von diesen
    nicht die über Benutzer aus ``fremde``."""
    abfrage = select(AuthEreignisRow)
    if benutzer is not None:
        abfrage = abfrage.where(AuthEreignisRow.benutzer == benutzer)
    if gesellschaften is not None:
        ohne = AuthEreignisRow.gesellschaft.is_(None)
        if fremde:
            ohne = and_(
                ohne,
                or_(
                    AuthEreignisRow.benutzer.is_(None),
                    AuthEreignisRow.benutzer.not_in(sorted(fremde)),
                ),
            )
        abfrage = abfrage.where(
            or_(ohne, AuthEreignisRow.gesellschaft.in_(sorted(gesellschaften)))
        )
    if neueste:
        abfrage = abfrage.order_by(
            AuthEreignisRow.zeitpunkt.desc(), AuthEreignisRow.id.desc()
        )
    else:
        abfrage = abfrage.order_by(AuthEreignisRow.zeitpunkt, AuthEreignisRow.id)
    zeilen = list(session.scalars(abfrage.limit(grenze)))
    if neueste:
        zeilen.reverse()
    return [
        AuthEreignis(
            id=UUID(z.id),
            zeitpunkt=z.zeitpunkt,
            art=z.art,
            benutzer=z.benutzer,
            gesellschaft=z.gesellschaft,
            quelle=z.quelle,
            ok=z.ok,
            hinweis=z.hinweis,
        )
        for z in zeilen
    ]


# ---------------------------------------------------------------------------
# Merker
# ---------------------------------------------------------------------------


def lade_merker(session: Session, schluessel: str) -> str | None:
    zeile = session.get(AuthMerkerRow, schluessel, populate_existing=True)
    return zeile.wert if zeile else None


def merker_mit_praefix(session: Session, praefix: str) -> list[str]:
    """Schlüssel der Merker, die mit ``praefix`` beginnen."""
    return list(
        session.scalars(
            select(AuthMerkerRow.schluessel).where(
                AuthMerkerRow.schluessel.startswith(praefix, autoescape=True)
            )
        )
    )


def loesche_merker(session: Session, schluessel: str) -> None:
    session.execute(delete(AuthMerkerRow).where(AuthMerkerRow.schluessel == schluessel))


def setze_merker_einmal(
    session: Session, schluessel: str, wert: str, jetzt: datetime
) -> str:
    """Setzt den Merker, wenn es ihn noch nicht gibt — gibt den gültigen Wert
    zurück (bei gleichzeitigem Setzen den, der zuerst kam)."""
    vorhanden = lade_merker(session, schluessel)
    if vorhanden is not None:
        return vorhanden
    session.add(AuthMerkerRow(schluessel=schluessel, wert=wert, gesetzt_am=jetzt))
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        gespeichert = lade_merker(session, schluessel)
        assert gespeichert is not None
        return gespeichert
    return wert
