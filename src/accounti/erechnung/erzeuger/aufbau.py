"""Ausgangsrechnung → Zwischenmodell.

Die Steuer kommt vollständig aus `steuer/umsatzsteuer.py`: Der `UStBerechner` bestimmt
je Position Geschäftsvorfall und Satz und rechnet die Steuer je Kategorie und Satz auf
die Summe. Hier wird nur noch auf die Steuerkategorien der EN 16931 abgebildet.
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
from accounti.models import Ausgangsrechnung
from accounti.steuer.umsatzsteuer import Geschaeftsvorfall, UStBerechner, UStPosition

XRECHNUNG_3 = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
PEPPOL_PROZESS = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
SEPA_UEBERWEISUNG = "58"
NULL = Decimal("0")


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


def _pruefe_kunde(entwurf: Ausgangsrechnung) -> None:
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
    if not entwurf.positionen:
        fehlt.append("mindestens eine Position")
    if fehlt:
        msg = "Für die XRechnung fehlt: " + ", ".join(fehlt)
        raise ValueError(msg)


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


def baue_rechnung(
    entwurf: Ausgangsrechnung,
    firma: Firma,
    nummer: str,
    rechnungsdatum: date,
) -> Rechnung:
    """Erzeugt das Zwischenmodell einer XRechnung aus Entwurf und Firmendaten."""
    _pruefe_kunde(entwurf)
    k = entwurf.kunde
    land = k.land.upper()
    berechner = UStBerechner(
        firmen_land=firma.anschrift.land,
        oss_registriert=firma.oss,
        oss_schwelle_ueberschritten=firma.oss,
    )
    ist_b2b = not k.privat
    hat_ust_id = bool(k.ust_id)

    def ust(netto: Decimal, ermaessigt: bool, leistung: bool) -> UStPosition:
        return berechner.berechne_ust(
            netto,
            bestimmungsland=land,
            ist_b2b=ist_b2b,
            kaeufer_hat_ust_id=hat_ust_id,
            ermaessigt=ermaessigt,
            ist_sonstige_leistung=leistung,
        )

    zeilen: list[Rechnungszeile] = []
    gruppen: dict[tuple[str, Decimal], list[tuple[Decimal, bool, bool]]] = defaultdict(
        list
    )
    vorfaelle: dict[tuple[str, Decimal], Geschaeftsvorfall] = {}
    for nr, p in enumerate(entwurf.positionen, start=1):
        u = ust(p.netto, p.ermaessigt, p.sonstige_leistung)
        if u.geschaeftsvorfall is Geschaeftsvorfall.DRITTLAND_AUSFUHR and (
            p.sonstige_leistung
        ):
            msg = (
                f"Position {nr}: Dienstleistung an einen Kunden im Drittland "
                "(nicht im Inland steuerbar, Kategorie O) wird noch nicht unterstützt"
            )
            raise NichtUnterstuetztError(msg)
        if u.geschaeftsvorfall not in _KATEGORIE:
            vorfall = u.geschaeftsvorfall.value
            msg = f"Position {nr}: Geschäftsvorfall {vorfall} nicht unterstützt"
            raise NichtUnterstuetztError(msg)
        kategorie = _KATEGORIE[u.geschaeftsvorfall][0]
        schluessel = (kategorie, u.steuersatz.normalize())
        gruppen[schluessel].append((p.netto, p.ermaessigt, p.sonstige_leistung))
        vorfaelle[schluessel] = u.geschaeftsvorfall
        zeilen.append(
            Rechnungszeile(
                id=str(nr),
                bezeichnung=p.bezeichnung,
                menge=p.menge,
                einheit=p.einheit,
                einzelpreis=p.einzelpreis,
                netto=p.netto,
                steuerkategorie=kategorie,
                steuersatz=u.steuersatz.normalize(),
            )
        )

    steuern: list[Steueraufschluesselung] = []
    hinweise: list[str] = []
    for (kategorie, satz), posten in gruppen.items():
        basis = sum((netto for netto, _, _ in posten), NULL)
        _, ermaessigt, leistung = posten[0]
        # Steuer je Kategorie und Satz auf die Summe — gerechnet von steuer/.
        betrag = ust(basis, ermaessigt, leistung).steuerbetrag
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
    faellig = rechnungsdatum + timedelta(days=firma.zahlungsziel_tage)
    bedingungen = (
        f"Zahlbar bis {faellig:%d.%m.%Y} ohne Abzug."
        if firma.zahlungsziel_tage
        else "Zahlbar sofort ohne Abzug."
    )
    if entwurf.skonto_prozent is not None and entwurf.skonto_tage is not None:
        bedingungen += (
            f"\n#SKONTO#TAGE={entwurf.skonto_tage}"
            f"#PROZENT={entwurf.skonto_prozent:.2f}#"
        )
    notizen = [n for n in (entwurf.notiz, *hinweise) if n]

    return Rechnung(
        syntax="CII",
        spezifikation=XRECHNUNG_3,
        nummer=nummer,
        datum=rechnungsdatum,
        typ="380",
        waehrung="EUR",
        faellig=faellig,
        # BT-10 ist in der XRechnung Pflicht; ohne Leitweg-ID dient die Bestellnummer.
        kaeufer_referenz=k.leitweg_id or entwurf.bestellnummer or "n/a",
        bestellnummer=entwurf.bestellnummer,
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
            brutto=netto + steuer,
            zahlbetrag=netto + steuer,
        ),
    )
