"""Kreditkarten — eigenes Konto, Abrechnung, Abgleich der Sammelbelastung.

Eine Kreditkarte ist ein eigenes Bankkonto mit eigenem Sachkonto. Ihre Umsätze
kommen über einen Provider (Datei, später PSD2) oder aus der PDF-Abrechnung, die die
Belegerfassung schon in Einzelumsätze zerlegt hat (Provider ``abrechnung``).

Eine Abrechnung fasst die Einzelumsätze eines Zeitraums zusammen. Die
Sammelbelastung auf dem Girokonto muss centgenau ihrer Summe entsprechen; jede
Abweichung ist ein **Befund** — gebucht wird dann die volle Belastung zur Prüfung,
nie ein Rundungsposten über die Differenz.

Gebucht wird so, dass jede Kontozeile genau einmal auf ihrem Finanzkonto steht:
PDF-Karten kennen keine Ausgleichszeile, die Sammelbelastung wird direkt
„Kreditkarte an Bank“. Karten mit Abruf zeigen die Begleichung auch auf dem
Kartenkonto; dann laufen beide Seiten über Geldtransit (SKR03 1360, SKR04 1460):
„Geldtransit an Bank“ und „Kreditkarte an Geldtransit“ — die Ausgleichszeile
automatisch nur, wenn eine gleich hohe Sammelbelastung der Karte über Geldtransit
gebucht ist. Die Einzelumsätze kontiert ``classify`` gegen das Sachkonto der Karte.

Streng vor großzügig, auch über mehrere Läufe: Eine Zuordnung mit Abweichung ist
vorläufig (Buchung zur Prüfung). Solange niemand sie bestätigt hat, wird sie bei
jedem Lauf neu bewertet — kommt später ein centgenauer Treffer oder ein zweiter
Kandidat, wird sie gelöst. Bei Karten mit Abruf kommen später gelieferte
Kartenumsätze in die offene Abrechnung ihres Zeitraums (oder die nächste).
PDF-Abrechnungen aus der Zeit vor der Karte übernimmt der Lauf nicht von selbst,
wenn ihre Sammelbelastung schon anders gebucht ist oder fehlt.
"""

from __future__ import annotations

import calendar
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.anzeige import betrag_de, datum_de
from accounti.bank.dubletten import mit_schluessel
from accounti.bank.einstellungen import KreditkartenEinstellungen
from accounti.bank.provider import BANK_PROVIDER
from accounti.db.repo_bank import (
    abgelehnte_belastungen,
    abgerechnete_transaktion_ids,
    aktualisiere_abrechnung,
    ergaenze_abrechnung,
    lade_abrechnungen,
    lade_kreditkarten,
    lade_transaktionen_nach_schluessel,
    lehne_belastung_ab,
    loesche_buchung,
    speichere_abrechnung,
    speichere_kreditkarte,
)
from accounti.db.repository import (
    aktualisiere_buchung,
    gebuchte_transaktion_ids,
    lade_bankkonten,
    lade_bankkonto,
    lade_belege,
    lade_buchungen,
    lade_transaktionen,
    speichere_bankkonto,
    speichere_buchung,
)
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Bankkonto,
    Beleg,
    Belegart,
    BelegStatus,
    Buchungssatz,
    BuchungStatus,
    Transaktion,
    TransaktionQuelle,
)
from accounti.models.bank import (
    AbrechnungStatus,
    Kreditkarte,
    Kreditkartenabrechnung,
)

PDF_PROVIDER = "abrechnung"
# so legt der Positionssplit (belege/positionen.py) Kartenumsätze an
_POSITION = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})\s+(.+)$")


class KreditkartenError(RuntimeError):
    """Einrichtung, Übernahme oder Abrechnung ist so nicht möglich."""


# --- Einrichtung ------------------------------------------------------------------


def richte_karte_ein(
    session: Session,
    *,
    girokonto: str,
    konto: str | None = None,
    kennung: str | None = None,
    bezeichnung: str | None = None,
    sachkonto: str | None = None,
    provider: str = PDF_PROVIDER,
    einstellungen: dict[str, str] | None = None,
    endziffern: str | None = None,
    muster: str | None = None,
    abrechnungstag: int | None = None,
) -> tuple[Kreditkarte, Bankkonto]:
    """Kreditkarte einrichten: neues Kartenkonto oder ein vorhandenes Konto."""
    try:
        giro = lade_bankkonto(session, girokonto)
    except ValueError as fehler:
        raise KreditkartenError(f"Girokonto: {fehler}") from fehler
    if endziffern is not None and not re.fullmatch(r"\d{2,4}", endziffern):
        raise KreditkartenError("Endziffern: zwei bis vier Ziffern der Kartennummer")
    if muster:
        try:
            re.compile(muster)
        except re.error as fehler:
            raise KreditkartenError(
                f"Muster ist kein regulärer Ausdruck: {fehler}"
            ) from None
    if konto is not None:
        try:
            karte_konto = lade_bankkonto(session, konto)
        except ValueError as fehler:
            raise KreditkartenError(str(fehler)) from fehler
    else:
        karte_konto = _neues_kartenkonto(
            kennung, bezeichnung, sachkonto, provider, einstellungen or {}
        )
    if karte_konto.iban == giro.iban:
        raise KreditkartenError("Die Karte kann nicht ihr eigenes Girokonto sein")
    if karte_konto.sachkonto == giro.sachkonto:
        msg = (
            f"Die Karte braucht ein eigenes Sachkonto (nicht {giro.sachkonto} wie das "
            "Girokonto)"
        )
        raise KreditkartenError(msg)
    if konto is None:
        try:
            speichere_bankkonto(session, karte_konto)
        except ValueError as fehler:
            raise KreditkartenError(str(fehler)) from fehler
    karte = Kreditkarte(
        bankkonto_id=karte_konto.id,
        girokonto_id=giro.id,
        endziffern=endziffern,
        muster=muster or None,
        abrechnungstag=abrechnungstag,
    )
    try:
        speichere_kreditkarte(session, karte)
    except ValueError as fehler:
        raise KreditkartenError(str(fehler)) from fehler
    return karte, karte_konto


