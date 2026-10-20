"""Generischer JSON/HTTP-Connector (``typ: json``) — ein REST-Portal per Konfiguration.

Beschrieben wird, wo die Liste der Dokumente steht (Pfad, Parameter, Punktpfad zu
den Einträgen, Seitenweise oder Next-URL), welche Felder ein Eintrag hat (ID,
Dateiname, Absender, Download-URL) und wie die Datei kommt (binär oder als
Base64-Feld einer JSON-Antwort).

Sicherheit: ``https`` ist Pflicht (``http`` nur für localhost) — auch für
Download-URLs fremder Hosts. Kopfzeilen mit Zugangsdaten gehen nur an den Host von
``basis_url``; Download-URLs auf fremde Hosts werden nur für ``erlaubte_hosts`` und
dann ohne Kopfzeilen abgerufen; Weiterleitungen auf fremde Hosts werden abgelehnt.
Geheimnisse stehen nie im Klartext in der Konfiguration: Ein geheimer Wert besteht
nur aus ``${VARIABLE}`` oder ``{zugang}`` (Tresor), höchstens mit festem Präfix wie
``Bearer ``.

Vollständigkeit: Jeder Lauf liest die ganze Liste. Hat sie mehr als ``max_seiten``
Seiten, scheitert der Lauf mit Meldung — Dokumente dahinter blieben sonst still
liegen. Ein Download, der vor dem angekündigten Ende abbricht, ist kein Original
und wird nicht aufgenommen.
"""

from __future__ import annotations

import base64
import binascii
import http.client
import json
import re
import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping
from http.client import HTTPMessage
from typing import IO, Any
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from accounti.belege.kanaele.abholung import KanalError
from accounti.belege.kanaele.connector import (
    BelegConnector,
    PortalDokument,
    registriere_connector,
)
from accounti.belege.kanaele.einstellungen import LOKALE_HOSTS, MB, loese_auf
from accounti.belege.kanaele.pruefung import DateiAbgelehntError
from accounti.konfiguration import KonfigurationError

ZUGANG = "{zugang}"
_GEHEIM = re.compile(
    r"authoriz|(?<![a-z])auth(?![a-z])|token|key|secret|passw|pwd|cookie|session"
    r"|credential|signature",
    re.I,
)
# Geheimer Wert: nur ein Platzhalter, höchstens mit festem Präfix ("Bearer ", "sid=")
_NUR_PLATZHALTER = re.compile(
    r"^(?:[A-Za-z][A-Za-z0-9_.-]*[ =])?(?:\$\{[A-Za-z_][A-Za-z0-9_]*\}|\{zugang\})$"
)
# Zeichen, die in einer URL stehen bleiben; alles andere wird prozentkodiert
_URL_ZEICHEN = "/%:@?&=+$,;~#!*'()[]"


class JsonListe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pfad: str
    parameter: dict[str, str] = Field(default_factory=dict)
    eintraege: str = Field(default="", description="Punktpfad; leer = Wurzel")
    seite_parameter: str | None = Field(default=None, description="z.B. pageNumber")
    erste_seite: int = 1
    naechste: str | None = Field(default=None, description="Punktpfad zur Next-URL")
    max_seiten: int = Field(
        default=50, ge=1, description="Schutz vor Endlosschleifen; mehr → Fehler"
    )

    @model_validator(mode="after")
    def _eine_blaetterart(self) -> JsonListe:
        if self.seite_parameter and self.naechste:
            msg = "entweder seite_parameter oder naechste angeben, nicht beides"
            raise ValueError(msg)
        return self


class JsonFelder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    dateiname: str | None = None
    absender: str | None = None
    datum: str | None = Field(
        default=None, description="Datum im Portal (ISO 8601), steht im Gedächtnis"
    )
    url: str | None = Field(default=None, description="Download-URL im Eintrag")


