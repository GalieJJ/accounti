"""SEPA-Überweisung als pain.001.001.09 nach DK-TVS GBIC_5 (Anlage 3 DFÜ-Abkommen)."""

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from accounti.models.zahlung import LaufStatus, Zahlung, Zahlungslauf
from accounti.zahlung.sepa import (
    leere_felder,
    referenz,
    schreibe_pain001,
    sepa_text,
    verwendungszweck,
)
from tests.zahlung_hilfe import IBAN_EIGEN, IBAN_MUELLER


def test_dk_zeichensatz_umlaute_bleiben_fremdes_wird_ersetzt():
    assert (
        sepa_text("Bürobedarf Müller & Söhne GmbH") == "Bürobedarf Müller & Söhne GmbH"
    )
    assert sepa_text("Café Žižek – «Spezial»") == "Cafe Zizek Spezial"
    assert sepa_text("  Größe: 100 %  *neu*  ") == "Größe: 100 % *neu*"
    assert sepa_text("Łódź S.A.") == "Lodz S.A."
    assert sepa_text("x" * 80, 70) == "x" * 70
    assert sepa_text("€€€") == ""


def test_referenzen_nur_latin_ohne_schraegstrich_am_rand():
    assert referenz("RE-2026/0042") == "RE-2026/0042"
    assert referenz("/RE//2026/") == "RE/2026"
    assert referenz("Müller#42_A") == "Muller42A"
    assert referenz("A" * 40) == "A" * 35
    assert referenz("###") == ""


def test_verwendungszweck():
    assert (
        verwendungszweck("RE-2026-0042", date(2026, 10, 10), Decimal("0"))
        == "RE-2026-0042 vom 10.10.2026"
    )
    assert (
        verwendungszweck("RE-200", date(2026, 10, 10), Decimal("23.80"))
        == "RE-200 vom 10.10.2026, abzgl. 23,80 EUR Skonto"
    )
    assert verwendungszweck(None, None, Decimal("0")) == "Rechnung"
    assert len(verwendungszweck("X" * 200, date(2026, 1, 1), Decimal("1"))) == 140


# --- pain.001.001.09 ----------------------------------------------------------------

