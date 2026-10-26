"""Ausgangsrechnung → Zwischenmodell.

Die Steuer kommt vollständig aus `steuer/umsatzsteuer.py`: Der `UStBerechner` bestimmt
je Position Geschäftsvorfall und Satz und rechnet die Steuer je Kategorie und Satz auf
die Summe. Hier wird nur noch auf die Steuerkategorien der EN 16931 abgebildet.

Spezifikation: XRechnung, sobald die Pflichtangaben des Käufers da sind. An
Privatkunden besteht keine E-Rechnungspflicht (§ 14 Abs. 2 Satz 2 Nr. 1 UStG) — fehlen
dort E-Mail, PLZ oder Ort, wird die Rechnung nach EN 16931 ohne die XRechnung-CIUS
erzeugt (ZUGFeRD-Profil EN 16931). Über 250 € braucht sie die Anschrift des Empfängers
(§ 14 Abs. 4 Satz 1 Nr. 1 UStG), bis 250 € genügt eine Kleinbetragsrechnung ohne
Empfängerangaben (§ 33 UStDV).

Gutschrift (381) und Rechnungskorrektur (384) verweisen auf die ursprüngliche Rechnung
(BT-25/26). Die Gutschrift weist die Minderung positiv aus; die Korrektur die Differenz
mit Vorzeichen (negative Menge, nie ein negativer Einzelpreis — BR-27).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from accounti.erechnung.modell import (
    Anschrift,
    Partei,
    Rechnung,
    Rechnungszeile,
    Steueraufschluesselung,
    Summen,
)
from accounti.konfiguration import Firma
from accounti.models import (
    GUTSCHRIFT,
    AusgangsPosition,
    Ausgangsrechnung,
    Rechnungsempfaenger,
)
from accounti.steuer.umsatzsteuer import Geschaeftsvorfall, UStBerechner, UStPosition

XRECHNUNG_3 = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
EN16931 = "urn:cen.eu:en16931:2017"
PEPPOL_PROZESS = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
SEPA_UEBERWEISUNG = "58"
NULL = Decimal("0")
CENT = Decimal("0.01")
KLEINBETRAG = Decimal("250")  # § 33 UStDV
# § 286 Abs. 3 Satz 1 Halbsatz 2 BGB: gegenüber Verbrauchern nur mit diesem Hinweis
HINWEIS_VERZUG = (
    "Hinweis nach § 286 Abs. 3 BGB: Sie kommen ohne weitere Mahnung in Verzug, wenn "
    "Sie nicht innerhalb von 30 Tagen nach Fälligkeit und Zugang dieser Rechnung "
    "zahlen."
)
VERRECHNUNG = "Der Betrag wird mit offenen Rechnungen verrechnet oder erstattet."


class NichtUnterstuetztError(ValueError):
    """Der Steuerfall lässt sich (noch) nicht als E-Rechnung ausstellen."""


# Geschäftsvorfall → (Kategorie, Befreiungscode, Befreiungsgrund, Rechnungshinweis)
_KATEGORIE: dict[Geschaeftsvorfall, tuple[str, str | None, str | None, str | None]] = {
    Geschaeftsvorfall.INLAND: ("S", None, None, None),
    Geschaeftsvorfall.EU_B2C_OSS: ("S", None, None, None),
    Geschaeftsvorfall.EU_B2B_REVERSE_CHARGE: (
        "AE",
        "VATEX-EU-AE",
        "Steuerschuldnerschaft des Leistungsempfängers",
        "Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge, "
        "§ 13b UStG / Art. 196 MwStSystRL).",
    ),
    Geschaeftsvorfall.EU_INNERGEMEINSCHAFTLICH: (
        "K",
        "VATEX-EU-IC",
        "Steuerfreie innergemeinschaftliche Lieferung",
        "Steuerfreie innergemeinschaftliche Lieferung (§ 4 Nr. 1b UStG).",
    ),
    Geschaeftsvorfall.DRITTLAND_AUSFUHR: (
        "G",
        "VATEX-EU-G",
        "Steuerfreie Ausfuhrlieferung",
        "Steuerfreie Ausfuhrlieferung (§ 4 Nr. 1a UStG).",
    ),
}


def _pruefe_entwurf(entwurf: Ausgangsrechnung) -> None:
    if not entwurf.positionen:
        msg = "Für die Rechnung fehlt: mindestens eine Position"
        raise ValueError(msg)
    prozent, tage = entwurf.skonto_prozent, entwurf.skonto_tage
    if (prozent is None) != (tage is None):
        msg = "Skonto: Prozent und Tage nur zusammen angeben"
        raise ValueError(msg)
    if prozent is not None and not NULL < prozent < 100:
        msg = (
            f"Skonto: {prozent} % — der Satz muss größer als 0 und kleiner als 100 sein"
        )
        raise ValueError(msg)
    if tage is not None and tage < 0:
        msg = "Skonto: die Frist in Tagen darf nicht negativ sein"
        raise ValueError(msg)
    if prozent is not None and entwurf.ist_korrektur:
        msg = "Skonto gibt es nicht auf einer Gutschrift oder Rechnungskorrektur"
        raise ValueError(msg)


def fehlende_anschrift(k: Rechnungsempfaenger, brutto: Decimal) -> list[str]:
    """Was über 250 € an der Anschrift des Empfängers fehlt (§ 14 Abs. 4 Satz 1 Nr. 1
    UStG) — Straße oder Postfach (Abschn. 14.5 Abs. 2 UStAE), PLZ und Ort; bis 250 €
    genügt die Kleinbetragsrechnung ohne Empfänger (§ 33 UStDV)."""
    if abs(brutto) <= KLEINBETRAG:
        return []
    return [
        bezeichnung
        for wert, bezeichnung in (
            (k.strasse, "Straße oder Postfach des Kunden"),
            (k.plz, "PLZ des Kunden"),
            (k.ort, "Ort des Kunden"),
        )
        if not (wert or "").strip()
    ]


def _pruefe_anschrift(k: Rechnungsempfaenger, brutto: Decimal) -> None:
    if fehlt := fehlende_anschrift(k, brutto):
        msg = (
            "Für die Rechnung über 250 € fehlt die Anschrift des Empfängers (§ 14 "
            "Abs. 4 Satz 1 Nr. 1 UStG): " + ", ".join(fehlt) + " — bis 250 € "
            "genügt eine Kleinbetragsrechnung (§ 33 UStDV)"
        )
        raise ValueError(msg)


def _spezifikation(entwurf: Ausgangsrechnung) -> str:
    """XRechnung, wenn die Pflichtangaben des Käufers da sind — sonst bei
    Privatkunden EN 16931 (keine E-Rechnungspflicht im B2C)."""
    k = entwurf.kunde
    fehlt = [
        bezeichnung
        for wert, bezeichnung in (
            (k.email, "E-Mail des Kunden (elektronische Adresse, BT-49)"),
            (k.ort, "Ort des Kunden"),
            (k.plz, "PLZ des Kunden"),
        )
        if not wert
    ]
    if not fehlt:
        return XRECHNUNG_3
    if not k.privat:
        msg = "Für die XRechnung fehlt: " + ", ".join(fehlt)
        raise ValueError(msg)
    return EN16931


def _verkaeufer(firma: Firma) -> Partei:
    a = firma.anschrift
    return Partei(
        name=firma.name,
        ust_id=firma.ust_id,
        steuernummer=firma.steuernummer,
        anschrift=Anschrift(strasse=a.strasse, plz=a.plz, ort=a.ort, land=a.land),
        email=firma.email,
        kontakt_name=firma.kontakt.name,
        kontakt_telefon=firma.kontakt.telefon,
        kontakt_email=firma.kontakt.email,
    )


def _berechner(firma: Firma) -> UStBerechner:
    return UStBerechner(
        firmen_land=firma.anschrift.land,
        oss_registriert=firma.oss,
        oss_schwelle_ueberschritten=firma.oss,
    )


def ustid_pflichtig(entwurf: Ausgangsrechnung, firma: Firma) -> bool:
    """Wird die Rechnung steuerfrei (K) oder mit Reverse Charge (AE) — braucht sie
    also eine bestätigte USt-IdNr. des Kunden?"""
    k = entwurf.kunde
    if k.privat or not k.ust_id:
        return False
    berechner = _berechner(firma)
    return any(
        berechner.bestimme_vorfall(
            k.land.upper(),
            ist_b2b=True,
            kaeufer_hat_ust_id=True,
            ist_sonstige_leistung=p.sonstige_leistung,
            ist_elektronisch=p.elektronisch,
        )
        in (
            Geschaeftsvorfall.EU_INNERGEMEINSCHAFTLICH,
            Geschaeftsvorfall.EU_B2B_REVERSE_CHARGE,
        )
        for p in entwurf.positionen
    )


def _nicht_steuerbar(nr: int, p: AusgangsPosition, privat: bool) -> str:
    if privat:
        return (
            f"Position {nr}: elektronische Leistung an einen Privatkunden im "
            "Drittland (§ 3a Abs. 5 Satz 1 UStG, nicht im Inland steuerbar, "
            "Kategorie O) wird noch nicht unterstützt"
        )
    return (
        f"Position {nr}: Dienstleistung an einen Kunden im Drittland (§ 3a Abs. 2 "
        "UStG, nicht im Inland steuerbar, Kategorie O) wird noch nicht unterstützt"
    )


def baue_rechnung(
    entwurf: Ausgangsrechnung,
    firma: Firma,
    nummer: str,
    rechnungsdatum: date,
    *,
    vorgaenger_datum: date | None = None,
    hinweis_verzug: bool = False,
    anschrift_pruefen: bool = True,
) -> Rechnung:
    """Erzeugt das Zwischenmodell einer E-Rechnung aus Entwurf und Firmendaten.

    ``vorgaenger_datum``: Datum der Rechnung, auf die sich eine Gutschrift oder
    Korrektur bezieht (BT-26). ``hinweis_verzug``: bei Privatkunden den Hinweis nach
    § 286 Abs. 3 BGB aufdrucken (``mahnwesen.hinweis_30_tage``).
    ``anschrift_pruefen``: über 250 € die vollständige Anschrift verlangen — beim
    Ausstellen; die Anzeige (``rechnung zeigen``) schaltet das ab, denn vor dieser
    Prüfung ausgestellte Rechnungen ohne Straße müssen sich weiter zeigen lassen
    (``fehlende_anschrift`` liefert dann den Hinweis).
    """
    _pruefe_entwurf(entwurf)
    k = entwurf.kunde
    land = k.land.upper()
    berechner = _berechner(firma)
    ist_b2b = not k.privat
    hat_ust_id = bool(k.ust_id)

    def ust(netto: Decimal, p: AusgangsPosition) -> UStPosition:
        return berechner.berechne_ust(
            netto,
            bestimmungsland=land,
            ist_b2b=ist_b2b,
            kaeufer_hat_ust_id=hat_ust_id,
            ermaessigt=p.ermaessigt,
            ist_sonstige_leistung=p.sonstige_leistung,
            ist_elektronisch=p.elektronisch,
        )

    # Eine Gutschrift weist die Minderung positiv aus: als negative Menge erfasst,
    # wird sie umgedreht (dieselbe Bedeutung)
    umkehren = entwurf.rechnungstyp == GUTSCHRIFT and (
        sum((p.netto for p in entwurf.positionen), NULL) < 0
    )
    zeilen: list[Rechnungszeile] = []
    gruppen: dict[tuple[str, Decimal], list[tuple[Decimal, AusgangsPosition]]] = (
        defaultdict(list)
    )
    vorfaelle: dict[tuple[str, Decimal], Geschaeftsvorfall] = {}
    for nr, p in enumerate(entwurf.positionen, start=1):
        menge, preis = p.menge, p.einzelpreis
        if (
            preis < 0
        ):  # BR-27: nie ein negativer Einzelpreis — die Menge trägt das Minus
            menge, preis = -menge, -preis
        if umkehren:
            menge = -menge
        netto = (menge * preis).quantize(CENT)
        u = ust(netto, p)
        if u.geschaeftsvorfall is Geschaeftsvorfall.NICHT_STEUERBAR:
            raise NichtUnterstuetztError(_nicht_steuerbar(nr, p, k.privat))
        if u.geschaeftsvorfall not in _KATEGORIE:
            vorfall = u.geschaeftsvorfall.value
            msg = f"Position {nr}: Geschäftsvorfall {vorfall} nicht unterstützt"
            raise NichtUnterstuetztError(msg)
        kategorie = _KATEGORIE[u.geschaeftsvorfall][0]
        schluessel = (kategorie, u.steuersatz.normalize())
        gruppen[schluessel].append((netto, p))
        vorfaelle[schluessel] = u.geschaeftsvorfall
        zeilen.append(
            Rechnungszeile(
                id=str(nr),
                bezeichnung=p.bezeichnung,
                menge=menge,
                einheit=p.einheit,
                einzelpreis=preis,
                netto=netto,
                steuerkategorie=kategorie,
                steuersatz=u.steuersatz.normalize(),
            )
        )

    steuern: list[Steueraufschluesselung] = []
    hinweise: list[str] = []
    for (kategorie, satz), posten in gruppen.items():
        basis = sum((netto for netto, _ in posten), NULL)
        # Steuer je Kategorie und Satz auf die Summe — gerechnet von steuer/.
        betrag = ust(basis, posten[0][1]).steuerbetrag
        _, code, grund, hinweis = _KATEGORIE[vorfaelle[(kategorie, satz)]]
        steuern.append(
            Steueraufschluesselung(
                kategorie=kategorie,
                satz=satz,
                basis=basis,
                betrag=betrag,
                befreiungsgrund=grund,
                befreiungsgrund_code=code,
            )
        )
        if hinweis and hinweis not in hinweise:
            hinweise.append(hinweis)

    netto = sum((z.netto or NULL for z in zeilen), NULL)
    steuer = sum((s.betrag or NULL for s in steuern), NULL)
    brutto = netto + steuer
    if anschrift_pruefen:
        _pruefe_anschrift(k, brutto)
    spezifikation = _spezifikation(entwurf)
    faellig = rechnungsdatum + timedelta(days=firma.zahlungsziel_tage)
    if entwurf.rechnungstyp == GUTSCHRIFT or brutto < 0:
        bedingungen = VERRECHNUNG
    elif firma.zahlungsziel_tage:
        bedingungen = f"Zahlbar bis {faellig:%d.%m.%Y} ohne Abzug."
    else:
        bedingungen = "Zahlbar sofort ohne Abzug."
    if entwurf.skonto_prozent is not None and entwurf.skonto_tage is not None:
        bedingungen += (
            f"\n#SKONTO#TAGE={entwurf.skonto_tage}"
            f"#PROZENT={entwurf.skonto_prozent:.2f}#"
        )
    notizen = [n for n in (entwurf.notiz, *hinweise) if n]
    if hinweis_verzug and k.privat and brutto > 0 and not entwurf.ist_korrektur:
        notizen.append(HINWEIS_VERZUG)

    return Rechnung(
        syntax="CII",
        spezifikation=spezifikation,
        nummer=nummer,
        datum=rechnungsdatum,
        typ=entwurf.rechnungstyp,
        waehrung="EUR",
        faellig=faellig,
        # BT-10 ist in der XRechnung Pflicht; ohne Leitweg-ID dient die Bestellnummer.
        kaeufer_referenz=k.leitweg_id or entwurf.bestellnummer or "n/a",
        bestellnummer=entwurf.bestellnummer,
        vorgaenger_nummer=entwurf.korrektur_zu,
        vorgaenger_datum=vorgaenger_datum if entwurf.korrektur_zu else None,
        notizen=notizen,
        leistungsdatum=entwurf.leistungsdatum or rechnungsdatum,
        # Innergemeinschaftliche Lieferung: Lieferanschrift ist Pflicht (BR-IC-12).
        lieferanschrift=(
            Anschrift(strasse=k.strasse, plz=k.plz, ort=k.ort, land=land)
            if any(s.kategorie == "K" for s in steuern)
            else None
        ),
        verkaeufer=_verkaeufer(firma),
        kaeufer=Partei(
            name=k.name,
            ust_id=k.ust_id,
            anschrift=Anschrift(strasse=k.strasse, plz=k.plz, ort=k.ort, land=land),
            email=k.email,
        ),
        zahlungsart=SEPA_UEBERWEISUNG,
        iban=firma.iban,
        zahlungsbedingungen=bedingungen,
        zeilen=zeilen,
        steuern=steuern,
        summen=Summen(
            positionen_netto=netto,
            netto=netto,
            steuer=steuer,
            brutto=brutto,
            zahlbetrag=brutto,
        ),
    )
