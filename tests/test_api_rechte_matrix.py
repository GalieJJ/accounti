"""Berechtigungen als Matrix: jede Rolle gegen jeden Endpunkt (Spec 6, Akzeptanz 3).

Jeder Endpunkt der App muss hier stehen — ein neuer Endpunkt ohne Eintrag lässt
``test_jeder_endpunkt_steht_in_der_matrix`` scheitern.
"""

import pytest
from sqlalchemy import text

from accounti.api.app import erstelle_app
from accounti.db import session_factory
from accounti.models.auth import Recht, Rolle, TokenRecht, rechte_der_rollen
from tests.api_hilfe import csrf, freigabe_hash, webwelt
from tests.auth_hilfe import billige_hashes
from tests.gesellschaft_hilfe import zahlungslauf
from tests.pdf_hilfe import pdf_mit_text

OFFEN = "offen"  # ohne Anmeldung
ANGEMELDET = "angemeldet"  # jede Rolle

# Seiten: (Methode, Pfad) → nötiges Recht
SEITEN: dict[tuple[str, str], object] = {
    ("GET", "/anmelden"): OFFEN,
    ("POST", "/anmelden"): OFFEN,
    ("POST", "/abmelden"): ANGEMELDET,
    ("POST", "/gesellschaft"): ANGEMELDET,
    ("GET", "/"): Recht.LESEN,
    ("GET", "/freigaben"): Recht.LESEN,
    ("POST", "/freigaben/zahlungslauf/{nr}"): Recht.ZAHLUNG_FREIGEBEN,
    ("POST", "/freigaben/ustva"): Recht.STEUER_FREIGEBEN,
}
# REST: (Methode, Pfad) → nötiges Token-Recht (None: jedes gültige Token)
REST: dict[tuple[str, str], TokenRecht | None] = {
    ("GET", "/api/v1/ich"): None,
    ("GET", "/api/v1/offene-posten"): TokenRecht.OPOS_LESEN,
    ("GET", "/api/v1/buchungen"): TokenRecht.BUCHUNGEN_LESEN,
    ("POST", "/api/v1/belege"): TokenRecht.BELEGE_SCHREIBEN,
    ("POST", "/api/v1/laeufe/bank"): TokenRecht.LAEUFE_STARTEN,
    ("POST", "/api/v1/laeufe/aufgaben"): TokenRecht.LAEUFE_STARTEN,
}
FREIGABEN = {Recht.BUCHUNG_FREIGEBEN, Recht.ZAHLUNG_FREIGEBEN, Recht.STEUER_FREIGEBEN}


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def welt(tmp_path):
    w = webwelt(tmp_path)
    for rolle in Rolle:
        w.person(rolle.value, rolle)
    zahlungslauf(w.umgebung, "a")
    return w


def laufstatus(welt) -> str:
    engine, fabrik = session_factory(welt.umgebung.db["a"])
    with fabrik() as s:
        status = s.execute(
            text("SELECT status FROM zahlungslaeufe WHERE nr = 1")
        ).scalar()
    engine.dispose()
    return str(status)


def test_jeder_endpunkt_steht_in_der_matrix(welt):
    app = erstelle_app(welt.dienste)
    vorhanden = {(e.methode, e.pfad) for e in app.state.endpunkte}
    vorhanden.discard(("GET", "/gesund"))
    assert vorhanden == set(SEITEN) | set(REST)


def anfrage(welt, client, rolle, methode, pfad):
    """Anfrage mit gültigem CSRF-Token und frischem Wiederherstellungscode."""
    person = welt.personen[rolle.value]
    daten = {"csrf": csrf(client), "einmalcode": person.codes.pop()}
    if pfad == "/freigaben/zahlungslauf/{nr}":
        inhalt = freigabe_hash(client, 1)
        if inhalt is not None:  # nur wer freigeben darf, sieht das Formular
            daten["freigabe_hash"] = inhalt
    if pfad == "/freigaben/ustva":
        daten["zeitraum"] = "2026-09"
    if pfad == "/gesellschaft":
        daten["kuerzel"] = "a"
    pfad = pfad.replace("{nr}", "1")
    if methode == "GET":
        return client.get(pfad, follow_redirects=False)
    return client.post(pfad, data=daten, follow_redirects=False)


