"""Nachprüfung der Web-Schicht 10b-1 nach dem Zusammenführen mit main (Prüfberichte
gw-web N1–N7, gw-storno N1–N2): Meldungen und Statuswerte übersetzt, nur ASCII-Ziffern,
Fehler im richtigen Formular, Sprachwahl nach einem POST, Fachfehler der Konfiguration
als 409, Doppelklick auf Stornieren ohne verbrauchten Code."""

from __future__ import annotations

import re
import threading
from contextlib import contextmanager
from datetime import date
from uuid import UUID

import pytest

from accounti.models import BuchungStatus
from tests.api_hilfe import csrf, formularwert, zaehle
from tests.auth_hilfe import billige_hashes
from tests.pruefen_hilfe import pdf, queuewelt, stand_aus

EN = {"Accept-Language": "en-GB,en;q=0.9"}
DE = {"Accept-Language": "de-DE,de;q=0.9"}
HX = {"HX-Request": "true"}


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def qw(tmp_path):
    return queuewelt(tmp_path)


def vorschlaege(qw, anzahl):  # noqa: ANN001, ANN201
    """``anzahl`` unsichere Buchungen aus einem Kontierungslauf, nach Datum."""
    for nr in range(anzahl):
        qw.umsatz(tag=date(2026, 10, 1 + nr), zweck=f"RE {4711 + nr} Büromaterial")
    return qw.kontiere()


def senden(client, pfad, kopf=None, ansicht=None, **felder):  # noqa: ANN001, ANN003, ANN201
    """Formular der Seite ``ansicht`` (Standard: Pfad ohne Aktion) absenden."""
    seite = client.get(ansicht or pfad.rsplit("/", 1)[0]).text
    daten = {"csrf": csrf(client), "ansicht": "offen"}
    if 'name="stand"' in seite:
        daten["stand"] = stand_aus(seite)
    daten.update({k: str(v) for k, v in felder.items()})
    return client.post(pfad, data=daten, headers=kopf or {}, follow_redirects=False)


def eingabe(html, ident):  # noqa: ANN001, ANN201
    """Das ``<input>``- bzw. ``<select>``-Element mit dieser id."""
    treffer = re.search(rf'<(?:input|select) id="{ident}"[^>]*>', html)
    assert treffer, f"Feld {ident} fehlt"
    return treffer.group(0)


# --- gw-web N1: Erfolgsmeldungen der Queue übersetzt ---------------------------------


def test_erfolgsmeldungen_der_queue_englisch_mit_und_ohne_htmx(qw):
    erste, zweite, dritte, vierte = vorschlaege(qw, 4)
    client = qw.web.angemeldet("jan")
    # ohne JavaScript: 303 auf den nächsten Eintrag, die Meldung über ?erledigt=
    r = senden(client, f"/pruefen/{erste.id}/freigeben", EN)
    assert r.status_code == 303
    seite = client.get(r.headers["location"], headers=EN).text
    assert "Booking approved." in seite and "Buchung freigegeben." not in seite
    # mit htmx: das Fragment des nächsten Eintrags trägt die Meldung
    r = senden(
        client,
        f"/pruefen/{zweite.id}/korrigieren",
        {**EN, **HX},
        soll="4930",
        haben="1200",
        steuer="9",
    )
    assert r.status_code == 200 and "<html" not in r.text
    assert "Booking corrected." in r.text and "Buchung korrigiert." not in r.text
    r = senden(client, f"/pruefen/{dritte.id}/zurueckstellen", {**EN, **HX}, text="?")
    assert "Booking put on hold" in r.text and "zurückgestellt —" not in r.text
    for pfad in (
        "/pruefen?erledigt=freigegeben",
        f"/pruefen/{vierte.id}?erledigt=korrigiert",
    ):
        seite = client.get(pfad, headers=EN).text
        assert "Booking approved." in seite or "Booking corrected." in seite, pfad
        assert 'class="fachmeldung" lang="de">Buchung' not in seite, pfad
    seite = client.get("/pruefen/regeln?erledigt=deaktiviert", headers=EN).text
    assert "Rule deactivated." in seite and "Regel deaktiviert." not in seite
    # Deutsch unverändert
    seite = client.get("/pruefen?erledigt=freigegeben", headers=DE).text
    assert "Buchung freigegeben." in seite


