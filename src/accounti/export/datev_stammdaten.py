"""Debitoren und Kreditoren im DATEV-Format (Formatkategorie 16, Version 5).

Quelle sind die Kontakte aus Baustein 4. Ein Kontakt mit beiden Rollen ergibt zwei
Sätze (Debitor und Kreditor), die über „Verknüpftes OPOS-Konto“ aufeinander zeigen.
Belegt werden: Konto, Name (Adressattyp Unternehmen), Kurzbezeichnung, EU-Land und
USt-IdNr. (ohne Länderpräfix, wie in DATEVs Musterdatei), Anschrift, E-Mail,
Bankverbindung (IBAN als Hauptbankverbindung), Steuernummer, Zahlungsbedingungen
(Debitor: Fälligkeit und Skonto-Prozent; Kreditor: Skontofrist und -satz als Ziel 1,
Nettofälligkeit als Ziel 3) und als „Nummer Fremdsystem“ die Kontakt-ID.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from accounti.export.datev_felder import DEBITOREN_KREDITOREN as FELDER
from accounti.export.datev_format import (
    DatevFormatError,
    Kopf,
    Wert,
    feldnummer,
    kontoart,
    schreibe_extf,
)
from accounti.models import Kontakt


@dataclass(frozen=True)
class DatevMandant:
    berater: int
    mandant: int
    wj_beginn: date
    sachkontenlaenge: int = 4
    skr: str = "03"


def _nr(name: str) -> int:
    return feldnummer(FELDER, name)


_F = {
    "konto": _nr("Konto"),
    "name": _nr("Name (Adressattyp Unternehmen)"),
    "adressattyp": _nr("Adressattyp"),
    "kurz": _nr("Kurzbezeichnung"),
    "eu_land": _nr("EU-Land"),
    "eu_ustid": _nr("EU-UStID"),
    "adressart": _nr("Adressart"),
    "strasse": _nr("Straße"),
    "plz": _nr("Postleitzahl"),
    "ort": _nr("Ort"),
    "land": _nr("Land"),
    "korrespondenz": _nr("Kennz. Korrespondenzadresse"),
    "email": _nr("E-Mail"),
    "laenderkz": _nr("Länderkennzeichen 1"),
    "iban": _nr("IBAN-Nr. 1"),
    "haupt": _nr("Kennz. Hauptbankverb. 1"),
    "steuernummer": _nr("Steuernummer"),
    "faellig_deb": _nr("Fälligkeit in Tagen (Debitor)"),
    "skonto_deb": _nr("Skonto in Prozent (Debitor)"),
    "ziel1": _nr("Kreditoren-Ziel 1 Tg."),
    "skonto1": _nr("Kreditoren-Skonto 1 %"),
    "ziel3": _nr("Kreditoren-Ziel 3 Brutto Tg."),
    "fremd": _nr("Nummer Fremdsystem"),
    "opos": _nr("Verknüpftes OPOS-Konto"),
}


def _kurz(text: str | None, laenge: int) -> str | None:
    return text[:laenge].rstrip() if text else None


def _satz(
    k: Kontakt, konto: str, rolle: str, gegenkonto: str | None
) -> dict[int, Wert]:
    satz: dict[int, Wert] = {
        _F["konto"]: konto,
        _F["name"]: _kurz(k.name, 50),
        _F["adressattyp"]: "2",
        _F["kurz"]: _kurz(k.name, 15),
        _F["email"]: _kurz(k.email, 60),
        _F["steuernummer"]: _kurz(k.steuernummer, 20),
        _F["fremd"]: k.id.hex[:15],
        _F["opos"]: gegenkonto,
    }
    ust_id = re.sub(r"\s", "", k.ust_id or "").upper()
    if re.match(r"[A-Z]{2}\w+$", ust_id):
        satz[_F["eu_land"]] = ust_id[:2]
        satz[_F["eu_ustid"]] = ust_id[2:]
    if k.strasse or k.plz or k.ort:
        satz.update(
            {
                _F["adressart"]: "STR",
                _F["strasse"]: _kurz(k.strasse, 36),
                _F["plz"]: _kurz(k.plz, 10),
                _F["ort"]: _kurz(k.ort, 30),
                _F["korrespondenz"]: 1,
            }
        )
    if k.land and k.land.upper() != "DE":
        satz[_F["land"]] = k.land.upper()
    if k.iban:
        iban = re.sub(r"\s", "", k.iban).upper()
        satz.update({_F["iban"]: iban, _F["laenderkz"]: iban[:2], _F["haupt"]: "1"})
    if rolle == "debitor":
        satz[_F["faellig_deb"]] = k.zahlungsziel_tage
        satz[_F["skonto_deb"]] = k.skonto_prozent if k.skonto_tage else None
    else:
        if k.skonto_prozent is not None and k.skonto_tage is not None:
            satz[_F["ziel1"]] = k.skonto_tage
            satz[_F["skonto1"]] = k.skonto_prozent
        satz[_F["ziel3"]] = k.zahlungsziel_tage
    return satz


def stammdaten_saetze(
    kontakte: list[Kontakt], sachkontenlaenge: int = 4
) -> list[dict[int, Wert]]:
    """Ein Satz je Personenkonto, nach Kontonummer sortiert."""
    saetze = []
    for k in kontakte:
        rollen = [
            ("debitor", k.debitor_konto, k.kreditor_konto),
            ("kreditor", k.kreditor_konto, k.debitor_konto),
        ]
        for rolle, konto, gegenkonto in rollen:
            if konto is None:
                continue
            if kontoart(konto, sachkontenlaenge) != "personenkonto":
                msg = (
                    f"Kontakt {k.name}: Personenkonto {konto} passt nicht zur "
                    f"Sachkontenlänge {sachkontenlaenge} (erwartet "
                    f"{sachkontenlaenge + 1} Stellen)"
                )
                raise DatevFormatError(msg)
            saetze.append(_satz(k, konto, rolle, gegenkonto))
    return sorted(saetze, key=lambda s: str(s[_F["konto"]]))


def exportiere_stammdaten(
    kontakte: list[Kontakt],
    mandant: DatevMandant,
    ausgabe: str | Path,
    erzeugt_am: datetime | None = None,
) -> tuple[Path, int]:
    """Schreibt ``EXTF_DebKred_Stamm_<Datum>.csv``; liefert Pfad und Anzahl Sätze."""
    erzeugt_am = erzeugt_am or datetime.now()
    saetze = stammdaten_saetze(kontakte, mandant.sachkontenlaenge)
    kopf = Kopf(
        kategorie=16,
        formatname="Debitoren/Kreditoren",
        formatversion=5,
        berater=mandant.berater,
        mandant=mandant.mandant,
        wj_beginn=mandant.wj_beginn,
        sachkontenlaenge=mandant.sachkontenlaenge,
        skr=mandant.skr,
        erzeugt_am=erzeugt_am,
    )
    ordner = Path(ausgabe)
    ordner.mkdir(parents=True, exist_ok=True)
    pfad = ordner / f"EXTF_DebKred_Stamm_{erzeugt_am:%Y%m%d}.csv"
    pfad.write_bytes(schreibe_extf(kopf, FELDER, saetze))
    return pfad, len(saetze)


def wirtschaftsjahr_beginn(stichtag: date, beginn: date | None = None) -> date:
    """Beginn des Wirtschaftsjahrs, in dem ``stichtag`` liegt.

    ``beginn`` ist irgendein Beginn aus der Konfiguration; maßgeblich sind nur Tag und
    Monat (abweichendes Wirtschaftsjahr, § 4a EStG). Ohne Angabe: 1. Januar.
    """
    monat, tag = (beginn.month, beginn.day) if beginn else (1, 1)
    kandidat = date(stichtag.year, monat, min(tag, 28) if monat == 2 else tag)
    if kandidat > stichtag:
        kandidat = kandidat.replace(year=stichtag.year - 1)
    return kandidat


def lade_datev_mandant(
    pfad: str | Path,
    stichtag: date,
    berater: str | None = None,
    mandant: str | None = None,
) -> DatevMandant:
    """Berater-/Mandantennummer aus Optionen oder Abschnitt ``datev`` der Konfiguration.

    Sachkontenlänge aus ``mandant.sachkonten_laenge`` (Standard 4), Kontenrahmen aus
    ``buchhaltung.kontenrahmen`` bzw. ``mandant.kontenrahmen`` (SKR03 → ``03``),
    Wirtschaftsjahresbeginn aus ``datev.wirtschaftsjahr_beginn`` (Tag und Monat,
    Standard 1. Januar) für das Wirtschaftsjahr, in dem ``stichtag`` liegt.
    """
    import yaml

    from accounti.konfiguration import KonfigurationError

    daten: dict[str, object] = {}
    datei = Path(pfad)
    if datei.is_file():
        geladen = yaml.safe_load(datei.read_text(encoding="utf-8")) or {}
        daten = geladen if isinstance(geladen, dict) else {}

    def abschnitt(name: str) -> dict[str, object]:
        wert = daten.get(name)
        return wert if isinstance(wert, dict) else {}

    datev = abschnitt("datev")
    firma = abschnitt("mandant")
    buchhaltung = abschnitt("buchhaltung")
    berater = berater or str(datev.get("berater_nummer") or "") or None
    mandant = mandant or str(datev.get("mandanten_nummer") or "") or None
    if not berater or not berater.isdigit():
        msg = "Beraternummer fehlt — --berater angeben oder datev.berater_nummer setzen"
        raise KonfigurationError(msg)
    if not mandant or not mandant.isdigit():
        msg = (
            "Mandantennummer fehlt — --mandant angeben oder "
            "datev.mandanten_nummer setzen"
        )
        raise KonfigurationError(msg)
    beginn = datev.get("wirtschaftsjahr_beginn")
    if isinstance(beginn, str):
        try:
            beginn = date.fromisoformat(beginn)
        except ValueError as fehler:
            msg = f"datev.wirtschaftsjahr_beginn {beginn!r}: Format JJJJ-MM-TT"
            raise KonfigurationError(msg) from fehler
    wj = wirtschaftsjahr_beginn(stichtag, beginn if isinstance(beginn, date) else None)
    rahmen = str(
        buchhaltung.get("kontenrahmen") or firma.get("kontenrahmen") or "SKR03"
    )
    laenge = firma.get("sachkonten_laenge", 4)
    return DatevMandant(
        berater=int(berater),
        mandant=int(mandant),
        wj_beginn=wj,
        sachkontenlaenge=int(laenge) if isinstance(laenge, int | str) else 4,
        skr=rahmen.upper().removeprefix("SKR")[-2:].zfill(2),
    )
