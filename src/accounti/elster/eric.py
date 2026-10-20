"""ERiC (ELSTER Rich Client) über ctypes — Multithreading-API (``EricMt…``).

Nach dem ERiC-Entwicklerhandbuch 43.3.2.0:

- Linux: ``libericapi.so`` mit ``RTLD_GLOBAL`` laden (Kap. 4.2.2), Instanz mit
  ``EricMtInstanzErzeugen(pluginPfad, logPfad)``.
- Prüfen ohne Versand: Anwendungsfall EBV-8 (``ERIC_PRUEFE_HINWEISE | ERIC_VALIDIERE``).
- Senden: EBV-6 (``ERIC_VALIDIERE | ERIC_SENDE | ERIC_DRUCKE``) mit Zertifikatshandle
  und PIN (``eric_verschluesselungs_parameter_t``) und PDF (``eric_druck_parameter_t``).
- Das Transferticket erzeugt ERiC seit Release 38 selbst; es steht im Rückgabepuffer.

Die Strukturen folgen ``eric_types.h`` in der Belegung, die erica (DigitalService,
MIT) verwendet; ihre ``version`` ist konfigurierbar, weil der Header nicht öffentlich
ist. Erprobt ist der Adapter nur gegen eine Attrappe der Bibliothek, nie gegen ELSTER.
"""

from __future__ import annotations

import ctypes
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from accounti.elster.uebermittlung import Ergebnis

ERIC_VALIDIERE = 1 << 1
ERIC_SENDE = 1 << 2
ERIC_DRUCKE = 1 << 5
ERIC_PRUEFE_HINWEISE = 1 << 7

ERIC_OK = 0
ERIC_GLOBAL_PRUEF_FEHLER = 610001002
ERIC_GLOBAL_HINWEISE = 610001003  # gültig, nur Hinweise
ERIC_GLOBAL_DATENARTVERSION_UNBEKANNT = 610001042
ERIC_IO_TESTHERSTELLERID_GESPERRT = 610301202

_BEKANNT = {
    ERIC_GLOBAL_PRUEF_FEHLER: "Datensatz nicht plausibel",
    ERIC_GLOBAL_DATENARTVERSION_UNBEKANNT: (
        "Datenartversion unbekannt — Plugin-Pfad prüfen (elster.eric.plugins)"
    ),
    ERIC_IO_TESTHERSTELLERID_GESPERRT: (
        "Test-Hersteller-ID gesperrt — eigene Hersteller-ID eintragen "
        "(elster.hersteller_id)"
    ),
}


class _DruckParameter(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("vorschau", ctypes.c_uint32),
        ("ersteSeite", ctypes.c_uint32),
        ("duplexDruck", ctypes.c_uint32),
        ("pdfName", ctypes.c_char_p),
        ("fussText", ctypes.c_char_p),
        ("pdfCallback", ctypes.c_void_p),
        ("pdfCallbackBenutzerdaten", ctypes.c_void_p),
    ]


class _VerschluesselungsParameter(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("zertifikatHandle", ctypes.c_uint32),
        ("pin", ctypes.c_char_p),
        ("abrufCode", ctypes.c_char_p),
    ]


class EricError(RuntimeError):
    """ERiC ließ sich nicht verwenden (Bibliothek, Instanz, Zertifikat)."""


def _signaturen(api: Any) -> None:
    p = ctypes.c_void_p
    s = ctypes.c_char_p
    u32 = ctypes.c_uint32
    i = ctypes.c_int
    tabelle: dict[str, tuple[list[Any], Any]] = {
        "EricMtInstanzErzeugen": ([s, s], p),
        "EricMtInstanzFreigeben": ([p], i),
        "EricMtRueckgabepufferErzeugen": ([p], p),
        "EricMtRueckgabepufferInhalt": ([p, p], s),
        "EricMtRueckgabepufferFreigeben": ([p, p], i),
        "EricMtGetHandleToCertificate": (
            [p, ctypes.POINTER(u32), ctypes.POINTER(u32), s],
            i,
        ),
        "EricMtCloseHandleToCertificate": ([p, u32], i),
        "EricMtHoleFehlerText": ([p, i, p], i),
        "EricMtBearbeiteVorgang": (
            [
                p,
                s,
                s,
                u32,
                ctypes.POINTER(_DruckParameter),
                ctypes.POINTER(_VerschluesselungsParameter),
                p,
                p,
                p,
            ],
            i,
        ),
    }
    for name, (argumente, rueckgabe) in tabelle.items():
        funktion = getattr(api, name)
        funktion.argtypes = argumente
        funktion.restype = rueckgabe


