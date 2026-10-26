"""Regelwerk-Extraktion: Felder, Steuerzeilen und Summen aus einem Belegtext.

Die Regeln sind bewusst vorsichtig — ein leeres Feld ist besser als ein falsches.
Was hier offen bleibt, darf die LLM-Stufe ergänzen oder der Mensch nachtragen.

Eine Rechnung ohne Umsatzsteuer weist keine Steuer aus, sie trägt einen Hinweis: bei
§ 13b UStG „Steuerschuldnerschaft des Leistungsempfängers“ (§ 14a Abs. 5 UStG — ein
Steuerausweis ist dort sogar verboten), bei der ig. Lieferung den Hinweis auf die
Steuerfreiheit (§ 14a Abs. 3 UStG), beim Kleinunternehmer § 19 UStG, bei steuerfreien
Leistungen § 4 UStG (§ 14 Abs. 4 Nr. 8 UStG). Eine 0-%-Zeile und dieser Hinweis gelten
deshalb als Steuerangabe (``steuerkennzeichen``, UNTDID 5305: AE, K, E).

Beträge behalten ihr Vorzeichen: Eine Gutschrift bzw. Rechnungskorrektur des
Lieferanten mindert Aufwand und Vorsteuer (§ 17 Abs. 1 UStG) — gedruckte Minusbeträge
werden übernommen, ein Korrekturbeleg mit positiven Beträgen wird negiert.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from accounti.belege.zahlen import BETRAG, DATUM, parse_betrag, parse_datum

CENT = Decimal("0.01")
TOLERANZ = Decimal("0.02")  # Rundungsdifferenzen je Steuerzeile


NULL = Decimal("0.00")

# Steuerfall ohne Steuerausweis (UNTDID 5305) → Text für Hinweise und Positionen
STEUERKENNZEICHEN = {
    "AE": "Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG)",
    "K": "steuerfreie innergemeinschaftliche Lieferung (§ 4 Nr. 1 Buchst. b UStG)",
    "E": "steuerfrei bzw. Kleinunternehmer (§ 4, § 19 UStG)",
}


@dataclass(frozen=True)
class Steuerzeile:
    satz: Decimal
    netto: Decimal
    steuer: Decimal
    # 0 %: die Zeile nennt nur „0,00“ — die Bemessungsgrundlage kommt aus den Summen
    basis_offen: bool = field(default=False, compare=False)


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
    steuerkennzeichen: str | None = None  # AE, K, E — Hinweis statt Steuerausweis
    korrektur: str | None = None  # "gutschrift" oder "korrektur" (Titel des Belegs)
    vorzeichen_gedreht: bool = False  # positiver Korrekturbeleg → Beträge negiert


# ---------------------------------------------------------------------------
# Muster
# ---------------------------------------------------------------------------

_I = re.IGNORECASE

_BELEGNUMMER = re.compile(
    r"(?:rechnungs?[\s-]*(?:nr|nummer)|rechnung\s+nr|re[\s-]?nr|"
    r"beleg[\s-]*(?:nr|nummer)|bon[\s-]*nr|quittungs?[\s-]*nr|"
    r"gutschrifts?[\s-]*(?:nr|nummer)|credit\s*note\s*(?:no|number|#)|"
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
        r"rechnungsbetrag|gesamtbetrag|endbetrag|zahlbetrag|zu\s+zahlen|"
        r"gutschrifts?betrag|erstattungsbetrag|korrekturbetrag|zu\s+erstatten|"
        r"gutschrift\s+gesamt",
        r"bruttobetrag|gesamt\s*brutto|summe\s+brutto|\bbrutto\b",
        r"gesamtsumme|\bsumme\b|\btotal\b|\bgesamt\b",
    )
]
_ZAHLBAR_BIS = re.compile(
    rf"(?:zahlbar\s+bis\s*(?:zum\s*)?|fällig\s*(?:am|bis)?\s*:?\s*)({DATUM})", _I
)
_ZAHLBAR_TAGE = re.compile(r"innerhalb\s+(?:von\s+)?(\d{1,3})\s+tag", _I)
# Teilsätze einer Zahlungsbedingung („…, oder …; bzw. …“) — „2,5 %“ bleibt ganz
_TEILSATZ = re.compile(r"\s+oder\s+|\s+bzw\.?\s+|;\s*|,\s+", _I)
# Ausdrücklich ohne Skonto — schlägt ein Skonto aus den Stammdaten (0 % ≠ unbekannt)
_OHNE_ABZUG = re.compile(
    r"ohne\s+(?:jeden\s+)?(?:skonto|abzug)|rein\s+netto|netto\s+kasse|"
    r"kein(?:en)?\s+skonto|skonto\s+(?:wird\s+)?nicht\s+gew[äa]hrt",
    _I,
)
# Hinweistexte statt Steuerausweis — die erste passende Art gewinnt
_KENNZEICHEN: list[tuple[str, re.Pattern[str]]] = [
    (
        "AE",
        re.compile(
            r"steuerschuldnerschaft\s+des\s+leistungsempf|reverse[\s-]*charge|"
            r"§\s*13\s*b\b|\b13b\s+ustg|steuerschuld\s+(?:geht\s+)?(?:auf\s+den|"
            r"beim)\s+leistungsempf|übergang\s+der\s+steuerschuld|autoliquidation|"
            r"inversione\s+contabile|btw\s+verlegd|omvänd\s+skattskyldighet|"
            r"odwrotne\s+obciążenie",
            _I,
        ),
    ),
    (
        "K",
        re.compile(
            r"innergemeinschaftliche\s+lieferung|"
            r"§\s*4\s*nr\.?\s*1\s*(?:buchst\.?\s*)?b\b|§\s*6\s*a\s+ustg|"
            r"intra[\s-]community\s+(?:supply|delivery)|"
            r"livraison\s+intracommunautaire|cessione\s+intracomunitaria",
            _I,
        ),
    ),
    (
        "E",
        re.compile(
            r"§\s*19\s*(?:abs\.?\s*1\s*)?ustg|kleinunternehmer|"
            r"(?:umsatz)?steuerfrei\w*\s+(?:nach|gem(?:\.|äß))\s*§\s*4\b|"
            r"§\s*4\s*nr\.?\s*\d+\s*(?:buchst\.?\s*[a-z]\s*)?ustg|"
            r"(?:umsatz)?steuerbefreit",
            _I,
        ),
    ),
]
# Titel eines Belegs: die ganze Zeile ist das Wort, höchstens mit Nummer, Datum oder
# Bezug („Rechnungskorrektur zur Rechnung Nr. RE-5“) — nie ein Satz wie
# „Rechnungskorrektur nur schriftlich innerhalb von 8 Tagen“ (Nachprüfung C, M1)
_KORREKTUR_WORT = (
    r"(?:rechnungskorrektur|korrekturrechnung|storno[\s-]*rechnung|rechnungsstorno|"
    r"gutschrift|credit\s+note)"
)
_NUMMER = r"[A-Z0-9][A-Z0-9\-/_.]*\d[A-Z0-9\-/_]*"  # wie bei der Belegnummer
_TITELZUSATZ = (
    r"(?:\s*[-:,]?\s*(?:"
    rf"(?:nr|nummer|no|number)\b\.?\s*[:#]?\s*{_NUMMER}|#\s*{_NUMMER}"
    r"|(?:zur|zu|für\s+die)\s+rechnung"
    rf"(?:\s*(?:nr|nummer)\b\.?)?\s*[:#]?\s*(?:{_NUMMER})?"
    rf"|(?:vom|datum\s*:?)\s*(?:{DATUM})"
    r"))*\s*[.:]?\s*$"
)
# „Gutschrift (Rechnungskorrektur)“, „Gutschrift / Credit Note“
_KORREKTUR_TITEL = re.compile(
    rf"^\s*{_KORREKTUR_WORT}"
    rf"(?:\s*(?:\(\s*{_KORREKTUR_WORT}\s*\)|[/–-]\s*{_KORREKTUR_WORT}))?"
    rf"{_TITELZUSATZ}",
    _I,
)
_RECHNUNG_TITEL = re.compile(rf"^\s*(?:rechnung|invoice|faktura){_TITELZUSATZ}", _I)
_KORREKTUR_EINDEUTIG = re.compile(
    r"korrektur|storno|credit\s+note", _I
)  # „Gutschrift“ allein kann auch § 14 Abs. 2 S. 2 UStG sein


# ---------------------------------------------------------------------------
# Einzelfelder
# ---------------------------------------------------------------------------


def _zeilen(text: str) -> list[str]:
    return [z.strip() for z in text.splitlines() if z.strip()]


def iban_gueltig(iban: str) -> bool:
    umgestellt = iban[4:] + iban[:4]
    ziffern = "".join(str(int(c, 36)) for c in umgestellt)
    return int(ziffern) % 97 == 1


def _finde_iban(text: str) -> str | None:
    for treffer in _IBAN_KANDIDAT.finditer(text):
        roh = treffer.group().replace(" ", "")
        # Der Kandidat kann Folgetext mitnehmen — von lang nach kurz prüfen.
        for laenge in range(min(len(roh), 34), 14, -1):
            if iban_gueltig(roh[:laenge]):
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
    """Satz, Netto und Steuer einer Steuerzeile — mit dem Vorzeichen des Belegs."""
    prozent = _PROZENT.search(zeile)
    if not (_STEUERWORT.search(zeile) and prozent):
        return None
    satz = Decimal(prozent.group(1).replace(",", "."))
    rest = zeile[: prozent.start()] + " " + zeile[prozent.end() :]
    werte = _betraege(rest)
    if satz == 0:
        # 0 %: keine Steuer; ein Betrag ungleich 0 ist die Bemessungsgrundlage
        basis = [w for w in werte if w != 0]
        if basis:
            return Steuerzeile(satz, max(basis, key=abs), NULL)
        return Steuerzeile(satz, NULL, NULL, basis_offen=True)

    def passt(netto: Decimal, steuer: Decimal) -> bool:
        return abs((abs(netto) * satz / 100).quantize(CENT) - abs(steuer)) <= TOLERANZ

    # Netto, Steuer, Brutto in einer Zeile (Kassenbon)
    if len(werte) >= 3 and werte[0] + werte[1] == werte[2]:
        return Steuerzeile(satz, werte[0], werte[1])
    if len(werte) >= 2:
        a, b = werte[-2], werte[-1]
        groesser, kleiner = (a, b) if abs(a) >= abs(b) else (b, a)
        if passt(groesser, kleiner):
            return Steuerzeile(satz, groesser, kleiner)
    if werte:
        steuer = werte[-1]
        return Steuerzeile(satz, (steuer * 100 / satz).quantize(CENT), steuer)
    return None


def _steuerkennzeichen(text: str) -> str | None:
    for kennzeichen, muster in _KENNZEICHEN:
        if muster.search(text):
            return kennzeichen
    return None


def _korrektur(zeilen: list[str]) -> str | None:
    """„korrektur“ (Rechnungskorrektur, Storno, Credit Note), „gutschrift“ oder None.

    Zählt nur als Belegtitel unter den ersten 40 Zeilen — und nicht, wenn vorher der
    Titel „Rechnung“ steht (dann ist es eine Zwischenüberschrift)."""
    for zeile in zeilen[:40]:
        if _RECHNUNG_TITEL.match(zeile):
            return None
        if _KORREKTUR_TITEL.match(zeile):
            return "korrektur" if _KORREKTUR_EINDEUTIG.search(zeile) else "gutschrift"
    return None


def _zahlungsteile(zeile: str) -> list[tuple[str, bool]]:
    """(Text, Skonto?) einer Zahlungsbedingung: „30 Tage ohne Abzug oder 10 Tage mit
    2 % Skonto“ → Ziel und Skonto je Teilsatz (Nachprüfung C, N5). Nennt der Teilsatz
    mit „Skonto“ selbst keine Frist („Skonto 2 %, innerhalb 10 Tagen“), bleibt die
    Zeile ganz Skonto — wie bisher."""
    if "skonto" not in zeile.lower():
        return [(zeile, False)]
    teile = _TEILSATZ.split(zeile)
    skonto = [t for t in teile if "skonto" in t.lower()]
    if not any(_ZAHLBAR_TAGE.search(t) for t in skonto):
        return [(zeile, True)]
    return [(t, "skonto" in t.lower()) for t in teile]


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

    ohne_abzug = False
    for zeile in zeilen:
        ohne_abzug = ohne_abzug or bool(_OHNE_ABZUG.search(zeile))
        for teil, ist_skonto in _zahlungsteile(zeile):
            if ist_skonto:
                if (p := _PROZENT.search(teil)) and e.skonto_prozent is None:
                    e.skonto_prozent = Decimal(p.group(1).replace(",", "."))
                if (t := _ZAHLBAR_TAGE.search(teil)) and e.skonto_tage is None:
                    e.skonto_tage = int(t.group(1))
            elif m := _ZAHLBAR_BIS.search(teil):
                e.zahlungsziel = e.zahlungsziel or parse_datum(m.group(1))
            elif (t := _ZAHLBAR_TAGE.search(teil)) and e.belegdatum:
                tage = int(t.group(1))
                e.zahlungsziel = e.zahlungsziel or e.belegdatum + timedelta(tage)
    if ohne_abzug and e.skonto_prozent is None:
        # „ohne Abzug“: ausdrücklich kein Skonto — nicht das des Kontakts nehmen
        e.skonto_prozent, e.skonto_tage = Decimal("0"), 0

    gesehen: set[Decimal] = set()
    for zeile in zeilen:
        sz = _steuerzeile(zeile)
        if sz is not None and sz.satz not in gesehen:
            gesehen.add(sz.satz)
            e.steuerzeilen.append(sz)

    e.steuerkennzeichen = _steuerkennzeichen(text)
    netto_gefunden = _betrag_nach_label(
        [z for z in zeilen if not _PROZENT.search(z)], _NETTO
    )
    brutto_gefunden = _brutto(zeilen)
    _ergaenze_nullsatz(e, netto_gefunden, brutto_gefunden)
    steuer_summe = sum((s.steuer for s in e.steuerzeilen), NULL)
    netto_summe = sum((s.netto for s in e.steuerzeilen), NULL)

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
    # Netto, Steuer und Brutto tragen dasselbe Vorzeichen — sonst stimmt etwas nicht
    if not _vorzeichen_einig(e):
        e.rechenprobe = False

    e.korrektur = _korrektur(zeilen)
    if e.korrektur and _alle_positiv(e):
        _negiere(e)
    return e


def _ergaenze_nullsatz(
    e: Extrakt, netto: Decimal | None, brutto: Decimal | None
) -> None:
    """0-%-Zeile ohne Bemessungsgrundlage aus den Summen ergänzen; ein Hinweistext
    ohne 0-%-Zeile wird eine — aber nur, wenn Netto und Brutto nicht widersprechen
    (sonst ist es eine besteuerte Rechnung, deren Steuerzeile nicht gelesen wurde)."""
    basis = netto if netto is not None else brutto
    andere = sum((s.netto for s in e.steuerzeilen if not s.basis_offen), NULL)
    for i, s in enumerate(e.steuerzeilen):
        if s.basis_offen and basis is not None:
            e.steuerzeilen[i] = Steuerzeile(s.satz, basis - andere, NULL)
    e.steuerzeilen = [s for s in e.steuerzeilen if not s.basis_offen]
    if (
        e.steuerkennzeichen is not None
        and not e.steuerzeilen
        and basis is not None
        and (netto is None or brutto is None or abs(netto - brutto) <= TOLERANZ)
    ):
        e.steuerzeilen.append(Steuerzeile(Decimal("0"), basis, NULL))


def _vorzeichen_einig(e: Extrakt) -> bool:
    werte = [e.netto, e.steuer, e.brutto] + [
        w for s in e.steuerzeilen for w in (s.netto, s.steuer)
    ]
    gesetzt = [w for w in werte if w]
    return not (any(w > 0 for w in gesetzt) and any(w < 0 for w in gesetzt))


def _alle_positiv(e: Extrakt) -> bool:
    werte = [w for w in (e.netto, e.steuer, e.brutto) if w]
    return bool(werte) and all(w > 0 for w in werte)


def _negiere(e: Extrakt) -> None:
    """Korrekturbeleg mit positiven Beträgen: als Minderung übernehmen."""
    e.steuerzeilen = [
        Steuerzeile(s.satz, _minus(s.netto), _minus(s.steuer)) for s in e.steuerzeilen
    ]
    e.netto = _minus(e.netto) if e.netto is not None else None
    e.steuer = _minus(e.steuer) if e.steuer is not None else None
    e.brutto = _minus(e.brutto) if e.brutto is not None else None
    e.vorzeichen_gedreht = True


def _minus(wert: Decimal) -> Decimal:
    return -wert if wert else wert  # keine „-0.00“