# --- gw-web N2: nur ASCII-Ziffern -----------------------------------------------------


@pytest.mark.parametrize("ziffer", ["²", "٣", "３"])
def test_seite_mit_unicode_ziffer_ist_seite_eins(qw, ziffer):
    vorschlaege(qw, 1)
    client = qw.web.angemeldet("leo")
    r = client.get(f"/pruefen?seite={ziffer}")
    assert r.status_code == 200 and 'aria-current="page"' in r.text


@pytest.mark.parametrize("steuer", ["²", "٩", "９"])
def test_steuer_mit_unicode_ziffer_422_auf_allen_wegen(qw, steuer):
    (b,) = vorschlaege(qw, 1)
    frei = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 10, 5))
    client = qw.web.angemeldet("jan")
    felder = {"soll": "4930", "haben": "1200", "steuer": steuer}
    for kopf in ({}, HX):
        r = senden(client, f"/pruefen/{b.id}/korrigieren", kopf, **felder)
        assert r.status_code == 422, (kopf, r.status_code)
        assert "Unbekannter Steuerschlüssel" in r.text
        r = senden(client, f"/pruefen/{b.id}/regelvorschau", kopf, regel="1", **felder)
        assert r.status_code == 422, (kopf, r.status_code)
    code = qw.web.personen["jan"].codes[-1]
    r = senden(client, f"/buchungen/{frei.id}/korrigieren", einmalcode=code, **felder)
    assert r.status_code == 422 and "Unbekannter Steuerschlüssel" in r.text
    assert 'aria-invalid="true"' in eingabe(r.text, "steuer")
    assert qw.sql("SELECT status FROM buchungssaetze WHERE id = :i", i=str(b.id)) == [
        ("pruefung",)
    ]
    # kein Code verbraucht, keine Buchung angelegt
    r = senden(client, f"/buchungen/{frei.id}/stornieren", einmalcode=code, grund="x")
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("konto", ["４９３０", "4９30", "²930"])
def test_konto_mit_unicode_ziffern_422(qw, konto):
    (b,) = vorschlaege(qw, 1)
    frei = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 10, 5))
    client = qw.web.angemeldet("jan")
    r = senden(
        client, f"/pruefen/{b.id}/korrigieren", soll=konto, haben="1200", steuer="9"
    )
    assert r.status_code == 422 and 'aria-invalid="true"' in eingabe(r.text, "soll")
    r = senden(
        client,
        f"/buchungen/{frei.id}/korrigieren",
        soll=konto,
        haben="1200",
        steuer="9",
        einmalcode=qw.web.personen["jan"].codes[-1],
    )
    assert r.status_code == 422 and 'aria-invalid="true"' in eingabe(r.text, "soll")
    konten = {z[0] for z in qw.sql("SELECT soll_konto FROM buchungssaetze")}
    assert konten <= {"4980"}


def test_ustva_zeitraum_mit_unicode_ziffern_422_ohne_code(qw):
    client = qw.web.angemeldet("fritz")
    daten = {
        "csrf": csrf(client),
        "zeitraum": "２０２６-09",
        "einmalcode": qw.web.personen["fritz"].codes[-1],
    }
    r = client.post("/freigaben/ustva", data=daten, headers=EN)
    assert r.status_code == 422 and "Period not understood" in r.text
    assert (
        zaehle(
            qw.web.umgebung.system,
            "SELECT count(*) FROM auth_wiederherstellungscodes "
            "WHERE verbraucht_am IS NOT NULL",
        )
        == 0
    )


