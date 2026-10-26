"""Lernschleife: aus einer Korrektur wird eine Regel (Datenbank der Gesellschaft).

Für CLI (``accounti korrigiere --lernen``, ``lerne``, ``regeln …``) und Browser
(Supervisions-Queue) dieselben Funktionen (Spec 3: keine UI-eigene Logik):

* ``entwurf_fuer`` / ``entwurf_aus_korrektur`` — Muster (der ganze Name der
  Gegenpartei ohne Rechtsform, sonst das erste Wort des Verwendungszwecks), Feld,
  **Richtung** aus dem Vorzeichen des Umsatzes, Konten und Schlüssel der Neubuchung;
  das Finanzkonto des Umsatzes muss auf seiner Seite bleiben.
* ``pruefe_entwurf`` — Vorschau: was träfe die Regel in den letzten 24 Monaten?
  Trifft sie andere Gegenparteien, ist die Gegenpartei ein Zahlungsdienst oder hat
  der Umsatz keinen Namen der Gegenpartei, muss die Warnung bestätigt werden
  (``Vorschau.bestaetigung_noetig``).
* ``lerne`` (Text, aus dem Browser), ``lerne_regex`` (Betreiber, CLI),
  ``lerne_sachkonto`` (Belegbuchung → Sachkonto am Kontakt), ``deaktiviere``,
  ``uebernehme_aus_datei`` (alte ``gelernt_*``-Einträge der Regeldatei und gewählte).
* ``lade_regelwerk`` — gelernte Regeln (neueste zuerst, übernommene dahinter) →
  Regeldatei der Gesellschaft
  → Standardregeln des Kontenrahmens. Die gelernte Regel greift also auch dann, wenn
  eine eigene Regel vorher falsch getroffen hat (Akzeptanz 2). Alle drei Quellen
  teilen ein Regelmodell (``engine.Regel``: Richtung ``ausgabe``/``einnahme``,
  Gegenbuchung zur Prüfung, Schranke des Mappers).

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

from accounti.buchung.konten import (
    KontoError,
    finanzkonto_fehler,
    kontobezeichnung,
    pruefe_kontonummer,
    umbuchung_fehler,
    zahlungsmittel,
)
from accounti.db.repo_kontierung import (
    deaktiviere_regel,
    lade_kontierungsregeln,
    regelnamen,
    speichere_regel,
    zaehle_regeltreffer,
)
from accounti.klassifikation.engine import (
    Regel,
    RegelwerkEngine,
    standard_regeln,
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
ZWECK_KURZ = 60  # Verwendungszweck eines Treffers ohne Namen in der Vorschau
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


# Rechtsformen (ohne Punkte, kleingeschrieben): der Mustervorschlag nimmt den Namen
# der Gegenpartei bis vor die erste — „Deutsche Telekom AG“ → „Deutsche Telekom“
RECHTSFORMEN = frozenset(
    {
        "gmbh",
        "ggmbh",
        "mbh",
        "gesmbh",
        "ag",
        "kg",
        "kgaa",
        "ohg",
        "gbr",
        "ug",
        "haftungsbeschränkt",
        "ek",
        "ekfm",
        "ekfr",
        "ev",
        "eg",
        "se",
        "partg",
        "partgmbb",
        "vvag",
        "ltd",
        "limited",
        "inc",
        "llc",
        "llp",
        "plc",
        "corp",
        "co",
        "sa",
        "sarl",
        "sàrl",
        "sas",
        "sca",
        "scs",
        "bv",
        "nv",
        "spa",
        "srl",
        "sl",
        "ab",
        "as",
        "asa",
        "aps",
        "oy",
        "oyj",
        "kft",
        "sro",
        "spzoo",
    }
)
_VERBINDER = frozenset({"&", "+", "-", "und", "u", "et", "and", "cie"})
# Rechtsformen, die auch gewöhnliche Wörter oder Kürzel in Namen sind
_MEHRDEUTIG = frozenset({"co", "ab", "as", "se", "sa", "sl"})
# Zahlungsdienste als Gegenpartei: ein Muster auf ihren Namen träfe jeden Kauf über
# den Dienst, gleich bei welchem Händler
ZAHLUNGSDIENSTE = (
    "PayPal",
    "Klarna",
    "Stripe",
    "Adyen",
    "Mollie",
    "SumUp",
    "Unzer",
    "Heidelpay",
    "Payone",
    "Computop",
    "Ratepay",
    "Riverty",
    "Afterpay",
    "Amazon Payments",
    "Sofort",
    "Giropay",
    "Paydirekt",
    "Zettle",
    "Worldline",
    "Concardis",
    "Nexi",
    "Secupay",
    "Skrill",
)


def _form(wort: str) -> str:
    return "".join(z for z in wort.casefold() if z not in ".,;:()[]")


def _ohne_verbinder(woerter: list[str], ende: int) -> int:
    while ende > 1 and _form(woerter[ende - 1]) in _VERBINDER | {""}:
        ende -= 1
    return ende


def ohne_rechtsform(name: str | None) -> str:
    """Name der Gegenpartei bis vor die erste Rechtsform (ab dem zweiten Wort), ohne
    Verbinder davor: „Bürobedarf Müller GmbH & Co. KG“ → „Bürobedarf Müller“.

    Rechtsformen, die auch Wörter oder Kürzel sind (``_MEHRDEUTIG``: „Co“, „AB“ …),
    kürzen nur, wenn davor mindestens zwei Wörter bleiben — „Kaffee & Co“ bliebe sonst
    „Kaffee“, „Möbel AB Werk Müller“ „Möbel“, ein Muster, das fremde Gegenparteien
    träfe."""
    woerter = (name or "").split()
    ende = len(woerter)
    for i in range(1, len(woerter)):
        form = _form(woerter[i])
        paar = form + (_form(woerter[i + 1]) if i + 1 < len(woerter) else "")
        rechtsform = form if form in RECHTSFORMEN else paar
        if rechtsform not in RECHTSFORMEN:
            continue
        vorher = _ohne_verbinder(woerter, i)
        if rechtsform in _MEHRDEUTIG and vorher < 2:
            continue
        ende = vorher
        break
    ende = _ohne_verbinder(woerter, ende)
    return " ".join(woerter[:ende]).strip(" ,;:-&+")


def _gegenpartei(name: str | None) -> str:
    """Vergleichsschlüssel einer Gegenpartei (ohne Rechtsform, Groß/klein egal)."""
    return " ".join(ohne_rechtsform(name).casefold().split())


def zahlungsdienst(name: str | None) -> str | None:
    """Der Zahlungsdienst, wenn die Gegenpartei einer ist (PayPal, Klarna …)."""
    for dienst in ZAHLUNGSDIENSTE:
        if re.search(text_muster(dienst), name or "", re.IGNORECASE):
            return dienst
    return None


def _auf_laenge(text: str) -> str:
    if len(text) <= TEXT_MAX:
        return text
    gekuerzt = text[: TEXT_MAX + 1].rsplit(" ", 1)[0]
    return gekuerzt if len(gekuerzt) >= TEXT_MIN else text[:TEXT_MAX]


def vorschlag_muster(umsatz: Transaktion) -> str:
    """Der ganze Name der Gegenpartei ohne Rechtsform — das erste Wort träfe fremde
    Gegenparteien („Deutsche“: Telekom, Bahn, Rentenversicherung). Ohne Namen das
    erste Wort des Verwendungszwecks (unter 3 Zeichen die ersten zwei Wörter)."""
    name = ohne_rechtsform(umsatz.gegenkonto_name)
    if len(name) >= TEXT_MIN:
        return _auf_laenge(name)
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
    kontenrahmen: Kontenrahmen | None = None,
) -> RegelEntwurf:
    """Entwurf aus Umsatz und (künftiger) Kontierung. Steht dort das Finanzkonto des
    Umsatzes (zweites Giro, Kreditkarte), speichert die Regel das Standard-Bankkonto —
    ``kontiere_umsaetze`` setzt beim Anwenden das Finanzkonto wieder ein. Das
    Finanzkonto muss auf der Seite seiner Zahlungsrichtung stehen (Ausgabe: Haben),
    sonst ``RegelError`` — die Regel buchte künftige Umsätze am Konto vorbei.

    Sind Soll und Haben beide Zahlungsmittel (Umbuchung Giro ↔ Tagesgeld, Bank ↔
    Kasse oder Kreditkarte, Geldtransit; ``kontenrahmen`` mit den eingerichteten
    Konten, ohne Angabe der mitgelieferte), ebenfalls ``RegelError`` (Feld
    ``regel``): Aus „1200 an 1210“ auf dem Tagesgeld würde sonst „1200 an 1200“
    (Gesamttest 10b-1, H-1)."""
    umbuchung = umbuchung_fehler(
        soll,
        haben,
        zahlungsmittel(buchhaltung, kontenrahmen, (umsatz.sachkonto,)),
    )
    if umbuchung is not None:
        raise RegelError(umbuchung, "regel")
    finanz = umsatz.sachkonto
    if finanz and finanz != buchhaltung.bank_konto:
        soll = buchhaltung.bank_konto if soll == finanz else soll
        haben = buchhaltung.bank_konto if haben == finanz else haben
    fehler = finanzkonto_fehler(
        soll.strip(), haben.strip(), umsatz.betrag, buchhaltung.bank_konto
    )
    if fehler is not None:
        raise RegelError(fehler[1], fehler[0])
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
    kontenrahmen: Kontenrahmen | None = None,
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
        kontenrahmen=kontenrahmen,
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
    if soll == haben:
        raise RegelError(f"Soll und Haben sind dasselbe Konto ({soll})", "regel")
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
    """Gelernte Regel als ``Regel`` des Regelwerks — dieselben Richtungswerte
    (``Richtung.value``) wie Regeldatei und Standardregeln; die Schranke des Mappers
    (Bankseite gegen Vorzeichen) gilt für sie wie für jede andere Quelle."""
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
        pruefen=pruefen,
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
    *,
    buchhaltung: Buchhaltung | None = None,
) -> RegelwerkEngine:
    """Gelernt (neueste zuerst, aus der Regeldatei übernommene dahinter) →
    Regeldatei der Gesellschaft → Standardregeln des Kontenrahmens
    (``engine.standard_regeln`` mit Kontenrahmen und Bankkonto der ``buchhaltung``;
    ohne: SKR03, Bank 1200).

    ``regeldatei``: in der CLI ``betrieb.kontext.regeln_datei()``, in Web und REST
    ``gesellschaft.regeln`` — kein eigener Ausweichpfad. Eine ungültige Regeldatei
    meldet ``KonfigurationError``."""
    from accounti.klassifikation.regeln_loader import lade_regeln

    eigene = lade_regeln(regeldatei) if regeldatei else []
    standard = (
        standard_regeln(buchhaltung.kontenrahmen, buchhaltung.bank_konto)
        if buchhaltung is not None
        else standard_regeln()
    )
    return RegelwerkEngine(gelernte_regeln(session, einstellung) + eigene + standard)


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
    # Muster passt, Richtung nicht: höchstens Gegenbuchung zur Prüfung (wenn sonst keine
    # Regel und kein LLM-Vorschlag greift — RegelwerkEngine.gegenrichtung)
    gegenrichtung: int = 0
    anders_kontiert: int = 0  # Treffer, die heute anders gebucht sind
    beispiele: list[Beispiel] = field(default_factory=list)
    greift_fuer_umsatz: bool = False
    verdraengt: str | None = None  # Regel, die bisher für diesen Umsatz griff
    fremde: list[str] = field(default_factory=list)  # andere Gegenparteien (bis 5)
    fremde_anzahl: int = 0  # Treffer bei anderen Gegenparteien
    zahlungsdienst: str | None = None  # Muster trifft den Namen eines Zahlungsdiensts
    # der Umsatz hat keinen Namen der Gegenpartei: jeder weitere Treffer zählt als
    # fremd, und die Regel braucht immer die Bestätigung
    ohne_namen: bool = False
    warnungen: list[str] = field(default_factory=list)
    hinweis: str = (
        "Die Regel wirkt nur auf Umsätze, die noch nicht gebucht sind (und auf "
        "Umsätze, die ein reines Storno wieder öffnet) — nicht rückwirkend."
    )

    @property
    def bestaetigung_noetig(self) -> bool:
        """Die Regel träfe Umsätze anderer Gegenparteien bzw. jeden Kauf über einen
        Zahlungsdienst, oder der Umsatz hat keinen Namen der Gegenpartei — gespeichert
        wird sie dann nur mit ausdrücklicher Bestätigung (Browser: Haken in der
        Regelvorschau, CLI: ``--trotz-warnung``).

        Ohne Namen stammt das Muster aus dem Verwendungszweck („Beitrag“,
        „Lastschrift“); ob künftige Treffer von derselben Gegenpartei kommen, lässt
        sich nicht prüfen — auch dann nicht, wenn heute keine weiteren Treffer im
        Bestand sind. Eine Regel auf fremde Umsätze bucht Vorsteuer, wo keine ist
        (§ 15 Abs. 1 Nr. 1 UStG), und die Voranmeldung wird falsch (§ 18 UStG)."""
        return bool(self.fremde) or self.zahlungsdienst is not None or self.ohne_namen

    @property
    def bestaetigungsgruende(self) -> list[str]:
        gruende = []
        if self.ohne_namen:
            treffer = (
                f"; das Muster trifft {self.fremde_anzahl} weitere Umsätze "
                f"({', '.join(self.fremde)})"
                if self.fremde
                else ""
            )
            gruende.append(
                "der Umsatz hat keinen Namen der Gegenpartei — ob Umsätze mit "
                f"„{self.entwurf.muster}“ von derselben Gegenpartei stammen, kann "
                f"accounti nicht prüfen{treffer}"
            )
        elif self.fremde:
            gruende.append(
                f"das Muster „{self.entwurf.muster}“ trifft auch andere "
                f"Gegenparteien ({', '.join(self.fremde)}; {self.fremde_anzahl} "
                "Umsätze)"
            )
        if self.zahlungsdienst is not None:
            gruende.append(
                f"die Gegenpartei ist der Zahlungsdienst {self.zahlungsdienst} — das "
                f"Muster träfe jeden Umsatz über {self.zahlungsdienst}, gleich bei "
                "welchem Händler"
            )
        return gruende


def _ohne_namen(t: Transaktion) -> str:
    """Treffer ohne Namen der Gegenpartei: mit dem Anfang des Verwendungszwecks."""
    zweck = " ".join((t.verwendungszweck or "").split())
    if len(zweck) > ZWECK_KURZ:
        zweck = zweck[:ZWECK_KURZ].rstrip() + " …"
    return f"ohne Namen: {zweck}" if zweck else "(ohne Namen)"


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
    regelwerk: RegelwerkEngine | None,
    *,
    heute: date | None = None,
    einstellung: Einstellung = "automatisch",
    kontenrahmen: Kontenrahmen | None = None,
) -> Vorschau:
    """Was träfe die Regel? Umsätze der letzten 24 Monate, getrennt nach Richtung.

    Warnt außerdem, wenn Treffer **andere Gegenparteien** betreffen oder die
    Gegenpartei ein Zahlungsdienst ist (dann ``bestaetigung_noetig``) und wenn weitere
    Treffer heute anders gebucht sind. ``regelwerk``: für „verdrängt Regel X“ (ohne:
    nicht ermittelt)."""
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
        if v.greift_fuer_umsatz and regelwerk is not None:
            bisher = next((r for r in regelwerk.regeln if r.passt(umsatz)), None)
            v.verdraengt = bisher.name if bisher is not None else None
        eigene = _gegenpartei(umsatz.gegenkonto_name)
        # ohne eigenen Namen lässt sich kein weiterer Treffer derselben Gegenpartei
        # zuordnen — alle zählen als fremd
        v.ohne_namen = not eigene
        fremd = [
            t
            for t in treffer
            if t.id != umsatz.id
            and (v.ohne_namen or _gegenpartei(t.gegenkonto_name) != eigene)
        ]
        v.fremde_anzahl = len(fremd)
        for t in fremd:
            name = (t.gegenkonto_name or "").strip() or _ohne_namen(t)
            if name not in v.fremde and len(v.fremde) < BEISPIELE:
                v.fremde.append(name)
        dienst = zahlungsdienst(umsatz.gegenkonto_name)
        if dienst is not None and entwurf.feld != "verwendungszweck":
            name_allein = umsatz.model_copy(update={"verwendungszweck": ""})
            if regel.passt_muster(name_allein):
                v.zahlungsdienst = dienst
        weitere = sum(
            1
            for t in treffer
            if t.id != umsatz.id and kontierung.get(t.id) not in (None, ziel)
        )
        if weitere:
            v.warnungen.append(
                f"{weitere} weitere Treffer sind heute anders gebucht — prüfen, ob "
                "die Regel auch für sie stimmt"
            )
    for grund in v.bestaetigungsgruende:
        v.warnungen.append(grund[0].upper() + grund[1:] + " — Muster genauer fassen")
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
    buchhaltung: Buchhaltung | None = None,
    kontenrahmen: Kontenrahmen | None = None,
) -> Kontierungsregel:
    """Regel mit regulärem Ausdruck vom Betreiber (``accounti lerne``). Sind Soll
    und Haben beide Zahlungsmittel (``buchhaltung``, ``kontenrahmen`` mit den
    eingerichteten Konten), ``RegelError`` — wie ``entwurf_fuer``."""
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
    umbuchung = umbuchung_fehler(
        soll, haben, zahlungsmittel(buchhaltung or Buchhaltung(), kontenrahmen)
    )
    if umbuchung is not None:
        raise RegelError(umbuchung, "regel")
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
    ohne_richtung: list[str] = field(default_factory=list)  # keine Bankseite erkannt
    # bleiben in der Regeldatei und greifen dort wie bisher (hinter den gelernten):
    # ``pruefen: true`` oder ``confidence`` unter 1 kennt eine gelernte Regel nicht
    mit_pruefkennzeichen: list[str] = field(default_factory=list)
    umbuchungen: list[str] = field(default_factory=list)  # Soll und Haben Geldkonten
    eigene: list[str] = field(default_factory=list)  # nicht gelernt_* und nicht gewählt
    unbekannt: list[str] = field(
        default_factory=list
    )  # gewählt, aber nicht in der Datei


def richtung_der_bankseite(
    soll: str, haben: str, bank_konto: str, kontenrahmen: Kontenrahmen | None = None
) -> Richtung | None:
    """Zahlungsrichtung einer Regel aus ihrer Bankseite: Bank im Haben → Ausgabe,
    Bank im Soll → Einnahme (sonst ein Geldkonto des Kontenrahmens; ``None``, wenn
    keine Seite ein Geldkonto ist)."""
    for geld in (
        lambda k: k == bank_konto,
        lambda k: kontenrahmen is not None and kontenrahmen.ist_geldkonto(k),
    ):
        if geld(haben) and not geld(soll):
            return Richtung.AUSGABE
        if geld(soll) and not geld(haben):
            return Richtung.EINNAHME
    return None


def _mit_pruefkennzeichen(eintrag: dict[str, object]) -> bool:
    """``pruefen: true`` oder ``confidence`` unter 1 (``ValueError`` bei ungültigen
    Werten — wie der Lader der Regeldatei)."""
    pruefen = eintrag.get("pruefen", False)
    if not isinstance(pruefen, bool):
        raise ValueError(f"pruefen {pruefen!r}")
    confidence = float(eintrag.get("confidence", 1.0))  # type: ignore[arg-type]
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence {confidence}")
    return pruefen or confidence < 1.0


def uebernehme_aus_datei(
    session: Session,
    regeldatei: str | Path,
    person: str,
    *,
    bank_konto: str = "1200",
    kontenrahmen: Kontenrahmen | None = None,
    probe: bool = False,
    jetzt: datetime | None = None,
    namen: Iterable[str] = (),
    buchhaltung: Buchhaltung | None = None,
) -> Uebernahme:
    """``gelernt_*``-Einträge der Regeldatei (dazu die Einträge mit einem Namen aus
    ``namen``, z. B. von ``accounti lerne --name`` vor 10b) → ``kontierungsregeln``
    (Muster bleibt regulärer Ausdruck — er ist schon ``re.escape``). Die Datei bleibt
    unverändert; die Einträge löscht der Betreiber von Hand. Andere Einträge nennt
    ``Uebernahme.eigene`` — sie bleiben eigene Regeln der Datei.

    Die Richtung kommt aus dem Eintrag, sonst aus seiner Bankseite
    (``richtung_der_bankseite``): Eine übernommene Regel hat Vorrang vor der
    Regeldatei und buchte ohne Richtung die Erstattung derselben Gegenpartei als
    Geldabgang. Ohne erkennbare Bankseite bleibt sie ohne Richtung
    (``Uebernahme.ohne_richtung``).

    Übernommene Regeln stehen hinter allen anderen gelernten
    (``repo_kontierung.lade_kontierungsregeln``) — wie bisher die Datei hinter den
    Korrekturen in der Datenbank —, untereinander in der Reihenfolge der Datei.

    In der Datei bleiben (und greifen dort wie bisher): Einträge mit ``pruefen: true``
    oder ``confidence`` unter 1 — eine gelernte Regel hat kein eigenes
    Prüfkennzeichen, übernommen buchte sie automatisch (``mit_pruefkennzeichen``) —
    und Umbuchungen zwischen Geldkonten (``umbuchungen``, wie ``entwurf_fuer``)."""
    pfad = Path(regeldatei)
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) if pfad.is_file() else []
    ergebnis = Uebernahme()
    vorhanden = regelnamen(session)
    gewaehlt = {n.strip() for n in namen if n and n.strip()}
    gefunden: set[str] = set()
    zeit = jetzt or datetime.now()
    geld = zahlungsmittel(
        buchhaltung or Buchhaltung(bank_konto=bank_konto), kontenrahmen
    )
    for nr, eintrag in enumerate(daten if isinstance(daten, list) else []):
        if not isinstance(eintrag, dict):
            continue
        name = str(eintrag.get("name") or "")
        gefunden.add(name)
        if not name.startswith("gelernt_") and name not in gewaehlt:
            ergebnis.eigene.append(name or "(ohne Namen)")
            continue
        if name in vorhanden:
            ergebnis.uebersprungen.append(name)
            continue
        try:
            muster = str(eintrag["muster"])
            re.compile(muster)
            soll, haben = str(eintrag["soll_konto"]), str(eintrag["haben_konto"])
            if _mit_pruefkennzeichen(eintrag):
                ergebnis.mit_pruefkennzeichen.append(name)
                continue
            if umbuchung_fehler(soll, haben, geld) is not None:
                ergebnis.umbuchungen.append(name)
                continue
            angabe = eintrag.get("richtung")
            if angabe == "beide":  # ausdrücklich ohne Richtung (wie die Regeldatei)
                richtung = None
            elif angabe:
                richtung = Richtung(angabe)
            else:
                richtung = richtung_der_bankseite(soll, haben, bank_konto, kontenrahmen)
            regel = Kontierungsregel(
                name=name[:100],
                muster=muster,
                ist_text=False,
                feld=eintrag.get("feld", "verwendungszweck"),
                richtung=richtung,
                soll_konto=soll,
                haben_konto=haben,
                steuer_schluessel=eintrag.get("steuer_schluessel"),
                buchungstext=(eintrag.get("buchungstext") or None),
                herkunft=RegelHerkunft.UEBERNAHME,
                angelegt_von=person,
                # Vorrang wie in der Datei (die erste passende Regel gewinnt): ein
                # früherer Eintrag gilt als neuer — hinter den anderen gelernten
                # Regeln stehen alle übernommenen (Herkunft, lade_kontierungsregeln)
                angelegt_am=zeit - timedelta(microseconds=nr),
            )
        except (KeyError, TypeError, re.error, ValueError):
            ergebnis.ungueltig.append(name)
            continue
        vorhanden.add(name)
        ergebnis.uebernommen.append(name)
        if richtung is None:
            ergebnis.ohne_richtung.append(name)
        if not probe:
            try:
                speichere_regel(session, regel)
            except IntegrityError as fehler:  # pragma: no cover — gleichzeitig angelegt
                raise RegelError(f"Regelname {name} ist schon vergeben") from fehler
    ergebnis.unbekannt = sorted(gewaehlt - gefunden)
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
