"""Zeitgerechtheit: zeitnah erfasst und gebucht? (§ 146 Abs. 1 AO, GoBD Rz. 46 ff.)"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select

from accounti.anzeige import betrag_de, datum_de
from accounti.db.repository import (
    gebuchte_beleg_ids,
    gebuchte_transaktion_ids,
    lade_abgleiche,
    lade_ausgangsrechnungen,
    verbuchte_beleg_ids,
)
from accounti.db.tabellen_abschluss import AbschlussRow
from accounti.db.tabellen_pruefung import PeriodenabschlussRow
from accounti.models import (
    AbgleichStatus,
    Belegart,
    Belegrichtung,
    BelegStatus,
    Buchungssatz,
    BuchungStatus,
)
from accounti.models.pruefung import Befund, Kategorie, Schwere
from accounti.pruefung.journal import lade_journal
from accounti.pruefung.regeln import Kontext, befund, registriere_pruefregel

VORSCHLAG = frozenset({BuchungStatus.ENTWURF, BuchungStatus.ZUR_PRUEFUNG})
_ANGELEGT = frozenset({"buchung_angelegt", "storno_gebucht"})
_UEBERNOMMEN = "bestand_uebernommen"  # Zeitpunkt der Buchung unbekannt


def _eb_buchung(x: Buchungssatz) -> bool:
    """EB-Buchung des Saldovortrags bzw. Eröffnungssaldos (abschluss/vortrag.py) —
    am 01.01. oder, bei abweichendem Wirtschaftsjahr, an dessen Beginn mit der
    Nummer des im Folgejahr endenden WJ (``EB-2026`` am 01.07.2025)."""
    nummer = x.beleg_nummer or ""
    return (
        (
            ((x.datum.month, x.datum.day) == (1, 1) and nummer.startswith("EB-"))
            or nummer == f"EB-{x.datum.year + 1}"
        )
        and x.transaktion_id is None
        and x.beleg_id is None
    )


def ende_folgemonat(tag: date) -> date:
    jahr, monat = (tag.year + 1, 1) if tag.month == 12 else (tag.year, tag.month + 1)
    return date(jahr, monat, monthrange(jahr, monat)[1])


def angelegt_am(k: Kontext) -> dict[str, datetime | None]:
    """Wann ist jede Buchung laut Journal entstanden? ``None``: Bestand von vor dem
    Journal, Zeitpunkt unbekannt; fehlt die Buchung ganz, hat sie keinen Eintrag."""
    ergebnis: dict[str, datetime | None] = {}
    for e in lade_journal(k.session):
        if e.objekt_typ != "buchung":
            continue
        if e.vorgang in _ANGELEGT:
            ergebnis.setdefault(e.objekt_id, e.zeitpunkt)
        elif e.vorgang == _UEBERNOMMEN:
            ergebnis.setdefault(e.objekt_id, None)
    return ergebnis


class BelegUnbearbeitet:
    name = "beleg_unbearbeitet"
    kategorie = Kategorie.ZEITGERECHTHEIT
    schwere = Schwere.WARNUNG
    beschreibung = "Beleg liegt länger als die Frist unbearbeitet (GoBD Rz. 47)"

    class Parameter(BaseModel):
        frist_tage: int = Field(default=10, ge=0)

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        verbucht = (
            gebuchte_beleg_ids(k.session)
            | verbuchte_beleg_ids(k.session)
            | {
                a.beleg_id
                for a in lade_abgleiche(k.session)
                if a.status is not AbgleichStatus.ABGELEHNT
            }
        )
        # bei Ausgangsrechnungen steht im Beleg die eigene Firma als Aussteller
        kunden = {
            r.beleg_id: r.kunde.name
            for r in lade_ausgangsrechnungen(k.session)
            if r.beleg_id is not None
        }
        befunde = []
        for b in k.belege.values():
            eingang = b.eingegangen_am.date()
            alter = (k.stichtag - eingang).days
            if alter <= p.frist_tage or not k.im_zeitraum(eingang):
                continue
            if b.status is not BelegStatus.ERFASST:
                grund = (
                    "noch nicht erfasst"
                    if b.status is BelegStatus.EINGEGANGEN
                    else (f"zur Prüfung: {b.pruef_grund or 'ohne Grund'}")
                )
            elif (
                b.belegart in (Belegart.EINGANGSRECHNUNG, Belegart.AUSGANGSRECHNUNG)
                and b.id not in verbucht
            ):
                grund = "erfasst, aber nicht gebucht (accounti opos verbuchen)"
            else:
                continue
            gegenpartei = (
                kunden.get(b.id)
                if b.richtung is Belegrichtung.AUSGANG
                else b.lieferant_name
            )
            befunde.append(
                befund(
                    self,
                    "beleg",
                    b.id,
                    f"Beleg {b.belegnummer or b.dateiname} ({gegenpartei or '—'}) "
                    f"seit {datum_de(eingang)} ({alter} Tage) unbearbeitet — {grund}",
                    datum=eingang,
                    betrag=b.brutto,
                    gegenpartei=gegenpartei,
                )
            )
        return befunde


class BuchungVerspaetet:
    name = "buchung_verspaetet"
    kategorie = Kategorie.ZEITGERECHTHEIT
    schwere = Schwere.HINWEIS
    beschreibung = "Gebucht erst nach Ablauf des Folgemonats (GoBD Rz. 50, 52)"

    class Parameter(BaseModel):
        zusatz_tage: int = Field(default=0, ge=0, description="nach dem Folgemonat")

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        angelegt = angelegt_am(k)
        korrekturen = {
            b.id for b in k.buchungen if b.storno_von or b.storniert_durch
        } | self._neubuchungen(k)
        befunde = []
        for x in k.buchungen:
            if x.transaktion_id is None and x.beleg_id is None:
                continue  # Abschluss, AfA, Abgrenzung: entstehen naturgemäß später
            if x.id in korrekturen or not k.im_zeitraum(x.datum):
                continue
            zeitpunkt = angelegt.get(str(x.id))
            if zeitpunkt is None:
                continue
            frist = ende_folgemonat(x.datum) + timedelta(days=p.zusatz_tage)
            if zeitpunkt.date() <= frist:
                continue
            befunde.append(
                befund(
                    self,
                    "buchung",
                    x.id,
                    f"Buchung {str(x.id)[:8]} (Geschäftsvorfall vom "
                    f"{datum_de(x.datum)}, {betrag_de(x.betrag_netto)} €) erst am "
                    f"{datum_de(zeitpunkt.date())} gebucht — nach Ablauf des "
                    "Folgemonats nur mit zeitnaher Grundaufzeichnung zulässig",
                    datum=x.datum,
                    betrag=x.betrag_netto,
                )
            )
        return befunde

    def _neubuchungen(self, k: Kontext) -> set[UUID]:
        from accounti.db.repo_pruefung import lade_korrekturen

        return {
            kk.neubuchung_id for kk in lade_korrekturen(k.session) if kk.neubuchung_id
        }


class BuchungInGesperrterPeriode:
    name = "buchung_in_gesperrter_periode"
    kategorie = Kategorie.ZEITGERECHTHEIT
    schwere = Schwere.FEHLER
    beschreibung = "Buchung oder Vorschlag mit Datum in einer abgeschlossenen Periode"

    class Parameter(BaseModel):
        pass

    def _sperren(self, k: Kontext) -> dict[str, datetime]:
        """Gesperrter Zeitraum (JJJJ bzw. JJJJ-MM) → seit wann."""
        sperren: dict[str, datetime] = {}
        for jahr, seit in k.session.execute(
            select(AbschlussRow.jahr, AbschlussRow.abgeschlossen_am).where(
                AbschlussRow.gesperrt.is_(True)
            )
        ):
            sperren[str(jahr)] = seit
        for monat, seit in k.session.execute(
            select(
                PeriodenabschlussRow.monat, PeriodenabschlussRow.geschlossen_am
            ).where(PeriodenabschlussRow.gesperrt.is_(True))
        ):
            sperren[monat] = seit
        return sperren

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        sperren = self._sperren(k)
        if not sperren:
            return []
        angelegt = angelegt_am(k)
        gebucht = gebuchte_transaktion_ids(k.session)
        befunde = []

        def sperre(tag: date) -> tuple[str, datetime] | None:
            for zeitraum in (f"{tag:%Y-%m}", str(tag.year)):
                if zeitraum in sperren:
                    return zeitraum, sperren[zeitraum]
            return None

        for x in k.buchungen:
            treffer = sperre(x.datum)
            if treffer is None or not k.im_zeitraum(x.datum):
                continue
            zeitraum, seit = treffer
            if "-" in zeitraum and _eb_buchung(x):
                continue  # Saldovortrag: nimmt die Monatssperre an (tabellen_pruefung)
            bekannt = str(x.id) in angelegt
            zeitpunkt = angelegt.get(str(x.id))
            if x.status in VORSCHLAG:
                text = (
                    f"Vorschlag {str(x.id)[:8]} vom {datum_de(x.datum)} liegt im "
                    f"abgeschlossenen Zeitraum {zeitraum} — er lässt sich nicht mehr "
                    "freigeben (Zeitraum öffnen oder verwerfen)"
                )
            elif not bekannt or (zeitpunkt is not None and zeitpunkt > seit):
                wann = (
                    f"am {datum_de(zeitpunkt.date())}"
                    if zeitpunkt
                    else "ohne Journaleintrag"
                )
                text = (
                    f"Buchung {str(x.id)[:8]} vom {datum_de(x.datum)} im seit "
                    f"{datum_de(seit.date())} abgeschlossenen Zeitraum {zeitraum} — "
                    f"angelegt {wann}, also nach dem Abschluss"
                )
            else:
                continue
            befunde.append(
                befund(
                    self,
                    "buchung",
                    x.id,
                    text,
                    datum=x.datum,
                    betrag=x.betrag_netto,
                )
            )
        for t in k.transaktionen.values():
            treffer = sperre(t.datum)
            if treffer is None or t.id in gebucht or not k.im_zeitraum(t.datum):
                continue
            befunde.append(
                befund(
                    self,
                    "transaktion",
                    t.id,
                    f"Umsatz vom {datum_de(t.datum)} ({betrag_de(t.betrag)} €, "
                    f"{t.gegenkonto_name or '—'}) im abgeschlossenen Zeitraum "
                    f"{treffer[0]} ist ungebucht",
                    schwere=Schwere.WARNUNG,
                    datum=t.datum,
                    betrag=t.betrag,
                    gegenpartei=t.gegenkonto_name,
                )
            )
        return befunde


for _regel in (BelegUnbearbeitet(), BuchungVerspaetet(), BuchungInGesperrterPeriode()):
    registriere_pruefregel(_regel)
