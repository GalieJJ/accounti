"""Aufgaben erzeugen, abschließen, zuweisen, kommentieren — die schmale Schnittstelle.

Andere Bausteine melden Aufgaben mit ``melde_aufgabe`` und schließen sie mit
``schliesse_wenn_erledigt``, sobald der Anlass entfallen ist. Der Idempotenzschlüssel
aus Art und Objekt verhindert, dass ein wiederholter Prüflauf dieselbe Aufgabe neu
anlegt: Ein zweiter Aufruf aktualisiert die vorhandene. Was das System geschlossen hat
(``hinfaellig``), öffnet es wieder, wenn der Anlass zurückkehrt; was ein Mensch
erledigt hat, bleibt erledigt.

Alle Funktionen arbeiten in der Sitzung des Aufrufers und committen nicht.
"""

from __future__ import annotations

import enum
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from accounti.aufgaben.einstellungen import AufgabenEinstellungen
from accounti.aufgaben.fehler import AufgabenError
from accounti.aufgaben.zustaendigkeit import bestimme_zustaendigkeit
from accounti.db.repo_aufgaben import (
    aktualisiere_aufgabe,
    lade_aufgabe,
    lade_aufgabe_nach_schluessel,
    lade_aufgaben,
    lade_kommentare,
    naechste_aufgaben_nr,
    speichere_aufgabe,
    speichere_kommentar,
)
from accounti.models.aufgaben import (
    AKTIVE_STATUS,
    Aufgabe,
    AufgabenStatus,
    Kommentar,
    KommentarArt,
    Objekt,
    Prioritaet,
    idempotenzschluessel,
)

SYSTEM = "system"


class Vorgang(str, enum.Enum):
    NEU = "neu"
    AKTUALISIERT = "aktualisiert"
    UNVERAENDERT = "unveraendert"
    WIEDER_OFFEN = "wieder_offen"  # war hinfällig (oder ausdrücklich wieder geöffnet)
    ABGESCHLOSSEN = "abgeschlossen"  # von einem Menschen erledigt — bleibt es


@dataclass
class Meldung:
    aufgabe: Aufgabe
    vorgang: Vorgang


def _jetzt(jetzt: datetime | None) -> datetime:
    return jetzt or datetime.now()


def _ereignis(
    session: Session, aufgabe: Aufgabe, text: str, von: str, jetzt: datetime
) -> None:
    speichere_kommentar(
        session,
        Kommentar(
            aufgabe_id=aufgabe.id,
            objekt_typ=aufgabe.objekt_typ,
            objekt_id=aufgabe.objekt_id,
            art=KommentarArt.EREIGNIS,
            autor=von,
            text=text,
            erstellt_am=jetzt,
        ),
    )


def _lade(session: Session, ref: str | int | Aufgabe) -> Aufgabe:
    if isinstance(ref, Aufgabe):
        ref = str(ref.id)
    try:
        return lade_aufgabe(session, ref)
    except ValueError as fehler:
        raise AufgabenError(str(fehler)) from fehler


def _anlegen(session: Session, aufgabe: Aufgabe) -> Aufgabe | None:
    """Legt an; None, wenn ein paralleler Lauf denselben Schlüssel schneller war."""
    for _ in range(3):
        try:
            with session.begin_nested():
                neu = aufgabe.model_copy(update={"nr": naechste_aufgaben_nr(session)})
                speichere_aufgabe(session, neu)
            return neu
        except IntegrityError:
            if lade_aufgabe_nach_schluessel(session, aufgabe.schluessel) is not None:
                return None
            # sonst war es die laufende Nummer — neue ziehen
    msg = "Keine freie Aufgabennummer (zu viele gleichzeitige Läufe)"
    raise AufgabenError(msg)


