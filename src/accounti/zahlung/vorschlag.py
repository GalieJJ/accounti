"""Zahlungsvorschlag: was ist zum Stichtag zu zahlen — und warum?

Skontofristen haben Vorrang vor Nettofälligkeiten: Ein Posten mit 2 % Skonto bei 10
Tagen und 30 Tagen Ziel ist hoch verzinst. Er wird vorgeschlagen, sobald seine
Skontofrist in den Planungshorizont fällt (``vorlauf_tage``), auch wenn das Nettoziel
noch Wochen entfernt ist. Alle anderen Posten kommen, wenn sie fällig sind. Früher
als nötig wird nichts gezahlt.

Der Stichtag ist der geplante Ausführungstag. Skonto zählt nur auf den unberührten
Posten (wie beim Ausgleich in ``opos``) und nur, solange die Frist am Stichtag läuft.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.anzeige import betrag_de, datum_de
from accounti.db.repo_zahlung import lade_zahlungssperren, posten_in_aktiven_laeufen
from accounti.db.repository import lade_kontakte, lade_posten
from accounti.models import Kontakt, OffenerPosten, PostenRichtung, PostenStatus
from accounti.models.zahlung import LaufStatus, Zahlungssperre
from accounti.zahlung.konfiguration import ZahlungEinstellungen

NULL = Decimal("0.00")


@dataclass(frozen=True)
class Vorschlagsposition:
    posten: OffenerPosten
    kontakt: Kontakt
    betrag: Decimal  # zu überweisen
    skonto: Decimal  # abgezogen
    art: str  # skonto, faellig, ueberfaellig
    frist: date  # Skontofrist oder Fälligkeit — danach wird sortiert
    grund: str


@dataclass(frozen=True)
class Ausgeschlossen:
    posten: OffenerPosten
    kontakt: Kontakt | None
    grund: str


@dataclass
class Zahlungsvorschlag:
    stichtag: date
    positionen: list[Vorschlagsposition] = field(default_factory=list)
    ausgeschlossen: list[Ausgeschlossen] = field(default_factory=list)

    @property
    def summe(self) -> Decimal:
        return sum((p.betrag for p in self.positionen), NULL)

    @property
    def skonto_summe(self) -> Decimal:
        return sum((p.skonto for p in self.positionen), NULL)


def _tage(n: int) -> str:
    return "1 Tag" if n == 1 else f"{n} Tagen"


def _prozent(wert: Decimal | None) -> str:
    return f"{(wert or NULL).normalize():f}".replace(".", ",")


def skonto_moeglich(p: OffenerPosten, ausfuehrung: date) -> bool:
    """Skonto auf den unberührten Posten, solange die Frist am Ausführungstag läuft."""
    return (
        p.skonto_betrag is not None
        and p.skonto_betrag > 0
        and p.skonto_bis is not None
        and p.skonto_bis >= ausfuehrung
        and p.restbetrag == p.betrag
    )


def _skonto_grund(p: OffenerPosten, stichtag: date) -> str:
    assert p.skonto_bis is not None
    n = (p.skonto_bis - stichtag).days
    wann = {0: "heute", 1: "morgen"}.get(n, f"in {n} Tagen")
    return (
        f"Skontofrist endet {wann} ({datum_de(p.skonto_bis)}): "
        f"{_prozent(p.skonto_prozent)} % = {betrag_de(p.skonto_betrag)} € sparen; "
        f"netto fällig erst am {datum_de(p.faellig_am)}"
    )


def _faellig_grund(p: OffenerPosten, stichtag: date) -> tuple[str, str]:
    n = (p.faellig_am - stichtag).days
    if n < 0:
        art = "ueberfaellig"
        grund = f"seit {_tage(-n)} überfällig (fällig am {datum_de(p.faellig_am)})"
    elif n == 0:
        art, grund = "faellig", f"heute fällig ({datum_de(p.faellig_am)})"
    else:
        art = "faellig"
        wann = "morgen" if n == 1 else f"in {n} Tagen"
        grund = f"fällig am {datum_de(p.faellig_am)} ({wann})"
    if p.skonto_betrag and p.skonto_bis is not None and p.skonto_bis < stichtag:
        grund += f"; Skonto verfallen am {datum_de(p.skonto_bis)}"
    if p.restbetrag != p.betrag:
        grund += "; Restbetrag nach Teilzahlung"
    return art, grund


def _position(
    p: OffenerPosten, k: Kontakt, stichtag: date, e: ZahlungEinstellungen
) -> Vorschlagsposition | None:
    """Die Position, wenn der Posten im Planungshorizont zu zahlen ist."""
    horizont = stichtag + timedelta(days=e.vorlauf_tage)
    mit_skonto = e.skonto_ziehen and skonto_moeglich(p, stichtag)
    if mit_skonto and p.skonto_bis is not None and p.skonto_betrag is not None:
        if p.skonto_bis <= horizont or p.faellig_am <= horizont:
            return Vorschlagsposition(
                posten=p,
                kontakt=k,
                betrag=p.restbetrag - p.skonto_betrag,
                skonto=p.skonto_betrag,
                art="skonto",
                frist=p.skonto_bis,
                grund=_skonto_grund(p, stichtag),
            )
        return None
    if p.faellig_am > horizont:
        return None
    art, grund = _faellig_grund(p, stichtag)
    return Vorschlagsposition(
        posten=p,
        kontakt=k,
        betrag=p.restbetrag,
        skonto=NULL,
        art=art,
        frist=p.faellig_am,
        grund=grund,
    )


def _ausschluss(
    pos: Vorschlagsposition,
    e: ZahlungEinstellungen,
    in_laeufen: Mapping[UUID, tuple[int, LaufStatus]],
    sperren: Mapping[UUID, Zahlungssperre],
) -> str | None:
    p = pos.posten
    sperre = sperren.get(p.kontakt_id)
    if sperre is not None:
        return f"Zahlungssperre: {sperre.grund} ({sperre.gesetzt_von})"
    if p.id in in_laeufen:
        nr, status = in_laeufen[p.id]
        return f"bereits in Zahlungslauf {nr} ({status.value})"
    if p.restbetrag < 0:
        return (
            f"Gutschrift über {betrag_de(p.restbetrag)} € — wird verrechnet, "
            "nicht überwiesen"
        )
    if e.mindestbetrag is not None and p.restbetrag < e.mindestbetrag:
        return f"unter dem Mindestbetrag von {betrag_de(e.mindestbetrag)} €"
    if e.hoechstbetrag is not None and p.restbetrag > e.hoechstbetrag:
        return f"über dem Höchstbetrag von {betrag_de(e.hoechstbetrag)} €"
    return None


def erstelle_vorschlag(
    posten: Iterable[OffenerPosten],
    kontakte: Mapping[UUID, Kontakt],
    stichtag: date,
    einstellungen: ZahlungEinstellungen,
    *,
    in_laeufen: Mapping[UUID, tuple[int, LaufStatus]] | None = None,
    sperren: Mapping[UUID, Zahlungssperre] | None = None,
    kontakt_ids: set[UUID] | None = None,
) -> Zahlungsvorschlag:
    """Vorschlagsliste: Skonto nach Frist zuerst, dann nach Fälligkeit."""
    vorschlag = Zahlungsvorschlag(stichtag=stichtag)
    for p in posten:
        if (
            p.richtung is not PostenRichtung.VERBINDLICHKEIT
            or p.status is PostenStatus.AUSGEGLICHEN
            or p.restbetrag == 0
            or (kontakt_ids is not None and p.kontakt_id not in kontakt_ids)
        ):
            continue
        k = kontakte.get(p.kontakt_id)
        if k is None:
            continue
        pos = _position(p, k, stichtag, einstellungen)
        if pos is None:
            continue
        grund = _ausschluss(pos, einstellungen, in_laeufen or {}, sperren or {})
        if grund is not None:
            vorschlag.ausgeschlossen.append(Ausgeschlossen(p, k, grund))
        else:
            vorschlag.positionen.append(pos)
    vorschlag.positionen.sort(
        key=lambda x: (x.art != "skonto", x.frist, x.posten.belegdatum)
    )
    return vorschlag


def lade_vorschlag(
    session: Session,
    stichtag: date,
    einstellungen: ZahlungEinstellungen,
    kontakt_ids: set[UUID] | None = None,
) -> Zahlungsvorschlag:
    return erstelle_vorschlag(
        lade_posten(
            session,
            richtung=PostenRichtung.VERBINDLICHKEIT,
            status={PostenStatus.OFFEN, PostenStatus.TEILBEZAHLT},
        ),
        {k.id: k for k in lade_kontakte(session)},
        stichtag,
        einstellungen,
        in_laeufen=posten_in_aktiven_laeufen(session),
        sperren=lade_zahlungssperren(session),
        kontakt_ids=kontakt_ids,
    )
