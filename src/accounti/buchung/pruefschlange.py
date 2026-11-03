"""Prüfschlange (Supervisions-Queue) — für ``accounti review`` und die Oberfläche.

Buchungen ``zur Prüfung`` in fester Reihenfolge (Datum, dann ID), je Eintrag alles,
was die Entscheidung braucht: Buchung, Umsatz, Beleg, Kontakt, **Herkunft und
Begründung**, Geschwister, Rückfragen, Aufgaben, Belegfreiheit bzw. Nachforderung,
Sperre und der ``stand`` — ein Fingerabdruck der ganzen Buchungszeile. Jede ändernde
Funktion holt zuerst die Schreibsperre (``journal.schreibsperre``), liest dann die
Zeile und vergleicht den Stand: Zwei Personen an derselben Queue oder ein Doppelklick
erzeugen so nie still ein Storno (``StandVeraltetError``). Gebucht wird nur über
``pruefung.storno`` (Baustein 7).

Alles in der Sitzung des Aufrufers — flush statt commit.
"""

from __future__ import annotations

import enum
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounti.aufgaben import (
    AufgabenEinstellungen,
    halte_rueckfrage_fest,
    kommentare_zu,
    schliesse_wenn_erledigt,
)
from accounti.aufgaben.erzeugung import RUECKFRAGE, Rueckfrage
from accounti.belege.zuordnung import beleg_zur_buchung
from accounti.buchung.konten import (
    KontoError,
    finanzkonto_fehler,
    ist_personenkontonummer,
    pruefe_kontonummer,
    soll_gleich_haben,
)
from accounti.db.repo_aufgaben import lade_aufgaben
from accounti.db.repo_kontierung import lade_kontierungsgruende, lade_kontierungsgrund
from accounti.db.repository import (
    finde_buchung,
    lade_bankkonten,
    lade_buchungen,
    lade_buchungen_zu,
    lade_kontakte,
    lade_transaktion,
)
from accounti.db.tabellen import BuchungssatzRow
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Beleg,
    Buchungssatz,
    BuchungStatus,
    Kontakt,
    Transaktion,
    TransaktionQuelle,
)
from accounti.models.aufgaben import AKTIVE_STATUS, Aufgabe, Kommentar, Objekt
from accounti.pruefung.journal import kanonisch, schnappschuss, schreibsperre
from accounti.pruefung.storno import (
    VORSCHLAG,
    Korrektur,
    Korrekturumgebung,
    SteuerOptionen,
    kontenplan,
    korrigiere,
    steuer_befunde,
    steuer_optionen,
    storniere,
)
from accounti.pruefung.storno import freigeben as storno_freigeben

if TYPE_CHECKING:
    from accounti.elster.konfiguration import ElsterEinstellungen
    from accounti.models.kontierung import Feld, Kontierungsregel
    from accounti.pruefung.einstellungen import BelegfreiRegel, PruefEinstellungen
    from accounti.pruefung.perioden import Sperre

JE_SEITE = 200
KONTIERUNG_PRUEFEN = "kontierung_pruefen"
BELEG_FEHLT = "beleg_fehlt"
# Quellen, aus denen eine Korrektur eine Regel lernen darf — nicht Kreditkarte,
# Anlagen, Marktplatz, OPOS (eine Regel aus „VISA“ oder einer AfA wäre Unsinn)
REGEL_QUELLEN = frozenset({"regelwerk", "llm", "standard"})
GRUND_MAX = 500  # buchungskorrekturen.grund
AN_MAX = 100  # aufgaben.zustaendig


class Ansicht(str, enum.Enum):
    OFFEN = "offen"  # ohne offene Rückfrage
    ZURUECKGESTELLT = "zurueckgestellt"  # mit offener Rückfrage


class PruefschlangeError(ValueError):
    """Die Aktion ist so nicht möglich — ``status`` für die Oberfläche (409/422)."""

    status = 422

    def __init__(
        self, meldung: str, *, feld: str | None = None, stand: str | None = None
    ) -> None:
        super().__init__(meldung)
        self.meldung = meldung
        self.feld = feld
        self.stand = stand


class BuchungFehltError(PruefschlangeError):
    status = 404


class StandVeraltetError(PruefschlangeError):
    """Die Buchung hat sich seit der Anzeige geändert."""

    status = 409


class NichtInPruefungError(PruefschlangeError):
    """Kein Vorschlag mehr — Änderung nur per Storno (``/buchungen/{id}``)."""

    status = 409


class SchonZurueckgestelltError(PruefschlangeError):
    status = 409


class PruefregelError(PruefschlangeError):
    """Die Prüfregel ``steuerschluessel_konto`` meldet einen Fehler — so wird die
    Buchung nicht freigegeben (erst korrigieren)."""

    status = 422


