"""Prüfläufe: vorhandene Daten auswerten und daraus Aufgaben machen.

Ein Prüflauf ändert keine Buchhaltungsdaten. Er liest, was andere Bausteine ohnehin
speichern (Buchungen mit Confidence, Umsätze ohne Beleg, Belege und Kontakte zur
Prüfung, Bankkonten mit Zustand), und meldet je Fund einen Anlass. Danach gleicht
``gleiche_ab`` die Aufgaben seiner Art ab: Neue entstehen, vorhandene werden
aktualisiert, und Aufgaben ohne Anlass werden ``hinfaellig`` — so schließt sich
„Beleg fehlt“ von selbst, sobald der Beleg abgeglichen ist.

Andere Bausteine tragen eigene Läufe mit ``registriere_prueflauf`` ein — in ihrem
Modul ``accounti.<baustein>.aufgaben_anbindung``, das ``fuehre_prueflaeufe_aus``
selbst lädt. Jeder Lauf besitzt genau eine Aufgabenart (seinen Namen): Er schließt
alle Aufgaben dieser Art ohne Anlass, gleich wer sie angelegt hat. Wer die Regeln
eines eingebauten Laufs ändern will, registriert seinen Lauf unter demselben Namen
(ersetzt ihn), statt dieselbe Art daneben zu melden.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from typing import Protocol

from sqlalchemy.orm import Session

from accounti.anzeige import betrag_de, datum_de
from accounti.aufgaben.anbindung import lade_anbindungen
from accounti.aufgaben.einstellungen import AufgabenEinstellungen
from accounti.aufgaben.erzeugung import Abgleich, Anlass, gleiche_ab
from accounti.aufgaben.fehler import AufgabenError
from accounti.bank.abgleichslauf import offen_in_der_bank
from accounti.db.repository import (
    lade_abgleiche,
    lade_bankkonten,
    lade_belege,
    lade_buchungen,
    lade_kontakte,
    lade_transaktionen,
    lade_zuordnungen,
)
from accounti.models import (
    AbgleichStatus,
    BelegStatus,
    BuchungStatus,
    KontaktStatus,
    KontoZustand,
    ZuordnungStatus,
)
from accounti.models.aufgaben import Objekt, Prioritaet

_ZEITRAUM = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@dataclass
class Pruefergebnis:
    anlaesse: list[Anlass] = field(default_factory=list)
    # geprüfte Objekte; None = alles. Nur darin wird „hinfällig“ geschlossen.
    umfang: set[Objekt] | None = None
    # warum der Anlass für ein Objekt entfallen ist (sonst grund_entfallen des Laufs)
    gruende: dict[Objekt, str] = field(default_factory=dict)
    # am Stichtag noch nicht beurteilbar (z.B. jüngere Umsätze bei einem Lauf mit
    # früherem Stichtag) — ihre Aufgaben bleiben, wie sie sind
    ausgenommen: set[Objekt] = field(default_factory=set)


class Prueflauf(Protocol):
    name: str  # zugleich die Aufgabenart
    beschreibung: str
    grund_entfallen: str

    def finde(
        self,
        session: Session,
        einstellungen: AufgabenEinstellungen,
        stichtag: date,
        zeitraum: str | None,
    ) -> Pruefergebnis: ...


PRUEFLAEUFE: dict[str, Prueflauf] = {}


def registriere_prueflauf(lauf: Prueflauf) -> None:
    """Trägt den Lauf ein; ein Lauf gleichen Namens wird ersetzt."""
    Objekt(lauf.name, "probe")  # Name ist ein gültiger Bezeichner
    PRUEFLAEUFE[lauf.name] = lauf


def _im_zeitraum(tag: date, zeitraum: str | None) -> bool:
    return zeitraum is None or f"{tag:%Y-%m}" == zeitraum


def _titel(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= 200 else text[:199] + "…"


def _vergleich(wert: float, schwelle: float) -> tuple[str, str]:
    """``wert < schwelle`` so zeigen, dass die Rundung den Vergleich nicht umdreht:
    Wert abgerundet, Schwelle aufgerundet, beide mit den Stellen der Schwelle
    (mindestens zwei, höchstens vier) — 0,949 unter 0,95 ist „0,94“, nicht „0,95“."""
    exponent = Decimal(str(schwelle)).normalize().as_tuple().exponent
    stellen = min(4, max(2, -exponent if isinstance(exponent, int) else 2))
    raster = Decimal(1).scaleb(-stellen)
    return (
        str(Decimal(str(wert)).quantize(raster, rounding=ROUND_DOWN)),
        str(Decimal(str(schwelle)).quantize(raster, rounding=ROUND_UP)),
    )


def _komma(text: str) -> str:
    return text.replace(".", ",")


# ---------------------------------------------------------------------------
# Eingebaute Läufe
# ---------------------------------------------------------------------------

_ENTSCHIEDEN = {
    BuchungStatus.GEPRUEFT: "geprüft",
    BuchungStatus.KORRIGIERT: "korrigiert",
    BuchungStatus.EXPORTIERT: "exportiert",
}


class KontierungPruefen:
    """Buchungen unter der Confidence-Schwelle oder zur Prüfung vorgelegt."""

    name = "kontierung_pruefen"
    beschreibung = "Buchungen unter der Confidence-Schwelle oder zur Prüfung"
    grund_entfallen = "Buchung geprüft, korrigiert oder nicht mehr unsicher"

    def finde(
        self,
        session: Session,
        einstellungen: AufgabenEinstellungen,
        stichtag: date,
        zeitraum: str | None,
    ) -> Pruefergebnis:
        schwelle = einstellungen.pruefung.kontierung_schwelle
        buchungen = [
            b for b in lade_buchungen(session) if _im_zeitraum(b.datum, zeitraum)
        ]
        ergebnis = Pruefergebnis(
            umfang={Objekt("buchung", b.id) for b in buchungen} if zeitraum else None
        )
        frist = timedelta(days=einstellungen.frist_tage(self.name))
        for b in buchungen:
            objekt = Objekt("buchung", b.id)
            if b.status in _ENTSCHIEDEN:
                von = f" von {b.geprueft_von}" if b.geprueft_von else ""
                ergebnis.gruende[objekt] = f"Buchung {_ENTSCHIEDEN[b.status]}{von}"
                continue
            unsicher = b.confidence < schwelle
            if not unsicher and b.status is not BuchungStatus.ZUR_PRUEFUNG:
                continue
            confidence, grenze = _vergleich(b.confidence, schwelle)
            grund = (
                f"Confidence {_komma(confidence)} unter Schwelle {_komma(grenze)}"
                if unsicher
                else "zur Prüfung vorgelegt"
            )
            kurz = str(b.id)[:8]
            ergebnis.anlaesse.append(
                Anlass(
                    objekt,
                    titel=_titel(
                        f"Kontierung prüfen: {b.buchungstext} ({b.soll_konto} an "
                        f"{b.haben_konto}, {betrag_de(b.betrag_netto)} € netto)"
                    ),
                    beschreibung=(
                        f"Buchung vom {datum_de(b.datum)}: {grund}. Vorschlag Soll "
                        f"{b.soll_konto} / Haben {b.haben_konto}, Steuerschlüssel "
                        f"{b.steuer_schluessel or '—'}. Freigeben: accounti bestaetige "
                        f"{kurz} · Korrigieren: accounti korrigiere {kurz} --soll … "
                        "--haben …"
                    ),
                    faellig_am=b.datum + frist,
                    merkmale={
                        "soll_konto": b.soll_konto,
                        "haben_konto": b.haben_konto,
                        "status": b.status.value,
                        "confidence": confidence,
                    },
                )
            )
        return ergebnis


class BelegFehlt:
    """Bankumsätze ohne Beleg (``offen_in_der_bank`` aus Baustein 5)."""

    name = "beleg_fehlt"
    beschreibung = "Umsätze ohne Beleg"
    grund_entfallen = "Umsatz hat einen Beleg oder fällt nicht mehr unter die Prüfung"

    def finde(
        self,
        session: Session,
        einstellungen: AufgabenEinstellungen,
        stichtag: date,
        zeitraum: str | None,
    ) -> Pruefergebnis:
        pruefung = einstellungen.pruefung
        frist = timedelta(days=einstellungen.frist_tage(self.name))
        transaktionen = [
            t for t in lade_transaktionen(session) if _im_zeitraum(t.datum, zeitraum)
        ]
        ergebnis = Pruefergebnis(
            umfang={Objekt("transaktion", t.id) for t in transaktionen}
            if zeitraum
            else None,
            # am Stichtag zu jung (oder danach): weder Anlass noch „hinfällig“
            ausgenommen={
                Objekt("transaktion", t.id)
                for t in transaktionen
                if (stichtag - t.datum).days < pruefung.beleg_fehlt_nach_tagen
            },
        )
        belege = {b.id: b for b in lade_belege(session)}
        for a in lade_abgleiche(session, status={AbgleichStatus.BESTAETIGT}):
            beleg = belege.get(a.beleg_id)
            was = " ".join(
                filter(None, [beleg.lieferant_name, beleg.belegnummer, beleg.dateiname])
                if beleg
                else [str(a.beleg_id)[:8]]
            )
            ergebnis.gruende[Objekt("transaktion", a.transaktion_id)] = (
                f"Beleg zugeordnet: {was}"
            )
        for z in lade_zuordnungen(session, status={ZuordnungStatus.GEBUCHT}):
            ergebnis.gruende[Objekt("transaktion", z.transaktion_id)] = (
                "Beleg zugeordnet: Zahlung einem offenen Posten zugeordnet"
            )
        vorschlaege = {
            a.transaktion_id
            for a in lade_abgleiche(session, status={AbgleichStatus.VORGESCHLAGEN})
        } | {
            z.transaktion_id
            for z in lade_zuordnungen(session, status={ZuordnungStatus.VORGESCHLAGEN})
        }
        konten = {k.id: k.iban for k in lade_bankkonten(session)}
        for tx in offen_in_der_bank(session).umsaetze_ohne_beleg:
            if not _im_zeitraum(tx.datum, zeitraum):
                continue
            if abs(tx.betrag) < pruefung.beleg_fehlt_ab_betrag:
                continue
            if (stichtag - tx.datum).days < pruefung.beleg_fehlt_nach_tagen:
                continue
            wer = tx.gegenkonto_name or "unbekannte Gegenpartei"
            iban = konten.get(tx.bankkonto_id) if tx.bankkonto_id else None
            hinweis = (
                " Es gibt einen Vorschlag: accounti bank vorschlaege bzw. "
                "accounti opos vorschlaege."
                if tx.id in vorschlaege
                else ""
            )
            ergebnis.anlaesse.append(
                Anlass(
                    Objekt("transaktion", tx.id),
                    titel=_titel(
                        f"Beleg fehlt: {datum_de(tx.datum)} {betrag_de(tx.betrag)} € "
                        f"{wer}"
                    ),
                    beschreibung=(
                        f"Umsatz ohne Beleg: {tx.verwendungszweck}"
                        + (f" (Konto {iban})" if iban else "")
                        + ". Beleg erfassen (accounti belege import …) und abgleichen "
                        "(accounti bank abgleich) — oder mit Begründung als belegfrei "
                        "erledigen (accounti aufgaben erledigen NR --text …)." + hinweis
                    ),
                    faellig_am=tx.datum + frist,
                    merkmale={
                        "bankkonto": iban or "",
                        "gegenpartei": tx.gegenkonto_name or "",
                        "betrag": str(tx.betrag),
                        "richtung": "einnahme" if tx.betrag > 0 else "ausgabe",
                    },
                )
            )
        return ergebnis


class BelegPruefen:
    """Belege, die die Erfassung zur Prüfung vorgelegt hat (z.B. unlesbar)."""

    name = "beleg_pruefen"
    beschreibung = "Belege zur Prüfung (unlesbar, unvollständig, Dublettenverdacht)"
    grund_entfallen = "Beleg erfasst"

    def finde(
        self,
        session: Session,
        einstellungen: AufgabenEinstellungen,
        stichtag: date,
        zeitraum: str | None,
    ) -> Pruefergebnis:
        frist = timedelta(days=einstellungen.frist_tage(self.name))
        belege = [
            b
            for b in lade_belege(session)
            if _im_zeitraum(b.eingegangen_am.date(), zeitraum)
        ]
        ergebnis = Pruefergebnis(
            umfang={Objekt("beleg", b.id) for b in belege} if zeitraum else None
        )
        for b in belege:
            if b.status is not BelegStatus.ZUR_PRUEFUNG:
                continue
            ergebnis.anlaesse.append(
                Anlass(
                    Objekt("beleg", b.id),
                    titel=_titel(f"Beleg prüfen: {b.dateiname}"),
                    beschreibung=(
                        f"{b.pruef_grund or 'zur Prüfung vorgelegt'}. Eingang "
                        f"{datum_de(b.eingegangen_am.date())} über {b.kanal}."
                    ),
                    faellig_am=b.eingegangen_am.date() + frist,
                    merkmale={"kanal": b.kanal, "belegart": b.belegart.value},
                )
            )
        return ergebnis


class KontaktPruefen:
    """Automatisch angelegte Kontakte, die ein Mensch bestätigen soll."""

    name = "kontakt_pruefen"
    beschreibung = "Kontakte zur Prüfung"
    grund_entfallen = "Kontakt bestätigt"

    def finde(
        self,
        session: Session,
        einstellungen: AufgabenEinstellungen,
        stichtag: date,
        zeitraum: str | None,
    ) -> Pruefergebnis:
        frist = timedelta(days=einstellungen.frist_tage(self.name))
        ergebnis = Pruefergebnis()
        for k in lade_kontakte(session):
            if k.status is not KontaktStatus.ZUR_PRUEFUNG:
                continue
            konto = k.kreditor_konto or k.debitor_konto or str(k.id)[:8]
            ergebnis.anlaesse.append(
                Anlass(
                    Objekt("kontakt", k.id),
                    titel=_titel(f"Kontakt prüfen: {k.name}"),
                    beschreibung=(
                        f"{k.pruef_grund or 'automatisch angelegt'}. Bestätigen: "
                        f"accounti kontakte bestaetigen {konto}"
                    ),
                    faellig_am=k.erstellt_am.date() + frist,
                    merkmale={
                        "rolle": "kreditor" if k.ist_kreditor else "debitor",
                    },
                )
            )
        return ergebnis


class BankFreigabe:
    """Bankkonten, deren Abruf eine TAN-Freigabe (starke Kundenauthentifizierung)
    braucht — der automatische Lauf meldet das als Zustand am Konto."""

    name = "bank_freigabe"
    beschreibung = "Bankabruf wartet auf Freigabe"
    grund_entfallen = "Abruf wieder bereit"

    def finde(
        self,
        session: Session,
        einstellungen: AufgabenEinstellungen,
        stichtag: date,
        zeitraum: str | None,
    ) -> Pruefergebnis:
        ergebnis = Pruefergebnis()
        for k in lade_bankkonten(session):
            if k.zustand is not KontoZustand.FREIGABE_NOETIG:
                continue
            ergebnis.anlaesse.append(
                Anlass(
                    Objekt("bankkonto", k.id),
                    titel=_titel(f"Bank verlangt Freigabe: {k.bezeichnung} {k.iban}"),
                    beschreibung=(
                        f"{k.meldung or 'Freigabe nötig'}. Abruf interaktiv mit TAN "
                        "wiederholen: accounti bank abrufen"
                    ),
                    # None: beim Anlegen heute + Frist, danach unverändert — sonst
                    # schöbe jeder Lauf die Fälligkeit vor sich her
                    faellig_am=None,
                    prioritaet=Prioritaet.HOCH,
                    merkmale={"bankkonto": k.iban},
                )
            )
        return ergebnis


for _lauf in (
    KontierungPruefen(),
    BelegFehlt(),
    BelegPruefen(),
    KontaktPruefen(),
    BankFreigabe(),
):
    registriere_prueflauf(_lauf)


# ---------------------------------------------------------------------------
# Ausführen
# ---------------------------------------------------------------------------


@dataclass
class Laufergebnis:
    name: str
    abgleich: Abgleich


def fuehre_prueflaeufe_aus(
    session: Session,
    einstellungen: AufgabenEinstellungen,
    *,
    stichtag: date | None = None,
    namen: Sequence[str] | None = None,
    zeitraum: str | None = None,
    jetzt: datetime | None = None,
) -> list[Laufergebnis]:
    """Führt die genannten (sonst alle nicht abgeschalteten) Prüfläufe aus."""
    if zeitraum is not None and not _ZEITRAUM.match(zeitraum):
        msg = f"Zeitraum {zeitraum!r} bitte als JJJJ-MM angeben, z.B. 2026-09"
        raise AufgabenError(msg)
    jetzt = jetzt or datetime.now()
    stichtag = stichtag or jetzt.date()
    lade_anbindungen()
    if namen:
        unbekannt = [n for n in namen if n not in PRUEFLAEUFE]
        if unbekannt:
            msg = (
                f"Unbekannter Prüflauf {', '.join(unbekannt)} "
                f"(vorhanden: {', '.join(sorted(PRUEFLAEUFE))})"
            )
            raise AufgabenError(msg)
        laeufe = [PRUEFLAEUFE[n] for n in namen]
    else:
        laeufe = [
            lauf
            for name, lauf in PRUEFLAEUFE.items()
            if name not in einstellungen.pruefung.abgeschaltet
        ]
    ergebnisse = []
    for lauf in laeufe:
        befund = lauf.finde(session, einstellungen, stichtag, zeitraum)
        abgleich = gleiche_ab(
            session,
            lauf.name,
            befund.anlaesse,
            erzeugt_von=f"prueflauf:{lauf.name}",
            grund_entfallen=lauf.grund_entfallen,
            umfang=befund.umfang,
            ausgenommen=befund.ausgenommen,
            gruende=befund.gruende,
            einstellungen=einstellungen,
            jetzt=jetzt,
        )
        ergebnisse.append(Laufergebnis(lauf.name, abgleich))
    return ergebnisse
