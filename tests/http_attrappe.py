"""Kleiner HTTP-Server für Tests — Routen sind Funktionen, Anfragen im Protokoll."""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit


@dataclass
class Anfrage:
    pfad: str
    parameter: dict[str, str]
    kopfzeilen: dict[str, str]


Antwort = tuple[int, dict[str, str], bytes]
Route = Callable[[Anfrage], Antwort]


def json_antwort(daten: Any, status: int = 200) -> Antwort:
    return status, {"Content-Type": "application/json"}, json.dumps(daten).encode()


def datei_antwort(inhalt: bytes, typ: str = "application/pdf") -> Antwort:
    return 200, {"Content-Type": typ}, inhalt


class HttpAttrappe:
    def __init__(self, routen: dict[str, Route] | None = None) -> None:
        self.routen: dict[str, Route] = dict(routen or {})
        self.anfragen: list[Anfrage] = []
        attrappe = self

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                teile = urlsplit(self.path)
                anfrage = Anfrage(
                    teile.path,
                    {k: v[0] for k, v in parse_qs(teile.query).items()},
                    {k.lower(): v for k, v in self.headers.items()},
                )
                attrappe.anfragen.append(anfrage)
                route = attrappe.routen.get(teile.path)
                status, kopf, inhalt = (
                    route(anfrage) if route else (404, {}, b'{"fehler": "unbekannt"}')
                )
                self.send_response(status)
                for name, wert in kopf.items():
                    self.send_header(name, wert)
                self.send_header("Content-Length", str(len(inhalt)))
                self.end_headers()
                self.wfile.write(inhalt)

            def log_message(self, *_: Any) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._faden = threading.Thread(
            target=self._server.serve_forever, args=(0.02,), daemon=True
        )

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> HttpAttrappe:
        self._faden.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._server.shutdown()
        self._server.server_close()


class RohAttrappe:
    """Server, der auf jede Anfrage genau ``antwort`` schickt und die Verbindung
    schließt — für abgebrochene Antworten (zu kurz, kaputtes chunked)."""

    def __init__(self, antwort: bytes = b"") -> None:
        self.antwort = antwort
        self.anfragen: list[bytes] = []
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self._sock.settimeout(0.05)
        self._stopp = threading.Event()
        self._faden = threading.Thread(target=self._lauf, daemon=True)

    def _lauf(self) -> None:
        while not self._stopp.is_set():
            try:
                verbindung, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with verbindung:
                verbindung.settimeout(2)
                kopf = b""
                while b"\r\n\r\n" not in kopf:
                    teil = verbindung.recv(4096)
                    if not teil:
                        break
                    kopf += teil
                self.anfragen.append(kopf)
                verbindung.sendall(self.antwort)

    @property
    def port(self) -> int:
        return int(self._sock.getsockname()[1])

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> RohAttrappe:
        self._faden.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stopp.set()
        self._faden.join(timeout=2)
        self._sock.close()
