"""Zahlungslauf als Zustandsautomat: Entwurf → freigegeben → eingereicht → ausgeführt.

Storniert werden kann aus Entwurf, freigegeben und eingereicht; jeder andere Übergang
ist ein ``ZustandError``. Jede Freigabe wird mit Person und Zeitpunkt protokolliert,
das Protokoll kann nur wachsen. Ein freigegebener Lauf ist unveränderbar: Der
Freigabe-Hash hält fest, was freigegeben wurde; wer korrigieren will, storniert.

Mit ``zahlung.vier_augen`` braucht die Freigabe zwei verschiedene Personen. Eine
Freigabe gilt nur für den Inhalt, den sie gesehen hat — ändert sich der Entwurf
danach, zählt sie nicht mehr.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
from datetime import date, datetime

from sqlalchemy.orm import Session

from accounti.anzeige import betrag_de, datum_de
from accounti.db.repo_zahlung import (
    PostenImLaufError,
    aktualisiere_lauf,
    entferne_zahlung,
    gib_posten_frei,
    hebe_zahlungssperre_auf,
    lade_lauf,
    lade_protokoll,
    naechste_laufnummer,
    protokolliere,
    setze_zahlungssperre,
    speichere_iban_klaerung,
    speichere_lauf,
)
from accounti.db.repository import lade_beleg, lade_einen_posten, lade_kontakt
from accounti.models import Kontakt
from accounti.models.zahlung import (
    IbanKlaerung,
    LaufProtokoll,
    LaufStatus,
    Zahlung,
    Zahlungslauf,
    Zahlungssperre,
)
from accounti.zahlung.iban import lesbar, normalisiere
from accounti.zahlung.konfiguration import ZahlungEinstellungen
from accounti.zahlung.pruefung import Pruefergebnis, pruefe_lauf
from accounti.zahlung.sepa import referenz, verwendungszweck
from accounti.zahlung.vorschlag import Zahlungsvorschlag

UEBERGAENGE: dict[LaufStatus, frozenset[LaufStatus]] = {
    LaufStatus.ENTWURF: frozenset({LaufStatus.FREIGEGEBEN, LaufStatus.STORNIERT}),
    LaufStatus.FREIGEGEBEN: frozenset({LaufStatus.EINGEREICHT, LaufStatus.STORNIERT}),
    LaufStatus.EINGEREICHT: frozenset({LaufStatus.AUSGEFUEHRT, LaufStatus.STORNIERT}),
    LaufStatus.AUSGEFUEHRT: frozenset(),
    LaufStatus.STORNIERT: frozenset(),
}


class LaufError(RuntimeError):
    """Der Zahlungslauf kann so nicht angelegt oder geändert werden."""


class ZustandError(LaufError):
    """Der Übergang ist im Zustandsautomaten nicht vorgesehen."""


class LaufGesperrtError(LaufError):
    """Die Prüfung hat Befunde — der Lauf darf nicht weiter."""

    def __init__(self, ergebnis: Pruefergebnis) -> None:
        self.ergebnis = ergebnis
        zeilen = "\n".join(f"  {z}" for z in ergebnis.zeilen())
        anzahl = len(ergebnis.befunde)
        super().__init__(
            f"Lauf {ergebnis.lauf_nr} ist gesperrt — "
            f"{anzahl} Befund{'e' if anzahl != 1 else ''}:\n{zeilen}"
        )


def person_standard() -> str:
    """Wer handelt: ``ACCOUNTI_BENUTZER``, sonst der Anmeldename."""
    return os.environ.get("ACCOUNTI_BENUTZER") or getpass.getuser()


def pruefe_uebergang(lauf: Zahlungslauf, nach: LaufStatus) -> None:
    if nach not in UEBERGAENGE[lauf.status]:
        msg = (
            f"Lauf {lauf.nr}: Übergang {lauf.status.value} → {nach.value} ist nicht "
            "erlaubt"
        )
        raise ZustandError(msg)


def freigabe_hash(lauf: Zahlungslauf) -> str:
    """SHA-256 über alles, was die Bank bekommt — Auftraggeber, Termin, Zahlungen."""
    inhalt = {
        "lauf": lauf.nr,
        "ausfuehrung": lauf.ausfuehrung.isoformat(),
        "auftraggeber": [
            lauf.auftraggeber_name,
            lauf.auftraggeber_iban,
            lauf.auftraggeber_bic,
        ],
        "zahlungen": [
            [
                z.nr,
                str(z.posten_id),
                str(z.kontakt_id),
                z.empfaenger,
                z.iban,
                z.strasse,
                z.plz,
                z.ort,
                z.land,
                f"{z.betrag:.2f}",
                f"{z.skonto:.2f}",
                z.verwendungszweck,
                z.end_to_end_id,
            ]
            for z in lauf.zahlungen
        ],
    }
    roh = json.dumps(inhalt, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()


def _protokoll(
    session: Session,
    lauf: Zahlungslauf,
    person: str,
    aktion: str,
    text: str,
    von: LaufStatus | None = None,
    nach: LaufStatus | None = None,
) -> None:
    protokolliere(
        session,
        LaufProtokoll(
            lauf_id=lauf.id,
            person=person,
            aktion=aktion,
            von_status=von,
            nach_status=nach,
            text=text,
        ),
    )


def _wechsel(
    session: Session,
    lauf: Zahlungslauf,
    nach: LaufStatus,
    person: str,
    aktion: str,
    text: str,
    **felder: object,
) -> Zahlungslauf:
    pruefe_uebergang(lauf, nach)
    von = lauf.status
    neu = lauf.model_copy(update={"status": nach, **felder})
    aktualisiere_lauf(session, neu)
    if nach in (LaufStatus.STORNIERT, LaufStatus.AUSGEFUEHRT):
        gib_posten_frei(session, lauf.id)
    _protokoll(session, neu, person, aktion, text, von, nach)
    return neu


def lege_an(
    session: Session,
    vorschlag: Zahlungsvorschlag,
    einstellungen: ZahlungEinstellungen,
    person: str,
    ausfuehrung: date | None = None,
) -> Zahlungslauf:
    """Entwurf aus dem Vorschlag; Empfänger, IBAN und Beträge werden eingefroren."""
    a = einstellungen.auftraggeber
    if not a.name or not a.iban:
        msg = (
            "Auftraggeber fehlt: Name und IBAN des eigenen Kontos in "
            "zahlung.auftraggeber oder mandant.name/mandant.bank eintragen"
        )
        raise LaufError(msg)
    if not vorschlag.positionen:
        msg = "Nichts zu zahlen — der Vorschlag ist leer."
        raise LaufError(msg)
    nr = naechste_laufnummer(session)
    lauf = Zahlungslauf(
        nr=nr,
        stichtag=vorschlag.stichtag,
        ausfuehrung=ausfuehrung or vorschlag.stichtag,
        auftraggeber_name=a.name,
        auftraggeber_iban=a.iban,
        auftraggeber_bic=a.bic,
        erstellt_von=person,
    )
    for i, pos in enumerate(vorschlag.positionen, start=1):
        p, k = pos.posten, pos.kontakt
        lauf.zahlungen.append(
            Zahlung(
                lauf_id=lauf.id,
                nr=i,
                posten_id=p.id,
                kontakt_id=k.id,
                empfaenger=k.name,
                iban=normalisiere(k.iban),
                strasse=k.strasse,
                plz=k.plz,
                ort=k.ort,
                land=k.land,
                betrag=pos.betrag,
                skonto=pos.skonto,
                restbetrag_vorher=p.restbetrag,
                verwendungszweck=verwendungszweck(
                    p.belegnummer, p.belegdatum, pos.skonto
                ),
                end_to_end_id=referenz(p.belegnummer) or f"ACCOUNTI-{nr}-{i}",
                belegnummer=p.belegnummer,
                belegdatum=p.belegdatum,
                grund=pos.grund[:500],
            )
        )
    try:
        speichere_lauf(session, lauf)
    except PostenImLaufError as fehler:
        msg = (
            "Ein Posten steht bereits in einem aktiven Zahlungslauf — Vorschlag neu "
            "erstellen."
        )
        raise LaufError(msg) from fehler
    text = (
        f"{len(lauf.zahlungen)} Zahlungen über {betrag_de(lauf.summe)} € zum "
        f"{datum_de(lauf.ausfuehrung)}, davon {betrag_de(lauf.skonto)} € Skonto"
    )
    _protokoll(session, lauf, person, "angelegt", text, None, LaufStatus.ENTWURF)
    return lauf


def _nur_entwurf(lauf: Zahlungslauf) -> None:
    if lauf.status is not LaufStatus.ENTWURF:
        msg = (
            f"Lauf {lauf.nr} ist {lauf.status.value} — nicht mehr änderbar, nur "
            f"stornieren (accounti zahlung stornieren {lauf.nr} --grund …)"
        )
        raise ZustandError(msg)


def _zahlung(lauf: Zahlungslauf, nr: int) -> Zahlung:
    for z in lauf.zahlungen:
        if z.nr == nr:
            return z
    msg = f"Lauf {lauf.nr} hat keine Zahlung {nr}."
    raise LaufError(msg)


def entferne(session: Session, lauf_nr: int, zahlung_nr: int, person: str) -> Zahlung:
    """Nimmt eine Zahlung aus dem Entwurf; der Posten ist wieder frei."""
    lauf = lade_lauf(session, lauf_nr)
    _nur_entwurf(lauf)
    z = _zahlung(lauf, zahlung_nr)
    entferne_zahlung(session, z.id)
    _protokoll(
        session,
        lauf,
        person,
        "entfernt",
        f"Zahlung {z.nr} entfernt: {z.belegnummer or '—'} an {z.empfaenger} über "
        f"{betrag_de(z.betrag)} €",
    )
    return z


def pruefe(
    session: Session, lauf_nr: int, einstellungen: ZahlungEinstellungen, heute: date
) -> Pruefergebnis:
    return pruefe_lauf(session, lade_lauf(session, lauf_nr), einstellungen, heute)


def _freigaben_fuer(session: Session, lauf: Zahlungslauf, inhalt: str) -> set[str]:
    return {
        e.person
        for e in lade_protokoll(session, lauf.id)
        if e.aktion == "freigabe" and inhalt in e.text
    }


def freigeben(
    session: Session,
    lauf_nr: int,
    person: str,
    einstellungen: ZahlungEinstellungen,
    heute: date,
) -> Zahlungslauf:
    """Prüft und gibt frei; mit Vier-Augen-Prinzip erst bei der zweiten Person."""
    lauf = lade_lauf(session, lauf_nr)
    pruefe_uebergang(lauf, LaufStatus.FREIGEGEBEN)
    ergebnis = pruefe_lauf(session, lauf, einstellungen, heute)
    if not ergebnis.ok:
        raise LaufGesperrtError(ergebnis)
    inhalt = freigabe_hash(lauf)
    bisher = _freigaben_fuer(session, lauf, inhalt)
    if einstellungen.vier_augen:
        if person in bisher:
            msg = (
                f"{person} hat bereits freigegeben — das Vier-Augen-Prinzip verlangt "
                "eine zweite Person"
            )
            raise LaufError(msg)
        if not bisher:
            _protokoll(
                session,
                lauf,
                person,
                "freigabe",
                f"erste Freigabe — eine zweite Person muss freigeben (Inhalt {inhalt})",
                LaufStatus.ENTWURF,
                LaufStatus.ENTWURF,
            )
            return lauf
    text = (
        f"freigegeben: {len(lauf.zahlungen)} Zahlungen über "
        f"{betrag_de(lauf.summe)} € zum {datum_de(lauf.ausfuehrung)}"
        + (f", zweite Freigabe nach {', '.join(sorted(bisher))}" if bisher else "")
        + f" (Inhalt {inhalt})"
    )
    return _wechsel(
        session,
        lauf,
        LaufStatus.FREIGEGEBEN,
        person,
        "freigabe",
        text,
        freigabe_hash=inhalt,
    )


def markiere_eingereicht(
    session: Session,
    lauf: Zahlungslauf,
    person: str,
    datei: str,
    msg_id: str,
    zeitpunkt: datetime | None = None,
) -> Zahlungslauf:
    """Die SEPA-Datei ist erzeugt — ab jetzt kann Geld fließen."""
    pruefe_uebergang(lauf, LaufStatus.EINGEREICHT)
    datei_hash = hashlib.sha256(datei.encode("utf-8")).hexdigest()
    return _wechsel(
        session,
        lauf,
        LaufStatus.EINGEREICHT,
        person,
        "eingereicht",
        f"SEPA-Datei {msg_id} erzeugt (pain.001.001.09, SHA-256 {datei_hash})",
        datei=datei,
        datei_hash=datei_hash,
        msg_id=msg_id,
        eingereicht_am=zeitpunkt or datetime.now().replace(microsecond=0),
    )


def storniere(session: Session, lauf_nr: int, person: str, grund: str) -> Zahlungslauf:
    """Storno mit Grund und Protokoll; die Posten werden wieder frei."""
    lauf = lade_lauf(session, lauf_nr)
    pruefe_uebergang(lauf, LaufStatus.STORNIERT)
    if not grund.strip():
        msg = "Ein Storno braucht einen Grund (--grund)."
        raise LaufError(msg)
    return _wechsel(
        session, lauf, LaufStatus.STORNIERT, person, "storniert", grund.strip()
    )


def iban_klaeren(
    session: Session, lauf_nr: int, zahlung_nr: int, person: str, grund: str
) -> IbanKlaerung:
    """Hält fest: trotz anderer IBAN auf der Rechnung wird an den Stammsatz gezahlt."""
    lauf = lade_lauf(session, lauf_nr)
    _nur_entwurf(lauf)
    z = _zahlung(lauf, zahlung_nr)
    if not grund.strip():
        msg = "Die Klärung braucht einen Grund (--grund), z.B. wer wann angerufen hat."
        raise LaufError(msg)
    p = lade_einen_posten(session, z.posten_id)
    beleg = lade_beleg(session, p.beleg_id)
    rechnung = normalisiere(beleg.iban if beleg else None)
    stamm = normalisiere(lade_kontakt(session, str(z.kontakt_id)).iban)
    if not rechnung or rechnung == stamm:
        msg = (
            f"Zahlung {zahlung_nr}: keine IBAN-Abweichung zwischen Rechnung und "
            "Stammsatz."
        )
        raise LaufError(msg)
    klaerung = IbanKlaerung(
        posten_id=p.id,
        rechnungs_iban=rechnung,
        stammsatz_iban=stamm,
        grund=grund.strip(),
        person=person,
    )
    speichere_iban_klaerung(session, klaerung)
    _protokoll(
        session,
        lauf,
        person,
        "iban_geklaert",
        f"IBAN-Abweichung geklärt für Zahlung {z.nr} ({z.belegnummer or '—'}): "
        f"Rechnung {lesbar(rechnung)}, gezahlt wird an den Stammsatz "
        f"{lesbar(stamm)} — {klaerung.grund}",
    )
    return klaerung


def setze_sperre(session: Session, schluessel: str, grund: str, person: str) -> Kontakt:
    if not grund.strip():
        msg = "Eine Zahlungssperre braucht einen Grund (--grund)."
        raise LaufError(msg)
    k = lade_kontakt(session, schluessel)
    setze_zahlungssperre(
        session,
        Zahlungssperre(kontakt_id=k.id, grund=grund.strip(), gesetzt_von=person),
    )
    return k


def hebe_sperre_auf(session: Session, schluessel: str) -> tuple[Kontakt, bool]:
    k = lade_kontakt(session, schluessel)
    return k, hebe_zahlungssperre_auf(session, k.id)