def _anfrage_mit_laenge(laenge: str):  # noqa: ANN202
    """POST mit ``Content-Length: laenge`` und dem Körper ``a=1`` (ohne Server)."""
    from types import SimpleNamespace

    from starlette.requests import Request

    async def empfangen():  # noqa: ANN202
        return {"type": "http.request", "body": b"a=1", "more_body": False}

    app = SimpleNamespace(
        state=SimpleNamespace(
            dienste=SimpleNamespace(server=SimpleNamespace(max_formular_bytes=10))
        )
    )
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [
                (b"content-type", b"application/x-www-form-urlencoded"),
                (b"content-length", laenge.encode("latin-1")),
            ],
            "app": app,
        },
        empfangen,
    )


def test_formular_und_rest_koerper_mit_unicode_laenge():
    """„²“ als Content-Length: ``isdigit`` wahr, ``int`` scheiterte (500)."""
    import asyncio

    from accounti.api.formular import formular
    from accounti.api.rest.belege import _koerper

    assert asyncio.run(formular(_anfrage_mit_laenge("²"))) == {"a": "1"}
    assert asyncio.run(_koerper(_anfrage_mit_laenge("²"), 10)) == b"a=1"


# --- gw-web N3: Fehler im Storno-Formular --------------------------------------------


def test_storno_fehler_im_storno_formular(qw):
    b = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 10, 1))
    client = qw.web.angemeldet("jan")
    code = qw.web.personen["jan"].codes[-1]
    r = senden(
        client,
        f"/buchungen/{b.id}/stornieren",
        einmalcode=code,
        grund="falsch",
        datum="2026-09-01",
    )
    assert r.status_code == 422 and "läge vor der Buchung" in r.text
    assert 'aria-invalid="true"' in eingabe(r.text, "datum-s")
    assert 'value="2026-09-01"' in eingabe(r.text, "datum-s")
    assert 'value="falsch"' in eingabe(r.text, "grund-s")
    for feld in ("datum-k", "grund-k"):
        assert "aria-invalid" not in eingabe(r.text, feld), feld
        assert 'value=""' in eingabe(r.text, feld), feld
    r = senden(client, f"/buchungen/{b.id}/stornieren", einmalcode=code, grund=" ")
    assert r.status_code == 422
    assert 'aria-invalid="true"' in eingabe(r.text, "grund-s")
    assert "aria-invalid" not in eingabe(r.text, "grund-k")


def test_korrektur_fehler_bleibt_im_korrektur_formular(qw):
    b = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 10, 1))
    client = qw.web.angemeldet("jan")
    r = senden(
        client,
        f"/buchungen/{b.id}/korrigieren",
        einmalcode=qw.web.personen["jan"].codes[-1],
        soll="4930",
        haben="1200",
        steuer="9",
        grund="falsch",
        datum="2026-09-01",
    )
    assert r.status_code == 422
    assert 'aria-invalid="true"' in eingabe(r.text, "datum-k")
    assert 'value="falsch"' in eingabe(r.text, "grund-k")
    assert "aria-invalid" not in eingabe(r.text, "datum-s")
    assert 'value=""' in eingabe(r.text, "grund-s")


# --- gw-web N4: Sprachwahl nach einer POST-Antwort ----------------------------------


