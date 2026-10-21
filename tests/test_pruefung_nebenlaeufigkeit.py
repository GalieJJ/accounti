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
from tests.pg_hilfe import mit_postgresql
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


def test_journal_uebernehmen_zweimal_gleichzeitig(make_session, monkeypatch):
    """Verzahnung (M-3): ``journal uebernehmen`` holt die Schreibsperre, bevor es
    Journal und Bestand liest — ein zweiter Lauf dazwischen wartet, statt denselben
    Bestand ein zweites Mal einzutragen."""
    import accounti.pruefung.journal as journal
    from accounti.pruefung.journal import uebernehme_bestand

    anlegen(make_session, buchung(steuer=None, schluessel=None))
    with make_session() as s:
        s.execute(text("DROP TRIGGER journal_kein_delete"))
        s.execute(text("DELETE FROM journal"))
        s.commit()
    original = journal.lade_journal
    zweiter: list[str] = []
    gestartet: list[bool] = []

    def lade_und_dazwischen(session, **kw):  # type: ignore[no-untyped-def]
        eintraege = original(session, **kw)
        if not gestartet:  # nur der erste Lauf lässt den zweiten dazwischen
            gestartet.append(True)
            zweiter.append(_zweiter(make_session, lambda s2: uebernehme_bestand(s2)))
        return eintraege

    monkeypatch.setattr(journal, "lade_journal", lade_und_dazwischen)
    with make_session() as s:
        assert uebernehme_bestand(s, person="jan") == 1
        s.commit()
    assert zweiter == ["gesperrt"]
    with make_session() as s:
        anzahl = s.execute(
            text("SELECT count(*) FROM journal WHERE vorgang = 'bestand_uebernommen'")
        ).scalar()
    assert anzahl == 1
    assert _in_ordnung(make_session)


def test_flush_ohne_journalbezug_holt_keine_schreibsperre(make_session, monkeypatch):
    """Schlussprüfung T-M2: Die Schreibsperre schützt Prüfung und Journal — ein Flush
    ohne erfasste oder geschützte Tabelle (Umsätze, Anmeldeprotokoll, Sitzungen)
    holt sie nicht. Unter PostgreSQL warteten sonst Anmeldungen ohne Frist auf eine
    Buchungstransaktion (siehe den PostgreSQL-Test unten)."""
    from datetime import datetime

    import accounti.pruefung.ereignisse as ereignisse
    from accounti.db import repo_auth
    from accounti.db.repository import speichere_transaktion
    from accounti.models.auth import AuthEreignis
    from tests.pruefung_hilfe import umsatz

    gerufen: list[str] = []
    original = ereignisse.schreibsperre
    monkeypatch.setattr(
        ereignisse, "schreibsperre", lambda v: gerufen.append("x") or original(v)
    )
    with make_session() as s:
        speichere_transaktion(s, umsatz())
        repo_auth.protokolliere_ereignis(
            s,
            AuthEreignis(
                zeitpunkt=datetime.now(),
                art="anmeldung_fehlgeschlagen",
                benutzer="eva",
                quelle="web",
                ok=False,
            ),
        )
        s.flush()
        assert gerufen == []
        speichere_buchung(s, buchung(steuer=None, schluessel=None))
        s.flush()
        assert gerufen == ["x"]
        s.commit()


@mit_postgresql
def test_anmeldung_wartet_nicht_auf_eine_buchung_postgresql(pg_datenbank):
    """T-M2 unter PostgreSQL: Eine Buchungstransaktion hält die Advisory-Sperre bis
    zum Commit; ein Auth-Ereignis daneben wartet trotzdem nicht."""
    import threading
    import time
    from datetime import datetime

    from accounti.db import init_db, repo_auth, session_factory
    from accounti.models.auth import AuthEreignis

    engine, fabrik = session_factory(pg_datenbank())
    init_db(engine)
    gehalten, frei = threading.Event(), threading.Event()

    def halter() -> None:
        with fabrik() as s:
            speichere_buchung(s, buchung(steuer=None, schluessel=None))
            s.flush()
            gehalten.set()
            frei.wait(timeout=10)
            s.commit()

    t = threading.Thread(target=halter)
    t.start()
    assert gehalten.wait(timeout=10)
    start = time.monotonic()
    with fabrik() as s:
        repo_auth.protokolliere_ereignis(
            s,
            AuthEreignis(
                zeitpunkt=datetime.now(),
                art="anmeldung_fehlgeschlagen",
                benutzer="eva",
                quelle="web",
                ok=False,
            ),
        )
        s.commit()
    dauer = time.monotonic() - start
    frei.set()
    t.join(timeout=10)
    engine.dispose()
    assert dauer < 1.0, dauer


def test_journal_pruefen_schreibt_offene_aenderungen_nicht_fest(make_session):
    """Schlussprüfung T-N1: Ruft jemand die Prüfung mit offenen Änderungen auf, darf
    der Lesestand sie nicht festschreiben — ein späteres rollback nimmt sie zurück."""
    from accounti.pruefung.journal import pruefe_journal

    with make_session() as s:
        speichere_buchung(s, buchung(steuer=None, schluessel=None))
        assert pruefe_journal(s).in_ordnung
        s.rollback()
    with make_session() as s:
        assert s.execute(text("SELECT count(*) FROM buchungssaetze")).scalar() == 0
        assert s.execute(text("SELECT count(*) FROM journal")).scalar() == 0


@mit_postgresql
def test_journal_pruefen_haelt_schreiber_nicht_an_postgresql(pg_datenbank, monkeypatch):
    """T-N2: Unter PostgreSQL liest die Prüfung aus einem Schnappschuss (REPEATABLE
    READ READ ONLY) — ein Schreiber kommt währenddessen durch, die Prüfung sieht
    trotzdem einen Stand (kein falscher Befund „ohne_eintrag“)."""
    import accounti.pruefung.journal as journal
    from accounti.db import init_db, session_factory

    engine, fabrik = session_factory(pg_datenbank())
    init_db(engine)
    anlegen(fabrik, buchung(steuer=None, schluessel=None))
    original = journal.lade_journal
    zweiter: list[str] = []

    def schreiber() -> str:
        try:
            with fabrik() as s2:
                s2.execute(text("SET lock_timeout = '500ms'"))
                speichere_buchung(s2, buchung(steuer=None, schluessel=None, netto="2"))
                s2.commit()
        except OperationalError:
            return "gesperrt"
        return "durchgekommen"

    def lade_und_schreibe(session, **kw):  # type: ignore[no-untyped-def]
        eintraege = original(session, **kw)
        if not zweiter:
            zweiter.append(schreiber())
        return eintraege

    monkeypatch.setattr(journal, "lade_journal", lade_und_schreibe)
    with fabrik() as s:
        p = journal.pruefe_journal(s)
    assert p.in_ordnung, [b.text for b in p.befunde]
    assert zweiter == ["durchgekommen"]
    monkeypatch.undo()
    with fabrik() as s:
        assert journal.pruefe_journal(s).in_ordnung
    engine.dispose()
