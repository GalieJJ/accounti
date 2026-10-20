"""Abruf und geplanter Lauf: alle Konten holen, dann zuordnen, abgleichen, kontieren.

Idempotent: Ein zweiter Lauf erzeugt keine doppelten Umsätze (Dublettenschutz) und
bucht nichts doppelt (jeder Schritt nimmt nur Offenes). Ein Konto, das eine Freigabe
braucht oder scheitert, hält die anderen nicht auf.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from accounti.bank.abgleich import Abgleichsergebnis
from accounti.bank.abgleichslauf import gleiche_belege_ab
from accounti.bank.dubletten import mit_schluessel
from accounti.bank.einstellungen import BankEinstellungen, lade_bank_einstellungen
from accounti.bank.kreditkarte import Kartenabgleich, gleiche_sammelbelastungen_ab
from accounti.bank.provider import (
    BANK_PROVIDER,
    Freigabe,
    FreigabeNoetigError,
    ProviderError,
)
from accounti.bank.tresor import (
    TresorError,
    entschluessele,
    lade_schluessel,
    verschluessele,
)
from accounti.buchung.kontierung import Kontierungslauf, kontiere_umsaetze
from accounti.db.repository import (
    aktualisiere_bankkonto,
    lade_bankkonten,
    speichere_transaktion,
    vorhandene_dublettenschluessel,
)
from accounti.klassifikation.engine import KlassifikationsEngine
from accounti.konfiguration import Buchhaltung
from accounti.models import Bankkonto, KontoZustand, Transaktion
from accounti.opos.zahlungslauf import Zahlungslauf, zuordne_zahlungen

UEBERLAPPUNG = timedelta(days=14)  # Banken buchen nach; Dubletten fängt der Schutz


def speichere_neue(
    session: Session,
    transaktionen: list[Transaktion],
    quelle: str,
    konto: Bankkonto | None = None,
) -> tuple[int, int]:
    """Speichert nur, was noch nicht da ist; liefert (neu, doppelt)."""
    mit = mit_schluessel(transaktionen, konto.iban if konto else quelle)
    vorhanden = vorhandene_dublettenschluessel(
        session, {t.dublettenschluessel for t in mit if t.dublettenschluessel}
    )
    neu = 0
    for tx in mit:
        if tx.dublettenschluessel in vorhanden:
            continue
        if konto is not None:
            tx = tx.model_copy(
                update={"bankkonto_id": konto.id, "sachkonto": konto.sachkonto}
            )
        speichere_transaktion(session, tx)
        neu += 1
    session.flush()
    return neu, len(mit) - neu


@dataclass
class KontoAbruf:
    konto: Bankkonto
    zustand: KontoZustand
    neu: int = 0
    doppelt: int = 0
    meldung: str | None = None


def rufe_ab(
    session: Session,
    schluessel: str | None = None,
    konten: list[Bankkonto] | None = None,
    jetzt: datetime | None = None,
    freigabe: Freigabe | None = None,
) -> list[KontoAbruf]:
    """Holt neue Umsätze aller (oder der genannten) Konten.

    Ohne ``freigabe`` (Cron, ``bank lauf``) wird eine verlangte Freigabe zum Zustand
    am Konto; mit ihr fragt der Provider nach (``accounti fints freigeben``).
    """
    ergebnisse = []
    for konto in konten if konten is not None else lade_bankkonten(session):
        ergebnis = KontoAbruf(konto, KontoZustand.BEREIT)
        stand = konto.abrufstand
        neuer_zugang: dict[str, str] | None = None
        try:
            klasse = BANK_PROVIDER.get(konto.provider)
            if klasse is None:
                raise ProviderError(f"Unbekannter Provider '{konto.provider}'")
            zugang: dict[str, str] = {}
            if konto.zugang:
                schluessel = schluessel or lade_schluessel()
                zugang = entschluessele(konto.zugang, schluessel, str(konto.id))
            ab = konto.abrufstand - UEBERLAPPUNG if konto.abrufstand else None
            abruf = klasse(freigabe=freigabe).abrufen(konto, zugang, ab)
            neuer_zugang = abruf.zugang
            with session.begin_nested():
                ergebnis.neu, ergebnis.doppelt = speichere_neue(
                    session, abruf.transaktionen, konto.iban, konto
                )
            if abruf.transaktionen:
                neuester = max(t.datum for t in abruf.transaktionen)
                stand = max(stand, neuester) if stand else neuester
        except FreigabeNoetigError as fehler:
            neuer_zugang = fehler.zugang
            ergebnis.zustand, ergebnis.meldung = (
                KontoZustand.FREIGABE_NOETIG,
                str(fehler),
            )
        except (ProviderError, TresorError, OSError, ValueError) as fehler:
            ergebnis.zustand, ergebnis.meldung = KontoZustand.FEHLER, str(fehler)
        aenderung: dict[str, object] = {
            "abrufstand": stand,
            "letzter_abruf": jetzt or datetime.now(),
        }
        if neuer_zugang is not None:  # z.B. Sitzung der Bank — nur verschlüsselt
            try:
                schluessel = schluessel or lade_schluessel()
                aenderung["zugang"] = verschluessele(
                    neuer_zugang, schluessel, str(konto.id)
                )
            except TresorError as fehler:
                ergebnis.zustand, ergebnis.meldung = KontoZustand.FEHLER, str(fehler)
        konto = konto.model_copy(
            update={
                **aenderung,
                "zustand": ergebnis.zustand,
                "meldung": ergebnis.meldung,
            }
        )
        aktualisiere_bankkonto(session, konto)
        ergebnis.konto = konto
        ergebnisse.append(ergebnis)
    return ergebnisse


@dataclass
class Banklauf:
    abrufe: list[KontoAbruf] = field(default_factory=list)
    kreditkarten: Kartenabgleich = field(default_factory=Kartenabgleich)
    zuordnung: Zahlungslauf = field(default_factory=Zahlungslauf)
    abgleich: Abgleichsergebnis = field(default_factory=Abgleichsergebnis)
    kontierung: Kontierungslauf = field(default_factory=Kontierungslauf)


def bank_lauf(
    session: Session,
    engine: KlassifikationsEngine,
    einstellungen: Buchhaltung,
    schluessel: str | None = None,
    bank_einstellungen: BankEinstellungen | None = None,
) -> Banklauf:
    """Der geplante Lauf: abrufen → Kreditkarten → offene Posten zuordnen →
    abgleichen → kontieren. Die Sammelbelastung einer Karte ist damit gebucht,
    bevor offene Posten oder das Regelwerk sie sehen."""
    bank = bank_einstellungen or lade_bank_einstellungen()
    return Banklauf(
        abrufe=rufe_ab(session, schluessel),
        kreditkarten=gleiche_sammelbelastungen_ab(
            session, einstellungen, bank.kreditkarte
        ),
        zuordnung=zuordne_zahlungen(session, einstellungen),
        abgleich=gleiche_belege_ab(session),
        kontierung=kontiere_umsaetze(session, engine, einstellungen),
    )
