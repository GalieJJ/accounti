"""Kleiner IMAP4rev1-Server für Tests — Klartext, SSL oder STARTTLS.

Kann genau das, was der E-Mail-Kanal braucht: CAPABILITY, STARTTLS, LOGIN,
SELECT/EXAMINE (mit UIDVALIDITY), UID SEARCH (ALL, SINCE), UID FETCH
(RFC822.SIZE, BODY.PEEK[], BODY[]), UID STORE, UID MOVE, NOOP, LOGOUT. Jeder Befehl
landet im Protokoll ``befehle`` (Passwörter nicht).
"""

from __future__ import annotations

import datetime as dt
import socket
import socketserver
import ssl
import threading
from dataclasses import dataclass, field
from pathlib import Path

_MONATE = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
           "Nov", "Dec"]  # fmt: skip


@dataclass
class Nachricht:
    uid: int
    roh: bytes
    datum: dt.date
    flags: set[str] = field(default_factory=set)


@dataclass
class Postfach:
    benutzer: str = "belege@firma.example"
    passwort: str = "geheim"
    faehigkeiten: tuple[str, ...] = ("IMAP4rev1", "MOVE")
    ordner: dict[str, list[Nachricht]] = field(default_factory=lambda: {"INBOX": []})
    uidvalidity: dict[str, int] = field(default_factory=dict)
    naechste_uid: dict[str, int] = field(default_factory=dict)
    befehle: list[str] = field(default_factory=list)

    def lege_ab(
        self,
        roh: bytes,
        ordner: str = "INBOX",
        datum: dt.date | None = None,
        flags: tuple[str, ...] = (),
    ) -> int:
        liste = self.ordner.setdefault(ordner, [])
        self.uidvalidity.setdefault(ordner, 1)
        uid = self.naechste_uid.get(ordner, 1)
        self.naechste_uid[ordner] = uid + 1
        liste.append(Nachricht(uid, roh, datum or dt.date(2026, 10, 1), set(flags)))
        return uid

    def neu_angelegt(self, ordner: str = "INBOX") -> None:
        """Ordner neu angelegt: neue UIDVALIDITY, UIDs neu vergeben."""
        self.uidvalidity[ordner] = self.uidvalidity.get(ordner, 1) + 1
        for nr, n in enumerate(self.ordner[ordner], start=1):
            n.uid = nr
        self.naechste_uid[ordner] = len(self.ordner[ordner]) + 1


def _tokens(text: str) -> list[str]:
    teile: list[str] = []
    i = 0
    while i < len(text):
        zeichen = text[i]
        if zeichen == " ":
            i += 1
        elif zeichen == '"':
            j, puffer = i + 1, []
            while text[j] != '"':
                if text[j] == "\\":
                    j += 1
                puffer.append(text[j])
                j += 1
            teile.append("".join(puffer))
            i = j + 1
        elif zeichen == "(":
            tiefe, j = 0, i
            while True:
                tiefe += {"(": 1, ")": -1}.get(text[j], 0)
                if tiefe == 0:
                    break
                j += 1
            teile.append(text[i : j + 1])
            i = j + 1
        else:
            j = text.find(" ", i)
            j = len(text) if j < 0 else j
            teile.append(text[i:j])
            i = j
    return teile


def _menge(text: str, hoechste: int) -> set[int]:
    uids: set[int] = set()
    for teil in text.split(","):
        von, _, bis = teil.partition(":")
        a = hoechste if von == "*" else int(von)
        b = a if not bis else (hoechste if bis == "*" else int(bis))
        uids.update(range(min(a, b), max(a, b) + 1))
    return uids


