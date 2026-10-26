"""Ordnung: Belegbezug, plausible offene Posten, Festschreibung (GoBD Rz. 61 ff.)"""

from __future__ import annotations

from datetime import date, datetime

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
# Journalvorgänge, mit denen eine Buchung neu in die Kennziffern eingeht
_GEBUCHT = frozenset({"buchung_angelegt", "storno_gebucht", "buchung_korrigiert"})


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
            if abs(op.restbetrag) > abs(op.betrag) or (
                op.betrag > 0 and op.restbetrag < 0
            ):
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


class AbgegebenAbweichend:
    """Buchungen, die laut Journal nach der Abgabe einer Umsatzsteuer-Voranmeldung in
    ihrem Zeitraum angelegt oder korrigiert wurden (Storno, Neubuchung, Nachbuchung)
    und deren Kennziffern sie ändern — dann ist eine berichtigte Anmeldung abzugeben
    (§ 153 Abs. 1 AO, § 18 Abs. 1 UStG). Ein Storno mit gleich hoher Neubuchung
    hebt sich auf und wird nicht gemeldet; den genauen Vergleich mit den abgegebenen
    Werten macht ``accounti ustva`` (Befund ``abgegeben_abweichend``)."""

    name = "abgegeben_abweichend"
    kategorie = Kategorie.ORDNUNG
    schwere = Schwere.WARNUNG
    beschreibung = "Buchungen ändern eine schon abgegebene Umsatzsteuer-Voranmeldung"

    class Parameter(BaseModel):
        pass

    def pruefe(self, k: Kontext, p: Parameter) -> list[Befund]:
        from accounti.db.repo_elster import lade_uebermittlungen
        from accounti.db.repository import lade_bankkonten
        from accounti.models.elster import Meldeart, Modus
        from accounti.pruefung.journal import journal_vorhanden, lade_journal
        from accounti.steuer.kennziffern import Kontenplan, ermittle
        from accounti.steuer.zeitraum import Zeitraum, ZeitraumError

        abgaben: dict[str, datetime] = {}
        for u in lade_uebermittlungen(k.session, Meldeart.USTVA, modus=Modus.ECHT):
            if u.erfolgreich:
                abgaben[u.zeitraum] = max(
                    u.zeitpunkt, abgaben.get(u.zeitraum, u.zeitpunkt)
                )
        if not abgaben or not journal_vorhanden(k.session.connection()):
            return []
        erste = min(abgaben.values())
        erfasst: dict[str, datetime] = {}  # Buchung → letzte Anlage/Korrektur
        for j in lade_journal(k.session, von=erste.date()):
            if j.objekt_typ == "buchung" and j.vorgang in _GEBUCHT:
                erfasst[j.objekt_id] = j.zeitpunkt
        b = k.buchhaltung
        plan = Kontenplan(
            kontenrahmen=b.kontenrahmen.upper(),
            debitoren=(b.debitoren_von, b.debitoren_bis),
            kreditoren=(b.kreditoren_von, b.kreditoren_bis),
            geldkonten=frozenset(
                {b.bank_konto, *(x.sachkonto for x in lade_bankkonten(k.session))}
            ),
        )
        befunde = []
        for text, zeitpunkt in sorted(abgaben.items()):
            try:
                z = Zeitraum.lies(text)
            except ZeitraumError:
                continue
            if not (k.im_zeitraum(z.von) or k.im_zeitraum(z.bis)):
                continue
            neu = [
                x
                for x in k.buchungen
                if z.enthaelt(x.datum)
                and str(x.id) in erfasst
                and erfasst[str(x.id)] > zeitpunkt
            ]
            if not neu:
                continue
            e = ermittle(neu, z, plan)
            if not (
                any(w for w in e.voranmeldung.werte.values())
                or e.offen
                or e.ohne_kennziffer
            ):
                continue
            ids = ", ".join(str(x.id)[:8] for x in neu[:5]) + (
                " …" if len(neu) > 5 else ""
            )
            befunde.append(
                befund(
                    self,
                    "voranmeldung",
                    text,
                    f"Umsatzsteuer-Voranmeldung {text} am {zeitpunkt:%d.%m.%Y} "
                    f"abgegeben, danach {len(neu)} Buchung(en) im Zeitraum angelegt "
                    f"({ids}), die ihre Kennziffern ändern",
                    datum=z.bis,
                    abhilfe=(
                        f"berichtigte Voranmeldung abgeben (accounti ustva --period "
                        f"{text}; Kz 10)"
                    ),
                )
            )
        return befunde


for _regel in (
    BuchungOhneBeleg(),
    OpAlter(),
    PeriodeNichtFestgeschrieben(),
    AbgegebenAbweichend(),
):
    registriere_pruefregel(_regel)