def melde_aufgabe(
    session: Session,
    art: str,
    objekt: Objekt,
    titel: str,
    *,
    beschreibung: str = "",
    faellig_am: date | None = None,
    prioritaet: Prioritaet = Prioritaet.NORMAL,
    merkmale: Mapping[str, str] | None = None,
    erzeugt_von: str = SYSTEM,
    zustaendig: str | None = None,
    rolle: str | None = None,
    einstellungen: AufgabenEinstellungen | None = None,
    wieder_oeffnen: bool = False,
    jetzt: datetime | None = None,
) -> Meldung:
    """Legt die Aufgabe zu (Art, Objekt) an oder aktualisiert die vorhandene.

    Beim Anlegen gilt: ohne ``faellig_am`` die Frist der Art aus den Einstellungen,
    ohne ``zustaendig``/``rolle`` die erste passende Zuständigkeitsregel. Ein zweiter
    Aufruf ändert Titel, Beschreibung, Fälligkeit und Merkmale, hebt die Priorität
    (senkt sie nie) und lässt Zuständigkeit und Status in Ruhe. Eine ``hinfaellig``
    geschlossene Aufgabe wird wieder ``offen``; eine ``erledigt`` geschlossene nur mit
    ``wieder_oeffnen=True``.
    """
    einstellungen = einstellungen or AufgabenEinstellungen()
    jetzt = _jetzt(jetzt)
    merkmale = dict(merkmale or {})
    entwurf = Aufgabe(
        art=art,
        titel=titel,
        beschreibung=beschreibung,
        objekt_typ=objekt.typ,
        objekt_id=objekt.id,
        faellig_am=faellig_am
        or jetzt.date() + timedelta(days=einstellungen.frist_tage(art)),
        prioritaet=prioritaet,
        erzeugt_von=erzeugt_von,
        merkmale=merkmale,
        erstellt_am=jetzt,
        aktualisiert_am=jetzt,
    )
    vorhanden = lade_aufgabe_nach_schluessel(session, entwurf.schluessel)
    if vorhanden is None:
        if zustaendig is None and rolle is None:
            zustaendig, rolle = bestimme_zustaendigkeit(
                einstellungen.zustaendigkeit, art, objekt, merkmale
            )
        entwurf = entwurf.model_copy(update={"zustaendig": zustaendig, "rolle": rolle})
        neu = _anlegen(session, entwurf)
        if neu is not None:
            _ereignis(
                session,
                neu,
                f"angelegt von {erzeugt_von}; zuständig: {neu.zustaendigkeit}",
                erzeugt_von,
                jetzt,
            )
            return Meldung(neu, Vorgang.NEU)
        vorhanden = lade_aufgabe_nach_schluessel(session, entwurf.schluessel)
        if vorhanden is None:  # pragma: no cover — _anlegen hat sie gesehen
            msg = f"Aufgabe {entwurf.schluessel} verschwunden"
            raise AufgabenError(msg)

    if vorhanden.status is AufgabenStatus.ERLEDIGT and not wieder_oeffnen:
        return Meldung(vorhanden, Vorgang.ABGESCHLOSSEN)

    aenderung: dict[str, object] = {
        "titel": entwurf.titel,
        "beschreibung": entwurf.beschreibung,
        "merkmale": entwurf.merkmale,
    }
    if faellig_am is not None:
        aenderung["faellig_am"] = faellig_am
    if prioritaet.rang > vorhanden.prioritaet.rang:
        aenderung["prioritaet"] = prioritaet
    vorgang = Vorgang.UNVERAENDERT
    if any(getattr(vorhanden, k) != v for k, v in aenderung.items()):
        vorgang = Vorgang.AKTUALISIERT

    if not vorhanden.aktiv:
        vorgang = Vorgang.WIEDER_OFFEN
        aenderung.update(
            status=AufgabenStatus.OFFEN,
            abschluss_grund=None,
            erledigt_am=None,
            quittiert_von=None,
            erinnerungsstufe=0,
            gemeldet_am=None,
        )
        if faellig_am is None:
            aenderung["faellig_am"] = entwurf.faellig_am
    if vorgang is Vorgang.UNVERAENDERT:
        return Meldung(vorhanden, vorgang)

    aenderung["aktualisiert_am"] = jetzt
    aufgabe = aktualisiere_aufgabe(session, vorhanden.model_copy(update=aenderung))
    if vorgang is Vorgang.WIEDER_OFFEN:
        _ereignis(
            session,
            aufgabe,
            f"wieder offen: Anlass besteht wieder (war {vorhanden.status.value})",
            erzeugt_von,
            jetzt,
        )
    return Meldung(aufgabe, vorgang)


