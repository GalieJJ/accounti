import base64
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from accounti.belege.archiv import BelegArchiv
from accounti.belege.kanaele import BELEG_KANAELE
from accounti.belege.kanaele.einstellungen import WebhookEinstellungen
from accounti.belege.kanaele.pruefung import Dateipruefung
from accounti.belege.kanaele.webhook import WebhookKanal
from accounti.belege.webhook import erstelle_app
from accounti.belege.webhook.token import (
    PRAEFIX,
    lege_token_an,
    pruefe_token,
    token_hash,
)
from accounti.db import init_db, session_factory
from accounti.db.repo_kanaele import (
    lade_nachrichten,
    lade_webhook_tokens,
    widerrufe_webhook_token,
)
from accounti.db.repository import lade_belege, lade_eingaenge
from accounti.models import BelegStatus
from tests.pdf_hilfe import pdf_mit_text

PDF = pdf_mit_text("Rechnung RE-7\nGesamtbetrag 50,00 EUR")
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x01" * 50


@pytest.fixture
def make_session(tmp_path):
    engine, make = session_factory(f"sqlite:///{(tmp_path / 'w.db').as_posix()}")
    init_db(engine)
    return make


@pytest.fixture
def token(make_session):
    with make_session() as s:
        t = lege_token_an(s, "n8n")
        s.commit()
    return t


def _client(make_session, tmp_path, erkenner=None, max_bytes=10_000, **einstellungen):
    app = erstelle_app(
        make_session,
        BelegArchiv(tmp_path / "archiv"),
        WebhookEinstellungen(**einstellungen),
        Dateipruefung(max_bytes=max_bytes),
        erkenner,
    )
    return TestClient(app)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------


def test_registry_kennt_webhook():
    assert BELEG_KANAELE["webhook"] is WebhookKanal
    roh = list(WebhookKanal([("a.pdf", PDF)], "Webhook x").abholen())
    assert [(r.kanal, r.herkunft, r.inhalt) for r in roh] == [
        ("webhook", "Webhook x", PDF)
    ]


def test_token_nur_als_hash_gespeichert(make_session, token):
    assert token.startswith(PRAEFIX)
    assert len(token) >= len(PRAEFIX) + 43  # 256 Bit, Base64
    with make_session() as s:
        (eintrag,) = lade_webhook_tokens(s)
        assert eintrag.token_hash == token_hash(token)
        assert re.fullmatch(r"[0-9a-f]{64}", eintrag.token_hash)
        assert token not in eintrag.model_dump_json()
        assert pruefe_token(s, token).name == "n8n"
        assert pruefe_token(s, token + "x") is None
        assert pruefe_token(s, "") is None
        with pytest.raises(ValueError, match="gibt es schon"):
            lege_token_an(s, "n8n")
        widerrufe_webhook_token(s, "n8n")
        s.commit()
        assert pruefe_token(s, token) is None


def test_widerrufenes_token_unter_demselben_namen_ersetzen(make_session):
    """Durchgesickertes Token für n8n austauschen: widerrufen, neu anlegen — der
    Name (und damit die Quelle im Gedächtnis) bleibt."""
    with make_session() as s:
        alt = lege_token_an(s, "n8n")
        with pytest.raises(ValueError, match="kanaele webhook widerrufen n8n"):
            lege_token_an(s, "n8n")
        widerrufe_webhook_token(s, "n8n")
        neu = lege_token_an(s, "n8n")
        s.commit()
    with make_session() as s:
        assert pruefe_token(s, alt) is None
        assert pruefe_token(s, neu).name == "n8n"
        tokens = lade_webhook_tokens(s)
        assert [(t.name, t.aktiv) for t in tokens] == [("n8n", False), ("n8n", True)]
        # erneut widerrufen trifft das aktive, danach wieder neu anlegbar
        widerrufe_webhook_token(s, "n8n")
        s.commit()
        assert pruefe_token(s, neu) is None
        lege_token_an(s, "n8n")
        s.commit()


def test_zwei_tokens_sind_verschieden(make_session):
    with make_session() as s:
        assert lege_token_an(s, "a") != lege_token_an(s, "b")
        with pytest.raises(ValueError):
            lege_token_an(s, "ungültig name!")


# ---------------------------------------------------------------------------
# Endpunkt
# ---------------------------------------------------------------------------


