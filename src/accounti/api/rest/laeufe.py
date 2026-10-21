"""Läufe anstoßen: ``POST /api/v1/laeufe/bank`` und ``/laeufe/aufgaben``.

Dieselben Funktionen wie ``accounti bank lauf`` (abrufen → Kreditkarten → offene
Posten zuordnen → abgleichen → kontieren; ohne LLM) und ``accounti aufgaben lauf``
(Prüfläufe, Erinnerungen). Synchron; je Gesellschaft läuft jeder Lauf höchstens
einmal gleichzeitig — auch gegenüber dem Dienst ``lauf`` und der CLI
(``betrieb.laufsperre``, in der Datenbank) —, ein zweiter Aufruf bekommt 409.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from accounti.api.rest import TokenDb, Zugang, erfordert_recht
from accounti.betrieb.laufsperre import LaufLaeuftError, laufsperre
from accounti.models.auth import TokenRecht

router = APIRouter()

LaufRecht = Annotated[Zugang, Depends(erfordert_recht(TokenRecht.LAEUFE_STARTEN))]


def _bank(zugang: Zugang, s: Session) -> dict[str, Any]:
    from accounti.bank.einstellungen import lade_bank_einstellungen
    from accounti.bank.lauf import bank_lauf
    from accounti.klassifikation.engine import (
        STANDARD_REGELN,
        KlassifikationsEngine,
        RegelwerkEngine,
    )
    from accounti.klassifikation.regeln_loader import lade_regeln
    from accounti.konfiguration import lade_buchhaltung

    g = zugang.gesellschaft
    engine = KlassifikationsEngine(
        regelwerk=RegelwerkEngine(lade_regeln(g.regeln) + STANDARD_REGELN), llm=None
    )
    ergebnis = bank_lauf(
        s,
        engine,
        lade_buchhaltung(g.konfiguration),
        bank_einstellungen=lade_bank_einstellungen(g.konfiguration),
    )
    s.commit()
    z, a, k = ergebnis.zuordnung, ergebnis.abgleich, ergebnis.kontierung
    return {
        "lauf": "bank",
        "konten": [
            {
                "iban": abruf.konto.iban,
                "zustand": abruf.zustand.value,
                "neu": abruf.neu,
                "doppelt": abruf.doppelt,
                "uebersprungen": abruf.uebersprungen,
            }
            for abruf in ergebnis.abrufe
        ],
        "offene_posten": {
            "ausgeglichen": len(z.gebucht),
            "vorgeschlagen": len(z.vorgeschlagen),
        },
        "belege": {
            "abgeglichen": len(a.automatisch),
            "vorgeschlagen": len(a.vorschlaege),
        },
        "kontierung": {
            "kontiert": k.kontiert,
            "mit_beleg": k.mit_beleg,
            "offen": k.offen,
        },
    }


def _aufgaben(zugang: Zugang, s: Session) -> dict[str, Any]:
    from accounti.aufgaben.benachrichtigung import (
        baue_kanaele,
        versende_tagesuebersichten,
    )
    from accounti.aufgaben.einstellungen import lade_aufgaben_einstellungen
    from accounti.aufgaben.prueflaeufe import fuehre_prueflaeufe_aus

    pfad = zugang.gesellschaft.konfiguration
    einstellungen = lade_aufgaben_einstellungen(pfad)
    stichtag = date.today()
    jetzt = datetime.now()
    laeufe = fuehre_prueflaeufe_aus(s, einstellungen, stichtag=stichtag, jetzt=jetzt)
    s.commit()
    kanaele, kanalfehler = baue_kanaele(einstellungen, pfad)
    versand = versende_tagesuebersichten(
        s,
        einstellungen,
        kanaele,
        stichtag=stichtag,
        jetzt=jetzt,
        kanalfehler=kanalfehler,
        sichern=s.commit,
    )
    s.commit()
    return {
        "lauf": "aufgaben",
        "prueflaeufe": [
            {
                "name": e.name,
                "neu": len(e.abgleich.neu),
                "hinfaellig": len(e.abgleich.hinfaellig),
                "wieder_offen": len(e.abgleich.wieder_offen),
            }
            for e in laeufe
        ],
        "zustellungen": [
            {
                "kanal": z.kanal,
                "erfolgreich": z.erfolgreich,
                "uebersprungen": z.uebersprungen,
            }
            for z in versand.zustellungen
        ],
        "kanalfehler": sorted(kanalfehler),
    }


def _gesperrt(
    zugang: Zugang,
    art: str,
    lauf: Callable[[Zugang, Session], dict[str, Any]],
    s: Session,
) -> dict[str, Any]:
    try:
        with laufsperre(zugang.gesellschaft.datenbank, art):
            return lauf(zugang, s)
    except LaufLaeuftError as fehler:
        raise HTTPException(409, str(fehler)) from fehler


@router.post("/laeufe/bank")
async def bank_lauf(zugang: LaufRecht, s: TokenDb) -> dict[str, Any]:
    return await run_in_threadpool(_gesperrt, zugang, "bank", _bank, s)


@router.post("/laeufe/aufgaben")
async def aufgaben_lauf(zugang: LaufRecht, s: TokenDb) -> dict[str, Any]:
    return await run_in_threadpool(_gesperrt, zugang, "aufgaben", _aufgaben, s)