def _neues_kartenkonto(
    kennung: str | None,
    bezeichnung: str | None,
    sachkonto: str | None,
    provider: str,
    einstellungen: dict[str, str],
) -> Bankkonto:
    fehlend = [
        n
        for n, w in (
            ("Kennung", kennung),
            ("Bezeichnung", bezeichnung),
            ("Sachkonto", sachkonto),
        )
        if not w
    ]
    if fehlend:
        msg = f"Für ein neues Kartenkonto fehlt: {', '.join(fehlend)}"
        raise KreditkartenError(msg)
    klasse = BANK_PROVIDER.get(provider)
    if klasse is None:
        msg = (
            f"Unbekannter Provider '{provider}' (verfügbar: {', '.join(BANK_PROVIDER)})"
        )
        raise KreditkartenError(msg)
    if klasse.geheime_felder:
        msg = (
            f"Provider '{provider}' braucht Zugangsdaten — das Konto zuerst mit "
            "'accounti bank verbinde' bzw. 'accounti fints einrichten' anlegen, "
            "dann 'accounti kreditkarte einrichten --konto …'"
        )
        raise KreditkartenError(msg)
    unbekannt = sorted(set(einstellungen) - set(klasse.felder))
    if unbekannt:
        msg = f"Einstellung {', '.join(unbekannt)} gibt es bei {provider} nicht"
        raise KreditkartenError(msg)
    return Bankkonto(
        iban=re.sub(r"\s", "", str(kennung)).upper(),
        bezeichnung=str(bezeichnung),
        sachkonto=str(sachkonto),
        provider=provider,
        einstellungen=einstellungen,
    )


# --- Abrechnungen -----------------------------------------------------------------


def ist_kartenabrechnung(beleg: Beleg) -> bool:
    """Kontoauszug, dessen Positionen Kartenumsätze sind (Datum + Text)."""
    return (
        beleg.belegart is Belegart.KONTOAUSZUG
        and bool(beleg.positionen)
        and all(_POSITION.match(p.bezeichnung) for p in beleg.positionen)
    )


@dataclass(frozen=True)
class _Kartenumsatz:
    datum: date
    text: str
    betrag: Decimal
    bezeichnung: str


def _kartenumsaetze(beleg: Beleg) -> list[_Kartenumsatz]:
    umsaetze = []
    for p in beleg.positionen:
        m = _POSITION.match(p.bezeichnung)
        if m is None:
            continue
        try:
            datum = date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            continue
        umsaetze.append(_Kartenumsatz(datum, m[4].strip(), p.netto, p.bezeichnung))
    return umsaetze


def _ist_ausgleich(tx: Transaktion, einst: KreditkartenEinstellungen) -> bool:
    """Begleichung der Vorperiode auf dem Kartenkonto — kein Einzelumsatz."""
    text = f"{tx.verwendungszweck} {tx.gegenkonto_name or ''}"
    return tx.betrag > 0 and einst.ist_ausgleich(text)


def _finde_beleg(session: Session, schluessel: str) -> Beleg:
    treffer = [
        b for b in lade_belege(session) if str(b.id).startswith(schluessel.lower())
    ]
    if len(treffer) != 1:
        msg = (
            f"Kein Beleg '{schluessel}'"
            if not treffer
            else f"'{schluessel}' ist nicht eindeutig"
        )
        raise KreditkartenError(msg)
    return treffer[0]


@dataclass
class _Karte:
    karte: Kreditkarte
    konto: Bankkonto
    giro: Bankkonto

    @property
    def direkt(self) -> bool:
        return self.konto.provider == PDF_PROVIDER

    def soll(self, geldtransit: str) -> str:
        """Gegenkonto der Sammelbelastung: Kartenkonto (PDF) oder Geldtransit."""
        return self.konto.sachkonto if self.direkt else geldtransit

    def belastet(self, tx: Transaktion, einst: KreditkartenEinstellungen) -> bool:
        """Ist ``tx`` eine Sammelbelastung dieser Karte auf ihrem Girokonto?"""
        if tx.bankkonto_id != self.giro.id or tx.betrag >= 0:
            return False
        text = f"{tx.verwendungszweck} {tx.gegenkonto_name or ''}"
        if self.karte.muster:  # eigenes Muster: volle Kontrolle, keine Ausnahme
            passt = re.search(self.karte.muster, text, re.IGNORECASE) is not None
        else:
            passt = einst.ist_belastung(text)
        endziffern = self.karte.endziffern
        return passt and (not endziffern or endziffern in re.sub(r"\s", "", text))


def _mit_konten(session: Session, karte: Kreditkarte) -> _Karte:
    konten = {k.id: k for k in lade_bankkonten(session)}
    if karte.bankkonto_id not in konten or karte.girokonto_id not in konten:
        raise KreditkartenError("Karten- oder Girokonto der Karte fehlt")
    return _Karte(karte, konten[karte.bankkonto_id], konten[karte.girokonto_id])


