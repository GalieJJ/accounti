"""Tabellen der Belegvollständigkeit & Ordnungsmäßigkeit (Baustein 7).

* ``journal`` — nur anfügen, jeder Eintrag per SHA-256 an seinen Vorgänger gekettet.
  Ändern und Löschen scheitern am ORM, unter SQLite zusätzlich an Triggern (per
  ``after_create`` angelegt).
* ``buchungskorrekturen`` — Storno (und Neubuchung) einer freigegebenen Buchung;
  ebenfalls nur anfügen.
* ``periodenabschluesse`` — festgeschriebene Monate. Ein ORM-Ereignis auf
  ``buchungssaetze`` verweigert wie die Jahressperre (``tabellen_abschluss``) Anlegen,
  Ändern und Löschen von Buchungen in einem gesperrten Monat
  (``PeriodeGesperrtError``, ein ``JahrGesperrtError``); angenommen wird nur der
  Stornovermerk.

Die Journal-Ereignisse auf der Sitzung (``accounti.pruefung.ereignisse``) hängen
``session_factory`` und ``init_db`` ein (``accounti.db.registriere_ereignisse``) — nicht
der Import dieses Moduls.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Connection,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    event,
    inspect,
    select,
)
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, Mapper, Session, mapped_column, object_session

from accounti.db import Base

if TYPE_CHECKING:
    from accounti.abschluss.konfiguration import Wirtschaftsjahr
    from accounti.abschluss.kontenrahmen import Kontenrahmen
from accounti.db.tabellen import BuchungssatzRow, UnveraenderbarError
from accounti.db.tabellen_abschluss import (
    JahrGesperrtError,
    jahressperre,
    nur_stornovermerk,
    sperrcache,
    vorab_geprueft,
)


class JournalRow(Base):
    """Journal aller buchungsrelevanten Vorgänge — nur anfügen, hash-verkettet."""

    __tablename__ = "journal"

    nr: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime)
    person: Mapped[str] = mapped_column(String(100))
    vorgang: Mapped[str] = mapped_column(String(40), index=True)
    objekt_typ: Mapped[str] = mapped_column(String(30))
    objekt_id: Mapped[str] = mapped_column(String(64))
    vorher: Mapped[str | None] = mapped_column(Text, nullable=True)
    nachher: Mapped[str | None] = mapped_column(Text, nullable=True)
    grund: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bezug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vorgaenger_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)

    __table_args__ = (Index("ix_journal_objekt", "objekt_typ", "objekt_id"),)


class BuchungskorrekturRow(Base):
    """Storno einer freigegebenen Buchung — nur anfügen."""

    __tablename__ = "buchungskorrekturen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_id: Mapped[str] = mapped_column(String(36), unique=True)
    storno_id: Mapped[str] = mapped_column(String(36), unique=True)
    neubuchung_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    datum: Mapped[date] = mapped_column(Date)
    grund: Mapped[str] = mapped_column(String(500))
    person: Mapped[str] = mapped_column(String(100))
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime)


@event.listens_for(JournalRow, "before_update")
@event.listens_for(JournalRow, "before_delete")
def _journal_nur_anfuegen(*_: object) -> None:
    raise UnveraenderbarError("Das Journal ist unveränderbar — Einträge nur anfügen")


@event.listens_for(BuchungskorrekturRow, "before_update")
@event.listens_for(BuchungskorrekturRow, "before_delete")
def _korrektur_nur_anfuegen(*_: object) -> None:
    raise UnveraenderbarError("Buchungskorrekturen sind unveränderbar")


def _trigger(tabelle: str, text: str) -> list[str]:
    return [
        f"CREATE TRIGGER {tabelle}_kein_{aktion.lower()} BEFORE {aktion} "
        f"ON {tabelle} BEGIN SELECT RAISE(ABORT, '{text}'); END"
        for aktion in ("UPDATE", "DELETE")
    ]


# SQLite sperrt auch rohes SQL; Postgres verlässt sich auf ORM-Sperre und Hash-Kette.
JOURNAL_TRIGGER = _trigger("journal", "Journal ist unveränderbar")
KORREKTUR_TRIGGER = _trigger(
    "buchungskorrekturen", "Buchungskorrekturen sind unveränderbar"
)


@event.listens_for(JournalRow.__table__, "after_create")
def _journal_trigger(_: object, verbindung: Connection, **__: object) -> None:
    if verbindung.dialect.name == "sqlite":
        for sql in JOURNAL_TRIGGER:
            verbindung.execute(sql_text(sql))


@event.listens_for(BuchungskorrekturRow.__table__, "after_create")
def _korrektur_trigger(_: object, verbindung: Connection, **__: object) -> None:
    if verbindung.dialect.name == "sqlite":
        for sql in KORREKTUR_TRIGGER:
            verbindung.execute(sql_text(sql))


# --- Monatssperre (Periodenabschluss) --------------------------------------------


class PeriodeGesperrtError(JahrGesperrtError):
    """Der Monat ist festgeschrieben — ändern erst nach ``accounti periode oeffnen``."""


class PeriodenabschlussRow(Base):
    """Ein festgeschriebener (oder wieder geöffneter) Monat."""

    __tablename__ = "periodenabschluesse"

    monat: Mapped[str] = mapped_column(String(7), primary_key=True)  # JJJJ-MM
    gesperrt: Mapped[bool] = mapped_column(Boolean)
    geschlossen_am: Mapped[datetime] = mapped_column(DateTime)
    geschlossen_von: Mapped[str] = mapped_column(String(100))
    geoeffnet_am: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    geoeffnet_von: Mapped[str | None] = mapped_column(String(100), nullable=True)
    grund: Mapped[str | None] = mapped_column(String(500), nullable=True)


def gesperrte_monate(verbindung: Connection) -> set[str]:
    if not verbindung.dialect.has_table(verbindung, PeriodenabschlussRow.__tablename__):
        return set()
    return set(
        verbindung.execute(
            select(PeriodenabschlussRow.monat).where(
                PeriodenabschlussRow.gesperrt.is_(True)
            )
        ).scalars()
    )


def monat_gesperrt(
    verbindung: Connection, monat: str, cache: dict[str, Any] | None = None
) -> bool:
    if cache is not None:
        if "monate" not in cache:
            cache["monate"] = gesperrte_monate(verbindung)
        return monat in cache["monate"]
    if not verbindung.dialect.has_table(verbindung, PeriodenabschlussRow.__tablename__):
        return False
    gesperrt = verbindung.execute(
        select(PeriodenabschlussRow.gesperrt).where(PeriodenabschlussRow.monat == monat)
    ).scalar()
    return bool(gesperrt)


def monatssperre(
    verbindung: Connection, monat: str, cache: dict[str, Any] | None = None
) -> PeriodeGesperrtError | None:
    """Der Fehler, wenn der Monat festgeschrieben ist — sonst ``None``."""
    if not monat_gesperrt(verbindung, monat, cache):
        return None
    return PeriodeGesperrtError(
        f"Monat {monat} ist festgeschrieben — Buchungen sind gesperrt "
        f"(Änderung nur nach accounti periode oeffnen {monat} --grund …)"
    )


def sperrfehler(
    verbindung: Connection, tag: date, cache: dict[str, Any] | None = None
) -> JahrGesperrtError | None:
    """Jahres- oder Monatssperre am Tag — der Fehler, sonst ``None``."""
    return jahressperre(verbindung, tag.year, cache) or monatssperre(
        verbindung, f"{tag:%Y-%m}", cache
    )


def erster_offener_tag(verbindung: Connection, ab: date) -> date:
    """Der erste Tag ab ``ab``, der weder im abgeschlossenen Jahr noch in einem
    festgeschriebenen Monat liegt."""
    tag = ab
    for _ in range(1200):  # höchstens 100 Jahre
        fehler = sperrfehler(verbindung, tag)
        if fehler is None:
            return tag
        if isinstance(fehler, PeriodeGesperrtError):
            tag = date(tag.year + tag.month // 12, tag.month % 12 + 1, 1)
        else:
            tag = date(tag.year + 1, 1, 1)
    raise JahrGesperrtError(f"Kein offener Tag ab {ab:%d.%m.%Y} gefunden")


def _monatssperre(verbindung: Connection, ziel: BuchungssatzRow) -> None:
    # das alte Datum steht dank active_history auch nach dem Ablauf in der Historie
    tage = {ziel.datum} if ziel.datum else set()
    tage |= {d for d in inspect(ziel).attrs.datum.history.deleted if d is not None}
    cache = sperrcache(ziel)
    for monat in sorted({f"{d:%Y-%m}" for d in tage}):
        if (fehler := monatssperre(verbindung, monat, cache)) is not None:
            raise fehler


# session.info: Rahmen der EB-Buchungen, die gerade angelegt werden (Saldovortrag)
_EROEFFNUNG = "accounti_eroeffnungsbuchungen"


@dataclass(eq=False)  # ein Rahmen ist er selbst — nicht gleich jedem gleichen Inhalts
class _Eroeffnung:
    ids: set[str]
    kontenrahmen: Kontenrahmen
    gewinnermittlung: str
    wirtschaftsjahr: Wirtschaftsjahr | None = None


@contextmanager
def eroeffnungsbuchungen(
    session: Session,
    kontenrahmen: Kontenrahmen,
    gewinnermittlung: str,
    wirtschaftsjahr: Wirtschaftsjahr | None = None,
) -> Iterator[set[str]]:
    """EB-Buchungen am 01.01. anlegen, auch wenn der Januar festgeschrieben ist —
    mit ``wirtschaftsjahr`` an dessen Beginn (abweichendes WJ: z. B. 01.07.,
    Belegnummer ``EB-<Jahr des WJ-Endes>``).

    Der Saldovortrag (und der erste Eröffnungssaldo) trägt die Schlussbilanz des
    Vorjahres vor: Er ändert weder die Verkehrszahlen noch die UStVA des Januars, und
    auf einen späteren Tag gebucht stimmten die Salden des Januars nicht mehr. Die
    Monatssperre nimmt deshalb genau diese Buchungen an — nur angelegt, nur mit der
    hier gemeldeten ID und nur in der Form einer EB-Buchung: am 01.01., ohne Steuer,
    Belegnummer ``EB-JJJJ``, kein Storno, eine Seite ein Saldenvortragskonto des
    Kontenrahmens, die andere ein Bestandskonto. Die Jahressperre gilt weiter;
    Rahmen lassen sich schachteln.
    """
    rahmen = _Eroeffnung(set(), kontenrahmen, gewinnermittlung, wirtschaftsjahr)
    stapel = session.info.get(_EROEFFNUNG)
    if not isinstance(stapel, list):
        stapel = session.info[_EROEFFNUNG] = []
    stapel.append(rahmen)
    try:
        yield rahmen.ids
    finally:
        stapel.remove(rahmen)
        if not stapel:
            session.info.pop(_EROEFFNUNG, None)


def _eb_form(ziel: BuchungssatzRow, rahmen: _Eroeffnung) -> bool:
    tag, kr = ziel.datum, rahmen.kontenrahmen
    v = kr.vortragskonten
    vortrag = {v.sachkonten, v.debitoren, v.kreditoren}
    seiten = [k for k in (ziel.soll_konto, ziel.haben_konto) if k not in vortrag]
    if len(seiten) != 1:  # genau eine Seite ein Saldenvortragskonto
        return False
    art = kr.art(seiten[0], rahmen.gewinnermittlung)  # type: ignore[arg-type]
    wj = rahmen.wirtschaftsjahr
    if wj is None:
        am_beginn, nummer = (tag.month, tag.day) == (1, 1), f"EB-{tag.year}"
    else:
        am_beginn, nummer = tag == wj.von, f"EB-{wj.jahr}"
    return (
        am_beginn
        and ziel.steuer_schluessel is None
        and not ziel.steuer_betrag
        and ziel.beleg_nummer == nummer
        and ziel.storno_von is None
        and ziel.storniert_durch is None
        and str(getattr(art, "value", art)) not in ("erfolg", "vortrag")
    )


def _eroeffnung(ziel: BuchungssatzRow) -> bool:
    session = object_session(ziel)
    stapel = session.info.get(_EROEFFNUNG) if session is not None else None
    if not isinstance(stapel, list):
        return False
    return any(
        isinstance(r, _Eroeffnung) and str(ziel.id) in r.ids and _eb_form(ziel, r)
        for r in stapel
    )


@event.listens_for(BuchungssatzRow, "before_insert")
def _neu_im_gesperrten_monat(
    _: Mapper[BuchungssatzRow], verbindung: Connection, ziel: BuchungssatzRow
) -> None:
    if not _eroeffnung(ziel):
        _monatssperre(verbindung, ziel)


@event.listens_for(BuchungssatzRow, "before_delete")
def _buchung_im_gesperrten_monat(
    _: Mapper[BuchungssatzRow], verbindung: Connection, ziel: BuchungssatzRow
) -> None:
    _monatssperre(verbindung, ziel)


@event.listens_for(BuchungssatzRow, "before_update")
def _aenderung_im_gesperrten_monat(
    _: Mapper[BuchungssatzRow], verbindung: Connection, ziel: BuchungssatzRow
) -> None:
    if not vorab_geprueft(ziel) and not nur_stornovermerk(ziel):
        _monatssperre(verbindung, ziel)
