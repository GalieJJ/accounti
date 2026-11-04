"""Supervisions-Queue im Browser (Spec 4.2; Baustein 10b, Paket 3)."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from accounti.db.repo_kontierung import speichere_kontierungsgrund
from accounti.models import Belegart, Belegrichtung, BuchungStatus
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
    # umgestellt (Plan P1, Schritt 12): der Vorschlag ist eine Karte
    vorschlag = seite.index('<h2 class="karte-titel">Vorschlag</h2>')
    assert links < iframe < rechts < vorschlag


@pytest.mark.parametrize(("confidence", "text"), [(0.57, "57 %"), (0.29, "29 %")])
def test_confidence_ohne_gleitkommafehler(qw, confidence, text):
    """Nachbesserung Fach N1: 0,57 · 100 = 56,99… — angezeigt wird 57 %, nicht 56 %
    (abgerundet bleibt abgerundet: 0,629 → 62 %)."""
    from accounti.api.seiten.pruefen import confidence_prozent

    assert confidence_prozent(0.629) == 62 and confidence_prozent(0.95) == 95
    b = qw.buchung(confidence=confidence)
    client = qw.web.angemeldet("jan")
    assert text in client.get("/pruefen").text
    assert f'class="confidence">{text}' in client.get(f"/pruefen/{b.id}").text


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
    # umgestellt (Plan P1, Schritt 12): der Vorschlag ist eine Karte
    vorschlag = '<h2 class="karte-titel">Vorschlag</h2>'
    assert "Bürobedarf Müller GmbH" in rechts and "DE89 3704 0044" in rechts
    assert rechts.index("<h2>Umsatz</h2>") < rechts.index(vorschlag)


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


def test_freigeben_mit_pruefregel_fehler_gesperrt(qw):
    """Nachbesserung M4: 1800 an 1200 mit Schlüssel 9 — die Arbeitsfläche zeigt den
    Befund der Prüfregel statt „Freigeben“; ein trotzdem gesendetes Freigeben
    ergibt 422, die Buchung bleibt in der Prüfung."""
    b = qw.buchung(soll="1800", haben="1200")
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{b.id}").text
    assert "Prüfregel Steuerschlüssel und Konto" in seite
    assert f'action="/pruefen/{b.id}/freigeben"' not in seite
    r = client.post(
        f"/pruefen/{b.id}/freigeben",
        data={"csrf": csrf(client), "stand": stand_aus(seite), "ansicht": "offen"},
        headers=HX,
    )
    assert r.status_code == 422 and "nicht freigeben" in r.text
    assert status_von(qw, b.id)[0] == "pruefung"


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
    # umgestellt (Plan P1, Schritt 9): statt des Hakens ein Formular am Benutzer
    assert 'id="tastenhilfe"' in seite and 'name="tastenkuerzel" value="aus"' in seite
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
    # umgestellt (Plan P1, B21): Kennzeichen data-hauptknopf statt der Klasse
    assert "data-hauptknopf" in knoepfe[0] and "formaction" not in knoepfe[0]
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
    ausgang = qw.beleg(
        pdf("Rechnung AR-1 500,00"), belegart=Belegart.AUSGANGSRECHNUNG,
        richtung=Belegrichtung.AUSGANG, belegnummer="AR-1",
    )  # fmt: skip
    ust = qw.buchung(
        beleg_id=ausgang.id, soll="1200", haben="8400", steuer_schluessel=3,
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
    # Schlüssel 3 auf dem Eingangsbeleg: Fehlschlüssel, kein § 14c — wählbar sind der
    # Schlüssel laut Beleg (19 % → 9) und „ohne Steuer“ (Runde 7, g6w N5)
    fehl = qw.buchung(
        beleg_id=beleg.id, soll="4930", haben="1200", steuer_schluessel=3,
        datum=date(2026, 10, 4),
    )  # fmt: skip
    assert optionen(fehl) == ["", "3", "9", "ohne"]


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
    # umgestellt (Plan P1, Schritt 12): die Anzahl steht im Reiter als eigene Zahl
    assert 'Zurückgestellt <span class="reiter-anzahl">1</span>' in offen
    assert f"/pruefen/{erste.id}" not in offen
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
    # umgestellt (Plan P1, Schritt 12): zwei Spalten über das Layout
    assert "<html" not in teil and 'class="layout-zweispaltig"' in teil
    ganz = client.get(
        f"/pruefen/{zweite.id}", headers={**HX, "HX-History-Restore-Request": "true"}
    ).text
    assert "<html" in ganz
    # letzte Entscheidung: zurück zur Liste (ganze Seite)
    r = aktion(client, zweite.id, "freigeben", kopf=HX)
    assert r.headers["hx-redirect"] == "/pruefen?ansicht=offen&erledigt=freigegeben"


def _weiter(html: str, klasse: str) -> str:
    form = re.search(rf'<form [^>]*class="{klasse}">(.*?)</form>', html, re.S)
    assert form, klasse
    # data-hier: accounti.js setzt beim Absenden die URL, die der Browser dann zeigt
    treffer = re.search(r'name="weiter" value="([^"]*)" data-hier>', form.group(1))
    assert treffer
    return treffer.group(1).replace("&amp;", "&")


def test_rueckkehrziel_der_vorlieben_folgt_der_angezeigten_seite(qw):
    """P1 Runde 2 (gp1-bestand N1/N3): „Tastenkürzel ausschalten“ und „Übernehmen“
    führen auf die Buchung und Ansicht zurück, die der Browser gerade zeigt — mit
    ``?ansicht=``, und nach einer htmx-Aktion auf die neue Buchung (Push-URL), nicht
    auf die eben freigegebene. ``?erledigt=`` (einmalige Meldung) und Fremdes fallen
    weg."""
    erste = qw.unsicher(tag=date(2026, 10, 1))
    zweite = qw.unsicher(tag=date(2026, 10, 2), name="Papier Paul")
    client = qw.web.angemeldet("jan")
    seite = client.get(f"/pruefen/{erste.id}?ansicht=offen").text
    assert _weiter(seite, "tasten-schalter") == f"/pruefen/{erste.id}?ansicht=offen"
    assert _weiter(seite, "benutzermenue-wahl") == f"/pruefen/{erste.id}?ansicht=offen"
    liste = client.get(
        "/pruefen?ansicht=zurueckgestellt&erledigt=freigegeben&x=%3Cy%3E"
    ).text
    assert _weiter(liste, "benutzermenue-wahl") == "/pruefen?ansicht=zurueckgestellt"
    assert "%3Cy%3E" not in liste and "&lt;y" not in liste  # nichts Fremdes gespiegelt
    r = aktion(client, erste.id, "freigeben", kopf=HX)
    push = r.headers["hx-push-url"]
    assert push == f"/pruefen/{zweite.id}?ansicht=offen"
    assert _weiter(r.text, "tasten-schalter") == push
    teil = client.get(
        f"/pruefen/{zweite.id}?ansicht=offen",
        headers={**HX, "HX-Current-URL": f"http://testserver/pruefen/{erste.id}"},
    ).text
    assert _weiter(teil, "tasten-schalter") == f"/pruefen/{zweite.id}?ansicht=offen"
    zurueck = client.post(
        "/konto/vorlieben",
        data={"csrf": csrf(client), "weiter": push, "tastenkuerzel": "aus"},
        follow_redirects=False,
    )
    assert zurueck.status_code == 303 and zurueck.headers["location"] == push


def test_fokus_nach_dem_austausch_auf_die_ueberschrift(qw):
    """A104 (P1 Runde 2, gp1-design B9): Nach jedem Austausch der Arbeitsfläche geht der
    Fokus auf die Überschrift des neuen Inhalts (``tabindex="-1"`` und ``data-fokus``,
    accounti.js setzt ihn) — bei einem Fehler auf die Fehlerliste, die vorn steht. Die
    ganze Seite trägt kein ``data-fokus`` (der Sprunglink bleibt das erste Ziel)."""
    erste = qw.unsicher(tag=date(2026, 10, 1))
    zweite = qw.unsicher(tag=date(2026, 10, 2), name="Papier Paul")
    client = qw.web.angemeldet("jan")
    ganz = client.get(f"/pruefen/{erste.id}").text
    assert "data-fokus" not in ganz
    for teil in (
        client.get(f"/pruefen/{zweite.id}?ansicht=offen", headers=HX).text,
        aktion(client, erste.id, "freigeben", kopf=HX).text,
    ):
        fokus = re.findall(r"<[a-z0-9]+ [^>]*data-fokus[^>]*>", teil)
        assert len(fokus) == 1, fokus
        assert fokus[0].startswith("<h2 ") and 'tabindex="-1"' in fokus[0], fokus
    fehler = aktion(client, zweite.id, "zurueckstellen", kopf=HX, text="")
    assert fehler.status_code == 422
    erstes = re.search(r"<[a-z0-9]+ [^>]*data-fokus[^>]*>", fehler.text)
    assert erstes and "fehlerliste" in erstes.group(0)


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


@pytest.mark.parametrize("kaputt", ["yaml", "latin1"])
def test_kaputte_konfiguration_zeigt_meldung_statt_standardwerten(qw, kaputt):
    """B7-4 (g7w, Runde 7): Mit kaputter accounti.yaml zeigte die Arbeitsfläche still
    eine Seite mit Standardwerten für Steuer und Prüfregeln (Runde 6: 500). Jetzt steht
    die Meldung samt Datei auf der Seite, und es gibt keine Entscheidung; Freigeben
    endet weiter mit 409, gebucht wird nichts."""
    b = qw.unsicher()
    frei = qw.buchung(status=BuchungStatus.GEPRUEFT, datum=date(2026, 10, 2))
    client = qw.web.angemeldet("jan")
    stand = stand_aus(client.get(f"/pruefen/{b.id}").text)
    assert (
        f'action="/buchungen/{frei.id}/stornieren"'
        in client.get(f"/buchungen/{frei.id}").text
    )
    pfad = qw.web.umgebung.config["a"]
    roh = pfad.read_text(encoding="utf-8")
    if kaputt == "yaml":
        pfad.write_text(roh + "\nkaputt: [a, b\n", encoding="utf-8")
        meldung = "kein gültiges YAML"
    else:
        pfad.write_bytes(roh.encode("utf-8") + "\n# Bürobedarf\n".encode("latin-1"))
        meldung = "keine UTF-8-Datei"
    seite = client.get(f"/pruefen/{b.id}")
    assert seite.status_code == 200
    assert "Konfiguration der Gesellschaft ist fehlerhaft" in seite.text
    assert meldung in seite.text and str(pfad) in seite.text
    for was in ("freigeben", "korrigieren", "zurueckstellen"):
        assert f'action="/pruefen/{b.id}/{was}"' not in seite.text, was
    r = client.post(
        f"/pruefen/{b.id}/freigeben",
        data={"csrf": csrf(client), "stand": stand, "ansicht": "offen"},
        follow_redirects=False,
    )
    assert r.status_code == 409 and meldung in r.text
    assert status_von(qw, b.id)[0] == "pruefung"
    # /buchungen: dieselbe Meldung, ohne Korrektur und Storno
    seite = client.get(f"/buchungen/{frei.id}")
    assert seite.status_code == 200
    assert "Konfiguration der Gesellschaft ist fehlerhaft" in seite.text
    for was in ("korrigieren", "stornieren"):
        assert f'action="/buchungen/{frei.id}/{was}"' not in seite.text, was


def test_steuerauswahl_erloes_auf_quittung(qw):
    """R7-3 (g7w): Ein Erlös auf einer Quittung (eigener Kassenbon) bzw. einer
    Marktplatzabrechnung (SONSTIGES) ist keine Eingangsbuchung — kein Schlüssel 9,
    kein „ohne Steuer“ (§ 14c); ein Aufwand auf der Quittung bleibt Fehlschlüssel."""
    client = qw.web.angemeldet("jan")

    def optionen(b):  # noqa: ANN001, ANN202
        seite = client.get(f"/pruefen/{b.id}").text
        auswahl = re.search(r'<select id="steuer".*?</select>', seite, re.S).group(0)
        return re.findall(r'<option value="([^"]*)"', auswahl), seite

    for art, soll in ((Belegart.QUITTUNG, "1000"), (Belegart.SONSTIGES, "1590")):
        beleg = qw.beleg(pdf(f"Beleg {art.value}"), belegart=art, belegnummer=None)
        erloes = qw.buchung(
            beleg_id=beleg.id, soll=soll, haben="8400", steuer_schluessel=3,
            datum=date(2026, 10, 2),
        )  # fmt: skip
        werte, seite = optionen(erloes)
        assert werte == ["", "3"], (art, werte)
        assert "Fehlschlüssel" not in seite and "§ 14c" in seite
    quittung = qw.beleg(pdf("Kassenbon"), belegart=Belegart.QUITTUNG, belegnummer="Q")
    aufwand = qw.buchung(
        beleg_id=quittung.id, soll="4930", haben="1000", steuer_schluessel=3,
        datum=date(2026, 10, 3),
    )  # fmt: skip
    werte, seite = optionen(aufwand)
    assert werte == ["", "3", "9", "ohne"] and "Fehlschlüssel" in seite


@pytest.mark.parametrize(
    ("bereiche", "erloes", "erwartet"),
    [
        # erweitert: 2700 ist Erlöskonto der Voranmeldung → § 14c, nur Schlüssel 3
        ("['2700-2759', '8000-8959']", "2700", ["", "3"]),
        # eingeschränkt: 8200 ist keines → Fehlschlüssel, laut Beleg 9, ohne Steuer
        ("['8400-8499']", "8200", ["", "3", "9", "ohne"]),
    ],
    ids=["erweitert", "eingeschraenkt"],
)
def test_steuerauswahl_mit_den_elster_konten(qw, bereiche, erloes, erwartet):
    """G8R-2 (g8w, t2_elster_auswahl.py): Queue und /buchungen bildeten den Kontenplan
    ohne ``elster.steuerrelevante_konten`` — die Auswahl bot an, was die Korrektur
    ablehnte (bzw. verbarg, was sie zuließ). Jetzt mit denselben Konten wie
    ``korrigiere``."""
    pfad = qw.web.umgebung.config["a"]
    pfad.write_text(
        pfad.read_text(encoding="utf-8")
        + f"elster:\n  steuerrelevante_konten: {bereiche}\n",
        encoding="utf-8",
    )
    client = qw.web.angemeldet("jan")
    beleg = qw.beleg(pdf("Kassenbon"), belegart=Belegart.QUITTUNG, belegnummer="Q")
    vorschlag = qw.buchung(
        beleg_id=beleg.id, soll="1000", haben=erloes, steuer_schluessel=3,
        datum=date(2026, 10, 2),
    )  # fmt: skip
    frei = qw.buchung(
        beleg_id=beleg.id, soll="1000", haben=erloes, steuer_schluessel=3,
        datum=date(2026, 10, 3), status=BuchungStatus.GEPRUEFT,
    )  # fmt: skip
    for url in (f"/pruefen/{vorschlag.id}", f"/buchungen/{frei.id}"):
        seite = client.get(url).text
        auswahl = re.search(r'<select id="steuer".*?</select>', seite, re.S)
        assert auswahl is not None, url
        werte = re.findall(r'<option value="([^"]*)"', auswahl.group(0))
        assert werte == erwartet, (url, werte)
    # der Hinweis der Arbeitsfläche (/buchungen zeigt ihn nicht)
    seite = client.get(f"/pruefen/{vorschlag.id}").text
    assert ("Fehlschlüssel" in seite) == ("ohne" in erwartet)
    assert ("§ 14c Abs. 1" in seite) == ("ohne" not in erwartet)


def test_erloesschmaelerung_im_haben_im_browser_bleibt_ausgewiesen(qw):
    """GF-1a (F Runde 2, gf-richtung test_gf6_web.py): Kassenbon „1000 an 8400,
    Schlüssel 3“ → in der Queue „1000 an 8700“ mit Schlüssel 3 (303), danach bot
    ``/buchungen`` „9“ und „ohne“ an, und „ohne Steuer“ mit Grund buchte die
    Umsatzsteuer aus (200). Jetzt bleibt die Auswahl ``3`` (§ 14c), der POST 422."""
    from tests.api_hilfe import formularwert

    client = qw.web.angemeldet("jan")
    beleg = qw.beleg(pdf("Kassenbon"), belegart=Belegart.QUITTUNG, belegnummer="Q")
    b = qw.buchung(
        beleg_id=beleg.id, soll="1000", haben="8400", steuer_schluessel=3,
        datum=date(2026, 10, 2),
    )  # fmt: skip
    r = aktion(client, b.id, "korrigieren", soll="1000", haben="8700", steuer="3")
    assert r.status_code == 303, r.text
    seite = client.get(f"/buchungen/{b.id}").text
    auswahl = re.search(r'<select id="steuer".*?</select>', seite, re.S)
    assert auswahl is not None
    assert re.findall(r'<option value="([^"]*)"', auswahl.group(0)) == ["", "3"]
    daten = {
        "csrf": csrf(client),
        "stand": formularwert(seite, "stand"),
        "einmalcode": qw.web.personen["jan"].codes.pop(),
        "soll": "1000",
        "haben": "8700",
        "steuer": "ohne",
        "grund": "kein USt-Beleg",
    }
    r = client.post(
        f"/buchungen/{b.id}/korrigieren", data=daten, follow_redirects=False
    )
    assert r.status_code == 422, r.status_code
    assert "§ 14c" in r.text
    wirksam = qw.sql(
        "SELECT haben_konto, steuer_schluessel FROM buchungssaetze WHERE beleg_id = :i "
        "AND storniert_durch IS NULL AND storno_von IS NULL",
        "a",
        i=str(beleg.id),
    )
    assert [tuple(z) for z in wirksam] == [("8700", 3)]


def _status_oob(html: str) -> str:
    treffer = re.search(r'<div hx-swap-oob="innerHTML:#status">(.*?)</div>', html, re.S)
    assert treffer, "kein hx-swap-oob für #status"
    return treffer.group(1)


def test_ergebnis_im_statusbereich(qw):
    """A110, AK54 (Plan P1, Schritt 12): Die Fragmente nach Freigeben, Korrigieren,
    Zurückstellen und nach einem 409 sagen ihr Ergebnis im globalen Bereich #status an
    (hx-swap-oob); die sichtbare Meldung trägt dann kein role."""
    eintraege = [
        qw.unsicher(tag=date(2026, 10, n), name=f"Firma {n}") for n in range(1, 5)
    ]
    client = qw.web.angemeldet("jan")
    r = aktion(client, eintraege[0].id, "freigeben", kopf=HX)
    assert "Buchung freigegeben." in _status_oob(r.text)
    assert '<div class="hinweis hinweis-ok">' in r.text  # ohne role
    r = aktion(
        client,
        eintraege[1].id,
        "korrigieren",
        kopf=HX,
        soll="4930",
        haben="1200",
        steuer="9",
    )
    assert r.status_code == 200 and _status_oob(r.text).strip()
    r = aktion(client, eintraege[2].id, "zurueckstellen", kopf=HX, text="Wofür?")
    assert r.status_code == 200 and _status_oob(r.text).strip()
    alt = stand_aus(client.get(f"/pruefen/{eintraege[3].id}").text)
    qw.sql("UPDATE buchungssaetze SET buchungstext = 'anders'")
    r = client.post(
        f"/pruefen/{eintraege[3].id}/freigeben",
        data={"csrf": csrf(client), "stand": alt},
        headers=HX,
    )
    assert r.status_code == 409 and "inzwischen geändert" in _status_oob(r.text)
    # ohne htmx (ganze Seite) kein hx-swap-oob, die Meldung selbst ist die Ansage
    seite = client.get(f"/pruefen/{eintraege[3].id}?erledigt=freigegeben").text
    assert (
        "hx-swap-oob" not in seite
        and 'class="hinweis hinweis-ok" role="status"' in seite
    )
