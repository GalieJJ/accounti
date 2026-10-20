"""Generischer JSON/HTTP-Connector (``typ: json``) — ein REST-Portal per Konfiguration.

Beschrieben wird, wo die Liste der Dokumente steht (Pfad, Parameter, Punktpfad zu
den Einträgen, Seitenweise oder Next-URL), welche Felder ein Eintrag hat (ID,
Dateiname, Absender, Download-URL) und wie die Datei kommt (binär oder als
Base64-Feld einer JSON-Antwort).

Sicherheit: ``https`` ist Pflicht (``http`` nur für localhost). Kopfzeilen mit
Zugangsdaten gehen nur an den Host von ``basis_url``; Download-URLs auf fremde
Hosts werden nur für ``erlaubte_hosts`` und dann ohne Kopfzeilen abgerufen;
Weiterleitungen auf fremde Hosts werden abgelehnt. Geheimnisse stehen nie im
Klartext in der Konfiguration: ``${VARIABLE}`` oder ``{zugang}`` (Tresor).
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping
from http.client import HTTPMessage
from typing import IO, Any
from urllib.parse import quote, urlencode, urljoin, urlsplit

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
_GEHEIM = re.compile(r"authorization|token|key|secret|passw|cookie|session", re.I)


class JsonListe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pfad: str
    parameter: dict[str, str] = Field(default_factory=dict)
    eintraege: str = Field(default="", description="Punktpfad; leer = Wurzel")
    seite_parameter: str | None = Field(default=None, description="z.B. pageNumber")
    erste_seite: int = 1
    naechste: str | None = Field(default=None, description="Punktpfad zur Next-URL")
    max_seiten: int = Field(default=50, ge=1)


class JsonFelder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    dateiname: str | None = None
    absender: str | None = None
    datum: str | None = None
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
        ]
        for ort, werte in geprueft:
            for name, wert in werte.items():
                geschuetzt = "${" in wert or ZUGANG in wert
                if _GEHEIM.search(name) and not geschuetzt:
                    msg = (
                        f"{ort}.{name}: Geheimnis im Klartext ist nicht erlaubt — "
                        "${UMGEBUNGSVARIABLE} oder {zugang} (accounti kanaele zugang "
                        "connector NAME) verwenden"
                    )
                    raise ValueError(msg)
        if not self.datei.pfad and not self.felder.url:
            raise ValueError(
                "datei.pfad oder felder.url angeben (woher kommt die Datei?)"
            )
        return self


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

    def _eigener_host(self, url: str) -> bool:
        a, b = urlsplit(url), urlsplit(self._e.basis_url)
        return (a.scheme, a.hostname, a.port) == (b.scheme, b.hostname, b.port)

    def _hole(self, url: str, grenze: int, mit_zugang: bool = True) -> bytes:
        kopf = self._kopfzeilen() if mit_zugang else {"User-Agent": "accounti"}
        anfrage = urllib.request.Request(url, headers=kopf, method="GET")
        oeffner = urllib.request.build_opener(_NurGleicherHost())
        ort = urlsplit(url).path
        try:
            with oeffner.open(anfrage, timeout=self._e.timeout_sekunden) as antwort:
                inhalt: bytes = antwort.read(grenze + 1)
        except urllib.error.HTTPError as fehler:
            auszug = fehler.read(300).decode("utf-8", "replace").strip()
            msg = f"Connector {self.name}: HTTP {fehler.code} von {ort}: {auszug[:200]}"
            raise KanalError(msg) from None
        except (urllib.error.URLError, TimeoutError, OSError) as fehler:
            grund = getattr(fehler, "reason", fehler)
            msg = f"Connector {self.name}: Verbindung zu {ort} gescheitert: {grund}"
            raise KanalError(msg) from None
        if len(inhalt) > grenze:
            msg = (
                f"Antwort von {ort} größer als erlaubt (höchstens {grenze / MB:.2f} MB)"
            )
            raise DateiAbgelehntError(msg, "groesse")
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

    def dokumente(self) -> Iterator[PortalDokument]:
        liste = self._e.liste
        felder = self._e.felder
        seite = liste.erste_seite
        url: str | None = None
        for _ in range(liste.max_seiten):
            if url is None or liste.seite_parameter:
                parameter = dict(liste.parameter)
                if liste.seite_parameter:
                    parameter[liste.seite_parameter] = str(seite)
                url = self._url(liste.pfad, parameter)
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
                url = urljoin(url, naechste)
                if not self._eigener_host(url):
                    msg = f"Connector {self.name}: Next-URL auf fremden Host abgelehnt"
                    raise KanalError(msg)
            elif liste.seite_parameter:
                seite += 1
            else:
                return
        self.hinweise.append(
            f"{self.name}: nach {liste.max_seiten} Seiten abgebrochen (max_seiten) — "
            "der nächste Lauf macht weiter"
        )

    def lade(self, dokument: PortalDokument) -> bytes:
        datei = self._e.datei
        grenze = self.max_bytes * 4 // 3 + 64 * 1024 if datei.inhalt else self.max_bytes
        if dokument.url:
            url = urljoin(self._e.basis_url.rstrip("/") + "/", dokument.url)
            if self._eigener_host(url):
                inhalt = self._hole(url, grenze)
            elif (urlsplit(url).hostname or "") in self._e.erlaubte_hosts:
                inhalt = self._hole(url, grenze, mit_zugang=False)
            else:
                msg = (
                    f"Download-URL auf {urlsplit(url).hostname} — Host nicht in "
                    "erlaubte_hosts"
                )
                raise KanalError(msg)
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