def test_gesund_ohne_token(make_session, tmp_path):
    r = _client(make_session, tmp_path).get("/gesund")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ohne_falscher_oder_widerrufener_token_401(make_session, tmp_path, token):
    c = _client(make_session, tmp_path)
    ohne = c.post("/belege", content=PDF)
    assert ohne.status_code == 401
    assert ohne.headers["www-authenticate"].startswith("Bearer")
    # letztes Zeichen sicher ändern — der Token kann selbst auf "A" enden
    anders = token[:-1] + ("B" if token.endswith("A") else "A")
    falsch = c.post("/belege", content=PDF, headers=_auth(anders))
    assert falsch.status_code == 401
    basic = c.post("/belege", content=PDF, headers={"Authorization": "Basic eDp5"})
    assert basic.status_code == 401
    with make_session() as s:
        widerrufe_webhook_token(s, "n8n")
        s.commit()
    assert c.post("/belege", content=PDF, headers=_auth(token)).status_code == 401
    with make_session() as s:
        assert lade_belege(s) == []


def test_rohdaten_werden_aufgenommen(make_session, tmp_path, token):
    c = _client(make_session, tmp_path)
    r = c.post(
        "/belege",
        content=PDF,
        headers={
            **_auth(token),
            "Content-Type": "application/octet-stream",
            "X-Dateiname": quote("Rechnung März.pdf"),
            "X-Absender": quote("Telegram +49 170 0000000"),
        },
    )
    assert r.status_code == 200, r.text
    (ergebnis,) = r.json()["ergebnisse"]
    assert ergebnis["dateiname"] == "Rechnung März.pdf"
    assert ergebnis["ergebnis"] == "neu"
    with make_session() as s:
        (beleg,) = lade_belege(s)
        assert str(beleg.id) == ergebnis["beleg_id"]
        assert beleg.kanal == "webhook"
        assert beleg.herkunft == "Webhook n8n von Telegram +49 170 0000000"
        (n,) = lade_nachrichten(s, kanal="webhook")
        assert n.quelle == "n8n"
        assert n.absender == "Telegram +49 170 0000000"
        assert n.datei_hashes == [beleg.datei_hash]
        (t,) = lade_webhook_tokens(s)
        assert t.zuletzt_genutzt_am is not None
    # Akzeptanz 6: Original unverändert im Archiv
    assert BelegArchiv(tmp_path / "archiv").lese(beleg.datei_hash) == PDF


def test_dateiname_als_parameter_und_ohne_namen(make_session, tmp_path, token):
    c = _client(make_session, tmp_path)
    r = c.post("/belege?dateiname=scan", content=JPEG, headers=_auth(token))
    assert r.json()["ergebnisse"][0]["dateiname"] == "scan.jpg"
    r = c.post("/belege", content=PDF, headers=_auth(token))
    assert r.json()["ergebnisse"][0]["dateiname"] == "beleg.pdf"


def test_multipart_mit_zwei_dateien_und_absender(make_session, tmp_path, token):
    c = _client(make_session, tmp_path)
    r = c.post(
        "/belege",
        headers=_auth(token),
        data={"absender": "WhatsApp Erika"},
        files=[
            ("datei", ("quittung.jpg", JPEG, "image/jpeg")),
            ("datei", ("rechnung.pdf", PDF, "application/pdf")),
        ],
    )
    assert r.status_code == 200, r.text
    assert [e["dateiname"] for e in r.json()["ergebnisse"]] == [
        "quittung.jpg",
        "rechnung.pdf",
    ]
    with make_session() as s:
        belege = lade_belege(s)
        archiv = BelegArchiv(tmp_path / "archiv")
        assert sorted(archiv.lese(b.datei_hash) for b in belege) == sorted([JPEG, PDF])
        assert {b.herkunft for b in belege} == {"Webhook n8n von WhatsApp Erika"}


