"""Sperre, Storno-Regel und Journal lassen sich über ORM-Wege nicht umgehen.

Regressionstests zu den Befunden der Prüfung von Baustein 7 (abgelaufene Attribute,
Wechsel des Primärschlüssels, Massenwege, großer Flush, Import ohne Nebeneffekt).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import insert, update
from sqlalchemy.orm import Session

import accounti
from accounti.db import init_db, session_factory
from accounti.db.repository import speichere_buchung
from accounti.db.tabellen import BuchungssatzRow, UnveraenderbarError
from accounti.db.tabellen_abschluss import JahrGesperrtError
from accounti.models import Buchungssatz, BuchungStatus
from accounti.pruefung.ereignisse import BuchungFestgeschriebenError
from accounti.pruefung.journal import lade_journal, pruefe_journal
from accounti.pruefung.perioden import schliesse
from accounti.pruefung.storno import storniere
from tests.pruefung_hilfe import anlegen, buchung, db_url, make_session_fixture

_ = make_session_fixture


def _fest(tag: date, **kw: object) -> Buchungssatz:
    return buchung(
        status=BuchungStatus.GEPRUEFT, tag=tag, steuer=None, schluessel=None, **kw
    )


def _geschlossen(make_session, monat: str) -> None:
    with make_session() as s:
        schliesse(s, monat, "erika", trotzdem=True)
        s.commit()


def _in_ordnung(make_session) -> bool:
    with make_session() as s:
        return pruefe_journal(s).in_ordnung


# --- abgelaufene Attribute (nach commit) ------------------------------------------


@pytest.mark.parametrize("mit_inhalt", [True, False])
def test_abgelaufenes_datum_verlaesst_den_gesperrten_monat_nicht(
    make_session, mit_inhalt
):
    jan = _fest(date(2026, 1, 15))
    anlegen(make_session, jan)
    _geschlossen(make_session, "2026-01")
    with make_session() as s:
        z = s.get(BuchungssatzRow, str(jan.id))
        s.commit()  # expire_on_commit: alle Attribute abgelaufen
        z.datum = date(2026, 3, 1)
        if mit_inhalt:
            z.betrag_netto = Decimal("999.00")
        with pytest.raises(JahrGesperrtError, match="2026-01"):
            s.commit()
        s.rollback()
    with make_session() as s:
        z = s.get(BuchungssatzRow, str(jan.id))
        assert (z.datum, z.betrag_netto) == (date(2026, 1, 15), Decimal("100.00"))
    assert _in_ordnung(make_session)


def test_abgelaufenes_datum_in_den_gesperrten_monat_hinein(make_session):
    vorschlag = buchung(tag=date(2026, 3, 5), steuer=None, schluessel=None)
    anlegen(make_session, vorschlag)
    _geschlossen(make_session, "2026-01")
    with make_session() as s:
        z = s.get(BuchungssatzRow, str(vorschlag.id))
        s.commit()
        z.datum = date(2026, 1, 20)
        with pytest.raises(JahrGesperrtError, match="2026-01"):
            s.commit()


@pytest.mark.parametrize("monat_gesperrt", [True, False])
def test_abgelaufener_stornovermerk_laesst_sich_nicht_ueberschreiben(
    make_session, monat_gesperrt
):
    orig = _fest(date(2026, 1, 10))
    anlegen(make_session, orig)
    with make_session() as s:
        storniere(s, str(orig.id), grund="falsch", von="erika")
        s.commit()
    if monat_gesperrt:
        _geschlossen(make_session, "2026-01")
    with make_session() as s:
        z = s.get(BuchungssatzRow, str(orig.id))
        s.commit()
        z.storniert_durch = str(uuid4())
        with pytest.raises((BuchungFestgeschriebenError, JahrGesperrtError)):
            s.commit()
    assert _in_ordnung(make_session)


def test_stornovermerk_ohne_stornobuchung_abgelehnt(make_session):
    fest = _fest(date(2026, 3, 10))
    anlegen(make_session, fest)
    with make_session() as s:
        z = s.get(BuchungssatzRow, str(fest.id))
        z.storniert_durch = str(uuid4())  # gibt es nicht
        with pytest.raises(BuchungFestgeschriebenError, match="Stornobuchung"):
            s.commit()
        s.rollback()
        andere = _fest(date(2026, 3, 11))
        speichere_buchung(s, andere)
        s.flush()
        z = s.get(BuchungssatzRow, str(fest.id))
        z.storniert_durch = str(andere.id)  # vorhanden, aber kein Storno von ihr
        with pytest.raises(BuchungFestgeschriebenError, match="Stornobuchung"):
            s.commit()


# --- Primärschlüssel ---------------------------------------------------------------


@pytest.mark.parametrize(
    "status", [BuchungStatus.EXPORTIERT, BuchungStatus.ZUR_PRUEFUNG]
)
def test_wechsel_des_primaerschluessels_abgelehnt(make_session, status):
    b = buchung(status=status, tag=date(2026, 4, 1), steuer=None, schluessel=None)
    anlegen(make_session, b)
    with make_session() as s:
        z = s.get(BuchungssatzRow, str(b.id))
        z.id = str(uuid4())
        z.betrag_netto = Decimal("1.00")
        with pytest.raises(UnveraenderbarError, match="Primärschlüssel"):
            s.commit()
    with make_session() as s:
        assert s.get(BuchungssatzRow, str(b.id)) is not None
        assert [e.vorgang for e in lade_journal(s)] == ["buchung_angelegt"]
    assert _in_ordnung(make_session)


def test_loeschen_und_neu_anlegen_mit_gleicher_id(make_session):
    b = buchung(tag=date(2026, 4, 1), steuer=None, schluessel=None)
    anlegen(make_session, b)
    with make_session() as s:
        s.delete(s.get(BuchungssatzRow, str(b.id)))
        speichere_buchung(s, b.model_copy(update={"soll_konto": "4100"}))
        s.commit()
        assert s.get(BuchungssatzRow, str(b.id)).soll_konto == "4100"
        vorgaenge = [e.vorgang for e in lade_journal(s)]
    assert vorgaenge[-1] != "buchung_verworfen"
    assert vorgaenge == ["buchung_angelegt", "buchung_korrigiert"]
    assert _in_ordnung(make_session)


# --- Massenwege über das ORM -------------------------------------------------------


def _zeile(tag: date) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "datum": tag,
        "soll_konto": "4900",
        "haben_konto": "1200",
        "betrag_netto": Decimal("5.00"),
        "buchungstext": "Masse",
        "status": "geprueft",
        "confidence": 1.0,
    }


@pytest.mark.parametrize(
    "weg",
    [
        "insert",
        "bulk_save_objects",
        "bulk_insert_mappings",
        "bulk_update_mappings",
        "update_tabelle",
    ],
)
def test_massenwege_auf_buchungen_abgelehnt(make_session, weg):
    fest = _fest(date(2026, 3, 5))
    anlegen(make_session, fest)
    _geschlossen(make_session, "2026-02")
    with make_session() as s:
        with pytest.raises(UnveraenderbarError, match="buchungssaetze"):
            if weg == "insert":
                s.execute(insert(BuchungssatzRow), [_zeile(date(2026, 2, 3))])
            elif weg == "bulk_save_objects":
                s.bulk_save_objects([BuchungssatzRow(**_zeile(date(2026, 2, 4)))])
            elif weg == "bulk_insert_mappings":
                s.bulk_insert_mappings(BuchungssatzRow, [_zeile(date(2026, 2, 4))])
            elif weg == "bulk_update_mappings":
                s.bulk_update_mappings(
                    BuchungssatzRow,
                    [{"id": str(fest.id), "betrag_netto": Decimal("1.00")}],
                )
            else:  # Core-Update auf die Tabelle, aber über die Sitzung
                t = BuchungssatzRow.__table__
                s.execute(
                    update(t).where(t.c.id == str(fest.id)).values(soll_konto="1")
                )
        s.rollback()
    with make_session() as s:
        assert s.query(BuchungssatzRow).count() == 1
    assert _in_ordnung(make_session)


# --- ein großer Flush --------------------------------------------------------------


def _vorschlag(i: int) -> Buchungssatz:
    return buchung(
        tag=date(2026, 1, 1 + i % 28), steuer=None, schluessel=None, netto="1.00"
    )


def test_after_flush_bildet_die_neuen_objekte_einmal(make_session, monkeypatch):
    zugriffe = 0
    original = Session.new

    def gezaehlt(self: Session):  # type: ignore[no-untyped-def]
        nonlocal zugriffe
        zugriffe += 1
        return original.fget(self)  # type: ignore[attr-defined]

    with make_session() as s:
        for i in range(300):
            speichere_buchung(s, _vorschlag(i))
        monkeypatch.setattr(Session, "new", property(gezaehlt))
        s.flush()
        monkeypatch.undo()
        s.commit()
        assert len(lade_journal(s)) == 300
    assert zugriffe < 20  # vorher: einmal je Objekt


def test_fuenftausend_buchungen_in_einem_flush(make_session):
    start = time.perf_counter()
    with make_session() as s:
        for i in range(5000):
            speichere_buchung(s, _vorschlag(i))
        s.commit()
    dauer = time.perf_counter() - start
    with make_session() as s:
        assert len(lade_journal(s)) == 5000
    assert dauer < 60, f"{dauer:.1f} s für 5.000 Buchungen in einem Flush"


# --- Import ohne Nebeneffekt -------------------------------------------------------


def _python(code: str) -> subprocess.CompletedProcess[str]:
    quelle = str(Path(accounti.__file__).resolve().parents[1])
    umgebung = {**os.environ, "PYTHONPATH": quelle}
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=umgebung,
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize(
    "modul",
    ["accounti.pruefung.journal", "accounti.pruefung.ereignisse", "accounti.db"],
)
def test_module_lassen_sich_einzeln_importieren(modul):
    r = _python(f"import {modul}")
    assert r.returncode == 0, r.stderr


def test_repository_ohne_init_db_erzwingt_die_storno_regel(tmp_path):
    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    fest = buchung(status=BuchungStatus.EXPORTIERT, steuer=None, schluessel=None)
    with fabrik() as s:
        speichere_buchung(s, fest)
        s.commit()
    engine.dispose()
    code = f"""
