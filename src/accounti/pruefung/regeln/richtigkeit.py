"""Richtigkeit: stimmt, was gebucht und belegt ist? (§ 14 UStG, § 33 UStDV, GoBD)"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from functools import cached_property
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from accounti.anzeige import betrag_de, datum_de
from accounti.db.repository import lade_bankkonten
from accounti.konfiguration import Buchhaltung, KonfigurationError
from accounti.kontakte.erkennung import normalisiere_name
from accounti.kontakte.ustid import aktuelle_bestaetigung, normalisiere
from accounti.models import (
    Beleg,
    Belegart,
    Belegrichtung,
    BelegStatus,
    Buchungssatz,
    BuchungStatus,
    Kontakt,
)
from accounti.models.pruefung import Befund, Kategorie, Schwere
from accounti.pruefung.einstellungen import PruefEinstellungen
from accounti.pruefung.regeln import Kontext, befund, registriere_pruefregel
from accounti.steuer.eu_steuersaetze import EU_STEUERSAETZE, ist_eu_land
from accounti.steuer.kennziffern import (
    KENNZIFFERN_KONTEN,
    STEUERSCHLUESSEL,
    Kontenplan,
)
from accounti.steuer.umsatzsteuer import OSS_ERLOES_KONTEN_SKR03

if TYPE_CHECKING:
    from accounti.pruefung.belegangaben import Belegangaben

NULL = Decimal("0")
VORSTEUER = frozenset(s for s, r in STEUERSCHLUESSEL.items() if r.vorsteuer)
# § 13b und ig. Erwerb: Steuer und Vorsteuer berechnet der Empfänger selbst
SELBST_BERECHNET = frozenset(
    s for s, r in STEUERSCHLUESSEL.items() if r.vorsteuer and r.bmg is not None
)
UMSATZSTEUER = frozenset({2, 3})
IG_ERWERB = frozenset({18, 19})
# Aufwandskonten je Kontenrahmen (Wareneingang, betriebliche und neutrale Aufwendungen)
AUFWAND: dict[str, tuple[tuple[int, int], ...]] = {
    "SKR03": ((2000, 2499), (3000, 3969), (4000, 4999)),
    "SKR04": ((5000, 7999),),
}
_USTID_LAND = {"EL": "GR", "XI": "GB"}
_FREIGEGEBEN = frozenset(
    {
        BuchungStatus.AUTO_GEBUCHT,
        BuchungStatus.GEPRUEFT,
        BuchungStatus.KORRIGIERT,
        BuchungStatus.EXPORTIERT,
    }
)


def _land_aus_ustid(ust_id: str | None) -> str | None:
    if not ust_id or len(ust_id) < 2 or not ust_id[:2].isalpha():
        return None
    land = ust_id[:2].upper()
    return _USTID_LAND.get(land, land)


def _lies_angaben(b: Beleg, k: Kontext) -> Belegangaben:
    """Angaben aus dem Original — erst hier geladen: ``belegangaben`` zieht die
    Belegerkennung nach (Sekunden beim Import), die Steuerschlüssel-Prüfung von
    ``korrigiere`` und der Export brauchen sie nicht."""
    from accounti.pruefung.belegangaben import lies_angaben

    return lies_angaben(b, k.archiv, k.ocr)


def _prozent(satz: Decimal) -> str:
    """Steuersatz ohne Exponentenschreibweise: 20 %, 5,5 % (nicht „2E+1 %“)."""
    return f"{satz.normalize():f}".replace(".", ",") + " %"


def _saetze(b: Beleg) -> list[Decimal]:
    return [p.steuersatz for p in b.positionen if p.steuersatz is not None]


def _rechnung(b: Beleg) -> str:
    return (
        f"Rechnung {b.belegnummer or b.dateiname} von {b.lieferant_name or '—'} "
        f"({datum_de(b.belegdatum)})"
    )


def _schwerste(probleme: list[tuple[Schwere, str]]) -> Schwere:
    return max((s for s, _ in probleme), key=lambda s: s.rang)


# --- § 14 Abs. 4 UStG / § 33 UStDV / § 14a UStG -------------------------------------

# Hinweis „Steuerschuldnerschaft des Leistungsempfängers“ (§ 14a Abs. 5 UStG)
_HINWEIS_13B = re.compile(
    r"steuerschuldnerschaft\s+des\s+leistungsempf|reverse[\s-]*charge|"
    r"§\s*13\s*b|autoliquidation|inversione\s+contabile|btw\s+verlegd",
    re.IGNORECASE,
)
# Hinweis auf die steuerfreie innergemeinschaftliche Lieferung (§ 14 Abs. 4 Nr. 8)
_HINWEIS_6A = re.compile(
    r"innergemeinschaftliche\s+lieferung|intra[\s-]*community\s+(?:supply|delivery)|"
    r"§\s*4\s*nr\.?\s*1\s*b|§\s*6\s*a|art(?:ikel|icle|\.)?\s*138|"
    r"livraison\s+intracommunautaire",
    re.IGNORECASE,
)
_SCHLUESSEL_13B = frozenset({91, 94})
_SCHLUESSEL_6A = frozenset({18, 19})  # ig. Erwerb beim Empfänger = § 6a beim Lieferer


class Pflichtangaben:
    name = "pflichtangaben"
    kategorie = Kategorie.RICHTIGKEIT
    schwere = Schwere.FEHLER
    beschreibung = "Pflichtangaben nach § 14 Abs. 4 UStG (Kleinbetrag: § 33 UStDV)"

    class Parameter(BaseModel):
        belegarten: list[Belegart] = Field(
            default_factory=lambda: [Belegart.EINGANGSRECHNUNG]
        )

    def _klein(self, b: Beleg, a: Belegangaben) -> list[tuple[Schwere, str]]:
        fehlt: list[tuple[Schwere, str]] = []
        if not (a.leistender_name or b.lieferant_name):
            fehlt.append((Schwere.FEHLER, "Name des leistenden Unternehmers (Nr. 1)"))
        if a.leistender_anschrift is False:
            fehlt.append((Schwere.WARNUNG, "Anschrift des Leistenden (Nr. 1)"))
        if b.belegdatum is None:
            fehlt.append((Schwere.FEHLER, "Ausstellungsdatum (Nr. 2)"))
        if a.leistungsbeschreibung is False:
            fehlt.append((Schwere.WARNUNG, "Menge und Art der Leistung (Nr. 3)"))
        if b.brutto is None:
            fehlt.append((Schwere.FEHLER, "Entgelt und Steuer in einer Summe (Nr. 4)"))
        if not _saetze(b) and not a.steuerbefreiung and b.steuer is None:
            fehlt.append((Schwere.FEHLER, "Steuersatz (Nr. 4)"))
        return fehlt

    def _sonderfall(
        self, b: Beleg, a: Belegangaben, schluessel: set[int | None], oss: bool
    ) -> str | None:
        """§ 13b, § 6a oder § 3c — dann gilt § 33 UStDV nicht (§ 33 Satz 3 UStDV)."""
        if schluessel & _SCHLUESSEL_13B or "AE" in a.steuerkategorien:
            return "§ 13b"
        if schluessel & _SCHLUESSEL_6A or "K" in a.steuerkategorien:
            return "§ 6a"
        if oss:
            return "§ 3c"
        if a.text and _HINWEIS_13B.search(a.text):
            return "§ 13b"
        if a.text and _HINWEIS_6A.search(a.text):
            return "§ 6a"
        return None

    def _14a(
        self, k: Kontext, b: Beleg, a: Belegangaben, fall: str
    ) -> list[tuple[Schwere, str]]:
        """§ 14a UStG: USt-IdNr. beider Seiten und der Hinweis auf den Sonderfall.

        Nur Warnungen: Der Vorsteuerabzug aus § 13b und aus dem ig. Erwerb hängt nicht
        an der Rechnung (§ 15 Abs. 1 Nr. 3 und 4 UStG)."""
        if fall == "§ 3c":
            return []
        eigene = _kompakt(k.firma.ust_id) if k.firma and k.firma.ust_id else ""
        alle = {_kompakt(x) for x in [*a.ust_ids, b.lieferant_ust_id] if x}
        fremde = alle - {eigene}
        if eigene:
            empfaenger = eigene in alle or eigene in _kompakt(a.text)
        else:
            empfaenger = len(alle) >= 2
        empfaenger = empfaenger or bool(a.empfaenger_ust_id)
        kontakt = k.kontakt_zum_beleg(b)
        land = kontakt.land.upper() if kontakt else None
        land = land or next((_land_aus_ustid(x) for x in fremde), None)
        nicht_gelesen = "" if a.gelesen else " nicht erkannt — Original nicht geprüft"
        inland = land == "DE"

        def zitat(absatz: str, nummer: str) -> str:
            """Inländischer Leistender: § 14a UStG; sonst das Recht seines Staats."""
            if inland:
                return f"§ 14a {absatz} UStG"
            return f"Art. 226 {nummer} MwStSystRL, Recht des Sitzstaats"

        fehlt: list[tuple[Schwere, str]] = []
        if fall == "§ 13b":
            if not inland:  # Leistender im Ausland: § 13b Abs. 1 bzw. Abs. 2 Nr. 1
                if not fremde:
                    fehlt.append(
                        (
                            Schwere.WARNUNG,
                            "USt-IdNr. des leistenden Unternehmers "
                            f"({zitat('Abs. 1', 'Nr. 3')})" + nicht_gelesen,
                        )
                    )
                if a.gelesen and not empfaenger:
                    fehlt.append(
                        (
                            Schwere.WARNUNG,
                            "USt-IdNr. des Leistungsempfängers "
                            f"({zitat('Abs. 1', 'Nr. 4')})",
                        )
                    )
            hinweis = "AE" in a.steuerkategorien or _HINWEIS_13B.search(a.text or "")
            if a.gelesen and not hinweis:
                fehlt.append(
                    (
                        Schwere.WARNUNG,
                        "Hinweis „Steuerschuldnerschaft des Leistungsempfängers“ "
                        f"({zitat('Abs. 5', 'Nr. 11a')})",
                    )
                )
            return fehlt
        if not fremde:  # § 6a
            fehlt.append(
                (
                    Schwere.WARNUNG,
                    f"USt-IdNr. des Lieferers ({zitat('Abs. 3', 'Nr. 3')})"
                    + nicht_gelesen,
                )
            )
        if a.gelesen and not empfaenger:
            fehlt.append(
                (
                    Schwere.WARNUNG,
                    f"USt-IdNr. des Leistungsempfängers ({zitat('Abs. 3', 'Nr. 4')})",
                )
            )
        hinweis = "K" in a.steuerkategorien or _HINWEIS_6A.search(a.text or "")
        if a.gelesen and not hinweis:
            fehlt.append(
                (
                    Schwere.WARNUNG,
                    "Hinweis auf die steuerfreie innergemeinschaftliche Lieferung ("
                    + (
                        "§ 14 Abs. 4 Nr. 8, § 14a Abs. 3 UStG"
                        if inland
                        else "Art. 226 Nr. 11 MwStSystRL, Recht des Sitzstaats"
                    )
                    + ")",
                )
            )
        return fehlt

    def _voll(
        self, b: Beleg, a: Belegangaben, fall: str | None = None
    ) -> list[tuple[Schwere, str]]:
        fehlt: list[tuple[Schwere, str]] = []
        if not (a.leistender_name or b.lieferant_name):
            fehlt.append((Schwere.FEHLER, "Nr. 1 Name des leistenden Unternehmers"))
        if a.leistender_anschrift is False:
            fehlt.append(
                (Schwere.WARNUNG, "Nr. 1 Anschrift des leistenden Unternehmers")
            )
        if a.quelle == "erechnung" and not a.empfaenger_name:
            fehlt.append((Schwere.WARNUNG, "Nr. 1 Name des Leistungsempfängers"))
        if not (a.steuernummer or a.ust_ids or b.lieferant_ust_id):
            fehlt.append(
                (
                    Schwere.FEHLER if a.gelesen else Schwere.WARNUNG,
                    "Nr. 2 Steuernummer oder USt-IdNr. des leistenden Unternehmers"
                    + (
                        " (kein Vorsteuerabzug, § 15 Abs. 1 Nr. 1 UStG)"
                        if a.gelesen
                        else " nicht erkannt — Original nicht geprüft"
                    ),
                )
            )
        if b.belegdatum is None:
            fehlt.append((Schwere.FEHLER, "Nr. 3 Ausstellungsdatum"))
        if not b.belegnummer:
            fehlt.append((Schwere.FEHLER, "Nr. 4 Rechnungsnummer"))
        if a.leistungsbeschreibung is False:
            fehlt.append((Schwere.FEHLER, "Nr. 5 Menge und Art der Leistung"))
        if a.leistungszeitpunkt is False:
            fehlt.append(
                (
                    Schwere.HINWEIS,
                    "Nr. 6 Zeitpunkt der Leistung (nur entbehrlich, wenn er dem "
                    "Rechnungsdatum entspricht — dann so vermerken)",
                )
            )
        if b.netto is None and not b.positionen:
            fehlt.append((Schwere.FEHLER, "Nr. 7 Entgelt nach Steuersätzen"))
        steuer = b.steuer is not None or any(
            p.steuer_betrag is not None for p in b.positionen
        )
        if fall in ("§ 13b", "§ 6a"):
            return fehlt  # ohne deutsche Steuer: Hinweis nach § 14a (siehe _14a)
        if not steuer and not a.steuerbefreiung:
            fehlt.append(
                (
                    Schwere.FEHLER,
                    "Nr. 8 Steuerbetrag (oder Hinweis auf eine Steuerbefreiung)",
                )
            )
        elif steuer and not _saetze(b) and not a.steuerbefreiung:
            fehlt.append((Schwere.WARNUNG, "Nr. 8 Steuersatz"))
        return fehlt

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        grenze = k.einstellungen.kleinbetrag_grenze
        befunde = []
        nur_felder = 0
        schluessel: dict[Any, set[int | None]] = defaultdict(set)
        oss: set[Any] = set()
        oss_konten = set(OSS_ERLOES_KONTEN_SKR03.values())
        for x in k.buchungen:
            if x.beleg_id is not None and not (x.storno_von or x.storniert_durch):
                schluessel[x.beleg_id].add(x.steuer_schluessel)
                if {x.soll_konto, x.haben_konto} & oss_konten:
                    oss.add(x.beleg_id)
        for b in k.belege.values():
            if b.belegart not in p.belegarten or b.status is not BelegStatus.ERFASST:
                continue
            if not k.im_zeitraum(b.belegdatum or b.eingegangen_am.date()):
                continue
            a = _lies_angaben(b, k)
            nur_felder += not a.gelesen
            fall = self._sonderfall(b, a, schluessel[b.id], b.id in oss)
            klein = b.brutto is not None and abs(b.brutto) <= grenze and fall is None
            if klein:
                fehlt = self._klein(b, a)
            else:
                fehlt = self._voll(b, a, fall)
                if fall is not None:
                    fehlt += self._14a(k, b, a, fall)
            if not fehlt:
                continue
            vorschrift = (
                "§ 33 UStDV (Kleinbetrag)"
                if klein
                else (
                    f"§ 14 Abs. 4 und § 14a UStG ({fall} UStG, keine "
                    "Kleinbetragsrechnung)"
                    if fall is not None
                    else "§ 14 Abs. 4 UStG"
                )
            )
            befunde.append(
                befund(
                    self,
                    "beleg",
                    b.id,
                    f"{_rechnung(b)} unvollständig nach {vorschrift} — fehlt: "
                    + "; ".join(text for _, text in fehlt),
                    schwere=_schwerste(fehlt),
                    datum=b.belegdatum,
                    betrag=b.brutto,
                    gegenpartei=b.lieferant_name,
                    abhilfe="berichtigte Rechnung beim Lieferanten anfordern",
                )
            )
        if nur_felder:
            befunde.append(
                befund(
                    self,
                    "pruefung",
                    "archiv",
                    f"{nur_felder} Beleg(e) nur aus den gespeicherten Feldern geprüft "
                    "(Original nicht im Archiv oder Scan ohne Text) — --archiv bzw. "
                    "--ocr angeben",
                    schwere=Schwere.HINWEIS,
                )
            )
        return befunde


# --- Rechenprobe ----------------------------------------------------------------------

_IM_BRUTTO = {2: Decimal("7"), 3: Decimal("19"), 8: Decimal("7"), 9: Decimal("19")}


class Rechenprobe:
    name = "rechenprobe"
    kategorie = Kategorie.RICHTIGKEIT
    schwere = Schwere.FEHLER
    beschreibung = "Netto + Steuer = Brutto, Summe der Positionen, Steuer zum Satz"

    class Parameter(BaseModel):
        toleranz: Decimal = Field(default=Decimal("0.02"), ge=0)
        toleranz_buchung: Decimal = Field(default=Decimal("0.05"), ge=0)

    def _beleg(self, b: Beleg, p: Parameter) -> list[str]:
        fehler = []
        if (
            b.netto is not None
            and b.steuer is not None
            and b.brutto is not None
            and abs(b.netto + b.steuer - b.brutto) > p.toleranz
        ):
            fehler.append(
                f"Netto {betrag_de(b.netto)} + Steuer {betrag_de(b.steuer)} ≠ "
                f"Brutto {betrag_de(b.brutto)}"
            )
        echte = [x for x in b.positionen if x.bezeichnung != "Gesamtbetrag"]
        if echte and b.netto is not None:
            summe = sum((x.netto for x in echte), NULL)
            if abs(summe - b.netto) > p.toleranz:
                fehler.append(
                    f"Summe der Positionen {betrag_de(summe)} ≠ Netto "
                    f"{betrag_de(b.netto)}"
                )
        mit_steuer = [x for x in echte if x.steuer_betrag is not None]
        if mit_steuer and b.steuer is not None:
            summe = sum((x.steuer_betrag or NULL for x in mit_steuer), NULL)
            if abs(summe - b.steuer) > p.toleranz:
                fehler.append(
                    f"Steuer der Positionen {betrag_de(summe)} ≠ Steuer "
                    f"{betrag_de(b.steuer)}"
                )
        for x in mit_steuer:
            if x.steuersatz is None or x.steuer_betrag is None:
                continue
            soll = (x.netto * x.steuersatz / 100).quantize(Decimal("0.01"))
            if abs(soll - x.steuer_betrag) > p.toleranz:
                fehler.append(
                    f"Position „{x.bezeichnung}“: {_prozent(x.steuersatz)} auf "
                    f"{betrag_de(x.netto)} sind {betrag_de(soll)}, ausgewiesen "
                    f"{betrag_de(x.steuer_betrag)}"
                )
        return fehler

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        befunde = []
        for b in k.belege.values():
            if b.status is BelegStatus.EINGEGANGEN:
                continue
            if not k.im_zeitraum(b.belegdatum or b.eingegangen_am.date()):
                continue
            fehler = self._beleg(b, p)
            if fehler:
                befunde.append(
                    befund(
                        self,
                        "beleg",
                        b.id,
                        f"{_rechnung(b)}: Rechenprobe — " + "; ".join(fehler),
                        datum=b.belegdatum,
                        betrag=b.brutto,
                        gegenpartei=b.lieferant_name,
                    )
                )
        for x in k.buchungen:
            if not k.im_zeitraum(x.datum) or x.steuer_schluessel not in _IM_BRUTTO:
                continue
            if x.steuer_betrag is None:
                continue
            satz = _IM_BRUTTO[x.steuer_schluessel]
            soll = (x.betrag_netto * satz / 100).quantize(Decimal("0.01"))
            if abs(soll - x.steuer_betrag) > p.toleranz_buchung:
                befunde.append(
                    befund(
                        self,
                        "buchung",
                        x.id,
                        f"Buchung {str(x.id)[:8]} ({x.soll_konto} an {x.haben_konto}): "
                        f"Steuer {betrag_de(x.steuer_betrag)} passt nicht zu "
                        f"{satz} % auf {betrag_de(x.betrag_netto)} ({betrag_de(soll)})",
                        schwere=Schwere.WARNUNG,
                        datum=x.datum,
                        betrag=x.betrag_netto,
                    )
                )
        return befunde


# --- Steuerschlüssel ./. Sachkonto (Akzeptanz 3) ------------------------------


def _lade_konten(
    einstellungen: PruefEinstellungen, kontenrahmen: str
) -> dict[str, dict[str, Any]]:
    """Konten der Kontenrahmen-Datei: ``pruefung.kontenrahmen_datei`` oder für SKR03
    die mitgelieferte ``accounti/pruefung/skr03.yaml`` — nicht abhängig vom
    Arbeitsverzeichnis. Eine fehlende oder kaputte Datei ist ein Fehler der
    Konfiguration."""
    if einstellungen.kontenrahmen_datei:
        pfad = Path(einstellungen.kontenrahmen_datei)
        name = str(pfad)
        if not pfad.is_file():
            raise KonfigurationError(f"Kontenrahmen-Datei {name} fehlt")
        text = pfad.read_text(encoding="utf-8")
    elif kontenrahmen.upper() == "SKR03":
        name = "accounti/pruefung/skr03.yaml"
        text = (
            resources.files("accounti.pruefung")
            .joinpath("skr03.yaml")
            .read_text(encoding="utf-8")
        )
    else:
        return {}
    try:
        daten: Any = yaml.safe_load(text) or {}
    except yaml.YAMLError as fehler:
        raise KonfigurationError(f"Kontenrahmen-Datei {name}: {fehler}") from fehler
    konten = daten.get("konten") if isinstance(daten, dict) else None
    if not isinstance(konten, dict):
        raise KonfigurationError(
            f"Kontenrahmen-Datei {name}: Abschnitt 'konten' fehlt oder ist keine "
            "Zuordnung"
        )
    return {str(n): w for n, w in konten.items() if isinstance(w, dict)}


def automatikkonten(
    buchhaltung: Buchhaltung, einstellungen: PruefEinstellungen | None = None
) -> dict[str, int]:
    """DATEV-Automatikkonten (AV/AM) mit dem Schlüssel ihrer Automatik — ohne die
    steuerfreien (8100, 8125: Automatik ohne Schlüssel)."""
    ergebnis = {}
    for konto, eintrag in _lade_konten(
        einstellungen or PruefEinstellungen(), buchhaltung.kontenrahmen
    ).items():
        steuer = eintrag.get("steuer") or {}
        if steuer.get("automatik") and steuer.get("schluessel") is not None:
            ergebnis[konto] = int(steuer["schluessel"])
    return ergebnis


class _Kontenwissen:
    """Steuerautomatik der Konten (Kontenrahmen-Datei) und Bereiche."""

    def __init__(
        self,
        session: Session,
        buchhaltung: Buchhaltung,
        einstellungen: PruefEinstellungen,
    ) -> None:
        self.session = session
        self.buchhaltung = buchhaltung
        self.einstellungen = einstellungen
        self.kr = buchhaltung.kontenrahmen.upper()

    @cached_property
    def plan(self) -> Kontenplan:
        b = self.buchhaltung
        geld = {konto.sachkonto for konto in lade_bankkonten(self.session)}
        return Kontenplan(
            kontenrahmen=self.kr,
            debitoren=(b.debitoren_von, b.debitoren_bis),
            kreditoren=(b.kreditoren_von, b.kreditoren_bis),
            geldkonten=frozenset(geld | {b.bank_konto}),
        )

    @cached_property
    def konten(self) -> dict[str, dict[str, Any]]:
        return _lade_konten(self.einstellungen, self.kr)

    def ist_aufwand(self, konto: str) -> bool:
        eintrag = self.konten.get(konto)
        if eintrag is not None:
            return bool(eintrag.get("typ") == "aufwand")
        nr = int(konto[:4]) if konto.isdigit() and len(konto) >= 4 else None
        return nr is not None and any(
            von <= nr <= bis for von, bis in AUFWAND.get(self.kr, ())
        )

    def automatik(self, konto: str) -> int | None:
        steuer = (self.konten.get(konto) or {}).get("steuer") or {}
        if steuer.get("automatik") and steuer.get("schluessel") is not None:
            return int(steuer["schluessel"])
        return None

    def ohne_vorsteuer(self, konto: str) -> str | None:
        """Name eines Aufwandskontos ohne Vorsteuerfunktion laut Kontenrahmen-Datei
        (``steuer.vorsteuer: false`` — z.B. Löhne, Versicherungen, Abschreibungen)."""
        eintrag = self.konten.get(konto) or {}
        steuer = eintrag.get("steuer") or {}
        if eintrag.get("typ") == "aufwand" and steuer.get("vorsteuer") is False:
            return str(eintrag.get("name") or konto)
        return None


def _schluesselname(s: int) -> str:
    regel = STEUERSCHLUESSEL.get(s)
    return f"{s} ({regel.bezeichnung})" if regel else str(s)


class SteuerschluesselKonto:
    name = "steuerschluessel_konto"
    kategorie = Kategorie.RICHTIGKEIT
    schwere = Schwere.FEHLER
    beschreibung = (
        "Steuerschlüssel passt nicht zum Sachkonto (Steuerautomatik, Kontoart)"
    )

    class Parameter(BaseModel):
        pass

    def _sachkonten(self, x: Buchungssatz, w: _Kontenwissen) -> list[str]:
        soll_gegen = w.plan.ist_gegenkonto(x.soll_konto)
        haben_gegen = w.plan.ist_gegenkonto(x.haben_konto)
        if soll_gegen and haben_gegen:
            return []
        if soll_gegen != haben_gegen:
            return [x.haben_konto if soll_gegen else x.soll_konto]
        return [x.soll_konto, x.haben_konto]

    def _konto(
        self, konto: str, x: Buchungssatz, w: _Kontenwissen
    ) -> list[tuple[Schwere, str]]:
        s = x.steuer_schluessel
        probleme: list[tuple[Schwere, str]] = []
        if s in VORSTEUER and w.plan.ist_erloeskonto(konto):
            probleme.append(
                (
                    Schwere.FEHLER,
                    f"Vorsteuerschlüssel {_schluesselname(s)} auf Erlöskonto {konto}",
                )
            )
        elif s in UMSATZSTEUER and w.ist_aufwand(konto):
            probleme.append(
                (
                    Schwere.FEHLER,
                    f"Umsatzsteuerschlüssel {_schluesselname(s)} auf Aufwandskonto "
                    f"{konto}",
                )
            )
        funktion = KENNZIFFERN_KONTEN.get(w.kr, {})
        if s in STEUERSCHLUESSEL and konto in funktion:
            probleme.append(
                (
                    Schwere.FEHLER,
                    f"Konto {konto} hat eine feste Steuerfunktion (Kennziffer "
                    f"{funktion[konto]}) und verträgt keinen Schlüssel "
                    f"{_schluesselname(s)}",
                )
            )
        auto = w.automatik(konto)
        if auto is not None and s is not None and s != auto:
            probleme.append(
                (
                    Schwere.FEHLER,
                    f"Konto {konto} ist Automatikkonto mit Schlüssel "
                    f"{_schluesselname(auto)}, gebucht mit {_schluesselname(s)}",
                )
            )
        elif auto is not None and s is None and not x.steuer_betrag:
            probleme.append(
                (
                    Schwere.WARNUNG,
                    f"Konto {konto} ist Automatikkonto mit Schlüssel "
                    f"{_schluesselname(auto)}, gebucht ohne Steuer — DATEV rechnet "
                    "dort selbst Steuer heraus (accounti exportiert BU 40, Aufhebung "
                    "der Automatik)",
                )
            )
        elif auto is not None and s is None:
            probleme.append(
                (
                    Schwere.FEHLER,
                    f"Konto {konto} ist Automatikkonto mit Schlüssel "
                    f"{_schluesselname(auto)}, gebucht mit Steuer, aber ohne Schlüssel "
                    "— accounti meldet die Steuer nicht in der Voranmeldung, DATEV "
                    "rechnet sie aus dem Bruttobetrag",
                )
            )
        ohne = w.ohne_vorsteuer(konto)
        if ohne is not None and s in VORSTEUER:
            probleme.append(
                (
                    Schwere.HINWEIS,
                    f"Konto {konto} ({ohne}) führt laut Kontenrahmen keine Vorsteuer, "
                    f"gebucht mit {_schluesselname(s)}",
                )
            )
        return probleme

    def _probleme(self, x: Buchungssatz, w: _Kontenwissen) -> list[tuple[Schwere, str]]:
        s = x.steuer_schluessel
        sachkonten = self._sachkonten(x, w)
        probleme: list[tuple[Schwere, str]] = []
        if s in STEUERSCHLUESSEL and not sachkonten:
            probleme.append(
                (
                    Schwere.FEHLER,
                    f"Schlüssel {_schluesselname(s)} auf einer Buchung zwischen Geld- "
                    f"und Personenkonten ({x.soll_konto} an {x.haben_konto})",
                )
            )
        for konto in sachkonten:
            probleme += self._konto(konto, x, w)
        if s not in (None, 0, 1, 40) and s not in STEUERSCHLUESSEL:
            probleme.append(
                (Schwere.WARNUNG, f"Steuerschlüssel {s} ist in accounti unbekannt")
            )
        return probleme

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        w = _Kontenwissen(k.session, k.buchhaltung, k.einstellungen)
        befunde = []
        for x in k.buchungen:
            if not k.im_zeitraum(x.datum) or x.storno_von or x.storniert_durch:
                continue
            probleme = self._probleme(x, w)
            if not probleme:
                continue
            befunde.append(
                befund(
                    self,
                    "buchung",
                    x.id,
                    f"Buchung {str(x.id)[:8]} vom {datum_de(x.datum)} "
                    f"({x.soll_konto} an {x.haben_konto}, "
                    f"{betrag_de(x.betrag_netto)} €): Steuerschlüssel "
                    "passt nicht zum Sachkonto — "
                    + "; ".join(text for _, text in probleme),
                    schwere=_schwerste(probleme),
                    datum=x.datum,
                    betrag=x.betrag_netto,
                    abhilfe=self._abhilfe(x, w),
                )
            )
        return befunde

    def _abhilfe(self, x: Buchungssatz, w: _Kontenwissen) -> str:
        """Ein Aufruf, den ``accounti korrigiere`` so annimmt (Soll und Haben dabei)."""
        befehl = (
            f"accounti korrigiere {str(x.id)[:8]} --soll {x.soll_konto} "
            f"--haben {x.haben_konto}"
        )
        grund = ' --grund "…"' if x.beleg_id is not None else ""
        sachkonten = self._sachkonten(x, w)
        automatik = {k: a for k in sachkonten if (a := w.automatik(k)) is not None}
        if automatik:  # auf einem Automatikkonto nie --ohne-steuer (DATEV rechnet)
            konto, auto = next(iter(automatik.items()))
            if x.beleg_id is None:  # Schlüssel an die Automatik anpassen
                return f"Schlüssel der Automatik von {konto}: {befehl} --steuer {auto}"
            # mit Beleg bleibt die Steuer des Belegs: das Konto ist zu ändern
            soll = "<Konto>" if x.soll_konto == konto else x.soll_konto
            haben = "<Konto>" if x.haben_konto == konto else x.haben_konto
            anders = (
                f"accounti korrigiere {str(x.id)[:8]} --soll {soll} --haben {haben}"
            )
            if x.steuer_schluessel is None:
                return (
                    "bewusst ohne Steuer: nichts zu korrigieren (der DATEV-Export "
                    f"setzt BU 40) — sonst ein Konto ohne Automatik: {anders}"
                )
            return (
                f"ein Konto mit Automatik {x.steuer_schluessel} oder ohne Automatik: "
                f"{anders} --steuer {x.steuer_schluessel}"
            )
        # --ohne-steuer entfernt keine ausgewiesene Umsatzsteuer (§ 14c UStG)
        vorsteuer = x.steuer_schluessel not in UMSATZSTEUER
        if not sachkonten:  # reine Geld-/Personenbewegung: ohne Steuer
            if x.status in _FREIGEGEBEN:
                return (
                    "nicht per Storno korrigierbar (beide Seiten Geld- oder "
                    "Personenkonto, die Gegenbuchung höbe die Steuer nicht auf) — "
                    "mit dem Steuerberater klären"
                )
            if x.beleg_id is not None and not vorsteuer:
                return (
                    "ausgewiesene Steuer aus dem Beleg (§ 14c UStG): die "
                    "Rechnungsberichtigung als neuen Beleg erfassen"
                )
            return f"{befehl} --ohne-steuer{grund}"
        if x.beleg_id is not None:  # Steuer aus dem Beleg: Konto ändern oder entfernen
            konto_aendern = (
                f"Sachkonto ändern: accounti korrigiere {str(x.id)[:8]} --soll … "
                f"--haben … --steuer {x.steuer_schluessel}"
            )
            if not vorsteuer:  # ausgewiesene USt bleibt (§ 14c UStG)
                return konto_aendern
            if x.steuer_schluessel in SELBST_BERECHNET:
                # § 13b bzw. ig. Erwerb: Steuerschuld und Vorsteuer bleiben, auch
                # ohne ordnungsgemäße Rechnung — nur das Konto ist falsch
                return konto_aendern
            return (
                f"{konto_aendern} — oder Vorsteuer entfernen: {befehl} "
                f"--ohne-steuer{grund}"
            )
        return f"{befehl} --steuer <Schlüssel> (oder --ohne-steuer)"


def steuerschluessel_probleme(
    session: Session,
    buchung: Buchungssatz,
    buchhaltung: Buchhaltung,
    einstellungen: PruefEinstellungen | None = None,
) -> list[tuple[Schwere, str]]:
    """Was die Regel ``steuerschluessel_konto`` an einer (geplanten) Buchung findet —
    für ``korrigiere``, bevor die Neubuchung entsteht."""
    w = _Kontenwissen(session, buchhaltung, einstellungen or PruefEinstellungen())
    return SteuerschluesselKonto()._probleme(buchung, w)


# --- Steuersatz zum Land ------------------------------------------------------------


def _erlaubt(land: str) -> set[Decimal] | None:
    info = EU_STEUERSAETZE.get(land)
    if info is None:
        return None
    saetze = {info.normal, info.ermaessigt, info.ermaessigt_2, info.super_ermaessigt}
    return {s.normalize() for s in saetze if s is not None} | {NULL}


class SteuersatzLand:
    name = "steuersatz_land"
    kategorie = Kategorie.RICHTIGKEIT
    schwere = Schwere.WARNUNG
    beschreibung = "Steuersatz unplausibel zum Land des Kontakts"

    class Parameter(BaseModel):
        pass

    def _land(self, k: Kontext, b: Beleg) -> str | None:
        eigene = _kompakt(k.firma.ust_id) if k.firma and k.firma.ust_id else ""
        if (
            b.richtung is Belegrichtung.EINGANG
            and _kompakt(b.lieferant_ust_id) != eigene
        ):
            # Steuer nach der USt-IdNr. auf der Rechnung: Amazon EU S.à r.l. (LU)
            # rechnet unter ihrer DE-USt-IdNr. deutsche Umsatzsteuer ab — die eigene
            # USt-IdNr. (von der Erkennung übernommen) sagt über den Lieferanten nichts
            land = _land_aus_ustid(b.lieferant_ust_id)
            if land is not None and ist_eu_land(land):
                return land
        kontakt = k.kontakt_zum_beleg(b)
        if kontakt is not None:
            return kontakt.land.upper()
        return _land_aus_ustid(b.lieferant_ust_id)

    def _beleg(self, k: Kontext, b: Beleg) -> Befund | None:
        saetze = {s.normalize() for s in _saetze(b)}
        land = self._land(k, b)
        eingang = b.richtung is Belegrichtung.EINGANG
        laender = [land] if eingang and land else ["DE"]
        if not eingang and land and land != "DE":
            laender.append(land)  # OSS: Satz des Bestimmungslands
        erlaubt: set[Decimal] = set()
        for x in laender:
            erlaubt |= _erlaubt(x) or set()
        if not erlaubt:
            return None
        fremd = sorted(saetze - erlaubt)
        if fremd:
            return befund(
                self,
                "beleg",
                b.id,
                f"{_rechnung(b)}: Steuersatz {', '.join(_prozent(s) for s in fremd)} "
                f"ist in {'/'.join(laender)} unüblich (üblich: "
                f"{', '.join(_prozent(s) for s in sorted(erlaubt))})",
                datum=b.belegdatum,
                betrag=b.brutto,
                gegenpartei=b.lieferant_name,
            )
        if eingang and land and land != "DE" and any(s > 0 for s in saetze):
            return befund(
                self,
                "beleg",
                b.id,
                f"{_rechnung(b)}: Umsatzsteuer aus {land} — in Deutschland nicht als "
                "Vorsteuer abziehbar (Vorsteuer-Vergütungsverfahren)",
                schwere=Schwere.HINWEIS,
                datum=b.belegdatum,
                betrag=b.brutto,
                gegenpartei=b.lieferant_name,
            )
        return None

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        befunde = []
        for b in k.belege.values():
            if not _saetze(b) or b.status is BelegStatus.EINGEGANGEN:
                continue
            if not k.im_zeitraum(b.belegdatum or b.eingegangen_am.date()):
                continue
            if (ergebnis := self._beleg(k, b)) is not None:
                befunde.append(ergebnis)
        for x in k.buchungen:
            if x.steuer_schluessel not in (8, 9) or x.beleg_id is None:
                continue
            if not k.im_zeitraum(x.datum) or x.storno_von or x.storniert_durch:
                continue
            beleg = k.belege.get(x.beleg_id)
            if beleg is None or beleg.richtung is not Belegrichtung.EINGANG:
                continue
            land = self._land(k, beleg)
            if land and land != "DE":
                befunde.append(
                    befund(
                        self,
                        "buchung",
                        x.id,
                        f"Buchung {str(x.id)[:8]}: deutsche Vorsteuer "
                        f"({_schluesselname(x.steuer_schluessel)}) aus der Rechnung "
                        f"eines Lieferanten in {land}",
                        schwere=Schwere.FEHLER,
                        datum=x.datum,
                        betrag=x.betrag_netto,
                        gegenpartei=beleg.lieferant_name,
                    )
                )
        return befunde


# --- Adressat -----------------------------------------------------------------------


def _kompakt(text: str | None) -> str:
    return re.sub(r"\s", "", text or "").upper()


class Adressat:
    name = "adressat"
    kategorie = Kategorie.RICHTIGKEIT
    schwere = Schwere.FEHLER
    beschreibung = "Rechnung ist nicht an die buchende Gesellschaft adressiert"

    class Parameter(BaseModel):
        pass

    def _namen(self, k: Kontext) -> list[str]:
        namen = list(k.einstellungen.eigene_namen)
        if k.firma is not None:
            namen.insert(0, k.firma.name)
        return [n for n in (normalisiere_name(x) for x in namen) if n]

    def _pruefe(
        self, b: Beleg, a: Belegangaben, eigene: list[str], eigene_ustid: str
    ) -> Befund | None:
        if a.quelle == "erechnung":
            if not a.empfaenger_name:
                return None
            name = normalisiere_name(a.empfaenger_name)
            passt = bool(name) and any(e in name or name in e for e in eigene)
            if eigene_ustid and _kompakt(a.empfaenger_ust_id) == eigene_ustid:
                passt = True
            if passt:
                return None
            return befund(
                self,
                "beleg",
                b.id,
                f"{_rechnung(b)} ist an „{a.empfaenger_name}“ adressiert, nicht an "
                "die buchende Gesellschaft — kein Vorsteuerabzug",
                datum=b.belegdatum,
                betrag=b.brutto,
                gegenpartei=b.lieferant_name,
            )
        if a.text is None:
            return None
        text = normalisiere_name(a.text)
        if any(e in text for e in eigene) or (
            eigene_ustid and eigene_ustid in _kompakt(a.text)
        ):
            return None
        return befund(
            self,
            "beleg",
            b.id,
            f"{_rechnung(b)}: die buchende Gesellschaft steht nicht als Empfänger "
            "auf der Rechnung",
            schwere=Schwere.WARNUNG,
            datum=b.belegdatum,
            betrag=b.brutto,
            gegenpartei=b.lieferant_name,
        )

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        eigene = self._namen(k)
        if not eigene:
            return []
        eigene_ustid = _kompakt(k.firma.ust_id if k.firma else None)
        grenze = k.einstellungen.kleinbetrag_grenze
        befunde = []
        for b in k.belege.values():
            if b.belegart is not Belegart.EINGANGSRECHNUNG:
                continue
            if b.status is not BelegStatus.ERFASST:
                continue
            if b.brutto is not None and abs(b.brutto) <= grenze:
                continue  # § 33 UStDV: der Empfänger ist keine Pflichtangabe
            if not k.im_zeitraum(b.belegdatum or b.eingegangen_am.date()):
                continue
            a = _lies_angaben(b, k)
            if (ergebnis := self._pruefe(b, a, eigene, eigene_ustid)) is not None:
                befunde.append(ergebnis)
        return befunde


# --- Vorsteuer aus ig. Erwerb ohne gültige USt-IdNr. ----------------------------------


class IgErwerbUstid:
    name = "ig_erwerb_ustid"
    kategorie = Kategorie.RICHTIGKEIT
    schwere = Schwere.FEHLER
    beschreibung = "Vorsteuer aus ig. Erwerb ohne gültige USt-IdNr. des Lieferanten"

    class Parameter(BaseModel):
        max_alter_tage: int = Field(default=400, ge=0)

    def _lieferant(
        self, k: Kontext, x: Buchungssatz
    ) -> tuple[Kontakt | None, str | None]:
        beleg = k.belege.get(x.beleg_id) if x.beleg_id else None
        kontakt = k.kontakt_zum_beleg(beleg) if beleg is not None else None
        for konto in (x.haben_konto, x.soll_konto):
            kontakt = kontakt or k.kontakt_zum_konto(konto)
        ust_id = (kontakt.ust_id if kontakt else None) or (
            beleg.lieferant_ust_id if beleg else None
        )
        return kontakt, ust_id

    def _problem(
        self,
        k: Kontext,
        x: Buchungssatz,
        kontakt: Kontakt | None,
        ust_id: str | None,
        p: Parameter,
    ) -> tuple[Schwere, str] | None:
        land = (kontakt.land.upper() if kontakt else None) or _land_aus_ustid(ust_id)
        if not ust_id:
            return (
                Schwere.FEHLER,
                "ohne USt-IdNr. des Lieferanten (§ 14a Abs. 3 UStG)",
            )
        if land == "DE" or (land is not None and not ist_eu_land(land)):
            return (
                Schwere.FEHLER,
                f"Lieferant sitzt in {land} — ein ig. Erwerb setzt einen Lieferanten "
                "aus einem anderen EU-Staat voraus",
            )
        bewertung = aktuelle_bestaetigung(
            k.session, normalisiere(ust_id), x.datum, p.max_alter_tage
        )
        if bewertung.gueltig is False:
            return (Schwere.FEHLER, f"USt-IdNr. {ust_id} laut BZSt {bewertung.grund}")
        if bewertung.gueltig is None:
            return (
                Schwere.HINWEIS,
                f"USt-IdNr. {ust_id} nicht beim BZSt bestätigt (accounti kontakte "
                "pruefe-ustid)",
            )
        return None

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        befunde = []
        for x in k.buchungen:
            if x.steuer_schluessel not in IG_ERWERB or not k.im_zeitraum(x.datum):
                continue
            if x.storno_von or x.storniert_durch:
                continue
            kontakt, ust_id = self._lieferant(k, x)
            problem = self._problem(k, x, kontakt, ust_id, p)
            if problem is None:
                continue
            befunde.append(
                befund(
                    self,
                    "buchung",
                    x.id,
                    f"Buchung {str(x.id)[:8]} vom {datum_de(x.datum)}: Vorsteuer aus "
                    f"ig. Erwerb ({_schluesselname(x.steuer_schluessel or 0)}) "
                    + problem[1],
                    schwere=problem[0],
                    datum=x.datum,
                    betrag=x.betrag_netto,
                    gegenpartei=kontakt.name if kontakt else None,
                )
            )
        return befunde


# --- Dubletten ----------------------------------------------------------------------


class Dublette:
    name = "dublette"
    kategorie = Kategorie.RICHTIGKEIT
    schwere = Schwere.WARNUNG
    beschreibung = (
        "Auffällige Dubletten: gleicher Betrag, gleicher Kontakt, enges Fenster"
    )

    class Parameter(BaseModel):
        fenster_tage: int = Field(default=7, ge=0)

    def _kontakt(self, b: Beleg) -> str | None:
        if b.kontakt_id:
            return f"k:{b.kontakt_id}"
        if b.lieferant_ust_id:
            return f"u:{_kompakt(b.lieferant_ust_id)}"
        if b.lieferant_name:
            return f"n:{normalisiere_name(b.lieferant_name)}"
        return None

    def _belege(self, k: Kontext, p: Parameter) -> list[Befund]:
        gruppen: dict[tuple[str, Decimal], list[Beleg]] = defaultdict(list)
        for b in k.belege.values():
            schluessel = self._kontakt(b)
            if schluessel and b.brutto is not None and b.belegdatum is not None:
                gruppen[(schluessel, b.brutto)].append(b)
        befunde = []
        for liste in gruppen.values():
            liste.sort(key=lambda b: (b.belegdatum, b.eingegangen_am))
            for i, spaet in enumerate(liste):
                for frueh in liste[:i]:
                    assert spaet.belegdatum is not None
                    assert frueh.belegdatum is not None
                    if (spaet.belegdatum - frueh.belegdatum).days > p.fenster_tage:
                        continue
                    if spaet.datei_hash == frueh.datei_hash:
                        continue  # dieselbe Datei verwirft schon die Erfassung
                    if not k.im_zeitraum(spaet.belegdatum):
                        continue
                    gleiche_nr = bool(
                        spaet.belegnummer and spaet.belegnummer == frueh.belegnummer
                    )
                    befunde.append(
                        befund(
                            self,
                            "beleg",
                            spaet.id,
                            f"{_rechnung(spaet)} gleicht Beleg {str(frueh.id)[:8]} "
                            f"vom {datum_de(frueh.belegdatum)}: gleicher Kontakt, "
                            f"{betrag_de(spaet.brutto)} €"
                            + (", gleiche Rechnungsnummer" if gleiche_nr else "")
                            + " — doppelt erfasst?",
                            schwere=Schwere.FEHLER if gleiche_nr else Schwere.WARNUNG,
                            datum=spaet.belegdatum,
                            betrag=spaet.brutto,
                            gegenpartei=spaet.lieferant_name,
                        )
                    )
                    break
        return befunde

    def _buchungen(self, k: Kontext) -> list[Befund]:
        gruppen: dict[tuple[Any, ...], list[Buchungssatz]] = defaultdict(list)
        for x in k.buchungen:
            if x.beleg_id is None or x.storno_von or x.storniert_durch:
                continue
            schluessel = (
                x.beleg_id,
                x.transaktion_id,
                # Marktplatz-Abrechnung: je Bestellung eine Buchung (Bestellnummer)
                x.beleg_nummer,
                x.beleg_position_id,
                x.soll_konto,
                x.haben_konto,
                x.betrag_netto,
                x.steuer_schluessel,
            )
            gruppen[schluessel].append(x)
        befunde = []
        for liste in gruppen.values():
            if len(liste) < 2 or not k.im_zeitraum(liste[-1].datum):
                continue
            x = liste[-1]
            befunde.append(
                befund(
                    self,
                    "buchung",
                    x.id,
                    f"Beleg {str(x.beleg_id)[:8]} ist {len(liste)}-mal gleich gebucht "
                    f"({x.soll_konto} an {x.haben_konto}, "
                    f"{betrag_de(x.betrag_netto)} €)",
                    schwere=Schwere.FEHLER,
                    datum=x.datum,
                    betrag=x.betrag_netto,
                    abhilfe=(
                        "überzählige Buchung stornieren (accounti buchung storniere "
                        f"{str(x.id)[:8]} --grund …)"
                    ),
                )
            )
        return befunde

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        return self._belege(k, p) + self._buchungen(k)


for _regel in (
    Pflichtangaben(),
    Rechenprobe(),
    SteuerschluesselKonto(),
    SteuersatzLand(),
    Adressat(),
    IgErwerbUstid(),
    Dublette(),
):
    registriere_pruefregel(_regel)
