"""E-Mail-Kanal — Belege aus einem IMAP-Postfach.

Geholt werden nur die Anhänge, byte-genau; die E-Mail selbst ist Transportmittel
(GoBD) und wird nicht archiviert. Der Absender wird als Hinweis auf den Kreditor
gespeichert — in der Herkunft des Belegs und im Gedächtnis ``kanal_nachrichten``.

Das Postfach bleibt unberührt, solange nichts anderes eingestellt ist: Der Ordner
wird nur lesend geöffnet (EXAMINE), Nachrichten werden mit ``BODY.PEEK[]`` geladen
(setzt ``\\Seen`` nicht, RFC 9051 6.4.5). Welche Nachricht schon verarbeitet ist,
weiß das Gedächtnis: Ordner + UIDVALIDITY + UID bezeichnen eine Nachricht dauerhaft
(RFC 9051 2.3.1.1), die Message-ID fängt neu angelegte Ordner ab.
"""

from __future__ import annotations

import contextlib
import email
import email.policy
import hashlib
import imaplib
import re
import ssl
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from email.message import Message
from email.utils import parseaddr

from accounti.belege.kanaele import RohBeleg, registriere
from accounti.belege.kanaele.abholung import AbholKanal, KanalError
from accounti.belege.kanaele.einstellungen import EmailPostfach
from accounti.belege.kanaele.gedaechtnis import Gedaechtnis
from accounti.belege.kanaele.pruefung import DateiAbgelehntError, Dateipruefung
from accounti.models.kanaele import AbgeholteNachricht

KANAL = "email"
_MONATE = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
           "Nov", "Dec")  # fmt: skip
# Inhaltstypen, die auch ohne Dateinamen als Beleg gelten
_BELEG_MIME = frozenset(
    {
        "application/pdf",
        "application/xml",
        "text/xml",
        "image/jpeg",
        "image/png",
        "image/tiff",
    }
)
_GROESSEN_JE_ABRUF = 200


# ---------------------------------------------------------------------------
# Eine Nachricht lesen
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Belegdatei:
    dateiname: str
    inhalt: bytes


@dataclass
class GeleseneNachricht:
    message_id: str | None = None
    absender: str | None = None
    absender_name: str | None = None
    betreff: str | None = None
    gesendet_am: datetime | None = None
    dateien: list[Belegdatei] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)


def _kopf(nachricht: Message, name: str) -> str | None:
    try:
        wert = nachricht.get(name)
        text = str(wert).strip() if wert is not None else ""
    except (ValueError, IndexError, TypeError, AttributeError):
        return None
    return text or None


def _absender(nachricht: Message) -> tuple[str | None, str | None]:
    try:
        kopf = nachricht.get("From")
        adressen = getattr(kopf, "addresses", ())
        if adressen:
            a = adressen[0]
            return (a.addr_spec or None), (a.display_name or None)
    except (ValueError, IndexError, TypeError, AttributeError):
        pass
    name, adresse = parseaddr(_kopf(nachricht, "From") or "")
    return (adresse or None), (name or None)


def _datum(nachricht: Message) -> datetime | None:
    try:
        kopf = nachricht.get("Date")
        zeit = getattr(kopf, "datetime", None)
    except (ValueError, IndexError, TypeError, AttributeError):
        return None
    if not isinstance(zeit, datetime):
        return None
    if zeit.tzinfo is not None:
        zeit = zeit.astimezone().replace(tzinfo=None)  # Ortszeit wie im Rest
    return zeit


def _dateiname(teil: Message) -> str | None:
    try:
        return teil.get_filename()
    except (ValueError, IndexError, TypeError, AttributeError):
        return None


def _blaetter(teil: Message, eltern: str = "") -> Iterator[tuple[Message, str]]:
    """Alle Blätter des MIME-Baums mit dem Inhaltstyp ihres Elternteils."""
    if teil.is_multipart():
        unterteile = teil.get_payload()
        if isinstance(unterteile, list):
            for unter in unterteile:
                if isinstance(unter, Message):
                    yield from _blaetter(unter, teil.get_content_type())
        return
    yield teil, eltern


