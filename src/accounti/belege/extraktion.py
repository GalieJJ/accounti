"""Regelwerk-Extraktion: Felder, Steuerzeilen und Summen aus einem Belegtext.

Die Regeln sind bewusst vorsichtig — ein leeres Feld ist besser als ein falsches.
Was hier offen bleibt, darf die LLM-Stufe ergänzen oder der Mensch nachtragen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from accounti.belege.zahlen import BETRAG, DATUM, parse_betrag, parse_datum

CENT = Decimal("0.01")
TOLERANZ = Decimal("0.02")  # Rundungsdifferenzen je Steuerzeile


@dataclass(frozen=True)
class Steuerzeile:
    satz: Decimal
    netto: Decimal
    steuer: Decimal


@dataclass
class Extrakt:
    belegnummer: str | None = None
    belegdatum: date | None = None
    leistungsdatum: date | None = None
    lieferant_name: str | None = None
    lieferant_ust_id: str | None = None
    ust_ids: list[str] = field(default_factory=list)
    iban: str | None = None
    zahlungsziel: date | None = None
    skonto_prozent: Decimal | None = None
    skonto_tage: int | None = None
    steuerzeilen: list[Steuerzeile] = field(default_factory=list)
    netto: Decimal | None = None
    steuer: Decimal | None = None
    brutto: Decimal | None = None
    rechenprobe: bool | None = None


# ---------------------------------------------------------------------------
# Muster
# ---------------------------------------------------------------------------

_I = re.IGNORECASE

_BELEGNUMMER = re.compile(
    r"(?:rechnungs?[\s-]*(?:nr|nummer)|rechnung\s+nr|re[\s-]?nr|"
    r"beleg[\s-]*(?:nr|nummer)|bon[\s-]*nr|quittungs?[\s-]*nr|"
    r"invoice\s*(?:no|number|#))\.?\s*[:#]?\s*"
    r"([A-Z0-9][A-Z0-9\-/_.]*\d[A-Z0-9\-/_]*)",
    _I,
)
_BELEGDATUM = re.compile(
    r"(?:\b(?:rechnungs|beleg|ausstellungs|abrechnungs)?datum|invoice\s+date)"
    rf"\s*[:\s]\s*({DATUM})",
    _I,
)
_LEISTUNGSDATUM = re.compile(
    rf"(?:leistungsdatum|lieferdatum|leistungszeitraum)\s*:?\s*({DATUM})", _I
)
_DATUM_IRGENDWO = re.compile(DATUM, _I)
_RECHTSFORM = re.compile(
    r"\b(?:GmbH|AG|UG|KG|OHG|GbR|SE|mbH|e\.\s?K\.|e\.\s?V\.|Ltd\.?|Inc\.?|LLC|B\.V\.)"
    r"(?=$|[\s,.&])"
)
_UST_ID_LABEL = re.compile(
    r"(?:USt[\s.-]*Id(?:ent)?[\s.-]*(?:Nr)?|VAT[\s.-]*(?:ID|No|Reg)?|UID)\.?\s*:?\s*"
    r"([A-Z]{2}[\s0-9A-Z]{8,14}?)(?=\s*(?:$|[·|,;]))",
    _I | re.MULTILINE,
)
_UST_ID_DE = re.compile(r"\bDE\s?\d{3}\s?\d{3}\s?\d{3}\b")
_IBAN_KANDIDAT = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}")
_STEUERWORT = re.compile(r"\b(?:USt|MwSt|Mehrwertsteuer|Umsatzsteuer|VAT)\b|Mwst\.", _I)
_PROZENT = re.compile(r"(\d{1,2}(?:,\d{1,2})?)\s*%")
_BETRAG = re.compile(BETRAG)
_NETTO = re.compile(
    r"summe\s+netto|netto\s*summe|nettobetrag|gesamt\s*netto|zwischensumme|\bnetto\b",
    _I,
)
# Absteigende Priorität; die allgemeinen Wörter erst, wenn nichts Genaueres steht.
_BRUTTO = [
    re.compile(p, _I)
    for p in (
        r"rechnungsbetrag|gesamtbetrag|endbetrag|zahlbetrag|zu\s+zahlen",
        r"bruttobetrag|gesamt\s*brutto|summe\s+brutto|\bbrutto\b",
        r"gesamtsumme|\bsumme\b|\btotal\b|\bgesamt\b",
    )
]
_ZAHLBAR_BIS = re.compile(
    rf"(?:zahlbar\s+bis\s*(?:zum\s*)?|fällig\s*(?:am|bis)?\s*:?\s*)({DATUM})", _I
)
_ZAHLBAR_TAGE = re.compile(r"innerhalb\s+(?:von\s+)?(\d{1,3})\s+tag", _I)


# ---------------------------------------------------------------------------
# Einzelfelder
# ---------------------------------------------------------------------------


def _zeilen(text: str) -> list[str]:
    return [z.strip() for z in text.splitlines() if z.strip()]


def _iban_gueltig(iban: str) -> bool:
    umgestellt = iban[4:] + iban[:4]
    ziffern = "".join(str(int(c, 36)) for c in umgestellt)
    return int(ziffern) % 97 == 1


def _finde_iban(text: str) -> str | None:
    for treffer in _IBAN_KANDIDAT.finditer(text):
        roh = treffer.group().replace(" ", "")
        # Der Kandidat kann Folgetext mitnehmen — von lang nach kurz prüfen.
        for laenge in range(min(len(roh), 34), 14, -1):
            if _iban_gueltig(roh[:laenge]):
                return roh[:laenge]
    return None


def _finde_ust_ids(text: str) -> list[str]:
    gefunden: list[str] = []
    for muster in (_UST_ID_LABEL, _UST_ID_DE):
        for treffer in muster.finditer(text):
            wert = re.sub(r"\s", "", treffer.group(1 if muster.groups else 0)).upper()
            if wert not in gefunden and re.fullmatch(r"[A-Z]{2}[0-9A-Z]{8,12}", wert):
                gefunden.append(wert)
    return gefunden


def _finde_lieferant(zeilen: list[str]) -> str | None:
    kopf = zeilen[:8]
    for zeile in kopf:
        if _RECHTSFORM.search(zeile) and len(zeile) <= 80:
            return zeile
    return kopf[0] if kopf else None


def _betraege(zeile: str) -> list[Decimal]:
    werte = [parse_betrag(t) for t in _BETRAG.findall(zeile)]
    return [w for w in werte if w is not None]


def _steuerzeile(zeile: str) -> Steuerzeile | None:
    prozent = _PROZENT.search(zeile)
    if not (_STEUERWORT.search(zeile) and prozent):
        return None
    satz = Decimal(prozent.group(1).replace(",", "."))
    if satz <= 0:
        return None
    rest = zeile[: prozent.start()] + " " + zeile[prozent.end() :]
    werte = [abs(w) for w in _betraege(rest)]

    def passt(netto: Decimal, steuer: Decimal) -> bool:
        return abs((netto * satz / 100).quantize(CENT) - steuer) <= TOLERANZ

    # Netto, Steuer, Brutto in einer Zeile (Kassenbon)
    if len(werte) >= 3 and werte[0] + werte[1] == werte[2]:
        return Steuerzeile(satz, werte[0], werte[1])
    if len(werte) >= 2:
        groesser, kleiner = max(werte[-2:]), min(werte[-2:])
        if passt(groesser, kleiner):
            return Steuerzeile(satz, groesser, kleiner)
    if werte:
        steuer = werte[-1]
        return Steuerzeile(satz, (steuer * 100 / satz).quantize(CENT), steuer)
    return None


def _betrag_nach_label(zeilen: list[str], muster: re.Pattern[str]) -> Decimal | None:
    wert = None
    for zeile in zeilen:
        treffer = muster.search(zeile)
        if not treffer:
            continue
        werte = _betraege(zeile[treffer.end() :])
        if werte:
            # erster Betrag hinter dem Label; die letzte Fundzeile gewinnt
            wert = werte[0]
    return wert


def _brutto(zeilen: list[str]) -> Decimal | None:
    """Gesamtbetrag: erster Betrag hinter einem Brutto-Label, die letzte Zeile gewinnt.

    Steht zwischen Label und Betrag „netto" oder ein Steuersatz (ohne „inkl."),
    ist es keine Bruttosumme — z.B. „Summe netto 150,00" oder „Gesamt 19 % USt".
    """
    for muster in _BRUTTO:
        wert = None
        for zeile in zeilen:
            for label in muster.finditer(zeile):
                rest = zeile[label.end() :]
                betrag = _BETRAG.search(rest)
                if betrag is None:
                    continue
                zwischen = rest[: betrag.start()]
                if _NETTO.search(zwischen):
                    continue
                steuerhinweis = "%" in zwischen or _STEUERWORT.search(zwischen)
                if steuerhinweis and not re.search(r"inkl", zwischen, _I):
                    continue
                if (w := parse_betrag(betrag.group())) is not None:
                    wert = w
                    break
        if wert is not None:
            return wert
    return None


# ---------------------------------------------------------------------------
# Gesamt
# ---------------------------------------------------------------------------


def extrahiere(text: str) -> Extrakt:
    """Liest alle Felder, die das Regelwerk sicher erkennt."""
    zeilen = _zeilen(text)
    e = Extrakt()

    if m := _BELEGNUMMER.search(text):
        e.belegnummer = m.group(1).rstrip(".")
    if m := _LEISTUNGSDATUM.search(text):
        e.leistungsdatum = parse_datum(m.group(1))
    if m := _BELEGDATUM.search(text):
        e.belegdatum = parse_datum(m.group(1))
    elif m := _DATUM_IRGENDWO.search(text):
        e.belegdatum = parse_datum(m.group())

    e.lieferant_name = _finde_lieferant(zeilen)
    e.ust_ids = _finde_ust_ids(text)
    e.lieferant_ust_id = e.ust_ids[0] if e.ust_ids else None
    e.iban = _finde_iban(text)

    for zeile in zeilen:
        if "skonto" in zeile.lower():
            if (p := _PROZENT.search(zeile)) and e.skonto_prozent is None:
                e.skonto_prozent = Decimal(p.group(1).replace(",", "."))
            if (t := _ZAHLBAR_TAGE.search(zeile)) and e.skonto_tage is None:
                e.skonto_tage = int(t.group(1))
        elif m := _ZAHLBAR_BIS.search(zeile):
            e.zahlungsziel = e.zahlungsziel or parse_datum(m.group(1))
        elif (t := _ZAHLBAR_TAGE.search(zeile)) and e.belegdatum:
            e.zahlungsziel = e.zahlungsziel or e.belegdatum + timedelta(int(t.group(1)))

    gesehen: set[Decimal] = set()
    for zeile in zeilen:
        sz = _steuerzeile(zeile)
        if sz is not None and sz.satz not in gesehen:
            gesehen.add(sz.satz)
            e.steuerzeilen.append(sz)

    netto_gefunden = _betrag_nach_label(
        [z for z in zeilen if not _PROZENT.search(z)], _NETTO
    )
    brutto_gefunden = _brutto(zeilen)
    steuer_summe = sum((s.steuer for s in e.steuerzeilen), Decimal("0.00"))
    netto_summe = sum((s.netto for s in e.steuerzeilen), Decimal("0.00"))

    e.brutto = brutto_gefunden
    e.steuer = steuer_summe if e.steuerzeilen else None
    e.netto = netto_gefunden if netto_gefunden is not None else None
    if e.netto is None and e.steuerzeilen:
        e.netto = netto_summe
    if e.brutto is None and e.netto is not None and e.steuer is not None:
        e.brutto = e.netto + e.steuer

    # Rechenprobe nur, wenn Brutto und Steuer unabhängig gefunden wurden.
    if brutto_gefunden is not None and e.steuerzeilen and e.netto is not None:
        e.rechenprobe = abs(e.netto + steuer_summe - brutto_gefunden) <= TOLERANZ and (
            netto_gefunden is None or abs(netto_gefunden - netto_summe) <= TOLERANZ
        )
    return e