class _Verbindung(socketserver.BaseRequestHandler):
    server: _Server

    def setup(self) -> None:
        self.sock: socket.socket = self.request
        self.tls = False
        if self.server.modus == "ssl":
            self.sock = self.server.kontext.wrap_socket(self.sock, server_side=True)
            self.tls = True
        self.datei = self.sock.makefile("rb")
        self.angemeldet = False
        self.ordner: str | None = None
        self.nur_lesen = False

    def sende(self, zeile: bytes) -> None:
        self.sock.sendall(zeile + b"\r\n")

    def handle(self) -> None:
        pf = self.server.postfach
        self.sende(b"* OK Attrappe bereit")
        while True:
            try:
                zeile = self.datei.readline()
            except (OSError, ssl.SSLError):
                return
            if not zeile:
                return
            text = zeile.rstrip(b"\r\n").decode()
            tag, _, rest = text.partition(" ")
            befehl, _, args = rest.partition(" ")
            befehl = befehl.upper()
            if befehl == "UID":
                unter, _, args = args.partition(" ")
                befehl = f"UID {unter.upper()}"
            pf.befehle.append("LOGIN ***" if befehl == "LOGIN" else f"{befehl} {args}")
            if not self.bearbeite(tag.encode(), befehl, _tokens(args)):
                return

    # -- Befehle --------------------------------------------------------------

    def _faehigkeiten(self) -> bytes:
        teile = list(self.server.postfach.faehigkeiten)
        if self.server.modus == "starttls" and not self.tls:
            teile.append("STARTTLS")
        return " ".join(teile).encode()

    def bearbeite(self, tag: bytes, befehl: str, args: list[str]) -> bool:
        pf = self.server.postfach
        if befehl == "CAPABILITY":
            self.sende(b"* CAPABILITY " + self._faehigkeiten())
            self.sende(tag + b" OK CAPABILITY erledigt")
        elif befehl == "NOOP":
            self.sende(tag + b" OK NOOP")
        elif befehl == "LOGOUT":
            self.sende(b"* BYE Attrappe sagt tschuess")
            self.sende(tag + b" OK LOGOUT erledigt")
            return False
        elif befehl == "STARTTLS" and self.server.modus == "starttls" and not self.tls:
            self.sende(tag + b" OK TLS beginnt")
            self.sock = self.server.kontext.wrap_socket(self.sock, server_side=True)
            self.datei = self.sock.makefile("rb")
            self.tls = True
        elif befehl == "LOGIN":
            if self.server.modus == "starttls" and not self.tls:
                self.sende(tag + b" NO [PRIVACYREQUIRED] erst STARTTLS")
            elif args[:2] == [pf.benutzer, pf.passwort]:
                self.angemeldet = True
                self.sende(tag + b" OK LOGIN erledigt")
            else:
                self.sende(tag + b" NO [AUTHENTICATIONFAILED] Anmeldung fehlgeschlagen")
        elif not self.angemeldet:
            self.sende(tag + b" BAD erst anmelden")
        elif befehl in ("SELECT", "EXAMINE"):
            self.waehle(tag, befehl, args[0])
        elif self.ordner is None:
            self.sende(tag + b" BAD erst einen Ordner waehlen")
        elif befehl == "UID SEARCH":
            self.suche(tag, args)
        elif befehl == "UID FETCH":
            self.hole(tag, args[0], args[1].upper())
        elif befehl == "UID STORE":
            self.markiere(tag, args[0], args[1], args[2])
        elif befehl == "UID MOVE" and "MOVE" in pf.faehigkeiten:
            self.verschiebe(tag, args[0], args[1])
        else:
            self.sende(tag + b" BAD unbekannter Befehl")
        return True

    def _liste(self) -> list[Nachricht]:
        assert self.ordner is not None
        return self.server.postfach.ordner[self.ordner]

    def waehle(self, tag: bytes, befehl: str, ordner: str) -> None:
        pf = self.server.postfach
        if ordner not in pf.ordner:
            self.ordner = None
            self.sende(tag + b" NO [NONEXISTENT] Ordner gibt es nicht")
            return
        self.ordner = ordner
        self.nur_lesen = befehl == "EXAMINE"
        pf.uidvalidity.setdefault(ordner, 1)
        self.sende(b"* FLAGS (\\Seen \\Deleted)")
        self.sende(b"* %d EXISTS" % len(self._liste()))
        self.sende(b"* 0 RECENT")
        self.sende(b"* OK [UIDVALIDITY %d] UIDs gueltig" % pf.uidvalidity[ordner])
        self.sende(b"* OK [UIDNEXT %d] naechste UID" % pf.naechste_uid.get(ordner, 1))
        art = b"READ-ONLY" if self.nur_lesen else b"READ-WRITE"
        self.sende(tag + b" OK [" + art + b"] " + befehl.encode() + b" erledigt")

    def suche(self, tag: bytes, args: list[str]) -> None:
        treffer = self._liste()
        if args and args[0].upper() == "SINCE":
            tag_, monat, jahr = args[1].split("-")
            ab = dt.date(int(jahr), _MONATE.index(monat) + 1, int(tag_))
            treffer = [n for n in treffer if n.datum >= ab]
        elif args != ["ALL"]:
            self.sende(tag + b" BAD Suche nicht unterstuetzt")
            return
        uids = " ".join(str(n.uid) for n in treffer)
        self.sende(b"* SEARCH" + (b" " + uids.encode() if uids else b""))
        self.sende(tag + b" OK SEARCH erledigt")

    def _auswahl(self, menge: str) -> list[tuple[int, Nachricht]]:
        liste = self._liste()
        hoechste = max((n.uid for n in liste), default=0)
        uids = _menge(menge, hoechste)
        return [(nr, n) for nr, n in enumerate(liste, start=1) if n.uid in uids]

    def hole(self, tag: bytes, menge: str, teile: str) -> None:
        for nr, n in self._auswahl(menge):
            if "RFC822.SIZE" in teile:
                self.sende(
                    b"* %d FETCH (UID %d RFC822.SIZE %d)" % (nr, n.uid, len(n.roh))
                )
            elif "BODY.PEEK[]" in teile or "BODY[]" in teile:
                if "PEEK" not in teile and not self.nur_lesen:
                    n.flags.add("\\Seen")
                self.sock.sendall(
                    b"* %d FETCH (UID %d BODY[] {%d}\r\n" % (nr, n.uid, len(n.roh))
                    + n.roh
                    + b")\r\n"
                )
        self.sende(tag + b" OK FETCH erledigt")

    def markiere(self, tag: bytes, menge: str, art: str, flags: str) -> None:
        if self.nur_lesen:
            self.sende(tag + b" NO [READ-ONLY] Ordner nur lesend geoeffnet")
            return
        neue = set(flags.strip("()").split())
        for nr, n in self._auswahl(menge):
            n.flags = n.flags | neue if art.startswith("+") else n.flags - neue
            liste = " ".join(sorted(n.flags)).encode()
            self.sende(b"* %d FETCH (UID %d FLAGS (%s))" % (nr, n.uid, liste))
        self.sende(tag + b" OK STORE erledigt")

    def verschiebe(self, tag: bytes, menge: str, ziel: str) -> None:
        pf = self.server.postfach
        if self.nur_lesen:
            self.sende(tag + b" NO [READ-ONLY] Ordner nur lesend geoeffnet")
            return
        if ziel not in pf.ordner:
            self.sende(tag + b" NO [TRYCREATE] Zielordner fehlt")
            return
        for nr, n in reversed(self._auswahl(menge)):
            self._liste().remove(n)
            pf.lege_ab(n.roh, ziel, n.datum, tuple(n.flags))
            self.sende(b"* %d EXPUNGE" % nr)
        self.sende(tag + b" OK MOVE erledigt")


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self, postfach: Postfach, modus: str, kontext: ssl.SSLContext | None
    ) -> None:
        super().__init__(("127.0.0.1", 0), _Verbindung)
        self.postfach = postfach
        self.modus = modus
        self.kontext = kontext  # type: ignore[assignment]


