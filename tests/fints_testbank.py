"""Lokale FinTS-Testbank für den **echten** python-fints-Client — keine echte Bank.

Ein HTTP-Server auf 127.0.0.1 nimmt FinTS-Nachrichten (Base64) entgegen, liest sie
mit dem Parser von python-fints und antwortet mit selbst geschriebenen Segmenten:
Bankparameter mit einem TAN-Verfahren, Kundensystem-ID, Freigabe bei der
Dialoginitialisierung, SEPA-Konten, MT940 in zwei Teilen (Aufsetzpunkt) und camt.
So prüfen die Tests, dass accounti und python-fints wirklich zusammenpassen —
Produkt-ID im HKVVB, TAN-Ablauf, gesicherte Sitzung —, ohne je eine Bank zu fragen.
Die Antworten sind für accounti geschrieben, nicht aus anderen Projekten kopiert.
"""

from __future__ import annotations

import base64
import datetime as dt
import http.server
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from fints.formals import (
    KTI1,
    KTZ1,
    AlgorithmParameterIVName,
    AlgorithmParameterName,
    AllowedFormat,
    BankIdentifier,
    BookedCamtStatements1,
    CompressionFunction,
    DateTimeType,
    DescriptionRequired,
    EncryptionAlgorithm,
    EncryptionAlgorithmCoded,
    IdentifiedRole,
    InitializationMode,
    KeyName,
    KeyType,
    Language2,
    OperationMode,
    ParameterPinTan,
    ParameterTwostepTAN6,
    PrincipalAccountRequired,
    Response,
    SecurityDateTime,
    SecurityIdentificationDetails,
    SecurityMethod,
    SecurityProfile,
    SecurityRole,
    SMSChargeAccountRequired,
    SupportedHBCIVersions2,
    SupportedLanguages2,
    TANTimeDialogAssociation,
    TaskHashAlgorithm,
    TransactionTanRequired,
    TwoStepParameters6,
    UsageEncryption,
)
from fints.parser import FinTS3Parser
from fints.segments.accounts import HISPA1
from fints.segments.auth import HIPINS1, HITAN6, HITANS6
from fints.segments.bank import HIBPA3
from fints.segments.base import FinTS3Segment
from fints.segments.dialog import HIRMG2, HIRMS2, HISYN4
from fints.segments.message import HNHBK3, HNHBS1, HNVSD1, HNVSK3
from fints.segments.statement import HICAZ1, HIKAZ7
from fints.types import SegmentSequence

BLZ = "12030000"
IBAN = "DE02120300000000202051"
BIC = "BYLADEM1001"
BPD_VERSION = 7
CAMT052 = "urn:iso:std:iso:20022:tech:xsd:camt.052.001.08"


def _roh(text: str) -> FinTS3Segment:
    """Ein Segment, das python-fints nicht als Klasse kennt (z.B. HIKAZS)."""
    segment: FinTS3Segment = FinTS3Parser().parse_message(text.encode()).segments[0]
    return segment


def _antwort(
    bezug: FinTS3Segment | None, *meldungen: tuple[str, str, list[str]]
) -> Any:
    seg = HIRMS2(
        responses=[
            Response(code=code, reference_element="", text=text, parameters=params)
            for code, text, params in meldungen
        ]
    )
    if bezug is not None:
        seg.header.reference = bezug.header.number
    return seg


def _bezug(seg: FinTS3Segment, bezug: FinTS3Segment) -> FinTS3Segment:
    seg.header.reference = bezug.header.number
    return seg


def _bankparameter(camt: bool) -> list[FinTS3Segment]:
    verfahren = TwoStepParameters6(
        security_function="942",
        tan_process="2",
        tech_id="MTAN2",
        zka_id="mobileTAN",
        zka_version="1",
        name="mobileTAN",
        max_length_input=6,
        allowed_format=AllowedFormat.NUMERIC,
        text_return_value="TAN",
        max_length_return_value=6,
        multiple_tans_allowed=False,
        tan_time_dialog_association=TANTimeDialogAssociation.NOT_ALLOWED,
        cancel_allowed=False,
        sms_charge_account_required=SMSChargeAccountRequired.MUST_NOT,
        principal_account_required=PrincipalAccountRequired.MUST_NOT,
        challenge_class_required=False,
        challenge_structured=False,
        initialization_mode=InitializationMode.CLEARTEXT_PIN_NO_TAN,
        description_required=DescriptionRequired.MUST_NOT,
        response_hhd_uc_required=False,
        supported_media_number=1,
    )
    segmente: list[FinTS3Segment] = [
        HIBPA3(
            bpd_version=BPD_VERSION,
            bank_identifier=BankIdentifier("280", BLZ),
            bank_name="accounti Testbank",
            number_tasks=3,
            supported_languages=SupportedLanguages2(languages=[Language2.DE]),
            supported_hbci_version=SupportedHBCIVersions2(versions=["300"]),
        ),
        HITANS6(
            max_number_tasks=1,
            min_number_signatures=1,
            security_class=1,
            parameter=ParameterTwostepTAN6(
                onestep_method_allowed=False,
                multiple_tasks_allowed=False,
                task_hash_algorithm=TaskHashAlgorithm.NONE,
                twostep_parameters=[verfahren],
            ),
        ),
        HIPINS1(
            max_number_tasks=1,
            min_number_signatures=1,
            security_class=0,
            parameter=ParameterPinTan(
                min_pin_length=4,
                max_pin_length=20,
                max_tan_length=6,
                user_id_field_text="Anmeldename",
                customer_id_field_text="Kunden-ID",
                transaction_tans_required=[
                    TransactionTanRequired(transaction=t, tan_required=False)
                    for t in ("HKSPA", "HKKAZ", "HKCAZ", "HKSAL")
                ],
            ),
        ),
        _roh("HISPAS:1:1:4+1+1+0+J:N:N'"),
        _roh("HIKAZS:1:7:4+1+1+0+90:N:N'"),
    ]
    if camt:
        formate = CAMT052.replace(":", "?:")
        segmente.append(_roh(f"HICAZS:1:1:4+1+1+0+90:N:N:{formate}'"))
    return segmente


