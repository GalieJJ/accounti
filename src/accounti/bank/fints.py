"""FinTS-Provider — Umsätze direkt bei der Bank, über python-fints (FinTS 3.0, PIN/TAN).

Keine dritte Partei sieht die Daten. Was es braucht:

- eine **Produkt-ID** der Deutschen Kreditwirtschaft, je Installation registriert
  (Einstellung ``produkt_id`` am Konto, ``ACCOUNTI_FINTS_PRODUKT_ID`` oder
  ``bank.fints.produkt_id``) — sie steht bei jeder Dialoginitialisierung im HKVVB;
- Benutzerkennung und PIN (``geheime_felder``, verschlüsselt im Tresor);
- die **Sitzung** (Kundensystem-ID, Bank- und Benutzerparameter, TAN-Verfahren aus
  ``deconstruct``). Sie liegt ebenfalls verschlüsselt im Zugang: Die Bank bindet die
  Ausnahme von der starken Kundenauthentifizierung (180 Tage) an die
  Kundensystem-ID — ohne sie verlangte sie bei jedem Abruf eine TAN.

Verlangt die Bank eine Freigabe, fragt der Provider über ``freigabe`` nach (TAN
eingeben oder in der App bestätigen, dann Statusabfrage) — oder er meldet
``FreigabeNoetigError``, wenn niemand gefragt werden kann (Cron, ``bank lauf``).
Umsätze kommen als camt.052 (HKCAZ), wenn die Bank es anbietet, sonst als MT940
(HKKAZ), und laufen durch dieselben Parser wie Dateien.
"""

from __future__ import annotations

import base64
import binascii
import functools
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol

from accounti.bank.einstellungen import (
    UMGEBUNG_PRODUKT_ID,
    FinTSEinstellungen,
    lade_bank_einstellungen,
)
from accounti.bank.provider import (
    Abruf,
    BankProvider,
    Freigabe,
    Freigabeanfrage,
    FreigabeNoetigError,
    ProviderError,
    registriere,
)
from accounti.importers.camt import lies_camt
from accounti.importers.kontoauszug import Auszug, KontoauszugError
from accounti.importers.mt940 import lies_mt940
from accounti.models import Bankkonto

# python-fints protokolliert jede Rückmeldung der Bank (3040, 3076 …) als Warnung;
# accounti meldet Ergebnisse selbst — ohne eigene Logging-Einrichtung bleibt es still
logging.getLogger("fints").addHandler(logging.NullHandler())

SITZUNG = "sitzung"  # Schlüssel im Zugang: Sitzungsdaten der Bank (Base64)
FORMATE = ("auto", "camt", "mt940")
REGISTRIERUNG = "https://www.fints.org/de/hersteller/produktregistrierung"
_MAX_TAN_RUNDEN = 3


class FinTSClient(Protocol):
    """Was accounti vom python-fints-Client braucht (plus roher MT940-Abfrage)."""

    init_tan_response: Any

    def __enter__(self) -> Any: ...
    def __exit__(self, *args: object) -> Any: ...
    def get_sepa_accounts(self) -> Any: ...
    def bietet_camt(self) -> bool: ...
    def get_transactions_xml(
        self, account: Any, start_date: date | None = ..., end_date: date | None = ...
    ) -> Any: ...
    def umsaetze_mt940(
        self, account: Any, start_date: date | None, end_date: date | None
    ) -> Any: ...
    def send_tan(self, challenge: Any, tan: str) -> Any: ...
    def deconstruct(self, including_private: bool = ...) -> bytes: ...
    def fetch_tan_mechanisms(self) -> Any: ...
    def get_tan_mechanisms(self) -> Any: ...
    def set_tan_mechanism(self, security_function: str) -> None: ...
    def is_tan_media_required(self) -> bool: ...
    def get_tan_media(self) -> Any: ...
    def set_tan_medium(self, tan_medium: Any) -> None: ...


@dataclass(frozen=True)
class TanVerfahren:
    kennung: str  # Sicherheitsfunktion, z.B. "921"
    name: str  # z.B. "pushTAN 2.0"