def _meldungen(xml: str, element: str) -> list[str]:
    """Texte aus ``<FehlerRegelpruefung>`` bzw. ``<Hinweis>`` des Rückgabepuffers."""
    bloecke = re.findall(rf"<(?:\w+:)?{element}\b.*?</(?:\w+:)?{element}>", xml, re.S)
    texte = []
    for block in bloecke:
        treffer = re.search(r"<(?:\w+:)?Text>(.*?)</(?:\w+:)?Text>", block, re.S)
        texte.append(" ".join((treffer.group(1) if treffer else block).split()))
    return texte


def _ticket(*xmls: str) -> str | None:
    for xml in xmls:
        treffer = re.search(r"<(?:\w+:)?TransferTicket>\s*([^<\s]+)\s*<", xml)
        if treffer:
            return treffer.group(1)
    return None


class EricUebermittler:
    weg = "eric"

    def __init__(
        self,
        *,
        bibliothek: str,
        zertifikat: str,
        pin: str,
        plugins: str | None = None,
        log: str | None = None,
        druck_version: int = 2,
        crypto_version: int = 2,
    ) -> None:
        self.bibliothek = bibliothek
        self.zertifikat = zertifikat
        self._pin = pin
        # das ERiC-Paket liefert die Plugins in lib/plugins2 (wie erica)
        self.plugins = plugins or str(Path(bibliothek).parent / "plugins2")
        self.log = log
        self.druck_version = druck_version
        self.crypto_version = crypto_version
        self._api: Any = None

    def __repr__(self) -> str:  # die PIN gehört in keine Ausgabe
        return f"EricUebermittler(bibliothek={self.bibliothek!r})"

    def _lade(self) -> Any:
        if self._api is None:
            try:
                api = ctypes.CDLL(self.bibliothek, mode=ctypes.RTLD_GLOBAL)
                _signaturen(api)
            except (OSError, AttributeError) as fehler:
                msg = f"ERiC-Bibliothek {self.bibliothek} nicht ladbar: {fehler}"
                raise EricError(msg) from fehler
            self._api = api
        return self._api

    @contextmanager
    def _instanz(self) -> Iterator[tuple[Any, Any]]:
        api = self._lade()
        with tempfile.TemporaryDirectory(prefix="eric-") as tmp:
            log = self.log or tmp
            instanz = api.EricMtInstanzErzeugen(
                self.plugins.encode(), str(log).encode()
            )
            if not instanz:
                raise EricError("ERiC-Instanz konnte nicht erzeugt werden")
            try:
                yield api, instanz
            finally:
                api.EricMtInstanzFreigeben(instanz)

    @contextmanager
    def _puffer(self, api: Any, instanz: Any) -> Iterator[Any]:
        puffer = api.EricMtRueckgabepufferErzeugen(instanz)
        if not puffer:
            raise EricError("ERiC-Rückgabepuffer konnte nicht erzeugt werden")
        try:
            yield puffer
        finally:
            api.EricMtRueckgabepufferFreigeben(instanz, puffer)

    @staticmethod
    def _inhalt(api: Any, instanz: Any, puffer: Any) -> str:
        roh = api.EricMtRueckgabepufferInhalt(instanz, puffer)
        return roh.decode("utf-8", "replace") if roh else ""

    def _fehlertext(self, api: Any, instanz: Any, kode: int) -> str:
        with self._puffer(api, instanz) as puffer:
            api.EricMtHoleFehlerText(instanz, kode, puffer)
            text = self._inhalt(api, instanz, puffer)
        bekannt = _BEKANNT.get(kode)
        return f"ERiC {kode}: " + "; ".join(t for t in (bekannt, text) if t)

    def _vorgang(self, xml: str, datenart_version: str, senden: bool) -> Ergebnis:
        with (
            self._instanz() as (api, instanz),
            self._puffer(api, instanz) as rueckgabe,
            self._puffer(api, instanz) as antwort,
        ):
            handle = ctypes.c_uint32(0)
            krypto = druck = None
            pdf_pfad: Path | None = None
            if senden:
                kode = api.EricMtGetHandleToCertificate(
                    instanz,
                    ctypes.byref(handle),
                    None,
                    self.zertifikat.encode(),
                )
                if kode != ERIC_OK:
                    fehler = self._fehlertext(api, instanz, kode)
                    return Ergebnis(False, fehler=f"Zertifikat: {fehler}")
                krypto = _VerschluesselungsParameter(
                    self.crypto_version, handle.value, self._pin.encode(), None
                )
                deskriptor, name = tempfile.mkstemp(
                    prefix="eric-", suffix=".pdf", dir=self.log
                )
                os.close(deskriptor)
                pdf_pfad = Path(name)
                druck = _DruckParameter(
                    self.druck_version, 0, 0, 0, str(pdf_pfad).encode(), None
                )
                flags = ERIC_VALIDIERE | ERIC_SENDE | ERIC_DRUCKE
            else:
                flags = ERIC_PRUEFE_HINWEISE | ERIC_VALIDIERE
            try:
                kode = api.EricMtBearbeiteVorgang(
                    instanz,
                    xml.encode("utf-8"),
                    datenart_version.encode(),
                    flags,
                    ctypes.byref(druck) if druck is not None else None,
                    ctypes.byref(krypto) if krypto is not None else None,
                    None,
                    rueckgabe,
                    antwort,
                )
                bericht = self._inhalt(api, instanz, rueckgabe)
                server = self._inhalt(api, instanz, antwort) or None
                pdf = (
                    pdf_pfad.read_bytes()
                    if pdf_pfad is not None and pdf_pfad.stat().st_size
                    else None
                )
            finally:
                if senden:
                    api.EricMtCloseHandleToCertificate(instanz, handle.value)
                if pdf_pfad is not None:
                    pdf_pfad.unlink(missing_ok=True)
            fehler_texte = _meldungen(bericht, "FehlerRegelpruefung")
            hinweise = tuple(_meldungen(bericht, "Hinweis"))
            # nur Hinweise (ERIC_GLOBAL_HINWEISE): der Datensatz ist gültig; jeder
            # andere Code bleibt ein Fehler, auch wenn Hinweise zurückkommen
            ok = kode == ERIC_OK or (
                not senden and kode == ERIC_GLOBAL_HINWEISE and not fehler_texte
            )
            meldung: str | None = None
            if not ok:
                meldung = "; ".join(fehler_texte) or self._fehlertext(
                    api, instanz, kode
                )
                if fehler_texte:
                    meldung = f"ERiC {kode}: {meldung}"
            return Ergebnis(
                ok,
                ticket=_ticket(bericht, server or "") if senden else None,
                pruefbericht=bericht,
                server_antwort=server,
                pdf=pdf,
                fehler=meldung,
                hinweise=hinweise,
            )

    def _sicher(self, xml: str, datenart_version: str, senden: bool) -> Ergebnis:
        try:
            return self._vorgang(xml, datenart_version, senden)
        except EricError as fehler:
            return Ergebnis(False, fehler=str(fehler))

    def pruefe(self, xml: str, datenart_version: str) -> Ergebnis:
        """EBV-8: Hinweisprüfung und Validierung, ohne Versand."""
        return self._sicher(xml, datenart_version, senden=False)

    def sende(self, xml: str, datenart_version: str) -> Ergebnis:
        """EBV-6: validieren, authentifiziert senden, Übertragungsprotokoll als PDF."""
        return self._sicher(xml, datenart_version, senden=True)