def schliesse_wenn_erledigt(
    session: Session,
    art: str,
    objekt: Objekt,
    grund: str,
    *,
    von: str = SYSTEM,
    jetzt: datetime | None = None,
) -> Aufgabe | None:
    """Der Anlass ist entfallen: aktive Aufgabe → ``hinfaellig`` (sonst None)."""
    vorhanden = lade_aufgabe_nach_schluessel(session, idempotenzschluessel(art, objekt))
    if vorhanden is None or not vorhanden.aktiv:
        return None
    return _schliesse(session, vorhanden, grund, von, _jetzt(jetzt))


def _schliesse(
    session: Session, aufgabe: Aufgabe, grund: str, von: str, jetzt: datetime
) -> Aufgabe:
    geschlossen = aktualisiere_aufgabe(
        session,
        aufgabe.model_copy(
            update={
                "status": AufgabenStatus.HINFAELLIG,
                "abschluss_grund": grund[:500],
                "erledigt_am": jetzt,
                "aktualisiert_am": jetzt,
            }
        ),
    )
    _ereignis(session, geschlossen, f"hinfällig: {grund}", von, jetzt)
    return geschlossen


def erledige(
    session: Session,
    ref: str | int | Aufgabe,
    von: str,
    *,
    text: str | None = None,
    jetzt: datetime | None = None,
) -> Aufgabe:
    """Ein Mensch schließt die Aufgabe ab — optional mit Begründung."""
    jetzt = _jetzt(jetzt)
    aufgabe = _lade(session, ref)
    if not aufgabe.aktiv:
        msg = f"Aufgabe #{aufgabe.nr} ist schon {aufgabe.status.value}."
        raise AufgabenError(msg)
    if text and text.strip():
        kommentiere(session, text, von, aufgabe=aufgabe, jetzt=jetzt)
    erledigt = aktualisiere_aufgabe(
        session,
        aufgabe.model_copy(
            update={
                "status": AufgabenStatus.ERLEDIGT,
                "quittiert_von": von,
                "erledigt_am": jetzt,
                "aktualisiert_am": jetzt,
            }
        ),
    )
    _ereignis(session, erledigt, f"erledigt von {von}", von, jetzt)
    return erledigt


_MENSCHLICHE_STATUS = (
    AufgabenStatus.OFFEN,
    AufgabenStatus.IN_ARBEIT,
    AufgabenStatus.WARTET,
)


def setze_status(
    session: Session,
    ref: str | int | Aufgabe,
    status: AufgabenStatus,
    von: str,
    *,
    jetzt: datetime | None = None,
) -> Aufgabe:
    """offen ↔ in_arbeit ↔ wartet. Erledigen über ``erledige``; hinfällig nur das
    System."""
    if status not in _MENSCHLICHE_STATUS:
        msg = (
            "Erledigen mit 'erledige'; hinfällig setzt nur das System, wenn der "
            "Anlass entfällt."
        )
        raise AufgabenError(msg)
    jetzt = _jetzt(jetzt)
    aufgabe = _lade(session, ref)
    if not aufgabe.aktiv:
        msg = f"Aufgabe #{aufgabe.nr} ist schon {aufgabe.status.value}."
        raise AufgabenError(msg)
    if aufgabe.status is status:
        return aufgabe
    neu = aktualisiere_aufgabe(
        session, aufgabe.model_copy(update={"status": status, "aktualisiert_am": jetzt})
    )
    _ereignis(
        session,
        neu,
        f"Status: {aufgabe.status.value} → {status.value} (von {von})",
        von,
        jetzt,
    )
    return neu


def weise_zu(
    session: Session,
    ref: str | int | Aufgabe,
    *,
    an: str | None = None,
    rolle: str | None = None,
    von: str,
    jetzt: datetime | None = None,
) -> Aufgabe:
    """An einen Benutzer, an eine Rolle oder (beides leer) zurück in die gemeinsame
    Liste."""
    if an is not None and rolle is not None:
        msg = "Entweder Benutzer oder Rolle zuweisen, nicht beides."
        raise AufgabenError(msg)
    jetzt = _jetzt(jetzt)
    aufgabe = _lade(session, ref)
    if not aufgabe.aktiv:
        msg = f"Aufgabe #{aufgabe.nr} ist schon {aufgabe.status.value}."
        raise AufgabenError(msg)
    neu = aktualisiere_aufgabe(
        session,
        aufgabe.model_copy(
            update={"zustaendig": an, "rolle": rolle, "aktualisiert_am": jetzt}
        ),
    )
    if an is not None:
        text = f"zugewiesen an {an}"
    elif rolle is not None:
        text = f"zugewiesen an Rolle {rolle}"
    else:
        text = "zurück in die gemeinsame Liste"
    _ereignis(session, neu, f"{text} (von {von})", von, jetzt)
    return neu


