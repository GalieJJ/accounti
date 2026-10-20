"""Prüfstufe des Zahlungsverkehrs — blockierend, nicht beratend.

Hier bewegt ein Softwarefehler unmittelbar Geld. Jeder Befund sperrt den ganzen Lauf
und nennt den Grund. Eine IBAN, die vom Stammsatz abweicht, ist ein Stoppschild:
Genau so funktionieren gefälschte Rechnungen mit ausgetauschter Bankverbindung.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.anzeige import betrag_de, datum_de
from accounti.db.repo_zahlung import (
    lade_iban_klaerungen,
    lade_zahlungssperren,
    zahlungen_zum_posten,
)
from accounti.db.repository import lade_beleg, lade_einen_posten, lade_kontakte
from accounti.models import Kontakt, KontaktStatus, OffenerPosten, PostenStatus
from accounti.models.zahlung import AKTIVE_STATUS, Zahlung, Zahlungslauf
from accounti.zahlung.iban import (
    gueltig,
    im_ewr,
    im_sepa_raum,
    lesbar,
    normalisiere,
)
from accounti.zahlung.konfiguration import ZahlungEinstellungen
from accounti.zahlung.vorschlag import (
    vorgeschlagene_zahlungen,
    zahlung_vorgeschlagen_text,
)
from accounti.zahlung.zeichen import sepa_text

HOECHSTER_SEPA_BETRAG = Decimal("999999999.99")


@dataclass(frozen=True)
class Befund:
    nr: int | None  # Zahlung im Lauf; None = der Lauf als Ganzes
    text: str


@dataclass
class Pruefergebnis:
    lauf_nr: int
    befunde: list[Befund] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.befunde

    def zeilen(self) -> list[str]:
        return [
            f"Zahlung {b.nr}: {b.text}" if b.nr is not None else b.text
            for b in self.befunde
        ]


def _bezeichnung(p: OffenerPosten) -> str:
    return p.belegnummer or str(p.id)[:8]


def _betrag(z: Zahlung, p: OffenerPosten, lauf: Zahlungslauf) -> list[str]:
    """Betrag = Restbetrag oder Restbetrag − Skonto, Skonto nur in der Frist."""
    if p.status is PostenStatus.AUSGEGLICHEN or p.restbetrag == 0:
        return [f"Posten {_bezeichnung(p)} ist bereits ausgeglichen"]
    if p.restbetrag != z.restbetrag_vorher:
        return [
            f"Posten {_bezeichnung(p)} hat sich seit der Anlage geändert (Rest jetzt "
            f"{betrag_de(p.restbetrag)} € statt {betrag_de(z.restbetrag_vorher)} €) "
            "— Zahlung entfernen oder Lauf neu anlegen"
        ]
    if z.skonto > 0:
        if (
            p.skonto_betrag != z.skonto
            or z.betrag + z.skonto != p.restbetrag
            or p.restbetrag != p.betrag
        ):
            return [
                f"Betrag {betrag_de(z.betrag)} € + Skonto {betrag_de(z.skonto)} € "
                f"passt nicht zu Posten {_bezeichnung(p)} (Rest "
                f"{betrag_de(p.restbetrag)} €)"
            ]
        if p.skonto_bis is None or p.skonto_bis < lauf.ausfuehrung:
            return [
                f"Skonto {betrag_de(z.skonto)} € nur bis {datum_de(p.skonto_bis)}, "
                f"Ausführung erst am {datum_de(lauf.ausfuehrung)} — Ausführungstag "
                "vorziehen oder ohne Skonto neu anlegen"
            ]
    elif z.betrag != p.restbetrag:
        return [
            f"Betrag {betrag_de(z.betrag)} € entspricht weder dem Rest "
            f"{betrag_de(p.restbetrag)} € von {_bezeichnung(p)} noch dem Rest "
            "abzüglich Skonto"
        ]
    return []


def _iban(
    session: Session,
    lauf: Zahlungslauf,
    z: Zahlung,
    p: OffenerPosten,
    k: Kontakt,
) -> list[str]:
    stamm = normalisiere(k.iban)
    if not stamm:
        return [f"{k.name} hat keine IBAN im Stammsatz"]
    befunde = []
    if not gueltig(stamm):
        befunde.append(f"IBAN {lesbar(stamm)} im Stammsatz ist ungültig (Prüfziffer)")
    elif not im_sepa_raum(stamm):
        befunde.append(f"IBAN {lesbar(stamm)} liegt nicht im SEPA-Raum ({stamm[:2]})")
    elif not im_ewr(stamm):
        befunde.append(
            f"IBAN {lesbar(stamm)} liegt außerhalb des EWR ({stamm[:2]}) — dorthin "
            "verlangt SEPA zusätzlich den BIC der Empfängerbank und die Anschrift des "
            "Auftraggebers, die accounti nicht schreibt; Zahlung entfernen und im "
            "Onlinebanking einzeln überweisen"
        )
    if normalisiere(z.iban) != stamm:
        befunde.append(
            f"IBAN der Zahlung {lesbar(z.iban)} weicht vom Stammsatz {lesbar(stamm)} "
            "ab — Zahlung entfernen oder Lauf stornieren und neu anlegen"
        )
    beleg = lade_beleg(session, p.beleg_id)
    rechnung = normalisiere(beleg.iban if beleg else None)
    if rechnung and rechnung != stamm and not _geklaert(session, p.id, rechnung, stamm):
        konto = k.kreditor_konto or str(k.id)[:8]
        befunde.append(
            f"IBAN-Abweichung: Rechnung {_bezeichnung(p)} von {k.name} nennt "
            f"{lesbar(rechnung)}, im Stammsatz steht {lesbar(stamm)}. Nicht zahlen, "
            "bevor die Bankverbindung beim Lieferanten auf bekanntem Weg bestätigt "
            "ist (bekannte Telefonnummer, nicht die aus Rechnung oder E-Mail) — dann "
            f"Stammsatz ändern (accounti kontakte bearbeiten {konto} --iban …) oder "
            "die Abweichung klären (accounti zahlung iban-klaeren "
            f"{lauf.nr} {z.nr} --grund …)."
        )
    if beleg is not None and beleg.waehrung != "EUR":
        befunde.append(
            f"Rechnung {_bezeichnung(p)} lautet auf {beleg.waehrung} — "
            "SEPA-Überweisungen nur in EUR"
        )
    return befunde


def _geklaert(session: Session, posten_id: UUID, rechnung: str, stamm: str) -> bool:
    return any(
        k.rechnungs_iban == rechnung and k.stammsatz_iban == stamm
        for k in lade_iban_klaerungen(session, posten_id)
    )


def _lauf_befunde(lauf: Zahlungslauf, heute: date) -> list[Befund]:
    befunde = []
    if not sepa_text(lauf.auftraggeber_name, 70):
        befunde.append(
            Befund(
                None,
                "Name des Auftraggebers fehlt oder enthält keine Zeichen aus dem "
                "SEPA-Zeichensatz (zahlung.auftraggeber.name)",
            )
        )
    if not gueltig(lauf.auftraggeber_iban):
        befunde.append(
            Befund(
                None,
                f"Auftraggeber-IBAN {lesbar(lauf.auftraggeber_iban)} ist ungültig — "
                "zahlung.auftraggeber oder mandant.bank in der Konfiguration prüfen",
            )
        )
    if lauf.ausfuehrung < heute:
        befunde.append(
            Befund(
                None,
                f"Ausführungstag {datum_de(lauf.ausfuehrung)} liegt in der "
                "Vergangenheit — Lauf stornieren und neu anlegen",
            )
        )
    if not lauf.zahlungen:
        befunde.append(Befund(None, "Der Lauf enthält keine Zahlungen"))
    return befunde


def pruefe_lauf(
    session: Session,
    lauf: Zahlungslauf,
    einstellungen: ZahlungEinstellungen,
    heute: date,
) -> Pruefergebnis:
    """Alle Befunde eines Laufs; ``ok`` nur, wenn es keinen gibt."""
    ergebnis = Pruefergebnis(lauf.nr, _lauf_befunde(lauf, heute))
    kontakte = {k.id: k for k in lade_kontakte(session)}
    sperren = lade_zahlungssperren(session)
    vorgeschlagen = vorgeschlagene_zahlungen(session)
    gesehen: dict[UUID, int] = {}
    for z in lauf.zahlungen:
        texte: list[str] = []
        try:
            p = lade_einen_posten(session, z.posten_id)
        except ValueError:
            ergebnis.befunde.append(Befund(z.nr, "Der Posten existiert nicht mehr"))
            continue
        texte += _betrag(z, p, lauf)
        if z.betrag <= 0 or z.betrag > HOECHSTER_SEPA_BETRAG:
            texte.append(
                f"Betrag {betrag_de(z.betrag)} € ist nicht überweisbar "
                "(0,01 bis 999.999.999,99 €)"
            )
        grenze = einstellungen.hoechstbetrag_zahlung
        if grenze is not None and z.betrag > grenze:
            texte.append(
                f"Betrag {betrag_de(z.betrag)} € über der Grenze je Zahlung von "
                f"{betrag_de(grenze)} € (zahlung.hoechstbetrag_zahlung)"
            )
        k = kontakte.get(z.kontakt_id)
        if not sepa_text(z.empfaenger, 70):
            konto = (k.kreditor_konto or str(k.id)[:8]) if k else "…"
            texte.append(
                f"Empfängername „{z.empfaenger}“ enthält keine Zeichen aus dem "
                "SEPA-Zeichensatz — Namen im Stammsatz in lateinischer Schrift "
                f"pflegen (accounti kontakte bearbeiten {konto} --name …), dann "
                "Zahlung entfernen und neu anlegen"
            )
        if not sepa_text(z.verwendungszweck, 140):
            texte.append(
                "Verwendungszweck ist leer — Zahlung entfernen und neu anlegen"
            )
        if k is None:
            texte.append("Der Kontakt existiert nicht mehr")
        else:
            if k.status is KontaktStatus.ZUR_PRUEFUNG:
                texte.append(
                    f"{k.name} ist noch zur Prüfung (automatisch angelegt) — erst "
                    "prüfen und mit 'accounti kontakte bestaetigen "
                    f"{k.kreditor_konto or str(k.id)[:8]}' freigeben"
                )
            sperre = sperren.get(k.id)
            if sperre is not None:
                texte.append(
                    f"Zahlungssperre für {k.name}: {sperre.grund} "
                    f"({sperre.gesetzt_von})"
                )
            texte += _iban(session, lauf, z, p, k)
        if p.id in gesehen:
            texte.append(
                f"Posten {_bezeichnung(p)} steht zweimal in diesem Lauf "
                f"(auch Zahlung {gesehen[p.id]})"
            )
        gesehen.setdefault(p.id, z.nr)
        if p.id in vorgeschlagen:
            texte.append(
                zahlung_vorgeschlagen_text(
                    vorgeschlagen[p.id], f"Posten {_bezeichnung(p)}"
                )
            )
        for _, nr, status in zahlungen_zum_posten(session, p.id):
            if nr != lauf.nr and status in AKTIVE_STATUS:
                texte.append(
                    f"Posten {_bezeichnung(p)} steht schon in Zahlungslauf {nr} "
                    f"({status.value}) — nie zweimal überweisen"
                )
        ergebnis.befunde += [Befund(z.nr, t) for t in texte]
    return ergebnis
