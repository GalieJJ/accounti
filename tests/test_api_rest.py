"""REST-API ``/api/v1`` (Integrationen & Export, Akzeptanzkriterium 7)."""

import base64
from datetime import date, datetime
from decimal import Decimal

import pytest

from accounti.db import session_factory
from accounti.db.repo_auth import widerrufe_api_token
from accounti.db.repository import lade_belege, speichere_buchung
from accounti.models import Buchungssatz, BuchungStatus
from accounti.models.auth import Rolle, TokenRecht
from tests.api_hilfe import Uhr, webwelt, zaehle
from tests.auth_hilfe import billige_hashes
from tests.pdf_hilfe import pdf_mit_text


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    return webwelt(tmp_path)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_akzeptanz_7_offene_posten_lesen(welt):
    token = welt.token("a", TokenRecht.OPOS_LESEN)
    r = welt.client().get("/api/v1/offene-posten", headers=bearer(token))
    assert r.status_code == 200, r.text
    daten = r.json()
    assert daten["anzahl"] == 1
    p = daten["offene_posten"][0]
    assert p["belegnummer"] == "A-RE-1"
    assert p["restbetrag"] == "111.00"  # Zeichenkette, nicht gerundet
    assert p["kontakt"] == {
        "id": p["kontakt"]["id"],
        "name": "Alpha Papier GmbH",
        "konto": "70001",
    }
    assert p["faellig_am"] == "2026-11-01"
    # Filter
    r = welt.client().get(
        "/api/v1/offene-posten",
        params={"richtung": "forderung"},
        headers=bearer(token),
    )
    assert r.json()["anzahl"] == 0
    r = welt.client().get(
        "/api/v1/offene-posten",
        params={"faellig_bis": "2026-10-31"},
        headers=bearer(token),
    )
    assert r.json()["anzahl"] == 0
    r = welt.client().get(
        "/api/v1/offene-posten", params={"richtung": "quer"}, headers=bearer(token)
    )
    assert r.status_code == 422


def test_akzeptanz_7_belege_einliefern(welt):
    token = welt.token("a", TokenRecht.BELEGE_SCHREIBEN)
    pdf = pdf_mit_text("Rechnung RE-77 Papier")
    r = welt.client().post(
        "/api/v1/belege",
        headers={
            **bearer(token),
            "Content-Type": "application/pdf",
            "X-Dateiname": "re-77.pdf",
        },
        content=pdf,
    )
    assert r.status_code == 200, r.text
    ergebnis = r.json()["ergebnisse"][0]
    assert ergebnis["ergebnis"] == "neu"
    assert ergebnis["dateiname"] == "re-77.pdf"
    # im Archiv und in der Datenbank der Gesellschaft des Tokens — nicht in B
    archiv = welt.umgebung.archiv["a"]
    assert any(p.read_bytes() == pdf for p in archiv.rglob("*.pdf"))
    assert not welt.umgebung.archiv["b"].exists()
    engine, fabrik = session_factory(welt.umgebung.db["a"])
    with fabrik() as s:
        neu = [b for b in lade_belege(s) if b.kanal == "api"]
    engine.dispose()
    assert len(neu) == 1 and neu[0].herkunft == "API-Token erp"
    # derselbe Beleg noch einmal: Dublette
    r = welt.client().post(
        "/api/v1/belege",
        headers={**bearer(token), "Content-Type": "application/pdf"},
        content=pdf,
    )
    assert r.json()["ergebnisse"][0]["ergebnis"] == "dublette"


