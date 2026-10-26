"""Ordnung: Belegbezug, plausible offene Posten, Festschreibung (GoBD Rz. 61 ff.)"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import select

from accounti.anzeige import betrag_de, datum_de
from accounti.db.tabellen_abschluss import AbgrenzungRow, AbschlussRow
from accounti.db.tabellen_anlagen import AfaVorgangRow
from accounti.db.tabellen_pruefung import PeriodenabschlussRow
from accounti.models import PostenStatus
from accounti.models.pruefung import Befund, Kategorie, Schwere
from accounti.pruefung.regeln import Kontext, befund, registriere_pruefregel
from accounti.pruefung.regeln.zeitgerechtheit import ende_folgemonat

SALDENVORTRAG = frozenset({"9000", "9008", "9009"})


class BuchungOhneBeleg:
    name = "buchung_ohne_beleg"
    kategorie = Kategorie.ORDNUNG
    schwere = Schwere.WARNUNG
    beschreibung = "Buchung ohne Belegbezug und ohne Begründung für Belegfreiheit"

    class Parameter(BaseModel):
        pass

    def _eigenbelege(self, k: Kontext) -> set[str]:
        """Buchungen, deren Beleg ein Vorgang in accounti ist (AfA, Abgrenzung)."""
        ids: set[str] = set()
        for (buchung_id,) in k.session.execute(select(AfaVorgangRow.buchung_id)):
            if buchung_id:
                ids.add(str(buchung_id))
        for a, b in k.session.execute(
            select(
                AbgrenzungRow.abgrenzung_buchung_id, AbgrenzungRow.aufloesung_buchung_id
            )
        ):
            ids |= {str(x) for x in (a, b) if x}
        return ids

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        eigen = self._eigenbelege(k)
        storniert = {str(x.storno_von) for x in k.buchungen if x.storno_von is not None}
        befunde = []
        for x in k.buchungen:
            if x.beleg_id is not None or x.transaktion_id is not None:
                continue  # Umsätze ohne Beleg meldet umsatz_ohne_beleg
            if not k.im_zeitraum(x.datum) or str(x.id) in eigen:
                continue
            if {x.soll_konto, x.haben_konto} & SALDENVORTRAG:
                continue  # Eröffnung und Saldovortrag
            if x.storno_von is not None or str(x.id) in storniert:
                continue
            if k.einstellungen.belegfrei_nach_regel(x.buchungstext, None):
                continue
            befunde.append(
                befund(
                    self,
                    "buchung",
                    x.id,
                    f"Buchung {str(x.id)[:8]} vom {datum_de(x.datum)} "
                    f"({x.soll_konto} an {x.haben_konto}, "
                    f"{betrag_de(x.betrag_netto)} €, "
                    f"„{x.buchungstext}“) ohne Beleg und ohne Begründung",
                    datum=x.datum,
                    betrag=x.betrag_netto,
                    abhilfe="Beleg zuordnen oder Eigenbeleg erstellen",
                )
            )
        return befunde


class OpAlter:
    name = "op_alter"
    kategorie = Kategorie.ORDNUNG
    schwere = Schwere.WARNUNG
    beschreibung = "Offene Posten mit unplausiblem Alter oder Restbetrag"

    class Parameter(BaseModel):
        max_tage: int = Field(default=365, ge=1)

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        befunde = []
        for op in k.posten:
            if op.status is PostenStatus.AUSGEGLICHEN:
                continue
            if not k.im_zeitraum(op.belegdatum):
                continue
            kontakt = k.kontakte.get(op.kontakt_id)
            wer = kontakt.name if kontakt else None
            alter = (k.stichtag - op.belegdatum).days
            text = None
            schwere = self.schwere
            if op.restbetrag * op.betrag < 0:
                # Überzahlung bzw. zu hohe Erstattung: der Rest kehrt das Vorzeichen um
                # und steht als Guthaben bzw. Nachforderung offen — kein Fehler
                art = "Guthaben" if op.betrag > 0 else "Restbetrag"
                text = (
                    f"{art} {betrag_de(abs(op.restbetrag))} € (Betrag "
                    f"{betrag_de(op.betrag)} €, überzahlt bzw. zu viel erstattet) — "
                    "erstatten oder verrechnen (accounti opos zuordnen --transaktion, "
                    "accounti opos verrechnen)"
                )
                schwere = Schwere.HINWEIS
            elif abs(op.restbetrag) > abs(op.betrag):
                text = (
                    f"Restbetrag {betrag_de(op.restbetrag)} € passt nicht zum Betrag "
                    f"{betrag_de(op.betrag)} €"
                )
                schwere = Schwere.FEHLER
            elif op.faellig_am < op.belegdatum:
                text = f"fällig am {datum_de(op.faellig_am)}, vor dem Belegdatum"
            elif alter > p.max_tage:
                text = f"seit {alter} Tagen offen — ausbuchen, mahnen oder klären"
            if text is None:
                continue
            befunde.append(
                befund(
                    self,
                    "posten",
                    op.id,
                    f"Offener Posten {op.belegnummer or '—'} vom "
                    f"{datum_de(op.belegdatum)} ({wer or '—'}): {text}",
                    schwere=schwere,
                    datum=op.belegdatum,
                    betrag=op.restbetrag,
                    gegenpartei=wer,
                )
            )
        return befunde


class PeriodeNichtFestgeschrieben:
    name = "periode_nicht_festgeschrieben"
    kategorie = Kategorie.ORDNUNG
    schwere = Schwere.HINWEIS
    beschreibung = "Monat nach Ablauf des Folgemonats noch nicht festgeschrieben"

    class Parameter(BaseModel):
        pass

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        gesperrt = set(
            k.session.execute(
                select(PeriodenabschlussRow.monat).where(
                    PeriodenabschlussRow.gesperrt.is_(True)
                )
            ).scalars()
        )
        jahre = set(
            k.session.execute(
                select(AbschlussRow.jahr).where(AbschlussRow.gesperrt.is_(True))
            ).scalars()
        )
        monate = sorted({f"{x.datum:%Y-%m}" for x in k.buchungen})
        befunde = []
        for monat in monate:
            erster = date(int(monat[:4]), int(monat[5:]), 1)
            if monat in gesperrt or erster.year in jahre or not k.im_zeitraum(erster):
                continue
            if k.stichtag <= ende_folgemonat(erster):
                continue
            befunde.append(
                befund(
                    self,
                    "periode",
                    monat,
                    f"Monat {monat} ist noch nicht festgeschrieben — spätestens mit "
                    "der Umsatzsteuer-Voranmeldung (accounti periode schliessen "
                    f"{monat})",
                    datum=erster,
                )
            )
        return befunde


class PersonenkontoOffenePosten:
    """Saldo eines Kreditoren-/Debitorenkontos = Summe seiner offenen Posten
    (Hauptbuch und Nebenbuch, GoBD Rz. 58 ff.; ``opos/abstimmung.py``)."""

    name = "personenkonto_op"
    kategorie = Kategorie.ORDNUNG
    schwere = Schwere.WARNUNG
    beschreibung = "Saldo eines Personenkontos weicht von seinen offenen Posten ab"

    class Parameter(BaseModel):
        pass

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        from accounti.abschluss.kontenrahmen import lade_kontenrahmen
        from accounti.db.repository import lade_zuordnungen
        from accounti.opos.abstimmung import abweichungen, befundtext

        stichtag = min(k.bis, k.stichtag) if k.bis else k.stichtag
        return [
            befund(
                self,
                "kontakt",
                a.kontakt.id,
                befundtext(a, stichtag),
                datum=stichtag,
                betrag=a.differenz,
                gegenpartei=a.kontakt.name,
                abhilfe="Buchungen und Posten des Kontos vergleichen (accounti "
                f"kontakte zeigen {a.konto}); falsche Buchung korrigieren",
            )
            for a in abweichungen(
                stichtag,
                lade_kontenrahmen(k.buchhaltung.kontenrahmen),
                k.buchungen,
                k.posten,
                k.kontakte,
                lade_zuordnungen(k.session),
                k.transaktionen,
            )
        ]


for _regel in (
    BuchungOhneBeleg(),
    OpAlter(),
    PeriodeNichtFestgeschrieben(),
    PersonenkontoOffenePosten(),
):
    registriere_pruefregel(_regel)
