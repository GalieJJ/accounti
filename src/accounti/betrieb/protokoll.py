"""Protokollierung ohne personenbezogene Inhalte und ohne Zugangsdaten.

Zwei Schichten: Der Code schreibt keine Belegtexte, Namen, Passwörter oder Token
ins Protokoll (das Zugriffsprotokoll der App enthält nur Methode, Pfad ohne Abfrage,
Status, Dauer). Zusätzlich schwärzt ein Filter an jedem Handler, was als Muster
erkennbar ist: IBAN, E-Mail-Adressen, accounti-Token, Bearer-Token und verbreitete
Zugangstoken, Benutzer und Passwort in URLs (auch zerschnitten), Geheimnis-Parameter
(``passwort=…``, ``token=…``), „Passwort: …“ sowie PIN und TAN als Zahl. Namen erkennt
kein Muster — sie dürfen gar nicht erst geschrieben werden. Wer eine Adresse nennen
muss (Webhook, Connector), nennt nur ``rechner_der_adresse``.

Stufe und Format aus ``ACCOUNTI_PROTOKOLL_STUFE`` (``INFO``) und
``ACCOUNTI_PROTOKOLL_FORMAT`` (``text`` oder ``json``).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from bisect import bisect_left, bisect_right
from typing import IO

# Zugangsdaten stehen hinter „://“ — gleich, was davor steht: Die Muster beginnen an
# „://“, nicht am Anfang des Schemas. Ein Schema-Anfang probierte jede Stelle einer
# langen Zeichenfolge bis zu ihrem Ende (quadratisch, Runde 8, g7w DoS-1), begrenzt auf
# 41 Buchstaben übersah es ein Schema hinter 42 Buchstaben ohne Trenner (Folgepaket F,
# g8w B8-3)
_SCHEMA = r"://"
# Zeichen einer E-Mail-Adresse vor dem „@“ bzw. des Rests einer zerschnittenen Adresse
_LOKAL = r"\w.+\-#?%!$&*=^~"
# Leerraum zwischen Schlüsselwort und Wert („Passwort:  …“, „PIN\n4711“), possessiv:
# Mit ``\s*`` probierte das PIN-Muster jede Aufteilung einer langen Leerraumfolge
# (quadratisch, Folgepaket F, g8w B8-1), begrenzt auf 40 Zeichen blieb ein Wert
# dahinter ungeschwärzt (F Runde 2, gf-betrieb F-B2) — ``\s*+`` gibt nichts zurück
_ABSTAND = r"\s*+"
# Teil einer Adresse zwischen „://“ und „:“ (ohne Punkt: ``_RECHNERTEIL``) und ein Port
# 1–65535 ohne führende Null
_HOSTTEIL = r"[^/\s:@?#\[\]]"
_RECHNERTEIL = r"[^/\s:@?#\[\].]"
_PORT = r"(?:6553[0-5]|655[0-2]\d|65[0-4]\d\d|6[0-4]\d{3}|[1-5]\d{4}|[1-9]\d{0,3})"
_MUSTER: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"accounti_(?:api|wh)_[A-Za-z0-9_\-]+"), "[Token]"),
    # verbreitete Zugangstoken (GitHub, GitLab, Slack) — auch ohne „token=“
    (
        re.compile(
            r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
            r"glpat-[A-Za-z0-9_\-]{20,}|xox[abeprs]-[A-Za-z0-9\-]{10,})"
        ),
        "[Token]",
    ),
    (re.compile(r"(?i)\bbearer\s++[A-Za-z0-9._~+/=\-]+"), "Bearer [Token]"),
    # Zugangsdaten jeder URL (scheme://benutzer:passwort@): die ganze userinfo, auch
    # mit unkodiertem # oder ? im Passwort (Runde 6, g5w-konten N1)
    (re.compile(rf"({_SCHEMA})[^/\s@]+@"), r"\1***@"),
    # … auch mit unkodiertem „/“ im Passwort („benutzer:4711/Sonne@rechner“): ein „@“
    # im ersten Pfadabschnitt hinter „benutzer:…“ (Runde 8, g7w B7-2; „/@kanal“ und ein
    # „@“ weiter hinten im Pfad bleiben Pfad)
    (re.compile(rf"({_SCHEMA})[^/\s@:]*:[^/\s@]*/[^/\s@]+@"), r"\1***@"),
    # … und abgeschnitten (Zeilenumbruch, kaputte Adresse): „scheme://benutzer:etwas“
    # ohne @ — außer einem Port: Ziffern bis 65535 hinter einem Rechner (mit Punkt —
    # auch IPv4 — oder localhost) vor „/“, Leerraum, Ende, einer Abfrage („?x=1“, „?“)
    # oder „#/“ (Runde 8, g7w B7-3). Ohne Rechner ist „alarm:4711?x=Sonne“ ein Passwort
    # (Folgepaket F, g8w B8-2), ebenso „:4711#Sonne“ und „:4711?Sonne“ (Runde 7, g6w
    # B-2). Die Gruppe ist atomar: Ein Port hinter einem Rechner fällt nicht auf die
    # zweite Lesart zurück
    (
        re.compile(
            rf"({_SCHEMA}(?>(?P<rechner>{_RECHNERTEIL}*\.{_HOSTTEIL}*|"
            rf"(?i:localhost)(?=:))|{_HOSTTEIL}+)):"
            rf"(?(rechner)(?!{_PORT}(?:[/\s]|$|\?(?:[^\s#/=]*=|[\s#/]|$)|#(?:[/\s]|$))))"
            r"[^/\s@]+"
        ),
        r"\1:***",
    ),
    (
        re.compile(
            r"(?i)\b(passwor[td]|pin|tan|token|secret|geheimnis|schluessel|key|"
            r"einmalcode|code|csrf|anmeldung)=([^&\s\"']+)"
        ),
        r"\1=***",
    ),
    # „Passwort: …“, „Kennwort = …“ (Text statt Parameter)
    (
        re.compile(
            rf"(?i)\b(passwor[td]|kennwort|secret|geheimnis)({_ABSTAND}[:=]{_ABSTAND})"
            r"[^\s\"',;]+"
        ),
        r"\1\2***",
    ),
    # PIN und TAN als Zahl („PIN: 12345“, „TAN 123456“)
    (
        re.compile(rf"(?i)\b(pin|tan)({_ABSTAND}(?:[:=]{_ABSTAND})?)\d{{4,8}}\b"),
        r"\1\2***",
    ),
    # E-Mail — und der Rest einer zerschnittenen Adresse („…geheim@host“); beginnt nur
    # am Anfang einer solchen Zeichenfolge, nicht an jeder ihrer Stellen (DoS-1). Ein
    # „wort:“ davor gehört nur dazu, wenn ein Passwortzeichen folgt
    # („benutzer:4711#Sonne@host“ ohne Schema) — „Empfänger:max@firma.de“ behält
    # „Empfänger:“, „Uhrzeit 10:30@…“ die Stunde (Runde 8, g7w B7-3)
    (
        re.compile(
            rf"(?<![{_LOKAL}])(?:[\w.+\-]+:(?=[\w.+\-]*[#?%!$&*=^~]))?"
            rf"[{_LOKAL}]+@[\w\-]+(?:\.[\w\-]+)+"
        ),
        "[E-Mail]",
    ),
    (
        re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,3})?\b"),
        "[IBAN]",
    ),
]


# Zeilen über ZEILE_HOECHSTENS Zeichen verlieren vor den Mustern ihre Mitte (zweite
# Ebene gegen DoS-1): höchstens RAND Zeichen vorn und hinten bleiben. Geschwärzt wird
# jedes Stück mit VORLAUF Zeichen über die Schnittkante hinaus, erst danach wird an ihr
# geschnitten — ein Schlüsselwort vor der Kante findet so seinen Wert dahinter
# (Folgepaket F, g8w B8-1)
ZEILE_HOECHSTENS = 4000
_RAND = 1500
_VORLAUF = 250
_LEER = re.compile(r"\s")


def _mit_herkunft(text: str) -> tuple[str, list[int]]:
    """``text`` geschwärzt (``_MUSTER``) — und je Zeichen des Ergebnisses die Stelle in
    ``text``, aus der es stammt (die eines Ersatzes: der Anfang seines Treffers; die
    Folge steigt nie)."""
    herkunft = list(range(len(text)))
    for muster, ersatz in _MUSTER:
        teile: list[str] = []
        neu: list[int] = []
        pos = 0
        for treffer in muster.finditer(text):
            anfang, ende = treffer.span()
            geschwaerzt = treffer.expand(ersatz)
            teile += [text[pos:anfang], geschwaerzt]
            neu += herkunft[pos:anfang] + [herkunft[anfang]] * len(geschwaerzt)
            pos = ende
        if teile:
            text = "".join([*teile, text[pos:]])
            herkunft = neu + herkunft[pos:]
    return text, herkunft


def _vor_dem_abstand(zeile: str, stelle: int) -> int:
    """Anfang der Folge aus Leerraum, „:“ und „=“, die bis ``stelle`` reicht (sonst
    ``stelle``) — dort, wo ein Abstand (``_ABSTAND``) sein Schlüsselwort hat."""
    while stelle > 0 and (zeile[stelle - 1].isspace() or zeile[stelle - 1] in ":="):
        stelle -= 1
    return stelle


def _ohne_mitte(zeile: str) -> str:
    """Kürzen ohne ein angeschnittenes Geheimnis stehen zu lassen: Die Schnittkanten
    liegen auf Leerraum (der Anfang endet vor dem letzten in den ersten ``_RAND``
    Zeichen, das Ende beginnt nach dem ersten in den letzten). Jedes Stück wird mit
    ``_VORLAUF`` Zeichen über seine Kante hinaus geschwärzt und erst dann geschnitten:
    Ein Treffer, der vor der Kante beginnt, bleibt vorn geschwärzt stehen und fällt
    hinten ganz weg — ein Wert hinter der Kante verliert nie sein Schlüsselwort
    („Bearer“, „passwort:“, „PIN“, eine IBAN mit Leerzeichen). Der Vorlauf des Endes
    reicht über einen Abstand (Leerraum, „:“, „=“ — beliebig lang), in dem er beginnt,
    bis ``_VORLAUF`` Zeichen vor diesen (F Runde 2, gf-betrieb F-B2: „PIN“, 300
    Leerzeichen, Wert hinter der Kante). Die Mitte erscheint nicht."""
    kante = max((m.start() for m in _LEER.finditer(zeile, 0, _RAND)), default=0)
    text, herkunft = _mit_herkunft(zeile[: kante + _VORLAUF])
    kopf = text[: bisect_left(herkunft, kante)].rstrip()
    weiter = _LEER.search(zeile, len(zeile) - _RAND)
    ende = ""
    if weiter is not None:
        start = max(weiter.start() - _VORLAUF, 0)
        start = max(_vor_dem_abstand(zeile, start) - _VORLAUF, 0)
        text, herkunft = _mit_herkunft(zeile[start:])
        ende = text[bisect_right(herkunft, weiter.start() - start) :].lstrip()
    return f"{kopf} … [gekürzt] … {ende}".strip()


def schwaerze(text: str) -> str:
    """Der Text ohne erkennbare Geheimnisse und Personendaten; eine Zeile über
    ``ZEILE_HOECHSTENS`` Zeichen ohne ihre Mitte (``_ohne_mitte``)."""
    if len(text) > ZEILE_HOECHSTENS:
        text = "\n".join(
            _ohne_mitte(z) if len(z) > ZEILE_HOECHSTENS else z for z in text.split("\n")
        )
    for muster, ersatz in _MUSTER:
        text = muster.sub(ersatz, text)
    return text


# Rechnername: Buchstaben (auch Umlaute, IDN wie „bücher.example“; Runde 8, g7w B7-1),
# Ziffern, „.“, „_“, „~“, „-“ — oder IPv6 in Klammern
_RECHNER = re.compile(r"[\w.~\-]+|\[[0-9A-Za-z:.%]+\]")


def _rechner_und_port(teil: str) -> tuple[str, str | None] | None:
    """„rechner[:port]“ zerlegt — ``None``, wenn kein Rechner zu erkennen ist; ein
    Port, der keiner ist (Text, 0, über 65535), fällt weg."""
    if teil.startswith("["):
        rechner, zu, rest = teil.partition("]")
        if not zu:
            return None  # „[::1“ ohne Klammer zu (Tippfehler)
        rechner += "]"
        port = rest[1:] if rest.startswith(":") else None
        if rest and port is None:
            return None
    else:
        rechner, trenner, port_text = teil.partition(":")
        port = port_text if trenner else None
    if not _RECHNER.fullmatch(rechner):
        return None
    if port is not None and not (port.isascii() and port.isdigit()):
        return rechner, None
    if port is not None and not 0 < int(port) <= 65535:
        return rechner, None
    return rechner, port


def _hinter_zugangsdaten(vorn: str, hinten: str) -> str | None:
    """Der Rechner hinter Zugangsdaten mit unkodiertem „#“, „?“ oder „/“ im Passwort
    („benutzer:4711#Sonne@rechner“): ``vorn`` ist der Teil vor dem ersten dieser
    Zeichen, ``hinten`` der Rest ab ihm. Steht im Abschnitt dahinter — bis zum nächsten
    „/“, nach einem „/“ bis zum nächsten „/“, „?“ oder „#“ — ein „@“ (nach einem „/“
    mit Text davor: „/@kanal“ ist Pfad), folgt der Rechner dem letzten „@“ dort. Sonst,
    wenn ``vorn`` nicht „rechner:port“ ist („benutzer:pa/s/s@rechner“), dem letzten
    „@“ überhaupt. ``None``: keine Zugangsdaten zu erkennen."""
    if ":" not in vorn or not hinten:
        return None
    zeichen, inhalt = hinten[0], hinten[1:]
    abschnitt = re.split(r"[/?#]" if zeichen == "/" else "/", inhalt, maxsplit=1)[0]
    zugang, at, rechner = abschnitt.rpartition("@")
    if not at or (zeichen == "/" and not zugang):
        sauber = _rechner_und_port(vorn)
        if (sauber is not None and sauber[1] is not None) or "@" not in hinten:
            return None
        rechner = hinten.rpartition("@")[2]
    return re.split(r"[/?#]", rechner, maxsplit=1)[0]


# statt eines Rechners, wenn die Adresse zwei Lesarten hat (``rechner_der_adresse``)
MEHRDEUTIGE_ADRESSE = (
    "(Adresse nicht eindeutig – @ # ? / im Passwort prozentkodieren: %40 %23 %3F %2F)"
)


def _mehrdeutig(rest: str) -> bool:
    """Zugangsdaten „benutzer:…@“ vor einem „#“ oder „?“ und dahinter (bis zum ersten
    „/“) ein weiteres „@“: „alarm:Son@ne#x@rechner.example“ ist ein Passwort „Son“ mit
    Rechner „ne“ und Fragment — oder ein Passwort „Son@ne#x“ mit Rechner
    „rechner.example“. Welche Lesart gemeint ist, lässt sich nicht erkennen."""
    bis_pfad = rest.split("/", 1)[0]
    trenner = re.search(r"[?#]", bis_pfad)
    if trenner is None:
        return False
    vorn, hinten = bis_pfad[: trenner.start()], bis_pfad[trenner.start() :]
    zugang = vorn.rpartition("@")[0]
    return ":" in zugang and "@" in hinten


def rechner_der_adresse(adresse: str) -> str | None:
    """„schema://rechner[:port]“ einer Adresse — ohne Benutzer, Passwort, Pfad und
    Abfrage (die tragen oft ein Geheimnis). Zugangsdaten stehen vor dem ersten „/“, „?“
    oder „#“ und enden am letzten „@“ dort; ein „@“ in Abfrage oder Fragment ist keine
    Zugangsangabe („https://rechner?an=jan@firma.example“; Runde 8, g7w B7-1). Robust
    gegen ein unkodiertes #, ? oder / im Passwort (``urlsplit`` machte dort den
    Passwortanfang zum Rechner und seine Ziffern zum Port, Runde 7, g6w B-2; Runde 8,
    g7w B7-2): ``_hinter_zugangsdaten``. Im Zweifel ohne Port. ``None``, wenn die
    Adresse keinen Rechner erkennen lässt; ``MEHRDEUTIGE_ADRESSE``, wenn sie zwei
    Lesarten hat (``_mehrdeutig``) — dann nennt sie keinen geratenen Rechner, der ein
    Teil des Passworts sein könnte (Folgepaket F, g8w B8-4)."""
    schema, trenner, rest = adresse.strip().partition("://")
    if not trenner or not re.fullmatch(r"[A-Za-z][A-Za-z0-9+.\-]*", schema):
        return None
    vorn = re.split(r"[/?#]", rest, maxsplit=1)[0]
    if "@" in vorn:
        if _mehrdeutig(rest):
            return MEHRDEUTIGE_ADRESSE
        vorn = vorn.rpartition("@")[2]
    elif (rechner := _hinter_zugangsdaten(vorn, rest[len(vorn) :])) is not None:
        vorn = rechner
    zerlegt = _rechner_und_port(vorn)
    if zerlegt is None:
        return None
    rechner, port = zerlegt
    return f"{schema.lower()}://{rechner}" + (f":{port}" if port else "")


class Schwaerzung(logging.Filter):
    """Ersetzt erkennbare Geheimnisse und Personendaten in jeder Meldung."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            text = record.getMessage()
        except (TypeError, ValueError):
            text = str(record.msg)
        record.msg = schwaerze(text)
        record.args = None
        if record.exc_info and record.exc_info[1] is not None:
            # der Stack bleibt (Betrieb braucht ihn), seine Texte werden geschwärzt
            record.exc_text = schwaerze(
                logging.Formatter().formatException(record.exc_info)
            )
        return True


class JsonFormat(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "zeit": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                "stufe": record.levelname,
                "logger": record.name,
                "text": record.getMessage(),
            },
            ensure_ascii=False,
        )


def richte_protokoll_ein(
    stufe: str | None = None,
    format_: str | None = None,
    ziel: IO[str] | None = None,
) -> logging.Handler:
    """Ein Handler am Wurzel-Logger mit Schwärzung; Uvicorn schreibt dorthin."""
    stufe = (stufe or os.environ.get("ACCOUNTI_PROTOKOLL_STUFE") or "INFO").upper()
    format_ = format_ or os.environ.get("ACCOUNTI_PROTOKOLL_FORMAT") or "text"
    handler = logging.StreamHandler(ziel or sys.stderr)
    handler.addFilter(Schwaerzung())
    handler.setFormatter(
        JsonFormat()
        if format_ == "json"
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    wurzel = logging.getLogger()
    wurzel.handlers = [handler]
    wurzel.setLevel(stufe)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    # HTTP-Bibliotheken schreiben ganze Adressen (Webhook-URLs tragen oft Token);
    # httpx2/httpcore2 kommen mit openai 2.x über litellm
    for name in ("httpx", "httpcore", "httpx2", "httpcore2", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
    return handler
