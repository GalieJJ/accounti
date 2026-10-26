"""Kontakterkennung aus Belegdaten: IBAN → USt-IdNr. → Name.

Ziel ist ein Kontakt je Firma, nicht einer je Schreibweise. Die Namensnormalisierung
entfernt deshalb Rechtsformen, Satzzeichen, Umlaut-Schreibweisen und Groß/Klein.

Ein Treffer darf dem Beleg nicht widersprechen:

* Eine andere USt-IdNr. ist ein anderes Unternehmen — auch bei gleicher IBAN
  (Factoring, Inkasso, Zahlungsdienst) oder gleichem Namen („Atelier Nord SARL“ und
  „Atelier Nord SRL“ sind nach der Normalisierung gleich). So ein Kandidat wird nicht
  genommen; die Zusammenfassende Meldung geht je USt-IdNr. (§ 18a Abs. 7 Nr. 1 UStG).
* Ein anderes Land schließt einen Namenstreffer aus, wenn der Beleg das Land nennt
  (OSS-Bestimmungsland, § 18j UStG).
* Für Kunden aus eigenen Rechnungen (``mit_anschrift``) reicht der Name allein nicht:
  zwei Privatkunden „Max Müller“ sind zwei Debitoren — Mahnung und Anschrift dürfen
  nicht vermischt werden (Art. 5 Abs. 1 lit. f DSGVO). Zusammengeführt wird nur bei
  gleicher PLZ oder E-Mail-Adresse.
* Gleiche IBAN, aber ein anderer Name (ohne passende USt-IdNr.): Treffer mit
  ``widerspruch`` — die Buchung geht zur Prüfung.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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


def _ustid(wert: str | None) -> str:
    kompakt = _kompakt(wert)
    return "EL" + kompakt[2:] if kompakt.startswith("GR") else kompakt


@dataclass(frozen=True)
class Suchergebnis:
    kontakt: Kontakt | None
    merkmal: str | None  # IBAN, USt-IdNr., Name
    # Treffer mit Abweichung (Mensch prüft) bzw. warum ein Kandidat ausschied
    widerspruch: str | None = None


def _andere_ustid(k: Kontakt, ust_id: str | None) -> bool:
    return bool(ust_id and k.ust_id) and _ustid(ust_id) != _ustid(k.ust_id)


def _gleiche_ustid(k: Kontakt, ust_id: str | None) -> bool:
    return bool(ust_id and k.ust_id) and _ustid(ust_id) == _ustid(k.ust_id)


def _namenstreffer_passt_nicht(
    k: Kontakt,
    ust_id: str | None,
    land: str | None,
    plz: str | None,
    email: str | None,
    mit_anschrift: bool,
) -> str | None:
    if _andere_ustid(k, ust_id):
        return f"USt-IdNr. {k.ust_id} ≠ {ust_id}"
    if land and k.land and land.upper() != k.land.upper():
        return f"Land {k.land} ≠ {land.upper()}"
    if mit_anschrift:
        gleiche_plz = bool(plz and k.plz) and _kompakt(plz) == _kompakt(k.plz)
        gleiche_email = bool(email and k.email) and (
            (email or "").strip().casefold() == (k.email or "").strip().casefold()
        )
        if not (gleiche_plz or gleiche_email):
            return "weder PLZ noch E-Mail-Adresse stimmen überein"
    return None


def suche_kontakt(
    kontakte: list[Kontakt],
    iban: str | None = None,
    ust_id: str | None = None,
    name: str | None = None,
    *,
    land: str | None = None,
    plz: str | None = None,
    email: str | None = None,
    mit_anschrift: bool = False,
) -> Suchergebnis:
    """Sucht den Kontakt (IBAN → USt-IdNr. → Name) und prüft den Treffer gegen den
    Beleg — siehe Moduldokumentation."""
    ausgeschlossen: list[str] = []
    if iban:
        for k in kontakte:
            if not (k.iban and _kompakt(k.iban) == _kompakt(iban)):
                continue
            if _andere_ustid(k, ust_id):
                ausgeschlossen.append(
                    f"IBAN {_kompakt(iban)} gehört zu {k.name} (USt-IdNr. {k.ust_id}), "
                    f"der Beleg nennt USt-IdNr. {ust_id} — Factoring oder "
                    "Zahlungsdienst?"
                )
                continue
            widerspruch = None
            if (
                name
                and normalisiere_name(k.name) != normalisiere_name(name)
                and not _gleiche_ustid(k, ust_id)
            ):
                widerspruch = (
                    f"über die IBAN als {k.name} erkannt, der Beleg nennt „{name}“ — "
                    "Factoring, Zahlungsdienst oder neuer Name?"
                )
            return Suchergebnis(k, "IBAN", widerspruch)
    if ust_id:
        for k in kontakte:
            if _gleiche_ustid(k, ust_id):
                return Suchergebnis(k, "USt-IdNr.")
    schluessel = normalisiere_name(name) if name else ""
    if schluessel:
        for k in kontakte:
            if normalisiere_name(k.name) != schluessel:
                continue
            grund = _namenstreffer_passt_nicht(
                k, ust_id, land, plz, email, mit_anschrift
            )
            if grund is not None:
                konto = k.debitor_konto or k.kreditor_konto or str(k.id)[:8]
                ausgeschlossen.append(f"gleichnamiger Kontakt {konto}: {grund}")
                continue
            return Suchergebnis(k, "Name")
    return Suchergebnis(None, None, "; ".join(ausgeschlossen) or None)


def finde_kontakt(
    kontakte: list[Kontakt],
    iban: str | None = None,
    ust_id: str | None = None,
    name: str | None = None,
    land: str | None = None,
) -> tuple[Kontakt | None, str | None]:
    """Sucht den Kontakt; liefert (Kontakt, Merkmal) oder (None, None) — ohne
    Kandidaten, die dem Beleg widersprechen (andere USt-IdNr., anderes Land)."""
    r = suche_kontakt(kontakte, iban=iban, ust_id=ust_id, name=name, land=land)
    return r.kontakt, r.merkmal


def naechste_kontonummer(belegt: set[str], von: int, bis: int) -> str:
    """Nächste freie Personenkontonummer im Kreis (hinter der höchsten vergebenen)."""
    im_kreis = [int(n) for n in belegt if n.isdigit() and von <= int(n) <= bis]
    naechste = max(im_kreis) + 1 if im_kreis else von
    if naechste > bis:
        msg = f"Personenkontenkreis {von}–{bis} ist voll"
        raise ValueError(msg)
    return str(naechste)
