"""Zwischenmodell → Beleg: was die E-Rechnung strukturiert liefert, landet 1:1 am Beleg.

Jede Rechnungszeile wird eine `Belegposition`, ebenso jeder Nachlass und Zuschlag
auf Belegebene. Die Steuer je Position wird so verteilt, dass ihre Summe je Kategorie
und Satz exakt der Steueraufschlüsselung der Rechnung (BG-23) entspricht.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from accounti.erechnung.modell import Rechnung
from accounti.erechnung.validierung import Befund, Schwere
from accounti.models import Beleg, Belegart, Belegposition, Belegrichtung, BelegStatus

CENT = Decimal("0.01")
NULL = Decimal("0")
# Gutschriften (UNTDID 1001) werden mit negativen Beträgen übernommen
GUTSCHRIFT_TYPEN = {"381", "261", "396", "532"}

_Schluessel = tuple[str | None, Decimal | None]


def _schluessel(kategorie: str | None, satz: Decimal | None) -> _Schluessel:
    return kategorie, (satz or NULL).normalize()


def _steuer(netto: Decimal, satz: Decimal | None) -> Decimal:
    if satz is None:
        return NULL
    return (netto * satz / 100).quantize(CENT, rounding=ROUND_HALF_UP)


def _positionen(r: Rechnung, beleg: Beleg) -> list[Belegposition]:
    roh: list[tuple[_Schluessel, Belegposition]] = []
    for z in r.zeilen:
        netto = z.netto or NULL
        roh.append(
            (
                _schluessel(z.steuerkategorie, z.steuersatz),
                Belegposition(
                    beleg_id=beleg.id,
                    bezeichnung=z.bezeichnung or f"Position {z.id}",
                    menge=z.menge if z.menge is not None else Decimal("1"),
                    netto=netto,
                    steuersatz=z.steuersatz,
                    steuer_betrag=_steuer(netto, z.steuersatz),
                ),
            )
        )
    for za in r.zu_abschlaege:
        betrag = za.betrag or NULL
        netto = betrag if za.zuschlag else -betrag
        art = "Zuschlag" if za.zuschlag else "Nachlass"
        roh.append(
            (
                _schluessel(za.steuerkategorie, za.steuersatz),
                Belegposition(
                    beleg_id=beleg.id,
                    bezeichnung=f"{art}: {za.grund}" if za.grund else art,
                    netto=netto,
                    steuersatz=za.steuersatz,
                    steuer_betrag=_steuer(netto, za.steuersatz),
                ),
            )
        )

    if not roh:
        # Reduzierte Profile: Aufschlüsselung je Satz, sonst eine Sammelposition.
        if r.steuern:
            return [
                Belegposition(
                    beleg_id=beleg.id,
                    bezeichnung=f"Netto {st.kategorie} {st.satz.normalize()} %"
                    if st.satz is not None
                    else f"Netto {st.kategorie}",
                    netto=st.basis or NULL,
                    steuersatz=st.satz,
                    steuer_betrag=st.betrag or NULL,
                )
                for st in r.steuern
            ]
        return [
            Belegposition(
                beleg_id=beleg.id,
                bezeichnung="Gesamtbetrag",
                netto=r.summen.netto or NULL,
                steuer_betrag=r.summen.steuer,
            )
        ]

    # Rundungsdifferenz je Satz auf die betragsmäßig größte Position der Gruppe legen.
    gruppen: dict[_Schluessel, list[int]] = defaultdict(list)
    for i, (schluessel, _) in enumerate(roh):
        gruppen[schluessel].append(i)
    for st in r.steuern:
        indizes = gruppen.get(_schluessel(st.kategorie, st.satz))
        if not indizes or st.betrag is None:
            continue
        ist = sum((roh[i][1].steuer_betrag or NULL for i in indizes), NULL)
        differenz = st.betrag - ist
        if differenz:
            groesste = max(indizes, key=lambda i: abs(roh[i][1].netto))
            pos = roh[groesste][1]
            roh[groesste] = (
                roh[groesste][0],
                pos.model_copy(
                    update={"steuer_betrag": (pos.steuer_betrag or NULL) + differenz}
                ),
            )
    return [pos for _, pos in roh]


def _negiert(positionen: list[Belegposition]) -> list[Belegposition]:
    return [
        p.model_copy(
            update={
                "netto": -p.netto,
                "steuer_betrag": -p.steuer_betrag
                if p.steuer_betrag is not None
                else None,
            }
        )
        for p in positionen
    ]


def zu_beleg(
    r: Rechnung,
    befunde: list[Befund],
    beleg: Beleg,
    eigene_ust_ids: set[str] | None = None,
) -> Beleg:
    """Überträgt Rechnung und Prüfergebnis auf den Beleg."""
    eigene = {u.replace(" ", "").upper() for u in eigene_ust_ids or set()}
    ausgang = bool(r.verkaeufer.ust_id) and (
        (r.verkaeufer.ust_id or "").replace(" ", "").upper() in eigene
    )
    gutschrift = r.typ in GUTSCHRIFT_TYPEN

    def betrag(wert: Decimal | None) -> Decimal | None:
        return -wert if gutschrift and wert is not None else wert

    positionen = _positionen(r, beleg)
    if gutschrift:
        positionen = _negiert(positionen)

    fehler = [b for b in befunde if b.schwere is Schwere.FEHLER]
    hinweise = [f"Fehler {b}" for b in fehler] + [
        f"Hinweis {b}" for b in befunde if b.schwere is Schwere.WARNUNG
    ]
    skonto = r.skonto

    return beleg.model_copy(
        update={
            "belegart": Belegart.AUSGANGSRECHNUNG
            if ausgang
            else Belegart.EINGANGSRECHNUNG,
            "richtung": Belegrichtung.AUSGANG if ausgang else Belegrichtung.EINGANG,
            "belegnummer": r.nummer,
            "belegdatum": r.datum,
            "leistungsdatum": r.leistungsdatum or r.leistungszeitraum_bis,
            "lieferant_name": r.verkaeufer.name,
            "lieferant_ust_id": r.verkaeufer.ust_id,
            "iban": r.iban,
            "netto": betrag(r.summen.netto),
            "steuer": betrag(r.summen.steuer),
            "brutto": betrag(r.summen.brutto),
            "waehrung": (r.waehrung or "EUR")[:3],
            "zahlungsziel": r.faellig,
            "skonto_prozent": skonto[0] if skonto else None,
            "skonto_tage": skonto[1] if skonto else None,
            "positionen": positionen,
            "status": BelegStatus.ZUR_PRUEFUNG if fehler else BelegStatus.ERFASST,
            "pruef_grund": "; ".join(hinweise) or None,
            "confidence": 0.5 if fehler else 1.0,
        }
    )
