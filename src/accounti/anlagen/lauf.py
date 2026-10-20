"""AfA-Lauf — bucht je Anlagegut die AfA laut Plan, soweit sie noch nicht gebucht ist.

Gerechnet wird „Soll bis Monat minus schon gebucht“ (Tabelle ``afa_vorgaenge``). Damit
ist der Lauf idempotent, monatlich wie jährlich nutzbar, und ein nachträglich erfasster
Abgang erzeugt eine Korrektur statt einer falschen Jahres-AfA. Frühere Jahre werden
bewusst nicht nachgeholt.

Abschlussbuchungen sind Vorschläge (Spec 5): Status „zur Prüfung“, die Begründung je
Anlagegut steht im Vorgang. Gebucht wird eine Buchung je AfA- und Anlagekonto.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session

from accounti.anlagen.afa import (
    AfaPlan,
    monatsende,
    plane,
    plane_sammelposten,
    sammelposten_mitglieder,
)
from accounti.anlagen.konfiguration import AnlagenEinstellungen
from accounti.anlagen.rechtsstand import Rechtsstand
from accounti.anzeige import betrag_de
from accounti.db.repo_abschluss import pruefe_jahr_offen
from accounti.db.repo_anlagen import (
    lade_afa_vorgaenge,
    lade_anlagen,
    speichere_afa_vorgang,
)
from accounti.db.repository import lade_buchungen, setze_status, speichere_buchung
from accounti.models import Buchungssatz, BuchungStatus
from accounti.models.anlagen import AfaArt, AfaVorgang, Anlagegut, sammelposten_objekt

_SAMMELPOSTEN = "sammelposten:"


def _sammelposten_aus_objekt(objekt: str) -> tuple[str, int] | None:
    """(Anlagekonto, Anschaffungsjahr) aus dem Schlüssel eines Sammelpostens."""
    if not objekt.startswith(_SAMMELPOSTEN):
        return None
    konto, _, jahr = objekt.removeprefix(_SAMMELPOSTEN).rpartition(":")
    return (konto, int(jahr)) if konto and jahr.isdigit() else None


NULL = Decimal("0")


@dataclass
class AfaPosition:
    objekt: str
    bezeichnung: str
    anlage: Anlagegut | None
    konto: str
    afa_konto: str
    soll: Decimal  # AfA des Jahres bis zum Monat laut Plan
    gebucht: Decimal
    rechenweg: str

    @property
    def differenz(self) -> Decimal:
        return self.soll - self.gebucht


@dataclass
class AfaLaufErgebnis:
    jahr: int
    bis_monat: int
    positionen: list[AfaPosition] = field(default_factory=list)
    buchungen: list[Buchungssatz] = field(default_factory=list)

    @property
    def summe(self) -> Decimal:
        return sum((p.differenz for p in self.positionen), NULL)


def _rechenweg(plan: AfaPlan, jahr: int) -> str:
    j = plan.jahr(jahr)
    return j.rechenweg if j is not None else "keine AfA in diesem Jahr"


def afa_positionen(
    session: Session,
    jahr: int,
    einstellungen: AnlagenEinstellungen,
    bis_monat: int = 12,
    rechtsstand: Rechtsstand | None = None,
) -> list[AfaPosition]:
    """Alle Anlagegüter und Sammelposten mit Soll und Gebuchtem für das Jahr.

    Auch ein Sammelposten ohne Mitglied gehört dazu, wenn für ihn im Jahr schon AfA
    gebucht ist — sein einziges Gut schied noch im Anschaffungsjahr aus (BMF
    30.09.2010, Rz. 10); das Soll ist dann 0 und der Lauf nimmt die AfA zurück.
    """
    rs = rechtsstand or einstellungen.rechtsstand()
    anlagen = lade_anlagen(session)
    gebucht: dict[str, Decimal] = defaultdict(lambda: NULL)
    for v in lade_afa_vorgaenge(session, jahr):
        gebucht[v.objekt] += v.betrag

    positionen: list[AfaPosition] = []
    gruppen: set[tuple[str, int]] = set()
    for a in anlagen:
        if a.afa_art is AfaArt.SAMMELPOSTEN and sammelposten_mitglieder(
            a.konto, a.anschaffungsdatum.year, [a]
        ):
            gruppen.add((a.konto, a.anschaffungsdatum.year))
            continue
        plan = plane(a, rs)
        soll = plan.afa_im_jahr(jahr, bis_monat)
        if soll == 0 and gebucht[a.objekt] == 0:
            continue
        positionen.append(
            AfaPosition(
                a.objekt,
                f"{a.bezeichnung} (Nr. {a.nr})",
                a,
                a.konto,
                einstellungen.afa_konto(a),
                soll,
                gebucht[a.objekt],
                _rechenweg(plan, jahr),
            )
        )
    gruppen |= {
        sp
        for objekt, betrag in gebucht.items()
        if betrag and (sp := _sammelposten_aus_objekt(objekt)) is not None
    }
    for konto, anschaffungsjahr in sorted(gruppen):
        objekt = sammelposten_objekt(konto, anschaffungsjahr)
        plan = plane_sammelposten(konto, anschaffungsjahr, anlagen, rs)
        soll = plan.afa_im_jahr(jahr, bis_monat)
        if soll == 0 and gebucht[objekt] == 0:
            continue
        # das AfA-Konto eines (auch ausgeschiedenen) Guts des Jahrgangs
        jahrgang = [
            a
            for a in anlagen
            if a.afa_art is AfaArt.SAMMELPOSTEN
            and a.konto == konto
            and a.anschaffungsdatum.year == anschaffungsjahr
        ]
        mitglieder = sammelposten_mitglieder(konto, anschaffungsjahr, anlagen)
        mitglied = next(iter(mitglieder or jahrgang), None)
        positionen.append(
            AfaPosition(
                objekt,
                f"Sammelposten {konto}/{anschaffungsjahr}",
                None,
                konto,
                einstellungen.afa_konto(mitglied)
                if mitglied
                else einstellungen.konten.sammelposten_afa,
                soll,
                gebucht[objekt],
                _rechenweg(plan, jahr),
            )
        )
    return positionen


def afa_lauf(
    session: Session,
    jahr: int,
    einstellungen: AnlagenEinstellungen,
    bis_monat: int = 12,
    nur: set[str] | None = None,
    rechtsstand: Rechtsstand | None = None,
) -> AfaLaufErgebnis:
    """Bucht die noch fehlende AfA des Jahres bis einschließlich ``bis_monat``.

    ``nur``: Objektschlüssel (``Anlagegut.objekt``, ``sammelposten_objekt``).
    """
    if not 1 <= bis_monat <= 12:
        raise ValueError(f"Monat {bis_monat} gibt es nicht")
    pruefe_jahr_offen(session, jahr)
    ergebnis = AfaLaufErgebnis(jahr, bis_monat)
    for p in afa_positionen(session, jahr, einstellungen, bis_monat, rechtsstand):
        if p.differenz == 0:
            continue
        if nur is not None and p.objekt not in nur:
            continue
        ergebnis.positionen.append(p)

    gruppen: dict[tuple[str, str, bool], list[AfaPosition]] = defaultdict(list)
    for p in ergebnis.positionen:
        gruppen[(p.afa_konto, p.konto, p.differenz < 0)].append(p)
    datum = monatsende(jahr, bis_monat)
    for (afa_konto, konto, korrektur), teile in sorted(gruppen.items()):
        betrag = abs(sum((p.differenz for p in teile), NULL))
        art = "AfA-Korrektur" if korrektur else "AfA"
        was = teile[0].bezeichnung if len(teile) == 1 else f"{konto} ({len(teile)})"
        buchung = Buchungssatz(
            datum=datum,
            soll_konto=konto if korrektur else afa_konto,
            haben_konto=afa_konto if korrektur else konto,
            betrag_netto=betrag,
            buchungstext=f"{art} {jahr} {was}"[:60],
            beleg_nummer=f"AfA-{jahr}-{bis_monat:02d}",
            status=BuchungStatus.ZUR_PRUEFUNG,
            confidence=1.0,
        )
        speichere_buchung(session, buchung)
        ergebnis.buchungen.append(buchung)
        for p in teile:
            begruendung = f"{p.bezeichnung}: {p.rechenweg}"
            if bis_monat < 12:
                begruendung += f"; bis {bis_monat:02d}/{jahr}"
            if p.gebucht:
                begruendung += (
                    f"; Soll {betrag_de(p.soll)} − schon gebucht {betrag_de(p.gebucht)}"
                )
            speichere_afa_vorgang(
                session,
                AfaVorgang(
                    objekt=p.objekt,
                    anlage_id=p.anlage.id if p.anlage else None,
                    jahr=jahr,
                    bis_monat=bis_monat,
                    betrag=p.differenz,
                    buchung_id=buchung.id,
                    begruendung=begruendung,
                ),
            )
    session.flush()
    return ergebnis


def freigeben(session: Session, jahr: int, von: str) -> int:
    """Gibt die AfA-Vorschläge eines Jahres frei; liefert die Anzahl."""
    ids = {v.buchung_id for v in lade_afa_vorgaenge(session, jahr) if v.buchung_id}
    offen = [
        b
        for b in lade_buchungen(session, status={BuchungStatus.ZUR_PRUEFUNG})
        if b.id in ids
    ]
    for b in offen:
        setze_status(session, str(b.id), BuchungStatus.GEPRUEFT, geprueft_von=von)
    session.flush()
    return len(offen)