class JsonDatei(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pfad: str | None = Field(default=None, description="mit Platzhalter {id}")
    parameter: dict[str, str] = Field(default_factory=dict)
    inhalt: str | None = Field(
        default=None, description="Punktpfad zum Base64-Inhalt; leer = Datei selbst"
    )


class JsonEinstellungen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basis_url: str
    kopfzeilen: dict[str, str] = Field(default_factory=dict)
    liste: JsonListe
    felder: JsonFelder
    datei: JsonDatei = Field(default_factory=JsonDatei)
    erlaubte_hosts: list[str] = Field(default_factory=list)
    timeout_sekunden: float = Field(default=60, gt=0)
    max_antwort_mb: float = Field(default=10, gt=0, description="für Listen")

    @model_validator(mode="after")
    def _regeln(self) -> JsonEinstellungen:
        teile = urlsplit(self.basis_url)
        lokal = (teile.hostname or "") in LOKALE_HOSTS
        if teile.scheme != "https" and not (teile.scheme == "http" and lokal):
            raise ValueError("basis_url muss https sein (http nur für localhost)")
        if not teile.hostname:
            raise ValueError("basis_url ohne Host")
        geprueft = [
            ("kopfzeilen", self.kopfzeilen),
            ("liste.parameter", self.liste.parameter),
            ("datei.parameter", self.datei.parameter),
            ("liste.pfad", _abfrage(self.liste.pfad)),
            ("datei.pfad", _abfrage(self.datei.pfad or "")),
        ]
        for ort, werte in geprueft:
            for name, wert in werte.items():
                if _GEHEIM.search(name) and not _NUR_PLATZHALTER.match(wert):
                    msg = (
                        f"{ort}.{name}: Geheimnis im Klartext ist nicht erlaubt — "
                        "nur ${UMGEBUNGSVARIABLE} oder {zugang} (accounti kanaele "
                        "zugang connector NAME), höchstens mit festem Präfix wie "
                        "'Bearer '"
                    )
                    raise ValueError(msg)
        if not self.datei.pfad and not self.felder.url:
            raise ValueError(
                "datei.pfad oder felder.url angeben (woher kommt die Datei?)"
            )
        return self


def _abfrage(pfad: str) -> dict[str, str]:
    """Parameter, die im Pfad selbst stehen (``/liste?apiKey=…``)."""
    return dict(parse_qsl(urlsplit(pfad).query, keep_blank_values=True))


def wert_an(daten: Any, pfad: str) -> Any:
    """Wert unter einem Punktpfad (``a.b.0.c``); ``None``, wenn es ihn nicht gibt."""
    if not pfad:
        return daten
    for teil in pfad.split("."):
        if isinstance(daten, Mapping):
            daten = daten.get(teil)
        elif isinstance(daten, list) and teil.isdigit() and int(teil) < len(daten):
            daten = daten[int(teil)]
        else:
            return None
    return daten


def _text(wert: Any) -> str | None:
    if wert is None or isinstance(wert, (dict, list)):
        return None
    text = str(wert).strip()
    return text or None


class _NurGleicherHost(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nur auf denselben Host — sonst gingen Zugangsdaten mit."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        alt, neu = urlsplit(req.full_url), urlsplit(newurl)
        if (neu.hostname, neu.port) != (alt.hostname, alt.port) or (
            alt.scheme == "https" and neu.scheme != "https"
        ):
            raise KanalError(
                f"Weiterleitung auf {neu.scheme}://{neu.hostname} abgelehnt "
                "(Zugangsdaten gehen nur an basis_url)"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@registriere_connector
class JsonConnector(BelegConnector):
    typ = "json"
    beschreibung = "Generisches REST-Portal: Liste und Download per JSON/HTTP"
    Einstellungen = JsonEinstellungen

    @property
    def _e(self) -> JsonEinstellungen:
        assert isinstance(self.einstellungen, JsonEinstellungen)
        return self.einstellungen

    # -- Hilfen ---------------------------------------------------------------

    def _aufloesen(self, wert: str) -> str:
        try:
            wert = loese_auf(wert)
        except KonfigurationError as fehler:
            raise KanalError(f"Connector {self.name}: {fehler}") from None
        if ZUGANG in wert:
            geheimnis = self.geheimnis()
            if geheimnis is None:
                msg = (
                    f"Kein Zugang für Connector {self.name} gespeichert — "
                    f"accounti kanaele zugang connector {self.name}"
                )
                raise KanalError(msg)
            wert = wert.replace(ZUGANG, geheimnis)
        return wert

    def _kopfzeilen(self) -> dict[str, str]:
        kopf = {"User-Agent": "accounti", "Accept": "application/json, */*"}
        kopf.update({k: self._aufloesen(v) for k, v in self._e.kopfzeilen.items()})
        return kopf

    def _url(self, pfad: str, parameter: Mapping[str, str]) -> str:
        url = urljoin(self._e.basis_url.rstrip("/") + "/", pfad.lstrip("/"))
        werte = {k: self._aufloesen(v) for k, v in parameter.items()}
        if werte:
            url += ("&" if "?" in url else "?") + urlencode(werte)
        return url

    def _adresse(self, basis: str, ziel: str) -> tuple[str, str, str]:
        """Absolute, prozentkodierte URL aus der Portalantwort mit Schema und Host
        — ``KanalError`` statt ``ValueError`` bei kaputten URLs."""
        try:
            url = urljoin(basis, quote(ziel, safe=_URL_ZEICHEN))
            teile = urlsplit(url)
            return url, teile.scheme, teile.hostname or ""
        except ValueError as fehler:
            msg = f"Connector {self.name}: URL aus der Portalantwort unbrauchbar"
            raise KanalError(f"{msg}: {fehler}") from None

    def _eigener_host(self, url: str) -> bool:
        try:
            a, b = urlsplit(url), urlsplit(self._e.basis_url)
            return (a.scheme, a.hostname, a.port) == (b.scheme, b.hostname, b.port)
        except ValueError:
            return False

    def _hole(self, url: str, grenze: int, mit_zugang: bool = True) -> bytes:
        kopf = self._kopfzeilen() if mit_zugang else {"User-Agent": "accounti"}
        ort = urlsplit(url).path
        try:
            anfrage = urllib.request.Request(url, headers=kopf, method="GET")
            oeffner = urllib.request.build_opener(_NurGleicherHost())
            with oeffner.open(anfrage, timeout=self._e.timeout_sekunden) as antwort:
                inhalt: bytes = antwort.read(grenze + 1)
                rest = getattr(antwort, "length", None)
        except urllib.error.HTTPError as fehler:
            auszug = fehler.read(300).decode("utf-8", "replace").strip()
            msg = f"Connector {self.name}: HTTP {fehler.code} von {ort}: {auszug[:200]}"
            raise KanalError(msg) from None
        except (urllib.error.URLError, TimeoutError, OSError) as fehler:
            grund = getattr(fehler, "reason", fehler)
            msg = f"Connector {self.name}: Verbindung zu {ort} gescheitert: {grund}"
            raise KanalError(msg) from None
        except (http.client.HTTPException, ValueError) as fehler:
            # z.B. IncompleteRead (chunked abgebrochen), InvalidURL, BadStatusLine
            grund = f"{type(fehler).__name__}: {fehler}"
            msg = f"Connector {self.name}: Antwort von {ort} unbrauchbar ({grund})"
            raise KanalError(msg) from None
        if len(inhalt) > grenze:
            msg = (
                f"Antwort von {ort} größer als erlaubt (höchstens {grenze / MB:.2f} MB)"
            )
            raise DateiAbgelehntError(msg, "groesse")
        if isinstance(rest, int) and rest > 0:
            # http.client meldet ein vorzeitiges Verbindungsende bei read(n) nicht
            msg = (
                f"Connector {self.name}: Antwort von {ort} unvollständig "
                f"({len(inhalt)} Bytes, {rest} fehlen) — Verbindung abgebrochen"
            )
            raise KanalError(msg)
        return inhalt

    def _json(self, url: str) -> Any:
        grenze = int(self._e.max_antwort_mb * MB)
        try:
            roh = self._hole(url, grenze)
        except DateiAbgelehntError as fehler:
            raise KanalError(f"Connector {self.name}: {fehler}") from None
        try:
            return json.loads(roh)
        except ValueError:
            msg = (
                f"Connector {self.name}: Antwort von {urlsplit(url).path} ist kein JSON"
            )
            raise KanalError(msg) from None

    # -- BelegConnector -------------------------------------------------------

    def _seite(self, seite: int) -> str:
        liste = self._e.liste
        parameter = dict(liste.parameter)
        if liste.seite_parameter:
            parameter[liste.seite_parameter] = str(seite)
        return self._url(liste.pfad, parameter)

    def dokumente(self) -> Iterator[PortalDokument]:
        """Alle Seiten der Liste, bis eine leer ist oder keine Next-URL mehr kommt.

        ``max_seiten`` schützt vor Endlosschleifen. Liegt danach noch eine Seite
        mit Einträgen, scheitert der Lauf: Jeder Lauf beginnt wieder bei der
        ersten Seite, Dokumente dahinter kämen also nie an.
        """
        liste = self._e.liste
        felder = self._e.felder
        seite = liste.erste_seite
        url = self._seite(seite)
        for gelesen in range(liste.max_seiten + 1):
            daten = self._json(url)
            eintraege = wert_an(daten, liste.eintraege)
            if not isinstance(eintraege, list):
                msg = (
                    f"Connector {self.name}: keine Liste unter "
                    f"'{liste.eintraege or '(Wurzel)'}' in der Antwort"
                )
                raise KanalError(msg)
            if not eintraege:
                return
            if gelesen == liste.max_seiten:
                msg = (
                    f"Connector {self.name}: Die Liste hat mehr als "
                    f"{liste.max_seiten} Seiten — die Dokumente dahinter wurden "
                    "nicht gelesen (jeder Lauf beginnt bei der ersten Seite). "
                    "liste.max_seiten erhöhen"
                )
                raise KanalError(msg)
            for eintrag in eintraege:
                kennung = _text(wert_an(eintrag, felder.id))
                if kennung is None:
                    self.hinweise.append(
                        f"{self.name}: Eintrag ohne '{felder.id}' übersprungen"
                    )
                    continue
                yield PortalDokument(
                    id=kennung,
                    dateiname=_text(wert_an(eintrag, felder.dateiname or "")),
                    absender=_text(wert_an(eintrag, felder.absender or "")),
                    datum=_text(wert_an(eintrag, felder.datum or "")),
                    url=_text(wert_an(eintrag, felder.url or "")),
                )
            if liste.naechste:
                naechste = _text(wert_an(daten, liste.naechste))
                if naechste is None:
                    return
                url = self._adresse(url, naechste)[0]
                if not self._eigener_host(url):
                    msg = f"Connector {self.name}: Next-URL auf fremden Host abgelehnt"
                    raise KanalError(msg)
            elif liste.seite_parameter:
                seite += 1
                url = self._seite(seite)
            else:
                return

    def lade(self, dokument: PortalDokument) -> bytes:
        datei = self._e.datei
        grenze = self.max_bytes * 4 // 3 + 64 * 1024 if datei.inhalt else self.max_bytes
        if dokument.url:
            basis = self._e.basis_url.rstrip("/") + "/"
            url, schema, host = self._adresse(basis, dokument.url)
            if self._eigener_host(url):
                inhalt = self._hole(url, grenze)
            elif host not in self._e.erlaubte_hosts or schema not in ("https", "http"):
                msg = f"Download-URL auf {host or url} — Host nicht in erlaubte_hosts"
                raise KanalError(msg)
            elif schema != "https" and host not in LOKALE_HOSTS:
                msg = (
                    f"Download-URL auf {host} ohne https abgelehnt — das archivierte "
                    "Original muss unverfälscht ankommen (http nur für localhost)"
                )
                raise KanalError(msg)
            else:
                inhalt = self._hole(url, grenze, mit_zugang=False)
        elif datei.pfad:
            pfad = datei.pfad.replace("{id}", quote(dokument.id, safe=""))
            inhalt = self._hole(self._url(pfad, datei.parameter), grenze)
        else:
            raise KanalError(f"Dokument {dokument.id}: keine Download-Adresse")
        if not datei.inhalt:
            return inhalt
        try:
            wert = wert_an(json.loads(inhalt), datei.inhalt)
            if not isinstance(wert, str):
                raise ValueError(datei.inhalt)
            return base64.b64decode(wert, validate=True)
        except (ValueError, binascii.Error):
            msg = f"Dokument {dokument.id}: kein Base64 unter '{datei.inhalt}'"
            raise KanalError(msg) from None
