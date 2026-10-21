"""Storno statt Änderung (Spec 4.4) — Freigabe, Korrektur, Storno, Export-Vermerk.

Vor der Freigabe ist eine Buchung ein Vorschlag und darf direkt korrigiert werden.
Ab der Freigabe (``auto``, ``geprueft``, ``korrigiert``, ``exportiert``) ist die
Korrektur ein Storno mit Neubuchung: Die Stornobuchung tauscht Soll und Haben bei
gleichen Beträgen und gleichem Steuerschlüssel (die Konvention des Projekts, mit der
sich Salden, Kennziffern, OSS und DATEV-Export von selbst umkehren), das Original
bekommt ``storniert_durch``, der Storno ``storno_von`` — beide bleiben sichtbar.
Die Neubuchung übernimmt alles vom Original (Transaktion, Beleg, Belegposition,
Belegnummer, Datum, Text, Betrag) und ändert nur, was korrigiert wird. Die
Sperre in ``ereignisse`` lässt andere Wege gar nicht erst zu.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from accounti.abschluss.kontenrahmen import Kontenrahmen, lade_kontenrahmen
from accounti.anzeige import datum_de
from accounti.db.repo_pruefung import setze_storniert_durch, speichere_korrektur
from accounti.db.repository import (
    aktualisiere_buchung,
    finde_buchung,
    setze_status,
    speichere_buchung,
)
from accounti.db.tabellen import BuchungssatzRow
from accounti.models import Buchungssatz, BuchungStatus
from accounti.models.pruefung import Buchungskorrektur
from accounti.pruefung.ereignisse import gesperrt
from accounti.pruefung.journal import schreibe
from accounti.pruefung.person import aktuelle_person, journal_kontext
from accounti.steuer.umsatzsteuer import UStBerechner

FREIGEGEBEN = frozenset(
    {
        BuchungStatus.AUTO_GEBUCHT,
        BuchungStatus.GEPRUEFT,
        BuchungStatus.KORRIGIERT,
        BuchungStatus.EXPORTIERT,
    }
)
VORSCHLAG = frozenset({BuchungStatus.ENTWURF, BuchungStatus.ZUR_PRUEFUNG})
NULL = Decimal("0")
_JE_ABFRAGE = 500  # Buchungen je IN-Abfrage
# DATEV-Schlüssel, deren Steuer im Zahlbetrag steckt → (Satz)
_IM_BRUTTO = {
    3: Decimal("19"),
    2: Decimal("7"),
    9: Decimal("19"),
    8: Decimal("7"),
}


class StornoError(ValueError):
    """Storno, Korrektur oder Freigabe ist so nicht möglich."""


def ist_freigegeben(b: Buchungssatz) -> bool:
    return b.status in FREIGEGEBEN


@dataclass
class Korrektur:
    original: Buchungssatz
    neu: Buchungssatz | None  # direkt korrigiert bzw. Neubuchung (None: nur Storno)
    storno: Buchungssatz | None = None  # None: direkt korrigierter Vorschlag
    korrektur: Buchungskorrektur | None = None

    @property
    def direkt(self) -> bool:
        return self.storno is None


def _lade(session: Session, buchung_id: str) -> Buchungssatz:
    try:
        return finde_buchung(session, buchung_id)
    except ValueError as fehler:
        raise StornoError(str(fehler)) from fehler


def _kurz(b: Buchungssatz) -> str:
    return str(b.id)[:8]


def _nicht_storniert(b: Buchungssatz) -> None:
    if b.storno_von is not None:
        raise StornoError(
            f"Buchung {_kurz(b)} ist selbst ein Storno (von {str(b.storno_von)[:8]}) — "
            "eine Stornobuchung wird nicht korrigiert"
        )
    if b.storniert_durch is not None:
        raise StornoError(
            f"Buchung {_kurz(b)} ist schon storniert (durch "
            f"{str(b.storniert_durch)[:8]}) — gegebenenfalls die Neubuchung korrigieren"
        )


def _steuer(
    b: Buchungssatz, steuer: int | None, ohne_steuer: bool
) -> tuple[int | None, Decimal, Decimal | None]:
    """(Schlüssel, Netto, Steuer) nach der Korrektur — aus dem Brutto der Buchung."""
    if ohne_steuer and steuer is not None:
        raise StornoError("--steuer und --ohne-steuer schließen sich aus")
    if not ohne_steuer and steuer is None:  # Schlüssel bleibt
        return b.steuer_schluessel, b.betrag_netto, b.steuer_betrag
    schluessel = None if ohne_steuer else steuer
    if schluessel == b.steuer_schluessel:
        return b.steuer_schluessel, b.betrag_netto, b.steuer_betrag
    if b.beleg_id is not None:
        raise StornoError(
            f"Buchung {_kurz(b)} hat einen Beleg — ihre Steuer kommt aus dem Beleg "
            "bzw. aus dem Ausgleich; nur Konten korrigieren"
        )
    brutto = b.betrag_netto + (b.steuer_betrag or NULL)
    if schluessel in _IM_BRUTTO:
        netto = UStBerechner().brutto_zu_netto(brutto, _IM_BRUTTO[schluessel])
        return schluessel, netto, brutto - netto
    return schluessel, brutto, None


def _pruefe_umkehrbar(b: Buchungssatz, kr: Kontenrahmen) -> None:
    """Die Gegenbuchung hebt die Steuer nur auf, wenn genau eine Seite ein Geld- oder
    Personenkonto ist (``abschluss/salden.py``)."""
    if not b.steuer_betrag or kr.steuerkonto(b.steuer_schluessel) is None:
        return
    if kr.ist_geldkonto(b.soll_konto) == kr.ist_geldkonto(b.haben_konto):
        raise StornoError(
            f"Buchung {_kurz(b)} ({b.soll_konto} an {b.haben_konto}, Schlüssel "
            f"{b.steuer_schluessel}) lässt sich nicht durch Gegenbuchung stornieren: "
            "beide Seiten haben dieselbe Natur, die Steuer höbe sich nicht auf — "
            "bitte mit dem Steuerberater klären"
        )


def _stornodatum(session: Session, b: Buchungssatz, datum: date | None) -> date:
    tag = datum or b.datum
    if gesperrt(session.connection(), tag):
        if datum is None:
            raise StornoError(
                f"Buchung {_kurz(b)} liegt in einem abgeschlossenen Zeitraum "
                f"({datum_de(b.datum)}) — Storno und Neubuchung mit --datum in einen "
                "offenen Zeitraum legen"
            )
        raise StornoError(f"{datum_de(tag)} liegt in einem abgeschlossenen Zeitraum")
    return tag


def _storno(
    session: Session,
    b: Buchungssatz,
    von: str,
    grund: str,
    datum: date | None,
    kr: Kontenrahmen,
    neu: Buchungssatz | None,
) -> Korrektur:
    _nicht_storniert(b)
    if not ist_freigegeben(b):
        raise StornoError(
            f"Buchung {_kurz(b)} ist noch ein Vorschlag ({b.status.value}) — direkt "
            "korrigieren statt stornieren"
        )
    _pruefe_umkehrbar(b, kr)
    tag = _stornodatum(session, b, datum)
    storno = b.model_copy(
        update={
            "id": uuid4(),
            "soll_konto": b.haben_konto,
            "haben_konto": b.soll_konto,
            "datum": tag,
            "buchungstext": f"Storno {b.buchungstext}"[:60],
            "status": BuchungStatus.GEPRUEFT,
            "confidence": 1.0,
            "geprueft_von": von[:50],
            "storno_von": b.id,
            "storniert_durch": None,
        }
    )
    korrektur = Buchungskorrektur(
        original_id=b.id,
        storno_id=storno.id,
        neubuchung_id=neu.id if neu else None,
        datum=tag,
        grund=grund,
        person=von,
    )
    with journal_kontext(person=von, grund=grund, bezug=f"korrektur {korrektur.id}"):
        speichere_buchung(session, storno)
        session.flush()
        setze_storniert_durch(session, b.id, storno.id)
        if neu is not None:
            neu = neu.model_copy(update={"datum": tag})
            speichere_buchung(session, neu)
            session.flush()
        speichere_korrektur(session, korrektur)
    return Korrektur(_lade(session, str(b.id)), neu, storno, korrektur)


def storniere(
    session: Session,
    buchung_id: str,
    *,
    grund: str,
    von: str | None = None,
    datum: date | None = None,
    kontenrahmen: Kontenrahmen | None = None,
) -> Korrektur:
    """Hebt eine freigegebene Buchung durch eine Gegenbuchung auf (ohne Neubuchung)."""
    if not grund.strip():
        raise StornoError("Grund für das Storno fehlt")
    b = _lade(session, buchung_id)
    person = aktuelle_person(von)
    return _storno(
        session,
        b,
        person,
        grund.strip(),
        datum,
        kontenrahmen or lade_kontenrahmen(),
        None,
    )


def korrigiere(
    session: Session,
    buchung_id: str,
    soll: str,
    haben: str,
    *,
    steuer: int | None = None,
    ohne_steuer: bool = False,
    von: str | None = None,
    grund: str | None = None,
    datum: date | None = None,
    kontenrahmen: Kontenrahmen | None = None,
) -> Korrektur:
    """Vorschlag: direkt korrigieren. Freigegeben: Storno und Neubuchung.

    Erhalten bleiben Transaktion, Beleg, Belegposition, Belegnummer, Text und der
    Betrag der Buchung; ``steuer`` rechnet Netto und Steuer aus ihrem Brutto neu.
    """
    b = _lade(session, buchung_id)
    _nicht_storniert(b)
    person = aktuelle_person(von)
    schluessel, netto, steuerbetrag = _steuer(b, steuer, ohne_steuer)
    aenderung = {
        "soll_konto": soll,
        "haben_konto": haben,
        "steuer_schluessel": schluessel,
        "betrag_netto": netto,
        "steuer_betrag": steuerbetrag,
        "status": BuchungStatus.KORRIGIERT,
        "confidence": 1.0,
        "geprueft_von": person[:50],
    }
    text = grund or (
        f"Korrektur: {b.soll_konto} an {b.haben_konto} → {soll} an {haben}"
        + (f", Schlüssel {schluessel}" if schluessel != b.steuer_schluessel else "")
    )
    if not ist_freigegeben(b):
        if datum is not None:
            raise StornoError(
                "--datum gilt nur für das Storno einer freigegebenen Buchung"
            )
        with journal_kontext(person=person, grund=text):
            neu = aktualisiere_buchung(
                session, str(b.id), b.model_copy(update=aenderung)
            )
            session.flush()
        return Korrektur(b, neu)
    if all(
        getattr(b, k) == v
        for k, v in aenderung.items()
        if k
        in (
            "soll_konto",
            "haben_konto",
            "steuer_schluessel",
            "betrag_netto",
            "steuer_betrag",
        )
    ):
        raise StornoError(f"Die Korrektur ändert an Buchung {_kurz(b)} nichts")
    neu = b.model_copy(update={**aenderung, "id": uuid4(), "storniert_durch": None})
    return _storno(
        session, b, person, text, datum, kontenrahmen or lade_kontenrahmen(), neu
    )


def freigeben(
    session: Session, buchung_id: str, von: str | None = None
) -> tuple[Buchungssatz, bool]:
    """Vorschlag oder automatische Buchung → ``geprueft``; (Buchung, geändert?)."""
    b = _lade(session, buchung_id)
    if b.status in VORSCHLAG or b.status is BuchungStatus.AUTO_GEBUCHT:
        person = aktuelle_person(von)
        with journal_kontext(person=person):
            neu = setze_status(
                session, str(b.id), BuchungStatus.GEPRUEFT, geprueft_von=person[:50]
            )
            session.flush()
        return neu, True
    return b, False


def markiere_exportiert(
    session: Session,
    buchungen: list[Buchungssatz],
    datei: Path | None,
    art: str,
) -> tuple[int, int]:
    """Freigegebene, exportierte Buchungen → ``exportiert``; Journal ``export``.

    Buchungen in abgeschlossenen Zeiträumen bleiben, wie sie sind (die Sperre nimmt
    keinen Statuswechsel an); sie stehen im Journaleintrag. Ergebnis: (markiert,
    gesperrt). Die Zeilen werden blockweise geladen und in einem Flush geschrieben —
    nicht je Buchung (jeder Zwischen-Flush kostete Sperrabfragen und Journal).
    """
    verbindung = session.connection()
    sperren: dict[str, Any] = {}  # gesperrte Jahre/Monate, einmal gelesen
    offen, gesperrt_ids = [], []
    for b in buchungen:
        if b.status not in FREIGEGEBEN - {BuchungStatus.EXPORTIERT}:
            continue
        if gesperrt(verbindung, b.datum, sperren):
            gesperrt_ids.append(str(b.id))
        else:
            offen.append(str(b.id))
    markiert = []
    with session.no_autoflush:
        for start in range(0, len(offen), _JE_ABFRAGE):
            teil = offen[start : start + _JE_ABFRAGE]
            for zeile in session.query(BuchungssatzRow).filter(
                BuchungssatzRow.id.in_(teil)
            ):
                zeile.status = BuchungStatus.EXPORTIERT.value
                markiert.append(zeile.id)
    session.flush()
    inhalt = datei.read_bytes() if datei is not None and datei.is_file() else b""
    schreibe(
        session,
        "export",
        "export",
        art,
        nachher={
            "datei": datei.name if datei is not None else None,
            "sha256": hashlib.sha256(inhalt).hexdigest() if inhalt else None,
            "anzahl": len(buchungen),
            "markiert": sorted(markiert),
            "gesperrt": sorted(gesperrt_ids),
        },
    )
    return len(markiert), len(gesperrt_ids)
