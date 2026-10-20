import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from accounti.kontakte.ustid import EvatrClient, HttpAntwort, UstIdError


class EvatrAttrappe:
    """Lokaler Server mit vorbereiteten Antworten; merkt sich jede Anfrage."""

    def __init__(self) -> None:
        self.antworten: list[tuple[int, str, float]] = []
        self.anfragen: list[dict[str, object]] = []
        attrappe = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 (http.server-Schnittstelle)
                laenge = int(self.headers.get("Content-Length", "0"))
                attrappe.anfragen.append(
                    {
                        "pfad": self.path,
                        "typ": self.headers.get("Content-Type"),
                        "body": json.loads(self.rfile.read(laenge)),
                    }
                )
                status, text, warten = attrappe.antworten.pop(0)
                time.sleep(warten)
                daten = text.encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=UTF-8")
                self.send_header("Content-Length", str(len(daten)))
                self.end_headers()
                self.wfile.write(daten)

            def log_message(self, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/app/v1/abfrage"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def antworte(self, status: int, body: dict[str, str], warten: float = 0) -> None:
        self.antworten.append((status, json.dumps(body), warten))


@pytest.fixture
def evatr():
    attrappe = EvatrAttrappe()
    attrappe.thread.start()
    yield attrappe
    attrappe.server.shutdown()
    attrappe.server.server_close()


ANFRAGE = {"anfragendeUstid": "DE123456789", "angefragteUstid": "ATU12345678"}


def test_gueltige_abfrage(evatr):
    body = {"id": "x1", "anfrageZeitpunkt": "2026-10-20T15:36:40+02:00"}
    evatr.antworte(200, {**body, "status": "evatr-0000"})
    antwort = EvatrClient(evatr.url).sende(ANFRAGE)
    assert antwort.status == 200
    assert json.loads(antwort.text)["status"] == "evatr-0000"
    (anfrage,) = evatr.anfragen
    assert anfrage["pfad"] == "/app/v1/abfrage"
    assert anfrage["typ"] == "application/json"
    assert anfrage["body"] == ANFRAGE


@pytest.mark.parametrize(
    ("http", "status"), [(404, "evatr-2001"), (400, "evatr-0005"), (503, "evatr-1001")]
)
def test_fehlerantworten_kommen_mit_body_zurueck(evatr, http, status):
    evatr.antworte(http, {"id": "x2", "status": status})
    antwort = EvatrClient(evatr.url).sende(ANFRAGE)
    assert antwort == HttpAntwort(http, json.dumps({"id": "x2", "status": status}))


def test_keine_verbindung():
    with socket.socket() as frei:
        frei.bind(("127.0.0.1", 0))
        port = frei.getsockname()[1]
    with pytest.raises(OSError):
        EvatrClient(f"http://127.0.0.1:{port}/app/v1/abfrage", timeout=2).sende(ANFRAGE)


def test_zeitueberschreitung(evatr):
    evatr.antworte(200, {"status": "evatr-0000"}, warten=1.0)
    with pytest.raises(OSError):
        EvatrClient(evatr.url, timeout=0.2).sende(ANFRAGE)


def test_nur_http_und_https():
    with pytest.raises(UstIdError, match="http"):
        EvatrClient("file:///etc/passwd")