@pytest.mark.parametrize("rolle", list(Rolle))
def test_jede_rolle_gegen_jeden_endpunkt(welt, rolle):
    client = welt.angemeldet(rolle.value)
    rechte = rechte_der_rollen([rolle])
    for (methode, pfad), recht in sorted(
        SEITEN.items(), key=lambda x: x[0][1] == "/abmelden"
    ):
        if recht == OFFEN:
            continue
        r = anfrage(welt, client, rolle, methode, pfad)
        erlaubt = recht == ANGEMELDET or recht in rechte
        if erlaubt:
            assert r.status_code not in (401, 403), (rolle, pfad, r.status_code, r.text)
        else:
            assert r.status_code == 403, (rolle, pfad, r.status_code)


def test_akzeptanz_3_betrachter_nichts_buchhalter_kein_zahlungslauf(welt):
    betrachter = welt.angemeldet("betrachter")
    for (methode, pfad), recht in SEITEN.items():
        if recht in FREIGABEN:
            r = anfrage(welt, betrachter, Rolle.BETRACHTER, methode, pfad)
            assert r.status_code == 403, pfad
    buchhalter = welt.angemeldet("buchhalter")
    r = anfrage(
        welt, buchhalter, Rolle.BUCHHALTER, "POST", "/freigaben/zahlungslauf/{nr}"
    )
    assert r.status_code == 403
    assert laufstatus(welt) == "entwurf"
    # ohne Einmalcode auch der Freigeber nicht
    freigeber = welt.angemeldet("freigeber")
    r = freigeber.post(
        "/freigaben/zahlungslauf/1",
        data={
            "csrf": csrf(freigeber),
            "einmalcode": "000000",
            "freigabe_hash": freigabe_hash(freigeber, 1),
        },
    )
    assert r.status_code == 403 and "Einmalcode" in r.text
    assert laufstatus(welt) == "entwurf"
    r = anfrage(
        welt, freigeber, Rolle.FREIGEBER, "POST", "/freigaben/zahlungslauf/{nr}"
    )
    assert r.status_code == 200, r.text
    assert "freigegeben von freigeber" in r.text
    assert laufstatus(welt) == "freigegeben"


def test_vier_augen_im_browser(welt):
    pfad = welt.umgebung.config["a"]
    pfad.write_text(
        pfad.read_text(encoding="utf-8").replace(
            "zahlung:\n", "zahlung:\n  vier_augen: true\n"
        ),
        encoding="utf-8",
    )
    welt.person("zweite", Rolle.FREIGEBER)
    erster = welt.angemeldet("freigeber")
    r = anfrage(welt, erster, Rolle.FREIGEBER, "POST", "/freigaben/zahlungslauf/{nr}")
    assert "zweite Person" in r.text and laufstatus(welt) == "entwurf"
    r = anfrage(welt, erster, Rolle.FREIGEBER, "POST", "/freigaben/zahlungslauf/{nr}")
    assert r.status_code == 409 and laufstatus(welt) == "entwurf"
    zweiter = welt.angemeldet("zweite")
    daten = {
        "csrf": csrf(zweiter),
        "einmalcode": welt.personen["zweite"].codes.pop(),
        "freigabe_hash": freigabe_hash(zweiter, 1),
    }
    r = zweiter.post("/freigaben/zahlungslauf/1", data=daten)
    assert r.status_code == 200 and laufstatus(welt) == "freigegeben"


def rest_anfrage(client, methode, pfad, token):
    kopf = {"Authorization": f"Bearer {token}"}
    if methode == "GET":
        return client.get(pfad, headers=kopf)
    if pfad.endswith("/belege"):
        kopf["X-Dateiname"] = "rechnung.pdf"
        kopf["Content-Type"] = "application/pdf"
        return client.post(pfad, headers=kopf, content=pdf_mit_text("Rechnung 1"))
    return client.post(pfad, headers=kopf)