def _sprache_auf(client, html, sprache="en"):  # noqa: ANN001, ANN201
    weiter = formularwert(html, "weiter")
    r = client.post(
        "/einstellungen/sprache",
        data={"csrf": csrf(client), "sprache": sprache, "weiter": weiter},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return weiter, client.get(r.headers["location"])


def test_sprachwahl_nach_post_fuehrt_auf_eine_get_seite(qw):
    b, gelernt = vorschlaege(qw, 2)
    frei = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 10, 5))
    client = qw.web.angemeldet("jan")
    r = senden(
        client,
        f"/pruefen/{gelernt.id}/korrigieren",
        soll="4930",
        haben="1200",
        steuer="9",
        regel="1",
        muster="Bürobedarf Müller",
        feld="beide",
    )
    assert r.status_code == 303, r.text
    ((regel_id,),) = qw.sql("SELECT id FROM kontierungsregeln")
    regel_id = UUID(str(regel_id))
    faelle = [
        (
            senden(client, f"/pruefen/{b.id}/korrigieren", soll="12", haben="1200"),
            f"/pruefen/{b.id}",
        ),
        (
            senden(client, f"/pruefen/{b.id}/regelvorschau", soll="4930", haben="1200"),
            f"/pruefen/{b.id}",
        ),
        (
            senden(client, f"/buchungen/{frei.id}/stornieren", grund=" "),
            f"/buchungen/{frei.id}",
        ),
        (
            senden(
                client,
                f"/pruefen/regeln/{regel_id}/deaktivieren",
                ansicht="/pruefen/regeln",
                grund=" ",
            ),
            "/pruefen/regeln",
        ),
    ]
    for antwort, erwartet in faelle:
        assert antwort.status_code in (200, 422), antwort.status_code
        weiter, ziel = _sprache_auf(client, antwort.text)
        assert weiter == erwartet
        assert ziel.status_code == 200, (weiter, ziel.status_code)
    # Fehlerseite eines POST (403): zurück auf die nächste GET-Seite darüber
    leo = qw.web.angemeldet("leo")
    r = leo.post(
        f"/pruefen/{b.id}/freigeben",
        data={"csrf": csrf(leo), "stand": "x"},
        follow_redirects=False,
    )
    assert r.status_code == 403
    weiter, ziel = _sprache_auf(leo, r.text)
    assert weiter == f"/pruefen/{b.id}" and ziel.status_code == 200
    # GET-Seiten behalten ihren Pfad, fremde Ziele bleiben ausgeschlossen
    assert formularwert(client.get("/pruefen/regeln").text, "weiter") == (
        "/pruefen/regeln"
    )
    r = client.post(
        "/einstellungen/sprache",
        data={"csrf": csrf(client), "sprache": "", "weiter": "//evil.example/x"},
        follow_redirects=False,
    )
    assert r.headers["location"] == "/"


# --- gw-web N5: lesbare Statuswerte, „Strg“ -----------------------------------------


def test_jeder_statuswert_hat_eine_bezeichnung():
    from accounti.api.vorlagen import BEZEICHNUNGEN, bezeichnung
    from accounti.erechnung.modell import Profil
    from accounti.models import Belegart, BelegStatus
    from accounti.models.aufgaben import AufgabenStatus

    for art in (BuchungStatus, Belegart, BelegStatus, AufgabenStatus, Profil):
        assert set(BEZEICHNUNGEN[art.__name__]) == {w.value for w in art}, art
    assert bezeichnung(BuchungStatus.ZUR_PRUEFUNG, "de") == "zur Prüfung"
    assert bezeichnung(BuchungStatus.ZUR_PRUEFUNG, "en") == "under review"
    assert bezeichnung(BelegStatus.ZUR_PRUEFUNG, "en") == "under review"
    assert bezeichnung(Belegart.EINGANGSRECHNUNG, "en") == "Incoming invoice"
    assert bezeichnung(AufgabenStatus.IN_ARBEIT, "de") == "in Arbeit"
    assert bezeichnung(Profil.EN16931, "en") == "EN 16931"


