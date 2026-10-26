"""Grundbausteine des DATEV-Formats (EXTF): Kopfzeile, Feldwerte, Datei.

Regeln aus DATEVs Musterdateien und der Formatbeschreibung des Prüfprogramms:

* Zeile 1 ist die Kopfzeile mit 31 Feldern (Versionsnummer 700); Textfelder stehen in
  Anführungszeichen — auch leer, so wie in der DATEV-Musterdatei.
* Zeile 2 enthält die Spaltenüberschriften, ab Zeile 3 folgen die Datensätze.
* Felder vom Typ Text stehen immer in Anführungszeichen, innere Anführungszeichen
  werden verdoppelt; Zahlen, Beträge, Daten und Konten stehen ohne.
* Dezimalkomma, keine Tausenderpunkte; Datum ``TTMMJJJJ`` (Belegdatum im
  Buchungsstapel ``TTMM``, das Jahr kommt aus dem Kopf).
* Semikolon als Trenner, CRLF als Zeilenende, Zeichensatz Windows-1252.

Was sich nicht in Windows-1252 schreiben lässt oder zu lang ist, wird nicht still
verändert, sondern als ``DatevFormatError`` gemeldet.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from accounti.export.datev_felder import Feld
from accounti.models import Buchungssatz


class DatevFormatError(ValueError):
    """Ein Wert passt nicht ins DATEV-Format."""


Wert = str | int | Decimal | date | None

# Kopffelder, die DATEV in Anführungszeichen schreibt (Musterdateien, 1-basiert)
_KOPF_TEXT = {1, 4, 8, 9, 10, 17, 18, 22, 24, 27, 30, 31}
HERKUNFT = "RE"
ANWENDUNG = "accounti"


@dataclass(frozen=True)
class Kopf:
    """Die 31 Felder der EXTF-Kopfzeile (soweit sie nicht konstant sind)."""

    kategorie: int
    formatname: str
    formatversion: int
    berater: int
    mandant: int
    wj_beginn: date
    sachkontenlaenge: int = 4
    datum_von: date | None = None
    datum_bis: date | None = None
    bezeichnung: str = ""
    diktatkuerzel: str = ""
    buchungstyp: int | None = None
    rechnungslegungszweck: int | None = None
    festschreibung: int | None = None
    waehrung: str = ""
    skr: str = ""
    erzeugt_am: datetime = field(default_factory=datetime.now)


def _zahl(wert: int | None) -> str:
    return "" if wert is None else str(wert)


def kopfzeile(k: Kopf) -> str:
    if len(k.bezeichnung) > 30:
        raise DatevFormatError(f"Bezeichnung {k.bezeichnung!r} länger als 30 Zeichen")
    if not 1001 <= k.berater <= 9999999:
        raise DatevFormatError(f"Beraternummer {k.berater} ungültig (1001–9999999)")
    if not 1 <= k.mandant <= 99999:
        raise DatevFormatError(f"Mandantennummer {k.mandant} ungültig (1–99999)")
    erzeugt = f"{k.erzeugt_am:%Y%m%d%H%M%S}{k.erzeugt_am.microsecond // 1000:03d}"
    werte = [
        "EXTF",
        "700",
        str(k.kategorie),
        k.formatname,
        str(k.formatversion),
        erzeugt,
        "",  # importiert (setzt DATEV)
        HERKUNFT,
        "",  # exportiert von
        "",  # importiert von (setzt DATEV)
        str(k.berater),
        str(k.mandant),
        f"{k.wj_beginn:%Y%m%d}",
        str(k.sachkontenlaenge),
        f"{k.datum_von:%Y%m%d}" if k.datum_von else "",
        f"{k.datum_bis:%Y%m%d}" if k.datum_bis else "",
        k.bezeichnung,
        k.diktatkuerzel,
        _zahl(k.buchungstyp),
        _zahl(k.rechnungslegungszweck),
        _zahl(k.festschreibung),
        k.waehrung,
        "",  # reserviert
        "",  # Derivatskennzeichen
        "",  # reserviert
        "",  # reserviert
        k.skr,
        "",  # Branchenlösung
        "",  # reserviert
        "",  # reserviert
        ANWENDUNG,
    ]
    return ";".join(
        f'"{w}"' if nr in _KOPF_TEXT else w for nr, w in enumerate(werte, start=1)
    )


def feldwert(feld: Feld, wert: Wert, datumsformat: str = "%d%m%Y") -> str:
    """Ein Feld nach seinem Typ schreiben."""
    if feld.typ == "T":
        text = re.sub(r"[\r\n\t]", " ", "" if wert is None else str(wert))
        if len(text) > feld.laenge:
            msg = f"{feld.name}: {text!r} länger als {feld.laenge} Zeichen"
            raise DatevFormatError(msg)
        return '"' + text.replace('"', '""') + '"'
    if wert is None or wert == "":
        return ""
    if feld.typ == "D":
        if not isinstance(wert, date):
            raise DatevFormatError(f"{feld.name}: {wert!r} ist kein Datum")
        return wert.strftime(datumsformat)
    if feld.typ == "K":
        text = str(wert)
        if not re.fullmatch(r"\d{1,9}", text):
            raise DatevFormatError(f"{feld.name}: Konto {text!r} ungültig")
        return text
    if isinstance(wert, date) or (isinstance(wert, str) and not wert.isdigit()):
        raise DatevFormatError(f"{feld.name}: {wert!r} ist keine Zahl")
    zahl = Decimal(str(wert))
    nachkomma = feld.nachkomma or (2 if feld.typ == "B" else 0)
    text = f"{zahl:.{nachkomma}f}"
    vorkomma = text.lstrip("-").split(".")[0]
    if len(vorkomma) > feld.laenge:
        raise DatevFormatError(f"{feld.name}: {wert} hat zu viele Stellen")
    return text.replace(".", ",")


_BELEGFELD1_UNZULAESSIG = re.compile(r"[^A-Za-z0-9_$&%*+\-/]")


def belegfeld1(text: str | None) -> str:
    """Belegfeld 1 (Rechnungs-/Belegnummer) im DATEV-Zeichenvorrat, höchstens 36.

    DATEV lässt nur Buchstaben, Ziffern und ``$ & % * + - /`` zu; Leerzeichen,
    Umlaute, Punkt, Komma, Semikolon und Doppelpunkt sind unzulässig (DATEV-Format,
    Buchungsstapel, Feld 11). Das Feld ist der Schlüssel für den OPOS-Ausgleich.
    """
    return _BELEGFELD1_UNZULAESSIG.sub("", text or "")[:36]


def belegfeld2_storno(
    storno_von: UUID | None, storniert_durch: UUID | None, ident: UUID
) -> str:
    """Belegfeld 2 eines Storno-Paars: ``ST`` und die ersten acht Zeichen der ID des
    Originals — an Original und Stornobuchung, sonst leer.

    GoBD Rz. 64: das Storno ist auf die ursprüngliche Buchung rückbeziehbar; über
    Belegfeld 1 nur, wenn es eine Belegnummer gibt. Zehn Zeichen aus Buchstaben und
    Ziffern passen in Feld 12 (höchstens 12) und sehen nie wie ein Datum (TTMMJJ)
    aus, das DATEV im OPOS als Fälligkeit läse.
    """
    original = storno_von or (ident if storniert_durch else None)
    return f"ST{original.hex[:8].upper()}" if original else ""


# Berichtigungsschlüssel 4 + Steuerschlüssel 0: Aufhebung der Automatik (DATEV)
AUFHEBUNG_DER_AUTOMATIK = "40"


def _automatik(b: Buchungssatz, automatikkonten: Mapping[str, int]) -> int | None:
    for konto in (b.soll_konto, b.haben_konto):
        if konto in automatikkonten:
            return automatikkonten[konto]
    return None


def bu_schluessel(b: Buchungssatz, automatikkonten: Mapping[str, int]) -> str:
    """BU-Schlüssel einer Buchung (Feld 9).

    DATEV-Steuerschlüssel-Tabelle (Dok.-Nr. 0907049, Kap. 3): Steuerschlüssel gelten
    nur auf Konten ohne Automatik. Auf einem Automatikkonto (AV/AM, z.B. 3400, 8400)
    bleibt das Feld deshalb leer, wenn der Schlüssel der Automatik entspricht — DATEV
    rechnet die Steuer selbst heraus; steht die Buchung dort bewusst ohne Steuer,
    trägt sie BU 40 „Aufhebung der Automatik“. Ein abweichender Schlüssel bleibt
    stehen und wird vorab gemeldet (``automatik_widerspruch``). Sonst der
    Steuerschlüssel der Buchung oder leer.
    """
    automatik = _automatik(b, automatikkonten)
    if b.steuer_schluessel is not None:
        if automatik is not None and b.steuer_schluessel == automatik:
            return ""
        return str(b.steuer_schluessel)
    if automatik is not None and not b.steuer_betrag:
        return AUFHEBUNG_DER_AUTOMATIK
    return ""


# § 13b und ig. Erwerb: DATEV rechnet Umsatz- und Vorsteuer aus dem Rechnungsbetrag
# (Netto = Zahlbetrag) — die selbst berechnete Steuer gehört nicht in den Umsatz
_STEUER_NICHT_IM_UMSATZ = frozenset({18, 19, 91, 94})


def datev_umsatz(b: Buchungssatz) -> Decimal:
    """Umsatz einer Buchung im Stapel: brutto, bei § 13b/ig. Erwerb das Netto."""
    umsatz = abs(b.betrag_netto)
    if b.steuer_betrag and b.steuer_schluessel not in _STEUER_NICHT_IM_UMSATZ:
        umsatz += abs(b.steuer_betrag)
    return umsatz


def automatik_widerspruch(
    b: Buchungssatz, automatikkonten: Mapping[str, int]
) -> str | None:
    """Warnung vor dem Export: anderer Schlüssel auf einem Automatikkonto — oder
    Steuer ohne Schlüssel (BU bleibt leer, DATEV rechnet, accounti meldet nichts)."""
    automatik = _automatik(b, automatikkonten)
    if automatik is None:
        return None
    konto = b.soll_konto if b.soll_konto in automatikkonten else b.haben_konto
    if b.steuer_schluessel is None and b.steuer_betrag:
        return (
            f"Buchung {b.beleg_nummer or str(b.id)[:8]} ({b.soll_konto} an "
            f"{b.haben_konto}): Konto {konto} ist DATEV-Automatikkonto (Schlüssel "
            f"{automatik}), gebucht mit Steuerbetrag, aber ohne Schlüssel — DATEV "
            "rechnet die Steuer aus dem Betrag heraus, accounti meldet sie in keiner "
            f"Voranmeldung; vor dem Import korrigieren (accounti korrigiere "
            f"{str(b.id)[:8]} --soll {b.soll_konto} --haben {b.haben_konto} "
            f"--steuer {automatik})"
        )
    if b.steuer_schluessel in (None, automatik):
        return None
    return (
        f"Buchung {b.beleg_nummer or str(b.id)[:8]} ({b.soll_konto} an "
        f"{b.haben_konto}): Konto {konto} ist DATEV-Automatikkonto (Schlüssel "
        f"{automatik}), gebucht mit Schlüssel {b.steuer_schluessel} — DATEV nimmt "
        "Steuerschlüssel nur auf Konten ohne Automatik an; vor dem Import korrigieren "
        "(accounti pruefen --regel steuerschluessel_konto)"
    )


def feldnummer(felder: tuple[Feld, ...], name: str) -> int:
    """1-basierte Feldnummer zu einer eindeutigen Spaltenüberschrift."""
    treffer = [i for i, f in enumerate(felder, start=1) if f.name == name]
    if len(treffer) != 1:
        raise KeyError(name)
    return treffer[0]


def kontoart(nummer: str, sachkontenlaenge: int) -> str | None:
    """``sachkonto``, ``personenkonto`` oder None, wenn die Nummer nicht passt."""
    if not re.fullmatch(r"\d{1,9}", nummer):
        return None
    if len(nummer) <= sachkontenlaenge:
        return "sachkonto"
    if len(nummer) == sachkontenlaenge + 1:
        return "personenkonto"
    return None


def schreibe_extf(
    kopf: Kopf,
    felder: tuple[Feld, ...],
    zeilen: list[dict[int, Wert]],
    datumsformate: dict[int, str] | None = None,
) -> bytes:
    """EXTF-Datei: Kopfzeile, Überschriften, Datensätze (Felder nach Nummer)."""
    datumsformate = datumsformate or {}
    ausgabe = [kopfzeile(kopf), ";".join(f.name for f in felder)]
    for nr, zeile in enumerate(zeilen, start=1):
        unbekannt = set(zeile) - set(range(1, len(felder) + 1))
        if unbekannt:
            raise DatevFormatError(
                f"Datensatz {nr}: Felder {sorted(unbekannt)} gibt es nicht"
            )
        ausgabe.append(
            ";".join(
                feldwert(f, zeile.get(i), datumsformate.get(i, "%d%m%Y"))
                for i, f in enumerate(felder, start=1)
            )
        )
    text = "\r\n".join(ausgabe) + "\r\n"
    try:
        return text.encode("cp1252")
    except UnicodeEncodeError as fehler:
        zeichen = text[fehler.start : fehler.end]
        msg = f"Zeichen {zeichen!r} lässt sich nicht in Windows-1252 schreiben"
        raise DatevFormatError(msg) from fehler
