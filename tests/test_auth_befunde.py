"""Befunde der gegnerischen Prüfung (Baustein 10a) an Anmeldung und Sperre.

- A-H3/B-N4: Fehlversuche atomar „reserviert“ — unter Parallelität werden höchstens
  so viele Codes geprüft wie die Sperre erlaubt; die Sperre setzt den Zähler nicht
  zurück (Obergrenze in Folge), nach Ablauf sperrt nicht schon ein Fehlversuch.
- A-M1: gleiche Arbeit je Versuch, ob das Passwort stimmt oder nicht.
- A-M4: Fehlversuche anderer beenden keine offenen Sitzungen.
- A-N6: ein neuer zweiter Faktor beendet die Sitzungen.
"""

import threading
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from accounti.auth import passwort
from accounti.auth.dienst import (
    bestaetige_2fa,
    entsperre,
    oeffne_sitzung,
    pruefe_anmeldung,
    pruefe_sitzung,
    pruefe_zweiten_faktor,
    setze_aktiv,
)
from accounti.auth.fehler import AnmeldungError
from accounti.auth.totp import code, neues_geheimnis
from accounti.db import init_db, session_factory
from accounti.db.repo_auth import lade_benutzer
from accounti.models.auth import Rolle
from tests.auth_hilfe import (
    JETZT,
    PASSWORT,
    SCHLUESSEL,
    billige_hashes,
    einstellungen,
    lege_person_an,
    systemdatenbank,
)

E = einstellungen()


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def system(tmp_path):
    with systemdatenbank(tmp_path) as s:
        yield s


def anmelden(s, name, pw, einmalcode, jetzt=JETZT, e=E):
    return pruefe_anmeldung(s, name, pw, einmalcode, SCHLUESSEL, e, jetzt=jetzt)


def _parallel(url: str, versuche: list, e) -> list[str]:
    """Alle Versuche zugleich (je eigene Sitzung, wie Threads der Web-App)."""
    engine, fabrik = session_factory(url)
    start = threading.Barrier(len(versuche))
    ergebnis: list[str] = []

    def versuch(pw: str, einmalcode: str) -> None:
        start.wait()
        with fabrik() as s:
            try:
                pruefe_anmeldung(s, "eva", pw, einmalcode, SCHLUESSEL, e, jetzt=JETZT)
                ergebnis.append("ok")
            except AnmeldungError as f:
                ergebnis.append(f.grund)

    threads = [threading.Thread(target=versuch, args=v) for v in versuche]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    engine.dispose()
    return ergebnis


def _zaehle(url: str, sql: str) -> int:
    engine, _ = session_factory(url)
    with engine.connect() as v:
        wert = v.execute(text(sql)).scalar()
    engine.dispose()
    return int(wert or 0)


def test_sperre_wirkt_unter_parallelitaet(tmp_path, monkeypatch):
    """40 gleichzeitige Versuche mit richtigem Passwort und falschem Code: geprüft
    werden höchstens 5 Codes, der Rest scheitert an der Sperre."""
    langsam = passwort.Kosten(log_n=12, r=8, p=1)  # spürbar, wie ein Server
    monkeypatch.setattr(passwort, "KOSTEN", langsam)
    url = f"sqlite:///{tmp_path / 'sys.db'}"
    engine, fabrik = session_factory(url)
    init_db(engine)
    with fabrik() as s:
        p = lege_person_an(s, "eva", Rolle.FREIGEBER, jetzt=JETZT)
    engine.dispose()
    richtig = p.code(JETZT)
    falsch = [f"{(int(richtig) + i) % 1_000_000:06d}" for i in range(1, 41)]
    ergebnis = _parallel(url, [(PASSWORT, c) for c in falsch], E)
    assert len(ergebnis) == 40 and "ok" not in ergebnis
    geprueft = _zaehle(
        url, "SELECT count(*) FROM auth_ereignisse WHERE art='einmalcode_falsch'"
    )
    assert geprueft <= 5, f"{geprueft} Codes geprüft trotz Sperre nach 5"
    assert ergebnis.count("gesperrt") >= 35
    assert _zaehle(url, "SELECT fehlversuche FROM auth_benutzer") == 5


