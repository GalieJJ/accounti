"""Gemeinsame Bausteine für die Tests von Baustein 8 (Aufgaben & Rückfragen)."""

from __future__ import annotations

import json
import socketserver
import threading
from datetime import date, datetime
from decimal import Decimal
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default as standard_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from accounti.models import Buchungssatz, BuchungStatus

JETZT = datetime(2026, 10, 20, 9, 0)
HEUTE = JETZT.date()


def buchung(confidence: float = 0.62, **kw: Any) -> Buchungssatz:
    werte: dict[str, Any] = {
        "datum": date(2026, 10, 14),
        "soll_konto": "4930",
        "haben_konto": "1200",
        "betrag_netto": Decimal("84.03"),
        "steuer_schluessel": 9,
        "steuer_betrag": Decimal("15.97"),
        "buchungstext": "Bürobedarf Schreibwaren Meier",
        "status": BuchungStatus.ZUR_PRUEFUNG
        if confidence < 0.95
        else BuchungStatus.AUTO_GEBUCHT,
        "confidence": confidence,
    }
    werte.update(kw)
    return Buchungssatz(**werte)


# ---------------------------------------------------------------------------
# Lokale Gegenstellen: SMTP- und Webhook-Server auf 127.0.0.1 — nichts verlässt
# den Rechner, es wird keine echte E-Mail versendet.
# ---------------------------------------------------------------------------


class SmtpTestserver:
    """Minimaler SMTP-Server nach RFC 5321 (EHLO, MAIL, RCPT, DATA, RSET, QUIT).

    Nimmt Nachrichten an und merkt sie sich; mit ``ablehnen = True`` weist er jeden
    Empfänger mit 550 ab.
    """

    def __init__(self) -> None:
        self.nachrichten: list[tuple[str, list[str], EmailMessage]] = []
        self.ablehnen = False
        server = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                def antworte(text: str) -> None:
                    self.wfile.write(text.encode("ascii") + b"\r\n")
                    self.wfile.flush()

                absender, an = "", []
                antworte("220 accounti-test ESMTP")
                while zeile := self.rfile.readline():
                    befehl = zeile.decode("ascii", "replace").strip()
                    gross = befehl.upper()
                    if gross.startswith("EHLO"):
                        antworte("250-accounti-test")
                        antworte("250 8BITMIME")
                    elif gross == "RSET":
                        absender, an = "", []
                        antworte("250 OK")
                    elif gross.startswith("HELO") or gross == "NOOP":
                        antworte("250 OK")
                    elif gross.startswith("MAIL FROM:"):
                        absender = befehl[10:].split()[0].strip("<>")
                        antworte("250 OK")
                    elif gross.startswith("RCPT TO:"):
                        if server.ablehnen:
                            antworte("550 Postfach unbekannt")
                            continue
                        an.append(befehl[8:].split()[0].strip("<>"))
                        antworte("250 OK")
                    elif gross == "DATA":
                        antworte("354 Ende mit <CRLF>.<CRLF>")
                        roh = bytearray()
                        while (teil := self.rfile.readline()) not in (b".\r\n", b""):
                            roh += teil[1:] if teil.startswith(b"..") else teil
                        nachricht = message_from_bytes(
                            bytes(roh), policy=standard_policy
                        )
                        server.nachrichten.append((absender, an, nachricht))
                        absender, an = "", []
                        antworte("250 OK angenommen")
                    elif gross == "QUIT":
                        antworte("221 Bye")
                        return
                    else:
                        antworte("502 nicht unterstuetzt")

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
        )

    def starte(self) -> SmtpTestserver:
        self.thread.start()
        return self

    def stoppe(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class WebhookTestserver:
    """Lokaler HTTP-Server; merkt sich jeden POST, antwortet mit ``status``."""

    def __init__(self) -> None:
        self.anfragen: list[dict[str, Any]] = []
        self.status = 200
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 (http.server-Schnittstelle)
                laenge = int(self.headers.get("Content-Length", "0"))
                server.anfragen.append(
                    {
                        "pfad": self.path,
                        "typ": self.headers.get("Content-Type"),
                        "body": json.loads(self.rfile.read(laenge)),
                    }
                )
                antwort = b"ok" if server.status < 300 else b"kaputt"
                self.send_response(server.status)
                self.send_header("Content-Length", str(len(antwort)))
                self.end_headers()
                self.wfile.write(antwort)

            def log_message(self, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/hooks/geheim123"
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
        )

    def starte(self) -> WebhookTestserver:
        self.thread.start()
        return self

    def stoppe(self) -> None:
        self.server.shutdown()
        self.server.server_close()
