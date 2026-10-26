"""Vollständigkeit: fehlt etwas? (§ 146 Abs. 1 AO, GoBD Rz. 36 ff.)"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select

from accounti.anzeige import betrag_de, datum_de
from accounti.bank.abgleichslauf import offen_in_der_bank
from accounti.db.repo_aufgaben import lade_aufgaben
from accounti.db.repository import lade_bankkonten
from accounti.db.tabellen_abschluss import KontoauszugssaldoRow
from accounti.export.kontoauszuege import pruefe_auszuege
from accounti.models import (
    Belegart,
    Belegrichtung,
    PostenRichtung,
    PostenStatus,
    Transaktion,
)
from accounti.models.aufgaben import AufgabenStatus, Objekt
from accounti.models.pruefung import Befund, Kategorie, Schwere
from accounti.pruefung.regeln import Kontext, befund, registriere_pruefregel

NULL = Decimal("0")


def begruendet_belegfrei(k: Kontext) -> dict[UUID, str]:
    """Umsätze, deren Aufgabe „Beleg fehlt“ ein Mensch mit Begründung erledigt hat."""
    erledigt = lade_aufgaben(
        k.session, status={AufgabenStatus.ERLEDIGT}, art="beleg_fehlt"
    )
    ergebnis = {}
    for a in erledigt:
        if a.objekt_typ != "transaktion":
            continue
        try:
            ergebnis[UUID(a.objekt_id)] = a.abschluss_grund or "erledigt"
        except ValueError:
            continue
    return ergebnis


def ohne_beleg(k: Kontext) -> list[Transaktion]:
    """Umsätze ohne Beleg: kein bestätigter Abgleich, keine Zahlungszuordnung und
    keine Buchung mit Beleg (z.B. Kreditkarten-Sammelbelastung)."""
    belegt = {b.transaktion_id for b in k.buchungen if b.transaktion_id and b.beleg_id}
    return [
        t
        for t in offen_in_der_bank(k.session).umsaetze_ohne_beleg
        if t.id not in belegt
    ]


class UmsatzOhneBeleg:
    name = "umsatz_ohne_beleg"
    kategorie = Kategorie.VOLLSTAENDIGKEIT
    schwere = Schwere.WARNUNG
    beschreibung = "Bankumsatz ohne zugeordneten Beleg (ab Betrag, nach Tagen)"

    class Parameter(BaseModel):
        ab_betrag: Decimal = Field(default=NULL, ge=0)
        nach_tagen: int = Field(default=0, ge=0)

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        begruendet = begruendet_belegfrei(k)
        befunde = []
        for tx in ohne_beleg(k):
            if not k.im_zeitraum(tx.datum) or abs(tx.betrag) < p.ab_betrag:
                continue
            if (k.stichtag - tx.datum).days < p.nach_tagen or tx.id in begruendet:
                continue
            if k.einstellungen.belegfrei_nach_regel(
                tx.verwendungszweck, tx.gegenkonto_name
            ):
                continue
            wer = tx.gegenkonto_name or "unbekannte Gegenpartei"
            befunde.append(
                befund(
                    self,
                    "transaktion",
                    tx.id,
                    f"Zahlung ohne Beleg: {datum_de(tx.datum)}, "
                    f"{betrag_de(tx.betrag)} €, {wer} — {tx.verwendungszweck}",
                    datum=tx.datum,
                    betrag=tx.betrag,
                    gegenpartei=tx.gegenkonto_name,
                    abhilfe=(
                        "Beleg erfassen und abgleichen (accounti belege import, "
                        "accounti bank abgleich) oder nachfordern (accounti "
                        "nachfordern); belegfrei nur mit Begründung"
                    ),
                )
            )
        return befunde


class BelegOhneZahlung:
    name = "beleg_ohne_zahlung"
    kategorie = Kategorie.VOLLSTAENDIGKEIT
    schwere = Schwere.WARNUNG
    beschreibung = "Rechnung nach Zahlungsziel ohne Zahlung, Quittung ohne Umsatz"

    class Parameter(BaseModel):
        karenz_tage: int = Field(default=0, ge=0, description="nach Fälligkeit")
        quittung_tage: int = Field(default=30, ge=0, description="nach Belegdatum")

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        befunde = []
        for op in k.posten:
            if op.status is PostenStatus.AUSGEGLICHEN or op.restbetrag <= 0:
                continue
            if not k.im_zeitraum(op.belegdatum):
                continue
            ueber = (k.stichtag - op.faellig_am).days
            if ueber <= p.karenz_tage:
                continue
            kontakt = k.kontakte.get(op.kontakt_id)
            eingang = op.richtung is PostenRichtung.VERBINDLICHKEIT
            art = "Eingangsrechnung" if eingang else "Ausgangsrechnung"
            zahlung = (
                f"Teilzahlung, Rest {betrag_de(op.restbetrag)} € offen"
                if op.restbetrag < op.betrag
                else "keine Zahlung zugeordnet"
            )
            befunde.append(
                befund(
                    self,
                    "posten",
                    op.id,
                    f"{art} {op.belegnummer or '—'} vom {datum_de(op.belegdatum)} "
                    f"über {betrag_de(op.betrag)} € seit {ueber} Tagen fällig — "
                    f"{zahlung}",
                    schwere=Schwere.WARNUNG if eingang else Schwere.HINWEIS,
                    datum=op.faellig_am,
                    betrag=op.restbetrag,
                    gegenpartei=kontakt.name if kontakt else None,
                    abhilfe=(
                        "Zahlung zuordnen (accounti opos zuordnen) oder klären"
                        if eingang
                        else "Mahnwesen (accounti mahnwesen lauf)"
                    ),
                )
            )
        for b in offen_in_der_bank(k.session).belege_ohne_umsatz:
            tag = b.belegdatum or b.eingegangen_am.date()
            if not k.im_zeitraum(tag) or (k.stichtag - tag).days <= p.quittung_tage:
                continue
            befunde.append(
                befund(
                    self,
                    "beleg",
                    b.id,
                    f"Beleg {b.belegnummer or b.dateiname} vom {datum_de(tag)} über "
                    f"{betrag_de(b.brutto)} € ohne Bankumsatz "
                    "(bar oder privat bezahlt?)",
                    schwere=Schwere.HINWEIS,
                    datum=tag,
                    betrag=b.brutto,
                    gegenpartei=b.lieferant_name,
                    abhilfe="Umsatz abgleichen (accounti bank abgleich) oder Kasse",
                )
            )
        return befunde


_LETZTE_ZAHL = re.compile(r"(\d+)(?!.*\d)")


class NummernkreisLuecke:
    name = "nummernkreis_luecke"
    kategorie = Kategorie.VOLLSTAENDIGKEIT
    schwere = Schwere.WARNUNG
    beschreibung = "Lücken und Doppel in den Nummern der Ausgangsrechnungen, Kassenbuch"

    class Parameter(BaseModel):
        max_anzeigen: int = Field(default=10, ge=1)

    def _ausgang(self, k: Kontext, p: Parameter) -> list[Befund]:
        jahre = (
            set(range(k.von.year, k.bis.year + 1))
            if k.von is not None and k.bis is not None
            else None
        )
        kreise: dict[tuple[str, int], dict[int, list[UUID]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for b in k.belege.values():
            if (
                b.richtung is not Belegrichtung.AUSGANG
                or b.belegart is not Belegart.AUSGANGSRECHNUNG
                or not b.belegnummer
                or b.belegdatum is None
            ):
                continue
            m = _LETZTE_ZAHL.search(b.belegnummer)
            if m is None:
                continue
            praefix = b.belegnummer[: m.start()] + "#" + b.belegnummer[m.end() :]
            kreise[(praefix, b.belegdatum.year)][int(m.group(1))].append(b.id)
        befunde = []
        for (praefix, jahr), nummern in sorted(kreise.items()):
            if jahre is not None and jahr not in jahre:
                continue
            vorhanden = sorted(nummern)
            fehlend = sorted(set(range(vorhanden[0], vorhanden[-1] + 1)) - set(nummern))
            if fehlend:
                liste = ", ".join(str(n) for n in fehlend[: p.max_anzeigen])
                rest = len(fehlend) - p.max_anzeigen
                befunde.append(
                    befund(
                        self,
                        "nummernkreis",
                        f"{praefix}/{jahr}",
                        f"Ausgangsrechnungen {praefix} ({jahr}): Nummer "
                        f"{liste}{f' und {rest} weitere' if rest > 0 else ''} fehlt "
                        f"zwischen {vorhanden[0]} und {vorhanden[-1]}",
                        abhilfe="fehlende Rechnung erfassen oder Lücke begründen",
                    )
                )
            for nr, ids in sorted(nummern.items()):
                if len(ids) > 1:
                    befunde.append(
                        befund(
                            self,
                            "beleg",
                            ids[-1],
                            f"Rechnungsnummer {praefix.replace('#', str(nr))} ({jahr}) "
                            f"{len(ids)}-mal vergeben "
                            "(§ 14 Abs. 4 Nr. 4 UStG: einmalig)",
                            schwere=Schwere.FEHLER,
                        )
                    )
        return befunde

    def _kasse(self, k: Kontext) -> list[Befund]:
        from accounti.db.repo_kasse import lade_kassenbuch

        nummern = sorted(v.nr for v in lade_kassenbuch(k.session))
        if not nummern:
            return []
        fehlend = sorted(set(range(1, nummern[-1] + 1)) - set(nummern))
        if not fehlend:
            return []
        return [
            befund(
                self,
                "kassenbuch",
                "kasse",
                f"Kassenbuch: Eintrag {', '.join(map(str, fehlend[:10]))} fehlt",
                schwere=Schwere.FEHLER,
            )
        ]

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        return self._ausgang(k, p) + self._kasse(k)


def _monate(von: date, bis: date) -> list[str]:
    monate, tag = [], date(von.year, von.month, 1)
    while tag <= bis:
        monate.append(f"{tag:%Y-%m}")
        tag = (tag.replace(day=28) + timedelta(days=4)).replace(day=1)
    return monate


class KontoauszugLuecke:
    name = "kontoauszug_luecke"
    kategorie = Kategorie.VOLLSTAENDIGKEIT
    schwere = Schwere.FEHLER
    beschreibung = "Kontoauszüge: Nummern-/Zeitlücken, Saldoverlauf, Monate ohne Umsatz"

    class Parameter(BaseModel):
        monate_ohne_umsatz: bool = True

    def _auszuege(self, k: Kontext) -> list[Befund]:
        return [
            befund(
                self,
                "kontoauszug",
                f"{a.finanzkonto}/{a.jahr}/{a.nummer}",
                a.text,
                abhilfe="accounti datev kontoauszuege (festgeschriebene Auszüge)",
            )
            for a in pruefe_auszuege(k.session)
            if a.jahr is None or k.von is None or k.von.year <= a.jahr
        ]

    def _salden(self, k: Kontext) -> list[Befund]:
        befunde = []
        zeilen = k.session.execute(
            select(KontoauszugssaldoRow).order_by(
                KontoauszugssaldoRow.bankkonto_id,
                KontoauszugssaldoRow.stichtag,
                KontoauszugssaldoRow.erfasst_am,
            )
        ).scalars()
        je_konto: dict[str, dict[date, Decimal]] = defaultdict(dict)
        for z in zeilen:  # der zuletzt erfasste Saldo je Stichtag gilt
            je_konto[z.bankkonto_id][z.stichtag] = Decimal(str(z.saldo))
        konten = {str(b.id): b for b in lade_bankkonten(k.session)}
        for konto_id, salden in je_konto.items():
            tage = sorted(salden)
            for alt, neu in zip(tage, tage[1:], strict=False):
                if not k.im_zeitraum(neu):
                    continue
                umsaetze = sum(
                    (
                        t.betrag
                        for t in k.transaktionen.values()
                        if str(t.bankkonto_id) == konto_id and alt < t.datum <= neu
                    ),
                    NULL,
                )
                differenz = salden[neu] - salden[alt] - umsaetze
                if differenz:
                    konto = konten.get(konto_id)
                    name = konto.iban if konto else konto_id[:8]
                    befunde.append(
                        befund(
                            self,
                            "bankkonto",
                            konto_id,
                            f"Konto {name}: Saldo {datum_de(alt)} "
                            f"{betrag_de(salden[alt])} € → {datum_de(neu)} "
                            f"{betrag_de(salden[neu])} €, Umsätze dazwischen "
                            f"{betrag_de(umsaetze)} € — es fehlen Umsätze über "
                            f"{betrag_de(differenz)} € (Kontoauszug fehlt?)",
                            datum=neu,
                            betrag=differenz,
                        )
                    )
        return befunde

    def _ohne_umsatz(self, k: Kontext) -> list[Befund]:
        je_konto: dict[str, list[date]] = defaultdict(list)
        for t in k.transaktionen.values():
            konto = t.sachkonto or k.buchhaltung.bank_konto
            je_konto[konto].append(t.datum)
        befunde = []
        for konto, tage in sorted(je_konto.items()):
            mit_umsatz = {f"{d:%Y-%m}" for d in tage}
            for monat in _monate(min(tage), max(tage)):
                erster = date(int(monat[:4]), int(monat[5:]), 1)
                if monat in mit_umsatz or not k.im_zeitraum(erster):
                    continue
                befunde.append(
                    befund(
                        self,
                        "finanzkonto",
                        f"{konto}/{monat}",
                        f"Finanzkonto {konto}: kein Umsatz im {monat} zwischen dem "
                        "ersten und letzten Umsatz — Kontoauszug vollständig "
                        "importiert?",
                        schwere=Schwere.HINWEIS,
                        datum=erster,
                    )
                )
        return befunde

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        befunde = self._auszuege(k) + self._salden(k)
        if p.monate_ohne_umsatz:
            befunde += self._ohne_umsatz(k)
        return befunde


for _regel in (
    UmsatzOhneBeleg(),
    BelegOhneZahlung(),
    NummernkreisLuecke(),
    KontoauszugLuecke(),
):
    registriere_pruefregel(_regel)

__all__ = ["Objekt", "begruendet_belegfrei", "ohne_beleg"]
