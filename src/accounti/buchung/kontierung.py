"""Kontierungslauf für Bankumsätze (``accounti classify``).

Ein Umsatz mit bestätigtem Beleg wird aus dem Beleg gebucht; alle anderen gehen wie
bisher durch Regelwerk und LLM. Jede Buchung bekommt in derselben Transaktion ihre
Herkunft und Begründung (``kontierungsgruende``, Baustein 10b). Schon gebuchte und
offenen Posten zugeordnete Umsätze bleiben unangetastet, ebenso solche mit offenem
Beleg-Vorschlag.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from accounti.buchung.mapper import zu_buchungssatz
from accounti.buchung.mit_beleg import kontiere_beleg
from accounti.db.repo_kontierung import speichere_kontierungsgrund
from accounti.db.repository import (
    lade_abgleiche,
    lade_belege,
    lade_kontakte,
    speichere_buchung,
)
from accounti.klassifikation.engine import KlassifikationsEngine
from accounti.konfiguration import Buchhaltung
from accounti.models import AbgleichStatus
from accounti.opos.zahlungslauf import offene_transaktionen


@dataclass
class Kontierungslauf:
    kontiert: int = 0
    mit_beleg: int = 0
    offen: int = 0


def kontiere_umsaetze(
    session: Session, engine: KlassifikationsEngine, einstellungen: Buchhaltung
) -> Kontierungslauf:
    lauf = Kontierungslauf()
    abgleiche = {
        a.transaktion_id: a
        for a in lade_abgleiche(session, status={AbgleichStatus.BESTAETIGT})
    }
    belege = {b.id: b for b in lade_belege(session)} if abgleiche else {}
    kontakte = lade_kontakte(session) if abgleiche else []
    for tx in offene_transaktionen(session, fuer_kontierung=True):
        abgleich = abgleiche.get(tx.id)
        if abgleich is not None and abgleich.beleg_id in belege:
            beleg = belege[abgleich.beleg_id]
            bk = kontiere_beleg(tx, beleg, einstellungen, engine.regelwerk, kontakte)
            for buchung in bk.buchungen:
                speichere_buchung(session, buchung)
                speichere_kontierungsgrund(
                    session,
                    buchung.id,
                    quelle=bk.quelle,  # type: ignore[arg-type]
                    regel=bk.regel,
                    begruendung=bk.begruendung,
                )
            lauf.kontiert += 1
            lauf.mit_beleg += 1
            continue
        ergebnis = engine.klassifiziere(tx)
        if ergebnis is None:
            lauf.offen += 1
            continue
        buchung = zu_buchungssatz(tx, ergebnis)
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
        speichere_buchung(session, buchung)
        speichere_kontierungsgrund(
            session,
            buchung.id,
            quelle="llm" if ergebnis.quelle == "llm" else "regelwerk",
            regel=ergebnis.regel,
            modell=ergebnis.modell,
            begruendung=ergebnis.begruendung,
        )
        lauf.kontiert += 1
    return lauf
