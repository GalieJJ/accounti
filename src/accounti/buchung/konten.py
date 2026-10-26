"""Kontonummern prüfen und benennen — gemeinsam für CLI und Browser (Baustein 10b)."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from decimal import Decimal
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from accounti.abschluss.kontenrahmen import Kontenrahmen
    from accounti.konfiguration import Buchhaltung
    from accounti.pruefung.einstellungen import PruefEinstellungen

_KONTO = re.compile(r"^\d{4,8}$")


class KontoError(ValueError):
    """Keine gültige Kontonummer."""


def pruefe_kontonummer(konto: str, feld: str = "Konto") -> str:
    """4 bis 8 Ziffern (Sachkonten 4-stellig, Personenkonten 5-stellig, mehr bei
    erweiterten Kontenrahmen) — sonst ``KontoError``."""
    wert = (konto or "").strip()
    if not _KONTO.match(wert):
        raise KontoError(
            f"{feld}: {wert or '(leer)'} ist keine Kontonummer (4–8 Ziffern)"
        )
    return wert


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


@lru_cache(maxsize=4)
def mitgelieferter_kontenrahmen(name: str) -> Kontenrahmen | None:
    """Die mitgelieferte Abschlusszuordnung des Kontenrahmens (``None``, wenn es keine
    gibt) — für Prüfungen ohne die Konfiguration der Gesellschaft."""
    from accounti.abschluss.kontenrahmen import KontenrahmenError, lade_kontenrahmen

    try:
        return lade_kontenrahmen(name)
    except KontenrahmenError:
        return None


def zahlungsmittel(
    buchhaltung: Buchhaltung,
    kontenrahmen: Kontenrahmen | None = None,
    weitere: Iterable[str | None] = (),
) -> Callable[[str], bool]:
    """Ist das Konto ein Zahlungsmittel der Gesellschaft? Kasse, Bank, Geldtransit und
    Kreditkarte laut Kontenrahmen (``Kontenrahmen.ist_zahlungsmittel``; ohne Angabe
    der mitgelieferte der Buchhaltung), dazu ``buchhaltung.bank_konto`` und
    ``weitere`` (Finanzkonto des Umsatzes, eingerichtete Bank- und Kartenkonten)."""
    kr = kontenrahmen or mitgelieferter_kontenrahmen(buchhaltung.kontenrahmen)
    eigene = {buchhaltung.bank_konto, *(k for k in weitere if k)}

    def pruefe(konto: str) -> bool:
        nummer = (konto or "").strip()
        return nummer in eigene or (kr is not None and kr.ist_zahlungsmittel(nummer))

    return pruefe


def umbuchung_fehler(
    soll: str, haben: str, ist_zahlungsmittel: Callable[[str], bool]
) -> str | None:
    """Meldung, wenn Soll und Haben beide Zahlungsmittel sind (Umbuchung Giro ↔
    Tagesgeld, Bank ↔ Kasse, Bank ↔ Kreditkarte, Geldtransit) — daraus wird keine
    Regel: Die Umbuchung steht auf beiden Kontoauszügen; eine Regel buchte die
    Gegenseite auf dem anderen Konto mit demselben Konto im Soll und im Haben (die
    Bewegung fiele aus den Büchern, der Bestand wiche vom Auszug ab — § 239 Abs. 2 HGB,
    § 146 Abs. 1 AO). Sonst ``None``."""
    soll, haben = (soll or "").strip(), (haben or "").strip()
    if soll == haben and not ist_zahlungsmittel(soll):
        return (
            f"Soll und Haben sind dasselbe Konto ({soll}) — die Buchung bewegte nichts"
        )
    if not (ist_zahlungsmittel(soll) and ist_zahlungsmittel(haben)):
        return None
    return (
        f"Soll {soll} und Haben {haben} sind beide Geldkonten (Bank, Kasse, "
        "Kreditkarte, Geldtransit) — aus einer Umbuchung zwischen eigenen Konten wird "
        "keine Regel: Sie steht auf beiden Kontoauszügen, und die Regel buchte "
        "künftige Umsätze mit demselben Konto im Soll und im Haben (§ 146 Abs. 1 AO, "
        "§ 239 Abs. 2 HGB). Ohne Regel korrigieren."
    )


def kein_sachkonto(
    konto: str, buchhaltung: Buchhaltung, weitere: Iterable[str | None] = ()
) -> bool:
    """Geld-, Personen-, Forderungs- oder Verbindlichkeitskonto (``ist_geldkonto``
    des Kontenrahmens), Zahlungsmittel oder Finanzkonto des Umsatzes — kein Sachkonto
    eines Belegs. Eine Regel „1210 an 1200“ oder „70001 an 1200“ liefert so kein
    Aufwandskonto (sonst „1210 an 1210“ bzw. „70001 an 70001“)."""
    nummer = (konto or "").strip()
    kr = mitgelieferter_kontenrahmen(buchhaltung.kontenrahmen)
    if zahlungsmittel(buchhaltung, kr, weitere)(nummer):
        return True
    if kr is None:
        return nummer.isdigit() and len(nummer) == 5  # Personenkonto
    return kr.ist_geldkonto(nummer)


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
