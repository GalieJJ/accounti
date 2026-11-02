"""Storno statt Änderung (Spec 4.4) — Freigabe, Korrektur, Storno, Export-Vermerk.

Vor der Freigabe ist eine Buchung ein Vorschlag und darf direkt korrigiert werden.
Ab der Freigabe (``auto``, ``geprueft``, ``korrigiert``, ``exportiert``) ist die
Korrektur ein Storno mit Neubuchung: Die Stornobuchung tauscht Soll und Haben bei
gleichen Beträgen und gleichem Steuerschlüssel (die Konvention des Projekts, mit der
sich Salden, Kennziffern, OSS und DATEV-Export von selbst umkehren), das Original
bekommt ``storniert_durch``, der Storno ``storno_von`` — beide bleiben sichtbar.
Die Neubuchung übernimmt alles vom Original (Transaktion, Beleg, Belegposition,
Belegnummer, Datum, Text, Betrag) und ändert nur, was korrigiert wird. Die
Sperre in ``ereignisse`` lässt andere Wege gar nicht erst zu.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from accounti.abschluss.kontenrahmen import (
    Kontenart,
    Kontenrahmen,
    lade_kontenrahmen,
    mit_eingerichteten_konten,
)
from accounti.anzeige import betrag_de, datum_de
from accounti.buchung.konten import soll_gleich_haben
from accounti.buchung.steuergruppe import selbst_berechnete_steuer
from accounti.db.repo_pruefung import setze_storniert_durch, speichere_korrektur
from accounti.db.repository import (
    aktualisiere_buchung,
    finde_buchung,
    lade_beleg,
    setze_status,
    speichere_buchung,
)
from accounti.db.tabellen import BuchungssatzRow
from accounti.konfiguration import Buchhaltung
from accounti.models import Beleg, Buchungssatz, BuchungStatus
from accounti.models.pruefung import Buchungskorrektur
from accounti.pruefung.einstellungen import PruefEinstellungen
from accounti.pruefung.ereignisse import gesperrt
from accounti.pruefung.journal import schreibe
from accounti.pruefung.person import aktuelle_person, journal_kontext
from accounti.steuer.kennziffern import (
    STEUERSCHLUESSEL,
    Kontenplan,
    Seite,
    sachseite_aus_konten,
)
from accounti.steuer.umsatzsteuer import UStBerechner

if TYPE_CHECKING:
    from accounti.elster.konfiguration import ElsterEinstellungen

FREIGEGEBEN = frozenset(
    {
        BuchungStatus.AUTO_GEBUCHT,
        BuchungStatus.GEPRUEFT,
        BuchungStatus.KORRIGIERT,
        BuchungStatus.EXPORTIERT,
    }
)
VORSCHLAG = frozenset({BuchungStatus.ENTWURF, BuchungStatus.ZUR_PRUEFUNG})
NULL = Decimal("0")
CENT = Decimal("0.01")
_JE_ABFRAGE = 500  # Buchungen je IN-Abfrage
# ausgewiesene Umsatzsteuer (2, 3): --ohne-steuer entfernt sie aus keiner
# Belegbuchung (§ 14c UStG) — Vorsteuer, ig. Erwerb und § 13b (Eingang) schon
AUSGEWIESENE_UST = frozenset(
    s for s, r in STEUERSCHLUESSEL.items() if r.vorsteuer is None and r.bmg is not None
)
# § 13b und ig. Erwerb (18, 19, 91, 94): Steuerschuld und Vorsteuer berechnet der
# Empfänger selbst — die Steuer steckt nicht im Zahlbetrag, und --ohne-steuer ist nur
# richtig, wenn gar kein solcher Fall vorliegt
SELBST_BERECHNET = frozenset(
    s
    for s, r in STEUERSCHLUESSEL.items()
    if r.vorsteuer is not None and r.bmg is not None
)
HINWEIS_SELBST_BERECHNET = (
    "liegt ein § 13b-Fall bzw. ein ig. Erwerb vor, bleibt die Steuer geschuldet "
    "(§ 13b Abs. 5, § 13a Abs. 1 Nr. 2 UStG), und der Vorsteuerabzug hängt nicht an "
    "der Rechnung (§ 15 Abs. 1 Nr. 3/4 UStG)"
)
# DATEV-Schlüssel, deren Steuer im Zahlbetrag steckt → (Satz)
_IM_BRUTTO = {
    3: Decimal("19"),
    2: Decimal("7"),
    9: Decimal("19"),
    8: Decimal("7"),
}


class StornoError(ValueError):
    """Storno, Korrektur oder Freigabe ist so nicht möglich.

    ``meldung`` ist der Text ohne CLI-Optionen (für die Oberfläche), ``feld`` das
    betroffene Formularfeld (``steuer``, ``datum``, ``grund`` oder ``None``), ``cli``
    der vollständige Text mit den Optionen der CLI (``--steuer`` …) — ``str()`` liefert
    ihn unverändert wie bisher (Baustein 10b)."""

    def __init__(
        self, meldung: str, *, feld: str | None = None, cli: str | None = None
    ) -> None:
        super().__init__(cli or meldung)
        self.meldung = meldung
        self.feld = feld
        self.cli = cli


def ist_freigegeben(b: Buchungssatz) -> bool:
    return b.status in FREIGEGEBEN


@dataclass(frozen=True)
class SteuerOptionen:
    """Was eine Korrektur am Steuerschlüssel dieser Buchung zulässt — dieselbe
    Prüfung, mit der ``korrigiere`` ablehnt (für das Formular der Oberfläche)."""

    aktuell: int | None
    andere_schluessel: bool  # anderen Schlüssel wählen (nicht bei Belegbuchungen)
    schluessel: tuple[int, ...]  # wählbare Schlüssel (mit dem aktuellen)
    ohne_steuer: bool  # „ohne Steuer“ wählbar
    ohne_nur_mit_grund: bool  # … dann nur mit Grund
    hinweis: str | None = None


def steuer_optionen(b: Buchungssatz) -> SteuerOptionen:
    beleg = b.beleg_id is not None
    ausgewiesen = beleg and b.steuer_schluessel in AUSGEWIESENE_UST
    hinweis = None
    if ausgewiesen:
        hinweis = (
            "Ausgewiesene Umsatzsteuer wird geschuldet, bis die Rechnung berichtigt "
            "ist (§ 14c Abs. 1 UStG) — die Berichtigung als neuen Beleg erfassen"
        )
    elif b.steuer_schluessel in SELBST_BERECHNET:
        hinweis = HINWEIS_SELBST_BERECHNET
    elif beleg:
        hinweis = "Die Steuer kommt aus dem Beleg — nur die Konten korrigieren"
    alle = tuple(sorted(STEUERSCHLUESSEL))
    aktuell = (b.steuer_schluessel,) if b.steuer_schluessel is not None else ()
    return SteuerOptionen(
        aktuell=b.steuer_schluessel,
        andere_schluessel=not beleg,
        schluessel=aktuell if beleg else alle,
        ohne_steuer=not ausgewiesen,
        ohne_nur_mit_grund=beleg or b.steuer_schluessel in SELBST_BERECHNET,
        hinweis=hinweis,
    )


@dataclass(frozen=True)
class Korrekturumgebung:
    """Kontenrahmen (mit ``abschluss.kontenzuordnung``), Buchhaltung und
    Prüfeinstellungen **der Gesellschaft** — für CLI und Browser gleich."""

    kontenrahmen: Kontenrahmen
    buchhaltung: Buchhaltung
    pruefung: PruefEinstellungen
    # Funktionskonten und steuerrelevante Konten der Voranmeldung — für die
    # Richtungsprüfung (``_kennziffer_gedreht``); None: die Standards
    elster: ElsterEinstellungen | None = None


def lade_korrekturumgebung(pfad: str | Path) -> Korrekturumgebung:
    """Aus der Konfiguration der Gesellschaft (``KonfigurationError``,
    ``KontenrahmenError`` bei Fehlern)."""
    from accounti.abschluss.konfiguration import lade_abschluss
    from accounti.elster.konfiguration import lade_elster_konten
    from accounti.konfiguration import lade_buchhaltung
    from accounti.pruefung.einstellungen import lade_pruefung

    return Korrekturumgebung(
        kontenrahmen=lade_abschluss(pfad).lade_kontenrahmen(),
        buchhaltung=lade_buchhaltung(pfad),
        pruefung=lade_pruefung(pfad),
        elster=lade_elster_konten(pfad),
    )


@dataclass
class Korrektur:
    original: Buchungssatz
    neu: Buchungssatz | None  # direkt korrigiert bzw. Neubuchung (None: nur Storno)
    storno: Buchungssatz | None = None  # None: direkt korrigierter Vorschlag
    korrektur: Buchungskorrektur | None = None
    warnungen: list[str] = field(default_factory=list)

    @property
    def direkt(self) -> bool:
        return self.storno is None


def _lade(session: Session, buchung_id: str) -> Buchungssatz:
    try:
        return finde_buchung(session, buchung_id)
    except ValueError as fehler:
        raise StornoError(str(fehler)) from fehler


def _kurz(b: Buchungssatz) -> str:
    return str(b.id)[:8]


def _nicht_storniert(b: Buchungssatz) -> None:
    if b.storno_von is not None:
        raise StornoError(
            f"Buchung {_kurz(b)} ist selbst ein Storno (von {str(b.storno_von)[:8]}) — "
            "eine Stornobuchung wird nicht korrigiert"
        )
    if b.storniert_durch is not None:
        raise StornoError(
            f"Buchung {_kurz(b)} ist schon storniert (durch "
            f"{str(b.storniert_durch)[:8]}) — gegebenenfalls die Neubuchung korrigieren"
        )


def _sachkonten(kr: Kontenrahmen, soll: str, haben: str) -> set[str]:
    """Die Seiten, die kein Geld- oder Personenkonto sind."""
    return {k for k in (soll, haben) if not kr.ist_geldkonto(k)}


def _pruefe_ausdruecklich(
    b: Buchungssatz,
    soll: str,
    haben: str,
    steuer: int | None,
    ohne_steuer: bool,
    kr: Kontenrahmen,
) -> None:
    """Ändert sich das Sachkonto, wird der Steuerschlüssel nicht still mitgenommen.

    Der Schlüssel gehört zum Sachkonto: Eine Versicherung (4360), eine Privatentnahme
    (1800) oder eine Geldbewegung (1200 an 1361) trägt keine Vorsteuer bzw.
    Umsatzsteuer, nur weil der Vorschlag auf 4900 oder 8400 lag."""
    if b.steuer_schluessel is None or steuer is not None or ohne_steuer:
        return
    alt = _sachkonten(kr, b.soll_konto, b.haben_konto)
    neu = _sachkonten(kr, soll, haben)
    if alt == neu:
        return
    von = "/".join(sorted(alt)) or "—"
    nach = "/".join(sorted(neu)) or "nur Geld- und Personenkonten"
    raise StornoError(
        f"Das Sachkonto ändert sich ({von} → {nach}) — Steuerschlüssel "
        f"{b.steuer_schluessel} ausdrücklich bestätigen oder „ohne Steuer“ wählen",
        feld="steuer",
        cli=f"Buchung {_kurz(b)}: Das Sachkonto ändert sich ({von} → {nach}) — "
        f"Steuerschlüssel {b.steuer_schluessel} ausdrücklich bestätigen mit "
        f"--steuer {b.steuer_schluessel} oder entfernen mit --ohne-steuer",
    )


_SEITE = {"soll": "Soll", "haben": "Haben"}
_ANDERE: dict[Seite, Seite] = {"soll": "haben", "haben": "soll"}


def kontenplan(
    session: Session,
    buchhaltung: Buchhaltung | None,
    elster: ElsterEinstellungen | None,
) -> Kontenplan:
    """Konten, wie die Voranmeldung sie liest (``elster.ustva.kontenplan``): Bereiche
    der Buchhaltung, eingerichtete Bankkonten, ``elster.steuerrelevante_konten`` und
    ``elster.kennziffern_konten``."""
    from accounti.db.repository import lade_bankkonten
    from accounti.elster.konfiguration import bereiche

    bh = buchhaltung or Buchhaltung()
    return Kontenplan(
        kontenrahmen=bh.kontenrahmen.upper(),
        debitoren=(bh.debitoren_von, bh.debitoren_bis),
        kreditoren=(bh.kreditoren_von, bh.kreditoren_bis),
        geldkonten=frozenset(
            {bh.bank_konto} | {k.sachkonto for k in lade_bankkonten(session)}
        ),
        steuerrelevant=bereiche(elster.steuerrelevante_konten) if elster else None,
        kennziffern_konten=dict(elster.kennziffern_konten) if elster else {},
    )


def _erfolgsseite(soll: str, haben: str, kr: Kontenrahmen) -> Seite | None:
    """Seite des einzigen Erfolgskontos (Aufwand, Ertrag) laut Abschlusszuordnung —
    Steuerkonten zählen hier als Bestand; ``None`` bei zwei oder keinem."""

    def erfolg(konto: str) -> bool:
        return kr.art(konto, "bilanz") is Kontenart.ERFOLG

    if erfolg(soll) == erfolg(haben):
        return None
    return "soll" if erfolg(soll) else "haben"


def _richtungswechsel(
    b: Buchungssatz, soll: str, haben: str, plan: Kontenplan, kr: Kontenrahmen
) -> str | None:
    """Was die Korrektur einer Belegbuchung an ihrer Richtung umdreht — ``None``, wenn
    die Seiten bleiben (Gesamttest 10b-1, Runde 6: g5w NEU-1, NEU-2):

    (a) ein Konto wechselt die Seite (neues Soll = altes Haben oder umgekehrt) — der
        Tausch zweier Sachkonten („1576 an 1548“) ebenso wie „10001 an 8400“;
    (b) die Sachseite ist vorher und nachher aus den Konten bestimmt
        (``kennziffern.sachseite_aus_konten``: gegenüber dem einzigen Gegenkonto,
        sonst das einzige Erlöskonto) und eine andere;
    (c) ist sie nur per Rückfall bestimmt (zwei Gegenkonten, zwei Sachkonten ohne
        Erlös), sperrt sie nicht — Runde 5 las dort die Seite des Schlüssels, ohne
        Schlüssel „Haben“, und sperrte „4360 an 1200 → 1800 an 1200“ (Privatanteil),
        „4120 an 70001 → 4120 an 1740“ (Lohnverbindlichkeit) usw.;
    (e) ein Erfolgskonto steht vorher und nachher allein auf einer Seite, nachher auf
        der anderen — aus einem Aufwand würde ein Ertrag („4930 an 70001 → 1700 an
        4931“, zwei Konten ohne Gegenkonto).

    Ob eine Kennziffer der Voranmeldung umkehrt (d), prüft ``_kennziffer_gedreht``
    mit dem Schlüssel nach der Korrektur."""
    alt_soll, alt_haben = b.soll_konto, b.haben_konto
    gewandert: list[tuple[str, Seite]] = []
    if alt_soll != alt_haben:  # ein Altfall „4900 an 4900“ hat keine Richtung
        if alt_soll == haben:
            gewandert.append((alt_soll, "soll"))
        if alt_haben == soll:
            gewandert.append((alt_haben, "haben"))
    if gewandert:
        return "die Korrektur stellt " + " und ".join(
            f"Konto {konto} aus dem {_SEITE[seite]} ins {_SEITE[_ANDERE[seite]]}"
            for konto, seite in gewandert
        )

    def sachkonto(s: str, h: str) -> Seite | None:
        return sachseite_aus_konten(s, h, plan)

    def erfolgskonto(s: str, h: str) -> Seite | None:
        return _erfolgsseite(s, h, kr)

    for art, seiten in (("Sachkonto", sachkonto), ("Erfolgskonto", erfolgskonto)):
        vorher, nachher = seiten(alt_soll, alt_haben), seiten(soll, haben)
        if vorher is None or nachher is None or vorher == nachher:
            continue
        konto = alt_soll if vorher == "soll" else alt_haben
        neu = soll if nachher == "soll" else haben
        return (
            f"das {art} {konto} steht im {_SEITE[vorher]}, nach der Korrektur stünde "
            f"das {art} {neu} im {_SEITE[nachher]}"
        )
    return None


def _kennziffer_gedreht(
    session: Session, b: Buchungssatz, kandidat: Buchungssatz, plan: Kontenplan
) -> str | None:
    """(d) Kehrt eine Kennziffer der Voranmeldung, die die Buchung vorher und nachher
    bucht, ihr Vorzeichen um? Fängt, was (a), (b) und (e) nicht sehen: eigene
    Funktionskonten (``elster.kennziffern_konten``) auf beiden Seiten getauscht. Allein
    genügte das nicht — „4930 an 70001, Schlüssel 9 → 1700 an 4930“ lässt die
    Voranmeldung gleich und bucht doch den Aufwand ins Haben."""
    from accounti.db.repository import lade_buchungen_zu
    from accounti.steuer.kennziffern import kennziffern_der_buchung

    andere = lade_buchungen_zu(session, beleg_id=b.beleg_id)
    vorher = kennziffern_der_buchung(b, plan, andere)
    nachher = kennziffern_der_buchung(kandidat, plan, andere)
    gedreht = sorted(
        kz for kz in vorher.keys() & nachher.keys() if vorher[kz] * nachher[kz] < 0
    )
    if not gedreht:
        return None
    return "die Voranmeldung kehrte " + ", ".join(
        f"Kz {kz} um ({betrag_de(vorher[kz])} € → {betrag_de(nachher[kz])} €)"
        for kz in gedreht
    )


def _richtung_fehler(b: Buchungssatz, kern: str) -> StornoError:
    """Bei einer Belegbuchung bestimmt der Beleg die Richtung: Eine Rechnung bucht ihr
    Sachkonto auf der einen Seite, eine Gutschrift bzw. Rechnungskorrektur auf der
    anderen. Eine Korrektur, die die Seiten vertauscht, buchte den Beleg als sein
    Gegenteil — die Voranmeldung kehrte das Vorzeichen um (aus 95 € Umsatzsteuer
    würden 95 € Erstattung, aus Vorsteuer eine Minderung), ohne Steuer würde aus einem
    Aufwand ein Ertrag.

    Gilt für jede Belegbuchung, nicht nur bei ausgewiesener Umsatzsteuer (2, 3):
    Diese wird geschuldet, bis die Rechnung berichtigt ist (§ 14c Abs. 1 UStG); die
    Vorsteuer mindert erst die Gutschrift bzw. Rechnungskorrektur des Lieferanten,
    beides im Zeitraum der Berichtigung (§ 17 Abs. 1 Satz 1, 2 und 7 UStG). Die
    Berichtigung ist ein eigener Beleg mit eigener Buchung (``rechnung neu
    --korrektur-zu``, Gutschrift des Lieferanten); ist die Buchung selbst falsch, ein
    Storno mit Grund — ein Vorschlag wird dafür erst freigegeben (sonst hinge er fest:
    „noch ein Vorschlag — direkt korrigieren statt stornieren“). Runde 5, g4w N1;
    Runde 6, g5w NEU-1/NEU-2."""
    k = _kurz(b)
    if b.steuer_schluessel in AUSGEWIESENE_UST:
        steuer = (
            f"die ausgewiesene Umsatzsteuer (Schlüssel {b.steuer_schluessel}) wird "
            "geschuldet, bis die Rechnung berichtigt ist (§ 14c Abs. 1 UStG); die "
            "Berichtigung wirkt erst in ihrem Zeitraum (§ 17 Abs. 1 UStG)"
        )
    elif b.steuer_schluessel in STEUERSCHLUESSEL:
        steuer = (
            f"die Steuer (Schlüssel {b.steuer_schluessel}) ändert erst die Gutschrift "
            "bzw. Rechnungskorrektur, in deren Zeitraum (§ 17 Abs. 1 UStG)"
        )
    else:
        steuer = "der Beleg würde als sein Gegenteil gebucht (Rechnung als Gutschrift)"
    if ist_freigegeben(b):
        falsch = "ist die Buchung selbst falsch, sie mit Grund stornieren"
        falsch_cli = (
            "ist die Buchung selbst falsch, sie stornieren (accounti buchung "
            f'storniere {k} --grund "…")'
        )
    else:
        falsch = (
            "ist der Vorschlag selbst falsch (z. B. ein anderer Beleg), ihn freigeben "
            "und dann mit Grund stornieren"
        )
        falsch_cli = (
            "ist der Vorschlag selbst falsch (z. B. ein anderer Beleg), ihn freigeben "
            f"und dann stornieren (accounti bestaetige {k}, dann accounti buchung "
            f'storniere {k} --grund "…")'
        )
    kopf = (
        f"Buchung {k} hat einen Beleg — er bestimmt die Richtung (Rechnung oder "
        f"Gutschrift): {kern}; {steuer}. Berichtigung als eigener Beleg "
        "(Gutschrift/Rechnungskorrektur) erfassen und verbuchen"
    )
    ende = " — nur Konten derselben Seite korrigieren"
    return StornoError(
        f"{kopf}; {falsch}{ende}",
        feld="soll",
        cli=f"{kopf} (Ausgangsrechnung: accounti rechnung neu --korrektur-zu …); "
        f"{falsch_cli}{ende}",
    )


def _steuer(
    b: Buchungssatz,
    steuer: int | None,
    ohne_steuer: bool,
    grund: str | None,
    beleg_mit_satz: bool = True,
) -> tuple[int | None, Decimal, Decimal | None]:
    """(Schlüssel, Netto, Steuer) nach der Korrektur — aus dem Brutto der Buchung.

    Bei einer Belegbuchung kommt die Steuer aus dem Beleg; einen anderen Schlüssel
    nimmt sie nur an, wenn der Beleg keinen Satz liefert (``beleg_mit_satz``, z. B.
    ZUGFeRD MINIMUM: brutto gebucht) oder der Schlüssel § 13b bzw. ig. Erwerb ist —
    diese Steuer steht nie auf dem Beleg (§ 14a Abs. 5 UStG), der Empfänger
    berechnet sie selbst. Weist der Beleg Umsatzsteuer aus (Schlüssel 2, 3), ändert
    keine Korrektur den Schlüssel (§ 14c Abs. 1 UStG)."""
    if ohne_steuer and steuer is not None:
        raise StornoError(
            "Steuerschlüssel und „ohne Steuer“ schließen sich aus",
            feld="steuer",
            cli="--steuer und --ohne-steuer schließen sich aus",
        )
    if steuer is not None and steuer not in STEUERSCHLUESSEL:
        # wie der Browser (_steuerangabe): -1, 0, 4 … buchten sonst ohne Steuerbetrag,
        # erst die Voranmeldung sperrte (Runde 4, g3w-web N5)
        bekannt = ", ".join(str(s) for s in sorted(STEUERSCHLUESSEL))
        raise StornoError(
            f"Unbekannter Steuerschlüssel {steuer} — bekannt sind {bekannt}",
            feld="steuer",
            cli=f"--steuer {steuer}: Unbekannter Steuerschlüssel — bekannt sind "
            f"{bekannt} (ohne Steuer: --ohne-steuer)",
        )
    if not ohne_steuer and steuer is None:  # Schlüssel bleibt
        return b.steuer_schluessel, b.betrag_netto, b.steuer_betrag
    schluessel = None if ohne_steuer else steuer
    if schluessel == b.steuer_schluessel:
        return b.steuer_schluessel, b.betrag_netto, b.steuer_betrag
    optionen = steuer_optionen(b)
    if (
        not ohne_steuer
        and not optionen.andere_schluessel
        and beleg_mit_satz
        and schluessel not in SELBST_BERECHNET
    ):
        # Beleg mit Satz: die Steuer kommt aus ihm — § 13b bzw. ig. Erwerb nicht, der
        # Empfänger berechnet sie selbst (Gesamttest Paket C)
        raise StornoError(
            "Die Buchung hat einen Beleg — ihre Steuer kommt aus dem Beleg bzw. aus "
            "dem Ausgleich; nur Konten korrigieren, § 13b bzw. ig. Erwerb mit "
            "Schlüssel 94/91/19/18 (oder die Vorsteuer mit „ohne Steuer“ und Grund "
            "entfernen)",
            feld="steuer",
            cli=f"Buchung {_kurz(b)} hat einen Beleg — ihre Steuer kommt aus dem Beleg "
            "bzw. aus dem Ausgleich; nur Konten korrigieren, § 13b bzw. ig. Erwerb "
            "mit --steuer 94/91/19/18 (oder die Vorsteuer mit --ohne-steuer --grund … "
            "entfernen)",
        )
    if not optionen.ohne_steuer:
        # ausgewiesene USt (2, 3) einer Belegbuchung: jede Schlüsseländerung, nicht nur
        # „ohne Steuer“ — auch § 13b/ig. Erwerb und ein Beleg ohne Satz nehmen sie
        # nicht aus der Voranmeldung; sie wird geschuldet, bis die Rechnung berichtigt
        # ist, die Berichtigung wirkt erst in ihrem Zeitraum (§ 14c Abs. 1 Satz 2
        # i. V. m. § 17 Abs. 1 UStG; wie main, Gesamttest 10b-1 Runde 4, g3w-merge M1)
        raise StornoError(
            f"Buchung {_kurz(b)} hat einen Beleg mit Schlüssel {b.steuer_schluessel}: "
            "ausgewiesene Umsatzsteuer wird geschuldet, bis die Rechnung berichtigt "
            "ist (§ 14c Abs. 1 UStG) — die Berichtigung als neuen Beleg erfassen und "
            "verbuchen, nicht den Schlüssel der Buchung ändern oder die Steuer "
            "entfernen",
            feld="steuer",
        )
    selbst = ohne_steuer and b.steuer_schluessel in SELBST_BERECHNET
    if selbst and not (grund or "").strip():
        raise StornoError(
            f"Schlüssel {b.steuer_schluessel}: „ohne Steuer“ entfernt Steuerschuld und "
            "Vorsteuer — nur, wenn kein § 13b-Fall bzw. kein ig. Erwerb vorliegt; "
            f"{HINWEIS_SELBST_BERECHNET}. Bitte einen Grund angeben (steht im Journal)",
            feld="grund",
            cli=f"Buchung {_kurz(b)}, Schlüssel {b.steuer_schluessel}: --ohne-steuer "
            "entfernt Steuerschuld und Vorsteuer — nur, wenn kein § 13b-Fall bzw. kein "
            f"ig. Erwerb vorliegt; {HINWEIS_SELBST_BERECHNET}. Mit Grund (steht im "
            'Journal): --ohne-steuer --grund "kein § 13b: …"',
        )
    if b.beleg_id is not None and not (grund or "").strip():
        if not ohne_steuer:
            raise StornoError(
                f"Die Buchung hat einen Beleg — Steuerschlüssel {schluessel} setzt "
                "nur, wer einen Grund nennt (steht im Journal), z.B. „Reverse Charge, "
                "Satz laut PDF-Ansicht 19 %“",
                feld="grund",
                cli=f"Buchung {_kurz(b)} hat einen Beleg — Steuerschlüssel "
                f"{schluessel} setzt nur, wer einen Grund nennt (steht im Journal): "
                '--grund "z.B. Reverse Charge, Satz laut PDF-Ansicht 19 %"',
            )
        raise StornoError(
            "Die Buchung hat einen Beleg — die Steuer daraus entfernt nur, wer einen "
            "Grund nennt (steht im Journal), z.B. „kein Vorsteuerabzug, Rechnung "
            "unvollständig“",
            feld="grund",
            cli=f"Buchung {_kurz(b)} hat einen Beleg — die Steuer daraus entfernt nur, "
            "wer einen Grund nennt (steht im Journal): --ohne-steuer --grund "
            '"z.B. kein Vorsteuerabzug, Rechnung unvollständig"',
        )
    # Brutto = Zahlbetrag: die selbst berechnete Steuer (§ 13b, ig. Erwerb) steckt
    # nicht darin
    steuer_im_zahlbetrag = b.steuer_schluessel not in SELBST_BERECHNET
    brutto = b.betrag_netto + (
        (b.steuer_betrag or NULL) if steuer_im_zahlbetrag else NULL
    )
    if schluessel in _IM_BRUTTO:
        netto = UStBerechner().brutto_zu_netto(brutto, _IM_BRUTTO[schluessel])
        return schluessel, netto, brutto - netto
    if schluessel in SELBST_BERECHNET:
        # der Zahlbetrag ist das Netto; die Steuer berechnet der Empfänger
        return schluessel, brutto, selbst_berechnete_steuer(schluessel, brutto)
    return schluessel, brutto, None


def _pruefe_umkehrbar(b: Buchungssatz, kr: Kontenrahmen) -> None:
    """Die Gegenbuchung hebt die Steuer nur auf, wenn genau eine Seite ein Geld- oder
    Personenkonto ist (``abschluss/salden.py``)."""
    if not b.steuer_betrag or kr.steuerkonto(b.steuer_schluessel) is None:
        return
    if kr.ist_geldkonto(b.soll_konto) == kr.ist_geldkonto(b.haben_konto):
        raise StornoError(
            f"Buchung {_kurz(b)} ({b.soll_konto} an {b.haben_konto}, Schlüssel "
            f"{b.steuer_schluessel}) lässt sich nicht durch Gegenbuchung stornieren: "
            "beide Seiten haben dieselbe Natur, die Steuer höbe sich nicht auf — "
            "bitte mit dem Steuerberater klären"
        )


def _stornodatum(session: Session, b: Buchungssatz, datum: date | None) -> date:
    """Datum von Storno und Neubuchung: ohne ``datum`` das des Originals, sonst
    ``datum`` — nie davor. Eine Änderung der Bemessungsgrundlage wird im Zeitraum
    berichtigt, in dem sie eintritt (§ 17 Abs. 1 Satz 7 UStG), ein Buchungsirrtum im
    Zeitraum des Originals (berichtigte Voranmeldung) — beides nie vor dem Umsatz."""
    tag = datum or b.datum
    if tag < b.datum:
        regel = "ein Storno gilt frühestens ab dem Tag des Originals"
        raise StornoError(
            f"Storno am {datum_de(tag)} läge vor der Buchung vom "
            f"{datum_de(b.datum)} — {regel}",
            feld="datum",
            cli=f"Storno am {datum_de(tag)} läge vor der Buchung {_kurz(b)} vom "
            f"{datum_de(b.datum)} — {regel}",
        )
    if gesperrt(session.connection(), tag):
        if datum is None:
            raise StornoError(
                f"Die Buchung liegt in einem abgeschlossenen Zeitraum "
                f"({datum_de(b.datum)}) — für Storno und Neubuchung ein Datum in einem "
                "offenen Zeitraum angeben",
                feld="datum",
                cli=f"Buchung {_kurz(b)} liegt in einem abgeschlossenen Zeitraum "
                f"({datum_de(b.datum)}) — Storno und Neubuchung mit --datum in einen "
                "offenen Zeitraum legen",
            )
        raise StornoError(
            f"{datum_de(tag)} liegt in einem abgeschlossenen Zeitraum", feld="datum"
        )
    return tag


def _storno(
    session: Session,
    b: Buchungssatz,
    von: str,
    grund: str,
    datum: date | None,
    kr: Kontenrahmen,
    neu: Buchungssatz | None,
) -> Korrektur:
    _nicht_storniert(b)
    if not ist_freigegeben(b):
        raise StornoError(
            f"Buchung {_kurz(b)} ist noch ein Vorschlag ({b.status.value}) — direkt "
            "korrigieren statt stornieren"
        )
    _pruefe_umkehrbar(b, kr)
    tag = _stornodatum(session, b, datum)
    storno = b.model_copy(
        update={
            "id": uuid4(),
            "soll_konto": b.haben_konto,
            "haben_konto": b.soll_konto,
            "datum": tag,
            "buchungstext": f"Storno {b.buchungstext}"[:60],
            "status": BuchungStatus.GEPRUEFT,
            "confidence": 1.0,
            "geprueft_von": von[:50],
            "storno_von": b.id,
            "storniert_durch": None,
        }
    )
    korrektur = Buchungskorrektur(
        original_id=b.id,
        storno_id=storno.id,
        neubuchung_id=neu.id if neu else None,
        datum=tag,
        grund=grund,
        person=von,
    )
    with journal_kontext(person=von, grund=grund, bezug=f"korrektur {korrektur.id}"):
        try:
            speichere_buchung(session, storno)
            session.flush()
            setze_storniert_durch(session, b.id, storno.id)
            if neu is not None:
                neu = neu.model_copy(update={"datum": tag})
                speichere_buchung(session, neu)
                session.flush()
            speichere_korrektur(session, korrektur)
        except IntegrityError as fehler:
            # zwei gleichzeitige Stornos derselben Buchung: der Unique-Index auf
            # storno_von bzw. storniert_durch hält den zweiten auf
            session.rollback()
            raise StornoError(
                f"Buchung {_kurz(b)} wurde inzwischen von einem anderen Vorgang "
                "storniert — nichts geändert",
                cli=f"Buchung {_kurz(b)} wurde inzwischen von einem anderen Vorgang "
                f"storniert — nichts geändert (accounti buchung zeige {_kurz(b)})",
            ) from fehler
    return Korrektur(
        _lade(session, str(b.id)),
        neu,
        storno,
        korrektur,
        _warnungen(b, tag),
    )


def _warnungen(b: Buchungssatz, tag: date) -> list[str]:
    """Storno in einem anderen Monat: die Umsatzsteuer ändert sich dort."""
    if b.steuer_schluessel is None or (tag.year, tag.month) == (
        b.datum.year,
        b.datum.month,
    ):
        return []
    return [
        f"Storno am {datum_de(tag)} liegt in einem anderen Voranmeldungszeitraum als "
        f"das Original ({b.datum:%m/%Y}): Die Umsatzsteuer ändert sich im Zeitraum "
        f"des Stornos — ist die Voranmeldung für {b.datum:%m/%Y} schon abgegeben "
        "und war sie falsch, ist eine berichtigte Voranmeldung für diesen Zeitraum "
        "abzugeben"
    ]


def ist_wirksam(b: Buchungssatz) -> bool:
    """Weder storniert noch selbst ein Storno."""
    return b.storno_von is None and b.storniert_durch is None


# Satz der ausgewiesenen Umsatzsteuer je Schlüssel (3 → 19 %, 2 → 7 %)
_SATZ_DER_UST = {s: STEUERSCHLUESSEL[s].satz for s in AUSGEWIESENE_UST}


@dataclass(frozen=True)
class UstLuecke:
    """Ausgewiesene Umsatzsteuer eines Belegs zu einem Satz, die nicht (ganz) wirksam
    gebucht ist."""

    schluessel: int
    satz: Decimal
    ausgewiesen: Decimal
    gebucht: Decimal

    @property
    def fehlt(self) -> Decimal:
        return self.ausgewiesen - self.gebucht


def _ausgewiesen(
    beleg: Beleg | None,
    saetze: dict[Decimal, int],
    eigene: list[Buchungssatz],
    plan: Kontenplan,
) -> dict[Decimal, tuple[Decimal, int]]:
    """Umsatzsteuer des Belegs je Satz (Betrag, Positionen) — aus seinen Positionen
    (ohne Steuerbetrag: Netto × Satz); nennen sie keinen der Sätze, die Belegsteuer
    (ein Satz) bzw. die Steuer der jüngsten Rechnungsbuchung je Satz."""
    je: dict[Decimal, tuple[Decimal, int]] = {}
    if beleg is not None:
        for p in beleg.positionen:
            satz = next((s for s in saetze if s == p.steuersatz), None)
            if satz is None:
                continue
            steuer = p.steuer_betrag
            if steuer is None:
                steuer = (p.netto * satz / 100).quantize(CENT, rounding=ROUND_HALF_UP)
            betrag, anzahl = je.get(satz, (NULL, 0))
            je[satz] = (betrag + steuer, anzahl + 1)
        if not je and beleg.steuer is not None and len(saetze) == 1:
            je = {next(iter(saetze)): (beleg.steuer, 1)}
    if not je:
        from accounti.steuer.kennziffern import sachseite

        for x in sorted(eigene, key=lambda x: x.datum):
            if x.storno_von is None and x.steuer_schluessel in AUSGEWIESENE_UST:
                vorzeichen = 1 if sachseite(x, plan) == "haben" else -1
                je[_SATZ_DER_UST[x.steuer_schluessel]] = (
                    vorzeichen * (x.steuer_betrag or NULL),
                    1,
                )
    return je


def ust_luecken(
    beleg: Beleg | None,
    buchungen: Iterable[Buchungssatz],
    plan: Kontenplan,
    kopien: Iterable[Buchungssatz] = (),
) -> list[UstLuecke]:
    """Ausgewiesene Umsatzsteuer des Belegs, die nicht wirksam gebucht ist — je Satz
    die wirksam gebuchte Steuer (Schlüssel 2, 3, auf der Seite einer Rechnung) gegen
    die des Belegs (Gesamttest 10b-1, Runde 6: g5w NEU-3, NEU-4).

    ``buchungen``: alle Buchungen des Belegs (mit Stornos), ``kopien``: die Buchungen
    anderer Belegdatensätze derselben Rechnung (``belege.dubletten.kopien``) — ist die
    Rechnung dort gebucht, fehlt nichts. Nicht gezählt werden eine Zahlung mit
    derselben ``beleg_id`` (``opos/ausgleich``, ohne Schlüssel), eine Buchung zu einem
    anderen Satz und eine Minderung (Skonto, Gutschrift: die Steuer auf der
    Gegenseite) — sie mindert nach § 17 UStG, sie bucht nicht die ausgewiesene Steuer.
    Ein Beleg, der Steuer mindert (Gutschrift, negativer Betrag), fehlt nie: Fällt
    seine Buchung weg, steigt die Steuer. Die Sätze sind die der Rechnungsbuchungen
    des Belegs mit Schlüssel 2 oder 3 (ohne sie: keine ausgewiesene Steuer in accounti,
    z. B. OSS)."""
    from accounti.steuer.kennziffern import sachseite

    eigene = list(buchungen)
    saetze: dict[Decimal, int] = {}
    for x in eigene:
        if x.storno_von is None and x.steuer_schluessel in AUSGEWIESENE_UST:
            saetze.setdefault(_SATZ_DER_UST[x.steuer_schluessel], x.steuer_schluessel)
    if not saetze:
        return []
    ausgewiesen = _ausgewiesen(beleg, saetze, eigene, plan)
    gebucht: dict[Decimal, Decimal] = dict.fromkeys(saetze, NULL)
    for x in [*eigene, *kopien]:
        if not ist_wirksam(x) or x.steuer_schluessel not in AUSGEWIESENE_UST:
            continue
        vorzeichen = 1 if sachseite(x, plan) == "haben" else -1
        betrag = vorzeichen * (x.steuer_betrag or NULL)
        satz = _SATZ_DER_UST[x.steuer_schluessel]
        if betrag > 0 and satz in gebucht:
            gebucht[satz] += betrag
    luecken = []
    for satz, schluessel in sorted(saetze.items(), reverse=True):
        betrag, anzahl = ausgewiesen.get(satz, (NULL, 0))
        # Rundung: je Position höchstens ein Cent Abstand zur Buchung
        if betrag > 0 and betrag - gebucht[satz] > CENT * max(1, anzahl):
            luecken.append(UstLuecke(schluessel, satz, betrag, gebucht[satz]))
    return luecken


def _satz_text(luecke: UstLuecke) -> str:
    return f"{luecke.satz.normalize():f} % (Schlüssel {luecke.schluessel})"


def hinweis_14c(beleg: str, luecken: Sequence[UstLuecke], nach: str) -> str:
    """Ausgewiesene Umsatzsteuer eines Belegs ohne (ausreichende) wirksame Buchung —
    für die Warnung beim Storno und die Prüfregel ``beleg_ust_ohne_buchung``."""
    fehlt = sum((x.fehlt for x in luecken), NULL)
    if len(luecken) == 1:
        (x,) = luecken
        kopf = f"Beleg {beleg} weist {betrag_de(x.ausgewiesen)} € Umsatzsteuer zu "
        if x.gebucht:
            kopf += (
                f"{_satz_text(x)} aus, {nach} sind davon nur "
                f"{betrag_de(x.gebucht)} € wirksam gebucht"
            )
        else:
            kopf += (
                f"{_satz_text(x)} aus und hat {nach} keine wirksame Buchung dieser "
                "Steuer mehr"
            )
    else:
        teile = "; ".join(
            f"{_satz_text(x)}: {betrag_de(x.ausgewiesen)} € ausgewiesen, "
            + (
                f"nur {betrag_de(x.gebucht)} € gebucht"
                if x.gebucht
                else "keine wirksame Buchung"
            )
            for x in luecken
        )
        kopf = f"Beleg {beleg} weist Umsatzsteuer aus, die {nach} fehlt ({teile})"
    return (
        f"{kopf} — die {betrag_de(fehlt)} € Umsatzsteuer fehlt in der "
        "Voranmeldung, geschuldet wird sie, bis die Rechnung berichtigt ist (§ 14c "
        "Abs. 1 UStG). Richtig nur, wenn sie anders gebucht ist; sonst den Beleg "
        "wieder buchen bzw. die Berichtigung als eigenen Beleg (Gutschrift/"
        "Rechnungskorrektur) erfassen und verbuchen"
    )


def _warnung_14c(session: Session, b: Buchungssatz, plan: Kontenplan) -> list[str]:
    """Storno ohne Neubuchung einer Belegbuchung mit ausgewiesener Umsatzsteuer: Fehlt
    danach ausgewiesene Steuer des Belegs in der Voranmeldung (``ust_luecken``), warnt
    das Storno (Runde 5, g4w N2; Runde 6, g5w NEU-3/NEU-4: auch bei bezahlter Rechnung
    und mehreren Sätzen, nicht bei Gutschrift und Dublette). Das Storno bleibt erlaubt —
    eine Doppelbuchung ist so aufzuheben, der Grund ist Pflicht und steht im
    Journal."""
    from accounti.belege.dubletten import kopien
    from accounti.db.repository import lade_belege, lade_buchungen_zu

    if b.beleg_id is None or b.steuer_schluessel not in AUSGEWIESENE_UST:
        return []
    beleg = lade_beleg(session, b.beleg_id)
    eigene = lade_buchungen_zu(session, beleg_id=b.beleg_id)
    luecken = ust_luecken(beleg, eigene, plan)
    if luecken and beleg is not None and beleg.belegnummer:
        gleiche = kopien(beleg, lade_belege(session))
        if gleiche:
            andere = [
                x for c in gleiche for x in lade_buchungen_zu(session, beleg_id=c.id)
            ]
            luecken = ust_luecken(beleg, eigene, plan, andere)
    if not luecken:
        return []
    name = (beleg.belegnummer or beleg.dateiname) if beleg else str(b.beleg_id)[:8]
    return [hinweis_14c(name, luecken, "nach dem Storno")]


def storniere(
    session: Session,
    buchung_id: str,
    *,
    grund: str,
    von: str | None = None,
    datum: date | None = None,
    kontenrahmen: Kontenrahmen | None = None,
    buchhaltung: Buchhaltung | None = None,
    elster: ElsterEinstellungen | None = None,
) -> Korrektur:
    """Hebt eine freigegebene Buchung durch eine Gegenbuchung auf (ohne Neubuchung) —
    mit Warnung, wenn ausgewiesene Umsatzsteuer ihres Belegs danach nicht mehr wirksam
    gebucht ist (``_warnung_14c``)."""
    if not grund.strip():
        raise StornoError("Grund für das Storno fehlt", feld="grund")
    b = _lade(session, buchung_id)
    person = aktuelle_person(von)
    k = _storno(
        session,
        b,
        person,
        grund.strip(),
        datum,
        mit_eingerichteten_konten(kontenrahmen or lade_kontenrahmen(), session),
        None,
    )
    k.warnungen.extend(
        _warnung_14c(session, b, kontenplan(session, buchhaltung, elster))
    )
    return k


def korrigiere(
    session: Session,
    buchung_id: str,
    soll: str,
    haben: str,
    *,
    steuer: int | None = None,
    ohne_steuer: bool = False,
    von: str | None = None,
    grund: str | None = None,
    datum: date | None = None,
    kontenrahmen: Kontenrahmen | None = None,
    buchhaltung: Buchhaltung | None = None,
    einstellungen: PruefEinstellungen | None = None,
    elster: ElsterEinstellungen | None = None,
) -> Korrektur:
    """Vorschlag: direkt korrigieren. Freigegeben: Storno und Neubuchung.

    Erhalten bleiben Transaktion, Beleg, Belegposition, Belegnummer, Text und der
    Betrag der Buchung; ``steuer`` rechnet Netto und Steuer aus ihrem Brutto neu.
    Ändert sich das Sachkonto, muss ein vorhandener Steuerschlüssel ausdrücklich
    bestätigt (``steuer``) oder entfernt werden (``ohne_steuer``); eine Kombination,
    die die Prüfregel ``steuerschluessel_konto`` als Fehler einstuft, wird abgelehnt.
    Bei Buchungen mit Beleg entfernt ``ohne_steuer`` die Steuer nur mit ``grund``, und
    die Seiten bleiben, wo der Beleg sie hinstellt (``_richtungswechsel``,
    ``_kennziffer_gedreht``; ``elster``: Funktionskonten und steuerrelevante Konten der
    Voranmeldung).
    """
    b = _lade(session, buchung_id)
    _nicht_storniert(b)
    if (gleich := soll_gleich_haben(soll, haben)) is not None:
        # Fachfunktion: CLI, Queue, /buchungen und REST lehnen gleich ab (Runde 3)
        raise StornoError(gleich, feld="haben")
    kr = mit_eingerichteten_konten(
        kontenrahmen or lade_kontenrahmen((buchhaltung or Buchhaltung()).kontenrahmen),
        session,
    )
    plan = kontenplan(session, buchhaltung, elster) if b.beleg_id else None
    if plan is not None and (kern := _richtungswechsel(b, soll, haben, plan, kr)):
        raise _richtung_fehler(b, kern)
    person = aktuelle_person(von)
    _pruefe_ausdruecklich(b, soll, haben, steuer, ohne_steuer, kr)
    schluessel, netto, steuerbetrag = _steuer(
        b, steuer, ohne_steuer, grund, _beleg_mit_satz(session, b)
    )
    aenderung = {
        "soll_konto": soll,
        "haben_konto": haben,
        "steuer_schluessel": schluessel,
        "betrag_netto": netto,
        "steuer_betrag": steuerbetrag,
        "status": BuchungStatus.KORRIGIERT,
        "confidence": 1.0,
        "geprueft_von": person[:50],
    }
    text = grund or (
        f"Korrektur: {b.soll_konto} an {b.haben_konto} → {soll} an {haben}"
        + (f", Schlüssel {schluessel}" if schluessel != b.steuer_schluessel else "")
    )
    kandidat = b.model_copy(update=aenderung)
    if plan is not None and (kern := _kennziffer_gedreht(session, b, kandidat, plan)):
        raise _richtung_fehler(b, kern)
    _pruefe_steuerschluessel(session, kandidat, buchhaltung, einstellungen)
    if not ist_freigegeben(b):
        if datum is not None:
            raise StornoError(
                "Ein Datum gilt nur für das Storno einer freigegebenen Buchung",
                feld="datum",
                cli="--datum gilt nur für das Storno einer freigegebenen Buchung",
            )
        with journal_kontext(person=person, grund=text):
            neu = aktualisiere_buchung(
                session, str(b.id), b.model_copy(update=aenderung)
            )
            session.flush()
        return Korrektur(b, neu, warnungen=_warnung_selbst(b, ohne_steuer))
    if all(
        getattr(b, k) == v
        for k, v in aenderung.items()
        if k
        in (
            "soll_konto",
            "haben_konto",
            "steuer_schluessel",
            "betrag_netto",
            "steuer_betrag",
        )
    ):
        raise StornoError(f"Die Korrektur ändert an Buchung {_kurz(b)} nichts")
    neu = b.model_copy(update={**aenderung, "id": uuid4(), "storniert_durch": None})
    k = _storno(session, b, person, text, datum, kr, neu)
    k.warnungen.extend(_warnung_selbst(b, ohne_steuer))
    return k


def _beleg_mit_satz(session: Session, b: Buchungssatz) -> bool:
    """Nennt der Beleg der Buchung einen Steuersatz (ihre bzw. irgendeine Position)?"""
    if b.beleg_id is None:
        return True
    beleg = lade_beleg(session, b.beleg_id)
    if beleg is None:
        return True
    positionen = [
        p
        for p in beleg.positionen
        if b.beleg_position_id is None or p.id == b.beleg_position_id
    ]
    return any(p.steuersatz is not None for p in positionen)


def _warnung_selbst(b: Buchungssatz, ohne_steuer: bool) -> list[str]:
    """--ohne-steuer bei § 13b bzw. ig. Erwerb: nur richtig ohne einen solchen Fall."""
    if not ohne_steuer or b.steuer_schluessel not in SELBST_BERECHNET:
        return []
    return [
        f"Steuerschuld und Vorsteuer (Schlüssel {b.steuer_schluessel}) entfernt — "
        "richtig nur, wenn tatsächlich kein § 13b-Fall bzw. kein ig. Erwerb vorliegt; "
        f"{HINWEIS_SELBST_BERECHNET}"
    ]


def _pruefe_steuerschluessel(
    session: Session,
    kandidat: Buchungssatz,
    buchhaltung: Buchhaltung | None,
    einstellungen: PruefEinstellungen | None,
) -> None:
    """Die Prüfregel ``steuerschluessel_konto`` auf die korrigierte Buchung — mit der
    Kontenrahmen-Datei der Konfiguration (``pruefung.kontenrahmen_datei``)."""
    from accounti.models.pruefung import Schwere
    from accounti.pruefung.regeln.richtigkeit import (
        automatikkonten,
        steuerschluessel_probleme,
    )

    buchhaltung = buchhaltung or Buchhaltung()
    if kandidat.steuer_schluessel is None and not kandidat.steuer_betrag:
        automatik = automatikkonten(buchhaltung, einstellungen)
        for konto in (kandidat.soll_konto, kandidat.haben_konto):
            if konto in automatik:
                raise StornoError(
                    f"Konto {konto} ist DATEV-Automatikkonto (Schlüssel "
                    f"{automatik[konto]}) — ohne Schlüssel rechnete DATEV trotzdem "
                    f"Steuer heraus: Steuerschlüssel {automatik[konto]} wählen oder "
                    "ein Konto ohne Automatik",
                    feld="steuer",
                    cli=f"Konto {konto} ist DATEV-Automatikkonto (Schlüssel "
                    f"{automatik[konto]}) — ohne Schlüssel rechnete DATEV trotzdem "
                    f"Steuer heraus: --steuer {automatik[konto]} angeben oder ein "
                    "Konto ohne Automatik wählen",
                )
    fehler = [
        text
        for schwere, text in steuerschluessel_probleme(
            session, kandidat, buchhaltung, einstellungen
        )
        if schwere is Schwere.FEHLER
    ]
    if fehler:
        kopf = (
            f"Korrektur {kandidat.soll_konto} an {kandidat.haben_konto} mit "
            f"Schlüssel {kandidat.steuer_schluessel}: " + "; ".join(fehler) + " — "
        )
        raise StornoError(
            kopf + "anderen Steuerschlüssel wählen oder „ohne Steuer“",
            feld="steuer",
            cli=kopf + "anderen Schlüssel mit --steuer angeben oder --ohne-steuer",
        )


def steuer_befunde(
    session: Session,
    b: Buchungssatz,
    buchhaltung: Buchhaltung | None = None,
    einstellungen: PruefEinstellungen | None = None,
) -> list[tuple[Any, str]]:
    """Was die Prüfregel ``steuerschluessel_konto`` an einer Buchung findet — dazu
    ein DATEV-Automatikkonto ohne Schlüssel (Fehler), wie ``korrigiere`` es
    ablehnt. ``(Schwere, Text)``; für die Freigabe in der Queue und die Anzeige."""
    from accounti.models.pruefung import Schwere
    from accounti.pruefung.regeln.richtigkeit import (
        automatikkonten,
        steuerschluessel_probleme,
    )

    buchhaltung = buchhaltung or Buchhaltung()
    befunde: list[tuple[Any, str]] = []
    if (gleich := soll_gleich_haben(b.soll_konto, b.haben_konto)) is not None:
        # Prüfregel soll_gleich_haben: ein Altfall wird nicht freigegeben (gw2-merge B3)
        befunde.append((Schwere.FEHLER, gleich))
    if b.steuer_schluessel is None and not b.steuer_betrag:
        automatik = automatikkonten(buchhaltung, einstellungen)
        for konto in (b.soll_konto, b.haben_konto):
            if konto in automatik:
                befunde.append(
                    (
                        Schwere.FEHLER,
                        f"Konto {konto} ist DATEV-Automatikkonto (Schlüssel "
                        f"{automatik[konto]}) — ohne Schlüssel rechnete DATEV "
                        "trotzdem Steuer heraus",
                    )
                )
    befunde += steuerschluessel_probleme(session, b, buchhaltung, einstellungen)
    return befunde


def freigeben(
    session: Session, buchung_id: str, von: str | None = None
) -> tuple[Buchungssatz, bool]:
    """Vorschlag oder automatische Buchung → ``geprueft``; (Buchung, geändert?)."""
    b = _lade(session, buchung_id)
    if b.status in VORSCHLAG or b.status is BuchungStatus.AUTO_GEBUCHT:
        person = aktuelle_person(von)
        with journal_kontext(person=person):
            neu = setze_status(
                session, str(b.id), BuchungStatus.GEPRUEFT, geprueft_von=person[:50]
            )
            session.flush()
        return neu, True
    return b, False


def markiere_exportiert(
    session: Session,
    buchungen: list[Buchungssatz],
    datei: Path | None,
    art: str,
) -> tuple[int, int]:
    """Freigegebene, exportierte Buchungen → ``exportiert``; Journal ``export``.

    Buchungen in abgeschlossenen Zeiträumen bleiben, wie sie sind (die Sperre nimmt
    keinen Statuswechsel an); sie stehen im Journaleintrag. Ergebnis: (markiert,
    gesperrt). Die Zeilen werden blockweise geladen und in einem Flush geschrieben —
    nicht je Buchung (jeder Zwischen-Flush kostete Sperrabfragen und Journal).
    """
    verbindung = session.connection()
    sperren: dict[str, Any] = {}  # gesperrte Jahre/Monate, einmal gelesen
    offen, gesperrt_ids = [], []
    for b in buchungen:
        if b.status not in FREIGEGEBEN - {BuchungStatus.EXPORTIERT}:
            continue
        if gesperrt(verbindung, b.datum, sperren):
            gesperrt_ids.append(str(b.id))
        else:
            offen.append(str(b.id))
    markiert = []
    with session.no_autoflush:
        for start in range(0, len(offen), _JE_ABFRAGE):
            teil = offen[start : start + _JE_ABFRAGE]
            for zeile in session.query(BuchungssatzRow).filter(
                BuchungssatzRow.id.in_(teil)
            ):
                zeile.status = BuchungStatus.EXPORTIERT.value
                markiert.append(zeile.id)
    session.flush()
    inhalt = datei.read_bytes() if datei is not None and datei.is_file() else b""
    schreibe(
        session,
        "export",
        "export",
        art,
        nachher={
            "datei": datei.name if datei is not None else None,
            "sha256": hashlib.sha256(inhalt).hexdigest() if inhalt else None,
            "anzahl": len(buchungen),
            "markiert": sorted(markiert),
            "gesperrt": sorted(gesperrt_ids),
        },
    )
    return len(markiert), len(gesperrt_ids)
