"""Supervisions-Queue im Browser (Spec 4.2; Baustein 10b, Paket 3)."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from accounti.db.repo_kontierung import speichere_kontierungsgrund
from accounti.models import BuchungStatus
from tests.api_hilfe import csrf
from tests.auth_hilfe import billige_hashes
from tests.pruefen_hilfe import LLM_BEGRUENDUNG, pdf, queuewelt, stand_aus

HX = {"HX-Request": "true"}


@pytest.fixture(autouse=True)
def _billig(monkeypatch):
    billige_hashes(monkeypatch)


@pytest.fixture
def qw(tmp_path):
    return queuewelt(tmp_path)


def status_von(qw, buchung_id, kuerzel="a"):  # noqa: ANN001, ANN201
    (zeile,) = qw.sql(
        "SELECT status, soll_konto, steuer_schluessel, geprueft_von FROM "
        "buchungssaetze WHERE id = :i",
        kuerzel,
        i=str(buchung_id),
    )
    return tuple(zeile)


def anzahl_buchungen(qw, kuerzel="a"):  # noqa: ANN001, ANN201
    return qw.sql("SELECT count(*) FROM buchungssaetze", kuerzel)[0][0]


def aktion(client, buchung_id, was, kopf=None, **felder):  # noqa: ANN001, ANN003, ANN201
    seite = client.get(f"/pruefen/{buchung_id}").text
    daten = {"csrf": csrf(client), "stand": stand_aus(seite), "ansicht": "offen"}
    daten.update({k: str(v) for k, v in felder.items()})
    return client.post(
        f"/pruefen/{buchung_id}/{was}",
        data=daten,
        headers=kopf or {},
        follow_redirects=False,
    )


# --- Liste und Arbeitsfläche ----------------------------------------------------------


def test_liste_mit_confidence_und_begruendung(qw):
    b = qw.unsicher()
    client = qw.web.angemeldet("jan")
    seite = client.get("/pruefen").text
    assert "Bürobedarf Müller GmbH" in seite and "59,50" in seite
    assert "62 %" in seite and LLM_BEGRUENDUNG in seite
    assert "4980 an 1200" in seite and f"/pruefen/{b.id}?ansicht=offen" in seite
    assert "KI-Vorschlag (LLM)" in seite


def test_arbeitsflaeche_beleg_links_vorschlag_rechts(qw):
    beleg = qw.beleg(pdf())
    b = qw.buchung(beleg_id=beleg.id)
    seite = qw.web.angemeldet("jan").get(f"/pruefen/{b.id}").text
    links = seite.index('class="links"')
    rechts = seite.index('class="rechts"')
    iframe = seite.index(f'<iframe class="beleg" src="/belege/{beleg.id}/datei"')
    vorschlag = seite.index("<h2>Vorschlag</h2>")
    assert links < iframe < rechts < vorschlag


def test_umsatzdaten_auch_mit_beleg(qw):
    """Nachbesserung M5: Der Mustervorschlag einer Regel stammt aus dem Umsatz —
    Gegenpartei, IBAN und Verwendungszweck stehen deshalb auch dann auf der
    Arbeitsfläche, wenn links der Beleg steht."""
    beleg = qw.beleg(pdf())
    tx = qw.umsatz(
        zweck="EMPFAENGERMARKER RE 4711", gegenkonto_iban="DE89370400440532013000"
    )
    b = qw.buchung(beleg_id=beleg.id, transaktion_id=tx.id)
    seite = qw.web.angemeldet("jan").get(f"/pruefen/{b.id}").text
    rechts = seite[seite.index('class="rechts"') :]
    assert "<h2>Umsatz</h2>" in rechts and "EMPFAENGERMARKER RE 4711" in rechts
    assert "Bürobedarf Müller GmbH" in rechts and "DE89 3704 0044" in rechts
    assert rechts.index("<h2>Umsatz</h2>") < rechts.index("<h2>Vorschlag</h2>")


def test_korrektur_verlaesst_das_finanzkonto_422(qw):
    """Nachbesserung M1: 4930 an 4980 für einen Umsatz auf 1200 wird abgelehnt
    (Feld Haben markiert), die Buchung bleibt in der Prüfung."""
    b = qw.unsicher()
    client = qw.web.angemeldet("jan")
    r = aktion(client, b.id, "korrigieren", HX, soll="4930", haben="4980", steuer="9")
    assert r.status_code == 422
    assert "Finanzkonto 1200" in r.text and 'id="haben"' in r.text
    assert re.search(r'id="haben"[^>]*aria-invalid="true"', r.text)
    assert status_von(qw, b.id)[:2] == ("pruefung", "4980")


def test_konto_mit_bezeichnung_und_schluessel_mit_bedeutung(qw):
    bekannt = qw.buchung(soll="4930", haben="1200")
    unbekannt = qw.buchung(soll="4987", haben="1200")
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{bekannt.id}").text
    assert re.search(
        r'konto-nr">4930</span> <span class="konto-name" lang="de">\w', seite
    )
    assert "(VSt 19 %)" in seite
    seite = client.get(f"/pruefen/{unbekannt.id}").text
    assert '<span class="konto-nr">4987</span></span>' in seite


def test_ohne_begruendung_hinweis(qw):
    b = qw.buchung()
    client = qw.web.angemeldet("jan")
    assert "Keine Begründung gespeichert" in client.get(f"/pruefen/{b.id}").text
    assert "Keine Begründung gespeichert" in client.get("/pruefen").text


def test_herkunft_afa_ohne_umsatz_und_beleg(qw):
    from accounti.anlagen.konfiguration import lade_anlagen
    from accounti.anlagen.lauf import afa_lauf
    from tests.abschluss_hilfe import anlegen

    anlegen(qw.fabrik(), 3600, date(2026, 9, 15), nd=3)
    with qw.fabrik()() as s:
        (b,) = afa_lauf(s, 2026, lade_anlagen(qw.tmp / "x.yaml")).buchungen
        s.commit()
    seite = qw.web.angemeldet("jan").get(f"/pruefen/{b.id}").text
    assert "Interne Buchung" in seite and "belegfrei: interne Buchung" in seite
    assert "linear" in seite and "Anlagen" in seite


def test_ohne_beleg_zeigt_nachforderung_oder_belegfrei(qw):
    from accounti.aufgaben import melde_aufgabe
    from accounti.models.aufgaben import Objekt

    cfg = qw.web.umgebung.config["a"]
    cfg.write_text(
        cfg.read_text(encoding="utf-8")
        + "pruefung:\n  belegfrei:\n    - {name: kontofuehrung, muster: "
        '"kontoführung", feld: verwendungszweck, begruendung: "Bankentgelt"}\n',
        encoding="utf-8",
    )
    frei = qw.unsicher(betrag="-4.90", zweck="Kontoführung 09/2026", name="Bank")
    fehlt = qw.unsicher(betrag="-119.00", zweck="Strom", name="Stadtwerke")
    with qw.fabrik()() as s:
        melde_aufgabe(
            s,
            "beleg_fehlt",
            Objekt("transaktion", fehlt.transaktion_id),
            "Beleg fehlt",
            erzeugt_von="pruefung",
            zustaendig="fritz",
            faellig_am=date(2026, 10, 30),
        )
        s.commit()
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{frei.id}").text
    assert "Belegfrei nach Regel kontofuehrung:" in seite and "Bankentgelt" in seite
    seite = client.get(f"/pruefen/{fehlt.id}").text
    assert "Beleg nachgefordert" in seite and "zuständig: fritz" in seite
    assert "30.10.2026" in seite and "accounti nachfordern anfrage" in seite


def test_aufgaben_der_buchung_mit_zustaendigkeit(qw):
    from accounti.aufgaben import melde_aufgabe
    from accounti.models.aufgaben import Objekt

    b = qw.buchung()
    with qw.fabrik()() as s:
        melde_aufgabe(
            s,
            "kontierung_pruefen",
            Objekt("buchung", b.id),
            "Kontierung prüfen: Bürobedarf",
            erzeugt_von="aufgaben",
            rolle="buchhaltung",
            faellig_am=date(2026, 10, 15),
        )
        s.commit()
    seite = qw.web.angemeldet("jan").get(f"/pruefen/{b.id}").text
    assert "Kontierung prüfen: Bürobedarf" in seite
    assert "zuständig: buchhaltung" in seite and "15.10.2026" in seite


def test_gesperrter_vorschlag_ohne_aktionen(qw):
    b = qw.buchung(datum=date(2025, 12, 30))
    qw.sql(
        "INSERT INTO abschluesse VALUES "
        "(2025, 1, 'euer', 0, '2026-03-01 10:00:00.000000', 'chef')"
    )
    seite = qw.web.angemeldet("jan").get(f"/pruefen/{b.id}").text
    assert "Geschäftsjahr 2025 ist abgeschlossen" in seite
    assert f'action="/pruefen/{b.id}/freigeben"' not in seite
    assert f'action="/pruefen/{b.id}/korrigieren"' not in seite


def test_kein_regelangebot_fuer_kreditkarte_anlagen_marktplatz(qw):
    angebote = {}
    for quelle in (
        "llm",
        "regelwerk",
        "standard",
        "kreditkarte",
        "anlagen",
        "marktplatz",
        "opos",
    ):
        tx = qw.umsatz()
        b = qw.buchung(transaktion_id=tx.id)
        with qw.fabrik()() as s:
            speichere_kontierungsgrund(s, b.id, quelle=quelle, begruendung="x")
            s.commit()
        seite = qw.web.angemeldet("jan").get(f"/pruefen/{b.id}").text
        angebote[quelle] = 'name="regel"' in seite
    assert {q for q, ja in angebote.items() if ja} == {"llm", "regelwerk", "standard"}


def test_position_und_vor_zurueck(qw):
    erste = qw.unsicher(tag=date(2026, 10, 1))
    zweite = qw.unsicher(tag=date(2026, 10, 2), name="Papier Paul")
    dritte = qw.unsicher(tag=date(2026, 10, 3), name="Toner Tom")
    seite = qw.web.angemeldet("jan").get(f"/pruefen/{zweite.id}").text
    assert "2 von 3" in seite
    assert f'href="/pruefen/{erste.id}?ansicht=offen"' in seite
    assert f'href="/pruefen/{dritte.id}?ansicht=offen"' in seite


def test_liste_seitenweise(qw, monkeypatch):
    from accounti.buchung import pruefschlange

    monkeypatch.setattr(pruefschlange, "JE_SEITE", 2)
    for tag in (1, 2, 3):
        qw.buchung(datum=date(2026, 10, tag))
    client = qw.web.angemeldet("jan")
    seite = client.get("/pruefen").text
    assert (
        "3 Buchungen" in seite and 'href="/pruefen?ansicht=offen&amp;seite=2"' in seite
    )
    assert seite.count("/pruefen/") >= 2
    zwei = client.get("/pruefen?seite=2").text
    assert "03.10.2026" in zwei and "01.10.2026" not in zwei


def test_betrachter_sieht_keine_formulare(qw):
    b = qw.unsicher()
    seite = qw.web.angemeldet("leo").get(f"/pruefen/{b.id}").text
    assert "Vorschlag" in seite
    for was in ("freigeben", "korrigieren", "zurueckstellen"):
        assert f"/pruefen/{b.id}/{was}" not in seite
    seite = qw.web.angemeldet("fritz").get(f"/pruefen/{b.id}").text
    assert f"/pruefen/{b.id}/freigeben" in seite
    assert f"/pruefen/{b.id}/korrigieren" not in seite
    assert f"/pruefen/{b.id}/zurueckstellen" in seite


def test_fremde_gesellschaft_404(qw):
    b_von_b = qw.buchung(kuerzel="b", soll="6815", haben="1800")
    client = qw.web.angemeldet("jan")  # aktiv: a
    assert client.get(f"/pruefen/{b_von_b.id}").status_code == 404
    r = client.post(
        f"/pruefen/{b_von_b.id}/freigeben",
        data={"csrf": csrf(client), "stand": "x"},
    )
    assert r.status_code == 404
    assert status_von(qw, b_von_b.id, "b")[0] == "pruefung"


def test_nur_volle_uuid(qw):
    b = qw.buchung()
    client = qw.web.angemeldet("jan")
    assert client.get(f"/pruefen/{str(b.id)[:8]}").status_code == 404
    assert client.get(f"/pruefen/{str(b.id)[:35]}%25").status_code == 404
    assert client.get(f"/pruefen/{uuid4()}").status_code == 404


def test_tastenbelegung_im_markup(qw):
    erste = qw.unsicher(tag=date(2026, 10, 1))
    zweite = qw.unsicher(tag=date(2026, 10, 2), name="Papier Paul")
    beleg = qw.beleg(pdf())
    qw.buchung(beleg_id=beleg.id, datum=date(2026, 10, 3))
    seite = qw.web.angemeldet("jan").get(f"/pruefen/{zweite.id}").text
    tasten = set(re.findall(r'data-taste="([^"]+)"', seite))
    assert tasten == {"j", "k", "f", "e", "r", "z"}
    assert 'id="tastenhilfe"' in seite and 'id="tasten-aus"' in seite
    dritte = qw.web.angemeldet("jan").get("/pruefen").text
    assert 'data-taste="j"' in dritte
    del erste


def test_korrigieren_ist_der_standardknopf(qw):
    """Enter in einem Feld löst den ersten Absendeknopf aus (HTML-Standard) — das muss
    „Korrigieren“ sein, nie die Regelvorschau (Browserprobe 10b)."""
    b = qw.unsicher()
    seite = qw.web.angemeldet("jan").get(f"/pruefen/{b.id}").text
    formular = re.search(r'<form[^>]*class="korrektur".*?</form>', seite, re.S)
    assert formular is not None
    knoepfe = re.findall(r'<button type="submit"[^>]*>', formular.group(0))
    assert len(knoepfe) == 2, knoepfe
    assert 'class="hauptknopf"' in knoepfe[0] and "formaction" not in knoepfe[0]
    neben = knoepfe[1]
    assert f'formaction="/pruefen/{b.id}/regelvorschau"' in neben
    # eigenes hx-disabled-elt: das geerbte „find button“ des Formulars fände unter dem
    # Knopf nichts (htmx meldet dann einen Fehler in der Konsole)
    assert 'hx-disabled-elt="this"' in neben


# --- Aktionen -------------------------------------------------------------------------


def test_freigeben_und_weiter(qw):
    erste = qw.unsicher(tag=date(2026, 10, 1))
    zweite = qw.unsicher(tag=date(2026, 10, 2), name="Papier Paul")
    client = qw.web.angemeldet("fritz")
    r = aktion(client, erste.id, "freigeben")
    assert r.status_code == 303
    assert (
        r.headers["location"]
        == f"/pruefen/{zweite.id}?ansicht=offen&erledigt=freigegeben"
    )
    assert status_von(qw, erste.id)[0] == "geprueft"
    assert status_von(qw, erste.id)[3] == "fritz"
    seite = client.get(r.headers["location"]).text
    assert "Buchung freigegeben." in seite


def test_korrigieren_vorschlag_direkt(qw):
    b = qw.unsicher()
    r = aktion(
        qw.web.angemeldet("jan"),
        b.id,
        "korrigieren",
        soll="4930",
        haben="1200",
        steuer="9",
    )
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/pruefen?ansicht=offen&erledigt=korrigiert"
    assert status_von(qw, b.id) == ("korrigiert", "4930", 9, "jan")
    assert anzahl_buchungen(qw) == 1  # kein Storno


def test_korrigieren_braucht_buchen(qw):
    b = qw.unsicher()
    for wer in ("fritz", "vera", "leo"):
        client = qw.web.angemeldet(wer)
        r = client.post(
            f"/pruefen/{b.id}/korrigieren",
            data={"csrf": csrf(client), "soll": "4930", "haben": "1200", "steuer": "9"},
        )
        assert r.status_code == 403, wer
    assert status_von(qw, b.id)[0] == "pruefung"


def test_steuerauswahl_aus_steuer_optionen(qw):
    beleg = qw.beleg(pdf())
    belegbuchung = qw.buchung(beleg_id=beleg.id)
    ust = qw.buchung(
        beleg_id=beleg.id, soll="1200", haben="8400", steuer_schluessel=3,
        datum=date(2026, 10, 2),
    )  # fmt: skip
    bank = qw.buchung(datum=date(2026, 10, 3))
    client = qw.web.angemeldet("jan")

    def optionen(b):  # noqa: ANN001, ANN202
        seite = client.get(f"/pruefen/{b.id}").text
        auswahl = re.search(r'<select id="steuer".*?</select>', seite, re.S).group(0)
        return re.findall(r'<option value="([^"]*)"', auswahl)

    assert optionen(belegbuchung) == ["", "9", "ohne"]
    assert optionen(ust) == ["", "3"]  # § 14c: nicht „ohne Steuer“
    assert set(optionen(bank)) >= {"", "2", "3", "8", "9", "19", "94", "ohne"}


def test_sachkontowechsel_verlangt_steuerangabe_422(qw):
    b = qw.unsicher()
    client = qw.web.angemeldet("jan")
    r = aktion(client, b.id, "korrigieren", soll="4360", haben="1200")
    assert r.status_code == 422
    assert "Das Sachkonto ändert sich (4980 → 4360)" in r.text
    assert "--steuer" not in r.text and "--ohne-steuer" not in r.text
    auswahl = re.search(r'<select id="steuer"[^>]*>', r.text).group(0)
    assert 'aria-invalid="true"' in auswahl and "required" in auswahl
    assert ">unverändert" not in r.text
    assert 'value="4360"' in r.text  # Eingabe vorbelegt
    assert status_von(qw, b.id)[:2] == ("pruefung", "4980")
    r = aktion(client, b.id, "korrigieren", soll="4360", haben="1200", steuer="ohne")
    assert r.status_code == 303
    assert status_von(qw, b.id)[:3] == ("korrigiert", "4360", None)


def test_automatikkonto_ohne_schluessel_422(qw):
    b = qw.buchung(steuer_schluessel=None, steuer_betrag=None)
    r = aktion(qw.web.angemeldet("jan"), b.id, "korrigieren", soll="3400", haben="1200")
    assert r.status_code == 422 and "Automatikkonto" in r.text
    assert "--steuer" not in r.text


def test_ohne_steuer_bei_beleg_verlangt_grund(qw):
    beleg = qw.beleg(pdf())
    b = qw.buchung(beleg_id=beleg.id)
    client = qw.web.angemeldet("jan")
    r = aktion(client, b.id, "korrigieren", soll="4980", haben="1200", steuer="ohne")
    assert r.status_code == 422 and "Grund" in r.text
    assert re.search(r'id="grund"[^>]*aria-invalid="true"', r.text)
    r = aktion(
        client, b.id, "korrigieren", soll="4980", haben="1200", steuer="ohne",
        grund="kein Vorsteuerabzug",
    )  # fmt: skip
    assert r.status_code == 303
    assert status_von(qw, b.id)[2] is None


def test_zurueckstellen_als_freigeber(qw):
    b = qw.unsicher()
    r = aktion(
        qw.web.angemeldet("fritz"), b.id, "zurueckstellen", text="Wofür war das?"
    )
    assert r.status_code == 303
    (person,) = qw.sql("SELECT autor FROM aufgaben_kommentare")[0]
    assert person == "fritz"
    for wer in ("leo", "vera"):
        client = qw.web.angemeldet(wer)
        r = client.post(
            f"/pruefen/{b.id}/zurueckstellen",
            data={"csrf": csrf(client), "text": "?"},
        )
        assert r.status_code == 403, wer


def test_veralteter_stand_409(qw):
    b = qw.unsicher()
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    alt = stand_aus(seite)
    qw.sql("UPDATE buchungssaetze SET buchungstext = 'geändert'")
    r = client.post(
        f"/pruefen/{b.id}/freigeben",
        data={"csrf": csrf(client), "stand": alt},
        follow_redirects=False,
    )
    assert r.status_code == 409 and "inzwischen geändert" in r.text
    assert stand_aus(r.text) != alt
    assert status_von(qw, b.id)[0] == "pruefung"


def test_doppelt_absenden_storniert_nicht(qw):
    b = qw.unsicher()
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    daten = {
        "csrf": csrf(client),
        "stand": stand_aus(seite),
        "soll": "4930",
        "haben": "1200",
        "steuer": "9",
    }
    erst = client.post(
        f"/pruefen/{b.id}/korrigieren", data=daten, follow_redirects=False
    )
    zweit = client.post(
        f"/pruefen/{b.id}/korrigieren", data=daten, follow_redirects=False
    )
    assert erst.status_code == 303 and zweit.status_code == 409
    assert anzahl_buchungen(qw) == 1
    assert qw.sql("SELECT count(*) FROM buchungskorrekturen")[0][0] == 0


def test_zurueckstellen_zweimal_409(qw):
    b = qw.unsicher()
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    daten = {"csrf": csrf(client), "stand": stand_aus(seite), "text": "Wofür?"}
    assert (
        client.post(
            f"/pruefen/{b.id}/zurueckstellen", data=daten, follow_redirects=False
        ).status_code
        == 303
    )
    r = client.post(
        f"/pruefen/{b.id}/zurueckstellen", data=daten, follow_redirects=False
    )
    assert r.status_code == 409 and "schon zurückgestellt" in r.text


@pytest.mark.parametrize("status", [BuchungStatus.GEPRUEFT, BuchungStatus.AUTO_GEBUCHT])
def test_queue_route_storniert_nie(qw, status):
    b = qw.buchung(status=status)
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    assert "nicht mehr in der Prüfung" in seite
    with qw.fabrik()() as s:
        from accounti.buchung.pruefschlange import stand

        aktuell = stand(s, b.id)
    for was, felder in (
        ("korrigieren", {"soll": "4930", "haben": "1200", "steuer": "9"}),
        ("freigeben", {}),
    ):
        r = client.post(
            f"/pruefen/{b.id}/{was}",
            data={"csrf": csrf(client), "stand": aktuell, **felder},
            follow_redirects=False,
        )
        assert r.status_code == 409, was
    assert anzahl_buchungen(qw) == 1
    assert status_von(qw, b.id)[0] == status.value


def test_zurueckstellen_und_ansicht_zurueckgestellt(qw):
    erste = qw.unsicher(tag=date(2026, 10, 1))
    zweite = qw.unsicher(tag=date(2026, 10, 2), name="Papier Paul")
    client = qw.web.angemeldet("jan")
    r = aktion(client, erste.id, "zurueckstellen", text="Wofür war das?", an="fritz")
    assert (
        r.headers["location"]
        == f"/pruefen/{zweite.id}?ansicht=offen&erledigt=zurueckgestellt"
    )
    offen = client.get("/pruefen").text
    assert "Zurückgestellt (1)" in offen and f"/pruefen/{erste.id}" not in offen
    zurueck = client.get("/pruefen?ansicht=zurueckgestellt").text
    assert f"/pruefen/{erste.id}?ansicht=zurueckgestellt" in zurueck
    seite = client.get(f"/pruefen/{erste.id}?ansicht=zurueckgestellt").text
    assert "Wofür war das?" in seite and "eine Rückfrage ist offen" in seite


def test_htmx_fragment_mit_push_url(qw):
    erste = qw.unsicher(tag=date(2026, 10, 1))
    zweite = qw.unsicher(tag=date(2026, 10, 2), name="Papier Paul")
    client = qw.web.angemeldet("jan")
    r = aktion(client, erste.id, "freigeben", kopf=HX)
    assert r.status_code == 200
    assert r.headers["hx-push-url"] == f"/pruefen/{zweite.id}?ansicht=offen"
    assert "<html" not in r.text and "Buchung freigegeben." in r.text
    assert f"/pruefen/{zweite.id}/freigeben" in r.text
    # GET mit HX-Request: Fragment; Verlaufsabruf: ganze Seite
    teil = client.get(f"/pruefen/{zweite.id}", headers=HX).text
    assert "<html" not in teil and 'class="flaeche"' in teil
    ganz = client.get(
        f"/pruefen/{zweite.id}", headers={**HX, "HX-History-Restore-Request": "true"}
    ).text
    assert "<html" in ganz
    # letzte Entscheidung: zurück zur Liste (ganze Seite)
    r = aktion(client, zweite.id, "freigeben", kopf=HX)
    assert r.headers["hx-redirect"] == "/pruefen?ansicht=offen&erledigt=freigegeben"


def test_htmx_409_fragment_mit_meldung_und_neuem_stand(qw):
    b = qw.unsicher()
    client = qw.web.angemeldet("jan")
    alt = stand_aus(client.get(f"/pruefen/{b.id}").text)
    qw.sql("UPDATE buchungssaetze SET buchungstext = 'anders'")
    r = client.post(
        f"/pruefen/{b.id}/freigeben",
        data={"csrf": csrf(client), "stand": alt},
        headers=HX,
    )
    assert r.status_code == 409 and "<html" not in r.text
    assert 'role="alert"' in r.text and "inzwischen geändert" in r.text
    assert stand_aus(r.text) not in (alt, "")


def test_htmx_422_fragment_mit_feld(qw):
    b = qw.unsicher()
    r = aktion(
        qw.web.angemeldet("jan"),
        b.id,
        "korrigieren",
        kopf=HX,
        soll="4360",
        haben="1200",
    )
    assert r.status_code == 422 and "<html" not in r.text
    assert re.search(r'<select id="steuer"[^>]*aria-invalid="true"', r.text)


def test_ohne_htmx_303_auf_den_naechsten(qw):
    erste = qw.unsicher(tag=date(2026, 10, 1))
    zweite = qw.unsicher(tag=date(2026, 10, 2), name="Papier Paul")
    r = aktion(qw.web.angemeldet("jan"), erste.id, "freigeben")
    assert r.status_code == 303 and str(zweite.id) in r.headers["location"]
    assert "hx-push-url" not in r.headers


def test_entscheidung_schliesst_kontierung_pruefen(qw):
    from accounti.aufgaben import aufgaben_zu, melde_aufgabe
    from accounti.models.aufgaben import AufgabenStatus, Objekt

    b = qw.unsicher()
    with qw.fabrik()() as s:
        melde_aufgabe(
            s, "kontierung_pruefen", Objekt("buchung", b.id), "prüfen", erzeugt_von="x"
        )
        s.commit()
    aktion(qw.web.angemeldet("jan"), b.id, "freigeben")
    with qw.fabrik()() as s:
        (a,) = aufgaben_zu(s, Objekt("buchung", b.id))
    assert a.status is AufgabenStatus.HINFAELLIG and "jan" in (a.abschluss_grund or "")


def test_fehler_der_fachlogik_als_409_mit_meldung(qw):
    b = qw.buchung(datum=date(2025, 12, 30))
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    qw.sql(
        "INSERT INTO abschluesse VALUES "
        "(2025, 1, 'euer', 0, '2026-03-01 10:00:00.000000', 'chef')"
    )
    r = client.post(
        f"/pruefen/{b.id}/freigeben",
        data={"csrf": csrf(client), "stand": stand_aus(seite)},
    )
    assert r.status_code == 409 and "2025" in r.text and 'role="alert"' in r.text
    assert status_von(qw, b.id)[0] == "pruefung"


def test_skr04_gesellschaft_mit_eigenem_bankkonto(qw):
    """Korrektur in b (SKR04, Bank 1800): Umgebung der Gesellschaft — freigegebene
    Buchung 6815 an 1800 ist umkehrbar (mit SKR03-Vorgaben wäre 1800 privat)."""
    vorschlag = qw.unsicher(kuerzel="b")
    assert (vorschlag.soll_konto, vorschlag.haben_konto) == ("6815", "1800")
    client = qw.web.angemeldet("jan")
    client.post("/gesellschaft", data={"csrf": csrf(client), "kuerzel": "b"})
    r = aktion(
        client, vorschlag.id, "korrigieren", soll="6805", haben="1800", steuer="9"
    )
    assert r.status_code == 303, r.text
    assert status_von(qw, vorschlag.id, "b")[:2] == ("korrigiert", "6805")


def test_keine_einmalcode_abfrage_in_der_queue(qw):
    b = qw.unsicher()
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    assert 'name="einmalcode"' not in seite
    assert aktion(client, b.id, "freigeben").status_code == 303


def _unbenutzt() -> None:  # pragma: no cover
    Decimal  # noqa: B018
