"""Abrechnung → Buchungssätze: jeder Bestandteil einzeln, gegen das Verrechnungskonto.

Erlös (+)       Verrechnungskonto  an  Erlöskonto (je Bestellung, Steuer je Land)
Erstattung (−)  Erlöskonto         an  Verrechnungskonto
Gebühr (−)      Gebührenkonto      an  Verrechnungskonto (je Gebührenart)
Einbehalt (−)   Einbehaltskonto    an  Verrechnungskonto (Freigabe umgekehrt)
Auszahlung      Bank               an  Verrechnungskonto  → ``integrationen.auszahlung``

Bei PayPal ist das Verrechnungskonto das PayPal-Konto selbst; jede Buchung hängt an
ihrem PayPal-Umsatz, Abbuchungen und Bankgutschriften laufen über Geldtransit.

Die Summenprobe vergleicht die Einzelposten mit der gemeldeten Auszahlung. Eine
Abweichung ist ein Befund: Alle Buchungen der Abrechnung gehen zur Prüfung, und es
gibt keine Ausgleichsbuchung — die Differenz bleibt auf dem Verrechnungskonto sichtbar.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from accounti.integrationen.einstellungen import Integrationen, Marktplatzkonten
from accounti.models import Buchungssatz, BuchungStatus
from accounti.models.integrationen import (
    Abrechnung,
    Befund,
    Marktplatzposten,
    Postenart,
    Schweregrad,
)
from accounti.steuer.eu_steuersaetze import EU_STEUERSAETZE, ist_eu_land
from accounti.steuer.oss import OSS_SCHWELLE_EUR
from accounti.steuer.umsatzsteuer import (
    DATEV_BU_SCHLUESSEL,
    OSS_ERLOES_KONTEN_SKR03,
    Geschaeftsvorfall,
    UStBerechner,
)

NULL = Decimal("0")
CENT = Decimal("0.01")
ANZEIGE = {"amazon": "Amazon", "ebay": "eBay", "paypal": "PayPal", "shopify": "Shopify"}
_NICHT_EINZELPOSTEN = {Postenart.AUSZAHLUNG, Postenart.UMRECHNUNG}


def eur_text(betrag: Decimal) -> str:
    """Betrag in deutscher Schreibweise, z.B. ``1.234,56``."""
    return f"{betrag:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@dataclass
class Buchungskontext:
    """Was die Buchung über den Mandanten wissen muss."""

    einstellungen: Integrationen
    oss_registriert: bool = False
    firmen_land: str = "DE"
    # EU-Fernverkäufe an Privatkunden (netto) je Kalenderjahr vor dieser Abrechnung
    eu_b2c_bisher: dict[int, Decimal] = field(default_factory=dict)


@dataclass
class Buchungsergebnis:
    buchungen: list[Buchungssatz] = field(default_factory=list)
    befunde: list[Befund] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Summenprobe
# ---------------------------------------------------------------------------


def summenprobe(abrechnung: Abrechnung) -> list[Befund]:
    """Einzelposten gegen die gemeldete Auszahlung — exakt, ohne Rundungsrest."""
    if abrechnung.auszahlung is None:
        return []
    einzel = sum(
        (p.betrag for p in abrechnung.posten if p.art not in _NICHT_EINZELPOSTEN), NULL
    )
    differenz = abrechnung.auszahlung - einzel
    if not differenz:
        return []
    return [
        Befund(
            code="summe_abweichung",
            schweregrad=Schweregrad.FEHLER,
            text=(
                f"Summe der Einzelposten {eur_text(einzel)} ≠ Auszahlung laut Bericht "
                f"{eur_text(abrechnung.auszahlung)} {abrechnung.waehrung} (Differenz "
                f"{eur_text(differenz)}) — wird nicht ausgeglichen, bitte klären"
            ),
        )
    ]


def ergaenze_auszahlung(abrechnung: Abrechnung) -> None:
    """Legt den Auszahlungsposten an, wenn der Bericht keine eigene Zeile hat.

    Betrag: die gemeldete Auszahlung, sonst die Summe der Einzelposten (dann prüft
    erst der Bankabgleich). PayPal hat keine Auszahlung — es ist ein Konto.
    """
    if abrechnung.marktplatz == "paypal" or any(
        p.art is Postenart.AUSZAHLUNG for p in abrechnung.posten
    ):
        return
    einzel = sum(
        (p.betrag for p in abrechnung.posten if p.art not in _NICHT_EINZELPOSTEN), NULL
    )
    gemeldet = abrechnung.auszahlung is not None
    betrag = abrechnung.auszahlung if abrechnung.auszahlung is not None else einzel
    abrechnung.posten.append(
        Marktplatzposten(
            nr=0,
            art=Postenart.AUSZAHLUNG,
            datum=abrechnung.auszahlungsdatum or abrechnung.bis,
            betrag=-betrag,
            waehrung=abrechnung.waehrung,
            beschreibung=(
                "Auszahlung laut Bericht"
                if gemeldet
                else "Auszahlung (Summe der Posten)"
            ),
            auszahlungs_nr=abrechnung.nummer,
        )
    )


# ---------------------------------------------------------------------------
# Buchen
# ---------------------------------------------------------------------------


@dataclass
class _Lauf:
    abrechnung: Abrechnung
    kontext: Buchungskontext
    konten: Marktplatzkonten
    umsaetze: dict[str, UUID]
    pruefen_alle: bool
    ergebnis: Buchungsergebnis = field(default_factory=Buchungsergebnis)
    gesammelt: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    schwelle_gemeldet: bool = False

    @property
    def markt(self) -> str:
        return ANZEIGE.get(self.abrechnung.marktplatz, self.abrechnung.marktplatz)

    def eur(self, betrag: Decimal) -> Decimal:
        kurs = self.abrechnung.kurs
        if self.abrechnung.waehrung == "EUR" or kurs is None:
            return betrag
        return (betrag / kurs).quantize(CENT, rounding=ROUND_HALF_UP)

    def bucht(
        self,
        betrag: Decimal,
        gegenkonto: str,
        datum: date,
        text: str,
        belegnummer: str | None,
        referenz: str | None = None,
        pruefen: bool = False,
        konto: str | None = None,
        schluessel: int | None = None,
        steuer: Decimal | None = None,
    ) -> None:
        """Positiver Betrag: Konto (Verrechnung) an Gegenkonto, negativ umgekehrt."""
        if not betrag:
            return
        eigenes = konto or self.konten.verrechnungskonto
        soll, haben = (eigenes, gegenkonto) if betrag > 0 else (gegenkonto, eigenes)
        pruefen = pruefen or self.pruefen_alle
        self.ergebnis.buchungen.append(
            Buchungssatz(
                transaktion_id=self.umsaetze.get(referenz or ""),
                beleg_id=self.abrechnung.beleg_id,
                datum=datum,
                soll_konto=soll,
                haben_konto=haben,
                betrag_netto=abs(betrag),
                steuer_schluessel=schluessel,
                steuer_betrag=abs(steuer) if steuer is not None else None,
                buchungstext=text[:60],
                beleg_nummer=(belegnummer or self.abrechnung.nummer)[:36],
                status=BuchungStatus.ZUR_PRUEFUNG
                if pruefen
                else BuchungStatus.AUTO_GEBUCHT,
                confidence=0.5 if pruefen else 1.0,
            )
        )

    def sammle(self, code: str, bestellung: str) -> None:
        self.gesammelt[code].append(bestellung)


def _gruppen(
    posten: list[Marktplatzposten], ermaessigt: set[str]
) -> list[tuple[Marktplatzposten, bool, Decimal]]:
    """Erlöse/Erstattungen je Bestellung, Art, Land und Steuersatz zusammengefasst."""
    summen: dict[tuple[object, ...], tuple[Marktplatzposten, bool, Decimal]] = {}
    for p in posten:
        if p.art not in (Postenart.ERLOES, Postenart.ERSTATTUNG):
            continue
        reduziert = bool(p.artikel and p.artikel in ermaessigt)
        schluessel = (
            p.art,
            p.bestellnummer or f"#{p.nr}",
            p.referenz,
            p.bestimmungsland,
            p.abgangsland,
            p.kaeufer_ust_id,
            reduziert,
        )
        erster, _, summe = summen.get(schluessel, (p, reduziert, NULL))
        if p.datum < erster.datum:
            erster = p
        summen[schluessel] = (erster, reduziert, summe + p.betrag)
    return sorted(summen.values(), key=lambda g: (g[0].datum, g[0].nr))


def _erloes(
    lauf: _Lauf, p: Marktplatzposten, ermaessigt: bool, brutto: Decimal
) -> None:
    """Erlös oder Erstattung (brutto, mit Vorzeichen), Steuer je Bestimmungsland."""
    k = lauf.kontext
    e = k.einstellungen
    art = "Erstattung" if p.art is Postenart.ERSTATTUNG else "Erlös"
    bestellung = p.bestellnummer or f"Zeile {p.nr}"
    land = p.bestimmungsland
    text = f"{lauf.markt} {art} {bestellung} {land or '??'}"
    bucht = lauf.bucht
    if land is None:
        lauf.sammle("land_fehlt", bestellung)
        bucht(
            brutto, e.erloes_unbekannt, p.datum, text, p.bestellnummer, p.referenz, True
        )
        return

    pruefen = False
    if p.abgangsland and p.abgangsland != k.firmen_land:
        lauf.sammle("abgangsland", f"{bestellung} ({p.abgangsland})")
        pruefen = True
    elif (
        not p.abgangsland
        and p.versand_durch_marktplatz
        and not lauf.konten.lager_nur_inland
    ):
        # aus einem Marktplatzlager unbekannten Landes (Pan-EU/CEE?) — nicht raten
        lauf.sammle("abgangsland_fehlt", bestellung)
        pruefen = True
    if p.geschaeftskunde and not p.kaeufer_ust_id and land != k.firmen_land:
        lauf.sammle("geschaeftskunde_ohne_ust_id", f"{bestellung} ({land})")
        pruefen = True
    b2b = bool(p.kaeufer_ust_id)
    berechner = UStBerechner(
        firmen_land=k.firmen_land,
        oss_registriert=k.oss_registriert,
        oss_schwelle_ueberschritten=k.oss_registriert,
    )
    vorfall = berechner.bestimme_vorfall(land, ist_b2b=b2b, kaeufer_hat_ust_id=b2b)

    if vorfall is Geschaeftsvorfall.INLAND:
        info = EU_STEUERSAETZE[k.firmen_land]
        satz = info.ermaessigt if ermaessigt else info.normal
        netto = berechner.brutto_zu_netto(abs(brutto), satz)
        if land != k.firmen_land and ist_eu_land(land):
            # Fernverkauf ohne OSS: Lieferschwelle § 3c Abs. 4 UStG — sie gilt nur,
            # wenn sie im Vorjahr nicht überschritten wurde und im laufenden Jahr
            # nicht überschritten wird; gezählt wird je Posten in seinem Jahr
            jahr = p.datum.year
            bisher = k.eu_b2c_bisher.get(jahr, NULL) + (netto if brutto > 0 else -netto)
            k.eu_b2c_bisher[jahr] = bisher
            if k.eu_b2c_bisher.get(jahr - 1, NULL) > OSS_SCHWELLE_EUR:
                pruefen = True
                lauf.sammle("lieferschwelle", f"{bestellung} (Vorjahr {jahr - 1})")
            elif bisher > OSS_SCHWELLE_EUR:
                pruefen = True
                lauf.sammle("lieferschwelle", f"{bestellung} ({jahr})")
        schluessel = e.bu_inland.get(f"{satz.normalize():f}")
        konto = e.erloes_inland.get(f"{satz.normalize():f}", e.erloes_unbekannt)
        vorzeichen = 1 if brutto > 0 else -1
        bucht(
            vorzeichen * netto,
            konto,
            p.datum,
            text,
            p.bestellnummer,
            p.referenz,
            pruefen or schluessel is None,
            schluessel=schluessel,
            steuer=abs(brutto) - netto,
        )
        return

    if vorfall is Geschaeftsvorfall.EU_B2C_OSS:
        info = EU_STEUERSAETZE[land]
        satz = info.ermaessigt if ermaessigt else info.normal
        netto = berechner.brutto_zu_netto(abs(brutto), satz)
        steuer_konto = berechner.berechne_ust(
            netto, land, ermaessigt=ermaessigt
        ).steuer_konto
        if ermaessigt:
            # die OSS-Meldung kennt den Satz nur über das Erlöskonto
            erloeskonto = e.oss_erloes_ermaessigt.get(land)
            if erloeskonto is None:
                pruefen = True
                erloeskonto = e.erloes_unbekannt
                lauf.sammle("oss_ermaessigt", f"{bestellung} ({land} {satz:f} %)")
        else:
            erloeskonto = OSS_ERLOES_KONTEN_SKR03.get(land)
            if erloeskonto is None:
                pruefen = True
                erloeskonto = e.erloes_unbekannt
                lauf.sammle("oss_konto_fehlt", f"{bestellung} ({land})")
        vorzeichen = 1 if brutto > 0 else -1
        bucht(
            vorzeichen * netto,
            erloeskonto,
            p.datum,
            text,
            p.bestellnummer,
            p.referenz,
            pruefen,
        )
        bucht(
            vorzeichen * (abs(brutto) - netto),
            steuer_konto,
            p.datum,
            f"{lauf.markt} USt {land} {satz.normalize():f} % {bestellung}",
            p.bestellnummer,
            p.referenz,
            pruefen,
        )
        return

    if vorfall in (
        Geschaeftsvorfall.EU_INNERGEMEINSCHAFTLICH,
        Geschaeftsvorfall.EU_B2B_REVERSE_CHARGE,
    ):
        lauf.sammle("ig_lieferung", f"{bestellung} ({p.kaeufer_ust_id})")
        bucht(
            brutto,
            e.erloes_ig_lieferung,
            p.datum,
            text,
            p.bestellnummer,
            p.referenz,
            True,
        )
        return

    # Drittland: steuerfreie Ausfuhr nur mit Ausfuhrnachweis (§ 6 UStG)
    lauf.sammle("ausfuhr", f"{bestellung} ({land})")
    bucht(brutto, e.erloes_ausfuhr, p.datum, text, p.bestellnummer, p.referenz, True)


def _kosten(
    lauf: _Lauf,
    betrag: Decimal,
    konto: str,
    datum: date,
    text: str,
    belegnummer: str | None,
    referenz: str | None,
    modus: str | None,
    bu_13b: int | None,
    was: str,
) -> None:
    """Gebühr oder Werbung (Vorzeichen aus Sicht des Guthabens) mit ihrer Steuer.

    ``vorsteuer``: der Betrag im Bericht ist brutto mit der USt des Firmensitzlands —
    Vorsteuer über den BU-Schlüssel (Beleg: die monatliche Gebührenrechnung);
    ``13b``: Nettobetrag mit dem eingestellten BU-Schlüssel; ``ohne``: steuerfrei.
    Ohne Einstellung wird ohne Vorsteuer gebucht, aber zur Prüfung, mit Befund.
    """
    k = lauf.kontext
    if modus == "vorsteuer":
        satz = EU_STEUERSAETZE[k.firmen_land].normal
        netto = UStBerechner(firmen_land=k.firmen_land).brutto_zu_netto(
            abs(betrag), satz
        )
        schluessel = DATEV_BU_SCHLUESSEL.get(f"vst_{int(satz)}")
        if schluessel is None:
            lauf.sammle("ust_gebuehren_offen", was)
        lauf.bucht(
            netto if betrag > 0 else -netto,
            konto,
            datum,
            text,
            belegnummer,
            referenz,
            schluessel is None,
            schluessel=schluessel,
            steuer=abs(betrag) - netto,
        )
        return
    if modus == "ohne" or (modus == "13b" and bu_13b is not None):
        lauf.bucht(betrag, konto, datum, text, belegnummer, referenz, schluessel=bu_13b)
        return
    lauf.sammle("ust_gebuehren_offen", was)
    lauf.bucht(betrag, konto, datum, text, belegnummer, referenz, True)


_BEFUNDTEXTE: dict[str, tuple[Schweregrad, str]] = {
    "land_fehlt": (
        Schweregrad.WARNUNG,
        "ohne Bestimmungsland — Erlös auf Klärungskonto zur Prüfung "
        "(Länderdatei mit --laender mitgeben)",
    ),
    "abgangsland": (
        Schweregrad.WARNUNG,
        "aus einem Lager im Ausland versandt — Steuerpflicht im Abgangsland prüfen",
    ),
    "abgangsland_fehlt": (
        Schweregrad.WARNUNG,
        "aus einem Lager des Marktplatzes ohne bekanntes Abgangsland — liegt die "
        "Ware in einem Lager im Ausland (Pan-EU, CEE), ist der Verkauf dort "
        "steuerbar; USt-Transaktionsbericht als Länderdatei nehmen oder "
        "marktplaetze.<name>.lager_nur_inland einstellen",
    ),
    "geschaeftskunde_ohne_ust_id": (
        Schweregrad.WARNUNG,
        "als Unternehmer bestellt, aber ohne USt-IdNr. in der Länderdatei — "
        "ig. Lieferung oder Fernverkauf? USt-IdNr. klären",
    ),
    "lieferschwelle": (
        Schweregrad.FEHLER,
        "nach Überschreiten der Lieferschwelle von 10.000 € im Vorjahr oder im "
        "laufenden Jahr (§ 3c Abs. 4 UStG) — steuerbar im Bestimmungsland, "
        "OSS-Registrierung prüfen",
    ),
    "oss_ermaessigt": (
        Schweregrad.WARNUNG,
        "mit ermäßigtem OSS-Satz ohne Erlöskonto dafür "
        "(integrationen.oss_erloes_ermaessigt) — Erlös auf dem Klärungskonto, "
        "nicht in der OSS-Meldung; Konto einstellen und umbuchen",
    ),
    "oss_konto_fehlt": (
        Schweregrad.WARNUNG,
        "ohne OSS-Erlöskonto in accounti.steuer — nicht in der OSS-Meldung; "
        "Konto anlegen und zuordnen",
    ),
    "ig_lieferung": (
        Schweregrad.WARNUNG,
        "an Unternehmer mit USt-IdNr. (ig. Lieferung) — USt-IdNr. bestätigen lassen",
    ),
    "ausfuhr": (
        Schweregrad.WARNUNG,
        "ins Drittland — steuerfrei nur mit Ausfuhrnachweis (§ 6 UStG)",
    ),
}


def buche_abrechnung(
    abrechnung: Abrechnung,
    kontext: Buchungskontext,
    umsaetze: dict[str, UUID] | None = None,
) -> Buchungsergebnis:
    """Bucht alle Bestandteile; ``umsaetze``: PayPal-Transaktionscode → Umsatz-ID."""
    e = kontext.einstellungen
    konten = e.marktplatz(abrechnung.marktplatz)
    befunde = summenprobe(abrechnung)
    if abrechnung.waehrung != "EUR" and abrechnung.kurs is None:
        return Buchungsergebnis(
            befunde=[
                Befund(
                    code="fremdwaehrung_ohne_kurs",
                    schweregrad=Schweregrad.FEHLER,
                    text=(
                        f"Abrechnung in {abrechnung.waehrung} — ohne Kurs (--kurs, "
                        "Einheiten je 1 EUR) wird nichts gebucht"
                    ),
                )
            ]
        )
    fehler = any(
        b.schweregrad is Schweregrad.FEHLER for b in [*abrechnung.befunde, *befunde]
    )
    lauf = _Lauf(abrechnung, kontext, konten, umsaetze or {}, pruefen_alle=fehler)
    lauf.ergebnis.befunde.extend(befunde)

    for p, ermaessigt, brutto in _gruppen(
        abrechnung.posten, set(e.ermaessigte_artikel)
    ):
        _erloes(lauf, p, ermaessigt, lauf.eur(brutto))

    gebuehren: dict[tuple[str, str | None, bool], tuple[Marktplatzposten, Decimal]] = {}
    for p in abrechnung.posten:
        if p.art is Postenart.GEBUEHR:
            art = p.gebuehrenart.value if p.gebuehrenart else "sonstige"
            schluessel = (art, p.referenz, p.betrag > 0)
            erster, summe = gebuehren.get(schluessel, (p, NULL))
            gebuehren[schluessel] = (erster, summe + lauf.eur(p.betrag))
    for (art, referenz, erstattet), (p, summe) in gebuehren.items():
        datum = p.datum if referenz else abrechnung.bis
        text = f"{lauf.markt} {'Gebührenerstattung' if erstattet else 'Gebühren'} {art}"
        _kosten(
            lauf,
            summe,
            konten.konto_fuer_gebuehr(art),
            datum,
            f"{text} {abrechnung.nummer if not referenz else p.bestellnummer or ''}",
            p.bestellnummer if referenz else None,
            referenz,
            konten.ust_gebuehren,
            konten.bu_gebuehren,
            "Gebühren",
        )

    transit = e.geldtransit_konto
    for p in abrechnung.posten:
        betrag = lauf.eur(p.betrag)
        if p.art is Postenart.WERBUNG:
            _kosten(
                lauf,
                betrag,
                konten.werbung,
                p.datum,
                f"{lauf.markt} Werbung",
                None,
                p.referenz,
                konten.ust_werbung,
                konten.bu_werbung,
                "Werbung",
            )
        elif p.art is Postenart.EINBEHALT:
            text = f"{lauf.markt} {'Einbehalt' if betrag < 0 else 'Einbehalt frei'}"
            lauf.bucht(
                betrag,
                konten.einbehalt_konto,
                p.datum,
                text,
                p.bestellnummer,
                p.referenz,
            )
        elif p.art is Postenart.ERSATZ:
            lauf.sammle("ersatz", p.beschreibung)
            lauf.bucht(
                betrag,
                konten.ersatzleistung,
                p.datum,
                f"{lauf.markt} Ersatzleistung {p.artikel or ''}",
                p.bestellnummer,
                p.referenz,
                True,
            )
        elif p.art is Postenart.SONSTIGES:
            lauf.bucht(
                betrag,
                konten.klaerung,
                p.datum,
                f"{lauf.markt} Klärung: {p.beschreibung}",
                p.bestellnummer,
                p.referenz,
                True,
            )
        elif p.art in (Postenart.AUSZAHLUNG, Postenart.EINZAHLUNG):
            if abrechnung.marktplatz == "paypal":
                text = f"PayPal {'Abbuchung' if betrag < 0 else 'Einzahlung'} Bank"
                lauf.bucht(betrag, transit, p.datum, text, None, p.referenz)
            elif abrechnung.waehrung != "EUR":
                p.betrag_eur = -sum(
                    (
                        lauf.eur(q.betrag)
                        for q in abrechnung.posten
                        if q.art not in _NICHT_EINZELPOSTEN
                    ),
                    NULL,
                )

    texte = dict(_BEFUNDTEXTE)
    texte["ersatz"] = (
        Schweregrad.WARNUNG,
        "Ersatzleistung des Marktplatzes — steuerliche Behandlung prüfen",
    )
    for code, faelle in lauf.gesammelt.items():
        if code == "ust_gebuehren_offen":
            arten = " und ".join(dict.fromkeys(faelle))
            name = abrechnung.marktplatz
            lauf.ergebnis.befunde.append(
                Befund(
                    code=code,
                    schweregrad=Schweregrad.WARNUNG,
                    text=(
                        f"Umsatzsteuer der {arten} ist nicht eingestellt "
                        f"(integrationen.marktplaetze.{name}.ust_gebuehren bzw. "
                        "ust_werbung: vorsteuer, 13b mit bu_gebuehren/bu_werbung "
                        "oder ohne) — ohne Vorsteuer gebucht, zur Prüfung"
                    ),
                )
            )
            continue
        schwere, text = texte[code]
        beispiele = ", ".join(faelle[:5]) + (" …" if len(faelle) > 5 else "")
        lauf.ergebnis.befunde.append(
            Befund(
                code=code,
                schweregrad=schwere,
                text=f"{len(faelle)} Posten {text}: {beispiele}",
            )
        )
    return lauf.ergebnis