def lies_nachricht(roh: bytes, pruefung: Dateipruefung) -> GeleseneNachricht:
    """Absender, Betreff, Datum und Belegdateien einer E-Mail.

    Belegdatei ist jeder MIME-Teil mit Dateinamen oder mit einem Belegtyp — auch in
    weitergeleiteten Nachrichten. Textkörper und eingebettete Bilder (``inline`` mit
    Content-ID, z.B. das Logo in der Signatur) sind keine Belege. Was die
    Dateiprüfung ablehnt, wird als Hinweis vermerkt, nicht still verworfen.
    """
    nachricht = email.message_from_bytes(roh, policy=email.policy.default)
    absender, absender_name = _absender(nachricht)
    gelesen = GeleseneNachricht(
        message_id=_kopf(nachricht, "Message-ID"),
        absender=absender,
        absender_name=absender_name,
        betreff=_kopf(nachricht, "Subject"),
        gesendet_am=_datum(nachricht),
    )
    nr = 0
    for teil, eltern in _blaetter(nachricht):
        dateiname = _dateiname(teil)
        typ = teil.get_content_type()
        disposition = teil.get_content_disposition()
        if dateiname is None and disposition != "attachment" and typ not in _BELEG_MIME:
            continue  # Textkörper
        eingebettet = disposition == "inline" or eltern == "multipart/related"
        if eingebettet and teil.get("Content-ID") and typ.startswith("image/"):
            continue  # im HTML eingebettetes Bild, z.B. Logo der Signatur
        nr += 1
        inhalt = teil.get_payload(decode=True)
        if not isinstance(inhalt, bytes):
            continue
        try:
            name = pruefung.pruefe(dateiname or f"anhang-{nr}", inhalt)
        except DateiAbgelehntError as fehler:
            gelesen.hinweise.append(f"übersprungen: {fehler}")
            continue
        gelesen.dateien.append(Belegdatei(name, inhalt))
    return gelesen


# ---------------------------------------------------------------------------
# IMAP
# ---------------------------------------------------------------------------


def _quote(ordner: str) -> str:
    return '"' + ordner.replace("\\", "\\\\").replace('"', '\\"') + '"'


def oeffne_imap(p: EmailPostfach) -> imaplib.IMAP4:
    """Verbindung aufbauen; bei TLS mit Prüfung von Zertifikat und Hostname."""
    port = p.port_oder_standard
    if p.verschluesselung == "keine":
        return imaplib.IMAP4(p.host, port, timeout=p.timeout_sekunden)
    kontext = ssl.create_default_context(cafile=p.ca_datei)
    if p.verschluesselung == "ssl":
        return imaplib.IMAP4_SSL(
            p.host, port, ssl_context=kontext, timeout=p.timeout_sekunden
        )
    imap = imaplib.IMAP4(p.host, port, timeout=p.timeout_sekunden)
    imap.starttls(ssl_context=kontext)
    return imap


def _imap_datum(tag: date) -> str:
    return f"{tag.day:02d}-{_MONATE[tag.month - 1]}-{tag.year}"


def _text(wert: object) -> str:
    if isinstance(wert, bytes):
        return wert.decode("utf-8", "replace")
    return str(wert)