class ImapAttrappe:
    """``with ImapAttrappe(postfach) as server: … server.port …``"""

    def __init__(
        self,
        postfach: Postfach | None = None,
        modus: str = "klartext",
        kontext: ssl.SSLContext | None = None,
    ) -> None:
        self.postfach = postfach or Postfach()
        self._server = _Server(self.postfach, modus, kontext)
        self._faden = threading.Thread(
            target=self._server.serve_forever, args=(0.02,), daemon=True
        )

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def __enter__(self) -> ImapAttrappe:
        self._faden.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._server.shutdown()
        self._server.server_close()


def zertifikate(ordner: Path) -> tuple[Path, ssl.SSLContext]:
    """Eigene CA und ein Serverzertifikat für ``localhost``.

    Gibt die CA-Datei (für ``ca_datei``) und den Serverkontext zurück.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    jetzt = dt.datetime.now(dt.UTC)
    ca_schluessel = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test-CA accounti")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_schluessel.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(jetzt - dt.timedelta(days=1))
        .not_valid_after(jetzt + dt.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_schluessel.public_key()),
            critical=False,
        )
        .sign(ca_schluessel, hashes.SHA256())
    )
    schluessel = ec.generate_private_key(ec.SECP256R1())
    zert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(ca_name)
        .public_key(schluessel.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(jetzt - dt.timedelta(days=1))
        .not_valid_after(jetzt + dt.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_schluessel.public_key()
            ),
            critical=False,
        )
        .sign(ca_schluessel, hashes.SHA256())
    )
    ca_datei = ordner / "ca.pem"
    ca_datei.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    kette = ordner / "server.pem"
    kette.write_bytes(
        zert.public_bytes(serialization.Encoding.PEM)
        + schluessel.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    kontext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    kontext.load_cert_chain(kette)
    return ca_datei, kontext
