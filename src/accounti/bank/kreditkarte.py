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
„Geldtransit an Bank“ und „Kreditkarte an Geldtransit“. Die Einzelumsätze kontiert
``classify`` gegen das Sachkonto der Karte.
"""

from __future__ import annotations

import calendar
import re
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
    abgerechnete_transaktion_ids,
    aktualisiere_abrechnung,
    lade_abrechnungen,
    lade_kreditkarten,
    lade_transaktionen_nach_schluessel,
    speichere_abrechnung,
    speichere_kreditkarte,
)
from accounti.db.repository import (
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


def _konto(session: Session, konto_id: UUID) -> Bankkonto:
    for k in lade_bankkonten(session):
        if k.id == konto_id:
            return k
    raise KreditkartenError(f"Bankkonto {konto_id} fehlt")


@dataclass
class Uebernahme:
    abrechnung: Kreditkartenabrechnung
    neu: int
    doppelt: int
    ausgleich: int  # Begleichung der Vorperiode, nicht übernommen


def uebernimm_abrechnung(
    session: Session,
    beleg_schluessel: str,
    karte: Kreditkarte,
    einst: KreditkartenEinstellungen,
) -> Uebernahme:
    """PDF-Abrechnung (erfasster Beleg) → Umsätze am Kartenkonto + Abrechnung."""
    beleg = _finde_beleg(session, beleg_schluessel)
    if not ist_kartenabrechnung(beleg):
        msg = (
            f"Beleg {str(beleg.id)[:8]} ist keine Kreditkartenabrechnung mit "
            f"Einzelumsätzen (Belegart {beleg.belegart.value})"
        )
        raise KreditkartenError(msg)
    if any(a.beleg_id == beleg.id for a in lade_abrechnungen(session)):
        raise KreditkartenError(f"Beleg {str(beleg.id)[:8]} ist schon übernommen")
    konto = _konto(session, karte.bankkonto_id)
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
    einzeln = [t for t in umsaetze if not _ist_ausgleich(t, einst)]
    if not einzeln:
        raise KreditkartenError("Die Abrechnung enthält keine Einzelumsätze")
    from accounti.bank.lauf import speichere_neue  # vermeidet einen Importkreis

    neu, doppelt = speichere_neue(session, einzeln, konto.iban, konto)
    schluessel = [
        t.dublettenschluessel or "" for t in mit_schluessel(einzeln, konto.iban)
    ]
    gespeichert = lade_transaktionen_nach_schluessel(session, schluessel)
    abrechnung = Kreditkartenabrechnung(
        kreditkarte_id=karte.id,
        stichtag=beleg.belegdatum or max(t.datum for t in einzeln),
        von=min(t.datum for t in einzeln),
        beleg_id=beleg.id,
        summe=sum((t.betrag for t in einzeln), Decimal("0")),
        anzahl=len(einzeln),
    )
    try:
        speichere_abrechnung(
            session, abrechnung, [gespeichert[s].id for s in schluessel]
        )
    except ValueError as fehler:
        raise KreditkartenError(str(fehler)) from fehler
    return Uebernahme(abrechnung, neu, doppelt, len(umsaetze) - len(einzeln))


def bilde_abrechnung(
    session: Session,
    karte: Kreditkarte,
    stichtag: date,
    einst: KreditkartenEinstellungen,
    von: date | None = None,
) -> Kreditkartenabrechnung | None:
    """Abrechnung aus den Umsätzen des Kartenkontos (Karten mit Abruf).

    Dazu gehören alle noch nicht abgerechneten Umsätze nach der letzten Abrechnung
    bis zum Stichtag, ohne Ausgleichszeilen. ``None``, wenn es keine gibt.
    """
    bisher = lade_abrechnungen(session, kreditkarte_id=karte.id)
    letzte = max((a.stichtag for a in bisher), default=None)
    if letzte is not None and stichtag <= letzte:
        msg = f"Stichtag muss nach der letzten Abrechnung ({datum_de(letzte)}) liegen"
        raise KreditkartenError(msg)
    beginn = von or (letzte + timedelta(days=1) if letzte else None)
    abgerechnet = abgerechnete_transaktion_ids(session)
    umsaetze = [
        t
        for t in lade_transaktionen(session)
        if t.bankkonto_id == karte.bankkonto_id
        and t.id not in abgerechnet
        and t.datum <= stichtag
        and (beginn is None or t.datum >= beginn)
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
    ausgleich_gebucht: int = 0
    hinweise: list[str] = field(default_factory=list)


@dataclass
class _Karte:
    karte: Kreditkarte
    konto: Bankkonto
    giro: Bankkonto

    @property
    def direkt(self) -> bool:
        return self.konto.provider == PDF_PROVIDER

    def belastet(self, tx: Transaktion, einst: KreditkartenEinstellungen) -> bool:
        """Ist ``tx`` eine Sammelbelastung dieser Karte auf ihrem Girokonto?"""
        if tx.bankkonto_id != self.giro.id or tx.betrag >= 0:
            return False
        text = f"{tx.verwendungszweck} {tx.gegenkonto_name or ''}"
        if self.karte.muster:
            passt = re.search(self.karte.muster, text, re.IGNORECASE) is not None
        else:
            passt = einst.ist_belastung(text)
        endziffern = self.karte.endziffern
        return passt and (not endziffern or endziffern in re.sub(r"\s", "", text))


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
        self.ergebnis = Kartenabgleich()
        konten = {k.id: k for k in lade_bankkonten(session)}
        self.karten = [
            _Karte(k, konten[k.bankkonto_id], konten[k.girokonto_id])
            for k in lade_kreditkarten(session)
            if k.bankkonto_id in konten and k.girokonto_id in konten
        ]

    def lauf(self) -> Kartenabgleich:
        if not self.karten:
            return self.ergebnis
        self._pdf_uebernehmen()
        self._sammelbelastungen()
        self._ausgleichszeilen()
        return self.ergebnis

    def _pdf_uebernehmen(self) -> None:
        uebernommen = {a.beleg_id for a in lade_abrechnungen(self.session)}
        offen = [
            b
            for b in lade_belege(self.session, status={BelegStatus.ERFASST})
            if b.id not in uebernommen and ist_kartenabrechnung(b)
        ]
        if not offen:
            return
        pdf_karten = [k for k in self.karten if k.direkt]
        if len(pdf_karten) != 1:
            self.ergebnis.hinweise.append(
                f"{len(offen)} Kreditkartenabrechnung(en) noch nicht übernommen — "
                "accounti kreditkarte uebernehmen <BELEG> --karte <KENNUNG>"
            )
            return
        for beleg in offen:
            try:
                self.ergebnis.uebernommen.append(
                    uebernimm_abrechnung(
                        self.session, str(beleg.id), pdf_karten[0].karte, self.einst
                    )
                )
            except KreditkartenError as fehler:
                self.ergebnis.hinweise.append(f"Beleg {str(beleg.id)[:8]}: {fehler}")

    def _sammelbelastungen(self) -> None:
        alle = lade_abrechnungen(self.session)
        belastet = {a.belastung_id for a in alle if a.belastung_id}
        transaktionen = [
            t for t in lade_transaktionen(self.session) if t.id not in belastet
        ]
        kandidaten = {
            k.karte.id: sorted(
                (t for t in transaktionen if k.belastet(t, self.einst)),
                key=lambda t: (t.datum, str(t.id)),
            )
            for k in self.karten
        }
        for k in self.karten:  # Karten mit Abruf: Abrechnung am Abrechnungstag bilden
            if k.direkt or not k.karte.abrechnungstag:
                continue
            for tx in kandidaten[k.karte.id]:
                if not self._offene(k, tx):
                    stichtag = letzter_stichtag(tx.datum, k.karte.abrechnungstag)
                    bisher = lade_abrechnungen(self.session, kreditkarte_id=k.karte.id)
                    if all(a.stichtag < stichtag for a in bisher):
                        bilde_abrechnung(self.session, k.karte, stichtag, self.einst)
        alle_tx = sorted(
            {t.id: t for ts in kandidaten.values() for t in ts}.values(),
            key=lambda t: (t.datum, str(t.id)),
        )
        rest = []
        for tx in alle_tx:  # 1. exakt: Belastung = Summe
            exakt = [(k, a) for k, a in self._paare(tx) if a.summe == tx.betrag]
            if len(exakt) == 1:
                self._ordne_zu(tx, *exakt[0], AbrechnungStatus.ABGEGLICHEN)
            elif exakt:
                self.ergebnis.mehrdeutig.append(tx)
            else:
                rest.append(tx)
        paare = {tx.id: self._paare(tx) for tx in rest}
        for tx in rest:  # 2. genau eine Abrechnung und keine andere Belastung dafür
            eigene = paare[tx.id]
            konkurrenz = [
                t
                for t in rest
                if t.id != tx.id
                and {a.id for _, a in paare[t.id]} & {a.id for _, a in eigene}
            ]
            if not eigene:
                self.ergebnis.ohne_abrechnung.append(tx)
            elif len(eigene) == 1 and not konkurrenz:
                self._ordne_zu(tx, *eigene[0], AbrechnungStatus.ABWEICHUNG)
            else:
                self.ergebnis.mehrdeutig.append(tx)

    def _offene(self, k: _Karte, tx: Transaktion) -> list[Kreditkartenabrechnung]:
        fenster = timedelta(days=self.einst.belastung_fenster_tage)
        return [
            a
            for a in lade_abrechnungen(self.session, kreditkarte_id=k.karte.id)
            if a.belastung_id is None and a.stichtag <= tx.datum <= a.stichtag + fenster
        ]

    def _paare(self, tx: Transaktion) -> list[tuple[_Karte, Kreditkartenabrechnung]]:
        return [
            (k, a)
            for k in self.karten
            if k.belastet(tx, self.einst)
            for a in self._offene(k, tx)
        ]

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
        soll = k.konto.sachkonto if k.direkt else self.geldtransit
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

    def _ausgleichszeilen(self) -> None:
        """Karten mit Abruf: Begleichung auf dem Kartenkonto über Geldtransit."""
        gebucht = gebuchte_transaktion_ids(self.session)
        for k in self.karten:
            if k.direkt:
                continue
            for tx in lade_transaktionen(self.session):
                if (
                    tx.bankkonto_id != k.konto.id
                    or tx.id in gebucht
                    or not _ist_ausgleich(tx, self.einst)
                ):
                    continue
                speichere_buchung(
                    self.session,
                    Buchungssatz(
                        transaktion_id=tx.id,
                        datum=tx.datum,
                        soll_konto=tx.sachkonto or k.konto.sachkonto,
                        haben_konto=self.geldtransit,
                        betrag_netto=tx.betrag,
                        buchungstext=f"Ausgleich {k.konto.bezeichnung}"[:60],
                        status=BuchungStatus.AUTO_GEBUCHT,
                        confidence=1.0,
                    ),
                )
                self.ergebnis.ausgleich_gebucht += 1


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