class RegelBestaetigenError(PruefschlangeError):
    """Die Regel träfe andere Gegenparteien bzw. jeden Kauf über einen
    Zahlungsdienst, oder der Umsatz hat keinen Namen der Gegenpartei — gespeichert
    wird sie nur mit Bestätigung (``LernWunsch``).
    ``vorschau`` zeigt, was sie träfe."""

    status = 422

    def __init__(self, meldung: str, *, vorschau: Any) -> None:
        super().__init__(meldung, feld="muster")
        self.vorschau = vorschau


# --- Stand -------------------------------------------------------------------------


def stand_der_zeile(zeile: Any) -> str:
    """SHA-256 über den kanonischen Schnappschuss der ganzen Zeile (16 Hex-Zeichen)."""
    daten = schnappschuss(BuchungssatzRow.__table__, zeile)  # type: ignore[arg-type]
    return hashlib.sha256((kanonisch(daten) or "").encode()).hexdigest()[:16]


def _zeile(session: Session, buchung_id: str) -> Any:
    t = BuchungssatzRow.__table__
    return (
        session.connection()
        .execute(select(t).where(t.c.id == buchung_id))
        .mappings()
        .first()
    )


def stand(session: Session, buchung_id: UUID | str) -> str:
    zeile = _zeile(session, str(buchung_id))
    if zeile is None:
        raise BuchungFehltError(f"Buchung {str(buchung_id)[:8]} nicht gefunden")
    return stand_der_zeile(zeile)


def _sperren_und_pruefen(
    session: Session,
    buchung_id: str,
    erwartet: str | None,
    nur_vorschlaege: bool,
) -> Buchungssatz:
    """Erst die Schreibsperre, dann lesen und vergleichen — kein zweiter Schreiber
    ändert die Zeile zwischen Vergleich und Änderung."""
    try:
        b = finde_buchung(session, buchung_id)
    except ValueError as fehler:
        raise BuchungFehltError(str(fehler)) from fehler
    schreibsperre(session.connection())
    zeile = _zeile(session, str(b.id))
    if zeile is None:  # pragma: no cover — zwischen Suche und Sperre gelöscht
        raise BuchungFehltError(f"Buchung {str(b.id)[:8]} nicht gefunden")
    aktuell = stand_der_zeile(zeile)
    if nur_vorschlaege and BuchungStatus(zeile["status"]) not in VORSCHLAG:
        raise NichtInPruefungError(
            f"Buchung {str(b.id)[:8]} ist nicht mehr in der Prüfung "
            f"({zeile['status']}) — Korrektur nur per Storno in der Buchungsansicht",
            stand=aktuell,
        )
    if erwartet is not None and erwartet != aktuell:
        raise StandVeraltetError(
            f"Buchung {str(b.id)[:8]} wurde inzwischen geändert — bitte die aktuelle "
            "Fassung prüfen",
            stand=aktuell,
        )
    session.expire_all()  # die Fachfunktion liest den Stand unter der Sperre
    return finde_buchung(session, str(b.id))


# --- Herkunft --------------------------------------------------------------------


@dataclass(frozen=True)
class Herkunft:
    quelle: str | None  # regelwerk, llm, beleg, …, korrektur, storno — None: unbekannt
    text: str  # Begründung (leer: keine gespeichert)
    regel: str | None = None
    modell: str | None = None
    gespeichert: bool = True  # aus kontierungsgruende (sonst abgeleitet)

    @property
    def bekannt(self) -> bool:
        return bool(self.text)


KEINE = Herkunft(None, "", gespeichert=False)


def _abgeleitet(session: Session, b: Buchungssatz) -> Herkunft:
    """Ohne gespeicherten Grund: was Bausteine 4, 5, 7, 11 anderswo festhielten."""
    from accounti.db.repo_anlagen import lade_afa_vorgaenge
    from accounti.db.repo_pruefung import korrektur_zu
    from accounti.db.repository import lade_abgleiche, lade_beleg, lade_zuordnungen
    from accounti.models import AbgleichStatus

    korrektur = korrektur_zu(session, b.id)
    if korrektur is not None and b.id != korrektur.original_id:
        art = "storno" if b.id == korrektur.storno_id else "korrektur"
        return Herkunft(
            art, f"{korrektur.person}: {korrektur.grund}", gespeichert=False
        )
    afa = [v for v in lade_afa_vorgaenge(session) if v.buchung_id == b.id]
    if afa:
        return Herkunft(
            "anlagen", " | ".join(v.begruendung for v in afa), gespeichert=False
        )
    if b.transaktion_id is not None:
        for a in lade_abgleiche(session, status={AbgleichStatus.BESTAETIGT}):
            if a.transaktion_id == b.transaktion_id:
                return Herkunft("beleg", a.begruendung, gespeichert=False)
        for z in lade_zuordnungen(session, transaktion_praefix=str(b.transaktion_id)):
            if z.transaktion_id == b.transaktion_id:
                return Herkunft("opos", z.begruendung, gespeichert=False)
    if b.beleg_id is not None:
        beleg = lade_beleg(session, b.beleg_id)
        if beleg is not None and beleg.pruef_grund:
            return Herkunft("beleg", beleg.pruef_grund, gespeichert=False)
        if beleg is not None and beleg.kontakt_id is not None:
            kontakt = next(
                (k for k in lade_kontakte(session) if k.id == beleg.kontakt_id), None
            )
            if kontakt is not None and kontakt.pruef_grund:
                return Herkunft("kontakt", kontakt.pruef_grund, gespeichert=False)
    return KEINE