# ---------------------------------------------------------------------------
# Kommentare und Rückfragen
# ---------------------------------------------------------------------------


def kommentiere(
    session: Session,
    text: str,
    autor: str,
    *,
    aufgabe: str | int | Aufgabe | None = None,
    objekt: Objekt | None = None,
    art: KommentarArt = KommentarArt.KOMMENTAR,
    anhang_beleg_id: UUID | None = None,
    jetzt: datetime | None = None,
) -> Kommentar:
    """Kommentar an einer Aufgabe (trägt deren Objekt mit) oder direkt am Objekt."""
    if not text.strip():
        msg = "Der Kommentar ist leer."
        raise AufgabenError(msg)
    aufgabe_id: UUID | None = None
    if aufgabe is not None:
        gefunden = _lade(session, aufgabe)
        if objekt is not None and objekt != gefunden.objekt:
            msg = (
                f"Aufgabe #{gefunden.nr} hängt an {gefunden.objekt}, nicht an "
                f"{objekt} — anderes Objekt."
            )
            raise AufgabenError(msg)
        aufgabe_id, objekt = gefunden.id, gefunden.objekt
    if objekt is None:
        msg = "Kommentar ohne Ziel: Aufgabe oder Objekt angeben."
        raise AufgabenError(msg)
    kommentar = Kommentar(
        aufgabe_id=aufgabe_id,
        objekt_typ=objekt.typ,
        objekt_id=objekt.id,
        art=art,
        autor=autor,
        text=text.strip(),
        erstellt_am=_jetzt(jetzt),
        anhang_beleg_id=anhang_beleg_id,
    )
    speichere_kommentar(session, kommentar)
    return kommentar


@dataclass
class Rueckfrage:
    kommentar: Kommentar
    aufgabe: Aufgabe | None = None


RUECKFRAGE = "rueckfrage"


def halte_rueckfrage_fest(
    session: Session,
    objekt: Objekt,
    text: str,
    autor: str,
    *,
    an: str | None = None,
    rolle: str | None = None,
    als_aufgabe: bool = False,
    faellig_am: date | None = None,
    einstellungen: AufgabenEinstellungen | None = None,
    jetzt: datetime | None = None,
) -> Rueckfrage:
    """Rückfrage am Objekt (z.B. am Beleg).

    Mit ``an``/``rolle``/``als_aufgabe`` zusätzlich als Aufgabe ``rueckfrage``; eine
    neue Rückfrage öffnet eine erledigte wieder.
    """
    jetzt = _jetzt(jetzt)
    aufgabe: Aufgabe | None = None
    if an is not None or rolle is not None or als_aufgabe:
        meldung = melde_aufgabe(
            session,
            RUECKFRAGE,
            objekt,
            titel=f"Rückfrage: {' '.join(text.split())}"[:200],
            beschreibung=text.strip(),
            faellig_am=faellig_am,
            erzeugt_von=autor,
            zustaendig=an,
            rolle=rolle,
            einstellungen=einstellungen,
            wieder_oeffnen=True,
            jetzt=jetzt,
        )
        aufgabe = meldung.aufgabe
        umgezogen = (aufgabe.zustaendig, aufgabe.rolle) != (an, rolle)
        if meldung.vorgang is not Vorgang.NEU and (an or rolle) and umgezogen:
            aufgabe = weise_zu(
                session, aufgabe, an=an, rolle=rolle, von=autor, jetzt=jetzt
            )
    kommentar = kommentiere(
        session,
        text,
        autor,
        aufgabe=aufgabe,
        objekt=None if aufgabe else objekt,
        art=KommentarArt.RUECKFRAGE,
        jetzt=jetzt,
    )
    return Rueckfrage(kommentar, aufgabe)