def test_statuswerte_und_tasten_lesbar_in_beiden_sprachen(qw):
    from accounti.aufgaben import melde_aufgabe
    from accounti.models.aufgaben import Objekt

    beleg = qw.beleg(pdf())
    vorschlag = qw.buchung(beleg_id=beleg.id)
    frei = qw.buchung(
        status=BuchungStatus.GEPRUEFT, beleg_id=beleg.id, datum=date(2026, 10, 3)
    )
    ohne = qw.unsicher(betrag="-119.00", zweck="Strom", name="Stadtwerke")
    with qw.fabrik()() as s:
        melde_aufgabe(
            s,
            "beleg_fehlt",
            Objekt("transaktion", ohne.transaktion_id),
            "Beleg fehlt",
            erzeugt_von="pruefung",
        )
        s.commit()
    client = qw.web.angemeldet("jan")
    erwartet = {
        "de": (
            "Eingangsrechnung",
            "<dt>Status</dt><dd>erfasst",
            "(zur Prüfung)",
            "<dt>Status</dt><dd>geprüft",
            "· geprüft</li>",
            "Aufgabe #1, offen)",
            "<kbd>Strg</kbd>",
        ),
        "en": (
            "Incoming invoice",
            "<dt>Status</dt><dd>recorded",
            "(under review)",
            "<dt>Status</dt><dd>reviewed",
            "· reviewed</li>",
            "task #1, open)",
            "<kbd>Ctrl</kbd>",
        ),
    }
    for sprache, kopf in (("de", DE), ("en", EN)):
        texte = erwartet[sprache]
        seite = client.get(f"/belege/{beleg.id}", headers=kopf).text
        assert texte[0] in seite and texte[1] in seite and texte[2] in seite
        assert ">eingangsrechnung<" not in seite and "(pruefung)" not in seite
        seite = client.get(f"/buchungen/{frei.id}", headers=kopf).text
        assert texte[3] in seite and "<dd>geprueft" not in seite
        seite = client.get(f"/pruefen/{vorschlag.id}", headers=kopf).text
        assert texte[4] in seite and "· geprueft<" not in seite
        assert texte[6] in seite
        seite = client.get(f"/pruefen/{ohne.id}", headers=kopf).text
        assert texte[5] in seite and texte[6] in seite
    seite = client.get(f"/pruefen/{vorschlag.id}", headers=EN).text
    assert "Strg" not in seite


def test_profil_der_e_rechnung_lesbar(qw):
    from pathlib import Path

    beispiele = Path(__file__).resolve().parents[1] / "examples" / "erechnung"
    inhalt = (beispiele / "xrechnung_ubl.xml").read_bytes()
    b = qw.beleg(inhalt, ".xml")
    seite = qw.web.angemeldet("jan").get(f"/belege/{b.id}", headers=EN).text
    assert "· XRechnung</dd>" in seite and "· xrechnung<" not in seite


# --- gw-web N6: Text der Regelseite --------------------------------------------------


def test_regelseite_nennt_die_gegenbuchung_zur_pruefung(qw):
    client = qw.web.angemeldet("jan")
    seite = client.get("/pruefen/regeln", headers=DE).text
    assert "Gegenbuchung zur Prüfung" in seite and "nur in der Richtung" not in seite
    seite = client.get("/pruefen/regeln", headers=EN).text
    assert "counter-entry for review" in seite and "apply only in" not in seite


# --- gw-web N7: Texte von Starlette und Formular ------------------------------------