from accounti.db import session_factory
from accounti.db.repository import aktualisiere_buchung, finde_buchung
_, fabrik = session_factory({url!r})
with fabrik() as s:
    b = finde_buchung(s, {str(fest.id)!r})
    neu = b.model_copy(update={{"soll_konto": "4100"}})
    try:
        aktualisiere_buchung(s, str(b.id), neu)
        s.commit()
        print("DURCHGEKOMMEN")
    except Exception as fehler:
        print(type(fehler).__name__)
"""
    r = _python(code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "BuchungFestgeschriebenError"


def test_export_vermerk_in_einem_flush(make_session):
    """Befund A4: ``markiere_exportiert`` flusht nicht je Buchung (vorher ein
    Autoflush je ``session.get`` mit Sperrabfragen und Journaleintrag)."""
    from sqlalchemy import event

    from accounti.db.repository import lade_buchungen
    from accounti.pruefung.storno import markiere_exportiert

    with make_session() as s:
        for i in range(300):
            speichere_buchung(
                s, _vorschlag(i).model_copy(update={"status": BuchungStatus.GEPRUEFT})
            )
        s.commit()
    flushes = 0

    def zaehle(*_: object) -> None:
        nonlocal flushes
        flushes += 1

    with make_session() as s:
        buchungen = lade_buchungen(s)
        event.listen(s, "before_flush", zaehle)
        start = time.perf_counter()
        assert markiere_exportiert(s, buchungen, None, "datev") == (300, 0)
        dauer = time.perf_counter() - start
        s.commit()
        event.remove(s, "before_flush", zaehle)
        assert pruefe_journal(s).in_ordnung
    assert flushes <= 3, flushes
    assert dauer < 30, f"{dauer:.1f} s"