DATEN = Path(__file__).resolve().parent / "daten" / "zahlung"
XSD = DATEN / "pain.001.001.09_GBIC_5.xsd"
SOLL = DATEN / "pain001_soll.xml"
NS = {"p": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"}
JAVA = os.environ.get("ACCOUNTI_JAVA", "java")
# In der CI (ACCOUNTI_PRUEFWERKZEUGE_PFLICHT=1) wird nicht übersprungen.
NUR_MIT_JAVA = pytest.mark.skipif(
    shutil.which(JAVA) is None
    and not os.environ.get("ACCOUNTI_PRUEFWERKZEUGE_PFLICHT"),
    reason="Java fehlt für die Schemaprüfung",
)
ERSTELLT = datetime(2026, 10, 20, 9, 30, 0)


def _zahlung(lauf_id, nr, **kw):
    werte = {
        "lauf_id": lauf_id,
        "nr": nr,
        "posten_id": uuid4(),
        "kontakt_id": uuid4(),
        "empfaenger": "Bürobedarf Müller GmbH",
        "iban": IBAN_MUELLER,
        "strasse": "Hauptstraße 12a",
        "plz": "24103",
        "ort": "Kiel",
        "land": "DE",
        "betrag": Decimal("1166.20"),
        "skonto": Decimal("23.80"),
        "restbetrag_vorher": Decimal("1190.00"),
        "verwendungszweck": "RE-200 vom 10.10.2026, abzgl. 23,80 EUR Skonto",
        "end_to_end_id": "RE-200",
        "grund": "Skonto",
    }
    werte.update(kw)
    return Zahlung(**werte)


def soll_lauf():
    lauf = Zahlungslauf(
        nr=7,
        status=LaufStatus.FREIGEGEBEN,
        stichtag=date(2026, 10, 20),
        ausfuehrung=date(2026, 10, 21),
        auftraggeber_name="Galerie Muster GmbH",
        auftraggeber_iban=IBAN_EIGEN,
        auftraggeber_bic="COBADEFFXXX",
        erstellt_von="erika",
    )
    lauf.zahlungen = [
        _zahlung(lauf.id, 1),
        _zahlung(
            lauf.id,
            2,
            empfaenger="Schulz & Söhne KG",
            iban="DE02120300000000202051",
            strasse="Am Markt",
            plz="20095",
            ort="Hamburg",
            betrag=Decimal("250.00"),
            skonto=Decimal("0.00"),
            restbetrag_vorher=Decimal("250.00"),
            verwendungszweck="SK-77 vom 01.10.2026",
            end_to_end_id="SK-77",
        ),
        _zahlung(
            lauf.id,
            3,
            empfaenger="Atelier Évian SARL",
            iban="FR1420041010050500013M02606",
            strasse="Rue Nationale 8",
            plz="74500",
            ort="Évian-les-Bains",
            land="FR",
            betrag=Decimal("0.01"),
            skonto=Decimal("0.00"),
            restbetrag_vorher=Decimal("0.01"),
            verwendungszweck="Rechnung",
            end_to_end_id="ACCOUNTI-7-3",
        ),
    ]
    return lauf


def test_pain001_entspricht_der_soll_datei():
    """Golden-Test: Änderungen am Erzeuger fallen auf und werden bewusst übernommen."""
    xml = schreibe_pain001(soll_lauf(), ERSTELLT, einzelbuchung=True)
    assert xml == SOLL.read_bytes()


def test_pain001_inhalt():
    wurzel = ET.fromstring(schreibe_pain001(soll_lauf(), ERSTELLT, einzelbuchung=False))
    assert wurzel.tag == "{urn:iso:std:iso:20022:tech:xsd:pain.001.001.09}Document"

    def text(pfad):
        return wurzel.findtext(pfad, namespaces=NS)

    kopf = "p:CstmrCdtTrfInitn/p:GrpHdr/"
    assert text(kopf + "p:MsgId") == "ACCOUNTI-7-20261020093000"
    assert text(kopf + "p:CreDtTm") == "2026-10-20T09:30:00"
    assert text(kopf + "p:NbOfTxs") == "3"
    assert text(kopf + "p:CtrlSum") == "1416.21"
    assert text(kopf + "p:InitgPty/p:Nm") == "Galerie Muster GmbH"
    zahlung = "p:CstmrCdtTrfInitn/p:PmtInf/"
    assert text(zahlung + "p:PmtInfId") == "ACCOUNTI-7"
    assert text(zahlung + "p:PmtMtd") == "TRF"
    assert text(zahlung + "p:BtchBookg") == "true"
    assert text(zahlung + "p:NbOfTxs") == "3"
    assert text(zahlung + "p:CtrlSum") == "1416.21"
    assert text(zahlung + "p:PmtTpInf/p:SvcLvl/p:Cd") == "SEPA"
    assert text(zahlung + "p:ReqdExctnDt/p:Dt") == "2026-10-21"
    assert text(zahlung + "p:DbtrAcct/p:Id/p:IBAN") == IBAN_EIGEN
    assert text(zahlung + "p:DbtrAgt/p:FinInstnId/p:BICFI") == "COBADEFFXXX"
    assert text(zahlung + "p:ChrgBr") == "SLEV"
    tx = wurzel.findall(zahlung + "p:CdtTrfTxInf", NS)
    assert [t.findtext("p:Cdtr/p:Nm", namespaces=NS) for t in tx] == [
        "Bürobedarf Müller GmbH",
        "Schulz & Söhne KG",
        "Atelier Evian SARL",
    ]
    erste = tx[0]
    assert erste.findtext("p:PmtId/p:EndToEndId", namespaces=NS) == "RE-200"
    assert erste.findtext("p:Amt/p:InstdAmt", namespaces=NS) == "1166.20"
    assert erste.find("p:Amt/p:InstdAmt", NS).get("Ccy") == "EUR"
    assert erste.findtext("p:CdtrAcct/p:Id/p:IBAN", namespaces=NS) == IBAN_MUELLER
    assert erste.findtext("p:Cdtr/p:PstlAdr/p:StrtNm", namespaces=NS) == "Hauptstraße"
    assert erste.findtext("p:Cdtr/p:PstlAdr/p:BldgNb", namespaces=NS) == "12a"
    assert erste.findtext("p:Cdtr/p:PstlAdr/p:TwnNm", namespaces=NS) == "Kiel"
    assert erste.findtext("p:RmtInf/p:Ustrd", namespaces=NS) == (
        "RE-200 vom 10.10.2026, abzgl. 23,80 EUR Skonto"
    )
    assert tx[1].find("p:Cdtr/p:PstlAdr/p:BldgNb", NS) is None
    assert tx[2].findtext("p:Cdtr/p:PstlAdr/p:Ctry", namespaces=NS) == "FR"
    assert tx[2].findtext("p:Cdtr/p:PstlAdr/p:TwnNm", namespaces=NS) == (
        "Evian-les-Bains"
    )


def test_einzelbuchung_und_ohne_bic():
    lauf = soll_lauf()
    lauf.auftraggeber_bic = None
    wurzel = ET.fromstring(schreibe_pain001(lauf, ERSTELLT, einzelbuchung=True))
    pmt = "p:CstmrCdtTrfInitn/p:PmtInf/"
    assert wurzel.findtext(pmt + "p:BtchBookg", namespaces=NS) == "false"
    agent = pmt + "p:DbtrAgt/p:FinInstnId/"
    assert wurzel.find(agent + "p:BICFI", NS) is None
    assert wurzel.findtext(agent + "p:Othr/p:Id", namespaces=NS) == "NOTPROVIDED"


def _grenzfall():
    """Höchstlängen, Sonderzeichen, Empfänger ohne Anschrift, Höchstbetrag."""
    lauf = soll_lauf()
    lauf.auftraggeber_bic = None
    lauf.auftraggeber_name = "Ä" * 90
    lauf.zahlungen = [
        _zahlung(
            lauf.id,
            1,
            empfaenger="Łódź " + "ß" * 80 + " & Co. *$%",
            strasse=None,
            plz=None,
            ort=None,
            land=None,
            betrag=Decimal("999999999.99"),
            skonto=Decimal("0.00"),
            verwendungszweck=verwendungszweck(
                "X/" * 90, date(2026, 1, 1), Decimal("1")
            ),
            end_to_end_id=referenz("/" + "R" * 50 + "/"),
        ),
        _zahlung(
            lauf.id,
            2,
            strasse="Straße des 17. Juni 100-102",
            ort="B" * 50,
            plz="1" * 20,
        ),
    ]
    return lauf


@NUR_MIT_JAVA
def test_pain001_ist_schemakonform_nach_dk_tvs_gbic_5(tmp_path):
    """Akzeptanz 2: gegen das offizielle Schema der Deutschen Kreditwirtschaft."""
    dateien = {
        "soll.xml": SOLL.read_bytes(),
        "sammelbuchung.xml": schreibe_pain001(soll_lauf(), ERSTELLT, False),
        "grenzfall.xml": schreibe_pain001(_grenzfall(), ERSTELLT, True),
    }
    for name, inhalt in dateien.items():
        (tmp_path / name).write_bytes(inhalt)
    # Gegenprobe: das Schema greift wirklich
    kaputt = SOLL.read_text(encoding="utf-8").replace(
        "<Ctry>DE</Ctry>", "<Ctry>D</Ctry>"
    )
    (tmp_path / "kaputt.xml").write_text(kaputt, encoding="utf-8")
    ergebnis = subprocess.run(
        [JAVA, str(DATEN / "XsdPruefung.java"), str(XSD)]
        + [str(tmp_path / n) for n in [*dateien, "kaputt.xml"]],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    zeilen = ergebnis.stdout.splitlines()
    assert [z for z in zeilen if z.endswith(": gueltig")] == [
        f"{n}: gueltig" for n in dateien
    ], ergebnis.stdout + ergebnis.stderr
    assert any(z.startswith("kaputt.xml: ") and "CountryCode" in z for z in zeilen)
    assert ergebnis.returncode == 1


def test_leere_pflichtfelder_werden_erkannt():
    """Letzte Sicherung vor dem Statuswechsel: kein leeres Element in der Datei."""
    assert leere_felder(SOLL.read_bytes()) == []
    lauf = soll_lauf()
    lauf.zahlungen[1] = lauf.zahlungen[1].model_copy(update={"empfaenger": "Фирма ООД"})
    assert leere_felder(schreibe_pain001(lauf, ERSTELLT)) == [
        "CstmrCdtTrfInitn/PmtInf/CdtTrfTxInf[2]/Cdtr/Nm"
    ]
