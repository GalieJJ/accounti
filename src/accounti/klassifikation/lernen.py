"""Lernschleife: aus einer Korrektur wird eine Regel (Datenbank der Gesellschaft).

Für CLI (``accounti korrigiere --lernen``, ``lerne``, ``regeln …``) und Browser
(Supervisions-Queue) dieselben Funktionen (Spec 3: keine UI-eigene Logik):

* ``entwurf_fuer`` / ``entwurf_aus_korrektur`` — Muster (erstes Wort der Gegenpartei,
  sonst des Verwendungszwecks; unter 3 Zeichen die ersten zwei Wörter), Feld,
  **Richtung** aus dem Vorzeichen des Umsatzes, Konten und Schlüssel der Neubuchung.
* ``pruefe_entwurf`` — Vorschau: was träfe die Regel in den letzten 24 Monaten?
* ``lerne`` (Text, aus dem Browser), ``lerne_regex`` (Betreiber, CLI),
  ``lerne_sachkonto`` (Belegbuchung → Sachkonto am Kontakt), ``deaktiviere``,
  ``uebernehme_aus_datei`` (alte ``gelernt_*``-Einträge der Regeldatei).
* ``lade_regelwerk`` — gelernte Regeln (neueste zuerst) → Regeldatei der Gesellschaft
  → Standardregeln. Die gelernte Regel greift also auch dann, wenn eine eigene Regel
  vorher falsch getroffen hat (Akzeptanz 2).

Alle Funktionen arbeiten in der Sitzung des Aufrufers und committen nicht. Anlage und
Deaktivierung stehen im Journal (``pruefung.ereignisse``).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import UUID

import yaml
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from accounti.buchung.konten import KontoError, kontobezeichnung, pruefe_kontonummer
from accounti.db.repo_kontierung import (
    deaktiviere_regel,
    lade_kontierungsregeln,
    regelnamen,
    speichere_regel,
    zaehle_regeltreffer,
)
from accounti.klassifikation.engine import (
    STANDARD_REGELN,
    Regel,
    RegelwerkEngine,
    text_muster,
)
from accounti.konfiguration import Buchhaltung
from accounti.models import Buchungssatz, Transaktion
from accounti.models.kontierung import (
    Feld,
    Kontierungsregel,
    RegelHerkunft,
    Richtung,
)

if TYPE_CHECKING:
    from accounti.abschluss.kontenrahmen import Kontenrahmen
    from accounti.pruefung.storno import Korrektur

LOG = logging.getLogger(__name__)

Einstellung = Literal["automatisch", "pruefen", "aus"]
PRUEFEN_CONFIDENCE = 0.9  # unter der Schwelle von buchung.mapper (0,95)
VORSCHAU_TAGE = 730  # 24 Monate
TEXT_MIN, TEXT_MAX = 3, 100
REGEX_MAX = 200
BREIT_ANTEIL = 0.2  # mehr als 20 % aller Umsätze: zu breit
BREIT_AB = 10  # … erst ab so vielen Umsätzen aussagekräftig
BEISPIELE = 5
FELDER: tuple[Feld, ...] = ("gegenkonto_name", "verwendungszweck", "beide")


class RegelError(ValueError):
    """Die Regel lässt sich so nicht lernen, ändern oder übernehmen.

    ``feld`` nennt das Formularfeld (``muster``, ``konto``, ``grund`` …) für die
    Oberfläche."""

    def __init__(self, meldung: str, feld: str | None = None) -> None:
        super().__init__(meldung)
        self.feld = feld


# --- Entwurf --------------------------------------------------------------------------


@dataclass(frozen=True)
class RegelEntwurf:
    muster: str  # Text, kein regulärer Ausdruck
    feld: Feld
    richtung: Richtung | None
    soll_konto: str
    haben_konto: str
    steuer_schluessel: int | None
    quelle_buchung_id: UUID | None = None
    buchungstext: str | None = None


def _woerter(text: str | None) -> list[str]:
    return [w.strip(".,;:!?/()[]\"'") for w in (text or "").split()]


def vorschlag_muster(umsatz: Transaktion) -> str:
    """Erstes Wort der Gegenpartei, sonst des Verwendungszwecks; ist es kürzer als 3
    Zeichen, die ersten zwei Wörter."""
    woerter = [w for w in _woerter(umsatz.gegenkonto_name) if w] or [
        w for w in _woerter(umsatz.verwendungszweck) if w
    ]
    if not woerter:
        return ""
    if len(woerter[0]) < TEXT_MIN and len(woerter) > 1:
        return f"{woerter[0]} {woerter[1]}"
    return woerter[0]


def richtung_von(umsatz: Transaktion) -> Richtung:
    return Richtung.AUSGABE if umsatz.betrag < 0 else Richtung.EINNAHME


def entwurf_fuer(
    umsatz: Transaktion,
    soll: str,
    haben: str,
    steuer_schluessel: int | None,
    buchhaltung: Buchhaltung,
    *,
    muster: str | None = None,
    feld: Feld | None = None,
    quelle_buchung_id: UUID | None = None,
) -> RegelEntwurf:
    """Entwurf aus Umsatz und (künftiger) Kontierung. Steht dort das Finanzkonto des
    Umsatzes (zweites Giro, Kreditkarte), speichert die Regel das Standard-Bankkonto —
    ``kontiere_umsaetze`` setzt beim Anwenden das Finanzkonto wieder ein."""
    finanz = umsatz.sachkonto
    if finanz and finanz != buchhaltung.bank_konto:
        soll = buchhaltung.bank_konto if soll == finanz else soll
        haben = buchhaltung.bank_konto if haben == finanz else haben
    return RegelEntwurf(
        muster=(muster if muster is not None else vorschlag_muster(umsatz)).strip(),
        feld=feld or "beide",
        richtung=richtung_von(umsatz),
        soll_konto=soll.strip(),
        haben_konto=haben.strip(),
        steuer_schluessel=steuer_schluessel,
        quelle_buchung_id=quelle_buchung_id,
    )


def entwurf_aus_korrektur(
    korrektur: Korrektur,
    umsatz: Transaktion,
    buchhaltung: Buchhaltung,
    *,
    muster: str | None = None,
    feld: Feld | None = None,
) -> RegelEntwurf:
    """Konten und Schlüssel **der Neubuchung** (bei neuem Sachkonto ausdrücklich
    angegeben, sonst der des unveränderten Sachkontos — wie Baustein 7)."""
    neu: Buchungssatz = korrektur.neu or korrektur.original
    return entwurf_fuer(
        umsatz,
        neu.soll_konto,
        neu.haben_konto,
        neu.steuer_schluessel,
        buchhaltung,
        muster=muster,
        feld=feld,
        quelle_buchung_id=korrektur.original.id,
    )


def pruefe_text(muster: str) -> str:
    text = " ".join((muster or "").split())
    if len(text) < TEXT_MIN:
        raise RegelError(
            f"Muster „{text}“ ist zu kurz — mindestens {TEXT_MIN} Zeichen", "muster"
        )
    if len(text) > TEXT_MAX:
        raise RegelError(f"Muster zu lang — höchstens {TEXT_MAX} Zeichen", "muster")
    return text


def _pruefe_entwurf_werte(e: RegelEntwurf) -> RegelEntwurf:
    if e.feld not in FELDER:
        raise RegelError(f"Feld {e.feld!r} unbekannt", "feld")
    try:
        soll = pruefe_kontonummer(e.soll_konto, "Soll")
        haben = pruefe_kontonummer(e.haben_konto, "Haben")
    except KontoError as fehler:
        raise RegelError(str(fehler), "konto") from fehler
    return RegelEntwurf(
        pruefe_text(e.muster),
        e.feld,
        e.richtung,
        soll,
        haben,
        e.steuer_schluessel,
        e.quelle_buchung_id,
        e.buchungstext,
    )


def regel_aus_entwurf(e: RegelEntwurf, name: str = "neu") -> Regel:
    return Regel.aus_text(
        name,
        e.muster,
        e.soll_konto,
        e.haben_konto,
        steuer_schluessel=e.steuer_schluessel,
        buchungstext=e.buchungstext,
        feld=e.feld,
        richtung=e.richtung.value if e.richtung else None,
    )


# --- Regelwerk ------------------------------------------------------------------------


def regel_aus_db(
    r: Kontierungsregel, einstellung: Einstellung = "automatisch"
) -> Regel:
    muster = text_muster(r.muster) if r.ist_text else r.muster
    pruefen = einstellung == "pruefen"
    return Regel(
        r.name,
        muster,
        r.soll_konto,
        r.haben_konto,
        steuer_schluessel=r.steuer_schluessel,
        buchungstext=r.buchungstext,
        feld=r.feld,
        richtung=r.richtung.value if r.richtung else None,
        confidence=PRUEFEN_CONFIDENCE if pruefen else 1.0,
        hinweis="Einstellung: prüfen" if pruefen else None,
    )


def gelernte_regeln(session: Session, einstellung: Einstellung) -> list[Regel]:
    if einstellung == "aus":
        return []
    regeln = []
    for r in lade_kontierungsregeln(session, nur_aktive=True):
        try:
            regeln.append(regel_aus_db(r, einstellung))
        except re.error:  # an accounti vorbei gespeichert — journal pruefen meldet es
            LOG.warning("Gelernte Regel mit ungültigem Muster übersprungen")
    return regeln


def lade_regelwerk(
    session: Session,
    regeldatei: str | Path | None,
    einstellung: Einstellung = "automatisch",
) -> RegelwerkEngine:
    """Gelernt (neueste zuerst) → Regeldatei der Gesellschaft → Standard.

    ``regeldatei``: in der CLI ``betrieb.kontext.regeln_datei()``, in Web und REST
    ``gesellschaft.regeln`` — kein eigener Ausweichpfad."""
    from accounti.klassifikation.regeln_loader import lade_regeln

    eigene = lade_regeln(regeldatei) if regeldatei else []
    return RegelwerkEngine(
        gelernte_regeln(session, einstellung) + eigene + list(STANDARD_REGELN)
    )


# --- Vorschau -------------------------------------------------------------------------


@dataclass(frozen=True)
class Beispiel:
    datum: date
    gegenkonto: str
    betrag: Decimal
    verwendungszweck: str
    kontierung: str | None  # bisherige Buchung „Soll an Haben“ oder None (offen)


@dataclass
class Vorschau:
    entwurf: RegelEntwurf
    gesamt: int = 0  # Umsätze im Zeitraum
    treffer: int = 0  # in der Richtung der Regel
    gegenrichtung: int = 0  # Muster passt, Richtung nicht: nicht betroffen
    anders_kontiert: int = 0  # Treffer, die heute anders gebucht sind
    beispiele: list[Beispiel] = field(default_factory=list)
    greift_fuer_umsatz: bool = False
    verdraengt: str | None = None  # Regel, die bisher für diesen Umsatz griff
    warnungen: list[str] = field(default_factory=list)
    hinweis: str = (
        "Die Regel wirkt nur auf Umsätze, die noch nicht gebucht sind (und auf "
        "Umsätze, die ein reines Storno wieder öffnet) — nicht rückwirkend."
    )


def _kontierung_je_umsatz(session: Session) -> dict[UUID, str]:
    from accounti.db.repository import lade_buchungen

    ergebnis: dict[UUID, str] = {}
    for b in lade_buchungen(session):
        if b.transaktion_id is None or b.storno_von or b.storniert_durch:
            continue
        ergebnis.setdefault(b.transaktion_id, f"{b.soll_konto} an {b.haben_konto}")
    return ergebnis


def pruefe_entwurf(
    session: Session,
    entwurf: RegelEntwurf,
    umsatz: Transaktion | None,
    regelwerk: RegelwerkEngine,
    *,
    heute: date | None = None,
    einstellung: Einstellung = "automatisch",
    kontenrahmen: Kontenrahmen | None = None,
) -> Vorschau:
    """Was träfe die Regel? Umsätze der letzten 24 Monate, getrennt nach Richtung."""
    from accounti.db.repository import lade_transaktionen

    v = Vorschau(entwurf)
    if len(entwurf.muster.strip()) < TEXT_MIN:
        v.warnungen.append(
            f"Muster zu kurz (unter {TEXT_MIN} Zeichen) — es träfe zu viele Umsätze"
        )
        return v
    regel = regel_aus_entwurf(entwurf)
    bis = heute or date.today()
    von = bis - timedelta(days=VORSCHAU_TAGE)
    umsaetze = [t for t in lade_transaktionen(session) if von <= t.datum <= bis]
    kontierung = _kontierung_je_umsatz(session)
    ziel = f"{entwurf.soll_konto} an {entwurf.haben_konto}"
    treffer = []
    for t in umsaetze:
        if not regel.passt_muster(t):
            continue
        if regel.passt_richtung(t):
            treffer.append(t)
        else:
            v.gegenrichtung += 1
    v.gesamt = len(umsaetze)
    v.treffer = len(treffer)
    v.anders_kontiert = sum(
        1 for t in treffer if kontierung.get(t.id) not in (None, ziel)
    )
    for t in sorted(treffer, key=lambda t: (t.datum, str(t.id)), reverse=True)[
        :BEISPIELE
    ]:
        v.beispiele.append(
            Beispiel(
                t.datum,
                t.gegenkonto_name or "",
                t.betrag,
                t.verwendungszweck,
                kontierung.get(t.id),
            )
        )
    if umsatz is not None:
        v.greift_fuer_umsatz = regel.passt(umsatz)
        if v.greift_fuer_umsatz:
            bisher = next((r for r in regelwerk.regeln if r.passt(umsatz)), None)
            v.verdraengt = bisher.name if bisher is not None else None
    if v.gesamt >= BREIT_AB and v.treffer > BREIT_ANTEIL * v.gesamt:
        v.warnungen.append(
            f"Muster sehr breit: {v.treffer} von {v.gesamt} Umsätzen "
            f"(über {int(BREIT_ANTEIL * 100)} %) — genauer fassen"
        )
    vorhandene = [
        r
        for r in lade_kontierungsregeln(session, nur_aktive=True)
        if r.muster.casefold() == entwurf.muster.casefold()
    ]
    if vorhandene:
        v.warnungen.append(
            f"Dasselbe Muster ist schon gelernt (Regel {vorhandene[0].name}) — die "
            "neue Regel hätte Vorrang"
        )
    if kontenrahmen is not None:
        for konto in (entwurf.soll_konto, entwurf.haben_konto):
            if not kontenrahmen.ist_geldkonto(konto) and not kontobezeichnung(
                konto, kontenrahmen
            ):
                v.warnungen.append(
                    f"Konto {konto} hat keine Bezeichnung im Kontenrahmen — Nummer "
                    "prüfen"
                )
    if einstellung == "aus":
        v.warnungen.append(
            "buchhaltung.gelernte_regeln steht auf „aus“ — die Regel wird gespeichert, "
            "greift aber erst nach dem Umschalten"
        )
    return v


# --- Lernen ---------------------------------------------------------------------------


def _name(session: Session, basis: str) -> str:
    slug = "_".join(re.findall(r"\w+", basis.casefold()))[:80] or "regel"
    vorhanden = regelnamen(session)
    name = f"gelernt_{slug}"
    nr = 2
    while name in vorhanden:
        name = f"gelernt_{slug}_{nr}"
        nr += 1
    return name


def lerne(
    session: Session,
    entwurf: RegelEntwurf,
    person: str,
    *,
    jetzt: datetime | None = None,
) -> Kontierungsregel:
    """Text-Regel aus einem Entwurf (Browser, ``korrigiere --lernen``)."""
    e = _pruefe_entwurf_werte(entwurf)
    regel = Kontierungsregel(
        name=_name(session, e.muster),
        muster=e.muster,
        ist_text=True,
        feld=e.feld,
        richtung=e.richtung,
        soll_konto=e.soll_konto,
        haben_konto=e.haben_konto,
        steuer_schluessel=e.steuer_schluessel,
        buchungstext=e.buchungstext,
        quelle_buchung_id=e.quelle_buchung_id,
        herkunft=RegelHerkunft.KORREKTUR,
        angelegt_von=person,
        angelegt_am=jetzt or datetime.now(),
    )
    speichere_regel(session, regel)
    return regel


def lerne_regex(
    session: Session,
    name: str,
    muster: str,
    soll: str,
    haben: str,
    steuer: int | None,
    person: str,
    *,
    feld: Feld = "beide",
    richtung: Richtung | None = None,
    jetzt: datetime | None = None,
) -> Kontierungsregel:
    """Regel mit regulärem Ausdruck vom Betreiber (``accounti lerne``)."""
    name = name.strip()
    if not name or len(name) > 100:
        raise RegelError("Regelname fehlt oder ist länger als 100 Zeichen", "name")
    if len(muster) > REGEX_MAX:
        raise RegelError(f"Muster zu lang — höchstens {REGEX_MAX} Zeichen", "muster")
    try:
        re.compile(muster, re.IGNORECASE)
    except re.error as fehler:
        raise RegelError(
            f"Muster ist kein gültiger regulärer Ausdruck: {fehler}", "muster"
        ) from fehler
    if name in regelnamen(session):
        raise RegelError(f"Regelname {name} ist schon vergeben", "name")
    try:
        soll, haben = (
            pruefe_kontonummer(soll, "Soll"),
            pruefe_kontonummer(haben, "Haben"),
        )
    except KontoError as fehler:
        raise RegelError(str(fehler), "konto") from fehler
    regel = Kontierungsregel(
        name=name,
        muster=muster,
        ist_text=False,
        feld=feld,
        richtung=richtung,
        soll_konto=soll,
        haben_konto=haben,
        steuer_schluessel=steuer,
        buchungstext=name[:60],
        herkunft=RegelHerkunft.LERNE,
        angelegt_von=person,
        angelegt_am=jetzt or datetime.now(),
    )
    speichere_regel(session, regel)
    return regel


def lerne_sachkonto(
    session: Session, buchung: Buchungssatz, soll: str, haben: str, person: str
) -> str | None:
    """Belegbuchung auf ein Personenkonto: das Sachkonto wird zum Vorschlag am Kontakt
    (Journal ``sachkonto_gelernt``). ``None``, wenn es nichts zu lernen gibt."""
    from accounti.db.repository import (
        aktualisiere_kontakt,
        lade_kontakt,
        lade_posten_fuer_beleg,
    )
    from accounti.pruefung.journal import schreibe

    if buchung.beleg_id is None:
        return None
    posten = lade_posten_fuer_beleg(session, buchung.beleg_id)
    if posten is None:
        return None
    kontakt = lade_kontakt(session, str(posten.kontakt_id))
    if kontakt.kreditor_konto == haben:
        sachkonto = soll  # Eingang: Aufwand an Kreditor
    elif kontakt.debitor_konto == soll:
        sachkonto = haben  # Ausgang: Debitor an Erlös
    else:
        return None
    bisher = kontakt.sachkonto
    aktualisiere_kontakt(session, kontakt.model_copy(update={"sachkonto": sachkonto}))
    schreibe(
        session,
        "sachkonto_gelernt",
        "kontakt",
        str(kontakt.id),
        nachher={"sachkonto": sachkonto, "bisher": bisher},
        grund=f"aus Buchung {str(buchung.id)[:8]}",
        person=person,
    )
    return f"Sachkonto {sachkonto} als Vorschlag für {kontakt.name}"


def deaktiviere(
    session: Session, regel_id: UUID | str, person: str, grund: str
) -> Kontierungsregel:
    if not (grund or "").strip():
        raise RegelError("Grund für das Deaktivieren fehlt", "grund")
    try:
        return deaktiviere_regel(session, regel_id, person, grund)
    except ValueError as fehler:
        raise RegelError(str(fehler)) from fehler


# --- Übernahme alter Einträge aus der Regeldatei --------------------------------------


@dataclass
class Uebernahme:
    uebernommen: list[str] = field(default_factory=list)
    uebersprungen: list[str] = field(default_factory=list)  # Name schon vergeben
    ungueltig: list[str] = field(default_factory=list)


def uebernehme_aus_datei(
    session: Session,
    regeldatei: str | Path,
    person: str,
    *,
    probe: bool = False,
    jetzt: datetime | None = None,
) -> Uebernahme:
    """``gelernt_*``-Einträge der Regeldatei → ``kontierungsregeln`` (ohne Richtung,
    Muster bleibt regulärer Ausdruck — er ist schon ``re.escape``). Die Datei bleibt
    unverändert; die Einträge löscht der Betreiber von Hand."""
    pfad = Path(regeldatei)
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) if pfad.is_file() else []
    ergebnis = Uebernahme()
    vorhanden = regelnamen(session)
    zeit = jetzt or datetime.now()
    for nr, eintrag in enumerate(daten or []):
        if not isinstance(eintrag, dict):
            continue
        name = str(eintrag.get("name") or "")
        if not name.startswith("gelernt_"):
            continue
        if name in vorhanden:
            ergebnis.uebersprungen.append(name)
            continue
        try:
            muster = str(eintrag["muster"])
            re.compile(muster)
            regel = Kontierungsregel(
                name=name[:100],
                muster=muster,
                ist_text=False,
                feld=eintrag.get("feld", "verwendungszweck"),
                richtung=eintrag.get("richtung"),
                soll_konto=str(eintrag["soll_konto"]),
                haben_konto=str(eintrag["haben_konto"]),
                steuer_schluessel=eintrag.get("steuer_schluessel"),
                buchungstext=(eintrag.get("buchungstext") or None),
                herkunft=RegelHerkunft.UEBERNAHME,
                angelegt_von=person,
                # Vorrang wie in der Datei (die erste passende Regel gewinnt): ein
                # früherer Eintrag gilt als neuer
                angelegt_am=zeit - timedelta(microseconds=nr),
            )
        except (KeyError, re.error, ValueError):
            ergebnis.ungueltig.append(name)
            continue
        vorhanden.add(name)
        ergebnis.uebernommen.append(name)
        if not probe:
            try:
                speichere_regel(session, regel)
            except IntegrityError as fehler:  # pragma: no cover — gleichzeitig angelegt
                raise RegelError(f"Regelname {name} ist schon vergeben") from fehler
    return ergebnis


# --- Liste ----------------------------------------------------------------------------


@dataclass(frozen=True)
class GelernteRegel:
    regel: Kontierungsregel
    treffer: int  # Buchungen, die sie seither kontiert hat


def lade_gelernte_regeln(session: Session) -> list[GelernteRegel]:
    regeln = lade_kontierungsregeln(session)
    zaehler = zaehle_regeltreffer(session, (r.name for r in regeln))
    return [GelernteRegel(r, zaehler.get(r.name, 0)) for r in regeln]


def namen(regeln: Iterable[Regel]) -> list[str]:
    return [r.name for r in regeln]
