"""Fachliche Validierung einer E-Rechnung.

Geprüft wird eine Auswahl der Geschäftsregeln aus EN 16931 (Pflichtangaben,
Rechenregeln, Steuerkategorien), die XRechnung-Regeln BR-DE-3/4/15 sowie § 14 UStG
und die Plausibilität des Steuersatzes zum Land des Verkäufers. Die formale Prüfung
gegen XSD und Schematron (KoSIT-Prüftool) gehört zum Ausgang (Paket 2).

Ergebnis ist eine Liste von Befunden: Fehler schicken den Beleg in die Prüfung,
Warnungen werden am Beleg vermerkt.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from accounti.erechnung.modell import Profil, Rechnung
from accounti.steuer.eu_steuersaetze import EU_STEUERSAETZE

CENT = Decimal("0.01")
NULL = Decimal("0")

# Kategorien ohne Steuer: Reverse-Charge, befreit, Nullsatz, ig. Lieferung, Export,
# nicht steuerbar
_STEUERFREI = {"AE", "E", "Z", "K", "G", "O"}
# Kategorien, die einen Befreiungsgrund (BT-120) verlangen
_MIT_BEFREIUNGSGRUND = {"AE", "E", "K", "G", "O"}
# Kategorien, bei denen Verkäufer und Käufer eine USt-IdNr. tragen müssen
_BEIDE_UST_ID = {"AE": "BR-AE-02", "K": "BR-IC-02"}


class Schwere(str, enum.Enum):
    FEHLER = "fehler"
    WARNUNG = "warnung"


@dataclass(frozen=True)
class Befund:
    regel: str
    schwere: Schwere
    text: str

    def __str__(self) -> str:
        return f"{self.regel}: {self.text}"


def _rund(wert: Decimal) -> Decimal:
    return wert.quantize(CENT, rounding=ROUND_HALF_UP)


def _summe(werte: Iterable[Decimal | None]) -> Decimal:
    return sum((w for w in werte if w is not None), NULL)


def _satz(wert: Decimal | None) -> Decimal | None:
    return wert.normalize() if wert is not None else None


def _gleiche_steuer(
    kategorie: str | None, satz: Decimal | None, soll_kat: str, soll_satz: Decimal
) -> bool:
    # Ohne Satz (z.B. Kategorie O) zählt wie 0 %.
    return kategorie == soll_kat and _satz(satz or NULL) == _satz(soll_satz)


class _Pruefung:
    def __init__(self, r: Rechnung) -> None:
        self.r = r
        self.befunde: list[Befund] = []

    def fehler(self, regel: str, text: str) -> None:
        self.befunde.append(Befund(regel, Schwere.FEHLER, text))

    def warnung(self, regel: str, text: str) -> None:
        self.befunde.append(Befund(regel, Schwere.WARNUNG, text))

    def pflicht(self, regel: str, wert: object, bezeichnung: str) -> None:
        if wert in (None, "", []):
            self.fehler(regel, f"{bezeichnung} fehlt")

    def gleich(self, regel: str, ist: Decimal | None, soll: Decimal, text: str) -> None:
        if ist is not None and abs(ist - soll) > CENT / 2:
            self.fehler(regel, f"{text}: ausgewiesen {ist:.2f}, berechnet {soll:.2f}")

    # -- Regeln -------------------------------------------------------------

    def kopf(self) -> None:
        r = self.r
        self.pflicht("BR-01", r.spezifikation, "Spezifikationskennung (BT-24)")
        self.pflicht("BR-02", r.nummer, "Rechnungsnummer (BT-1)")
        self.pflicht("BR-03", r.datum, "Rechnungsdatum (BT-2)")
        self.pflicht("BR-04", r.typ, "Rechnungstyp (BT-3)")
        self.pflicht("BR-05", r.waehrung, "Währung (BT-5)")
        self.pflicht("BR-06", r.verkaeufer.name, "Name des Verkäufers (BT-27)")
        self.pflicht("BR-07", r.kaeufer.name, "Name des Käufers (BT-44)")
        self.pflicht(
            "BR-09", r.verkaeufer.anschrift.land, "Land des Verkäufers (BT-40)"
        )
        self.pflicht("BR-13", r.summen.netto, "Nettosumme (BT-109)")
        self.pflicht("BR-14", r.summen.brutto, "Bruttosumme (BT-112)")
        self.pflicht("BR-15", r.summen.zahlbetrag, "Zahlbetrag (BT-115)")

        if r.profil.reduziert:
            self.warnung(
                "PROFIL",
                f"Profil {r.profil.value.upper()} enthält keine Positionen und gilt "
                "nicht als E-Rechnung nach § 14 UStG",
            )
            return
        if r.profil is Profil.UNBEKANNT:
            self.warnung("PROFIL", f"Unbekannte Spezifikation {r.spezifikation!r}")
        if r.profil is Profil.XRECHNUNG:
            self.pflicht(
                "BR-DE-15", r.kaeufer_referenz, "Leitweg-ID/Käuferreferenz (BT-10)"
            )
            self.pflicht(
                "BR-DE-3", r.verkaeufer.anschrift.ort, "Ort des Verkäufers (BT-37)"
            )
            self.pflicht(
                "BR-DE-4", r.verkaeufer.anschrift.plz, "PLZ des Verkäufers (BT-38)"
            )
            if r.lieferanschrift is not None:
                lieferung = r.lieferanschrift
                self.pflicht(
                    "BR-DE-10", lieferung.ort, "Ort der Lieferanschrift (BT-77)"
                )
                self.pflicht(
                    "BR-DE-11", lieferung.plz, "PLZ der Lieferanschrift (BT-78)"
                )
        self.pflicht("BR-10", r.kaeufer.anschrift.land, "Land des Käufers (BT-55)")
        self.pflicht(
            "BR-12", r.summen.positionen_netto, "Summe der Positionen (BT-106)"
        )
        self.pflicht("BR-16", r.zeilen, "Mindestens eine Rechnungsposition")
        self.pflicht("BR-CO-18", r.steuern, "Steueraufschlüsselung (BG-23)")

    def zeilen(self) -> None:
        if self.r.profil.reduziert:
            return
        for nr, z in enumerate(self.r.zeilen, start=1):
            name = f"Position {z.id or nr}"
            self.pflicht("BR-21", z.id, f"{name}: Positionsnummer (BT-126)")
            self.pflicht("BR-22", z.menge, f"{name}: Menge (BT-129)")
            self.pflicht("BR-23", z.einheit, f"{name}: Einheit (BT-130)")
            self.pflicht("BR-24", z.netto, f"{name}: Nettobetrag (BT-131)")
            self.pflicht("BR-25", z.bezeichnung, f"{name}: Bezeichnung (BT-153)")
            self.pflicht("BR-26", z.einzelpreis, f"{name}: Einzelpreis (BT-146)")
            self.pflicht(
                "BR-CO-04", z.steuerkategorie, f"{name}: Steuerkategorie (BT-151)"
            )
            if z.einzelpreis is not None and z.einzelpreis < 0:
                self.fehler("BR-27", f"{name}: Einzelpreis ist negativ")
            if z.steuerkategorie == "S" and (z.steuersatz or NULL) <= 0:
                self.fehler("BR-S-05", f"{name}: Normalbesteuerung mit Satz 0")
            if z.steuerkategorie in _STEUERFREI and (z.steuersatz or NULL) != 0:
                self.fehler(
                    f"BR-{z.steuerkategorie}-05",
                    f"{name}: Kategorie {z.steuerkategorie} verlangt Steuersatz 0",
                )

    def rechenregeln(self) -> None:
        r, s = self.r, self.r.summen
        abschlaege = _summe(za.betrag for za in r.zu_abschlaege if not za.zuschlag)
        zuschlaege = _summe(za.betrag for za in r.zu_abschlaege if za.zuschlag)

        if not r.profil.reduziert:
            self.gleich(
                "BR-CO-10",
                s.positionen_netto,
                _summe(z.netto for z in r.zeilen),
                "Summe der Positionen (BT-106)",
            )
            if r.zu_abschlaege or s.abschlaege:
                self.gleich(
                    "BR-CO-11", s.abschlaege or NULL, abschlaege, "Nachlässe (BT-107)"
                )
            if r.zu_abschlaege or s.zuschlaege:
                self.gleich(
                    "BR-CO-12", s.zuschlaege or NULL, zuschlaege, "Zuschläge (BT-108)"
                )
            if s.positionen_netto is not None:
                self.gleich(
                    "BR-CO-13",
                    s.netto,
                    s.positionen_netto
                    - (s.abschlaege or NULL)
                    + (s.zuschlaege or NULL),
                    "Nettosumme (BT-109)",
                )
        if r.steuern:
            self.gleich(
                "BR-CO-14",
                s.steuer,
                _summe(st.betrag for st in r.steuern),
                "Steuersumme (BT-110)",
            )
        if s.netto is not None and s.brutto is not None:
            self.gleich(
                "BR-CO-15",
                s.brutto,
                s.netto + (s.steuer or NULL),
                "Bruttosumme (BT-112)",
            )
        if s.brutto is not None and s.zahlbetrag is not None:
            soll = s.brutto - (s.vorauszahlung or NULL) + (s.rundung or NULL)
            if r.erweitert and abs(s.zahlbetrag - soll) > CENT / 2:
                # Extensions kennen z.B. Drittzahlungen, die den Zahlbetrag ändern.
                self.warnung(
                    "BR-CO-16",
                    f"Zahlbetrag (BT-115): ausgewiesen {s.zahlbetrag:.2f}, nach "
                    f"EN 16931 {soll:.2f} — Extension-Profil",
                )
            else:
                self.gleich("BR-CO-16", s.zahlbetrag, soll, "Zahlbetrag (BT-115)")

    def steuern(self) -> None:
        r = self.r
        for st in r.steuern:
            kat, satz = st.kategorie or "?", st.satz or NULL
            name = f"Steuer {kat} {_satz(satz)} %"
            if st.basis is not None and not r.profil.reduziert:
                basis = (
                    _summe(
                        z.netto
                        for z in r.zeilen
                        if _gleiche_steuer(z.steuerkategorie, z.steuersatz, kat, satz)
                    )
                    - _summe(
                        za.betrag
                        for za in r.zu_abschlaege
                        if not za.zuschlag
                        and _gleiche_steuer(
                            za.steuerkategorie, za.steuersatz, kat, satz
                        )
                    )
                    + _summe(
                        za.betrag
                        for za in r.zu_abschlaege
                        if za.zuschlag
                        and _gleiche_steuer(
                            za.steuerkategorie, za.steuersatz, kat, satz
                        )
                    )
                )
                self.gleich(
                    f"BR-{kat}-08", st.basis, basis, f"{name}: Bemessungsgrundlage"
                )
            if kat == "S" and st.basis is not None and st.betrag is not None:
                self._steuerbetrag(name, st.betrag, _rund(st.basis * satz / 100))
            if kat in _STEUERFREI and (st.betrag or NULL) != 0:
                self.fehler(f"BR-{kat}-09", f"{name}: Steuerbetrag muss 0 sein")
            if kat in _MIT_BEFREIUNGSGRUND and not (
                st.befreiungsgrund or st.befreiungsgrund_code
            ):
                self.fehler(f"BR-{kat}-10", f"{name}: Befreiungsgrund (BT-120) fehlt")
            if kat == "K" and not (r.lieferanschrift and r.lieferanschrift.land):
                self.fehler("BR-IC-12", f"{name}: Lieferland (BT-80) fehlt")
            if kat in _BEIDE_UST_ID and not (r.verkaeufer.ust_id and r.kaeufer.ust_id):
                self.fehler(
                    _BEIDE_UST_ID[kat],
                    f"{name}: Verkäufer und Käufer brauchen eine USt-IdNr.",
                )
            if kat == "S":
                self._satz_zum_land(satz)

    def _steuerbetrag(self, name: str, ist: Decimal, soll: Decimal) -> None:
        """BR-S-09 mit der Toleranz des CEN-Schematrons: unter 1,00 ist Rundung."""
        abweichung = abs(ist - soll)
        text = f"{name}: Steuerbetrag: ausgewiesen {ist:.2f}, berechnet {soll:.2f}"
        if abweichung >= 1:
            self.fehler("BR-S-09", text)
        elif abweichung > CENT / 2:
            self.warnung("BR-S-09", f"{text} (Rundungsdifferenz)")

    def _satz_zum_land(self, satz: Decimal) -> None:
        land = (self.r.verkaeufer.anschrift.land or "").upper()
        info = EU_STEUERSAETZE.get(land)
        if info is None:
            return
        # Im OSS-Verfahren gilt der Satz des Bestimmungslands.
        laender = [info]
        ziel = EU_STEUERSAETZE.get((self.r.kaeufer.anschrift.land or "").upper())
        if ziel is not None and ziel is not info:
            laender.append(ziel)
        erlaubt = {
            _satz(s)
            for i in laender
            for s in (i.normal, i.ermaessigt, i.ermaessigt_2, i.super_ermaessigt)
            if s is not None
        }
        if _satz(satz) not in erlaubt:
            saetze = ", ".join(
                f"{s} %" for s in sorted(s for s in erlaubt if s is not None)
            )
            self.warnung(
                "SATZ-LAND",
                f"Steuersatz {_satz(satz)} % ist in {info.land_name} unüblich "
                f"({saetze})",
            )

    def ustg(self) -> None:
        r = self.r
        if not (r.verkaeufer.ust_id or r.verkaeufer.steuernummer):
            self.fehler(
                "UStG-14-2",
                "Verkäufer ohne USt-IdNr. und ohne Steuernummer (§ 14 Abs. 4 Nr. 2)",
            )
        if not r.profil.reduziert and not (
            r.leistungsdatum or r.leistungszeitraum_von or r.leistungszeitraum_bis
        ):
            self.warnung(
                "UStG-14-6",
                "Kein Leistungsdatum oder -zeitraum (§ 14 Abs. 4 Nr. 6) — "
                "gilt nur als erfüllt, wenn es dem Rechnungsdatum entspricht",
            )


def pruefe(rechnung: Rechnung) -> list[Befund]:
    """Alle Befunde zu einer Rechnung, Fehler zuerst."""
    p = _Pruefung(rechnung)
    p.kopf()
    p.zeilen()
    p.rechenregeln()
    p.steuern()
    p.ustg()
    return sorted(p.befunde, key=lambda b: b.schwere is not Schwere.FEHLER)