@pytest.mark.parametrize("recht", list(TokenRecht))
def test_jedes_token_recht_gegen_jeden_rest_endpunkt(welt, recht):
    client = welt.client()
    token = welt.token("a", recht, name=f"t-{recht.name.lower()}")
    for (methode, pfad), noetig in REST.items():
        r = rest_anfrage(client, methode, pfad, token)
        if noetig is None or noetig == recht:
            assert r.status_code == 200, (recht, pfad, r.status_code, r.text)
        else:
            assert r.status_code == 403, (recht, pfad, r.status_code)
            assert 'error="insufficient_scope"' in r.headers["www-authenticate"]


def test_sitzung_oeffnet_die_rest_api_nicht(welt):
    client = welt.angemeldet("verwalter")
    for methode, pfad in REST:
        r = client.request(methode, pfad)
        assert r.status_code == 401, pfad


def test_ustva_freigabe_im_browser(tmp_path):
    from datetime import datetime

    from accounti.api.dienste import Dienste, einzelne_gesellschaft
    from accounti.db.repo_elster import lade_freigaben
    from accounti.models.elster import Meldeart
    from tests import test_cli_ustva as ustva
    from tests.api_hilfe import Uhr, Webwelt
    from tests.auth_hilfe import SCHLUESSEL

    url, konfig = ustva.umgebung(tmp_path)
    uhr = Uhr(datetime(2026, 10, 20, 9, 0))
    g = einzelne_gesellschaft(url, str(tmp_path / "archiv"), konfig)
    dienste = Dienste(url, {g.kuerzel: g}, schluessel=lambda: SCHLUESSEL, uhr=uhr)
    welt = Webwelt(None, dienste, uhr)
    welt.person("chef", Rolle.FREIGEBER, gesellschaft="standard")
    welt.person("eva", Rolle.BUCHHALTER, gesellschaft="standard")
    eva = welt.angemeldet("eva")
    r = eva.post("/freigaben/ustva", data={"csrf": csrf(eva), "zeitraum": "2026-08"})
    assert r.status_code == 403
    chef = welt.angemeldet("chef")
    r = chef.post(
        "/freigaben/ustva",
        data={
            "csrf": csrf(chef),
            "zeitraum": "2026-08",
            "einmalcode": welt.code("chef"),
        },
    )
    assert r.status_code == 200, r.text
    assert "freigegeben von chef" in r.text and "2.145,18" in r.text
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        freigaben = lade_freigaben(s, Meldeart.USTVA, "2026-08")
    engine.dispose()
    assert [f.freigegeben_von for f in freigaben] == ["chef"]


def test_freigabe_gilt_nur_fuer_den_angezeigten_inhalt(welt):
    """Befund B-M11: Die Seite zeigt Empfänger, IBAN und Betrag und schickt den
    Freigabe-Hash mit; ändert sich der Entwurf bis zum Klick, gibt es 409."""
    freigeber = welt.angemeldet("freigeber")
    seite = freigeber.get("/freigaben").text
    assert "Alpha Papier GmbH" in seite and "DE89 3704 0044 0532 0130 00" in seite
    assert "A-RE-1" in seite and "111,00" in seite
    gesehen = freigabe_hash(freigeber, 1)
    assert gesehen is not None
    engine, fabrik = session_factory(welt.umgebung.db["a"])
    with fabrik() as s:  # jemand ändert den Entwurf zwischen Anzeige und Klick
        s.execute(text("UPDATE zahlungen SET verwendungszweck = 'RE A-RE-1 NEU'"))
        s.commit()
    engine.dispose()
    person = welt.personen["freigeber"]
    for inhalt in (gesehen, None):
        daten = {"csrf": csrf(freigeber), "einmalcode": person.codes.pop()}
        if inhalt:
            daten["freigabe_hash"] = inhalt
        r = freigeber.post("/freigaben/zahlungslauf/1", data=daten)
        assert r.status_code == 409, r.text
        assert "geändert" in r.text
        assert laufstatus(welt) == "entwurf"
    neu = freigabe_hash(freigeber, 1)
    assert neu != gesehen
    assert "RE A-RE-1 NEU" in freigeber.get("/freigaben").text
    daten = {
        "csrf": csrf(freigeber),
        "einmalcode": person.codes.pop(),
        "freigabe_hash": neu,
    }
    r = freigeber.post("/freigaben/zahlungslauf/1", data=daten)
    assert r.status_code == 200, r.text
    assert laufstatus(welt) == "freigegeben"