def test_sperre_setzt_den_zaehler_nicht_zurueck(system):
    """Fehlversuche in Folge sind begrenzt (NIST: höchstens 100) — danach gesperrt
    bis ``entsperren``; zwischen den Sperren gibt es je ein volles Fenster."""
    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    e = einstellungen(
        sperre_nach_fehlversuchen=3, sperre_minuten=15, fehlversuche_obergrenze=7
    )
    t = JETZT
    zeiten = []
    for _ in range(7):
        with pytest.raises(AnmeldungError):
            anmelden(system, "jan", "falsch falsch falsch", "000000", jetzt=t, e=e)
        b = lade_benutzer(system, "jan")
        zeiten.append((b.fehlversuche, b.gesperrt(t + timedelta(seconds=1))))
        if b.gesperrt(t + timedelta(seconds=1)):
            t += timedelta(minutes=16)  # Sperre abwarten
    # nach 3 und 6 Fehlversuchen gesperrt, dazwischen nicht schon nach einem
    assert zeiten == [
        (1, False),
        (2, False),
        (3, True),
        (4, False),
        (5, False),
        (6, True),
        (7, True),
    ]
    # nach der Obergrenze hilft Warten nicht mehr, auch nicht das richtige Passwort
    spaeter = t + timedelta(days=30)
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", PASSWORT, jan.code(spaeter), jetzt=spaeter, e=e)
    assert lade_benutzer(system, "jan").fehlversuche == 7
    entsperre(system, lade_benutzer(system, "jan"), spaeter, durch="chef")
    anmelden(system, "jan", PASSWORT, jan.code(spaeter), jetzt=spaeter, e=e)
    assert lade_benutzer(system, "jan").fehlversuche == 0


def test_nach_ablauf_sperrt_nicht_schon_ein_fehlversuch(system):
    lege_person_an(system, "jan", Rolle.BUCHHALTER)
    e = einstellungen(sperre_nach_fehlversuchen=5, sperre_minuten=15)
    for _ in range(5):
        with pytest.raises(AnmeldungError):
            anmelden(system, "jan", "falsch falsch falsch", "000000", e=e)
    assert lade_benutzer(system, "jan").gesperrt(JETZT)
    spaeter = JETZT + timedelta(minutes=16)
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", "falsch falsch falsch", "000000", jetzt=spaeter, e=e)
    assert not lade_benutzer(system, "jan").gesperrt(spaeter)