def _buchungen_je_umsatz(session: Session) -> dict[UUID, list[Buchungssatz]]:
    je: dict[UUID, list[Buchungssatz]] = {}
    for b in lade_buchungen(session):
        if b.transaktion_id is not None:
            je.setdefault(b.transaktion_id, []).append(b)
    return je


@dataclass
class Uebernahme:
    abrechnung: Kreditkartenabrechnung
    neu: int
    doppelt: int
    ausgleich: int  # Begleichung der Vorperiode, nicht übernommen
    warnungen: list[str] = field(default_factory=list)


@dataclass
class _Vorpruefung:
    """Was vor der Übernahme einer PDF-Abrechnung auf dem Girokonto steht."""

    stichtag: date
    summe: Decimal
    schon_gebucht: list[tuple[Transaktion, list[str]]]  # Belastung, Soll-Konten
    offene_belastung: bool  # eine noch ungebuchte Belastung im Fenster
    vor_einrichtung: bool  # Stichtag vor der Einrichtung der Karte

    def gebucht_text(self) -> str:
        tx, konten = self.schon_gebucht[0]
        return (
            f"Sammelbelastung {betrag_de(tx.betrag)} € vom {datum_de(tx.datum)} ist "
            f"schon gebucht (Soll {', '.join(konten)}) — die Einzelumsätze buchten "
            "den Aufwand doppelt"
        )


def _umsaetze_aus_beleg(
    beleg: Beleg, einst: KreditkartenEinstellungen
) -> tuple[list[Transaktion], list[Transaktion]]:
    """(alle Zeilen, Einzelumsätze ohne Ausgleichszeilen) der PDF-Abrechnung."""
    umsaetze = [
        Transaktion(
            datum=u.datum,
            betrag=u.betrag,
            verwendungszweck=u.text[:500],
            quelle=TransaktionQuelle.BANK,
            rohtext=f"{beleg.dateiname}: {u.bezeichnung} {u.betrag}"[:2000],
        )
        for u in _kartenumsaetze(beleg)
    ]
    return umsaetze, [t for t in umsaetze if not _ist_ausgleich(t, einst)]


def _pruefe_vorher(
    session: Session,
    k: _Karte,
    beleg: Beleg,
    einzeln: list[Transaktion],
    einst: KreditkartenEinstellungen,
) -> _Vorpruefung:
    """Steht die Sammelbelastung der Abrechnung schon anders gebucht da (etwa per
    Regel als Aufwand, bevor es die Karte gab), buchten die Einzelumsätze den
    Aufwand ein zweites Mal."""
    stichtag = beleg.belegdatum or max(t.datum for t in einzeln)
    summe = sum((t.betrag for t in einzeln), Decimal("0"))
    fenster = timedelta(days=einst.belastung_fenster_tage)
    zugeordnet = {a.belastung_id for a in lade_abrechnungen(session) if a.belastung_id}
    buchungen = _buchungen_je_umsatz(session)
    erlaubt = {
        k.konto.sachkonto,
        einst.geldtransit("SKR03"),
        einst.geldtransit("SKR04"),
    }
    kandidaten = [
        t
        for t in lade_transaktionen(session)
        if t.id not in zugeordnet
        and k.belastet(t, einst)
        and stichtag <= t.datum <= stichtag + fenster
    ]
    schon = [
        (t, sorted({b.soll_konto for b in buchungen[t.id]}))
        for t in kandidaten
        if t.betrag == summe
        and t.id in buchungen
        and not any(b.soll_konto in erlaubt for b in buchungen[t.id])
    ]
    return _Vorpruefung(
        stichtag=stichtag,
        summe=summe,
        schon_gebucht=schon,
        offene_belastung=any(t.id not in buchungen for t in kandidaten),
        vor_einrichtung=stichtag < k.karte.erstellt_am.date(),
    )


def uebernimm_abrechnung(
    session: Session,
    beleg_schluessel: str,
    karte: Kreditkarte,
    einst: KreditkartenEinstellungen,
    trotzdem: bool = False,
) -> Uebernahme:
    """PDF-Abrechnung (erfasster Beleg) → Umsätze am Kartenkonto + Abrechnung.

    Ist die Sammelbelastung schon anders gebucht, nur mit ``trotzdem`` — sonst
    stünde der Aufwand doppelt in den Büchern."""
    beleg = _finde_beleg(session, beleg_schluessel)
    if not ist_kartenabrechnung(beleg):
        msg = (
            f"Beleg {str(beleg.id)[:8]} ist keine Kreditkartenabrechnung mit "
            f"Einzelumsätzen (Belegart {beleg.belegart.value})"
        )
        raise KreditkartenError(msg)
    if any(a.beleg_id == beleg.id for a in lade_abrechnungen(session)):
        raise KreditkartenError(f"Beleg {str(beleg.id)[:8]} ist schon übernommen")
    k = _mit_konten(session, karte)
    konto = k.konto
    umsaetze, einzeln = _umsaetze_aus_beleg(beleg, einst)
    if not einzeln:
        raise KreditkartenError("Die Abrechnung enthält keine Einzelumsätze")
    vor = _pruefe_vorher(session, k, beleg, einzeln, einst)
    warnungen = []
    if vor.schon_gebucht:
        if not trotzdem:
            msg = (
                f"{vor.gebucht_text()}; erst die Buchung prüfen, dann mit --trotzdem "
                "übernehmen"
            )
            raise KreditkartenError(msg)
        warnungen.append(vor.gebucht_text())
    elif vor.vor_einrichtung and not vor.offene_belastung:
        warnungen.append(
            f"Abrechnung zum {datum_de(vor.stichtag)} liegt vor der Einrichtung der "
            "Karte und hat keine offene Sammelbelastung — prüfen, ob ihre Umsätze "
            "schon gebucht sind"
        )
    from accounti.bank.lauf import speichere_neue  # vermeidet einen Importkreis

    neu, doppelt = speichere_neue(session, einzeln, konto.iban, konto)
    schluessel = [
        t.dublettenschluessel or "" for t in mit_schluessel(einzeln, konto.iban)
    ]
    gespeichert = lade_transaktionen_nach_schluessel(session, schluessel)
    abrechnung = Kreditkartenabrechnung(
        kreditkarte_id=karte.id,
        stichtag=vor.stichtag,
        von=min(t.datum for t in einzeln),
        beleg_id=beleg.id,
        summe=vor.summe,
        anzahl=len(einzeln),
    )
    try:
        speichere_abrechnung(
            session, abrechnung, [gespeichert[s].id for s in schluessel]
        )
    except ValueError as fehler:
        raise KreditkartenError(str(fehler)) from fehler
    return Uebernahme(abrechnung, neu, doppelt, len(umsaetze) - len(einzeln), warnungen)