def herkunft(session: Session, buchung: Buchungssatz) -> Herkunft:
    g = lade_kontierungsgrund(session, buchung.id)
    if g is not None:
        return Herkunft(g.quelle, g.begruendung, g.regel, g.modell)
    return _abgeleitet(session, buchung)


# --- Liste ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Eintrag:
    buchung: Buchungssatz
    umsatz: Transaktion | None
    herkunft: Herkunft
    zurueckgestellt: bool


@dataclass(frozen=True)
class Seite:
    eintraege: list[Eintrag]
    gesamt: int
    seite: int
    seiten: int
    zurueckgestellt: int  # Anzahl in der anderen Ansicht (Zähler)
    offen: int


def _zurueckgestellte(session: Session) -> set[str]:
    """Buchungen mit offener Rückfrage (Aufgabe ``rueckfrage``, Baustein 8)."""
    return {
        a.objekt.id
        for a in lade_aufgaben(session, art=RUECKFRAGE, status=AKTIVE_STATUS)
        if a.objekt.typ == "buchung"
    }


def anzahl_offen(session: Session) -> int:
    """Offene Vorschläge ohne die zurückgestellten — dieselbe Zahl wie die Ansicht
    „Offen“, aber als ``COUNT`` (Zähler der Navigation, Baustein 10c P1)."""
    pruefung = BuchungssatzRow.status == BuchungStatus.ZUR_PRUEFUNG.value
    alle = session.scalar(
        select(func.count()).select_from(BuchungssatzRow).where(pruefung)
    )
    zurueck = _zurueckgestellte(session)
    davon = (
        session.scalar(
            select(func.count())
            .select_from(BuchungssatzRow)
            .where(pruefung, BuchungssatzRow.id.in_(zurueck))
        )
        if zurueck
        else 0
    )
    return int(alle or 0) - int(davon or 0)


def _reihe(session: Session) -> tuple[list[Buchungssatz], set[str]]:
    buchungen = sorted(
        lade_buchungen(session, status={BuchungStatus.ZUR_PRUEFUNG}),
        key=lambda b: (b.datum, str(b.id)),
    )
    return buchungen, _zurueckgestellte(session)


def _in_ansicht(b: Buchungssatz, zurueck: set[str], ansicht: Ansicht) -> bool:
    return (str(b.id) in zurueck) == (ansicht is Ansicht.ZURUECKGESTELLT)


def ids_der_ansicht(session: Session, ansicht: Ansicht = Ansicht.OFFEN) -> list[UUID]:
    buchungen, zurueck = _reihe(session)
    return [b.id for b in buchungen if _in_ansicht(b, zurueck, ansicht)]


