import threading

from accounti.db import init_db, session_factory
from accounti.db.repository import naechste_nummer


def test_fortlaufend_je_kreis_und_jahr():
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    with make_session() as s:
        assert [naechste_nummer(s, "GM", 2026) for _ in range(3)] == [1, 2, 3]
        assert naechste_nummer(s, "GM", 2027) == 1
        assert naechste_nummer(s, "Tochter", 2026) == 1
        assert naechste_nummer(s, "GM", 2026) == 4
        s.commit()


def test_rollback_gibt_die_nummer_frei():
    engine, make_session = session_factory("sqlite:///:memory:")
    init_db(engine)
    with make_session() as s:
        assert naechste_nummer(s, "GM", 2026) == 1
        s.commit()
        assert naechste_nummer(s, "GM", 2026) == 2
        s.rollback()  # z.B. weil die Prüfung der Rechnung fehlschlug
        assert naechste_nummer(s, "GM", 2026) == 2


def test_lueckenlos_bei_parallelen_zugriffen(tmp_path):
    """Akzeptanz 6."""
    url = f"sqlite:///{(tmp_path / 'n.db').as_posix()}"
    engine, make_session = session_factory(url)
    init_db(engine)
    vergeben: list[int] = []
    sperre = threading.Lock()
    fehler: list[BaseException] = []

    def arbeiter():
        try:
            for _ in range(10):
                with make_session() as s:
                    nr = naechste_nummer(s, "GM", 2026)
                    s.commit()
                with sperre:
                    vergeben.append(nr)
        except BaseException as e:  # noqa: BLE001
            fehler.append(e)

    threads = [threading.Thread(target=arbeiter) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    engine.dispose()
    assert fehler == []
    assert sorted(vergeben) == list(range(1, 41))