def _kartenbeginn(bisher: list[Kreditkartenabrechnung]) -> date | None:
    """Beginn der ersten Abrechnung — ältere Umsätze gehören zu keiner."""
    erste = min(bisher, key=lambda a: a.stichtag, default=None)
    return erste.von if erste is not None else None


def bilde_abrechnung(
    session: Session,
    karte: Kreditkarte,
    stichtag: date,
    einst: KreditkartenEinstellungen,
    von: date | None = None,
) -> Kreditkartenabrechnung | None:
    """Abrechnung aus den Umsätzen des Kartenkontos (Karten mit Abruf).

    Dazu gehören alle noch nicht abgerechneten Umsätze bis zum Stichtag, ohne
    Ausgleichszeilen — auch spät gelieferte aus einem früheren Zeitraum, dessen
    Abrechnung schon abgeschlossen ist (nicht aber Umsätze vor der ersten
    Abrechnung). Mit ``von`` nur Umsätze ab diesem Tag. ``None``, wenn es keine gibt.
    """
    bisher = lade_abrechnungen(session, kreditkarte_id=karte.id)
    letzte = max((a.stichtag for a in bisher), default=None)
    if letzte is not None and stichtag <= letzte:
        msg = f"Stichtag muss nach der letzten Abrechnung ({datum_de(letzte)}) liegen"
        raise KreditkartenError(msg)
    beginn = von or (letzte + timedelta(days=1) if letzte else None)
    untergrenze = von or _kartenbeginn(bisher)
    abgerechnet = abgerechnete_transaktion_ids(session)
    umsaetze = [
        t
        for t in lade_transaktionen(session)
        if t.bankkonto_id == karte.bankkonto_id
        and t.id not in abgerechnet
        and t.datum <= stichtag
        and (untergrenze is None or t.datum >= untergrenze)
        and not _ist_ausgleich(t, einst)
    ]
    if not umsaetze:
        return None
    abrechnung = Kreditkartenabrechnung(
        kreditkarte_id=karte.id,
        stichtag=stichtag,
        von=beginn,
        summe=sum((t.betrag for t in umsaetze), Decimal("0")),
        anzahl=len(umsaetze),
    )
    speichere_abrechnung(session, abrechnung, [t.id for t in umsaetze])
    return abrechnung


def letzter_stichtag(datum: date, tag: int) -> date:
    """Letzter Abrechnungsstichtag am oder vor ``datum`` (Monatsende bei Tag 31)."""

    def im_monat(jahr: int, monat: int) -> date:
        return date(jahr, monat, min(tag, calendar.monthrange(jahr, monat)[1]))

    stichtag = im_monat(datum.year, datum.month)
    if stichtag <= datum:
        return stichtag
    vormonat = datum.replace(day=1) - timedelta(days=1)
    return im_monat(vormonat.year, vormonat.month)


# --- Abgleich der Sammelbelastung -----------------------------------------------------


@dataclass
class Kartenabgleich:
    uebernommen: list[Uebernahme] = field(default_factory=list)
    abgeglichen: list[Kreditkartenabrechnung] = field(default_factory=list)
    abweichungen: list[Kreditkartenabrechnung] = field(default_factory=list)
    ohne_abrechnung: list[Transaktion] = field(default_factory=list)
    mehrdeutig: list[Transaktion] = field(default_factory=list)
    geloest: list[Transaktion] = field(default_factory=list)  # vorläufig, überholt
    nachgetragen: int = 0  # spät gelieferte Kartenumsätze in offenen Abrechnungen
    ausgleich_gebucht: int = 0
    ausgleich_ohne_belastung: list[Transaktion] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)
    namen: dict[UUID, str] = field(default_factory=dict)  # Karte → Bezeichnung


# noch nicht bestätigt: der Abgleich darf sie lösen
_VORLAEUFIG = frozenset({BuchungStatus.ZUR_PRUEFUNG, BuchungStatus.ENTWURF})
_STATUS_TEXT = {
    BuchungStatus.AUTO_GEBUCHT: "automatisch gebucht und freigegeben",
    BuchungStatus.GEPRUEFT: "geprüft",
    BuchungStatus.KORRIGIERT: "korrigiert",
    BuchungStatus.EXPORTIERT: "exportiert",
}

_Ziel = tuple[Transaktion, _Karte, Kreditkartenabrechnung, AbrechnungStatus]