def lade_pruefschlange(
    session: Session, ansicht: Ansicht = Ansicht.OFFEN, seite: int = 1
) -> Seite:
    buchungen, zurueck = _reihe(session)
    alle = [b for b in buchungen if _in_ansicht(b, zurueck, ansicht)]
    zurueck_anzahl = sum(1 for b in buchungen if str(b.id) in zurueck)
    seiten = max(1, -(-len(alle) // JE_SEITE))
    seite = min(max(1, seite), seiten)
    teil = alle[(seite - 1) * JE_SEITE : seite * JE_SEITE]
    gruende = lade_kontierungsgruende(session, [b.id for b in teil])
    eintraege = []
    for b in teil:
        g = gruende.get(b.id)
        h = (
            Herkunft(g.quelle, g.begruendung, g.regel, g.modell)
            if g is not None
            else _abgeleitet(session, b)
        )
        tx = lade_transaktion(session, b.transaktion_id) if b.transaktion_id else None
        eintraege.append(Eintrag(b, tx, h, str(b.id) in zurueck))
    return Seite(
        eintraege,
        len(alle),
        seite,
        seiten,
        zurueck_anzahl,
        len(buchungen) - zurueck_anzahl,
    )


@dataclass(frozen=True)
class Position:
    nr: int  # 1-basiert, 0: nicht (mehr) in der Ansicht
    gesamt: int
    vorher: UUID | None
    nachher: UUID | None


def position(
    session: Session, buchung_id: UUID | str, ansicht: Ansicht = Ansicht.OFFEN
) -> Position:
    ids = ids_der_ansicht(session, ansicht)
    ziel = UUID(str(buchung_id))
    if ziel not in ids:
        return Position(0, len(ids), None, ids[0] if ids else None)
    i = ids.index(ziel)
    return Position(
        i + 1,
        len(ids),
        ids[i - 1] if i > 0 else None,
        ids[i + 1] if i + 1 < len(ids) else None,
    )


def naechster(
    session: Session, nach: Buchungssatz, ansicht: Ansicht = Ansicht.OFFEN
) -> UUID | None:
    """Der Eintrag nach ``nach`` in der Reihenfolge — sonst der erste, sonst None."""
    buchungen, zurueck = _reihe(session)
    alle = [b for b in buchungen if _in_ansicht(b, zurueck, ansicht)]
    schluessel = (nach.datum, str(nach.id))
    for b in alle:
        if (b.datum, str(b.id)) > schluessel:
            return b.id
    rest = [b for b in alle if b.id != nach.id]
    return rest[0].id if rest else None


# --- Arbeitsfläche ------------------------------------------------------------------


@dataclass
class Arbeitsflaeche:
    buchung: Buchungssatz
    umsatz: Transaktion | None
    beleg: Beleg | None
    kontakt: Kontakt | None
    herkunft: Herkunft
    stand: str
    geschwister: list[Buchungssatz] = field(default_factory=list)
    rueckfragen: list[Kommentar] = field(default_factory=list)
    aufgaben: list[Aufgabe] = field(default_factory=list)  # der Buchung, aktiv
    nachforderung: list[Aufgabe] = field(default_factory=list)  # beleg_fehlt, aktiv
    belegfrei: BelegfreiRegel | None = None
    sperre: Sperre | None = None
    zurueckgestellt: bool = False
    regel_moeglich: bool = False
    sachkonto_lernbar: bool = False
    steuer: SteuerOptionen | None = None
    # Prüfregel steuerschluessel_konto: (Schwere, Text) — ein Fehler sperrt Freigeben
    steuer_befunde: list[tuple[Any, str]] = field(default_factory=list)

    @property
    def freigabe_gesperrt(self) -> bool:
        return any(_ist_fehler(schwere) for schwere, _ in self.steuer_befunde)

    @property
    def ist_vorschlag(self) -> bool:
        return self.buchung.status in VORSCHLAG


def _ist_fehler(schwere: Any) -> bool:
    from accounti.models.pruefung import Schwere

    return bool(schwere is Schwere.FEHLER)


def _kontakt(session: Session, b: Buchungssatz, beleg: Beleg | None) -> Kontakt | None:
    kontakte = lade_kontakte(session)
    if beleg is not None and beleg.kontakt_id is not None:
        treffer = next((k for k in kontakte if k.id == beleg.kontakt_id), None)
        if treffer is not None:
            return treffer
    for konto in (b.soll_konto, b.haben_konto):
        for k in kontakte:
            if konto in (k.kreditor_konto, k.debitor_konto):
                return k
    return None


def _personenkonto(konto: str) -> bool:
    return ist_personenkontonummer(konto)


def lade_eintrag(
    session: Session,
    buchung_id: UUID | str,
    *,
    pruefung: PruefEinstellungen | None = None,
    buchhaltung: Buchhaltung | None = None,
    elster: ElsterEinstellungen | None = None,
) -> Arbeitsflaeche:
    """Alles für die Entscheidung über eine Buchung. Mit ``buchhaltung`` auch die
    Befunde der Prüfregel ``steuerschluessel_konto`` (``steuer_befunde``) und die
    Steuerauswahl nach den Konten der Gesellschaft (``steuer_optionen`` mit Kontenplan:
    ein Erlös auf einer Quittung ist keine Eingangsbuchung; Runde 8, g7w R7-3) — mit
    ``elster`` (steuerrelevante Konten, Funktionskonten) wie ``korrigiere``
    (Folgepaket F, g8w G8R-2)."""
    from accounti.aufgaben import aufgaben_zu
    from accounti.models.aufgaben import KommentarArt
    from accounti.pruefung.perioden import sperre_am

    try:
        b = finde_buchung(session, str(buchung_id))
    except ValueError as fehler:
        raise BuchungFehltError(str(fehler)) from fehler
    tx = lade_transaktion(session, b.transaktion_id) if b.transaktion_id else None
    beleg = beleg_zur_buchung(session, b)
    objekt = Objekt("buchung", b.id)
    aufgaben = [a for a in aufgaben_zu(session, objekt) if a.aktiv]
    geschwister = [
        x
        for x in lade_buchungen_zu(session, b.transaktion_id, b.beleg_id)
        if x.id != b.id
    ]
    h = herkunft(session, b)
    flaeche = Arbeitsflaeche(
        buchung=b,
        umsatz=tx,
        beleg=beleg,
        kontakt=_kontakt(session, b, beleg),
        herkunft=h,
        stand=stand(session, b.id),
        geschwister=sorted(geschwister, key=lambda x: (x.datum, str(x.id))),
        rueckfragen=[
            k
            for k in kommentare_zu(session, objekt)
            if k.art is KommentarArt.RUECKFRAGE
        ],
        aufgaben=aufgaben,
        zurueckgestellt=any(a.art == RUECKFRAGE for a in aufgaben),
        sperre=sperre_am(session, b.datum),
        steuer=steuer_optionen(
            b,
            beleg if beleg and beleg.id == b.beleg_id else None,
            kontenplan(session, buchhaltung, elster)
            if buchhaltung is not None
            else None,
        ),
    )
    if tx is not None:
        flaeche.nachforderung = [
            a
            for a in aufgaben_zu(session, Objekt("transaktion", tx.id))
            if a.art == BELEG_FEHLT and a.aktiv
        ]
        if beleg is None and pruefung is not None:
            flaeche.belegfrei = pruefung.belegfrei_nach_regel(
                tx.verwendungszweck, tx.gegenkonto_name
            )
    flaeche.regel_moeglich = regel_lernbar(h, tx is not None)
    if buchhaltung is not None and flaeche.ist_vorschlag:
        flaeche.steuer_befunde = steuer_befunde(session, b, buchhaltung, pruefung)
    flaeche.sachkonto_lernbar = (
        tx is None
        and b.beleg_id is not None
        and any(_personenkonto(k) for k in (b.soll_konto, b.haben_konto))
    )
    return flaeche


# --- Aktionen ---------------------------------------------------------------------


def _schliesse_aufgaben(
    session: Session, b: Buchungssatz, grund: str, person: str
) -> None:
    """Die Entscheidung erledigt Rückfrage und ``kontierung_pruefen`` sofort (sonst
    erst der nächste Aufgabenlauf)."""
    objekt = Objekt("buchung", b.id)
    for art in (KONTIERUNG_PRUEFEN, RUECKFRAGE):
        schliesse_wenn_erledigt(session, art, objekt, grund, von=person)


def freigeben(
    session: Session,
    buchung_id: UUID | str,
    person: str,
    stand: str | None = None,
    *,
    nur_vorschlaege: bool = True,
    umgebung: Korrekturumgebung | None = None,
) -> tuple[Buchungssatz, bool]:
    """Vorschlag → ``geprueft`` (CLI ``bestaetige``: auch ``auto``, ohne Stand).

    Mit ``umgebung`` prüft die Freigabe die Prüfregel ``steuerschluessel_konto``
    wie eine Korrektur: Meldet sie einen Fehler (Vorsteuer auf einer Privatentnahme,
    Automatikkonto ohne Schlüssel …), wird nicht freigegeben (``PruefregelError``)
    — eine Korrektur mit denselben Werten lehnt ``korrigiere`` ebenso ab."""
    b = _sperren_und_pruefen(session, str(buchung_id), stand, nur_vorschlaege)
    aendert = b.status in VORSCHLAG or b.status is BuchungStatus.AUTO_GEBUCHT
    gleich = soll_gleich_haben(b.soll_konto, b.haben_konto)
    if gleich is not None and aendert:
        # Altfall „1210 an 1210“ (Prüfregel soll_gleich_haben): nicht ohne Hinweis
        # als geprüft festschreiben (gw2-merge B3) — auch ohne Umgebung (REST)
        raise PruefregelError(
            f"Buchung {str(b.id)[:8]} ({b.soll_konto} an {b.haben_konto}): {gleich} "
            "— so nicht freigeben, erst korrigieren (Gegenkonto der Bewegung)"
        )
    if umgebung is not None and aendert:  # schon geprüft/korrigiert/exportiert: nichts
        fehler = [
            text
            for schwere, text in steuer_befunde(
                session, b, umgebung.buchhaltung, umgebung.pruefung
            )
            if _ist_fehler(schwere)
        ]
        if fehler:
            schluessel = b.steuer_schluessel if b.steuer_schluessel is not None else "—"
            raise PruefregelError(
                f"Buchung {str(b.id)[:8]} ({b.soll_konto} an {b.haben_konto}, "
                f"Schlüssel {schluessel}): " + "; ".join(fehler) + " — so nicht "
                "freigeben, erst Steuerschlüssel oder Konto korrigieren"
            )
    neu, geaendert = storno_freigeben(session, str(b.id), von=person)
    if geaendert:
        _schliesse_aufgaben(session, neu, f"Buchung geprüft von {person}", person)
    session.flush()
    return neu, geaendert


@dataclass(frozen=True)
class Aenderung:
    soll: str
    haben: str
    steuer: int | None = None
    ohne_steuer: bool = False
    grund: str | None = None
    datum: date | None = None


@dataclass(frozen=True)
class LernWunsch:
    """Regel aus der Korrektur — Muster und Feld wie im Formular (sonst Vorschlag).

    ``bestaetigt``: die Warnungen der Regelvorschau (andere Gegenparteien,
    Zahlungsdienst, Umsatz ohne Namen der Gegenpartei) sind gesehen und bestätigt —
    ohne sie wird so eine Regel nicht gespeichert (``RegelBestaetigenError``)."""

    muster: str | None = None
    feld: Feld | None = None
    bestaetigt: bool = False


@dataclass
class Korrekturergebnis:
    korrektur: Korrektur
    regel: Kontierungsregel | None = None
    gelernt: str | None = None  # „Sachkonto … als Vorschlag für …“


def _konten(a: Aenderung) -> Aenderung:
    try:
        soll = pruefe_kontonummer(a.soll, "Soll")
    except KontoError as fehler:
        raise PruefschlangeError(str(fehler), feld="soll") from fehler
    try:
        haben = pruefe_kontonummer(a.haben, "Haben")
    except KontoError as fehler:
        raise PruefschlangeError(str(fehler), feld="haben") from fehler
    if (gleich := soll_gleich_haben(soll, haben)) is not None:
        raise PruefschlangeError(gleich, feld="haben")
    if a.grund is not None and len(a.grund) > GRUND_MAX:
        raise PruefschlangeError(
            f"Der Grund ist zu lang — höchstens {GRUND_MAX} Zeichen", feld="grund"
        )
    return Aenderung(soll, haben, a.steuer, a.ohne_steuer, a.grund, a.datum)


def eingerichtete_bankkonten(session: Session, buchhaltung: Buchhaltung) -> set[str]:
    """Das Standard-Bankkonto der Konfiguration und die Sachkonten der eingerichteten
    Bankkonten (``accounti bank verbinde``, auch Kartenkonten von Kreditkarten)."""
    return {buchhaltung.bank_konto} | {k.sachkonto for k in lade_bankkonten(session)}


@dataclass(frozen=True)
class Bankkontowechsel:
    """Die Korrektur bucht den Umsatz über ein anderes eingerichtetes Bankkonto."""

    von: str
    nach: str
    warnung: str


def _pruefe_finanzkonto(
    session: Session,
    b: Buchungssatz,
    tx: Transaktion | None,
    a: Aenderung,
    umgebung: Korrekturumgebung,
) -> Bankkontowechsel | None:
    """Eine Buchung zu einem Umsatz behält dessen Finanzkonto (``tx.sachkonto``, sonst
    ``buchhaltung.bank_konto``) auf der Seite seiner Zahlungsrichtung — sonst stimmt
    der Kontostand nicht mehr mit dem Auszug (§ 146 Abs. 1 AO, § 239 Abs. 2 HGB).
    Geprüft nur, wenn die Buchung das Finanzkonto heute berührt (Skonto- und
    Restbuchungen am selben Umsatz tun das nicht) — oder, nach einem Wechsel, ein
    anderes eingerichtetes Bankkonto auf der Seite der Zahlung.

    Ausnahme: der Wechsel auf ein **anderes eingerichtetes Bankkonto** (Umsatz ohne
    oder mit falscher Kontozuordnung, z. B. ``import bank`` ohne ``--konto``) — das
    gibt einen ``Bankkontowechsel`` mit Warnung zurück; daraus wird keine Regel
    gelernt. Aufwand, Kasse oder ein nicht eingerichtetes Konto bleiben abgewiesen."""
    if tx is None or tx.betrag == 0:
        return None
    buchhaltung = umgebung.buchhaltung
    banken = eingerichtete_bankkonten(session, buchhaltung)
    zuordnung = tx.sachkonto or buchhaltung.bank_konto
    ausgabe = tx.betrag < 0
    finanz = zuordnung
    if finanz not in (b.soll_konto, b.haben_konto):
        seite = b.haben_konto if ausgabe else b.soll_konto
        if seite not in banken:
            return None
        finanz = seite  # nach einem Wechsel: das Bankkonto der Buchung
    fehler = finanzkonto_fehler(a.soll, a.haben, tx.betrag, finanz)
    if fehler is None:
        return None
    neu = a.haben if ausgabe else a.soll
    if finanz in banken and neu in banken:
        if neu == zuordnung:
            return None  # zurück auf das Konto, dem der Umsatz zugeordnet ist
        rest = (
            f"die Kontozuordnung des Umsatzes ({tx.sachkonto}) bleibt"
            if tx.sachkonto
            else "der Umsatz selbst hat keine Kontozuordnung"
        )
        return Bankkontowechsel(
            finanz,
            neu,
            f"Bankkonto gewechselt: Der Umsatz läuft jetzt über {neu} statt über "
            f"{finanz} — richtig nur, wenn er auf dem Kontoauszug von {neu} steht "
            f"(der Abschluss stimmt beide Konten mit dem Auszug ab). {rest[0].upper()}"
            f"{rest[1:]}; nach einem Storno bucht classify ihn wieder über "
            f"{zuordnung}.",
        )
    meldung = fehler[1]
    if finanz in banken and umgebung.kontenrahmen.ist_bankkonto(neu):
        meldung += (
            f" — {neu} ist nicht als Bankkonto eingerichtet (accounti bank verbinde "
            f"… --sachkonto {neu}); erst dann lässt sich der Umsatz dorthin umbuchen"
        )
    raise PruefschlangeError(meldung, feld=fehler[0])


def regel_lernbar(h: Herkunft, mit_umsatz: bool, *, unbekannt: bool = False) -> bool:
    """Aus einer Korrektur lernt eine Text-Regel nur, wer einen Kontierungsvorschlag
    eines Umsatzes korrigiert — nicht Kreditkarte, Anlagen, Marktplatz, OPOS.
    ``unbekannt``: auch ohne gespeicherte Herkunft (Altbuchungen vor 10b, CLI)."""
    return mit_umsatz and (
        h.quelle in REGEL_QUELLEN or (unbekannt and h.quelle is None)
    )


def korrigieren(
    session: Session,
    buchung_id: UUID | str,
    aenderung: Aenderung,
    person: str,
    stand: str | None,
    umgebung: Korrekturumgebung,
    *,
    lernen: LernWunsch | None = None,
    nur_vorschlaege: bool = True,
    unbekannte_herkunft_lernbar: bool = False,
) -> Korrekturergebnis:
    """Korrektur über ``storno.korrigiere`` (Vorschlag direkt, freigegeben Storno und
    Neubuchung) — mit der Umgebung der Gesellschaft, auf Wunsch mit Regel.

    Gelernt wird nur aus Kontierungsvorschlägen (``regel_lernbar``) — in der Queue wie
    in der CLI, unabhängig von ``nur_vorschlaege``; ``unbekannte_herkunft_lernbar``
    lässt die CLI auch aus Altbuchungen ohne gespeicherte Herkunft lernen (nicht aus
    Kassenvorgängen). Trifft die Regel andere Gegenparteien oder einen Zahlungsdienst
    oder hat der Umsatz keinen Namen der Gegenpartei, nur mit ``lernen.bestaetigt``
    (sonst ``RegelBestaetigenError`` samt Vorschau). Wechselt die Korrektur auf ein
    anderes eingerichtetes Bankkonto, steht das als Warnung in
    ``korrektur.warnungen``; eine Regel gibt es dann nicht."""
    from accounti.klassifikation.lernen import (
        RegelError,
        UmbuchungError,
        entwurf_aus_korrektur,
        lerne,
        lerne_sachkonto,
        pruefe_entwurf,
    )

    b = _sperren_und_pruefen(session, str(buchung_id), stand, nur_vorschlaege)
    a = _konten(aenderung)
    tx = lade_transaktion(session, b.transaktion_id) if b.transaktion_id else None
    wechsel = _pruefe_finanzkonto(session, b, tx, a, umgebung)
    if lernen is not None and wechsel is not None:
        raise PruefschlangeError(
            f"Die Korrektur wechselt das Bankkonto ({wechsel.von} → {wechsel.nach}) — "
            "daraus wird keine Regel gelernt (sie buchte künftige Umsätze am Konto "
            "vorbei); ohne Regel korrigieren",
            feld="regel",
        )
    if lernen is not None:
        h = herkunft(session, b)
        # Kassenvorgänge (quelle manuell, Kassenbuch) speichern keine Herkunft — aus
        # ihnen entstünde eine Bankregel; sie zählen nicht als Altbuchung
        kasse = tx is not None and tx.quelle is TransaktionQuelle.MANUELL
        regel_ok = regel_lernbar(
            h,
            b.transaktion_id is not None,
            unbekannt=unbekannte_herkunft_lernbar and not kasse,
        )
        sachkonto_ok = b.transaktion_id is None and b.beleg_id is not None
        if not (regel_ok or sachkonto_ok):
            raise PruefschlangeError(
                "Für diese Buchung wird keine Regel angeboten (Herkunft "
                f"{h.quelle or 'unbekannt'}) — Regeln entstehen nur aus "
                "Kontierungsvorschlägen eines Umsatzes",
                feld="regel",
            )
    k = korrigiere(
        session,
        str(b.id),
        a.soll,
        a.haben,
        steuer=a.steuer,
        ohne_steuer=a.ohne_steuer,
        von=person,
        grund=a.grund,
        datum=a.datum,
        kontenrahmen=umgebung.kontenrahmen,
        buchhaltung=umgebung.buchhaltung,
        einstellungen=umgebung.pruefung,
        elster=umgebung.elster,
    )
    if wechsel is not None:
        k.warnungen.append(wechsel.warnung)
    ergebnis = Korrekturergebnis(k)
    if lernen is not None:
        if k.original.transaktion_id is not None:
            if tx is not None:
                try:
                    # Umbuchung zwischen eigenen Geldkonten: keine Regel — auch
                    # eingerichtete Bank- und Kartenkonten zählen (H-1)
                    entwurf = entwurf_aus_korrektur(
                        k,
                        tx,
                        umgebung.buchhaltung,
                        muster=lernen.muster,
                        feld=lernen.feld,
                        kontenrahmen=umgebung.kontenrahmen.mit_geldkonten(
                            eingerichtete_bankkonten(session, umgebung.buchhaltung)
                        ),
                    )
                    if not lernen.bestaetigt:
                        v = pruefe_entwurf(session, entwurf, tx, None)
                        if v.bestaetigung_noetig:
                            raise RegelBestaetigenError(
                                "Regel nicht gespeichert: "
                                + "; ".join(v.bestaetigungsgruende)
                                + " — das Muster genauer fassen oder die Warnung in "
                                "der Regelvorschau bestätigen",
                                vorschau=v,
                            )
                    ergebnis.regel = lerne(session, entwurf, person)
                except UmbuchungError as fehler:
                    # Umbuchung zwischen Konten mit Kontoauszug: die Korrektur gilt,
                    # nur ohne Regel (gw2-merge B2: sonst ging auch sie verloren)
                    k.warnungen.append(f"Keine Regel gelernt: {fehler.args[0]}")
                except RegelError as fehler:
                    raise PruefschlangeError(
                        fehler.args[0], feld=fehler.feld or "muster"
                    ) from fehler
        else:
            try:
                ergebnis.gelernt = lerne_sachkonto(
                    session, k.original, a.soll, a.haben, person, umgebung.buchhaltung
                )
            except RegelError as fehler:
                k.warnungen.append(fehler.args[0])
    if k.storno is None:
        _schliesse_aufgaben(
            session, k.original, f"Buchung korrigiert von {person}", person
        )
    session.flush()
    return ergebnis


def stornieren(
    session: Session,
    buchung_id: UUID | str,
    grund: str,
    person: str,
    stand: str | None,
    umgebung: Korrekturumgebung,
    datum: date | None = None,
) -> Korrektur:
    """Storno einer freigegebenen Buchung (``/buchungen/{id}``, CLI ``buchung
    storniere``)."""
    if len(grund or "") > GRUND_MAX:
        raise PruefschlangeError(
            f"Der Grund ist zu lang — höchstens {GRUND_MAX} Zeichen", feld="grund"
        )
    b = _sperren_und_pruefen(session, str(buchung_id), stand, False)
    k = storniere(
        session,
        str(b.id),
        grund=grund,
        von=person,
        datum=datum,
        kontenrahmen=umgebung.kontenrahmen,
        buchhaltung=umgebung.buchhaltung,
        elster=umgebung.elster,
    )
    session.flush()
    return k


def zurueckstellen(
    session: Session,
    buchung_id: UUID | str,
    text: str,
    person: str,
    *,
    an: str | None = None,
    einstellungen: AufgabenEinstellungen | None = None,
) -> Rueckfrage:
    """Rückfrage als Aufgabe (Baustein 8); die Buchung bleibt ``zur Prüfung`` und
    erscheint in der Ansicht „zurückgestellt“. Nur einmal (sonst 409)."""
    if not (text or "").strip():
        raise PruefschlangeError("Die Rückfrage braucht einen Text", feld="text")
    if an is not None and len(an) > AN_MAX:
        raise PruefschlangeError(
            f"„an“ ist zu lang — höchstens {AN_MAX} Zeichen (Benutzername)", feld="an"
        )
    b = _sperren_und_pruefen(session, str(buchung_id), None, True)
    if str(b.id) in _zurueckgestellte(session):
        raise SchonZurueckgestelltError(
            f"Buchung {str(b.id)[:8]} ist schon zurückgestellt — die offene Rückfrage "
            "beantworten oder schließen"
        )
    r = halte_rueckfrage_fest(
        session,
        Objekt("buchung", b.id),
        text.strip(),
        person,
        an=an or None,
        als_aufgabe=True,
        einstellungen=einstellungen,
    )
    session.flush()
    return r


def anzahl_zur_pruefung(buchungen: Sequence[Buchungssatz]) -> int:
    return sum(1 for b in buchungen if b.status is BuchungStatus.ZUR_PRUEFUNG)
