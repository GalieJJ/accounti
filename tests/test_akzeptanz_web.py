"""Akzeptanzkriterien 1 und 2 der Web-Oberfläche (Spec 10, Baustein 10b) — Ende zu
Ende über den Testclient: Anmeldung mit Passwort und zweitem Faktor, Queue, Beleg,
Korrektur, Regel, nächster Lauf über REST und CLI.

1. Eine unsichere Buchung lässt sich im Browser mit Belegansicht prüfen, korrigieren
   und freigeben.
2. Aus einer Korrektur entsteht auf Wunsch eine Regel, die beim nächsten Lauf greift.
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from accounti.aufgaben import aufgaben_zu, melde_aufgabe
from accounti.db.repo_kontierung import lade_kontierungsgrund, lade_kontierungsregeln
from accounti.db.repository import lade_buchungen, speichere_abgleich
from accounti.models import AbgleichStatus, Belegabgleich, BuchungStatus
from accounti.models.aufgaben import AufgabenStatus, Objekt
from accounti.models.auth import TokenRecht
from accounti.pruefung.journal import lade_journal, pruefe_journal
from tests.api_hilfe import csrf, formularwert
from tests.auth_hilfe import billige_hashes
from tests.pruefen_hilfe import (
    LLM_BEGRUENDUNG,
    LLMAttrappe,
    jpeg,
    pdf,
    png,
    queuewelt,
    stand_aus,
    tiff,
)

HX = {"HX-Request": "true"}
ERECHNUNG = Path(__file__).resolve().parents[1] / "examples" / "erechnung"


@pytest.fixture(autouse=True)
def _umgebung(monkeypatch):
    billige_hashes(monkeypatch)
    # der Server-Prozess heißt anders — im Journal darf er nie stehen
    monkeypatch.setenv("ACCOUNTI_BENUTZER", "mallory")
    monkeypatch.setattr("getpass.getuser", lambda: "mallory")


@pytest.fixture
def qw(tmp_path):
    return queuewelt(tmp_path)


def journal(qw, buchung_id, kuerzel="a"):  # noqa: ANN001, ANN201
    with qw.fabrik(kuerzel)() as s:
        return [
            (e.vorgang, e.person) for e in lade_journal(s, objekt_id=str(buchung_id))
        ]


def buchung(qw, buchung_id, kuerzel="a"):  # noqa: ANN001, ANN201
    with qw.fabrik(kuerzel)() as s:
        return next(b for b in lade_buchungen(s) if b.id == buchung_id)


def mit_beleg_aus_abgleich(qw, b, inhalt: bytes, endung: str = ".pdf", **kw):  # noqa: ANN001, ANN003, ANN201
    """Beleg im Archiv der Gesellschaft, mit dem Umsatz der Buchung bestätigt
    abgeglichen (nach der Kontierung — die Buchung bleibt der LLM-Vorschlag)."""
    beleg = qw.beleg(inhalt, endung, **kw)
    with qw.fabrik()() as s:
        speichere_abgleich(
            s,
            Belegabgleich(
                transaktion_id=b.transaktion_id,
                beleg_id=beleg.id,
                stufe="referenz",
                status=AbgleichStatus.BESTAETIGT,
                confidence=1.0,
                begruendung="Rechnungsnummer im Verwendungszweck",
            ),
        )
        s.commit()
    return beleg


# --- Akzeptanz 1 ----------------------------------------------------------------------


def test_akzeptanz_1_mit_abgleich_vor_der_kontierung(qw):
    """Nachbesserung Fach N7: der Ablauf wie im Betrieb — der Beleg ist vor der
    Kontierung abgeglichen, die Buchung ist eine Belegbuchung (Beleg links,
    Umsatzdaten rechts). Dann greifen die Beleg-Schlüsselsperre und „ohne Steuer“
    nur mit Grund; die Korrektur mit bestätigtem Schlüssel geht durch."""
    tx = qw.umsatz(zweck="RE-4711 Büromaterial")
    beleg = qw.beleg(pdf("Rechnung RE-4711 Bürobedarf Müller GmbH 59,50 EUR"))
    with qw.fabrik()() as s:
        speichere_abgleich(
            s,
            Belegabgleich(
                transaktion_id=tx.id,
                beleg_id=beleg.id,
                stufe="referenz",
                status=AbgleichStatus.BESTAETIGT,
                confidence=1.0,
                begruendung="Rechnungsnummer im Verwendungszweck",
            ),
        )
        s.commit()
    (b,) = [x for x in qw.kontiere() if x.transaktion_id == tx.id]
    assert b.beleg_id == beleg.id and b.status is BuchungStatus.ZUR_PRUEFUNG
    jan = qw.web.angemeldet("jan")
    flaeche = jan.get(f"/pruefen/{b.id}").text
    assert f'<iframe class="beleg" src="/belege/{beleg.id}/datei"' in flaeche
    assert "RE-4711 Büromaterial" in flaeche  # Umsatzdaten (M5)
    assert '<option value="8"' not in flaeche  # nur der Schlüssel des Belegs
    daten = {
        "csrf": csrf(jan),
        "stand": stand_aus(flaeche),
        "ansicht": "offen",
        "soll": "4930",
        "haben": "1200",
    }
    anderer = jan.post(f"/pruefen/{b.id}/korrigieren", data={**daten, "steuer": "8"})
    assert anderer.status_code == 422 and "Beleg" in anderer.text
    ohne = jan.post(f"/pruefen/{b.id}/korrigieren", data={**daten, "steuer": "ohne"})
    assert ohne.status_code == 422 and "Grund" in ohne.text
    r = jan.post(
        f"/pruefen/{b.id}/korrigieren",
        data={**daten, "steuer": "9"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    korrigiert = buchung(qw, b.id)
    assert (korrigiert.soll_konto, korrigiert.steuer_schluessel) == ("4930", 9)
    assert korrigiert.status is BuchungStatus.KORRIGIERT


def test_akzeptanz_1_unsichere_buchung_pruefen_korrigieren_freigeben(qw):
    erste = qw.unsicher(tag=date(2026, 10, 1))
    zweite = qw.unsicher(
        tag=date(2026, 10, 2), name="Papier Paul KG", zweck="RE 77 Kopierpapier"
    )
    inhalt = pdf("Rechnung RE-4711 Bürobedarf Müller GmbH 59,50 EUR")
    beleg = mit_beleg_aus_abgleich(qw, erste, inhalt)
    with qw.fabrik()() as s:
        melde_aufgabe(
            s,
            "kontierung_pruefen",
            Objekt("buchung", erste.id),
            "Kontierung prüfen",
            erzeugt_von="aufgaben",
        )
        s.commit()

    jan = qw.web.angemeldet("jan")  # Passwort und TOTP-Code der Authenticator-App
    liste = jan.get("/pruefen").text
    assert "62 %" in liste and LLM_BEGRUENDUNG in liste
    assert "Bürobedarf Müller GmbH" in liste and "Papier Paul KG" in liste

    flaeche = jan.get(f"/pruefen/{erste.id}").text
    assert f'<iframe class="beleg" src="/belege/{beleg.id}/datei"' in flaeche
    assert "KI-Vorschlag (LLM)" in flaeche and "attrappe/kontierer-1" in flaeche
    datei = jan.get(f"/belege/{beleg.id}/datei")
    assert datei.content == inhalt
    assert datei.headers["content-type"] == "application/pdf"
    assert datei.headers["content-disposition"].startswith("inline;")

    r = jan.post(
        f"/pruefen/{erste.id}/korrigieren",
        data={
            "csrf": csrf(jan),
            "stand": stand_aus(flaeche),
            "ansicht": "offen",
            "soll": "4930",
            "haben": "1200",
            "steuer": "9",  # ausdrücklich: das Sachkonto ändert sich
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].startswith(f"/pruefen/{zweite.id}")
    korrigiert = buchung(qw, erste.id)
    assert korrigiert.status is BuchungStatus.KORRIGIERT
    assert (korrigiert.soll_konto, korrigiert.steuer_schluessel) == ("4930", 9)
    assert korrigiert.geprueft_von == "jan"
    assert ("buchung_korrigiert", "jan") in journal(qw, erste.id)
    with qw.fabrik()() as s:
        (aufgabe,) = aufgaben_zu(s, Objekt("buchung", erste.id))
    assert aufgabe.status is AufgabenStatus.HINFAELLIG

    naechste = jan.get(r.headers["location"]).text
    assert "Buchung korrigiert." in naechste and "Papier Paul KG" in naechste
    assert 'name="einmalcode"' not in naechste  # die Queue verlangt keinen Code
    r = jan.post(
        f"/pruefen/{zweite.id}/freigeben",
        data={"csrf": csrf(jan), "stand": stand_aus(naechste), "ansicht": "offen"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert buchung(qw, zweite.id).status is BuchungStatus.GEPRUEFT
    assert ("buchung_freigegeben", "jan") in journal(qw, zweite.id)
    assert "Nichts zu prüfen" in jan.get(r.headers["location"]).text
    with qw.fabrik()() as s:
        assert pruefe_journal(s).in_ordnung
        personen = {
            e.person
            for e in lade_journal(s)
            if e.vorgang in ("buchung_korrigiert", "buchung_freigegeben")
        }
    assert personen == {"jan"}


def test_akzeptanz_1_mit_bild_und_erechnung(qw):
    from tests.test_erechnung_zugferd import _pdf

    _r, _x, zugferd = _pdf()
    faelle = [
        (png(), ".png", '<img class="beleg-bild" src="/belege/{id}/datei"'),
        (jpeg(), ".jpg", '<img class="beleg-bild" src="/belege/{id}/datei"'),
        (tiff((5, 4), (5, 4)), ".tif", 'src="/belege/{id}/seite/2.png"'),
        ((ERECHNUNG / "xrechnung_ubl.xml").read_bytes(), ".xml", "Rechnungsnummer"),
        (
            (ERECHNUNG / "xrechnung_cii.xml").read_bytes(),
            ".xml",
            "Steueraufschlüsselung",
        ),
        (zugferd, ".pdf", "E-Rechnung (maßgeblich)"),
    ]
    jan = qw.web.angemeldet("jan")
    for nr, (inhalt, endung, erwartet) in enumerate(faelle, start=1):
        b = qw.unsicher(tag=date(2026, 10, nr), name=f"Lieferant {nr}")
        beleg = mit_beleg_aus_abgleich(qw, b, inhalt, endung, belegnummer=f"B-{nr}")
        seite = jan.get(f"/pruefen/{b.id}").text
        assert erwartet.format(id=beleg.id) in seite, endung


def test_akzeptanz_1_freigegebene_buchung_per_storno(qw):
    b = qw.buchung(status=BuchungStatus.EXPORTIERT)
    jan = qw.web.angemeldet("jan")
    seite = jan.get(f"/buchungen/{b.id}").text
    r = jan.post(
        f"/buchungen/{b.id}/korrigieren",
        data={
            "csrf": csrf(jan),
            "stand": formularwert(seite, "stand"),
            "soll": "4930",
            "haben": "1200",
            "steuer": "9",
            "einmalcode": qw.web.code("jan"),  # frischer TOTP-Code
        },
    )
    assert r.status_code == 200, r.text
    with qw.fabrik()() as s:
        alle = lade_buchungen(s)
        assert pruefe_journal(s).in_ordnung
    assert len(alle) == 3
    original = next(x for x in alle if x.id == b.id)
    assert original.status is BuchungStatus.EXPORTIERT and original.storniert_durch
    seite = jan.get(f"/buchungen/{b.id}").text
    assert "Storniert durch" in seite and "Neubuchung" in seite


def test_akzeptanz_1_betrachter_kann_nicht_freigeben(qw):
    b = qw.unsicher()
    leo = qw.web.angemeldet("leo")
    seite = leo.get(f"/pruefen/{b.id}").text
    assert "62 %" in seite and f"/pruefen/{b.id}/freigeben" not in seite
    r = leo.post(
        f"/pruefen/{b.id}/freigeben",
        data={
            "csrf": csrf(leo),
            "stand": stand_aus(qw.web.angemeldet("jan").get(f"/pruefen/{b.id}").text),
        },
    )
    assert r.status_code == 403
    assert buchung(qw, b.id).status is BuchungStatus.ZUR_PRUEFUNG


def test_akzeptanz_1_htmx_mit_veraltetem_stand(qw):
    b = qw.unsicher()
    jan = qw.web.angemeldet("jan")
    gesehen = stand_aus(jan.get(f"/pruefen/{b.id}").text)
    fritz = qw.web.angemeldet("fritz")
    fritz.post(
        f"/pruefen/{b.id}/freigeben",
        data={"csrf": csrf(fritz), "stand": gesehen},
    )
    r = jan.post(
        f"/pruefen/{b.id}/korrigieren",
        data={
            "csrf": csrf(jan),
            "stand": gesehen,
            "soll": "4930",
            "haben": "1200",
            "steuer": "9",
        },
        headers=HX,
    )
    assert r.status_code == 409 and "<html" not in r.text
    assert "nicht mehr in der Prüfung" in r.text and 'role="alert"' in r.text
    with qw.fabrik()() as s:
        assert len(lade_buchungen(s)) == 1  # kein Storno
    assert buchung(qw, b.id).geprueft_von == "fritz"


def test_akzeptanz_1_htmx_steuerangabe_fehlt(qw):
    b = qw.unsicher()
    jan = qw.web.angemeldet("jan")
    seite = jan.get(f"/pruefen/{b.id}").text
    daten = {
        "csrf": csrf(jan),
        "stand": stand_aus(seite),
        "soll": "4930",
        "haben": "1200",
    }
    r = jan.post(f"/pruefen/{b.id}/korrigieren", data=daten, headers=HX)
    assert r.status_code == 422 and "<html" not in r.text
    assert re.search(r'<select id="steuer"[^>]*aria-invalid="true"', r.text)
    assert "Das Sachkonto ändert sich" in r.text
    r = jan.post(
        f"/pruefen/{b.id}/korrigieren",
        data={**daten, "stand": stand_aus(r.text), "steuer": "9"},
        headers=HX,
    )
    assert r.status_code == 200 or "hx-redirect" in r.headers
    assert buchung(qw, b.id).status is BuchungStatus.KORRIGIERT


def test_akzeptanz_1_skr04_gesellschaft(qw):
    b = qw.unsicher(kuerzel="b")
    jan = qw.web.angemeldet("jan")
    jan.post("/gesellschaft", data={"csrf": csrf(jan), "kuerzel": "b"})
    seite = jan.get(f"/pruefen/{b.id}").text
    assert "Gesellschaft: <strong>Beta Rahmen KG</strong>" in seite
    r = jan.post(
        f"/pruefen/{b.id}/korrigieren",
        data={
            "csrf": csrf(jan),
            "stand": stand_aus(seite),
            "soll": "6805",
            "haben": "1800",
            "steuer": "9",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    assert buchung(qw, b.id, "b").soll_konto == "6805"
    assert jan.get(f"/pruefen/{qw.unsicher().id}").status_code == 404  # nur b aktiv


# --- Akzeptanz 2 ----------------------------------------------------------------------


def lerne_aus_korrektur(qw, client, b, mit_regel=True, **felder):  # noqa: ANN001, ANN003, ANN201
    seite = client.get(f"/pruefen/{b.id}").text
    daten = {
        "csrf": csrf(client),
        "stand": stand_aus(seite),
        "soll": "4930",
        "haben": "1200",
        "steuer": "9",
        "muster": formularwert(seite, "muster")
        if mit_regel and "muster" not in felder
        else "",
        "feld": "beide",
    }
    if mit_regel:
        daten["regel"] = "1"
    daten.update(felder)
    return client.post(
        f"/pruefen/{b.id}/korrigieren", data=daten, follow_redirects=False
    )


TOKEN: dict[tuple[int, str], str] = {}


def rest_lauf(qw, kuerzel="a"):  # noqa: ANN001, ANN201
    schluessel = (id(qw), kuerzel)
    if schluessel not in TOKEN:
        TOKEN[schluessel] = qw.web.token(
            kuerzel,
            TokenRecht.LAEUFE_STARTEN,
            name=f"erp-{kuerzel}" if kuerzel != "a" else "erp",
        )
    token = TOKEN[schluessel]
    return qw.web.client().post(
        "/api/v1/laeufe/bank", headers={"Authorization": f"Bearer {token}"}
    )


def neue_buchung(qw, tx, kuerzel="a"):  # noqa: ANN001, ANN201
    with qw.fabrik(kuerzel)() as s:
        (b,) = [x for x in lade_buchungen(s) if x.transaktion_id == tx.id]
        return b, lade_kontierungsgrund(s, b.id)


def test_akzeptanz_2_korrektur_wird_regel_und_greift_beim_naechsten_lauf(
    qw, monkeypatch
):
    b = qw.unsicher(betrag="-59.50")
    assert (b.soll_konto, b.confidence) == ("4980", 0.62)
    jan = qw.web.angemeldet("jan")
    seite = jan.get(f"/pruefen/{b.id}").text
    # Vorschlag: der ganze Name der Gegenpartei ohne Rechtsform (Nachbesserung H1)
    assert formularwert(seite, "muster") == "Bürobedarf Müller"
    vorschau = jan.post(
        f"/pruefen/{b.id}/regelvorschau",
        data={
            "csrf": csrf(jan),
            "soll": "4930",
            "haben": "1200",
            "steuer": "9",
            "muster": "Bürobedarf Müller",
            "feld": "beide",
        },
        headers=HX,
    )
    assert "Trifft 1 Ausgabe in den letzten 24 Monaten" in vorschau.text
    assert "greift für diesen Umsatz" in vorschau.text

    assert lerne_aus_korrektur(qw, jan, b).status_code == 303
    with qw.fabrik()() as s:
        (regel,) = lade_kontierungsregeln(s)
    assert regel.richtung is not None and regel.richtung.value == "ausgabe"
    assert (regel.soll_konto, regel.steuer_schluessel) == ("4930", 9)
    assert ("regel_gelernt", "jan") in journal(qw, regel.id)

    # nächster Lauf über die REST-API (ohne LLM, unter der Laufsperre)
    attrappe = LLMAttrappe()
    monkeypatch.setattr(
        "accounti.klassifikation.llm.LLMEngine", lambda *a, **k: attrappe
    )
    tx = qw.umsatz(betrag="-12.00", tag=date(2026, 10, 9), zweck="RE 4790")
    r = rest_lauf(qw)
    assert r.status_code == 200, r.text
    neu, grund = neue_buchung(qw, tx)
    assert (neu.soll_konto, neu.confidence) == ("4930", 1.0)
    assert neu.status is BuchungStatus.AUTO_GEBUCHT
    assert grund is not None and grund.regel == regel.name
    assert f"Regel '{regel.name}'" in grund.begruendung
    assert journal(qw, neu.id)[0] == ("buchung_angelegt", "API-Token erp")
    assert attrappe.gefragt == []

    # ebenso über die CLI der Gesellschaft
    monkeypatch.setenv("ACCOUNTI_KONFIG", str(qw.web.umgebung.registry))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT"):
        monkeypatch.delenv(name, raising=False)
    from accounti.cli import app

    tx2 = qw.umsatz(betrag="-7.50", tag=date(2026, 10, 12), zweck="RE 4801")
    ergebnis = CliRunner().invoke(app, ["--gesellschaft", "a", "classify", "--no-llm"])
    assert ergebnis.exit_code == 0, ergebnis.output
    neu2, _ = neue_buchung(qw, tx2)
    assert (neu2.soll_konto, neu2.confidence) == ("4930", 1.0)


def test_akzeptanz_2_vor_falsch_treffender_eigener_regel(qw):
    (qw.web.umgebung.wurzel / "a-regeln.yaml").write_text(
        "- name: buero_falsch\n  muster: 'b(ü|ue)ro'\n  feld: beide\n"
        "  soll_konto: '4980'\n  haben_konto: '1200'\n  steuer_schluessel: 9\n",
        encoding="utf-8",
    )
    tx0 = qw.umsatz()
    assert rest_lauf(qw).status_code == 200
    falsch, _ = neue_buchung(qw, tx0)
    assert falsch.soll_konto == "4980" and falsch.status is BuchungStatus.AUTO_GEBUCHT
    # die eigene Regel bucht automatisch falsch; ein Vorschlag (LLM) wird korrigiert
    b = qw.unsicher(name="Bürobedarf Müller GmbH", zweck="Toner", tag=date(2026, 10, 3))
    jan = qw.web.angemeldet("jan")
    assert lerne_aus_korrektur(qw, jan, b).status_code == 303
    tx = qw.umsatz(betrag="-30.00", tag=date(2026, 10, 9))
    assert rest_lauf(qw).status_code == 200
    neu, grund = neue_buchung(qw, tx)
    assert neu.soll_konto == "4930" and grund is not None
    assert grund.regel is not None and grund.regel.startswith("gelernt_")


def test_akzeptanz_2_erstattung_derselben_gegenpartei_unberuehrt(qw):
    b = qw.unsicher()
    assert lerne_aus_korrektur(qw, qw.web.angemeldet("jan"), b).status_code == 303
    erstattung = qw.umsatz(betrag="12.00", tag=date(2026, 10, 9), zweck="Gutschrift")
    assert rest_lauf(qw).status_code == 200
    with qw.fabrik()() as s:
        gebucht = [x for x in lade_buchungen(s) if x.transaktion_id == erstattung.id]
    assert gebucht == []  # kein Geldabgang auf 4930 — offen für Mensch oder LLM


def test_akzeptanz_2_schalter_pruefen(qw):
    cfg = qw.web.umgebung.config["a"]
    cfg.write_text(
        cfg.read_text(encoding="utf-8").replace(
            "buchhaltung:\n  kontenrahmen: SKR03\n",
            "buchhaltung:\n  kontenrahmen: SKR03\n  gelernte_regeln: pruefen\n",
        ),
        encoding="utf-8",
    )
    b = qw.unsicher()
    assert lerne_aus_korrektur(qw, qw.web.angemeldet("jan"), b).status_code == 303
    tx = qw.umsatz(betrag="-9.00", tag=date(2026, 10, 9))
    assert rest_lauf(qw).status_code == 200
    neu, grund = neue_buchung(qw, tx)
    assert neu.status is BuchungStatus.ZUR_PRUEFUNG and neu.confidence == 0.9
    assert neu.soll_konto == "4930"
    assert grund is not None and "Einstellung: prüfen" in grund.begruendung


def test_akzeptanz_2_ohne_haken_keine_regel(qw):
    b = qw.unsicher()
    r = lerne_aus_korrektur(qw, qw.web.angemeldet("jan"), b, mit_regel=False)
    assert r.status_code == 303
    with qw.fabrik()() as s:
        assert lade_kontierungsregeln(s) == []


def test_akzeptanz_2_nur_in_der_eigenen_gesellschaft(qw):
    b = qw.unsicher()
    assert lerne_aus_korrektur(qw, qw.web.angemeldet("jan"), b).status_code == 303
    tx_b = qw.umsatz(kuerzel="b", tag=date(2026, 10, 9))
    assert rest_lauf(qw, "b").status_code == 200
    with qw.fabrik("b")() as s:
        assert lade_kontierungsregeln(s) == []
        gebucht = [x for x in lade_buchungen(s) if x.transaktion_id == tx_b.id]
    assert gebucht == []


def test_akzeptanz_2_belegbuchung_lernt_sachkonto(qw):
    """Belegbuchung auf ein Personenkonto (OPOS): „Sachkonto am Kontakt lernen“ —
    die nächste Rechnung desselben Lieferanten kommt auf das gelernte Konto."""
    from accounti.konfiguration import Buchhaltung
    from accounti.opos.verbuchung import verbuche_beleg

    erste = qw.beleg(pdf("RE-1"), belegnummer="RE-1", brutto=Decimal("119.00"),
                     netto=Decimal("100.00"), steuer=Decimal("19.00"))  # fmt: skip
    with qw.fabrik()() as s:
        v = verbuche_beleg(s, erste, Buchhaltung())
        s.commit()
    (b,) = v.buchungen
    assert b.status is BuchungStatus.ZUR_PRUEFUNG and b.soll_konto == "4900"
    jan = qw.web.angemeldet("jan")
    seite = jan.get(f"/pruefen/{b.id}").text
    assert "Sachkonto am Kontakt lernen" in seite
    r = lerne_aus_korrektur(
        qw, jan, b, soll="4930", haben=b.haben_konto, steuer="", muster=""
    )
    assert r.status_code == 303, r.text
    zweite = qw.beleg(pdf("RE-2"), belegnummer="RE-2", brutto=Decimal("59.50"),
                      netto=Decimal("50.00"), steuer=Decimal("9.50"))  # fmt: skip
    with qw.fabrik()() as s:
        v2 = verbuche_beleg(s, zweite, Buchhaltung())
        s.commit()
        (e,) = lade_journal(s, vorgang="sachkonto_gelernt")
    assert {x.soll_konto for x in v2.buchungen} == {"4930"}
    assert e.person == "jan" and json.loads(e.nachher or "{}")["sachkonto"] == "4930"


def test_akzeptanz_2_lauf_laeuft_schon_409(qw):
    from accounti.betrieb.laufsperre import laufsperre

    b = qw.unsicher()
    assert lerne_aus_korrektur(qw, qw.web.angemeldet("jan"), b).status_code == 303
    tx = qw.umsatz(betrag="-5.00", tag=date(2026, 10, 9))
    with laufsperre(qw.web.umgebung.db["a"], "bank"):
        assert rest_lauf(qw).status_code == 409
    with qw.fabrik()() as s:
        assert [x for x in lade_buchungen(s) if x.transaktion_id == tx.id] == []
    assert rest_lauf(qw).status_code == 200
    neu, _ = neue_buchung(qw, tx)
    assert neu.soll_konto == "4930"
