"""ELSTER-Datensatz der Voranmeldung: Aufbau, Formate, interne Prüfung."""

import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal

import pytest

from accounti.elster.datensatz import (
    TESTMERKER,
    Absender,
    Kopf,
    datenart_version,
    dauerfrist_xml,
    lies_kennzahlen,
    pruefe_datensatz,
    ustva_xml,
)
from accounti.steuer.plausibilitaet import Schweregrad
from accounti.steuer.voranmeldung import UStVoranmeldung
from accounti.steuer.zeitraum import Zeitraum

D = Decimal
NS = {
    "e": "http://www.elster.de/elsterxml/schema/v11",
    "u": "http://finkonsens.de/elster/elsteranmeldung/ustva/v2026",
}
ABSENDER = Absender("Galerie Muster & Söhne GmbH", "Kunstweg 1", "80331", "München")
STNR = "9181081508155"


def va_august():
    va = UStVoranmeldung(zeitraum="2026-08")
    for kz, betrag in {
        81: "12000.67",
        86: "1234.56",
        41: "5000",
        46: "800",
        47: "152.00",
        66: "221.20",
        67: "152.00",
    }.items():
        va.addiere(kz, D(betrag))
    return va


def kopf(testmerker=TESTMERKER, hersteller_id="12345"):
    return Kopf(hersteller_id, "accounti", "0.1.0", testmerker)


def xml_august(**kw):
    return ustva_xml(
        va_august(),
        Zeitraum.lies("2026-08"),
        STNR,
        ABSENDER,
        kw.pop("kopf", kopf()),
        date(2026, 9, 7),
    )


def test_aufbau_wie_elster_xml_v11():
    wurzel = ET.fromstring(xml_august())
    assert wurzel.tag == "{http://www.elster.de/elsterxml/schema/v11}Elster"
    th = wurzel.find("e:TransferHeader", NS)
    assert th.get("version") == "11"
    assert [k.tag.split("}")[1] for k in th] == [
        "Verfahren",
        "DatenArt",
        "Vorgang",
        "Testmerker",
        "HerstellerID",
        "DatenLieferant",
        "Datei",
    ]
    assert th.findtext("e:Verfahren", namespaces=NS) == "ElsterAnmeldung"
    assert th.findtext("e:DatenArt", namespaces=NS) == "UStVA"
    assert th.findtext("e:Vorgang", namespaces=NS) == "send-Auth"
    assert th.findtext("e:Testmerker", namespaces=NS) == "700000004"
    assert (
        th.findtext("e:Datei/e:Verschluesselung", namespaces=NS) == "CMSEncryptedData"
    )
    assert th.findtext("e:Datei/e:Kompression", namespaces=NS) == "GZIP"
    ndh = wurzel.find("e:DatenTeil/e:Nutzdatenblock/e:NutzdatenHeader", NS)
    assert ndh.get("version") == "11"
    empfaenger = ndh.find("e:Empfaenger", NS)
    assert (empfaenger.get("id"), empfaenger.text) == ("F", "9181")
    assert ndh.findtext("e:Hersteller/e:ProduktName", namespaces=NS) == "accounti"

    anmeldung = wurzel.find(
        "e:DatenTeil/e:Nutzdatenblock/e:Nutzdaten/u:Anmeldungssteuern", NS
    )
    assert anmeldung.get("version") == "2026"
    assert anmeldung.get("art") is None  # seit der neuen Struktur kein Attribut art
    assert [k.tag.split("}")[1] for k in anmeldung] == [
        "Erstellungsdatum",
        "DatenLieferant",
        "Steuerfall",
    ]
    assert anmeldung.findtext("u:Erstellungsdatum", namespaces=NS) == "20260907"
    assert anmeldung.findtext("u:DatenLieferant/u:Name", namespaces=NS) == (
        "Galerie Muster & Söhne GmbH"
    )
    ustva = anmeldung.find("u:Steuerfall/u:Umsatzsteuervoranmeldung", NS)
    felder = [(k.tag.split("}")[1], k.text) for k in ustva]
    assert felder == [
        ("Jahr", "2026"),
        ("Zeitraum", "08"),
        ("Steuernummer", "9181081508155"),
        ("Kz09", "12345"),
        ("Kz41", "5000"),
        ("Kz46", "800"),
        ("Kz47", "152.00"),
        ("Kz66", "221.20"),
        ("Kz67", "152.00"),
        ("Kz81", "12000"),
        ("Kz83", "2145.18"),
        ("Kz86", "1234"),
    ]