class _Server(http.server.HTTPServer):
    def handle_error(self, request: Any, client_address: Any) -> None:
        """Nach einem Zeitlimit ist der Client schon weg — kein Grund zum Lärm."""


@dataclass
class FinTSTestbank:
    mt940_teile: list[str]
    camt_dokumente: list[bytes] = field(default_factory=list)
    camt: bool = False
    pin: str = "1234"
    tan: str = "123456"
    sca_bei_init: bool = True
    verzoegerung: float = 0.0  # Sekunden bis zur Antwort (Zeitlimit prüfen)
    produkt_ids: list[str] = field(default_factory=list)
    produkt_versionen: list[str] = field(default_factory=list)
    systeme: list[str] = field(default_factory=list)
    freigegeben: set[str] = field(default_factory=set)
    tans: list[str] = field(default_factory=list)
    eingang: list[list[str]] = field(default_factory=list)
    zeitraeume: list[tuple[Any, Any, str | None]] = field(default_factory=list)
    url: str = ""
    _dialoge: dict[str, dict[str, Any]] = field(default_factory=dict)
    _server: http.server.HTTPServer | None = None

    # --- Server ---------------------------------------------------------------

    def starte(self) -> str:
        bank = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 (Name aus http.server)
                time.sleep(bank.verzoegerung)
                laenge = int(self.headers["Content-Length"])
                nachricht = base64.b64decode(self.rfile.read(laenge))
                antwort = base64.b64encode(bank.beantworte(nachricht))
                self.send_response(200)
                self.send_header("Content-Length", str(len(antwort)))
                self.end_headers()
                self.wfile.write(antwort)

            def log_message(self, *_: object) -> None:
                pass

        self._server = _Server(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        host, port = self._server.server_address[:2]
        self.url = f"http://{host!s}:{port}/fints"
        return self.url

    def stoppe(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    # --- Antworten --------------------------------------------------------------

    def beantworte(self, roh: bytes) -> bytes:
        nachricht = FinTS3Parser().parse_message(roh)
        segmente = list(nachricht.find_segments(callback=lambda s: True))
        self.eingang.append([s.header.type for s in segmente])
        kopf = nachricht.find_segment_first("HNHBK")
        dialog_id = str(kopf.dialog_id)
        if dialog_id == "0":
            dialog_id = f"DIALOG-{len(self._dialoge) + 1}"
            self._dialoge[dialog_id] = {}
        dialog = self._dialoge.setdefault(dialog_id, {})
        signatur = nachricht.find_segment_first("HNSHA")
        pin = tan = None
        if signatur is not None and signatur.user_defined_signature is not None:
            pin = str(signatur.user_defined_signature.pin or "")
            tan = signatur.user_defined_signature.tan

        inhalt: list[Any] = [
            HIRMG2(responses=[Response("0010", "", "Nachricht entgegengenommen")])
        ]
        if pin is not None and pin != self.pin:
            inhalt = [HIRMG2(responses=[Response("9910", "", "PIN ungültig")])]
        else:
            for seg in segmente:
                inhalt += self._segment(seg, dialog, tan)
        return self._umschlag(dialog_id, int(kopf.message_number), inhalt)

    def _segment(
        self, seg: Any, dialog: dict[str, Any], tan: str | None
    ) -> list[FinTS3Segment]:
        art = seg.header.type
        if art == "HKIDN":
            dialog["system"] = str(seg.system_id)
            return []
        if art == "HKVVB":
            self.produkt_ids.append(str(seg.product_name))
            self.produkt_versionen.append(str(seg.product_version))
            meldungen = [("0020", "Dialoginitialisierung erfolgreich", [])]
            antwort: list[FinTS3Segment] = []
            if int(seg.bpd_version) != BPD_VERSION:
                meldungen.insert(0, ("3050", "BPD nicht mehr aktuell", []))
                antwort = _bankparameter(self.camt)
            meldungen.append(("3920", "Zugelassene TAN-Verfahren", ["942"]))
            return [_antwort(seg, *meldungen), *antwort]
        if art == "HKSYN":
            system = f"TESTSYSTEM-{len(self.systeme) + 1}"
            self.systeme.append(system)
            return [
                _antwort(seg, ("0020", "Auftrag ausgeführt", [])),
                HISYN4(system_id=system),
            ]
        if art == "HKTAN":
            return self._tan(seg, dialog, tan)
        if art == "HKSPA":
            konto = KTZ1(
                is_sepa=True,
                iban=IBAN,
                bic=BIC,
                account_number="202051",
                subaccount_number=None,
                bank_identifier=BankIdentifier("280", BLZ),
            )
            return [
                _antwort(seg, ("0020", "Auftrag ausgeführt", [])),
                _bezug(HISPA1(accounts=[konto]), seg),
            ]
        if art == "HKKAZ":
            self.zeitraeume.append((seg.date_start, seg.date_end, seg.touchdown_point))
            teil = int(seg.touchdown_point or 0)
            umsaetze = _bezug(
                HIKAZ7(statement_booked=self.mt940_teile[teil].encode("iso-8859-1")),
                seg,
            )
            if teil + 1 < len(self.mt940_teile):
                weiter = (
                    "3040",
                    "Es liegen weitere Informationen vor",
                    [str(teil + 1)],
                )
                return [_antwort(seg, weiter), umsaetze]
            return [_antwort(seg, ("0020", "Auftrag ausgeführt", [])), umsaetze]
        if art == "HKCAZ":
            self.zeitraeume.append((seg.date_start, seg.date_end, seg.touchdown_point))
            camt = HICAZ1(
                account=KTI1(iban=IBAN, bic=BIC),
                camt_descriptor=CAMT052,
                statement_booked=BookedCamtStatements1(
                    camt_statements=list(self.camt_dokumente)
                ),
            )
            return [
                _antwort(seg, ("0020", "Auftrag ausgeführt", [])),
                _bezug(camt, seg),
            ]
        if art == "HKEND":
            return [_antwort(seg, ("0100", "Dialog beendet", []))]
        return []

    def _tan(
        self, seg: Any, dialog: dict[str, Any], tan: str | None
    ) -> list[FinTS3Segment]:
        system = dialog.get("system", "")
        if seg.tan_process == "4":  # Freigabe der Dialoginitialisierung anfordern
            if not self.sca_bei_init or system in self.freigegeben:
                meldung = ("3076", "Keine starke Kundenauthentifizierung notwendig", [])
                return [_antwort(seg, meldung)]
            referenz = f"AUFTRAG-{len(self.tans) + 1}"
            dialog["auftrag"] = referenz
            return [
                _antwort(seg, ("0030", "Auftragsfreigabe erforderlich", [])),
                _bezug(
                    HITAN6(
                        tan_process="4",
                        task_reference=referenz,
                        challenge="Bitte TAN aus der SMS eingeben",
                    ),
                    seg,
                ),
            ]
        if seg.tan_process == "2":  # TAN zur Auftragsreferenz
            self.tans.append(str(tan))
            if seg.task_reference == dialog.get("auftrag") and tan == self.tan:
                self.freigegeben.add(system)
                return [_antwort(seg, ("0020", "Auftrag freigegeben", []))]
            return [_antwort(seg, ("9941", "TAN ungültig", []))]
        return [_antwort(seg, ("9120", "TAN-Prozess nicht unterstützt", []))]

    def _umschlag(self, dialog_id: str, nummer: int, inhalt: list[Any]) -> bytes:
        jetzt = dt.datetime.now()
        for nr, seg in enumerate(inhalt, start=2):
            seg.header.number = nr
        umschlag = SegmentSequence(
            [
                HNHBK3(
                    message_size=0,
                    hbci_version=300,
                    dialog_id=dialog_id,
                    message_number=nummer,
                ),
                HNVSK3(
                    security_profile=SecurityProfile(SecurityMethod.PIN, 2),
                    security_function="998",
                    security_role=SecurityRole.ISS,
                    security_identification_details=SecurityIdentificationDetails(
                        IdentifiedRole.MS, identifier="0"
                    ),
                    security_datetime=SecurityDateTime(
                        DateTimeType.STS, jetzt.date(), jetzt.time()
                    ),
                    encryption_algorithm=EncryptionAlgorithm(
                        UsageEncryption.OSY,
                        OperationMode.CBC,
                        EncryptionAlgorithmCoded.TWOKEY3DES,
                        b"\x00" * 8,
                        AlgorithmParameterName.KYE,
                        AlgorithmParameterIVName.IVC,
                    ),
                    key_name=KeyName(BankIdentifier("280", BLZ), "0", KeyType.V, 0, 0),
                    compression_function=CompressionFunction.NULL,
                ),
                HNVSD1(data=SegmentSequence(inhalt)),
                HNHBS1(message_number=nummer),
            ]
        )
        umschlag.segments[0].header.number = 1
        umschlag.segments[1].header.number = 998
        umschlag.segments[2].header.number = 999
        umschlag.segments[3].header.number = len(inhalt) + 2
        roh = umschlag.render_bytes()
        umschlag.segments[0].message_size = len(roh)
        return bytes(umschlag.render_bytes())
