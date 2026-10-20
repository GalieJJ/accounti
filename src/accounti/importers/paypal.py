"""PayPal-Aktivitäten (CSV) → eine Abrechnung über den Zeitraum der Datei.

PayPal ist ein eigenes Konto mit Guthaben, kein bloßer Zahlungsweg. Format:
„Aktivitäten herunterladen“ als CSV (Kopfzeile u. a. ``Datum, Uhrzeit, Zeitzone, Name,
Typ, Status, Währung, Brutto, Gebühr, Netto, …, Transaktionscode, …, Zugehöriger
Transaktionscode, …, Guthaben, …, Land, …, Auswirkung auf Guthaben``). Je Zeile wird
das Guthaben der Währung fortgeschrieben; die Kette (vorheriges Guthaben + Netto =
Guthaben) wird geprüft.

Fremdwährungsverkäufe werden über die zugehörige Währungsumrechnung in EUR übernommen:
Die EUR-Zeile der Umrechnung ist der Nettobetrag, Brutto und Gebühr werden zum
effektiven Kurs dieser Umrechnung anteilig umgerechnet. So bleibt das EUR-Guthaben
exakt.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from accounti.importers.marktplatz import (
    MarktplatzFormatError,
    MarktplatzImporter,
    dekodiere,
    erkenne_dezimal,
    land_iso,
    lies_betrag,
    lies_datum,
    lies_tabelle,
    registriere,
    spalte,
)
from accounti.models.integrationen import (
    Abrechnung,
    Befund,
    Gebuehrenart,
    Laenderangabe,
    Marktplatzposten,
    Postenart,
    Schweregrad,
)

NULL = Decimal("0")
CENT = Decimal("0.01")
KONTOWAEHRUNG = "EUR"
_ABGESCHLOSSEN = {"abgeschlossen", "completed", "erledigt"}
_NICHT_SALDENWIRKSAM = {"memo"}


@dataclass
class _Zeile:
    nr: int
    datum: date
    zeit: str
    name: str
    typ: str
    waehrung: str
    brutto: Decimal
    gebuehr: Decimal
    netto: Decimal
    code: str
    zugehoerig: str
    guthaben: Decimal | None
    land: str | None
    text: str


# Zahlungsarten aus dem Checkout eines Shops oder Marktplatzes — nur sie sind Verkäufe
_CHECKOUT = (
    "website",
    "checkout",
    "handy",
    "mobil",
    "warenkorb",
    "shopping cart",
    "ebay",
)


@dataclass(frozen=True)
class FruehereUmsaetze:
    """Transaktionscodes aus schon importierten PayPal-Exporten."""

    verkaeufe: frozenset[str] = frozenset()  # Checkout-Erlöse (Code oder Bezug)
    alle: frozenset[str] = frozenset()


def _art(
    z: _Zeile,
    verkaeufe: Collection[str] = (),
    bekannt: Collection[str] = (),
) -> tuple[Postenart, str | None]:
    """Postenart der Zeile und ggf. der Code des Hinweises dazu.

    Verkauf ist nur eine eingehende Checkout-Zahlung; andere eingehende Zahlungen
    (z.B. auf eine Ausgangsrechnung) und Erstattungen an uns bleiben unverbucht für
    ``opos zuordnen``/``classify``. Eine Rückzahlung an den Kunden mindert den Erlös
    nur, wenn ihre zugehörige Zahlung ein Checkout-Verkauf ist (``verkaeufe``: aus
    dieser Datei oder früheren Exporten) — sonst bleibt sie wie die Zahlung selbst
    unverbucht. Einbehaltungen und ihre Freigaben gehen auf das Einbehaltskonto,
    Rückbuchungen (Chargebacks) und Zahlungsrückbuchungen zur Prüfung auf das
    Klärungskonto.
    """
    t = z.typ.casefold()
    if "währungsumrechnung" in t or "currency conversion" in t:
        return Postenart.UMRECHNUNG, None
    if ("abbuchung" in t and "bank" in t) or "withdrawal" in t:
        return Postenart.AUSZAHLUNG, None
    if "bankgutschrift" in t or "einzahlung" in t or "deposit" in t:
        return Postenart.EINZAHLUNG, None
    if "einbehalt" in t or "hold" in t:
        return Postenart.EINBEHALT, None  # Einbehaltung (−) oder Freigabe (+)
    if "rückbuchung" in t or "reversal" in t or "chargeback" in t:
        return Postenart.SONSTIGES, "rueckbuchung"
    if "rückzahlung" in t or "rückerstattung" in t or "refund" in t:
        if z.brutto >= 0:
            return Postenart.ZAHLUNG, "eingehende_zahlung"  # Erstattung an uns
        if z.zugehoerig and z.zugehoerig in verkaeufe:
            return Postenart.ERSTATTUNG, None
        if z.zugehoerig and z.zugehoerig in bekannt:
            return Postenart.ZAHLUNG, "rueckzahlung_ohne_verkauf"
        return Postenart.ZAHLUNG, "rueckzahlung_unbekannt"
    if "zahlung" in t or "payment" in t:
        if z.brutto <= 0:
            return Postenart.ZAHLUNG, None
        if any(w in t for w in _CHECKOUT):
            return Postenart.ERLOES, None
        return Postenart.ZAHLUNG, "eingehende_zahlung"
    return Postenart.SONSTIGES, None


class PaypalImporter(MarktplatzImporter):
    name = "paypal"
    beschreibung = "PayPal-Aktivitäten (CSV-Download)"

    def lies(
        self,
        inhalt: bytes,
        dateiname: str,
        laender: dict[str, Laenderangabe] | None = None,
        *,
        frueher: FruehereUmsaetze | None = None,
    ) -> list[Abrechnung]:
        """``frueher``: Codes schon importierter Exporte (für Rückzahlungen)."""
        zeilen, befunde = self._zeilen(inhalt)
        if not zeilen:
            raise MarktplatzFormatError(
                "keine abgeschlossenen PayPal-Umsätze in der Datei"
            )
        anfang, ende = self._guthabenkette(zeilen, befunde)
        abrechnung = Abrechnung(
            marktplatz=self.name,
            nummer=f"PayPal {zeilen[0].datum:%Y-%m-%d} bis {zeilen[-1].datum:%Y-%m-%d}",
            von=zeilen[0].datum,
            bis=zeilen[-1].datum,
            waehrung=KONTOWAEHRUNG,
            anfangssaldo=anfang,
            endsaldo=ende,
            dateiname=dateiname,
            befunde=befunde,
        )
        umrechnungen: dict[str, list[_Zeile]] = defaultdict(list)
        for z in zeilen:
            if _art(z)[0] is Postenart.UMRECHNUNG and z.zugehoerig:
                umrechnungen[z.zugehoerig].append(z)
        # EUR-Seiten von Umrechnungen, die zu einem Fremdwährungsumsatz gehören
        verbraucht = {
            u.code
            for z in zeilen
            if z.waehrung != KONTOWAEHRUNG and _art(z)[0] is not Postenart.UMRECHNUNG
            for u in umrechnungen[z.code]
            if u.waehrung == KONTOWAEHRUNG
        }
        frueher = frueher or FruehereUmsaetze()
        verkaeufe = frueher.verkaeufe | {
            c
            for z in zeilen
            if _art(z)[0] is Postenart.ERLOES
            for c in (z.code, z.zugehoerig)
            if c
        }
        bekannt = frueher.alle | {z.code for z in zeilen}
        for z in zeilen:
            art, hinweis = _art(z, verkaeufe, bekannt)
            if art is Postenart.UMRECHNUNG:
                if z.waehrung != KONTOWAEHRUNG:
                    self._posten(abrechnung, z, Postenart.UMRECHNUNG, z.netto)
                elif z.code not in verbraucht:
                    self._eur(abrechnung, z, Postenart.SONSTIGES)
                continue
            if z.waehrung == KONTOWAEHRUNG:
                self._eur(abrechnung, z, art, hinweis, z.zugehoerig)
                continue
            # Fremdwährung: EUR-Seite der zugehörigen Umrechnung suchen
            eur = next(
                (u for u in umrechnungen[z.code] if u.waehrung == KONTOWAEHRUNG), None
            )
            self._posten(abrechnung, z, Postenart.UMRECHNUNG, z.netto)
            if eur is None or not z.netto:
                abrechnung.befunde.append(
                    Befund(
                        code="fremdwaehrung",
                        schweregrad=Schweregrad.WARNUNG,
                        text=(
                            f"Zeile {z.nr}: {z.typ} in {z.waehrung} ohne Umrechnung in "
                            "EUR — bleibt Fremdwährungsguthaben, nicht gebucht"
                        ),
                        posten_nr=z.nr,
                    )
                )
                continue
            kurs = eur.netto / z.netto
            brutto = (z.brutto * kurs).quantize(CENT, rounding=ROUND_HALF_UP)
            umgerechnet = _Zeile(
                nr=eur.nr,
                datum=eur.datum,
                zeit=eur.zeit,
                name=z.name,
                typ=z.typ,
                waehrung=KONTOWAEHRUNG,
                brutto=brutto,
                gebuehr=eur.netto - brutto,
                netto=eur.netto,
                code=eur.code,
                zugehoerig=z.code,
                guthaben=eur.guthaben,
                land=z.land,
                text=(
                    f"{z.text} ({z.waehrung} {z.brutto} zum Kurs "
                    f"{kurs.quantize(Decimal('0.000001'))})"
                ),
            )
            self._eur(abrechnung, umgerechnet, art, hinweis, z.zugehoerig)
        return [abrechnung]

    # -- Zeilen ----------------------------------------------------------------

    def _zeilen(self, inhalt: bytes) -> tuple[list[_Zeile], list[Befund]]:
        kopf, roh = lies_tabelle(
            dekodiere(inhalt),
            {
                "Datum",
                "Typ",
                "Status",
                "Währung",
                "Brutto",
                "Netto",
                "Transaktionscode",
            },
        )
        s_gebuehr = spalte(kopf, "Gebühr", "Entgelt")
        s_guthaben = spalte(kopf, "Guthaben")
        s_land = spalte(kopf, "Land", "Ländervorwahl")
        s_wirkung = spalte(kopf, "Auswirkung auf Guthaben")
        dezimal = erkenne_dezimal(w["Brutto"] for _, w in roh)
        befunde: list[Befund] = []
        zeilen = []
        for nr, w in roh:
            if w["Status"].casefold() not in _ABGESCHLOSSEN:
                continue
            if s_wirkung and w[s_wirkung].casefold() in _NICHT_SALDENWIRKSAM:
                continue
            land_text = w.get(s_land, "") if s_land else ""
            land = land_iso(land_text)
            if land_text and land is None:
                befunde.append(
                    Befund(
                        code="land_unbekannt",
                        schweregrad=Schweregrad.WARNUNG,
                        text=f"Zeile {nr}: Land {land_text!r} unbekannt",
                        posten_nr=nr,
                    )
                )
            teile = [w.get("Artikelbezeichnung", ""), w.get("Rechnungsnummer", "")]
            zeilen.append(
                _Zeile(
                    nr=nr,
                    datum=lies_datum(w["Datum"]),
                    zeit=w.get("Uhrzeit", ""),
                    name=w.get("Name", ""),
                    typ=w["Typ"],
                    waehrung=w["Währung"].upper() or KONTOWAEHRUNG,
                    brutto=lies_betrag(w["Brutto"], dezimal),
                    gebuehr=lies_betrag(w[s_gebuehr], dezimal) if s_gebuehr else NULL,
                    netto=lies_betrag(w["Netto"], dezimal),
                    code=w["Transaktionscode"],
                    zugehoerig=w.get("Zugehöriger Transaktionscode", ""),
                    guthaben=(
                        lies_betrag(w[s_guthaben], dezimal)
                        if s_guthaben and w[s_guthaben]
                        else None
                    ),
                    land=land,
                    text=" ".join(t for t in [w["Typ"], *teile] if t),
                )
            )
        if zeilen and (zeilen[0].datum, zeilen[0].zeit) > (
            zeilen[-1].datum,
            zeilen[-1].zeit,
        ):
            zeilen.reverse()  # neueste zuerst exportiert
        return zeilen, befunde

    @staticmethod
    def _guthabenkette(
        zeilen: list[_Zeile], befunde: list[Befund]
    ) -> tuple[Decimal | None, Decimal | None]:
        """Prüft je Währung: vorheriges Guthaben + Netto = Guthaben."""
        letztes: dict[str, Decimal] = {}
        anfang: Decimal | None = None
        for z in zeilen:
            if z.guthaben is None:
                continue
            vorher = letztes.get(z.waehrung)
            if vorher is None:
                if z.waehrung == KONTOWAEHRUNG:
                    anfang = z.guthaben - z.netto
            elif vorher + z.netto != z.guthaben:
                befunde.append(
                    Befund(
                        code="saldensprung",
                        schweregrad=Schweregrad.FEHLER,
                        text=(
                            f"Zeile {z.nr}: Guthaben {z.waehrung} {vorher} + Netto "
                            f"{z.netto} ≠ {z.guthaben} — fehlt eine Zeile im Export?"
                        ),
                        posten_nr=z.nr,
                    )
                )
            letztes[z.waehrung] = z.guthaben
        return anfang, letztes.get(KONTOWAEHRUNG)

    # -- Posten ----------------------------------------------------------------

    @staticmethod
    def _posten(
        abrechnung: Abrechnung,
        z: _Zeile,
        art: Postenart,
        betrag: Decimal,
        gebuehrenart: Gebuehrenart | None = None,
    ) -> None:
        abrechnung.posten.append(
            Marktplatzposten(
                nr=z.nr,
                art=art,
                datum=z.datum,
                betrag=betrag,
                waehrung=z.waehrung,
                beschreibung=z.text,
                gebuehrenart=gebuehrenart,
                bestellnummer=z.zugehoerig or z.code,
                bestimmungsland=(
                    z.land if art in (Postenart.ERLOES, Postenart.ERSTATTUNG) else None
                ),
                referenz=z.code,
                gegenpartei=z.name or None,
            )
        )

    def _eur(
        self,
        abrechnung: Abrechnung,
        z: _Zeile,
        art: Postenart,
        hinweis: str | None = None,
        bezug: str = "",
    ) -> None:
        """``bezug``: zugehöriger Transaktionscode laut Export."""
        if art in (Postenart.ERLOES, Postenart.ERSTATTUNG):
            self._posten(abrechnung, z, art, z.brutto)
            if z.gebuehr:
                self._posten(
                    abrechnung, z, Postenart.GEBUEHR, z.gebuehr, Gebuehrenart.ZAHLUNG
                )
            if z.brutto + z.gebuehr != z.netto:
                abrechnung.befunde.append(
                    Befund(
                        code="zeile_rechnet_nicht",
                        schweregrad=Schweregrad.FEHLER,
                        text=f"Zeile {z.nr}: Brutto + Gebühr ≠ Netto",
                        posten_nr=z.nr,
                    )
                )
            return
        self._posten(abrechnung, z, art, z.netto)
        betrag = f"{z.brutto:.2f}".replace(".", ",")
        if hinweis == "rueckbuchung":
            abrechnung.befunde.append(
                Befund(
                    code="rueckbuchung",
                    schweregrad=Schweregrad.WARNUNG,
                    text=(
                        f"Zeile {z.nr}: {z.typ} über {betrag} {z.waehrung} "
                        f"(zu {z.zugehoerig or z.code}) — auf dem Klärungskonto zur "
                        "Prüfung: Erlösminderung mit Berichtigung der USt "
                        "(§ 17 UStG) oder Forderung an den Käufer"
                    ),
                    posten_nr=z.nr,
                )
            )
        elif hinweis == "eingehende_zahlung":
            abrechnung.befunde.append(
                Befund(
                    code="eingehende_zahlung",
                    schweregrad=Schweregrad.HINWEIS,
                    text=(
                        f"Zeile {z.nr}: {z.text} über {betrag} {z.waehrung} von "
                        f"{z.name or 'unbekannt'} — kein Checkout-Verkauf, nicht als "
                        "Erlös gebucht; mit accounti opos zuordnen bzw. classify "
                        "kontieren"
                    ),
                    posten_nr=z.nr,
                )
            )
        elif hinweis == "rueckzahlung_ohne_verkauf":
            abrechnung.befunde.append(
                Befund(
                    code=hinweis,
                    schweregrad=Schweregrad.HINWEIS,
                    text=(
                        f"Zeile {z.nr}: {z.text} über {betrag} {z.waehrung} an "
                        f"{z.name or 'unbekannt'} zu {bezug} — die zugehörige "
                        "Zahlung war kein Checkout-Verkauf, daher keine "
                        "Erlösminderung; mit accounti opos zuordnen bzw. classify "
                        "kontieren"
                    ),
                    posten_nr=z.nr,
                )
            )
        elif hinweis == "rueckzahlung_unbekannt":
            abrechnung.befunde.append(
                Befund(
                    code="rueckzahlung_ohne_verkauf",
                    schweregrad=Schweregrad.WARNUNG,
                    text=(
                        f"Zeile {z.nr}: {z.text} über {betrag} {z.waehrung} an "
                        f"{z.name or 'unbekannt'} zu {bezug or 'keiner Zahlung'} — "
                        "die zugehörige Zahlung ist nicht importiert, daher nicht "
                        "als Erlösminderung gebucht: war sie ein Verkauf, mit "
                        "Berichtigung der USt (§ 17 UStG) kontieren, sonst mit "
                        "accounti opos zuordnen"
                    ),
                    posten_nr=z.nr,
                )
            )
        elif art is Postenart.SONSTIGES:
            abrechnung.befunde.append(
                Befund(
                    code="unbekannter_posten",
                    schweregrad=Schweregrad.WARNUNG,
                    text=(
                        f"Zeile {z.nr}: Typ {z.typ!r} ist nicht zugeordnet "
                        "— zur Prüfung"
                    ),
                    posten_nr=z.nr,
                )
            )


registriere(PaypalImporter())
