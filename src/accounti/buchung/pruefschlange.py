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

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounti.aufgaben import (
    AufgabenEinstellungen,
    halte_rueckfrage_fest,
    kommentare_zu,
    schliesse_wenn_erledigt,
)
from accounti.aufgaben.erzeugung import RUECKFRAGE, Rueckfrage
from accounti.belege.zuordnung import beleg_zur_buchung
from accounti.buchung.konten import KontoError, pruefe_kontonummer
from accounti.db.repo_aufgaben import lade_aufgaben
from accounti.db.repo_kontierung import lade_kontierungsgruende, lade_kontierungsgrund
from accounti.db.repository import (
    finde_buchung,
    lade_buchungen,
    lade_kontakte,
    lade_transaktion,
)
from accounti.db.tabellen import BuchungssatzRow
from accounti.models import (
    Beleg,
    Buchungssatz,
    BuchungStatus,
    Kontakt,
    Transaktion,
)
from accounti.models.aufgaben import AKTIVE_STATUS, Aufgabe, Kommentar, Objekt
from accounti.pruefung.journal import kanonisch, schnappschuss, schreibsperre
from accounti.pruefung.storno import (
    VORSCHLAG,
    Korrektur,
    Korrekturumgebung,
    SteuerOptionen,
    korrigiere,
    steuer_optionen,
    storniere,
)
from accounti.pruefung.storno import freigeben as storno_freigeben

if TYPE_CHECKING:
    from accounti.models.kontierung import Feld, Kontierungsregel
    from accounti.pruefung.einstellungen import BelegfreiRegel, PruefEinstellungen
    from accounti.pruefung.perioden import Sperre

JE_SEITE = 200
KONTIERUNG_PRUEFEN = "kontierung_pruefen"
BELEG_FEHLT = "beleg_fehlt"
# Quellen, aus denen eine Korrektur eine Regel lernen darf — nicht Kreditkarte,
# Anlagen, Marktplatz, OPOS (eine Regel aus „VISA“ oder einer AfA wäre Unsinn)
REGEL_QUELLEN = frozenset({"regelwerk", "llm", "standard"})


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

    @property
    def ist_vorschlag(self) -> bool:
        return self.buchung.status in VORSCHLAG


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
    return konto.isdigit() and len(konto) == 5


def lade_eintrag(
    session: Session,
    buchung_id: UUID | str,
    *,
    pruefung: PruefEinstellungen | None = None,
) -> Arbeitsflaeche:
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
        for x in lade_buchungen(session)
        if x.id != b.id
        and (
            (b.transaktion_id is not None and x.transaktion_id == b.transaktion_id)
            or (b.beleg_id is not None and x.beleg_id == b.beleg_id)
        )
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
        steuer=steuer_optionen(b),
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
    flaeche.regel_moeglich = tx is not None and h.quelle in REGEL_QUELLEN
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
) -> tuple[Buchungssatz, bool]:
    """Vorschlag → ``geprueft`` (CLI ``bestaetige``: auch ``auto``, ohne Stand)."""
    b = _sperren_und_pruefen(session, str(buchung_id), stand, nur_vorschlaege)
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
    """Regel aus der Korrektur — Muster und Feld wie im Formular (sonst Vorschlag)."""

    muster: str | None = None
    feld: Feld | None = None


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
    return Aenderung(soll, haben, a.steuer, a.ohne_steuer, a.grund, a.datum)


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
) -> Korrekturergebnis:
    """Korrektur über ``storno.korrigiere`` (Vorschlag direkt, freigegeben Storno und
    Neubuchung) — mit der Umgebung der Gesellschaft, auf Wunsch mit Regel."""
    from accounti.klassifikation.lernen import (
        RegelError,
        entwurf_aus_korrektur,
        lerne,
        lerne_sachkonto,
    )

    b = _sperren_und_pruefen(session, str(buchung_id), stand, nur_vorschlaege)
    a = _konten(aenderung)
    if lernen is not None and nur_vorschlaege:
        h = herkunft(session, b)
        regel_ok = b.transaktion_id is not None and h.quelle in REGEL_QUELLEN
        sachkonto_ok = b.transaktion_id is None and b.beleg_id is not None
        if not (regel_ok or sachkonto_ok):
            raise PruefschlangeError(
                "Für diese Buchung wird keine Regel angeboten (Herkunft "
                f"{h.quelle or 'unbekannt'})",
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
    )
    ergebnis = Korrekturergebnis(k)
    if lernen is not None:
        if k.original.transaktion_id is not None:
            tx = lade_transaktion(session, k.original.transaktion_id)
            if tx is not None:
                entwurf = entwurf_aus_korrektur(
                    k, tx, umgebung.buchhaltung, muster=lernen.muster, feld=lernen.feld
                )
                try:
                    ergebnis.regel = lerne(session, entwurf, person)
                except RegelError as fehler:
                    raise PruefschlangeError(
                        fehler.args[0], feld=fehler.feld or "muster"
                    ) from fehler
        else:
            ergebnis.gelernt = lerne_sachkonto(
                session, k.original, a.soll, a.haben, person
            )
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
    b = _sperren_und_pruefen(session, str(buchung_id), stand, False)
    k = storniere(
        session,
        str(b.id),
        grund=grund,
        von=person,
        datum=datum,
        kontenrahmen=umgebung.kontenrahmen,
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