def test_starlette_und_formulartexte_uebersetzt(qw):
    (b,) = vorschlaege(qw, 1)
    client = qw.web.angemeldet("jan")
    r = client.get("/gibt-es-nicht", headers=DE)
    assert r.status_code == 404 and "Not Found" not in r.text
    assert "Seite nicht gefunden" in r.text
    r = client.get(f"/pruefen/{b.id}/korrigieren", headers=DE)
    assert r.status_code == 405 and "Method Not Allowed" not in r.text
    assert "(Methode nicht erlaubt)" in r.text
    assert "Page not found" in client.get("/gibt-es-nicht", headers=EN).text
    r = client.get(f"/pruefen/{b.id}/korrigieren", headers=EN)
    assert "(method not allowed)" in r.text
    gross = "x" * (qw.web.dienste.server.max_formular_bytes + 10)
    r = client.post(
        f"/pruefen/{b.id}/korrigieren", data={"csrf": csrf(client), "a": gross},
        headers=EN,
    )  # fmt: skip
    assert r.status_code == 413 and "Form too large" in r.text
    assert "Formular zu groß" not in r.text
    r = client.post(
        f"/pruefen/{b.id}/korrigieren",
        content=b"csrf=\xff\xfe",
        headers={**EN, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 400 and "Form cannot be read" in r.text
    # die REST-API meldet wie bisher
    assert client.get("/api/v1/gibt-es-nicht").json() == {"fehler": "Not Found"}


def test_formular_und_csrf_fehler_in_der_sprache_des_benutzers(qw):
    """Die Wahl am Benutzer gilt auch für Fehler, die vor der Seite entstehen
    (Formular zu groß, CSRF) — nicht nur ``Accept-Language``."""
    (b,) = vorschlaege(qw, 1)
    client = qw.web.angemeldet("jan")
    r = client.post(
        "/einstellungen/sprache",
        data={"csrf": csrf(client), "sprache": "en", "weiter": "/"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    gross = "x" * (qw.web.dienste.server.max_formular_bytes + 10)
    r = client.post(
        f"/pruefen/{b.id}/korrigieren",
        data={"csrf": csrf(client), "a": gross},
        headers=DE,
    )
    assert r.status_code == 413 and "Form too large" in r.text
    r = client.post(f"/pruefen/{b.id}/freigeben", data={"csrf": "x"}, headers=DE)
    assert r.status_code == 403 and "CSRF token missing or invalid" in r.text
    # auch ohne passende Route (404, 405)
    r = client.get("/gibt-es-nicht", headers=DE)
    assert r.status_code == 404 and "Page not found" in r.text
    r = client.get(f"/pruefen/{b.id}/korrigieren", headers=DE)
    assert r.status_code == 405 and "(method not allowed)" in r.text
    # ohne Sitzung: Accept-Language
    assert "Seite nicht gefunden" in qw.web.client().get("/x", headers=DE).text


# --- gw-storno N1: Fehler im Kontenrahmen der Gesellschaft --------------------------


def test_fehlerhafte_kontenzuordnung_409_statt_500(qw, tmp_path):
    (b,) = vorschlaege(qw, 1)
    frei = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 10, 5))
    cfg = qw.web.umgebung.config["a"]
    cfg.write_text(
        cfg.read_text(encoding="utf-8")
        + f"abschluss:\n  kontenzuordnung: '{tmp_path / 'fehlt.yaml'}'\n",
        encoding="utf-8",
    )
    client = qw.web.angemeldet("jan")
    code = qw.web.personen["jan"].codes[-1]
    for kopf in ({}, HX):
        r = senden(client, f"/pruefen/{b.id}/freigeben", kopf)
        assert r.status_code == 409, (kopf, r.status_code)
        assert 'role="alert"' in r.text and "fehlt.yaml" in r.text
    r = senden(client, f"/pruefen/{b.id}/korrigieren", soll="4930", haben="1200")
    assert r.status_code == 409
    r = senden(client, f"/buchungen/{frei.id}/stornieren", einmalcode=code, grund="x")
    assert r.status_code == 409 and "fehlt.yaml" in r.text
    assert len(qw.sql("SELECT id FROM buchungssaetze")) == 2
    assert zaehle(
        qw.web.umgebung.system,
        "SELECT count(*) FROM auth_wiederherstellungscodes "
        "WHERE verbraucht_am IS NOT NULL",
    ) == 0  # fmt: skip


# --- gw-storno N2: Doppelklick auf Stornieren/Korrigieren ---------------------------


@contextmanager
def nach_der_probe_beide(monkeypatch):  # noqa: ANN001, ANN201
    """Beide Anfragen erst weiter, wenn beide ihre Probe hinter sich haben (der erste
    ``im_namen``-Block jeder Anfrage ist die Probe, danach ist zurückgerollt)."""
    from accounti.api.seiten import buchungen

    echt = buchungen.im_namen
    schranke = threading.Barrier(2, timeout=20)
    zaehler = iter(range(1_000))
    sperre = threading.Lock()

    @contextmanager
    def im_namen(a):  # noqa: ANN001, ANN202
        with sperre:
            nr = next(zaehler)
        with echt(a) as person:
            yield person
        if nr < 2:
            schranke.wait()

    monkeypatch.setattr(buchungen, "im_namen", im_namen)
    yield


def zwei_gleichzeitig(client, pfad, daten_a, daten_b):  # noqa: ANN001, ANN201
    ergebnis: dict[str, object] = {}

    def los(name, daten):  # noqa: ANN001, ANN202
        ergebnis[name] = client.post(pfad, data=daten, follow_redirects=False)

    faeden = [
        threading.Thread(target=los, args=("a", daten_a)),
        threading.Thread(target=los, args=("b", daten_b)),
    ]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join(60)
    return ergebnis["a"], ergebnis["b"]


def _einmalcode_ereignisse(qw, art):  # noqa: ANN001, ANN201
    return zaehle(
        qw.web.umgebung.system,
        f"SELECT count(*) FROM auth_ereignisse WHERE art = '{art}'",
    )


@pytest.mark.parametrize("was", ["stornieren", "korrigieren"])
def test_doppelklick_mit_demselben_code_409_ohne_fehlversuch(qw, monkeypatch, was):
    b = qw.buchung(status=BuchungStatus.GEPRUEFT)
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/buchungen/{b.id}").text
    daten = {
        "csrf": csrf(client),
        "stand": formularwert(seite, "stand"),
        "einmalcode": qw.web.code("jan"),
        "grund": "doppelt",
        "soll": "4930",
        "haben": "1200",
        "steuer": "9",
    }
    with nach_der_probe_beide(monkeypatch):
        a, b2 = zwei_gleichzeitig(client, f"/buchungen/{b.id}/{was}", daten, daten)
    assert sorted((a.status_code, b2.status_code)) == [200, 409]
    zweite = a if a.status_code == 409 else b2
    assert "inzwischen geändert" in zweite.text
    assert _einmalcode_ereignisse(qw, "einmalcode_falsch") == 0
    assert zaehle(
        qw.web.umgebung.system,
        "SELECT fehlversuche FROM auth_benutzer WHERE name = 'jan'",
    ) == 0  # fmt: skip
    stornos = qw.sql("SELECT id FROM buchungssaetze WHERE storno_von IS NOT NULL")
    assert len(stornos) == 1


def test_doppelklick_verbraucht_keinen_zweiten_code(qw, monkeypatch):
    b = qw.buchung(status=BuchungStatus.GEPRUEFT)
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/buchungen/{b.id}").text
    daten = {"csrf": csrf(client), "stand": formularwert(seite, "stand"), "grund": "x"}
    totp = qw.web.code("jan")
    wiederherstellung = qw.web.personen["jan"].codes[-1]
    with nach_der_probe_beide(monkeypatch):
        a, b2 = zwei_gleichzeitig(
            client,
            f"/buchungen/{b.id}/stornieren",
            {**daten, "einmalcode": totp},
            {**daten, "einmalcode": wiederherstellung},
        )
    assert sorted((a.status_code, b2.status_code)) == [200, 409]
    ungenutzt = wiederherstellung if a.status_code == 200 else totp
    assert _einmalcode_ereignisse(qw, "einmalcode_falsch") == 0
    # der Code der abgewiesenen Anfrage gilt noch
    weitere = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 10, 2))
    r = senden(
        client, f"/buchungen/{weitere.id}/stornieren", einmalcode=ungenutzt, grund="y"
    )
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("was", ["freigeben", "korrigieren"])
def test_doppelklick_in_der_queue_409(qw, was):
    """Die Queue fragt keinen Einmalcode ab; ihre Fachfunktionen vergleichen den Stand
    unter der Schreibsperre — der zweite gleichzeitige POST bekommt 409."""
    (b,) = vorschlaege(qw, 1)
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    daten = {
        "csrf": csrf(client),
        "stand": stand_aus(seite),
        "soll": "4930",
        "haben": "1200",
        "steuer": "9",
    }
    a, b2 = zwei_gleichzeitig(client, f"/pruefen/{b.id}/{was}", daten, daten)
    assert sorted((a.status_code, b2.status_code)) == [303, 409]
    assert len(qw.sql("SELECT id FROM buchungssaetze")) == 1
    assert qw.sql("SELECT count(*) FROM buchungskorrekturen")[0][0] == 0