class _Abgleich:
    def __init__(
        self,
        session: Session,
        einstellungen: Buchhaltung,
        einst: KreditkartenEinstellungen,
    ) -> None:
        self.session = session
        self.einst = einst
        self.geldtransit = einst.geldtransit(einstellungen.kontenrahmen)
        self.fenster = timedelta(days=einst.belastung_fenster_tage)
        konten = {k.id: k for k in lade_bankkonten(session)}
        self.karten = [
            _Karte(k, konten[k.bankkonto_id], konten[k.girokonto_id])
            for k in lade_kreditkarten(session)
            if k.bankkonto_id in konten and k.girokonto_id in konten
        ]
        self.karte_von = {k.karte.id: k for k in self.karten}
        self.abgelehnt = abgelehnte_belastungen(session)
        self.nachgetragen: set[UUID] = set()
        self.ergebnis = Kartenabgleich(
            namen={k.karte.id: k.konto.bezeichnung for k in self.karten}
        )

    def lauf(self) -> Kartenabgleich:
        if not self.karten:
            return self.ergebnis
        self._pdf_uebernehmen()
        self._nachtragen()
        self._abrechnungen_bilden()
        self._sammelbelastungen()
        self._ausgleichszeilen()
        return self.ergebnis

    # --- Hilfen -------------------------------------------------------------

    def _eigene(
        self, k: _Karte, tx: Transaktion, buchungen: dict[UUID, list[Buchungssatz]]
    ) -> list[Buchungssatz]:
        """Buchungen, die der Kartenabgleich für diese Belastung angelegt hat."""
        haben = tx.sachkonto or k.giro.sachkonto
        soll = k.soll(self.geldtransit)
        return [
            b
            for b in buchungen.get(tx.id, [])
            if b.soll_konto == soll and b.haben_konto == haben
        ]

    def _vorlaeufig(
        self,
        a: Kreditkartenabrechnung,
        buchungen: dict[UUID, list[Buchungssatz]],
        transaktionen: dict[UUID, Transaktion],
    ) -> bool:
        """Zuordnung mit Abweichung, die noch niemand bestätigt hat."""
        if a.status is not AbrechnungStatus.ABWEICHUNG or a.belastung_id is None:
            return False
        k = self.karte_von.get(a.kreditkarte_id)
        tx = transaktionen.get(a.belastung_id)
        if k is None or tx is None:
            return False
        eigene = self._eigene(k, tx, buchungen)
        if any(b.status not in _VORLAEUFIG for b in eigene):
            return False  # bestätigt, korrigiert oder exportiert
        # ohne eigene Buchung („schon anders gebucht“): nur eine Differenz ist offen
        return bool(eigene) or tx.betrag != a.summe or a.id in self.nachgetragen

    def _loese(
        self, a: Kreditkartenabrechnung, transaktionen: dict[UUID, Transaktion]
    ) -> Transaktion:
        """Zuordnung aufheben; die vorläufige Buchung der Belastung entfällt."""
        k = self.karte_von[a.kreditkarte_id]
        tx = transaktionen[a.belastung_id] if a.belastung_id else None
        if tx is None:
            raise KreditkartenError(f"Abrechnung {str(a.id)[:8]} hat keine Belastung")
        for b in self._eigene(k, tx, _buchungen_je_umsatz(self.session)):
            loesche_buchung(self.session, b.id)
        aktualisiere_abrechnung(
            self.session,
            a.model_copy(
                update={
                    "belastung_id": None,
                    "belastung_betrag": None,
                    "status": AbrechnungStatus.OFFEN,
                    "befund": None,
                }
            ),
        )
        return tx

    # --- Schritte -------------------------------------------------------------

    def _pdf_uebernehmen(self) -> None:
        uebernommen = {a.beleg_id for a in lade_abrechnungen(self.session)}
        offen = [
            b
            for b in lade_belege(self.session, status={BelegStatus.ERFASST})
            if b.id not in uebernommen and ist_kartenabrechnung(b)
        ]
        if not offen:
            return
        # von selbst nur, wenn es genau eine Karte gibt und sie per PDF abrechnet —
        # die PDF einer Karte mit Abruf liegt oft auch in den Belegen
        pdf_karten = [k for k in self.karten if k.direkt]
        if len(self.karten) != 1 or len(pdf_karten) != 1:
            self.ergebnis.hinweise.append(
                f"{len(offen)} Kreditkartenabrechnung(en) noch nicht übernommen — "
                "accounti kreditkarte uebernehmen <BELEG> --karte <KENNUNG>"
            )
            return
        k = pdf_karten[0]
        alt = []
        for beleg in offen:
            kurz = str(beleg.id)[:8]
            _, einzeln = _umsaetze_aus_beleg(beleg, self.einst)
            if einzeln:  # ohne Einzelumsätze meldet die Übernahme den Grund
                vor = _pruefe_vorher(self.session, k, beleg, einzeln, self.einst)
                if vor.schon_gebucht:
                    self.ergebnis.hinweise.append(
                        f"Beleg {kurz}: {vor.gebucht_text()} — nicht übernommen; "
                        "Buchung prüfen, dann accounti kreditkarte uebernehmen "
                        f"{kurz} --trotzdem"
                    )
                    continue
                if vor.vor_einrichtung and not vor.offene_belastung:
                    alt.append(kurz)
                    continue
            try:
                self.ergebnis.uebernommen.append(
                    uebernimm_abrechnung(
                        self.session, str(beleg.id), k.karte, self.einst
                    )
                )
            except KreditkartenError as fehler:
                self.ergebnis.hinweise.append(f"Beleg {kurz}: {fehler}")
        if alt:
            self.ergebnis.hinweise.append(
                f"{len(alt)} Kreditkartenabrechnung(en) vor der Einrichtung der Karte "
                f"ohne offene Sammelbelastung nicht von selbst übernommen "
                f"({', '.join(alt)}) — waren ihre Umsätze schon gebucht? Von Hand: "
                "accounti kreditkarte uebernehmen <BELEG>"
            )

    def _nachtragen(self) -> None:
        """Karten mit Abruf: spät gelieferte Umsätze in die offene Abrechnung ihres
        Zeitraums (ist sie schon abgeschlossen, in die nächste offene)."""
        buchungen = _buchungen_je_umsatz(self.session)
        transaktionen = {t.id: t for t in lade_transaktionen(self.session)}
        abgerechnet = abgerechnete_transaktion_ids(self.session)
        for k in self.karten:
            if k.direkt:
                continue
            bisher = lade_abrechnungen(self.session, kreditkarte_id=k.karte.id)
            offen = sorted(
                (
                    a
                    for a in bisher
                    if a.beleg_id is None
                    and (
                        a.belastung_id is None
                        or self._vorlaeufig(a, buchungen, transaktionen)
                    )
                ),
                key=lambda a: a.stichtag,
            )
            beginn = _kartenbeginn(bisher)
            dazu: dict[UUID, list[Transaktion]] = {}
            for t in sorted(transaktionen.values(), key=lambda t: (t.datum, str(t.id))):
                if (
                    t.bankkonto_id != k.konto.id
                    or t.id in abgerechnet
                    or _ist_ausgleich(t, self.einst)
                    or (beginn is not None and t.datum < beginn)
                ):
                    continue
                ziel = next((a for a in offen if a.stichtag >= t.datum), None)
                if ziel is not None:
                    dazu.setdefault(ziel.id, []).append(t)
            for a in offen:
                neu = dazu.get(a.id)
                if not neu:
                    continue
                ergaenze_abrechnung(
                    self.session,
                    a.model_copy(
                        update={
                            "summe": a.summe
                            + sum((t.betrag for t in neu), Decimal("0")),
                            "anzahl": a.anzahl + len(neu),
                        }
                    ),
                    [t.id for t in neu],
                )
                self.nachgetragen.add(a.id)
                self.ergebnis.nachgetragen += len(neu)

    def _offene(
        self,
        alle: list[Kreditkartenabrechnung],
        buchungen: dict[UUID, list[Buchungssatz]],
        transaktionen: dict[UUID, Transaktion],
    ) -> list[Kreditkartenabrechnung]:
        """Abrechnungen ohne Belastung oder mit vorläufiger Zuordnung."""
        return [
            a
            for a in alle
            if a.kreditkarte_id in self.karte_von
            and (
                a.belastung_id is None or self._vorlaeufig(a, buchungen, transaktionen)
            )
        ]

    def _im_fenster(self, a: Kreditkartenabrechnung, tx: Transaktion) -> bool:
        return a.stichtag <= tx.datum <= a.stichtag + self.fenster

    def _kandidaten(
        self, transaktionen: dict[UUID, Transaktion], fest: set[UUID]
    ) -> list[Transaktion]:
        return sorted(
            (
                t
                for t in transaktionen.values()
                if t.id not in fest
                and any(k.belastet(t, self.einst) for k in self.karten)
            ),
            key=lambda t: (t.datum, str(t.id)),
        )

    def _abrechnungen_bilden(self) -> None:
        """Karten mit Abruf: Abrechnung am Abrechnungstag, sobald eine Belastung
        im Fenster kommt und keine offene Abrechnung dafür da ist."""
        buchungen = _buchungen_je_umsatz(self.session)
        transaktionen = {t.id: t for t in lade_transaktionen(self.session)}
        alle = lade_abrechnungen(self.session)
        offen = self._offene(alle, buchungen, transaktionen)
        offen_ids = {a.id for a in offen}
        fest = {
            a.belastung_id for a in alle if a.belastung_id and a.id not in offen_ids
        }
        for tx in self._kandidaten(transaktionen, fest):
            for k in self.karten:
                if (
                    k.direkt
                    or not k.karte.abrechnungstag
                    or not k.belastet(tx, self.einst)
                ):
                    continue
                if any(
                    a.kreditkarte_id == k.karte.id and self._im_fenster(a, tx)
                    for a in offen
                ):
                    continue
                stichtag = letzter_stichtag(tx.datum, k.karte.abrechnungstag)
                bisher = lade_abrechnungen(self.session, kreditkarte_id=k.karte.id)
                if all(a.stichtag < stichtag for a in bisher):
                    neu = bilde_abrechnung(self.session, k.karte, stichtag, self.einst)
                    if neu is not None:
                        offen.append(neu)

    def _sammelbelastungen(self) -> None:
        buchungen = _buchungen_je_umsatz(self.session)
        transaktionen = {t.id: t for t in lade_transaktionen(self.session)}
        alle = lade_abrechnungen(self.session)
        offen = self._offene(alle, buchungen, transaktionen)
        offen_ids = {a.id for a in offen}
        vorlaeufig = [a for a in offen if a.belastung_id is not None]
        fest = {
            a.belastung_id for a in alle if a.belastung_id and a.id not in offen_ids
        }

        def paare(
            tx: Transaktion, vergeben: dict[UUID, _Ziel]
        ) -> list[tuple[_Karte, Kreditkartenabrechnung]]:
            return [
                (k, a)
                for a in offen
                if a.id not in vergeben
                and (a.id, tx.id) not in self.abgelehnt
                and self._im_fenster(a, tx)
                for k in [self.karte_von[a.kreditkarte_id]]
                if k.belastet(tx, self.einst)
            ]

        ziel: dict[UUID, _Ziel] = {}
        rest: list[Transaktion] = []
        mehrdeutig: list[Transaktion] = []
        ohne: list[Transaktion] = []
        for tx in self._kandidaten(transaktionen, fest):  # 1. exakt: Belastung = Summe
            exakt = [(k, a) for k, a in paare(tx, ziel) if a.summe == tx.betrag]
            if len(exakt) == 1:
                k, a = exakt[0]
                ziel[a.id] = (tx, k, a, AbrechnungStatus.ABGEGLICHEN)
            elif exakt:
                mehrdeutig.append(tx)
            else:
                rest.append(tx)
        moeglich = {tx.id: paare(tx, ziel) for tx in rest}
        for tx in rest:  # 2. genau eine Abrechnung und keine andere Belastung dafür
            eigene = moeglich[tx.id]
            ids = {a.id for _, a in eigene}
            konkurrenz = any(
                t.id != tx.id and ids & {a.id for _, a in moeglich[t.id]} for t in rest
            )
            if not eigene:
                ohne.append(tx)
            elif len(eigene) == 1 and not konkurrenz:
                k, a = eigene[0]
                ziel[a.id] = (tx, k, a, AbrechnungStatus.ABWEICHUNG)
            else:
                mehrdeutig.append(tx)

        # vorläufige Zuordnungen: bleiben, wenn sich nichts ändert, sonst gelöst
        geloest = []
        for a in vorlaeufig:
            neu = ziel.get(a.id)
            if (
                neu is not None
                and neu[0].id == a.belastung_id
                and neu[3] is AbrechnungStatus.ABWEICHUNG
                and a.id not in self.nachgetragen
            ):
                del ziel[a.id]  # unverändert
                continue
            geloest.append(self._loese(a, transaktionen))
        for tx, k, a, status in sorted(ziel.values(), key=lambda z: z[0].datum):
            self._ordne_zu(tx, k, a, status)
        bleibt = {z[0].id for z in ziel.values()} | {t.id for t in mehrdeutig}
        self.ergebnis.geloest += [t for t in geloest if t.id not in bleibt]
        gebucht = gebuchte_transaktion_ids(self.session)
        still = {t.id for t in geloest} | {tx_id for _, tx_id in self.abgelehnt}
        self.ergebnis.ohne_abrechnung += [
            t for t in ohne if t.id not in gebucht and t.id not in still
        ]
        self.ergebnis.mehrdeutig += mehrdeutig

    def _ordne_zu(
        self,
        tx: Transaktion,
        k: _Karte,
        a: Kreditkartenabrechnung,
        status: AbrechnungStatus,
    ) -> None:
        befunde = []
        if status is AbrechnungStatus.ABWEICHUNG:
            befunde.append(
                f"Sammelbelastung {betrag_de(tx.betrag)} € vom {datum_de(tx.datum)} "
                f"≠ Summe der {a.anzahl} Einzelumsätze {betrag_de(a.summe)} € — "
                f"Differenz {betrag_de(tx.betrag - a.summe)} €; kein Rundungsposten: "
                "fehlt ein Umsatz, eine Gebühr oder Zinsen?"
            )
        soll = k.soll(self.geldtransit)
        if tx.id in gebuchte_transaktion_ids(self.session):
            vorhanden = [
                b for b in lade_buchungen(self.session) if b.transaktion_id == tx.id
            ]
            if not any(b.soll_konto == soll for b in vorhanden):
                konten = ", ".join(sorted({b.soll_konto for b in vorhanden}))
                befunde.append(
                    f"Sammelbelastung ist schon anders gebucht (Soll {konten} statt "
                    f"{soll}) — Buchung prüfen"
                )
                status = AbrechnungStatus.ABWEICHUNG
        else:
            speichere_buchung(
                self.session,
                Buchungssatz(
                    transaktion_id=tx.id,
                    beleg_id=a.beleg_id,
                    datum=tx.datum,
                    soll_konto=soll,
                    haben_konto=tx.sachkonto or k.giro.sachkonto,
                    betrag_netto=-tx.betrag,
                    buchungstext=f"Kreditkarte {k.konto.bezeichnung}"[:60],
                    status=(
                        BuchungStatus.AUTO_GEBUCHT
                        if status is AbrechnungStatus.ABGEGLICHEN
                        else BuchungStatus.ZUR_PRUEFUNG
                    ),
                    confidence=1.0 if status is AbrechnungStatus.ABGEGLICHEN else 0.5,
                ),
            )
            self.session.flush()
        neu = a.model_copy(
            update={
                "belastung_id": tx.id,
                "belastung_betrag": tx.betrag,
                "status": status,
                "befund": "; ".join(befunde) or None,
            }
        )
        aktualisiere_abrechnung(self.session, neu)
        if status is AbrechnungStatus.ABGEGLICHEN:
            self.ergebnis.abgeglichen.append(neu)
        else:
            self.ergebnis.abweichungen.append(neu)

    def _eigener_ausgleich(
        self, k: _Karte, t: Transaktion, buchungen: dict[UUID, list[Buchungssatz]]
    ) -> list[Buchungssatz]:
        """Buchungen „Kreditkarte an Geldtransit“ dieser Ausgleichszeile."""
        soll = t.sachkonto or k.konto.sachkonto
        return [
            b
            for b in buchungen.get(t.id, [])
            if b.soll_konto == soll and b.haben_konto == self.geldtransit
        ]

    def _ausgleichszeilen(self) -> None:
        """Karten mit Abruf: Begleichung auf dem Kartenkonto über Geldtransit —
        automatisch nur gegen eine gleich hohe, über Geldtransit gebuchte
        Sammelbelastung dieser Karte, sonst zur Prüfung."""
        buchungen = _buchungen_je_umsatz(self.session)
        transaktionen = {t.id: t for t in lade_transaktionen(self.session)}
        for k in self.karten:
            if k.direkt:
                continue
            offen: Counter[Decimal] = Counter(
                -transaktionen[a.belastung_id].betrag
                for a in lade_abrechnungen(self.session, kreditkarte_id=k.karte.id)
                if a.belastung_id in transaktionen
                and self._eigene(k, transaktionen[a.belastung_id], buchungen)
            )
            ausgleiche = sorted(
                (
                    t
                    for t in transaktionen.values()
                    if t.bankkonto_id == k.konto.id and _ist_ausgleich(t, self.einst)
                ),
                key=lambda t: (t.datum, str(t.id)),
            )

            for t in ausgleiche:  # bestätigte Ausgleiche verbrauchen ihre Belastung
                if (
                    any(
                        b.status not in _VORLAEUFIG
                        for b in self._eigener_ausgleich(k, t, buchungen)
                    )
                    and offen[t.betrag]
                ):
                    offen[t.betrag] -= 1
            for t in ausgleiche:
                vorhanden = self._eigener_ausgleich(k, t, buchungen)
                if any(b.status not in _VORLAEUFIG for b in vorhanden):
                    continue
                if t.id in buchungen and not vorhanden:
                    continue  # anders gebucht — nicht anfassen
                passend = offen[t.betrag] > 0
                if passend:
                    offen[t.betrag] -= 1
                if vorhanden:  # vorläufig gebucht: jetzt mit Belastung bestätigen
                    for b in vorhanden if passend else []:
                        aktualisiere_buchung(
                            self.session,
                            str(b.id),
                            b.model_copy(
                                update={
                                    "status": BuchungStatus.AUTO_GEBUCHT,
                                    "confidence": 1.0,
                                }
                            ),
                        )
                    continue
                speichere_buchung(
                    self.session,
                    Buchungssatz(
                        transaktion_id=t.id,
                        datum=t.datum,
                        soll_konto=t.sachkonto or k.konto.sachkonto,
                        haben_konto=self.geldtransit,
                        betrag_netto=t.betrag,
                        buchungstext=f"Ausgleich {k.konto.bezeichnung}"[:60],
                        status=(
                            BuchungStatus.AUTO_GEBUCHT
                            if passend
                            else BuchungStatus.ZUR_PRUEFUNG
                        ),
                        confidence=1.0 if passend else 0.5,
                    ),
                )
                self.ergebnis.ausgleich_gebucht += 1
                if not passend:
                    self.ergebnis.ausgleich_ohne_belastung.append(t)
            self.session.flush()


