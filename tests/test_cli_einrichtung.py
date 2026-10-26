"""Einrichtungsphase je Gesellschaft, der letzte Verwalter (Gesamttest Betrieb B7, B8).

- B7: Nach der Einrichtung der Installation bekam eine zweite oder später ergänzte
  Gesellschaft keinen Verwalter mehr — nur über SQL. Jetzt richtet ein Verwalter
  irgendeiner Gesellschaft (mit Einmalcode) eine Gesellschaft ein, die noch nie einen
  Verwalter mit zweitem Faktor hatte; das Protokoll hält es fest.
- B8: Legte sich der letzte Verwalter still oder nahm sich die Rolle, war die
  Einrichtungsphase wieder offen — jeder an der Shell legte ohne Code einen Verwalter
  an. Jetzt lehnt accounti das ab (fail-closed), und eine Gesellschaft, die einmal
  einen Verwalter mit zweitem Faktor hatte, öffnet ihre Einrichtungsphase nie wieder.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from typer.testing import CliRunner

from accounti.auth import totp
from accounti.cli import app
from accounti.db import init_db, session_factory
from accounti.db.repo_auth import lade_benutzer, lade_ereignisse, rollen_von
from accounti.models.auth import Rolle
from tests.auth_hilfe import billige_hashes, lege_person_an, setze_schluessel
from tests.gesellschaft_hilfe import zwei_gesellschaften

runner = CliRunner()
PW = "ein langer geheimer Satz"
GEHEIMNIS = b"neuneuneuneuneuneu42"


@pytest.fixture(autouse=True)
def _umgebung(monkeypatch, tmp_path):
    billige_hashes(monkeypatch)
    setze_schluessel(monkeypatch)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in (
        "ACCOUNTI_DB",
        "ACCOUNTI_ARCHIV",
        "ACCOUNTI_GESELLSCHAFT",
        "ACCOUNTI_EINMALCODE",
        "ACCOUNTI_SYSTEM_DB",
        "ACCOUNTI_BENUTZER",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(totp, "neues_geheimnis", lambda: GEHEIMNIS)


def run(*args, input=None):
    return runner.invoke(app, list(args), input=input, env={"COLUMNS": "250"})


class Welt:
    def __init__(self, url: str, monkeypatch, *eintraege) -> None:
        self.url = url
        self.monkeypatch = monkeypatch
        engine, fabrik = session_factory(url)
        init_db(engine)
        jetzt = datetime.now()
        with fabrik() as s:
            self.p = {
                name: lege_person_an(s, name, rolle, gesellschaft=g, jetzt=jetzt)
                for name, g, rolle in eintraege
            }
        engine.dispose()
        self.codes = {n: list(p.codes) for n, p in self.p.items()}

    def als(self, name: str, code: bool = True) -> None:
        self.monkeypatch.setenv("ACCOUNTI_BENUTZER", name)
        if code:
            self.monkeypatch.setenv("ACCOUNTI_EINMALCODE", self.codes[name].pop())
        else:
            self.monkeypatch.delenv("ACCOUNTI_EINMALCODE", raising=False)

    def lade(self, fn, *args):
        engine, fabrik = session_factory(self.url)
        with fabrik() as s:
            ergebnis = fn(s, *args)
        engine.dispose()
        return ergebnis

    def rollen(self, name: str) -> set[tuple[str, str]]:
        b = self.lade(lade_benutzer, name)
        return {(z.gesellschaft, z.rolle.value) for z in self.lade(rollen_von, b.id)}


@pytest.fixture
def zwei(tmp_path, monkeypatch):
    """Registry a, b; chef ist Verwalter (mit 2FA) nur in a, eva Buchhalterin in a."""
    u = zwei_gesellschaften(tmp_path)
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(u.registry))
    w = Welt(
        u.system,
        monkeypatch,
        ("chef", "a", Rolle.VERWALTER),
        ("eva", "a", Rolle.BUCHHALTER),
    )
    return u, w


def test_b7_verwalter_richtet_eine_gesellschaft_ohne_verwalter_ein(zwei):
    u, w = zwei
    w.als("chef")
    r = run("-g", "b", "benutzer", "rolle", "chef", "--rolle", "verwalter")
    assert r.exit_code == 0, r.output
    assert ("b", "verwalter") in w.rollen("chef")
    ereignisse = w.lade(lade_ereignisse)
    assert any(
        e.art == "einrichtung_gesellschaft" and e.gesellschaft == "b" and e.ok
        for e in ereignisse
    )


def test_b7_ersten_verwalter_in_b_anlegen_und_2fa_einrichten(zwei):
    u, w = zwei
    w.als("chef")
    r = run(
        "-g", "b", "benutzer", "anlegen", "bert", "--rolle", "verwalter",
        input=f"{PW}\n{PW}\n",
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    assert w.rollen("bert") == {("b", "verwalter")}
    w.als("chef")
    code = totp.code(GEHEIMNIS, datetime.now().timestamp())
    r = run("-g", "b", "benutzer", "2fa", "bert", input=f"{code}\n")
    assert r.exit_code == 0, r.output
    assert w.lade(lade_benutzer, "bert").totp_aktiv
    # b hat jetzt einen eigenen Verwalter mit zweitem Faktor: chef (nur a) darf dort
    # nichts mehr verwalten
    w.als("chef")
    r = run("-g", "b", "benutzer", "rolle", "chef", "--rolle", "verwalter")
    assert r.exit_code == 1, r.output
    assert "in der Gesellschaft b nicht" in r.output


def test_b7_nur_mit_einmalcode_und_nur_als_verwalter(zwei):
    u, w = zwei
    w.monkeypatch.setenv("ACCOUNTI_BENUTZER", "chef")
    w.monkeypatch.setenv("ACCOUNTI_EINMALCODE", "000000")
    r = run("-g", "b", "benutzer", "rolle", "chef", "--rolle", "verwalter")
    assert r.exit_code == 1, r.output
    w.als("eva")  # Buchhalterin in a — keine Verwalterin
    r = run("-g", "b", "benutzer", "rolle", "eva", "--rolle", "verwalter")
    assert r.exit_code == 1, r.output
    assert "eva darf" in r.output
    assert ("b", "verwalter") not in w.rollen("chef") | w.rollen("eva")


def test_b7_verwalter_von_a_uebernimmt_keine_konten_einer_dritten_gesellschaft(
    zwei,
):
    """Einrichten heißt nicht: Konten mit Rollen in einer anderen, eingerichteten
    Gesellschaft übernehmen (Zuständigkeit wie bisher)."""
    u, w = zwei
    engine, fabrik = session_factory(u.system)
    with fabrik() as s:
        lege_person_an(s, "tina", Rolle.VERWALTER, gesellschaft="c")
    engine.dispose()
    w.als("chef")
    r = run("-g", "b", "benutzer", "rolle", "tina", "--rolle", "verwalter")
    assert r.exit_code == 1, r.output
    assert "Verwalter in c" in r.output


@pytest.fixture
def einzeln(tmp_path, monkeypatch):
    """Ohne Registry: chef ist der einzige Verwalter (mit 2FA), eva Buchhalterin."""
    url = f"sqlite:///{tmp_path / 'a.db'}"
    w = Welt(
        url,
        monkeypatch,
        ("chef", "standard", Rolle.VERWALTER),
        ("eva", "standard", Rolle.BUCHHALTER),
    )
    return url, w


def _mallory_legt_verwalter_an(url: str):
    return run(
        "benutzer", "anlegen", "mallory", "--rolle", "verwalter", "--db", url,
        input=f"{PW}\n{PW}\n",
    )  # fmt: skip


@pytest.mark.parametrize(
    "befehl",
    [
        ["benutzer", "sperren", "chef"],
        ["benutzer", "rolle", "chef", "--rolle", "verwalter", "--entfernen"],
    ],
)
def test_b8_letzter_verwalter_nicht_still_oder_entrechtet(einzeln, befehl):
    url, w = einzeln
    w.als("chef")
    r = run(*befehl, "--db", url)
    assert r.exit_code == 1, r.output
    assert "letzte aktive Verwalter" in r.output
    chef = w.lade(lade_benutzer, "chef")
    assert chef.aktiv and ("standard", "verwalter") in w.rollen("chef")
    w.als("mallory", code=False)
    r = _mallory_legt_verwalter_an(url)
    assert r.exit_code == 1, r.output
    assert w.lade(lade_benutzer, "mallory") is None


def test_b8_mit_zweitem_verwalter_geht_es(einzeln):
    url, w = einzeln
    w.als("chef")
    r = run("benutzer", "rolle", "eva", "--rolle", "verwalter", "--db", url)
    assert r.exit_code == 0, r.output
    w.als("chef")
    r = run("benutzer", "sperren", "chef", "--db", url)
    assert r.exit_code == 0, r.output
    assert not w.lade(lade_benutzer, "chef").aktiv


def test_b8_einmal_eingerichtet_nie_wieder_frei(einzeln):
    """Auch wenn der letzte Verwalter an accounti vorbei wegfällt (Datenbank), öffnet
    sich die Einrichtungsphase nicht wieder."""
    from accounti.auth.dienst import setze_aktiv

    url, w = einzeln
    w.als("chef")
    assert run("benutzer", "liste", "--db", url).exit_code == 0  # eingerichtet
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        setze_aktiv(s, lade_benutzer(s, "chef"), False, None, "sql")
        s.commit()
    engine.dispose()
    w.als("mallory", code=False)
    r = _mallory_legt_verwalter_an(url)
    assert r.exit_code == 1, r.output
    assert w.lade(lade_benutzer, "mallory") is None


def test_b8_eingerichtete_gesellschaft_nicht_durch_fremden_verwalter(zwei):
    """Hatte b einmal einen Verwalter mit zweitem Faktor, richtet sie kein Verwalter
    einer anderen Gesellschaft neu ein — auch wenn ihr Verwalter wegfällt."""
    from accounti.auth.dienst import setze_aktiv

    u, w = zwei
    engine, fabrik = session_factory(u.system)
    with fabrik() as s:
        w.p["tina"] = lege_person_an(s, "tina", Rolle.VERWALTER, gesellschaft="b")
    engine.dispose()
    w.codes["tina"] = list(w.p["tina"].codes)
    w.als("tina")
    assert run("-g", "b", "benutzer", "liste").exit_code == 0  # b eingerichtet
    with fabrik() as s:
        setze_aktiv(s, lade_benutzer(s, "tina"), False, None, "sql")
        s.commit()
    engine.dispose()
    w.als("chef")
    r = run("-g", "b", "benutzer", "rolle", "chef", "--rolle", "verwalter")
    assert r.exit_code == 1, r.output
    assert ("b", "verwalter") not in w.rollen("chef")


def test_einrichtung_uebernimmt_keine_konten_der_gesellschaft(zwei):
    """Nachprüfung N2: Die Einrichtung von b bestimmt den ersten Verwalter — sie gibt
    chef (Verwalter nur in a) nicht Passwort, Codes und Rollen eines Benutzers, der in
    b schon arbeitet (tom, Freigeber in b): sonst handelte chef unter toms Namen."""
    u, w = zwei
    engine, fabrik = session_factory(u.system)
    with fabrik() as s:
        lege_person_an(s, "tom", Rolle.FREIGEBER, gesellschaft="b")
    engine.dispose()
    neu = "ein anderes langes Passwort"
    for befehl, eingabe in (
        (["benutzer", "passwort", "tom"], f"{neu}\n{neu}\n"),
        (["benutzer", "codes", "tom"], None),
        (["benutzer", "rolle", "tom", "--rolle", "verwalter"], None),
        (["benutzer", "sperren", "tom"], None),
    ):
        w.als("chef")
        r = run("-g", "b", *befehl, input=eingabe)
        assert r.exit_code == 1, (befehl, r.output)
        assert "Einrichtung" in r.output, (befehl, r.output)
    assert w.rollen("tom") == {("b", "freigeber")}
    assert w.lade(lade_benutzer, "tom").aktiv
    arten = {(e.art, e.benutzer) for e in w.lade(lade_ereignisse)}
    assert ("passwort_geaendert", "tom") not in arten
    assert ("wiederherstellungscodes_neu", "tom") not in arten
    # einen neuen Benutzer zum Verwalter machen geht weiter (test_b7_ersten_…)


def test_protokoll_nennt_wer_codes_erneuert(zwei):
    """Nachprüfung N2: ``wiederherstellungscodes_neu`` stand ohne „durch …“ im
    Protokoll, wenn ein Verwalter die Codes eines anderen erneuerte."""
    u, w = zwei
    w.als("chef")
    r = run("-g", "a", "benutzer", "codes", "eva")
    assert r.exit_code == 0, r.output
    eintraege = [
        (e.benutzer, e.hinweis)
        for e in w.lade(lade_ereignisse)
        if e.art == "wiederherstellungscodes_neu"
    ]
    assert ("eva", "durch chef") in eintraege, eintraege
