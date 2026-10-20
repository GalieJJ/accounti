"""Attrappe des python-fints-Clients — nie eine echte Bank.

``AttrappenClient`` hat die Schnittstelle von ``FinTS3PinTanClient`` (plus der
rohen MT940-Abfrage, die accounti ergänzt), ``AttrappenBank`` den Zustand auf der Seite
der Bank über mehrere Clients hinweg: welche Kundensystem-IDs gerade eine gültige
starke Kundenauthentifizierung haben, welche TAN stimmt, was abgefragt wurde.
Freigabe-Anforderungen sind echte ``fints.client.NeedTANResponse``-Objekte.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from fints.client import NeedTANResponse
from fints.exceptions import (
    FinTSClientPINError,
    FinTSUnsupportedOperation,
)
from fints.models import SEPAAccount

DATEN = Path(__file__).parent / "daten" / "bank"
IBAN = "DE02120300000000202051"


@dataclass
class TanAnforderung:
    """Steht für das HITAN-Segment, aus dem NeedTANResponse den Text liest."""

    challenge: str
    challenge_hhduc: bytes | None = None


@dataclass
class Verfahren:
    security_function: str
    name: str


@dataclass
class Medium:
    tan_medium_name: str


@dataclass
class AttrappenBank:
    pin: str = "1234"
    tan: str = "123456"
    konten: list[str] = field(default_factory=lambda: [IBAN])
    camt: bool = True  # bietet HKCAZ an
    mt940: str = field(
        default_factory=lambda: (DATEN / "auszug.sta").read_bytes().decode("cp1252")
    )
    camt_dokumente: list[bytes] = field(
        default_factory=lambda: [(DATEN / "camt052_v08.xml").read_bytes()]
    )
    sca_bei_init: str | None = "tan"  # "tan", "app" oder None
    sca_beim_abruf: bool = False  # zusätzlich TAN für den Umsatzabruf
    app_bestaetigt_nach: int = 2  # so viele Statusabfragen, bis die App bestätigt
    verfahren: dict[str, str] = field(
        default_factory=lambda: {"921": "pushTAN 2.0", "942": "mobileTAN"}
    )
    medien: list[str] = field(default_factory=list)  # TAN-Medium nötig, wenn gefüllt
    verbindung_weg: Exception | None = None
    freigegeben: set[str] = field(default_factory=set)  # Kundensystem-IDs mit SCA
    systeme: int = 0
    clients: list[dict[str, Any]] = field(default_factory=list)
    abrufe: list[tuple[str, str, date | None, date | None]] = field(
        default_factory=list
    )
    tans: list[str] = field(default_factory=list)

    def fabrik(self, **kw: Any) -> AttrappenClient:
        self.clients.append(kw)
        return AttrappenClient(self, **kw)


class AttrappenClient:
    def __init__(
        self,
        bank: AttrappenBank,
        *,
        blz: str,
        benutzerkennung: str,
        pin: str,
        server: str,
        kunden_id: str | None,
        produkt_id: str,
        produkt_version: str,
        daten: bytes | None,
    ) -> None:
        self.bank = bank
        self.pin = pin
        zustand = json.loads(daten) if daten else {}
        self.system_id: str | None = zustand.get("system_id")
        self.verfahren: str | None = zustand.get("verfahren")
        self.medium: str | None = zustand.get("medium")
        self.init_tan_response: NeedTANResponse | None = None
        self.offen = False
        self._warten = 0
        self._ausstehend: tuple[str, Any] | None = None

    # --- Dialog -------------------------------------------------------------

    def _pruefe_zugang(self) -> None:
        if self.bank.verbindung_weg is not None:
            raise self.bank.verbindung_weg
        if self.pin != self.bank.pin:
            raise FinTSClientPINError("Error during dialog initialization, PIN wrong?")
        if self.system_id is None:
            self.bank.systeme += 1
            self.system_id = f"SYS-{self.bank.systeme}"

    def __enter__(self) -> None:
        self._pruefe_zugang()
        self.offen = True
        if self.bank.sca_bei_init and self.system_id not in self.bank.freigegeben:
            app = self.bank.sca_bei_init == "app"
            text = "Bitte bestätigen Sie in der App" if app else "Bitte TAN eingeben"
            self.init_tan_response = NeedTANResponse(
                None,
                TanAnforderung(text),
                "_continue_dialog_initialization",
                False,
                app,
            )

    def __exit__(self, *_: object) -> None:
        self.offen = False

    def _freigabe_fehlt(self) -> bool:
        return self.init_tan_response is not None and (
            self.system_id not in self.bank.freigegeben
        )

    def send_tan(self, antwort: NeedTANResponse, tan: str) -> Any:
        if antwort.decoupled:
            self._warten += 1
            if self._warten < self.bank.app_bestaetigt_nach:
                return NeedTANResponse(
                    antwort.command_seg,
                    TanAnforderung("Freigabe steht noch aus"),
                    antwort.resume_method,
                    False,
                    True,
                )
        else:
            self.bank.tans.append(tan)
            if tan != self.bank.tan:
                raise Exception("Error response: 9941 TAN ungültig")
        if antwort.command_seg is None:  # Freigabe der Dialoginitialisierung
            self.bank.freigegeben.add(str(self.system_id))
            return "Dialog initialisiert"
        art, ergebnis = self._ausstehend or ("", None)
        self._ausstehend = None
        return ergebnis

    # --- Geschäftsvorfälle --------------------------------------------------

    def _vorfall(self, art: str, ergebnis: Any) -> Any:
        if not self.offen:
            raise Exception("Cannot send on dialog that is not open")
        if self._freigabe_fehlt():
            raise Exception("Error response: 9075 Starke Kundenauthentifizierung nötig")
        if art == "umsaetze" and self.bank.sca_beim_abruf:
            self._ausstehend = (art, ergebnis)
            return NeedTANResponse(
                object(), TanAnforderung("TAN für den Umsatzabruf"), "_resume", False
            )
        return ergebnis

    def get_sepa_accounts(self) -> list[SEPAAccount]:
        konten = [
            SEPAAccount(iban, "BYLADEM1001", iban[-10:], None, iban[4:12])
            for iban in self.bank.konten
        ]
        return self._vorfall("konten", konten)  # type: ignore[no-any-return]

    def bietet_camt(self) -> bool:
        return self.bank.camt

    def get_transactions_xml(
        self,
        account: SEPAAccount,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Any:
        if not self.bank.camt:
            raise FinTSUnsupportedOperation("No supported HICAZS version found")
        self.bank.abrufe.append(("camt", account.iban, start_date, end_date))
        return self._vorfall("umsaetze", (list(self.bank.camt_dokumente), []))

    def umsaetze_mt940(
        self, account: SEPAAccount, start_date: date | None, end_date: date | None
    ) -> Any:
        self.bank.abrufe.append(("mt940", account.iban, start_date, end_date))
        return self._vorfall("umsaetze", self.bank.mt940)

    # --- TAN-Verfahren und Sitzung --------------------------------------------

    def fetch_tan_mechanisms(self) -> str | None:
        self._pruefe_zugang()
        return self.verfahren

    def get_tan_mechanisms(self) -> dict[str, Verfahren]:
        return {k: Verfahren(k, v) for k, v in self.bank.verfahren.items()}

    def get_current_tan_mechanism(self) -> str | None:
        return self.verfahren

    def set_tan_mechanism(self, verfahren: str) -> None:
        self.verfahren = verfahren

    def is_tan_media_required(self) -> bool:
        return bool(self.bank.medien)

    def get_tan_media(self) -> tuple[str, list[Medium]]:
        return "1", [Medium(m) for m in self.bank.medien]

    def set_tan_medium(self, medium: Medium) -> None:
        self.medium = medium.tan_medium_name

    def deconstruct(self, including_private: bool = False) -> bytes:
        return json.dumps(
            {
                "system_id": self.system_id,
                "verfahren": self.verfahren,
                "medium": self.medium,
            }
        ).encode()