def test_wer_den_lauf_anlegt_gibt_ihn_im_browser_nicht_frei(welt):
    """Befund B-M10: Ersteller ≠ Freigeber (``zahlung.ersteller_darf_freigeben``)."""
    welt.person("eva", Rolle.FREIGEBER)  # eva hat den Lauf angelegt
    eva = welt.angemeldet("eva")
    daten = {
        "csrf": csrf(eva),
        "einmalcode": welt.personen["eva"].codes.pop(),
        "freigabe_hash": freigabe_hash(eva, 1),
    }
    r = eva.post("/freigaben/zahlungslauf/1", data=daten)
    assert r.status_code == 409, r.text
    assert "angelegt" in r.text and laufstatus(welt) == "entwurf"


def test_ersteller_darf_freigeben_im_browser_mit_der_serverkonfiguration(welt):
    """Ein-Personen-Betrieb: ``zahlung.ersteller_darf_freigeben: true`` in der
    Konfiguration der Gesellschaft (die ``accounti serve`` kennt) gilt im Browser."""
    pfad = welt.umgebung.config["a"]
    pfad.write_text(
        pfad.read_text(encoding="utf-8").replace(
            "zahlung:\n", "zahlung:\n  ersteller_darf_freigeben: true\n"
        ),
        encoding="utf-8",
    )
    welt.person("eva", Rolle.FREIGEBER)  # eva hat den Lauf angelegt
    eva = welt.angemeldet("eva")
    daten = {
        "csrf": csrf(eva),
        "einmalcode": welt.personen["eva"].codes.pop(),
        "freigabe_hash": freigabe_hash(eva, 1),
    }
    r = eva.post("/freigaben/zahlungslauf/1", data=daten)
    assert r.status_code == 200, r.text
    assert laufstatus(welt) == "freigegeben"


def bindung_setzen(url: str) -> None:
    """Gesellschafts-Datenbank an die Benutzerverwaltung gebunden (Merker), wie nach
    der ersten Rechteprüfung — ab dann kennzeichnet das Journal ungeprüfte Personen."""
    from datetime import datetime

    from accounti.db.repo_auth import setze_merker_einmal

    engine, fabrik = session_factory(url)
    with fabrik() as s:
        setze_merker_einmal(
            s,
            "benutzerverwaltung",
            '{"gesellschaft": "a", "system": "x"}',
            datetime.now(),
        )
        s.commit()
    engine.dispose()


def test_freigabe_im_browser_steht_geprueft_im_journal(welt):
    """Abschlussprüfung M-A: Der angemeldete Freigeber (mit frischem Einmalcode) steht
    ohne „(ungeprüft)“ im Journal — auch in einer gebundenen Datenbank."""
    url = welt.umgebung.db["a"]
    bindung_setzen(url)
    freigeber = welt.angemeldet("freigeber")
    r = anfrage(
        welt, freigeber, Rolle.FREIGEBER, "POST", "/freigaben/zahlungslauf/{nr}"
    )
    assert r.status_code == 200, r.text
    engine, fabrik = session_factory(url)
    with fabrik() as s:
        personen = set(
            s.execute(
                text("SELECT person FROM journal WHERE vorgang LIKE 'zahlungslauf_%'")
            ).scalars()
        )
    engine.dispose()
    assert "freigeber" in personen and not any("ungeprüft" in p for p in personen)