def gleiche_sammelbelastungen_ab(
    session: Session,
    einstellungen: Buchhaltung,
    einst: KreditkartenEinstellungen | None = None,
) -> Kartenabgleich:
    """PDF-Abrechnungen übernehmen (bei einer PDF-Karte), Sammelbelastungen gegen
    die Abrechnungen prüfen und buchen, Ausgleichszeilen über Geldtransit buchen."""
    if einst is None:
        from accounti.bank.einstellungen import lade_bank_einstellungen

        einst = lade_bank_einstellungen().kreditkarte
    return _Abgleich(session, einstellungen, einst).lauf()


def loese_zuordnung(
    session: Session,
    schluessel: str,
    einstellungen: Buchhaltung,
    einst: KreditkartenEinstellungen | None = None,
) -> tuple[Kreditkartenabrechnung, Transaktion]:
    """Zuordnung von Hand lösen: die vorläufige Buchung der Belastung entfällt, und
    der Abgleich ordnet diese Belastung der Abrechnung nicht wieder zu."""
    if einst is None:
        from accounti.bank.einstellungen import lade_bank_einstellungen

        einst = lade_bank_einstellungen().kreditkarte
    treffer = [
        a
        for a in lade_abrechnungen(session)
        if str(a.id).startswith(schluessel.lower())
    ]
    if len(treffer) != 1:
        msg = (
            f"Keine Abrechnung '{schluessel}'"
            if not treffer
            else f"'{schluessel}' ist nicht eindeutig"
        )
        raise KreditkartenError(msg)
    a = treffer[0]
    abgleich = _Abgleich(session, einstellungen, einst)
    k = abgleich.karte_von.get(a.kreditkarte_id)
    transaktionen = {t.id: t for t in lade_transaktionen(session)}
    tx = transaktionen.get(a.belastung_id) if a.belastung_id else None
    if k is None or tx is None:
        msg = f"Abrechnung {str(a.id)[:8]} hat keine zugeordnete Sammelbelastung"
        raise KreditkartenError(msg)
    for b in abgleich._eigene(k, tx, _buchungen_je_umsatz(session)):
        if b.status not in _VORLAEUFIG:
            msg = (
                f"Die Buchung der Sammelbelastung ist "
                f"{_STATUS_TEXT.get(b.status, b.status.value)} — nicht gelöst; "
                "eine Korrektur gehört in die Buchhaltung (Storno)"
            )
            raise KreditkartenError(msg)
    abgleich._loese(a, transaktionen)
    lehne_belastung_ab(session, a.id, tx.id)
    geloest = a.model_copy(
        update={
            "belastung_id": None,
            "belastung_betrag": None,
            "status": AbrechnungStatus.OFFEN,
            "befund": None,
        }
    )
    return geloest, tx