@dataclass(frozen=True)
class _Medium:
    tan_medium_name: str


def _mt940_text(antworten: Any) -> str:
    # MT940 nutzt den SWIFT-Zeichensatz, eine Teilmenge von ISO 8859
    return "".join(seg.statement_booked.decode("iso-8859-1") for seg in antworten)


@functools.cache
def _client_klasse() -> type:
    """python-fints-Client mit roher MT940-Abfrage (statt mt-940-Objekten)."""
    from fints.client import FinTS3PinTanClient
    from fints.segments.statement import HKKAZ5, HKKAZ6, HKKAZ7

    class Client(FinTS3PinTanClient):  # type: ignore[misc]
        def bietet_camt(self) -> bool:
            return bool(self.bpd.find_segment_first("HICAZS"))

        def umsaetze_mt940(
            self, account: Any, start_date: date | None, end_date: date | None
        ) -> Any:
            # wie FinTS3Client.get_transactions, aber der Text bleibt roh — die
            # Auswertung macht accounti selbst (importers/mt940.py)
            with self._get_dialog() as dialog:
                hkkaz = self._find_highest_supported_command(HKKAZ5, HKKAZ6, HKKAZ7)
                konto = hkkaz._fields["account"].type.from_sepa_account(account)
                return self._fetch_with_touchdowns(
                    dialog,
                    lambda aufsetzpunkt: hkkaz(
                        account=konto,
                        all_accounts=False,
                        date_start=start_date,
                        date_end=end_date,
                        touchdown_point=aufsetzpunkt,
                    ),
                    _mt940_text,
                    "HIKAZ",
                )

    return Client


def erzeuge_client(
    *,
    blz: str,
    benutzerkennung: str,
    pin: str,
    server: str,
    kunden_id: str | None,
    produkt_id: str,
    produkt_version: str,
    daten: bytes | None,
) -> FinTSClient:
    """Der echte Client; Tests ersetzen diese Funktion durch eine Attrappe."""
    klasse = _client_klasse()
    client: FinTSClient = klasse(
        blz,
        benutzerkennung,
        pin,
        server,
        customer_id=kunden_id or None,
        from_data=daten,
        product_id=produkt_id,
        product_version=produkt_version,
    )
    return client


def _braucht_freigabe(antwort: Any) -> bool:
    from fints.client import NeedTANResponse

    return isinstance(antwort, NeedTANResponse)


def _ohne_geheimnisse(text: str, zugang: dict[str, str]) -> str:
    for name in FinTSProvider.geheime_felder:
        wert = zugang.get(name, "")
        if len(wert) >= 3:
            text = text.replace(wert, "***")
    return text


@contextmanager
def _fehler_uebersetzt(konto: Bankkonto, zugang: dict[str, str]) -> Iterator[None]:
    """Fehler von python-fints und der Verbindung werden zu ``ProviderError``."""
    import requests
    from fints.exceptions import (
        FinTSClientPINError,
        FinTSClientTemporaryAuthError,
        FinTSConnectionError,
        FinTSError,
        FinTSSCARequiredError,
        FinTSUnsupportedOperation,
    )

    def fehler(text: str) -> ProviderError:
        return ProviderError(_ohne_geheimnisse(text, zugang))

    server = konto.einstellungen.get("server", "")
    try:
        yield
    except (FreigabeNoetigError, ProviderError):
        raise
    except FinTSClientPINError as f:
        msg = (
            "Die Bank lehnt die Anmeldung ab (PIN oder Benutzerkennung falsch?) — "
            "Zugang neu einrichten (accounti fints einrichten); weitere Versuche "
            "mit diesem Zugang können ihn sperren"
        )
        raise fehler(msg) from f
    except FinTSClientTemporaryAuthError as f:
        msg = (
            "Der Zugang ist bei der Bank vorübergehend gesperrt — "
            "im Onlinebanking entsperren"
        )
        raise fehler(msg) from f
    except FinTSSCARequiredError as f:
        raise FreigabeNoetigError(_hinweis(konto)) from f
    except (FinTSConnectionError, requests.RequestException) as f:
        raise fehler(f"Bank nicht erreichbar ({server}): {f}") from f
    except FinTSUnsupportedOperation as f:
        raise fehler(f"Die Bank bietet das per FinTS nicht an: {f}") from f
    except KontoauszugError as f:
        raise fehler(f"Antwort der Bank nicht lesbar: {f}") from f
    except (FinTSError, ValueError) as f:
        raise fehler(f"FinTS-Fehler: {f}") from f
    except Exception as f:
        if type(f) is not Exception:  # python-fints wirft schlichte Exceptions
            raise
        raise fehler(f"FinTS-Fehler: {f}") from f