def test_zweiter_faktor_allein_unter_parallelitaet(tmp_path):
    """Dieselbe Reservierung für den Einmalcode einer Freigabe (CLI, Browser)."""
    url = f"sqlite:///{tmp_path / 'sys.db'}"
    engine, fabrik = session_factory(url)
    init_db(engine)
    with fabrik() as s:
        p = lege_person_an(s, "eva", Rolle.FREIGEBER, jetzt=JETZT)
    start = threading.Barrier(20)
    ergebnis = []
    richtig = int(p.code(JETZT))

    def versuch(i: int) -> None:
        start.wait()
        with fabrik() as s:
            b = lade_benutzer(s, "eva")
            falsch = f"{(richtig + i) % 1_000_000:06d}"
            try:
                pruefe_zweiten_faktor(s, b, falsch, SCHLUESSEL, E, JETZT, quelle="cli")
            except AnmeldungError as f:
                ergebnis.append(f.grund)

    threads = [threading.Thread(target=versuch, args=(i,)) for i in range(1, 21)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    engine.dispose()
    geprueft = _zaehle(
        url, "SELECT count(*) FROM auth_ereignisse WHERE art='einmalcode_falsch'"
    )
    assert geprueft <= 5 and ergebnis.count("gesperrt") >= 15


def test_gleiche_arbeit_ob_das_passwort_stimmt(system, monkeypatch):
    """Befund A-M1: ein wiederherstellungscode-förmiger Code kostet bei richtigem
    Passwort nicht zehn zusätzliche scrypt-Hashes."""
    lege_person_an(system, "eva", Rolle.FREIGEBER)
    e = einstellungen(sperre_nach_fehlversuchen=100)
    echt = passwort._scrypt
    zaehler = {"n": 0}

    def gezaehlt(*a, **kw):
        zaehler["n"] += 1
        return echt(*a, **kw)

    monkeypatch.setattr(passwort, "_scrypt", gezaehlt)
    kosten = {}
    for pw, einmalcode in [
        ("falsches Passwort 123", "AAAAA-AAAAA"),
        (PASSWORT, "AAAAA-AAAAA"),
        ("falsches Passwort 123", "123456"),
        (PASSWORT, "123456"),
        (PASSWORT, ""),
    ]:
        zaehler["n"] = 0
        with pytest.raises(AnmeldungError):
            anmelden(system, "eva", pw, einmalcode, e=e)
        kosten[(pw == PASSWORT, einmalcode)] = zaehler["n"]
    assert set(kosten.values()) == {1}, kosten
    zaehler["n"] = 0
    with pytest.raises(AnmeldungError):
        anmelden(system, "niemand", PASSWORT, "AAAAA-AAAAA", e=e)
    assert zaehler["n"] == 1


def test_wiederherstellungscodes_nur_mit_dem_schluessel(system):
    """Codes liegen als HMAC mit dem Tresor-Schlüssel (Pepper) — ein anderer
    Schlüssel macht sie wertlos, und kein Code steht im Klartext da."""
    from accounti.bank.tresor import neuer_schluessel

    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    gespeichert = " ".join(
        str(z)
        for z in system.execute(text("SELECT * FROM auth_wiederherstellungscodes"))
    )
    assert all(c.replace("-", "") not in gespeichert for c in jan.codes)
    from accounti.auth import wiederherstellung
    from accounti.db.repo_auth import offene_wiederherstellungscodes

    hashes = [
        c.code_hash for c in offene_wiederherstellungscodes(system, jan.benutzer.id)
    ]
    assert len(hashes) == 10
    mit = [
        wiederherstellung.passt(jan.codes[0], h, SCHLUESSEL, jan.benutzer.id)
        for h in hashes
    ]
    ohne = [
        wiederherstellung.passt(jan.codes[0], h, neuer_schluessel(), jan.benutzer.id)
        for h in hashes
    ]
    assert mit.count(True) == 1 and not any(ohne)
    assert anmelden(system, "jan", PASSWORT, jan.codes[0]).name == "jan"


def test_fehlversuche_anderer_beenden_keine_sitzung(system):
    """Befund A-M4: Wer den Namen kennt, sperrt neue Anmeldungen — die offene
    Sitzung des Opfers läuft weiter. Ein Verwalter, der sperrt, beendet sie."""
    jan = lege_person_an(system, "jan", Rolle.FREIGEBER)
    token, _ = oeffne_sitzung(system, jan.benutzer, "standard", E, JETZT)
    system.commit()
    e = einstellungen(sperre_nach_fehlversuchen=1)
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", "falsch falsch falsch", "000000", e=e)
    assert lade_benutzer(system, "jan").gesperrt(JETZT)
    assert pruefe_sitzung(system, token, e, JETZT) is not None
    setze_aktiv(system, lade_benutzer(system, "jan"), False, JETZT, durch="chef")
    assert pruefe_sitzung(system, token, e, JETZT) is None


def test_neuer_zweiter_faktor_beendet_die_sitzungen(system):
    """Befund A-N6: wer den Faktor ersetzt (Gerät verloren), wirft offene
    Sitzungen hinaus."""
    jan = lege_person_an(system, "jan", Rolle.BUCHHALTER)
    token, _ = oeffne_sitzung(system, jan.benutzer, "standard", E, JETZT)
    system.commit()
    geheimnis = neues_geheimnis()
    bestaetige_2fa(
        system,
        lade_benutzer(system, "jan"),
        geheimnis,
        code(geheimnis, JETZT.timestamp()),
        SCHLUESSEL,
        E,
        JETZT,
    )
    system.commit()
    assert pruefe_sitzung(system, token, E, JETZT) is None
    spaeter = JETZT + timedelta(seconds=60)
    assert anmelden(
        system, "jan", PASSWORT, code(geheimnis, spaeter.timestamp()), jetzt=spaeter
    )


def test_zeitpunkt_der_dauerhaften_sperre_ist_lesbar(system):
    lege_person_an(system, "jan", Rolle.BUCHHALTER)
    e = einstellungen(sperre_nach_fehlversuchen=1, fehlversuche_obergrenze=1)
    with pytest.raises(AnmeldungError):
        anmelden(system, "jan", "falsch falsch falsch", "000000", e=e)
    b = lade_benutzer(system, "jan")
    assert b.gesperrt(datetime(2999, 1, 1))