def test_echtfall_ohne_testmerker_und_quartal():
    xml = ustva_xml(
        va_august(),
        Zeitraum.lies("2026-Q3"),
        STNR,
        ABSENDER,
        kopf(testmerker=None),
        date(2026, 10, 5),
    )
    wurzel = ET.fromstring(xml)
    assert wurzel.find("e:TransferHeader/e:Testmerker", NS) is None
    assert lies_kennzahlen(xml)["Zeitraum"] == "43"
    assert pruefe_datensatz(xml, testfall=False) == []


def test_interne_pruefung_ohne_befund():
    assert pruefe_datensatz(xml_august(), testfall=True) == []
    assert lies_kennzahlen(xml_august())["Kz83"] == "2145.18"


def test_negative_werte_und_berichtigung():
    va = UStVoranmeldung(zeitraum="2026-08", berichtigt=True)
    va.addiere(81, D("-50.75"))
    xml = ustva_xml(
        va, Zeitraum.lies("2026-08"), STNR, ABSENDER, kopf(), date(2026, 9, 7)
    )
    werte = lies_kennzahlen(xml)
    assert (werte["Kz10"], werte["Kz81"], werte["Kz83"]) == ("1", "-50", "-9.50")
    assert pruefe_datensatz(xml, testfall=True) == []


@pytest.mark.parametrize(
    ("aendern", "erwartet"),
    [
        (lambda x: x.replace("<Kz83>2145.18<", "<Kz83>2145.19<"), "Kz 83"),
        (lambda x: x.replace("<Kz09>12345</Kz09>", ""), "Kz09"),
        (lambda x: x.replace("<Kz81>12000<", "<Kz81>12000.67<"), "Kz81"),
        (lambda x: x.replace("<Testmerker>700000004</Testmerker>", ""), "Testmerker"),
        (lambda x: x.replace("9181081508155", "918108150815"), "Steuernummer"),
        (lambda x: x.replace(">9181<", ">9198<"), "Finanzamt"),
        (lambda x: x.replace("</Elster>", ""), "nicht wohlgeformt"),
        (lambda x: x.replace("<Zeitraum>08<", "<Zeitraum>13<"), "Zeitraum"),
    ],
)
def test_interne_pruefung_findet_fehler(aendern, erwartet):
    befunde = pruefe_datensatz(aendern(xml_august()), testfall=True)
    assert any(erwartet in b.text for b in befunde), befunde
    assert all(b.schweregrad is Schweregrad.FEHLER for b in befunde)


def test_testmerker_im_echtfall_ist_ein_fehler():
    befunde = pruefe_datensatz(xml_august(), testfall=False)
    assert [b.text for b in befunde] == [
        "Testmerker 700000004 im Echtfall — der Datensatz würde gelöscht"
    ]


def test_test_hersteller_id_ist_gesperrt():
    xml = xml_august(kopf=kopf(hersteller_id="74931"))
    (befund,) = pruefe_datensatz(xml, testfall=True)
    assert befund.schweregrad is Schweregrad.WARNUNG
    assert "seit ERiC 39.4" in befund.text
    (echt,) = pruefe_datensatz(xml.replace("<Testmerker>700000004</Testmerker>", ""),
                               testfall=False)  # fmt: skip
    assert echt.schweregrad is Schweregrad.FEHLER


def test_dauerfristverlaengerung_mit_sondervorauszahlung():
    xml = dauerfrist_xml(
        2027, STNR, ABSENDER, kopf(), D("4000.00"), berichtigt=False,
        erstellt=date(2027, 2, 1),
    )  # fmt: skip
    werte = lies_kennzahlen(xml)
    assert werte["Jahr"] == "2027" and werte["Kz38"] == "4000.00"
    assert "Kz83" not in werte
    assert pruefe_datensatz(xml, testfall=True) == []
    ohne = dauerfrist_xml(2027, STNR, ABSENDER, kopf(), None, False, date(2027, 2, 1))
    assert "Kz38" not in lies_kennzahlen(ohne)


def test_datenart_version():
    assert datenart_version(2026) == "UStVA_2026"
