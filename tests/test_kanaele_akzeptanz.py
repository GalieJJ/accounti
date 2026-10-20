"""Akzeptanzkriterien 1–6 der Spec über die neuen Kanäle E-Mail, Webhook, Connector.

Jeder Kanal läuft über die echte Gegenstelle (lokaler IMAP-Server, FastAPI-TestClient,
lokaler HTTP-Server) und die echte Pipeline mit dem BelegErkenner.
"""

import base64
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from accounti.belege.archiv import BelegArchiv
from accounti.belege.erkennung import BelegErkenner
from accounti.belege.kanaele.connector import ConnectorKanal, baue_connector
from accounti.belege.kanaele.einstellungen import ConnectorEintrag, EmailPostfach
from accounti.belege.kanaele.email import EmailKanal
from accounti.belege.kanaele.gedaechtnis import DbGedaechtnis, absender_zu_beleg
from accounti.belege.kanaele.ordner import OrdnerKanal
from accounti.belege.ocr import OCREngine, OCRNichtVerfuegbarError
from accounti.belege.pipeline import nimm_auf
from accounti.belege.webhook import erstelle_app
from accounti.belege.webhook.token import lege_token_an
from accounti.db import init_db, session_factory
from accounti.db.repository import lade_belege, lade_eingaenge
from accounti.models import Belegart, BelegStatus, Eingangsergebnis
from tests.http_attrappe import HttpAttrappe, datei_antwort, json_antwort
from tests.imap_attrappe import ImapAttrappe, Postfach
from tests.pdf_hilfe import pdf_mit_text
from tests.test_kanaele_email import mail

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "belege"
RECHNUNG = (FIXTURES / "rechnung_zwei_steuersaetze.txt").read_text(encoding="utf-8")
KREDITKARTE = (FIXTURES / "kreditkarte_12_umsaetze.txt").read_text(encoding="utf-8")
SCAN = (FIXTURES / "quittung_tankstelle_scan.jpg").read_bytes()
PDF = pdf_mit_text(RECHNUNG)


class KeineOCR(OCREngine):
    name = "keine"

    def erkenne(self, bild):
        raise OCRNichtVerfuegbarError("Tesseract ist nicht installiert")


@pytest.fixture
def umgebung(tmp_path):
    engine, make_session = session_factory(
        f"sqlite:///{(tmp_path / 'a.db').as_posix()}"
    )
    init_db(engine)
    return make_session, BelegArchiv(tmp_path / "archiv"), BelegErkenner(ocr=KeineOCR())


def _nimm_auf(kanal, umgebung):
    make_session, archiv, erkenner = umgebung
    eingaenge = []
    with make_session() as s:
        for roh in kanal.abholen():
            eingaenge.append(nimm_auf(s, archiv, roh, erkenner=erkenner))
            s.commit()
            kanal.bestaetige(roh)
    return eingaenge


def _per_email(umgebung, *anhaenge, postfach_name="rechnungen", **mailwerte):
    pf = Postfach()
    pf.lege_ab(mail(*anhaenge, **mailwerte))
    with ImapAttrappe(pf) as server:
        postfach = EmailPostfach(
            name=postfach_name,
            host="127.0.0.1",
            port=server.port,
            verschluesselung="keine",
            benutzer=pf.benutzer,
        )
        kanal = EmailKanal(postfach, pf.passwort, DbGedaechtnis(umgebung[0]))
        return _nimm_auf(kanal, umgebung)


def _per_webhook(umgebung, dateiname, inhalt, absender="n8n-Weiterleitung"):
    make_session, archiv, erkenner = umgebung
    with make_session() as s:
        token = lege_token_an(s, f"t{len(lade_eingaenge(s))}")
        s.commit()
    client = TestClient(erstelle_app(make_session, archiv, erkenner=erkenner))
    antwort = client.post(
        "/belege",
        headers={"Authorization": f"Bearer {token}"},
        data={"absender": absender},
        files=[("datei", (dateiname, inhalt, "application/octet-stream"))],
    )
    assert antwort.status_code == 200, antwort.text
    return antwort.json()["ergebnisse"]


def _per_connector(umgebung, dateiname, inhalt, base64_feld=False):
    route_datei = (
        (lambda a: json_antwort({"inhalt": base64.b64encode(inhalt).decode()}))
        if base64_feld
        else (lambda a: datei_antwort(inhalt))
    )
    routen = {
        "/api/belege": lambda a: json_antwort(
            [{"id": "K-1", "name": dateiname, "von": "Portal GmbH"}]
        ),
        "/api/belege/K-1": route_datei,
    }
    with HttpAttrappe(routen) as server:
        eintrag = ConnectorEintrag(
            name="portal",
            typ="json",
            basis_url=f"{server.url}/api",
            liste={"pfad": "/belege"},
            felder={"id": "id", "dateiname": "name", "absender": "von"},
            datei={"pfad": "/belege/{id}", "inhalt": "inhalt" if base64_feld else None},
        )
        kanal = ConnectorKanal(
            baue_connector(eintrag, lambda: None), DbGedaechtnis(umgebung[0])
        )
        return _nimm_auf(kanal, umgebung)


def _einziger_beleg(umgebung):
    with umgebung[0]() as s:
        (beleg,) = lade_belege(s)
    return beleg


KANAELE = ["email", "webhook", "connector"]


