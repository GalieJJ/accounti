"""Person aus der Sitzung (Spec 4.1 „echter Benutzer statt Zeichenkette“; Baustein
10b): Jeder schreibende Weg der Oberfläche trägt den angemeldeten Benutzer — nie
``ACCOUNTI_BENUTZER`` oder den Anmeldenamen des Server-Prozesses."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from accounti.api.app import erstelle_app
from accounti.db import session_factory
from accounti.models.auth import Rolle
from tests.api_hilfe import webwelt
from tests.auth_hilfe import billige_hashes
from tests.test_api_rechte_matrix import anfrage, bindung_setzen, fachdaten


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


SPALTEN = (
    "SELECT person FROM journal WHERE nr > :nr",
    "SELECT geprueft_von FROM buchungssaetze WHERE geprueft_von IS NOT NULL",
    "SELECT person FROM buchungskorrekturen",
    "SELECT angelegt_von FROM kontierungsregeln WHERE angelegt_von <> 't'",
    "SELECT deaktiviert_von FROM kontierungsregeln WHERE deaktiviert_von IS NOT NULL",
    "SELECT autor FROM aufgaben_kommentare",
    "SELECT erzeugt_von FROM aufgaben WHERE art = 'rueckfrage'",
)


def test_kein_web_eintrag_ohne_angemeldeten_benutzer(tmp_path, monkeypatch):
    from tests.gesellschaft_hilfe import zahlungslauf

    monkeypatch.setenv("ACCOUNTI_BENUTZER", "mallory")
    monkeypatch.setattr("getpass.getuser", lambda: "mallory")
    welt = webwelt(tmp_path)
    welt.person("jan", Rolle.BUCHHALTER)
    welt.rolle("jan", "a", Rolle.FREIGEBER)
    welt.rolle("jan", "a", Rolle.VERWALTER)
    for rolle in Rolle:  # die Matrix-Hilfe zieht Codes der Rolle
        welt.person(rolle.value, rolle)
    zahlungslauf(welt.umgebung, "a")
    welt.daten = fachdaten(welt, tmp_path)  # type: ignore[attr-defined]
    url = welt.umgebung.db["a"]
    bindung_setzen(url)  # gebunden: ungeprüfte Personen wären gekennzeichnet
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        start = s.execute(text("SELECT max(nr) FROM journal")).scalar() or 0
    client = welt.angemeldet("jan")
    welt.personen["buchhalter"] = welt.personen["jan"]  # Codes von jan
    posts = [
        e.pfad
        for e in erstelle_app(welt.dienste).state.endpunkte
        if e.methode == "POST"
        and not e.pfad.startswith(("/api/", "/anmelden"))
        and e.pfad not in ("/abmelden", "/gesellschaft")
    ]
    # Reihenfolge: erst Regelvorschau und Zurückstellen, dann Korrigieren/Freigeben
    reihenfolge = ["regelvorschau", "zurueckstellen", "korrigieren", "freigeben"]
    posts.sort(key=lambda p: next((i for i, w in enumerate(reihenfolge) if w in p), 9))
    for pfad in posts:
        r = anfrage(welt, client, Rolle.BUCHHALTER, "POST", pfad)
        # 308: der alte Sprachpfad leitet auf /konto/vorlieben (Plan P1, Schritt 9)
        assert r.status_code in (200, 303, 308, 409), (
            pfad,
            r.status_code,
            r.text[:300],
        )
    with fabrik() as s:
        werte: list[str] = []
        for abfrage in SPALTEN:
            werte += [str(w) for w in s.execute(text(abfrage), {"nr": start}).scalars()]
        vorgaenge = set(
            s.execute(
                text("SELECT vorgang FROM journal WHERE nr > :nr"), {"nr": start}
            ).scalars()
        )
    engine.dispose()
    assert werte, "nichts geschrieben"
    assert not [w for w in werte if "mallory" in w or "ungeprüft" in w], werte
    assert {w for w in werte if w != "eva"} <= {"jan"}, set(werte)
    # die schreibenden Wege haben tatsächlich geschrieben
    assert {"buchung_freigegeben", "storno_gebucht", "regel_deaktiviert"} <= vorgaenge
