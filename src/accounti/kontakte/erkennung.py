"""Kontakterkennung aus Belegdaten: IBAN → USt-IdNr. → Name.

Ziel ist ein Kontakt je Firma, nicht einer je Schreibweise. Die Namensnormalisierung
entfernt deshalb Rechtsformen, Satzzeichen, Umlaut-Schreibweisen und Groß/Klein.
"""

from __future__ import annotations

import re

from accounti.models import Kontakt

_RECHTSFORMEN = {
    "gmbh",
    "mbh",
    "ag",
    "ug",
    "kg",
    "kgaa",
    "ohg",
    "gbr",
    "ek",
    "ev",
    "se",
    "co",
    "haftungsbeschraenkt",
    "ltd",
    "limited",
    "inc",
    "llc",
    "bv",
    "sarl",
    "srl",
}
_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def normalisiere_name(name: str) -> str:
    text = name.casefold().translate(_UMLAUTE)
    # „G.m.b.H." → „gmbh", „e.K." → „ek": Punkte innerhalb von Abkürzungen entfernen
    text = re.sub(r"(?<=\w)\.(?=\w)", "", text)
    woerter = re.findall(r"[a-z0-9]+", text)
    return " ".join(w for w in woerter if w not in _RECHTSFORMEN)


def _kompakt(wert: str | None) -> str:
    return re.sub(r"\s", "", wert or "").upper()


def land_aus_kennung(ust_id: str | None, iban: str | None = None) -> str | None:
    """Land eines Geschäftspartners aus dem Präfix der USt-IdNr. (EL → GR, XI → GB),
    sonst aus der IBAN — ein PDF-Beleg nennt das Land selten auswertbar, und ohne Land
    gälte jeder Kreditor als deutsch (§ 13b: Kz 46/47 nur für EU-Unternehmer)."""
    for wert in (ust_id, iban):
        kompakt = _kompakt(wert)
        if len(kompakt) > 2 and kompakt[:2].isalpha():
            code = kompakt[:2]
            return {"EL": "GR", "XI": "GB"}.get(code, code)
    return None


def finde_kontakt(
    kontakte: list[Kontakt],
    iban: str | None = None,
    ust_id: str | None = None,
    name: str | None = None,
) -> tuple[Kontakt | None, str | None]:
    """Sucht den Kontakt; liefert (Kontakt, Merkmal) oder (None, None)."""
    if iban:
        for k in kontakte:
            if k.iban and _kompakt(k.iban) == _kompakt(iban):
                return k, "IBAN"
    if ust_id:
        for k in kontakte:
            if k.ust_id and _kompakt(k.ust_id) == _kompakt(ust_id):
                return k, "USt-IdNr."
    schluessel = normalisiere_name(name) if name else ""
    if schluessel:
        for k in kontakte:
            if normalisiere_name(k.name) == schluessel:
                return k, "Name"
    return None, None


def naechste_kontonummer(belegt: set[str], von: int, bis: int) -> str:
    """Nächste freie Personenkontonummer im Kreis (hinter der höchsten vergebenen)."""
    im_kreis = [int(n) for n in belegt if n.isdigit() and von <= int(n) <= bis]
    naechste = max(im_kreis) + 1 if im_kreis else von
    if naechste > bis:
        msg = f"Personenkontenkreis {von}–{bis} ist voll"
        raise ValueError(msg)
    return str(naechste)
