"""Kontierungslauf für Bankumsätze (``accounti classify``).

Ein Umsatz mit bestätigtem Beleg wird aus dem Beleg gebucht; alle anderen gehen wie
bisher durch Regelwerk und LLM. Jede Buchung bekommt in derselben Transaktion ihre
Herkunft und Begründung (``kontierungsgruende``, Baustein 10b) — greift die Schranke
des Mappers (Bankseite gegen Vorzeichen), steht das in der Begründung. Schon gebuchte
und offenen Posten zugeordnete Umsätze bleiben unangetastet, ebenso solche mit
offenem Beleg-Vorschlag und solche, die der Marktplatz-Abgleich erwartet
(``buchung.marktplatz``).

Die zweite Schranke gilt für jeden Weg (Beleg, gelernte Regel, Regeldatei,
Standardregel, Gegenrichtung, LLM) an dieser einen Stelle: Eine Buchung mit demselben
Konto im Soll und im Haben entsteht nie automatisch. Sie bewegte nichts — bei einer
Umbuchung zwischen eigenen Geldkonten (Regel „1210 an 1200“ auf einem Umsatz des
Tagesgelds 1210) fiele die Bewegung aus den Büchern, der Bestand wiche vom Kontoauszug
ab (§ 239 Abs. 2 HGB, § 146 Abs. 1 AO). Der Umsatz bleibt offen, der Lauf nennt ihn
(``Kontierungslauf.umbuchungen``); ``accounti pruefen`` meldet Altfälle (Prüfregel
``soll_gleich_haben``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.anzeige import betrag_de, datum_de
from accounti.buchung.mapper import SCHRANKE_HINWEIS, bankseite, zu_buchungssatz
from accounti.buchung.marktplatz import Marktplatzauszahlungen
from accounti.buchung.mit_beleg import kontiere_beleg
from accounti.db.repo_kontierung import speichere_kontierungsgrund
from accounti.db.repository import (
    lade_abgleiche,
    lade_belege,
    lade_kontakte,
    speichere_buchung,
)
from accounti.integrationen.einstellungen import Integrationen
from accounti.klassifikation.engine import KlassifikationsEngine
from accounti.konfiguration import Buchhaltung
from accounti.models import AbgleichStatus, Buchungssatz, Transaktion
from accounti.opos.zahlungslauf import offene_transaktionen


@dataclass
class Kontierungslauf:
    kontiert: int = 0
    mit_beleg: int = 0
    offen: int = 0
    marktplatz: int = 0  # davon offen, weil der Marktplatz-Abgleich sie erwartet
    marktplaetze: set[str] = field(default_factory=set)
    # davon offen, weil die Kontierung Soll = Haben ergäbe (je Umsatz ein Hinweis)
    umbuchungen: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Kandidat:
    buchung: Buchungssatz
    quelle: str
    begruendung: str
    regel: str | None = None
    modell: str | None = None


def _soll_gleich_haben(tx: Transaktion, kandidaten: list[_Kandidat]) -> str | None:
    """Hinweis, wenn eine der Buchungen Soll = Haben hätte — sonst ``None``."""
    k = next(
        (k for k in kandidaten if k.buchung.soll_konto == k.buchung.haben_konto), None
    )
    if k is None:
        return None
    herkunft = {
        "llm": "der LLM-Vorschlag",
        "beleg": "die Belegbuchung",
    }.get(k.quelle, f"Regel '{k.regel}'" if k.regel else "die Kontierung")
    wer = tx.gegenkonto_name or (tx.verwendungszweck or "")[:40]
    return (
        f"Umsatz vom {datum_de(tx.datum)} über {betrag_de(tx.betrag)} € ({wer}): "
        f"{herkunft} ergäbe {k.buchung.soll_konto} an {k.buchung.haben_konto}"
    )


def kontiere_umsaetze(
    session: Session,
    engine: KlassifikationsEngine,
    einstellungen: Buchhaltung,
    integrationen: Integrationen | None = None,
    auslassen: Mapping[UUID, str] | None = None,
) -> Kontierungslauf:
    """``integrationen``: Stichworte und Konten der Marktplätze (Standard ohne
    Konfiguration) — Auszahlungen bleiben offen, bis die Abrechnung sie abgleicht.
    ``auslassen``: Umsatz → Marktplatz, über den der Marktplatz-Abgleich desselben
    Laufs einen Befund hat (``bank lauf``) — offen, auch mit Beleg."""
    lauf = Kontierungslauf()
    markt = Marktplatzauszahlungen(
        session, integrationen or Integrationen(), einstellungen.bank_konto
    )
    abgleiche = {
        a.transaktion_id: a
        for a in lade_abgleiche(session, status={AbgleichStatus.BESTAETIGT})
    }
    belege = {b.id: b for b in lade_belege(session)} if abgleiche else {}
    kontakte = lade_kontakte(session) if abgleiche else []
    for tx in offene_transaktionen(session, fuer_kontierung=True):
        if auslassen and tx.id in auslassen:
            # der Abgleich weiß, dass er eine Auszahlung ist (Nachprüfung 5 E, M4 a)
            lauf.offen += 1
            lauf.marktplatz += 1
            lauf.marktplaetze.add(auslassen[tx.id])
            continue
        kandidaten: list[_Kandidat]
        abgleich = abgleiche.get(tx.id)
        mit_beleg = abgleich is not None and abgleich.beleg_id in belege
        if abgleich is not None and mit_beleg:
            beleg = belege[abgleich.beleg_id]
            bk = kontiere_beleg(tx, beleg, einstellungen, engine.regelwerk, kontakte)
            kandidaten = [
                _Kandidat(b, bk.quelle, bk.begruendung, bk.regel) for b in bk.buchungen
            ]
        else:
            marktplatz = markt.marktplatz(tx)
            if marktplatz is not None:
                # Geldbewegung, deren Erlöse die Abrechnung bucht (Steuer B2)
                lauf.offen += 1
                lauf.marktplatz += 1
                lauf.marktplaetze.add(marktplatz)
                continue
            ergebnis = engine.klassifiziere(tx)
            if ergebnis is None:
                lauf.offen += 1
                continue
            buchung = zu_buchungssatz(tx, ergebnis, bank_konto=einstellungen.bank_konto)
            begruendung = ergebnis.begruendung
            seite = bankseite(
                tx, ergebnis.soll_konto, ergebnis.haben_konto, einstellungen.bank_konto
            )
            if seite != "passt":
                begruendung = f"{begruendung} — {SCHRANKE_HINWEIS[seite]}"
            if tx.sachkonto and tx.sachkonto != einstellungen.bank_konto:
                # Regeln buchen gegen das Standard-Bankkonto; dieser Umsatz gehört
                # zu einem anderen Finanzkonto (zweites Giro, Kreditkarte, …)
                buchung = buchung.model_copy(
                    update={
                        feld: tx.sachkonto
                        for feld in ("soll_konto", "haben_konto")
                        if getattr(buchung, feld) == einstellungen.bank_konto
                    }
                )
            kandidaten = [
                _Kandidat(
                    buchung,
                    "llm" if ergebnis.quelle == "llm" else "regelwerk",
                    begruendung,
                    ergebnis.regel,
                    ergebnis.modell,
                )
            ]
        hinweis = _soll_gleich_haben(tx, kandidaten)
        if hinweis is not None:
            # die zweite Schranke: nie Soll = Haben, gleich aus welcher Quelle
            lauf.offen += 1
            lauf.umbuchungen.append(hinweis)
            continue
        for k in kandidaten:
            speichere_buchung(session, k.buchung)
            speichere_kontierungsgrund(
                session,
                k.buchung.id,
                quelle=k.quelle,  # type: ignore[arg-type]
                regel=k.regel,
                modell=k.modell,
                begruendung=k.begruendung,
            )
        lauf.kontiert += 1
        if mit_beleg:
            lauf.mit_beleg += 1
    return lauf


UMBUCHUNG_HINWEIS = (
    "offen gelassen: Die Kontierung ergäbe dasselbe Konto im Soll und im Haben "
    "(Soll = Haben, meist eine Umbuchung zwischen eigenen Geldkonten) — von Hand "
    "buchen (z. B. über Geldtransit oder nur auf einem der beiden Konten) und die "
    "Regel prüfen (accounti regeln liste)"
)


def umbuchung_hinweise(lauf: Kontierungslauf, hoechstens: int = 5) -> list[str]:
    """Zeilen für die Ausgabe von ``classify`` und ``bank lauf``."""
    if not lauf.umbuchungen:
        return []
    anzahl = len(lauf.umbuchungen)
    wort = "Umsatz" if anzahl == 1 else "Umsätze"
    zeilen = [f"{anzahl} {wort} {UMBUCHUNG_HINWEIS}:"]
    zeilen += [f"  {h}" for h in lauf.umbuchungen[:hoechstens]]
    if anzahl > hoechstens:
        zeilen.append(f"  … und {anzahl - hoechstens} weitere")
    return zeilen
