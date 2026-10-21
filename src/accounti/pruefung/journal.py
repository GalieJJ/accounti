"""Das Journal — fortlaufend, nur anfügbar, jeder Eintrag an seinen Vorgänger gekettet.

Jeder Eintrag trägt laufende Nummer, Zeitpunkt, Person, Vorgang, Objekt und den
Stand vorher/nachher als kanonisches JSON (alle Spalten der Zeile, Beträge mit der
Skala ihrer Spalte). Der Hash ist SHA-256 über alle Felder außer dem Hash selbst —
inklusive Vorgänger-Hash. So fällt auf (``pruefe_journal``):

* ein veränderter Eintrag (Hash stimmt nicht),
* ein entfernter oder eingeschobener Eintrag (Nummer oder Verkettung),
* eine Buchung oder ein Beleg, der an accounti vorbei geändert, gelöscht oder
  angelegt wurde (Abgleich des Bestands mit dem letzten Stand im Journal) — damit
  fällt auch ein am Ende abgeschnittenes Journal auf, solange die Daten noch da sind.

Angefügt wird über die Verbindung der laufenden Transaktion: Ein Rollback nimmt
Vorgang und Eintrag gemeinsam zurück. Die Einträge zu Buchungen, Belegen,
Zahlungsläufen und Abschlüssen entstehen von selbst (``ereignisse``); ``schreibe``
ist für Vorgänge ohne eigene Zeile (Export, Verfahrensdokumentation).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Column, Connection, Float, Numeric, Table, insert, select, text
from sqlalchemy.orm import Session

from accounti.db.tabellen import BelegRow, BuchungssatzRow
from accounti.db.tabellen_abschluss import AbschlussRow
from accounti.db.tabellen_pruefung import JournalRow, PeriodenabschlussRow
from accounti.models.pruefung import Journaleintrag
from accounti.pruefung.person import aktuelle_person, kontext

GENESIS = "0" * 64
PERSON_LAENGE = 100
GRUND_LAENGE = 500
BEZUG_LAENGE = 100
# Postgres: Nummernvergabe serialisieren (beliebige, feste Schlüsselzahl)
_SPERRSCHLUESSEL = 7_202_610


def kanonisch(daten: Mapping[str, Any] | None) -> str | None:
    if daten is None:
        return None
    return json.dumps(daten, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _allgemein(wert: Any) -> Any:
    if wert is None or isinstance(wert, bool | int | str):
        return wert
    if isinstance(wert, datetime | date):
        return wert.isoformat()
    return str(wert)


def _umwandler(spalte: Column[Any]) -> Callable[[Any], Any]:
    """Wie ein Spaltenwert normiert wird — je Spaltentyp einmal bestimmt."""
    typ = spalte.type
    if isinstance(typ, Float):
        return lambda wert: None if wert is None else float(wert)
    if isinstance(typ, Numeric):
        skala = typ.scale

        def zahl(wert: Any) -> Any:
            if wert is None:
                return None
            d = Decimal(str(wert))
            return f"{d:.{skala}f}" if skala is not None else str(d)

        return zahl
    return _allgemein


def _wert(spalte: Column[Any], wert: Any) -> Any:
    """Spaltenwert so, dass Python-Stand und Datenbankstand gleich aussehen."""
    return _umwandler(spalte)(wert)


_SPALTEN: dict[tuple[int, frozenset[str]], list[tuple[str, Callable[[Any], Any]]]] = {}


def schnappschuss(
    tabelle: Table, zeile: Mapping[Any, Any], ohne: Iterable[str] = ()
) -> dict[str, Any]:
    """Alle Spalten einer Zeile, normiert — ohne die genannten."""
    weg = frozenset(ohne)
    schluessel = (id(tabelle), weg)
    spalten = _SPALTEN.get(schluessel)
    if spalten is None:
        spalten = [
            (s.name, _umwandler(s)) for s in tabelle.columns if s.name not in weg
        ]
        _SPALTEN[schluessel] = spalten
    return {name: f(zeile[name]) for name, f in spalten if name in zeile}


def _hash(daten: Mapping[str, Any]) -> str:
    roh = json.dumps(daten, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(roh.encode()).hexdigest()


def eintrag_hash(e: Journaleintrag) -> str:
    return _hash(e.model_dump(mode="json", exclude={"hash"}))


def journal_vorhanden(verbindung: Connection) -> bool:
    """Gibt es die Tabelle? (Eine Datenbank von vor Baustein 7 hat sie nicht.)"""
    if verbindung.info.get("accounti_journal"):
        return True
    da = verbindung.dialect.has_table(verbindung, JournalRow.__tablename__)
    if da:
        verbindung.info["accounti_journal"] = True
    return bool(da)


@dataclass
class Vorgang:
    """Ein Journaleintrag, bevor er Nummer und Hash bekommt."""

    vorgang: str
    objekt_typ: str
    objekt_id: str
    vorher: dict[str, Any] | None = None
    nachher: dict[str, Any] | None = None
    grund: str | None = None
    bezug: str | None = None
    person: str | None = None


def _kurz(wert: str | None, laenge: int) -> str | None:
    return wert[:laenge] if wert is not None else None


def fuege_an(verbindung: Connection, vorgaenge: list[Vorgang]) -> list[Journaleintrag]:
    """Hängt die Vorgänge in dieser Reihenfolge an das Journal an."""
    if not vorgaenge:
        return []
    if verbindung.dialect.name == "postgresql":  # pragma: no cover — nur Postgres
        verbindung.execute(text(f"SELECT pg_advisory_xact_lock({_SPERRSCHLUESSEL})"))
    letzter = verbindung.execute(
        select(JournalRow.nr, JournalRow.hash).order_by(JournalRow.nr.desc()).limit(1)
    ).first()
    nr, vorgaenger = (letzter[0], letzter[1]) if letzter else (0, GENESIS)
    ctx = kontext()
    jetzt = datetime.now()
    # der Zeitpunkt so, wie ihn eintrag_hash serialisiert — einmal je Aufruf
    vorlage = Journaleintrag(
        zeitpunkt=jetzt, person="", vorgang="", objekt_typ="", objekt_id=""
    )
    zeit = vorlage.model_dump(mode="json")["zeitpunkt"]
    person = ctx.person or aktuelle_person()
    zeilen = []
    for v in vorgaenge:
        nr += 1
        daten = {
            "nr": nr,
            "zeitpunkt": zeit,
            "person": (v.person or person)[:PERSON_LAENGE],
            "vorgang": v.vorgang,
            "objekt_typ": v.objekt_typ,
            "objekt_id": v.objekt_id,
            "vorher": kanonisch(v.vorher),
            "nachher": kanonisch(v.nachher),
            "grund": _kurz(v.grund if v.grund is not None else ctx.grund, GRUND_LAENGE),
            "bezug": _kurz(v.bezug if v.bezug is not None else ctx.bezug, BEZUG_LAENGE),
            "vorgaenger_hash": vorgaenger,
        }
        vorgaenger = _hash(daten)  # wie eintrag_hash, ohne Modell je Eintrag
        zeilen.append({**daten, "zeitpunkt": jetzt, "hash": vorgaenger})
    verbindung.execute(insert(JournalRow), zeilen)
    return [Journaleintrag.model_construct(**z) for z in zeilen]


def schreibe(
    session: Session,
    vorgang: str,
    objekt_typ: str,
    objekt_id: str,
    *,
    vorher: dict[str, Any] | None = None,
    nachher: dict[str, Any] | None = None,
    grund: str | None = None,
    bezug: str | None = None,
    person: str | None = None,
) -> Journaleintrag | None:
    """Ein Vorgang ohne eigene Zeile (z.B. Export) — ``None`` ohne Journal-Tabelle."""
    session.flush()
    verbindung = session.connection()
    if not journal_vorhanden(verbindung):
        return None
    (e,) = fuege_an(
        verbindung,
        [
            Vorgang(
                vorgang, objekt_typ, objekt_id, vorher, nachher, grund, bezug, person
            )
        ],
    )
    return e


# ---------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------


def _eintrag(r: JournalRow) -> Journaleintrag:
    return Journaleintrag.model_validate(
        {f: getattr(r, f) for f in Journaleintrag.model_fields}
    )


def lade_journal(
    session: Session,
    *,
    von: date | None = None,
    bis: date | None = None,
    objekt_id: str | None = None,
    vorgang: str | None = None,
) -> list[Journaleintrag]:
    """Einträge in Nummernfolge; ``objekt_id`` als Anfang (z.B. 8 Zeichen)."""
    query = session.query(JournalRow).order_by(JournalRow.nr)
    if von is not None:
        query = query.filter(
            JournalRow.zeitpunkt >= datetime.combine(von, datetime.min.time())
        )
    if bis is not None:
        query = query.filter(
            JournalRow.zeitpunkt <= datetime.combine(bis, datetime.max.time())
        )
    if objekt_id is not None:
        query = query.filter(JournalRow.objekt_id.like(f"{objekt_id.lower()}%"))
    if vorgang is not None:
        query = query.filter(JournalRow.vorgang == vorgang)
    return [_eintrag(r) for r in query.all()]


def lade_eintrag(session: Session, nr: int) -> Journaleintrag | None:
    r = session.get(JournalRow, nr)
    return _eintrag(r) if r is not None else None


# ---------------------------------------------------------------------------
# Prüfen
# ---------------------------------------------------------------------------

# Objekte, deren Bestand mit dem Journal abgeglichen wird
BESTAND: dict[str, Table] = {
    "buchung": BuchungssatzRow.__table__,  # type: ignore[dict-item]
    "beleg": BelegRow.__table__,  # type: ignore[dict-item]
}


@dataclass(frozen=True)
class Journalbefund:
    art: str  # luecke, verkettung, veraendert, kopf, ohne_eintrag, abweichung, fehlt
    text: str
    nr: int | None = None
    objekt: str | None = None


@dataclass
class Journalpruefung:
    anzahl: int = 0
    kopf_nr: int = 0
    kopf_hash: str = GENESIS
    befunde: list[Journalbefund] = field(default_factory=list)
    vorhanden: bool = True

    @property
    def in_ordnung(self) -> bool:
        return self.vorhanden and not self.befunde


def _pruefe_kette(eintraege: list[Journaleintrag], p: Journalpruefung) -> None:
    vorher, erwartet = GENESIS, 1
    for e in eintraege:
        if e.nr != erwartet:
            luecke = f"{erwartet} bis {e.nr - 1}" if e.nr - 1 > erwartet else erwartet
            p.befunde.append(
                Journalbefund("luecke", f"Eintrag {luecke} fehlt", nr=e.nr)
            )
        if e.vorgaenger_hash != vorher:
            p.befunde.append(
                Journalbefund(
                    "verkettung",
                    f"Eintrag {e.nr}: Verkettung zum Vorgänger gebrochen",
                    nr=e.nr,
                )
            )
        if eintrag_hash(e) != e.hash:
            p.befunde.append(
                Journalbefund("veraendert", f"Eintrag {e.nr} wurde verändert", nr=e.nr)
            )
        vorher, erwartet = e.hash, e.nr + 1


def _pruefe_kopf(
    eintraege: list[Journaleintrag], kopf: str, p: Journalpruefung
) -> None:
    nr_text, _, erwartet = kopf.partition(":")
    if not nr_text.strip().isdigit() or not erwartet.strip():
        p.befunde.append(Journalbefund("kopf", f"Anker {kopf!r}: erwartet NR:HASH"))
        return
    nr = int(nr_text)
    gefunden = next((e for e in eintraege if e.nr == nr), None)
    if gefunden is None:
        p.befunde.append(Journalbefund("kopf", f"Eintrag {nr} des Ankers fehlt", nr=nr))
    elif not gefunden.hash.startswith(erwartet.strip().lower()):
        p.befunde.append(
            Journalbefund(
                "kopf", f"Eintrag {nr} hat nicht mehr den notierten Hash", nr=nr
            )
        )


def letzter_stand(eintraege: list[Journaleintrag]) -> dict[tuple[str, str], Any]:
    """Je Objekt der letzte Stand laut Journal — ``None`` nach dem Verwerfen."""
    stand: dict[tuple[str, str], Any] = {}
    for e in eintraege:
        if e.objekt_typ not in BESTAND:
            continue
        schluessel = (e.objekt_typ, e.objekt_id)
        if e.nachher is not None:
            stand[schluessel] = json.loads(e.nachher)
        elif e.vorher is not None:
            stand[schluessel] = None
    return stand


def _unterschiede(alt: Mapping[str, Any], neu: Mapping[str, Any]) -> list[str]:
    return [
        f"{k}: {alt.get(k)!r} → {neu.get(k)!r}"
        for k in sorted(set(alt) | set(neu))
        if alt.get(k) != neu.get(k)
    ]


def _pruefe_bestand(
    session: Session, eintraege: list[Journaleintrag], p: Journalpruefung
) -> None:
    stand = letzter_stand(eintraege)
    verbindung = session.connection()
    for typ, tabelle in BESTAND.items():
        aktuell = {
            str(z["id"]): schnappschuss(tabelle, z)
            for z in verbindung.execute(select(tabelle)).mappings()
        }
        for ident, jetzt in aktuell.items():
            objekt = f"{typ} {ident[:8]}"
            if (typ, ident) not in stand:
                p.befunde.append(
                    Journalbefund(
                        "ohne_eintrag",
                        f"{objekt} hat keinen Journaleintrag (an accounti vorbei "
                        "angelegt? Bestand von vor dem Journal: accounti journal "
                        "uebernehmen)",
                        objekt=ident,
                    )
                )
                continue
            zuletzt = stand[(typ, ident)]
            if zuletzt is None:
                p.befunde.append(
                    Journalbefund(
                        "abweichung",
                        f"{objekt} ist laut Journal verworfen, steht aber im Bestand",
                        objekt=ident,
                    )
                )
            elif zuletzt != jetzt:
                felder = "; ".join(_unterschiede(zuletzt, jetzt))
                p.befunde.append(
                    Journalbefund(
                        "abweichung",
                        f"{objekt} wurde an accounti vorbei geändert ({felder})",
                        objekt=ident,
                    )
                )
        for (t, ident), zuletzt in stand.items():
            if t == typ and zuletzt is not None and ident not in aktuell:
                p.befunde.append(
                    Journalbefund(
                        "fehlt",
                        f"{typ} {ident[:8]} fehlt im Bestand (an accounti vorbei "
                        "gelöscht)",
                        objekt=ident,
                    )
                )


# Sperren: Vorgang im Journal → gesperrt?  (Objekt „periode“ bzw. „geschaeftsjahr“)
_SPERRVORGAENGE = {
    "periode_geschlossen": True,
    "periode_geoeffnet": False,
    "jahr_abgeschlossen": True,
    "jahr_geoeffnet": False,
    "sperre_uebernommen": True,  # vor dem Journal gesperrt (uebernehme_bestand)
}
_SPERRTABELLEN = (
    ("periode", PeriodenabschlussRow.__tablename__, "monat"),
    ("geschaeftsjahr", AbschlussRow.__tablename__, "jahr"),
)


def _sperren_laut_journal(
    eintraege: list[Journaleintrag],
) -> dict[tuple[str, str], bool]:
    laut_journal: dict[tuple[str, str], bool] = {}
    for e in eintraege:
        if e.vorgang in _SPERRVORGAENGE:
            laut_journal[(e.objekt_typ, e.objekt_id)] = _SPERRVORGAENGE[e.vorgang]
    return laut_journal


def _sperren_im_bestand(verbindung: Connection) -> dict[tuple[str, str], bool]:
    tatsaechlich: dict[tuple[str, str], bool] = {}
    for typ, tabelle, spalte in _SPERRTABELLEN:
        if not verbindung.dialect.has_table(verbindung, tabelle):
            continue
        zeilen = verbindung.execute(
            text(f"SELECT {spalte}, gesperrt FROM {tabelle}")  # feste Namen
        )
        for ident, gesperrt in zeilen:
            tatsaechlich[(typ, str(ident))] = bool(gesperrt)
    return tatsaechlich


def _pruefe_sperren(
    session: Session, eintraege: list[Journaleintrag], p: Journalpruefung
) -> None:
    """Monats- und Jahressperre müssen dem letzten Vorgang im Journal entsprechen."""
    laut_journal = _sperren_laut_journal(eintraege)
    tatsaechlich = _sperren_im_bestand(session.connection())
    for (typ, ident), gesperrt in sorted(tatsaechlich.items()):
        erwartet = laut_journal.get((typ, ident), False)
        if gesperrt != erwartet:
            was = "Monat" if typ == "periode" else "Geschäftsjahr"
            p.befunde.append(
                Journalbefund(
                    "abweichung",
                    f"{was} {ident} ist {'gesperrt' if gesperrt else 'offen'}, laut "
                    f"Journal {'gesperrt' if erwartet else 'offen'} — an accounti "
                    "vorbei geändert",
                    objekt=ident,
                )
            )


def pruefe_journal(session: Session, kopf: str | None = None) -> Journalpruefung:
    """Kette, optional Anker ``NR:HASH`` und Abgleich mit dem Bestand."""
    p = Journalpruefung()
    if not journal_vorhanden(session.connection()):
        p.vorhanden = False
        return p
    eintraege = lade_journal(session)
    p.anzahl = len(eintraege)
    if eintraege:
        p.kopf_nr, p.kopf_hash = eintraege[-1].nr, eintraege[-1].hash
    _pruefe_kette(eintraege, p)
    if kopf is not None:
        _pruefe_kopf(eintraege, kopf, p)
    _pruefe_bestand(session, eintraege, p)
    _pruefe_sperren(session, eintraege, p)
    return p


def uebernehme_bestand(session: Session, person: str | None = None) -> int:
    """Buchungen, Belege und Sperren ohne Journaleintrag einmal als Bestand eintragen.

    Sperren: ein Jahr oder Monat, das vor dem Journal abgeschlossen wurde, steht danach
    als ``sperre_uebernommen`` im Journal — sonst meldete ``pruefe_journal`` es auf
    jeder aktualisierten Datenbank als „an accounti vorbei gesperrt“. Ein Objekt, zu
    dem das Journal schon einen Sperrvorgang kennt, bleibt unberührt: Weicht es ab, ist
    das ein echter Befund."""
    verbindung = session.connection()
    if not journal_vorhanden(verbindung):
        return 0
    session.flush()
    eintraege = lade_journal(session)
    bekannt = {(e.objekt_typ, e.objekt_id) for e in eintraege}
    vorgaenge = []
    laut_journal = _sperren_laut_journal(eintraege)
    for (typ, ident), gesperrt in sorted(_sperren_im_bestand(verbindung).items()):
        if gesperrt and (typ, ident) not in laut_journal:
            vorgaenge.append(
                Vorgang(
                    "sperre_uebernommen",
                    typ,
                    ident,
                    nachher={"gesperrt": True},
                    grund="Sperre von vor dem Journal übernommen",
                    person=person,
                )
            )
    for typ, tabelle in BESTAND.items():
        for z in verbindung.execute(select(tabelle)).mappings():
            ident = str(z["id"])
            if (typ, ident) in bekannt:
                continue
            vorgaenge.append(
                Vorgang(
                    "bestand_uebernommen",
                    typ,
                    ident,
                    nachher=schnappschuss(tabelle, z),
                    grund="Bestand von vor dem Journal übernommen",
                    person=person,
                )
            )
    fuege_an(verbindung, vorgaenge)
    return len(vorgaenge)
