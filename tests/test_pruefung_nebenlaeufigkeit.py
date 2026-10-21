"""Zwei Schreiber gleichzeitig: Prüfen und Schreiben sind atomar (Baustein 7).

Ein zweiter „Prozess“ (eigene Sitzung, eigene Verbindung) handelt genau im Fenster
zwischen der Prüfung in ``before_flush`` und dem Schreiben der ersten Sitzung. Er muss
warten bzw. scheitern — sonst prüft die erste Sitzung gegen einen veralteten Stand
(Regressionstests zu den Befunden M1, N1 und N3 der Nachprüfung).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from accounti.db.repository import (
    finde_buchung,
    lade_buchungen,
    setze_status,
    speichere_buchung,
)
from accounti.db.tabellen import BuchungssatzRow
from accounti.models import Buchungssatz, BuchungStatus
from accounti.pruefung.journal import pruefe_journal, schreibe
from accounti.pruefung.perioden import schliesse
from accounti.pruefung.storno import markiere_exportiert, storniere
from tests.pruefung_hilfe import anlegen, buchung, make_session_fixture

_ = make_session_fixture


def _zweiter(fabrik: sessionmaker[Session], aktion: Callable[[Session], object]) -> str:
    """Der zweite Schreiber — wartet höchstens 50 ms auf die Schreibsperre."""
    try:
        with fabrik() as s2:
            s2.connection().exec_driver_sql("PRAGMA busy_timeout = 50")
            aktion(s2)
            s2.commit()
    except OperationalError as fehler:
        return "gesperrt" if "locked" in str(fehler) else str(fehler)
    return "durchgekommen"


def _dazwischen(
    s: Session, fabrik: sessionmaker[Session], aktion: Callable[[Session], object]
) -> list[str]:
    """Einmal, nach der Prüfung in ``before_flush`` der ersten Sitzung."""
    ergebnis: list[str] = []

    def hook(*_: object) -> None:
        if not ergebnis:
            ergebnis.append(_zweiter(fabrik, aktion))

    event.listen(s, "before_flush", hook)
    return ergebnis


def _in_ordnung(make_session) -> bool:
    with make_session() as s:
        p = pruefe_journal(s)
        assert p.in_ordnung, [b.text for b in p.befunde]
        return True


def _fest(tag: date = date(2026, 3, 5), **kw: object) -> Buchungssatz:
    return buchung(
        status=BuchungStatus.GEPRUEFT, tag=tag, steuer=None, schluessel=None, **kw
    )


def test_export_vermerk_und_storno_gleichzeitig(make_session):
    """Fall 1: A vermerkt den Export, B storniert dieselbe Buchung dazwischen."""
    x = _fest()
    anlegen(make_session, x)
    with make_session() as s:
        b = _dazwischen(
            s,
            make_session,
            lambda s2: storniere(
                s2, str(x.id), grund="parallel", von="b", datum=date(2026, 3, 6)
            ),
        )
        assert markiere_exportiert(s, lade_buchungen(s), None, "datev") == (1, 0)
        s.commit()
    assert b == ["gesperrt"]
    assert _in_ordnung(make_session)
    # danach kommt B durch — gegen den neuen Stand
    with make_session() as s:
        storniere(s, str(x.id), grund="danach", von="b", datum=date(2026, 3, 6))
        s.commit()
    assert _in_ordnung(make_session)


def test_freigabe_waehrend_einer_aenderung(make_session):
    """Fall 2: A ändert den Betrag eines Vorschlags, B gibt ihn dazwischen frei."""
    y = buchung(tag=date(2026, 3, 5), steuer=None, schluessel=None)
    anlegen(make_session, y)
    with make_session() as s:
        b = _dazwischen(
            s,
            make_session,
            lambda s2: setze_status(
                s2, str(y.id), BuchungStatus.GEPRUEFT, geprueft_von="b"
            ),
        )
        s.get(BuchungssatzRow, str(y.id)).betrag_netto = Decimal("1.00")
        s.commit()
    assert b == ["gesperrt"]
    with make_session() as s:
        stand = finde_buchung(s, str(y.id))
    assert (stand.status, stand.betrag_netto) == (
        BuchungStatus.ZUR_PRUEFUNG,
        Decimal("1.00"),
    )
    assert _in_ordnung(make_session)


def test_festschreibung_waehrend_einer_verschiebung(make_session):
    """A verschiebt einen Vorschlag in den Februar, B will den Februar dazwischen
    festschreiben — B bekommt die Sperre nicht (hier nach 50 ms: „gesperrt“)."""
    x = buchung(tag=date(2026, 3, 5), steuer=None, schluessel=None)
    anlegen(make_session, x)
    with make_session() as s:
        b = _dazwischen(
            s, make_session, lambda s2: schliesse(s2, "2026-02", "b", trotzdem=True)
        )
        s.get(BuchungssatzRow, str(x.id)).datum = date(2026, 2, 20)
        s.commit()
    assert b == ["gesperrt"]
    with make_session() as s:
        assert s.execute(text("select count(*) from periodenabschluesse")).scalar() == 0


def test_journalnummer_ohne_vorheriges_schreiben(make_session):
    """N3: ``schreibe`` holt die Sperre, bevor es die höchste Nummer liest."""
    anlegen(make_session, buchung(steuer=None, schluessel=None, netto="1.00"))
    ergebnis: list[str] = []

    def vor_insert(_c, _cur, statement, *_: object) -> None:
        if statement.startswith("INSERT INTO journal") and not ergebnis:
            ergebnis.append(
                _zweiter(
                    make_session,
                    lambda s2: speichere_buchung(
                        s2, buchung(steuer=None, schluessel=None, netto="2.00")
                    ),
                )
            )

    with make_session() as s:
        event.listen(s.connection(), "before_cursor_execute", vor_insert)
        schreibe(s, "export", "export", "datev", nachher={"anzahl": 0})
        s.commit()
    assert ergebnis == ["gesperrt"]
    assert _in_ordnung(make_session)


def test_journal_pruefen_liest_einen_gemeinsamen_stand(make_session, monkeypatch):
    """Befund M-2 (Runde 3): Zwischen dem Lesen des Journals und dem des Bestands
    schreibt ein anderer Prozess — die Prüfung sieht trotzdem einen Stand und meldet
    keinen falschen Befund („ohne_eintrag“)."""
    import accounti.pruefung.journal as journal

    anlegen(make_session, buchung(steuer=None, schluessel=None))
    original = journal.lade_journal
    zweiter: list[str] = []

    def lade_und_schreibe(session, **kw):  # type: ignore[no-untyped-def]
        eintraege = original(session, **kw)
        if not zweiter:
            zweiter.append(
                _zweiter(
                    make_session,
                    lambda s2: speichere_buchung(
                        s2, buchung(steuer=None, schluessel=None, netto="2.00")
                    ),
                )
            )
        return eintraege

    monkeypatch.setattr(journal, "lade_journal", lade_und_schreibe)
    with make_session() as s:
        p = journal.pruefe_journal(s)
    assert p.in_ordnung, [b.text for b in p.befunde]
    assert zweiter == ["gesperrt"]  # SQLite: der Leser hält seinen Stand bis zum Ende
    monkeypatch.undo()
    assert _in_ordnung(make_session)


def test_sqlite_wartet_dreissig_sekunden_auf_die_sperre(tmp_path):
    """Befund N-5: Ein langer Lauf hält die Schreibsperre länger als die 5 s, die
    sqlite3 sonst wartet — session_factory stellt 30 s ein (nur SQLite)."""
    from accounti.db import session_factory
    from tests.pruefung_hilfe import db_url

    engine, fabrik = session_factory(db_url(tmp_path))
    with fabrik() as s:
        assert s.execute(text("PRAGMA busy_timeout")).scalar() == 30000
    engine.dispose()


def test_periode_schliessen_wartet_und_prueft_danach(tmp_path):
    """Befund N-4: B (eigener Thread, übliche Wartezeit) will den Februar schließen,
    während A einen Vorschlag hineinverschiebt. B holt die Sperre vor seinen Prüfungen,
    wartet auf A und lehnt dann wegen des Vorschlags ab."""
    import threading
    import time

    from accounti.db import init_db, session_factory
    from accounti.pruefung.perioden import PeriodeError
    from tests.pruefung_hilfe import db_url

    url = db_url(tmp_path)
    engine, fabrik = session_factory(url)
    init_db(engine)
    x = buchung(tag=date(2026, 3, 5), steuer=None, schluessel=None)
    with fabrik() as s:
        speichere_buchung(s, x)
        s.commit()
    ergebnis: list[str] = []

    def b() -> None:
        _, fabrik_b = session_factory(url)  # eigene Verbindung im eigenen Thread
        try:
            with fabrik_b() as s2:
                schliesse(s2, "2026-02", "b", trotzdem=True)
                s2.commit()
            ergebnis.append("geschlossen")
        except PeriodeError as fehler:
            ergebnis.append(str(fehler))

    with fabrik() as s:
        s.get(BuchungssatzRow, str(x.id)).datum = date(2026, 2, 20)
        s.flush()  # A hält die Schreibsperre
        faden = threading.Thread(target=b)
        faden.start()
        time.sleep(0.5)  # B steht jetzt an der Sperre
        s.commit()
    faden.join(timeout=30)
    assert len(ergebnis) == 1 and "Vorschlag" in ergebnis[0], ergebnis
    engine.dispose()
