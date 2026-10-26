"""Anlagegut ändern und Abgang zurücknehmen (Gesamttest Abschluss B7).

Stammdaten eines Anlageguts sind keine Buchungen — sie lassen sich ändern, aber nur
mit Grund und mit Journaleintrag (``objekt_typ`` ``anlage``, vorher/nachher). Was
schon gebucht ist, bleibt: Die AfA wird nach dem Muster des AfA-Laufs neu gerechnet
(„Soll laut Plan minus schon gebucht“). Noch nicht freigegebene AfA-Vorschläge, die
nur dieses Gut betreffen, werden verworfen und neu vorgeschlagen; freigegebene AfA
bleibt stehen und bekommt eine AfA-Korrektur als Vorschlag (keine Löschung, GoBD
Rz. 58 ff.). Liegt gebuchte AfA in einem abgeschlossenen Jahr, ist die Änderung
gesperrt — dort wäre sie eine Bilanzberichtigung.

Ein Abgang lässt sich zurücknehmen, solange seine Buchungen (Restbuchwert, Erlös)
Vorschläge sind oder storniert wurden; die AfA-Vorschläge des Abgangs werden
verworfen bzw. per Korrektur ausgeglichen.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.anlagen.abgang import AbgangError
from accounti.anlagen.afa import plane, pruefe_anlage
from accounti.anlagen.dienst import AnlageError, finde_zugangsbuchung
from accounti.anlagen.konfiguration import AnlagenEinstellungen
from accounti.anlagen.lauf import AfaLaufErgebnis, afa_lauf
from accounti.anlagen.rechtsstand import Rechtsstand
from accounti.anzeige import betrag_de
from accounti.db.repo_abschluss import pruefe_jahr_offen
from accounti.db.repo_anlagen import (
    aktualisiere_anlage,
    lade_afa_vorgaenge,
    lade_anlage,
    lade_anlagen,
    loesche_afa_vorgaenge,
    verwirf_vorschlag,
)
from accounti.db.repository import lade_buchungen
from accounti.models import Buchungssatz, BuchungStatus
from accounti.models.anlagen import AfaArt, AfaVorgang, Anlagegut, sammelposten_objekt
from accounti.pruefung.journal import schreibe
from accounti.pruefung.person import journal_kontext

VORSCHLAG = frozenset({BuchungStatus.ENTWURF, BuchungStatus.ZUR_PRUEFUNG})
# Felder, die den AfA-Plan bestimmen
AFA_FELDER = (
    "konto",
    "afa_konto",
    "anschaffungsdatum",
    "anschaffungskosten",
    "nutzungsdauer",
    "afa_art",
    "wechsel_linear",
    "immateriell",
)
ABGANG_FELDER = ("abgang_datum", "abgang_art", "abgang_erloes")


@dataclass
class Neuberechnung:
    """Was die Änderung an Buchungen bewirkt hat."""

    verworfen: list[Buchungssatz] = field(default_factory=list)
    afa: list[AfaLaufErgebnis] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)

    @property
    def buchungen(self) -> list[Buchungssatz]:
        return [b for lauf in self.afa for b in lauf.buchungen]


@dataclass
class Aenderung:
    vorher: Anlagegut
    anlage: Anlagegut
    geaendert: dict[str, tuple[Any, Any]]
    neuberechnung: Neuberechnung = field(default_factory=Neuberechnung)


def _text(wert: Any) -> Any:
    if wert is None or isinstance(wert, bool | int | str):
        return wert
    if isinstance(wert, date):
        return wert.isoformat()
    return str(getattr(wert, "value", wert))


def _objekte(*anlagen: Anlagegut) -> set[str]:
    """Objektschlüssel der AfA-Vorgänge, die diese Güter betreffen — beim
    Sammelposten auch der Jahrgang (§ 6 Abs. 2a EStG: AfA je Sammelposten)."""
    objekte = set()
    for a in anlagen:
        objekte.add(a.objekt)
        if a.afa_art is AfaArt.SAMMELPOSTEN:
            objekte.add(sammelposten_objekt(a.konto, a.anschaffungsdatum.year))
    return objekte


def _verwirf_eigene_vorschlaege(
    session: Session, objekte: set[str], jahre: set[int] | None = None
) -> list[Buchungssatz]:
    """AfA-Vorschläge, deren Vorgänge nur ``objekte`` betreffen, samt Vorgängen
    verwerfen — eine Sammelbuchung mit anderen Gütern bleibt (dort korrigiert der
    AfA-Lauf)."""
    alle = lade_afa_vorgaenge(session)
    je_buchung: dict[UUID, list[AfaVorgang]] = defaultdict(list)
    for v in alle:
        if v.buchung_id is not None:
            je_buchung[v.buchung_id].append(v)
    kandidaten = {
        v.buchung_id
        for v in alle
        if v.objekt in objekte
        and v.buchung_id is not None
        and (jahre is None or v.jahr in jahre)
    }
    buchungen = {b.id: b for b in lade_buchungen(session, status=set(VORSCHLAG))}
    verworfen = []
    for bid in sorted(kandidaten, key=str):
        b = buchungen.get(bid)
        if b is None or any(v.objekt not in objekte for v in je_buchung[bid]):
            continue
        loesche_afa_vorgaenge(session, {v.id for v in je_buchung[bid]})
        verwirf_vorschlag(session, bid)
        verworfen.append(b)
    return verworfen


def _bis_monat(
    session: Session, objekte: set[str], einstellungen: AnlagenEinstellungen
) -> dict[tuple[int, int], int]:
    """Je Jahr und Abschnitt (erster Monat; bei abweichendem Wirtschaftsjahr zwei je
    Kalenderjahr, ``afa_abschnitt``) der späteste Monat, bis zu dem für die Objekte
    AfA gebucht ist."""
    bis: dict[tuple[int, int], int] = {}
    for v in lade_afa_vorgaenge(session):
        if v.objekt in objekte:
            schluessel = (v.jahr, einstellungen.afa_abschnitt(v.bis_monat)[0])
            bis[schluessel] = max(bis.get(schluessel, 0), v.bis_monat)
    return bis


def _neu_rechnen(
    session: Session,
    objekte: set[str],
    bis: dict[tuple[int, int], int],
    einstellungen: AnlagenEinstellungen,
    rs: Rechtsstand,
) -> list[AfaLaufErgebnis]:
    ergebnisse = []
    for (jahr, _), monat in sorted(bis.items()):
        lauf = afa_lauf(session, jahr, einstellungen, monat, objekte, rs)
        if lauf.buchungen:
            ergebnisse.append(lauf)
    return ergebnisse


def _pruefe_jahre_offen(session: Session, jahre: set[int]) -> None:
    for jahr in sorted(jahre):
        pruefe_jahr_offen(session, jahr)


def _hinweise(
    alt: Anlagegut,
    neu: Anlagegut,
    gebucht: Decimal,
    bis: dict[tuple[int, int], int],
    einstellungen: AnlagenEinstellungen,
    rs: Rechtsstand,
) -> list[str]:
    """Was die Neuberechnung nicht selbst bucht (Nachprüfung F, N7): Ein neues
    Anlagekonto lässt Zugang und gebuchte AfA auf dem alten, ein früheres
    Anschaffungsdatum braucht die AfA der Jahre davor."""
    hinweise = []
    if alt.konto != neu.konto:
        hinweise.append(
            f"Anlagekonto {alt.konto} → {neu.konto}: Zugang bzw. Eröffnungssaldo und "
            f"gebuchte AfA stehen weiter auf {alt.konto} — den Buchwert "
            f"{betrag_de(alt.anschaffungskosten - gebucht)} € umbuchen (Zugangs- "
            f"und AfA-Buchungen mit accounti korrigiere <ID> --soll … --haben … auf "
            f"{neu.konto}), sonst meldet abschluss pruefen Saldo ≠ Restbuchwert"
        )
    if bis and neu.anschaffungsdatum.year < alt.anschaffungsdatum.year:
        plan = plane(neu, rs)
        ab = einstellungen.afa_abschnitt(12)[0]  # abweichendes WJ: zwei Abschnitte
        gebuchte_jahre = {j for j, _ in bis}
        for jahr in range(neu.anschaffungsdatum.year, alt.anschaffungsdatum.year):
            if jahr in gebuchte_jahre or not plan.afa_im_jahr(jahr):
                continue
            zusatz = f" sowie --jahr {jahr} --bis-monat {ab - 1}" if ab > 1 else ""
            hinweise.append(
                f"AfA {jahr} fehlt (Anschaffung jetzt "
                f"{neu.anschaffungsdatum:%d.%m.%Y}): accounti anlagen afa --jahr "
                f"{jahr}{zusatz}"
            )
    return hinweise


def _journal(
    session: Session,
    vorgang: str,
    a: Anlagegut,
    vorher: dict[str, Any],
    nachher: dict[str, Any],
    grund: str | None,
) -> None:
    schreibe(
        session,
        vorgang,
        "anlage",
        str(a.id),
        vorher={"nr": a.nr, **{k: _text(w) for k, w in vorher.items()}},
        nachher={"nr": a.nr, **{k: _text(w) for k, w in nachher.items()}},
        grund=grund,
    )


def aendere_anlage(
    session: Session,
    schluessel: str,
    einstellungen: AnlagenEinstellungen,
    *,
    grund: str | None = None,
    bezeichnung: str | None = None,
    datum: date | None = None,
    kosten: Decimal | None = None,
    nutzungsdauer: int | None = None,
    art: AfaArt | None = None,
    konto: str | None = None,
    afa_konto: str | None = None,
    buchung: str | None = None,
    rechtsstand: Rechtsstand | None = None,
) -> Aenderung:
    """Ändert Stammdaten eines Anlageguts und rechnet die AfA neu (siehe Modul).

    Bezeichnung und Zugangsbuchung (``buchung``, Befund B11) ändern nichts am
    AfA-Plan; alles andere nur mit ``grund`` (steht im Journal)."""
    rs = rechtsstand or einstellungen.rechtsstand()
    alt = lade_anlage(session, schluessel)
    if alt.abgang_datum is not None:
        raise AnlageError(
            f"Anlagegut {alt.nr} ist am {alt.abgang_datum:%d.%m.%Y} abgegangen — "
            f"erst zurücknehmen: accounti anlagen abgang {alt.nr} --zuruecknehmen"
        )
    werte: dict[str, Any] = {
        "bezeichnung": bezeichnung,
        "anschaffungsdatum": datum,
        "anschaffungskosten": kosten,
        "nutzungsdauer": nutzungsdauer,
        "afa_art": art,
        "konto": konto,
        "afa_konto": afa_konto,
    }
    if buchung is not None:
        werte["buchung_id"] = finde_zugangsbuchung(session, buchung).id
    if art is AfaArt.DIGITAL and nutzungsdauer is None:
        werte["nutzungsdauer"] = 1  # BMF 22.02.2022
    update = {k: w for k, w in werte.items() if w is not None and getattr(alt, k) != w}
    if not update:
        raise AnlageError(f"Die Änderung ändert an Anlagegut {alt.nr} nichts")
    try:
        neu = Anlagegut.model_validate({**alt.model_dump(), **update})
    except ValueError as fehler:
        raise AnlageError(f"Anlagegut {alt.nr}: {fehler}") from fehler
    if neu.afa_art in (AfaArt.LINEAR, AfaArt.DEGRESSIV) and not neu.nutzungsdauer:
        raise AnlageError("Nutzungsdauer fehlt (--nutzungsdauer)")
    bestand = [a for a in lade_anlagen(session) if a.id != alt.id]
    pruefe_anlage(neu, rs, bestand)
    geaendert = {k: (getattr(alt, k), getattr(neu, k)) for k in update}
    ergebnis = Aenderung(alt, neu, geaendert)
    afa_relevant = set(update) & set(AFA_FELDER)
    if afa_relevant and not (grund or "").strip():
        raise AnlageError(
            f"Anlagegut {alt.nr}: {', '.join(sorted(afa_relevant))} ändern nur mit "
            'Grund (steht im Journal): --grund "…"'
        )
    with journal_kontext(grund=(grund or "").strip() or None):
        if afa_relevant:
            objekte = _objekte(alt, neu)
            bis = _bis_monat(session, objekte, einstellungen)
            _pruefe_jahre_offen(
                session,
                {j for j, _ in bis}
                | {alt.anschaffungsdatum.year, neu.anschaffungsdatum.year},
            )
            nb = ergebnis.neuberechnung
            nb.verworfen = _verwirf_eigene_vorschlaege(session, objekte)
            # was nach dem Verwerfen noch gebucht ist, steht auf dem alten Konto
            gebucht = sum(
                (v.betrag for v in lade_afa_vorgaenge(session) if v.objekt in objekte),
                Decimal(0),
            )
            aktualisiere_anlage(session, neu)
            nb.afa = _neu_rechnen(session, objekte, bis, einstellungen, rs)
            if not bis:
                nb.hinweise.append(
                    "Noch keine AfA gebucht — accounti anlagen afa --jahr … rechnet "
                    "mit den neuen Werten"
                )
            nb.hinweise += _hinweise(alt, neu, gebucht, bis, einstellungen, rs)
        else:
            aktualisiere_anlage(session, neu)
        _journal(
            session,
            "anlage_geaendert",
            neu,
            {k: v[0] for k, v in geaendert.items()},
            {k: v[1] for k, v in geaendert.items()},
            (grund or "").strip() or None,
        )
    session.flush()
    return ergebnis


@dataclass
class Ruecknahme:
    anlage: Anlagegut
    vorher: Anlagegut
    neuberechnung: Neuberechnung = field(default_factory=Neuberechnung)


def nimm_abgang_zurueck(
    session: Session,
    schluessel: str,
    einstellungen: AnlagenEinstellungen,
    grund: str,
    rechtsstand: Rechtsstand | None = None,
) -> Ruecknahme:
    """Nimmt einen Abgang zurück, solange Restbuchwert- und Erlösbuchung
    (Belegnummer ``ANL-<Nr>``) Vorschläge sind — freigegebene erst stornieren."""
    if not grund.strip():
        raise AbgangError("Grund für die Rücknahme fehlt (steht im Journal)")
    rs = rechtsstand or einstellungen.rechtsstand()
    alt = lade_anlage(session, schluessel)
    if alt.abgang_datum is None:
        raise AbgangError(f"Anlagegut {alt.nr} hat keinen Abgang")
    pruefe_jahr_offen(session, alt.abgang_datum.year)
    gueltig = [
        b
        for b in lade_buchungen(session)
        if b.beleg_nummer == f"ANL-{alt.nr}"
        and b.storno_von is None
        and b.storniert_durch is None
    ]
    freigegeben = [b for b in gueltig if b.status not in VORSCHLAG]
    if freigegeben:
        ids = ", ".join(str(b.id)[:8] for b in freigegeben)
        raise AbgangError(
            f"Abgangsbuchung {ids} zu Anlagegut {alt.nr} ist schon freigegeben — erst "
            "stornieren (accounti buchung storniere <ID> --grund …), dann zurücknehmen"
        )
    neu = alt.model_copy(update=dict.fromkeys(ABGANG_FELDER))
    ergebnis = Ruecknahme(neu, alt)
    nb = ergebnis.neuberechnung
    with journal_kontext(grund=grund.strip()):
        objekte = _objekte(alt)
        nb.verworfen = _verwirf_eigene_vorschlaege(
            session, objekte, {alt.abgang_datum.year}
        )
        for b in gueltig:
            verwirf_vorschlag(session, b.id)
            nb.verworfen.append(b)
        aktualisiere_anlage(session, neu)
        bis = {
            (j, ab): m
            for (j, ab), m in _bis_monat(session, objekte, einstellungen).items()
            if j == alt.abgang_datum.year
        }
        nb.afa = _neu_rechnen(session, objekte, bis, einstellungen, rs)
        if not bis:
            nb.hinweise.append(
                f"AfA {alt.abgang_datum.year} für dieses Gut erneut laufen lassen: "
                f"accounti anlagen afa --jahr {alt.abgang_datum.year}"
            )
        _journal(
            session,
            "anlage_abgang_zurueck",
            neu,
            {k: getattr(alt, k) for k in ABGANG_FELDER},
            dict.fromkeys(ABGANG_FELDER),
            grund.strip(),
        )
    session.flush()
    return ergebnis
