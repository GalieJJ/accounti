"""Kontonummern prüfen und benennen — gemeinsam für CLI und Browser (Baustein 10b)."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from accounti.abschluss.kontenrahmen import Kontenrahmen
    from accounti.konfiguration import Buchhaltung
    from accounti.pruefung.einstellungen import PruefEinstellungen

# nur ASCII-Ziffern: ``\d`` ließe „１２００“ (vollbreit) durch — ein Phantomkonto neben
# 1200, an dem die Sperre gegen Soll = Haben vorbeiging und der DATEV-Export abbrach
# (Runde 4, g3w-fach N6). Bis 9 Stellen: DATEV-Personenkonten sind eine Stelle länger
# als die Sachkontenlänge (4–8), bei Sachkontenlänge 8 also 9 Stellen (Runde 5, g4w N5)
_KONTO = re.compile(r"[0-9]{4,9}")
KONTO_ZIFFERN = "4–9 Ziffern"


class KontoError(ValueError):
    """Keine gültige Kontonummer."""


def pruefe_kontonummer(konto: str, feld: str = "Konto") -> str:
    """4 bis 9 ASCII-Ziffern (Sachkonten 4-stellig, Personenkonten 5-stellig, mehr
    bei erweiterten Kontenrahmen: Unterkonten 6-stellig, Personenkonten bei
    Sachkontenlänge 8 9-stellig) — sonst ``KontoError``."""
    wert = (konto or "").strip()
    if not _KONTO.fullmatch(wert):
        raise KontoError(
            f"{feld}: {wert or '(leer)'} ist keine Kontonummer ({KONTO_ZIFFERN})"
        )
    return wert


def ist_personenkontonummer(konto: str) -> bool:
    """Personenkonto an der Länge: 5 Stellen (Sachkontenlänge 4, wie accounti
    rechnet) oder 9 (Sachkontenlänge 8 — längere Sachkonten gibt es bei DATEV nicht,
    9 Stellen sind dort immer ein Personenkonto; Runde 5, g4w N5)."""
    return konto.isascii() and konto.isdigit() and len(konto) in (5, 9)


def finanzkonto_fehler(
    soll: str, haben: str, betrag: Decimal, finanzkonto: str
) -> tuple[str, str] | None:
    """Ein Bankumsatz läuft über sein Finanzkonto — eine Ausgabe im Haben, eine
    Einnahme im Soll. Sonst stimmt der Bestand des Kontos in den Büchern nicht mehr mit
    dem Kontoauszug (Buchungen müssen richtig sein, § 146 Abs. 1 AO, § 239 Abs. 2
    HGB). ``(feld, meldung)`` bei einem Fehler, sonst ``None``."""
    if betrag < 0:
        feld, konto, art, seite = "haben", haben, "eine Ausgabe", "Haben"
    elif betrag > 0:
        feld, konto, art, seite = "soll", soll, "eine Einnahme", "Soll"
    else:
        return None
    if konto == finanzkonto:
        return None
    return feld, (
        f"Der Umsatz ist {art} über das Finanzkonto {finanzkonto} — {finanzkonto} "
        f"muss im {seite} stehen (sonst stimmt der Kontostand in den Büchern nicht "
        "mehr mit dem Kontoauszug)"
    )


@dataclass(frozen=True)
class Erloeskonten:
    """Erlöskonten eines Kontenrahmens für Ausgangsbelege (Belegbuchung, OPOS).

    ``steuerpflichtig``: Steuersatz → Konto; ``steuerfrei``: Steuerkategorie der
    E-Rechnung (EN 16931: K ig. Lieferung, G Ausfuhr, E steuerfrei § 4 Nr. 8 ff., AE
    Steuerschuld beim Empfänger) → Konto — aus ``steuer.kennziffern.KENNZIFFERN_KONTEN``
    (dasselbe Konto, das die Voranmeldung der Kennziffer zuordnet); ``unbekannt``:
    ohne erkennbaren Satz (zur Prüfung); ``oss``: Land → Erlöskonto eines
    OSS-Fernverkaufs (zur Prüfung; ``steuer.umsatzsteuer.oss_erloeskonten``) — ein Land
    ohne eigenes Konto geht auf ``unbekannt``, die OSS-Meldung ordnet über das Konto
    zu."""

    steuerpflichtig: dict[Decimal, str]
    steuerfrei: dict[str, str]
    unbekannt: str
    oss: dict[str, str]


# Kategorie der E-Rechnung → Kennziffer der Voranmeldung (Bemessungsgrundlage)
_KATEGORIE_KZ = {"K": 41, "G": 43, "E": 48, "AE": 21}


@lru_cache(maxsize=4)
def erloeskonten(kontenrahmen: str) -> Erloeskonten:
    """Erlöskonten des Kontenrahmens (DATEV SKR03 bzw. SKR04, Kontenrahmen 2026):
    SKR03 8400 (19 %), 8300 (7 %), 8200 (ohne Satz), OSS 8320–8327; SKR04 4400, 4300,
    4200, OSS 4320–4327 — im SKR04 sind 8400/8300/8200 „zur freien Verfügung“
    (Gesamttest 10b-1 nach dem Merge, M-3; OSS: Runde 3). Andere Kontenrahmen lässt
    ``Buchhaltung`` nicht zu."""
    from accounti.steuer.kennziffern import KENNZIFFERN_KONTEN
    from accounti.steuer.umsatzsteuer import oss_erloeskonten

    name = kontenrahmen.upper()
    funktion = KENNZIFFERN_KONTEN[name]
    steuerfrei = {
        kategorie: next(k for k, z in funktion.items() if z == kz)
        for kategorie, kz in _KATEGORIE_KZ.items()
    }
    if name == "SKR04":
        return Erloeskonten(
            {Decimal("19"): "4400", Decimal("7"): "4300"},
            steuerfrei,
            "4200",
            oss_erloeskonten("SKR04"),
        )
    return Erloeskonten(
        {Decimal("19"): "8400", Decimal("7"): "8300"},
        steuerfrei,
        "8200",
        oss_erloeskonten("SKR03"),
    )


@lru_cache(maxsize=4)
def mitgelieferter_kontenrahmen(name: str) -> Kontenrahmen | None:
    """Die mitgelieferte Abschlusszuordnung des Kontenrahmens (``None``, wenn es keine
    gibt) — für Prüfungen ohne die Konfiguration der Gesellschaft."""
    from accounti.abschluss.kontenrahmen import KontenrahmenError, lade_kontenrahmen

    try:
        return lade_kontenrahmen(name)
    except KontenrahmenError:
        return None


@dataclass(frozen=True)
class Zahlungsmittel:
    """Ist das Konto ein Zahlungsmittel der Gesellschaft? (aufrufbar) — dazu
    ``geldtransit``: ein Zahlungsmittel ohne eigenen Kontoauszug."""

    kontenrahmen: Kontenrahmen | None
    eigene: frozenset[str]

    def __call__(self, konto: str) -> bool:
        nummer = (konto or "").strip()
        kr = self.kontenrahmen
        return nummer in self.eigene or (
            kr is not None and kr.ist_zahlungsmittel(nummer)
        )

    def geldtransit(self, konto: str) -> bool:
        nummer = (konto or "").strip()
        kr = self.kontenrahmen
        return (
            nummer not in self.eigene and kr is not None and kr.ist_geldtransit(nummer)
        )


def zahlungsmittel(
    buchhaltung: Buchhaltung,
    kontenrahmen: Kontenrahmen | None = None,
    weitere: Iterable[str | None] = (),
) -> Zahlungsmittel:
    """Ist das Konto ein Zahlungsmittel der Gesellschaft? Kasse, Bank, Geldtransit und
    Kreditkarte laut Kontenrahmen (``Kontenrahmen.ist_zahlungsmittel``; ohne Angabe
    der mitgelieferte der Buchhaltung), dazu ``buchhaltung.bank_konto`` und
    ``weitere`` (Finanzkonto des Umsatzes, eingerichtete Bank- und Kartenkonten)."""
    kr = kontenrahmen or mitgelieferter_kontenrahmen(buchhaltung.kontenrahmen)
    eigene = frozenset({buchhaltung.bank_konto, *(k for k in weitere if k)})
    return Zahlungsmittel(kr, eigene)


def umbuchung_fehler(
    soll: str, haben: str, ist_zahlungsmittel: Callable[[str], bool]
) -> str | None:
    """Meldung, wenn Soll und Haben beide Zahlungsmittel sind (Umbuchung Giro ↔
    Tagesgeld, Bank ↔ Kasse, Bank ↔ Kreditkarte) — daraus wird keine Regel: Die
    Umbuchung steht auf beiden Kontoauszügen; eine Regel buchte die Gegenseite auf dem
    anderen Konto mit demselben Konto im Soll und im Haben (die Bewegung fiele aus den
    Büchern, der Bestand wiche vom Auszug ab — § 239 Abs. 2 HGB, § 146 Abs. 1 AO).

    Ausnahme Geldtransit (``Zahlungsmittel.geldtransit``): Er hat keinen eigenen
    Kontoauszug, eine Regel „1360 an 1200“ bucht auf keinem Konto Soll = Haben
    (Gesamttest 10b-1, Runde 3). Sonst ``None``."""
    soll, haben = (soll or "").strip(), (haben or "").strip()
    if soll == haben and not ist_zahlungsmittel(soll):
        return (
            f"Soll und Haben sind dasselbe Konto ({soll}) — die Buchung bewegte nichts"
        )
    if not (ist_zahlungsmittel(soll) and ist_zahlungsmittel(haben)):
        return None
    transit = getattr(ist_zahlungsmittel, "geldtransit", None)
    if soll != haben and transit is not None and (transit(soll) or transit(haben)):
        return None
    return (
        f"Soll {soll} und Haben {haben} sind beide Geldkonten (Bank, Kasse, "
        "Kreditkarte) — aus einer Umbuchung zwischen eigenen Konten mit Kontoauszug "
        "wird keine Regel: Sie steht auf beiden Kontoauszügen, und die Regel buchte "
        "künftige Umsätze mit demselben Konto im Soll und im Haben (§ 146 Abs. 1 AO, "
        "§ 239 Abs. 2 HGB). Ohne Regel korrigieren; über Geldtransit (SKR03 1360, "
        "SKR04 1460) bleibt sie lernbar."
    )


def soll_gleich_haben(soll: str, haben: str) -> str | None:
    """Meldung, wenn Soll und Haben dasselbe Konto sind — eine solche Buchung bewegt
    nichts; bei einem Bankumsatz fehlte die Bewegung in den Büchern, der Bestand
    wiche vom Kontoauszug ab (§ 239 Abs. 2 HGB, § 146 Abs. 1 AO). Gilt für jede
    Buchung, auch von Hand (Korrektur, Kassenbuch; Gesamttest 10b-1, Runde 3)."""
    soll, haben = (soll or "").strip(), (haben or "").strip()
    if soll and soll == haben:
        return (
            f"Soll und Haben sind dasselbe Konto ({soll}) — die Buchung bewegte "
            "nichts (bei einem Bankumsatz fehlte die Bewegung in den Büchern)"
        )
    return None


def kein_sachkonto(
    konto: str, buchhaltung: Buchhaltung, weitere: Iterable[str | None] = ()
) -> bool:
    """Zahlungsmittel (Kasse, Bank, Geldtransit, Kreditkarte; ``weitere``:
    Finanzkonto des Umsatzes), Personenkonto oder Forderung bzw. Verbindlichkeit aus
    Lieferungen und Leistungen (``Kontenrahmen.ist_lul_konto``) — kein Sachkonto eines
    Belegs. Eine Regel „1210 an 1200“ oder „70001 an 1200“ liefert so kein
    Aufwandskonto (sonst „1210 an 1210“ bzw. „70001 an 70001“).

    Andere Bestandskonten bleiben zulässig (Gesamttest 10b-1, Runde 3): Wertpapiere
    (SKR03 1348, SKR04 1510), Festgeld 1290/1890, Rückdeckungsversicherung 1355,
    Verrechnungs- und durchlaufende Posten — gegen Bank oder Kreditor bucht keines
    davon Soll = Haben (§ 266 Abs. 2 B III HGB: Wertpapiere sind keine flüssigen
    Mittel)."""
    nummer = (konto or "").strip()
    kr = mitgelieferter_kontenrahmen(buchhaltung.kontenrahmen)
    if zahlungsmittel(buchhaltung, kr, weitere)(nummer):
        return True
    if ist_personenkontonummer(nummer):
        return True
    return kr is not None and kr.ist_lul_konto(nummer)


@lru_cache(maxsize=8)
def _namen_der_datei(datei: str | None, kontenrahmen: str) -> dict[str, str]:
    from accounti.konfiguration import KonfigurationError
    from accounti.pruefung.einstellungen import PruefEinstellungen
    from accounti.pruefung.regeln.richtigkeit import _lade_konten

    try:
        konten = _lade_konten(
            PruefEinstellungen(kontenrahmen_datei=datei), kontenrahmen
        )
    except KonfigurationError:
        return {}
    return {
        str(nr): str(eintrag.get("name") or "")
        for nr, eintrag in konten.items()
        if isinstance(eintrag, dict)
    }


def kontobezeichnung(
    konto: str,
    kontenrahmen: Kontenrahmen | None = None,
    pruefung: PruefEinstellungen | None = None,
) -> str:
    """Bezeichnung aus dem Kontenrahmen (``namen``), sonst aus der Kontenrahmen-Datei
    der Prüfregeln (``pruefung/skr03.yaml`` bzw. ``pruefung.kontenrahmen_datei``),
    sonst leer — dann zeigt die Oberfläche nur die Nummer."""
    if kontenrahmen is not None:
        name = kontenrahmen.bezeichnung(konto)
        if name:
            return name
    datei = pruefung.kontenrahmen_datei if pruefung is not None else None
    rahmen = kontenrahmen.name if kontenrahmen is not None else "SKR03"
    return _namen_der_datei(str(datei) if datei else None, rahmen).get(konto, "")