@registriere
class EmailKanal(AbholKanal):
    """Holt die Anhänge neuer Nachrichten eines IMAP-Ordners."""

    name = KANAL
    beschreibung = (
        "IMAP-Postfach; Anhänge werden gezogen, der Absender als Hinweis gespeichert"
    )

    def __init__(
        self,
        postfach: EmailPostfach,
        passwort: str | Callable[[], str],
        gedaechtnis: Gedaechtnis,
        pruefung: Dateipruefung | None = None,
        verbinde: Callable[[EmailPostfach], imaplib.IMAP4] = oeffne_imap,
    ) -> None:
        super().__init__(f"E-Mail {postfach.name} ({postfach.benutzer})")
        self.postfach = postfach
        self._passwort = passwort
        self.gedaechtnis = gedaechtnis
        self.pruefung = pruefung or Dateipruefung()
        self._verbinde = verbinde
        self._bestaetigt: set[int] = set()

    # -- BelegKanal -----------------------------------------------------------

    def abholen(self) -> Iterator[RohBeleg]:
        p = self.postfach
        passwort = self._passwort() if callable(self._passwort) else self._passwort
        try:
            imap = self._verbinde(p)
        except (imaplib.IMAP4.error, OSError) as fehler:
            msg = (
                f"Verbindung zu {p.host}:{p.port_oder_standard} "
                f"({p.verschluesselung}) gescheitert: {fehler}"
            )
            raise KanalError(msg) from fehler
        try:
            yield from self._hole(imap, passwort)
        except (imaplib.IMAP4.error, OSError) as fehler:
            msg = f"Postfach {p.name}: {fehler}"
            raise KanalError(msg) from fehler
        finally:
            with contextlib.suppress(imaplib.IMAP4.error, OSError):
                imap.logout()

    def bestaetige(self, roh: RohBeleg) -> None:
        self._bestaetigt.add(id(roh))

    # -- Ablauf ---------------------------------------------------------------

    def _anmelden(self, imap: imaplib.IMAP4, passwort: str) -> set[str]:
        p = self.postfach
        try:
            imap.login(p.benutzer, passwort)
        except imaplib.IMAP4.error as fehler:
            msg = (
                f"Anmeldung am Postfach {p.name} ({p.benutzer}@{p.host}) "
                f"fehlgeschlagen: {_text(fehler)}"
            )
            raise KanalError(msg) from None
        except UnicodeEncodeError:
            msg = (
                f"Postfach {p.name}: Benutzer oder Passwort enthält Nicht-ASCII-Zeichen"
            )
            raise KanalError(msg) from None
        typ, daten = imap.capability()
        return set(_text(daten[0]).upper().split()) if typ == "OK" and daten else set()

    def _uidvalidity(self, imap: imaplib.IMAP4) -> str:
        _, werte = imap.response("UIDVALIDITY")
        if werte and werte[0]:
            return _text(werte[0])
        typ, daten = imap.status(_quote(self.postfach.ordner), "(UIDVALIDITY)")
        treffer = re.search(r"UIDVALIDITY (\d+)", _text(daten[0])) if daten else None
        return treffer.group(1) if typ == "OK" and treffer else "0"

    def _groessen(self, imap: imaplib.IMAP4, uids: list[str]) -> dict[str, int]:
        groessen: dict[str, int] = {}
        for i in range(0, len(uids), _GROESSEN_JE_ABRUF):
            teil = uids[i : i + _GROESSEN_JE_ABRUF]
            typ, daten = imap.uid("FETCH", ",".join(teil), "(RFC822.SIZE)")
            if typ != "OK":
                continue
            for eintrag in daten:
                text = _text(eintrag[0] if isinstance(eintrag, tuple) else eintrag)
                uid = re.search(r"UID (\d+)", text)
                groesse = re.search(r"RFC822\.SIZE (\d+)", text)
                if uid and groesse:
                    groessen[uid.group(1)] = int(groesse.group(1))
        return groessen

    def _lade(self, imap: imaplib.IMAP4, uid: str) -> bytes | None:
        typ, daten = imap.uid("FETCH", uid, "(BODY.PEEK[])")
        if typ != "OK":
            return None
        for eintrag in daten:
            if isinstance(eintrag, tuple) and b"BODY[]" in eintrag[0].upper():
                inhalt = eintrag[1]
                return inhalt if isinstance(inhalt, bytes) else None
        return None

    def _merke(
        self,
        schluessel: str,
        gelesen: GeleseneNachricht | None = None,
        rohbelege: list[RohBeleg] | None = None,
        hinweis: str | None = None,
    ) -> None:
        g = gelesen or GeleseneNachricht()
        self.gedaechtnis.merke(
            AbgeholteNachricht(
                kanal=KANAL,
                quelle=self.postfach.name,
                schluessel=schluessel,
                message_id=g.message_id,
                absender=g.absender,
                absender_name=g.absender_name,
                betreff=g.betreff,
                gesendet_am=g.gesendet_am,
                datei_hashes=[
                    hashlib.sha256(r.inhalt).hexdigest() for r in rohbelege or []
                ],
                hinweis=hinweis,
            )
        )

    def _hinweis(self, uid: str, gelesen: GeleseneNachricht | None, text: str) -> str:
        von = f" von {gelesen.absender}" if gelesen and gelesen.absender else ""
        meldung = f"{self.postfach.name}: Nachricht UID {uid}{von}: {text}"
        self.hinweise.append(meldung)
        return text

    def _herkunft(self, g: GeleseneNachricht) -> str:
        herkunft = (
            f"E-Mail {self.postfach.name} von {g.absender or 'unbekannt'}: "
            f"{g.betreff or '(ohne Betreff)'}"
        )
        return herkunft[:500]

    def _nachbehandeln(self, imap: imaplib.IMAP4, uid: str) -> None:
        p = self.postfach
        if p.nach_abholen == "gelesen":
            typ, daten = imap.uid("STORE", uid, "+FLAGS", "(\\Seen)")
        elif p.nach_abholen == "verschieben" and p.ziel_ordner:
            typ, daten = imap.uid("MOVE", uid, _quote(p.ziel_ordner))
        else:
            return
        if typ != "OK":
            self._hinweis(uid, None, f"{p.nach_abholen} gescheitert: {daten}")

    def _hole(self, imap: imaplib.IMAP4, passwort: str) -> Iterator[RohBeleg]:
        p = self.postfach
        faehigkeiten = self._anmelden(imap, passwort)
        if p.nach_abholen == "verschieben" and "MOVE" not in faehigkeiten:
            msg = (
                f"Postfach {p.name}: Der Server kann kein MOVE (RFC 6851) — "
                "nach_abholen 'gelesen' oder 'belassen' verwenden"
            )
            raise KanalError(msg)
        typ, daten = imap.select(
            _quote(p.ordner), readonly=p.nach_abholen == "belassen"
        )
        if typ != "OK":
            msg = (
                f"Postfach {p.name}: Ordner {p.ordner} nicht gefunden ({_text(daten)})"
            )
            raise KanalError(msg)
        uidvalidity = self._uidvalidity(imap)
        kriterien = ["ALL"] if p.ab is None else ["SINCE", _imap_datum(p.ab)]
        typ, daten = imap.uid("SEARCH", *kriterien)
        if typ != "OK":
            msg = f"Postfach {p.name}: Suche gescheitert ({_text(daten)})"
            raise KanalError(msg)
        uids = _text(daten[0]).split() if daten and daten[0] else []

        def schluessel(uid: str) -> str:
            return f"{p.ordner}:{uidvalidity}:{uid}"

        neu = [
            u
            for u in uids
            if not self.gedaechtnis.bekannt(KANAL, p.name, schluessel(u))
        ]
        groessen = self._groessen(imap, neu)
        for uid in neu:
            groesse = groessen.get(uid)
            if groesse is not None and groesse > p.max_nachricht_bytes:
                text = (
                    f"Nachricht zu groß ({groesse / 1024 / 1024:.1f} MB, erlaubt "
                    f"{p.max_nachricht_mb:g} MB) — nicht abgeholt"
                )
                self._merke(schluessel(uid), hinweis=self._hinweis(uid, None, text))
                continue
            roh = self._lade(imap, uid)
            if roh is None:
                self._hinweis(uid, None, "konnte nicht geladen werden")
                continue
            gelesen = lies_nachricht(roh, self.pruefung)
            if gelesen.message_id and self.gedaechtnis.bekannt(
                KANAL, p.name, schluessel(uid), gelesen.message_id
            ):
                text = (
                    f"Message-ID {gelesen.message_id} schon verarbeitet — übersprungen"
                )
                self._merke(
                    schluessel(uid), gelesen, hinweis=self._hinweis(uid, gelesen, text)
                )
                continue
            rohbelege = [
                RohBeleg(
                    dateiname=d.dateiname,
                    inhalt=d.inhalt,
                    kanal=KANAL,
                    herkunft=self._herkunft(gelesen),
                )
                for d in gelesen.dateien
            ]
            yield from rohbelege
            if not all(id(r) in self._bestaetigt for r in rohbelege):
                continue  # nicht aufgenommen → beim nächsten Lauf erneut
            hinweise = list(gelesen.hinweise)
            if not rohbelege:
                hinweise.insert(0, "keine Belegdatei")
            for h in hinweise:
                self._hinweis(uid, gelesen, h)
            self._merke(
                schluessel(uid), gelesen, rohbelege, "; ".join(hinweise) or None
            )
            self._nachbehandeln(imap, uid)