def kommentare_zu(
    session: Session, objekt: Objekt, *, mit_ereignissen: bool = False
) -> list[Kommentar]:
    """Alles, was am Objekt steht — direkt oder an einer seiner Aufgaben."""
    arten = (
        None if mit_ereignissen else {KommentarArt.KOMMENTAR, KommentarArt.RUECKFRAGE}
    )
    return lade_kommentare(session, objekt=objekt, arten=arten)


def aufgaben_zu(session: Session, objekt: Objekt) -> list[Aufgabe]:
    return lade_aufgaben(session, objekt=objekt)


# ---------------------------------------------------------------------------
# Abgleich einer ganzen Art (für Prüfläufe)
# ---------------------------------------------------------------------------


@dataclass
class Anlass:
    """Ein Grund für eine Aufgabe, wie ihn ein Prüflauf findet."""

    objekt: Objekt
    titel: str
    beschreibung: str = ""
    faellig_am: date | None = None
    prioritaet: Prioritaet = Prioritaet.NORMAL
    merkmale: dict[str, str] = field(default_factory=dict)


@dataclass
class Abgleich:
    neu: list[Aufgabe] = field(default_factory=list)
    aktualisiert: list[Aufgabe] = field(default_factory=list)
    unveraendert: list[Aufgabe] = field(default_factory=list)
    wieder_offen: list[Aufgabe] = field(default_factory=list)
    abgeschlossen: list[Aufgabe] = field(default_factory=list)  # erledigt, bleibt es
    hinfaellig: list[Aufgabe] = field(default_factory=list)


def gleiche_ab(
    session: Session,
    art: str,
    anlaesse: Sequence[Anlass],
    *,
    erzeugt_von: str,
    grund_entfallen: str,
    umfang: Collection[Objekt] | None = None,
    gruende: Mapping[Objekt, str] | None = None,
    einstellungen: AufgabenEinstellungen | None = None,
    jetzt: datetime | None = None,
) -> Abgleich:
    """Meldet alle Anlässe einer Art und schließt, was keinen Anlass mehr hat.

    Geschlossen werden nur aktive Aufgaben dieses Erzeugers, deren Objekt im
    geprüften ``umfang`` liegt (``None`` = alles geprüft) — ein Lauf über einen Monat
    schließt nichts aus anderen Monaten. ``gruende`` nennt je Objekt, warum der Anlass
    entfallen ist (z.B. welcher Beleg zugeordnet wurde); sonst ``grund_entfallen``.
    """
    gruende = gruende or {}
    jetzt = _jetzt(jetzt)
    ergebnis = Abgleich()
    gesehen: set[str] = set()
    for anlass in anlaesse:
        m = melde_aufgabe(
            session,
            art,
            anlass.objekt,
            anlass.titel,
            beschreibung=anlass.beschreibung,
            faellig_am=anlass.faellig_am,
            prioritaet=anlass.prioritaet,
            merkmale=anlass.merkmale,
            erzeugt_von=erzeugt_von,
            einstellungen=einstellungen,
            jetzt=jetzt,
        )
        gesehen.add(m.aufgabe.schluessel)
        {
            Vorgang.NEU: ergebnis.neu,
            Vorgang.AKTUALISIERT: ergebnis.aktualisiert,
            Vorgang.UNVERAENDERT: ergebnis.unveraendert,
            Vorgang.WIEDER_OFFEN: ergebnis.wieder_offen,
            Vorgang.ABGESCHLOSSEN: ergebnis.abgeschlossen,
        }[m.vorgang].append(m.aufgabe)
    im_umfang = set(umfang) if umfang is not None else None
    for aufgabe in lade_aufgaben(
        session, status=AKTIVE_STATUS, art=art, erzeugt_von=erzeugt_von
    ):
        if aufgabe.schluessel in gesehen:
            continue
        if im_umfang is not None and aufgabe.objekt not in im_umfang:
            continue
        grund = gruende.get(aufgabe.objekt, grund_entfallen)
        ergebnis.hinfaellig.append(_schliesse(session, aufgabe, grund, SYSTEM, jetzt))
    return ergebnis