def test_json_mit_base64(make_session, tmp_path, token):
    c = _client(make_session, tmp_path)
    r = c.post(
        "/belege",
        headers=_auth(token),
        json={
            "absender": "ERP",
            "dateien": [
                {"dateiname": "r.pdf", "inhalt_base64": base64.b64encode(PDF).decode()}
            ],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["ergebnisse"][0]["ergebnis"] == "neu"


@pytest.mark.parametrize(
    ("kopf", "inhalt"),
    [
        ({"Content-Type": "application/json"}, b"{kaputt"),
        ({"Content-Type": "application/json"}, json.dumps({"dateien": "x"}).encode()),
        (
            {"Content-Type": "application/json"},
            json.dumps(
                {"dateien": [{"dateiname": "a.pdf", "inhalt_base64": "!!kein base64"}]}
            ).encode(),
        ),
        ({"Content-Type": "multipart/form-data"}, b"--x\r\nkaputt"),
        ({"Content-Type": "multipart/form-data; boundary=x"}, b"--x--\r\n"),
        ({}, b""),
    ],
)
def test_kaputte_anfragen_400(make_session, tmp_path, token, kopf, inhalt):
    r = _client(make_session, tmp_path).post(
        "/belege", content=inhalt, headers={**_auth(token), **kopf}
    )
    assert r.status_code == 400, r.text
    assert r.json()["fehler"]


def test_zu_gross_413(make_session, tmp_path, token):
    c = _client(make_session, tmp_path, max_anfrage_mb=0.01)  # ≈ 10 KB
    gross = PDF + b"x" * 20_000
    r = c.post("/belege", content=gross, headers=_auth(token))
    assert r.status_code == 413

    def gestreamt():
        for _ in range(30):
            yield b"x" * 1000

    r = c.post("/belege", content=gestreamt(), headers=_auth(token))
    assert r.status_code == 413
    # Datei über der Dateigrenze (max_bytes 10 000), Anfrage darunter
    c = _client(make_session, tmp_path)
    r = c.post("/belege", content=PDF + b"x" * 12_000, headers=_auth(token))
    assert r.status_code == 413
    assert "höchstens" in r.json()["fehler"]
    with make_session() as s:
        assert lade_belege(s) == []


def test_zu_viele_dateien_413(make_session, tmp_path, token):
    c = _client(make_session, tmp_path, max_dateien=1)
    r = c.post(
        "/belege",
        headers=_auth(token),
        files=[
            ("datei", ("a.pdf", PDF, "application/pdf")),
            ("datei", ("b.pdf", PDF + b"b", "application/pdf")),
        ],
    )
    assert r.status_code == 413


def test_falscher_typ_415_und_nichts_gespeichert(make_session, tmp_path, token):
    c = _client(make_session, tmp_path)
    r = c.post(
        "/belege",
        headers=_auth(token),
        files=[
            ("datei", ("ok.pdf", PDF, "application/pdf")),
            ("datei", ("makro.docm", b"PK\x03\x04", "application/pdf")),
        ],
    )
    assert r.status_code == 415
    assert "makro.docm" in r.json()["fehler"]
    with make_session() as s:
        assert lade_belege(s) == []
        assert lade_eingaenge(s) == []


def test_gleiche_datei_zweimal_ist_dublette(make_session, tmp_path, token):
    c = _client(make_session, tmp_path)
    erst = c.post("/belege", content=PDF, headers=_auth(token)).json()
    zweit = c.post("/belege", content=PDF, headers=_auth(token)).json()
    assert erst["ergebnisse"][0]["ergebnis"] == "neu"
    assert zweit["ergebnisse"][0]["ergebnis"] == "dublette"
    assert zweit["ergebnisse"][0]["beleg_id"] == erst["ergebnisse"][0]["beleg_id"]
    with make_session() as s:
        assert len(lade_belege(s)) == 1
        assert len(lade_eingaenge(s)) == 2


def test_erkenner_fehler_geht_zur_pruefung(make_session, tmp_path, token):
    def kaputt(roh, beleg):
        raise RuntimeError("OCR abgestürzt")

    c = _client(make_session, tmp_path, erkenner=kaputt)
    r = c.post("/belege", content=JPEG, headers=_auth(token))
    assert r.status_code == 200
    (e,) = r.json()["ergebnisse"]
    assert e["status"] == BelegStatus.ZUR_PRUEFUNG.value
    assert "OCR abgestürzt" in e["hinweis"]


def test_gleichzeitige_gleiche_uploads_ergeben_einen_beleg(
    make_session, tmp_path, token
):
    c = _client(make_session, tmp_path)
    with ThreadPoolExecutor(max_workers=6) as pool:
        antworten = list(
            pool.map(
                lambda _: c.post("/belege", content=PDF, headers=_auth(token)),
                range(6),
            )
        )
    assert all(a.status_code == 200 for a in antworten)
    ergebnisse = sorted(a.json()["ergebnisse"][0]["ergebnis"] for a in antworten)
    assert ergebnisse == ["dublette"] * 5 + ["neu"]
    with make_session() as s:
        assert len(lade_belege(s)) == 1
