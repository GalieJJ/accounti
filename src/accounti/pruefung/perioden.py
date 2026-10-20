"""Periodenabschluss (Spec 4.5): ein festgeschriebener Monat nimmt nichts mehr an.

Die Jahressperre aus Baustein 12 (Saldovortrag, ``abschluss oeffnen``) bleibt, wie
sie ist; der Monat ist die feinere Stufe daneben. Beide teilen sich:

* die Fehlerklasse — ``PeriodeGesperrtError`` ist ein ``JahrGesperrtError``, jeder
  vorhandene Fänger (Kasse, Anlagen, ``opos verbuchen``, Abschluss) behandelt die
  Monatssperre mit;
* die Prüfung am ORM (``db/tabellen_pruefung.py`` wie ``db/tabellen_abschluss.py``) —
  angenommen wird im gesperrten Zeitraum nur der Stornovermerk;
* das Protokoll — Schließen und Öffnen stehen im Abschlussprotokoll (Hash-Kette aus
  Baustein 12) und daraus im Journal;
* die Abfrage ``sperre_am`` für alle, die wissen wollen, ob ein Tag offen ist.

Geschlossen wird nur ein Monat ohne Vorschläge (sie ließen sich danach nicht mehr
freigeben); ungebuchte Umsätze verhindern den Abschluss, außer mit ``trotzdem``.
Geöffnet wird nur mit Grund und nur, solange das Geschäftsjahr offen ist.
"""

from __future__ import annotations

import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from accounti.abschluss.protokoll import protokolliere
from accounti.db.repo_abschluss import ist_gesperrt
from accounti.db.repository import lade_buchungen
from accounti.db.tabellen_pruefung import PeriodenabschlussRow, monat_gesperrt
from accounti.models import BuchungStatus
from accounti.models.pruefung import Periodenabschluss
from accounti.opos.zahlungslauf import offene_transaktionen

_MONAT = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
VORSCHLAG = frozenset({BuchungStatus.ENTWURF, BuchungStatus.ZUR_PRUEFUNG})


class PeriodeError(ValueError):
    """Schließen oder Öffnen ist so nicht möglich."""


def pruefe_monat(text: str) -> str:
    monat = text.strip()
    if not _MONAT.match(monat):
        raise PeriodeError(f"Monat {text!r} bitte als JJJJ-MM angeben, z.B. 2026-08")
    return monat


def grenzen(monat: str) -> tuple[date, date]:
    jahr, nr = int(monat[:4]), int(monat[5:])
    return date(jahr, nr, 1), date(jahr, nr, monthrange(jahr, nr)[1])


@dataclass(frozen=True)
class Sperre:
    art: str  # "jahr" oder "monat"
    zeitraum: str  # "2026" bzw. "2026-08"
    text: str


def sperre_am(session: Session, tag: date) -> Sperre | None:
    """Ist der Tag gesperrt — durch den Jahresabschluss oder einen Monatsabschluss?"""
    if ist_gesperrt(session, tag.year):
        return Sperre(
            "jahr",
            str(tag.year),
            f"Geschäftsjahr {tag.year} ist abgeschlossen (accounti abschluss oeffnen "
            f"--jahr {tag.year})",
        )
    monat = f"{tag:%Y-%m}"
    if monat_gesperrt(session.connection(), monat):
        return Sperre(
            "monat",
            monat,
            f"Monat {monat} ist festgeschrieben (accounti periode oeffnen {monat})",
        )
    return None


def _periode(r: PeriodenabschlussRow) -> Periodenabschluss:
    return Periodenabschluss(
        monat=r.monat,
        gesperrt=r.gesperrt,
        geschlossen_am=r.geschlossen_am,
        geschlossen_von=r.geschlossen_von,
        geoeffnet_am=r.geoeffnet_am,
        geoeffnet_von=r.geoeffnet_von,
        grund=r.grund,
    )


def lade_perioden(session: Session) -> list[Periodenabschluss]:
    rows = session.query(PeriodenabschlussRow).order_by(PeriodenabschlussRow.monat)
    return [_periode(r) for r in rows.all()]


def schliesse(
    session: Session, monat: str, von: str, *, trotzdem: bool = False
) -> Periodenabschluss:
    """Monat festschreiben; protokolliert im Abschlussprotokoll und im Journal."""
    monat = pruefe_monat(monat)
    jahr = int(monat[:4])
    if ist_gesperrt(session, jahr):
        raise PeriodeError(
            f"Geschäftsjahr {jahr} ist schon abgeschlossen — {monat} ist damit gesperrt"
        )
    zeile = session.get(PeriodenabschlussRow, monat)
    if zeile is not None and zeile.gesperrt:
        raise PeriodeError(f"{monat} ist schon geschlossen")
    von_tag, bis_tag = grenzen(monat)
    im_monat = [b for b in lade_buchungen(session) if von_tag <= b.datum <= bis_tag]
    vorschlaege = [b for b in im_monat if b.status in VORSCHLAG]
    if vorschlaege:
        n = len(vorschlaege)
        raise PeriodeError(
            f"{monat}: {n} Vorschl{'äge' if n > 1 else 'ag'} noch nicht freigegeben "
            "(accounti review) — nach dem Abschluss ließe sich nichts mehr freigeben"
        )
    ungebucht = [
        t for t in offene_transaktionen(session) if von_tag <= t.datum <= bis_tag
    ]
    if ungebucht and not trotzdem:
        n = len(ungebucht)
        raise PeriodeError(
            f"{monat}: {n} Umsatz{'' if n == 1 else 'e'} ungebucht (accounti classify) "
            "— mit --trotzdem schließen: sie bleiben dann bis zum Öffnen ungebucht"
        )
    jetzt = datetime.now()
    if zeile is None:
        zeile = PeriodenabschlussRow(monat=monat)
        session.add(zeile)
    zeile.gesperrt = True
    zeile.geschlossen_am = jetzt
    zeile.geschlossen_von = von[:100]
    session.flush()
    protokolliere(
        session,
        jahr,
        "periode_geschlossen",
        von,
        None,
        {"monat": monat, "buchungen": len(im_monat), "ungebucht": len(ungebucht)},
    )
    return _periode(zeile)


def oeffne(session: Session, monat: str, von: str, grund: str) -> Periodenabschluss:
    """Monat wieder öffnen — nur mit Grund und nur bei offenem Geschäftsjahr."""
    monat = pruefe_monat(monat)
    if not grund.strip():
        raise PeriodeError("Grund für das Öffnen fehlt")
    zeile = session.get(PeriodenabschlussRow, monat)
    if zeile is None or not zeile.gesperrt:
        raise PeriodeError(f"{monat} ist nicht geschlossen")
    jahr = int(monat[:4])
    if ist_gesperrt(session, jahr):
        raise PeriodeError(
            f"Geschäftsjahr {jahr} ist abgeschlossen — erst accounti abschluss oeffnen "
            f"--jahr {jahr}"
        )
    zeile.gesperrt = False
    zeile.geoeffnet_am = datetime.now()
    zeile.geoeffnet_von = von[:100]
    zeile.grund = grund.strip()[:500]
    session.flush()
    protokolliere(
        session, jahr, "periode_geoeffnet", von, grund.strip(), {"monat": monat}
    )
    return _periode(zeile)