def test_belege_als_json_und_multipart(welt):
    token = welt.token("a", TokenRecht.BELEGE_SCHREIBEN)
    client = welt.client()
    r = client.post(
        "/api/v1/belege",
        headers=bearer(token),
        json={
            "absender": "erp",
            "dateien": [
                {
                    "dateiname": "a.pdf",
                    "inhalt_base64": base64.b64encode(pdf_mit_text("A")).decode(),
                }
            ],
        },
    )
    assert r.status_code == 200, r.text
    r = client.post(
        "/api/v1/belege",
        headers=bearer(token),
        files={"datei": ("b.pdf", pdf_mit_text("B"), "application/pdf")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ergebnisse"][0]["dateiname"] == "b.pdf"


def test_falscher_typ_wird_vor_dem_speichern_abgewiesen(welt):
    token = welt.token("a", TokenRecht.BELEGE_SCHREIBEN)
    r = welt.client().post(
        "/api/v1/belege",
        headers={**bearer(token), "X-Dateiname": "boese.exe"},
        content=b"MZ\x90\x00 kein Beleg",
    )
    assert r.status_code == 415
    assert "nichts gespeichert" in r.json()["fehler"]
    assert not welt.umgebung.archiv["a"].exists()
    assert (
        zaehle(welt.umgebung.db["a"], "SELECT COUNT(*) FROM belege WHERE kanal='api'")
        == 0
    )


def test_akzeptanz_7_token_ohne_recht_wird_abgewiesen(welt):
    nur_lesen = welt.token("a", TokenRecht.OPOS_LESEN)
    r = welt.client().post(
        "/api/v1/belege",
        headers={**bearer(nur_lesen), "Content-Type": "application/pdf"},
        content=pdf_mit_text("x"),
    )
    assert r.status_code == 403
    assert 'error="insufficient_scope"' in r.headers["www-authenticate"]
    assert 'scope="belege:schreiben"' in r.headers["www-authenticate"]
    assert not welt.umgebung.archiv["a"].exists()
    nur_belege = welt.token("a", TokenRecht.BELEGE_SCHREIBEN, name="beleg")
    r = welt.client().get("/api/v1/offene-posten", headers=bearer(nur_belege))
    assert r.status_code == 403


def test_ohne_oder_mit_falschem_token(welt):
    client = welt.client()
    r = client.get("/api/v1/offene-posten")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == 'Bearer realm="accounti"'
    r = client.get("/api/v1/offene-posten", headers=bearer("accounti_api_falsch"))
    assert r.status_code == 401
    assert 'error="invalid_token"' in r.headers["www-authenticate"]
    r = client.get("/api/v1/offene-posten", headers={"Authorization": "Basic abc"})
    assert r.status_code == 401


def test_widerrufen_und_abgelaufen(tmp_path):
    uhr = Uhr(datetime(2026, 10, 20, 9, 0))
    welt = webwelt(tmp_path, uhr=uhr)
    token = welt.token("a", TokenRecht.OPOS_LESEN)
    client = welt.client()
    assert client.get("/api/v1/ich", headers=bearer(token)).status_code == 200
    with welt.system() as s:
        widerrufe_api_token(s, "erp", uhr())
        s.commit()
    assert client.get("/api/v1/ich", headers=bearer(token)).status_code == 401
    from accounti.auth.token import lege_api_token_an

    with welt.system() as s:
        kurz = lege_api_token_an(
            s,
            "kurz",
            "a",
            [TokenRecht.OPOS_LESEN],
            "t",
            gueltig_bis=date(2026, 10, 20),
            jetzt=uhr(),
        )
        s.commit()
    assert client.get("/api/v1/ich", headers=bearer(kurz)).status_code == 200
    uhr.weiter(24 * 3600)
    assert client.get("/api/v1/ich", headers=bearer(kurz)).status_code == 401


def test_ich(welt):
    token = welt.token("b", TokenRecht.OPOS_LESEN, TokenRecht.BUCHUNGEN_LESEN)
    r = welt.client().get("/api/v1/ich", headers=bearer(token))
    assert r.json() == {
        "token": "erp",
        "gesellschaft": "b",
        "rechte": ["buchungen:lesen", "opos:lesen"],
        "gueltig_bis": None,
    }


def test_buchungen_abfragen(welt):
    engine, fabrik = session_factory(welt.umgebung.db["a"])
    with fabrik() as s:
        for tag, status in (
            (date(2026, 9, 3), BuchungStatus.GEPRUEFT),
            (date(2026, 10, 1), BuchungStatus.ZUR_PRUEFUNG),
        ):
            speichere_buchung(
                s,
                Buchungssatz(
                    datum=tag,
                    soll_konto="4930",
                    haben_konto="1200",
                    betrag_netto=Decimal("10.00"),
                    buchungstext="Papier",
                    status=status,
                ),
            )
        s.commit()
    engine.dispose()
    token = welt.token("a", TokenRecht.BUCHUNGEN_LESEN)
    client = welt.client()
    alle = client.get("/api/v1/buchungen", headers=bearer(token)).json()
    assert alle["anzahl"] == 2
    assert alle["buchungen"][0]["betrag_netto"] == "10.00"
    sept = client.get(
        "/api/v1/buchungen",
        params={"von": "2026-09-01", "bis": "2026-09-30"},
        headers=bearer(token),
    ).json()
    assert [b["datum"] for b in sept["buchungen"]] == ["2026-09-03"]
    pruefung = client.get(
        "/api/v1/buchungen", params={"status": "pruefung"}, headers=bearer(token)
    ).json()
    assert [b["status"] for b in pruefung["buchungen"]] == ["pruefung"]
    assert (
        client.get(
            "/api/v1/buchungen", params={"status": "x"}, headers=bearer(token)
        ).status_code
        == 422
    )


def test_laeufe_anstossen(welt):
    token = welt.token("a", TokenRecht.LAEUFE_STARTEN)
    client = welt.client()
    r = client.post("/api/v1/laeufe/bank", headers=bearer(token))
    assert r.status_code == 200, r.text
    assert r.json()["lauf"] == "bank"
    assert set(r.json()["kontierung"]) == {
        "kontiert",
        "mit_beleg",
        "offen",
        "marktplatz",
    }
    r = client.post("/api/v1/laeufe/aufgaben", headers=bearer(token))
    assert r.status_code == 200, r.text
    assert r.json()["lauf"] == "aufgaben"


def test_lauf_nicht_doppelt(welt):
    from accounti.betrieb.laufsperre import laufsperre

    token = welt.token("a", TokenRecht.LAEUFE_STARTEN)
    with laufsperre(welt.umgebung.db["a"], "bank"):
        r = welt.client().post("/api/v1/laeufe/bank", headers=bearer(token))
    assert r.status_code == 409
    # über Prozesse: tests/test_betrieb_laufsperre.py


def test_benutzer_mit_sitzung_braucht_trotzdem_ein_token(welt):
    welt.person("jan", Rolle.BUCHHALTER)
    client = welt.angemeldet("jan")
    assert client.get("/api/v1/offene-posten").status_code == 401


def test_im_journal_steht_das_token(welt):
    """Verzahnung mit Baustein 7: was ein API-Token anstößt, steht im Journal unter
    dem Token — nicht unter dem Betriebssystem-Benutzer des Servers."""
    from sqlalchemy import text

    def personen(ab: int = 0) -> list[tuple[int, str]]:
        engine, fabrik = session_factory(welt.umgebung.db["a"])
        with fabrik() as s:
            zeilen = s.execute(
                text(
                    "SELECT nr, person FROM journal "
                    "WHERE vorgang = 'beleg_importiert' AND nr > :ab"
                ),
                {"ab": ab},
            ).all()
        engine.dispose()
        return [(nr, person) for nr, person in zeilen]

    # gebunden wie nach der ersten Rechteprüfung — sonst kennzeichnete das Journal
    # gar nicht, und „geprüft“ des Tokens bliebe ungetestet (Abschlussprüfung U4)
    from tests.test_api_rechte_matrix import bindung_setzen

    bindung_setzen(welt.umgebung.db["a"])
    bisher = max((nr for nr, _ in personen()), default=0)
    token = welt.token("a", TokenRecht.BELEGE_SCHREIBEN)
    r = welt.client().post(
        "/api/v1/belege",
        headers={**bearer(token), "Content-Type": "application/pdf"},
        content=pdf_mit_text("Rechnung RE-78 Papier"),
    )
    assert r.status_code == 200, r.text
    assert {person for _, person in personen(bisher)} == {"API-Token erp"}


def test_lauf_ueber_rest_steht_unter_dem_token_im_journal(welt, monkeypatch):
    """Schlussprüfung T-N5: auch ``/laeufe/…`` setzt die Person des Journals."""
    from sqlalchemy import text

    from accounti.api.rest import laeufe
    from accounti.pruefung.journal import schreibe

    def lauf(zugang, s):  # type: ignore[no-untyped-def]
        schreibe(s, "export", "export", "probe", nachher={"anzahl": 0})
        s.commit()
        return {"lauf": "bank"}

    monkeypatch.setattr(laeufe, "_bank", lauf)
    from tests.test_api_rechte_matrix import bindung_setzen

    bindung_setzen(welt.umgebung.db["a"])
    token = welt.token("a", TokenRecht.LAEUFE_STARTEN)
    r = welt.client().post("/api/v1/laeufe/bank", headers=bearer(token))
    assert r.status_code == 200, r.text
    engine, fabrik = session_factory(welt.umgebung.db["a"])
    with fabrik() as s:
        person = s.execute(
            text("SELECT person FROM journal WHERE objekt_id = 'probe'")
        ).scalar()
    engine.dispose()
    assert person == "API-Token erp"