def _hinweis(konto: Bankkonto) -> str:
    return (
        f"Die Bank verlangt eine Freigabe (TAN oder App) für {konto.iban} — "
        f"accounti fints freigeben --konto {konto.iban}"
    )


def _sitzung_lesen(zugang: dict[str, str]) -> bytes | None:
    try:
        return base64.b64decode(zugang[SITZUNG], validate=True) or None
    except (KeyError, binascii.Error, ValueError):
        return None  # keine oder kaputte Sitzung: die Bank vergibt eine neue


@registriere
class FinTSProvider(BankProvider):
    name = "fints"
    felder = (
        "blz",
        "server",
        "kunden_id",
        "format",
        "produkt_id",
        "tan_verfahren",
        "tan_medium",
    )
    geheime_felder = ("benutzerkennung", "pin")

    def __init__(
        self,
        freigabe: Freigabe | None = None,
        einstellungen: FinTSEinstellungen | None = None,
        warte: Callable[[float], None] = time.sleep,
        uhr: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(freigabe)
        self._einstellungen = einstellungen
        self.warte = warte
        self.uhr = uhr

    @property
    def einstellungen(self) -> FinTSEinstellungen:
        if self._einstellungen is None:
            self._einstellungen = lade_bank_einstellungen().fints
        return self._einstellungen

    # --- Aufbau -----------------------------------------------------------------

    def _client(
        self, konto: Bankkonto, zugang: dict[str, str], mit_sitzung: bool = True
    ) -> FinTSClient:
        e = konto.einstellungen
        produkt_id = (
            e.get("produkt_id") or ""
        ).strip() or self.einstellungen.produkt_id
        if not produkt_id:
            msg = (
                "FinTS-Produkt-ID fehlt — jede Installation braucht eine eigene "
                f"Registrierung bei der Deutschen Kreditwirtschaft ({REGISTRIERUNG}); "
                f"dann {UMGEBUNG_PRODUKT_ID} setzen, bank.fints.produkt_id in "
                "config/accounti.yaml oder Einstellung produkt_id am Konto"
            )
            raise ProviderError(msg)
        if len(produkt_id) > 25:
            raise ProviderError("FinTS-Produkt-ID hat höchstens 25 Zeichen")
        fehlend = [n for n in ("blz", "server") if not e.get(n)]
        fehlend += [n for n in self.geheime_felder if not zugang.get(n)]
        if fehlend:
            msg = f"FinTS-Zugang unvollständig, es fehlt: {', '.join(fehlend)}"
            raise ProviderError(msg)
        if (e.get("format") or "auto") not in FORMATE:
            msg = f"Unbekanntes format '{e['format']}' (erlaubt: {', '.join(FORMATE)})"
            raise ProviderError(msg)
        client = erzeuge_client(
            blz=e["blz"],
            benutzerkennung=zugang["benutzerkennung"],
            pin=zugang["pin"],
            server=e["server"],
            kunden_id=e.get("kunden_id"),
            produkt_id=produkt_id,
            produkt_version=self.einstellungen.produkt_version,
            daten=_sitzung_lesen(zugang) if mit_sitzung else None,
        )
        if e.get("tan_verfahren"):
            client.set_tan_mechanism(e["tan_verfahren"])
        if e.get("tan_medium"):
            client.set_tan_medium(_Medium(e["tan_medium"]))
        return client

    def _zugang_mit_sitzung(
        self, client: FinTSClient, zugang: dict[str, str]
    ) -> dict[str, str]:
        sitzung = client.deconstruct(including_private=True)
        return {**zugang, SITZUNG: base64.b64encode(sitzung).decode()}

    # --- Freigabe ---------------------------------------------------------------

    def _freigeben(self, client: FinTSClient, antwort: Any, konto: Bankkonto) -> Any:
        """Beantwortet Freigabe-Anforderungen, bis die Bank ein Ergebnis liefert."""
        for _ in range(_MAX_TAN_RUNDEN):
            if not _braucht_freigabe(antwort):
                return antwort
            if self.freigabe is None:
                raise FreigabeNoetigError(_hinweis(konto))
            anfrage = Freigabeanfrage(
                konto=konto,
                text=str(antwort.challenge or "").strip(),
                app=bool(antwort.decoupled),
                hinweis=(
                    "Die Bank schickt eine Grafik oder einen Flickercode, den die "
                    "Konsole nicht anzeigen kann — ein Verfahren mit TAN-App oder "
                    "SMS wählen (accounti fints einrichten)"
                    if antwort.challenge_matrix or antwort.challenge_hhduc
                    else None
                ),
            )
            tan = self.freigabe(anfrage)
            if tan is None or (not anfrage.app and not tan.strip()):
                raise FreigabeNoetigError(f"Freigabe abgebrochen — {_hinweis(konto)}")
            antwort = (
                self._warte_auf_app(client, antwort, konto)
                if anfrage.app
                else client.send_tan(antwort, tan.strip())
            )
        if _braucht_freigabe(antwort):
            raise FreigabeNoetigError(
                f"Bank verlangt weiter Freigaben — {_hinweis(konto)}"
            )
        return antwort

    def _warte_auf_app(
        self, client: FinTSClient, antwort: Any, konto: Bankkonto
    ) -> Any:
        frist = self.uhr() + self.einstellungen.freigabe_wartezeit_sekunden
        while _braucht_freigabe(antwort) and antwort.decoupled:
            if self.uhr() >= frist:
                msg = (
                    "Freigabe in der App nicht rechtzeitig bestätigt — "
                    f"{_hinweis(konto)}"
                )
                raise FreigabeNoetigError(msg)
            self.warte(self.einstellungen.freigabe_intervall_sekunden)
            antwort = client.send_tan(antwort, "")
        return antwort

    def _initialisiere(self, client: FinTSClient, konto: Bankkonto) -> None:
        if client.init_tan_response is not None:
            self._freigeben(client, client.init_tan_response, konto)

    def _sepa_konto(self, client: FinTSClient, konto: Bankkonto) -> Any:
        konten = self._freigeben(client, client.get_sepa_accounts(), konto)
        for sepa in konten or []:
            if (sepa.iban or "").upper() == konto.iban:
                return sepa
        gefunden = ", ".join(str(k.iban) for k in konten or []) or "keine"
        msg = (
            f"Konto {konto.iban} gibt es unter diesem Zugang nicht "
            f"(gefunden: {gefunden})"
        )
        raise ProviderError(msg)

    # --- Abruf ------------------------------------------------------------------

    def _auszuege(
        self, client: FinTSClient, konto: Bankkonto, sepa: Any, von: date
    ) -> list[Auszug]:
        format = konto.einstellungen.get("format") or "auto"
        camt = client.bietet_camt()
        if format == "camt" and not camt:
            raise ProviderError("Die Bank bietet Umsätze als camt (HKCAZ) nicht an")
        if format == "camt" or (format == "auto" and camt):
            antwort = client.get_transactions_xml(sepa, start_date=von, end_date=None)
            gebucht, _vorgemerkt = self._freigeben(client, antwort, konto)
            return [a for xml in gebucht for a in lies_camt(bytes(xml))]
        text = self._freigeben(client, client.umsaetze_mt940(sepa, von, None), konto)
        return lies_mt940(text) if str(text or "").strip() else []

    def abrufen(
        self, konto: Bankkonto, zugang: dict[str, str], ab: date | None
    ) -> Abruf:
        tage = self.einstellungen.erster_abruf_tage
        von = ab or date.today() - timedelta(days=tage)
        with _fehler_uebersetzt(konto, zugang):
            client = self._client(konto, zugang)
        try:
            with _fehler_uebersetzt(konto, zugang), client:
                self._initialisiere(client, konto)
                sepa = self._sepa_konto(client, konto)
                auszuege = self._auszuege(client, konto, sepa, von)
        except FreigabeNoetigError as fehler:
            # auch ohne Freigabe die Sitzung sichern: die Kundensystem-ID bleibt
            with _fehler_uebersetzt(konto, zugang):
                fehler.zugang = self._zugang_mit_sitzung(client, zugang)
            raise
        with _fehler_uebersetzt(konto, zugang):
            abruf = Abruf(zugang=self._zugang_mit_sitzung(client, zugang))
        for auszug in auszuege:
            if not auszug.gehoert_zu(konto.iban):
                continue
            abruf.transaktionen.extend(auszug.umsaetze)
            if auszug.endsaldo is not None:
                abruf.saldo, abruf.saldo_datum = auszug.endsaldo, auszug.endsaldo_datum
        return abruf


def richte_fints_ein(
    konto: Bankkonto,
    zugang: dict[str, str],
    *,
    waehle_verfahren: Callable[[list[TanVerfahren]], str],
    waehle_medium: Callable[[list[str]], str],
    freigabe: Freigabe,
    einstellungen: FinTSEinstellungen | None = None,
    warte: Callable[[float], None] = time.sleep,
) -> tuple[Bankkonto, dict[str, str]]:
    """Erste Verbindung: TAN-Verfahren (und -Medium) wählen, erste Freigabe,
    prüfen, dass es das Konto unter dem Zugang gibt. Liefert das Konto mit den
    gewählten Einstellungen und den Zugang samt Sitzung (noch unverschlüsselt)."""
    provider = FinTSProvider(freigabe, einstellungen, warte)
    einstellungen_neu = dict(konto.einstellungen)
    with _fehler_uebersetzt(konto, zugang):
        client = provider._client(konto, zugang, mit_sitzung=False)
        client.fetch_tan_mechanisms()
        verfahren = [
            TanVerfahren(str(kennung), str(getattr(p, "name", "") or kennung))
            for kennung, p in (client.get_tan_mechanisms() or {}).items()
            if str(kennung) != "999"  # einschrittig: für Umsätze nicht mehr zulässig
        ]
        if not verfahren:
            raise ProviderError("Die Bank nennt kein zweistufiges TAN-Verfahren")
        wahl = (
            verfahren[0].kennung if len(verfahren) == 1 else waehle_verfahren(verfahren)
        )
        if wahl not in {v.kennung for v in verfahren}:
            raise ProviderError(f"TAN-Verfahren '{wahl}' bietet die Bank nicht an")
        client.set_tan_mechanism(wahl)
        einstellungen_neu["tan_verfahren"] = wahl
        if client.is_tan_media_required():
            _, medien = client.get_tan_media()
            namen = [str(m.tan_medium_name) for m in medien or []]
            if namen:
                medium = namen[0] if len(namen) == 1 else waehle_medium(namen)
                client.set_tan_medium(_Medium(medium))
                einstellungen_neu["tan_medium"] = medium
        with client:
            provider._initialisiere(client, konto)
            provider._sepa_konto(client, konto)
        neuer_zugang = provider._zugang_mit_sitzung(client, zugang)
    return konto.model_copy(update={"einstellungen": einstellungen_neu}), neuer_zugang


__all__ = [
    "SITZUNG",
    "FinTSClient",
    "FinTSProvider",
    "TanVerfahren",
    "erzeuge_client",
    "richte_fints_ein",
]
