"""ELSTER-Datensatz der Umsatzsteuer-Voranmeldung und der Dauerfristverlängerung.

Aufbau nach ERiC-Entwicklerhandbuch 43.3.2.0 (Kap. 5.1, 6.5, 8.1, 8.5)::

    <Elster xmlns="http://www.elster.de/elsterxml/schema/v11">
      <TransferHeader version="11">  Verfahren ElsterAnmeldung, DatenArt UStVA,
                                     Vorgang send-Auth, [Testmerker], HerstellerID,
                                     DatenLieferant, Datei (CMSEncryptedData, GZIP)
      <DatenTeil><Nutzdatenblock>
        <NutzdatenHeader version="11">  NutzdatenTicket, Empfaenger id="F" (Finanzamt),
                                        Hersteller (ProduktName, ProduktVersion)
        <Nutzdaten><Anmeldungssteuern version="2026"
            xmlns="http://finkonsens.de/elster/elsteranmeldung/ustva/v2026">
          Erstellungsdatum, DatenLieferant, Steuerfall/Umsatzsteuervoranmeldung (Jahr,
          Zeitraum, Steuernummer, Kz09 = Hersteller-ID, Kennzahlen aufsteigend)

Bemessungsgrundlagen in vollen Euro, Steuerbeträge mit Punkt und zwei Nachkommastellen.
Die amtlichen XML-Schemas liegen nur im ERiC-Paket; mit ERiC prüft ERiC selbst, ohne
ERiC prüft ``pruefe_datensatz`` Aufbau, Formate und die Rechnung von Kz 83.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from xml.sax.saxutils import escape, quoteattr

from accounti.elster.steuernummer import finanzamtsnummer
from accounti.steuer.plausibilitaet import Befund, Schweregrad
from accounti.steuer.voranmeldung import KENNZIFFERN_2026, Art, UStVoranmeldung
from accounti.steuer.zeitraum import Zeitraum

ELSTER_NS = "http://www.elster.de/elsterxml/schema/v11"
TESTMERKER = "700000004"  # Testfall, der sofort nach Eingang gelöscht wird
TEST_HERSTELLER_ID = "74931"  # nur noch Illustration, seit ERiC 39.4 gesperrt
_ZEITRAEUME = {f"{m:02d}" for m in range(1, 13)} | {"41", "42", "43", "44"}


def ustva_ns(jahr: int) -> str:
    return f"http://finkonsens.de/elster/elsteranmeldung/ustva/v{jahr}"


def datenart_version(jahr: int) -> str:
    """Parameter ``datenartVersion`` für ``EricBearbeiteVorgang``."""
    return f"UStVA_{jahr}"


@dataclass(frozen=True)
class Absender:
    """Datenlieferant: das Unternehmen, das die Anmeldung abgibt."""

    name: str
    strasse: str
    plz: str
    ort: str


@dataclass(frozen=True)
class Kopf:
    hersteller_id: str
    produkt_name: str
    produkt_version: str
    testmerker: str | None  # None im Echtfall


def _e(tag: str, text: str) -> str:
    return f"<{tag}>{escape(text)}</{tag}>"


def _betrag(kz: int, wert: Decimal) -> str:
    k = KENNZIFFERN_2026.get(kz)
    if k is not None and k.art is Art.BMG:
        return str(int(wert))
    if k is not None and k.art is Art.MERKER:
        return str(int(wert))
    return f"{wert.quantize(Decimal('0.01')):.2f}"


def _umschlag(steuernummer: str, absender: Absender, kopf: Kopf, nutzdaten: str) -> str:
    teile = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<Elster xmlns="{ELSTER_NS}">',
        '<TransferHeader version="11">',
        _e("Verfahren", "ElsterAnmeldung"),
        _e("DatenArt", "UStVA"),
        _e("Vorgang", "send-Auth"),
    ]
    if kopf.testmerker:
        teile.append(_e("Testmerker", kopf.testmerker))
    teile += [
        _e("HerstellerID", kopf.hersteller_id),
        _e("DatenLieferant", absender.name[:45]),
        "<Datei>",
        _e("Verschluesselung", "CMSEncryptedData"),
        _e("Kompression", "GZIP"),
        "<TransportSchluessel></TransportSchluessel>",
        "</Datei>",
        "</TransferHeader>",
        "<DatenTeil>",
        "<Nutzdatenblock>",
        '<NutzdatenHeader version="11">',
        _e("NutzdatenTicket", "1"),
        f'<Empfaenger id="F">{escape(finanzamtsnummer(steuernummer))}</Empfaenger>',
        "<Hersteller>",
        _e("ProduktName", kopf.produkt_name),
        _e("ProduktVersion", kopf.produkt_version),
        "</Hersteller>",
        "</NutzdatenHeader>",
        "<Nutzdaten>",
        nutzdaten,
        "</Nutzdaten>",
        "</Nutzdatenblock>",
        "</DatenTeil>",
        "</Elster>",
    ]
    return "\n".join(teile) + "\n"


def _anmeldung(jahr: int, absender: Absender, erstellt: date, steuerfall: str) -> str:
    return "\n".join(
        [
            f'<Anmeldungssteuern xmlns={quoteattr(ustva_ns(jahr))} version="{jahr}">',
            _e("Erstellungsdatum", f"{erstellt:%Y%m%d}"),
            "<DatenLieferant>",
            _e("Name", absender.name[:45]),
            _e("Strasse", absender.strasse[:30]),
            _e("PLZ", absender.plz[:12]),
            _e("Ort", absender.ort[:30]),
            "</DatenLieferant>",
            "<Steuerfall>",
            steuerfall,
            "</Steuerfall>",
            "</Anmeldungssteuern>",
        ]
    )


def ustva_xml(
    va: UStVoranmeldung,
    zeitraum: Zeitraum,
    steuernummer: str,
    absender: Absender,
    kopf: Kopf,
    erstellt: date,
) -> str:
    """Voranmeldung als ELSTER-XML; die Werte kommen aus ``formularwerte()``."""
    werte = va.formularwerte()
    felder = [
        _e("Jahr", str(zeitraum.jahr)),
        _e("Zeitraum", zeitraum.elster_code),
        _e("Steuernummer", steuernummer),
        _e("Kz09", kopf.hersteller_id),
    ] + [_e(f"Kz{kz:02d}", _betrag(kz, werte[kz])) for kz in sorted(werte)]
    steuerfall = "\n".join(
        ["<Umsatzsteuervoranmeldung>", *felder, "</Umsatzsteuervoranmeldung>"]
    )
    nutzdaten = _anmeldung(zeitraum.jahr, absender, erstellt, steuerfall)
    return _umschlag(steuernummer, absender, kopf, nutzdaten)


def dauerfrist_xml(
    jahr: int,
    steuernummer: str,
    absender: Absender,
    kopf: Kopf,
    sondervorauszahlung: Decimal | None,
    berichtigt: bool,
    erstellt: date,
) -> str:
    """Antrag auf Dauerfristverlängerung, mit Sondervorauszahlung (Kz 38) für
    Monatszahler. Elementnamen nicht gegen das amtliche Schema geprüft."""
    felder = [
        _e("Jahr", str(jahr)),
        _e("Steuernummer", steuernummer),
        _e("Kz09", kopf.hersteller_id),
    ]
    if berichtigt:
        felder.append(_e("Kz10", "1"))
    if sondervorauszahlung is not None:
        felder.append(
            _e("Kz38", f"{sondervorauszahlung.quantize(Decimal('0.01')):.2f}")
        )
    steuerfall = "\n".join(
        ["<Dauerfristverlaengerung>", *felder, "</Dauerfristverlaengerung>"]
    )
    nutzdaten = _anmeldung(jahr, absender, erstellt, steuerfall)
    return _umschlag(steuernummer, absender, kopf, nutzdaten)


def _lokal(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def lies_kennzahlen(xml: str) -> dict[str, str]:
    """Felder des Steuerfalls (Jahr, Zeitraum, Steuernummer, Kz…) als Text."""
    wurzel = ET.fromstring(xml)
    for element in wurzel.iter():
        if _lokal(element.tag) in (
            "Umsatzsteuervoranmeldung",
            "Dauerfristverlaengerung",
        ):
            return {_lokal(k.tag): (k.text or "") for k in element}
    return {}


_BMG = re.compile(r"^-?\d+$")
_STEUER = re.compile(r"^-?\d+\.\d{2}$")


class _Pruefung:
    def __init__(self, testfall: bool) -> None:
        self.testfall = testfall
        self.befunde: list[Befund] = []
        self.finanzamt: str | None = None

    def fehler(self, text: str) -> None:
        self.befunde.append(Befund("datensatz", Schweregrad.FEHLER, text))

    def warnung(self, text: str) -> None:
        self.befunde.append(Befund("datensatz", Schweregrad.WARNUNG, text))

    def kopf(self, wurzel: ET.Element) -> str | None:
        e = {"e": ELSTER_NS}
        if wurzel.tag != f"{{{ELSTER_NS}}}Elster":
            self.fehler(f"Wurzel {wurzel.tag} statt Elster (Schema v11)")
            return None
        th = wurzel.find("e:TransferHeader", e)
        if th is None or th.get("version") != "11":
            self.fehler("TransferHeader version 11 fehlt")
            return None
        for feld, soll in (("Verfahren", "ElsterAnmeldung"), ("DatenArt", "UStVA")):
            if th.findtext(f"e:{feld}", namespaces=e) != soll:
                self.fehler(f"TransferHeader/{feld} ist nicht {soll}")
        testmerker = th.findtext("e:Testmerker", namespaces=e)
        if self.testfall and testmerker != TESTMERKER:
            self.fehler(
                f"Testmerker {TESTMERKER} fehlt — ohne ihn wäre es ein Echtfall"
            )
        if not self.testfall and testmerker:
            self.fehler(
                f"Testmerker {testmerker} im Echtfall — der Datensatz würde gelöscht"
            )
        hersteller = th.findtext("e:HerstellerID", namespaces=e) or ""
        if not hersteller.isdigit():
            self.fehler("HerstellerID fehlt oder ist nicht numerisch")
        elif hersteller == TEST_HERSTELLER_ID:
            text = (
                f"Hersteller-ID {TEST_HERSTELLER_ID} ist seit ERiC 39.4 gesperrt, auch "
                "für Testfälle — eigene Hersteller-ID eintragen (elster.hersteller_id)"
            )
            (self.warnung if self.testfall else self.fehler)(text)
        empfaenger = wurzel.find(
            "e:DatenTeil/e:Nutzdatenblock/e:NutzdatenHeader/e:Empfaenger", e
        )
        if empfaenger is None or empfaenger.get("id") != "F":
            self.fehler("NutzdatenHeader/Empfaenger id=F fehlt")
            return hersteller
        self.finanzamt = empfaenger.text or ""
        return hersteller

    def steuerfall(self, wurzel: ET.Element, hersteller: str | None) -> None:
        felder = lies_kennzahlen(ET.tostring(wurzel, encoding="unicode"))
        if not felder:
            self.fehler("Steuerfall (Umsatzsteuervoranmeldung) fehlt")
            return
        jahr = felder.get("Jahr", "")
        anmeldung = next(
            (x for x in wurzel.iter() if _lokal(x.tag) == "Anmeldungssteuern"), None
        )
        if (
            anmeldung is None
            or not jahr.isdigit()
            or anmeldung.tag != (f"{{{ustva_ns(int(jahr))}}}Anmeldungssteuern")
        ):
            self.fehler(f"Anmeldungssteuern nicht im Namensraum ustva/v{jahr}")
        elif anmeldung.get("version") != jahr:
            self.fehler(
                f"Anmeldungssteuern version={anmeldung.get('version')} ≠ {jahr}"
            )
        if "Zeitraum" in felder and felder["Zeitraum"] not in _ZEITRAEUME:
            self.fehler(f"Zeitraum {felder['Zeitraum']} unzulässig (01–12, 41–44)")
        stnr = felder.get("Steuernummer", "")
        if not (len(stnr) == 13 and stnr.isdigit() and stnr[4] == "0"):
            self.fehler(f"Steuernummer {stnr!r} nicht im 13-stelligen ELSTER-Format")
        elif self.finanzamt != finanzamtsnummer(stnr):
            self.fehler(
                f"Empfänger-Finanzamt {self.finanzamt} passt nicht zur "
                f"Steuernummer ({finanzamtsnummer(stnr)})"
            )
        if "Kz09" not in felder:
            self.fehler("Kz09 (Hersteller-ID) fehlt — Pflichtfeld")
        elif hersteller is not None and felder["Kz09"] != hersteller:
            self.fehler("Kz09 und HerstellerID weichen voneinander ab")
        self.kennzahlen(felder)

    def kennzahlen(self, felder: dict[str, str]) -> None:
        va = UStVoranmeldung(zeitraum="Prüfung")
        dauerfrist = "Zeitraum" not in felder
        for name, text in felder.items():
            if not name.startswith("Kz") or name in ("Kz09", "Kz83"):
                continue
            kz = int(name[2:])
            if dauerfrist and kz == 38:
                if not _STEUER.match(text):
                    self.fehler(
                        f"{name}={text!r}: erwartet Euro mit zwei Nachkommastellen"
                    )
                continue
            k = KENNZIFFERN_2026.get(kz)
            if k is None:
                self.fehler(f"{name} gibt es im Vordruck 2026 nicht")
                continue
            muster = _STEUER if k.art is Art.STEUER else _BMG
            if not muster.match(text):
                form = "Euro und Cent" if k.art is Art.STEUER else "volle Euro"
                self.fehler(f"{name}={text!r}: erwartet {form}")
                continue
            if k.art is not Art.MERKER:
                va.addiere(kz, Decimal(text))
        if dauerfrist:
            return
        if "Kz83" not in felder:
            self.fehler("Kz83 fehlt — ist in jedem Fall auszufüllen")
            return
        try:
            gemeldet = Decimal(felder["Kz83"])
        except InvalidOperation:
            self.fehler(f"Kz83={felder['Kz83']!r} ist keine Zahl")
            return
        if gemeldet != va.kz83:
            self.fehler(
                f"Kz 83 ({gemeldet}) stimmt nicht mit der Rechnung aus den Kennzahlen "
                f"überein ({va.kz83})"
            )


def pruefe_datensatz(xml: str, *, testfall: bool) -> list[Befund]:
    """Interne Prüfung des Datensatzes — Aufbau, Formate, Kz 83, Testmerker."""
    pruefung = _Pruefung(testfall)
    try:
        wurzel = ET.fromstring(xml)
    except ET.ParseError as fehler:
        pruefung.fehler(f"Datensatz nicht wohlgeformt: {fehler}")
        return pruefung.befunde
    hersteller = pruefung.kopf(wurzel)
    pruefung.steuerfall(wurzel, hersteller)
    return pruefung.befunde