def _ueber(kanal, umgebung, dateiname, inhalt):
    if kanal == "email":
        _per_email(umgebung, (dateiname, inhalt, "application/pdf"))
    elif kanal == "webhook":
        _per_webhook(umgebung, dateiname, inhalt)
    else:
        _per_connector(umgebung, dateiname, inhalt, base64_feld=True)


@pytest.mark.parametrize("kanal", KANAELE)
def test_akzeptanz_1_pdf_rechnung_wird_ohne_zutun_zum_beleg(umgebung, kanal):
    _ueber(kanal, umgebung, "rechnung.pdf", PDF)
    b = _einziger_beleg(umgebung)
    assert b.kanal == kanal
    assert b.status is BelegStatus.ERFASST, b.pruef_grund
    assert b.belegart is Belegart.EINGANGSRECHNUNG
    assert b.lieferant_name == "Bürobedarf Müller GmbH"
    assert b.belegdatum == date(2026, 3, 5)
    assert (b.netto, b.steuer, b.brutto) == (
        Decimal("150.00"),
        Decimal("22.50"),
        Decimal("172.50"),
    )


@pytest.mark.parametrize("kanal", KANAELE)
def test_akzeptanz_2_zwei_steuersaetze_zwei_positionen(umgebung, kanal):
    _ueber(kanal, umgebung, "rechnung.pdf", PDF)
    b = _einziger_beleg(umgebung)
    assert [(p.steuersatz, p.netto, p.steuer_betrag) for p in b.positionen] == [
        (Decimal("19"), Decimal("100.00"), Decimal("19.00")),
        (Decimal("7"), Decimal("50.00"), Decimal("3.50")),
    ]


def test_akzeptanz_3_derselbe_beleg_ueber_vier_kanaele_ein_datensatz(
    umgebung, tmp_path
):
    ordner = tmp_path / "eingang"
    ordner.mkdir()
    (ordner / "rechnung.pdf").write_bytes(PDF)
    _nimm_auf(OrdnerKanal(ordner), umgebung)
    _per_email(umgebung, ("rechnung.pdf", PDF, "application/pdf"))
    ergebnis = _per_webhook(umgebung, "rechnung.pdf", PDF)
    _per_connector(umgebung, "rechnung.pdf", PDF)
    # derselbe Beleg als andere Datei (anderer Hash): Lieferant + Belegnummer
    _per_email(
        umgebung,
        ("kopie.pdf", pdf_mit_text(RECHNUNG + "\nKopie"), "application/pdf"),
        message_id="<kopie@x>",
        postfach_name="buchhaltung",
    )
    beleg = _einziger_beleg(umgebung)
    assert ergebnis[0]["ergebnis"] == "dublette"
    assert ergebnis[0]["beleg_id"] == str(beleg.id)
    with umgebung[0]() as s:
        eingaenge = lade_eingaenge(s)
    assert [(e.kanal, e.ergebnis) for e in eingaenge] == [
        ("ordner", Eingangsergebnis.NEU),
        ("email", Eingangsergebnis.DUBLETTE),
        ("webhook", Eingangsergebnis.DUBLETTE),
        ("connector", Eingangsergebnis.DUBLETTE),
        ("email", Eingangsergebnis.DUBLETTE),
    ]
    assert all(e.beleg_id == beleg.id for e in eingaenge)
    assert "Hash" in (eingaenge[1].hinweis or "")
    assert "RE-2026-0042" in (eingaenge[-1].hinweis or "")


def test_akzeptanz_4_kreditkartenabrechnung_per_connector(umgebung):
    _per_connector(umgebung, "kreditkarte.pdf", pdf_mit_text(KREDITKARTE))
    b = _einziger_beleg(umgebung)
    assert b.belegart is Belegart.KONTOAUSZUG
    assert len(b.positionen) == 12


def test_akzeptanz_5_unlesbarer_scan_per_email_geht_zur_pruefung(umgebung):
    eingaenge = _per_email(
        umgebung,
        ("scan.jpg", SCAN, "image/jpeg"),
        ("rechnung.pdf", PDF, "application/pdf"),
    )
    assert len(eingaenge) == 2  # die Pipeline läuft nach dem Scan weiter
    with umgebung[0]() as s:
        belege = {b.dateiname: b for b in lade_belege(s)}
    assert belege["scan.jpg"].status is BelegStatus.ZUR_PRUEFUNG
    assert "Tesseract" in (belege["scan.jpg"].pruef_grund or "")
    assert belege["rechnung.pdf"].status is BelegStatus.ERFASST


@pytest.mark.parametrize("kanal", KANAELE)
def test_akzeptanz_6_original_unveraendert_im_archiv(umgebung, kanal):
    _ueber(kanal, umgebung, "scan.jpg", SCAN)
    b = _einziger_beleg(umgebung)
    assert umgebung[1].lese(b.datei_hash) == SCAN
    assert umgebung[1].pfad(b.datei_hash).suffix == ".jpg"


def test_absender_ist_hinweis_zum_beleg(umgebung):
    _per_email(umgebung, ("rechnung.pdf", PDF, "application/pdf"))
    b = _einziger_beleg(umgebung)
    assert b.herkunft.startswith("E-Mail rechnungen von rechnung@mueller.example")
    with umgebung[0]() as s:
        nachricht = absender_zu_beleg(s, b)
    assert nachricht is not None
    assert nachricht.absender_name == "Bürobedarf Müller GmbH"
